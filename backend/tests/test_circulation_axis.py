"""The route is laid out as one line, and everything on it meets what comes next.

Runs and landings used to be placed independently against the plan's x extents. That
looks equivalent and is not: whenever a run was shorter than its leg -- which is
whenever the 760 mm rise limit binds before the slope does -- the alternating anchors
stopped meeting, and every westward run began 3.41 m from the landing that was supposed
to feed it. The ramp was compliant on every measure §405 asks for and did not join up.

The same shape appeared twice more. The top landing was placed from a setback the
caller chose rather than from the floor it serves, and came to rest 2.14 m short of the
building; and the entry stair ended 1.2 m before a landing that itself overlapped the
plate by 450 mm, leaving 1.65 m between them that was nobody's business.

So these tests measure joints, not compliance. A route can satisfy every clause and
still arrive nowhere.
"""

import json
import math

import pytest

from backend.app.compiler_v3 import compile_building_model_v3
from backend.app.models import ArchitecturalScore, AudioFeatures

from backend.tests.test_differentiation import DEMO, V2_DEMO


# How far a joint may miss and still be a joint. A landing and the deck that arrives on
# it are cast together; this is a modelling epsilon, not a construction allowance.
JOINT_TOLERANCE_M = 0.35

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


def _inside(polygon, x: float, y: float) -> bool:
    inside = False
    count = len(polygon)
    for index in range(count):
        a, b = polygon[index], polygon[(index + 1) % count]
        if (a.y > y) != (b.y > y):
            if x < (b.x - a.x) * (y - a.y) / (b.y - a.y) + a.x:
                inside = not inside
    return inside


def _box_gap(point, centre, size) -> float:
    return math.sqrt(max(0.0, abs(point[0] - centre.x) - size.x / 2.0) ** 2
                     + max(0.0, abs(point[1] - centre.y) - size.y / 2.0) ** 2
                     + max(0.0, abs(point[2] - centre.z) - size.z / 2.0) ** 2)


def _instances(model, kind):
    return [instance for group in model.element_groups if group.kind == kind
            for instance in group.instances]


# --- the ramp is one walked line --------------------------------------------------

@pytest.mark.parametrize('massing', MASSINGS)
def test_the_plan_carries_a_continuous_centre_line(models, massing):
    """One polyline, bottom landing to top, rising and never doubling back in level."""
    plan = models[massing].accessible_route
    if plan is None:
        pytest.skip(f'{massing} builds a stair; there is no compliant ramp to walk')
    path = plan.centre_line
    assert len(path) >= 2 * len(plan.runs), massing
    for (_x0, _y0, z0), (_x1, _y1, z1) in zip(path, path[1:]):
        assert z1 >= z0 - 1e-6, f'{massing}: the route steps down at some point'
    assert path[-1][2] == pytest.approx(plan.rise_m + path[0][2], abs=1e-3)


@pytest.mark.parametrize('massing', MASSINGS)
def test_every_run_starts_and_ends_on_a_landing(models, massing):
    """The joint the layout is for. Both ends, every run, measured to the landing's
    own box rather than to its centre."""
    plan = models[massing].accessible_route
    if plan is None:
        pytest.skip(f'{massing} builds a stair')
    landings = {landing.index: landing for landing in plan.landings}
    for run in plan.runs:
        for label, index, point in (
                ('start', run.index, (run.x_start, run.y, run.z_start)),
                ('end', run.index + 1, (run.x_end, run.y, run.z_end))):
            landing = landings[index]
            gap = math.sqrt(
                max(0.0, abs(point[0] - landing.x) - landing.size_x / 2.0) ** 2
                + max(0.0, abs(point[1] - landing.y) - landing.size_y / 2.0) ** 2
                + (point[2] - landing.z) ** 2)
            assert gap <= JOINT_TOLERANCE_M, (
                f'{massing}: run {run.index} {label} is {gap:.2f} m from '
                f'landing {index}')


@pytest.mark.parametrize('massing', MASSINGS)
def test_the_route_arrives_on_the_floor_it_serves(models, massing):
    """A compliant ramp that stops short of the building is worse than no ramp: it
    occupies the place the accessible route belongs and reports the problem solved."""
    model = models[massing]
    plan = model.accessible_route
    if plan is None:
        pytest.skip(f'{massing} builds a stair')
    top = next(landing for landing in plan.landings if landing.kind == 'top')
    served = [level for level in model.lattice.levels if abs(level.z - top.z) < 0.2]
    assert served, f'{massing}: the ramp arrives at no level'
    corners = [(top.x + sx * top.size_x / 2.0, top.y + sy * top.size_y / 2.0)
               for sx in (-1, 1) for sy in (-1, 1)]
    assert any(_inside(served[0].plate, x, y) for x, y in corners), (
        f'{massing}: the top landing at ({top.x:.2f}, {top.y:.2f}) touches no part of '
        f'the {served[0].id} plate')


@pytest.mark.parametrize('massing', MASSINGS)
def test_a_turn_landing_is_deep_enough_to_turn_on(models, massing):
    """The pitch between legs is also the depth of the landing between them, so it
    cannot be narrower than 405.7.4 allows. `width + 0.25` gave 1.17 m."""
    plan = models[massing].accessible_route
    if plan is None:
        pytest.skip(f'{massing} builds a stair')
    from backend.app.ada import MIN_TURN_LANDING_M
    for landing in plan.landings:
        if landing.kind != 'turn':
            continue
        assert min(landing.size_x, landing.size_y) >= MIN_TURN_LANDING_M - 1e-6, (
            massing, landing.index, landing.size_x, landing.size_y)


@pytest.mark.parametrize('massing', MASSINGS)
def test_the_route_is_still_compliant_after_being_made_to_join_up(models, massing):
    plan = models[massing].accessible_route
    if plan is None:
        assert models[massing].accessible_route_unresolved, massing
        pytest.skip(f'{massing} records an unresolved route, which is the honest state')
    assert not plan.compliance(), (massing, plan.compliance())


# --- the stair ends on something too ----------------------------------------------

@pytest.mark.parametrize('massing', MASSINGS)
def test_every_flight_ends_on_a_landing_a_floor_or_the_ground(models, massing):
    """A flight may legitimately begin outside on grade. It may not end in the air."""
    import re

    model = models[massing]
    tread = re.compile(r'CIR-TRD-([A-Z]\d{2})-S(\d{3})')
    flights: dict[str, list] = {}
    for instance in _instances(model, 'stair_tread'):
        match = tread.match(instance.id)
        if match:
            flights.setdefault(match.group(1), []).append(
                (int(match.group(2)), instance.geometry.center))

    landings = [(instance.geometry.center, instance.geometry.size)
                for kind in ('stair_landing', 'stair_half_landing', 'ramp_landing')
                for instance in _instances(model, kind)]
    plates = [(level.z, level.plate) for level in model.lattice.levels]

    adrift = []
    for flight, steps in flights.items():
        steps.sort()
        for label, (_index, centre) in (('bottom', steps[0]), ('top', steps[-1])):
            point = (centre.x, centre.y, centre.z)
            if any(_box_gap(point, lc, ls) <= 0.45 for lc, ls in landings):
                continue
            if any(abs(centre.z - z) < 0.6 and _inside(plate, centre.x, centre.y)
                   for z, plate in plates):
                continue
            if centre.z < 0.9:
                continue      # an approach that starts on grade
            adrift.append(f'{flight} {label} at z {centre.z:.2f}')
    assert not adrift, f'{massing}: {adrift}'
