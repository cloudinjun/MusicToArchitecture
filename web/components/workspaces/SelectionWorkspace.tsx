'use client';

/**
 * How the four decisions were reached, including the ones that were refused.
 *
 * `SelectionRecord` separates what the music asked for from what the screen allowed,
 * and this panel keeps them apart on screen for the same reason: a building that
 * expresses a preference it was denied should never look like one that got its way.
 * The unbuildable systems are shown with their reasons rather than hidden, because
 * "this compiler cannot emit a gridshell" is a fact about the tool, not about the music.
 */

import type { GenerationResponse } from '../../lib/types';
import { number, percent, titleCase } from '../../lib/format';
import { Empty, KeyValue, Meter, Panel, Pill, Stat, StatGrid } from '../ui';

export function SelectionWorkspace({ run }: { run: GenerationResponse | null }) {
  const selection = run?.analysis?.selection ?? null;
  if (!run || !selection) {
    return (
      <Empty title="No selection record">
        The selection record travels on the schema 3.0 model. A run whose v3 compile did
        not complete has none.
      </Empty>
    );
  }

  const unbuildable = Object.entries(selection.unbuildable_systems);
  const chosenPair = selection.ranked_options.findIndex(
    (option) => option.system_id === selection.system_id && option.grammar_id === selection.grammar_id);

  return (
    <div className="stack">
      <Panel title="Outcome" sub={selection.typology + ' · ' + selection.program_id}>
        <StatGrid>
          <Stat label="Massing" value={selection.massing_label} foot={selection.massing_id} />
          <Stat
            label="Structural system"
            value={titleCase(selection.system_id.replace('STR-SYS-', ''))}
            foot={selection.frame_tectonic_id + ' · affinity ' + number(selection.system_affinity)}
          />
          <Stat
            label="Facade grammar"
            value={selection.grammar_id.replace(/^FCD-\d+-/, '').replace(/-/g, ' ')}
            foot={selection.envelope_tectonic_id + ' · affinity ' + number(selection.grammar_affinity)}
          />
          <Stat
            label="Screen"
            value={<Pill tone={selection.overruled_by_screen ? 'warn' : 'ok'}>
              {selection.overruled_by_screen ? 'overruled the score' : 'agreed with the score'}
            </Pill>}
            foot={selection.overrule_reason ?? 'the preferred pair survived the screen'}
          />
          <Stat
            label="Runner-up margin"
            value={selection.runner_up_margin === null ? '—' : number(selection.runner_up_margin)}
            foot={selection.runner_up_grammar_id ?? 'no second grammar was admissible'}
          />
          <Stat
            label="Jurisdiction"
            value={<Pill tone={selection.jurisdiction_resolved ? 'ok' : 'unknown'}>
              {selection.jurisdiction_resolved ? 'resolved' : 'unresolved'}
            </Pill>}
            foot="a code edition nobody has confirmed cannot eliminate a system"
          />
        </StatGrid>
        <p className="prose" style={{ marginTop: 12 }}>{selection.note}</p>
      </Panel>

      <Panel
        title="Axes the music placed"
        sub={selection.axes.length + ' readings'}
        flush
        note="Never the mean of two readings: the average of two mid-range numbers is more mid-range than either, so the axis takes the more decisive one and says which."
      >
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: 110 }}>Axis</th>
                <th style={{ width: 170 }}>Position</th>
                <th style={{ width: 220 }}>From</th>
                <th>Reading</th>
              </tr>
            </thead>
            <tbody>
              {selection.axes.map((axis) => (
                <tr key={axis.axis}>
                  <td><b>{titleCase(axis.axis)}</b></td>
                  <td>
                    <div className="meter-row">
                      <Meter value={axis.value} />
                      <span className="num" style={{ fontSize: 11 }}>{axis.value.toFixed(3)}</span>
                    </div>
                  </td>
                  <td className="id">{axis.sources.join(', ')}</td>
                  <td className="wrap">{axis.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="cols-2">
        <Panel title="Form" sub={selection.massing_id}>
          <ul className="list-reasons">
            {selection.massing_reason.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
          {selection.sizing_fallback && (
            <div style={{ marginTop: 12 }}>
              <p className="section-label">Sizing fallback</p>
              <p className="prose">{selection.sizing_fallback}</p>
            </div>
          )}
          <div style={{ marginTop: 12 }}>
            <KeyValue rows={[
              ['Preferred system', <span key="a" className="mono">{selection.preferred_system_id}</span>],
              ['Built system', <span key="b" className="mono">{selection.system_id}</span>],
              ['Preferred grammar', <span key="c" className="mono">{selection.preferred_grammar_id}</span>],
              ['Built grammar', <span key="d" className="mono">{selection.grammar_id}</span>],
            ]} />
          </div>
        </Panel>

        <Panel title="Survived the screen" sub="hard standards only; soft axes cannot eliminate">
          <p className="section-label">Systems ({selection.admissible_systems.length})</p>
          <div className="chip-row" style={{ margin: '8px 0 14px' }}>
            {selection.admissible_systems.map((system) => (
              <span key={system} className="chip mono">{system}</span>
            ))}
          </div>
          <p className="section-label">Grammars ({selection.admissible_grammars.length})</p>
          <div className="chip-row" style={{ marginTop: 8 }}>
            {selection.admissible_grammars.map((grammar) => (
              <span key={grammar} className="chip mono">{grammar}</span>
            ))}
          </div>
        </Panel>
      </div>

      <Panel
        title="Every admissible pair, in the order the music prefers them"
        sub={selection.ranked_options.length + ' pairs'
          + (chosenPair >= 0 ? ' · built rank ' + (chosenPair + 1) : '')}
        flush
        note="The compiler walks this list when a preferred frame turns out not to be sizeable. A glulam column that cannot carry the load is a correct engineering result, and the fallback is recorded rather than hidden."
      >
        <div className="table-wrap" style={{ maxHeight: 420 }}>
          <table className="table">
            <thead>
              <tr>
                <th className="right" style={{ width: 48 }}>Rank</th>
                <th>System</th><th>Grammar</th>
                <th style={{ width: 190 }}>Affinity</th><th style={{ width: 90 }}>Built</th>
              </tr>
            </thead>
            <tbody>
              {selection.ranked_options.map((option, index) => {
                const isBuilt = option.system_id === selection.system_id
                  && option.grammar_id === selection.grammar_id;
                return (
                  <tr key={option.system_id + option.grammar_id} className={isBuilt ? 'is-selected' : ''}>
                    <td className="right num">{index + 1}</td>
                    <td className="id">{option.system_id}</td>
                    <td className="id">{option.grammar_id}</td>
                    <td>
                      <div className="meter-row">
                        <Meter value={option.affinity} tone={isBuilt ? 'ok' : 'info'} />
                        <span className="num" style={{ fontSize: 11 }}>{option.affinity.toFixed(3)}</span>
                      </div>
                    </td>
                    <td>{isBuilt && <Pill tone="ok">built</Pill>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel
          title="Not emittable by this compiler"
          sub={unbuildable.length + ' systems'}
          flush
          note="A limit of the generator, stated as one. None of these was ruled out by the music."
        >
          <div className="table-wrap" style={{ maxHeight: 340 }}>
            <table className="table">
              <thead><tr><th>System</th><th>Why</th></tr></thead>
              <tbody>
                {unbuildable.map(([system, reason]) => (
                  <tr key={system}>
                    <td className="id">{system}</td>
                    <td className="wrap">{reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
      </Panel>

      <Panel title="Facade grammar gates" sub={run.analysis?.facade_gates?.guide_ref ?? 'no gate report'} flush>
        {run.analysis?.facade_gates ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Gate</th><th>Invariant</th><th>Verdict</th>
                  <th className="right">Measured</th><th>Required</th><th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {run.analysis.facade_gates.gates.map((gate) => (
                  <tr key={gate.id}>
                    <td><b>{titleCase(gate.id)}</b></td>
                    <td className="id">{gate.invariant_ref}</td>
                    <td><Pill tone={gate.verdict === 'passed' ? 'ok' : gate.verdict === 'failed' ? 'bad' : 'unknown'}>{gate.verdict}</Pill></td>
                    <td className="right">{gate.measured === null ? '—' : number(gate.measured, 3)}</td>
                    <td className="nowrap">{gate.required}</td>
                    <td className="wrap">{gate.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Empty title="No facade gate report" />}
      </Panel>

      <Panel
        title="Facade host surfaces"
        sub={run.facade_handoff.host_surfaces.length + ' surfaces · '
          + run.facade_handoff.authority_status
          + ' · on ' + (run.building_model.typology ?? 'the v2 contract')}
        flush
        note={'Deterministic host planes published for every massing face. They are '
          + 'preview hosts: a candidate panel layout is not planned until the handoff '
          + 'gates clear. These faces come from the v2 massing contract, not from the '
          + 'selection above — the two chains run side by side and neither derives from '
          + 'the other, so the planes belong to '
          + (run.building_model.typology ?? 'the v2 building') + ' rather than to '
          + (run.analysis?.typology ?? 'the model in the viewport') + '.'}
      >
        <div className="table-wrap" style={{ maxHeight: 340 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Surface</th><th>Orientation</th><th>Program</th><th>Category</th>
                <th className="right">Width m</th><th className="right">Height m</th>
                <th className="right">Level range</th><th>Origin</th>
              </tr>
            </thead>
            <tbody>
              {run.facade_handoff.host_surfaces.map((surface) => (
                <tr key={surface.id}>
                  <td className="id">{surface.id}</td>
                  <td className="nowrap">{titleCase(surface.orientation)}</td>
                  <td className="nowrap">{titleCase(surface.program_owner)}</td>
                  <td>
                    <span className="chip">
                      <span className={'swatch swatch-' + surface.program_category} aria-hidden="true" />
                      {surface.program_category}
                    </span>
                  </td>
                  <td className="right">{number(surface.width, 2)}</td>
                  <td className="right">{number(surface.height, 2)}</td>
                  <td className="right nowrap">
                    {number(surface.level_min, 1)} – {number(surface.level_max, 1)}
                  </td>
                  <td className="id">
                    {number(surface.origin.x, 1)}, {number(surface.origin.y, 1)}, {number(surface.origin.z, 1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {run.facade_handoff.limitations.length > 0 && (
        <Panel title="What the handoff does not claim" sub={run.facade_handoff.maturity}>
          <ul className="list-reasons">
            {run.facade_handoff.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
          </ul>
        </Panel>
      )}

      <Panel title="Score dimensions available to the facade" sub={run.facade_handoff.maturity} flush>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Dimension</th><th>Status</th><th className="right">Value</th>
                <th className="right">Confidence</th><th>Source</th><th>Required for handoff</th>
              </tr>
            </thead>
            <tbody>
              {run.facade_handoff.score_dimensions.map((slot) => (
                <tr key={slot.id}>
                  <td><b>{titleCase(slot.id)}</b></td>
                  <td><Pill tone={slot.status === 'known' ? 'ok' : 'unknown'}>{slot.status}</Pill></td>
                  <td className="right">{slot.value === null ? '—' : number(slot.value, 3)}</td>
                  <td className="right">{slot.confidence === null ? '—' : percent(slot.confidence)}</td>
                  <td className="id">{slot.source_type}{slot.source_ref ? ' · ' + slot.source_ref : ''}</td>
                  <td>{slot.required_for_handoff ? <Pill tone="info">required</Pill> : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
