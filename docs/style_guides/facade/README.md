# Facade Style Grammar Research and Modeling Guidelines

- Status: research library; no executable grammar selected by this document
- Date: 2026-08-27
- Project role: supports V1 formalizing intent and V4 evaluation preparation
- Decision boundary: follows `docs/decisions/0003-style-language-candidate-library.md`

## Purpose

This folder translates the project's ten approved architectural-language candidates
into facade design and modeling guidance. Each guide separates four kinds of content:

1. **Research basis** — historical ideas and reference works supported by sources.
2. **Project interpretation** — a deliberately limited, qualified grammar for this
   compiler.
3. **Project-authored parameters** — starting ranges for controlled experiments;
   these are not universal historical rules.
4. **Validation** — tests that can distinguish an executed grammar from a style label
   attached after generation.

The ten guides form a research library. Decision 0003 still limits the first controlled
experiment to two executable grammars selected after a leading typology–tectonic
combination exists.

Manual cube-entry concept illustrations and their traceable score fixture are available
at [`examples/README.md`](./examples/README.md). They support visual discussion and do
not count as implemented grammar evidence.

## Guide index

| ID | Qualified project grammar | Primary facade operation | Main implementation risk |
|---|---|---|---|
| 01 | [International Style–informed abstract facade grammar](./01_international_style.md) | regular non-load-bearing plane, proportional grid, abstract surface | collapsing the language into a generic glass box |
| 02 | [Bauhaus-informed functional modular grammar](./02_bauhaus.md) | program-legible volumes, industrial module, transparency and color by role | treating Bauhaus as a monochrome graphic brand |
| 03 | [Brutalism-informed mass-and-assembly grammar](./03_brutalism.md) | deep mass, material directness, circulation and structure made legible | equating the language with exposed concrete alone |
| 04 | [Organic Architecture–informed site-and-growth grammar](./04_organic_architecture.md) | site response, part-to-whole module, inside–outside continuity | using curvature as the only signal |
| 05 | [High-tech–informed legible assembly grammar](./05_high_tech.md) | exposed structure, services, circulation and replaceable components | adding decorative pipes without a real system role |
| 06 | [Postmodernism-informed communicative facade grammar](./06_postmodernism.md) | sign, reference, scale shift, layered composition | producing an arbitrary ornament catalogue |
| 07 | [Deconstructivism-informed controlled-fragmentation grammar](./07_deconstructivism.md) | collision, shear, split and displaced grids under constraints | randomizing geometry and losing program or envelope continuity |
| 08 | [Minimalism-informed reductive facade grammar](./08_minimalism.md) | reduced palette, exact proportion, joints, light and material continuity | relying on empty white surfaces without detail discipline |
| 09 | [Critical Regionalism–informed place-responsive grammar](./09_critical_regionalism.md) | climate, topography, local material/craft and tactile depth | executing the grammar before site evidence exists |
| 10 | [Parametricism-informed relational facade grammar](./10_parametricism.md) | correlated fields, continuous differentiation and fabrication-aware panelization | making a smooth or complex form with no dependency logic |

## Structural compatibility screen

Grammar selection is no longer independent of the structural system. Each grammar
publishes a `FacadeDemand` -- areal mass range, accepted backup types, support spacing,
deflection limit, panel geometry class, facade depth, barrier continuity, opening ratio
range, and whether its cladding is combustible -- and each structural system publishes
what it can offer. Compatibility is computed, not asserted; see
[`docs/decisions/0009`](../../decisions/0009-program-structure-facade-coupling.md) and
`backend/app/coupling.py`.

Two consequences bind this library:

- **The two-grammar experiment of decision 0003 must be selected from the admissible
  set**, not from all ten. A grammar that fails a hard gate against the selected
  structural system is not a candidate.
- **The building-code layer can remove a grammar from a specific site.** A small fire
  separation distance caps unprotected openings, so a grammar whose lowest legal opening
  ratio exceeds that cap is unavailable on that elevation regardless of intent.

## Cross-candidate analysis

