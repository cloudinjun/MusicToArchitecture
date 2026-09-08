from copy import deepcopy
import math
from types import SimpleNamespace

import pytest
from shapely.geometry import Polygon

from backend.app.datums import Lattice, LevelDatum, PlanBounds
from backend.app.facade_control import (
    CANONICAL_FACADE_ROLES,
    FacadeControl,
    FacadeLevelControl,
    canonical_role_for,
    controlled_facade_metadata,
    facade_control_for,
    parallel_outboard_rings,
    validate_facade_collar,
)
from backend.app.geometry import BoxGeometry, CONVENTION_PROFILES, MemberGeometry, v2, v3
from backend.app.grammar_specs import spec_for
from backend.app.program_volume_contracts import ProgramVolumeRegion
from backend.app.tectonics import ENVELOPE_TECTONICS


class _Datums:
    def __init__(self, **values):
        self.values = values

    def value(self, name):
        return self.values[name]


def _lattice(*, source_digest: str | None = 'pv-source-abc') -> Lattice:
    ring = [v2(0.0, 0.0), v2(10.0, 0.0), v2(10.0, 8.0), v2(0.0, 8.0)]
    levels = [
        LevelDatum(index=0, id='L00', z=0.0, kind='podium', plate=ring, voids=[]),
        LevelDatum(index=1, id='L01', z=4.0, kind='occupied', plate=ring, voids=[]),
        LevelDatum(index=2, id='L02', z=8.0, kind='roof', plate=ring, voids=[]),
    ]
    return Lattice(
        levels=levels, x_lines=[0.0, 5.0, 10.0], y_lines=[0.0, 4.0, 8.0],
        apse_nodes=[], plan_x_m=10.0, plan_y_m=8.0,
        plan=PlanBounds(x_min=0.0, x_max=10.0, y_min=0.0, y_max=8.0),
        program_volume_source_digest=source_digest)


def test_parallel_offset_is_exact_for_a_concave_polygon_with_a_hole():
    boundary = [(0, 0), (12, 0), (12, 10), (7, 10), (7, 4), (0, 4)]
    voids = [[(8, 5), (10, 5), (10, 8), (8, 8)]]

    outer, holes = parallel_outboard_rings(boundary, voids, 0.5)
    actual = Polygon(outer, holes=holes)
    expected = Polygon(boundary, holes=voids).buffer(0.5, join_style=2)

    assert actual.symmetric_difference(expected).area == pytest.approx(0.0, abs=1e-8)
    assert len(actual.interiors) == 1
    # The exterior grows and the courtyard contracts by one half metre on every edge.
    assert actual.bounds == pytest.approx((-0.5, -0.5, 12.5, 10.5))
    assert Polygon(actual.interiors[0]).bounds == pytest.approx((8.5, 5.5, 9.5, 7.5))


def test_resolution_order_is_score_then_tectonic_then_grammar_clamp():
    lattice = _lattice()
    before = deepcopy(lattice.model_dump(mode='json'))
    env = ENVELOPE_TECTONICS['ENV-PANEL-FIELD']
    spec = spec_for('FCD-10-PARAMETRICISM')

    control = facade_control_for(
        lattice,
        _Datums(envelope_offset_m=0.50, shading_depth_m=0.30,
                envelope_layer_count=2),
        env, spec)

    assert control is not None
    assert control.score_offset_m == pytest.approx(0.50)
    assert control.tectonic_multiplier == pytest.approx(1.35)
    assert control.multiplied_offset_m == pytest.approx(0.675)
    assert control.grammar_depth_range_m == pytest.approx((0.04, 0.45))
    assert control.resolved_offset_m == pytest.approx(0.45)
    assert control.program_volume_source_digest == 'pv-source-abc'
    assert control.review_status == 'professional_review_required'
    assert tuple(control.canonical_roles) == CANONICAL_FACADE_ROLES
    # Resolving the downstream control cannot rewrite or re-hash the source lattice.
    assert lattice.model_dump(mode='json') == before


def test_facade_source_remains_the_authoring_union_after_floor_carving():
    lattice = _lattice()
    lattice.program_volume_x_lines = [0.0, 10.0]
    lattice.program_volume_y_lines = [0.0, 8.0]
    lattice.program_volume_regions = [ProgramVolumeRegion(
        id='PV-L01-PROGRAM-01', level_id='L01', category='public',
        role='program', space_ids=['SP-TEST'], grid_rect=(0, 0, 1, 1),
        z_base=4.0, z_top=8.0)]
    # A floor-opening ring touching the outer edge is intentionally an invalid hole.
    # Facade authority still comes from the immutable Program Volume union.
    lattice.occupied[0].voids = [[
        v2(4.0, 0.0), v2(6.0, 0.0), v2(6.0, 3.0), v2(4.0, 3.0)]]

    control = facade_control_for(
        lattice,
        _Datums(envelope_offset_m=0.50, shading_depth_m=0.30,
                envelope_layer_count=2),
        ENVELOPE_TECTONICS['ENV-PANEL-FIELD'],
        spec_for('FCD-10-PARAMETRICISM'))

    assert control is not None
    source = Polygon(
        control.levels[0].source_boundary,
        holes=control.levels[0].source_voids)
    assert source.is_valid
    assert source.area == pytest.approx(80.0)


