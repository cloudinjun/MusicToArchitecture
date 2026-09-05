"""Read-only geometric measurements for a schema 3 building model.

The compiler's dependency and spatial reports answer different questions from this
module.  This script measures a small set of reviewable invariants directly from the
serialised primitives:

* stair tread clearance to the first floor slab or ceiling above it;
* true 3-D intersections between stair treads and floor slabs or elevator shafts;
* positive plan-area overlaps between program zones on one level; and
* plan contact and top-surface alignment between each floor landing and its slab.

It also reports invalid closed plan rings before a failed triangulation can be
mistaken for a clean no-overlap result, and compares treads across distinct stair
core pairs.

The calculations use polygon intersections rather than axis-aligned bounding boxes.
Box rotation, extrusion holes, and the constant-z nature of the emitted primitives
are retained.  The module intentionally has no application imports, so it can be
used against a frozen ``building_model_v3.json`` without changing the compiler.

The 2.0 m head-clearance value is a project design-review convention.  It is not a
code-compliance determination.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from shapely.errors import GEOSException
from shapely.geometry import Polygon
from shapely.ops import unary_union


Point2 = tuple[float, float]
Point3 = tuple[float, float, float]

AREA_EPS_M2 = 1.0e-7
PLAN_EPS_M = 1.0e-9
Z_EPS_M = 1.0e-6
VERTICAL_REVIEW_TOLERANCE_M = 0.005
# How far a landing footprint is grown to find the slab it abuts. A hand's width:
# wide enough to cross the shared edge, too narrow to reach a slab a step away.
EDGE_CONTACT_REACH_M = 0.05
HEAD_CLEARANCE_REVIEW_M = 2.0
SAMPLE_LIMIT = 12

# These tags mirror the circulation contract in ``dependencies.py``: A/B is the
# primary core, C/D the second core, and G/H then J/K are optional extra cores.  A
# flight letter without a partner (F01 is the grade approach) is kept out of the
# inter-core test because it is not an egress-core pair.
_FLIGHT_PAIR_BY_LETTER = {
    "A": "primary",
    "B": "primary",
    "C": "second",
    "D": "second",
    "G": "extra_1",
    "H": "extra_1",
    "J": "extra_2",
    "K": "extra_2",
}


@dataclass(frozen=True)
class Element:
    """One expanded element-group instance from the JSON payload."""

    id: str
    kind: str
    level_id: str
    geometry: Mapping[str, Any]
    group_id: str


def _as_float(value: Any) -> float:
    return float(value)


def _point2(value: Any) -> Point2:
    if not isinstance(value, Mapping):
        raise TypeError("plan point must be an object with x and y")
    return (_as_float(value["x"]), _as_float(value["y"]))


def _point3(value: Any) -> Point3:
    if not isinstance(value, Mapping):
        raise TypeError("spatial point must be an object with x, y, and z")
    return (
        _as_float(value["x"]),
        _as_float(value["y"]),
        _as_float(value["z"]),
    )


def _iter_elements(model: Mapping[str, Any]) -> list[Element]:
    elements: list[Element] = []
    for group in model["element_groups"]:
        group_id = str(group["group_id"])
        kind = str(group["kind"])
        for instance in group["instances"]:
            geometry = instance["geometry"]
            if not isinstance(geometry, Mapping):
                raise TypeError(f"{instance['id']}: geometry must be an object")
            elements.append(
                Element(
                    id=str(instance["id"]),
                    kind=kind,
                    level_id=str(instance["level_id"]),
                    geometry=geometry,
                    group_id=group_id,
                )
            )
    return elements


def _ring_area(ring: Sequence[Point2]) -> float:
    return 0.5 * sum(
        ring[index][0] * ring[(index + 1) % len(ring)][1]
        - ring[(index + 1) % len(ring)][0] * ring[index][1]
        for index in range(len(ring))
    ) if ring else 0.0


def _clean_ring(ring: Iterable[Point2]) -> list[Point2]:
    cleaned: list[Point2] = []
    for point in ring:
        point = (float(point[0]), float(point[1]))
        if not cleaned or math.dist(point, cleaned[-1]) > 1.0e-10:
            cleaned.append(point)
    if len(cleaned) > 1 and math.dist(cleaned[0], cleaned[-1]) <= 1.0e-10:
        cleaned.pop()
    return cleaned


def _ccw(ring: Iterable[Point2]) -> list[Point2]:
    cleaned = _clean_ring(ring)
    if _ring_area(cleaned) < 0.0:
        cleaned.reverse()
    return cleaned


def _cross(a: Point2, b: Point2, c: Point2) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _point_on_segment(point: Point2, start: Point2, end: Point2, tolerance: float = 1.0e-9) -> bool:
    if abs(_cross(start, end, point)) > tolerance:
        return False
    return (
        min(start[0], end[0]) - tolerance <= point[0] <= max(start[0], end[0]) + tolerance
        and min(start[1], end[1]) - tolerance <= point[1] <= max(start[1], end[1]) + tolerance
    )


def _point_in_triangle(point: Point2, triangle: Sequence[Point2]) -> bool:
    signs = [_cross(triangle[index], triangle[(index + 1) % 3], point) for index in range(3)]
    return min(signs) >= -1.0e-9


def _triangulate(ring: Sequence[Point2]) -> list[tuple[Point2, Point2, Point2]]:
    """Triangulate a simple ring using ear clipping.

    The emitted plates are normally convex rectangles/quadrilaterals.  Ear clipping
    keeps the helper honest for a stepped or concave plate as well, which is useful
    for the hole fixture and avoids introducing a third-party geometry dependency.
    """

    vertices = _ccw(ring)
    if len(vertices) < 3 or abs(_ring_area(vertices)) <= AREA_EPS_M2:
        return []
    if len(vertices) == 3:
        return [(vertices[0], vertices[1], vertices[2])]

    remaining = list(range(len(vertices)))
    triangles: list[tuple[Point2, Point2, Point2]] = []
    guard = 0
    while len(remaining) > 3 and guard < len(vertices) * len(vertices) * 2:
        guard += 1
        ear_found = False
        for offset, current_index in enumerate(remaining):
            previous_index = remaining[(offset - 1) % len(remaining)]
            next_index = remaining[(offset + 1) % len(remaining)]
            previous = vertices[previous_index]
            current = vertices[current_index]
            following = vertices[next_index]
            if _cross(previous, current, following) <= 1.0e-10:
                continue
            triangle = (previous, current, following)
            if any(
                other_index not in (previous_index, current_index, next_index)
                and _point_in_triangle(vertices[other_index], triangle)
                for other_index in remaining
            ):
                continue
            triangles.append(triangle)
            remaining.pop(offset)
            ear_found = True
            break
        if not ear_found:
            # A malformed ring should be reported as unevaluated by its caller.  A
            # fan here would silently make a concave plate look solid.
            return []
    if len(remaining) == 3:
        triangle = tuple(vertices[index] for index in remaining)
        triangles.append(triangle)  # type: ignore[arg-type]
    return triangles


def _line_intersection(start: Point2, end: Point2, clip_start: Point2, clip_end: Point2) -> Point2:
    """Intersection of two lines, with a midpoint fallback for parallel edges."""

    x1, y1 = start
    x2, y2 = end
    x3, y3 = clip_start
    x4, y4 = clip_end
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) <= 1.0e-12:
        return end
    determinant_a = x1 * y2 - y1 * x2
    determinant_b = x3 * y4 - y3 * x4
    x = (determinant_a * (x3 - x4) - (x1 - x2) * determinant_b) / denominator
    y = (determinant_a * (y3 - y4) - (y1 - y2) * determinant_b) / denominator
    return (x, y)


def _clip_convex(subject: Sequence[Point2], clip: Sequence[Point2]) -> list[Point2]:
    """Sutherland-Hodgman clipping where ``clip`` is counter-clockwise convex."""

    output = list(subject)
    if not output:
        return []
    clip = _ccw(clip)
    for index, clip_start in enumerate(clip):
        clip_end = clip[(index + 1) % len(clip)]
        input_points = output
        output = []
        if not input_points:
            break
        previous = input_points[-1]
        previous_inside = _cross(clip_start, clip_end, previous) >= -1.0e-9
        for current in input_points:
            current_inside = _cross(clip_start, clip_end, current) >= -1.0e-9
            if current_inside:
                if not previous_inside:
                    output.append(_line_intersection(previous, current, clip_start, clip_end))
                output.append(current)
            elif previous_inside:
                output.append(_line_intersection(previous, current, clip_start, clip_end))
            previous = current
            previous_inside = current_inside
    return _clean_ring(output)


def _convex_intersection_area(first: Sequence[Point2], second: Sequence[Point2]) -> float:
    clipped = _clip_convex(first, second)
    return abs(_ring_area(clipped)) if len(clipped) >= 3 else 0.0


def _intersection_area(first: Sequence[Point2], second: Sequence[Point2]) -> float | None:
    """Return exact area for two simple rings, or ``None`` for malformed rings."""

    first_triangles = _triangulate(first)
    second_triangles = _triangulate(second)
    if not first_triangles or not second_triangles:
        return None
    area = 0.0
    for first_triangle in first_triangles:
        for second_triangle in second_triangles:
            area += _convex_intersection_area(first_triangle, second_triangle)
    return max(0.0, area)


def _box_polygon(geometry: Mapping[str, Any]) -> list[Point2] | None:
    center = geometry.get("center")
    size = geometry.get("size")
    if not isinstance(center, Mapping) or not isinstance(size, Mapping):
        return None
    try:
        cx = _as_float(center["x"])
        cy = _as_float(center["y"])
        sx = abs(_as_float(size["x"]))
        sy = abs(_as_float(size["y"]))
        angle = _as_float(geometry["rotation_z"])
    except (KeyError, TypeError, ValueError):
        return None
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    corners: list[Point2] = []
    for local_x, local_y in ((-sx / 2.0, -sy / 2.0), (sx / 2.0, -sy / 2.0), (sx / 2.0, sy / 2.0), (-sx / 2.0, sy / 2.0)):
        corners.append((cx + cos_a * local_x - sin_a * local_y, cy + sin_a * local_x + cos_a * local_y))
    return corners


def _geometry_polygon(geometry: Mapping[str, Any]) -> list[Point2] | None:
    geometry_type = geometry.get("type")
    if geometry_type == "box":
        return _box_polygon(geometry)
    if geometry_type == "extrusion":
        raw = geometry.get("boundary")
        if isinstance(raw, Sequence):
            try:
                return _clean_ring(_point2(point) for point in raw)
            except (KeyError, TypeError, ValueError):
                return None
    if geometry_type == "quad":
        raw = geometry.get("corners")
        if isinstance(raw, Sequence):
            try:
                return _clean_ring(_point2(point) for point in raw)
            except (KeyError, TypeError, ValueError):
                return None
    return None


def _geometry_holes(geometry: Mapping[str, Any]) -> list[list[Point2]]:
    if geometry.get("type") != "extrusion":
        return []
    raw_holes = geometry.get("holes") or []
    holes: list[list[Point2]] = []
    for raw_hole in raw_holes:
        if isinstance(raw_hole, Sequence):
            try:
                ring = _clean_ring(_point2(point) for point in raw_hole)
            except (KeyError, TypeError, ValueError):
                continue
            if len(ring) >= 3:
                holes.append(ring)
    return holes


def _raw_geometry_holes(geometry: Mapping[str, Any]) -> list[list[Point2]] | None:
    """Return every extrusion hole, preserving malformed input as ``None``."""

    if geometry.get("type") != "extrusion":
        return []
    raw_holes = geometry.get("holes", [])
    if raw_holes is None:
        return []
    if not isinstance(raw_holes, Sequence) or isinstance(raw_holes, (str, bytes)):
        return None
    holes: list[list[Point2]] = []
    for raw_hole in raw_holes:
        if not isinstance(raw_hole, Sequence) or isinstance(raw_hole, (str, bytes)):
            return None
        try:
            ring = _clean_ring(_point2(point) for point in raw_hole)
        except (KeyError, TypeError, ValueError):
            return None
        if len(ring) < 3:
            return None
        holes.append(ring)
    return holes


@lru_cache(maxsize=8192)
def _valid_plan_polygon(
    boundary: tuple[Point2, ...],
    holes: tuple[tuple[Point2, ...], ...],
) -> bool:
    """Validate a complete boundary-plus-holes topology without repairing it."""

    if len(boundary) < 3:
        return False
    try:
        polygon = Polygon(boundary, holes)
    except (GEOSException, TypeError, ValueError):
        return False
    return bool(polygon.is_valid)


def _geometry_has_valid_plan_topology(geometry: Mapping[str, Any]) -> bool:
    boundary = _geometry_polygon(geometry)
    holes = _raw_geometry_holes(geometry)
    if boundary is None or holes is None:
        return False
    return _valid_plan_polygon(
        tuple(boundary),
        tuple(tuple(hole) for hole in holes),
    )


def _solid_plan_polygon(geometry: Mapping[str, Any]) -> Polygon | None:
    """Build a valid, unrepaired plan solid for union-based measurements."""

    boundary = _geometry_polygon(geometry)
    holes = _raw_geometry_holes(geometry)
    if (
        boundary is None
        or holes is None
        or not _geometry_has_valid_plan_topology(geometry)
    ):
        return None
    try:
        polygon = Polygon(boundary, holes)
    except (GEOSException, TypeError, ValueError):
        return None
    return polygon if polygon.is_valid and not polygon.is_empty else None


def _plan_geometry_may_overlap(subject: Polygon, geometry: Mapping[str, Any]) -> bool:
    """Return whether an invalid solid could change ``subject``'s plan result."""

    boundary = _geometry_polygon(geometry)
    if boundary is None or len(boundary) < 3:
        return True
    try:
        coordinates = [coordinate for point in boundary for coordinate in point]
        if not all(math.isfinite(value) for value in coordinates):
            return True
        min_x = min(point[0] for point in boundary)
        max_x = max(point[0] for point in boundary)
        min_y = min(point[1] for point in boundary)
        max_y = max(point[1] for point in boundary)
        subject_min_x, subject_min_y, subject_max_x, subject_max_y = subject.bounds
        if (
            max_x <= subject_min_x + PLAN_EPS_M
            or min_x >= subject_max_x - PLAN_EPS_M
            or max_y <= subject_min_y + PLAN_EPS_M
            or min_y >= subject_max_y - PLAN_EPS_M
        ):
            return False
        boundary_polygon = Polygon(boundary)
        if boundary_polygon.is_empty:
            return False
        if not boundary_polygon.is_valid:
            return True
        return subject.intersection(boundary_polygon).area > AREA_EPS_M2
    except (GEOSException, TypeError, ValueError):
        return True