| Grammar | Primary order | Facade is understood as | Most legible score channels | Extra evidence needed before execution |
|---|---|---|---|---|
| International Style–informed | orthogonal proportional grid | abstract non-load-bearing plane | repetition, continuity, hierarchy | structure/facade grid relationship and zone-specific glazing limits |
| Bauhaus-informed | functional volumes plus industrial module | program-legible kit of envelope types | repetition, polyphony, interruption | program-to-facade assignment and repeatable-part catalogue |
| Brutalism-informed | mass, section and construction trace | inhabited/material edge | hierarchy, tension/release, density | declared material process and sectional support/assembly |
| Organic-informed | site fields plus part-to-whole module | inside–outside/site mediator | continuity, variation, tension/release | topography, view, sun and material inputs |
| High-tech–informed | system graph and repeated interfaces | visible assembly of technical systems | polyphony, repetition, density | real function tags, ports, routes and maintenance logic |
| Postmodernism-informed | background order plus semantic layer | public communication and transformed reference | hierarchy, interruption, polyphony | human-authored motif source, audience and meaning |
| Deconstructivism-informed | conflict among coherent source systems | controlled split/collision | interruption, tension/release, polyphony | source grids, protected zones and collision details |
| Minimalism-informed | proportion and joint hierarchy | reduced material/light plane with precise depth | continuity, hierarchy, low-rate interruption | assembly tolerance, joint graph and time-based light study |
| Critical Regionalism–informed | place/climate/material evidence | environmental and cultural mediator | variation, continuity, hierarchy | full context prerequisite set; generation blocks without it |
| Parametricism-informed | dependency graph and correlated fields | adaptive relational system | variation, density, tempo of change, polyphony | driver ownership, fabrication limits and deterministic tests |

### Boundaries that must stay visible

- **International Style and Bauhaus:** both may use glass, orthogonal modules and
  industrial materials. The International Style guide emphasizes abstract regularity
  and a free facade; the Bauhaus guide requires functional differentiation, repeatable
  production logic and program/color roles.
- **Brutalism and Minimalism:** both can use concrete and limited palettes. Brutalism
  foregrounds mass, texture, program and construction trace; Minimalism foregrounds
  reduction, datum precision, joints and controlled light.
- **Organic Architecture and Critical Regionalism:** both respond to site and material.
  Organic Architecture adds part-to-whole growth and inside–outside continuity;
  Critical Regionalism requires geographically and culturally specific climate,
  topography, craft and tactile evidence.
- **Deconstructivism and Parametricism:** both can generate non-orthogonal geometry.
  Deconstructivism works through bounded conflict, fragmentation and displaced systems;
  Parametricism works through continuous or thresholded correlation among variables.
- **High-tech and Brutalism:** both may expose structure and services. High-tech
  emphasizes component interfaces, replaceability and system routing; Brutalism
  emphasizes material presence, mass and direct construction expression.
- **Postmodernism:** it is the only guide in this library that makes authored symbolic
  reference and audience legibility a primary facade invariant.

## Research method and confidence

The research prioritizes original or institutional sources: MoMA exhibition material,
UNESCO and the Bauhaus Dessau Foundation, RIBA, the Frank Lloyd Wright Foundation,
Centre Pompidou, the Pritzker Architecture Prize, project-owner archives, Zaha Hadid
Architects, WBDG/NIBS/GSA, and Facade Tectonics Institute. Foundational books are
included where a web page cannot represent the full theory.

Source claims support historical interpretation and reference analysis. All numeric
ranges in the guides are explicitly marked **project-authored starting range** unless a
source or project brief supplies them. They must be replaced or clamped by selected
material systems, site climate, typology, structure, fabrication limits, and code review.

## Shared authority order

Facade generation follows the project's existing ownership model:

```text
typology constitution
        ↓ defines required rooms, access, privacy, daylight/acoustic needs
accepted massing + tectonic system
        ↓ defines host geometry, support and movement limits
facade style grammar
        ↓ defines vocabulary, composition, assembly expression
architectural score
        ↓ modulates only declared legal variables
environment + fabrication constraints
        ↓ clamp or reject proposals
facade validator
        ↓ produces pass/warning/fail with affected IDs
accepted Rhino geometry + manifest
        ↓
Blender presentation adapter
```

A style grammar cannot delete required access, conceal an unresolved support path,
override panel or span limits, or convert low-confidence music inference into a major
envelope decision without review.

## Shared score-to-facade channels

Every guide uses this common interpretation layer, then narrows or disables channels
according to its own invariants.

