# Structural System Research and Modeling Guidelines

- Status: research library; **no executable system selected by this document**
- Date: 2026-08-29
- Project role: supports V1 formalizing intent, V2 coordinating systems, V4 evaluation
- Decision boundary: follows [`docs/decisions/0002-tectonic-system-shortlist.md`](../../decisions/0002-tectonic-system-shortlist.md)
- Shared contract: [`docs/guidelines/structural_system_guideline.md`](../structural_system_guideline.md)
- Element and primitive contract: [`docs/decisions/0008`](../../decisions/0008-element-taxonomy-and-datum-chain.md)

## Purpose

This folder expands decision 0002's three tectonic **families** into ten executable
**systems**, and gives each one an independent guideline. Exactly one system is
implemented to portfolio depth. The other nine remain specification-ready comparison
candidates.

Each guide separates the same four kinds of content, in the same order, so the ten are
directly comparable:

1. **Research basis** — canonical works and primary standard sources.
2. **Structural thesis and invariants** — what the system must always do.
3. **Element taxonomy, geometry primitives, and datum chain** — what the compiler must be
   able to emit and how every element gets located.
4. **Legal variables, score channels, and validation** — what music is allowed to move and
   how the result is tested.

The split criterion is deliberate: a system earns its own guideline when its **element
taxonomy, its required geometry primitives, and its validation gates** are all materially
different. Two material variants that share all three belong in one guide.

## Guide index

| ID | System | Family | Primary structural operation | Main implementation risk |
|---|---|---|---|---|
| 01 | [Structural steel frame](./01_steel_frame.md) | frame | discrete grid, two-tier spanning hierarchy, declared lateral bays | musical mapping collapses into changing bay spacing |
| 02 | [Reinforced concrete frame and wall](./02_reinforced_concrete_frame_wall.md) | frame | continuous plates on columns and walls; the surface is the structure | box-only schema cannot express a wall with a door |
| 03 | [Mass timber: CLT on glulam](./03_mass_timber_clt_glulam.md) | frame | panelised floor; the panel module becomes plan datum | exporting a room footprint as one impossible panel |
| 04 | [Glulam post-and-beam](./04_glulam_post_and_beam.md) | frame | three-tier stick frame with visible joints | assuming moment continuity at timber joints |
| 05 | [Light wood frame](./05_light_wood_frame.md) | frame | stacked bearing wall lines, no column grid | forcing a commercial grid onto a wall-line system |
| 06 | [Tensile membrane](./06_tensile_membrane.md) | tensile | form-found anticlastic tension surface | faking form finding by drawing a surface |
| 07 | [Cable net and cable-supported hybrid](./07_cable_net_hybrid.md) | tensile | prestressed discrete tension network on a compression boundary | decorative cables that carry nothing |
| 08 | [Reinforced concrete shell](./08_reinforced_concrete_shell.md) | shell | continuous curved surface in membrane action | beautiful images with no solved structure |
| 09 | [Timber gridshell](./09_timber_gridshell.md) | shell | elastically bent lath mesh; radius is the buildability limit | a quad mesh with no shear layer |
| 10 | [Steel space frame and gridshell](./10_steel_space_frame_shell.md) | shell | straight struts and manufactured nodes approximating curvature | unbounded unique node and panel counts |

## Selection protocol — N choose 1

The project selects **one** system, in three gates. No gate may be skipped, and no gate
may be decided on image appeal.

```text
GATE A — family shortlist        decision 0002: frame | tensile | shell        (3)
        ↓ eliminate on typology fit and scope risk
GATE B — system shortlist        this folder: 01 … 10                          (10 → 3)
        ↓ eliminate on primitive cost, datum-chain cost, and score capacity
GATE C — single selection        one system implemented to portfolio depth     (3 → 1)
```

### Gate B required artifacts

For each of the three surviving candidates, and **only** these:

- one structural topology diagram at the selected typology's scale;
- one element-taxonomy table with expected instance counts per layer;
- one list of hard invariants and legal score-controlled variables;
- one typology-specific span or enclosure episode;
- one credible failure-and-recovery scenario;
- one primitive and datum-chain cost note against decision 0008.

These are comparative studies. **Do not implement three full structural generators.**

### Gate C scoring

| Criterion | Weight | Question |
|---|---|---|
| Career evidence | high | does it make V1–V4 visible through rules, coordination, workflow, evaluation? |
| Typology fit | high | can it carry the selected typology's critical span, program, and enclosure? |
| Score capacity | high | can music vary several meaningful properties without touching safety-critical decisions? |
| Primitive cost | high | how far beyond decision 0008's four primitives does it require the schema to go? |
| Constraint clarity | medium | can the MVP state honest pass/fail rules? |
| Datum-chain cost | medium | does the lattice already exist, or must a solver stage be added? |
| Cross-system coordination | medium | does it create legible relations among structure, space, facade, interior? |
| Fabrication evidence | medium | can the project show credible components, joints, panels, assembly logic? |
| Legacy reuse | low | which neutral utilities migrate without importing old form language? |
| Scope risk | high | can one result reach architectural and portfolio depth on schedule? |

