"""The property this project failed at for fourteen tracks: different music, different building.

A corpus run produced fourteen models that shared thirty-five of their thirty-six element
kinds, because four decisions were module constants rather than consequences of the
score:

    models.py:105        typology: Literal['library'] = 'library'
    models.py:106        tectonic_system: Literal['frame'] = 'frame'
    compiler_v3.py:39    STRUCTURAL_SYSTEM_ID = 'STR-SYS-STEEL-FRAME'
    datums.py:285        PLAN_X_MIN, PLAN_X_MAX = -14.0, 22.0

These tests exist so that none of the four can quietly become a constant again. They
check reachability rather than any particular assignment: a decision tree with a leaf
nothing routes to is the same defect as a constant, and it is the one that keeps
recurring here -- the nearest-neighbour selector had four dead grammars, and the frame
tree had a concrete branch that could not fire because the system behind it was screened
out.
"""

import itertools
import json
from pathlib import Path

import pytest

from backend.app.briefs import BRIEFS, choose_typology
from backend.app.compiler_v3 import compile_building_model_v3
from backend.app.facade_gates import evaluate
from backend.app.massing import MASSING_FAMILIES, choose_massing
from backend.app.models import ArchitecturalScore, AudioFeatures
from backend.app.selection import choose_envelope, choose_frame
from backend.app.tectonics import ENVELOPE_TECTONICS, FRAME_TECTONICS

ROOT = Path(__file__).parents[2]
DEMO = ROOT / 'artifacts' / 'v3_demo'
V2_DEMO = (ROOT / 'artifacts' / 'integrated_demo'
           / 'building-b7ad95fa45a6-library-steel-international-v1')

GRID = [i / 8 for i in range(9)]


@pytest.fixture(scope='module')
def features() -> AudioFeatures:
    return AudioFeatures.model_validate(
        json.loads((V2_DEMO / 'music_features.json').read_text(encoding='utf-8')))


@pytest.fixture(scope='module')
def template() -> ArchitecturalScore:
    return ArchitecturalScore.model_validate(
        json.loads((DEMO / 'architectural_score.json').read_text(encoding='utf-8')))


def _score(template: ArchitecturalScore, **values) -> ArchitecturalScore:
    return template.model_copy(update={'dimensions': [
        d.model_copy(update={'value': values[d.id]}) if d.id in values else d
        for d in template.dimensions]})


# ---------------------------------------------------------------------------
# Reachability: no dead leaves
# ---------------------------------------------------------------------------

def test_every_envelope_tectonic_is_reachable():
    hit = set()
    for mass, layering, regularity, incident in itertools.product(GRID, repeat=4):
        hit.add(choose_envelope({
            'mass': mass, 'layering': layering,
            'regularity': regularity, 'incident': incident})[0])
    assert hit == set(ENVELOPE_TECTONICS)


def test_every_buildable_frame_tectonic_is_reachable():
    hit = {choose_frame({'mass': m, 'expression': e})[0]
           for m, e in itertools.product(GRID, repeat=2)}
    assert hit == set(FRAME_TECTONICS)


def test_every_massing_family_is_reachable():
    hit = set()
    for mass, layering, regularity, incident in itertools.product(GRID, repeat=4):
        reading = {'mass': mass, 'layering': layering,
                   'regularity': regularity, 'incident': incident}
        for density in (0.1, 0.5, 0.9):
            for tempo in (0.1, 0.9):
                hit.add(choose_massing(reading, density, tempo)[0].id)
    assert hit == set(MASSING_FAMILIES)


def test_every_typology_is_reachable():
    hit = set()
    for mass, layering, regularity, incident in itertools.product(GRID, repeat=4):
        reading = {'mass': mass, 'layering': layering,
                   'regularity': regularity, 'incident': incident}
        for density in (0.1, 0.5, 0.9):
            for massing_id in MASSING_FAMILIES:
                hit.add(choose_typology(reading, density, massing_id)[0])
    assert hit == set(BRIEFS)


# ---------------------------------------------------------------------------
# The four decisions are consequences of the score, not constants
# ---------------------------------------------------------------------------

