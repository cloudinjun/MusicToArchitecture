"""The structural centre-line skeleton: nodes first, solids afterwards.

Every structural member in this pipeline is already authored as a centre-line plus a
profile -- `MemberGeometry(path=[...], profile=...)`. What was missing is the layer
underneath: an explicit set of **nodes** that those centre-lines register to.

Without it, "is this member attached to anything?" could only be answered by measuring
distances after the fact, and every such answer needed a tolerance. A tolerance is a
guess about how far apart two things may be and still count as joined, and it gets the
question wrong in both directions: a beam whose end genuinely misses its column by
250 mm passes a 300 mm check, and a plate resting on the face of a girder fails a
tight one because the girder is stored as an axis and the plate touches its surface,
half a section away.

Registering to nodes replaces the measurement with an identity. Two members are
connected when they share a node id -- not when they happen to be close. The only
tolerance left is `SNAP_M`, and it does not decide whether a joint exists; it decides
whether two coordinates computed by different expressions are the same point. At one
tenth of a millimetre it is a float-comparison epsilon, not a design allowance.

Joints in a frame are not all end-to-end. A girder lands on the side of a column
partway up its height, and both are correct: the column runs floor to floor and the
beam meets it at the beam elevation. So a node is allowed to sit in a segment's
interior, and `finalise` records those T-joints alongside the endpoint ones. This is
how an analysis model treats the same condition.

Solid geometry -- slab plates, treads, fascias, cladding -- is then modelled *around*
the skeleton rather than beside it: a solid names the axis it wraps, and its host
follows from that axis rather than from a nearest-centroid guess.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import math

from .geometry import Vector3


# Two coordinates closer than this are the same point. This is a float-comparison
# epsilon -- endpoints that should coincide are computed from the same datum values and
# differ only in the last bits -- and deliberately not a tolerance for whether a joint
# exists. Widening it would start inventing connections that the geometry does not have.
SNAP_M = 1.0e-4

# How close a node must be to a segment's centre-line to count as lying on it. Same
# reasoning: a beam end that meets a column mid-height shares the column's x and y
# exactly, so the distance is zero to floating point.
ON_AXIS_M = 1.0e-3

# How far apart two centre-lines may be and still be joined by a *declared* bearing.
# Unlike the two epsilons above this one is a real dimension: it is the offset between
# the axis of a member and the axis of the member it sits on, which is half of each
# section's depth. A metre covers the deepest girder-and-joist pair the registry holds
# and still catches a member declaring a support it lands nowhere near.
BEARING_M = 1.0


@dataclass(frozen=True)
class AxisNode:
    """A registered point in the skeleton. Members meet by sharing one of these."""

    id: str
    point: Vector3


@dataclass
class AxisSegment:
    """One member's centre-line, stated as two node ids."""

    id: str
    owner_id: str
    start: str
    end: str
    role: str
    # Nodes lying on the segment, endpoints included. Filled by `finalise`.
    nodes: set[str] = field(default_factory=set)

    def length(self, skeleton: 'AxisSkeleton') -> float:
        a, b = skeleton.point(self.start), skeleton.point(self.end)
        return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


def _closest_between(a0: Vector3, a1: Vector3, b0: Vector3, b1: Vector3
                     ) -> tuple[Vector3, float]:
    """The point on segment b closest to segment a, and the gap between them."""
    ux, uy, uz = a1.x - a0.x, a1.y - a0.y, a1.z - a0.z
    vx, vy, vz = b1.x - b0.x, b1.y - b0.y, b1.z - b0.z
    wx, wy, wz = a0.x - b0.x, a0.y - b0.y, a0.z - b0.z
    a = ux * ux + uy * uy + uz * uz
    b = ux * vx + uy * vy + uz * vz
    c = vx * vx + vy * vy + vz * vz
    d = ux * wx + uy * wy + uz * wz
    e = vx * wx + vy * wy + vz * wz
    denom = a * c - b * b
    s_par = 0.0 if denom <= 1e-12 else max(0.0, min(1.0, (b * e - c * d) / denom))
    t_par = 0.0 if c <= 1e-12 else max(0.0, min(1.0, (b * s_par + e) / c))
    pa = Vector3(x=a0.x + ux * s_par, y=a0.y + uy * s_par, z=a0.z + uz * s_par)
    pb = Vector3(x=b0.x + vx * t_par, y=b0.y + vy * t_par, z=b0.z + vz * t_par)
    return pb, math.dist((pa.x, pa.y, pa.z), (pb.x, pb.y, pb.z))


