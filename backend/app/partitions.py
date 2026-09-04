"""Interior partitions: what divides one space from the next, and why that one.

The pipeline drew a partition as a single box on the south edge of any private or service
zone -- 200 mm thick and 2.70 m tall whatever the storey height, on one side of a
rectangle, with no type, no rating, no acoustic separation and no door. A wall along one
edge of a room does not enclose it, and a room that is not enclosed is not a room. Public
zones got nothing at all.

Three questions decide a partition, and the old one answered none of them.

**What has to be separated.** The program constitution already carries a `must_separate`
relation and an `access_class`, so the model knows a staff workroom is not a gallery and
that refuse must not open onto the entrance sequence. Partitions are how those relations
become geometry -- until now the vocabulary existed and nothing built from it.

**What rating the separation needs.** IBC 509 rates the walls around incidental uses --
a storage room over 9.3 m2, a refuse room, a mechanical room -- at one hour, or admits a
sprinkler in lieu. IBC 707.4 rates a shaft at one hour below four storeys and two at four
and above. IBC 1020.1 rates a corridor at one hour unless the building is sprinklered.
None of these are preferences; a wall that is one hour short is a wall a plan checker
rejects.

**What the room needs acoustically.** A seminar room beside a lobby and a rehearsal room
beside a gallery are different problems, and neither is solved by the same 200 mm box.
STC targets are not code in the way fire ratings are -- they come from ANSI/ASA S12.60 for
teaching spaces and from ordinary practice elsewhere -- so they are recorded as targets
with their source rather than asserted as requirements.

**On the listings.** Each assembly here describes a real construction -- stud gauge and
spacing, layer count, board type -- and names the *kind* of tested assembly it belongs to
rather than a specific UL design number. A partition schedule for permit cites a tested
design; asserting one this project has not looked up would be the same failure the site
module refuses, which is a citation attached to a recollection.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Construction = Literal[
    'steel_stud_gypsum', 'shaft_wall', 'masonry', 'glazed_screen', 'demountable',
]

# Who may pass, which decides whether an opening gets a door and what kind.
Permeability = Literal['open', 'door', 'controlled_door', 'sealed']


class PartitionType(BaseModel):
    """One buildable partition assembly."""

    id: str
    label: str
    construction: Construction
    thickness_mm: float = Field(gt=0)
    fire_rating_hours: float = Field(ge=0.0)
    stc: int = Field(ge=0)
    material: str
    # What the assembly is, in enough detail to price and to look up a listing against.
    assembly: str
    listing_basis: str
    note: str = ''


# Assemblies ordered light to heavy, so the selector can take the first that satisfies
# both the rating and the acoustic target and get the cheapest wall that works.
PARTITION_TYPES: tuple[PartitionType, ...] = (
    PartitionType(
        id='PRT-GLAZED', label='Glazed screen', construction='glazed_screen',
        thickness_mm=100.0, fire_rating_hours=0.0, stc=35, material='glass',
        assembly='Aluminium framed single-glazed screen, 12 mm laminated glass, full '
                 'height with a head deflection track.',
        listing_basis='Non-rated. A rated glazed assembly needs fire-protective or '
                      'fire-resistive glazing and a tested frame, which is a different '
                      'product.',
        note='Divides without enclosing acoustically. Used where a room needs to be '
             'seen into.'),
    PartitionType(
        id='PRT-DEMOUNTABLE', label='Demountable partition', construction='demountable',
        thickness_mm=100.0, fire_rating_hours=0.0, stc=38, material='white_soft',
        assembly='Proprietary demountable system, 100 mm, factory-finished panels on a '
                 'floor and ceiling track.',
        listing_basis='Non-rated unless the manufacturer holds a listing for the '
                      'specific configuration.',
        note='Chosen where the brief expects the layout to change.'),
    PartitionType(
        id='PRT-GWB-NR', label='Non-rated stud partition',
        construction='steel_stud_gypsum', thickness_mm=124.0, fire_rating_hours=0.0,
        stc=39, material='white_soft',
        assembly='92 mm steel studs at 400 mm centres, one layer 16 mm gypsum board '
                 'each face, no insulation.',
        listing_basis='Non-rated. The default interior wall where nothing requires more.',
        note='The ordinary partition. Anything heavier needs a reason.'),
    PartitionType(
        id='PRT-GWB-1HR', label='One-hour stud partition',
        construction='steel_stud_gypsum', thickness_mm=124.0, fire_rating_hours=1.0,
        stc=45, material='white_soft',
        assembly='92 mm steel studs at 400 mm centres, one layer 16 mm Type X gypsum '
                 'board each face, mineral wool in the cavity.',
        listing_basis='A single-layer Type X stud wall of this configuration is the '
                      'common one-hour assembly. The specific tested design must be '
                      'cited on a partition schedule; this project does not choose one.',
        note='The workhorse rating: incidental uses, unsprinklered corridors, most '
             'occupancy separations at one hour.'),
    PartitionType(
        id='PRT-GWB-1HR-ACOUSTIC', label='One-hour acoustic stud partition',
        construction='steel_stud_gypsum', thickness_mm=156.0, fire_rating_hours=1.0,
        stc=52, material='white_soft',
        assembly='92 mm steel studs at 400 mm centres, two layers 16 mm Type X each '
                 'face, mineral wool, resilient channel one side.',
        listing_basis='A double-layer Type X stud wall reaches one hour comfortably; '
                      'the resilient channel is what carries the STC rather than the '
                      'rating.',
        note='Where a room needs both the hour and the quiet.'),
    PartitionType(
        id='PRT-SHAFT-2HR', label='Two-hour shaft wall', construction='shaft_wall',
        thickness_mm=130.0, fire_rating_hours=2.0, stc=51, material='white_soft',
        assembly='64 mm C-H studs, 25 mm shaft liner panel on the shaft face, two '
                 'layers 16 mm Type X on the room face.',
        listing_basis='Shaft wall assemblies are tested as a system and are the only '
                      'way to build a two-hour wall from one side.',
        note='Risers and lift shafts, which cannot be built from both faces.'),
    PartitionType(
        id='PRT-GWB-2HR', label='Two-hour stud partition',
        construction='steel_stud_gypsum', thickness_mm=156.0, fire_rating_hours=2.0,
        stc=54, material='white_soft',
        assembly='92 mm steel studs at 400 mm centres, two layers 16 mm Type X gypsum '
                 'board each face, mineral wool in the cavity.',
        listing_basis='A double-layer Type X stud wall is the common two-hour assembly.',
        note='Occupancy separations at two hours and exit enclosures below four '
             'storeys.'),
    PartitionType(
        id='PRT-ACOUSTIC-60', label='High-isolation double-stud partition',
        construction='steel_stud_gypsum', thickness_mm=250.0, fire_rating_hours=1.0,
        stc=60, material='white_soft',
        assembly='Two rows of 92 mm studs on separate plates with a 25 mm gap, two '
                 'layers 16 mm Type X each face, mineral wool in both cavities.',
        listing_basis='Structurally separated leaves are what get past STC 55; a single '
                      'framed wall cannot, whatever is hung on it.',
        note='Rehearsal, auditorium and anything beside plant.'),
    PartitionType(
        id='PRT-CMU-ACOUSTIC', label='Masonry with isolated lining',
        construction='masonry', thickness_mm=290.0, fire_rating_hours=2.0, stc=60,
        material='concrete',
        assembly='190 mm hollow concrete masonry with an independent 64 mm stud '
                 'lining on the quiet side, mineral wool in the cavity, two layers '
                 '16 mm gypsum board.',
        listing_basis='The masonry carries the rating on its own equivalent '
                      'thickness; the isolated lining carries the isolation. '
                      'Neither depends on the other being there.',
        note='A loading bay beside a quiet room needs both a wall that survives a '
             'trolley and one that stops the noise. Choosing between them, which is '
             'what a selector reading only the two numbers does, gets a gypsum wall '
             'destroyed in a year or a masonry one that transmits.'),
    PartitionType(
        id='PRT-CMU-2HR', label='Concrete masonry wall', construction='masonry',
        thickness_mm=190.0, fire_rating_hours=2.0, stc=52, material='concrete',
        assembly='190 mm hollow concrete masonry, grouted at reinforcement, painted or '
                 'fair faced.',
        listing_basis='IBC Table 722.3.2 gives the equivalent thickness for a masonry '
                      'fire-resistance rating directly, without a tested assembly.',
        note='Where the wall is also loadbearing or needs to take abuse: loading, '
             'refuse, plant.'),
)

# Sorted rather than trusted to be in order. `select_partition` takes the first
# assembly that satisfies both requirements, so the ordering *is* the design
# objective -- and the hand-written order had the STC 60 double-stud wall sitting
# after the two-hour ones, which would have handed out a two-hour wall where a
# one-hour one with better isolation was available and cheaper.
PARTITION_TYPES = tuple(sorted(
    PARTITION_TYPES,
    key=lambda p: (p.fire_rating_hours, p.stc, p.thickness_mm)))

BY_ID: dict[str, PartitionType] = {p.id: p for p in PARTITION_TYPES}


# ---------------------------------------------------------------------------
# What the code requires between two spaces
# ---------------------------------------------------------------------------

# IBC Table 509 incidental uses. Each needs a one-hour separation, or a sprinkler in
# lieu of it -- and the sprinkler alternative is why the site's `sprinklered` flag
# reaches this far.
INCIDENTAL_USE_TYPES: frozenset[str] = frozenset({
    'mechanical', 'plant', 'electrical_it', 'refuse', 'general_storage',
    'closed_stack', 'fire_service', 'loading',
})

# Space types that need to be quiet, and the target they are held to. ANSI/ASA S12.60
# sets 50 for a classroom envelope; the rest are ordinary practice and are labelled as
# such rather than as code.
STC_TARGETS: dict[str, tuple[int, str]] = {
    'seminar': (50, 'ANSI/ASA S12.60 for a teaching space'),
    # The house, the stage, and the room between them. An auditorium is the quietest
    # room in the building and stands against the two loudest -- a foyer holding the
    # whole audience at the interval, and a stage. These carried a gallery's 45 while
    # they shared the gallery's type; a performance space is not a gallery.
    'auditorium': (60, 'practice: a performance space is the quietest room here and '
                       'its neighbours are the loudest'),
    'stage': (60, 'practice: get-ins, scene changes and rehearsal run against '
                  'performance next door'),
    'theatre_foyer': (55, 'practice: the whole audience stands here at the interval, '
                          'on the other side of the auditorium wall'),
    'exhibition_foyer': (45, 'practice: a gallery needs its own quiet'),
    'adult_reading': (50, 'practice: a reading room is the quietest public space here'),
    'reading_room': (50, 'practice: a reading room is the quietest public space here'),
    'children_reading': (45, 'practice: noisy on purpose, so contain it'),
    'staff_workroom': (45, 'practice: staff need to speak without being overheard'),
    'staff_restroom': (45, 'practice: privacy'),
    'public_restroom': (45, 'practice: privacy'),
    'cafe': (45, 'practice: a cafe is a noise source, so contain it'),
}

# Plant and circulation cores are noise sources; anything occupied beside them needs
# more than the room's own target.
NOISE_SOURCES: frozenset[str] = frozenset({
    'mechanical', 'plant', 'electrical_it', 'refuse', 'loading', 'riser',
    # A stage is machinery and a foyer is five hundred people talking. Both are noise
    # sources to whatever stands beside them, which in a theatre is the one room that
    # cannot tolerate either.
    'stage', 'theatre_foyer',
})


# Rooms that need a fixed, opaque enclosure. A collection store behind a glazed
# screen is a security problem and a conservation one; behind a demountable panel
# system it is still not enclosed, it is partitioned. Neither a fire rating nor an
# STC target expresses this, so it has to be stated -- and reviewing the emitted
# schedule is what surfaced it, first as glazing on the store and then, after the
# glazing was excluded, as a demountable system in its place.
OPAQUE_REQUIRED_TYPES: frozenset[str] = frozenset({
    'closed_stack', 'general_storage', 'refuse', 'loading', 'mechanical', 'plant',
    'electrical_it', 'riser', 'fire_service', 'public_restroom', 'staff_restroom',
    'janitor', 'staff_workroom', 'staff_support',
})

# Rooms whose walls take a beating: trolleys, bins, pallets. Gypsum board on studs
# is the wrong product there whatever its rating, and masonry is what gets built.
ABUSE_RESISTANT_TYPES: frozenset[str] = frozenset({
    'loading', 'refuse', 'general_storage',
})


class SeparationRequirement(BaseModel):
    """What a wall between two named spaces has to do, and on whose authority."""

    fire_rating_hours: float
    fire_basis: str
    stc_target: int
    stc_basis: str
    permeability: Permeability
    permeability_basis: str
    # The clause that produced the rating, so a partition schedule cites what
    # governed rather than every clause the module can reach.
    fire_clause: str = ''
    # Constraints that are neither a rating nor an acoustic target, and that a
    # selector reading only those two gets wrong.
    opaque_required: bool = False
    opaque_basis: str = ''
    abuse_resistant: bool = False
    abuse_basis: str = ''


def required_separation(
    space_type_a: str, space_type_b: str, *, category_a: str, category_b: str,
    storeys: int, sprinklered: bool, area_a_m2: float = 0.0,
) -> SeparationRequirement:
    """The rating, the acoustic target and the openability between two spaces.

    Fire and acoustics are answered separately because they come from different places
    and one does not imply the other: a two-hour masonry wall can be acoustically worse
    than a double-stud partition with no rating at all.
    """
    rating, fire_clause = 0.0, 'IBC-509'
    fire_basis = ('IBC 708 and 509 require no rated separation between two spaces '
                  'of the same ordinary use.')

    if 'riser' in (space_type_a, space_type_b) or 'elevator' in (space_type_a,
                                                                space_type_b):
        rating, fire_clause = (2.0 if storeys >= 4 else 1.0), 'IBC-707.4'
        fire_basis = (f'IBC 707.4 shaft enclosure: {rating:.0f} hour for a shaft '
                      f'connecting {storeys} storeys.')
    elif any(t in INCIDENTAL_USE_TYPES for t in (space_type_a, space_type_b)):
        incidental = (space_type_a if space_type_a in INCIDENTAL_USE_TYPES
                      else space_type_b)
        if sprinklered and incidental in ('general_storage', 'closed_stack', 'refuse'):
            rating = 0.0
            fire_basis = (f'IBC Table 509: a {incidental.replace("_", " ")} over 9.3 m2 '
                          f'needs a one-hour separation *or* a sprinkler in the room. '
                          f'The building is sprinklered, so the alternative applies and '
                          f'the wall carries no rating.')
        else:
            rating = 1.0
            room = incidental.replace('_', ' ')
            if not sprinklered:
                why = ('The building is not sprinklered, so the alternative Table '
                       '509 offers is unavailable.')
            else:
                why = (f'Table 509 offers a sprinkler in lieu for a storage or '
                       f'refuse room; it does not extend to a {room}, so the '
                       f'separation stands.')
            fire_basis = (f'IBC Table 509 incidental use: {room} takes a one-hour '
                          f'separation. {why}')
    elif 'circulation' in (category_a, category_b) and not sprinklered:
        rating, fire_clause = 1.0, 'IBC-1020.1'
        fire_basis = ('IBC Table 1020.1: a corridor serving more than 30 occupants is '
                      'one hour in an unsprinklered building.')
    elif 'circulation' in (category_a, category_b):
        fire_clause = 'IBC-1020.1'
        fire_basis = ('IBC Table 1020.1: a sprinklered Group A or B corridor takes '
                      'no rating.')

    # Acoustics. The higher of the two rooms' own targets, raised beside a noise source.
    target_a = STC_TARGETS.get(space_type_a, (0, ''))
    target_b = STC_TARGETS.get(space_type_b, (0, ''))
    stc, stc_basis = max(target_a, target_b)
    if not stc_basis:
        stc, stc_basis = 35, 'practice: a visual division with no acoustic requirement'
    if any(t in NOISE_SOURCES for t in (space_type_a, space_type_b)):
        source = space_type_a if space_type_a in NOISE_SOURCES else space_type_b
        if stc < 55:
            stc, stc_basis = 55, (f'practice: {source.replace("_", " ")} is a noise '
                                  f'source, so the wall beside it is held higher than '
                                  f'the quiet room would ask on its own')

    # Who may pass.
    if {category_a, category_b} == {'public', 'service'} or 'service' in (category_a,
                                                                         category_b):
        permeability: Permeability = 'controlled_door'
        permeability_basis = ('Constitution access_class: a service zone is reached '
                              'without crossing controlled public space, so the opening '
                              'is a controlled door rather than a threshold.')
    elif 'private' in (category_a, category_b):
        permeability = 'controlled_door'
        permeability_basis = ('Constitution access_class: staff-only, so the opening is '
                              'controlled.')
    elif rating > 0.0:
        permeability = 'door'
        permeability_basis = ('A rated wall needs a rated, self-closing opening; a '
                              'threshold would defeat it.')
    else:
        permeability = 'door'
        permeability_basis = 'An ordinary door between two public rooms.'

    opaque_types = [t for t in (space_type_a, space_type_b)
                    if t in OPAQUE_REQUIRED_TYPES]
    abuse_types = [t for t in (space_type_a, space_type_b)
                   if t in ABUSE_RESISTANT_TYPES]

    return SeparationRequirement(
        fire_rating_hours=rating, fire_basis=fire_basis,
        fire_clause=fire_clause, stc_target=stc,
        stc_basis=stc_basis, permeability=permeability,
        permeability_basis=permeability_basis,
        opaque_required=bool(opaque_types),
        opaque_basis=(f'{opaque_types[0].replace("_", " ")} must not be seen into: '
                      f'security, conservation or simple decency, none of which a '
                      f'fire rating or an STC target expresses.'
                      if opaque_types else ''),
        abuse_resistant=bool(abuse_types),
        abuse_basis=(f'{abuse_types[0].replace("_", " ")} takes trolleys, bins and '
                     f'pallets against its walls; gypsum board on studs is the wrong '
                     f'product there whatever its rating.'
                     if abuse_types else ''))


def select_partition(requirement: SeparationRequirement,
                     *, shaft: bool = False) -> PartitionType:
    """The lightest assembly that meets both the rating and the acoustic target.

    Lightest rather than strongest is the design objective: a two-hour wall where an
    hour is required costs money, takes floor area and is not safer. Where nothing in
    the list satisfies both, the heaviest is returned -- the caller then sees a partition
    that does not meet its target rather than a silent substitution.
    """
    if shaft:
        return BY_ID['PRT-SHAFT-2HR']
    if requirement.abuse_resistant:
        # Masonry is what gets built against a loading bay. Where the acoustic target
        # is above what bare masonry delivers, the answer is masonry with an isolated
        # lining rather than a choice between surviving a trolley and stopping the
        # noise -- a gypsum wall at a loading dock is destroyed in a year.
        for candidate in (BY_ID['PRT-CMU-2HR'], BY_ID['PRT-CMU-ACOUSTIC']):
            if (candidate.fire_rating_hours >= requirement.fire_rating_hours
                    and candidate.stc >= requirement.stc_target):
                return candidate

    candidates = PARTITION_TYPES
    if requirement.opaque_required:
        candidates = tuple(p for p in candidates
                           if p.construction not in ('glazed_screen',
                                                     'demountable'))
    for partition in candidates:
        if (partition.fire_rating_hours >= requirement.fire_rating_hours
                and partition.stc >= requirement.stc_target):
            return partition
    return max(candidates or PARTITION_TYPES,
               key=lambda p: (p.fire_rating_hours, p.stc))


class PartitionRun(BaseModel):
    """One straight length of wall, with an opening in it where one is needed."""

    id: str
    partition_type_id: str
    level_id: str
    x0: float
    y0: float
    x1: float
    y1: float
    height_m: float
    # Door opening measured from the start of the run; None means the run is solid.
    door_at_m: float | None = None
    door_width_m: float = 0.0
    separates: tuple[str, str]
    requirement: SeparationRequirement

    @property
    def length_m(self) -> float:
        return ((self.x1 - self.x0) ** 2 + (self.y1 - self.y0) ** 2) ** 0.5


# IBC 1010.1.1 and ADA 404.2.3: 815 mm clear width through a doorway, which a 915 mm
# leaf delivers once the stop and the open leaf are taken off.
DOOR_LEAF_M = 0.915
DOOR_CLEAR_M = 0.815
