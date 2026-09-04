# Revit/Dynamo handoff UI evidence

This capture is the frozen demo run rendered in the web Workbench at 1600×1000.
The values are read from `analysis.bim_handoff`, compiled from the same schema 3.0
model and versioned mapping registry as the rest of the run.

Visible evidence:

- 70/70 schema 3.0 kinds and 42/42 emitted kinds have a declared strategy.
- 2,220 of 2,424 instances are BIM targets; 204 presentation-only instances are omitted.
- 18 shared parameters have stable GUIDs, with dry-run and reconciliation safeguards.
- Live Revit/Dynamo validation remains visibly `pending`.

Artifact:

- `bim_handoff_panel.png`
- SHA-256: `764427D9F10EF15814F8CA058880C5E96E2E519D6120DDE4F031F808CF63F885`

Verification: `npm run lint`, `npm run build`, 19 targeted pytest checks, Playwright
semantic snapshot, 1600×1000 screenshot, and zero browser-console errors.
