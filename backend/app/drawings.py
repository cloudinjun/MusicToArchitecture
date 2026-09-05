"""Floor plans, elevations and sections, drawn from the model by cutting it with a plane.

A drawing here is not a picture of the model; it is a *reading* of it. Every mark on
the sheet carries the id of the element it came from, so a line can be traced back to
the thing it describes and, in the other direction, an element can be asked which
drawings show it. That is what closes the loop: the drawing set cannot drift from the
model, because there is nothing in it that was not derived from the model, and the
`DrawingAudit` at the end says so by counting rather than by assertion.

The order of operations is the order a drawing is actually made in:

1. **Cut.** One plane, handed in. A plan is a horizontal cut 1.2 m above the floor; a
   section is a vertical cut at any bearing; an elevation is the same vertical cut with
   the plane set down outside the building, so that nothing is cut and everything is
   beyond. Same code -- see `drawing_geometry`.
2. **Sort by depth and paint back to front.** Far solids are filled with the paper
   colour before their outline is stroked, so nearer things overpaint them. Occlusion
   falls out of the ordering, which is how it is done by hand.
3. **Stroke from the standard.** No weight, tone or dash is chosen here. Each mark
   states its role and its state, and `drawing_standard` answers. That is what keeps a
   sheet coherent and lets the whole set be restyled from one table.
4. **Annotate.** Grid, dimensions, level datums, section marks, room names, scale bar,
   north point. Annotation is where a drawing stops being a shape and becomes
   measurable.
5. **Issue.** `drawing_sheet` puts the drawing on paper: one size for the set, a frame,
   a title block read off the model, a key plan read off the lattice, and a cover that
   lists the set.

One thing worth saying plainly: the cut is geometric, not semantic. Nothing is on a list
of "things that get cut in plan". An element is cut when the plane passes through its
solid and not otherwise, which means a mezzanine, a sloped soffit or a stair mid-flight
land correctly without anyone having thought about them in advance. The two exceptions
are stated where they happen: a scale figure is never cut, because a body sliced at
1.2 m is not information, and a lift shaft is cut as the hollow core it is rather than
the solid block the model carries for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import pathlib
import math
import re

from .datums import Lattice
from .drawing_geometry import (
    Plane, Point2, Solid, ViewFrame, box_solid, convex_hull, extrusion_rings,
    clip_polygon, clip_polyline, member_solids, plan_frame, quad_solid,
    section_frame, silhouette, slice_convex, slice_extrusion,
)
from .drawing_sheet import (
    FONT, INK_SOFT, CoverFacts, KeyPlan, SetIdentity, SheetSpec, cover_svg,
    drawing_area, earth_pattern_defs, frame_and_title, paper_for, text as sheet_text,
    line as sheet_line,
)
from .drawing_standard import (
    CutState, DrawingRole, DrawingStandard, LineType, NEVER_OVERHEAD_KINDS,
    OVERHEAD_ROLES, PLAN_STANDARD, SECTION_STANDARD, Scale, Stroke, Tone, Weight,
)
from .geometry import (
    BoxGeometry, ExtrusionGeometry, MemberGeometry, ProfileSpec, QuadGeometry, Vector2,
)
from .version import COMPILER_VERSION


# Where a plan is cut. 1.2 m is the convention: above a desk and a window sill, below a
# door head, so a plan shows doorways as openings and windows as cut glazing.
PLAN_CUT_HEIGHT_M = 1.2

# How far above the cut plane overhead work is still drawn dashed. Beyond this it
# belongs to the storey above and showing it would be two plans on one sheet.
OVERHEAD_REACH_M = 4.5

# How far a plan reaches past the floor plate it draws. Enough ground to sit the
# building on and to carry the grid bubbles and dimension strings, not the site.
PLAN_CLIP_MARGIN_M = 7.0

# A section shows a little ground either side so the building sits on
# something, and enough sky for the parapet to end against.
SECTION_CLIP_MARGIN_M = 6.0

# How much earth a section shows under the lowest floor: enough to hold the footings
# and to read as ground, not so much that the building floats on a block of hatch.
SECTION_EARTH_M = 2.0

# Sky above the roof datum. Enough for the roof structure and the parapet to end
# against; not so much that two sections cannot share a sheet.
SECTION_SKY_M = 3.5

# The offsets a section will try, in order, to get its plane off a wall that runs
# parallel to it. A plane inside a partition cuts it lengthwise and draws the whole
# wall as a block of poché across the room it bounds; half a metre either way and
# the same section reads. The requested offset is tried first, then the rest.
SECTION_OFFSET_STEPS_M = (0.0, 0.6, -0.6, 1.2, -1.2, 1.8, -1.8, 2.4, -2.4, 3.0, -3.0)

# Element kinds a section must not lie inside. Anything thin and planar.
WALL_KINDS: frozenset[str] = frozenset({
    'partition', 'partition_head', 'door', 'shear_wall', 'core_wall', 'wall_panel',
    'solid_wall_panel', 'spandrel_panel', 'glazing_panel',
})

# Paper between drawings that share a sheet, and the caption under each.
SHEET_GUTTER_MM = 16.0
CAPTION_MM = 14.0

# How far outside the nearest face an elevation's plane is set down. It only has to
# clear the building; nothing is cut, so the exact figure changes no line.
ELEVATION_STANDOFF_M = 2.0

# The wall a lift shaft is drawn with. The model carries the shaft as a solid prism
# because that is what the structure needs to see; a drawing needs the hollow.
SHAFT_WALL_M = 0.2

# The four faces an elevation set covers, named for the face and given the bearing the
# viewer looks along: the north elevation is seen from the north, looking south.
ELEVATION_FACES: tuple[tuple[str, float], ...] = (
    ('North', 180.0), ('East', 270.0), ('South', 0.0), ('West', 90.0),
)

PAPER_WHITE = '#ffffff'


@dataclass
class Mark:
    """One drawn thing, and the element it came from.

    `element_id` is not decoration. It is what makes the sheet auditable: every mark
    can be traced to a member, and the audit can ask the opposite question -- which
    elements inside the cut produced no mark at all.
    """

    element_id: str
    kind: str
    role: DrawingRole
    state: CutState
    stroke: Stroke
    points: list[Point2]
    closed: bool = True
    fill: Tone | None = None
    depth: float = 0.0
    # A named hatch pattern instead of a tone; the sheet defines the pattern once.
    hatch: str | None = None
    # False for a fill that has lost its outline to the sheet edge. A polygon clipped
    # by the sheet keeps its poché, but the edge the clip made is not an edge of the
    # thing, and stroking it draws a box that is not there.
    outline: bool = True


@dataclass
class Annotation:
    """Grid, dimension, datum, label. Carried apart from the building's own marks so a
    sheet can be issued without them, and so the audit never counts a grid bubble as a
    drawn element."""

    kind: str
    stroke: Stroke | None
    points: list[Point2] = field(default_factory=list)
    text: str = ''
    anchor: Point2 = (0.0, 0.0)
    size_mm: float = 2.5
    align: str = 'middle'
    rotate: float = 0.0
    weight: int | None = None


@dataclass
class DrawingAudit:
    """What the sheet did and did not show, counted rather than claimed."""

    elements_considered: int
    elements_drawn: int
    elements_cut: int
    marks: int
    omitted_by_scale: dict[str, int]
    outside_cut: int

    @property
    def coverage(self) -> float:
        eligible = self.elements_considered - sum(self.omitted_by_scale.values())
        if eligible <= 0:
            return 1.0
        return (self.elements_drawn + self.outside_cut) / eligible


@dataclass
class Drawing:
    id: str
    title: str
    kind: str                    # 'plan' | 'section' | 'elevation'
    standard: DrawingStandard
    marks: list[Mark]
    annotations: list[Annotation]
    extents: tuple[float, float, float, float]   # u_min, v_min, u_max, v_max, metres
    audit: DrawingAudit
    subtitle: str = ''
    # How the drawing is issued. None until the set lays itself out, in which case the
    # sheet is sized to its content and carries the plain title line.
    sheet: SheetSpec | None = None

    @property
    def content_mm(self) -> tuple[float, float]:
        """The drawing's own size on paper, annotation included, before any frame."""
        u0, v0, u1, v1 = self.extents
        scale = self.standard.scale
        return (scale.to_paper_mm(u1 - u0), scale.to_paper_mm(v1 - v0))

    # -- sheet ---------------------------------------------------------------
    def body_svg(self, origin: Point2, *, denominator: int | None = None,
                 annotations: bool = True) -> str:
        """The drawing itself, placed with its top-left content corner at `origin`.

        `denominator` redraws the same marks at another scale -- the cover's
        miniatures -- and applies that scale's detail level, so a 1:400 miniature
        drops what a 1:400 drawing drops. Weights stay paper weights either way.
        """
        standard = self.standard
        scale = standard.scale
        if denominator is not None:
            standard = DrawingStandard(scale=Scale(denominator))
            scale = standard.scale
        u0, v0, u1, v1 = self.extents
        origin_x, origin_y = origin

        def to_paper(point: Point2) -> Point2:
            return (origin_x + scale.to_paper_mm(point[0] - u0),
                    origin_y + scale.to_paper_mm(v1 - point[1]))

        parts: list[str] = [
            '<g stroke-linecap="round" stroke-linejoin="round" fill="none">',
        ]

        def path_of(points: list[Point2], closed: bool) -> str:
            paper = [to_paper(point) for point in points]
            body = ' L '.join(f'{x:.3f} {y:.3f}' for x, y in paper[1:])
            return (f'M {paper[0][0]:.3f} {paper[0][1]:.3f}'
                    + (f' L {body}' if body else '')
                    + (' Z' if closed else ''))

        def emit(points: list[Point2], stroke: Stroke, closed: bool,
                 fill: str = 'none', element_id: str = '', outline: bool = True) -> None:
            if len(points) < 2:
                return
            if outline:
                attrs = (f'd="{path_of(points, closed)}" fill="{fill}" '
                         f'stroke="{stroke.colour}" '
                         f'stroke-width="{stroke.weight.value:g}"')
                dash = stroke.line_type.dasharray()
                if dash:
                    attrs += f' stroke-dasharray="{dash}"'
            else:
                attrs = f'd="{path_of(points, closed)}" fill="{fill}" stroke="none"'
            if element_id:
                # The mark names its element on the sheet itself, so a viewer can ask
                # what a line is by clicking it. The id was already on the mark; this
                # is the only place it was being dropped.
                attrs += f' data-element="{_escape(element_id)}"'
            parts.append(f'<path {attrs}/>')

        # Painter's algorithm: furthest first, each filled with paper before it is
        # stroked, so what is nearer covers what is behind it.
        for mark in sorted(self.marks, key=lambda m: -m.depth):
            if denominator is not None and not standard.draws(mark.role):
                continue
            fill = PAPER_WHITE
            if mark.hatch:
                fill = f'url(#{mark.hatch})'
            elif mark.fill is not None:
                value = round(mark.fill.value * 255)
                fill = f'#{value:02x}{value:02x}{value:02x}'
            elif mark.role == 'glazing' or not mark.closed:
                fill = 'none'
            emit(mark.points, mark.stroke, mark.closed, fill, mark.element_id,
                 outline=mark.outline)

        if annotations:
            for note in self.annotations:
                if note.kind == 'text':
                    x, y = to_paper(note.anchor)
                    colour = note.stroke.colour if note.stroke else '#000000'
                    rotate = (f' transform="rotate({note.rotate:g} {x:.3f} {y:.3f})"'
                              if note.rotate else '')
                    weight = f' font-weight="{note.weight}"' if note.weight else ''
                    parts.append(
                        f'<text x="{x:.3f}" y="{y:.3f}" font-size="{note.size_mm:g}" '
                        f'font-family="{FONT}" '
                        f'fill="{colour}" text-anchor="{note.align}"{weight}{rotate}>'
                        f'{_escape(note.text)}</text>')
                elif note.kind == 'fill' and note.stroke is not None:
                    emit(note.points, note.stroke, closed=True, fill=note.stroke.colour)
                elif note.stroke is not None:
                    emit(note.points, note.stroke, closed=note.kind == 'polygon')

        parts.append('</g>')
        return '\n'.join(parts)

    def to_svg(self, margin_mm: float = 18.0, title_block_mm: float = 26.0) -> str:
        """The drawing on its own: sized to its content, with a plain title line.

        The issued set does not use this -- `Sheet.to_svg` composes one or more
        drawings on standard paper -- but a single drawing must still be able to
        stand alone, for a test, a probe, or a quick look at one cut.
        """
        scale = self.standard.scale
        content_w, content_h = self.content_mm
        if self.sheet is not None:
            width, height = self.sheet.paper_mm
            area_x, area_y, area_w, area_h = drawing_area(self.sheet.paper)
            origin = (area_x + (area_w - content_w) / 2.0,
                      area_y + (area_h - content_h) / 2.0)
        else:
            width = content_w + margin_mm * 2
            height = content_h + margin_mm * 2 + title_block_mm
            origin = (margin_mm, margin_mm)
        parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width:.2f}mm" height="{height:.2f}mm" '
            f'viewBox="0 0 {width:.3f} {height:.3f}">',
            f'<rect width="{width:.3f}" height="{height:.3f}" fill="{PAPER_WHITE}"/>',
            earth_pattern_defs(),
            self.body_svg(origin),
        ]
        if self.sheet is not None:
            parts.append(frame_and_title(
                self.sheet, title=self.title, subtitle=self.subtitle,
                drawing_id=self.id, scale_name=scale.name, kind=self.kind))
        else:
            parts.append(self._title_block(width, height, title_block_mm, margin_mm))
        parts.append('</svg>')
        return '\n'.join(parts)

    def _title_block(self, width: float, height: float, block_mm: float,
                     margin_mm: float) -> str:
        top = height - block_mm
        return (
            f'<g font-family="Helvetica, Arial, sans-serif">'
            f'<line x1="{margin_mm:.2f}" y1="{top:.2f}" '
            f'x2="{width - margin_mm:.2f}" y2="{top:.2f}" '
            f'stroke="#000000" stroke-width="{Weight.MEDIUM.value:g}"/>'
            f'<text x="{margin_mm:.2f}" y="{top + 8:.2f}" font-size="4.2" '
            f'fill="#000000">{_escape(self.title)}</text>'
            f'<text x="{margin_mm:.2f}" y="{top + 14:.2f}" font-size="2.6" '
            f'fill="#3a3a3a">{_escape(self.subtitle)}</text>'
            f'<text x="{width - margin_mm:.2f}" y="{top + 8:.2f}" font-size="3.4" '
            f'fill="#000000" text-anchor="end">{self.standard.scale.name} @ A1</text>'
            f'<text x="{width - margin_mm:.2f}" y="{top + 14:.2f}" font-size="2.4" '
            f'fill="#3a3a3a" text-anchor="end">{_escape(self.id)}</text>'
            f'</g>')


