"""What separates a coordination model from a permit set.

Four things, and this file holds each of them:

- **Standard product specifications.** A member has to carry a designation a fabricator
  recognises. `I-450x225x9x14` is a correct calculation of a shape nobody rolls.
- **Complete code checks.** A ratio under one is not a calculation record. A plan checker
  asks which clause governed, under which combination, and which clauses were skipped.
- **A program constitution.** A brief is what a client asks for; a building also needs
  restrooms, a janitor's closet, an electrical room and a riser.
- **A life-safety graph.** Drawing stairs is not egress design. Two hundred people on a
  floor need a stated number of exits, remote from each other, at a width their occupant
  load sets.
"""

import json
import math
from pathlib import Path

import pytest

from backend.app import life_safety
from backend.app.briefs import BRIEFS, brief_for
from backend.app.compiler_v3 import compile_building_model_v3
from backend.app.constitution import (
    BASE_BUILDING_SUPPORT, OCCUPANT_LOAD_FACTOR_M2, occupant_load,
    total_occupant_load, validate_model,
)
from backend.app.massing import MASSING_FAMILIES
from backend.app.models import ArchitecturalScore, AudioFeatures
from backend.app.registry import (
    BY_DESIGNATION, REGISTRY, catalogue, products, verify_against_catalogue,
)
from backend.app.sections import MATERIALS
from backend.app.validators import (
    Actions, lrfd_combinations, steel_ltb_capacity,
    validate_steel_beam,
)

ROOT = Path(__file__).parents[2]
DEMO = ROOT / 'artifacts' / 'v3_demo'
V2_DEMO = (ROOT / 'artifacts' / 'integrated_demo'
           / 'building-b7ad95fa45a6-library-steel-international-v1')


@pytest.fixture(scope='module')
def features() -> AudioFeatures:
    return AudioFeatures.model_validate(
        json.loads((V2_DEMO / 'music_features.json').read_text(encoding='utf-8')))


@pytest.fixture(scope='module')
def template() -> ArchitecturalScore:
    return ArchitecturalScore.model_validate(
        json.loads((DEMO / 'architectural_score.json').read_text(encoding='utf-8')))


@pytest.fixture(scope='module')
def model(features, template):
    return compile_building_model_v3(features, template, massing_id='MAS-SLAB',
                                     typology='library')


# ---------------------------------------------------------------------------
# Standard product registry
# ---------------------------------------------------------------------------

def test_every_registered_product_names_a_producing_standard():
    for spec in REGISTRY:
        assert spec.producing_standard, spec.designation
        assert spec.material_id in MATERIALS, spec.designation


def test_computed_properties_agree_with_the_published_catalogue():
    """The transcription check, and the reason the published numbers are carried.

    A computed Ix a few per cent under the published value is the root fillets the
    idealised geometry has none of. One out by twenty is a typo, and a typo in a section
    table sizes a beam wrong in a way no downstream check can catch. Three were caught
    this way: the plastic modulus of W10X49, W12X65 and W12X87 had been entered against
    the wrong conversion.
    """
    deviations = verify_against_catalogue()
    assert deviations
    outside = [d for d in deviations if not d.within_expected]
    assert not outside, [
        (d.designation, d.property_name, f'{d.deviation:+.1%}') for d in outside[:5]]


def test_the_deviation_band_is_tight_and_one_sided_for_rolled_shapes():
    """Fillets make a computed W-shape property low, never high.

    A one-sided band is evidence the geometry is right; scatter in both directions would
    mean the dimensions or the transcription were wrong somewhere.
    """
    shapes = {p.designation for p in products('steel_w_shape')}
    values = [d.deviation for d in verify_against_catalogue()
              if d.designation in shapes and d.property_name in ('ix_mm4', 'zx_mm3')]
    assert values
    assert max(values) <= 0.0
    assert min(values) >= -0.04


