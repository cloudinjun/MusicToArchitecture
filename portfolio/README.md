# Portfolio figures

The figure set this project shows to companies, reviewers and readers. Every image here
is a journal-style figure: evidence arranged in a reading order, with nothing else on the
canvas. The words that explain a figure live in [`captions.md`](captions.md), not in the
image, so each PNG can be placed on its own page and captioned in the document's own type.

**This folder is the single home for source images.** Before drawing an architecture
diagram, a pipeline figure, a specimen grid or any other image meant for a portfolio or a
paper, work here — replace a figure or add one — rather than starting a second set under
`artifacts/`, `docs/` or `web/`. `AGENTS.md` states the same rule for agents.

## What is here

| File | Skeleton | Shows | Reads |
|---|---|---|---|
| `fig1_framework` | phase band × specimen grid | three recordings through recording → score → massing → structure | corpus 2026-08-31 |
| `fig2_datum_clamp` | dot-and-range chart | 29 score-driven datums, grouped by driving dimension; reach permitted by confidence | demo run |
| `fig3_axes_and_massing` | (a) branch-and-merge, (b) decision flowchart | ten dimensions → four axes; the massing decision tree with its real thresholds | demo run + corpus |
| `fig4_two_authorities` | matrix | 10 structural systems × 10 facade grammars: affinity, screen, music's preference, chosen | demo run |
| `fig5_lattice` | keyed plan + section | the registration lattice drawn from data, keyed to the datums that set it, beside the massing | demo run |
| `fig6_fourteen_recordings` | specimen grid | fourteen massings, one camera | corpus 2026-08-31 |
| `fig7_semantic_layers` | specimen grid | five models × program / envelope / structure | corpus 2026-08-31 |
| `fig8_drawings` | keyed spatial (a)(b) | plan sheet A-102 and section sheet A-301, verbatim at A1 | demo run |
| `fig9_presentation_presets` | paired row | five presentation looks of one saved model | `artifacts/v3_demo/model_v3.blend` |
| `fig10_bim_handoff` | verbatim capture | the Workbench Revit/Dynamo handoff panel | `building-v3-b7ad95fa45a6` |
| `table1_verification` | journal table | passed / failed / unevaluated per authority | demo run |

Figures 2–5 are the core recipe between the score and the massing, drawn from the demo
run's own records: its datum set, its selection record, its lattice. They are the figures
a technical reviewer should read first.

"Demo run" is whatever `web/public/reports/demo_run.json` holds at render time; the
manifest records which run that was. Figures 1, 6 and 7 use the fourteen-track corpus
rerun of 2026-08-31 so that cross-recording comparisons are between models compiled by
the same compiler build.

Each figure exists as `<name>.svg` (the source: Times, grayscale chrome, thumbnails
linked from `assets/`) and `<name>.png` (3300 px wide, rasterised from that same SVG).
Edit the SVG in Illustrator or Inkscape if a one-off adjustment is needed; edit the
generator for anything that should survive regeneration.

## The contract every figure keeps

- No title, subtitle, heading, footnote, source line, logo or stamp inside the canvas.
  A multi-panel figure may carry a bare `(a)` `(b)` in a panel corner, nothing more.
- No sentence over 14 words; labels name, they do not explain. The explanation is the
  caption.
- Chrome is grayscale. Colour appears only inside data — a render, a program map — and
  the single red outline `#E8362D` marks the option carried forward.
- Type is Times New Roman throughout. Boxes, arrows and rules follow the constants in
  `backend/scripts/render_paper_figures.py`.
- Thumbnails are real: renders, drawings, waveforms from the cached audio, glyphs drawn
  from the score. Never an icon or a word where an image belongs.
- Plans carry a graphic scale bar and a north arrow. Verbatim artifacts (an emitted
  sheet, a UI capture) are reproduced whole, including their own title blocks.
- Every number printed in a caption is read from this repository's run data, and no
  status is upgraded: `unevaluated` stays unevaluated, Blender output stays
  presentation-only, the Revit contract stays `ready_for_dry_run`, failed checks are
  shown.

## Regenerate, replace, add

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.render_paper_figures
```

The generator rewrites every SVG, PNG and `assets/` thumbnail and then writes
`figures_manifest.json`, which pins the SHA-256 of each SVG and PNG and names the run,
the sheets and the tracks used. Commit the manifest with the figures.

Regeneration reads sources that git ignores — `artifacts/v3_runs/`, the corpus `tracks/`
renders, the local audio cache — so it works on a machine that has run the pipeline, not
on a fresh clone. The committed SVGs, PNGs and `assets/` are the pinned deliverable and
stand on their own.

To **replace** a figure, edit its `figN()` function and rerun; the hash changes and the
manifest records it. To **add** one, write a `figN()` in the same vocabulary (`slot`,
`img`, `arrow`, `key`, `text`), source its thumbnails through `thumb()` so they land in
`assets/`, register it in `main()`, add its caption to `captions.md`, and rerun. Choose
the skeleton by what the figure asserts — sequence, composition, relation, comparison or
extent — before drawing; if two unrelated skeletons want the same canvas, that is two
panels or two figures.

## Superseded

`artifacts/portfolio_plates/` is an earlier plate-style set with titles and data strips
drawn into the image. It was rejected in favour of this set and is kept only for
reference.
