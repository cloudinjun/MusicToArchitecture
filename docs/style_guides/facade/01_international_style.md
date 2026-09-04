# 01 — International Style–informed Abstract Facade Grammar

## Scope and research basis

This project uses a qualified grammar derived from a historically broad and contested
label. MoMA's 1932 framing emphasized utility, flexibility, regularity, stripped-down
materials and the rejection of applied classical trappings. Le Corbusier's free facade
and ribbon window show how a structural frame can release the envelope from a
load-bearing composition. Mies and Reich's Barcelona Pavilion adds precise proportion,
material planes and assembly clarity to the research basis.

Canonical references:

1. Le Corbusier and Pierre Jeanneret, **Villa Savoye**, 1928–1931.
2. Ludwig Mies van der Rohe and Lilly Reich, **Barcelona Pavilion**, 1929.
3. Walter Gropius, **Bauhaus Building, Dessau**, 1925–1926, used here only where its
   curtain wall informs wider modern-envelope development; Bauhaus-specific operations
   remain in Guide 02.

Primary sources:

- [MoMA, Architecture for a Modern Age](https://www.moma.org/interactives/moma_through_time/1930/architecture-for-a-modern-age/)
- [MoMA, 1932 Modern Architecture exhibition catalogue](https://assets.moma.org/documents/moma_catalogue_2044_300061855.pdf)
- [Fondation Le Corbusier, Villa Savoye](https://www.fondationlecorbusier.fr/oeuvre-architecture/realisations-villa-savoye-et-loge-du-jardinier-poissy-france-1928-1931/)
- [Fondation Le Corbusier, Corbusian vocabulary](https://www.fondationlecorbusier.fr/dossier-thematique/vocabulaire-corbuseen/)
- [Fundació Mies van der Rohe, Barcelona Pavilion](https://miesbcn.com/the-pavilion/)

## Facade thesis

The facade is an abstract, proportioned, non-load-bearing plane coordinated with a
regular structural order. Openings, opaque zones and material joints follow a limited
set of horizontal and vertical datums. Variation remains legible against that stable
order. Structure and envelope may align or slide past one another, but their
relationship is deliberate.

## Invariants

- `IS-INV-01` — facade composition uses an explicit orthogonal datum and base module.
- `IS-INV-02` — primary envelope planes remain geometrically calm and visually
  continuous; isolated sculptural projections require a program reason.
- `IS-INV-03` — openings and joints resolve to the facade module or a documented
  proportional subdivision.
- `IS-INV-04` — material palette remains limited and abstract; applied historical
  ornament is excluded.
- `IS-INV-05` — entrance hierarchy is achieved through proportion, plane displacement,
  canopy, transparency or void rather than a pasted symbolic motif.
- `IS-INV-06` — free-facade expression cannot disguise the actual tectonic system or
  an unresolved support condition.

## Legal variables and starting ranges

All ranges below are project-authored experiment defaults.

| Parameter | Starting range | Owner and use |
|---|---:|---|
| base facade bay | 1.2–3.6 m | grammar; coordinated with structural grid |
| submodule count per bay | 2–6 | grammar/assembly |
| glazing ratio by facade zone | 0.25–0.75 | typology/environment first, score second |
| opaque-spandrel height / storey height | 0.15–0.40 | grammar; floor edge and services |
| plane offset | 0–0.45 m | score-eligible for hierarchy/interruption |
| mullion rhythm variation | ±0–20% around base module | score-eligible with deterministic grouping |
| accent material area | 0–12% of elevation | human/grammar; one accent family maximum |

The project should use dimensionless proportional studies before fixing metric values.
Environmental analysis may reduce glazing or introduce external shading; those changes
must remain subordinate to the primary datum.

## Forbidden operations

- random window placement with no grid or proportional rule;
- full-height glazing used as an automatic style marker;
- historical cornices, arches or applied orders introduced without changing the grammar;
- score-driven curvature that erases planar and orthogonal invariants;
- facade panels that float without a support or attachment record;
- using identical transparency on gallery, service, entry and circulation zones when
  their daylight, privacy or acoustic needs differ.

## Shared Score channels

| Dimension | Mapping in this grammar |
|---|---|
| Hierarchy | increase bay width, plane depth or transparency at the primary entrance/public zone |
| Repetition | repeat the base bay or a small family of proportional sub-bays |
| Variation | vary mullion grouping or opaque/glazed subdivision within ±20% |
| Density | change subdivision count while retaining main datums |
| Continuity | align horizontal joints, ribbon windows or material planes across volumes |
| Interruption | remove one bay, create a recessed threshold or pause a continuous band |
| Polyphony | coordinate independent structural grid, facade grid and program banding |
| Tension / Release | contrast compressed opaque approach with a more transparent public bay |
| Tempo of Change | set how often the legal bay family changes along the elevation path |

Genre may propose this grammar; it supplies no direct facade scalar.

## Grasshopper/Rhino modeling guideline

1. Extract each accepted exterior host face and assign a stable elevation path.
2. Project structural levels and column lines onto the elevation as read-only datums.
3. Establish the facade base grid independently, then record every alignment or offset
   from structure.
4. Divide the elevation into typology-owned zones before generating openings.
5. Construct a small panel family: opaque, vision, spandrel, entrance and corner.
6. Apply score changes through grouped bay indices. Keep the start/end datums and major
   horizontal bands stable.
7. Resolve corners as one of three named conditions: wrapped datum, expressed vertical
   joint, or recessed return. Do not accept an accidental leftover strip.
8. At MTA-F2, model glazing, mullion/transom, opaque backing, floor-edge/spandrel,
   shading and support as separate systems.
9. Bake by facade zone and system with rule IDs, applied ratios and support metadata.

## Tectonic compatibility

- **Frame — native.** The frame enables free plan/free facade and clear grid comparison.
- **Tensile — poor as the primary envelope language.** It can appear as a bounded canopy
  or secondary shading layer while the main facade retains planar modular order.
- **Shell — conditional.** Use a rationalized shell with planar or developable facade
  zones; continuous free-form curvature weakens the grammar's core evidence.

## Typology notes

- **Library:** use regular daylight bands and deeper solar control at reading zones;
  protect archives and glare-sensitive spaces with opaque modules.
- **Theater:** keep auditorium and back-of-house zones more opaque; express foyer and
  circulation through controlled transparency rather than uniform glass.
- **Museum:** protect display walls and light-sensitive galleries; place transparency at
  circulation, lobby and framed-view moments.

## Validation

- at least 90% of non-boundary joints resolve to declared main/submodule datums;
- every exception names a program, corner, movement or score-interruption reason;
- the structural and facade grids are separately inspectable;
- the entrance is identifiable without color-only annotation;
- glazing ratios pass zone-specific daylight/privacy/acoustic warnings;
- a music change modifies only declared facade variables and preserves planar order,
  datum hierarchy and material-family limit;
- a reviewer can recover the base module and exception rule from elevation geometry.

## Limitations

This grammar models a selected operational subset. It does not represent every architect
included in the 1932 exhibition, resolve later critiques of universalism, or establish a
complete modern-envelope technical specification.

