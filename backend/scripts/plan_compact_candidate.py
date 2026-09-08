"""Preflight one saved-score composition through shared spatial/system planning."""
import argparse
import hashlib
import json
from pathlib import Path

from backend.app.candidate_planning import plan_compact_candidate
from backend.app.legacy_program_layout import LegacyLayoutControls
from backend.app.models import ArchitecturalScore
from backend.app.project_brief import ProjectBrief
from backend.app.version import compiler_source_fingerprint
from backend.scripts.run_small_site_study import preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('score','brief','controls','out'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--score-composition',action='store_true')
    parser.add_argument('--joint-layout',action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    load = lambda path: json.loads(path.read_text(encoding='utf-8'))
    score = ArchitecturalScore.model_validate(load(args.score))
    brief = ProjectBrief.model_validate(load(args.brief))
    payload = load(args.controls)
    controls = LegacyLayoutControls.model_validate(payload.get('controls',payload))
    fingerprint = compiler_source_fingerprint()
    result = plan_compact_candidate(score,brief,controls=controls,
                                    score_composition=args.score_composition,
                                    joint_layout=args.joint_layout)
    if fingerprint != compiler_source_fingerprint():
        raise RuntimeError('Compiler source changed during candidate planning')
    report = dict(status=result.status, compiler_source_fingerprint=fingerprint,
                  source_unchanged=True, composition_basis=result.composition_basis,
                  inputs={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (args.score,args.brief,args.controls)},
                  attempts=result.attempts, native_export='not_run',
                  authority='Pre-emission proposal only; no physical member or readiness approval.')
    (args.out/'planning.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    if result.volumes is not None:
        volumes = result.volumes
        (args.out/'program_volumes.json').write_text(volumes.model_dump_json(indent=2),encoding='utf-8')
        if result.status == 'spatially_coordinated':
            # A compile must replay the selected root and any facade-reserved
            # brief, not reconstruct controls from an earlier failed proposal.
            (args.out/'resolved_project_brief.json').write_text(
                volumes.project_brief.model_dump_json(indent=2),encoding='utf-8')
            (args.out/'compile_input_patch.json').write_text(json.dumps(dict(
                brief_overrides={}, reasons=['Replay of spatially coordinated compact planning; '
                    'physical geometry and professional review remain unevaluated.'],
                controls=result.controls.model_dump(mode='json')),indent=2),encoding='utf-8')
        rectangles = [dict(id=v.id,level=v.level_index-1,category=v.category,role=v.role,
                          spaces=v.space_ids,rect=volumes.rect_of(v)) for v in volumes.volumes]
        preview(args.out,volumes.project_brief,rectangles,
                [(v.z_base,v.z_top) for v in volumes.levels],None,result.status)
    print(json.dumps({'status':result.status,'attempts':[
        {k:v for k,v in a.items() if k not in ('program_volumes','facade_control','selection','rectangles')}
        for a in result.attempts]}))


if __name__ == '__main__':
    main()
