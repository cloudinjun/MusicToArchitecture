# Real-audio saturation corpus

14/14 recordings completed the audio → Shared Score → v3 datum/program/structure/envelope chain.

## Saturation result

- Raw-feature exact endpoint rate: 0.0%
- Raw-feature near-endpoint rate (±0.02): 0.0%
- Shared Score near-endpoint rate: 0.0%
- Variable-datum near-endpoint rate: 0.0%
- Score/model collision rate: 0.0% / 0.0%

## Predeclared checks

- PASS — pipeline success rate: 1.0
- PASS — feature exact endpoint rate: 0.0
- PASS — feature near-endpoint rate: 0.0
- PASS — worst single-feature near-endpoint rate: 0.0
- PASS — score signature collision rate: 0.0
- PASS — model signature collision rate: 0.0
- PASS — minimum variable coverage: 1.0

## Highest-saturation metrics

| Metric | Near endpoint | Exact endpoint | Normalised span | Raw p05–p95 |
|---|---:|---:|---:|---:|
| dynamic_range_db | 0.0% | 0.0% | 0.24–0.87 | 2.46–43.3 |
| harmonic_ratio | 0.0% | 0.0% | 0.28–0.75 | 0.514–0.97 |
| novelty_peak_rate_per_min | 0.0% | 0.0% | 0.09–0.82 | 7.9–35.4 |
| onset_density_hz | 0.0% | 0.0% | 0.10–0.85 | 0.81–5.9 |
| periodicity | 0.0% | 0.0% | 0.14–0.87 | 0.732–4.38 |
| rms_energy | 0.0% | 0.0% | 0.12–0.86 | 0.0713–0.45 |

## Per recording

| Recording | Curated style | Feature near | Score near | Datum near | Elements | Runtime |
|---|---|---:|---:|---:|---:|---:|
| Symphony No. 29 in A major, K. 201 (excerpt) | Classical orchestral | 0.0% | 0.0% | 0.0% | 4948 | 4.1s |
| L'Art de toucher le clavecin (recorded excerpt) | Baroque harpsichord | 0.0% | 0.0% | 0.0% | 4426 | 1.3s |
| Silience Is Gold | Dub / roots reggae | 0.0% | 0.0% | 0.0% | 5290 | 1.4s |
| Wake-up Call Intro – 24 Hours | Detroit techno | 0.0% | 0.0% | 0.0% | 5371 | 1.4s |
| Hymne III | Black metal / noise | 0.0% | 0.0% | 0.0% | 4608 | 1.4s |
| Guitar Soundscape 1 | Ambient guitar / drone | 0.0% | 0.0% | 0.0% | 5279 | 1.4s |
| His Akorns | Electronic industrial | 0.0% | 0.0% | 0.0% | 4851 | 1.4s |
| Like Life Easily Ended | Indie rock | 0.0% | 0.0% | 0.0% | 4228 | 1.4s |
| Visions | Trip-hop / breakbeats / jazz | 0.0% | 0.0% | 0.0% | 5277 | 1.4s |
| Accorte | Acousmatic / electroacoustic improvisation | 0.0% | 0.0% | 0.0% | 5624 | 1.4s |
| Bueid | Portuguese guitar / electronic world music | 0.0% | 0.0% | 0.0% | 4029 | 1.6s |
| Rainfields | Electropop / IDM / ambient | 0.0% | 0.0% | 0.0% | 4630 | 2.1s |
| Blind Istanbul | Alternative hip-hop / jazz-funk / dub | 0.0% | 0.0% | 0.0% | 4772 | 2.1s |
| Cancer | Hardcore punk / thrash / crust | 0.0% | 0.0% | 0.0% | 4865 | 2.2s |

## Scope

- Each source is a real recording with a source page and declared license.
- Every run uses a deterministic 30-second centre excerpt transcoded to mono MP3.
- This evaluates calibration and output differentiation. It does not test full-song sectional form.
- Style labels are curator/source metadata. The audio extractor does not classify genre.
- Structural code tables remain project placeholders; no result claims code compliance or safety.

## What changed since `corpus-2026-08-30`

Same 14 recordings, same 30-second deterministic centre slice, same pipeline. The only
difference is the normalisation layer in `backend/app/audio.py`: ranges and transforms
now come from `backend/scripts/calibrate_audio_ranges.py` instead of from a single
44-second fixture.

| measure | before | after |
|---|---:|---:|
| raw feature exact-endpoint rate | 28.6 % | **0.0 %** |
| raw feature near-endpoint rate | 31.0 % | **0.0 %** |
| shared score near-endpoint rate | 25.7 % | **0.0 %** |
| datum near-endpoint rate | 27.3 % | **0.0 %** |
| worst single feature | `novelty_peak_rate` 71.4 % | **0.0 %** |
| score signature collisions | 0 % | 0 % |
| model signature collisions | 0 % | 0 % |
| minimum variable coverage | 100 % | 100 % |
| program fit rate | 8/14 | 8/14 |

The two rates that were already at zero stay at zero, and the program fit rate is
unchanged — the readings moved apart without making the buildings harder to inhabit.

`interruption`, the dimension the previous round flagged as the top priority, was pinning
`void_count`, `void_scale` and `terrace_count` against their upper limits on 10 of 14
tracks. It no longer pins on any.

This still measures normalisation and output difference on a 30-second slice, not full-song
sectional form. The audio is not committed; the cache lives outside the repository.
