# Real-audio saturation corpus

> **Superseded — read the verdicts below as history, not as status (noted 2026-09-03).**
>
> This run is the evidence that motivated two fixes, and it predates both. Everything
> below describes code that no longer exists:
>
> - **Saturation.** The three FAIL lines were what drove the range calibration in
>   `artifacts/audio_saturation/calibration/proposed_ranges.json`, now shipped in
>   `audio.py`. Re-normalising these same fourteen recordings' raw measurements with the
>   ranges `audio.py` carries today puts **every one of the twelve features at 0 of 14
>   near-endpoint**, against the 28.6% exact / 31.0% near recorded here.
> - **One building, fourteen times.** Every track here reports `library / frame` because
>   typology, tectonic system, structural system and plan extent were module constants
>   at the time. They are decisions now — see the docstring of
>   `backend/tests/test_differentiation.py`, which exists so they cannot silently become
>   constants again. Two opposite scores now compile a theater in Postmodernism on an
>   RC frame and a pavilion in Critical Regionalism on glulam.
>
> The per-track manifests here also predate the fields `run_audio_saturation_corpus.py`
> now records (`massing_id`, `facade_grammar_id`, `envelope_tectonic_id`, `selection`),
> which is the quickest way to tell this corpus from a current one. Re-run the corpus to
> replace these numbers; do not cite them as the pipeline's present behaviour.

14/14 recordings completed the audio → Shared Score → v3 datum/program/structure/envelope chain.

## Saturation result

- Raw-feature exact endpoint rate: 28.6%
- Raw-feature near-endpoint rate (±0.02): 31.0%
- Shared Score near-endpoint rate: 25.7%
- Variable-datum near-endpoint rate: 27.3%
- Score/model collision rate: 0.0% / 0.0%

## Predeclared checks

- PASS — pipeline success rate: 1.0
- FAIL — feature exact endpoint rate: 0.2857142857142857
- FAIL — feature near-endpoint rate: 0.30952380952380953
- FAIL — worst single-feature near-endpoint rate: 0.7142857142857143
- PASS — score signature collision rate: 0.0
- PASS — model signature collision rate: 0.0
- PASS — minimum variable coverage: 1.0

## Highest-saturation metrics

| Metric | Near endpoint | Exact endpoint | Normalised span | Raw p05–p95 |
|---|---:|---:|---:|---:|
| novelty_peak_rate_per_min | 71.4% | 71.4% | 0.16–1.00 | 7.9–35.4 |
| harmonic_ratio | 57.1% | 57.1% | 0.15–1.00 | 0.514–0.97 |
| spectral_flatness | 57.1% | 42.9% | 0.00–0.27 | 0.000152–0.0443 |
| rms_energy | 50.0% | 50.0% | 0.23–1.00 | 0.0713–0.45 |
| onset_density_hz | 42.9% | 35.7% | 0.10–1.00 | 0.81–5.9 |
| periodicity | 42.9% | 35.7% | 0.22–1.00 | 0.732–4.38 |

## Per recording

| Recording | Curated style | Feature near | Score near | Datum near | Elements | Runtime |
|---|---|---:|---:|---:|---:|---:|
| Symphony No. 29 in A major, K. 201 (excerpt) | Classical orchestral | 16.7% | 0.0% | 0.0% | 4952 | 4.9s |
| L'Art de toucher le clavecin (recorded excerpt) | Baroque harpsichord | 25.0% | 10.0% | 10.3% | 4558 | 2.0s |
| Silience Is Gold | Dub / roots reggae | 8.3% | 10.0% | 10.3% | 5290 | 2.2s |
| Wake-up Call Intro – 24 Hours | Detroit techno | 33.3% | 40.0% | 48.3% | 6728 | 2.3s |
| Hymne III | Black metal / noise | 41.7% | 40.0% | 41.4% | 4660 | 2.3s |
| Guitar Soundscape 1 | Ambient guitar / drone | 16.7% | 0.0% | 0.0% | 5593 | 2.3s |
| His Akorns | Electronic industrial | 25.0% | 30.0% | 34.5% | 5674 | 2.2s |
| Like Life Easily Ended | Indie rock | 25.0% | 20.0% | 24.1% | 4142 | 2.2s |
| Visions | Trip-hop / breakbeats / jazz | 41.7% | 30.0% | 34.5% | 7026 | 2.3s |
| Accorte | Acousmatic / electroacoustic improvisation | 41.7% | 30.0% | 24.1% | 5467 | 1.8s |
| Bueid | Portuguese guitar / electronic world music | 33.3% | 20.0% | 20.7% | 4351 | 1.4s |
| Rainfields | Electropop / IDM / ambient | 41.7% | 40.0% | 31.0% | 5017 | 1.4s |
| Blind Istanbul | Alternative hip-hop / jazz-funk / dub | 41.7% | 40.0% | 44.8% | 5464 | 1.4s |
| Cancer | Hardcore punk / thrash / crust | 41.7% | 50.0% | 58.6% | 5667 | 1.4s |

## Scope

- Each source is a real recording with a source page and declared license.
- Every run uses a deterministic 30-second centre excerpt transcoded to mono MP3.
- This evaluates calibration and output differentiation. It does not test full-song sectional form.
- Style labels are curator/source metadata. The audio extractor does not classify genre.
- Structural code tables remain project placeholders; no result claims code compliance or safety.
