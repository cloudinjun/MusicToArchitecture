"""Fast contract tests for the bounded legacy Program Volume adapter.

These tests keep a compact custom theater brief at the public
``organize_program_volumes`` boundary.  They deliberately stop before native
exports: this file verifies the upstream massing contract and its registration
round-trip, while downstream member generation has its own gates.
"""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from backend.app.legacy_program_layout import LegacyLayoutControls
from backend.app.models import ArchitecturalScore, ScoreDimension
from backend.app.project_brief import ProjectBrief
from backend.app.program_massing import datums_for, lattice_for
from backend.app.program_volumes import organize_program_volumes


_DIMENSIONS = (
    'genre_style', 'hierarchy', 'repetition', 'variation', 'density',
    'continuity', 'interruption', 'polyphony', 'tension_release',
    'tempo_of_change',
)


def _score() -> ArchitecturalScore:
    return ArchitecturalScore(
        score_id='legacy-layout-contract-test',
        source_audio_sha256='1' * 64,
        dimensions=[
            ScoreDimension(
                id=dimension,
                value=0.4,
                source_feature=f'test_{dimension}',
                extraction_method='manual',
                confidence=1.0,
                architectural_proposal='bounded legacy layout contract test',
            )
            for dimension in _DIMENSIONS
        ],
        mapping_rules=[],
    )


def _brief() -> ProjectBrief:
    """A small, valid theater brief that does not depend on run artifacts."""
    spaces = [
        {
            'id': 'SP-AUDITORIUM', 'space_type': 'auditorium',
            'label': 'Auditorium', 'category': 'public', 'area_m2': 80.0,
            'min_dimension_m': 6.0, 'level_preference': 'ground',
            'daylight': 'none', 'occupancy_id': 'assembly_fixed_seats',
            'adjacency': ['SP-STAGE', 'SP-FOYER'], 'reason': 'test brief',
        },
        {
            'id': 'SP-STAGE', 'space_type': 'stage', 'label': 'Stage',
            'category': 'service', 'area_m2': 30.0, 'min_dimension_m': 4.0,
            'level_preference': 'ground', 'daylight': 'none',
            'occupancy_id': 'stage', 'adjacency': ['SP-AUDITORIUM'],
            'reason': 'test brief',
        },
        {
            'id': 'SP-FOYER', 'space_type': 'theatre_foyer', 'label': 'Foyer',
            'category': 'circulation', 'area_m2': 22.0, 'min_dimension_m': 3.0,
            'level_preference': 'ground', 'daylight': 'preferred',
            'occupancy_id': 'lobby_first_corridor',
            'adjacency': ['SP-AUDITORIUM'], 'reason': 'test brief',
        },
        {
            'id': 'SP-BAR', 'space_type': 'cafe', 'label': 'Bar',
            'category': 'public', 'area_m2': 28.0, 'min_dimension_m': 4.0,
            'level_preference': 'low', 'daylight': 'preferred',
            'occupancy_id': 'assembly_movable_seats', 'adjacency': ['SP-FOYER'],
            'reason': 'test brief',
        },
        {
            'id': 'SP-DRESSING', 'space_type': 'staff_support',
            'label': 'Dressing', 'category': 'private', 'area_m2': 12.0,
            'min_dimension_m': 2.5, 'level_preference': 'ground',
            'daylight': 'none', 'occupancy_id': 'office',
            'adjacency': ['SP-STAGE'], 'reason': 'test brief',
        },
        {
            'id': 'SP-REHEARSAL', 'space_type': 'seminar', 'label': 'Rehearsal',
            'category': 'public', 'area_m2': 40.0, 'min_dimension_m': 5.0,
            'level_preference': 'low', 'daylight': 'preferred',
            'occupancy_id': 'assembly_movable_seats', 'adjacency': ['SP-BAR'],
            'reason': 'test brief',
        },
    ]
    return ProjectBrief.model_validate({
        'brief_id': 'legacy-layout-compact-fixture',
        'typology': 'theater',
        'site': {'polygon': [(0.0, 0.0), (25.0, 0.0),
                             (25.0, 20.0), (0.0, 20.0)]},
        'site_setbacks': {
            'setback_m': 1.0,
            'facade_projection_m': 0.4,
            'provenance': 'test premise',
            'reason': 'reserve a facade collar inside the parcel',
            'needs_review': True,
        },
        'occupied_storeys': 4,
        'target_gross_area_m2': 900.0,
        'spaces': spaces,
        'circulation_budget_m2': 450.0,
        'provenance': {'provider_type': 'manual', 'model': 'test-fixture'},
    })


