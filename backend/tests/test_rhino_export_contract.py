"""Source/native contract checks; real Rhino save/reopen is a separate execution gate."""
from copy import deepcopy
import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

from backend.app.mesh_primitives import primitive_mesh, triangulate_faces

_SPEC = importlib.util.spec_from_file_location('mta_rhino_adapter',
    Path(__file__).resolve().parents[2] / 'rhino/import_building_model_v3.py')
adapter = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(adapter)


def xyz(x, y, z):
    return dict(x=x, y=y, z=z)


def xy_ring(points):
    return [dict(x=x, y=y) for x,y in points]


def box():
    return dict(type='box', center=xyz(10,20,4), size=xyz(4,2,3), rotation_z=math.pi/4)


def extrusion():
    return dict(type='extrusion', boundary=xy_ring([(0,0),(6,0),(6,4),(0,4)]),
        holes=[xy_ring([(1,1),(3,1),(3,3),(1,3)])], z_base=8, z_top=8.3)


def model_of(*geometries):
    return {'schema_version':'3.0', 'model_id':'native-contract-fixture',
        'units':'meters', 'coordinate_system':'right_handed_z_up', 'lattice':{'cutaway':False},
        'profiles':{}, 'element_groups':[{'group_id':'slab-group', 'kind':'floor_slab',
            'semantic_layer':'structure', 'subsystem':'floor', 'instances':[
                {'id':f'source-{index}', 'level_id':'L01', 'geometry':geometry}
                for index,geometry in enumerate(geometries)]}]}


def program_volume_model():
    return {
        'schema_version':'mta.program_volumes/1.0',
        'score_id':'score-program-volume-fixture',
        'typology':'library',
        'grammar_id':'PVG-SPLIT-BRIDGE',
        'grammar_reason':['Fixture authored by the score.'],
        'levels':[
            {'index':1,'id':'L01','z_base':0.0,'z_top':4.0},
            {'index':2,'id':'L02','z_base':4.0,'z_top':8.0},
        ],
        'grid':{
            'x_lines':[0.0,4.0,8.0,12.0],
            'y_lines':[0.0,5.0,10.0],
            'band_lines':[0.0,5.0,10.0],
            'apse_nodes':[],
        },
        'volumes':[
            {'id':'PV-L01-PROGRAM','level_index':1,'level_id':'L01',
             'category':'public','role':'program','space_ids':['SP-READING'],
             'grid_rect':[0,0,1,1],'target_area_m2':20.0,'gross_area_m2':20.0,
             'reason':'Fixture program volume.'},
            {'id':'PV-L01-ARCHETYPE','level_index':1,'level_id':'L01',
             'category':'private','role':'archetype','space_ids':['SP-STACKS'],
             'grid_rect':[1,0,2,1],'target_area_m2':20.0,'gross_area_m2':20.0,
             'reason':'Fixture archetype volume.'},
            {'id':'PV-L02-SPINE','level_index':2,'level_id':'L02',
             'category':'circulation','role':'circulation_spine','space_ids':[],
             'grid_rect':[1,1,2,2],'target_area_m2':0.0,'gross_area_m2':20.0,
             'reason':'Fixture circulation carrier.'},
            {'id':'PV-L02-CONNECTOR','level_index':2,'level_id':'L02',
             'category':'circulation','role':'connector','space_ids':[],
             'grid_rect':[2,1,3,2],'target_area_m2':0.0,'gross_area_m2':20.0,
             'reason':'Fixture connector volume.'},
        ],
        'level_unions':[
            {'level_index':1,'level_id':'L01','boundary':[[0,0],[8,0],[8,5],[0,5]],
             'voids':[],'gross_area_m2':40.0,
             'source_volume_ids':['PV-L01-PROGRAM','PV-L01-ARCHETYPE']},
            {'level_index':2,'level_id':'L02','boundary':[[4,5],[12,5],[12,10],[4,10]],
             'voids':[],'gross_area_m2':40.0,
             'source_volume_ids':['PV-L02-SPINE','PV-L02-CONNECTOR']},
        ],
        'topology_signature':'fixture-split-bridge',
        'program_volume_regions':[],
        'circulation_intent':None,
        'roof_control':None,
        'note':'Fixture Program Volume protocol.',
    }