| Shared Score dimension | Eligible facade interpretation | Required safeguard |
|---|---|---|
| Genre / Style | proposes a grammar ID or weights | human acceptance is recorded; genre never bypasses compatibility checks |
| Hierarchy | primary entrance bay, public-zone emphasis, primary/secondary layer depth | program hierarchy remains authoritative |
| Repetition | bay, panel, mullion, joint or solid/void cadence | base module belongs to grammar/assembly |
| Variation | bounded family changes in width, depth, aperture or orientation | one stated transformation rule; no unseeded randomness |
| Density | number of fins, subdivisions, opaque elements or visible members per area | daylight, view, structure and fabrication limits clamp output |
| Continuity | seam alignment, material run, horizontal/vertical datum persistence | movement joints and system transitions stay explicit |
| Interruption | entrance, void, courtyard, reveal, missing bay or material break | interruption is localized and tied to a program/sequence event |
| Polyphony | two or more coordinated layers such as frame, screen and glazing | each layer retains its own ID, support and rule owner |
| Tension / Release | depth, compression, aperture contrast, shadow or material weight | avoid using color alone when spatial or tectonic evidence is claimed |
| Tempo of Change | frequency of legal module-family changes along a path/elevation | rate is sampled on a stable facade path and capped to preserve legibility |

## Required facade grammar contract

Each executable grammar should eventually normalize into a portable record with fields
equivalent to the following. Names may change when a schema is implemented.

```yaml
grammar_id: string
grammar_version: semver
qualified_name: string
research_basis:
  - source_id: string
    claim_scope: string
invariants:
  - rule_id: string
    measurable_condition: string
legal_variables:
  - parameter: string
    domain: [min, max]
    unit: string
    owner: grammar | score | environment | human
forbidden_operations:
  - rule_id: string
score_channels:
  - score_dimension: string
    target_parameter: string
    direction: direct | inverse | piecewise
    confidence_gate: float
tectonic_compatibility:
  frame: native | conditional | poor
  tensile: native | conditional | poor
  shell: native | conditional | poor
validation_rules:
  - rule_id: string
limitations:
  - string
```

Every generated facade object or panel should retain at least:

- stable `facade_element_id` and `host_surface_id`;
- source massing/program/category IDs;
- orientation and facade zone;
- assembly/system type and material ID;
- dimensions, thickness, aperture and joint data appropriate to its modeling stage;
- direct support IDs or an explicit unresolved-support warning;
- grammar rule IDs and actual score bindings;
- provenance, schema version, run ID and accepted-state hash;
- geometry status and validation results.

## MTA facade modeling stages

These stages are project-specific reliability levels. They do not claim equivalence to
industry BIM LOD definitions.

| Stage | Required geometry/information | May be used for | Must not claim |
|---|---|---|---|
| MTA-F0 intent | elevation zones, datums, grammar rules, target metrics | selection studies and before/after diagrams | buildable facade |
| MTA-F1 grammar | host surfaces, openings, primary layers, stable IDs | style/score comparison and massing coordination | resolved assembly or performance |
| MTA-F2 system | panel/mullion families, cavities, major subframe/support, corners and transitions | Rhino inspection and preliminary coordination | final anchors, waterproofing or code compliance |
| MTA-F3 validation | joints, movement zones, barrier continuity paths, panel limits, schedules and warnings | documented design-development experiment | professional engineering or certified envelope performance |
| MTA-F4 presentation | Blender materials, weathering, lighting, cameras and explainer overlays | render/animation/web communication | design authority when geometry differs from accepted Rhino state |

The current Blender `add_facade()` output is below MTA-F1: five schematic boxes per
volume with semantic provenance. These guides define a future Grasshopper/Rhino
acceptance route; they do not reclassify current Blender preview geometry as a resolved
facade.

## Shared modeling workflow

1. **Read accepted inputs.** Consume `building_model_v2`, selected grammar, selected
   tectonic system, site/environment record and accepted score. Do not reinterpret MP3.
2. **Extract host surfaces.** Give each exterior face a stable ID, orientation, program
   adjacency, level range and boundary curve.
3. **Create facade zones.** Mark entrance, public display/reading/gallery, service,
   circulation, opaque-back-of-house, daylight-sensitive and acoustic-sensitive zones.
4. **Apply invariants.** Establish grammar datums, base module, material/assembly logic
   and forbidden operations before applying score modulation.
5. **Apply legal score mappings.** Record proposed and applied values. Clamp against
   confidence gates, typology, structure, environment and fabrication.
