"""Regenerate the schema 3.0 browser asset from the checked-in score fixture.

    python -m backend.scripts.generate_v3_demo

Runs the whole v3 chain without the API or an MP3 upload, so the web page has something
to draw and the renders stay reproducible. Authority: presentation only.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.audio import extract_audio_features
from backend.app.blender_export_v3 import export_blender_web_model_v3
from backend.app.compiler_v3 import compile_building_model_v3
from backend.app.score import compile_architectural_score
from backend.app.translation_report import compile_translation_report

ROOT = Path(__file__).resolve().parents[2]
MP3 = ROOT / 'fixtures' / 'audio' / 'gemini_music_to_architecture_44s.mp3'
OUT = ROOT / 'artifacts' / 'v3_demo'
WEB_REPORTS = ROOT / 'web' / 'public' / 'reports'


def main() -> None:
    # Run the real MP3 so the demo exercises the full ten-dimension score rather than
    # the four-dimension artifact that predates the extended extractor.
    features = extract_audio_features(MP3, MP3.name)
    score = compile_architectural_score(features)

    model = compile_building_model_v3(features, score)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'architectural_score.json').write_text(
        score.model_dump_json(indent=2), encoding='utf-8')
    (OUT / 'building_model_v3.json').write_text(
        model.model_dump_json(indent=1), encoding='utf-8')

    allocation = model.program_allocation
    report = [
        '# Program allocation', '',
        f'Model `{model.model_id}` from score `{model.score_id}`.', '',
        f'- occupied levels: **{len(model.lattice.occupied)}**',
        f'- usable plate: **{sum(allocation.usable_area_by_level.values()):.0f} m2**',
        f'- briefed: **{allocation.required_area_m2:.0f} m2**, '
        f'delivered **{allocation.delivered_area_m2:.0f} m2** '
        f'({allocation.fulfilment:.0%})',
        f'- every space fits: **{allocation.fits}**', '',
        '| space | level | size | delivered | briefed | dev | daylight | preferred level |',
        '|---|---|---|---:|---:|---:|:--:|:--:|',
    ]
    for zone in allocation.zones:
        report.append(
            f'| {zone.label} | {zone.level_id} | '
            f'{zone.x1 - zone.x0:.1f} x {zone.y1 - zone.y0:.1f} m | '
            f'{zone.area_delivered_m2:.0f} | {zone.area_required_m2:.0f} | '
            f'{zone.deviation:+.0%} | {"yes" if zone.daylight_satisfied else "no"} | '
            f'{"yes" if zone.level_preference_satisfied else "no"} |')
    if allocation.unplaced:
        report += ['', '## Unplaced', '',
                   'The score did not produce enough plate for these. Reported rather '
                   'than absorbed by shrinking the rooms that did fit.', '']
        for space in allocation.unplaced:
            report.append(f'- **{space.label}** ({space.area_required_m2:.0f} m2): '
                          f'{space.reason}')
    (OUT / 'program_allocation.md').write_text('\n'.join(report) + '\n',
                                               encoding='utf-8')

    # --- score -> datum -> element traceability -----------------------------
    by_dimension: dict[str, list] = {}
    for datum in model.datum_set.datums:
        by_dimension.setdefault(datum.driving_dimension or datum.provenance,
                                []).append(datum)
    element_datums: dict[str, int] = {}
    for group in model.element_groups:
        for ref in group.datum_refs:
            element_datums[ref] = element_datums.get(ref, 0) + len(group.instances)

    trace = [
        '# Score to element traceability', '',
        f'Model `{model.model_id}` from score `{model.score_id}`.', '',
        f'- score dimensions emitted: **{len(score.dimensions)} of 10**',
        f'- datums: **{len(model.datum_set.datums)}**, '
        f'{model.datum_set.coverage:.0%} score-driven overall, '
        f'**{model.datum_set.variable_coverage:.0%} of the variable datums**',
        f'- elements: **{model.element_count}** in '
        f'{len(model.element_groups)} groups', '',
        'A datum whose driving dimension is measured at low confidence is clamped '
        'toward the middle of its declared range, so a weak reading nudges the design '
        'and a strong one commits. The clamp column shows how much of the range each '
        'datum was actually allowed to travel.', '',
    ]
    for dimension in score.dimensions:
        datums = by_dimension.get(dimension.id, [])
        trace += [
            f'## {dimension.id}  ({dimension.value:.3f}, '
            f'{dimension.extraction_method}, confidence {dimension.confidence:.2f})', '',
            f'Measured from `{dimension.source_feature}`.', '',
            f'> {dimension.architectural_proposal}', '',
            '| datum | value | range | travel | elements |',
            '|---|---:|---|---:|---:|',
        ]
        for datum in datums:
            low, high = datum.output_range or (0.0, 0.0)
            factor = 1.0
            if datum.dimension_confidence is not None:
                factor = min(1.0, datum.dimension_confidence / 0.75)
            trace.append(
                f'| `{datum.id}` | {datum.value:.3f} {datum.unit} | '
                f'{low:g} .. {high:g} | {factor:.0%} | '
                f'{element_datums.get(datum.id, 0)} |')
        trace.append('')

    constants = by_dimension.get('tectonic_constant', [])
    if constants:
        trace += ['## Fixed by the tectonic system, never by music', '',
                  '| datum | value | why |', '|---|---:|---|']
        for datum in constants:
            trace.append(f'| `{datum.id}` | {datum.value:g} {datum.unit} | '
                         f'{datum.reason} |')
        trace.append('')
    (OUT / 'score_traceability.md').write_text('\n'.join(trace), encoding='utf-8')

    report_model = compile_translation_report(features, score, model)
    (OUT / 'translation_report.json').write_text(
        report_model.model_dump_json(indent=2), encoding='utf-8')
    WEB_REPORTS.mkdir(parents=True, exist_ok=True)
    (WEB_REPORTS / 'translation_report.json').write_text(
        report_model.model_dump_json(), encoding='utf-8')

    asset = export_blender_web_model_v3(model, render=True)
    (OUT / 'model_asset_v3.json').write_text(
        asset.model_dump_json(indent=2), encoding='utf-8')

    datums = model.datum_set
    print(f'elements    {model.element_count} across {len(model.element_counts)} kinds '
          f'in {len(model.element_groups)} groups')
    print(f'program     {allocation.delivered_area_m2:.0f}/'
          f'{allocation.required_area_m2:.0f} m2 ({allocation.fulfilment:.0%}), '
          f'fits={allocation.fits}'
          + ('' if allocation.fits else
             ', unplaced: ' + ', '.join(u.label for u in allocation.unplaced)))
    print(f'layers      {model.layer_counts}')
    print(f'levels      {len(model.lattice.levels)}, roof at '
          f'{model.lattice.roof.z:.1f} m')
    print(f'score       {len(score.dimensions)} dimensions: '
          + ', '.join(f'{d.id}={d.value:.2f}' for d in score.dimensions))
    print(f'datums      {len(datums.datums)} total, {datums.coverage:.0%} score-driven, '
          f'{datums.variable_coverage:.0%} of the variables')
    if datums.waiting_on:
        print(f'            waiting on {", ".join(datums.waiting_on)}')
    if datums.clamped_datums:
        print(f'            clamped by low confidence: '
              f'{len(datums.clamped_datums)} datums')
    for record in model.sizing:
        print(f'  {record.role:16} {record.section_id:22} '
              f'{record.governing_check:18} {record.utilisation:.2f}')
    print(f'health      ' + ', '.join(f'{k} {v}'
                                       for k, v in sorted(report_model.grades.items())))
    print(f'glb         {asset.asset_url}  {asset.merged_object_count} objects, '
          f'{asset.face_count} faces')
    print(f'renders     {", ".join(asset.renders)}')
    print()
    print('The standalone v3 report is copied to web/public/reports. Run '
          'backend.scripts.generate_web_demo to refresh the complete frozen workbench.')


if __name__ == '__main__':
    main()
