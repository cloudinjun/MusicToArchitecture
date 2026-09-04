# Contributing

This repository is a research prototype for traceable design-intent computation. Read
`PROJECT_CHARTER.md` and `AGENTS.md` before changing architecture or scope.

## Where changes belong

- Portable compiler and validation logic: `backend/app/`
- Reproducible maintenance and generation commands: `backend/scripts/`
- Python tests: `backend/tests/`
- Shared deterministic inputs: `fixtures/`
- Web workbench: `web/`
- Decisions, contracts, and experiments: `docs/`
- Blender adapters and examples: `blender/`
- Generated evidence and local outputs: `artifacts/`

Do not commit local runtime contracts, per-run output, Blender backups, dependency
folders, or build caches. Keep the frozen web demo only when its report, GLB, drawings,
and renders describe the same generated run.

## Verify a change

From the repository root on Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
Set-Location web
npm run build
npm run lint
```

Regenerate `web/public/reports/demo_run.json` with
`python -m backend.scripts.generate_web_demo` whenever the payload shape, datum table,
drawings, renders, or GLB changes.

## Pull-request notes

Explain which charter ability (V1–V4) the change supports, which quality gate it
strengthens, and how it was verified. Report limitations and unevaluated checks directly;
do not convert them into passes.
