"""Portable evidence-view and source-binding tests; no Blender import required."""
from copy import deepcopy
import json

import pytest

from blender.render_model_review import (
    HASH_BASIS, build_view_specs, canonical_model_sha256, sha256,
    source_candidates, verify_inputs,
)


def sample_model():
    def element(identifier,x,y,z,kind='seat',subsystem='room_fixtures'):
        return {'group_id':'G-'+identifier,'kind':kind,'semantic_layer':'program',
            'subsystem':subsystem,'program':'auditorium','category':'public',
            'material_profile':'furn','instances':[{'id':identifier,'level_id':'L01',
                'position':{'x':x,'y':y,'z':z},'dimensions':{'x':.5,'y':.5,'z':.8}}]}
    def portal(identifier,passable):
        return {'id':identifier,'kind':'room','level_id':'L01','door_ids':[identifier],
            'host_wall_ids':['WALL'],'center':[4,0],'normal':[0,1],'tangent':[1,0],
            'aperture':[[3.5,-.1],[4.5,-.1],[4.5,.1],[3.5,.1]],
            'floor_z':0.,'width_m':1.,'height_m':2.1,'wall_depth_m':.2,
            'side_a':{'region':[[3.4,.1],[4.6,.1],[4.6,1.3],[3.4,1.3]],
                      'clash_ids':[] if passable else ['BLOCKER'],'unsupported_m2':0},
            'side_b':{'region':[[3.4,-1.3],[4.6,-1.3],[4.6,-.1],[3.4,-.1]],
                      'clash_ids':[],'unsupported_m2':0},
            'reasons':[] if passable else ['PORTAL-APPROACH-BLOCKED'],'passable':passable}
    return {'model_id':'building-v3-review-test','score_id':'score-test','units':'meters',
        'coordinate_system':'right_handed_z_up',
        'lattice':{'levels':[{'id':name,'index':i,'z':z,'kind':kind,
            'plate':[{'x':x,'y':y} for x,y in ((0,0),(12,0),(12,10),(0,10))],'voids':[]}
            for i,(name,z,kind) in enumerate((('L01',0.,'occupied'),('L02',4.,'occupied'),('RF',8.,'roof')))]},
        'program_allocation':{'zones':[
            {'space_id':'HOUSE','space_type':'auditorium','level_id':'L01','x0':1.,'y0':1.,'x1':10.,'y1':9.},
            {'space_id':'STAGE','space_type':'stage','level_id':'L01','x0':10.,'y0':1.,'x1':12.,'y1':9.}]},
        'element_groups':[element('CHAIR',6,5,.8),element('ZONE',6,5,.05,'program_zone','zones')],
        'portals':{'portals':[portal('GOOD-DOOR',True),portal('BAD-DOOR',False)]},
        'room_layout_plan':{'reservations':[{'id':'AISLE','space_id':'HOUSE',
            'purpose':'longitudinal_aisle','floor_z_m':.4,'polygon':[[3,4],[4,4],[4,5],[3,5]]}]} }


def transformed(model,scale,offset):
    model=deepcopy(model)
    def xy(points):
        return [[p[0]*scale+offset[0],p[1]*scale+offset[1]] for p in points]
    for level in model['lattice']['levels']:
        level['z']=level['z']*scale+offset[2]
        for point in level['plate']:
            point['x']=point['x']*scale+offset[0]
            point['y']=point['y']*scale+offset[1]
    for zone in model['program_allocation']['zones']:
        for axis,index in (('x',0),('y',1)):
            for side in ('0','1'):
                zone[axis+side]=zone[axis+side]*scale+offset[index]
    for group in model['element_groups']:
        for item in group['instances']:
            for index,axis in enumerate(('x','y','z')):
                item['position'][axis]=item['position'][axis]*scale+offset[index]
                item['dimensions'][axis]*=scale
    for portal in model['portals']['portals']:
        portal['center']=xy([portal['center']])[0]
        portal['aperture']=xy(portal['aperture'])
        portal['floor_z']=portal['floor_z']*scale+offset[2]
        for name in ('width_m','height_m','wall_depth_m'):
            portal[name]*=scale
        for name in ('side_a','side_b'):
            portal[name]['region']=xy(portal[name]['region'])
    for reservation in model['room_layout_plan']['reservations']:
        reservation['polygon']=xy(reservation['polygon'])
        reservation['floor_z_m']=reservation['floor_z_m']*scale+offset[2]
    return model


