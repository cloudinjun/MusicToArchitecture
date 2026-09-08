"""Save the bounded site-to-volume preflight before any costly native export."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from time import perf_counter

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from shapely.geometry import Polygon

from backend.app.datums import compile_datum_set
from backend.app.models import ArchitecturalScore
from backend.app.project_brief import ProjectBrief
from backend.app.legacy_program_layout import LegacyLayoutControls, LayoutRejected
from backend.app.program_volumes import organize_program_volumes
from backend.app.version import compiler_source_fingerprint
from backend.app.world_xy_grid import GridBounds, ProgramVolumeLevelFootprint, plan_world_xy_columns


COLORS = {'public': '#3e5ce0', 'private': '#d64238', 'service': '#d64238',
          'circulation': '#42bd4b'}


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def preview(output, brief, rectangles, levels, column_plan, status):
    fig, axes = plt.subplots(1, brief.occupied_storeys, figsize=(16,5), squeeze=False)
    for k, ax in enumerate(axes[0]):
        for shape, color, ls in ((brief.site.shape,'#333','-'),
                                  (brief.buildable_shape,'#888','--'),
                                  (brief.massing_limit_shape,'#111',':')):
            parts = [shape] if shape.geom_type=='Polygon' else list(shape.geoms)
            for part in parts:
                ax.plot(*part.exterior.xy, color=color, linestyle=ls, linewidth=.8)
        for rect in rectangles:
            if rect['level'] != k:
                continue
            x0,y0,x1,y1=rect['rect']
            ax.add_patch(plt.Rectangle((x0,y0),x1-x0,y1-y0,
                facecolor=COLORS[rect['category']],alpha=.3 if rect['role']=='sectional_clearance' else .65,
                edgecolor='white',linewidth=.5))
            if rect['spaces']:
                ax.text((x0+x1)/2,(y0+y1)/2,rect['spaces'][0].replace('SP-',''),
                        fontsize=5,ha='center',va='center')
        if column_plan:
            for node in column_plan.candidates:
                if node.floor_id != f'L{k+1:02d}':
                    continue
                ax.plot(*node.point_xy, 'x' if node.support_status=='transfer_required' else 'o',
                        color='#171717', markersize=2)
        ax.set(title=f'L{k+1:02d}',aspect='equal',xlabel='m')
    fig.suptitle(f'{brief.site.area_m2:g} m² site — {status}',fontsize=12)
    fig.tight_layout()
    fig.savefig(output/'site_volume_plan.png',dpi=180)
    plt.close(fig)
    fig=plt.figure(figsize=(8,8)); ax=fig.add_subplot(111,projection='3d')
    for rect in rectangles:
        x0,y0,x1,y1=rect['rect']; z0,z1=levels[rect['level']]
        corners=[(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
                 (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
        faces=[[corners[i] for i in face] for face in
               ((0,1,2,3),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))]
        ax.add_collection3d(Poly3DCollection(faces,facecolors=COLORS[rect['category']],
            edgecolors='#333333',linewidths=.25,alpha=.15 if rect['role']=='sectional_clearance' else .65))
    x0,y0,x1,y1=brief.site.shape.bounds
    ax.set(xlim=(x0,x1),ylim=(y0,y1),zlim=(0,levels[-1][1]))
    ax.set_box_aspect((x1-x0,y1-y0,levels[-1][1])); ax.view_init(elev=22,azim=-60)
    ax.set_title('Program Volumes — '+status,fontsize=11)
    fig.tight_layout(); fig.savefig(output/'program_volumes.png',dpi=180); plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--brief',type=Path,required=True)
    parser.add_argument('--score',type=Path,required=True)
    parser.add_argument('--input-patch',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--compile',action='store_true',
                        help='Run the actual public building compiler after volume preflight; no native export')
    parser.add_argument('--spatial',action='store_true',
                        help='Run shared room/core/circulation preparation without detailed members')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    raw=json.loads(args.brief.read_text(encoding='utf-8'))
    patch=json.loads(args.input_patch.read_text(encoding='utf-8'))
    if patch.get('site_source'):
        raw['site']=json.loads(Path(patch['site_source']).read_text(encoding='utf-8'))['site']
    raw.update(patch['brief_overrides'])
    raw['assumptions']+=patch['reasons']
    raw['provenance']['normalizer_version']='small-site-test-premises/1.0'
    raw['provenance']['source_ref']=(raw['provenance'].get('source_ref') or str(args.brief.resolve()))+'; candidate premises: '+str(args.input_patch.resolve())
    brief=ProjectBrief.model_validate(raw)
    score=ArchitecturalScore.model_validate_json(args.score.read_text(encoding='utf-8'))
    controls=LegacyLayoutControls.model_validate(patch.get('controls',{}))
    write(args.output/'project_brief.json',brief.model_dump(mode='json'))
    write(args.output/'site_envelopes.json',brief.report())
    datums=compile_datum_set(score)
    started=perf_counter(); columns=None
    source_fingerprint=compiler_source_fingerprint()
    try:
        volumes=organize_program_volumes(score,brief.typology,project_brief=brief,legacy_controls=controls)
        # Exercise the real massing boundary, including site and floor-budget gates.
        massing=volumes.to_program_massing()
        from backend.app.program_massing import lattice_for, datums_for
        lattice_for(massing,datums_for(massing,score))
        rectangles=[{'id':v.id,'level':v.level_index-1,'category':v.category,'role':v.role,
                     'spaces':v.space_ids,'rect':volumes.rect_of(v)} for v in volumes.volumes]
        columns=plan_world_xy_columns(
            volumes.world_xy_grid,
            [ProgramVolumeLevelFootprint(u.level_id,Polygon(u.boundary,holes=u.voids),u.level_index)
             for u in volumes.level_unions],GridBounds(*brief.site.shape.bounds))
        write(args.output/'program_volumes.json',volumes.model_dump(mode='json'))
        write(args.output/'program_massing.json',massing.model_dump(mode='json'))
        write(args.output/'world_xy_column_candidates.json',asdict(columns))
        status='volume_preflight_passed'; findings=[]
    except LayoutRejected as exc:
        status='volume_preflight_failed'; findings=exc.findings; rectangles=exc.rectangles
    if source_fingerprint != compiler_source_fingerprint():
        raise RuntimeError('Compiler source changed during the preflight')
    write(args.output/'rectangles.json',rectangles)
    levels=[(controls.entry_elevation_m+k*datums.value('floor_to_floor_m'),
             controls.entry_elevation_m+(k+1)*datums.value('floor_to_floor_m'))
            for k in range(brief.occupied_storeys)]
    preview(args.output,brief,rectangles,levels,columns,status)
    evidence={'status':status,'findings':findings,'elapsed_seconds':round(perf_counter()-started,2),
              'compiler_source_fingerprint':source_fingerprint,'source_unchanged':True,
              'brief_source_sha256':hashlib.sha256(args.brief.read_bytes()).hexdigest(),
              'input_patch_sha256':hashlib.sha256(args.input_patch.read_bytes()).hexdigest(),
              'legacy_source_sha256':hashlib.sha256(Path('backend/legacy/EllipseAgent.py').read_bytes()).hexdigest(),
              'site_area_m2':brief.site.area_m2,'massing_limit_area_m2':brief.massing_limit_shape.area,
              'rectangles':len(rectangles),'world_xy_candidate_count':len(columns.candidates) if columns else 0,
              'native_export':'not_run','member_level_world_grid':'not_evaluated_in_form_preflight',
              'authority':'Form preflight only; circulation, structure, facade and final model remain unchecked.'}
    write(args.output/'result.json',evidence); print(json.dumps(evidence))
    spatial_ready = False
    if (args.spatial or args.compile) and status == 'volume_preflight_passed':
        from backend.app.program_massing import prepare_massing
        started = perf_counter()
        try:
            prepared = prepare_massing(massing, score=score)
            allocation = prepared.allocation
            unresolved = (allocation.public_circulation.unresolved
                          if allocation.public_circulation else {'network': 'not evaluated'})
            spatial_ready = allocation.fits and not unresolved
            spatial_result = {
                'status': 'spatial_preflight_passed' if spatial_ready else 'spatial_preflight_failed',
                'required_area_m2': allocation.required_area_m2,
                'delivered_area_m2': allocation.delivered_area_m2,
                'unplaced': [item.model_dump(mode='json') for item in allocation.unplaced],
                'short': [item.space_id for item in allocation.short],
                'circulation_unresolved': unresolved,
                'allocation': allocation.model_dump(mode='json'),
                'authority': 'Shared spatial stage only; physical members and final coordination unchecked.'}
        except ValueError as exc:
            spatial_result = {'status': 'spatial_preflight_failed', 'error': str(exc)}
        if source_fingerprint != compiler_source_fingerprint():
            raise RuntimeError('Compiler source changed during spatial preparation')
        spatial_result.update(seconds=round(perf_counter()-started, 2),
                              compiler_source_fingerprint=source_fingerprint,
                              source_unchanged=True)
        write(args.output/'spatial_result.json', spatial_result)
        print(json.dumps({k: v for k, v in spatial_result.items() if k != 'allocation'}, ensure_ascii=False))
    if args.compile and status == 'volume_preflight_passed' and not spatial_ready:
        write(args.output/'building_result.json', {
            'status': 'building_compile_not_run', 'reason': 'spatial_preflight_failed',
            'native_export': 'not_run'})
    if args.compile and spatial_ready:
        from backend.app.program_volumes import compile_program_volume_candidate
        started=perf_counter()
        try:
            building, compiled_volumes=compile_program_volume_candidate(
                score,typology=brief.typology,project_brief=brief,legacy_controls=controls)
            if source_fingerprint != compiler_source_fingerprint():
                raise RuntimeError('Compiler source changed during building compilation')
            if compiled_volumes.digest() != volumes.digest():
                raise RuntimeError('Building compilation changed the preflight Program Volumes')
            write(args.output/'building_model_v3.json',building.model_dump(mode='json'))
            result={'status':'building_compiled_pending_review','model_id':building.model_id,
                    'element_counts':building.element_counts,
                    'world_xy_grid':asdict(building.lattice.world_xy_grid),
                    'spatial_status':building.spatial.status,
                    'dependency_status':building.dependency_graph.status,
                    'unplaced':[item.model_dump(mode='json') for item in building.program_allocation.unplaced],
                    'limitations':building.limitations,'native_export':'not_run'}
        except (ValueError, RuntimeError) as exc:
            result={'status':'building_compile_failed','error_type':type(exc).__name__,
                    'error':str(exc),'native_export':'not_run'}
        result.update(seconds=round(perf_counter()-started,2),
                      compiler_source_fingerprint=source_fingerprint,
                      source_unchanged=source_fingerprint==compiler_source_fingerprint())
        write(args.output/'building_result.json',result)
        print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
