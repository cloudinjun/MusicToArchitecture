"""Program Volumes make the form; every downstream plate is their exact union."""
from __future__ import annotations

from collections import Counter
from types import SimpleNamespace

import pytest
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from backend.app.briefs import brief_for
from backend.app.compiler_v3 import _Builder, _clear_of_plate_edge, _emit_roof
from backend.app.datums import compile_datum_set
from backend.app.envelope import _register_entrance, registered_bays
from backend.app.geometry import ExtrusionGeometry, MemberGeometry, inset, v2, v3
from backend.app.materials import MATERIALS
from backend.app.models import ArchitecturalScore, ScoreDimension
from backend.app.program import allocate_program
from backend.app.program_massing import datums_for, lattice_for
from backend.app.program_volumes import (
    STACKED_PHASE_CELLS,
    _stacked_band_phase,
    choose_program_volume_grammar,
    organize_program_volumes,
)
from backend.app.roof import (
    ROOF_ASSEMBLY_RULE,
    ROOF_CONTROL_RULE,
    ROOF_PROFESSIONAL_REVIEW_RULE,
    roof_assembly_layers,
    roof_control_for,
    roof_geometry_max_z,
    validate_roof_emission,
)

GRAMMARS = (
    'PVG-STACKED-BANDS',
    'PVG-TERRACED-WEAVE',
    'PVG-SPLIT-BRIDGE',
)
DIMENSIONS = (
    'genre_style', 'hierarchy', 'repetition', 'variation', 'density',
    'continuity', 'interruption', 'polyphony', 'tension_release',
    'tempo_of_change',
)


def _score(**values) -> ArchitecturalScore:
    return ArchitecturalScore(
        score_id='score-program-volume-test', source_audio_sha256='1' * 64,
        dimensions=[ScoreDimension(
            id=dimension, value=values.get(dimension, 0.4),
            source_feature=f'test_{dimension}', extraction_method='manual',
            confidence=1.0, architectural_proposal='Program Volume reachability test.')
                    for dimension in DIMENSIONS],
        mapping_rules=[])


def _shape(boundary, voids=()):
    return Polygon(boundary, holes=voids)


def _volume_shape(model, volume):
    return box(*model.rect_of(volume))


def test_every_program_volume_grammar_is_reachable():
    cases = (
        (_score(), 'PVG-STACKED-BANDS'),
        (_score(hierarchy=0.8), 'PVG-TERRACED-WEAVE'),
        (_score(interruption=0.8, hierarchy=0.8), 'PVG-SPLIT-BRIDGE'),
    )
    assert {choose_program_volume_grammar(score)[0] for score, _expected in cases} \
        == set(GRAMMARS)
    for score, expected in cases:
        assert choose_program_volume_grammar(score)[0] == expected


def test_stacked_band_repetition_question_reaches_both_lattice_phases():
    alternating = _score(repetition=0.0)
    registered = _score(repetition=1.0)

    assert [_stacked_band_phase(alternating, level) for level in range(5)] == [
        0, STACKED_PHASE_CELLS, 0, STACKED_PHASE_CELLS, 0]
    assert [_stacked_band_phase(registered, level) for level in range(5)] == [
        0, 0, 0, 0, 0]

    alternating_model = organize_program_volumes(
        alternating, 'museum', grammar_id='PVG-STACKED-BANDS')
    registered_model = organize_program_volumes(
        registered, 'museum', grammar_id='PVG-STACKED-BANDS')
    assert alternating_model.topology_signature != registered_model.topology_signature
    assert any('alternating AB phase' in reason
               for reason in alternating_model.grammar_reason)
    assert any('same lattice phase' in reason
               for reason in registered_model.grammar_reason)


def test_same_score_and_brief_produce_three_different_volume_topologies():
    score = _score(hierarchy=0.7, variation=0.72, interruption=0.2)
    models = [organize_program_volumes(score, 'museum', grammar_id=grammar)
              for grammar in GRAMMARS]
    assert len({model.topology_signature for model in models}) == len(GRAMMARS)

    # Compare geometry, not labels: centroid travel and exterior complexity must
    # expose more than one silhouette for the same brief.
    signatures = []
    for model in models:
        shapes = [_shape(union.boundary, union.voids)
                  for union in model.level_unions]
        signatures.append((
            tuple(round(shape.area, 1) for shape in shapes),
            tuple(round(shape.length, 1) for shape in shapes),
            tuple((round(shape.centroid.x, 1), round(shape.centroid.y, 1))
                  for shape in shapes),
        ))
    assert len(set(signatures)) == len(GRAMMARS)


