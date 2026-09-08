"""Small contract tests for saved-study candidate delivery.

The real drawing, Rhino, and Blender adapters are deliberately kept out of this
module.  These tests exercise the delivery coordinator with a tiny model and
fake stage functions so that failure isolation and source identity remain cheap
to verify.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.scripts import package_candidate_study as delivery


class _Dumpable:
    def __init__(self, payload):
        self.payload = payload

    def model_dump(self, *, mode="json"):
        return self.payload


class _FakeModel:
    def __init__(self, model_id="model-a"):
        self.model_id = model_id
        self.lattice = SimpleNamespace(cutaway=False)
        self.program_volume_model = _Dumpable({"model_id": model_id})
        self.spatial = _Dumpable({"status": "fixture"})
        self.dependency_graph = _Dumpable({"edges": []})
        self.limitations = ["fixture"]


class _FakeBuildingModel:
    @classmethod
    def model_validate_json(cls, raw):
        return _FakeModel(json.loads(raw)["model_id"])


def _write_study(tmp_path: Path, *, evidence_model_id="model-a", fingerprint="source-fp"):
    study = tmp_path / "study"
    study.mkdir()
    (study / "building_model_v3.json").write_text(
        json.dumps({"model_id": "model-a"}), encoding="utf-8")
    (study / "building_result.json").write_text(json.dumps({
        "status": "building_compiled_pending_review",
        "source_unchanged": True,
        "model_id": evidence_model_id,
        "compiler_source_fingerprint": fingerprint,
    }), encoding="utf-8")
    return study


def _install_fake_reader(monkeypatch, study: Path, *, model=None, fingerprint="source-fp"):
    model = model or _FakeModel()
    source = (study / "building_model_v3.json").resolve()
    evidence = (study / "building_result.json").resolve()
    monkeypatch.setattr(delivery, "compiler_source_fingerprint", lambda: fingerprint)

    def fake_reader(_study):
        return model, fingerprint, {
            source: delivery.digest(source),
            evidence: delivery.digest(evidence),
        }

    monkeypatch.setattr(delivery, "read_study", fake_reader)
    return model


@pytest.mark.parametrize(
    ("evidence_model_id", "fingerprint", "message"),
    [
        ("other-model", "source-fp", "does not identify this model"),
        ("model-a", "stale-source-fp", "different compiler/exporter source"),
    ],
)
def test_read_study_identity_rejection_happens_before_any_export(
    monkeypatch, tmp_path, evidence_model_id, fingerprint, message
):
    """A stale saved study cannot create even a partial delivery directory."""
    study = _write_study(
        tmp_path, evidence_model_id=evidence_model_id, fingerprint=fingerprint)
    monkeypatch.setattr(delivery, "BuildingModelV3", _FakeBuildingModel)
    monkeypatch.setattr(delivery, "compiler_source_fingerprint", lambda: "source-fp")
    called = []
    monkeypatch.setattr(
        delivery,
        "EXPORTERS",
        {"drawings": lambda *_args: called.append("drawings")},
    )

    with pytest.raises(ValueError, match=message):
        delivery.package(study, tmp_path / "delivery")

    assert called == []
    assert not (tmp_path / "delivery").exists()


def test_existing_destination_is_refused_before_export(monkeypatch, tmp_path):
    study = _write_study(tmp_path)
    _install_fake_reader(monkeypatch, study)
    destination = tmp_path / "already-there"
    destination.mkdir()
    called = []
    monkeypatch.setattr(
        delivery,
        "EXPORTERS",
        {"drawings": lambda *_args: called.append("drawings")},
    )

    with pytest.raises(FileExistsError):
        delivery.package(study, destination)

    assert called == []
    assert list(destination.iterdir()) == []


def test_failed_drawings_do_not_block_rhino_or_upgrade_acceptance(monkeypatch, tmp_path):
    study = _write_study(tmp_path)
    _install_fake_reader(monkeypatch, study)
    called = []

    def drawings(*_args):
        called.append("drawings")
        raise RuntimeError("drawing projection unavailable")

    def rhino(*_args):
        called.append("rhino")
        return {"status": "geometry_candidate"}

    def blender(*_args):
        called.append("blender")
        return {"status": "should-not-run"}

    monkeypatch.setattr(
        delivery,
        "EXPORTERS",
        {"drawings": drawings, "rhino": rhino, "blender": blender},
    )
    report = delivery.package(study, tmp_path / "delivery")

    assert called == ["drawings", "rhino"]
    assert report["status"] == "export_failed"
    assert report["stages"]["drawings"]["status"] == "failed"
    assert report["stages"]["drawings"]["error"] == "drawing projection unavailable"
    assert report["stages"]["rhino"]["status"] == "exported"
    assert report["rhino_acceptance"] == "not_recorded"
    assert report["candidate_selection"] == "not_performed"


def test_blender_defaults_to_not_requested_and_is_never_called(monkeypatch, tmp_path):
    study = _write_study(tmp_path)
    _install_fake_reader(monkeypatch, study)
    called = []

    def stage(name):
        def run(*_args):
            called.append(name)
            return {"status": "ok"}
        return run

    monkeypatch.setattr(
        delivery,
        "EXPORTERS",
        {"drawings": stage("drawings"), "rhino": stage("rhino"),
         "blender": stage("blender")},
    )
    report = delivery.package(study, tmp_path / "delivery")

    assert called == ["drawings", "rhino"]
    assert report["stages"]["blender"] == {"status": "not_requested"}
    assert report["status"] == "exported_pending_review"


def test_source_mutation_invalidates_and_stops_before_next_stage(monkeypatch, tmp_path):
    study = _write_study(tmp_path)
    _install_fake_reader(monkeypatch, study)
    called = []
    source = study / "building_model_v3.json"

    def drawings(*_args):
        called.append("drawings")
        source.write_text("mutated during export", encoding="utf-8")
        return {"status": "ok"}

    def rhino(*_args):
        called.append("rhino")
        return {"status": "should-not-run"}

    monkeypatch.setattr(
        delivery,
        "EXPORTERS",
        {"drawings": drawings, "rhino": rhino},
    )
    destination = tmp_path / "delivery"

    with pytest.raises(RuntimeError, match="Source changed during delivery"):
        delivery.package(study, destination)

    saved = json.loads((destination / "delivery.json").read_text(encoding="utf-8"))
    assert called == ["drawings"]
    assert saved["status"] == "invalidated_source_changed"
    assert saved["source_unchanged"] is False
    assert saved["stages"]["drawings"]["status"] == "exported"
    assert saved["stages"]["rhino"]["status"] == "pending"