def test_hollow_sections_model_their_corner_radii():
    """A sharp-cornered idealisation of an HSS is unconservative, unlike a W-shape.

    Ignoring the corner radii overstated the area by two to three per cent and Ix by up
    to nine, which makes a column look stronger than it is. The direction is what
    matters: for a rolled shape the same idealisation errs the safe way.
    """
    for spec in products('steel_hss_square'):
        section = spec.to_section()
        sharp = spec.depth_mm ** 2 - (spec.depth_mm - 2 * spec.web_mm) ** 2
        assert section.area_mm2 < sharp
        assert abs(section.area_mm2 / spec.catalogue_area_mm2 - 1.0) < 0.02


def test_every_member_the_compiler_sizes_carries_an_orderable_designation(model):
    for record in model.sizing:
        spec = BY_DESIGNATION.get(record.section_id)
        assert spec is not None, record.section_id
        assert spec.producing_standard


def test_the_catalogues_are_ordered_by_area_so_the_first_pass_is_the_lightest():
    for family in ('steel_w_shape', 'glulam', 'concrete_cast'):
        areas = [section.area_mm2 for section in catalogue(family)]
        assert areas == sorted(areas), family


# ---------------------------------------------------------------------------
# Complete code checks
# ---------------------------------------------------------------------------

def test_lateral_torsional_buckling_matches_the_published_bracing_lengths():
    """The clause that was previously assumed away, checked against AISC's own numbers.

    `steel_flexural_capacity` returned phi*Fy*Zx and its docstring said "continuously
    braced compression flange assumed". For W18X50 the published Lp is 5.83 ft and Lr is
    17.0 ft; the implementation reproduces both, which is what makes the branch it picks
    trustworthy.
    """
    section = BY_DESIGNATION['W18X50'].to_section()
    material = MATERIALS['steel_s355']
    _, short = steel_ltb_capacity(section, material, 1.0)
    _, mid = steel_ltb_capacity(section, material, 3.5)
    _, long = steel_ltb_capacity(section, material, 9.0)
    assert 'F2.1 yielding' in short
    assert 'inelastic LTB' in mid
    assert 'elastic LTB' in long
    # Lp near 1.78 m and Lr near 5.18 m, from the published table
    assert 'Lp 1788' in short
    assert 'Lr 5173' in mid


def test_lateral_torsional_buckling_can_govern_and_does(model):
    """An unbraced span fails a section that passes on yielding alone."""
    section = BY_DESIGNATION['W18X50'].to_section()
    material = MATERIALS['steel_s355']
    braced = validate_steel_beam(
        member_id='B', role='girder', section=section, material=material, span_m=8.0,
        unbraced_length_m=2.5, moment_kn_m=280.0, shear_kn=140.0,
        live_deflection_mm=10.0, total_deflection_mm=16.0, live_limit=360,
        total_limit=240, combination='1.2D + 1.6L')
    unbraced = validate_steel_beam(
        member_id='B', role='girder', section=section, material=material, span_m=8.0,
        unbraced_length_m=8.0, moment_kn_m=280.0, shear_kn=140.0,
        live_deflection_mm=10.0, total_deflection_mm=16.0, live_limit=360,
        total_limit=240, combination='1.2D + 1.6L')
    assert braced.passes
    assert not unbraced.passes
    assert unbraced.governing.clause == 'F2.2'


def test_a_closed_section_does_not_suffer_lateral_torsional_buckling():
    section = BY_DESIGNATION['HSS12X12X1/2'].to_section()
    material = MATERIALS['steel_s355']
    near, _ = steel_ltb_capacity(section, material, 1.0)
    far, basis = steel_ltb_capacity(section, material, 12.0)
    assert near == far
    assert 'closed section' in basis


def test_every_member_record_names_its_governing_clause_and_its_gaps(model):
    for record in model.sizing:
        assert record.assumptions
    for check in model.sizing:
        assert check.governing_check


