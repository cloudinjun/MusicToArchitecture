"""Run the full music audit with temporary v3 candidate pins.

The audit runner owns the pipeline, output contracts, evidence hashing, and review
render.  This wrapper changes only the three candidate decisions at runtime, then
restores the original compiler entry point before returning.
"""

from __future__ import annotations

import argparse
import functools
import sys
from pathlib import Path

# Allow the helper to be called by file path as well as ``python -m`` from the
# repository root, matching the public audit runner's package imports.
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--track', action='append', help='Select ids; default all tracks')
    parser.add_argument('--review', action='store_true', help='Render bound diagnostic views')
    parser.add_argument('--massing', required=True,
                        help='v3 massing family id to pin for this candidate')
    parser.add_argument('--typology', required=True,
                        help='v3 typology id to pin for this candidate')
    parser.add_argument('--grammar', dest='grammar_id',
                        help='Optional v3 facade grammar id to pin for this candidate')
    return parser


def _runner_argv(args: argparse.Namespace) -> list[str]:
    """Translate wrapper arguments to the unchanged audit runner CLI."""
    argv = [sys.argv[0], '--manifest', str(args.manifest), '--output', str(args.output)]
    for track in args.track or []:
        argv.extend(['--track', track])
    if args.review:
        argv.append('--review')
    return argv


def _control_payload(args: argparse.Namespace, *, status: str,
                     error: str | None = None) -> dict:
    payload = {
        'schema_version': 'mta-design-director/candidate-control-v1',
        'status': status,
        'runtime_pins': {
            'massing_id': args.massing,
            'typology': args.typology,
            'grammar_id': args.grammar_id,
        },
        'v2_companion': {
            'pipeline': 'backend.app.compiler.compile_building_model',
            'score_driven': True,
            'runtime_pins_applied': False,
            'note': 'The v2 acceptance companion remains score-driven; only the v3 candidate compiler is wrapped.',
        },
        'authority': {
            'candidate': 'candidate_unreviewed',
            'presentation': 'presentation_only',
            'professional_review': 'professional_review_required',
        },
        'runner': 'backend.scripts.run_visual_music_audit.main',
        'wrapper': 'mta-design-director/scripts/run_pinned_music_candidate.py',
        'output': str(args.output.resolve()),
    }
    if error:
        payload['error'] = error
    return payload


def main() -> None:
    args = _parser().parse_args()
    output = args.output.resolve()
    output.relative_to(ROOT)
    # Keep ``--help`` usable in a lean environment: the audit imports optional
    # audio/render dependencies only after argparse has accepted a real run.
    from backend.app import pipeline
    from backend.scripts import run_visual_music_audit as audit

    original = pipeline.compile_building_model_v3
    original_argv = sys.argv

    @functools.wraps(original)
    def pinned_compile(*compile_args, **compile_kwargs):
        compile_kwargs['massing_id'] = args.massing
        compile_kwargs['typology'] = args.typology
        if args.grammar_id is not None:
            compile_kwargs['grammar_id'] = args.grammar_id
        return original(*compile_args, **compile_kwargs)

    status = 'completed'
    error = None
    try:
        pipeline.compile_building_model_v3 = pinned_compile
        sys.argv = _runner_argv(args)
        audit.main()
    except BaseException as exc:
        status = 'failed'
        error = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        pipeline.compile_building_model_v3 = original
        sys.argv = original_argv
        # The runner owns atomic JSON writes; keep the control record in the same
        # contract and make it available even when a run stops after preserving a
        # failure artifact.
        try:
            audit.write_json(output / 'candidate_control.json',
                             _control_payload(args, status=status, error=error))
        except Exception:
            if status == 'completed':
                raise


if __name__ == '__main__':
    main()