@pytest.mark.parametrize('grammar', GRAMMARS)
def test_every_brief_space_has_one_full_height_volume_and_no_phantom_level(grammar):
    score = _score(hierarchy=0.7, variation=0.75)
    model = organize_program_volumes(score, 'museum', grammar_id=grammar)
    expected = {space.id for space in brief_for('museum', storeys=len(model.levels))}
    actual = Counter(space_id for volume in model.volumes
                     if volume.role in ('program', 'archetype')
                     for space_id in volume.space_ids)
    assert set(actual) == expected
    assert all(count == 1 for count in actual.values())

    datums = compile_datum_set(score)
    for level in model.levels:
        program = [volume for volume in model.volumes
                   if volume.level_id == level.id
                   and volume.role in ('program', 'archetype')]
        assert program, f'{level.id} carries form but no program'
        assert level.z_top - level.z_base == pytest.approx(
            datums.value('floor_to_floor_m'))

        # Room volumes do not collide. Connector/spine boxes may meet their faces,
        # but do not consume positive room area.
        for index, volume in enumerate(program):
            for other in program[index + 1:]:
                assert _volume_shape(model, volume).intersection(
                    _volume_shape(model, other)).area <= 1e-6


@pytest.mark.parametrize('grammar', GRAMMARS)
def test_library_sectional_clearance_keeps_the_envelope_without_claiming_a_room(
        grammar):
    score = _score(hierarchy=0.7, variation=0.75)
    model = organize_program_volumes(
        score, 'library', grammar_id=grammar)

    (adult,) = [volume for volume in model.volumes
                if 'SP-ADULT' in volume.space_ids]
    (clearance,) = [volume for volume in model.volumes
                    if volume.role == 'sectional_clearance']
    highest = model.levels[-1]
    assert clearance.level_id == highest.id
    assert adult.level_index + 1 == clearance.level_index
    assert clearance.grid_rect == adult.grid_rect
    assert clearance.space_ids == []
    assert clearance.target_area_m2 == 0.0

    clearance_shape = _volume_shape(model, clearance)
    top_program = [volume for volume in model.volumes
                   if volume.level_id == highest.id
                   and volume.role in ('program', 'archetype')]
    assert top_program
    assert all(clearance_shape.intersection(_volume_shape(model, volume)).area <= 1e-6
               for volume in top_program)

    top_union = next(union for union in model.level_unions
                     if union.level_id == highest.id)
    assert _shape(top_union.boundary, top_union.voids).covers(clearance_shape)
    region = next(region for region in model.program_volume_regions
                  if region.id == clearance.id)
    assert region.role == 'sectional_clearance'
    assert region.space_ids == []


@pytest.mark.parametrize('grammar', GRAMMARS)
def test_theater_house_stage_pair_controls_the_upper_sectional_clearance(grammar):
    model = organize_program_volumes(
        _score(hierarchy=0.72, variation=0.78, interruption=0.22),
        'theater', grammar_id=grammar)
    ground = [volume for volume in model.volumes if volume.level_id == 'L01'
              and {'SP-AUDITORIUM', 'SP-STAGE'} & set(volume.space_ids)]
    owners = {volume.space_ids[0]: volume for volume in ground}
    assert set(owners) == {'SP-AUDITORIUM', 'SP-STAGE'}
    auditorium = owners['SP-AUDITORIUM']
    stage = owners['SP-STAGE']
    assert auditorium.grid_rect[1] == stage.grid_rect[1]
    assert auditorium.grid_rect[3] == stage.grid_rect[3]
    assert auditorium.grid_rect[2] == stage.grid_rect[0]

    clearances = [volume for volume in model.volumes
                  if volume.level_id == 'L02'
                  and volume.role == 'sectional_clearance']
    assert {clearance.grid_rect for clearance in clearances} == {
        auditorium.grid_rect, stage.grid_rect}
    upper_program = [volume for volume in model.volumes
                     if volume.level_id == 'L02'
                     and volume.role in ('program', 'archetype')]
    for clearance in clearances:
        clearance_shape = _volume_shape(model, clearance)
        assert all(clearance_shape.intersection(
            _volume_shape(model, volume)).area <= 1e-6
            for volume in upper_program)

    for union in model.level_unions:
        assert _shape(union.boundary, union.voids).geom_type == 'Polygon'
    upper_roles = {volume.role for volume in model.volumes if volume.level_id == 'L02'}
    assert {'circulation_spine', 'connector'} <= upper_roles


