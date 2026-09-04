"""The centre-line skeleton, and what it is allowed to leave unconnected.

These lock the answer to a question that used to be asked with a tolerance: is a member
attached to anything? Measuring distances got it wrong in both directions, and one of
the wrong answers hid a real fault. Joists bear on the top flange of the girders under
them, so their centre-lines run 140 mm above the girders' and never cross. Consecutive
bays shared an end node, so the joist field daisy-chained across the plate and none of
that chain touched a girder -- yet only the dozen edge joists with no neighbour to chain
to ever looked wrong. A real defect reporting at a twentieth of its size is worse than
no report, because it looks like it has been dealt with.
"""

import json

import pytest

from backend.app.axis import AxisSkeleton, BEARING_M, _point_segment_distance
from backend.app.compiler_v3 import compile_building_model_v3
from backend.app.geometry import Vector3
from backend.app.models import ArchitecturalScore, AudioFeatures

from backend.tests.test_differentiation import DEMO, V2_DEMO


def v3(x: float, y: float, z: float) -> Vector3:
    return Vector3(x=x, y=y, z=z)


# The frame proper: everything that carries gravity down through linear members. These
# reach the ground through shared nodes alone, with no plate in the path.
FRAME_KINDS = {
    'column', 'piloti_column', 'primary_beam', 'secondary_joist', 'heavy_joist',
    'brace', 'knee_brace', 'outrigger_strut',
}

# Members that legitimately share no node with another member: both land on a plate,
# and a plate has no centre-line to share. Their hosts are carried by the dependency
# graph instead, which is where element-to-plate relations live.
PLATE_BORNE_KINDS = {'stair_stringer', 'entry_canopy'}

CASES = [
    ('library', 'MAS-SLAB'), ('museum', 'MAS-COURTYARD'),
    ('theater', 'MAS-BAR-PODIUM'), ('library', 'MAS-TOWER'),
    ('library', 'MAS-ZIGGURAT'), ('theater', 'MAS-SPLIT'),
    ('pavilion', 'MAS-PAVILION'),
]


@pytest.fixture(scope='module')
def score() -> ArchitecturalScore:
    return ArchitecturalScore.model_validate(
        json.loads((DEMO / 'architectural_score.json').read_text(encoding='utf-8')))


@pytest.fixture(scope='module')
def features() -> AudioFeatures:
    return AudioFeatures.model_validate(
        json.loads((V2_DEMO / 'music_features.json').read_text(encoding='utf-8')))


@pytest.fixture(scope='module')
def models(score, features):
    return {massing: compile_building_model_v3(features, score,
                                               massing_id=massing, typology=typology)
            for typology, massing in CASES}


def _axis_checks(model) -> dict[str, object]:
    return {check.id: check for check in model.axis_report.checks}


# --- the skeleton itself ---------------------------------------------------------

def test_coincident_points_register_to_one_node():
    skeleton = AxisSkeleton()
    first = skeleton.node(v3(4.0, 2.0, 0.0))
    # The same point reached by a different arithmetic path, differing in the last bits.
    second = skeleton.node(v3(2.0 + 2.0, 6.0 - 4.0, 0.0))
    assert first == second


def test_a_beam_landing_partway_up_a_column_shares_its_node():
    """The T-joint. Endpoint-only matching would call this column unconnected."""
    skeleton = AxisSkeleton()
    skeleton.segment('COL', [v3(0.0, 0.0, 0.0), v3(0.0, 0.0, 8.0)], 'columns')
    skeleton.segment('BEAM', [v3(0.0, 0.0, 4.0), v3(6.0, 0.0, 4.0)], 'beams')
    skeleton.finalise()
    assert skeleton.connections()['COL'] == {'BEAM'}
    assert not skeleton.isolated()


def test_a_joist_bearing_on_a_girder_is_joined_although_the_axes_never_cross():
    skeleton = AxisSkeleton()
    skeleton.segment('GIRDER', [v3(0.0, 0.0, 3.0), v3(8.0, 0.0, 3.0)], 'beams')
    # 140 mm higher: sitting on the girder's top flange, as a joist does.
    skeleton.segment('JOIST', [v3(4.0, 0.0, 3.14), v3(4.0, 6.0, 3.14)], 'beams')
    skeleton.finalise()
    assert skeleton.isolated() == ['GIRDER', 'JOIST'], 'geometry alone cannot pair these'

    declared = AxisSkeleton()
    declared.segment('GIRDER', [v3(0.0, 0.0, 3.0), v3(8.0, 0.0, 3.0)], 'beams')
    declared.segment('JOIST', [v3(4.0, 0.0, 3.14), v3(4.0, 6.0, 3.14)], 'beams')
    declared.attach('JOIST', 'GIRDER')
    declared.finalise()
    assert not declared.isolated()
    assert not declared.strained


