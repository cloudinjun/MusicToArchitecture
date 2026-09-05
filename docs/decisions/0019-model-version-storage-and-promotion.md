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
