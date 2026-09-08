"""Physical enclosure regressions: corners, level returns and the raised roof."""

import math
from types import SimpleNamespace

import pytest
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from backend.app.axis import AxisSkeleton
from backend.app.compiler_v3 import _Builder, _emit_roof, _record_axis_checks, _plan_approach
from backend.app.datums import Lattice, LevelDatum
from backend.app.dependencies import _Record, _contact_gap, compile_dependency_graph
from backend.app.envelope import (
    EDGE_BRACKET_PROFILE, GEOMETRY_EPS_M, _Bay, _bay_subdivided, _emit_level_returns, _emit_screen_fin,
    _registered_return_solids,
    closure_solid_bearings, emit_envelope, registered_bays, planned_entrance,
)
from backend.app.facade_gates import (
    FacadeGateReport, GateResult, evaluate as evaluate_facade,
)
from backend.app.geometry import (
    BoxGeometry, CONVENTION_PROFILES, ExtrusionGeometry, MemberGeometry, QuadGeometry, inset, v2, v3,
)
from backend.app.plan_regions import extrusions, polygon
from backend.app.portals import inspect_portals, matching_entrances, wall_run_parts
from backend.app.program_volume_contracts import ProgramVolumeRegion
from backend.app.roof import _plan_footprint, roof_control_for
from backend.app.mesh_primitives import primitive_mesh
from backend.app.tectonics import ENVELOPE_TECTONICS
from backend.app.grammar_specs import spec_for


class Datums:
    values = {
        'mullion_module_m': 2.0, 'transom_rows': 2, 'spandrel_height_m': 0.4,
        'envelope_offset_m': 0.7, 'envelope_layer_count': 1, 'edge_fascia_m': 0.55,
        'floor_to_floor_m': 4.0, 'shading_rows': 0, 'opaque_fraction': 0.3,
        'entry_canopy_span_m': 3.0, 'truss_depth_m': 1.2, 'truss_panels': 4,
        'bay_x_m': 4.0, 'bay_y_m': 4.0, 'flight_width_m': 2.4,
    }

    def __init__(self, **updates):
        self.values = {**self.values, **updates}

    def value(self, key):
        return self.values[key]

    def integer(self, key):
        return int(self.values[key])


def ring(points):
    return [v2(x, y) for x, y in points]


RECT = ring([(12, 0), (0, 0), (0, 8), (12, 8)])


def builder(plates=None, *, slab_holes=None, datum_updates=None):
    plates = plates or [RECT, RECT, RECT]
    levels = [LevelDatum(index=i, id=f'L{i:02d}', z=i * 4.0,
                         kind='podium' if i == 0 else 'roof' if i == len(plates) - 1
                         else 'occupied', plate=plate, voids=[])
              for i, plate in enumerate(plates)]
    lattice = Lattice(levels=levels, x_lines=[3.0, 6.0, 9.0],
                      y_lines=[0.0, 4.0, 8.0], apse_nodes=[],
                      plan_x_m=12.0, plan_y_m=8.0)
    # Use the real storage/geometry builder without running the unrelated core planner.
    b = _Builder.__new__(_Builder)
    b.datums, b.lattice, b.axis = Datums(**(datum_updates or {})), lattice, AxisSkeleton()
    b.cores = {'width': 0.0, 'run': 0.0, 'primary': None,
               'second': None, 'extras': []}
    b.groups, b.count, b.element_ids = {}, 0, set()
    b.element_kinds, b.element_levels = {}, {}
    b.profiles = dict(CONVENTION_PROFILES)
    for level in levels:
        holes = (slab_holes or {}).get(level.index, [])
        b.add_plate(f'STR-SLB-{level.id}', 'floor_slab', 'structure', 'slabs',
                    level.plate, holes, level.z - 0.3, level.z, 'concrete_light',
                    level_id=level.id)
    return b


def elements(b):
    return [element for group in b.groups.values() for element in group.expand()]


def add_entry_landing(b):
    b.approach = _plan_approach(b.lattice, b.datums)
    x0,y0,x1,y1 = b.approach['entry']
    level = b.lattice.occupied[0]
    b.add('CIR-LND-ENTRY', 'stair_landing', 'circulation', 'entry_approach',
          BoxGeometry(center=v3((x0+x1)/2,(y0+y1)/2,level.z-.1),
                      size=v3(x1-x0,y1-y0,.2)), 'concrete_light', level_id=level.id)
    return planned_entrance(b.lattice, b.datums, b.approach)


def portal_model(b):
    return SimpleNamespace(element_groups=list(b.groups.values()), elements=elements(b),
                           lattice=b.lattice, profiles=b.profiles)


def facade_model(b, grammar_id='FCD-05-HIGH-TECH'):
    return SimpleNamespace(
        facade_grammar_id=grammar_id,
        envelope_tectonic_id='ENV-EXPRESSED-FRAME',
        element_groups=list(b.groups.values()), elements=elements(b),
        lattice=b.lattice, datum_set=b.datums, profiles=b.profiles)


def add_program_volume_regions(b, *, all_public=False):
    """Attach authored-grid regions without borrowing the mutable structural grid."""
    b.lattice.program_volume_x_lines = [0.0, 6.0, 12.0]
    b.lattice.program_volume_y_lines = [0.0, 8.0]
    b.lattice.program_volume_regions = [
        ProgramVolumeRegion(
            id='PV-PUBLIC', level_id='L01', category='public', role='program',
            space_ids=['SP-PUBLIC'], grid_rect=(0, 0, 1, 1),
            z_base=4.0, z_top=8.0),
        ProgramVolumeRegion(
            id='PV-EAST', level_id='L01',
            category='public' if all_public else 'service', role='program',
            space_ids=['SP-EAST'], grid_rect=(1, 0, 2, 1),
            z_base=4.0, z_top=8.0),
    ]


def horizontal_section(b, z, *, subsystem=None):
    lines = []
    for element in elements(b):
        g = element.geometry
        if (not isinstance(g, QuadGeometry)
                or (subsystem and element.subsystem != subsystem)):
            continue
        low, high = min(p.z for p in g.corners), max(p.z for p in g.corners)
        if low <= z <= high and high - low > 0.01:
            lines.append(LineString([(g.corners[0].x, g.corners[0].y),
                                     (g.corners[1].x, g.corners[1].y)]))
    return unary_union(lines)


@pytest.mark.parametrize('shift,scale', [((0, 0), 1), ((103, -49), 1.7)])
def test_registration_keeps_every_corner_and_every_short_edge(shift, scale):
    source = [(12, 0), (0, 0), (0, 8), (11.8, 8), (12, 7.8)]
    plate = ring([(shift[0] + x * scale, shift[1] + y * scale) for x, y in source])
    spans = registered_bays(plate, 2.0, 0.9, stagger=True)
    for edge in range(len(plate)):
        intervals = [(lo, hi) for ei, lo, hi in spans if ei == edge]
        assert intervals[0][0] == 0.0 and intervals[-1][1] == 1.0
        assert all(first[1] == second[0] for first, second in zip(intervals, intervals[1:]))


def test_impossible_short_window_becomes_visible_solid_closure():
    plate = ring([(12, 0), (0, 0), (0, 8), (11.8, 8), (12, 7.8)])
    b = builder([plate] * 3, datum_updates={'envelope_offset_m': 0.0})
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-PUNCHED-WALL'])
    closures = [e for e in elements(b) if e.id.startswith('ENV-CLOSE-')]
    assert closures and all(e.supports for e in closures)
    assert all('ENVELOPE-CLOSURE-UNRESOLVED-GRAMMAR' in e.rule_refs for e in closures)
    # Read the actual wall foot, not a requested bay count. Deleting the short bay
    # or joining across the bevel leaves measurable uncovered perimeter here.
    section = horizontal_section(b, b.lattice.occupied[0].z + 0.05)
    assert polygon(plate).boundary.difference(section.buffer(1e-5)).length < 1e-4
    for e in elements(b):
        if e.id.startswith('ENV-GLZ-') and e.kind == 'glazing_panel':
            a, c = e.geometry.corners[:2]
            assert Point(a.x, a.y).distance(Point(c.x, c.y)) >= 0.3 - 1e-5


