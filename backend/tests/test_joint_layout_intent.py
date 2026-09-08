"""Relational intent stays traceable and never claims geometry feasibility."""
import pytest

from backend.app.candidate_planning import joint_layout_intent
from backend.tests.test_legacy_program_layout import _score


@pytest.mark.parametrize('value,expected', [
    (0., 'concentrated_threshold'), (.5, 'concentrated_threshold'),
    (1., 'separated_terminals')])
def test_relations_reachable_without_corpus_tuning(value, expected):
    score = _score()
    dimension = next(d for d in score.dimensions if d.id == 'interruption')
    dimension.value, dimension.confidence = value, 1.
    intent = joint_layout_intent(score)
    assert intent['relation'] == expected
    assert intent['geometry_status'] == 'not_evaluated'
    assert intent == joint_layout_intent(score)


def test_unknown_or_zero_confidence_does_not_select_separation():
    score = _score()
    dimension = next(d for d in score.dimensions if d.id == 'interruption')
    dimension.value, dimension.confidence = 1., 0.
    assert joint_layout_intent(score)['relation'] == 'concentrated_threshold'
    score.dimensions = [d for d in score.dimensions if d.id != 'interruption']
    intent = joint_layout_intent(score)
    assert intent['authority'] == 'design_fixture'
    assert intent['applied_position'] == .5


@pytest.mark.parametrize('relation', ['concentrated_threshold', 'separated_terminals'])
def test_explicit_relationship_pin_is_preserved(relation):
    intent = joint_layout_intent(_score(), relation=relation)
    assert intent['relation'] == relation
    assert intent['authority'] == 'pinned'
    with pytest.raises(ValueError):
        joint_layout_intent(_score(), relation='random')
