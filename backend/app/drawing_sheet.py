"""The sheet around the drawing: paper, frame, title block, key plan, cover.

A drawing and a sheet are different things. The drawing is the cut -- everything in
`drawings.py` -- and it is complete without a border. The sheet is what the drawing is
issued on: a standard piece of paper, a frame, a strip along the bottom that says what
the drawing is, which set it belongs to, and where in the building it was taken. A set
that is pinned up is read as a set before any one sheet is read, so the sheet is what
makes ten drawings one document.

Three rules, each of which is a convention rather than a preference:

**One paper size for the whole set.** The largest drawing chooses the size and every
other sheet takes it, centred. A set in mixed formats cannot be pinned in a row, cannot
be bound, and reads as ten separate exhibits. A roof plan floating on A0 is a small
price; it is also what an issued set actually looks like.

**Nothing in the title block is authored.** Every string is read off the model: the
typology, the massing family, the structural system, the grammar, the model identity,
the compiler version. There is no date, because the sheet is a pure function of the
model and a date would make two identical issues differ. There is no author line for
the same reason.

**The key plan is drawn from the lattice.** A plan sheet carries a stack diagram with
its own level filled in; a section carries the footprint with the cut line across it;
an elevation carries the footprint with the face it looks at marked. A reader holding
one sheet can find it in the building without the index.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re

from .drawing_standard import LineType, Stroke, Tone, Weight

Point2 = tuple[float, float]

# ISO 216 A-series, landscape, in millimetres. Smallest first: the fit walks up.
PAPER_MM: dict[str, tuple[float, float]] = {
    'A3': (420.0, 297.0),
    'A2': (594.0, 420.0),
    'A1': (841.0, 594.0),
    'A0': (1189.0, 841.0),
}
PAPER_ORDER = ['A3', 'A2', 'A1', 'A0']

FRAME_MM = 12.0          # border inset from the paper edge, all four sides
TITLE_STRIP_MM = 34.0    # the strip along the bottom, inside the frame
GUTTER_MM = 10.0         # clear paper between the drawing and the frame or the strip

FONT = "'Helvetica Neue', Helvetica, Arial, sans-serif"
INK = '#000000'
INK_SOFT = '#4a4a4a'
INK_FAINT = '#8a8a8a'


def humanise(identifier: str) -> str:
    """`STR-SYS-STEEL-FRAME` -> `Steel frame`. The id survives elsewhere on the sheet."""
    stripped = re.sub(r'^(MAS|STR-SYS|FCD-\d+|ENV|FRM)-', '', identifier or '')
    words = stripped.replace('-', ' ').replace('_', ' ').strip().lower()
    return words[:1].upper() + words[1:] if words else ''


@dataclass(frozen=True)
class SetIdentity:
    """What every sheet in the set says about the building it belongs to."""

    model_id: str
    score_id: str
    typology: str
    massing_id: str
    structural_system_id: str
    facade_grammar_id: str
    envelope_tectonic_id: str
    compiler_version: str
    project: str = 'Music to Architecture'
    subtitle: str = 'Design-intent compiler · sheets issued from the compiled model'

    @property
    def building_line(self) -> str:
        return ' · '.join(part for part in (
            humanise(self.typology), humanise(self.massing_id),
            humanise(self.structural_system_id), humanise(self.facade_grammar_id),
        ) if part)


@dataclass
class KeyPlan:
    """A thumbnail's worth of geometry, in model metres. Rendered to fit its cell."""

    outlines: list[list[Point2]] = field(default_factory=list)   # faint context
    highlight: list[list[Point2]] = field(default_factory=list)  # filled
    traces: list[list[Point2]] = field(default_factory=list)     # cuts, heavy dashed
    arrows: list[tuple[Point2, Point2]] = field(default_factory=list)  # (tail, head)
    labels: list[tuple[Point2, str]] = field(default_factory=list)
    label: str = ''

    def bounds(self) -> tuple[float, float, float, float] | None:
        points = [p for ring in self.outlines + self.highlight for p in ring]
        for trace in self.traces:
            points += trace
        for tail, head in self.arrows:
            points += [tail, head]
        for anchor, _ in self.labels:
            points.append(anchor)
        if not points:
            return None
        return (min(p[0] for p in points), min(p[1] for p in points),
                max(p[0] for p in points), max(p[1] for p in points))


