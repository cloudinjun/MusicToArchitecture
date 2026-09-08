# Twenty buildings — sources

`twenty_buildings_2026-09-07.png` (5976 × 4198). A specimen grid: twenty recordings in
the corpus's own order, one camera rule, one caption shape. A recording that did not
compile keeps its cell and says so.

## The batch

| | |
|---|---|
| Corpus | the twenty recordings of [`docs/experiments/visual_music_plate_20260907.json`](../docs/experiments/visual_music_plate_20260907.json) — seventeen carried over from the licensed twenty-track corpus, three added 2026-09-07 for styles it did not cover; attribution and licence terms in [`visual_music_corpus_20_license.md`](../docs/experiments/visual_music_corpus_20_license.md) |
| Batch | [`artifacts/visual_audit/2026-09-07-portfolio`](../artifacts/visual_audit/2026-09-07-portfolio), run 2026-09-07 |
| Compiler | 3.9.1, `v3_mode=program_volume`, authority `presentation_only` |
| Source inventory | sha256 `e56e4a893fc427ac1dfd8a1e3500f18a4cfba65edfb0b3f38690eab2322bd0b1` over the 86 hashed generation files |
| Compiled | 20 of 20; 409,108 elements |
| Selections | typology 11 theater · 7 library · 1 museum · 1 pavilion; envelope 13 International Style · 5 Critical Regionalism · 2 Organic; frame 19 steel · 1 glulam post-and-beam |

The batch ran from a frozen copy of the generation source rather than from the working
tree. An earlier attempt aborted at the fourth recording because another session edited
six compiler files mid-run; the driver stops rather than mix two compilers inside one
comparison, and that abort's artifacts were discarded. Freezing first is what makes the
twenty cells comparable at all.

## The three added recordings

`tango-de-manzana`, `aces-high` and `ibn-al-noor` were added on 2026-09-07 from the same
official catalogue and the same CC BY 4.0 licence as the sixteen Kevin MacLeod recordings
already in the set, chosen for three styles the corpus did not cover — tango, big-band
swing and Middle Eastern. They were compiled on the same frozen source as the other
seventeen; the merge is refused unless both runs declare the same compiler identity, so
every cell on this plate came out of one compiler.

The set the plate shows is stated in
[`visual_music_plate_20260907.json`](../docs/experiments/visual_music_plate_20260907.json),
and the plate and the roll-up both read that manifest rather than whatever the batch
directory happens to hold.

## The camera

Every cell is one perspective from the same direction, the same 50 mm lens and the same
light, at a distance solved from that building's own bounding box — envelope, structure,
program and circulation, never the site plane or its context masses. The pipeline's own
review renders could not be used: their camera positions are literals, and a plate that
grows past 90 m walks out of the frame.

Because each building is framed to fill its own cell, **the images are not to a common
scale.** Every caption therefore states the building's own extents, read from the render
manifest that framed it.

## What the plate does not claim

`presentation_only` is the declared authority of every model in it. None is claimed
usable, buildable or code-compliant, and per-run verdicts vary widely: of the twenty,
one has no failed check and seventeen fail the dependency graph. The per-track roll-up
is in [`artifacts/evidence/twenty_buildings_2026-09-07/rank.csv`](../artifacts/evidence/twenty_buildings_2026-09-07/rank.csv).

## The specimen the rest of the set uses

`android-sock-hop` (cell 19) — `building-v3-17d43fed2ff2`, `run-48ef74d3ea5f`: a library
on a steel frame with an International Style envelope, 21,886 elements over 7 levels,
106 × 69 × 32 m, compiled in 203.74 s; 81 checks passed, 6 failed, 36 unevaluated, with
the spatial roll-up passing and the dependency graph failing two of its nine checks. It
is the specimen for `pipeline_2026-09-07`, for every `fig*` in this folder and for the
workbench stills in
[`artifacts/evidence/workbench_ui_2026-09-07`](../artifacts/evidence/workbench_ui_2026-09-07),
so the plate, the pipeline figure, the drawings and the interface all show one building.

Two alternatives kept beside it in
[`artifacts/evidence/twenty_buildings_2026-09-07`](../artifacts/evidence/twenty_buildings_2026-09-07),
each with a full view set and its own 13 sheets: `carefree` (cell 02), the only one of
the seventeen with no failed check, and `night-in-venice` (cell 09), the corpus's only
museum.

## Rebuilding it

```
python tools/portfolio/render_batch.py artifacts/visual_audit/2026-09-07-portfolio \
    --out artifacts/evidence/twenty_buildings_2026-09-07 --views hero,elevation
python tools/portfolio/contact_sheet.py artifacts/evidence/twenty_buildings_2026-09-07 \
    --batch artifacts/visual_audit/2026-09-07-portfolio \
    --corpus docs/experiments/visual_music_plate_20260907.json \
    --out portfolio/twenty_buildings_2026-09-07.png --columns 5
```
