"""Regression tests for Program Volume owners that keep their authored XY shape.

These tests intentionally use a tiny lattice instead of compiling a building.  The
contract under test is the seam between an authored Program Volume rectangle and the
area allocator: a registered room may keep a free-XY rectangle, while the plate,
holes, and non-waivable reservations still have authority over it.
"""

from __future__ import annotations

import pytest
from shapely.geometry import box

from backend.app.datums import DatumSet, Lattice, LevelDatum
from backend.app.geometry import v2
from backend.app.program import SpaceRequirement, allocate_program
from backend.app.program_volume_contracts import (
    ProgramVolumeRegion,
    is_exact_registered_room,
)


def _ring(shape):
    return [v2(x, y) for x, y in list(shape.exterior.coords)[:-1]]


def _lattice(*, owner=(1.0, 0.7, 3.0, 4.7), obstruction=None):
    """A plate whose structural and authored registration grids are independent."""
    x0, y0, x1, y1 = owner
    plate = box(0.0, 0.0, 8.0, 6.0)
    void_shape = box(1.5, 1.5, 2.5, 2.5)
    level = LevelDatum(
        index=1,
        id='L01',
        z=0.0,
        kind='occupied',
        plate=_ring(plate),
        voids=[_ring(void_shape)] if obstruction == 'void' else [],
        reserved=[(1.5, 1.5, 2.5, 2.5)] if obstruction == 'core' else [],
    )
    podium = level.model_copy(update={'id': 'L00', 'index': 0, 'kind': 'podium'})
    return Lattice(
        levels=[podium, level],
        # These lines deliberately do not contain the authored room edges.
        x_lines=[0.0, 4.0, 8.0],
        y_lines=[0.0, 2.0, 6.0],
        band_lines=[0.0, 2.5, 6.0],
        apse_nodes=[],
        plan_x_m=8.0,
        plan_y_m=6.0,
        program_volume_x_lines=[x0, x1],
        program_volume_y_lines=[y0, y1],
        program_volume_regions=[ProgramVolumeRegion(
            id='PV-L01-OWNER',
            level_id='L01',
            category='service',
            role='program',
            space_ids=['SP-OWNER'],
            grid_rect=(0, 0, 1, 1),
            z_base=0.0,
            z_top=4.0,
        )],
    )


def _brief(area=8.0):
    return (SpaceRequirement(
        id='SP-OWNER',
        space_type='service',
        label='Owner room',
        category='service',
        area_m2=area,
        min_dimension_m=2.0,
        level_preference='ground',
        daylight='none',
        occupancy_id='office',
        reason='Exact authored owner regression.',
    ),)


def _empty_datums():
    # The allocator falls back to its declared circulation allowance when this
    # optional datum is absent.  Keeping the datum set empty isolates this seam.
    return DatumSet(score_id='exact-owner-test', datums=[])


def test_exact_registered_room_is_allowed_off_structural_and_band_lines():
    lattice = _lattice()
    owner = lattice.program_volume_regions[0].resolve_bounds(lattice)
    assert owner == pytest.approx((1.0, 0.7, 3.0, 4.7))
    assert owner[0] not in lattice.x_lines and owner[2] not in lattice.x_lines
    assert owner[1] not in lattice.band_lines and owner[3] not in lattice.band_lines

    allocation = allocate_program(lattice, _empty_datums(), _brief())

    assert allocation.fits
    assert not allocation.unplaced
    assert len(allocation.zones) == 1
    zone = allocation.zones[0]
    assert (zone.x0, zone.y0, zone.x1, zone.y1) == pytest.approx(owner)
    assert zone.area_delivered_m2 == pytest.approx(8.0)


@pytest.mark.parametrize('obstruction', ['core', 'void'])
def test_exact_owner_remains_rejected_when_a_core_or_void_obstructs_it(obstruction):
    # Both obstructions remove floor from the authored rectangle.  The direct owner
    # path may preserve XY freedom, but it may not bypass floor authority.
    lattice = _lattice(obstruction=obstruction)
    allocation = allocate_program(lattice, _empty_datums(), _brief())

    assert not allocation.zones
    assert [space.space_id for space in allocation.unplaced] == ['SP-OWNER']


def test_exact_room_tolerance_is_only_coordinate_quantization():
    rect = (1.0, 0.7, 3.0, 4.7)  # 8.0 m2, serialized at 0.1 mm precision

    assert is_exact_registered_room(rect, 8.0, 2.0)
    assert is_exact_registered_room(rect, 8.0005, 2.0)
    assert not is_exact_registered_room(rect, 7.9, 2.0)


def test_allocator_does_not_accept_a_materially_undersized_owner():
    # The owner is 7.9 m2 while the brief asks for 8.0 m2.  It is also narrower
    # than the legacy 4 m band filter, so accepting it would specifically indicate
    # that area tolerance leaked into the exact-owner seam.
    lattice = _lattice(owner=(1.0, 0.7, 3.0, 4.65))
    allocation = allocate_program(lattice, _empty_datums(), _brief(area=8.0))

    assert not allocation.zones
    assert [space.space_id for space in allocation.unplaced] == ['SP-OWNER']


@pytest.mark.parametrize('blocked', [False, True])
def test_adjacent_authored_rooms_share_a_boundary_but_need_real_corridor_access(blocked):
    from shapely.geometry import LineString
    from backend.app.program import PublicCirculationPlanner

    lattice = _lattice()
    lattice.occupied[0].plate = _ring(box(0, 0, 8, 8))
    lattice.program_volume_x_lines = [1, 3, 5]
    lattice.program_volume_regions.append(lattice.program_volume_regions[0].model_copy(update={
        'id': 'PV-NEIGHBOUR', 'space_ids': ['SP-NEIGHBOUR'], 'grid_rect': (1, 0, 2, 1)}))
    brief = (*_brief(), _brief()[0].model_copy(update={'id': 'SP-NEIGHBOUR'}))
    obstacles = [box(0, 4.8, 8, 5.8)] if blocked else []
    planner = PublicCirculationPlanner(lattice, obstacles={1: obstacles},
        terminals={1: [('STAIR-1', [(6, 6.3)])]})
    allocation = allocate_program(lattice, _empty_datums(), brief, public_circulation=planner)
    if blocked:
        assert not allocation.zones
        assert len(allocation.unplaced) == 2
        return
    assert allocation.fits
    assert {zone.space_id for zone in allocation.zones} == {'SP-OWNER', 'SP-NEIGHBOUR'}
    rooms = [box(zone.x0, zone.y0, zone.x1, zone.y1) for zone in allocation.zones]
    for path in planner.plan.paths:
        if path.target_id.startswith('SP-'):
            corridor = LineString(path.points).buffer(planner.radius)
            assert box(0, 0, 8, 8).buffer(1e-7).covers(corridor)
            assert all(corridor.intersection(room).area < 1e-7 for room in rooms)
