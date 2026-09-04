'use client';

/**
 * Every check the run ran, with its clause and its subject.
 *
 * Three rules this page holds to, all of them from the project's own gate rules:
 * a check that could not be evaluated is drawn in its own tone and never as a pass;
 * the code tables behind several of these clauses are placeholders, so the words
 * "compliant", "safe" and "permit ready" appear nowhere; and a failing check is shown
 * with the geometry that failed it rather than summarised away.
 */

import { useEffect, useRef, useState } from 'react';
import { createTimeline, svg as animeSvg } from 'animejs';
import type { GenerationResponse, RampPlan } from '../../lib/types';
import { compact, number, titleCase, toneFor } from '../../lib/format';
import { reducedMotion } from '../../lib/motion';
import { Empty, KeyValue, Panel, Pill, Stat, StatGrid, StatusPill } from '../ui';

function RampDiagram({ plan }: { plan: RampPlan }) {
  const hostRef = useRef<SVGSVGElement>(null);
  const [trace, setTrace] = useState(0);
  const xs = [
    ...plan.runs.flatMap((run) => [run.x_start, run.x_end]),
    ...plan.landings.flatMap((landing) => [landing.x - landing.size_x / 2, landing.x + landing.size_x / 2]),
  ];
  const ys = [
    ...plan.runs.map((run) => run.y),
    ...plan.landings.flatMap((landing) => [landing.y - landing.size_y / 2, landing.y + landing.size_y / 2]),
  ];
  if (xs.length === 0 || ys.length === 0) return null;
  const pad = 2;
  const minX = Math.min(...xs) - pad;
  const maxX = Math.max(...xs) + pad;
  const minY = Math.min(...ys) - pad;
  const maxY = Math.max(...ys) + pad;
  const width = maxX - minX;
  const height = maxY - minY;
  const toX = (x: number) => x - minX;
  const toY = (y: number) => maxY - y;
  const topZ = Math.max(...plan.runs.map((run) => run.z_end), 0) || 1;

  // The centre-line, run by run in walking order — the same line the ADA check
  // measured, so what animates is literally what was verified.
  const centreline = [...plan.runs]
    .sort((a, b) => a.index - b.index)
    .flatMap((run) => [
      toX(run.x_start).toFixed(2) + ',' + toY(run.y).toFixed(2),
      toX(run.x_end).toFixed(2) + ',' + toY(run.y).toFixed(2),
    ])
    .join(' ');

  return (
    <div>
    <svg ref={hostRef} className="diagram" viewBox={'0 0 ' + width.toFixed(2) + ' ' + height.toFixed(2)}
      role="img" aria-label="Accessible route in plan" style={{ maxHeight: 320 }}>
      {plan.runs.map((run) => (
        <g key={'run' + run.index}>
          <rect
            x={Math.min(toX(run.x_start), toX(run.x_end))}
            y={toY(run.y) - plan.width_m / 2}
            width={Math.abs(toX(run.x_end) - toX(run.x_start))}
            height={plan.width_m}
            fill="rgba(0, 85, 255, .13)" stroke="var(--accent)" strokeWidth="0.08"
          />
          <text
            x={Math.min(toX(run.x_start), toX(run.x_end)) + 0.3}
            y={toY(run.y) + 0.3} fontSize="0.7" fill="var(--accent)"
          >
            {'+' + run.z_end.toFixed(2) + ' m'}
          </text>
        </g>
      ))}
      {plan.landings.map((landing) => (
        <rect
          key={'landing' + landing.index}
          x={toX(landing.x) - landing.size_x / 2}
          y={toY(landing.y) - landing.size_y / 2}
          width={landing.size_x} height={landing.size_y}
          fill={landing.kind === 'turn' ? 'rgba(11,158,82,.16)' : 'rgba(11,158,82,.3)'}
          stroke="var(--circulation)" strokeWidth="0.08"
        />
      ))}
      <polyline
        className="ramp-centreline"
        points={centreline}
        fill="none" stroke="var(--accent)" strokeWidth="0.14"
        strokeLinejoin="round" strokeLinecap="round"
      />
      <circle className="ramp-walker" r="0.5" fill="var(--accent)" opacity="0" />
      <text x={0.4} y={height - 0.5} fontSize="0.8" fill="var(--muted)">
        {'rise ' + plan.rise_m.toFixed(2) + ' m to +' + topZ.toFixed(2)
          + ' m · width ' + plan.width_m.toFixed(2) + ' m'}
      </text>
    </svg>
    <RampTrace hostRef={hostRef} trace={trace} onTrace={() => setTrace((value) => value + 1)} />
    </div>
  );
}