def test_high_tech_short_closure_has_a_real_same_assembly_slab_route():
    plate = ring([(12, 0), (0, 0), (0, 8), (11.8, 8), (12, 7.8)])
    b = builder([plate] * 3)
    add_program_volume_regions(b)
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))

    closure = next(element for element in elements(b)
                   if element.id.startswith('ENV-CLOSE-L01-'))
    assert len(closure.supports) == 1
    bracket = next(element for element in elements(b)
                   if element.id == closure.supports[0])
    assert bracket.id.startswith('ENV-CLOSE-BKT-L01-')
    assert bracket.part_role == 'support'
    assert bracket.assembly_id == closure.assembly_id
    assert len(bracket.supports) == 1
    slab = next(element for element in elements(b)
                if element.id == bracket.supports[0])
    assert slab.kind == 'floor_slab'

    before = {closure.id: tuple(closure.supports),
              bracket.id: tuple(bracket.supports)}
    compile_dependency_graph(list(b.groups.values()))
    after = {element.id: tuple(element.supports) for element in elements(b)
             if element.id in before}
    assert after == before
    bearings, misses = closure_solid_bearings(b)
    assert bracket.id in bearings
    assert bracket.id not in misses

    gates = {gate.id: gate for gate in evaluate_facade(facade_model(b)).gates}
    assert gates['high_tech_interfaces'].verdict == 'passed'
    assert gates['high_tech_interfaces'].measured == pytest.approx(1.0)
    assert gates['high_tech_standard_component_share'].verdict == 'unevaluated'
    assert gates['closure_grammar'].verdict == 'unevaluated'


def test_staggered_course_keeps_both_end_panels():
    b = builder([RECT] * 4)
    env = ENVELOPE_TECTONICS['ENV-FACETED-PANEL']
    emit_envelope(b, env)
    level = b.lattice.occupied[1]
    boundary = polygon(inset(level.plate, -b.datums.value('envelope_offset_m'))).boundary
    section = horizontal_section(b, level.z + 0.05)
    assert boundary.difference(section.buffer(1e-5)).length < 1e-4


def test_recessed_skin_meets_original_slab_boundary_in_both_windings():
    for plate in (RECT, list(reversed(RECT))):
        b = builder([plate] * 3)
        emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'])
        glass = [e for e in elements(b) if e.kind == 'glazing_panel'
                 and e.subsystem == 'expressed_frame']
        assert glass
        boundary = polygon(plate).boundary
        assert max(boundary.distance(Point(p.x, p.y)) for e in glass
                   for p in e.geometry.corners) < 1e-5
        frames = [e for e in elements(b) if e.kind == 'frame_expression']
        assert any(boundary.distance(Point(e.geometry.path[0].x,
                                           e.geometry.path[0].y)) > 0.1 for e in frames)


def test_high_tech_and_brutalism_use_different_operations_on_the_same_massing():
    high_tech = builder(datum_updates={'envelope_offset_m': 0.0})
    add_program_volume_regions(high_tech)
    brutalism = builder(datum_updates={'envelope_offset_m': 0.0})
    emit_envelope(high_tech, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    emit_envelope(brutalism, ENVELOPE_TECTONICS['ENV-PUNCHED-WALL'],
                  spec_for('FCD-03-BRUTALISM'))
    high_kinds = {element.kind for element in elements(high_tech)}
    brutal_kinds = {element.kind for element in elements(brutalism)}
    assert {'frame_expression', 'external_strut', 'solid_wall_panel'} <= high_kinds
    assert {'wall_panel', 'window_reveal', 'glazing_panel'} <= brutal_kinds
    assert 'frame_expression' not in brutal_kinds
    assert 'window_reveal' not in high_kinds


def test_high_tech_programme_puts_more_cassettes_at_service_than_public_bays():
    b = builder(datum_updates={'envelope_offset_m': 0.0, 'opaque_fraction': 0.35})
    b.program_allocation = SimpleNamespace(zones=[
        SimpleNamespace(level_id='L01', category='public', space_id='SP-PUBLIC',
                        x0=0.0, y0=0.0, x1=6.0, y1=8.0),
        SimpleNamespace(level_id='L01', category='service', space_id='SP-SERVICE',
                        x0=6.0, y0=0.0, x1=12.0, y1=8.0),
    ])
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    infill = [element for element in elements(b)
              if element.subsystem == 'expressed_frame'
              and element.part_role in {'cassette', 'glazing'}]
    by_category = {
        category: [element for element in infill if element.category == category]
        for category in ('public', 'service')}
    assert all(by_category.values())

    def opaque_share(items):
        return sum(item.part_role == 'cassette' for item in items) / len(items)

    assert opaque_share(by_category['service']) > opaque_share(by_category['public'])
    assert {item.program for item in by_category['service']} == {'SP-SERVICE'}


@pytest.mark.parametrize('rows,expected', [(2, 1), (3, 3), (4, 5)])
def test_high_tech_score_density_emits_one_to_five_real_secondary_members(rows, expected):
    b = builder(datum_updates={'envelope_offset_m': 0.0, 'transom_rows': rows})
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    secondaries = [element for element in elements(b)
                   if element.subsystem == 'expressed_frame'
                   and element.kind == 'external_strut'
                   and 'secondary' in element.lattice_index
                   and 'DENSITY_TO_FACADE' in element.rule_refs]
    counts = {}
    for element in secondaries:
        counts[element.assembly_id] = counts.get(element.assembly_id, 0) + 1
        assert element.supports
        assert all(host in b.element_ids for host in element.supports)
    assert counts and set(counts.values()) == {expected}
    gate = next(gate for gate in evaluate_facade(facade_model(b)).gates
                if gate.id == 'high_tech_secondary_density')
    assert gate.verdict == 'passed'


def test_high_tech_gates_distinguish_pass_fail_and_unpublished_measurements():
    import copy

    b = builder(datum_updates={'envelope_offset_m': 0.0, 'transom_rows': 3})
    add_program_volume_regions(b)
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    model = facade_model(b)
    report = evaluate_facade(model)
    gates = {gate.id: gate for gate in report.gates}
    assert gates['opening_ratio'].verdict == 'unevaluated'
    assert gates['material_families'].verdict == 'unevaluated'
    for gate_id in ('high_tech_assembly_metadata', 'high_tech_system_roles',
                    'high_tech_primary_bay', 'high_tech_enclosure_submodule',
                    'high_tech_system_depth', 'high_tech_interfaces',
                    'high_tech_program_control', 'high_tech_secondary_density',
                    'high_tech_standard_component_share'):
        assert gates[gate_id].verdict == 'passed', gates[gate_id]
    assert report.status == 'unevaluated'
    assert not report.passed
    facade = [element for element in model.elements
              if element.semantic_layer == 'envelope'
              and element.subsystem not in {'roof', 'roof_closure', 'parapet', 'canopy'}]
    assert all(element.assembly_id and element.part_role for element in facade)
    assert {'frame', 'support', 'enclosure', 'cassette', 'glazing'} <= {
        element.part_role for element in facade}

    damaged = copy.deepcopy(model)
    victim = next(element for element in damaged.elements
                  if element.part_role == 'cassette')
    victim.assembly_id = None
    damaged_report = evaluate_facade(damaged)
    assert next(gate for gate in damaged_report.gates
                if gate.id == 'high_tech_assembly_metadata').verdict == 'failed'

    no_datum = copy.deepcopy(model)
    no_datum.datum_set = None
    no_datum_report = evaluate_facade(no_datum)
    assert next(gate for gate in no_datum_report.gates
                if gate.id == 'high_tech_secondary_density').verdict == 'unevaluated'


def test_facade_report_status_is_strictly_three_valued():
    def result(verdict):
        return GateResult(id=verdict, invariant_ref='TEST', verdict=verdict,
                          required='test', detail='test')

    def report(gates):
        return FacadeGateReport(grammar_id='FCD-05-HIGH-TECH',
                                grammar_label='High-Tech', guide_ref='guide',
                                gates=gates)

    assert report([]).status == 'unevaluated'
    assert report([result('passed')]).status == 'passed'
    assert report([result('passed'), result('unevaluated')]).status == 'unevaluated'
    assert report([result('passed'), result('failed'),
                   result('unevaluated')]).status == 'failed'
    assert report([result('passed')]).passed
    assert not report([result('unevaluated')]).passed
    assert report([result('unevaluated')]).model_dump()['status'] == 'unevaluated'


@pytest.mark.parametrize('requested,realised', [
    (0.0, 0.6), (0.6, 0.6), (1.7, 1.7), (2.4, 2.4), (4.0, 2.4),
])
def test_high_tech_depth_clamps_without_moving_primary_or_submodules(requested, realised):
    b = builder(datum_updates={'envelope_offset_m': requested})
    add_program_volume_regions(b)
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    report = evaluate_facade(facade_model(b))
    gates = {gate.id: gate for gate in report.gates}
    assert gates['high_tech_primary_bay'].verdict == 'passed'
    assert gates['high_tech_primary_bay'].measured == pytest.approx(4.0)
    assert gates['high_tech_enclosure_submodule'].verdict == 'passed'
    assert gates['high_tech_enclosure_submodule'].measured == pytest.approx(
        4.0 / 3.0, abs=1.0e-4)
    assert gates['high_tech_system_depth'].verdict == 'passed'
    assert gates['high_tech_system_depth'].measured == pytest.approx(realised)
    assert {element.assembly_id for element in elements(b)
            if element.assembly_id and element.assembly_id.startswith('HTA-')} == {
        f'HTA-L01-S{index:03d}' for index in range(10)}


def test_high_tech_all_public_volume_needs_no_fabricated_cassette():
    b = builder()
    add_program_volume_regions(b, all_public=True)
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    infill = [element for element in elements(b)
              if element.assembly_id and element.assembly_id.startswith('HTA-')
              and element.part_role in {'cassette', 'glazing'}]
    assert infill and {element.part_role for element in infill} == {'glazing'}
    gates = {gate.id: gate for gate in evaluate_facade(facade_model(b)).gates}
    assert gates['high_tech_system_roles'].verdict == 'passed'
    assert gates['high_tech_program_control'].verdict == 'passed'


def test_high_tech_program_regions_keep_their_authoring_grid_after_frame_regrid():
    b = builder()
    add_program_volume_regions(b)
    # Core framing may insert/reorder structural lines after Program Volumes were
    # authored. These arrays deliberately no longer match the region indices.
    b.lattice.x_lines = [-20.0, -10.0, 30.0, 50.0]
    b.lattice.y_lines = [-30.0, 40.0, 70.0]
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    infill = [element for element in elements(b)
              if element.part_role in {'cassette', 'glazing'}]
    assert {'public', 'service'} <= {element.category for element in infill}
    # The programme line is an actual enclosure station. No panel may acquire its
    # category from one midpoint while crossing into the other authored volume.
    horizontal = [element for element in infill
                  if abs(element.geometry.corners[0].y
                         - element.geometry.corners[1].y) < 1.0e-6]
    assert horizontal
    assert all(not (min(point.x for point in element.geometry.corners) < 6.0 - 1.0e-6
                    and max(point.x for point in element.geometry.corners) > 6.0 + 1.0e-6)
               for element in horizontal)
    assert next(gate for gate in evaluate_facade(facade_model(b)).gates
                if gate.id == 'high_tech_program_control').verdict == 'passed'


def test_high_tech_bay_program_uses_volume_height_not_same_level_list_order():
    b = builder()
    b.lattice.program_volume_x_lines = [0.0, 12.0]
    b.lattice.program_volume_y_lines = [0.0, 8.0]
    b.lattice.program_volume_regions = [
        ProgramVolumeRegion(
            id='PV-ABOVE', level_id='L01', category='service', role='program',
            space_ids=['SP-ABOVE'], grid_rect=(0, 0, 1, 1),
            z_base=100.0, z_top=104.0),
        ProgramVolumeRegion(
            id='PV-L01', level_id='L01', category='public', role='program',
            space_ids=['SP-L01'], grid_rect=(0, 0, 1, 1),
            z_base=4.0, z_top=8.0),
    ]
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    infill = [element for element in elements(b)
              if element.part_role in {'cassette', 'glazing'}
              and 'HT-PROGRAM-HUMAN-EXEMPT' not in element.rule_refs]
    assert infill
    assert {element.program for element in infill} == {'SP-L01'}
    assert {element.part_role for element in infill} == {'glazing'}


def test_high_tech_program_fallback_cannot_receive_a_program_control_pass():
    b = builder()
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    gate = next(gate for gate in evaluate_facade(facade_model(b)).gates
                if gate.id == 'high_tech_program_control')
    assert gate.verdict == 'unevaluated'


def test_high_tech_standard_share_is_independent_of_secondary_density():
    shares = []
    for rows in (2, 4):
        b = builder(datum_updates={'transom_rows': rows})
        add_program_volume_regions(b)
        emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                      spec_for('FCD-05-HIGH-TECH'))
        gate = next(gate for gate in evaluate_facade(facade_model(b)).gates
                    if gate.id == 'high_tech_standard_component_share')
        assert 'ID denominator' in gate.detail
        shares.append(gate.measured)
    assert shares[0] == shares[1]


