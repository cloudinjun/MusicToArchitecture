# Real-audio saturation corpus

14/14 recordings completed the audio → Shared Score → v3 datum/program/structure/envelope chain.

## Saturation result

- Raw-feature exact endpoint rate: 0.0%
- Raw-feature near-endpoint rate (±0.02): 0.0%
- Shared Score near-endpoint rate: 0.0%
- Variable-datum near-endpoint rate: 0.0%
- Score/model collision rate: 0.0% / 0.0%
- Dependency graph pass rate: 85.7%
- Minimum constructed-element connection rate: 100.0%
- Minimum structure-to-soil path rate: 100.0%
- Connection capacity status: not checked

## Predeclared checks

- PASS — pipeline success rate: 1.0
- PASS — feature exact endpoint rate: 0.0
- PASS — feature near-endpoint rate: 0.0
- PASS — worst single-feature near-endpoint rate: 0.0
- PASS — score signature collision rate: 0.0
- PASS — model signature collision rate: 0.0
- PASS — minimum variable coverage: 1.0
- FAIL — dependency graph pass rate: 0.8571428571428571
- FAIL — minimum dependency connected rate: 0.9996159754224271
- PASS — minimum structure-to-soil path rate: 1.0

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

| Recording | Curated style | Feature near | Score near | Datum near | Dependency | Structure path | Elements | Runtime |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Symphony No. 29 in A major, K. 201 (excerpt) | Classical orchestral | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 5791 | 7.5s |
| L'Art de toucher le clavecin (recorded excerpt) | Baroque harpsichord | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 4880 | 1.8s |
| Silience Is Gold | Dub / roots reggae | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 5558 | 2.0s |
| Wake-up Call Intro – 24 Hours | Detroit techno | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 4279 | 1.7s |
| Hymne III | Black metal / noise | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 4969 | 2.1s |
| Guitar Soundscape 1 | Ambient guitar / drone | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 5125 | 2.0s |
| His Akorns | Electronic industrial | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 3986 | 1.8s |
| Like Life Easily Ended | Indie rock | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 3315 | 1.7s |
| Visions | Trip-hop / breakbeats / jazz | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 4272 | 1.8s |
| Accorte | Acousmatic / electroacoustic improvisation | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 5743 | 2.0s |
| Bueid | Portuguese guitar / electronic world music | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 2857 | 1.8s |
| Rainfields | Electropop / IDM / ambient | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 4963 | 2.0s |
| Blind Istanbul | Alternative hip-hop / jazz-funk / dub | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 2955 | 1.6s |
| Cancer | Hardcore punk / thrash / crust | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 3938 | 1.7s |

## Scope

- Each source is a real recording with a source page and declared license.
- Every run uses a deterministic 30-second centre excerpt transcoded to mono MP3.
- This evaluates calibration and output differentiation. It does not test full-song sectional form.
- Style labels are curator/source metadata. The audio extractor does not classify genre.
- Structural code tables remain project placeholders; no result claims code compliance or safety.
