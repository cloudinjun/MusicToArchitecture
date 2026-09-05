"""Interior partitions: what divides one space from the next, and why that one.

What this replaces was a single box along the south edge of any private or service zone,
200 mm thick and 2.70 m tall whatever the storey height, with no type, no rating, no
acoustic separation and no door. A wall along one edge does not enclose a room, and
public zones got nothing at all.

The rules these tests hold:

- a partition is **chosen**, from a fire rating and an acoustic target that each cite
  where they come from;
- the lightest assembly that satisfies both is the one built, because a two-hour wall
  where an hour is required is not safer, it is just heavier;
- every opening is a real door with the ADA clear width, and a rated wall carries its
  rating across the doorway on a head;
- a wall nothing asks for is not built.
"""

import json
from pathlib import Path

import pytest

from backend.app.compiler_v3 import compile_building_model_v3
from backend.app.models import ArchitecturalScore, AudioFeatures
from backend.app.partitions import (
    BY_ID, DOOR_CLEAR_M, DOOR_LEAF_M, PARTITION_TYPES, required_separation,
    select_partition,
)

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
def model(features, template):
    return compile_building_model_v3(features, template, massing_id='MAS-SLAB',
                                     typology='library')


# ---------------------------------------------------------------------------
# The assemblies
# ---------------------------------------------------------------------------

def test_every_assembly_describes_itself_and_names_its_listing_basis():
    for partition in PARTITION_TYPES:
        assert partition.assembly, partition.id
        assert partition.listing_basis, partition.id
        assert partition.thickness_mm > 0


def test_assemblies_are_ordered_light_to_heavy():
    """The selector takes the first that works, so the order is the design objective."""
    weights = [(p.fire_rating_hours, p.stc) for p in PARTITION_TYPES]
    assert weights == sorted(weights, key=lambda pair: (pair[0], pair[1]))


def test_a_rating_alone_does_not_buy_acoustic_isolation():
    """The reason fire and acoustics are answered separately.

    A two-hour masonry wall is acoustically worse than a double-stud partition with no
    rating at all, so a selector that treated one as a proxy for the other would pick
    wrongly in both directions.
    """
    masonry = BY_ID['PRT-CMU-2HR']
    isolating = BY_ID['PRT-ACOUSTIC-60']
    assert masonry.fire_rating_hours > isolating.fire_rating_hours
    assert isolating.stc > masonry.stc


# ---------------------------------------------------------------------------
# What the code asks for
# ---------------------------------------------------------------------------

def test_a_shaft_takes_its_rating_from_the_storeys_it_connects():
    low = required_separation('riser', 'circulation', category_a='service',
                              category_b='circulation', storeys=3, sprinklered=True)
    high = required_separation('riser', 'circulation', category_a='service',
                               category_b='circulation', storeys=6, sprinklered=True)
    assert low.fire_rating_hours == 1.0
    assert high.fire_rating_hours == 2.0
    assert '707.4' in high.fire_basis


def test_the_sprinkler_alternative_applies_where_the_code_offers_it():
    """IBC Table 509 gives a one-hour separation *or* a sprinkler for a storage room.

    Applying the alternative where it exists and refusing it where it does not is the
    difference between reading the table and remembering that it is there.
    """
    wet = required_separation('general_storage', 'adult_reading', category_a='service',
                              category_b='public', storeys=5, sprinklered=True)
    dry = required_separation('general_storage', 'adult_reading', category_a='service',
                              category_b='public', storeys=5, sprinklered=False)
    assert wet.fire_rating_hours == 0.0
    assert 'sprinklered' in wet.fire_basis
    assert dry.fire_rating_hours == 1.0

    # a mechanical room does not get the alternative in this project
    plant = required_separation('mechanical', 'adult_reading', category_a='service',
                                category_b='public', storeys=5, sprinklered=True)
    assert plant.fire_rating_hours == 1.0


def test_a_corridor_is_rated_only_when_the_building_is_not_sprinklered():
    wet = required_separation('adult_reading', 'circulation', category_a='public',
                              category_b='circulation', storeys=5, sprinklered=True)
    dry = required_separation('adult_reading', 'circulation', category_a='public',
                              category_b='circulation', storeys=5, sprinklered=False)
    assert wet.fire_rating_hours == 0.0
    assert dry.fire_rating_hours == 1.0
    assert '1020.1' in dry.fire_basis


