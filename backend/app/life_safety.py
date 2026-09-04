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
measurement follows the natural path of travel around furniture and partitions; this
walks centre to centre and adds a corridor allowance. It is the right order of magnitude
and the wrong number for a submission, and every result says so.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel

from .constitution import occupant_load

NodeKind = Literal['space', 'exit_stair', 'exit_discharge']

# --- IBC 2021 Chapter 10 -----------------------------------------------------
# 1005.3.1 stairways: 7.6 mm per occupant with sprinklers and an alarm, 5.1 mm without.
EGRESS_WIDTH_STAIR_MM = 7.6
# 1005.3.2 other egress components: 5.1 mm per occupant sprinklered, 3.8 mm otherwise.
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
    width_mm: float = 0.0


class EgressEdge(BaseModel):
    source: str
    target: str
    distance_m: float
    kind: Literal['within_floor', 'vertical']


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
        return not self.failures

    def summary(self) -> str:
        passed = sum(1 for f in self.findings if f.status == 'pass')
        return (f'{self.typology}: {self.total_occupants} occupants, '
                f'{len(self.exits)} exits, {passed}/{len(self.findings)} egress checks '
                f'passed, {len(self.failures)} failed, '
                f'{len(self.unevaluated)} not evaluable')


def _distance(a: EgressNode, b: EgressNode) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def build(model, brief, *, typology: str, sprinklered: bool = True,
          occupancy_group: str = 'A-3') -> LifeSafetyGraph:
    """Build the egress graph from an emitted model and check it against Chapter 10."""
    loads = {entry.space_id: entry for entry in occupant_load(brief)}
    nodes: list[EgressNode] = []
    edges: list[EgressEdge] = []

    # --- occupied spaces -----------------------------------------------------
    level_index = {level.id: level.index for level in model.lattice.levels}
    for zone in model.program_allocation.zones:
        entry = loads.get(zone.space_id)
        occupants = entry.occupants if entry else 1
        nodes.append(EgressNode(
            id=f'SP-{zone.level_id}-{zone.space_id}', kind='space', label=zone.label,
            level_id=zone.level_id, level_index=level_index.get(zone.level_id, 0),
            x=(zone.x0 + zone.x1) / 2.0, y=(zone.y0 + zone.y1) / 2.0,
            occupants=occupants))

    # --- exits: the stair landings on each level, and the discharge at grade --
    flight_width_mm = model.datum_set.value('flight_width_m') * 1000.0
    for element in model.elements:
        if element.kind != 'stair_landing':
            continue
        nodes.append(EgressNode(
            id=f'EX-{element.id}', kind='exit_stair', label='Protected stair',
            level_id=element.level_id,
            level_index=level_index.get(element.level_id, 0),
            x=element.position.x, y=element.position.y,
            width_mm=flight_width_mm))
    ground = model.lattice.levels[0]
    for index, element in enumerate(
            [e for e in model.elements if e.kind == 'ramp_landing'][:2]):
        nodes.append(EgressNode(
            id=f'EX-DISCHARGE-{index:02d}', kind='exit_discharge',
            label='Exit discharge at grade', level_id=ground.id, level_index=0,
            x=element.position.x, y=element.position.y,
            width_mm=max(MIN_CORRIDOR_WIDTH_MM, flight_width_mm)))

    # --- edges: every space to every exit on its own level, plus the stack ----
    by_level: dict[str, list[EgressNode]] = {}
    for node in nodes:
        by_level.setdefault(node.level_id, []).append(node)
    for level_id, group in by_level.items():
        spaces = [n for n in group if n.kind == 'space']
        exits = [n for n in group if n.kind != 'space']
        for space in spaces:
            for exit_node in exits:
                # A corridor allowance, because nobody walks the diagonal through walls.
                edges.append(EgressEdge(
                    source=space.id, target=exit_node.id,
                    distance_m=round(_distance(space, exit_node) * 1.25, 2),
                    kind='within_floor'))
    stack = sorted([n for n in nodes if n.kind == 'exit_stair'],
                   key=lambda n: n.level_index)
    for lower, upper in zip(stack, stack[1:]):
        if upper.level_index == lower.level_index + 1:
            edges.append(EgressEdge(
                source=upper.id, target=lower.id,
                distance_m=round(model.datum_set.value('floor_to_floor_m') * 2.0, 2),
                kind='vertical'))

    findings = _check(model, nodes, edges, sprinklered)
    return LifeSafetyGraph(
        typology=typology, occupancy_group=occupancy_group, sprinklered=sprinklered,
        nodes=nodes, edges=edges, findings=findings)


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
        status='pass' if worst[0] <= MAX_TRAVEL_DISTANCE_M else 'fail',
        subject=worst[1] or 'no space',
        demand=round(worst[0], 2), capacity=MAX_TRAVEL_DISTANCE_M, unit='m',
        detail=f'Longest path from a space centroid to its nearest exit, with a 1.25 '
               f'corridor factor. IBC allows {MAX_TRAVEL_DISTANCE_M:.0f} m '
               f'{"sprinklered" if sprinklered else "unsprinklered"} in Group A/B. '
               f'This is a graph distance, not a natural-path measurement.'))

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
            detail=f'{load} occupants on this storey. IBC 1006.3.2 requires '
                   f'{required}; {len(level_exits)} are modelled.'))

        # --- 1005.3.1 egress capacity ---------------------------------------
        provided = sum(n.width_mm for n in level_exits)
        needed = load * (EGRESS_WIDTH_STAIR_MM if sprinklered else 5.1)
        findings.append(EgressFinding(
            clause='1005.3.1', label=f'Egress capacity, {level_id}',
            status='pass' if provided >= needed else 'fail',
            subject=level_id, demand=round(needed, 0), capacity=round(provided, 0),
            unit='mm', detail=f'{EGRESS_WIDTH_STAIR_MM} mm per occupant for stairways '
                              f'in a sprinklered building, against the modelled clear '
                              f'width of every exit on the storey.'))

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
                detail=f'Sprinklered buildings may use one third of the '
                       f'{diagonal:.1f} m plan diagonal. The two furthest exits on this '
                       f'storey are {best:.1f} m apart.'))

    # --- 1011.2 minimum stair width -----------------------------------------
    stairs = [n for n in exits if n.kind == 'exit_stair']
    if stairs:
        narrowest = min(n.width_mm for n in stairs)
        findings.append(EgressFinding(
            clause='1011.2', label='Minimum stairway width',
            status='pass' if narrowest >= MIN_STAIR_WIDTH_MM else 'fail',
            subject='all protected stairs', demand=MIN_STAIR_WIDTH_MM,
            capacity=round(narrowest, 0), unit='mm',
            detail='IBC 1011.2 sets 1120 mm minimum clear width for a stairway serving '
                   'an occupant load of 50 or more.'))

    # --- what the graph cannot answer ---------------------------------------
    findings.extend([
        EgressFinding(
            clause='1006.2.1', label='Common path of egress travel',
            status='unevaluated', subject='every space',
            detail=f'The {MAX_COMMON_PATH_M:.0f} m limit applies to the portion of the '
                   f'path before two independent routes become available. The graph '
                   f'connects each space directly to every exit on its storey and does '
                   f'not model the corridor branch where the paths separate, so the '
                   f'measurement it would produce is not the one the clause means.'),
        EgressFinding(
            clause='1020', label='Corridor fire-resistance rating',
            status='unevaluated', subject='all corridors',
            detail='No corridor is enclosed or rated in the model, so Table 1020.1 '
                   'cannot be applied.'),
        EgressFinding(
            clause='1023', label='Interior exit stairway enclosure',
            status='unevaluated', subject='all protected stairs',
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
                   'not a designed system. Turning it off changes the required widths '
                   'and several of the distances.'),
    ])
    return findings
