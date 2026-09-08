# Music to Architecture

Implementation overview, inspected 2026-09-04. The diagram shows how shared musical intent reaches two independently compiled building contracts and their downstream tools. Branches indicate data dependencies; the Python runner executes v2 and v3 sequentially.

Solid arrows show implemented data or adapter paths. Dashed arrows show handoffs still requiring interactive validation or acceptance. The Rhino adapter emits candidate geometry only; Rhino acceptance and live Revit/Dynamo validation remain pending. The three report labels identify distinct verdict categories, without asserting an overall pass.

The glyphs and thumbnails are an archived specimen: `20260904T234614Z-v3.4.0-d7cb03bc14a1-98b0ba3b0a89`, status `latest_preview` when inspected. Its v3 model is `building-v3-5b3193b619f5`; Rhino is blocked. This specimen has `cutaway=True`; current normal compilation uses `cutaway=False`, and the Rhino candidate adapter requires a complete model. The image therefore illustrates output objects, not a new compile or proof of current source geometry.

| Relationship | Source |
|---|---|
| MP3 → features → score; v2/v3 branches; exports | `backend/app/pipeline.py:112–205`, `audio.py`, `score.py` |
| Score → datums/lattice → allocation/selection → element groups | `backend/app/compiler_v3.py:3750–4041`, `datums.py`, `program.py`, `selection.py` |
| Brief, site, grammar and sizing constraints | `briefs.py`, `site.py`, `grammar_specs.py`, `sizing.py` |
| GH pending; Rhino acceptance blocked | `backend/app/integration.py:391–403`, decision 0006 |
| Full v3 model → Rhino candidate geometry | `rhino/import_building_model_v3.py:310–399`, `rhino/README.md` |
| GLB, portable drawings, reports → browser | `pipeline.py`, `analysis_bundle.py`, `main.py`, `backend/scripts/generate_web_demo.py` |
| Stored runs and version promotion | `backend/app/run_store.py`, `backend/scripts/publish_model_version.py`, archived `manifest.json` |

Audio glyphs read six recorded segments, independently scaled within each feature. The signature reads all ten score dimensions in the order stored in the scene. The lattice, level L01 zone footprints, v2 massing boxes and v3 structural member paths are drawn from the archived JSON. North is model +Y, not a surveyed orientation. The scale bar reads model metres. The structural glyph is a subset of the element groups, not a complete structural analysis. The section sheet and Blender render are embedded verbatim; no generated or retouched imagery is used. Input image hashes and original archive paths are stored in the scene.

Edit `system_architecture.drawio` or `system_architecture.svg`. Text, connections and logical groups remain editable; the render and section sheet are embedded image objects. The portable scene JSON is the reproducible source. This standalone figure uses the requested skill's scene exporter to leave project implementation code unchanged; it follows the portfolio's Times/grayscale/no-title canvas convention. Re-export with `concise-research-figures/scripts/figure_scene.py`, set its SVG arrow marker fill to `#6b6b6b`, then rasterize that SVG with Sharp at 3300 px width. Keep this filename outside the paper generator's `fig*_*.*` replacement scope.

The SVG was rendered and visually inspected at full overview and 1200 px display width. XML structure, unique IDs, native text, groups and embedded images were checked. A diagrams.net editor session was not opened; automatic connector rerouting after node movement was not tested.
