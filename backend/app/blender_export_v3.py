"""Headless Blender export for schema 3.0.

Same contract as `blender_export.py`: run Blender out of process, produce a semantic GLB
the browser can load, and hash everything so the run manifest can record what was
actually shipped. Authority stays `presentation_only`.

The v3 model is roughly an order of magnitude more elements than v2, so the adapter
merges meshes per (layer, subsystem, category, material) before export. The element-level
authority stays in `building_model_v3.json`; the GLB carries exactly the grouping the web
viewport filters on and nothing finer.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from .blender_export import (
    BlenderExportError,
    _blender_output_tail,
    find_blender_executable,
    sha256_file,
)
from .models import ModelAssetV3
from .models_v3 import BuildingModelV3

ROOT = Path(__file__).resolve().parents[2]
IMPORT_SCRIPT = ROOT / 'blender' / 'import_building_model_v3.py'
WEB_ASSET_DIRECTORY = ROOT / 'web' / 'public' / 'models' / 'generated'
BLEND_DIRECTORY = ROOT / 'blender' / 'generated'
RENDER_DIRECTORY = ROOT / 'artifacts' / 'v3_runs'
BLENDER_TIMEOUT_SECONDS = 240
SAFE_MODEL_ID = re.compile(r'^[a-zA-Z0-9_-]+$')


def export_blender_web_model_v3(
    model: BuildingModelV3, *, render: bool = False,
) -> ModelAssetV3:
    if not SAFE_MODEL_ID.fullmatch(model.model_id):
        raise BlenderExportError(f'Unsafe model_id for Blender export: {model.model_id}')
    blender = find_blender_executable()
    if not IMPORT_SCRIPT.is_file():
        raise BlenderExportError(f'Blender v3 import script is missing: {IMPORT_SCRIPT}')

    for directory in (WEB_ASSET_DIRECTORY, BLEND_DIRECTORY, RENDER_DIRECTORY):
        directory.mkdir(parents=True, exist_ok=True)

    glb_path = WEB_ASSET_DIRECTORY / f'{model.model_id}.glb'
    manifest_path = WEB_ASSET_DIRECTORY / f'{model.model_id}.manifest.json'
    blend_path = BLEND_DIRECTORY / f'{model.model_id}.blend'
    render_dir = RENDER_DIRECTORY / model.model_id
    model_json_path = render_dir / 'building_model_v3.json'
    render_dir.mkdir(parents=True, exist_ok=True)
    model_json_path.write_text(model.model_dump_json(indent=1), encoding='utf-8')

    with TemporaryDirectory(prefix='mta-blender-v3-') as temp_directory:
        source_path = Path(temp_directory) / 'building_model_v3.json'
        source_path.write_text(model.model_dump_json(), encoding='utf-8')
        command = [
            str(blender), '--background', '--factory-startup',
            '--python-exit-code', '1',
            '--python', str(IMPORT_SCRIPT), '--',
            str(source_path), str(blend_path), str(render_dir),
            str(glb_path), str(manifest_path),
        ]
        try:
            result = subprocess.run(
                command, cwd=ROOT, capture_output=True, text=True,
                timeout=BLENDER_TIMEOUT_SECONDS, check=False)
        except subprocess.TimeoutExpired as error:
            raise BlenderExportError(
                f'Blender timed out after {BLENDER_TIMEOUT_SECONDS}s') from error
        if result.returncode != 0:
            raise BlenderExportError(
                'Blender v3 export failed: ' + _blender_output_tail(result))

    for path in (glb_path, manifest_path):
        if not path.is_file():
            raise BlenderExportError(
                f'Blender did not write {path.name}; '
                f'Blender output: {_blender_output_tail(result)}')

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    return ModelAssetV3(
        asset_url=f'/models/generated/{glb_path.name}',
        manifest_url=f'/models/generated/{manifest_path.name}',
        native_blend_path=str(blend_path.relative_to(ROOT)).replace('\\', '/'),
        model_json_path=str(model_json_path.relative_to(ROOT)).replace('\\', '/'),
        asset_sha256=sha256_file(glb_path),
        manifest_sha256=sha256_file(manifest_path),
        element_count=manifest['element_count'],
        merged_object_count=manifest['merged_objects'],
        face_count=manifest['total_faces'],
        semantic_layers=sorted({o['layer'] for o in manifest['objects'].values()}),
        renders=manifest.get('renders', []) if render else [],
    )
