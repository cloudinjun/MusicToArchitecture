# Project Charter — Music to Architecture

## North Star

This project must demonstrate the following professional value:

> I can translate ambiguous design intent into a cross-scale, testable, traceable,
> and reusable computational design system that coordinates program, massing,
> circulation, structure, facade, and interior.

Music gives the project a memorable and accessible public story. The durable technical
subject is **design-intent computation**.

Recruiter-facing description:

> A constraint-aware design-intent compiler that coordinates program, massing,
> circulation, structure, facade, and interior through a shared, traceable
> compositional model.

Public-facing hook:

> AI can generate every part of a building. But can it compose one?

Personal positioning:

> A computational designer who turns qualitative design intent into structured,
> testable, and reusable design systems across disciplines.

## Problem this project solves

The primary problem is **cross-scale design-intent propagation**:

> When computational or AI-assisted tools generate program, massing, structure,
> facade, and interior in separate stages, how can the workflow preserve one coherent
> intent across every handoff?

The project addresses these recurring failures:

- qualitative intent cannot be executed directly by software;
- each stage uses different data, tools, and professional vocabulary;
- handoffs reinterpret and gradually dilute the original intent;
- locally plausible outputs can still describe an incoherent overall building;
- upstream changes trigger excessive manual downstream rework;
- output objects often lack a clear reason or source rule;
- one-off scripts resist reuse by another project or team;
- generative workflows produce outputs without defining what counts as a valid result.

## Three levels of the research problem

### Core problem — Cross-scale design-intent propagation

Preserve a shared compositional intention across program, massing, circulation,
structure, facade, and interior.

### Engineering problem — Reliable and reusable computational workflow

Make the translation deterministic, regenerable, validated, traceable, maintainable,
and extensible through schemas and adapters.

### Validation problem — Controlled generalization

When music, style grammar, or typology changes, demonstrate which outputs should
change and which requirements must remain stable.

## What music contributes

Music is the first expressive input and the project's stress test. It contributes
relationships such as hierarchy, repetition, variation, density, tension and release,
polyphony, interruption, and tempo of change.

The first pipeline accepts MP3 input. Its full score contract contains genre/style,
hierarchy, repetition, variation, density, continuity, interruption, polyphony,
tension/release, and tempo of change. Each dimension must retain extraction method,
confidence, and provenance. See
`docs/decisions/0004-project-brief-program-and-mp3-score-contract.md`.

The intended flow is:

```text
Ambiguous compositional intent
        ↓
shared architectural score
        ↓
typology-specific interpretation
        ↓
coordinated building systems
        ↓
constraint validation
        ↓
traceable building output
```

The same design-intent compiler could later accept a brand brief, spatial experience
goal, historical-building analysis, composition brief, performance target, site
behavior, or circulation data. These future inputs are architectural extensions, not
MVP requirements.

Exploratory site, scale, and project requirements may come from a deterministic random
provider or a local-LLM provider. All providers must normalize into the same validated
project-brief schema so a real external brief can replace them later.

Grasshopper is the primary interactive design and visualization environment, Rhino is
the accepted geometry and drawing host, and Blender is the rendering, animation,
explainer, and optional downstream environment. Shared contracts and portable Python
logic remain application-neutral. See
`docs/decisions/0005-software-toolchain-and-authority.md`.

Grasshopper primarily receives data through monitored local JSON contracts. The graph
must separate watching, parsing, translation, building systems, validation, and export;
one all-in-one code component is outside the approved architecture. See
`docs/decisions/0006-grasshopper-json-watch-and-component-architecture.md`.

## The four abilities the work must make visible

### V1 — Formalize ambiguous intent

Translate qualitative concepts into executable rules:

- separate invariants from variables;
- define how repetition, hierarchy, interruption, and variation are measured;
- separate typology, style, structure, and score ownership;
- define priority when rules conflict;
- document the human judgment behind every interpretation.

Example: “a strong spatial climax” must become a combination of position in the
primary sequence, relative clear height, preceding compression, daylight change,
circulation convergence, and structural feasibility.

### V2 — Coordinate multiple building systems

Show how one shared intention receives distinct but related interpretations in
program, massing, circulation, structure, facade, and interior.

Example: “repetition — interruption — recovery” may appear as repeated program units
interrupted by a commons, a circulation path passing through a courtyard, a structural
transfer condition, a facade module pause and variation, and a coordinated material or
light change.

### V3 — Turn experiments into reliable workflows

Prove that:

- inputs and interfaces are explicit;
- invalid data is rejected before committing partial output;
- identical inputs and seeds reproduce identical results;
- upstream changes regenerate intended downstream stages;
- unrelated stages remain untouched;
- outputs retain provenance;
- a new typology is added through configuration and adapters with minimal core changes.

### V4 — Define and evaluate good results

Create honest quality gates rather than a decorative aggregate score. Evaluation must
cover architectural validity, compositional coherence, and pipeline reliability.

## Quality gates

### Typology validity

