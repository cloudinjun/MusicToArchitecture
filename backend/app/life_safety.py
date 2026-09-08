"""The life-safety graph: how everyone gets out, and whether the code allows it.

Until now the model knew where the stairs were and nothing about what they were for. It
drew protected stairs because a building has stairs, not because two hundred people on
the fourth floor need two of them at a combined width the occupant load sets. Those are
different claims, and only the second one is checkable.

This module builds the graph IBC Chapter 10 is written about: every occupied space is a
node, every stair and exterior door is an exit node, and the edges carry the distance a
person actually walks. Then it asks the questions a plan reviewer asks.

    1004.5    occupant load per space, from the area and the published factor
    1006.2.1  how many exits each space needs, and the common path limit
    1006.3.2  how many exits each storey needs
    1005.3    egress capacity: millimetres of width per occupant
    1017.2    exit access travel distance
    1007.1.1  remoteness, the diagonal rule

**What a graph makes possible that a checklist does not.** Travel distance is not a
property of a room; it is the length of the shortest path from the furthest point in
that room to the nearest exit, through the circulation that exists. Remoteness is a
relation between two exits and the space they serve. Both need the graph, which is why
the guideline calls for one and why counting stairs was never going to answer it.

**The distances are graph distances, not fire-model distances.** A real exit-access
measurement follows the natural path of travel around furniture and partitions. This
implementation samples each connected room component and follows the emitted free
floor around obstacles. Maximum travel, protected independence and site discharge
remain unverified, and provisional code arithmetic never becomes an approval.
"""

from __future__ import annotations

import math
import re
from typing import Literal

from pydantic import BaseModel, Field
from shapely.ops import unary_union

from .constitution import occupant_load
from .navigation import NavigationReport, build_navigation
from .geometry_review import _polygon, _z_interval

NodeKind = Literal['space', 'exit_stair', 'exit_discharge']

# --- IBC 2021 Chapter 10 -----------------------------------------------------
# Provisional screening values inherited from the original module, not a verified
# adopted-code profile. Do not apply a reduction merely because sprinklers are set.
# Exact applicability, exceptions, alarm conditions and editions remain unevaluated.
EGRESS_WIDTH_STAIR_MM = 7.6
# Provisional width for level components; no unverified sprinkler reduction.
EGRESS_WIDTH_LEVEL_MM = 5.1
# 1011.2 minimum stairway width, and 1005.2 minimum corridor width.
MIN_STAIR_WIDTH_MM = 1120.0
MIN_CORRIDOR_WIDTH_MM = 1120.0
# 1017.2 exit access travel distance, sprinklered, Group A and B.
MAX_TRAVEL_DISTANCE_M = 76.2          # 250 ft
# 1006.2.1 common path of egress travel, sprinklered Group A/B.
MAX_COMMON_PATH_M = 22.9              # 75 ft
# 1006.2.1: a space needs a second exit above this occupant load (Group A and B).
SECOND_EXIT_OCCUPANT_LOAD = 49
# 1006.3.2: a storey needs a second exit above this occupant load.
SECOND_EXIT_STOREY_LOAD = 49
# 1007.1.1 remoteness: exits at least half the diagonal apart, or a third when the
# building is sprinklered throughout and the exits are interconnected.
REMOTENESS_FRACTION_SPRINKLERED = 1.0 / 3.0


class EgressNode(BaseModel):
    id: str
    kind: NodeKind
    label: str
    level_id: str
    level_index: int
    x: float
    y: float
    occupants: int = 0
    occupant_basis: str = 'Provisional brief-area estimate; use and code profile unconfirmed'
    width_mm: float = 0.0


class EgressEdge(BaseModel):
    source: str
    target: str
    distance_m: float
    kind: Literal['within_floor', 'vertical']
    points: list[tuple[float, float]] = Field(default_factory=list)
    points_3d: list[tuple[float, float, float]] = Field(default_factory=list)
    step_count: int = 0
    source_surface_ids: list[str] = Field(default_factory=list)
    sample_id: str | None = None
    basis: str = 'Legacy route basis unverified'