6. **Rationalize geometry.** Resolve corners, boundaries, openings, panel families,
   unique-part count and support. Avoid relying on unpredictable trimmed-surface UVs;
   use explicit elevation paths, sections or remapped domains where needed.
7. **Generate systems separately.** Keep glazing, opaque cladding, primary/secondary
   support, shading, services and presentation layers distinct.
8. **Validate before commit.** Publish atomically only when schema and geometry gates
   pass. Preserve the last accepted state when a run fails.
9. **Bake with metadata.** Rhino owns accepted geometry. Blender consumes the matching
   accepted artifact/manifest and adds presentation-only data.

## Shared validation gates

### Geometry and data

- all facade pieces are valid, bounded, non-zero geometry;
- no unintended duplicate or coplanar-overlapping panels;
- corners, openings and system transitions close within declared tolerance;
- every generated piece resolves to a host surface and grammar rule;
- identical inputs, seed and versions reproduce equivalent IDs and geometry;
- rejected runs do not overwrite the last accepted output.

### Architecture and tectonics

- entrances and required openings remain recognizable and unobstructed;
- facade support returns to declared primary/secondary structure;
- panels do not cross movement joints or unsupported boundaries;
- public/private/circulation requirements remain legible where the grammar claims
  program expression;
- score-driven changes preserve typology and grammar invariants.

### Envelope development

- rain-shedding/drainage direction is diagrammed;
- air, water, thermal and vapor-control layers have continuous conceptual paths at
  openings, parapets, bases and system changes;
- glazing, opaque wall, shading and subframe transitions have named conditions;
- panel dimensions, curvature/planarity, joint widths, anchors and movement allowances
  use material-system limits when known; unresolved limits remain warnings;
- daylight, glare, solar gain, privacy, views, acoustics and maintenance access are
  evaluated to the depth implemented by the project.

WBDG guidance treats heat, air and moisture control as only part of envelope performance
and also names structure, fire, lighting and rain penetration. The project should keep
the same limited-claim discipline.

## Controlled comparison protocol

For a fair two-grammar experiment, hold constant:

- one selected typology and program constitution;
- one accepted massing;
- one tectonic system and structural grid/topology;
- one site/environment input;
- one architectural score;
- facade modeling stage and validator set;
- camera, drawing scale and comparison metrics.

Declare expected differences before generation. Compare rule execution and metrics such
as provenance coverage, facade-zone preservation, panel family count, support coverage,
opening distribution, geometry failures and manual interventions. Image resemblance can
support communication but cannot be the only grammar test.

## Shared technical references

- [WBDG, Exterior Envelope requirements](https://www.wbdg.org/FFC/NIH/nih_design_requirements_rev_2.1_2024.pdf) — air, thermal and moisture control; drainage, flashing and condensation review.
- [WBDG, Above Grade Wall Selection Guide](https://www.wbdg.org/files/pdfs/edg/bedg_agwsg.pdf) — barrier and drainage-cavity wall distinctions.
- [Facade Tectonics Institute, Systems Thinking](https://www.facadetectonics.org/papers/systems-thinking) — facade typologies, assemblies and performance flows.
- [Facade Tectonics Institute, Design Considerations and the Complex Facade](https://www.facadetectonics.org/papers/design-considerations-and-the-complex-facade) — early reconciliation of form, material, structure, durability and environmental demands.
- [NIBS, Project BIM Requirements template](https://www.nibs.org/sites/default/files/docs/V4-PBR-Template-and-Example-Language.pdf) — model-element breakdown and explicit development requirements.
- [GSA BIM Guide 07](https://www.gsa.gov/cdnstatic/BIM_Guide_07_v_1.pdf) — distinction between visual detail and information reliability.
- [McNeel, PanelingTools for Grasshopper Primer](https://wiki.mcneel.com/_media/labs/panelingtools4grasshopperprimer.pdf) — parameterized panel grids, modules and attractor-driven aperture examples.

## Scope limitations

- The guides are research and operationalization artifacts, not proof that a style has
  been implemented or validated.
- Numeric starting ranges need project-specific testing and human acceptance.
- No guide makes professional structural, fire, waterproofing, thermal, acoustic,
  accessibility or fabrication-compliance claims.
- Critical Regionalism remains non-executable until site, climate, material and cultural
  evidence is supplied.
- Evidence-matrix statuses should remain unchanged until an actual grammar, controlled
  comparison or verified artifact demonstrates a claim.