def test_rotated_box_preserves_native_dimensions_and_source_volume():
    contract = adapter.primitive_contract(box(), {})
    assert contract['recipe'] == 'box_brep'
    assert contract['expected_volume_m3'] == pytest.approx(24)
    bounds = np.array(contract['expected_bounds_m'])
    assert bounds[1]-bounds[0] == pytest.approx([3*math.sqrt(2),3*math.sqrt(2),3])
    assert bounds.mean(axis=0) == pytest.approx([10,20,4])


def test_architectural_hole_remains_a_separate_inner_profile():
    geometry = extrusion()
    before = deepcopy(geometry)
    contract = adapter.primitive_contract(geometry, {})
    assert geometry == before
    assert contract['hole_count'] == 1
    assert len(contract['holes']) == 1
    assert adapter._area(contract['holes'][0]) == -4
    assert contract['path'] == [(0,0,8),(0,0,8.3)]
    assert contract['expected_volume_m3'] == pytest.approx(6)


@pytest.mark.parametrize('outline',[
    [(0,0),(6,0),(6,4),(0,4)], [(0,4),(6,4),(6,0),(0,0)],
    [(0,0),(6,0),(6,4),(0,4),(0,0)],
])
def test_ring_winding_and_repeated_closure_do_not_move_the_solid(outline):
    geometry = extrusion()
    geometry['boundary'] = xy_ring(outline)
    contract = adapter.primitive_contract(geometry, {})
    assert len(contract['outer']) == 4
    assert contract['expected_volume_m3'] == pytest.approx(6)


@pytest.mark.parametrize('roll', [xyz(0,0,1), xyz(1,0,0), xyz(1,2,3)])
def test_straight_member_uses_exact_shared_profile_and_roll(roll):
    profiles = {'i':dict(shape='i_section', depth_m=.6, width_m=.3, web_m=.02, flange_m=.03)}
    geometry = dict(type='member',path=[xyz(0,0,0),xyz(3,0,0)],profile='i',roll=roll)
    contract = adapter.primitive_contract(geometry, profiles)
    assert contract['recipe'] == 'profile_extrusion'
    assert len(contract['outer']) == 12
    assert contract['expected_volume_m3'] == pytest.approx((2*.3*.03+(.6-.06)*.02)*3)
    assert sum(a*b for a,b in zip(contract['up'],(1,0,0))) == pytest.approx(0)
    vertices,_ = primitive_mesh(geometry,profiles)
    assert np.array(contract['expected_bounds_m']) == pytest.approx(np.array([np.min(vertices,axis=0),np.max(vertices,axis=0)]))


def test_curved_member_native_face_plan_is_the_exact_shared_body():
    profiles = {'r':dict(shape='rectangle', depth_m=.5, width_m=.2)}
    geometry = dict(type='member',path=[xyz(0,0,0),xyz(1,0,.3),xyz(2,.2,.8)], profile='r')
    contract = adapter.primitive_contract(geometry, profiles)
    assert contract['recipe'] == 'member_faceted_brep'
    vertices,faces = primitive_mesh(geometry,profiles)
    assert contract['vertices'] == vertices and contract['faces'] == faces
    trimesh = pytest.importorskip('trimesh')
    mesh = trimesh.Trimesh(vertices=vertices, faces=triangulate_faces(vertices,faces), process=True)
    assert mesh.is_volume
    assert contract['expected_volume_m3'] == pytest.approx(mesh.volume)