def _organize(score: ArchitecturalScore, brief: ProjectBrief, **layout):
    return organize_program_volumes(
        score,
        'theater',
        project_brief=brief,
        legacy_controls=LegacyLayoutControls(seed=17, iterations=120, **layout),
    )


def test_public_legacy_entry_keeps_volumes_inside_setback_and_facade_reserve():
    score = _score()
    brief = _brief()
    model = _organize(score, brief)

    assert model.project_brief is brief
    assert model.grammar_id == 'PVG-LEGACY-ELLIPSE'
    assert brief.site.area_m2 == pytest.approx(500.0)
    assert brief.buildable_shape.area == pytest.approx(414.0)
    assert brief.massing_limit_shape.area == pytest.approx(381.84)
    # The second inset is a real collar, so a generator that only honors the
    # parcel setback cannot satisfy this contract.
    assert brief.buildable_shape.difference(brief.massing_limit_shape).area > 0.0

    limit = brief.massing_limit_shape
    for volume in model.volumes:
        assert limit.buffer(1e-6).covers(box(*model.rect_of(volume)))
    for union in model.level_unions:
        shape = Polygon(union.boundary, holes=union.voids)
        assert limit.buffer(1e-6).covers(shape)
        assert union.gross_area_m2 == pytest.approx(shape.area, abs=1e-4)


def test_lift_assembly_is_reserved_before_search_and_timeout_keeps_partial_evidence(monkeypatch):
    from backend.app.layout_search import SearchDeadline, LayoutSearchTimeout
    from backend.app.legacy_program_layout import LayoutRejected
    from backend.app.portals import APPROACH_DEPTH_M, APPROACH_WIDTH_M

    def expired(self):
        raise LayoutSearchTimeout

    monkeypatch.setattr(SearchDeadline, 'check', expired)
    brief = _brief()
    original = brief.model_dump()
    with pytest.raises(LayoutRejected, match='Layout time budget') as result:
        _organize(_score(), brief, lift_layout='core_front_inner', core_inset_fraction=.15)
    assert brief.model_dump() == original
    rectangles = {r['id']: r for r in result.value.rectangles}
    for index in range(brief.occupied_storeys):
        shaft, spine, landing = [box(*rectangles[f'PV-L{index+1:02d}-CIRC-{i}']['rect'])
                                 for i in (3, 2, 5)]
        assert shaft.boundary.intersection(landing.boundary).length >= APPROACH_WIDTH_M
        assert spine.intersection(landing).area == pytest.approx(landing.area)
        x0,y0,x1,y1 = landing.bounds
        assert min(x1-x0,y1-y0) >= APPROACH_DEPTH_M
        assert brief.massing_limit_shape.buffer(1e-7).covers(shaft.union(landing))
    # This proves a retained spatial proposal, not room fit or lift operation.
    assert any('unresolved at unchanged' in finding for finding in result.value.findings)


def test_group_priority_uses_the_whole_spatial_batch(monkeypatch):
    from backend.app import layout_search
    from backend.app.legacy_program_layout import LayoutRejected

    observed = []

    def capture(items, initial, proposals, **kwargs):
        observed.extend(tuple(space.id for space in item[1]) for item in items)
        return layout_search.LayoutSearchResult(list(initial), False, 0, False, list(items))

    monkeypatch.setattr(layout_search, 'search_layout', capture)
    with pytest.raises(LayoutRejected):
        _organize(_score(), _brief(), room_groups=[{
            'space_ids':['SP-FIRE','SP-REFUSE'], 'axis':'y',
            'reason':'Grouped service owners precede a smaller standalone foyer'}])
    assert observed.index(('SP-FIRE','SP-REFUSE')) < observed.index(('SP-FOYER',))
    assert observed.index(('SP-LOADING',)) < observed.index(('SP-FIRE','SP-REFUSE'))


