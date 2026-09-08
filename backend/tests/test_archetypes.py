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
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from backend.app.archetypes import (
    C_VALUE_DESIGN_M, C_VALUE_MIN_M, ROW_DEPTH_M, STAGE_RISE_M, CarveRefusal,
    carve_museum, carve_theatre, derive_bowl,
)
from backend.app.briefs import brief_for
from backend.app.compiler_v3 import compile_building_model_v3, core_anchors
from backend.app.datums import build_lattice, compile_datum_set
from backend.app.geometry import ExtrusionGeometry
from backend.app.massing import MASSING_FAMILIES
from backend.app.models import ArchitecturalScore, AudioFeatures
from backend.app.plan_regions import usable_region
from backend.app.program_massing import datums_for, lattice_for
from backend.app.program_volumes import organize_program_volumes

ROOT = Path(__file__).parents[2]
DEMO = ROOT / 'artifacts' / 'v3_demo'
V2_DEMO = (ROOT / 'artifacts' / 'integrated_demo'
           / 'building-b7ad95fa45a6-library-steel-international-v1')
PV_GRAMMARS = (
    'PVG-STACKED-BANDS',
    'PVG-TERRACED-WEAVE',
    'PVG-SPLIT-BRIDGE',
)


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


def test_stage_clearance_reaches_a_shifted_upper_east_facade(template):
    """A drifting bar leaves no detached floor sliver beyond its east-end stage."""

    datums = compile_datum_set(template)
    base = MASSING_FAMILIES['MAS-BAR-PODIUM']
    massing = base.model_copy(update={
        'plan_x_m': round(base.plan_x_m * 1.5, 3),
        'plan_y_m': round(base.plan_y_m * 1.5, 3),
    })
    lattice = build_lattice(datums, massing, cutaway=False)
    carve = carve_theatre(
        lattice, datums, brief_for('theater', storeys=len(lattice.occupied)))

    assert not isinstance(carve, CarveRefusal)
    first_cut_level = min(carve.removed)
    level = lattice.level(first_cut_level)
    stage_cut = max(carve.removed[first_cut_level], key=lambda rect: rect[2])
    assert stage_cut[2] >= max(point.x for point in level.plate)


@pytest.mark.parametrize('grammar', PV_GRAMMARS)
def test_program_volume_theatre_carve_consumes_its_exact_owner_pair(template, grammar):
    volumes = organize_program_volumes(
        template, 'theater', grammar_id=grammar)
    massing = volumes.to_program_massing()
    datums = datums_for(massing, template)
    lattice = lattice_for(massing, datums)
    if lattice.given_cores:
        core_anchors(lattice, datums)
    carve = carve_theatre(
        lattice, datums, brief_for('theater', storeys=len(lattice.occupied)))

    assert not isinstance(carve, CarveRefusal), getattr(carve, 'reason', None)
    owners = {
        space_id: box(*region.resolve_bounds(lattice))
        for region in lattice.program_volume_regions
        for space_id in region.space_ids
        if space_id in ('SP-AUDITORIUM', 'SP-STAGE')
    }
    assert set(owners) == {'SP-AUDITORIUM', 'SP-STAGE'}
    assert owners['SP-AUDITORIUM'].buffer(1e-6).covers(box(*carve.house))
    assert owners['SP-STAGE'].buffer(1e-6).covers(box(*carve.stage))
    assert carve.house[1:4:2] == pytest.approx(carve.stage[1:4:2])
    assert carve.house[2] == pytest.approx(carve.stage[0])

    cuts_by_level = {
        level_index: unary_union([box(*rect) for rect in cuts])
        for level_index, cuts in carve.removed.items()
    }
    level_by_id = {level.id: level.index for level in lattice.occupied}
    for region in lattice.program_volume_regions:
        if region.role not in ('program', 'archetype'):
            continue
        cut = cuts_by_level.get(level_by_id[region.level_id])
        if cut is not None:
            assert cut.intersection(box(*region.resolve_bounds(lattice))).area <= 1e-6


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


def test_stage_access_pocket_is_removed_from_the_emitted_stage_zone(theatre):
    """The service route takes a pocket from the stage without overlapping it."""
    stage_zone = next(
        instance for group in theatre.element_groups if group.kind == 'program_zone'
        for instance in group.instances if instance.id.endswith('-SP-STAGE'))
    assert isinstance(stage_zone.geometry, ExtrusionGeometry)
    assert len(stage_zone.geometry.boundary) > 4
    stage_access_ids = {
        instance.id for group in theatre.element_groups
        if group.subsystem == 'stage_access' for instance in group.instances}
    overlaps = theatre.spatial.by_rule('SP-SUBSYSTEM-OVERLAP')
    assert not [finding for finding in overlaps
                if stage_access_ids & set(finding.elements)]