class EgressFinding(BaseModel):
    clause: str
    label: str
    status: Literal['pass', 'fail', 'unevaluated']
    subject: str
    demand: float | None = None
    capacity: float | None = None
    unit: str = ''
    detail: str

    @property
    def ratio(self) -> float | None:
        if self.demand is None or not self.capacity:
            return None
        return round(self.demand / self.capacity, 3)


class LifeSafetyGraph(BaseModel):
    """Nodes, edges, and every Chapter 10 question asked of them."""

    typology: str
    occupancy_group: str
    sprinklered: bool
    nodes: list[EgressNode]
    edges: list[EgressEdge]
    findings: list[EgressFinding]
    navigation: NavigationReport | None = None

    @property
    def spaces(self) -> list[EgressNode]:
        return [n for n in self.nodes if n.kind == 'space']

    @property
    def exits(self) -> list[EgressNode]:
        return [n for n in self.nodes if n.kind != 'space']

    @property
    def total_occupants(self) -> int:
        return sum(n.occupants for n in self.spaces)

    @property
    def failures(self) -> list[EgressFinding]:
        return [f for f in self.findings if f.status == 'fail']

    @property
    def unevaluated(self) -> list[EgressFinding]:
        return [f for f in self.findings if f.status == 'unevaluated']

    @property
    def compliant(self) -> bool:
        return bool(self.findings) and not self.failures and not self.unevaluated

    def summary(self) -> str:
        passed = sum(1 for f in self.findings if f.status == 'pass')
        return (f'{self.typology}: {self.total_occupants} occupants, '
                f'{len(self.exits)} exits, {passed}/{len(self.findings)} egress checks '
                f'passed, {len(self.failures)} failed, '
                f'{len(self.unevaluated)} not evaluable')