def test_planar_quad_thickness_is_centered_on_the_source_plane():
    geometry = dict(type='quad', corners=[xyz(3,2,4),xyz(3,7,4),xyz(3,7,6),xyz(3,2,6)])
    contract = adapter.primitive_contract(geometry, {}, .2)
    assert contract['recipe'] == 'profile_extrusion'
    assert contract['expected_volume_m3'] == pytest.approx(2)
    assert np.array(contract['expected_bounds_m']) == pytest.approx(np.array([[2.9,2,4],[3.1,7,6]]))


@pytest.mark.parametrize('change', ['missing_thickness','zero_thickness','nonplanar','duplicate_corner'])
def test_unresolved_quad_cannot_be_disguised_as_a_native_solid(change):
    geometry = dict(type='quad', corners=[xyz(0,0,0),xyz(2,0,0),xyz(2,2,0),xyz(0,2,0)])
    thickness = .1
    if change == 'missing_thickness': thickness = None
    if change == 'zero_thickness': thickness = 0
    if change == 'nonplanar': geometry['corners'][3]['z'] = .5
    if change == 'duplicate_corner': geometry['corners'][1] = geometry['corners'][0]
    with pytest.raises(ValueError):
        adapter.primitive_contract(geometry, {}, thickness)


@pytest.mark.parametrize('change', ['cutaway','unknown_cutaway','units','web_summary','duplicate_id','empty'])
def test_incomplete_or_ambiguous_model_is_rejected(change):
    model = model_of(box(),extrusion())
    if change == 'cutaway': model['lattice']['cutaway'] = True
    if change == 'unknown_cutaway': del model['lattice']['cutaway']
    if change == 'units': model['units'] = 'millimeters'
    if change == 'web_summary': del model['element_groups'][0]['instances']
    if change == 'duplicate_id': model['element_groups'][0]['instances'][1]['id'] = 'source-0'
    if change == 'empty': model['element_groups'][0]['instances'] = []
    with pytest.raises(ValueError):
        adapter.prepare_model(model)


def test_source_semantics_and_identity_survive_without_design_acceptance():
    model = model_of(box(),extrusion())
    model['element_groups'][0].update(datum_refs=['grid-X1'], reason='Fixture source rule', section_id='A')
    model['element_groups'][0]['instances'][0].update(assembly_id='assembly-a',part_role='top',supports=['source-1'])
    before = deepcopy(model)
    records = adapter.prepare_model(model)
    assert model == before
    metadata = records[0]['metadata']
    assert metadata['id'] == 'source-0' and metadata['model_id'] == model['model_id']
    assert metadata['datum_refs'] == ['grid-X1']
    assert metadata['supports'] == ['source-1'] and metadata['assembly_id'] == 'assembly-a'
    assert metadata['authority'] == 'candidate'


def test_program_volume_references_are_separate_native_contracts():
    model = model_of(box(),extrusion())
    model['program_volume_model'] = program_volume_model()
    before = deepcopy(model)
    source_records = adapter.prepare_model(model)
    references = adapter.prepare_program_volume_references(model)
    assert model == before
    assert len(source_records) == 2
    assert len(references) == 4
    assert {reference['metadata']['role'] for reference in references} == {
        'program','archetype','circulation_spine','connector'}
    assert all('id' not in reference['metadata'] for reference in references)
    assert all(reference['contract']['recipe'] == 'profile_extrusion'
               for reference in references)
    assert all(reference['layer_path'].startswith(
        'MTA::Reference::Program_Volumes::') for reference in references)
    program = next(reference for reference in references
                   if reference['volume_id'] == 'PV-L01-PROGRAM')
    assert program['contract']['expected_bounds_m'] == [[0.0,0.0,0.0],[4.0,5.0,4.0]]
    assert program['contract']['expected_volume_m3'] == pytest.approx(80.0)
    assert program['metadata']['grammar_id'] == 'PVG-SPLIT-BRIDGE'
    assert program['metadata']['space_ids'] == ['SP-READING']
    assert len(program['metadata']['program_volume_digest']) == 64
    assert len({reference['metadata']['program_volume_digest']
                for reference in references}) == 1
    changed = deepcopy(model)
    changed['program_volume_model']['volumes'][0]['space_ids'].append('SP-CHANGED')
    assert (adapter.prepare_program_volume_references(changed)[0]['metadata'][
        'program_volume_digest'] != program['metadata']['program_volume_digest'])


