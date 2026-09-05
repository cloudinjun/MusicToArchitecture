# Model versions

`latest/` is a verified mirror of one immutable folder under `archive/`. The pointer in
`latest.json` names that archive and records the Rhino and Blender status. A file outside
this structure cannot be cited as the current model.

```text
model_versions/
  latest.json
  latest/                         verified mirror
    manifest.json
    portable/building_model_v3.json
    rhino/status.json
    blender/scene_v3.blend
    blender/model_v3.glb
    renders/
    drawings/portable_preview/
    contracts/
  archive/<version_id>/           immutable release
  legacy_index.json               superseded and rejected evidence
```

## Authority

| Asset | Use | Required current status |
|---|---|---|
| `rhino/model.3dm` + `rhino/acceptance.json` | architectural drawings and Revit handoff | `accepted_geometry` for the exact run, model ID, and `.3dm` hash |
| `blender/scene_v3.blend` | rendering and animation | `presentation_only` |
| `blender/model_v3.glb` | web preview | `presentation_only` |
| `drawings/portable_preview/*.svg` | automated drawing preview | `candidate`; never a Rhino-issued set |

A release without a matching Rhino pair contains `rhino/status.json` with `blocked` and
contains no `.3dm`. The existing historical Rhino smoke file is archived separately and
cannot be used for drawings or Revit delivery.

## Publish and verify

Generate a candidate and promote it through the verifier:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.generate_web_demo
.\.venv\Scripts\python.exe -m backend.scripts.publish_model_version --check
```

After Rhino review and accepted baking, publish the exact pair:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.publish_model_version `
  --rhino-3dm rhino/path/to/model.3dm `
  --rhino-manifest rhino/path/to/acceptance.json
```

The acceptance JSON must contain `status: accepted`, `authority: accepted_geometry`, and
the exact `run_id`, `model_id`, and `geometry_sha256`. The publisher verifies every copied
asset and the exact compiler-source fingerprint, creates an immutable archive, replaces
`latest/` atomically, and updates only stable `/latest/` URLs in the web deployment. A
source edit during generation aborts the run; an older candidate cannot be promoted after
source code changes.

`contracts/visual_geometry_measurement.json` travels with each release. It records the
bounded polygon/vertical checks used in the visual audit and retains every unevaluated
count; it does not upgrade Blender output or claim code compliance.

Current screenshots must come from `latest/renders/`. Archived screenshots must cite the
full version ID and its status. Rejected visual-audit rounds remain negative evidence and
must be labelled as rejected when shown.
