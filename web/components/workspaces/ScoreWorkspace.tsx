'use client';

/**
 * The interpretive layer: ten dimensions, the rules they own, and the datums they set.
 *
 * The datum table is the part that was never on screen. Between a score dimension and
 * a mullion spacing sits a datum with a declared range, a rule id, and a clamp derived
 * from the reading's confidence -- and without it the health check's "travel" figure
 * is a number a reader has to take on trust. Here it is the row above.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { animate } from 'animejs';
import type { GenerationResponse } from '../../lib/types';
import { dimensionLabel, number, percent, titleCase } from '../../lib/format';
import { reducedMotion } from '../../lib/motion';
import { Empty, Meter, Panel, Pill, Stat, StatGrid } from '../ui';
import { MappingReport } from '../MappingReport';
import { TranslationHealthReport } from '../TranslationHealthReport';

type Tab = 'dimensions' | 'datums' | 'rules' | 'health' | 'mapping';

const SIGNATURE_SIZE = 196;
const SIGNATURE_R = 76;

/**
 * Ten dimensions, one shape: the piece's signature.
 *
 * The decagon is drawn from the score's own values, and when another run replaces
 * this one the shape tweens between the two — which dimensions moved is visible as
 * geometry, not as two columns of numbers to compare by eye.
 */
function ScoreSignature({ run }: { run: GenerationResponse }) {
  const pathRef = useRef<SVGPolygonElement>(null);
  const dotsRef = useRef<SVGGElement>(null);
  // A keyed object, not an array: anime treats an array target as a list of
  // separate targets, which is exactly not what a ten-value tween wants.
  const state = useRef<Record<string, number> | null>(null);
  const dimensions = run.architectural_score.dimensions;

  const centre = SIGNATURE_SIZE / 2;
  const count = dimensions.length;
  const pointFor = useCallback((index: number, value: number) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / count;
    return [
      centre + Math.cos(angle) * SIGNATURE_R * value,
      centre + Math.sin(angle) * SIGNATURE_R * value,
    ] as const;
  }, [centre, count]);

  useEffect(() => {
    const path = pathRef.current;
    const dots = dotsRef.current;
    if (!path || !dots || dimensions.length === 0) return;
    const targets = Object.fromEntries(
      dimensions.map((dimension, index) => ['d' + index, dimension.value]));

    const draw = (values: Record<string, number>) => {
      const list = dimensions.map((_, index) => values['d' + index] ?? 0);
      path.setAttribute('points', list
        .map((value, index) => pointFor(index, value).join(',')).join(' '));
      [...dots.children].forEach((dot, index) => {
        const [x, y] = pointFor(index, list[index] ?? 0);
        dot.setAttribute('cx', x.toFixed(2));
        dot.setAttribute('cy', y.toFixed(2));
      });
    };

    if (!state.current || reducedMotion()
      || Object.keys(state.current).length !== dimensions.length) {
      state.current = { ...targets };
      draw(targets);
      return;
    }
    const holder = state.current;
    const tween = animate(holder, {
      ...targets,
      duration: 480,
      ease: 'inOut(2)',
      onUpdate: () => draw(holder),
    });
    return () => { tween.cancel(); };
    // The dimension array's identity is stable per run object, so this fires exactly
    // when another run replaces this one.
  }, [dimensions, pointFor]);

  return (
    <figure style={{ margin: 0, textAlign: 'center' }}>
      <svg
        viewBox={'0 0 ' + SIGNATURE_SIZE + ' ' + SIGNATURE_SIZE}
        width={SIGNATURE_SIZE} height={SIGNATURE_SIZE}
        role="img" aria-label="The ten score dimensions as one shape"
      >
        {[0.25, 0.5, 0.75, 1].map((ring) => (
          <polygon
            key={ring}
            points={dimensions.map((_, index) => pointFor(index, ring).join(',')).join(' ')}
            fill="none" stroke="var(--hairline-soft)" strokeWidth="1"
          />
        ))}
        {dimensions.map((_, index) => {
          const [x, y] = pointFor(index, 1);
          return (
            <line
              key={index} x1={centre} y1={centre} x2={x} y2={y}
              stroke="var(--hairline-soft)" strokeWidth="1"
            />
          );
        })}
        <polygon
          ref={pathRef}
          points=""
          fill="var(--accent-soft-2)"
          stroke="var(--accent)" strokeWidth="1.5" strokeLinejoin="round"
        />
        <g ref={dotsRef}>
          {dimensions.map((dimension) => (
            <circle key={dimension.id} r="2.4" fill="var(--accent)">
              <title>
                {dimensionLabel(dimension.id) + ' · ' + dimension.value.toFixed(2)}
              </title>
            </circle>
          ))}
        </g>
      </svg>
      <figcaption style={{ color: 'var(--muted)', fontSize: 10.5, marginTop: 2 }}>
        Ten dimensions, one signature — it reshapes when the music changes.
      </figcaption>
    </figure>
  );
}