def test_a_room_beside_a_noise_source_is_held_higher_than_it_would_ask_alone():
    alone = required_separation('seminar', 'adult_reading', category_a='public',
                                category_b='public', storeys=5, sprinklered=True)
    beside_plant = required_separation('seminar', 'mechanical', category_a='public',
                                       category_b='service', storeys=5,
                                       sprinklered=True)
    assert beside_plant.stc_target > alone.stc_target
    assert 'noise source' in beside_plant.stc_basis


def test_every_separation_says_where_both_numbers_come_from():
    requirement = required_separation('seminar', 'circulation', category_a='public',
                                      category_b='circulation', storeys=5,
                                      sprinklered=True)
    assert requirement.fire_basis
    assert requirement.stc_basis
    assert requirement.permeability_basis


def test_a_service_zone_is_reached_through_a_controlled_door():
    requirement = required_separation('refuse', 'circulation', category_a='service',
                                      category_b='circulation', storeys=5,
                                      sprinklered=True)
    assert requirement.permeability == 'controlled_door'


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def test_the_lightest_assembly_that_satisfies_both_is_chosen():
    requirement = required_separation('staff_workroom', 'circulation',
                                      category_a='private', category_b='circulation',
                                      storeys=5, sprinklered=True)
    chosen = select_partition(requirement)
    assert chosen.fire_rating_hours >= requirement.fire_rating_hours
    assert chosen.stc >= requirement.stc_target
    lighter = [p for p in PARTITION_TYPES
               if (p.fire_rating_hours, p.stc) < (chosen.fire_rating_hours, chosen.stc)]
    for candidate in lighter:
        assert (candidate.fire_rating_hours < requirement.fire_rating_hours
                or candidate.stc < requirement.stc_target), candidate.id


def test_a_shaft_always_gets_a_shaft_wall():
    """A two-hour wall built from one side is a different product, not a thicker one."""
    requirement = required_separation('riser', 'circulation', category_a='service',
                                      category_b='circulation', storeys=6,
                                      sprinklered=True)
    assert select_partition(requirement, shaft=True).id == 'PRT-SHAFT-2HR'


# ---------------------------------------------------------------------------
# What gets built
# ---------------------------------------------------------------------------

def test_a_zone_that_needs_enclosing_gets_more_than_one_wall(model):
    """One box along one edge is not enclosure, which is what was there before."""
    runs: dict[str, set[str]] = {}
    for element in model.elements:
        if element.kind != 'partition':
            continue
        # PRG-PRT-<level>-<space>-<edge>-<segment>
        parts = element.id.split('-')
        runs.setdefault('-'.join(parts[:4]), set()).add(parts[4])
    assert runs
    assert any(len(edges) >= 2 for edges in runs.values()), (
        'no zone is enclosed on more than one side')


def test_every_partition_opening_is_a_door_with_a_head_over_it(model):
    """A rated wall that stops at the door head is not rated."""
    doors = [e for e in model.elements
             if e.kind == 'door' and e.subsystem == 'partitions']
    heads = [e for e in model.elements
             if e.kind == 'partition_head' and e.subsystem == 'partitions']
    assert doors
    assert {door.id.removesuffix('-DR') + '-HD' for door in doors} == {
        head.id for head in heads
    }


def test_doors_clear_the_accessible_width(model):
    doors = [e for e in model.elements if e.kind == 'door']
    assert doors
    for door in doors:
        leaf = max(door.dimensions.x, door.dimensions.y)
        assert 'mm clear' in door.reason
        if door.subsystem == 'partitions':
            assert leaf >= DOOR_LEAF_M - 1e-6, door.id
            assert f'{DOOR_CLEAR_M * 1000:.0f} mm clear' in door.reason
        else:
            assert leaf >= DOOR_CLEAR_M - 1e-6, door.id


def test_a_rated_door_says_it_needs_a_rated_assembly(features, template):
    built = compile_building_model_v3(features, template, massing_id='MAS-SLAB',
                                      typology='museum')
    rated = [e for e in built.elements
             if e.kind == 'door' and 'IBC-716' in e.rule_refs]
    assert rated
    for door in rated:
        assert 'rated self-closing assembly' in door.reason


def test_partitions_run_to_the_underside_of_the_structure(model):
    """A partition that stops at a ceiling nobody modelled separates nothing."""
    f2f = model.datum_set.value('floor_to_floor_m')
    slab = model.datum_set.value('slab_thickness_m')
    expected = max(2.4, f2f - slab - 0.15)
    walls = [e for e in model.elements if e.kind == 'partition']
    assert walls
    assert all(e.dimensions.z >= expected - 0.02 for e in walls)
    assert any(e.dimensions.z == pytest.approx(expected, abs=0.02) for e in walls)


