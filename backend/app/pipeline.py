"""One run, start to finish, with no HTTP in it.

The API used to hold the pipeline inline, which meant the only way to produce a
complete run was to upload a file to a live server. The demo generator therefore
rebuilt a subset of the same chain by hand, and the two drifted: the page's offline
demo carried a translation report and a GLB while a real upload carried a dozen
reports more.

Extracting it fixes that by construction. `compile_generation` is what a run *is*;
`main.py` maps it onto HTTP and `backend.scripts.generate_v3_demo` writes its result
to disk for the browser to read without a server. Neither can produce a run the other
cannot.

The additive rule from the API is preserved exactly: the v2 acceptance chain is
compiled first and never made to depend on schema 3.0, and each optional downstream
product -- the member-level GLB, the drawing set -- records its own absence instead of
failing a run that otherwise succeeded.
"""

from __future__ import annotations

import re
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

from .analysis_bundle import compile_analysis_bundle
from .audio import extract_audio_features
from .version import COMPILER_VERSION
from .bim_handoff import compile_bim_handoff_report
from .blender_export import BlenderExportError, export_blender_web_model
from .blender_export_v3 import export_blender_web_model_v3
from .compiler import compile_building_model
from .compiler_v3 import compile_building_model_v3
from .drawings import issue_drawings, write_drawing_set
from .integration import compile_facade_host_handoff, compile_pipeline_manifest
from .mapping_report import compile_mapping_report
from .models import DrawingSheetRef, GenerationResponse, RenderRef
from .score import compile_architectural_score
from .translation_report import compile_translation_report

ROOT = Path(__file__).resolve().parents[2]
RENDER_DIRECTORY = ROOT / 'artifacts' / 'v3_runs'

# Ids and filenames that end up in a URL or joined to a directory are matched against
# these first. The route that serves them repeats the check and adds a resolved-path
# test; neither is sufficient alone.
SAFE_ID = re.compile(r'^[A-Za-z0-9_-]{1,80}$')


def drawing_sheet_refs(model_id: str, index: dict | None) -> list[DrawingSheetRef]:
    """The drawing index as fetchable references, each keeping its own audit."""
    if not index:
        return []
    sheets: list[DrawingSheetRef] = []
    for sheet in index.get('sheets', []):
        sheet_id = str(sheet.get('id', ''))
        if not SAFE_ID.fullmatch(sheet_id):
            continue
        sheets.append(DrawingSheetRef(
            id=sheet_id,
            title=sheet.get('title', sheet_id),
            kind=sheet.get('kind', 'plan'),
            scale=sheet.get('scale', ''),
            subtitle=sheet.get('subtitle', ''),
            url=f'/api/models/{model_id}/drawings/{sheet_id}.svg',
            sheet_mm=[float(value) for value in sheet.get('sheet_mm', [])],
            marks=int(sheet.get('marks', 0)),
            elements_cut=int(sheet.get('elements_cut', 0)),
            elements_drawn=int(sheet.get('elements_drawn', 0)),
            omitted_by_scale={str(kind): int(count)
                              for kind, count in sheet.get('omitted_by_scale', {}).items()},
        ))
    return sheets


def render_refs(model_id: str) -> list[RenderRef]:
    """Whatever stills the run left on disk.

    The API path does not render -- four camera passes are minutes the request cannot
    spend -- but a scripted run does, and those images belong to the run either way.
    """
    if not SAFE_ID.fullmatch(model_id):
        return []
    directory = RENDER_DIRECTORY / model_id
    if not directory.is_dir():
        return []
    return [
        RenderRef(id=path.stem, filename=path.name,
                  url=f'/api/models/{model_id}/renders/{path.name}')
        for path in sorted(directory.glob('*.png'))
    ]


def compile_generation(audio_path: Path, filename: str, *,
                       render: bool = False) -> GenerationResponse:
    """Compile one MP3 into every artifact and report this project produces.

    Blocking throughout -- librosa and two Blender subprocesses -- so an async caller
    should hand it to a thread rather than awaiting pieces of it.
    """
    started = time.perf_counter()
    features = extract_audio_features(audio_path, filename)
    score = compile_architectural_score(features)

    # --- v2: the massing contract the acceptance chain reads --------------------
    model = compile_building_model(features, score)
    mapping_report = compile_mapping_report(features, score, model)
    facade_handoff = compile_facade_host_handoff(score, model)
    model_asset = export_blender_web_model(model)

    # --- v3: the member-level model the viewport draws --------------------------
    model_v3 = compile_building_model_v3(features, score)
    translation_report = compile_translation_report(features, score, model_v3)
    bim_handoff = compile_bim_handoff_report(model_v3)
    try:
        model_asset_v3 = export_blender_web_model_v3(model_v3, render=render)
    except BlenderExportError:
        model_asset_v3 = None

    # Plans and sections, issued from the same model the viewport draws. A drawing set
    # that cannot be produced -- a massing whose plate no plane meets, a level with
    # nothing on it -- leaves the index absent rather than failing the run.
    try:
        issued = issue_drawings(model_v3)
        write_drawing_set(issued, model_v3)
        drawing_index = issued.manifest(model_v3)
    except ValueError:
        drawing_index = None

    # One run, one identity: the audio, the compiler that ran, and the building that
    # came out. Keying runs on the audio alone let a re-run after a compiler change
    # replace assets an older stored run still pointed at, and made two pinned variants
    # of one piece impossible to keep side by side.
    run_seed = f'{features.provenance.sha256}|{COMPILER_VERSION}|{model_v3.model_id}'
    run_id = 'run-' + hashlib.sha256(run_seed.encode('utf-8')).hexdigest()[:12]
    pipeline_manifest = compile_pipeline_manifest(
        features, score, model, mapping_report, facade_handoff, model_asset,
        run_id=run_id)

    # Everything the v3 compile decided and checked. The v2 validation and the handoff
    # gates are handed in so the roll-up covers every check the run ran rather than
    # only the member-level half.
    analysis = compile_analysis_bundle(
        model_v3, validation=model.validation, pipeline_gates=facade_handoff.gates,
        bim_handoff=bim_handoff,
        companion_identity=(
            f'{model.typology}/{model.facade_profile.grammar_id}'))

    return GenerationResponse(
        run_id=pipeline_manifest.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        elapsed_seconds=round(time.perf_counter() - started, 2),
        audio_features=features,
        architectural_score=score,
        building_model=model,
        mapping_report=mapping_report,
        facade_handoff=facade_handoff,
        model_asset=model_asset,
        pipeline_manifest=pipeline_manifest,
        model_asset_v3=model_asset_v3,
        translation_report=translation_report,
        datum_coverage=model_v3.datum_set.coverage,
        datum_waiting_on=model_v3.datum_set.waiting_on,
        drawing_index=drawing_index,
        drawing_sheets=drawing_sheet_refs(model_v3.model_id, drawing_index),
        renders=render_refs(model_v3.model_id),
        analysis=analysis,
    )