def _escape(text: str) -> str:
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


# --- turning elements into solids --------------------------------------------------

def _solids_for(geometry, profiles: dict[str, ProfileSpec]) -> list[Solid]:
    if isinstance(geometry, MemberGeometry):
        return member_solids(geometry, profiles.get(geometry.profile))
    if isinstance(geometry, BoxGeometry):
        return [box_solid(geometry)]
    if isinstance(geometry, QuadGeometry):
        return [quad_solid(geometry)]
    return []


def _z_range(geometry) -> tuple[float, float]:
    if isinstance(geometry, ExtrusionGeometry):
        return geometry.z_base, geometry.z_top
    if isinstance(geometry, MemberGeometry):
        zs = [point.z for point in geometry.path]
        return min(zs), max(zs)
    if isinstance(geometry, BoxGeometry):
        half = geometry.size.z / 2.0
        return geometry.center.z - half, geometry.center.z + half
    if isinstance(geometry, QuadGeometry):
        zs = [corner.z for corner in geometry.corners]
        return min(zs), max(zs)
    return (0.0, 0.0)


def _shaft_geometry(geometry: ExtrusionGeometry) -> ExtrusionGeometry:
    """The lift shaft as walls around a void.

    The compiler emits the shaft as a solid prism, which is right for the structure
    that leans on it and wrong for a drawing: cut, a solid prism is a grey block through
    every plan and a grey column up every section, and a reader takes it for a wall
    four metres thick. The hollow is built here rather than in the compiler because it
    is a drawing fact -- the load path does not care where the car goes.
    """
    if geometry.holes:
        return geometry
    xs = [point.x for point in geometry.boundary]
    ys = [point.y for point in geometry.boundary]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    wall = SHAFT_WALL_M
    if x1 - x0 <= 2 * wall + 0.3 or y1 - y0 <= 2 * wall + 0.3:
        return geometry
    inner = [Vector2(x=x0 + wall, y=y0 + wall), Vector2(x=x1 - wall, y=y0 + wall),
             Vector2(x=x1 - wall, y=y1 - wall), Vector2(x=x0 + wall, y=y1 - wall)]
    return geometry.model_copy(update={'holes': [inner]})


def _principal_extent(points: list[Point2]) -> tuple[tuple[Point2, Point2], float]:
    """The longest chord through a small polygon, and the polygon's width across it.

    This is what decides whether a silhouette is drawn as an outline or collapsed to a
    line. The chord is moved to the middle of the width so the line sits where the
    element's axis is, not along one of its faces.
    """
    best: tuple[Point2, Point2] = (points[0], points[-1])
    best_length = -1.0
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            length = math.dist(points[i], points[j])
            if length > best_length:
                best_length, best = length, (points[i], points[j])
    a, b = best
    if best_length < 1e-9:
        return (a, b), 0.0
    ux, uy = (b[0] - a[0]) / best_length, (b[1] - a[1]) / best_length
    nx, ny = -uy, ux
    offsets = [(p[0] - a[0]) * nx + (p[1] - a[1]) * ny for p in points]
    low, high = min(offsets), max(offsets)
    shift = (low + high) / 2.0
    centred = ((a[0] + nx * shift, a[1] + ny * shift),
               (b[0] + nx * shift, b[1] + ny * shift))
    return centred, high - low


# --- the compiler ------------------------------------------------------------------

def compile_drawing(
    model, plane: Plane, frame: ViewFrame, standard: DrawingStandard, *,
    drawing_id: str, title: str, kind: str, subtitle: str = '',
    keep: tuple[float, float] | None = None,
    above_reach: float | None = None,
    clip_rect: tuple[float, float, float, float] | None = None,
    skip_roles: frozenset[str] = frozenset(),
    skip_kinds: frozenset[str] = frozenset(),
) -> Drawing:
    """Cut the model with `plane` and draw what that reveals.

    `keep` bounds the depth that is drawn, in metres behind the cut. A plan needs it --
    without a floor above to stop at, every storey below would pile into one sheet -- and
    a section usually does not.

    `skip_roles` and `skip_kinds` are what this kind of drawing does not show at all --
    figures in a plan, the earth in an elevation. They are counted as reached by no
    cut, which is what they are on this sheet, rather than as omitted by scale.
    """
    profiles = dict(model.profiles)
    marks: list[Mark] = []
    considered = drawn = cut_count = outside = 0
    omitted: dict[str, int] = {}

    # First pass: how deep the visible field is, so the depth planes are spread over
    # the building this drawing shows rather than over the site it stands on. The
    # plates are what the eye reads as the building; sizing the bands to a hundred and
    # fifty metres of ground put the whole far wall in the nearest band.
    spread = 0.0
    lattice = getattr(model, 'lattice', None)
    if lattice is not None:
        for level in lattice.levels:
            for point in level.plate:
                spread = max(spread, frame.depth((point.x, point.y, level.z)))
    if spread <= 1e-6:
        for group in model.element_groups:
            for instance in group.instances:
                for solid in _solids_for(instance.geometry, profiles):
                    for vertex in solid.vertices:
                        spread = max(spread, frame.depth(vertex))
    if keep is not None:
        spread = min(spread, keep[1])
    spread = max(spread, 1e-3)

    for group in model.element_groups:
        role = standard.role_of(group.kind)
        for instance in group.instances:
            considered += 1
            # Semantic room regions are labels, not opaque building solids. Keeping
            # them in the painter can conceal real floors, stairs and voids.
            if group.kind == 'program_zone':
                outside += 1
                continue
            if not standard.draws(role):
                omitted[group.kind] = omitted.get(group.kind, 0) + 1
                continue
            if role in skip_roles or group.kind in skip_kinds:
                outside += 1
                continue
            produced = _marks_for(instance, group.kind, role, standard, plane, frame,
                                  spread, profiles, keep, above_reach)
            if produced is None:
                outside += 1
                continue
            if produced:
                marks.extend(produced)
                drawn += 1
                if any(mark.state == 'cut' for mark in produced):
                    cut_count += 1
            else:
                outside += 1

    if clip_rect is not None:
        marks = _clip_marks(marks, clip_rect)

    if not marks:
        raise ValueError(f'{drawing_id}: the cut plane passes through nothing')

    us = [point[0] for mark in marks for point in mark.points]
    vs = [point[1] for mark in marks for point in mark.points]
    extents = (min(us), min(vs), max(us), max(vs))

    return Drawing(
        id=drawing_id, title=title, kind=kind, standard=standard, marks=marks,
        annotations=[], extents=extents, subtitle=subtitle,
        audit=DrawingAudit(elements_considered=considered, elements_drawn=drawn,
                           elements_cut=cut_count, marks=len(marks),
                           omitted_by_scale=omitted, outside_cut=outside))


def _plate_rect(plate, frame, z: float, margin: float):
    """The sheet rectangle a plate occupies, grown by `margin`."""
    sheet = [frame.project((point.x, point.y, z)) for point in plate]
    return (min(point[0] for point in sheet) - margin,
            min(point[1] for point in sheet) - margin,
            max(point[0] for point in sheet) + margin,
            max(point[1] for point in sheet) + margin)


def _edges_off_boundary(points: list[Point2], rect) -> list[list[Point2]] | None:
    """The runs of a clipped polygon's edges that are not the clip rectangle itself.

    None when no edge touches the boundary and the polygon may be stroked whole.
    """
    x0, y0, x1, y1 = rect
    eps = 1e-6

    def on_side(a: Point2, b: Point2) -> bool:
        for axis, bound in ((0, x0), (0, x1), (1, y0), (1, y1)):
            if abs(a[axis] - bound) < eps and abs(b[axis] - bound) < eps:
                return True
        return False

    count = len(points)
    flags = [on_side(points[i], points[(i + 1) % count]) for i in range(count)]
    if not any(flags):
        return None
    start = next(i for i, flag in enumerate(flags) if flag) + 1
    runs: list[list[Point2]] = []
    current: list[Point2] = []
    for step in range(count):
        i = (start + step) % count
        if flags[i]:
            if len(current) >= 2:
                runs.append(current)
            current = []
        else:
            if not current:
                current = [points[i]]
            current.append(points[(i + 1) % count])
    if len(current) >= 2:
        runs.append(current)
    return runs


def _clip_marks(marks, rect):
    """Bound the marks to the sheet, without drawing the sheet's edge as a line.

    A polygon clipped by the sheet keeps its fill -- the ground is still the ground
    where the drawing stops -- but the edge the clip produced is not an edge of the
    thing. Stroking it drew a box around every plan at exactly the clip margin and
    ended every section in a vertical line where the earth was cut off.
    """
    kept = []
    for mark in marks:
        if mark.closed:
            clipped = clip_polygon(mark.points, rect)
            if len(clipped) < 3:
                continue
            runs = _edges_off_boundary(clipped, rect)
            if runs is None:
                kept.append(replace(mark, points=clipped))
                continue
            kept.append(replace(mark, points=clipped, outline=False))
            for run in runs:
                kept.append(replace(mark, points=run, closed=False, fill=None,
                                    hatch=None))
        else:
            for run in clip_polyline(mark.points, rect):
                kept.append(replace(mark, points=run))
    return kept