@pytest.mark.parametrize('grammar', GRAMMARS)
def test_museum_gallery_pair_is_adjacent_and_keeps_independent_areas(grammar):
    model = organize_program_volumes(
        _score(hierarchy=0.72, variation=0.78, interruption=0.22),
        'museum', grammar_id=grammar)
    galleries = {
        volume.space_ids[0]: volume for volume in model.volumes
        if volume.level_id == 'L05' and volume.role == 'archetype'
        and volume.space_ids and volume.space_ids[0] in {
            'SP-GALLERY-A', 'SP-GALLERY-B'}
    }
    assert set(galleries) == {'SP-GALLERY-A', 'SP-GALLERY-B'}
    gallery_a = galleries['SP-GALLERY-A']
    gallery_b = galleries['SP-GALLERY-B']
    assert gallery_a.level_id == gallery_b.level_id
    assert set(gallery_a.space_ids).isdisjoint(gallery_b.space_ids)
    assert gallery_a.gross_area_m2 > 0.0
    assert gallery_b.gross_area_m2 > 0.0
    assert (gallery_a.grid_rect[2] == gallery_b.grid_rect[0]
            or gallery_a.grid_rect[0] == gallery_b.grid_rect[2]
            or gallery_a.grid_rect[3] == gallery_b.grid_rect[1]
            or gallery_a.grid_rect[1] == gallery_b.grid_rect[3])
    assert not any(volume.role == 'sectional_clearance'
                   for volume in model.volumes)


def test_owner_first_allocation_is_inside_authored_regions_and_deterministic():
    score = _score(hierarchy=0.7, variation=0.75)
    model = organize_program_volumes(
        score, 'library', grammar_id='PVG-STACKED-BANDS')
    massing = model.to_program_massing()
    datums = datums_for(massing, score)
    lattice = lattice_for(massing, datums)
    selected = {'SP-PERIODICALS', 'SP-SPECIAL'}
    brief = tuple(space for space in brief_for(
        'library', storeys=len(model.levels)) if space.id in selected)

    forward = allocate_program(lattice, datums, brief)
    reversed_input = allocate_program(lattice, datums, tuple(reversed(brief)))
    assert forward == reversed_input
    assert forward.fits
    assert {zone.space_id for zone in forward.zones} == selected

    owners = {
        space_id: (region.level_id, box(*region.resolve_bounds(lattice)))
        for region in lattice.program_volume_regions
        if region.role in ('program', 'archetype')
        for space_id in region.space_ids
    }
    for zone in forward.zones:
        owner_level, owner_shape = owners[zone.space_id]
        footprint = box(zone.x0, zone.y0, zone.x1, zone.y1)
        assert zone.level_id == owner_level
        assert owner_shape.buffer(1e-6).covers(footprint)
        assert zone.area_satisfied


@pytest.mark.parametrize('grammar', GRAMMARS)
def test_level_plate_is_the_exact_program_volume_union(grammar):
    model = organize_program_volumes(
        _score(hierarchy=0.72, variation=0.78, interruption=0.22),
        'museum', grammar_id=grammar)
    massing = model.to_program_massing()
    occupied = {level.id: level for level in massing.levels if level.kind == 'occupied'}

    for union in model.level_unions:
        sources = [volume for volume in model.volumes
                   if volume.level_id == union.level_id]
        source_union = unary_union([_volume_shape(model, volume) for volume in sources])
        contract = _shape(union.boundary, union.voids)
        plate = _shape(occupied[union.level_id].plate, occupied[union.level_id].voids)
        assert source_union.geom_type == 'Polygon'
        assert source_union.symmetric_difference(contract).area <= 1e-6
        assert contract.symmetric_difference(plate).area <= 1e-6

    assert massing.massing_id == 'MAS-PROGRAM-VOLUME'
    assert massing.program_volume_grammar_id == grammar
    assert massing.program_volume_source_digest == model.digest()
    assert not massing.zones, 'gross volumes shape the plate; detailed rooms are measured next'
    assert not any(level.is_terrace for level in occupied.values()), (
        'a shifted program floor remains enclosed; terrace means an intentionally '
        'open storey, not a changed silhouette')


