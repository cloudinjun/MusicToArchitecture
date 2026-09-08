"""The things a person would see, written down so a blind pipeline can be told.

Someone modelling this by hand never puts a lift shaft through a fire lobby, never
leaves a ramp deck floating 120 mm above the landing it arrives on, and never opens a
250 mm slot down the middle of a switchback. They do not avoid these by following a
rule; they avoid them by looking. The pipeline does not look, so what the eye does has
to be stated.

Every rule here is one this model has actually broken. That is the whole basis for the
list -- not a survey of what could go wrong, but a record of what did, each one found by
measuring after a render or a drawing made it obvious:

* a lift shaft standing in a fire lobby, eating 46% of it
* a ramp deck whose top sat half a deck-thickness above every landing it met, because
  one emitter read the centre-line as the walking surface and the other read it as the
  deck's middle
* a switchback whose legs were `width + 0.25` apart, leaving a slot between two decks
  at different heights
* partitions crossing stair half-landings

The existing reports check *relations* -- what hosts what, what reaches ground, what a
grammar's guide permits. None of them ask whether two things are in the same place, or
whether a surface a person walks onto is level with the one they walk off. That is the
gap these fill.

Findings are measured and stated, never inferred from an emitter's intent. A rule that
reports a violation says how big it is, so a reader can tell a modelling error from a
rounding one.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from typing import Callable, Literal

from pydantic import BaseModel, Field
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from .geometry import BoxGeometry, ExtrusionGeometry, MemberGeometry, QuadGeometry
from .mesh_primitives import box_mesh, member_mesh
from .geometry_review import _polygon


Severity = Literal['violation', 'warning']

# Two solids overlapping by less than this in plan are touching, not colliding: a
# tolerance for how emitters round, not an allowance for how much a lift may intrude
# into a room.
TOUCH_M2 = 0.02

# A walking surface meeting another must be flush to within this. Five millimetres is a
# threshold; 120 mm is a modelling error, and the point of the number is to tell them
# apart.
FLUSH_M = 0.005

# A gap between two walking surfaces at different heights that a foot fits through.
FALL_GAP_M = 0.030

# The plan grid the index buckets into. Large enough that a bucket holds few elements,
# small enough that few elements span many buckets.
CELL_M = 4.0


class Finding(BaseModel):
    """One thing a person would have seen.

    Constructed by keyword only. It was a positional dataclass first, and when it
    became a model type the four rules kept calling it positionally -- so every rule
    would have raised the moment it found anything. Nothing caught that, because
    nothing was finding anything: the models all passed. The tests that build a
    violation on purpose are what surfaced it.
    """

    rule_id: str
    severity: Severity
    elements: tuple[str, ...]
    measure: float
    unit: str
    detail: str


@dataclass
class Solid:
    """An element reduced to what these rules need: a plan box and a height range."""

    id: str
    kind: str
    subsystem: str
    layer: str
    level_id: str
    x0: float
    y0: float
    x1: float
    y1: float
    z0: float
    z1: float
    footprint: object | None = None
    walking_faces: tuple = ()

    @property
    def plan_area(self) -> float:
        if self.footprint is not None:
            return self.footprint.area
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)


def _bounds(instance, geometry, profiles=None) -> tuple[float, ...] | None:
    """Broad phase only. Boxes rotate; members include their resolved section."""
    if isinstance(geometry, BoxGeometry):
        points, _ = box_mesh(geometry.model_dump())
    elif isinstance(geometry, MemberGeometry):
        if profiles is None or geometry.profile not in profiles:
            # Unknown profiles are not silently assigned an invented section.
            raise ValueError(f'Unresolved member profile: {geometry.profile}')
        points, _ = member_mesh(geometry.model_dump(), {
            key: value.model_dump() if hasattr(value, 'model_dump') else value
            for key, value in profiles.items()})
    elif isinstance(geometry, ExtrusionGeometry):
        points = [(p.x,p.y,z) for p in geometry.boundary
                  for z in (geometry.z_base,geometry.z_top)]
    elif isinstance(geometry, QuadGeometry):
        points = [p.as_tuple() for p in geometry.corners]
    else:
        return None
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    return (low[0],low[1],high[0],high[1],low[2],high[2])


class SpatialIndex:
    """Everything the rules read, walked once.

    Pairwise comparison of thirty-six hundred elements is six and a half million tests
    per model, most of them between objects at opposite ends of the site. Bucketing by
    a coarse plan grid turns that into a few thousand, and the rules stay readable
    because none of them has to think about it.
    """

    def __init__(self, model) -> None:
        self.model = model
        self.solids: list[Solid] = []
        self.by_kind: dict[str, list[Solid]] = defaultdict(list)
        for group in model.element_groups:
            for instance in group.instances:
                bounds = _bounds(instance, instance.geometry, getattr(model, 'profiles', {}))
                if bounds is None:
                    continue
                solid = Solid(instance.id, group.kind, group.subsystem,
                              group.semantic_layer, instance.level_id, *bounds, footprint=_polygon(instance.geometry))
                if group.kind == 'ramp' and isinstance(instance.geometry, MemberGeometry):
                    solid.walking_faces = _ramp_top_faces(instance.geometry, model.profiles)
                    solid.footprint = unary_union([face[0] for face in solid.walking_faces])
                self.solids.append(solid)
                self.by_kind[group.kind].append(solid)

        self._cells: dict[tuple[int, int], list[Solid]] = defaultdict(list)
        for solid in self.solids:
            for cell in self._cells_for(solid):
                self._cells[cell].append(solid)

    def _cells_for(self, solid: Solid):
        for i in range(int(math.floor(solid.x0 / CELL_M)),
                       int(math.floor(solid.x1 / CELL_M)) + 1):
            for j in range(int(math.floor(solid.y0 / CELL_M)),
                           int(math.floor(solid.y1 / CELL_M)) + 1):
                yield (i, j)

    def near(self, solid: Solid) -> list[Solid]:
        found: set[int] = set()
        out: list[Solid] = []
        for cell in self._cells_for(solid):
            for other in self._cells.get(cell, ()):
                if other is solid or id(other) in found:
                    continue
                found.add(id(other))
                out.append(other)
        return out


def plan_overlap(a: Solid, b: Solid) -> float:
    # Exact prism footprints preserve rotation and holes after the AABB broad phase.
    if a.footprint is not None and b.footprint is not None:
        return a.footprint.intersection(b.footprint).area
    width = min(a.x1, b.x1) - max(a.x0, b.x0)
    height = min(a.y1, b.y1) - max(a.y0, b.y0)
    return width * height if width > 0 and height > 0 else 0.0


def height_overlap(a: Solid, b: Solid) -> float:
    return min(a.z1, b.z1) - max(a.z0, b.z0)


# --- the rules -------------------------------------------------------------------

# Subsystems that may not stand in one another. Structure inside a room is normal --
# a column in a hall is a column in a hall -- so the pairs here are the ones where one
# subsystem being inside the other means the layout ignored it.
EXCLUSIVE_PAIRS = (
    ({'stair_tread', 'stair_landing', 'stair_half_landing', 'stair_stringer',
      'elevator_shaft', 'ramp', 'ramp_landing'}, {'program_zone'},
     'circulation standing in a program zone'),
    ({'partition', 'partition_head'},
     {'stair_tread', 'stair_landing', 'stair_half_landing', 'ramp', 'ramp_landing'},
     'a partition crossing a route'),
)


def rule_no_two_subsystems_in_one_place(index: SpatialIndex) -> list[Finding]:
    """A lift shaft standing in the fire lobby is the clearest case of this.

    Program, circulation and structure are each laid out from the lattice on their own
    and nothing arbitrates between them, so where they meet, they simply overlap. The
    eye catches it instantly; nothing in the pipeline was looking.
    """
    # Levels whose plate was too small to carry its own cores. The program was laid
    # out over them because cutting them out left nothing to lay out on, and that is a
    # recorded cause, not permission for an overlap. Legacy payloads retain that
    # explanation, but measured physical conflicts still report a violation.
    unreserved = set(index.model.program_allocation.cores_unreserved)

    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for first, second, description in EXCLUSIVE_PAIRS:
        for kind in first:
            for solid in index.by_kind.get(kind, ()):
                for other in index.near(solid):
                    if other.kind not in second or other.level_id != solid.level_id:
                        continue
                    area = plan_overlap(solid, other)
                    if area <= TOUCH_M2 or height_overlap(solid, other) <= 0.0:
                        continue
                    key = tuple(sorted((solid.id, other.id)))
                    if key in seen:
                        continue
                    seen.add(key)
                    share = area / max(1e-6, other.plan_area)
                    excused = solid.level_id in unreserved
                    findings.append(Finding(
                        rule_id='SP-SUBSYSTEM-OVERLAP',
                        severity='violation',
                        elements=key, measure=share, unit='of the host',
                        detail=f'{description}: {solid.kind} takes {share:.0%} of '
                               f'{other.id}.'
                               + (f' {solid.level_id} is too small to cut its cores '
                                  'out of, so the program shares the floor with them.'
                                  if excused else '')))
    return findings


WALKING = {'ramp', 'ramp_landing', 'stair_landing', 'stair_half_landing',
           'floor_slab', 'podium_slab'}


def _ramp_top_faces(geometry, profiles):
    """Upward triangles of the emitted sweep, including its real end transitions."""
    vertices, faces = member_mesh(geometry.model_dump(), {
        key: value.model_dump() for key, value in profiles.items()})
    result = []
    for face in faces:
        for k in range(1, len(face) - 1):
            a, b, c = [vertices[i] for i in (face[0], face[k], face[k + 1])]
            u = [b[i] - a[i] for i in range(3)]
            v = [c[i] - a[i] for i in range(3)]
            nx, ny, nz = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2],
                          u[0]*v[1]-u[1]*v[0])
            if nz <= 1e-10:
                continue
            result.append((Polygon([(p[0], p[1]) for p in (a, b, c)]),
                           (-nx/nz, -ny/nz, a[2]+(nx*a[0]+ny*a[1])/nz)))
    return tuple(result)


def _walking_step(a: Solid, b: Solid) -> float:
    """Maximum local height difference over the shared walking footprint.

    Plane differences are affine; their extrema occur at intersection vertices.
    Flat decks keep their exact footprint holes. No slope or step is waived.
    """
    def faces(solid):
        footprint = solid.footprint if solid.footprint is not None else box(
            solid.x0, solid.y0, solid.x1, solid.y1)
        return solid.walking_faces or ((footprint, (0, 0, solid.z1)),)
    if not (a.walking_faces or b.walking_faces):
        return abs(a.z1 - b.z1)
    step = 0.0
    for pa, ha in faces(a):
        for pb, hb in faces(b):
            overlap = pa.intersection(pb)
            pieces = [overlap] if overlap.geom_type == 'Polygon' else getattr(overlap, 'geoms', ())
            for piece in pieces:
                if piece.geom_type != 'Polygon' or piece.area <= 1e-10:
                    continue
                for x, y in piece.exterior.coords:
                    step = max(step, abs((ha[0]-hb[0])*x + (ha[1]-hb[1])*y + ha[2]-hb[2]))
    return step


def rule_walking_surfaces_meet_flush(index: SpatialIndex) -> list[Finding]:
    """You step from one onto the other, so their tops are the same height.

    This is the rule the ramp broke everywhere at once: the deck was swept along the
    walking line, which put its top half a thickness above it, while the landings were
    built with their tops *on* that line. Both were following the centre-line and they
    disagreed by 120 mm at every joint on every model.
    """
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    # Sorted: the kinds are a set, and a finding order that changed with the hash
    # seed made the report differ between two runs of one model.
    surfaces = [solid for kind in sorted(WALKING) for solid in index.by_kind.get(kind, ())]
    for solid in surfaces:
        for other in index.near(solid):
            if other.kind not in WALKING:
                continue
            key = tuple(sorted((solid.id, other.id)))
            if key in seen or plan_overlap(solid, other) <= TOUCH_M2:
                continue
            seen.add(key)
            step = _walking_step(solid, other)
            # Surfaces that overlap in plan and are a storey apart are a floor above a
            # floor, not a joint. Only near-coincident tops are meant to be flush.
            if step <= FLUSH_M or step > 0.5:
                continue
            findings.append(Finding(
                rule_id='SP-SURFACE-NOT-FLUSH', severity='violation', elements=key,
                measure=step, unit='m',
                detail=f'{solid.kind} and {other.kind} overlap in plan but their '
                       f'walking surfaces differ by {step * 1000:.0f} mm.'))
    return findings


def rule_no_gap_between_adjacent_decks(index: SpatialIndex) -> list[Finding]:
    """A slot between two walking surfaces at different heights is a hole.

    The switchback had one down its whole length, because the legs were pitched a
    quarter-metre further apart than the deck is wide. Two runs of a switchback sit at
    different heights along most of their length, so the gap between them is not a
    joint, it is a drop.
    """
    findings: list[Finding] = []
    decks = list(index.by_kind.get('ramp', ())) + list(index.by_kind.get('ramp_landing', ()))
    seen: set[tuple[str, str]] = set()
    for solid in decks:
        for other in decks:
            if other is solid:
                continue
            key = tuple(sorted((solid.id, other.id)))
            if key in seen:
                continue
            # Side by side along y, overlapping along x: the switchback condition.
            if min(solid.x1, other.x1) - max(solid.x0, other.x0) <= 1.0:
                continue
            gap = max(solid.y0, other.y0) - min(solid.y1, other.y1)
            if not (FALL_GAP_M < gap < 0.6):
                continue
            seen.add(key)
            findings.append(Finding(
                rule_id='SP-FALL-GAP', severity='violation', elements=key,
                measure=gap, unit='m',
                detail=f'{gap * 1000:.0f} mm slot between two decks that run '
                       f'alongside each other at different heights.'))
    return findings


def _inside_ring(ring, x: float, y: float) -> bool:
    inside = False
    count = len(ring)
    for i in range(count):
        a, b = ring[i], ring[(i + 1) % count]
        if (a.y > y) != (b.y > y):
            if x < (b.x - a.x) * (y - a.y) / (b.y - a.y) + a.x:
                inside = not inside
    return inside


def rule_nothing_stands_in_a_void(index: SpatialIndex) -> list[Finding]:
    """An atrium is a hole. Furniture in it is standing on nothing.

    Measured over the solid's plan footprint rather than at its centre point. The
    centre test called a wall a mistake for doing exactly what a person would draw:
    a room beside a void is enclosed by a wall along the void's edge, the wall's
    centre-line lies on that edge, and half a thickness of rounding put the centre
    a hair inside the hole. A solid is standing in the void when most of its
    footprint is over it, not when it touches the line -- so the footprint is
    sampled on a three-by-three grid and the share is the measure reported.
    """
    findings: list[Finding] = []
    levels = {level.id: level for level in index.model.lattice.levels}
    cut_their_own = {'ceiling', 'floor_slab', 'podium_slab', 'roof_deck'}
    for solid in index.solids:
        if solid.layer not in ('program',) or solid.kind == 'program_zone':
            continue
        # An element that cut the void out of itself is not standing in it. The
        # ceiling spans the whole plate and carries the courtyard as a hole; testing
        # the centre of its bounding box put that centre in the courtyard and called
        # a correctly-built plane a mistake.
        if solid.kind in cut_their_own:
            continue
        level = levels.get(solid.level_id)
        if level is None or not level.voids:
            continue
        samples = [(solid.x0 + (solid.x1 - solid.x0) * (i + 0.5) / 3.0,
                    solid.y0 + (solid.y1 - solid.y0) * (j + 0.5) / 3.0)
                   for i in range(3) for j in range(3)]
        over = sum(1 for x, y in samples
                   if any(_inside_ring(ring, x, y) for ring in level.voids))
        share = over / len(samples)
        if share >= 0.6:
            findings.append(Finding(
                rule_id='SP-STANDS-IN-VOID', severity='violation',
                elements=(solid.id,), measure=share, unit='of its footprint',
                detail=f'{solid.kind} {solid.id} stands {share:.0%} inside a floor '
                       f'void on {solid.level_id}.'))
    return findings


@dataclass(frozen=True)
class SpatialRule:
    id: str
    sees: str
    severity: Severity
    check: Callable[[SpatialIndex], list[Finding]]


RULES: tuple[SpatialRule, ...] = (
    SpatialRule('SP-SUBSYSTEM-OVERLAP',
                'Two systems standing in the same floor area.',
                'violation', rule_no_two_subsystems_in_one_place),
    SpatialRule('SP-SURFACE-NOT-FLUSH',
                'A surface you step onto that is not level with the one you step off.',
                'violation', rule_walking_surfaces_meet_flush),
    SpatialRule('SP-FALL-GAP',
                'A slot between two walking surfaces at different heights.',
                'violation', rule_no_gap_between_adjacent_decks),
    SpatialRule('SP-STANDS-IN-VOID',
                'Something standing where the floor has a hole in it.',
                'violation', rule_nothing_stands_in_a_void),
)


class SpatialReport(BaseModel):
    """What the rules saw, counted and named.

    Travels on the model rather than living in a script: a rule that only runs when
    somebody remembers to run it is not a constraint, and the whole point of writing
    these down was that nobody is looking.
    """

    schema_version: Literal['mta.spatial/1.0'] = 'mta.spatial/1.0'
    status: Literal['passed', 'failed', 'unevaluated']
    findings: list[Finding] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    # What each rule watches for, carried with the result so a reader does not have to
    # find the source to know what a passing check actually checked.
    watches: dict[str, str] = Field(default_factory=dict)

    def by_rule(self, rule_id: str) -> list[Finding]:
        return [finding for finding in self.findings if finding.rule_id == rule_id]


def check_spatial_rules(model, *, limit: int = 40) -> SpatialReport:
    """Run every rule. Findings are capped for reporting; counts are not."""
    if limit < 0:
        raise ValueError('Report limit cannot be negative')
    index = SpatialIndex(model)
    findings: list[Finding] = []
    counts: dict[str, int] = {}
    has_violation = False
    has_warning = False
    for rule in RULES:
        found = rule.check(index)
        counts[rule.id] = len(found)
        has_violation = has_violation or any(
            finding.severity == 'violation' for finding in found)
        has_warning = has_warning or any(finding.severity == 'warning' for finding in found)
        # Preserve violations in the capped display. A warning with a larger numeric
        # measure must not push the actual collision out of the report readers use.
        findings.extend(sorted(
            found,
            key=lambda item: (0 if item.severity == 'violation' else 1,
                              -item.measure),
        )[:limit])
    # Warnings mean a rule ran but the available geometry could not support a finding;
    # that is an honest third state for the report, even when no measured violation was
    # found. Status is derived from the complete result set, not the capped display.
    status = ('failed' if has_violation else
              'unevaluated' if has_warning else 'passed')
    return SpatialReport(status=status,
                         findings=findings, counts=counts,
                         watches={rule.id: rule.sees for rule in RULES})


# The checks below are kept at the end of this module so the existing broad-phase
# rules remain readable and stable.  `geometry_review` deliberately does not import
# this module: it returns Finding-shaped records, and this adapter is the only place
# where those records enter the established spatial-report schema.
from .geometry_review import (  # noqa: E402
    GeometryFinding,
    review_geometry,
)


def _as_spatial_findings(records: list[GeometryFinding]) -> list[Finding]:
    return [Finding(
        rule_id=record.rule_id,
        severity=record.severity,
        elements=record.elements,
        measure=record.measure,
        unit=record.unit,
        detail=record.detail,
    ) for record in records]


def _geometry_review_for_rule(index: SpatialIndex, rule_id: str) -> list[Finding]:
    # One model run shares one SpatialIndex.  Cache the exact geometry pass there so
    # five report entries do not rebuild the same Shapely polygons five times.
    if not hasattr(index, '_geometry_review_cache'):
        index._geometry_review_cache = review_geometry(index.model)
    return _as_spatial_findings([
        record for record in index._geometry_review_cache
        if record.rule_id == rule_id
    ])


def rule_stair_head_clearance(index: SpatialIndex) -> list[Finding]:
    return _geometry_review_for_rule(index, 'SP-STAIR-HEAD-CLEARANCE')


def rule_tread_floor_slab_overlap(index: SpatialIndex) -> list[Finding]:
    return _geometry_review_for_rule(index, 'SP-STAIR-TREAD-SLAB-OVERLAP')


def rule_tread_elevator_shaft_overlap(index: SpatialIndex) -> list[Finding]:
    return _geometry_review_for_rule(index, 'SP-STAIR-TREAD-LIFT-OVERLAP')


def rule_intercore_stair_overlap(index: SpatialIndex) -> list[Finding]:
    return _geometry_review_for_rule(index, 'SP-STAIR-INTERCORE-OVERLAP')


def rule_invalid_plan_rings(index: SpatialIndex) -> list[Finding]:
    return _geometry_review_for_rule(index, 'SP-INVALID-PLAN-RING')


RULES = RULES + (
    SpatialRule(
        'SP-STAIR-HEAD-CLEARANCE',
        'Stair treads retain a two metre design-review clearance to slabs and ceilings.',
        'violation', rule_stair_head_clearance),
    SpatialRule(
        'SP-STAIR-TREAD-SLAB-OVERLAP',
        'Stair tread bodies do not pass through floor slabs.',
        'violation', rule_tread_floor_slab_overlap),
    SpatialRule(
        'SP-STAIR-TREAD-LIFT-OVERLAP',
        'Stair tread bodies do not occupy a lift shaft solid.',
        'violation', rule_tread_elevator_shaft_overlap),
    SpatialRule(
        'SP-STAIR-INTERCORE-OVERLAP',
        'Distinct stair core pairs do not share positive tread volume.',
        'violation', rule_intercore_stair_overlap),
    SpatialRule(
        'SP-INVALID-PLAN-RING',
        'Closed plan solids have evaluable rings before intersections are measured.',
        'violation', rule_invalid_plan_rings),
)


from .assembly_review import review_furniture  # noqa: E402


def _furniture_findings(index, rule_id):
    if not hasattr(index, '_furniture_review_cache'):
        index._furniture_review_cache = review_furniture(index.model)
    return _as_spatial_findings([f for f in index._furniture_review_cache if f.rule_id == rule_id])


RULES = RULES + (
    SpatialRule('SP-FURNITURE-COMPLETE',
                'Furniture contains the required named parts of its selected recipe.',
                'violation', lambda index: _furniture_findings(index, 'SP-FURNITURE-COMPLETE')),
    SpatialRule('SP-FURNITURE-CONTACT',
                'Furniture parts physically meet their declared parts or floor supports.',
                'violation', lambda index: _furniture_findings(index, 'SP-FURNITURE-CONTACT')),
)


def rule_room_support(index: SpatialIndex) -> list[Finding]:
    return _geometry_review_for_rule(index, 'SP-ROOM-OUTSIDE-SUPPORT')


RULES = RULES + (SpatialRule(
    'SP-ROOM-OUTSIDE-SUPPORT',
    'Room footprints are contained in the actual same-level floor support, including holes.',
    'violation', rule_room_support),)


# ---------------------------------------------------------------------------
# Program Volume physical-boundary gates (decisions 0024 and 0025)
# ---------------------------------------------------------------------------

_PV_INTERNAL_LAYERS = {'structure', 'program', 'circulation'}
_PV_NON_BUILDING_KINDS = {'figure', 'earth', 'site_context'}
_PV_ROOF_KINDS = {'roof_deck', 'parapet'}
_PV_PRIMARY_FACADE_KINDS = {
    'glazing_panel', 'spandrel_panel', 'solid_wall_panel', 'wall_panel',
    'backing_panel', 'field_panel', 'facet_panel', 'facet_glazing',
    'lattice_cell', 'order_field',
}
_PV_PRIMARY_FACADE_SUBSYSTEMS = {
    'curtain_wall', 'backing_skin', 'bearing_wall', 'panel_field',
    'lattice_screen',
}


def _unknown(rule_id: str, elements: tuple[str, ...], detail: str) -> Finding:
    """Record a Program Volume check whose physical geometry cannot be measured."""
    return Finding(
        rule_id=rule_id,
        severity='warning',
        elements=elements,
        measure=0.0,
        unit='unmeasured',
        detail=detail,
    )


def _program_volume_regions(model):
    contract = getattr(model, 'program_volume_model', None)
    if contract is None:
        return None, {}, {}
    regions = {
        union.level_id: Polygon(union.boundary, holes=union.voids)
        for union in contract.level_unions
    }
    levels = {level.id: level for level in contract.levels}
    return contract, regions, levels


def _program_region_for(element, regions, contract, model):
    if element.level_id in regions:
        return regions[element.level_id]
    lattice = getattr(model, 'lattice', None)
    roof = getattr(lattice, 'roof', None)
    if element.level_id == getattr(roof, 'id', None) and contract.levels:
        return regions.get(contract.levels[-1].id)
    # L00 is the open/support storey below the first authored occupied volume. Its
    # frame may stand below that volume, but it cannot spread beyond its footprint.
    if element.level_id == 'L00' and contract.levels:
        return regions.get(contract.levels[0].id)
    return None


def _physical_projection(element, model):
    """Measured primitive footprint and z interval, including real sections."""
    from .physical_geometry import physical_projection

    try:
        projection = physical_projection(
            element.geometry,
            getattr(model, 'profiles', {}),
            thickness_m=getattr(element, 'thickness_m', None),
        )
        return projection, None
    except ValueError as exc:
        return None, str(exc)


def rule_program_volume_internal_containment(index: SpatialIndex) -> list[Finding]:
    """Keep every physical internal element inside its authored storey union.

    The projection includes the real member section and rotated boxes. Centre points
    therefore cannot hide a column or stair whose body crosses the massing boundary.
    Roof and exterior-approach parts have their own control volumes and are excluded by
    explicit identity, never by a broad subsystem guess.
    """
    rule_id = 'PV-INTERNAL-SOLID-CONTAINMENT'
    contract, regions, _levels = _program_volume_regions(index.model)
    if contract is None:
        return []
    exceptions = set()
    circulation = getattr(index.model, 'circulation_plan', None)
    if circulation is not None:
        exceptions.update(circulation.exterior_exception_ids)
    findings: list[Finding] = []
    for element in index.model.elements:
        if (element.semantic_layer not in _PV_INTERNAL_LAYERS
                or element.kind in _PV_NON_BUILDING_KINDS
                or element.kind in _PV_ROOF_KINDS
                or element.kind == 'footing'
                or element.id in exceptions):
            continue
        allowed = _program_region_for(element, regions, contract, index.model)
        if allowed is None:
            findings.append(_unknown(
                rule_id, (element.id,),
                f'{element.kind} has no Program Volume region for {element.level_id}.'))
            continue
        projection, error = _physical_projection(element, index.model)
        if projection is None:
            findings.append(_unknown(
                rule_id, (element.id,),
                f'{element.kind} physical projection could not be measured: {error}'))
            continue
        footprint, _z = projection
        outside = footprint.difference(allowed.buffer(1.0e-5, join_style=2)).area
        if outside <= 1.0e-5:
            continue
        share = outside / max(footprint.area, 1.0e-9)
        findings.append(Finding(
            rule_id=rule_id, severity='violation', elements=(element.id,),
            measure=outside, unit='m2',
            detail=(f'{element.kind} {element.id} has {outside:.4f} m2 '
                    f'({share:.1%}) of its physical plan projection outside the '
                    f'{element.level_id} Program Volume union.')))
    return findings


def rule_program_volume_facade_collar(index: SpatialIndex) -> list[Finding]:
    """Project the shared FacadeControl validator into the spatial report."""
    rule_id = 'PV-FACADE-COLLAR'
    contract, _regions, _levels = _program_volume_regions(index.model)
    if contract is None:
        return []
    control = getattr(getattr(index.model, 'lattice', None), 'facade_control', None)
    if control is None:
        return [_unknown(
            rule_id, (),
            'Program Volume model has no FacadeControl resolved from score, tectonic '
            'and facade grammar.')]

    from .facade_control import validate_facade_collar

    lineage = []
    source_digest = contract.digest()
    if control.program_volume_source_digest != source_digest:
        lineage.append(Finding(
            rule_id=rule_id, severity='violation', elements=(), measure=1.0,
            unit='digest_mismatch',
            detail=('FacadeControl references Program Volume digest '
                    f'{control.program_volume_source_digest}, while the attached '
                    f'authoring artifact is {source_digest}; facade validation cannot '
                    'be credited to a different form source.')))
    records = validate_facade_collar(
        control, index.model.elements, getattr(index.model, 'profiles', {}))
    return lineage + [Finding(
        rule_id=rule_id,
        severity=('violation' if record.status == 'failed' else 'warning'),
        elements=((record.element_id,) if record.element_id else ()),
        measure=record.measure,
        unit=record.unit,
        detail=record.detail,
    ) for record in records]


RULES = RULES + (
    SpatialRule(
        'PV-INTERNAL-SOLID-CONTAINMENT',
        'Physical structure, rooms and internal circulation remain inside their '
        'authored Program Volume union, except named exterior approach parts.',
        'violation', rule_program_volume_internal_containment),
    SpatialRule(
        'PV-FACADE-COLLAR',
        'Primary facade bodies stay on/outboard of the Program Volume boundary and '
        'within the declared offset plus their measured physical half-breadth.',
        'violation', rule_program_volume_facade_collar),
)
