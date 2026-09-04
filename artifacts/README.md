# Artifact guide

This directory holds generated evidence, reports, and local run output. Source code and
hand-authored project rules live elsewhere.

| Directory | Purpose | Publication policy |
|---|---|---|
| `evidence/` | Curated same-run screenshots and manifests | Keep selected evidence |
| `style_evidence/` | Cross-track massing, facade, and structure comparisons | Keep summary sheets and report |
| `audio_saturation/` | Calibration and cross-genre experiment results | Keep summaries; per-track payloads are ignored |
| `gemini_smoke_test/` | Small deterministic smoke-test record | Keep |
| `audits/` | Review findings and limitations | Keep |
| `coupling/` | Program–structure–facade screening reports | Keep selected reports |
| `fidelity_probe/` | Target-state Blender probe with no design authority | Keep only when cited |
| `integrated_demo/`, `v3_demo/` | Reproducible demo contracts and render sets | Keep named demos |
| `drawings/`, `native_models/generated/` | Regenerable local exports | Ignored |
| `v3_runs/`, `web_runs/`, `inspector/` | Per-run and standalone inspection output | Ignored |

The public web demo lives in `web/public/`. Only assets referenced by
`web/public/reports/demo_run.json` should remain there; research-corpus assets belong
with their run under `artifacts/v3_runs/`.

Useful generators:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.generate_web_demo
.\.venv\Scripts\python.exe -m backend.scripts.generate_v3_demo
.\.venv\Scripts\python.exe -m backend.scripts.render_style_evidence
```

Generated evidence never upgrades itself to Rhino-accepted geometry, code compliance,
or professional approval. Read the manifest and local README before citing an artifact.