def test_a_member_validation_lists_what_was_not_checked():
    section = BY_DESIGNATION['W24X76'].to_section()
    validation = validate_steel_beam(
        member_id='B', role='girder', section=section,
        material=MATERIALS['steel_s355'], span_m=9.0, unbraced_length_m=2.4,
        moment_kn_m=400.0, shear_kn=200.0, live_deflection_mm=12.0,
        total_deflection_mm=20.0, live_limit=360, total_limit=240,
        combination='1.2D + 1.6L + 0.5Lr')
    absent = {c.label for c in validation.unevaluated}
    assert {'Wind load', 'Seismic load', 'Snow load', 'Connections'} <= absent
    for check in validation.unevaluated:
        assert check.basis, check.label


def test_all_seven_strength_combinations_are_evaluated():
    """ASCE 7 2.3.1 has seven; the pipeline used one and called it the design."""
    combinations = lrfd_combinations(
        Actions(dead=20.0, live=30.0, roof_live=5.0, wind=12.0, seismic=8.0))
    assert len(combinations) == 7
    names = [name for name, _ in combinations]
    assert '1.4D' in names
    assert any('W' in name for name in names)
    assert any('E' in name for name in names)


# ---------------------------------------------------------------------------
# Program constitution
# ---------------------------------------------------------------------------

def test_every_typology_satisfies_the_base_building_constitution(features, template):
    for typology in BRIEFS:
        built = compile_building_model_v3(features, template, typology=typology)
        report = built.constitution
        assert report is not None
        assert report.complete, (typology, [f.label for f in report.missing_required])


def test_a_brief_on_its_own_does_not_satisfy_the_constitution(features, template):
    """The finding this module exists to make, kept as a test so it cannot regress.

    A client's brief is rooms. Checking one against the constitution before the support
    spaces are generated should still fail, because a list of galleries is not a
    building.
    """
    model = compile_building_model_v3(features, template, typology='library')
    bare = validate_model('library', BRIEFS['library'], model)
    assert not bare.complete
    missing = {f.label for f in bare.missing_required}
    assert 'Janitor and custodial closet' in missing
    assert 'Electrical and IT room' in missing


def test_the_brief_the_compiler_allocates_includes_the_support(features, template):
    full = brief_for('library', storeys=5)
    types = {space.space_type for space in full}
    for required in ('public_restroom', 'janitor', 'electrical_it', 'riser',
                     'refuse', 'general_storage'):
        assert required in types, required


def test_a_placeholder_area_says_that_it_is_one():
    """Where the guideline delegates a quantity, the space must not pretend otherwise."""
    full = brief_for('library', storeys=5)
    restroom = next(s for s in full if s.space_type == 'public_restroom')
    assert 'placeholder' in restroom.reason.lower()
    assert 'plumbing code' in restroom.reason.lower()


def test_occupant_load_comes_from_the_published_table():
    loads = occupant_load(brief_for('library', storeys=5))
    assert loads
    for entry in loads:
        assert entry.factor_key in OCCUPANT_LOAD_FACTOR_M2
        assert entry.occupants == max(1, math.ceil(entry.area_m2 / entry.factor_m2))
        assert 'IBC Table 1004.5' in entry.basis
    assert total_occupant_load(brief_for('library', storeys=5)) > 100


def test_every_support_requirement_states_where_its_quantity_comes_from():
    for requirement in BASE_BUILDING_SUPPORT:
        assert requirement.quantity_basis, requirement.id
        assert requirement.reason, requirement.id


# ---------------------------------------------------------------------------
# Life-safety graph
# ---------------------------------------------------------------------------

def test_the_model_carries_an_egress_graph(model):
    graph = model.life_safety
    assert graph is not None
    assert graph.spaces and graph.exits and graph.edges
    assert graph.total_occupants > 0


def test_travel_distance_and_exit_counts_are_checked_against_the_code(model):
    clauses = {finding.clause for finding in model.life_safety.findings}
    for clause in ('1017.2', '1006.3.2', '1005.3.1', '1007.1.1', '1011.2'):
        assert clause in clauses, clause


