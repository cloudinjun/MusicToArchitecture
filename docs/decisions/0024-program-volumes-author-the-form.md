# 0024 — Program Volumes author the form

Status: accepted, first executable slice 2026-09-06.

## Purpose

The project exists to produce complete, coordinated, presentable architectural
candidates quickly. The previous music path selected a plate silhouette first and then
packed the brief into it. That ordering allowed different labels and facade grammars to
land on buildings whose spatial organisation remained substantially alike. It also
produced occupied plates with no program on them: the Bach museum carried rooms only on
L01–L02 while structure and facade continued through L06.

The legacy project exposed a stronger shared protocol. Full-height Program Volumes were
visible before the other systems; facade was attached to their outside; structure and
interior systems were constrained by the same volume. This decision keeps that protocol
and makes the *method of constructing Program Volumes* the principal form-diversity
variable.

Portfolio evidence: V2 system coordination, V3 reliable workflow and V4 measurable
comparison. The gate is geometric propagation, not the number of rendered styles.

## Decision

The causal chain for the new candidate path is:

```text
music + brief
  -> Program Volume organisation grammar
  -> registered full-height room volumes + explicit sectional clearances
  -> exact union on every occupied storey
  -> ProgramMassing plates / voids
  -> allocation + archetype + circulation + structure
  -> facade on the plate boundary or its declared outward offset
```

`ProgramVolumeModel` is a first-class serialized artifact. Every program room appears
once as a full-storey box located by indices into its grid. Explicit circulation spine
and connector volumes may carry no room id; they keep each level union connected and
reserve a common vertical datum. A disconnected union is refused. No convex hull or
bounding box may silently fill the separation.

A sectional archetype may author a `sectional_clearance` volume above its room owner.
This grid-registered prism is coordinated airspace inside the gross envelope: it carries
no `space_ids`, contributes no room area to `ProgramAllocation`, and may not consume
positive area from a program or archetype volume on the same level. It still participates
in the exact level union, keeping the roof and facade envelope continuous while the
archetype removes the intervening floor. The library uses this role above `SP-ADULT` for
its double-height reading room. The theater authors separate gross clearances above the
auditorium and stage, moves any intersecting upper program as one whole-grid group, and
requires the residual upper floor to remain connected after those clearances are cut.
The paired theater section continues through every occupied level reached by the
larger of the derived bowl clearance and raised-stage clearance, including the shared
floor-build-up allowance. Its upper program move also includes rooms stranded by the
cut, even when those rooms do not overlap the clearance directly. This keeps the
stage's taller enclosure connected through its adjacent auditorium owner and gives
the transfer structure one explicit gross sectional volume.

Program Volume ownership is also the archetype's coordinate authority. The theater
carver consumes the adjacent auditorium/stage owner pair and its clearances; the museum
carver consumes the two gallery owners and their shared wall; the library carver consumes
the adult-reading owner. A Program Volume carver validates and measures these authored
regions and may refuse them, but may not perform a second whole-plate search. The former
whole-plate algorithms remain only for legacy lattices that carry no owner regions.

`ProgramVolumeModel.level_unions` are the form authority. Its adapter writes those
unions directly into `ProgramMassing.levels`; `_fit_plan_to_brief` is not called on this
path. `ProgramMassing` remains the common carrier introduced by decision 0022 and the
existing `_compile_from_lattice` tail remains shared. The score is passed through so
structure and facade selection retain their musical provenance. The massing digest is
included in model identity, so two volume topologies from one score cannot overwrite
each other.

The first organisation library has three reachable grammars:

- `PVG-STACKED-BANDS`: compact registered room bands around a common vertical spine.
- `PVG-TERRACED-WEAVE`: floors shift relative to the stable spine and reconnect to it.
- `PVG-SPLIT-BRIDGE`: public and controlled program occupy separate wings joined by an
  explicit circulation bridge.

Selection uses short discrete questions. High interruption selects the split bridge;
decisive hierarchy or variation selects the terraced weave; the remaining domain uses
stacked bands. A caller may pin the grammar to compare form while holding typology,
structure and facade fixed.

## Two program representations

The upstream Program Volumes carry gross capacity and make the building form. The
downstream `ProgramAllocation` records rooms the deterministic kernel could actually
fit after cores, archetype reservations and public circulation take floor. Both remain
on the model because they answer different questions:

- `ProgramVolumeModel`: what spatial composition authored the candidate;
- `ProgramAllocation`: what the coordinated building delivered inside that composition.

On the Program Volume candidate path, each geometrically viable program or archetype
region receives first claim on its authored storey and rectangle at full room area.
Unresolved same-storey owners are temporary obstacles while the public route is planned,
so an early shortest path cannot consume the only rectangle that can hold a later room.
An owner obstructed by a core, archetype or required route enters the measured spill pass;
the final `ProgramAllocation` geometry makes that departure inspectable. The spill pass
does not shrink a Program Volume room to conceal a capacity failure.

Decision 0023 continues to govern fixed detailed zones: a zone writer assigns usable
floor and the kernel measures it. Its statement that zoning does not create floor now
applies to those downstream zones. The upstream Program Volume grammar does create the
gross form by union.

## Shared-boundary rules

1. Every form-bearing occupied level has at least one room volume. An intentional void
   needs explicit provenance; an empty phantom storey is invalid.