def test_models_without_program_volume_contract_remain_exportable():
    assert adapter.prepare_program_volume_references(model_of(box())) == []


def test_program_volume_outside_grid_is_rejected_with_its_identity():
    model = model_of(box())
    model['program_volume_model'] = program_volume_model()
    model['program_volume_model']['volumes'][2]['grid_rect'] = [1,1,4,2]
    with pytest.raises(ValueError,match='PV-L02-SPINE'):
        adapter.prepare_program_volume_references(model)


def test_bad_source_reports_the_specific_element_instead_of_dropping_it():
    geometry = box()
    geometry['size']['x'] = 0
    with pytest.raises(ValueError, match='source-0'):
        adapter.prepare_model(model_of(geometry))


@pytest.fixture
def file_sdk():
    return pytest.importorskip('rhino3dm',reason='optional standalone native file SDK')


def test_standalone_file_roundtrip_keeps_holes_ids_units_and_editable_solids(tmp_path,file_sdk):
    from rhino.export_file import export_file, validate_file
    model = model_of(box(),extrusion())
    path = tmp_path/'model.json'
    import json
    path.write_text(json.dumps(model))
    original = path.read_bytes()
    report = export_file(path,tmp_path/'native',run_id='run-test')
    assert report['native_types'] == {'Brep':1,'Extrusion':1}
    assert report['object_count'] == report['source_element_count'] == 2
    assert report['verification']['saved_file_reopened'] == 'passed'
    assert report['verification']['native_volume'] == 'not_checked'
    assert report['verification']['rhino_gui_review'] == 'not_checked'
    assert report['verification']['rhino_acceptance'] == 'not_recorded'
    assert report['verification']['program_volume_references'] == 'not_applicable'
    assert report['program_volume_reference_count'] == 0
    assert report['objects']['source-1']['hole_count'] == 1
    assert path.read_bytes() == original
    saved = file_sdk.File3dm.Read(str(tmp_path/'native/model.3dm'))
    assert saved.Settings.ModelUnitSystem == file_sdk.UnitSystem.Meters
    assert {type(obj.Geometry).__name__ for obj in saved.Objects} == {'Brep','Extrusion'}
    assert all(obj.Geometry.IsSolid and obj.Geometry.IsValid for obj in saved.Objects)
    with pytest.raises(FileExistsError):
        export_file(path,tmp_path/'native',run_id='run-test')
    metadata = {key:saved.Strings['mta:'+key] for key in ('model_id','run_id','source_sha256','producer','authority','representation','coordinate_system','adapter_version')}
    metadata['run_id'] = 'wrong-run'
    with pytest.raises(ValueError,match='metadata mismatch'):
        validate_file(tmp_path/'native/model.3dm',adapter.prepare_model(model),metadata)


