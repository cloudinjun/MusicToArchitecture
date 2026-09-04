'use client';

import { useState } from 'react';
import { downloadJson } from '../lib/api';
import type {
  DimensionHealth,
  DrivenDatum,
  TranslationGrade,
  TranslationReport,
} from '../lib/types';

const GRADE_LABEL: Record<TranslationGrade, string> = {
  strong: 'Strong',
  working: 'Working',
  constrained: 'Constrained',
  proxy: 'Proxy',
  proxy_clamped: 'Proxy, clamped',
  unsupported: 'Unsupported',
};

const GRADE_ORDER: TranslationGrade[] = [
  'strong', 'working', 'constrained', 'proxy', 'proxy_clamped', 'unsupported',
];

function percent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

function compact(value: number): string {
  if (Math.abs(value) >= 100) return value.toFixed(0);
  if (Math.abs(value) >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

/**
 * The declared range, the band the confidence actually allows, and where the datum
 * landed.
 *
 * This is the one drawing that carries the whole honesty argument: a dimension known at
 * 0.35 confidence gets a narrow band around the midpoint, so the reader can see at a
 * glance that it nudged the design rather than shaped it. A table of numbers hides that;
 * a bar cannot.
 */
function RangeBar({ datum }: { datum: DrivenDatum }) {
  const travel = Math.max(0, Math.min(1, datum.travel));
  const bandStart = (0.5 - travel / 2) * 100;
  const bandWidth = travel * 100;
  const marker = Math.max(0, Math.min(1, datum.applied_position)) * 100;
  return (
    <div className="range-bar" aria-hidden="true">
      <div className="range-track" />
      <div
        className={'range-band' + (datum.clamped ? ' is-clamped' : '')}
        style={{ left: `${bandStart}%`, width: `${bandWidth}%` }}
      />
      <div className="range-marker" style={{ left: `${marker}%` }} />
    </div>
  );
}

function DatumRow({ datum }: { datum: DrivenDatum }) {
  return (
    <div className="datum-row">
      <div className="datum-name">
        <span className="datum-label">{datum.label}</span>
        <code className="datum-id">{datum.id}</code>
      </div>
      <div className="datum-value">
        {compact(datum.value)}
        <span className="datum-unit">{datum.unit === 'fraction' || datum.unit === 'factor' ? '' : ` ${datum.unit}`}</span>
      </div>
      <div className="datum-range">
        <span className="range-end">{compact(datum.range_low)}</span>
        <RangeBar datum={datum} />
        <span className="range-end">{compact(datum.range_high)}</span>
      </div>
      <div className="datum-reach">
        {datum.element_count > 0 ? (
          <>
            <strong>{datum.element_count.toLocaleString()}</strong>
            <span className="datum-kinds">
              {datum.element_kinds.slice(0, 3).join(', ').replace(/_/g, ' ')}
              {datum.element_kinds.length > 3 ? ` +${datum.element_kinds.length - 3}` : ''}
            </span>
          </>
        ) : <span className="datum-kinds">no elements</span>}
      </div>
    </div>
  );
}

function DimensionCard({ dimension }: { dimension: DimensionHealth }) {
  const [open, setOpen] = useState(false);
  const source = dimension.source_features[0];
  return (
    <article className={`dimension-card grade-${dimension.grade}`}>
      <button
        className="dimension-head"
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="dimension-title">
          <span className="dimension-name">{dimension.label}</span>
          <code className="dimension-id">{dimension.id}</code>
        </span>
        <span className="dimension-metrics">
          <span className="dimension-value">
            {dimension.value === null || dimension.value === undefined
              ? '—' : dimension.value.toFixed(3)}
          </span>
          <span className="dimension-travel" title="How much of its declared range this dimension was allowed to cross">
            travel {percent(dimension.travel)}
          </span>
          <span className="dimension-reach" title="Elements positioned or sized by this dimension">
            {dimension.element_count.toLocaleString()} elem
          </span>
          <span className={`grade-pill grade-${dimension.grade}`}>
            {GRADE_LABEL[dimension.grade]}
          </span>
          <span className="dimension-chevron">{open ? '−' : '+'}</span>
        </span>
      </button>

      <div className="dimension-evidence">
        {source ? (
          <>
            <span className="evidence-kind">{dimension.extraction_method}</span>
            <code>{source.id}</code>
            <span>{compact(source.value)} {source.unit}</span>
            <span className="evidence-method">{source.method}</span>
            <span>confidence {percent(dimension.confidence)}</span>
          </>
        ) : <span className="evidence-kind">no supporting metric</span>}
      </div>

      {open && (
        <div className="dimension-body">
          {dimension.proposal && (
            <p className="dimension-proposal">{dimension.proposal}</p>
          )}
          <p className="dimension-note">{dimension.note}</p>
          {dimension.datums.length > 0 ? (
            <div className="datum-table">
              <div className="datum-row datum-head">
                <div className="datum-name">Datum it moves</div>
                <div className="datum-value">Adopted</div>
                <div className="datum-range">Declared range · allowed band · landed</div>
                <div className="datum-reach">Elements</div>
              </div>
              {dimension.datums.map((datum) => (
                <DatumRow key={datum.id} datum={datum} />
              ))}
            </div>
          ) : (
            <p className="dimension-note">
              This dimension moves no datum in the current model.
            </p>
          )}
        </div>
      )}
    </article>
  );
}

export function TranslationHealthReport({ report }: { report: TranslationReport }) {
  const counts = GRADE_ORDER.map((grade) => ({
    grade,
    count: report.dimensions.filter((d) => d.grade === grade).length,
  })).filter((entry) => entry.count > 0);

  return (
    <section className="health-report" aria-labelledby="health-report-title">
      <div className="health-header">
        <div>
          <p className="eyebrow">04 / TRANSLATION HEALTH CHECK</p>
          <h2 id="health-report-title">How this music became this building</h2>
          <p className="health-lede">
            Ten shared dimensions, and what each one actually moved. A dimension can look
            present and be inert, so this reads four things separately: whether it is
            measured or inferred, how much of its declared range the evidence let it
            cross, how many elements it reaches, and what it did in the building&rsquo;s
            own units.
          </p>
        </div>
        <button
          className="secondary-action report-download"
          type="button"
          onClick={() => downloadJson('translation_report.json', report)}
        >Download report JSON</button>
      </div>

      <dl className="health-summary">
        <div>
          <dt>Dimensions emitted</dt>
          <dd>{report.dimensions_emitted}/{report.dimensions_total}</dd>
        </div>
        <div>
          <dt>Datums</dt>
          <dd>{report.datum_count}</dd>
        </div>
        <div>
          <dt>Variable datums driven</dt>
          <dd>{percent(report.variable_coverage)}</dd>
        </div>
        <div>
          <dt>Clamped by confidence</dt>
          <dd>{report.clamped_datum_count}</dd>
        </div>
        <div>
          <dt>Elements</dt>
          <dd>{report.element_count.toLocaleString()}</dd>
        </div>
      </dl>

      <div className="grade-strip" role="img" aria-label="Distribution of dimension grades">
        {counts.map(({ grade, count }) => (
          <span key={grade} className={`grade-chip grade-${grade}`}>
            <span className="grade-dot" />
            {GRADE_LABEL[grade]} <strong>{count}</strong>
          </span>
        ))}
      </div>

      <div className="dimension-list">
        {report.dimensions.map((dimension) => (
          <DimensionCard key={dimension.id} dimension={dimension} />
        ))}
      </div>

      <div className="health-footer">
        <div className="health-constants">
          <p className="health-subhead">Fixed by the tectonic system, never by music</p>
          <ul>
            {report.constants.map((constant) => (
              <li key={constant.id}>
                <span>{constant.label}</span>
                <span className="constant-value">
                  {compact(constant.value)} {constant.unit}
                </span>
              </li>
            ))}
          </ul>
          <p className="health-note">
            Overall coverage is {percent(report.coverage)} because these five are counted
            in it. They are set by the structural system and the code, not by the brief,
            which is why the honest figure is the {percent(report.variable_coverage)} of
            variable datums above.
          </p>
        </div>
        <div className="health-limitations">
          <p className="health-subhead">What this run does not claim</p>
          <ul>
            {report.limitations.map((limitation, index) => (
              <li key={index}>{limitation}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
