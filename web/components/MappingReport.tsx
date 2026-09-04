import { downloadJson } from '../lib/api';
import { number } from '../lib/format';
import type { MappingReport as MappingReportData, MappingReportEntry } from '../lib/types';


/**
 * Where inside the declared range the music actually landed — and where it did not.
 *
 * The range and the direction are the architectural decision; the music only chooses a
 * position within them. Without the range on screen a reader cannot tell a rule that
 * travelled its whole span from one that barely moved.
 *
 * The track spans the declared range *and* whatever was applied, rather than the
 * declared range alone. On the demo run `ENERGY_TO_READING_HEIGHT` declares 5.4–7.2 m
 * and applies from 4.8, because the site envelope overruled it. Clamping the drawing
 * to the declared range would hide the one entry where architecture overrode the
 * music, which is the event this report exists to record.
 */
function RangeBar({ entry }: { entry: MappingReportEntry }) {
  // An inverse rule declares its range high-first, so neither end can be assumed.
  const [first, second] = entry.declared_output_range;
  const lo = Math.min(first, second);
  const hi = Math.max(first, second);
  const from = Math.min(entry.applied_min, entry.applied_max);
  const to = Math.max(entry.applied_min, entry.applied_max);
  if (!(hi > lo)) return null;

  const start = Math.min(lo, from);
  const end = Math.max(hi, to);
  const domain = end - start;
  if (!(domain > 0)) return null;

  const pct = (value: number) => ((value - start) / domain) * 100;
  const outside = from < lo || to > hi;
  const digits = hi < 10 ? 2 : 1;
  // One mark when every affected element took the same value, two when they span.
  const marks = from === to ? [from] : [from, to];

  return (
    <div className="mapping-range">
      {/* The same bar vocabulary the translation health report uses: the band is the
          region a value is allowed to occupy, the marks are where this run landed, and
          `is-clamped` means it did not land inside. Two reports, one bar. */}
      <div className="range-bar" aria-hidden="true">
        <div className="range-track" />
        <div
          className={'range-band' + (outside ? ' is-clamped' : '')}
          style={{ left: `${pct(lo)}%`, width: `${pct(hi) - pct(lo)}%` }}
        />
        {marks.map((value) => (
          <div key={value} className="range-marker" style={{ left: `${pct(value)}%` }} />
        ))}
      </div>
      <p className="mapping-meta">
        declared {number(lo, digits)}–{number(hi, digits)} {entry.applied_unit}
        {' · applied '}
        {from === to
          ? number(from, digits)
          : `${number(from, digits)}–${number(to, digits)}`}
        {outside && <b className="mapping-range-flag"> · outside the declared range</b>}
      </p>
    </div>
  );
}


function formatMusicValue(entry: MappingReportEntry): string {
  if (entry.music_feature === 'tempo_bpm') return entry.music_value.toFixed(1);
  if (entry.music_feature === 'spectral_centroid_hz') return entry.music_value.toFixed(0);
  return entry.music_value.toFixed(2);
}


function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}


/** The building the viewport is drawing, when it is not the one this report counted. */
export interface MappingSubject {
  typology: string;
  grammarId: string;
  elementCount: number;
}


/**
 * The v2 contract names its one grammar in its own vocabulary and the v3 selection names
 * ten in the style guides'; this pair denotes a single grammar. Mirrors
 * `V2_GRAMMAR_ALIASES` in `backend/app/analysis_bundle.py` so this banner appears on
 * exactly the runs where the compliance roll-up also separates the two buildings — one
 * rule, two panels, rather than two panels disagreeing about whether it is one building.
 */
const GRAMMAR_ALIASES: Record<string, string> = {
  international_style_informed: 'FCD-01-INTERNATIONAL-STYLE',
};

const canonicalGrammar = (id: string) => GRAMMAR_ALIASES[id] ?? id;