@pytest.mark.parametrize('grammar', GRAMMARS)
def test_roof_control_copies_highest_union_through_massing_and_lattice(grammar):
    score = _score(hierarchy=0.72, variation=0.78, interruption=0.22)
    model = organize_program_volumes(score, 'museum', grammar_id=grammar)
    highest = model.level_unions[-1]
    control = model.roof_control
    assert control is not None
    assert control.boundary == highest.boundary
    assert control.voids == highest.voids
    assert control.datum_z == pytest.approx(model.levels[-1].z_top)

    massing = model.to_program_massing()
    assert massing.roof_control == control
    lattice = lattice_for(massing, datums_for(massing, score))
    assert lattice.roof_control == control


@pytest.mark.parametrize('grammar', GRAMMARS)
def test_program_volume_roof_cap_covers_every_emitted_roof_solid(grammar):
    score = _score(hierarchy=0.72, variation=0.78, interruption=0.22)
    model = organize_program_volumes(score, 'museum', grammar_id=grammar)
    massing = model.to_program_massing()
    datums = datums_for(massing, score)
    lattice = lattice_for(massing, datums)
    builder = _Builder(datums, lattice)
    _emit_roof(builder)

    elements = [element for group in builder.groups.values() for element in group.expand()]
    emitted = [element.geometry for element in elements]
    assert emitted
    assert max(roof_geometry_max_z(geometry) for geometry in emitted) <= (
        lattice.roof_control.physical_top_z + 1.0e-6)

    assembly_id = f'ROOF-{lattice.roof.id}-WARM-001'
    assert {element.assembly_id for element in elements} == {assembly_id}
    assert all(element.part_role and element.datum_refs for element in elements)
    assert all({ROOF_ASSEMBLY_RULE, ROOF_CONTROL_RULE,
                ROOF_PROFESSIONAL_REVIEW_RULE} <= set(element.rule_refs)
               for element in elements)
    assert all(element.supports or 'ENVELOPE-CLOSURE-UNRESOLVED-SUPPORT' in element.rule_refs
               for element in elements)

    expected_roles = {
        'structural_deck_substrate', 'vapour_control_layer',
        'insulation_fall_build_up', 'cover_board', 'waterproofing_membrane',
        'parapet_substrate', 'insulation_upstand', 'waterproofing_upstand', 'coping',
    }
    assert expected_roles <= {element.part_role for element in elements}
    plan = Polygon(lattice.roof_control.boundary, holes=lattice.roof_control.voids)
    horizontal_roles = {layer.part_role for layer in roof_assembly_layers(
        lattice.roof_control.profile)}
    horizontal_layers = [element for element in elements
                         if element.part_role in horizontal_roles]
    assert {element.part_role for element in horizontal_layers} == horizontal_roles
    for element in horizontal_layers:
        assert isinstance(element.geometry, ExtrusionGeometry)
        geometry = element.geometry
        emitted_plan = Polygon(
            [(point.x, point.y) for point in geometry.boundary],
            holes=[[(point.x, point.y) for point in ring] for ring in geometry.holes])
        assert emitted_plan.symmetric_difference(plan).area <= 1.0e-8
        assert geometry.z_top - geometry.z_base == pytest.approx(element.thickness_m)
        assert element.material_profile in MATERIALS
        assert element.validation_status == 'professional_review_required'


def test_roof_profile_cap_sums_the_emitted_warm_roof_and_coping():
    control = roof_control_for(
        [(0.0, 0.0), (12.0, 0.0), (12.0, 8.0), (0.0, 8.0)], [],
        datum_z=12.0, truss_depth_m=1.4)
    profile = control.profile
    layers = roof_assembly_layers(profile)

    assert [layer.part_role for layer in layers] == [
        'structural_deck_substrate', 'vapour_control_layer',
        'insulation_fall_build_up', 'cover_board', 'waterproofing_membrane']
    assert layers[-1].top_offset_m == pytest.approx(profile.warm_roof_top_offset_m)
    assert profile.parapet_body_top_offset_m + profile.coping_thickness_m == pytest.approx(
        profile.physical_top_offset_m)
    assert control.physical_top_z == pytest.approx(
        control.datum_z + profile.physical_top_offset_m)