const TABS: Array<{ id: Tab; label: string }> = [
  { id: 'dimensions', label: 'Dimensions' },
  { id: 'datums', label: 'Datums' },
  { id: 'rules', label: 'Mapping rules' },
  { id: 'health', label: 'Translation health' },
  { id: 'mapping', label: 'Shared score report' },
];

export function ScoreWorkspace({ run }: { run: GenerationResponse | null }) {
  const [tab, setTab] = useState<Tab>('dimensions');
  if (!run) return <Empty title="No score">A score is compiled from the audio features.</Empty>;

  const score = run.architectural_score;
  const health = run.translation_report ?? null;
  const datums = run.analysis?.datum_set.datums ?? [];
  const scoreDriven = datums.filter((datum) => datum.provenance === 'score_driven').length;

  return (
    <div className="stack">
      <Panel title="Shared score" sub={score.score_id}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center' }}>
        <div style={{ flex: '1 1 340px', minWidth: 0 }}>
        <StatGrid>
          <Stat label="Dimensions emitted" value={score.dimensions.length + '/10'}
            foot={score.dimensions.filter((d) => d.extraction_method === 'observed').length + ' measured directly'} />
          <Stat label="Mapping rules" value={score.mapping_rules.length} foot="each with a declared output range" />
          <Stat label="Datums" value={datums.length}
            foot={scoreDriven + ' score-driven · ' + (datums.length - scoreDriven) + ' fixed'} />
          <Stat label="Variable coverage" value={percent(health?.variable_coverage)}
            foot={'overall ' + percent(health?.coverage ?? run.datum_coverage)} />
          <Stat label="Clamped datums" value={health?.clamped_datum_count ?? 0}
            tone={(health?.clamped_datum_count ?? 0) > 0 ? 'warn' : 'ok'}
            foot="a weak reading nudges rather than decides" />
          <Stat label="Elements reached" value={health?.element_count ?? 0}
            foot={(health?.element_kind_count ?? 0) + ' distinct kinds'} />
        </StatGrid>
        </div>
        <div style={{ flex: '0 0 auto' }}>
          <ScoreSignature run={run} />
        </div>
        </div>
      </Panel>

      <div className="segmented" style={{ alignSelf: 'flex-start' }}>
        {TABS.map((entry) => (
          <button
            key={entry.id} type="button"
            className={tab === entry.id ? 'is-active' : ''}
            onClick={() => setTab(entry.id)}
          >{entry.label}</button>
        ))}
      </div>

      {tab === 'dimensions' && (
        <Panel title="Ten dimensions" sub="six measured, the rest declared proxies" flush
          note="A proxy is declared inferred with its real confidence, never observed. genre_style is a timbral position that proposes a facade weighting for a human to accept; it never selects a grammar.">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Dimension</th><th className="right">Value</th><th style={{ width: 150 }}>Position</th>
                  <th>Evidence</th><th className="right">Confidence</th><th>Source feature</th><th>Proposal</th>
                </tr>
              </thead>
              <tbody>
                {score.dimensions.map((dimension) => (
                  <tr key={dimension.id}>
                    <td><b>{dimensionLabel(dimension.id)}</b><div className="id">{dimension.id}</div></td>
                    <td className="right">{number(dimension.value, 3)}</td>
                    <td><Meter value={dimension.value} /></td>
                    <td>
                      <Pill tone={dimension.extraction_method === 'observed' ? 'ok' : 'warn'}>
                        {dimension.extraction_method}
                      </Pill>
                    </td>
                    <td className="right">{percent(dimension.confidence)}</td>
                    <td className="id">{dimension.source_feature}</td>
                    <td className="wrap">{dimension.architectural_proposal}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {tab === 'datums' && (run.datum_waiting_on?.length ?? 0) > 0 && (
        <Panel title="Datums still waiting on a dimension" sub={(run.datum_waiting_on ?? []).length + ' datums'}>
          <p className="prose" style={{ marginBottom: 10 }}>
            These carry a design fixture because the dimension that would drive them was
            not emitted. They are excluded from mapping coverage rather than counted as
            reached.
          </p>
          <div className="chip-row">
            {(run.datum_waiting_on ?? []).map((datum) => (
              <span key={datum} className="chip mono">{datum}</span>
            ))}
          </div>
        </Panel>
      )}

      {tab === 'datums' && (
        <Panel title="Datums" sub={datums.length + ' values the lattice and the emitters read'} flush
          note="Score bindings live on datums, not on elements: a mullion did not individually negotiate with the music. Travel is confidence / 0.75, capped at 1, so a reading at 0.35 confidence moves less than half its declared range.">
          <div className="table-wrap" style={{ maxHeight: 560 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Datum</th><th className="right">Value</th><th>Unit</th>
                  <th>Provenance</th><th>Driving dimension</th>
                  <th style={{ width: 160 }}>Range and position</th>
                  <th className="right">Travel</th><th>Rule</th><th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {datums.map((datum) => {
                  const range = datum.output_range;
                  const travel = datum.dimension_confidence === null || datum.dimension_confidence === undefined
                    ? null : Math.min(1, datum.dimension_confidence / 0.75);
                  const position = datum.applied_position ?? 0;
                  const band = travel ?? 1;
                  const bandLeft = Math.max(0, 0.5 - band / 2) * 100;
                  return (
                    <tr key={datum.id}>
                      <td className="id">{datum.id}</td>
                      <td className="right">{number(datum.value, 3)}</td>
                      <td style={{ color: 'var(--muted)' }}>{datum.unit}</td>
                      <td>
                        <Pill tone={datum.provenance === 'score_driven' ? 'ok' : 'unknown'}>
                          {datum.provenance.replace(/_/g, ' ')}
                        </Pill>
                      </td>
                      <td>{datum.driving_dimension ? dimensionLabel(datum.driving_dimension) : '—'}</td>
                      <td>
                        {range ? (
                          <div>
                            <div className="range-strip">
                              <i />
                              <b style={{ left: bandLeft + '%', width: (band * 100) + '%' }} />
                              <u style={{ left: (position * 100) + '%' }} />
                            </div>
                            <div className="id" style={{ marginTop: 2 }}>
                              {number(range[0], 2)} … {number(range[1], 2)}
                            </div>
                          </div>
                        ) : <span style={{ color: 'var(--muted)' }}>fixed</span>}
                      </td>
                      <td className="right">{travel === null ? '—' : percent(travel)}</td>
                      <td className="id">{datum.rule_id ?? '—'}</td>
                      <td className="wrap">{datum.reason}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {tab === 'rules' && (
        <Panel title="Mapping rules" sub={score.mapping_rules.length + ' rules'} flush>
          <div className="table-wrap" style={{ maxHeight: 560 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Rule</th><th>Source dimension</th><th>Target parameter</th>
                  <th>Output range</th><th>Direction</th><th className="right">Priority</th><th>Owner</th>
                </tr>
              </thead>
              <tbody>
                {score.mapping_rules.map((rule) => (
                  <tr key={rule.id}>
                    <td className="id">{rule.id}</td>
                    <td>{dimensionLabel(rule.source_dimension)}</td>
                    <td className="id">{rule.target_parameter}</td>
                    <td className="nowrap num">
                      {Array.isArray(rule.output_range)
                        ? number(rule.output_range[0], 2) + ' … ' + number(rule.output_range[1], 2)
                        : '—'}
                    </td>
                    <td>{titleCase(rule.direction)}</td>
                    <td className="right">{rule.priority}</td>
                    <td><Pill tone={rule.owner === 'music' ? 'info' : 'unknown'}>{rule.owner}</Pill></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {tab === 'health' && (
        health
          ? <div className="panel"><TranslationHealthReport report={health} /></div>
          : <Empty title="No translation health report on this run" />
      )}

      {tab === 'mapping' && (
        <div className="panel">
          <MappingReport
            report={run.mapping_report}
            reportGrammarId={typeof run.building_model.facade_profile?.grammar_id === 'string'
              ? run.building_model.facade_profile.grammar_id
              : null}
            viewportBuilding={run.analysis ? {
              typology: run.analysis.typology,
              grammarId: run.analysis.facade_grammar_id,
              elementCount: run.analysis.element_count,
            } : null}
          />
        </div>
      )}
    </div>
  );
}
