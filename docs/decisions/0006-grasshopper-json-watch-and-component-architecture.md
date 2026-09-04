# Decision 0006 — Grasshopper JSON Watch and Component Architecture

- Status: accepted direction; implementation pending
- Date: 2026-08-26
- Decision owner: user
- Career-value tags: V2, V3, V4

## Decision

Grasshopper will receive pipeline data primarily by monitoring a local folder for
versioned JSON contracts. The Grasshopper definition will detect accepted file changes,
parse each contract separately, expose structured data to downstream components, and
regenerate only the affected systems.

The definition must not depend on one Python/C# script component that watches files,
parses every schema, performs all design logic, generates all geometry, validates the
result, and exports it.

The legacy `ProgramDiagram2 1.gh` definition has been inspected as a reference. It
demonstrates a useful visible chain from file path and `Read File` through a bounded
Python parser to separate point/size/color outputs and native geometry/preview
components. Findings and migration cautions are recorded in
`../legacy/grasshopper_program_diagram_reference.md`.

## Intended local contract flow

```text
providers / portable Python core
        ↓ atomic write
local contract workspace
        ↓ watch / poll / hash check
Grasshopper contract readers
        ↓ typed or clearly structured outputs
program / circulation / structure / envelope / interior components
        ↓
validators + provenance display
        ↓ user accepts state
Rhino bake/export + manifest
```

## Proposed workspace boundary

The exact project-relative path will be chosen during scaffolding. The conceptual
layout is:

```text
runtime/
├── inbox/
│   ├── project_brief.json
│   ├── music_features.json
│   ├── architectural_score.json
│   ├── design_directives.json
│   ├── building_model_v2.json
│   ├── facade_host_handoff.json
│   └── pipeline_run_manifest.json
├── reports/
│   ├── input_validation.json
│   ├── architectural_validation.json
│   └── grasshopper_state.json
├── accepted/
│   ├── accepted_state.json
│   ├── geometry_manifest.json
│   └── exports/
└── rejected/
    └── validation artifacts
```

`runtime/` is generated state and should not become the permanent source of project
rules. Schemas, fixtures, and authored configuration belong in version-controlled
directories outside the runtime workspace.

## File-monitoring rules

### Atomic publication

Writers must avoid exposing partially written JSON. The preferred publication pattern
is:

1. write a complete temporary file in the same directory;
2. flush and close it;
3. validate it;
4. rename/replace it atomically as the published contract;
5. optionally update a small manifest last.

Grasshopper should respond only to the published file or manifest.

### Change detection

The watcher/reader layer should track:

- contract path;
- schema version;
- content hash;
- modification time as a secondary signal;
- generation/run ID;
- upstream dependency IDs;
- last successfully accepted version.

Use a short debounce window or stable-file check so multiple related writes do not
trigger an incomplete intermediate solve. Content hash or run ID should decide whether
data changed; modification time alone is insufficient.

### Failure behavior

When a JSON contract is missing, malformed, unsupported, or invalid:

- emit an explicit component error and validation record;
- identify the file, schema, field, and failure reason;
- preserve the last accepted Grasshopper/Rhino state;
- block only dependent downstream branches where practical;
- do not bake, export, or overwrite accepted artifacts;
- allow the corrected file to trigger recovery without restarting the whole pipeline.

## Grasshopper component boundaries

The initial definition should use small components or clusters with one primary
responsibility each.

### Input and contract layer

1. **Workspace Config** — resolves the monitored directory and project/run IDs.
2. **Contract Watcher** — detects stable published changes and emits change events.
3. **Manifest Reader** — reads run/dependency metadata when a manifest is used.
4. **Schema Gate** — checks contract name and supported version.
5. **JSON Reader: Project Brief** — parses only `project_brief`.
6. **JSON Reader: Music Features** — parses only `music_features`.
7. **JSON Reader: Architectural Score** — parses only `architectural_score`.
8. **JSON Reader: Design Directives** — parses only `design_directives`.
9. **JSON Reader: Building Model** — parses only `building_model_v2`.

### Translation layer

