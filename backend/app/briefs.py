"""Four building types, and the briefs that make them different buildings.

`LIBRARY_BRIEF` was the only brief, and `compiler_v3` passed it on every run:

    compiler_v3.py:949   allocate_program(lattice, datums, LIBRARY_BRIEF)

`coupling.py` already screened four programs -- library, museum, theatre, pavilion --
so the screening layer had been asking a question about a typology the compiler could
not build. This module supplies the missing three.

A brief is not a style. Two libraries in different grammars are the same building
differently dressed; a theatre and a pavilion are different buildings before anything is
drawn, because a room that seats four hundred people facing one direction and a single
daylit hall have different depths, different level counts and different structure. That
is why typology belongs in this goal alongside massing: it changes the plan, and the
plan changes everything downstream of it.

**A note on where typology comes from.** Normally a client hands the architect a brief;
it is not a property of a piece of music, and choosing one from an MP3 is a stronger
claim than choosing a facade grammar from one. This project makes that claim
deliberately and says so here rather than burying it: the typology is selected from the
score, the reasoning is recorded in words on every model, and the mapping is stated so a
reader can disagree with it. What is *not* claimed is that the music knows the building
should be a theatre. What is claimed is that a piece organised around one dominant event
in a single continuous span has more in common with a theatre than with a library, and
that this is a defensible way to pick which brief to test the geometry against.

The briefs are sized so the smallest fits a pavilion footprint and the largest needs a
real stack, which is what makes `ProgramAllocation.fits` mean something across the set
instead of failing on everything but the slab.
"""

from __future__ import annotations

from typing import Literal

from .program import SpaceRequirement

TypologyId = Literal['library', 'museum', 'theater', 'pavilion']


MUSEUM_BRIEF: tuple[SpaceRequirement, ...] = (
    SpaceRequirement(
        id='SP-ATRIUM', space_type='lobby_welcome_checkout', label='Entrance atrium',
        category='circulation', area_m2=260.0, min_dimension_m=10.0,
        level_preference='ground', daylight='required',
        occupancy_id='lobby_first_corridor', adjacency=['SP-GALLERY-A', 'SP-SHOP'],
        reason='A museum sells the vertical circulation as the first exhibit; the '
               'atrium has to hold the crowd that arrives together.'),
    SpaceRequirement(
        id='SP-SHOP', space_type='cafe', label='Shop and cafe',
        category='public', area_m2=150.0, min_dimension_m=6.0,
        level_preference='ground', daylight='required',
        occupancy_id='assembly_movable_seats', adjacency=['SP-ATRIUM'],
        reason='Retail on the free side of the ticket line.'),
    SpaceRequirement(
        id='SP-GALLERY-A', space_type='exhibition_foyer', label='Permanent gallery',
        category='public', area_m2=520.0, min_dimension_m=11.0,
        level_preference='high', daylight='none',
        occupancy_id='assembly_movable_seats', adjacency=['SP-GALLERY-B'],
        reason='The largest single room in the building, and the reason its structure '
               'wants long spans: a gallery broken by columns is a corridor.'),
    SpaceRequirement(
        id='SP-GALLERY-B', space_type='exhibition_foyer', label='Temporary gallery',
        category='public', area_m2=380.0, min_dimension_m=10.0,
        level_preference='high', daylight='none',
        occupancy_id='assembly_movable_seats', adjacency=['SP-GALLERY-A'],
        reason='Changing shows need a room that can be re-partitioned without touching '
               'the permanent collection.'),
    SpaceRequirement(
        id='SP-STUDY', space_type='seminar', label='Study and seminar',
        category='public', area_m2=170.0, min_dimension_m=6.0,
        level_preference='high', daylight='preferred',
        occupancy_id='library_reading', adjacency=[],
        reason='Teaching space attached to the collection.'),
    SpaceRequirement(
        id='SP-CONSERVATION', space_type='staff_workroom', label='Conservation studio',
        category='private', area_m2=190.0, min_dimension_m=6.5,
        level_preference='any', daylight='preferred',
        occupancy_id='office', adjacency=['SP-STORE'],
        reason='Works arrive, are treated and are stored without crossing a public '
               'route.'),
    SpaceRequirement(
        id='SP-STORE', space_type='closed_stack', label='Collection store',
        category='service', area_m2=300.0, min_dimension_m=6.0,
        level_preference='any', daylight='none',
        occupancy_id='library_stacks', adjacency=['SP-CONSERVATION'],
        reason='Dense storage. The heaviest floor load in the building and the reason '
               'the column stack is not sized on the galleries alone.'),
    SpaceRequirement(
        id='SP-PLANT-M', space_type='plant', label='Plant and services',
        category='service', area_m2=140.0, min_dimension_m=5.0,
        level_preference='any', daylight='none',
        occupancy_id='library_stacks', adjacency=[],
        reason='Close environmental control is what a collection actually needs. '
               'ASCE 7 has no mechanical-room entry in this project, so the '
               'heaviest published occupancy stands in for the plant load.'),
)


