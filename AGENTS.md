# Project Agent Notes

## Mandatory project purpose

- Read `PROJECT_CHARTER.md` before planning architecture, adding features, migrating
  legacy code, or changing project scope.
- Treat `PROJECT_CHARTER.md` as the decision filter for this repository.
- Material work must make at least one charter ability visible: V1 formalizing intent,
  V2 coordinating systems, V3 building a reliable workflow, or V4 evaluating results.
- Identify the intended portfolio evidence or quality gate before implementing a
  material feature.
- Update `docs/evidence_matrix.md` only when an artifact genuinely demonstrates or
  verifies a claim. Do not mark planned work as demonstrated.
- Keep music as the memorable stress test and public story; prioritize transferable
  design-intent computation in engineering decisions.
- Defer scope that only adds output count, style count, technologies, or visual effects
  until the core evidence set is complete.
- The primary typology must be selected from library, theater, and museum using
  `docs/decisions/0001-primary-typology-shortlist.md`. Do not build all three or add a
  fourth candidate during the first selection round.
- The first tectonic system must be selected from frame, tensile, and shell using
  `docs/decisions/0002-tectonic-system-shortlist.md`. Keep tectonics separate from
  style grammar and do not build three complete structural generators.
- That shortlist is a three-gate N-choose-1: family (3) -> executable system (10 -> 3)
  -> single selection (1). The ten systems each have an independent guideline in
  `docs/guidelines/structural_systems/`; the selection protocol, geometry-primitive
  requirement matrix, and MTA-S stages are in that folder's `README.md`.
  `docs/guidelines/structural_system_guideline.md` remains the shared contract every
  system obeys. Do not add an eleventh system unless its element taxonomy, required
  geometry primitives, and validation gates are all three materially different, and do
  not write extra guidelines instead of closing the selection.
- The element taxonomy, four geometry primitives, and datum chain that any structural
  system must emit into are defined in
  `docs/decisions/0008-element-taxonomy-and-datum-chain.md`. Do not position a generated
  element with an absolute coordinate literal; index it into the registration lattice.
- Schema 3.0 implements that decision and runs **in parallel with v2, not instead of it**.
  `compiler.py` still owns the massing contract that the Grasshopper watcher, the facade
  handoff, and the acceptance manifest read; `compiler_v3.py` owns the member-level model
  the viewport draws. Neither derives from the other, so a v3 failure must never block the
  v2 acceptance chain. Do not merge them without replacing every v2 consumer first.
- The v3 chain is `datums.py` (score -> datums -> lattice) -> `program.py` (area brief ->
  allocated zones) -> `compiler_v3.py` (lattice + allocation -> elements) ->
  `blender/import_building_model_v3.py` (elements -> GLB). Four rules are binding: no
  emitter may contain a coordinate literal; a datum whose driving score dimension is
  absent records `provenance='design_fixture'` and never counts toward mapping coverage;
  only members a load calculation governed may carry
  `sizing_status='sized_by_calculation'` and a utilisation; and the program allocator
  must report what it could not place rather than shrinking rooms to make the brief fit.
- All ten shared score dimensions are emitted by `score.py` and every variable datum is
  score-driven. Three rules protect that from becoming a claim the evidence cannot
  carry: `repetition` and `variation` must never share a source feature; a proxy is
  declared `inferred` with its real confidence, never `observed`; and `datums.py` clamps
  how far a datum may travel by `confidence / 0.75`, so a low-confidence reading nudges
  and a high-confidence one commits. `genre_style` is a timbral position, not a genre —
  it proposes a facade weighting for a human to accept and never selects a grammar.
-  grades each dimension on four separate axes:
  evidence, travel, reach, and outcome. A dimension that is measured perfectly but
  touches nothing is not `strong`. Do not collapse those axes into one score, and do
  not let a dimension appear healthy because it is merely present.
- `backend/app/translation_report.py` grades each dimension on four separate axes:
  evidence, travel, reach, and outcome. A dimension that is measured perfectly but
  touches nothing is not `strong`, and one that is merely present is not healthy. Do
  not collapse those axes into a single score; the web health check exists because a
  mapping table makes an inert dimension look identical to a load-bearing one.
