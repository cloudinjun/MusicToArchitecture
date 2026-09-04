# Program Constitution Guideline

Status: design guideline, 2026-08-27  
Authority: project-level contract subordinate to `PROJECT_CHARTER.md` and the selected
jurisdiction code profile

## 1. Purpose

This guideline turns a short brief into a detailed, inspectable program constitution.
The rendered color category remains useful for reading the building, while generation
and validation operate on room-level space types such as restroom, janitor, storage,
stair, elevator, mechanical room, reading room, auditorium, gallery, loading, and
collection storage.

It supports the charter abilities as follows:

- **V1 Formalize intent:** convert brief, typology, occupancy, and code assumptions into
  explicit spaces and rules;
- **V2 Coordinate systems:** expose access, adjacency, clear-span, wet-stack, service,
  facade, and structural requirements to downstream generators;
- **V3 Reliable workflow:** require stable IDs, schema versions, source references,
  validation, and last-accepted-state protection;
- **V4 Evaluate results:** report missing spaces, capacity gaps, broken relationships,
  unresolved code inputs, and repair proposals.

This is a schematic-design contract. A generated result may report which declared
checks passed. It must not claim permit approval or professional code certification.

## 2. Required distinction: color class, room type, use, and access

Every space carries four independent classifications.

| Field | Purpose | Example values |
|---|---|---|
| `program_category` | broad visual and operational layer | `public`, `private`, `circulation`, `service` |
| `space_type` | detailed room identity used by rules | `public_restroom`, `janitor`, `gallery`, `reading_room`, `stage`, `loading` |
| `access_class` | who may enter | `public`, `ticketed`, `staff`, `restricted`, `service` |
| `occupancy_use` | code-profile classification | jurisdiction-specific occupancy and use identifier |

`program_category` must not substitute for `space_type`. Two rooms may share a color
and still have different fixture, egress, acoustic, loading, daylight, or structural
requirements.

Until the renderer exposes a separate `service` color, a compatibility adapter may map
it to `private` for display only. The source value remains `service` in downloaded data
and provenance.

## 3. Code-profile gate

Code-dependent quantities require a versioned `code_profile`:

```yaml
code_profile:
  id: us-ca-local-placeholder
  jurisdiction: null
  adopted_building_code: null
  adopted_plumbing_code: null
  accessibility_standard: null
  local_amendments: []
  occupancy_classification_status: review_required
  effective_date: null
  source_urls: []
```

The brief may be generated before this profile exists, but the run status remains
`code_inputs_incomplete`. Fixture counts, exit counts, travel limits, accessible-route
requirements, construction type, height/area limits, and fire-resistance requirements
must remain `unknown` or `review_required`; the compiler cannot invent values.

The current online edition of a model code is reference material. The applicable
edition is the version adopted by the named authority having jurisdiction, including
local amendments.

## 4. Detailed space contract

Each program space must satisfy this minimum contract:

```yaml
id: SP-L01-READING-001
name: Adult reading room
space_type: adult_reading
program_category: public
access_class: public
level_id: L01
area:
  target_m2: 320
  min_m2: 280
  max_m2: 360
  source: BRIEF-AREA-04
geometry_requirements:
  min_clear_height_m: null
  min_width_m: null
  aspect_ratio_range: null
  daylight_priority: preferred
occupancy:
  use_id: null
  occupant_load_factor: null
  estimated_occupants: null
  code_profile_ref: null
accessibility:
  accessible_route_required: true
  turning_or_clearance_rule_refs: []
egress:
  egress_role: occupied
  required_exit_count: null
  max_travel_distance_m: null
service:
  wet_stack_group: null
  loading_route_required: false
  acoustic_separation_class: normal
structure:
  load_class: reading
  clear_span_preference_m: null
  column_policy: coordinated
relations: []
rule_refs: []
provenance: []
status: candidate
```

Null code values are visible unresolved inputs. They are never silently converted to
zero or a convenient default.

## 5. Base-building support constitution

Every typology expands the brief through a base-building support pass. Each item is
`required`, `conditional`, or `not_applicable` with a recorded reason.

