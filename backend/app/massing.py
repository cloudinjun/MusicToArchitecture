"""Massing families: the silhouette, before any skin is put on it.

The tectonic work made fourteen recordings produce six facade grammars and two frames,
and rendering them side by side showed the limit of that immediately. The eye reads
massing first. Every one of the fourteen was the same thirty-six by twenty-two metre
slab, six storeys, cut away on the same two faces, so the sheet said "same building,
different cladding" before a viewer got as far as the wall.

The cause was the same shape of mistake as `STRUCTURAL_SYSTEM_ID`, one layer down:

    datums.py:285   PLAN_X_MIN, PLAN_X_MAX = -14.0, 22.0
    datums.py:286   PLAN_Y_MIN, PLAN_Y_MAX = -11.0, 11.0

Module constants. Cantilever, step-back, rotation and apse radius were all score-driven,
but they were perturbations of one footprint that no recording could change. A building
that is twenty metres square and nine storeys and one that is forty-six metres long and
three are not the same building at two settings; they are different buildings, and no
amount of moving a cantilever gets from one to the other.

A massing family sets the footprint, how it changes with height, and how many storeys
the score's own level count is scaled to. The families are the silhouettes a mid-rise
public building actually takes, and each is chosen by a question about the music that a
reader can disagree with in words rather than in coefficients.

The level lattice still underlies all of them. A family that needed a different skeleton
-- a true tower with a structural core, a shell -- is not here, for the same reason the
shells are absent from `tectonics.py`: this compiler indexes elements into stacked
levels, and pretending otherwise would produce a picture rather than a model.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MassingId = Literal[
    'MAS-SLAB', 'MAS-TOWER', 'MAS-COURTYARD', 'MAS-ZIGGURAT',
    'MAS-BAR-PODIUM', 'MAS-SPLIT', 'MAS-PAVILION',
]

# How the plate changes as it goes up.
#
#   uniform     every plate the same, give or take the score's cantilever
#   stepped     each plate loses a band from one end -- a ziggurat read
#   tapered     each plate insets on every side, so the mass narrows as it rises
#   podium_bar  a broad two-storey base with a narrow bar standing on it
#   split       two lobes joined only at the podium
Profile = Literal['uniform', 'stepped', 'tapered', 'podium_bar', 'split']


class MassingFamily(BaseModel):
    """One silhouette, as the numbers the lattice needs to build it."""

    id: MassingId
    label: str
    # Footprint of the podium, in metres. The score modulates this within
    # `plan_tolerance`; it cannot move between families.
    plan_x_m: float = Field(gt=0)
    plan_y_m: float = Field(gt=0)
    plan_tolerance: float = Field(default=0.18, ge=0.0, le=0.5)

    profile: Profile
    # Multiplies the score's own level count, then `level_floor` is the hard minimum.
    # A pavilion is one or two storeys however busy the music; a tower is not a tower
    # at four.
    level_factor: float = Field(gt=0)
    level_floor: int = Field(ge=1)
    level_ceiling: int = Field(ge=1)

    # `stepped` and `tapered` remove this share of the plate per level above the second.
    step_share: float = Field(default=0.0, ge=0.0, le=0.35)
    # `podium_bar`: the bar's footprint as a share of the podium's.
    bar_share: float = Field(default=0.55, gt=0.0, le=1.0)
    # `split`: the gap between the two lobes, as a share of the long dimension.
    gap_share: float = Field(default=0.0, ge=0.0, le=0.4)
    # A void through every occupied plate, as a share of the footprint.
    courtyard_share: float = Field(default=0.0, ge=0.0, le=0.5)
    # Whether the west end is rounded. A square end reads as a different building even
    # when nothing else changes, so it belongs to the family and not to a datum.
    west_apse: bool = True

    note: str


MASSING_FAMILIES: dict[str, MassingFamily] = {
    m.id: m for m in (
        MassingFamily(
            id='MAS-SLAB', label='Stacked slab',
            plan_x_m=36.0, plan_y_m=22.0, profile='uniform',
            level_factor=1.0, level_floor=4, level_ceiling=8,
            west_apse=True,
            note='The default public block: a broad plate repeated, rounded at the west '
                 'end. It is what the project built for every recording before the '
                 'families existed, and it stays as the answer for music that is not '
                 'decisive about anything else.'),

        MassingFamily(
            id='MAS-TOWER', label='Compact tower',
            plan_x_m=21.0, plan_y_m=18.0, profile='tapered',
            level_factor=2.0, level_floor=8, level_ceiling=15,
            # 4.5 % a side per level over nine storeys left the top plate at 28 % of
            # the base, which is not a floor anyone can use -- the stair could not
            # fit on it, and neither could a room. A tower narrows; it does not
            # taper to a spire.
            step_share=0.018, west_apse=False,
            note='A small footprint taken up. Dense, continuous music earns the compact '
                 'plan and the height; the slight taper keeps the columns stacking '
                 'while the silhouette still narrows.'),

        MassingFamily(
            id='MAS-COURTYARD', label='Courtyard block',
            plan_x_m=44.0, plan_y_m=32.0, profile='uniform',
            level_factor=0.8, level_floor=3, level_ceiling=6,
            courtyard_share=0.26, west_apse=False,
            note='A broad ring around a void. The interruption goes through the middle '
                 'of the plan rather than up the section, which is a different way of '
                 'breaking a building and reads as one from every angle.'),

        MassingFamily(
            id='MAS-ZIGGURAT', label='Stepped terraces',
            plan_x_m=46.0, plan_y_m=27.0, profile='stepped',
            level_factor=1.15, level_floor=5, level_ceiling=9,
            step_share=0.13, west_apse=True,
            note='Every plate loses a band from the east end, so the section is a '
                 'stair. Music that refuses to stay continuous gets a mass that refuses '
                 'to repeat.'),

        MassingFamily(
            id='MAS-BAR-PODIUM', label='Bar on a podium',
            plan_x_m=48.0, plan_y_m=27.0, profile='podium_bar',
            level_factor=1.25, level_floor=5, level_ceiling=10,
            bar_share=0.46, west_apse=False,
            note='Two elements with an argument between them: a broad low base and a '
                 'narrow bar standing on it. A piece with one dominant voice over a '
                 'steady ground gets the same relationship in plan.'),

        MassingFamily(
            id='MAS-SPLIT', label='Split mass',
            plan_x_m=50.0, plan_y_m=22.0, profile='split',
            level_factor=1.0, level_floor=4, level_ceiling=8,
            gap_share=0.17, west_apse=False,
            note='Two masses joined only at the podium. The most literal reading of an '
                 'interrupted piece with a dominant event: the building is broken in '
                 'plan and the break is the entrance.'),

        MassingFamily(
            id='MAS-PAVILION', label='Single volume pavilion',
            plan_x_m=40.0, plan_y_m=30.0, profile='uniform',
            level_factor=0.34, level_floor=2, level_ceiling=3,
            west_apse=True,
            note='Broad and almost flat. Sparse, open music does not earn six storeys, '
                 'and forcing them on it is how every recording ended up the same '
                 'height in the first place.'),
    )
}


def choose_massing(reading: dict[str, float], density: float,
                   tempo: float) -> tuple[MassingFamily, list[str]]:
    """Pick a silhouette, and say why in words rather than in coefficients.

    The order of the questions is the order an architect would ask them: is the mass
    broken at all, is one part of it dominant, does it repeat, and only then how tall
    and how compact. Each branch is a claim about the music that can be argued with.

    `reading` carries the four axes `selection.read_axes` produced; `density` and
    `tempo` come straight off the score, because compactness and storey count are
    questions those two dimensions answer more directly than any axis does.
    """
    incident = reading['incident']
    layering = reading['layering']
    regularity = reading['regularity']
    mass = reading['mass']
    why: list[str] = []

    # The two thresholds below used to be 0.62 and 0.42, which left the ziggurat a
    # window 0.04 wide: anything under 0.38 was already a courtyard or a split, so
    # the stepped family fired almost never. A branch that narrow is a dead leaf
    # wearing a condition, and the reachability sweep in the tests is there to catch
    # exactly that.
    interruption = 1.0 - regularity
    if interruption >= 0.68 and incident >= 0.55:
        why.append(f'nothing returns on a period (regularity {regularity:.2f}) and one '
                   f'event dominates (incident {incident:.2f}): the mass is broken in '
                   f'plan and the break becomes the entrance')
        return MASSING_FAMILIES['MAS-SPLIT'], why
    if interruption >= 0.68:
        why.append(f'regularity {regularity:.2f} is low with no single dominant event: '
                   f'the interruption goes through the middle of the plan as a void '
                   f'rather than up the section')
        return MASSING_FAMILIES['MAS-COURTYARD'], why
    if incident >= 0.66:
        why.append(f'incident {incident:.2f}: one dominant voice over a steady ground, '
                   f'which in plan is a narrow bar standing on a broad base')
        return MASSING_FAMILIES['MAS-BAR-PODIUM'], why
    if regularity < 0.48:
        why.append(f'regularity {regularity:.2f}: material that will not repeat gets a '
                   f'section that will not repeat either, so every plate steps back')
        return MASSING_FAMILIES['MAS-ZIGGURAT'], why
    if density >= 0.58 and mass >= 0.40:
        why.append(f'density {density:.2f} with mass {mass:.2f}: dense and weighty '
                   f'material earns a compact footprint taken up rather than out')
        return MASSING_FAMILIES['MAS-TOWER'], why
    if density < 0.34 or tempo < 0.22:
        why.append(f'density {density:.2f} and tempo of change {tempo:.2f} are both '
                   f'low: sparse material does not earn six storeys, and forcing them '
                   f'on it is what made every recording the same height')
        return MASSING_FAMILIES['MAS-PAVILION'], why
    why.append('no reading is decisive enough to leave the default: a broad plate '
               'repeated, rounded at the west end')
    return MASSING_FAMILIES['MAS-SLAB'], why


def level_count_for(family: MassingFamily, score_levels: int) -> int:
    """Scale the score's storey count into the family's own band."""
    scaled = round(score_levels * family.level_factor)
    return max(family.level_floor, min(family.level_ceiling, scaled))