def _geometry_z_interval(geometry: Mapping[str, Any]) -> tuple[float, float] | None:
    geometry_type = geometry.get("type")
    if geometry_type == "box":
        center = geometry.get("center")
        size = geometry.get("size")
        if isinstance(center, Mapping) and isinstance(size, Mapping):
            try:
                half_z = abs(_as_float(size["z"])) / 2.0
                z = _as_float(center["z"])
            except (KeyError, TypeError, ValueError):
                return None
            return (z - half_z, z + half_z)
    if geometry_type == "extrusion":
        if "z_base" in geometry and "z_top" in geometry:
            try:
                z_base = _as_float(geometry["z_base"])
                z_top = _as_float(geometry["z_top"])
            except (TypeError, ValueError):
                return None
            return (min(z_base, z_top), max(z_base, z_top))
    if geometry_type == "member":
        raw_path = geometry.get("path") or []
        if raw_path:
            z_values = [_point3(point)[2] for point in raw_path]
            return (min(z_values), max(z_values))
    if geometry_type == "quad":
        raw_corners = geometry.get("corners") or []
        if raw_corners:
            try:
                z_values = [_point3(point)[2] for point in raw_corners]
                thickness = abs(_as_float(geometry["thickness_m"]))
            except (KeyError, TypeError, ValueError):
                return None
            return (min(z_values) - thickness / 2.0, max(z_values) + thickness / 2.0)
    return None


