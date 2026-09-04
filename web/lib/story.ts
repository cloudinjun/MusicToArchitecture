/**
 * The performance script: what the feed says while the building assembles.
 *
 * Two registers, deliberately separated. The evidence panels keep the compiler's own
 * sentences verbatim — clause numbers, section designations, thresholds. This feed is
 * the *telling*: plain-language lines a visitor's parent could follow, written as
 * templates and filled only with values from the run. The rule that survives the
 * polish: every number in a sentence exists in the payload, and a stage with no data
 * says less — it never invents.
 */

import type { GenerationResponse } from './types';
import { dimensionLabel, titleCase } from './format';

export interface StoryStage {
  id: string;
  index: string;
  title: string;
  /** The semantic layer assembling while this stage speaks; null for bookends. */
  layer: string | null;
  lines: string[];
}

/** Cut at a word boundary, never mid-word — “the modul…” reads as a glitch. */
export function trimWords(text: string | null | undefined, max = 100): string {
  if (!text) return '';
  if (text.length <= max) return text;
  const cut = text.lastIndexOf(' ', max - 1);
  return text.slice(0, cut > 40 ? cut : max - 1).replace(/[,;·—-]$/, '').trimEnd() + '…';
}

/**
 * Compiler reasons open with their evidence key — “incident 0.73: one dominant
 * voice…”. The evidence stays inspectable in the panels; the telling starts at the
 * sentence.
 */
export function cleanReason(text: string | null | undefined, max = 110): string {
  if (!text) return '';
  const bare = text.replace(/^[a-z_/ ]+[0-9.]+\s*:\s*/i, '').trim();
  const sentence = bare.charAt(0).toUpperCase() + bare.slice(1);
  return trimWords(sentence, max);
}

function firstSentence(text: string): string {
  const stop = text.indexOf('. ');
  return stop > 0 ? text.slice(0, stop + 1) : text;
}

function seismicInWords(category: string): string {
  if (category === 'D' || category === 'E' || category === 'F') return 'serious earthquake country';
  if (category === 'C') return 'moderate earthquake demand';
  return 'quiet ground';
}

