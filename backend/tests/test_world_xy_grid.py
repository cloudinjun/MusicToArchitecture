"""Contract tests for the independent World-XY column candidate planner."""

from __future__ import annotations

from shapely.geometry import Polygon, box

from backend.app.world_xy_grid import (
    ColumnFootprint,
    GridBounds,
    ProgramVolumeLevelFootprint,
    WorldXYGrid,
    plan_world_xy_columns,
)


def _plan(levels, *, origin=(0.0, 0.0), spacing=4.0, bounds=None):
    if bounds is None:
        bounds = GridBounds(-1.0, -1.0, 17.0, 17.0)
    return plan_world_xy_columns(
        WorldXYGrid(origin=origin, spacing_x=spacing, spacing_y=spacing),
        levels,
        bounds,
        footprint=ColumnFootprint(width_m=0.4, depth_m=0.4),
    )


def test_world_xy_grid_is_independent_of_level_translation():
    first = _plan([ProgramVolumeLevelFootprint("L01", box(0, 0, 12, 12))])
    shift_x, shift_y = 23.0, -11.0
    second = _plan(
        [ProgramVolumeLevelFootprint(
            "L01", box(shift_x, shift_y, 12 + shift_x, 12 + shift_y))],
        origin=(shift_x, shift_y),
        bounds=GridBounds(shift_x - 1, shift_y - 1, shift_x + 17, shift_y + 17),
    )

    first_points = sorted((round(item.point_xy[0], 6), round(item.point_xy[1], 6))
                          for item in first.fitted_candidates)
    second_points = sorted((round(item.point_xy[0] - shift_x, 6),
                            round(item.point_xy[1] - shift_y, 6))
                           for item in second.fitted_candidates)
    assert first_points == second_points
    assert {item.grid_node_id for item in first.candidates if item.grid_node_id} == {
        item.grid_node_id for item in second.candidates if item.grid_node_id
    }


def test_inside_grid_node_is_indexed_and_uses_actual_polygon():
    plan = _plan([ProgramVolumeLevelFootprint("L01", box(0, 0, 12, 12))])
    node = next(item for item in plan.candidates if item.grid_node_id == "WXG-N-1-1")
    assert node.grid_source == "grid_node"
    assert node.point_xy == (4.0, 4.0)
    assert node.fits_whole_footprint
    assert node.support_status == "grounded"


def test_boundary_intersection_keeps_raw_anchor_and_moves_along_grid_line():
    # The y=4 world line enters the rectangle from x=0.  The resolved point therefore
    # moves along that same horizontal grid line to the conservative inset.
    plan = _plan([ProgramVolumeLevelFootprint("L01", box(0, 0, 12, 12))])
    boundary = [
        item for item in plan.candidates
        if item.grid_source == "grid_line_y"
        and item.raw_boundary_anchor is not None
        and abs(item.raw_boundary_anchor[0]) < 1e-7
        and abs(item.raw_boundary_anchor[1] - 4.0) < 1e-7
    ]
    assert boundary
    candidate = next(item for item in boundary if item.fits_whole_footprint)
    assert candidate.boundary_provenance == "program_volume_boundary"
    assert candidate.raw_boundary_anchor == (0.0, 4.0)
    assert candidate.point_xy[0] > candidate.raw_boundary_anchor[0]
    assert abs(candidate.point_xy[1] - 4.0) < 1e-7
    assert candidate.inset_distance_m > 0.0


def test_hole_and_notch_are_real_geometry_not_bounding_box_space():
    # The hole is a courtyard.  A concave notch on the north edge tests a non-rectangular
    # outer ring at the same time.
    outer = [(0, 0), (16, 0), (16, 16), (12, 16), (12, 12), (4, 12), (4, 16), (0, 16)]
    shape = Polygon(outer, holes=[[(6, 4), (10, 4), (10, 8), (6, 8)]])
    plan = _plan([ProgramVolumeLevelFootprint("L01", shape)])
    hole = Polygon([(6, 4), (10, 4), (10, 8), (6, 8)])
    for candidate in plan.fitted_candidates:
        footprint = plan.footprint.geometry_at(candidate.point_xy)
        assert shape.covers(footprint)
        assert footprint.intersection(hole).area <= 1.0e-9
    # The node at (8, 4) lies on the courtyard boundary and is never emitted as an
    # interior grid node; any boundary candidate there must retain the hole provenance.
    assert not any(item.grid_node_id == "WXG-N-2-1" for item in plan.candidates)


def test_sloped_boundary_requires_full_footprint_fit():
    triangle = Polygon([(0, 0), (16, 0), (0, 12)])
    plan = _plan([ProgramVolumeLevelFootprint("L01", triangle)])
    assert plan.candidates
    assert all(triangle.covers(plan.footprint.geometry_at(item.point_xy))
               for item in plan.fitted_candidates)
    # Any unresolved boundary point remains visible and is explicitly labelled.
    assert any(item.raw_boundary_anchor is not None
               and not item.fits_whole_footprint for item in plan.candidates)


def test_upper_overhang_is_retained_as_transfer_required():
    plan = _plan([
        ProgramVolumeLevelFootprint("L01", box(0, 0, 8, 8), level_index=0),
        ProgramVolumeLevelFootprint("L02", box(4, 0, 12, 8), level_index=1),
    ])
    candidate = next(item for item in plan.candidates
                     if item.floor_id == "L02" and item.grid_node_id == "WXG-N-2-1")
    assert candidate.fits_whole_footprint
    assert candidate.support_status == "transfer_required"
    assert candidate.supporting_floor_ids == ()
    assert "transfer" in candidate.reason.lower()


def test_candidate_plan_is_reproducible_and_retains_failed_footprints():
    levels = [ProgramVolumeLevelFootprint("L01", box(0, 0, 12, 12))]
    first = _plan(levels)
    second = _plan(levels)
    assert first == second
    assert any(not item.fits_whole_footprint for item in first.candidates)
    assert any(item.fits_status in {
        "footprint_outside_program_volume",
        "no_inset_intersection_for_full_column_footprint",
    } for item in first.candidates)


def test_invalid_grid_and_level_input_is_rejected():
    try:
        WorldXYGrid(spacing_x=0.0)
    except ValueError as error:
        assert "spacing" in str(error).lower()
    else:  # pragma: no cover - assertion documents the contract
        raise AssertionError("zero World XY spacing must be rejected")

    try:
        _plan([ProgramVolumeLevelFootprint("L01", Polygon())])
    except ValueError as error:
        assert "polygon" in str(error).lower()
    else:  # pragma: no cover
        raise AssertionError("empty Program Volume level must be rejected")
