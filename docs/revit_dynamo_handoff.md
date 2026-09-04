# Revit/Dynamo handoff guide

This guide turns the proposed boundary in
[Decision 0011](decisions/0011-revit-dynamo-bim-handoff.md) into a build-and-test plan.
The current deliverable is a validated handoff contract. A `.dyn` graph and tested
`.rvt` are the next evidence stage.

## What the prototype proves

The handoff is designed to prove one bounded professional claim:

> The design compiler can hand a traceable element model to BIM, preserve identity
> across regeneration, distinguish native elements from geometric fallbacks, and make
> conflicts or unresolved decisions visible to a person.

It does not prove construction readiness, model-authoring standards for a particular
firm, fabrication detail, permit compliance, or a complete Revit family library.

## Package to consume

Use one frozen pipeline run, not loose files from different runs.

| Input | Purpose |
|---|---|
| `analysis` / `BuildingModelV3` | Element groups, instances, geometry, levels, IDs, provenance, status |
| `pipeline_manifest` | Run ID, artifact hashes, authority, blockers |
| `docs/contracts/revit_dynamo_mapping.v1.json` | Categories, delivery strategies, shared parameter GUIDs |
| source-to-Revit transform | Origin, rotation, translation, and level relationship |
| reviewed family/type table | Revit family/type choices that the portable compiler cannot own |
| previous binding index | Source IDs, Revit `UniqueId` values, and last-synced fingerprints |

The frozen browser demo contains a real schema 3.0 `analysis` payload in
`web/public/reports/demo_run.json`. For a first graph, extract that object and pair it
with the same run's `pipeline_manifest`.

## Dry-run first

Every execution has a read-only planning phase. It must finish before a Revit
transaction starts.

```text
read package
  → validate versions and hashes
  → expand element groups in memory
  → reject duplicate MTA IDs
  → apply the category strategy
  → resolve transform, levels, families, and types
  → compare with the binding index
  → write operation plan and blockers
  → require user confirmation for a write run
```

The operation plan uses seven outcomes:

| Outcome | Meaning | Default action |
|---|---|---|
| `create` | New source ID | Create after mapping gates pass |
| `update` | Source changed; tracked Revit state did not | Update the bound element |
| `keep` | Source and host state are unchanged | Leave the element untouched |
| `preserve_host_edit` | Only the host state changed | Keep Revit edit and report it |
| `review_conflict` | Source and host both changed | Do not overwrite |
| `retire` | Bound source ID no longer exists | Mark for review; do not delete |
| `review` | Mapping or geometry is unresolved | Do not create a misleading element |

## Suggested graph layout

Keep each group small enough to inspect in Dynamo Player or the Dynamo workspace.

| Group | Inputs | Outputs | Writes Revit? |
|---|---|---|---|
| 01 Package | package folder | parsed JSON, hashes | no |
| 02 Preflight | JSON + target document | blockers, transform, level map | no |
| 03 Mapping | elements + registry | delivery plans | no |
| 04 Binding | document + `MTA_ElementId` | current bindings and host fingerprints | no |
| 05 Diff | source + bindings | operation plan | no |
| 06 Native | approved native plans | Revit elements | yes |
| 07 Fallback | approved preview plans | DirectShape elements | yes |
| 08 Metadata | created/updated elements | parameters and compact storage | yes |
| 09 Reconcile | plan + document | binding index, JSON report, schedules | no |

Groups 06–08 run inside one transaction group. Any blocking failure rolls back the
whole write run. Non-blocking review items stay in the report and do not silently
change category, family, type, or geometry.

## Source geometry translation

| Schema 3.0 primitive | Revit translation candidate | Required review |
|---|---|---|
| `member` | Structural framing/column family instance or DirectShape sweep | Profile catalogue match, roll, analytical intent, end joins |
| `extrusion` | Floor, roof, wall, shaft, or DirectShape solid | Sketch validity, openings, compound structure, level/offset |
| `quad` | Curtain panel, wall-hosted panel, or DirectShape face/solid | Thickness, host, orientation, panel type |
| `box` | Room/program proxy, family instance, or DirectShape solid | Semantic category and whether a native host exists |