| Space or system | Default condition | Minimum design intent |
|---|---|---|
| Entry / vestibule / lobby | required for occupied public building | legible arrival connected to public way and primary public circulation |
| Public restrooms | conditional on occupancy and fixture calculation | quantity and distribution derived from adopted plumbing and accessibility rules |
| Staff or all-user restroom | conditional | serve staff/restricted zones without routing through controlled public space |
| Janitor / custodial closet | normally required | service access, mop/service sink requirement delegated to code profile |
| Electrical / IT | normally required | restricted access and serviceable route |
| Mechanical room / shafts | normally required | area and distribution derived from system assumption, with replacement path noted |
| Fire/sprinkler service | conditional | reserved when required by adopted fire and building rules |
| General storage | required | sized from typology and operations, separate from egress width |
| Refuse / recycling | normally required | service route to exterior without crossing primary public sequence where practical |
| Horizontal circulation | required | continuous graph connecting occupied spaces, exits, accessible route, and service zones |
| Protected stairs / exits | conditional by stories, occupant load, travel, and code profile | number, remoteness, width, enclosure, and discharge remain code-derived |
| Elevator / lift | conditional | vertical accessible route and operational service needs tracked separately |
| Loading / receiving | conditional by typology and scale | direct service route to storage, stage, collection, or back-of-house destination |
| Staff support | conditional | workroom, break, lockers, and staff storage based on brief and operating model |
| Vertical riser zones | normally required | align wet, mechanical, electrical, and fire-service distribution where practical |

“A restroom exists” is only the first check. A credible result also calculates the
required fixture demand from use and occupant load, reserves accessible layouts,
connects them to an accessible route, and coordinates wet-stack/service access.

## 6. Typology starter constitutions

These lists provide a minimum operational skeleton for comparison studies. The first
implemented typology still must be selected through decision 0001; the project does
not build all three generators during the first round.

### 6.1 Library

**Public and collection spaces**

- entry, lobby, welcome/security, and checkout/service point;
- adult reading, children/teen reading, open stacks, periodicals or media;
- individual study and group study;
- community/multipurpose room with after-hours access strategy;
- digital learning, maker, or flexible project space when present in the brief;
- public restrooms and drinking-water provision as required by the code profile.

**Staff and service spaces**

- staff workroom, administration, meeting, break/locker, and staff restroom strategy;
- processing/cataloguing, holds, secure storage, supplies, and book return route;
- loading/receiving when collection or event operations require it;
- janitor, refuse, IT/electrical, mechanical, risers, stairs, elevator, and egress.

**Key relationships**

- public arrival sees welcome/security and the primary circulation decision;
- book return reaches processing without crossing quiet reading areas;
- children areas have controlled visibility and convenient restroom access;
- community space can operate after hours without opening all collection areas;
- noisy maker/community uses receive explicit acoustic separation from quiet reading.

### 6.2 Theater

**Audience spaces**

- entry, exterior queue allowance, lobby, box office/ticketing, concessions if briefed;
- auditorium, seating aisles, accessible seating positions, crossovers, and exits;
- public restrooms and drinking-water provision sized from occupancy and event profile.

**Performance and production spaces**

- stage/performance volume, wings, crossover, control booth, technical access;
- green room, dressing rooms, performer restroom/shower strategy, rehearsal when briefed;
- scene/prop/costume/storage, workshop when briefed, and secure loading path;
- administration, staff support, janitor, refuse, IT/electrical, mechanical, fire service,
  stairs, elevator, and egress.

**Key relationships**

- audience circulation and scenery/loading circulation remain separately traceable;
- loading reaches stage and storage without passing through lobby or seating;
- auditorium and stage export clear-span and column-prohibition zones to structure;
- sound-critical rooms carry acoustic adjacency and separation requirements;
- assembly seating, aisles, exits, accessible means of egress, and fixture demand are
  code-profile calculations, not fixed legacy dimensions.

### 6.3 Museum

**Visitor spaces**

- entry, lobby, ticketing/information, security screening, orientation;
- permanent and temporary galleries, flexible education/multipurpose space;
- public restrooms, coat/bag storage, and visitor amenities required by the brief.

