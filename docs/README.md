# Documentation guide

Start with the project claim, then follow the decisions into implementation evidence.

| Read this | Use it for |
|---|---|
| [`../PROJECT_CHARTER.md`](../PROJECT_CHARTER.md) | North star, scope filter, quality gates, and required portfolio evidence |
| [`evidence_matrix.md`](evidence_matrix.md) | What is demonstrated, verified, incomplete, or still missing |
| [`decisions/`](decisions/) | Accepted architecture and ownership boundaries |
| [`guidelines/`](guidelines/) | Program and structural-system contracts |
| [`style_guides/facade/`](style_guides/facade/) | Facade grammar variables and validation rules |
| [`experiments/`](experiments/) | Controlled experiment records and calibration data |
| [`native_model_workflow.md`](native_model_workflow.md) | Grasshopper, Rhino, Blender, and GLB regeneration |
| [`revit_dynamo_handoff.md`](revit_dynamo_handoff.md) | Proposed design-to-BIM boundary, Dynamo graph plan, sync policy, and validation experiment |
| [`contracts/revit_dynamo_mapping.v1.json`](contracts/revit_dynamo_mapping.v1.json) | Machine-readable Revit category, parameter, identity, and fallback registry |
| [`legacy_migration.md`](legacy_migration.md) | Rules for using the read-only legacy repository |
| [`public_release_checklist.md`](public_release_checklist.md) | Remaining publication checks |
| [`project_origin.zh-CN.md`](project_origin.zh-CN.md) | Historical Chinese planning summary |
| [`../artifacts/README.md`](../artifacts/README.md) | Generated-output and evidence map |

## Organization rules

- Keep durable decisions in `decisions/`, measured trials in `experiments/`, and reusable
  system contracts in `guidelines/`.
- Keep directory depth shallow. Add a subdirectory only when several files share one
  stable purpose.
- Use repository-relative paths in public documentation.
- Record an evidence claim only after the named artifact and verification exist.