def test_stage_access_arrives_on_the_stage_without_impersonating_a_floor_landing(
        theatre):
    """The raised working platform keeps its host level without claiming its datum."""
    access = [element for element in theatre.elements
              if element.subsystem == 'stage_access']
    top = next(element for element in access
               if element.id == 'PRG-STG-ACCESS-L01-TOP')
    stage = next(element for element in theatre.elements
                 if element.id == 'PRG-STG-L01')

    assert top.kind == 'stage_platform'
    assert top.level_id == 'L01'
    assert not [element for element in access if element.kind == 'stair_landing']
    assert top.position.z + top.dimensions.z / 2 == pytest.approx(
        stage.position.z + stage.dimensions.z / 2)


def test_entry_landing_cedes_floor_from_seating_bands(theatre):
    """One shared approach boundary keeps the landing exposed and both bands intact."""
    landing = next(element for element in theatre.elements
                   if element.id == 'CIR-LND-ENTRY')
    landing_plan = box(
        landing.position.x - landing.dimensions.x / 2,
        landing.position.y - landing.dimensions.y / 2,
        landing.position.x + landing.dimensions.x / 2,
        landing.position.y + landing.dimensions.y / 2)
    risers = [element for element in theatre.elements
              if element.kind == 'auditorium_riser']
    bands_by_row = {}
    for riser in risers:
        bands_by_row.setdefault(riser.lattice_index['row'], set()).add(
            riser.lattice_index['band'])
        riser_plan = box(
            riser.position.x - riser.dimensions.x / 2,
            riser.position.y - riser.dimensions.y / 2,
            riser.position.x + riser.dimensions.x / 2,
            riser.position.y + riser.dimensions.y / 2)
        assert landing_plan.intersection(riser_plan).area <= 1e-8, riser.id
    assert bands_by_row
    assert all(bands == {0, 1} for bands in bands_by_row.values())


def test_every_row_is_measured_and_every_measured_row_sees(theatre):
    report = theatre.archetype
    risers = [e for e in theatre.elements if e.kind == 'auditorium_riser']
    row_count = len({riser.lattice_index['row'] for riser in risers})
    assert len(report.sightlines) == row_count
    measured = [record for record in report.sightlines
                if record.c_measured_m is not None]
    assert len(measured) == row_count - 1
    for record in measured:
        assert record.c_measured_m >= C_VALUE_MIN_M - 1e-3, record
    assert not [f for f in report.findings if f.gate_id == 'ARCH-SIGHTLINE']


def test_the_claimed_plates_are_actually_gone(theatre):
    report = theatre.archetype
    assert not [f for f in report.findings if f.gate_id == 'ARCH-CLAIM-UNCUT']
    ground = theatre.lattice.occupied[0]
    stations = [*theatre.lattice.y_lines, *(point.y for point in ground.plate)]
    assert all(any(abs(edge - station) <= 0.001 for station in stations)
               for edge in (report.house[1], report.house[3]))
    # The house needs more clear height than one storey gives, so at least one
    # upper plate must have the exact claimed footprint subtracted from it.
    f2f = theatre.lattice.occupied[1].z - ground.z if \
        len(theatre.lattice.occupied) > 1 else 99.0
    claimed = []
    for level in theatre.lattice.occupied[1:]:
        rise = level.z - ground.z
        cuts = []
        if rise < report.clear_house_m + 0.3:
            cuts.append(box(*report.house))
        if rise < report.clear_stage_m + 0.3:
            cuts.append(box(*report.stage))
        if cuts:
            claimed.append((level, cuts))
    if report.clear_house_m > f2f:
        assert claimed, 'a claim above the first storey must cut a plate'
    for level, cuts in claimed:
        remaining = usable_region(level)
        assert remaining.intersection(unary_union(cuts)).area <= 1e-5
        assert remaining.geom_type == 'Polygon', (level.index, remaining.geom_type)
        assert remaining.is_valid and not remaining.is_empty
        assert remaining.area >= 120.0


