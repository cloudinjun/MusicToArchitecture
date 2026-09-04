# Legacy Pipeline Migration Guide

## Purpose

This repository is the new Music-to-Architecture project. The existing architecture
automation pipeline is a donor repository, not a dependency to mirror wholesale.

All migration decisions must also pass the career-value filter in
`../PROJECT_CHARTER.md`. A reusable legacy capability is valuable here only when it
helps formalize intent, coordinate systems, improve workflow reliability, or evaluate
results.

Program and structural constraint assumptions identified for MVP reference are listed
in `decisions/0004-project-brief-program-and-mp3-score-contract.md`. They must be
re-scoped and moved into data/configuration before reuse.

Legacy repository (expected as a sibling directory):

```text
../architecture_automation_pipeline
```

The migration strategy is demand-driven: copy or extract a legacy capability only
after a new schema, caller, experiment, or test establishes why it is needed.

## Intended system boundary

```text
music / architectural analysis
        ↓
architectural_score.json
        ↓
design_directives.json
        ↓
new building compiler
        ↓
building_model_v2.json
        ↓
legacy compatibility adapter
        ↓
volumeMassing-compatible data
        ↓
selected Blender execution modules
```

The new repository owns score extraction, typology/program schemas, style grammar,
design directives, building compilation, coherence evaluation, and compatibility
adapters. The legacy repository remains the reference implementation for selected
downstream execution and explanation capabilities.

## Migration queue

### Tier 1 — inspect or migrate first when a caller exists

| Capability | Legacy source | Suggested new destination | Migration condition |
|---|---|---|---|
| Grasshopper external-file program preview | `ProgramDiagram2 1.gh` | Reference via `docs/legacy/grasshopper_program_diagram_reference.md`; rebuild as modular JSON readers | When implementing the first Grasshopper contract reader and preview |
| Blender execution rules | `Blender/blender_agent_rules.md` | `docs/blender/execution_contract.md` | Before the first Blender automation module is added |
| Pipeline contracts and ownership | `Blender/LOGIC.md` | `docs/legacy/blender_pipeline_contracts.md` | When defining adapters or Blender collection ownership |
| Legacy building data fixture | `program_generator/fileTransfer/volumeMassing.json` | `fixtures/legacy/volume_massing_v1.json` | When the backward-compatible adapter test is written |
| Massing importer/renderer | `Blender/volume_massing_generator.py` | `src/music_to_architecture/blender/massing.py` | After `building_model_v2` and its v1 adapter exist |
| Structural utilities | `Blender/structural_generator.py` | `src/music_to_architecture/structure/` and `src/music_to_architecture/blender/structure.py` | After pure analysis is separated from Blender rendering |
| Process explainer | `Blender/pipeline_explainer.py` | `src/music_to_architecture/explainer/stages.py` | After stage registry and score-derived stages are specified |
| Explainer playback | `Blender/pipeline_explainer_playback.py` | `src/music_to_architecture/explainer/playback.py` | When a real explainer artifact exists |

### Tier 2 — conditional, later-stage migration

| Capability | Legacy source | Use only when |
|---|---|---|
| Facade panelization | `Blender/facade_panelizer.py` | The selected envelope remains compatible with the UHPC rainscreen workflow |
| Facade substructure | `Blender/substructure.py` | The same UHPC/SSG load-path assumptions remain relevant |
| Spatial relaxation ideas | `program_generator/EllipseAgent.py` | A generic deterministic layout solver is being implemented from `program_graph` data |
| Interior primitives | `Blender/interior_generator.py` | A specific room/interior prototype needs a verified primitive utility |

### Tier 3 — reference only; do not copy as defaults

| Legacy source | Reason |
|---|---|
| `program_generator/OpenAI_ProgramDetails.py` | Hard-coded for the wearable scanning/fabrication building and site |
| `Blender/facade_generator.py` and variants | Strong Computational Gothic/trabecular language would predetermine the new project's style |
| `Blender/ToBlender.py` | Legacy transfer glue and path assumptions should be replaced by explicit adapters |
| Old circle/ellipse packing entry scripts | Program relationships and runtime modes are embedded in implementation |

## Required procedure for every migrated file

1. Identify the concrete new-project caller, experiment, or test.
2. Re-read the legacy file and its relevant contract in `Blender/LOGIC.md`.
3. Copy the smallest coherent unit; extract neutral helpers where practical.
4. Add a provenance header or module docstring containing:
   - legacy repository path;
   - legacy relative file path;
   - migration date;
   - behavior retained;
   - behavior intentionally removed or changed.
