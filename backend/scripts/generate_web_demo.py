"""Freeze one complete run into the web app's public folder.

    python -m backend.scripts.generate_web_demo

The workbench has to show something real before anyone uploads anything, and "something
real" now means every panel: the score, the selection reasoning, the sizing, the gates,
the egress findings, the drawings, the stills. A hand-written fixture would be a lie
that rots, so this runs the actual pipeline -- the same `compile_generation` the API
calls -- and writes the response where the browser can fetch it with no server running.

The pipeline first writes a candidate. `publish_model_version` validates and archives
that candidate, then updates the stable `latest` public aliases and frozen payload. A
live run keeps its `/api/...` URLs; the published demo needs no server.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from backend.app.drawings import DRAWING_DIRECTORY
from backend.app.pipeline import RENDER_DIRECTORY, compile_generation

ROOT = Path(__file__).resolve().parents[2]
MP3 = ROOT / 'fixtures' / 'audio' / 'gemini_music_to_architecture_44s.mp3'
WEB_PUBLIC = ROOT / 'web' / 'public'
WEB_REPORTS = WEB_PUBLIC / 'reports'
WEB_DRAWINGS = WEB_PUBLIC / 'drawings'
WEB_RENDERS = WEB_PUBLIC / 'renders'


def _copy_tree(source: Path, target: Path, pattern: str) -> int:
    if not source.is_dir():
        return 0
    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    for path in sorted(source.glob(pattern)):
        shutil.copy2(path, target / path.name)
        copied += 1
    return copied


def main() -> None:
    print(f'compiling {MP3.name} …')
    response = compile_generation(MP3, MP3.name, render=True)
    model_id = response.analysis.model_id if response.analysis else response.building_model.model_id

    sheets = _copy_tree(DRAWING_DIRECTORY / model_id, WEB_DRAWINGS / model_id, '*.svg')
    stills = _copy_tree(RENDER_DIRECTORY / model_id, WEB_RENDERS / model_id, '*.png')

    # Re-point the copied artifacts. Everything else in the payload is left exactly as
    # the pipeline produced it, so the demo and a live run differ in URLs and nothing.
    for sheet in response.drawing_sheets:
        sheet.url = f'/drawings/{model_id}/{sheet.id}.svg'
    for render in response.renders:
        render.url = f'/renders/{model_id}/{render.filename}'

    WEB_REPORTS.mkdir(parents=True, exist_ok=True)
    payload = response.model_dump_json()
    candidate = WEB_REPORTS / 'demo_candidate.json'
    candidate.write_text(payload, encoding='utf-8')
    translation_candidate = WEB_REPORTS / 'translation_report_candidate.json'
    if response.translation_report is not None:
        translation_candidate.write_text(response.translation_report.model_dump_json(),
                                         encoding='utf-8')

    analysis = response.analysis
    compliance = analysis.compliance if analysis else None
    print(f'model       {model_id}')
    print(f'selection   {analysis.typology if analysis else "?"} · '
          f'{analysis.selection.massing_id if analysis and analysis.selection else "?"} · '
          f'{analysis.structural_system_id if analysis else "?"} · '
          f'{analysis.facade_grammar_id if analysis else "?"}')
    print(f'elements    {analysis.element_count if analysis else 0} in '
          f'{len(analysis.element_groups) if analysis else 0} groups')
    if compliance:
        print(f'checks      {compliance.passed_total} passed, {compliance.failed_total} failed, '
              f'{compliance.unevaluated_total} unevaluated')
    print(f'drawings    {sheets} sheets, {stills} stills copied to web/public')
    print(f'candidate   {len(payload) / 1024:.0f} KB → web/public/reports/demo_candidate.json')

    # A last check that the file the browser will read parses as what was written.
    json.loads(candidate.read_text(encoding='utf-8'))
    from backend.scripts.publish_model_version import publish
    pointer = publish(candidate)
    candidate.unlink()
    translation_candidate.unlink(missing_ok=True)
    print(f'published   {pointer["version_id"]} → artifacts/model_versions/latest/')


if __name__ == '__main__':
    main()
