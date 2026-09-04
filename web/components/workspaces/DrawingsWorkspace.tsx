'use client';

/**
 * The issued set: plans and sections, cut from the same model the viewport draws.
 *
 * Each sheet is shown with its own audit, because a drawing whose omissions are not
 * stated is a picture. The element account underneath is the part that closes the
 * loop: every element in the model is drawn, dropped by scale, or reached by no cut,
 * and the three buckets are made to sum.
 */

import { useMemo, useState } from 'react';
import type { GenerationResponse } from '../../lib/types';
import { assetUrl } from '../../lib/api';
import { compact, number, percent, titleCase } from '../../lib/format';
import { Empty, Panel, Pill, StackedBar, Stat, StatGrid } from '../ui';

const ZOOMS = [0.5, 0.75, 1, 1.5, 2, 3];

export function DrawingsWorkspace({ run }: { run: GenerationResponse | null }) {
  const sheets = useMemo(() => run?.drawing_sheets ?? [], [run]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);

  // Derived rather than synchronised: the selected sheet is whichever id is still in
  // this run's set, falling back to the first. Opening another run therefore needs no
  // reset, because there is no second copy of the selection to reset.
  const active = sheets.find((sheet) => sheet.id === activeId) ?? sheets[0] ?? null;
  const account = run?.drawing_index?.element_account ?? null;

  if (!run || sheets.length === 0) {
    return (
      <Empty title="No drawing set on this run">
        A set that cannot be produced — a massing whose plate no plane meets, a level
        with nothing on it — leaves the index absent rather than failing the run.
      </Empty>
    );
  }

  return (
    <div className="stack">
      <div className="cols-2" style={{ gridTemplateColumns: 'minmax(240px, 300px) minmax(0, 1fr)' }}>
        <div className="stack">
          <Panel title="Sheets" sub={sheets.length + ' issued'} flush>
            <div className="sheet-list" style={{ padding: 6 }}>
              {sheets.map((sheet) => (
                <button
                  key={sheet.id} type="button"
                  className={'sheet-item' + (sheet.id === activeId ? ' is-active' : '')}
                  onClick={() => setActiveId(sheet.id)}
                >
                  <span>
                    {sheet.title}
                    <span className="id" style={{ display: 'block' }}>{sheet.id} · {sheet.scale}</span>
                  </span>
                  <small>{sheet.marks} marks</small>
                </button>
              ))}
            </div>
          </Panel>

          {active && (
            <Panel title="Sheet audit" sub={active.id} flush>
              <div style={{ padding: 12 }}>
                <StatGrid>
                  <Stat label="Marks" value={compact(active.marks)} />
                  <Stat label="Elements cut" value={compact(active.elements_cut)} />
                  <Stat label="Elements drawn" value={compact(active.elements_drawn)} />
                  <Stat
                    label="Paper"
                    value={active.sheet_mm.length === 2
                      ? number(active.sheet_mm[0], 0) + '×' + number(active.sheet_mm[1], 0)
                      : '—'}
                    unit="MM"
                    foot={'at ' + active.scale}
                  />
                </StatGrid>
                {Object.keys(active.omitted_by_scale).length > 0 && (
                  <div style={{ marginTop: 12 }}>
                    <p className="section-label">Omitted by scale</p>
                    <div className="chip-row" style={{ marginTop: 8 }}>
                      {Object.entries(active.omitted_by_scale).map(([kind, count]) => (
                        <span key={kind} className="chip">
                          {titleCase(kind)}<b className="num">{count}</b>
                        </span>
                      ))}
                    </div>
                    <p className="prose" style={{ marginTop: 10 }}>
                      A plan at this scale carrying every seat is a grey field, not a more
                      informative drawing. These are counted, not lost.
                    </p>
                  </div>
                )}
              </div>
            </Panel>
          )}
        </div>

        <Panel
          title={active ? active.title : 'Sheet'}
          sub={active?.subtitle}
          flush
          actions={
            <>
              <div className="segmented">
                {ZOOMS.map((level) => (
                  <button
                    key={level} type="button"
                    className={zoom === level ? 'is-active' : ''}
                    onClick={() => setZoom(level)}
                  >{Math.round(level * 100)}%</button>
                ))}
              </div>
              {active && (
                <a className="btn btn-sm" href={assetUrl(active.url)} target="_blank" rel="noreferrer">
                  Open SVG
                </a>
              )}
            </>
          }
        >
          <div className="sheet-stage" style={{ height: 620 }}>
            {active ? (
              <div className="sheet-paper" style={{ padding: 0 }}>
                {/* The sheet is an image rather than inlined markup: it is a file the API
                    serves, and an <img> cannot execute anything it contains. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  key={active.id}
                  src={assetUrl(active.url)}
                  alt={active.title}
                  style={{ width: 640 * zoom, maxWidth: 'none', display: 'block' }}
                />
              </div>
            ) : <Empty title="Select a sheet" />}
          </div>
        </Panel>
      </div>

      {account && (
        <Panel
          title="Element account"
          sub={run.drawing_index?.accounted_for ? 'every element accounted for' : 'buckets do not sum'}
          note={run.drawing_index?.limitation}
        >
          <div className="cols-2">
            <StatGrid>
              <Stat label="Drawn" value={compact(account.drawn)} tone="ok"
                foot={percent(account.drawn / (account.total || 1)) + ' of the model'} />
              <Stat label="Omitted by scale" value={compact(account.omitted_by_scale)} tone="unknown"
                foot="the convention working, not a gap" />
              <Stat label="On no cut" value={compact(account.on_no_cut)} tone="unknown"
                foot="would need elevations" />
              <Stat label="Total" value={compact(account.total)}
                foot={run.drawing_index?.accounted_for
                  ? <Pill tone="ok">buckets sum</Pill>
                  : <Pill tone="bad">buckets do not sum</Pill>} />
            </StatGrid>
            <div style={{ alignSelf: 'center' }}>
              <StackedBar parts={[
                { label: 'drawn', value: account.drawn, color: 'var(--ok)' },
                { label: 'omitted by scale', value: account.omitted_by_scale, color: 'var(--unknown)' },
                { label: 'on no cut', value: account.on_no_cut, color: 'var(--warn)' },
              ]} />
            </div>
          </div>
        </Panel>
      )}
    </div>
  );
}