/** Draws the checked centre-line and walks a point up it — replayable. */
function RampTrace({
  hostRef, trace, onTrace,
}: {
  hostRef: React.RefObject<SVGSVGElement | null>;
  trace: number;
  onTrace: () => void;
}) {
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const line = host.querySelector<SVGPolylineElement>('.ramp-centreline');
    const walker = host.querySelector<SVGCircleElement>('.ramp-walker');
    if (!line || !walker) return;
    if (reducedMotion()) {
      walker.setAttribute('opacity', '0');
      return;
    }
    const [drawable] = animeSvg.createDrawable(line);
    const path = animeSvg.createMotionPath(line);
    const timeline = createTimeline()
      .add(drawable, { draw: ['0 0', '0 1'], duration: 1400, ease: 'linear' }, 0)
      .add(walker, { opacity: [0, 1], duration: 120, ease: 'linear' }, 0)
      .add(walker, {
        translateX: path.translateX,
        translateY: path.translateY,
        duration: 1400,
        ease: 'linear',
      }, 0)
      .add(walker, { opacity: 0, duration: 260, ease: 'linear' }, 1450);
    return () => { timeline.cancel(); };
  }, [hostRef, trace]);

  return (
    <div style={{ marginTop: 8 }}>
      <button type="button" className="btn btn-sm" onClick={onTrace}>
        Walk the route
      </button>
    </div>
  );
}

