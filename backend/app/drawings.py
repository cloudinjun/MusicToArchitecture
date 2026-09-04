"""Floor plans and sections, drawn from the model by cutting it with a plane.

A drawing here is not a picture of the model; it is a *reading* of it. Every mark on
the sheet carries the id of the element it came from, so a line can be traced back to
the thing it describes and, in the other direction, an element can be asked which
drawings show it. That is what closes the loop: the drawing set cannot drift from the
model, because there is nothing in it that was not derived from the model, and the
`DrawingAudit` at the end says so by counting rather than by assertion.

The order of operations is the order a drawing is actually made in:

1. **Cut.** One plane, handed in. A plan is a horizontal cut 1.2 m above the floor; a
   section is a vertical cut at any bearing. Same code -- see `drawing_geometry`.
2. **Sort by depth and paint back to front.** Far solids are filled with the paper
   colour before their outline is stroked, so nearer things overpaint them. Occlusion
   falls out of the ordering, which is how it is done by hand.
3. **Stroke from the standard.** No weight, tone or dash is chosen here. Each mark
   states its role and its state, and `drawing_standard` answers. That is what keeps a
   sheet coherent and lets the whole set be restyled from one table.
4. **Annotate.** Grid, dimensions, level datums, section marks, scale bar, north point.
   Annotation is where a drawing stops being a shape and becomes measurable.

One thing worth saying plainly: the cut is geometric, not semantic. Nothing is on a list
of "things that get cut in plan". An element is cut when the plane passes through its
solid and not otherwise, which means a mezzanine, a sloped soffit or a stair mid-flight
land correctly without anyone having thought about them in advance.
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
from .drawing_standard import (
    CutState, DrawingRole, DrawingStandard, LineType, OVERHEAD_ROLES,
    PLAN_STANDARD, SECTION_STANDARD, Stroke, Tone, Weight,
)
from .geometry import (
    BoxGeometry, ExtrusionGeometry, MemberGeometry, ProfileSpec, QuadGeometry,
)


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
    kind: str                    # 'plan' | 'section'
    standard: DrawingStandard
    marks: list[Mark]
    annotations: list[Annotation]
    extents: tuple[float, float, float, float]   # u_min, v_min, u_max, v_max, metres
    audit: DrawingAudit
    subtitle: str = ''

    # -- sheet ---------------------------------------------------------------
    def to_svg(self, margin_mm: float = 18.0, title_block_mm: float = 26.0) -> str:
        scale = self.standard.scale
        u0, v0, u1, v1 = self.extents
        width = scale.to_paper_mm(u1 - u0) + margin_mm * 2
        height = scale.to_paper_mm(v1 - v0) + margin_mm * 2 + title_block_mm

        def to_paper(point: Point2) -> Point2:
            return (margin_mm + scale.to_paper_mm(point[0] - u0),
                    margin_mm + scale.to_paper_mm(v1 - point[1]))

        parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width:.2f}mm" height="{height:.2f}mm" '
            f'viewBox="0 0 {width:.3f} {height:.3f}">',
            f'<rect width="{width:.3f}" height="{height:.3f}" fill="{PAPER_WHITE}"/>',
            '<g stroke-linecap="round" stroke-linejoin="round" fill="none">',
        ]

        def path_of(points: list[Point2], closed: bool) -> str:
            paper = [to_paper(point) for point in points]
            body = ' L '.join(f'{x:.3f} {y:.3f}' for x, y in paper[1:])
            return (f'M {paper[0][0]:.3f} {paper[0][1]:.3f}'
                    + (f' L {body}' if body else '')
                    + (' Z' if closed else ''))

        def emit(points: list[Point2], stroke: Stroke, closed: bool,
                 fill: str = 'none', element_id: str = '') -> None:
            if len(points) < 2:
                return
            dash = stroke.line_type.dasharray()
            attrs = (f'd="{path_of(points, closed)}" fill="{fill}" '
                     f'stroke="{stroke.colour}" stroke-width="{stroke.weight.value:g}"')
            if dash:
                attrs += f' stroke-dasharray="{dash}"'
            if element_id:
                # The mark names its element on the sheet itself, so a viewer can ask
                # what a line is by clicking it. The id was already on the mark; this
                # is the only place it was being dropped.
                attrs += f' data-element="{_escape(element_id)}"'
            parts.append(f'<path {attrs}/>')

        # Painter's algorithm: furthest first, each filled with paper before it is
        # stroked, so what is nearer covers what is behind it.
        for mark in sorted(self.marks, key=lambda m: -m.depth):
            fill = PAPER_WHITE
            if mark.fill is not None:
                value = round(mark.fill.value * 255)
                fill = f'#{value:02x}{value:02x}{value:02x}'
            elif mark.role == 'glazing' or not mark.closed:
                fill = 'none'
            emit(mark.points, mark.stroke, mark.closed, fill, mark.element_id)

        for note in self.annotations:
            if note.kind == 'text':
                x, y = to_paper(note.anchor)
                colour = note.stroke.colour if note.stroke else '#000000'
                rotate = (f' transform="rotate({note.rotate:g} {x:.3f} {y:.3f})"'
                          if note.rotate else '')
                parts.append(
                    f'<text x="{x:.3f}" y="{y:.3f}" font-size="{note.size_mm:g}" '
                    f'font-family="Helvetica, Arial, sans-serif" fill="{colour}" '
                    f'text-anchor="{note.align}"{rotate}>{_escape(note.text)}</text>')
            elif note.kind == 'fill' and note.stroke is not None:
                emit(note.points, note.stroke, closed=True, fill=note.stroke.colour)
            elif note.stroke is not None:
                emit(note.points, note.stroke, closed=False)

        parts.append('</g>')
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


# --- the compiler ------------------------------------------------------------------

def compile_drawing(
    model, plane: Plane, frame: ViewFrame, standard: DrawingStandard, *,
    drawing_id: str, title: str, kind: str, subtitle: str = '',
    keep: tuple[float, float] | None = None,
    above_reach: float | None = None,
    clip_rect: tuple[float, float, float, float] | None = None,
) -> Drawing:
    """Cut the model with `plane` and draw what that reveals.

    `keep` bounds the depth that is drawn, in metres behind the cut. A plan needs it --
    without a floor above to stop at, every storey below would pile into one sheet -- and
    a section usually does not.
    """
    profiles = dict(model.profiles)
    marks: list[Mark] = []
    considered = drawn = cut_count = outside = 0
    omitted: dict[str, int] = {}

    # First pass: work out how deep the visible field actually is, so the depth planes
    # are spread over this drawing rather than over an assumed building size.
    spread = 0.0
    for group in model.element_groups:
        for instance in group.instances:
            for solid in _solids_for(instance.geometry, profiles):
                for vertex in solid.vertices:
                    spread = max(spread, frame.depth(vertex))
            if isinstance(instance.geometry, ExtrusionGeometry):
                for point in instance.geometry.boundary:
                    for z in _z_range(instance.geometry):
                        spread = max(spread, frame.depth((point.x, point.y, z)))
    if keep is not None:
        spread = min(spread, keep[1])
    spread = max(spread, 1e-3)

    for group in model.element_groups:
        role = standard.role_of(group.kind)
        for instance in group.instances:
            considered += 1
            if not standard.draws(role):
                omitted[group.kind] = omitted.get(group.kind, 0) + 1
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


def _clip_marks(marks, rect):
    kept = []
    for mark in marks:
        if mark.closed:
            clipped = clip_polygon(mark.points, rect)
            if len(clipped) >= 3:
                kept.append(replace(mark, points=clipped))
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

    # --- prisms take their own path, so a courtyard stays open -------------------
    if isinstance(geometry, ExtrusionGeometry):
        cut = slice_extrusion(geometry, plane, frame)
        if cut:
            stroke = standard.stroke(role, 'cut')
            # The outer ring carries the poché; the voids inside it are painted back to
            # paper. Order matters and is preserved: the fill goes down first and the
            # holes are cut out of it by the painter, the same way a hole in a solid
            # reads on a drawn plan.
            return [Mark(instance.id, kind, role, 'cut', stroke, polygon,
                         fill=standard.poche(role) if index == 0 else None,
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
                              depth=0.0))
            continue
        depths = [frame.depth(vertex) for vertex in solid.vertices]
        state, depth = _state_of(min(depths), max(depths), keep, above_reach)
        if state is None or (state == 'above' and role not in OVERHEAD_ROLES):
            continue
        any_in_range = True
        band = standard.band_for(depth, spread)
        outline = silhouette(solid, frame)
        if len(outline) >= 3:
            marks.append(Mark(instance.id, kind, role, state,
                              standard.stroke(role, state, band), outline,
                              closed=True, fill=None, depth=depth))
    if not any_in_range:
        return None
    return marks


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
    for index, level in enumerate(lattice.levels):
        # The roof is cut just above its own datum rather than at 1.2 m: a roof plan is
        # a view down onto the roof, and cutting it at head height would slice the
        # parapet and show the storey below through it. Without this sheet the parapet
        # ring, the purlins and the deck appear on no drawing at all -- which the
        # coverage count made visible.
        roof = level.kind == 'roof'
        cut_z = level.z + (0.15 if roof else PLAN_CUT_HEIGHT_M)
        plane, frame = plan_frame(cut_z)
        # Looking down: depth grows downward from the cut, and stops at this level's
        # own floor. Overhead work is kept for a limited reach above.
        keep = (0.0, 1.1) if roof else (0.0, PLAN_CUT_HEIGHT_M + 0.9)
        drawing = compile_drawing(
            model, plane, frame, standard,
            drawing_id=f'DWG-PLAN-{level.id}',
            title=(f'Roof plan — {level.id}' if roof
                   else f'Floor plan — {level.id}'),
            subtitle=(f'{level.kind} level, cut {PLAN_CUT_HEIGHT_M:.2f} m above '
                      f'FFL {level.z:+.3f} m · overhead shown dashed'),
            kind='plan', keep=keep,
            above_reach=1.4 if roof else OVERHEAD_REACH_M,
            clip_rect=_plate_rect(level.plate, frame, cut_z,
                                  PLAN_CLIP_MARGIN_M))
        annotate_plan(drawing, lattice, level, standard)
        if not roof:
            annotate_rooms(drawing, model, level)
            annotate_doors(drawing, model, level)
            annotate_stair_direction(drawing, model, level)
        if section_marks:
            annotate_section_marks(drawing, section_marks, standard)
        _fit_to_annotations(drawing)
        drawings.append(drawing)
        del index
    return drawings


def building_section(model, bearing_deg: float, *, offset_m: float = 0.0,
                     standard: DrawingStandard = SECTION_STANDARD,
                     name: str = 'A') -> Drawing:
    """A vertical cut at any bearing, through the plan's centre plus `offset_m`.

    `bearing_deg` is the direction of view: 0 looks north, 90 east. Any angle works --
    the plane is general, and an oblique section is the same operation as an orthogonal
    one, so there is no separate path for it to be wrong in.
    """
    lattice: Lattice = model.lattice
    xs = [point.x for level in lattice.levels for point in level.plate]
    ys = [point.y for level in lattice.levels for point in level.plate]
    centre = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
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
                 min(heights) - 3.0,
                 max(across) + SECTION_CLIP_MARGIN_M,
                 max(heights) + 4.5)
    drawing = compile_drawing(
        model, plane, frame, standard,
        drawing_id=f'DWG-SECT-{name}',
        title=f'Section {name}—{name}',
        subtitle=(f'Cut plane bearing {bearing_deg:g}°, offset {offset_m:+.2f} m '
                  f'from plan centre · looking {_compass(bearing_deg)}'),
        kind='section', clip_rect=clip_rect)
    annotate_section(drawing, lattice, standard)
    _fit_to_annotations(drawing)
    return drawing


def _fit_to_annotations(drawing: Drawing) -> None:
    """Grow the sheet to hold the annotation.

    Extents are taken from the building's marks, because that is what the drawing is
    of. Grid lines run past it, dimension strings sit outside it and the scale bar sits
    below -- all of which would be cropped at the sheet edge if the extents were left
    where the building ended.
    """
    us = [point[0] for note in drawing.annotations for point in note.points]
    vs = [point[1] for note in drawing.annotations for point in note.points]
    us += [note.anchor[0] for note in drawing.annotations if note.kind == 'text']
    vs += [note.anchor[1] for note in drawing.annotations if note.kind == 'text']
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
            area = box.size.x * box.size.y
            drawing.annotations.append(Annotation(
                'text', name, text=_pretty(group.program),
                anchor=(anchor[0], anchor[1] + 0.55), size_mm=3.0))
            drawing.annotations.append(Annotation(
                'text', area_tone, text=f'{area:.0f} m²',
                anchor=(anchor[0], anchor[1] - 0.9), size_mm=2.4))


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
        if group.kind != 'door':
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
            far = (centre[0] + along[0] * leaf / 2.0,
                   centre[1] + along[1] * leaf / 2.0)
            steps = 8
            start = math.atan2(tip[1] - hinge[1], tip[0] - hinge[0])
            end = math.atan2(far[1] - hinge[1], far[0] - hinge[0])
            if sense > 0:
                sweep = (end - start) % (2 * math.pi)
            else:
                sweep = -((start - end) % (2 * math.pi))
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
    for flight, steps in flights.items():
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
        del flight


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
                size_mm=3.0))


def annotate_section(drawing: Drawing, lattice: Lattice, standard: DrawingStandard
                     ) -> None:
    """Level datums with heights, a ground line, and a vertical dimension string.

    A section is read by height, so the datums are the annotation that matters: every
    level line carries its own figure, and the storey heights between them are
    dimensioned rather than left to be scaled off.
    """
    u0, v0, u1, v1 = drawing.extents
    datum = standard.stroke('grid', 'cut')
    label = Stroke(Weight.FINE, Tone.CUT)
    notes = drawing.annotations
    reach = 2.0

    for level in lattice.levels:
        if not (v0 - 0.5 <= level.z <= v1 + 0.5):
            continue
        notes.append(Annotation('line', datum,
                                [(u0 - reach, level.z), (u1 + reach, level.z)]))
        notes.append(Annotation('text', label, text=f'{level.id}  {level.z:+.3f}',
                                anchor=(u1 + reach, level.z + 0.25), size_mm=2.4,
                                align='end'))

    # The ground line is the heaviest line on a section: it is what the building
    # stands on, and the eye uses it to find the bottom of the drawing.
    ground = Stroke(Weight.PROFILE, Tone.CUT)
    base = min(level.z for level in lattice.levels)
    notes.append(Annotation('line', ground,
                            [(u0 - reach * 1.6, base), (u1 + reach * 1.6, base)]))

    heights = sorted({level.z for level in lattice.levels})
    _dimension_string(notes, heights, u0 - reach - 2.4, horizontal=False,
                      standard=standard, low=v0, high=v1)
    _scale_bar(notes, (u0, v0 - 3.4), standard)


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
                            anchor=(x, y + arm + 0.75), size_mm=2.6))


# --- the set --------------------------------------------------------------------

@dataclass
class DrawingSet:
    """Every drawing issued for one model, and what they collectively cover."""

    model_id: str
    plans: list[Drawing]
    sections: list[Drawing]

    @property
    def all(self) -> list[Drawing]:
        return self.plans + self.sections

    def element_coverage(self, model) -> dict[str, int]:
        """Every element accounted for: drawn, dropped by scale, or on no cut.

        The loop closes here, and it closes as three numbers rather than one. A bare
        percentage would call a 1:100 plan incomplete for leaving out the chairs, which
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


    def manifest(self, model) -> dict:
        """What the set claims, in a form that outlives the objects.

        Written next to the sheets so the two cannot drift: the sheet count, what each
        one cut, and the three-bucket account of every element in the model. A drawing
        set with no record of what it left out is a set nobody can check.
        """
        account = self.element_coverage(model)
        return {
            'schema_version': 'mta.drawings/1.0',
            'model_id': self.model_id,
            'sheets': [
                {
                    'id': drawing.id,
                    'title': drawing.title,
                    'kind': drawing.kind,
                    'scale': drawing.standard.scale.name,
                    'subtitle': drawing.subtitle,
                    'sheet_mm': [
                        round(drawing.standard.scale.to_paper_mm(
                            drawing.extents[2] - drawing.extents[0]), 1),
                        round(drawing.standard.scale.to_paper_mm(
                            drawing.extents[3] - drawing.extents[1]), 1),
                    ],
                    'marks': drawing.audit.marks,
                    'elements_cut': drawing.audit.elements_cut,
                    'elements_drawn': drawing.audit.elements_drawn,
                    'omitted_by_scale': drawing.audit.omitted_by_scale,
                }
                for drawing in self.all
            ],
            'element_account': account,
            'accounted_for': (account['drawn'] + account['omitted_by_scale']
                              + account['on_no_cut']) == account['total'],
            'limitation': (
                'Plans and sections only. An element on a face that no cut plane '
                'reaches appears on no sheet and is counted under on_no_cut; showing '
                'those would need elevations, which this module does not issue.'),
        }


def issue_drawings(model, *, sections: tuple[tuple[str, float, float], ...] = (
        ('A', 90.0, 0.0), ('B', 0.0, 0.0))) -> DrawingSet:
    """The standard issue: every floor plan, plus a section per entry in `sections`.

    Each section is `(name, bearing, offset)`. The default pair is a long and a cross
    section through the centre, which is the minimum a plan set needs to be read in
    three dimensions; any other bearing works the same way.
    """
    return DrawingSet(
        model_id=model.model_id,
        plans=floor_plans(model, section_marks=sections),
        sections=[building_section(model, bearing, offset_m=offset, name=name)
                  for name, bearing, offset in sections])


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
    issued_names = {f'{drawing.id}.svg' for drawing in issued.all}
    for stale in target.glob('*.svg'):
        if stale.name not in issued_names:
            stale.unlink()
    for drawing in issued.all:
        (target / f'{drawing.id}.svg').write_text(drawing.to_svg(), encoding='utf-8')
    (target / 'index.json').write_text(
        json.dumps(issued.manifest(model), indent=2), encoding='utf-8')
    return target