def _marks_for(instance, kind: str, role: DrawingRole, standard: DrawingStandard,
               plane: Plane, frame: ViewFrame, spread: float,
               profiles: dict[str, ProfileSpec],
               keep: tuple[float, float] | None,
               above_reach: float | None) -> list[Mark] | None:
    geometry = instance.geometry
    marks: list[Mark] = []

    # --- a figure is a glyph, never a section ------------------------------------
    if role == 'entourage':
        return _figure_marks(instance, kind, role, standard, frame, spread, keep)

    # --- prisms take their own path, so a courtyard stays open -------------------
    if isinstance(geometry, ExtrusionGeometry):
        if kind == 'elevator_shaft':
            geometry = _shaft_geometry(geometry)
        cut = slice_extrusion(geometry, plane, frame)
        if cut:
            stroke = standard.stroke(role, 'cut')
            # The outer ring carries the poché; the voids inside it are painted back to
            # paper. Order matters and is preserved: the fill goes down first and the
            # holes are cut out of it by the painter, the same way a hole in a solid
            # reads on a drawn plan. A vertical cut returns bands rather than rings,
            # and every band is solid.
            horizontal = abs(plane.normal[2]) > 0.99
            return [Mark(instance.id, kind, role, 'cut', stroke, polygon,
                         fill=(standard.poche(role)
                               if (index == 0 or not horizontal) else None),
                         hatch=(standard.hatch(role)
                                if (index == 0 or not horizontal) else None),
                         depth=0.0)
                    for index, polygon in enumerate(cut) if len(polygon) >= 3]
        depths = [frame.depth((point.x, point.y, z))
                  for point in geometry.boundary for z in _z_range(geometry)]
        state, depth = _state_of(min(depths), max(depths), keep, above_reach)
        if state is None or (state == 'above' and role not in OVERHEAD_ROLES):
            return None
        band = standard.band_for(depth, spread)
        stroke = standard.stroke(role, state, band)
        return [Mark(instance.id, kind, role, state, stroke, ring, closed=True,
                     fill=None, depth=depth)
                for ring in extrusion_rings(geometry, frame) if len(ring) >= 3]

    # --- everything else is one or more convex solids ---------------------------
    solids = _solids_for(geometry, profiles)
    if not solids:
        return None
    any_in_range = False
    for solid in solids:
        polygon = slice_convex(solid, plane, frame)
        if polygon:
            any_in_range = True
            closed = len(polygon) >= 3
            marks.append(Mark(instance.id, kind, role, 'cut',
                              standard.stroke(role, 'cut'), polygon,
                              closed=closed,
                              fill=standard.poche(role) if closed else None,
                              hatch=standard.hatch(role) if closed else None,
                              depth=0.0))
            continue
        depths = [frame.depth(vertex) for vertex in solid.vertices]
        state, depth = _state_of(min(depths), max(depths), keep, above_reach)
        if state is None:
            continue
        if state == 'above' and (role not in OVERHEAD_ROLES
                                 or kind in NEVER_OVERHEAD_KINDS):
            continue
        any_in_range = True
        band = standard.band_for(depth, spread)
        outline = silhouette(solid, frame)
        if len(outline) < 3:
            continue
        stroke = standard.stroke(role, state, band)
        axis, width = _principal_extent(outline)
        if standard.collapses(width):
            # Thinner than a line: a post, a rail, a fin, a mullion seen edge-on. Drawn
            # as its axis, because an outline two strokes wide with no paper between
            # them is a smear, and a hundred of them over a stair is a cage.
            marks.append(Mark(instance.id, kind, role, state, stroke, list(axis),
                              closed=False, fill=None, depth=depth))
        else:
            marks.append(Mark(instance.id, kind, role, state, stroke, outline,
                              closed=True, fill=None, depth=depth))
    if not any_in_range:
        return None
    return marks


def _figure_marks(instance, kind: str, role: DrawingRole, standard: DrawingStandard,
                  frame: ViewFrame, spread: float,
                  keep: tuple[float, float] | None) -> list[Mark] | None:
    """A scale figure as a glyph: a body and a head, sized from the boxes the model
    carries for them.

    Never cut. A section plane through a person yields a rectangle of poché that says
    nothing, and a figure standing in front of the cut has, like everything else on
    that side, been removed. What is drawn is the figure beyond the cut, at the depth
    band it stands in, so it recedes with the wall behind it.
    """
    geometry = instance.geometry
    if not isinstance(geometry, BoxGeometry):
        return None
    solid = box_solid(geometry)
    depths = [frame.depth(vertex) for vertex in solid.vertices]
    near = min(depths)
    if near < 0.0:
        return None
    if keep is not None and near > keep[1]:
        return None
    band = standard.band_for(near, spread)
    stroke = standard.stroke(role, 'beyond', band)
    projected = [frame.project(vertex) for vertex in solid.vertices]
    u_lo = min(p[0] for p in projected)
    u_hi = max(p[0] for p in projected)
    v_lo = min(p[1] for p in projected)
    v_hi = max(p[1] for p in projected)
    cx = (u_lo + u_hi) / 2.0
    half = (u_hi - u_lo) / 2.0
    if instance.id.endswith('-H'):
        radius = min(half, (v_hi - v_lo) / 2.0)
        return [Mark(instance.id, kind, role, 'beyond', stroke,
                     _circle((cx, (v_lo + v_hi) / 2.0), radius, 16),
                     closed=True, fill=None, depth=near)]
    hip = v_lo + (v_hi - v_lo) * 0.46
    body = [(cx - half, v_hi), (cx + half, v_hi), (cx + half * 0.78, hip),
            (cx + half * 0.55, v_lo), (cx - half * 0.55, v_lo), (cx - half * 0.78, hip)]
    return [Mark(instance.id, kind, role, 'beyond', stroke, body, closed=True,
                 fill=None, depth=near),
            Mark(instance.id, kind, role, 'beyond', stroke, [(cx, hip), (cx, v_lo)],
                 closed=False, fill=None, depth=near)]


def _state_of(near: float, far: float, keep: tuple[float, float] | None,
              above_reach: float | None) -> tuple[CutState | None, float]:
    """Where an uncut solid sits relative to the plane, and how far behind it is.

    Depth is measured to the *nearest* point, because that is the face the viewer sees
    and the one whose distance the eye reads.

    The two drawing types disagree about what lies in front of the plane, and the
    disagreement is the whole difference between them. In a plan you stand inside the
    building looking down, so what is above the cut is overhead work -- a beam, a
    canopy, a slab edge -- and it is drawn dashed because it is really there. In a
    section you have removed everything on your side of the plane, so what is in front
    of it is not overhead: it is gone. Drawing it would put the wall you just cut
    through back on top of the drawing.
    """
    if far <= 0.0:
        if above_reach is None:
            return (None, -far)          # a section: cut away, not drawn
        height = -far
        if height > above_reach:
            return (None, height)        # belongs to the storey above
        return ('above', height)
    depth = max(0.0, near)
    if keep is not None and depth > keep[1]:
        return (None, depth)
    return ('beyond', depth)


# --- plans --------------------------------------------------------------------------

def floor_plans(model, standard: DrawingStandard = PLAN_STANDARD, *,
                section_marks=()) -> list[Drawing]:
    """One plan per occupied level, cut at 1.2 m and looking down."""
    lattice: Lattice = model.lattice
    drawings: list[Drawing] = []
    for level in lattice.levels:
        # The roof is cut just above its own datum rather than at 1.2 m: a roof plan is
        # a view down onto the roof, and cutting it at head height would slice the
        # parapet and show the storey below through it. Without this sheet the parapet
        # ring, the purlins and the deck appear on no drawing at all -- which the
        # coverage count made visible.
        roof = level.kind == 'roof'
        cut_height = 0.15 if roof else PLAN_CUT_HEIGHT_M
        cut_z = level.z + cut_height
        plane, frame = plan_frame(cut_z)
        # Looking down: depth grows downward from the cut, and stops at this level's
        # own floor. Overhead work is kept for a limited reach above.
        keep = (0.0, 1.1) if roof else (0.0, PLAN_CUT_HEIGHT_M + 0.9)
        drawing = compile_drawing(
            model, plane, frame, standard,
            drawing_id=f'DWG-PLAN-{level.id}',
            title=(f'Roof plan — {level.id}' if roof
                   else f'Floor plan — {level.id}'),
            subtitle=(f'{level.kind} level, cut {cut_height:.2f} m above '
                      f'FFL {level.z:+.3f} m · overhead shown dashed · '
                      f'loose furniture at the lightest weight'),
            kind='plan', keep=keep,
            above_reach=1.4 if roof else OVERHEAD_REACH_M,
            clip_rect=_plate_rect(level.plate, frame, cut_z,
                                  PLAN_CLIP_MARGIN_M),
            skip_roles=frozenset({'entourage'}))
        annotate_plan(drawing, lattice, level, standard)
        if not roof:
            annotate_rooms(drawing, model, level)
            annotate_doors(drawing, model, level)
            annotate_stair_direction(drawing, model, level)
            annotate_lifts(drawing, model, cut_z)
        if section_marks:
            annotate_section_marks(drawing, section_marks, standard)
        _fit_to_annotations(drawing)
        drawings.append(drawing)
    return drawings


# --- sections and elevations -----------------------------------------------------------

def _plan_centre(lattice: Lattice) -> Point2:
    xs = [point.x for level in lattice.levels for point in level.plate]
    ys = [point.y for level in lattice.levels for point in level.plate]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def _cut_lengthwise(geometry, plane: Plane) -> bool:
    """Whether a vertical plane lies inside a thin planar element that runs along it."""
    if isinstance(geometry, BoxGeometry):
        thin_x = geometry.size.x <= geometry.size.y
        thickness = geometry.size.x if thin_x else geometry.size.y
        if thickness > 0.6:
            return False
        rotation = geometry.rotation_z
        axis = ((math.cos(rotation), math.sin(rotation)) if thin_x
                else (-math.sin(rotation), math.cos(rotation)))
        if abs(axis[0] * plane.normal[0] + axis[1] * plane.normal[1]) < 0.97:
            return False
        centre = (geometry.center.x, geometry.center.y, geometry.center.z)
        return abs(plane.signed(centre)) < thickness / 2.0 + 0.05
    if isinstance(geometry, QuadGeometry):
        corners = [(c.x, c.y, c.z) for c in geometry.corners]
        signed = [plane.signed(corner) for corner in corners]
        return max(abs(value) for value in signed) < 0.15
    if isinstance(geometry, ExtrusionGeometry):
        # A shaft wall runs along its boundary; the plane inside that wall draws the
        # whole wall as a band. Each edge parallel to the plane is checked.
        ring = geometry.boundary
        for i in range(len(ring)):
            a, b = ring[i], ring[(i + 1) % len(ring)]
            edge = (b.x - a.x, b.y - a.y)
            length = math.hypot(*edge) or 1.0
            along = (edge[0] * plane.normal[0] + edge[1] * plane.normal[1]) / length
            if abs(along) > 0.03:
                continue
            if abs(plane.signed((a.x, a.y, 0.0))) < SHAFT_WALL_M + 0.1:
                return True
    return False


