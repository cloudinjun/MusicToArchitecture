# Decision 0011 — Revit/Dynamo BIM handoff boundary

- Status: proposed; documentation and mapping contract implemented, live Revit validation pending
- Date: 2026-09-02
- Decision owner: user
- Career-value tags: V2, V3, V4

## Decision

Revit/Dynamo is a downstream BIM translation route for an explicitly accepted design
state. It consumes schema 3.0 element identity, geometry, provenance, and validation
status without re-running music interpretation or replacing the portable compiler.

The first route is deliberately bounded:

```text
schema 3.0 building model + pipeline run manifest
                    ↓ preflight
machine-readable Revit mapping contract
                    ↓ plan only
create / update / keep / retire / review operations
                    ↓ human review gate
Dynamo/Revit transaction group
                    ↓
native BIM candidates + labeled DirectShape fallbacks
                    ↓
binding index + reconciliation report
```

The route prepares a coordination/documentation model. It does not claim construction
readiness, permit compliance, fabrication resolution, or verified family selection.

## Why this boundary exists

Design geometry and BIM elements fail at different seams. The handoff must address the
following before a live graph is credible:

| Handoff failure | Project response |
|---|---|
| A rerun duplicates elements or breaks tags and dimensions | Match by stable `MTA_ElementId`; keep Revit `UniqueId` only as the host-side binding |
| Generic solids look complete but carry no BIM behavior | Prefer reviewed native categories; label every DirectShape fallback |
| Revit IDs are mistaken for source identity | Store both source ID and Revit `UniqueId`; never persist `ElementId` as the cross-run key |
| Metres/Z-up/model origin are silently reinterpreted | Require an explicit transform and convert units at the adapter boundary |
| Deleted source elements disappear from Revit without review | Produce `retire`; hard deletion is a separate human-approved action |
| A designer edits an imported element while the source also changes | Produce `review_conflict`; preserve both states until resolved |
| Shared parameters drift between files | Keep stable parameter GUIDs in the repository-owned mapping registry |
| One failed element leaves a partial run committed | Plan first, then write inside a transaction group; roll back on blocking failures |

## Authority model

| Record | Authority |
|---|---|
| Shared Score, datums, rules, and element IDs | Portable compiler |
| Accepted design geometry | Rhino acceptance route defined by Decisions 0005 and 0007 |
| Revit family/type choice and native BIM semantics | Human-reviewed Revit adapter |
| Source-to-Revit binding index | Revit handoff manifest plus Revit `UniqueId` |
| Tags, schedules, sheets, and construction-document annotations | Revit document |
| Compliance or engineering approval | Named professional review outside this prototype |

Importing an element cannot raise its authority. A Revit element remains
`professional_review_required` when its source record has that status. DirectShape
output is a coordination fallback and never evidence of native BIM completion.

## Source contract

The route reads `BuildingModelV3` from the `analysis` view of a pipeline run. Schema 3.0
continues to run in parallel with v2 and does not replace the Grasshopper/Rhino
acceptance chain.

Required source fields are:

- model identity, schema version, units, and coordinate system;
- grouped element descriptions and per-instance stable IDs;
- tagged geometry (`box`, `member`, `extrusion`, or `quad`);
- levels, lattice indices, datum references, rule references, and program ownership;
- section, sizing, governing-check, and validation status where applicable;
- run identity and source artifact hash from the pipeline manifest.

The adapter must reject an unknown schema version, unknown geometry primitive,
duplicate source ID, unresolved required level, non-finite coordinate, or absent project
transform before opening a Revit write transaction.

## Identity and synchronization

`ElementV3.id` becomes the external key in `MTA_ElementId`. It must not be replaced by
Revit `ElementId`. Autodesk documents `UniqueId` as the stable host identifier across
upgrades and worksharing operations, while `ElementId` is project-local and can change.

Each successful sync records:

- `MTA_ElementId` → Revit `UniqueId`;
- source element fingerprint;
- Revit-controlled fingerprint at sync time;
- source model hash and run ID;
- mapping-rule ID and delivery status;
- sync outcome and unresolved review items.

The planner compares the new source set with that binding index:

| Condition | Operation |
|---|---|
| Source ID has no binding | `create` |
| Source and Revit-controlled fields match their last-synced state | `keep` |
| Source changed and Revit-controlled fields did not | `update` |
| Source did not change and Revit-controlled fields changed | `preserve_host_edit` |
| Both changed | `review_conflict` |
| Binding exists and source ID is absent | `retire` |
| Category, family, type, level, or geometry cannot be resolved | `review` |

`retire` never means automatic deletion in the first implementation. The graph places
the element in a review set and produces a report. A later user-approved cleanup action
may delete confirmed retirements.

## Native element and DirectShape policy

The repository mapping contract assigns every one of the 70 current `ElementKind`
values one delivery strategy.

