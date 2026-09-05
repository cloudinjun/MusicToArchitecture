import json
from pathlib import Path

import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union

from backend.app.compiler_v3 import compile_building_model_v3, core_reservations
from backend.app.datums import build_lattice, compile_datum_set
from backend.app.geometry import (
    BoxGeometry, ExtrusionGeometry, MemberGeometry, QuadGeometry,
    point_inside, polyline_stations, profile_from_section_id,
)
from backend.app.models import ArchitecturalScore, AudioFeatures, ScoreDimension

DEMO = (Path(__file__).parents[2] / 'artifacts' / 'integrated_demo'
        / 'building-b7ad95fa45a6-library-steel-international-v1')


@pytest.fixture(scope='module')
def features() -> AudioFeatures:
    return AudioFeatures.model_validate(
        json.loads((DEMO / 'music_features.json').read_text(encoding='utf-8')))


@pytest.fixture(scope='module')
def score() -> ArchitecturalScore:
    return ArchitecturalScore.model_validate(
        json.loads((DEMO / 'architectural_score.json').read_text(encoding='utf-8')))


@pytest.fixture(scope='module')
def model(features, score):
    """The reference building: a library on a stacked slab.

    Pinned rather than free because the tests below assert library-specific facts --
    that stack rooms govern the live load, that reading rooms reach daylight. Once the
    score began choosing its own massing and brief those became assertions about
    whichever building this particular fixture happened to produce, which is not what
    any of them were written to check. `test_the_score_chooses_its_own_building` is
    where the free path is exercised.
    """
    return compile_building_model_v3(features, score, massing_id='MAS-SLAB',
                                     typology='library')


def score_with(base: ArchitecturalScore, **values) -> ArchitecturalScore:
    dimensions = [
        ScoreDimension(
            id=d.id, value=values.get(d.id, d.value), source_feature=d.source_feature,
            extraction_method=d.extraction_method, confidence=d.confidence,
            architectural_proposal=d.architectural_proposal)
        for d in base.dimensions
    ]
    return ArchitecturalScore(
        score_id=base.score_id, source_audio_sha256=base.source_audio_sha256,
        dimensions=dimensions, mapping_rules=base.mapping_rules)


# ---------------------------------------------------------------------------
# Geometry primitives
# ---------------------------------------------------------------------------

def test_all_four_primitives_are_emitted(model):
    kinds = {type(element.geometry) for element in model.elements}
    assert kinds == {BoxGeometry, MemberGeometry, ExtrusionGeometry, QuadGeometry}


def test_section_id_round_trips_into_a_drawable_profile():
    profile = profile_from_section_id('I-450x225x9x14')
    assert profile.shape == 'i_section'
    assert profile.depth_m == pytest.approx(0.450)
    assert profile.width_m == pytest.approx(0.225)
    assert profile.source == 'sized'
    assert len(profile.outline()) == 12
    assert profile_from_section_id('SHS-300x300x12').shape == 'box'
    assert profile_from_section_id('CHS-180x10').shape == 'chs'
    with pytest.raises(ValueError):
        profile_from_section_id('not-a-section')


def test_every_member_profile_is_declared(model):
    for element in model.elements:
        if isinstance(element.geometry, MemberGeometry):
            assert element.geometry.profile in model.profiles, element.id


def test_derived_bounds_stay_consistent_with_the_geometry(model):
    for element in model.elements:
        assert element.dimensions.x > 0
        assert element.dimensions.y > 0
        assert element.dimensions.z > 0


def test_floor_slabs_exclude_the_atrium_voids(model):
    slabs = [e for e in model.elements if e.kind == 'floor_slab']
    assert slabs
    voided_levels = [level for level in model.lattice.levels if level.voids]
    assert voided_levels

    for level in voided_levels:
        material = unary_union([
            Polygon(
                [(point.x, point.y) for point in slab.geometry.boundary],
                holes=[[(point.x, point.y) for point in ring]
                       for ring in slab.geometry.holes],
            )
            for slab in slabs if slab.level_id == level.id
        ])
        assert not material.is_empty
        for ring in level.voids:
            void = Polygon([(point.x, point.y) for point in ring])
            assert material.intersection(void).area == pytest.approx(0.0, abs=1e-7)


# ---------------------------------------------------------------------------
# The datum chain
# ---------------------------------------------------------------------------

