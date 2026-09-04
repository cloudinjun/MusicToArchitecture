"""The accessible approach: ADA 405 in full, or a stair that says why not.

What this replaces was one box, `rise * 6.0` long. That is a 1:6 slope on every model
the corpus produced -- exactly twice the maximum 405.2 allows -- carrying five metres of
rise in a single run where 405.6 caps a run at 760 mm, with no intermediate landings, no
handrails and no edge protection.

The tests below check the two halves of the rule. A ramp that exists must comply
completely. Where compliance is impossible on the site, a stair must be built instead
and the model must record that the accessible route is unresolved -- an almost-compliant
ramp being the one outcome worse than either, because it occupies the place an
accessible route belongs and reports the problem as solved.
"""

import json
import math
from pathlib import Path

import pytest

from backend.app.ada import (
    HANDRAIL_RISE_THRESHOLD_M, MAX_RUN_RISE_M, MAX_SLOPE, MIN_CLEAR_WIDTH_M,
    MIN_LANDING_LENGTH_M, MIN_TURN_LANDING_M, plan_switchback_ramp,
)
from backend.app.compiler_v3 import compile_building_model_v3
from backend.app.massing import MASSING_FAMILIES
from backend.app.models import ArchitecturalScore, AudioFeatures

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


# ---------------------------------------------------------------------------
# The planner
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('rise', [0.2, 0.45, 1.2, 3.0, 5.4, 8.0])
def test_a_plan_that_is_returned_is_a_plan_that_complies(rise):
    """`plan_switchback_ramp` returns nothing rather than something non-compliant."""
    plan = plan_switchback_ramp(
        rise_m=rise, width_m=1.5, x_min=-14.0, x_max=14.0, y_start=-6.0,
        y_available=24.0, z_base=0.0)
    assert plan is not None, rise
    assert plan.compliance() == []
    assert plan.steepest_slope <= MAX_SLOPE + 1e-6
    assert all(run.rise <= MAX_RUN_RISE_M + 1e-6 for run in plan.runs)
    assert plan.width_m >= MIN_CLEAR_WIDTH_M - 1e-6


def test_a_turn_landing_is_square_and_a_run_landing_is_long_enough():
    plan = plan_switchback_ramp(
        rise_m=4.0, width_m=1.2, x_min=-14.0, x_max=14.0, y_start=-6.0,
        y_available=24.0, z_base=0.0)
    assert plan is not None
    turns = [landing for landing in plan.landings if landing.kind == 'turn']
    assert len(turns) == len(plan.runs) - 1
    for landing in turns:
        assert landing.size_x >= MIN_TURN_LANDING_M - 1e-6
        assert landing.size_y >= MIN_TURN_LANDING_M - 1e-6
    for landing in plan.landings:
        assert min(landing.size_x, landing.size_y) >= MIN_LANDING_LENGTH_M - 1e-6


def test_the_planner_refuses_a_site_that_cannot_hold_a_compliant_ramp():
    """Refusing is the feature. Five metres of rise needs sixty of run."""
    assert plan_switchback_ramp(
        rise_m=5.4, width_m=1.5, x_min=-6.0, x_max=6.0, y_start=-4.0,
        y_available=6.0, z_base=0.0) is None
    # too narrow for a run plus its two landings, whatever the depth
    assert plan_switchback_ramp(
        rise_m=1.0, width_m=1.5, x_min=-1.5, x_max=1.5, y_start=-4.0,
        y_available=80.0, z_base=0.0) is None


def test_handrails_are_required_above_the_threshold_and_not_below():
    low = plan_switchback_ramp(
        rise_m=0.12, width_m=1.5, x_min=-14.0, x_max=14.0, y_start=-6.0,
        y_available=24.0, z_base=0.0)
    high = plan_switchback_ramp(
        rise_m=0.9, width_m=1.5, x_min=-14.0, x_max=14.0, y_start=-6.0,
        y_available=24.0, z_base=0.0)
    assert low is not None and not low.handrails_required
    assert high is not None and high.handrails_required
    assert HANDRAIL_RISE_THRESHOLD_M == 0.150


# ---------------------------------------------------------------------------
# What the compiler actually builds
# ---------------------------------------------------------------------------

