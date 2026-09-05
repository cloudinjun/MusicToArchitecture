# Portfolio plates

Eight standalone PNGs, each readable on its own page. Every plate carries its own number,
title, one line of what it shows, and the figures that make it checkable — so a single
image can be placed without surrounding text and still say what it proves and what it
does not.

Regenerate with `python -m backend.scripts.render_portfolio_plates`.

| Plate | Shows | Source |
|---|---|---|
| P-01 | The pipeline: nine stages, four outputs, two authorities, nine checks | drawn |
| P-02 | Fourteen recordings, fourteen buildings | `style_evidence/contact_sheet_massing.png` |
| P-03 | The same fourteen with only structure shown | `audio_saturation/corpus-2026-08-31-evidence-rerun-2/contact_sheet_structure.png` |
| P-04 | Member-level resolution and what was load-sized | `v3_demo/03_structure_closeup.png` |
| P-05 | An emitted 1:100 plan sheet | `web/public/drawings/<run>/DWG-PLAN-L01.svg`, rasterised |
| P-06 | The verification schedule — pass / fail / unevaluated kept apart | drawn |
| P-07 | Five presentation looks from one saved `.blend` | `render_presets/model_v3/*/hero.png` |
| P-08 | The Revit/Dynamo delivery contract | `evidence/revit_dynamo_handoff_ui/bim_handoff_panel.png` |

All plates describe run `building-v3-c64269ebc1a8` unless the plate itself says it covers
the fourteen-track corpus (P-02, P-03).

## Claim discipline

Every figure printed on a plate is read from this repository's own run data. The plates
repeat the statuses the pipeline publishes and never upgrade one: `unevaluated` stays
unevaluated, Blender output stays presentation-only, the Revit contract stays
`ready_for_dry_run`, and every plate is stamped `professional_review_required`.

P-06 prints the construction audit's `0 of 14 construction-ready` deliberately. A plate
that showed only the passing counts would misrepresent the work.
