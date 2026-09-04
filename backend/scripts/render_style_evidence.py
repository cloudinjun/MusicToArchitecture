"""Build and render one model per corpus track, then assemble the comparison sheets.

This exists to answer one question with pictures rather than with counts: do fourteen
recordings now produce fourteen buildings a person would call different, or do they
produce fourteen buildings that only a diff can tell apart?

The scores come from the corpus report's recorded per-track dimension values rather than
from the audio, so the run is fast, deterministic, and isolates what is being tested. The
audio path is already covered by `run_audio_saturation_corpus`; what is under test here
is the compiler, and re-extracting features would only add a variable.

    python -m backend.scripts.render_style_evidence
    python -m backend.scripts.render_style_evidence --no-render   # geometry only
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.blender_export_v3 import export_blender_web_model_v3
from backend.app.compiler_v3 import compile_building_model_v3
from backend.app.models import ArchitecturalScore, AudioFeatures
from backend.app.tectonics import ENVELOPE_TECTONICS, FRAME_TECTONICS

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / 'artifacts' / 'audio_saturation' / 'corpus-2026-08-30-rerun'
OUT = ROOT / 'artifacts' / 'style_evidence'
RENDER_ROOT = ROOT / 'artifacts' / 'v3_runs'
# The v3 demo, not the integrated one: the integrated demo predates schema 3.0 and
# carries only the four original dimensions. Using it as the template silently drops
# polyphony, hierarchy, repetition and the rest, every track then reads 0.5 on those
# axes, and all fourteen models collapse onto the same two grammars -- the original
# complaint, reproduced by the evidence script meant to disprove it.
DEMO = ROOT / 'artifacts' / 'v3_demo'

TEN_DIMENSIONS = {
    'tempo_of_change', 'tension_release', 'density', 'continuity', 'repetition',
    'variation', 'hierarchy', 'interruption', 'polyphony', 'genre_style',
}

SHEETS = {
    # Massing first: it is the thing the corpus failed at hardest and the thing a
    # viewer reads before anything else.
    '05_massing_south_west': 'contact_sheet_massing.png',
    '01_three_quarter': 'contact_sheet_three_quarter.png',
    '02_section_open_side': 'contact_sheet_section.png',
    '04_south_elevation': 'contact_sheet_elevation.png',
}


def load_tracks() -> list[dict]:
    report = json.loads(
        (CORPUS / 'corpus_saturation_report.json').read_text(encoding='utf-8'))
    return report['tracks']


def build_score(track: dict, template: ArchitecturalScore) -> ArchitecturalScore:
    """One track's recorded dimensions, wearing the template's evidence metadata.

    Confidence, extraction method and the mapping rules are properties of the extractor,
    not of the track, so they come from the template. Only the ten values move.
    """
    meta = {d.id: d for d in template.dimensions}
    missing = TEN_DIMENSIONS - set(meta)
    if missing:
        raise SystemExit(
            f'the template score is missing {sorted(missing)}. A dimension absent '
            'from the template is read at its 0.5 default for every track, which '
            'makes every building identical on that axis -- exactly the failure this '
            'script exists to measure. Regenerate the v3 demo before running it.')
    dimensions = [meta[key].model_copy(update={'value': value})
                  for key, value in track['dimensions'].items() if key in meta]
    slug = track['id'][:12].replace('-', '')[:12].ljust(12, '0')
    return ArchitecturalScore(
        score_id=f'score-{slug}', source_audio_sha256=track['excerpt_mp3_sha256'],
        mapping_rules=template.mapping_rules, dimensions=dimensions)


def contact_sheet(images: list[tuple[str, Path]], destination: Path,
                  columns: int = 4, cell_width: int = 620) -> None:
    """Lay the renders out in a grid with a caption strip under each one."""
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.truetype('arial.ttf', 17)
        small = ImageFont.truetype('arial.ttf', 14)
    except OSError:  # pragma: no cover - depends on the host's fonts
        font = small = ImageFont.load_default()

    thumbs = []
    for caption, path in images:
        image = Image.open(path).convert('RGB')
        ratio = cell_width / image.width
        thumbs.append((caption, image.resize(
            (cell_width, int(image.height * ratio)), Image.LANCZOS)))
    if not thumbs:
        return

    cell_height = max(t.height for _, t in thumbs)
    caption_height = 52
    rows = (len(thumbs) + columns - 1) // columns
    pad = 14
    sheet = Image.new(
        'RGB',
        (columns * cell_width + pad * (columns + 1),
         rows * (cell_height + caption_height) + pad * (rows + 1)),
        (250, 249, 246))
    draw = ImageDraw.Draw(sheet)

    for index, (caption, thumb) in enumerate(thumbs):
        row, column = divmod(index, columns)
        x = pad + column * (cell_width + pad)
        y = pad + row * (cell_height + caption_height + pad)
        sheet.paste(thumb, (x, y))
        title, _, subtitle = caption.partition('\n')
        draw.text((x + 4, y + cell_height + 6), title, fill=(24, 24, 26), font=font)
        draw.text((x + 4, y + cell_height + 28), subtitle, fill=(110, 108, 104),
                  font=small)

    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination)
    print(f'  wrote {destination.relative_to(ROOT)}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-render', action='store_true',
                        help='compile the models but skip Blender')
    parser.add_argument('--solid', action='store_true',
                        help='author the envelope on every face, so the massing reads as a volume rather than as a sliced stack')
    args = parser.parse_args()

    template = ArchitecturalScore.model_validate(json.loads(
        (DEMO / 'architectural_score.json')
        .read_text(encoding='utf-8')))
    # `features` is only carried through for provenance; the compiler reads the
    # score, not the raw metrics. The integrated demo still has a valid v2 payload
    # for it, and it does not touch the geometry.
    features = AudioFeatures.model_validate(json.loads(
        (ROOT / 'artifacts' / 'integrated_demo'
         / 'building-b7ad95fa45a6-library-steel-international-v1'
         / 'music_features.json').read_text(encoding='utf-8')))

    global OUT
    if args.solid:
        # A separate directory, because these are the same buildings photographed
        # differently and overwriting the cutaway sheets with them would lose the
        # structural read the project actually needs.
        OUT = OUT / 'solid'
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    per_view: dict[str, list[tuple[str, Path]]] = {name: [] for name in SHEETS}

    tracks = load_tracks()
    for index, track in enumerate(tracks, start=1):
        score = build_score(track, template)
        model = compile_building_model_v3(features, score,
                                          cutaway=not args.solid)
        grammar = model.facade_grammar_id
        envelope = ENVELOPE_TECTONICS[model.envelope_tectonic_id]
        frame = FRAME_TECTONICS[model.tectonic_system]
        sel = model.selection
        print(f'[{index:02d}/{len(tracks)}] {track["id"][:26]:28}'
              f'{sel.massing_id[4:]:13}{model.typology:9}{grammar[4:]:22}'
              f'{frame.id[4:]:13}'
              f'{len(model.lattice.levels):>3}L '
              f'{model.lattice.plan_x_m:>5.0f}x{model.lattice.plan_y_m:<5.0f}'
              f'{len(model.element_counts):>3}k '
              f'{"fits" if model.program_allocation.fits else "    "}')

        rows.append({
            'track_id': track['id'], 'title': track.get('title'),
            'style_family': track.get('style_family'),
            'model_id': model.model_id,
            'massing_id': sel.massing_id, 'massing_label': sel.massing_label,
            'massing_reason': sel.massing_reason,
            'typology': model.typology,
            'level_count': len(model.lattice.levels),
            'plan_x_m': model.lattice.plan_x_m,
            'plan_y_m': model.lattice.plan_y_m,
            'program_fits': model.program_allocation.fits,
            'facade_grammar_id': grammar,
            'envelope_tectonic': envelope.id,
            'envelope_label': envelope.label,
            'opening_logic': envelope.opening_logic,
            'structural_system_id': model.structural_system_id,
            'frame_tectonic': frame.id, 'frame_label': frame.label,
            'floor_system': frame.floor_system, 'lateral_kind': frame.lateral_kind,
            'element_count': len(model.elements),
            'element_kinds': sorted(model.element_counts),
            'overruled': bool(model.selection and model.selection.overruled_by_screen),
            'sizing_fallback': model.selection.sizing_fallback if model.selection else None,
            'axes': ({a.axis: a.value for a in model.selection.axes}
                     if model.selection else {}),
        })

        if args.no_render:
            continue
        asset = export_blender_web_model_v3(model, render=True)
        render_dir = RENDER_ROOT / model.model_id
        caption = (f'{index:02d}  {track.get("style_family") or track["id"]}\n'
                   f'{grammar[4:]}  ·  {envelope.label}  ·  {frame.label}')
        for view in SHEETS:
            candidate = render_dir / f'{view}.png'
            if candidate.is_file():
                per_view[view].append((caption, candidate))
        print(f'         rendered {asset.merged_object_count} objects, '
              f'{asset.face_count} faces')

    (OUT / 'style_evidence.json').write_text(
        json.dumps({'tracks': rows}, indent=2), encoding='utf-8')
    print(f'\nwrote {(OUT / "style_evidence.json").relative_to(ROOT)}')

    print()
    print(f'distinct massing families  : '
          f'{len({r["massing_id"] for r in rows})}')
    print(f'distinct typologies        : '
          f'{len({r["typology"] for r in rows})}')
    print(f'distinct footprints        : '
          f'{len({(round(r["plan_x_m"]), round(r["plan_y_m"])) for r in rows})}')
    print(f'level counts               : '
          f'{sorted({r["level_count"] for r in rows})}')
    print(f'program fits               : '
          f'{sum(1 for r in rows if r["program_fits"])}/{len(rows)}')
    grammars = {r['facade_grammar_id'] for r in rows}
    envelopes = {r['envelope_tectonic'] for r in rows}
    frames = {r['frame_tectonic'] for r in rows}
    kindsets = {tuple(r['element_kinds']) for r in rows}
    print(f'distinct facade grammars   : {len(grammars)}')
    print(f'distinct envelope tectonics: {len(envelopes)}')
    print(f'distinct frame tectonics   : {len(frames)}')
    print(f'distinct element vocabularies: {len(kindsets)} / {len(rows)}')

    if not args.no_render:
        print()
        for view, filename in SHEETS.items():
            contact_sheet(per_view[view], OUT / filename)


if __name__ == '__main__':
    main()
