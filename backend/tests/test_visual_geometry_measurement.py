"""Regression fixtures for direct measurements of emitted v3 geometry."""

import pytest

from backend.scripts.measure_visual_geometry import measure


def _point(x: float, y: float) -> dict[str, float]:
    return {"x": x, "y": y}


def _extrusion(
    element_id: str,
    boundary: list[tuple[float, float]],
    *,
    z_top: float = 1.2,
    z_base: float = 0.0,
) -> dict:
    return {
        "id": element_id,
        "level_id": "L01",
        "geometry": {
            "type": "extrusion",
            "boundary": [_point(x, y) for x, y in boundary],
            "holes": [],
            "z_base": z_base,
            "z_top": z_top,
        },
    }


def _landing() -> dict:
    return {
        "id": "CIR-LND-L01",
        "level_id": "L01",
        "geometry": {
            "type": "box",
            "center": {"x": 2.0, "y": 1.0, "z": 1.1},
            "size": {"x": 4.0, "y": 2.0, "z": 0.2},
            "rotation_z": 0.0,
        },
    }


def _model(landing: dict, slabs: list[dict]) -> dict:
    return {
        "element_groups": [
            {
                "group_id": "GRP-landings",
                "kind": "stair_landing",
                "instances": [landing],
            },
            {
                "group_id": "GRP-slabs",
                "kind": "floor_slab",
                "instances": slabs,
            },
        ]
    }


def _landing_check(model: dict) -> dict:
    return next(
        check for check in measure(model)["checks"]
        if check["class"] == "landing_slab_contact"
    )


def test_adjacent_floor_slab_parts_are_unioned_for_landing_contact():
    slabs = [
        _extrusion("STR-SLB-L01-A", [(0, 0), (2, 0), (2, 2), (0, 2)]),
        _extrusion("STR-SLB-L01-B", [(2, 0), (4, 0), (4, 2), (2, 2)]),
    ]

    check = _landing_check(_model(_landing(), slabs))

    assert check["count"] == 0
    assert check["evaluated_count"] == 1
    assert check["unevaluated_count"] == 0
    measurement = check["all_measurements"][0]
    assert measurement["status"] == "ok"
    assert measurement["matching_slab_ids"] == [
        "STR-SLB-L01-A",
        "STR-SLB-L01-B",
    ]
    assert measurement["contact_area_m2"] == pytest.approx(8.0)
    assert measurement["contact_ratio"] == pytest.approx(1.0)


def test_invalid_slab_part_that_reaches_landing_keeps_contact_unknown():
    invalid_part = _extrusion(
        "STR-SLB-L01-BAD",
        [(2, 0), (4, 2), (2, 2), (4, 0)],
    )
    valid_part = _extrusion(
        "STR-SLB-L01-A",
        [(0, 0), (2, 0), (2, 2), (0, 2)],
    )

    check = _landing_check(_model(_landing(), [valid_part, invalid_part]))

    assert check["count"] == 0
    assert check["evaluated_count"] == 0
    assert check["unevaluated_count"] == 1
    measurement = check["all_measurements"][0]
    assert measurement["status"] == "unevaluated_invalid_geometry"
    assert measurement["invalid_slab_ids"] == ["STR-SLB-L01-BAD"]


def test_overlapping_slab_with_nonflush_top_reports_vertical_mismatch():
    slab = _extrusion(
        "STR-SLB-L01-LOW",
        [(0, 0), (4, 0), (4, 2), (0, 2)],
        z_top=1.0,
    )

    check = _landing_check(_model(_landing(), [slab]))

    assert check["count"] == 1
    assert check["evaluated_count"] == 1
    measurement = check["samples"][0]
    assert measurement["status"] == "vertical_mismatch"
    assert measurement["vertical_offset_m"] == pytest.approx(0.2)
    assert measurement["mismatched_contact_area_m2"] == pytest.approx(8.0)
