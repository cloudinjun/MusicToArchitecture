# Style evidence: fourteen recordings, fourteen buildings

Produced by `python -m backend.scripts.render_style_evidence`.

Each track's ten recorded score dimensions are replayed through the compiler, so this
isolates what is under test — the geometry — from the audio extraction, which
`run_audio_saturation_corpus` already covers.

## What varies, and what it used to be

| | before | after |
|---|---:|---:|
| massing families | 1 | **6** |
| typologies | 1 | **3** |
| distinct footprints | 1 | **10** |
| storey counts | 6–7 | **6–9** |
| facade grammars | 1 | **6** |
| structural systems | 1 | **3** |
| distinct element vocabularies | 1 | **11 / 14** |
| element kinds across the corpus | 36 | **48** |
| kinds shared by all fourteen | 35 | **27** |
| program brief fits | 8/14 | **11/14** |
| facade gates passing | (none ran) | **60/60** |

The last row of the old column is the point: the guides in `docs/style_guides/facade/`
existed and nothing checked against them. Four of the fourteen models self-corrected
once, re-emitting after the opening-ratio gate measured an elevation outside the band its
own guide publishes.

## The sheets

- `contact_sheet_massing.png` — from the south-west, where both visible faces are
  enclosed. This is the one to read silhouettes on; every other camera looks into the
  sectional cut, which is right for structure and wrong for massing.
- `contact_sheet_three_quarter.png` — the standard view, cut on the north and east.
- `contact_sheet_section.png` — into the open side.
- `contact_sheet_elevation.png` — south elevation.

## What this does not show

The sectional cut removes the north and east faces of every model, which is a
presentation decision recorded in `datums.envelope_stations_visible` rather than a
property of the buildings. A split mass whose break faces the cut reads less clearly than
it should.

Three of the eight facade grammars and one of the seven massing families were not
selected by any of these fourteen recordings. They are reachable — the sweeps in
`backend/tests/test_differentiation.py` prove every leaf of every decision tree has a
non-empty preimage — but fourteen tracks are not a sample of music.