def test_two_scores_differ_in_all_four_of_type_form_style_and_structure(
        features, template):
    """The whole goal, as one assertion.

    Two scores chosen to sit at opposite ends of the axes must produce buildings that
    differ in typology, silhouette, facade grammar and structural system at once. Any
    one of those four collapsing to a constant fails here.
    """
    heavy = compile_building_model_v3(features, _score(
        template, tension_release=0.95, continuity=0.05, repetition=0.10,
        hierarchy=0.85, polyphony=0.20, density=0.75, variation=0.20,
        genre_style=0.10, interruption=0.9, tempo_of_change=0.8))
    light = compile_building_model_v3(features, _score(
        template, tension_release=0.10, continuity=0.90, repetition=0.90,
        hierarchy=0.15, polyphony=0.85, density=0.20, variation=0.85,
        genre_style=0.90, interruption=0.1, tempo_of_change=0.2))

    assert heavy.typology != light.typology
    assert heavy.selection.massing_id != light.selection.massing_id
    assert heavy.facade_grammar_id != light.facade_grammar_id
    assert heavy.structural_system_id != light.structural_system_id
    # and the vocabularies, not only the labels
    assert set(heavy.element_counts) != set(light.element_counts)


def test_the_footprint_is_not_a_constant(features, template):
    plans = set()
    for massing_id in MASSING_FAMILIES:
        model = compile_building_model_v3(features, template, massing_id=massing_id)
        plans.add((round(model.lattice.plan_x_m), round(model.lattice.plan_y_m)))
    assert len(plans) >= 5


def test_every_massing_family_compiles_to_a_standing_building(features, template):
    """A silhouette that cannot be built is worse than one that was never offered."""
    for massing_id in MASSING_FAMILIES:
        model = compile_building_model_v3(features, template, massing_id=massing_id)
        assert len(model.lattice.levels) >= 3, massing_id
        assert model.element_counts.get('column', 0) > 0, massing_id
        assert model.layer_counts.get('envelope', 0) > 0, massing_id


def test_every_grammar_compiles_and_passes_its_own_guide(features, template):
    """Each grammar is checked against the guide it claims, not against a shared rule."""
    for grammar_id in sorted(
            {g for g in __import__(
                'backend.app.tectonics', fromlist=['x']).GRAMMAR_ENVELOPE}):
        model = compile_building_model_v3(features, template, grammar_id=grammar_id)
        report = model.facade_gates
        assert report is not None and report.grammar_id == grammar_id
        assert not report.failures, (
            grammar_id, [f'{g.id}={g.measured} needs {g.required}'
                         for g in report.failures])


def test_a_gate_that_cannot_be_evaluated_never_reports_passed(features, template):
    """Critical Regionalism requires orientation data this project does not have."""
    model = compile_building_model_v3(
        features, template, grammar_id='FCD-09-CRITICAL-REGIONALISM')
    orientation = next(g for g in model.facade_gates.gates
                       if g.id == 'orientation_response')
    assert orientation.verdict == 'unevaluated'
    assert 'validation stop' in orientation.detail


def test_pinning_a_decision_overrides_the_score(features, template):
    free = compile_building_model_v3(features, template)
    pinned = compile_building_model_v3(
        features, template, massing_id='MAS-TOWER', typology='pavilion',
        grammar_id='FCD-08-MINIMALISM')
    assert pinned.selection.massing_id == 'MAS-TOWER'
    assert pinned.typology == 'pavilion'
    assert pinned.facade_grammar_id == 'FCD-08-MINIMALISM'
    assert (free.selection.massing_id, free.typology, free.facade_grammar_id) != (
        'MAS-TOWER', 'pavilion', 'FCD-08-MINIMALISM')


def test_minimalism_moves_less_under_the_same_score_than_parametricism(
        features, template):
    """The guides publish different score authorities and the emitter honours them.

    Minimalism caps score-driven dimensional variation at 12 %; Parametricism expects
    the field to swing. Two models from the *same* score must therefore differ in how
    far their elevations travelled from what the tectonic alone would draw.
    """
    strong = _score(template, genre_style=0.02, tension_release=0.95)
    minimal = compile_building_model_v3(features, strong,
                                        grammar_id='FCD-08-MINIMALISM')
    parametric = compile_building_model_v3(features, strong,
                                           grammar_id='FCD-10-PARAMETRICISM')

    def authority_used(model) -> float:
        gate = next(g for g in model.facade_gates.gates if g.id == 'score_authority')
        return gate.measured if gate.measured is not None else 0.0

    assert authority_used(minimal) <= authority_used(parametric)


# ---------------------------------------------------------------------------
# Circulation: a landing has to land
# ---------------------------------------------------------------------------

