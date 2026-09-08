"""Focused contract tests for project-level support-space sizing premises."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.constitution import support_spaces
from backend.app.project_brief import (
    ProjectBrief,
    SupportProgramSizing,
    SupportSpaceSize,
    normalize_project_brief,
)
from backend.tests.test_project_brief import _brief


def _sizing(space_id: str = 'SP-JANITOR', *, area: float = 16.0,
            min_dimension: float = 3.2) -> SupportProgramSizing:
    return SupportProgramSizing(
        source='manual',
        basis='operations schedule reviewed upstream',
        sizes={space_id: SupportSpaceSize(
            area_m2=area, min_dimension_m=min_dimension)},
    )


def _by_id(brief: ProjectBrief):
    return {space.id: space for space in brief.resolved_spaces()}


def test_default_support_generation_remains_unchanged() -> None:
    brief = _brief()
    expected = tuple(brief.spaces) + tuple(support_spaces(
        brief.typology, brief.spaces, storeys=brief.occupied_storeys))

    assert brief.support_sizing is None
    assert brief.resolved_spaces() == expected


def test_explicit_size_replaces_only_named_auto_support_before_budget_check() -> None:
    baseline = _brief(target=347.0)
    sized = _brief(target=360.0, support_sizing=_sizing())

    assert tuple(space.model_dump() for space in sized.spaces) == tuple(
        space.model_dump() for space in baseline.spaces)
    base_by_id = _by_id(baseline)
    sized_by_id = _by_id(sized)
    assert sized_by_id['SP-JANITOR'].area_m2 == pytest.approx(16.0)
    assert sized_by_id['SP-JANITOR'].min_dimension_m == pytest.approx(3.2)
    assert sized.gross_program_area_m2 > baseline.gross_program_area_m2

    changed_fields = {'area_m2', 'min_dimension_m', 'reason'}
    for space_id, original in base_by_id.items():
        actual = sized_by_id[space_id]
        if space_id == 'SP-JANITOR':
            original_data = original.model_dump()
            actual_data = actual.model_dump()
            assert {key: actual_data[key] for key in actual_data
                    if key not in changed_fields} == {
                        key: original_data[key] for key in original_data
                        if key not in changed_fields}
            assert 'manual' in actual.reason
            assert 'needs_review=True' in actual.reason
        else:
            assert actual.model_dump() == original.model_dump()

    # The default brief still fits this target. The larger upstream premise does
    # not get applied after budgeting or silently shrunk to make it fit.
    with pytest.raises(ValidationError, match='rooms are never silently shrunk'):
        _brief(target=347.0, support_sizing=_sizing())


@pytest.mark.parametrize('space_id', ['SP-NOT-AUTO', 'SP-HALL'])
def test_support_sizing_rejects_unknown_and_explicit_room_ids(space_id: str) -> None:
    with pytest.raises(ValidationError, match='may only replace automatically'):
        _brief(support_sizing=_sizing(space_id))


def test_support_sizing_requires_review() -> None:
    with pytest.raises(ValidationError, match='needs_review'):
        SupportProgramSizing(
            source='manual', basis='unreviewed input', needs_review=False,
            sizes={'SP-JANITOR': SupportSpaceSize(area_m2=16.0,
                                                   min_dimension_m=3.2)},
        )


@pytest.mark.parametrize(
    ('area', 'min_dimension'),
    [(0.0, 1.0), (1.0, 0.0), (-1.0, 1.0)],
)
def test_support_space_size_rejects_nonpositive_dimensions(
        area: float, min_dimension: float) -> None:
    with pytest.raises(ValidationError):
        SupportSpaceSize(area_m2=area, min_dimension_m=min_dimension)


def test_support_space_size_rejects_area_smaller_than_minimum_square() -> None:
    with pytest.raises(ValidationError, match='cannot contain'):
        SupportSpaceSize(area_m2=8.0, min_dimension_m=3.0)


def test_support_sizing_normalization_round_trip_retains_provenance() -> None:
    brief = _brief(
        target=360.0,
        support_sizing=_sizing(area=18.0, min_dimension=3.0),
    )
    payload = brief.normalized_json()
    restored = normalize_project_brief(payload)

    assert payload['support_sizing'] == {
        'source': 'manual',
        'basis': 'operations schedule reviewed upstream',
        'needs_review': True,
        'sizes': {
            'SP-JANITOR': {'area_m2': 18.0, 'min_dimension_m': 3.0},
        },
    }
    assert restored.support_sizing == brief.support_sizing
    restored_janitor = _by_id(restored)['SP-JANITOR']
    assert restored_janitor.area_m2 == pytest.approx(18.0)
    assert restored_janitor.min_dimension_m == pytest.approx(3.0)
    assert 'operations schedule reviewed upstream' in restored_janitor.reason