def _solid_overlap_area(subject: Mapping[str, Any], solid: Mapping[str, Any]) -> float | None:
    subject_polygon = _geometry_polygon(subject)
    solid_polygon = _geometry_polygon(solid)
    solid_holes = _raw_geometry_holes(solid)
    if (
        subject_polygon is None
        or solid_polygon is None
        or solid_holes is None
        or not _geometry_has_valid_plan_topology(subject)
        or not _geometry_has_valid_plan_topology(solid)
    ):
        return None
    area = _intersection_area(subject_polygon, solid_polygon)
    if area is None:
        return None
    for hole in solid_holes:
        hole_area = _intersection_area(subject_polygon, hole)
        if hole_area is None:
            return None
        area -= hole_area
    return max(0.0, area)


def _segment_intersection_point(
    first_start: Point2,
    first_end: Point2,
    second_start: Point2,
    second_end: Point2,
) -> Point2 | None:
    """Return a segment intersection, including a collinear endpoint touch."""

    first_a = _cross(first_start, first_end, second_start)
    first_b = _cross(first_start, first_end, second_end)
    second_a = _cross(second_start, second_end, first_start)
    second_b = _cross(second_start, second_end, first_end)
    proper = ((first_a > 1.0e-9 and first_b < -1.0e-9) or
              (first_a < -1.0e-9 and first_b > 1.0e-9)) and (
                  (second_a > 1.0e-9 and second_b < -1.0e-9) or
                  (second_a < -1.0e-9 and second_b > 1.0e-9))
    if proper:
        return _line_intersection(first_start, first_end, second_start, second_end)
    if abs(first_a) <= 1.0e-9 and _point_on_segment(second_start, first_start, first_end):
        return second_start
    if abs(first_b) <= 1.0e-9 and _point_on_segment(second_end, first_start, first_end):
        return second_end
    if abs(second_a) <= 1.0e-9 and _point_on_segment(first_start, second_start, second_end):
        return first_start
    if abs(second_b) <= 1.0e-9 and _point_on_segment(first_end, second_start, second_end):
        return first_end
    return None