10. **Units and Coordinates** — normalizes units, axes, origin, and tolerances.
11. **ID/Provenance Mapper** — carries stable IDs and source-rule references.
12. **Score Segment Mapper** — converts score sections into Grasshopper-friendly data
    trees or typed records.
13. **Typology/Program Mapper** — exposes rooms, areas, categories, adjacency, and
    invariants.
14. **Directive Router** — sends declared parameters only to their owned systems.

### Building-system layer

15. **Program Generator** — creates program volumes/relationships.
16. **Circulation Generator** — creates and evaluates paths and access relationships.
17. **Structure Generator** — interprets the selected tectonic system.
18. **Envelope Generator** — applies the accepted grammar and system constraints.
19. **Interior/Spatial Episode Generator** — handles bounded interior expressions when
    implemented.

### Validation and output layer

20. **Typology Validator**
21. **Spatial Validator**
22. **Tectonic Validator**
23. **Compositional Coherence Validator**
24. **Pipeline State Aggregator** — collects reports without hiding individual results.
25. **Accepted-State Gate** — requires explicit valid/accepted state before baking.
26. **Bake/Export Adapter** — writes Rhino layers, metadata, geometry, and manifest.

This list defines responsibilities, not a requirement for exactly 26 visible boxes.
Related low-level operations may be grouped into readable clusters. Independent
architectural systems and contracts should remain separate.

## Code-component rules

- One script component should have one bounded responsibility.
- Portable parsing, schemas, and rule logic should live in reusable Python modules when
  Grasshopper can import or call them reliably.
- RhinoCommon geometry construction belongs in Grasshopper/Rhino adapters.
- Do not duplicate the same JSON traversal or field-name constants across many nodes;
  use shared readers/models and expose structured outputs.
- Do not hide the entire pipeline in a single cluster with only `Run` and `Geometry`
  outputs.
- Each component should expose meaningful inputs, outputs, status, and error state.
- Keep user-adjustable parameters visible at the architectural-system layer.
- Separate pure transformation from geometry generation and from visualization.
- Avoid implicit cross-node global state; pass run IDs, hashes, and model data through
  declared wires or stable shared services.

## Selective regeneration

Each accepted contract should declare or imply its downstream dependencies.

Example:

```text
music_features
   ↓
architectural_score
   ↓
design_directives
   ├── program
   ├── circulation
   ├── structure
   └── envelope
```

A file change should regenerate only affected branches where practical. The pipeline
must retain enough state metadata to explain:

- which file changed;
- which hash/run ID was accepted;
- which components recomputed;
- which outputs remained stable;
- which validators reran;
- whether the state became accepted or rejected.

This behavior is required evidence for change propagation and failure containment.

## Grasshopper visualization requirements

The definition should make system state readable during interaction:

- current contract versions and run ID;
- source MP3/brief identity;
- score sections and selected segment;
- visible user-adjustable parameters and allowed ranges;
- stable IDs or inspectable metadata for selected elements;
- pass/warning/fail states per validator;
- stale-data warning when the viewport does not reflect the newest published input;
- baseline versus score-conditioned comparison when enabled.

The visualization is part of the evidence and debugging workflow. It should not become
a decorative dashboard that hides the underlying Grasshopper graph.

## Acceptance criteria

The first implementation of this architecture passes when:

1. a valid JSON change is detected without restarting Grasshopper;
2. an unchanged content hash causes no meaningful regeneration;
3. malformed JSON reports a clear error and preserves the last accepted state;
4. an unsupported schema version is rejected explicitly;
5. two contracts can update under one run ID without solving against a mixed state;
6. at least two downstream branches show selective regeneration behavior;
7. generated elements retain stable IDs and source-rule references;
8. baking/export is blocked for an invalid or stale state;
9. the definition remains understandable as separated contract, system, validation,
   and export regions.

## Consequences

- JSON files become the primary application-neutral integration boundary for
  Grasshopper.
- Grasshopper remains interactive while upstream providers and analyzers run outside
  the definition.
- The graph architecture itself becomes evidence of modular workflow design.
- Atomic writes, hashes, run IDs, and last-accepted-state protection are required from
  the first useful watcher prototype.
- A monolithic all-in-one script component is outside the approved architecture.
