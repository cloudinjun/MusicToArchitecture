'use client';

/**
 * The gravity frame: what was calculated, what was carried at a convention, and
 * which shape somebody could actually order.
 *
 * `sizing_status` is the load-bearing distinction on this page. A member whose
 * section came out of a load calculation carries a utilisation and a governing check;
 * one carried at an architectural convention carries neither and must not be drawn as
 * though it does. The two are separated in the summary and labelled in every row.
 */

import { useMemo, useState } from 'react';
import type { GenerationResponse } from '../../lib/types';
import { compact, number, percent, titleCase } from '../../lib/format';
import { Empty, Meter, Panel, Pill, Stat, StatGrid, StackedBar } from '../ui';

export function StructureWorkspace({ run }: { run: GenerationResponse | null }) {
  const analysis = run?.analysis ?? null;
  const [layerFilter, setLayerFilter] = useState<string>('structure');
  const [query, setQuery] = useState('');

  const groups = useMemo(() => {
    if (!analysis) return [];
    const needle = query.trim().toLowerCase();
    return analysis.element_groups
      .filter((group) => layerFilter === 'all' || group.semantic_layer === layerFilter)
      .filter((group) => !needle
        || group.group_id.toLowerCase().includes(needle)
        || group.kind.toLowerCase().includes(needle)
        || group.subsystem.toLowerCase().includes(needle)
        || (group.section_id ?? '').toLowerCase().includes(needle)
        || group.datum_refs.join(' ').toLowerCase().includes(needle)
        || group.reason.toLowerCase().includes(needle))
      .sort((a, b) => (b.utilisation ?? -1) - (a.utilisation ?? -1) || b.instance_count - a.instance_count);
  }, [analysis, layerFilter, query]);

  if (!run || !analysis) {
    return <Empty title="No structural model">A run compiles its frame from the score; none is loaded.</Empty>;
  }

  const sizedGroups = analysis.element_groups.filter((group) => group.sizing_status === 'sized_by_calculation');
  const conventionGroups = analysis.element_groups.filter((group) => group.sizing_status === 'architectural_convention');
  const worst = analysis.sizing.reduce<number>((max, record) => Math.max(max, record.utilisation), 0);
  const layers = ['all', ...Object.keys(analysis.layer_counts)];

  return (
    <div className="stack">
      <Panel
        title="Frame"
        sub={analysis.structural_system_id
          + (analysis.tectonic_system
            ? ' · ' + titleCase(analysis.tectonic_system.replace(/^FRM-/, '').toLowerCase())
            : '')}
      >
        <StatGrid>
          <Stat label="Member calculations" value={analysis.sizing.length} foot="each with a stated basis" />
          <Stat
            label="Elements sized by calculation"
            value={compact(analysis.sized_element_count)}
            foot={percent(analysis.sized_element_count / (analysis.element_count || 1)) + ' of all elements'}
          />
          <Stat
            label="Highest utilisation"
            value={number(worst, 2)}
            tone={worst > 1 ? 'bad' : worst > 0.9 ? 'warn' : 'ok'}
            foot="demand over capacity at the governing check"
          />
          <Stat label="Sections in use" value={Object.keys(analysis.profiles).length} foot="profiles carried on the model" />
          <Stat label="Groups sized" value={sizedGroups.length} foot={conventionGroups.length + ' carried at a convention'} />
        </StatGrid>
        <div style={{ marginTop: 14 }}>
          <StackedBar parts={[
            { label: 'sized by calculation', value: analysis.sized_element_count, color: 'var(--ok)' },
            { label: 'architectural convention', value: Math.max(0, analysis.element_count - analysis.sized_element_count), color: 'var(--unknown)' },
          ]} />
        </div>
      </Panel>

      <Panel
        title="Member calculations"
        sub={analysis.sizing.length + ' roles'}
        note="A check that was not run is listed on the member rather than in a project note, because a reviewer reads a member calculation."
      >
        {analysis.sizing.length === 0 ? (
          <Empty title="No member calculation on this run" />
        ) : (
          <div className="stack">
            {analysis.sizing.map((record) => (
              <div key={record.role + record.section_id} className="panel" style={{ padding: 12, background: 'var(--surface-2)' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
                  <b style={{ fontSize: 14 }}>{titleCase(record.role)}</b>
                  <span className="chip mono">{record.section_id}</span>
                  <span className="chip">{record.material_id}</span>
                  <span className="chip"><span className="chip-key">governs</span><b>{record.governing_check}</b></span>
                  <span style={{ marginLeft: 'auto', minWidth: 180 }}>
                    <div className="meter-row">
                      <Meter
                        value={record.utilisation}
                        tone={record.utilisation > 1 ? 'bad' : record.utilisation > 0.9 ? 'warn' : 'ok'}
                      />
                      <span className="num" style={{ fontSize: 11 }}>{number(record.utilisation, 3)}</span>
                    </div>
                  </span>
                </div>
                <div className="chip-row" style={{ marginTop: 10 }}>
                  <span className="chip"><span className="chip-key">span</span><b className="num">{number(record.span_m, 2)} m</b></span>
                  <span className="chip"><span className="chip-key">tributary</span><b className="num">{number(record.tributary_width_m, 2)} m</b></span>
                  <span className="chip"><span className="chip-key">load</span><b className="num">{number(record.factored_load_kn_m, 2)} kN/m</b></span>
                  <span className="chip"><span className="chip-key">combination</span><b>{record.load_combination}</b></span>
                  <span className="chip"><span className="chip-key">elements</span><b className="num">{record.element_count}</b></span>
                </div>
                {record.assumptions.length > 0 && (
                  <ul className="list-reasons" style={{ marginTop: 10 }}>
                    {record.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}
                  </ul>
                )}
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel
        title="Element vocabulary"
        sub={Object.keys(analysis.element_counts).length + ' kinds across '
          + Object.keys(analysis.layer_counts).length + ' layers'}
        note="Before type, form, style and structure were compiled from the score rather than fixed, fourteen recordings shared 35 of their 36 element kinds. The vocabulary is evidence that the decisions reach the geometry."
      >
        <div className="chip-row" style={{ marginBottom: 12 }}>
          {Object.entries(analysis.layer_counts).map(([layer, count]) => (
            <span key={layer} className="chip">
              <span className={'swatch swatch-' + layer} aria-hidden="true" />
              {titleCase(layer)}<b className="num">{compact(count)}</b>
            </span>
          ))}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))', gap: '4px 16px' }}>
          {Object.entries(analysis.element_counts)
            .sort((a, b) => b[1] - a[1])
            .map(([kind, count]) => (
              <div key={kind} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 11.5, padding: '3px 0' }}>
                <span style={{ color: 'var(--text-2)' }}>{titleCase(kind)}</span>
                <span className="num" style={{ fontWeight: 600 }}>{compact(count)}</span>
              </div>
            ))}
        </div>
      </Panel>

      {analysis.materials && Object.keys(analysis.materials).length > 0 && (
        <Panel
          title="Materials"
          sub={Object.keys(analysis.materials).length + ' finishes, as the renderer paints them'}
          note="Colour, roughness and metallic values are what the exporter hands Blender; glass is glass because of its transmission, not its tint. Program overlays are diagrams, not built surfaces."
        >
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))', gap: 10 }}>
            {Object.values(analysis.materials).map((material) => (
              <div key={material.id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <span
                  aria-hidden="true"
                  style={{
                    flex: '0 0 auto', width: 34, height: 34, borderRadius: 8,
                    background: material.base_color,
                    opacity: material.transmission > 0.5 ? 0.55 : 1,
                    boxShadow: 'inset 0 0 0 1px rgba(0,0,0,.12)',
                  }}
                />
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>
                    {titleCase(material.id.replace(/_/g, ' '))}
                    <span style={{ color: 'var(--muted)', fontWeight: 500 }}> · {material.family}</span>
                  </div>
                  <div style={{ color: 'var(--muted)', fontSize: 11 }}>
                    {material.finish} · roughness {material.roughness.toFixed(2)}
                    {material.metallic > 0 ? ' · metallic ' + material.metallic.toFixed(2) : ''}
                    {material.transmission > 0 ? ' · transmission ' + material.transmission.toFixed(2) : ''}
                  </div>
                  <div className="prose" style={{ fontSize: 11, marginTop: 2 }}>{material.reason}</div>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Panel title="Sections carried on the model" sub={Object.keys(analysis.profiles).length + ' profiles'} flush>
        <div className="table-wrap" style={{ maxHeight: 340 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Profile</th><th>Shape</th>
                <th className="right">Depth</th><th className="right">Width</th>
                <th className="right">Web</th><th className="right">Flange</th><th>Source</th>
              </tr>
            </thead>
            <tbody>
              {Object.values(analysis.profiles).map((profile) => (
                <tr key={profile.id}>
                  <td className="id">{profile.id}</td>
                  <td>{profile.shape.toUpperCase()}</td>
                  <td className="right">{number(profile.depth_m, 3)}</td>
                  <td className="right">{number(profile.width_m, 3)}</td>
                  <td className="right">{profile.web_m ? number(profile.web_m, 3) : '—'}</td>
                  <td className="right">{profile.flange_m ? number(profile.flange_m, 3) : '—'}</td>
                  <td>
                    <Pill tone={profile.source === 'catalogue' ? 'ok' : 'unknown'}>{profile.source}</Pill>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel
        title="Element groups"
        sub={groups.length + ' of ' + analysis.element_groups.length}
        flush
        actions={
          <>
            <input
              className="btn btn-sm"
              style={{ minWidth: 210, textAlign: 'left', fontWeight: 400 }}
              placeholder="Filter by id, kind, section, datum or reason"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <div className="segmented">
              {layers.map((layer) => (
                <button
                  key={layer} type="button"
                  className={layerFilter === layer ? 'is-active' : ''}
                  onClick={() => setLayerFilter(layer)}
                >{layer}</button>
              ))}
            </div>
          </>
        }
      >
        <div className="table-wrap" style={{ maxHeight: 520 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Group</th><th>Kind</th><th>Subsystem</th>
                <th className="right">Count</th><th>Section</th><th>Datums</th>
                <th>Sizing</th><th style={{ width: 140 }}>Utilisation</th><th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((group) => (
                <tr key={group.group_id}>
                  <td className="id">{group.group_id}</td>
                  <td className="nowrap">{titleCase(group.kind)}</td>
                  <td className="nowrap" style={{ color: 'var(--muted)' }}>{group.subsystem}</td>
                  <td className="right">{group.instance_count}</td>
                  <td className="id">{group.section_id ?? '—'}</td>
                  <td className="id">{group.datum_refs.join(', ') || '—'}</td>
                  <td>
                    <Pill tone={group.sizing_status === 'sized_by_calculation' ? 'ok' : 'unknown'}>
                      {group.sizing_status === 'sized_by_calculation' ? 'calculated' : 'convention'}
                    </Pill>
                  </td>
                  <td>
                    {group.utilisation === null ? <span style={{ color: 'var(--muted)' }}>—</span> : (
                      <div className="meter-row">
                        <Meter
                          value={group.utilisation}
                          tone={group.utilisation > 1 ? 'bad' : group.utilisation > 0.9 ? 'warn' : 'ok'}
                        />
                        <span className="num" style={{ fontSize: 11 }}>{number(group.utilisation, 2)}</span>
                      </div>
                    )}
                  </td>
                  <td className="wrap">{group.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