def test_foyer_and_complete_hall_companions_are_committed_before_room_search(monkeypatch):
    from backend.app import layout_search
    from backend.app.legacy_program_layout import LayoutRejected
    captured = []

    def capture(items, initial, proposals, **kwargs):
        captured.extend(initial)
        return layout_search.LayoutSearchResult(list(initial),False,0,False,list(items))

    monkeypatch.setattr(layout_search,'search_layout',capture)
    brief = _brief()
    with pytest.raises(LayoutRejected):
        _organize(_score(),brief,core_inset_fraction=.15,lift_layout='core_front_inner',
                  arrival_layout='west_forecourt',foyer_layout='hall_front_shared')
    identifiers = [p.identifier for p in captured]
    assert identifiers.index('PV-L01-SP-FOYER') < identifiers.index('PV-L01-SP-AUDITORIUM')
    companions = [p for p in captured if p.identifier.startswith('PV-L01-GALLERY-')]
    assert len(companions) == 4
    assert all(brief.massing_limit_shape.buffer(1e-7).covers(p.shape) for p in companions)
    foyer = next(p for p in captured if p.identifier == 'PV-L01-SP-FOYER')
    rooms = [p for p in captured if p.level == 0 and p.role == 'archetype']
    assert foyer.shape.area == pytest.approx(22.)
    assert all(foyer.shape.intersection(p.shape).area < 1e-7 for p in rooms)


def test_rear_commons_keeps_hall_galleries_and_clearance_in_one_search_batch(monkeypatch):
    from backend.app import layout_search
    from backend.app.legacy_program_layout import LayoutRejected
    captured = {}
    def capture(items,initial,proposals,**kwargs):
        captured.update(items=items,initial=list(initial),options=kwargs)
        captured['hall'] = next(batch for batch in proposals(items[0],tuple(initial)) if batch is not None)
        return layout_search.LayoutSearchResult(list(initial),False,0,False,list(items))
    monkeypatch.setattr(layout_search,'search_layout',capture)
    brief = _brief()
    with pytest.raises(LayoutRejected):
        _organize(_score(),brief,backbone_layout='rear_commons',core_inset_fraction=.15,
            lift_layout='core_front_inner',arrival_layout='complete_forecourt',
            foyer_layout='hall_front_shared')
    assert captured['options']['fair_roots']
    assert captured['items'][0][3] == 'hall'
    assert not any(p.role in ('archetype','sectional_clearance') for p in captured['initial'])
    hall = captured['hall']
    assert len([p for p in hall if p.role=='archetype']) == 2
    assert any(p.role=='sectional_clearance' for p in hall)
    assert len([p for p in hall if p.identifier.startswith('PV-L01-GALLERY')]) == 4
    assert sum(p.shape.area for p in hall if p.spaces) == pytest.approx(110.)
    assert all(brief.massing_limit_shape.buffer(1e-7).covers(p.shape) for p in hall)


def test_horizontal_core_layout_keeps_end_access_and_unchanged_core_area(monkeypatch):
    from backend.app import layout_search
    from backend.app.legacy_program_layout import LayoutRejected
    captured = []
    def capture(items,initial,proposals,**kwargs):
        captured.extend(initial)
        return layout_search.LayoutSearchResult(list(initial),False,0,False,list(items))
    monkeypatch.setattr(layout_search,'search_layout',capture)
    brief = _brief()
    with pytest.raises(LayoutRejected):
        _organize(_score(),brief,backbone_layout='rear_commons',stair_run_axis='x',
            core_inset_fraction=.15,lift_layout='core_front_inner',
            arrival_layout='complete_forecourt',foyer_layout='hall_front_shared')
    sources = {p.identifier:p for p in captured}
    for level in range(1,brief.occupied_storeys+1):
        spine = sources[f'PV-L{level:02d}-CIRC-2'].shape
        end_gallery = sources[f'PV-L{level:02d}-CIRC-7'].shape
        assert spine.bounds[2] == pytest.approx(end_gallery.bounds[2])
        assert spine.boundary.intersection(end_gallery.boundary).length == pytest.approx(1.8)
        for core_index,gallery_index in ((0,6),(1,7)):
            core = sources[f'PV-L{level:02d}-CIRC-{core_index}'].shape
            gallery = sources[f'PV-L{level:02d}-CIRC-{gallery_index}'].shape
            a,b,c,d = core.bounds
            assert (c-a,d-b) == pytest.approx((6.68,3.04))
            assert core.boundary.intersection(gallery.boundary).length == pytest.approx(3.04)
            assert core.intersection(gallery).area < 1e-7
            assert brief.massing_limit_shape.buffer(1e-7).covers(core.union(gallery))


