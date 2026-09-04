# Decision 0007 — Integrated Pipeline Run and Acceptance Contract

- Status: accepted integration spine implemented; selection-dependent facade geometry remains blocked
- Date: 2026-08-27
- Decision owner: user
- Career-value tags: V1, V2, V3, V4

## Decision

One run is coordinated by a repository-owned `pipeline_run_manifest`. It records every
stage, input/output artifact, content hash, authority, blocker, limitation, and Rhino
accepted-state reference. Program, structure, facade, Grasshopper/Rhino, and
Blender/Web may progress at different maturity levels without being presented as one
undifferentiated success state.

The integrated dependency graph is:

```text
project brief + MP3
        ↓
audio features → architectural score (10 slots; unsupported remain unknown)
        ↓
program constitution → massing/circulation host model
        ↓                         ↓
structural profile + topology    facade_host_handoff
        ↓                         ↓ selection records + reference evidence
coordinated building model       facade candidate plan
                  ╲             ╱
               Grasshopper candidate geometry
                           ↓ validators + human review
               Rhino accepted geometry + manifest
                           ↓
                 Blender / Web presentation

Every branch and artifact is indexed by pipeline_run_manifest.
```

The current API also has a separate preview route:

```text
building_model_v2 → Blender semantic adapter → .blend + GLB + scene/asset manifests → Web
```

This route remains useful for layer inspection and clipping. Its derived facade,
secondary structure, and foundations retain `presentation_only` authority.

## New runtime contracts

### `mta.facade_host_handoff/1.0`

The portable compiler derives one stable host-surface record for each north, south,
east, and west face of every massing element. Each host records:

- stable host ID and source building-element ID;
- orientation, origin, normal, local U/V axes, width, height, and level interval;
- program owner and broad program category;
- preview authority and facade gates;
- all ten Shared Score dimension slots with `known` or `unknown` status;
- blockers and explicit readiness flags.

This contract supplies the missing bridge required by the
`mta-facade-image-pipeline` candidate-plan contract. It contains no facade geometry and
cannot create a Rhino acceptance record.

### `mta.pipeline_run_manifest/1.0`

The manifest joins authored specifications, runtime contracts, and generated files:

- Program, Structure, and Facade guideline hashes;
- typology, tectonic, and grammar decision-record hashes;
- audio, score, building-model, mapping-report, and facade-handoff hashes;
- `.blend`, GLB, Blender manifest, and scene-state hashes;
- stage route, producer, authority, status, dependencies, and blockers;
- one Rhino-owned accepted-state record.

Identical inputs and authored specification files produce equivalent inline contract
hashes and deterministic stage state. A guideline change becomes visible in the next
run even when geometry has not yet changed.

## Authority order

| Artifact or action | Authority |
|---|---|
| Program/Structure/Facade guideline | `specification` |
| MP3 measurements | `source_observation` |
| Architectural score and portable building data | `candidate` |
| Current schematic program, structure, and facade hosts | `preview_only` |
| Facade research image/spec and unselected grammar study | `review_only` |
| Grasshopper generated geometry | `candidate` |
| Explicit Rhino bake/export plus matching acceptance manifest | `accepted_geometry` |
| Blender scene, GLB, Web materials/cameras/context | `presentation_only` |
| Validation and mapping reports | `validation_report` |

Downstream software cannot increase authority by importing, rendering, renaming, or
editing a lower-authority artifact.

## Facade Skill boundary

The user-level `mta-facade-image-pipeline` remains an authoring and review tool. The
repository owns the building/host input and accepted-state output boundaries. A future
candidate plan enters the repository only after its Skill validator confirms:

- selected primary typology and tectonic profile;
- selected executable facade grammar and matching selection record;
- building-model host IDs and hashes;
- all ten Shared Score dimension states;
- legal operations, invariants, support/assembly checks, and limitations;
- `ready_for_geometry_handoff: true`.

The external Skill path is not a runtime dependency of the API. Its JSON artifacts are
portable handoff files validated at the integration boundary.

## Current run truth

The implemented pavilion API run reports:

| Stage | Current status | Reason |
|---|---|---|
| Audio extraction | pass | measured MP3 features with provenance |
| Architectural score | warning | four known dimensions, six explicit unknowns |
| Program compilation | warning | broad massing categories; detailed Program Constitution pending |
| Structure compilation | warning | schematic orthogonal columns; material profile and analysis pending |
| Facade host bridge | warning | stable MTA-F0 hosts available |
| Facade candidate plan | blocked | typology, tectonic profile, and executable grammar selections pending |
| Grasshopper integrated facade | pending/blocked dependency | candidate plan unavailable |
| Rhino acceptance | blocked | no matching per-run acceptance manifest |
| Blender/Web preview | pass | semantic presentation-only artifact set |

`preview_ready` is the highest honest overall status for this route.

## Failure and regeneration rules

- A blocked or failed stage cannot publish a higher-authority downstream artifact.
- Rhino accepted state requires the exact input/run hashes recorded by the manifest.
- Blender/Web can still publish a clearly labeled preview when acceptance is blocked.
- A specification, score, program, structural profile, facade plan, or accepted geometry
  hash change invalidates only its declared downstream stages.
- Invalid candidate plans and geometry never overwrite the last accepted Rhino state.
- Unsupported score dimensions retain `unknown`; a facade adapter cannot fill them from
  image appearance.

## Next implementation order

1. Add explicit JSON selection records for one typology, one tectonic/material profile,
   and two executable grammars.
2. Replace the fixed pavilion Program preview with the detailed Program Constitution
   contract and validators.
3. Replace schematic frame columns with the selected structural profile and load-path
   contract.
4. Add a repository ingestion adapter for one validated facade candidate plan.
5. Implement separate Grasshopper host, zoning/grid, opening/entry, envelope,
   support/detail, validation, and bake/export responsibilities.
6. Emit a Rhino acceptance manifest tied to the exact pipeline run and element IDs.
7. Let Blender import that accepted artifact; retain the current direct route as an
   explicitly named web-preview adapter.

## Verification

`backend/tests/test_integration.py` verifies that:

- each massing exposes four stable, source-linked facade hosts;
- the bridge contains exactly ten Shared Score dimensions;
- unsupported dimensions remain null with reasons;
- facade planning and Rhino acceptance stay blocked while selections are absent;
- Blender outputs remain `presentation_only`;
- the run manifest and inline artifact hashes are deterministic.

## Consequences

- The project now has one inspectable run-level account of what exists, what is only a
  preview, what is blocked, and who can accept geometry.
- Program and Structure guidelines become hashed runtime dependencies without implying
  that their full generators already exist.
- Facade research can continue immediately while geometry authority remains protected.
- Future integration work attaches to declared contracts and stage IDs instead of
  adding another independent pipeline.