# The three rooms a theatre is. They carried `exhibition_foyer` and
# `lobby_welcome_checkout` -- generic types borrowed from the library brief -- which
# made every downstream reader treat an auditorium as a gallery: the plans labelled two
# different rooms "Exhibition Foyer", and the acoustic separation between the house and
# the foyer was chosen from a gallery's target. A type is what the rest of the pipeline
# reasons from, so a room whose type is a lie is a room nothing downstream can get right.
THEATER_BRIEF: tuple[SpaceRequirement, ...] = (
    SpaceRequirement(
        id='SP-FOYER', space_type='theatre_foyer', label='Foyer',
        category='circulation', area_m2=330.0, min_dimension_m=9.0,
        level_preference='ground', daylight='preferred',
        occupancy_id='lobby_first_corridor', adjacency=['SP-AUDITORIUM', 'SP-BAR'],
        reason='The whole audience arrives and leaves within ten minutes, twice a '
               'night. The foyer is sized by that, not by average occupancy.'),
    SpaceRequirement(
        id='SP-BAR', space_type='cafe', label='Bar',
        category='public', area_m2=160.0, min_dimension_m=6.0,
        level_preference='ground', daylight='preferred',
        occupancy_id='assembly_movable_seats', adjacency=['SP-FOYER'],
        reason='Interval trade, which is most of a theatre\'s margin.'),
    SpaceRequirement(
        id='SP-AUDITORIUM', space_type='auditorium', label='Auditorium',
        category='public', area_m2=680.0, min_dimension_m=16.0,
        level_preference='ground', daylight='none',
        occupancy_id='assembly_fixed_seats', adjacency=['SP-STAGE'],
        # The sentence below is the tolerance: if this room does not arrive at very
        # nearly its full size the building is not the thing it claims to be, so it
        # is not allowed to be delivered short and averaged away.
        area_tolerance=0.97,
        reason='One room facing one direction, and by far the largest clear span in '
               'the set. A theatre that cannot hold this is not a theatre.'),
    SpaceRequirement(
        id='SP-STAGE', space_type='stage', label='Stage and wings',
        category='private', area_m2=340.0, min_dimension_m=12.0,
        level_preference='ground', daylight='none',
        occupancy_id='stage', adjacency=['SP-AUDITORIUM', 'SP-DRESSING'],
        # Wings are the part that gets cut, and a stage without wings cannot change a
        # scene. Held to its area for the same reason as the house.
        area_tolerance=0.97,
        reason='Performance area with the wings that make a scene change possible.'),
    SpaceRequirement(
        id='SP-DRESSING', space_type='staff_workroom', label='Dressing rooms',
        category='private', area_m2=180.0, min_dimension_m=5.0,
        level_preference='any', daylight='preferred',
        occupancy_id='office', adjacency=['SP-STAGE'],
        reason='Company accommodation with its own route to the stage.'),
    SpaceRequirement(
        id='SP-REHEARSAL', space_type='seminar', label='Rehearsal room',
        category='private', area_m2=220.0, min_dimension_m=9.0,
        level_preference='high', daylight='preferred',
        occupancy_id='assembly_movable_seats', adjacency=[],
        reason='A room the size of the stage, so a rehearsal is not a guess.'),
    SpaceRequirement(
        id='SP-PLANT-T', space_type='plant', label='Plant and services',
        category='service', area_m2=170.0, min_dimension_m=5.0,
        level_preference='any', daylight='none',
        occupancy_id='library_stacks', adjacency=[],
        reason='Ventilating a full house quietly is the hardest service problem '
               'here. Loaded as stack room: no mechanical occupancy is '
               'published in this project and plant floors are heavy.'),
)


