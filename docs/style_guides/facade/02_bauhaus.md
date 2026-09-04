# 02 — Bauhaus-informed Functional Modular Facade Grammar

## Scope and research basis

Bauhaus changed across Weimar, Dessau and Berlin and cannot be compressed into one visual
formula. This project grammar focuses on the Dessau period's relationship among program,
industrial production, modular construction, transparency, movement around the building
and color as an architectural/wayfinding material.

Canonical references:

1. Walter Gropius, **Bauhaus Building, Dessau**, 1925–1926.
2. Walter Gropius, **Masters' Houses**, 1925–1926.
3. Hannes Meyer and Hans Wittwer, **ADGB Trade Union School**, 1928–1930.
4. Hannes Meyer and the Bauhaus building department, **Houses with Balcony Access**, 1930.

Primary sources:

- [Bauhaus Dessau Foundation, Bauhaus Building](https://bauhaus-dessau.de/en/venues/bauhaus-building/)
- [Bauhaus Dessau Foundation, Masters' Houses](https://bauhaus-dessau.de/en/venues/masters-houses/)
- [Bauhaus Dessau Foundation, Houses with Balcony Access](https://bauhaus-dessau.de/en/venues/houses-with-balcony-access/)
- [UNESCO, Bauhaus and its Sites](https://whc.unesco.org/en/list/729)
- [UNESCO, Bauhaus Dessau Conservation Management Plan](https://whc.unesco.org/document/207227)

## Facade thesis

The facade makes functional organization, construction module and movement legible.
Different program wings may receive different envelope types while a common module,
material discipline and color system keeps the ensemble coherent. Transparency has a
specific program role. The whole building may require movement around it to understand;
there is no requirement for one symmetrical front.

## Invariants

- `BH-INV-01` — facade types are assigned by program/use and documented in a program-to-
  envelope table.
- `BH-INV-02` — industrial modules, repeatable parts and assembly logic are visible.
- `BH-INV-03` — volume differences preserve program hierarchy rather than becoming a
  decorative collage.
- `BH-INV-04` — transparency is concentrated where collective work, circulation or
  public activity benefits from visual connection.
- `BH-INV-05` — color supports orientation, structure or spatial grouping; it cannot be
  distributed as untracked decoration.
- `BH-INV-06` — white plaster, glass and primary-color accents are optional references;
  the grammar remains identifiable through program, module and assembly without them.

## Legal variables and starting ranges

Project-authored experiment defaults:

| Parameter | Starting range | Owner and use |
|---|---:|---|
| standard module | 0.6–1.5 m | grammar/assembly |
| module grouping | 2–8 units | score-eligible repetition/hierarchy |
| workshop/public curtain-wall ratio | 0.55–0.85 | typology/environment clamp |
| service/collection opaque ratio | 0.65–0.95 | typology-owned |
| stair/circulation vertical glass width | 1–3 modules | program/grammar |
| facade color accent | 0–10% of area | orientation/structure only |
| connector/bridge setback | 0.5–2.0 modules | hierarchy/interruption |

## Forbidden operations

- making every program volume the same white-and-glass box;
- assigning transparency by score before daylight, privacy and acoustic needs;
- using primary colors without a system role or legend;
- forcing a single axial/symmetrical primary elevation;
- hiding all standard-part logic inside one continuous surface;
- presenting a curved parametric skin as Bauhaus solely through a red-yellow-blue palette.

## Shared Score channels

| Dimension | Mapping in this grammar |
|---|---|
| Hierarchy | select which functional wing receives the most transparent or largest grouped bay |
| Repetition | repeat standard windows, balcony access, curtain-wall or studio modules |
| Variation | rotate/group volumes or change module family by program within a shared kit |
| Density | alter mullion, balcony or opaque-panel subdivision inside a facade type |
| Continuity | extend a curtain wall, balcony line or color datum through connected zones |
| Interruption | bridge, recessed connector, stair strip or missing module at a threshold |
| Polyphony | allow program volumes, facade module and color/orientation system to operate as coordinated layers |
| Tension / Release | move from opaque service wing to transparent collective/public wing |
| Tempo of Change | control the frequency of facade-type transitions along circulation |

## Grasshopper/Rhino modeling guideline

1. Read program categories and split massing into functional volumes before facade work.
2. Build a reusable kit of facade types: curtain wall, punched-window wall, studio window,
   circulation strip, balcony/access gallery, opaque service wall and bridge/connector.
3. Assign types through data, never by manual face selection that cannot be reproduced.
4. Establish one module family and allow named multiples/submultiples only.
5. Model curtain wall with a distinct support grid, transparent infill and opaque floor-
   edge condition; retain view of structure only where the selected assembly permits it.
6. Attach a small color-role enum such as `orientation`, `circulation`, `structure` or
   `program_group`. Reject color with no role.
7. Generate an orbit/elevation sequence so the ensemble is evaluated from multiple
   sides, reflecting the Dessau Building's non-central reading.
8. At MTA-F2, separate standardized repeatable parts from boundary/corner specials and
   report their counts.

## Tectonic compatibility

- **Frame — native.** Repeatable bays, curtain wall and program-separated volumes align
  directly with a frame system.
- **Tensile — conditional.** Limit to canopies, connectors or assembly experiments with
  a clearly stated functional role.
- **Shell — conditional to poor.** A modular folded or plate shell may be explored;
  continuous expressive shells conflict with the current grammar's part/assembly logic.

## Typology notes

- **Library:** reading rooms may receive modular daylight facades; stacks/archive/service
  require controlled opaque walls; circulation color can aid orientation.
- **Theater:** public foyer transparency and circulation strips can reveal collective
  movement; auditorium and stage volumes remain materially direct and largely opaque.
- **Museum:** workshop/education/public zones may be transparent; galleries use a more
  controlled facade type; connectors can mark curatorial sequence.

## Validation

- every facade type resolves to a program role and every color resolves to a declared role;
- at least 80% of non-boundary pieces use standard repeatable families at MTA-F2;
- special parts occur at named corners, transitions, openings or score interruptions;
- the ensemble remains understandable from at least four exterior viewpoints;
- replacing music changes grouping/density/interruption but preserves program-to-facade
  assignment, module family and material/assembly logic;
- a monochrome test still reads as the same grammar, proving color is supporting evidence.

## Limitations

The guide does not describe the whole Bauhaus institution, pedagogy or politics. It uses
a bounded facade grammar suitable for the project's program/assembly experiment and
should be labeled accordingly in public material.