def test_all_occupied_levels_and_theatre_views_come_from_the_model():
    views=build_view_specs(sample_model())
    assert [v.level_id for v in views if v.kind=='occupied_floor_slice']==['L01','L02']
    assert {v.kind for v in views}>={'theatre_overview','theatre_aisle_detail','portal_closeup'}
    assert all(v.capped is False for v in views)
    assert all(v.resolution==(1100,850) and v.samples==64 for v in views)
    assert all(v.authority=='diagnostic_presentation_only' for v in views)


@pytest.mark.parametrize('scale,offset',[(1.,(1020.,-770.,80.)),(2.5,(-240.,560.,-13.))])
def test_every_camera_and_cut_follows_translated_scaled_model(scale,offset):
    original=build_view_specs(sample_model())
    shifted=build_view_specs(transformed(sample_model(),scale,offset))
    assert [v.id for v in original]==[v.id for v in shifted]
    for a,b in zip(original,shifted):
        assert b.orthographic_scale==pytest.approx(a.orthographic_scale*scale)
        assert b.camera_location==pytest.approx([a.camera_location[i]*scale+offset[i] for i in range(3)])
        assert b.camera_target==pytest.approx([a.camera_target[i]*scale+offset[i] for i in range(3)])
        for p,q in zip(a.planes,b.planes):
            assert q.point==pytest.approx([p.point[i]*scale+offset[i] for i in range(3)])
            assert q.normal==p.normal


def test_worst_portal_gets_first_closeup_and_context_contains_both_sides():
    view=next(v for v in build_view_specs(sample_model(),max_portals=1) if v.kind=='portal_closeup')
    assert 'BAD-DOOR' in view.focus_element_ids
    assert 'BLOCKER' in view.focus_element_ids
    assert view.bounds[1]<-1.3 and view.bounds[4]>1.3
    assert view.bounds[2]<0 and view.bounds[5]>2.1


def test_source_candidate_ids_are_not_mislabeled_as_pixel_visibility():
    model=sample_model()
    result=source_candidates(model,build_view_specs(model)[0])
    assert result['candidate_source_element_ids']==['CHAIR']
    assert result['intersecting_source_group_ids']==['G-CHAIR']
    assert 'per-face' in result['element_visibility_basis']
    assert 'visible_element_ids' not in result


def source_files(tmp_path):
    model=sample_model()
    model['note']='测量模型'
    path=tmp_path/'model.json'
    path.write_text(json.dumps(model,indent=2,ensure_ascii=False),encoding='utf-8')
    blend=tmp_path/'model.blend'
    blend.write_bytes(b'BLENDER-source-test')
    manifest=tmp_path/'model.manifest.json'
    data={'model_id':model['model_id'],'source_hash_basis':HASH_BASIS,
        'source_model_sha256':canonical_model_sha256(model),
        'native_blend_path':str(blend),'native_blend_sha256':sha256(blend),'run_id':'run-test'}
    manifest.write_text(json.dumps(data),encoding='utf-8')
    contract=tmp_path/'generation_response.json'
    contract.write_text(json.dumps({'run_id':'run-test','analysis':{'model_id':model['model_id']},
        'model_asset_v3':{'source_model_sha256':data['source_model_sha256'],
            'native_blend_sha256':data['native_blend_sha256'],
            'manifest_sha256':sha256(manifest)}}),encoding='utf-8')
    return model,path,blend,manifest,data,contract


