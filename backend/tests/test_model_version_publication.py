from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.version import compiler_source_fingerprint
from backend.scripts import publish_model_version as versions


ROOT = Path(__file__).resolve().parents[2]


def test_latest_bundle_matches_immutable_archive() -> None:
    result = versions.check()
    assert result["status"] == "passed"
    assert result["asset_count"] > 0
    assert result["compiler_source_sha256"] == compiler_source_fingerprint()


def test_public_demo_uses_only_stable_version_urls() -> None:
    payload = json.loads(
        (ROOT / "web/public/reports/demo_run.json").read_text(encoding="utf-8"))
    assert payload["model_asset_v3"]["asset_url"] == "/models/generated/latest-v3.glb"
    assert payload["model_asset_v3"]["manifest_url"] == "/models/generated/latest-v3.manifest.json"
    assert all(item["url"].startswith("/renders/latest/") for item in payload["renders"])
    assert all(item["url"].startswith("/drawings/latest/")
               for item in payload["drawing_sheets"])
    assert not (ROOT / "web/public/reports/demo_candidate.json").exists()
    assert not (ROOT / "web/public/reports/translation_report_candidate.json").exists()


def test_candidate_and_public_urls_have_one_canonical_contract() -> None:
    candidate = {
        "model_asset_v3": {"asset_url": "/models/generated/model-a.glb",
                           "manifest_url": "/models/generated/model-a.manifest.json"},
        "model_asset": {"asset_url": "/models/generated/model-v2.glb",
                        "manifest_url": "/models/generated/model-v2.manifest.json"},
        "renders": [{"filename": "hero.png", "url": "/renders/model-a/hero.png"}],
        "drawing_sheets": [{"id": "A-101", "url": "/drawings/model-a/A-101.svg"}],
        "pipeline_manifest": {"artifacts": [
            {"id": "blender-glb", "uri": "/models/generated/model-v2.glb"},
            {"id": "blender-manifest", "uri": "/models/generated/model-v2.manifest.json"},
        ]},
    }
    public = json.loads(json.dumps(candidate))
    public["model_asset_v3"]["asset_url"] = "/models/generated/latest-v3.glb"
    public["renders"][0]["url"] = "/renders/latest/hero.png"
    public["drawing_sheets"][0]["url"] = "/drawings/latest/A-101.svg"
    assert versions._stable_public_payload(candidate) == versions._stable_public_payload(public)


def test_blocked_rhino_slot_contains_no_design_file() -> None:
    manifest = json.loads(
        (ROOT / "artifacts/model_versions/latest/manifest.json").read_text(encoding="utf-8"))
    rhino = manifest["authority"]["rhino"]
    assert (ROOT / "artifacts/model_versions/latest/blender/scene_v3.blend").is_file()
    assert (ROOT / "artifacts/model_versions/latest/blender/model_v3.glb").is_file()
    if rhino["status"] == "blocked":
        assert not list((ROOT / "artifacts/model_versions/latest/rhino").glob("*.3dm"))
        assert rhino["files"] == []


def test_visual_measurement_is_bound_to_the_latest_model() -> None:
    base = ROOT / "artifacts/model_versions/latest"
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((base / "contracts/visual_geometry_measurement.json").read_text(
        encoding="utf-8"))
    assert report["model_id"] == manifest["v3_model_id"]
    assert {item["class"] for item in report["checks"]} == {
        "primitive_invalid_plan_ring",
        "stair_head_clearance",
        "stair_tread_floor_slab_intersection",
        "stair_tread_elevator_shaft_intersection",
        "stair_intercore_tread_volume_intersection",
        "program_zone_positive_overlap",
        "landing_slab_contact",
    }
    assert any(item["unevaluated_count"] for item in report["checks"])


def test_rhino_acceptance_requires_exact_run_model_and_hash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(versions, "ROOT", tmp_path)
    model = tmp_path / "candidate.3dm"
    model.write_bytes(b"rhino fixture")
    acceptance = tmp_path / "acceptance.json"
    payload = {"run_id": "run-a", "analysis": {"model_id": "model-a"}}

    acceptance.write_text(json.dumps({
        "status": "accepted",
        "authority": "accepted_geometry",
        "run_id": "run-old",
        "model_id": "model-a",
        "geometry_sha256": versions._sha256(model),
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match this run"):
        versions._rhino_acceptance(payload, tmp_path / "bad", model, acceptance)

    acceptance.write_text(json.dumps({
        "status": "accepted",
        "authority": "accepted_geometry",
        "run_id": "run-a",
        "model_id": "model-a",
        "geometry_sha256": versions._sha256(model),
    }), encoding="utf-8")
    status, assets = versions._rhino_acceptance(
        payload, tmp_path / "good", model, acceptance)
    assert status["status"] == "accepted"
    assert {asset["path"] for asset in assets} == {
        "rhino/model.3dm", "rhino/acceptance.json"}


def test_current_surfaces_do_not_cite_superseded_demo_model() -> None:
    stale_id = "building-v3-c64269ebc1a8"
    assert stale_id not in (ROOT / "README.md").read_text(encoding="utf-8")
    assert stale_id not in (
        ROOT / "web/public/reports/demo_run.json").read_text(encoding="utf-8")


def test_historical_rhino_file_is_not_an_active_design_source() -> None:
    assert not (ROOT / "rhino/MusicToArchitecture_Gemini_SmokeTest.3dm").exists()
    assert (ROOT / "artifacts/model_versions/archive/"
            "20260827T062803Z-rhino-smoke-unversioned/rhino/model.3dm").is_file()