`position` and `dimensions` are derived compatibility fields. Translation must use the
tagged `geometry` record as its geometric authority.

## Native BIM gate

A mapping marked `native_candidate` still requires all of these:

- source kind matches the intended Revit category;
- level and offsets resolve;
- geometry is representable without silent simplification;
- family and type are explicitly selected;
- section/material catalogue match is recorded;
- required host exists for hosted elements;
- source and target parameters have declared ownership;
- failures can be reported per source ID.

If a gate fails, use `review`. DirectShape may be selected only when a coordination
preview is useful and its non-native status is visible.

## Parameter use

The mapping registry separates two data layers:

- Shared parameters: compact, visible fields for filtering, schedules, tags, identity,
  sync status, and review.
- Sidecar/Extensible Storage: long provenance lists, fingerprints, relation edges, and
  adapter diagnostics.

Do not create one shared parameter per score dimension or dependency relation. Keep
the visible model legible and retain the full source in the versioned JSON package.

Minimum schedules for the live proof:

1. **MTA Sync Status** — element ID, kind, category, delivery status, run ID, validation.
2. **MTA Review Queue** — unresolved mapping, conflict, retirement, or fallback reason.
3. **MTA Structural Provenance** — section, sizing status, utilisation, governing check.

## Family/type mapping worksheet

The machine registry selects a category strategy. A human-owned table resolves actual
families and types:

| Source kind | Source section/material | Revit category | Family | Type | Status | Reviewer |
|---|---|---|---|---|---|---|
| `column` | example: `GL28h 240x1200` / timber | Structural Columns | TBD | TBD | unresolved | — |
| `primary_beam` | source `section_id` | Structural Framing | TBD | TBD | unresolved | — |
| `floor_slab` | concrete | Floors | TBD | TBD | unresolved | — |
| `glazing_panel` | glass + `thickness_m` | Curtain Panels | TBD | TBD | unresolved | — |
| `partition` | assembly from partition selector | Walls | TBD | TBD | unresolved | — |

Unresolved rows are expected in the first proof. They must remain visible and cannot be
replaced by a plausible family name invented by the adapter.

## First validation experiment

Use one small accepted or frozen model subset: two levels, one structural bay, one
facade bay, one partition/door pair, and one program zone. Keep the full run hash in the
evidence record.

### Run A — first import

- preflight passes;
- approved source IDs create exactly one target each;
- unsupported objects enter `review` or labeled DirectShape preview;
- binding index records Revit `UniqueId` and fingerprints.

### Run B — unchanged rerun

- zero new elements;
- all prior elements resolve by `MTA_ElementId`;
- operation plan is `keep` except explicit review items;
- tags/schedules attached after Run A remain attached.

### Run C — controlled source change

- change one score-driven datum or one frozen element in a copied fixture;
- only declared downstream elements update;
- stable IDs keep their Revit bindings;
- reconciliation lists exactly what changed and why.

### Run D — conflict and retirement

- manually edit one tracked Revit-controlled value;
- change the same source element and confirm `review_conflict`;
- remove another source ID and confirm `retire` without deletion;
- reject the run and confirm the prior committed state remains intact.

## Evidence folder when the live run exists

Create one named folder under `artifacts/evidence/` containing:

- `README.md` with versions, scope, source hash, procedure, and limitations;
- frozen source model or repository-relative reference;
- mapping registry hash and family/type worksheet;
- dry-run and committed reconciliation JSON;
- binding index with no personal/project path data;
- screenshots of the three schedules and one model view;
- Dynamo graph hash and package dependency list;
- rerun, change, conflict, retirement, and rollback results.

Only then add “Revit/Dynamo integration verified” to the evidence matrix.

## Portfolio wording

Current truthful wording:

> Defined and automatically checked a Revit/Dynamo handoff contract for 70 generated
> element kinds, including stable cross-tool identity, native-versus-DirectShape
> strategy, parameter GUIDs, conservative update/delete semantics, and a repeatable
> validation plan. Live Revit graph validation remains pending.

After the experiment passes:

> Built and tested a repeatable design-to-BIM handoff that preserves element identity
> across reruns, updates changed elements without duplication, surfaces host/source
> conflicts, and reports non-native or unresolved content for human review.

