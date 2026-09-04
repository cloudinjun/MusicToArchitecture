'use client';

/**
 * The panel every report opens in.
 *
 * One drawer, not twelve pages: the building stays on screen behind it, Escape or the
 * scrim closes it, and the wide tables that need room get it from the expand toggle
 * rather than from a permanently wider window. The body is a container-query context,
 * so the two- and three-column layouts inside collapse to one column when the drawer
 * is narrow without any of the panels knowing they are in a drawer.
 */

import { useEffect, type ReactNode } from 'react';

export function Drawer({
  open, title, subtitle, expanded, onToggleExpand, onClose, children,
}: {
  open: boolean;
  title: string;
  subtitle?: string;
  expanded: boolean;
  onToggleExpand: () => void;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <button
        type="button"
        className="scrim"
        aria-label="Close panel"
        onClick={onClose}
      />
      <aside
        className={'drawer' + (expanded ? ' is-expanded' : '')}
        role="dialog"
        aria-modal="false"
        aria-label={title}
      >
        <header className="drawer-head">
          <div style={{ minWidth: 0 }}>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <div className="drawer-actions">
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={onToggleExpand}
              title={expanded ? 'Narrow the panel' : 'Widen the panel'}
            >{expanded ? 'Narrow' : 'Widen'}</button>
            <button type="button" className="icon-btn" aria-label="Close panel" onClick={onClose}>
              ×
            </button>
          </div>
        </header>
        <div className="drawer-body">{children}</div>
      </aside>
    </>
  );
}