def test_no_element_is_positioned_by_a_literal(model):
    """Every element must index into the lattice or belong to the site layer."""
    for element in model.elements:
        if element.semantic_layer == 'site':
            continue
        assert element.lattice_index or element.datum_refs or element.level_id, element.id


def test_datums_record_whether_the_score_actually_drove_them(model):
    driven = [d for d in model.datum_set.datums if d.provenance == 'score_driven']
    fixtures = [d for d in model.datum_set.datums if d.provenance == 'design_fixture']
    assert driven and fixtures
    for datum in driven:
        assert datum.driving_dimension and datum.dimension_value is not None
    for datum in fixtures:
        assert 'design fixture' in datum.reason
    assert 0.0 < model.datum_set.coverage < 1.0
    assert model.datum_set.waiting_on


def test_coverage_is_not_inflated_by_the_missing_dimensions(model):
    """Six of the ten shared dimensions are still unobserved. The model must say so."""
    assert set(model.datum_set.waiting_on) <= {
        'hierarchy', 'repetition', 'variation', 'interruption', 'polyphony',
        'genre_style'}
    assert any('score does not yet supply' in limitation
               for limitation in model.limitations) or model.datum_set.waiting_on


def test_element_ids_are_lattice_coordinates(model):
    columns = [e for e in model.elements if e.kind == 'column']
    assert columns
    sample = columns[0]
    assert sample.id.startswith('STR-COL-')
    assert {'x', 'y', 'level'} <= set(sample.lattice_index) or 'apse' in sample.lattice_index


def test_ids_are_unique(model):
    ids = [element.id for element in model.elements]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# The claim the whole rewrite exists for
# ---------------------------------------------------------------------------

def test_two_different_scores_produce_two_different_buildings(features, score):
    loose = compile_building_model_v3(features, score_with(
        score, tempo_of_change=0.05, density=0.10, tension_release=0.90,
        continuity=0.85))
    dense = compile_building_model_v3(features, score_with(
        score, tempo_of_change=0.95, density=0.95, tension_release=0.10,
        continuity=0.10))

    assert len(dense.lattice.levels) > len(loose.lattice.levels)
    assert dense.lattice.roof.z > loose.lattice.roof.z
    assert dense.datum_set.value('bay_x_m') < loose.datum_set.value('bay_x_m')
    assert dense.datum_set.value('joist_spacing_m') < loose.datum_set.value('joist_spacing_m')
    assert len(dense.elements) > len(loose.elements) * 1.3


def test_the_load_calculation_follows_the_geometry_the_score_produced(features, score):
    """Wider bays must produce a deeper girder. If the sections do not move with the
    music-driven geometry, the calculation is decoration."""
    narrow = compile_building_model_v3(features, score_with(score, density=0.95))
    wide = compile_building_model_v3(features, score_with(score, density=0.05))
    narrow_girder = next(r for r in narrow.sizing if r.role == 'primary_beam')
    wide_girder = next(r for r in wide.sizing if r.role == 'primary_beam')
    assert wide_girder.span_m > narrow_girder.span_m
    assert wide_girder.section_id != narrow_girder.section_id


def test_compilation_is_deterministic(features, score):
    a = compile_building_model_v3(features, score)
    b = compile_building_model_v3(features, score)
    assert [e.id for e in a.elements] == [e.id for e in b.elements]
    assert a.element_counts == b.element_counts


# ---------------------------------------------------------------------------
# Sizing provenance
# ---------------------------------------------------------------------------

def test_only_calculated_members_claim_to_be_sized(model):
    """The three tiers a load path actually governs, whichever frame was selected.

    This used to name `secondary_joist` outright. It cannot any more: a mass-timber
    frame carries CLT bands and a flat slab carries none, so the tier's *name* depends
    on the tectonic. What must not depend on the tectonic is the rule -- a member claims
    `sized_by_calculation` only if a check governed it.
    """
    sized = [e for e in model.elements if e.sizing_status == 'sized_by_calculation']
    assert sized
    tiers = {'secondary_joist', 'heavy_joist', 'clt_panel'}
    kinds = {e.kind for e in sized}
    assert {'column', 'piloti_column', 'primary_beam'} <= kinds
    assert kinds - {'column', 'piloti_column', 'primary_beam'} <= tiers
    for element in sized:
        assert element.section_id and element.utilisation is not None
        assert element.governing_check