def test_high_tech_standard_share_keeps_required_entry_and_edge_kits_in_scope():
    shares = []
    for with_entry in (False, True):
        b = builder()
        add_program_volume_regions(b)
        if with_entry:
            add_entry_landing(b)
        emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                      spec_for('FCD-05-HIGH-TECH'))
        gate = next(gate for gate in evaluate_facade(facade_model(b)).gates
                    if gate.id == 'high_tech_standard_component_share')
        assert gate.verdict == 'passed', gate
        assert gate.measured >= 0.80
        if with_entry:
            program_gate = next(
                item for item in evaluate_facade(facade_model(b)).gates
                if item.id == 'high_tech_program_control')
            assert program_gate.verdict == 'passed', program_gate
            assert 'explicit human/program exemption' in program_gate.detail
        shares.append(gate.measured)
    assert shares[1] <= shares[0]


def test_high_tech_explicit_special_assemblies_enter_only_one_denominator_class():
    import copy

    b = builder()
    add_program_volume_regions(b)
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    base = facade_model(b)
    baseline = next(gate for gate in evaluate_facade(base).gates
                    if gate.id == 'high_tech_standard_component_share')
    damaged = copy.deepcopy(base)
    primary_ids = sorted({element.assembly_id for element in damaged.elements
                          if element.assembly_id
                          and element.assembly_id.startswith('HTA-')})
    for element in damaged.elements:
        if element.assembly_id == primary_ids[0]:
            element.rule_refs.append('HT-SPECIAL-COMPONENT')
    one_special = next(gate for gate in evaluate_facade(damaged).gates
                       if gate.id == 'high_tech_standard_component_share')
    assert one_special.measured < baseline.measured
    assert '1 named special' in one_special.detail

    for element in damaged.elements:
        if element.assembly_id in primary_ids[1:3]:
            element.rule_refs.append('HT-SPECIAL-COMPONENT')
    three_special = next(gate for gate in evaluate_facade(damaged).gates
                         if gate.id == 'high_tech_standard_component_share')
    assert three_special.verdict == 'failed'


def test_high_tech_unrelated_structural_supports_fail_geometric_interfaces():
    import copy

    b = builder()
    add_program_volume_regions(b)
    b.add_plate('STR-SLB-FAR', 'floor_slab', 'structure', 'slabs',
                ring([(50, 50), (60, 50), (60, 60), (50, 60)]), [],
                3.7, 4.0, 'concrete_light', level_id='L01')
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    model = copy.deepcopy(facade_model(b))
    for element in model.elements:
        if element.semantic_layer == 'envelope' and element.subsystem not in {
                'roof', 'roof_closure', 'parapet', 'canopy'}:
            element.supports = ['STR-SLB-FAR']
    gate = next(gate for gate in evaluate_facade(model).gates
                if gate.id == 'high_tech_interfaces')
    assert gate.verdict == 'failed'
    assert 'no_contact' in gate.detail


@pytest.mark.parametrize('rows', [2, 3, 4])
def test_high_tech_declared_interfaces_survive_the_real_dependency_graph(rows):
    b = builder(datum_updates={'transom_rows': rows})
    add_program_volume_regions(b)
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    before = {
        element.id: tuple(element.supports) for element in elements(b)
        if element.semantic_layer == 'envelope'
        and element.subsystem not in {'roof', 'roof_closure', 'parapet', 'canopy'}
    }
    assert before and all(before.values())
    compile_dependency_graph(list(b.groups.values()))
    after = {
        element.id: tuple(element.supports) for element in elements(b)
        if element.id in before
    }
    assert after == before
    profiles = {key: value.model_dump() for key, value in b.profiles.items()}
    for element in elements(b):
        if (element.semantic_layer == 'envelope'
                and element.assembly_id
                and isinstance(element.geometry, MemberGeometry)):
            primitive_mesh(element.geometry.model_dump(), profiles)
    gate = next(gate for gate in evaluate_facade(facade_model(b)).gates
                if gate.id == 'high_tech_interfaces')
    assert gate.verdict == 'passed', gate


