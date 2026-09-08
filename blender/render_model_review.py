"""Diagnostic views of a hash-bound native Blender model; never save the master.

Blender is imported only by ``render``. The view specification and input verification
are portable Python, so camera framing and version rejection are tested without bpy.
All cuts are uncapped bmesh cuts of the existing scene. Architectural voids are never
filled, and no geometry is recompiled or replaced with a diagnostic building model.

    blender --background --factory-startup --python-exit-code 1 \
      --python blender/render_model_review.py -- --model MODEL.json --blend MODEL.blend \
      --manifest MODEL.manifest.json --run-contract GENERATION_RESPONSE.json \
      --run-id RUN_ID --output NEW_DIRECTORY
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys


HASH_BASIS = 'canonical_json_sort_keys_utf8'
SCHEMA = 'mta.diagnostic_views/1.0'
RESOLUTION = (1100, 850)
HIDDEN_LAYERS = ('site',)
HIDDEN_SUBSYSTEMS = ('zones', 'scale_reference')


def canonical_model_sha256(model: dict) -> str:
    content = json.dumps(model, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hashlib.sha256(content).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_inputs(model_path: Path, blend_path: Path, manifest_path: Path,
                  run_id: str, run_contract_path: Path) -> tuple[dict, dict]:
    """Reject wrong scenes before opening Blender or creating an output directory."""
    model_path,blend_path,manifest_path = (Path(path).resolve() for path in
                                           (model_path,blend_path,manifest_path))
    if not run_id.strip():
        raise ValueError('A source run ID is required')
    model = json.loads(model_path.read_text(encoding='utf-8'))
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('model_id') != model.get('model_id'):
        raise ValueError('Manifest and model IDs differ')
    if manifest.get('source_hash_basis') != HASH_BASIS:
        raise ValueError('Manifest has no supported canonical source-model hash binding')
    model_hash = canonical_model_sha256(model)
    if manifest.get('source_model_sha256') != model_hash:
        raise ValueError('Source model content does not match the manifest hash')
    declared_blend = manifest.get('native_blend_path')
    if not declared_blend:
        raise ValueError('Manifest has no native Blender file pointer')
    pointed = Path(declared_blend)
    if not pointed.is_absolute():
        pointed = manifest_path.parent/pointed
    # Archived bundles relocate the same immutable bytes. Content identity, scene
    # metadata and the run contract remain authoritative; the original path is provenance.
    relocated = pointed.resolve() != blend_path
    blend_hash = sha256(blend_path)
    if manifest.get('native_blend_sha256') != blend_hash:
        raise ValueError('Native Blender file does not match the manifest hash')
    if manifest.get('run_id') and manifest['run_id'] != run_id:
        raise ValueError('Requested run ID differs from the manifest run ID')
    run_contract_path = Path(run_contract_path).resolve()
    contract = json.loads(run_contract_path.read_text(encoding='utf-8'))
    if contract.get('run_id') != run_id:
        raise ValueError('Requested run ID differs from the generation response contract')
    if (contract.get('analysis') or {}).get('model_id') != model['model_id']:
        raise ValueError('Generation response analysis belongs to another model')
    asset = contract.get('model_asset_v3') or {}
    expected = {'source_model_sha256':model_hash, 'native_blend_sha256':blend_hash,
                'manifest_sha256':sha256(manifest_path)}
    for field,digest in expected.items():
        if asset.get(field) != digest:
            raise ValueError(f'Generation response {field} does not match the verified source')
    return model, {
        'model_id':model['model_id'], 'score_id':model.get('score_id'), 'run_id':run_id,
        'run_id_basis':'generation_response_contract',
        'source_model_sha256':model_hash, 'source_hash_basis':HASH_BASIS,
        'model_file_sha256':sha256(model_path), 'native_blend_sha256':blend_hash,
        'manifest_sha256':sha256(manifest_path),
        'model_path':str(model_path), 'native_blend_path':str(blend_path),
        'original_native_blend_path':str(pointed), 'native_blend_relocated':relocated,
        'manifest_path':str(manifest_path),
        'run_contract_path':str(run_contract_path),
        'run_contract_sha256':sha256(run_contract_path),
    }


@dataclass(frozen=True)
class ClipPlane:
    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    label: str
    keep: str = 'negative_halfspace'


@dataclass(frozen=True)
class ViewSpec:
    id: str
    title: str
    kind: str
    level_id: str
    camera_location: tuple[float, float, float]
    camera_target: tuple[float, float, float]
    orthographic_scale: float
    bounds: tuple[float, float, float, float, float, float]
    planes: tuple[ClipPlane, ...]
    hidden_layers: tuple[str, ...] = HIDDEN_LAYERS
    hidden_subsystems: tuple[str, ...] = HIDDEN_SUBSYSTEMS
    focus_element_ids: tuple[str, ...] = ()
    resolution: tuple[int, int] = RESOLUTION
    samples: int = 64
    capped: bool = False
    authority: str = 'diagnostic_presentation_only'


def _point(value):
    return tuple(float(value[key]) for key in ('x','y','z'))


def _element_bounds(instance):
    """The compiler's derived bounds select focus candidates; bpy cuts actual faces."""
    center,size = _point(instance['position']),_point(instance['dimensions'])
    return (*[center[i]-size[i]/2 for i in range(3)],
            *[center[i]+size[i]/2 for i in range(3)])


