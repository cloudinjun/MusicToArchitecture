# Circulation clearance and visual regression

The 20-recording visual audit found stairs hidden inside uncut slabs, lift walls
inside flights, intersecting stair cores, and self-intersecting west-apse plates.
Successful export and a landing at the right elevation did not establish a usable route.

## Implemented

- `core_anchors` selects complete stair footprints against the actual plate minus
  voids. Each new core excludes existing cores. A lift searches four adjacent
  positions independently; it cannot consume a flight's clear volume.
- `_core_layout` coordinates flight directions, landing positions and openings.
  Allocation, floor slabs, ceilings and circulation read the same decision.
  Archetype cuts precede this decision; a refused carve restores the original voids.
- `plan_regions` subtracts the union of openings and retains every connected plate
  component. It decomposes regions with holes into simple polygons whose exact union
  is the original material region, with no overlapping area. Each extrusion has a
  CCW boundary. Invalid input fails explicitly. The west-apse traversal is corrected
  at its source, without repairing malformed polygons after generation.
- Source polygons and exported surfaces receive independent checks. Shapely's
  opposite ring winding first filled GLB holes; normalizing winding still left
  spurious faces in a multiple-hole case. Simple-part decomposition removes reliance
  on the existing adapter's nearest-vertex hole bridges. Blender automation is unchanged.
- Floor landings remain flush and overlap real slab material. Three closed edges
  of each stair opening receive guards; its entrance remains open.
- `geometry_review` checks emitted solids independently of layout intent. Rotated
  boxes and extrusion holes participate in exact plan intersections and separate
  elevation intervals. Unknown geometry never becomes a clean check. Member
  clearance uses a declared approximation and remains a review warning.
- A failed v2 presentation export retains its error and blocked artifacts while
  allowing the v3 branch to run. Missing assets have no invented URLs or hashes.
  Blender's native Python error exit flag exposes failed exporters.

## Limits

No feasible core means an unresolved route, recorded by level; it does not authorize
a centroid fallback or a reduced clearance. Removing an invalid stair cannot be
reported as successful access. The audit reports service coverage alongside collision
counts. The 2 m clearance threshold is a design-review convention, not code approval.

Opening-edge framing and rerouting existing beams require a structural coordination
stage. Existing members remain visible and reportable. Lift doors and equipment,
connections, fire enclosure, and all-room access are not designed by these changes.

## Evidence

`docs/experiments/visual_music_corpus_20.json` records source rights and audio hashes.
The local `artifacts/visual_audit/2026-09-03/` store retains frozen sources and full
pipeline outputs. Git publishes the compact review surface: whole-building and detail
cards, numeric checks, source hashes and separate visual review records.
The formal comparison is `baseline-frozen` to `verified-frozen`; `after-frozen`
(3.3.0) and `final-frozen` (3.3.1) are rejected intermediate exports. Source archives
isolate this change from concurrent drawing-workbench edits. The full JSON and the
exported GLB are separate QA surfaces.
