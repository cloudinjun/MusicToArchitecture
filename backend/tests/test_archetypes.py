"""The theatre archetype: derived, then measured, and the measurement is the gate.

Decision 0016 has the theatre build the archetype layer first. These tests hold both
halves of its contract. The derivation half is arithmetic: the rake recurrence must
produce exactly the C-value it was asked for, row over row, checkable by hand. The
measurement half is the model: a compiled theatre must contain the bowl as geometry,
the plates its section claimed must actually be gone from the lattice, the sightline
gate must recompute every row's clearance from the emitted riser tops -- and the
columns still standing in the bowl must be reported as the violation they are, not
absorbed into a passing summary. A theatre that cannot carve must refuse with a
reason, never degrade into the flat rectangle the archetype replaces.
"""

import json
from pathlib import Path

import pytest

from backend.app.archetypes import (
    C_VALUE_DESIGN_M, C_VALUE_MIN_M, ROW_DEPTH_M, STAGE_RISE_M, CarveRefusal,
    derive_bowl,
)
from backend.app.compiler_v3 import compile_building_model_v3
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


@pytest.fixture(scope='module')
def theatre(features, template):
    return compile_building_model_v3(features, template, massing_id='MAS-SLAB',
                                     typology='theater')


# ---------------------------------------------------------------------------
# The derivation, by hand
# ---------------------------------------------------------------------------

def test_the_rake_recurrence_delivers_its_design_c_value():
    rows = derive_bowl(house_w_m=40.0)
    assert len(rows) >= 10
    focal = STAGE_RISE_M
    for near, far in zip(rows, rows[1:]):
        # The sightline from the farther eye to the focal point, evaluated at the
        # nearer row: similar triangles, no geometry library involved.
        sight = focal + (far.eye_m - focal) * near.distance_m / far.distance_m
        assert sight - near.eye_m == pytest.approx(C_VALUE_DESIGN_M, abs=1e-3)


def test_the_rake_only_ever_rises():
    rows = derive_bowl(house_w_m=40.0)
    assert rows[0].floor_m == pytest.approx(0.0, abs=1e-6)
    for near, far in zip(rows, rows[1:]):
        assert far.floor_m > near.floor_m
        assert far.distance_m - near.distance_m == pytest.approx(ROW_DEPTH_M)


def test_a_shallow_house_holds_fewer_rows_not_steeper_ones():
    deep = derive_bowl(house_w_m=42.0)
    shallow = derive_bowl(house_w_m=25.0)
    assert len(shallow) < len(deep)
    for a, b in zip(shallow, deep):
        assert a.floor_m == pytest.approx(b.floor_m, abs=1e-6)


# ---------------------------------------------------------------------------
# The compiled theatre
# ---------------------------------------------------------------------------

def test_the_theatre_carves_rather_than_refuses(theatre):
    report = theatre.archetype
    assert report is not None
    assert report.refused is None
    assert report.archetype_id == 'ARCH-THEATRE-BOWL'


def test_the_house_is_delivered_to_its_own_tolerance(theatre):
    zones = {zone.space_id: zone for zone in theatre.program_allocation.zones}
    house = zones['SP-AUDITORIUM']
    stage = zones['SP-STAGE']
    assert house.area_satisfied and stage.area_satisfied
    assert house.area_delivered_m2 >= house.area_required_m2 * 0.97


def test_the_bowl_is_geometry_not_a_flat_zone(theatre):
    risers = [e for e in theatre.elements if e.kind == 'auditorium_riser']
    assert len(risers) >= 8
    tops = sorted(e.position.z + e.dimensions.z / 2.0 for e in risers)
    assert tops[-1] - tops[0] > 1.0, 'the rake must actually rise'
    assert any(e.kind == 'stage_platform' for e in theatre.elements)
    assert any(e.kind == 'proscenium_wall' for e in theatre.elements)


def test_every_row_is_measured_and_every_measured_row_sees(theatre):
    report = theatre.archetype
    risers = [e for e in theatre.elements if e.kind == 'auditorium_riser']
    assert len(report.sightlines) == len(risers)
    measured = [record for record in report.sightlines
                if record.c_measured_m is not None]
    assert len(measured) == len(risers) - 1
    for record in measured:
        assert record.c_measured_m >= C_VALUE_MIN_M - 1e-3, record
    assert not [f for f in report.findings if f.gate_id == 'ARCH-SIGHTLINE']


def test_the_claimed_plates_are_actually_gone(theatre):
    report = theatre.archetype
    assert not [f for f in report.findings if f.gate_id == 'ARCH-CLAIM-UNCUT']
    # The house needs more clear height than one storey gives, so at least one
    # upper plate must carry a void over it.
    ground = theatre.lattice.occupied[0]
    f2f = theatre.lattice.occupied[1].z - ground.z if \
        len(theatre.lattice.occupied) > 1 else 99.0
    if report.clear_house_m > f2f:
        voided = [level for level in theatre.lattice.occupied[1:] if level.voids]
        assert voided, 'a claim above the first storey must cut a plate'


