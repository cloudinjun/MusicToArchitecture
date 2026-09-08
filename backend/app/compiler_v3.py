"""Compiler 3.0: lattice -> member-level elements.

Every emitter here is a pure function of an index into `Lattice`. No element in this
module carries an absolute coordinate literal, which is the property decision 0008 asked
for and the reason two different MP3s now produce two different buildings rather than the
same building at two scales.

Structural members carry the section the load calculation in `sizing.py` actually chose,
so the member drawn is the member that was checked. Everything else -- railings, treads,
mullions, furniture -- is dimensioned by architectural convention and says so through
`sizing_status`, because presenting a handrail as a verified structural result would be
a lie of exactly the kind this project exists to avoid.
"""

from __future__ import annotations

import hashlib
import math
from typing import Iterable

from shapely.geometry import LineString, Point, Polygon, box as plan_box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from .datums import (
    DatumSet, Lattice, build_lattice, compile_datum_set,
    CORE_WALL_M, FLIGHT_TURN_M, HEADER_SETBACK_M, MIN_BAY_M, WELL_EDGE_M, flight_run,
)
from .grammar_specs import GRAMMAR_SPECS, GrammarSpec
from .ada import (
    CURB_HEIGHT_M, HANDRAIL_EXTENSION_M, MAX_RUN_RISE_M, MIN_CLEAR_WIDTH_M,
    MIN_LANDING_LENGTH_M, MIN_TURN_LANDING_M, RAMP_THICKNESS_M, RampLanding,
    RampPlan, RampRun, plan_switchback_ramp,
)
from .geometry import (
    BoxGeometry, CONVENTION_PROFILES, ExtrusionGeometry, MemberGeometry,
    ProfileSpec, Vector2, Vector3, bounds, convention_profile, inset, point_inside,
    profile_from_section_id, v2, v3,
)
from .roof import (
    PARAPET_UPSTAND_M,
    ROOF_ASSEMBLY_RULE,
    ROOF_CONTROL_RULE,
    ROOF_COPING_WIDTH_M,
    ROOF_DECK_THICKNESS_M,
    ROOF_PARAPET_INSULATION_UPSTAND_THICKNESS_M,
    ROOF_PARAPET_WIDTH_M,
    ROOF_PROFESSIONAL_REVIEW_ITEMS,
    ROOF_PROFESSIONAL_REVIEW_RULE,
    assert_roof_control_matches_level,
    roof_assembly_layers,
    roof_perimeter_geometries,
    roof_section_profile,
    validate_roof_emission,
)
from .loads import LoadCase, OCCUPANCY_LIVE, composite_steel_deck, flat_roof_assembly
from .massing import MASSING_FAMILIES
from .spatial_rules import check_spatial_rules
from .materials import MATERIALS as MATERIAL_LIBRARY
from .models import ArchitecturalScore, AudioFeatures
from .models_v3 import (
    BuildingModelV3, ElementGroup, ElementInstance, MemberSizingRecord, RankedOption,
)
from .axis import AxisSkeleton
from .furniture import furniture_parts, emit_furniture, usable_floor

from .envelope import emit_envelope
from .dependencies import (
    EXTRA_FLIGHT_PAIRS, SECOND_FLIGHT_PAIR, compile_dependency_graph,
)
from .constitution import validate_model
from .facade_gates import correction_for, evaluate
from .facade_control import controlled_facade_metadata, facade_control_for
from .life_safety import build as life_safety_graph
from .lateral_clearance import lateral_bay_clear
from .portals import inspect_portals
from .room_fixtures import inspect_room_layouts
from .archetypes import (
    C_VALUE_DESIGN_M, PORTAL_H_M, Carve, CarveRefusal, MuseumCarve, TheatreCarve,
    carve_for, evaluate_archetype,
)
from .briefs import brief_for
from .typology import kit_for
from .program import (
    DEFAULT_CIRCULATION_ALLOWANCE, LIBRARY_BRIEF, ProgramAllocation,
    UnplacedSpace, allocate_program, level_bands,
)
from .program_volume_contracts import (
    CirculationFinding, ResolvedCirculationPlan, covers_registered_footprint,
)
from .plan_regions import polygon as plan_polygon, extrusions as plan_extrusions
from .registry import catalogue, profile_for
from .partitions import (
    DOOR_CLEAR_M, DOOR_LEAF_M, required_separation, select_partition,
)
from .selection import select_massing, select_project
from .site import SiteParameters, resolve_site, to_jurisdiction
from .version import COMPILER_VERSION, compiler_source_fingerprint
from . import site_loads
from .validators import set_site_loads
from .sizing import select_beam, size_gravity_frame
from .tectonics import (
    ENVELOPE_TECTONICS, FRAME_TECTONICS, GRAMMAR_ENVELOPE, SYSTEM_BUILDABILITY,
    EnvelopeTectonic, FrameTectonic,
)

# The structural system was a module constant until the corpus test showed what
# that cost: fourteen recordings, fourteen steel frames. `selection.py` now picks
# it inside whatever the physical and code screens admit. This name survives only
# as the fallback for a run where nothing is admissible.
FALLBACK_SYSTEM_ID = 'STR-SYS-STEEL-FRAME'

# Anything whose position is read off a plate boundary is shaped by all four plate
# datums, not only by the one that is most obvious. Listing them accurately is what
# makes the reach column in the translation report mean something.
# How far in front of the building the accessible route may reach before it
# runs into the approach steps and the street. A site fact, not a score one.
from .approach import APRON_DEPTH_M, LANDING_OVERLAP_M, plan_boundary_switchback

PLATE_DATUMS = ('cantilever_m', 'plate_step_m', 'plate_rotation_deg', 'apse_radius_m')

class _Builder:
    """Accumulates elements and keeps the datum references honest."""

    def __init__(self, datums: DatumSet, lattice: Lattice) -> None:
        self.datums = datums
        self.lattice = lattice
        self.roof_control = lattice.roof_control
        # Filled by `_assemble` before any subsystem emitter runs.  Envelope and
        # circulation adapters may read the detailed allocation only as a fallback;
        # score-authored Program Volume regions travel on the lattice and remain the
        # preferred gross-form authority.
        self.program_allocation: ProgramAllocation | None = None
        # The centre-line skeleton every member registers to as it is emitted. Members
        # were already authored as centre-lines; this gives those lines shared nodes, so
        # "attached to" becomes an identity two members either share or do not, instead
        # of a distance that needs a tolerance to interpret.
        self.axis = AxisSkeleton()
        self.groups: dict[tuple, ElementGroup] = {}
        self.count = 0
        self.element_ids: set[str] = set()
        self.element_kinds: dict[str, str] = {}
        self.element_levels: dict[str, str] = {}
        self.profiles: dict[str, ProfileSpec] = dict(CONVENTION_PROFILES)
        # Levels no single stair core could reach, recorded by
        # `_emit_circulation` and reported on the model rather than left
        # for a reader to discover from a missing landing.
        self.unreached_levels: list[str] = []
        # The accessible route: a compliant plan, or the reason there is
        # none. Exactly one of these is set on every run.
        self.accessible_route: RampPlan | None = None
        self.unresolved_accessible_route: str | None = None
        self.public_stair_ids: list[str] = []
        self.circulation_plan: ResolvedCirculationPlan | None = None
        # Where the second egress stair landed, if one was placed. A plan
        # too small to hold two remote cores does not get a second one.
        self.second_stair_anchor: tuple[float, float] | None = None
        self.second_stair_levels: list[str] = []
        self.cores = core_anchors(lattice, datums)
        # What the floor framing did about the stair and lift openings, for the
        # limitations a reader is owed: girders that still cross an opening (a
        # transfer this compiler does not design), and the count of headers and
        # trimmers it did size. A floor system with no members to trim is listed.
        self.opening_conflicts: list[str] = []
        self.headers_emitted = 0
        self.trimmers_emitted = 0
        self.unframed_levels: list[str] = []
        self.world_xy_frame_notes: list[str] = []
        # The approach decided once -- entry landing, the ramp or the stair that
        # replaces it -- so the slab gives up their footprints before either is drawn.
        self.approach = _plan_approach(lattice, datums)
        # The lift as built: which occupied levels have a landing door, and the
        # sentence that says so, written by the emitter that knows.
        self.lift_served_levels: list[str] = []
        self.lift_note = ''
        self.furniture_omissions: list[str] = []
        from .room_fixtures import RoomLayoutPlan
        self.room_layout_plan = RoomLayoutPlan()

    def add_plate(self, element_id, kind, layer, subsystem, boundary, holes,
                  z_base, z_top, material, **metadata):
        for index, geometry in enumerate(plan_extrusions(boundary, holes, z_base, z_top)):
            part_id = element_id if index == 0 else f'{element_id}-P{index:02d}'
            self.add(part_id, kind, layer, subsystem, geometry, material, **metadata)

    def profile(self, spec: ProfileSpec) -> str:
        self.profiles[spec.id] = spec
        return spec.id

    def add(
        self, element_id: str, kind: str, layer: str, subsystem: str,
        geometry, material: str, *, category: str = 'public',
        program: str = 'structure', level_id: str = 'L00',
        lattice_index: dict[str, int] | None = None,
        datum_refs: Iterable[str] = (), supports: Iterable[str] = (),
        section_id: str | None = None, sizing_status: str = 'architectural_convention',
        utilisation: float | None = None, governing_check: str | None = None,
        rule_refs: Iterable[str] = (), reason: str = '',
        axis_ref: str | None = None, thickness_m: float | None = None,
        assembly_id: str | None = None, part_role: str | None = None,
    ) -> str:
        if element_id in self.element_ids:
            raise ValueError(f'duplicate element id: {element_id}')
        facade_control = getattr(self.lattice, 'facade_control', None)
        if facade_control is not None:
            assembly_id, part_role = controlled_facade_metadata(
                facade_control, level_id=level_id, semantic_layer=layer,
                subsystem=subsystem, kind=kind, assembly_id=assembly_id,
                part_role=part_role)
        centre, size = bounds(geometry)
        datum_tuple, rule_tuple = tuple(datum_refs), tuple(rule_refs)
        key = (kind, layer, subsystem, category, program, material, section_id,
               sizing_status, utilisation, governing_check, datum_tuple, rule_tuple,
               reason, thickness_m)
        group = self.groups.get(key)
        if group is None:
            group = ElementGroup(
                group_id=f'GRP-{layer}-{subsystem}-{kind}-{len(self.groups):03d}',
                kind=kind, semantic_layer=layer, subsystem=subsystem,
                category=category, program=program, material_profile=material,
                datum_refs=list(datum_tuple), section_id=section_id,
                thickness_m=thickness_m,
                sizing_status=sizing_status, utilisation=utilisation,
                governing_check=governing_check, rule_refs=list(rule_tuple),
                reason=reason, instances=[])
            self.groups[key] = group
        group.instances.append(ElementInstance(
            id=element_id, level_id=level_id, lattice_index=lattice_index or {},
            geometry=geometry, position=centre, dimensions=size,
            supports=list(supports), assembly_id=assembly_id, part_role=part_role))
        if isinstance(geometry, MemberGeometry):
            self.axis.segment(element_id, list(geometry.path), subsystem)
            for support_id in supports:
                if (subsystem in {'edge_closure', 'roof_closure', 'entrance'}
                        and self.element_kinds.get(support_id) in {'floor_slab','roof_deck'}):
                    # This terminal is checked against the slab solid by
                    # closure_solid_bearings, not attached to a nonexistent axis.
                    continue
                if (subsystem == 'auditorium_handrail'
                        and self.element_kinds.get(support_id) == 'railing'):
                    # Rail-to-post terminals are checked against actual box solids.
                    continue
                self.axis.attach(element_id, support_id)
        elif axis_ref is not None:
            # A solid modelled around an existing centre-line, not standing free.
            self.axis.wrap(element_id, axis_ref)
        self.element_ids.add(element_id)
        self.element_kinds[element_id] = kind
        self.element_levels[element_id] = level_id
        self.count += 1
        return element_id

    def ids(self, *, kinds: Iterable[str] | None = None,
            level_id: str | None = None) -> list[str]:
        allowed = set(kinds) if kinds is not None else None
        return sorted(
            element_id for element_id in self.element_ids
            if (allowed is None or self.element_kinds[element_id] in allowed)
            and (level_id is None or self.element_levels[element_id] == level_id))

    def member(self, points: list[Vector3], profile_id: str) -> MemberGeometry:
        return MemberGeometry(path=points, profile=profile_id)


# ---------------------------------------------------------------------------
# Sizing
# ---------------------------------------------------------------------------

def _record_axis_checks(b: _Builder):
    """Report what the centre-line skeleton found.

    Two findings are worth stating on the model rather than leaving to a reader.

    A member may declare a support it lands nowhere near. That was not hypothetical:
    a raker named "the first fascia on its level" by scanning a *set* of ids, and on one
    model drew a bearing to a member thirty-four metres away. Hash order is not a rule,
    and the only thing that catches it is measuring the joint the declaration implies.

    A member may also share no node with any other member. Some of those are correct --
    a stair stringer lands on a floor plate and a canopy post on a slab, and a plate has
    no centre-line to share -- so this is reported rather than failed, with the count
    that makes an unexplained jump visible.
    """
    from .models_v3 import AxisReport, DependencyCheck

    from collections import deque

    strained = sorted(b.axis.strained, key=lambda item: -item[2])
    isolated = b.axis.isolated()
    from .envelope import closure_solid_bearings
    closure_bearings, closure_misses = closure_solid_bearings(b)
    from .dependencies import rail_solid_bearings
    rail_bearings, rail_misses = rail_solid_bearings(b.groups.values())

    # Does the frame get to the ground along its own centre-lines, with no plate in
    # the path? Columns, girders, joists and bracing should; a truss bearing on the
    # roof plate legitimately should not, and is not asked to.
    frame_kinds = {'column', 'piloti_column', 'primary_beam', 'secondary_joist',
                   'heavy_joist', 'brace', 'knee_brace', 'outrigger_strut'}
    linked = b.axis.connections()
    # A ground-storey core wall stands on its raft as a ground column stands on its
    # pad: the footing is a solid with no centre-line, so the root is what stands on it.
    footing_borne_cores = {
        instance.id for group in b.groups.values() if group.kind == 'core_wall'
        for instance in group.instances
        if any(b.element_kinds.get(support) == 'footing' for support in instance.supports)}
    reached = {owner for owner in linked
               if b.element_kinds.get(owner) in ('footing', 'piloti_column')
               or owner in footing_borne_cores}
    queue = deque(reached)
    while queue:
        for neighbour in linked.get(queue.popleft(), ()):
            if neighbour not in reached:
                reached.add(neighbour)
                queue.append(neighbour)
    floating = sorted(owner for segment in b.axis.segments.values()
                      for owner in (segment.owner_id,)
                      if b.element_kinds.get(owner) in frame_kinds
                      and owner not in reached)
    plate_borne = sorted(
        owner for owner in isolated
        if b.element_kinds.get(owner) in {'stair_stringer', 'entry_canopy'}
        or owner in closure_bearings or owner in rail_bearings)
    unexplained = sorted(set(isolated) - set(plate_borne))
    checks = [
        DependencyCheck(
            id='AXIS-RAIL-SOLID-BEARING', status='failed' if rail_misses else 'passed',
            message=(f'{len(rail_bearings)} rails have both endpoints on their declared '
                     'solid posts. Every post and terminal is measured at 0.01 mm; '
                     'attachment strength remains unchecked.'),
            affected_ids=sorted(rail_misses)),
        DependencyCheck(
            id='AXIS-CLOSURE-SOLID-BEARING',
            status='failed' if closure_misses else 'passed',
            message=(f'{len(closure_bearings)} closure member terminals meet their '
                     'declared slab material, measured against its polygon minus holes '
                     'and actual height; no slab centre-line is invented. Attachment '
                     'strength is not checked.' +
                     (f' {len(closure_misses)} terminals lack that measured contact.'
                      if closure_misses else '')),
            affected_ids=sorted(closure_misses)),
        DependencyCheck(
            id='AXIS-DECLARED-BEARING-MEETS',
            status='passed' if not strained else 'failed',
            message=('Every declared bearing joins two centre-lines that are within a '
                     'section depth of each other.' if not strained else
                     'Some members declare a support their centre-line does not reach.'),
            affected_ids=[owner for owner, _host, _gap in strained]),
        DependencyCheck(
            id='AXIS-MEMBER-CONNECTIVITY',
            status='passed' if not unexplained else 'failed',
            message=(f'{len(b.axis.segments)} centre-lines over {b.axis.node_count} '
                     f'nodes; members sharing no node with another member are the '
                     f'{len(plate_borne)} supported by plates or measured solid posts, '
                     'which carry no member axis.'
                     if not unexplained else
                     'Some members share no node with any other member and do not bear '
                     'on a verified solid host.'),
            affected_ids=unexplained),
        DependencyCheck(
            id='AXIS-FRAME-TO-GROUND',
            status='passed' if not floating else 'failed',
            message=('Every column, girder, joist and brace reaches the foundation '
                     'along shared centre-line nodes, with no plate in the path.'
                     if not floating else
                     'Some frame members reach no foundation through the skeleton.'),
            affected_ids=sorted(set(floating))),
    ]
    return AxisReport(
        status='failed' if any(check.status == 'failed' for check in checks) else 'passed',
        node_count=b.axis.node_count, segment_count=len(b.axis.segments),
        checks=checks)


def _catalogues(frame: FrameTectonic):
    """The section catalogue the chosen material is actually checked against.

    A timber frame sized from the steel catalogue would report an I-section with a
    glulam material id, and `check_beam` would then apply NDS allowable stresses to
    a shape no sawmill produces. The catalogue and the capacity equations have to
    agree, so they are chosen together.
    """
    # Asked of the material, not pattern-matched on its name. `column_material` is a
    # palette key doing two jobs: it says what the frame looks like *and* it chose the
    # capacity equations. That worked while the keys happened to read 'timber' and
    # 'concrete'; a frame specified as `timber_light` would have failed `== 'timber'`
    # and had its glulam columns checked against AISC steel, silently and with a
    # plausible-looking utilisation on the end of it.
    family = MATERIAL_LIBRARY[frame.column_material].family         if frame.column_material in MATERIAL_LIBRARY else frame.column_material
    if family == 'timber':
        return catalogue('glulam'), catalogue('glulam')
    if family in ('concrete', 'masonry'):
        return catalogue('concrete_cast'), catalogue('concrete_cast')
    # Beams from the W range, columns from the W column range plus square HSS: a
    # beam-proportioned shape makes a poor column and the registry keeps them apart.
    return (catalogue('steel_w_shape'),
            sorted(catalogue('steel_w_shape') + catalogue('steel_hss_square'),
                   key=lambda section: section.area_mm2))


def _run_sizing(datums: DatumSet, lattice: Lattice, allocation: ProgramAllocation,
                frame: FrameTectonic):
    """Size the frame against the program that was actually allocated.

    The beam tier is sized for the heaviest room in the building, because a girder does
    not know which floor it is on until the layout is fixed. The column stack sums the
    real per-level loads instead of repeating that worst case on every storey, which is
    the difference between a column sized for a library of stack rooms and one sized for
    a library that has one.
    """
    beam_catalogue, column_catalogue = _catalogues(frame)
    deck, roof = composite_steel_deck(), flat_roof_assembly()
    live_by_id = {key: value.live_kpa for key, value in OCCUPANCY_LIVE.items()}

    governing_id = 'office'
    per_level: list[float] = []
    for level in lattice.occupied:
        occupancy_id = allocation.governing_occupancy(level.index, live_by_id)
        per_level.append(live_by_id[occupancy_id])
        if live_by_id[occupancy_id] > live_by_id[governing_id]:
            governing_id = occupancy_id

    return OCCUPANCY_LIVE[governing_id], size_gravity_frame(
        bay_x_m=(lattice.world_xy_grid.spacing_x if lattice.world_xy_grid
                 else datums.value('bay_x_m')),
        bay_y_m=(lattice.world_xy_grid.spacing_y if lattice.world_xy_grid
                 else datums.value('bay_y_m')),
        joist_spacing_m=datums.value('joist_spacing_m'),
        floor_to_floor_m=datums.value('floor_to_floor_m'),
        storeys=len(lattice.levels), plan_x_m=lattice.plan_x_m,
        plan_y_m=lattice.plan_y_m,
        occupancy=OCCUPANCY_LIVE[governing_id],
        roof_occupancy=OCCUPANCY_LIVE['roof_ordinary'],
        superimposed_dead_kpa=deck.superimposed_dead_kpa(),
        roof_dead_kpa=roof.superimposed_dead_kpa(),
        beam_catalogue=beam_catalogue, column_catalogue=column_catalogue,
        per_level_live_kpa=per_level)


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def _on_plate(plate, x: float, y: float, tolerance: float = 0.01) -> bool:
    """Whether a grid node stands on this plate, its boundary included.

    The plates are cut from the same plan bounds the grid lines are drawn on, so the
    outermost lines run exactly along the plate edge -- and a ray-casting inside test
    answers a point on an edge by which way the edge happens to run. It said yes on
    the south and west edges and no on the north and east, so every building stood
    its columns on three sides and framed nothing along the fourth: no columns on
    the north line, no girders on it, and the whole top row of joists missing on
    every level. A node within a centimetre of the boundary is on the plate.
    """
    if point_inside(plate, x, y):
        return True
    count = len(plate)
    for index in range(count):
        a, b = plate[index], plate[(index + 1) % count]
        dx, dy = b.x - a.x, b.y - a.y
        length2 = dx * dx + dy * dy
        if length2 <= 1e-12:
            continue
        t = max(0.0, min(1.0, ((x - a.x) * dx + (y - a.y) * dy) / length2))
        if math.hypot(x - (a.x + t * dx), y - (a.y + t * dy)) <= tolerance:
            return True
    return False


def _parallel_inset_ring(plate, amount: float, label: str) -> list[Vector2]:
    """Return one true parallel inner ring for a physical perimeter member.

    The general ``geometry.inset`` keeps legacy convex output stable through a radial
    move. Program Volume boundary members need a measured face offset instead: their
    outside face must meet the authored union while their complete body stays inside.
    """
    shifted = Polygon([(point.x, point.y) for point in plate]).buffer(
        -amount, join_style=2)
    if shifted.is_empty or shifted.geom_type != 'Polygon':
        raise ValueError(
            f'Program Volume {label} inset {amount:.3f} m produced '
            f'{shifted.geom_type}; one continuous perimeter is required')
    shifted = orient(shifted, sign=1.0)
    return [v2(round(float(x), 6), round(float(y), 6))
            for x, y in list(shifted.exterior.coords)[:-1]]


def _segment_crosses_rect(ax: float, ay: float, bx: float, by: float,
                          rect: tuple[float, float, float, float]) -> bool:
    """Whether an axis-aligned member runs through the interior of a plan rectangle."""
    x0, y0, x1, y1 = rect
    if abs(ay - by) < 1e-9:
        return (y0 + 0.05 < ay < y1 - 0.05
                and min(ax, bx) < x1 - 0.05 and max(ax, bx) > x0 + 0.05)
    if abs(ax - bx) < 1e-9:
        return (x0 + 0.05 < ax < x1 - 0.05
                and min(ay, by) < y1 - 0.05 and max(ay, by) > y0 + 0.05)
    return False


def _point_load_tributary(cut_span_m: float, header_span_m: float, a_m: float,
                          trimmer_span_m: float) -> float:
    """The extra tributary width a trimmer joist carries for one header reaction.

    A header at an opening edge collects the trimmed joists' reactions -- each
    trimmed joist delivers half its remaining span -- and lands them as a point load
    on the trimmer joist beside the opening, at `a_m` from the trimmer's support.
    `check_beam` sizes uniform loads, so the point load is expressed as the uniform
    load producing the same maximum moment (8·M/L²), stated per kPa of floor load
    so it adds to the trimmer's own spacing as metres of tributary width. Hand
    check: R = w·(Lcut/2)·(Lh/2); M = R·a·(L−a)/L; w_eq = 8M/L².
    """
    reaction_per_kpa = (cut_span_m / 2.0) * (header_span_m / 2.0)
    moment_per_kpa = reaction_per_kpa * a_m * (trimmer_span_m - a_m) / trimmer_span_m
    return 8.0 * moment_per_kpa / trimmer_span_m ** 2


# The exit door into the stair core: a pair of leaves, wider than the 1.2 m planning
# clear width the egress walker needs plus its wall allowance, and taller than the
# 2.1 m use height below which a solid counts as an obstacle.
CORE_DOOR_W_M = 1.6
# The strip beyond a landing face that a core's exit door may open onto: the door
# leaf swung out and a person beside it. Narrower than this, the door faces the
# plate's interior instead.
CORE_DOOR_ROOM_M = 2.0
CORE_DOOR_H_M = 2.4
# Existing route terminal offset beyond the planning body's radius. It keeps its
# centre off the buffered wall boundary; it is not a door-swing/code clearance.
CORE_TERMINAL_GAP_M = 0.1
# The landing-side threshold crosses the whole core wall and bears onto both adjacent
# floor surfaces.  Fifty millimetres at each edge is a geometric bearing used to keep
# the emitted walking surface continuous through the aperture after the 600 mm route
# body is applied; it is not a proprietary sill or a finished-door detail.
CORE_THRESHOLD_BEARING_M = 0.05
# A lift sill crosses the shaft-wall thickness as a coordination surface. It is
# a geometric threshold, not a lift manufacturer's sill, waterproofing, or code
# detail.
LIFT_THRESHOLD_THICKNESS_M = 0.15
CORE_WALL_FC_KPA = 30_000.0   # f'c 30 MPa, as kN/m2
CORE_WALL_DENSITY_KN_M3 = 24.0


def _core_wall_check(demand_kn: float, length_m: float, storey_m: float
                     ) -> tuple[float, str]:
    """Utilisation of a plain reinforced-concrete bearing wall, and its basis.

    ACI 318 empirical wall design: phi Pn = 0.55 phi f'c Ag [1 - (k lc / 32 h)^2], with
    phi 0.65, f'c 30 MPa, k 1.0 (braced top and bottom), lc the storey height and h the
    wall thickness. A screening check of the gravity load path only: reinforcement,
    openings, in-plane shear and the lateral system are not designed here.
    """
    slenderness = 1.0 - (storey_m / (32.0 * CORE_WALL_M)) ** 2
    capacity = 0.55 * 0.65 * CORE_WALL_FC_KPA * (CORE_WALL_M * length_m) * max(0.05, slenderness)
    return (demand_kn / capacity if capacity > 0 else float('inf'),
            'ACI 318 11.5.3 empirical bearing wall (phi 0.65, f\'c 30 MPa, k 1.0)')


def _wall_axis(fx0: float, fy0: float, fx1: float, fy1: float, z0: float,
               z1: float) -> list:
    """A core wall's centre-lines for the axis skeleton: up its middle, then along
    its top in the centre plane. A wall is a solid, but the frame that bears on it
    is drawn as centre-lines, and a girder ending at a wall with no line to share a
    node with read as floating -- the skeleton could not see the wall carry it.
    `z1` is the storey line, not the solid's top under the slab: the wall above
    starts there, so the two storeys meet at one node by identity, the way a
    column stack does, rather than by a bearing measured across the slab.
    """
    cx, cy = (fx0 + fx1) / 2.0, (fy0 + fy1) / 2.0
    if fx1 - fx0 >= fy1 - fy0:
        a, c = v3(fx0, cy, z1), v3(fx1, cy, z1)
    else:
        a, c = v3(cx, fy0, z1), v3(cx, fy1, z1)
    return [v3(cx, cy, z0), v3(cx, cy, z1), a, c]


def _emit_core_walls(b: _Builder, lower, upper, core_boxes, slab_t: float, floor_case,
                     deck_dead_kpa: float, material: str) -> dict[tuple[int, str], str]:
    """The stair cores' walls for one storey, and the footing they stand on.

    A stair core is structure (decision 0022): reinforced-concrete walls on the
    four faces of the volume the grid was drawn to, from a footing to the roof,
    carrying the floor framing that meets them, the landings inside them and their
    own weight. The wall on the landing side has the exit door in it -- two jambs and
    a head -- so the route into the stair is a real aperture the portal and egress
    reports can measure, not a wall a person is assumed to pass through.

    Returns the support id for each (core index, face) at this storey: the wall, or
    the head over the door, which is what the floor framing above the door bears on.
    The load check is a gravity screening of the wall as a bearing wall from this
    storey up; it does not design reinforcement, the lateral system or the joints.
    """
    lattice = b.lattice
    anchors = b.cores
    width, run = anchors['width'], anchors['run']
    layout = _core_layout(anchors)
    t = CORE_WALL_M
    z0, z1 = lower.z, upper.z - slab_t
    if z1 - z0 < 0.5:
        return {}
    factored_kpa, combination = LoadCase(dead_kpa=deck_dead_kpa,
                                         live_kpa=floor_case.live_kpa).lrfd()
    supports_out: dict[tuple[int, str], str] = {}
    for ci, ((ax, ay), served, _tags, label, facing) in enumerate(layout):
        served_ids = [level.id for level in served]
        if upper.id not in served_ids or lower.id not in served_ids:
            continue
        # A near-grade registration plane can leave no exposed wall below the
        # first occupied floor. The first actual wall still needs a raft: level
        # index zero is not a reliable synonym for its physical base.
        first_wall = next(a for a,c in zip(lattice.levels,lattice.levels[1:])
                          if a.id in served_ids and c.id in served_ids
                          and c.z-slab_t-a.z >= 0.5)
        at_base = lower.index == first_wall.index
        bx0, by0, bx1, by1 = core_boxes[ci]
        run_axis = _core_run_axis(anchors, (ax, ay))
        landing_face = (('W' if facing > 0 else 'E') if run_axis == 'x'
                        else ('S' if facing > 0 else 'N'))
        storeys_above = [level for level in served if level.index > lower.index]

        # Gravity demand at the base of this storey: every storey of wall above,
        # and at every level above the floor the walls carry -- the core interior
        # outside the well, and half of each bay the framing spans onto the faces.
        well = _opening_span(ax, ay, width, run, facing, run_axis)
        interior = (bx1 - bx0) * (by1 - by0) - (well[2] - well[0]) * (well[3] - well[1])
        xl, yl = lattice.x_lines, lattice.y_lines
        west = max((x for x in xl if x < bx0 - 0.05), default=None)
        east = min((x for x in xl if x > bx1 + 0.05), default=None)
        south = max((y for y in yl if y < by0 - 0.05), default=None)
        north = min((y for y in yl if y > by1 + 0.05), default=None)
        outside = ((bx0 - west) / 2.0 * (by1 - by0) if west is not None else 0.0) \
            + ((east - bx1) / 2.0 * (by1 - by0) if east is not None else 0.0) \
            + ((by0 - south) / 2.0 * (bx1 - bx0) if south is not None else 0.0) \
            + ((north - by1) / 2.0 * (bx1 - bx0) if north is not None else 0.0)
        perimeter = 2.0 * ((bx1 - bx0) + (by1 - by0)) - CORE_DOOR_W_M
        demand = 0.0
        for level in storeys_above:
            below = lattice.levels[level.index - 1]
            demand += 1.2 * CORE_WALL_DENSITY_KN_M3 * t * perimeter * (level.z - below.z)
            demand += factored_kpa * max(0.0, interior + outside)
        utilisation, basis = _core_wall_check(demand, perimeter, upper.z - lower.z)
        sizing_kwargs = dict(section_id=f'RC-WALL-{t * 1000:.0f}',
                             sizing_status='sized_by_calculation',
                             utilisation=round(utilisation, 4), governing_check=basis)

        def support_below(face_tag: str) -> list[str]:
            if at_base:
                return [f'STR-FDN-CORE-{label}']
            return [f'STR-CWL-{label}-{face_tag}-{lattice.levels[lower.index - 1].id}']

        if at_base:
            grade = lattice.levels[0]
            raft_bottom, raft_top = grade.z - 0.9, lower.z
            b.add(f'STR-FDN-CORE-{label}', 'footing', 'structure', 'foundations',
                  BoxGeometry(center=v3((bx0 + bx1) / 2.0, (by0 + by1) / 2.0,
                                        (raft_bottom + raft_top) / 2.0),
                              size=v3(bx1 - bx0 + 0.6, by1 - by0 + 0.6, raft_top-raft_bottom)),
                  'concrete', level_id=grade.id, lattice_index={'core': ci, 'level': lower.index},
                  datum_refs=['flight_width_m'],
                  rule_refs=['STR-LOAD-PATH-FOUNDATION-001'],
                  reason=(f'Raft footing under stair core {label}: the core walls end '
                          f'their gravity path here. {demand:.0f} kN factored at the '
                          f'base. Top follows the first emitted wall base; bottom '
                          f'is the practice embedment below grade. Soils and foundation '
                          f'capacity remain unresolved.'))

        faces = {
            'W': (bx0, by0, bx0 + t, by1),
            'E': (bx1 - t, by0, bx1, by1),
            'S': (bx0 + t, by0, bx1 - t, by0 + t),
            'N': (bx0 + t, by1 - t, bx1 - t, by1),
        }
        common = dict(category='service', program='vertical_circulation',
                      level_id=lower.id, datum_refs=['flight_width_m', 'floor_to_floor_m'],
                      rule_refs=['STR-CORE-WALL-001', 'STR-LOAD-PATH-FOUNDATION-001'])
        reason = (f'Reinforced-concrete core wall of stair {label}: the frame stops at '
                  f'its face and bears on it. Screened as a bearing wall for '
                  f'{demand:.0f} kN factored ({combination}) at this storey\'s base '
                  f'({utilisation:.2f} utilisation); reinforcement, in-plane shear and '
                  f'the lateral role are not designed.')
        for face_tag, (fx0, fy0, fx1, fy1) in faces.items():
            wall_id = f'STR-CWL-{label}-{face_tag}-{lower.id}'
            if face_tag != landing_face:
                b.add(wall_id, 'core_wall', 'structure', 'cores',
                      BoxGeometry(center=v3((fx0 + fx1) / 2.0, (fy0 + fy1) / 2.0, (z0 + z1) / 2.0),
                                  size=v3(fx1 - fx0, fy1 - fy0, z1 - z0)),
                      material, lattice_index={'core': ci, 'level': lower.index},
                      supports=support_below(face_tag), reason=reason, **sizing_kwargs,
                      **common)
                b.axis.segment(wall_id, _wall_axis(fx0, fy0, fx1, fy1, z0, upper.z), 'cores')
                supports_out[(ci, face_tag)] = wall_id
                continue
            # The landing wall: two jambs, the head over the door, and the door. The
            # framing that meets this face bears on whichever piece stands where it
            # arrives, so pieces carry extents along the actual World XY face.
            along_y = face_tag in ('W', 'E')
            centre = ay if along_y else ax
            door_x0, door_x1 = centre - CORE_DOOR_W_M / 2.0, centre + CORE_DOOR_W_M / 2.0

            def piece_bounds(lo, hi):
                return (fx0, lo, fx1, hi) if along_y else (lo, fy0, hi, fy1)

            def piece_geometry(lo, hi, bottom, top):
                px0, py0, px1, py1 = piece_bounds(lo, hi)
                return BoxGeometry(center=v3((px0+px1)/2, (py0+py1)/2, (bottom+top)/2),
                                   size=v3(px1-px0, py1-py0, top-bottom))

            pieces: list[tuple[float, float, str]] = []
            jambs = {'JA': (fy0 if along_y else fx0, door_x0),
                     'JB': (door_x1, fy1 if along_y else fx1)}
            for jamb_tag, (jx0, jx1) in jambs.items():
                if jx1 - jx0 < 0.05:
                    continue
                b.add(f'{wall_id}-{jamb_tag}', 'core_wall', 'structure', 'cores',
                      piece_geometry(jx0, jx1, z0, z1),
                      material, lattice_index={'core': ci, 'level': lower.index},
                      supports=[f'{s}-{jamb_tag}' if not at_base else s
                                for s in support_below(face_tag)],
                      reason=reason, **sizing_kwargs, **common)
                b.axis.segment(f'{wall_id}-{jamb_tag}',
                               _wall_axis(*piece_bounds(jx0, jx1), z0, upper.z), 'cores')
                pieces.append((jx0, jx1, f'{wall_id}-{jamb_tag}'))
            head_z0 = z0 + CORE_DOOR_H_M
            if z1 - head_z0 > 0.05:
                b.add(f'{wall_id}-HD', 'core_wall', 'structure', 'cores',
                      piece_geometry(door_x0, door_x1, head_z0, z1),
                      material, lattice_index={'core': ci, 'level': lower.index},
                      supports=[f'{wall_id}-JA', f'{wall_id}-JB'],
                      reason='Head of the core wall over the exit door, spanning jamb '
                             'to jamb; the floor framing above the door bears on it.',
                      **sizing_kwargs, **common)
                b.axis.segment(f'{wall_id}-HD',
                               _wall_axis(*piece_bounds(door_x0, door_x1), head_z0, upper.z), 'cores')
                pieces.append((door_x0, door_x1, f'{wall_id}-HD'))
            if pieces:
                supports_out[(ci, face_tag)] = pieces
            if lower.kind != 'roof':
                # Subsystem 'stairs', not 'vertical_core': the portal report reads a
                # vertical-core door as a lift landing door and asks for a car floor
                # behind it. This one opens onto the stair landing.
                b.add(f'CIR-COR-{label}-{lower.id}-DR', 'door', 'circulation', 'stairs',
                      piece_geometry(door_x0, door_x1, z0, z0 + CORE_DOOR_H_M),
                      'frame_dark', category='service', program='vertical_circulation',
                      level_id=lower.id, lattice_index={'core': ci, 'level': lower.index},
                      # The door hangs in its frame: the jambs either side of it.
                      supports=[piece for piece in (f'{wall_id}-JA', f'{wall_id}-JB')
                                if piece in b.element_ids],
                      datum_refs=['flight_width_m'], rule_refs=['IBC-1010.1.1'],
                      reason=(f'Exit door into stair core {label}, {CORE_DOOR_W_M * 1000:.0f} mm '
                              f'clear by {CORE_DOOR_H_M * 1000:.0f} mm, in the landing-side '
                              f'core wall. A real aperture; hardware, rating and swing '
                              f'are not modelled.'))
    return supports_out


def _emit_structure(b: _Builder, sizing, frame: FrameTectonic, occupancy, *,
                    carve=None) -> None:
    """Emit the gravity frame in the tectonic family the selection chose.

    Three things change between families and all three are visible in a study model:
    the material and therefore the section the catalogue offers, the floor system
    (ribs, a blank soffit on drop panels, or panel bands), and the lateral vocabulary
    (a diagonal, a wall plane, or a triangulated joint at every connection).

    What does not change here, and should: `bay_span_factor` is declared on the
    tectonic but not applied, because the lattice is built before the selection runs
    and the bay spacing is fixed by then. A timber frame therefore spans as far as a
    steel one did, which is generous to it. The limitation is recorded on the model
    rather than hidden by quietly resizing the members.
    """
    from .transfer_structure import (prepare_transfer, emit_transfer,
                                    post_id, edge_column_id, retained_edge_segments)
    from .hall_enclosure import replaces_framing
    lattice, datums = b.lattice, b.datums
    transfer_report = prepare_transfer(b, sizing, frame, occupancy, carve)
    active_transfers = {candidate.x_index: candidate for candidate in transfer_report.frames
                        if candidate.activated}
    transfer_piers = {pier.id: pier.check for candidate in active_transfers.values()
                      for pier in candidate.piers}
    if active_transfers:
        transfer_piers.update({pier.id:pier.check for pier in transfer_report.boundary_piers})
    transfer_edges = transfer_report.edges if active_transfers else []
    for edge in transfer_edges:
        if edge.regular_x_index is not None:
            for j in edge.y_indices:
                if j < len(lattice.y_lines) and abs(edge.y_coordinates[j]-lattice.y_lines[j]) < 1e-7:
                    for k in range(edge.level_index):
                        transfer_piers[edge_column_id(edge,j,k,lattice)] = edge.check
    def sized_profile(section_id: str) -> str:
        # The registry first: a real designation has no dimensions in its name.
        spec = profile_for(section_id)
        return b.profile(spec if spec else profile_from_section_id(section_id))

    column_profile = sized_profile(sizing.column.check.section_id)
    girder_profile = sized_profile(sizing.beam.check.section_id)
    joist_profile = sized_profile(sizing.joist.check.section_id)
    piloti_profile = column_profile

    col_util, col_gov = sizing.column.check.max_ratio, sizing.column.check.governing
    gir_util, gir_gov = sizing.beam.check.max_ratio, sizing.beam.check.governing
    jst_util, jst_gov = sizing.joist.check.max_ratio, sizing.joist.check.governing

    # The opening framing is sized here, member by member, against the same floor
    # case the frame takedown used: a header carries a real share of the floor and
    # gets a real section from the same catalogue, or it says it could not.
    beam_catalogue, _column_catalogue = _catalogues(frame)
    floor_case = LoadCase(dead_kpa=composite_steel_deck().superimposed_dead_kpa(),
                          live_kpa=occupancy.live_kpa)

    # The section the calculation chose already carries the material's proportion --
    # a glulam catalogue returns a member far wider than a rolled steel one at the
    # same capacity -- so the drawn member needs no correction factor on top of it.
    col_mat = frame.column_material
    beam_mat = frame.beam_material
    joist_mat = 'steel_light' if frame.column_material == 'steel_white' else frame.beam_material
    deck_dead_kpa = composite_steel_deck().superimposed_dead_kpa()

    # The stair cores (decision 0022): the volumes the grid was drawn to. No column
    # stands inside one or on its faces -- the core walls stand there.
    core_boxes = _core_rects(b.cores)

    def node_in_core(x: float, y: float) -> bool:
        return any(bx0 - 0.05 <= x <= bx1 + 0.05 and by0 - 0.05 <= y <= by1 + 0.05
                   for bx0, by0, bx1, by1 in core_boxes)

    fascia = 'FASCIA-200x550'
    strut = 'STRUT-CHS180'

    # Program Volume authoring lines are preserved for rooms and boundary review,
    # while the structural lattice normally uses their cell centres.  Core framing
    # may insert additional lines later, and on a split wing a few of those lines can
    # coincide with an exterior face.  A centre point on the plate is insufficient:
    # half of a real column or girder then sits outside the authored volume.  These
    # two predicates measure the complete plan breadth before a PV structural member
    # is emitted.  Legacy massings retain their historical point/midpoint test.
    safe_plate_cache: dict[tuple[str, float], object] = {}
    plate_material_cache: dict[str, object] = {}
    unresolved_joists: list[str] = []

    def plate_material(level):
        if level.id not in plate_material_cache:
            material = Polygon(
                [(point.x, point.y) for point in level.plate],
                holes=[[(point.x, point.y) for point in ring]
                       for ring in level.voids],
            )
            if lattice.world_xy_grid is not None:
                # Independent lines may cross cores. Remove the actual keep-outs
                # locally; moving the entire world grid would erase its authority.
                from shapely.geometry import box as plan_box
                for rect in core_boxes + _opening_rects(b.cores, level.id):
                    material = material.difference(plan_box(*rect))
            plate_material_cache[level.id] = material
        return plate_material_cache[level.id]

    def safe_plate(level, clearance: float):
        key = (level.id, round(clearance, 6))
        if key not in safe_plate_cache:
            safe_plate_cache[key] = plate_material(level).buffer(
                -(clearance + 1.0e-6), join_style=2)
        return safe_plate_cache[key]

    def emit_joist(member_id, level, x, y0, y1, z, profile, kind, material, **metadata):
        geometry = b.member([v3(x, y0, z), v3(x, y1, z)], profile)
        if lattice.program_volume_regions or lattice.world_xy_grid is not None:
            # These members run along World Y with an upright section. Their
            # complete flange width, including the rounded emitted coordinates,
            # must fit; an inside midpoint cannot see an intervening notch/void.
            half_width = b.profiles[profile].width_m / 2.0
            a, c = geometry.path
            footprint = plan_box(a.x-half_width, min(a.y,c.y),
                                 a.x+half_width, max(a.y,c.y))
            if not covers_registered_footprint(plate_material(level), footprint):
                # The caller supplies the actual girders/headers. Cutting at a
                # geometric boundary would leave a free end without such a host.
                unresolved_joists.append(member_id)
                return False
        b.add(member_id, kind, 'structure', 'beams', geometry, material,
              level_id=level.id, **metadata)
        return True

    column_clearance = max(
        b.profiles[column_profile].width_m,
        b.profiles[column_profile].depth_m,
    ) / 2.0
    girder_clearance = b.profiles[girder_profile].width_m / 2.0

    from .core_access import column_access_regions
    column_keepouts = column_access_regions(lattice,b.datums,b.approach)

    def structural_node_on_plate(level, x: float, y: float) -> bool:
        body = plan_box(x-column_clearance,y-column_clearance,x+column_clearance,y+column_clearance)
        if any(body.intersection(region).area > 1e-7
               for region in column_keepouts[level.id]):
            return False
        if not lattice.program_volume_regions and lattice.world_xy_grid is None:
            return _on_plate(level.plate, x, y)
        region = safe_plate(level, column_clearance)
        return not region.is_empty and region.covers(Point(x, y))

    def structural_axis_on_plate(level, x0: float, y0: float,
                                 x1: float, y1: float) -> bool:
        if not lattice.program_volume_regions and lattice.world_xy_grid is None:
            return _on_plate(level.plate, (x0 + x1) / 2.0, (y0 + y1) / 2.0)
        region = safe_plate(level, girder_clearance)
        return (not region.is_empty
                and region.covers(LineString([(x0, y0), (x1, y1)])))

    # --- columns and footings: node (i, j, k) -> (i, j, k+1) --------------------
    for xi, x in enumerate(lattice.x_lines):
        for yj, y in enumerate(lattice.y_lines):
            for k in range(len(lattice.levels) - 1):
                lower, upper = lattice.levels[k], lattice.levels[k + 1]
                candidate_id = f'STR-{"PIL" if k==0 else "COL"}-X{xi:02d}-Y{yj:02d}-{lower.id}'
                # STF-INV-02: a column exists only where every plate from the first
                # occupied level up to the one it supports contains the node, so the
                # stack is continuous by construction rather than by inspection.
                if (candidate_id not in transfer_piers
                        and not all(structural_node_on_plate(lattice.levels[j], x, y)
                                    for j in range(1, k + 2))):
                    continue
                if node_in_core(x, y):
                    continue   # the core wall carries here, from its own footing
                transfer = active_transfers.get(xi)
                transferred_node = (transfer is not None
                                    and yj in transfer.y_indices[1:-1])
                # Removed floors require no short columns under their old grid
                # nodes. Some stacks stop below the transfer floor because the
                # upper mass retreats; retire those unloaded stubs as well.
                clear_node = (active_transfers and carve is not None
                              and any(r[0]+.30 < x < r[2]-.30 and r[1]+.30 < y < r[3]-.30
                                      for r in (carve.house,carve.stage)))
                transfer_index = next(iter(active_transfers.values())).level_index if active_transfers else 0
                if clear_node and lattice.occupied[0].index <= k < transfer_index:
                    continue
                index = {'x': xi, 'y': yj, 'level': k}
                is_piloti = k == 0
                footing_id = f'STR-FDN-X{xi:02d}-Y{yj:02d}'
                if is_piloti:
                    b.add(footing_id, 'footing', 'structure', 'foundations',
                          BoxGeometry(center=v3(x, y, -0.45), size=v3(1.6, 1.6, 0.9)),
                          'concrete', level_id='L00', lattice_index=index,
                          datum_refs=['bay_x_m', 'bay_y_m'],
                          rule_refs=['STR-LOAD-PATH-FOUNDATION-001'],
                          reason='Pad foundation terminates one explicit gravity path; '
                                 'soils remain unresolved.')
                    support_id = footing_id
                else:
                    below = lattice.levels[k - 1]
                    prefix = 'PIL' if k == 1 else 'COL'
                    support_id = f'STR-{prefix}-X{xi:02d}-Y{yj:02d}-{below.id}'
                if transferred_node and k == transfer.level_index:
                    support_id = post_id(transfer,yj)
                member_id = f'STR-{"PIL" if is_piloti else "COL"}-X{xi:02d}-Y{yj:02d}-{lower.id}'
                member_check = transfer_piers.get(member_id) or sizing.column.check
                b.add(
                    member_id,
                    'piloti_column' if is_piloti else 'column', 'structure', 'columns',
                    b.member([v3(x, y, lower.z), v3(x, y, upper.z)],
                             sized_profile(member_check.section_id)),
                    col_mat, category='service' if y > 6.0 else 'public',
                    level_id=lower.id, lattice_index=index,
                     datum_refs=['bay_x_m', 'bay_y_m', 'floor_to_floor_m',
                                 'ground_open_height_m' if is_piloti else 'floor_to_floor_m'],
                    supports=[support_id],
                    section_id=member_check.section_id,
                    sizing_status='sized_by_calculation', utilisation=member_check.max_ratio,
                    governing_check=member_check.governing,
                    rule_refs=['STR-STEEL-GRAVITY-001', 'STF-INV-01'],
                    reason=('Column carries the tributary bay from every level above to '
                            'a footing through an explicit node chain.'
                            + (' Resized for the explicitly calculated theatre transfer reaction.'
                               if member_id in transfer_piers else '')))

    from .world_xy_frame import emit_boundary_columns, emit_boundary_spans
    emit_transfer(b, transfer_report, beam_mat)
    b.world_xy_frame_notes = emit_boundary_columns(
        b, column_profile, col_mat, core_boxes,
        lambda level_id: _opening_rects(b.cores, level_id))

    # --- radial columns on the apsidal end -------------------------------------
    for ai, node in enumerate(lattice.apse_nodes):
        for k in range(len(lattice.levels) - 1):
            lower, upper = lattice.levels[k], lattice.levels[k + 1]
            is_piloti = k == 0
            footing_id = f'STR-FDN-A{ai:02d}'
            if is_piloti:
                b.add(footing_id, 'footing', 'structure', 'foundations',
                      BoxGeometry(center=v3(node.x, node.y, -0.45),
                                  size=v3(1.4, 1.4, 0.9)),
                      'concrete', level_id='L00', lattice_index={'apse': ai},
                      datum_refs=['apse_radius_m'],
                      rule_refs=['STR-LOAD-PATH-FOUNDATION-001'],
                      reason='Pad foundation under a radial column.')
                support_id = footing_id
            else:
                below = lattice.levels[k - 1]
                prefix = 'PIL' if k == 1 else 'COL'
                support_id = f'STR-{prefix}-A{ai:02d}-{below.id}'
            b.add(
                f'STR-{"PIL" if is_piloti else "COL"}-A{ai:02d}-{lower.id}',
                'piloti_column' if is_piloti else 'column', 'structure', 'columns',
                b.member([v3(node.x, node.y, lower.z), v3(node.x, node.y, upper.z)],
                         piloti_profile if is_piloti else column_profile),
                col_mat, level_id=lower.id,
                lattice_index={'apse': ai, 'level': k},
                datum_refs=['apse_radius_m', 'floor_to_floor_m'],
                supports=[support_id],
                section_id=sizing.column.check.section_id,
                sizing_status='sized_by_calculation', utilisation=col_util,
                governing_check=col_gov, rule_refs=['STR-STEEL-GRAVITY-001'],
                reason='Radial column follows the apsidal plate boundary.')

    slab_t = datums.value('slab_thickness_m')

    def column_below(level, xi: int, yj: int) -> str:
        transfer = active_transfers.get(xi)
        if (transfer is not None and level.index == transfer.level_index
                and yj in transfer.y_indices[1:-1]):
            return post_id(transfer,yj)
        k = level.index - 1
        lower = lattice.levels[k]
        prefix = 'PIL' if k == 0 else 'COL'
        return f'STR-{prefix}-X{xi:02d}-Y{yj:02d}-{lower.id}'

    def radial_column_below(level, ai: int) -> str:
        k = level.index - 1
        lower = lattice.levels[k]
        prefix = 'PIL' if k == 0 else 'COL'
        return f'STR-{prefix}-A{ai:02d}-{lower.id}'

    for level in lattice.levels[1:]:
        z_beam = level.z - slab_t - 0.31
        plate = level.plate
        # The stair and lift openings on this level, as the framing sees them. The
        # slab and the ceiling cut these same rectangles out; the members now either
        # stop at their edges or are named as crossing them.
        openings = _opening_rects(b.cores, level.id)
        # Theatre voids are real openings too. They are read after the core
        # transfer planner below so its bounded well algorithm does not attempt
        # to replace the complete thirty-metre theatre volume.
        theatre_openings = ([tuple(rect) for rect in carve.removed.get(level.index,())]
                            if active_transfers and carve is not None else [])

        def girder_reason(default: str, a, c, member_id: str) -> tuple[str, list[str]]:
            crossing = [o for o in openings if _segment_crosses_rect(a[0], a[1], c[0], c[1], o)]
            if not crossing:
                return default, ['STR-STEEL-GRAVITY-001']
            b.opening_conflicts.append(member_id)
            return (default + ' It runs through a stair or lift opening: a girder on '
                    'a grid line the core straddles. Kept and reported -- cutting it '
                    'would break the load path and the transfer that resolves it is '
                    'not designed here.'), ['STR-STEEL-GRAVITY-001',
                                            'STR-OPENING-TRANSFER-UNRESOLVED']

        # --- the wells a girder line runs through --------------------------------
        # Planned before the girders are drawn, so a girder the frame will carry
        # around its well is emitted in halves rather than whole and then flagged.
        def would_emit(direction: str, i: int, j: int) -> bool:
            xl, yl = lattice.x_lines, lattice.y_lines
            if direction == 'BMX':
                if not (0 <= i < len(xl) - 1 and 0 <= j < len(yl)):
                    return False
                if not structural_axis_on_plate(
                        level, xl[i], yl[j], xl[i + 1], yl[j]):
                    return False
                return all(support in b.element_ids for support in
                           (column_below(level, i, j), column_below(level, i + 1, j)))
            if not (0 <= i < len(xl) and 0 <= j < len(yl) - 1):
                return False
            if not structural_axis_on_plate(
                    level, xl[i], yl[j], xl[i], yl[j + 1]):
                return False
            return all(support in b.element_ids for support in
                       (column_below(level, i, j), column_below(level, i, j + 1)))

        # --- the stair cores: walls first, framing bears on them -------------------
        # The grid was drawn to these volumes (decision 0022). The storey's core
        # walls stand from the level below to this one; nothing structural is
        # drawn inside a core, and a girder or joist that meets a face bears on
        # the wall there instead of on a column or girder that no longer exists.
        wall_ids = _emit_core_walls(b, lattice.levels[level.index - 1], level, core_boxes,
                                    slab_t, floor_case, deck_dead_kpa, col_mat)

        def core_face_at(x: float, y: float) -> tuple[int, str] | None:
            for ci, (bx0, by0, bx1, by1) in enumerate(core_boxes):
                on_x = bx0 - 0.05 <= x <= bx1 + 0.05
                on_y = by0 - 0.05 <= y <= by1 + 0.05
                if abs(x - bx0) <= 0.05 and on_y:
                    return ci, 'W'
                if abs(x - bx1) <= 0.05 and on_y:
                    return ci, 'E'
                if abs(y - by0) <= 0.05 and on_x:
                    return ci, 'S'
                if abs(y - by1) <= 0.05 and on_x:
                    return ci, 'N'
            return None

        def within_core(x0: float, y0: float, x1: float, y1: float) -> bool:
            return any(bx0 - 0.05 <= x0 and x1 <= bx1 + 0.05
                       and by0 - 0.05 <= y0 and y1 <= by1 + 0.05
                       for bx0, by0, bx1, by1 in core_boxes)

        def face_support(face: tuple[int, str], x: float, y: float) -> str | None:
            """The wall on this face where a member arrives: the wall itself, or on
            the landing face the jamb or the head standing at that x."""
            entry = wall_ids.get(face)
            if entry is None or isinstance(entry, str):
                return entry
            along = x if face[1] in ('S', 'N') else y
            for lo, hi, piece in entry:
                if lo - 0.05 <= along <= hi + 0.05:
                    return piece
            return min(entry, key=lambda item: min(abs(along - item[0]),
                                                   abs(along - item[1])))[2]

        def core_ends(a: tuple[float, float], c: tuple[float, float]):
            """(inside, [support-or-None, support-or-None]) for a member from a to c."""
            if within_core(min(a[0], c[0]), min(a[1], c[1]), max(a[0], c[0]), max(a[1], c[1])):
                return True, [None, None]
            ends = []
            for point in (a, c):
                face = core_face_at(*point)
                ends.append(face_support(face, *point) if face is not None else None)
            return False, ends

        def edge_support(direction: str, i: int, j: int) -> str | None:
            """The girder on this grid segment, or the core wall standing on it."""
            xl, yl = lattice.x_lines, lattice.y_lines
            if direction == 'BMX':
                member = f'STR-BMX-X{i:02d}-Y{j:02d}-{level.id}'
                if member in b.element_ids:
                    return member
                if not (0 <= i < len(xl) - 1 and 0 <= j < len(yl)):
                    return None
                mid = ((xl[i] + xl[i + 1]) / 2.0, yl[j])
            else:
                member = f'STR-BMY-X{i:02d}-Y{j:02d}-{level.id}'
                if member in b.element_ids:
                    return member
                if not (0 <= i < len(xl) and 0 <= j < len(yl) - 1):
                    return None
                mid = (xl[i], (yl[j] + yl[j + 1]) / 2.0)
            face = core_face_at(*mid)
            return face_support(face, *mid) if face is not None else None

        # --- primary beams, both grid directions --------------------------------
        for yj, y in enumerate(lattice.y_lines):
            for xi in range(len(lattice.x_lines) - 1):
                x0, x1 = lattice.x_lines[xi], lattice.x_lines[xi + 1]
                if replaces_framing(b,level,'BMX',xi,yj):
                    continue
                if not structural_axis_on_plate(level, x0, y, x1, y):
                    continue
                inside, wall_ends = core_ends((x0, y), (x1, y))
                if inside:
                    continue   # the core wall stands here
                beam_supports = [wall_ends[0] or column_below(level, xi, yj),
                                 wall_ends[1] or column_below(level, xi + 1, yj)]
                for edge in transfer_edges:
                    if (xi == edge.x_bay_index and yj in edge.y_indices
                            and lattice.occupied[0].index < level.index < edge.level_index):
                        x1 = edge.x
                        beam_supports[1] = edge_column_id(edge,yj,level.index-1,lattice)
                if not all(support in b.element_ids for support in beam_supports):
                    continue
                member_id = f'STR-BMX-X{xi:02d}-Y{yj:02d}-{level.id}'
                reason, rules = girder_reason(
                    'Primary girder spans one bay between column nodes.',
                    (x0, y), (x1, y), member_id)
                b.add(member_id, 'primary_beam', 'structure', 'beams',
                      b.member([v3(x0, y, z_beam), v3(x1, y, z_beam)], girder_profile),
                      beam_mat, level_id=level.id,
                      lattice_index={'x': xi, 'y': yj, 'level': level.index},
                      datum_refs=['bay_x_m'],
                      supports=beam_supports,
                      section_id=sizing.beam.check.section_id,
                      sizing_status='sized_by_calculation', utilisation=gir_util,
                      governing_check=gir_gov, rule_refs=rules, reason=reason)
        for xi, x in enumerate(lattice.x_lines):
            for yj in range(len(lattice.y_lines) - 1):
                y0, y1 = lattice.y_lines[yj], lattice.y_lines[yj + 1]
                if replaces_framing(b,level,'BMY',xi,yj):
                    continue
                if not structural_axis_on_plate(level, x, y0, x, y1):
                    continue
                inside, wall_ends = core_ends((x, y0), (x, y1))
                if inside:
                    continue   # the core wall stands here
                beam_supports = [wall_ends[0] or column_below(level, xi, yj),
                                 wall_ends[1] or column_below(level, xi, yj + 1)]
                if not all(support in b.element_ids for support in beam_supports):
                    continue
                member_id = f'STR-BMY-X{xi:02d}-Y{yj:02d}-{level.id}'
                reason, rules = girder_reason(
                    'Primary girder closes the bay in the second direction.',
                    (x, y0), (x, y1), member_id)
                b.add(member_id, 'primary_beam', 'structure', 'beams',
                      b.member([v3(x, y0, z_beam), v3(x, y1, z_beam)], girder_profile),
                      beam_mat, level_id=level.id,
                      lattice_index={'x': xi, 'y': yj, 'level': level.index},
                      datum_refs=['bay_y_m'],
                      supports=beam_supports,
                      section_id=sizing.beam.check.section_id,
                      sizing_status='sized_by_calculation', utilisation=gir_util,
                      governing_check=gir_gov, rule_refs=rules, reason=reason)
        for edge in transfer_edges:
            if not lattice.occupied[0].index < level.index < edge.level_index:
                continue
            from .hall_stations import hall_axes
            _, edge_y = hall_axes(b)
            edge_y = edge.y_coordinates or edge_y
            for ja,jc in zip(edge.y_indices,edge.y_indices[1:]):
                b.add(f'STR-TRF-EDGE-BMY-X{edge.x_bay_index:02d}-Y{ja:02d}-{level.id}',
                      'primary_beam','structure','beams',
                      b.member([v3(edge.x,edge_y[ja],z_beam),
                                v3(edge.x,edge_y[jc],z_beam)],girder_profile),
                      beam_mat,level_id=level.id,
                      lattice_index={'x':edge.x_bay_index,'y':ja,'level':level.index,'transfer_edge':1},
                      datum_refs=['bay_y_m','slab_thickness_m'],
                      supports=[edge_column_id(edge,j,level.index-1,lattice) for j in (ja,jc)],
                      section_id=sizing.beam.check.section_id,sizing_status='sized_by_calculation',
                      utilisation=gir_util,governing_check=gir_gov,
                      rule_refs=['STR-TRANSFER-EDGE-001'],
                      reason='Perimeter girder closes the retained west floor strip. The original full-bay catalogue section conservatively carries this smaller tributary strip at the same span.')
        # --- ring beam across the apsidal end -----------------------------------
        for ai in range(len(lattice.apse_nodes) - 1):
            a, c = lattice.apse_nodes[ai], lattice.apse_nodes[ai + 1]
            beam_supports = [radial_column_below(level, ai),
                             radial_column_below(level, ai + 1)]
            if not all(support in b.element_ids for support in beam_supports):
                continue
            b.add(f'STR-BMA-A{ai:02d}-{level.id}', 'primary_beam', 'structure', 'beams',
                  b.member([v3(a.x, a.y, z_beam), v3(c.x, c.y, z_beam)], girder_profile),
                  beam_mat, level_id=level.id,
                  lattice_index={'apse': ai, 'level': level.index},
                  datum_refs=['apse_radius_m'],
                  supports=beam_supports,
                  section_id=sizing.beam.check.section_id,
                  sizing_status='sized_by_calculation', utilisation=gir_util,
                  governing_check=gir_gov, rule_refs=['STR-STEEL-GRAVITY-001'],
                  reason='Ring beam closes the curved end of the plate.')

        openings = openings + theatre_openings

        # --- the floor system, which is where the families separate -------------
        z_joist = level.z - slab_t - 0.17
        spacing = datums.value('joist_spacing_m')

        def emit_header(header_id: str, xa: float, xb: float, y_edge: float,
                        cut_span: float, supports: list[str], index: dict,
                        material: str) -> str | None:
            """One opening-edge beam, sized for the joists it collects.

            The header spans between the members that flank the opening and carries
            the trimmed joists' reactions -- half of each remaining span -- as the
            uniform load `check_beam` sizes. Same floor case, same catalogue as the
            frame takedown; where no section in the catalogue works the member is
            still drawn, as convention, and its reason says the calculation failed.
            """
            span = xb - xa
            if span < 0.3:
                return None
            if len(supports) < 2:
                # A header with an end on nothing is not a header. Reported, and the
                # joists it would have carried stay whole and are reported with it.
                b.opening_conflicts.append(header_id)
                return None
            chosen = select_beam(header_id, span, max(0.3, cut_span / 2.0), floor_case,
                                 beam_catalogue, role='girder',
                                 unbraced_length_m=min(spacing, span))
            if chosen.selected and chosen.check is not None:
                profile = sized_profile(chosen.check.section_id)
                sizing_kwargs = dict(
                    section_id=chosen.check.section_id,
                    sizing_status='sized_by_calculation',
                    utilisation=chosen.check.max_ratio,
                    governing_check=chosen.check.governing)
                verdict = (f'sized for {cut_span / 2.0:.2f} m of tributary floor over a '
                           f'{span:.2f} m span; {chosen.reason}.')
            else:
                profile = girder_profile
                sizing_kwargs = dict(section_id=None,
                                     sizing_status='architectural_convention',
                                     utilisation=None, governing_check=None)
                verdict = (f'no catalogue section carries {cut_span / 2.0:.2f} m of '
                           f'tributary floor over {span:.2f} m; drawn at the girder '
                           f'section as convention and reported.')
                b.opening_conflicts.append(header_id)
            b.add(header_id, 'primary_beam', 'structure', 'beams',
                  b.member([v3(xa, y_edge, z_joist), v3(xb, y_edge, z_joist)], profile),
                  material, level_id=level.id, lattice_index=index,
                  datum_refs=['joist_spacing_m', 'bay_y_m', 'flight_width_m'],
                  supports=supports,
                  rule_refs=['STR-STEEL-GRAVITY-001', 'STR-OPENING-HEADER-001'],
                  reason=('Header framing a stair or lift opening: the members that '
                          'ran through the opening now stop on it, and it carries them '
                          'to the trimmers beside the opening. ' + verdict),
                  **sizing_kwargs)
            b.headers_emitted += 1
            return header_id

        if frame.floor_system in ('joisted', 'heavy_joist'):
            # A heavy timber floor carries fewer, deeper joists at a wider centre than
            # a steel deck: the same load through a material that is weaker per unit
            # area but available in larger sections.
            heavy = frame.floor_system == 'heavy_joist'
            spacing = spacing * (1.9 if heavy else 1.0)
            kind = 'heavy_joist' if heavy else 'secondary_joist'
            joist_datums = ['joist_spacing_m', 'bay_y_m']
            for xi in range(len(lattice.x_lines) - 1):
                x0, x1 = lattice.x_lines[xi], lattice.x_lines[xi + 1]
                divisions = max(1, int(round((x1 - x0) / spacing)))
                joist_xs = [(sub, x0 + (x1 - x0) * sub / divisions)
                            for sub in range(1, divisions)]
                for yj in range(len(lattice.y_lines) - 1):
                    y0, y1 = lattice.y_lines[yj], lattice.y_lines[yj + 1]
                    if within_core(x0, y0, x1, y1):
                        continue   # the core interior: landings on the walls, no joists
                    girder_s = edge_support('BMX', xi, yj)
                    girder_n = edge_support('BMX', xi, yj + 1)
                    if girder_s is None or girder_n is None:
                        continue
                    bay_span = y1 - y0
                    bay_openings = [o for o in openings
                                    if o[0] < x1 - 0.05 and o[2] > x0 + 0.05
                                    and o[1] < y1 - 0.05 and o[3] > y0 + 0.05]

                    def joist_id(sub: int) -> str:
                        return f'STR-JST-X{xi:02d}-S{sub:02d}-Y{yj:02d}-{level.id}'

                    # The openings this bay's joists meet, the joists that flank each
                    # one (the trimmers), and the header edges that fall inside the bay.
                    trimmer_extra: dict[int, float] = {}
                    header_plan: list[tuple] = []
                    framed_edges: dict[tuple[int, str], str] = {}
                    for oi, (ox0, oy0, ox1, oy1) in enumerate(bay_openings):
                        west = [p for p in joist_xs if p[1] < ox0 - 0.05]
                        east = [p for p in joist_xs if p[1] > ox1 + 0.05]
                        w = max(west, key=lambda p: p[1]) if west else None
                        e = min(east, key=lambda p: p[1]) if east else None
                        xa = w[1] if w else x0
                        xb = e[1] if e else x1
                        support_w = (joist_id(w[0]) if w
                                     else edge_support('BMY', xi, yj))
                        support_e = (joist_id(e[0]) if e
                                     else edge_support('BMY', xi + 1, yj))
                        for tag, y_edge, cut_span in (
                                ('S', oy0 - HEADER_SETBACK_M, oy0 - HEADER_SETBACK_M - y0),
                                ('N', oy1 + HEADER_SETBACK_M, y1 - oy1 - HEADER_SETBACK_M)):
                            if not (y0 + 0.3 < y_edge < y1 - 0.3):
                                continue
                            header_plan.append((oi, tag, y_edge, xa, xb, cut_span,
                                                support_w, support_e))
                            for trimmer in (w, e):
                                if trimmer is not None:
                                    trimmer_extra[trimmer[0]] = (
                                        trimmer_extra.get(trimmer[0], 0.0)
                                        + _point_load_tributary(cut_span, xb - xa,
                                                                y_edge - y0, bay_span))

                    # Pass one: the joists that run the full bay -- ordinary ones, and
                    # the trimmers beside an opening, resized for the header they carry.
                    crossing_by_sub: dict[int, list] = {}
                    for sub, x in joist_xs:
                        if not point_inside(plate, x, (y0 + y1) / 2.0):
                            continue
                        crossing = [o for o in bay_openings if o[0] - 0.05 < x < o[2] + 0.05]
                        if crossing:
                            crossing_by_sub[sub] = crossing
                            continue
                        index = {'x': xi, 'sub': sub, 'y': yj, 'level': level.index}
                        extra = trimmer_extra.get(sub, 0.0)
                        if extra <= 1e-6:
                            emit_joist(joist_id(sub), level, x, y0, y1, z_joist,
                                  joist_profile, kind, joist_mat, lattice_index=index,
                                  datum_refs=joist_datums, supports=[girder_s, girder_n],
                                  section_id=sizing.joist.check.section_id,
                                  sizing_status='sized_by_calculation',
                                  utilisation=jst_util, governing_check=jst_gov,
                                  rule_refs=['STR-STEEL-GRAVITY-001', 'STF-INV-04'],
                                  reason='Secondary member spans between primary '
                                         'girders at the density the score and the '
                                         'material set.')
                            continue
                        chosen = select_beam(joist_id(sub), bay_span, spacing + extra,
                                             floor_case, beam_catalogue, role='beam',
                                             unbraced_length_m=0.0)
                        if chosen.selected and chosen.check is not None:
                            profile = sized_profile(chosen.check.section_id)
                            kwargs = dict(section_id=chosen.check.section_id,
                                          sizing_status='sized_by_calculation',
                                          utilisation=chosen.check.max_ratio,
                                          governing_check=chosen.check.governing)
                            verdict = f'{chosen.reason}.'
                        else:
                            profile = joist_profile
                            kwargs = dict(section_id=None,
                                          sizing_status='architectural_convention',
                                          utilisation=None, governing_check=None)
                            verdict = ('no catalogue section carries the header '
                                       'reaction; drawn at the joist section and '
                                       'reported.')
                            b.opening_conflicts.append(joist_id(sub))
                        emitted = emit_joist(joist_id(sub), level, x, y0, y1, z_joist,
                              profile, kind, joist_mat, lattice_index=index,
                              datum_refs=joist_datums + ['flight_width_m'],
                              supports=[girder_s, girder_n],
                              rule_refs=['STR-STEEL-GRAVITY-001', 'STF-INV-04',
                                         'STR-OPENING-HEADER-001'],
                              reason=(f'Trimmer joist beside a stair or lift opening: '
                                      f'it carries its own {spacing:.2f} m of floor plus '
                                      f'the header reactions, taken as {extra:.2f} m of '
                                      f'equivalent tributary width (8M/L² of the point '
                                      f'load). ' + verdict),
                              **kwargs)
                        b.trimmers_emitted += int(emitted)

                    # Pass two: the headers, now that the trimmers they land on exist.
                    header_ids: dict[tuple[int, str], str] = dict(framed_edges)
                    for oi, tag, y_edge, xa, xb, cut_span, support_w, support_e in header_plan:
                        supports = [s for s in (support_w, support_e)
                                    if s is not None and s in b.element_ids]
                        header_id = emit_header(
                            f'STR-HDR-X{xi:02d}-Y{yj:02d}-{level.id}-O{oi}{tag}',
                            xa, xb, y_edge, cut_span, supports,
                            {'x': xi, 'y': yj, 'level': level.index, 'opening': oi},
                            joist_mat)
                        if header_id:
                            header_ids[(oi, tag)] = header_id

                    # Pass three: the trimmed joists, as the pieces that remain outside
                    # the opening, each bearing on a girder at one end and a header at
                    # the other.
                    for sub, crossing in crossing_by_sub.items():
                        x = x0 + (x1 - x0) * sub / divisions
                        cuts = sorted((max(y0, o[1] - HEADER_SETBACK_M),
                                       min(y1, o[3] + HEADER_SETBACK_M),
                                       bay_openings.index(o)) for o in crossing)
                        # Each remaining piece is bounded by the girder at the bay edge
                        # or by the header of the opening it stops at: the south edge
                        # header of the opening ahead, the north edge header of the
                        # opening behind.
                        cursor, pieces, behind = y0, [], None
                        for c0, c1, oi in cuts:
                            if c0 - cursor > 0.3:
                                pieces.append((cursor, c0, behind, oi))
                            cursor = max(cursor, c1)
                            behind = oi
                        if y1 - cursor > 0.3:
                            pieces.append((cursor, y1, behind, None))
                        missing = any(
                            (behind_oi is not None and (behind_oi, 'N') not in header_ids)
                            or (ahead_oi is not None and (ahead_oi, 'S') not in header_ids)
                            for _pa, _pb, behind_oi, ahead_oi in pieces)
                        if missing:
                            # A header found nothing to bear on, so the joist keeps its
                            # full span through the opening and says so: a piece hanging
                            # off nothing is worse than a member that crosses.
                            b.opening_conflicts.append(joist_id(sub))
                            emit_joist(joist_id(sub), level, x, y0, y1, z_joist,
                                  joist_profile, kind, joist_mat,
                                  lattice_index={'x': xi, 'sub': sub, 'y': yj,
                                                 'level': level.index},
                                  datum_refs=joist_datums,
                                  supports=[girder_s, girder_n],
                                  section_id=sizing.joist.check.section_id,
                                  sizing_status='sized_by_calculation',
                                  utilisation=jst_util, governing_check=jst_gov,
                                  rule_refs=['STR-STEEL-GRAVITY-001', 'STF-INV-04',
                                             'STR-OPENING-TRANSFER-UNRESOLVED'],
                                  reason=('Secondary member kept through a stair or '
                                          'lift opening: the header at its edge found '
                                          'no member to bear on, so the joist is left '
                                          'crossing and reported rather than cut back '
                                          'to nothing.'))
                            continue
                        for n, (pa, pb, behind_oi, ahead_oi) in enumerate(pieces):
                            start_support = (girder_s if behind_oi is None
                                             else header_ids.get((behind_oi, 'N')))
                            end_support = (girder_n if ahead_oi is None
                                           else header_ids.get((ahead_oi, 'S')))
                            supports = [s for s in (start_support, end_support) if s]
                            emit_joist(f'{joist_id(sub)}-T{n}', level, x, pa, pb, z_joist,
                                  joist_profile, kind, joist_mat,
                                  lattice_index={'x': xi, 'sub': sub, 'y': yj,
                                                 'level': level.index, 'piece': n},
                                  datum_refs=joist_datums + ['flight_width_m'],
                                  supports=sorted(set(supports)),
                                  section_id=sizing.joist.check.section_id,
                                  sizing_status='sized_by_calculation',
                                  utilisation=jst_util, governing_check=jst_gov,
                                  rule_refs=['STR-STEEL-GRAVITY-001', 'STF-INV-04',
                                             'STR-OPENING-HEADER-001'],
                                  reason=('Trimmed joist: the part of a secondary '
                                          'member left outside a stair or lift opening, '
                                          'bearing on the girder at one end and the '
                                          'opening header at the other. Its section is '
                                          'the full joist\'s, which is conservative on '
                                          'the shorter span.'))
        elif frame.floor_system == 'panel':
            # CLT bands span girder to girder. They are drawn, not implied, because a
            # panel floor reads completely differently from a ribbed one in section --
            # and they are recorded as convention, because no panel check was run. A
            # band an opening interrupts is emitted as the pieces outside the opening,
            # and a glulam header spans the bay at each opening edge so those pieces
            # have an edge to bear on.
            for xi in range(len(lattice.x_lines) - 1):
                x0, x1 = lattice.x_lines[xi], lattice.x_lines[xi + 1]
                bands = max(1, int(round((x1 - x0) / 2.4)))
                for yj in range(len(lattice.y_lines) - 1):
                    y0, y1 = lattice.y_lines[yj], lattice.y_lines[yj + 1]
                    if within_core(x0, y0, x1, y1):
                        continue   # the core interior: landings on the walls, no panels
                    panel_supports = [edge_support('BMX', xi, yj),
                                      edge_support('BMX', xi, yj + 1)]
                    if any(support is None for support in panel_supports):
                        continue
                    bay_openings = [o for o in openings
                                    if o[0] < x1 - 0.05 and o[2] > x0 + 0.05
                                    and o[1] < y1 - 0.05 and o[3] > y0 + 0.05]
                    header_ids: dict[tuple[int, str], str] = {}
                    for oi, (ox0, oy0, ox1, oy1) in enumerate(bay_openings):
                        girders_y = [edge_support('BMY', xi, yj),
                                     edge_support('BMY', xi + 1, yj)]
                        supports = [g for g in girders_y if g is not None and g in b.element_ids]
                        for tag, y_edge, cut_span in (
                                ('S', oy0 - HEADER_SETBACK_M, oy0 - HEADER_SETBACK_M - y0),
                                ('N', oy1 + HEADER_SETBACK_M, y1 - oy1 - HEADER_SETBACK_M)):
                            if not (y0 + 0.3 < y_edge < y1 - 0.3):
                                continue
                            header_id = emit_header(
                                f'STR-HDR-X{xi:02d}-Y{yj:02d}-{level.id}-O{oi}{tag}',
                                x0, x1, y_edge, cut_span, supports,
                                {'x': xi, 'y': yj, 'level': level.index, 'opening': oi},
                                beam_mat)
                            if header_id:
                                header_ids[(oi, tag)] = header_id
                    for band in range(bands):
                        xa = x0 + (x1 - x0) * band / bands
                        xb = x0 + (x1 - x0) * (band + 1) / bands
                        if not point_inside(plate, (xa + xb) / 2.0, (y0 + y1) / 2.0):
                            continue
                        crossing = [o for o in bay_openings
                                    if o[0] < xb - 0.05 and o[2] > xa + 0.05]
                        cuts = sorted((max(y0, o[1] - HEADER_SETBACK_M),
                                       min(y1, o[3] + HEADER_SETBACK_M),
                                       bay_openings.index(o)) for o in crossing)
                        cursor, pieces, behind = y0, [], None
                        for c0, c1, oi in cuts:
                            if c0 - cursor > 0.3:
                                pieces.append((cursor, c0, behind, oi))
                            cursor = max(cursor, c1)
                            behind = oi
                        if y1 - cursor > 0.3:
                            pieces.append((cursor, y1, behind, None))
                        for n, (pa, pb, behind_oi, ahead_oi) in enumerate(pieces):
                            start = (panel_supports[0] if behind_oi is None
                                     else header_ids.get((behind_oi, 'N')))
                            end = (panel_supports[1] if ahead_oi is None
                                   else header_ids.get((ahead_oi, 'S')))
                            piece_supports = [s for s in (start, end) if s]
                            suffix = '' if not crossing else f'-T{n}'
                            b.add(f'STR-CLT-X{xi:02d}-B{band:02d}-Y{yj:02d}-{level.id}{suffix}',
                                  'clt_panel', 'structure', 'floor_panels',
                                  BoxGeometry(
                                      center=v3((xa + xb) / 2.0, (pa + pb) / 2.0,
                                                z_joist + 0.05),
                                      size=v3((xb - xa) * 0.97, (pb - pa) * 0.99,
                                              slab_t * frame.slab_thickness_factor)),
                                  beam_mat, level_id=level.id,
                                  lattice_index={'x': xi, 'sub': band, 'y': yj,
                                                 'level': level.index},
                                  datum_refs=['bay_y_m', 'slab_thickness_m'],
                                  supports=piece_supports or panel_supports,
                                  rule_refs=['STR-TIMBER-FLOOR-001'],
                                  reason='CLT band spanning girder to girder. No panel '
                                         'bending check is implemented, so this is carried '
                                         'as convention and says so.'
                                         + (' Cut back to the opening header.' if crossing
                                            else ''))
        else:
            if openings:
                b.unframed_levels.append(level.id)
            # A flat slab has no secondary tier at all. What it has instead is a drop
            # panel over every column, and the absence of ribs is the thing a section
            # drawing shows.
            for xi, x in enumerate(lattice.x_lines):
                for yj, y in enumerate(lattice.y_lines):
                    if not point_inside(plate, x, y):
                        continue
                    drop_support = column_below(level, xi, yj)
                    if drop_support not in b.element_ids:
                        continue
                    b.add(f'STR-DRP-X{xi:02d}-Y{yj:02d}-{level.id}', 'drop_panel',
                          'structure', 'slabs',
                          BoxGeometry(center=v3(x, y, level.z - slab_t * 1.6),
                                      size=v3(2.4, 2.4, slab_t * 1.2)),
                          beam_mat, level_id=level.id,
                          lattice_index={'x': xi, 'y': yj, 'level': level.index},
                          datum_refs=['slab_thickness_m', 'bay_x_m', 'bay_y_m'],
                          supports=[drop_support],
                          reason='Drop panel thickens the slab over the column for '
                                 'punching shear. No ACI check is implemented.')

        # --- slab, fascia --------------------------------------------------------
        emit_boundary_spans(b, level, girder_profile, beam_mat, core_boxes,
                            lambda level_id: _opening_rects(b.cores, level_id))
        floor_support_kinds = (
            [kind] if frame.floor_system in ('joisted', 'heavy_joist') else
            ['clt_panel'] if frame.floor_system == 'panel' else ['drop_panel'])
        floor_supports = b.ids(kinds=floor_support_kinds, level_id=level.id)
        if not floor_supports:
            floor_supports = b.ids(kinds=['primary_beam'], level_id=level.id)
        slab_id = f'STR-SLB-{level.id}'
        b.add_plate(slab_id, 'floor_slab', 'structure', 'slabs',
              inset(plate, 0.0),
              [list(hole) for hole in level.voids] + _core_openings(b.cores, level.id)
              + [_rect_ring(*rect) for rect in _landing_footprints(b.cores, level.id)]
              + [_rect_ring(*rect)
                 for rect in _approach_landing_footprints(b.approach, level.id)],
              round(level.z - slab_t, 4), level.z,
              'concrete_light', level_id=level.id,
              lattice_index={'level': level.index},
              datum_refs=['slab_thickness_m', 'void_count', 'void_scale',
                          'terrace_count', *PLATE_DATUMS],
              supports=floor_supports,
              rule_refs=['STR-STEEL-DIAPHRAGM-001'],
              reason='Composite deck diaphragm; boundary and voids come from the plate '
                     'datum, not from a literal.')
        # The ceiling, and with it the storey's build-up. Without one a section showed
        # a single 300 mm band per floor and every partition stopped 150 mm short of
        # the structure with nothing to stop against -- the head clearance was in the
        # model as a number and not as a thing. The plane sits at exactly the height
        # the partitions already run to, so they meet it instead of ending in air, and
        # the gap between it and the slab soffit reads as the services zone it is.
        if level.kind == 'occupied':
            ceiling_z = level.z + max(
                2.4, datums.value('floor_to_floor_m') - slab_t
                - PARTITION_HEAD_CLEARANCE_M)
            # An archetype's carved volumes have their own section; a suspended
            # ceiling drawn across the auditorium at corridor height would cut the
            # room the carve exists to make.
            ceiling_holes = [list(hole) for hole in level.voids] + [
                [v2(cx0, cy0), v2(cx1, cy0), v2(cx1, cy1), v2(cx0, cy1)]
                for cx0, cy0, cx1, cy1 in lattice.carved.get(level.index, ())]
            ceiling_holes += _core_openings(b.cores, level.id, ceiling=True)
            b.add_plate(f'ARC-CLG-{level.id}', 'ceiling', 'program', 'finishes',
                  inset(plate, 0.15), ceiling_holes,
                  round(ceiling_z - CEILING_THICKNESS_M, 4), round(ceiling_z, 4),
                  'white', category='public', program='ceiling', level_id=level.id,
                  lattice_index={'level': level.index},
                  datum_refs=['floor_to_floor_m', 'slab_thickness_m', *PLATE_DATUMS],
                  supports=[slab_id],
                  thickness_m=CEILING_THICKNESS_M,
                  reason='Suspended ceiling at the head height the partitions run to. '
                         'The zone above it carries the structure and the services; '
                         'the two together are what a section reads as a floor.')
        fascia_depth = datums.value('edge_fascia_m')
        fascia_clearance = b.profiles[fascia].width_m / 2.0 + 1.0e-6
        fascia_plate = _parallel_inset_ring(
            plate, fascia_clearance, f'{level.id} slab-fascia')
        for ei in range(len(fascia_plate)):
            a, c = fascia_plate[ei], fascia_plate[(ei + 1) % len(fascia_plate)]
            for piece,(start,end) in enumerate(retained_edge_segments(a,c,level.voids)):
                suffix = '' if piece==0 else f'-T{piece}'
                b.add(f'STR-FAS-{level.id}-E{ei:03d}{suffix}', 'slab_fascia', 'structure', 'slabs',
                      b.member([v3(*start,level.z-fascia_depth/2.),
                                v3(*end,level.z-fascia_depth/2.)],fascia),
                      'white',level_id=level.id,
                      lattice_index={'level':level.index,'edge':ei,'piece':piece},
                      datum_refs=['edge_fascia_m',*PLATE_DATUMS],supports=[slab_id],
                      reason='Thickened retained plate edge. Its centre-line is a true '
                             'half-section inside the Program Volume boundary, so the '
                             'outside face meets that boundary without crossing it; '
                             'portions over removed floor are omitted with the slab.')

    # --- the lateral system, the second place the families separate -----------
    # Polyphony decides how often the lateral system is expressed. The count is a
    # tectonic minimum of two, raised by the score; it is never reduced below two,
    # because the number of lateral bays is a safety decision, not a compositional one.
    wanted = max(2, datums.integer('braced_bay_count'))
    interior = list(range(1, max(2, len(lattice.x_lines) - 1)))
    if len(interior) <= wanted:
        braced = interior
    else:
        braced = sorted({interior[round(i * (len(interior) - 1) / (wanted - 1))]
                         for i in range(wanted)})
    lateral_mat = 'concrete' if frame.lateral_kind == 'shear_wall' else col_mat

    def _braced_frame_line(level_index: int, lower_id: str) -> tuple[int, list[int]]:
        """The y grid line with the most usable lateral bays at this storey.

        The lateral bays used to be pinned to `y_lines[-1]`, the northernmost line. On a
        plate that does not reach that line -- which is most of them, once the footprint
        stopped being a constant -- no column stands there, the connectivity guard below
        refused to draw a brace onto nothing, and the building came out with **no
        lateral system at all**. The guard was right; the fixed line was wrong.

        Requiring *every* nominated bay on one line was the second version and was wrong
        the same way: an apsidal or stepped plate drops the outermost node, so no line
        qualified and the count stayed at zero. A bay is usable when it has a column at
        each end; a line is chosen for how many of those it has, rear-most first so the
        bracing stays on the service side and clear of the entrance.
        """
        prefix = 'PIL' if level_index == 0 else 'COL'
        best: tuple[int, list[int]] = (-1, [])
        # A brace runs the storey between these two levels, and a stair well that
        # straddles its grid line runs through it: the diagonal would cross the
        # flight. The wells the upper plate cuts are the ones this storey's stair
        # climbs into, so a bay is only usable when its line misses every one.
        wells = _opening_rects(b.cores, lattice.levels[level_index + 1].id) + core_boxes
        for yj in range(len(lattice.y_lines) - 1, -1, -1):
            usable = [
                xi for xi in braced
                if f'STR-{prefix}-X{xi:02d}-Y{yj:02d}-{lower_id}' in b.element_ids
                and f'STR-{prefix}-X{xi + 1:02d}-Y{yj:02d}-{lower_id}' in b.element_ids
                and not any(_segment_crosses_rect(
                    lattice.x_lines[xi], lattice.y_lines[yj],
                    lattice.x_lines[xi + 1], lattice.y_lines[yj], well)
                    for well in wells)
                and lateral_bay_clear(lattice, level_index,
                    lattice.x_lines[xi], lattice.x_lines[xi+1], lattice.y_lines[yj],
                    max(b.profiles['EDGEBEAM-160'].width_m,
                        b.profiles['EDGEBEAM-160'].depth_m)/2)]
            if len(usable) > len(best[1]):
                best = (yj, usable)
            if len(usable) == len(braced):
                break
        return best

    for level_index in range(0, len(lattice.levels) - 1):
        lower, upper = lattice.levels[level_index], lattice.levels[level_index + 1]
        yj_line, usable_bays = _braced_frame_line(level_index, lower.id)
        if not usable_bays:
            continue
        y = lattice.y_lines[yj_line]
        for xi in usable_bays:
            x0, x1 = lattice.x_lines[xi], lattice.x_lines[xi + 1]
            prefix = 'PIL' if level_index == 0 else 'COL'
            column_supports = [
                f'STR-{prefix}-X{xi:02d}-Y{yj_line:02d}-{lower.id}',
                f'STR-{prefix}-X{xi + 1:02d}-Y{yj_line:02d}-{lower.id}',
            ]
            upper_beam = f'STR-BMX-X{xi:02d}-Y{yj_line:02d}-{upper.id}'
            if frame.lateral_kind == 'braced_bay':
                if not all(support in b.element_ids for support in column_supports):
                    continue
                apex = v3((x0 + x1) / 2.0, y, upper.z - 0.4)
                for d, start in enumerate((x0, x1), start=1):
                    b.add(f'STR-BRC-X{xi:02d}-{lower.id}-D{d}', 'brace', 'structure',
                          'bracing',
                          b.member([v3(start, y, lower.z), apex], 'EDGEBEAM-160'),
                          col_mat, level_id=lower.id,
                          lattice_index={'x': xi, 'level': level_index},
                          datum_refs=['bay_x_m', 'floor_to_floor_m'],
                          supports=[column_supports[d - 1]]
                          + ([upper_beam] if upper_beam in b.element_ids else []),
                          rule_refs=['STR-STEEL-LATERAL-001', 'STF-INV-03'],
                          reason='Declared lateral bay, continuous to foundation and '
                                 'clear of the entry.')
            elif frame.lateral_kind in ('shear_wall', 'core_wall'):
                # A plane, not a diagonal. It reads as a blank panel in elevation and
                # is the reason a concrete or mass-timber building looks solid where a
                # braced steel one looks triangulated.
                kind = 'shear_wall' if frame.lateral_kind == 'shear_wall' else 'core_wall'
                wall_id = f'STR-WAL-X{xi:02d}-{lower.id}'
                if level_index == 0:
                    wall_supports = [
                        f'STR-FDN-X{xi:02d}-Y{len(lattice.y_lines) - 1:02d}',
                        f'STR-FDN-X{xi + 1:02d}-Y{len(lattice.y_lines) - 1:02d}',
                    ]
                else:
                    wall_supports = [f'STR-WAL-X{xi:02d}-{lattice.levels[level_index - 1].id}']
                if not all(support in b.element_ids for support in wall_supports):
                    continue
                b.add(wall_id, kind, 'structure', 'bracing',
                      BoxGeometry(
                          center=v3((x0 + x1) / 2.0, y, (lower.z + upper.z) / 2.0),
                          size=v3((x1 - x0) * 0.92, 0.32, upper.z - lower.z)),
                      lateral_mat, level_id=lower.id,
                      lattice_index={'x': xi, 'level': level_index},
                      datum_refs=['bay_x_m', 'floor_to_floor_m'],
                      supports=wall_supports,
                      rule_refs=['STR-LATERAL-WALL-001'],
                      reason='Lateral wall plane. No lateral analysis is implemented; '
                             'its thickness is a convention, not a result.')
            else:
                # A knee brace at the joint, which is the motif that identifies a
                # post-and-beam frame across a room.
                knee = min(1.2, (x1 - x0) * 0.22)
                if not all(support in b.element_ids for support in column_supports):
                    continue
                for d, start in enumerate((x0, x1), start=1):
                    sign = 1.0 if start == x0 else -1.0
                    b.add(f'STR-KNE-X{xi:02d}-{lower.id}-D{d}', 'knee_brace',
                          'structure', 'bracing',
                          b.member([v3(start, y, upper.z - knee * 1.6),
                                    v3(start + sign * knee, y, upper.z - 0.35)],
                                   'EDGEBEAM-160'),
                          col_mat, level_id=lower.id,
                          lattice_index={'x': xi, 'level': level_index},
                          datum_refs=['bay_x_m', 'floor_to_floor_m'],
                          supports=[column_supports[d - 1]]
                          + ([upper_beam] if upper_beam in b.element_ids else []),
                          rule_refs=['STR-TIMBER-LATERAL-001'],
                          reason='Knee brace triangulating the post-to-beam joint. '
                                 'Carried as convention: no moment check was run on '
                                 'the connection it represents.')

    # --- rakers propping the cantilevered plate edge ---------------------------
    # This used to run from the plate edge up to a point in mid-air -- `y_edge + 2.4`
    # at 0.85 of a storey above the slab -- and claim the slab as its support. Nothing
    # was there. A cantilever is propped by a raker that lands on a column, so that is
    # what gets drawn: from under the projecting edge back and down to the nearest
    # column node that exists at the storey below.
    for level_index in (2, 3):
        if level_index >= len(lattice.levels) - 1:
            continue
        level = lattice.levels[level_index]
        below = lattice.levels[level_index - 1]
        prefix = 'PIL' if level_index - 1 == 0 else 'COL'
        y_edge = min(point.y for point in level.plate)
        fascia_axis_y = y_edge + b.profiles[fascia].width_m / 2.0 + 1.0e-6
        # The raker's head lands on the thickened plate edge -- the fascia member
        # that runs along every plate boundary -- rather than floating just below
        # it. That fascia is what a prop under a cantilever actually bears on, and
        # it is the member that was there all along while the strut ended beside it.
        fascia_z = level.z - datums.value('edge_fascia_m') / 2.0
        # the first registered y line inboard of the cantilever, and its column
        inboard = [(yj, y) for yj, y in enumerate(lattice.y_lines) if y > y_edge + 0.5]
        if not inboard:
            continue
        yj, y_node = inboard[0]
        for xi, x in enumerate(lattice.x_lines):
            if not point_inside(level.plate, x, y_edge + 0.3):
                continue
            column_id = f'STR-{prefix}-X{xi:02d}-Y{yj:02d}-{below.id}'
            if column_id not in b.element_ids:
                continue
            b.add(f'STR-RKR-X{xi:02d}-{level.id}', 'outrigger_strut', 'structure',
                  'bracing',
                  b.member([v3(x, fascia_axis_y, fascia_z),
                            v3(x, y_node, below.z + (level.z - below.z) * 0.45)],
                           strut),
                  # The frame's own material. Hard-coded steel, this raker was the one
                  # steel member in a mass-timber building -- not a decision anyone
                  # made, just the colour the line was written with.
                  lateral_mat, level_id=level.id,
                  lattice_index={'x': xi, 'y': yj, 'level': level_index},
                  datum_refs=['cantilever_m'],
                  supports=[f'STR-SLB-{level.id}', column_id]
                  + [fid for fid in
                      (b.axis.nearest_owner(v3(x, fascia_axis_y, fascia_z),
                                            f'STR-FAS-{level.id}-'),) if fid],
                  rule_refs=['STR-STEEL-GRAVITY-001'],
                  reason='Raker propping the cantilevered plate edge back to the column '
                         'below. Both ends land on a member that exists; the previous '
                         'strut ended in mid-air and named the slab as its support.')


    if unresolved_joists:
        b.world_xy_frame_notes.append(
            f'Unresolved floor framing: {len(unresolved_joists)} secondary members '
            'were not emitted because their complete catalogue-section footprint '
            'leaves the supported plate or crosses a reserved opening. Their '
            'existing end girders/headers cannot support a cut at that boundary; '
            'replacement framing and floor-deck spans require design. Member IDs: '
            + ', '.join(unresolved_joists) + '.')
    if lattice.world_xy_grid is not None:
        boundary_spans = sum(identifier.startswith('STR-WXB-BM-') for identifier in b.element_ids)
        b.world_xy_frame_notes.append(
            f'World XY boundary frame: {boundary_spans} physical boundary spans fill '
            'gaps after regular beams are emitted and before slabs declare their supports.')


def _vertical_plate_span(
    plate: list[Vector2], x: float, holes: list[list[Vector2]] | None = None,
) -> tuple[float, float] | None:
    """Return the longest inside segment cut by a vertical registered line.

    Roof holes are subtracted from the span before a truss line is selected.  The
    no-hole call remains the historical path used by legacy massings.
    """

    tolerance = 1e-8
    intersections: list[float] = []
    for start, end in zip(plate, plate[1:] + plate[:1]):
        delta_x = end.x - start.x
        if abs(delta_x) <= tolerance:
            if abs(x - start.x) <= tolerance:
                intersections.extend((start.y, end.y))
            continue
        amount = (x - start.x) / delta_x
        if -tolerance <= amount <= 1.0 + tolerance:
            intersections.append(start.y + (end.y - start.y) * amount)

    unique: list[float] = []
    for value in sorted(intersections):
        if not unique or abs(value - unique[-1]) > tolerance:
            unique.append(value)
    inside: list[tuple[float, float]] = []
    for low, high in zip(unique, unique[1:]):
        if high - low <= tolerance:
            continue
        if point_inside(plate, x, (low + high) / 2.0):
            inside.append((low, high))
    if holes and inside:
        for hole in holes:
            hole_span = _vertical_plate_span(hole, x)
            if hole_span is None:
                continue
            next_inside: list[tuple[float, float]] = []
            h0, h1 = hole_span
            for low, high in inside:
                if h1 <= low or h0 >= high:
                    next_inside.append((low, high))
                    continue
                if h0 > low:
                    next_inside.append((low, min(h0, high)))
                if h1 < high:
                    next_inside.append((max(h1, low), high))
            inside = [span for span in next_inside if span[1] - span[0] > tolerance]
    return max(inside, key=lambda span: span[1] - span[0]) if inside else None


def _roof_truss_lines(
    lattice: Lattice, *, clearance_m: float = 0.0,
) -> list[tuple[str, float, float, float, dict[str, int]]]:
    """Choose at least two truss lines from the roof plate registration geometry.

    A stepped or rotated upper plate can move entirely between the base-building grid
    lines.  In that case the roof receives its own two-line sub-grid, positioned as
    fractions of the roof bounds and indexed as ``roof_x``.  This prevents a roof deck
    from being emitted over a single truss with no purlins.
    """

    roof = lattice.roof
    holes = roof.voids
    roof_region = plan_polygon(roof.plate)
    if holes:
        roof_region = roof_region.difference(unary_union(
            [plan_polygon(hole) for hole in holes]))

    def usable_span(x: float):
        if clearance_m > 0.0:
            inset_region = roof_region.buffer(-clearance_m, join_style=2)
            if inset_region.is_empty:
                return None
            y_values = [point.y for point in roof.plate]
            line = LineString([(x, min(y_values) - 1.0),
                               (x, max(y_values) + 1.0)])
            clipped = inset_region.intersection(line)
            segments = []
            geometries = ([clipped] if clipped.geom_type == 'LineString' else
                          list(getattr(clipped, 'geoms', ())))
            for item in geometries:
                if item.geom_type == 'LineString' and item.length > 1.0e-6:
                    ys = [point[1] for point in item.coords]
                    segments.append((min(ys), max(ys)))
            return max(segments, key=lambda span: span[1] - span[0]) \
                if segments else None
        span = _vertical_plate_span(roof.plate, x, holes)
        if span is None:
            return None
        return span
    registered: list[tuple[str, float, float, float, dict[str, int]]] = []
    for xi, x in enumerate(lattice.x_lines):
        span = usable_span(x)
        if span:
            registered.append((f'X{xi:02d}', x, span[0], span[1],
                               {'x': xi, 'level': roof.index}))
    if len(registered) >= 2:
        return registered

    min_x = min(point.x for point in roof.plate)
    max_x = max(point.x for point in roof.plate)
    fractions = (0.20, 0.25, 1.0 / 3.0, 0.50, 2.0 / 3.0, 0.75, 0.80)
    candidates: list[tuple[float, float, float]] = []
    for fraction in fractions:
        x = min_x + (max_x - min_x) * fraction
        span = usable_span(x)
        if span:
            candidates.append((x, span[0], span[1]))
    if len(candidates) < 2:
        raise ValueError('Roof plate cannot register two complete truss support lines.')
    selected = (candidates[0], candidates[-1])
    return [(f'R{index:02d}', x, y0, y1,
             {'roof_x': index, 'level': roof.index})
            for index, (x, y0, y1) in enumerate(selected)]


def _emit_roof(b: _Builder) -> None:
    from shapely.geometry import Point, Polygon
    from shapely.geometry.polygon import orient
    from .roof import supported_purlin_stations
    from .envelope import (
        GEOMETRY_EPS_M, _point_on_edge, _slab_region, _slabs, registered_bays,
    )
    lattice, datums = b.lattice, b.datums
    roof_start_ids = set(b.element_ids)
    roof = lattice.roof
    depth = datums.value('truss_depth_m')
    panels = max(3, datums.integer('truss_panels'))
    purlin_depth = b.profiles['PURLIN-120x200'].depth_m
    chord_depth = b.profiles['TRUSSCHORD-200x260'].depth_m
    roof_control = lattice.roof_control
    profile = roof_section_profile(
        depth,
        chord_depth_m=chord_depth,
        purlin_depth_m=purlin_depth,
        deck_thickness_m=ROOF_DECK_THICKNESS_M,
        parapet_upstand_m=PARAPET_UPSTAND_M,
        # Preserve the established one-piece deck in compatibility models.  Program
        # Volume candidates carry the complete serialized warm-roof recipe.
        include_warm_roof_layers=roof_control is not None)
    roof_assembly_id = f'ROOF-{roof.id}-WARM-001'
    assembly_rules = [
        ROOF_ASSEMBLY_RULE,
        ROOF_CONTROL_RULE,
        ROOF_PROFESSIONAL_REVIEW_RULE,
    ] if roof_control is not None else []
    professional_review = '; '.join(ROOF_PROFESSIONAL_REVIEW_ITEMS)

    def assembly_metadata(part_role: str, *rule_refs: str) -> dict:
        metadata = {'rule_refs': [*rule_refs, *assembly_rules]}
        if roof_control is not None:
            metadata.update(assembly_id=roof_assembly_id, part_role=part_role)
        return metadata

    if roof_control is not None:
        # The lattice check catches a changed plan at the handoff. Repeat the check
        # here because this emitter is also callable directly in focused tests.
        assert_roof_control_matches_level(roof_control, roof)
        if roof_control.profile != profile:
            raise ValueError(
                'Program Volume roof_control profile does not match the active roof '
                'section profiles; regenerate the control from the same convention')
        expected_cap = roof_control.datum_z + profile.physical_top_offset_m
        if not math.isclose(roof_control.physical_top_z, expected_cap,
                            abs_tol=1.0e-6):
            raise ValueError(
                'Program Volume roof_control physical_top_z is below the active '
                f'roof section cap ({expected_cap:.5f} m)')
        z_bot = roof_control.datum_z
    else:
        z_bot = roof.z
    z_top = z_bot + depth
    # Purlins bear on the top chord; the deck bears on their measured top face.
    # All three axes previously coincided and the deck then floated above an inset
    # boundary. These remain convention members with no roof load analysis claim.
    purlin_z = z_top + chord_depth / 2.0 + purlin_depth / 2.0
    deck_base = purlin_z + purlin_depth / 2.0
    deck_thickness = profile.deck_thickness_m  # Concept recipe; no waterproofing claim.
    lines = _roof_truss_lines(
        lattice,
        clearance_m=b.profiles['TRUSSCHORD-200x260'].width_m / 2.0)
    # A truss stops at a stair core (decision 0022). The grid is drawn to the core
    # faces, so a truss line can run along one; the core walls carry the roof over
    # the core, and a chord run across it would be a member over the top flight's
    # treads. Each line is cut into the pieces outside the cores it meets.
    core_boxes = _core_rects(b.cores)

    def pieces_for(x: float, y0: float, y1: float) -> list[tuple[float, float]]:
        cuts = sorted(
            (max(by0, y0), min(by1, y1))
            for bx0, by0, bx1, by1 in core_boxes
            if bx0 - 0.05 <= x <= bx1 + 0.05
            and by1 > y0 and by0 < y1)
        pieces, cursor = [], y0
        for c0, c1 in cuts:
            if c1 <= c0:
                continue
            if c0 - cursor > 0.3:
                pieces.append((cursor, c0))
            cursor = min(y1, max(cursor, c1))
        if y1 - cursor > 0.3:
            pieces.append((cursor, y1))
        return pieces

    trusses: list[list[tuple[str, float, float, float, dict]]] = []
    for token, x, y0, y1, lattice_index in lines:
        pieces = pieces_for(x, y0, y1)
        trusses.append([
            (token if len(pieces) == 1 else f'{token}-{k}', x, py0, py1,
             {**lattice_index, 'piece': k})
            for k, (py0, py1) in enumerate(pieces)])

    for run in trusses:
        for token, x, y0, y1, lattice_index in run:
            panel = (y1 - y0) / panels
            for tag, z in (('T', z_top), ('B', z_bot)):
                chord_supports = (
                    [f'STR-TWB-{token}-P{p:02d}-V' for p in range(panels + 1)]
                    if tag == 'T' else [f'STR-SLB-{roof.id}'])
                b.add(f'STR-TCH-{token}-{tag}', 'truss_chord', 'structure', 'roof_truss',
                      b.member([v3(x, y0, z), v3(x, y1, z)], 'TRUSSCHORD-200x260'),
                      'steel_white', level_id=roof.id,
                      lattice_index=lattice_index,
                      datum_refs=['truss_depth_m'],
                      supports=chord_supports,
                      reason='Roof truss chord. Truss members are dimensioned by '
                             'convention; no truss analysis is implemented.' + (
                                 f' Professional review remains required for {professional_review}.'
                                 if roof_control is not None else ''),
                      **assembly_metadata(
                          'primary_truss_chord_top' if tag == 'T'
                          else 'primary_truss_chord_bottom',
                          'STR-STEEL-GRAVITY-001'))
            for p in range(panels + 1):
                y = y0 + panel * p
                b.add(f'STR-TWB-{token}-P{p:02d}-V', 'truss_web', 'structure',
                      'roof_truss',
                      b.member([v3(x, y, z_bot), v3(x, y, z_top)], 'TRUSSWEB-130'),
                      'steel_white', level_id=roof.id,
                      lattice_index={**lattice_index, 'panel': p},
                      datum_refs=['truss_panels'],
                      supports=[f'STR-TCH-{token}-B'],
                      reason='Truss vertical at a panel point.' + (
                          ' Member and connection capacity require professional review.'
                          if roof_control is not None else ''),
                      **assembly_metadata('primary_truss_web_vertical'))
                if p < panels:
                    yn = y + panel
                    start, end = ((z_bot, z_top) if p % 2 == 0 else (z_top, z_bot))
                    b.add(f'STR-TWB-{token}-P{p:02d}-D', 'truss_web', 'structure',
                          'roof_truss',
                          b.member([v3(x, y, start), v3(x, yn, end)], 'TRUSSWEB-130'),
                          'steel_white', level_id=roof.id,
                          lattice_index={**lattice_index, 'panel': p},
                          datum_refs=['truss_panels'],
                          supports=[f'STR-TCH-{token}-B'],
                          reason='Warren diagonal; handedness alternates panel to panel.' + (
                              ' Member and connection capacity require professional review.'
                              if roof_control is not None else ''),
                          **assembly_metadata('primary_truss_web_diagonal'))
    covered_purlins: list[str] = []
    roof_region = Polygon([(p.x, p.y) for p in roof.plate],
                          holes=[[(p.x, p.y) for p in ring] for ring in roof.voids])
    for i in range(len(trusses) - 1):
        for kl, left in enumerate(trusses[i]):
            for kr, right in enumerate(trusses[i + 1]):
                lo, hi = max(left[2], right[2]), min(left[3], right[3])
                if hi - lo < 0.3:
                    continue
                suffix = '' if len(trusses[i]) == 1 and len(trusses[i + 1]) == 1 else f'-{kl}{kr}'
                stations = (supported_purlin_stations(
                    roof_region, left[1], right[1], lo, hi,
                    width_m=b.profiles['PURLIN-120x200'].width_m,
                    max_spacing_m=(hi-lo)/panels)
                    if roof_control is not None else
                    [lo + (hi-lo)*p/panels for p in range(panels+1)])
                for p, y in enumerate(stations):
                    purlin_id = f'STR-PRL-P{p:02d}-B{i:02d}{suffix}'
                    b.add(purlin_id, 'purlin', 'structure', 'roof_truss',
                          b.member([v3(left[1], y, purlin_z), v3(right[1], y, purlin_z)],
                                   'PURLIN-120x200'),
                          'steel_light', level_id=roof.id,
                          lattice_index={'panel': p, 'bay': i, 'level': roof.index},
                          datum_refs=['truss_panels'],
                          supports=[f'STR-TCH-{left[0]}-T', f'STR-TCH-{right[0]}-T'],
                          reason='Purlin spans between trusses on the top chord.' + (
                              ' Section and connections require professional review.'
                              if roof_control is not None else ''),
                          **assembly_metadata('secondary_purlin'))
                    covered_purlins.append(purlin_id)

    if roof_control is not None:
        deck_plate = [v2(x, y) for x, y in roof_control.boundary]
        deck_holes = [[v2(x, y) for x, y in ring] for ring in roof_control.voids]
    else:
        deck_plate = list(roof.plate)
        deck_holes = list(roof.voids)
    # Every perimeter family has a different physical breadth.  One shared inset
    # left the 90 mm closure panel behind the 200 mm parapet centre-line, creating a
    # real slot below the deck.  It also relied on `geometry.inset`'s preserved convex
    # radial move, whose edge distance is smaller than the requested amount on a
    # rectangle.  Roof control needs a true parallel offset: each centre-line sits one
    # half of its own body inside the exact Program Volume ring, so the outside face
    # reaches that ring without crossing it.
    def parallel_inset(ring, amount: float, label: str):
        return _parallel_inset_ring(ring, amount, f'roof {label}')

    containment_margin = 1.0e-6
    closure_thickness = 0.09
    frame_clearance = max(
        b.profiles['TRUSSWEB-130'].width_m,
        b.profiles['PURLIN-120x200'].width_m) / 2.0
    edge_plate = parallel_inset(
        deck_plate, frame_clearance + containment_margin, 'edge-frame')
    closure_inner_plate = parallel_inset(
        deck_plate, closure_thickness, 'closure-panel inner face')
    parapet_plate = parallel_inset(
        deck_plate,
        b.profiles['PARAPET-200x580'].width_m / 2.0 + containment_margin,
        'parapet')
    edge_spans = registered_bays(
        edge_plate, min(datums.value('bay_x_m'), datums.value('bay_y_m')))

    roof_slabs = [(ident, geometry, _slab_region(geometry))
                 for ident, geometry in _slabs(b, roof.id)]
    edge_nodes = [_point_on_edge(edge_plate, edge, lo) for edge, lo, _ in edge_spans]
    edge_posts = []
    for si, point in enumerate(edge_nodes):
        probe = Point(point.x, point.y)
        hosts = [ident for ident, _, region in roof_slabs
                 if region.distance(probe) <= GEOMETRY_EPS_M]
        post_id = f'STR-ROOF-EDGE-S{si:03d}'
        b.add(post_id, 'truss_web', 'structure', 'roof_closure',
              b.member([v3(point.x, point.y, z_bot),
                        v3(point.x, point.y, purlin_z - purlin_depth / 2.0)],
                       'TRUSSWEB-130'),
              'steel_light', level_id=roof.id,
              lattice_index={'level': roof.index, 'station': si},
              datum_refs=['truss_depth_m', 'bay_x_m', 'bay_y_m', *PLATE_DATUMS],
              supports=hosts,
              reason='Concept roof-edge post from the actual roof slab to the edge '
                     'purlin underside. Member and connection capacity remain unchecked.',
              **assembly_metadata(
                  'edge_post', 'ROOF-PERIMETER-CLOSURE',
                  *([] if hosts else ['ENVELOPE-CLOSURE-UNRESOLVED-SUPPORT'])))
        edge_posts.append(post_id)
    edge_purlins = []
    for si, a in enumerate(edge_nodes):
        nxt = (si + 1) % len(edge_nodes)
        c = edge_nodes[nxt]
        purlin_id = f'STR-PRL-EDGE-S{si:03d}'
        b.add(purlin_id, 'purlin', 'structure', 'roof_closure',
              b.member([v3(a.x, a.y, purlin_z), v3(c.x, c.y, purlin_z)],
                       'PURLIN-120x200'), 'steel_light', level_id=roof.id,
              lattice_index={'level': roof.index, 'station': si},
              datum_refs=['truss_depth_m', 'bay_x_m', 'bay_y_m', *PLATE_DATUMS],
              supports=[edge_posts[si], edge_posts[nxt]],
              reason='Concept edge purlin closes the deck perimeter between real '
                     'roof-edge posts; no capacity or waterproofing approval is implied.',
              **assembly_metadata('edge_purlin', 'ROOF-PERIMETER-CLOSURE'))
        covered_purlins.append(purlin_id)
        edge_purlins.append(purlin_id)
    # One real perimeter band avoids the false corner gaps produced by treating each
    # vertical panel as an infinitely thin Quad with an unrelated thickness field.
    # The outer face copies the Program Volume boundary and the inner face is its true
    # 90 mm parallel offset; both drawing cuts and containment checks now read the
    # same solid.
    b.add('ENV-ROOF-CLOSE-RING', 'spandrel_panel', 'envelope',
          'roof_closure', ExtrusionGeometry(
              boundary=deck_plate, holes=[closure_inner_plate],
              z_base=z_bot, z_top=deck_base),
          'white', level_id=roof.id,
          lattice_index={'level': roof.index},
          datum_refs=['truss_depth_m', *PLATE_DATUMS],
          supports=[*edge_posts, *edge_purlins],
          reason='Continuous 90 mm concept closure band from the roof slab to the '
                 'deck underside. Its outside face exactly copies the Program Volume '
                 'roof boundary; drainage, ventilation, fire performance and '
                 'waterproofing details require design.',
          **assembly_metadata('perimeter_closure', 'ROOF-PERIMETER-CLOSURE'))
    if roof_control is None:
        # Compatibility path: preserve the established single deck and member parapet
        # geometry.  The D2 warm-roof layers belong only to an explicit RoofControl.
        b.add('ENV-DECK-ROOF', 'roof_deck', 'envelope', 'roof',
              ExtrusionGeometry(boundary=deck_plate, holes=deck_holes,
                                z_base=round(deck_base, 5),
                                z_top=round(deck_base + deck_thickness, 5)),
              'white', level_id=roof.id, datum_refs=['truss_depth_m'],
              supports=covered_purlins,
              reason='Concept roof deck closes the complete registered roof boundary and '
                     'bears on the purlin top faces. Drainage and waterproofing are not designed.')
        deck_top = deck_base + deck_thickness
        par_z = deck_top + PARAPET_UPSTAND_M / 2.0
        for ei in range(len(parapet_plate)):
            a, c = parapet_plate[ei], parapet_plate[(ei + 1) % len(parapet_plate)]
            b.add(f'ENV-PAR-E{ei:03d}', 'parapet', 'envelope', 'roof',
                  b.member([v3(a.x, a.y, par_z), v3(c.x, c.y, par_z)],
                           'PARAPET-200x580'),
                  'white', level_id=roof.id, lattice_index={'edge': ei},
                  supports=['ENV-DECK-ROOF'],
                  reason='Parapet upstand on the enclosed elevations, bearing on the deck.')
    else:
        # The RoofSectionProfile owns this sequence and its physical cap. Every layer
        # is a real extrusion of the exact highest Program Volume union, including its
        # holes, so a section reads modelled construction rather than drawing-only fill.
        previous_layer_ids = list(covered_purlins)
        layer_ids: dict[str, str] = {}
        for layer in roof_assembly_layers(profile):
            z0 = round(z_bot + layer.base_offset_m, 6)
            z1 = round(z_bot + layer.top_offset_m, 6)
            b.add(
                layer.id, 'roof_deck', 'envelope', 'roof',
                ExtrusionGeometry(
                    boundary=deck_plate, holes=deck_holes,
                    z_base=z0, z_top=z1),
                layer.material_profile,
                level_id=roof.id,
                lattice_index={'level': roof.index},
                datum_refs=['truss_depth_m', *PLATE_DATUMS],
                supports=previous_layer_ids,
                thickness_m=layer.thickness_m,
                reason=(
                    f'{layer.part_role.replace("_", " ").capitalize()} in the '
                    'Program Volume warm-roof section. Its depth is an architectural '
                    f'convention; professional review remains required for {professional_review}.'),
                **assembly_metadata(layer.part_role))
            layer_ids[layer.part_role] = layer.id
            previous_layer_ids = [layer.id]

        structural_deck_top = z_bot + profile.deck_top_offset_m
        warm_roof_top = z_bot + profile.warm_roof_top_offset_m
        parapet_body_top = z_bot + profile.parapet_body_top_offset_m
        perimeter_common = dict(
            level_id=roof.id,
            datum_refs=['truss_depth_m', *PLATE_DATUMS],
        )

        def add_perimeter(
            id_prefix: str,
            part_role: str,
            material: str,
            *,
            width_m: float,
            z0: float,
            z1: float,
            supports: list[str],
            inset_m: float = 0.0,
        ) -> list[str]:
            geometries = roof_perimeter_geometries(
                roof_control, width_m=width_m, z_base=round(z0, 6),
                z_top=round(z1, 6), inset_m=inset_m)
            ids = []
            for index, geometry in enumerate(geometries):
                element_id = id_prefix if len(geometries) == 1 else f'{id_prefix}-P{index:02d}'
                b.add(
                    element_id, 'parapet', 'envelope', 'roof', geometry, material,
                    lattice_index={'level': roof.index, 'piece': index},
                    supports=supports,
                    thickness_m=width_m,
                    reason=(
                        f'{part_role.replace("_", " ").capitalize()} around the exact '
                        'controlled outer boundary and roof openings. Dimensions are '
                        'architectural conventions; product, joint, fixing, drainage '
                        'and envelope-performance review remains required.'),
                    **perimeter_common,
                    **assembly_metadata(part_role))
                ids.append(element_id)
            return ids

        parapet_ids = add_perimeter(
            'ENV-PARAPET-SUBSTRATE', 'parapet_substrate',
            'roof_parapet_substrate', width_m=ROOF_PARAPET_WIDTH_M,
            z0=structural_deck_top, z1=parapet_body_top,
            supports=[layer_ids['structural_deck_substrate']])
        insulation_upstand_ids = add_perimeter(
            'ENV-ROOF-INS-UPSTAND', 'insulation_upstand', 'roof_insulation',
            width_m=ROOF_PARAPET_INSULATION_UPSTAND_THICKNESS_M,
            inset_m=ROOF_PARAPET_WIDTH_M,
            z0=structural_deck_top + profile.vapour_control_thickness_m,
            z1=parapet_body_top,
            supports=[layer_ids['insulation_fall_build_up'], *parapet_ids])
        membrane_upstand_ids = add_perimeter(
            'ENV-ROOF-MEM-UPSTAND', 'waterproofing_upstand', 'roof_waterproofing',
            width_m=profile.waterproofing_thickness_m,
            inset_m=(ROOF_PARAPET_WIDTH_M
                     + ROOF_PARAPET_INSULATION_UPSTAND_THICKNESS_M),
            z0=warm_roof_top - profile.waterproofing_thickness_m,
            z1=parapet_body_top,
            supports=[layer_ids['waterproofing_membrane'], *insulation_upstand_ids])
        from .roof import ROOF_PARAPET_FINISH_THICKNESS_M
        facade = lattice.facade_control
        roof_trim = (ENVELOPE_TECTONICS[facade.tectonic_id].trim_material
                     if facade is not None else 'roof_coping')
        finish_ids = []
        coping_width = ROOF_COPING_WIDTH_M
        if facade is not None:
            finish_inset = (ROOF_PARAPET_WIDTH_M
                            + ROOF_PARAPET_INSULATION_UPSTAND_THICKNESS_M
                            + profile.waterproofing_thickness_m)
            finish_ids = add_perimeter(
                'ENV-ROOF-INNER-FINISH', 'parapet_inner_finish', roof_trim,
                width_m=ROOF_PARAPET_FINISH_THICKNESS_M,
                inset_m=finish_inset, z0=warm_roof_top, z1=parapet_body_top,
                supports=membrane_upstand_ids)
            coping_width = max(coping_width,
                               finish_inset + ROOF_PARAPET_FINISH_THICKNESS_M)
        add_perimeter(
            'ENV-ROOF-COPING', 'coping', roof_trim,
            width_m=coping_width,
            z0=parapet_body_top, z1=roof_control.physical_top_z,
            supports=[*parapet_ids, *insulation_upstand_ids, *membrane_upstand_ids,
                      *finish_ids])

    if roof_control is not None:
        emitted: list[tuple[str, object, float | None]] = []
        emitted_ids = b.element_ids - roof_start_ids
        for group in b.groups.values():
            for instance in group.instances:
                if instance.id in emitted_ids:
                    emitted.append((instance.id, instance.geometry, group.thickness_m))
        validate_roof_emission(roof_control, emitted, profiles=b.profiles)


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------

def _emit_envelope(b: _Builder, envelope: EnvelopeTectonic,
                   spec: GrammarSpec | None = None,
                   opacity_override: float | None = None) -> None:
    """Build the envelope in the tectonic family the selection chose.

    The body of this function used to be a single curtain wall. It now lives in
    `envelope.py`, one emitter per family, because the operation an elevation performs
    -- subdivide, subtract, overlay, recess -- is what makes two buildings look
    different, and that cannot be expressed as a parameter on one wall.
    """
    emit_envelope(b, envelope, spec, opacity_override)
    _emit_entry_canopy(b)


def _emit_entry_canopy(b: _Builder) -> None:
    """Hierarchy announces the entrance, or declines to."""
    span = b.datums.value('entry_canopy_span_m')
    if span < 1.5:
        return
    lattice = b.lattice
    if lattice.circulation_intent is not None:
        from .envelope import ENTRANCE_HEAD_M, planned_entrance
        entrance = planned_entrance(lattice, b.datums, b.approach)
        if entrance is None:
            raise ValueError('PV-CANOPY-ENTRY: authored entrance has no threshold')
        level = next(level for level in lattice.occupied
                     if level.id == entrance.level_id)
        origin, tangent = entrance.center, entrance.tangent
        outward = (-entrance.inward[0], -entrance.inward[1])
        # The underside clears the same door head that the facade emits.
        z = entrance.floor_z + ENTRANCE_HEAD_M + 0.28 / 2.0
    else:
        level = lattice.levels[1]
        origin = ((min(p.x for p in level.plate) + max(p.x for p in level.plate)) / 2.0,
                  min(p.y for p in level.plate))
        tangent, outward = (1.0, 0.0), (0.0, -1.0)
        z = level.z - b.datums.value('edge_fascia_m') - 0.9

    def point(u, v, height):
        return v3(origin[0] + tangent[0] * u + outward[0] * v,
                  origin[1] + tangent[1] * u + outward[1] * v, height)

    depth = min(4.2, span * 0.55)
    b.add('ENV-CAN-ENTRY', 'entry_canopy', 'envelope', 'canopy',
          BoxGeometry(center=point(0.0, depth / 2.0, z),
                      size=v3(span, depth, 0.28),
                      rotation_z=math.atan2(tangent[1], tangent[0])),
          'white', category='circulation', program='entry', level_id=level.id,
          datum_refs=['entry_canopy_span_m'],
          rule_refs=['HIERARCHY_TO_ENTRY_CANOPY', 'FCD-ENTRY-HIERARCHY-001'],
          reason='Entry canopy sized by the dominant order in the music; a level piece '
                 'produces no canopy at all.')
    for offset_x in (-span / 2.0 + 0.4, span / 2.0 - 0.4):
        b.add(f'ENV-CAN-POST-{"L" if offset_x < 0 else "R"}', 'entry_canopy',
              'envelope', 'canopy',
              b.member([point(offset_x, depth - 0.4, lattice.levels[0].z),
                        point(offset_x, depth - 0.4, z)],
                       'STRUT-CHS180'),
              'steel_white', category='circulation', program='entry', level_id=level.id,
              datum_refs=['entry_canopy_span_m'],
              reason='Canopy support returning to the podium.')


# ---------------------------------------------------------------------------
# Circulation
# ---------------------------------------------------------------------------

def _emit_flight(
    b: _Builder, flight_id: str, start: Vector3, end: Vector3, width: float,
    level_id: str, *, typed_supports: bool = False,
    terminal_supports: Iterable[str] = (),
    clear_end_landing: bool = False,
) -> None:
    riser = b.datums.value('riser_m')
    dz = end.z - start.z
    dx, dy = end.x - start.x, end.y - start.y
    run = math.hypot(dx, dy)
    if dz <= 0.01 or run <= 0.01:
        return
    steps = max(2, int(round(dz / riser)))
    ux, uy = dx / run, dy / run
    angle = math.atan2(uy, ux)
    flight_stringers = [f'CIR-STG-{flight_id}-{tag}' for tag in ('L', 'R')]
    terminal_supports = tuple(dict.fromkeys(terminal_supports))
    for s in range(steps):
        f0 = s / steps
        b.add(f'CIR-TRD-{flight_id}-S{s:03d}', 'stair_tread', 'circulation', 'stairs',
              BoxGeometry(
                  center=v3(start.x + dx * (f0 + 0.5 / steps),
                            start.y + dy * (f0 + 0.5 / steps),
                            start.z + dz * (f0 + 1.0 / steps) - 0.045),
                  size=v3(run / steps + 0.06, width, 0.09), rotation_z=angle),
              'white', category='circulation', program='circulation',
              level_id=level_id, lattice_index={'flight': int(flight_id[-2:]), 'step': s},
              datum_refs=['riser_m', 'floor_to_floor_m', 'flight_width_m'],
              supports=flight_stringers if typed_supports else (),
              rule_refs=['PV-CIRC-PUBLIC-STAIR'] if typed_supports else (),
              reason=('Program Volume tread with explicit stringer hosts; the riser '
                      'datum divides the flight.' if typed_supports else
                      'Individual tread; the riser datum divides the flight.'))
    px, py = -uy, ux
    for side, tag in ((-1, 'L'), (1, 'R')):
        ox, oy = px * side * width / 2.0, py * side * width / 2.0
        b.add(f'CIR-STG-{flight_id}-{tag}', 'stair_stringer', 'circulation', 'stairs',
              b.member([v3(start.x + ox, start.y + oy, start.z - 0.22),
                        v3(end.x + ox, end.y + oy, end.z - 0.22)], 'STRINGER-180x450'),
              'white_soft', category='circulation', program='circulation',
              level_id=level_id, datum_refs=['flight_width_m'],
              supports=terminal_supports if typed_supports else (),
              rule_refs=['PV-CIRC-PUBLIC-STAIR'] if typed_supports else (),
              reason=('Program Volume stringer with explicit lower-terminal support.'
                      if typed_supports else 'Stringer carries the flight.'))
    rail_end = end
    if clear_end_landing:
        # The arrival landing is a shared clear-space claim. A rail axis ending
        # on its edge still puts half the physical section through that claim.
        # Keep the rail/post bodies on the flight side, without changing tread,
        # landing or doorway geometry. Extensions and guard design remain reviewable.
        reach = max(math.hypot(b.profiles[key].depth_m,b.profiles[key].width_m)/2
                    for key in ('RAIL-CHS64','POST-45x45'))
        fraction = max(0.,1.-reach/run)
        rail_end = v3(start.x+dx*fraction,start.y+dy*fraction,start.z+dz*fraction)
    _emit_railing(b, f'{flight_id}-RAIL', start, rail_end, width, level_id,
                  typed_supports=typed_supports,
                  tread_prefix=f'CIR-TRD-{flight_id}-S' if typed_supports else None,
                  tread_count=steps if typed_supports else None)


def _emit_railing(
    b: _Builder, rail_id: str, start: Vector3, end: Vector3, width: float,
    level_id: str, spacing: float | None = None, *,
    typed_supports: bool = False, tread_prefix: str | None = None,
    tread_count: int | None = None,
) -> None:
    height = b.datums.value('rail_height_m')
    if spacing is None:
        spacing = b.datums.value('rail_post_spacing_m')
    dx, dy = end.x - start.x, end.y - start.y
    run = math.hypot(dx, dy)
    if run < 0.2:
        return
    px, py = -dy / run, dx / run
    posts = max(2, int(run / spacing))
    for side, tag in (((-1, 'L'), (1, 'R')) if width > 0.01 else ((0, 'C'),)):
        ox, oy = px * side * width / 2.0, py * side * width / 2.0
        post_ids = [f'CIR-RAL-{rail_id}-{tag}-P{s:03d}' for s in range(posts + 1)]
        rail_supports = post_ids[:1] + post_ids[-1:] if typed_supports else []
        for level, drop in (('T', 0.0), ('M', 0.5)):
            b.add(f'CIR-RAL-{rail_id}-{tag}-{level}', 'railing', 'circulation', 'safety',
                  b.member([v3(start.x + ox, start.y + oy, start.z + height - drop),
                            v3(end.x + ox, end.y + oy, end.z + height - drop)],
                           'RAIL-CHS64'),
                  'steel_white', category='circulation', program='circulation',
                  level_id=level_id,
                  datum_refs=['rail_height_m', 'rail_post_spacing_m'],
                  supports=rail_supports,
                  rule_refs=['PV-CIRC-PUBLIC-STAIR'] if typed_supports else (),
                  reason=('Program Volume guard rail with explicit post hosts; also the '
                          'model scale anchor.' if typed_supports else
                          'Guard rail at the declared height; also the model scale anchor.'))
        for s in range(posts + 1):
            f = s / posts
            x = start.x + dx * f + ox
            y = start.y + dy * f + oy
            z = start.z + (end.z - start.z) * f
            tread_supports = ()
            if typed_supports and tread_prefix and tread_count:
                tread_index = min(tread_count - 1, int(f * tread_count))
                tread_supports = (f'{tread_prefix}{tread_index:03d}',)
            b.add(post_ids[s], 'railing', 'circulation', 'safety',
                  b.member([v3(x, y, z), v3(x, y, z + height)], 'POST-45x45'),
                  'steel_white', category='circulation', program='circulation',
                  level_id=level_id,
                  datum_refs=['rail_height_m', 'rail_post_spacing_m'],
                  supports=tread_supports,
                  rule_refs=['PV-CIRC-PUBLIC-STAIR'] if typed_supports else (),
                  reason=('Program Volume guard post with an explicit tread host.'
                          if typed_supports else
                          'Guard post at the repeated spacing the score set.'))


# The clear gap a landing keeps from a plate edge it overlaps, so the two read as
# meeting rather than as coinciding.


def _program_carrier_regions(lattice: Lattice) -> dict[str, object]:
    """Union the circulation-spine volumes on each occupied level.

    The regions resolve on the immutable Program Volume grid.  The ordinary lattice
    grid is later reframed around the chosen core, so using it here would make the
    authority depend on whether this function had already run once.
    """
    intent = lattice.circulation_intent
    if intent is None:
        return {}
    carrier_ids = set(intent.carrier_volume_ids)
    by_level: dict[str, list] = {}
    for region in lattice.program_volume_regions:
        if region.id not in carrier_ids:
            continue
        x0, y0, x1, y1 = region.resolve_bounds(lattice)
        by_level.setdefault(region.level_id, []).append(plan_box(x0, y0, x1, y1))
    return {level_id: unary_union(parts) for level_id, parts in by_level.items()}


def _plate_south_at(plate, x: float) -> float:
    """The plate's southern boundary on the vertical line `x`.

    A plate is not a rectangle -- these have apsidal ends and step-backs -- so its
    southernmost point and its southern edge at a given x are different numbers, and
    using the first where the second is meant puts an arriving landing outside the
    building by however much the boundary curves.
    """
    crossings: list[float] = []
    count = len(plate)
    for index in range(count):
        a, b = plate[index], plate[(index + 1) % count]
        if (a.x > x) == (b.x > x) or abs(b.x - a.x) < 1e-9:
            continue
        t = (x - a.x) / (b.x - a.x)
        crossings.append(a.y + (b.y - a.y) * t)
    return min(crossings) if crossings else min(point.y for point in plate)


def _plate_north_at(plate, x: float) -> float:
    """The plate's northern boundary on the vertical line `x` (see `_plate_south_at`)."""
    crossings: list[float] = []
    count = len(plate)
    for index in range(count):
        a, b = plate[index], plate[(index + 1) % count]
        if (a.x > x) == (b.x > x) or abs(b.x - a.x) < 1e-9:
            continue
        t = (x - a.x) / (b.x - a.x)
        crossings.append(a.y + (b.y - a.y) * t)
    return max(crossings) if crossings else max(point.y for point in plate)


def _stair_sites(lattice, width: float, run: float, levels: list, *,
                 allowed_by_level: dict[str, object] | None = None,
                 ) -> list[tuple[float, float]]:
    """Every point in plan where a stair serving these levels can stand.

    The margin is the stair's *whole* footprint, landings included, not the width
    of one flight. Checking the flight alone was the first version's mistake and
    it put landings a metre and a half outside the plate they were flush with,
    which is a worse failure than the one it replaced: flush and unreachable.

    Forty divisions rather than twenty. At the coarse grid the best remote
    candidate on the demo plan came out 16.56 m from the first stair against a
    16.8 m requirement -- a 1.4 % miss that was resolution, not geometry, and it
    cost the building its second exit.
    """
    plates = [plan_polygon(level.plate).difference(
        unary_union([plan_polygon(hole) for hole in level.voids]))
        for level in levels if level.plate]
    if not plates:
        return []
    # Sample the floor the run actually shares, not the plan rectangle. The plan
    # bounds are the orthogonal figure the family declares; an apsidal end or a
    # projecting level stands outside them, and sampling the rectangle alone never
    # visited the seventeen metres of plate west of a theatre's house -- so a slab
    # that had room for its stairs reported that no stair could serve any level.
    x_min = max(min(p.x for p in level.plate) for level in levels if level.plate)
    x_max = min(max(p.x for p in level.plate) for level in levels if level.plate)
    y_min = max(min(p.y for p in level.plate) for level in levels if level.plate)
    y_max = min(max(p.y for p in level.plate) for level in levels if level.plate)
    # Inside the orthogonal frame's extent: an apsidal end stands on radial columns
    # and ring beams, and a core there would have no grid line to be drawn to. The
    # extent lines are the two the grid keeps fixed, so this does not move when the
    # grid is redrawn to the cores.
    x_min, x_max = max(x_min, lattice.x_lines[0]), min(x_max, lattice.x_lines[-1])
    y_min, y_max = max(y_min, lattice.y_lines[0]), min(y_max, lattice.y_lines[-1])
    if x_max - x_min < 1.0 or y_max - y_min < 1.0:
        return []
    # Sampled from the plates alone, never from the module grid: the grid is drawn
    # to the cores afterwards (`_frame_the_volumes`), so a site must not depend on
    # where its interior lines fall. The sites flush with the extent are sampled
    # as well: a sample a bay short of an edge leaves the sliver `_sliver_faces`
    # penalises, and the remote corner a second exit wants is exactly such a
    # sample -- without the flush sites the courtyard's pair stood 25 m apart
    # against 36 m required, on sliver-free floor in the middle of the plan. A face
    # on the extent line is the grid's own line, so a corner costs the frame nothing.
    half_x = width * 1.1 + CORE_CLEARANCE_M
    half_y = run / 2.0 + 1.7 + CORE_CLEARANCE_M
    # A millimetre inside the extent: rounding put the flush face a hair outside
    # the plate and `covers` rejected every flush site, silently.
    xs = sorted({round(x_min + (x_max - x_min) * u / 40.0, 4) for u in range(5, 36)}
                | {round(x_min + half_x + 0.001, 4), round(x_max - half_x - 0.001, 4)})
    ys = sorted({round(y_min + (y_max - y_min) * v / 40.0, 4) for v in range(5, 36)}
                | {round(y_min + half_y + 0.001, 4), round(y_max - half_y - 0.001, 4)})
    if allowed_by_level is not None:
        # Program Volumes can reserve exactly one core footprint. A whole-building
        # sample cannot find that single feasible centre. Add contact events from
        # the authored carrier boundaries; the complete-footprint checks stay below.
        vertices = []
        for allowed in allowed_by_level.values():
            parts = [allowed] if allowed.geom_type == 'Polygon' else list(allowed.geoms)
            vertices.extend(point for part in parts for point in part.exterior.coords)
        xs = sorted(set(xs) | {x + sign * half_x for x, _ in vertices for sign in (-1, 1)})
        ys = sorted(set(ys) | {y + sign * half_y for _, y in vertices for sign in (-1, 1)})
    sites: list[tuple[float, float]] = []
    for x in xs:
        for y in ys:
            footprint = plan_box(*_core_box(x, y, width, run))
            program_fit = True
            if allowed_by_level is not None:
                for level in levels:
                    if level.kind != 'occupied':
                        continue
                    allowed = allowed_by_level.get(level.id)
                    if allowed is None or not allowed.buffer(1e-7).covers(footprint):
                        program_fit = False
                        break
            if program_fit and all(plate.buffer(1e-7).covers(footprint) for plate in plates):
                sites.append((x, y))
    return sites


def _core_xy(point, dx: float, dy: float, run_axis: str = 'y') -> tuple[float, float]:
    """Canonical Y-running stair offsets in World XY; X rotates clockwise."""
    ax, ay = point
    return (ax + dy, ay - dx) if run_axis == 'x' else (ax + dx, ay + dy)


def _core_bounds(point, rect, run_axis: str = 'y'):
    corners = [_core_xy(point, x, y, run_axis)
               for x, y in ((rect[0], rect[1]), (rect[2], rect[3]))]
    return (min(p[0] for p in corners), min(p[1] for p in corners),
            max(p[0] for p in corners), max(p[1] for p in corners))


def _core_run_axis(anchors, point) -> str:
    if point == anchors.get('primary'):
        return anchors.get('primary_run_axis', 'y')
    if point == anchors.get('second'):
        return anchors.get('second_run_axis', 'y')
    axes = anchors.get('extra_run_axes', [])
    return next((axes[index] if index < len(axes) else 'y'
                 for index, (candidate, _levels) in enumerate(anchors.get('extras', []))
                 if candidate == point), 'y')


def _core_route_radius() -> float:
    """Use the same clear route body and wall allowance as the public planner."""
    from .program import PublicCirculationPlan
    from .partitions import PARTITION_TYPES
    plan = PublicCirculationPlan(
        wall_allowance_m=max(part.thickness_mm for part in PARTITION_TYPES) / 2000.0)
    return plan.clear_width_m / 2.0 + plan.wall_allowance_m


def _core_terminal(anchors, point, facing, radius):
    return _core_xy(point, 0.0,
        -facing * (anchors['run'] / 2.0 + 1.7 + CORE_CLEARANCE_M
                   + radius + CORE_TERMINAL_GAP_M),
        _core_run_axis(anchors, point))


def _core_box(ax: float, ay: float, width: float,
              run: float, run_axis: str = 'y') -> tuple[float, float, float, float]:
    """Whole stair footprint, including either landing direction and edge clearance."""
    return _core_bounds((ax, ay), (-width * 1.1 - CORE_CLEARANCE_M,
            -run / 2.0 - 1.7 - CORE_CLEARANCE_M,
            width * 1.1 + CORE_CLEARANCE_M,
            run / 2.0 + 1.7 + CORE_CLEARANCE_M), run_axis)



def _box_overlaps(a, b, *, tolerance=0.0) -> bool:
    return (min(a[2], b[2]) - max(a[0], b[0]) > tolerance
            and min(a[3], b[3]) - max(a[1], b[1]) > tolerance)


def _opening_span(ax: float, ay: float, width: float, run: float,
                  facing: float, run_axis: str = 'y') -> tuple[float, float, float, float]:
    """The flight-and-turn opening a stair at this anchor cuts, facing this way."""
    y0, y1 = -facing * run / 2.0, facing * (run / 2.0 + FLIGHT_TURN_M)
    return _core_bounds((ax, ay), (-width - WELL_EDGE_M, min(y0, y1) - WELL_EDGE_M,
            width + WELL_EDGE_M, max(y0, y1) + WELL_EDGE_M), run_axis)


def _core_rects(anchors) -> list[tuple[float, float, float, float]]:
    """The plan rectangles the stair cores enclose: flights, landings and clearance.

    These are the volumes the grid frames and the frame stays out of (decision
    0022): every face is a grid line, the core walls stand on those faces, and no
    column, girder or joist is drawn inside. The lift shaft is not among them -- it
    is an opening the floor framing trims, in the bay beside the stair.
    """
    width, run = anchors['width'], anchors['run']
    points = [anchors['primary']] if anchors.get('primary') is not None else []
    if anchors.get('second') is not None:
        points.append(anchors['second'])
    points += [point for point, _levels in anchors.get('extras', [])]
    return [_core_box(*point, width, run, _core_run_axis(anchors, point)) for point in points]


def _sliver_faces(lattice, rect, keep_out) -> int:
    """How many faces of this rectangle would leave a bay narrower than `MIN_BAY_M`
    against a plate boundary line or a neighbouring reserved volume without standing
    on it. Zero is a core the grid frames cleanly; the placement prefers it, and the
    grid never drops a face to avoid a sliver, because a face that is not a line is a
    joist through the stair."""
    x0, y0, x1, y1 = rect
    xs = [lattice.x_lines[0], lattice.x_lines[-1]] + [v for r in keep_out for v in (r[0], r[2])]
    ys = [lattice.y_lines[0], lattice.y_lines[-1]] + [v for r in keep_out for v in (r[1], r[3])]
    count = 0
    for face, lines in ((x0, xs), (x1, xs), (y0, ys), (y1, ys)):
        if any(0.05 < abs(face - line) < MIN_BAY_M for line in lines):
            count += 1
    return count


def _frame_the_volumes(lattice, anchors, datums, avoid: list = ()) -> None:
    """The grid follows the volumes (decision 0022).

    Every face of every stair core is a grid line; the score's bay module fills the
    spans between the fixed lines; no line is added inside a core. The plate's extent
    lines and the archetype's carved room edges stay fixed as well, and a massing
    that handed in its own grid keeps every line of it. This replaces the search for
    a grid the stair could fit, the transfer frames around wells it could not, and
    the coarsening of the module to hold the well: the structure is drawn to the
    core, not the core into the structure. Idempotent -- the cores are placed from
    the plates alone, so calling it again reproduces the same lines.
    """
    if getattr(lattice, 'world_xy_grid', None) is not None:
        return  # independent registration survives core movement and carved rooms
    rects = _core_rects(anchors)
    carved = [rect for rects_ in lattice.carved.values() for rect in rects_]

    def lines_for(axis: int, current: list[float], module: float) -> list[float]:
        lo, hi = current[0], current[-1]
        fixed = {lo, hi}
        faces = sorted({round(rect[axis], 4) for rect in rects}
                       | {round(rect[axis + 2], 4) for rect in rects})
        if getattr(lattice, 'grid_given', False):
            # The massing's lines stand, except where one would leave a sliver bay
            # against a core face: the volume outranks the module there too.
            fixed |= {line for line in current
                      if not any(0.05 < abs(line - face) < MIN_BAY_M for face in faces)}
        for rect in rects + carved:
            for value in (rect[axis], rect[axis + 2]):
                if lo + 0.05 < value < hi - 0.05:
                    fixed.add(round(value, 4))
        ordered: list[float] = []
        for value in sorted(fixed):
            if not ordered or value - ordered[-1] > 0.05:
                ordered.append(value)
        spans = [(rect[axis], rect[axis + 2]) for rect in rects]
        # Openings a module line must not run through but whose faces are not
        # lines: a lift shaft the massing placed, which the floor framing trims.
        keep_clear = spans + [(rect[axis], rect[axis + 2]) for rect in avoid]
        lines: list[float] = []
        for a, c in zip(ordered, ordered[1:]):
            lines.append(a)
            if any(c0 - 0.05 <= a and c <= c1 + 0.05 for c0, c1 in spans):
                continue  # the core's own extent: one bay, however wide the module
            count = max(1, int(round((c - a) / module)))
            for k in range(1, count):
                value = a + (c - a) * k / count
                if any(c0 + 0.05 < value < c1 - 0.05 for c0, c1 in keep_clear):
                    continue
                lines.append(value)
        lines.append(ordered[-1])
        return [round(v, 4) for v in lines]

    lattice.x_lines = lines_for(0, lattice.x_lines, datums.value('bay_x_m'))
    lattice.y_lines = lines_for(1, lattice.y_lines, datums.value('bay_y_m'))


def _stair_anchor(lattice, width: float, run: float, levels: list,
                  away_from: tuple[float, float] | None = None,
                  keep_out: tuple = (), required: float = 0.0,
                  allowed_by_level: dict[str, object] | None = None,
                  ) -> tuple[float, float] | None:
    """A point in plan that lies inside every plate the stair has to serve.

    The stair core used to be authored at literal coordinates taken from the original
    thirty-six by twenty-two metre slab -- `v3(16.0, south, ...)`, `ax = min_x - 1.5`,
    `v2(18.4, 5.2)` for the lift shaft. Once the footprint became a property of the
    massing family those numbers stopped describing anywhere: on a twenty-one metre
    tower more than half the treads stood outside the building, and no landing on any of
    the fourteen models met the floor it claimed.

    This is the same invariant the column stack already keeps, applied to circulation: a
    node is only usable if *every* plate from the bottom to the top contains it. The
    search prefers the north-east quadrant, away from the south entrance, because that
    is where a service stair belongs and because the sectional cut is on those faces --
    a stair there stays visible in section. The feasibility scan itself lives in
    `_stair_sites`, because the pair adjustment in `core_anchors` needs the whole
    region, not one preferred point of it.
    """
    sites = _stair_sites(
        lattice, width, run, levels, allowed_by_level=allowed_by_level)
    # A core whose flight opening straddles a grid line puts a girder through the
    # stair -- a transfer this compiler does not design. Sites are taken in order of
    # how many grid lines they must straddle: inside one bay first, then one line,
    # then two. A stair deeper than its bay never reaches zero, and the fewest
    # transfers is then the honest best; each one is reported rather than cut.
    usable = [site for site in sites
              if not any(_box_overlaps(_core_box(*site, width, run), rect)
                         for rect in keep_out)]
    if not usable:
        return None
    # The grid is drawn to the core (decision 0022), so no site puts a girder
    # through the stair. What a site can still do is stand a face of the core a
    # sliver short of a plate edge or of a neighbouring reserved volume, which the
    # grid would then have to frame as a bay too narrow to mean anything. Fewest
    # such faces first; the remoteness or back-of-plan score decides among equals.
    # (Preferring sites that share lines with another core was tried and measured
    # worse: the second core stacked over the first in plan and cut every room
    # band in two. Rooms lay out on the module rows, so a face line of its own
    # costs them nothing.)
    def penalty(site) -> int:
        return _sliver_faces(lattice, _core_box(*site, width, run), keep_out)
    penalties = {site: penalty(site) for site in usable}
    if away_from is not None:
        # A second exit is only an exit if it is remote from the first. IBC
        # 1007.1.1 wants a third of the diagonal of the area served (`required`),
        # and that is code, where a sliver bay is a preference: among the sites
        # that meet the separation the fewest slivers wins, and only when none
        # does is the farthest taken regardless. Ranking slivers first left the
        # bar-podium's pair 15 m apart against 25 m, with the remote corner of the
        # podium refused for a sliver against the ramp's keep-out.
        def gap(site) -> float:
            return math.hypot(site[0] - away_from[0], site[1] - away_from[1])
        remote = [site for site in usable if gap(site) >= required]
        pool = remote or usable
        fewest = min(penalties[site] for site in pool)
        return max((site for site in pool if penalties[site] == fewest), key=gap)
    return _primary_sites(lattice, usable, penalties)[0]


def _primary_sites(lattice, usable: list, penalties: dict) -> list:
    """The primary's sites in order of preference: fewest sliver faces, then the
    back of the plan, then the east side. `usable` already excludes an archetype's
    carved floor -- a stair in the auditorium is the collision that filter ends."""
    def score(site) -> tuple:
        x, y = site
        return (penalties[site],
                -((y - lattice.plan.y_min) + (x - lattice.plan.x_min) * 0.35))
    return sorted(usable, key=score)


def _emit_floor_landing(
    b: _Builder, landing_id: str, x: float, y: float, level, size_x: float,
    size_y: float, *, supports: Iterable[str] = (),
) -> None:
    """A landing at a floor level, flush with the plate and owning its footprint.

    Flush matters: a landing whose top sits at the plate's z is a floor a person steps
    onto, and one sitting a few centimetres proud or shy is a trip hazard drawn to look
    like a landing. The slab is emitted *below* `level.z` so its top surface is the
    floor -- and the slab gives up the landing's footprint (`_landing_footprints`), so
    the two walking surfaces abut instead of lying one inside the other: two coplanar
    surfaces in one place drew as a striped fight and counted the same floor twice.
    """
    supports = tuple(supports)
    thickness = max(0.18, b.datums.value('slab_thickness_m') * 0.6)
    b.add(landing_id, 'stair_landing', 'circulation', 'stairs',
          BoxGeometry(center=v3(x, y, level.z - thickness / 2.0),
                      size=v3(size_x, size_y, thickness)),
          'white', category='circulation', program='circulation',
          level_id=level.id, lattice_index={'level': level.index},
          datum_refs=['flight_width_m', 'slab_thickness_m'],
          supports=supports,
          rule_refs=(['CIR-INV-LANDING-MEETS-PLATE']
                     + (['PV-CIRC-PUBLIC-STAIR'] if supports else [])),
          reason=(
              'Program Volume floor landing with explicit slab support. Its top is '
              'flush with the plate and it owns its own footprint -- the slab is cut '
              'back to its edge -- so the flight arrives on one floor surface.'
              if supports else
              'Floor landing. Its top is flush with the plate and it owns its own '
              'footprint -- the slab is cut back to its edge -- so the flight '
              'arrives on one floor surface rather than on two drawn in the same '
              'place.'))


def _emit_core_door_threshold(
    b: _Builder, landing_id: str, ax: float, ay: float, level, width: float,
    run: float, facing: float, run_axis: str = 'y',
) -> None:
    """Emit the floor carried through a protected-stair door aperture.

    The core wall separates the storey plate from the stair landing by its physical
    thickness.  An open door without floor through that thickness leaves two valid
    surfaces with no walkable joint.  This registered threshold spans the wall and
    bears slightly onto the landing and adjacent plate, so navigation, the portal
    report and a detail section all read the same physical connection.
    """
    _bx0, by0, _bx1, by1 = _core_box(ax, ay, width, run)
    outer_y = by0 if facing > 0 else by1
    centre_y = outer_y + facing * CORE_WALL_M / 2.0
    centre = _core_xy((ax, ay), 0.0, centre_y - ay, run_axis)
    size = (CORE_DOOR_W_M, CORE_WALL_M + CORE_THRESHOLD_BEARING_M * 2.0)
    if run_axis == 'x':
        size = size[::-1]
    thickness = max(0.18, b.datums.value('slab_thickness_m') * 0.6)
    threshold_id = f'{landing_id}-THR'
    b.add(
        threshold_id, 'stair_landing', 'circulation', 'stairs',
        BoxGeometry(
            center=v3(*centre, level.z - thickness / 2.0),
            size=v3(
                *size,
                thickness,
            ),
        ),
        'white', category='circulation', program='circulation',
        level_id=level.id, lattice_index={'level': level.index},
        datum_refs=['flight_width_m', 'slab_thickness_m'],
        supports=[landing_id],
        rule_refs=['CIR-INV-LANDING-MEETS-PLATE',
                   'CIR-INV-CORE-DOOR-THRESHOLD'],
        reason=(
            'Protected-stair door threshold, flush with the served floor. It carries '
            f'the walking surface through the {CORE_WALL_M * 1000:.0f} mm core wall '
            f'and bears {CORE_THRESHOLD_BEARING_M * 1000:.0f} mm onto the stair '
            'landing and adjacent plate; finish, membrane, fire stopping and door '
            'manufacturer interfaces require professional review.'
        ),
        assembly_id=f'ASM-PV-PROTECTED-STAIR-{level.id}',
        part_role='landing_door_threshold',
    )


def _local_xy(origin, tangent, outward, u: float, v: float) -> tuple[float, float]:
    return (origin[0] + tangent[0] * u + outward[0] * v,
            origin[1] + tangent[1] * u + outward[1] * v)


def _local_rect_bounds(origin, tangent, outward, u0: float, v0: float,
                       u1: float, v1: float) -> tuple[float, float, float, float]:
    points = [_local_xy(origin, tangent, outward, u, v)
              for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]
    return (min(point[0] for point in points), min(point[1] for point in points),
            max(point[0] for point in points), max(point[1] for point in points))


def _transform_ramp_plan(plan: RampPlan, origin, tangent, outward) -> RampPlan:
    """Rotate a code-checked local switchback onto a Program Volume entry edge."""
    runs = []
    for run in plan.runs:
        start = _local_xy(origin, tangent, outward, run.x_start, run.start_y)
        end = _local_xy(origin, tangent, outward, run.x_end, run.end_y)
        runs.append(RampRun(
            index=run.index,
            x_start=round(start[0], 4), x_end=round(end[0], 4),
            y=round((start[1] + end[1]) / 2.0, 4),
            y_start=round(start[1], 4), y_end=round(end[1], 4),
            z_start=run.z_start, z_end=run.z_end,
            direction=run.direction))
    tangent_is_world_y = abs(tangent[1]) > abs(tangent[0])
    landings = []
    for landing in plan.landings:
        centre = _local_xy(origin, tangent, outward, landing.x, landing.y)
        landings.append(RampLanding(
            index=landing.index, x=round(centre[0], 4), y=round(centre[1], 4),
            z=landing.z,
            size_x=(landing.size_y if tangent_is_world_y else landing.size_x),
            size_y=(landing.size_x if tangent_is_world_y else landing.size_y),
            kind=landing.kind))
    centre_line = []
    for u, v, z in plan.centre_line:
        x, y = _local_xy(origin, tangent, outward, u, v)
        centre_line.append((round(x, 4), round(y, 4), z))
    return plan.model_copy(update={
        'runs': runs,
        'landings': landings,
        'centre_line': centre_line,
        'footprint_x_m': (plan.footprint_y_m if tangent_is_world_y
                          else plan.footprint_x_m),
        'footprint_y_m': (plan.footprint_x_m if tangent_is_world_y
                          else plan.footprint_y_m),
    })


def _plan_program_volume_approach(
    lattice: Lattice, datums: DatumSet, *, apron_depth_m: float,
) -> dict:
    """Place entry, public stair and ramp from the authored boundary station.

    ADA dimensions remain in :mod:`ada`.  The Program Volume protocol decides the
    facade edge, local orientation, which side receives the folded route and how far
    the approach may travel.  If the declared edge/depth cannot hold a legal ramp,
    the result keeps the named intent and returns no ramp.
    """
    intent = lattice.circulation_intent
    if intent is None:
        raise ValueError('Program Volume approach called without circulation intent')
    podium = next((level for level in lattice.occupied
                   if level.id == intent.entry_station.level_id), None)
    if podium is None:
        raise ValueError(
            f'PV-CIRC-ENTRY-LEVEL: {intent.entry_station.level_id} is not an '
            'occupied lattice level')
    origin, tangent, outward = intent.entry_station.resolve(lattice)
    plate = plan_polygon(podium.plate).difference(
        unary_union([plan_polygon(hole) for hole in podium.voids]))
    if plate.boundary.distance(Point(*origin)) > 1.0e-5:
        raise ValueError('PV-CIRC-ENTRY-BOUNDARY: entry station left its volume union')
    if not math.isclose(intent.entry_floor_elevation_m, podium.z, abs_tol=1.0e-4):
        raise ValueError(
            'PV-CIRC-ENTRY-Z: circulation intent elevation does not match its '
            f'Program Volume level ({intent.entry_floor_elevation_m:.4f} != '
            f'{podium.z:.4f})')

    # The threshold report measures 1.2 m of clear walking surface on each side of
    # the door, beginning outside the reveal depth.  The old entry landing stopped
    # 795 mm short of that measured exterior approach: the leaf existed, but its
    # outside half opened onto air.  Give the Program Volume entry one continuous
    # landing across the complete measured threshold zone.  This is a project review
    # convention, not a declaration of adopted-code manoeuvring clearance.
    from .envelope import ENTRANCE_MIN_WIDTH_M, ENTRANCE_REVEAL_DEPTH_M
    from .portals import APPROACH_DEPTH_M

    width = datums.value('flight_width_m')
    threshold_reach = ENTRANCE_REVEAL_DEPTH_M / 2.0 + APPROACH_DEPTH_M
    landing_depth = threshold_reach * 2.0
    landing_width = max(width * 1.9, ENTRANCE_MIN_WIDTH_M)
    centre_v = 0.0
    entry = _local_rect_bounds(
        origin, tangent, outward,
        -landing_width / 2.0, centre_v - landing_depth / 2.0,
        landing_width / 2.0, centre_v + landing_depth / 2.0)
    result = {
        'podium_id': podium.id,
        'entry': entry,
        'entry_x': origin[0],
        'entry_point': origin,
        'entry_tangent': tangent,
        'entry_outward': outward,
        'entry_station': intent.entry_station,
        'public_stair_family': intent.public_stair_family,
        'ramp_preference': intent.ramp_preference,
        'ramp': None,
        'ramp_top': None,
        'access': None,
        'access_point': None,
        'ramp_attachment_verified': False,
    }

    if intent.arrival_assembly is not None:
        assembly = intent.arrival_assembly
        if not math.isclose(assembly.ramp.rise_m,podium.z-lattice.levels[0].z,abs_tol=1e-4):
            raise ValueError('PV-CIRC-ARRIVAL-RISE: frozen arrival no longer matches its served floor')
        ramp = _transform_ramp_plan(assembly.ramp,origin,tangent,outward)
        top = next(p for p in ramp.landings if p.kind=='top')
        result.update(entry=_local_rect_bounds(origin,tangent,outward,*assembly.entry_rect),
            ramp=ramp,ramp_top=(top.x-top.size_x/2,top.y-top.size_y/2,
                                top.x+top.size_x/2,top.y+top.size_y/2),
            public_stair_family=assembly.stair_family,
            arrival_assembly=assembly)
        return result

    x_lines = lattice.program_volume_x_lines or lattice.x_lines
    y_lines = lattice.program_volume_y_lines or lattice.y_lines
    i0, j0, i1, j1 = intent.entry_station.grid_edge
    edge_start = (x_lines[i0], y_lines[j0])
    edge_end = (x_lines[i1], y_lines[j1])
    edge_length = math.dist(edge_start, edge_end)
    boundary_plan = plan_boundary_switchback(
        edge_length_m=edge_length, fraction=intent.entry_station.fraction,
        flight_width_m=width, rise_m=podium.z - lattice.levels[0].z,
        approach_depth_m=intent.approach_depth_m,
        preference=intent.ramp_preference, z_base=lattice.levels[0].z,
        apron_depth_m=apron_depth_m)
    ramp_width = boundary_plan.ramp_width_m
    sides, order = boundary_plan.sides, boundary_plan.order
    local = boundary_plan.ramp
    if local is not None:
        transformed = _transform_ramp_plan(local, origin, tangent, outward)
        top = next((landing for landing in transformed.landings
                    if landing.kind == 'top'), None)
        if top is not None:
            # The top landing doubles as the two-sided floor at a dedicated ramp
            # portal.  Keep its centre-line and code-checked route unchanged, enlarge
            # only the level landing so its outboard half reaches the complete portal
            # approach and its tangential width can carry the clear door opening.
            tangent_is_world_y = abs(tangent[1]) > abs(tangent[0])
            dx, dy = top.x - origin[0], top.y - origin[1]
            top_v = dx * outward[0] + dy * outward[1]
            normal_size = top.size_x if tangent_is_world_y else top.size_y
            along_size = top.size_y if tangent_is_world_y else top.size_x
            normal_size = 2.0 * max(
                normal_size / 2.0,
                threshold_reach - top_v,
                top_v + LANDING_OVERLAP_M / 2.0,
            )
            along_size = max(along_size, ENTRANCE_MIN_WIDTH_M)
            enlarged = top.model_copy(update={
                'size_x': normal_size if tangent_is_world_y else along_size,
                'size_y': along_size if tangent_is_world_y else normal_size,
            })
            transformed = transformed.model_copy(update={
                'landings': [enlarged if landing.index == top.index else landing
                             for landing in transformed.landings],
            })
            top = enlarged
            result['ramp_top'] = (
                top.x - top.size_x / 2.0, top.y - top.size_y / 2.0,
                top.x + top.size_x / 2.0, top.y + top.size_y / 2.0)
        result['ramp'] = transformed

    if result['ramp'] is None:
        # The fallback access stair is still registered to the chosen facade edge.
        side = order[0]
        u0, u1 = sides[side]
        stair_u = (u0 + u1) / 2.0 if u1 > u0 else 0.0
        result['access_point'] = _local_xy(
            origin, tangent, outward, stair_u, centre_v)
        result['access'] = _local_rect_bounds(
            origin, tangent, outward,
            stair_u - ramp_width * 0.9, centre_v - landing_depth / 2.0,
            stair_u + ramp_width * 0.9, centre_v + landing_depth / 2.0)
    return result


def _plan_approach(lattice, datums, *, apron_depth_m: float = APRON_DEPTH_M) -> dict:
    """The approach decided once: the entry landing, and the ramp or the stair that
    stands in for it.

    Three emitters used to derive these separately -- the entry flight, the
    accessible route, and the slab both arrive on -- and the slab never learned where
    the landings were, so it lay under them: two coplanar walking surfaces in one
    place, drawn as a striped fight between them and counted twice. This is the one
    derivation. The slab gives up these footprints and the emitters draw on them.
    """
    if lattice.circulation_intent is not None:
        return _plan_program_volume_approach(
            lattice, datums, apron_depth_m=apron_depth_m)
    levels = lattice.levels
    plan: dict = {'podium_id': None, 'entry': None, 'entry_x': None, 'ramp': None,
                  'ramp_top': None, 'access': None}
    if len(levels) < 2:
        return plan
    podium = levels[1]
    xs = [p.x for p in podium.plate]
    width = datums.value('flight_width_m')
    entry_x = (min(xs) + max(xs)) / 2.0
    south = _plate_south_at(podium.plate, entry_x)
    landing_depth = LANDING_OVERLAP_M * 2.4
    landing_y = south + LANDING_OVERLAP_M / 2.0
    plan.update(
        podium_id=podium.id, entry_x=entry_x,
        entry=(entry_x - width * 1.9 / 2.0, landing_y - landing_depth / 2.0,
               entry_x + width * 1.9 / 2.0, landing_y + landing_depth / 2.0))
    # The same threshold that cuts the facade owns both approach surfaces. Expand
    # the actual landing, whose outer edge also locates the top entrance tread;
    # adding a second patch over the old flight would cover its last risers.
    from .envelope import planned_entrance, ENTRANCE_EDGE_MARGIN_M
    entrance = planned_entrance(lattice, datums, plan)
    if entrance is not None:
        regions = (entrance.aperture, entrance.inside_approach, entrance.outside_approach)
        bounds = [region.bounds for region in regions]
        old = plan['entry']
        margin = ENTRANCE_EDGE_MARGIN_M
        plan['entry'] = (min(old[0], min(item[0] for item in bounds) - margin),
                         min(old[1], min(item[1] for item in bounds) - margin),
                         max(old[2], max(item[2] for item in bounds) + margin),
                         max(old[3], max(item[3] for item in bounds) + margin))

    # The accessible route, on the numbers `_emit_accessible_approach` draws to: the
    # apron beside the entrance stair, the arrival edge where the ramp actually
    # lands, and the switchback that fits there or does not.
    rise = podium.z - levels[0].z
    ramp_width = max(MIN_CLEAR_WIDTH_M, width * 0.62)
    margin = (max(xs) - min(xs)) * 0.06
    clearance = max(2.5, width * 1.6)
    # The ramp runs along the frontage *outside* the plate. Its runs march east from
    # the arrival, so the arrival stands where the south edge has reached its
    # southernmost line -- on an apsidal plate that is just east of the apse, not
    # at the plan's west extreme, where a ramp started at the curve's local edge
    # ran its later legs under the straight part of the building.
    west_bound = entry_x - clearance
    samples = [min(xs) + margin + (west_bound - min(xs) - margin) * k / 40.0
               for k in range(41)]
    edge = {x: _plate_south_at(podium.plate, x) for x in samples}
    southmost = min(edge.values())
    ramp_x_min = next((x for x in samples if edge[x] <= southmost + 0.05),
                      min(xs) + margin)
    arrival_x = ramp_x_min + MIN_LANDING_LENGTH_M * 0.5
    ramp = plan_switchback_ramp(
        rise_m=rise, width_m=ramp_width, x_min=ramp_x_min,
        x_max=west_bound,
        y_start=_plate_south_at(podium.plate, arrival_x) + LANDING_OVERLAP_M / 2.0,
        y_available=apron_depth_m, z_base=levels[0].z)
    plan['ramp'] = ramp
    if ramp is not None:
        top = next((landing for landing in ramp.landings if landing.kind == 'top'),
                   None)
        if top is not None:
            plan['ramp_top'] = (top.x - top.size_x / 2.0, top.y - top.size_y / 2.0,
                                top.x + top.size_x / 2.0, top.y + top.size_y / 2.0)
    else:
        stair_x = entry_x - clearance
        access_y = _plate_south_at(podium.plate, stair_x) + LANDING_OVERLAP_M / 2.0
        plan['access'] = (stair_x - ramp_width * 1.8 / 2.0,
                          access_y - landing_depth / 2.0,
                          stair_x + ramp_width * 1.8 / 2.0,
                          access_y + landing_depth / 2.0)
    return plan


def _approach_keep_out(approach: dict) -> tuple:
    """Every plan rectangle the approach occupies: the landings the slab gives up,
    and the ramp's runs and turn landings. Read by the core search as floor no
    core may stand on."""
    rects = [rect for rect in (approach.get('entry'), approach.get('access'),
                               approach.get('ramp_top')) if rect is not None]
    ramp = approach.get('ramp')
    if ramp is not None:
        half = max(ramp.width_m, getattr(ramp, 'pitch_m', 0.0) or 0.0) / 2.0
        for piece in ramp.runs:
            footprint = LineString([
                (piece.x_start, piece.start_y),
                (piece.x_end, piece.end_y),
            ]).buffer(half, cap_style=2, join_style=2)
            rects.append(tuple(footprint.bounds))
        for landing in ramp.landings:
            rects.append((landing.x - landing.size_x / 2.0, landing.y - landing.size_y / 2.0,
                          landing.x + landing.size_x / 2.0, landing.y + landing.size_y / 2.0))
    return tuple(rects)


def _approach_landing_footprints(approach: dict, level_id: str) -> list:
    """Where the approach landings stand on this level, for the slab to give up."""
    if approach.get('podium_id') != level_id:
        return []
    return [rect for rect in (approach.get('entry'), approach.get('access'),
                              approach.get('ramp_top')) if rect is not None]


def _emit_accessible_approach(b: _Builder, levels, flight_width: float,
                              entry_x: float,
                              apron_depth_m: float = APRON_DEPTH_M) -> None:
    """An ADA-compliant ramp where one fits, and a stair where one does not.

    What was here before was a single box `rise * 6.0` long -- a 1:6 slope, twice the
    maximum §405.2 allows, on every model the corpus produced. It carried five metres of
    rise in one run where §405.6 caps a run at 760 mm, and it had no landings, no
    handrails and no edge protection.

    The choice this function makes is the honest part. A ramp that does not comply is
    worse than no ramp: it occupies the place the accessible route belongs and tells a
    reader the problem is solved. So either §405 is satisfied in full, or a stair goes
    there instead and the model records that the accessible route is unresolved.
    """
    if len(levels) < 2:
        return
    podium = next((level for level in levels
                   if level.id == b.approach.get('podium_id')), levels[1])
    xs = [p.x for p in podium.plate]
    rise = podium.z - levels[0].z
    width = max(MIN_CLEAR_WIDTH_M, flight_width * 0.62)

    # The apron the route may occupy: the frontage *beside* the entrance stair, not
    # across it. The first version spanned the whole elevation and the two ran
    # through each other -- the ramp from x -13.7 to 19.3 and the stair descending
    # at 4.9, both between ground and podium. A switchback that crosses the front
    # door is not a route, it is a collision drawn twice.
    # The plate's southern edge *where the ramp arrives*, not its southernmost point
    # anywhere. On an apsidal plate the two differ: the global minimum sat 480 mm south
    # of the boundary at the ramp's own x, and the top landing came to rest thirty
    # millimetres short of a building it appeared to reach. The apron, that arrival
    # edge and the switchback itself are now decided once in `_plan_approach`, from
    # these same numbers, so the slab has already given up the landing this route
    # arrives on. A caller probing a shallower site re-decides the approach for that
    # depth; the builder's own decision stands at the standard apron.
    if apron_depth_m != APRON_DEPTH_M:
        b.approach = _plan_approach(b.lattice, b.datums, apron_depth_m=apron_depth_m)
    plan = b.approach['ramp']

    if plan is None:
        # No compliant ramp fits. Build the stair and record the failure rather than
        # drawing a ramp that would have to break the standard to be here.
        available_depth = (min(apron_depth_m, b.lattice.circulation_intent.approach_depth_m)
                           if b.lattice.circulation_intent is not None
                           else apron_depth_m)
        b.unresolved_accessible_route = (
            f'No ADA-compliant ramp fits the approach: {rise:.2f} m of rise needs '
            f'{rise * 12:.0f} m of run at 1:12 in {math.ceil(rise / MAX_RUN_RISE_M)} '
            f'runs (405.2, 405.6), and the apron is '
            f'{available_depth:.1f} m deep. A stair is built instead; the accessible '
            f'route is unresolved and needs a lift or a regraded approach.')
        rx0, ry0, rx1, ry1 = b.approach['access']
        stair_x, landing_y = (b.approach.get('access_point')
                              or ((rx0 + rx1) / 2.0, (ry0 + ry1) / 2.0))
        landing_depth = ry1 - ry0
        approach = max(4.0, rise * 2.2)
        # Same derivation as the entry flight: the landing decides where the stair
        # ends, and the slab gave its footprint up before either was drawn.
        if b.lattice.circulation_intent is not None:
            outward = b.approach['entry_outward']
            top = (stair_x, landing_y)
            bottom = (top[0] + outward[0] * approach,
                      top[1] + outward[1] * approach)
            _emit_flight(b, 'R01', v3(*bottom, levels[0].z),
                         v3(*top, podium.z), width * 1.2, levels[0].id)
        else:
            top_y = landing_y - landing_depth / 2.0
            _emit_flight(b, 'R01', v3(stair_x, top_y - approach, levels[0].z),
                         v3(stair_x, top_y, podium.z), width * 1.2, levels[0].id)
        _emit_floor_landing(b, 'CIR-LND-ACCESS', stair_x, landing_y, podium,
                            rx1 - rx0, landing_depth)
        return

    b.accessible_route = plan
    width = plan.width_m
    # The deck is as wide as the leg pitch, not the clear width. At a 1.1 m clear
    # width the legs of a switchback stood 1.525 m apart and a 400 mm slot ran the
    # length of two decks at different heights -- a drop you can put a foot through.
    # The clear width is what 405.5 measures; the deck is what the legs are cast as,
    # and they abut.
    deck_width = max(width, plan.pitch_m)
    deck = b.profile(convention_profile(
        f'RAMP-{deck_width * 1000:.0f}x{RAMP_THICKNESS_M * 1000:.0f}', 'box',
        RAMP_THICKNESS_M, deck_width))

    # The plan's centre-line is the *walking surface* -- it is what §405 measures the
    # slope of, and what the landings are levelled to. A swept member centres its
    # section on its path, so a deck swept along the walking line stands half its own
    # thickness proud of it: 120 mm above every landing it meets, at every joint, on
    # every model. The centre-lines agreed and the solids did not, which is what made
    # the ramp read as loose planks.
    #
    # So the deck hangs below the line it serves, the way a floor hangs below its
    # finished level. The landing already does this; this is the half that did not.
    deck_drop = RAMP_THICKNESS_M / 2.0
    # The deck runs *into* the landing, level, before it starts to slope.
    #
    # Ending it at the landing's near face left a sloping end meeting a level face
    # along a single line -- no overlap, a wedge of daylight between them, and eight
    # runs that read as loose planks however well their centre-lines agreed. A ramp is
    # cast with its landings; the deck reaches the middle of each one and is flat where
    # it does, which is also how a person meets a landing rather than a slope.
    #
    # The plan's runs are untouched: the slope and the rise §405 measures are the
    # sloping length between the landings, not this overlap.
    reach = MIN_TURN_LANDING_M / 2.0
    for run in plan.runs:
        sx, sy = run.x_start, run.start_y
        ex, ey = run.x_end, run.end_y
        run_length = math.hypot(ex - sx, ey - sy)
        ux, uy = (ex - sx) / run_length, (ey - sy) / run_length
        px, py = -uy, ux
        start = v3(sx, sy, run.z_start - deck_drop)
        end = v3(ex, ey, run.z_end - deck_drop)
        path = [v3(sx - ux * reach, sy - uy * reach, run.z_start - deck_drop),
                start, end,
                v3(ex + ux * reach, ey + uy * reach, run.z_end - deck_drop)]
        b.add(f'CIR-RMP-RUN-{run.index:02d}', 'ramp', 'circulation', 'ramps',
              b.member(path, deck),
              'white_soft', category='circulation', program='circulation',
              level_id=levels[0].id, lattice_index={'run': run.index},
              datum_refs=['ground_open_height_m'],
              # The landings this run starts from and arrives at, named from the plan
              # that placed all three. Left to be inferred afterwards, a run was paired
              # with whichever landing was nearest -- which was the right one only when
              # the layout was already correct, and silent when it was not.
              supports=[f'CIR-RMP-LND-{run.index:02d}',
                        f'CIR-RMP-LND-{run.index + 1:02d}'],
              rule_refs=['ADA-405.2', 'ADA-405.5', 'ADA-405.6'],
              reason=f'Ramp run {run.index + 1} of {len(plan.runs)}, rising '
                     f'{run.rise * 1000:.0f} mm at 1:{1 / abs(run.slope):.0f}. '
                     f'405.2 caps the slope at 1:12 and 405.6 caps the run at 760 mm.')
        # 405.9.2 edge protection, a curb along each side of the run
        for side in (-1, 1):
            b.add(f'CIR-RMP-CURB-{run.index:02d}-{"L" if side < 0 else "R"}',
                  'ramp_curb', 'circulation', 'ramps',
                  b.member([v3(sx + px * side * deck_width / 2.0,
                               sy + py * side * deck_width / 2.0,
                               run.z_start + CURB_HEIGHT_M / 2.0),
                            v3(ex + px * side * deck_width / 2.0,
                               ey + py * side * deck_width / 2.0,
                               run.z_end + CURB_HEIGHT_M / 2.0)],
                           b.profile(convention_profile(
                               'RAMPCURB-100x60', 'box', CURB_HEIGHT_M, 0.06))),
                  'white', category='circulation', program='circulation',
                  level_id=levels[0].id, lattice_index={'run': run.index},
                  supports=[f'CIR-RMP-RUN-{run.index:02d}'],
                  datum_refs=['ground_open_height_m', 'flight_width_m'],
                  rule_refs=['ADA-405.9.2'],
                  reason='Edge protection: a 100 mm curb, the option 405.9.2 allows. '
                         'Cast with the run it edges: the curb sits half a deck width '
                         'off the run centre-line, so the two axes never cross and the '
                         'bearing has to be declared rather than found.')
        if plan.handrails_required:
            # 505.10 extensions run 305 mm beyond each end of the run
            ext = HANDRAIL_EXTENSION_M
            _emit_railing(
                b, f'RMP-{run.index:02d}',
                v3(sx - ux * ext, sy - uy * ext, run.z_start),
                v3(ex + ux * ext, ey + uy * ext, run.z_end), width, levels[0].id)

    for landing in plan.landings:
        b.add(f'CIR-RMP-LND-{landing.index:02d}', 'ramp_landing', 'circulation', 'ramps',
              BoxGeometry(center=v3(landing.x, landing.y,
                                    landing.z - RAMP_THICKNESS_M / 2.0),
                          size=v3(landing.size_x, landing.size_y, RAMP_THICKNESS_M)),
              'white', category='circulation', program='circulation',
              # The top landing is floor at the podium level -- the slab gave up its
              # footprint to it -- so it belongs to that level, where a room reaching
              # onto it counts it as support. The rest of the ramp is the ground's.
              level_id=(podium.id if landing.kind == 'top' else levels[0].id),
              lattice_index={'landing': landing.index},
              datum_refs=['ground_open_height_m', 'flight_width_m'],
              supports=([] if landing.kind == 'bottom'
                        else [f'CIR-RMP-RUN-{landing.index - 1:02d}']),
              rule_refs=['ADA-405.7.3'] + (['ADA-405.7.4']
                                           if landing.kind == 'turn' else []),
              reason=f'{landing.kind.title()} landing, '
                     f'{min(landing.size_x, landing.size_y) * 1000:.0f} mm clear. '
                      + ('405.7.4 requires 1525 x 1525 mm where a ramp changes '
                         'direction.' if landing.kind == 'turn' else
                         '405.7.3 requires 1525 mm of clear length.'))

    # Program Volume approaches may place the folded ramp beside the expressive
    # public stair.  Their two top landings used to remain many metres apart along
    # the same facade, while only the public stair received a door.  Join them with
    # one level exterior landing gallery, registered to the same authored boundary
    # tangent.  It stands wholly outside the entrance reveal, overlaps the ramp top
    # and the main entry landing by a full clear width, and bears on the site podium
    # below.  Capacity, drainage and waterproofing remain professional work.
    if b.lattice.circulation_intent is not None:
        from .envelope import (
            ENTRANCE_EDGE_MARGIN_M, ENTRANCE_REVEAL_DEPTH_M, planned_entrance,
        )
        from .portals import APPROACH_DEPTH_M

        entrance = planned_entrance(b.lattice, b.datums, b.approach)
        top = next((landing for landing in plan.landings
                    if landing.kind == 'top'), None)
        if entrance is not None and top is not None:
            tangent = entrance.tangent
            outward = (-entrance.inward[0], -entrance.inward[1])
            dx, dy = top.x - entrance.center[0], top.y - entrance.center[1]
            top_u = dx * tangent[0] + dy * tangent[1]
            # Stop at the ramp-side edge of the main landing. Continuing to u=0
            # would run the level gallery across the upper treads of the expressive
            # public stair, which owns the centre of the entry station.
            rx0, ry0, rx1, ry1 = b.approach['entry']
            entry_corners = ((rx0, ry0), (rx1, ry0), (rx1, ry1), (rx0, ry1))
            entry_us = [
                (x - entrance.center[0]) * tangent[0]
                + (y - entrance.center[1]) * tangent[1]
                for x, y in entry_corners
            ]
            overlap = ENTRANCE_EDGE_MARGIN_M
            if top_u < 0.0:
                entry_u = min(entry_us) + overlap
                u0, u1 = top_u - overlap, entry_u
            else:
                entry_u = max(entry_us) - overlap
                u0, u1 = entry_u, top_u + overlap
            clear = APPROACH_DEPTH_M
            v0 = ENTRANCE_REVEAL_DEPTH_M / 2.0
            v1 = v0 + APPROACH_DEPTH_M
            if b.approach.get('arrival_assembly') is not None:
                u0,v0,u1,v1 = b.approach['arrival_assembly'].link_rect
                clear = v1-v0
            centre = _local_xy(
                entrance.center, tangent, outward,
                (u0 + u1) / 2.0, (v0 + v1) / 2.0)
            link_id = 'CIR-RMP-LND-ENTRY-LINK'
            top_id = f'CIR-RMP-LND-{top.index:02d}'
            b.add(
                link_id, 'ramp_landing', 'circulation', 'ramps',
                BoxGeometry(
                    center=v3(centre[0], centre[1],
                              podium.z - RAMP_THICKNESS_M / 2.0),
                    size=v3(u1 - u0, clear, RAMP_THICKNESS_M),
                    rotation_z=math.atan2(tangent[1], tangent[0])),
                'white', category='circulation', program='public_entry',
                level_id=podium.id,
                lattice_index={'landing': len(plan.landings)},
                datum_refs=['flight_width_m'],
                supports=[top_id, 'CIR-LND-ENTRY'],
                rule_refs=['PV-CIRC-PORTAL-ATTACHMENT'],
                reason=(
                    'Level accessible-entry gallery between the Program Volume ramp '
                    'top and the main facade threshold. Its plan derives from the '
                    'authored entry tangent and the measured portal approach depth; '
                    'structural capacity, drainage and waterproofing are unchecked.'))
            rail_a = _local_xy(entrance.center, tangent, outward, u0, v1)
            rail_b = _local_xy(entrance.center, tangent, outward, u1, v1)
            _emit_railing(
                b, 'RMP-ENTRY-LINK', v3(*rail_a, podium.z),
                v3(*rail_b, podium.z), 0.0, podium.id)
            b.approach['ramp_link_id'] = link_id
            b.approach['ramp_link_bounds'] = _local_rect_bounds(
                entrance.center, tangent, outward, u0, v0, u1, v1)


# How many cores may be added beyond the remote pair: exactly as many as the emitter
# has flight names for, read from the one place those names live. A building needing
# more is one to report on, not to keep adding stairs to.
MAX_EXTRA_CORES = len(EXTRA_FLIGHT_PAIRS)
# How many preferred primary sites are tried for one that leaves every storey two
# ways out before the best coverage found is kept.
MAX_PRIMARY_TRIALS = 8


def _given_core_anchors(lattice, width: float, run: float, keep_out: tuple,
                        datums) -> dict:
    """Anchors read off the cores a program massing placed (decision 0022).

    Nothing is searched for. Each core is checked against the plates it serves --
    its whole footprint, landings included, inside every one of them and clear of
    carved floor and of the other cores -- and a core that fails is an error naming
    it, not a silent move: the massing is the designer's decision and the compiler
    does not amend it. Stairs are taken in the order given: the first is the
    primary, the second its egress partner, the rest the extra cores the emitter
    names flights for. The first lift is the lift; with none given, the compiler
    places one in a cell beside the primary stair as it does on a music run.
    """
    levels = lattice.levels
    by_id = {level.id: level for level in levels}

    def run_for(core) -> list:
        unknown = [name for name in core.serves if name not in by_id]
        if unknown:
            raise ValueError(f'core {core.id} serves unknown levels {unknown}')
        wanted = [level for level in levels
                  if not core.serves or level.id in core.serves]
        if not wanted or wanted[0].index != 0:
            raise ValueError(
                f'core {core.id} must serve the ground level {levels[0].id}: a stair '
                f'is an exit only if it runs to grade')
        contiguous = [wanted[0]]
        for level in wanted[1:]:
            if level.index != contiguous[-1].index + 1:
                break
            contiguous.append(level)
        return contiguous

    def check(core, footprint, served) -> None:
        for level in served:
            if not level.plate:
                continue
            region = plan_polygon(level.plate).difference(
                unary_union([plan_polygon(hole) for hole in level.voids]))
            # Match the core-site search's float identity tolerance. A serialized
            # 4.73 boundary and 6.25 - 1.52 differ by 9e-16 m; exact GEOS coverage
            # must not reject the same authored face after arithmetic.
            if not covers_registered_footprint(region,plan_box(*footprint)):
                raise ValueError(
                    f'core {core.id} does not stand inside the {level.id} plate it '
                    f'serves (footprint {tuple(round(v, 2) for v in footprint)})')
        if any(_box_overlaps(footprint, rect, tolerance=1e-7) for rect in keep_out):
            raise ValueError(f'core {core.id} stands in floor the archetype carved')

    stairs = [core for core in lattice.given_cores if core.kind == 'stair']
    lifts = [core for core in lattice.given_cores if core.kind == 'lift']
    if not stairs:
        raise ValueError('a program massing must place at least one stair core')
    if len(stairs) > 2 + MAX_EXTRA_CORES:
        raise ValueError(f'at most {2 + MAX_EXTRA_CORES} stair cores are emitted; '
                         f'{len(stairs)} were given')
    placed: list[tuple] = []
    runs: dict[str, list] = {}
    for core in stairs:
        runs[core.id] = run_for(core)
        footprint = _core_box(core.x, core.y, width, run, core.run_axis)
        check(core, footprint, runs[core.id])
        for other, other_box in placed:
            if _box_overlaps(footprint, other_box, tolerance=1e-7):
                raise ValueError(f'cores {core.id} and {other.id} overlap')
        placed.append((core, footprint))

    primary, second = stairs[0], (stairs[1] if len(stairs) > 1 else None)
    anchors = {'width': width, 'run': run,
               'primary': (primary.x, primary.y), 'served': runs[primary.id],
               'second': (second.x, second.y) if second else None,
               'second_served': runs[second.id] if second else [],
               'extras': [((core.x, core.y), runs[core.id]) for core in stairs[2:]],
               'primary_run_axis': primary.run_axis,
               'second_run_axis': second.run_axis if second else 'y',
               'extra_run_axes': [core.run_axis for core in stairs[2:]],
               'lattice': lattice}
    # The grid is drawn to the given cores; a given grid keeps every line it had,
    # and no module line is added through a given lift shaft.
    avoid = []
    if lifts:
        half = LIFT_SHAFT_M / 2.0
        avoid.append((lifts[0].x - half, lifts[0].y - half,
                      lifts[0].x + half, lifts[0].y + half))
    _frame_the_volumes(lattice, anchors, datums, avoid=avoid)
    if lifts:
        lift = lifts[0]
        served = run_for(lift)
        half = LIFT_SHAFT_M / 2.0 + CORE_CLEARANCE_M
        footprint = (lift.x - half, lift.y - half, lift.x + half, lift.y + half)
        check(lift, footprint, served)
        for other, other_box in placed:
            if _box_overlaps(footprint, other_box, tolerance=1e-7):
                raise ValueError(f'lift {lift.id} stands in stair core {other.id}')
        anchors['lift'] = (lift.x, lift.y, served)
    else:
        anchors['lift'] = _place_lift(lattice, anchors, keep_out)
    return anchors


def core_anchors(lattice, datums) -> dict:
    """Where the vertical cores go, decided once and read by everyone who needs it.

    The program allocation needs this before it bands a floor, and the emitter needs
    the same answer when it draws the stairs. Two computations of "where the core is"
    is the shape of every collision this pipeline has produced; one computation, read
    twice, is the fix.

    The archetype's carved floor is read off `lattice.carved` rather than taken as a
    parameter, for the same reason: the carve runs first because the house is the
    building's reason and a stair serves it, and every anchor search below refuses a
    site whose core box stands in carved floor. A parameter here was tried and it
    reintroduced the two-answers bug within a day -- a test recomputing the
    reservation without the parameter disagreed with the model it was checking.
    """
    width = datums.value('flight_width_m')
    run = flight_run(width)
    keep_out = tuple(rect for rects in lattice.carved.values() for rect in rects)

    # A program massing that placed its cores is read, not second-guessed
    # (decision 0022): the search below exists for the music path, where nobody
    # has yet said where the stair goes.
    if lattice.given_cores:
        return _given_core_anchors(lattice, width, run, keep_out, datums)

    # The approach is decided from the plate alone and before the cores: the entry
    # landing, the ramp with its runs and landings, the access stair. A core standing
    # in it put a half landing over a ramp run on an apsidal library, so its
    # footprints are floor no core may take.
    keep_out += _approach_keep_out(_plan_approach(lattice, datums))

    carrier_regions = (_program_carrier_regions(lattice)
                       if lattice.circulation_intent is not None else None)
    primary, served = None, list(lattice.levels)
    while len(served) >= 2:
        primary = _stair_anchor(
            lattice, width, run, served, keep_out=keep_out,
            allowed_by_level=carrier_regions)
        if primary is not None:
            break
        served = served[:-1]
    if primary is None:
        if lattice.circulation_intent is not None:
            carriers = ', '.join(lattice.circulation_intent.carrier_volume_ids)
            raise ValueError(
                'PV-CIRC-SPINE-NO-FIT: the complete stair footprint cannot fit '
                f'inside the declared circulation carrier volumes ({carriers}); '
                'the stair was not narrowed or moved into undeclared programme')
        served = []

    def run_diagonal(levels_run) -> float:
        # IBC 1007.1.1 measures the diagonal of the area served -- the plates of
        # the run under trial, not of every level the primary reaches. Measuring
        # the whole building demanded podium-scale separation from a bar-sized floor.
        best = 0.0
        for level in levels_run:
            if not level.plate:
                continue
            xs = [point.x for point in level.plate]
            ys = [point.y for point in level.plate]
            best = max(best, math.hypot(max(xs) - min(xs), max(ys) - min(ys)))
        return best

    def pick_second(anchor_point):
        # The second core is placed by maximising distance from the first: remoteness
        # matters most on the largest floors, and those are the ones every candidate
        # run serves. The storeys a remote candidate stops short of are not traded
        # away for that distance -- they are covered by the extra cores below.
        # Preferring separation *instead* of coverage is what left a theatre bar with
        # a hundred and nineteen people on L04 and one way out, while the second
        # stair stood in the far corner of a podium it served three storeys of.
        chosen, chosen_served, best = None, [], -1.0
        trial = list(served)
        while len(trial) >= 2:
            candidate = _stair_anchor(lattice, width, run, trial,
                                      away_from=anchor_point, keep_out=keep_out + (
                                          _core_box(*anchor_point, width, run),),
                                      required=run_diagonal(trial) / 3.0,
                                      allowed_by_level=carrier_regions)
            if candidate is not None:
                gap = math.hypot(candidate[0] - anchor_point[0],
                                 candidate[1] - anchor_point[1])
                if gap > best:
                    chosen, chosen_served, best = candidate, list(trial), gap
                if gap >= run_diagonal(trial) / 3.0:
                    break
            trial = trial[:-1]
        if best < width * 1.5:
            return None, []
        return chosen, chosen_served

    def pick_extras(anchor_point, second_run, second_point):
        # At most `MAX_EXTRA_CORES`, which is what the emitter names flights for. A
        # building needing a fourth core is one this compiler should report on rather
        # than keep adding stairs to.
        # Extra cores for the storeys the second stops short of. A stair is an exit
        # only if it runs to grade, so an extra core's run still grows from the
        # ground; it exists for the storeys above the second's top. On a bar over a
        # podium this is the bar's own second stair: the podium keeps its remote
        # pair, the bar gets a second way down. Occupied storeys only -- the roof
        # needs no exit, and requiring the extra to stand inside the roof plate as
        # well shrank its feasible region to a sliver five metres from the primary.
        chosen: list[tuple[tuple[float, float], list]] = []
        for _ in range(MAX_EXTRA_CORES):
            covered = {level.id for level in second_run}
            for _point, levels_run in chosen:
                covered.update(level.id for level in levels_run)
            missing = [level for level in served
                       if level.kind == 'occupied' and level.id not in covered]
            if not missing:
                break
            top_missing = missing[-1].id
            placed, best_gap = None, -1.0
            trial = list(served)
            occupied = [_core_box(*anchor_point, width, run)]
            if second_point is not None:
                occupied.append(_core_box(*second_point, width, run))
            occupied += [_core_box(*point, width, run)
                         for point, _levels in chosen]
            while len(trial) >= 2:
                if not any(level.id == top_missing for level in trial):
                    break  # truncated below the storey this core exists for
                candidate = _stair_anchor(lattice, width, run, trial,
                                          away_from=anchor_point,
                                          keep_out=keep_out + tuple(occupied),
                                          required=run_diagonal(trial) / 3.0,
                                          allowed_by_level=carrier_regions)
                if candidate is not None:
                    gap = math.hypot(candidate[0] - anchor_point[0],
                                     candidate[1] - anchor_point[1])
                    if gap > best_gap:
                        placed, best_gap = (candidate, list(trial)), gap
                    if gap >= run_diagonal(trial) / 3.0:
                        break
                trial = trial[:-1]
            if placed is None or best_gap < width * 1.5:
                break  # reported by the life-safety graph, not hidden here
            chosen.append(placed)
        return chosen

    def short_storeys(second_run, extras_chosen) -> int:
        # Occupied storeys of the primary's run with fewer than two cores.
        cores = {level.id: 1 for level in served if level.kind == 'occupied'}
        for levels_run in [second_run] + [levels for _point, levels in extras_chosen]:
            for level in levels_run:
                if level.id in cores:
                    cores[level.id] += 1
        return sum(1 for count in cores.values() if count < 2)

    # The primary stands where a service stair likes to be -- but among the sites
    # that leave every storey two ways out. Placed on preference alone, the sliver
    # rule moved it from the end of a theatre bar to the middle, and the bar's own
    # second stair then had no floor left to stand on: the extras cover storeys the
    # second stops short of, and they can only cover what the primary leaves room
    # for. So the preferred sites are tried in order until one covers, or the best
    # coverage is kept; coverage is code, the preference is not.
    second, second_served, extras = None, [], []
    if primary is not None:
        sites = _stair_sites(
            lattice, width, run, served, allowed_by_level=carrier_regions)
        usable = [site for site in sites
                  if not any(_box_overlaps(_core_box(*site, width, run), rect)
                             for rect in keep_out)]
        ranked = _primary_sites(lattice, usable, {
            site: _sliver_faces(lattice, _core_box(*site, width, run), keep_out)
            for site in usable})
        best = None
        for candidate in ranked[:MAX_PRIMARY_TRIALS]:
            trial_second, trial_served = pick_second(candidate)
            trial_extras = pick_extras(candidate, trial_served, trial_second)
            short = short_storeys(trial_served, trial_extras)
            if best is None or short < best[0]:
                best = (short, candidate, trial_second, trial_served, trial_extras)
            if short == 0:
                break
        _short, primary, second, second_served, extras = best

    # Two exits are a pair, not one stair plus an afterthought. The primary is placed
    # where a service stair likes to be and its partner is then found as far away as
    # the leftover region allows -- and on a slim bar with curved ends the leftover is
    # never far enough: greedy placement measured 7.3 m against a 9.9 m third-diagonal
    # requirement. When the pair that covers the top storeys fails its own rule, both
    # ends are re-placed together as the two farthest feasible points -- the diameter
    # of the region -- and the remote second is then re-chosen against the moved
    # primary. Guarded, so a massing whose greedy pair already clears is untouched.
    if primary is not None and extras:
        top_point, top_run = extras[-1]
        occupied_above = [level for level in top_run
                          if level.kind == 'occupied'
                          and level.id not in {lv.id for lv in second_served}]
        need = max((run_diagonal([level]) / 3.0 for level in occupied_above),
                   default=0.0)
        gap = math.hypot(top_point[0] - primary[0], top_point[1] - primary[1])
        if gap < need:
            def clear_of_carve(sites):
                return [(x, y) for x, y in sites
                        if not any(_box_overlaps(_core_box(x, y, width, run), rect)
                                   for rect in keep_out)]

            sites_primary = clear_of_carve(_stair_sites(
                lattice, width, run, served, allowed_by_level=carrier_regions))
            sites_extra = clear_of_carve(_stair_sites(
                lattice, width, run, top_run,
                allowed_by_level=carrier_regions))

            # The pair is placed for distance, never onto a column node: a well
            # with grid lines through it both ways cannot be framed and the stair
            # in it cannot be built. Node-free sites only, while there are any --
            # this search took the farthest pair of all sites and moved the
            # primary stair of a theatre onto its corner column.
            def clean(sites):
                # Sites the grid frames without a sliver bay, when there are any.
                kept = [site for site in sites
                        if _sliver_faces(lattice, _core_box(*site, width, run), keep_out) == 0]
                return kept or sites

            sites_primary = clean(sites_primary)
            sites_extra = clean(sites_extra)
            best_pair, best_span = None, gap
            for px, py in sites_primary:
                for qx, qy in sites_extra:
                    if _box_overlaps(_core_box(px, py, width, run),
                                     _core_box(qx, qy, width, run)):
                        continue
                    span = math.hypot(px - qx, py - qy)
                    if span > best_span:
                        best_pair, best_span = ((px, py), (qx, qy)), span
            if best_pair is not None:
                primary = best_pair[0]
                second, second_served = pick_second(primary)
                extras = pick_extras(primary, second_served, second)
                # The moved pair is the point; if the re-picked extra strayed, pin
                # the partner this adjustment chose for the run it was chosen for.
                # Replacing at the cap rather than appending: `pick_extras` yields at
                # most two, the emitter names exactly two, and a third would have been
                # an IndexError in a branch that only fires on a massing whose greedy
                # pair fails -- the kind that ships.
                pinned_box = _core_box(*best_pair[1], width, run)
                occupied_boxes = ([_core_box(*second, width, run)]
                                  if second is not None else [])
                occupied_boxes += [_core_box(*point, width, run)
                                   for point, _run in extras]
                if ((not extras or extras[-1][1][-1].id != top_run[-1].id)
                        and not any(_box_overlaps(pinned_box, box) for box in occupied_boxes)):
                    pinned = (best_pair[1], top_run)
                    if len(extras) >= MAX_EXTRA_CORES:
                        extras[-1] = pinned
                    else:
                        extras.append(pinned)

    anchors = {'width': width, 'run': run, 'primary': primary, 'served': served,
               'second': second, 'second_served': second_served, 'extras': extras,
               # The layout reads the grid off this to settle which way each stair
               # faces; it is the one place the facing is decided.
               'lattice': lattice}
    # The grid is drawn to the cores before the lift looks for a bay beside them.
    _frame_the_volumes(lattice, anchors, datums)
    anchors['lift'] = _place_lift(lattice, anchors, keep_out)
    return anchors


# How far the brief may resize a massing family's plate, as a linear factor. Inside
# these bounds a tower is still a tower and a pavilion is still a pavilion; at them the
# family's identity holds and whatever brief is left over stays reported as unplaced.
PLAN_FIT_MIN = 0.7
PLAN_FIT_MAX = 1.5


def _frame_closes(lattice) -> bool:
    """Whether the top level has a bay a girder can actually span.

    A column exists at a grid node only where that node lies inside *every* plate from
    the ground up, and a primary beam needs a column at both of its ends. On a bar that
    tapers hard the surviving stack can thin to a single line by the top storey -- and
    then the roof level gets no beams, the roof slab is declared with no support, and
    the truss that bears on that slab stands on nothing. The dependency graph reports
    all of it, correctly; the point of testing it here is that the plate size is still
    a free variable at this stage, so a scale whose frame does not close can simply not
    be chosen.
    """
    levels = lattice.levels
    if len(levels) < 2:
        return False
    plates = [level.plate for level in levels if level.plate]
    if not plates:
        return False

    def stands(xi: int, yj: int) -> bool:
        x, y = lattice.x_lines[xi], lattice.y_lines[yj]
        # The same boundary-inclusive test the column stack uses, so the fit and
        # the frame agree about which nodes carry a column.
        return all(_on_plate(plate, x, y) for plate in plates)

    for yj in range(len(lattice.y_lines)):
        for xi in range(len(lattice.x_lines) - 1):
            if stands(xi, yj) and stands(xi + 1, yj):
                return True
    for xi in range(len(lattice.x_lines)):
        for yj in range(len(lattice.y_lines) - 1):
            if stands(xi, yj) and stands(xi, yj + 1):
                return True
    return False


def _apply_floor_removals(level, rectangles) -> str | None:
    """Subtract a carve and serialize the exact connected floor that remains.

    A removal that reaches the outside edge is a notch, not an interior-ring
    rectangle. Appending that rectangle to ``level.voids`` creates a self-intersecting
    polygon at the shared edge, so the planar boolean owns the resulting rings here.
    """
    source = Polygon(
        [(point.x, point.y) for point in level.plate],
        holes=[[(point.x, point.y) for point in ring] for ring in level.voids])
    if source.is_empty or not source.is_valid or source.area <= 0.0:
        return f'{level.id} has invalid floor geometry before the archetype carve'
    cuts = [plan_box(*rect) for rect in rectangles]
    if any(cut.is_empty or cut.area <= 0.0 for cut in cuts):
        return f'{level.id} received an empty archetype floor-removal rectangle'
    remaining = source.difference(unary_union(cuts))
    if remaining.is_empty:
        return f'the archetype removes the whole floor of {level.id}'
    if remaining.geom_type != 'Polygon' or not remaining.is_valid:
        return (f'the archetype splits {level.id} into {remaining.geom_type}; '
                'one connected plate is required')
    remaining = orient(remaining, sign=1.0)
    level.plate[:] = [v2(round(float(x), 6), round(float(y), 6))
                      for x, y in list(remaining.exterior.coords)[:-1]]
    level.voids[:] = [
        [v2(round(float(x), 6), round(float(y), 6))
         for x, y in list(ring.coords)[:-1]]
        for ring in remaining.interiors]
    return None


def _carve_and_allocate(grid, datums, typology: str, brief, zoned=()):
    """The archetype first, the cores around it, the allocator around both.

    The carve runs before the cores because the house is what the building is for
    and a stair serves it: `core_anchors` refuses a site inside carved floor. What
    comes back is either the carve applied -- its plate removals entered on the
    lattice as voids, its rooms preplaced, its floor reserved -- or the carver's
    refusal, whose rooms are reported unplaced with the reason, so the plate fit
    grows toward a plate the archetype accepts instead of housing an auditorium as
    a flat rectangle.
    """
    carve = carve_for(typology, grid, datums, brief)
    if isinstance(carve, Carve):
        # Reserve a registered transfer zone before rooms and loads claim its floor.
        # This spatial allowance does not select a structural system or prove capacity.
        from .transfer_structure import reserve_transfer_zone
        reserve_transfer_zone(grid, carve, datums.value('slab_thickness_m'))
        original_plates = {level.index: list(level.plate) for level in grid.levels}
        original_voids = {level.index: [list(ring) for ring in level.voids]
                          for level in grid.levels}

        def restore_floor_geometry() -> None:
            for level in grid.levels:
                level.plate[:] = original_plates[level.index]
                level.voids[:] = original_voids[level.index]

        def refuse_applied_carve(reason: str) -> CarveRefusal:
            return CarveRefusal(
                archetype_id=carve.archetype_id,
                precluded=[UnplacedSpace(
                    space_id=zone.space_id, label=zone.label,
                    area_required_m2=zone.area_required_m2,
                    reason=f'the {carve.archetype_id} archetype could not carve this '
                           f'plate: {reason}') for zone in carve.zones],
                reason=reason)

        removal_error = None
        for level_index, rects in carve.removed.items():
            removal_error = _apply_floor_removals(grid.level(level_index), rects)
            if removal_error is not None:
                break
        if removal_error is not None:
            restore_floor_geometry()
            grid.carved = {}
            carve = refuse_applied_carve(removal_error)
        else:
            # Written to the lattice, not passed around: every later reader of the
            # cores -- the emitter, a test recomputing the reservation -- must see the
            # same carved floor this allocation saw.
            grid.carved = {index: list(rects)
                           for index, rects in carve.reservations.items()}
            # A storey no stair can reach once the house has its floor is a storey the
            # carve stranded. The carver's own gutting check catches the levels the
            # claim erases; this catches the ones it orphans -- on a bar over a podium
            # the bar's top storeys keep their floor and lose every feasible core site,
            # which the carver cannot see because the core search lives here. Measured
            # by running that search, not predicted.
            anchors = core_anchors(grid, datums)
            runs = [anchors['served'], anchors['second_served']]
            runs += [levels for _point, levels in anchors['extras']]
            covered = {level.id for run in runs for level in run}
            stranded = [level.id for level in grid.occupied if level.id not in covered]
            if stranded:
                grid.carved = {}
                restore_floor_geometry()
                carve = refuse_applied_carve(
                    f'once the house takes its floor no stair can serve '
                    f'{", ".join(stranded)}: this massing stands those storeys '
                    'where only a later transfer/vertical-circulation phase can make '
                    'them reachable')
    cores = core_reservations(grid, datums)
    from .program import PublicCirculationPlanner
    from .partitions import PARTITION_TYPES
    from .room_fixtures import theatre_floor_layout
    from .envelope import planned_entrance
    from .navigation import polygons
    from .plan_regions import usable_region
    radius = _core_route_radius()
    anchors = core_anchors(grid, datums)
    terminals, obstacles, aprons = {}, {}, {}
    approach = _plan_approach(grid, datums)
    entrance = planned_entrance(grid,datums,approach)
    # The approach's landings on the storey the entry stands on -- the entry
    # landing, the ramp's top landing, the access stair's -- are floor a person
    # walks onto, not floor a room may take: a riser closet laid out over the
    # ramp's top landing put its partition across the landing (decision 0023).
    # A wall's thickness beyond the landing: the room's partition stands outside
    # the room rectangle, and one flush with the landing crossed it by a centimetre.
    wall = max(p.thickness_mm for p in PARTITION_TYPES) / 1000.0
    walked = {level.index: [(x0 - wall, y0 - wall, x1 + wall, y1 + wall)
                            for x0, y0, x1, y1 in _approach_landing_footprints(approach, level.id)]
              for level in grid.occupied}
    walked = {index: rects for index, rects in walked.items() if rects}
    placed = tuple(carve.zones) if isinstance(carve, Carve) else ()
    core_boxes = _core_rects(anchors)
    width, run = anchors['width'], anchors['run']
    protected = {}
    level_index_by_id = {level.id: level.index for level in grid.occupied}
    for region in getattr(grid, 'program_volume_regions', ()):
        if region.role not in ('program', 'archetype'):
            continue
        level_index = level_index_by_id.get(region.level_id)
        if level_index is None:
            raise ValueError(
                f'{region.id} protects program on unknown level {region.level_id}')
        for space_id in region.space_ids:
            protected.setdefault(level_index, {})[space_id] = plan_box(
                *region.resolve_bounds(grid))
    for level in grid.occupied:
        # The cores are walled volumes (decision 0022): the corridors go around
        # them and reach each stair at the point outside its exit door, not at
        # a landing edge the wall now stands on.
        obstacles[level.index] = ([plan_box(*rect) for rect in _opening_rects(anchors,level.id)]
                                  + [plan_box(*rect) for rect in core_boxes])
        entries = terminals[level.index] = []
        for index, ((ax, ay), levels, _tags, _label, facing) in enumerate(_core_layout(anchors)):
            if level.id not in {lv.id for lv in levels}:
                continue
            terminal = _core_terminal(anchors, (ax, ay), facing, radius)
            entries.append((f'STAIR-{index+1}', [terminal]))
        if entrance is not None and entrance.level_id==level.id:
            aprons[level.index]=polygons(entrance.inside_approach.union(entrance.aperture).intersection(
                usable_region(level)))
            entries.append(('PUBLIC-ENTRY',[tuple(entrance.inside_approach.centroid.coords[0])]))
        for zone in placed:
            if zone.level_id != level.id:
                continue
            owner = protected.get(level.index, {}).get(zone.space_id)
            front_x = None
            if isinstance(carve,TheatreCarve) and zone.space_type=='auditorium':
                front_x = theatre_floor_layout(carve, level, approach).front.centroid.x
            entries.append((zone.space_id, _preplaced_terminal_points(
                zone, radius, owner=owner, front_x=front_x)))
    public = PublicCirculationPlanner(
        grid, obstacles=obstacles, terminals=terminals,
        preplaced=placed, aprons=aprons, protected=protected)
    if carve is None:
        return allocate_program(grid, datums, brief, reserved=cores,public_circulation=public,
                                walked=walked, zoned=zoned), None
    if isinstance(carve, CarveRefusal):
        return allocate_program(grid, datums, brief, reserved=cores,
                                precluded=tuple(carve.precluded),public_circulation=public,
                                walked=walked, zoned=zoned), carve
    allocation = allocate_program(
        grid, datums, brief, reserved=cores,
        carved={index: tuple(rects) for index, rects in carve.reservations.items()},
        preplaced=tuple(carve.zones),public_circulation=public, zoned=zoned,
        walked=walked)
    return allocation, carve


def _preplaced_terminal_points(zone, radius, *, owner=None, front_x=None):
    """Read terminal faces from the same full owner the planner protects.

    Carve rectangles have millimetre rounding; an indexed Program Volume keeps
    finer bounds. Offsetting from the rounded carve can leave a route centre
    inside its owner's buffered obstacle, even when the corridor itself fits.
    """
    from .room_access import owner_terminal_points
    bounds = owner.bounds if owner is not None else (
        zone.x0, zone.y0, zone.x1, zone.y1)
    return owner_terminal_points(bounds, radius, front_x=front_x)


def _fit_plan_to_brief(datums, massing, lattice, typology: str, *, cutaway: bool):
    """Size the plate from the brief; leave every directional decision to the score.

    The score gives direction -- which silhouette, how many storeys, how coarse a bay,
    what proportion -- and the brief says how much building those directions have to
    hold. Before this the two never met: every family carried a constant footprint, the
    score stretched it eighteen per cent either way, and whether 3,066 m2 of library
    landed in 1,400 m2 of plate or 6,000 m2 was luck. Three of the four briefs could
    not be housed by the building their own score produced.

    The fit scales the family's plan uniformly, so the proportion the family declares
    and the bay grain the score chose both survive; more area means more bays, not
    bigger ones. It steers on the thing that matters -- a trial allocation of the
    actual brief -- rather than on gross area, because floor is lost to quantisation
    the area ratio cannot see: rooms truncate at band edges, and a small change of
    plate can drop a whole structural row. For the same reason the walk keeps the best
    state it has visited and returns that, not wherever the last step landed: shrinking
    a plate that measured roomy can collapse past the target, and the first version of
    this walk did exactly that, ending a roomy score at 0.62 fulfilment on its way to a
    building it had already been inside.
    """
    base_x, base_y = massing.plan_x_m, massing.plan_y_m

    def measure(scale: float):
        fitted = massing if scale == 1.0 else massing.model_copy(update={
            'plan_x_m': round(base_x * scale, 3),
            'plan_y_m': round(base_y * scale, 3)})
        grid = build_lattice(datums, fitted, cutaway=cutaway)
        brief = brief_for(typology, storeys=len(grid.occupied))
        trial, carve = _carve_and_allocate(grid, datums, typology, brief)
        return fitted, grid, trial, carve

    # Fulfilment the fit is content with. Not 1.0: quantisation keeps a few rooms a
    # band short of their ask on any honest plate, and chasing the last two per cent
    # inflates the building for nobody.
    ENOUGH = 0.97

    scale = 1.0
    tried: set[float] = set()
    best = None  # (key, scale, fitted, grid, trial, carve)
    for _ in range(5):
        scale = round(min(PLAN_FIT_MAX, max(PLAN_FIT_MIN, scale)), 3)
        if scale in tried:
            break
        tried.add(scale)
        fitted, grid, trial, carve = measure(scale)
        # Read per space, not averaged. A theatre whose auditorium came out a fifth
        # short still measured 0.979 overall, so the fit stopped growing the plate
        # while the one room the building exists for was 134 m2 down. `fits` is now
        # every space placed *and* delivered to its own tolerance.
        housed = trial.fits and trial.fulfilment >= ENOUGH
        # A plate that houses the brief on a frame that does not reach its own roof is
        # not a state to prefer over one that does, however well the rooms fit.
        closes = _frame_closes(grid)
        # Three tiers, best first: housed on a frame that closes, then housed on one
        # that does not, then neither. Inside the first tier the smaller building wins,
        # because a building should be as small as its brief allows. Inside the second
        # the *larger* one does -- a frame closes by having more grid inside every
        # plate, so if nothing in the walk ever closes, the widest plate tried is the
        # nearest to standing up. Inside the third, the fuller one.
        key = ((0, scale) if housed and closes
               else (1, -scale) if housed
               else (2, -trial.fulfilment))
        if best is None or key < best[0]:
            best = (key, scale, fitted, grid, trial, carve)
        if housed and closes and trial.delivered_area_m2 >= trial.required_area_m2 * 0.99:
            # Delivered in full -- probe one size down; a building should be as small
            # as its brief allows, and if the probe loses rooms `best` keeps this one.
            scale *= 0.92
            continue
        if housed and closes:
            break
        if housed:
            # Housed but the frame does not close: nudge the plate rather than stop.
            scale *= 1.06
            continue
        # Grow by what the *worst* space is missing when one is short, by the overall
        # ratio otherwise. The average is nearly one when a single large room is down,
        # so steering on it took steps too small to ever close the gap.
        worst = min((zone.area_delivered_m2 / (zone.area_required_m2 * zone.area_tolerance)
                     for zone in trial.short), default=1.0)
        deficit = min(worst, trial.delivered_area_m2 / max(1.0, trial.required_area_m2))
        step = math.sqrt(1.0 / max(0.35, deficit))
        scale *= min(1.3, max(0.8, step))

    # The winning trial travels with its lattice: re-allocating here would carve the
    # same voids into the same levels a second time.
    _, scale, fitted, grid, trial, carve = best

    note = (f'plate sized by the brief: {trial.required_area_m2:.0f} m2 asked for, '
            f'{trial.delivered_area_m2:.0f} m2 delivered at plan scale x{scale:.2f}')
    if scale in (PLAN_FIT_MIN, PLAN_FIT_MAX) and trial.fulfilment < ENOUGH:
        note += (' -- held at the bound where the family stops being itself; the rest '
                 'of the brief is reported unplaced rather than housed in a building '
                 'that no longer answers the music')
    return fitted, grid, trial, carve, note


# A passenger lift shaft with its structure. Not a function of the stair beside it.
LIFT_SHAFT_M = 2.6
LIFT_GAP_M = 0.30  # architectural clearance between the stair and shaft wall
LIFT_WALL_M = 0.20  # schematic wall thickness, not a calculated assembly
CORE_CLEARANCE_M = 0.20
# The shaft beyond its landings. A car cannot stop at the top floor without headroom
# above it for the car, its counterweight run-by and, on a machine-room-less drive,
# the machine itself; nor at the bottom without a pit for the buffers. The figures
# are practice for a mid-speed MRL passenger lift (EN 81-20 sets the refuge spaces
# they derive from), not a manufacturer's dimension, and the reason says so.
LIFT_OVERRUN_M = 3.8
LIFT_PIT_M = 1.4
# Landing door: 900 mm clear is the accessible passenger-lift norm (EN 81-70 minimum
# 800; ADA 407.3.1 minimum 915 for larger cars), 2100 mm high.
LIFT_DOOR_W_M = 0.9
LIFT_DOOR_H_M = 2.1


def _core_layout(anchors):
    """One set of positions and directions for reservations, voids and stairs.

    Prefer remote doors where their complete approach fits on supported floor.
    A plate-boundary distance alone cannot see a lift occupying that approach.
    This chooses geometry only; door operation and egress remain reviewable.
    """
    primary = anchors['primary']
    if primary is None:
        return []
    lattice = anchors.get('lattice')
    width, run = anchors['width'], anchors['run']

    plan = getattr(lattice, 'plan', None) if lattice is not None else None

    def approach_fits(point, levels, facing):
        from .plan_regions import usable_region
        radius = _core_route_radius()
        # The complete doorway-width strip through the unchanged route terminal
        # and its planning body, not an arbitrary point shifted until it routes.
        half_width = max(CORE_DOOR_W_M / 2.0, radius)
        face = -facing * (run / 2.0 + 1.7 + CORE_CLEARANCE_M)
        outer = face - facing * (2.0 * radius + CORE_TERMINAL_GAP_M)
        apron = plan_box(*_core_bounds(point,
            (-half_width, min(face, outer), half_width, max(face, outer)),
            _core_run_axis(anchors, point)))
        cuts = list(_core_rects(anchors))
        lift = anchors.get('lift')
        if lift is not None:
            cx, cy, _served = lift
            half = LIFT_SHAFT_M / 2.0
            cuts.append((cx-half, cy-half, cx+half, cy+half))
        floors = [level for level in levels if level.kind == 'occupied']
        return bool(floors) and all(covers_registered_footprint(
            usable_region(level, cuts + list(lattice.carved.get(level.index, []))), apron)
            for level in floors)

    def room_beyond(point, levels, facing: float) -> float:
        # The strip between the landing face and the plate edge, on every storey
        # served; the narrowest is what a door on that face opens onto.
        axis = _core_run_axis(anchors, point)
        box = _core_box(point[0], point[1], width, run, axis)
        room = math.inf
        for level in levels:
            if not level.plate:
                continue
            if axis == 'x':
                # Transpose the plate for the same section-at-station measurement.
                plate = [v2(p.y, p.x) for p in level.plate]
                if facing > 0:
                    room = min(room, box[0] - _plate_south_at(plate, point[1]))
                else:
                    room = min(room, _plate_north_at(plate, point[1]) - box[2])
            elif facing > 0:
                room = min(room, box[1] - _plate_south_at(level.plate, point[0]))
            else:
                room = min(room, _plate_north_at(level.plate, point[0]) - box[3])
        return room

    def settle(point, preferred: float, levels) -> float:
        # The doors of a pair open away from each other, because the separation
        # the code asks for is measured door to door -- a pair facing each other
        # across a slim theatre bar measured 3 m against 10. That holds where the
        # strip beyond the landing face has room for the door and a person on
        # every storey the stair serves; where it does not, the door faces the
        # plate's interior, where the corridor is: a door on a strip narrower than
        # that sent every corridor around the core to reach it. The grid is drawn
        # to the core (decision 0022), so no facing puts a girder through the well.
        if plan is None:
            return preferred
        available = [facing for facing in (preferred, -preferred)
                     if approach_fits(point, levels, facing)]
        if len(available) == 1:
            return available[0]
        if room_beyond(point, levels, preferred) >= CORE_DOOR_ROOM_M:
            return preferred
        if _core_run_axis(anchors, point) == 'x':
            return 1.0 if point[0] > (plan.x_min + plan.x_max) / 2.0 else -1.0
        return 1.0 if point[1] > (plan.y_min + plan.y_max) / 2.0 else -1.0

    def preferred(point, partner):
        axis = 0 if _core_run_axis(anchors, point) == 'x' else 1
        return -1.0 if partner is not None and partner[axis] < point[axis] else 1.0

    partner = anchors['extras'][0][0] if anchors['extras'] else anchors['second']
    facing = settle(primary, preferred(primary, partner),
                    anchors['served'])
    cores = [(primary, anchors['served'], ('A', 'B'), 'LND', facing)]
    others = []
    if anchors['second'] is not None:
        others.append((anchors['second'], anchors['second_served'], SECOND_FLIGHT_PAIR, 'LND2'))
    others.extend((point, levels, EXTRA_FLIGHT_PAIRS[index], f'LND{3 + index}')
                  for index, (point, levels) in enumerate(anchors['extras']))
    for point, levels, tags, label in others:
        cores.append((point, levels, tags, label,
                      settle(point, preferred(point, primary), levels)))
    return cores


def _rect_ring(x0, y0, x1, y1):
    return [v2(x0, y0), v2(x1, y0), v2(x1, y1), v2(x0, y1)]


def _place_lift(lattice, anchors, keep_out):
    """Try each side of a stair; a lift never consumes a stair's clear volume."""
    if anchors['primary'] is None:
        return None
    ax, ay = anchors['primary']
    width, run = anchors['width'], anchors['run']
    half = LIFT_SHAFT_M / 2.0
    dx = width * 1.1 + CORE_CLEARANCE_M + LIFT_GAP_M + half
    dy = run / 2.0 + 1.7 + CORE_CLEARANCE_M + LIFT_GAP_M + half
    layout = _core_layout(anchors)
    stair_boxes = _core_rects(anchors)
    # Not in front of a core's exit door either: the strip outside the landing
    # face is the corridor every route to that stair uses, and a shaft parked in
    # it between two cores facing each other closed both doors on one theatre.
    approaches = []
    for (px, py), _levels, _tags, _label, facing in layout:
        face_y = -facing * (run / 2.0 + 1.7 + CORE_CLEARANCE_M)
        outer = face_y - facing * (LIFT_SHAFT_M + 0.5)
        approaches.append(_core_bounds((px, py),
            (-CORE_DOOR_W_M / 2.0 - 1.0, min(face_y, outer),
              CORE_DOOR_W_M / 2.0 + 1.0, max(face_y, outer)),
            _core_run_axis(anchors, (px, py))))
    candidates = [_core_xy((ax, ay), u, v, _core_run_axis(anchors, (ax, ay)))
                  for u, v in ((dx, 0.0), (-dx, 0.0), (0.0, dy), (0.0, -dy))]
    # The shaft is an opening in the bay beside the core, and the grid has already
    # been drawn to the core (`_frame_the_volumes`): a shaft straddling one of its
    # lines would put a girder through the lift. Candidates inside one bay are
    # tried first; the rest are the fallback, reported by the floor framing.
    def crosses_grid(candidate) -> bool:
        cx, cy = candidate
        return (any(cx - half + 0.05 < x < cx + half - 0.05 for x in lattice.x_lines)
                or any(cy - half + 0.05 < y < cy + half - 0.05 for y in lattice.y_lines))
    candidates = sorted(candidates, key=crosses_grid)
    for count in range(len(anchors['served']), 1, -1):
        served = anchors['served'][:count]
        regions = [plan_polygon(level.plate).difference(
            unary_union([plan_polygon(h) for h in level.voids])) for level in served]
        for cx, cy in candidates:
            bounds = (cx - half, cy - half, cx + half, cy + half)
            footprint = plan_box(*bounds).buffer(CORE_CLEARANCE_M, join_style=2)
            if (all(region.covers(footprint) for region in regions)
                    and not any(_box_overlaps(bounds, other)
                                for other in (*keep_out, *stair_boxes, *approaches))):
                return (cx, cy, served)
    return None


def _opening_rects(anchors, level_id, *, ceiling=False):
    """The structural openings on one level: each flight with its turn, each shaft.

    Plan rectangles, because three readers need the same answer -- the slab and the
    ceiling cut them out, and the floor framing now frames them. The floor landing
    is not among them: it is floor, carried on the joists that run beneath it.
    """
    width, run = anchors['width'], anchors['run']
    rects = []
    for (ax, ay), levels, tags, _label, facing in _core_layout(anchors):
        cut_levels = levels[:-1] if ceiling else levels[1:]
        if level_id not in {level.id for level in cut_levels}:
            continue
        rects.append(_opening_span(ax, ay, width, run, facing,
                                   _core_run_axis(anchors, (ax, ay))))
    if anchors['lift'] is not None:
        cx, cy, levels = anchors['lift']
        cut_levels = levels[:-1] if ceiling else levels[1:]
        if level_id in {level.id for level in cut_levels}:
            half = LIFT_SHAFT_M / 2.0
            rects.append((cx - half, cy - half, cx + half, cy + half))
    return rects


def _core_landing_levels(levels):
    """Floor interfaces exist independently of flights between those floors."""
    return [level for index,level in enumerate(levels)
            if index > 0 or level.kind == 'occupied']


def _emit_core_floor_interfaces(b, point, served, landing_tag, facing, width, run):
    ax,ay = point
    axis = _core_run_axis(b.cores, point)
    y0 = ay-facing*run/2
    centre = _core_xy(point, 0.0, y0-facing*.8-ay, axis)
    size = (width*2.2, LANDING_OVERLAP_M*2)
    if axis == 'x':
        size = size[::-1]
    for level in _core_landing_levels(served):
        ident = f'CIR-{landing_tag}-{level.id}'
        _emit_floor_landing(b,ident,*centre,level,*size)
        _emit_core_door_threshold(b,ident,ax,ay,level,width,run,facing,axis)


def _landing_footprints(anchors, level_id):
    """Where each floor landing stands on this level, as the plan rectangle it owns.

    The slab gives this floor up to the landing rather than lying under it: two
    coplanar walking surfaces in one place drew as a striped fight between them and
    counted the same floor twice. One surface owns each square metre; the landing is
    that surface here, flush with the plate it abuts, bearing on the joists below.
    """
    width, run = anchors['width'], anchors['run']
    rects = []
    for (ax, ay), levels, _tags, _label, facing in _core_layout(anchors):
        if level_id not in {level.id for level in _core_landing_levels(levels)}:
            continue
        y0 = -facing * run / 2.0
        centre_y = y0 - facing * 0.8
        rects.append(_core_bounds((ax, ay), (-width * 1.1, centre_y - LANDING_OVERLAP_M,
                      width * 1.1, centre_y + LANDING_OVERLAP_M),
                      _core_run_axis(anchors, (ax, ay))))
    return rects


def _core_openings(anchors, level_id, *, ceiling=False):
    """Clear the flight and turn as rings; the floor landing remains supported at
    its edge and, on the slab, owns its own floor (see `_landing_footprints`)."""
    return [_rect_ring(*rect) for rect in _opening_rects(anchors, level_id, ceiling=ceiling)]


def core_reservations(lattice, datums,
                      ) -> tuple[tuple[float, float, float, float], ...]:
    """The floor area the cores occupy, as plan rectangles.

    Generous on purpose: a landing that overlaps the plate edge, a lift lobby, the
    swing of a door onto the stair. A room laid out flush against a core is a room
    somebody has to walk through.
    """
    anchors = core_anchors(lattice, datums)
    width, run = anchors['width'], anchors['run']
    anchor_points = [anchors['primary'], anchors['second']]
    anchor_points += [point for point, _levels in anchors['extras']]
    rectangles = [_core_box(*anchor, width, run, _core_run_axis(anchors, anchor))
                  for anchor in anchor_points if anchor is not None]
    if anchors['lift'] is not None:
        cx, cy, _levels = anchors['lift']
        half = LIFT_SHAFT_M / 2.0 + CORE_CLEARANCE_M
        rectangles.append((cx - half, cy - half, cx + half, cy + half))
    return tuple(rectangles)


def _emit_program_public_stair(b: _Builder, podium, ground, width: float) -> None:
    """Emit the expressive entry stair selected by Program Volume grammar.

    Protected cores remain the egress stairs.  This stair gives the massing its
    public sectional character and is therefore registered to the same boundary
    station as the entrance rather than counted as a life-safety exit.
    """
    before = set(b.element_ids)
    origin = b.approach['entry_point']
    tangent = b.approach['entry_tangent']
    outward = b.approach['entry_outward']
    family = b.approach['public_stair_family']
    top = _local_xy(origin, tangent, outward, 0.0, -LANDING_OVERLAP_M / 2.0)
    rise = podium.z - ground.z
    depth = max(4.0, rise * 2.2)

    def point(u: float, distance: float, z: float) -> Vector3:
        x, y = _local_xy(origin, tangent, outward, u, distance)
        return v3(x, y, z)

    def intermediate_landing(ident: str, u: float, distance: float, z: float,
                             size_u: float, size_v: float,
                             supports: Iterable[str] = ()) -> None:
        x, y = _local_xy(origin, tangent, outward, u, distance)
        tangent_is_y = abs(tangent[1]) > abs(tangent[0])
        b.add(ident, 'stair_half_landing', 'circulation', 'public_stair',
              BoxGeometry(
                  center=v3(x, y, z - 0.12),
                  size=v3(size_v if tangent_is_y else size_u,
                          size_u if tangent_is_y else size_v, 0.24)),
              'white', category='circulation', program='public_entry',
              level_id=ground.id, datum_refs=['flight_width_m', 'riser_m'],
              supports=supports,
              rule_refs=['PV-CIRC-PUBLIC-STAIR'],
              reason=f'{family} intermediate public landing, located from the '
                     'Program Volume entry station. It is expressive circulation '
                     'and is not counted as a protected egress stair.')

    if b.approach.get('arrival_assembly') is not None:
        assembly = b.approach['arrival_assembly']
        _emit_flight(b,'F01',point(0.,assembly.stair_start_v,ground.z),
                     point(0.,assembly.stair_end_v,podium.z),assembly.stair_width_m,
                     ground.id,clear_end_landing=True)
    elif family == 'terraced_cascade':
        segments = 3
        stair_width = width * 1.45
        for index in range(segments):
            d0 = depth * (1.0 - index / segments)
            d1 = depth * (1.0 - (index + 1) / segments)
            z0 = ground.z + rise * index / segments
            z1 = ground.z + rise * (index + 1) / segments
            _emit_flight(
                b, f'TC{index:02d}', point(0.0, d0, z0), point(0.0, d1, z1),
                stair_width, ground.id, typed_supports=True,
                # A stringer returns to the support at its lower terminal.  The
                # landing above is carried by the lower flight; recording both ends
                # would create a false landing <-> stringer dependency cycle.
                terminal_supports=(
                    'SIT-POD-001' if index == 0 else
                    f'CIR-PUBLIC-TC-LND-{index - 1:02d}',))
            if index < segments - 1:
                intermediate_landing(
                    f'CIR-PUBLIC-TC-LND-{index:02d}', 0.0, d1, z1,
                    stair_width * 1.15, max(1.525, width * 0.75),
                    supports=(
                        f'CIR-STG-TC{index:02d}-L',
                        f'CIR-STG-TC{index:02d}-R'))
    elif family == 'bridge_split':
        middle_d = depth * 0.48
        middle_z = ground.z + rise * 0.48
        lower_width = width * 1.25
        _emit_flight(
            b, 'BS00', point(0.0, depth, ground.z),
            point(0.0, middle_d, middle_z), lower_width, ground.id)
        intermediate_landing(
            'CIR-PUBLIC-BS-LND-00', 0.0, middle_d, middle_z,
            width * 2.4, max(1.525, width * 0.9))
        branch_width = width * 0.72
        for side, tag in ((-1.0, 'L'), (1.0, 'R')):
            _emit_flight(
                b, f'BS{tag}01',
                point(side * width * 0.28, middle_d, middle_z),
                point(side * width * 0.45, 0.0, podium.z),
                branch_width, ground.id)
    else:
        _emit_flight(
            b, 'F01', point(0.0, depth, ground.z),
            v3(top[0], top[1], podium.z), width * 1.3, ground.id)

    rx0, ry0, rx1, ry1 = b.approach['entry']
    _emit_floor_landing(
        b, 'CIR-LND-ENTRY', (rx0 + rx1) / 2.0, (ry0 + ry1) / 2.0,
        podium, rx1 - rx0, ry1 - ry0,
        supports=(f'STR-SLB-{podium.id}',))
    b.public_stair_ids = sorted(b.element_ids - before)


def _resolve_program_circulation(
    b: _Builder, *, portal_report=None, model: BuildingModelV3 | None = None,
) -> ResolvedCirculationPlan | None:
    """Measure the emitted circulation back against its Program Volume intent.

    Geometry checks and connection checks stay separate.  A code-checked exterior
    ramp can therefore be recorded as emitted without upgrading the complete route
    while its facade threshold and supported interior continuation remain unresolved.
    """
    intent = b.lattice.circulation_intent
    if intent is None:
        return None

    findings: list[CirculationFinding] = []
    carriers = _program_carrier_regions(b.lattice)
    primary = b.cores.get('primary')
    served = [level for level in b.cores.get('served', [])
              if level.kind == 'occupied']
    outside: list[str] = []
    if primary is None:
        outside = [level.id for level in served] or ['all occupied levels']
    else:
        cores = [('primary', primary, served)]
        if b.cores.get('second') is not None:
            cores.append((
                'second', b.cores['second'],
                [level for level in b.cores.get('second_served', [])
                 if level.kind == 'occupied']))
        cores.extend((
            f'extra-{index + 1}', point,
            [level for level in levels if level.kind == 'occupied'])
            for index, (point, levels) in enumerate(b.cores.get('extras', [])))
        for label, point, levels in cores:
            footprint = plan_box(*_core_box(
                *point, b.cores['width'], b.cores['run'], _core_run_axis(b.cores, point)))
            outside.extend(
                f'{label}:{level.id}' for level in levels
                if level.id not in carriers
                or not covers_registered_footprint(carriers[level.id],footprint))
    findings.append(CirculationFinding(
        id='PV-CIRC-CORE-CARRIER',
        status='failed' if outside else 'passed',
        subject='protected stair cores',
        detail=(
            'A protected core footprint leaves its declared circulation-spine '
            f'Program Volume on: {", ".join(outside)}.'
            if outside else
            'Every emitted protected stair-core footprint is contained by declared '
            'carrier volumes on every occupied level it serves.'),
    ))

    findings.append(CirculationFinding(
        id='PV-CIRC-PUBLIC-STAIR',
        status='passed' if b.public_stair_ids else 'failed',
        subject=intent.public_stair_family,
        detail=(
            f'{len(b.public_stair_ids)} emitted parts instantiate the '
            f'{b.approach.get("public_stair_family",intent.public_stair_family)} family '
            'at the Program Volume entry station; '
            + (intent.arrival_assembly.basis if intent.arrival_assembly else '')
            if b.public_stair_ids else
            f'No emitted parts instantiate the requested '
            f'{intent.public_stair_family} public stair family.'),
    ))

    if b.accessible_route is not None:
        issues = b.accessible_route.compliance()
        ramp_status = 'failed' if issues else 'passed'
        ramp_detail = ('; '.join(issues) if issues else
                       f'{len(b.accessible_route.runs)} runs and '
                       f'{len(b.accessible_route.landings)} landings satisfy the '
                       'evaluated ADA §405 geometry checks.')
    elif b.unresolved_accessible_route:
        ramp_status = 'failed'
        ramp_detail = b.unresolved_accessible_route
    else:
        ramp_status = 'unevaluated'
        ramp_detail = 'No accessible approach result was recorded.'
    findings.append(CirculationFinding(
        id='PV-CIRC-ACCESSIBLE-APPROACH', status=ramp_status,
        subject=intent.ramp_preference, detail=ramp_detail))

    attachment_portal_id = None
    attached_portal = None
    intended_portal = None
    if b.accessible_route is None:
        portal_status = 'unevaluated'
        portal_detail = ('No ramp top landing exists to test against a facade portal; '
                         'the accessible-approach finding records the unresolved route.')
    elif portal_report is None:
        portal_status = 'unevaluated'
        portal_detail = ('The emitted approach has not yet been measured against an '
                         'open facade portal on the same Program Volume boundary station.')
    else:
        top = next((landing for landing in b.accessible_route.landings
                    if landing.kind == 'top'), None)
        top_id = f'CIR-RMP-LND-{top.index:02d}' if top is not None else None
        entry_id = 'CIR-LND-ENTRY'
        link_id = b.approach.get('ramp_link_id')
        emitted = {
            instance.id: instance.geometry
            for group in b.groups.values()
            for instance in group.instances
        }

        def surfaces_meet(first_id: str | None, second_id: str | None) -> bool:
            if not first_id or not second_id:
                return False
            from .geometry_review import _polygon, _z_interval

            first, second = emitted.get(first_id), emitted.get(second_id)
            if first is None or second is None:
                return False
            first_plan, second_plan = _polygon(first), _polygon(second)
            first_z, second_z = _z_interval(first), _z_interval(second)
            return bool(
                first_plan is not None and second_plan is not None
                and first_z is not None and second_z is not None
                and first_plan.intersection(second_plan).area > 1.0e-5
                and math.isclose(first_z[1], second_z[1], abs_tol=0.005))

        walking_chain = (
            surfaces_meet(top_id, entry_id)
            or (surfaces_meet(top_id, link_id)
                and surfaces_meet(link_id, entry_id))
        )
        from .envelope import planned_entrance
        intended_portal = planned_entrance(b.lattice, b.datums, b.approach)

        def shares_entry_station(portal) -> bool:
            if intended_portal is None:
                return False
            return (
                math.dist(portal.center, intended_portal.center) <= 1.0e-4
                and abs(portal.tangent[0] * intended_portal.tangent[0]
                        + portal.tangent[1] * intended_portal.tangent[1])
                >= 1.0 - 1.0e-5
                and math.isclose(
                    portal.floor_z, intended_portal.floor_z, abs_tol=0.005))

        candidates = [
            portal for portal in portal_report.portals
            if portal.kind == 'entrance'
            and portal.level_id == intent.entry_station.level_id
            and shares_entry_station(portal)
            and entry_id in set(portal.side_a.support_ids + portal.side_b.support_ids)
        ]
        passable = [portal for portal in candidates if portal.passable]
        chosen = (sorted(passable, key=lambda portal: portal.id)
                  or sorted(candidates, key=lambda portal: portal.id))
        if chosen:
            attached_portal = chosen[0]
            attachment_portal_id = attached_portal.id
        if passable and walking_chain:
            portal_status = 'passed'
            portal_detail = (
                f'Ramp top landing {top_id} reaches {entry_id}'
                + (f' through level landing gallery {link_id}' if link_id else '')
                + f', and {entry_id} supports open facade portal '
                  f'{attachment_portal_id}. Every link has measured plan overlap, '
                  'matching top elevation, and a clear emitted threshold.')
        elif passable:
            portal_status = 'failed'
            portal_detail = (
                f'Facade portal {attachment_portal_id} is passable at {entry_id}, '
                f'but emitted walking surfaces do not connect ramp top {top_id} to '
                f'the entry landing through {link_id or "a direct joint"}.')
        elif candidates:
            portal_status = 'failed'
            reasons = '; '.join(candidates[0].reasons) or 'portal is not passable'
            portal_detail = (
                f'Ramp top landing {top_id} reaches facade portal '
                f'{attachment_portal_id}, but the emitted portal fails: {reasons}')
        else:
            portal_status = 'failed'
            portal_detail = (
                f'Ramp top landing {top_id or "unresolved"} supports no emitted '
                'entrance portal at the Program Volume entry level.')
    b.approach['ramp_attachment_verified'] = portal_status == 'passed'
    if portal_status != 'passed':
        interior_status = 'unevaluated'
        interior_detail = (
            'Interior continuation is withheld until the ramp has a verified open '
            'facade threshold; the exterior attachment finding records that prerequisite.')
    elif model is None or attached_portal is None or intended_portal is None:
        interior_status = 'unevaluated'
        interior_detail = (
            'The facade threshold is attached, but no completed model was supplied '
            'for a same-storey free-floor route probe to the vertical core.')
    else:
        from .geometry_review import _polygon
        from .navigation import WalkMesh, free_floor

        level = next((candidate for candidate in b.lattice.levels
                      if candidate.id == intent.entry_station.level_id), None)
        target_id = f'CIR-LND-{intent.entry_station.level_id}'
        target_geometry = emitted.get(target_id)
        if level is None or target_geometry is None:
            interior_status = 'failed'
            interior_detail = (
                f'No emitted primary-core floor landing {target_id} exists on the '
                'Program Volume entry level.')
        else:
            open_ids = {
                door_id for portal in portal_report.portals if portal.passable
                for door_id in portal.door_ids
            }
            domain, unresolved = free_floor(model, level, open_ids)
            target_plan = _polygon(target_geometry)
            source_region = domain.intersection(intended_portal.inside_approach)
            target_region = (domain.intersection(target_plan)
                             if target_plan is not None else None)
            if unresolved:
                interior_status = 'unevaluated'
                interior_detail = (
                    'The free-floor route probe found unresolved emitted geometry: '
                    + '; '.join(unresolved[:3]))
            elif (source_region.is_empty or target_region is None
                  or target_region.is_empty):
                interior_status = 'failed'
                interior_detail = (
                    f'The clear floor probe cannot locate both the inside of portal '
                    f'{attachment_portal_id} and primary-core landing {target_id}.')
            else:
                source = tuple(source_region.representative_point().coords[0])
                target = tuple(target_region.representative_point().coords[0])
                route = WalkMesh(domain).route(source, target)
                if route is None:
                    interior_status = 'failed'
                    interior_detail = (
                        f'No continuous supported obstacle-free route connects portal '
                        f'{attachment_portal_id} to primary-core landing {target_id}.')
                else:
                    distance = sum(math.dist(a, c) for a, c in zip(route, route[1:]))
                    interior_status = 'passed'
                    interior_detail = (
                        f'A {distance:.2f} m supported same-storey route connects the '
                        f'inside of portal {attachment_portal_id} to primary-core '
                        f'landing {target_id}, measured with the navigation module\'s '
                        '0.60 m planning body. Adopted-code width, headroom, fire '
                        'protection and accessible lift operation remain unverified.')

    findings.extend([
        CirculationFinding(
            id='PV-CIRC-PORTAL-ATTACHMENT', status=portal_status,
            subject='top landing to facade threshold', detail=portal_detail),
        CirculationFinding(
            id='PV-CIRC-INTERIOR-CONTINUATION', status=interior_status,
            subject='threshold to supported interior route',
            detail=interior_detail),
    ])

    primary_prefixes = (
        'STR-FDN-CORE-LND', 'STR-CWL-LND-', 'CIR-TRD-A', 'CIR-STG-A',
        'CIR-HLF-A', 'CIR-LND-L', 'CIR-RAL-A',
    )
    primary_ids = sorted(identifier for identifier in b.element_ids
                         if identifier.startswith(primary_prefixes))
    exterior_ids = sorted(set(b.public_stair_ids) | {
        identifier for identifier in b.element_ids
        if identifier.startswith((
            'CIR-RMP-', 'CIR-RAL-RMP-',
            # When a compliant ramp cannot fit, the explicitly reported fallback
            # access stair occupies the same exterior approach control.  Its flight,
            # rails and half-in/half-out arrival landing are legitimate named
            # exceptions; leaving them unnamed made two Program Volume grammars fail
            # the internal-solid gate for the very exterior route ADR 0024 permits.
            'CIR-TRD-R01', 'CIR-STG-R01', 'CIR-RAL-R01', 'CIR-LND-ACCESS',
        ))
    })
    if b.lattice.site_boundary:
        from .approach import site_approach_finding
        findings.append(site_approach_finding(b, exterior_ids))
    return ResolvedCirculationPlan(
        intent=intent,
        primary_core_ids=primary_ids,
        public_stair_ids=list(b.public_stair_ids),
        ramp_plan=b.accessible_route,
        attachment_portal_id=attachment_portal_id,
        exterior_exception_ids=exterior_ids,
        findings=findings,
    )


def _emit_circulation(b: _Builder) -> None:
    lattice, datums = b.lattice, b.datums
    levels = lattice.levels
    width = datums.value('flight_width_m')

    run = flight_run(width)

    # Serve the tallest run of levels a single core can actually reach, from the ground
    # up. A heavily stepped or split mass genuinely has no point in plan inside every
    # plate, and the honest answer is a stair that stops where the building stops being
    # stackable -- not one drawn through the levels it cannot reach. Falling back to a
    # centroid was the first attempt and it produced landings that were flush with a
    # floor and a metre and a half outside it, which is worse than none.
    anchors = b.cores
    layout = _core_layout(anchors)
    reached = {level.id for _point, run_levels, _tags, _label, _facing in layout
               for level in run_levels}
    b.unreached_levels = [level.id for level in lattice.occupied if level.id not in reached]
    b.second_stair_anchor = anchors['second']
    b.second_stair_levels = [level.id for level in anchors['second_served']]
    for (ax, ay), served, tags, landing_tag, facing in layout:
        run_axis = _core_run_axis(anchors, (ax, ay))

        def stair_point(dx, dy, z):
            return v3(*_core_xy((ax, ay), dx, dy, run_axis), z)

        # Landings belong to served floors, not to the preceding flight. A low
        # grade-to-entry rise can omit a switchback without erasing its doorway floor.
        _emit_core_floor_interfaces(b,(ax,ay),served,landing_tag,facing,width,run)
        for k, (lower, upper) in enumerate(zip(served, served[1:])):
            if upper.z - lower.z < 0.4:
                continue
            zm = (lower.z + upper.z) / 2.0
            y0, y1 = -facing * run / 2.0, facing * run / 2.0
            _emit_flight(b, f'{tags[0]}{k:02d}',
                         stair_point(-width / 2.0, y0, lower.z),
                         stair_point(-width / 2.0, y1, zm), width, lower.id)
            b.add(f'CIR-HLF-{tags[0]}{k:02d}', 'stair_half_landing', 'circulation', 'stairs',
                  BoxGeometry(center=stair_point(0.0, y1 + facing * 0.7, zm - 0.12),
                              size=(v3(1.4, width * 2.0, 0.24) if run_axis == 'x'
                                    else v3(width * 2.0, 1.4, 0.24))),
                  'white', category='circulation', program='circulation',
                  level_id=lower.id, lattice_index={'level': lower.index},
                  datum_refs=['flight_width_m', 'floor_to_floor_m'],
                  reason='Switchback turn at half storey height.')
            _emit_flight(b, f'{tags[1]}{k:02d}',
                         stair_point(width / 2.0, y1, zm),
                         stair_point(width / 2.0, y0, upper.z), width, lower.id)
            # Guard the three closed sides of the floor opening. The fourth side
            # remains open where the arriving floor landing connects to the plate.
            edge_x = width + 0.17
            edge_start = y0 - facing * 0.12
            edge_end = y1 + facing * 1.57
            corners = [(-edge_x, edge_start), (-edge_x, edge_end),
                       (edge_x, edge_end), (edge_x, edge_start)]
            for edge, (start, end) in enumerate(zip(corners, corners[1:])):
                _emit_railing(b, f'CORE-{landing_tag}-{upper.id}-{edge}',
                              stair_point(*start, upper.z), stair_point(*end, upper.z),
                              0.0, upper.id)

    # --- the external approach, from grade to the podium ----------------------
    # It genuinely starts outside the building; what it must not do is finish outside.
    # The top landing overlaps the podium plate, so the flight ends on the floor.
    if len(levels) > 1:
        podium = next((level for level in levels
                       if level.id == b.approach.get('podium_id')), levels[1])
        if lattice.circulation_intent is not None:
            _emit_program_public_stair(b, podium, levels[0], width)
        else:
            rx0, ry0, rx1, ry1 = b.approach['entry']
            entry_x, landing_y = (rx0 + rx1) / 2.0, (ry0 + ry1) / 2.0
            landing_depth = ry1 - ry0
            # The flight ends where the landing starts, derived from it rather than set
            # back on its own. Both used to be placed independently -- the flight 1.2 m
            # short of the plate, the landing 450 mm over it -- and the 1.65 m between them
            # was nobody's business, so the stair arrived at nothing. The landing itself
            # was decided in `_plan_approach`, where the slab read it first.
            top_y = landing_y - landing_depth / 2.0
            approach = max(4.0, (podium.z - levels[0].z) * 2.2)
            _emit_flight(b, 'F01',
                         v3(entry_x, top_y - approach, levels[0].z),
                         v3(entry_x, top_y, podium.z), width * 1.3, levels[0].id)
            _emit_floor_landing(b, 'CIR-LND-ENTRY', entry_x, landing_y, podium,
                                rx1 - rx0, landing_depth)

    # --- the lift and service core, inside the plan and full height -----------
    # A shaft is not a lift. The lift is the shaft plus the pit the buffers stand in,
    # the headroom above the top landing that the car, its run-by and the machine
    # need, and a door at every floor it serves. The first version emitted the shaft
    # between the levels in its served run and stopped at the top floor's slab: a
    # car could not have stopped there, and the compiler's own text said the level
    # was served. What is served is now read off the doors that were built.
    if anchors['lift'] is not None:
        cx, cy, served = anchors['lift']
        half = LIFT_SHAFT_M / 2.0
        floors = [level for level in served if level.kind != 'roof']
        ax, ay = anchors['primary']
        face_x = abs(ax - cx) >= abs(ay - cy)
        side = (1.0 if ax > cx else -1.0) if face_x else (1.0 if ay > cy else -1.0)
        from .portals import select_lift_face
        face_x, side, landing_levels = select_lift_face(
            b, floors, cx, cy, LIFT_SHAFT_M, LIFT_WALL_M, LIFT_DOOR_W_M,
            (face_x, side),declared_face=next((getattr(core,'access_face',None)
                for core in lattice.given_cores if core.kind=='lift'),None))

        def shaft_segment(segment_id: str, z_base: float, z_top: float, level,
                          reason: str) -> None:
            from .portals import shaft_wall_parts
            for tag, geometry in shaft_wall_parts(
                    cx, cy, LIFT_SHAFT_M, LIFT_WALL_M, z_base, z_top,
                    face_x=face_x, side=side,
                    opening_bottom=(level.z if z_base >= level.z-.001
                                    and level.id in landing_levels else None),
                    opening_width=LIFT_DOOR_W_M, opening_height=LIFT_DOOR_H_M):
                b.add(segment_id if tag == 'BACK' else f'{segment_id}-{tag}',
                      'elevator_shaft', 'circulation', 'vertical_core', geometry,
                      'concrete', category='service', program='vertical_circulation',
                      level_id=level.id, lattice_index={'level': level.index},
                      datum_refs=['flight_width_m'],
                      reason=reason + ' Separate wall solids preserve the actual landing aperture.')

        for lower, upper in zip(served, served[1:]):
            shaft_segment(f'CIR-SHF-{lower.id}', lower.z, upper.z, lower,
                          'Hollow lift shaft beside the stair, on the shared core '
                          'layout. Wall thickness is schematic, not a calculated '
                          'assembly.')
        if floors:
            bottom, top = floors[0], floors[-1]
            shaft_segment(f'CIR-SHF-{bottom.id}-PIT', bottom.z - LIFT_PIT_M, bottom.z,
                          bottom,
                          f'Lift pit, {LIFT_PIT_M:.1f} m below the lowest landing, for '
                          f'the buffers and the car\'s bottom run-by. Practice for a '
                          f'mid-speed passenger lift, not a manufacturer\'s figure; the '
                          f'pit floor bears on the ground it is dug into and its '
                          f'waterproofing is not designed.')
            # The overrun starts at the top landing floor, where the last storey
            # segment ended; the top landing's door sits in it.
            shaft_segment(f'CIR-SHF-{top.id}-OVR', top.z, top.z + LIFT_OVERRUN_M, top,
                          f'Lift overrun, {LIFT_OVERRUN_M:.1f} m above the top landing: '
                          f'car headroom, counterweight run-by and the machine-room-'
                          f'less drive in the headroom. Practice, not a manufacturer\'s '
                          f'dimension; the machine, controller and hoist ropes are not '
                          f'modelled.')
            # Doors face the stair the shaft was placed beside, on the shaft face
            # nearest the primary anchor.
            if face_x:
                door_size = v3(LIFT_WALL_M, LIFT_DOOR_W_M, LIFT_DOOR_H_M)
                door_at = lambda z: v3(cx + side * (half - LIFT_WALL_M / 2.0), cy, z)
            else:
                door_size = v3(LIFT_DOOR_W_M, LIFT_WALL_M, LIFT_DOOR_H_M)
                door_at = lambda z: v3(cx, cy + side * (half - LIFT_WALL_M / 2.0), z)
            for level in floors:
                if level.id not in landing_levels:
                    continue
                b.add(f'CIR-SHF-{level.id}-DR', 'door', 'circulation', 'vertical_core',
                      BoxGeometry(center=door_at(level.z + LIFT_DOOR_H_M / 2.0),
                                  size=door_size),
                      'frame_dark', category='service', program='vertical_circulation',
                      level_id=level.id, lattice_index={'level': level.index},
                      datum_refs=['flight_width_m'],
                      rule_refs=['ADA-407.3.1'],
                      reason=(f'Lift landing door, {LIFT_DOOR_W_M * 1000:.0f} mm clear '
                              f'by {LIFT_DOOR_H_M * 1000:.0f} mm, in the shaft face '
                              f'toward measured clear supported floor. The shaft wall has a real aperture; '
                              f'the car-side floor, operator and hardware remain '
                              f'unmodelled, so usable lift service is unverified.'))
                # The slab is intentionally cut back at the shaft opening. Add a
                # registered threshold slab through the wall opening so the
                # emitted sill has an actual top surface at the landing elevation.
                # The shaft-side walking condition remains unevaluated until a
                # lift car/door assembly is verified.
                threshold_xy = door_at(level.z)
                threshold_size = (LIFT_WALL_M, LIFT_DOOR_W_M) if face_x else (
                    LIFT_DOOR_W_M, LIFT_WALL_M)
                floor_supports = b.ids(
                    kinds=['floor_slab', 'podium_slab'], level_id=level.id)
                b.add(
                    f'CIR-LFT-LND-{level.id}', 'lift_landing', 'circulation',
                    'vertical_core',
                    BoxGeometry(center=v3(threshold_xy.x, threshold_xy.y,
                                          level.z - LIFT_THRESHOLD_THICKNESS_M / 2.0),
                                size=v3(threshold_size[0], threshold_size[1],
                                        LIFT_THRESHOLD_THICKNESS_M)),
                    'concrete_light', category='service',
                    program='vertical_circulation', level_id=level.id,
                    lattice_index={'level': level.index},
                    datum_refs=['flight_width_m'], supports=floor_supports,
                    rule_refs=['MTA-LIFT-THRESHOLD-001'],
                    assembly_id=f'ASM-PV-LIFT-{level.id}',
                    part_role='lift_threshold',
                    reason=(
                        'Lift landing threshold slab bridges the measured shaft-wall '
                        'aperture to the supported floor surface. Its thickness and '
                        'bearing are coordination geometry; sill, waterproofing, '
                        'door hardware and lift operation remain unverified.'))
                b.lift_served_levels.append(level.id)

            # The car, parked at the lowest landing it serves, and the drive in the
            # overrun. A shaft with doors is still not a lift: the car is the one
            # thing a landing door opens onto, and the drive is why the overrun is the
            # height it is. The car floor stands flush with its landing, so that
            # landing's door has floor on both sides; every other landing's door
            # opens onto the shaft, and the portal report says so. Travel, ropes,
            # the counterweight, buffers and the controller are not modelled.
            parked_levels = [level for level in floors if level.id in landing_levels]
            if parked_levels:
                parked = parked_levels[0]
                inner = LIFT_SHAFT_M - 2.0 * LIFT_WALL_M
                car_w, car_d, car_h = min(1.6, inner - 0.2), min(1.4, inner - 0.2), 2.3
                # The car floor meets the landing sill: the sill gap is below the
                # tolerance a walking approach is measured at.
                offset = half - LIFT_WALL_M - car_d / 2.0
                if face_x:
                    car_centre = (cx + side * offset, cy)
                    car_size = (car_d, car_w)
                    back_centre = (cx + side * (offset - car_d / 2.0 + 0.025), cy)
                    back_size = (0.05, car_w)
                    machine_centre = (cx - side * (half - LIFT_WALL_M - 0.35), cy)
                    machine_size = (0.7, 0.9)
                else:
                    car_centre = (cx, cy + side * offset)
                    car_size = (car_w, car_d)
                    back_centre = (cx, cy + side * (offset - car_d / 2.0 + 0.025))
                    back_size = (car_w, 0.05)
                    machine_centre = (cx, cy - side * (half - LIFT_WALL_M - 0.35))
                    machine_size = (0.9, 0.7)
                pit_walls = [f'CIR-SHF-{bottom.id}-PIT-SIDEA',
                             f'CIR-SHF-{bottom.id}-PIT-SIDEB']
                car_floor = 'CIR-LFT-CAR-FLOOR'
                b.add(car_floor, 'lift_car', 'circulation', 'vertical_core',
                      BoxGeometry(center=v3(car_centre[0], car_centre[1],
                                            parked.z - 0.075),
                                  size=v3(car_size[0], car_size[1], 0.15)),
                      'steel_dark', category='service', program='vertical_circulation',
                      level_id=parked.id, lattice_index={'level': parked.index},
                      datum_refs=['flight_width_m'],
                      supports=[wall for wall in pit_walls if wall in b.element_ids],
                      assembly_id='CIR-LFT-CAR', part_role='floor',
                      reason=(f'Lift car floor, {car_w:.1f} x {car_d:.1f} m, parked '
                              f'flush with the {parked.id} landing on the guide-rail '
                              f'walls. The one landing door that opens onto floor; the '
                              f'car does not travel in this model.'))
                b.add('CIR-LFT-CAR-BACK', 'lift_car', 'circulation', 'vertical_core',
                      BoxGeometry(center=v3(back_centre[0], back_centre[1],
                                            parked.z + car_h / 2.0),
                                  size=v3(back_size[0], back_size[1], car_h)),
                      'steel_dark', category='service', program='vertical_circulation',
                      level_id=parked.id, lattice_index={'level': parked.index},
                      datum_refs=['flight_width_m'], supports=[car_floor],
                      assembly_id='CIR-LFT-CAR', part_role='back',
                      reason='Lift car back wall, standing on the car floor; the side '
                             'walls and the car door are not modelled.')
                b.add('CIR-LFT-CAR-CANOPY', 'lift_car', 'circulation', 'vertical_core',
                      BoxGeometry(center=v3(car_centre[0], car_centre[1],
                                            parked.z + car_h + 0.025),
                                  size=v3(car_size[0], car_size[1], 0.05)),
                      'steel_dark', category='service', program='vertical_circulation',
                      level_id=parked.id, lattice_index={'level': parked.index},
                      datum_refs=['flight_width_m'], supports=['CIR-LFT-CAR-BACK'],
                      assembly_id='CIR-LFT-CAR', part_role='canopy',
                      reason=f'Lift car canopy, {car_h:.1f} m over the car floor.')
                overrun_wall = f'CIR-SHF-{top.id}-OVR'
                b.add('CIR-LFT-MACHINE', 'mechanical_equipment', 'circulation',
                      'vertical_core',
                      BoxGeometry(center=v3(machine_centre[0], machine_centre[1],
                                            top.z + LIFT_OVERRUN_M - 0.5),
                                  size=v3(machine_size[0], machine_size[1], 0.8)),
                      'steel_dark', category='service', program='vertical_circulation',
                      level_id=top.id, lattice_index={'level': top.index},
                      datum_refs=['flight_width_m'],
                      supports=[overrun_wall] if overrun_wall in b.element_ids else [],
                      assembly_id='CIR-LFT-MACHINE', part_role='machine',
                      reason=(f'Machine-room-less drive in the {LIFT_OVERRUN_M:.1f} m '
                              f'overrun, on the shaft back wall. A placeholder '
                              f'envelope: the drive, ropes, controller and their loads '
                              f'on the shaft are not designed.'))
            unserved = [level.id for level in lattice.occupied
                        if level.id not in b.lift_served_levels]
            b.lift_note = (
                f'Lift: shaft from a {LIFT_PIT_M:.1f} m pit below {bottom.id} to a '
                f'{LIFT_OVERRUN_M:.1f} m overrun above {top.id}, landing doors at '
                f'{", ".join(b.lift_served_levels)}. '
                + ('Every occupied level has a landing door.' if not unserved else
                   f'Occupied levels without a landing door: {", ".join(unserved)}.')
                + ' Pit and overrun depths are practice for a machine-room-less '
                  'passenger lift, not a manufacturer\'s figures; the car, drive, '
                  'controller and door hardware are not modelled and the lift\'s '
                  'capacity and accessible operation are unverified.')
    if not b.lift_note:
        b.lift_note = ('No lift: no shaft position clear of the stairs fits inside '
                       'every plate of a run this core serves.')

    # --- the accessible approach, to ADA or not at all ------------------------
    if len(levels) > 1:
        entry_xs = [p.x for p in levels[1].plate]
        _emit_accessible_approach(
            b, levels, width, (min(entry_xs) + max(entry_xs)) / 2.0)

    # --- edge rails on every open plate edge ----------------------------------
    for level in levels[1:]:
        for ei in range(len(level.plate)):
            a, c = level.plate[ei], level.plate[(ei + 1) % len(level.plate)]
            mx, my = (a.x + c.x) / 2.0, (a.y + c.y) / 2.0
            if lattice.encloses(mx, my) and not level.is_terrace:
                continue
            _emit_railing(b, f'EDGE-{level.id}-E{ei:03d}',
                          v3(a.x, a.y, level.z), v3(c.x, c.y, level.z), 0.0, level.id)


# ---------------------------------------------------------------------------
# Program
# ---------------------------------------------------------------------------

def _plate_box(plate: list[Vector2]) -> tuple[float, float, float, float]:
    return (min(p.x for p in plate), min(p.y for p in plate),
            max(p.x for p in plate), max(p.y for p in plate))


_CATEGORY_MATERIAL = {
    'public': 'prog_public', 'private': 'prog_private',
    'circulation': 'prog_circulation', 'service': 'prog_service',
}


# The clear height a partition runs to: the underside of the structure above, so it
# actually separates rather than stopping at a ceiling nobody modelled.
PARTITION_HEAD_CLEARANCE_M = 0.15

# A suspended ceiling board and its grid. Thin, and not nothing: at zero it
# is a surface with no body and a cut plane can make nothing of it.
CEILING_THICKNESS_M = 0.025

# The podium's underside, which is also grade.
PODIUM_BASE_M = -0.35

# How far the drawn earth reaches below grade. Enough to bury the deepest pad footing
# and leave a band of soil under it, which is what makes a section read as founded.
SITE_EARTH_DEPTH_M = 2.6


def _zone_edges(zone) -> list[tuple[str, float, float, float, float]]:
    """The four sides of a zone rectangle, named."""
    return [
        ('south', zone.x0, zone.y0, zone.x1, zone.y0),
        ('north', zone.x0, zone.y1, zone.x1, zone.y1),
        ('west', zone.x0, zone.y0, zone.x0, zone.y1),
        ('east', zone.x1, zone.y0, zone.x1, zone.y1),
    ]


def _touching_zone(zone, others, edge: str, tolerance: float = 0.35):
    """The zone on the other side of one edge, if a zone is there at all.

    A band-sliced plan puts neighbours side by side in x within a band and separates
    bands in y with circulation, so an edge with nothing against it faces either the
    corridor or the envelope. Both need a wall; only one of them needs a rated one.
    """
    for other in others:
        if other.space_id == zone.space_id:
            continue
        if edge in ('south', 'north'):
            y = zone.y0 if edge == 'south' else zone.y1
            near = abs((other.y1 if edge == 'south' else other.y0) - y) <= tolerance
            overlap = min(zone.x1, other.x1) - max(zone.x0, other.x0)
        else:
            x = zone.x0 if edge == 'west' else zone.x1
            near = abs((other.x1 if edge == 'west' else other.x0) - x) <= tolerance
            overlap = min(zone.y1, other.y1) - max(zone.y0, other.y0)
        if near and overlap > 1.0:
            return other
    return None


def _clear_of_cores(x0: float, y0: float, x1: float, y1: float,
                    reserved) -> list[tuple[float, float, float, float]]:
    """The longest stretch of this wall line that misses every core.

    A partition follows the edge of the zone it encloses, and the zones are now banded
    around the cores -- so a zone edge runs *up to* a core and the wall along it runs
    straight through the stair beyond. The wall is right; its length is not. Trimming
    it to the clear stretch is what a person drawing the plan would do, and stopping a
    wall at a stair is a thing buildings do rather than a compromise.
    """
    if not reserved:
        return [(x0, y0, x1, y1)]
    horizontal = abs(x1 - x0) >= abs(y1 - y0)
    lo, hi = (min(x0, x1), max(x0, x1)) if horizontal else (min(y0, y1), max(y0, y1))
    fixed = y0 if horizontal else x0

    blocked: list[tuple[float, float]] = []
    for rx0, ry0, rx1, ry1 in reserved:
        if horizontal:
            if ry0 <= fixed <= ry1:
                blocked.append((rx0, rx1))
        elif rx0 <= fixed <= rx1:
            blocked.append((ry0, ry1))

    clear = [(lo, hi)]
    for bx0, bx1 in blocked:
        nxt: list[tuple[float, float]] = []
        for a, b in clear:
            if bx1 <= a or bx0 >= b:
                nxt.append((a, b))
                continue
            if bx0 > a:
                nxt.append((a, bx0))
            if bx1 < b:
                nxt.append((bx1, b))
        clear = nxt
    # Every clear stretch, not just the longest. Keeping one piece was fine on a wide
    # plate and emptied a narrow one: on the tower two cores take most of a twenty-one
    # metre floor, every wall was cut to under a metre, and the storey came out with no
    # partitions at all -- rooms with no edges, which is worse than a wall that stops.
    return [((a, fixed, b, fixed) if horizontal else (fixed, a, fixed, b))
            for a, b in clear if b - a >= 0.05]


def _clear_of_plate_edge(x0: float, y0: float, x1: float, y1: float,
                         level, thickness: float
                         ) -> list[tuple[float, float, float, float]]:
    """Clip an internal partition so its physical thickness stays in the massing.

    A room rectangle may meet the exterior Program Volume boundary. Its perimeter
    line is then the facade's host, not a second partition centred on the same edge.
    Intersecting the run with the plate inset by half its wall thickness removes that
    exterior portion and trims perpendicular returns cleanly back from the facade.
    """
    material = plan_polygon(level.plate).difference(
        unary_union([plan_polygon(hole) for hole in level.voids]))
    safe = material.buffer(-(thickness / 2.0 + 1e-5), join_style=2)
    if safe.is_empty:
        return []
    start, end = (x0, y0), (x1, y1)
    line = LineString([start, end])
    clipped = line.intersection(safe)
    pieces = ([clipped] if clipped.geom_type == 'LineString' and not clipped.is_empty else
              [part for part in getattr(clipped, 'geoms', ())
               if part.geom_type == 'LineString' and not part.is_empty])
    dx, dy = x1 - x0, y1 - y0
    length2 = max(1e-12, dx * dx + dy * dy)

    def station(point) -> float:
        return ((point[0] - x0) * dx + (point[1] - y0) * dy) / length2

    result = []
    for part in sorted(pieces, key=lambda item: station(item.coords[0])):
        a, c = part.coords[0], part.coords[-1]
        if station(a) > station(c):
            a, c = c, a
        if math.dist(a, c) >= 0.05:
            result.append((float(a[0]), float(a[1]), float(c[0]), float(c[1])))
    return result


def _partition_door_id(run_id: str, tag: str) -> str:
    """Name a door from its semantic room edge, keeping split-run identity last.

    Program Volume edge clearance can split one planned partition edge into several
    physical runs, so the wall run carries a ``-Pnn`` suffix.  A door's stable
    semantic prefix is also used by drawing readers to resolve the room it serves;
    putting that piece suffix between the room edge and ``DR`` made
    ``PRG-PRT-...-P00-DR`` resolve to a non-existent zone.  Keep the piece marker
    after the door tag instead.  The first piece therefore retains the legacy id,
    while later pieces remain unique and still resolve to the same program zone.
    """
    base, separator, piece = run_id.rpartition('-P')
    if separator and piece.isdigit():
        piece_suffix = '' if int(piece) == 0 else f'-P{int(piece):02d}'
        run_id = base
    else:
        piece_suffix = ''
    return f'{run_id}-{tag}{piece_suffix}'


def _emit_partition_run(
    b: _Builder, run_id: str, partition, requirement, level, x0: float, y0: float,
    x1: float, y1: float, height: float, zone, *, openings=None, access_rooms=(),
) -> None:
    """Emit a planned wall and its actual apertures, preserving existing leaves."""
    from .portals import WallOpening, choose_partition_opening, wall_run_parts
    length = math.hypot(x1-x0,y1-y0)
    if length < .05:
        return
    thickness = partition.thickness_mm/1000
    refs = ['floor_to_floor_m','slab_thickness_m','circulation_allowance']
    rules = [requirement.fire_clause] + (
        ['CONSTITUTION-OPAQUE'] if requirement.opaque_required else []) + (
        ['CONSTITUTION-ABUSE'] if requirement.abuse_resistant else [])
    unresolved = False
    if openings is None:
        openings = []
        if requirement.permeability in ('door','controlled_door'):
            at = choose_partition_opening(b,level,(x0,y0),(x1,y1),DOOR_LEAF_M,thickness)
            if at is None:
                unresolved = True
                rules.append('MTA-DOOR-UNRESOLVED')
            else:
                openings = [WallOpening(at_m=at,width_m=DOOR_LEAF_M,threshold_z=level.z)]
    rules.extend(f'MTA-ROOM-ACCESS-REQUIRED:{room}' for room in access_rooms)
    for tag,kind,geometry in wall_run_parts((x0,y0),(x1,y1),level.z,height,thickness,openings):
        b.add(f'{run_id}-{tag}',kind,'program','partitions',geometry,partition.material,
              category=zone.category,program=zone.space_type,level_id=level.id,
              lattice_index={'level':level.index,'band':zone.band_index},
              datum_refs=refs,rule_refs=rules,
              reason=(f'{partition.label} at {zone.label}. {requirement.fire_basis} '
                      f'Acoustic target STC {requirement.stc_target}: {requirement.stc_basis}. '
                      f'{partition.assembly}' +
                      (' Required door unresolved: no supported unobstructed approach fits on both sides.'
                       if unresolved else ' Openings follow the selected room access connections.')))
    horizontal = abs(x1-x0) >= abs(y1-y0)
    controlled = requirement.permeability == 'controlled_door'
    for index,opening in enumerate(openings):
        if opening.existing_door_ids:
            continue
        t=opening.at_m/length
        cx,cy=x0+(x1-x0)*t,y0+(y1-y0)*t
        tag='DR' if len(openings)==1 else f'DR{index:02}'
        b.add(_partition_door_id(run_id, tag),'door','program','partitions',
              BoxGeometry(center=v3(cx,cy,opening.threshold_z+opening.height_m/2),
                  size=(v3(opening.width_m,thickness*.5,opening.height_m) if horizontal
                        else v3(thickness*.5,opening.width_m,opening.height_m))),
              'frame_dark' if controlled else 'white',category=zone.category,
              program=zone.space_type,level_id=level.id,
              lattice_index={'level':level.index,'band':zone.band_index},datum_refs=refs,
              rule_refs=['IBC-1010.1.1','ADA-404.2.3']+
                        (['IBC-716'] if requirement.fire_rating_hours>0 else []),
              reason=(f'{"Controlled" if controlled else "Ordinary"} room access door, '
                      f'{opening.width_m*1000:.0f} mm leaf, placed against measured floor '
                      f'and obstacle geometry. {requirement.permeability_basis} '
                      'Operation, opening protective and code clearance remain unverified.'))


def _emit_partitions(b: _Builder, allocation, sprinklered: bool,
                     reserved=(), carve=None) -> None:
    """Plan complete walls first, then choose supported access for enclosed rooms.

    Access is a room/connection requirement. Solid wall runs which do not carry a
    selected connection remain solid; they do not each invent a required door.
    """
    from types import SimpleNamespace as NS
    from .portals import (WallOpening, split_room_edges, matching_entrances,
                          choose_partition_opening, wall_run_parts)
    from .shared_boundaries import split_shared_route_boundary
    lattice,datums=b.lattice,b.datums
    height=max(2.4,datums.value('floor_to_floor_m')-datums.value('slab_thickness_m')-
               PARTITION_HEAD_CLEARANCE_M)
    tall=dict(getattr(carve,'tall_walls_m',None) or {})
    hall=getattr(b,'hall_enclosure',None)
    if hall is not None and hall.status=='review_required':
        for space_id in ('SP-AUDITORIUM','SP-STAGE'):
            tall[space_id]=hall.roof_bottom_z-lattice.occupied[0].z
    for level in lattice.occupied:
        zones=[z for z in allocation.zones if z.level_id==level.id]
        runs,open_edges=[],[]
        for zone,neighbour,edge,coords in split_room_edges(zones):
            if neighbour and {zone.space_type,neighbour.space_type}=={'auditorium','stage'}:
                continue
            other_type=neighbour.space_type if neighbour else 'circulation'
            other_category=neighbour.category if neighbour else 'circulation'
            requirement=required_separation(zone.space_type,other_type,
                category_a=zone.category,category_b=other_category,
                storeys=len(lattice.occupied),sprinklered=sprinklered,
                area_a_m2=zone.area_delivered_m2)
            owners=[zone.space_id]+([neighbour.space_id] if neighbour else [])
            open_pair={zone.category,other_category}<={'public','circulation'}
            if open_pair and requirement.fire_rating_hours==0 and requirement.stc_target<=40:
                open_edges.append((owners,coords))
                continue
            partition=select_partition(requirement,shaft=zone.space_type in ('riser','elevator'))
            boundary_parts = [(coords,False)]
            if neighbour is None and requirement.fire_rating_hours == 0:
                # A named commons/carrier overlap is one public floor, not a
                # second acoustic room at an arbitrary program-box edge. Only
                # that crossing loses its partition. Independent room and fire
                # boundaries retain their original separation requirement.
                boundary_parts = split_shared_route_boundary(
                    lattice,level.id,zone.space_id,coords)
                open_edges.extend((owners,part) for part,shared in boundary_parts if shared)
            clear_runs = [clear for part,shared in boundary_parts if not shared
                          for clear in _clear_of_cores(*part,reserved)]
            if getattr(lattice, 'massing_id', None) == 'MAS-PROGRAM-VOLUME':
                clear_runs = [clipped for clear in clear_runs
                              for clipped in _clear_of_plate_edge(
                                  *clear, level, partition.thickness_mm / 1000)]
            for piece,clear in enumerate(clear_runs):
                x0,y0,x1,y1=clear
                run=NS(id=f'PRG-PRT-{level.id}-{zone.space_id}-{edge}-P{piece:02}',
                    zone=zone,neighbour=neighbour,owners=owners,coords=clear,
                    requirement=requirement,partition=partition,
                    height=max(height,tall.get(zone.space_id,0),
                        tall.get(neighbour.space_id if neighbour else '',0)),
                    openings=matching_entrances(b,level,(x0,y0),(x1,y1),
                                               partition.thickness_mm/1000),access_rooms=[])
                runs.append(run)
        # Candidate doors must see every prospective wall, including one belonging
        # to a later room; otherwise that later wall can close a selected opening.
        virtual={}
        for run in runs:
            x0,y0,x1,y1=run.coords
            virtual[run.id]=[NS(kind=kind,subsystem='partitions',rule_refs=[],
                instances=[NS(id=f'{run.id}-PLAN-{tag}',level_id=level.id,geometry=g)])
                for tag,kind,g in wall_run_parts((x0,y0),(x1,y1),level.z,run.height,
                    run.partition.thickness_mm/1000,run.openings)]
        def candidate_builder(skip=None):
            groups=dict(b.groups)
            for key,family in virtual.items():
                if key!=skip:
                    groups.update({f'{key}-{i}':group for i,group in enumerate(family)})
            return NS(groups=groups,profiles=b.profiles,
                      _portal_geometry_cache=getattr(b,'_portal_geometry_cache',{}))
        open_rooms=set()
        for owners,coords in open_edges:
            if choose_partition_opening(candidate_builder(),level,coords[:2],coords[2:],1.2,.01) is not None:
                open_rooms.update(owners)
        # Feasible connections are selected outward from open circulation. Shared
        # rooms get a door only where it joins a room already reached by this plan.
        candidates=[]
        public=getattr(allocation,'public_circulation',None)
        approaches={path.target_id:path.points[0] for path in getattr(public,'paths',[])
                    if path.level_id==level.id and path.points}
        for run in runs:
            if run.requirement.permeability not in ('door','controlled_door'):
                continue
            priority=1
            at=choose_partition_opening(candidate_builder(run.id),level,
                run.coords[:2],run.coords[2:],DOOR_LEAF_M,run.partition.thickness_mm/1000)
            x0,y0,x1,y1=run.coords
            length=math.hypot(x1-x0,y1-y0)
            tx,ty=(x1-x0)/length,(y1-y0)/length
            half=max(DOOR_LEAF_M,1.2)/2+.02
            for owner in run.owners:
                point=approaches.get(owner)
                if point is None:
                    continue
                along=(point[0]-x0)*tx+(point[1]-y0)*ty
                distance=abs((point[0]-x0)*ty-(point[1]-y0)*tx)
                if (distance>public.clear_width_m/2+public.wall_allowance_m+.01
                        or not half<=along<=length-half):
                    continue
                start=(x0+tx*(along-half),y0+ty*(along-half))
                end=(x0+tx*(along+half),y0+ty*(along+half))
                preferred=choose_partition_opening(candidate_builder(run.id),level,
                    start,end,DOOR_LEAF_M,run.partition.thickness_mm/1000)
                if preferred is not None:
                    at,priority=along-half+preferred,0
                    break
            if at is not None:
                candidates.append((priority,run,at))
        reached=set(open_rooms)
        pending=[(run,at) for _,run,at in sorted(candidates,key=lambda item:item[0])]
        while pending:
            progress=False
            remaining=[]
            for run,at in pending:
                if all(owner in reached for owner in run.owners):
                    continue
                if run.neighbour is None or any(owner in reached for owner in run.owners):
                    run.openings.append(WallOpening(at_m=at,width_m=DOOR_LEAF_M,threshold_z=level.z))
                    reached.update(run.owners)
                    progress=True
                else:
                    remaining.append((run,at))
            if not progress:
                break
            pending=remaining
        # One requirement marker per enclosed room, measured back from final doors.
        # A later furniture or structure collision can still make its selected door
        # unusable; the inspector reports the room, not every unselected wall.
        required={owner for run in runs for owner in run.owners}-open_rooms
        for room in sorted(required):
            host=next((run for run in runs if room in run.owners),None)
            if host is not None:
                host.access_rooms.append(room)
        for run in runs:
            _emit_partition_run(b,run.id,run.partition,run.requirement,level,*run.coords,
                run.height,run.zone,openings=run.openings,access_rooms=run.access_rooms)


def _emit_archetype(b: _Builder, carve) -> None:
    """The archetype's own geometry, per typology.

    This emitter is the promise and `evaluate_archetype` is the audit: the theatre's
    riser tops come from the carve's derived rows and the sightline gate recomputes
    the C-value from the solids; the museum's party wall is built here and the
    enfilade gate measures the portal between the built pieces. The library and the
    pavilion emit nothing -- their archetype is a void, and the voids were already
    entered on the lattice where every other emitter respects them.
    """
    if isinstance(carve, MuseumCarve):
        level = b.lattice.level(carve.level_index)
        slab_id = f'STR-SLB-{level.id}'
        lo, hi = carve.party_lo, carve.party_hi
        middle = (lo + hi) / 2.0
        half = carve.portal_w_m / 2.0
        wall_t = 0.25
        pieces = (('A', lo, middle - half, level.z, level.z + carve.wall_h_m,
                   'partition'),
                  ('B', middle + half, hi, level.z, level.z + carve.wall_h_m,
                   'partition'),
                  ('HD', middle - half, middle + half, level.z + PORTAL_H_M,
                   level.z + carve.wall_h_m, 'partition_head'))
        for tag, run0, run1, wz0, wz1, kind in pieces:
            if run1 - run0 < 0.05 or wz1 - wz0 < 0.05:
                continue
            run_mid = (run0 + run1) / 2.0
            if carve.party_axis == 'y':
                center = v3(carve.party_pos, run_mid, (wz0 + wz1) / 2.0)
                size = v3(wall_t, run1 - run0, wz1 - wz0)
            else:
                center = v3(run_mid, carve.party_pos, (wz0 + wz1) / 2.0)
                size = v3(run1 - run0, wall_t, wz1 - wz0)
            b.add(f'PRG-ENF-{level.id}-{tag}', kind, 'program', 'archetype',
                  BoxGeometry(center=center, size=size),
                  'white_soft', category='public', program='exhibition_foyer',
                  level_id=level.id, lattice_index={'level': level.index},
                  supports=[slab_id],
                  reason=(f'The party wall that makes the galleries a sequence: '
                          f'{carve.portal_w_m:.1f} m portal on the enfilade axis, '
                          f'hanging surface both sides, no glazing. Measured by '
                          f'the ARCH-ENFILADE gate.'))
        return
    if not isinstance(carve, TheatreCarve):
        return
    ground = b.lattice.occupied[0]
    slab_id = f'STR-SLB-{ground.id}'
    hx0, hy0, hx1, hy1 = carve.house
    sx0, sy0, sx1, sy1 = carve.stage
    dx = carve.audience_dx
    mid_y = (hy0 + hy1) / 2.0
    from .room_fixtures import emit_theatre_floor
    emit_theatre_floor(b, carve)

    from .portals import stage_access_plan
    access=stage_access_plan(b,ground,carve)
    if access:
        if not hasattr(b, 'program_zone_cutouts'):
            b.program_zone_cutouts = {}
        # The allocator retains the stage's gross scheduled area.  Its thin emitted
        # analysis zone gives up the same approved access pocket as the physical
        # stage platform, so the stair is not subsequently reported as occupying a
        # room that has already ceded this footprint.
        b.program_zone_cutouts[(ground.id, 'SP-STAGE')] = tuple(
            float(value) for value in access['pocket'].bounds)
    b.add_plate(f'PRG-STG-{ground.id}','stage_platform','program','archetype',
        _rect_ring(sx0+.05,sy0+.05,sx1-.05,sy1-.05),
        ([_rect_ring(*access['pocket'].bounds)] if access else []),
        ground.z,ground.z+carve.focal_h_m,'timber',category='private',program='stage',
        level_id=ground.id,lattice_index={'level':ground.index},supports=[slab_id],
        reason=(f'Stage floor {carve.focal_h_m:.1f} m above the house slab. '
                + ('Its side access pocket is subtracted before emitting the stair and stage arrival platform.'
                   if access else 'Stage access unresolved: no supported side pocket fits.')))
    if access:
        for tag,kind,geometry in access['parts']:
            part_name = ('stage arrival platform'
                         if kind == 'stage_platform' else 'stage access tread')
            b.add(f'PRG-STG-ACCESS-{ground.id}-{tag}',kind,'circulation','stage_access',
                geometry,'timber',category='private',program='stage',level_id=ground.id,
                lattice_index={'level':ground.index},supports=[slab_id],
                rule_refs=['MTA-STAGE-ACCESS-PLANNING'],
                reason=(f'{part_name.capitalize()} {tag}: '
                        f'{access["rise_m"]*1000:.0f} mm rise and '
                        f'{access["tread_m"]*1000:.0f} mm tread planning recipe. '
                        'The doorway remains on the storey floor; steps meet the stage inside '
                        'its carved pocket. Handrails and code applicability require review.'))

    # The one wall between house and stage, carrying the opening. The rated
    # partition a zone pair would normally get is skipped across the proscenium
    # edge; this wall is what stands there instead.
    wall_t = 0.4
    top_z = ground.z + carve.clear_house_m
    hall=getattr(b,'hall_enclosure',None)
    if hall is not None and hall.status=='review_required':
        top_z=hall.roof_bottom_z
    open_w = carve.proscenium_w_m
    open_top = ground.z + min(7.0, carve.clear_stage_m - 1.0)
    yc = mid_y
    pieces = (
        ('S', hy0, yc - open_w / 2.0, ground.z, top_z),
        ('N', yc + open_w / 2.0, hy1, ground.z, top_z),
        ('HD', yc - open_w / 2.0, yc + open_w / 2.0, open_top, top_z),
    )
    for tag, wy0, wy1, wz0, wz1 in pieces:
        if wy1 - wy0 < 0.05 or wz1 - wz0 < 0.05:
            continue
        b.add(f'PRG-PRO-{ground.id}-{tag}', 'proscenium_wall',
              'program', 'archetype',
              BoxGeometry(center=v3(carve.proscenium_x, (wy0 + wy1) / 2.0,
                                    (wz0 + wz1) / 2.0),
                          size=v3(wall_t, wy1 - wy0, wz1 - wz0)),
              'concrete', category='public', program='auditorium',
              level_id=ground.id, lattice_index={'level': ground.index},
              supports=[slab_id],
              reason=(f'Proscenium wall with a {open_w:.1f} m opening: the single '
                      f'place the audience side and the working side meet. Masonry '
                      f'for the same reason the acoustic separation demands it '
                      f'everywhere else on this room.'))


SHELF_RUN_MAX_M = 4.2
SHELF_RUN_MIN_M = 1.2
SHELF_RUN_GAP_M = 0.4
SHELF_CROSS_AISLE_M = 1.5
SHELF_EDGE_CLEARANCE_M = 0.3
SHELF_DEPTH_M = 0.55
SHELF_ROW_PITCH_M = 1.9
SHELF_FIRST_ROW_OFFSET_M = 1.0
SHELF_AISLE_SEARCH_STEP_M = 0.05
SHELF_FIXED_OBSTACLE_CLEARANCE_M = 0.3
# ``usable_floor`` already holds furniture 50 mm off every fixed body.  The
# remaining 250 mm makes the same 300 mm half-body used by navigation at walls,
# columns and doorway reservations; shelf bodies themselves still take the full
# half-body below.
SHELF_REGION_BODY_MARGIN_M = 0.25


def _shelving_run_layout(
    x0: float,
    x1: float,
    *,
    aisle_centre: float | None = None,
) -> list[tuple[float, float]]:
    """Pack shelf runs on both sides of one continuous cross aisle.

    The old 4.2 m run on a 4.6 m module left 0.4 m between every run. Aligned over
    several rows, those sub-body-width gaps turned each row into a wall. This layout
    reserves a 1.5 m physical band through every row first, then fits complete shelf
    assemblies independently into the two remaining bays. Run widths may shorten,
    within the declared furniture convention, so a cross aisle is never the leftover
    error in a module count.
    """

    inner_x0 = x0 + SHELF_EDGE_CLEARANCE_M
    inner_x1 = x1 - SHELF_EDGE_CLEARANCE_M
    if inner_x1 - inner_x0 <= SHELF_CROSS_AISLE_M:
        return []
    aisle_centre = ((inner_x0 + inner_x1) / 2.0
                    if aisle_centre is None else aisle_centre)
    aisle_x0 = aisle_centre - SHELF_CROSS_AISLE_M / 2.0
    aisle_x1 = aisle_centre + SHELF_CROSS_AISLE_M / 2.0
    if aisle_x0 < inner_x0 or aisle_x1 > inner_x1:
        raise ValueError('shelving cross aisle leaves the room edge clearances')

    placements: list[tuple[float, float]] = []
    for bay_x0, bay_x1 in ((inner_x0, aisle_x0), (aisle_x1, inner_x1)):
        bay_width = bay_x1 - bay_x0
        if bay_width < SHELF_RUN_MIN_M:
            continue
        count = max(1, math.ceil(
            (bay_width + SHELF_RUN_GAP_M)
            / (SHELF_RUN_MAX_M + SHELF_RUN_GAP_M)))
        run_width = (bay_width - SHELF_RUN_GAP_M * (count - 1)) / count
        while count > 1 and run_width < SHELF_RUN_MIN_M:
            count -= 1
            run_width = (bay_width - SHELF_RUN_GAP_M * (count - 1)) / count
        run_width = min(SHELF_RUN_MAX_M, run_width)
        used = count * run_width + (count - 1) * SHELF_RUN_GAP_M
        cursor = bay_x0 + (bay_width - used) / 2.0
        placements.extend(
            (cursor + run_width / 2.0 + index * (run_width + SHELF_RUN_GAP_M),
             run_width)
            for index in range(count))
    return placements


def _shelving_cross_aisle_x(
    region,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    row_count: int,
) -> float | None:
    """Find a cross-aisle band clear of the room's emitted fixed obstacles.

    A centre aisle can coincide with a structural column even when the shelves leave
    it open. Search the actual usable region over the complete shelf-row depth and
    return the nearest-to-centre 1.5 m rectangle with a 0.3 m planning-body margin
    from fixed obstacles. Returning ``None`` emits no shelf field, preserving the
    route instead of drawing a knowingly disconnected stack layout.
    """

    half = SHELF_CROSS_AISLE_M / 2.0
    search_half = half + SHELF_FIXED_OBSTACLE_CLEARANCE_M
    low = x0 + SHELF_EDGE_CLEARANCE_M + half
    high = x1 - SHELF_EDGE_CLEARANCE_M - half
    if high < low:
        return None
    first_y = y0 + SHELF_FIRST_ROW_OFFSET_M
    last_y = first_y + (row_count - 1) * SHELF_ROW_PITCH_M
    band_y0 = max(y0 + SHELF_EDGE_CLEARANCE_M, first_y - SHELF_DEPTH_M / 2.0)
    band_y1 = min(y1 - SHELF_EDGE_CLEARANCE_M, last_y + SHELF_DEPTH_M / 2.0)
    if band_y1 <= band_y0:
        return None
    steps = max(1, math.ceil((high - low) / SHELF_AISLE_SEARCH_STEP_M))
    candidates = [low + (high - low) * index / steps
                  for index in range(steps + 1)]
    centre = (x0 + x1) / 2.0
    candidates.sort(key=lambda candidate: (abs(candidate - centre), candidate))
    return next((candidate for candidate in candidates
                 if region.covers(plan_box(
                     candidate - search_half, band_y0,
                     candidate + search_half, band_y1))), None)


def _plan_shelving_field(
    region,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    aisle_x: float | None = None,
) -> tuple[list[tuple[int, int, float, float, float]], list[tuple[int, int]]]:
    """Keep shelf capacity without cutting the walkable floor into pockets.

    A continuous longitudinal cross aisle is necessary but not sufficient on a
    structural grid.  A column in a 1.35 m row aisle consumes that aisle after the
    0.60 m planning body is applied; two shelf rows can then trap an otherwise valid
    strip of floor between adjacent columns.  The former layout produced exactly
    those five-point islands in collection processing and open stacks.

    Candidates are tried in stable row/column order.  A shelf is retained only when
    subtracting its real footprint plus the navigation half-body leaves every
    previously connected component connected.  This normally omits a few runs beside
    columns, forming real door-to-aisle links, while keeping the rest of the field.
    """

    from .navigation import BODY_WIDTH_M, polygons

    row_count = max(1, int((y1 - y0) / SHELF_ROW_PITCH_M))
    if aisle_x is None:
        aisle_x = _shelving_cross_aisle_x(
            region, x0, y0, x1, y1, row_count)
    if aisle_x is None:
        return [], []
    runs = _shelving_run_layout(x0, x1, aisle_centre=aisle_x)
    candidates = [
        (row, column, x, y0 + SHELF_FIRST_ROW_OFFSET_M + row * SHELF_ROW_PITCH_M,
         width)
        for row in range(row_count)
        for column, (x, width) in enumerate(runs)
    ]
    # The 50 mm convention inset is already present on ``region``.  This second
    # inset brings fixed bodies to the same measured 300 mm half-body as free_floor.
    domain = region.buffer(-SHELF_REGION_BODY_MARGIN_M, join_style=2)
    if domain.is_empty:
        return [], [(row, column) for row, column, *_ in candidates]

    kept: list[tuple[int, int, float, float, float]] = []
    omitted: list[tuple[int, int]] = []
    half_body = BODY_WIDTH_M / 2.0
    for row, column, x, y, width in candidates:
        footprint = plan_box(
            x - width / 2.0, y - SHELF_DEPTH_M / 2.0,
            x + width / 2.0, y + SHELF_DEPTH_M / 2.0)
        if not region.covers(footprint):
            omitted.append((row, column))
            continue
        blocked = footprint.buffer(half_body, join_style=2)
        before = polygons(domain)
        remaining = [piece.difference(blocked) for piece in before]
        if any(piece.is_empty or len(polygons(piece)) != 1 for piece in remaining):
            omitted.append((row, column))
            continue
        domain = domain.difference(blocked)
        kept.append((row, column, x, y, width))
    return kept, omitted


def _emit_program(b: _Builder, allocation: ProgramAllocation,
                  sprinklered: bool = True) -> None:
    """Zones come from the allocator, so the plan is a result rather than a drawing."""
    from .room_fixtures import (
        emit_auditorium_seating, emit_service_room, placement_obstacles,
    )
    lattice = b.lattice
    for level in lattice.occupied:
        zones = allocation.zones_on(level.index)
        # The partitions and real doors have already been emitted. All furniture
        # respects their bodies and both doorway approaches, including open rooms.
        forbidden = placement_obstacles(b, level)
        for zi, zone in enumerate(zones):
            x0, y0, x1, y1 = zone.x0, zone.y0, zone.x1, zone.y1
            material = _CATEGORY_MATERIAL[zone.category]
            zone_cutout = getattr(b, 'program_zone_cutouts', {}).get(
                (level.id, zone.space_id))
            if zone_cutout:
                # The access pocket opens through the stage perimeter.  Encoding it
                # as an interior hole would make a self-touching/invalid polygon;
                # subtract it first and serialise the resulting concave boundary.
                zone_plan = orient(
                    plan_box(x0, y0, x1, y1).difference(plan_box(*zone_cutout)),
                    sign=1.0)
                if zone_plan.geom_type != 'Polygon' or zone_plan.is_empty \
                        or not zone_plan.is_valid:
                    raise ValueError(
                        f'{zone.space_id} access pocket did not leave one valid zone polygon')
                zone_geometry = ExtrusionGeometry(
                    boundary=[v2(px, py) for px, py in list(zone_plan.exterior.coords)[:-1]],
                    holes=[[v2(px, py) for px, py in list(ring.coords)[:-1]]
                           for ring in zone_plan.interiors],
                    z_base=level.z, z_top=level.z + 0.11)
            else:
                zone_geometry = BoxGeometry(
                    center=v3((x0 + x1) / 2.0, (y0 + y1) / 2.0,
                              level.z + 0.055),
                    size=v3(x1 - x0, y1 - y0, 0.11))
            b.add(f'PRG-ZON-{level.id}-{zone.space_id}', 'program_zone', 'program',
                  'zones',
                  zone_geometry,
                  material, category=zone.category, program=zone.space_type,
                  level_id=level.id,
                  lattice_index={'level': level.index, 'band': zone.band_index,
                                 'zone': zi},
                  datum_refs=['bay_x_m', 'bay_y_m', 'level_count',
                              'circulation_allowance', *PLATE_DATUMS],
                  rule_refs=['PRG-LIB-CONSTITUTION-001', 'PRG-AREA-ALLOCATION-001'],
                  reason=(f'{zone.label}: {zone.area_delivered_m2:.0f} m2 delivered '
                          f'against {zone.area_required_m2:.0f} m2 briefed '
                          f'({zone.deviation:+.0%}). Laid on the plate as a thin zone so '
                          f'the section stays legible.'
                          + (' Its approved stage-access pocket is omitted from this '
                             'analysis surface while the scheduled gross area remains '
                             'on the allocation record.' if zone_cutout else '')))

            if zone.space_type == 'auditorium':
                emit_auditorium_seating(b, level, zone)
                continue
            if zone.space_type == 'stage':
                continue
            if emit_service_room(b, level, zone, forbidden):
                continue

            region = usable_floor(level, zone, forbidden)

            def place(root_id, kind, x, y, width, depth, facing=1):
                parts = furniture_parts(kind, x, y, level.z, width, depth, facing=facing)
                placed = emit_furniture(b, root_id, kind, parts, level, zone, region)
                if not placed:
                    if not hasattr(b, 'furniture_omissions'):
                        b.furniture_omissions = []
                    b.furniture_omissions.append(root_id)
                return placed

            name = zone.space_type
            if 'stacks' in name or 'collections' in name or 'processing' in name:
                row_count = max(1, int((y1-y0) / SHELF_ROW_PITCH_M))
                aisle_x = _shelving_cross_aisle_x(
                    region, x0, y0, x1, y1, row_count)
                if aisle_x is None:
                    b.furniture_omissions.append(
                        f'PRG-SHF-{level.id}-{zone.space_id}-CROSS-AISLE')
                    shelf_field, topology_omissions = [], []
                else:
                    shelf_field, topology_omissions = _plan_shelving_field(
                        region, x0, y0, x1, y1, aisle_x=aisle_x)
                if not hasattr(b, 'furniture_omissions'):
                    b.furniture_omissions = []
                b.furniture_omissions.extend(
                    f'PRG-SHF-{level.id}-{zone.space_id}-R{row:02d}-C{column:02d}'
                    for row, column in topology_omissions)
                for row, column, x, y, width in shelf_field:
                    place(
                        f'PRG-SHF-{level.id}-{zone.space_id}-R{row:02d}-C{column:02d}',
                        'shelving_run', x, y, width, SHELF_DEPTH_M)
            elif any(word in name for word in
                     ('reading','seminar','cafe','foyer','lobby','periodicals')):
                for r in range(max(1, int((y1-y0)/2.6))):
                    for c in range(max(1, int((x1-x0)/2.9))):
                        x,y = x0+1.7+c*2.9, y0+1.5+r*2.6
                        tag = f'{level.id}-{zone.space_id}-R{r:02d}-C{c:02d}'
                        if place(f'PRG-DSK-{tag}', 'desk', x, y, 1.6, .8):
                            for side in (-1,1):
                                place(f'PRG-SEA-{tag}-{"N" if side > 0 else "S"}',
                                      'seat', x, y+side*.72, .48, .48, side)
            else:
                for c in range(max(1, int((x1-x0)/3.2))):
                    place(f'PRG-DSK-{level.id}-{zone.space_id}-C{c:02d}',
                          'desk', x0+1.8+c*3.2, (y0+y1)/2, 1.4, 2.0)


def _emit_figures(b: _Builder) -> int:
    lattice = b.lattice
    height = b.datums.value('figure_height_m')
    state = 20260829
    placed = 0

    def rnd() -> float:
        nonlocal state
        state = (1103515245 * state + 12345) % (2 ** 31)
        return state / (2 ** 31)

    def place(tag: str, x: float, y: float, z: float, level_id: str) -> None:
        b.add(f'PRG-FIG-{tag}-T', 'figure', 'program', 'scale_reference',
              BoxGeometry(center=v3(x, y, z + height * 0.34),
                          size=v3(0.40, 0.28, height * 0.69)),
              'accent_red', category='public', program='occupant', level_id=level_id,
              datum_refs=['figure_height_m'],
              reason='Scale figure. The reason every other member reads at its true size.')
        b.add(f'PRG-FIG-{tag}-H', 'figure', 'program', 'scale_reference',
              BoxGeometry(center=v3(x, y, z + height * 0.80),
                          size=v3(0.24, 0.24, height * 0.22)),
              'accent_red', category='public', program='occupant', level_id=level_id,
              datum_refs=['figure_height_m'], reason='Scale figure head.')

    for level in lattice.levels[:-1]:
        x0, y0, x1, y1 = _plate_box(level.plate)
        material = plan_polygon(level.plate).difference(
            unary_union([plan_polygon(hole) for hole in level.voids]))
        # The random station was once checked as a point, so a torso centred a few
        # centimetres inside a concave edge still projected outside the building.
        figure_region = material.buffer(-math.hypot(0.40, 0.28) / 2.0,
                                        join_style=2)
        got, tries = 0, 0
        while got < 18 and tries < 500:
            tries += 1
            x, y = x0 + rnd() * (x1 - x0), y0 + rnd() * (y1 - y0)
            if figure_region.is_empty or not figure_region.covers(Point(x, y)):
                continue
            # A figure scattered into the bowl would stand inside the rake's solid;
            # the carved rooms get their scale from the rake and the stage instead.
            if any(cx0 <= x <= cx1 and cy0 <= y <= cy1
                   for cx0, cy0, cx1, cy1 in lattice.carved.get(level.index, ())):
                continue
            place(f'{level.id}-N{got:03d}', x, y, level.z, level.id)
            got += 1
            placed += 1
    for i in range(12):
        place(f'GRD-N{i:03d}', -4.0 + rnd() * 34.0,
              min(p.y for p in lattice.levels[1].plate) - 13.0 - rnd() * 6.0,
              -0.4, 'L00')
        placed += 1
    return placed


def _emit_site(b: _Builder) -> None:
    lattice = b.lattice
    if lattice.site_boundary:
        _emit_bounded_site(b)
        return
    # Grade meets the podium's underside, and the earth goes down past the footings.
    #
    # It used to be a 700 mm slab whose top sat at -0.40: fifty millimetres below the
    # podium, which therefore floated, and 400 mm below the top of every footing, which
    # therefore stood out of the ground. In section that read as a row of blocks
    # balanced on a line rather than a building founded in soil. The depth is what a
    # section needs to show cut earth around a foundation at all.
    plate = lattice.levels[1].plate
    ground_x = (min(point.x for point in plate) + max(point.x for point in plate)) / 2.0
    top = PODIUM_BASE_M
    b.add('SIT-GRD-001', 'site_ground', 'site', 'context',
          BoxGeometry(center=v3(ground_x, 0.0, top - SITE_EARTH_DEPTH_M / 2.0),
                      size=v3(150.0, 130.0, SITE_EARTH_DEPTH_M)),
          'ground', category='context', program='site', level_id='L00',
          reason='Ground. The top is grade at the podium underside and the body reaches '
                 'below the foundations, so a section cuts earth rather than skimming a '
                 'line. Presentation context, not accepted geometry.')
    b.add('SIT-POD-001', 'podium_slab', 'site', 'podium',
          ExtrusionGeometry(boundary=inset(lattice.levels[1].plate, -4.5),
                            z_base=PODIUM_BASE_M, z_top=0.0),
          'concrete', category='context', program='site', level_id='L00',
          reason='Podium under the lifted mass.')
    south = min(p.y for p in lattice.levels[1].plate)
    xs = [p.x for p in lattice.levels[1].plate]
    entry_x = (min(xs) + max(xs)) / 2.0
    # The approach steps belong to the entrance, not to the whole elevation. They
    # spanned forty-six metres at a literal x of 4.0, which put them underneath the
    # accessible ramp once that ramp became a real switchback.
    step_width = min(18.0, (max(xs) - min(xs)) * 0.42)
    for s in range(3):
        b.add(f'SIT-STP-{s:02d}', 'site_step', 'site', 'context',
              BoxGeometry(center=v3(entry_x, south - 4.0 - s * 1.4,
                                    -0.12 - s * 0.14),
                          size=v3(step_width - s * 1.4, 1.4, 0.30)),
              'ground_light', category='context', program='site', level_id='L00',
              reason='Approach step.')


def _emit_bounded_site(b: _Builder) -> None:
    """Parcel -> earth/paving, with floor and arrival ownership kept separate.

    The legacy display plinth and its decorative steps have no site authority.
    Real entry flights still belong to circulation and remain independently checked.
    """
    lattice = b.lattice
    ground, first = lattice.levels[0], lattice.occupied[0]
    base = ground.z + PODIUM_BASE_M
    b.add_plate('SIT-GRD-001', 'site_ground', 'site', 'context',
        lattice.site_boundary, [], base-SITE_EARTH_DEPTH_M, base,
        'ground', category='context', program='site', level_id=ground.id,
        rule_refs=['SITE-PARCEL-BOUNDARY'],
        reason='Earth representation follows the exact brief parcel and ground datum; '
               'soil and grading design remain unverified.')
    # Where the occupied slab meets grade, its plan is not also outdoor paving.
    # Preserve ground beneath genuinely lifted buildings; no subtraction of an
    # upper-floor projection or its cantilever is justified at grade.
    from .plan_regions import _simple_parts, _ring
    claimed = []
    if first.z-b.datums.value('slab_thickness_m') <= ground.z+1e-7:
        occupied = plan_polygon(first.plate).difference(
            unary_union([plan_polygon(hole) for hole in first.voids]))
        occupied = occupied.union(unary_union([
            plan_box(*rect) for rect in _approach_landing_footprints(b.approach,first.id)]))
        claimed.append(occupied)
    arrival = b.approach.get('arrival_assembly')
    if arrival is not None:
        claimed.append(arrival.reserved_footprint(b.approach['entry_point'],
            b.approach['entry_tangent'],b.approach['entry_outward']))
    cuts = [_ring(part.exterior.coords) for part in _simple_parts(unary_union(claimed))]
    b.add_plate('SIT-POD-001', 'podium_slab', 'site', 'podium',
        lattice.site_boundary, cuts, base, ground.z,
        'concrete', category='context', program='site', level_id=ground.id,
        rule_refs=['SITE-PARCEL-BOUNDARY','SITE-WALKING-SURFACE-OWNERSHIP'],
        reason='Outdoor paving within the exact parcel, excluding grade-bearing '
               'occupied floor and the complete authored arrival claim. Entry flights come only '
               'from the Program Volume circulation assembly; no fixed display steps.')


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def compile_building_model_v3(
    features: AudioFeatures, score: ArchitecturalScore, *,
    massing_id: str | None = None, typology: str | None = None,
    grammar_id: str | None = None, cutaway: bool = False,
    site: SiteParameters | None = None,
) -> BuildingModelV3:
    """Compile one building from one score.

    `massing_id`, `typology` and `grammar_id` pin the decisions the score would
    otherwise make for itself. They exist because comparing two recordings is only
    meaningful with the other variables held: asking whether a more repetitive piece
    tightens the mullion module is unanswerable if the repetitive piece also stopped
    being Deconstructivist and started being International Style, because then the two
    elevations do not both have mullions to count. A designer testing variations
    against a fixed facade wants the same control.

    Left as `None` -- the normal path -- the score chooses all three, and the reasoning
    is recorded on `model.selection`.
    """
    # The caller's pins, held before `typology` is resolved against the score's own
    # choice below -- the identity hash needs the pin as given, not the outcome.
    pinned_massing, pinned_typology = massing_id, typology

    # The site is the seam a human takes over. Passing one replaces the proposal;
    # passing none resolves the default and marks every parameter for review.
    site = site or resolve_site()
    datums = compile_datum_set(score)

    # The silhouette is the first decision and it comes from the score alone. It has
    # to: a footprint cannot be chosen after the levels are already standing in one,
    # and leaving it as a module constant is what made fourteen recordings produce
    # fourteen copies of the same thirty-six metre slab.
    massing, chosen_typology, massing_why = select_massing(score)
    if massing_id is not None:
        massing = MASSING_FAMILIES[massing_id]
        massing_why = [f'massing pinned to {massing_id} by the caller']
    typology = typology or chosen_typology
    lattice = build_lattice(datums, massing, cutaway=cutaway)

    # The brief sets how much building there is; everything about *how* that quantity
    # stands -- silhouette, storeys, grain, proportion -- was the score's and stays so.
    # The fit hands back the allocation and the archetype carve along with the
    # lattice it measured them on: the carve wrote its plate removals into that
    # lattice as voids, so allocating again here would carve them twice.
    massing, lattice, allocation, carve, fit_note = _fit_plan_to_brief(
        datums, massing, lattice, typology, cutaway=cutaway)
    massing_why.append(fit_note)

    # The typology's archetype outranks the score's silhouette (decision 0016): a
    # theatre whose house cannot stand on the massing the music chose is not a
    # theatre. Where the carver refused at every plate size the fit could reach, the
    # kit's massing bias -- the silhouette the typology asks for when the music has
    # not been decisive -- is tried in its place, and the swap is recorded on the
    # selection so a reader sees the music's massing and why it was left. A pinned
    # massing is the caller's decision and is not swapped; the refusal stands and is
    # reported. This is the bias's first consumer: it existed unread until the
    # twenty-track audit showed three theatres with no house.
    if isinstance(carve, CarveRefusal) and massing_id is None:
        bias = MASSING_FAMILIES[kit_for(typology).massing_bias]
        if bias.id != massing.id:
            retry = _fit_plan_to_brief(
                datums, bias, build_lattice(datums, bias, cutaway=cutaway), typology,
                cutaway=cutaway)
            if not isinstance(retry[3], CarveRefusal):
                massing_why.append(
                    f'the score\'s {massing.id} could not hold the {typology} '
                    f'archetype ({carve.reason}); the typology\'s bias massing '
                    f'{bias.id} was built instead, so the house exists and the '
                    f'music\'s silhouette is recorded here as the one it lost')
                massing, lattice, allocation, carve, fit_note = retry
                massing_why.append(fit_note)
            else:
                massing_why.append(
                    f'the {typology} archetype refused both the score\'s {massing.id} '
                    f'and the typology\'s bias massing {bias.id} '
                    f'({retry[3].reason}); the rooms it carves are reported unplaced')

    return _compile_from_lattice(
        score=score, datums=datums, lattice=lattice, allocation=allocation,
        carve=carve, typology=typology, massing=massing, massing_why=massing_why,
        site=site, cutaway=cutaway, pinned_massing=pinned_massing,
        pinned_typology=pinned_typology, grammar_id=grammar_id)


def plan_building_systems(*, score, datums, lattice, allocation, carve, typology,
                          massing, massing_why, site, grammar_id=None, system_id=None):
    """Shared pre-emission selection and sizing, usable by PV proposal planning.

    Does not emit members or accept the proposed spatial composition. Site-load
    context is set exactly as in final compilation; callers run this sequentially.
    """
    # The selection runs here and not earlier because the screen is given the building
    # this score actually produced -- its storeys, its height, its clear span -- rather
    # than a canned brief that would ask the same question of every recording.
    from .transfer_structure import required_structural_capabilities
    required_capabilities = required_structural_capabilities(lattice, carve)
    if system_id is not None:
        missing = set(required_capabilities) - set(
            SYSTEM_BUILDABILITY[system_id].compiler_capabilities)
        if missing:
            raise ValueError(
                f'Pinned structural system {system_id} lacks compiler_v3 capability '
                + ', '.join(sorted(missing)) + ' required by this geometry')
    selection, domain = select_project(
        score, datums, lattice, allocation, program_id=kit_for(typology).program_id,
        typology=typology, jurisdiction=to_jurisdiction(site),
        massing=massing, massing_why=massing_why,
        required_capabilities=required_capabilities)

    # The gravity check is the last screen, and it runs here because it is the only one
    # that needs the frame to exist before it can answer. A glulam column that cannot
    # carry 4000 kN over 4.6 m is a correct result, not a bug, and the honest response
    # is to build the next admissible option and say which member refused -- not to
    # crash, and not to draw the timber frame anyway with a steel section inside it.
    # Environmental actions are a property of the place, so they are computed once
    # here and read by every member check. The seismic weight is the gravity load
    # the frame already carries; a real one would use the ASCE 7 12.7.2 effective
    # weight, which this project does not assemble.
    plan_width = max(lattice.plan.width, lattice.plan.depth)
    seismic_weight_kn = (lattice.plan_x_m * lattice.plan_y_m
                         * max(1, len(lattice.occupied)) * 6.0)
    set_site_loads(site_loads.compute(
        site, height_m=max(4.0, lattice.levels[-1].z), width_m=plan_width,
        seismic_weight_kn=seismic_weight_kn,
        structural_system_id=selection.system_id))

    attempts: list[str] = []
    frame = envelope = sizing = governing_occupancy = None
    options = list(selection.ranked_options
                   or [RankedOption(system_id=selection.system_id,
                                    grammar_id=selection.grammar_id, affinity=0.0)])
    if system_id is not None:
        # The caller's structural system goes first and the ranking becomes its
        # fallback; the selection records the pin the way it records a fallback.
        pinned = ([option for option in options if option.system_id == system_id]
                  or [RankedOption(system_id=system_id, grammar_id=selection.grammar_id,
                                   affinity=0.0)])
        options = pinned + [option for option in options if option.system_id != system_id]
    for option in options:
        candidate_frame = FRAME_TECTONICS[
            SYSTEM_BUILDABILITY[option.system_id].frame_tectonic]
        occupancy, trial = _run_sizing(datums, lattice, allocation, candidate_frame)
        if trial.feasible:
            frame, sizing, governing_occupancy = candidate_frame, trial, occupancy
            if attempts or option.system_id != selection.system_id:
                selection = selection.model_copy(update={
                    'system_id': option.system_id, 'grammar_id': option.grammar_id,
                    'frame_tectonic_id': candidate_frame.id,
                    'envelope_tectonic_id': GRAMMAR_ENVELOPE[option.grammar_id],
                    'sizing_fallback': (
                        ('The preferred frame could not be sized: '
                         + '; '.join(attempts[:2])
                         + f'. Built on {option.system_id} instead.')
                        if attempts else
                        f'Structural system pinned to {option.system_id} by the caller.')})
            break
        attempts.append(f'{option.system_id} ({"; ".join(trial.failures[:1])})')

    if sizing is None:
        raise ValueError(
            'no admissible structural system carries this score: ' + '; '.join(attempts))

    if grammar_id is not None:
        selection = selection.model_copy(update={
            'grammar_id': grammar_id,
            'envelope_tectonic_id': GRAMMAR_ENVELOPE[grammar_id],
            'note': selection.note + f' Grammar pinned to {grammar_id} by the '
                                     f'caller, overriding the selection.'})
    envelope = ENVELOPE_TECTONICS[selection.envelope_tectonic_id]
    spec = GRAMMAR_SPECS[selection.grammar_id]
    return dict(selection=selection, domain=domain, frame=frame, envelope=envelope,
                spec=spec, sizing=sizing, governing_occupancy=governing_occupancy,
                seismic_weight_kn=seismic_weight_kn)


def _compile_from_lattice(*, score, datums, lattice, allocation, carve, typology,
                          massing, massing_why, site, cutaway: bool,
                          pinned_massing, pinned_typology, grammar_id,
                          system_id: str | None = None,
                          identity_token: str = '', project_brief=None) -> BuildingModelV3:
    """One shared tail: plan systems, emit members and evaluate the whole model."""
    brief = (project_brief.resolved_spaces() if project_brief is not None
             else brief_for(typology, storeys=len(lattice.occupied)))
    systems = plan_building_systems(
        score=score, datums=datums, lattice=lattice, allocation=allocation,
        carve=carve, typology=typology, massing=massing, massing_why=massing_why,
        site=site, grammar_id=grammar_id, system_id=system_id)
    selection, domain = systems['selection'], systems['domain']
    frame, envelope, spec = systems['frame'], systems['envelope'], systems['spec']
    sizing, governing_occupancy = systems['sizing'], systems['governing_occupancy']
    seismic_weight_kn = systems['seismic_weight_kn']
    # Program Volumes remain the immutable form source.  FacadeControl is resolved
    # downstream, after the score, tectonic and grammar are all known, and attached to
    # a lattice copy so its source digest cannot be changed by facade selection.
    if lattice.program_volume_source_digest:
        lattice = lattice.model_copy(update={
            'facade_control': facade_control_for(lattice, datums, envelope, spec)})
        if project_brief is not None:
            from .facade_control import weather_plane_site_overflow
            overflow = weather_plane_site_overflow(lattice.facade_control,
                                                   project_brief.buildable_shape)
            if any(area > 1e-6 for area in overflow.values()):
                raise ValueError('PV-FACADE-SITE: weather planes leave the setback polygon; '
                                 'revise the upstream massing reserve: ' + str(overflow))
        intent = lattice.circulation_intent
        if (intent is not None and intent.arrival_assembly is not None
                and lattice.facade_control.resolved_offset_m
                > intent.arrival_assembly.facade_allowance_m+1e-7):
            raise ValueError('PV-CIRC-ARRIVAL-FACADE: selected facade exceeds the upstream '
                             'arrival allowance; revise that spatial assembly before emission')

    # The model's identity, and through it the identity of every artifact directory:
    # the GLB, the drawings and the renders are all pathed by `model_id`. It used to be
    # the audio hash alone, which stopped being an identity the day anything else began
    # to shape the building -- a re-run after a compiler change quietly replaced the
    # GLB an older stored run still pointed at, and the same MP3 could not keep two
    # pinned variants side by side. Hashed from everything that decides what gets
    # built: the score (which carries the audio), the compiler version, the caller's
    # pins, and the four selection outcomes. Same inputs, same id, so an identical
    # re-run replaces its own identical output; anything different builds beside it.
    identity_parts = [
        score.score_id, COMPILER_VERSION, compiler_source_fingerprint(),
        f'pins:{pinned_massing or "-"}/{pinned_typology or "-"}'
        f'/{grammar_id or "-"}/cutaway={cutaway}'
        + (f'/system={system_id}' if system_id else ''),
        selection.typology, selection.massing_id,
        selection.system_id, selection.grammar_id,
    ]
    # The existing score-authored path keeps its historical identity byte for byte.
    # A designer-authored geometry contract adds its digest because the same score and
    # downstream selections can legitimately carry several different plate stacks.
    if identity_token:
        identity_parts.insert(3, f'geometry:{identity_token}')
    if project_brief is not None:
        identity_parts.append('brief:' + hashlib.sha256(
            project_brief.model_dump_json().encode('utf-8')).hexdigest())
    identity_seed = '|'.join(identity_parts)
    identity = hashlib.sha256(identity_seed.encode('utf-8')).hexdigest()[:12]

    def assemble(opacity_override: float | None) -> BuildingModelV3:
        return _assemble(
            model_id=f'building-v3-{identity}',
            score=score, datums=datums, lattice=lattice,
            allocation=allocation, selection=selection, frame=frame,
            envelope=envelope, spec=spec, sizing=sizing,
            governing_occupancy=governing_occupancy,
            opacity_override=opacity_override,
            sprinklered=bool(site.sprinklered.value), carve=carve)

    # Build, check the result against the grammar's own guide, and re-emit
    # once if the failure has a single unambiguous fix. Anything else is
    # reported and shipped, because a compiler that guesses at what a
    # designer meant is more dangerous than one that says what is wrong.
    model = assemble(None)
    report = evaluate(model)
    correction = correction_for(report)
    if correction is not None:
        target_opening, note = correction
        model = assemble(1.0 - target_opening)
        report = evaluate(model)
        report.corrected = note
    model.facade_gates = report
    # The two reports that say whether this is a building rather than a diagram of
    # one: what the constitution requires and whether everyone can get out.
    model.site = site
    model.project_brief = project_brief
    model.site_loads = site_loads.compute(
        site, height_m=max(4.0, lattice.levels[-1].z),
        width_m=max(lattice.plan.width, lattice.plan.depth),
        seismic_weight_kn=seismic_weight_kn,
        structural_system_id=selection.system_id)
    model.constitution = validate_model(typology, brief, model)
    model.portals = inspect_portals(model)
    model.room_layouts = inspect_room_layouts(model)
    model.life_safety = life_safety_graph(
        model, brief, typology=typology, sprinklered=bool(site.sprinklered.value))
    # The spatial rules go here with the other post-assembly reports. They need every
    # element in place, and leaving them in a script would mean the constraint exists
    # only while somebody is looking -- which is the situation they were written to end.
    model.spatial = check_spatial_rules(model)
    # What the archetype promised, measured back off the geometry that was built:
    # sightlines row by row, the claimed plate removals, columns in the bowl, front
    # of house against the stage wall. None on typologies without an archetype.
    model.archetype = evaluate_archetype(model, carve, typology)
    return model


def _assemble(*, model_id, score, datums, lattice, allocation, selection, frame,
              envelope, spec, sizing, governing_occupancy,
              opacity_override, sprinklered: bool = True,
              carve=None) -> BuildingModelV3:
    """Emit every layer and package the result. Called twice at most."""
    builder = _Builder(datums, lattice)
    builder.program_allocation = allocation
    _emit_site(builder)
    _emit_structure(builder, sizing, frame, governing_occupancy, carve=carve)
    from .hall_enclosure import emit_hall
    emit_hall(builder)
    _emit_roof(builder)
    _emit_envelope(builder, envelope, spec, opacity_override)
    _emit_circulation(builder)
    _emit_archetype(builder, carve)
    # The theatre's stage-access stair is emitted with the archetype. Annotate after
    # it exists so every Program Volume circulation part reaches the same assembly
    # and detail-section contract.
    from .assembly_metadata import annotate_program_volume_circulation
    annotate_program_volume_circulation(builder)
    _emit_partitions(builder, allocation, sprinklered=sprinklered,
                     reserved=core_reservations(lattice, datums), carve=carve)
    from .hall_enclosure import inspect_hall
    inspect_hall(builder)
    _emit_program(builder, allocation, sprinklered=sprinklered)
    _emit_figures(builder)

    groups = list(builder.groups.values())
    # Resolve the centre-line skeleton before the dependency graph is compiled, so the
    # two agree on what a joint is. The graph answers "does every element name a host";
    # the skeleton answers "do the members that name each other actually meet", which
    # is the question a nearest-centroid rule cannot ask.
    builder.axis.finalise()
    dependency_graph = compile_dependency_graph(groups)
    axis_report = _record_axis_checks(builder)
    counts: dict[str, int] = {}
    layers: dict[str, int] = {}
    for group in groups:
        size = len(group.instances)
        counts[group.kind] = counts.get(group.kind, 0) + size
        layers[group.semantic_layer] = layers.get(group.semantic_layer, 0) + size

    records = []
    for role, sized in (('secondary_joist', sizing.joist),
                        ('primary_beam', sizing.beam),
                        ('column', sizing.column)):
        check = sized.check
        if check is None:
            continue
        records.append(MemberSizingRecord(
            role=role, section_id=check.section_id, material_id=check.material_id,
            span_m=check.span_m, tributary_width_m=check.tributary_width_m,
            governing_check=check.governing, utilisation=check.max_ratio,
            load_combination=check.load.combination,
            factored_load_kn_m=check.load.factored_kn_m,
            element_count=counts.get(role, 0), assumptions=check.assumptions))

    model = BuildingModelV3(
        model_id=model_id,
        score_id=score.score_id, typology=selection.typology,
        tectonic_system=frame.id,
        structural_system_id=selection.system_id,
        facade_grammar_id=selection.grammar_id,
        envelope_tectonic_id=envelope.id,
        selection=selection,
        datum_set=datums, lattice=lattice, program_allocation=allocation,
        profiles=builder.profiles,
        sizing=records, element_groups=groups,
        dependency_graph=dependency_graph,
        axis_report=axis_report,
        spatial=None,
        room_layout_plan=builder.room_layout_plan,
        transfer_structure=getattr(builder, 'transfer_structure', None),
        materials={key: MATERIAL_LIBRARY[key]
                   for key in sorted({group.material_profile
                                      for group in groups})
                   if key in MATERIAL_LIBRARY},
        accessible_route=builder.accessible_route,
        accessible_route_unresolved=builder.unresolved_accessible_route,
        circulation_plan=builder.circulation_plan,
        element_counts=dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        layer_counts=layers,
        limitations=[
            *builder.world_xy_frame_notes,
            *([f'Furniture: {len(builder.furniture_omissions)} candidate assemblies '
               'were not placed because their complete footprint or floor bearing did '
               'not fit. No partial furniture was emitted. First IDs: '
               + ', '.join(builder.furniture_omissions[:8]) + '.']
              if builder.furniture_omissions else []),
            f'{datums.coverage:.0%} of datums are score-driven; the rest are declared '
            f'design fixtures waiting on ' + ', '.join(datums.waiting_on) + '.',
            (f'Program: {allocation.delivered_area_m2:.0f} m2 delivered against '
             f'{allocation.required_area_m2:.0f} m2 briefed '
             f'({allocation.fulfilment:.0%}); '
             + ('every space fits.' if allocation.fits else
                'unplaced: ' + ', '.join(u.label for u in allocation.unplaced) + '.')
             + ''.join(f" Zone '{report.label}' on {report.level_id}: "
                       f'{report.area_delivered_m2:.0f} m2 delivered of '
                       f'{report.area_required_m2:.0f} m2 asked in '
                       f'{report.area_usable_m2:.0f} m2 usable '
                       f'({report.area_rows_m2:.0f} m2 in whole rows)'
                       + (f" (not fitted: {', '.join(report.unplaced)})" if report.unplaced else '')
                       + '.' for report in allocation.zone_reports)),
            (f'Regular frame sized for {governing_occupancy.label} at '
             f'{governing_occupancy.live_kpa:.2f} kPa, the heaviest allocated room; the '
             f'column stack sums the real per-level loads.'),
            *([f'Circulation: no single stair core lies inside every plate, so '
               f'{", ".join(builder.unreached_levels)} have no emitted stair route. '
               f'Circulation remains unresolved on those levels.']
              if builder.unreached_levels else []),
            *([builder.unresolved_accessible_route]
              if builder.unresolved_accessible_route else []),
            builder.lift_note,
            (f'Stair and lift openings: the slab and ceiling are cut, the joists that '
             f'met an opening are trimmed to it, and {builder.headers_emitted} header '
             f'beams and {builder.trimmers_emitted} trimmer joists were sized for the '
             f'load they collect. '
             + (f'{len(_core_rects(builder.cores))} stair cores are reinforced-concrete '
                f'walls from a footing to the roof; '
                + ('the World XY grid remains independent, '
                   if lattice.world_xy_grid is not None else 'the grid is drawn to their faces, ')
                +
                f'no member is framed inside them, and the framing that meets a face '
                f'bears on the wall. The walls are screened as bearing walls; '
                f'reinforcement, in-plane shear and the lateral role are not designed. '
                if _core_rects(builder.cores) else '')
             + (f'{len(builder.opening_conflicts)} members still cross an opening or '
                f'found no section and are kept for review: '
                f'{", ".join(builder.opening_conflicts[:6])}'
                + (', …' if len(builder.opening_conflicts) > 6 else '') + '. '
                if builder.opening_conflicts else
                'No girder crosses an opening. ')
             + (f'Flat-slab levels {", ".join(builder.unframed_levels)} have openings '
                f'with no edge reinforcement designed. '
                if builder.unframed_levels else '')
             + 'Connections at the headers are not designed.'),
            *([f'Accessible approach: {len(builder.accessible_route.runs)} ramp '
               f'runs at 1:'
               f'{1 / builder.accessible_route.steepest_slope:.0f} with '
               f'{len(builder.accessible_route.landings)} landings, checked against '
               + '; '.join(builder.accessible_route.citations[:3]) + '.']
              if builder.accessible_route else []),
            'Gravity only. No wind, seismic, snow, or notional lateral load.',
            'Roof truss, envelope, circulation, and furniture members are dimensioned '
            'by architectural convention. Only members explicitly marked '
            'sized_by_calculation carry a section governed by the recorded load calculation; '
            'boundary-station conventions do not inherit that claim.',
            ('Connection topology is explicit and graph-checked; connection plates, '
             'bolts, welds, anchors, fasteners and capacities are not designed. Fire '
             'protection, camber, vibration and lateral-torsional buckling remain '
             'unchecked. Every element remains professional_review_required.'),
            (f'System and grammar: {selection.system_id} with '
             f'{selection.grammar_id}. ' + selection.note),
            *([selection.sizing_fallback] if selection.sizing_fallback else []),
            *([f'The music preferred {selection.preferred_grammar_id} on '
               f'{selection.preferred_system_id}; the screen overruled it. '
               f'{selection.overrule_reason}']
              if selection.overruled_by_screen else []),
            ('Six of the ten structural systems are not emitted by this compiler and '
             'were screened out rather than approximated: '
             + '; '.join(f'{k} ({v.split(".")[0]})'
                         for k, v in sorted(selection.unbuildable_systems.items()))
             + '.'),
        ])
    # Portal passability is a reading of the completed emitted model.  Resolve the
    # Program Volume circulation chain only after those real door leaves, walking
    # surfaces and obstructions exist, so a compliant ramp cannot silently stand in
    # for a route that still ends at a closed facade.
    model.portals = inspect_portals(model)
    builder.circulation_plan = _resolve_program_circulation(
        builder, portal_report=model.portals, model=model)
    model.circulation_plan = builder.circulation_plan
    return model