def _box_planes(bounds):
    low,high = bounds[:3],bounds[3:]
    planes=[]
    for axis,name in enumerate(('x','y','z')):
        for sign,coordinate in ((-1,low[axis]),(1,high[axis])):
            point=[(low[i]+high[i])/2 for i in range(3)]
            point[axis]=coordinate
            normal=[0.,0.,0.]
            normal[axis]=float(sign)
            planes.append(ClipPlane(tuple(point),tuple(normal),f'{name}_{"min" if sign<0 else "max"}'))
    return tuple(planes)


def _camera(bounds, direction):
    target=tuple((bounds[i]+bounds[i+3])/2 for i in range(3))
    diagonal=math.sqrt(sum((bounds[i+3]-bounds[i])**2 for i in range(3)))
    length=math.sqrt(sum(v*v for v in direction))
    forward=tuple(v/length for v in direction)
    # Camera local right is horizontal; top views use world X as their right.
    right=(-forward[1],forward[0],0.)
    rlen=math.sqrt(sum(v*v for v in right))
    right=tuple(v/rlen for v in right) if rlen>1e-9 else (1.,0.,0.)
    up=(forward[1]*right[2]-forward[2]*right[1],
        forward[2]*right[0]-forward[0]*right[2],
        forward[0]*right[1]-forward[1]*right[0])
    extent=[bounds[i+3]-bounds[i] for i in range(3)]
    width=sum(abs(right[i])*extent[i] for i in range(3))
    height=sum(abs(up[i])*extent[i] for i in range(3))
    scale=max(width,height*RESOLUTION[0]/RESOLUTION[1])*1.16
    return tuple(target[i]+forward[i]*diagonal*1.8 for i in range(3)),target,scale


def _spec(identifier,title,kind,level,bounds,direction,focus=()):
    if any(not math.isfinite(value) for value in bounds) or any(bounds[i+3]<=bounds[i] for i in range(3)):
        raise ValueError(f'{identifier}: finite non-empty view bounds required')
    location,target,scale=_camera(bounds,direction)
    return ViewSpec(identifier,title,kind,level,location,target,scale,tuple(bounds),
                    _box_planes(bounds),focus_element_ids=tuple(sorted(set(focus))))


