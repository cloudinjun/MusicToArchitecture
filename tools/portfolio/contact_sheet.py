"""One plate holding every building a batch produced, in the corpus's own order.

The point of the sheet is comparison, so nothing about a cell may vary except the
building: same camera solve, same lens, same light, same crop, same caption shape. A
recording that failed to compile keeps its cell and says so, because a grid of twenty
that quietly shows eighteen is a claim the batch did not earn.

    python tools/portfolio/contact_sheet.py artifacts/portfolio_plates/<batch> \
        --batch artifacts/visual_audit/<batch> --out portfolio/plate_twenty.png
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / 'docs' / 'experiments' / 'visual_music_corpus_20.json'

SERIF = 'C:/Windows/Fonts/times.ttf'
SERIF_BOLD = 'C:/Windows/Fonts/timesbd.ttf'
SERIF_ITALIC = 'C:/Windows/Fonts/timesi.ttf'

INK = (0, 0, 0)
GREY = (110, 110, 110)
RULE = (30, 30, 30)
FAINT = (205, 205, 205)
PAPER = (255, 255, 255)
MISSING = (244, 244, 244)


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def corpus_index(path: Path = CORPUS) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding='utf-8-sig'))
    auxiliary = set(payload.get('auxiliary_tracks', []))
    return {row['id']: row for row in payload['tracks'] if row['id'] not in auxiliary}


def pretty(identifier: str | None) -> str:
    """`FCD-09-CRITICAL-REGIONALISM` reads as `Critical regionalism` in a caption."""
    if not identifier:
        return '—'
    parts = [p for p in identifier.split('-') if not p.isdigit()]
    for prefix in ('FCD', 'STR', 'SYS', 'MAS'):
        if parts and parts[0] == prefix:
            parts = parts[1:]
    text = ' '.join(parts).lower()
    return text[:1].upper() + text[1:] if text else '—'


def span_of(render_dir: Path) -> str | None:
    """The building's own extents, from the render manifest that framed it."""
    manifest = render_dir / 'views_manifest.json'
    if not manifest.is_file():
        return None
    bounds = json.loads(manifest.read_text(encoding='utf-8')).get('building_bounds') or {}
    span = bounds.get('span')
    if not span or len(span) != 3:
        return None
    return ' × '.join(f'{value:.0f}' for value in span) + ' m'


def fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Cover-crop to the cell so every thumbnail has identical geometry."""
    target_w, target_h = size
    scale = max(target_w / image.width, target_h / image.height)
    resized = image.resize((max(1, round(image.width * scale)),
                            max(1, round(image.height * scale))), Image.LANCZOS)
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def wrap(draw: ImageDraw.ImageDraw, text: str, typeface, width: int) -> list[str]:
    words, lines, current = text.split(), [], ''
    for word in words:
        trial = f'{current} {word}'.strip()
        if draw.textlength(trial, font=typeface) <= width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('renders', type=Path, help='Directory of per-track render dirs')
    parser.add_argument('--batch', type=Path, required=True, help='The audit batch')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--view', default='hero')
    parser.add_argument('--columns', type=int, default=5)
    parser.add_argument('--cell-width', type=int, default=1120)
    parser.add_argument('--title', default='Twenty recordings, twenty buildings')
    parser.add_argument('--subtitle', default='')
    parser.add_argument('--footnote', default='')
    parser.add_argument('--corpus', type=Path, default=CORPUS,
                        help='Manifest naming the recordings this plate shows')
    args = parser.parse_args()

    # The manifest defines the plate. A batch may hold more runs than the plate shows --
    # earlier attempts, replaced recordings -- and rendering whatever the batch happens
    # to contain would make the sheet a by-product of the directory rather than a stated
    # set of recordings.
    corpus = corpus_index(args.corpus)
    results = json.loads((args.batch / 'batch_results.json').read_text(encoding='utf-8'))
    rank = {track: index for index, track in enumerate(corpus)}
    rows = sorted((row for row in results if row['track_id'] in corpus),
                  key=lambda row: rank[row['track_id']])
    missing = set(corpus) - {row['track_id'] for row in rows}
    if missing:
        raise SystemExit('the batch has no result for: ' + ', '.join(sorted(missing)))

    cell_w = args.cell_width
    cell_h = round(cell_w * 2 / 3)
    columns = args.columns
    lines_of_caption = 4
    caption_h = 26 + lines_of_caption * 34
    gutter_x, gutter_y = 46, 40
    margin = 96
    header_h = 250
    footer_h = 96

    width = margin * 2 + columns * cell_w + (columns - 1) * gutter_x
    row_count = (len(rows) + columns - 1) // columns
    height = (header_h + margin + row_count * (cell_h + caption_h)
              + (row_count - 1) * gutter_y + footer_h)

    sheet = Image.new('RGB', (width, height), PAPER)
    draw = ImageDraw.Draw(sheet)

    title_font = font(SERIF, 74)
    subtitle_font = font(SERIF_ITALIC, 34)
    number_font = font(SERIF_BOLD, 30)
    caption_font = font(SERIF, 30)
    meta_font = font(SERIF, 27)
    foot_font = font(SERIF, 26)

    draw.text((margin, margin - 24), args.title, font=title_font, fill=INK)
    if args.subtitle:
        draw.text((margin, margin + 74), args.subtitle, font=subtitle_font, fill=GREY)
    draw.line([(margin, header_h + 4), (width - margin, header_h + 4)], fill=RULE, width=3)

    for index, row in enumerate(rows):
        column, line = index % columns, index // columns
        x = margin + column * (cell_w + gutter_x)
        y = header_h + margin // 2 + line * (cell_h + caption_h + gutter_y)

        source = args.renders / row['track_id'] / f'{args.view}.png'
        if source.is_file():
            with Image.open(source) as image:
                sheet.paste(fit(image.convert('RGB'), (cell_w, cell_h)), (x, y))
        else:
            draw.rectangle([x, y, x + cell_w, y + cell_h], fill=MISSING, outline=FAINT)
            note = 'not compiled' if row.get('status') != 'compiled' else 'not rendered'
            draw.text((x + cell_w / 2, y + cell_h / 2), f'{note} — {row.get("status")}',
                      font=caption_font, fill=GREY, anchor='mm')
        draw.rectangle([x, y, x + cell_w - 1, y + cell_h - 1], outline=FAINT, width=2)

        entry = corpus.get(row['track_id'], {})
        caption_y = y + cell_h + 16
        number = f'{index + 1:02d}'
        draw.text((x, caption_y), number, font=number_font, fill=INK)
        indent = draw.textlength('00', font=number_font) + 14

        title = entry.get('title', row['track_id'])
        for offset, text in enumerate(
                wrap(draw, title, caption_font, cell_w - indent)[:1]):
            draw.text((x + indent, caption_y - 2 + offset * 34), text,
                      font=caption_font, fill=INK)
        style = entry.get('style', '')
        draw.text((x + indent, caption_y + 32), style, font=meta_font, fill=GREY)
        facts = ' · '.join(part for part in (
            (row.get('typology') or '').title() or None,
            pretty(row.get('structural_system')),
            pretty(row.get('facade_grammar')),
        ) if part)
        draw.text((x + indent, caption_y + 66), facts, font=meta_font, fill=GREY)
        # Each cell is framed to fill itself, so the images carry no common scale.
        # The building's own extents put the scale back in the caption, where it is
        # read rather than inferred.
        size = span_of(args.renders / row['track_id'])
        measure = ' · '.join(part for part in (
            size,
            f'{row["elements"]:,} elements' if row.get('elements') else None,
        ) if part)
        draw.text((x + indent, caption_y + 100), measure, font=meta_font, fill=GREY)

    if args.footnote:
        draw.line([(margin, height - footer_h + 6), (width - margin, height - footer_h + 6)],
                  fill=FAINT, width=2)
        draw.text((margin, height - footer_h + 26), args.footnote,
                  font=foot_font, fill=GREY)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out, 'PNG', optimize=True)
    print(f'{len(rows)} cells -> {args.out} ({sheet.width} x {sheet.height})')


if __name__ == '__main__':
    main()
