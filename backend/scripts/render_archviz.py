"""One-command entry point for the five Blender architectural render presets.

Examples:

    python -m backend.scripts.render_archviz
    python -m backend.scripts.render_archviz --input-blend path/to/model.blend
    python -m backend.scripts.render_archviz --preview
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from backend.app.blender_export import find_blender_executable


ROOT = Path(__file__).resolve().parents[2]
BLENDER_SCRIPT = ROOT / "blender" / "render_presets.py"
DEFAULT_DEMO = ROOT / "artifacts" / "v3_demo" / "model_v3.blend"
OUTPUT_ROOT = ROOT / "artifacts" / "render_presets"


def latest_input() -> Path:
    """Prefer the latest generated building and fall back to the stable v3 demo."""
    generated = ROOT / "blender" / "generated"
    candidates = [
        path for path in generated.glob("*.blend")
        if not path.name.startswith("MTA_Render_Ready")
    ]
    if DEFAULT_DEMO.is_file():
        candidates.append(DEFAULT_DEMO)
    if not candidates:
        raise FileNotFoundError(
            "No input .blend found. Pass --input-blend or generate the v3 demo first.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def validate_manifest(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError(f"Blender did not write the render manifest: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not payload.get("complete"):
        raise RuntimeError(
            f"Render manifest is incomplete: {payload.get('render_count')} / "
            f"{payload.get('expected_render_count')}")
    missing = [
        row["path"] for row in payload.get("renders", [])
        if not (path.parent / row["path"]).is_file()
    ]
    if missing:
        raise RuntimeError(f"Manifest references missing renders: {missing}")
    if payload.get("input_overwritten"):
        raise RuntimeError("Render system overwrote its input .blend")
    if payload.get("geometry_mutated"):
        raise RuntimeError("Render system reports a source-geometry mutation")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-blend", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--styles", default="all")
    parser.add_argument("--views", default="all")
    parser.add_argument("--resolution", default="1400x900")
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument(
        "--preview", action="store_true",
        help="Render at 800x520 with 16 samples for rapid look development.")
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args()

    source = (args.input_blend or latest_input()).resolve()
    if not source.is_file() or source.suffix.lower() != ".blend":
        raise FileNotFoundError(f"Input is not a .blend file: {source}")
    output = (args.output or OUTPUT_ROOT / source.stem).resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / "render_manifest.json"
    template = output / "MTA_Render_Ready.blend"
    resolution = "800x520" if args.preview else args.resolution
    samples = 16 if args.preview else args.samples

    blender = find_blender_executable()
    command = [
        str(blender), "--background", str(source),
        "--python-exit-code", "1",
        "--python", str(BLENDER_SCRIPT), "--",
        "--output", str(output),
        "--template", str(template),
        "--manifest", str(manifest),
        "--styles", args.styles,
        "--views", args.views,
        "--resolution", resolution,
        "--samples", str(samples),
    ]
    if args.no_render:
        command.append("--no-render")

    print(f"Input   : {source}")
    print(f"Output  : {output}")
    print(f"Blender : {blender}")
    result = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace")
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode:
        excerpt = ((result.stderr or "") + "\n" + (result.stdout or ""))[-6000:]
        raise RuntimeError(f"Blender render failed ({result.returncode}):\n{excerpt}")

    if args.no_render:
        if not template.is_file() or not manifest.is_file():
            excerpt = ((result.stderr or "") + "\n" + (result.stdout or ""))[-6000:]
            raise RuntimeError(f"Blender did not prepare the template and manifest:\n{excerpt}")
        print(f"Prepared template: {template}")
        return
    payload = validate_manifest(manifest)
    print(
        f"Verified {payload['render_count']} renders across "
        f"{len(payload['styles'])} styles and {len(payload['views'])} views.")
    print(f"Template: {template}")
    print(f"Manifest: {manifest}")


if __name__ == "__main__":
    main()
