/** Formatting, labels, and the one place a backend status becomes a colour. */

import type { MetricValue, AudioFeatures } from './types';

/** Four tones, and no fifth. `unknown` is what an unevaluated check gets: it is not a
 *  pass wearing a lighter colour, and the palette must not let it read as one. */
export type Tone = 'ok' | 'warn' | 'bad' | 'unknown' | 'info';

const TONE_BY_STATUS: Record<string, Tone> = {
  pass: 'ok', passed: 'ok', satisfied: 'ok', accepted: 'ok', available: 'ok',
  verified: 'ok', geometry_checked: 'ok', rule_checked: 'ok', preview_ready: 'ok',
  warning: 'warn', pending: 'warn', unresolved: 'warn', needs_review: 'warn',
  fail: 'bad', failed: 'bad', missing: 'bad', blocked: 'bad',
  unevaluated: 'unknown', not_checked: 'unknown', not_applicable: 'unknown',
  code_inputs_incomplete: 'unknown',
};

export function toneFor(status: string | null | undefined): Tone {
  if (!status) return 'unknown';
  return TONE_BY_STATUS[status] ?? 'info';
}

export function percent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return (value * 100).toFixed(digits) + '%';
}

export function number(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return value.toFixed(digits);
}

export function compact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  if (Math.abs(value) >= 10000) return (value / 1000).toFixed(1) + 'k';
  if (Number.isInteger(value)) return String(value);
  if (Math.abs(value) >= 100) return value.toFixed(0);
  if (Math.abs(value) >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

export function seconds(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  if (value < 60) return value.toFixed(1) + ' s';
  return Math.floor(value / 60) + ' m ' + Math.round(value % 60) + ' s';
}

export function titleCase(value: string): string {
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function shortHash(value: string | null | undefined, length = 10): string {
  if (!value) return '—';
  return value.slice(0, length);
}

export function timestamp(value: string | null | undefined): string {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

/** The twelve measured features, in the order a reader should meet them. */
export const AUDIO_FEATURE_KEYS = [
  'tempo_bpm', 'rms_energy', 'onset_density_hz', 'spectral_centroid_hz',
  'periodicity', 'timbre_variation', 'dynamic_range_db', 'novelty_peak_rate_per_min',
  'spectral_contrast_db', 'harmonic_ratio', 'spectral_flatness', 'zero_crossing_rate',
] as const;

export type AudioFeatureKey = (typeof AUDIO_FEATURE_KEYS)[number];

export const AUDIO_FEATURE_LABELS: Record<AudioFeatureKey, string> = {
  tempo_bpm: 'Tempo',
  rms_energy: 'Energy',
  onset_density_hz: 'Onset density',
  spectral_centroid_hz: 'Spectral centroid',
  periodicity: 'Periodicity',
  timbre_variation: 'Timbre variation',
  dynamic_range_db: 'Dynamic range',
  novelty_peak_rate_per_min: 'Novelty peaks',
  spectral_contrast_db: 'Spectral contrast',
  harmonic_ratio: 'Harmonic ratio',
  spectral_flatness: 'Spectral flatness',
  zero_crossing_rate: 'Zero-crossing rate',
};

export function audioFeatureEntries(
  features: AudioFeatures | null | undefined,
): Array<{ key: AudioFeatureKey; label: string; metric: MetricValue }> {
  if (!features) return [];
  return AUDIO_FEATURE_KEYS
    .map((key) => ({ key, label: AUDIO_FEATURE_LABELS[key], metric: features[key] }))
    .filter((entry): entry is { key: AudioFeatureKey; label: string; metric: MetricValue } =>
      Boolean(entry.metric));
}

export const DIMENSION_LABELS: Record<string, string> = {
  tempo_of_change: 'Tempo of change',
  tension_release: 'Tension / release',
  density: 'Density',
  continuity: 'Continuity',
  repetition: 'Repetition',
  variation: 'Variation',
  hierarchy: 'Hierarchy',
  interruption: 'Interruption',
  polyphony: 'Polyphony',
  genre_style: 'Timbral position',
};

export function dimensionLabel(id: string): string {
  return DIMENSION_LABELS[id] ?? titleCase(id);
}

/** Colour keys for the semantic layers, matched to the viewport's swatches. */
export const LAYER_ORDER = ['structure', 'envelope', 'circulation', 'program', 'site'] as const;
