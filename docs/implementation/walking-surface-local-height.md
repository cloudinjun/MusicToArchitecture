# Local walking-surface height

Portfolio evidence: V4 measures emitted geometry rather than an element's global
bounding box. No geometry or tolerance changes are made by this repair.

The compact candidate 64 reported two 300 mm ramp steps. Its ramp is a four-station
sweep with level end pads and a sloped middle. The old comparison used its maximum
height at every point and used an AABB when the other footprint was polygonal.

SpatialIndex now retains upward triangles from the same member_mesh used for the
physical body. The walking footprint is their union. The flush rule compares affine
surface heights at vertices of the actual overlap; flat decks retain their holes.
Existing 5 mm flush and 0.02 m2 contact thresholds are unchanged.

Read-only reassessment of archived building-v3-82347b2afc26:

- Lower landing: overlap 1.1628125 m2, maximum local mismatch 0.00040332 m.
- Podium: overlap 0.00008725 m2, below the original contact threshold; the former
  AABB overlap cannot substantiate a walking joint.
- The corrected walking rule emits zero findings for these unchanged geometries.

Four focused tests pass: aligned lower pads and real 120 mm offsets, in two plan
orientations. The physical sweep's averaged tangent creates a submillimetre tilt,
which is retained in the measurement. Broader spatial regression completed in
626.80 seconds: 42 passed, 3 failed. Ziggurat, split and pavilion each report one
walking-surface finding under the new local measurement. Those geometries require
diagnosis; no general compatibility pass is claimed and no assertion was relaxed.

This reassessment does not rewrite candidate 64 or promote it. Its original reports
remain bound to its original compiler. A new compile/export is required before a
delivery can carry these results. ENV-RET-L01-HEAD-P001 remains unsupported: its
10.67 by 3.64 m bounds show this needs a geometric support/closure investigation,
not a cosmetic dependency label. Professional checks remain unresolved.
