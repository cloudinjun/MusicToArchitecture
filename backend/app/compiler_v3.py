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

from .datums import (
    DatumSet, Lattice, build_lattice, compile_datum_set,
)
from .grammar_specs import GRAMMAR_SPECS, GrammarSpec
from .ada import (
    CURB_HEIGHT_M, HANDRAIL_EXTENSION_M, MAX_RUN_RISE_M, MIN_CLEAR_WIDTH_M,
    MIN_LANDING_LENGTH_M, MIN_TURN_LANDING_M, RAMP_THICKNESS_M, RampPlan,
    plan_switchback_ramp,
)
from .geometry import (
    BoxGeometry, CONVENTION_PROFILES, ExtrusionGeometry, MemberGeometry,
    ProfileSpec, Vector2, Vector3, bounds, convention_profile, inset, point_inside,
    profile_from_section_id, v2, v3,
)
from .loads import OCCUPANCY_LIVE, composite_steel_deck, flat_roof_assembly
from .massing import MASSING_FAMILIES
from .spatial_rules import check_spatial_rules
from .materials import MATERIALS as MATERIAL_LIBRARY
from .models import ArchitecturalScore, AudioFeatures
from .models_v3 import (
    BuildingModelV3, ElementGroup, ElementInstance, MemberSizingRecord, RankedOption,
)
from .axis import AxisSkeleton
from .envelope import emit_envelope
from .dependencies import (
    EXTRA_FLIGHT_PAIRS, SECOND_FLIGHT_PAIR, compile_dependency_graph,
)
from .constitution import validate_model
from .facade_gates import correction_for, evaluate
from .life_safety import build as life_safety_graph
from .archetypes import (
    C_VALUE_DESIGN_M, CarveRefusal, TheatreCarve, carve_for, evaluate_archetype,
)
from .briefs import brief_for
from .typology import kit_for
from .program import (
    DEFAULT_CIRCULATION_ALLOWANCE, LIBRARY_BRIEF, ProgramAllocation,
    UnplacedSpace, allocate_program, level_bands,
)
from .registry import catalogue, profile_for
from .partitions import (
    DOOR_CLEAR_M, DOOR_LEAF_M, required_separation, select_partition,
)
from .selection import select_massing, select_project
from .site import SiteParameters, resolve_site, to_jurisdiction
from .version import COMPILER_VERSION
from . import site_loads
from .validators import set_site_loads
from .sizing import size_gravity_frame
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
APRON_DEPTH_M = 21.0

PLATE_DATUMS = ('cantilever_m', 'plate_step_m', 'plate_rotation_deg', 'apse_radius_m')

class _Builder:
    """Accumulates elements and keeps the datum references honest."""

    def __init__(self, datums: DatumSet, lattice: Lattice) -> None:
        self.datums = datums
        self.lattice = lattice
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
        # Where the second egress stair landed, if one was placed. A plan
        # too small to hold two remote cores does not get a second one.
        self.second_stair_anchor: tuple[float, float] | None = None
        self.second_stair_levels: list[str] = []

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
    ) -> str:
        if element_id in self.element_ids:
            raise ValueError(f'duplicate element id: {element_id}')
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
            supports=list(supports)))
        if isinstance(geometry, MemberGeometry):
            self.axis.segment(element_id, list(geometry.path), subsystem)
            for support_id in supports:
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

    # Does the frame get to the ground along its own centre-lines, with no plate in
    # the path? Columns, girders, joists and bracing should; a truss bearing on the
    # roof plate legitimately should not, and is not asked to.
    frame_kinds = {'column', 'piloti_column', 'primary_beam', 'secondary_joist',
                   'heavy_joist', 'brace', 'knee_brace', 'outrigger_strut'}
    linked = b.axis.connections()
    reached = {owner for owner in linked
               if b.element_kinds.get(owner) in ('footing', 'piloti_column')}
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
        if b.element_kinds.get(owner) in {'stair_stringer', 'entry_canopy'})
    unexplained = sorted(set(isolated) - set(plate_borne))
    checks = [
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
                     f'{len(plate_borne)} that bear on a plate, which carries no axis.'
                     if not unexplained else
                     'Some members share no node with any other member and do not bear '
                     'on a plate.'),
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
        bay_x_m=datums.value('bay_x_m'), bay_y_m=datums.value('bay_y_m'),
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

