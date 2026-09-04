"""The constraints that stand in for looking at the model.

A person modelling this never puts a lift shaft through a fire lobby. They do not avoid
it by following a rule, they avoid it by seeing it -- and the pipeline does not see, so
the rules exist to say what the eye would have said.

Two kinds of test here, and the second is the one that matters. Checking that the models
pass proves the fixes hold; checking that each rule *fires* on a case built to break it
proves the rule is a rule. A constraint that cannot fail is not protecting anything, and
every one of these was written against a real failure, so each can be shown catching it.
"""

import json

import pytest

from backend.app.compiler_v3 import compile_building_model_v3, core_reservations
from backend.app.geometry import BoxGeometry, Vector2, v3
from backend.app.models import ArchitecturalScore, AudioFeatures
from backend.app.models_v3 import ElementGroup, ElementInstance
from backend.app.spatial_rules import RULES, check_spatial_rules

from backend.tests.test_differentiation import DEMO, V2_DEMO


CASES = [
    ('library', 'MAS-SLAB'), ('museum', 'MAS-COURTYARD'),
    ('theater', 'MAS-BAR-PODIUM'), ('library', 'MAS-TOWER'),
    ('library', 'MAS-ZIGGURAT'), ('theater', 'MAS-SPLIT'),
    ('pavilion', 'MAS-PAVILION'),
]
MASSINGS = [massing for _typology, massing in CASES]


@pytest.fixture(scope='module')
def models():
    score = ArchitecturalScore.model_validate(
        json.loads((DEMO / 'architectural_score.json').read_text(encoding='utf-8')))
    features = AudioFeatures.model_validate(
        json.loads((V2_DEMO / 'music_features.json').read_text(encoding='utf-8')))
    return {massing: compile_building_model_v3(features, score,
                                               massing_id=massing, typology=typology)
            for typology, massing in CASES}


def _add(model, kind, layer, subsystem, level_id, centre, size, element_id):
    """Put one element into a copy of the model, to see whether a rule notices."""
    clone = model.model_copy(deep=True)
    clone.element_groups = list(clone.element_groups) + [ElementGroup(
        group_id=f'GRP-TEST-{element_id}', kind=kind, semantic_layer=layer,
        subsystem=subsystem, category='service', program='test',
        material_profile='white', reason='injected to test a rule',
        instances=[ElementInstance(
            id=element_id, level_id=level_id,
            geometry=BoxGeometry(center=centre, size=size),
            position=centre, dimensions=size)])]
    return clone


# --- the models pass ---------------------------------------------------------------

@pytest.mark.parametrize('massing', MASSINGS)
def test_no_model_breaks_a_spatial_rule(models, massing):
    report = models[massing].spatial
    assert report is not None, f'{massing} carries no spatial report'
    assert report.status == 'passed', {
        rule: count for rule, count in report.counts.items() if count}


@pytest.mark.parametrize('massing', MASSINGS)
def test_the_report_travels_on_the_model(models, massing):
    """A rule that only runs when somebody remembers to run it is not a constraint."""
    report = models[massing].spatial
    assert set(report.counts) == {rule.id for rule in RULES}
    assert set(report.watches) == {rule.id for rule in RULES}
    for rule_id, sees in report.watches.items():
        assert sees.endswith('.') and len(sees) > 20, rule_id


# --- and each rule can fail --------------------------------------------------------

def test_a_lift_shaft_in_a_room_is_caught(models):
    """The case from the plan: a shaft taking 41% of the refuse store."""
    model = models['MAS-SLAB']
    zone = next(instance for group in model.element_groups
                if group.kind == 'program_zone' for instance in group.instances)
    broken = _add(model, 'elevator_shaft', 'circulation', 'vertical_core',
                  zone.level_id, zone.position,
                  v3(2.6, 2.6, 3.0), 'TEST-SHAFT-IN-ROOM')
    report = check_spatial_rules(broken)
    assert report.counts['SP-SUBSYSTEM-OVERLAP'] >= 1
    assert report.status == 'failed'
    found = report.by_rule('SP-SUBSYSTEM-OVERLAP')
    assert any('TEST-SHAFT-IN-ROOM' in finding.elements for finding in found)


def test_a_surface_that_is_not_level_with_its_neighbour_is_caught(models):
    """The ramp's own failure: a deck top 120 mm above every landing it met."""
    model = models['MAS-SLAB']
    landing = next(instance for group in model.element_groups
                   if group.kind == 'ramp_landing' for instance in group.instances)
    top = landing.position.z + landing.dimensions.z / 2.0
    broken = _add(model, 'ramp_landing', 'circulation', 'ramps', landing.level_id,
                  v3(landing.position.x, landing.position.y, top + 0.12),
                  v3(1.5, 1.5, 0.24), 'TEST-STEP-UP')
    report = check_spatial_rules(broken)
    assert report.counts['SP-SURFACE-NOT-FLUSH'] >= 1
    finding = next(item for item in report.by_rule('SP-SURFACE-NOT-FLUSH')
                   if 'TEST-STEP-UP' in item.elements)
    assert finding.measure == pytest.approx(0.24, abs=0.02)


def test_a_slot_between_two_decks_is_caught(models):
    """The switchback's 250 mm gap: not a joint, a drop."""
    model = models['MAS-SLAB']
    run = next(instance for group in model.element_groups
               if group.kind == 'ramp' for instance in group.instances)
    beside = v3(run.position.x, run.position.y + run.dimensions.y + 0.25,
                run.position.z + 0.4)
    broken = _add(model, 'ramp', 'circulation', 'ramps', run.level_id, beside,
                  v3(run.dimensions.x, run.dimensions.y, 0.24), 'TEST-SLOT')
    report = check_spatial_rules(broken)
    assert report.counts['SP-FALL-GAP'] >= 1
    finding = next(item for item in report.by_rule('SP-FALL-GAP')
                   if 'TEST-SLOT' in item.elements)
    assert 0.03 < finding.measure < 0.6


