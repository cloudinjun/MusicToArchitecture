# 06 — Postmodernism-informed Communicative Facade Grammar

## Scope and research basis

Postmodern architecture reacted against modernist uniformity through ambiguity,
reference, symbolism, color, historical allusion, popular culture and scale play. This
project grammar treats the facade as a communicative composition. Each reference or
motif needs a source, intended audience and compositional role; randomness does not
produce meaningful plurality.

Canonical references:

1. Robert Venturi and John Rauch, **Guild House**, 1960–1963.
2. Michael Graves, **Portland Building**, 1979–1982.
3. Charles Moore and MLTW, **Piazza d'Italia**, 1975–1978.
4. James Stirling and Michael Wilford, **Neue Staatsgalerie**, 1977–1984.

Primary sources:

- [RIBA, Postmodernism in Architecture](https://www.riba.org/explore/riba-collections/architectural-styles/post-modernism-movement/)
- [V&A, Postmodern Design](https://www.vam.ac.uk/info/collection-selection-boxes-postmodern-design)
- [City of Portland, Portland Building](https://www.portland.gov/fleet-and-facilities/facilities/portland-building)
- [City of Portland, Portland Building monograph](https://www.portland.gov/omf/documents/portland-building-monograph/download)
- Robert Venturi, *Complexity and Contradiction in Architecture*, 1966.
- Robert Venturi, Denise Scott Brown and Steven Izenour, *Learning from Las Vegas*, 1972.

## Facade thesis

The facade communicates public role, entrance, scale and cultural reference through a
layered composition. A stable background organization supports a limited set of
transformed motifs, signs or historical conventions. Contradiction and double-coding are
deliberate: a facade can be formally familiar and materially contemporary, or grand in
symbolic scale and ordinary in assembly.

## Invariants

- `PM-INV-01` — every motif/reference has source, transformation rule, audience and role.
- `PM-INV-02` — the facade has a readable base/middle/top, frame/infill, field/event or
  another declared compositional hierarchy.
- `PM-INV-03` — entrance and public identity remain legible at pedestrian and urban scale.
- `PM-INV-04` — symbolic layer and environmental/technical wall layer remain separately
  modeled when they differ.
- `PM-INV-05` — color/material contrast follows the hierarchy or reference system.
- `PM-INV-06` — contradiction is limited and recoverable; unrelated motif accumulation
  fails the grammar.

## Legal variables and starting ranges

Project-authored experiment defaults:

| Parameter | Starting range | Owner and use |
|---|---:|---|
| motif families | 1–3 per project | human/grammar |
| motif area | 5–30% of public elevation | grammar/hierarchy |
| symbolic scale multiplier | 1.5–4.0× normal component scale | hierarchy/tension |
| plane/layer offset | 0.10–1.00 m | grammar/assembly |
| color families | 2–6 | grammar/reference |
| compositional exceptions | 1–4 per elevation | interruption/human review |
| repeated background module | 0.9–3.6 m | tectonic/grammar |

## Forbidden operations

- selecting ornaments from a random library with no source or meaning;
- using classical-looking trim while claiming actual stone/load-bearing construction;
- obscuring entrance, egress or facade performance behind a symbolic layer;
- changing reference system on every bay;
- relying on bright color alone;
- allowing music genre stereotypes to choose cultural symbols automatically.

## Shared Score channels

| Dimension | Mapping in this grammar |
|---|---|
| Hierarchy | scale or frame the entrance motif and public crown/base |
| Repetition | repeat a transformed conventional window, pilaster, sign or background bay |
| Variation | alter motif scale, crop, color or alignment through one declared rule |
| Density | vary reference/symbol concentration over a stable background |
| Continuity | continue a cornice-like datum, frame, arcade or graphic band |
| Interruption | displaced pediment/frame, broken datum, oversized opening or sign event |
| Polyphony | coordinate functional wall, symbolic layer and public signage as distinct voices |
| Tension / Release | contrast ordinary repeated bays with an exaggerated public event |
| Tempo of Change | control spacing between symbolic exceptions |

## Grasshopper/Rhino modeling guideline

1. Define the public message and intended audience before motif geometry.
2. Establish a background facade organization tied to structure/program.
3. Create a motif library containing vector profile, source/reference, transformation
   limits, permitted materials, attachment plane and semantic role.
4. Apply motifs through named operations such as scale, crop, mirror, flatten, frame,
   displace or color substitution.
5. Keep symbolic screen/relief separate from weather barrier and glazing systems.
6. Test the facade at pedestrian close view, street elevation and distant silhouette.
7. Apply score modulation only to approved transformation parameters; cultural source
   and intended meaning remain human-owned.
8. At MTA-F2, detail returns, supports, drainage and junctions for projecting reliefs or
   screens.
9. Export a motif schedule with source, applied transformation and affected IDs.

## Tectonic compatibility

- **Frame — native.** A regular frame can support a communicative infill/screen and makes
  symbolic versus construction layers explicit.
- **Tensile — conditional.** Symbolic canopies or banners can operate when attachment and
  weathering are resolved.
- **Shell — conditional.** Shell silhouette can carry meaning, but applied references
  need a clear relationship to surface geometry and fabrication.

## Typology notes

- **Library:** public identity, civic entry and readable scale are useful; signage and
  motifs cannot compromise daylight or quiet zones.
- **Theater:** marquee, entrance sequence and performance symbolism are natural channels;
  back-of-house remains programmatically direct.
- **Museum:** reference can address collection, city or institution; avoid turning the
  building into a fixed icon that conflicts with flexible curatorial identity.

## Validation

- 100% of motifs have source, role, audience and transformation metadata;
- the entrance is recognizable in untextured elevation and at human-eye view;
- background grid and symbolic layer are independently visible;
- no motif blocks required openings, drainage or movement joints;
- a score change varies declared transformations without changing source/meaning;
- removing color still leaves scale, hierarchy and reference operations legible;
- a reviewer can distinguish intentional contradiction from geometry error.

## Limitations

The grammar cannot automate cultural legitimacy or audience interpretation. Symbol and
reference require human authorship, contextual review and careful public explanation.
