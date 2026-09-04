"""Fit a Blender Grease Pencil SVG onto a paper sheet.

Blender's Grease Pencil SVG exporter writes the drawing in scene units and states the
canvas as whatever number that produces -- two and a half million pixels across for a
building. The geometry inside is correct and proportional; only the canvas is wrong,
and only because the exporter has no idea the drawing is meant to land on A1 at 1:100.

So this reads the coordinates back, finds what the drawing actually occupies, and
restates the canvas in millimetres at the intended scale. It is packaging, not
geometry: no point moves relative to any other, which is what keeps a dimension taken
off the sheet true.

The stroke widths come back in the same units and are rescaled with everything else, so
a weight specified as 0.5 mm in `drawing_standard` arrives on the sheet at 0.5 mm.

Two limits of that exporter are worth knowing before laying a sheet up. Its canvas is
not the camera frame -- strokes run past both edges -- and its axes are not the render's,
so a section that renders landscape can be written portrait. The scale and the extent
here are exact; the orientation is the exporter's, and a sheet may want a quarter turn.
The PNG rendered alongside it is the one that matches what was composed.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


_NUMBER = re.compile(r'-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?')
_HEADER = re.compile(
    r'<svg\b[^>]*?\bwidth="(?P<w>[^"]+)"[^>]*?\bheight="(?P<h>[^"]+)"'
    r'[^>]*?\bviewBox="(?P<vb>[^"]+)"[^>]*?>', re.S)
_POINTS = re.compile(r'\b(?:d|points)="([^"]+)"')
_STROKE_WIDTH = re.compile(r'stroke-width="([^"]+)"')


@dataclass(frozen=True)
class SheetFit:
    """What the fit did, so a caller can report it rather than trust it."""

    content_mm: tuple[float, float]
    sheet_mm: tuple[float, float]
    factor: float
    paths: int


def _coordinates(body: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for match in _POINTS.finditer(body):
        numbers = [float(value) for value in _NUMBER.findall(match.group(1))]
        points.extend(zip(numbers[0::2], numbers[1::2]))
    return points


def fit_metres(svg: str, *, metres_across: float, scale_denominator: int,
               margin_mm: float = 16.0) -> tuple[str, SheetFit]:
    """Fit knowing what the camera framed, which is what makes the scale true.

    `metres_across` is the orthographic span the drawing was rendered at. Paper width
    follows from it and the scale, and every coordinate and stroke width is multiplied
    by the same factor -- so the sheet is not merely the right size, it is the right
    size *because* of the scale, and a scale bar drawn on it measures correctly.
    """
    header = _HEADER.search(svg)
    if header is None:
        raise ValueError('not a Grease Pencil SVG: no <svg> header with a viewBox')
    points = _coordinates(svg)
    if not points:
        raise ValueError('the exported sheet carries no geometry')
    view = [float(value) for value in _NUMBER.findall(header.group('vb'))]
    canvas_span = max(view[2], view[3])
    paper_mm = metres_across * 1000.0 / scale_denominator
    factor = paper_mm / canvas_span

    # Fitted to what the drawing occupies, not to the exporter's canvas.
    #
    # Neither is entirely trustworthy and it is worth saying which way. The canvas is
    # not the camera frame: one section's strokes ran 75 units off its left edge and
    # 45 past its right. And the exporter's axes are not the render's -- a cross
    # section that renders landscape comes back portrait, 78 mm by 601, because the
    # sheet is written rotated a quarter turn from the image.
    #
    # So the scale is exact and the extent is exact; the orientation is whatever the
    # exporter chose. A sheet may need a quarter turn before it is laid up, and it is
    # better to say that than to guess a rotation and be wrong on the sheets where the
    # building happens to be square.
    # Paths that never touch the camera frame are dropped first. Line Art emits some,
    # and on an oblique cut it emits a lot: fitting to them turned a 60 m section into
    # 2.9 x 4.2 metres of paper. A stroke wholly outside the view was not part of the
    # drawing, so removing it changes nothing that was composed.
    body_raw, dropped = _drop_offscreen(svg[header.end():], view[2], view[3])
    points = _coordinates(body_raw)
    if not points:
        raise ValueError('every stroke fell outside the camera frame')
    del dropped
    points_scaled = [(x * factor, y * factor) for x, y in points]
    min_x = min(x for x, _ in points_scaled)
    max_x = max(x for x, _ in points_scaled)
    min_y = min(y for _, y in points_scaled)
    max_y = max(y for _, y in points_scaled)

    body = _scale_body(body_raw, factor)
    width, height = max_x - min_x, max_y - min_y
    fitted = (
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
        f'width="{width + margin_mm * 2:.3f}mm" '
        f'height="{height + margin_mm * 2:.3f}mm" '
        f'viewBox="{min_x - margin_mm:.3f} {min_y - margin_mm:.3f} '
        f'{width + margin_mm * 2:.3f} {height + margin_mm * 2:.3f}">'
        + body)
    return fitted, SheetFit(content_mm=(width, height), sheet_mm=(width, height),
                            factor=factor, paths=len(_POINTS.findall(svg)))


def _drop_offscreen(body: str, canvas_x: float, canvas_y: float) -> tuple[str, int]:
    """Remove whole elements whose geometry lies entirely outside the frame."""
    margin_x, margin_y = canvas_x * 0.02, canvas_y * 0.02
    kept: list[str] = []
    dropped = 0
    for chunk in re.split(r'(?=<)', body):
        match = _POINTS.search(chunk)
        if match is None:
            kept.append(chunk)
            continue
        numbers = [float(value) for value in _NUMBER.findall(match.group(1))]
        xs, ys = numbers[0::2], numbers[1::2]
        if not xs or not ys:
            kept.append(chunk)
            continue
        if (max(xs) < -margin_x or min(xs) > canvas_x + margin_x
                or max(ys) < -margin_y or min(ys) > canvas_y + margin_y):
            dropped += 1
            continue
        kept.append(chunk)
    return ''.join(kept), dropped


def _scale_body(body: str, factor: float) -> str:
    def scale_points(match: re.Match) -> str:
        attribute = match.group(0)[:match.group(0).index('=')]
        scaled = _NUMBER.sub(
            lambda number: f'{float(number.group()) * factor:.4f}', match.group(1))
        return f'{attribute}="{scaled}"'

    body = _POINTS.sub(scale_points, body)
    return _STROKE_WIDTH.sub(
        lambda m: f'stroke-width="{float(m.group(1)) * factor:.4f}"', body)
