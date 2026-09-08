"""Whole-root geometry and rejection remain independent between proposals."""
import pytest
from shapely.geometry import box

from backend.app.datums import compile_datum_set
from backend.app.joint_layout import root_proposals
from backend.app.legacy_program_layout import LegacyLayoutControls, LayoutRejected
from backend.tests.test_legacy_program_layout import _brief, _score


def controls():
    return LegacyLayoutControls(backbone_layout='distributed_cores',stair_run_axis='x',
        core_inset_fraction=.15,secondary_core_inset_fraction=.08,
        lift_layout='core_front_inner',arrival_layout='complete_forecourt',
        foyer_layout='hall_front_shared',hall_depth_position=.5,
        arrival_facade_allowance_m=.4)


def test_relations_move_a_whole_core_relative_to_unchanged_hall_and_parcel():
    brief,score = _brief(),_score()
    proposals = [next(root_proposals(brief,compile_datum_set(score),controls(),relation))
        for relation in ('concentrated_threshold','separated_terminals')]
    first,second = proposals
    assert first.hall_bounds == second.hall_bounds
    assert first.primary_left == second.primary_left
    assert first.secondary_bottom != second.secondary_bottom
    hall = box(*first.hall_bounds)
    assert hall.area == pytest.approx(110.)
    assert brief.massing_limit_shape.covers(hall)
    depth = hall.bounds[3]-hall.bounds[1]
    assert depth >= 6 and 80/depth >= 6 and 30/depth >= 4
    assert list(root_proposals(brief,compile_datum_set(score),controls(),first.relation))[0] == first


def test_full_author_rebuilds_secondary_core_and_arrival_for_each_root(monkeypatch):
    from backend.app import layout_search
    from backend.app.program_volumes import organize_program_volumes
    captured = []
    rejections = []
    def stop(items,initial,proposals,**kwargs):
        captured.append(list(initial))
        return layout_search.LayoutSearchResult(list(initial),False,0,False,list(items))
    monkeypatch.setattr(layout_search,'search_layout',stop)
    brief,score = _brief(),_score()
    # This unit test stops before room placement. Two storeys isolate root
    # identity from the separate four-storey circulation-capacity rejection.
    brief = brief.model_copy(update={'occupied_storeys':2})
    for relation in ('concentrated_threshold','separated_terminals'):
        root = next(root_proposals(brief,compile_datum_set(score),controls(),relation))
        with pytest.raises(LayoutRejected) as exc:
            organize_program_volumes(score,'theater',project_brief=brief,
                legacy_controls=controls().model_copy(update={'root_proposal':root}))
        rejections.append(exc.value.findings)
    assert len(captured) == 2, rejections
    cores = [next(p for p in records if p.identifier=='PV-L01-CIRC-1') for records in captured]
    assert cores[0].shape.area == pytest.approx(cores[1].shape.area)
    assert cores[0].shape.bounds != cores[1].shape.bounds
    assert not {id(p) for p in captured[0]} & {id(p) for p in captured[1]}
    for records in captured:
        assert any(p.identifier=='PV-L01-CIRC-4' for p in records)
        foyer = next(p for p in records if p.spaces==['SP-FOYER'])
        assert foyer.shape.area == pytest.approx(22.)
        assert foyer.shared_route_volume_ids


def test_root_rejection_restarts_the_whole_author_without_returning_a_partial(monkeypatch):
    from backend.app import candidate_planning as planner
    seen = []
    def reject(score,typology,*,project_brief,legacy_controls):
        seen.append(legacy_controls.root_proposal)
        raise LayoutRejected(['whole assembly rejected'])
    monkeypatch.setattr(planner,'organize_program_volumes',reject)
    result = planner.plan_compact_candidate(_score(),_brief(),controls=controls(),joint_layout=True)
    assert len(seen) == 2 and seen[0].hall_bounds != seen[1].hall_bounds
    assert result.volumes is None
    assert all(a['status']=='form_unresolved' for a in result.attempts)
    assert all(a['findings']==['whole assembly rejected'] for a in result.attempts)
    assert result.composition_basis['joint_root']['geometry_status']=='not_evaluated'