def test_high_tech_entry_jamb_keeps_its_bracket_chain_through_dependency_graph():
    b = builder()
    add_program_volume_regions(b)
    add_entry_landing(b)
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    jambs = [element for element in elements(b)
             if element.subsystem == 'entrance' and element.kind == 'wall_panel']
    assert len(jambs) == 2
    declared = {element.id: tuple(element.supports) for element in jambs}
    assert all(hosts and hosts[0].startswith('ENV-ENT-')
               for hosts in declared.values())
    compile_dependency_graph(list(b.groups.values()))
    assert {element.id: tuple(element.supports) for element in elements(b)
            if element.id in declared} == declared
    gate = next(gate for gate in evaluate_facade(facade_model(b)).gates
                if gate.id == 'high_tech_interfaces')
    assert gate.verdict == 'passed', gate


def test_high_tech_illegal_part_role_fails_interface_gate():
    import copy

    b = builder()
    add_program_volume_regions(b)
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    model = copy.deepcopy(facade_model(b))
    next(element for element in model.elements
         if element.assembly_id and element.assembly_id.startswith('HTA-')).part_role = 'ornament'
    assert next(gate for gate in evaluate_facade(model).gates
                if gate.id == 'high_tech_interfaces').verdict == 'failed'


def test_high_tech_finalizer_does_not_relabel_an_unknown_kind_as_enclosure():
    b = builder()
    add_program_volume_regions(b)
    b.add(
        'ENV-UNKNOWN-L01', 'field_panel', 'envelope', 'unknown_system',
        QuadGeometry(corners=[v3(1.0, 0.0, 4.0), v3(2.0, 0.0, 4.0),
                              v3(2.0, 0.0, 5.0), v3(1.0, 0.0, 5.0)]),
        'steel_light', level_id='L01')
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    unknown = next(element for element in elements(b)
                   if element.id == 'ENV-UNKNOWN-L01')
    assert unknown.assembly_id is None
    assert unknown.part_role is None
    gate = next(gate for gate in evaluate_facade(facade_model(b)).gates
                if gate.id == 'high_tech_assembly_metadata')
    assert gate.verdict == 'failed'
    assert unknown.id in gate.detail


def test_high_tech_module_and_depth_damage_fail_their_dedicated_gates():
    import copy

    b = builder(datum_updates={'envelope_offset_m': 1.0})
    add_program_volume_regions(b)
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    base = facade_model(b)

    primary = copy.deepcopy(base)
    span = next(element for element in primary.elements
                if element.part_role == 'frame'
                and 'primary_span' in element.lattice_index)
    a, c = span.geometry.path
    length = math.hypot(c.x - a.x, c.y - a.y)
    span.geometry = span.geometry.model_copy(update={'path': [
        a, v3(a.x + (c.x - a.x) / length * 10.0,
              a.y + (c.y - a.y) / length * 10.0, c.z)]})
    assert next(gate for gate in evaluate_facade(primary).gates
                if gate.id == 'high_tech_primary_bay').verdict == 'failed'

    submodule = copy.deepcopy(base)
    panel = next(element for element in submodule.elements
                 if element.part_role in {'cassette', 'glazing'})
    a, c, d, e = panel.geometry.corners
    length = math.hypot(c.x - a.x, c.y - a.y)
    ux, uy = (c.x - a.x) / length, (c.y - a.y) / length
    panel.geometry = QuadGeometry(corners=[
        a, v3(a.x + ux * 2.2, a.y + uy * 2.2, c.z),
        v3(e.x + ux * 2.2, e.y + uy * 2.2, d.z), e])
    assert next(gate for gate in evaluate_facade(submodule).gates
                if gate.id == 'high_tech_enclosure_submodule').verdict == 'failed'

    depth = copy.deepcopy(base)
    assembly = next(element.assembly_id for element in depth.elements
                    if element.part_role in {'cassette', 'glazing'})
    frame = next(element for element in depth.elements
                 if element.assembly_id == assembly and element.part_role == 'frame'
                 and 'primary_span' not in element.lattice_index)
    infill = [element for element in depth.elements
              if element.assembly_id == assembly
              and element.part_role in {'cassette', 'glazing'}]
    dx = frame.geometry.path[0].x - infill[0].geometry.corners[0].x
    dy = frame.geometry.path[0].y - infill[0].geometry.corners[0].y
    infill[0].geometry = QuadGeometry(corners=[
        v3(point.x + dx, point.y + dy, point.z)
        for point in infill[0].geometry.corners])
    assert next(gate for gate in evaluate_facade(depth).gates
                if gate.id == 'high_tech_system_depth').verdict == 'failed'

    moved_frame = copy.deepcopy(base)
    assembly = next(element.assembly_id for element in moved_frame.elements
                    if element.part_role in {'cassette', 'glazing'})
    frame = next(element for element in moved_frame.elements
                 if element.assembly_id == assembly and element.part_role == 'frame'
                 and 'primary_span' not in element.lattice_index)
    panel = next(element for element in moved_frame.elements
                 if element.assembly_id == assembly
                 and element.part_role in {'cassette', 'glazing'})
    dx = frame.geometry.path[0].x - panel.geometry.corners[0].x
    dy = frame.geometry.path[0].y - panel.geometry.corners[0].y
    frame.geometry = frame.geometry.model_copy(update={'path': [
        v3(point.x + 3.0 * dx, point.y + 3.0 * dy, point.z)
        for point in frame.geometry.path
    ]})
    assert next(gate for gate in evaluate_facade(moved_frame).gates
                if gate.id == 'high_tech_system_depth').verdict == 'failed'


def test_high_tech_hard_failure_outranks_unresolved_special_assemblies():
    import copy

    b = builder()
    b.lattice.program_volume_x_lines = [0.0, 4.2, 12.0]
    b.lattice.program_volume_y_lines = [0.0, 8.0]
    b.lattice.program_volume_regions = [
        ProgramVolumeRegion(
            id='PV-NARROW', level_id='L01', category='public', role='program',
            space_ids=['SP-NARROW'], grid_rect=(0, 0, 1, 1),
            z_base=4.0, z_top=8.0),
        ProgramVolumeRegion(
            id='PV-WIDE', level_id='L01', category='service', role='program',
            space_ids=['SP-WIDE'], grid_rect=(1, 0, 2, 1),
            z_base=4.0, z_top=8.0),
    ]
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    base = facade_model(b)
    assert any('HT-SUBMODULE-PROGRAM-BOUNDARY-UNRESOLVED' in element.rule_refs
               for element in base.elements)

    primary = copy.deepcopy(base)
    span = next(element for element in primary.elements
                if element.part_role == 'frame'
                and 'primary_span' in element.lattice_index
                and 'HT-PRIMARY-BAY-UNRESOLVED' not in element.rule_refs)
    a, c = span.geometry.path
    length = math.hypot(c.x - a.x, c.y - a.y)
    span.geometry = span.geometry.model_copy(update={'path': [
        a, v3(a.x + (c.x - a.x) / length * 10.0,
              a.y + (c.y - a.y) / length * 10.0, c.z)]})
    assert next(gate for gate in evaluate_facade(primary).gates
                if gate.id == 'high_tech_primary_bay').verdict == 'failed'

    submodule = copy.deepcopy(base)
    panel = next(element for element in submodule.elements
                 if element.part_role in {'cassette', 'glazing'}
                 and 'HT-SUBMODULE-PROGRAM-BOUNDARY-UNRESOLVED'
                 not in element.rule_refs)
    a, c, d, e = panel.geometry.corners
    length = math.hypot(c.x - a.x, c.y - a.y)
    ux, uy = (c.x - a.x) / length, (c.y - a.y) / length
    panel.geometry = QuadGeometry(corners=[
        a, v3(a.x + ux * 2.2, a.y + uy * 2.2, c.z),
        v3(e.x + ux * 2.2, e.y + uy * 2.2, d.z), e])
    assert next(gate for gate in evaluate_facade(submodule).gates
                if gate.id == 'high_tech_enclosure_submodule').verdict == 'failed'

    programme = copy.deepcopy(base)
    victim = next(element for element in programme.elements
                  if element.part_role in {'cassette', 'glazing'}
                  and 'HT-SUBMODULE-PROGRAM-BOUNDARY-UNRESOLVED'
                  not in element.rule_refs)
    if victim.category in {'service', 'private'}:
        victim.category, victim.part_role = 'public', 'glazing'
    else:
        victim.category, victim.part_role = 'service', 'cassette'
    assert next(gate for gate in evaluate_facade(programme).gates
                if gate.id == 'high_tech_program_control').verdict == 'failed'