def resolve_section_offset(model, bearing_deg: float, offset_m: float) -> float:
    """The requested offset, or the nearest one whose plane is not inside a wall.

    A section is placed where it reads. The requested position is kept when it is
    clear; when it lies along a partition or a shaft wall the plane is stepped off it,
    and the drawing's subtitle says by how much. This is judgement a person applies
    by eye and it is applied here by the same test, so the set does not depend on
    someone noticing a block of grey.
    """
    lattice: Lattice = model.lattice
    centre = _plan_centre(lattice)
    angle = math.radians(bearing_deg)
    walls = [instance.geometry for group in model.element_groups
             if group.kind in WALL_KINDS or group.kind == 'elevator_shaft'
             for instance in group.instances]
    for delta in SECTION_OFFSET_STEPS_M:
        offset = offset_m + delta
        origin = (centre[0] - math.sin(angle) * offset,
                  centre[1] - math.cos(angle) * offset)
        plane, _frame = section_frame(origin, bearing_deg)
        if not any(_cut_lengthwise(geometry, plane) for geometry in walls):
            return offset
    return offset_m


def building_section(model, bearing_deg: float, *, offset_m: float = 0.0,
                     standard: DrawingStandard = SECTION_STANDARD,
                     name: str = 'A', requested_offset_m: float | None = None
                     ) -> Drawing:
    """A vertical cut at any bearing, through the plan's centre plus `offset_m`.

    `bearing_deg` is the direction of view: 0 looks north, 90 east. Any angle works --
    the plane is general, and an oblique section is the same operation as an orthogonal
    one, so there is no separate path for it to be wrong in. `requested_offset_m` is
    where the caller asked for the cut when `offset_m` was moved off a wall; it is
    only used to say so on the sheet.
    """
    lattice: Lattice = model.lattice
    centre = _plan_centre(lattice)
    angle = math.radians(bearing_deg)
    # Offset moves the plane along its own normal, so a section can be slid through
    # the building without changing which way it looks.
    origin = (centre[0] - math.sin(angle) * offset_m,
              centre[1] - math.cos(angle) * offset_m)
    plane, frame = section_frame(origin, bearing_deg)
    # A section runs across a hundred-and-fifty-metre site slab. Bound it to the
    # building the way the plans are bounded, or the sheet is mostly ground with a
    # building somewhere along it.
    across = [frame.project((point.x, point.y, 0.0))[0]
              for level in lattice.levels for point in level.plate]
    heights = [level.z for level in lattice.levels]
    clip_rect = (min(across) - SECTION_CLIP_MARGIN_M,
                 min(heights) - SECTION_EARTH_M,
                 max(across) + SECTION_CLIP_MARGIN_M,
                 max(heights) + SECTION_SKY_M)
    moved = ''
    if requested_offset_m is not None and abs(requested_offset_m - offset_m) > 1e-6:
        moved = (f' (moved {offset_m - requested_offset_m:+.2f} m off a wall that '
                 f'runs along the cut)')
    drawing = compile_drawing(
        model, plane, frame, standard,
        drawing_id=f'DWG-SECT-{name}',
        title=f'Section {name}—{name}',
        subtitle=(f'Cut plane bearing {bearing_deg:g}°, offset {offset_m:+.2f} m '
                  f'from plan centre{moved} · looking {_compass(bearing_deg)} · '
                  f'earth hatched, figures at their true height'),
        kind='section', clip_rect=clip_rect)
    annotate_vertical(drawing, lattice, standard, frame, bearing_deg)
    annotate_section_rooms(drawing, model, plane, frame)
    _fit_to_annotations(drawing)
    return drawing


def _face_enclosed(lattice: Lattice, bearing_deg: float) -> bool:
    """Whether the face an elevation looks at carries an envelope in this run.

    A cutaway run authors the envelope on two faces only; the other two are open, and
    an elevation of an open face shows the floors and the frame rather than a wall.
    That is a fact about the model, so the sheet states it rather than hiding it.
    """
    angle = math.radians(bearing_deg)
    view = (math.sin(angle), math.cos(angle))
    reference = lattice.levels[1] if len(lattice.levels) > 1 else lattice.levels[0]
    centre = _plan_centre(lattice)
    nearest = min(((point.x - centre[0]) * view[0] + (point.y - centre[1]) * view[1])
                  for point in reference.plate)
    face = (centre[0] + view[0] * nearest, centre[1] + view[1] * nearest)
    return lattice.encloses(face[0], face[1])


def building_elevation(model, bearing_deg: float, *, name: str,
                       standard: DrawingStandard = SECTION_STANDARD) -> Drawing:
    """The building seen from outside one face: a section whose plane cuts nothing.

    The plane is set down `ELEVATION_STANDOFF_M` outside the nearest point of the
    building along the direction of view, so every element is beyond it and the
    painter's ordering gives the face with everything behind it correctly hidden. No
    poché, because nothing is cut; the ground is a line, because an elevation is seen
    from grade and the earth is not open in front of it.
    """
    lattice: Lattice = model.lattice
    centre = _plan_centre(lattice)
    angle = math.radians(bearing_deg)
    view = (math.sin(angle), math.cos(angle))
    plates = [(point.x, point.y) for level in lattice.levels for point in level.plate]
    nearest = min((x - centre[0]) * view[0] + (y - centre[1]) * view[1]
                  for x, y in plates)
    # The plates are not the whole building: an entrance flight or a ramp may stand
    # outside them, and a plane set from the plates alone cut one on the fixture.
    # Every element except the site slab is allowed to push the plane out.
    profiles = dict(model.profiles)
    for group in model.element_groups:
        if group.kind == 'site_ground':
            continue
        for instance in group.instances:
            geometry = instance.geometry
            if isinstance(geometry, ExtrusionGeometry):
                points = [(point.x, point.y) for point in geometry.boundary]
            else:
                points = [(vertex[0], vertex[1])
                          for solid in _solids_for(geometry, profiles)
                          for vertex in solid.vertices]
            for x, y in points:
                nearest = min(nearest, (x - centre[0]) * view[0] + (y - centre[1]) * view[1])
    offset = -nearest + ELEVATION_STANDOFF_M
    origin = (centre[0] - view[0] * offset, centre[1] - view[1] * offset)
    plane, frame = section_frame(origin, bearing_deg)
    across = [frame.project((x, y, 0.0))[0] for x, y in plates]
    heights = [level.z for level in lattice.levels]
    base = min(heights)
    clip_rect = (min(across) - SECTION_CLIP_MARGIN_M, base,
                 max(across) + SECTION_CLIP_MARGIN_M, max(heights) + SECTION_SKY_M)
    enclosed = _face_enclosed(lattice, bearing_deg)
    subtitle = (f'Seen from the {name.lower()}, looking {_compass(bearing_deg)} · '
                f'nothing cut, everything beyond · ')
    subtitle += ('envelope authored on this face'
                 if enclosed else
                 'open face: this run authors the envelope on two faces only, so the '
                 'floors and the frame are what this side shows')
    drawing = compile_drawing(
        model, plane, frame, standard,
        drawing_id=f'DWG-ELEV-{name.upper()}',
        title=f'{name} elevation',
        subtitle=subtitle, kind='elevation', clip_rect=clip_rect,
        skip_kinds=frozenset({'site_ground'}))
    annotate_vertical(drawing, lattice, standard, frame, bearing_deg, elevation=True)
    _fit_to_annotations(drawing)
    return drawing


def _fit_to_annotations(drawing: Drawing) -> None:
    """Grow the sheet to hold the annotation.

    Extents are taken from the building's marks, because that is what the drawing is
    of. Grid lines run past it, dimension strings sit outside it and the scale bar sits
    below -- all of which would be cropped at the sheet edge if the extents were left
    where the building ended. Text is allowed for by its length: an anchor inside the
    sheet with the label running off it is the same crop.
    """
    scale = drawing.standard.scale
    us = [point[0] for note in drawing.annotations for point in note.points]
    vs = [point[1] for note in drawing.annotations for point in note.points]
    for note in drawing.annotations:
        if note.kind != 'text':
            continue
        run = scale.to_metres(len(note.text) * note.size_mm * 0.62)
        rise = scale.to_metres(note.size_mm)
        x, y = note.anchor
        if note.rotate:
            us += [x - rise, x + rise]
            vs += [y - run / 2.0, y + run / 2.0]
            continue
        vs += [y - rise * 0.3, y + rise]
        if note.align == 'end':
            us += [x - run, x]
        elif note.align == 'start':
            us += [x, x + run]
        else:
            us += [x - run / 2.0, x + run / 2.0]
    if not us:
        return
    u0, v0, u1, v1 = drawing.extents
    drawing.extents = (min(u0, min(us)), min(v0, min(vs)),
                       max(u1, max(us)), max(v1, max(vs)))