def test_every_floor_landing_is_flush_with_its_plate_and_sits_on_it(
        features, template):
    """A landing that does not meet the floor is a shelf drawn in mid-air.

    The circulation core was authored at coordinates taken from the original
    thirty-six by twenty-two metre slab -- `v3(16.0, south, ...)`, `ax = min_x - 1.5`,
    a lift shaft at `v2(18.4, 5.2)`. Once the footprint became a property of the massing
    family those numbers stopped describing anywhere: across fourteen models, eight of
    seventy-eight landings sat on the plate they claimed and more than half the treads
    on a compact tower stood outside the building.

    Two conditions, and both matter. *On the plate* means a person can reach it. *Flush*
    means the top of the landing is the floor, not a step above or below it.
    """
    from backend.app.geometry import point_inside

    for massing_id in MASSING_FAMILIES:
        model = compile_building_model_v3(features, template, massing_id=massing_id)
        by_level = {level.id: level for level in model.lattice.levels}
        landings = [e for e in model.elements if e.kind == 'stair_landing']
        assert landings, massing_id
        for landing in landings:
            level = by_level[landing.level_id]
            top = landing.position.z + landing.dimensions.z / 2.0
            assert abs(top - level.z) < 0.02, (
                massing_id, landing.id, f'top {top:.3f} against plate {level.z:.3f}')
            assert point_inside(level.plate, landing.position.x, landing.position.y), (
                massing_id, landing.id, 'landing centre is outside the plate it serves')


def test_a_landing_exists_at_every_level_a_flight_arrives_at(features, template):
    """Every flight that climbs a storey has a floor to arrive on."""
    for massing_id in MASSING_FAMILIES:
        model = compile_building_model_v3(features, template, massing_id=massing_id)
        served = {e.level_id for e in model.elements if e.kind == 'stair_landing'}
        occupied = {level.id for level in model.lattice.occupied}
        assert occupied - served == set(), (massing_id, sorted(occupied - served))


def test_only_the_approach_flights_stand_outside_the_building(features, template):
    """A flight from grade starts outside; nothing else may.

    Two flights are allowed out there and both are approaches. `F01` is the entrance
    stair from the ground to the podium. `R01` only exists when no ADA-compliant ramp
    fits the site, in which case it replaces that ramp and climbs the same rise from the
    same ground -- a compact tower with a five-metre podium and a twenty-two metre
    frontage genuinely cannot hold a switchback beside its door. Every other tread
    sitting outside every plate is a stair that missed the building.
    """
    from backend.app.geometry import point_inside

    approaches = ('-F01-', '-R01-')
    for massing_id in MASSING_FAMILIES:
        model = compile_building_model_v3(features, template, massing_id=massing_id)
        stray = [
            e.id for e in model.elements
            if e.kind == 'stair_tread'
            and not any(tag in e.id for tag in approaches)
            and not any(point_inside(level.plate, e.position.x, e.position.y)
                        for level in model.lattice.levels)]
        assert not stray, (massing_id, stray[:4])


def test_the_lift_core_is_inside_the_plates_it_passes_through(features, template):
    """A shaft segment spans one storey, so it is checked against that storey.

    The first version of this test checked every shaft against every plate in the
    building, which is a stronger claim than the geometry makes or needs: a core that
    stops where the massing stops being stackable is correct behaviour, and asserting
    otherwise would have forced the emitter to draw shafts through floors that are not
    there.
    """
    from backend.app.geometry import point_inside

    for massing_id in MASSING_FAMILIES:
        model = compile_building_model_v3(features, template, massing_id=massing_id)
        by_level = {level.id: level for level in model.lattice.levels}
        for shaft in [e for e in model.elements if e.kind == 'elevator_shaft']:
            level = by_level[shaft.level_id]
            assert point_inside(level.plate, shaft.position.x, shaft.position.y), (
                massing_id, shaft.id, level.id)


def test_no_circulation_element_carries_a_coordinate_from_the_old_slab(
        features, template):
    """The compiler's own docstring forbids absolute coordinate literals in emitters.

    The circulation emitter had a dozen of them, all inherited from a footprint that no
    longer exists. This checks the consequence rather than the source: on a plan that
    does not contain the old one, nothing may sit where the old literals were.
    """
    model = compile_building_model_v3(features, template, massing_id='MAS-TOWER')
    plan = model.lattice.plan
    circulation = [e for e in model.elements if e.semantic_layer == 'circulation']
    assert circulation
    outside = [e.id for e in circulation
               if e.position.x > plan.x_max + 6.0 or e.position.x < plan.x_min - 6.0]
    assert not outside, outside[:5]