def test_high_tech_program_metadata_cannot_self_certify_against_volume_geometry():
    import copy

    b = builder()
    add_program_volume_regions(b)
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    model = copy.deepcopy(facade_model(b))
    victim = next(element for element in model.elements
                  if element.part_role == 'cassette')
    victim.category = 'public'
    victim.part_role = 'glazing'
    # The provenance token remains present; the independent region lookup must still
    # catch the false relabelling.
    assert 'PROGRAM_VOLUME_TO_FACADE' in victim.rule_refs
    assert next(gate for gate in evaluate_facade(model).gates
                if gate.id == 'high_tech_program_control').verdict == 'failed'


def test_high_tech_program_gate_reads_the_whole_panel_not_only_its_midpoint():
    import copy

    b = builder()
    add_program_volume_regions(b)
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    model = copy.deepcopy(facade_model(b))
    victim = next(
        element for element in model.elements
        if element.part_role == 'glazing'
        and element.category == 'public'
        and abs(element.geometry.corners[0].y
                - element.geometry.corners[1].y) < 1.0e-6
        and max(point.x for point in element.geometry.corners) == pytest.approx(6.0)
    )
    victim.geometry = QuadGeometry(corners=[
        v3(6.20, point.y, point.z) if abs(point.x - 6.0) < 1.0e-6 else point
        for point in victim.geometry.corners
    ])
    gate = next(gate for gate in evaluate_facade(model).gates
                if gate.id == 'high_tech_program_control')
    assert gate.verdict == 'failed'
    assert victim.id in gate.detail


def test_high_tech_subminimum_program_boundary_fragment_stays_special_and_unevaluated():
    b = builder()
    b.lattice.program_volume_x_lines = [0.0, 4.2, 12.0]
    b.lattice.program_volume_y_lines = [0.0, 8.0]
    b.lattice.program_volume_regions = [
        ProgramVolumeRegion(
            id='PV-NARROW', level_id='L01', category='public', role='program',
            space_ids=['SP-NARROW'], grid_rect=(0, 0, 1, 1),
            z_base=4.0, z_top=8.0),
        ProgramVolumeRegion(
            id='PV-WIDE', level_id='L01', category='service', role='program',
            space_ids=['SP-WIDE'], grid_rect=(1, 0, 2, 1),
            z_base=4.0, z_top=8.0),
    ]
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    unresolved = [element for element in elements(b)
                  if 'HT-SUBMODULE-PROGRAM-BOUNDARY-UNRESOLVED'
                  in element.rule_refs]
    assert unresolved
    assert all(element.assembly_id.startswith('HTS-') for element in unresolved)
    gates = {gate.id: gate for gate in evaluate_facade(facade_model(b)).gates}
    assert gates['high_tech_enclosure_submodule'].verdict == 'unevaluated'
    assert gates['high_tech_program_control'].verdict == 'unevaluated'


def test_high_tech_program_gate_includes_short_edge_special_assemblies():
    import copy

    chamfered = ring([(12, 0), (0, 0), (0, 8), (11, 8), (12, 7)])
    b = builder([chamfered, chamfered, chamfered])
    add_program_volume_regions(b)
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    base = facade_model(b)
    special = next(element for element in base.elements
                   if element.assembly_id and element.assembly_id.endswith('-EDGE')
                   and element.part_role in {'cassette', 'glazing'})
    gates = {gate.id: gate for gate in evaluate_facade(base).gates}
    assert gates['high_tech_primary_bay'].verdict == 'unevaluated'
    assert gates['high_tech_program_control'].verdict == 'passed'
    assert gates['high_tech_standard_component_share'].verdict == 'passed'
    assert '1 named special' in gates['high_tech_standard_component_share'].detail

    damaged = copy.deepcopy(base)
    victim = next(element for element in damaged.elements if element.id == special.id)
    if victim.category in {'service', 'private'}:
        victim.category, victim.part_role = 'public', 'glazing'
    else:
        victim.category, victim.part_role = 'service', 'cassette'
    gate = next(gate for gate in evaluate_facade(damaged).gates
                if gate.id == 'high_tech_program_control')
    assert gate.verdict == 'failed'
    assert victim.id in gate.detail


@pytest.mark.parametrize('z_base,z_top', [(100.0, 104.0), (5.0, 7.0)])
def test_high_tech_program_gate_rejects_same_level_metadata_at_the_wrong_height(
        z_base, z_top):
    import copy

    b = builder()
    add_program_volume_regions(b)
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'],
                  spec_for('FCD-05-HIGH-TECH'))
    model = copy.deepcopy(facade_model(b))
    service = next(region for region in model.lattice.program_volume_regions
                   if region.category == 'service')
    service.z_base, service.z_top = z_base, z_top
    gate = next(gate for gate in evaluate_facade(model).gates
                if gate.id == 'high_tech_program_control')
    assert gate.verdict == 'failed'
    assert 'outside_program_volume_z' in gate.detail


def test_controlled_head_preserves_upper_authored_void():
    from backend.app.facade_control import facade_control_for
    upper = ring([(11, 1), (1, 1), (1, 7), (11, 7)])
    hole = ring([(4, 3), (6, 3), (6, 5), (4, 5)])
    b = builder([RECT, RECT, upper], slab_holes={2: [hole]})
    b.lattice.levels[2].voids = [hole]
    b.lattice.program_volume_source_digest = 'upper-opening-regression'
    env = ENVELOPE_TECTONICS['ENV-CURTAIN-WALL']
    b.lattice.facade_control = facade_control_for(
        b.lattice, b.datums, env, spec_for('FCD-01-INTERNATIONAL-STYLE'))
    # Later floor carving can turn an authored inner hole into an edge notch.
    # The immutable control still owns the original source opening.
    b.lattice.levels[2].voids = []
    skin = ring(b.lattice.facade_control.level('L01').weather_boundary)
    _emit_level_returns(b, b.lattice.levels[1], b.lattice.levels[2], skin, [], env)
    returns = [e for e in elements(b) if e.id.startswith('ENV-RET-L01-HEAD-P')]
    region = unary_union([polygon(e.geometry.boundary) for e in returns])
    assert region.intersection(polygon(hole)).area == pytest.approx(0)
    expected = polygon(skin).difference(polygon(upper))
    assert region.symmetric_difference(expected).area < 1e-4


def test_returns_close_exact_offset_and_step_but_keep_internal_void_open():
    upper = ring([(11, 1), (1, 1), (1, 7), (11, 7)])
    hole = ring([(4, 3), (6, 3), (6, 5), (4, 5)])
    b = builder([RECT, RECT, upper], slab_holes={2: [hole]})
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-CURTAIN-WALL'])
    returns = [e for e in elements(b) if e.id.startswith('ENV-RET-L01-HEAD-P')]
    region = unary_union([polygon(e.geometry.boundary) for e in returns])
    expected = polygon(inset(RECT, -0.7)).difference(polygon(upper))
    assert region.symmetric_difference(expected).area < 1e-4
    assert region.intersection(polygon(hole)).area == 0.0
    assert all(e.geometry.z_base == pytest.approx(7.7) for e in returns)
    # Every declared attachment is independently checked against the actual solids.
    records = {instance.id: _Record(group, instance) for group in b.groups.values()
               for instance in group.instances}
    closures = [r for r in records.values() if r.group.subsystem == 'edge_closure']
    assert closures and all(r.instance.supports for r in closures)
    for record in closures:
        for host in record.instance.supports:
            assert _contact_gap(record, records[host]) < 1e-4, (record.id, host)
    heads = [e for e in elements(b) if e.id.startswith('ENV-GLZ-L01')]
    assert max(p.z for e in heads for p in e.geometry.corners) == pytest.approx(7.7)


@pytest.mark.parametrize('course', [1, 2])
def test_returns_keep_authored_multistorey_clearance_open(course):
    retained = ring([(0, 0), (6, 0), (6, 8), (0, 8)])
    b = builder([RECT, RECT, retained, retained])
    b.lattice.facade_control = SimpleNamespace(grammar_id='TEST-FACADE')
    b.lattice.program_volume_x_lines = [0, 6, 12]
    b.lattice.program_volume_y_lines = [0, 8]
    b.lattice.program_volume_regions = [ProgramVolumeRegion(
        id=f'PV-CLEAR-{i}', level_id=f'L{i:02d}', role='sectional_clearance',
        category='public', space_ids=[], grid_rect=(1, 0, 2, 1),
        z_base=i * 4.0, z_top=(i + 1) * 4.0) for i in (2, 3)]
    skin = ring([(12.7, -0.7), (-0.7, -0.7), (-0.7, 8.7), (12.7, 8.7)])
    _emit_level_returns(b, b.lattice.levels[course], b.lattice.levels[course + 1],
                        skin, skin, ENVELOPE_TECTONICS['ENV-CURTAIN-WALL'])
    clearance = box(6, 0, 12, 8)
    returns = [element for element in elements(b)
               if element.id.startswith(f'ENV-RET-L{course:02d}-')
               and (course == 2 or '-HEAD-' in element.id)]
    assert returns
    for element in returns:
        footprint = _plan_footprint(element.geometry, profiles=b.profiles,
                                    thickness_m=element.thickness_m)
        assert footprint.intersection(clearance).area <= 1e-7, element.id


