'use client';

/**
 * How each family of elements came to be, in the order it was reasoned.
 *
 * Every other panel in this workbench reports what was *recorded* -- a datum, a section,
 * a clause, a status. This one reports how the decision was made, which is what a reader
 * needs in order to disagree with it. The chain is assembled, never authored: each step
 * is read off what the element already carries, so a chain cannot claim a reason the
 * model does not hold.
 *
 * Two honesties are drawn rather than hidden. A chain that never reaches a solid is
 * incomplete, and one that never reaches the recording is not music-driven -- a fire
 * stair is required by code whatever the piece sounds like, and saying so is better than
 * inventing a musical cause for it.
 */

import { useMemo, useState } from 'react';

import { titleCase } from '../../lib/format';
import type { DerivationChain, DerivationStep, GenerationResponse } from '../../lib/types';
import { Empty, Panel, Pill, Stat, StatGrid } from '../ui';

/** The stages a chain moves through, in the order the reasoning runs. */
const STAGE_ORDER = ['feature', 'dimension', 'rule', 'datum', 'point', 'line',
  'surface', 'solid', 'host', 'check'] as const;

/** What it means that a chain *starts* at a given stage. */
const STAGE_BLURB: Record<string, string> = {
  feature: 'begins at the recording',
  dimension: 'begins at a score dimension',
  rule: 'begins at an architectural rule',
  datum: 'begins at a building dimension',
  point: 'begins already located',
  line: 'begins as a run between nodes',
  surface: 'begins as a plane',
  solid: 'begins already solid',
  host: 'begins at what it bears on',
  check: 'begins at a calculation',
};

function stageRank(stage: string): number {
  const index = (STAGE_ORDER as readonly string[]).indexOf(stage);
  return index === -1 ? STAGE_ORDER.length : index;
}

function StepRow({ step, last }: { step: DerivationStep; last: boolean }) {
  return (
    <li className={'drv-step' + (last ? ' is-last' : '')}>
      <span className={'drv-dot stage-' + step.stage} aria-hidden="true" />
      <div className="drv-step-body">
        <p className="drv-step-head">
          <span className="drv-stage">{step.stage}</span>
          <b>{step.label}</b>
          <span className="drv-value mono">{step.value}</span>
        </p>
        <p className="drv-why">{step.why}</p>
        <p className="drv-source">{step.source.replace(/_/g, ' ')}</p>
      </div>
    </li>
  );
}

function Chain({ chain, elementId }: { chain: DerivationChain; elementId?: string }) {
  return (
    <>
      <div className="drv-chain-head">
        <div>
          <h3 className="drv-kind">{titleCase(chain.kind)}</h3>
          <p className="drv-summary">{chain.summary || 'No reason recorded.'}</p>
        </div>
        <div className="chip-row">
          <Pill tone={chain.reaches_audio ? 'ok' : 'unknown'}>
            {chain.reaches_audio ? 'reaches the recording' : 'not music-driven'}
          </Pill>
          <Pill tone={chain.reaches_solid ? 'ok' : 'warn'}>
            {chain.reaches_solid ? 'reaches a solid' : 'never reaches a solid'}
          </Pill>
          <Pill tone={chain.starts_located ? 'ok' : 'warn'}>
            {chain.starts_located ? 'located' : 'unlocated'}
          </Pill>
        </div>
      </div>

      <p className="drv-provenance">
        Assembled from instance <span className="id">{elementId ?? chain.element_id}</span>
        {' on '}<b>{chain.level_id}</b>. The other instances of this family differ in their
        lattice indices and coordinates, not in why they exist.
      </p>
      {chain.rule_refs.length > 0 && (
        <div className="chip-row" style={{ margin: '0 0 12px' }}>
          {chain.rule_refs.map((rule) => (
            <span key={rule} className="chip mono">{rule}</span>
          ))}
        </div>
      )}

      <ol className="drv-steps">
        {chain.steps.map((step, index) => (
          <StepRow
            key={step.stage + '-' + step.label + '-' + index}
            step={step}
            last={index === chain.steps.length - 1}
          />
        ))}
      </ol>
    </>
  );
}

