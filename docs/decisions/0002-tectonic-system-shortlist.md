# Decision 0002 — Tectonic System Shortlist

- Status: active shortlist; expanded to a ten-system N-choose-1 on 2026-08-29;
  final selection pending
- Date: 2026-08-26, amended 2026-08-29
- Decision owner: user
- Career-value tags: V1, V2, V4

## Decision

The first implementation will select one tectonic system from exactly three
candidates:

1. Frame system（框架体系）
2. Tensile system（张拉体系）
3. Shell system（壳体体系）

The selection defines the first project's structural vocabulary, geometric freedoms,
hard constraints, and fabrication assumptions. Material and detailed structural
subtype remain separate decisions.

Examples of later subtype decisions include steel, reinforced concrete, or mass-timber
frames; cable-net or membrane tensile systems; and grid, ribbed, folded, or continuous
shells. Do not silently choose a subtype while selecting among the three system
families.

## Amendment 2026-08-29 — the shortlist is an N-choose-1 over ten systems

The three families above are the **first** gate, not the selection itself. A family is
not executable: "frame" does not tell the compiler what to emit, and steel, concrete,
mass timber, post-and-beam, and light wood produce genuinely different element
taxonomies, geometry primitives, and validation gates. The selection therefore runs in
three gates over **N = 10 executable systems**, each with its own independent guideline
in [`docs/guidelines/structural_systems/`](../guidelines/structural_systems/README.md).

```text
GATE A  family shortlist    frame | tensile | shell                       3
GATE B  system shortlist    01 … 10, comparative studies only        10 -> 3
GATE C  single selection    one system implemented to portfolio depth  3 -> 1
```

| ID | System | Family |
|---|---|---|
| 01 | [Structural steel frame](../guidelines/structural_systems/01_steel_frame.md) | frame |
| 02 | [Reinforced concrete frame and wall](../guidelines/structural_systems/02_reinforced_concrete_frame_wall.md) | frame |
| 03 | [Mass timber: CLT on glulam](../guidelines/structural_systems/03_mass_timber_clt_glulam.md) | frame |
| 04 | [Glulam post-and-beam](../guidelines/structural_systems/04_glulam_post_and_beam.md) | frame |
| 05 | [Light wood frame](../guidelines/structural_systems/05_light_wood_frame.md) | frame |
| 06 | [Tensile membrane](../guidelines/structural_systems/06_tensile_membrane.md) | tensile |
| 07 | [Cable net and cable-supported hybrid](../guidelines/structural_systems/07_cable_net_hybrid.md) | tensile |
| 08 | [Reinforced concrete shell](../guidelines/structural_systems/08_reinforced_concrete_shell.md) | shell |
| 09 | [Timber gridshell](../guidelines/structural_systems/09_timber_gridshell.md) | shell |
| 10 | [Steel space frame and gridshell](../guidelines/structural_systems/10_steel_space_frame_shell.md) | shell |

A system earns its own guideline when its element taxonomy, its required geometry
primitives, and its validation gates are **all three** materially different. Two material
variants that share all three belong in one guide. Apply that test before proposing an
eleventh system, and before merging two.

Gate C adds two criteria that the original family-level criteria could not express,
because they only become visible once a system is described concretely:

- **primitive cost** — how far beyond the four geometry primitives of
  [decision 0008](./0008-element-taxonomy-and-datum-chain.md) the system pushes the
  schema. Systems 01–05 and 10 fit inside them; 06 and 08 require `mesh_surface`; 09
  requires curved members with a bend-radius limit.
- **datum-chain cost** — whether the registration lattice already exists or a solver
  stage (form finding, relaxation, planarisation) must be added inside the accepted
  route. Systems 06, 07, and 09 require one.

The comparative-study rule is unchanged and now applies at system level: produce the
Gate B artifacts for three candidates only. **Do not implement three full structural
generators, and do not write an eleventh guideline to avoid making a choice.**

The executable system/profile and validation contract is defined in
[`docs/guidelines/structural_system_guideline.md`](../guidelines/structural_system_guideline.md).
It keeps this three-family shortlist intact while defining materially different
generation logic for CLT/mass timber, glulam, light wood, steel, reinforced concrete,
tensile membrane/cable, and shell profiles. It also defines the jurisdiction code gate,
load-path graph, program negotiation, provenance, and honest compliance vocabulary.
Only the selected family/profile pair proceeds to an implementation at portfolio depth.

## Role in the compiler

The tectonic system owns what the building can physically express:

