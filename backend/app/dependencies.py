"""Typed construction dependencies for schema 3.0.

This module compiles the emitted element groups into one directed graph covering two
different questions:

* where gravity and lateral actions return to the foundation/soil root;
* which host or carrier an architectural assembly is installed on.

The graph verifies topology, element identity and selected geometric interfaces.  It
does not design plates, bolts, welds, anchors, fasteners, reinforcement, or soil bearing
capacity; those remain visibly ``not_checked`` on every relation and on the report.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
import re
from typing import Iterable

from .geometry import BoxGeometry, ExtrusionGeometry, MemberGeometry, QuadGeometry, Vector3
from .models_v3 import (
    DependencyCheck, DependencyEdge, DependencyExemption, DependencyGraph,
    DependencyRelationGroup, DependencyRoot, ElementDependency, ElementGroup,
    ElementInstance,
)


SOIL_ROOT = DependencyRoot(
    id='ROOT-SOIL', kind='soil', topology_status='unresolved',
    capacity_status='not_checked',
    reason=('External geotechnical root. Foundation topology terminates here; bearing, '
            'settlement, uplift and lateral resistance require verified site data.'),
)

_STATION = re.compile(r'-(L\d+)-S(\d{3})')
_FLIGHT = re.compile(r'CIR-(?:TRD|STG)-([A-Z]\d{2})')
_RAMP_INDEX = re.compile(r'RMP-(?:RUN|CURB)-(\d{2})')

_EXEMPT_KINDS = {
    'program_zone': 'Semantic program overlay; it describes ownership and area, not a constructed object.',
    'figure': 'Scale-reference figure; excluded from the building construction graph.',
}

_FACADE_CARRIERS = {
    'wall_panel', 'mullion', 'backing_panel', 'lattice_mullion', 'frame_expression',
    'field_carrier', 'order_jamb', 'external_strut',
}

_FACADE_INFILL = {
    'transom', 'glazing_panel', 'spandrel_panel', 'solid_wall_panel', 'brise_soleil',
    'screen_fin', 'window_reveal', 'window_head', 'sill', 'slot_opening',
    'lattice_cell', 'lattice_transom', 'field_panel', 'facet_panel', 'facet_glazing',
    'seam_edge', 'order_lintel', 'order_field',
    # The entrance is infill like any other panel: it hangs on the same carrier the
    # bay's glazing would have hung on. What makes it an entrance is that it is a hole
    # you can walk through, not a different way of being attached.
    'entrance_door', 'entrance_head',
}

_MINIMUM_HOSTS = {
    'primary_beam': 2,
    'secondary_joist': 2,
    'heavy_joist': 2,
    'clt_panel': 2,
    'purlin': 2,
    'stair_tread': 2,
}


@dataclass(frozen=True)
class _Record:
    group: ElementGroup
    instance: ElementInstance

    @property
    def id(self) -> str:
        return self.instance.id

    @property
    def kind(self) -> str:
        return self.group.kind

    @property
    def layer(self) -> str:
        return self.group.semantic_layer

    @property
    def level_id(self) -> str:
        return self.instance.level_id

    @property
    def centre(self) -> Vector3:
        return self.instance.position


def _flatten(groups: Iterable[ElementGroup]) -> list[_Record]:
    return [_Record(group, instance) for group in groups for instance in group.instances]


def _distance(a: Vector3, b: Vector3) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def _point_segment_distance(point: Vector3, a: Vector3, b: Vector3) -> float:
    vx, vy, vz = b.x - a.x, b.y - a.y, b.z - a.z
    wx, wy, wz = point.x - a.x, point.y - a.y, point.z - a.z
    length2 = vx * vx + vy * vy + vz * vz
    if length2 <= 1e-12:
        return _distance(point, a)
    t = max(0.0, min(1.0, (wx * vx + wy * vy + wz * vz) / length2))
    closest = Vector3(x=a.x + vx * t, y=a.y + vy * t, z=a.z + vz * t)
    return _distance(point, closest)


def _distance_to(record: _Record, point: Vector3) -> float:
    geometry = record.instance.geometry
    if isinstance(geometry, MemberGeometry):
        return min(_point_segment_distance(point, a, b)
                   for a, b in zip(geometry.path, geometry.path[1:]))
    if isinstance(geometry, QuadGeometry):
        return min(_distance(point, corner) for corner in geometry.corners)
    if isinstance(geometry, BoxGeometry):
        return _distance(point, geometry.center)
    if isinstance(geometry, ExtrusionGeometry):
        z = (geometry.z_base + geometry.z_top) / 2.0
        return min(math.sqrt((point.x - p.x) ** 2 + (point.y - p.y) ** 2
                             + (point.z - z) ** 2)
                   for p in geometry.boundary)
    return _distance(point, record.centre)


# What `geometry_checked` is allowed to mean. Two elements are in contact when their
# geometries come within this of each other; members are stored as centre-lines, so a
# member end of the pair is credited half a generous section depth on top.
# Each switchback stair is two flights, and the half landing between them is carried by
# both. These are the names the circulation emitter gives those flights -- A/B the
# primary, C/D the remote second, then one pair per extra core covering the storeys the
# second stops short of -- and this is the single place the pairing is written down.
#
# It used to be a two-case guess in the hosting rule below: `('A','B') if the token
# starts with A else ('C','D')`. The day a third core appeared, its half landings looked
# for stringers that do not exist, matched nothing, and hung off the dependency graph
# entirely -- two elements of a building with no support and no exemption, which is the
# exact condition DEP-REQUIRED-COVERAGE exists to catch.
PRIMARY_FLIGHT_PAIR = ('A', 'B')
SECOND_FLIGHT_PAIR = ('C', 'D')
EXTRA_FLIGHT_PAIRS = (('G', 'H'), ('J', 'K'))
FLIGHT_PAIRS = {pair[0]: pair for pair in
                (PRIMARY_FLIGHT_PAIR, SECOND_FLIGHT_PAIR, *EXTRA_FLIGHT_PAIRS)}


CONTACT_M = 0.35
MEMBER_SLACK_M = 0.30


def _vertices(geometry) -> list[Vector3]:
    if isinstance(geometry, MemberGeometry):
        return list(geometry.path)
    if isinstance(geometry, QuadGeometry):
        return list(geometry.corners)
    if isinstance(geometry, BoxGeometry):
        centre, size = geometry.center, geometry.size
        angle = geometry.rotation_z
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        out = []
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    lx, ly = sx * size.x / 2.0, sy * size.y / 2.0
                    out.append(Vector3(x=centre.x + lx * cos_a - ly * sin_a,
                                       y=centre.y + lx * sin_a + ly * cos_a,
                                       z=centre.z + sz * size.z / 2.0))
        return out
    if isinstance(geometry, ExtrusionGeometry):
        return [Vector3(x=p.x, y=p.y, z=z) for p in geometry.boundary
                for z in (geometry.z_base, geometry.z_top)]
    return []


def _point_to_geometry(point: Vector3, geometry) -> float:
    """Distance from a point to a geometry, zero inside or on it."""
    if isinstance(geometry, MemberGeometry):
        return min(_point_segment_distance(point, a, b)
                   for a, b in zip(geometry.path, geometry.path[1:]))
    if isinstance(geometry, BoxGeometry):
        centre, size = geometry.center, geometry.size
        angle = geometry.rotation_z
        cos_a, sin_a = math.cos(-angle), math.sin(-angle)
        rx, ry = point.x - centre.x, point.y - centre.y
        lx, ly = rx * cos_a - ry * sin_a, rx * sin_a + ry * cos_a
        gaps = (max(0.0, abs(lx) - size.x / 2.0), max(0.0, abs(ly) - size.y / 2.0),
                max(0.0, abs(point.z - centre.z) - size.z / 2.0))
        return math.sqrt(sum(g * g for g in gaps))
    if isinstance(geometry, ExtrusionGeometry):
        boundary, inside = geometry.boundary, False
        count = len(boundary)
        for i in range(count):
            a, c = boundary[i], boundary[(i + 1) % count]
            if (a.y > point.y) != (c.y > point.y):
                if point.x < (c.x - a.x) * (point.y - a.y) / (c.y - a.y) + a.x:
                    inside = not inside
        flat = 0.0 if inside else min(
            _point_segment_distance(Vector3(x=point.x, y=point.y, z=0.0),
                                    Vector3(x=boundary[i].x, y=boundary[i].y, z=0.0),
                                    Vector3(x=boundary[(i + 1) % count].x,
                                            y=boundary[(i + 1) % count].y, z=0.0))
            for i in range(count))
        vertical = max(0.0, geometry.z_base - point.z, point.z - geometry.z_top)
        return math.hypot(flat, vertical)
    if isinstance(geometry, QuadGeometry):
        corners = geometry.corners
        return min(_point_segment_distance(point, corners[i], corners[(i + 1) % 4])
                   for i in range(4))
    return 1e9


def _contact_gap(dependent: _Record, host: _Record) -> float:
    """How far apart the two elements actually are, measured both ways.

    One direction is not enough. A slab corner is ten metres from the nearest joist
    while the whole underside rests on the joist field, so measuring only the
    dependent's vertices against the host reports a bearing that plainly exists as a
    ten-metre gap. The reverse direction catches it.
    """
    ours, theirs = dependent.instance.geometry, host.instance.geometry
    here, there = _vertices(ours), _vertices(theirs)
    if not here or not there:
        return 1e9
    gap = min(min(_point_to_geometry(p, theirs) for p in here),
              min(_point_to_geometry(q, ours) for q in there))
    slack = (MEMBER_SLACK_M if isinstance(ours, MemberGeometry) else 0.0)         + (MEMBER_SLACK_M if isinstance(theirs, MemberGeometry) else 0.0)
    return max(0.0, gap - slack)


def _nearest(source: _Record, candidates: Iterable[_Record], count: int = 1,
             *, same_station: bool = False, within: float | None = None) -> list[_Record]:
    pool = list(candidates)
    if not pool:
        return []
    station = _STATION.search(source.id)
    if same_station and station:
        keyed = [candidate for candidate in pool
                 if (match := _STATION.search(candidate.id))
                 and match.groups() == station.groups()]
        if keyed:
            pool = keyed
    # Ranked by the gap between the two geometries, not between their centroids. A
    # centroid stands in for an element only when the element is small and compact: a
    # guard rail running the length of a floor edge has its centroid out in the middle
    # of the run, which put the nearest stair tread closer than the slab it is bolted
    # to and handed a floor-edge guard a host twenty-four metres away.
    ranked = sorted(pool, key=lambda candidate: (_contact_gap(source, candidate),
                                                 candidate.id))[:count]
    if within is None:
        return ranked
    # `count` is how many hosts the element *can* have, not how many it has. The first
    # ramp run rises from grade and touches one landing, so asking for two handed it a
    # second one at the far end of the switchback.
    return [candidate for candidate in ranked
            if _contact_gap(source, candidate) <= within]


def _slab_above(record: _Record, by_id: dict, records) -> str | None:
    """The nearest floor slab whose underside sits above this element."""
    top = record.centre.z + record.instance.dimensions.z / 2.0
    best: tuple[float, str] | None = None
    for candidate in records:
        if candidate.kind != 'floor_slab':
            continue
        base = candidate.centre.z - candidate.instance.dimensions.z / 2.0
        if base < top - 0.01:
            continue
        gap = base - top
        if best is None or gap < best[0]:
            best = (gap, candidate.id)
    return best[1] if best else None


def _relation_family(dependent: _Record, host: _Record | None, relation: str) -> str:
    if relation == 'anchors_to':
        return 'foundation_bearing_pending_geotechnical'
    if dependent.kind in ('column', 'piloti_column'):
        return ('cast_in_place_vertical_joint_concept'
                if dependent.group.material_profile == 'concrete'
                else 'column_base_or_splice_concept')
    if dependent.layer == 'structure':
        return ('cast_in_place_structural_joint_concept'
                if dependent.group.material_profile == 'concrete'
                else 'bolted_or_welded_structural_joint_concept')
    if dependent.layer == 'envelope':
        return 'adjustable_bracket_and_anchor_concept'
    if dependent.layer == 'circulation':
        return 'bearing_or_mechanical_fastener_concept'
    if dependent.kind in ('partition', 'partition_head', 'door'):
        return 'track_frame_and_opening_anchor_concept'
    return 'bearing_or_mechanical_attachment_concept'


def _group_relations(relations: list[ElementDependency]) -> list[DependencyRelationGroup]:
    grouped: dict[tuple[str, ...], list[DependencyEdge]] = defaultdict(list)
    for relation in relations:
        key = (relation.relation, relation.role, relation.connection_family,
               relation.topology_status, relation.capacity_status, relation.basis)
        grouped[key].append(DependencyEdge(
            dependent_id=relation.dependent_id, host_id=relation.host_id))
    out: list[DependencyRelationGroup] = []
    for index, (key, edges) in enumerate(sorted(grouped.items()), start=1):
        relation, role, family, topology, capacity, basis = key
        out.append(DependencyRelationGroup(
            group_id=f'DEP-GRP-{role}-{relation}-{index:03d}',
            relation=relation, role=role, connection_family=family,
            topology_status=topology, capacity_status=capacity, basis=basis,
            edges=sorted(edges, key=lambda edge: (edge.dependent_id, edge.host_id))))
    return out


def compile_dependency_graph(groups: list[ElementGroup]) -> DependencyGraph:
    """Compile and validate the complete dependency graph in-place.

    Legacy ``instance.supports`` is regenerated from the typed graph for existing
    consumers.  External roots stay only in the typed graph so a legacy consumer never
    mistakes ``ROOT-SOIL`` for generated geometry.
    """

    records = _flatten(groups)
    by_id = {record.id: record for record in records}
    by_kind: dict[str, list[_Record]] = defaultdict(list)
    by_level: dict[str, list[_Record]] = defaultdict(list)
    declared = {record.id: list(record.instance.supports) for record in records}
    for record in records:
        by_kind[record.kind].append(record)
        by_level[record.level_id].append(record)
        record.instance.supports = []

    relations: dict[tuple[str, str, str, str], ElementDependency] = {}
    exemptions = [DependencyExemption(element_id=record.id, reason=_EXEMPT_KINDS[record.kind])
                  for record in records if record.kind in _EXEMPT_KINDS]
    root_ids = {SOIL_ROOT.id}

    downgraded: list[tuple[str, str, float]] = []

    def add(dependent: _Record, host_id: str, relation: str, role: str, basis: str,
            *, topology: str = 'rule_checked') -> None:
        if host_id not in by_id and host_id not in root_ids:
            return
        host = by_id.get(host_id)
        if topology == 'geometry_checked' and host is not None:
            # Earn the claim. `geometry_checked` was a literal written at each call
            # site, so eight thousand relations per model asserted a check that no
            # code performed -- and several of them were wrong by metres. A status
            # that reports itself is worth less than no status, because a reader
            # stops looking. Where the geometry does not confirm contact the relation
            # is still recorded; it just says a rule placed it, which is the truth.
            gap = _contact_gap(dependent, host)
            if gap > CONTACT_M:
                downgraded.append((dependent.id, host_id, gap))
                topology = 'rule_checked'
        key = (dependent.id, host_id, relation, role)
        relations[key] = ElementDependency(
            id=f'DEP-{dependent.id}-TO-{host_id}-{relation}',
            dependent_id=dependent.id, host_id=host_id, relation=relation, role=role,
            connection_family=_relation_family(dependent, host, relation),
            topology_status=topology, capacity_status='not_checked', basis=basis)
        if host_id in by_id and host_id not in dependent.instance.supports:
            dependent.instance.supports.append(host_id)

    # Structural emitters own their support topology.  These edges have already been
    # derived from the registration lattice; this stage types them and rejects drift.
    for record in records:
        if record.kind == 'footing':
            add(record, SOIL_ROOT.id, 'anchors_to', 'gravity',
                'Foundation terminates the generated gravity graph at the explicit soil root.',
                topology='unresolved')
            continue
        if record.layer != 'structure' and record.kind not in {'roof_deck', 'parapet'}:
            continue
        role = ('lateral' if record.kind in
                {'brace', 'shear_wall', 'core_wall', 'knee_brace'} else 'gravity')
        relation = ('fastens_to' if role == 'lateral' else 'bears_on')
        for host_id in declared[record.id]:
            add(record, host_id, relation, role,
                'Emitter-declared relation derived from shared lattice indices.',
                topology='geometry_checked')

    def floor_host(record: _Record) -> str | None:
        slab = f'STR-SLB-{record.level_id}'
        if slab in by_id:
            return slab
        if record.level_id == 'L00' and 'SIT-POD-001' in by_id:
            return 'SIT-POD-001'
        return 'SIT-GRD-001' if 'SIT-GRD-001' in by_id else None

    # Envelope hierarchy: infill -> local carrier -> floor/slab edge -> structure.
    facade = [record for record in records if record.layer == 'envelope']
    carriers = [record for record in facade if record.kind in _FACADE_CARRIERS]
    canopy_posts = [record for record in by_kind['entry_canopy']
                    if record.id.startswith('ENV-CAN-POST-')]
    for record in facade:
        if record.kind in {'roof_deck', 'parapet'}:
            continue
        if record.id.startswith('ENV-CAN-POST-'):
            # A canopy post stands at the entrance, on grade. `floor_host` reads the
            # level it is tagged with and returns that level's slab, which is the plate
            # overhead -- the post was recorded as bearing on the floor above it.
            ground = ('SIT-POD-001' if 'SIT-POD-001' in by_id
                      else 'SIT-GRD-001' if 'SIT-GRD-001' in by_id else None)
            if ground:
                add(record, ground, 'bears_on', 'gravity',
                    'Entry canopy post bears on the podium or grade it stands on.',
                    topology='geometry_checked')
            continue
        if record.id == 'ENV-CAN-ENTRY':
            for host in canopy_posts:
                add(record, host.id, 'bears_on', 'gravity',
                    'Entry canopy plate bears on both generated canopy posts.',
                    topology='geometry_checked')
            continue
        if record in canopy_posts:
            host = floor_host(record)
            if host:
                add(record, host, 'bears_on', 'gravity',
                    'Canopy post returns to the podium/floor support.',
                    topology='geometry_checked')
            continue
        if record.kind in _FACADE_CARRIERS:
            host = floor_host(record)
            if host:
                add(record, host, 'fastens_to', 'assembly',
                    'Primary facade carrier anchors to the structural slab edge.',
                    topology='rule_checked')
            continue
        if record.kind in _FACADE_INFILL:
            local = [candidate for candidate in carriers
                     if candidate.level_id == record.level_id and candidate.id != record.id]
            wanted = 2 if record.kind in {'glazing_panel', 'facet_glazing',
                                          'spandrel_panel', 'solid_wall_panel'} else 1
            hosts = _nearest(record, local, wanted, same_station=True)
            if hosts:
                for host in hosts:
                    add(record, host.id, 'fastens_to', 'assembly',
                        'Facade infill installs on the nearest carrier in its registered bay.',
                        topology='rule_checked')
            else:
                host = floor_host(record)
                if host:
                    add(record, host, 'fastens_to', 'assembly',
                        'No separate carrier family exists in this grammar; the element '
                        'anchors directly to the structural edge.', topology='rule_checked')

    # Circulation assemblies.  Flights use their stable flight token, while landings,
    # edge rails and shafts return directly to the floor they serve.
    stringers = by_kind['stair_stringer']
    for record in records:
        if record.layer != 'circulation':
            continue
        if record.kind == 'stair_tread':
            match = _FLIGHT.search(record.id)
            hosts = ([candidate for candidate in stringers
                      if match and f'CIR-STG-{match.group(1)}-' in candidate.id])
            for host in hosts:
                add(record, host.id, 'bears_on', 'gravity',
                    'Tread bears on the two stringers generated for its flight.',
                    topology='geometry_checked')
        elif record.kind == 'stair_stringer':
            host = floor_host(record)
            if host:
                add(record, host, 'bears_on', 'gravity',
                    'Stringer returns the flight to its served floor/podium.',
                    topology='rule_checked')
        elif record.kind == 'stair_landing':
            host = floor_host(record)
            if host:
                add(record, host, 'bears_on', 'gravity',
                    'Floor landing is flush with the served slab and abuts its edge; '
                    'the slab gives up the landing footprint so one surface owns it.',
                    topology='geometry_checked')
        elif record.kind == 'door':
            # A lift landing door sits in the shaft wall of its own level. Partition
            # doors are hosted below with their partition run; this one has none.
            shaft = f'CIR-SHF-{record.level_id}'
            host_id = shaft if shaft in by_id else f'CIR-SHF-{record.level_id}-OVR'
            if host_id in by_id:
                add(record, host_id, 'hosts', 'assembly',
                    'Lift landing door is an opening in the shaft segment of its level.',
                    topology='rule_checked')
        elif record.kind == 'stair_half_landing':
            token = record.id.rsplit('-', 1)[-1]
            number = token[1:] if len(token) > 1 else token
            flight_letters = FLIGHT_PAIRS.get(token[:1], ())
            hosts = [candidate for candidate in stringers
                     if any(f'CIR-STG-{letter}{number}-' in candidate.id
                            for letter in flight_letters)]
            for host in hosts:
                add(record, host.id, 'bears_on', 'gravity',
                    'Half landing is carried by the adjacent switchback stringers.',
                    topology='rule_checked')
        elif record.kind == 'ramp':
            landings = _nearest(record, by_kind['ramp_landing'], 2,
                                within=CONTACT_M)
            for host in landings:
                add(record, host.id, 'bears_on', 'gravity',
                    'Ramp run bears between its adjacent landings.',
                    topology='geometry_checked')
        elif record.kind == 'ramp_landing':
            host = 'SIT-POD-001' if 'SIT-POD-001' in by_id else floor_host(record)
            if host:
                add(record, host, 'bears_on', 'gravity',
                    'Accessible-route landing returns to the podium/site support.',
                    topology='rule_checked')
        elif record.kind == 'ramp_curb':
            match = _RAMP_INDEX.search(record.id)
            host_id = f'CIR-RMP-RUN-{match.group(1)}' if match else ''
            add(record, host_id, 'fastens_to', 'assembly',
                'Ramp curb fastens to the run with the same stable run index.',
                topology='geometry_checked')
        elif record.kind == 'railing':
            local_bases = [candidate for candidate in by_level[record.level_id]
                           if candidate.kind in {'stair_tread', 'stair_stringer', 'ramp',
                                                 'ramp_landing', 'floor_slab'}]
            hosts = _nearest(record, local_bases, 1)
            if hosts:
                add(record, hosts[0].id, 'fastens_to', 'assembly',
                    'Guard/handrail post or rail anchors to the nearest walking surface '
                    'or stair carrier on its level.', topology='rule_checked')
        elif record.kind == 'elevator_shaft':
            host = floor_host(record)
            if host:
                add(record, host, 'bears_on', 'gravity',
                    'Shaft segment returns to the floor/podium at its base level.',
                    topology='rule_checked')

    # Interior construction and movable objects.  Program zones and scale figures were
    # exempted above; partitions, openings and furniture still need a real host.
    partitions = by_kind['partition']
    for record in records:
        if record.layer != 'program' or record.kind in _EXEMPT_KINDS:
            continue
        if record.kind == 'ceiling':
            # A ceiling hangs; it does not bear. `floor_host` would return the slab of
            # its own level, which is the floor underneath it -- the one relation a
            # suspended ceiling definitely does not have. It is hung from the structure
            # above, so the host is the next slab up.
            above = _slab_above(record, by_id, records)
            if above:
                add(record, above, 'hangs_from', 'gravity',
                    'Suspended ceiling hung from the floor structure above it.',
                    topology='geometry_checked')
            continue
        if (record.kind in {'desk', 'seat', 'shelving_run'}
                and record.instance.assembly_id is not None):
            # The emitter declares real subassembly edges. Replacing these with
            # floor_host made a floating tabletop look supported by the slab.
            for host_id in declared[record.id]:
                add(record, host_id, 'bears_on', 'assembly',
                    'Declared furniture part-to-part or part-to-floor contact; '
                    'strict assembly checks also measure each interface.',
                    topology='geometry_checked')
            continue
        if record.kind in {'partition', 'shelving_run', 'desk', 'seat',
                           'auditorium_riser', 'stage_platform', 'proscenium_wall'}:
            host = floor_host(record)
            if host:
                anchored = record.kind in ('partition', 'proscenium_wall')
                add(record, host, 'fastens_to' if anchored else 'bears_on',
                    'assembly' if anchored else 'gravity',
                    'Element bears on or anchors to the generated floor serving its level.',
                    topology='rule_checked')
        elif record.kind in {'partition_head', 'door'}:
            prefix = record.id.rsplit('-', 1)[0]
            local = [candidate for candidate in partitions
                     if candidate.id.startswith(prefix.rsplit('-', 1)[0])]
            for host in _nearest(record, local, 2):
                add(record, host.id, 'hosts', 'assembly',
                    'Opening/head is hosted by the partition run that generated it.',
                    topology='rule_checked')

    # Site construction.  Grade visualization remains exempt; podium and approach
    # pieces have explicit paths without pretending the soil capacity was checked.
    for record in records:
        if record.kind == 'site_ground':
            add(record, SOIL_ROOT.id, 'hosts', 'context',
                'The grade mesh visualises the external soil root without claiming soil capacity.',
                topology='unresolved')
        elif record.kind == 'podium_slab':
            add(record, SOIL_ROOT.id, 'anchors_to', 'gravity',
                'Podium terminates at the external soil root; geotechnical design is pending.',
                topology='unresolved')
        elif record.kind == 'site_step':
            add(record, 'SIT-GRD-001', 'bears_on', 'context',
                'Approach step bears on the represented grade surface.',
                topology='geometry_checked')

    relation_list = sorted(relations.values(), key=lambda relation: relation.id)
    relation_by_dependent: dict[str, list[ElementDependency]] = defaultdict(list)
    for relation in relation_list:
        relation_by_dependent[relation.dependent_id].append(relation)

    exempt_ids = {item.element_id for item in exemptions}
    required = [record for record in records if record.id not in exempt_ids]
    uncovered = sorted(record.id for record in required if not relation_by_dependent[record.id])

    dangling = sorted({relation.host_id for relation in relation_list
                       if relation.host_id not in by_id and relation.host_id not in root_ids})
    self_refs = sorted(relation.dependent_id for relation in relation_list
                       if relation.dependent_id == relation.host_id)

    # Directed cycles among generated elements.  Roots terminate traversal.
    adjacency: dict[str, list[str]] = defaultdict(list)
    for relation in relation_list:
        adjacency[relation.dependent_id].append(relation.host_id)
    state: dict[str, int] = {}
    cycles: set[str] = set()

    def visit(element_id: str, trail: tuple[str, ...]) -> None:
        state[element_id] = 1
        for host_id in adjacency[element_id]:
            if state.get(host_id) == 1:
                cycles.update(trail + (host_id,))
            elif state.get(host_id, 0) == 0:
                visit(host_id, trail + (host_id,))
        state[element_id] = 2

    for element_id in by_id:
        if state.get(element_id, 0) == 0:
            visit(element_id, (element_id,))

    def reaches_soil(element_id: str, seen: frozenset[str] = frozenset()) -> bool:
        if element_id in seen:
            return False
        return any(
            relation.host_id == SOIL_ROOT.id
            or (relation.host_id in by_id
                and reaches_soil(relation.host_id, seen | {element_id}))
            for relation in relation_by_dependent[element_id]
        )

    structural = [record for record in records if record.layer == 'structure']
    no_gravity_path = sorted(record.id for record in structural if not reaches_soil(record.id))

    no_host_path = sorted(
        record.id for record in required
        if record.layer != 'structure'
        and not any(host_id in root_ids or by_id.get(host_id, record).layer == 'structure'
                    for host_id in _reachable_hosts(record.id, adjacency)))

    insufficient = []
    for record in required:
        minimum = _MINIMUM_HOSTS.get(record.kind)
        if minimum is not None and len(relation_by_dependent[record.id]) < minimum:
            insufficient.append(record.id)

    endpoint_failures = _check_member_endpoints(records, relation_by_dependent, by_id)

    checks = [
        DependencyCheck(
            id='DEP-REFERENCE-INTEGRITY', status='passed' if not dangling and not self_refs else 'failed',
            message=('Every dependency target resolves to an element or declared external root.'
                     if not dangling and not self_refs else
                     'Some dependencies are dangling or self-referential.'),
            affected_ids=sorted(set(dangling + self_refs))),
        DependencyCheck(
            id='DEP-REQUIRED-COVERAGE', status='passed' if not uncovered else 'failed',
            message=('Every constructed element has a dependency; semantic/context objects '
                     'carry explicit exemptions.' if not uncovered else
                     'Some constructed elements have no dependency or exemption.'),
            affected_ids=uncovered),
        DependencyCheck(
            id='DEP-ACYCLIC', status='passed' if not cycles else 'failed',
            message='Dependency directions are acyclic.' if not cycles else
                    'Dependency graph contains a cycle.',
            affected_ids=sorted(cycles)),
        DependencyCheck(
            id='DEP-STRUCTURE-TO-SOIL', status='passed' if not no_gravity_path else 'failed',
            message=('Every structural element reaches the external soil root through an '
                     'explicit chain.' if not no_gravity_path else
                     'Some structural elements do not reach the soil root.'),
            affected_ids=no_gravity_path),
        DependencyCheck(
            id='DEP-ASSEMBLY-TO-STRUCTURE', status='passed' if not no_host_path else 'failed',
            message=('Every non-structural constructed element reaches structure or an '
                     'external root.' if not no_host_path else
                     'Some assemblies do not reach structure or an external root.'),
            affected_ids=no_host_path),
        DependencyCheck(
            id='DEP-MINIMUM-SUPPORTS', status='passed' if not insufficient else 'failed',
            message=('Two-ended spanning members and stair treads declare both hosts.'
                     if not insufficient else 'Some two-ended elements are missing a host.'),
            affected_ids=sorted(insufficient)),
        DependencyCheck(
            id='DEP-MEMBER-END-GEOMETRY', status='passed' if not endpoint_failures else 'failed',
            message=('Checked member ends land within the declared support tolerance.'
                     if not endpoint_failures else
                     'Some spanning-member ends do not meet their declared hosts.'),
            affected_ids=endpoint_failures),
        DependencyCheck(
            id='DEP-GEOMETRY-CLAIMS', status='passed',
            message=(
                f'{len(downgraded)} relations claimed a geometric check the geometry '
                f'does not support and were recorded as rule-placed instead.'
                if downgraded else
                'Every relation claiming a geometric check was measured and confirmed.'),
            affected_ids=sorted({dependent_id for dependent_id, _host, _gap
                                 in downgraded})),
        DependencyCheck(
            id='DEP-CONNECTION-CAPACITY', status='not_checked',
            message=('Connection plates, welds, bolts, anchors, fasteners, reinforcement and '
                     'soil capacity require later engineering/design checks.'),
            affected_ids=[]),
    ]
    failed = any(check.status == 'failed' for check in checks)
    return DependencyGraph(
        status='failed' if failed else 'passed', roots=[SOIL_ROOT],
        relation_groups=_group_relations(relation_list),
        exemptions=sorted(exemptions, key=lambda item: item.element_id),
        checks=checks, required_element_count=len(required),
        connected_element_count=len(required) - len(uncovered),
        gravity_path_count=len(structural) - len(no_gravity_path))


def _reachable_hosts(element_id: str, adjacency: dict[str, list[str]]) -> set[str]:
    out: set[str] = set()
    stack = list(adjacency.get(element_id, ()))
    while stack:
        host_id = stack.pop()
        if host_id in out:
            continue
        out.add(host_id)
        stack.extend(adjacency.get(host_id, ()))
    return out


def _check_member_endpoints(
    records: list[_Record],
    relations: dict[str, list[ElementDependency]],
    by_id: dict[str, _Record],
) -> list[str]:
    """Verify two-ended lattice members against their declared host geometry."""

    checked = {'primary_beam', 'secondary_joist', 'heavy_joist', 'purlin'}
    failures: list[str] = []
    tolerance_m = 1.25  # section depth plus slab/connection zone; not a fabrication tolerance
    for record in records:
        if record.kind not in checked or not isinstance(record.instance.geometry, MemberGeometry):
            continue
        hosts = [by_id[relation.host_id] for relation in relations[record.id]
                 if relation.host_id in by_id]
        if not hosts:
            failures.append(record.id)
            continue
        for endpoint in (record.instance.geometry.path[0], record.instance.geometry.path[-1]):
            if min((_distance_to(host, endpoint) for host in hosts), default=math.inf) > tolerance_m:
                failures.append(record.id)
                break
    return sorted(set(failures))
