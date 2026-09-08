# Bounded brief on the canonical pipeline

The API accepts multipart `project_brief` JSON and optional `layout_controls` JSON. Both are validated before compilation. `compile_generation(..., project_brief=brief)` chooses the Program Volume path unless an incompatible explicit legacy mode was supplied, which is rejected before audio work. Layout controls without a brief are rejected. The saved GenerationResponse carries the actual input brief.

The batch entry `backend.scripts.run_visual_music_audit` accepts `--project-brief <json>` and optional `--layout-controls <json>`. Supplying a brief selects Program Volume mode. This is an explicit supplied brief; music-only brief generation is not yet automatically invoked here. No CLI/API default plot of 448 m2 is implied when no brief is supplied.

V2 remains the parallel legacy companion required by the existing acceptance contract. Its `building_model` is not evidence of bounded v3 area. Verify the supplied brief, v3 Program Volume geometry and emitted v3 file together; do not interpret v2 dimensions as v3 dimensions.

`stage_errors.v3_export` and `stage_errors.drawings` retain optional-stage failures. A missing preview no longer discards the original Blender exception. The batch's absent-v3 error includes these details. V3 compilation failures still propagate; they are not changed into a successful bounded model.

Blender's v3 importer calls `require_polygon_runtime` before scene generation. It loads the isolated `.venv/blender_dependencies` directory and exercises constrained Delaunay tessellation. Missing/broken imports identify the actual Python version and target requirements directory. No runtime package installation or hole-filling fallback is performed.

Verification: 17 API, pipeline-handoff, preview-isolation and audit-runner tests passed. A 28 x 16 m (448 m2) brief reaches the v3 compiler in the handoff test; explicit legacy use is refused. Blender 5.0's actual bundled Python 3.11.13 loaded isolated Shapely 2.1.2 and passed the triangulation smoke test. The handoff test mocks generation: no complete 448 m2 native building or real-audio batch success is claimed by this change. That end-to-end run remains required. Prior native candidates have older compiler fingerprints and were not republished.
