"""Aggregate quantitative geometry and pipeline evidence for a music audit batch.

The geometry verdicts come only from :func:`measure` and this module never writes a
visual review verdict.  A batch row without a compiled model stays ``unevaluated``;
its counts are ``null`` rather than invented zeros.

Usage::

    python -m backend.scripts.summarize_visual_music_audit \
        artifacts/visual_audit/2026-09-03/final-frozen \
        --compare-dir artifacts/visual_audit/2026-09-03/baseline-frozen
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from backend.scripts.measure_visual_geometry import measure
except ModuleNotFoundError:  # Support ``python backend/scripts/...py`` as well as -m.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from backend.scripts.measure_visual_geometry import measure


CHECK_CLASSES = (
    "primitive_invalid_plan_ring",
    "stair_head_clearance",
    "stair_tread_floor_slab_intersection",
    "stair_tread_elevator_shaft_intersection",
    "stair_intercore_tread_volume_intersection",
    "program_zone_positive_overlap",
    "landing_slab_contact",
)
SPATIAL_REPORT_LIMIT = 40
ENTRY_LANDING_ID = "CIR-LND-ENTRY"


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    partial.replace(path)


def _resolve_path(project_root: Path, audit_dir: Path, raw_path: Any) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path:
        return None
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    for base in (project_root, audit_dir):
        resolved = base / candidate
        if resolved.exists():
            return resolved
    return project_root / candidate


def _model_path(project_root: Path, audit_dir: Path, result: Mapping[str, Any]) -> Path | None:
    evidence = result.get("evidence")
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        return None
    for item in evidence:
        if not isinstance(item, Mapping):
            continue
        raw_path = item.get("path")
        if isinstance(raw_path, str) and raw_path.endswith("building_model_v3.json"):
            candidate = _resolve_path(project_root, audit_dir, raw_path)
            if candidate is not None:
                return candidate
    return None


def _result_response(audit_dir: Path, result: Mapping[str, Any]) -> Mapping[str, Any] | None:
    track_id = result.get("track_id")
    if not isinstance(track_id, str):
        return None
    path = audit_dir / "tracks" / track_id / "response.json"
    if not path.is_file():
        return None
    value = _read_json(path)
    return value if isinstance(value, Mapping) else None


def _source_fingerprints(
    response: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    audio_features = response.get("audio_features") if response is not None else None
    architectural_score = response.get("architectural_score") if response is not None else None
    audio_provenance = audio_features.get("provenance") if isinstance(audio_features, Mapping) else None
    source_audio_sha = (
        audio_provenance.get("sha256")
        if isinstance(audio_provenance, Mapping)
        else None
    )
    if source_audio_sha is None and isinstance(result, Mapping):
        source_audio_sha = result.get("audio_sha256")
    score_audio_sha = (
        architectural_score.get("source_audio_sha256")
        if isinstance(architectural_score, Mapping)
        else None
    )
    return {
        "audio_features_canonical_sha256": (
            _canonical_sha256(audio_features)
            if isinstance(audio_features, Mapping)
            else None
        ),
        "architectural_score_canonical_sha256": (
            _canonical_sha256(architectural_score)
            if isinstance(architectural_score, Mapping)
            else None
        ),
        "audio_features_source_audio_sha256": source_audio_sha,
        "architectural_score_source_audio_sha256": score_audio_sha,
        "canonicalization": "JSON sort_keys=true, compact separators, UTF-8, SHA-256",
    }


def _ordered_unique(values: Sequence[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        item = str(value)
        if item not in seen:
            seen.add(item)
            output.append(item)
    return output


def _instances_by_kind(model: Mapping[str, Any], kind: str) -> list[Mapping[str, Any]] | None:
    groups = model.get("element_groups")
    if not isinstance(groups, Sequence) or isinstance(groups, (str, bytes)):
        return None
    instances: list[Mapping[str, Any]] = []
    found_group = False
    for group in groups:
        if not isinstance(group, Mapping) or group.get("kind") != kind:
            continue
        found_group = True
        raw_instances = group.get("instances")
        if not isinstance(raw_instances, Sequence) or isinstance(raw_instances, (str, bytes)):
            return None
        instances.extend(item for item in raw_instances if isinstance(item, Mapping))
    return instances if found_group else []


def _occupied_level_ids(model: Mapping[str, Any]) -> list[str] | None:
    lattice = model.get("lattice")
    levels = lattice.get("levels") if isinstance(lattice, Mapping) else None
    if not isinstance(levels, Sequence) or isinstance(levels, (str, bytes)):
        return None
    occupied: list[str] = []
    for level in levels:
        if isinstance(level, Mapping) and level.get("kind") == "occupied" and level.get("id") is not None:
            occupied.append(str(level["id"]))
    return _ordered_unique(occupied)


def _level_coverage(
    model: Mapping[str, Any],
    *,
    kind: str,
    exclude_id: str | None = None,
    label: str,
) -> dict[str, Any]:
    occupied = _occupied_level_ids(model)
    instances = _instances_by_kind(model, kind)
    if occupied is None or instances is None:
        return {
            "status": "unevaluated",
            "context_only": True,
            "occupied_level_ids": occupied,
            "emitted_level_ids": None,
            "missing_occupied_level_ids": None,
            "emitted_level_ids_outside_occupied": None,
            "emitted_count": None,
            "emitted_count_by_level": None,
            "excluded_instance_id": exclude_id,
        }
    emitted_instances = [
        item for item in instances
        if exclude_id is None or item.get("id") != exclude_id
    ]
    emitted_values = [item.get("level_id") for item in emitted_instances]
    emitted = _ordered_unique(emitted_values)
    occupied_set = set(occupied)
    emitted_set = set(emitted)
    counts = Counter(str(value) for value in emitted_values if value is not None)
    return {
        "status": "measured",
        "context_only": True,
        "label": label,
        "occupied_level_ids": occupied,
        "emitted_level_ids": emitted,
        "missing_occupied_level_ids": [level for level in occupied if level not in emitted_set],
        "emitted_level_ids_outside_occupied": [level for level in emitted if level not in occupied_set],
        "occupied_count": len(occupied),
        "emitted_count": len(emitted),
        "emitted_instance_count": len(emitted_instances),
        "emitted_count_by_level": dict(sorted(counts.items())),
        "excluded_instance_id": exclude_id,
    }


def _program_context(model: Mapping[str, Any]) -> dict[str, Any]:
    allocation = model.get("program_allocation")
    if not isinstance(allocation, Mapping):
        return {
            "status": "unevaluated",
            "context_only": True,
            "unplaced_count": None,
            "unplaced_space_ids": None,
        }
    unplaced = allocation.get("unplaced")
    if not isinstance(unplaced, Sequence) or isinstance(unplaced, (str, bytes)):
        return {
            "status": "unevaluated",
            "context_only": True,
            "unplaced_count": None,
            "unplaced_space_ids": None,
        }
    ids = [
        item.get("space_id")
        if isinstance(item, Mapping)
        else None
        for item in unplaced
    ]
    return {
        "status": "measured",
        "context_only": True,
        "unplaced_count": len(unplaced),
        "unplaced_space_ids": _ordered_unique([item for item in ids if item is not None]),
    }


def _spatial_context(model: Mapping[str, Any]) -> dict[str, Any]:
    spatial = model.get("spatial")
    if not isinstance(spatial, Mapping):
        return {
            "status": "unevaluated",
            "context_only": True,
            "rule_counts_uncapped": None,
            "rule_count_total_uncapped": None,
            "severity_counts_reported": None,
            "severity_counts_complete": None,
            "reported_finding_count": None,
            "reported_finding_limit": SPATIAL_REPORT_LIMIT,
            "reported_findings_capped": None,
        }
    raw_counts = spatial.get("counts")
    rule_counts: dict[str, int] | None = None
    if isinstance(raw_counts, Mapping):
        try:
            rule_counts = {
                str(key): int(value)
                for key, value in raw_counts.items()
            }
        except (TypeError, ValueError):
            rule_counts = None
    findings = spatial.get("findings")
    reported_count = len(findings) if isinstance(findings, Sequence) and not isinstance(findings, (str, bytes)) else None
    severity = Counter()
    if isinstance(findings, Sequence) and not isinstance(findings, (str, bytes)):
        for finding in findings:
            if isinstance(finding, Mapping):
                severity[str(finding.get("severity", "unknown"))] += 1
            else:
                severity["unknown"] += 1
    total_uncapped = sum(rule_counts.values()) if rule_counts is not None else None
    capped = (
        total_uncapped > reported_count
        if total_uncapped is not None and reported_count is not None
        else None
    )
    return {
        "status": spatial.get("status"),
        "context_only": True,
        "rule_counts_uncapped": dict(sorted(rule_counts.items())) if rule_counts is not None else None,
        "rule_count_total_uncapped": total_uncapped,
        "severity_counts_reported": dict(sorted(severity.items())) if reported_count is not None else None,
        "severity_counts_complete": False if capped else (True if capped is False else None),
        "reported_finding_count": reported_count,
        "reported_finding_limit": SPATIAL_REPORT_LIMIT,
        "reported_findings_capped": capped,
        "severity_count_note": (
            "Severity counts come from spatial.findings, whose display is capped; "
            "spatial.counts is the uncapped per-rule count."
        ),
    }


def _v2_asset_context(response: Mapping[str, Any] | None) -> dict[str, Any]:
    if response is None or "model_asset" not in response:
        return {
            "status": "unknown",
            "available": None,
            "asset_url": None,
            "asset_sha256": None,
            "reason": "response.json or response.model_asset is unavailable",
        }
    asset = response.get("model_asset")
    if not isinstance(asset, Mapping):
        return {
            "status": "missing",
            "available": False,
            "asset_url": None,
            "asset_sha256": None,
            "reason": "response.model_asset is null",
        }
    asset_url = asset.get("asset_url")
    available = isinstance(asset_url, str) and bool(asset_url)
    return {
        "status": "available" if available else "missing",
        "available": available,
        "asset_url": asset_url if isinstance(asset_url, str) else None,
        "asset_sha256": asset.get("asset_sha256"),
        "manifest_url": asset.get("manifest_url"),
        "reason": None if available else "response.model_asset has no asset_url",
    }


def _checks_by_class(report: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    raw_checks = report.get("checks")
    if not isinstance(raw_checks, Sequence) or isinstance(raw_checks, (str, bytes)):
        raise ValueError(f"measurement report for {report.get('model_id')} has no checks list")
    by_class = {item.get("class"): item for item in raw_checks if isinstance(item, Mapping)}
    if set(by_class) != set(CHECK_CLASSES):
        raise ValueError(
            f"Unexpected check classes for {report.get('model_id')}: {sorted(by_class)}"
        )
    return {
        name: {
            "count": int(by_class[name]["count"]),
            "evaluated_count": int(by_class[name]["evaluated_count"]),
            "unevaluated_count": int(by_class[name]["unevaluated_count"]),
        }
        for name in CHECK_CLASSES
    }


def _unevaluated_checks() -> dict[str, dict[str, Any]]:
    return {
        name: {
            "count": None,
            "evaluated_count": None,
            "unevaluated_count": None,
            "status": "unevaluated",
        }
        for name in CHECK_CLASSES
    }


def _failure_reason(audit_dir: Path, result: Mapping[str, Any]) -> str:
    error = result.get("error")
    if isinstance(error, str) and error:
        return error
    track_id = result.get("track_id")
    if isinstance(track_id, str):
        failure_path = audit_dir / "tracks" / track_id / "failure.txt"
        if failure_path.is_file():
            text = failure_path.read_text(encoding="utf-8", errors="replace").strip()
            if text:
                return text[-2000:]
    return "No compiled model was recorded."


def _fingerprint_map(
    project_root: Path,
    audit_dir: Path,
    results: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for result in results:
        track_id = result.get("track_id")
        if not isinstance(track_id, str) or result.get("status") != "compiled":
            continue
        output[track_id] = _source_fingerprints(_result_response(audit_dir, result), result)
    return output


def _compare_fingerprints(
    project_root: Path,
    audit_dir: Path,
    current_results: Sequence[Mapping[str, Any]],
    compare_dir: Path | None,
) -> dict[str, Any]:
    if compare_dir is None:
        return {
            "status": "not_requested",
            "current_batch": str(audit_dir),
            "compared_batch": None,
            "per_track": [],
        }
    compare_dir = compare_dir.resolve()
    batch_path = compare_dir / "batch_results.json"
    if not batch_path.is_file():
        return {
            "status": "unavailable",
            "current_batch": str(audit_dir),
            "compared_batch": str(compare_dir),
            "reason": "comparison batch_results.json is missing",
            "per_track": [],
        }
    compare_results = _read_json(batch_path)
    if not isinstance(compare_results, list):
        return {
            "status": "unavailable",
            "current_batch": str(audit_dir),
            "compared_batch": str(compare_dir),
            "reason": "comparison batch_results.json is not a list",
            "per_track": [],
        }
    current_map = _fingerprint_map(project_root, audit_dir, current_results)
    compare_map = _fingerprint_map(project_root, compare_dir, compare_results)
    all_ids = sorted(set(current_map) | set(compare_map))
    per_track: list[dict[str, Any]] = []
    exact_count = 0
    unknown_count = 0
    for track_id in all_ids:
        current = current_map.get(track_id)
        compared = compare_map.get(track_id)
        fields: dict[str, Any] = {}
        for field in (
            "audio_features_canonical_sha256",
            "architectural_score_canonical_sha256",
            "audio_features_source_audio_sha256",
            "architectural_score_source_audio_sha256",
        ):
            current_value = current.get(field) if current else None
            compared_value = compared.get(field) if compared else None
            fields[f"{field}_equal"] = (
                current_value == compared_value
                if current_value is not None and compared_value is not None
                else None
            )
        comparisons = [
            fields["audio_features_canonical_sha256_equal"],
            fields["architectural_score_canonical_sha256_equal"],
        ]
        fields["all_canonical_hashes_equal"] = (
            all(comparisons) if all(item is not None for item in comparisons) else None
        )
        if fields["all_canonical_hashes_equal"] is True:
            exact_count += 1
        elif fields["all_canonical_hashes_equal"] is None:
            unknown_count += 1
        per_track.append({"track_id": track_id, **fields})
    current_ids = set(current_map)
    compare_ids = set(compare_map)
    return {
        "status": "compared",
        "current_batch": str(audit_dir),
        "compared_batch": str(compare_dir),
        "common_compiled_track_count": len(current_ids & compare_ids),
        "current_only_track_ids": sorted(current_ids - compare_ids),
        "compared_only_track_ids": sorted(compare_ids - current_ids),
        "matching_canonical_hash_count": exact_count,
        "unknown_canonical_hash_count": unknown_count,
        "changed_canonical_hash_count": len(all_ids) - exact_count - unknown_count,
        "per_track": per_track,
    }


def _add_context_aggregates(tracks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    landing_missing: dict[str, list[str]] = {}
    lift_missing: dict[str, list[str]] = {}
    unplaced_total = 0
    unplaced_tracks = 0
    severity_counts = Counter()
    rule_counts = Counter()
    capped_tracks = 0
    v2_available = v2_missing = v2_unknown = 0
    for track in tracks:
        if track.get("status") != "measured":
            continue
        landing = track.get("landing_coverage")
        if isinstance(landing, Mapping):
            missing = landing.get("missing_occupied_level_ids")
            if isinstance(missing, list) and missing:
                landing_missing[str(track.get("track_id"))] = list(missing)
        lift = track.get("lift_coverage")
        if isinstance(lift, Mapping):
            missing = lift.get("missing_occupied_level_ids")
            if isinstance(missing, list) and missing:
                lift_missing[str(track.get("track_id"))] = list(missing)
        program = track.get("program")
        if isinstance(program, Mapping) and isinstance(program.get("unplaced_count"), int):
            unplaced = int(program["unplaced_count"])
            unplaced_total += unplaced
            if unplaced:
                unplaced_tracks += 1
        spatial = track.get("spatial")
        if isinstance(spatial, Mapping):
            for key, value in (spatial.get("severity_counts_reported") or {}).items():
                severity_counts[str(key)] += int(value)
            for key, value in (spatial.get("rule_counts_uncapped") or {}).items():
                rule_counts[str(key)] += int(value)
            if spatial.get("reported_findings_capped") is True:
                capped_tracks += 1
        v2 = track.get("v2_asset")
        if isinstance(v2, Mapping):
            if v2.get("available") is True:
                v2_available += 1
            elif v2.get("available") is False:
                v2_missing += 1
            else:
                v2_unknown += 1
    return {
        "context_only": True,
        "landing_missing_by_track": dict(sorted(landing_missing.items())),
        "lift_missing_by_track": dict(sorted(lift_missing.items())),
        "program_unplaced_total": unplaced_total,
        "tracks_with_program_unplaced": unplaced_tracks,
        "spatial_severity_counts_reported": dict(sorted(severity_counts.items())),
        "spatial_rule_counts_uncapped": dict(sorted(rule_counts.items())),
        "spatial_tracks_with_capped_findings": capped_tracks,
        "v2_asset_available_count": v2_available,
        "v2_asset_missing_count": v2_missing,
        "v2_asset_unknown_count": v2_unknown,
    }


def summarize_batch(
    audit_dir: Path,
    *,
    project_root: Path | None = None,
    compare_dir: Path | None = None,
) -> dict[str, Any]:
    audit_dir = audit_dir.resolve()
    project_root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    results = _read_json(audit_dir / "batch_results.json")
    if not isinstance(results, list):
        raise ValueError("batch_results.json must contain a list")
    ordered_results = sorted(
        (item for item in results if isinstance(item, Mapping)),
        key=lambda item: str(item.get("track_id", "")),
    )

    by_check = {
        name: {"count": 0, "evaluated_count": 0, "unevaluated_count": 0}
        for name in CHECK_CLASSES
    }
    distributions = {
        "massing": Counter(),
        "typology": Counter(),
        "structure": Counter(),
        "grammar": Counter(),
    }
    tracks: list[dict[str, Any]] = []
    failed_tracks: list[dict[str, Any]] = []
    measured_count = 0
    finding_count = evaluated_count = unevaluated_count = 0
    tracks_with_findings = tracks_with_unevaluated = 0
    tracks_with_rings = tracks_with_nonring = 0

    for result in ordered_results:
        track_id = str(result.get("track_id", ""))
        if result.get("status") != "compiled":
            failed = {
                "track_id": track_id,
                "status": "unevaluated",
                "source_status": result.get("status"),
                "reason": _failure_reason(audit_dir, result),
                "checks": _unevaluated_checks(),
                "landing_coverage": None,
                "lift_coverage": None,
                "program": None,
                "spatial": None,
                "v2_asset": None,
                "source_fingerprints": None,
            }
            failed_tracks.append(failed)
            tracks.append(failed)
            continue

        model_path = _model_path(project_root, audit_dir, result)
        if model_path is None or not model_path.is_file():
            raise FileNotFoundError(f"Missing frozen building_model_v3.json for {track_id}")
        model = _read_json(model_path)
        if not isinstance(model, Mapping):
            raise ValueError(f"building_model_v3.json for {track_id} must contain an object")
        report = measure(model)
        measurement_path = audit_dir / "tracks" / track_id / "geometry_measurements.json"
        _write_json(measurement_path, report)
        checks = _checks_by_class(report)
        response = _result_response(audit_dir, result)
        source_fingerprints = _source_fingerprints(response, result)
        landing_coverage = _level_coverage(
            model,
            kind="stair_landing",
            exclude_id=ENTRY_LANDING_ID,
            label="internal stair landings; CIR-LND-ENTRY excluded",
        )
        lift_coverage = _level_coverage(
            model,
            kind="elevator_shaft",
            label="emitted elevator shaft levels",
        )
        program = _program_context(model)
        spatial = _spatial_context(model)
        v2_asset = _v2_asset_context(response)

        track_findings = sum(item["count"] for item in checks.values())
        track_evaluated = sum(item["evaluated_count"] for item in checks.values())
        track_unevaluated = sum(item["unevaluated_count"] for item in checks.values())
        ring_count = checks["primitive_invalid_plan_ring"]["count"]
        nonring_count = track_findings - ring_count
        measured_count += 1
        finding_count += track_findings
        evaluated_count += track_evaluated
        unevaluated_count += track_unevaluated
        tracks_with_findings += track_findings > 0
        tracks_with_unevaluated += track_unevaluated > 0
        tracks_with_rings += ring_count > 0
        tracks_with_nonring += nonring_count > 0
        for name in CHECK_CLASSES:
            for key in by_check[name]:
                by_check[name][key] += checks[name][key]
        for output_key, source_key in (
            ("massing", "massing"),
            ("typology", "typology"),
            ("structure", "structural_system"),
            ("grammar", "facade_grammar"),
        ):
            distributions[output_key][str(result.get(source_key, "unknown"))] += 1
        relative_measurement_path = measurement_path
        try:
            relative_measurement_path = measurement_path.relative_to(project_root)
        except ValueError:
            pass
        tracks.append({
            "track_id": track_id,
            "status": "measured",
            "source_status": result.get("status"),
            "model_id": result.get("model_id"),
            "massing": result.get("massing"),
            "typology": result.get("typology"),
            "structure": result.get("structural_system"),
            "grammar": result.get("facade_grammar"),
            "measurement_path": relative_measurement_path.as_posix(),
            "checks": checks,
            "finding_count": track_findings,
            "evaluated_count": track_evaluated,
            "unevaluated_count": track_unevaluated,
            "invalid_plan_ring_count": ring_count,
            "has_findings": track_findings > 0,
            "has_unevaluated_checks": track_unevaluated > 0,
            "has_invalid_plan_rings": ring_count > 0,
            "landing_coverage": landing_coverage,
            "lift_coverage": lift_coverage,
            "program": program,
            "spatial": spatial,
            "v2_asset": v2_asset,
            "source_fingerprints": source_fingerprints,
        })

    summary = {
        "schema_version": "visual-geometry-measurement-summary-1",
        "batch": audit_dir.name,
        "measurement_script": "backend/scripts/measure_visual_geometry.py",
        "measurement_function": "measure(dict)",
        "measurement_basis": (
            "Each compiled building_model_v3.json was decoded and passed directly to "
            "measure(dict); failed runs have no geometry measurement."
        ),
        "check_classes": list(CHECK_CLASSES),
        "track_count": len(results),
        "compiled_track_count": measured_count,
        "failed_track_count": len(failed_tracks),
        "tracks": tracks,
        "failed_tracks": failed_tracks,
        "totals": {
            "compiled_track_count": measured_count,
            "by_check": by_check,
            "finding_count": finding_count,
            "evaluated_count": evaluated_count,
            "unevaluated_count": unevaluated_count,
        },
        "problem_track_count": tracks_with_findings,
        "tracks_with_findings": tracks_with_findings,
        "tracks_with_non_ring_findings": tracks_with_nonring,
        "tracks_with_unevaluated_checks": tracks_with_unevaluated,
        "tracks_with_invalid_plan_rings": tracks_with_rings,
        "invalid_plan_ring_finding_count": by_check["primitive_invalid_plan_ring"]["count"],
        "unknown_policy": (
            "A nonzero primitive_invalid_plan_ring count is reported explicitly. Any "
            "unevaluated_count remains unknown; it is never converted to zero findings. "
            "Failed tracks and missing context remain null/unevaluated."
        ),
        "selection_distribution": {
            key: dict(sorted(counter.items())) for key, counter in distributions.items()
        },
        "coverage_context": _add_context_aggregates(tracks),
        "source_fingerprint_comparison": _compare_fingerprints(
            project_root,
            audit_dir,
            ordered_results,
            compare_dir,
        ),
        "source_fingerprint_note": (
            "Canonical hashes cover the complete response audio_features and "
            "architectural_score objects; equal hashes indicate equal serialized "
            "payloads under the stated canonicalization, not a visual verdict."
        ),
    }
    _write_json(audit_dir / "measurement_summary.json", summary)
    return summary


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "audit_dir",
        type=Path,
        help="Audit directory containing batch_results.json and tracks/.",
    )
    parser.add_argument(
        "--compare-dir",
        type=Path,
        default=None,
        help="Optional sibling audit directory for source fingerprint comparison.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Repository root used to resolve evidence paths (defaults to this repo).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    project_root = (args.project_root or Path(__file__).resolve().parents[2]).resolve()
    summary = summarize_batch(
        args.audit_dir,
        project_root=project_root,
        compare_dir=args.compare_dir,
    )
    print(json.dumps({
        "batch": summary["batch"],
        "track_count": summary["track_count"],
        "compiled_track_count": summary["compiled_track_count"],
        "failed_track_count": summary["failed_track_count"],
        "finding_count": summary["totals"]["finding_count"],
        "unevaluated_count": summary["totals"]["unevaluated_count"],
        "measurement_summary": str((args.audit_dir.resolve() / "measurement_summary.json")),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