export function ComplianceWorkspace({ run }: { run: GenerationResponse | null }) {
  const analysis = run?.analysis ?? null;
  const [findingFilter, setFindingFilter] = useState<'all' | 'pass' | 'fail' | 'unevaluated'>('all');

  if (!run || !analysis) {
    return <Empty title="No checks to show">Compliance reports travel on the schema 3.0 model.</Empty>;
  }

  const life = analysis.life_safety;
  const constitution = analysis.constitution;
  const route = analysis.accessible_route;
  const validation = run.building_model.validation ?? [];
  const findings = (life?.findings ?? []).filter(
    (finding) => findingFilter === 'all' || finding.status === findingFilter);
  const occupants = (life?.nodes ?? []).reduce((sum, node) => sum + node.occupants, 0);
  const foreign = analysis.compliance.foreign_tallies ?? [];

  return (
    <div className="stack">
      <Panel title="Roll-up" sub={analysis.compliance.tallies.length + ' check families'}>
        <StatGrid>
          <Stat label="Passed" value={analysis.compliance.passed_total} tone="ok" />
          <Stat label="Failed" value={analysis.compliance.failed_total}
            tone={analysis.compliance.failed_total ? 'bad' : 'ok'} />
          <Stat label="Not evaluable" value={analysis.compliance.unevaluated_total} tone="unknown"
            foot="missing inputs, or a clause this pipeline cannot run" />
          <Stat label="Occupant load" value={compact(occupants)} foot={life?.occupancy_group ?? '—'} />
          <Stat
            label="Sprinklered"
            value={<Pill tone={life?.sprinklered ? 'ok' : 'unknown'}>{life?.sprinklered ? 'yes' : 'no'}</Pill>}
            foot="assumed on the model, not verified against a system design"
          />
        </StatGrid>
      </Panel>

      <Panel
        title="Every check this run ran"
        sub={(analysis.compliance.passed_total + analysis.compliance.failed_total
          + analysis.compliance.unevaluated_total)
          + ' clauses across ' + analysis.compliance.tallies.length + ' families'}
        flush
        note="A clause the pipeline could not evaluate is counted in its own column. It is not a pass."
      >
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Check family</th>
                <th>Authority</th>
                <th className="right">Passed</th>
                <th className="right">Failed</th>
                <th className="right">Not evaluable</th>
                <th style={{ width: 150 }}>Share</th>
              </tr>
            </thead>
            <tbody>
              {analysis.compliance.tallies.map((tally) => {
                const total = tally.passed + tally.failed + tally.unevaluated || 1;
                return (
                  <tr key={tally.source}>
                    <td><b>{tally.label}</b><div className="id">{tally.source}</div></td>
                    <td className="wrap">{tally.authority}</td>
                    <td className="right">{tally.passed}</td>
                    <td className="right" style={{ color: tally.failed ? 'var(--bad)' : undefined }}>{tally.failed}</td>
                    <td className="right" style={{ color: tally.unevaluated ? 'var(--unknown)' : undefined }}>{tally.unevaluated}</td>
                    <td>
                      <div className="bar-track">
                        <span style={{ width: (tally.passed / total * 100) + '%', background: 'var(--ok)' }} />
                        <span style={{ width: (tally.failed / total * 100) + '%', background: 'var(--bad)' }} />
                        <span style={{ width: (tally.unevaluated / total * 100) + '%', background: 'var(--unknown)' }} />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      {foreign.length > 0 && (
        <Panel
          title="Checks on a different building"
          sub={foreign[0].building ?? 'companion chain'}
          flush
          note="The v2 massing contract is typed to one building; when the score chooses another, its checks are carried here and never summed into the totals above. One building per number."
        >
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Check family</th>
                  <th>Building</th>
                  <th className="right">Passed</th>
                  <th className="right">Failed</th>
                  <th className="right">Not evaluable</th>
                </tr>
              </thead>
              <tbody>
                {foreign.map((tally) => (
                  <tr key={tally.source}>
                    <td><b>{tally.label}</b><div className="id">{tally.source}</div></td>
                    <td className="wrap">{tally.building}</td>
                    <td className="right">{tally.passed}</td>
                    <td className="right">{tally.failed}</td>
                    <td className="right">{tally.unevaluated}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {life && (
        <Panel
          title="Egress and occupancy"
          sub={'IBC Chapter 10 · occupancy ' + life.occupancy_group}
          flush
          actions={
            <div className="segmented">
              {(['all', 'pass', 'fail', 'unevaluated'] as const).map((status) => (
                <button
                  key={status} type="button"
                  className={findingFilter === status ? 'is-active' : ''}
                  onClick={() => setFindingFilter(status)}
                >{status}</button>
              ))}
            </div>
          }
          note="A clause reported unevaluated is one this pipeline could not run against the geometry it has. It is not a clause that passed."
        >
          <div className="table-wrap" style={{ maxHeight: 440 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Clause</th><th>Check</th><th>Status</th><th>Subject</th>
                  <th className="right">Demand</th><th className="right">Capacity</th>
                  <th>Unit</th><th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {findings.map((finding, index) => (
                  <tr key={finding.clause + finding.subject + index}>
                    <td className="id">{finding.clause}</td>
                    <td className="nowrap">{finding.label}</td>
                    <td><StatusPill status={finding.status} /></td>
                    <td className="id">{finding.subject}</td>
                    <td className="right">{finding.demand === null ? '—' : number(finding.demand, 2)}</td>
                    <td className="right">{finding.capacity === null ? '—' : number(finding.capacity, 2)}</td>
                    <td style={{ color: 'var(--muted)' }}>{finding.unit}</td>
                    <td className="wrap">{finding.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {life && (
        <div className="cols-2">
          <Panel title="Egress nodes" sub={life.nodes.length + ' nodes'} flush>
            <div className="table-wrap" style={{ maxHeight: 320 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Node</th><th>Kind</th><th>Level</th>
                    <th className="right">Occupants</th><th className="right">Width mm</th>
                  </tr>
                </thead>
                <tbody>
                  {life.nodes.map((node) => (
                    <tr key={node.id}>
                      <td><b>{node.label}</b><div className="id">{node.id}</div></td>
                      <td>{titleCase(node.kind)}</td>
                      <td className="nowrap">{node.level_id}</td>
                      <td className="right">{node.occupants || '—'}</td>
                      <td className="right">{node.width_mm ? number(node.width_mm, 0) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="Egress paths" sub={life.edges.length + ' edges'} flush>
            <div className="table-wrap" style={{ maxHeight: 320 }}>
              <table className="table">
                <thead>
                  <tr><th>From</th><th>To</th><th className="right">Distance m</th><th>Kind</th></tr>
                </thead>
                <tbody>
                  {life.edges.map((edge, index) => (
                    <tr key={edge.source + edge.target + index}>
                      <td className="id">{edge.source}</td>
                      <td className="id">{edge.target}</td>
                      <td className="right">{number(edge.distance_m, 2)}</td>
                      <td>{edge.kind.replace('_', ' ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}

      {constitution && (
        <Panel
          title="Base-building support"
          sub={'Constitution for ' + constitution.typology + ' · ' + constitution.findings.length + ' requirements'}
          flush
          note="What a building of this type must contain. A missing requirement is a defect in the building, not in the check."
        >
          <div className="table-wrap" style={{ maxHeight: 400 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Requirement</th><th>Necessity</th><th>Status</th>
                  <th>Matched space</th><th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {constitution.findings.map((finding) => (
                  <tr key={finding.requirement_id}>
                    <td><b>{finding.label}</b><div className="id">{finding.requirement_id}</div></td>
                    <td>{titleCase(finding.necessity)}</td>
                    <td><Pill tone={toneFor(finding.status)}>{finding.status}</Pill></td>
                    <td className="id">{finding.matched_space_id ?? '—'}</td>
                    <td className="wrap">{finding.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      <Panel
        title="Accessible route"
        sub="ADA §405"
        note="plan_switchback_ramp returns a compliant plan or nothing. An almost-compliant ramp occupies the place the accessible route belongs and reports the problem as solved, so there is no third outcome."
      >
        {route ? (
          <div className="cols-2">
            <div>
              <RampDiagram plan={route} />
            </div>
            <div>
              <KeyValue rows={[
                ['Rise', number(route.rise_m, 3) + ' m'],
                ['Clear width', number(route.width_m, 3) + ' m'],
                ['Runs', String(route.runs.length)],
                ['Landings', String(route.landings.length)],
                ['Footprint', number(route.footprint_x_m, 2) + ' × ' + number(route.footprint_y_m, 2) + ' m'],
                ['Handrails', route.handrails_required ? 'required' : 'not required'],
              ]} />
              <p className="section-label" style={{ marginTop: 14 }}>Clauses this plan satisfies</p>
              <ul className="list-reasons" style={{ marginTop: 8 }}>
                {route.citations.map((citation) => <li key={citation}>{citation}</li>)}
              </ul>
            </div>
          </div>
        ) : (
          <div>
            <Pill tone="bad">no compliant ramp fits</Pill>
            <p className="prose" style={{ marginTop: 10 }}>
              {analysis.accessible_route_unresolved
                ?? 'No accessible route was resolved and no reason was recorded.'}
            </p>
          </div>
        )}
      </Panel>

      <div className="cols-2">
        <Panel title="Massing validation" sub={validation.length + ' checks on the v2 contract'} flush>
          <div className="table-wrap" style={{ maxHeight: 300 }}>
            <table className="table">
              <thead><tr><th>Check</th><th>Status</th><th>Message</th></tr></thead>
              <tbody>
                {validation.map((check) => (
                  <tr key={check.id}>
                    <td className="id">{check.id}</td>
                    <td><StatusPill status={check.status} /></td>
                    <td className="wrap">{check.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Handoff gates" sub={run.facade_handoff.gates.length + ' gates'} flush>
          <div className="table-wrap" style={{ maxHeight: 300 }}>
            <table className="table">
              <thead><tr><th>Gate</th><th>Status</th><th>Authority</th><th>Message</th></tr></thead>
              <tbody>
                {run.facade_handoff.gates.map((gate) => (
                  <tr key={gate.id}>
                    <td className="id">{gate.id}</td>
                    <td><StatusPill status={gate.status} /></td>
                    <td style={{ color: 'var(--muted)' }}>{gate.authority}</td>
                    <td className="wrap">
                      {gate.message}
                      {gate.blocked_by.length > 0 && (
                        <div className="id" style={{ marginTop: 4 }}>blocked by {gate.blocked_by.join(', ')}</div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      <Panel
        title="Facade grammar gates"
        sub={analysis.facade_gates
          ? analysis.facade_gates.grammar_label + ' · ' + analysis.facade_gates.guide_ref
          : 'no gate report'}
        flush
      >
        {analysis.facade_gates ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Gate</th><th>Invariant</th><th>Verdict</th>
                  <th className="right">Measured</th><th>Required</th><th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {analysis.facade_gates.gates.map((gate) => (
                  <tr key={gate.id}>
                    <td><b>{titleCase(gate.id)}</b></td>
                    <td className="id">{gate.invariant_ref}</td>
                    <td><StatusPill status={gate.verdict} /></td>
                    <td className="right">{gate.measured === null ? '—' : number(gate.measured, 3)}</td>
                    <td className="nowrap">{gate.required}</td>
                    <td className="wrap">{gate.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Empty title="No facade gate report on this run" />}
      </Panel>

      {analysis.compliance.blockers.length > 0 && (
        <Panel title="Open items" sub={analysis.compliance.blockers.length + ' across every family'} flush>
          <ul style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {analysis.compliance.blockers.map((blocker, index) => (
              <li key={index} style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                <Pill tone="unknown">open</Pill>
                <span className="prose" style={{ margin: 0 }}>{blocker}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}
