"""Publish one verified demo as an immutable archive and a stable latest bundle.

Generation writes candidates to their native application folders.  This script is the
only promotion step.  It copies the files, verifies their hashes and keeps Rhino design
authority separate from Blender presentation authority.

    python -m backend.scripts.publish_model_version
    python -m backend.scripts.publish_model_version --check

A Rhino model can join a release only with a matching acceptance sidecar:

    python -m backend.scripts.publish_model_version \
      --rhino-3dm path/to/model.3dm --rhino-manifest path/to/acceptance.json
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.version import COMPILER_VERSION, compiler_source_fingerprint
from backend.scripts.measure_visual_geometry import measure as measure_visual_geometry


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEMO = ROOT / "web" / "public" / "reports" / "demo_run.json"
VERSIONS = ROOT / "artifacts" / "model_versions"
LATEST = VERSIONS / "latest"
ARCHIVE = VERSIONS / "archive"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _inside(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"path leaves repository: {path}")
    return resolved


def _from_url(root: Path, url: str) -> Path:
    clean = url.split("?", 1)[0]
    if not clean.startswith("/"):
        raise ValueError(f"expected a public absolute URL, got {url!r}")
    return _inside(root, root / "web" / "public" / clean.lstrip("/"))


def _asset(source: Path, bundle: Path, relative_path: str, role: str,
           authority: str) -> dict[str, Any]:
    source = _inside(ROOT, source)
    if not source.is_file():
        raise FileNotFoundError(source)
    destination = bundle / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {
        "role": role,
        "authority": authority,
        "path": relative_path,
        "source_path": source.relative_to(ROOT).as_posix(),
        "bytes": destination.stat().st_size,
        "sha256": _sha256(destination),
    }


def _record_generated_asset(path: Path, relative_path: str, role: str,
                            authority: str, source: str) -> dict[str, Any]:
    return {
        "role": role,
        "authority": authority,
        "path": relative_path,
        "source_path": source,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _bundle_signature(assets: list[dict[str, Any]]) -> str:
    inventory = [
        (item["path"], item["sha256"], item["authority"], item["role"])
        for item in sorted(assets, key=lambda value: value["path"])
    ]
    encoded = json.dumps(inventory, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stable_public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the one canonical URL form used for hashing and public delivery."""
    stable = copy.deepcopy(payload)
    stable["model_asset_v3"]["asset_url"] = "/models/generated/latest-v3.glb"
    stable["model_asset_v3"]["manifest_url"] = "/models/generated/latest-v3.manifest.json"
    if isinstance(stable.get("model_asset"), dict):
        stable["model_asset"]["asset_url"] = "/models/generated/latest-v2.glb"
        stable["model_asset"]["manifest_url"] = "/models/generated/latest-v2.manifest.json"
    for render in stable.get("renders", []):
        render["url"] = f"/renders/latest/{render['filename']}"
    for sheet in stable.get("drawing_sheets", []):
        sheet["url"] = f"/drawings/latest/{sheet['id']}.svg"
    for artifact in stable.get("pipeline_manifest", {}).get("artifacts", []):
        if artifact.get("id") == "blender-glb":
            artifact["uri"] = "/models/generated/latest-v2.glb"
        elif artifact.get("id") == "blender-manifest":
            artifact["uri"] = "/models/generated/latest-v2.manifest.json"
    return stable