- `native_candidate`: use a reviewed Revit category and family/type mapping when the
  source geometry and semantics can be represented without distortion.
- `room_candidate`: create only after native room-bounding geometry and level mapping
  pass; otherwise retain the program record as data.
- `direct_shape_preview`: use DirectShape for coordination geometry and attach the full
  identity/status parameter set.
- `omit_presentation_only`: do not import presentation context such as scale figures.

DirectShape is not a universal fallback. The adapter must call Revit geometry/category
validation, record `MTA_DeliveryStatus=directshape_fallback`, and keep the object out of
native-completion metrics.

## Parameters and detailed provenance

The small set needed for schedules, filters, tags, and audit is stored as shared
instance parameters with stable GUIDs. The registry is
[`../contracts/revit_dynamo_mapping.v1.json`](../contracts/revit_dynamo_mapping.v1.json).

Long lists and structured data stay in the sidecar manifest or Extensible Storage:
`datum_refs`, `rule_refs`, dependency edges, reason text, and full source fingerprints.
This keeps interactive parameters legible and avoids filling the Revit database with
large duplicated payloads.

## Coordinate and unit policy

Schema 3.0 is metres in a right-handed, Z-up coordinate system. The adapter must:

1. validate those declarations;
2. read an explicit source-to-Revit transform;
3. convert every length with Revit `UnitUtils` at the API boundary;
4. resolve source levels to named Revit levels before element creation;
5. report the source origin, Revit origin, north rotation, and translation in the
   reconciliation report.

Identity transform is allowed only when preflight confirms the selected project
template uses the same origin and orientation.

## Dynamo graph responsibilities

The graph is split into inspectable groups:

1. Select package and target document.
2. Validate schema, hashes, units, transform, and duplicate IDs.
3. Load parameter and category mapping.
4. Read existing bindings by `MTA_ElementId` and Revit `UniqueId`.
5. Produce a dry-run operation plan.
6. Resolve levels, families, types, and materials.
7. Create or update native candidates.
8. Create or update labeled DirectShape previews.
9. Apply shared parameters and compact Extensible Storage records.
10. Reconcile counts, identities, failures, conflicts, and retirements.
11. Commit only after the blocking gates pass.

Dynamo trace may assist element rebinding, but source identity remains the portable key.
The graph must not inspect or edit serialized trace data directly.

## Acceptance gate for the first live proof

The first Revit/Dynamo run is accepted as portfolio evidence only when all of these are
recorded:

- exact Revit, Dynamo, package, template, and operating-system versions;
- one fixed schema 3.0 source model and SHA-256 hash;
- zero duplicate `MTA_ElementId` values;
- 100% mapping-strategy coverage across emitted kinds;
- create/update/keep/retire/review counts before and after two consecutive runs;
- unchanged rerun creates zero new elements;
- one controlled source change updates the intended element set;
- one host edit plus source edit produces a visible conflict;
- one removed source element becomes `retire` and remains recoverable;
- all DirectShape fallbacks and unresolved family/type mappings are listed;
- a failed blocking case rolls back without leaving a partial run;
- screenshots of schedules/filters plus the reconciliation JSON.

Until that experiment exists, project language must say “Revit/Dynamo handoff contract
and test plan prepared,” not “Revit integration completed.”

## Official implementation references

- [Revit `Element.UniqueId`](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/f9a9cb77-6913-6d41-ecf5-4398a24e8ff8.htm)
- [Revit shared parameters](https://help.autodesk.com/cloudhelp/2024/ENU/Revit-API/files/Revit_API_Developers_Guide/Basic_Interaction_with_Revit_Elements/Parameters/Revit_API_Revit_API_Developers_Guide_Basic_Interaction_with_Revit_Elements_Parameters_Shared_Parameters_html.html)
- [Revit Extensible Storage](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/79486a74-376c-9555-c873-45d5a750f051.htm)
- [Revit `UnitUtils`](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/128dd879-fea8-5d7b-1eb2-d64f87753990.htm)
- [Revit `DirectShape`](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/bfbd137b-c2c2-71bb-6f4a-992d0dcf6ea8.htm)
- [Revit `TransactionGroup`](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/f1113d30-4c36-7844-1537-aad7f095cea0.htm)
- [Dynamo integration, trace, and element binding](https://primer2.dynamobim.org/1_developer_primer_intro/3_developing_for_dynamo/13-dynamo-integration)

These links establish API behavior. The first live proof must replace the documentation
baseline with the versions actually installed and tested.

## Consequences

- The project gains a credible BIM boundary without claiming a finished Revit add-in.
- Stable source identity and conservative update semantics protect downstream BIM work.
- Native semantics, human review, and fallback geometry remain distinguishable.
- A future Dynamo graph or Revit add-in can consume the same mapping registry.
- Construction-detail, code, family-library, and worksharing claims remain out of scope
  until separately verified.