- The health check is rendered by `web/components/TranslationHealthReport.tsx` and
  reads `web/public/reports/translation_report.json` for the demo, or the API
  response for a real run. Regenerate the demo copy with
  `python -m backend.scripts.generate_v3_demo` whenever the datum table changes.
- Report datum coverage two ways. Overall coverage includes the tectonic constants and
  will never reach 100 %; `variable_coverage` is the honest figure for how much of the
  design the music reaches. Do not quote one without the other.
- `program.py` states the brief as areas and requirements. Do not reintroduce literal
  room rectangles or fractions of a bounding box; both are the same mistake the datum
  chain exists to remove. A room's proportion must remain a consequence of the
  structural grid the score set.
- Elements are serialised as `element_groups`, not a flat list. `BuildingModelV3.elements`
  expands them, so consumers still see flat records; do not flatten the payload on the
  wire.
- Typology, structural system, and facade grammar are coupled by
  `docs/decisions/0009-program-structure-facade-coupling.md`, implemented in
  `backend/app/{codes,coupling,sections,loads,sizing,optimizer}.py`. Five rules are
  binding: this is an elimination stage and no layer may pre-empt selection; only hard
  standards eliminate, and soft axes have no elimination power; compatibility is computed
  from declared physical quantities, never from a hand-authored matrix; structural claims
  come from a load calculation with a stated basis; and cost is not a criterion yet, so
  `material_efficiency` stays at weight zero until `ObjectiveWeights.selection_stage()`
  is deliberately chosen.
- Do not sort the feasible domain by `resolution_burden` and present the top row as a
  recommendation. Burden describes detailing effort, not quality. `screen_project`
  returns the set in identifier order for exactly this reason.
- Code tables in `backend/app/codes.py` are placeholders. A rule evaluated against them
  may return `fail` or `code_inputs_incomplete` but never `pass`, and an exclusion made
  on them is `provisionally_excluded`, never `excluded`. Do not remove that distinction,
  and never emit `code_compliant`, `safe`, or `permit_ready`.
- Architectural-language candidates and the two-grammar selection protocol are defined
  in `docs/decisions/0003-style-language-candidate-library.md`. Do not implement all
  ten candidates or reduce a named architectural language to a prompt adjective.
- Project-brief providers, lightweight program rules, MP3 input, and the ten shared
  score dimensions are defined in
  `docs/decisions/0004-project-brief-program-and-mp3-score-contract.md`.
- Keep brief generation pluggable. Random and local-LLM output must normalize and
  validate into the same schema used by future real-project briefs.
- Record extraction method, confidence, and provenance for MP3-derived dimensions.
  Unsupported dimensions must remain unknown or require review.
- Treat legacy program and structure constraints as scoped heuristics with provenance;
  do not present them as universal code requirements.
- Software authority and synchronization rules are defined in
  `docs/decisions/0005-software-toolchain-and-authority.md`. Grasshopper is the primary
  interactive design environment; Rhino owns accepted geometry/drawings; Blender owns
  rendering, animation, explainer staging, and bounded downstream adapters.
- Keep portable rules independent from RhinoCommon and `bpy` where practical. Blender
  must not silently reinterpret score mappings or modify accepted design authority.
- Grasshopper JSON monitoring and component boundaries are defined in
  `docs/decisions/0006-grasshopper-json-watch-and-component-architecture.md`.
- Do not implement the Grasshopper pipeline as one Python/C# component. Separate file
  watching, schema gates, contract readers, system generators, validators, accepted
  state, and bake/export responsibilities.
- Publish JSON atomically and use schema versions, hashes, run IDs, debounce/stability
  checks, and last-accepted-state protection.
- Before building the first Grasshopper reader/preview, read
  `docs/legacy/grasshopper_program_diagram_reference.md`. Preserve its visible
  file-reader → bounded parser → separate native geometry/preview pattern while
  replacing positional text and absolute paths with versioned JSON contracts.

## What the score must be allowed to decide

Four things about a building are chosen from the score: its **type** (which brief),
its **form** (which massing family), its **style** (which facade grammar) and its
**structure** (which system). Each was a module constant once, and each time the symptom
was the same -- every recording produced the same building -- so the rules below exist to
stop any of them quietly becoming one again.