def test_a_second_remote_stair_core_is_built(features, template):
    """IBC 1007.1.1, and the reason a second stair core exists at all.

    With one core the graph reported remoteness failing at 2.11 against the
    one-third-diagonal rule. A second core placed by maximising distance from the first
    is what fixes it, on every plan wide enough to hold two.
    """
    built = compile_building_model_v3(features, template, massing_id='MAS-COURTYARD',
                                      typology='library')
    remoteness = [f for f in built.life_safety.findings if f.clause == '1007.1.1']
    assert remoteness
    assert all(f.status == 'pass' for f in remoteness), [
        (f.subject, f.demand, f.capacity) for f in remoteness]
    # two independent cores, not one drawn twice
    landings = [e for e in built.elements if e.kind == 'stair_landing']
    xs = {round(e.position.x, 1) for e in landings}
    assert len(xs) >= 2


def test_a_plan_too_narrow_for_two_remote_cores_still_gets_the_best_pair(
        features, template):
    """The other half, and the more important one.

    This used to pin MAS-TOWER and assert that 1007.1.1 *failed* on it -- a twenty-two
    metre tower could not put two exit stairs a third of its diagonal apart. It can
    now: the pair is placed as a pair rather than one stair plus whatever the leftover
    region allows, and the landings of a pair face away from each other, so the tower
    measures 21.5 m against a 12.7 m ask. No massing in the family set fails the clause
    any more, so asserting a failure would mean keeping a building broken to have
    something to point at.

    What must not change is the behaviour the old test was written for: when the
    geometry genuinely cannot deliver the separation, build the best second core
    available and let the graph say so -- never omit the second stair, never quietly
    pass the clause. Checked here on a plate deliberately shrunk below anything the
    massing families produce.
    """
    from backend.app.compiler_v3 import core_anchors
    from backend.app.datums import build_lattice, compile_datum_set
    from backend.app.massing import MASSING_FAMILIES

    datums = compile_datum_set(template)
    cramped = MASSING_FAMILIES['MAS-TOWER'].model_copy(
        update={'plan_x_m': 16.0, 'plan_y_m': 13.0})
    lattice = build_lattice(datums, cramped)
    anchors = core_anchors(lattice, datums)

    assert anchors['primary'] is not None, 'no stair at all on a small plate'
    assert anchors['second'] is not None, (
        'the second core was omitted rather than placed as well as the plate allows')
    gap = math.hypot(anchors['second'][0] - anchors['primary'][0],
                     anchors['second'][1] - anchors['primary'][1])
    diagonal = math.hypot(16.0, 13.0)
    assert gap < diagonal / 3.0, (
        f'this plate is no longer cramped: {gap:.1f} m against {diagonal / 3.0:.1f} m, '
        f'so the test has stopped exercising the shortfall path it exists for')
    assert gap > 0.0


@pytest.mark.parametrize('massing_id', ['MAS-SLAB', 'MAS-TOWER', 'MAS-BAR-PODIUM',
                                        'MAS-COURTYARD', 'MAS-ZIGGURAT', 'MAS-SPLIT'])
def test_the_remoteness_clause_is_answered_on_every_storey(
        features, template, massing_id):
    """1007.1.1 is evaluated and quantified wherever it applies.

    The failure mode this guards is silence: a storey with one exit produces no pair to
    measure, so the clause goes missing rather than failing, and a reader scanning for
    red sees none. Every finding carries the demand and the capacity that produced it.
    """
    built = compile_building_model_v3(features, template, massing_id=massing_id,
                                      typology='library')
    # Storeys with people on them. A ziggurat's top plate can shrink past a usable
    # floor, so no program lands there and nobody has to get out of it -- the clause
    # does not apply and its absence is correct. Read from the graph rather than
    # assumed, so the exemption is earned: an empty storey is one with no occupants,
    # not one the pipeline forgot to lay out.
    occupants = {}
    for node in built.life_safety.nodes:
        occupants[node.level_id] = occupants.get(node.level_id, 0) + node.occupants
    storeys = {level.id for level in built.lattice.occupied
               if occupants.get(level.id, 0) > 0}
    assert storeys, f'{massing_id}: no storey has anybody on it'
    answered = {finding.subject for finding in built.life_safety.findings
                if finding.clause == '1007.1.1'}
    unanswered = storeys - answered - {
        finding.subject for finding in built.life_safety.unevaluated
        if finding.clause == '1007.1.1'}
    assert not unanswered, (
        f'{massing_id}: {sorted(unanswered)} produced no remoteness finding at all, '
        f'which reads as compliance and is not')
    for finding in built.life_safety.findings:
        if finding.clause == '1007.1.1':
            assert finding.demand is not None and finding.capacity is not None
            assert 'diagonal' in finding.detail