def build_view_specs(model: dict, *, max_portals: int = 4) -> list[ViewSpec]:
    """All occupied floors plus a theatre overview/detail and worst portal contexts."""
    if model.get('units','meters')!='meters' or model.get('coordinate_system','right_handed_z_up')!='right_handed_z_up':
        raise ValueError('Review views require the native metre / Z-up coordinate contract')
    levels=sorted(model['lattice']['levels'],key=lambda level:level['z'])
    occupied=[level for level in levels if level['kind']=='occupied']
    if not occupied:
        raise ValueError('No occupied levels to review')
    all_gaps=[b['z']-a['z'] for a,b in zip(levels,levels[1:]) if b['z']>a['z']]
    if not all_gaps:
        raise ValueError('A storey height is required to derive review slices')
    floor_scale={}
    views=[]
    for index,level in enumerate(occupied):
        above=next((item['z'] for item in levels if item['z']>level['z']),None)
        height=above-level['z'] if above is not None else min(all_gaps)
        floor_scale[level['id']]=height
        xs=[p['x'] for p in level['plate']]
        ys=[p['y'] for p in level['plate']]
        bounds=(min(xs)-height*.04,min(ys)-height*.04,level['z']-height*.08,
                max(xs)+height*.04,max(ys)+height*.04,level['z']+height*.4)
        views.append(_spec(f'floor_{index+1:02d}_{level["id"]}',level['id']+' floor slice',
                           'occupied_floor_slice',level['id'],bounds,(0.,0.,1.)))
    records={item['id']:(group,item) for group in model['element_groups'] for item in group['instances']}
    zones=model.get('program_allocation',{}).get('zones',[])
    for zone in zones:
        if zone['space_type']!='auditorium':
            continue
        level=next(level for level in occupied if level['id']==zone['level_id'])
        h=floor_scale[level['id']]
        seats=[item for group,item in records.values() if group['kind']=='seat'
               and group.get('program')=='auditorium' and item['level_id']==level['id']]
        top=max((_element_bounds(item)[5] for item in seats),default=level['z']+h)
        margin=h*.06
        bounds=(zone['x0']-margin,zone['y0']-margin,level['z']-h*.06,
                zone['x1']+margin,zone['y1']+margin,top+h*.16)
        stage=next((z for z in zones if z['space_type']=='stage' and z['level_id']==level['id']),None)
        direction=1 if stage and stage['x0']>zone['x0'] else -1
        views.append(_spec('theatre_overview','Theatre overview','theatre_overview',
            level['id'],bounds,(direction*.2,-.15,1.),[item['id'] for item in seats]))
        reservations=model.get('room_layout_plan',{}).get('reservations',[]) if model.get('room_layout_plan') else []
        aisles=[r for r in reservations if r['space_id']==zone['space_id']
                and r['purpose']=='longitudinal_aisle']
        if aisles:
            # Middle-height aisle keeps the detail on actual stairs, independent of
            # a fixed world camera or a particular song's house orientation.
            by_height=sorted(aisles,key=lambda r:(r['floor_z_m'],r['id']))
            focus=by_height[len(by_height)//2]
            x=sum(p[0] for p in focus['polygon'])/len(focus['polygon'])
            y=sum(p[1] for p in focus['polygon'])/len(focus['polygon'])
            z=focus['floor_z_m']
            extent=h*.9
            detail=(x-extent,y-extent,z-h*.36,x+extent,y+extent,z+h*.5)
            views.append(_spec('theatre_aisle_detail','Seats and aisle','theatre_aisle_detail',
                level['id'],detail,(direction*.7,-.9,1.2)))
    # Read each actual service-room footprint; a whole-floor view cannot resolve
    # fixture parts, door approaches, or the floor around plant equipment.
    service_types={'public_restroom','staff_restroom','mechanical','plant','electrical_it'}
    for zone in zones:
        if zone['space_type'] not in service_types:
            continue
        level=next(level for level in occupied if level['id']==zone['level_id'])
        h=floor_scale[level['id']]
        margin=h*.08
        bounds=(zone['x0']-margin,zone['y0']-margin,level['z']-h*.08,
                zone['x1']+margin,zone['y1']+margin,level['z']+h*.55)
        focus=[item['id'] for group,item in records.values()
               if group.get('subsystem')=='room_fixtures' and item['level_id']==level['id']
               and zone['x0']<=item['position']['x']<=zone['x1']
               and zone['y0']<=item['position']['y']<=zone['y1']]
        suffix=hashlib.sha256(zone['space_id'].encode()).hexdigest()[:8]
        views.append(_spec('service_'+suffix,zone['space_type'].replace('_',' '),
                           'service_room_detail',level['id'],bounds,(.25,-.3,1.4),focus))
    portals=(model.get('portals') or {}).get('portals',[])
    def priority(portal):
        sides=(portal.get('side_a',{}),portal.get('side_b',{}))
        return (bool(portal.get('passable')), -len(portal.get('reasons',[])),
                -sum(len(side.get('clash_ids',[])) for side in sides),
                -sum(side.get('unsupported_m2',0.) for side in sides),portal['id'])
    for index,portal in enumerate(sorted(portals,key=priority)[:max(0,max_portals)]):
        points=[*portal['aperture'],*portal['side_a']['region'],*portal['side_b']['region']]
        xs,ys=[p[0] for p in points],[p[1] for p in points]
        h=portal['height_m']
        margin=h*.4
        bounds=(min(xs)-margin,min(ys)-margin,portal['floor_z']-h*.2,
                max(xs)+margin,max(ys)+margin,portal['floor_z']+h*1.08)
        normal=portal['normal']
        tangent=portal['tangent']
        direction=(normal[0]+tangent[0]*.6,normal[1]+tangent[1]*.6,1.3)
        focus=[*portal['door_ids'],*portal.get('host_wall_ids',[]),
               *portal['side_a'].get('clash_ids',[]),*portal['side_b'].get('clash_ids',[])]
        suffix=hashlib.sha256(portal['id'].encode()).hexdigest()[:8]
        views.append(_spec(f'portal_{index+1:02d}_{suffix}',f'Portal {index+1} / {portal["kind"]}',
            'portal_closeup',portal['level_id'],bounds,direction,focus))
        if portal['kind']=='entrance':
            # This separate diagnostic exposes the two platforms and real aperture.
            # The closed-door view and immutable native file retain every door leaf.
            views.append(replace(views[-1],id=views[-1].id+'_aperture',
                title=f'Entrance {index+1} / leaves hidden',kind='entrance_aperture_detail',
                hidden_subsystems=(*views[-1].hidden_subsystems,'entrance')))
    if len({view.id for view in views})!=len(views):
        raise ValueError('Review view identities are not unique')
    return views


def source_candidates(model, spec):
    """Conservative AABB candidates, labelled separately from visible merged objects."""
    groups,ids=[],[]
    for group in model['element_groups']:
        if group['semantic_layer'] in spec.hidden_layers or group['subsystem'] in spec.hidden_subsystems:
            continue
        matching=[]
        for item in group['instances']:
            bounds=_element_bounds(item)
            if all(bounds[i+3]>=spec.bounds[i] and bounds[i]<=spec.bounds[i+3] for i in range(3)):
                matching.append(item['id'])
        if matching:
            groups.append(group['group_id'])
            ids.extend(matching)
    return {'intersecting_source_group_ids':sorted(groups),'candidate_source_element_ids':sorted(ids),
            'element_visibility_basis':'Conservative source AABB intersection; merged scene meshes do not carry per-face element IDs.'}


def _clip_mesh(obj, planes, tolerance):
    import bmesh
    from mathutils import Matrix, Vector
    bm=bmesh.new()
    try:
        bm.from_mesh(obj.data)
        before=len(bm.faces)
        bm.transform(obj.matrix_world)
        cut_edges=0
        for plane in planes:
            if not bm.faces:
                break
            cut=bmesh.ops.bisect_plane(bm,geom=[*bm.verts,*bm.edges,*bm.faces],
                dist=tolerance,plane_co=Vector(plane.point),plane_no=Vector(plane.normal),
                clear_outer=True,clear_inner=False)
            cut_edges+=sum(isinstance(item,bmesh.types.BMEdge) for item in cut['geom_cut'])
        bm.normal_update()
        after=len(bm.faces)
        bm.to_mesh(obj.data)
        obj.data.update()
        obj.matrix_world=Matrix.Identity(4)
        obj.hide_render=after==0
        return {'faces_before':before,'faces_after':after,'intersection_edge_count':cut_edges,
                'caps_added':0}
    finally:
        bm.free()


def _scene_setup(bpy, spec):
    from mathutils import Vector
    scene=bpy.context.scene
    engines={item.identifier for item in scene.render.bl_rna.properties['engine'].enum_items}
    scene.render.engine='BLENDER_EEVEE' if 'BLENDER_EEVEE' in engines else 'BLENDER_EEVEE_NEXT'
    scene.render.resolution_x,scene.render.resolution_y=spec.resolution
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.render.film_transparent=False
    if hasattr(scene,'eevee') and hasattr(scene.eevee,'taa_render_samples'):
        scene.eevee.taa_render_samples=spec.samples
    camera=scene.camera
    if camera is None:
        camera=bpy.data.objects.new('DiagnosticCamera',bpy.data.cameras.new('DiagnosticCamera'))
        scene.collection.objects.link(camera)
        scene.camera=camera
    camera.location=spec.camera_location
    camera.rotation_euler=(Vector(spec.camera_target)-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO'
    camera.data.ortho_scale=spec.orthographic_scale
    camera.data.clip_start=spec.orthographic_scale*.001
    camera.data.clip_end=spec.orthographic_scale*12
    # Retain the imported materials/world/sun. Reposition the existing fill light
    # with the view so a translated model receives the same diagnostic illumination.
    lights=[]
    for obj in scene.objects:
        if obj.type=='LIGHT' and obj.data.type=='AREA':
            scale=spec.orthographic_scale
            obj.location=Vector(spec.camera_target)+Vector((-scale,-scale,scale*1.5))
            obj.rotation_euler=(Vector(spec.camera_target)-obj.location).to_track_quat('-Z','Y').to_euler()
            obj.data.size=scale
            obj.data.energy=scale*scale*8
            lights.append({'name':obj.name,'location':list(obj.location),
                           'size':obj.data.size,'energy':obj.data.energy})
    return camera,lights


def _caption(bpy,camera,spec,model_id):
    from mathutils import Vector
    curve=bpy.data.curves.new('DiagnosticCaption','FONT')
    curve.body=f'{spec.title} | {model_id} | diagnostic / uncapped'
    curve.size=spec.orthographic_scale*.014
    obj=bpy.data.objects.new('DiagnosticCaption',curve)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    aspect=spec.resolution[0]/spec.resolution[1]
    obj.location=camera.matrix_world@Vector((-spec.orthographic_scale*.47,
        spec.orthographic_scale/aspect*.46,-spec.orthographic_scale*.1))
    obj.rotation_euler=camera.rotation_euler
    material=bpy.data.materials.new('DiagnosticCaptionInk')
    material.use_nodes=True
    nodes=material.node_tree.nodes
    nodes.clear()
    emission=nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value=(.025,.025,.025,1)
    output=nodes.new('ShaderNodeOutputMaterial')
    material.node_tree.links.new(emission.outputs[0],output.inputs[0])
    curve.materials.append(material)


def render(model_path,blend_path,manifest_path,run_id,run_contract_path,output,max_portals=4):
    import bpy
    model,source=verify_inputs(model_path,blend_path,manifest_path,run_id,run_contract_path)
    views=build_view_specs(model,max_portals=max_portals)
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    evidence={'schema_version':SCHEMA,'authority':'diagnostic_presentation_only',
        'created_at':datetime.now(timezone.utc).isoformat(),'source':source,
        'source_master_saved':False,'cut_method':'bmesh_plane_bisect_uncapped',
        'visibility_scope':'retained geometry, not pixel-level occlusion visibility',
        'renderer_script_sha256':sha256(Path(__file__)),'views':[],'status':'running'}
    def record():
        path=output/'views_manifest.json'
        path.write_text(json.dumps(evidence,indent=2,ensure_ascii=False),encoding='utf-8')
    record()
    try:
        for spec in views:
            # Reopen for every view: a previous view's cut can never leak into this one.
            bpy.ops.wm.open_mainfile(filepath=source['native_blend_path'])
            scene=bpy.context.scene
            if scene.get('mta:model_id')!=source['model_id'] or scene.get('mta:source_model_sha256')!=source['source_model_sha256']:
                raise ValueError('Opened scene identity does not match the verified source model')
            root=bpy.data.collections.get('MTA_v3')
            if root is None:
                raise ValueError('Verified source has no MTA_v3 collection')
            for collection in [root,*root.children_recursive]:
                collection.hide_render=False
            stats={}
            hidden=[]
            for obj in list(root.all_objects):
                if obj.type!='MESH':
                    continue
                if obj.get('mta:model_id')!=source['model_id']:
                    raise ValueError(f'{obj.name}: mixed model identity inside source collection')
                if obj.get('mta:layer') in spec.hidden_layers or obj.get('mta:subsystem') in spec.hidden_subsystems:
                    obj.hide_render=True
                    hidden.append(obj.name)
                    continue
                # Mesh datablocks may be shared in a native file; copy only in memory.
                obj.data=obj.data.copy()
                stats[obj.name]=_clip_mesh(obj,spec.planes,spec.orthographic_scale*1e-8)
            camera,lights=_scene_setup(bpy,spec)
            _caption(bpy,camera,spec,source['model_id'])
            png=output/(spec.id+'.png')
            scene.render.filepath=str(png)
            bpy.ops.render.render(write_still=True)
            evidence['views'].append({**asdict(spec),'source':source,
                'image':png.name,'image_sha256':sha256(png),
                'visible_object_names':sorted(name for name,stat in stats.items() if stat['faces_after']),
                'hidden_object_names':sorted(hidden), 'mesh_cuts':stats,
                'light_overrides':lights, **source_candidates(model,spec),
                'visual_judgment_status':'pending_human_or_vision_review'})
            record()
        # File changes during rendering invalidate the entire evidence set.
        _,after=verify_inputs(model_path,blend_path,manifest_path,run_id,run_contract_path)
        if source!=after:
            raise ValueError('Source inputs changed during diagnostic rendering')
        evidence['status']='rendered_pending_visual_review'
    except Exception as error:
        evidence['status']='failed'
        evidence['error']=f'{type(error).__name__}: {error}'
        record()
        raise
    record()
    return evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('model','blend','manifest','run-contract','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--max-portals',type=int,default=4)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:])
    result=render(args.model,args.blend,args.manifest,args.run_id,args.run_contract,
                  args.output,args.max_portals)
    print(json.dumps({'status':result['status'],'views':len(result['views']),
                      'manifest':str(args.output/'views_manifest.json')}))


if __name__=='__main__':
    main()