def _compass(bearing_deg: float) -> str:
    names = ['north', 'north-east', 'east', 'south-east',
             'south', 'south-west', 'west', 'north-west']
    return names[int(((bearing_deg % 360) + 22.5) // 45) % 8]


# --- annotation ---------------------------------------------------------------------

def _grid_label(index: int, letters: bool) -> str:
    if not letters:
        return str(index + 1)
    label = ''
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        label = chr(ord('A') + remainder) + label
    return label


_FLIGHT_TREAD = re.compile(r'CIR-TRD-([A-Z]\d{2})-S(\d{3})')


def _inside_ring(point: tuple[float, float], ring) -> bool:
    inside = False
    count = len(ring)
    for i in range(count):
        a, b = ring[i], ring[(i + 1) % count]
        if (a.y > point[1]) != (b.y > point[1]):
            if point[0] < (b.x - a.x) * (point[1] - a.y) / (b.y - a.y) + a.x:
                inside = not inside
    return inside


def _pretty(program: str) -> str:
    return program.replace('_', ' ').title()


def annotate_rooms(drawing: Drawing, model, level) -> None:
    """Room name and area, from the program zone that owns the space.

    A program zone is not a constructed object -- the dependency graph exempts it for
    exactly that reason -- so it has no business being drawn as a solid. As annotation
    it is the most useful thing on the sheet: a plan whose rooms are unnamed can be
    measured but not read, and the area is already known to the compiler, so putting it
    on the drawing costs nothing and settles the usual first question about a plan.
    """
    name = Stroke(Weight.FINE, Tone.CUT)
    area_tone = Stroke(Weight.FINE, Tone.MIDDLE)
    allocation = getattr(model, 'program_allocation', None)
    rooms = {f'PRG-ZON-{zone.level_id}-{zone.space_id}': zone
             for zone in (allocation.zones if allocation is not None else [])}
    u0, v0, u1, v1 = drawing.extents
    for group in model.element_groups:
        if group.kind != 'program_zone':
            continue
        for instance in group.instances:
            if instance.level_id != level.id:
                continue
            box = instance.geometry
            anchor = (box.center.x, box.center.y)
            if not (u0 <= anchor[0] <= u1 and v0 <= anchor[1] <= v1):
                continue
            if any(_inside_ring(anchor, ring) for ring in level.voids):
                continue    # a label floating over an atrium names nothing
            room = rooms.get(instance.id)
            label = room.label if room is not None else _pretty(group.program)
            area_text = (f'{room.area_delivered_m2:.0f} m² allocated'
                         if room is not None else 'AREA UNVERIFIED')
            drawing.annotations.append(Annotation(
                'text', name, text=label.upper(),
                anchor=(anchor[0], anchor[1] + 0.55), size_mm=2.8, weight=600))
            drawing.annotations.append(Annotation(
                'text', area_tone, text=area_text,
                anchor=(anchor[0], anchor[1] - 0.9), size_mm=2.3))


def annotate_section_rooms(drawing: Drawing, model, plane: Plane, frame: ViewFrame
                           ) -> None:
    """Name the spaces a section passes through.

    A section is read room by room -- foyer under auditorium under plant -- and the
    zone the plane crosses is known, so the name goes on the drawing where the space
    is, at about eye height off its floor. Only zones the plane actually passes through
    are named: a room beyond the cut is seen through a wall and is not this room.
    """
    label = Stroke(Weight.FINE, Tone.CUT)
    levels = {level.id: level for level in model.lattice.levels}
    ordered = sorted(model.lattice.levels, key=lambda level: level.z)
    above = {level.id: (ordered[i + 1].z if i + 1 < len(ordered) else level.z + 3.5)
             for i, level in enumerate(ordered)}
    u0, v0, u1, v1 = drawing.extents
    nx, ny = abs(plane.normal[0]), abs(plane.normal[1])
    rx, ry = abs(frame.right[0]), abs(frame.right[1])
    for group in model.element_groups:
        if group.kind != 'program_zone':
            continue
        for instance in group.instances:
            box = instance.geometry
            level = levels.get(instance.level_id)
            if level is None:
                continue
            centre = (box.center.x, box.center.y, box.center.z)
            half_normal = nx * box.size.x / 2.0 + ny * box.size.y / 2.0
            if abs(plane.signed(centre)) > half_normal:
                continue
            across = rx * box.size.x + ry * box.size.y
            if across < 3.0:
                continue
            u = frame.project(centre)[0]
            v = level.z + (above[level.id] - level.z) * 0.42
            if not (u0 <= u <= u1 and v0 <= v <= v1):
                continue
            drawing.annotations.append(Annotation(
                'text', label, text=_pretty(group.program).upper(),
                anchor=(u, v), size_mm=2.6, weight=600))


def annotate_lifts(drawing: Drawing, model, cut_z: float) -> None:
    """The lift car inside its shaft: a lighter rectangle and a cross.

    The shaft walls are cut and drawn from the model. The car is a symbol -- the model
    has no car -- and is drawn as one, at the lightest weight, so a reader sees a lift
    and not a second room.
    """
    car = Stroke(Weight.THIN, Tone.NEAR)
    cross = Stroke(Weight.FINE, Tone.MIDDLE)
    u0, v0, u1, v1 = drawing.extents
    for group in model.element_groups:
        if group.kind != 'elevator_shaft':
            continue
        for instance in group.instances:
            geometry = instance.geometry
            if not isinstance(geometry, ExtrusionGeometry):
                continue
            if not (geometry.z_base < cut_z < geometry.z_top):
                continue
            xs = [point.x for point in geometry.boundary]
            ys = [point.y for point in geometry.boundary]
            inset = SHAFT_WALL_M + 0.35
            x0, x1 = min(xs) + inset, max(xs) - inset
            y0, y1 = min(ys) + inset, max(ys) - inset
            if x1 - x0 < 0.8 or y1 - y0 < 0.8:
                continue
            if not (u0 <= x0 and x1 <= u1 and v0 <= y0 and y1 <= v1):
                continue
            drawing.annotations.append(Annotation(
                'line', car, [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]))
            drawing.annotations.append(Annotation('line', cross, [(x0, y0), (x1, y1)]))
            drawing.annotations.append(Annotation('line', cross, [(x0, y1), (x1, y0)]))


def annotate_doors(drawing: Drawing, model, level) -> None:
    """Leaf and swing arc, opening into the room the door serves.

    The side a door swings to is information, not decoration, and it is derivable here
    rather than guessed: a door's id names the space it belongs to, so it is drawn
    opening into that space. Picking a side by convention instead would put half the
    leaves through the wall they hang on.
    """
    swing = Stroke(Weight.THIN, Tone.NEAR)
    arc = Stroke(Weight.FINE, Tone.MIDDLE)
    zones = {instance.id: instance.geometry
             for group in model.element_groups if group.kind == 'program_zone'
             for instance in group.instances}
    for group in model.element_groups:
        if group.kind != 'door' or group.subsystem != 'partitions':
            continue
        for instance in group.instances:
            if instance.level_id != level.id:
                continue
            box = instance.geometry
            angle = box.rotation_z
            # The leaf runs along the box's longer plan axis; the swing is square to it.
            along = (math.cos(angle), math.sin(angle))
            across = (-math.sin(angle), math.cos(angle))
            leaf = max(box.size.x, box.size.y)
            if box.size.y > box.size.x:
                along, across = across, (-along[0], -along[1])
            centre = (box.center.x, box.center.y)
            # Into the space this door serves.
            zone_id = ('PRG-ZON-' + instance.id.split('PRG-PRT-')[-1]
                       .rsplit('-', 2)[0])
            zone = zones.get(zone_id)
            sense = 1.0
            if zone is not None:
                toward = (zone.center.x - centre[0], zone.center.y - centre[1])
                if toward[0] * across[0] + toward[1] * across[1] < 0:
                    sense = -1.0
            hinge = (centre[0] - along[0] * leaf / 2.0,
                     centre[1] - along[1] * leaf / 2.0)
            tip = (hinge[0] + across[0] * leaf * sense,
                   hinge[1] + across[1] * leaf * sense)
            drawing.annotations.append(Annotation('line', swing, [hinge, tip]))
            # A quarter arc from the open leaf back to the closed jamb.
            steps = 8
            start = math.atan2(tip[1] - hinge[1], tip[0] - hinge[0])
            # The open vector is sense * 90 degrees from the closed vector.
            # Return by the quarter turn, not by the other three quadrants.
            sweep = -sense * math.pi / 2.0
            drawing.annotations.append(Annotation('line', arc, [
                (hinge[0] + leaf * math.cos(start + sweep * i / steps),
                 hinge[1] + leaf * math.sin(start + sweep * i / steps))
                for i in range(steps + 1)]))


def annotate_stair_direction(drawing: Drawing, model, level) -> None:
    """An arrow up each flight, with UP at its head.

    Two flights meeting at a landing look identical in plan; which way they go is
    carried entirely by this arrow, and a plan without it cannot be used to find your
    way through the building.
    """
    line = Stroke(Weight.LIGHT, Tone.CUT)
    label = Stroke(Weight.FINE, Tone.CUT)
    u0, v0, u1, v1 = drawing.extents
    flights: dict[str, list[tuple[int, tuple[float, float], float]]] = {}
    for group in model.element_groups:
        if group.kind != 'stair_tread':
            continue
        for instance in group.instances:
            match = _FLIGHT_TREAD.match(instance.id)
            if not match:
                continue
            box = instance.geometry
            flights.setdefault(match.group(1), []).append(
                (int(match.group(2)), (box.center.x, box.center.y), box.center.z))
    for steps in flights.values():
        steps.sort()
        low, high = steps[0], steps[-1]
        # Only the flights this plan actually shows.
        if not (level.z - 0.6 <= low[2] <= level.z + PLAN_CUT_HEIGHT_M + 1.2):
            continue
        start, end = low[1], high[1]
        span = math.dist(start, end)
        if span < 1.2:
            continue
        if not (u0 <= start[0] <= u1 and v0 <= start[1] <= v1):
            continue
        direction = ((end[0] - start[0]) / span, (end[1] - start[1]) / span)
        head = (start[0] + direction[0] * span * 0.82,
                start[1] + direction[1] * span * 0.82)
        drawing.annotations.append(Annotation('line', line, [start, head]))
        wing = 0.45
        side = (-direction[1], direction[0])
        for turn in (1.0, -1.0):
            drawing.annotations.append(Annotation('line', line, [
                head,
                (head[0] - direction[0] * wing * 1.7 + side[0] * wing * turn,
                 head[1] - direction[1] * wing * 1.7 + side[1] * wing * turn)]))
        drawing.annotations.append(Annotation(
            'text', label, text='UP',
            anchor=(head[0] + direction[0] * 1.1, head[1] + direction[1] * 1.1),
            size_mm=2.4))


def annotate_plan(drawing: Drawing, lattice: Lattice, level, standard: DrawingStandard
                  ) -> None:
    """Grid with bubbles, overall dimensions, north point and scale bar.

    A plan without a grid cannot be built from and cannot be discussed -- "the column on
    the left" is not a reference. The grid is drawn from the same `x_lines`/`y_lines`
    the elements were registered to, so a bubble names the line the column stands on
    rather than a line that happens to pass nearby.
    """
    u0, v0, u1, v1 = drawing.extents
    grid = standard.stroke('grid', 'cut')
    thin = Stroke(Weight.FINE, Tone.NEAR)
    over = 2.2   # how far the grid runs past the building, in metres
    notes = drawing.annotations

    # The profile line: the outline of the floor plate, at the heaviest weight on the
    # sheet. Without it a plan is a field of separate marks that a reader has to
    # assemble into a building; with it the figure reads at arm's length and everything
    # else is understood as being inside or outside it. It is drawn from the level's
    # own plate -- the same polygon the elements were registered against -- so it is a
    # datum like the grid rather than a traced outline that could disagree with them.
    for ring in [level.plate] + list(level.voids):
        notes.append(Annotation('line', Stroke(Weight.PROFILE, Tone.CUT),
                                [(point.x, point.y) for point in ring]
                                + [(ring[0].x, ring[0].y)]))

    # Which grid lines belong here is a property of the plate, not of where the marks
    # happened to fall. Filtering by the drawing's extents looked equivalent and was
    # not: the extents are taken from the marks and then grown to hold the annotation,
    # so a line running along the very edge of the plate sat outside the range at the
    # moment it was tested and inside it by the time the sheet was sized -- and the
    # column standing on that line ended up with no bubble to name it.
    plate_x = [point.x for point in level.plate]
    plate_y = [point.y for point in level.plate]
    x_lo, x_hi = min(plate_x), max(plate_x)
    y_lo, y_hi = min(plate_y), max(plate_y)

    for axis, values, letters in (('x', lattice.x_lines, True),
                                  ('y', lattice.y_lines, False)):
        for index, value in enumerate(values):
            if axis == 'x':
                if not (x_lo - 0.1 <= value <= x_hi + 0.1):
                    continue
                notes.append(Annotation('line', grid,
                                        [(value, v0 - over), (value, v1 + over)]))
                bubble = (value, v1 + over)
            else:
                if not (y_lo - 0.1 <= value <= y_hi + 0.1):
                    continue
                notes.append(Annotation('line', grid,
                                        [(u0 - over, value), (u1 + over, value)]))
                bubble = (u0 - over, value)
            notes.append(Annotation('circle', grid, _circle(bubble, 0.55)))
            notes.append(Annotation('text', Stroke(Weight.FINE, Tone.CUT),
                                    text=_grid_label(index, letters), anchor=(
                                        bubble[0], bubble[1] - 0.18),
                                    size_mm=2.4))

    _dimension_string(notes, lattice.x_lines, v0 - over - 2.4, horizontal=True,
                      standard=standard, low=x_lo, high=x_hi)
    _dimension_string(notes, lattice.y_lines, u0 - over - 2.4, horizontal=False,
                      standard=standard, low=y_lo, high=y_hi)
    _scale_bar(notes, (u0, v0 - over - 5.2), standard)
    _north_point(notes, (u1 + over + 1.4, v1 + over - 1.4))
    notes.append(Annotation('text', thin, text=f'FFL {level.z:+.3f}',
                            anchor=(u1, v0 - over - 0.8), size_mm=2.6, align='end'))


def _section_trace(lattice: Lattice, bearing: float, offset: float,
                   *, pad: float = 2.5) -> tuple[Point2, Point2, Point2, Point2]:
    """Where a section's plane crosses the plan: its two ends, the direction along the
    plane, and the direction of view. Shared by the plan's section marks and the key
    plan, so the two cannot disagree about where a section was taken."""
    xs = [point.x for level in lattice.levels for point in level.plate]
    ys = [point.y for level in lattice.levels for point in level.plate]
    u0, v0, u1, v1 = min(xs), min(ys), max(xs), max(ys)
    centre = ((u0 + u1) / 2.0, (v0 + v1) / 2.0)
    angle = math.radians(bearing)
    along = (math.cos(angle), -math.sin(angle))
    origin = (centre[0] - math.sin(angle) * offset,
              centre[1] - math.cos(angle) * offset)
    reach = max(abs((corner[0] - origin[0]) * along[0]
                    + (corner[1] - origin[1]) * along[1])
                for corner in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))) + pad
    a = (origin[0] - along[0] * reach, origin[1] - along[1] * reach)
    b = (origin[0] + along[0] * reach, origin[1] + along[1] * reach)
    look = (math.sin(angle), math.cos(angle))
    return a, b, along, look