- **No decision that belongs to the score may be a module constant or a one-value
  `Literal`.** `typology: Literal['library'] = 'library'` is not a default a caller can
  override; it is a type that admits one building. If a decision has an obvious fallback,
  make it a named default the score can move off, not a constant.
- **A decision tree with an unreachable leaf is a constant wearing a condition.** Every
  tree in `selection.py`, `massing.py` and `briefs.py` is swept in
  `backend/tests/test_differentiation.py`, and a new branch needs a new sweep. Two real
  cases: `FRM-CONCRETE` was positioned and unreachable because the system behind it was
  screened out, and the ziggurat branch sat in a window 0.04 wide between two thresholds.
- **Do not choose by nearest neighbour over a fixed option set.** It concentrates on
  whatever sits nearest the middle of the data and leaves the corners dead, and no
  reweighting fixes that. Ask a short sequence of discrete questions against single axes
  instead, and write each threshold so a reader can disagree with it in words.
- **Never average two readings into one axis.** The mean of two mid-range numbers is
  more mid-range than either, so the axis can never reach its own ends. Take the more
  decisive reading -- `selection._decisive` -- and say why.
- **Do not tune thresholds against the corpus.** Fourteen recordings do not define
  architecture any more than they define a normalisation range. Reachability over the
  whole axis space is the test; the corpus is evidence, not a target.
- **A footprint is not a coordinate literal.** `PlanBounds` travels on the lattice.
  Anything positioned in plan -- the sectional cut, void seeds, entry -- takes fractions
  of it. Decision 0008 forbade absolute coordinates in emitters; the same rule applies to
  the ground they stand on.

## Facade grammars and their guides

`docs/style_guides/facade/` holds ten written guides. They are not background reading:
`grammar_specs.py` transcribes their numbers and `facade_gates.py` runs their Validation
sections against the emitted geometry.

- Every number in `grammar_specs.py` comes from a guide's *Legal variables* table. If a
  guide declines to publish one -- Critical Regionalism gives derivation rules, because a
  shading depth without a latitude is a decoration -- record the refusal rather than
  inventing a plausible figure.
- `score_authority` is how much the music may move that grammar. It is a published
  figure, not a tuning knob: Minimalism states +/-0-12 % outright.
- A tectonic's `base_opacity` must sit inside the opening band of every grammar it
  serves, so the tectonic alone lands where its guide expects with no music at all.
  Getting this wrong puts two gates in direct conflict, each correctly reporting the
  other's fix as a violation.
- Gate verdicts are three-valued. A gate the pipeline cannot evaluate returns
  `unevaluated` and never `passed`; the distinction between "checked and fine" and "could
  not check" is the point.
- `correction_for` proposes a repair only where the fix is a single unambiguous scalar.
  Everything else fails loudly. A compiler that guesses at what a designer meant is worse
  than one that reports the problem.

## Comparing two runs

`compile_building_model_v3` takes `massing_id`, `typology` and `grammar_id`. Use them
whenever a test or an experiment isolates one variable: a score dimension usually reaches
further than it looks, and `repetition` alone moves the mullion module, the facade
grammar *and* the silhouette. Several existing tests had quietly become assertions about
whichever building the fixture happened to produce.

## Interior partitions

A partition is chosen, not drawn. `partitions.py` answers three questions and each one
cites where its answer comes from:

- **Fire rating** from IBC 509 incidental uses, 707.4 shafts and 1020.1 corridors. The
  sprinkler alternative applies only where the table offers it -- a storage room takes it,
  a mechanical room does not.
- **Acoustic target** from ANSI/ASA S12.60 where it applies and from ordinary practice
  elsewhere, labelled as practice. Never present an STC target as a code requirement.
- **Permeability** from the constitution's `access_class`: a service or staff zone is
  reached through a controlled door, not a threshold.

Fire and acoustics are separate answers. The two-hour masonry wall is acoustically worse
than the one-hour double-stud one, so neither is a proxy for the other.