def _emit_structure(b: _Builder, sizing, frame: FrameTectonic) -> None:
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
    lattice, datums = b.lattice, b.datums
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

    # The section the calculation chose already carries the material's proportion --
    # a glulam catalogue returns a member far wider than a rolled steel one at the
    # same capacity -- so the drawn member needs no correction factor on top of it.
    col_mat = frame.column_material
    beam_mat = frame.beam_material
    joist_mat = 'steel_light' if frame.column_material == 'steel_white' else frame.beam_material

    fascia = 'FASCIA-200x550'
    strut = 'STRUT-CHS180'

    # --- columns and footings: node (i, j, k) -> (i, j, k+1) --------------------
    for xi, x in enumerate(lattice.x_lines):
        for yj, y in enumerate(lattice.y_lines):
            for k in range(len(lattice.levels) - 1):
                lower, upper = lattice.levels[k], lattice.levels[k + 1]
                # STF-INV-02: a column exists only where every plate from the first
                # occupied level up to the one it supports contains the node, so the
                # stack is continuous by construction rather than by inspection.
                if not all(point_inside(lattice.levels[j].plate, x, y)
                           for j in range(1, k + 2)):
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
                b.add(
                    f'STR-{"PIL" if is_piloti else "COL"}-X{xi:02d}-Y{yj:02d}-{lower.id}',
                    'piloti_column' if is_piloti else 'column', 'structure', 'columns',
                    b.member([v3(x, y, lower.z), v3(x, y, upper.z)],
                             piloti_profile if is_piloti else column_profile),
                    col_mat, category='service' if y > 6.0 else 'public',
                    level_id=lower.id, lattice_index=index,
                     datum_refs=['bay_x_m', 'bay_y_m', 'floor_to_floor_m',
                                 'ground_open_height_m' if is_piloti else 'floor_to_floor_m'],
                    supports=[support_id],
                    section_id=sizing.column.check.section_id,
                    sizing_status='sized_by_calculation', utilisation=col_util,
                    governing_check=col_gov,
                    rule_refs=['STR-STEEL-GRAVITY-001', 'STF-INV-01'],
                    reason=('Column carries the tributary bay from every level above to '
                            'a footing through an explicit node chain.'))

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
        # --- primary beams, both grid directions --------------------------------
        for yj, y in enumerate(lattice.y_lines):
            for xi in range(len(lattice.x_lines) - 1):
                x0, x1 = lattice.x_lines[xi], lattice.x_lines[xi + 1]
                if not point_inside(plate, (x0 + x1) / 2.0, y):
                    continue
                beam_supports = [column_below(level, xi, yj),
                                 column_below(level, xi + 1, yj)]
                if not all(support in b.element_ids for support in beam_supports):
                    continue
                b.add(f'STR-BMX-X{xi:02d}-Y{yj:02d}-{level.id}', 'primary_beam',
                      'structure', 'beams',
                      b.member([v3(x0, y, z_beam), v3(x1, y, z_beam)], girder_profile),
                      beam_mat, level_id=level.id,
                      lattice_index={'x': xi, 'y': yj, 'level': level.index},
                      datum_refs=['bay_x_m'],
                      supports=beam_supports,
                      section_id=sizing.beam.check.section_id,
                      sizing_status='sized_by_calculation', utilisation=gir_util,
                      governing_check=gir_gov, rule_refs=['STR-STEEL-GRAVITY-001'],
                      reason='Primary girder spans one bay between column nodes.')
        for xi, x in enumerate(lattice.x_lines):
            for yj in range(len(lattice.y_lines) - 1):
                y0, y1 = lattice.y_lines[yj], lattice.y_lines[yj + 1]
                if not point_inside(plate, x, (y0 + y1) / 2.0):
                    continue
                beam_supports = [column_below(level, xi, yj),
                                 column_below(level, xi, yj + 1)]
                if not all(support in b.element_ids for support in beam_supports):
                    continue
                b.add(f'STR-BMY-X{xi:02d}-Y{yj:02d}-{level.id}', 'primary_beam',
                      'structure', 'beams',
                      b.member([v3(x, y0, z_beam), v3(x, y1, z_beam)], girder_profile),
                      beam_mat, level_id=level.id,
                      lattice_index={'x': xi, 'y': yj, 'level': level.index},
                      datum_refs=['bay_y_m'],
                      supports=beam_supports,
                      section_id=sizing.beam.check.section_id,
                      sizing_status='sized_by_calculation', utilisation=gir_util,
                      governing_check=gir_gov, rule_refs=['STR-STEEL-GRAVITY-001'],
                      reason='Primary girder closes the bay in the second direction.')
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

        # --- the floor system, which is where the families separate -------------
        z_joist = level.z - slab_t - 0.17
        spacing = datums.value('joist_spacing_m')
        if frame.floor_system in ('joisted', 'heavy_joist'):
            # A heavy timber floor carries fewer, deeper joists at a wider centre than
            # a steel deck: the same load through a material that is weaker per unit
            # area but available in larger sections.
            heavy = frame.floor_system == 'heavy_joist'
            spacing = spacing * (1.9 if heavy else 1.0)
            kind = 'heavy_joist' if heavy else 'secondary_joist'
            for xi in range(len(lattice.x_lines) - 1):
                x0, x1 = lattice.x_lines[xi], lattice.x_lines[xi + 1]
                divisions = max(1, int(round((x1 - x0) / spacing)))
                for sub in range(1, divisions):
                    x = x0 + (x1 - x0) * sub / divisions
                    for yj in range(len(lattice.y_lines) - 1):
                        y0, y1 = lattice.y_lines[yj], lattice.y_lines[yj + 1]
                        if not point_inside(plate, x, (y0 + y1) / 2.0):
                            continue
                        joist_supports = [
                            f'STR-BMX-X{xi:02d}-Y{yj:02d}-{level.id}',
                            f'STR-BMX-X{xi:02d}-Y{yj + 1:02d}-{level.id}',
                        ]
                        if not all(support in b.element_ids for support in joist_supports):
                            continue
                        b.add(f'STR-JST-X{xi:02d}-S{sub:02d}-Y{yj:02d}-{level.id}',
                              kind, 'structure', 'beams',
                              b.member([v3(x, y0, z_joist), v3(x, y1, z_joist)],
                                       joist_profile),
                              joist_mat, level_id=level.id,
                              lattice_index={'x': xi, 'sub': sub, 'y': yj,
                                             'level': level.index},
                              datum_refs=['joist_spacing_m', 'bay_y_m'],
                              supports=joist_supports,
                              section_id=sizing.joist.check.section_id,
                              sizing_status='sized_by_calculation', utilisation=jst_util,
                              governing_check=jst_gov,
                              rule_refs=['STR-STEEL-GRAVITY-001', 'STF-INV-04'],
                              reason='Secondary member spans between primary girders at '
                                     'the density the score and the material set.')
        elif frame.floor_system == 'panel':
            # CLT bands span girder to girder. They are drawn, not implied, because a
            # panel floor reads completely differently from a ribbed one in section --
            # and they are recorded as convention, because no panel check was run.
            for xi in range(len(lattice.x_lines) - 1):
                x0, x1 = lattice.x_lines[xi], lattice.x_lines[xi + 1]
                bands = max(1, int(round((x1 - x0) / 2.4)))
                for band in range(bands):
                    xa = x0 + (x1 - x0) * band / bands
                    xb = x0 + (x1 - x0) * (band + 1) / bands
                    for yj in range(len(lattice.y_lines) - 1):
                        y0, y1 = lattice.y_lines[yj], lattice.y_lines[yj + 1]
                        if not point_inside(plate, (xa + xb) / 2.0, (y0 + y1) / 2.0):
                            continue
                        panel_supports = [
                            f'STR-BMX-X{xi:02d}-Y{yj:02d}-{level.id}',
                            f'STR-BMX-X{xi:02d}-Y{yj + 1:02d}-{level.id}',
                        ]
                        if not all(support in b.element_ids for support in panel_supports):
                            continue
                        b.add(f'STR-CLT-X{xi:02d}-B{band:02d}-Y{yj:02d}-{level.id}',
                              'clt_panel', 'structure', 'floor_panels',
                              BoxGeometry(
                                  center=v3((xa + xb) / 2.0, (y0 + y1) / 2.0,
                                            z_joist + 0.05),
                                  size=v3((xb - xa) * 0.97, (y1 - y0) * 0.99,
                                          slab_t * frame.slab_thickness_factor)),
                              beam_mat, level_id=level.id,
                              lattice_index={'x': xi, 'sub': band, 'y': yj,
                                             'level': level.index},
                              datum_refs=['bay_y_m', 'slab_thickness_m'],
                              supports=panel_supports,
                              rule_refs=['STR-TIMBER-FLOOR-001'],
                              reason='CLT band spanning girder to girder. No panel '
                                     'bending check is implemented, so this is carried '
                                     'as convention and says so.')
        else:
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
        floor_support_kinds = (
            [kind] if frame.floor_system in ('joisted', 'heavy_joist') else
            ['clt_panel'] if frame.floor_system == 'panel' else ['drop_panel'])
        floor_supports = b.ids(kinds=floor_support_kinds, level_id=level.id)
        if not floor_supports:
            floor_supports = b.ids(kinds=['primary_beam'], level_id=level.id)
        slab_id = f'STR-SLB-{level.id}'
        b.add(slab_id, 'floor_slab', 'structure', 'slabs',
              ExtrusionGeometry(boundary=inset(plate, 0.0),
                                holes=[list(hole) for hole in level.voids],
                                z_base=round(level.z - slab_t, 4), z_top=level.z),
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
            b.add(f'ARC-CLG-{level.id}', 'ceiling', 'program', 'finishes',
                  ExtrusionGeometry(boundary=inset(plate, 0.15),
                                    holes=ceiling_holes,
                                    z_base=round(ceiling_z - CEILING_THICKNESS_M, 4),
                                    z_top=round(ceiling_z, 4)),
                  'white', category='public', program='ceiling', level_id=level.id,
                  lattice_index={'level': level.index},
                  datum_refs=['floor_to_floor_m', 'slab_thickness_m', *PLATE_DATUMS],
                  supports=[slab_id],
                  thickness_m=CEILING_THICKNESS_M,
                  reason='Suspended ceiling at the head height the partitions run to. '
                         'The zone above it carries the structure and the services; '
                         'the two together are what a section reads as a floor.')
        fascia_depth = datums.value('edge_fascia_m')
        for ei in range(len(plate)):
            a, c = plate[ei], plate[(ei + 1) % len(plate)]
            b.add(f'STR-FAS-{level.id}-E{ei:03d}', 'slab_fascia', 'structure', 'slabs',
                  b.member([v3(a.x, a.y, level.z - fascia_depth / 2.0),
                            v3(c.x, c.y, level.z - fascia_depth / 2.0)], fascia),
                  'white', level_id=level.id,
                  lattice_index={'level': level.index, 'edge': ei},
                  datum_refs=['edge_fascia_m', *PLATE_DATUMS],
                  supports=[slab_id],
                  reason='Thickened plate edge; the line a study model actually reads.')

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
        for yj in range(len(lattice.y_lines) - 1, -1, -1):
            usable = [
                xi for xi in braced
                if f'STR-{prefix}-X{xi:02d}-Y{yj:02d}-{lower_id}' in b.element_ids
                and f'STR-{prefix}-X{xi + 1:02d}-Y{yj:02d}-{lower_id}' in b.element_ids]
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
                  b.member([v3(x, y_edge, fascia_z),
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
                     (b.axis.nearest_owner(v3(x, y_edge, fascia_z),
                                           f'STR-FAS-{level.id}-'),) if fid],
                  rule_refs=['STR-STEEL-GRAVITY-001'],
                  reason='Raker propping the cantilevered plate edge back to the column '
                         'below. Both ends land on a member that exists; the previous '
                         'strut ended in mid-air and named the slab as its support.')


def _vertical_plate_span(plate: list[Vector2], x: float) -> tuple[float, float] | None:
    """Return the longest inside segment cut by a vertical registered line."""

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
    return max(inside, key=lambda span: span[1] - span[0]) if inside else None


def _roof_truss_lines(lattice: Lattice) -> list[tuple[str, float, float, float, dict[str, int]]]:
    """Choose at least two truss lines from the roof plate registration geometry.

    A stepped or rotated upper plate can move entirely between the base-building grid
    lines.  In that case the roof receives its own two-line sub-grid, positioned as
    fractions of the roof bounds and indexed as ``roof_x``.  This prevents a roof deck
    from being emitted over a single truss with no purlins.
    """

    roof = lattice.roof
    registered: list[tuple[str, float, float, float, dict[str, int]]] = []
    for xi, x in enumerate(lattice.x_lines):
        span = _vertical_plate_span(roof.plate, x)
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
        span = _vertical_plate_span(roof.plate, x)
        if span:
            candidates.append((x, span[0], span[1]))
    if len(candidates) < 2:
        raise ValueError('Roof plate cannot register two complete truss support lines.')
    selected = (candidates[0], candidates[-1])
    return [(f'R{index:02d}', x, y0, y1,
             {'roof_x': index, 'level': roof.index})
            for index, (x, y0, y1) in enumerate(selected)]


def _emit_roof(b: _Builder) -> None:
    lattice, datums = b.lattice, b.datums
    roof = lattice.roof
    depth = datums.value('truss_depth_m')
    panels = max(3, datums.integer('truss_panels'))
    z_bot, z_top = roof.z, roof.z + depth
    lines = _roof_truss_lines(lattice)

    for token, x, y0, y1, lattice_index in lines:
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
                  rule_refs=['STR-STEEL-GRAVITY-001'],
                  reason='Roof truss chord. Truss members are dimensioned by convention; '
                         'no truss analysis is implemented.')
        for p in range(panels + 1):
            y = y0 + panel * p
            b.add(f'STR-TWB-{token}-P{p:02d}-V', 'truss_web', 'structure',
                  'roof_truss',
                  b.member([v3(x, y, z_bot), v3(x, y, z_top)], 'TRUSSWEB-130'),
                  'steel_white', level_id=roof.id,
                  lattice_index={**lattice_index, 'panel': p},
                  datum_refs=['truss_panels'],
                  supports=[f'STR-TCH-{token}-B'],
                  reason='Truss vertical at a panel point.')
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
                      reason='Warren diagonal; handedness alternates panel to panel.')
    covered_purlins: list[str] = []
    for p in range(panels + 1):
        for i in range(len(lines) - 1):
            left, right = lines[i], lines[i + 1]
            left_y = left[2] + (left[3] - left[2]) * p / panels
            right_y = right[2] + (right[3] - right[2]) * p / panels
            b.add(f'STR-PRL-P{p:02d}-B{i:02d}', 'purlin', 'structure', 'roof_truss',
                  b.member([v3(left[1], left_y, z_top),
                            v3(right[1], right_y, z_top)],
                           'PURLIN-120x200'),
                  'steel_light', level_id=roof.id,
                  lattice_index={'panel': p, 'bay': i, 'level': roof.index},
                  datum_refs=['truss_panels'],
                  supports=[f'STR-TCH-{left[0]}-T', f'STR-TCH-{right[0]}-T'],
                  reason='Purlin spans between trusses on the top chord.')
            # The deck stops 1.4 m short of the plate, so the end panels' purlins run
            # out beyond it. Declaring every purlin as a deck support named several the
            # deck does not reach.
            if point_inside(inset(roof.plate, 1.4),
                            (left[1] + right[1]) / 2.0, (left_y + right_y) / 2.0):
                covered_purlins.append(f'STR-PRL-P{p:02d}-B{i:02d}')
    # The deck stops short of the plate edge: the truss zone below oversails it. The
    # parapet ring has to stand on this boundary rather than on the plate's, which is
    # where it used to be drawn -- 1.4 m outboard of the deck, over the eaves, on
    # nothing. Lowering it onto the deck level fixed the height and left the ring
    # hanging in plan, which is why the same defect survived one repair.
    deck_plate = inset(roof.plate, 1.4)
    b.add('ENV-DECK-ROOF', 'roof_deck', 'envelope', 'roof',
          ExtrusionGeometry(boundary=deck_plate,
                            z_base=round(z_top + 0.08, 4), z_top=round(z_top + 0.26, 4)),
          'white', level_id=roof.id, datum_refs=['truss_depth_m'],
          supports=covered_purlins,
          reason='Roof deck closes the envelope over the truss zone.')
    # A parapet is an upstand off the roof surface, not a rail above it. Drawn as a
    # 260 mm cap centred 450 mm over the deck, its underside cleared the roof by
    # 320 mm and the ring read in every render as a line floating around the roof
    # edge. Same cap level, but the section now runs down to the deck it stands on.
    deck_top = z_top + 0.26
    par_z = deck_top + PARAPET_UPSTAND_M / 2.0
    for ei in range(len(deck_plate)):
        a, c = deck_plate[ei], deck_plate[(ei + 1) % len(deck_plate)]
        if not lattice.encloses((a.x + c.x) / 2.0, (a.y + c.y) / 2.0):
            continue
        b.add(f'ENV-PAR-E{ei:03d}', 'parapet', 'envelope', 'roof',
              b.member([v3(a.x, a.y, par_z), v3(c.x, c.y, par_z)], 'PARAPET-200x580'),
              'white', level_id=roof.id, lattice_index={'edge': ei},
              supports=['ENV-DECK-ROOF'],
              reason='Parapet upstand on the enclosed elevations, bearing on the deck.')


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
    level = lattice.levels[1]
    south = min(p.y for p in level.plate)
    # The entrance sits on the plan's own centre line. This was the literal 14.0 -- a
    # coordinate from the original thirty-six metre slab, left behind when the footprint
    # became a property of the massing family. It put the canopy posts off the podium
    # entirely on every plan that is not that slab, and they stood on nothing. The two
    # other places that need this axis already derive it the same way.
    entry_x = (min(p.x for p in level.plate) + max(p.x for p in level.plate)) / 2.0
    z = level.z - b.datums.value('edge_fascia_m') - 0.9
    depth = min(4.2, span * 0.55)
    b.add('ENV-CAN-ENTRY', 'entry_canopy', 'envelope', 'canopy',
          BoxGeometry(center=v3(entry_x, south - depth / 2.0, z),
                      size=v3(span, depth, 0.28)),
          'white', category='circulation', program='entry', level_id=level.id,
          datum_refs=['entry_canopy_span_m'],
          rule_refs=['HIERARCHY_TO_ENTRY_CANOPY', 'FCD-ENTRY-HIERARCHY-001'],
          reason='Entry canopy sized by the dominant order in the music; a level piece '
                 'produces no canopy at all.')
    for offset_x in (-span / 2.0 + 0.4, span / 2.0 - 0.4):
        b.add(f'ENV-CAN-POST-{"L" if offset_x < 0 else "R"}', 'entry_canopy',
              'envelope', 'canopy',
              b.member([v3(entry_x + offset_x, south - depth + 0.4,
                           lattice.levels[0].z),
                        v3(entry_x + offset_x, south - depth + 0.4, z)],
                       'STRUT-CHS180'),
              'steel_white', category='circulation', program='entry', level_id=level.id,
              datum_refs=['entry_canopy_span_m'],
              reason='Canopy support returning to the podium.')


