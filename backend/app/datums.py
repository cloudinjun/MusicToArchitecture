"""Score -> datums -> registration lattice.

This is the inversion decision 0008 asked for. The v2 compiler positioned every element
from a literal in `LIBRARY_SPACE_SPECS`, so the score could only rescale a fixed plan and
every MP3 produced the same building. Here the chain runs the other way:

    architectural_score.json   up to 10 dimensions, four of them currently observed
            |
            v
    DatumSet                   ~15 scalars, each recording which dimension drove it,
            |                  the formula, the range, and its provenance
            v
    Lattice                    level table x grid lines x plate polygons x voids
            |
            v
    elements                   every element indexes into the lattice; no element
                               anywhere carries an absolute coordinate literal

Honesty rule carried through the whole module: a datum whose driving dimension is not
present in the score is **not** silently defaulted. It records
`provenance='design_fixture'` and names the dimension it is waiting for, so
`mapping_report.py` can report real coverage instead of an inflated one.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Literal

from .massing import (
    MASSING_FAMILIES, MassingFamily, level_count_for,
)

from pydantic import BaseModel, Field

from .geometry import (
    Vector2, point_inside, resample_by_arclength, superellipse, v2,
)
# Type-only. `models` imports `translation_report`, which imports this module, so a
# runtime import here closes a cycle that resolves only when `models` happens to be
# the module that enters it first. Every entry point used to satisfy that by luck;
# `selection.py` was the first one that did not, and pytest importing a single test
# module was the second. `from __future__ import annotations` makes the annotation
# on `compile_datum_set` lazy, so the import is not needed at runtime at all.
if TYPE_CHECKING:  # pragma: no cover
    from .models import ArchitecturalScore

DatumProvenance = Literal['score_driven', 'design_fixture', 'tectonic_constant']


FULL_CONFIDENCE = 0.75


def confidence_factor(confidence: float) -> float:
    """How much of its declared range a dimension is allowed to travel.

    A dimension measured at 0.35 confidence -- `genre_style` is inferred from timbre, not
    classified by a trained model -- must not be permitted to swing an architectural
    decision from one end of its range to the other. It is clamped toward the middle of
    the range in proportion to how well it is known, so a weak reading nudges and a
    strong one commits. The alternative, letting every dimension move its full range
    regardless of evidence, would make the mapping report a fiction.
    """
    return min(1.0, max(0.0, confidence) / FULL_CONFIDENCE)


class Datum(BaseModel):
    """One scalar, and the complete story of where it came from."""

    id: str
    value: float
    unit: str
    provenance: DatumProvenance
    driving_dimension: str | None = None
    dimension_value: float | None = None
    dimension_confidence: float | None = None
    applied_position: float | None = None
    output_range: tuple[float, float] | None = None
    rule_id: str
    reason: str

    @property
    def score_driven(self) -> bool:
        return self.provenance == 'score_driven'

    @property
    def clamped(self) -> bool:
        return (self.dimension_confidence is not None
                and self.dimension_confidence < FULL_CONFIDENCE)


class DatumSet(BaseModel):
    schema_version: Literal['mta.datum_set/1.0'] = 'mta.datum_set/1.0'
    score_id: str
    datums: list[Datum]

    def value(self, datum_id: str) -> float:
        for datum in self.datums:
            if datum.id == datum_id:
                return datum.value
        raise KeyError(f'unknown datum: {datum_id}')

    def integer(self, datum_id: str) -> int:
        return int(round(self.value(datum_id)))

    def by_id(self, datum_id: str) -> Datum:
        for datum in self.datums:
            if datum.id == datum_id:
                return datum
        raise KeyError(f'unknown datum: {datum_id}')

    @property
    def coverage(self) -> float:
        """Score-driven share of every datum, constants included."""
        driven = sum(1 for d in self.datums if d.score_driven)
        return round(driven / len(self.datums), 4) if self.datums else 0.0

    @property
    def variable_coverage(self) -> float:
        """Score-driven share of the datums music is *allowed* to move.

        Tectonic constants -- slab thickness, riser height, guard height -- are fixed by
        the structural system and the code, not by the brief, so counting them against
        the score understates how much of the design the music actually reaches.
        """
        variables = [d for d in self.datums if d.provenance != 'tectonic_constant']
        driven = sum(1 for d in variables if d.score_driven)
        return round(driven / len(variables), 4) if variables else 0.0

    @property
    def clamped_datums(self) -> list[str]:
        return [d.id for d in self.datums if d.score_driven and d.clamped]

    @property
    def dimensions_used(self) -> list[str]:
        return sorted({d.driving_dimension for d in self.datums
                       if d.score_driven and d.driving_dimension})

    @property
    def waiting_on(self) -> list[str]:
        return sorted({d.driving_dimension for d in self.datums
                       if not d.score_driven and d.driving_dimension})


# ---------------------------------------------------------------------------
# Score -> datums
# ---------------------------------------------------------------------------

def _lerp(low: float, high: float, amount: float) -> float:
    return low + (high - low) * amount


# id, dimension, low, high, unit, rule, reason, fixture value when absent
_DATUM_RULES: tuple[tuple[str, str, float, float, str, str, str, float], ...] = (
    # --- tempo of change ---------------------------------------------------
    ('level_count', 'tempo_of_change', 4, 7, 'levels', 'TEMPO_TO_LEVEL_COUNT',
     'A faster rate of change stacks more distinct occupied floor episodes.', 5),
    # --- tension and release -----------------------------------------------
    ('floor_to_floor_m', 'tension_release', 3.9, 5.4, 'm', 'TENSION_TO_FLOOR_HEIGHT',
     'Released passages get more headroom; compressed ones less.', 4.4),
    ('shading_rows', 'tension_release', 1, 3, 'rows', 'TENSION_TO_SHADING_ROWS',
     'Tension multiplies the south shading comb.', 2),
    ('shading_depth_m', 'tension_release', 0.40, 1.00, 'm', 'TENSION_TO_SHADING_DEPTH',
     'Release deepens the shading projection and the shadow it throws.', 0.70),
    # --- density -----------------------------------------------------------
    ('bay_x_m', 'density', 7.8, 5.6, 'm', 'DENSITY_TO_BAY_X',
     'Denser music tightens the primary structural bay.', 6.6),
    ('bay_y_m', 'density', 8.4, 6.2, 'm', 'DENSITY_TO_BAY_Y',
     'The secondary direction follows the same density, one step wider.', 7.2),
    ('joist_spacing_m', 'density', 2.6, 1.5, 'm', 'DENSITY_TO_JOIST_SPACING',
     'Density sets the tertiary framing rhythm read from below.', 2.0),
    ('transom_rows', 'density', 2, 4, 'rows', 'DENSITY_TO_TRANSOM_ROWS',
     'Density subdivides each storey of the curtain wall.', 3),
    # --- continuity --------------------------------------------------------
    ('cantilever_m', 'continuity', 0.6, 3.6, 'm', 'CONTINUITY_TO_CANTILEVER',
     'Continuous passages push the floor plate past its supports.', 1.6),
    ('apse_radius_m', 'continuity', 8.0, 12.0, 'm', 'CONTINUITY_TO_APSE',
     'Continuity rounds the end of the plate instead of cutting it.', 10.0),
    ('circulation_allowance', 'continuity', 0.16, 0.28, 'fraction',
     'CONTINUITY_TO_CIRCULATION',
     'Continuity keeps more of the plate for uninterrupted routes.', 0.22),
    ('flight_width_m', 'continuity', 1.8, 3.4, 'm', 'CONTINUITY_TO_FLIGHT_WIDTH',
     'A continuous public route carries a wider stair.', 2.4),
    # --- repetition --------------------------------------------------------
    ('mullion_module_m', 'repetition', 1.55, 1.15, 'm', 'REPETITION_TO_MULLION',
     'Repetition fixes the envelope module.', 1.35),
    ('spandrel_height_m', 'repetition', 0.75, 0.40, 'm', 'REPETITION_TO_SPANDREL',
     'A regular piece bands the floor zone tightly and repeatedly.', 0.55),
    ('rail_post_spacing_m', 'repetition', 1.9, 1.1, 'm', 'REPETITION_TO_RAIL_POSTS',
     'The guard post rhythm is the finest repeated element in the model.', 1.5),
    # --- variation ---------------------------------------------------------
    ('plate_step_m', 'variation', 0.0, 3.5, 'm', 'VARIATION_TO_PLATE_STEP',
     'Variation steps the upper plates back from the lower ones.', 2.0),
    ('plate_rotation_deg', 'variation', 0.0, 3.0, 'degrees',
     'VARIATION_TO_PLATE_ROTATION',
     'Each level turns against the one below, so the stack is never a simple extrusion.',
     0.0),
    # --- hierarchy ---------------------------------------------------------
    ('truss_depth_m', 'hierarchy', 1.5, 3.0, 'm', 'HIERARCHY_TO_TRUSS_DEPTH',
     'Hierarchy sets how much the roof structure dominates.', 2.2),
    ('truss_panels', 'hierarchy', 4, 9, 'panels', 'HIERARCHY_TO_TRUSS_PANELS',
     'Hierarchy sets the web rhythm inside the roof truss.', 6),
    ('ground_open_height_m', 'hierarchy', 4.2, 6.0, 'm', 'HIERARCHY_TO_PILOTI',
     'Hierarchy decides how far the mass lifts off the ground.', 5.0),
    ('entry_canopy_span_m', 'hierarchy', 0.0, 9.0, 'm', 'HIERARCHY_TO_ENTRY_CANOPY',
     'A dominant order announces its entrance; a level one does not.', 4.0),
    # --- interruption ------------------------------------------------------
    ('void_count', 'interruption', 0, 3, 'voids', 'INTERRUPTION_TO_VOIDS',
     'Interruption punches atrium voids through the stack.', 1),
    ('void_scale', 'interruption', 0.70, 1.35, 'factor', 'INTERRUPTION_TO_VOID_SCALE',
     'A harder break opens a larger hole in the plate.', 1.0),
    ('terrace_count', 'interruption', 0, 2, 'levels', 'INTERRUPTION_TO_TERRACES',
     'A break strips the envelope from a whole level and makes it a terrace.', 1),
    # --- polyphony ---------------------------------------------------------
    ('envelope_offset_m', 'polyphony', 0.15, 0.90, 'm', 'POLYPHONY_TO_ENVELOPE_OFFSET',
     'Independent voices need separation: the envelope stands off the frame so both '
     'read.', 0.35),
    ('envelope_layer_count', 'polyphony', 1, 3, 'layers', 'POLYPHONY_TO_ENVELOPE_LAYERS',
     'Glazing, then a screen, then a shading comb: one readable layer per voice.', 2),
    ('braced_bay_count', 'polyphony', 2, 6, 'bays', 'POLYPHONY_TO_BRACED_BAYS',
     'More independent lines means the lateral system is expressed more often.', 2),
    # --- genre and style (low confidence; the clamp does the work) ----------
    ('opaque_fraction', 'genre_style', 0.45, 0.10, 'fraction',
     'GENRE_TO_OPAQUE_FRACTION',
     'A timbral position between a heavy panelled envelope and a light glazed one. '
     'Proposed only; a human accepts the weighting.', 0.28),
    ('fin_depth_m', 'genre_style', 0.14, 0.42, 'm', 'GENRE_TO_FIN_DEPTH',
     'The same timbral position sets how far the mullion projects and how hard the '
     'elevation reads.', 0.24),
)

# Fixed by the tectonic system, never by music.
_TECTONIC_CONSTANTS: tuple[tuple[str, float, str, str, str], ...] = (
    ('slab_thickness_m', 0.30, 'm', 'STR-SLAB-THICKNESS',
     'Composite deck and topping depth for the selected steel frame.'),
    ('edge_fascia_m', 0.55, 'm', 'STR-EDGE-FASCIA',
     'Visible plate edge: slab plus edge beam.'),
    ('riser_m', 0.175, 'm', 'CIR-RISER',
     'Stair riser inside the accessible range; sets every flight division.'),
    ('rail_height_m', 1.05, 'm', 'CIR-RAIL-HEIGHT',
     'Guard height; also the primary scale anchor in the model.'),
    ('figure_height_m', 1.75, 'm', 'PRG-FIGURE-HEIGHT',
     'Scale figure. Not architecture, but the reason the rest reads as architecture.'),
)


def compile_datum_set(score: ArchitecturalScore) -> DatumSet:
    available = {dimension.id: (dimension.value, dimension.confidence)
                 for dimension in score.dimensions}
    datums: list[Datum] = []

    for (datum_id, dimension, low, high, unit, rule, reason, fixture) in _DATUM_RULES:
        if dimension in available:
            amount, confidence = available[dimension]
            factor = confidence_factor(confidence)
            applied = 0.5 + (amount - 0.5) * factor
            note = reason
            if factor < 1.0:
                note = (f'{reason} The driving dimension is known at {confidence:.2f} '
                        f'confidence, so the datum travels only {factor:.0%} of its '
                        f'declared range from the midpoint.')
            datums.append(Datum(
                id=datum_id, value=round(_lerp(low, high, applied), 4), unit=unit,
                provenance='score_driven', driving_dimension=dimension,
                dimension_value=amount, dimension_confidence=confidence,
                applied_position=round(applied, 4), output_range=(low, high),
                rule_id=rule, reason=note))
        else:
            datums.append(Datum(
                id=datum_id, value=float(fixture), unit=unit,
                provenance='design_fixture', driving_dimension=dimension,
                output_range=(low, high), rule_id=rule,
                reason=(f'{reason} The score does not yet supply {dimension}, so this '
                        f'datum is a declared design fixture and drives no mapping '
                        f'coverage.')))

    for datum_id, value, unit, rule, reason in _TECTONIC_CONSTANTS:
        datums.append(Datum(
            id=datum_id, value=value, unit=unit, provenance='tectonic_constant',
            rule_id=rule, reason=reason))

    return DatumSet(score_id=score.score_id, datums=datums)


# ---------------------------------------------------------------------------
# Datums -> lattice
# ---------------------------------------------------------------------------

# The footprint the project shipped for every recording, kept as the default so a
# caller that does not choose a massing family gets exactly the old building. It is no
# longer the only footprint: `massing.py` sets one per family, and these four numbers
# are now a fallback rather than a fact about every building this pipeline can make.
PLAN_X_MIN, PLAN_X_MAX = -14.0, 22.0
PLAN_Y_MIN, PLAN_Y_MAX = -11.0, 11.0


class PlanBounds(BaseModel):
    """The footprint one building actually occupies.

    Carried on the lattice so that every consumer -- the emitters, the sectional cut,
    the void seeds -- reads the plan it belongs to instead of a literal. That is the
    same property decision 0008 made for elements, applied to the ground they stand on.
    """

    x_min: float
    x_max: float
    y_min: float
    y_max: float

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def depth(self) -> float:
        return self.y_max - self.y_min

    def fx(self, t: float) -> float:
        """A fraction across the plan, west to east."""
        return self.x_min + self.width * t

    def fy(self, t: float) -> float:
        """A fraction across the plan, south to north."""
        return self.y_min + self.depth * t


DEFAULT_PLAN = PlanBounds(x_min=PLAN_X_MIN, x_max=PLAN_X_MAX,
                          y_min=PLAN_Y_MIN, y_max=PLAN_Y_MAX)
MAX_ACCUMULATED_ROTATION_DEG = 12.0

# Below this, a floor plate cannot hold a stair landing and its flights, so it is
# not a floor. Derived from the widest stair footprint the circulation emitter
# builds rather than chosen: flight width 2.6 m gives a 6.3 m run, and a plate
# has to clear that plus a way past it.
MIN_PLATE_SPAN_M = 9.0

APSE_SEGMENTS = 20


class LevelDatum(BaseModel):
    index: int
    id: str
    z: float
    kind: Literal['podium', 'occupied', 'roof']
    plate: list[Vector2]
    voids: list[list[Vector2]]
    is_terrace: bool = False


class Lattice(BaseModel):
    """The single source of horizontal and vertical registration.

    Every element in `compiler_v3.py` is a pure function of an index into this object.
    That property, not the polygon count, is what makes the model traceable.
    """

    schema_version: Literal['mta.lattice/1.0'] = 'mta.lattice/1.0'
    levels: list[LevelDatum]
    x_lines: list[float]
    y_lines: list[float]
    apse_nodes: list[Vector2]
    plan_x_m: float
    plan_y_m: float
    # The footprint these levels sit in, and the massing family that set it. Carried
    # here so an emitter never has to assume a plan it cannot see.
    plan: PlanBounds = DEFAULT_PLAN
    massing_id: str = 'MAS-SLAB'
    # Whether this run authors the envelope on two faces only. It is a presentation
    # decision, not a property of the building, and it belongs on the lattice so a
    # run can turn it off and see the volume it actually made. Reading massing off a
    # model sliced open on the two faces you can see is nearly impossible, which is
    # what the first evidence sheets demonstrated.
    cutaway: bool = True
    # Floor a spatial archetype carved for its own rooms (decision 0016), as plan
    # rectangles keyed by level index. Written by the compiler when a carve is
    # applied, alongside the voids it punches in the levels above. It lives on the
    # lattice, not in a parameter, so that everyone who asks where the cores may
    # stand -- the compiler at build time, a test recomputing the reservation --
    # reads the same answer. Passing it around by hand is how the reservation and
    # the emitted stair briefly disagreed about where the core was.
    carved: dict[int, list[tuple[float, float, float, float]]] = Field(
        default_factory=dict)

    def encloses(self, x: float, y: float) -> bool:
        """Whether a point is on an enclosed face rather than in the sectional cut."""
        if not self.cutaway:
            return True
        return envelope_stations_visible(x, y, self.plan)

    @property
    def occupied(self) -> list[LevelDatum]:
        return [level for level in self.levels if level.kind == 'occupied']

    @property
    def roof(self) -> LevelDatum:
        return self.levels[-1]

    def level(self, index: int) -> LevelDatum:
        return self.levels[index]


def plan_bounds(datums: DatumSet, family: MassingFamily) -> PlanBounds:
    """The footprint this family asks for, stretched a little by the score.

    The family fixes the proportion and the rough area, because that is what makes a
    tower a tower. The score is allowed to stretch it within the family's declared
    tolerance, taken from the bay datums, so a piece that wants generous structural bays
    gets a slightly larger building rather than the same building with fewer columns in
    it. The origin stays off-centre exactly as the original footprint was, so the west
    end still reads as the head of the plan.
    """
    def position(name: str) -> float:
        datum = datums.by_id(name)
        if datum is None or datum.output_range is None:
            return 0.5
        return datum.applied_position

    stretch_x = 1.0 + (position('bay_x_m') - 0.5) * 2.0 * family.plan_tolerance
    stretch_y = 1.0 + (position('bay_y_m') - 0.5) * 2.0 * family.plan_tolerance
    width = family.plan_x_m * stretch_x
    depth = family.plan_y_m * stretch_y
    return PlanBounds(
        x_min=round(-width * 0.389, 4), x_max=round(width * 0.611, 4),
        y_min=round(-depth / 2.0, 4), y_max=round(depth / 2.0, 4))


def _profile_extent(family: MassingFamily, plan: PlanBounds, level: int
                    ) -> tuple[float, float, float, float] | None:
    """The rectangle this level occupies before the apse and the cantilever act.

    Returning `None` means the family puts no plate at this level at all, which is how
    a bar on a podium stops being a podium.
    """
    above = max(0, level - 1)
    x_min, x_max = plan.x_min, plan.x_max
    y_min, y_max = plan.y_min, plan.y_max

    if family.profile == 'stepped':
        # every plate loses a band from the east end, so the section is a stair
        x_max -= plan.width * family.step_share * above
        if x_max - x_min < plan.width * 0.28:
            return None
    elif family.profile == 'tapered':
        # narrows on all four sides, which is what keeps a tower reading as a tower
        inset_x = plan.width * family.step_share * above
        inset_y = plan.depth * family.step_share * above
        x_min, x_max = x_min + inset_x, x_max - inset_x
        y_min, y_max = y_min + inset_y, y_max - inset_y
        if x_max - x_min < plan.width * 0.35 or y_max - y_min < plan.depth * 0.35:
            return None
    elif family.profile == 'podium_bar' and level >= 3:
        # the bar stands on the podium, centred on the plan and much narrower
        bar_w = plan.width * family.bar_share
        bar_d = plan.depth * family.bar_share
        cx = (plan.x_min + plan.x_max) / 2.0
        cy = (plan.y_min + plan.y_max) / 2.0
        x_min, x_max = cx - bar_w / 2.0, cx + bar_w / 2.0
        y_min, y_max = cy - bar_d / 2.0, cy + bar_d / 2.0
    return x_min, x_max, y_min, y_max


def _plate_polygon(datums: DatumSet, level: int, family: MassingFamily,
                   plan: PlanBounds) -> list[Vector2]:
    """Outer boundary of one floor plate. Derived from datums, never authored.

    The family decides the silhouette; three score-driven moves then shape it, each
    owned by a different dimension: the apse rounds the west end (continuity), the upper
    plates step back (variation), and the middle plates cantilever south (continuity).
    """
    extent = _profile_extent(family, plan, level)
    if extent is None:
        return []
    x_min, x_max, y_min, y_max = extent

    cantilever = datums.value('cantilever_m')
    step = datums.value('plate_step_m')
    radius = datums.value('apse_radius_m')

    # The score's step-back applies inside the family's own profile, but where the
    # family centres its plate an east-only step turns that plate into a wedge and
    # walks it west as it rises. Measured on a ten-storey tower the east edge came in
    # from 11.7 m to 2.0 m while the west edge did not move; on a bar over a podium
    # the bar drifted three metres between the third floor and the roof, so no single
    # point stayed inside it and the stair could not serve the top.
    #
    # A centred plate takes the step from both sides. An end-anchored one -- a slab,
    # a ziggurat, a split mass -- keeps the east-only step, because there the
    # step-back from one end is the reading rather than an accident.
    centred = family.profile == 'tapered' or (
        family.profile == 'podium_bar' and level >= 3)
    if centred:
        pull = step * max(0, level - 2) / 2.0
        x_min, x_max = x_min + pull, x_max - pull
    else:
        x_max -= step * max(0, level - 2)
    projecting = level in (2, 3) and family.profile != 'podium_bar'
    south = y_min - (cantilever if projecting else 0.0)

    if family.profile == 'split' and level >= 2:
        # A U in plan: two lobes joined across the north edge, with the notch cut in
        # from the south so the break is the thing a visitor walks into.
        gap = plan.width * family.gap_share
        cx = (x_min + x_max) / 2.0
        notch_north = south + (y_max - south) * 0.68
        points = [
            v2(x_max, south), v2(cx + gap / 2.0, south),
            v2(cx + gap / 2.0, notch_north), v2(cx - gap / 2.0, notch_north),
            v2(cx - gap / 2.0, south), v2(x_min, south),
            v2(x_min, y_max), v2(x_max, y_max),
        ]
    elif family.west_apse:
        apse_r = radius + (cantilever * 0.35 if projecting else 0.0)
        squash = abs(south) / abs(y_min) if y_min else 1.0
        points = [v2(x_max, south), v2(x_min, south)]
        # The boundary arrives at the west end from the south.  Walk the apse from
        # its south end through west to its north end before closing the rectangle;
        # the increasing-angle traversal starts at the north end and folds the ring
        # across itself.
        for step_index in range(APSE_SEGMENTS - 1, 0, -1):
            angle = math.pi * 0.5 + math.pi * step_index / APSE_SEGMENTS
            sine = math.sin(angle)
            points.append(v2(x_min + math.cos(angle) * apse_r,
                             sine * apse_r * (1.0 if sine > 0 else squash)))
        points.append(v2(x_min, y_max))
        points.append(v2(x_max, y_max))
    else:
        points = [v2(x_max, south), v2(x_min, south),
                  v2(x_min, y_max), v2(x_max, y_max)]

    # The minimum usable plate, checked here rather than inside `_profile_extent`.
    # The family's own taper and the score's step-back both narrow the plate, and
    # checking only the first let a tower reach a top floor 3.6 m across -- too narrow
    # for a stair to land on, which is how four storeys of a ten-storey tower ended up
    # with no way to reach them. A plate this small is where the building stops.
    if points:
        span_x = max(p.x for p in points) - min(p.x for p in points)
        span_y = max(p.y for p in points) - min(p.y for p in points)
        if span_x < MIN_PLATE_SPAN_M or span_y < MIN_PLATE_SPAN_M:
            return []

    # Each level turns against the one below. Kept small on purpose: the structural grid
    # stays orthogonal, so a large rotation would walk columns off the plate above and
    # break the stacking invariant the frame depends on.
    #
    # Two corrections a ten-storey building forced, neither of which showed on the six
    # levels this was written for. The accumulated angle is capped, because `deg *
    # (level - 1)` is unbounded and at ten levels it had turned the top plate far enough
    # to carry it outside the plan. And the turn is about a *fixed* point rather than
    # each plate's own centroid: rotating about a centroid that moves with the taper
    # walks the stack sideways, which is how a top plate ended up fifteen metres west of
    # a footprint that starts at minus seven.
    rotation = math.radians(min(MAX_ACCUMULATED_ROTATION_DEG,
                                datums.value('plate_rotation_deg') * max(0, level - 1)))
    if abs(rotation) > 1e-6:
        cx = (plan.x_min + plan.x_max) / 2.0
        cy = (plan.y_min + plan.y_max) / 2.0
        cos_r, sin_r = math.cos(rotation), math.sin(rotation)
        points = [
            v2(cx + (p.x - cx) * cos_r - (p.y - cy) * sin_r,
               cy + (p.x - cx) * sin_r + (p.y - cy) * cos_r)
            for p in points
        ]
    return points


# Fractions of the plan, west-south to east-north. They were coordinate literals until
# the footprint stopped being a constant, at which point a void authored at x=12.5 was a
# void that fell outside a twenty-one metre tower. This module's own docstring forbids
# absolute coordinates in emitters; the same rule belongs here.
_VOID_SEEDS: tuple[tuple[float, float, float, float], ...] = (
    (0.40, 0.30, 0.61, 0.65),
    (0.74, 0.41, 0.88, 0.68),
    (0.14, 0.59, 0.28, 0.82),
)


def _void_polygons(datums: DatumSet, level: int, family: MassingFamily,
                   plan: PlanBounds) -> list[list[Vector2]]:
    """Atrium voids. Interruption sets how many and how large.

    A courtyard family adds one more, on every occupied level rather than two: the void
    is the point of that massing, so it goes all the way up.
    """
    voids: list[list[Vector2]] = []
    if family.courtyard_share > 0.0 and level not in (0,):
        half = family.courtyard_share / 2.0
        voids.append([
            v2(plan.fx(0.5 - half), plan.fy(0.5 - half)),
            v2(plan.fx(0.5 + half), plan.fy(0.5 - half)),
            v2(plan.fx(0.5 + half), plan.fy(0.5 + half)),
            v2(plan.fx(0.5 - half), plan.fy(0.5 + half)),
        ])

    count = datums.integer('void_count')
    if count == 0 or level not in (2, 3):
        return voids
    scale = datums.value('void_scale')
    for index, (tx0, ty0, tx1, ty1) in enumerate(_VOID_SEEDS[:count]):
        x0, y0 = plan.fx(tx0), plan.fy(ty0)
        x1, y1 = plan.fx(tx1), plan.fy(ty1)
        # the third void only appears on the lower of the two pierced levels, so the
        # stack reads as a sequence rather than a single shaft
        if index == 1 and level != 3:
            continue
        if index == 2 and level != 2:
            continue
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        hx, hy = (x1 - x0) / 2.0 * scale, (y1 - y0) / 2.0 * scale
        voids.append([v2(cx - hx, cy - hy), v2(cx + hx, cy - hy),
                      v2(cx + hx, cy + hy), v2(cx - hx, cy + hy)])
    return voids


def build_lattice(datums: DatumSet,
                  family: MassingFamily | None = None,
                  cutaway: bool = True) -> Lattice:
    """Register one building's levels and grid inside its massing family's footprint.

    `family` defaults to the stacked slab, which reproduces exactly the building this
    pipeline made before the families existed. Passing one is what lets two recordings
    differ in silhouette rather than only in cladding.
    """
    family = family or MASSING_FAMILIES['MAS-SLAB']
    plan = plan_bounds(datums, family)

    # the datum counts *occupied* levels; the podium below and the roof above are
    # tectonic facts, not compositional ones, so they are added rather than competed for
    occupied_count = level_count_for(family, max(2, datums.integer('level_count')))
    level_count = occupied_count + 2
    floor_to_floor = datums.value('floor_to_floor_m')
    ground_open = datums.value('ground_open_height_m')

    # Interruption strips the envelope from whole levels and turns them into terraces.
    # Tectonic clamp: however hard the music breaks, at most one occupied level in
    # three may lose its envelope. Past that the building stops being a building.
    def _terraces(count: int) -> set[int]:
        occupied_indices = [i for i in range(1, count - 1)]
        ceiling = max(0, len(occupied_indices) // 3)
        wanted = min(ceiling, max(0, datums.integer('terrace_count')))
        middle = occupied_indices[1:-1] or occupied_indices
        return set(middle[:wanted])

    terraces = _terraces(level_count)

    # A stepping or tapering family eventually runs out of plate, and that is the
    # correct place for the building to stop rather than a case to pad around: a
    # ziggurat whose top plate has shrunk past a usable floor has reached its roof. The
    # stack truncates there, and the roof is put on the last level that still had one.
    plates: list[list[Vector2]] = []
    for index in range(level_count):
        plate = _plate_polygon(datums, max(index, 1), family, plan)
        if not plate:
            break
        plates.append(plate)
    if len(plates) < 3:
        # Never fewer than a podium, one occupied level and a roof. A family whose
        # profile cannot deliver that has been configured wrongly, and falling back to
        # the podium plate keeps the failure visible as a squat building rather than as
        # a division by zero four modules downstream.
        plates = (plates or [_plate_polygon(datums, 1, family, plan)])
        while len(plates) < 3:
            plates.append(list(plates[-1]))
    level_count = len(plates)
    terraces = _terraces(level_count)

    levels: list[LevelDatum] = []
    z = 0.0
    for index in range(level_count):
        if index == 0:
            kind: Literal['podium', 'occupied', 'roof'] = 'podium'
        elif index == level_count - 1:
            kind = 'roof'
        else:
            kind = 'occupied'
        levels.append(LevelDatum(
            index=index, id=f'L{index:02d}', z=round(z, 4), kind=kind,
            plate=plates[index],
            voids=_void_polygons(datums, index, family, plan),
            is_terrace=index in terraces))
        z += ground_open if index == 0 else floor_to_floor

    span_x = plan.width
    span_y = plan.depth
    bays_x = max(2, round(span_x / datums.value('bay_x_m')))
    bays_y = max(2, round(span_y / datums.value('bay_y_m')))
    x_lines = [round(plan.x_min + span_x * i / bays_x, 4) for i in range(bays_x + 1)]
    y_lines = [round(plan.y_min + span_y * j / bays_y, 4) for j in range(bays_y + 1)]

    radius = datums.value('apse_radius_m') * 0.98
    if family.west_apse:
        apse_count = max(5, round(math.pi * radius / datums.value('bay_y_m')) * 2 + 1)
        apse_nodes = [
            v2(plan.x_min
               + math.cos(math.pi * 0.5 + math.pi * k / (apse_count + 1)) * radius,
               math.sin(math.pi * 0.5 + math.pi * k / (apse_count + 1)) * radius)
            for k in range(1, apse_count + 1)
        ]
    else:
        # A square-ended family has no radial bay, and emitting one anyway would put a
        # ring of columns outside the plate it is meant to support.
        apse_nodes = []

    return Lattice(
        levels=levels, x_lines=x_lines, y_lines=y_lines, apse_nodes=apse_nodes,
        plan=plan, massing_id=family.id, cutaway=cutaway,
        plan_x_m=round(span_x + (radius if family.west_apse else 0.0), 3),
        plan_y_m=round(span_y, 3))


# Where the section cuts, as fractions of the plan. On the original 36 x 22 m footprint
# these reproduce the old literals of y > 1.5 and x > 15.5 exactly.
CUT_NORTH_T = 0.5682
CUT_EAST_T = 0.8194


def envelope_stations_visible(x: float, y: float,
                              plan: 'PlanBounds | None' = None) -> bool:
    """The sectional cut. Envelope is authored on the south and west faces only, so the
    north and east read as a cut and the frame, plates, and program stay visible.

    This is a presentation decision recorded in the datum layer rather than hidden in the
    renderer, so a run can say why half the envelope is missing.

    The cut is a fraction of the plan rather than a coordinate, because the plan is no
    longer a constant: on a twenty-one metre tower the old literal `x > 15.5` cut away
    almost nothing, and on a fifty metre split mass it removed most of the building.
    """
    plan = plan or DEFAULT_PLAN
    return not (y > plan.fy(CUT_NORTH_T) or x > plan.fx(CUT_EAST_T))


__all__ = [
    'Datum', 'DatumSet', 'Lattice', 'LevelDatum', 'build_lattice',
    'compile_datum_set', 'envelope_stations_visible', 'plan_bounds', 'PlanBounds',
    'DEFAULT_PLAN', 'point_inside',
    'resample_by_arclength', 'superellipse',
]
