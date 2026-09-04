# 08 — Minimalism-informed Reductive Facade Grammar

## Scope and research basis

Architectural minimalism is a broad attitude rather than one institutionally fixed
movement. This project grammar draws from Tadao Ando's reduction of material and his use
of boundaries, light and shadow; it also learns from precise modern assemblies such as
the Barcelona Pavilion. Reduction is evaluated through proportion, material continuity,
joint discipline, light and removal of nonessential elements.

Canonical references:

1. Tadao Ando, **Church of the Light**, 1987–1989.
2. Tadao Ando, **Chichu Art Museum**, 1999–2004.
3. Tadao Ando, **Conference Pavilion, Vitra Campus**, 1989–1993.
4. Ludwig Mies van der Rohe and Lilly Reich, **Barcelona Pavilion**, 1929.

Primary sources:

- [Pritzker Prize, Tadao Ando](https://www.pritzkerprize.com/laureates/1995)
- [Benesse Art Site Naoshima, Chichu Art Museum](https://benesse-artsite.jp/en/art/chichu.html)
- [Benesse, Chichu Art Museum works/materials](https://benesse-artsite.jp/en/contact/press/BASN_MediaKit_April2018_GenerallPress_eng.pdf)
- [Fundació Mies van der Rohe, Barcelona Pavilion](https://miesbcn.com/the-pavilion/)
- [WBDG, Building Envelope Design Guide](https://www.wbdg.org/files/pdfs/edg/bedg_agwsg.pdf)

## Facade thesis

The facade uses the fewest necessary planes, openings, materials and joints to produce
clear proportion and controlled light. Each remaining element gains importance. Flush,
recessed and shadow-gap conditions require high geometric and assembly precision. A
quiet elevation may contain substantial sectional depth and technical coordination.

## Invariants

- `MI-INV-01` — the facade uses a declared limited material family and joint hierarchy.
- `MI-INV-02` — all visible openings and joints align to primary or secondary datums.
- `MI-INV-03` — every projecting, recessed or accent element has a program, light,
  drainage, structure or transition purpose.
- `MI-INV-04` — material continuity is preserved across ordinary bays; exceptions mark
  significant thresholds.
- `MI-INV-05` — light and shadow are tested in section/time, not represented only by
  render exposure.
- `MI-INV-06` — reduction cannot delete required protection, flashing, movement or
  maintenance access; technical layers may be concealed only when their continuity is
  documented.

## Legal variables and starting ranges

Project-authored experiment defaults:

| Parameter | Starting range | Owner and use |
|---|---:|---|
| primary material families | 1–3 | grammar/human |
| visible joint families | 1–2 | assembly |
| primary opening families | 1–3 | grammar/program |
| reveal depth | 0.10–0.90 m | light/program |
| shadow joint | 0.01–0.05 m at MTA-F2 | assembly placeholder |
| facade accent area | 0–8% | hierarchy/human |
| score-driven dimensional variation | ±0–12% | intentionally low amplitude |

## Forbidden operations

- assuming a white material and sparse openings satisfy the grammar;
- hiding misaligned panels or accidental slivers behind a continuous shader;
- adding many small score-driven variations that create visual noise;
- using zero-thickness planes at MTA-F2;
- treating missing flashing, drip, movement or access as aesthetic purity;
- mixing material families without a threshold or assembly reason.

## Shared Score channels

| Dimension | Mapping in this grammar |
|---|---|
| Hierarchy | one dominant opening, plane, void or light cut |
| Repetition | exact joint, opening or panel cadence |
| Variation | rare bounded change in width, depth or spacing |
| Density | adjust subdivision only within a narrow low-noise range |
| Continuity | preserve material plane, datum and joint alignment |
| Interruption | one shadow gap, court, slit or recessed threshold |
| Polyphony | coordinate a small number of layers, such as opaque plane and glass plane |
| Tension / Release | move between deep shadow and calibrated light/open view |
| Tempo of Change | usually low; controls distance between rare exceptions |

## Grasshopper/Rhino modeling guideline

1. Establish primary proportions and facade datums before panelization.
2. Create an element inventory and justify every family; delete nonessential families
   before adding detail.
3. Generate openings as a small named set and align them to program and light vectors.
4. Model actual facade depth, reveals and plane offsets. Avoid coplanar material changes
   when a joint or return is intended.
5. Create a joint graph before splitting panels; align ordinary joints across corners and
   systems where the assembly permits.
6. Apply score variation only after the base composition passes. Use sparse event masks
   and low amplitude limits.
7. At MTA-F2, include simplified cavity/support, edge returns, base, parapet and opening
   transitions even if presentation views conceal them.
8. Produce elevation, large-scale corner/opening views and sun/shadow studies.
9. Run an automatic stray-edge/sliver/duplicate-material audit before baking.

## Tectonic compatibility

- **Frame — native.** Precise bays and independent planes are straightforward when
  structure/envelope alignment is controlled.
- **Tensile — conditional.** A highly reduced membrane/cable system can work, but node
  and edge complexity must be honestly included.
- **Shell — native/conditional.** A continuous material shell with precise cuts supports
  reduction; panel/joint rationalization cannot be omitted.

## Typology notes

- **Library:** prioritize soft daylight, calm cadence and clear entry; shelves/archive
  needs determine opacity.
- **Theater:** a restrained public face may emphasize one foyer/entrance cut; life-safety
  and back-of-house openings remain explicit in technical drawings.
- **Museum:** controlled top/side light and uninterrupted display zones align well; an
  iconic single opening cannot compromise conservation requirements.

## Validation

- material, opening and visible-joint family counts stay within declared limits;
- 100% of ordinary joints align to declared datums or named transition rules;
- no unreasoned sliver panels, duplicate faces or near-coplanar offsets;
- shadow/light hierarchy remains visible in neutral clay renders at multiple sun times;
- score change affects a sparse declared subset and preserves material/joint continuity;
- concealed technical layers remain traceable in section and metadata;
- deleting any accent element either improves reduction or removes a declared function;
  the review records that decision.

## Limitations

Minimal appearance often demands high construction quality and cost. The guide cannot
claim feasibility until tolerances, mockups, material samples, drainage and maintenance
are evaluated.

