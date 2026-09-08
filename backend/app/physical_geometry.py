"""Physical plan projections for the four schema-3 geometry primitives.

The v3 contract carries both semantic geometry and a small set of derived bounds.  A
derived axis-aligned bound is useful for broad-phase queries, but it is not sufficient
for a Program Volume containment check: a rotated box, a hollow extrusion, or an
I-section member can occupy substantially less plan area than its convex hull.

This module is the shared, primitive-level measurement authority for those checks.  It
keeps exact polygons for boxes and extrusions.  Member and quad projections are made
from the emitted mesh and its triangulated faces, then unioned in XY.  No repair,
convex-hull fill, or guessed profile is performed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .geometry import BoxGeometry, ExtrusionGeometry, Geometry, MemberGeometry, QuadGeometry
from .mesh_primitives import primitive_mesh, triangulate_faces


_AREA_EPS_M2 = 1.0e-10
_Z_EPS_M = 1.0e-9


@dataclass(frozen=True)
class PhysicalProjection:
    """Measured physical footprint and vertical extent of one primitive.

    ``footprint`` is a valid Shapely ``Polygon`` or ``MultiPolygon`` in world XY
    coordinates.  ``z_interval`` is ``(bottom, top)`` in metres.  A projection is
    deliberately a value object so callers cannot mistake a broad-phase bounds tuple
    for a measured solid.
    """

    footprint: BaseGeometry
    z_interval: tuple[float, float]

    @property
    def z_bottom(self) -> float:
        return self.z_interval[0]

    @property
    def z_top(self) -> float:
        return self.z_interval[1]

    def __iter__(self):
        """Allow the result to be unpacked as ``footprint, (bottom, top)``.

        Existing review code commonly carries that pair without needing the richer
        value object.  The explicit attributes remain the preferred public form.
        """

        yield self.footprint
        yield self.z_interval


def _as_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    dump = getattr(value, 'model_dump', None)
    if callable(dump):
        result = dump()
        if isinstance(result, Mapping):
            return result
    raise ValueError(f'{label} must be a geometry/profile model or mapping')


def _finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} must be a finite number') from exc
    if not math.isfinite(number):
        raise ValueError(f'{label} must be a finite number')
    return number


def _xy_ring(points: Any, label: str, *, min_length: int = 3) -> list[tuple[float, float]]:
    if not isinstance(points, (list, tuple)) or len(points) < min_length:
        raise ValueError(f'{label} needs at least {min_length} points')
    ring: list[tuple[float, float]] = []
    for index, point in enumerate(points):
        data = _as_mapping(point, f'{label}[{index}]')
        ring.append((_finite(data.get('x'), f'{label}[{index}].x'),
                     _finite(data.get('y'), f'{label}[{index}].y')))
    return ring


def _polygon_with_holes(geometry: Mapping[str, Any]) -> Polygon:
    boundary = _xy_ring(geometry.get('boundary'), 'extrusion boundary')
    holes_data = geometry.get('holes', [])
    if not isinstance(holes_data, (list, tuple)):
        raise ValueError('extrusion holes must be a list of rings')
    holes = [_xy_ring(hole, f'extrusion hole {index}')
             for index, hole in enumerate(holes_data)]
    footprint = Polygon(boundary, holes)
    if footprint.is_empty or not footprint.is_valid or footprint.area <= _AREA_EPS_M2:
        raise ValueError('extrusion boundary or holes form an invalid or zero-area polygon')
    return footprint


def _box_projection(geometry: Mapping[str, Any]) -> PhysicalProjection:
    center = _as_mapping(geometry.get('center'), 'box center')
    size = _as_mapping(geometry.get('size'), 'box size')
    cx, cy, cz = (_finite(center.get(axis), f'box center.{axis}') for axis in 'xyz')
    sx, sy, sz = (_finite(size.get(axis), f'box size.{axis}') for axis in 'xyz')
    if min(sx, sy, sz) <= 0.0:
        raise ValueError('box dimensions must be positive')
    angle = _finite(geometry.get('rotation_z', 0.0), 'box rotation_z')
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    half_x, half_y = sx / 2.0, sy / 2.0
    corners: list[tuple[float, float]] = []
    for local_x, local_y in ((-half_x, -half_y), (half_x, -half_y),
                             (half_x, half_y), (-half_x, half_y)):
        corners.append((cx + cos_a * local_x - sin_a * local_y,
                        cy + sin_a * local_x + cos_a * local_y))
    footprint = Polygon(corners)
    if footprint.is_empty or not footprint.is_valid or footprint.area <= _AREA_EPS_M2:
        raise ValueError('box dimensions form an invalid or zero-area footprint')
    return PhysicalProjection(footprint, (cz - sz / 2.0, cz + sz / 2.0))


def _extrusion_projection(geometry: Mapping[str, Any]) -> PhysicalProjection:
    z_base = _finite(geometry.get('z_base'), 'extrusion z_base')
    z_top = _finite(geometry.get('z_top'), 'extrusion z_top')
    if z_top <= z_base + _Z_EPS_M:
        raise ValueError('extrusion z_top must be above z_base')
    return PhysicalProjection(_polygon_with_holes(geometry), (z_base, z_top))


def _normalise_profiles(profiles: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if profiles is None:
        return {}
    if not isinstance(profiles, Mapping):
        raise ValueError('profiles must be a mapping keyed by profile id')
    normalised: dict[str, Mapping[str, Any]] = {}
    for profile_id, profile in profiles.items():
        normalised[str(profile_id)] = _as_mapping(profile, f'profile {profile_id!r}')
    return normalised


def _mesh_projection(
    geometry: Mapping[str, Any],
    profiles: Mapping[str, Any] | None,
    thickness_m: float | None,
) -> PhysicalProjection:
    kind = geometry.get('type')
    if kind == 'member':
        profile_id = geometry.get('profile')
        if not profile_id:
            raise ValueError('member profile is required')
        profile_map = _normalise_profiles(profiles)
        if profile_id not in profile_map:
            raise ValueError(f'member profile {profile_id!r} is missing')
    elif kind == 'quad':
        if thickness_m is None:
            raise ValueError('quad thickness_m is required for a physical projection')
        thickness_m = _finite(thickness_m, 'quad thickness_m')
        if thickness_m <= 0.0:
            raise ValueError('quad thickness_m must be positive')
        profile_map = _normalise_profiles(profiles)
    else:
        raise ValueError(f'unsupported mesh primitive: {kind!r}')

    try:
        vertices, faces = primitive_mesh(geometry, profile_map, thickness_m)
        triangles = triangulate_faces(vertices, faces)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'{kind} mesh could not be measured: {exc}') from exc
    if not vertices or not triangles:
        raise ValueError(f'{kind} mesh has no faces')

    projected: list[Polygon] = []
    for face_index, triangle in enumerate(triangles):
        try:
            coords = [(float(vertices[index][0]), float(vertices[index][1]))
                      for index in triangle]
        except (IndexError, TypeError, ValueError) as exc:
            raise ValueError(f'{kind} face {face_index} has invalid vertex indices') from exc
        polygon = Polygon(coords)
        # Faces perpendicular to the XY plane collapse to lines under projection.
        # They carry no plan area and are intentionally skipped; a non-degenerate
        # invalid polygon still indicates malformed mesh data and must fail loudly.
        if polygon.is_empty or polygon.area <= _AREA_EPS_M2:
            continue
        if not polygon.is_valid:
            raise ValueError(f'{kind} face {face_index} projects to invalid geometry')
        projected.append(polygon)
    if not projected:
        raise ValueError(f'{kind} has zero-area XY projection')
    footprint = unary_union(projected)
    if footprint.is_empty or not footprint.is_valid or footprint.area <= _AREA_EPS_M2:
        raise ValueError(f'{kind} has an invalid or zero-area XY projection')
    try:
        z_values = [float(vertex[2]) for vertex in vertices]
    except (IndexError, TypeError, ValueError) as exc:
        raise ValueError(f'{kind} mesh has invalid z coordinates') from exc
    if not z_values or not all(math.isfinite(z) for z in z_values):
        raise ValueError(f'{kind} mesh has non-finite z coordinates')
    z_interval = (min(z_values), max(z_values))
    if z_interval[1] <= z_interval[0] + _Z_EPS_M:
        raise ValueError(f'{kind} has zero-height physical extent')
    return PhysicalProjection(footprint, z_interval)


def physical_projection(
    geometry: Geometry | Mapping[str, Any],
    profiles: Mapping[str, Any] | None = None,
    *,
    thickness_m: float | None = None,
) -> PhysicalProjection:
    """Return the measured XY footprint and z interval of one primitive.

    ``profiles`` may contain either :class:`~backend.app.geometry.ProfileSpec`
    instances or their serialised dictionaries.  It is required for members and is
    accepted for quads for a consistent call surface.  A quad must additionally carry
    the emitted positive ``thickness_m`` because that value belongs to the element,
    not to ``QuadGeometry`` itself.

    Invalid, missing, non-finite, or zero-area geometry raises ``ValueError`` with a
    reason suitable for a spatial-rule ``unevaluated`` finding.  The function never
    fills an omitted profile or repairs a malformed polygon.
    """

    data = _as_mapping(geometry, 'geometry')
    kind = data.get('type')
    if kind == 'box':
        return _box_projection(data)
    if kind == 'extrusion':
        return _extrusion_projection(data)
    if kind in {'member', 'quad'}:
        return _mesh_projection(data, profiles, thickness_m)
    raise ValueError(f'unknown or missing geometry primitive type: {kind!r}')


# A descriptive alias for callers that prefer a verb matching their report wording.
project_physical_geometry = physical_projection


__all__ = ['PhysicalProjection', 'physical_projection', 'project_physical_geometry']