@dataclass(frozen=True)
class SheetSpec:
    """How one drawing is issued: on which paper, under which number, in which set."""

    paper: str
    number: str
    identity: SetIdentity
    key_plan: KeyPlan | None = None
    sequence: str = ''       # 'Sheet 3 of 13'

    @property
    def paper_mm(self) -> tuple[float, float]:
        return PAPER_MM[self.paper]


def drawing_area(paper: str) -> tuple[float, float, float, float]:
    """(x, y, width, height) of the region a drawing may occupy, in paper mm."""
    width, height = PAPER_MM[paper]
    x = FRAME_MM + GUTTER_MM
    y = FRAME_MM + GUTTER_MM
    return (x, y,
            width - 2 * (FRAME_MM + GUTTER_MM),
            height - 2 * (FRAME_MM + GUTTER_MM) - TITLE_STRIP_MM)


def paper_for(contents_mm: list[tuple[float, float]]) -> str | None:
    """The smallest paper on which every content rectangle fits its drawing area.

    None when even A0 is too small, in which case the caller issues that sheet at its
    own size and says so in the manifest rather than cropping a plan to fit.
    """
    for paper in PAPER_ORDER:
        _, _, width, height = drawing_area(paper)
        if all(w <= width and h <= height for w, h in contents_mm):
            return paper
    return None


# --- svg helpers ---------------------------------------------------------------------

def escape(text_value: str) -> str:
    return text_value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def text(x: float, y: float, size: float, content: str, *, anchor: str = 'start',
         colour: str = INK, weight: int | None = None, spacing: float | None = None,
         rotate: float = 0.0) -> str:
    attrs = (f'x="{x:.3f}" y="{y:.3f}" font-size="{size:g}" fill="{colour}" '
             f'text-anchor="{anchor}"')
    if weight:
        attrs += f' font-weight="{weight}"'
    if spacing:
        attrs += f' letter-spacing="{spacing:g}"'
    if rotate:
        attrs += f' transform="rotate({rotate:g} {x:.3f} {y:.3f})"'
    return f'<text {attrs}>{escape(content)}</text>'


def line(x1: float, y1: float, x2: float, y2: float, stroke: Stroke) -> str:
    dash = stroke.line_type.dasharray()
    attrs = (f'x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" '
             f'stroke="{stroke.colour}" stroke-width="{stroke.weight.value:g}"')
    if dash:
        attrs += f' stroke-dasharray="{dash}"'
    return f'<line {attrs}/>'


def path(points: list[Point2], stroke: Stroke | None, *, closed: bool = False,
         fill: str = 'none') -> str:
    if len(points) < 2:
        return ''
    body = ' L '.join(f'{x:.3f} {y:.3f}' for x, y in points[1:])
    d = f'M {points[0][0]:.3f} {points[0][1]:.3f} L {body}' + (' Z' if closed else '')
    if stroke is None:
        return f'<path d="{d}" fill="{fill}" stroke="none"/>'
    dash = stroke.line_type.dasharray()
    attrs = (f'd="{d}" fill="{fill}" stroke="{stroke.colour}" '
             f'stroke-width="{stroke.weight.value:g}"')
    if dash:
        attrs += f' stroke-dasharray="{dash}"'
    return f'<path {attrs}/>'


