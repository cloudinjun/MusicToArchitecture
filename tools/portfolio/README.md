# Portfolio tooling

Scripts that turn a compiled batch into figures. They read artifacts and write images;
none of them compiles anything, and none of them lives under `backend/app`, `blender/` or
`rhino/` — the audit driver hashes those three trees and aborts a run if any file in them
changes mid-batch, so a tool added there would stop the very batch it was meant to
photograph.

| Script | Does |
|---|---|
| `render_portfolio_views.py` | a Blender script: measures the building's own bounds and solves the camera distance that fits every corner, then renders hero / aerial / orthographic elevation / orthographic plan, and optionally isolates one semantic layer at a time from the same camera |
| `render_batch.py` | runs the above over every compiled track in a batch, reading each track's own `.blend` |
| `rasterise_sheets.py` | issued-set SVG → PNG through Chrome (the reference renderer for these sheets), with `svglib` as the fallback and as the only option for a figure whose thumbnails are linked |
| `contact_sheet.py` | one plate holding every recording in a batch, failures included |
| `pipeline_figure.py` | the four-phase pipeline figure, assets fitted to one frame |
| `rank_batch.py` | every track's own published verdicts side by side, as a table, CSV and JSON |
| `stage_web_demo.py` | puts one compiled run in front of the workbench temporarily, and `--restore` puts the published demo back |
| `capture_ui.mjs` | Playwright: eighteen workbench stills at 2× |
| `capture_figure_assets.mjs` | Playwright: the two element-level crops the pipeline figure needs |
| `probe_blend.py` | dumps a `.blend`'s collection tree and per-collection bounds; used when a camera rule needs checking |

## Two things that will bite

**Blender needs absolute output paths.** A relative `--out` is silently resolved
somewhere else and the render never lands where the manifest says it did.

**An SVG with linked images cannot be screenshotted.** A browser loading
`<img src="figure.svg">` will not fetch the figure's thumbnails, so Chrome renders the
chrome and nothing else. Rasterise linked figures with `--engine svglib`; use Chrome for
drawing sheets, which are self-contained.

## Typical order

```
python tools/portfolio/render_batch.py <batch> --out <evidence-dir> --views hero,elevation
python tools/portfolio/rank_batch.py <batch> --csv <evidence-dir>/rank.csv
python tools/portfolio/contact_sheet.py <evidence-dir> --batch <batch> --out portfolio/<name>.png
```

Then, for a featured model: the full view set with `--layer-views`, its sheets through
`rasterise_sheets.py`, a staged capture through `stage_web_demo.py` and `capture_ui.mjs`,
and finally `pipeline_figure.py`.
