"""Core-wall foundations follow the first physically emitted wall interval."""

from __future__ import annotations

import pytest

from backend.app.compiler_v3 import _Builder, _core_rects, _emit_structure, _run_sizing
from backend.app.program import ProgramAllocation
from backend.app.program_massing import datums_for, lattice_for, neutral_score
from backend.app.tectonics import FRAME_TECTONICS
from backend.tests.test_world_xy_frame_integration import _massing


@pytest.fixture(
    params=(
        pytest.param(0.3, id="compact-elevated-first-floor"),
        pytest.param(4.3, id="normal-first-span"),
    )
)
def builder(request):
    """Emit the small World XY fixture with either first-storey condition."""
    massing = _massing().model_copy(deep=True)
    first_floor_z = request.param
    for index, level in enumerate(massing.levels):
        level.z = 0.0 if index == 0 else first_floor_z + 4.0 * (index - 1)

    datums = datums_for(massing, neutral_score(massing))
    lattice = lattice_for(massing, datums)
    builder = _Builder(datums, lattice)
    allocation = ProgramAllocation(
        zones=[], unplaced=[], usable_area_by_level={},
        required_area_m2=0, delivered_area_m2=0,
    )
    builder.program_allocation = allocation
    occupancy, sizing = _run_sizing(datums, lattice, allocation, FRAME_TECTONICS['FRM-STEEL'])
    _emit_structure(builder, sizing, FRAME_TECTONICS['FRM-STEEL'], occupancy)
    return builder


def _elements(builder):
    return [element for group in builder.groups.values() for element in group.expand()]


def _core_walls(builder):
    return [
        element for element in _elements(builder)
        if element.kind == 'core_wall' and element.id.startswith('STR-CWL-')
    ]


def _core_footings(builder):
    return [
        element for element in _elements(builder)
        if element.kind == 'footing' and element.id.startswith('STR-FDN-CORE-')
    ]


def _z_bottom(element):
    return element.geometry.center.z - element.geometry.size.z / 2.0


def _z_top(element):
    return element.geometry.center.z + element.geometry.size.z / 2.0


def test_each_given_core_gets_a_raft_at_the_first_emitted_wall(builder):
    footings = _core_footings(builder)
    assert len(footings) == len(_core_rects(builder.cores)) == 2

    slab_t = builder.datums.value('slab_thickness_m')
    first_intervals = [
        lower.index
        for lower, upper in zip(builder.lattice.levels, builder.lattice.levels[1:])
        if upper.z - lower.z - slab_t >= 0.5
    ]
    assert first_intervals
    walls = _core_walls(builder)
    assert walls
    first_wall_level = min(wall.lattice_index['level'] for wall in walls)
    assert first_wall_level == first_intervals[0]

    grade_z = builder.lattice.levels[0].z
    for footing in footings:
        assert _z_bottom(footing) < grade_z
        assert _z_top(footing) == pytest.approx(
            builder.lattice.levels[first_wall_level].z
        )


def test_core_wall_supports_are_real_ids_including_first_jambs(builder):
    walls = _core_walls(builder)
    assert walls
    for wall in walls:
        assert wall.supports, wall.id
        assert set(wall.supports) <= builder.element_ids, (wall.id, wall.supports)

    first_wall_level = min(wall.lattice_index['level'] for wall in walls)
    first_walls = [
        wall for wall in walls if wall.lattice_index['level'] == first_wall_level
    ]
    first_footings = {
        footing.lattice_index['core']: footing.id for footing in _core_footings(builder)
    }
    jambs = [wall for wall in first_walls if wall.id.endswith(('-JA', '-JB'))]
    assert jambs
    for jamb in jambs:
        footing_id = first_footings[jamb.lattice_index['core']]
        assert jamb.supports == [footing_id]
        assert not any(support.endswith(('-JA', '-JB')) for support in jamb.supports)


def test_first_core_walls_start_on_raft_top_and_stay_inside_their_carrier(builder):
    walls = _core_walls(builder)
    first_wall_level = min(wall.lattice_index['level'] for wall in walls)
    lower = builder.lattice.levels[first_wall_level]
    footing_by_core = {
        footing.lattice_index['core']: footing for footing in _core_footings(builder)
    }
    carriers = _core_rects(builder.cores)

    for wall in walls:
        core_index = wall.lattice_index['core']
        bx0, by0, bx1, by1 = carriers[core_index]
        x0 = wall.geometry.center.x - wall.geometry.size.x / 2.0
        x1 = wall.geometry.center.x + wall.geometry.size.x / 2.0
        y0 = wall.geometry.center.y - wall.geometry.size.y / 2.0
        y1 = wall.geometry.center.y + wall.geometry.size.y / 2.0
        assert bx0 - 1e-7 <= x0 <= x1 <= bx1 + 1e-7, wall.id
        assert by0 - 1e-7 <= y0 <= y1 <= by1 + 1e-7, wall.id

        if wall.lattice_index['level'] == first_wall_level and not wall.id.endswith('-HD'):
            assert _z_bottom(wall) == pytest.approx(lower.z), wall.id
            assert _z_top(footing_by_core[core_index]) == pytest.approx(lower.z)


def test_core_foundation_does_not_rephase_world_xy_registration(builder):
    assert builder.lattice.x_lines == [0.0, 4.0, 8.0, 12.0, 16.0, 20.0, 24.0]
    assert builder.lattice.y_lines == [0.0, 4.0, 8.0, 12.0, 16.0, 20.0]
