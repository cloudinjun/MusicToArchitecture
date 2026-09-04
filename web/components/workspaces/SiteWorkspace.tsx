'use client';

/**
 * Where the building is proposed to be, and what that place asks of it.
 *
 * Every parameter is a sourced value, never a bare number, because the question a
 * reviewer asks about a basic wind speed is not what it is -- it is who says so. Only
 * `manual` and `verified_lookup` are strong enough to design on; a `code_lookup`
 * nobody has reviewed carries its weakness forward into every load computed from it,
 * and the load cards say so rather than presenting a design value.
 *
 * This is the seam where a person takes over. It is drawn as one.
 */

import type { GenerationResponse, LoadResult, SourcedValue } from '../../lib/types';
import { number, titleCase } from '../../lib/format';
import { Empty, KeyValue, Panel, Pill, Stat, StatGrid } from '../ui';

const STRONG_SOURCES = new Set(['manual', 'verified_lookup']);

function sourceTone(source: string) {
  return STRONG_SOURCES.has(source) ? 'ok' : source === 'llm_proposed' ? 'bad' : 'warn';
}

function LoadCard({ load }: { load: LoadResult }) {
  return (
    <div className="panel" style={{ padding: 12, background: 'var(--surface-2)' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <b style={{ fontSize: 13 }}>{titleCase(load.action)}</b>
        <span className="chip mono">{load.clause}</span>
        <span style={{ marginLeft: 'auto' }}>
          <Pill tone={load.design_ready ? 'ok' : 'unknown'}>
            {load.design_ready ? 'design value' : 'not a design value'}
          </Pill>
        </span>
      </div>
      <p className="num" style={{ margin: '10px 0 0', fontSize: 26, fontWeight: 620, letterSpacing: '-.04em' }}>
        {number(load.value, load.value >= 100 ? 0 : 2)}
        <span style={{ marginLeft: 6, fontSize: 12, color: 'var(--muted)', fontWeight: 600 }}>{load.unit}</span>
      </p>
      <p className="prose" style={{ marginTop: 8 }}>{load.basis}</p>
      {load.inputs.length > 0 && (
        <div className="chip-row" style={{ marginTop: 10 }}>
          {load.inputs.map((input) => <span key={input} className="chip mono">{input}</span>)}
        </div>
      )}
    </div>
  );
}

export function SiteWorkspace({ run }: { run: GenerationResponse | null }) {
  const analysis = run?.analysis ?? null;
  const site = analysis?.site ?? null;
  const loads = analysis?.site_loads ?? null;

  if (!run || !site) {
    return (
      <Empty title="No site resolved">
        Anything that depends on where the building is goes through site.py. This run
        carries no site record.
      </Empty>
    );
  }

  const entries = Object.entries(site).filter(([key]) => key !== 'location') as Array<[string, SourcedValue]>;
  const needingReview = entries.filter(([, value]) => value.needs_review).length;
  const strong = entries.filter(([, value]) => STRONG_SOURCES.has(value.source)).length;

  return (
    <div className="stack">
      <Panel title="Location" sub={site.location.source}>
        <div className="cols-2">
          <KeyValue rows={[
            ['Place', site.location.city + ', ' + site.location.region + ', ' + site.location.country],
            ['Latitude', number(site.location.latitude, 4)],
            ['Longitude', number(site.location.longitude, 4)],
            ['Set by', site.location.set_by ?? '—'],
          ]} />
          <p className="prose">{site.location.rationale}</p>
        </div>
      </Panel>

      <Panel title="Parameters" sub={entries.length + ' sourced values'} flush
        note="A value nobody has reviewed cannot become a design value. Widening the strong-source set to make a report look better is the one change this module exists to prevent.">
        <div style={{ padding: 14, borderBottom: '1px solid var(--line)' }}>
          <StatGrid>
            <Stat label="Strong enough to design on" value={strong} tone={strong ? 'ok' : 'unknown'}
              foot="manual or verified lookup" />
            <Stat label="Needs review" value={needingReview} tone={needingReview ? 'warn' : 'ok'}
              foot="recalled code values, not read from the standard" />
            <Stat label="Adopted code" value={<span style={{ fontSize: 13 }}>{String(site.adopted_building_code.value)}</span>} />
          </StatGrid>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>Parameter</th><th className="right">Value</th><th>Source</th><th>Review</th><th>Basis</th></tr>
            </thead>
            <tbody>
              {entries.map(([key, value]) => (
                <tr key={key}>
                  <td><b>{titleCase(key)}</b><div className="id">{key}</div></td>
                  <td className="right nowrap">
                    {typeof value.value === 'number' ? number(value.value, 2) : String(value.value)}
                  </td>
                  <td><Pill tone={sourceTone(value.source)}>{value.source.replace(/_/g, ' ')}</Pill></td>
                  <td>{value.needs_review ? <Pill tone="warn">needs review</Pill> : <Pill tone="ok">reviewed</Pill>}</td>
                  <td className="wrap">{value.basis}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {loads && (
        <Panel title="Load cases" sub="ASCE 7-16, computed from the parameters above">
          <div className="cols-3">
            <LoadCard load={loads.snow} />
            <LoadCard load={loads.wind} />
            <LoadCard load={loads.seismic} />
          </div>
        </Panel>
      )}
    </div>
  );
}
