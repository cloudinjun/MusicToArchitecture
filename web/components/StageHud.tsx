'use client';

/**
 * One readout on the drawing: what the building is, and where its checks stand.
 *
 * There used to be three corners — identity, levels, verification, quantities — and
 * together with the notes, the feed and the strip they made the stage read as a
 * console. Now the HUD says four things a visitor would ask first (type, form, style,
 * frame) and one line of verdicts. The levels moved into the section dock, where
 * cutting happens; the quantities are in Layers; the verdicts open in Compliance.
 * Every value is still from the run; nothing here is decoration.
 */

import type { GenerationResponse } from '../lib/types';
import { titleCase } from '../lib/format';

function human(id: string | null | undefined, strip?: RegExp): string {
  if (!id) return '—';
  return titleCase((strip ? id.replace(strip, '') : id).toLowerCase());
}

export function StageHud({
  run, assembling, layersOpen, onOpenCompliance,
}: {
  run: GenerationResponse;
  assembling: string | null;
  layersOpen: boolean;
  onOpenCompliance?: () => void;
}) {
  const analysis = run.analysis ?? null;
  const compliance = analysis?.compliance ?? null;
  if (layersOpen) return null;

  return (
    <div className="hud" aria-hidden={false}>
      <section className="hud-block" data-avoid>
        <h3>{titleCase(analysis?.typology ?? run.architectural_score.typology)}</h3>
        <div className="hud-row"><span>Form</span><b>{analysis?.selection?.massing_label ?? '—'}</b></div>
        <div className="hud-row"><span>Style</span><b>{analysis?.facade_gates?.grammar_label ?? human(analysis?.facade_grammar_id, /^FCD-\d+-/)}</b></div>
        <div className="hud-row"><span>Frame</span><b>{human(analysis?.structural_system_id, /^STR-SYS-/)}</b></div>
        {compliance && (
          <button
            type="button" className="hud-status"
            style={{ border: 0, background: 'transparent', padding: 0, paddingTop: 8, width: '100%', cursor: 'pointer', font: 'inherit', color: 'inherit', textAlign: 'left' }}
            title="Every check, in Compliance"
            onClick={onOpenCompliance}
          >
            <span><b className="tone-ok">{compliance.passed_total}</b> passed</span>
            <span><b className={compliance.failed_total ? 'tone-bad' : ''}>{compliance.failed_total}</b> failed</span>
            <span><b className="tone-unknown">{compliance.unevaluated_total}</b> open</span>
          </button>
        )}
        {assembling && (
          <div className="hud-assembly is-processing">assembling · {assembling}</div>
        )}
      </section>
    </div>
  );
}
