"""Negative fixtures for source-to-STL fabrication, not printer certification."""
from copy import deepcopy
from math import pi
from pathlib import Path
import json

import numpy as np
import pytest
from pydantic import ValidationError

from backend.app.fabrication import (
    PrintPart, PrintPlan, PrintProfile, export_print_package, level_plan, mesh_for,
)
from backend.app.geometry import BoxGeometry, ExtrusionGeometry, MemberGeometry, v2, v3
from backend.app.mesh_primitives import box_mesh, member_mesh


def box_at(x=0, y=0, z=.5, size=(1, 1, 1), rotation=0):
    return BoxGeometry(center=v3(x,y,z), size=v3(*size), rotation_z=rotation).model_dump()


def model_of(*geometries, kind='floor_slab', thickness=None):
    return {'schema_version':'3.0','model_id':'synthetic-print-fixture',
            'lattice':{'cutaway':False},'profiles':{},
            'element_groups':[{'kind':kind,'thickness_m':thickness,'instances':[
                {'id':f'element-{i}','level_id':'L01','geometry':g}
                for i,g in enumerate(geometries)]}]}


def reviewed(**changes):
    data = dict(id='synthetic-test-only', scale_denominator=100,
                status='reviewed',process='FDM', printer='test device, not a recommendation',
                material='test material', build_volume_mm=(200,200,200),
                minimum_feature_mm=.1,parameter_basis='Synthetic test thresholds only')
    data.update(changes)
    return PrintProfile(**data)


@pytest.mark.parametrize('size',[(1,2,3),(.02,.8,2),(.04,.04,.69)])
def test_box_positive_volume(size):
    mesh = mesh_for(box_at(size=size),{})
    assert mesh.is_volume
    assert mesh.volume == pytest.approx(np.prod(size))


def test_rotated_box_uses_true_corners():
    verts,_=box_mesh(box_at(size=(4,1,1),rotation=pi/2))
    assert np.ptp(verts,axis=0) == pytest.approx([1,4,1])


def test_i_section_cap_preserves_web_recesses():
    profiles={'i':dict(shape='i_section',depth_m=.6,width_m=.3,web_m=.02,flange_m=.03)}
    geometry=MemberGeometry(path=[v3(0,0,0),v3(3,0,0)],profile='i').model_dump()
    mesh=mesh_for(geometry,profiles)
    area=2*.3*.03+(.6-2*.03)*.02
    assert mesh.is_volume and mesh.volume == pytest.approx(area*3)


def test_parallel_roll_and_real_section_bounds():
    profiles={'p':dict(shape='rectangle',depth_m=.4,width_m=.2)}
    geometry=MemberGeometry(path=[v3(0,0,0),v3(3,0,0)],profile='p',roll=v3(1,0,0)).model_dump()
    mesh=mesh_for(geometry,profiles)
    assert mesh.is_volume and mesh.volume == pytest.approx(3*.4*.2)
    assert sorted(mesh.extents) == pytest.approx([.2,.4,3])


def test_extrusion_does_not_fill_architectural_opening():
    geometry=ExtrusionGeometry(boundary=[v2(0,0),v2(4,0),v2(4,4),v2(0,4)],
        holes=[[v2(1,1),v2(3,1),v2(3,3),v2(1,3)]], z_base=0,z_top=.3).model_dump()
    mesh=mesh_for(geometry,{})
    assert mesh.is_volume and mesh.volume == pytest.approx((16-4)*.3)
    # Every horizontal cap triangle is outside the opening, including at boundaries.
    from shapely.geometry import Polygon
    opening=Polygon([(1,1),(3,1),(3,3),(1,3)])
    for face in mesh.triangles:
        if np.ptp(face[:,2]) < 1e-9:
            assert Polygon(face[:,:2]).intersection(opening).area < 1e-9


@pytest.mark.parametrize('ring',[
    [(0,0),(2,2),(0,2),(2,0)], [(0,0),(1,0),(2,0)]])
def test_invalid_polygon_rejected_without_repair(ring):
    with pytest.raises(ValueError):
        mesh_for({'type':'extrusion','boundary':[{'x':x,'y':y} for x,y in ring],
                  'holes':[],'z_base':0,'z_top':1},{})


def test_quad_requires_real_declared_body():
    geometry={'type':'quad','corners':[v3(0,0,0).model_dump(),v3(1,0,0).model_dump(),
                                     v3(1,0,2).model_dump(),v3(0,0,2).model_dump()]}
    with pytest.raises(ValueError,match='thickness'):
        mesh_for(geometry,{})
    assert mesh_for(geometry,{},.1).volume == pytest.approx(.2)
    geometry['corners'][3]['y']=.2
    with pytest.raises(ValueError,match='Non-planar'):
        mesh_for(geometry,{},.1)