def _point_segment_distance(p: Vector3, a: Vector3, b: Vector3) -> float:
    vx, vy, vz = b.x - a.x, b.y - a.y, b.z - a.z
    length2 = vx * vx + vy * vy + vz * vz
    if length2 <= 1e-12:
        return math.dist((p.x, p.y, p.z), (a.x, a.y, a.z))
    t = (((p.x - a.x) * vx + (p.y - a.y) * vy + (p.z - a.z) * vz) / length2)
    t = max(0.0, min(1.0, t))
    return math.dist((p.x, p.y, p.z),
                     (a.x + vx * t, a.y + vy * t, a.z + vz * t))


class AxisSkeleton:
    """Nodes and centre-lines, built before any solid is emitted."""

    def __init__(self) -> None:
        self._nodes: dict[str, AxisNode] = {}
        # Coarse spatial bucket so node lookup does not scan every node.
        self._buckets: dict[tuple[int, int, int], list[str]] = defaultdict(list)
        self.segments: dict[str, AxisSegment] = {}
        # Solids that wrap a centre-line rather than standing free.
        self.wrapped: dict[str, str] = {}
        # Declared bearing joints, resolved in `finalise`.
        self._pending: list[tuple[str, str]] = []
        # Bearing joints whose gap exceeded `BEARING_M`, kept for reporting rather
        # than silently joined.
        self.strained: list[tuple[str, str, float]] = []

    # -- nodes ---------------------------------------------------------------
    def _bucket(self, p: Vector3) -> tuple[int, int, int]:
        return (int(p.x * 100), int(p.y * 100), int(p.z * 100))

    def node(self, point: Vector3) -> str:
        """The id of the node at `point`, registering one if it is new."""
        bx, by, bz = self._bucket(point)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for node_id in self._buckets.get((bx + dx, by + dy, bz + dz), ()):
                        q = self._nodes[node_id].point
                        if (abs(q.x - point.x) < SNAP_M and abs(q.y - point.y) < SNAP_M
                                and abs(q.z - point.z) < SNAP_M):
                            return node_id
        node_id = f'AXN-{len(self._nodes):05d}'
        self._nodes[node_id] = AxisNode(id=node_id, point=point)
        self._buckets[(bx, by, bz)].append(node_id)
        return node_id

    def point(self, node_id: str) -> Vector3:
        return self._nodes[node_id].point

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    # -- segments ------------------------------------------------------------
    def segment(self, owner_id: str, path: list[Vector3], role: str) -> list[str]:
        """Register a member's centre-line. Returns the segment ids created."""
        created = []
        for index, (a, b) in enumerate(zip(path, path[1:])):
            start, end = self.node(a), self.node(b)
            if start == end:
                continue
            segment_id = f'{owner_id}#{index}'
            self.segments[segment_id] = AxisSegment(
                id=segment_id, owner_id=owner_id, start=start, end=end, role=role)
            created.append(segment_id)
        return created

    def attach(self, owner_id: str, host_id: str) -> None:
        """Declare that `owner` lands on `host`; the joint is resolved in `finalise`.

        Not every real joint is an axis crossing. A joist bears on the top flange of
        the girder carrying it, so the two centre-lines run parallel half a section
        apart and never meet -- correct framing, and invisible to a rule that only
        joins members sharing a point. Left at that, the joists in a floor register
        only to each other: consecutive bays share an end node, the field daisy-chains
        across the plate, and nothing in the chain touches a girder. Only the edge
        joists with no neighbour to chain to look wrong, which is the worst kind of
        defect report -- a real fault showing up at a twentieth of its true size.

        So a bearing joint is placed explicitly, on the host's axis at the point
        closest to the member it carries, and added to both.
        """
        self._pending.append((owner_id, host_id))

    def wrap(self, solid_id: str, owner_id: str) -> None:
        """Record that a solid is modelled around an existing centre-line."""
        self.wrapped[solid_id] = owner_id

    # -- resolution ----------------------------------------------------------
    def finalise(self) -> None:
        """Attach every node that lies on a segment, T-joints included.

        A girder meeting a column partway up its storey height shares no endpoint with
        it, yet the two are joined. Endpoint-only matching would call that column
        unconnected and send someone off to fix geometry that is already right.
        """
        for segment in self.segments.values():
            segment.nodes = {segment.start, segment.end}
        # Only nodes that are some segment's endpoint can be a T-joint partner; a point
        # no member ends at is not a joint, however close it passes.
        endpoints = {node_id for segment in self.segments.values()
                     for node_id in (segment.start, segment.end)}
        by_bucket: dict[tuple[int, int, int], list[str]] = defaultdict(list)
        for node_id in endpoints:
            by_bucket[self._bucket(self._nodes[node_id].point)].append(node_id)
        for segment in self.segments.values():
            a, b = self.point(segment.start), self.point(segment.end)
            lo = self._bucket(Vector3(x=min(a.x, b.x), y=min(a.y, b.y), z=min(a.z, b.z)))
            hi = self._bucket(Vector3(x=max(a.x, b.x), y=max(a.y, b.y), z=max(a.z, b.z)))
            for bx in range(lo[0] - 1, hi[0] + 2):
                for by in range(lo[1] - 1, hi[1] + 2):
                    for bz in range(lo[2] - 1, hi[2] + 2):
                        for node_id in by_bucket.get((bx, by, bz), ()):
                            if node_id in segment.nodes:
                                continue
                            if _point_segment_distance(
                                    self._nodes[node_id].point, a, b) <= ON_AXIS_M:
                                segment.nodes.add(node_id)
        # Declared bearing joints, placed on the host axis.
        by_owner: dict[str, list[AxisSegment]] = defaultdict(list)
        for segment in self.segments.values():
            by_owner[segment.owner_id].append(segment)
        for owner_id, host_id in self._pending:
            own, host = by_owner.get(owner_id), by_owner.get(host_id)
            if not own or not host:
                continue
            best: tuple[float, AxisSegment, AxisSegment, Vector3] | None = None
            for a_seg in own:
                pa0, pa1 = self.point(a_seg.start), self.point(a_seg.end)
                for h_seg in host:
                    ph0, ph1 = self.point(h_seg.start), self.point(h_seg.end)
                    q, gap = _closest_between(pa0, pa1, ph0, ph1)
                    if best is None or gap < best[0]:
                        best = (gap, a_seg, h_seg, q)
            gap, a_seg, h_seg, q = best
            if gap > BEARING_M:
                self.strained.append((owner_id, host_id, gap))
                continue
            node_id = self.node(q)
            a_seg.nodes.add(node_id)
            h_seg.nodes.add(node_id)

    # -- queries -------------------------------------------------------------
    def owners_at(self, node_id: str) -> set[str]:
        return {segment.owner_id for segment in self.segments.values()
                if node_id in segment.nodes}

    def nearest_owner(self, point: Vector3, prefix: str) -> str | None:
        """The member whose centre-line passes closest to `point`, among `prefix`.

        Naming a host by picking the first id that matches a prefix reads as a rule and
        is not one: `element_ids` is a set, so "the first fascia on this level" is
        whichever the hash order happens to yield, and on one model that put a strut's
        head thirty-four metres from the member it claimed to bear on. Asking the
        skeleton which line actually runs through the point is the question that was
        meant.
        """
        best: tuple[float, str] | None = None
        for segment in self.segments.values():
            if not segment.owner_id.startswith(prefix):
                continue
            gap = _point_segment_distance(
                point, self.point(segment.start), self.point(segment.end))
            if best is None or gap < best[0]:
                best = (gap, segment.owner_id)
        return best[1] if best else None

    def connections(self) -> dict[str, set[str]]:
        """owner id -> the owners it shares at least one node with."""
        at_node: dict[str, set[str]] = defaultdict(set)
        for segment in self.segments.values():
            for node_id in segment.nodes:
                at_node[node_id].add(segment.owner_id)
        linked: dict[str, set[str]] = defaultdict(set)
        for owners in at_node.values():
            for owner in owners:
                linked[owner] |= owners - {owner}
        return linked

    def isolated(self) -> list[str]:
        """Owners whose centre-line shares no node with any other member.

        This is the question the tolerance-based probe was trying to answer, now
        answered by identity: a member here is not merely far from its neighbours, it
        registers to no node that any other member registers to.
        """
        linked = self.connections()
        owners = {segment.owner_id for segment in self.segments.values()}
        return sorted(owner for owner in owners if not linked.get(owner))
