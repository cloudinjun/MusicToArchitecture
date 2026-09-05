"""Exact planar subtraction, preserving every connected piece and interior ring."""
from shapely.geometry import LineString, Polygon
from shapely.ops import split, unary_union

from .geometry import ExtrusionGeometry, v2


def _ring(points):
    """The extrusion adapter reverses holes: supply every source ring CCW."""
    points = list(points)[:-1]
    area = sum(a[0] * b[1] - b[0] * a[1]
               for a, b in zip(points, points[1:] + points[:1]))
    if area < 0:
        points.reverse()
    return [v2(x, y) for x, y in points]


def polygon(points):
    return Polygon([(p.x, p.y) for p in points])


def _simple_parts(region):
    """Cut through holes without changing the solid region.

    The common extrusion adapter accepts simple concave faces; its nearest-vertex
    bridges are not a reliable tessellation of multiple holes. A line through an
    interior ring opens that ring onto the boundaries of two ordinary polygons.
    These coplanar parts share an edge and retain the exact original solid union.
    """
    pending = [region] if region.geom_type == 'Polygon' else list(region.geoms)
    result = []
    while pending:
        part = pending.pop()
        if part.is_empty:
            continue
        if not part.interiors:
            result.append(part)
            continue
        x = Polygon(part.interiors[0]).representative_point().x
        _, y0, _, y1 = part.bounds
        margin = max(1.0, y1 - y0)
        pieces = list(split(part, LineString([(x, y0 - margin),
                                             (x, y1 + margin)])).geoms)
        if len(pieces) < 2:
            raise ValueError('Could not open an extrusion hole into simple parts')
        pending.extend(pieces)
    return sorted(result, key=lambda part: (-part.area, part.bounds))


def extrusions(boundary, holes, z_base, z_top):
    """Return all parts; invalid input is an error, never silently repaired."""
    outer = polygon(boundary)
    cuts = [polygon(ring) for ring in holes]
    if not outer.is_valid or any(not cut.is_valid for cut in cuts):
        raise ValueError('Invalid plan ring in extrusion input')
    region = outer.difference(unary_union(cuts)) if cuts else outer
    parts = _simple_parts(region)
    return [ExtrusionGeometry(
        boundary=_ring(part.exterior.coords),
        holes=[_ring(ring.coords) for ring in part.interiors],
        z_base=z_base, z_top=z_top) for part in parts]
