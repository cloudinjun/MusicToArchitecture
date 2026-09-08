"""Named public-floor claims open only their actual crossing edge intervals."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.app.program_volume_contracts import ProgramVolumeRegion
from backend.app.shared_boundaries import split_shared_route_boundary


def _lattice(routes, *, named=None, owner_level='L01', category='circulation'):
    owners = ProgramVolumeRegion(
        id='FOYER', level_id=owner_level, category=category, role='program',
        space_ids=['SP-FOYER'], shared_route_volume_ids=(
            list(routes) if named is None else named),
        grid_rect=(0, 0, 10, 5), z_base=0., z_top=4.)
    regions = [owners]
    for identifier, (rect, level) in routes.items():
        regions.append(ProgramVolumeRegion(
            id=identifier, level_id=level, category='circulation', role='connector',
            grid_rect=rect, z_base=0., z_top=4.))
    return SimpleNamespace(program_volume_regions=regions,
        program_volume_x_lines=list(range(11)), program_volume_y_lines=list(range(11)))


def test_partial_crossing_partitions_full_edge_without_mutating_registry():
    lattice = _lattice({'R1': ((2, 4, 6, 8), 'L01')})
    before = deepcopy(lattice)
    assert split_shared_route_boundary(lattice, 'L01', 'SP-FOYER', (0, 5, 10, 5)) == [
        ((0, 5, 2, 5), False), ((2, 5, 6, 5), True), ((6, 5, 10, 5), False)]
    assert lattice == before


def test_overlapping_carriers_union_before_partition_and_clip_to_input_fragment():
    lattice = _lattice({'R1': ((2, 4, 6, 8), 'L01'), 'R2': ((4, 3, 9, 7), 'L01')})
    assert split_shared_route_boundary(lattice, 'L01', 'SP-FOYER', (3, 5, 10, 5)) == [
        ((3, 5, 9, 5), True), ((9, 5, 10, 5), False)]


def test_reversed_edge_keeps_traversal_order_and_endpoint_directions():
    lattice = _lattice({'R1': ((2, 4, 6, 8), 'L01')})
    assert split_shared_route_boundary(lattice, 'L01', 'SP-FOYER', (10, 5, 0, 5)) == [
        ((10, 5, 6, 5), False), ((6, 5, 2, 5), True), ((2, 5, 0, 5), False)]


def test_vertical_boundary_uses_the_other_crossing_axis():
    lattice = _lattice({'R1': ((3, 2, 7, 6), 'L01')})
    assert split_shared_route_boundary(lattice, 'L01', 'SP-FOYER', (5, 10, 5, 0)) == [
        ((5, 10, 5, 6), False), ((5, 6, 5, 2), True), ((5, 2, 5, 0), False)]


@pytest.mark.parametrize('rect', [(2, 5, 6, 8), (2, 1, 6, 5)])
def test_tangent_carrier_opens_no_boundary(rect):
    lattice = _lattice({'R1': (rect, 'L01')})
    edge = (0, 5, 10, 5)
    assert split_shared_route_boundary(lattice, 'L01', 'SP-FOYER', edge) == [(edge, False)]


@pytest.mark.parametrize('case', ['unnamed', 'unrelated_space', 'route_other_level', 'owner_other_level'])
def test_non_authoritative_carrier_has_no_effect(case):
    lattice = _lattice({'R1': ((2, 4, 6, 8), 'L02' if case=='route_other_level' else 'L01')},
        named=[] if case=='unnamed' else ['R1'],
        owner_level='L02' if case=='owner_other_level' else 'L01')
    edge = (0, 5, 10, 5)
    space = 'SP-OTHER' if case=='unrelated_space' else 'SP-FOYER'
    assert split_shared_route_boundary(lattice, 'L01', space, edge) == [(edge, False)]


def test_non_circulation_owner_cannot_open_edge_even_if_validation_was_bypassed():
    lattice = _lattice({'R1': ((2, 4, 6, 8), 'L01')})
    lattice.program_volume_regions[0] = lattice.program_volume_regions[0].model_copy(
        update={'category': 'service'})
    edge = (0, 5, 10, 5)
    assert split_shared_route_boundary(lattice, 'L01', 'SP-FOYER', edge) == [(edge, False)]
