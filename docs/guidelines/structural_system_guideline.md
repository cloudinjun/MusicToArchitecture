# Structural System Guideline

Status: design guideline, 2026-08-27  
Authority: project-level contract subordinate to `PROJECT_CHARTER.md`, decision 0002,
the selected tectonic/material profile, and the project jurisdiction code profile

## 1. Purpose and evidence target

This guideline is the **shared contract** obeyed by all ten executable structural
systems in [`structural_systems/`](./structural_systems/README.md), whichever one is
selected. It makes structural generation materially different across CLT/mass timber,
light wood, glulam post-and-beam, structural steel, reinforced concrete, tensile
membrane, cable net, and the three shell systems. Each model must expose an inspectable load
path, system-specific geometry, program negotiations, validation results, stable
element IDs, rule sources, and provenance.

The portfolio evidence is the ability to:

- translate program needs into structural constraints across scales;
- select and execute a coherent system profile;
- coordinate gravity, lateral, diaphragm, core, facade-support, and foundation roles;
- reject or repair unsupported spans, discontinuities, prohibited columns, missing
  anchors, incompatible openings, and unresolved code inputs;
- repeat a run from the same brief, score, profiles, seed, and software versions.

Generated sections and sizes are schematic or preliminary until an implemented
analysis and a qualified engineer verify them. Passing project validators does not
constitute professional structural approval.

## 2. Two-axis classification

Decision 0002 retains three first-round tectonic families. Material and construction
subtypes form a separate axis.

| `tectonic_family` | Supported profile candidates | Distinct geometric behavior |
|---|---|---|
| `frame` | mass timber CLT + glulam, glulam post-and-beam, light wood, steel, reinforced concrete | discrete supports, spanning members or plates, diaphragm, lateral system, foundations |
| `tensile` | tensile membrane, cable net, cable-supported hybrid | form-found tension surface/cable families, masts or boundary frame, prestress, anchors |
| `shell` | reinforced-concrete shell, timber gridshell, steel space-frame shell | continuous or networked load-bearing surface, curvature, edge conditions, openings, buckling/stability |

CLT is a panel product and may serve floors, roofs, or walls inside a mass-timber
profile. “Wood structure” must resolve to light-frame, post-and-beam, mass timber, or a
declared hybrid because their grids, spans, connections, diaphragms, fire behavior,
fabrication, and modeling logic differ.

Only one family/profile pair is implemented to portfolio depth after the selection
study. Other profiles remain specification-ready comparison candidates.

## 3. Structural code-profile gate

Every accepted structural run references a resolved profile:

```yaml
structural_code_profile:
  id: STR-CODE-US-LOCAL-PLACEHOLDER
  jurisdiction: null
  adopted_building_code: null
  local_amendments: []
  risk_category: null
  occupancy_refs: []
  design_load_standard: null
  material_standards: []
  seismic_design_inputs: null
  wind_design_inputs: null
  snow_rain_flood_inputs: null
  fire_resistance_requirements: null
  soils_geotechnical_report_ref: null
  special_inspection_requirements: []
  source_urls: []
  status: unresolved
```

The currently published standard and the locally adopted standard may differ. The
generator records both when useful and calculates only from the declared adopted
profile. Missing site hazard, soil, occupancy, fire, or material inputs produce
`review_required` or `blocked`, never invented loads or capacities.

## 4. System profile contract

```yaml
structural_profile:
  id: STR-PROFILE-MASS-TIMBER-001
  tectonic_family: frame
  material_system: mass_timber_clt_glulam
  gravity_system:
    vertical_support: glulam_columns
    primary_span: glulam_beams
    secondary_span: clt_panels
    panel_span_direction_rule: shortest_feasible_with_program_exceptions
  lateral_system:
    type: unresolved
    diaphragm: clt_diaphragm_candidate
    collectors_and_chords: required
  foundation_system:
    type: unresolved_pending_soils
  connection_family:
    beam_column: conceptual
    panel_support: conceptual
    hold_down: unresolved
  constraints:
    span_limits: []
    fire_design: unresolved
    moisture_class: unresolved
    vibration_limits: unresolved
  code_profile_ref: STR-CODE-US-LOCAL-PLACEHOLDER
  rule_refs: []
  provenance: []
  status: candidate
```