`select_partition` returns the **lightest** assembly that satisfies both, so the order of
`PARTITION_TYPES` is the design objective and is sorted rather than hand-maintained. A
heavier wall than the requirement is not a safety margin, it is cost and floor area.

Two more rules the emitter holds:

- **Every opening is a door with a head over it.** A rated wall that stops at the door
  head is not rated.
- **A wall nothing asks for is not built.** Two rooms in open categories with no rating
  and no acoustic target stay open; the plate reads as one floor.

## Site data, and the seam a person takes over

Anything that depends on where the building is -- wind, seismic, snow, the adopted code
edition -- goes through `site.py`. Three rules:

- **Every parameter is a `SourcedValue`, never a bare number.** The question a reviewer
  asks about a basic wind speed is not what it is, it is who says so. Adding a parameter
  means adding its `basis` and leaving `needs_review=True`.
- **A value nobody has reviewed cannot become a design value.** `code_lookup` and
  `llm_proposed` are not strong enough to design on; only `manual` and `verified_lookup`
  are. Results computed from a weak input carry that weakness (`LoadResult.design_ready`)
  and the clause stays `unevaluated` with the figure shown. Never widen `STRONG_SOURCES`
  to make a report look better.
- **Replacement is per field.** `override(site, by=..., field=value)` marks one value
  `manual` and leaves the rest alone. A project with a real site passes a whole
  `SiteParameters` into `compile_building_model_v3(site=...)` and the proposal never
  runs.

The lookup table's numbers are recalled, not read. Treat adding a row as adding a
starting point for a reviewer, not as adding a fact, and keep the row's `basis` honest
about that.

## Permit level, not coordination level

Four rules keep the model on the permit side of that line.

**A member carries a designation somebody can order.** `registry.py` lists real products
with the standard each is made to. Never generate a section from proportions: a correct
calculation of a shape nobody rolls is a schematic model with good arithmetic. Adding a
product means adding its published dimensions and, where they can be vouched for, its
published properties for `verify_against_catalogue()` to check against. Where they cannot
be vouched for, leave them out and say why -- a cross-check against a number nobody can
stand behind either passes spuriously or fails spuriously.

**Idealise conservatively or not at all.** A rolled shape without its fillets computes
low, which is safe and is reported. A hollow section without its corner radii computes
*high*, which makes a column look stronger than it is; those corners are modelled. Before
simplifying a section, work out which way the error goes.

**A check that is not run is listed on every member.** `validators.py` returns a clause
record, and `unevaluated` clauses appear on each member rather than in a project note,
because a reviewer reads a member calculation. Never assume a clause away in a docstring:
`steel_flexural_capacity` said "continuously braced compression flange assumed" for a
girder braced only at its joists, and when AISC F2.2 was finally run it governed at 1.71
where yielding read 0.55.

**A quantity that belongs to a code profile is a placeholder that says so.** Restroom
fixture counts belong to the adopted plumbing code and mechanical area to the system
selection. Generate the space so the allocator has to find room for it, and put the
delegation in the space's own reason. A placeholder that announces itself is usable; one
that does not is fabricated compliance.

`constitution.py` holds the base-building support every building needs, `life_safety.py`
holds the IBC Chapter 10 graph, and both travel on the model. When either reports a
failure the honest response is to fix the building or to leave the failure visible --
never to relax the check. Both found real defects on their first run: four typologies
satisfying 2-4 of 15 support requirements, and a 419-occupant building with one stair
core failing exit remoteness at 2.11.

## Circulation

The accessible route obeys ADA §405 or it is not a ramp:

- **`ada.plan_switchback_ramp` returns a compliant plan or nothing.** There is no third
  outcome by design. An almost-compliant ramp is worse than none: it occupies the place
  the accessible route belongs and reports the problem as solved.
- **Where no compliant ramp fits, build a stair and record why** on
  `model.accessible_route_unresolved`. Three of the seven massing families reach this
  branch on the corpus, all of them compact towers, and that is the rule working rather
  than a gap.
- **Every constant in `ada.py` cites its clause.** Adding one without a citation means
  nobody can check it against the standard.
- **Measure a run on its centre-line, not its bounding box.** A swept deck's box
  includes its thickness, which turns a compliant 1:12 into an apparent 1:8.6 and
  reports violations that are not there.