export function MappingReport(
  { report, reportGrammarId, viewportBuilding }: {
    report: MappingReportData;
    /** The grammar the v2 contract built. The report itself does not carry one. */
    reportGrammarId?: string | null;
    viewportBuilding?: MappingSubject | null;
  },
) {
  // Every figure below is counted on the v2 massing contract, which is typed to a
  // library in the International Style. The viewport draws the v3 selection, which
  // follows the score. Reading "traceable elements 471/514" as a statement about the
  // building on screen is the mistake this banner exists to prevent.
  const divergent = viewportBuilding != null
    && (viewportBuilding.typology !== report.typology
      || (reportGrammarId != null
        && canonicalGrammar(viewportBuilding.grammarId)
          !== canonicalGrammar(reportGrammarId)));

  return (
    <section className="mapping-report" aria-labelledby="mapping-report-title">
      <div className="mapping-report-header">
        <div>
          <p className="eyebrow">05 / MAPPING REPORT</p>
          <h2 id="mapping-report-title">What the music became</h2>
          <p className="mapping-report-lede">
            Measured audio becomes a Shared Score proposal. Architectural rules then
            negotiate that proposal into traceable dimensions and elements.
          </p>
          <p className="mapping-subject">
            Counted on the v2 massing contract —{' '}
            <b>{report.typology}</b>, {report.total_element_count} elements,{' '}
            <span className="id">{report.model_id}</span>
          </p>
        </div>
        <button
          className="secondary-action report-download"
          type="button"
          onClick={() => downloadJson('shared_score_mapping_report.json', report)}
        >Download mapping JSON</button>
      </div>

      {divergent && (
        <p className="mapping-divergence">
          The viewport is showing a different building: <b>{viewportBuilding.typology}</b>{' '}
          in {viewportBuilding.grammarId}, {viewportBuilding.elementCount} elements. The
          two chains run side by side and neither derives from the other, so the counts
          below describe the massing contract rather than the model on screen.
        </p>
      )}

      <dl className="mapping-summary">
        <div><dt>Automated dimensions</dt><dd>{report.automated_dimensions.length}</dd></div>
        <div><dt>Actual translations</dt><dd>{report.entries.length}</dd></div>
        <div><dt>Traceable elements</dt><dd>{report.covered_element_count}/{report.total_element_count}</dd></div>
        <div><dt>Coverage</dt><dd>{percent(report.coverage_ratio)}</dd></div>
      </dl>

      <div className="mapping-table" role="table" aria-label="Shared Score mapping report">
        <div className="mapping-row mapping-table-header" role="row">
          <div className="mapping-cell" role="columnheader">Music proposes</div>
          <div className="mapping-cell" role="columnheader">Shared Score</div>
          <div className="mapping-cell" role="columnheader">Architecture negotiates</div>
        </div>
        {report.entries.map((entry) => (
          <div className="mapping-row" role="row" key={entry.id}>
            <div className="mapping-cell" role="cell">
              <p className="mapping-step-label">Music proposes</p>
              <p className="mapping-kicker">{entry.music_feature_label}</p>
              <p className="mapping-music-value">
                {formatMusicValue(entry)} <span>{entry.music_unit}</span>
              </p>
              <p className="mapping-meta">
                {entry.music_method} · normalized {entry.music_normalized.toFixed(2)} · confidence {percent(entry.music_confidence)}
              </p>
            </div>
            <div className="mapping-cell mapping-score-cell" role="cell">
              <p className="mapping-step-label">Shared Score</p>
              <p className="mapping-kicker">{entry.shared_dimension_label}</p>
              <p className="mapping-score-value">{entry.score_value.toFixed(2)}</p>
              <p className="mapping-meta">
                {entry.extraction_method} · confidence {percent(entry.score_confidence)}
              </p>
              <p className="mapping-proposal">{entry.architectural_proposal}</p>
            </div>
            <div className="mapping-cell" role="cell">
              <p className="mapping-step-label">Architecture negotiates</p>
              <p className="mapping-kicker">{entry.architectural_target_label}</p>
              <p className="mapping-outcome">{entry.outcome}</p>
              <RangeBar entry={entry} />
              <p className="mapping-proposal">{entry.negotiation}</p>
              <p className="mapping-meta mapping-rule">
                {entry.rule_id} · {entry.mapping_direction} · {entry.affected_element_ids.length} elements · {entry.affected_programs.join(' / ')}
              </p>
            </div>
          </div>
        ))}
      </div>

      <div className="mapping-limitations">
        <p className="eyebrow">DECLARED LIMITS</p>
        {report.limitations.map((limitation) => <p key={limitation}>{limitation}</p>)}
      </div>
    </section>
  );
}