**Collections and operations**

- secure collection storage, preparation/staging, conservation when briefed;
- loading, receiving, quarantine/inspection, freight path, and oversized-object route;
- curator/administration, staff workroom, meeting, break/locker, staff restroom strategy;
- janitor, refuse, security/IT, electrical, mechanical, fire service, stairs, elevator,
  and egress.

**Key relationships**

- visitor and art/service circulation form separate graphs with controlled crossings;
- loading connects to receiving, quarantine, storage, prep, and galleries;
- galleries export clear-span, daylight, loading, environmental, and hanging constraints;
- collection spaces carry restricted access and environmental reliability requirements;
- key interior sequence records arrival → orientation → gallery transition → focal room.

## 7. Relationship vocabulary

Relationships are data records, not hard-coded `if room_name == ...` branches.

| Relation | Meaning | Validator |
|---|---|---|
| `must_connect` | direct door or open threshold | graph edge and geometric contact |
| `preferred_near` | weighted proximity | distance score with declared target |
| `must_separate` | acoustic, security, hazard, or operational separation | minimum route/partition condition |
| `service_connect` | continuous back-of-house route | service graph reachability |
| `public_connect` | continuous public route | public graph reachability |
| `accessible_connect` | continuous accessible route | accessible graph and unresolved detail checks |
| `vertical_align` | wet stack, core, riser, or repeated support | overlap/alignment tolerance |
| `visual_connect` | sightline or orientation relationship | view corridor or opening proxy |
| `daylight_edge` | preference or requirement for facade adjacency | exterior-edge length or exposure |
| `column_exclusion` | structural support prohibited or tightly limited | structure/program collision check |

Useful legacy relationships become versioned rules: restrooms near wet/core service,
loading near freight/service circulation, office near meeting, fabrication/prep near
loading, and repeated wet/core spaces vertically aligned. They remain typology- and
brief-dependent.

## 8. Program-generation sequence

1. **Normalize brief.** Validate site, scale, typology candidate, operating model,
   opening hours, target capacity, and source provenance.
2. **Resolve code inputs.** Load jurisdiction profile, occupancy/use candidates,
   construction assumptions, accessibility basis, and unresolved decisions.
3. **Expand detailed list.** Add typology rooms and base-building support spaces with
   conditions and reasons.
4. **Calculate demand.** Estimate occupant loads, restroom/fixture demand, exit demand,
   accessible route needs, service capacity, and operational storage.
5. **Build relationship graphs.** Maintain separate public, staff, service, accessible,
   egress, and visual/acoustic relations.
6. **Allocate levels and stacks.** Place public sequence, back-of-house, wet stacks,
   risers, cores, freight/service, and high-load/clear-span zones.
7. **Solve geometry.** Enforce boundary containment, area ranges, non-overlap, minimum
   dimensions when known, and adjacency weights.
8. **Negotiate with structure/facade/interior.** Publish column policies, clear spans,
   load classes, daylight edges, acoustic zones, entries, and key interior sequence.
9. **Validate and repair.** Produce rule-level pass/fail/review results and bounded
   repair proposals.
10. **Accept or retain prior state.** Publish only stable, schema-valid output; preserve
    the last accepted state when a new run fails.

## 9. Rule contract

```yaml
rule_id: PRG-BASE-RESTROOM-DEMAND-001
title: Derive restroom demand from use and occupant load
applies_to: [library, theater, museum]
source_type: adopted_code
source_ref: code_profile.plumbing_fixture_table
condition: occupied_building
severity: hard_when_profile_resolved
inputs: [occupancy_use, occupant_load, sex_or_all_user_policy, accessibility_profile]
check: fixture_demand_satisfied
repair: add_or_resize_restroom_group
limitations: requires resolved jurisdiction and occupancy classification
```

Every rule includes `rule_id`, source, applicable typology, severity, measurable check,
repair strategy, limitations, version, and provenance hash. A heuristic rule cannot be
labelled `adopted_code`.

## 10. Validation gates

### Hard when inputs are resolved