def earth_pattern_defs() -> str:
    """The one hatch the set uses. Hairline diagonals at a spacing that stays open at
    1:100 and closes to a tone at 1:500, which is how earth hatch is meant to behave."""
    spacing = 1.8
    weight = Weight.HAIRLINE.value
    return (
        f'<defs><pattern id="earth" patternUnits="userSpaceOnUse" '
        f'width="{spacing:g}" height="{spacing:g}" patternTransform="rotate(45)">'
        f'<line x1="0" y1="0" x2="0" y2="{spacing:g}" stroke="{INK}" '
        f'stroke-width="{weight:g}"/></pattern></defs>'
    )


# --- the frame and the title block ---------------------------------------------------

_CELLS = ((0.0, 0.22), (0.22, 0.50), (0.50, 0.62), (0.62, 0.745), (0.745, 0.86),
          (0.86, 1.0))


def frame_and_title(spec: SheetSpec, *, title: str, subtitle: str, drawing_id: str,
                    scale_name: str, kind: str) -> str:
    width, height = spec.paper_mm
    border = Stroke(Weight.MEDIUM, Tone.CUT)
    rule = Stroke(Weight.THIN, Tone.CUT)
    left, right = FRAME_MM, width - FRAME_MM
    bottom = height - FRAME_MM
    top = bottom - TITLE_STRIP_MM
    inner = right - left
    parts = [f'<g font-family="{FONT}">',
             f'<rect x="{left:.3f}" y="{FRAME_MM:.3f}" width="{inner:.3f}" '
             f'height="{height - 2 * FRAME_MM:.3f}" fill="none" '
             f'stroke="{border.colour}" stroke-width="{border.weight.value:g}"/>',
             line(left, top, right, top, border)]
    cells = [(left + inner * a, left + inner * b) for a, b in _CELLS]
    for x0, _ in cells[1:]:
        parts.append(line(x0, top, x0, bottom, rule))
    pad = 4.0
    base = top + pad
    identity = spec.identity

    # 1 -- project and building
    x0, x1 = cells[0]
    parts.append(text(x0 + pad, base + 5.0, 4.4, identity.project.upper(),
                      weight=700, spacing=0.5))
    parts.append(text(x0 + pad, base + 10.2, 2.2, identity.subtitle, colour=INK_SOFT))
    parts.append(text(x0 + pad, base + 17.4, 2.8, identity.building_line))
    parts.append(text(x0 + pad, base + 22.6, 2.0,
                      f'{identity.typology} · {identity.massing_id} · '
                      f'{identity.structural_system_id} · {identity.facade_grammar_id}',
                      colour=INK_FAINT))
    parts.append(text(x0 + pad, base + 26.2, 2.0,
                      f'envelope {identity.envelope_tectonic_id}', colour=INK_FAINT))

    # 2 -- this sheet
    x0, x1 = cells[1]
    parts.append(text(x0 + pad, base + 6.2, 5.2, title, weight=600))
    limit = int((x1 - x0 - 2 * pad) / 1.15)
    for index, chunk in enumerate(_wrap(subtitle, max_chars=limit)):
        parts.append(text(x0 + pad, base + 12.4 + index * 3.4, 2.3, chunk,
                          colour=INK_SOFT))
    parts.append(text(x0 + pad, base + 26.2, 2.0,
                      f'{kind} · drawing {drawing_id}', colour=INK_FAINT))

    # 3 -- key plan
    x0, x1 = cells[2]
    parts.append(text(x0 + pad, base + 2.4, 1.9, 'KEY', colour=INK_FAINT, spacing=0.4))
    if spec.key_plan is not None:
        parts.append(render_key_plan(spec.key_plan, (x0 + pad, base + 4.0,
                                                     x1 - x0 - 2 * pad,
                                                     TITLE_STRIP_MM - 2 * pad - 4.0)))

    # 4 -- scale and paper
    x0, x1 = cells[3]
    parts.append(text(x0 + pad, base + 2.4, 1.9, 'SCALE', colour=INK_FAINT, spacing=0.4))
    parts.append(text(x0 + pad, base + 10.6, 7.0, scale_name, weight=600))
    parts.append(text(x0 + pad, base + 16.4, 2.3,
                      f'{spec.paper} · {spec.paper_mm[0]:g} × {spec.paper_mm[1]:g} mm',
                      colour=INK_SOFT))
    parts.append(text(x0 + pad, base + 20.6, 2.0,
                      'measure from the bar, not the ratio', colour=INK_FAINT))
    parts.append(text(x0 + pad, base + 26.2, 2.0, spec.sequence, colour=INK_FAINT))

    # 5 -- issue
    x0, x1 = cells[4]
    parts.append(text(x0 + pad, base + 2.4, 1.9, 'ISSUE', colour=INK_FAINT, spacing=0.4))
    parts.append(text(x0 + pad, base + 7.4, 2.3, 'Issued from the model',
                      colour=INK_SOFT))
    parts.append(text(x0 + pad, base + 11.4, 2.3, identity.model_id))
    parts.append(text(x0 + pad, base + 15.4, 2.1, f'score {identity.score_id}',
                      colour=INK_SOFT))
    parts.append(text(x0 + pad, base + 19.4, 2.1,
                      f'compiler {identity.compiler_version}', colour=INK_SOFT))
    parts.append(text(x0 + pad, base + 24.6, 2.0,
                      'no date: the sheet is a function of the model',
                      colour=INK_FAINT))

    # 6 -- number
    x0, x1 = cells[5]
    parts.append(text(x1 - pad, base + 2.4, 1.9, 'SHEET', colour=INK_FAINT,
                      anchor='end', spacing=0.4))
    parts.append(text(x1 - pad, base + 16.0, 13.0, spec.number, weight=700,
                      anchor='end'))
    parts.append(text(x1 - pad, base + 22.0, 2.3, drawing_id, anchor='end',
                      colour=INK_SOFT))
    parts.append(text(x1 - pad, base + 26.2, 2.0, scale_name + ' @ ' + spec.paper,
                      anchor='end', colour=INK_FAINT))
    parts.append('</g>')
    return '\n'.join(parts)


