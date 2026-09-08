# Closed-loop protocol

## Isolation

Use a new directory below `artifacts/skill_runs/<run-name>/`. Keep downloaded audio in an OS temp directory. Record its source URL, attribution, licence, byte length, and SHA-256 in the run manifest.

Do not use `--fixed-snapshot`, `generate_web_demo`, or `publish_model_version` for an exploratory candidate. They target frozen or promoted evidence surfaces.

## Baseline command

Create a one-track manifest, then run:

```powershell
.venv\Scripts\python.exe -m backend.scripts.run_visual_music_audit `
  --manifest <manifest.json> `
  --output <round-directory> `
  --track <track-id> `
  --review `
  --program-volume `
  --package-native `
  --rhino
```

The output must stay beneath the repository root. This form is the Program Volume
closed loop: the score chooses the volume grammar, the native Blend stays under
`<round-directory>/native/`, and Rhino output remains an unaccepted candidate. Omit
`--program-volume` only when the task explicitly asks for the parallel legacy v3 path.

## Diversity preflight

When the claim concerns diversity across recordings, compare form before paying for
full model, drawing, Blender, and Rhino exports:

1. Choose at least four licence-verified recordings with contrasting score readings.
2. Hold typology constant so a brief change cannot masquerade as form variation.
3. Run `backend.scripts.run_program_volume_study` for every recording and each legal
   Program Volume grammar, without `--compile`.
4. Run `backend.scripts.evaluate_program_volume_diversity` with every `study.json`.
5. Inspect raw topology/digest collisions and normalized-shape collisions separately.

The evaluator normalizes every candidate's complete XY envelope to a unit square before
comparing corresponding level unions. Translation and independent global X/Y scaling
therefore cannot produce a diversity claim. It reports measurements and exact/tolerance
collisions without a corpus-tuned aesthetic threshold.

Any normalized collision blocks a stable form-diversity claim for that tested grammar.
Treat it as a missing score-to-form control surface, repair the generator through lattice
indices, rerun the preflight, and preserve the measurement-only authority of the report.
Only candidates that clear this screen should enter a multi-track native closed loop.

For a controlled v3 comparison that retains the real pipeline and run contract, use:

```powershell
.venv\Scripts\python.exe .agents\skills\mta-design-director\scripts\run_pinned_music_candidate.py `
  --manifest <manifest.json> `
  --output <round-directory> `
  --track <track-id> `
  --massing <massing-id> `
  --typology <library|theater|museum> `
  --review
```

The wrapper applies runtime pins only to v3, restores the original entry point, and leaves v2 score-driven. Its `candidate_control.json` records that split. Do not use it against fixed snapshots or as a publication path.

## Machine gate

Require all of the following for a candidate:

- `result.json.status == "compiled"`;
- `result.json.source_unchanged == true`;
- v3 model JSON, GLB, GLB manifest, native Blend, response, and review manifest exist;
- a Program Volume run reports `v3_mode == "program_volume"`, preserves its first-class
  volume contract, and exposes its native `Program_Volumes` scene collection;
- A-4xx detail sheets carry model-projected detail audits and separate
  `drawing_status` from `d3_status`;
- evidence files match the hashes in `result.json`;
- the review manifest is bound to the same run ID and reports `rendered_pending_visual_review` before judgment;
- program allocation, circulation, geometry, facade, structure, and compliance rollups are reported without status inflation.

Treat `fail`, `unknown`, `provisionally_excluded`, and `unevaluated` as distinct outcomes. A candidate can be presentation-ready while still requiring professional review; state both.
`ready_with_limitations` is the highest student-detail result; it never means accepted
Rhino geometry or construction documentation.

## Review views

Inspect every generated PNG at original resolution. Use the same rubric for both rounds, on a 1–5 scale:

1. silhouette and massing coherence;
2. entry and public approach legibility;
3. spatial/program hierarchy;
4. circulation legibility and continuity;
5. structure, envelope, and opening agreement;
6. facade rhythm and depth;
7. presentation clarity.

Record blocking observations separately from preferences. A visual score never cancels a machine failure.

## Iteration policy

Change one architectural decision family per round. First use existing structured overrides or candidate entry points. Keep the audio-derived score and provenance unchanged so the comparison isolates the intervention.

If no supported override can address the finding, retain the baseline and record the missing control surface. Do not patch emitted coordinates or presentation files.

## Candidate-ready decision

Select a revision only when:

- every baseline hard gate remains at least as strong;
- the named visual blocker is measurably reduced in matched views;
- no new program, circulation, geometry, or coordination blocker appears;
- all remaining professional checks are listed verbatim from the source reports.

Write `report.md` and `decision.json` in the run root. The decision should name the selected round and link to immutable evidence paths; it must not claim accepted geometry, code compliance, safety, permit readiness, or fabrication readiness.