def test_legacy_layout_keeps_brief_areas_unchanged():
    brief = _brief()
    model = _organize(_score(), brief)
    required = {space.id: space.area_m2 for space in brief.resolved_spaces()}

    program_volumes = [volume for volume in model.volumes if volume.space_ids]
    assert {volume.space_ids[0] for volume in program_volumes} == set(required)
    for volume in program_volumes:
        space_id = volume.space_ids[0]
        assert volume.target_area_m2 == pytest.approx(required[space_id])
        assert box(*model.rect_of(volume)).area == pytest.approx(required[space_id], abs=.002)


def test_legacy_layout_is_reproducible_for_same_score_brief_and_seed():
    score = _score()
    brief = _brief()
    first = _organize(score, brief)
    second = _organize(score, brief)

    assert first.model_dump(mode='json') == second.model_dump(mode='json')


def test_legacy_program_volume_round_trips_through_registration_lattice():
    score = _score()
    brief = _brief()
    model = _organize(score, brief)
    massing = model.to_program_massing()
    lattice = lattice_for(massing, datums_for(massing, score))

    assert len(lattice.occupied) == brief.occupied_storeys
    assert len(lattice.levels) == brief.occupied_storeys + 2
    for level in lattice.levels:
        plate = Polygon(
            [(point.x, point.y) for point in level.plate],
            holes=[[(point.x, point.y) for point in ring]
                   for ring in level.voids],
        )
        assert brief.massing_limit_shape.buffer(1e-6).covers(plate)


def test_sectional_reservations_follow_theatre_height_before_upper_rooms_are_placed():
    from backend.app.archetypes import theatre_clearance_height

    brief = _brief()
    model = _organize(_score(), brief)
    house = next(v for v in model.volumes if 'SP-AUDITORIUM' in v.space_ids)
    x0, _, x1, _ = model.rect_of(house)
    height = theatre_clearance_height(x1-x0)
    ground = model.levels[0].z_base
    expected = {level.id for level in model.levels[1:] if level.z_base-ground < height}
    clearances = [v for v in model.volumes if v.role == 'sectional_clearance']
    assert {v.level_id for v in clearances} == expected
    assert len(expected) >= 2  # The original single-upper-storey reservation missed this.
    for clearance in clearances:
        air = box(*model.rect_of(clearance))
        for room in model.volumes:
            if room.level_id == clearance.level_id and room.space_ids:
                assert air.intersection(box(*model.rect_of(room))).area < 1e-7

    # Tall-room airspace stays in the envelope, without being counted as built floor.
    envelope_area = sum(u.gross_area_m2 for u in model.level_unions)
    floor_area = sum(unary_union([
        box(*model.rect_of(v)) for v in model.volumes
        if v.level_id == level.id and v.role != 'sectional_clearance']).area
        for level in model.levels)
    assert floor_area <= brief.target_gross_area_m2 < envelope_area
    # The shared massing budget must interpret this distinction the same way.
    massing = model.to_program_massing()
    lattice_for(massing, datums_for(massing, _score()))


def test_small_authored_floor_preserves_owners_instead_of_needing_120_square_metres():
    from backend.app.archetypes import _gutted, _section_removals_are_viable
    from backend.app.plan_regions import usable_region

    model = _organize(_score(), _brief())
    massing = model.to_program_massing()
    grid = lattice_for(massing, datums_for(massing, _score()))
    cuts = {}
    for region in grid.program_volume_regions:
        if region.role == 'sectional_clearance':
            index = next(level.index for level in grid.occupied if level.id == region.level_id)
            cuts.setdefault(index, []).append(region.resolve_bounds(grid))
    assert _gutted(grid, cuts) is None
    # Authored side galleries preserve the independent connected-floor check.
    assert _section_removals_are_viable(grid, cuts)
    # Taking an authored room is invalid even where a coarse area heuristic fits.
    room = next(region for region in grid.program_volume_regions
                if region.level_id == 'L02' and region.role == 'program')
    cuts[2].append(room.resolve_bounds(grid))
    assert _gutted(grid, cuts)[0] == 'L02'


