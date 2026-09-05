'use client';

/**
 * The issued set: a cover, plans, elevations and sections, cut from the same model
 * the viewport draws and laid out on one paper size.
 *
 * A sheet is what is pinned up; a drawing is a cut. One sheet may carry two sections
 * or three small plans, so the audit is shown per drawing under the sheet it sits on.
 * Each drawing states what it left out, because a drawing whose omissions are not
 * stated is a picture. The element account underneath is the part that closes the
 * loop: every element in the model is drawn, dropped by scale, or reached by no cut,
 * and the three buckets are made to sum.
 */

import { useMemo, useState } from 'react';
import type { DrawingSheetRef, GenerationResponse } from '../../lib/types';
import { assetUrl } from '../../lib/api';
import { compact, number, percent, titleCase } from '../../lib/format';
import { Empty, Panel, Pill, StackedBar, Stat, StatGrid } from '../ui';

/** Width of the sheet relative to the stage: fit, then multiples of it. */
const ZOOMS = [1, 1.5, 2, 3, 4];

const KIND_LABEL: Record<DrawingSheetRef['kind'], string> = {
  cover: 'Cover', plan: 'Plans', elevation: 'Elevations', section: 'Sections',
};
const KIND_ORDER: DrawingSheetRef['kind'][] = ['cover', 'plan', 'elevation', 'section'];

export function DrawingsWorkspace({ run }: { run: GenerationResponse | null }) {
  const sheets = useMemo(() => run?.drawing_sheets ?? [], [run]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);

  // Derived rather than synchronised: the selected sheet is whichever id is still in
  // this run's set, falling back to the first. Opening another run therefore needs no
  // reset, because there is no second copy of the selection to reset.
  const active = sheets.find((sheet) => sheet.id === activeId) ?? sheets[0] ?? null;
  const account = run?.drawing_index?.element_account ?? null;
  const paper = run?.drawing_index?.paper ?? active?.paper ?? '';

  if (!run || sheets.length === 0) {
    return (
      <Empty title="No drawing set on this run">
        A set that cannot be produced — a massing whose plate no plane meets, a level
        with nothing on it — leaves the index absent rather than failing the run.
      </Empty>
    );
  }

  const grouped = KIND_ORDER
    .map((kind) => ({ kind, items: sheets.filter((sheet) => sheet.kind === kind) }))
    .filter((group) => group.items.length > 0);
  const drawingsOnSheet = active?.drawings ?? [];
  const omitted = drawingsOnSheet[0]?.omitted_by_scale ?? active?.omitted_by_scale ?? {};

  return (
    <div className="stack">
      <div className="cols-2" style={{ gridTemplateColumns: 'minmax(240px, 300px) minmax(0, 1fr)' }}>
        <div className="stack">
          <Panel
            title="Sheets"
            sub={sheets.length + ' issued' + (paper ? ' · ' + paper + ' throughout' : '')}
            flush
          >
            <div className="sheet-list" style={{ padding: 6 }}>
              {grouped.map((group) => (
                <div key={group.kind}>
                  <p className="section-label" style={{ padding: '6px 10px 2px' }}>
                    {KIND_LABEL[group.kind]}
                  </p>
                  {group.items.map((sheet) => (
                    <button
                      key={sheet.id} type="button"
                      className={'sheet-item' + (sheet.id === active?.id ? ' is-active' : '')}
                      onClick={() => setActiveId(sheet.id)}
                    >
                      <span>
                        <b className="num" style={{ marginRight: 8 }}>{sheet.sheet_number || sheet.id}</b>
                        {sheet.title}
                        {sheet.drawings.length > 1 && (
                          <span className="id" style={{ display: 'block' }}>
                            {sheet.drawings.map((drawing) => drawing.id).join(' · ')}
                          </span>
                        )}
                      </span>
                      <small>{sheet.kind === 'cover' ? 'index' : compact(sheet.marks) + ' marks'}</small>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </Panel>

          {active && active.kind !== 'cover' && (
            <Panel title="Sheet audit" sub={active.sheet_number || active.id} flush>
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
                    foot={(active.paper ? active.paper + ' at ' : 'at ') + active.scale}
                  />
                </StatGrid>
                {drawingsOnSheet.length > 0 && (
                  <div style={{ marginTop: 12 }}>
                    <p className="section-label">On this sheet</p>
                    <table className="table" style={{ marginTop: 6 }}>
                      <tbody>
                        {drawingsOnSheet.map((drawing) => (
                          <tr key={drawing.id}>
                            <td>
                              {drawing.title}
                              <span className="id" style={{ display: 'block' }}>{drawing.id}</span>
                            </td>
                            <td className="num" style={{ textAlign: 'right' }}>{compact(drawing.marks)}</td>
                            <td className="num" style={{ textAlign: 'right' }}>{compact(drawing.elements_cut)} cut</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {Object.keys(omitted).length > 0 && (
                  <div style={{ marginTop: 12 }}>
                    <p className="section-label">Omitted by scale</p>
                    <div className="chip-row" style={{ marginTop: 8 }}>
                      {Object.entries(omitted).map(([kind, count]) => (
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
          title={active ? (active.sheet_number ? active.sheet_number + ' · ' : '') + active.title : 'Sheet'}
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
                  >{level === 1 ? 'Fit' : Math.round(level * 100) + '%'}</button>
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
          <div className="sheet-stage" style={{ height: 680, placeItems: zoom === 1 ? 'center' : 'start' }}>
            {active ? (
              <div className="sheet-paper" style={{ padding: 0, width: zoom * 100 + '%', maxWidth: 'none' }}>
                {/* The sheet is an image rather than inlined markup: it is a file the API
                    serves, and an <img> cannot execute anything it contains. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  key={active.id}
                  src={assetUrl(active.url)}
                  alt={active.title}
                  style={{ width: '100%', maxWidth: 'none', display: 'block' }}
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
                foot="no plane reached it and no face showed it" />
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