def test_critical_regionalism_remains_provisional_without_site_range():
    control = facade_control_for(
        _lattice(),
        _Datums(envelope_offset_m=0.50, shading_depth_m=0.20,
                envelope_layer_count=1),
        ENVELOPE_TECTONICS['ENV-DEEP-LATTICE'],
        spec_for('FCD-09-CRITICAL-REGIONALISM'))

    assert control is not None
    assert control.multiplied_offset_m == pytest.approx(0.85)
    assert control.resolved_offset_m == pytest.approx(0.85)
    assert control.grammar_depth_range_m is None
    assert control.resolution_status == 'provisional_unevaluated'
    assert 'site' in control.resolution_reason


@pytest.mark.parametrize(('subsystem', 'kind', 'part_role', 'expected'), [
    ('bearing_wall', 'wall_panel', None, 'weather_skin'),
    ('bearing_wall', 'glazing_panel', None, 'recessed_infill'),
    ('edge_closure', 'external_strut', None, 'return_tie'),
    ('lattice_screen', 'lattice_mullion', None, 'outboard_screen'),
    ('expressed_frame', 'frame_expression', 'frame', 'outboard_screen'),
    ('expressed_frame', 'external_strut', 'support', 'return_tie'),
    ('expressed_frame', 'glazing_panel', 'glazing', 'recessed_infill'),
])
def test_role_adapter_preserves_high_tech_part_roles(
        subsystem, kind, part_role, expected):
    element = SimpleNamespace(
        semantic_layer='envelope', subsystem=subsystem, kind=kind,
        part_role=part_role)
    original = element.part_role

    assert canonical_role_for(element) == expected
    assert element.part_role == original


def test_shared_collar_validator_uses_canonical_weather_plane():
    level = FacadeLevelControl(
        level_id='L01', z_base=4.0, z_top=8.0,
        source_boundary=[(0, 0), (10, 0), (10, 8), (0, 8)],
        weather_boundary=[(-0.5, -0.5), (10.5, -0.5),
                          (10.5, 8.5), (-0.5, 8.5)])
    control = FacadeControl(
        program_volume_source_digest='pv-source-abc',
        grammar_id='FCD-01-INTERNATIONAL-STYLE',
        tectonic_id='ENV-CURTAIN-WALL',
        score_offset_m=0.5, tectonic_multiplier=1.0,
        multiplied_offset_m=0.5, grammar_depth_range_m=(0.0, 0.5),
        resolved_offset_m=0.5, resolution_status='resolved',
        resolution_reason='test', levels=[level])
    good = SimpleNamespace(
        id='ENV-GOOD', semantic_layer='envelope', subsystem='bearing_wall',
        kind='wall_panel', part_role=None, level_id='L01', thickness_m=None,
        geometry=BoxGeometry(center=v3(10.5, 4.0, 6.0), size=v3(0.2, 4.0, 3.0)))
    bad = SimpleNamespace(
        id='ENV-BAD', semantic_layer='envelope', subsystem='bearing_wall',
        kind='wall_panel', part_role=None, level_id='L01', thickness_m=None,
        geometry=BoxGeometry(center=v3(9.0, 4.0, 6.0), size=v3(0.2, 4.0, 3.0)))

    assert validate_facade_collar(control, [good], {}) == []
    findings = validate_facade_collar(control, [bad], {})
    assert len(findings) == 1
    assert findings[0].status == 'failed'
    assert findings[0].role == 'weather_skin'


def test_pv_facade_metadata_is_complete_and_high_tech_detail_survives():
    level = FacadeLevelControl(
        level_id='L01', z_base=4.0, z_top=8.0,
        source_boundary=[(0, 0), (10, 0), (10, 8), (0, 8)],
        weather_boundary=[(-0.5, -0.5), (10.5, -0.5),
                          (10.5, 8.5), (-0.5, 8.5)])
    control = FacadeControl(
        program_volume_source_digest='pv-source-abc',
        grammar_id='FCD-01-INTERNATIONAL-STYLE',
        tectonic_id='ENV-CURTAIN-WALL', score_offset_m=0.5,
        tectonic_multiplier=1.0, multiplied_offset_m=0.5,
        grammar_depth_range_m=(0.0, 0.5), resolved_offset_m=0.5,
        resolution_status='resolved', resolution_reason='test', levels=[level])

    assembly, role = controlled_facade_metadata(
        control, level_id='L01', semantic_layer='envelope',
        subsystem='curtain_wall', kind='glazing_panel',
        assembly_id=None, part_role=None)
    assert assembly == 'FACADE-FCD-01-INTERNATIONAL-STYLE-L01-R00'
    assert role == 'weather_skin'

    high_tech = controlled_facade_metadata(
        control, level_id='L01', semantic_layer='envelope',
        subsystem='expressed_frame', kind='frame_expression',
        assembly_id='HT-L01-B003', part_role='frame')
    assert high_tech == ('HT-L01-B003', 'frame')


