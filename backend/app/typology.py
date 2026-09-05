"""One kit per typology, and a registry a half-added typology cannot get past.

Adding a typology touches four files: the brief and its program id in `briefs.py`, the
structural demand row in `coupling.py`, the loading-dock rule in `constitution.py`, the
massing bias beside the briefs. The *definitions* are scattered on purpose -- each sits
next to the code that reasons about it, and moving the structural demand away from the
screen that reads it would cost more than it saves. What was wrong is that the sites
failed differently when one was missed: a missing brief raises at once, a missing
demand row raises only when a run reaches the screen, a missing massing bias is silent
because nothing consumes it yet, and a missing loading-dock rule is silent because a
membership test does not know what it has never heard of. Two silent failures out of
four is how the theatre ran for a goal and a half with a gallery's room types before
anyone noticed.

So the kit is the *lookup*, not the home. `KITS` is assembled once at import from the
modules that own each part, and the assembly raises naming the typology and the missing
part rather than serving a kit with a hole in it. A typology you can look up is a
typology that is whole; one you cannot is a loud error at import, not a quiet gap at
allocation. This is the seam the ten-typology expansion grows through: a new typology
is one entry in `_SPECS` plus the parts the build demands, and the build enumerates
exactly what is still owed.

Two facts live here directly because they had no principled home elsewhere. The massing
bias -- which silhouette a typology asks for when the music has not been decisive -- sat
in `briefs.py` with no consumer, which is precisely the silent-failure mode this module
exists to end; it is kept, still unconsumed, but now a stated part of the kit that a
future selector can read. The loading-dock rule sat as a membership test inside
`constitution.support_spaces`, which is a typology fact hiding in a support-space
generator.
"""

from __future__ import annotations

from typing import get_args

from pydantic import BaseModel

from .briefs import BRIEFS, TypologyId
from .coupling import ProgramDemand, program_by_id
from .massing import MASSING_FAMILIES
from .program import SpaceRequirement


class TypologyKit(BaseModel):
    """Everything the pipeline holds about one typology, gathered behind one id.

    The brief and the demand are references to their home modules, not copies: editing
    `THEATER_BRIEF` edits this kit. Only `massing_bias` and `requires_loading_dock`
    are defined here, because this is now their home.
    """

    id: TypologyId
    program_id: str
    brief: tuple[SpaceRequirement, ...]
    # The massing a typology asks for when the music has not already been decisive. A
    # theatre wants one large uninterrupted volume; a museum wants a stacked block with
    # deep, daylight-free rooms; a pavilion is a pavilion. No selector consumes this
    # yet: `select_massing` lets the score lead unconditionally, and whether the bias
    # should temper that is an open question for the ten-typology round.
    massing_bias: str
    demand: ProgramDemand
    # Whether the base building needs a dock: a direct service route to the stage or
    # the collection. A library receives books through a workroom and a pavilion has
    # nothing to load, so neither carries the 36 m2 a dock reserves at ground.
    requires_loading_dock: bool
    # The type-specific space the band allocator cannot invent -- an auditorium bowl,
    # a stacked archive, a wet sequence. None means the typology is entirely the
    # allocator's, which is what every typology was before decision 0016. The id names
    # a carver in `archetypes.py`, which runs before allocation and hands the
    # allocator what is left.
    archetype: str | None = None

    @property
    def occupancy_group(self) -> str:
        return self.demand.occupancy_group


# program id, massing bias, loading dock, archetype. The brief comes from
# `briefs.BRIEFS` and the demand from `coupling.PROGRAM_DEMANDS`, both looked up --
# and insisted upon -- by `_build`.
_SPECS: dict[str, tuple[str, str, bool, str | None]] = {
    'library': ('PRG-LIBRARY-MID-RISE', 'MAS-SLAB', False, 'ARCH-READING-ROOM'),
    'museum': ('PRG-MUSEUM-MID-RISE', 'MAS-COURTYARD', True,
               'ARCH-GALLERY-SEQUENCE'),
    # The theatre's bias was MAS-BAR-PODIUM -- one large volume beside a low base --
    # until the bowl archetype measured the pairing: the bar stands centred exactly
    # where the house must be, so the house's clear height guts the bar's floors and
    # strands every room on them. The carver refuses that pairing (see
    # `archetypes.carve_theatre`), and a bias toward a massing the typology's own
    # archetype refuses is not a bias, it is a trap. The slab's full-width plates
    # give the bowl its section and keep their remainders; the bar-podium comes back
    # when the fly tower gives it a reason (decision 0016).
    'theater': ('PRG-THEATER-MID-RISE', 'MAS-SLAB', True, 'ARCH-THEATRE-BOWL'),
    'pavilion': ('PRG-PAVILION-SINGLE-VOLUME', 'MAS-PAVILION', False, 'ARCH-HALL'),
}


def _build() -> dict[str, TypologyKit]:
    """Assemble the kits, refusing to assemble a partial one.

    Every check here is a failure mode that was possible before: a typology in the
    Literal with no spec, a spec for a typology the Literal does not name, a brief that
    was never installed, a program id with no demand row, a massing bias naming a
    family that does not exist. Each raises naming the typology and the part, because
    "KeyError: 'transit_hub'" three modules downstream is the experience this module
    replaces.
    """
    declared = set(get_args(TypologyId))
    if set(_SPECS) != declared:
        raise LookupError(
            f'typology specs and TypologyId disagree: specs without a Literal entry '
            f'{sorted(set(_SPECS) - declared)}, Literal entries without a spec '
            f'{sorted(declared - set(_SPECS))}')

    kits: dict[str, TypologyKit] = {}
    for typology, (program_id, massing_bias, loading_dock,
                   archetype) in _SPECS.items():
        brief = BRIEFS.get(typology)
        if not brief:
            raise LookupError(f'typology {typology!r} has no brief in briefs.BRIEFS')
        try:
            demand = program_by_id(program_id)
        except KeyError as exc:
            raise LookupError(
                f'typology {typology!r} names {program_id!r} but coupling has no '
                f'demand row for it') from exc
        if massing_bias not in MASSING_FAMILIES:
            raise LookupError(
                f'typology {typology!r} asks for massing {massing_bias!r}, which is '
                f'not a massing family')
        if archetype is not None:
            from .archetypes import _CARVERS
            if archetype not in _CARVERS:
                raise LookupError(
                    f'typology {typology!r} names archetype {archetype!r}, which '
                    f'has no carver in archetypes._CARVERS')
        kits[typology] = TypologyKit(
            id=typology, program_id=program_id, brief=tuple(brief),
            massing_bias=massing_bias, demand=demand,
            requires_loading_dock=loading_dock, archetype=archetype)
    return kits


KITS: dict[str, TypologyKit] = _build()


def kit_for(typology: str) -> TypologyKit:
    try:
        return KITS[typology]
    except KeyError:
        raise KeyError(f'unknown typology {typology!r}; kits exist for '
                       f'{sorted(KITS)}') from None