No span, depth, thickness, bay size, or connection capacity becomes authoritative
without a source, units, applicability, and verification method.

## 5. Structural element contract

Every generated object is an element in a connected structural graph:

```yaml
id: STR-L02-BEAM-017
semantic_layer: structure
role: primary_span
element_type: glulam_beam
material_profile_ref: STR-PROFILE-MASS-TIMBER-001
level_id: L02
geometry_ref: GEO-004921
section:
  family: rectangular
  dimensions_m: [null, null]
  sizing_status: unresolved
supports: [STR-L02-COL-006, STR-L02-COL-007]
supports_elements: [STR-L02-PANEL-012]
load_path_to_foundation: []
program_constraints: [SP-L02-GALLERY-001]
score_bindings: []
rule_refs: []
reason: spans gallery edge while respecting column-exclusion zone
authority: generated_candidate
provenance: []
validation_status: review_required
```

Required fields include stable ID, semantic role, material/system profile, geometry,
level, supports, supported elements, load-path trace, program constraints, rule refs,
reason, authority, provenance, and validation status.

## 6. Common generation sequence

1. **Read accepted program state.** Consume space types, levels, occupancy/load classes,
   clear spans, column policies, openings, cores, wet/service stacks, facade support,
   and key interior sequence.
2. **Resolve structural and code profiles.** Select family, material subtype, lateral
   concept, fire/construction constraints, loads, hazards, and foundation assumptions.
3. **Generate topology.** Create supports, spans/surfaces, diaphragms, lateral system,
   collectors/chords, cores where structural, and foundation/anchor nodes.
4. **Trace gravity load path.** Every deck, roof, beam, wall, column, mast, cable, shell,
   and transfer element reaches a foundation or anchor through explicit edges.
5. **Trace lateral load path.** Diaphragms or surfaces connect to the declared lateral
   system, collectors/chords, vertical elements, and foundations/anchors.
6. **Resolve discontinuities.** Openings, cantilevers, column removals, transfer levels,
   facade reactions, and program exclusion zones receive a system-specific solution.
7. **Preliminary sizing.** Generate sourced candidate families or run an implemented
   solver; clearly label heuristic and unresolved sizes.
8. **Validate and repair.** Run common and profile-specific gates; keep a full change log.
9. **Publish accepted design state.** Export semantic collections and validation data;
   preserve the prior state when the new run fails.

## 7. Per-system modeling logic (N choose 1)

The per-system rules that used to live in this section are now **ten independent
guidelines**, one per executable structural system, in
[`docs/guidelines/structural_systems/`](./structural_systems/README.md). Exactly one
system is implemented to portfolio depth; the other nine stay specification-ready
comparison candidates.

| ID | System | Family | Primitives beyond decision 0008 |
|---|---|---|---|
| 01 | [Structural steel frame](./structural_systems/01_steel_frame.md) | frame | none |
| 02 | [Reinforced concrete frame and wall](./structural_systems/02_reinforced_concrete_frame_wall.md) | frame | none |
| 03 | [Mass timber: CLT on glulam](./structural_systems/03_mass_timber_clt_glulam.md) | frame | none |
| 04 | [Glulam post-and-beam](./structural_systems/04_glulam_post_and_beam.md) | frame | none |
| 05 | [Light wood frame](./structural_systems/05_light_wood_frame.md) | frame | `element_group` compaction required |
| 06 | [Tensile membrane](./structural_systems/06_tensile_membrane.md) | tensile | `mesh_surface` + form-finding stage |
| 07 | [Cable net and cable-supported hybrid](./structural_systems/07_cable_net_hybrid.md) | tensile | `member.pretension` + solver stage |
| 08 | [Reinforced concrete shell](./structural_systems/08_reinforced_concrete_shell.md) | shell | `mesh_surface` + variable thickness |
| 09 | [Timber gridshell](./structural_systems/09_timber_gridshell.md) | shell | curved `member.path` + bend radius |
| 10 | [Steel space frame and gridshell](./structural_systems/10_steel_space_frame_shell.md) | shell | none |