A stair is only a stair if it meets the floors it serves, and the check is cheap:

- **A `stair_landing` must be flush with its level's plate and inside it.** Flush means
  its top surface is the floor, not a step above or below. `stair_half_landing` is the
  separate kind for the turn between flights, which is flush with nothing.
- **The stair core follows the column invariant**: a location is usable only if every
  plate from the ground to the top contains the whole stair footprint, landings
  included. Checking the flight width alone puts landings outside the plate they are
  flush with.
- **Where no core serves every level, serve the tallest run that works and record the
  rest.** A stair drawn through floors it cannot land on is worse than a short one.
- **Only the entrance flight may stand outside the building.** It climbs from grade;
  everything else that does is a stair that missed.

`backend/tests/test_differentiation.py` holds all four across every massing family. Any
change to `_emit_circulation`, to `_plate_polygon`, or to a massing family's profile can
break them, and three real massing defects — an asymmetric taper, an uncapped rotation
about a drifting centroid, and a minimum-plate guard checked before the last narrowing —
were found by these tests rather than by looking at renders.

## Audio normalisation ranges

The 0..1 normalisation in `backend/app/audio.py` is calibrated, not chosen. Do not edit a
range or a transform by hand.

- Ranges and transforms come from `backend/scripts/calibrate_audio_ranges.py`, run
  against the cross-genre corpus report. Change the corpus or the selection rule, re-run
  the script, and re-run `backend.scripts.run_audio_saturation_corpus` to confirm the
  saturation figures before committing.
- A reading within 0.02 of an endpoint has stopped measuring: every recording in that
  neighbourhood produces the same building parameter. Both saturation tests in
  `backend/tests/test_score_dimensions.py` must stay green, and the out-of-corpus one is
  the load-bearing check — a range that only holds on the corpus is fitted to it.
- `DOMAIN_BOUNDS` in the calibrator is for quantities whose extent is known from their
  definition or the physics. Adding a feature there is a claim about the world, not about
  the corpus; if the number would be a guess, leave it out and let the corpus rule apply.
