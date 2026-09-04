# Test fixtures

Shared, deterministic inputs used by tests and demo-generation scripts live here.
Fixtures are inputs; generated models and reports belong in `artifacts/` or
`web/public/`.

## Audio fixture

`audio/gemini_music_to_architecture_44s.mp3` is the 43.96-second Gemini/Lyria input
used by the smoke test and frozen demo.

- SHA-256: `b7ad95fa45a6d546149a4256eb6677ea3f147e0652151d6a0b783846a8695d39`
- Purpose: deterministic audio extraction, score compilation, and end-to-end tests
- Provenance and measured limitations: `artifacts/gemini_smoke_test/README.md`

Before a public release, the maintainer must confirm that this generated audio may be
redistributed under the repository's chosen license. Do not add third-party recordings
without source, license, and hash metadata.
