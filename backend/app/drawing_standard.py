"""The drawing template: line weights, tones and line types, and the rules that pick them.

An architectural drawing carries its information in the *hierarchy* of its lines, not in
the lines themselves. A plan is a horizontal cut: what the plane passes through is drawn
heaviest and filled, what lies below it is drawn lighter as it recedes, and what hangs
above it is dashed because it is not there at the height you are standing. Take that
hierarchy away and a plan becomes a uniform-weight diagram that reads as a maze -- every
line equally important, which is the same as none of them being important.

So the weights here are not decoration. They are how the reader is told what is solid,
what is beyond, and what is overhead, and they are the reason a drawing can be understood
at a glance rather than decoded.

Three decisions make this a template rather than a palette:

**Weights are paper dimensions.** A 0.35 mm line is 0.35 mm on the sheet whether the
drawing is at 1:50 or 1:200. Storing weights in model metres would make the same wall
print as a hairline on one drawing and a smear on another, which is why the geometry is
transformed into paper millimetres before anything is stroked, rather than the strokes
being scaled into the model. `Scale` does that conversion in one place.

**The stroke follows from the element's state, not from the emitter.** Nothing calls for
"a heavy black line"; it asks what stroke a cut structural element gets, and the table
answers. A drawing whose weights are chosen at each call site drifts within a single
sheet and cannot be restyled at all.

**Depth is banded, not continuous.** Fading a line smoothly with distance produces a
photograph, not a drawing. Conventional practice sorts what is seen into a few discrete
planes, and the eye reads discrete planes as depth far more reliably than it reads a
gradient.

The weight series is the ISO 128 progression, where each step is about √2 times the last.
That ratio is what makes two adjacent weights distinguishable in print; a finer series
produces pairs a reader cannot tell apart, which is a hierarchy that only exists in the
file.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Literal


# --- line weights ----------------------------------------------------------------
# ISO 128 pen widths in millimetres on paper. Each is roughly √2 times the one below,
# which is the smallest ratio that stays legible as a difference once printed.
class Weight(float, Enum):
    HAIRLINE = 0.13   # hatching, poché texture, the faintest reference
    FINE = 0.18       # dimension lines, leaders, fittings
    THIN = 0.25       # distant beyond-lines, grid
    LIGHT = 0.35      # middle-ground beyond, furniture, secondary edges
    MEDIUM = 0.50     # near beyond, floor edges, the general working weight
    THICK = 0.70      # cut secondary elements: partitions, glazing frames
    HEAVY = 1.00      # cut primary structure and cut ground
    PROFILE = 1.40    # the outline of the whole cut figure, and the ground line


# --- tones -----------------------------------------------------------------------
# Greyscale, 0.0 black to 1.0 white. Sorted the way depth is read: black is the cut,
# and everything behind it steps back through the greys.
class Tone(float, Enum):
    CUT = 0.00
    NEAR = 0.20
    MIDDLE = 0.42
    FAR = 0.60
    DISTANT = 0.74
    GHOST = 0.84      # what is above the cut plane, and other non-present information


# --- line types ------------------------------------------------------------------
# Dash patterns in paper millimetres, so a dash is the same length on every sheet.
class LineType(Enum):
    CONTINUOUS = ()
    DASHED = (3.0, 1.6)              # above the cut plane; hidden but present
    CLOSE_DASHED = (1.6, 1.2)        # overhead at close range, so the two read apart
    DASH_DOT = (7.0, 1.8, 0.6, 1.8)  # grid and centre lines
    DOTTED = (0.5, 1.4)              # below the floor: foundations, buried services
    LONG_DASH = (12.0, 2.4)          # section marks, match lines, the cut's own trace

    def dasharray(self, scale_factor: float = 1.0) -> str | None:
        """SVG stroke-dasharray in paper millimetres, or None for a solid line."""
        if not self.value:
            return None
        return ' '.join(f'{segment * scale_factor:g}' for segment in self.value)


@dataclass(frozen=True)
class Stroke:
    """Everything needed to draw one line, in paper units."""

    weight: Weight
    tone: Tone
    line_type: LineType = LineType.CONTINUOUS

    @property
    def colour(self) -> str:
        value = round(self.tone.value * 255)
        return f'#{value:02x}{value:02x}{value:02x}'

    def lighter(self, steps: int = 1) -> 'Stroke':
        """Step back one depth plane: lighter tone and a thinner line together.

        Tone alone is not enough. A distant edge that keeps its weight still reads as
        near, because the eye takes thickness as proximity before it takes value.
        """
        tones = list(Tone)
        weights = list(Weight)
        tone_index = min(len(tones) - 1, tones.index(self.tone) + steps)
        weight_index = max(0, weights.index(self.weight) - steps)
        return replace(self, tone=tones[tone_index], weight=weights[weight_index])


# --- what the drawing is of ------------------------------------------------------

# Where an element sits relative to the cut plane. This is measured, never declared:
# `drawings.py` derives it from the element's geometry against the plane.
CutState = Literal['cut', 'beyond', 'above', 'below']

# Which system the element belongs to. Kept coarse on purpose -- a drawing that gives
# every subsystem its own weight has no hierarchy left to spend on the cut.
DrawingRole = Literal[
    'primary_structure', 'secondary_structure', 'envelope', 'partition',
    'glazing', 'circulation', 'furniture', 'site', 'grid', 'annotation',
]

# Element kinds to drawing roles. Anything absent is drawn as furniture -- present,
# lightest, and never mistaken for structure.
ROLE_OF_KIND: dict[str, DrawingRole] = {
    'column': 'primary_structure', 'piloti_column': 'primary_structure',
    'primary_beam': 'primary_structure', 'truss_chord': 'primary_structure',
    'brace': 'primary_structure', 'knee_brace': 'primary_structure',
    'outrigger_strut': 'primary_structure', 'shear_wall': 'primary_structure',
    'core_wall': 'primary_structure', 'footing': 'primary_structure',
    'floor_slab': 'primary_structure', 'podium_slab': 'primary_structure',
    'roof_deck': 'primary_structure',
    'secondary_joist': 'secondary_structure', 'heavy_joist': 'secondary_structure',
    'purlin': 'secondary_structure', 'truss_web': 'secondary_structure',
    'clt_panel': 'secondary_structure', 'slab_fascia': 'secondary_structure',
    'wall_panel': 'envelope', 'backing_panel': 'envelope', 'mullion': 'envelope',
    'lattice_mullion': 'envelope', 'frame_expression': 'envelope',
    'external_strut': 'envelope', 'field_carrier': 'envelope',
    'order_jamb': 'envelope', 'screen_fin': 'envelope', 'brise_soleil': 'envelope',
    'spandrel_panel': 'envelope', 'solid_wall_panel': 'envelope',
    'parapet': 'envelope', 'entry_canopy': 'envelope',
    'glazing_panel': 'glazing', 'facet_glazing': 'glazing', 'transom': 'glazing',
    'entrance_door': 'glazing', 'entrance_head': 'envelope',
    'partition': 'partition', 'partition_head': 'partition', 'door': 'partition',
    # A ceiling is cut in section and is the underside of the floor above in
    # plan, so it is drawn with the enclosure rather than with the furniture
    # a plan at this scale drops.
    'ceiling': 'partition',
    'stair_tread': 'circulation', 'stair_stringer': 'circulation',
    'stair_landing': 'circulation', 'stair_half_landing': 'circulation',
    'ramp': 'circulation', 'ramp_landing': 'circulation', 'ramp_curb': 'circulation',
    'railing': 'circulation', 'elevator_shaft': 'circulation',
    'desk': 'furniture', 'seat': 'furniture', 'shelving_run': 'furniture',
    'figure': 'furniture',
    'site_ground': 'site', 'site_step': 'site',
}


# --- the rule table ---------------------------------------------------------------
# What a cut element is drawn with. Everything else is derived from these by stepping
# back through the depth planes, so the whole sheet moves together when one changes.
_CUT_STROKE: dict[DrawingRole, Stroke] = {
    'primary_structure': Stroke(Weight.HEAVY, Tone.CUT),
    'secondary_structure': Stroke(Weight.THICK, Tone.CUT),
    'envelope': Stroke(Weight.THICK, Tone.CUT),
    'partition': Stroke(Weight.THICK, Tone.CUT),
    # Light enough to sit below solid wall, heavy enough to enclose. At LIGHT the
    # perimeter of a curtain-walled plan dissolved into a dotted line of mullions
    # with nothing between them, and the plan stopped reading as a room.
    'glazing': Stroke(Weight.MEDIUM, Tone.CUT),
    'circulation': Stroke(Weight.MEDIUM, Tone.CUT),
    'furniture': Stroke(Weight.LIGHT, Tone.NEAR),
    'site': Stroke(Weight.HEAVY, Tone.CUT),
    'grid': Stroke(Weight.THIN, Tone.FAR, LineType.DASH_DOT),
    'annotation': Stroke(Weight.FINE, Tone.NEAR),
}

# Poché: the fill inside a cut solid. Solid black for small sections reads as a blot at
# 1:50, so the heavier systems take a dense grey and glazing takes none at all.
_POCHE: dict[DrawingRole, Tone | None] = {
    'primary_structure': Tone.CUT,
    'secondary_structure': Tone.NEAR,
    'envelope': Tone.NEAR,
    'partition': Tone.MIDDLE,
    'glazing': None,
    'circulation': Tone.FAR,
    'furniture': None,
    'site': Tone.MIDDLE,
    'grid': None,
    'annotation': None,
}


@dataclass(frozen=True)
class Scale:
    """A drawing scale, and the one place model metres become paper millimetres.

    Weights are paper dimensions and geometry is in metres, so exactly one of the two
    has to cross over. Converting the geometry keeps every stroke in the units it was
    specified in; converting the weights instead would mean re-deriving them per
    drawing and losing the guarantee that a 0.35 line is 0.35 on every sheet.
    """

    denominator: int

    @property
    def name(self) -> str:
        return f'1:{self.denominator}'

    def to_paper_mm(self, metres: float) -> float:
        return metres * 1000.0 / self.denominator

    def to_metres(self, paper_mm: float) -> float:
        return paper_mm * self.denominator / 1000.0

    @property
    def detail_level(self) -> int:
        """How much may be drawn. Smaller scales must shed information or they blacken.

        2 draws everything, 1 drops furniture and fittings, 0 keeps structure and
        enclosure only. A 1:200 plan carrying every chair is not a more informative
        drawing; it is a grey field with a building somewhere inside it.
        """
        if self.denominator <= 50:
            return 2
        if self.denominator <= 100:
            return 1
        return 0


# What is worth showing dashed above the cut. A plan shows overhead work so the
# reader knows what is over their head -- a beam they duck under, a canopy, a void.
# It does not show the joists: at 1:100 every joist in the ceiling above turns the
# plan into a hatch pattern, and the one piece of information dashing carries -- "this
# is above you" -- is lost in it.
OVERHEAD_ROLES: set[DrawingRole] = {
    'primary_structure', 'envelope', 'circulation',
}


# Roles that survive each detail level, coarsest first.
_ROLES_AT_LEVEL: dict[int, set[DrawingRole]] = {
    0: {'primary_structure', 'envelope', 'partition', 'glazing', 'circulation',
        'site', 'grid', 'annotation'},
    1: {'primary_structure', 'secondary_structure', 'envelope', 'partition',
        'glazing', 'circulation', 'site', 'grid', 'annotation'},
    2: {'primary_structure', 'secondary_structure', 'envelope', 'partition',
        'glazing', 'circulation', 'furniture', 'site', 'grid', 'annotation'},
}


@dataclass(frozen=True)
class DrawingStandard:
    """The template. One instance governs a whole sheet."""

    scale: Scale
    # How many depth planes the beyond-view is sorted into before everything further
    # is drawn at the same faintest weight.
    depth_planes: int = 3

    def role_of(self, kind: str) -> DrawingRole:
        return ROLE_OF_KIND.get(kind, 'furniture')

    def draws(self, role: DrawingRole) -> bool:
        return role in _ROLES_AT_LEVEL[self.scale.detail_level]

    def stroke(self, role: DrawingRole, state: CutState, depth_band: int = 0) -> Stroke:
        """The stroke for an element in this state, at this depth behind the cut.

        Everything is derived from the cut stroke so the sheet keeps one hierarchy:
        a change to how cut structure is drawn moves its beyond-lines with it.
        """
        base = _CUT_STROKE[role]
        if state == 'cut':
            return base
        if state == 'above':
            # Overhead: present, but not at the height of the cut. Dashed and pale,
            # and never heavy enough to be confused with something you could touch.
            line = LineType.CLOSE_DASHED if depth_band <= 0 else LineType.DASHED
            return replace(base.lighter(2), line_type=line, weight=Weight.THIN)
        if state == 'below':
            return replace(base.lighter(3), line_type=LineType.DOTTED,
                           weight=Weight.FINE)
        # 'beyond': step back one plane per band, then hold at the faintest.
        return base.lighter(1 + min(depth_band, self.depth_planes))

    def poche(self, role: DrawingRole) -> Tone | None:
        return _POCHE[role]

    def band_for(self, distance_m: float, spread_m: float) -> int:
        """Which depth plane something `distance_m` behind the cut belongs to.

        Banded rather than continuous: discrete planes read as depth, a gradient reads
        as haze. The bands are spread over the actual depth of what is visible, so a
        deep section and a shallow one both use the full range.
        """
        if spread_m <= 1e-6:
            return 0
        share = max(0.0, min(1.0, distance_m / spread_m))
        return min(self.depth_planes, int(share * (self.depth_planes + 1)))


# The two standards this pipeline issues drawings at. A plan of a whole floor fits a
# sheet at 1:100; a section through the building is read at the same scale so the two
# can be laid up together and measured against each other.
PLAN_STANDARD = DrawingStandard(scale=Scale(100))
SECTION_STANDARD = DrawingStandard(scale=Scale(100))
DETAIL_STANDARD = DrawingStandard(scale=Scale(50))


def export_profile(standard: DrawingStandard) -> dict:
    """The template, in a form Blender can apply.

    The drawing's appearance is decided here and nowhere else. Blender does the
    geometry it is better at -- solidifying, cutting, resolving occlusion and edge
    types -- and reads this for every weight, grey and dash. Two renderers deciding
    their own line weights would be two drawing standards wearing one name.
    """
    roles = dict(ROLE_OF_KIND)
    strokes: dict[str, dict] = {}
    for role in sorted({*roles.values(), 'grid', 'annotation'}):
        cut = standard.stroke(role, 'cut')
        strokes[role] = {
            'weight_mm': cut.weight.value,
            'grey': cut.tone.value,
            'dash_mm': list(cut.line_type.value),
            'poche_grey': (None if standard.poche(role) is None
                           else standard.poche(role).value),
            'beyond': [
                {'weight_mm': standard.stroke(role, 'beyond', band).weight.value,
                 'grey': standard.stroke(role, 'beyond', band).tone.value}
                for band in range(standard.depth_planes + 1)
            ],
        }
    return {
        'schema_version': 'mta.drawing_profile/1.0',
        'scale': standard.scale.name,
        'scale_denominator': standard.scale.denominator,
        'detail_level': standard.scale.detail_level,
        'roles': roles,
        'drawn_roles': sorted(role for role in strokes if standard.draws(role)),
        'strokes': strokes,
    }