def _non_adjacent_crossing(ring: Sequence[Point2]) -> tuple[int, int, Point2] | None:
    ring = _clean_ring(ring)
    edge_count = len(ring)
    for first_index in range(edge_count):
        first_start = ring[first_index]
        first_end = ring[(first_index + 1) % edge_count]
        for second_index in range(first_index + 1, edge_count):
            if second_index in {
                first_index,
                (first_index - 1) % edge_count,
                (first_index + 1) % edge_count,
            }:
                continue
            second_start = ring[second_index]
            second_end = ring[(second_index + 1) % edge_count]
            point = _segment_intersection_point(first_start, first_end, second_start, second_end)
            if point is not None:
                return first_index, second_index, point
    return None


def _plan_rings(element: Element) -> list[tuple[str, list[Point2]]]:
    """Extract the closed plan rings a primitive exposes in the v3 contract."""

    geometry = element.geometry
    geometry_type = geometry.get("type")
    if geometry_type == "box":
        return [("boundary", _box_polygon(geometry) or [])]
    # Quads are also used for vertical facade surfaces.  Their XY projection is a
    # line by design, so they are not closed plan solids and do not belong in this
    # ring validity check.
    if geometry_type == "extrusion":
        raw_boundary = geometry.get("boundary")
        try:
            boundary = _clean_ring(_point2(point) for point in raw_boundary) \
                if isinstance(raw_boundary, Sequence) else []
        except (KeyError, TypeError, ValueError):
            boundary = []
        rings = [("boundary", boundary)]
        raw_holes = geometry.get("holes", [])
        for hole_index, raw_hole in enumerate(raw_holes):
            try:
                ring = _clean_ring(_point2(point) for point in raw_hole) \
                    if isinstance(raw_hole, Sequence) else []
            except (KeyError, TypeError, ValueError):
                ring = []
            rings.append((f"hole-{hole_index}", ring))
        return rings
    return []


