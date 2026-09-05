# M.Arch model quality and fabrication

## Implemented in compiler 3.5.0

This is an incremental implementation of the thesis-model/3D-printing task, not a
claim that every generated building is presentation-ready or physically printable.
It strengthens V2 (assembly coordination), V3 (reproducible derived artifacts), and
V4 (negative tests and measured failures).

The program emitter now builds located table, chair and shelving assemblies with
named parts. The existing semantic kinds and root IDs are retained; instances add
optional `assembly_id` and `part_role`. Child supports name the actual adjacent parts.
Floor supports are selected from the emitted slabs, including decomposed islands and
holes, rather than inferred from a level name. Complete furniture footprints must fit
the allocated zone, floor and reserved column/lift regions. Unplaceable candidates are
reported in the existing model limitations; they do not produce partial assemblies.

`SP-FURNITURE-COMPLETE` and `SP-FURNITURE-CONTACT` run in the existing spatial report.
They are separate from dependency-graph coverage. Deleting a leg or moving a part away
from a host fails even if another report still contains a host relationship. These
checks validate these three selected recipes, not arbitrary furniture typologies.

Rotated box bounds and swept member bounds now use the same vertex functions as the
Blender box/member adapter. Exact box/extrusion footprint intersections preserve
rotation and holes in the existing broad-phase spatial rules. This does not turn the
entire spatial report into a general 3D solid-clash engine: inclined members, quads,
headroom and unspecified architectural interfaces still have scoped limitations.

## Optional diagnostic STL route

Install the ordinary backend dependencies, then:

```powershell
python -m pip install -r backend/requirements-fabrication.txt
python -m backend.scripts.export_print_model `
  --model artifacts/model_versions/latest/portable/building_model_v3.json `
  --profile fixtures/fabrication/planning_1_100.json `
  --output artifacts/print_diagnostics/first-review
```

The example profile is explicitly **planning**, with no assumed printer, material,
feature threshold or build volume. Its 1:100 scale is an example, not a user-confirmed
choice. The CLI returns 2 when geometry/profile checks are blocked, even when it has
written useful diagnostic files. It never changes `latest/`, v2 acceptance, or Rhino
accepted geometry. Existing destination directories are refused.

Input must be the full v3 model JSON, not the web GLB. Source geometry remains in
metres. STL coordinates are millimetres, using `1000 / scale_denominator` exactly
once. Each output part carries source IDs, file hash and inverse assembly transform.
The package identity includes the complete model, profile, part plan, geometry-library
versions and exact exporter source hashes. Re-running the same inputs produces the
same identity. Unknown representation is not called a complete building, and a
source `cutaway=true` is recorded as sectional.

With no plan, parts are grouped by source level. This is a diagnostic grouping, not
an assertion that floors detach, fit a printer, or have designed joints. A custom
`--plan` JSON explicitly names parts, source IDs and optional XYZ rotations in degrees:

```json
{
  "representation": "sectional",
  "parts": [
    {"id": "example-part", "source_ids": ["actual-source-id"], "rotation_deg": [0, 0, 0]}
  ],
  "exclusions": {"another-actual-id": "Explicit reason for this study"}
}
```

Every source element must occur exactly once in a part or an explained exclusion.
Do not copy the placeholder IDs above into a real plan. Diagnostic defaults exclude
program-zone overlays, scale figures and the earth visualization explicitly.

The exporter creates positive-volume primitive meshes, triangulates concave caps and
holes without filling openings, gives planar quads their declared thickness, performs
Manifold solid union within each part, writes STL, and re-imports the actual file to
check closure, winding, volume and dimensions. It flags disconnected parts, declared
thin features and bed overflow instead of hiding them with global thickening, voxel
remeshing, deletion, or invented connectors. An invalid source prevents the entire
corresponding part from being exported as a misleading partial success.

## What the status fields mean

`geometry_verified` is scoped to the implemented primitive, boolean, shell and STL
round-trip checks. It is not a comprehensive proof of all self-intersection, strength,
minimum local thickness or support conditions.

`profile_screened` covers only the supplied primitive-feature and un-supported-part
build-volume limits. It excludes ungenerated supports, brim/raft, warping, shrinkage,
bridging and layer-direction strength. A `reviewed` profile requires explicit device,
material, limits and a written basis, but that label is not calibration evidence.

`slicer_verified`, `physical_sample_verified` and `assembly_verified` remain
`not_checked`. `release_ready` is false. `--release` refuses promotion: actual slicer
integration/layer checks, support-removal planning, mechanical assembly design and
physical evidence have not been implemented in this first change. Geometry export
success cannot advance those states. No machine commands or print jobs are sent.

The source outer-solid convention for box/CHS profiles is retained, not silently
replaced with fabricated hollow sections. Non-planar quads require a reviewed panel
construction. The feature screen is not a full local-thickness field; local topology
and thin-wall analysis remain required for production. Do not suppress these limits.

## Verification and next quality gate

```powershell
python -m pytest -q backend/tests/test_fabrication.py backend/tests/test_furniture_assemblies.py backend/tests/test_geometry_review.py
python -m pytest -q backend/tests/test_dependencies.py -k "not offset_roofs"
```

Negative tests cover missing legs, floating parts, false floor hosts, point contact,
voids cutting a floor edge, full footprints, rotations, real member depths, concave
I-section caps, architectural holes, non-planar/zero-thickness panels, units, invalid
profiles, source coverage, disconnected solids, bed overflow, thin features,
immutability and prohibited production promotion.

Before promoting new model evidence, regenerate and inspect the complete model,
plans/sections, Blender output and frozen web demo through the existing publication
workflow. Do not overwrite accepted archives or present older renders as the new
geometry. The next implementation gate is a printer-specific assembly/section model
with complete wall/slab/stair/envelope interfaces, designed physical joints and actual
slicer evidence, not additional style or output count.