def annotate_section_marks(drawing: Drawing, cuts, standard: DrawingStandard
                           ) -> None:
    """Where each section is taken, drawn on the plan.

    Without this the two halves of the set do not refer to each other: a reader holding
    Section B has no way to know where in the plan it was cut, and the drawings become
    two separate claims about the building rather than one description of it.
    """
    u0, v0, u1, v1 = drawing.extents
    trace = Stroke(Weight.THICK, Tone.CUT, LineType.LONG_DASH)
    tag = Stroke(Weight.FINE, Tone.CUT)
    centre = ((u0 + u1) / 2.0, (v0 + v1) / 2.0)
    for name, bearing, offset in cuts:
        angle = math.radians(bearing)
        # The cut line runs along the plane, which is perpendicular to the view.
        along = (math.cos(angle), -math.sin(angle))
        origin = (centre[0] - math.sin(angle) * offset,
                  centre[1] - math.cos(angle) * offset)
        # Just past the building, not half a diagonal. A section mark sized from the
        # sheet's larger dimension overshoots on the short axis, and since the sheet is
        # then grown to hold its annotation, the mark pushes the sheet out and the plan
        # ends up small and off-centre inside its own drawing.
        reach = max(abs((corner[0] - origin[0]) * along[0]
                        + (corner[1] - origin[1]) * along[1])
                    for corner in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))) + 2.5
        a = (origin[0] - along[0] * reach, origin[1] - along[1] * reach)
        b = (origin[0] + along[0] * reach, origin[1] + along[1] * reach)
        # Stubs at the ends, not a line across the middle. A section mark drawn the
        # full width of the plan sits on top of the drawing it refers to, and at 1:100
        # a heavy long-dash line through the middle of a plan hides more than the mark
        # is worth. The convention is two short lengths and a sight arrow: the reader
        # joins them up, and the plan stays legible.
        stub = min(reach * 0.28, 6.0)
        look = (math.sin(angle), math.cos(angle))
        for end, inward in ((a, 1.0), (b, -1.0)):
            tail = (end[0] + along[0] * stub * inward,
                    end[1] + along[1] * stub * inward)
            drawing.annotations.append(Annotation('line', trace, [end, tail]))
            head = (end[0] + look[0] * 2.0, end[1] + look[1] * 2.0)
            drawing.annotations.append(Annotation('line', trace, [end, head]))
            drawing.annotations.append(Annotation(
                'text', tag, text=name,
                anchor=(end[0] - look[0] * 1.4, end[1] - look[1] * 1.4 - 0.35),
                size_mm=3.0, weight=600))


def annotate_vertical(drawing: Drawing, lattice: Lattice, standard: DrawingStandard,
                      frame: ViewFrame, bearing_deg: float, *,
                      elevation: bool = False) -> None:
    """What a section and an elevation share: level datums with heights, a ground line,
    the grid where the cut is square to it, a vertical dimension string, a scale bar.

    A vertical drawing is read by height, so the datums are the annotation that
    matters: every level line carries its own figure at a datum symbol, and the storey
    heights between them are dimensioned rather than left to be scaled off.
    """
    u0, v0, u1, v1 = drawing.extents
    datum = standard.stroke('grid', 'cut')
    label = Stroke(Weight.FINE, Tone.CUT)
    soft = Stroke(Weight.FINE, Tone.MIDDLE)
    notes = drawing.annotations
    reach = 2.0
    base = min(level.z for level in lattice.levels)
    top = max(level.z for level in lattice.levels)

    for level in lattice.levels:
        if not (v0 - 0.5 <= level.z <= v1 + 0.5):
            continue
        notes.append(Annotation('line', datum,
                                [(u0 - reach, level.z), (u1 + reach, level.z)]))
        # The datum symbol: an open triangle with its apex on the line, the level's
        # name above it and its height below, the way a level is marked on any section.
        mark_u = u1 + reach
        notes.append(Annotation('polygon', label, [
            (mark_u, level.z), (mark_u - 0.36, level.z + 0.5),
            (mark_u + 0.36, level.z + 0.5)]))
        notes.append(Annotation('text', label, text=level.id,
                                anchor=(mark_u + 0.6, level.z + 0.65), size_mm=2.6,
                                align='start', weight=600))
        notes.append(Annotation('text', soft, text=f'{level.z:+.3f}',
                                anchor=(mark_u + 0.6, level.z - 0.55), size_mm=2.3,
                                align='start'))

    # The ground line is the heaviest line on a section: it is what the building
    # stands on, and the eye uses it to find the bottom of the drawing.
    ground = Stroke(Weight.PROFILE, Tone.CUT)
    notes.append(Annotation('line', ground,
                            [(u0 - reach * 1.6, base), (u1 + reach * 1.6, base)]))

    # The grid, where the drawing is square to it. Columns stand on grid lines in
    # section as in plan, and a section without bubbles cannot be read against the
    # plan it was cut from. An oblique cut is not square to any line and gets none.
    grid = standard.stroke('grid', 'cut')
    right = frame.right
    over = 1.4
    values: list[float] = []
    letters = True
    if abs(abs(right[0]) - 1.0) < 1e-6:
        values, letters = list(lattice.x_lines), True
    elif abs(abs(right[1]) - 1.0) < 1e-6:
        values, letters = list(lattice.y_lines), False
    if values:
        plate_x = [point.x for level in lattice.levels for point in level.plate]
        plate_y = [point.y for level in lattice.levels for point in level.plate]
        span = ((min(plate_x), max(plate_x)) if letters
                else (min(plate_y), max(plate_y)))
        centre = _plan_centre(lattice)
        for index, value in enumerate(values):
            if not (span[0] - 0.1 <= value <= span[1] + 0.1):
                continue
            point = ((value, centre[1], 0.0) if letters else (centre[0], value, 0.0))
            u = frame.project(point)[0]
            notes.append(Annotation('line', grid, [(u, base - 0.6), (u, v1 + over)]))
            bubble = (u, v1 + over)
            notes.append(Annotation('circle', grid, _circle(bubble, 0.55)))
            notes.append(Annotation('text', label, text=_grid_label(index, letters),
                                    anchor=(bubble[0], bubble[1] - 0.18), size_mm=2.4))

    heights = sorted({level.z for level in lattice.levels})
    _dimension_string(notes, heights, u0 - reach - 2.4, horizontal=False,
                      standard=standard, low=v0, high=v1)
    _scale_bar(notes, (u0, base - (1.5 if elevation else SECTION_EARTH_M + 0.7)),
               standard)
    del top, bearing_deg


def _circle(centre: Point2, radius: float, segments: int = 24) -> list[Point2]:
    return [(centre[0] + radius * math.cos(2 * math.pi * i / segments),
             centre[1] + radius * math.sin(2 * math.pi * i / segments))
            for i in range(segments + 1)]


def _dimension_string(notes: list[Annotation], values: list[float], offset: float,
                      *, horizontal: bool, standard: DrawingStandard,
                      low: float, high: float) -> None:
    """Running dimensions between consecutive grid lines, plus the overall.

    Drawn with real tick marks rather than arrowheads, which is the architectural
    convention and stays legible at 1:100 where an arrowhead fills in to a blob.
    """
    inside = [value for value in values if low - 0.1 <= value <= high + 0.1]
    if len(inside) < 2:
        return
    line = Stroke(Weight.FINE, Tone.NEAR)
    text = Stroke(Weight.FINE, Tone.CUT)
    tick = 0.45

    def place(along: float, across: float) -> Point2:
        return (along, across) if horizontal else (across, along)

    notes.append(Annotation('line', line,
                            [place(inside[0], offset), place(inside[-1], offset)]))
    for value in inside:
        notes.append(Annotation('line', line,
                                [place(value, offset - tick),
                                 place(value, offset + tick)]))
    for a, b in zip(inside, inside[1:]):
        mid = (a + b) / 2.0
        notes.append(Annotation(
            'text', text, text=f'{(b - a) * 1000:.0f}',
            anchor=place(mid, offset + 0.55), size_mm=2.2,
            rotate=0.0 if horizontal else -90.0))
    overall = offset - 2.0
    notes.append(Annotation('line', line,
                            [place(inside[0], overall), place(inside[-1], overall)]))
    for value in (inside[0], inside[-1]):
        notes.append(Annotation('line', line,
                                [place(value, overall - tick),
                                 place(value, overall + tick)]))
    notes.append(Annotation(
        'text', text, text=f'{(inside[-1] - inside[0]) * 1000:.0f}',
        anchor=place((inside[0] + inside[-1]) / 2.0, overall + 0.55), size_mm=2.4,
        rotate=0.0 if horizontal else -90.0))


def _scale_bar(notes: list[Annotation], anchor: Point2,
               standard: DrawingStandard) -> None:
    """A drawn bar, not a printed ratio.

    The ratio in the title block is only true if the sheet is printed at size. The bar
    is measured off the drawing itself, so it survives being scaled on a photocopier or
    dropped into a portfolio at another size -- which is what always happens.
    """
    step = 5.0 if standard.scale.denominator >= 100 else 1.0
    count = 4
    x0, y = anchor
    height = 0.55
    solid = Stroke(Weight.THIN, Tone.CUT)
    for i in range(count):
        box = [(x0 + step * i, y), (x0 + step * (i + 1), y),
               (x0 + step * (i + 1), y + height), (x0 + step * i, y + height),
               (x0 + step * i, y)]
        notes.append(Annotation('line', solid, box))
        if i % 2 == 0:
            notes.append(Annotation('fill', solid, box))
    for i in range(count + 1):
        notes.append(Annotation('text', Stroke(Weight.FINE, Tone.CUT),
                                text=f'{step * i:g}',
                                anchor=(x0 + step * i, y - 0.9), size_mm=2.2))
    notes.append(Annotation('text', Stroke(Weight.FINE, Tone.MIDDLE),
                            text=f'metres · {standard.scale.name}',
                            anchor=(x0 + step * count + 0.8, y + 0.1), size_mm=2.2,
                            align='start'))


def _north_point(notes: list[Annotation], anchor: Point2) -> None:
    x, y = anchor
    arm = 1.6
    notes.append(Annotation('line', Stroke(Weight.MEDIUM, Tone.CUT),
                            [(x, y - arm), (x, y + arm)]))
    notes.append(Annotation('line', Stroke(Weight.MEDIUM, Tone.CUT),
                            [(x - arm * 0.34, y + arm * 0.42), (x, y + arm),
                             (x + arm * 0.34, y + arm * 0.42)]))
    notes.append(Annotation('text', Stroke(Weight.FINE, Tone.CUT), text='N',
                            anchor=(x, y + arm + 0.75), size_mm=2.6, weight=600))


# --- the set --------------------------------------------------------------------

def _ring_area(ring) -> float:
    count = len(ring)
    if count < 3:
        return 0.0
    return abs(sum(ring[i].x * ring[(i + 1) % count].y
                   - ring[(i + 1) % count].x * ring[i].y
                   for i in range(count)) / 2.0)


def _stack_key(lattice: Lattice, highlight: str | None) -> KeyPlan:
    """The building as a stack of plates seen from the south, one level filled."""
    key = KeyPlan()
    ordered = sorted(lattice.levels, key=lambda level: level.z)
    for index, level in enumerate(ordered):
        xs = [point.x for point in level.plate]
        if not xs:
            continue
        top = ordered[index + 1].z if index + 1 < len(ordered) else level.z + 1.0
        ring = [(min(xs), level.z), (max(xs), level.z), (max(xs), top), (min(xs), top)]
        if level.id == highlight:
            key.highlight.append(ring)
        else:
            key.outlines.append(ring)
    if highlight:
        key.label = highlight
    return key