def test_standalone_roundtrip_keeps_program_volumes_hidden_locked_and_out_of_source_count(
        tmp_path,file_sdk):
    from rhino.export_file import export_file
    model = model_of(box(),extrusion())
    model['program_volume_model'] = program_volume_model()
    path = tmp_path/'model.json'
    import json
    path.write_text(json.dumps(model))
    report = export_file(path,tmp_path/'native',run_id='run-program-volume')
    assert report['object_count'] == report['source_element_count'] == 2
    assert report['file_object_count'] == 6
    assert report['program_volume_reference_count'] == 4
    assert report['program_volume_reference_native_types'] == {'Extrusion':4}
    assert report['verification']['program_volume_references'] == 'passed'
    saved = file_sdk.File3dm.Read(str(tmp_path/'native/model.3dm'))
    references = [obj for obj in saved.Objects
                  if obj.Attributes.GetUserString('mta:reference_kind') == 'program_volume']
    assert len(references) == 4
    for obj in references:
        layer = saved.Layers[obj.Attributes.LayerIndex]
        assert layer.FullPath.startswith('MTA::Reference::Program_Volumes::')
        assert layer.Visible is False and layer.Locked is True
        assert obj.Attributes.Mode == file_sdk.ObjectMode.Locked
        assert not obj.Attributes.GetUserString('mta:id')
        assert obj.Attributes.GetUserString('mta:volume_id') == obj.Attributes.Name
        assert obj.Attributes.GetUserString('mta:grammar_id') == 'PVG-SPLIT-BRIDGE'
        assert len(obj.Attributes.GetUserString('mta:program_volume_digest')) == 64
        assert isinstance(json.loads(obj.Attributes.GetUserString('mta:space_ids')),list)
        assert isinstance(obj.Geometry,file_sdk.Extrusion)
        assert obj.Geometry.IsSolid and obj.Geometry.IsValid


def test_standalone_validator_rejects_changed_program_volume_layer_or_metadata(
        tmp_path,file_sdk):
    from rhino.export_file import export_file,validate_file
    import json
    model = model_of(box())
    model['program_volume_model'] = program_volume_model()
    path = tmp_path/'model.json'
    path.write_text(json.dumps(model))
    export_file(path,tmp_path/'native',run_id='run-program-volume')
    original = file_sdk.File3dm.Read(str(tmp_path/'native/model.3dm'))
    reference = next(obj for obj in original.Objects
                     if obj.Attributes.GetUserString('mta:reference_kind') == 'program_volume')
    original.Layers[reference.Attributes.LayerIndex].Visible = True
    changed_layer = tmp_path/'changed-layer.3dm'
    assert original.Write(str(changed_layer),8)
    metadata = {key:original.Strings['mta:'+key] for key in (
        'model_id','run_id','source_sha256','producer','authority','representation',
        'coordinate_system','adapter_version')}
    references = adapter.prepare_program_volume_references(model)
    with pytest.raises(ValueError,match='hidden locked reference layer'):
        validate_file(changed_layer,adapter.prepare_model(model),metadata,
                      program_volume_references=references)

    changed = file_sdk.File3dm.Read(str(tmp_path/'native/model.3dm'))
    reference = next(obj for obj in changed.Objects
                     if obj.Attributes.GetUserString('mta:reference_kind') == 'program_volume')
    reference.Attributes.SetUserString('mta:grammar_id','PVG-TERRACED-WEAVE')
    changed_metadata = tmp_path/'changed-metadata.3dm'
    assert changed.Write(str(changed_metadata),8)
    with pytest.raises(ValueError,match='lost metadata: grammar_id'):
        validate_file(changed_metadata,adapter.prepare_model(model),metadata,
                      program_volume_references=references)


def test_standalone_polyline_ramp_is_an_exact_native_extrusion(file_sdk):
    from rhino.export_file import build_file_geometry,validate_file_geometry,_exact_prism_contract
    profiles = {'r':dict(shape='box',depth_m=.24,width_m=1.63)}
    geometry = dict(type='member',path=[xyz(0,3,0),xyz(.76,3,0),xyz(9,3,.69),xyz(9.76,3,.69)],profile='r',roll=xyz(0,0,1))
    contract = adapter.primitive_contract(geometry,profiles)
    exact = _exact_prism_contract(contract)
    assert exact['conversion'] == 'exact_constant_width_source_polyhedron'
    assert exact['expected_volume_m3'] == contract['expected_volume_m3']
    body = build_file_geometry(file_sdk,contract)
    assert isinstance(body,file_sdk.Extrusion)
    assert body.IsSolid and body.IsValid
    assert validate_file_geometry(file_sdk,body,contract)['native_type'] == 'Extrusion'