def _wrap(sentence: str, *, max_chars: int) -> list[str]:
    words = sentence.split()
    lines: list[str] = []
    current = ''
    for word in words:
        candidate = (current + ' ' + word).strip()
        if len(candidate) > max(12, max_chars) and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:3]


def render_key_plan(key: KeyPlan, cell: tuple[float, float, float, float]) -> str:
    """Fit the thumbnail into `cell` (x, y, w, h) with its aspect kept."""
    bounds = key.bounds()
    if bounds is None:
        return ''
    cx, cy, cw, ch = cell
    bx0, by0, bx1, by1 = bounds
    span_x, span_y = max(bx1 - bx0, 1e-6), max(by1 - by0, 1e-6)
    factor = min((cw - 2.0) / span_x, (ch - 2.0) / span_y)
    ox = cx + (cw - span_x * factor) / 2.0
    oy = cy + (ch - span_y * factor) / 2.0

    def to_cell(point: Point2) -> Point2:
        return (ox + (point[0] - bx0) * factor, oy + (by1 - point[1]) * factor)

    faint = Stroke(Weight.THIN, Tone.MIDDLE)
    heavy = Stroke(Weight.MEDIUM, Tone.CUT, LineType.LONG_DASH)
    arrow = Stroke(Weight.THIN, Tone.CUT)
    parts = ['<g>']
    for ring in key.outlines:
        parts.append(path([to_cell(p) for p in ring], faint, closed=True))
    for ring in key.highlight:
        parts.append(path([to_cell(p) for p in ring], Stroke(Weight.THIN, Tone.CUT),
                          closed=True, fill=INK))
    for trace in key.traces:
        parts.append(path([to_cell(p) for p in trace], heavy))
    for tail, head in key.arrows:
        a, b = to_cell(tail), to_cell(head)
        parts.append(path([a, b], arrow))
        # A small open head, so the direction of view reads at thumbnail size.
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        size = 1.2
        parts.append(path([
            (b[0] - ux * size - uy * size * 0.6, b[1] - uy * size + ux * size * 0.6),
            b,
            (b[0] - ux * size + uy * size * 0.6, b[1] - uy * size - ux * size * 0.6),
        ], arrow))
    if key.label:
        parts.append(text(cx + cw - 1.0, cy + ch - 0.5, 2.2, key.label, anchor='end',
                          weight=600))
    parts.append('</g>')
    return '\n'.join(parts)