Use an explicit 1–5 rating with written evidence per criterion. A high visual-impact
score cannot compensate for weak constraint definition or unmanageable technical scope.

Gate B and Gate C both now have a computed screen. `backend/app/coupling.py` evaluates
program -> structure and structure -> facade from declared physical quantities, and
`backend/app/codes.py` applies the building-code layer as a separate hard screen that
contributes nothing to any weight. Run
`python -m backend.scripts.generate_coupling_report` for the current matrices; the
protocol and its rules are in
[`docs/decisions/0009`](../../decisions/0009-program-structure-facade-coupling.md).

## Cross-candidate analysis

| System | Primary order | Structure is understood as | Registration lattice | Most legible score channels |
|---|---|---|---|---|
| 01 steel frame | orthogonal grid | separable skeleton | `level × x_lines × y_lines` | density, hierarchy, continuity |
| 02 RC frame/wall | plate and wall-plane | continuous monolithic surface | grid + wall-line set | interruption, continuity, hierarchy |
| 03 mass timber | panel module | manufactured kit of plates | grid + panel layout | repetition, variation, polyphony |
| 04 glulam post-and-beam | three-tier stick rhythm | visible framing and joints | grid + roof datum | repetition, density, polyphony |
| 05 light wood frame | wall-line graph | continuous field of small members | wall lines + openings | repetition (binary), density |
| 06 tensile membrane | equilibrium surface | force made into shape | found surface + boundary | tension/release, hierarchy |
| 07 cable net | prestressed line network | force made countable | `node[i][j]` | repetition, density, tension/release |
| 08 RC shell | curvature and boundary | one object that is structure and enclosure | surface curve network | repetition (unit count), hierarchy |
| 09 timber gridshell | woven lath mesh | shell made of bent sticks | `node[i][j]` on a surface | repetition, density, polyphony |
| 10 steel network shell | node graph and faceting | rationalisation problem | node graph + adjacency | repetition, density, continuity |

## Geometry primitive requirement matrix

Cross-referenced against the four primitives defined in decision 0008. This table is the
single most useful Gate C input, because it converts "which system do I like" into "how
much schema does this system cost".

| System | `box` | `member` | `extrusion` | `quad` | Additional requirement |
|---|:--:|:--:|:--:|:--:|---|
| 01 steel frame | ● | ●●● | ●● | — | none |
| 02 RC frame/wall | ●● | ●● | ●●● | — | none |
| 03 mass timber | ●● | ●●● | ●●● | — | panel grain and product limits on `extrusion` |
| 04 glulam post-and-beam | ●● | ●●●● | ●● | — | none |
| 05 light wood frame | ● | ●●●● | ●● | ●● | **`element_group`** payload compaction is mandatory |
| 06 tensile membrane | ●● | ●●● | ●● | — | **`mesh_surface`** + form-finding solver stage |
| 07 cable net | ●●● | ●●● | ● | ●● | `member.pretension`, panel planarity, solver stage |
| 08 RC shell | ● | ●● | ●● | — | **`mesh_surface`** + variable thickness |
| 09 timber gridshell | ●● | ●●● | ● | ●● | **curved `member.path`** + `min_bend_radius` |
| 10 steel network shell | ●●● | ●●● | ● | ●●● | stable node graph IDs, panel planarity |

Legend: ●●●● dominant · ●●● major · ●● secondary · ● minor · — not required.

**Systems 01–05 and 10 fit inside the four primitives of decision 0008.** Systems 06, 08,
and 09 extend the geometry contract, and 06, 07, and 09 additionally require a solver
stage inside the accepted route. That cost is a legitimate reason to prefer or reject a
candidate, and it must be stated in the Gate C record rather than discovered later.

## Boundaries that must stay visible

- **03 mass timber and 04 glulam post-and-beam:** both are glulam frames. 03 has a
  panelised floor whose module governs the plan and whose seams are the ceiling; 04 has a
  three-tier joist floor and no panel module. A post-and-beam project may not silently
  inherit CLT diaphragm behaviour.
- **04 glulam post-and-beam and 05 light wood frame:** both are timber sticks. 04 is a
  discrete frame on a column grid; 05 has no columns at all and is organised entirely by
  wall lines. "Wood structure" is never an acceptable resolution between them.
