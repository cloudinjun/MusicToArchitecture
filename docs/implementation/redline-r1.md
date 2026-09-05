# Redline generator hardening R1

Baseline: `bc586fcf2d810a7144a611f2db1b83bd930712db`. Compiler: **3.5.0**.

This is a bounded first implementation of the drawing review, not completion of all
44 redlines and not permit, accessibility, structural, or print-readiness approval.
It strengthens charter V2 (coordination) and V4 (measured failure and recovery).

## Model changes

- `program.level_bands` uses exact full-strip containment against the declared plate
  minus actual voids and core reservations. Centre-line samples no longer establish
  the size of a room. The existing grid-based rectangular allocator is retained.
- Candidate coordinates are rounded inward to millimetres, then checked again as the
  exact serialized rectangle; area is derived from that rectangle. Requirements that
  do not fit remain unplaced or explicitly short. Core reservations are never waived.
- Preplaced archetype rooms are checked too. A refused preplacement is reported as
  unplaced, not replaced by a generic room. The theatre pair shares canonical edges
  across its zones, reservations, carved openings, and proscenium.
- `SP-ROOM-OUTSIDE-SUPPORT` independently measures each emitted room against the union
  of its same-level, same-elevation floor pieces. Slab holes stay holes. Missing or
  invalid geometry is unevaluated, never a successful empty intersection.
- Default compilation and the normal API pipeline now use `cutaway=False`.
  `issue_drawings` rejects an incomplete cutaway unless explicitly requested with
  `allow_cutaway=True`; such diagnostic view captions are labelled. This prevents a
  presentation cutaway from silently becoming a normal architectural drawing set.
  Legacy explicit cutaway compilation is still supported; a fully separate ViewSpec
  architecture is **not** implemented in this batch.

## Drawing changes

- Hinged partition-door arcs return by 90 degrees, not the other 270 degrees.
  Lift landing doors no longer receive a hinged-room-door symbol.
- `program_zone` is a semantic region, not an opaque surface in the drawing painter.
  It still supplies room annotations and remains included in the audit accounting.
- Room names use the brief label rather than the generic space-type name. Area labels
  use the serialized allocation area and explicitly say `allocated`. They are not
  presented as legal/net area measurements. Missing allocation data stays unverified.
- Roof caption and actual section plane read the same cut-height variable.

## Egress diagnostics, not automated compliance

- Consecutive vertical edges preserve the stair family; two different cores can no
  longer be joined just because their landings were adjacent in a storey-sorted list.
- The entrance landing is not another protected stair. Arbitrary first/second ramp
  landings are not fabricated as discharge nodes. Actual site discharge is unevaluated.
- The site sprinkler input reaches the graph. No unverified sprinkler-based reduction
  is applied to the inherited width screening value. Occupancy classification defaults
  to `unconfirmed`, not a blanket A-3 assignment.
- The centroid-to-stair graph and inherited tables remain provisional. Arithmetic
  failures remain diagnostic failures; apparently favourable arithmetic is explicitly
  unevaluated until a verified code profile, occupant basis, and traversable geometry
  exist. Empty/unevaluated findings cannot yield `compliant=True`.

## Compatibility and evidence

No v2 consumer is replaced. No accepted Rhino geometry, promoted `latest` archive,
frozen demo run, GLB, or published screenshot is overwritten by this source change.
The minor-version/source fingerprint ensures future generation has a new identity.
Existing saved models remain readable; `cores_unreserved` remains a legacy field,
but it no longer excuses a measured collision.

`backend/tests/test_redline_r1.py` contains small counterexamples and a real compile
of the checked-in theatre features/score. It checks rotated/concave/holed plates,
non-waivable cores, preplaced-room coverage, split support slabs, 16 door orientations,
semantic non-occlusion, allocation labels, roof captions, cutaway refusal and correct
stair-family links. Existing drawing tests retain their checks and now verify actual
brief labels/area basis. The preview isolation test also asserts full-model forwarding.

## Still open

The new constraint may reveal a brief that the existing greedy allocator cannot fully
place. This is not proof that no architectural solution exists: search/replanning and
function-specific layout are further work. Do not remove requirements or widen the
geometric tolerance to make the report green.

Still required: real portals and door-side space/landing checks; an actual traversable
route graph; seat/aisle and sanitary-fixture layouts; service/equipment clearances;
complete stair UP/DN/service-layer semantics; door frames and duplicate closed-leaf
cleanup; weatherproof/detail assemblies, drainage, dimensions, view references, issue
metadata, and a manufacturing-specific printing gate. Existing structural intrusion
and approximate head-clearance reports remain visible. This batch does not resolve
the long-span theatre transfer or certify the entire building.

The numerical `PLAN_EPS_M = 1e-7` is a computational tolerance, not an architectural
clearance, code limit, or permitted room overhang.