def _measure_invalid_plan_rings(elements: Sequence[Element]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    checked_ring_count = 0
    crossing_count = 0
    triangulation_count = 0
    affected_elements: set[str] = set()
    for element in elements:
        ring_has_finding = False
        for ring_name, ring in _plan_rings(element):
            checked_ring_count += 1
            crossing = _non_adjacent_crossing(ring) if len(ring) >= 3 else None
            if crossing is not None:
                first_index, second_index, point = crossing
                crossing_count += 1
                affected_elements.add(element.id)
                ring_has_finding = True
                findings.append(
                    {
                        "element_ids": [element.id],
                        "kind": element.kind,
                        "ring": ring_name,
                        "reason": "non_adjacent_edge_intersection",
                        "edge_indices": [first_index, second_index],
                        "intersection_xy": list(point),
                    }
                )
                continue
            if not _triangulate(ring):
                triangulation_count += 1
                affected_elements.add(element.id)
                ring_has_finding = True
                findings.append(
                    {
                        "element_ids": [element.id],
                        "kind": element.kind,
                        "ring": ring_name,
                        "reason": "triangulation_unavailable",
                        "detail": "ring has fewer than three vertices, zero area, or ear clipping could not evaluate it",
                    }
                )
        # Individual rings can each be simple while the closed solid is still
        # unusable: a hole may overlap another hole or cross the outer boundary.
        # Keep that topology failure visible instead of letting area subtraction
        # turn it into a measured zero-overlap result.
        if (
            not ring_has_finding
            and element.geometry.get("type") == "extrusion"
            and _raw_geometry_holes(element.geometry)
            and not _geometry_has_valid_plan_topology(element.geometry)
        ):
            affected_elements.add(element.id)
            findings.append(
                {
                    "element_ids": [element.id],
                    "kind": element.kind,
                    "ring": "solid",
                    "reason": "invalid_solid_topology",
                    "detail": "boundary and holes do not form a valid polygonal solid",
                }
            )
    numeric = {
        "checked_ring_count": checked_ring_count,
        "affected_element_count": len(affected_elements),
        "non_adjacent_edge_intersection_count": crossing_count,
        "triangulation_unavailable_count": triangulation_count,
    }
    return _check("primitive_invalid_plan_ring", findings, checked_ring_count, numeric)


def _sample_ids(findings: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    return [list(item.get("element_ids", ())) for item in findings[:SAMPLE_LIMIT]]


def _round_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, Mapping):
        return {str(key): _round_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_round_value(item) for item in value]
    return value


def _check(
    class_name: str,
    findings: Sequence[Mapping[str, Any]],
    evaluated_count: int,
    numeric: Mapping[str, Any],
    *,
    unevaluated_count: int = 0,
) -> dict[str, Any]:
    return {
        "class": class_name,
        "count": len(findings),
        "evaluated_count": evaluated_count,
        "unevaluated_count": unevaluated_count,
        "sample_element_ids": _sample_ids(findings),
        "samples": [_round_value(dict(item)) for item in findings[:SAMPLE_LIMIT]],
        "numeric": _round_value(dict(numeric)),
    }


def _measure_head_clearance(treads: Sequence[Element], obstacles: Sequence[Element]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    measured: list[float] = []
    unevaluated = 0
    for tread in treads:
        tread_polygon = _geometry_polygon(tread.geometry)
        tread_z = _geometry_z_interval(tread.geometry)
        if tread_polygon is None or tread_z is None:
            unevaluated += 1
            continue
        tread_top = tread_z[1]
        candidates: list[tuple[float, float, Element]] = []
        for obstacle in obstacles:
            obstacle_z = _geometry_z_interval(obstacle.geometry)
            if obstacle_z is None or obstacle_z[1] <= tread_z[0] + Z_EPS_M:
                continue
            overlap_area = _solid_overlap_area(tread.geometry, obstacle.geometry)
            if overlap_area is None:
                continue
            # A tread inside an atrium/shaft hole has zero solid overlap and must not
            # inherit the AABB of the surrounding plate as a false obstacle.
            if overlap_area <= AREA_EPS_M2:
                continue
            clearance = obstacle_z[0] - tread_top
            candidates.append((clearance, overlap_area, obstacle))
        if not candidates:
            unevaluated += 1
            continue
        clearance, overlap_area, obstacle = min(candidates, key=lambda item: item[0])
        measured.append(clearance)
        if clearance < HEAD_CLEARANCE_REVIEW_M - Z_EPS_M:
            findings.append(
                {
                    "element_ids": [tread.id, obstacle.id],
                    "tread_id": tread.id,
                    "obstacle_id": obstacle.id,
                    "obstacle_kind": obstacle.kind,
                    "clearance_m": clearance,
                    "overlap_area_m2": overlap_area,
                    "tread_top_z": tread_top,
                    "obstacle_underside_z": _geometry_z_interval(obstacle.geometry)[0],  # type: ignore[index]
                }
            )
    numeric: dict[str, Any] = {
        "review_threshold_m": HEAD_CLEARANCE_REVIEW_M,
        "minimum_clearance_m": min(measured) if measured else None,
        "maximum_clearance_m": max(measured) if measured else None,
        "below_review_threshold_count": len(findings),
        "measured_tread_count": len(measured),
    }
    return _check("stair_head_clearance", findings, len(measured), numeric, unevaluated_count=unevaluated)


def _measure_tread_intersections(treads: Sequence[Element], solids: Sequence[Element], class_name: str) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    candidate_pairs = 0
    evaluated_pairs = 0
    unevaluated_pairs = 0
    areas: list[float] = []
    depths: list[float] = []
    volumes: list[float] = []
    for tread in treads:
        tread_z = _geometry_z_interval(tread.geometry)
        for solid in solids:
            candidate_pairs += 1
            solid_z = _geometry_z_interval(solid.geometry)
            if tread_z is None or solid_z is None:
                unevaluated_pairs += 1
                continue
            vertical_overlap = max(0.0, min(tread_z[1], solid_z[1]) - max(tread_z[0], solid_z[0]))
            if vertical_overlap <= Z_EPS_M:
                evaluated_pairs += 1
                continue
            overlap_area = _solid_overlap_area(tread.geometry, solid.geometry)
            if overlap_area is None:
                unevaluated_pairs += 1
                continue
            evaluated_pairs += 1
            if overlap_area <= AREA_EPS_M2:
                continue
            volume_proxy = overlap_area * vertical_overlap
            areas.append(overlap_area)
            depths.append(vertical_overlap)
            volumes.append(volume_proxy)
            findings.append(
                {
                    "element_ids": [tread.id, solid.id],
                    "tread_id": tread.id,
                    "solid_id": solid.id,
                    "solid_kind": solid.kind,
                    "overlap_area_m2": overlap_area,
                    "vertical_overlap_m": vertical_overlap,
                    "intersection_volume_m3": volume_proxy,
                }
            )
    numeric = {
        "tested_pair_count": candidate_pairs,
        "evaluated_pair_count": evaluated_pairs,
        "unevaluated_pair_count": unevaluated_pairs,
        "minimum_overlap_area_m2": min(areas) if areas else None,
        "maximum_overlap_area_m2": max(areas) if areas else None,
        "maximum_vertical_overlap_m": max(depths) if depths else None,
        "total_intersection_volume_m3": sum(volumes) if volumes else 0.0,
    }
    return _check(
        class_name,
        findings,
        evaluated_pairs,
        numeric,
        unevaluated_count=unevaluated_pairs,
    )


def _measure_program_overlaps(zones: Sequence[Element]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    candidate_pairs = 0
    evaluated_pairs = 0
    unevaluated_pairs = 0
    areas: list[float] = []
    by_level: dict[str, list[Element]] = {}
    for zone in zones:
        by_level.setdefault(zone.level_id, []).append(zone)
    for level_id, level_zones in by_level.items():
        for index, first in enumerate(level_zones):
            for second in level_zones[index + 1 :]:
                candidate_pairs += 1
                first_polygon = _geometry_polygon(first.geometry)
                second_polygon = _geometry_polygon(second.geometry)
                if (
                    first_polygon is None
                    or second_polygon is None
                    or not _geometry_has_valid_plan_topology(first.geometry)
                    or not _geometry_has_valid_plan_topology(second.geometry)
                ):
                    unevaluated_pairs += 1
                    continue
                overlap_area = _intersection_area(first_polygon, second_polygon)
                if overlap_area is None:
                    unevaluated_pairs += 1
                    continue
                evaluated_pairs += 1
                if overlap_area <= AREA_EPS_M2:
                    continue
                areas.append(overlap_area)
                findings.append(
                    {
                        "element_ids": [first.id, second.id],
                        "level_id": level_id,
                        "overlap_area_m2": overlap_area,
                    }
                )
    numeric = {
        "tested_pair_count": candidate_pairs,
        "evaluated_pair_count": evaluated_pairs,
        "unevaluated_pair_count": unevaluated_pairs,
        "level_count": len(by_level),
        "minimum_positive_overlap_area_m2": min(areas) if areas else None,
        "maximum_positive_overlap_area_m2": max(areas) if areas else None,
        "total_positive_overlap_area_m2": sum(areas) if areas else 0.0,
    }
    return _check(
        "program_zone_positive_overlap",
        findings,
        evaluated_pairs,
        numeric,
        unevaluated_count=unevaluated_pairs,
    )


def _flight_pair(element: Element) -> str | None:
    # CIR-TRD-A00-S000 -> A; tolerate a future token with a different numeric suffix
    # while requiring the complete element id prefix so unrelated boxes are ignored.
    parts = element.id.split("-")
    if len(parts) < 4 or parts[0] != "CIR" or parts[1] != "TRD":
        return None
    flight_token = parts[2]
    if not flight_token or flight_token[0] not in _FLIGHT_PAIR_BY_LETTER:
        return None
    if not flight_token[1:].isdigit():
        return None
    return _FLIGHT_PAIR_BY_LETTER[flight_token[0]]


def _measure_intercore_tread_collisions(treads: Sequence[Element]) -> dict[str, Any]:
    """Measure true positive-volume collisions between distinct stair-core pairs.

    The same pair's A/B (or C/D, etc.) flights intentionally meet at their turn
    landing; comparing those treads would report the ordinary nosing/landing overlap
    as a defect.  Distinct core pairs are compared only when their z intervals overlap
    and their rotated footprint polygons have positive area intersection.
    """

    grouped: dict[str, list[Element]] = {}
    unassigned = 0
    for tread in treads:
        pair = _flight_pair(tread)
        if pair is None:
            unassigned += 1
            continue
        grouped.setdefault(pair, []).append(tread)
    pair_names = sorted(grouped)
    findings: list[dict[str, Any]] = []
    tested = 0
    volumes: list[float] = []
    areas: list[float] = []
    depths: list[float] = []
    by_pair: dict[str, int] = {}
    for first_index, first_name in enumerate(pair_names):
        for second_name in pair_names[first_index + 1 :]:
            pair_key = f"{first_name}__{second_name}"
            for first in grouped[first_name]:
                first_z = _geometry_z_interval(first.geometry)
                if first_z is None:
                    continue
                for second in grouped[second_name]:
                    second_z = _geometry_z_interval(second.geometry)
                    if second_z is None:
                        continue
                    vertical_overlap = max(0.0, min(first_z[1], second_z[1]) - max(first_z[0], second_z[0]))
                    if vertical_overlap <= Z_EPS_M:
                        continue
                    tested += 1
                    overlap_area = _intersection_area(
                        _geometry_polygon(first.geometry) or [],
                        _geometry_polygon(second.geometry) or [],
                    )
                    if overlap_area is None or overlap_area <= AREA_EPS_M2:
                        continue
                    volume = overlap_area * vertical_overlap
                    areas.append(overlap_area)
                    depths.append(vertical_overlap)
                    volumes.append(volume)
                    by_pair[pair_key] = by_pair.get(pair_key, 0) + 1
                    findings.append(
                        {
                            "element_ids": [first.id, second.id],
                            "flight_pair_a": first_name,
                            "flight_pair_b": second_name,
                            "overlap_area_m2": overlap_area,
                            "vertical_overlap_m": vertical_overlap,
                            "intersection_volume_m3": volume,
                        }
                    )
    numeric = {
        "tested_positive_z_pair_count": tested,
        "flight_pair_count": len(grouped),
        "flight_pair_members": {name: len(grouped[name]) for name in pair_names},
        "collisions_by_pair": by_pair,
        "minimum_overlap_area_m2": min(areas) if areas else None,
        "maximum_overlap_area_m2": max(areas) if areas else None,
        "maximum_vertical_overlap_m": max(depths) if depths else None,
        "total_intersection_volume_m3": sum(volumes) if volumes else 0.0,
        "unassigned_tread_count": unassigned,
    }
    return _check("stair_intercore_tread_volume_intersection", findings, tested, numeric)


def _measure_landing_contact(landings: Sequence[Element], slabs: Sequence[Element]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    offsets: list[float] = []
    contact_areas: list[float] = []
    unevaluated = 0
    evaluated = 0
    slabs_by_level: dict[str, list[Element]] = {}
    for slab in slabs:
        slabs_by_level.setdefault(slab.level_id, []).append(slab)
    for landing in landings:
        landing_polygon = _geometry_polygon(landing.geometry)
        landing_plan = _solid_plan_polygon(landing.geometry)
        landing_z = _geometry_z_interval(landing.geometry)
        candidate_slabs = slabs_by_level.get(landing.level_id, [])
        if (
            landing_polygon is None
            or landing_plan is None
            or landing_z is None
            or not candidate_slabs
        ):
            unevaluated += 1
            reports.append({
                "element_ids": [landing.id],
                "landing_id": landing.id,
                "level_id": landing.level_id,
                "status": "unevaluated_no_level_slab",
            })
            continue

        # A level can contain several slab parts after a hole is split into simple
        # solids.  Keep every valid part whose top is flush with the landing and
        # union their plan polygons before measuring contact.  This avoids both
        # picking one arbitrary part and double-counting overlaps between parts.
        valid_candidates: list[tuple[float, float, Element, Polygon]] = []
        matching_candidates: list[tuple[float, float, Element, Polygon]] = []
        mismatched_candidates: list[tuple[float, float, Element, Polygon]] = []
        edge_candidates: list[tuple[float, float, Element, Polygon]] = []
        invalid_affecting_ids: list[str] = []
        for slab in candidate_slabs:
            slab_z = _geometry_z_interval(slab.geometry)
            slab_plan = _solid_plan_polygon(slab.geometry)
            if slab_z is None or slab_plan is None:
                # An invalid same-level slab can change the union if it reaches
                # the landing.  If its plan is unavailable, retain unknown rather
                # than treating the remaining valid parts as complete evidence.
                if _plan_geometry_may_overlap(landing_plan, slab.geometry):
                    invalid_affecting_ids.append(slab.id)
                continue
            try:
                plan_overlap = landing_plan.intersection(slab_plan).area
            except (GEOSException, TypeError, ValueError):
                invalid_affecting_ids.append(slab.id)
                continue
            vertical_offset = landing_z[1] - slab_z[1]
            candidate = (float(plan_overlap), vertical_offset, slab, slab_plan)
            valid_candidates.append(candidate)
            # Since compiler 3.4 the slab gives the landing its footprint, so a
            # correctly built pair overlaps by nothing and shares an edge. Edge
            # contact -- the landing grown by a hand's width reaching slab -- is the
            # contact a face-owning model can show, and it is measured, not assumed.
            try:
                edge_contact = landing_plan.buffer(EDGE_CONTACT_REACH_M).intersection(slab_plan).area
            except (GEOSException, TypeError, ValueError):
                edge_contact = 0.0
            if plan_overlap <= AREA_EPS_M2 and edge_contact <= AREA_EPS_M2:
                continue
            if plan_overlap <= AREA_EPS_M2:
                edge_candidates.append((float(edge_contact), vertical_offset, slab, slab_plan))
                if abs(vertical_offset) > VERTICAL_REVIEW_TOLERANCE_M:
                    mismatched_candidates.append(candidate)
                continue
            if abs(vertical_offset) <= VERTICAL_REVIEW_TOLERANCE_M:
                matching_candidates.append(candidate)
            else:
                mismatched_candidates.append(candidate)

        if invalid_affecting_ids:
            unevaluated += 1
            reports.append({
                "element_ids": [landing.id, *invalid_affecting_ids],
                "landing_id": landing.id,
                "level_id": landing.level_id,
                "status": "unevaluated_invalid_geometry",
                "reason": "invalid_same_level_slab_may_affect_contact",
                "invalid_slab_ids": invalid_affecting_ids,
            })
            continue

        def union_contact_area(
            candidates: Sequence[tuple[float, float, Element, Polygon]],
        ) -> float | None:
            if not candidates:
                return 0.0
            try:
                union = unary_union([item[3] for item in candidates])
                return max(0.0, float(landing_plan.intersection(union).area))
            except (GEOSException, TypeError, ValueError):
                return None

        contact_area = union_contact_area(matching_candidates)
        plan_overlap_area = union_contact_area(valid_candidates)
        mismatched_contact_area = union_contact_area(mismatched_candidates)
        if contact_area is None or plan_overlap_area is None or mismatched_contact_area is None:
            unevaluated += 1
            reports.append({
                "element_ids": [landing.id],
                "landing_id": landing.id,
                "level_id": landing.level_id,
                "status": "unevaluated_union_geometry",
            })
            continue

        # A valid but non-flush slab still supplies evidence of a vertical error.
        # Prefer it as the representative when it overlaps the landing; otherwise
        # report the matching part with the largest plan overlap for compatibility
        # with the previous single-slab report shape.
        flush_edge_candidates = [item for item in edge_candidates
                                 if abs(item[1]) <= VERTICAL_REVIEW_TOLERANCE_M]
        edge_contact_area = sum(item[0] for item in flush_edge_candidates)
        representative_candidates = (mismatched_candidates or matching_candidates
                                     or flush_edge_candidates or valid_candidates)
        if not representative_candidates:
            unevaluated += 1
            reports.append({
                "element_ids": [landing.id],
                "landing_id": landing.id,
                "level_id": landing.level_id,
                "status": "unevaluated_invalid_geometry",
                "reason": "no_valid_same_level_slab_geometry",
            })
            continue
        representative = max(representative_candidates, key=lambda item: item[0])
        _, representative_offset, slab, _ = representative
        slab_z = _geometry_z_interval(slab.geometry)
        if slab_z is None:  # defensive: valid_candidates already filters this case
            unevaluated += 1
            reports.append({
                "element_ids": [landing.id],
                "landing_id": landing.id,
                "level_id": landing.level_id,
                "status": "unevaluated_invalid_geometry",
            })
            continue
        evaluated += 1
        landing_area = float(landing_plan.area)
        landing_top = landing_z[1]
        contact_depth = max(0.0, min(landing_z[1], slab_z[1]) - max(landing_z[0], slab_z[0]))
        contact_ratio = contact_area / landing_area if landing_area > AREA_EPS_M2 else 0.0
        offsets.append(representative_offset)
        contact_areas.append(contact_area)
        status = "ok"
        if mismatched_contact_area > AREA_EPS_M2:
            status = "vertical_mismatch"
        elif contact_area <= AREA_EPS_M2 and edge_contact_area <= AREA_EPS_M2:
            status = "no_plan_contact"
        matching_ids = [item[2].id for item in matching_candidates] + [
            item[2].id for item in flush_edge_candidates]
        mismatched_ids = [item[2].id for item in mismatched_candidates]
        relevant_ids = [item[2].id for item in valid_candidates]
        report = {
            "element_ids": [landing.id, *relevant_ids],
            "landing_id": landing.id,
            "slab_id": slab.id,
            "slab_ids": relevant_ids,
            "matching_slab_ids": matching_ids,
            "mismatched_slab_ids": mismatched_ids,
            "level_id": landing.level_id,
            "status": status,
            "landing_area_m2": landing_area,
            "contact_area_m2": contact_area,
            "contact_ratio": contact_ratio,
            "edge_contact_area_m2": edge_contact_area,
            "plan_overlap_area_m2": plan_overlap_area,
            "mismatched_contact_area_m2": mismatched_contact_area,
            "contact_depth_m": contact_depth,
            "landing_top_z": landing_top,
            "slab_top_z": slab_z[1],
            "vertical_offset_m": representative_offset,
            "matching_vertical_offsets_m": [item[1] for item in matching_candidates],
            "mismatched_vertical_offsets_m": [item[1] for item in mismatched_candidates],
        }
        reports.append(report)
        if status != "ok":
            findings.append(report)
    numeric = {
        "tested_landing_count": len(reports),
        "evaluated_landing_count": evaluated,
        "unevaluated_landing_count": unevaluated,
        "minimum_contact_area_m2": min(contact_areas) if contact_areas else None,
        "minimum_vertical_offset_m": min(offsets) if offsets else None,
        "maximum_vertical_offset_m": max(offsets) if offsets else None,
        "vertical_tolerance_m": VERTICAL_REVIEW_TOLERANCE_M,
        "reported_ok_count": sum(1 for report in reports if report.get("status") == "ok"),
        "reported_vertical_mismatch_count": sum(
            1 for report in reports if report.get("status") == "vertical_mismatch"
        ),
    }
    result = _check(
        "landing_slab_contact",
        findings,
        evaluated,
        numeric,
        unevaluated_count=unevaluated,
    )
    result["all_measurements"] = [_round_value(report) for report in reports[:SAMPLE_LIMIT]]
    return result


def measure(model: Mapping[str, Any]) -> dict[str, Any]:
    """Measure a decoded ``building_model_v3.json`` mapping.

    The return value is JSON serialisable and deliberately reports findings only;
    it does not mutate the model or label a model code-compliant.
    """

    elements = _iter_elements(model)
    treads = [element for element in elements if element.kind == "stair_tread"]
    floors = [element for element in elements if element.kind == "floor_slab"]
    ceilings = [element for element in elements if element.kind == "ceiling"]
    shafts = [element for element in elements if element.kind == "elevator_shaft"]
    zones = [element for element in elements if element.kind == "program_zone"]
    landings = [element for element in elements if element.kind == "stair_landing"]
    checks = [
        _measure_invalid_plan_rings(elements),
        _measure_head_clearance(treads, [*floors, *ceilings]),
        _measure_tread_intersections(treads, floors, "stair_tread_floor_slab_intersection"),
        _measure_tread_intersections(treads, shafts, "stair_tread_elevator_shaft_intersection"),
        _measure_intercore_tread_collisions(treads),
        _measure_program_overlaps(zones),
        _measure_landing_contact(landings, floors),
    ]
    return {
        "schema_version": "visual-geometry-measurement-1",
        "model_id": model.get("model_id"),
        "measurement_basis": "Exact 2-D polygon intersections plus constant-z primitive intervals; no AABB collision verdicts.",
        "review_conventions": {
            "head_clearance_m": HEAD_CLEARANCE_REVIEW_M,
            "head_clearance_note": "2.0 m is a project design-review convention, not a code-compliance claim.",
            "landing_vertical_tolerance_m": VERTICAL_REVIEW_TOLERANCE_M,
            "positive_area_epsilon_m2": AREA_EPS_M2,
        },
        "element_counts": {
            "stair_tread": len(treads),
            "floor_slab": len(floors),
            "ceiling": len(ceilings),
            "elevator_shaft": len(shafts),
            "program_zone": len(zones),
            "stair_landing": len(landings),
        },
        "checks": checks,
    }


def _load_json(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise ValueError("model JSON must contain an object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_json", type=Path, help="path to building_model_v3.json")
    parser.add_argument("--pretty", action="store_true", help="indent the machine-readable JSON")
    args = parser.parse_args(argv)
    try:
        report = measure(_load_json(args.model_json))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"measure_visual_geometry: {error}", file=sys.stderr)
        return 2
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2 if args.pretty else None, separators=None if args.pretty else (",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