@pytest.mark.parametrize('right,expected', [
    (-16.838796, 0), (-16.838795, 1), (-16.8387, 1), (-16.7638, 1)])
def test_return_registration_discards_only_collapsed_subresolution_strips(right, expected):
    # Fixed-precision GEOS registration rounds a half-grid tie toward +infinity.
    # Below that tie the strip vanishes; at/above it one grid cell remains. This
    # replaces independent Python vertex rounding while retaining a fixed 10 µm grid.
    region = box(-16.8388, 7.3355, right, 14.671)
    solids = _registered_return_solids(region, 12, 12.075)
    assert len(solids) == expected
    for solid in solids:
        assert polygon(solid.boundary).is_valid
        assert polygon(solid.boundary).area > 0


def test_invalid_return_region_is_not_automatically_repaired():
    with pytest.raises(ValueError, match='Invalid facade return region'):
        _registered_return_solids(Polygon([(0, 0), (2, 2), (0, 2), (2, 0)]), 0, .075)


@pytest.mark.parametrize('shift,scale,angle', [
    ((0, 0), 1, 0), ((103, -49), 1.7, 0), ((-21, 37), 1, 90),
])
def test_return_checks_other_edges_when_nearest_slab_point_is_occluded(shift, scale, angle):
    def moved(points):
        theta = math.radians(angle)
        return ring([(shift[0] + scale * (x * math.cos(theta) - y * math.sin(theta)),
                      shift[1] + scale * (x * math.sin(theta) + y * math.cos(theta)))
                     for x, y in points])

    # The closest point on this U-shaped slab is across an open notch. Its south
    # edge is reachable inside the current/upper volume union. A separate west
    # slab is farther away and must not win just because the first point failed.
    upper = moved([(0, 0), (10, 0), (10, 1), (2, 1),
                   (2, 7), (10, 7), (10, 10), (0, 10)])
    local = moved([(1, 0), (10, 0), (10, 1), (2, 1),
                   (2, 7), (10, 7), (10, 10), (1, 10)])
    remote = moved([(0, 0), (1, 0), (1, 10), (0, 10)])
    b = builder([upper] * 3)
    b.lattice.facade_control = SimpleNamespace(grammar_id='TEST-FACADE')
    for group in b.groups.values():
        if group.kind == 'floor_slab':
            for instance in group.instances:
                instance.geometry.boundary = local
    b.add_plate('REMOTE-SLAB', 'floor_slab', 'structure', 'slabs',
                remote, [], 7.7, 8.0, 'concrete_light', level_id='L02')
    skin = moved([(0, 0), (6.5, 0), (6.5, 5.5), (0, 5.5)])
    _emit_level_returns(b, b.lattice.levels[1], b.lattice.levels[2], skin,
                        moved([(6.5, 5)]), ENVELOPE_TECTONICS['ENV-CURTAIN-WALL'])
    tie = next(element for element in elements(b)
               if element.id == 'ENV-RET-L01-HEAD-S000')
    assert tie.supports == ['STR-SLB-L02']
    a, c = tie.geometry.path[0], tie.geometry.path[-1]
    assert math.hypot(a.x - c.x, a.y - c.y) == pytest.approx(4 * scale)
    allowed = polygon(skin).union(polygon(upper)).buffer(GEOMETRY_EPS_M)
    assert allowed.covers(LineString([(a.x, a.y), (c.x, c.y)]))
    assert 'ENV-RET-L01-HEAD-S000' in closure_solid_bearings(b)[0]


def test_return_emitter_refuses_remote_slab_across_entry_notch():
    boundary = ring([(0,0),(12,0),(12,12),(8,12),(8,4),(4,4),(4,12),(0,12)])
    b = builder([boundary] * 3)
    b.lattice.facade_control = SimpleNamespace(grammar_id='TEST-FACADE')
    # A tall clearance has removed the local floor; only the opposite wing can
    # offer an endpoint. Its existence cannot justify a tie across the open notch.
    for group in b.groups.values():
        if group.kind == 'floor_slab':
            for instance in group.instances:
                instance.geometry.boundary = ring([(8,0),(12,0),(12,12),(8,12)])
    skin_shape = Polygon([(p.x,p.y) for p in boundary]).buffer(.5, join_style=2)
    skin = ring(list(skin_shape.exterior.coords)[:-1])
    _emit_level_returns(b, b.lattice.levels[1], b.lattice.levels[2], skin,
        [v2(4.5,10)], ENVELOPE_TECTONICS['ENV-CURTAIN-WALL'])
    returns = [element for element in elements(b) if element.id.startswith('ENV-RET-')]
    assert returns
    assert not any(isinstance(element.geometry, MemberGeometry) for element in returns)
    assert all('ENVELOPE-CLOSURE-UNRESOLVED-SUPPORT' in element.rule_refs
               for element in returns)


def test_controlled_weather_return_preserves_courtyard_void_and_supports_mullion():
    source_hole = ring([(4, 3), (6, 3), (6, 5), (4, 5)])
    weather_hole = ring([(4.7, 3.7), (5.3, 3.7), (5.3, 4.3), (4.7, 4.3)])
    b = builder([RECT, RECT, RECT],
                 slab_holes={1: [source_hole], 2: [source_hole]})
    b.lattice.levels[1].voids = [source_hole]
    b.lattice.levels[2].voids = [source_hole]
    # A non-null control marks this as the Program Volume facade path. The direct
    # emitter test keeps the contract local and avoids coupling it to a full compile.
    b.lattice.facade_control = SimpleNamespace(grammar_id='TEST-FACADE')
    env = ENVELOPE_TECTONICS['ENV-CURTAIN-WALL']
    skin = ring([(12.7, -0.7), (-0.7, -0.7), (-0.7, 8.7), (12.7, 8.7)])
    stations = [v2(12.7, -0.7), v2(-0.7, -0.7),
                v2(-0.7, 8.7), v2(12.7, 8.7)]
    head = _emit_level_returns(
        b, b.lattice.levels[1], b.lattice.levels[2], skin, stations, env,
        weather_voids=[weather_hole])

    # The return union may be split for mesh export, yet it must still leave the
    # weather-plane courtyard empty.
    returns = [element for element in elements(b)
               if element.id.startswith('ENV-RET-L01-')]
    assert returns
    return_union = unary_union([
        Polygon([(point.x, point.y) for point in element.geometry.boundary],
                holes=[[(point.x, point.y) for point in hole]
                       for hole in element.geometry.holes])
        for element in returns if isinstance(element.geometry, ExtrusionGeometry)])
    assert return_union.intersection(Polygon([(point.x, point.y) for point in weather_hole])).area == pytest.approx(0)

    bay = _Bay(stations[0], stations[1], b.lattice.levels[1].z, head, 0.0,
               {'level': 1, 'station': 0}, 'L01', 0, True)
    _bay_subdivided(
        b, bay, env, b.datums, opaque=False,
        row_z=[b.lattice.levels[1].z, head], spandrel_height=0.0,
        mullion_profile='MULL-240x75', course=0)
    mullion = next(element for element in elements(b)
                   if element.id == 'ENV-MUL-L01-S000')
    assert {'ENV-RET-L01-BASE-S000', 'ENV-RET-L01-HEAD-S000'} <= set(mullion.supports)
    bracket_by_id = {element.id: element for element in elements(b)
                     if element.id in mullion.supports}
    # The full section touches the facade terminal; its axis stays behind the
    # finish. Placing the axis at that terminal exposed half the return bracket.
    half_depth = b.profiles[EDGE_BRACKET_PROFILE].depth_m / 2
    assert bracket_by_id['ENV-RET-L01-BASE-S000'].geometry.path[-1].z + half_depth == pytest.approx(
        mullion.geometry.path[0].z)
    assert bracket_by_id['ENV-RET-L01-HEAD-S000'].geometry.path[-1].z - half_depth == pytest.approx(
        mullion.geometry.path[-1].z)
    assert len(bracket_by_id['ENV-RET-L01-HEAD-S000'].geometry.path) == 2
    groups = list(b.groups.values())
    graph = compile_dependency_graph(groups)
    actual = next(instance for group in groups for instance in group.instances
                  if instance.id == mullion.id)
    assert set(actual.supports) == set(mullion.supports)
    assert compile_dependency_graph(groups).model_dump() == graph.model_dump()
    from rhino.import_building_model_v3 import primitive_contract
    from rhino.export_file import build_file_geometry, validate_file_geometry
    sdk = pytest.importorskip('rhino3dm')
    profiles = {key:value.model_dump() for key,value in b.profiles.items()}
    for bracket in returns:
        if isinstance(bracket.geometry, MemberGeometry):
            contract = primitive_contract(bracket.geometry.model_dump(), profiles)
            native = build_file_geometry(sdk, contract)
            assert validate_file_geometry(sdk, native, contract)['valid']


