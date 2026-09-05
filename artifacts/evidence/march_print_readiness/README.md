# M.Arch / print-readiness implementation evidence

Status: **diagnostic only**. This directory is not the current accepted model archive.
No `latest` pointer, Rhino acceptance sidecar, existing GLB or frozen demo is changed.

A fresh compiler 3.5.0 full-envelope (`cutaway=False`) library / MAS-SLAB run used the
existing `artifacts/integrated_demo/building-b7ad95fa45a6-library-steel-international-v1`
feature and score JSON. The exact compiler fingerprint and source-model file hash are
in `verification.json`. This is a full compiler run, not a manually assembled table.

The run emitted 9,801 elements, including 717 complete furniture assemblies. Both new
furniture checks returned zero findings. Fourteen candidate furniture placements did
not fit and were explicitly reported rather than emitted partially. Dependency and
axis reports passed. The spatial report still failed: two non-flush surface findings,
six ramp-deck-gap findings, and 53 unevaluated head-clearance findings remain. Those
counts are not suppressed. This is **not** a thesis-ready whole-building certification.

`desk-coupon.stl` is one actual desk assembly from that run at 1:100 in millimetres.
Its source IDs, inverse assembly placement, dimensions, volume and STL hash are recorded
in the JSON. All five desk parts were solid-unioned, exported and re-imported; the
result is a single watertight, winding-consistent positive-volume shell. It has not
been sliced or printed, and its thin legs may not suit a particular printer. The
profile is planning-only with unresolved machine/material limits.

Local verification completed: 49 focused tests, 28 existing single-fixture compiler
checks and 10 existing dependency tests. Two offset-roof scenarios were deselected;
the complete repository suite was not completed. Blender/Rhino, slicing, physical
samples and physical assembly were not executed in this environment. No new render
is presented as if it had been generated.

Reproduction uses `compile_building_model_v3(features, score, massing_id='MAS-SLAB',
typology='library', cutaway=False)` and the normal diagnostic exporter. Read
`docs/fabrication_workflow.md` before assigning any print-readiness status.