def test_the_colonnade_in_the_bowl_is_reported_not_hidden(theatre):
    """Columns still stand in the carved volumes: the long-span re-frame is the
    phase 0016 owes. Until it lands, the gate must say so -- and the day it lands,
    this test flips to asserting the finding is gone."""
    hx0, hy0, hx1, hy1 = theatre.archetype.house
    base_z = theatre.lattice.occupied[0].z
    clear_top = base_z + theatre.archetype.clear_house_m
    inside = [e for e in theatre.elements
              if e.kind in ('column', 'piloti_column')
              and min(max(p.z for p in e.geometry.path), clear_top)
                  - max(min(p.z for p in e.geometry.path), base_z) > 1e-6
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


@pytest.mark.parametrize('grammar', PV_GRAMMARS)
def test_program_volume_museum_carve_consumes_owner_pair_not_structural_grid(
        template, grammar):
    volumes = organize_program_volumes(template, 'museum', grammar_id=grammar)
    massing = volumes.to_program_massing()
    datums = datums_for(massing, template)
    lattice = lattice_for(massing, datums)
    if lattice.given_cores:
        core_anchors(lattice, datums)
    brief = brief_for('museum', storeys=len(lattice.occupied))
    carve = carve_museum(lattice, datums, brief)

    assert not isinstance(carve, CarveRefusal), getattr(carve, 'reason', None)
    owners = {
        space_id: box(*region.resolve_bounds(lattice))
        for region in lattice.program_volume_regions
        for space_id in region.space_ids
        if space_id in ('SP-GALLERY-A', 'SP-GALLERY-B')
    }
    assert set(owners) == {'SP-GALLERY-A', 'SP-GALLERY-B'}
    for space_id, rect in carve.rooms.items():
        assert owners[space_id].buffer(1e-6).covers(box(*rect))

    changed = lattice.model_copy(update={
        'y_lines': [value + (0.317 if index % 2 else -0.193)
                    for index, value in enumerate(lattice.y_lines)],
    })
    repeated = carve_museum(changed, datums, brief)
    assert not isinstance(repeated, CarveRefusal), getattr(repeated, 'reason', None)
    assert repeated.rooms == carve.rooms
    assert repeated.party_axis == carve.party_axis
    assert repeated.party_pos == carve.party_pos


def test_the_reading_room_is_daylit_and_double_height(library):
    report = library.archetype
    assert not [f for f in report.findings
                if f.gate_id in ('ARCH-DAYLIGHT', 'ARCH-CLAIM-UNCUT')]
    zones = {z.space_id: z for z in library.program_allocation.zones}
    (space_id, rect), = report.rooms.items()
    assert zones[space_id].area_satisfied
    # The plate above the room really is open. An edge-touching claim becomes a
    # notch in the outer ring; an interior claim remains a hole.
    host_index = zones[space_id].level_index
    above = next(level for level in library.lattice.occupied
                 if level.index > host_index)
    remaining = usable_region(above)
    assert remaining.intersection(box(*rect)).area <= 1e-5
    assert remaining.geom_type == 'Polygon'
    assert remaining.is_valid and not remaining.is_empty


def test_the_pavilion_hall_is_the_full_height_volume(pavilion):
    report = pavilion.archetype
    assert not [f for f in report.findings
                if f.gate_id in ('ARCH-DAYLIGHT', 'ARCH-CLAIM-UNCUT')]
    assert report.clear_m is not None
    storey = (pavilion.lattice.occupied[1].z - pavilion.lattice.occupied[0].z
              if len(pavilion.lattice.occupied) > 1 else 0.0)
    assert report.clear_m > storey, 'the hall must be taller than one storey'
    hall_id = next(iter(report.rooms))
    zone = next(zone for zone in pavilion.program_allocation.zones
                if zone.space_id == hall_id)
    assert zone.area_satisfied


def test_pavilion_upper_floors_and_ceiling_offsets_stay_connected(pavilion):
    """The exact hall notch and its true 150 mm ceiling offset are both buildable."""
    hall = box(*next(iter(pavilion.archetype.rooms.values())))
    ground = pavilion.lattice.occupied[0]
    stations = [*pavilion.lattice.y_lines, *(point.y for point in ground.plate)]
    assert all(any(abs(edge - station) <= 0.001 for station in stations)
               for edge in (hall.bounds[1], hall.bounds[3]))
    for level in pavilion.lattice.occupied[1:]:
        remaining = usable_region(level)
        assert remaining.intersection(hall).area <= 1e-5
        assert remaining.geom_type == 'Polygon', (level.index, remaining.geom_type)
        assert remaining.is_valid and not remaining.is_empty
        ceiling = Polygon(remaining.exterior.coords).buffer(-0.15, join_style=2)
        assert ceiling.geom_type == 'Polygon', (level.index, ceiling.geom_type)
        assert ceiling.is_valid and not ceiling.is_empty


def test_the_other_carves_do_not_break_their_buildings(museum, library, pavilion):
    for model in (museum, library, pavilion):
        violations = [f for f in model.spatial.findings
                      if f.severity == 'violation']
        assert not violations, (model.typology,
                                [f.detail for f in violations])
