"""Program Volume meaning survives the compiler boundary as registered data."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from backend.app.models import ArchitecturalScore, ScoreDimension
from backend.app.program_massing import (
    MassingLevel, ProgramMassing, datums_for, lattice_for, neutral_score,
    program_massing_of,
)
from backend.app.program_volume_contracts import ProgramVolumeRegion
from backend.app.program_volumes import organize_program_volumes

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


def _score() -> ArchitecturalScore:
    return ArchitecturalScore(
        score_id='score-program-volume-semantics',
        source_audio_sha256='7' * 64,
        dimensions=[ScoreDimension(
            id=dimension,
            value={'hierarchy': 0.72, 'variation': 0.78,
                   'interruption': 0.22}.get(dimension, 0.4),
            source_feature=f'test_{dimension}',
            extraction_method='manual', confidence=1.0,
            architectural_proposal='Program Volume semantic propagation test.')
                    for dimension in DIMENSIONS],
        mapping_rules=[])


@pytest.fixture(params=GRAMMARS)
def volume_chain(request):
    score = _score()
    model = organize_program_volumes(
        score, 'museum', grammar_id=request.param)
    massing = model.to_program_massing()
    lattice = lattice_for(massing, datums_for(massing, score))
    return model, massing, lattice


def test_regions_survive_program_volume_to_massing_to_lattice_exactly(volume_chain):
    model, massing, lattice = volume_chain
    levels = {level.id: level for level in model.levels}
    expected = [ProgramVolumeRegion(
        id=volume.id,
        level_id=volume.level_id,
        category=volume.category,
        role=volume.role,
        space_ids=list(volume.space_ids),
        grid_rect=volume.grid_rect,
        z_base=levels[volume.level_id].z_base,
        z_top=levels[volume.level_id].z_top)
                for volume in model.volumes]
    assert model.program_volume_regions == expected
    assert massing.program_volume_regions == expected
    assert lattice.program_volume_regions == expected
    assert lattice.program_volume_grammar_id == model.grammar_id
    assert lattice.program_volume_source_digest == model.digest()


def test_three_grammars_carry_three_distinct_circulation_intents():
    models = [organize_program_volumes(
        _score(), 'museum', grammar_id=grammar) for grammar in GRAMMARS]
    intents = [model.circulation_intent for model in models]
    assert all(intent is not None for intent in intents)
    assert len({intent.model_dump_json() for intent in intents}) == len(GRAMMARS)
    assert {intent.public_stair_family for intent in intents} == {
        'broad_straight', 'terraced_cascade', 'bridge_split'}
    assert {intent.ramp_preference for intent in intents} == {
        'edge_parallel', 'terrace_return', 'notch_switchback'}


def test_entry_station_is_ccw_union_boundary_with_exterior_to_its_right(volume_chain):
    model, massing, lattice = volume_chain
    intent = model.circulation_intent
    assert intent is not None
    station = intent.entry_station
    first_union = next(union for union in model.level_unions
                       if union.level_id == model.levels[0].id)
    union_shape = Polygon(first_union.boundary, holes=first_union.voids)
    point, _tangent, outward = station.resolve(model.grid)
    gaps = [abs(b - a) for lines in (model.grid.x_lines, model.grid.y_lines)
            for a, b in zip(lines, lines[1:])]
    epsilon = min(gap for gap in gaps if gap > 0.0) * 1.0e-5

    assert union_shape.boundary.distance(Point(*point)) <= 1.0e-7
    assert not union_shape.covers(Point(
        point[0] + outward[0] * epsilon,
        point[1] + outward[1] * epsilon))
    assert union_shape.covers(Point(
        point[0] - outward[0] * epsilon,
        point[1] - outward[1] * epsilon))
    assert massing.circulation_intent == intent
    assert lattice.circulation_intent == intent


def test_circulation_ids_reference_authored_volumes_and_separate_connectors(volume_chain):
    model, _massing, _lattice = volume_chain
    intent = model.circulation_intent
    assert intent is not None
    volumes = {volume.id: volume for volume in model.volumes}
    spine_ids = {volume.id for volume in model.volumes
                 if volume.role == 'circulation_spine'}
    connector_ids = {volume.id for volume in model.volumes
                     if volume.role == 'connector'}

    assert set(intent.carrier_volume_ids) == spine_ids
    assert set(intent.connector_volume_ids) == connector_ids
    assert not (set(intent.carrier_volume_ids) & set(intent.connector_volume_ids))
    assert intent.entry_station.source_volume_id in volumes
    assert volumes[intent.entry_station.source_volume_id].level_id == model.levels[0].id


def test_remote_spine_is_aligned_clear_and_connected_on_every_level(volume_chain):
    model, _massing, _lattice = volume_chain
    remote_by_level = {}
    remote_links = set()
    carrier_rects_by_level = []

    for level in model.levels:
        level_volumes = [volume for volume in model.volumes
                         if volume.level_id == level.id]
        carriers = [volume for volume in level_volumes
                    if volume.role == 'circulation_spine']
        assert len(carriers) == 2
        remote = max(carriers, key=lambda volume: volume.grid_rect[0])
        common = min(carriers, key=lambda volume: volume.grid_rect[0])
        remote_by_level[level.id] = remote
        carrier_rects_by_level.append(tuple(sorted(
            volume.grid_rect for volume in carriers)))
        assert box(*model.rect_of(remote)).intersection(
            box(*model.rect_of(common))).area <= 1.0e-7

        i0, j0, i1, j1 = remote.grid_rect
        assert i1 - i0 >= 2
        assert j1 - j0 >= 2
        remote_shape = box(*model.rect_of(remote))
        owners = [volume for volume in level_volumes
                  if volume.role in ('program', 'archetype')]
        assert all(remote_shape.intersection(box(*model.rect_of(owner))).area
                   <= 1.0e-7 for owner in owners)

        links = [volume for volume in level_volumes
                 if volume.role == 'connector'
                 and box(*model.rect_of(volume)).boundary.intersection(
                     remote_shape.boundary).length > 1.0e-7]
        assert len(links) == 1
        link = links[0]
        remote_links.add(link.id)
        assert link.grid_rect[3] - link.grid_rect[1] == 1
        link_shape = box(*model.rect_of(link))
        assert all(link_shape.intersection(box(*model.rect_of(owner))).area
                   <= 1.0e-7 for owner in owners)

        prior_shapes = [box(*model.rect_of(volume)) for volume in level_volumes
                        if volume.id not in (remote.id, link.id)]
        prior_union = unary_union(prior_shapes)
        assert link_shape.boundary.intersection(prior_union.boundary).length > 1.0e-7
        complete_union = unary_union([*prior_shapes, link_shape, remote_shape])
        assert complete_union.geom_type == 'Polygon'
        assert complete_union.is_valid

        declared = next(union for union in model.level_unions
                        if union.level_id == level.id)
        declared_shape = Polygon(declared.boundary, holes=declared.voids)
        assert complete_union.symmetric_difference(declared_shape).area <= 1.0e-7
        if level.index == 1:
            assert model.circulation_intent is not None
            assert model.circulation_intent.entry_station.source_volume_id == common.id

    assert len(set(carrier_rects_by_level)) == 1
    remote_i0 = next(iter(remote_by_level.values())).grid_rect[0]
    prior_global_i1 = max(
        volume.grid_rect[2] for volume in model.volumes
        if volume.id not in remote_links
        and volume.id not in {remote.id for remote in remote_by_level.values()})
    assert remote_i0 == prior_global_i1 + 1


def test_high_daylight_library_owner_shares_the_remote_carrier_edge():
    model = organize_program_volumes(
        _score(), 'library', grammar_id='PVG-STACKED-BANDS')
    owner = next(volume for volume in model.volumes
                 if volume.space_ids == ['SP-QUIET'])
    remote = max(
        (volume for volume in model.volumes
         if volume.level_id == owner.level_id
         and volume.role == 'circulation_spine'),
        key=lambda volume: volume.grid_rect[0])
    owner_shape = box(*model.rect_of(owner))
    remote_shape = box(*model.rect_of(remote))

    assert owner_shape.intersection(remote_shape).area <= 1.0e-7
    assert owner_shape.boundary.intersection(
        remote_shape.boundary).length > 1.0e-7


def test_program_massing_export_preserves_volume_semantics(volume_chain, monkeypatch):
    _model, _massing, lattice = volume_chain
    empty_anchors = {
        'primary': None, 'served': [], 'second': None, 'second_served': [],
        'extras': [], 'lift': None,
    }
    monkeypatch.setattr(
        'backend.app.compiler_v3.core_anchors',
        lambda _lattice, _datums: empty_anchors)
    fake = SimpleNamespace(
        model_id='semantic-round-trip', typology='museum', lattice=lattice,
        datum_set=datums_for(_massing, _score()),
        project_brief=None,
        structural_system_id='STR-SYS-STEEL-FRAME',
        facade_grammar_id='FCD-05-HIGH-TECH')
    exported = program_massing_of(fake)
    assert exported.program_volume_regions == lattice.program_volume_regions
    assert exported.circulation_intent == lattice.circulation_intent
    assert exported.program_volume_grammar_id == lattice.program_volume_grammar_id
    assert exported.program_volume_source_digest == lattice.program_volume_source_digest


def test_legacy_massing_keeps_optional_program_volume_semantics_empty():
    plate = [(-8.0, -6.0), (8.0, -6.0), (8.0, 6.0), (-8.0, 6.0)]
    legacy = ProgramMassing(levels=[
        MassingLevel(plate=plate),
        MassingLevel(plate=plate),
    ])
    score = neutral_score(legacy)
    lattice = lattice_for(legacy, datums_for(legacy, score))
    assert legacy.program_volume_regions == []
    assert legacy.circulation_intent is None
    assert lattice.program_volume_regions == []
    assert lattice.circulation_intent is None
    assert lattice.program_volume_grammar_id is None
    assert lattice.program_volume_source_digest is None
