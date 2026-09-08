"""The compact Program Volume contracts stay grid-derived and three-valued."""
from types import SimpleNamespace

import pytest

from backend.app.program_volume_contracts import (
    CirculationFinding, GridBoundaryStation, ProgramCirculationIntent,
    ProgramVolumeRegion, ResolvedCirculationPlan,
)


def _intent() -> ProgramCirculationIntent:
    return ProgramCirculationIntent(
        source_volume_digest='abc123', carrier_volume_ids=['PV-L01-SPINE'],
        entry_station=GridBoundaryStation(
            level_id='L01', source_volume_id='PV-L01-SPINE',
            grid_edge=(0, 0, 2, 0), fraction=0.25),
        public_stair_family='broad_straight', ramp_preference='edge_parallel',
        entry_floor_elevation_m=0.6, approach_depth_m=21.0,
        approach_depth_provenance='site proposal; review required',
        reason='Compact volume entry test.')


def test_boundary_station_resolves_from_grid_indices_and_keeps_orientation():
    station = _intent().entry_station
    point, tangent, outward = station.resolve(SimpleNamespace(
        x_lines=[-6.0, 0.0, 8.0], y_lines=[-4.0, 3.0]))
    assert point == pytest.approx((-2.5, -4.0))
    assert tangent == pytest.approx((1.0, 0.0))
    assert outward == pytest.approx((0.0, -1.0))


def test_boundary_station_refuses_a_diagonal_or_out_of_grid_edge():
    with pytest.raises(ValueError, match='axis-aligned'):
        GridBoundaryStation(level_id='L01', source_volume_id='PV',
                            grid_edge=(0, 0, 1, 1))
    with pytest.raises(ValueError, match='outside the registration grid'):
        GridBoundaryStation(level_id='L01', source_volume_id='PV',
                            grid_edge=(0, 0, 9, 0)).resolve(
                                SimpleNamespace(x_lines=[0.0, 1.0], y_lines=[0.0, 1.0]))


def test_regions_and_stations_keep_using_the_authoring_grid_after_reframing():
    lattice = SimpleNamespace(
        # Structural lines were redrawn around a core after the volume was authored.
        x_lines=[-9.0, -4.0, 1.0, 9.0], y_lines=[-8.0, -1.0, 8.0],
        program_volume_x_lines=[-6.0, 0.0, 8.0],
        program_volume_y_lines=[-4.0, 3.0],
    )
    region = ProgramVolumeRegion(
        id='PV-L01-SPINE', level_id='L01', category='circulation',
        role='circulation_spine', grid_rect=(0, 0, 2, 1),
        z_base=0.6, z_top=4.8)
    assert region.resolve_bounds(lattice) == pytest.approx((-6.0, -4.0, 8.0, 3.0))
    point, tangent, outward = _intent().entry_station.resolve(lattice)
    assert point == pytest.approx((-2.5, -4.0))
    assert tangent == pytest.approx((1.0, 0.0))
    assert outward == pytest.approx((0.0, -1.0))


def test_resolved_plan_never_upgrades_missing_or_unevaluated_evidence():
    assert ResolvedCirculationPlan(intent=_intent()).status == 'unevaluated'
    reviewed = ResolvedCirculationPlan(intent=_intent(), findings=[
        CirculationFinding(id='portal', status='passed', subject='entry',
                           detail='Top landing reaches the emitted portal.'),
        CirculationFinding(id='interior', status='unevaluated', subject='route',
                           detail='Interior route is not measured.'),
    ])
    assert reviewed.status == 'unevaluated'
    refused = reviewed.model_copy(update={'findings': [
        CirculationFinding(id='fit', status='failed', subject='spine',
                           detail='The required stair does not fit.'),
    ]})
    assert refused.status == 'failed'