@pytest.mark.parametrize('damage', [None, 'moved_host', 'missing_host'])
def test_controlled_screen_fin_prefers_same_station_mullion_and_ties_back(damage):
    b = builder()
    b.lattice.facade_control = SimpleNamespace(grammar_id='TEST-FACADE')
    bay = _Bay(v2(3.0, 0.0), v2(6.0, 0.0), 4.0, 8.0, 0.0,
               {'level': 1, 'station': 0}, 'L01', 0, True)
    b.add('ENV-MUL-L01-S000', 'mullion', 'envelope', 'curtain_wall',
          MemberGeometry(path=[v3(3.0, 0.0, 4.0), v3(3.0, 0.0, 8.0)],
                         profile='MULL-240x75'), 'frame_dark', level_id='L01')
    _emit_screen_fin(b, bay, ENVELOPE_TECTONICS['ENV-CURTAIN-WALL'], 0.7)
    fin = next(element for element in elements(b) if element.id == 'ENV-SCR-L01-S000')
    assert fin.supports == ['ENV-MUL-L01-S000']
    assert fin.geometry.path[0].x == pytest.approx(3.0)
    assert fin.geometry.path[0].y == pytest.approx(0.0)
    assert len(fin.geometry.path) == 3
    assert not {'HT-INV-01', 'HT-INV-03', 'HT-INV-04'}.intersection(fin.rule_refs)
    groups = list(b.groups.values())
    host = next(instance for group in groups for instance in group.instances
                if instance.id == fin.supports[0])
    if damage == 'moved_host':
        host.geometry = host.geometry.model_copy(update={
            'path': [v3(point.x + 10, point.y, point.z) for point in host.geometry.path]})
    if damage == 'missing_host':
        for group in groups:
            group.instances[:] = [instance for instance in group.instances if instance is not host]
    graph = compile_dependency_graph(groups)
    relations = [relation for relation in graph.relations if relation.dependent_id == fin.id]
    if damage == 'missing_host':
        assert any(check.status == 'failed' and fin.id in check.affected_ids
                   for check in graph.checks)
    else:
        assert len(relations) == 1
        assert relations[0].host_id == fin.supports[0]
        assert relations[0].topology_status == (
            'geometry_checked' if damage is None else 'rule_checked')
        contact_check = next(check for check in graph.checks if check.id == 'DEP-GEOMETRY-CLAIMS')
        assert contact_check.status == ('passed' if damage is None else 'failed')


def test_exact_coincident_tall_program_volume_head_returns_are_simple_and_clear():
    """A tall edge claim must not leave a zero-width return ring or enter its volume."""
    b = builder([RECT, RECT, RECT])
    b.lattice.program_volume_x_lines = [0.0, 1.0, 12.0]
    b.lattice.program_volume_y_lines = [0.0, 8.0]
    b.lattice.program_volume_regions = [ProgramVolumeRegion(
        id='PV-TALL-EDGE', level_id='L01', category='public', role='archetype',
        space_ids=['SP-TALL'], grid_rect=(0, 0, 1, 1), z_base=4.0, z_top=12.0)]
    claim = b.lattice.program_volume_regions[0].resolve_bounds(b.lattice)
    b.lattice.carved = {1: [claim]}

    emit_envelope(b, ENVELOPE_TECTONICS['ENV-CURTAIN-WALL'])

    heads = [element for element in elements(b)
             if element.id.startswith('ENV-RET-L01-HEAD-P')]
    assert heads
    claim_region = box(*claim)
    for element in heads:
        assert isinstance(element.geometry, ExtrusionGeometry)
        footprint = polygon(element.geometry.boundary)
        assert footprint.is_valid
        assert footprint.area > GEOMETRY_EPS_M ** 2

        points = list(footprint.exterior.coords)[:-1]
        assert len(points) >= 3
        segments = []
        for index, point in enumerate(points):
            following = points[(index + 1) % len(points)]
            vector = (following[0] - point[0], following[1] - point[1])
            assert math.hypot(*vector) > 0.0
            segments.append(vector)
        for first, second in zip(segments, segments[1:] + segments[:1]):
            cross = first[0] * second[1] - first[1] * second[0]
            dot = first[0] * second[0] + first[1] * second[1]
            assert not (abs(cross) <= GEOMETRY_EPS_M and dot < 0.0)

        assert footprint.intersection(claim_region).area <= GEOMETRY_EPS_M
        assert footprint.intersection(
            claim_region.buffer(GEOMETRY_EPS_M, join_style=2)).area <= GEOMETRY_EPS_M


def test_floor_return_supports_stay_below_real_door_apertures():
    b = builder()
    add_entry_landing(b)
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-CURTAIN-WALL'])
    model = SimpleNamespace(element_groups=list(b.groups.values()), elements=elements(b),
                            lattice=b.lattice, profiles=b.profiles)
    profiles = {key: value.model_dump() for key, value in b.profiles.items()}
    supports = [e for e in model.elements if e.id.startswith('ENV-RET-L01-BASE-S')]
    assert supports
    for e in supports:
        vertices, _ = primitive_mesh(e.geometry.model_dump(), profiles)
        # Inspect the swept member, including its section. An axis below the floor
        # alone did not prevent the previous real 32.5 mm threshold obstruction.
        assert max(point[2] for point in vertices) == pytest.approx(4.0 - 0.075)
    report = inspect_portals(model)
    assert report.portals
    blockers = {ident for finding in report.findings
                if finding.rule_id in {'PORTAL-APERTURE-BLOCKED', 'PORTAL-APPROACH-BLOCKED'}
                for ident in finding.elements}
    assert not blockers.intersection(e.id for e in supports)
    contact, misses = closure_solid_bearings(b)
    assert {e.id for e in supports} <= contact
    assert not misses


@pytest.mark.parametrize('tectonic', ['ENV-CURTAIN-WALL', 'ENV-EXPRESSED-FRAME', 'ENV-PUNCHED-WALL'])
@pytest.mark.parametrize('shift,scale,reverse', [((0,0),1,False), ((103,-49),1.7,True)])
def test_entry_is_one_real_screen_with_both_supported_approaches(tectonic,shift,scale,reverse):
    plate = ring([(shift[0]+p.x*scale,shift[1]+p.y*scale) for p in RECT])
    if reverse:
        plate.reverse()
    b = builder([plate]*3)
    entrance = add_entry_landing(b)
    assert entrance is not None
    landing = box(*b.approach['entry'])
    assert all(landing.covers(region) for region in (
        entrance.aperture,entrance.inside_approach,entrance.outside_approach))
    emit_envelope(b, ENVELOPE_TECTONICS[tectonic])
    report = inspect_portals(portal_model(b))
    assert len(report.portals) == 1
    door = report.portals[0]
    assert len(door.door_ids) == 2 and door.width_m == pytest.approx(2.4)
    assert door.center == pytest.approx(entrance.center)
    assert door.wall_depth_m == pytest.approx(.45)
    assert door.passable, report.model_dump()


@pytest.mark.parametrize('damage', ['platform_removed','wall_across_opening'])
def test_entry_does_not_hide_a_missing_platform_or_wall(damage):
    b = builder()
    entrance = add_entry_landing(b)
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'])
    if damage == 'platform_removed':
        for group in b.groups.values():
            group.instances[:] = [i for i in group.instances if i.id != 'CIR-LND-ENTRY']
    else:
        b.add('BLOCK-ENTRY', 'partition', 'program', 'partitions',
              BoxGeometry(center=v3(*entrance.center,entrance.floor_z+1.5),
                          size=v3(entrance.width_m,.25,3.0)), 'white', level_id=entrance.level_id)
    report = inspect_portals(portal_model(b))
    assert not report.portals[0].passable
    expected = 'PORTAL-APPROACH-UNSUPPORTED' if damage == 'platform_removed' else 'PORTAL-APERTURE-BLOCKED'
    assert any(f.rule_id == expected for f in report.findings)