def test_residual_hall_keeps_proportion_and_avoids_complete_arrival(monkeypatch):
    from backend.app import layout_search, approach
    from backend.app.program_volumes import organize_program_volumes
    brief,score = _brief(),_score()
    brief = brief.model_copy(update={'site_setbacks':brief.site_setbacks.model_copy(
        update={'facade_projection_m':1.11588})})
    control = controls().model_copy(update={'arrival_facade_allowance_m':1.11588})
    root = next(root_proposals(brief,compile_datum_set(score),control,'concentrated_threshold'))
    captured = {}
    original = approach.plan_compact_arrival
    def arrival(**kwargs):
        value = original(**kwargs)
        captured['arrival'] = value.reserved_footprint(kwargs['origin'],kwargs['tangent'],
            kwargs['outward'],landing_clearance_m=kwargs['landing_clearance_m'])
        return value
    def stop(items,initial,proposals,**kwargs):
        captured['batch'] = next(batch for batch in proposals(items[0],tuple(initial)) if batch is not None)
        return layout_search.LayoutSearchResult(list(initial),False,0,False,list(items))
    monkeypatch.setattr(approach,'plan_compact_arrival',arrival)
    monkeypatch.setattr(layout_search,'search_layout',stop)
    with pytest.raises(LayoutRejected):
        organize_program_volumes(score,'theater',project_brief=brief,
            legacy_controls=control.model_copy(update={'root_proposal':root}))
    halls = [p.shape for p in captured['batch'] if p.role=='archetype']
    assert sum(p.area for p in halls) == pytest.approx(110.)
    for hall in halls:
        assert hall.bounds[3]-hall.bounds[1] == pytest.approx(root.hall_bounds[3]-root.hall_bounds[1])
        assert hall.intersection(captured['arrival']).area < 1e-7
        assert brief.massing_limit_shape.buffer(1e-7).covers(hall)
    assert any(p.role=='sectional_clearance' for p in captured['batch'])


def test_budget_rejection_reports_exact_shared_foyer_union():
    from backend.app.program_volumes import organize_program_volumes
    from shapely.ops import unary_union
    brief,score = _brief(),_score()
    root = next(root_proposals(brief,compile_datum_set(score),controls(),'separated_terminals'))
    with pytest.raises(LayoutRejected,match='Circulation union needs') as result:
        organize_program_volumes(score,'theater',project_brief=brief,
            legacy_controls=controls().model_copy(update={'root_proposal':root}))
    rows = result.value.rectangles
    measured = sum(unary_union([box(*p['rect']) for p in rows
        if p['level']==level and p['category']=='circulation']).area for level in range(4))
    assert measured > brief.circulation_area_m2
    assert f'{measured:.3f}' in result.value.findings[0]


def test_narrow_field_rotates_whole_core_and_preserves_shared_foyer(monkeypatch):
    from backend.app import layout_search
    from backend.app.program_volumes import organize_program_volumes
    brief,score = _brief(),_score()
    brief = brief.model_copy(update={'site_setbacks':brief.site_setbacks.model_copy(
        update={'facade_projection_m':1.23046})})
    control = controls().model_copy(update={'arrival_facade_allowance_m':1.23046})
    root = next(root_proposals(brief,compile_datum_set(score),control,'concentrated_threshold'))
    assert root.secondary_run_axis == 'x'
    assert root.foyer_placement == 'between_cores'
    assert box(*root.hall_bounds).area == pytest.approx(110.)
    separated = next(root_proposals(brief,compile_datum_set(score),control,'separated_terminals'))
    assert separated.secondary_run_axis == 'y'
    assert separated.foyer_placement == 'hall_front'
    assert 'exact residual placement' in separated.basis
    assert box(*separated.hall_bounds).area == pytest.approx(110.)
    captured=[]
    def stop(items,initial,proposals,**kwargs):
        captured.extend(initial)
        return layout_search.LayoutSearchResult(list(initial),False,0,False,list(items))
    monkeypatch.setattr(layout_search,'search_layout',stop)
    with pytest.raises(LayoutRejected):
        organize_program_volumes(score,'theater',project_brief=brief,
            legacy_controls=control.model_copy(update={'root_proposal':root}))
    ground={p.identifier:p for p in captured if p.level==0}
    first=ground['PV-L01-CIRC-0'].shape
    second=ground['PV-L01-CIRC-1'].shape
    assert first.area==pytest.approx(second.area)
    assert second.bounds[2]-second.bounds[0] > second.bounds[3]-second.bounds[1]
    foyer=ground['PV-L01-SP-FOYER']
    assert foyer.shape.area==pytest.approx(22.)
    assert foyer.shared_route_volume_ids
    assert not any(foyer.shape.intersection(core).area>1e-7 for core in (first,second))
    assert all(brief.massing_limit_shape.buffer(1e-7).covers(p.shape) for p in captured)


def test_narrow_parcel_frontage_is_local_not_a_full_width_hall_exclusion():
    from backend.app.project_brief import SiteBoundary
    brief, score = _brief(), _score()
    brief = brief.model_copy(update={'site': SiteBoundary(
        polygon=[(0,0),(28,0),(28,16),(0,16)])})
    control = controls().model_copy(update={'arrival_facade_allowance_m':1.0})
    before = brief.model_dump_json()
    root = next(root_proposals(brief,compile_datum_set(score),control,'separated_terminals'))
    assert 'exact residual placement' in root.basis
    assert root.hall_placement == 'residual_domain'
    assert root.relation == 'separated_terminals'
    hall = box(*root.hall_bounds)
    assert hall.area == pytest.approx(110.)
    assert hall.bounds[3]-hall.bounds[1] >= 6.
    assert brief.massing_limit_shape.covers(hall)
    assert brief.model_dump_json() == before
