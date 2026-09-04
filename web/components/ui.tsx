'use client';

/**
 * The workbench's shared parts.
 *
 * Everything here is deliberately thin: a panel is a bordered box with a header, a
 * pill is a coloured label, a meter is a bar. The reason to have them at all is
 * consistency of *status* -- every place a backend verdict reaches the screen it goes
 * through `StatusPill`, so `unevaluated` can never be drawn as a quiet pass in one
 * panel and as its own thing in another.
 */

import type { ReactNode } from 'react';
import { toneFor, type Tone } from '../lib/format';

export function Panel({
  title, sub, actions, children, flush = false, note, id,
}: {
  title?: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  flush?: boolean;
  note?: ReactNode;
  id?: string;
}) {
  return (
    <section className="panel" id={id}>
      {(title || actions) && (
        <header className="panel-head">
          {title && <h2>{title}</h2>}
          {sub && <span className="panel-sub">{sub}</span>}
          {actions && <div className="panel-head-actions">{actions}</div>}
        </header>
      )}
      <div className={'panel-body' + (flush ? ' is-flush' : '')}>{children}</div>
      {note && <p className="panel-note">{note}</p>}
    </section>
  );
}

export function StatGrid({ children }: { children: ReactNode }) {
  return <dl className="stat-grid">{children}</dl>;
}

export function Stat({
  label, value, unit, foot, tone,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  foot?: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className={'stat' + (tone ? ' tone-' + tone : '')}>
      <dt>{label}</dt>
      <dd>{value}{unit && <small>{unit}</small>}</dd>
      {foot && <p className="stat-foot">{foot}</p>}
    </div>
  );
}

export function Pill({ tone = 'info', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={'pill tone-' + tone}>{children}</span>;
}

/** The single door every backend status walks through on its way to the screen. */
export function StatusPill({ status, label }: { status: string | null | undefined; label?: string }) {
  return <Pill tone={toneFor(status)}>{label ?? (status ?? 'unknown').replace(/_/g, ' ')}</Pill>;
}

export function Chip({ label, value }: { label?: string; value: ReactNode }) {
  return (
    <span className="chip">
      {label && <span className="chip-key">{label}</span>}
      <b>{value}</b>
    </span>
  );
}

export function Meter({ value, tone = 'info' }: { value: number; tone?: Tone }) {
  const clamped = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));
  return (
    <div className={'meter tone-' + tone} role="presentation">
      <span style={{ width: (clamped * 100).toFixed(1) + '%' }} />
    </div>
  );
}

export function MeterRow({ value, label, tone }: { value: number; label: string; tone?: Tone }) {
  return (
    <div className="meter-row">
      <Meter value={value} tone={tone} />
      <span className="num" style={{ fontSize: 11, color: 'var(--text-2)' }}>{label}</span>
    </div>
  );
}

export function KeyValue({ rows }: { rows: Array<[ReactNode, ReactNode]> }) {
  return (
    <dl className="kv">
      {rows.map(([key, value], index) => (
        <div key={index} style={{ display: 'contents' }}>
          <dt>{key}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  );
}

export function Disclosure({
  summary, children, count,
}: { summary: ReactNode; children: ReactNode; count?: number }) {
  return (
    <details className="disclosure">
      <summary>
        {summary}
        {count !== undefined && <span className="rail-count">{count}</span>}
      </summary>
      <div className="disclosure-body">{children}</div>
    </details>
  );
}

export function ToggleRow({
  on, label, count, swatch, onToggle,
}: {
  on: boolean;
  label: string;
  count?: ReactNode;
  swatch?: string;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      className={'toggle-row' + (on ? '' : ' is-off')}
      aria-pressed={on}
      onClick={onToggle}
    >
      <span className="toggle-box" aria-hidden="true" />
      {swatch && <span className={'swatch swatch-' + swatch} aria-hidden="true" />}
      <span className="toggle-name">{label}</span>
      {count !== undefined && <span className="toggle-count num">{count}</span>}
    </button>
  );
}

/** A proportional bar broken into named parts, for accounts that must sum. */
export function StackedBar({
  parts,
}: { parts: Array<{ label: string; value: number; color: string }> }) {
  const total = parts.reduce((sum, part) => sum + part.value, 0) || 1;
  return (
    <div>
      <div className="bar-track">
        {parts.map((part) => (
          <span
            key={part.label}
            title={`${part.label}: ${part.value}`}
            style={{ width: (part.value / total * 100).toFixed(2) + '%', background: part.color }}
          />
        ))}
      </div>
      <div className="chip-row" style={{ marginTop: 8 }}>
        {parts.map((part) => (
          <span key={part.label} className="chip">
            <span className="swatch" style={{ background: part.color }} aria-hidden="true" />
            {part.label}<b className="num">{part.value}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return <p className="section-label">{children}</p>;
}

export function Notice({ tone = 'info', children }: { tone?: Tone; children: ReactNode }) {
  return <p className={'notice tone-' + tone}>{children}</p>;
}