- permitted structural topology;
- span and support relationships;
- continuity requirements;
- member or surface hierarchy;
- allowable geometric variation;
- connection, panelization, and fabrication assumptions;
- structural failure conditions implemented by the project.

The architectural score may modulate legal variation inside this system. It cannot
override hard structural and fabrication constraints.

```text
typology constitution → what the building must do
style grammar         → how the building speaks
architectural score   → how systems compose and vary
tectonic system       → how the building stands and can be made
validator             → whether the declared rules pass
```

## Candidate hypotheses

These are starting hypotheses for comparison, not final engineering claims.

### Frame system（框架体系）

Potential strengths:

- clear columns, beams, bays, grids, cores, and transfer conditions;
- rhythm, grouping, repetition, interruption, and hierarchy are easy to trace;
- strong compatibility with the reusable structural utilities in the legacy pipeline;
- constraints and failure cases can be stated clearly for an MVP;
- supports direct comparison across library, theater, and museum programs.

Risks to test:

- musical mapping may collapse into changing bay spacing;
- rigid grids can limit spatial sequence unless transfer and secondary systems are
  designed carefully;
- a visually conventional result may hide the cross-system contribution.

### Tensile system（张拉体系）

Potential strengths:

- tension, release, hierarchy, direction, and force distribution align with the
  project's shared compositional vocabulary;
- structure, envelope, and spatial atmosphere can become one coordinated system;
- produces strong evidence of constraint negotiation because form depends on support,
  prestress, curvature, and boundary conditions.

Risks to test:

- credible form finding and engineering validation require specialized methods;
- program enclosure, acoustics, environmental control, and interior subdivision may
  need a secondary building system;
- unsupported structural claims could weaken the portfolio evidence;
- direct reuse from the legacy frame-oriented structure module may be limited.

### Shell system（壳体体系）

Potential strengths:

- integrates structure, enclosure, spatial sequence, and surface articulation;
- supports continuity, interruption, density, rib hierarchy, and opening variation;
- offers meaningful fabrication and panelization quality gates;
- can make cross-scale score propagation visible from global form to local components.

Risks to test:

- geometric freedom can drift into unconstrained form-making;
- credible support, thickness, curvature, buckling, openings, and edge conditions add
  technical scope;
- program insertion and circulation may become secondary to the shell image;
- panelization evidence may arrive too early and distract from the compiler core.

## Selection criteria

Evaluate each system against the selected or leading typology candidate using a
comparable architectural episode and scale.

| Criterion | Question |
|---|---|
| Career evidence | Does the system make V1–V4 visible through rules, coordination, workflow, and evaluation? |
| Typology fit | Can it support the critical program, circulation, span, and enclosure requirements? |
| Score capacity | Can music vary several meaningful properties without controlling safety-critical decisions? |
| Constraint clarity | Can the MVP state honest pass/fail rules? |
| Cross-system coordination | Does it create legible relationships among structure, space, facade, and interior? |
| Computational feasibility | Can deterministic generation and validation be implemented with available tools? |
| Legacy reuse | Which neutral utilities or contracts can be migrated without importing old form language? |
| Fabrication evidence | Can the project show credible components, joints, panels, or assembly logic? |
| Scope risk | Can one result reach architectural and portfolio depth within the project schedule? |

Use an explicit 1–5 rating plus written evidence. A high visual-impact score cannot
compensate for weak constraint definition or unmanageable technical scope.

## Required artifacts before final selection

For each candidate, produce only:

- one structural topology diagram;
- one list of hard invariants and legal score-controlled variables;
- one typology-specific span or enclosure episode;
- one cross-system interpretation example;
- one credible failure-and-recovery scenario;
- one tooling, validation, and legacy-reuse risk note.

These are comparative studies. Do not implement three full structural generators.

## Consequences

- The first tectonic system remains undecided until compared with the typology
  shortlist.
- Typology and tectonics should be evaluated as a compatibility matrix before either
  choice becomes expensive to reverse.
- Style grammar must not redefine structural topology or bypass tectonic constraints.
- Core schemas may proceed if `tectonic_system` is an explicit contract and no frame,
  tensile, or shell assumptions leak into typology-neutral fields.
- `structural_system_id` is a separate field from `tectonic_family`. Code that branches
  on family alone is under-specified and will not survive the Gate C selection.
- The element taxonomy, geometry primitives, and datum chain of the selected system
  determine what decision 0008's schema-3.0 work must actually implement, so Gate C
  should close before stage S2 of that plan begins.
- Legacy `structural_generator.py` is a stronger donor for the frame option; it remains
  reference material for other options rather than an architectural requirement.