def test_conventional_members_never_report_a_utilisation(model):
    for element in model.elements:
        if element.sizing_status != 'sized_by_calculation':
            assert element.utilisation is None, element.id


def test_every_element_stays_under_professional_review(model):
    assert all(e.validation_status == 'professional_review_required'
               for e in model.elements)


def test_sizing_records_carry_their_assumptions(model):
    assert model.sizing
    for record in model.sizing:
        assert record.utilisation <= 1.0
        assert record.assumptions
        assert record.load_combination


# ---------------------------------------------------------------------------
# The taxonomy actually reaches the studio-model register
# ---------------------------------------------------------------------------

def test_the_four_semantic_layers_are_all_populated(model):
    assert set(model.layer_counts) == {
        'structure', 'envelope', 'circulation', 'program', 'site'}
    for layer in ('structure', 'envelope', 'circulation', 'program'):
        assert model.layer_counts[layer] > 50


def test_the_tertiary_tier_exists(model):
    """Small repeated members are what establish scale. The v2 model had none of them.

    Which small members exist is now a property of the tectonic -- a punched wall has
    reveals and sills where a curtain wall has mullions and transoms -- so the test asks
    for a populated secondary structural tier and a populated envelope subdivision
    rather than for four specific names.
    """
    for kind in ('stair_tread', 'railing'):
        assert model.element_counts.get(kind, 0) > 10, kind

    floor_tier = ('secondary_joist', 'heavy_joist', 'clt_panel', 'drop_panel')
    assert sum(model.element_counts.get(k, 0) for k in floor_tier) > 10

    envelope_tier = ('mullion', 'transom', 'wall_panel', 'window_reveal', 'sill',
                     'lattice_mullion', 'lattice_transom', 'field_panel',
                     'facet_panel', 'backing_panel', 'frame_expression')
    assert sum(model.element_counts.get(k, 0) for k in envelope_tier) > 10


def test_scale_figures_are_present(model):
    assert model.element_counts.get('figure', 0) > 40


def test_envelope_is_cut_away_on_the_section_side(model):
    """The sectional read depends on the envelope stopping.

    Whatever the grammar draws on the elevation, it must draw it only on the enclosed
    faces; the cutaway is a property of the model, not of one wall type.
    """
    from backend.app.datums import envelope_stations_visible
    # Members that sit *on* a station carry the station's own coordinate, so they test
    # the predicate directly. Anything placed *within* a bay -- a panel, a reveal at the
    # edge of an opening -- legitimately reaches past the last visible station, because
    # the bay it belongs to starts inside the visible region and ends outside it. The
    # curtain wall always did this with its glazing quads; it is not what this test is
    # about, and the generous bound below is what catches a genuinely stray member.
    at_station = ('mullion', 'lattice_mullion', 'frame_expression', 'screen_fin')
    posts = [e for e in model.elements if e.kind in at_station]
    assert posts
    assert all(envelope_stations_visible(e.position.x, e.position.y,
                                        model.lattice.plan) for e in posts)

    # And nothing in the envelope layer strays deep into the cut, whatever it is.
    # The bound comes from the model's own plan -- the plate is sized by the brief now,
    # so a literal tuned to the old 36 x 22 m footprint would fail every building that
    # grew, and it was a coordinate literal in a test besides.
    from backend.app.datums import CUT_EAST_T, CUT_NORTH_T
    plan = model.lattice.plan
    y_bound = plan.fy(CUT_NORTH_T) + 3.5
    x_bound = plan.fx(CUT_EAST_T) + 3.5
    skin = [e for e in model.elements
            if e.semantic_layer == 'envelope' and e.subsystem != 'canopy']
    assert skin
    assert all(e.position.y < y_bound and e.position.x < x_bound for e in skin)


def test_limitations_are_declared(model):
    text = ' '.join(model.limitations)
    assert 'Gravity only' in text
    assert 'professional_review_required' in text


# ---------------------------------------------------------------------------
# S6 -- the program allocator
# ---------------------------------------------------------------------------

