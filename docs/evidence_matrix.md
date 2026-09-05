# Career Evidence Matrix

This file tracks whether implementation work supports the professional claims in
`PROJECT_CHARTER.md`. Update it when a material capability or experiment is completed.

Status values: `not started`, `in progress`, `demonstrated`, `verified`.

| ID | Claim | Required artifact or experiment | Metric / acceptance signal | Status |
|---|---|---|---|---|
| V1.1 | Qualitative intent becomes executable rules | Shared score schema plus documented mapping rules | Every mapping declares source, target, range, priority, and owner | verified |
| V1.2 | Typology, style, score, tectonics, and constraints remain distinct | Separate schemas/configuration contracts | No core field has ambiguous ownership | in progress |
| V2.1 | One intent coordinates multiple systems | Cross-system interpretation of one motif | At least three systems update coherently from one rule | demonstrated |
| V2.2 | Systems interpret intent without copying one scalar | System-specific adapters | Each adapter documents its architectural interpretation | demonstrated |
| V3.1 | Results are reproducible | Deterministic fixture and rerun test | Same input and seed produce equivalent output | verified |
| V3.2 | Changes propagate selectively | Before/after dependency experiment | Intended stages update; unrelated stages remain unchanged | verified |
| V3.3 | Failures are contained | Deliberately invalid input fixture | No partial invalid stage is committed | in progress |
| V3.4 | Outputs are traceable | Provenance fields and explainer | Generated objects resolve to source rule and input | verified |
| V3.5 | Core logic transfers | Selected-primary-to-transfer-typology test | Typology added mainly through constitution, graph, and adapter config | not started |
| V4.1 | Architectural requirements are evaluated | Typology/spatial/structure validators | Pass/fail report names rules and affected objects | verified |
| V4.2 | Compositional coherence is evaluated | Controlled score/style experiments | Expected changes and invariants are declared before generation | in progress |
| V4.3 | Limitations are reported honestly | Metrics and limitations summary | Manual interventions, runtime, pass rate, and unsupported checks disclosed | demonstrated |

## Required evidence set

| Evidence | Planned artifact | Status |
|---|---|---|
| Baseline failure | Legacy design-intent drift diagram and example | not started |
| Shared representation | Schema diagram and readable examples | demonstrated |
| Decision ownership | Designer/music/AI/solver/rejection ownership diagram | not started |
| Change propagation | One-rule controlled before/after experiment | verified |
| Failure and recovery | Span, circulation, panel, or adjacency rejection/correction | demonstrated |
| Transfer test | Primary typology to transfer typology comparison | not started |

## Update note format

When changing a status, add a short entry below:

```text
YYYY-MM-DD — Evidence ID — artifact/path — what was demonstrated — verification used
```

## Log

- 2026-09-04 — V3.1/V3.3/V3.4/V4.3 —
  `backend/scripts/publish_model_version.py`,
  `artifacts/model_versions/latest.json`, and
  `docs/decisions/0019-model-version-storage-and-promotion.md`, with the current visual
  findings in `docs/experiments/latest_model_visual_recheck_2026-09-04.md` — one checked promotion
  path now binds the portable model, Blender scene/GLB, renders, drawing previews, run
  contract, and tool-authority status to an immutable version. The current 3.4.0 bundle's
  26 assets match their archive hashes; public evidence uses stable `latest` URLs. Rhino is
  correctly blocked because the only existing `.3dm` predates the current run acceptance
  contract, while the matching Blender scene remains available for rendering. Superseded
  models and mixed-source portfolio plates are preserved with explicit historical or
  rejected statuses. Model and run identities now include the exact generation-source
  fingerprint; a source change during a run aborts publication. Verification:
  `publish_model_version --check` rehashed 199 assets across ten archives, and eight
  publication tests cover archive/public parity,
  stable URLs, empty blocked Rhino slots and exact Rhino run/model/hash acceptance, plus
  pipeline tests for concurrent source-change rejection and content-stable reruns.

