'use client';

/**
 * What holds what up, and where the members actually meet.
 *
 * Two separate reports, kept separate on screen because they answer different
 * questions. The dependency graph is a pure function of the element groups: every
 * physical element either names a host or carries an explicit exemption. The axis
 * report reads the centre-line skeleton the emitters registered to, and asks whether
 * members that name each other share a node -- a question proximity kept answering
 * wrongly.
 *
 * `connection_design_status` is displayed prominently for the same reason it exists:
 * a verified topology is not a designed connection, and nothing here should let a
 * reader believe otherwise.
 */

import { useState } from 'react';
import type { GenerationResponse } from '../../lib/types';
import { compact, percent, titleCase, toneFor } from '../../lib/format';
import { Disclosure, Empty, Panel, Pill, Stat, StatGrid, StatusPill } from '../ui';

export function DependencyWorkspace({ run }: { run: GenerationResponse | null }) {
  const analysis = run?.analysis ?? null;
  const graph = analysis?.dependency_graph ?? null;
  const axis = analysis?.axis_report ?? null;
  const [showExemptions, setShowExemptions] = useState(false);

  if (!run || !analysis || (!graph && !axis)) {
    return <Empty title="No dependency report">The typed support graph travels on the schema 3.0 model.</Empty>;
  }

  return (
    <div className="stack">
      <Panel title="Topology" sub={graph ? graph.schema_version : ''}>
        <StatGrid>
          <Stat label="Graph" value={<StatusPill status={graph?.status} />}
            foot="topology only; never connection capacity" />
          <Stat
            label="Connected"
            value={compact(graph?.connected_element_count ?? 0)}
            foot={'of ' + compact(graph?.required_element_count ?? 0) + ' required ('
              + percent((graph?.connected_element_count ?? 0) / (graph?.required_element_count || 1)) + ')'}
            tone={graph && graph.connected_element_count === graph.required_element_count ? 'ok' : 'warn'}
          />
          <Stat label="Gravity paths" value={compact(graph?.gravity_path_count ?? 0)}
            foot="paths that terminate at a declared root" />
          <Stat
            label="Connection design"
            value={<Pill tone="unknown">{(graph?.connection_design_status ?? 'not_checked').replace(/_/g, ' ')}</Pill>}
            foot="no fastener, weld or bearing detail is checked by this pipeline"
          />
          <Stat label="Axis nodes" value={compact(axis?.node_count ?? 0)}
            foot={compact(axis?.segment_count ?? 0) + ' centre-line segments'} />
          <Stat label="Axis check" value={<StatusPill status={axis?.status} />}
            foot="joints by identity, not by proximity" />
        </StatGrid>
      </Panel>

      <div className="cols-2">
        <Panel title="Dependency checks" sub={(graph?.checks.length ?? 0) + ' checks'} flush>
          <div className="table-wrap" style={{ maxHeight: 340 }}>
            <table className="table">
              <thead><tr><th>Check</th><th>Status</th><th>Message</th></tr></thead>
              <tbody>
                {(graph?.checks ?? []).map((check) => (
                  <tr key={check.id}>
                    <td className="id">{check.id}</td>
                    <td><StatusPill status={check.status} /></td>
                    <td className="wrap">
                      {check.message}
                      {check.affected_ids.length > 0 && (
                        <div className="id" style={{ marginTop: 4 }}>
                          {check.affected_ids.length} affected · {check.affected_ids.slice(0, 3).join(', ')}
                          {check.affected_ids.length > 3 ? ' …' : ''}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Axis checks" sub={(axis?.checks.length ?? 0) + ' checks'} flush>
          <div className="table-wrap" style={{ maxHeight: 340 }}>
            <table className="table">
              <thead><tr><th>Check</th><th>Status</th><th>Message</th></tr></thead>
              <tbody>
                {(axis?.checks ?? []).map((check) => (
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
      </div>

      {graph && (
        <Panel
          title="Relation groups"
          sub={graph.relation_groups.length + ' groups · '
            + compact(graph.relation_groups.reduce((sum, group) => sum + group.edges.length, 0)) + ' edges'}
          flush
          note="Shared dependency semantics are stated once for many element-to-host edges. Open a group to see the edges it covers."
        >
          {graph.relation_groups.map((group) => (
            <Disclosure
              key={group.group_id}
              count={group.edges.length}
              summary={
                <span style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                  <b>{group.relation.replace(/_/g, ' ')}</b>
                  <span className="chip">{group.role}</span>
                  <Pill tone={toneFor(group.topology_status)}>{group.topology_status.replace(/_/g, ' ')}</Pill>
                  <Pill tone="unknown">{group.capacity_status.replace(/_/g, ' ')}</Pill>
                  <span style={{
                    color: 'var(--muted)', overflow: 'hidden',
                    textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {group.connection_family}
                  </span>
                </span>
              }
            >
              <p className="prose" style={{ marginBottom: 10 }}>{group.basis}</p>
              <div className="table-wrap" style={{ maxHeight: 260 }}>
                <table className="table">
                  <thead><tr><th>Dependent</th><th>Host</th></tr></thead>
                  <tbody>
                    {group.edges.slice(0, 400).map((edge, index) => (
                      <tr key={edge.dependent_id + index}>
                        <td className="id">{edge.dependent_id}</td>
                        <td className="id">{edge.host_id}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {group.edges.length > 400 && (
                <p className="panel-note" style={{ padding: '8px 0 0' }}>
                  Showing the first 400 of {group.edges.length}. The whole set is in the model JSON.
                </p>
              )}
            </Disclosure>
          ))}
        </Panel>
      )}

      <div className="cols-2">
        {graph && (
          <Panel title="External roots" sub={graph.roots.length + ' roots'} flush
            note="Soil is a declared root rather than a fake building element, so the topology terminates explicitly while its bearing capacity stays visibly unchecked.">
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Root</th><th>Kind</th><th>Topology</th><th>Capacity</th><th>Reason</th></tr></thead>
                <tbody>
                  {graph.roots.map((root) => (
                    <tr key={root.id}>
                      <td className="id">{root.id}</td>
                      <td>{titleCase(root.kind)}</td>
                      <td><Pill tone={toneFor(root.topology_status)}>{root.topology_status}</Pill></td>
                      <td><Pill tone="unknown">{root.capacity_status.replace(/_/g, ' ')}</Pill></td>
                      <td className="wrap">{root.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        )}

        {graph && (
          <Panel
            title="Exemptions"
            sub={graph.exemptions.length + ' elements outside the construction graph'}
            actions={
              <button type="button" className="btn btn-sm" onClick={() => setShowExemptions((value) => !value)}>
                {showExemptions ? 'Collapse' : 'Show all'}
              </button>
            }
            flush
          >
            <div className="table-wrap" style={{ maxHeight: showExemptions ? 420 : 200 }}>
              <table className="table">
                <thead><tr><th>Element</th><th>Reason</th></tr></thead>
                <tbody>
                  {(showExemptions ? graph.exemptions : graph.exemptions.slice(0, 12)).map((exemption) => (
                    <tr key={exemption.element_id}>
                      <td className="id">{exemption.element_id}</td>
                      <td className="wrap">{exemption.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        )}
      </div>
    </div>
  );
}