def _footprint_key(lattice: Lattice) -> KeyPlan:
    key = KeyPlan()
    seen: set[tuple] = set()
    for level in lattice.levels:
        ring = tuple((round(point.x, 2), round(point.y, 2)) for point in level.plate)
        if len(ring) < 3 or ring in seen:
            continue
        seen.add(ring)
        key.outlines.append(list(ring))
    return key


def _section_key(lattice: Lattice, name: str, bearing: float, offset: float) -> KeyPlan:
    key = _footprint_key(lattice)
    a, b, _along, look = _section_trace(lattice, bearing, offset, pad=1.5)
    key.traces.append([a, b])
    for end in (a, b):
        key.arrows.append((end, (end[0] + look[0] * 3.0, end[1] + look[1] * 3.0)))
    key.labels.append(((a[0] - look[0] * 2.2, a[1] - look[1] * 2.2), name))
    key.label = f'Section {name}'
    return key


def _elevation_key(lattice: Lattice, name: str, bearing: float) -> KeyPlan:
    key = _footprint_key(lattice)
    angle = math.radians(bearing)
    view = (math.sin(angle), math.cos(angle))
    along = (math.cos(angle), -math.sin(angle))
    centre = _plan_centre(lattice)
    plates = [(point.x, point.y) for level in lattice.levels for point in level.plate]
    nearest = min((x - centre[0]) * view[0] + (y - centre[1]) * view[1]
                  for x, y in plates)
    half = max(abs((x - centre[0]) * along[0] + (y - centre[1]) * along[1])
               for x, y in plates)
    stand = nearest - ELEVATION_STANDOFF_M
    mid = (centre[0] + view[0] * stand, centre[1] + view[1] * stand)
    key.traces.append([(mid[0] - along[0] * half, mid[1] - along[1] * half),
                       (mid[0] + along[0] * half, mid[1] + along[1] * half)])
    key.arrows.append(((mid[0] - view[0] * 3.0, mid[1] - view[1] * 3.0),
                       (mid[0] + view[0] * 1.5, mid[1] + view[1] * 1.5)))
    key.label = f'{name} elevation'
    return key




# --- sheets ---------------------------------------------------------------------

@dataclass
class Placement:
    drawing: Drawing
    x: float      # paper mm, top-left of the drawing's content
    y: float


@dataclass
class Sheet:
    """One piece of paper: one or more drawings of a kind, each under its own caption.

    A drawing is a cut; a sheet is what is pinned up. The two are different objects
    because their sizes are decided differently -- a drawing by its content, a sheet
    by the set -- and because a sheet with two sections on it is how sections are
    actually issued. Every drawing keeps its own scale bar and its own audit; the
    sheet adds a caption under each and a title block for all of them.
    """

    number: str
    kind: str
    placements: list[Placement]
    spec: SheetSpec

    @property
    def id(self) -> str:
        return self.number

    @property
    def drawings(self) -> list[Drawing]:
        return [placement.drawing for placement in self.placements]

    @property
    def title(self) -> str:
        titles = [drawing.title for drawing in self.drawings]
        if len(titles) == 1:
            return titles[0]
        if self.kind == 'plan':
            return 'Floor plans — ' + ', '.join(
                title.split('— ', 1)[-1] for title in titles)
        if self.kind == 'elevation':
            return ' and '.join(title.split(' ')[0] for title in titles) + ' elevations'
        return 'Sections ' + ' and '.join(title.split(' ', 1)[-1] for title in titles)

    @property
    def subtitle(self) -> str:
        if len(self.placements) == 1:
            return self.drawings[0].subtitle
        return (f'{len(self.placements)} drawings on this sheet, each with its own '
                f'caption, scale bar and audit · '
                + ' · '.join(drawing.id for drawing in self.drawings))

    @property
    def marks(self) -> int:
        return sum(drawing.audit.marks for drawing in self.drawings)

    def to_svg(self) -> str:
        width, height = self.spec.paper_mm
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.2f}mm" '
            f'height="{height:.2f}mm" viewBox="0 0 {width:.3f} {height:.3f}">',
            f'<rect width="{width:.3f}" height="{height:.3f}" fill="{PAPER_WHITE}"/>',
            earth_pattern_defs(),
        ]
        for placement in self.placements:
            drawing = placement.drawing
            parts.append(f'<g id="{_escape(drawing.id)}">')
            parts.append(drawing.body_svg((placement.x, placement.y)))
            parts.append(self._caption(placement))
            parts.append('</g>')
        parts.append(frame_and_title(
            self.spec, title=self.title, subtitle=self.subtitle,
            drawing_id=' · '.join(drawing.id for drawing in self.drawings),
            scale_name=self.drawings[0].standard.scale.name, kind=self.kind))
        parts.append('</svg>')
        return '\n'.join(parts)

    def _caption(self, placement: Placement) -> str:
        """The drawing's name under it, the way a view is titled on a composed sheet:
        a rule, the title in capitals, the scale and the cut in a line beneath."""
        drawing = placement.drawing
        content_w, content_h = drawing.content_mm
        top = placement.y + content_h + 4.0
        rule = Stroke(Weight.MEDIUM, Tone.CUT)
        parts = [f'<g font-family="{FONT}">',
                 sheet_line(placement.x, top, placement.x + content_w, top, rule),
                 sheet_text(placement.x, top + 5.2, 3.6, drawing.title.upper(),
                            weight=700, spacing=0.4),
                 sheet_text(placement.x, top + 9.2, 2.2,
                            f'{drawing.standard.scale.name} · {drawing.id} · '
                            f'{drawing.subtitle}', colour=INK_SOFT),
                 '</g>']
        return '\n'.join(parts)


def _pack(drawings: list[Drawing], area: tuple[float, float, float, float]
          ) -> list[list[Placement]]:
    """Lay drawings of one kind onto sheets, in order, as rows of a shelf.

    Greedy and stable: a drawing joins the current row if it fits beside the last,
    starts a new row if the row would still fit under the ones above, and otherwise
    starts a new sheet. Order is preserved because a set is read in order -- level
    by level, face by face -- and a packer that reorders to save paper produces a set
    nobody can find their way through. Rows are centred as a block on the sheet.
    """
    area_x, area_y, area_w, area_h = area
    sheets: list[list[list[tuple[Drawing, float, float]]]] = []   # sheet -> rows
    rows: list[list[tuple[Drawing, float, float]]] = []
    row: list[tuple[Drawing, float, float]] = []
    row_w = row_h = used_h = 0.0

    def close_row() -> None:
        nonlocal rows, row, row_w, row_h, used_h
        if row:
            rows.append(row)
            used_h += row_h + SHEET_GUTTER_MM
        row, row_w, row_h = [], 0.0, 0.0

    def close_sheet() -> None:
        nonlocal rows, used_h
        close_row()
        if rows:
            sheets.append(rows)
        rows, used_h = [], 0.0

    for drawing in drawings:
        w, h = drawing.content_mm
        h_total = h + CAPTION_MM
        fits_in_row = (row and row_w + SHEET_GUTTER_MM + w <= area_w
                       and used_h + max(row_h, h_total) <= area_h)
        fits_new_row = (not row or used_h + row_h + SHEET_GUTTER_MM + h_total <= area_h)
        if fits_in_row:
            row.append((drawing, w, h_total))
            row_w += SHEET_GUTTER_MM + w
            row_h = max(row_h, h_total)
            continue
        if row and not fits_new_row:
            close_sheet()
        elif row:
            close_row()
        if rows and used_h + h_total > area_h:
            close_sheet()
        row = [(drawing, w, h_total)]
        row_w, row_h = w, h_total
    close_sheet()

    laid: list[list[Placement]] = []
    for rows in sheets:
        block_h = sum(max(h for _, _, h in row) for row in rows) \
            + SHEET_GUTTER_MM * (len(rows) - 1)
        y = area_y + max(0.0, (area_h - block_h) / 2.0)
        placements: list[Placement] = []
        for row in rows:
            row_w = sum(w for _, w, _ in row) + SHEET_GUTTER_MM * (len(row) - 1)
            row_h = max(h for _, _, h in row)
            x = area_x + max(0.0, (area_w - row_w) / 2.0)
            for drawing, w, h in row:
                # Bottom-aligned within the row, so the captions sit on one line.
                placements.append(Placement(drawing, x, y + (row_h - h)))
                x += w + SHEET_GUTTER_MM
            y += row_h + SHEET_GUTTER_MM
        laid.append(placements)
    return laid


def _merge_keys(keys: list[KeyPlan]) -> KeyPlan:
    merged = KeyPlan()
    seen: set[tuple] = set()
    for key in keys:
        for ring in key.outlines:
            token = tuple(ring)
            if token not in seen:
                seen.add(token)
                merged.outlines.append(ring)
        merged.highlight.extend(key.highlight)
        merged.traces.extend(key.traces)
        merged.arrows.extend(key.arrows)
        merged.labels.extend(key.labels)
    merged.label = ' · '.join(key.label for key in keys if key.label)
    return merged