- 2026-09-04 — V3.1/V3.4/V4.3 — `backend/app/drawings.py`,
  `backend/app/drawing_sheet.py`, `docs/decisions/0018-the-issued-set.md`, and
  `web/public/drawings/latest/A-*.svg` — the drawing set is now
  issued as a numbered set on one paper size (A0 for the frozen theater run): a
  cover with the drawing list, building facts, key plans and every drawing again at
  1:400; five plan sheets, two elevation sheets carrying the four faces, and one
  sheet carrying both sections, each drawing under its own caption, scale bar and
  audit. Every string on a sheet is read off the model; there is no date. The cut
  now applies as rules what was applied by eye: figures are never cut and stand as
  glyphs in section, the lift shaft is cut hollow, elements thinner than a line are
  drawn as their axis, the earth is hatched, the clip edge is never stroked, and a
  section steps off any wall it would lie inside and says so in its caption. With
  four elevations the frozen run's element account reads 3,545 drawn, 0 omitted by
  scale, 0 on no cut, and the buckets sum. Verification: 50 tests in
  `backend/tests/test_drawings.py` (paper uniformity, placement inside the drawing
  area, no date on a sheet, every stroke width on a composed sheet in the ISO
  series, elevations cutting nothing, the shaft hollow in both cuts, posts collapsing
  while columns keep their outline, clip edges unstroked, the offset resolver leaving
  no wall cut lengthwise), the regenerated demo payload, and a browser check of the
  Drawings panel. This is a presentation surface over the same reading of the model:
  no check is raised by it and no status in the table above changes.

- 2026-09-02 — V2.2/V3.3/V3.4/V4.3 — `backend/app/bim_handoff.py`,
  `web/components/workspaces/BimHandoffWorkspace.tsx`,
  `web/public/reports/demo_run.json`, and
  `artifacts/evidence/revit_dynamo_handoff_ui/` — the frozen theater run now joins its
  2,424 schema 3.0 elements to the versioned Revit/Dynamo registry and exposes the
  result in the Workbench. The panel shows 70/70 taxonomy kinds and 42/42 emitted kinds
  mapped, 2,220 BIM targets, 204 presentation-only omissions, 18 stable parameter GUIDs,
  delivery strategies, category gates, and bounded sync operations. Static evidence is
  `ready_for_dry_run`; installed-host proof remains visibly `pending`. Verification:
  19 targeted pytest checks, frontend lint and production build, a Playwright semantic
  snapshot, a 1600×1000 capture, and zero browser-console errors.

- 2026-09-02 — V3.1/V3.4/V4.3 — `blender/render_presets.py`,
  `backend/scripts/render_archviz.py`, and `artifacts/render_presets/model_v3/` — a
  presentation-only Blender adapter now self-frames any saved `.blend` into three views
  and renders photoreal, post-digital collage, cinematic, minimalist, and watercolor
  looks from native shader, World, Freestyle, and compositor nodes. Photoreal output
  uses Cycles, closer architectural cameras, transmissive glass, interior lights, and a
  deterministic shared-mesh landscape while filtering diagram-only program zones and
  scale figures. The evidence run
  produced 15 distinct 1400×900 PNGs whose hashes match `render_manifest.json`; the
  source and saved-template hashes also match, the input was not overwritten, and the
  manifest records no geometry mutation. Blender 5.0.1 reopen inspection retained 35
  style materials, five Worlds, five compositor groups, three cameras, and 192 shared
  tree instances plus the light/camera/ground helpers; a second 41-mesh generated building passed the same
  automatic framing path. Material-role inference now operates per material slot from
  names, metadata, or transmissive shader nodes, preserving mixed wall/window face
  assignments. The images are render evidence, not accepted-geometry or
  code-compliance evidence.

- 2026-09-02 — V2.2/V3.3/V3.4/V4.3 —
  `docs/decisions/0011-revit-dynamo-bim-handoff.md`,
  `docs/revit_dynamo_handoff.md`,
  `docs/contracts/revit_dynamo_mapping.v1.json`, and
  `backend/tests/test_revit_dynamo_contract.py` — prepared a bounded Revit/Dynamo BIM
  handoff: all 70 schema 3.0 element kinds have exactly one delivery strategy; stable
  source identity, shared-parameter GUIDs, unit/coordinate gates, native-versus-
  DirectShape status, conservative update/conflict/retirement semantics, rollback, and
  a four-run validation experiment are explicit. Static contract checks pass; live
  Revit/Dynamo execution, family/type resolution, transaction rollback, and unchanged-
  rerun evidence remain pending, so no integration or construction-readiness claim is
  made.

- 2026-08-26 — Charter initialized from the career-value discussion; no implementation
  evidence has been claimed yet.
- 2026-08-26 — Primary typology shortlist fixed to library, theater, and museum; final
  selection and transfer typology remain pending.
- 2026-08-26 — Tectonic shortlist fixed to frame, tensile, and shell; material,
  structural subtype, and final selection remain pending.
- 2026-08-26 — Architectural-language library fixed to ten candidates; the first
  controlled experiment will select and implement two executable grammars.
- 2026-08-26 — Brief generation defined as a pluggable random/local-LLM/external
  provider boundary; MP3 fixed as music input; ten shared score dimensions accepted
  with extraction-method, confidence, and provenance requirements.