- **01 steel frame and 02 RC frame/wall:** both are orthogonal frames. Steel is a
  separable skeleton with a two-tier hierarchy; concrete is a continuous plate where
  column stacking and punching shear are the governing constraints.
- **06 tensile membrane and 07 cable net:** both are prestressed tension systems solved
  rather than drawn. 06 is a continuous surface with a cutting pattern; 07 is a discrete
  network where the node is the detail and the cladding is passive.
- **08 RC shell, 09 timber gridshell, 10 steel network shell:** all three are shells. 08 is
  a continuous surface governed by curvature and formwork; 09 is bent continuous laths
  governed by bending radius; 10 is straight struts governed by unique node and panel
  counts. They share a family and share almost no rules.
- **07 cable net and 10 steel network shell:** both are node-and-line networks with
  planar-panel problems. 07 is tension-only and prestressed; 10 carries compression and
  bending, and its nodes must resist rotation.

## Shared authority order

```text
typology constitution
        ↓ required rooms, access, privacy, clear spans, load classes
project brief + site + code profile
        ↓ hazards, occupancy, soils, fire, material standards
selected structural system  (this folder — exactly one)
        ↓ permitted topology, span relations, primitives, fabrication limits
architectural score
        ↓ modulates only declared legal variables inside tectonic clamps
facade grammar + program allocator
        ↓ consume published support points, load paths, and exclusion zones
structural validator
        ↓ pass / warning / fail with affected element IDs
accepted Rhino geometry + manifest
        ↓
Blender presentation adapter
```

A structural system may reject a program request. A score may never override a hard
structural or fabrication constraint, and a facade grammar may never redefine structural
topology.

## Shared score-to-structure channels

Every guide narrows this common layer according to its own invariants, and every guide
must state which channels it **disables**.

| Shared Score dimension | Eligible structural interpretation | Required safeguard |
|---|---|---|
| Genre / Style | proposes a system or profile weighting | human acceptance recorded; never bypasses fit checks |
| Hierarchy | primary/secondary depth ratio, transfer prominence, open ground level | hierarchy is expressed at declared elements, not by resizing safety-critical members |
| Repetition | bay, panel, joist, mesh, or unit cadence | base module belongs to the system and its fabrication limits |
| Variation | bounded family change in span, module, or direction | one stated transformation rule; no unseeded randomness |
| Density | span, spacing, subdivision, member count per area | tectonic clamps always win |
| Continuity | cantilever depth, seam or line continuity, plate alignment | load path continuity is never traded for visual continuity |
| Interruption | voids, transfer levels, missing bays, openings | every interruption has a named structural repair |
| Polyphony | independent readable orders (frame / panel / bracing) | each order retains its own IDs, supports, and rule owner |
| Tension / Release | floor-to-floor, rise-to-span, prestress selection inside a legal band | never sets prestress, curvature, or thickness outside the band |
| Tempo of Change | frequency of legal module-family change along a path | rate sampled on a stable path and capped for legibility |

**Universal prohibition.** No score dimension may set: member capacity, section size on a
lateral or transfer element, prestress level, curvature ratio, shell thickness, bending
radius, planarity tolerance, or any fabrication limit.

## Required structural system contract

Each executable system normalises into a portable record. Field names may change when a
schema is implemented; the content may not shrink.

```yaml
system_id: string
system_version: semver
tectonic_family: frame | tensile | shell
material_system: string
code_profile_ref: string
invariants:
  - rule_id: string
    measurable_condition: string
element_taxonomy:
  - kind: string
    primitive: box | member | extrusion | quad | mesh_surface
    section_or_form: string
    located_by: string
required_primitives: [string]
datum_chain:
  datums: [string]
  lattice: string
  solver_stage: none | form_finding | planarisation | relaxation
legal_variables:
  - parameter: string
    domain: [min, max]
    unit: string
    owner: tectonic | score | program | fabrication | human
forbidden_operations:
  - rule_id: string
score_channels:
  - score_dimension: string
    target_parameter: string
    direction: direct | inverse | piecewise | selection
    clamp_ref: string
disabled_score_channels: [string]
typology_fit:
  library: native | conditional | poor
  theater: native | conditional | poor
  museum: native | conditional | poor
validation_rules: [string]
limitations: [string]
status: candidate | selected | rejected
```

## MTA structural modeling stages

Project-specific reliability levels. They do not claim equivalence to industry BIM LOD
definitions, and they parallel the MTA-F stages used by the facade guides.