- all required spaces exist exactly as their rules specify;
- total and departmental areas remain within declared tolerance;
- every occupied space reaches the required egress and accessible-route graph;
- required restroom/fixture demand and accessible facilities are satisfied;
- loading, collection, stage, or service routes reach their destinations;
- required adjacency, separation, vertical alignment, and boundary conditions pass;
- no room overlap, negative dimension, orphan level, missing stable ID, or lost source;
- structural column exclusions, clear spans, load classes, and core openings are
  consumed and answered by the structural model;
- every automatic repair records changed element IDs, prior values, rules, and reason.

### Review required

- occupancy classification or mixed-use strategy is unresolved;
- code profile, local amendments, operating model, event capacity, or collection
  requirements are incomplete;
- daylight, acoustics, security, conservation, or accessibility needs exceed the
  implemented proxy;
- a layout passes geometry but lacks human review of sequence and architectural quality.

## 11. Legacy extraction record

| Legacy behavior | Guideline treatment |
|---|---|
| detailed room names in `OpenAI_ProgramDetails.py`, `RoughProgram.txt`, and `output.txt` | retain the distinction between detailed space type and broad color category |
| explicit toilets, storage, loading, mechanical, stairs, elevator, and circulation | retain as conditional support constitution with demand and code-profile checks |
| `EllipseAgent.py` boundary, overlap, adjacency, and vertical stacking | retain as solver/validator concepts; move relationships into data |
| restroom/core, loading/freight, office/meeting, fabrication/loading relationships | retain as scoped starter rules with provenance |
| fixed 18 × 33 m site, 80–90% floor fill, 2 m increments, 4 m circulation spine | legacy experiment heuristics only |
| exactly two stairs per floor and fixed core positions | remove as universal rules; derive through code profile and building geometry |
| program names embedded in algorithm branches | replace with rule tables and semantic capabilities |

Reviewed legacy sources:

- `program_generator/OpenAI_ProgramDetails.py`
- `program_generator/fileTransfer/ProgramFormat.txt`
- `program_generator/fileTransfer/RoughProgram.txt`
- `program_generator/fileTransfer/output.txt`
- `program_generator/ProgramDeveloperEllipseBoundary.py`
- `program_generator/EllipseAgent.py`

No legacy code or fixed coordinates were copied into this guideline.

## 12. Initial verification fixtures

1. **Missing restroom:** a public library brief without restrooms expands to a restroom
   demand item; unresolved occupancy remains visible and prevents a code-pass claim.
2. **Theater service route:** loading must reach stage/storage without routing through
   lobby or audience seating.
3. **Museum collection route:** loading → receiving → quarantine/inspection → storage →
   prep → gallery is traceable, with restricted access.
4. **Wet-stack alignment:** restroom groups on repeated levels align within a declared
   tolerance or produce a repair proposal.
5. **Column conflict:** structure cannot place a column in an auditorium, stage, critical
   gallery zone, required aisle, door clearance, or egress path without an explicit
   negotiated exception.
6. **Category fidelity:** hiding `public` affects the broad layer, while inspection still
   reports the exact `space_type`, access class, area, rules, and provenance.

## 13. Official reference baseline

These sources define the initial U.S. reference vocabulary; a project uses only the
edition adopted by its jurisdiction:

- [ICC 2024 IBC Chapter 3: Occupancy Classification and Use](https://codes.iccsafe.org/lookup/IBC2024P1_Ch03)
- [ICC 2024 IBC Chapter 10: Means of Egress](https://codes.iccsafe.org/content/IBC2024V2.0/chapter-10-means-of-egress)
- [ICC IBC Chapter 29: Plumbing Systems](https://codes.iccsafe.org/content/IBC2021V2.0/chapter-29-plumbing-systems)
- [ICC 2024 IPC Chapter 4: Fixtures, Faucets and Fixture Fittings](https://codes.iccsafe.org/content/IPC2024P1/chapter-4-fixtures-faucets-and-fixture-fittings)

The source list belongs in the code-profile registry with edition, effective date,
local amendments, and retrieval date. It is not a substitute for the adopted code set.
