# 05 — High-tech–informed Legible Assembly Facade Grammar

## Scope and research basis

High-tech architecture makes construction, circulation, services, change and industrial
assembly architecturally legible. Centre Pompidou externalizes structure, circulation
and services to preserve flexible interior floors and uses a functional color code. The
Sainsbury Centre places structure and services in a double-layer envelope. These
references show multiple valid configurations; external pipes are only one strategy.

Canonical references:

1. Renzo Piano, Richard Rogers and Gianfranco Franchini, **Centre Pompidou**, 1971–1977.
2. Norman Foster, **Sainsbury Centre for Visual Arts**, 1974–1978.
3. Richard Rogers, **Lloyd's Building**, 1978–1986.
4. Nicholas Grimshaw, **Vitra Factory Building**, 1981–1983.

Primary sources:

- [Centre Pompidou, An Iconic Architecture](https://www.centrepompidou.fr/en/centre-pompidou-is-transforming-itself/an-iconic-architecture)
- [Centre Pompidou, Structure and Modules](https://www.centrepompidou.fr/fr/offre-aux-professionnels/enseignants/dossiers-ressources-sur-lart/larchitecture-du-centre-pompidou/structure-et-modules)
- [Centre Pompidou, architectural systems and free floors](https://mediation.centrepompidou.fr/education/ressources/ENS-architecture-Centre-Pompidou/comment_ca_fonctionne/p1.htm)
- [Foster + Partners, Sainsbury Centre for Visual Arts](https://www.fosterandpartners.com/projects/sainsbury-centre-for-visual-arts)
- [Facade Tectonics Institute, Coupling Facade and Structure](https://www.facadetectonics.org/papers/coupling-facade-and-structure)

## Facade thesis

The facade is an organized assembly of structure, enclosure, circulation, services,
shading and replaceable components. Each visible element has a real system role. A
regular kit of parts permits maintenance, change and expansion. Color, depth and
connection details communicate ownership and load/service routes.

## Invariants

- `HT-INV-01` — every visible technical element has a system classification and actual
  architectural function.
- `HT-INV-02` — a repeated structural/assembly module organizes the facade.
- `HT-INV-03` — primary, secondary and enclosure systems remain independently
  inspectable and carry stable IDs.
- `HT-INV-04` — connections, brackets, edge members or system interfaces are modeled at
  the declared development stage.
- `HT-INV-05` — replaceability/maintenance logic is documented for repeated components.
- `HT-INV-06` — color, when used, maps to a function through a project legend.

## Legal variables and starting ranges

Project-authored experiment defaults:

| Parameter | Starting range | Owner and use |
|---|---:|---|
| primary assembly bay | 3–9 m | tectonic/structure |
| enclosure submodule | 0.75–1.8 m | assembly |
| facade system depth | 0.6–2.4 m | system routing/maintenance |
| visible secondary-member density | 1–5 members per bay | grammar/score, structural clamp |
| external circulation share | 0–35% of public facade length | program/human |
| color-coded system families | 0–5 | grammar; functional legend required |
| standard component share | ≥ 80% at MTA-F2 | assembly target |

## Forbidden operations

- decorative ducts, trusses, bolts or brackets with no system function;
- color coding that changes meaning between elevations or runs;
- one merged mesh that prevents inspection of structure, services and enclosure;
- exposing equipment without maintenance, drainage, weathering or safety consideration;
- allowing score values to resize structural members or service routes outside their
  engineering authority;
- claiming flexibility when partitions, services and circulation cannot support change.

## Shared Score channels

| Dimension | Mapping in this grammar |
|---|---|
| Hierarchy | enlarge or foreground the primary structural/circulation bay |
| Repetition | repeat truss, gerberette, mullion, cassette, service or connection modules |
| Variation | choose bounded component-family variants with common interfaces |
| Density | vary visible secondary members, fins or service-expression frequency |
| Continuity | keep service routes, catwalks, rails or structural chords continuous |
| Interruption | service node, transfer bay, entry machine, missing module or maintenance zone |
| Polyphony | structure, circulation, services and enclosure form independent readable voices |
| Tension / Release | alternate dense serviced bays with open flexible/public bays |
| Tempo of Change | set frequency of component-family substitution along the kit-of-parts grid |

## Grasshopper/Rhino modeling guideline

1. Build a system graph before geometry: primary structure, secondary support,
   enclosure, service family, circulation, shading and maintenance access.
2. Establish primary structural bays and derive enclosure submodules.
3. Create reusable component definitions with ports/interfaces: start/end frames,
   support points, clearance zones, material, family ID and replaceability metadata.
4. Instantiate components from data; avoid duplicating custom geometry per bay.
5. Route service/circulation curves only after clash zones and facade depth are defined.
6. Generate brackets and connection nodes at MTA-F2 as simplified but countable objects.
7. Apply score modulation to component selection or density; structural/member sizing
   remains owned by the tectonic/engineering layer.
8. Produce exploded assembly, system-isolation and maintenance-access views.
9. Bake each system to deterministic layers and write a component schedule.

## Tectonic compatibility

- **Frame — native.** Repeated bays, external frames and component interfaces align well.
- **Tensile — native/conditional.** Cables and membranes can be expressed as a technical
  assembly when force, boundary and replacement logic are real.
- **Shell — conditional.** Use gridshell, space-frame or panelized shell systems with
  legible nodes; an apparently seamless sculptural shell weakens assembly evidence.

## Typology notes

- **Library:** flexible reading floors and visible circulation fit; noisy services and
  glare require control near quiet/reading zones.
- **Theater:** stage/service infrastructure and public circulation offer strong evidence;
  acoustic enclosure and fire/smoke strategy limit exposure.
- **Museum:** flexible floors and maintenance logic are useful; gallery climate control
  and light-sensitive enclosure require clear separation from public technical display.

## Validation

- 100% of visible technical elements have functional system tags;
- all facade components resolve to valid support/interface ports;
- standard versus special component counts are reported;
- no service/circulation route enters a declared structure, egress or maintenance clash zone;
- function-color legend is one-to-one or explicitly documents shared colors;
- score changes modify allowed family/density selections while preserving interfaces,
  routing continuity and tectonic limits;
- exploded and assembled models produce matching IDs and component counts.

## Limitations

The grammar models legible technical organization and does not verify actual mechanical,
electrical, fire, structural or maintenance engineering. Exposed systems can add energy,
material and weathering burdens that require later evaluation.

