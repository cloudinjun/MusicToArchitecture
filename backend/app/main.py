"""HTTP for the pipeline: one generate route, the run library, and run artifacts.

What a run *is* lives in `pipeline.py`. This module maps it onto requests, refuses
uploads it should not accept, and serves the files a run leaves on disk so the web
client can show the drawings and stills rather than only the numbers describing them.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .blender_export import BlenderExportError
from .drawings import DRAWING_DIRECTORY
from .models import GenerationResponse, RunSummary
from .pipeline import RENDER_DIRECTORY, compile_generation
from .run_store import list_runs, load_run, store_run

MAX_UPLOAD_BYTES = 30 * 1024 * 1024

# Matched before anything is joined to a directory; `_safe_artifact` then requires the
# resolved path to stay inside the artifact tree. Neither check is sufficient alone.
SAFE_ID = re.compile(r'^[A-Za-z0-9_-]{1,80}$')
SAFE_FILENAME = re.compile(r'^[A-Za-z0-9_.-]{1,120}$')

app = FastAPI(title="Music to Architecture API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _safe_artifact(base: Path, model_id: str, filename: str) -> Path:
    if not SAFE_ID.fullmatch(model_id) or not SAFE_FILENAME.fullmatch(filename):
        raise HTTPException(status_code=400, detail="Malformed artifact reference")
    candidate = (base / model_id / filename).resolve()
    if not candidate.is_relative_to(base.resolve()):
        raise HTTPException(status_code=400, detail="Malformed artifact reference")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return candidate


@app.get("/api/models/{model_id}/drawings/{filename}")
def drawing_sheet(model_id: str, filename: str) -> FileResponse:
    """One issued sheet as SVG, cut from the model the viewport is showing."""
    return FileResponse(_safe_artifact(DRAWING_DIRECTORY, model_id, filename),
                        media_type='image/svg+xml')


@app.get("/api/models/{model_id}/renders/{filename}")
def render_still(model_id: str, filename: str) -> FileResponse:
    return FileResponse(_safe_artifact(RENDER_DIRECTORY, model_id, filename),
                        media_type='image/png')


@app.get("/api/runs", response_model=list[RunSummary])
def runs() -> list[RunSummary]:
    """The run library, newest first."""
    return list_runs()


@app.get("/api/runs/{run_id}", response_model=GenerationResponse)
def run(run_id: str) -> GenerationResponse:
    stored = load_run(run_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="No stored run with that id")
    return stored


@app.post("/api/generate", response_model=GenerationResponse)
async def generate(file: UploadFile = File(...)) -> GenerationResponse:
    filename = Path(file.filename or "upload.mp3").name
    if Path(filename).suffix.lower() != ".mp3":
        raise HTTPException(status_code=415, detail="Only MP3 uploads are supported")

    payload = await file.read(MAX_UPLOAD_BYTES + 1)
    if not payload:
        raise HTTPException(status_code=400, detail="The uploaded MP3 is empty")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The MP3 exceeds the 30 MB MVP limit")

    try:
        with TemporaryDirectory(prefix="music-to-architecture-") as temp_dir:
            audio_path = Path(temp_dir) / "source.mp3"
            audio_path.write_bytes(payload)
            response = await asyncio.to_thread(compile_generation, audio_path, filename)
    except BlenderExportError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=422,
            detail="The MP3 could not be decoded or analyzed") from error

    # Kept so the run can be reopened and compared. A storage failure is not a
    # generation failure: the caller already has the payload in hand.
    try:
        await asyncio.to_thread(store_run, response)
    except OSError:
        pass
    return response
