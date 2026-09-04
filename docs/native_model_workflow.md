# Native Modeling Workflow

All three modeling environments consume the same shared model contract. Per-run
accepted geometry requires an explicit Rhino acceptance manifest:

```text
runtime/inbox/building_model_v2.json
    ├─ facade_host_handoff: stable host faces + 10-dimension availability + gates
    ├─ Grasshopper: monitored, parsed, candidate geometry, validated
    ├─ Rhino: explicit acceptance + editable Breps + geometry manifest
    └─ Blender: presentation-only semantic adapter, editable scene, GLB, and manifest

pipeline_run_manifest
    └─ joins authored guideline hashes, stage status, artifact hashes, blockers, and authority
```

These are original new-repository artifacts. No legacy `.gh`, `.3dm`, or `.blend`
binary was copied. The legacy repository was inspected only for file-watching,
coordinate, collection, metadata, and execution-safety conventions.

## Grasshopper

Open `grasshopper/MusicToArchitecture_MVP.gh` in Rhino 8 Grasshopper. Its path panel
points to `runtime/inbox/building_model_v2.json` relative to the repository root.
Toggle `Refresh` after atomically replacing that JSON file.

The definition deliberately separates five responsibilities:

1. contract watcher;
2. schema gate and parser;
3. massing generator;
4. frame generator;
5. validation and accepted-state report.

For the Gemini smoke fixture, the component statuses report 17 accepted elements,
5 closed massing Breps, 12 closed frame Breps, zero failed checks, and zero elements
without score bindings. The model-scale slider changes the Grasshopper preview only;
the source JSON remains unchanged.

## Rhino

Open `rhino/MusicToArchitecture_Gemini_SmokeTest.3dm`. The file contains:

- `MTA_Massing`: 5 named Breps;
- `MTA_Structure`: 12 named Breps;
- `MTA_Site`: 1 site Brep.

Each building object carries `mta:model_id`, `mta:score_id`, `mta:element_id`,
`mta:kind`, `mta:program`, and serialized `mta:score_bindings` user strings.

## Blender

Open `blender/examples/MusicToArchitecture_Gemini_SmokeTest.blend`, or regenerate it with:

```powershell
$env:BLENDER_EXE = (Get-Command blender).Source
& $env:BLENDER_EXE `
  --background --factory-startup `
  --python 'blender\import_building_model.py' -- `
  'runtime\inbox\building_model_v2.json' `
  'blender\examples\MusicToArchitecture_Gemini_SmokeTest.blend' `
  'artifacts\native_models\blender_render.png' `
  'artifacts\native_models\blender_scene_state.json' `
  'web\public\models\demo\library-pavilion.glb' `
  'web\public\models\demo\library-pavilion.manifest.json'
```

The importer validates schema version and object budget, preserves every source ID and
score binding, and keeps source massing in a hidden `MTA_Source` collection. It creates
an exportable colored program copy of each occupied source volume, then derives five
facade panels per volume, perimeter beams, floor slabs, supplemental entry/service
columns, and isolated pad foundations. The exported asset contains these semantic
collections:

- `MTA_Program_Massing`;
- `MTA_Facade`;
- `MTA_Structure_Columns`;
- `MTA_Structure_Beams`;
- `MTA_Structure_Slabs`;
- `MTA_Structure_Foundations`;
- `MTA_Site`.
- `MTA_Site_Context`;
- `MTA_Context_Trees`;
- `MTA_Context_Vehicles`;
- `MTA_Context_People`.

Every exported mesh carries `mta:layer`, `mta:subsystem`, `mta:category`, model/score
provenance, program, and either `mta:element_id` or `mta:derived_from`. Public,
private, and circulation massing use cobalt, red, and green materials. Seven additional
basic Blender materials distinguish gallery facade, entry facade, service facade,
columns, beams, slabs, foundations/site, paving, road, trees, vehicles, and people.
The six trees are 5.4–7.0 m tall, the two cars are 4.4 m long, and the four people are
1.75 m tall. Each context asset records `mta:context_type`, `mta:context_id`, and
`mta:context_role`. The backend runs this importer after each successful MP3 compile
and publishes the GLB under `web/public/models/generated/`.

The browser loads the GLB produced by Blender. It offers Overall, Program, Facade, and
Structure views. Program exposes independent Public, Private, and Circulation filters;
Structure exposes column, beam, slab, and foundation filters. A world-coordinate X/Y/Z
clipping plane uses Three.js material clipping to inspect the interior without changing
the authored asset. Site context stays visible in Overall, Program, and Facade views
and is suppressed in Structure view to keep structural inspection clear.

After an MP3 run, the browser also renders the backend-authored Shared Score mapping
report below the model. The report joins measured audio, score interpretation, and
actual source-element bindings; downstream Blender presentation geometry is excluded
from its coverage count.

## Verification

The checked artifacts were verified in Rhino 8 and Blender 5.0.1. The Blender adapter
reported 17 source objects and 139 web-exportable objects: 5 program masses, 25 facade
panels, 20 columns, 20 beams, 5 slabs, 20 foundations, 1 site object, 3 site-surface
objects, 12 tree parts, 12 vehicle parts, and 16 person parts. Program massing contains
3 public, 1 private, and 1 circulation volume. The context manifest resolves those
parts into 3 site features, 6 trees, 2 vehicles, and 4 people. A Blender reopen check,
GLB manifest inspection, pytest, TypeScript build, and ESLint verified the current
artifact.

`backend/tests/test_native_model_contract.py` compares all source Blender element IDs,
locations, dimensions, and kinds with the shared JSON contract, then verifies the GLB
manifest and subsystem counts.

The facade and secondary structure are schematic adapter geometry for coordination and
inspection. Site context is presentation-only scale reference. Neither layer claims
resolved openings, structural sizing/analysis, landscape design, traffic design,
envelope performance, construction detailing, or detailed code compliance.

The integrated contract and implementation order are defined in
`docs/decisions/0007-integrated-pipeline-run-and-acceptance-contract.md`.