The selection protocol, cross-candidate analysis, geometry-primitive requirement matrix,
shared score-to-structure channels, system contract schema, and MTA-S modeling stages are
in that folder's [README](./structural_systems/README.md). This document remains the
shared contract that every system obeys regardless of which one is selected: the code
profile gate (section 3), the profile and element contracts (sections 4-5), the common
generation sequence (section 6), program negotiation (section 8), common validation
gates (section 9), and the compliance vocabulary (section 10).

A guideline is split out as its own system when its **element taxonomy, required geometry
primitives, and validation gates** are all materially different. Two material variants
that share all three belong in one guide. Use that test before adding an eleventh.

## 8. Program–structure negotiation

Structure consumes detailed `space_type` and requirements rather than broad color
alone.

| Program condition | Structural response |
|---|---|
| auditorium, stage, key gallery, major reading room | declare clear-span range and column-prohibition/coordination zone |
| public circulation, egress aisle, door, accessible clearance | hard geometric exclusion unless a reviewed exception exists |
| collection storage, stacks, archives, workshop, mechanical | assign sourced load class and flag high/concentrated loads |
| loading/receiving | coordinate vehicle/service clearances, slab/foundation load class, impact where applicable |
| toilets, janitor, wet service | coordinate penetrations and stack zones; do not cut primary members silently |
| core, riser, shafts | align openings and lateral/vertical systems across levels |
| facade/envelope | publish support points, allowable movement, edge reactions, and substructure zones |
| key interior sequence | control visible structural rhythm, depth, and obstruction while preserving the load path |

When a requested clear span exceeds the selected profile’s supported method, the
compiler may choose a declared long-span subtype, propose a program change, or fail.
It cannot enlarge a legacy beam depth without evidence.

## 9. Common validation gates

### Topology and geometry

- every gravity element has a continuous support path to foundation;
- every lateral element connects diaphragm/surface, collectors/chords, vertical system,
  and foundation/anchor;
- no floating columns, beams, panels, shells, cables, walls, masts, or foundations;
- columns/walls align across levels or a named transfer element resolves the offset;
- spans, cantilevers, openings, and support spacing remain within sourced profile limits;
- no element intersects a program exclusion, egress, accessible clearance, or required
  service path without a recorded negotiation.

### Loads and serviceability

- load cases and combinations come from the adopted profile;
- occupancy-specific live/load classes remain linked to program spaces;
- wind, seismic, snow, rain/ponding, flood, soil, and fire conditions are resolved or
  visibly pending according to site and system applicability;
- strength, drift, deflection, vibration, stability/buckling, and robustness checks show
  method, inputs, units, result, limit, and confidence;
- facade, equipment, concentrated, transfer, and anchor reactions are included or
  marked unresolved.

### Material/system integrity

- selected material standard, grade/product class, section/layup, connection family,
  durability/exposure, fire strategy, and fabrication assumptions are recorded;
- profile-specific checks in Section 7 pass;
- hybrid systems expose responsibility at each interface.

### Workflow integrity

- every structural element has stable ID, role, source constraints, rule refs, reason,
  authority, provenance, and validation status;
- seed, input hashes, profile versions, solver version, tolerances, and software versions
  are recorded;
- failures preserve the last accepted design state and publish a machine-readable report.

## 10. Compliance vocabulary

Use these labels consistently:

| Status | Meaning |
|---|---|
| `geometry_valid` | schema/topology/geometric project checks passed |
| `rule_checked` | named rule evaluated using recorded inputs and method |
| `analysis_checked` | named structural analysis ran and met its declared criterion |
| `code_inputs_incomplete` | adopted profile, hazards, use, soil, fire, or material data missing |
| `professional_review_required` | structural engineer or other qualified professional must verify |
| `design_accepted` | project pipeline accepted this version for downstream coordination |

Do not emit `code_compliant`, `safe`, `permit_ready`, or `engineer_approved` unless the
project later establishes an authorized certification workflow that genuinely supports
the statement.

## 11. Legacy extraction record