5. Remove absolute paths and program/site-specific constants.
6. Separate pure data/analysis logic from `bpy` rendering wherever possible.
7. Replace implicit globals and collection names with configuration or adapter input.
8. Add validation for stable IDs, units, schema version, and deterministic seed where relevant.
9. Add a pure-Python test or a documented Blender smoke test.
10. Update the migration log below.

## Migration log

| Date | New file | Legacy source | Adaptation | Verification |
|---|---|---|---|---|
| 2026-08-26 | `AGENTS.md`, `docs/legacy_migration.md` | Repository survey | Established demand-driven migration policy; no legacy code copied yet | Confirmed candidate paths exist in the legacy repository |
| 2026-08-26 | `docs/legacy/grasshopper_program_diagram_reference.md` | `ProgramDiagram2 1.gh` | Read-only structural inspection; documented file-reader, parser, geometry, and preview pattern | Loaded with Rhino 8; confirmed 13 Grasshopper objects and component connections |
| 2026-08-26 | `grasshopper/MusicToArchitecture_MVP.gh` | `ProgramDiagram2 1.gh` (reference only) | Original five-component definition; retained external JSON observation and modular separation, replaced legacy program parsing and geometry with schema-v2 score-aware massing/frame/validation | Rhino 8 GH solve: 5 massing Breps, 12 frame Breps, validation pass, 17/17 provenance |
| 2026-08-26 | `blender/import_building_model.py` | `Blender/blender_agent_rules.md`, `Blender/LOGIC.md`, `Blender/volume_massing_generator.py` (reference only) | Original schema-v2 importer; retained explicit collections, centered box primitive, metadata, scene-state export, object budget, and headless safety; removed legacy floor/category/site assumptions and absolute input path | Blender 5.0.1 headless generation, render, reopen, and 18-mesh/17-provenance validation |
| 2026-08-27 | `backend/app/models.py`, `backend/app/compiler.py`, `blender/import_building_model.py` | `program_generator/fileTransfer/volumeMassing.json`, `Blender/volume_massing_generator.py` (reference only) | Retained the visible `public`/`private`/`circulation` category contract and category-massing concept; replaced legacy site, floor, program, color, and path assumptions with schema-v2 assignments, current palette, stable provenance, and an export-only program layer | Pytest category coverage; Blender 5.0.1 headless export of 5 program masses; GLB extras inspection found 3 public, 1 private, and 1 circulation object |
| 2026-08-27 | `docs/guidelines/program_constitution_guideline.md` | `program_generator/OpenAI_ProgramDetails.py`, `fileTransfer/ProgramFormat.txt`, `RoughProgram.txt`, `output.txt`, `ProgramDeveloperEllipseBoundary.py`, `EllipseAgent.py` (read-only reference) | Extracted detailed room types, support-space completeness, category/type separation, adjacency, boundary, overlap, and vertical-alignment concepts; converted embedded names, dimensions, site, core, and stair assumptions into scoped data rules and a jurisdiction code-profile gate | Manual source-to-guideline trace recorded in the guideline; no legacy code or coordinates copied |
| 2026-08-27 | `docs/guidelines/structural_system_guideline.md` | `Blender/structural_generator.py`, `Blender/clt_building_generator.py`, `Blender/LOGIC.md` (read-only reference) | Extracted core-anchored topology, support continuity, column-exclusion negotiation, transfer/perimeter repair, footprint coordination, lateral roles, and element-reason metadata; replaced fixed frame/CLT values and inconsistent material descriptions with system-specific profiles, load-path contracts, and a jurisdiction code gate | Manual source-to-guideline trace recorded in the guideline; identified fixed 6 m/12 m/member sizes and core/material conflicts as nonportable heuristics |

## First recommended implementation slice

The first code migration should happen only after these new-project artifacts exist:

1. `architectural_score` schema;
2. `building_model_v2` schema;
3. a v2-to-legacy `volumeMassing` adapter;
4. a compatibility test using the legacy JSON fixture.

At that point, migrate `volume_massing_generator.py` behind a narrow Blender adapter.
Next, extract structural analysis utilities from `structural_generator.py`. Delay facade,
panelization, substructure, interior, and playback until massing and structure can show
score-derived variation while passing architectural constraints.

## Current repository state

As of 2026-08-27, the new repository contains a FastAPI compiler, a web viewer,
schema-v2 fixtures, an original modular Grasshopper definition, a verified Rhino
model, and an original Blender importer/render scene with category-aware program
massing. The folder does not yet contain Git metadata. Legacy-v1 compatibility and the
transfer-typology experiment remain pending, so related destinations in the queue are
still provisional.
