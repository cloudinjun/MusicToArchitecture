"""Freeze one complete run into the web app's public folder.

    python -m backend.scripts.generate_web_demo

The workbench has to show something real before anyone uploads anything, and "something
real" now means every panel: the score, the selection reasoning, the sizing, the gates,
the egress findings, the drawings, the stills. A hand-written fixture would be a lie
that rots, so this runs the actual pipeline -- the same `compile_generation` the API
calls -- and writes the response where the browser can fetch it with no server running.

The sheets and stills are copied into `web/public` and the payload's URLs are rewritten
to point at the copies. A live run keeps its `/api/...` URLs and is served by the API;
the demo keeps public ones and needs nothing. The client tells them apart by the prefix
and nothing else has to know.
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


def _drop_other_models(root: Path, keep: str) -> list[str]:
    """Remove artifact directories belonging to some other building.

    The demo folder holds exactly one run, and the model identity is now a hash of
    everything that shapes the building rather than of the audio alone -- so a compiler
    change or a different selection produces a new directory beside the old one instead
    of writing over it. That is the point upstream; here it would leave the previous
    demo's sheets and stills sitting in `web/public` forever, served by a client that no
    longer references them.
    """
    if not root.is_dir():
        return []
    dropped = []
    for path in sorted(root.iterdir()):
        if path.is_dir() and path.name != keep:
            shutil.rmtree(path)
            dropped.append(path.name)
    return dropped


def main() -> None:
    print(f'compiling {MP3.name} …')
    response = compile_generation(MP3, MP3.name, render=True)
    model_id = response.analysis.model_id if response.analysis else response.building_model.model_id

    stale = (_drop_other_models(WEB_DRAWINGS, model_id)
             + _drop_other_models(WEB_RENDERS, model_id))
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
    (WEB_REPORTS / 'demo_run.json').write_text(payload, encoding='utf-8')
    if response.translation_report is not None:
        (WEB_REPORTS / 'translation_report.json').write_text(
            response.translation_report.model_dump_json(), encoding='utf-8')

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
    if stale:
        print(f'removed     {len(stale)} stale artifact directories: '
              + ', '.join(sorted(set(stale))))
    print(f'payload     {len(payload) / 1024:.0f} KB → web/public/reports/demo_run.json')

    # A last check that the file the browser will read parses as what was written.
    json.loads((WEB_REPORTS / 'demo_run.json').read_text(encoding='utf-8'))


if __name__ == '__main__':
    main()
