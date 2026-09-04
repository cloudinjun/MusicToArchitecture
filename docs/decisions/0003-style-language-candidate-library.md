# Decision 0003 — Style Language Candidate Library

- Status: candidate library fixed; first two grammars pending selection
- Date: 2026-08-26
- Decision owner: user
- Career-value tags: V1, V2, V4

## Decision

The architectural-language candidate library contains exactly these ten entries:

1. International Style（国际式风格）
2. Bauhaus（包豪斯风格）
3. Brutalism（粗野主义）
4. Organic Architecture（有机建筑）
5. High-tech Architecture（高技派）
6. Postmodernism（后现代主义）
7. Deconstructivism（解构主义）
8. Minimalism（极简主义）
9. Critical Regionalism（批判性地域主义）
10. Parametricism（参数化主义）

The first controlled experiment will implement only two executable style grammars
selected from this library. The remaining entries stay documented candidates for
later transfer or comparison work.

## Terminology and scope

These labels describe different historical movements, theories, methods, and design
attitudes. They should not be treated as equivalent categories with interchangeable
surface presets.

For this project, a `style_grammar` is a transparent, project-authored operational
model derived from a named architectural language. It must declare:

- the rules included in the model;
- the aspects intentionally omitted;
- the architectural references or research supporting those rules;
- which parameters may vary;
- which rules remain invariant;
- how the grammar interacts with typology and tectonic constraints;
- how its output can be evaluated.

The project should use qualified labels such as `Bauhaus-informed modular grammar`
when the implementation models only a subset of a broader historical tradition.

## Separation of responsibilities

```text
typology constitution  → required function and relationships
tectonic system        → structural and fabrication possibility
style grammar          → architectural vocabulary and compositional expression
architectural score    → shared hierarchy, repetition, variation, and sequence
validator              → declared validity and coherence checks
```

Style grammar cannot remove required rooms, invalidate circulation, bypass spans or
supports, or redefine score facts. It determines how valid programmatic and
compositional relationships become architectural expression.

## Operational research fields

Every candidate must be described using the same fields before selection:

| Field | Questions to encode |
|---|---|
| Geometry | Orthogonal, faceted, continuous, irregular, or hybrid? |
| Proportion | Which ratios, scales, alignments, and hierarchy methods apply? |
| Organization | Grid, field, axis, collage, aggregation, or contextual response? |
| Structure expression | Concealed, integrated, monumental, exposed, or celebrated? |
| Envelope | Curtain wall, monolithic mass, layered assembly, free facade, or context-responsive skin? |
| Material logic | Abstract surface, material mass, industrial assembly, local material, or minimized palette? |
| Repetition and variation | Standard module, serial repetition, motif, gradient, rupture, or controlled exception? |
| Ornament and reference | Suppressed, tectonic, symbolic, historical, ironic, or computational? |
| Context | Universalizing, site-derived, climatic, cultural, topographic, or intentionally contrasted? |
| Score channels | Which grammar parameters may respond to hierarchy, density, interruption, tension, or tempo of change? |
| Invariants | Which rules must survive different music inputs? |
| Evaluation | What evidence distinguishes a successful grammar from a label applied after generation? |

## Candidate research cautions

| Candidate | Primary caution for implementation |
|---|---|
| International Style | Avoid reducing it to glass boxes; encode proportion, free plan/facade, regularity, and abstraction with historical care |
| Bauhaus | Separate the institution's changing history from a simplified visual brand; use a qualified project grammar |
| Brutalism | Avoid equating it only with exposed concrete; address mass, program legibility, circulation, structure, and material directness |
| Organic Architecture | Avoid using curvature as the sole rule; examine site, growth, material continuity, part-to-whole relations, and inhabitation |
| High-tech Architecture | Require legible assembly, services, structure, and replaceable components; a metallic appearance alone is insufficient |
| Postmodernism | Define how reference, symbolism, contradiction, scale, and composition operate; avoid a random ornament catalogue |
| Deconstructivism | Define controlled fragmentation, collision, instability, and circulation while preserving constructability and program validity |
| Minimalism | Encode reduction, proportion, joint discipline, material continuity, light, and detail; avoid an empty white-box preset |
| Critical Regionalism | Require climate, topography, material culture, tactile experience, and local conditions; it needs a selected site context |
| Parametricism | Separate computational method from stylistic doctrine; define continuity, differentiation, correlation, and constraint behavior explicitly |

## Selection criteria for the first two grammars

Choose the first two only after a leading typology–tectonic combination exists.

| Criterion | Question |
|---|---|
| Contrast value | Do the two grammars express the same score through meaningfully different architectural vocabularies? |
| Rule clarity | Can each language be expressed as transparent, testable rules? |
| Typology fit | Can both preserve the selected program and circulation invariants? |
| Tectonic compatibility | Can each operate honestly within the chosen structural system? |
| Score separation | Can score identity remain visible after the grammar changes? |
| Research defensibility | Can the selected rules be supported by specific architectural references? |
| Evaluation clarity | Can reviewers see why an output passed or failed the grammar? |
| MVP feasibility | Can both grammars reach comparable depth without doubling the whole pipeline? |

The two grammars should create a strong controlled comparison. They do not need equal
visual complexity, but they must use the same compiler boundary, typology constitution,
tectonic system, music inputs, and evaluation method.

## Required artifact before implementation

For each shortlisted grammar, prepare a compact grammar card containing:

- qualified grammar name;
- three to five references;
- invariant rules;
- legal variables and ranges;
- forbidden operations;
- tectonic interpretation;
- score-controlled channels;
- one pass example and one failure example;
- limitations of the model.

Do not train a classifier or build ten generators. Do not use image resemblance as the
sole verification method.

## Facade research library

The research and preliminary operational guidance for all ten candidates is indexed at
`docs/style_guides/facade/README.md`. Each candidate has a separate facade design and
Grasshopper/Rhino modeling guide with research sources, project-qualified invariants,
legal variables, forbidden operations, score channels, tectonic/typology notes and
validation gates.

These documents are research cards, not implemented grammars. They do not change the
two-grammar limit for the first controlled experiment or the requirement to select a
leading typology–tectonic combination first.

## Consequences

- The style library is broad, but implementation remains limited to two grammars in
  the first controlled experiment.
- Typology and tectonic constraints take priority over style operations.
- Grammar research should begin after the typology–tectonic compatibility study has a
  leading combination.
- The style comparison is intended to prove that the score and grammar are separable:
  the same score retains compositional identity while architectural expression changes.
- Adding a style later should primarily add configuration, references, and a bounded
  adapter; widespread core-compiler changes count against transferability.