def _distance(a: EgressNode, b: EgressNode) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def build(model, brief, *, typology: str, sprinklered: bool = True,
          occupancy_group: str = 'unconfirmed') -> LifeSafetyGraph:
    """Build the egress graph from an emitted model and check it against Chapter 10."""
    loads = {entry.space_id: entry for entry in occupant_load(brief)}
    nodes: list[EgressNode] = []
    edges: list[EgressEdge] = []
    exit_geometry_findings: list[EgressFinding] = []

    # --- occupied spaces -----------------------------------------------------
    level_index = {level.id: level.index for level in model.lattice.levels}
    for zone in model.program_allocation.zones:
        entry = loads.get(zone.space_id)
        occupants = entry.occupants if entry else 1
        occupant_basis = 'Provisional brief-area estimate; use and code profile unconfirmed'
        layout = getattr(model, 'room_layout_plan', None)
        if zone.space_type == 'auditorium' and layout is not None:
            seats = [assembly for assembly in layout.assemblies
                     if assembly.space_id == zone.space_id
                     and assembly.recipe in ('theatre_seat', 'companion_seat')]
            # Every seat needs its actual emitted sitting surface. Unplaced grid
            # positions never become occupants, nor does a generic chair elsewhere.
            actual_seats = {element.assembly_id for element in model.elements
                            if element.kind == 'seat' and element.part_role == 'seat'}
            fixed_count = sum(assembly.assembly_id in actual_seats for assembly in seats)
            wheelchair_count = sum(reservation.space_id == zone.space_id
                                   and reservation.purpose == 'wheelchair_position'
                                   for reservation in layout.reservations)
            if fixed_count or wheelchair_count:
                occupants = fixed_count + wheelchair_count
                occupant_basis = ('Count of emitted auditorium and companion sitting surfaces '
                                  'plus reserved wheelchair positions; standing areas and adopted '
                                  'occupant-load requirements remain unverified')
        nodes.append(EgressNode(
            id=f'SP-{zone.level_id}-{zone.space_id}', kind='space', label=zone.label,
            level_id=zone.level_id, level_index=level_index.get(zone.level_id, 0),
            x=(zone.x0 + zone.x1) / 2.0, y=(zone.y0 + zone.y1) / 2.0,
            occupants=occupants, occupant_basis=occupant_basis))

    # --- exits: the stair landings on each level, and the discharge at grade --
    flight_width_mm = model.datum_set.value('flight_width_m') * 1000.0
    elevations = {level.id: level.z for level in model.lattice.levels}
    floors = {}
    for element in model.elements:
        if element.kind in {'floor_slab', 'podium_slab'}:
            geometry = getattr(element, 'geometry', None)
            polygon, interval = _polygon(geometry), _z_interval(geometry)
            z = elevations.get(element.level_id)
            if polygon is not None and interval and z is not None and abs(interval[1]-z) <= .005:
                floors.setdefault(element.level_id, []).append(polygon)
    for element in model.elements:
        if element.kind != 'stair_landing' or not re.fullmatch(
                r'CIR-LND(?:[2-9]\d*)?-L\d+', element.id):
            continue
        geometry = getattr(element, 'geometry', None)
        polygon, interval = _polygon(geometry), _z_interval(geometry)
        z = elevations.get(element.level_id)
        floor_support = unary_union(floors.get(element.level_id, []))
        # Landing solids own the area removed from the plate. They must connect
        # along a usable edge; demanding a second slab below duplicates geometry.
        contact = (floor_support.buffer(1e-6).intersection(polygon.boundary).length
                   if polygon is not None else 0.0)
        if (polygon is None or interval is None or z is None or abs(interval[1]-z) > .005
                or contact < .60):
            exit_geometry_findings.append(EgressFinding(clause='NAV-STAIR-LANDING',
                label='Stair candidate landing', status='unevaluated' if polygon is None else 'fail',
                subject=element.id, detail='Landing must have measured geometry, be flush with its '
                'storey and connect along at least 0.60 m of emitted floor edge '
                '(planning probe) before it becomes a route destination.'))
            continue
        nodes.append(EgressNode(
            id=f'EX-{element.id}', kind='exit_stair', label='Stair landing (exit status unverified)',
            level_id=element.level_id,
            level_index=level_index.get(element.level_id, 0),
            x=element.position.x, y=element.position.y,
            width_mm=flight_width_mm))
    # A generic ramp landing is not a verified discharge to a public way. Do not
    # assign the first two landings to grade regardless of their actual elevation.
    # Discharge nodes await an explicit site/portal contract.

    # Only measured paths may enter the graph. A space-to-exit summary requires
    # every sampled component of that room to reach the same destination.
    navigation = build_navigation(model, nodes, getattr(model, 'portals', None))
    samples_by_space: dict[str, set[str]] = {}
    paths_by_pair: dict[tuple[str, str], list] = {}
    for sample in navigation.samples:
        samples_by_space.setdefault(sample.space_id, set()).add(sample.id)
    for route in navigation.routes:
        paths_by_pair.setdefault((route.source, route.target), []).append(route)
    incomplete_spaces = {finding.subject for finding in navigation.findings
                         if finding.id in {'NAV-SEAT-SURFACE', 'NAV-STAGE-SURFACE',
                                           'NAV-SEAT-ACCESS-UNKNOWN'}}
    for (source, target), routes in sorted(paths_by_pair.items()):
        if source in incomplete_spaces or {r.sample_id for r in routes} != samples_by_space[source]:
            continue
        worst = max(routes, key=lambda route: route.distance_m)
        edges.append(EgressEdge(source=source, target=target,
            distance_m=worst.distance_m, points=worst.points, sample_id=worst.sample_id,
            points_3d=worst.points_3d, step_count=worst.step_count,
            source_surface_ids=worst.source_surface_ids,
            kind='within_floor', basis='Longest sampled route through emitted free floor and contacting theatre steps'))
    # Keep the same stair's identity across storeys; sorting all landings together
    # can connect A-L02 to C-L01 and omit both real vertical links.
    by_stair: dict[str, list[EgressNode]] = {}
    for node in nodes:
        if node.kind == 'exit_stair':
            by_stair.setdefault(node.id.rsplit('-L', 1)[0], []).append(node)
    for stack in by_stair.values():
        stack.sort(key=lambda node: node.level_index)
        for lower, upper in zip(stack, stack[1:]):
            if upper.level_index == lower.level_index + 1:
                edges.append(EgressEdge(
                    source=upper.id, target=lower.id,
                    distance_m=round((elevations[upper.level_id] - elevations[lower.level_id]) * 2.0, 2),
                    kind='vertical', basis='Storey-height screening estimate; flight path unverified'))

    findings = _check(model, nodes, edges, sprinklered)
    findings.extend(exit_geometry_findings)
    findings.extend(EgressFinding(clause=finding.id, label='Traversable geometry',
        status='fail' if finding.status == 'failed' else 'unevaluated',
        subject=finding.subject, detail=finding.detail) for finding in navigation.findings)
    return LifeSafetyGraph(
        typology=typology, occupancy_group=occupancy_group, sprinklered=sprinklered,
        nodes=nodes, edges=edges, findings=findings, navigation=navigation)