def test_a_wall_nothing_asks_for_is_not_built(features, template):
    """Two open-category rooms with no acoustic target and no rating stay open.

    Asserted on the count rather than on the reason text, because a glazed screen with
    the same STC 35 and no rating is entirely correct beside a service zone -- what
    decides it is the pair of categories, not the wall.
    """
    from backend.app.partitions import required_separation

    open_pair = required_separation('exhibition_foyer', 'cafe', category_a='public',
                                    category_b='public', storeys=5, sprinklered=True)
    assert open_pair.fire_rating_hours == 0.0

    built = compile_building_model_v3(features, template, massing_id='MAS-SLAB',
                                      typology='library')
    zones = {z.space_id for z in built.program_allocation.zones}
    walled_edges = {tuple(e.id.split('-')[:5]) for e in built.elements
                    if e.kind == 'partition'}
    # four edges per zone is the maximum; some are open, so fewer are built
    assert len(walled_edges) < 4 * len(zones)


def test_each_typology_gets_a_partition_mix_its_program_asks_for(features, template):
    """A theatre is all acoustically demanding rooms; a library is not."""
    mixes = {}
    for typology in ('library', 'museum', 'theater', 'pavilion'):
        built = compile_building_model_v3(features, template, massing_id='MAS-SLAB',
                                          typology=typology)
        labels = {e.reason.split(' between ')[0] for e in built.elements
                  if e.kind == 'partition'}
        assert labels, typology
        mixes[typology] = labels
    assert len({frozenset(v) for v in mixes.values()}) > 1


def test_every_partition_cites_the_clause_and_the_acoustic_basis(model):
    for element in model.elements:
        if element.kind not in ('partition', 'partition_head'):
            continue
        assert 'Acoustic target STC' in element.reason, element.id
        assert 'IBC' in element.reason or 'no rated separation' in element.reason
        assert element.rule_refs


# ---------------------------------------------------------------------------
# Constraints that are neither a rating nor an acoustic target
# ---------------------------------------------------------------------------

def test_a_store_is_never_glazed_or_demountable():
    """Reviewing the emitted schedule is what found this, twice.

    First the museum had glazed screens on its collection store, because nothing in a
    fire rating or an STC target says a store must not be seen into. Excluding glazing
    alone then put a demountable panel system there instead, which is opaque and still
    not an enclosure. Both are excluded now.
    """
    requirement = required_separation('closed_stack', 'circulation',
                                      category_a='service', category_b='circulation',
                                      storeys=5, sprinklered=True)
    assert requirement.opaque_required
    assert requirement.opaque_basis
    chosen = select_partition(requirement)
    assert chosen.construction not in ('glazed_screen', 'demountable')


def test_a_loading_bay_gets_a_wall_that_survives_a_trolley():
    """Abuse resistance and isolation are both required, so neither is traded away.

    A 250 mm gypsum wall at a loading dock is destroyed in a year; bare masonry beside
    a gallery transmits. The answer is masonry with an isolated lining, which is a real
    assembly rather than a preference between the two numbers.
    """
    requirement = required_separation('loading', 'exhibition_foyer',
                                      category_a='service', category_b='public',
                                      storeys=5, sprinklered=True)
    assert requirement.abuse_resistant
    chosen = select_partition(requirement)
    assert chosen.construction == 'masonry'
    assert chosen.stc >= requirement.stc_target
    assert chosen.fire_rating_hours >= requirement.fire_rating_hours


def test_a_quiet_store_still_gets_plain_masonry():
    """The composite assembly is for the case that needs it, not the default."""
    requirement = required_separation('general_storage', 'general_storage',
                                      category_a='service', category_b='service',
                                      storeys=5, sprinklered=True)
    chosen = select_partition(requirement)
    assert chosen.id == 'PRT-CMU-2HR'


def test_a_gallery_does_not_get_a_loading_bay_wall(features, template):
    """The constraints apply where they belong and nowhere else.

    On the courtyard rather than the slab because the test needs a gallery to check the
    walls of, and the slab this score produces has no room that holds one: a 520 m2
    permanent gallery at 11 m minimum dimension against a largest available rectangle of
    165 m2. That mismatch is the allocator reporting a brief too big for the massing,
    which is its own finding and not this test's.
    """
    built = compile_building_model_v3(features, template, massing_id='MAS-COURTYARD',
                                      typology='museum')
    gallery_walls = [e for e in built.elements
                     if e.kind == 'partition' and 'gallery' in e.reason.lower()]
    assert gallery_walls
    for wall in gallery_walls:
        assert 'Masonry with isolated lining' not in wall.reason