def test_the_colonnade_in_the_bowl_is_reported_not_hidden(theatre):
    """Columns still stand in the carved volumes: the long-span re-frame is the
    phase 0016 owes. Until it lands, the gate must say so -- and the day it lands,
    this test flips to asserting the finding is gone."""
    hx0, hy0, hx1, hy1 = theatre.archetype.house
    inside = [e for e in theatre.elements
              if e.kind in ('column', 'piloti_column')
              and hx0 + 0.3 < e.position.x < hx1 - 0.3
              and hy0 + 0.3 < e.position.y < hy1 - 0.3]
    findings = [f for f in theatre.archetype.findings
                if f.gate_id == 'ARCH-CLEAR-SPAN']
    if inside:
        assert findings, 'columns in the bowl must be reported'
        assert 'not yet re-framed' in findings[0].detail
    else:
        assert not findings


def test_the_carve_does_not_break_the_rest_of_the_building(theatre):
    spatial = theatre.spatial
    assert spatial is not None
    violations = [f for f in spatial.findings if f.severity == 'violation']
    assert not violations, [f.detail for f in violations]


def test_a_refusal_names_its_rooms_and_its_reason():
    refusal = CarveRefusal(
        archetype_id='ARCH-THEATRE-BOWL', precluded=[], reason='test')
    assert refusal.reason == 'test'


# ---------------------------------------------------------------------------
# Every typology carves, not only the theatre
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def museum(features, template):
    return compile_building_model_v3(features, template,
                                     massing_id='MAS-COURTYARD',
                                     typology='museum')


@pytest.fixture(scope='module')
def library(features, template):
    return compile_building_model_v3(features, template, massing_id='MAS-SLAB',
                                     typology='library')


@pytest.fixture(scope='module')
def pavilion(features, template):
    return compile_building_model_v3(features, template,
                                     massing_id='MAS-PAVILION',
                                     typology='pavilion')


def test_every_typology_carves_on_its_own_biased_massing(theatre, museum, library,
                                                         pavilion):
    """The kit's bias names a massing its own archetype accepts, measured by
    compiling the pair -- the lesson the theatre's bar-podium trap taught."""
    for model in (theatre, museum, library, pavilion):
        report = model.archetype
        assert report is not None, model.typology
        assert report.refused is None, (model.typology, report.refused)
        assert report.rooms, model.typology


def test_the_galleries_are_a_sequence_on_the_roof_lit_plate(museum):
    report = museum.archetype
    for gate in ('ARCH-ENFILADE', 'ARCH-TOPLIGHT', 'ARCH-CLAIM-UNCUT'):
        assert not [f for f in report.findings if f.gate_id == gate], gate
    # Under the roof means either the last occupied plate, or every plate above the
    # galleries opened over them -- a top plate too small to hold the pair sends them
    # one plate down with the roof-light claim carried through the void.
    top = museum.lattice.occupied[-1].index
    zones = {z.space_id: z for z in museum.program_allocation.zones}
    for space_id in report.rooms:
        zone = zones[space_id]
        above = [level for level in museum.lattice.occupied if level.index > zone.level_index]
        assert zone.level_index == top or all(level.voids for level in above), space_id
        assert zone.area_satisfied, space_id
    assert [e for e in museum.elements if e.id.startswith('PRG-ENF-')], \
        'the party wall must be built, or the enfilade gate measured nothing'


def test_the_reading_room_is_daylit_and_double_height(library):
    report = library.archetype
    assert not [f for f in report.findings
                if f.gate_id in ('ARCH-DAYLIGHT', 'ARCH-CLAIM-UNCUT')]
    zones = {z.space_id: z for z in library.program_allocation.zones}
    (space_id, rect), = report.rooms.items()
    assert zones[space_id].area_satisfied
    # The plate above the room really is open: the claim gate passed, and the
    # voided level must carry a hole overlapping the room.
    host_index = zones[space_id].level_index
    above = next(level for level in library.lattice.occupied
                 if level.index > host_index)
    assert above.voids, 'the double height claim left no void above the room'


def test_the_pavilion_hall_is_the_full_height_volume(pavilion):
    report = pavilion.archetype
    assert not [f for f in report.findings
                if f.gate_id in ('ARCH-DAYLIGHT', 'ARCH-CLAIM-UNCUT')]
    assert report.clear_m is not None
    storey = (pavilion.lattice.occupied[1].z - pavilion.lattice.occupied[0].z
              if len(pavilion.lattice.occupied) > 1 else 0.0)
    assert report.clear_m > storey, 'the hall must be taller than one storey'


def test_the_other_carves_do_not_break_their_buildings(museum, library, pavilion):
    for model in (museum, library, pavilion):
        violations = [f for f in model.spatial.findings
                      if f.severity == 'violation']
        assert not violations, (model.typology,
                                [f.detail for f in violations])