def _check(model, nodes: list[EgressNode], edges: list[EgressEdge],
           sprinklered: bool) -> list[EgressFinding]:
    findings: list[EgressFinding] = []
    spaces = [n for n in nodes if n.kind == 'space']
    exits = [n for n in nodes if n.kind != 'space']
    by_level: dict[str, list[EgressNode]] = {}
    for node in nodes:
        by_level.setdefault(node.level_id, []).append(node)

    nearest: dict[str, float] = {}
    for edge in edges:
        if edge.kind != 'within_floor':
            continue
        current = nearest.get(edge.source)
        if current is None or edge.distance_m < current:
            nearest[edge.source] = edge.distance_m

    # --- 1017.2 exit access travel distance ---------------------------------
    worst = max(((value, key) for key, value in nearest.items()), default=(0.0, ''))
    findings.append(EgressFinding(
        clause='1017.2', label='Exit access travel distance',
        status=('unevaluated' if not nearest else
                'pass' if worst[0] <= MAX_TRAVEL_DISTANCE_M else 'fail'),
        subject=worst[1] or 'no space',
        demand=round(worst[0], 2) if nearest else None, capacity=MAX_TRAVEL_DISTANCE_M, unit='m',
        detail=f'Longest sampled room-to-stair route through the obstacle-aware floor graph. '
               f'Unreachable and unsampled spaces remain separate findings. '
               f'The inherited screening threshold is '
               f'{MAX_TRAVEL_DISTANCE_M:.0f} m; its adopted-code applicability '
               f'is unverified (sprinkler input: {sprinklered}). '
               f'This sampled path does not establish maximum natural-path travel.'))

    # --- 1006.2.1 spaces with only one way out ------------------------------
    for level_id, group in sorted(by_level.items()):
        level_spaces = [n for n in group if n.kind == 'space']
        level_exits = [n for n in group if n.kind != 'space']
        if not level_spaces:
            continue
        load = sum(n.occupants for n in level_spaces)
        required = 2 if load > SECOND_EXIT_STOREY_LOAD else 1
        if load > 500:
            required = 3
        if load > 1000:
            required = 4
        findings.append(EgressFinding(
            clause='1006.3.2', label=f'Number of exits, {level_id}',
            status='pass' if len(level_exits) >= required else 'fail',
            subject=level_id, demand=float(required),
            capacity=float(len(level_exits)), unit='exits',
            detail=f'{load} occupants from the node-specific stated bases. The inherited screening '
                   f'table asks for {required}; {len(level_exits)} stair candidates '
                   f'are modelled. Adopted-code applicability is unverified.'))

        # --- 1005.3.1 egress capacity ---------------------------------------
        provided = sum(n.width_mm for n in level_exits)
        needed = load * EGRESS_WIDTH_STAIR_MM
        findings.append(EgressFinding(
            clause='1005.3.1', label=f'Egress capacity, {level_id}',
            status='pass' if provided >= needed else 'fail',
            subject=level_id, demand=round(needed, 0), capacity=round(provided, 0),
            unit='mm', detail=f'{EGRESS_WIDTH_STAIR_MM} mm per occupant for stairways '
                              f'is the unreduced screening basis, against the modelled '
                              f'width of stair candidates. This is not a verified '
                              f'capacity calculation for actual exit components.'))

        # --- 1007.1.1 remoteness --------------------------------------------
        if len(level_exits) >= 2:
            level = next(lv for lv in model.lattice.levels if lv.id == level_id)
            xs = [p.x for p in level.plate]
            ys = [p.y for p in level.plate]
            diagonal = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
            best = max(_distance(a, b)
                       for i, a in enumerate(level_exits)
                       for b in level_exits[i + 1:])
            required_gap = diagonal * REMOTENESS_FRACTION_SPRINKLERED
            findings.append(EgressFinding(
                clause='1007.1.1', label=f'Exit remoteness, {level_id}',
                status='pass' if best >= required_gap else 'fail',
                subject=level_id, demand=round(required_gap, 2),
                capacity=round(best, 2), unit='m',
                detail=f'The inherited screening ratio is one third of the '
                       f'{diagonal:.1f} m plan diagonal. Applicability is unverified. '
                       f'The two furthest stair candidates are {best:.1f} m apart.'))

    # --- 1011.2 minimum stair width -----------------------------------------
    stairs = [n for n in exits if n.kind == 'exit_stair']
    if stairs:
        narrowest = min(n.width_mm for n in stairs)
        findings.append(EgressFinding(
            clause='1011.2', label='Minimum stairway width',
            status='pass' if narrowest >= MIN_STAIR_WIDTH_MM else 'fail',
            subject='all stair candidates', demand=MIN_STAIR_WIDTH_MM,
            capacity=round(narrowest, 0), unit='mm',
            detail='The inherited width screening threshold is 1120 mm. '
                   'Actual clearances, occupant basis and adopted code are unverified.'))

    # --- what the graph cannot answer ---------------------------------------
    findings.extend([
        EgressFinding(
            clause='1006.2.1', label='Common path of egress travel',
            status='unevaluated', subject='every space',
            detail=f'The {MAX_COMMON_PATH_M:.0f} m limit applies to the portion of the '
                   f'path before two independent routes become available. The graph '
                   f'has measured obstacle-aware routes, but shared segments and '
                   f'independent protected branches have not been classified.'),
        EgressFinding(
            clause='1020', label='Corridor fire-resistance rating',
            status='unevaluated', subject='all corridors',
            detail='No corridor is enclosed or rated in the model, so Table 1020.1 '
                   'cannot be applied.'),
        EgressFinding(
            clause='1023', label='Interior exit stairway enclosure',
            status='unevaluated', subject='all stair candidates',
            detail='Stairs are drawn as flights and landings, not as rated enclosures '
                   'with rated openings. Calling them protected is a label the model '
                   'does not yet earn.'),
        EgressFinding(
            clause='1009', label='Accessible means of egress',
            status='unevaluated', subject='all storeys',
            detail='Areas of refuge, their size and their two-way communication are not '
                   'modelled. A lift is present but is not an accessible means of '
                   'egress unless it meets 1009.4.'),
        EgressFinding(
            clause='906 / 907', label='Fire protection and alarm systems',
            status='unevaluated', subject='the building',
            detail='The sprinkler assumption every width above depends on is an input, '
                   'not a designed system. No sprinkler-based reduction is applied; '
                   'the applicable code profile and systems require review.'),
    ])
    findings.append(EgressFinding(
        clause='1028', label='Exit discharge to the site', status='unevaluated',
        subject='the building',
        detail='No verified site/portal connection to a public way has been modelled. '
               'Ramp landing order is not evidence of discharge.'))
    for finding in findings:
        if finding.status == 'pass':
            finding.status = 'unevaluated'
            finding.detail += (' Screening arithmetic only: the adopted code profile, '
                               'occupant basis and actual traversable portal/route geometry '
                               'are not verified. This is not a code-compliance pass.')
    return findings