| Stage | Required geometry / information | May be used for | Must not claim |
|---|---|---|---|
| MTA-S0 intent | family and system choice, topology diagram, invariants | selection studies | any buildable structure |
| MTA-S1 topology | datums, lattice, analytical line/surface model, stable IDs, load-path graph | system comparison, program negotiation | member sizes or capacity |
| MTA-S2 members | named sections or thicknesses, element taxonomy fully emitted, supports and reactions declared | Rhino inspection, studio-model output, coordination | analysis results or code compliance |
| MTA-S3 validation | conflict checks, span and limit checks, fabrication counts, schedules, warnings | documented design-development experiment | professional engineering approval |
| MTA-S4 presentation | Blender materials, lighting, cameras, explainer overlays | render, animation, web | design authority when geometry differs from accepted Rhino state |

The current pipeline is at **MTA-S1 for one storey only**. The fidelity probe in
`artifacts/fidelity_probe/` demonstrates MTA-S2 output for system 01 without pipeline
authority.

## Shared validation gates

Applied to every system in addition to its own gates. The full text lives in the shared
contract; this is the summary.

### Topology and load path

- every gravity element reaches a foundation or anchor through explicit graph edges;
- every lateral element connects diaphragm or surface, collectors, vertical system, and
  foundation;
- no floating elements of any kind;
- vertical elements align across levels or a named transfer element resolves the offset;
- spans, cantilevers, openings, and spacing stay inside sourced profile limits;
- no element intersects a program exclusion, egress, or accessible clearance zone without
  a recorded negotiation.

### Data and workflow

- every element has stable ID, role, primitive, datum refs, rule refs, reason, authority,
  provenance, and validation status;
- element IDs are lattice coordinates and are stable across runs;
- seed, input hashes, profile versions, solver version, tolerances, and software versions
  are recorded;
- failures preserve the last accepted state and publish a machine-readable report.

### Honest claim discipline

Statuses are limited to `geometry_valid`, `rule_checked`, `analysis_checked`,
`code_inputs_incomplete`, `professional_review_required`, and `design_accepted`. Never
emit `code_compliant`, `safe`, `permit_ready`, or `engineer_approved`.

## Controlled comparison protocol

For a fair Gate B comparison, hold constant:

- one selected typology and program constitution;
- one site, code profile, and load assumption set;
- one architectural score;
- one target program area and one critical span episode;
- MTA-S stage and validator set;
- camera, drawing scale, and comparison metrics.

Declare expected differences before generation. Compare element count by layer, unique
part count, load-path completeness, exclusion-zone conflicts, span-limit violations,
manual interventions, and primitive cost. Image resemblance can support communication but
cannot be the system test.

## Shared technical references

- [ASCE/SEI 7-22, Minimum Design Loads and Associated Criteria](https://www.asce.org/publications-and-news/codes-and-standards/asce-sei-7-22)
- [ICC 2024 IBC Chapter 6, Types of Construction](https://codes.iccsafe.org/content/IBC2024V2.0/chapter-6-types-of-construction)
- [ICC 2024 IBC Chapter 5, Building Heights and Areas](https://codes.iccsafe.org/content/IBC2024P1/chapter-5-general-building-heights-and-areas)
- [AISC ANSI/AISC 360, Specification for Structural Steel Buildings](https://www.aisc.org/aisc/publications/current-standards/aisc-360/)
- [ACI 318 Building Code Portal](https://www.concrete.org/topicsinconcrete/318buildingcodeportal.aspx)
- [AWC 2024 National Design Specification for Wood Construction](https://awc.org/resources/2024-nds/)
- [AWC 2021 Special Design Provisions for Wind and Seismic](https://awc.org/resources/2021-sdpws/)
- [APA ANSI/APA PRG 320-2025, Performance-Rated Cross-Laminated Timber](https://www.apawood.org/guides-tools-training/technical-document-library/standards/ansiapa-prg-320-2025-standard-for-performance-rated-cross-laminated-timber/)
- [ASCE/SEI 55-16, Tensile Membrane Structures](https://sp360.asce.org/personifyebusiness/Merchandise/Product-Details/productId/233135208)
- [IASS, International Association for Shell and Spatial Structures](https://iass-structures.org/)

The reference registry must retain source title, publisher, edition, adoption status,
effective date, local amendment, retrieval date, and any errata used by a run.

## Scope limitations

- These guides are research and operationalization artifacts. They are not proof that any
  system has been implemented or validated.
- All numeric ranges are **project-authored starting ranges** unless a cited source or the
  project brief supplies them. They must be replaced or clamped by the resolved code
  profile, material system, site, and fabrication limits.
- No guide makes a professional structural, fire, seismic, geotechnical, or fabrication
  compliance claim.
- Systems 06, 07, 08, and 09 cannot be executed at all until the geometry contract and the
  solver stage identified in the primitive matrix exist.
- Evidence-matrix statuses stay unchanged until an actual generator, controlled
  comparison, or verified artifact demonstrates a claim.