def test_every_emitted_ramp_run_is_within_the_slope_and_rise_limits(
        features, template):
    """Measured on the member centre-line, not on a bounding box.

    A swept deck's bounding box includes its own thickness, which makes a compliant
    1:12 run measure about 1:8.6 if you divide box height by box length. That is how a
    check reports a violation that is not there, so the geometry is read the way it was
    drawn: two points and the line between them.
    """
    for massing_id in MASSING_FAMILIES:
        model = compile_building_model_v3(features, template, massing_id=massing_id)
        runs = [e for e in model.elements if e.kind == 'ramp']
        if not runs:
            assert model.accessible_route_unresolved, massing_id
            continue
        for run in runs:
            start, end = run.geometry.path[0], run.geometry.path[1]
            length = math.hypot(end.x - start.x, end.y - start.y)
            rise = abs(end.z - start.z)
            assert length > 0.5, (massing_id, run.id)
            assert rise / length <= MAX_SLOPE + 1e-6, (
                massing_id, run.id, f'1 in {length / rise:.2f}')
            assert rise <= MAX_RUN_RISE_M + 1e-6, (
                massing_id, run.id, f'{rise * 1000:.0f} mm')


def test_exactly_one_of_a_compliant_route_or_a_stated_failure(features, template):
    for massing_id in MASSING_FAMILIES:
        model = compile_building_model_v3(features, template, massing_id=massing_id)
        has_plan = model.accessible_route is not None
        has_reason = bool(model.accessible_route_unresolved)
        assert has_plan != has_reason, massing_id
        if has_plan:
            assert model.accessible_route.compliance() == [], massing_id


def test_a_ramp_carries_its_landings_curbs_and_handrails(features, template):
    model = compile_building_model_v3(features, template)
    assert model.accessible_route is not None
    counts = model.element_counts
    assert counts.get('ramp', 0) == len(model.accessible_route.runs)
    assert counts.get('ramp_landing', 0) == len(model.accessible_route.landings)
    # 405.9.2 edge protection, both sides of every run
    assert counts.get('ramp_curb', 0) == len(model.accessible_route.runs) * 2
    # 405.8 handrails, which at this rise are required
    assert model.accessible_route.handrails_required
    assert counts.get('railing', 0) > 0


def test_a_site_too_small_for_a_ramp_gets_a_stair_and_a_stated_reason(
        features, template):
    """The other half of the rule, exercised through the emitter not the planner.

    The apron depth is a parameter so this branch can be reached without inventing a
    building. On the real site every corpus model fits a compliant ramp, which is the
    right outcome and would otherwise leave the fallback untested.
    """
    from backend.app.compiler_v3 import _Builder, _emit_accessible_approach

    model = compile_building_model_v3(features, template)
    builder = _Builder(model.datum_set, model.lattice)
    xs = [point.x for point in model.lattice.levels[1].plate]
    _emit_accessible_approach(builder, model.lattice.levels,
                              model.datum_set.value('flight_width_m'),
                              (min(xs) + max(xs)) / 2.0, apron_depth_m=3.0)

    assert builder.accessible_route is None
    assert builder.unresolved_accessible_route
    reason = builder.unresolved_accessible_route
    assert '405.2' in reason and '405.6' in reason
    assert 'stair is built instead' in reason
    assert 'unresolved' in reason

    kinds = {group.kind for group in builder.groups.values()}
    assert 'ramp' not in kinds
    assert 'stair_tread' in kinds
    assert 'stair_landing' in kinds


def test_the_old_one_in_six_ramp_could_not_pass_this(features, template):
    """A regression guard aimed at the specific thing that was here.

    `rise * 6.0` is 1:6. Stating it as a test rather than only in a comment means the
    next person who reaches for a convenient multiplier finds out immediately.
    """
    model = compile_building_model_v3(features, template)
    rise = model.lattice.levels[1].z - model.lattice.levels[0].z
    old_length = rise * 6.0
    assert rise / old_length > MAX_SLOPE, 'the old ramp was 1:6 and must not pass'
    assert model.accessible_route is not None
    assert model.accessible_route.total_run_length_m > old_length * 1.5