PAVILION_BRIEF: tuple[SpaceRequirement, ...] = (
    SpaceRequirement(
        id='SP-HALL', space_type='exhibition_foyer', label='Main hall',
        category='public', area_m2=420.0, min_dimension_m=12.0,
        level_preference='ground', daylight='required',
        occupancy_id='assembly_movable_seats', adjacency=['SP-ENTRY'],
        reason='One daylit volume doing nearly all the work. A pavilion is a room, not '
               'a stack of them.'),
    SpaceRequirement(
        id='SP-ENTRY', space_type='lobby_welcome_checkout', label='Entry and threshold',
        category='circulation', area_m2=120.0, min_dimension_m=6.0,
        level_preference='ground', daylight='required',
        occupancy_id='lobby_first_corridor', adjacency=['SP-HALL'],
        reason='Arrival, sheltered, without a separate lobby volume.'),
    SpaceRequirement(
        id='SP-STUDIO', space_type='seminar', label='Workshop studio',
        category='public', area_m2=180.0, min_dimension_m=7.0,
        level_preference='any', daylight='required',
        occupancy_id='library_reading', adjacency=['SP-HALL'],
        reason='The one enclosed room, so the hall can stay open.'),
    SpaceRequirement(
        id='SP-SERVICE-P', space_type='staff_workroom', label='Service and store',
        category='service', area_m2=110.0, min_dimension_m=4.5,
        level_preference='any', daylight='none',
        occupancy_id='office', adjacency=[],
        reason='Everything the hall needs, kept out of the hall.'),
)


# The program ids, the massing bias and the loading-dock rule moved to
# `typology.KITS`, which assembles one kit per typology from this module and the
# others that own a part, and refuses to assemble a partial one.
BRIEFS: dict[str, tuple[SpaceRequirement, ...]] = {}


def _install() -> None:
    from .program import LIBRARY_BRIEF
    BRIEFS.update({
        'library': LIBRARY_BRIEF,
        'museum': MUSEUM_BRIEF,
        'theater': THEATER_BRIEF,
        'pavilion': PAVILION_BRIEF,
    })


_install()


def brief_for(typology: str, *, storeys: int = 5) -> tuple[SpaceRequirement, ...]:
    """The client's rooms plus the base-building support the constitution requires.

    Splitting these is deliberate: `BRIEFS` is what a client asks for and
    `constitution.support_spaces` is what a building needs in order to open. Keeping
    them apart means a brief can be read as a brief, and joining them here means the
    allocator has to find room for both. Before this, every typology was allocated with
    no restrooms, no janitor's closet, no electrical room and no riser -- 2,770 m2 of
    library with nowhere to wash your hands.
    """
    from .constitution import support_spaces

    base = BRIEFS[typology]
    return tuple(base) + tuple(support_spaces(typology, base, storeys=storeys))


def choose_typology(reading: dict[str, float], density: float,
                    massing_id: str) -> tuple[str, list[str]]:
    """Pick which brief the geometry is tested against, and say why.

    The massing is decided first and constrains this, which is the right order: a
    single-volume pavilion cannot hold a museum's store and a bar on a podium is not a
    pavilion. Where the massing has already settled the question the reasoning says so
    rather than pretending an independent decision was made.
    """
    why: list[str] = []
    if massing_id == 'MAS-PAVILION':
        why.append('the massing is a single low volume, which only the pavilion brief '
                   'fits; no further reading is needed')
        return 'pavilion', why
    if massing_id == 'MAS-SPLIT':
        why.append('a mass broken in plan with the entrance in the break is a foyer '
                   'building: the theatre brief is the one that uses that arrival')
        return 'theater', why

    incident = reading['incident']
    layering = reading['layering']
    if incident >= 0.62:
        why.append(f'incident {incident:.2f}: the piece is organised around one '
                   f'dominant event, which is what an auditorium is')
        return 'theater', why
    if layering >= 0.60 and density < 0.55:
        why.append(f'layering {layering:.2f} over a sparse texture (density '
                   f'{density:.2f}): sequenced rooms entered one after another, which '
                   f'is a gallery sequence rather than an open floor')
        return 'museum', why
    why.append(f'no decisive reading toward a single room or a sequence of them '
               f'(incident {incident:.2f}, layering {layering:.2f}): the stacked '
               f'reading floors of a library')
    return 'library', why
