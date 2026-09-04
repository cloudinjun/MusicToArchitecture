'use client';

/** Run-specific evidence for the proposed Revit/Dynamo handoff. */

import type { BimDeliveryStrategy, GenerationResponse } from '../../lib/types';
import { compact, percent, shortHash, titleCase } from '../../lib/format';
import {
  Empty, Notice, Panel, Pill, StackedBar, Stat, StatGrid, StatusPill,
} from '../ui';

const STRATEGY_TONE: Record<BimDeliveryStrategy, 'info' | 'ok' | 'unknown'> = {
  native_candidate: 'info',
  room_candidate: 'ok',
  direct_shape_preview: 'unknown',
  omit_presentation_only: 'unknown',
};

const STRATEGY_COLOR: Record<BimDeliveryStrategy, string> = {
  native_candidate: 'var(--accent)',
  room_candidate: 'var(--ok)',
  direct_shape_preview: 'var(--unknown)',
  omit_presentation_only: 'var(--line-strong)',
};

export function BimHandoffWorkspace({ run }: { run: GenerationResponse | null }) {
  const report = run?.analysis?.bim_handoff;
  if (!report) {
    return (
      <Empty title="No BIM handoff report">
        Regenerate the run to join its schema 3.0 elements to the Revit/Dynamo mapping contract.
      </Empty>
    );
  }

  const receiving = report.receiving;
  const materials = report.material_bindings ?? [];
  const reviewQueue = report.review_queue ?? [];

  const strategyParts = report.strategy_summaries.map((summary) => ({
    label: summary.label,
    value: summary.element_count,
    color: STRATEGY_COLOR[summary.strategy],
  }));

  return (
    <div className="stack bim-workspace">
      <Panel
        title="Handoff route"
        sub={`${report.source_model_id} · ${shortHash(report.source_model_sha256, 12)}`}
        actions={<StatusPill status={report.handoff_readiness === 'blocked' ? 'blocked' : 'preview_ready'} label={titleCase(report.handoff_readiness)} />}
        note="Ready for dry-run certifies the portable mapping package only. Revit/Dynamo runtime behavior remains a separate pending gate."
      >
        <div className="bim-route" aria-label="Schema 3 model through the mapping registry and dry-run plan to Revit and Dynamo">
          <div className="bim-route-step">
            <span>Source</span><strong>Schema 3.0</strong>
            <small>{compact(report.emitted_element_count)} elements</small>
          </div>
          <span className="bim-route-arrow" aria-hidden="true">→</span>
          <div className="bim-route-step">
            <span>Registry</span><strong>{report.mapped_taxonomy_kind_count}/{report.taxonomy_kind_count} kinds</strong>
            <small>{report.mapping_rule_count} mapping rules</small>
          </div>
          <span className="bim-route-arrow" aria-hidden="true">→</span>
          <div className="bim-route-step">
            <span>Sync plan</span><strong>Dry-run first</strong>
            <small>stable IDs · conflicts · retire</small>
          </div>
          <span className="bim-route-arrow" aria-hidden="true">→</span>
          <div className="bim-route-step is-pending">
            <span>Target</span><strong>{report.target_host}</strong>
            <small>{report.orchestrator} · live proof pending</small>
          </div>
        </div>
      </Panel>

      {receiving && (
        <Panel
          title="What the receiving team gets"
          sub="the same mapping, in the terms a BIM lead prices the work in"
          note="A DirectShape renders and does not schedule, tag or dimension. Somebody remodels it by hand before the model is worth anything to a project, so the share that arrives native is the number that decides whether this handoff saves time or costs it."
        >
          <StatGrid>
            <Stat
              label="Arrives schedulable"
              value={percent(receiving.schedulable_share)}
              foot={`${compact(receiving.native_element_count + receiving.room_element_count)} of ${compact(receiving.mapped_element_count)} instances`}
              tone={receiving.schedulable_share >= 0.7 ? 'ok' : 'warn'}
            />
            <Stat label="Native candidates" value={compact(receiving.native_element_count)}
              foot="schedule, tag, dimension, join" tone="ok" />
            <Stat label="Rooms" value={compact(receiving.room_element_count)}
              foot="area and department schedules" tone="ok" />
            <Stat label="DirectShape" value={compact(receiving.direct_shape_element_count)}
              foot="remodel by hand before use" tone={receiving.direct_shape_element_count ? 'warn' : 'ok'} />
            <Stat label="Omitted" value={compact(receiving.omitted_element_count)}
              foot="presentation context, deliberately not sent" />
          </StatGrid>
          <div className="bim-receiving-notes">
            <p>{receiving.remodel_note}</p>
            <p>{receiving.takeoff_note}</p>
          </div>
        </Panel>
      )}

      {materials.length > 0 && (
        <Panel
          title="Material takeoff"
          sub={`${materials.length} materials · every instance accounted for`}
          flush
          note="Each element carries MTA_MaterialProfile and MTA_MaterialFamily; the table below is what the host has to create once, not per element. A count in grey sits on DirectShape geometry, where a Revit takeoff cannot reach it."
        >
          <div className="table-wrap" style={{ maxHeight: 420 }}>
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 34 }} aria-label="Colour" />
                  <th>Material</th>
                  <th>Revit class</th>
                  <th className="right">Instances</th>
                  <th className="right">Schedulable</th>
                  <th>Categories</th>
                </tr>
              </thead>
              <tbody>
                {materials.map((material) => (
                  <tr key={material.profile}>
                    <td>
                      <span
                        className="swatch-material"
                        title={`${material.base_color} · roughness ${material.roughness}${material.metallic ? ` · metallic ${material.metallic}` : ''}${material.transmission ? ` · transmission ${material.transmission}` : ''}`}
                        style={{ background: material.base_color }}
                      />
                    </td>
                    <td>
                      <b>{titleCase(material.profile)}</b>
                      <div className="id">{material.family} · {material.finish}</div>
                    </td>
                    <td>{material.revit_class}</td>
                    <td className="right">{compact(material.element_count)}</td>
                    <td
                      className="right"
                      style={{ color: material.schedulable_element_count ? undefined : 'var(--unknown)' }}
                    >{compact(material.schedulable_element_count)}</td>
                    <td className="wrap id">{material.categories.join(', ') || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {reviewQueue.length > 0 && (
        <Panel
          title="Review queue"
          sub="the order to work through before the transaction"
          flush
          note="Ordered by how much of the model sits behind each gate, with the categories needing a native rebuild first. Alphabetical order is how a review misses the 404 elements that matter and catches the one that does not."
        >
          <div className="table-wrap" style={{ maxHeight: 360 }}>
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 28 }} className="right">#</th>
                  <th>Category</th>
                  <th className="right">Instances</th>
                  <th>Arrives as</th>
                  <th>What has to be settled</th>
                </tr>
              </thead>
              <tbody>
                {reviewQueue.map((category, index) => (
                  <tr key={category.revit_category + category.strategy}>
                    <td className="right id">{index + 1}</td>
                    <td>
                      <b>{category.revit_category}</b>
                      <div className="id">{category.built_in_category ?? '—'}</div>
                    </td>
                    <td className="right">{compact(category.element_count)}</td>
                    <td>
                      <Pill tone={STRATEGY_TONE[category.strategy]}>
                        {category.strategy === 'direct_shape_preview' ? 'DirectShape' : titleCase(category.strategy)}
                      </Pill>
                    </td>
                    <td className="wrap">{category.review_gate}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      <Panel title="Run evidence" sub="calculated from this model and the versioned registry" flush>
        <StatGrid>
          <Stat label="Contract coverage" value={percent(report.contract_coverage)}
            foot={`${report.mapped_taxonomy_kind_count}/${report.taxonomy_kind_count} schema kinds`} tone="ok" />
          <Stat label="Run mapping" value={`${report.mapped_emitted_kind_count}/${report.emitted_kind_count}`}
            foot={`${compact(report.mapped_element_count)} emitted elements`} tone="ok" />
          <Stat label="BIM targets" value={compact(report.target_element_count)}
            foot={`${compact(report.omitted_element_count)} presentation-only omitted`} />
          <Stat label="Parameters" value={report.parameter_count}
            foot={`${report.required_parameter_count} required · stable GUIDs`} />
          <Stat label="Dry-run" value={<StatusPill status={report.handoff_readiness === 'blocked' ? 'blocked' : 'preview_ready'} label={report.handoff_readiness === 'blocked' ? 'Blocked' : 'Ready'} />}
            foot="no Revit writes executed" />
          <Stat label="Live validation" value={<StatusPill status={report.live_validation_status} />}
            foot=".dyn/.rvt evidence required" tone="warn" />
        </StatGrid>
      </Panel>

      <div className="cols-2">
        <Panel title="Delivery strategy" sub={`${compact(report.emitted_element_count)} source instances`}>
          <StackedBar parts={strategyParts} />
          <div className="bim-strategy-list">
            {report.strategy_summaries.map((summary) => (
              <div className="bim-strategy-row" key={summary.strategy}>
                <Pill tone={STRATEGY_TONE[summary.strategy]}>{summary.label}</Pill>
                <span className="num">{compact(summary.element_count)} elements</span>
                <small>{summary.emitted_kind_count} emitted kinds · {summary.mapping_rule_count} rules</small>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Evidence gates" sub="status is never inferred from colour alone">
          <div className="bim-check-list">
            {report.evidence_checks.map((check) => (
              <div className="bim-check" key={check.id}>
                <div><strong>{check.label}</strong><span className="id">{check.id}</span></div>
                <StatusPill status={check.status} />
                <p>{check.detail}</p>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Panel title="Category routing" sub="candidate Revit categories · review gates remain binding" flush>
        <div className="table-wrap" style={{ maxHeight: 420 }}>
          <table className="table">
            <thead>
              <tr><th>Revit category</th><th>Strategy</th><th>Kinds</th><th>Elements</th><th>Review gate</th></tr>
            </thead>
            <tbody>
              {report.category_summaries.map((category) => (
                <tr key={`${category.revit_category}-${category.strategy}`}>
                  <td>
                    <strong>{category.revit_category}</strong>
                    <div className="id">{category.built_in_category ?? 'no built-in category'}</div>
                  </td>
                  <td><Pill tone={STRATEGY_TONE[category.strategy]}>{titleCase(category.strategy)}</Pill></td>
                  <td className="right">{category.emitted_kind_count}/{category.taxonomy_kind_count}</td>
                  <td className="right">{compact(category.element_count)}</td>
                  <td className="wrap">{category.review_gate}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="cols-2">
        <Panel title="Stable identity" sub={`${report.identity_parameters.length} handoff fields`} flush>
          <div className="table-wrap" style={{ maxHeight: 360 }}>
            <table className="table">
              <thead><tr><th>Parameter</th><th>GUID</th><th>Purpose</th></tr></thead>
              <tbody>
                {report.identity_parameters.map((parameter) => (
                  <tr key={parameter.guid}>
                    <td className="id">{parameter.name}</td>
                    <td className="id">{parameter.guid}</td>
                    <td className="wrap">{parameter.purpose}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Sync safety" sub="bounded operations before host mutation">
          <div className="chip-row">
            {report.sync_operations.map((operation) => (
              <Pill key={operation} tone={operation === 'review_conflict' || operation === 'review' ? 'warn' : 'info'}>
                {titleCase(operation)}
              </Pill>
            ))}
          </div>
          <ul className="list-reasons" style={{ marginTop: 12 }}>
            {report.safeguards.map((safeguard) => <li key={safeguard}>{safeguard}</li>)}
          </ul>
        </Panel>
      </div>

      <Panel title="Still required in Revit/Dynamo" actions={<StatusPill status="pending" />}>
        <Notice tone="warn">The contract is reviewable today; the installed-host behavior has not been observed.</Notice>
        <ul className="list-reasons" style={{ marginTop: 12 }}>
          {report.live_validation_blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
        </ul>
      </Panel>
    </div>
  );
}