def test_unsupported_spatial_member_never_gets_an_approximate_prism(file_sdk):
    from rhino.export_file import build_file_geometry,validate_file_geometry,_exact_prism_contract
    profiles = {'r':dict(shape='i_section',depth_m=.5,width_m=.3,web_m=.03,flange_m=.04)}
    geometry = dict(type='member',path=[xyz(0,0,0),xyz(1,0,.3),xyz(2,.2,.8)],profile='r')
    contract = adapter.primitive_contract(geometry,profiles)
    assert _exact_prism_contract(contract) is None
    body = build_file_geometry(file_sdk,contract)
    assert isinstance(body,file_sdk.Brep)
    # Some SDK releases leave edge tolerances unset after CreateFromMesh. That
    # defect must remain visible; a valid SDK conversion may proceed unchanged.
    if not body.IsValid:
        with pytest.raises(ValueError,match='invalid or open'):
            validate_file_geometry(file_sdk,body,contract)
    else:
        assert validate_file_geometry(file_sdk,body,contract)['native_type'] == 'Brep'


@pytest.mark.parametrize('angle', [0, math.pi/4, 1.3, math.pi])
@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('rise', [.145, -.145])
def test_vertical_return_keeps_its_path_plane_and_exact_native_body(tmp_path,file_sdk,angle,reverse,rise):
    from rhino.export_file import build_file_geometry, validate_file_geometry, _exact_prism_contract
    profiles = {'r':dict(shape='rectangle', depth_m=.14, width_m=.075)}
    direction = np.array([math.cos(angle), math.sin(angle), 0.])
    normal = np.array([-math.sin(angle), math.cos(angle), 0.])
    origin = np.array([-57., -36., 5.3])
    path = [origin, origin+direction*1.24, origin+direction*1.24+[0,0,rise]]
    if reverse:
        path.reverse()
    geometry = dict(type='member',path=[xyz(*p) for p in path],profile='r',roll=xyz(0,0,1))
    original = deepcopy(geometry)
    contract = adapter.primitive_contract(geometry,profiles)
    vertices = np.array(contract['vertices'])
    # All station rings keep the same lateral width and centred source path.
    for station, centre in zip(vertices.reshape(-1,4,3), path):
        assert station.mean(axis=0) == pytest.approx(centre)
        assert sorted((station-centre) @ normal) == pytest.approx([-.0375,-.0375,.0375,.0375])
        assert np.linalg.norm(station[1]-station[0]) == pytest.approx(.075)
        assert np.linalg.norm(station[2]-station[1]) == pytest.approx(.14)
    assert geometry == original
    assert _exact_prism_contract(contract) is not None
    body = build_file_geometry(file_sdk,contract)
    result = validate_file_geometry(file_sdk,body,contract)
    assert result['native_type'] == 'Extrusion'
    native = file_sdk.File3dm()
    native.Objects.AddExtrusion(body,file_sdk.ObjectAttributes())
    path_3dm = tmp_path/'return.3dm'
    assert native.Write(str(path_3dm),8)
    reopened = file_sdk.File3dm.Read(str(path_3dm))
    assert validate_file_geometry(file_sdk,reopened.Objects[0].Geometry,contract)['valid']
    mesh = pytest.importorskip('trimesh').Trimesh(
        vertices=vertices,faces=triangulate_faces(vertices,contract['faces']),process=True)
    assert mesh.is_volume
    assert mesh.volume == pytest.approx(contract['expected_volume_m3'])


def test_standalone_rejects_crossed_hole_before_file_creation(file_sdk):
    from rhino.export_file import build_file_geometry
    geometry = extrusion()
    geometry['holes'] = [xy_ring([(5,1),(7,1),(7,3),(5,3)])]
    contract = adapter.primitive_contract(geometry,{})
    with pytest.raises(ValueError,match='Invalid outer profile'):
        build_file_geometry(file_sdk,contract)
