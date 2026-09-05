"""Small exact geometry checks used by the spatial common-sense report.

The model already has a dependency graph and a broad-phase spatial index.  This module
answers the narrower questions that need the emitted primitives themselves: a rotated
stair tread cannot pass through a solid slab or lift shaft, two distinct stair cores
cannot occupy the same positive 3-D volume, and a malformed plan ring cannot be
silently treated as an empty intersection.

``BoxGeometry`` and ``ExtrusionGeometry`` are measured with Shapely polygons.  An
extrusion's holes remain holes in every intersection.  Members do not have a swept
solid here; where an overhead member may affect a stair head-clearance review, the
center-line buffer is returned as a warning that needs review rather than a pass.

The 2.0 m head-clearance value is a project design-review convention.  It does not
state code compliance.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Iterable, Sequence

from shapely.geometry import LineString, Polygon
from shapely.validation import explain_validity

from .geometry import BoxGeometry, ExtrusionGeometry, MemberGeometry


AREA_EPS_M2 = 1.0e-7
Z_EPS_M = 1.0e-6
HEAD_CLEARANCE_REVIEW_M = 2.0
PLAN_RING_TOLERANCE_M = 1.0e-9
MEMBER_APPROX_RADIUS_M = 0.15

_FLIGHT_RE = re.compile(r'^CIR-TRD-([A-Z])(\d{2})-S\d{3}$')
_FLIGHT_PAIR_BY_LETTER = {
    'A': 'primary', 'B': 'primary',
    'C': 'second', 'D': 'second',
    'G': 'extra_1', 'H': 'extra_1',
    'J': 'extra_2', 'K': 'extra_2',
}
_OVERHEAD_MEMBER_KINDS = {
    'primary_beam', 'secondary_joist', 'heavy_joist', 'purlin',
    'truss_chord', 'truss_web', 'brace', 'outrigger_strut',
    'frame_expression', 'external_strut',
}


@dataclass(frozen=True)
class GeometryFinding:
    """A Finding-shaped record that does not import ``spatial_rules``."""

    rule_id: str
    severity: str
    elements: tuple[str, ...]
    measure: float
    unit: str
    detail: str


@dataclass(frozen=True)
class _Element:
    id: str
    kind: str
    level_id: str
    geometry: Any


@dataclass
class _ReviewContext:
    elements: list[_Element]
    by_kind: dict[str, list[_Element]]
    polygons: dict[str, Polygon | None]
    z_intervals: dict[str, tuple[float, float] | None]
    member_lines: dict[str, LineString | None]
    plan_rings: dict[str, list[tuple[str, list[tuple[float, float]]]]]


def _elements(model: Any) -> list[_Element]:
    out: list[_Element] = []
    for group in model.element_groups:
        for instance in group.instances:
            out.append(_Element(
                id=instance.id,
                kind=group.kind,
                level_id=instance.level_id,
                geometry=getattr(instance, 'geometry', None),
            ))
    return out


def _context(model: Any) -> _ReviewContext:
    elements = _elements(model)
    by_kind: dict[str, list[_Element]] = {}
    polygons: dict[str, Polygon | None] = {}
    z_intervals: dict[str, tuple[float, float] | None] = {}
    member_lines: dict[str, LineString | None] = {}
    plan_rings: dict[str, list[tuple[str, list[tuple[float, float]]]]] = {}
    for element in elements:
        by_kind.setdefault(element.kind, []).append(element)
        polygons[element.id] = _polygon(element.geometry)
        z_intervals[element.id] = _z_interval(element.geometry)
        member_lines[element.id] = _member_line(element.geometry)
        try:
            plan_rings[element.id] = _plan_rings(element)
        except (TypeError, ValueError):
            plan_rings[element.id] = []
    return _ReviewContext(elements, by_kind, polygons, z_intervals, member_lines, plan_rings)


def _box_ring(geometry: BoxGeometry) -> list[tuple[float, float]]:
    cx, cy = geometry.center.x, geometry.center.y
    sx, sy = abs(geometry.size.x), abs(geometry.size.y)
    cos_a, sin_a = math.cos(geometry.rotation_z), math.sin(geometry.rotation_z)
    ring: list[tuple[float, float]] = []
    for local_x, local_y in (
        (-sx / 2.0, -sy / 2.0), (sx / 2.0, -sy / 2.0),
        (sx / 2.0, sy / 2.0), (-sx / 2.0, sy / 2.0),
    ):
        ring.append((
            cx + cos_a * local_x - sin_a * local_y,
            cy + sin_a * local_x + cos_a * local_y,
        ))
    return ring


def _extrusion_ring(geometry: ExtrusionGeometry) -> list[tuple[float, float]]:
    return [(point.x, point.y) for point in geometry.boundary]


def _extrusion_polygon(geometry: ExtrusionGeometry) -> Polygon:
    return Polygon(
        _extrusion_ring(geometry),
        [[(point.x, point.y) for point in hole] for hole in geometry.holes],
    )


def _polygon(geometry: Any) -> Polygon | None:
    """Return a Shapely plan polygon, preserving extrusion holes."""

    try:
        if isinstance(geometry, BoxGeometry):
            polygon = Polygon(_box_ring(geometry))
        elif isinstance(geometry, ExtrusionGeometry):
            polygon = _extrusion_polygon(geometry)
        else:
            return None
    except (TypeError, ValueError):
        return None
    if polygon.is_empty or polygon.area <= AREA_EPS_M2 or not polygon.is_valid:
        return None
    return polygon


def _z_interval(geometry: Any) -> tuple[float, float] | None:
    try:
        if isinstance(geometry, BoxGeometry):
            half = abs(geometry.size.z) / 2.0
            return geometry.center.z - half, geometry.center.z + half
        if isinstance(geometry, ExtrusionGeometry):
            return min(geometry.z_base, geometry.z_top), max(geometry.z_base, geometry.z_top)
        if isinstance(geometry, MemberGeometry):
            z_values = [point.z for point in geometry.path]
            return min(z_values), max(z_values)
    except (TypeError, ValueError):
        return None
    return None


def _member_line(geometry: Any) -> LineString | None:
    if not isinstance(geometry, MemberGeometry):
        return None
    try:
        line = LineString([(point.x, point.y) for point in geometry.path])
    except (TypeError, ValueError):
        return None
    return line if not line.is_empty and line.length > PLAN_RING_TOLERANCE_M else None


def _ring_edges(ring: Sequence[tuple[float, float]]) -> Iterable[tuple[int, tuple[float, float], tuple[float, float]]]:
    for index, start in enumerate(ring):
        yield index, start, ring[(index + 1) % len(ring)]


def _non_adjacent_crossing(
    ring: Sequence[tuple[float, float]],
) -> tuple[int, int, tuple[float, float]] | None:
    """Find a real crossing/touch between two non-adjacent ring edges."""

    if len(ring) < 3:
        return None
    edges = list(_ring_edges(ring))
    for first_offset, (first_index, first_start, first_end) in enumerate(edges):
        for second_index, second_start, second_end in edges[first_offset + 1:]:
            if second_index in {
                first_index,
                (first_index - 1) % len(ring),
                (first_index + 1) % len(ring),
            }:
                continue
            intersection = LineString([first_start, first_end]).intersection(
                LineString([second_start, second_end]))
            if intersection.is_empty:
                continue
            point = intersection.representative_point()
            return first_index, second_index, (point.x, point.y)
    return None


def _plan_rings(element: _Element) -> list[tuple[str, list[tuple[float, float]]]]:
    geometry = element.geometry
    if isinstance(geometry, BoxGeometry):
        try:
            return [('boundary', _box_ring(geometry))]
        except (AttributeError, TypeError, ValueError):
            return [('boundary', [])]
    if isinstance(geometry, ExtrusionGeometry):
        try:
            rings = [('boundary', _extrusion_ring(geometry))]
            rings.extend((f'hole-{index}', [(point.x, point.y) for point in hole])
                         for index, hole in enumerate(geometry.holes))
            return rings
        except (AttributeError, TypeError, ValueError):
            return [('boundary', [])]
    return []


def _unknown(rule_id: str, elements: Sequence[str], detail: str) -> GeometryFinding:
    return GeometryFinding(
        rule_id=rule_id, severity='warning', elements=tuple(elements),
        measure=0.0, unit='unevaluated', detail=f'Unevaluated: {detail}',
    )


def check_invalid_plan_rings(
    model: Any, *, context: _ReviewContext | None = None,
) -> list[GeometryFinding]:
    """Report invalid plan solids before their intersections become unknowable."""

    rule_id = 'SP-INVALID-PLAN-RING'
    findings: list[GeometryFinding] = []
    context = context or _context(model)
    for element in context.elements:
        if element.geometry is None:
            # A missing instance geometry is a review item wherever a physical element
            # was promised.  Members and quads have no closed plan ring and are not
            # part of this check.
            if element.kind not in {'stair_stringer', 'railing'}:
                findings.append(_unknown(rule_id, (element.id,), 'element has no geometry.'))
            continue
        rings = context.plan_rings.get(element.id, ())
        if not rings:
            continue

        # Boxes have no hole topology.  Polygon.is_valid is the complete fast path;
        # do not spend time walking the four edges of every valid instance.
        if isinstance(element.geometry, BoxGeometry):
            if context.polygons.get(element.id) is not None:
                continue
            polygon = Polygon(rings[0][1])
            reason = explain_validity(polygon)
            findings.append(GeometryFinding(
                rule_id=rule_id, severity='violation', elements=(element.id,),
                measure=0.0, unit='plan ring',
                detail=(f'{element.kind} {element.id} boundary is not '
                        f'triangulable/evaluable: {reason}.'),
            ))
            continue

        # For extrusions the compound polygon, including holes, is authoritative.
        # A valid compound polygon returns immediately.  Only an invalid extrusion
        # gets the more detailed edge walk that identifies a crossing ring.
        if isinstance(element.geometry, ExtrusionGeometry):
            try:
                polygon = _extrusion_polygon(element.geometry)
            except (TypeError, ValueError):
                polygon = None
            if (polygon is not None and not polygon.is_empty
                    and polygon.area > AREA_EPS_M2 and polygon.is_valid):
                continue

            crossing_detail: str | None = None
            for ring_name, ring in rings:
                crossing = _non_adjacent_crossing(ring)
                if crossing is None:
                    continue
                first_edge, second_edge, point = crossing
                crossing_detail = (
                    f'{element.kind} {element.id} {ring_name} has a '
                    f'non-adjacent edge intersection at '
                    f'({point[0]:.3f}, {point[1]:.3f}) '
                    f'(edges {first_edge} and {second_edge}).')
                break
            if crossing_detail is not None:
                findings.append(GeometryFinding(
                    rule_id=rule_id, severity='violation', elements=(element.id,),
                    measure=0.0, unit='plan ring', detail=crossing_detail,
                ))
                continue

            reason = explain_validity(polygon) if polygon is not None else 'invalid coordinates'
            findings.append(GeometryFinding(
                rule_id=rule_id, severity='violation', elements=(element.id,),
                measure=0.0, unit='plan ring',
                detail=(f'{element.kind} {element.id} compound plan solid is not '
                        f'triangulable/evaluable: {reason}.'),
            ))
    return findings


def _solid_overlap(first: Polygon, second: Polygon) -> float:
    # Bounds are only a broad-phase rejection.  The reported area below always comes
    # from the exact rotated polygon intersection, so an AABB cannot create a finding.
    first_x0, first_y0, first_x1, first_y1 = first.bounds
    second_x0, second_y0, second_x1, second_y1 = second.bounds
    if (min(first_x1, second_x1) - max(first_x0, second_x0) <= 0.0
            or min(first_y1, second_y1) - max(first_y0, second_y0) <= 0.0):
        return 0.0
    # Both polygons have already passed the validity gate in ``_context``.  Let a
    # Shapely failure surface instead of turning an unevaluated intersection into a
    # false zero-overlap pass.
    return max(0.0, first.intersection(second).area)


def _vertical_overlap(first: tuple[float, float], second: tuple[float, float]) -> float:
    return max(0.0, min(first[1], second[1]) - max(first[0], second[0]))


def _solid_rows(elements: Sequence[_Element], kinds: set[str]) -> list[_Element]:
    return [element for element in elements if element.kind in kinds]


def _invalid_geometry_warning(rule_id: str, element: _Element, role: str) -> GeometryFinding:
    return _unknown(rule_id, (element.id,), f'{role} {element.kind} {element.id} has no valid solid plan polygon.')


def check_stair_head_clearance(
    model: Any, *, context: _ReviewContext | None = None,
) -> list[GeometryFinding]:
    """Check each tread against the first solid slab/ceiling above its footprint."""

    rule_id = 'SP-STAIR-HEAD-CLEARANCE'
    context = context or _context(model)
    elements = context.elements
    treads = _solid_rows(elements, {'stair_tread'})
    overhead = _solid_rows(elements, {'floor_slab', 'ceiling'})
    findings: list[GeometryFinding] = []
    warned_treads: set[str] = set()
    warned_obstacles: set[str] = set()
    for tread in treads:
        tread_polygon = context.polygons.get(tread.id)
        tread_z = context.z_intervals.get(tread.id)
        if tread_polygon is None or tread_z is None:
            if tread.id not in warned_treads:
                findings.append(_invalid_geometry_warning(rule_id, tread, 'tread'))
                warned_treads.add(tread.id)
            continue
        candidates: list[tuple[float, float, _Element]] = []
        for obstacle in overhead:
            obstacle_polygon = context.polygons.get(obstacle.id)
            obstacle_z = context.z_intervals.get(obstacle.id)
            if obstacle_polygon is None or obstacle_z is None:
                if obstacle.id not in warned_obstacles:
                    findings.append(_invalid_geometry_warning(rule_id, obstacle, 'overhead obstacle'))
                    warned_obstacles.add(obstacle.id)
                continue
            if obstacle_z[1] <= tread_z[0] + Z_EPS_M:
                continue
            overlap_area = _solid_overlap(tread_polygon, obstacle_polygon)
            if overlap_area <= AREA_EPS_M2:
                continue
            candidates.append((obstacle_z[0] - tread_z[1], overlap_area, obstacle))
        if candidates:
            clearance, overlap_area, obstacle = min(candidates, key=lambda item: item[0])
            if clearance < HEAD_CLEARANCE_REVIEW_M - Z_EPS_M:
                findings.append(GeometryFinding(
                    rule_id=rule_id, severity='violation',
                    elements=(tread.id, obstacle.id), measure=clearance, unit='m',
                    detail=(f'{tread.id} has {clearance:.3f} m from its walking '
                            f'surface to the underside of {obstacle.id}; '
                            f'{overlap_area:.3f} m² plan overlap. The 2.0 m value '
                            'is a project design-review convention, not a code claim.'),
                ))

    # Structural members are center-lines in the portable contract.  A buffered line
    # is useful to surface a possible overhead member, but it stays a warning because
    # section depth/roll is not authoritative in this small review gate.
    warned_members: set[str] = set()
    for member in _solid_rows(elements, _OVERHEAD_MEMBER_KINDS):
        line = context.member_lines.get(member.id)
        member_z = context.z_intervals.get(member.id)
        if line is None or member_z is None:
            if member.id not in warned_members:
                findings.append(_invalid_geometry_warning(rule_id, member, 'overhead member'))
                warned_members.add(member.id)
            continue
        approx_plan = line.buffer(MEMBER_APPROX_RADIUS_M, cap_style=2, join_style=2)
        for tread in treads:
            tread_polygon = context.polygons.get(tread.id)
            tread_z = context.z_intervals.get(tread.id)
            if tread_polygon is None or tread_z is None or member.id in warned_members:
                continue
            if member_z[1] <= tread_z[0] + Z_EPS_M:
                continue
            if _solid_overlap(tread_polygon, approx_plan) <= AREA_EPS_M2:
                continue
            clearance = member_z[0] - tread_z[1]
            findings.append(_unknown(
                rule_id, (tread.id, member.id),
                (f'overhead member center-line is within the stair review volume '
                 f'with approximate clearance {clearance:.3f} m; section depth '
                 'and roll require review.'),
            ))
            warned_members.add(member.id)
            break
    return findings


def _check_tread_against_solids(
    model: Any,
    target_kinds: set[str],
    rule_id: str,
    target_label: str,
    *,
    context: _ReviewContext | None = None,
) -> list[GeometryFinding]:
    context = context or _context(model)
    elements = context.elements
    treads = _solid_rows(elements, {'stair_tread'})
    targets = _solid_rows(elements, target_kinds)
    findings: list[GeometryFinding] = []
    warned: set[str] = set()
    for tread in treads:
        tread_polygon = context.polygons.get(tread.id)
        tread_z = context.z_intervals.get(tread.id)
        if tread_polygon is None or tread_z is None:
            if tread.id not in warned:
                findings.append(_invalid_geometry_warning(rule_id, tread, 'tread'))
                warned.add(tread.id)
            continue
        for target in targets:
            target_polygon = context.polygons.get(target.id)
            target_z = context.z_intervals.get(target.id)
            if target_polygon is None or target_z is None:
                if target.id not in warned:
                    findings.append(_invalid_geometry_warning(rule_id, target, target_label))
                    warned.add(target.id)
                continue
            depth = _vertical_overlap(tread_z, target_z)
            if depth <= Z_EPS_M:
                continue
            area = _solid_overlap(tread_polygon, target_polygon)
            if area <= AREA_EPS_M2:
                continue
            volume = area * depth
            findings.append(GeometryFinding(
                rule_id=rule_id, severity='violation',
                elements=(tread.id, target.id), measure=volume, unit='m³',
                detail=(f'{tread.id} and {target.id} have {area:.3f} m² exact '
                        f'plan overlap and {depth:.3f} m positive z overlap '
                        f'({volume:.4f} m³ intersection volume).'),
            ))
    return findings


def check_tread_floor_slab_overlap(
    model: Any, *, context: _ReviewContext | None = None,
) -> list[GeometryFinding]:
    return _check_tread_against_solids(
        model, {'floor_slab'}, 'SP-STAIR-TREAD-SLAB-OVERLAP', 'floor slab',
        context=context)


def check_tread_elevator_shaft_overlap(
    model: Any, *, context: _ReviewContext | None = None,
) -> list[GeometryFinding]:
    return _check_tread_against_solids(
        model, {'elevator_shaft'}, 'SP-STAIR-TREAD-LIFT-OVERLAP', 'lift shaft',
        context=context)


def _flight_pair(element: _Element) -> str | None:
    match = _FLIGHT_RE.match(element.id)
    return _FLIGHT_PAIR_BY_LETTER.get(match.group(1)) if match else None


def check_intercore_stair_overlap(
    model: Any, *, context: _ReviewContext | None = None,
) -> list[GeometryFinding]:
    """Compare exact positive 3-D tread volumes between distinct stair cores."""

    rule_id = 'SP-STAIR-INTERCORE-OVERLAP'
    context = context or _context(model)
    elements = context.elements
    grouped: dict[str, list[_Element]] = {}
    findings: list[GeometryFinding] = []
    warned: set[str] = set()
    for tread in _solid_rows(elements, {'stair_tread'}):
        pair = _flight_pair(tread)
        if pair is None:
            continue  # F01 is the external approach, not an egress-core pair.
        if (context.polygons.get(tread.id) is None
                or context.z_intervals.get(tread.id) is None):
            if tread.id not in warned:
                findings.append(_invalid_geometry_warning(rule_id, tread, 'core tread'))
                warned.add(tread.id)
            continue
        grouped.setdefault(pair, []).append(tread)
    pair_names = sorted(grouped)
    for first_index, first_name in enumerate(pair_names):
        for second_name in pair_names[first_index + 1:]:
            for first in grouped[first_name]:
                first_polygon = context.polygons.get(first.id)
                first_z = context.z_intervals.get(first.id)
                if first_polygon is None or first_z is None:
                    continue
                for second in grouped[second_name]:
                    second_polygon = context.polygons.get(second.id)
                    second_z = context.z_intervals.get(second.id)
                    if second_polygon is None or second_z is None:
                        continue
                    depth = _vertical_overlap(first_z, second_z)
                    if depth <= Z_EPS_M:
                        continue
                    area = _solid_overlap(first_polygon, second_polygon)
                    if area <= AREA_EPS_M2:
                        continue
                    volume = area * depth
                    findings.append(GeometryFinding(
                        rule_id=rule_id, severity='violation',
                        elements=(first.id, second.id), measure=volume, unit='m³',
                        detail=(f'{first_name} and {second_name} stair treads '
                                f'overlap by {area:.3f} m² in plan and {depth:.3f} m '
                                f'in z ({volume:.4f} m³ positive volume).'),
                    ))
    return findings


def review_geometry(model: Any) -> list[GeometryFinding]:
    """Return all geometry-review findings without mutating ``model``."""

    context = _context(model)
    findings: list[GeometryFinding] = []
    findings.extend(check_invalid_plan_rings(model, context=context))
    findings.extend(check_stair_head_clearance(model, context=context))
    findings.extend(check_tread_floor_slab_overlap(model, context=context))
    findings.extend(check_tread_elevator_shaft_overlap(model, context=context))
    findings.extend(check_intercore_stair_overlap(model, context=context))
    return findings


# Explicit alias for callers that prefer a verb over the noun used in the report.
geometry_review = review_geometry