def test_geometry_event_candidates_preserve_area_and_never_take_occupied_floor():
    from backend.app.legacy_program_layout import _placements

    parcel = box(0, 0, 10, 8)
    obstacle = box(4, 0, 6, 6)
    candidates = list(_placements(parcel, [obstacle], 3, 2, (5, 4), accept=lambda _: True))
    assert len(candidates) > 1
    assert [r.bounds for r in candidates] == [r.bounds for r in
        _placements(parcel, [obstacle], 3, 2, (5, 4), accept=lambda _: True)]
    for candidate in candidates:
        assert candidate.area == pytest.approx(6)
        assert parcel.covers(candidate)
        assert candidate.intersection(obstacle).area == 0


def test_insufficient_circulation_budget_rejects_before_room_search():
    from backend.app.legacy_program_layout import LayoutRejected

    brief = _brief().model_copy(update={'circulation_budget_m2': 300.0})
    with pytest.raises(LayoutRejected, match='Circulation union needs'):
        _organize(_score(), brief)


def test_area_budget_measures_shared_floor_once_and_excludes_sectional_airspace():
    from backend.app.legacy_program_layout import Placed, _layout_areas
    records = [
        Placed(0,'foyer','circulation','program',['foyer'],box(0,0,4,4),16,'fixture'),
        Placed(0,'route','circulation','connector',[],box(0,0,4,2),0,'fixture'),
        Placed(0,'room','public','program',['room'],box(4,0,8,4),16,'fixture'),
        Placed(1,'air','public','sectional_clearance',[],box(4,0,8,4),0,'fixture'),
        Placed(1,'upper-route','circulation','connector',[],box(0,0,4,2),0,'fixture'),
    ]
    assert _layout_areas(records) == pytest.approx((40.,24.))


def test_topology_uses_registered_precision_without_filling_a_real_gap():
    from backend.app.legacy_program_layout import Placed, _layout_topology_findings
    street = Placed(0,'route','circulation','connector',[],box(0,0,8,2),0,'fixture')
    room = Placed(0,'room','public','program',['room'],box(0,2+1e-15,4,6),16,'fixture')
    assert _layout_topology_findings([street,room],1,set()) == []
    room.shape = box(0,2.001,4,6.001)
    assert _layout_topology_findings([street,room],1,set()) == [
        'L01 contains disconnected volumes; circulation needs another layout']


def test_joint_levels_offer_sectional_anchors_before_filling_one_floor_twice():
    from backend.app.legacy_program_layout import Placed, _level_proposal_tiers
    state = [Placed(1,'room','public','program',['room'],box(0,0,4,4),16,'fixture'),
             Placed(2,'air','public','sectional_clearance',[],box(0,0,4,4),0,'fixture')]
    assert _level_proposal_tiers([1,3,2],state) == [[2],[3],[1]]
    assert sorted(k for tier in _level_proposal_tiers([1,3,2],state) for k in tier) == [1,2,3]


@pytest.mark.parametrize('axis', ['x', 'y'])
def test_authored_group_shares_a_dimension_without_shrinking_or_merging_rooms(axis):
    from types import SimpleNamespace
    from backend.app.legacy_program_layout import _split_group

    spaces = [SimpleNamespace(area_m2=12, min_dimension_m=2.5),
              SimpleNamespace(area_m2=16, min_dimension_m=3)]
    rect = box(0,0,7,4) if axis == 'x' else box(0,0,4,7)
    parts = _split_group(rect, spaces, axis)
    assert [part.area for part in parts] == pytest.approx([12,16])
    assert parts[0].intersection(parts[1]).area == 0
    assert parts[0].boundary.intersection(parts[1].boundary).length == pytest.approx(4)
    assert unary_union(parts).equals(rect)
    # Equal total area cannot excuse a room narrower than its required minimum.
    thin = box(0,0,14,2) if axis == 'x' else box(0,0,2,14)
    assert _split_group(thin, spaces, axis) is None
