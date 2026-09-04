# Public release checklist

## Release decisions

- [x] First public release uses a reserved-rights `LICENSE`; public visibility grants no
  general permission to copy, modify, redistribute, or commercialize the project.
- [x] Project owner authorized public release of the included project files on
  2026-09-03, including the documented Gemini/Lyria MP3 fixture.
- [ ] Add maintainer and citation metadata, such as `CITATION.cff`, when the public
  author name and preferred citation are known.
- [x] Initialize the repository on the `main` branch and prepare the public GitHub target.

## Repository checks

- [x] Source, fixtures, runtime exchange, documentation, and artifacts have distinct homes.
- [x] Local caches, Blender backups, runtime contracts, and large per-run outputs are ignored.
- [x] The frozen web directory contains only its demo assets; corpus GLBs are archived with runs.
- [x] Public navigation exists in the root README, `docs/README.md`, and `artifacts/README.md`.
- [x] Run the web production build and lint immediately before publishing.
- [ ] Complete a fresh full backend run after the in-progress local architecture changes
  are ready for integration. The public baseline retains the last completed full result.
- [x] Review the final staged file list for secrets, personal paths, and files larger than the
  hosting provider's limit.
- [x] Check every Markdown link after the repository URL and default branch are known.

## Claim checks

- [x] Keep `docs/evidence_matrix.md` aligned with artifacts that actually exist.
- [x] Preserve `unevaluated`, `not_checked`, and `professional_review_required` statuses.
- [x] State that code tables and site values are placeholders where applicable.
- [x] Do not present the work as code compliant, safe, permit ready, or construction ready.

## Current verification

Baseline verification on 2026-09-01:

- Backend: `399 passed, 5 skipped` in 38m 42s; four third-party deprecation warnings.
- Web production build: passed; the bundler reported a large-chunk advisory.
- Web lint: passed.
- Local Markdown links: 70 files checked, no broken repository-relative links.

Release verification on 2026-09-03:

- Web production build and lint: passed; the large-chunk advisory remains non-blocking.
- Staged content: 362 files; no file exceeds 100 MB, and scans found no common secret
  signatures or local user/workspace paths.
- Local Markdown links: 80 files checked with no broken repository-relative links; all
  detected frozen-demo model, drawing, and render references resolve.
- The latest full backend rerun was intentionally interrupted after unrelated working-tree
  changes appeared; no result from that run is claimed.
- The staged public baseline keeps those later business changes outside the release commit.