@pytest.mark.parametrize('grammar', GRAMMARS)
def test_program_volume_roof_rejects_a_lowered_cap(grammar):
    score = _score(hierarchy=0.72, variation=0.78, interruption=0.22)
    model = organize_program_volumes(score, 'museum', grammar_id=grammar)
    control = model.roof_control
    assert control is not None
    lowered = control.model_copy(update={
        'physical_top_z': control.physical_top_z - 0.05,
    })
    massing = model.to_program_massing().model_copy(update={'roof_control': lowered})
    datums = datums_for(massing, score)
    with pytest.raises(ValueError, match='physical_top_z|roof section cap'):
        lattice = lattice_for(massing, datums)
        _emit_roof(_Builder(datums, lattice))


@pytest.mark.parametrize('point', ((0.05, 2.0), (3.95, 5.0)))
def test_roof_plan_gate_rejects_profile_body_crossing_edge_or_void(point):
    control = roof_control_for(
        [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)],
        [[(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0)]],
        datum_z=0.0, truss_depth_m=2.0)
    member = MemberGeometry(
        path=[v3(point[0], point[1], 0.0), v3(point[0], point[1], 1.0)],
        profile='PURLIN-120x200')
    with pytest.raises(ValueError, match='roof plan exceeded'):
        validate_roof_emission(control, [('TEST-ROOF-MEMBER', member)])


def test_terraced_volume_move_reaches_the_plate_and_identity():
    score = _score(hierarchy=0.8, variation=0.8)
    stacked = organize_program_volumes(score, 'museum', grammar_id='PVG-STACKED-BANDS')
    terraced = organize_program_volumes(score, 'museum', grammar_id='PVG-TERRACED-WEAVE')
    assert stacked.to_program_massing().digest() != terraced.to_program_massing().digest()
    assert [union.boundary for union in stacked.level_unions] != [
        union.boundary for union in terraced.level_unions]


def test_concave_volume_facade_offsets_outboard_and_remaps_the_entry():
    # A redundant station on the south edge is deliberate: true polygon offsets may
    # remove it, so source and facade edge indices no longer have the same meaning.
    plate = [v2(*point) for point in (
        (0, 0), (4, 0), (8, 0), (8, 8), (4, 8), (4, 4), (0, 4))]
    outboard = inset(plate, -0.5)
    source_shape = Polygon([(point.x, point.y) for point in plate])
    facade_shape = Polygon([(point.x, point.y) for point in outboard])
    assert facade_shape.covers(source_shape)
    assert facade_shape.area > source_shape.area

    entrance = SimpleNamespace(
        center=(2.0, 0.0), tangent=(1.0, 0.0), edge=0, fraction=0.5,
        width_m=2.4)
    spans = registered_bays(outboard, module=2.0, minimum_span=0.3)
    remodulated, entry_span = _register_entrance(
        spans, plate, outboard, entrance, module=2.0,
        minimum_span=0.3, jamb_width=0.3)
    assert entry_span is not None
    assert entry_span in remodulated
    edge, low, high = entry_span
    centre = (low + high) / 2.0
    point = outboard[edge]
    nxt = outboard[(edge + 1) % len(outboard)]
    assert point.x + (nxt.x - point.x) * centre == pytest.approx(2.0)
    assert point.y + (nxt.y - point.y) * centre == pytest.approx(-0.5)


def test_program_volume_partition_body_stops_at_the_facade_boundary():
    level = SimpleNamespace(
        plate=[v2(*point) for point in (
            (0, 0), (8, 0), (8, 8), (4, 8), (4, 4), (0, 4))],
        voids=[])
    assert _clear_of_plate_edge(0, 0, 8, 0, level, 0.12) == []
    clipped = _clear_of_plate_edge(2, 0, 2, 3, level, 0.12)
    assert len(clipped) == 1
    x0, y0, x1, y1 = clipped[0]
    assert (x0, x1, y1) == pytest.approx((2.0, 2.0, 3.0))
    assert y0 == pytest.approx(0.06001)
