# Rhino model files

Both adapters consume the complete `building_model_v3.json` used by the Blender
adapter. They preserve metre units, source identities, openings, semantic layers,
and source group/assembly membership. Every output remains a geometry candidate.

The standalone [official rhino3dm SDK](https://github.com/mcneel/rhino3dm) supports
file creation without starting Rhino:

```powershell
python -m rhino.export_file --model FULL_MODEL_JSON --run-id EXACT_RUN_ID --output NEW_DIRECTORY
```

Install `rhino3dm` and the backend dependencies in the Python runtime. The command
refuses to overwrite a directory. It saves `model.3dm`, the exact source JSON and
`candidate_manifest.json`, then reopens the file and checks all native bodies,
source metadata, layers, groups and geometry serialization. Curved rectangular
ramps are converted to exact side-profile extrusions only when both caps and every
connecting source face match. Unsupported or invalid conversions stop the export.

The RhinoCommon adapter additionally measures native volume. Run it only in an
explicit isolated empty Rhino document, using the MCP slot's `__rhino_doc__`:

```python
import runpy
adapter = runpy.run_path(r'ABSOLUTE_PATH/rhino/import_building_model_v3.py')
adapter['export_to_document'](__rhino_doc__, FULL_MODEL_JSON, NEW_DIRECTORY,
                              run_id=EXACT_RUN_ID)
```

File readback establishes serialization and solid validity. GUI architectural
review, native volume in the standalone SDK, Revit import, and Rhino acceptance
remain separate checks. The recorded local `License Not Found` condition blocks
the GUI route; the file SDK does not change licensing or application settings.
Neither adapter writes an `accepted_geometry` record or promotes `latest`.
