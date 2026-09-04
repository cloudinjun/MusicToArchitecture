import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_blender_scene_state_preserves_shared_model_contract() -> None:
    model = json.loads(
        (ROOT / "runtime/inbox/building_model_v2.json").read_text(encoding="utf-8-sig")
    )
    state = json.loads(
        (ROOT / "artifacts/native_models/blender_scene_state.json").read_text(
            encoding="utf-8"
        )
    )

    expected = {element["id"]: element for element in model["elements"]}
    actual = {
        obj["element_id"]: obj
        for obj in state["objects"]
        if obj.get("source_element") and obj.get("element_id") is not None
    }

    assert state["schema_version"] == model["schema_version"] == "2.0"
    assert state["model_id"] == model["model_id"]
    assert state["source_object_count"] == len(expected)
    assert state["exportable_object_count"] > len(expected)
    assert actual.keys() == expected.keys()

    for element_id, element in expected.items():
        obj = actual[element_id]
        assert obj["kind"] == element["kind"]
        assert obj["location"] == [
            element["position"][axis] for axis in ("x", "y", "z")
        ]
        if not element.get("rotation"):
            assert obj["dimensions"] == pytest.approx([
                element["dimensions"][axis] for axis in ("x", "y", "z")
            ], abs=1e-4)


def test_blender_web_asset_has_semantic_architectural_layers() -> None:
    manifest = json.loads(
        (ROOT / "web/public/models/demo/library-pavilion.manifest.json").read_text(
            encoding="utf-8"
        )
    )
    glb_path = ROOT / "web/public/models/demo/library-pavilion.glb"

    assert glb_path.stat().st_size > 10_000
    assert manifest["producer"] == "Blender 5.0 semantic adapter"
    assert manifest["layers"]["structure"] == [
        "columns", "beams", "slabs", "foundations", "bracing", "cores"
    ]
    assert manifest["layers"]["program"] == [
        "program_massing", "site", "site_context", "context_tree",
        "context_vehicle", "context_person",
    ]
    assert manifest["program_category_counts"] == {
        "circulation": 3,
        "private": 2,
        "public": 8,
        "service": 8,
    }
    assert manifest["subsystem_counts"] == {
        "beams": 58,
        "bracing": 4,
        "columns": 35,
        "context_person": 16,
        "context_tree": 12,
        "context_vehicle": 12,
        "cores": 3,
        "facade": 299,
        "foundations": 35,
        "interior_sequence": 11,
        "program_massing": 21,
        "site": 1,
        "site_context": 3,
        "slabs": 5,
    }
    assert manifest["context_counts"] == {
        "person": 4,
        "site_feature": 3,
        "tree": 6,
        "vehicle": 2,
    }
    assert manifest["object_count"] == 515
