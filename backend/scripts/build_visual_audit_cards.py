"""Assemble the five unaltered evidence views into one review card per recording."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
VIEW_LABELS = ['Three-quarter', 'Open side', 'Structure detail', 'South elevation', 'Massing']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch', type=Path)
    args = parser.parse_args()
    batch = args.batch.resolve()
    results = [json.loads(path.read_text(encoding='utf-8'))
               for path in sorted((batch / 'tracks').glob('*/result.json'))]
    out = batch / 'review_cards'
    out.mkdir(exist_ok=True)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 22)
    for result in results:
        if result['status'] != 'compiled':
            continue
        pictures = [ROOT / e['path'] for e in result['evidence'] if e['path'].endswith('.png')]
        if len(pictures) != 5:
            raise ValueError(f"Expected five views: {result['track_id']}")
        card = Image.new('RGB', (2400, 1210), 'white')
        draw = ImageDraw.Draw(card)
        draw.text((20, 12), f"{result['track_id']} | {result['typology']} | {result['massing']}", fill='black', font=font)
        for n, (picture, label) in enumerate(zip(pictures, VIEW_LABELS)):
            x, y = n % 3 * 800, 55 + n // 3 * 575
            with Image.open(picture) as source:
                source.thumbnail((800, 540))
                card.paste(source, (x + (800 - source.width) // 2, y))
            draw.text((x + 14, y + 541), label, fill='black', font=font)
        card.save(out / f"{result['track_id']}.jpg", quality=93)
        details = [batch / 'closeups' / f"{result['track_id']}-{view}.png"
                   for view in ('floor', 'section')]
        if all(path.is_file() for path in details):
            pair = Image.new('RGB', (1800, 644), 'white')
            for index, path in enumerate(details):
                with Image.open(path) as source:
                    source.thumbnail((900, 644))
                    pair.paste(source, (index * 900, 0))
            destination = batch / 'detail_cards'
            destination.mkdir(exist_ok=True)
            pair.save(destination / f"{result['track_id']}.jpg", quality=95)
    print(f'{len(list(out.glob("*.jpg")))} review cards')


if __name__ == '__main__':
    main()
