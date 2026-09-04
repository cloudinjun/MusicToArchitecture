"""Recalibrate the audio normalisation ranges against a measured corpus.

The ranges shipped in `audio.py` were guessed from a single 44-second fixture. The
14-track cross-genre corpus showed what that costs: 31 % of raw readings landed within
0.02 of an endpoint, and `novelty_peak_rate_per_min` pinned on 10 of 14 tracks. A pinned
feature is not a measurement -- every track that pins gets the same building parameter,
so the dimension stops discriminating exactly where the music is most distinctive.

This script derives replacement ranges from the corpus instead of from intuition, and it
searches two things at once:

- **the transform.** Several features are not linearly distributed. `spectral_flatness`
  runs 0.0001 / 0.0037 / 0.055 for min / median / max -- a linear range piles almost
  every track into the bottom fifth whatever the endpoints are. `harmonic_ratio` is the
  mirror image, bunched against 1.0 because most music is harmonic. A log or logit
  transform is not a cosmetic fix here; it is what makes the spacing mean anything.
- **the endpoints.** Anchored on the 5th and 95th percentiles rather than the extremes,
  so one outlying recording cannot stretch the range and flatten everyone else, then
  widened by a margin so a track outside the corpus still has somewhere to go.

Selection is by two criteria in order: no reading may sit within 0.02 of an endpoint,
and among the candidates that satisfy that, the one whose normalised values spread most
evenly across 0..1 wins. Even spread is the point -- it is what lets two recordings that
differ musically produce datums that differ architecturally.

    python -m backend.scripts.calibrate_audio_ranges
    python -m backend.scripts.calibrate_audio_ranges --apply
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = (ROOT / 'artifacts' / 'audio_saturation' / 'corpus-2026-08-30'
          / 'corpus_saturation_report.json')
AUDIO = ROOT / 'backend' / 'app' / 'audio.py'
OUT = ROOT / 'artifacts' / 'audio_saturation' / 'calibration'

NEAR = 0.02
MARGINS = (0.15, 0.22, 0.30, 0.40, 0.55, 0.75, 1.0)

# The ranges currently compiled into audio.py, for the before/after.
CURRENT: dict[str, tuple[float, float]] = {
    'tempo_bpm': (60.0, 180.0),
    'rms_energy': (0.015, 0.25),
    'onset_density_hz': (0.3, 5.0),
    'spectral_centroid_hz': (500.0, 5000.0),
    'periodicity': (0.0, 2.8),
    'timbre_variation': (12.0, 160.0),
    'dynamic_range_db': (6.0, 40.0),
    'novelty_peak_rate_per_min': (1.0, 20.0),
    'spectral_contrast_db': (12.0, 30.0),
    'harmonic_ratio': (0.15, 0.85),
    'spectral_flatness': (0.002, 0.20),
    'zero_crossing_rate': (0.02, 0.20),
}

# A feature bounded on 0..1 that bunches against an end is a logit candidate; a strictly
# positive feature with a long right tail is a log candidate. Both are offered to every
# feature and the corpus decides.
BOUNDED = {'harmonic_ratio', 'spectral_flatness', 'zero_crossing_rate'}


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def transform(name: str, value: float) -> float | None:
    if name == 'linear':
        return value
    if name == 'log':
        return math.log(value) if value > 1e-12 else None
    if name == 'logit':
        clipped = min(1.0 - 1e-6, max(1e-6, value))
        return math.log(clipped / (1.0 - clipped))
    raise ValueError(name)


def percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    position = q * (len(sorted_values) - 1)
    low = int(math.floor(position))
    high = min(low + 1, len(sorted_values) - 1)
    weight = position - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def uniformity(normalised: list[float]) -> float:
    """1.0 when the readings sit on an even ladder across 0..1, lower when they clump."""
    if len(normalised) < 2:
        return 0.0
    ordered = sorted(normalised)
    n = len(ordered)
    ideal = [(i + 0.5) / n for i in range(n)]
    deviation = sum(abs(a - b) for a, b in zip(ordered, ideal)) / n
    return max(0.0, 1.0 - 4.0 * deviation)


def evaluate(values: list[float], name: str, low: float, high: float) -> dict | None:
    mapped = [transform(name, v) for v in values]
    if any(m is None for m in mapped) or high <= low:
        return None
    normalised = [clamp01((m - low) / (high - low)) for m in mapped]
    near = sum(1 for v in normalised if v <= NEAR or v >= 1.0 - NEAR)
    return {
        'transform': name,
        'low': low,
        'high': high,
        'normalised': normalised,
        'near': near,
        'near_rate': near / len(normalised),
        'span': max(normalised) - min(normalised),
        'uniformity': uniformity(normalised),
    }


def candidates(values: list[float]) -> list[dict]:
    out: list[dict] = []
    names = ['linear', 'log']
    if all(0.0 <= v <= 1.0 for v in values):
        names.append('logit')
    for name in names:
        mapped = [transform(name, v) for v in values]
        if any(m is None for m in mapped):
            continue
        ordered = sorted(mapped)
        p05, p95 = percentile(ordered, 0.05), percentile(ordered, 0.95)
        core = p95 - p05
        if core <= 0:
            core = (max(ordered) - min(ordered)) or 1.0
        for margin in MARGINS:
            result = evaluate(values, name, p05 - core * margin, p95 + core * margin)
            if result:
                result['margin'] = margin
                out.append(result)
    return out


# Headroom the range must keep beyond the corpus extremes, as a share of the range.
# Fourteen recordings do not cover the space, and a range fitted exactly to them clips
# the first track that falls outside -- which is what the gemini fixture, an ambient
# generated piece slower than anything in the corpus, immediately demonstrated. The
# corpus sets the shape; it does not get to define the edges of the world.
OUTSIDE_HEADROOM = 0.12


# Bounds that are known independently of any corpus, in each feature's own units.
#
# Headroom as a share of the range is the wrong instrument on its own: it is measured
# from the corpus extremes, so it can only reach as far as the corpus already reaches.
# The 14 tracks bottom out around 80 BPM, so 12 % of the range bought a floor of 74 BPM
# -- and the gemini fixture, at 64.6 BPM, pinned immediately. Ambient and drone sit
# lower still.
#
# So where a quantity has an extent that is known from its definition or from the
# physics rather than from these recordings, that extent is stated here and the range
# must contain it. Tempo markings run from largo to prestissimo; spectral flatness runs
# from a pure tone to white noise; a zero-crossing rate cannot exceed half the sample
# rate. Only features with a defensible independent extent appear -- `periodicity`,
# `timbre_variation`, `novelty_peak_rate_per_min`, `onset_density_hz`, `rms_energy` and
# `spectral_contrast_db` are outputs of a particular algorithm at a particular hop size,
# and inventing bounds for them would be guessing dressed as knowledge. Those keep the
# corpus-plus-headroom rule alone.
#
# The cost is real and intended: a range wide enough for music the corpus does not
# contain is a range the corpus does not fill. Fourteen tracks landing across 0.2..0.9
# discriminate perfectly well; a track pinned at 0.0 does not discriminate at all.
DOMAIN_BOUNDS: dict[str, tuple[float, float]] = {
    'tempo_bpm': (40.0, 220.0),               # largo to prestissimo
    'spectral_centroid_hz': (100.0, 8000.0),  # bass fundamental to cymbal wash
    'spectral_flatness': (1e-5, 0.7),         # pure tone to broadband noise
    'harmonic_ratio': (0.02, 0.98),           # HPSS cannot resolve past either end
    'zero_crossing_rate': (0.005, 0.5),       # sub-bass drone to white noise
    'dynamic_range_db': (0.5, 60.0),          # brickwalled master to unlimited orchestra
}


def widen_to_domain(feature: str, option: dict) -> dict:
    """Extend a candidate range until it contains the feature's known extent."""
    bounds = DOMAIN_BOUNDS.get(feature)
    if not bounds:
        return option
    low, high = (transform(option['transform'], v) for v in bounds)
    if low is None or high is None:
        return option
    return {**option, 'low': min(option['low'], low), 'high': max(option['high'], high)}