- 2026-08-26 — Grasshopper designated as the primary interactive design environment,
  Rhino as accepted geometry/drawing host, and Blender as rendering, animation,
  explainer, and bounded downstream environment.
- 2026-08-26 — Grasshopper integration fixed to monitored local JSON contracts with
  modular readers/generators/validators, atomic publication, selective regeneration,
  and last-accepted-state protection.
- 2026-08-26 — V1.1 — `backend/app/models.py`, `backend/app/score.py` — four shared-score
  dimensions and five mappings declare source, target, range, priority, and owner —
  verified by `test_score_has_four_bounded_dimensions`.
- 2026-08-26 — V3.1/V3.2 — `backend/tests/test_compiler.py` — deterministic reruns and
  tempo-only propagation change module count while preserving the structural grid —
  verified by pytest.
- 2026-08-26 — V3.4/V4.1 — `backend/app/compiler.py` — all 32 elements from the MP3
  smoke test carried score bindings; five named validation checks reported no failure —
  verified by pytest and the local API end-to-end run.
- 2026-08-26 — V4.3 — `artifacts/gemini_smoke_test/README.md` — a Gemini/Lyria
  fixture exposed the whole-track tempo estimator's half-time/changing-tempo limitation;
  measured features, generated element count, pass rate, and next correction are reported.
- 2026-08-26 — V2.1/V2.2 — `grasshopper/MusicToArchitecture_MVP.gh`,
  `artifacts/model_versions/archive/20260827T062803Z-rhino-smoke-unversioned/rhino/model.3dm`, and
  `blender/examples/MusicToArchitecture_Gemini_SmokeTest.blend` — one accepted score/model
  contract produced browser, Grasshopper, Rhino, and Blender representations while
  massing and frame remained separate system adapters — verified by Rhino 8 GH solve,
  Rhino object inspection, Blender 5.0.1 reopen, and scene-state contract test.
- 2026-08-26 — V3.3/V3.4/V4.1 — `docs/native_model_workflow.md` — the Grasshopper
  definition exposes schema, generation, and validation status independently and the
  native objects preserve stable element IDs and score bindings; invalid-input
  last-accepted-state retention remains to be implemented before V3.3 can advance —
  verified against the 17-element Gemini fixture.
- 2026-08-27 — V2.1/V2.2/V3.4 — `blender/import_building_model.py`,
  `web/public/models/demo/library-pavilion.glb`, and
  `web/components/ArchitectureViewport.tsx` — one accepted building contract now
  coordinates facade, columns, beams, slabs, and foundations through system-specific
  Blender adapters; 91 exported objects preserve layer/subsystem provenance and appear
  as independently selectable browser systems — verified by Blender 5.0.1 GLB export,
  manifest counts, GLB extras inspection, pytest, TypeScript build, and ESLint.
- 2026-08-27 — V3.1/V4.3 — `backend/app/blender_export.py` and
  `docs/native_model_workflow.md` — an MP3 API request deterministically writes an
  editable `.blend`, GLB, scene state, and manifest while documenting the schematic
  status of facade/secondary structure — verified by a local HTTP 200 Gemini fixture
  run and explicit limitation disclosure.
- 2026-08-27 — V1.1/V2.1/V3.4/V4.1 — `backend/app/compiler.py`,
  `blender/import_building_model.py`, and `web/components/ArchitectureViewport.tsx` —
  public/private/circulation became an explicit validated program classification; five
  colored program masses and their derived facade/structure objects preserve category
  provenance through the GLB and browser filters — verified by pytest, Blender 5.0.1
  headless export, manifest/GLB extras inspection, TypeScript build, and ESLint.
- 2026-08-27 — V3.4/V4.3 — `blender/import_building_model.py`,
  `artifacts/native_models/blender_render.png`, and
  `web/public/models/demo/library-pavilion.manifest.json` — a deterministic
  presentation-only site layer supplies metric scale references without entering the
  accepted building contract; 3 site features, 6 trees, 2 cars, and 4 people retain
  context IDs and roles — verified by Blender 5.0.1 render/reopen, 139-object manifest
  counts, pytest, TypeScript build, and ESLint.
- 2026-08-27 — V1.1/V2.1/V3.4/V4.3 — `backend/app/mapping_report.py`,
  `web/components/MappingReport.tsx`, and
  `artifacts/gemini_smoke_test/mapping_report.json` — executed element bindings now
  expose seven music→Shared Score→architecture translations with measurement method,
  confidence, rule, negotiation, actual result, and affected IDs; known proxy and
  unsupported-dimension limits remain visible — verified by deterministic pytest,
  a real Gemini MP3 API/Blender run with 17/17 coverage, TypeScript build, and ESLint.