def test_something_standing_in_an_atrium_is_caught(models):
    """A desk over a void is standing on nothing."""
    model = models['MAS-SLAB']
    level = next((level for level in model.lattice.levels if level.voids), None)
    assert level is not None, 'the fixture model has no void to stand in'
    ring = level.voids[0]
    centre = (sum(point.x for point in ring) / len(ring),
              sum(point.y for point in ring) / len(ring))
    broken = _add(model, 'desk', 'program', 'furniture', level.id,
                  v3(centre[0], centre[1], level.z + 0.4), v3(1.4, 0.7, 0.75),
                  'TEST-DESK-IN-VOID')
    report = check_spatial_rules(broken)
    assert report.counts['SP-STANDS-IN-VOID'] >= 1
    assert any('TEST-DESK-IN-VOID' in finding.elements
               for finding in report.by_rule('SP-STANDS-IN-VOID'))


def test_a_plane_that_cut_the_void_out_of_itself_is_not_standing_in_it(models):
    """The ceiling spans the plate and carries the courtyard as a hole. Testing the
    centre of its bounding box called a correctly-built plane a mistake."""
    for massing in ('MAS-COURTYARD', 'MAS-SLAB'):
        report = models[massing].spatial
        offenders = [finding for finding in report.by_rule('SP-STANDS-IN-VOID')
                     if 'CLG' in ' '.join(finding.elements)]
        assert not offenders, (massing, offenders)


# --- the reservation that makes the first rule pass --------------------------------

@pytest.mark.parametrize('massing', MASSINGS)
def test_the_cores_are_reserved_before_the_program_is_banded(models, massing):
    """The fix behind SP-SUBSYSTEM-OVERLAP, checked at its source.

    The reservation used to be a constant rectangle -- 18.4, 5.2 to 21.4, 9.4 -- from
    a footprint the pipeline stopped using long ago, and the program was banded around
    a core that was not there.
    """
    model = models[massing]
    reserved = core_reservations(model.lattice, model.datum_set)
    assert reserved, f'{massing}: no core reserved'
    for x0, y0, x1, y1 in reserved:
        assert x1 > x0 and y1 > y0
        # Inside the building, not at a coordinate from a previous footprint.
        xs = [point.x for level in model.lattice.levels for point in level.plate]
        ys = [point.y for level in model.lattice.levels for point in level.plate]
        assert min(xs) - 6 < (x0 + x1) / 2 < max(xs) + 6, (massing, x0, x1)
        assert min(ys) - 6 < (y0 + y1) / 2 < max(ys) + 6, (massing, y0, y1)


@pytest.mark.parametrize('massing', MASSINGS)
def test_the_stair_is_drawn_where_the_reservation_was_cut(models, massing):
    """One search, read twice.

    Two of these existed -- the emitter stopped at the first candidate clearing the
    third-diagonal rule, the reservation took the most remote one outright -- and on a
    stepped plate they chose different points. The program was banded around one core
    and the stair drawn at the other.
    """
    model = models[massing]
    reserved = core_reservations(model.lattice, model.datum_set)
    stringers = [instance for group in model.element_groups
                 if group.kind == 'stair_stringer' for instance in group.instances]
    assert stringers, massing
    inside = 0
    for instance in stringers:
        for x0, y0, x1, y1 in reserved:
            if (x0 - 1.0 <= instance.position.x <= x1 + 1.0
                    and y0 - 1.0 <= instance.position.y <= y1 + 1.0):
                inside += 1
                break
    # The external approach flight is deliberately outside; the cores are not.
    assert inside >= len(stringers) * 0.6, (
        f'{massing}: only {inside} of {len(stringers)} stringers stand in a reserved '
        f'core, so the stairs are not where the program was told they would be')


@pytest.mark.parametrize('massing', MASSINGS)
def test_no_room_is_laid_out_over_a_reserved_core(models, massing):
    """The reservation checked where it is made, not only where it shows.

    `SP-SUBSYSTEM-OVERLAP` catches this downstream, once the shaft and the treads have
    been built and can be seen standing in a room. This asks the allocator directly, and
    it is the test that names the cause: a room laid out west of a stair used to write
    its finishing edge into the cursor of the strip *east* of the stair, which begins
    further east still. The cursor then read behind that strip's own beginning, and the
    next room started from it and ran the full width of the plate -- a theatre foyer with
    the lift shaft standing in the middle of it, on a level where the core had been
    reserved and the bands correctly cut around it.

    Levels named in `cores_unreserved` are excluded: there the reservation was
    deliberately not applied because cutting it out left nothing to lay out on, and the
    overlap is a stated consequence rather than this failure.
    """
    model = models[massing]
    reserved = core_reservations(model.lattice, model.datum_set)
    excused = set(model.program_allocation.cores_unreserved)
    for zone in model.program_allocation.zones:
        if zone.level_id in excused:
            continue
        for x0, y0, x1, y1 in reserved:
            overlap = (max(0.0, min(zone.x1, x1) - max(zone.x0, x0))
                       * max(0.0, min(zone.y1, y1) - max(zone.y0, y0)))
            assert overlap < 0.5, (
                f'{massing}: {zone.space_id} on {zone.level_id} takes {overlap:.1f} m2 '
                f'of the core reserved at ({x0:.1f}, {y0:.1f})-({x1:.1f}, {y1:.1f})')