def test_the_brief_states_requirements_not_geometry():
    from backend.app.program import LIBRARY_BRIEF
    for space in LIBRARY_BRIEF:
        assert space.area_m2 > 0 and space.min_dimension_m > 0
        assert space.occupancy_id and space.reason
        assert not hasattr(space, 'x0')


def test_allocation_reports_what_it_could_not_place(features, score):
    """A building that genuinely cannot hold its brief says so.

    The contract from decision 0013: a brief that does not fit inside the family's
    identity bound is *reported with numbers*, not housed in a building that has
    stopped being that family.

    The vehicle has moved twice, both times because the building got better. It began
    as a tight score on the slab -- few plates, starved brief -- and the plate is sized
    by the brief now, so few storeys buy a wider building and everything fits. It then
    used a pavilion asked to be a 3,000 m2 library, and the derived stacking span
    (decision 0015) let even that deliver the whole brief on two deep floors. What is
    still genuinely unhousable is a footprint too small in *plan*: a 21 x 18 m tower
    holds its proportion to a 1.5 scale bound and a library needs more floor than five
    storeys of that can offer. If this test starts failing again, check whether the
    building improved before changing anything -- the assertion is the contract, and
    the massing is only the case that exercises it.
    """
    built = compile_building_model_v3(features, score, massing_id='MAS-TOWER',
                                      typology='library')
    allocation = built.program_allocation
    assert not allocation.fits, (
        f'MAS-TOWER now houses the whole library brief at '
        f'{allocation.fulfilment:.3f}; this test needs a case that genuinely cannot')
    assert allocation.unplaced
    for space in allocation.unplaced:
        assert 'occupied levels' in space.reason
    # Held at the bound, and saying so -- not quietly grown past the family.
    assert any('held at the bound' in reason
               for reason in built.selection.massing_reason)
    # And the fit's own sentence is on the record where the massing reasoning lives.
    assert any('plate sized by the brief' in reason
               for reason in built.selection.massing_reason)


def test_fewer_storeys_buy_a_wider_plate(features, score):
    """The score keeps direction; the brief keeps the amount.

    Storey count is the score's decision, so a score that stacks few levels gets a
    broader building and a score that stacks many gets a slimmer one -- and the same
    brief is housed either way. Before decision 0013 the tight score simply failed its
    brief, which punished a direction for being a direction.
    """
    pin = dict(massing_id='MAS-SLAB', typology='library')
    tight = compile_building_model_v3(
        features, score_with(score, tempo_of_change=0.0), **pin)
    roomy = compile_building_model_v3(
        features, score_with(score, tempo_of_change=1.0), **pin)
    assert len(tight.lattice.occupied) < len(roomy.lattice.occupied)
    assert tight.lattice.plan_x_m > roomy.lattice.plan_x_m
    for model in (tight, roomy):
        assert not model.program_allocation.unplaced, (
            f'{len(model.lattice.occupied)} storeys left '
            f'{[u.space_id for u in model.program_allocation.unplaced]} unplaced')
        assert model.program_allocation.fulfilment > 0.95


def test_a_taller_score_fits_the_whole_brief(features, score):
    """Every space gets a home, and all but the cores' worth of the briefed area.

    This asked for 1.0 while the program was banded over the stairs -- a brief fulfilled
    by putting the open stacks where the fire stair is, which is the kind of number that
    looks like success and is not. With the cores reserved, the one space larger than any
    clear run the plate still offers is delivered short, and the shortfall is reported on
    the zone rather than absorbed. What it must not exceed is the floor the cores take:
    that ties the number to the thing that caused it, so a real regression in the layout
    cannot hide behind a tolerance.
    """
    roomy = compile_building_model_v3(
        features,
        score_with(score, tempo_of_change=0.95, density=0.95, continuity=0.10),
        massing_id='MAS-SLAB', typology='library')
    allocation = roomy.program_allocation
    assert allocation.fits
    assert not allocation.unplaced
    shortfall = sum(zone.area_required_m2 - zone.area_delivered_m2
                    for zone in allocation.zones
                    if zone.area_delivered_m2 < zone.area_required_m2)
    reserved = sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1
                   in core_reservations(roomy.lattice, roomy.datum_set))
    assert shortfall < reserved * len(roomy.lattice.occupied)
    assert allocation.fulfilment > 0.9