# ---------------------------------------------------------------------------
# Circulation
# ---------------------------------------------------------------------------

def _emit_flight(
    b: _Builder, flight_id: str, start: Vector3, end: Vector3, width: float,
    level_id: str,
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
              reason='Individual tread; the riser datum divides the flight.')
    px, py = -uy, ux
    for side, tag in ((-1, 'L'), (1, 'R')):
        ox, oy = px * side * width / 2.0, py * side * width / 2.0
        b.add(f'CIR-STG-{flight_id}-{tag}', 'stair_stringer', 'circulation', 'stairs',
              b.member([v3(start.x + ox, start.y + oy, start.z - 0.22),
                        v3(end.x + ox, end.y + oy, end.z - 0.22)], 'STRINGER-180x450'),
              'white_soft', category='circulation', program='circulation',
              level_id=level_id, datum_refs=['flight_width_m'],
              reason='Stringer carries the flight.')
    _emit_railing(b, f'{flight_id}-RAIL', start, end, width, level_id)


def _emit_railing(
    b: _Builder, rail_id: str, start: Vector3, end: Vector3, width: float,
    level_id: str, spacing: float | None = None,
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
        for level, drop in (('T', 0.0), ('M', 0.5)):
            b.add(f'CIR-RAL-{rail_id}-{tag}-{level}', 'railing', 'circulation', 'safety',
                  b.member([v3(start.x + ox, start.y + oy, start.z + height - drop),
                            v3(end.x + ox, end.y + oy, end.z + height - drop)],
                           'RAIL-CHS64'),
                  'steel_white', category='circulation', program='circulation',
                  level_id=level_id,
                  datum_refs=['rail_height_m', 'rail_post_spacing_m'],
                  reason='Guard rail at the declared height; also the model scale anchor.')
        for s in range(posts + 1):
            f = s / posts
            x = start.x + dx * f + ox
            y = start.y + dy * f + oy
            z = start.z + (end.z - start.z) * f
            b.add(f'CIR-RAL-{rail_id}-{tag}-P{s:03d}', 'railing', 'circulation', 'safety',
                  b.member([v3(x, y, z), v3(x, y, z + height)], 'POST-45x45'),
                  'steel_white', category='circulation', program='circulation',
                  level_id=level_id,
                  datum_refs=['rail_height_m', 'rail_post_spacing_m'],
                  reason='Guard post at the repeated spacing the score set.')


# The parapet upstand, deck surface to cap. Chosen to keep the cap where it already
# was while closing the gap underneath it.
PARAPET_UPSTAND_M = 0.58


# The clear gap a landing keeps from a plate edge it overlaps, so the two read as
# meeting rather than as coinciding.
LANDING_OVERLAP_M = 0.9


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


def _stair_sites(lattice, width: float, run: float, levels: list,
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
    plates = [level.plate for level in levels if level.plate]
    if not plates:
        return []
    margin_x = width * 1.2
    margin_y = run / 2.0 + LANDING_OVERLAP_M + 1.0
    sites: list[tuple[float, float]] = []
    for u in range(5, 36):
        for v in range(5, 36):
            x = lattice.plan.fx(u / 40.0)
            y = lattice.plan.fy(v / 40.0)
            # the whole footprint of the stair has to be inside, not just its centre
            corners = ((x - margin_x, y - margin_y), (x + margin_x, y - margin_y),
                       (x + margin_x, y + margin_y), (x - margin_x, y + margin_y))
            if all(point_inside(plate, cx, cy)
                   for plate in plates for cx, cy in corners):
                sites.append((x, y))
    return sites


def _core_box(ax: float, ay: float, width: float,
              run: float) -> tuple[float, float, float, float]:
    """The floor a core at this anchor takes: stair, lift bay, landings.

    One formula, read by the reservation that cuts the program around the core and
    by the feasibility filter that keeps a core out of carved floor. Two copies of
    this box is two opinions about where the core is, which is the shape of every
    collision this pipeline has produced.
    """
    return (ax - width * 1.4, ay - run / 2.0 - LANDING_OVERLAP_M * 1.6,
            ax + width * 1.4 + LIFT_SHAFT_M, ay + run / 2.0 + 1.4)


def _box_overlaps(a, b) -> bool:
    return (min(a[2], b[2]) > max(a[0], b[0])
            and min(a[3], b[3]) > max(a[1], b[1]))


def _stair_anchor(lattice, width: float, run: float, levels: list,
                  away_from: tuple[float, float] | None = None,
                  keep_out: tuple = (),
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
    sites = _stair_sites(lattice, width, run, levels)
    best = None
    for x, y in sites:
        # An archetype's carved floor is not available, however well a core there
        # would score: a stair in the auditorium is the collision this filter ends.
        if any(_box_overlaps(_core_box(x, y, width, run), rect)
               for rect in keep_out):
            continue
        if away_from is None:
            # prefer the back of the plan, then the east side
            score = (y - lattice.plan.y_min) + (x - lattice.plan.x_min) * 0.35
        else:
            # A second exit is only an exit if it is remote from the first.
            # IBC 1007.1.1 wants a third of the plan diagonal in a sprinklered
            # building, so distance is the whole score here rather than a
            # tie-breaker on where a service stair would like to be.
            score = math.hypot(x - away_from[0], y - away_from[1])
        if best is None or score > best[0]:
            best = (score, x, y)
    return (best[1], best[2]) if best else None


def _emit_floor_landing(
    b: _Builder, landing_id: str, x: float, y: float, level, size_x: float,
    size_y: float,
) -> None:
    """A landing at a floor level, flush with the plate and overlapping it.

    Flush matters as much as overlapping: a landing whose top sits at the plate's z is
    a floor a person steps onto, and one sitting a few centimetres proud or shy is a
    trip hazard drawn to look like a landing. The slab is emitted *below* `level.z` so
    its top surface is the floor.
    """
    thickness = max(0.18, b.datums.value('slab_thickness_m') * 0.6)
    b.add(landing_id, 'stair_landing', 'circulation', 'stairs',
          BoxGeometry(center=v3(x, y, level.z - thickness / 2.0),
                      size=v3(size_x, size_y, thickness)),
          'white', category='circulation', program='circulation',
          level_id=level.id, lattice_index={'level': level.index},
          datum_refs=['flight_width_m', 'slab_thickness_m'],
          rule_refs=['CIR-INV-LANDING-MEETS-PLATE'],
          reason='Floor landing. Its top is flush with the plate and its footprint '
                 'overlaps it, so the flight arrives on the floor rather than beside '
                 'it.')


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
    podium = levels[1]
    xs = [p.x for p in podium.plate]
    rise = podium.z - levels[0].z
    width = max(MIN_CLEAR_WIDTH_M, flight_width * 0.62)

    # The apron the route may occupy: the frontage *beside* the entrance stair, not
    # across it. The first version spanned the whole elevation and the two ran
    # through each other -- the ramp from x -13.7 to 19.3 and the stair descending
    # at 4.9, both between ground and podium. A switchback that crosses the front
    # door is not a route, it is a collision drawn twice.
    margin = (max(xs) - min(xs)) * 0.06
    clearance = max(2.5, flight_width * 1.6)
    # The plate's southern edge *where the ramp arrives*, not its southernmost point
    # anywhere. On an apsidal plate the two differ: the global minimum sat 480 mm south
    # of the boundary at the ramp's own x, and the top landing came to rest thirty
    # millimetres short of a building it appeared to reach.
    arrival_x = min(xs) + margin + MIN_LANDING_LENGTH_M * 0.5
    south = _plate_south_at(podium.plate, arrival_x)
    plan = plan_switchback_ramp(
        rise_m=rise, width_m=width, x_min=min(xs) + margin,
        x_max=entry_x - clearance,
        # The plate edge itself, overlapped the way a stair landing overlaps it, so
        # the top landing meets the floor rather than stopping short of it.
        y_start=south + LANDING_OVERLAP_M / 2.0,
        y_available=apron_depth_m, z_base=levels[0].z)

    if plan is None:
        # No compliant ramp fits. Build the stair and record the failure rather than
        # drawing a ramp that would have to break the standard to be here.
        b.unresolved_accessible_route = (
            f'No ADA-compliant ramp fits the approach: {rise:.2f} m of rise needs '
            f'{rise * 12:.0f} m of run at 1:12 in {math.ceil(rise / MAX_RUN_RISE_M)} '
            f'runs (405.2, 405.6), and the apron is '
            f'{apron_depth_m:.0f} m deep. A stair is built instead; the accessible '
            f'route is unresolved and needs a lift or a regraded approach.')
        stair_x = entry_x - max(2.5, flight_width * 1.6)
        approach = max(4.0, rise * 2.2)
        # Same derivation as the entry flight: the landing decides where the stair ends.
        stair_south = _plate_south_at(podium.plate, stair_x)
        landing_depth = LANDING_OVERLAP_M * 2.4
        landing_y = stair_south + LANDING_OVERLAP_M / 2.0
        top_y = landing_y - landing_depth / 2.0
        _emit_flight(b, 'R01', v3(stair_x, top_y - approach, levels[0].z),
                     v3(stair_x, top_y, podium.z), width * 1.2, levels[0].id)
        _emit_floor_landing(b, 'CIR-LND-ACCESS', stair_x, landing_y, podium,
                            width * 1.8, landing_depth)
        return

    b.accessible_route = plan
    deck = b.profile(convention_profile(
        f'RAMP-{width * 1000:.0f}x{RAMP_THICKNESS_M * 1000:.0f}', 'box',
        RAMP_THICKNESS_M, width))

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
        direction = 1.0 if run.direction > 0 else -1.0
        start = v3(run.x_start, run.y, run.z_start - deck_drop)
        end = v3(run.x_end, run.y, run.z_end - deck_drop)
        path = [v3(run.x_start - direction * reach, run.y, run.z_start - deck_drop),
                start, end,
                v3(run.x_end + direction * reach, run.y, run.z_end - deck_drop)]
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
                  b.member([v3(run.x_start, run.y + side * width / 2.0,
                               run.z_start + CURB_HEIGHT_M / 2.0),
                            v3(run.x_end, run.y + side * width / 2.0,
                               run.z_end + CURB_HEIGHT_M / 2.0)],
                           b.profile(convention_profile(
                               'RAMPCURB-100x60', 'box', CURB_HEIGHT_M, 0.06))),
                  'white', category='circulation', program='circulation',
                  level_id=levels[0].id, lattice_index={'run': run.index},
                  supports=[f'CIR-RMP-RUN-{run.index:02d}'],
                  rule_refs=['ADA-405.9.2'],
                  reason='Edge protection: a 100 mm curb, the option 405.9.2 allows. '
                         'Cast with the run it edges: the curb sits half a deck width '
                         'off the run centre-line, so the two axes never cross and the '
                         'bearing has to be declared rather than found.')
        if plan.handrails_required:
            # 505.10 extensions run 305 mm beyond each end of the run
            ext = HANDRAIL_EXTENSION_M
            ux = 1.0 if run.direction > 0 else -1.0
            _emit_railing(
                b, f'RMP-{run.index:02d}',
                v3(run.x_start - ux * ext, run.y, run.z_start),
                v3(run.x_end + ux * ext, run.y, run.z_end), width, levels[0].id)

    for landing in plan.landings:
        b.add(f'CIR-RMP-LND-{landing.index:02d}', 'ramp_landing', 'circulation', 'ramps',
              BoxGeometry(center=v3(landing.x, landing.y,
                                    landing.z - RAMP_THICKNESS_M / 2.0),
                          size=v3(landing.size_x, landing.size_y, RAMP_THICKNESS_M)),
              'white', category='circulation', program='circulation',
              level_id=levels[0].id, lattice_index={'landing': landing.index},
              supports=([] if landing.kind == 'bottom'
                        else [f'CIR-RMP-RUN-{landing.index - 1:02d}']),
              rule_refs=['ADA-405.7.3'] + (['ADA-405.7.4']
                                           if landing.kind == 'turn' else []),
              reason=f'{landing.kind.title()} landing, '
                     f'{min(landing.size_x, landing.size_y) * 1000:.0f} mm clear. '
                     + ('405.7.4 requires 1525 x 1525 mm where a ramp changes '
                        'direction.' if landing.kind == 'turn' else
                        '405.7.3 requires 1525 mm of clear length.'))


# How many cores may be added beyond the remote pair: exactly as many as the emitter
# has flight names for, read from the one place those names live. A building needing
# more is one to report on, not to keep adding stairs to.
MAX_EXTRA_CORES = len(EXTRA_FLIGHT_PAIRS)


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
    run = max(2.2, width * 2.4)
    keep_out = tuple(rect for rects in lattice.carved.values() for rect in rects)

    primary, served = None, list(lattice.levels)
    while len(served) >= 3:
        primary = _stair_anchor(lattice, width, run, served, keep_out=keep_out)
        if primary is not None:
            break
        served = served[:-1]

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
        while len(trial) >= 3:
            candidate = _stair_anchor(lattice, width, run, trial,
                                      away_from=anchor_point, keep_out=keep_out)
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

    def pick_extras(anchor_point, second_run):
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
            while len(trial) >= 3:
                if not any(level.id == top_missing for level in trial):
                    break  # truncated below the storey this core exists for
                candidate = _stair_anchor(lattice, width, run, trial,
                                          away_from=anchor_point,
                                          keep_out=keep_out)
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

    second, second_served = (None, []) if primary is None else pick_second(primary)
    extras = [] if primary is None else pick_extras(primary, second_served)

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

            sites_primary = clear_of_carve(_stair_sites(lattice, width, run, served))
            sites_extra = clear_of_carve(_stair_sites(lattice, width, run, top_run))
            best_pair, best_span = None, gap
            for px, py in sites_primary:
                for qx, qy in sites_extra:
                    span = math.hypot(px - qx, py - qy)
                    if span > best_span:
                        best_pair, best_span = ((px, py), (qx, qy)), span
            if best_pair is not None:
                primary = best_pair[0]
                second, second_served = pick_second(primary)
                extras = pick_extras(primary, second_served)
                # The moved pair is the point; if the re-picked extra strayed, pin
                # the partner this adjustment chose for the run it was chosen for.
                # Replacing at the cap rather than appending: `pick_extras` yields at
                # most two, the emitter names exactly two, and a third would have been
                # an IndexError in a branch that only fires on a massing whose greedy
                # pair fails -- the kind that ships.
                if not extras or extras[-1][1][-1].id != top_run[-1].id:
                    pinned = (best_pair[1], top_run)
                    if len(extras) >= MAX_EXTRA_CORES:
                        extras[-1] = pinned
                    else:
                        extras.append(pinned)

    return {'width': width, 'run': run, 'primary': primary, 'served': served,
            'second': second, 'second_served': second_served, 'extras': extras}


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
        return all(point_inside(plate, x, y) for plate in plates)

    for yj in range(len(lattice.y_lines)):
        for xi in range(len(lattice.x_lines) - 1):
            if stands(xi, yj) and stands(xi + 1, yj):
                return True
    for xi in range(len(lattice.x_lines)):
        for yj in range(len(lattice.y_lines) - 1):
            if stands(xi, yj) and stands(xi, yj + 1):
                return True
    return False


def _carve_and_allocate(grid, datums, typology: str, brief):
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
    if isinstance(carve, TheatreCarve):
        # Written to the lattice, not passed around: every later reader of the
        # cores -- the emitter, a test recomputing the reservation -- must see the
        # same carved floor this allocation saw.
        grid.carved = {grid.occupied[0].index: [carve.house, carve.stage]}
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
            carve = CarveRefusal(
                archetype_id=carve.archetype_id,
                precluded=[UnplacedSpace(
                    space_id=zone.space_id, label=zone.label,
                    area_required_m2=zone.area_required_m2,
                    reason=f'the theatre archetype could not carve this plate: no '
                           f'stair can serve {", ".join(stranded)} once the house '
                           f'takes its floor') for zone in carve.zones],
                reason=f'once the house takes its floor no stair can serve '
                       f'{", ".join(stranded)}: this massing stands those storeys '
                       f'where only the fly-tower phase (decision 0016) can make '
                       f'them reachable')
    cores = core_reservations(grid, datums)
    if carve is None:
        return allocate_program(grid, datums, brief, reserved=cores), None
    if isinstance(carve, CarveRefusal):
        return allocate_program(grid, datums, brief, reserved=cores,
                                precluded=tuple(carve.precluded)), carve
    for level_index, rects in carve.removed.items():
        level = grid.level(level_index)
        for x0, y0, x1, y1 in rects:
            # A music void that lands inside the carved volume is swallowed by it: a
            # hole inside a hole is nothing, and two overlapping rings confuse every
            # consumer that triangulates the plate.
            level.voids[:] = [
                void for void in level.voids
                if not (min(x1, max(p.x for p in void)) - max(x0, min(p.x for p in void)) > 0
                        and min(y1, max(p.y for p in void)) - max(y0, min(p.y for p in void)) > 0)]
            level.voids.append([v2(x0, y0), v2(x1, y0), v2(x1, y1), v2(x0, y1)])
    allocation = allocate_program(
        grid, datums, brief, reserved=cores,
        carved={index: tuple(rects) for index, rects in carve.reservations.items()},
        preplaced=tuple(carve.zones))
    return allocation, carve


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
    # The stair itself, plus the lift bay beside it and the landings at each end.
    # (A lift car is a lift car: the shaft width is `LIFT_SHAFT_M` inside `_core_box`,
    # not a function of the flight width -- scaling it by the stair once handed an
    # 11.6 m reservation to a 2.6 m flight.)
    return tuple(_core_box(anchor[0], anchor[1], width, run)
                 for anchor in anchor_points if anchor is not None)


def _emit_circulation(b: _Builder) -> None:
    lattice, datums = b.lattice, b.datums
    levels = lattice.levels
    width = datums.value('flight_width_m')

    run = max(2.2, width * 2.4)

    # Serve the tallest run of levels a single core can actually reach, from the ground
    # up. A heavily stepped or split mass genuinely has no point in plan inside every
    # plate, and the honest answer is a stair that stops where the building stops being
    # stackable -- not one drawn through the levels it cannot reach. Falling back to a
    # centroid was the first attempt and it produced landings that were flush with a
    # floor and a metre and a half outside it, which is worse than none.
    anchors = core_anchors(lattice, datums)
    anchor, served = anchors['primary'], anchors['served']
    if anchor is None:
        served = levels[:3]
        podium = levels[0].plate
        anchor = (sum(p.x for p in podium) / len(podium),
                  sum(p.y for p in podium) / len(podium))
    unreached = [level.id for level in levels[len(served):] if level.kind == 'occupied']
    b.unreached_levels = unreached
    ax, ay = anchor

    # --- the main switchback, level by level ---------------------------------
    # Each storey is: a flight up to the half-landing, the turn, a flight up to the
    # next floor, and a floor landing there. The floor landing is what the old emitter
    # never drew, which is why every flight arrived in mid-air.
    #
    # The stair faces away from its egress partner. The landing is where a person
    # enters the stair -- it is the exit the life-safety graph measures -- and its
    # side of the core is a free design choice, so the doors of a pair open away from
    # each other. On the theatre bar the anchors could stand no further apart than
    # 9.4 m against a 10.3 m third-diagonal ask, and the doors facing away from each
    # other is what a person would draw before moving either core.
    partner = (anchors['extras'][0][0] if anchors['extras']
               else anchors['second'])
    facing = -1.0 if partner is not None and partner[1] < ay else 1.0

    for k in range(len(served) - 1):
        lower, upper = served[k], served[k + 1]
        za, zb = lower.z, upper.z
        if zb - za < 0.4:
            continue
        zm = (za + zb) / 2.0
        y0 = ay - facing * run / 2.0
        y1 = ay + facing * run / 2.0
        half_x = ax - width / 2.0
        up_x = ax + width / 2.0

        _emit_flight(b, f'A{k:02d}', v3(half_x, y0, za), v3(half_x, y1, zm), width,
                     lower.id)
        # the turn, at half height and flush with nothing, which is what it is
        b.add(f'CIR-HLF-A{k:02d}', 'stair_half_landing', 'circulation', 'stairs',
              BoxGeometry(center=v3(ax, y1 + facing * 0.7, zm - 0.12),
                          size=v3(width * 2.0, 1.4, 0.24)),
              'white', category='circulation', program='circulation',
              level_id=lower.id, lattice_index={'level': lower.index},
              datum_refs=['flight_width_m', 'floor_to_floor_m'],
              reason='Switchback turn at half storey height.')
        _emit_flight(b, f'B{k:02d}', v3(up_x, y1, zm), v3(up_x, y0, zb), width,
                     lower.id)

        # and the floor landing the second flight arrives on
        _emit_floor_landing(b, f'CIR-LND-{upper.id}', ax, y0 - facing * 0.8, upper,
                            width * 2.2, LANDING_OVERLAP_M * 2.0)

    # --- the second egress stair, remote from the first -----------------------
    # A building with four hundred occupants and one stair does not comply with IBC
    # 1006.3.2, and two stairs beside each other do not comply with 1007.1.1 either:
    # the life-safety graph reported remoteness failing at 2.11 against the one-third
    # diagonal rule before this existed. The second core is placed by maximising
    # distance from the first rather than by where a service stair would prefer to be.
    #
    # It does not have to reach the top. Requiring a second core inside *every*
    # plate found exactly one valid point on this plan -- the same point as the
    # first -- because a building whose upper floors shrink has only one region
    # common to all of them. A second stair that serves the lower storeys and stops
    # is a real building; two coincident stairs are not an egress strategy. The
    # storeys it cannot reach then fail 1006.3.2 in the graph, which is the correct
    # report rather than a hidden compromise.
    # IBC 1007.1.1 measures the diagonal of the *area served*, which is a storey's
    # plate rather than the site footprint. Using the plan bounds asked for a
    # separation larger than any single floor needs, and the life-safety graph --
    # which correctly uses the plate -- would then have passed a target the emitter
    # had already failed to hit. Both now measure the same thing.
    # The same search the reservation was cut from. Two of these existed -- this one
    # stopped at the first candidate clearing the third-diagonal rule, the other took
    # the most remote candidate outright -- and on a stepped plate they chose different
    # points. The program was then banded around a core the stair was not drawn at, and
    # nine partitions ran through the flights of the one that was.
    #
    # IBC 1007.1.1 measures the diagonal of the area served, and the shortfall when no
    # candidate clears it is reported by the life-safety graph rather than hidden here:
    # a second exit twelve metres away is not compliant and is still a second exit.
    second, second_served = anchors['second'], anchors['second_served']

    def emit_scissor_stair(anchor_point, levels_run, tags, landing_tag: str,
                           why: str) -> None:
        bx, by = anchor_point
        # Entered from the side away from the primary, for the same reason the
        # primary faces away from here: the landings are the exits, and the pair is
        # measured door to door.
        away = -1.0 if ay < by else 1.0
        for k in range(len(levels_run) - 1):
            lower, upper = levels_run[k], levels_run[k + 1]
            if upper.z - lower.z < 0.4:
                continue
            zm = (lower.z + upper.z) / 2.0
            y0, y1 = by - away * run / 2.0, by + away * run / 2.0
            _emit_flight(b, f'{tags[0]}{k:02d}', v3(bx - width / 2.0, y0, lower.z),
                         v3(bx - width / 2.0, y1, zm), width, lower.id)
            b.add(f'CIR-HLF-{tags[0]}{k:02d}', 'stair_half_landing', 'circulation',
                  'stairs',
                  BoxGeometry(center=v3(bx, y1 + away * 0.7, zm - 0.12),
                              size=v3(width * 2.0, 1.4, 0.24)),
                  'white', category='circulation', program='circulation',
                  level_id=lower.id, lattice_index={'level': lower.index},
                  datum_refs=['flight_width_m', 'floor_to_floor_m'],
                  rule_refs=['IBC-1007.1.1'],
                  reason=f'{why}, turn at half storey height.')
            _emit_flight(b, f'{tags[1]}{k:02d}', v3(bx + width / 2.0, y1, zm),
                         v3(bx + width / 2.0, y0, upper.z), width, lower.id)
            _emit_floor_landing(b, f'CIR-{landing_tag}-{upper.id}', bx,
                                y0 - away * 0.8, upper,
                                width * 2.2, LANDING_OVERLAP_M * 2.0)

    if second is not None:
        emit_scissor_stair(second, second_served, SECOND_FLIGHT_PAIR, 'LND2',
                           'Second egress stair')
        b.second_stair_anchor = second
        b.second_stair_levels = [lv.id for lv in second_served]

    # The storeys the second stops short of get their own way down. On a bar over a
    # podium this is the bar's second stair: the podium keeps its remote pair and no
    # storey counts one exit because another storey's remoteness was worth more.
    for index, (anchor_point, levels_run) in enumerate(
            anchors['extras'][:MAX_EXTRA_CORES]):
        # Named from `EXTRA_FLIGHT_PAIRS`, which the dependency graph reads too: the
        # half landing between a pair of flights is hosted by looking those letters up,
        # so a name invented here and not there leaves the landing supported by nothing.
        emit_scissor_stair(anchor_point, levels_run, EXTRA_FLIGHT_PAIRS[index],
                           f'LND{3 + index}',
                           'Egress stair for the storeys the remote core stops short of')

    # --- the external approach, from grade to the podium ----------------------
    # It genuinely starts outside the building; what it must not do is finish outside.
    # The top landing overlaps the podium plate, so the flight ends on the floor.
    if len(levels) > 1:
        podium = levels[1]
        xs = [p.x for p in podium.plate]
        entry_x = (min(xs) + max(xs)) / 2.0
        south = _plate_south_at(podium.plate, entry_x)
        # The flight ends where the landing starts, derived from it rather than set
        # back on its own. Both used to be placed independently -- the flight 1.2 m
        # short of the plate, the landing 450 mm over it -- and the 1.65 m between them
        # was nobody's business, so the stair arrived at nothing.
        landing_depth = LANDING_OVERLAP_M * 2.4
        landing_y = south + LANDING_OVERLAP_M / 2.0
        top_y = landing_y - landing_depth / 2.0
        approach = max(4.0, (podium.z - levels[0].z) * 2.2)
        _emit_flight(b, 'F01',
                     v3(entry_x, top_y - approach, levels[0].z),
                     v3(entry_x, top_y, podium.z), width * 1.3, levels[0].id)
        _emit_floor_landing(b, 'CIR-LND-ENTRY', entry_x, landing_y, podium,
                            width * 1.9, landing_depth)

    # --- the lift and service core, inside the plan and full height -----------
    core_w = max(2.6, width * 1.6)
    core_x = ax + width * 1.4
    if all(point_inside(level.plate, core_x, ay) for level in served if level.plate):
        for k in range(len(served) - 1):
            b.add(f'CIR-SHF-{served[k].id}', 'elevator_shaft', 'circulation',
                  'vertical_core',
                  ExtrusionGeometry(
                      boundary=[v2(core_x - core_w / 2.0, ay - core_w / 2.0),
                                v2(core_x + core_w / 2.0, ay - core_w / 2.0),
                                v2(core_x + core_w / 2.0, ay + core_w / 2.0),
                                v2(core_x - core_w / 2.0, ay + core_w / 2.0)],
                      z_base=served[k].z, z_top=served[k + 1].z),
                  'concrete', category='service', program='vertical_circulation',
                  level_id=served[k].id, lattice_index={'level': k},
                  datum_refs=['flight_width_m'],
                  reason='Service and lift core, continuous and inside every plate.')

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
            for a, b in clear if b - a >= 1.2]


def _emit_partition_run(
    b: _Builder, run_id: str, partition, requirement, level, x0: float, y0: float,
    x1: float, y1: float, height: float, zone,
) -> None:
    """One wall, with the door and the head over it where an opening is needed."""
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 1.2:
        return
    horizontal = abs(x1 - x0) >= abs(y1 - y0)
    thickness = partition.thickness_mm / 1000.0
    refs = ['floor_to_floor_m', 'slab_thickness_m', 'circulation_allowance']
    # The clause that governed, not every clause the module can reach.
    rules = [requirement.fire_clause] + (
        ['CONSTITUTION-OPAQUE'] if requirement.opaque_required else []) + (
        ['CONSTITUTION-ABUSE'] if requirement.abuse_resistant else [])

    opening = requirement.permeability in ('door', 'controlled_door')
    door_at = length / 2.0 if opening else None
    leaf = DOOR_LEAF_M if opening else 0.0

    def segment(tag: str, start: float, end: float, z_centre: float,
                z_size: float, kind: str) -> None:
        if end - start < 0.05 or z_size < 0.05:
            return
        t0, t1 = start / length, end / length
        cx = x0 + (x1 - x0) * (t0 + t1) / 2.0
        cy = y0 + (y1 - y0) * (t0 + t1) / 2.0
        span = end - start
        size = (v3(span, thickness, z_size) if horizontal
                else v3(thickness, span, z_size))
        b.add(f'{run_id}-{tag}', kind, 'program', 'partitions',
              BoxGeometry(center=v3(cx, cy, z_centre), size=size),
              partition.material, category=zone.category, program=zone.space_type,
              level_id=level.id,
              lattice_index={'level': level.index, 'band': zone.band_index},
              datum_refs=refs, rule_refs=rules,
              reason=(f'{partition.label} between {zone.label} and its neighbour. '
                      f'{requirement.fire_basis} Acoustic target STC '
                      f'{requirement.stc_target}: {requirement.stc_basis}. '
                      f'{partition.assembly}'))

    if door_at is None:
        segment('W', 0.0, length, level.z + height / 2.0, height, 'partition')
        return

    half = leaf / 2.0
    segment('WA', 0.0, max(0.0, door_at - half), level.z + height / 2.0, height,
            'partition')
    segment('WB', min(length, door_at + half), length, level.z + height / 2.0, height,
            'partition')
    # The head over the opening. A rated wall that stops at the door head is not rated.
    head_height = max(0.0, height - 2.1)
    segment('HD', max(0.0, door_at - half), min(length, door_at + half),
            level.z + 2.1 + head_height / 2.0, head_height, 'partition_head')

    t = door_at / length
    dx = x0 + (x1 - x0) * t
    dy = y0 + (y1 - y0) * t
    controlled = requirement.permeability == 'controlled_door'
    b.add(f'{run_id}-DR', 'door', 'program', 'partitions',
          BoxGeometry(center=v3(dx, dy, level.z + 1.05),
                      size=(v3(leaf, thickness * 0.5, 2.1) if horizontal
                            else v3(thickness * 0.5, leaf, 2.1))),
          'frame_dark' if controlled else 'white',
          category=zone.category, program=zone.space_type, level_id=level.id,
          lattice_index={'level': level.index, 'band': zone.band_index},
          datum_refs=refs,
          rule_refs=['IBC-1010.1.1', 'ADA-404.2.3']
          + (['IBC-716'] if requirement.fire_rating_hours > 0 else []),
          reason=(f'{"Controlled" if controlled else "Ordinary"} door, '
                  f'{DOOR_LEAF_M * 1000:.0f} mm leaf giving '
                  f'{DOOR_CLEAR_M * 1000:.0f} mm clear, which is the ADA 404.2.3 '
                  f'minimum. {requirement.permeability_basis}'
                  + (f' A {requirement.fire_rating_hours:.0f}-hour wall needs a rated '
                     f'self-closing assembly per IBC Table 716.1(2); the opening '
                     f'protective is not selected here.'
                     if requirement.fire_rating_hours > 0 else '')))


def _emit_partitions(b: _Builder, allocation, sprinklered: bool,
                     reserved=(), carve=None) -> None:
    """Enclose every zone that needs enclosing, rated and openable.

    What was here drew one box along the south edge of any private or service zone --
    2.70 m tall whatever the storey, on one side of a rectangle, with no type, no
    rating, no acoustic separation and no door. A wall along one edge does not enclose
    a room, and public zones got nothing at all.
    """
    lattice, datums = b.lattice, b.datums
    f2f = datums.value('floor_to_floor_m')
    slab = datums.value('slab_thickness_m')
    height = max(2.4, f2f - slab - PARTITION_HEAD_CLEARANCE_M)
    storeys = len(lattice.occupied)
    by_level: dict[str, list] = {}
    for zone in allocation.zones:
        by_level.setdefault(zone.level_id, []).append(zone)

    # Walls an archetype requires to run its carved volume's full height rather than
    # the storey's: the acoustic enclosure of a nine-metre house is nine metres tall,
    # or it is a fence.
    tall_walls = dict(getattr(carve, 'tall_walls_m', None) or {})

    for level in lattice.occupied:
        zones = by_level.get(level.id, [])
        for zone in zones:
            for edge, x0, y0, x1, y1 in _zone_edges(zone):
                neighbour = _touching_zone(zone, zones, edge)
                # Only one of a pair draws the wall between them, or every shared edge
                # gets two coincident partitions.
                if neighbour is not None and neighbour.space_id < zone.space_id:
                    continue
                # The house and the stage meet at the proscenium, which the archetype
                # builds as its own wall with the opening in it; a rated partition
                # drawn across it would wall the audience off from the play.
                if (neighbour is not None
                        and {zone.space_type, neighbour.space_type}
                        == {'auditorium', 'stage'}):
                    continue
                other_type = neighbour.space_type if neighbour else 'circulation'
                other_category = neighbour.category if neighbour else 'circulation'
                requirement = required_separation(
                    zone.space_type, other_type, category_a=zone.category,
                    category_b=other_category, storeys=storeys,
                    sprinklered=sprinklered, area_a_m2=zone.area_delivered_m2)
                # Two public rooms with nothing to separate them stay open, and so
                # does a public room facing the corridor. The plate reads as one
                # floor, which is the point of an open public building; a wall
                # drawn where no clause and no acoustic target asks for one is
                # clutter that also costs money to build.
                # A lobby is category `circulation`, so a public-only test would
                # still wall the lobby off from the room beside it.
                open_pair = {zone.category, other_category} <= {'public',
                                                                'circulation'}
                if (open_pair and requirement.fire_rating_hours == 0.0
                        and requirement.stc_target <= 40):
                    continue
                partition = select_partition(
                    requirement, shaft=zone.space_type in ('riser', 'elevator'))
                # A carved room's enclosure runs to the height its section claims;
                # the taller of the pair governs a shared wall.
                run_height = max(height,
                                 tall_walls.get(zone.space_id, 0.0),
                                 tall_walls.get(
                                     neighbour.space_id if neighbour else '', 0.0))
                for piece, clear in enumerate(
                        _clear_of_cores(x0, y0, x1, y1, reserved)):
                    suffix = '' if piece == 0 else f'-{piece}'
                    _emit_partition_run(
                        b,
                        f'PRG-PRT-{level.id}-{zone.space_id}-'
                        f'{edge[:1].upper()}{suffix}',
                        partition, requirement, level, *clear, run_height, zone)


def _emit_archetype(b: _Builder, carve) -> None:
    """The theatre's own geometry: the rake, the stage floor, the proscenium wall.

    This emitter is the promise and `evaluate_archetype` is the audit: every riser
    top here comes from the carve's derived rows, and the sightline gate then
    recomputes the C-value from these solids rather than trusting the derivation
    that placed them. The bowl is emitted as solid stepped platforms -- stadia
    construction -- each bearing on the ground slab; the 50 mm the boxes sink below
    the slab top gives the front rows a body without moving any derived floor.
    """
    if not isinstance(carve, TheatreCarve):
        return
    ground = b.lattice.occupied[0]
    slab_id = f'STR-SLB-{ground.id}'
    hx0, hy0, hx1, hy1 = carve.house
    sx0, sy0, sx1, sy1 = carve.stage
    dx = carve.audience_dx
    mid_y = (hy0 + hy1) / 2.0
    width_y = hy1 - hy0 - 0.1

    for row in carve.rows:
        xa = carve.proscenium_x + dx * row.offset_front_m
        xb = carve.proscenium_x + dx * row.offset_back_m
        x0, x1 = min(xa, xb), max(xa, xb)
        top = ground.z + row.floor_m
        base = ground.z - 0.05
        b.add(f'PRG-BWL-{ground.id}-R{row.index:02d}', 'auditorium_riser',
              'program', 'archetype',
              BoxGeometry(center=v3((x0 + x1) / 2.0, mid_y, (base + top) / 2.0),
                          size=v3(x1 - x0, width_y, top - base)),
              'concrete_light', category='public', program='auditorium',
              level_id=ground.id,
              lattice_index={'level': ground.index, 'row': row.index},
              supports=[slab_id],
              rule_refs=['ARCH-SIGHTLINE'],
              reason=(f'Row {row.index}: floor {row.floor_m:.3f} m above the slab, '
                      f'placed so its eye clears the row in front by '
                      f'{C_VALUE_DESIGN_M * 1000:.0f} mm to a focal point '
                      f'{carve.focal_h_m:.1f} m up at the proscenium. Derived by '
                      f'the sightline recurrence, then measured back by the '
                      f'ARCH-SIGHTLINE gate.'))

    b.add(f'PRG-STG-{ground.id}', 'stage_platform', 'program', 'archetype',
          BoxGeometry(center=v3((sx0 + sx1) / 2.0, (sy0 + sy1) / 2.0,
                                ground.z + carve.focal_h_m / 2.0),
                      size=v3(sx1 - sx0 - 0.1, sy1 - sy0 - 0.1, carve.focal_h_m)),
          'timber', category='private', program='stage', level_id=ground.id,
          lattice_index={'level': ground.index},
          supports=[slab_id],
          reason=(f'Stage floor {carve.focal_h_m:.1f} m above the house slab: the '
                  f'height the whole rake was derived against, so the downstage '
                  f'edge is the focal point the sightline gate measures to.'))

    # The one wall between house and stage, carrying the opening. The rated
    # partition a zone pair would normally get is skipped across the proscenium
    # edge; this wall is what stands there instead.
    wall_t = 0.4
    top_z = ground.z + carve.clear_house_m
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


def _emit_program(b: _Builder, allocation: ProgramAllocation,
                  sprinklered: bool = True) -> None:
    """Zones come from the allocator, so the plan is a result rather than a drawing."""
    lattice = b.lattice
    for level in lattice.occupied:
        zones = allocation.zones_on(level.index)
        for zi, zone in enumerate(zones):
            x0, y0, x1, y1 = zone.x0, zone.y0, zone.x1, zone.y1
            material = _CATEGORY_MATERIAL[zone.category]
            b.add(f'PRG-ZON-{level.id}-{zone.space_id}', 'program_zone', 'program',
                  'zones',
                  BoxGeometry(center=v3((x0 + x1) / 2.0, (y0 + y1) / 2.0,
                                        level.z + 0.055),
                              size=v3(x1 - x0, y1 - y0, 0.11)),
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
                          f'the section stays legible.'))

            # The archetype builds these rooms' interiors itself -- the rake is the
            # furniture -- and a grid of workbenches across a raked house is what the
            # generic fallback below would draw.
            if zone.space_type in ('auditorium', 'stage'):
                continue

            blocked = lambda px, py: (not point_inside(level.plate, px, py)
                                      or any(point_inside(v, px, py)
                                             for v in level.voids))
            name = zone.space_type
            if 'stacks' in name or 'collections' in name or 'processing' in name:
                for r in range(max(1, int((y1 - y0) / 1.9))):
                    yy = y0 + 1.0 + r * 1.9
                    for cx in range(max(1, int((x1 - x0) / 4.6))):
                        xx = x0 + 2.4 + cx * 4.6
                        if blocked(xx, yy):
                            continue
                        b.add(f'PRG-SHF-{level.id}-{zone.space_id}-R{r:02d}-C{cx:02d}',
                              'shelving_run', 'program', 'furniture',
                              BoxGeometry(center=v3(xx, yy, level.z + 1.15),
                                          size=v3(4.2, 0.55, 2.10)),
                              'furn', category=zone.category, program=name,
                              level_id=level.id, reason='Shelving run.')
            elif any(word in name for word in
                     ('reading', 'seminar', 'cafe', 'foyer', 'lobby', 'periodicals')):
                for r in range(max(1, int((y1 - y0) / 2.6))):
                    for cx in range(max(1, int((x1 - x0) / 2.9))):
                        xx, yy = x0 + 1.7 + cx * 2.9, y0 + 1.5 + r * 2.6
                        if blocked(xx, yy):
                            continue
                        tag = f'{level.id}-{zone.space_id}-R{r:02d}-C{cx:02d}'
                        b.add(f'PRG-DSK-{tag}', 'desk', 'program', 'furniture',
                              BoxGeometry(center=v3(xx, yy, level.z + 0.40),
                                          size=v3(1.60, 0.80, 0.08)),
                              'furn', category=zone.category, program=name,
                              level_id=level.id, reason='Table.')
                        for side in (-1, 1):
                            b.add(f'PRG-SEA-{tag}-{"N" if side > 0 else "S"}', 'seat',
                                  'program', 'furniture',
                                  BoxGeometry(center=v3(xx, yy + side * 0.72,
                                                        level.z + 0.24),
                                              size=v3(0.48, 0.48, 0.06)),
                                  'furn', category=zone.category, program=name,
                                  level_id=level.id, reason='Seat.')
            else:
                for cx in range(max(1, int((x1 - x0) / 3.2))):
                    xx = x0 + 1.8 + cx * 3.2
                    if blocked(xx, (y0 + y1) / 2.0):
                        continue
                    b.add(f'PRG-DSK-{level.id}-{zone.space_id}-C{cx:02d}', 'desk',
                          'program', 'furniture',
                          BoxGeometry(center=v3(xx, (y0 + y1) / 2.0, level.z + 0.45),
                                      size=v3(1.4, 2.0, 0.10)),
                          'furn', category=zone.category, program=name,
                          level_id=level.id, reason='Equipment or workbench.')


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
        got, tries = 0, 0
        while got < 18 and tries < 500:
            tries += 1
            x, y = x0 + rnd() * (x1 - x0), y0 + rnd() * (y1 - y0)
            if level.index > 0 and not point_inside(level.plate, x, y):
                continue
            if any(point_inside(hole, x, y) for hole in level.voids):
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def compile_building_model_v3(
    features: AudioFeatures, score: ArchitecturalScore, *,
    massing_id: str | None = None, typology: str | None = None,
    grammar_id: str | None = None, cutaway: bool = True,
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

    # The brief follows the typology, and the typology followed the massing. Passing
    # LIBRARY_BRIEF on every run was the last of the four constants that made every
    # recording produce the same building: a theatre tested against a library brief
    # is a library that happens to be shaped oddly.
    brief = brief_for(typology, storeys=len(lattice.occupied))

    # The selection runs here and not earlier because the screen is given the building
    # this score actually produced -- its storeys, its height, its clear span -- rather
    # than a canned brief that would ask the same question of every recording.
    selection, domain = select_project(
        score, datums, lattice, allocation, program_id=kit_for(typology).program_id,
        typology=typology, jurisdiction=to_jurisdiction(site),
        massing=massing, massing_why=massing_why)

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
    for option in (selection.ranked_options
                   or [RankedOption(system_id=selection.system_id,
                                    grammar_id=selection.grammar_id, affinity=0.0)]):
        candidate_frame = FRAME_TECTONICS[
            SYSTEM_BUILDABILITY[option.system_id].frame_tectonic]
        occupancy, trial = _run_sizing(datums, lattice, allocation, candidate_frame)
        if trial.feasible:
            frame, sizing, governing_occupancy = candidate_frame, trial, occupancy
            if attempts:
                selection = selection.model_copy(update={
                    'system_id': option.system_id, 'grammar_id': option.grammar_id,
                    'frame_tectonic_id': candidate_frame.id,
                    'envelope_tectonic_id': GRAMMAR_ENVELOPE[option.grammar_id],
                    'sizing_fallback': (
                        'The preferred frame could not be sized: '
                        + '; '.join(attempts[:2])
                        + f'. Built on {option.system_id} instead.')})
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

    # The model's identity, and through it the identity of every artifact directory:
    # the GLB, the drawings and the renders are all pathed by `model_id`. It used to be
    # the audio hash alone, which stopped being an identity the day anything else began
    # to shape the building -- a re-run after a compiler change quietly replaced the
    # GLB an older stored run still pointed at, and the same MP3 could not keep two
    # pinned variants side by side. Hashed from everything that decides what gets
    # built: the score (which carries the audio), the compiler version, the caller's
    # pins, and the four selection outcomes. Same inputs, same id, so an identical
    # re-run replaces its own identical output; anything different builds beside it.
    identity_seed = '|'.join((
        score.score_id, COMPILER_VERSION,
        f'pins:{pinned_massing or "-"}/{pinned_typology or "-"}'
        f'/{grammar_id or "-"}/cutaway={cutaway}',
        selection.typology, selection.massing_id,
        selection.system_id, selection.grammar_id,
    ))
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
    model.site_loads = site_loads.compute(
        site, height_m=max(4.0, lattice.levels[-1].z),
        width_m=max(lattice.plan.width, lattice.plan.depth),
        seismic_weight_kn=seismic_weight_kn,
        structural_system_id=selection.system_id)
    model.constitution = validate_model(typology, brief, model)
    model.life_safety = life_safety_graph(model, brief, typology=typology)
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
    _emit_site(builder)
    _emit_structure(builder, sizing, frame)
    _emit_roof(builder)
    _emit_envelope(builder, envelope, spec, opacity_override)
    _emit_circulation(builder)
    _emit_program(builder, allocation, sprinklered=sprinklered)
    _emit_partitions(builder, allocation, sprinklered=sprinklered,
                     reserved=core_reservations(lattice, datums), carve=carve)
    _emit_archetype(builder, carve)
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

    return BuildingModelV3(
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
        materials={key: MATERIAL_LIBRARY[key]
                   for key in sorted({group.material_profile
                                      for group in groups})
                   if key in MATERIAL_LIBRARY},
        accessible_route=builder.accessible_route,
        accessible_route_unresolved=builder.unresolved_accessible_route,
        element_counts=dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        layer_counts=layers,
        limitations=[
            f'{datums.coverage:.0%} of datums are score-driven; the rest are declared '
            f'design fixtures waiting on ' + ', '.join(datums.waiting_on) + '.',
            (f'Program: {allocation.delivered_area_m2:.0f} m2 delivered against '
             f'{allocation.required_area_m2:.0f} m2 briefed '
             f'({allocation.fulfilment:.0%}); '
             + ('every space fits.' if allocation.fits else
                'unplaced: ' + ', '.join(u.label for u in allocation.unplaced) + '.')),
            (f'Frame sized for {governing_occupancy.label} at '
             f'{governing_occupancy.live_kpa:.2f} kPa, the heaviest allocated room; the '
             f'column stack sums the real per-level loads.'),
            *([f'Circulation: no single stair core lies inside every plate, so '
               f'{", ".join(builder.unreached_levels)} are reached by the lift core '
               f'only. A stepped or split mass can do this and the stair stops '
               f'rather than being drawn through floors it cannot land on.']
              if builder.unreached_levels else []),
            *([builder.unresolved_accessible_route]
              if builder.unresolved_accessible_route else []),
            *([f'Accessible approach: {len(builder.accessible_route.runs)} ramp '
               f'runs at 1:'
               f'{1 / builder.accessible_route.steepest_slope:.0f} with '
               f'{len(builder.accessible_route.landings)} landings, checked against '
               + '; '.join(builder.accessible_route.citations[:3]) + '.']
              if builder.accessible_route else []),
            'Gravity only. No wind, seismic, snow, or notional lateral load.',
            'Roof truss, envelope, circulation, and furniture members are dimensioned '
            'by architectural convention; only column, girder, and joist carry a section '
            'a load calculation governed.',
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

