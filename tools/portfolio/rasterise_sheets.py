"""Rasterise issued drawing sheets to PNG at a stated pixel width.

Chrome renders the sheet, because Chrome is what everyone who opens the SVG will use
and its dash patterns, hatch fills and text metrics are the reference. svglib is kept
as the fallback for machines without Chrome; it is a different renderer, so the manifest
records which one drew each PNG rather than pretending the two are interchangeable.

    python tools/portfolio/rasterise_sheets.py <drawings_dir> --out <png_dir> --width 4000
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME_CANDIDATES = (
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
)


def find_chrome() -> Path | None:
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).is_file():
            return Path(candidate)
    found = shutil.which('chrome') or shutil.which('msedge')
    return Path(found) if found else None


def svg_aspect(svg: Path) -> float:
    """Height / width, read from the viewBox so the PNG keeps the sheet's proportion."""
    head = svg.read_text(encoding='utf-8', errors='ignore')[:2000]
    marker = 'viewBox="'
    start = head.index(marker) + len(marker)
    numbers = [float(v) for v in head[start:head.index('"', start)].split()]
    return numbers[3] / numbers[2]


def render_with_chrome(chrome: Path, svg: Path, png: Path, width: int) -> None:
    height = int(round(width * svg_aspect(svg)))
    with tempfile.TemporaryDirectory(prefix='mta-raster-') as workspace:
        page = Path(workspace) / 'sheet.html'
        page.write_text(
            '<!doctype html><meta charset="utf-8">'
            '<style>html,body{margin:0;padding:0;background:#fff}'
            f'img{{display:block;width:{width}px;height:{height}px}}</style>'
            f'<img src="{svg.resolve().as_uri()}">',
            encoding='utf-8')
        command = [
            str(chrome), '--headless=new', '--disable-gpu', '--hide-scrollbars',
            '--force-device-scale-factor=1', '--default-background-color=FFFFFFFF',
            f'--user-data-dir={workspace}/profile',
            f'--window-size={width},{height}',
            '--virtual-time-budget=30000',
            f'--screenshot={png.resolve()}', page.as_uri(),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if not png.is_file():
        raise RuntimeError(f'Chrome wrote no PNG for {svg.name}: {result.stderr[-800:]}')


def render_with_svglib(svg: Path, png: Path, width: int) -> None:
    from reportlab.graphics import renderPM
    from svglib.svglib import svg2rlg

    drawing = svg2rlg(str(svg))
    if drawing is None:
        raise RuntimeError(f'svglib could not parse {svg}')
    dpi = 72 * width / drawing.width
    renderPM.drawToPIL(drawing, dpi=dpi, bg=0xFFFFFF).save(png, 'PNG', optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('drawings', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--width', type=int, default=4000)
    parser.add_argument('--sheets', default='', help='Comma-separated sheet ids; default all')
    parser.add_argument('--engine', choices=('chrome', 'svglib', 'auto'), default='auto')
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    wanted = {s.strip() for s in args.sheets.split(',') if s.strip()}
    svgs = sorted(p for p in args.drawings.glob('*.svg') if not wanted or p.stem in wanted)
    if not svgs:
        raise SystemExit(f'No sheets to rasterise in {args.drawings}')

    chrome = find_chrome() if args.engine in ('chrome', 'auto') else None
    if args.engine == 'chrome' and chrome is None:
        raise SystemExit('Chrome was requested but not found')

    rows = []
    for svg in svgs:
        png = args.out / f'{svg.stem}.png'
        engine = 'chrome' if chrome else 'svglib'
        try:
            if chrome:
                render_with_chrome(chrome, svg, png, args.width)
            else:
                render_with_svglib(svg, png, args.width)
        except Exception as error:                              # noqa: BLE001
            if chrome and args.engine == 'auto':
                render_with_svglib(svg, png, args.width)
                engine = 'svglib'
                print(f'  {svg.stem}: chrome failed ({error}); svglib drew it instead')
            else:
                raise
        rows.append({'sheet': svg.stem, 'svg': str(svg), 'png': str(png),
                     'engine': engine, 'width_px': args.width,
                     'bytes': png.stat().st_size})
        print(f'  {svg.stem:8s} {engine:7s} {png.stat().st_size / 1048576:6.2f} MB')
    (args.out / 'raster_manifest.json').write_text(
        json.dumps({'source': str(args.drawings), 'sheets': rows}, indent=1),
        encoding='utf-8')
    print(f'{len(rows)} sheets -> {args.out}')


if __name__ == '__main__':
    sys.exit(main())
