# Runtime handoff directory

`runtime/inbox/` is a local exchange point for versioned JSON contracts consumed by
Grasshopper, Rhino, Blender, and integration checks. Its contents are generated and are
ignored by Git.

Regenerate the integrated contracts from the repository root:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.generate_integrated_demo
```

Do not treat files in `runtime/inbox/` as source or accepted geometry. The run manifest
records each artifact's authority, hash, and acceptance state.