def test_canonical_model_binding_accepts_whitespace_changes_but_records_file_hash(tmp_path):
    model,path,blend,manifest,_,contract=source_files(tmp_path)
    _,first=verify_inputs(path,blend,manifest,'run-test',contract)
    path.write_text(json.dumps(model,sort_keys=True,ensure_ascii=True),encoding='utf-8')
    _,second=verify_inputs(path,blend,manifest,'run-test',contract)
    assert first['source_model_sha256']==second['source_model_sha256']
    assert first['model_file_sha256']!=second['model_file_sha256']


def test_archived_native_scene_can_move_without_changing_identity(tmp_path):
    _,path,blend,manifest,_,contract=source_files(tmp_path)
    archived=tmp_path/'archive'/'scene_v3.blend'
    archived.parent.mkdir()
    archived.write_bytes(blend.read_bytes())
    _,source=verify_inputs(path,archived,manifest,'run-test',contract)
    assert source['native_blend_relocated'] is True
    assert source['original_native_blend_path']==str(blend)
    archived.write_bytes(b'older native model')
    with pytest.raises(ValueError,match='Blender file does not match'):
        verify_inputs(path,archived,manifest,'run-test',contract)


@pytest.mark.parametrize('change,message',[
    ('model_id','IDs differ'),('model_content','model content'),('blend_bytes','Blender file does not match'),
    ('blend_pointer','manifest_sha256 does not match'),('unbound','no supported canonical'),
    ('run','run ID differs'),
])
def test_source_mismatches_refuse_evidence_generation(tmp_path,change,message):
    model,path,blend,manifest,data,contract=source_files(tmp_path)
    run='run-test'
    if change=='model_id': data['model_id']='old-model'
    elif change=='model_content':
        model['element_groups'][0]['instances'][0]['position']['x']+=.1
        path.write_text(json.dumps(model),encoding='utf-8')
    elif change=='blend_bytes': blend.write_bytes(b'old scene bytes')
    elif change=='blend_pointer': data['native_blend_path']=str(tmp_path/'old.blend')
    elif change=='unbound': del data['source_hash_basis']
    elif change=='run': run='other-run'
    manifest.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError,match=message):
        verify_inputs(path,blend,manifest,run,contract)


@pytest.mark.parametrize('change,message',[
    ('run_id','run ID differs from the generation response'),
    ('analysis','analysis belongs to another model'),
    ('source_model_sha256','source_model_sha256 does not match'),
    ('native_blend_sha256','native_blend_sha256 does not match'),
    ('manifest_sha256','manifest_sha256 does not match'),
])
def test_old_run_contract_cannot_relabel_current_scene(tmp_path,change,message):
    _,path,blend,manifest,_,contract=source_files(tmp_path)
    data=json.loads(contract.read_text(encoding='utf-8'))
    if change=='run_id':
        data['run_id']='older-run'
    elif change=='analysis':
        data['analysis']['model_id']='older-model'
    else:
        data['model_asset_v3'][change]='0'*64
    contract.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError,match=message):
        verify_inputs(path,blend,manifest,'run-test',contract)


def test_success_records_generation_contract_identity_and_file_hash(tmp_path):
    _,path,blend,manifest,_,contract=source_files(tmp_path)
    _,source=verify_inputs(path,blend,manifest,'run-test',contract)
    assert source['run_id_basis']=='generation_response_contract'
    assert source['run_contract_sha256']==sha256(contract)
    assert source['run_contract_path']==str(contract.resolve())


def test_model_without_a_floor_or_storey_scale_cannot_get_invented_cameras():
    model=sample_model()
    model['lattice']['levels']=[]
    with pytest.raises(ValueError,match='No occupied levels'):
        build_view_specs(model)
    model=sample_model()
    model['lattice']['levels']=model['lattice']['levels'][:1]
    with pytest.raises(ValueError,match='storey height'):
        build_view_specs(model)
