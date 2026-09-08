"""Contract tests for generated small-site briefs."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend.app.project_brief import (
    BriefProvenance,
    ProjectBrief,
    SiteSetbacks,
    SiteBoundary,
    normalize_project_brief,
)
from backend.app.program import SpaceRequirement


def _space(
    identifier: str = 'SP-HALL',
    *,
    area: float = 80.0,
    space_type: str = 'exhibition_foyer',
    category: str = 'public',
    area_tolerance: float = 0.9,
) -> SpaceRequirement:
    return SpaceRequirement(
        id=identifier,
        space_type=space_type,
        label=identifier,
        category=category,
        area_m2=area,
        min_dimension_m=4.0,
        level_preference='ground',
        daylight='preferred',
        occupancy_id='assembly_movable_seats',
        adjacency=[],
        reason='test requirement',
        area_tolerance=area_tolerance,
    )


def _brief(
    *,
    polygon=((0.0, 0.0), (30.0, 0.0), (0.0, 30.0)),
    area=80.0,
    target=450.0,
    spaces=None,
    storeys=1,
    site_setbacks=None,
    **kwargs,
) -> ProjectBrief:
    values = dict(
        brief_id='test-brief',
        typology='library',
        site=SiteBoundary(polygon=polygon),
        site_setbacks=site_setbacks,
        occupied_storeys=storeys,
        target_gross_area_m2=target,
        spaces=tuple(spaces or (_space(area=area),)),
        circulation_fraction=0.15,
        provenance=BriefProvenance(provider_type='agent_llm', model='test-agent'),
    )
    values.update(kwargs)
    return ProjectBrief(**values)


def test_actual_polygon_area_is_used_not_bounding_box() -> None:
    brief = _brief()
    assert brief.site.area_m2 == pytest.approx(450.0)
    assert brief.site.bbox_area_m2 == pytest.approx(900.0)
    assert brief.validation_report().site_area_m2 == pytest.approx(450.0)


def test_nonzero_setback_derives_buildable_and_massing_envelopes() -> None:
    brief = _brief(
        polygon=((0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)),
        area=10.0, target=300.0, storeys=2,
        site_setbacks=SiteSetbacks(
            setback_m=2.0, facade_projection_m=1.0,
            provenance='test input', reason='reserve the envelope', needs_review=True),
    )
    assert brief.site.area_m2 == pytest.approx(400.0)
    assert brief.buildable_shape.geom_type == 'Polygon'
    assert brief.buildable_shape.area == pytest.approx(256.0)
    assert brief.massing_limit_shape.area == pytest.approx(196.0)
    assert brief.capacity_m2 == pytest.approx(392.0)
    report = brief.validation_report()
    assert report.buildable_area_m2 == pytest.approx(256.0)
    assert report.massing_limit_area_m2 == pytest.approx(196.0)
    assert report.massing_limit_boundary


def test_concave_setback_preserves_multipolygon_pieces() -> None:
    concave = (
        (0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (12.0, 20.0),
        (12.0, 5.0), (8.0, 5.0), (8.0, 20.0), (0.0, 20.0),
    )
    brief = _brief(
        polygon=concave, area=10.0, target=350.0, storeys=4,
        site_setbacks=SiteSetbacks(
            setback_m=2.5, facade_projection_m=0.0,
            provenance='test input', reason='test concave split', needs_review=True),
    )
    assert brief.buildable_shape.geom_type == 'MultiPolygon'
    assert len(brief.validation_report().buildable_boundary) == 2
    assert brief.massing_limit_shape.geom_type == 'MultiPolygon'


def test_empty_setback_inset_is_rejected() -> None:
    with pytest.raises(ValidationError, match='buildable setback leaves an empty'):
        _brief(
            polygon=((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)),
            area=10.0, target=300.0,
            site_setbacks=SiteSetbacks(
                setback_m=6.0, facade_projection_m=0.0,
                provenance='test input', reason='deliberately impossible',
                needs_review=True),
        )


def test_facade_projection_reserve_is_applied_after_setback() -> None:
    brief = _brief(
        polygon=((0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)),
        area=10.0, target=350.0, storeys=2,
        site_setbacks=SiteSetbacks(
            setback_m=2.0, facade_projection_m=1.0,
            provenance='test input', reason='facade offset reserve', needs_review=True),
    )
    assert brief.massing_limit_shape.area < brief.buildable_shape.area
    assert brief.capacity_m2 == pytest.approx(392.0)


def test_total_budget_uses_massing_limit_capacity() -> None:
    with pytest.raises(ValidationError, match='necessary site capacity'):
        _brief(
            polygon=((0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)),
            area=10.0, target=400.0, storeys=1,
            site_setbacks=SiteSetbacks(
                setback_m=2.0, facade_projection_m=1.0,
                provenance='test input', reason='capacity test', needs_review=True),
        )


def test_site_over_500_m2_is_rejected_by_measured_area() -> None:
    with pytest.raises(ValidationError, match='exceeds the hard limit'):
        SiteBoundary(polygon=((0, 0), (25, 0), (25, 21), (0, 21)))


def test_rooms_are_not_shrunk_when_target_is_too_small() -> None:
    with pytest.raises(ValidationError, match='rooms are never silently shrunk'):
        _brief(area=180.0, target=100.0)


def test_duplicate_space_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match='space ids must be unique'):
        _brief(spaces=(_space('SP-DUP'), _space('SP-DUP', area=20.0)))


def test_support_spaces_are_added_by_existing_constitution() -> None:
    brief = _brief()
    resolved = brief.resolved_spaces()
    types = {space.space_type for space in resolved}
    assert 'public_restroom' in types
    assert 'staff_restroom' in types
    assert 'janitor' in types
    assert len(resolved) > len(brief.spaces)
    assert set(brief.validation_report().support_space_ids)


def test_explicit_circulation_budget_is_not_double_counted() -> None:
    brief = _brief(circulation_fraction=None, circulation_budget_m2=20.0)
    assert brief.circulation_area_m2 == pytest.approx(20.0)
    assert brief.gross_program_area_m2 == pytest.approx(
        brief.net_program_area_m2 + 20.0)


def test_circulation_foyer_is_inside_total_circulation_budget() -> None:
    foyer = _space('SP-FOYER', area=80.0, category='circulation')
    brief = _brief(
        spaces=(foyer,), circulation_fraction=None,
        circulation_budget_m2=100.0)
    assert brief.listed_circulation_area_m2 == pytest.approx(80.0)
    assert brief.circulation_area_m2 == pytest.approx(100.0)
    assert brief.gross_program_area_m2 == pytest.approx(
        brief.net_program_area_m2 + 100.0)
    assert brief.resolved_space_area_m2 > brief.gross_program_area_m2 - 100.0


def test_circulation_budget_cannot_be_smaller_than_foyer() -> None:
    foyer = _space('SP-FOYER', area=80.0, category='circulation')
    with pytest.raises(ValidationError, match='below explicitly listed circulation'):
        _brief(
            spaces=(foyer,), circulation_fraction=None,
            circulation_budget_m2=60.0)


def test_both_circulation_forms_are_rejected() -> None:
    with pytest.raises(ValidationError, match='exactly one'):
        _brief(circulation_budget_m2=20.0)


def test_new_bounded_brief_rejects_misread_area_tolerance() -> None:
    with pytest.raises(ValidationError, match='area_tolerance'):
        _brief(spaces=(_space(area_tolerance=0.001),))


def test_room_coordinate_fields_are_rejected_at_raw_boundary() -> None:
    raw = {
        'brief_id': 'raw',
        'typology': 'library',
        'site': {'polygon': [(0, 0), (30, 0), (0, 30)]},
        'occupied_storeys': 1,
        'target_gross_area_m2': 300,
        'spaces': [{**_space().model_dump(), 'x0': 1.0}],
        'circulation_fraction': 0.15,
        'provenance': {'provider_type': 'openai', 'model': 'gpt-test'},
    }
    with pytest.raises(ValidationError, match='geometry fields'):
        normalize_project_brief(raw)


def test_normalized_json_contains_measured_area_and_unplaced_status() -> None:
    payload = _brief().normalized_json()
    assert payload['site']['area_m2'] == pytest.approx(450.0)
    assert payload['site']['bbox_area_m2'] == pytest.approx(900.0)
    assert payload['area_accounting']['placement_status'] == 'not_evaluated'
    assert len(payload['resolved_spaces']) > len(payload['spaces'])
    json.dumps(payload)


def test_provider_provenance_is_preserved() -> None:
    raw = _brief().normalized_json()
    raw.pop('area_accounting', None)
    raw.pop('resolved_spaces', None)
    normalized = normalize_project_brief(raw)
    assert normalized.provenance.provider_type == 'agent_llm'
    assert normalized.provenance.model == 'test-agent'


def test_capacity_is_necessary_gate() -> None:
    with pytest.raises(ValidationError, match='necessary site capacity'):
        # The measured triangle is 450 m2, but one storey cannot host this unchanged
        # program plus its circulation reserve.
        _brief(area=420.0, target=800.0)