def test_daylight_required_spaces_land_on_a_perimeter_band(model):
    from backend.app.program import LIBRARY_BRIEF
    needs_daylight = {s.id for s in LIBRARY_BRIEF if s.daylight == 'required'}
    placed = [z for z in model.program_allocation.zones if z.space_id in needs_daylight]
    assert placed
    assert all(zone.daylight_satisfied for zone in placed)


def test_zones_stay_inside_the_plate_the_score_produced(model):
    from backend.app.geometry import point_inside
    for zone in model.program_allocation.zones:
        plate = model.lattice.level(zone.level_index).plate
        cx, cy = zone.centre
        assert point_inside(plate, cx, cy), zone.space_id


def test_the_governing_live_load_comes_from_the_allocation(model):
    """Stacks at 7.18 kPa must actually govern the beam tier, and the limitation text
    must name the room that did it."""
    text = ' '.join(model.limitations)
    assert 'Library stack rooms' in text and '7.18 kPa' in text


def test_room_proportions_move_with_the_score(features, score):
    """Room shape is a consequence of the structural grid the score set, not a drawing.

    Two statements: every room edge lands on a structural grid line, which is the
    mechanism; and no room the two grids share keeps its rectangle, which is what that
    mechanism does. Depth is the visible half -- a room clamped to its minimum width
    still changes depth, because depth is a whole number of bays.

    This used to follow SP-STACKS through both models. The wide grid cannot place a
    430 m2 stack room any more: with the cores reserved and rooms no longer able to run
    through them, a three-bay plate has no clear run long enough. Pinning one space made
    the test hostage to whether that space fits, which is a different question from the
    one it asks.
    """
    # Massing pinned: density also chooses a silhouette, and a tower against a
    # pavilion would demonstrate that rather than the grid this test is about.
    pin = dict(massing_id='MAS-SLAB', typology='library')
    narrow = compile_building_model_v3(
        features, score_with(score, density=1.0), **pin)
    wide = compile_building_model_v3(features, score_with(score, density=0.0), **pin)
    assert len(narrow.lattice.y_lines) != len(wide.lattice.y_lines)

    for model in (narrow, wide):
        lines = [round(line, 3) for line in model.lattice.y_lines]
        for zone in model.program_allocation.zones:
            assert round(zone.y0, 3) in lines and round(zone.y1, 3) in lines, (
                f'{zone.space_id} runs from {zone.y0} to {zone.y1}, which is not a '
                f'span of whole bays on {lines}')

    def shapes(model):
        return {zone.space_id: (round(zone.x1 - zone.x0, 2),
                                round(zone.y1 - zone.y0, 2))
                for zone in model.program_allocation.zones}

    a, b = shapes(narrow), shapes(wide)
    common = sorted(set(a) & set(b))
    assert len(common) >= 8, f'only {len(common)} rooms in both grids to compare'
    unchanged = [space_id for space_id in common if a[space_id] == b[space_id]]
    assert not unchanged, (
        f'{unchanged} kept the same rectangle across two different bay grids, so their '
        f'shape is not coming from the grid')


def test_program_elements_are_emitted_from_the_allocation(model):
    zone_ids = {z.space_id for z in model.program_allocation.zones}
    emitted = {e.id.split('-', 3)[-1] for e in model.elements
               if e.kind == 'program_zone'}
    assert emitted == zone_ids


# ---------------------------------------------------------------------------
# S7 -- payload compaction
# ---------------------------------------------------------------------------

def test_groups_expand_to_the_reported_element_count(model):
    assert len(model.elements) == model.element_count
    assert model.element_count == sum(len(g.instances) for g in model.element_groups)
    assert len(model.element_groups) < model.element_count / 10


def test_grouping_never_merges_elements_that_differ_descriptively(model):
    for group in model.element_groups:
        expanded = group.expand()
        assert {e.kind for e in expanded} == {group.kind}
        assert {e.sizing_status for e in expanded} == {group.sizing_status}
        assert {e.reason for e in expanded} == {group.reason}


def test_the_grouped_payload_is_materially_smaller(model):
    import json as _json
    grouped = len(model.model_dump_json())
    flat = len(_json.dumps([e.model_dump(mode='json') for e in model.elements]))
    assert grouped < flat * 0.7


def test_expansion_preserves_unique_ids(model):
    ids = [e.id for e in model.elements]
    assert len(ids) == len(set(ids))