@pytest.mark.parametrize('changes',[
    {'id':'../escape'}, {'scale_denominator':0}, {'scale_denominator':float('nan')},
    {'source_unit':'mm'}, {'build_volume_mm':(200,-1,200)},
    {'status':'reviewed'}, {'build_volume_mm':(1,1,1),'edge_margin_mm':1}])
def test_invalid_or_unresolved_profile_cannot_be_reviewed(changes):
    with pytest.raises(ValidationError):
        PrintProfile(**(dict(id='planning',scale_denominator=100)|changes))


def test_plan_cannot_duplicate_or_silently_exclude_sources():
    with pytest.raises(ValidationError):
        PrintPlan(parts=[PrintPart(id='a',source_ids=['x']),PrintPart(id='b',source_ids=['x'])])
    with pytest.raises(ValidationError):
        PrintPlan(parts=[PrintPart(id='a',source_ids=['x'])],exclusions={'y':''})


def test_unknown_and_sectional_representations_are_not_full_models():
    model=model_of(box_at()); model.pop('lattice')
    assert level_plan(model).representation == 'unresolved'
    model['lattice']={'cutaway':True}
    assert level_plan(model).representation == 'sectional'


def test_production_promotion_is_blocked_before_optional_import(tmp_path):
    with pytest.raises(ValueError,match='Production release blocked'):
        export_print_package(model_of(box_at()),reviewed(),tmp_path/'release',release=True)
    assert not (tmp_path/'release').exists()


@pytest.fixture
def boolean_engine():
    pytest.importorskip('manifold3d',reason='optional fabrication dependency not installed')


def test_scale_union_reimport_and_inverse_transform(tmp_path,boolean_engine):
    model=model_of(box_at(),box_at(x=.5)); original=deepcopy(model)
    plan=PrintPlan(parts=[PrintPart(id='union',source_ids=['element-0','element-1'],rotation_deg=(0,0,90))])
    report=export_print_package(model,reviewed(),tmp_path/'package',plan)
    part=report['parts'][0]
    assert part['volume_mm3'] == pytest.approx(1500)
    assert part['extent_mm'] == pytest.approx([10,15,10])
    assert part['positive_shells']==1
    assert report['verification']['geometry_verified']=='passed'
    assert report['verification']['profile_screened']=='passed'
    assert report['verification']['slicer_verified']=='not_checked'
    assert report['verification']['physical_sample_verified']=='not_checked'
    assert report['release_ready'] is False and model==original
    forward=np.array(part['assembly_to_print_mm']); back=np.array(part['print_to_assembly_mm'])
    assert forward@back == pytest.approx(np.eye(4))
    assert json.loads((tmp_path/'package/print_manifest.json').read_text())['exporter_source']
    with pytest.raises(FileExistsError):
        export_print_package(model,reviewed(),tmp_path/'package',plan)


def test_disconnected_part_is_not_certified(tmp_path,boolean_engine):
    result=export_print_package(model_of(box_at(),box_at(x=4)),reviewed(),tmp_path/'loose')
    assert result['verification']['geometry_verified']=='failed'
    assert any(i['rule']=='PRINT-DISCONNECTED-PART' for i in result['parts'][0]['issues'])


def test_missing_profile_does_not_turn_green(tmp_path,boolean_engine):
    result=export_print_package(model_of(box_at()),PrintProfile(id='unknown',scale_denominator=100),tmp_path/'unknown')
    assert result['verification']['geometry_verified']=='passed'
    assert result['verification']['profile_screened']=='not_checked'
    assert result['source_blockers']


def test_feature_and_bed_failures_are_measured(tmp_path,boolean_engine):
    result=export_print_package(model_of(box_at(size=(4,1,.01))),
        reviewed(build_volume_mm=(20,20,20),minimum_feature_mm=.8),tmp_path/'too-thin')
    assert result['verification']['profile_screened']=='failed'
    assert {i['rule'] for i in result['parts'][0]['issues']} == {'PRINT-BED-OVERFLOW','PRINT-THIN-FEATURE'}


def test_bad_source_never_yields_a_partially_exported_part(tmp_path,boolean_engine):
    invalid=box_at(); invalid['size']['z']=0
    result=export_print_package(model_of(box_at(),invalid),reviewed(),tmp_path/'invalid')
    assert result['verification']['geometry_verified']=='failed'
    assert not list((tmp_path/'invalid').glob('*.stl'))


def test_missing_plan_coverage_and_unknown_ids_fail_before_output(tmp_path,boolean_engine):
    with pytest.raises(ValueError,match='coverage mismatch'):
        export_print_package(model_of(box_at(),box_at(x=4)),reviewed(),tmp_path/'missing',
            PrintPlan(parts=[PrintPart(id='incomplete',source_ids=['element-0'])]))
    assert not (tmp_path/'missing').exists()