def test_the_graph_says_what_it_cannot_measure(model):
    unevaluated = {f.clause for f in model.life_safety.unevaluated}
    # the common path clause needs a corridor branch the graph does not model
    assert '1006.2.1' in unevaluated
    assert '1023' in unevaluated
    for finding in model.life_safety.unevaluated:
        assert finding.detail


def test_egress_width_scales_with_the_occupant_load_it_serves(model):
    capacity = [f for f in model.life_safety.findings if f.clause == '1005.3.1']
    assert capacity
    for finding in capacity:
        assert finding.demand is not None and finding.capacity is not None
        assert '7.6 mm per occupant' in finding.detail


def test_every_massing_family_produces_a_gradeable_egress_report(features, template):
    for massing_id in MASSING_FAMILIES:
        built = compile_building_model_v3(features, template, massing_id=massing_id)
        graph = built.life_safety
        assert graph is not None and graph.findings, massing_id
        # a report that cannot fail is not a check
        assert any(f.status in ('pass', 'fail') for f in graph.findings), massing_id


def test_a_column_carries_a_clause_record_like_a_beam():
    """Columns imported the validators and never called them.

    A beam carried a clause-by-clause record and the column holding it up carried four
    utilisations, which is half a frame checked. The gap was found by a stale-import
    scan rather than by a test, which is why this one exists.
    """
    from backend.app.loads import LoadCase
    from backend.app.sizing import check_column

    section = BY_DESIGNATION['HSS12X12X1/2'].to_section()
    record = check_column('C1', 2400.0, 4.2, section).validation
    assert record is not None
    clauses = {c.clause for c in record.checks}
    assert {'E3', 'E2', 'B4.1a'} <= clauses
    assert record.governing.clause == 'E3'
    # and the gaps a column has that a beam does not
    absent = {c.clause for c in record.unevaluated}
    assert 'H1' in absent and 'E4' in absent


def test_a_timber_column_says_it_has_no_clause_record_yet():
    """Attaching a steel record to a glulam post would be worse than admitting the gap."""
    from backend.app.registry import spec_for
    from backend.app.sizing import check_column

    section = spec_for('GL28h 215x680').to_section()
    record = check_column('C2', 900.0, 4.2, section)
    assert record.validation is None
    assert record.max_ratio > 0.0  # the NDS check still ran


# ---------------------------------------------------------------------------
# The theatre that shipped with one way out
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def theater_bar_podium():
    """The real-music demo building: a theatre bar standing on a podium.

    Kept as a fixture because it is the shape that found the flaw: the second core
    stood in the far corner of the podium it served three storeys of, and L04 --
    a hundred and nineteen people -- had one exit. Separation had been preferred
    *instead of* coverage; the fix covers first and stays remote where it can.
    """
    fixtures = Path(__file__).parent / 'fixtures'
    features = AudioFeatures.model_validate(json.loads(
        (fixtures / 'theater_bar_podium_features.json').read_text(encoding='utf-8')))
    score = ArchitecturalScore.model_validate(json.loads(
        (fixtures / 'theater_bar_podium_score.json').read_text(encoding='utf-8')))
    return compile_building_model_v3(features, score)