- required program is present;
- room areas fall within declared ranges;
- required adjacency and separation rules pass;
- operational and public circulation logic remains valid.

### Spatial validity

- rooms do not overlap illegally;
- circulation is continuous;
- minimum widths and clear heights pass;
- geometry stays within the site boundary.

### Structural and envelope validity

- grids and cores remain continuous where required;
- spans stay within configured limits or produce explicit transfer conditions;
- columns avoid prohibited locations;
- facade support returns to primary structure;
- panel dimensions, joints, anchors, and fabrication limits are checked when applicable.

### Compositional coherence

- shared motifs appear across intended scales;
- hierarchy remains consistent across selected building systems;
- changing the score affects declared targets;
- typology invariants survive musical variation;
- style grammar changes expression without erasing score identity.

### Pipeline validity

- same input and seed reproduce the same result;
- outputs trace back to source data and rules;
- invalid stages stop cleanly without contaminating accepted results;
- stage ownership and regeneration boundaries remain explicit.

## Required portfolio evidence

The finished project must contain these six evidence types:

1. **Baseline failure** — show how the legacy sequence loses shared intent across
   program, massing, structure, facade, and interior.
2. **Shared representation** — show the schemas for typology, program graph, style
   grammar, and architectural score.
3. **Decision ownership** — label what the designer defines, music supplies, AI
   suggests, constraints modify, and the designer rejects.
4. **Change propagation** — change one high-level rule and show coordinated updates
   alongside intentionally stable elements.
5. **Failure and recovery** — trigger a span, circulation, panel, or adjacency failure
   and show rejection or correction.
6. **Transfer test** — change typology without changing the core compiler; replace the
   constitution, program graph, and only necessary adapter configuration.

## Metrics to report honestly

| Metric | Evidence sought |
|---|---|
| Reproducibility | Same input and seed produce the same result |
| Provenance coverage | Generated objects trace to a source rule |
| Constraint pass rate | Declared hard requirements that pass |
| Manual interventions | Human repair required for one complete run |
| Change propagation | Downstream stages updated after an input change |
| Transfer effort | Core-code changes required for a new typology |
| Failure containment | Invalid stages leave accepted results unpolluted |
| Runtime | Time spent in each generation and validation stage |

Metrics may expose weaknesses. Honest measurements are stronger evidence than an
unsupported claim of optimization.

## Recommended controlled experiment

The first typology decision uses a three-candidate shortlist:

- library;
- theater;
- museum.

Select one primary typology before building a typology-specific generator. The
comparison protocol, candidate hypotheses, and required pre-selection artifacts are
recorded in `docs/decisions/0001-primary-typology-shortlist.md`.

After selection, the controlled experiment should use:

- one selected primary typology;
- two executable style grammars selected from the approved candidate library;
- two musically distinct inputs;
- one fixed tectonic system selected from frame, tensile, and shell;
- one shared score schema.

The tectonic shortlist and comparison protocol are recorded in
`docs/decisions/0002-tectonic-system-shortlist.md`. Typology and tectonic choices should
be tested as a compatibility matrix before either choice becomes expensive to reverse.

The approved style-language library contains International Style, Bauhaus, Brutalism,
Organic Architecture, High-tech Architecture, Postmodernism, Deconstructivism,
Minimalism, Critical Regionalism, and Parametricism. Selection and operationalization
rules are recorded in `docs/decisions/0003-style-language-candidate-library.md`.

Choose a transfer typology only after the primary compiler boundary is stable. The
transfer test should demonstrate that a new constitution and program graph can be
introduced with minimal core-code changes.

## Non-goals for the first complete version

- a catalogue of many building types or styles;
- a universal music-to-form mapping;
- a style lottery driven by prompts;
- maximum visual complexity;
- real-time microphone input, VR, robotic fabrication, or full acoustic simulation;
- unrestricted AI generation of program requirements;
- a single opaque “quality score”;
- claims of professional structural, fire, accessibility, envelope, or acoustic
  compliance beyond the explicitly implemented checks.

## Decision filter for every material task

Before adding a feature, migrating legacy code, or expanding scope, answer:

1. Which ability does this make visible: V1, V2, V3, or V4?
2. Which required portfolio evidence does it produce?
3. Which quality gate or traceability mechanism does it strengthen?
4. Can it be tested with a controlled input and expected outcome?
5. Does it preserve the distinction among typology, program, style, score, tectonics,
   and constraint ownership?
6. Is it required for the next experiment, or can it wait?

Work that only increases the number of outputs, styles, technologies, or visual effects
should be deferred until the core evidence is complete.

## Definition of project success

A reviewer should be able to conclude:

> She can formalize ambiguous requirements, design shared data and rule systems across
> tools, coordinate multiple architectural stages, and establish validation,
> provenance, regeneration, and reuse mechanisms.

If reviewers remember only the musical form-making, the project has missed its career
objective. If music makes the system memorable while the evidence reveals the four
abilities above, the project has stayed true to its purpose.
