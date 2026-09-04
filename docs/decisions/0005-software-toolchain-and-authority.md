# Decision 0005 — Software Toolchain and Authority

- Status: accepted; web-preview interchange implemented, Rhino acceptance route pending
- Date: 2026-08-26
- Decision owner: user
- Career-value tags: V2, V3, V4

## Decision

The project may use Rhino/Grasshopper and Blender together.

- **Grasshopper** is the primary interactive computational-design environment and the
  main surface for real-time parameter adjustment and visual feedback.
- **Rhino** is the geometry host for Grasshopper, accepted-geometry baking, inspection,
  architectural drawings, and design-model export.
- **Blender** is the primary rendering and animation environment, a host for the
  process explainer, and a downstream/backup execution environment for selected legacy
  capabilities.
- **Pure Python** owns portable schemas, normalization, feature processing, rule
  evaluation, provenance, and validators that do not require RhinoCommon or `bpy`.

## Authority model

The project needs one shared design record so each application does not reinterpret
music or regenerate independent design logic.

```text
project_brief.json
music_features.json
architectural_score.json
design_directives.json
        ↓
portable compiler / validators
        ↓
building_model_v2.json
        ↓
Grasshopper interactive geometry + validation display
        ↓ accepted export
Rhino baked model / drawings
        ↓ presentation handoff
Blender render / animation / explainer
```

### Source-of-truth responsibilities

| Concern | Authority |
|---|---|
| Project requirements | Normalized `project_brief` contract |
| MP3-derived observations | `music_features` contract with confidence and provenance |
| Shared compositional interpretation | `architectural_score` and `design_directives` |
| Program, element identity, constraints, and accepted parameters | `building_model_v2` |
| Interactive design geometry | Grasshopper definition hosted in Rhino |
| Accepted architectural geometry | Baked/exported Rhino model plus matching model manifest |
| Render appearance, cameras, animation, and presentation staging | Blender scene |
| Validation truth | Versioned validation reports, not viewport appearance |

Per-run stage status, artifact hashes, blockers, and the single Rhino accepted-state
record are coordinated by
[`0007-integrated-pipeline-run-and-acceptance-contract.md`](./0007-integrated-pipeline-run-and-acceptance-contract.md).
An application import or render cannot increase the authority recorded there.

Blender may add presentation materials, lighting, cameras, animation, and non-authority
explainer geometry. It should not silently change accepted program, structure, IDs, or
score mappings.

Presentation-only site context may include deterministic paving, planting, vehicles,
and human scale figures. These objects must use a separate semantic layer and stable
context IDs, remain absent from the accepted building-element contract, and carry no
claim of resolved landscape, traffic, accessibility, or site-code design.

For the web MVP, Blender may also derive schematic facade and secondary-structure
preview geometry directly from `building_model_v2`. Every such object must declare
`mta:derived_from`, system ownership, and a manifest entry. This geometry supports
coordination and section inspection; it does not become accepted architectural
geometry until it passes through the Grasshopper/Rhino acceptance route.

## Grasshopper responsibilities

Grasshopper should provide:

- real-time or near-real-time control of design parameters;
- visible program, circulation, structural, and facade/interior representations;
- parameter limits derived from schemas and constraints;
- score timeline/segment selection when useful;
- immediate pass/warning/fail feedback;
- comparison among baseline and score-conditioned states;
- controlled baking/export of an accepted state;
- stable IDs and provenance attached to exported elements where the format permits.

The Grasshopper definition should be data-driven. Repeated operations should use
clusters, Hops/components, scripts, or reusable builders instead of large duplicated
wiring regions.

Grasshopper receives application-neutral inputs by monitoring a local workspace of
versioned JSON contracts. File watching, parsing, system generation, validation, and
export must remain modular. The full component rules are defined in
`0006-grasshopper-json-watch-and-component-architecture.md`.

## Rhino responsibilities

Rhino should provide:

- geometric inspection and manual review;
- accepted-state baking into deterministic layers/groups;
- units, coordinates, layer names, object IDs, and user-text metadata;
- plans, sections, elevations, and fabrication-oriented geometry when required;
- versioned design-model exports for Blender and portfolio production.

Manual Rhino edits that affect design authority must either return to the compiler/
Grasshopper inputs or be recorded as explicit human overrides. Invisible downstream
edits cannot become the only copy of a design decision.

## Blender responsibilities

Blender should provide:

- high-quality rendering and material/lighting studies;
- architectural and process animation;
- non-destructive pipeline explanation views;
- comparison and presentation staging;
- optional downstream constructability or geometry utilities migrated from the legacy
  repository;
- a backup execution route when a bounded module is better suited to `bpy`.

Any Blender-side design-affecting module must consume the same IDs, accepted parameters,
and provenance contracts. Its output must return a report or artifact manifest to the
shared pipeline.

## Portable core and application adapters

Keep portable logic separate from application APIs:

```text
src/core/                 schemas, models, rules, validators, provenance
src/providers/            random brief, Ollama brief, MP3 analysis
src/adapters/grasshopper/ RhinoCommon/Grasshopper integration
src/adapters/blender/     bpy integration
```

This is a conceptual boundary. The exact package layout will be decided when the
repository scaffold is created.

Pure rules should accept plain data and return plain data plus validation reports.
RhinoCommon and `bpy` imports should remain inside their respective adapters whenever
possible.

## MVP synchronization strategy

Use two explicit, versioned file routes:

### Interactive acceptance route

1. Grasshopper loads the normalized contracts.
2. Grasshopper generates and previews geometry and validation state.
3. The user accepts a state.
4. Rhino bakes/exports geometry with a matching manifest.
5. Blender imports the accepted artifact for rendering or explanation.

### Web inspection route

1. The portable compiler publishes `building_model_v2`.
2. The Blender adapter preserves source objects and derives schematic facade, beams,
   slabs, supplemental columns, and foundations.
3. Blender writes `.blend`, GLB, scene-state, and manifest artifacts.
4. The browser reads GLB semantic extras for system isolation and clipping-plane review.

The second route is a preview/inspection path. Its derived geometry stays visibly
separate from accepted Rhino geometry.

A live Rhino–Blender bridge is optional future work. File-based handoff provides a
clearer audit trail and failure boundary for the first complete version.

## Pending interchange decisions

Before the first Rhino-to-Blender handoff, define:

- Rhino and Blender versions;
- project units and world coordinate convention;
- stable element-ID format;
- baked layer/group naming;
- geometry export format or formats;
- metadata sidecar/manifest format;
- curve, NURBS, mesh, material, and instance conversion policy;
- accepted-state folder/version naming;
- round-trip policy for Blender-generated design-affecting results.

## Consequences

- Grasshopper receives priority for interactive design development.
- Blender remains valuable without becoming a competing source of design truth.
- The shared contracts and portable Python core demonstrate cross-tool workflow design.
- File-based accepted-state handoff is the default MVP path.
- Real-time audio-to-geometry playback and live Rhino–Blender synchronization are
  deferred until deterministic generation, validation, and provenance are working.