def test_setback_head_return_resolves_between_adjacent_controlled_levels():
    lower = FacadeLevelControl(
        level_id='L01', z_base=4.0, z_top=8.0,
        source_boundary=[(0, 0), (10, 0), (10, 8), (0, 8)],
        weather_boundary=[(-0.5, -0.5), (10.5, -0.5),
                          (10.5, 8.5), (-0.5, 8.5)])
    upper_weather, upper_voids = parallel_outboard_rings(
        [(2, 1), (8, 1), (8, 7), (2, 7)], [], 0.5)
    upper = FacadeLevelControl(
        level_id='L02', z_base=8.0, z_top=12.0,
        source_boundary=[(2, 1), (8, 1), (8, 7), (2, 7)],
        weather_boundary=upper_weather, weather_voids=upper_voids)
    control = FacadeControl(
        program_volume_source_digest='pv-source-abc',
        grammar_id='FCD-01-INTERNATIONAL-STYLE',
        tectonic_id='ENV-CURTAIN-WALL', score_offset_m=0.5,
        tectonic_multiplier=1.0, multiplied_offset_m=0.5,
        grammar_depth_range_m=(0.0, 0.5), resolved_offset_m=0.5,
        resolution_status='resolved', resolution_reason='test',
        levels=[lower, upper])
    return_tie = SimpleNamespace(
        id='ENV-RET-L01-HEAD-S000', semantic_layer='envelope',
        subsystem='edge_closure', kind='external_strut', part_role=None,
        level_id='L01', thickness_m=None,
        geometry=MemberGeometry(
            path=[v3(10.5, 4.0, 7.9), v3(8.0, 4.0, 7.9)],
            profile='TRAN-75x140'))

    assert validate_facade_collar(
        control, [return_tie], CONVENTION_PROFILES) == []


def test_legacy_lattice_serialization_omits_null_facade_control():
    payload = _lattice(source_digest=None).model_dump(mode='json')
    assert 'facade_control' not in payload


@pytest.mark.parametrize('across_void', [False, True])
def test_return_body_cannot_cross_notch_despite_valid_endpoints(across_void):
    boundary = [(0,0),(12,0),(12,12),(8,12),(8,4),(4,4),(4,12),(0,12)]
    weather, voids = parallel_outboard_rings(boundary, [], .5)
    level = FacadeLevelControl(level_id='L01', z_base=4, z_top=8,
        source_boundary=boundary, weather_boundary=weather, weather_voids=voids)
    control = FacadeControl(program_volume_source_digest='pv-notch',
        grammar_id='FCD-01-INTERNATIONAL-STYLE', tectonic_id='ENV-CURTAIN-WALL',
        score_offset_m=.5, tectonic_multiplier=1, multiplied_offset_m=.5,
        grammar_depth_range_m=(0,.5), resolved_offset_m=.5,
        resolution_status='resolved', resolution_reason='test', levels=[level])
    member = SimpleNamespace(id='return-notch', semantic_layer='envelope',
        subsystem='edge_closure', kind='external_strut', part_role=None,
        level_id='L01', thickness_m=None,
        geometry=MemberGeometry(path=[v3(8 if across_void else 4,10,4),v3(4.5,10,4)],
                                profile='TRAN-75x140'))
    findings = validate_facade_collar(control, [member], CONVENTION_PROFILES)
    if across_void:
        assert len(findings) == 1
        assert findings[0].status == 'failed'
        assert 'return body' in findings[0].detail
        assert findings[0].measure > 0
    else:
        assert findings == []


@pytest.mark.parametrize('bearing', [0, 30, 90, 180])
def test_return_turn_uses_profile_radius_at_weather_corner(bearing):
    """A 75 x 140 mm turned section exceeds 70 mm in some plan directions."""
    angle = math.radians(bearing)

    def xy(x, y):
        return (x * math.cos(angle) - y * math.sin(angle),
                x * math.sin(angle) + y * math.cos(angle))

    boundary = [xy(x, y) for x, y in [(0, 0), (10, 0), (10, 8), (0, 8)]]
    weather, voids = parallel_outboard_rings(boundary, [], .5)
    level = FacadeLevelControl(level_id='L01', z_base=4, z_top=8,
        source_boundary=boundary, weather_boundary=weather, weather_voids=voids)
    control = FacadeControl(program_volume_source_digest='pv-corner',
        grammar_id='FCD-01-INTERNATIONAL-STYLE', tectonic_id='ENV-CURTAIN-WALL',
        score_offset_m=.5, tectonic_multiplier=1, multiplied_offset_m=.5,
        grammar_depth_range_m=(0, .5), resolved_offset_m=.5,
        resolution_status='resolved', resolution_reason='test', levels=[level])
    member = SimpleNamespace(id='return-corner', semantic_layer='envelope',
        subsystem='edge_closure', kind='external_strut', part_role=None,
        level_id='L01', thickness_m=None,
        geometry=MemberGeometry(path=[v3(*xy(.5, .5), 4),
            v3(*xy(-.5, -.5), 4), v3(*xy(-.5, -.5), 4.145)],
            profile='TRAN-75x140'))

    assert validate_facade_collar(control, [member], CONVENTION_PROFILES) == []