- Recalibrating shifts every normalised value, so regenerate the demo afterwards
  (`python -m backend.scripts.generate_v3_demo` for the artifacts,
  `python -m backend.scripts.generate_web_demo` for the browser's frozen run) or the
  published health-check JSON, the GLB, the sheets and the renders go stale against the
  code. The web demo writes its own asset URLs, so there is no hand-maintained fixture
  to bump; the hardcoded `web/lib/demo-building.ts` it replaced has been removed.

See `docs/experiments/audio_normalization_calibration.md` for the reasoning and the
current table.

## The web workbench, and what must reach it

A run computes forty-odd reports. For a long time the browser received five of them,
and the rest existed only inside a request that had already returned — which is how the
page came to show four of twelve audio features and none of the sizing, the gates, the
egress graph or the drawings. Four rules keep that from happening again.

- **`pipeline.py` is what a run is.** `main.py` maps it onto HTTP and
  `backend.scripts.generate_web_demo` writes it to disk. Neither may grow its own copy
  of the chain: the demo drifting from the API is the original defect, not a variant of
  it.
- **`analysis_bundle.py` is a view, not a stage.** It carries the schema 3.0 results and
  computes nothing except the roll-up count. It must never upgrade a status — an
  `unevaluated` gate is counted in its own column, and `ComplianceRollup` deliberately
  has no field that could read as approval. Adding a report to `BuildingModelV3` means
  adding it here in the same change, or it is invisible again.
- **Instance geometry stays out of the payload.** Element groups travel with their
  descriptive fields and an instance count; the browser draws the instances from the
  GLB. Putting them back would triple the response to say the same thing twice.
- **`web/lib/types.ts` names every field the backend sends,** including ones no panel
  draws yet. A page can only show what it can name, and the four-of-twelve bug was a
  missing type before it was a missing panel.

The frozen demo run at `web/public/reports/demo_run.json` is a real compile, not a
fixture. Regenerate it with `python -m backend.scripts.generate_web_demo` whenever the
payload shape, the datum table, or the GLB changes; it rewrites the sheets and stills
in `web/public` and re-points their URLs, so the workbench needs no server to show a
complete run. Live runs are stored in `artifacts/web_runs/` keyed by the audio hash, so
re-running one recording replaces its entry rather than accumulating duplicates.

Colour in the workbench carries no information a label does not repeat, and there are
four status tones because `unknown` is one of them. Do not add a fifth, and do not
render an unevaluated check as a quieter pass.

**The visual language is the macOS idiom, and it lives in `web/app/globals.css`.**
Every token a component needs is already defined there; a new panel spends them and
adds none. The rules that keep the surface coherent:

- One accent (`--accent`, system blue) plus the four status tones. Everything else is
  ink on white or gray.
- Radii come from the four-step scale (`--r-sm` … `--r-xl`); borders are translucent
  hairlines (`--hairline`, `--hairline-soft`), never solid gray outlines. `--line` is
  solid and exists only as the backdrop of gap-grids.
- Overlays — title bar, menus, floating panels, the section dock, toasts — are frosted
  (`--glass`, `--glass-strong` with `backdrop-filter`); the report sheet stays opaque
  because dense tables sit on it. Elevation uses the `--shadow-*` scale.
- Labels are sentence case. The uppercase micro-label is not part of this language;
  the only survivors are tiny provenance badges (the demo tag) and the two embedded
  legacy reports' kickers.
- Menus highlight the full row in accent with white text, macOS-style. Segmented
  controls are a gray track with a raised white thumb. Pressed toolbar toggles are
  accent-tinted, and their rule outranks `.btn:hover` so the label never washes out
  under the cursor.
- Motion is 150–320 ms on `--ease-sheet`/`--ease-out`, distance is small, and every
  animation is disabled under `prefers-reduced-motion`.

**This is a user interface, not a debug dashboard.** The panel a viewer meets first —
Overview — speaks prose: the renders, one sentence about the building, the four
decisions with their reasons in words, and a plain-language account of the brief and
the checks. Three rules keep it that way:

- KPI grids, clause tables and blocker lists belong to the Evidence and Diagnostics
  panels. Overview may summarise them in a sentence and link to them, never render
  them.
- Machine identifiers (`STR-SYS-…`, `FCD-…`, run hashes) never appear on a narrative
  surface. Humanise them (`humanize` in OverviewWorkspace strips the prefix and
  title-cases); the ids stay intact in Selection, Artifacts and Diagnostics where a
  reader needs to cite them.
- Nothing is deleted to achieve this. Every table that leaves a narrative panel must
  land in an evidence panel in the same change — the check-family table moved from
  Overview into Compliance, it did not disappear.

**The interface performs process and argument — it does not exhibit results.** This is
the Craftbot lesson, adopted deliberately and per the user's direction, HUD included:

- **Two modes, one component set.** `data-mode` on `.shell` flips the tokens:
  `blueprint` (the default) is a cyanotype — Prussian-blue ground, white line work
  with hidden-line occlusion (opaque ground-colour fills under white `EdgesGeometry`
  overlays), graph-paper grid, mono type; `studio` is the light macOS face. Neither
  mode owns any component; everything reads the same tokens.
- **The model assembles itself** in construction order (site → structure → envelope →
  circulation → program, `LAYER_ORDER` in `ArchitectureViewport`), narrating the stage
  through the HUD; `prefers-reduced-motion` skips it, and the Build button replays it.
- **Presentation surfaces speak plainly; evidence panels keep the verbatim.** Per the
  user's direction, the feed and the callouts are written for a general audience:
  finished sentences, human labels, no `variable_names`, no clause-number strings, no
  mid-word truncation (`trimWords`/`cleanReason` in `web/lib/story.ts`). The honesty
  rule survives the polish — every number in a sentence exists in the payload, and a
  stage with missing data says less, never invents. The compiler's own wording, with
  its thresholds and clause ids, stays one click away in Evidence and Diagnostics.
- **HUD blocks are readouts, never decoration.** Model identity, levels (click to cut
  that plan), verification counts and the takeoff — every number is from the run, and
  a block that cannot cite its field in the payload does not ship.
- **The performance shows all three at once: building, process, judgment.** Opening a
  run (and the Play button) runs the narrated build: assembly slows to ~3 s per layer
  while the rationale feed (`web/lib/story.ts` → `.story-feed`) streams the compiled
  reasoning stage by stage — score, site, structure, envelope, circulation, program,
  verification. Every feed line is a plain-language template filled with payload
  values; a stage with no data says less, never invents. Skip fast-forwards the same
  clock rather than tearing the scene down,
  and `prefers-reduced-motion` lands the finished building with the full feed shown.
  The intended impression is precise: this person designs buildings *and* builds the
  workflow that reasons about them — so the feed must always read as the workflow
  speaking, never as marketing voice-over.
- **anime.js (v4) owns the DOM/SVG motion layer; the r3f clock owns the 3D scene.**
  Never drive scene materials or the assembly from anime — two clocks over one scene
  is how motion starts to stutter. The adopted effects, all bound to real data and
  gated on `prefers-reduced-motion` (`web/lib/motion.ts`): the audio segment lines
  draw themselves on first open (`svg.createDrawable` + `stagger`); the ramp diagram
  draws its checked centre-line and walks a dot along it (`createTimeline` +
  `svg.createMotionPath`, replayable via “Walk the route”); program zones enter once
  per level change in occupancy order (public → circulation → private → service);
  and the ten-dimension score signature decagon tweens between runs (a keyed-object
  value tween — an array target would be read as a target *list*). Every animation
  plays on a meaningful event — first open, a level change, a run change — never on
  incidental re-renders, and every one cancels on cleanup.
- **Switching runs is a comparison, and a comparison holds still.** The stage is not
  remounted per run: the Canvas — and with it the camera — survives the switch, the
  rationale feed closes, and only elements whose key or size changed animate in (a
  fast, unnarrated cascade; `fingerprintRef` in `ArchitectureViewport`). The camera
  fits once per Canvas lifetime and never re-frames on a switch. The full narrated
  performance belongs to the first open and to the Play button, never to a switch.
  The Runs menu always carries a “Frozen demo run” entry so the shipped run stays
  reachable after browsing the library.

**The default view is the building.** Mounting every result does not mean showing every
result at once: the first version of this page put a rail, an inspector and a status bar
around the model and lost the thing the project is arguing for. The shell is a title
bar, a full-bleed model, and one drawer that holds whichever panel was asked for.

- A new report becomes an entry in the `PANELS` list in `web/app/page.tsx`, not a new
  fixed region. Diagnostics — the dependency graph, the artifact hashes, anything a
  reader only opens when something looks wrong — go in the `Diagnostics` group at the
  foot of the menu.
- Panels know nothing about the drawer. `.drawer-body` is a container-query context and
  the two- and three-column layouts collapse from there, so no panel tests its own width.
- The model's own controls stay off the glass: the layer tree is a floating panel, the
  section plane is a dock that appears with it, and neither is on screen unless it was
  asked for.

## Repository roles

- This directory is the new Music-to-Architecture repository.
- The legacy architecture automation repository is read-only source material in the
  sibling directory `../architecture_automation_pipeline`.
- Before reimplementing building generation, Blender execution, structural geometry,
  constructability checks, or pipeline explanation, read
  `docs/legacy_migration.md` and inspect the named legacy module.

## Migration rule

- Migrate files only when the new repository has a concrete caller, schema, test, or
  documented experiment that needs them.
- Do not bulk-copy the legacy repository.
- Do not modify the legacy repository as part of new-project implementation unless
  the user explicitly asks.
- Prefer extracting small, neutral utilities over copying a whole program-specific
  generator.
- Every migrated module must record its legacy source path and the adaptations made.
- Replace absolute paths, hard-coded site/program values, and legacy collection names
  with configuration or adapter boundaries before treating migrated code as reusable.
- Add a smoke test or validation fixture for migrated pure-Python behavior whenever
  Blender is not required.

## Large assets

Do not copy `.3dm`, `.3dmbak`, `.gh`, `.ply`, `.pts`, `.zip`, rendered media, point
clouds, or Blender scene assets unless a named experiment requires a specific file.
Reference those assets in documentation until that need exists.