@dataclass
class DrawingSet:
    """Every drawing issued for one model, and what they collectively cover."""

    model_id: str
    plans: list[Drawing]
    sections: list[Drawing]
    elevations: list[Drawing] = field(default_factory=list)
    section_cuts: tuple[tuple[str, float, float], ...] = ()
    elevation_faces: tuple[tuple[str, float], ...] = ()
    identity: SetIdentity | None = None
    paper: str | None = None
    cover: str | None = None
    sheets: list[Sheet] = field(default_factory=list)

    @property
    def all(self) -> list[Drawing]:
        """The cut drawings, in issue order: plans, then elevations, then sections."""
        return self.plans + self.elevations + self.sections

    def lay_out(self, model) -> None:
        """Put the set on paper: one size, numbered sheets, key plans, a cover.

        Done once for the whole set rather than per drawing because the paper is a
        property of the set -- the largest drawing chooses it -- and because the cover
        needs every other sheet's number before it can list them.
        """
        lattice: Lattice = model.lattice
        self.identity = SetIdentity(
            model_id=model.model_id, score_id=getattr(model, 'score_id', ''),
            typology=getattr(model, 'typology', ''),
            massing_id=getattr(lattice, 'massing_id', ''),
            structural_system_id=getattr(model, 'structural_system_id', ''),
            facade_grammar_id=getattr(model, 'facade_grammar_id', ''),
            envelope_tectonic_id=getattr(model, 'envelope_tectonic_id', ''),
            compiler_version=COMPILER_VERSION)
        self.paper = paper_for([drawing.content_mm for drawing in self.all])
        if self.paper is None:
            # Nothing standard holds the largest drawing at this scale. Each sheet
            # keeps its own size and the manifest says so; cropping would lose marks.
            for drawing in self.all:
                drawing.sheet = None
            self.sheets = []
            self.cover = None
            return
        area = drawing_area(self.paper)
        # Captions need paper under the drawing; the area is reduced by one caption
        # so a single drawing centred on a sheet still has room for its own.
        keyed: dict[str, KeyPlan] = {}
        for drawing in self.plans:
            keyed[drawing.id] = _stack_key(lattice, drawing.id.rsplit('-', 1)[-1])
        for index, drawing in enumerate(self.elevations):
            name, bearing = self.elevation_faces[index]
            keyed[drawing.id] = _elevation_key(lattice, name, bearing)
        for index, drawing in enumerate(self.sections):
            name, bearing, offset = self.section_cuts[index]
            keyed[drawing.id] = _section_key(lattice, name, bearing, offset)

        self.sheets = []
        for kind, drawings, series in (('plan', self.plans, 1),
                                       ('elevation', self.elevations, 2),
                                       ('section', self.sections, 3)):
            for index, placements in enumerate(_pack(drawings, area)):
                number = f'A-{series}{index + 1:02d}'
                key = _merge_keys([keyed[p.drawing.id] for p in placements])
                spec = SheetSpec(paper=self.paper, number=number,
                                 identity=self.identity, key_plan=key)
                for placement in placements:
                    placement.drawing.sheet = spec
                self.sheets.append(Sheet(number=number, kind=kind,
                                         placements=placements, spec=spec))
        total = len(self.sheets) + 1
        for position, sheet in enumerate(self.sheets):
            sheet.spec = replace(sheet.spec, sequence=f'Sheet {position + 2} of {total}')
            for placement in sheet.placements:
                placement.drawing.sheet = sheet.spec
        self.cover = cover_svg(
            SheetSpec(paper=self.paper, number='A-000', identity=self.identity,
                      key_plan=_stack_key(lattice, None),
                      sequence=f'Sheet 1 of {total}'),
            self._cover_facts(model),
            miniatures=self._miniatures())

    def _miniatures(self) -> str:
        """Every drawing again at 1:400, laid out in issue order under the list.

        The cover's job is to let a reader see the whole set before opening any
        sheet. The marks are the same marks; the smaller scale applies its own
        detail level, so the miniatures carry structure, enclosure and circulation
        and shed the furniture the way a 1:400 drawing would.
        """
        if self.paper is None:
            return ''
        from .drawing_sheet import cover_miniature_area
        area_x, area_y, area_w, area_h = cover_miniature_area(self.paper)
        denominator = 400
        factor = self.all[0].standard.scale.denominator / denominator if self.all else 1.0
        gutter, caption = 8.0, 7.0
        parts = [f'<g font-family="{FONT}">']
        x = area_x
        y = area_y
        row_h = 0.0
        label = Stroke(Weight.THIN, Tone.CUT)
        for drawing in self.all:
            w, h = drawing.content_mm
            w, h = w * factor, h * factor
            if x > area_x and x + w > area_x + area_w:
                x = area_x
                y += row_h + gutter
                row_h = 0.0
            if y + h + caption > area_y + area_h:
                break
            parts.append(drawing.body_svg((x, y), denominator=denominator,
                                          annotations=False))
            number = drawing.sheet.number if drawing.sheet else ''
            parts.append(sheet_line(x, y + h + 1.5, x + w, y + h + 1.5, label))
            parts.append(sheet_text(x, y + h + 4.6, 2.2,
                                    f'{number} · {drawing.title}', weight=600))
            x += w + gutter
            row_h = max(row_h, h + caption)
        parts.append('</g>')
        return '\n'.join(parts)

    def _cover_facts(self, model) -> CoverFacts:
        lattice: Lattice = model.lattice
        levels = [(level.id, level.kind, level.z, _ring_area(level.plate))
                  for level in lattice.levels]
        heights = [level.z for level in lattice.levels]
        footprint = _footprint_key(lattice)
        for index, drawing in enumerate(self.sections):
            name, bearing, offset = self.section_cuts[index]
            a, b, _along, look = _section_trace(lattice, bearing, offset, pad=1.5)
            footprint.traces.append([a, b])
            footprint.labels.append(((a[0] - look[0] * 2.2, a[1] - look[1] * 2.2), name))
            footprint.labels.append(((b[0] - look[0] * 2.2, b[1] - look[1] * 2.2), name))
        for index, drawing in enumerate(self.elevations):
            name, bearing = self.elevation_faces[index]
            elevation_key = _elevation_key(lattice, name, bearing)
            footprint.traces.extend(elevation_key.traces)
            footprint.arrows.extend(elevation_key.arrows)
        return CoverFacts(
            levels=levels,
            height_m=max(heights) - min(heights),
            footprint_m2=max((area for _, _, _, area in levels), default=0.0),
            gross_floor_m2=sum(area for _, kind, _, area in levels if kind != 'roof'),
            element_total=sum(len(group.instances) for group in model.element_groups),
            account=self.element_coverage(model),
            sheets=self._sheet_rows(),
            stack=_stack_key(lattice, None),
            footprint=footprint,
            limitation=self.limitation)

    @property
    def limitation(self) -> str:
        faces = len(self.elevations)
        return (
            f'Plans, {faces} elevations and {len(self.sections)} sections, all cut or '
            'projected from one model. Drawn means the element produced at least one '
            'mark on some sheet; an element wholly overpainted by nearer work is still '
            'drawn. On no cut is what no plane reached and no face showed.')

    def element_coverage(self, model) -> dict[str, int]:
        """Every element accounted for: drawn, dropped by scale, or on no cut.

        The loop closes here, and it closes as three numbers rather than one. A bare
        percentage would call a 1:200 plan incomplete for leaving out the chairs, which
        is not a gap but the convention working -- a plan at that scale carrying every
        seat is a grey field, not a more informative drawing. What must not happen is an
        element in none of the three buckets, so the buckets are counted and made to sum.
        """
        shown = {mark.element_id for drawing in self.all for mark in drawing.marks}
        dropped: set[str] = set()
        for group in model.element_groups:
            if all(group.kind in drawing.audit.omitted_by_scale
                   for drawing in self.all):
                dropped |= {instance.id for instance in group.instances}
        dropped -= shown
        total = sum(len(group.instances) for group in model.element_groups)
        return {'drawn': len(shown), 'omitted_by_scale': len(dropped),
                'on_no_cut': total - len(shown) - len(dropped), 'total': total}

    @staticmethod
    def _drawing_row(drawing: Drawing) -> dict:
        return {
            'id': drawing.id,
            'title': drawing.title,
            'kind': drawing.kind,
            'scale': drawing.standard.scale.name,
            'subtitle': drawing.subtitle,
            'content_mm': [round(value, 1) for value in drawing.content_mm],
            'marks': drawing.audit.marks,
            'elements_cut': drawing.audit.elements_cut,
            'elements_drawn': drawing.audit.elements_drawn,
            'omitted_by_scale': drawing.audit.omitted_by_scale,
        }

    def _sheet_rows(self) -> list[dict]:
        """One row per issued sheet, each carrying the drawings placed on it.

        When no standard paper holds the set every drawing is its own sheet at its
        own size, so the rows are then one per drawing and say `custom`.
        """
        rows: list[dict] = []
        if self.paper is not None and self.identity is not None:
            paper_mm = list(SheetSpec(paper=self.paper, number='A-000',
                                      identity=self.identity).paper_mm)
            rows.append({
                'id': 'A-000', 'sheet_number': 'A-000', 'kind': 'cover',
                'title': 'Cover and drawing list', 'scale': '—',
                'subtitle': 'Drawing list, building facts, key plans, the set at 1:400',
                'paper': self.paper,
                'sheet_mm': [round(value, 1) for value in paper_mm],
                'content_mm': [round(value, 1) for value in paper_mm],
                'marks': 0, 'elements_cut': 0, 'elements_drawn': 0,
                'omitted_by_scale': {}, 'drawings': [],
            })
            for sheet in self.sheets:
                drawings = sheet.drawings
                rows.append({
                    'id': sheet.id, 'sheet_number': sheet.number, 'kind': sheet.kind,
                    'title': sheet.title, 'scale': drawings[0].standard.scale.name,
                    'subtitle': sheet.subtitle, 'paper': self.paper,
                    'sheet_mm': [round(value, 1) for value in sheet.spec.paper_mm],
                    'content_mm': [round(value, 1) for value in sheet.spec.paper_mm],
                    'marks': sheet.marks,
                    'elements_cut': sum(d.audit.elements_cut for d in drawings),
                    'elements_drawn': sum(d.audit.elements_drawn for d in drawings),
                    'omitted_by_scale': drawings[0].audit.omitted_by_scale,
                    'drawings': [self._drawing_row(d) for d in drawings],
                })
            return rows
        for drawing in self.all:
            row = self._drawing_row(drawing)
            row.update({'sheet_number': '', 'paper': 'custom',
                        'sheet_mm': row['content_mm'], 'drawings': [self._drawing_row(drawing)]})
            rows.append(row)
        return rows

    def manifest(self, model) -> dict:
        """What the set claims, in a form that outlives the objects.

        Written next to the sheets so the two cannot drift: the sheet count, what each
        one cut, and the three-bucket account of every element in the model. A drawing
        set with no record of what it left out is a set nobody can check.
        """
        account = self.element_coverage(model)
        return {
            'schema_version': 'mta.drawings/1.1',
            'model_id': self.model_id,
            'paper': self.paper or 'custom',
            'sheets': self._sheet_rows(),
            'element_account': account,
            'accounted_for': (account['drawn'] + account['omitted_by_scale']
                              + account['on_no_cut']) == account['total'],
            'limitation': self.limitation,
        }


def issue_drawings(model, *, sections: tuple[tuple[str, float, float], ...] = (
        ('A', 90.0, 0.0), ('B', 0.0, 0.0)),
        elevations: tuple[tuple[str, float], ...] = ELEVATION_FACES,
        allow_cutaway: bool = False) -> DrawingSet:
    """The standard issue: every floor plan, four elevations, and a section per entry
    in `sections`, laid out on one paper size with a cover.

    Each section is `(name, bearing, offset)`. The default pair is a long and a cross
    section through the centre, which is the minimum a plan set needs to be read in
    three dimensions; any other bearing works the same way. Each elevation is
    `(face, bearing)`.
    """
    if model.lattice.cutaway and not allow_cutaway:
        raise ValueError('A diagnostic cutaway is not a complete building model. '
                         'Compile with cutaway=False before issuing architectural drawings; '
                         'allow_cutaway=True is for explicitly labelled diagnostics only.')
    # Where each section is actually taken: the requested offset, stepped off any
    # wall it would lie inside. Resolved before the plans are drawn so the section
    # marks on the plans and the sections themselves agree.
    resolved = tuple((name, bearing, resolve_section_offset(model, bearing, offset))
                     for name, bearing, offset in sections)
    issued = DrawingSet(
        model_id=model.model_id,
        plans=floor_plans(model, section_marks=resolved),
        elevations=[building_elevation(model, bearing, name=name)
                    for name, bearing in elevations],
        sections=[building_section(model, bearing, offset_m=offset, name=name,
                                   requested_offset_m=requested)
                  for (name, bearing, offset), (_, _, requested)
                  in zip(resolved, sections)],
        section_cuts=resolved, elevation_faces=tuple(elevations))
    if model.lattice.cutaway:
        for drawing in issued.all:
            drawing.subtitle = 'DIAGNOSTIC CUTAWAY — NOT A COMPLETE BUILDING · ' + drawing.subtitle
    issued.lay_out(model)
    return issued


# The set is written where the other per-run artifacts go, one SVG per sheet plus an
# index that carries the audit. The index is the part worth keeping: it is the record
# of what the drawings claim to show, next to the drawings that show it.
DRAWING_DIRECTORY = pathlib.Path(__file__).resolve().parents[2] / 'artifacts' / 'drawings'


def write_drawing_set(issued: 'DrawingSet', model,
                      directory: pathlib.Path | None = None) -> pathlib.Path:
    """Write every sheet and the index beside them. Returns the directory."""
    target = (directory or DRAWING_DIRECTORY) / model.model_id
    target.mkdir(parents=True, exist_ok=True)
    # The directory belongs to exactly this model identity, so anything in it that
    # this issue did not produce is a leftover from an older issue of the same
    # identity -- and a stale sheet beside a fresh index is a drawing set that lies
    # about its own contents: the script counted ten sheets while the payload carried
    # nine.
    if issued.sheets:
        files = {'A-000.svg': issued.cover or ''}
        files.update({f'{sheet.id}.svg': sheet.to_svg() for sheet in issued.sheets})
    else:
        files = {f'{drawing.id}.svg': drawing.to_svg() for drawing in issued.all}
    for stale in target.glob('*.svg'):
        if stale.name not in files:
            stale.unlink()
    for name, svg in files.items():
        (target / name).write_text(svg, encoding='utf-8')
    (target / 'index.json').write_text(
        json.dumps(issued.manifest(model), indent=2), encoding='utf-8')
    return target
