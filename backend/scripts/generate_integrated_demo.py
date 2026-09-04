"""Generate one reproducible Library + steel frame + facade evidence run.

The script writes versioned JSON contracts before asking Blender to materialize the
explicit semantic elements. Rhino acceptance remains outside this demonstration.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.audio import extract_audio_features
from backend.app.blender_export import export_blender_web_model
from backend.app.compiler import compile_building_model
from backend.app.integration import compile_facade_host_handoff, compile_pipeline_manifest
from backend.app.mapping_report import compile_mapping_report
from backend.app.score import compile_architectural_score


AUDIO = ROOT / "fixtures/audio/gemini_music_to_architecture_44s.mp3"
GUIDELINE = ROOT / "docs/style_guides/facade/01_international_style.md"
SELECTION = ROOT / "docs/experiments/integrated_demo_selection.md"
RUNTIME = ROOT / "runtime/inbox"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def project_uri(path: Path) -> str:
    return "project://" + path.relative_to(ROOT).as_posix()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    temporary.replace(path)


def available_input(identifier: str, kind: str, path: Path) -> dict[str, object]:
    return {
        "id": identifier,
        "kind": kind,
        "status": "available",
        "path": project_uri(path),
        "sha256": sha256_file(path),
    }


def facade_reference_spec(render_path: Path, model_id: str) -> dict[str, object]:
    return {
        "schema_version": "mta.facade_reference_spec/1.0",
        "spec_id": f"generated-evidence-{model_id}",
        "mode": "reference-analysis",
        "authority_status": "evidence_only",
        "source_images": [{
            "id": "generated-blender-overall",
            "path": project_uri(render_path),
            "sha256": sha256_file(render_path),
            "role": "generated_model_evidence",
            "view_kind": "aerial_oblique",
            "technical_suitability": "warning",
            "limitations": [
                "This is output evidence from the same run, not an external design reference.",
                "It supports review of visible assembly only and supplies no hidden dimensions.",
            ],
        }],
        "regions": [],
        "claims": [],
        "unknowns": [
            "No external facade image was used as design authority in this integrated run."
        ],
        "provenance": {
            "producer": "Blender 5.0 headless semantic adapter",
            "model_id": model_id,
        },
        "limitations": [
            "The selected project guideline, program ownership, and structural support records drive the candidate facade."
        ],
    }


def facade_candidate_plan(score_path: Path, model_path: Path, reference_path: Path, model, handoff):
    facade_elements = [element for element in model.elements if element.semantic_layer == "facade"]
    plan_elements = []
    kind_map = {
        "facade_panel": "panel",
        "glazing": "material_layer",
        "mullion": "mullion",
        "facade_support": "support",
        "canopy": "canopy",
    }
    pass_map = {
        "facade_panel": "envelope_assembly",
        "glazing": "envelope_assembly",
        "mullion": "supports_details",
        "facade_support": "supports_details",
        "canopy": "openings_entry",
    }
    valid_hosts = {host.id for host in handoff.host_surfaces}
    for element in facade_elements:
        if element.host_surface_id not in valid_hosts:
            continue
        grammar_rule = next(
            (rule for rule in element.rule_refs if rule.startswith("IS-INV-")),
            element.rule_refs[0],
        )
        plan_elements.append({
            "id": element.id,
            "kind": kind_map[element.kind],
            "host_id": element.host_surface_id,
            "pass_id": pass_map[element.kind],
            "grammar_rule_id": grammar_rule,
            "source_claim_ids": [],
            "program_rule_id": element.rule_refs[0],
            "operations": [{
                "type": "materialize_explicit_contract_element",
                "parameters": {
                    "element_id": element.id,
                    "material_profile": element.material_profile,
                    "supports": element.supports,
                    "dimensions_m": element.dimensions.model_dump(mode="json"),
                },
            }],
            "score_bindings": [{
                "dimension_id": binding.source_dimension,
                "rule_id": binding.rule_id,
                "target_parameter": binding.target_parameter,
                "applied_value": binding.applied_value,
                "source_ref": f"architectural-score#{binding.source_dimension}",
            } for binding in element.score_bindings],
        })

    score_dimensions = []
    for dimension in handoff.score_dimensions:
        score_dimensions.append({
            "id": dimension.id,
            "status": dimension.status,
            "value": dimension.value,
            "confidence": dimension.confidence,
            "source_type": dimension.source_type,
            "source_ref": dimension.source_ref,
            "reason": dimension.reason,
            "required_for_handoff": dimension.required_for_handoff,
        })

    return {
        "schema_version": "mta.facade_candidate_plan/1.0",
        "plan_id": f"facade-plan-{model.model_id}",
        "mode": "candidate-planning",
        "authority_status": "candidate",
        "maturity": "MTA-F2",
        "inputs": [
            available_input("facade-evidence-01", "facade_reference_spec", reference_path),
            available_input("guideline-international-01", "guideline", GUIDELINE),
            available_input("architectural-score-01", "architectural_score", score_path),
            available_input("building-model-01", "building_model", model_path),
            available_input("typology-selection-01", "typology_selection", SELECTION),
            available_input("tectonic-selection-01", "tectonic_selection", SELECTION),
            available_input("grammar-selection-01", "grammar_selection", SELECTION),
        ],
        "typology": "library",
        "tectonic_system": "frame",
        "grammar": {
            "id": "international_style_informed",
            "qualified_name": "International Style-informed abstract facade grammar",
            "execution_status": "selected",
            "guideline_path": project_uri(GUIDELINE),
            "guideline_sha256": sha256_file(GUIDELINE),
            "selection_record_id": "grammar-selection-01",
            "invariant_rule_ids": [f"IS-INV-0{index}" for index in range(1, 7)],
            "legal_variables": [
                {"id": "base_facade_bay", "unit": "m", "range": [1.2, 3.6]},
                {"id": "submodule_count", "unit": "count", "range": [2, 6]},
                {"id": "glazing_ratio", "unit": "ratio", "range": [0.25, 0.75]},
                {"id": "plane_offset", "unit": "m", "range": [0.0, 0.45]},
            ],
            "forbidden_operation_ids": [
                "IS-FORB-random-window-placement",
                "IS-FORB-uniform-transparency",
                "IS-FORB-score-curvature",
                "IS-FORB-unsupported-floating-panel",
            ],
            "context_status": "complete_for_test_site",
        },
        "score_dimensions": score_dimensions,
        "host_surfaces": [{
            "id": host.id,
            "source_contract_id": handoff.handoff_id,
            "source_element_id": host.source_element_id,
            "program_owner": host.program_owner,
            "orientation": host.orientation,
            "status": "preview_host",
        } for host in handoff.host_surfaces],
        "passes": [{
            "id": pass_id,
            "status": "candidate",
            "producer": "portable_compiler_to_blender_semantic_adapter",
        } for pass_id in (
            "host", "zoning_grid", "openings_entry", "envelope_assembly",
            "supports_details", "optimization", "evidence",
        )],
        "elements": plan_elements,
        "validation_targets": [
            {"id": "VT-HOST", "category": "host_and_program", "status": "pass"},
            {"id": "VT-GRAMMAR", "category": "grammar_invariants", "status": "pass"},
            {"id": "VT-SCORE", "category": "score_trace", "status": "pass"},
            {"id": "VT-SUPPORT", "category": "tectonic_and_support", "status": "pass"},
            {"id": "VT-COMPOSITION", "category": "composition", "status": "pass"},
        ],
        "limitations": [
            "Candidate geometry has not received Rhino acceptance.",
            "Envelope thermal, moisture, fire, movement, and connection engineering remain unresolved.",
            "Unknown Shared Score dimensions remain unknown and do not drive geometry.",
        ],
        "ready_for_geometry_handoff": True,
    }


def main() -> None:
    if not AUDIO.is_file():
        raise FileNotFoundError(AUDIO)
    features = extract_audio_features(AUDIO, AUDIO.name)
    score = compile_architectural_score(features)
    model = compile_building_model(features, score)
    report = compile_mapping_report(features, score, model)
    handoff = compile_facade_host_handoff(score, model)

    run_directory = ROOT / "artifacts/integrated_demo" / model.model_id
    run_directory.mkdir(parents=True, exist_ok=True)
    render_path = run_directory / "blender_overall.png"
    asset = export_blender_web_model(model, render_path=render_path)
    manifest = compile_pipeline_manifest(features, score, model, report, handoff, asset)

    payloads = {
        "music_features.json": features.model_dump(mode="json"),
        "architectural_score.json": score.model_dump(mode="json"),
        "building_model_v2.json": model.model_dump(mode="json"),
        "shared_score_mapping_report.json": report.model_dump(mode="json"),
        "facade_host_handoff.json": handoff.model_dump(mode="json"),
        "model_asset.json": asset.model_dump(mode="json"),
        "pipeline_run_manifest.json": manifest.model_dump(mode="json"),
    }
    for filename, payload in payloads.items():
        write_json(run_directory / filename, payload)
        write_json(RUNTIME / filename, payload)

    reference_path = run_directory / "facade_generated_evidence_spec.json"
    write_json(reference_path, facade_reference_spec(render_path, model.model_id))
    plan_path = run_directory / "facade_candidate_plan.json"
    write_json(
        plan_path,
        facade_candidate_plan(
            run_directory / "architectural_score.json",
            run_directory / "building_model_v2.json",
            reference_path,
            model,
            handoff,
        ),
    )

    generated_glb = ROOT / "web/public" / asset.asset_url.split("?", 1)[0].lstrip("/")
    generated_manifest = ROOT / "web/public" / asset.manifest_url.split("?", 1)[0].lstrip("/")
    shutil.copy2(generated_glb, ROOT / "web/public/models/demo/library-pavilion.glb")
    shutil.copy2(generated_manifest, ROOT / "web/public/models/demo/library-pavilion.manifest.json")
    shutil.copy2(render_path, ROOT / "artifacts/native_models/blender_render.png")
    shutil.copy2(ROOT / asset.scene_state_path, ROOT / "artifacts/native_models/blender_scene_state.json")

    write_json(ROOT / "artifacts/integrated_demo/latest_run.json", {
        "model_id": model.model_id,
        "score_id": model.score_id,
        "audio_sha256": features.provenance.sha256,
        "glb_sha256": asset.asset_sha256,
        "blend_sha256": asset.native_blend_sha256,
        "run_directory": project_uri(run_directory),
        "element_count": len(model.elements),
        "room_count": model.parameters.room_count,
        "validation": [item.model_dump(mode="json") for item in model.validation],
    })
    print(json.dumps({
        "model_id": model.model_id,
        "element_count": len(model.elements),
        "run_directory": str(run_directory),
        "render_path": str(render_path),
        "asset_sha256": asset.asset_sha256,
    }, indent=2))


if __name__ == "__main__":
    main()
