# Audio normalization calibration

## 14-track corpus (2026-08-30)

The ranges above were guessed from one 44-second fixture, and a cross-genre corpus test
showed what that costs. Across 14 tracks spanning dub, drone, folk, noise and orchestral
material, **31 % of raw readings landed within 0.02 of a range endpoint**. A pinned
reading is not a measurement: every recording in that neighbourhood produces the same
building parameter, so the dimension stops discriminating exactly where the music is most
distinctive. `novelty_peak_rate_per_min` pinned on 10 of 14 tracks, which drove
`void_count`, `void_scale` and `terrace_count` to their upper limits in 71 % of the runs.

`backend/scripts/calibrate_audio_ranges.py` now derives the ranges from that corpus. It
searches two things together, because endpoints alone could not have fixed this:

**The transform.** Several of these quantities are not linearly distributed and never
were. `spectral_flatness` runs 0.0001 / 0.0037 / 0.055 for min / median / max — on a
linear range almost every recording piles into the bottom fifth whatever the endpoints
are. `harmonic_ratio` is the mirror image, bunched against 1.0 because most music is
harmonic. Tempo and spectral centroid are perceived logarithmically in the first place.
So `_metric()` takes a `transform` of `linear`, `log` or `logit`, and the corpus chooses
which. The raw value is always reported untransformed; only the normalisation moves.

**The endpoints**, anchored on the 5th and 95th percentiles rather than the extremes, so
one outlying recording cannot stretch the range and flatten everyone else.

Selection is by two criteria in order: no reading may sit within 0.02 of an endpoint, and
among the candidates that pass, the one whose normalised values spread most evenly across
0..1 wins. Even spread is the whole point — it is what lets two recordings that differ
musically produce datums that differ architecturally.

### The corpus does not get to define the edges of the world

Two guards keep the ranges from being fitted to 14 recordings.

*Headroom.* A range must keep 12 % of its width clear beyond the corpus extremes. This
was not a precaution; the first pass omitted it, and the out-of-corpus gemini fixture
immediately pinned on two features.

*Known domain bounds.* Headroom as a share of the range is measured from the corpus
extremes, so it can only reach as far as the corpus already reaches. The 14 tracks bottom
out near 80 BPM, so 12 % bought a floor of 74 BPM — and the 64.6 BPM fixture pinned
anyway. Ambient and drone sit lower still. So where a quantity has an extent known from
its definition or the physics rather than from these recordings, `DOMAIN_BOUNDS` states
it and the range must contain it: tempo from largo to prestissimo, spectral flatness from
a pure tone to white noise, and so on. Only six features qualify. The other six are
outputs of a particular algorithm at a particular hop size, and inventing bounds for them
would be guessing dressed as knowledge; those keep the corpus-plus-headroom rule alone.

Forcing tempo to hold 40..220 BPM flipped it from log back to linear — once the range
must span that much, log stops helping and linear spreads the corpus more evenly. The
cost is paid where the domain is widest: `spectral_centroid_hz` fell from 0.62 uniformity
to 0.30, because the range now accommodates sounds the corpus does not contain. That
trade is intended. Fourteen tracks landing across 0.2..0.9 discriminate perfectly well; a
track pinned at 0.0 does not discriminate at all.

### Calibrated ranges

| feature | transform | range | near-endpoint before → after |
|---|---|---|---|
| `tempo_bpm` | linear | 40 .. 220 bpm | 0 % → 0 % |
| `rms_energy` | linear | 0 .. 0.564 | 50 % → 0 % |
| `onset_density_hz` | linear | 0 .. 7.94 | 43 % → 0 % |
| `spectral_centroid_hz` | log | 100 .. 13 930 Hz | 0 % → 0 % |
| `periodicity` | log | 0.425 .. 7.45 | 43 % → 0 % |
| `timbre_variation` | linear | 0 .. 133 | 7 % → 0 % |
| `dynamic_range_db` | log | 0.5 .. 162 dB | 29 % → 0 % |
| `novelty_peak_rate_per_min` | linear | 0 .. 46.4 /min | 71 % → 0 % |
| `spectral_contrast_db` | log | 19.2 .. 27.9 dB | 0 % → 0 % |
| `harmonic_ratio` | logit | 0.02 .. 0.998 | 57 % → 0 % |
| `spectral_flatness` | log | 1e-5 .. 0.700 | 57 % → 0 % |
| `zero_crossing_rate` | logit | 0.005 .. 0.5 | 14 % → 0 % |

Re-running the corpus against these ranges takes every saturation figure to zero: raw
features 31 % → **0 %**, shared score dimensions 25.7 % → **0 %**, datums 27.3 % →
**0 %**. Signature collisions stay at 0 %, variable coverage stays at 100 %, and the
program fit rate is unchanged at 8/14 — the recalibration moved the readings apart
without making the buildings harder to inhabit.

Two tests hold the line. `test_no_metric_saturates_its_normalisation_range` now covers
all twelve metrics rather than the eight added in schema 3.0 — that gap is precisely what
let `tempo_bpm` pin unnoticed. `test_no_metric_sits_against_an_endpoint_on_out_of_corpus_material`
makes the stronger claim, holding the 0.02 margin on a fixture the calibration never saw.
