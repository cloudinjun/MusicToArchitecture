# Gemini / Lyria MP3 smoke test

## Input intent

Gemini was asked to generate a roughly 45-second instrumental track for this prototype. The requested musical arc used a sparse opening, a denser rhythmic build, a short dissonant energy peak, and a sustained resolution. This deliberately targets the four MVP feature channels without treating a waveform as geometry.

Input fixture: `fixtures/audio/gemini_music_to_architecture_44s.mp3`

## Observed pipeline result

| Measure | Result |
|---|---:|
| Duration | 43.9641 s |
| Whole-track tempo estimate | 64.5996 BPM |
| Energy, normalized | 0.4442 |
| Onset density, normalized | 0.3814 |
| Spectral continuity proxy, normalized | 0.1754 |
| Pavilion modules | 3 |
| Generated elements | 17 |
| Elements with score bindings | 17 / 17 |
| Shared Score translations | 7 |
| Mapping-report coverage | 17 / 17 |
| Failed architectural checks | 0 |

Outputs:

- `architectural_score.json`
- `building_model_v2.json`
- `mapping_report.json`
- `generation_response.json`

## Executed Shared Score mapping

| Music observation | Shared Score | Architectural result |
|---|---|---|
| 64.5996 BPM | Tempo of change 0.0383 | 3 repeated public gallery modules |
| RMS energy 0.1194 | Tension / release 0.4442 | 4.81–5.19 m public gallery heights |
| 2.0926 onsets/s | Density 0.3814 | 4.36 m frame bays across 12 source columns |
| 2.0926 onsets/s | Density 0.3814 | 7.31–7.59 m public gallery depths |
| 2.0926 onsets/s | Density 0.3814 | 6.50 m private service volume width |
| 1289.104 Hz spectral proxy | Continuity 0.1754 | 1.30 m gallery module gaps |
| 1289.104 Hz spectral proxy | Continuity 0.1754 | 0.40 m circulation entry threshold |

The standalone JSON also records method, confidence, direct/inverse direction,
typology negotiation, rule ID, affected programs, and affected element IDs.

## Honest limitation exposed by the test

The prompt requested a 90-to-128 BPM progression, while the whole-track beat estimator returned 64.6 BPM. A single global `librosa.beat.beat_track` result can select a half-time pulse and cannot faithfully describe a changing-tempo piece. The MVP remains deterministic and valid, but the displayed tempo should be read as an estimator output rather than ground truth.

Continuity is also explicitly labeled `inferred`: spectral centroid is only a proxy and
does not directly measure musical legato or formal continuity.

A later iteration should retain the global value for compatibility while adding segment-level tempo estimates, a tempo-confidence field, and a controlled comparison fixture before allowing tempo to drive more consequential architectural parameters.