export function DerivationWorkspace({ run }: { run: GenerationResponse | null }) {
  const analysis = run?.analysis ?? null;
  const groups = useMemo(() => analysis?.element_groups ?? [], [analysis]);
  const chains = useMemo(() => analysis?.derivation ?? {}, [analysis]);
  const sampled = analysis?.derivation_element_ids ?? {};

  // Ordered by where the reasoning starts, so the families the music actually drove
  // come first and the ones required by code or convention follow.
  const rows = useMemo(() => groups
    .filter((group) => chains[group.group_id])
    .map((group) => ({ group, chain: chains[group.group_id] }))
    .sort((a, b) => (stageRank(a.chain.steps[0]?.stage ?? '')
      - stageRank(b.chain.steps[0]?.stage ?? ''))
      || a.group.kind.localeCompare(b.group.kind)),
  [groups, chains]);

  const [selected, setSelected] = useState<string | null>(null);
  const [audioOnly, setAudioOnly] = useState(false);

  const visible = audioOnly ? rows.filter((row) => row.chain.reaches_audio) : rows;
  const active = visible.find((row) => row.group.group_id === selected)
    ?? visible[0] ?? null;

  if (!run || rows.length === 0) {
    return (
      <Empty title="No derivation chains">
        Chains are assembled by derivation.py from what the model carries. This run
        carries none, so it either predates the chains being published or produced no
        element groups.
      </Empty>
    );
  }

  const audioBacked = rows.filter((row) => row.chain.reaches_audio).length;
  const incomplete = rows.filter((row) => !row.chain.reaches_solid).length;

  return (
    <div className="stack">
      <Panel
        title="Reasoning"
        sub={rows.length + ' families, one chain each'}
        note="Assembled, never authored: every step is read off what the element already carries - the datums it declared, the lattice it sits on, what it bears on, and the clause that fixed it. One chain per family rather than per element, because the instances of a family differ in their coordinates, not in their reasoning."
      >
        <StatGrid>
          <Stat label="Families with a chain" value={rows.length}
            foot="every element group in the model" />
          <Stat label="Reach the recording" value={audioBacked}
            tone={audioBacked ? 'ok' : 'unknown'}
            foot="the rest are required by code or convention, not by the music" />
          <Stat label="Never reach a solid" value={incomplete}
            tone={incomplete ? 'warn' : 'ok'}
            foot="a chain that stops short is stated, not hidden" />
        </StatGrid>
      </Panel>

      <div className="drv-layout">
        <Panel
          title="Element families"
          sub={visible.length + (audioOnly ? ' driven by the music' : ' in the model')}
          flush
          actions={(
            <button
              type="button"
              className="secondary-action"
              onClick={() => setAudioOnly((value) => !value)}
            >{audioOnly ? 'Show all' : 'Music-driven only'}</button>
          )}
        >
          <div className="drv-list">
            {visible.map(({ group, chain }) => (
              <button
                key={group.group_id}
                type="button"
                className={'drv-item'
                  + (active?.group.group_id === group.group_id ? ' is-active' : '')}
                onClick={() => setSelected(group.group_id)}
              >
                <span className="drv-item-head">
                  <b>{titleCase(group.kind)}</b>
                  <span className="drv-item-count">{group.instance_count}</span>
                </span>
                <span className="drv-item-meta">
                  {group.semantic_layer} · {chain.steps.length} steps
                  {chain.reaches_audio ? ' · music' : ''}
                </span>
              </button>
            ))}
          </div>
        </Panel>

        <Panel
          title="How it was reasoned"
          sub={active ? (STAGE_BLURB[active.chain.steps[0]?.stage ?? ''] ?? 'in order') : ''}
        >
          {active
            ? <Chain chain={active.chain} elementId={sampled[active.group.group_id]} />
            : <Empty title="Nothing selected">Pick a family on the left.</Empty>}
        </Panel>
      </div>
    </div>
  );
}