| Legacy behavior in `Blender/structural_generator.py` | Guideline treatment |
|---|---|
| grid generated relative to two cores | retain the idea that structure responds to accepted core/program anchors |
| columns kept only where current/upper slabs support continuity | retain as load-path topology check |
| selected public-space columns removed when a 12 m heuristic allowed it | retain column-exclusion negotiation; replace 12 m with profile-specific verified limits |
| transfer beams created below discontinuous upper columns | retain with explicit supports, reactions, and validation |
| deeper perimeter beams added around column-free public rooms | retain as one frame repair candidate, never a universal response |
| slabs generated from program footprints | retain footprint coordination; add real panel/slab direction, supports, openings, and system logic |
| two cores, bracing, stairs, and elevator generated together | separate architectural circulation, structural lateral role, and material choice |
| element metadata contains category/type/floor/location/dimensions/reason | extend to stable IDs, graph edges, rules, authority, and provenance |
| 6 m grid; 12 m retained span; 0.15 m CLT slab; 0.3/0.4/0.8 m member dimensions | legacy heuristics only until sourced and analyzed |
| fixed core coordinates, floors, material assignment, and absolute paths | remove from portable rules |
| comments/doc mix concrete cores and steel bracing while code creates CLT cores and glulam bracing | eliminate through one versioned structural profile as source of truth |

Additional reviewed sources:

- `Blender/clt_building_generator.py`
- `Blender/LOGIC.md`

No legacy geometry, fixed coordinates, or absolute paths were copied.

## 12. Initial verification fixtures

1. **Mass-timber gallery:** a gallery column-exclusion zone forces a sourced long-span
   option, transfer solution, or failure; every CLT panel has support and span direction.
2. **Steel theater:** the auditorium selects a declared long-span topology and preserves
   continuous lateral bays outside audience/egress conflicts.
3. **Concrete opening conflict:** an opening near a column/punching zone, wall, slab band,
   or collector fails until shifted or structurally repaired.
4. **Tensile missing anchor:** a membrane/cable result without prestress, reactions,
   anchors, or foundations fails hard.
5. **Shell interruption:** an opening that breaks the shell path requires a reinforced
   edge/boundary solution and a new stability check.
6. **Profile substitution:** the same stable program IDs under mass timber, steel, and
   reinforced-concrete comparison profiles produce different structural element graphs;
   program provenance remains intact.
7. **Repeatability:** identical inputs, profiles, seed, and versions reproduce element
   IDs, topology, and validation results within declared geometric tolerance.

## 13. Official reference baseline

These current official sources establish the initial U.S. reference registry. The
adopted jurisdiction profile decides the applicable edition and amendments.

### General, loads, fire, and construction type

- [ASCE/SEI 7-22: Minimum Design Loads and Associated Criteria](https://www.asce.org/publications-and-news/codes-and-standards/asce-sei-7-22)
- [ICC 2024 IBC Chapter 6: Types of Construction](https://codes.iccsafe.org/content/IBC2024V2.0/chapter-6-types-of-construction)
- [ICC 2024 IBC Chapter 5: Building Heights and Areas](https://codes.iccsafe.org/content/IBC2024P1/chapter-5-general-building-heights-and-areas)

### Steel

- [AISC ANSI/AISC 360: Specification for Structural Steel Buildings](https://www.aisc.org/aisc/publications/current-standards/aisc-360/)
- [AISC standards revisions and errata](https://www.aisc.org/aisc/publications/revisions-and-errata/)

### Concrete

- [ACI 318 Building Code Portal](https://www.concrete.org/topicsinconcrete/318buildingcodeportal.aspx)

### Wood and CLT

- [AWC 2024 NDS for Wood Construction](https://awc.org/resources/2024-nds/)
- [AWC 2021 SDPWS](https://awc.org/resources/2021-sdpws/)
- [APA ANSI/APA PRG 320-2025 for Performance-Rated CLT](https://www.apawood.org/guides-tools-training/technical-document-library/standards/ansiapa-prg-320-2025-standard-for-performance-rated-cross-laminated-timber/)

### Tensile membrane and cable

- [ASCE/SEI 55-16: Tensile Membrane Structures](https://sp360.asce.org/personifyebusiness/Merchandise/Product-Details/productId/233135208)
- [ASCE Structural Engineering Institute standards committees](https://www.asce.org/communities/institutes-and-technical-groups/structural-engineering-institute/committees)

The registry must retain source title, publisher, edition, adoption status, effective
date, local amendment, retrieval date, and any errata/supplements used by a run.
