# Pipeline figure — sources

`pipeline.svg` (1760 × 692) and its 3300 px raster. An A1 phase band: four phases, two
real artifacts each, one reading direction. No title, no legend, no caption on the
canvas; the caption below is text to paste beside the image.

## The specimen

Everything in the figure comes from one run of one recording — the same run the rest of
the `portfolio/` figure set was rendered against.

| | |
|---|---|
| Recording | `android-sock-hop` — *Android Sock Hop*, Kevin MacLeod, CC BY 4.0 (see [`docs/experiments/visual_music_corpus_20_license.md`](../../docs/experiments/visual_music_corpus_20_license.md)) |
| Run | `run-48ef74d3ea5f` |
| Model | `building-v3-17d43fed2ff2` |
| Compiler | 3.9.1, `v3_mode=program_volume`, authority `presentation_only` |
| Source inventory | sha256 `e56e4a893fc427ac1dfd8a1e3500f18a4cfba65edfb0b3f38690eab2322bd0b1` over the 86 hashed generation files, recorded in the batch's `source_identity.json` |
| Selection | library · program volume · steel frame · International Style |
| Size | 21,886 elements, 843 of them load-sized; 7 levels; 106 × 69 × 32 m |
| Compiled in | 203.74 s |
| Batch | [`artifacts/visual_audit/2026-09-07-portfolio`](../../artifacts/visual_audit/2026-09-07-portfolio) |

## Slot by slot

| Slot | File in `assets/` | Came from |
|---|---|---|
| Recording read as six measures | `01_score_strip.png` | the workbench's own score strip, captured as a DOM element while it read this run |
| Ten dimensions, one signature | `02_signature.png` | the Shared score report's signature, same capture |
| Full-height room volumes | `03_program_volumes.png` | `geometry/building-v3-17d43fed2ff2/06_program_volumes.png`, written by the run's Blender export |
| Rooms allocated on every plate | `04_program_layer.png` | the run's `.blend`, program + circulation layers isolated from the framed hero camera |
| Gravity frame, sized members | `05_structure_layer.png` | same `.blend`, structure layer, same camera |
| 21,886 elements | `06_building.png` | same `.blend`, all layers, same camera |
| 13 sheets, one paper size | `07_sheet.png` | sheet `A-301` of the issued set, rasterised from its own SVG |
| Every report on one model | `08_workbench.png` | the web workbench reading this run's payload, 1600 × 1000 at 2× |

The three Blender slots share one camera solved from the building's own bounding box, so
no layer is photographed from a kinder angle than the layer beside it. Assets are fitted
to one 3:2 frame: renders are cover-cropped, the score strip is centred on its own
ground because cropping it would throw away four of its six measures.

## What the figure does not claim

The phase names are the compiler's stages, not a design method for a person to follow.
`presentation_only` is the model's declared authority: nothing here is claimed usable,
buildable or code-compliant. This run's own verdicts are 81 checks passed, 6 failed and
36 unevaluated — one each under egress and occupancy, door openings and landings, the
accessible route and the brief (`SP-PERIODICALS` was not placed, so 2,861.74 m² of the
3,066.5 m² brief was delivered), and two under dependency topology
(`DEP-REQUIRED-COVERAGE`, `DEP-ASSEMBLY-TO-STRUCTURE`). The spatial-rule roll-up passes.

## Rebuilding it

```
python tools/portfolio/pipeline_figure.py \
    --batch artifacts/visual_audit/2026-09-07-portfolio --track android-sock-hop \
    --renders artifacts/evidence/twenty_buildings_2026-09-07/android-sock-hop \
    --sheets  artifacts/evidence/twenty_buildings_2026-09-07/android-sock-hop/sheets \
    --ui      artifacts/evidence/workbench_ui_2026-09-07 \
    --figure-assets artifacts/evidence/twenty_buildings_2026-09-07/android-sock-hop/figure_assets \
    --out portfolio/pipeline_2026-09-07
```

The raster is `svglib`, not Chrome: an SVG loaded as an image cannot reach its linked
thumbnails, so a browser screenshot of this file renders the chrome and none of the
evidence. Keep the assets beside the SVG.

This folder sits outside `render_paper_figures.py`'s scope — that script deletes
`portfolio/assets/` and `portfolio/fig*_*.*` on every run.
