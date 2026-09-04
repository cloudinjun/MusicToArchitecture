"""Where a completed run is kept so it can be reopened, compared, and cited.

A run takes a minute of audio analysis and two Blender invocations to produce, and
until now it existed only in the browser tab that asked for it. Storing the response
turns the web client from a demo into a workbench: the run library is what makes
"the same piece, one dimension pinned" a thing a designer can look at side by side
rather than a thing they have to remember.

Two rules hold here:

- **The stored file is the response, unaltered.** Nothing is summarised on the way in.
  A summary that drifts from the payload it describes is worse than no summary, so
  `summarise` reads the stored payload every time rather than caching its own copy.
- **The key is the run id, which is a hash of the run's full identity** -- the audio,
  the compiler version, and the model identity that came out (which carries the pins
  and the four selection outcomes). An identical re-run replaces its own identical
  entry; a re-run after anything changed stores beside the old one, so an older run's
  assets are never silently replaced and one piece can keep several pinned variants.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import GenerationResponse, RunSummary

ROOT = Path(__file__).resolve().parents[2]
RUN_DIRECTORY = ROOT / 'artifacts' / 'web_runs'

# A run id is `run-` and twelve hex characters from the audio hash. Anything else did
# not come from this pipeline and is not looked up on disk.
_RUN_ID_LENGTH = 16


def _is_run_id(value: str) -> bool:
    return (len(value) == _RUN_ID_LENGTH and value.startswith('run-')
            and all(character in '0123456789abcdef' for character in value[4:]))


def run_path(run_id: str) -> Path | None:
    if not _is_run_id(run_id):
        return None
    return RUN_DIRECTORY / f'{run_id}.json'


def store_run(response: GenerationResponse) -> Path | None:
    """Write one response to the run library. Returns the file, or None if unkeyed."""
    path = run_path(response.run_id)
    if path is None:
        return None
    RUN_DIRECTORY.mkdir(parents=True, exist_ok=True)
    # Written to a sibling and moved into place: a half-written run that a listing
    # picks up mid-write is a corrupt entry, and the atomic replace costs nothing.
    staging = path.with_suffix('.json.partial')
    staging.write_text(response.model_dump_json(indent=1), encoding='utf-8')
    staging.replace(path)
    return path


def load_run(run_id: str) -> GenerationResponse | None:
    path = run_path(run_id)
    if path is None or not path.is_file():
        return None
    try:
        return GenerationResponse.model_validate_json(path.read_text(encoding='utf-8'))
    except ValueError:
        # An entry written by an older schema. It is not an error for the library to
        # contain one; it is a reason not to serve it as if it were current.
        return None


def summarise(response: GenerationResponse) -> RunSummary:
    analysis = response.analysis
    selection = analysis.selection if analysis else None
    compliance = analysis.compliance if analysis else None
    return RunSummary(
        run_id=response.run_id,
        # The member-level id, because that is what the drawings, the renders and the
        # GLB are keyed by. The v2 massing id is in the payload for anyone who needs it.
        model_id=analysis.model_id if analysis else response.building_model.model_id,
        score_id=response.architectural_score.score_id,
        generated_at=response.generated_at,
        source_filename=response.audio_features.provenance.filename,
        typology=analysis.typology if analysis else response.architectural_score.typology,
        massing_id=selection.massing_id if selection else '',
        structural_system_id=analysis.structural_system_id if analysis else '',
        facade_grammar_id=analysis.facade_grammar_id if analysis else '',
        element_count=analysis.element_count if analysis else len(response.building_model.elements),
        variable_coverage=(response.translation_report.variable_coverage
                           if response.translation_report else None),
        failed_checks=compliance.failed_total if compliance else 0,
        unevaluated_checks=compliance.unevaluated_total if compliance else 0,
        overall_status=response.pipeline_manifest.overall_status,
    )


def list_runs() -> list[RunSummary]:
    """Every stored run, newest first. Unreadable entries are skipped, not raised."""
    if not RUN_DIRECTORY.is_dir():
        return []
    summaries: list[RunSummary] = []
    for path in RUN_DIRECTORY.glob('run-*.json'):
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
            response = GenerationResponse.model_validate(payload)
        except (ValueError, OSError):
            continue
        summaries.append(summarise(response))
    return sorted(summaries, key=lambda summary: summary.generated_at, reverse=True)
