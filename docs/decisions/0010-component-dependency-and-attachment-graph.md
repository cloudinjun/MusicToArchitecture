# Decision 0010 — Component dependency and attachment graph

- Status: implemented in schema 3.0
- Date: 2026-08-31
- Decision owner: project
- Career-value tags: V2, V3, V4
- Evidence: `artifacts/audio_saturation/corpus-2026-08-31-dependency-rerun-2/`

## Decision

Every emitted physical element must have at least one typed relation to another emitted
element or to a declared external root. A non-physical record must carry an explicit
exemption. The result is stored as `BuildingModelV3.dependency_graph` and compressed as
relation groups on the wire.

The graph answers two bounded questions:

1. Which generated host, carrier, or support another component relies on.
2. Whether every structural component reaches the external soil root through a complete
   generated load-path topology.

It does not size or certify plates, bolts, welds, anchors, fasteners, reinforcement,
soil bearing, settlement, uplift, or connection capacity. Those checks remain
`not_checked` on the graph and every relation.

## Contract

Each relation records stable dependent and host IDs, relation type, role, connection
family, topology status, capacity status, and basis. Relation types are `bears_on`,
`anchors_to`, `fastens_to`, `hangs_from`, `hosts`, and `abuts`. Roles are `gravity`,
`lateral`, `assembly`, `containment`, and `context`.

`ROOT-SOIL` is the explicit external root. Its topology and capacity are unresolved
until verified site and geotechnical design data exist. `program_zone` and `figure`
records are exempt because they are semantic overlays and scale references rather than
constructed building components.

The existing `ElementInstance.supports` list remains a compatibility view. It is
regenerated from the typed graph for generated-element targets and never contains an
external root. Schema 3.0 continues to run in parallel with v2.

## Required validation

Every model is rejected by the dependency acceptance checks when any of these fail:

- all dependent and host IDs resolve and no relation points to itself;
- every constructed element is connected or explicitly exempt;
- the directed graph is acyclic;
- every structural component reaches `ROOT-SOIL`;
- every architectural assembly reaches structure or an external root;
- two-ended beams, joists, CLT panels, purlins, and stair treads name both hosts;
- selected spanning-member ends fall within the declared connection zone.

Connection-capacity validation is always listed and remains `not_checked` until a later
engineering module can evaluate it honestly.

## Roof sub-grid amendment

The first 14-track dependency run exposed two offset upper plates with only one main-grid
truss line. They produced no purlins, leaving the roof deck and parapets without a path to
structure. When fewer than two base-grid lines intersect the roof, the compiler now
derives a stable two-line `roof_x` sub-grid from fractions of the roof plate bounds and
clips each truss line to the plate. Purlins connect corresponding panel points on both
trusses, and the roof deck bears on those purlins.

## Evidence

The corrected 14-track run contains 62,828 generated elements and 74,345 typed
relations. All 14 models have unique element IDs, resolved targets, no failed graph
checks, complete required-element coverage, complete structure-to-soil paths, and exact
dependency-graph round trips. Connection design remains `not_checked` in every model.

