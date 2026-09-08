"""The resolved World-XY support registry is a durable lattice contract."""

from __future__ import annotations

from shapely.geometry import box

from backend.app.datums import Lattice
from backend.app.world_xy_grid import (
    ColumnFootprint,
    GridBounds,
    ProgramVolumeLevelFootprint,
    WorldXYGrid,
    plan_world_xy_columns,
)


def _resolved_plan():
    grid = WorldXYGrid(origin=(1.0, 2.0), spacing_x=4.0, spacing_y=6.0)
    return plan_world_xy_columns(
        grid,
        [ProgramVolumeLevelFootprint("L01", box(0.0, 0.0, 12.0, 12.0))],
        GridBounds(-1.0, -1.0, 17.0, 17.0),
        footprint=ColumnFootprint(width_m=0.6, depth_m=0.8),
    )


def _lattice(*, plan=None) -> Lattice:
    return Lattice(
        levels=[],
        x_lines=[0.0, 4.0, 8.0],
        y_lines=[0.0, 6.0, 12.0],
        apse_nodes=[],
        plan_x_m=8.0,
        plan_y_m=12.0,
        world_xy_grid=plan.grid if plan is not None else None,
        world_xy_column_plan=plan,
    )


def test_resolved_column_plan_survives_lattice_round_trip():
    plan = _resolved_plan()
    lattice = _lattice(plan=plan)
    x_lines, y_lines = list(lattice.x_lines), list(lattice.y_lines)

    payload = lattice.model_dump(mode="json")
    assert payload["world_xy_column_plan"]["footprint"] == {
        "width_m": 0.6,
        "depth_m": 0.8,
    }
    restored = Lattice.model_validate_json(lattice.model_dump_json())

    assert restored.world_xy_column_plan == plan
    assert restored.world_xy_column_plan is not None
    assert restored.world_xy_column_plan.candidates == plan.candidates
    assert restored.x_lines == x_lines
    assert restored.y_lines == y_lines


def test_candidate_index_resolves_persisted_id_to_resolved_coordinates():
    plan = _resolved_plan()
    lattice = _lattice(plan=plan)
    restored = Lattice.model_validate_json(lattice.model_dump_json())
    assert restored.world_xy_column_plan is not None

    candidate = next(
        item for item in restored.world_xy_column_plan.candidates
        if item.grid_source == "grid_line_y" and item.fits_whole_footprint
    )
    candidate_index = {
        item.id: item for item in restored.world_xy_column_plan.candidates
    }
    resolved = candidate_index[candidate.id]

    assert resolved.id == candidate.id
    assert resolved.point_xy == candidate.point_xy
    assert resolved.raw_boundary_anchor is not None
    assert resolved.point_xy != resolved.raw_boundary_anchor


def test_legacy_lattice_omits_empty_column_plan():
    lattice = _lattice()
    payload = lattice.model_dump(mode="json")

    assert lattice.world_xy_column_plan is None
    assert "world_xy_column_plan" not in payload
    assert "world_xy_column_plan" not in lattice.model_dump_json()
    assert Lattice.model_validate_json(lattice.model_dump_json()).world_xy_column_plan is None