export function buildStory(run: GenerationResponse): StoryStage[] {
  const analysis = run.analysis;
  const selection = analysis?.selection ?? null;
  const score = run.architectural_score;
  const stages: StoryStage[] = [];

  // 00 — the listening. The music, before any geometry exists.
  const duration = Math.round(run.audio_features.provenance.duration_seconds);
  const topDimensions = [...score.dimensions]
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 3);
  const coverage = run.translation_report?.variable_coverage ?? null;
  stages.push({
    id: 'score', index: '00', title: 'The score', layer: null,
    lines: [
      'We listened to ' + duration + ' seconds of music and measured '
      + score.dimensions.length + ' of its qualities.',
      ...topDimensions.map((dimension) =>
        dimensionLabel(dimension.id) + ' came out at ' + dimension.value.toFixed(2)
        + ' — ' + cleanReason(firstSentence(dimension.architectural_proposal), 88)),
      ...(coverage !== null ? [
        coverage >= 0.995
          ? 'Every variable choice in this design traces back to the music.'
          : Math.round(coverage * 100) + '% of the variable design traces back to the music.',
      ] : []),
    ],
  });

  // 01 — the ground it stands on.
  const site = analysis?.site ?? null;
  stages.push({
    id: 'site', index: '01', title: 'The site', layer: 'site',
    lines: site ? [
      'It stands in ' + site.location.city + ' — '
      + seismicInWords(String(site.seismic_design_category.value))
      + ', design winds of ' + String(site.basic_wind_speed_ms.value) + ' m/s.',
      'Site values no engineer has reviewed stay marked as provisional — they never quietly become facts.',
    ] : ['No site is recorded for this run.'],
  });

  // 02 — the bones, and the checking behind them.
  const sizing = analysis?.sizing?.[0] ?? null;
  stages.push({
    id: 'structure', index: '02', title: 'The structure', layer: 'structure',
    lines: [
      ...(selection && analysis ? [
        'Of the structural systems screened, ' + selection.admissible_systems.length
        + ' could carry this building. The music chose a '
        + titleCase(analysis.structural_system_id.replace(/^STR-SYS-/, '').toLowerCase()).toLowerCase()
        + '.',
      ] : []),
      ...(sizing ? [
        'Its hardest-working ' + sizing.role.replace(/_/g, ' ') + ' runs at '
        + Math.round(sizing.utilisation * 100)
        + '% of its checked capacity (' + sizing.section_id + ').',
      ] : []),
    ],
  });

  // 03 — the face it shows the street.
  const gates = analysis?.facade_gates ?? null;
  const gatesPassed = gates?.gates.filter((gate) => gate.verdict === 'passed').length ?? 0;
  stages.push({
    id: 'envelope', index: '03', title: 'The envelope', layer: 'envelope',
    lines: [
      ...(selection ? [
        'The form is ' + selection.massing_label.toLowerCase() + ': '
        + cleanReason(selection.massing_reason[0], 96).toLowerCase(),
      ] : []),
      ...(gates ? [
        'The facade speaks ' + gates.grammar_label + ', and '
        + (gatesPassed === gates.gates.length
          ? 'passes all ' + gates.gates.length
          : 'passes ' + gatesPassed + ' of ' + gates.gates.length)
        + ' of that style’s own written rules.',
      ] : []),
    ],
  });

  // 04 — how people move, and get out.
  const egressPasses = analysis?.life_safety?.findings
    .filter((finding) => finding.status === 'pass').length ?? 0;
  stages.push({
    id: 'circulation', index: '04', title: 'Moving through it', layer: 'circulation',
    lines: [
      ...(analysis?.accessible_route
        ? ['A wheelchair ramp meets the ADA accessibility standard — switchbacks, landings and all.']
        : analysis?.accessible_route_unresolved
          ? ['No compliant ramp fits this form, so a stair stands in — and the design says so openly.']
          : []),
      ...(egressPasses ? [
        'Every escape route was measured, not assumed: ' + egressPasses
        + ' fire-safety checks pass.',
      ] : []),
    ],
  });

  // 05 — the life inside.
  const allocation = analysis?.program_allocation ?? null;
  const biggestRoom = allocation?.zones.reduce<typeof allocation.zones[number] | null>(
    (best, zone) => (!best || zone.area_delivered_m2 > best.area_delivered_m2 ? zone : best),
    null) ?? null;
  stages.push({
    id: 'program', index: '05', title: 'Life inside', layer: 'program',
    lines: [
      ...(analysis && allocation ? [
        'Inside, a ' + analysis.typology + ': '
        + Math.round(allocation.delivered_area_m2) + ' of the '
        + Math.round(allocation.required_area_m2) + ' m² the brief asked for found a place'
        + (allocation.unplaced.length > 0
          ? ' — and the ' + allocation.unplaced.length
          + ' spaces that did not fit are admitted, not hidden.'
          : '.'),
      ] : []),
      ...(biggestRoom ? [
        'Its largest room is the ' + biggestRoom.label.toLowerCase()
        + ', at ' + Math.round(biggestRoom.area_delivered_m2) + ' m².',
      ] : []),
    ],
  });

  // 06 — what was checked, and what refuses to claim more than it knows.
  const compliance = analysis?.compliance ?? null;
  stages.push({
    id: 'verify', index: '06', title: 'Checked, not assumed', layer: null,
    lines: compliance ? [
      compliance.passed_total
      + ' independent checks passed — structure, fire escape, accessibility, facade.',
      ...(compliance.failed_total > 0 ? [
        compliance.failed_total + ' checks failed, and they are shown, not hidden.',
      ] : []),
      ...(compliance.unevaluated_total > 0 ? [
        compliance.unevaluated_total
        + ' questions stay honestly open rather than being assumed away.',
      ] : []),
      'This is a design proposal: a licensed architect holds the final word.',
    ] : ['No verification record travels with this run.'],
  });

  return stages.map((stage) => ({ ...stage, lines: stage.lines.filter(Boolean) }))
    .filter((stage) => stage.lines.length > 0);
}