- 2026-08-27 — V1.2/V3.3 — `backend/app/integration.py`,
  `backend/app/models.py`, and
  `docs/decisions/0007-integrated-pipeline-run-and-acceptance-contract.md` — one run
  manifest now separates specification, observation, candidate, preview, Rhino-accepted,
  presentation, and validation authority; the facade host bridge exposes ten score
  availability slots and blocks candidate planning/Rhino acceptance while typology,
  tectonic profile, and grammar selections are missing — verified by two deterministic
  integration tests within the 11-test pytest suite. Detailed Program/Structure runtime
  contracts and rejected-state persistence remain pending, so both claims stay in progress.
- 2026-08-27 — V1.1/V2.1/V2.2/V3.1/V3.4/V4.1/V4.3 —
  `artifacts/evidence/integrated_library_building-b7ad95fa45a6/` and
  `artifacts/integrated_demo/building-b7ad95fa45a6-library-steel-international-v1/` —
  one Gemini MP3 run produced 21 detailed library spaces, 140 explicit steel-frame
  elements, 299 room-owned MTA-F2 facade elements, an 11-element interior sequence,
  site context, a seven-row Shared Score report, and five same-run layer/section
  captures — verified by 11 passing pytest tests, a successful frontend production
  build, Blender 5.0.1 headless GLB/.blend export, 471/471 provenance coverage, and
  facade reference/plan validation with no errors or warnings. Rhino acceptance,
  jurisdictional code review, structural analysis, and facade engineering remain open.
- 2026-08-30 — V4.2/V4.3 —
  `artifacts/audio_saturation/corpus-2026-08-30/` — fourteen licensed real recordings
  spanning curated style families ran through the same 30-second MP3, ten-dimension
  Shared Score, v3 datum, program, structure, envelope, and translation-health chain;
  predeclared endpoint and collision checks exposed a 31.0% raw-feature near-endpoint
  rate while retaining 0% score/model signature collisions and 100% variable coverage —
  verified by `backend/scripts/run_audio_saturation_corpus.py`, its three accounting
  tests, and 14/14 completed run manifests. V4.2 remains in progress because this probe
  calibrates input/output differentiation and does not yet judge full-song spatial
  sequence coherence.
- 2026-08-30 — V2.1/V3.1/V3.4/V4.2/V4.3 —
  `artifacts/audio_saturation/corpus-2026-08-30-rerun/` — the same fourteen source and
  excerpt hashes reran after the recorded audio-range calibration, producing fourteen
  complete v3 models and 56 Blender presentation-only evidence renders: three-quarter,
  open-side section, structure close-up, and south elevation for every run. All 56 PNG
  hashes match their fourteen `render_evidence.json` manifests; the run completed 14/14,
  retained 0% score/model signature collisions and 100% minimum variable-datum coverage,
  and reduced corpus endpoint saturation to 0%. Program allocation fit remains 8/14,
  and structural code tables remain placeholders, so these images demonstrate repeatable
  semantic generation and visual differentiation without claiming code compliance or
  full-song sequence quality — verified by 122 passing backend tests.
- 2026-08-31 — V2.1/V2.2/V3.1/V3.4/V4.2/V4.3 —
  `artifacts/audio_saturation/corpus-2026-08-31-semantic-rerun/` — all fourteen fixed
  source/excerpt hashes were re-analysed and recompiled into new v3 models, then rendered
  through three isolated semantic states per run: program plus circulation, envelope-only
  facade, and structure-only. The 42 source PNGs are 1600×1100, match all hashes in the
  fourteen `render_evidence.json` files, and feed three labelled contact sheets with their
  own manifest. Every model populated program (483–929 elements), circulation (571–1230),
  envelope (805–2677), structure (228–1566), and five site-context elements; the batch
  completed 14/14 with 0% score/model collisions, 100% minimum variable-datum coverage,
  and 11/14 program allocation fit — verified by 133 passing backend tests. These images
  prove semantic separation, repeatable generation, and cross-run differentiation while
  remaining Blender presentation evidence; Rhino acceptance and code-compliance claims
  remain outside their authority.
- 2026-08-31 — V4.1/V4.3 —
  `artifacts/audits/construction_component_audit_2026-08-31.md` — a construction-oriented
  audit checked all fourteen v3 models against current official accessibility, egress,
  steel, concrete, and mass-timber baselines; it separates plausible geometry from
  product-standard identity and completed code verification, identifies repeated
  life-safety and assembly blockers, and defines eight dependency-ordered reality gates —
  verified by direct JSON/model-contract inspection and cited primary standards. The
  artifact explicitly records 0/14 construction-ready and preserves every model's
  `professional_review_required` status.
