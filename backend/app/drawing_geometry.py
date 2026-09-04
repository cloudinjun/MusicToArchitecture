"""Cutting the model with a plane, and projecting what the cut reveals.

A plan and a section are the same operation at different angles: put a plane through the
building, draw what it passes through as solid, and draw what lies behind it receding.
So there is one implementation here and the two drawing types differ only in the plane
they hand it. A separate plan generator and section generator would drift apart -- the
same wall would end up drawn one way in plan and another in section, which is the
specific failure that makes a drawing set stop being readable as one building.

Three things this does, and one it does not:

**Solidify.** Elements are stored as centre-lines with profiles, boxes, prisms and
quads. A centre-line cannot be cut -- it has no thickness -- so every element is first
turned into a solid using the section it was sized with. This is why the axis skeleton
had to exist first: the profile a member carries is what gives its drawn thickness, and
a member drawn without it would show a beam as a line and a column as a dot.

**Cut.** Convex solids are sliced by walking their edges through the plane and ordering
the crossings. Prisms get their own path: a horizontal plane through an extrusion
returns the boundary polygon exactly, and a vertical one returns a rectangle per
interval where the plane crosses the boundary. That matters for a courtyard plate, whose
polygon is not convex -- treating it as convex would fill the courtyard with building.

**Project.** What lies beyond the cut is drawn as a silhouette. For a convex solid the
convex hull of its projected vertices *is* its silhouette under orthographic projection,
so no separate outline algorithm is needed; prisms project their two boundary rings.

**Not hidden-line removal, exactly.** Occlusion comes from the painter's algorithm in
`drawings.py`: far solids are filled with the paper colour before their outline is
stroked, so nearer ones overpaint them. This is what hand-drawn sections do, it produces
correct occlusion for opaque solids, and it costs nothing. It is not a general HLR
solution and does not pretend to be -- transparent and interpenetrating solids are drawn
as the painter's order happens to place them.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .geometry import (
    BoxGeometry, ExtrusionGeometry, MemberGeometry, ProfileSpec, QuadGeometry, Vector3,
)


Point2 = tuple[float, float]
Point3 = tuple[float, float, float]

# Below this a slice is a graze rather than a cut: a plane touching a face tangentially
# would otherwise produce a zero-area polygon and a stray line on the sheet.
MIN_SLICE_M = 1.0e-4


@dataclass(frozen=True)
class Plane:
    """A cut plane. `normal` points toward the viewer; everything on the far side is
    what the drawing shows."""

    origin: Point3
    normal: Point3

    def signed(self, point: Point3) -> float:
        return sum((point[i] - self.origin[i]) * self.normal[i] for i in range(3))


@dataclass(frozen=True)
class ViewFrame:
    """The sheet's own axes: where 3D goes when it becomes 2D.

    `right` runs left-to-right across the sheet and `up` runs up it. Both are unit and
    perpendicular, and both are perpendicular to the plane normal, so projecting is a
    pair of dot products and nothing is foreshortened -- an orthographic drawing, which
    is the only kind a dimension can be taken off.
    """

    origin: Point3
    right: Point3
    up: Point3
    normal: Point3

    def project(self, point: Point3) -> Point2:
        delta = tuple(point[i] - self.origin[i] for i in range(3))
        return (sum(delta[i] * self.right[i] for i in range(3)),
                sum(delta[i] * self.up[i] for i in range(3)))

    def depth(self, point: Point3) -> float:
        """How far behind the cut plane a point lies. Positive is further away."""
        return -sum((point[i] - self.origin[i]) * self.normal[i] for i in range(3))


def plan_frame(z: float) -> tuple[Plane, ViewFrame]:
    """A horizontal cut at `z`, seen from above. North is up the sheet."""
    origin = (0.0, 0.0, z)
    normal = (0.0, 0.0, 1.0)
    return (Plane(origin, normal),
            ViewFrame(origin, right=(1.0, 0.0, 0.0), up=(0.0, 1.0, 0.0), normal=normal))


def section_frame(origin_xy: Point2, bearing_deg: float) -> tuple[Plane, ViewFrame]:
    """A vertical cut through `origin_xy`, looking along `bearing_deg`.

    Bearing is measured the way a site plan reads it: 0 looks north (+y), 90 looks east
    (+x). The viewer stands on the near side and sees the far side, so the plane normal
    points back at the viewer and everything with positive depth is drawn.
    """
    angle = math.radians(bearing_deg)
    # The direction of view, in plan.
    view = (math.sin(angle), math.cos(angle), 0.0)
    normal = (-view[0], -view[1], 0.0)
    # Right-hand across the sheet, so the drawing is not mirrored.
    right = (math.cos(angle), -math.sin(angle), 0.0)
    origin = (origin_xy[0], origin_xy[1], 0.0)
    return (Plane(origin, normal),
            ViewFrame(origin, right=right, up=(0.0, 0.0, 1.0), normal=normal))


# --- solids ----------------------------------------------------------------------

@dataclass
class Solid:
    """A convex piece of an element, as vertices plus the edges that bound it."""

    vertices: list[Point3]
    edges: list[tuple[int, int]]


_BOX_EDGES = [
    (0, 1), (1, 3), (3, 2), (2, 0),      # bottom
    (4, 5), (5, 7), (7, 6), (6, 4),      # top
    (0, 4), (1, 5), (2, 6), (3, 7),      # verticals
]


def _box_solid(centre: Point3, half: Point3, axes: tuple[Point3, Point3, Point3]
               ) -> Solid:
    vertices = []
    for sz in (-1, 1):
        for sy in (-1, 1):
            for sx in (-1, 1):
                vertices.append(tuple(
                    centre[i]
                    + sx * half[0] * axes[0][i]
                    + sy * half[1] * axes[1][i]
                    + sz * half[2] * axes[2][i]
                    for i in range(3)))
    return Solid(vertices=vertices, edges=list(_BOX_EDGES))


def _normalise(vector: Point3) -> Point3:
    length = math.sqrt(sum(component * component for component in vector))
    if length < 1e-12:
        return (1.0, 0.0, 0.0)
    return tuple(component / length for component in vector)


def _cross(a: Point3, b: Point3) -> Point3:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def member_solids(geometry: MemberGeometry, profile: ProfileSpec | None) -> list[Solid]:
    """One box per centre-line segment, swept at the member's own section.

    Without the profile a member is a line, and a drawing of lines is a diagram: a
    600 mm girder and a 60 mm handrail would be the same mark. The profile is the
    element's real width, so it is what the drawing shows.
    """
    depth = profile.depth_m if profile else 0.2
    width = profile.width_m if profile else 0.2
    solids = []
    for a, b in zip(geometry.path, geometry.path[1:]):
        start = (a.x, a.y, a.z)
        end = (b.x, b.y, b.z)
        along = tuple(end[i] - start[i] for i in range(3))
        length = math.sqrt(sum(component * component for component in along))
        if length < 1e-9:
            continue
        axis = tuple(component / length for component in along)
        # Roll the section about the member axis. A vertical member has no unique
        # "up", so the fallback keeps its section square to the world instead of
        # spinning with floating-point noise in the cross product.
        reference = (0.0, 0.0, 1.0) if abs(axis[2]) < 0.9 else (0.0, 1.0, 0.0)
        side = _normalise(_cross(axis, reference))
        up = _normalise(_cross(side, axis))
        centre = tuple((start[i] + end[i]) / 2.0 for i in range(3))
        solids.append(_box_solid(centre, (length / 2.0, width / 2.0, depth / 2.0),
                                 (axis, side, up)))
    return solids


def box_solid(geometry: BoxGeometry) -> Solid:
    angle = geometry.rotation_z
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    axes = ((cos_a, sin_a, 0.0), (-sin_a, cos_a, 0.0), (0.0, 0.0, 1.0))
    centre = (geometry.center.x, geometry.center.y, geometry.center.z)
    half = (geometry.size.x / 2.0, geometry.size.y / 2.0, geometry.size.z / 2.0)
    return _box_solid(centre, half, axes)


def quad_solid(geometry: QuadGeometry) -> Solid:
    vertices = [(corner.x, corner.y, corner.z) for corner in geometry.corners]
    return Solid(vertices=vertices, edges=[(0, 1), (1, 2), (2, 3), (3, 0)])


# --- cutting -----------------------------------------------------------------------

def slice_convex(solid: Solid, plane: Plane, frame: ViewFrame) -> list[Point2]:
    """The polygon where the plane passes through a convex solid, in sheet coordinates.

    Crossings are collected along the edges and then ordered by angle about their own
    centroid. For a convex solid the section is convex, so angular order is the correct
    order; taking the points as they came off the edge list would produce a bow-tie.
    """
    signs = [plane.signed(vertex) for vertex in solid.vertices]
    if min(signs) > -MIN_SLICE_M or max(signs) < MIN_SLICE_M:
        return []
    crossings: list[Point2] = []
    for i, j in solid.edges:
        si, sj = signs[i], signs[j]
        if (si > 0.0) == (sj > 0.0):
            continue
        if abs(si - sj) < 1e-12:
            continue
        t = si / (si - sj)
        point = tuple(solid.vertices[i][k]
                      + (solid.vertices[j][k] - solid.vertices[i][k]) * t
                      for k in range(3))
        crossings.append(frame.project(point))
    if len(crossings) < 2:
        return []
    if len(crossings) == 2:
        # A plane through a *planar* solid -- a glazing quad, a panel -- crosses two
        # edges and the section is a line, not an area. Returning nothing here sent
        # every cut glazing panel down the beyond path, where it was drawn as a pale
        # silhouette of the whole sheet of glass instead of the heavy short line that
        # says "you are cutting through this". Two points is a legitimate section.
        return list(crossings)
    cx = sum(point[0] for point in crossings) / len(crossings)
    cy = sum(point[1] for point in crossings) / len(crossings)
    ordered = sorted(crossings, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    # Drop duplicates produced by crossings that land on a shared vertex.
    unique: list[Point2] = []
    for point in ordered:
        if not unique or math.dist(point, unique[-1]) > MIN_SLICE_M:
            unique.append(point)
    if len(unique) > 2 and math.dist(unique[0], unique[-1]) <= MIN_SLICE_M:
        unique.pop()
    return unique if len(unique) >= 3 else []


def slice_extrusion(geometry: ExtrusionGeometry, plane: Plane, frame: ViewFrame
                    ) -> list[list[Point2]]:
    """Cut a prism. Horizontal planes and vertical planes are different problems.

    A horizontal cut returns the boundary itself -- exact, and the only way to keep a
    courtyard open, since the convex path would bridge straight across it. A vertical
    cut returns one rectangle for each interval where the plane is inside the boundary,
    which is what a section through a plate with a hole in it actually looks like.
    """
    boundary = geometry.boundary
    holes = list(geometry.holes)
    horizontal = abs(plane.normal[2]) > 0.99
    if horizontal:
        z = plane.origin[2]
        if not (geometry.z_base + MIN_SLICE_M < z < geometry.z_top - MIN_SLICE_M):
            return []
        # The outer ring first, then each void. A courtyard or an atrium is carried in
        # `holes`, not as a notch in the boundary, so reading only the boundary drew
        # the slab solid and put a floor across the void -- the plan then described a
        # building you could walk over the atrium of.
        return ([[frame.project((point.x, point.y, z)) for point in boundary]]
                + [[frame.project((point.x, point.y, z)) for point in ring]
                   for ring in holes])

    # Vertical plane: find where it crosses the rings, in sheet-x order. Holes count
    # the same way -- each crossing flips inside to outside -- so a section through a
    # plate with an atrium comes back as two bands with the void between them.
    hits: list[float] = []
    for ring in [boundary] + holes:
        count = len(ring)
        for i in range(count):
            a, b = ring[i], ring[(i + 1) % count]
            sa = plane.signed((a.x, a.y, 0.0))
            sb = plane.signed((b.x, b.y, 0.0))
            if (sa > 0.0) == (sb > 0.0) or abs(sa - sb) < 1e-12:
                continue
            t = sa / (sa - sb)
            point = (a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, 0.0)
            hits.append(frame.project(point)[0])
    hits.sort()
    # The sheet heights of the prism's two faces. Projected rather than assumed: the
    # frame decides which way is up, and reading it off is what keeps this correct if
    # a drawing ever looks along a different axis.
    z0 = frame.project((plane.origin[0], plane.origin[1], geometry.z_base))[1]
    z1 = frame.project((plane.origin[0], plane.origin[1], geometry.z_top))[1]
    bands: list[list[Point2]] = []
    # Crossings pair up: in, out, in, out. An odd count means the plane grazed a vertex.
    for i in range(0, len(hits) - 1, 2):
        u0, u1 = hits[i], hits[i + 1]
        if u1 - u0 < MIN_SLICE_M:
            continue
        bands.append([(u0, z0), (u1, z0), (u1, z1), (u0, z1)])
    return bands


# --- projecting --------------------------------------------------------------------

def convex_hull(points: list[Point2]) -> list[Point2]:
    """Monotone chain hull. For a convex solid this is exactly its silhouette."""
    unique = sorted(set((round(x, 6), round(y, 6)) for x, y in points))
    if len(unique) < 3:
        return unique

    def half(source: list[Point2]) -> list[Point2]:
        out: list[Point2] = []
        for point in source:
            while len(out) >= 2:
                (x1, y1), (x2, y2) = out[-2], out[-1]
                if (x2 - x1) * (point[1] - y1) - (y2 - y1) * (point[0] - x1) > 0:
                    break
                out.pop()
            out.append(point)
        return out

    lower = half(unique)
    upper = half(list(reversed(unique)))
    return lower[:-1] + upper[:-1]


Rect = tuple[float, float, float, float]


def clip_polygon(points: list[Point2], rect: Rect) -> list[Point2]:
    """Sutherland-Hodgman against the sheet.

    A ground-floor plan sits on a site slab a hundred and fifty metres across. Left
    whole it sets the sheet extents, and the building -- the subject of the drawing --
    ends up a third of the page at 1:100. Dropping the site instead would be worse: the
    plan would float with no ground under it. Clipping keeps the ground, bounded by the
    sheet, which is what a drawing does at its edge anyway.
    """
    x0, y0, x1, y1 = rect
    output = list(points)
    for which, bound in ((0, x0), (1, x1), (2, y0), (3, y1)):
        if not output:
            return []

        def inside(point: Point2, which=which, bound=bound) -> bool:
            if which == 0:
                return point[0] >= bound
            if which == 1:
                return point[0] <= bound
            if which == 2:
                return point[1] >= bound
            return point[1] <= bound

        def cross(a: Point2, b: Point2, which=which, bound=bound) -> Point2:
            if which in (0, 1):
                span = b[0] - a[0]
                t = (bound - a[0]) / span if abs(span) > 1e-12 else 0.0
                return (bound, a[1] + (b[1] - a[1]) * t)
            span = b[1] - a[1]
            t = (bound - a[1]) / span if abs(span) > 1e-12 else 0.0
            return (a[0] + (b[0] - a[0]) * t, bound)

        buffer: list[Point2] = []
        for index, current in enumerate(output):
            previous = output[index - 1]
            if inside(current):
                if not inside(previous):
                    buffer.append(cross(previous, current))
                buffer.append(current)
            elif inside(previous):
                buffer.append(cross(previous, current))
        output = buffer
    return output


def clip_polyline(points: list[Point2], rect: Rect) -> list[list[Point2]]:
    """Keep the parts of an open line that fall inside the sheet."""
    x0, y0, x1, y1 = rect

    def inside(point: Point2) -> bool:
        return x0 <= point[0] <= x1 and y0 <= point[1] <= y1

    runs: list[list[Point2]] = []
    current: list[Point2] = []
    for point in points:
        if inside(point):
            current.append(point)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return [run for run in runs if len(run) >= 2]


def silhouette(solid: Solid, frame: ViewFrame) -> list[Point2]:
    return convex_hull([frame.project(vertex) for vertex in solid.vertices])


def extrusion_rings(geometry: ExtrusionGeometry, frame: ViewFrame
                    ) -> list[list[Point2]]:
    """A prism seen from beyond: its rings at both faces, voids included."""
    rings = [geometry.boundary] + list(geometry.holes)
    return [[frame.project((point.x, point.y, z)) for point in ring]
            for ring in rings for z in (geometry.z_base, geometry.z_top)]