# --- the cover sheet -----------------------------------------------------------------

@dataclass
class CoverFacts:
    """What the cover says about the building. Every value is read off the model."""

    levels: list[tuple[str, str, float, float]]       # id, kind, z, plate area m²
    height_m: float
    footprint_m2: float
    gross_floor_m2: float
    element_total: int
    account: dict[str, int]
    sheets: list[dict]                                # manifest rows, in issue order
    stack: KeyPlan
    footprint: KeyPlan
    limitation: str = ''


def cover_miniature_area(paper: str) -> tuple[float, float, float, float]:
    """Where the cover lays out the set at 1:400: the lower two thirds of the sheet."""
    width, height = PAPER_MM[paper]
    x = FRAME_MM + GUTTER_MM * 1.6
    top = FRAME_MM + GUTTER_MM * 1.6 + 60.0 + 6.0 + 10 * 6.2 + 16.0 + 8.5 + 14 * 6.0 + 22.0
    return (x, top, width - 2 * x, height - top - FRAME_MM - TITLE_STRIP_MM - GUTTER_MM)


def cover_svg(spec: SheetSpec, facts: CoverFacts, *, miniatures: str = '') -> str:
    width, height = spec.paper_mm
    identity = spec.identity
    x, y = FRAME_MM + GUTTER_MM * 1.6, FRAME_MM + GUTTER_MM * 1.6
    rule = Stroke(Weight.THIN, Tone.CUT)
    hair = Stroke(Weight.HAIRLINE, Tone.MIDDLE)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.2f}mm" '
        f'height="{height:.2f}mm" viewBox="0 0 {width:.3f} {height:.3f}">',
        f'<rect width="{width:.3f}" height="{height:.3f}" fill="#ffffff"/>',
        f'<g font-family="{FONT}">',
    ]
    # Title
    parts.append(text(x, y + 16.0, 18.0, identity.project, weight=700, spacing=-0.2))
    parts.append(text(x, y + 25.0, 4.2, identity.subtitle, colour=INK_SOFT))
    parts.append(text(x, y + 38.0, 7.0, identity.building_line, weight=600))
    parts.append(text(x, y + 44.5, 2.8,
                      f'{identity.typology} · {identity.massing_id} · '
                      f'{identity.structural_system_id} · {identity.facade_grammar_id} · '
                      f'{identity.envelope_tectonic_id}', colour=INK_FAINT))
    parts.append(line(x, y + 50.0, width - FRAME_MM - GUTTER_MM * 1.6, y + 50.0, rule))

    # Facts, in two columns of label / value
    column_x = x
    row_y = y + 60.0
    facts_rows = [
        ('Model', identity.model_id),
        ('Score', identity.score_id),
        ('Compiler', identity.compiler_version),
        ('Levels', f'{len(facts.levels)} · {facts.height_m:.1f} m to roof datum'),
        ('Footprint', f'{facts.footprint_m2:,.0f} m²'),
        ('Gross floor area', f'{facts.gross_floor_m2:,.0f} m² (sum of plates)'),
        ('Elements', f'{facts.element_total:,} in the model'),
        ('Drawn', f'{facts.account.get("drawn", 0):,} on at least one sheet'),
        ('Omitted by scale', f'{facts.account.get("omitted_by_scale", 0):,}'),
        ('On no cut', f'{facts.account.get("on_no_cut", 0):,}'),
    ]
    parts.append(text(column_x, row_y, 2.4, 'BUILDING', colour=INK_FAINT, spacing=0.5))
    for index, (label, value) in enumerate(facts_rows):
        yy = row_y + 6.0 + index * 6.2
        parts.append(text(column_x, yy, 2.8, label, colour=INK_SOFT))
        parts.append(text(column_x + 44.0, yy, 3.0, value))

    # Level table
    table_x = column_x + 150.0
    parts.append(text(table_x, row_y, 2.4, 'LEVELS', colour=INK_FAINT, spacing=0.5))
    for index, (level_id, kind, z, area) in enumerate(reversed(facts.levels)):
        yy = row_y + 6.0 + index * 6.2
        parts.append(text(table_x, yy, 3.0, level_id, weight=600))
        parts.append(text(table_x + 16.0, yy, 2.8, kind, colour=INK_SOFT))
        parts.append(text(table_x + 44.0, yy, 2.8, f'FFL {z:+.3f}'))
        parts.append(text(table_x + 78.0, yy, 2.8, f'{area:,.0f} m²', anchor='end'))

    # Key diagrams: the stack and the footprint, large
    key_x = width * 0.56
    key_w = width - key_x - FRAME_MM - GUTTER_MM * 1.6
    parts.append(text(key_x, row_y, 2.4, 'STACK', colour=INK_FAINT, spacing=0.5))
    parts.append(render_key_plan(facts.stack, (key_x, row_y + 4.0, key_w, 70.0)))
    parts.append(text(key_x, row_y + 82.0, 2.4, 'FOOTPRINT · SECTION TRACES',
                      colour=INK_FAINT, spacing=0.5))
    parts.append(render_key_plan(facts.footprint, (key_x, row_y + 86.0, key_w, 110.0)))

    # Sheet list
    list_y = row_y + 6.0 + len(facts_rows) * 6.2 + 16.0
    parts.append(text(x, list_y, 2.4, 'DRAWING LIST', colour=INK_FAINT, spacing=0.5))
    parts.append(line(x, list_y + 2.5, x + 250.0, list_y + 2.5, rule))
    for index, sheet in enumerate(facts.sheets):
        yy = list_y + 8.5 + index * 6.0
        parts.append(text(x, yy, 3.0, sheet.get('sheet_number', ''), weight=600))
        parts.append(text(x + 22.0, yy, 3.0, sheet.get('title', '')))
        parts.append(text(x + 130.0, yy, 2.6, sheet.get('id', ''), colour=INK_SOFT))
        parts.append(text(x + 190.0, yy, 2.6, sheet.get('scale', ''), colour=INK_SOFT))
        marks = sheet.get('marks', 0)
        parts.append(text(x + 250.0, yy, 2.6,
                          f'{marks:,} marks' if marks else 'index', colour=INK_FAINT,
                          anchor='end'))
        parts.append(line(x, yy + 2.0, x + 250.0, yy + 2.0, hair))
    if facts.limitation:
        note_y = list_y + 8.5 + len(facts.sheets) * 6.0 + 6.0
        for index, chunk in enumerate(_wrap(facts.limitation, max_chars=120)):
            parts.append(text(x, note_y + index * 3.6, 2.3, chunk, colour=INK_SOFT))
    parts.append('</g>')
    if miniatures:
        mx, my, _mw, _mh = cover_miniature_area(spec.paper)
        parts.append(text(mx, my - 6.0, 2.4, 'THE SET AT 1:400', colour=INK_FAINT,
                          spacing=0.5))
        parts.append(earth_pattern_defs())
        parts.append(miniatures)
    parts.append(frame_and_title(spec, title='Cover and drawing list',
                                 subtitle=(f'{len(facts.sheets)} sheets issued from '
                                           f'{identity.model_id}; every sheet is a cut '
                                           f'or a projection of the same model'),
                                 drawing_id='DWG-COVER', scale_name='—', kind='cover'))
    parts.append('</svg>')
    return '\n'.join(parts)