def test_every_crowded_storey_has_two_ways_out(theater_bar_podium):
    """IBC 1006.3.2 on the building that failed it.

    Not an assertion that the graph passes in general -- an assertion that no storey
    is left counting one exit because another storey's remoteness was worth more.
    """
    graph = theater_bar_podium.life_safety
    failures = [finding for finding in graph.findings
                if finding.status == 'fail' and finding.clause == '1006.3.2']
    assert not failures, [f'{f.subject}: {f.detail}' for f in failures]


def test_the_pair_that_covers_the_bar_is_remote_enough(theater_bar_podium):
    """IBC 1007.1.1 on the same building.

    The anchors of the bar's pair can stand at most 9.4 m apart -- the bar is slim
    and its ends are curved -- against a 10.3 m third-diagonal ask. The pair passes
    because the exits are the landings, not the anchors, and the doors of a pair
    open away from each other: measured door to door the separation is 15 m. If this
    fails again, the first thing to check is whether some emitter change moved the
    landings back to the same side.
    """
    graph = theater_bar_podium.life_safety
    failures = [finding for finding in graph.findings
                if finding.status == 'fail' and finding.clause == '1007.1.1']
    assert not failures, [f'{f.subject}: {f.detail}' for f in failures]


def test_the_extra_core_is_reserved_like_the_others(theater_bar_podium):
    """The third stair takes floor like the first two, or the program is banded
    through its flights -- which is the exact collision the reservations exist for."""
    model = theater_bar_podium
    from backend.app.compiler_v3 import core_anchors, core_reservations
    anchors = core_anchors(model.lattice, model.datum_set)
    assert anchors['extras'], 'the bar-podium no longer needs an extra core; if that '\
        'is a real improvement this test should start asserting why'
    reserved = core_reservations(model.lattice, model.datum_set)
    assert len(reserved) == 2 + len(anchors['extras'])
    assert model.spatial.status == 'passed'


def _wind_clause(validation):
    """The wind row of a member record. It carries a `demand` only when a site is set."""
    return next(check for check in validation.checks if check.label == 'Wind load')


def _beam_record():
    return validate_steel_beam(
        member_id='B', role='girder', section=BY_DESIGNATION['W24X76'].to_section(),
        material=MATERIALS['steel_s355'], span_m=9.0, unbraced_length_m=2.4,
        moment_kn_m=400.0, shear_kn=200.0, live_deflection_mm=12.0,
        total_deflection_mm=20.0, live_limit=360, total_limit=240,
        combination='1.2D + 1.6L')


def test_one_runs_site_loads_never_reach_another_runs_member_checks():
    """The site a member check reports has to belong to the run that asked.

    `set_site_loads` is read out of band, from deep inside the sizing loop. It was a
    module global, and the API compiles runs on worker threads -- `main.generate` hands
    `compile_generation` to `asyncio.to_thread` -- so two uploads in flight shared one
    variable, and either could serve the other's wind and seismic figures. Nothing about
    the resulting member record would look wrong: it carries a plausible number, a real
    clause and a citation, for a place the building is not.

    Written through the member record rather than the variable, so it keeps testing the
    property if the mechanism changes again.
    """
    import threading

    from backend.app import validators
    from backend.app.site import DEFAULT_LOCATION, lookup
    from backend.app.site_loads import compute

    validators.set_site_loads(compute(
        lookup(DEFAULT_LOCATION), height_m=20.0, width_m=30.0,
        seismic_weight_kn=5000.0, structural_system_id='STR-SYS-STEEL-FRAME'))
    try:
        mine = _wind_clause(_beam_record())
        assert mine.demand is not None, 'this run should be reporting its own site'

        theirs: list = []

        def a_second_run() -> None:
            # Another upload, on its own worker thread, that has not resolved a site.
            theirs.append(_wind_clause(_beam_record()))

        thread = threading.Thread(target=a_second_run)
        thread.start()
        thread.join()

        assert theirs[0].demand is None, (
            'a run with no site of its own reported a wind load — it read the site '
            'belonging to another run in flight')
        assert _wind_clause(_beam_record()).demand == mine.demand, (
            "the second run moved the first run's site out from under it")
    finally:
        validators.set_site_loads(None)