- 2026-08-31 — V2.1/V2.2/V3.1/V3.4/V4.2/V4.3 —
  `artifacts/audio_saturation/corpus-2026-08-31-evidence-rerun-2/` — the current compiler
  reprocessed all fourteen licensed source excerpts and regenerated three isolated
  Blender semantic states per run: program plus circulation, envelope-only facade, and
  structure-only. The run completed 14/14 with no failures, produced 42 fresh 1600×1100
  PNGs, and matched all 42 source hashes and byte counts against the per-track
  `render_evidence.json` records. Three labelled contact sheets and their manifest expose
  the same-run comparison; score/model collision rates remain 0 and minimum variable
  coverage remains 100%. Program allocation fits 5/14 after the expanded constitution,
  so the evidence preserves nine explicit failures rather than treating rendered output
  as program validity. Blender evidence remains `presentation_only`; Rhino acceptance and
  professional code review remain separate gates.
- 2026-08-31 — V2.1/V3.1/V3.4/V4.1/V4.3 —
  `artifacts/audio_saturation/corpus-2026-08-31-dependency-rerun-2/` — all fourteen
  real-audio runs now carry a typed component dependency and attachment graph covering
  structure, roof, facade, circulation, interior construction, and site. The first run
  exposed two offset roofs with no purlin support; the corrected run completed 14/14
  with 62,828 unique element IDs, 74,345 resolved relations, 100% constructed-element
  connection coverage, 100% structure-to-soil paths, no failed graph checks, and exact
  graph round trips. Negative tests still reject missing beam supports. Connection
  plates, bolts, welds, anchors, fasteners, reinforcement, soil response, and capacity
  remain explicitly `not_checked`; this evidence verifies dependency topology and does
  not claim construction safety or code compliance.
- 2026-09-01 — V3.4/V4.1/V4.3 — `backend/app/analysis_bundle.py`,
  `web/public/reports/demo_run.json`, `web/app/page.tsx` — every schema 3.0 result the
  compiler produced now reaches a client. The response carries the selection record,
  datums, lattice, program allocation, member sizing, facade gates, accessible route,
  constitution, life-safety graph, dependency graph, axis report, site parameters and
  load cases, plus the issued sheets and stills as fetchable references; the web client
  mounts them across twelve workspaces, and `web/lib/types.ts` names every field on the
  wire. The roll-up counts passed, failed and **not evaluable** in three separate
  columns and has no field that can read as approval. Verification: eleven tests in
  `backend/tests/test_analysis_bundle.py` hold that every report reaches the bundle,
  that instance geometry does not, that an unevaluated clause is never counted as a
  pass, that a load computed from unreviewed site inputs is reported as not-a-design-
  value, and that artifact routes refuse to leave the artifact tree; the full suite
  passes 351/351. The frozen demo run is a real compile of the checked-in fixture, not
  a hand-written fixture. This is a reporting surface: it changes what is visible, not
  what has been checked, and no status in the table above is raised by it.

- 2026-09-04 — V2.1/V2.2/V3.1/V3.4/V4.1/V4.3 —
  `docs/experiments/visual_music_audit_20.md` and
  `artifacts/visual_audit/2026-09-03/verified-frozen/` — twenty license-documented
  recordings completed the real v3 pipeline and a seven-view visual inspection per
  model (100 Blender stills plus 40 actual-GLB cuts). A frozen 19-model baseline and
  one failed v2 export exposed uncut stair openings, shaft/flight and intercore
  overlaps, invalid west-apse boundaries, and exported false hole faces. Shared
  circulation layout, exact plate subtraction and simple-part decomposition resolve
  those bounded defects; v2 export failure is isolated without upgrading missing
  assets or Rhino acceptance. The public compact set retains 40 comparison cards,
  per-track measurements and matching source/audio hashes; full JSON/GLB/still runs and
  licensed audio remain in the ignored local audit store. Forty floor/ceiling
  surface-parity checks pass. Independent
  geometry measurement records zero findings in its defined classes but retains
  5,430 unevaluated head-clearance records. Visual review still identifies beam/core
  clashes and coplanar landing surfaces; lift design, eight unplaced program spaces,
  egress and construction checks remain unresolved. This entry demonstrates defect
  discovery, source-to-export verification and failure isolation, not construction
  readiness. Rejected intermediate exports remain locally as negative controls.
