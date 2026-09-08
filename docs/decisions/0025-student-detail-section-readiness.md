# 0025 — Student detail-section readiness

Status: accepted target, staged implementation from 2026-09-07.

## Purpose

The pipeline is expected to turn music into a building candidate that can survive an
architecture-school review at detail-section scale.  The target is a coordinated design
model with explicit assemblies and interfaces, suitable for 1:20 sections and selected
1:10 enlargements.  Permit approval, fabrication tolerances, sealed calculations and
manufacturer shop drawings remain professional follow-on work.

This target makes V2 coordination, V3 workflow reliability and V4 evaluation visible.
The quality gate is a cut through one emitted model, not a separately illustrated detail.

## Authority chain

The existing logical sequence and deliverables remain stable:

```text
music
  -> score with evidence and confidence
  -> typology + Program Volume grammar + structure + facade grammar
  -> Program Volume spatial contract
  -> coordinated deterministic building systems
  -> verified model views and drawing cuts
  -> .blend + candidate .3dm + drawing set
```

Music supplies design intent and chooses among reachable architectural alternatives.
It may move proportions, topology, rhythm, hierarchy and assembly density inside each
system's published range.  It does not supply site facts, code editions, material
properties, product data or connection capacities.

Long language-model prompts may be compressed into a short direction record plus
versioned contracts.  Image generation may propose references or presentation imagery.
Neither route may author accepted geometry, dimensions, drawing marks, validation
results or Rhino acceptance state.

## Fidelity ladder

Every candidate reports the highest completed tier; it never infers a higher tier from
visual complexity.

| Tier | Required evidence |
|---|---|
| D0 — volume | Program Volumes, usable floors, openings and silhouette are explicit. |
| D1 — systems | Structure, circulation, envelope and program share the same boundaries and datums. |
| D2 — assemblies | Cuttable layers have thickness; members have sections; components have assembly IDs, part roles, hosts and interfaces. |
| D3 — student detail section | A generated 1:20 section and selected 1:10 enlargement expose the complete floor-to-facade-to-roof or circulation interface with dimensions, material roles, support path and declared unresolved items. |
| D4 — professional development | Adopted-code review, sealed calculations, manufacturer systems, waterproofing continuity, tolerances and shop drawings. Outside this pipeline's completion claim. |

The product goal is D3.  D4 remains an explicit handoff.

## Program Volume system rule

Program Volume is the shared three-dimensional control protocol:

1. Occupied program establishes the union and every supported floor boundary.
2. Internal structure, rooms, protected stairs, landings and services remain inside the
   relevant occupied union or a named system-control volume.
3. A roof-control volume starts at the highest occupied union and bounds the complete
   roof assembly in plan and section.
4. The weather carrier follows the Program Volume boundary or its declared facade
   offset.  Every outboard layer remains inside a measured facade collar.
5. Exterior entrance stairs and ramps are explicit approach exceptions.  Their landing,
   portal and interior continuation still resolve from the Program Volume circulation
   intent.
6. A system that cannot fit reports the failed element and volume.  It may not expand
   the form, shrink a required route or move to an undeclared position silently.

## D3 acceptance gate

A candidate reaches D3 only when all of the following are true:

- roof structure, deck and parapet are checked against the roof-control volume;
- internal circulation is checked against its carrier volumes, and an exterior ramp is
  not called a verified route until its top landing reaches a real facade portal and a
  supported interior path;
- facade geometry is program-aware and passes the selected guide's evaluated invariants;
- every cut envelope layer has a non-zero thickness and a material role;
- every visible assembly part carries `assembly_id`, `part_role`, source datum/rule and
  a resolvable host or a named unresolved interface;
- the detail cut contains no geometry authored only for the drawing;
- the `.blend`, `.3dm`, model JSON and drawings identify one model/run and pass their
  existing save/reopen/hash gates;
- unknown site, code, product and capacity inputs remain `unevaluated` or
  `professional_review_required`.

The first reference cuts are:

1. roof edge: top Program Volume, truss, purlin, deck, parapet and facade return;
2. typical facade/floor: primary frame, slab edge, bracket, insulated cassette or
   glazing, mullion and interior finish zone;
3. entry/circulation: Program Volume boundary, stair or ramp, landing, slab opening,
   edge beam, portal and interior supported route.

## Promotion

Implementation proceeds as independent gates: three-dimensional roof authority,
circulation authority, facade assembly authority, then detail drawing projection.  A
candidate may remain useful at D1 or D2 while a later gate is incomplete, but the
portfolio and UI must show that tier and the blocking evidence plainly.