def has_headroom(values: list[float], option: dict) -> bool:
    mapped = [transform(option['transform'], v) for v in values]
    if any(m is None for m in mapped):
        return False
    width = option['high'] - option['low']
    if width <= 0:
        return False
    margin = width * OUTSIDE_HEADROOM
    return (min(mapped) - margin >= option['low']
            and max(mapped) + margin <= option['high'])


def choose(feature: str, values: list[float]) -> dict | None:
    """No reading may pin, the range must survive material outside the corpus, and
    among the candidates that satisfy both, the most evenly spread wins.

    Widening to the known domain happens *before* the candidates are judged, so the
    uniformity being compared is the uniformity of the range that actually ships.
    """
    options = []
    for option in candidates(values):
        widened = widen_to_domain(feature, option)
        scored = evaluate(values, widened['transform'], widened['low'], widened['high'])
        if scored:
            options.append({**scored, 'margin': option['margin']})
    if not options:
        return None
    clean = [o for o in options if o['near'] == 0 and has_headroom(values, o)]
    if not clean:
        clean = [o for o in options if o['near'] == 0]
    pool = clean or options
    return max(pool, key=lambda o: (o['near'] == 0, has_headroom(values, o),
                                    o['uniformity'], o['span']))


def round_range(name: str, low: float, high: float) -> tuple[float, float]:
    """Keep the published numbers readable without moving them enough to matter."""
    def tidy(value: float) -> float:
        if value == 0:
            return 0.0
        magnitude = math.floor(math.log10(abs(value)))
        digits = max(0, 3 - magnitude - 1)
        return round(value, min(digits, 6))
    if name in ('log', 'logit'):
        return round(low, 4), round(high, 4)
    return tidy(low), tidy(high)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true',
                        help='write the chosen ranges into backend/app/audio.py')
    args = parser.parse_args()

    report = json.loads(REPORT.read_text(encoding='utf-8'))
    raw_by_feature: dict[str, list[float]] = {}
    for track in report['tracks']:
        for key, value in (track.get('metric_raw_values') or {}).items():
            raw_by_feature.setdefault(key, []).append(float(value))

    per_feature = report.get('per_feature', {})
    print(f'corpus: {len(report["tracks"])} recordings, '
          f'{len(raw_by_feature)} features with per-track raw values\n')

    header = (f'{"feature":26} {"n":>3} {"tf":>6} {"margin":>7} '
              f'{"near now":>9} {"near new":>9} {"unif":>6} {"span":>6}   new range')
    print(header)
    print('-' * len(header))

    chosen: dict[str, dict] = {}
    for feature, values in sorted(raw_by_feature.items()):
        best = choose(feature, values)
        if not best:
            print(f'{feature:26} {len(values):>3}   no viable candidate')
            continue
        low, high = round_range(best['transform'], best['low'], best['high'])
        verify = evaluate(values, best['transform'], low, high)
        was = per_feature.get(feature, {}).get('near_endpoint_rate', float('nan'))
        chosen[feature] = {**best, 'low': low, 'high': high,
                           'near_after_rounding': verify['near'] if verify else -1,
                           'near_before': was}
        print(f'{feature:26} {len(values):>3} {best["transform"]:>6} '
              f'{best["margin"]:>7.2f} {was:>8.0%} '
              f'{(verify["near_rate"] if verify else 1):>8.0%} '
              f'{best["uniformity"]:>6.2f} {best["span"]:>6.2f}   '
              f'{low:g} .. {high:g}')

    missing = sorted(set(CURRENT) - set(raw_by_feature))
    if missing:
        print(f'\nno per-track raw values in the report for: {", ".join(missing)}')
        print('their ranges are left untouched; re-run the corpus with raw capture for '
              'these before calibrating them.')

    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        'source_report': str(REPORT.relative_to(ROOT)).replace('\\', '/'),
        'corpus_size': len(report['tracks']),
        'near_endpoint_epsilon': NEAR,
        'selection_rule': ('no reading within 0.02 of an endpoint; among those, the most '
                           'evenly spread across 0..1'),
        'features': {
            name: {
                'transform': data['transform'],
                'low': data['low'],
                'high': data['high'],
                'margin': data['margin'],
                'domain_bounds': DOMAIN_BOUNDS.get(name),
                'near_rate_before': data['near_before'],
                'near_count_after': data['near_after_rounding'],
                'uniformity': round(data['uniformity'], 4),
                'normalised': [round(v, 4) for v in data['normalised']],
            } for name, data in chosen.items()
        },
        'untouched': missing,
    }
    (OUT / 'proposed_ranges.json').write_text(json.dumps(payload, indent=2),
                                              encoding='utf-8')
    print(f'\nwrote {(OUT / "proposed_ranges.json").relative_to(ROOT)}')

    if args.apply:
        apply_ranges(chosen)


def apply_ranges(chosen: dict[str, dict]) -> None:
    """Rewrite the `_metric(...)` calls in audio.py in place."""
    source = AUDIO.read_text(encoding='utf-8')
    changed = 0
    for feature, data in chosen.items():
        pattern = re.compile(
            r'(' + re.escape(feature) + r'=_metric\(\s*\n\s*[a-z_]+,\s*)'
            r'([-\d.eE]+),\s*([-\d.eE]+)(,)')
        replacement = (lambda m, d=data:
                       f'{m.group(1)}{d["low"]!r}, {d["high"]!r}{m.group(4)}')
        source, count = pattern.subn(replacement, source)
        changed += count
        if count == 0:
            print(f'  !! could not rewrite {feature}; edit it by hand')
    AUDIO.write_text(source, encoding='utf-8')
    print(f'applied {changed} range changes to {AUDIO.relative_to(ROOT)}')
    print('transforms still need wiring by hand where transform != linear')


if __name__ == '__main__':
    main()