def test_a_support_declared_out_of_reach_is_reported_not_joined():
    """The failure that hash order produced: a member naming a host far away."""
    skeleton = AxisSkeleton()
    skeleton.segment('STRUT', [v3(0.0, 0.0, 3.0), v3(0.0, 2.0, 5.0)], 'bracing')
    skeleton.segment('FASCIA', [v3(34.0, 0.0, 3.0), v3(40.0, 0.0, 3.0)], 'beams')
    skeleton.attach('STRUT', 'FASCIA')
    skeleton.finalise()
    assert [owner for owner, _host, _gap in skeleton.strained] == ['STRUT']
    assert skeleton.strained[0][2] > BEARING_M
    assert 'STRUT' in skeleton.isolated(), 'a strained bearing must not count as a joint'


def test_nearest_owner_picks_the_line_through_the_point():
    skeleton = AxisSkeleton()
    skeleton.segment('FAS-A', [v3(0.0, 0.0, 3.0), v3(10.0, 0.0, 3.0)], 'beams')
    skeleton.segment('FAS-B', [v3(0.0, 30.0, 3.0), v3(10.0, 30.0, 3.0)], 'beams')
    assert skeleton.nearest_owner(v3(5.0, 0.0, 3.0), 'FAS-') == 'FAS-A'
    assert skeleton.nearest_owner(v3(5.0, 29.9, 3.0), 'FAS-') == 'FAS-B'
    assert skeleton.nearest_owner(v3(5.0, 0.0, 3.0), 'NOTHING-') is None


# --- the compiled models ---------------------------------------------------------

@pytest.mark.parametrize('massing', [massing for _typology, massing in CASES])
def test_every_declared_bearing_reaches_its_host(models, massing):
    check = _axis_checks(models[massing])['AXIS-DECLARED-BEARING-MEETS']
    assert check.status == 'passed', check.affected_ids


@pytest.mark.parametrize('massing', [massing for _typology, massing in CASES])
def test_unconnected_members_are_only_the_ones_that_land_on_a_plate(models, massing):
    check = _axis_checks(models[massing])['AXIS-MEMBER-CONNECTIVITY']
    assert check.status == 'passed', check.affected_ids


@pytest.mark.parametrize('massing', [massing for _typology, massing in CASES])
def test_the_frame_reaches_the_ground_through_shared_nodes_alone(models, massing):
    """No member of the frame is floating, and none needs a plate to get down.

    This is the invariant the whole skeleton exists to state. It is asserted from the
    model's own check rather than recomputed here: the compiler holds the skeleton the
    emitters registered to, while `instance.supports` on the finished model has been
    cleared and re-derived by the dependency stage. Rebuilding from the re-derived list
    would test the inference against itself.
    """
    check = _axis_checks(models[massing])['AXIS-FRAME-TO-GROUND']
    assert check.status == 'passed', check.affected_ids


@pytest.mark.parametrize('massing', [massing for _typology, massing in CASES])
def test_a_facade_fin_names_the_member_it_brackets_to(models, massing):
    """The fin stands off the skin, so no geometry rule can pair it with its carrier.

    Emitted without a declared support it was the largest floating population in the
    model, and a downstream rule guessed a host for it afterwards -- an answer resting
    on nothing. Where the family has no mullion the fin brackets to the floor-edge
    fascia instead, which is a member that exists at its base.
    """
    model = models[massing]
    fins = [instance for group in model.element_groups if group.kind == 'screen_fin'
            for instance in group.instances]
    if not fins:
        pytest.skip(f'{massing} draws no screen fin')
    geometry_of = {instance.id: instance.geometry
                   for group in model.element_groups for instance in group.instances}
    for fin in fins:
        assert fin.supports, f'{fin.id} hangs off nothing'
        gaps = []
        for host_id in fin.supports:
            host = geometry_of.get(host_id)
            if host is None or getattr(host, 'type', '') != 'member':
                continue
            for point in fin.geometry.path:
                gaps += [_point_segment_distance(point, a, b)
                         for a, b in zip(host.path, host.path[1:])]
        assert gaps, f'{fin.id} names no member to bracket to'
        assert min(gaps) <= BEARING_M, (
            f'{fin.id} names a carrier {min(gaps):.2f} m from its own line')
