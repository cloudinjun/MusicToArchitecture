# 09 — Critical Regionalism–informed Place-responsive Facade Grammar

## Scope and research basis

Kenneth Frampton's critical regionalism mediates universal technique and the specific
conditions of place. Topography, context, climate, light, tectonic form and tactile
experience are central. This project grammar requires evidence about the selected site,
climate, material culture and craft. It cannot run responsibly from a style name alone.

Canonical references for study, selected to show different regional negotiations:

1. Alvar Aalto, **Säynätsalo Town Hall**, 1949–1952.
2. Jørn Utzon, **Bagsværd Church**, 1968–1976.
3. Balkrishna Doshi, **Sangath**, 1978–1980.
4. Geoffrey Bawa, **Parliament of Sri Lanka**, 1979–1982.
5. Arup Associates, **Druk White Lotus School**, phased from 1998.

Primary sources:

- Kenneth Frampton, “Towards a Critical Regionalism: Six Points for an Architecture of
  Resistance,” in *The Anti-Aesthetic*, 1983.
- [Association of Collegiate Schools of Architecture, Re-Reading Critical Regionalism](https://www.acsa-arch.org/chapter/re-reading-critical-regionalism/)
- [Pritzker Prize, Balkrishna Doshi](https://www.pritzkerprize.com/laureates/balkrishna-doshi)
- [Archnet/Aga Khan Trust for Culture, Druk Pema Karpo Institute](https://www.archnet.org/sites/6326)
- [Archnet/Aga Khan Trust for Culture, New Baris Village](https://www.archnet.org/sites/2560)

## Execution prerequisite

Set grammar status to `blocked_missing_context` until the project has:

- geolocated site and topography;
- orientation, sun path and local climate file or documented climate assumptions;
- prevailing wind, rainfall and relevant seasonal extremes;
- surrounding urban/landscape morphology;
- locally available material/assembly candidates with source and maintenance notes;
- cultural/historical research reviewed by a human;
- declared community/user relevance and limits of representation.

## Facade thesis

The facade mediates climate, local light, topography, craft and contemporary building
systems. Depth, shade, porosity, material weathering and tactile thresholds grow from
place-specific evidence. Regional reference is transformed through performance and
tectonic logic rather than copied as a decorative motif.

## Invariants

- `CR-INV-01` — each major facade operation cites a site, climate, material, cultural or
  craft input.
- `CR-INV-02` — solar, rain, ventilation and privacy responses vary by orientation.
- `CR-INV-03` — local material/craft influence appears in assembly, module, depth or
  touch, not texture imagery alone.
- `CR-INV-04` — contemporary technical requirements remain visible in the rule record;
  vernacular reference cannot waive them.
- `CR-INV-05` — tactile and temporal qualities are reviewed at pedestrian zones.
- `CR-INV-06` — site specificity survives music changes.

## Legal variables and starting logic

Metric ranges must derive from evidence, so this guide defines calculation rules instead
of universal dimensions.

| Parameter | Required derivation |
|---|---|
| shading depth/spacing | solar altitude/azimuth, glazing target, orientation and program hours |
| opening ratio | daylight, ventilation, privacy, rain exposure, acoustic and program needs |
| screen porosity | view/privacy plus airflow and driving-rain assumptions |
| material module | local product/craft dimensions, transport, handling and structural support |
| sill/reveal/plinth depth | rain, splash, sun, tactile use, security and assembly |
| thermal mass/insulation expression | climate and selected wall system |
| color/finish | measured/photographic material palette and weathering review |

The score may modulate only a bounded interval remaining after environmental and
typology constraints are satisfied.

## Forbidden operations

- running the grammar without site/context inputs;
- copying a vernacular pattern as a universal ornament;
- labeling a generic timber/stone/brick texture as local material evidence;
- allowing music genre to infer culture, ethnicity or regional symbols;
- applying the same opening/shading rule to all orientations;
- claiming passive performance without analysis and declared assumptions.

## Shared Score channels

| Dimension | Mapping in this grammar |
|---|---|
| Hierarchy | emphasize a civic/public threshold using locally grounded depth/material/light |
| Repetition | repeat a material/craft or shading module |
| Variation | adapt that module by orientation, climate and program first, score second |
| Density | vary screen/shade density inside environmental performance bounds |
| Continuity | maintain material, shaded walkway, plinth or landscape datum |
| Interruption | court, breezeway, rain threshold, framed view or community entrance |
| Polyphony | coordinate universal frame/services with local enclosure/landscape systems |
| Tension / Release | move between protected shade and open local light/view |
| Tempo of Change | control frequency of bounded material/opening adaptation along movement |

## Grasshopper/Rhino modeling guideline

1. Validate the execution prerequisites and stop cleanly if any hard input is absent.
2. Build orientation, solar, wind/rain exposure, view/privacy and program zone maps as
   separate inspectable fields.
3. Create a material/assembly catalogue with source location, module, embodied/maintenance
   notes where known, craft process and geometric limits.
4. Select a contemporary wall concept and identify how local material/craft modifies its
   cladding, screen, mass, joints or thresholds.
5. Compute environmental legal domains before applying score fields.
6. Model pedestrian touch zones, shaded transitions, sills, screens and material depth;
   surface color maps alone are insufficient.
7. At MTA-F2/F3, document drainage, ventilation, thermal and movement paths for the
   selected assembly.
8. Produce orientation elevations, seasonal sun/shadow, rain-flow diagram and one
   1:20-equivalent material/threshold study.
9. Export every applied rule with context source and any unresolved cultural review.

## Tectonic compatibility

- **Frame — native.** Universal frame and place-specific infill/shading can demonstrate
  mediation clearly.
- **Tensile — conditional/native by climate and craft.** Strong for shade and airflow
  where local material/maintenance capacity supports it.
- **Shell — conditional/native by material tradition and environment.** Earth, masonry,
  concrete or gridshell approaches require site-specific construction evidence.

## Typology notes

- **Library:** daylight, shade, outdoor reading and material tactility can root the
  building; collection protection stays invariant.
- **Theater:** public forecourt, shaded foyer thresholds and local craft can mediate civic
  presence; acoustic enclosure remains a hard technical layer.
- **Museum:** local light and material can shape circulation/courts; conservation and
  curatorial neutrality constrain gallery facades.

## Validation

- context prerequisite coverage equals 100% before generation;
- every major facade object has at least one evidence-backed context binding;
- orientation responses differ where solar/rain maps differ, or document why they do not;
- local material claims include actual assembly/module data or remain marked `research`;
- score changes stay inside precomputed environmental legal domains;
- site/context inputs remain invariant in fixed-grammar music comparisons;
- removing context causes a validation stop, not a silent default.

## Limitations

This guide cannot select a regional identity for the user or certify cultural
appropriateness. Community knowledge, local consultants, measured climate data, material
suppliers and mockups are required for deeper claims.

