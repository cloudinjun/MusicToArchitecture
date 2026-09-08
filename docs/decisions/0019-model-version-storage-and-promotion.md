# Decision 0019 — Model version storage and promotion

- Status: accepted and implemented
- Date: 2026-09-04
- Decision owner: user
- Career-value tags: V2, V3, V4

## Problem

Different testing tasks cited images from different compiler periods. A former demo model,
intermediate visual-audit exports, and a historical Rhino smoke file could all look like
current evidence because folders and URLs carried model IDs without a single promotion
record. This allowed repaired defects to reappear in reviews and left Rhino/Revit authority
unclear.

## Decision

One verified release owns the `latest` name. Every release has an immutable archive,
content hashes, a complete run contract, and separate authority records for Rhino and
Blender.

`backend.scripts.publish_model_version` is the sole promotion step. Generation writes a
candidate. Promotion verifies model IDs and hashes, writes the archive, copies a checked
mirror to `latest/`, and then updates the web cache through stable `latest` URLs. Candidate
and stable URL forms are normalized before contract hashing, so the same data receives one
release ID.

The version ID combines the UTC generation time, compiler version, portable model hash,
and the complete asset-inventory hash. The manifest also records a hash of the Python source
that generated geometry and exports. The model and run identities include that source
hash, and generation aborts if the source changes before the run completes. This protects
long renders from concurrent edits in another task.

Publication and candidate archiving share an exclusive writer lock. A second window
cannot overwrite a staging directory or pointer while the first owns publication.
An abandoned lock identifies its process and time for explicit inspection.

## Complete candidate pairs

Before interactive Rhino acceptance, `--archive-candidate` stores a complete same-run
pair under `candidates/<version_id>/`: `rhino/model.3dm`, `blender/scene_v3.blend`, GLB,
the exact portable JSON, original generation response, and diagnostic images. The
`current_candidate.json` pointer is explicitly a candidate; it never replaces `latest`.
File-SDK solid validity and readback do not become interactive Rhino acceptance.

The user's current delivery target is an M Arch thesis model demonstrating design
coordination and software handoff. Complete visible geometry, connected spatial
interfaces and same-version native files are the delivery gate. Permit calculations,
construction detailing, universal check clearance and fabrication slicing are outside
this delivery. Remaining findings stay visible in the model's review record.

Blender manifests bind the canonical source JSON, actual native file, GLB and every
render by SHA256. Diagnostic views additionally require the matching generation response
and record the view planes, camera, visibility changes and per-image hash. Relocating
identical native bytes into an archive is allowed; changed bytes are rejected.

Diagnostic cuts are temporary uncapped view operations. The master `.blend` and complete
model stay unchanged. These images do not establish successful visual review until a
reviewer has actually inspected them. No fabrication slicing is part of this workflow.

Concurrent design edits use `backend.scripts.freeze_generation_source`: a verified
`source_snapshots/<inventory_hash>/` stores Python source, runtime documents and the
audio input. Each is hashed before and after copying. A fresh isolated Python process
compiles inside that snapshot and creates its own outputs. `adopt_snapshot_candidate`
copies the checked native-file pair into the shared candidate directory and records
which source snapshot owns its relative run paths. It never promotes `latest` or
requires another design window to stop editing.

Snapshot folder names use a verified 16-character prefix to stay within native Windows
file-path limits. The complete inventory hash, runtime record and source file hashes
remain in `source_snapshot.json` and the candidate's `contracts/` directory. Corpus
recordings are copied from the licensed input manifest and checked before copying.

## Tool authority

Rhino owns accepted architectural geometry, issued drawings, and the Revit handoff. A
current Rhino release requires both:

- one `.3dm` file whose hash is recorded;
- one acceptance manifest for the exact run ID and model ID.

If either file is absent or mismatched, the release records Rhino as `blocked` and stores
no `.3dm` in `latest/`.

Blender owns rendering, animation, and web presentation. Every `.blend` and GLB remains
`presentation_only`. A Blender render cannot establish Rhino acceptance. Portable SVG
sheets are stored as `candidate` previews until the matching Rhino model is accepted.

## Evidence policy

- Current UI, README, and review screenshots use stable `latest` paths.
- An archived image cites its full version ID and release status.
- Superseded models, intermediate exports, and rejected audit rounds remain available only
  as labelled historical or negative evidence.
- Mixed-source portfolio plates are retired because no single manifest can support their
  claims.

## Verification

`python -m backend.scripts.publish_model_version --check` rehashes every asset in `latest/`
and its immutable archive, compares the two inventories, verifies the Rhino pairing rule,
requires the Blender scene and GLB, and checks the saved exact-geometry visual measurement.
Focused tests also hold the stable public URLs and the exact Rhino acceptance contract.

## Consequences

An old Rhino file can no longer occupy the current Revit slot. A new Blender scene can be
published immediately for rendering while Rhino remains visibly blocked. Once Rhino review
accepts the matching geometry, the same release route publishes the `.3dm` pair and changes
the latest status to accepted.