def test_program_wall_uses_the_actual_shared_entry_opening():
    b = builder()
    entrance = add_entry_landing(b)
    emit_envelope(b, ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'])
    level = b.lattice.occupied[0]
    a,c = level.plate[entrance.edge],level.plate[(entrance.edge+1)%len(level.plate)]
    start,end = (a.x,a.y),(c.x,c.y)
    openings = matching_entrances(b,level,start,end,.25)
    assert len(openings)==1 and openings[0].width_m==pytest.approx(2.4)
    for tag,kind,geometry in wall_run_parts(start,end,level.z,3.7,.25,openings):
        b.add(f'PRG-WALL-{tag}',kind,'program','partitions',geometry,'white',level_id=level.id)
    assert inspect_portals(portal_model(b)).portals[0].passable


@pytest.mark.parametrize('cap_emitted',[True,False])
def test_low_head_cannot_shortcut_across_the_hall_to_remote_slab(cap_emitted):
    upper = ring([(6,0),(0,0),(0,8),(6,8)])
    b = builder([RECT,RECT,upper])
    hall = box(6,0,12,8)
    roof_z = b.lattice.roof.z + (b.lattice.roof.z-b.lattice.occupied[0].z)
    b.hall_geometry = SimpleNamespace(footprint=hall,clear_top_z=roof_z,
                                      roof_bottom_z=roof_z)
    if cap_emitted:
        b.add('ENV-HALL-ROOF','roof_deck','envelope','hall_enclosure',
              ExtrusionGeometry(boundary=ring(list(hall.exterior.coords)[:-1]),
                                z_base=roof_z,z_top=roof_z+.3),'white',level_id='L02')
    emit_envelope(b,ENVELOPE_TECTONICS['ENV-EXPRESSED-FRAME'])
    head = [e for e in elements(b) if e.id.startswith('ENV-RET-L01-HEAD-')]
    assert head
    profiles = {key:value.model_dump() for key,value in b.profiles.items()}
    for e in head:
        if isinstance(e.geometry,MemberGeometry):
            verts,_ = primitive_mesh(e.geometry.model_dump(),profiles)
            projection = Polygon([(p[0],p[1]) for p in verts]).convex_hull
            assert projection.intersection(hall).area < 1e-8
        elif cap_emitted:
            assert polygon(e.geometry.boundary).intersection(hall).area < 1e-8
    # The replacement is only credited when the real cap has been emitted. A
    # requested cap with absent solids must retain visible unresolved geometry.
    intrusion = sum(polygon(e.geometry.boundary).intersection(hall).area for e in head
                    if isinstance(e.geometry,ExtrusionGeometry))
    assert intrusion == pytest.approx(0) if cap_emitted else intrusion > 1
    assert not closure_solid_bearings(b)[1]


@pytest.mark.parametrize('shift,scale', [((0, 0), 1), ((117, -33), 1.4)])
def test_roof_has_complete_boundary_and_contacting_deck_supports(shift, scale):
    plate = ring([(shift[0] + p.x * scale, shift[1] + p.y * scale) for p in RECT])
    b = builder([plate] * 3)
    _emit_roof(b)
    es = {e.id: e for e in elements(b)}
    deck = es['ENV-DECK-ROOF']
    assert polygon(deck.geometry.boundary).symmetric_difference(polygon(plate)).area == 0.0
    assert deck.supports and all(ident.startswith('STR-PRL-') for ident in deck.supports)
    for ident in deck.supports:
        purlin = es[ident].geometry
        top = purlin.path[0].z + b.profiles[purlin.profile].depth_m / 2.0
        assert deck.geometry.z_base == pytest.approx(top)
    closure_solids = unary_union([
        _plan_footprint(
            element.geometry, profiles=b.profiles,
            thickness_m=element.thickness_m)
        for element in es.values()
        if element.subsystem == 'roof_closure'
        and element.kind == 'spandrel_panel'
    ])
    # The closure is a real 90 mm perimeter band. Its outside face, rather than an
    # abstract centre surface, closes the exact Program Volume boundary at corners.
    assert polygon(plate).boundary.difference(
        closure_solids.buffer(2e-6)).length < 1e-4
    records = {instance.id: _Record(group, instance) for group in b.groups.values()
               for instance in group.instances}
    for e in es.values():
        if e.subsystem == 'roof_closure':
            assert e.supports, e.id
            for host in e.supports:
                assert _contact_gap(records[e.id], records[host]) < 1e-4, (e.id, host)


def test_legacy_roof_keeps_single_deck_and_member_parapet():
    b = builder()
    assert b.lattice.roof_control is None
    _emit_roof(b)
    roof_elements = elements(b)

    decks = [element for element in roof_elements if element.kind == 'roof_deck']
    parapets = [element for element in roof_elements if element.kind == 'parapet']
    assert [element.id for element in decks] == ['ENV-DECK-ROOF']
    assert decks[0].material_profile == 'white'
    assert decks[0].assembly_id is None and decks[0].part_role is None
    assert parapets and all(isinstance(element.geometry, MemberGeometry)
                            for element in parapets)
    assert all(element.assembly_id is None and element.part_role is None
               for element in parapets)


def test_physical_roof_perimeter_stays_inside_program_volume_control():
    b = builder()
    roof = b.lattice.roof
    b.lattice.roof_control = roof_control_for(
        [(point.x, point.y) for point in roof.plate], [],
        datum_z=roof.z,
        truss_depth_m=b.datums.value('truss_depth_m'))

    # `_emit_roof` runs the physical cap and plan-containment validator before
    # returning. This regression previously failed at the first edge post because
    # the convex radial inset was shallower than the member's half-width.
    _emit_roof(b)
    emitted = {element.id: element for element in elements(b)}
    assert 'ENV-ROOF-CLOSE-RING' in emitted
    assert 'ENV-DECK-ROOF' in emitted


def test_missing_roof_edge_support_stays_reported():
    cut = ring([(11.5, -1), (13, -1), (13, 9), (11.5, 9)])
    b = builder(slab_holes={2: [cut]})
    _emit_roof(b)
    unresolved = [e for e in elements(b)
                  if 'ENVELOPE-CLOSURE-UNRESOLVED-SUPPORT' in e.rule_refs]
    assert unresolved and all(not e.supports for e in unresolved)
    assert any(e.kind == 'truss_web' for e in unresolved)


@pytest.mark.parametrize('subsystem', ['edge_closure', 'entrance'])
@pytest.mark.parametrize('damage', [None, 'removed_host', 'moved_host', 'hole_at_endpoints'])
def test_solid_terminal_is_measured_without_inventing_an_axis(damage, subsystem):
    b = builder()
    host = ExtrusionGeometry(boundary=RECT, z_base=3.7, z_top=4.0)
    b.add('SLAB-PROBE', 'floor_slab', 'structure', 'slabs', host,
          'concrete_light', level_id='L01')
    b.add('RETURN-PROBE', 'external_strut', 'envelope', subsystem,
          MemberGeometry(path=[v3(3, 4, 3.9), v3(3.2, 4, 3.9)], profile='TRAN-75x140'),
          'steel_light', level_id='L01', supports=['SLAB-PROBE'])
    assert ('RETURN-PROBE', 'SLAB-PROBE') not in b.axis._pending
    host_group = next(g for g in b.groups.values()
                      if any(i.id == 'SLAB-PROBE' for i in g.instances))
    instance = next(i for i in host_group.instances if i.id == 'SLAB-PROBE')
    if damage == 'removed_host':
        host_group.instances.remove(instance)
    elif damage == 'moved_host':
        instance.geometry = host.model_copy(update={
            'boundary': [v2(p.x + 20.0, p.y) for p in RECT]})
    elif damage == 'hole_at_endpoints':
        instance.geometry = host.model_copy(update={
            'holes': [ring([(2.5, 3.5), (3.5, 3.5), (3.5, 4.5), (2.5, 4.5)])]})
    b.axis.finalise()
    assert 'RETURN-PROBE' in b.axis.isolated()  # Still no shared member node.
    contact, misses = closure_solid_bearings(b)
    check = next(c for c in _record_axis_checks(b).checks
                 if c.id == 'AXIS-CLOSURE-SOLID-BEARING')
    if damage is None:
        assert 'RETURN-PROBE' in contact and not misses
        assert check.status == 'passed'
    else:
        assert 'RETURN-PROBE' in misses and not contact
        assert check.status == 'failed' and 'RETURN-PROBE' in check.affected_ids