def _rhino_acceptance(
    payload: dict[str, Any],
    destination: Path,
    rhino_3dm: Path | None,
    rhino_manifest: Path | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    run_id = payload["run_id"]
    model_id = payload["analysis"]["model_id"]
    if (rhino_3dm is None) != (rhino_manifest is None):
        raise ValueError("Rhino publication requires both .3dm and acceptance manifest")
    if rhino_3dm is None:
        status = {
            "status": "blocked",
            "authority": "accepted_geometry",
            "owner": "rhino",
            "purposes": ["issued_drawings", "revit_handoff"],
            "model_id": model_id,
            "run_id": run_id,
            "files": [],
            "blocked_by": ["MATCHING_RHINO_3DM_AND_ACCEPTANCE_MANIFEST_REQUIRED"],
        }
        _write_json(destination / "rhino" / "status.json", status)
        return status, []

    rhino_3dm = _inside(ROOT, rhino_3dm)
    rhino_manifest = _inside(ROOT, rhino_manifest)
    if rhino_3dm.suffix.lower() != ".3dm":
        raise ValueError("Rhino design file must use .3dm")
    acceptance = json.loads(rhino_manifest.read_text(encoding="utf-8"))
    expected = {
        "status": "accepted",
        "authority": "accepted_geometry",
        "run_id": run_id,
        "model_id": model_id,
        "geometry_sha256": _sha256(rhino_3dm),
    }
    mismatches = {key: (acceptance.get(key), value) for key, value in expected.items()
                  if acceptance.get(key) != value}
    if mismatches:
        raise ValueError(f"Rhino acceptance manifest does not match this run: {mismatches}")
    assets = [
        _asset(rhino_3dm, destination, "rhino/model.3dm",
               "rhino_accepted_model", "accepted_geometry"),
        _asset(rhino_manifest, destination, "rhino/acceptance.json",
               "rhino_acceptance_manifest", "accepted_geometry"),
    ]
    status = {
        "status": "accepted",
        "authority": "accepted_geometry",
        "owner": "rhino",
        "purposes": ["issued_drawings", "revit_handoff"],
        "model_id": model_id,
        "run_id": run_id,
        "files": ["rhino/model.3dm", "rhino/acceptance.json"],
        "blocked_by": [],
    }
    _write_json(destination / "rhino" / "status.json", status)
    return status, assets


def _collect_bundle(
    payload: dict[str, Any],
    demo_path: Path,
    destination: Path,
    rhino_3dm: Path | None,
    rhino_manifest: Path | None,
) -> dict[str, Any]:
    analysis = payload.get("analysis")
    asset_v3 = payload.get("model_asset_v3")
    if not isinstance(analysis, dict) or not isinstance(asset_v3, dict):
        raise ValueError("demo has no complete v3 analysis and asset")
    model_id = analysis.get("model_id")
    if not model_id or payload.get("drawing_index", {}).get("model_id") != model_id:
        raise ValueError("analysis and drawing model IDs do not agree")
    if asset_v3.get("authority_status") != "presentation_only":
        raise ValueError("Blender v3 asset must remain presentation_only")
    source_fingerprint = payload.get("compiler_source_sha256")
    if source_fingerprint != compiler_source_fingerprint():
        raise ValueError(
            "candidate compiler source does not match the current generation source")

    assets: list[dict[str, Any]] = []
    model_json = _inside(ROOT, ROOT / asset_v3["model_json_path"])
    model = json.loads(model_json.read_text(encoding="utf-8"))
    if model.get("model_id") != model_id:
        raise ValueError("portable model JSON belongs to a different model")
    assets.append(_asset(model_json, destination, "portable/building_model_v3.json",
                         "portable_building_model", "candidate"))
    visual_report = destination / "contracts" / "visual_geometry_measurement.json"
    _write_json(visual_report, measure_visual_geometry(model))
    assets.append(_record_generated_asset(
        visual_report, "contracts/visual_geometry_measurement.json",
        "visual_geometry_measurement", "validation_report",
        "derived:portable/building_model_v3.json"))

    glb = _from_url(ROOT, asset_v3["asset_url"])
    glb_manifest = _from_url(ROOT, asset_v3["manifest_url"])
    blend = _inside(ROOT, ROOT / asset_v3["native_blend_path"])
    expected_hashes = {
        glb: asset_v3["asset_sha256"],
        glb_manifest: asset_v3["manifest_sha256"],
    }
    for source, expected_hash in expected_hashes.items():
        if _sha256(source) != expected_hash:
            raise ValueError(f"payload hash is stale for {source}")
    assets.extend([
        _asset(blend, destination, "blender/scene_v3.blend",
               "blender_render_scene_v3", "presentation_only"),
        _asset(glb, destination, "blender/model_v3.glb",
               "blender_web_model_v3", "presentation_only"),
        _asset(glb_manifest, destination, "blender/model_v3.manifest.json",
               "blender_export_manifest_v3", "presentation_only"),
    ])

    legacy = payload.get("model_asset")
    if isinstance(legacy, dict):
        legacy_glb = _from_url(ROOT, legacy["asset_url"])
        legacy_manifest = _from_url(ROOT, legacy["manifest_url"])
        legacy_blend = _inside(ROOT, ROOT / legacy["native_blend_path"])
        legacy_scene = _inside(ROOT, ROOT / legacy["scene_state_path"])
        for source, field in ((legacy_glb, "asset_sha256"),
                              (legacy_manifest, "manifest_sha256"),
                              (legacy_blend, "native_blend_sha256"),
                              (legacy_scene, "scene_state_sha256")):
            if _sha256(source) != legacy[field]:
                raise ValueError(f"legacy preview hash is stale for {source}")
        for source, name, role in (
            (legacy_blend, "scene_v2.blend", "blender_legacy_preview_scene_v2"),
            (legacy_glb, "model_v2.glb", "blender_legacy_preview_model_v2"),
            (legacy_manifest, "model_v2.manifest.json", "blender_legacy_preview_manifest_v2"),
            (legacy_scene, "model_v2.scene.json", "blender_legacy_preview_state_v2"),
        ):
            assets.append(_asset(source, destination, f"blender/{name}",
                                 role, "presentation_only"))

    for render in payload.get("renders", []):
        source = _from_url(ROOT, render["url"])
        assets.append(_asset(source, destination, f"renders/{render['filename']}",
                             f"render:{render['id']}", "presentation_only"))
    for sheet in payload.get("drawing_sheets", []):
        source = _from_url(ROOT, sheet["url"])
        assets.append(_asset(source, destination,
                             f"drawings/portable_preview/{sheet['id']}.svg",
                             f"drawing_preview:{sheet['id']}",
                             "candidate"))

    canonical_contract = destination / "contracts" / "demo_run.json"
    _write_json(canonical_contract, _stable_public_payload(payload))
    assets.append(_record_generated_asset(
        canonical_contract, "contracts/demo_run.json", "complete_run_contract",
        "validation_report", f"canonicalized:{demo_path.relative_to(ROOT).as_posix()}"))
    candidate_translation = demo_path.with_name("translation_report_candidate.json")
    translation = (candidate_translation if candidate_translation.is_file() else
                   ROOT / "web" / "public" / "reports" / "translation_report.json")
    if translation.is_file():
        assets.append(_asset(translation, destination,
                             "contracts/translation_report.json", "translation_report",
                             "validation_report"))
    if analysis.get("bim_handoff") is not None:
        _write_json(destination / "contracts" / "revit_handoff.json",
                    analysis["bim_handoff"])
        assets.append({
            "role": "revit_handoff_contract",
            "authority": "candidate",
            "path": "contracts/revit_handoff.json",
            "source_path": "inline:analysis.bim_handoff",
            "bytes": (destination / "contracts" / "revit_handoff.json").stat().st_size,
            "sha256": _sha256(destination / "contracts" / "revit_handoff.json"),
        })

    rhino, rhino_assets = _rhino_acceptance(
        payload, destination, rhino_3dm, rhino_manifest)
    assets.extend(rhino_assets)
    generated_at = payload.get("generated_at")
    try:
        generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise ValueError("demo generated_at is missing or invalid") from error
    bundle_sha256 = _bundle_signature(assets)
    version_id = (generated.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                  + f"-v{COMPILER_VERSION}-{_sha256(model_json)[:12]}-"
                  + bundle_sha256[:12])
    return {
        "schema_version": "mta.model_version/1.0",
        "version_id": version_id,
        "status": "archived_release",
        "generated_at": generated_at,
        "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "compiler_version": COMPILER_VERSION,
        "compiler_source_sha256": source_fingerprint,
        "bundle_sha256": bundle_sha256,
        "run_id": payload["run_id"],
        "v3_model_id": model_id,
        "v2_model_id": payload.get("building_model", {}).get("model_id"),
        "source_audio_sha256": payload.get("audio_features", {}).get("provenance", {}).get("sha256"),
        "authority": {
            "rhino": rhino,
            "blender": {
                "status": "available",
                "authority": "presentation_only",
                "owner": "blender",
                "purposes": ["rendering", "animation", "web_preview"],
            },
            "drawings": {
                "status": "candidate_preview",
                "authority": "candidate",
                "owner": "portable_drawing_compiler",
                "note": "These SVG sheets are not Rhino-issued drawings.",
            },
        },
        "assets": sorted(assets, key=lambda item: item["path"]),
    }


def _verify_recorded_assets(directory: Path, manifest: dict[str, Any]) -> int:
    for item in manifest["assets"]:
        path = directory / item["path"]
        if not path.is_file() or path.stat().st_size != item["bytes"] or _sha256(path) != item["sha256"]:
            raise ValueError(f"version asset is missing or stale: {path}")
    return len(manifest["assets"])


def _verify_bundle(directory: Path, manifest: dict[str, Any]) -> None:
    _verify_recorded_assets(directory, manifest)
    if manifest.get("bundle_sha256") != _bundle_signature(manifest["assets"]):
        raise ValueError("version asset inventory does not match its bundle hash")
    rhino = manifest["authority"]["rhino"]
    three_dm = list((directory / "rhino").glob("*.3dm"))
    if rhino["status"] == "accepted":
        if len(three_dm) != 1 or not (directory / "rhino" / "acceptance.json").is_file():
            raise ValueError("accepted Rhino release lacks its paired files")
    elif three_dm:
        raise ValueError("unaccepted release contains a Rhino design file")
    for required in (directory / "blender" / "scene_v3.blend",
                     directory / "blender" / "model_v3.glb"):
        if not required.is_file():
            raise ValueError(f"Blender presentation bundle is incomplete: {required}")


def _verify_matching_directories(source: Path, published: Path, label: str) -> None:
    source_files = {path.relative_to(source) for path in source.rglob("*") if path.is_file()}
    public_files = {path.relative_to(published) for path in published.rglob("*") if path.is_file()}
    if source_files != public_files:
        raise ValueError(f"public {label} inventory differs from latest")
    for relative in source_files:
        if _sha256(source / relative) != _sha256(published / relative):
            raise ValueError(f"public {label} is stale: {relative}")


def _verify_public_latest(manifest: dict[str, Any]) -> None:
    web_public = ROOT / "web" / "public"
    reports = web_public / "reports"
    models = web_public / "models" / "generated"
    public_demo = reports / "demo_run.json"
    public_payload = json.loads(public_demo.read_text(encoding="utf-8"))
    if public_payload.get("run_id") != manifest["run_id"]:
        raise ValueError("public demo run ID differs from latest")
    if public_payload.get("analysis", {}).get("model_id") != manifest["v3_model_id"]:
        raise ValueError("public demo model ID differs from latest")
    if _sha256(public_demo) != _sha256(LATEST / "contracts" / "demo_run.json"):
        raise ValueError("public demo contract differs from latest")
    for source, published in (
        (LATEST / "blender" / "model_v3.glb", models / "latest-v3.glb"),
        (LATEST / "blender" / "model_v3.manifest.json", models / "latest-v3.manifest.json"),
    ):
        if not published.is_file() or _sha256(source) != _sha256(published):
            raise ValueError(f"public Blender asset differs from latest: {published.name}")
    if (LATEST / "blender" / "model_v2.glb").is_file():
        for source, published in (
            (LATEST / "blender" / "model_v2.glb", models / "latest-v2.glb"),
            (LATEST / "blender" / "model_v2.manifest.json", models / "latest-v2.manifest.json"),
        ):
            if not published.is_file() or _sha256(source) != _sha256(published):
                raise ValueError(f"public Blender asset differs from latest: {published.name}")
    _verify_matching_directories(
        LATEST / "renders", web_public / "renders" / "latest", "renders")
    _verify_matching_directories(
        LATEST / "drawings" / "portable_preview",
        web_public / "drawings" / "latest", "drawings")
    translation = LATEST / "contracts" / "translation_report.json"
    if translation.is_file() and _sha256(translation) != _sha256(
            reports / "translation_report.json"):
        raise ValueError("public translation report differs from latest")
    allowed = {"latest-v3.glb", "latest-v3.manifest.json"}
    if (LATEST / "blender" / "model_v2.glb").is_file():
        allowed.update({"latest-v2.glb", "latest-v2.manifest.json"})
    extra = {path.name for path in models.iterdir() if path.is_file()} - allowed
    if extra:
        raise ValueError(f"deployment contains model-specific assets: {sorted(extra)}")


def _copy_latest(archive_dir: Path, manifest: dict[str, Any]) -> None:
    stage = VERSIONS / ".latest-next"
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(archive_dir, stage)
    latest_manifest = dict(manifest, status="latest_preview" if
                           manifest["authority"]["rhino"]["status"] != "accepted" else "latest_accepted")
    _write_json(stage / "manifest.json", latest_manifest)
    _verify_bundle(stage, latest_manifest)
    old = VERSIONS / ".latest-old"
    if old.exists():
        shutil.rmtree(old)
    if LATEST.exists():
        LATEST.replace(old)
    stage.replace(LATEST)
    if old.exists():
        shutil.rmtree(old)


def _replace_public_directory(source: Path, target: Path) -> None:
    stage = target.with_name(f".{target.name}-next")
    old = target.with_name(f".{target.name}-old")
    for path in (stage, old):
        if path.exists():
            shutil.rmtree(path)
    shutil.copytree(source, stage)
    if target.exists():
        target.replace(old)
    stage.replace(target)
    if old.exists():
        shutil.rmtree(old)


def _replace_public_file(source: Path, target: Path) -> None:
    temporary = target.with_name(f".{target.name}-next")
    if temporary.exists():
        temporary.unlink()
    shutil.copy2(source, temporary)
    temporary.replace(target)


def _publish_web_latest(payload: dict[str, Any], archive_dir: Path) -> None:
    """Update the deployment cache only after the archive bundle passed verification."""
    web_public = ROOT / "web" / "public"
    models = web_public / "models" / "generated"
    models.mkdir(parents=True, exist_ok=True)
    reports = web_public / "reports"
    stage = web_public / ".model-version-next"
    if stage.exists():
        shutil.rmtree(stage)
    try:
        stage_models = stage / "models"
        stage_reports = stage / "reports"
        stage_models.mkdir(parents=True)
        stage_reports.mkdir(parents=True)
        shutil.copy2(archive_dir / "blender" / "model_v3.glb",
                     stage_models / "latest-v3.glb")
        shutil.copy2(archive_dir / "blender" / "model_v3.manifest.json",
                     stage_models / "latest-v3.manifest.json")
        has_v2 = (archive_dir / "blender" / "model_v2.glb").is_file()
        if has_v2:
            shutil.copy2(archive_dir / "blender" / "model_v2.glb",
                         stage_models / "latest-v2.glb")
            shutil.copy2(archive_dir / "blender" / "model_v2.manifest.json",
                         stage_models / "latest-v2.manifest.json")
        shutil.copytree(archive_dir / "renders", stage / "renders")
        shutil.copytree(archive_dir / "drawings" / "portable_preview", stage / "drawings")
        _write_json(stage_reports / "demo_run.json", _stable_public_payload(payload))
        translation = archive_dir / "contracts" / "translation_report.json"
        if translation.is_file():
            shutil.copy2(translation, stage_reports / "translation_report.json")

        _replace_public_file(stage_models / "latest-v3.glb", models / "latest-v3.glb")
        _replace_public_file(stage_models / "latest-v3.manifest.json",
                             models / "latest-v3.manifest.json")
        if has_v2:
            _replace_public_file(stage_models / "latest-v2.glb", models / "latest-v2.glb")
            _replace_public_file(stage_models / "latest-v2.manifest.json",
                                 models / "latest-v2.manifest.json")
        _replace_public_directory(stage / "renders", web_public / "renders" / "latest")
        _replace_public_directory(stage / "drawings", web_public / "drawings" / "latest")
        _replace_public_file(stage_reports / "demo_run.json", reports / "demo_run.json")
        if translation.is_file():
            _replace_public_file(stage_reports / "translation_report.json",
                                 reports / "translation_report.json")
    finally:
        if stage.exists():
            shutil.rmtree(stage)

    # Deployment contains stable aliases only.  Versioned originals live in archive/.
    for root in (web_public / "renders", web_public / "drawings"):
        for child in root.iterdir():
            if child.is_dir() and child.name != "latest":
                shutil.rmtree(child)
    for pattern in ("building-v3-*.glb", "building-v3-*.manifest.json"):
        for path in models.glob(pattern):
            path.unlink()
    for asset in (payload.get("model_asset"), payload.get("model_asset_v3")):
        if not isinstance(asset, dict):
            continue
        for field in ("asset_url", "manifest_url"):
            source = _from_url(ROOT, asset[field])
            if source.parent == models.resolve() and not source.name.startswith("latest-"):
                source.unlink(missing_ok=True)


def publish(demo_path: Path = DEFAULT_DEMO, *, rhino_3dm: Path | None = None,
            rhino_manifest: Path | None = None) -> dict[str, Any]:
    demo_path = _inside(ROOT, demo_path)
    payload = json.loads(demo_path.read_text(encoding="utf-8"))
    scratch = VERSIONS / ".archive-next"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    manifest = _collect_bundle(payload, demo_path, scratch, rhino_3dm, rhino_manifest)
    _write_json(scratch / "manifest.json", manifest)
    _verify_bundle(scratch, manifest)
    archive_dir = ARCHIVE / manifest["version_id"]
    if archive_dir.exists():
        existing = json.loads((archive_dir / "manifest.json").read_text(encoding="utf-8"))
        if [(a["path"], a["sha256"]) for a in existing["assets"]] != [
                (a["path"], a["sha256"]) for a in manifest["assets"]]:
            raise ValueError(f"immutable archive already differs: {archive_dir}")
        shutil.rmtree(scratch)
        manifest = existing
    else:
        archive_dir.parent.mkdir(parents=True, exist_ok=True)
        scratch.replace(archive_dir)
    _publish_web_latest(payload, archive_dir)
    _copy_latest(archive_dir, manifest)
    pointer = {
        "schema_version": "mta.model_version_pointer/1.0",
        "version_id": manifest["version_id"],
        "manifest": f"archive/{manifest['version_id']}/manifest.json",
        "v3_model_id": manifest["v3_model_id"],
        "compiler_version": manifest["compiler_version"],
        "compiler_source_sha256": manifest["compiler_source_sha256"],
        "bundle_sha256": manifest["bundle_sha256"],
        "rhino_status": manifest["authority"]["rhino"]["status"],
        "blender_status": manifest["authority"]["blender"]["status"],
    }
    _write_json(VERSIONS / "latest.json", pointer)
    return pointer


def check() -> dict[str, Any]:
    pointer = json.loads((VERSIONS / "latest.json").read_text(encoding="utf-8"))
    archive_dir = VERSIONS / Path(pointer["manifest"]).parent
    archived = json.loads((archive_dir / "manifest.json").read_text(encoding="utf-8"))
    latest = json.loads((LATEST / "manifest.json").read_text(encoding="utf-8"))
    if len({archived["version_id"], latest["version_id"], pointer["version_id"]}) != 1:
        raise ValueError("latest pointer and manifests disagree")
    _verify_bundle(archive_dir, archived)
    _verify_bundle(LATEST, latest)
    archived_hashes = {(item["path"], item["sha256"]) for item in archived["assets"]}
    latest_hashes = {(item["path"], item["sha256"]) for item in latest["assets"]}
    if archived_hashes != latest_hashes:
        raise ValueError("latest files differ from their immutable archive")
    if latest.get("compiler_source_sha256") != compiler_source_fingerprint():
        raise ValueError("latest was generated by a different compiler source snapshot")
    _verify_public_latest(latest)
    archive_count = 0
    archive_asset_count = 0
    for directory in sorted(path for path in ARCHIVE.iterdir() if path.is_dir()):
        archive_manifest = json.loads(
            (directory / "manifest.json").read_text(encoding="utf-8"))
        archive_asset_count += _verify_recorded_assets(directory, archive_manifest)
        archive_count += 1
    return {
        "status": "passed",
        **pointer,
        "asset_count": len(latest["assets"]),
        "archive_count": archive_count,
        "archive_asset_count": archive_asset_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", type=Path, default=DEFAULT_DEMO)
    parser.add_argument("--rhino-3dm", type=Path)
    parser.add_argument("--rhino-manifest", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = check() if args.check else publish(
        args.demo, rhino_3dm=args.rhino_3dm, rhino_manifest=args.rhino_manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
