from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from .models import BuildingModel, ModelAsset


ROOT = Path(__file__).resolve().parents[2]
IMPORT_SCRIPT = ROOT / "blender" / "import_building_model.py"
WEB_ASSET_DIRECTORY = ROOT / "web" / "public" / "models" / "generated"
BLEND_DIRECTORY = ROOT / "blender" / "generated"
STATE_DIRECTORY = ROOT / "artifacts" / "native_models" / "generated"
BLENDER_TIMEOUT_SECONDS = 90
SAFE_MODEL_ID = re.compile(r"^[a-zA-Z0-9_-]+$")


class BlenderExportError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def find_blender_executable() -> Path:
    configured = os.environ.get("MTA_BLENDER_EXECUTABLE")
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if candidate.is_file():
            return candidate
        raise BlenderExportError(f"Configured Blender executable does not exist: {candidate}")

    roots = [Path(r"C:\Program Files\Blender Foundation")]
    candidates = [
        executable
        for root in roots
        if root.exists()
        for executable in root.glob("Blender */blender.exe")
    ]
    if not candidates:
        raise BlenderExportError(
            "Blender was not found. Install Blender or set MTA_BLENDER_EXECUTABLE."
        )
    return sorted(candidates, reverse=True)[0]


def export_blender_web_model(
    model: BuildingModel, *, render_path: Path | None = None
) -> ModelAsset:
    if not SAFE_MODEL_ID.fullmatch(model.model_id):
        raise BlenderExportError(f"Unsafe model_id for Blender export: {model.model_id}")
    blender = find_blender_executable()
    if not IMPORT_SCRIPT.is_file():
        raise BlenderExportError(f"Blender import script is missing: {IMPORT_SCRIPT}")

    for directory in (WEB_ASSET_DIRECTORY, BLEND_DIRECTORY, STATE_DIRECTORY):
        directory.mkdir(parents=True, exist_ok=True)

    glb_path = WEB_ASSET_DIRECTORY / f"{model.model_id}.glb"
    manifest_path = WEB_ASSET_DIRECTORY / f"{model.model_id}.manifest.json"
    blend_path = BLEND_DIRECTORY / f"{model.model_id}.blend"
    state_path = STATE_DIRECTORY / f"{model.model_id}.scene.json"

    if render_path:
        render_path = render_path.resolve()
        render_path.parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix="mta-blender-") as temp_directory:
        source_path = Path(temp_directory) / "building_model_v2.json"
        source_path.write_text(
            json.dumps(model.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
        command = [
            str(blender),
            "--background",
            "--factory-startup",
            "--python",
            str(IMPORT_SCRIPT),
            "--",
            str(source_path),
            str(blend_path),
            str(render_path) if render_path else "-",
            str(state_path),
            str(glb_path),
            str(manifest_path),
        ]
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=BLENDER_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise BlenderExportError(
                f"Blender export exceeded {BLENDER_TIMEOUT_SECONDS} seconds"
            ) from error

    if result.returncode != 0:
        excerpt = (result.stderr or result.stdout or "unknown Blender error")[-1200:]
        raise BlenderExportError(f"Blender export failed: {excerpt.strip()}")
    missing = [path.name for path in (glb_path, manifest_path, blend_path, state_path) if not path.is_file()]
    if missing:
        raise BlenderExportError(f"Blender did not create required outputs: {', '.join(missing)}")

    return ModelAsset(
        asset_url=f"/models/generated/{glb_path.name}?v={glb_path.stat().st_mtime_ns}",
        manifest_url=f"/models/generated/{manifest_path.name}?v={manifest_path.stat().st_mtime_ns}",
        native_blend_path=str(blend_path.relative_to(ROOT)).replace("\\", "/"),
        scene_state_path=str(state_path.relative_to(ROOT)).replace("\\", "/"),
        asset_sha256=sha256_file(glb_path),
        manifest_sha256=sha256_file(manifest_path),
        native_blend_sha256=sha256_file(blend_path),
        scene_state_sha256=sha256_file(state_path),
        semantic_layers=[
            "program_massing", "facade", "columns", "beams", "slabs", "foundations",
            "bracing", "cores", "interior_sequence",
            "site", "site_context", "context_tree", "context_vehicle", "context_person",
        ],
    )
