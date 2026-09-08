# Model versions

## 2026-09-04 M Arch 交付档案

当前候选以 `current_candidate.json` 为准。以下链接固定指向本次交付版本，
后续更新不会改写这些档案：

- [Rhino model.3dm](candidates/20260905T055645Z-v3.7.0-a6eb35023a86-7e0a8c9f8233/rhino/model.3dm)
- [Blender scene_v3.blend](candidates/20260905T055645Z-v3.7.0-a6eb35023a86-7e0a8c9f8233/blender/scene_v3.blend)
- [实际视觉检查记录](candidates/20260905T055645Z-v3.7.0-a6eb35023a86-7e0a8c9f8233/review/visual_review.json)

版本 `20260905T055645Z-v3.7.0-a6eb35023a86-7e0a8c9f8233`，模型
`building-v3-a534abce46cf`。Rhino 文件已通过 SDK 实体检查和保存后重读；
交互验收与 Revit 导入尚未记录。Blender 文件用于渲染。

`latest` 保留正式发布记录；完整候选通过独立指针提供。各首音乐的测试
变体保存在固定源码快照的 `artifacts/corpus/tracks/`，只作为测试档案，不能
覆盖展示候选。引用图片时同时引用其版本或模型 ID、状态及视觉检查记录。
设计修改请另存为新的工作文件，再生成新候选；保留版本档案的原始文件。

[20首音乐复测与原生文件索引](../visual_audit/2026-09-04-march/README.md)
记录了334张已看图片、逐案问题、原生文件和完整版本号。测试档案中的大结构
问题仍保持可见，不能把“生成成功”读成“建筑审查通过”。

## Released versions

`latest/` is a verified mirror of one immutable folder under `archive/`. The pointer in
`latest.json` names that archive and records the Rhino and Blender status. A file outside
this structure cannot be cited as the current released model.

```text
model_versions/
  current_candidate.json          complete M Arch candidate, separate from release
  candidates/<version_id>/        immutable same-run .3dm + .blend + evidence
  source_snapshots/<hash16>/      frozen source and labelled corpus test outputs
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
