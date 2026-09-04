# 03 — Brutalism-informed Mass-and-Assembly Facade Grammar

## Scope and research basis

RIBA describes Brutalism through material, texture and construction, with expressive
form, mass and exposed services; its history includes concrete, steel, brick and wood.
This project grammar therefore centers material directness, program/circulation
legibility, deep mass and construction trace. Concrete is one available realization.

Canonical references:

1. Le Corbusier, **Unité d'Habitation, Marseille**, 1947–1952.
2. Alison and Peter Smithson, **Hunstanton School**, 1949–1954.
3. Denys Lasdun, **National Theatre, London**, 1963–1976.
4. Chamberlin, Powell and Bon, **Barbican Estate**, 1955–1982.

Primary sources:

- [RIBA, Brutalism in Architecture](https://www.riba.org/explore/riba-collections/architectural-styles/brutalism-movement/)
- [National Theatre Archive, Denys Lasdun & Partners drawings](https://catalogue.nationaltheatre.org.uk/CalmView/Record.aspx?id=TPC%2F5%2F4&src=CalmView.Catalog)
- [WBDG, Above Grade Wall Selection Guide](https://www.wbdg.org/files/pdfs/edg/bedg_agwsg.pdf)
- [Facade Tectonics Institute, Systems Thinking](https://www.facadetectonics.org/papers/systems-thinking)

## Facade thesis

The facade is read as mass, load, inhabited edge and construction. Deep reveals,
terraces, circulation, service elements and structural bays produce legibility at urban
and bodily scales. Surface texture records a material or fabrication process. A thin
cladding system may still support the grammar when its panelization, joints and support
are expressed honestly.

## Invariants

- `BR-INV-01` — facade composition has primary masses and secondary inhabited/service
  elements with measurable depth hierarchy.
- `BR-INV-02` — material expression corresponds to a declared process such as cast,
  board-formed, precast, masonry, bush-hammered or exposed steel assembly.
- `BR-INV-03` — major structure, circulation or program zones remain externally legible
  where the grammar claims their expression.
- `BR-INV-04` — openings appear as cuts, recesses or repeated inhabited modules rather
  than an unrelated graphic layer.
- `BR-INV-05` — facade weight and roughness cannot conceal drainage, joints, insulation
  or attachment needs at MTA-F2/F3.
- `BR-INV-06` — expressive scale includes human thresholds and touch zones; monumental
  mass alone is insufficient.

## Legal variables and starting ranges

Project-authored experiment defaults:

| Parameter | Starting range | Owner and use |
|---|---:|---|
| primary reveal depth | 0.35–1.80 m | grammar/solar/program |
| secondary texture relief | 0.01–0.08 m | material/fabrication |
| opening ratio by main mass | 0.10–0.45 | typology/environment |
| repeated inhabited bay | 1.8–4.8 m | tectonic/program |
| mass step/setback | 0.5–2.0 structural bays | hierarchy/interruption |
| board-form or panel module | 0.15–1.20 m | material/assembly |
| special monumental events | 1–3 per public elevation | grammar/human acceptance |

## Forbidden operations

- applying a grey concrete material to an otherwise unresolved box and declaring success;
- generating random deep cuts with no room, circulation, structure or solar role;
- using texture maps to imply joints or formwork that have no geometric/module record;
- hiding a lightweight rainscreen behind claims of monolithic load-bearing mass;
- eliminating human-scale entries, handrails, thresholds and window depth;
- allowing score modulation to perforate an auditorium, archive or gallery wall beyond
  typology limits.

## Shared Score channels

| Dimension | Mapping in this grammar |
|---|---|
| Hierarchy | primary mass depth, entrance cut, tower/service emphasis or terrace sequence |
| Repetition | inhabited bays, precast units, structural frames or board-form lines |
| Variation | bounded changes in recess depth, bay width or balcony projection |
| Density | frequency of deep openings, ribs or service/circulation elements |
| Continuity | continuous datum, terrace, structural beam or material pour/panel sequence |
| Interruption | large void, stair tower, recessed entrance or deliberate missing bay |
| Polyphony | mass, frame, circulation and texture operate as distinct coordinated layers |
| Tension / Release | compressed shadowed cuts lead to open terraces or large public voids |
| Tempo of Change | rate of bay-depth and solid/void changes along a circulation-facing elevation |

## Grasshopper/Rhino modeling guideline

1. Begin with accepted solid massing and identify load-bearing/primary structure,
   circulation, public rooms, service cores and environmental zones.
2. Generate facade through boolean cuts, mass steps, inhabited bays and terraces. Keep
   the pre-operation host and transformation record for traceability.
3. Tie each opening/cut to a room, route, view, ventilation or daylight requirement.
4. Model primary mass, window/recess liners, balustrades, service elements and texture/
   panel modules as separate sublayers.
5. Use geometry for major formwork/panel joints and surface shaders for fine grain only.
6. At MTA-F2, choose a declared wall concept: structural concrete, precast/drained
   assembly, masonry cavity wall, or exposed frame with infill. The model and labels must
   match that concept.
7. Generate section cuts through typical opening, base, parapet and mass transition;
   Brutalist evidence requires sectional depth.
8. Report standard/special panel or formwork counts and every unsupported cantilever/
   projection warning.

## Tectonic compatibility

- **Frame — native/conditional.** Exposed steel or concrete frames and infill can be
  legible; deep precast or cast elements require clear load paths.
- **Tensile — poor as the main grammar.** A tensile insert may create a contrasting public
  event but cannot carry the mass-and-material identity alone.
- **Shell — native when material and force are expressed.** Folded, ribbed or continuous
  concrete shells can support deep sectional and tectonic evidence.

## Typology notes

- **Library:** repeated reading bays, terraces and cores can express use; archives need
  protected mass and careful moisture detailing.
- **Theater:** auditorium/stage mass, foyer terraces, stairs and service towers offer
  strong program legibility; acoustic needs govern openings.
- **Museum:** galleries may be solid masses with calibrated deep openings; circulation
  and public terraces can articulate sequence without sacrificing display walls.

## Validation

- every major opening/cut has a program/environment rule and host ID;
- mass-depth hierarchy is visible in section and exceeds texture-only relief;
- material/process labels match actual geometry and assembly type;
- structure/circulation claims are recoverable from facade objects and IDs;
- no panel or formwork module terminates in an unreasoned sliver at corners/openings;
- music changes legal cadence/depth variables while preserving material process, primary
  mass hierarchy and typology-owned opaque zones;
- monochrome clay and line-section views retain grammar identity without concrete color.

## Limitations

This grammar does not claim that mass or exposed concrete guarantees durability,
sustainability or social value. Material carbon, weathering, staining, thermal bridging
and repair need separate evaluation when a real assembly is selected.
