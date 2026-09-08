"""The compiler's four phases as a journal figure: A1 phase band, real thumbnails.

Every slot is an artifact the run actually wrote -- two workbench crops, four Blender
views from the model's own .blend, one issued sheet, one screenshot of the workbench
reading that same run. Nothing is drawn to illustrate a stage it did not produce.

The figure carries no title, no caption and no legend; those belong to the manuscript.
Assets are written beside the SVG so the file stays editable in Illustrator or Inkscape.

    python tools/portfolio/pipeline_figure.py --run <track-dir> --out <dir>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]

FONT = "'Times New Roman','Liberation Serif','Nimbus Roman',serif"
INK = '#000'
BOX_FILL = '#595959'
ARROW = '#6b6b6b'
SLOT_STROKE = '#bfbfbf'

# One 3:2 slot geometry for every thumbnail, so no phase can look more finished than
# its neighbour by being photographed in a wider frame.
COLUMNS = 4
MARGIN = 30
GUTTER = 60
COLUMN_W = 380
SLOT_H = 253
ASSET_W, ASSET_H = 1140, 760

HEADER_BASELINE = 30
RULE_Y = 42
BOX_Y, BOX_H = 54, 32
ROW1_Y = 100
LABEL1_Y = ROW1_Y + SLOT_H + 20
ROW2_Y = LABEL1_Y + 22
LABEL2_Y = ROW2_Y + SLOT_H + 20
CANVAS_H = LABEL2_Y + 24
CANVAS_W = MARGIN * 2 + COLUMNS * COLUMN_W + (COLUMNS - 1) * GUTTER


def column_x(index: int) -> int:
    return MARGIN + index * (COLUMN_W + GUTTER)


def fit_asset(source: Path, target: Path) -> None:
    """Write a uniform 3:2 asset: cover-crop when close, letterbox when it is not.

    A render is cropped because its framing is already the subject. The score strip is
    a long ribbon; cropping it to 3:2 would throw away four of the six measures, so it
    is centred instead, and the bands it needs are visible rather than pretended away.
    """
    with Image.open(source) as image:
        image = image.convert('RGB')
        aspect = image.width / image.height
        goal = ASSET_W / ASSET_H
        # Letterbox bands take the source's own edge colour. A dark workbench crop
        # centred on white reads as a mistake; centred on its own ground it reads as
        # the panel it is.
        edge = image.crop((0, 0, max(1, image.width // 40), image.height))
        ground = edge.resize((1, 1), Image.LANCZOS).getpixel((0, 0))
        canvas = Image.new('RGB', (ASSET_W, ASSET_H), ground)
        if 0.72 <= aspect / goal <= 1.38:
            scale = max(ASSET_W / image.width, ASSET_H / image.height)
            resized = image.resize((round(image.width * scale), round(image.height * scale)),
                                   Image.LANCZOS)
            left = (resized.width - ASSET_W) // 2
            top = (resized.height - ASSET_H) // 2
            canvas = resized.crop((left, top, left + ASSET_W, top + ASSET_H))
        else:
            scale = min(ASSET_W / image.width, ASSET_H / image.height)
            resized = image.resize((max(1, round(image.width * scale)),
                                    max(1, round(image.height * scale))), Image.LANCZOS)
            canvas.paste(resized, ((ASSET_W - resized.width) // 2,
                                   (ASSET_H - resized.height) // 2))
        target.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(target, 'PNG', optimize=True)


def straight_arrow(x0: float, y: float, x1: float) -> str:
    """A shaft and an explicit triangular head.

    SVG markers do not survive every rasteriser, and an arrow that loses its head
    stops being an arrow. The head is drawn as a polygon so the figure reads the same
    in Illustrator, in a browser and in whatever the journal runs.
    """
    head = 9.0
    return (
        f'<line x1="{x0}" y1="{y}" x2="{x1 - head}" y2="{y}" stroke="{ARROW}" '
        f'stroke-width="2"/>'
        f'<polygon points="{x1},{y} {x1 - head},{y - 4.6} {x1 - head},{y + 4.6}" '
        f'fill="{ARROW}"/>'
    )


def build(phases: list[dict], out: Path) -> Path:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}" '
        f'font-family="{FONT}">',
        f'<rect width="{CANVAS_W}" height="{CANVAS_H}" fill="#ffffff"/>',
    ]
    for index, phase in enumerate(phases):
        x = column_x(index)
        parts.append(
            f'<text x="{x}" y="{HEADER_BASELINE}" font-size="17" font-weight="bold" '
            f'fill="{INK}" letter-spacing="1.2">{escape(phase["header"])}</text>')
        parts.append(
            f'<line x1="{x}" y1="{RULE_Y}" x2="{x + COLUMN_W}" y2="{RULE_Y}" '
            f'stroke="{INK}" stroke-width="1"/>')
        parts.append(
            f'<rect x="{x}" y="{BOX_Y}" width="{COLUMN_W}" height="{BOX_H}" fill="{BOX_FILL}"/>')
        parts.append(
            f'<text x="{x + COLUMN_W / 2}" y="{BOX_Y + 21}" font-size="15" fill="#ffffff" '
            f'text-anchor="middle">{escape(phase["box"])}</text>')

        for row, (top, label_y) in enumerate(((ROW1_Y, LABEL1_Y), (ROW2_Y, LABEL2_Y))):
            slot = phase['slots'][row]
            parts.append(
                f'<image x="{x}" y="{top}" width="{COLUMN_W}" height="{SLOT_H}" '
                f'preserveAspectRatio="xMidYMid slice" xlink:href="{slot["href"]}"/>')
            parts.append(
                f'<rect x="{x}" y="{top}" width="{COLUMN_W}" height="{SLOT_H}" fill="none" '
                f'stroke="{SLOT_STROKE}" stroke-width="1"/>')
            parts.append(
                f'<text x="{x}" y="{label_y}" font-size="13" fill="{INK}">'
                f'{escape(slot["label"])}</text>')

        if index < COLUMNS - 1:
            y = (ROW1_Y + LABEL2_Y) / 2
            parts.append(straight_arrow(x + COLUMN_W + 10, y, x + COLUMN_W + GUTTER - 10))

    parts.append('</svg>')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(parts), encoding='utf-8')
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--track', required=True)
    parser.add_argument('--renders', type=Path, required=True,
                        help='Directory holding hero.png / layer_*.png for the track')
    parser.add_argument('--sheets', type=Path, required=True,
                        help='Directory holding the rasterised sheet PNGs')
    parser.add_argument('--ui', type=Path, required=True,
                        help='Directory holding the workbench screenshots')
    parser.add_argument('--figure-assets', type=Path, required=True,
                        help='Directory holding score_strip.png and signature.png')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()

    response = json.loads(
        (args.batch / 'tracks' / args.track / 'response.json').read_text(encoding='utf-8'))
    model_id = response['analysis']['model_id']
    elements = response['analysis']['element_count']
    sheets = len(response.get('drawing_sheets') or [])
    geometry = args.batch / 'geometry' / model_id

    assets = args.out / 'assets'
    sources = [
        ('01_score_strip', args.figure_assets / 'score_strip.png'),
        ('02_signature', args.figure_assets / 'signature.png'),
        ('03_program_volumes', geometry / '06_program_volumes.png'),
        ('04_program_layer', args.renders / 'layer_program.png'),
        ('05_structure_layer', args.renders / 'layer_structure.png'),
        ('06_building', args.renders / 'hero.png'),
        ('07_sheet', args.sheets / 'A-301.png'),
        ('08_workbench', args.ui / '01_stage_blueprint.png'),
    ]
    missing = [str(path) for _, path in sources if not path.is_file()]
    if missing:
        raise SystemExit('Missing figure inputs:\n  ' + '\n  '.join(missing))
    for name, path in sources:
        fit_asset(path, assets / f'{name}.png')

    phases = [
        {'header': 'MEASURE', 'box': 'Twelve features, ten dimensions',
         'slots': [{'href': 'assets/01_score_strip.png',
                    'label': 'Recording read as six measures'},
                   {'href': 'assets/02_signature.png',
                    'label': 'Ten dimensions, one signature'}]},
        {'header': 'REGISTER', 'box': 'Datums, lattice, volumes',
         'slots': [{'href': 'assets/03_program_volumes.png',
                    'label': 'Full-height room volumes'},
                   {'href': 'assets/04_program_layer.png',
                    'label': 'Rooms allocated on every plate'}]},
        {'header': 'COMPILE', 'box': 'Union, plates, elements',
         'slots': [{'href': 'assets/05_structure_layer.png',
                    'label': 'Gravity frame, sized members'},
                   {'href': 'assets/06_building.png',
                    'label': f'{elements:,} elements'}]},
        {'header': 'ISSUE', 'box': 'Model, sheets, reports',
         'slots': [{'href': 'assets/07_sheet.png',
                    'label': f'{sheets} sheets, one paper size'},
                   {'href': 'assets/08_workbench.png',
                    'label': 'Every report on one model'}]},
    ]
    path = build(phases, args.out / 'pipeline.svg')
    print(f'{path}  ({CANVAS_W} x {CANVAS_H})')


if __name__ == '__main__':
    main()