2. The plate with its holes equals the horizontal union of Program Volumes within a
   geometric tolerance. Roof geometry comes from the highest union.
   A score-authored model also carries an optional `RoofControl`: its boundary and
   void rings are copied exactly from that highest union, `datum_z` is the highest
   Program Volume `z_top`, and `physical_top_z` is calculated by the shared roof
   section rule (truss, chord, purlin, deck and parapet). The roof emitter reads the
   same rule and refuses a plan or three-dimensional overflow; the roof deck preserves
   declared union holes. This is a student coordination envelope and remains
   `professional_review_required` for member capacity, connections, drainage,
   waterproofing, fire and code review.
3. Structure, partitions, rooms and internal circulation are inside or on this union.
   Site, foundations and the exterior entrance approach need explicit exemptions.
4. Primary facade is on the union boundary or its declared outward offset. Returns and
   ties may occupy only the collar between those two boundaries.
5. One room id occurs in one Program Volume. Positive room-volume overlap is invalid.
   Circulation connectors may meet room faces without consuming room area.
   An explicitly authored circulation-category room may name
   `shared_route_volume_ids`: that room is a commons whose floor also carries those
   public routes. This does not create extra floor or a second room owner. Named
   targets must be same-level carriers/connectors, never protected cores. Core,
   void, archetype and other-room exclusions remain binding, the complete room
   area/minimum dimension is measured, and a full-width route must reach a real
   stair before the shared room is delivered. Category alone grants no sharing.
6. Sectional clearance is gross-envelope airspace, not allocatable floor. It carries no
   room id and does not overlap a room volume by positive plan area on its own storey.
7. An archetype room with a Program Volume owner is placed inside that owner. Paired
   type-spaces preserve their authored shared boundary, and an upper-floor carve reads
   explicit sectional-clearance regions rather than extending itself to a convenient
   plate edge.
8. Program Volume geometry stays in the review `.blend` and the model JSON. It is
   excluded from the canonical GLB because it is an explanatory overlay, not a second
   accepted solid occupying the building.

The common circulation carrier reserves its entry capacity before the plate is fixed.
On the bounded legacy adapter, the opt-in `west_forecourt` layout reserves a
complete low-rise arrival before room search. Its `ArrivalAssembly` carries the
stair, checked ramp, landings and connecting gallery in the registered entry
station's local frame. The downstream compiler reads that frozen arrangement;
it cannot independently enlarge the stair or borrow room area. The actual parcel
constrains the reservation, and a selected facade deeper than the declared planning
allowance rejects the proposal. The initial compact family is a single public
flight; taller arrivals retain the existing path and are not claimed as covered
by this compact planner. Physical emitted-body and route checks remain required.
`approach.plan_boundary_switchback` is shared by volume authoring and the compiler.
Authoring selects the smallest whole-grid carrier width that fits the accessible route
on its continuous west face, bounded by the declared project approach-depth budget.
If none fits, the minimum carrier remains and the unresolved route stays visible.
Feasible faces take precedence over the grammar's edge ranking. The selected station
still owns the public stair, ramp, facade portal and entry canopy; its inside approach
must reach public circulation without crossing a protected archetype room.

The consumed archetype also supplies geometry-derived compiler capability demand.
Actual support nodes inside the theater's cleared auditorium/stage volume require the
implemented gravity-transfer emitter. This filter follows physical/code screening and
records its exclusions independently, as specified in decision 0009. It preserves the
music's preferred system and explains any substitution; a pinned incapable system is
refused before geometry emission.

The paired theater reserves a one-cell perimeter gallery along its north and south
edges before union. Existing room/circulation cells retain ownership; only absent
consecutive cells are filled with connector volumes. The gallery meets the common
carrier and persists through the transfer storeys. It gives the cell-centred structural
grid actual inboard pier stations outside the clear room. This is a spatial reservation;
the transfer calculation, physical section containment and connection review retain
their own independent gates.

Facade base and head returns consume the host storey's explicit sectional clearances.
An edge-connected floor subtraction cannot become a horizontal panel across that
airspace. Bracket paths remain outside it by their actual half-section. The protocol
report checks floor material against union minus upstream clearances and preserves the
raw gross/floor difference; an unregistered removal or a restored obstruction fails.

## Compatibility and promotion

`compile_building_model_v3` remains the current legacy entry while this path accumulates
cross-system evidence. `compile_program_volume_candidate` is the score-authored entry.
The v2 compiler remains parallel and unchanged. Promotion of this path to the public
default requires all shared-boundary gates, four typology/archetype checks and a
same-score three-grammar visual comparison.

Pre-authored `MassingFamily` silhouettes stay available as compatibility inputs and
capacity studies. They do not own the final boundary of a Program Volume candidate.

## Current evidence and limits

`backend/tests/test_program_volumes.py` proves grammar reachability, one volume per
brief space, no phantom levels, distinct same-brief topology, and exact
`union(volumes) == ProgramMassing plate` propagation. The Blender adapter prefers the
first-class volume contract when present and rejects bad grid or level references.

The first slice keeps Program Volumes orthogonal and grid-registered. Detailed fixed
zones remain opt-in; owner-first allocation is the normal coordination seam for cores,
archetype reservations and the public route. Archetype rooms run through owner-aware
carvers and are measured against both their region and the volume-authored plate. Full
solid containment and facade collar reports remain promotion gates, and a compiled
result remains a review candidate rather than a compliance claim.
