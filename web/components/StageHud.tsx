'use client';

/**
 * The corner readouts, in the Craftbot idiom: small technical blocks that live on the
 * drawing itself. Every number is pulled from the run — the HUD is a readout, never a
 * decoration — and every block earns its corner: identity top-left, levels below it,
 * verification top-right, quantities bottom-right. The narrative panels still own the
 * argument; the HUD owns the state of the instrument.
 */

import type { GenerationResponse, GlbManifest, ClippingSettings } from '../lib/types';
import { compact, seconds, titleCase } from '../lib/format';

function human(id: string | null | undefined, strip?: RegExp): string {
  if (!id) return '—';
  return titleCase((strip ? id.replace(strip, '') : id).toLowerCase());
}

export function StageHud({
  run, manifest, layerCounts, clipping, sectionOpen, assembling, layersOpen,
  feedOpen = false, onLevelCut,
}: {
  run: GenerationResponse;
  manifest: GlbManifest | null;
  layerCounts: Array<{ layer: string; elements: number }>;
  clipping: ClippingSettings;
  sectionOpen: boolean;
  assembling: string | null;
  layersOpen: boolean;
  /** The rationale feed owns the right edge while it is speaking. */
  feedOpen?: boolean;
  onLevelCut: (z: number) => void;
}) {
  const analysis = run.analysis ?? null;
  const compliance = analysis?.compliance ?? null;
  const levels = analysis?.lattice.levels ?? [];

  return (
    <div className="hud" aria-hidden={false}>
      {!layersOpen && (
        <div className="hud-col hud-tl">
          <section className="hud-block">
            <h3>Model</h3>
            <div className="hud-row"><span>id</span><b>{analysis?.model_id ?? run.building_model.model_id}</b></div>
            <div className="hud-row"><span>type</span><b>{titleCase(analysis?.typology ?? '—')}</b></div>
            <div className="hud-row"><span>form</span><b>{analysis?.selection?.massing_label ?? '—'}</b></div>
            <div className="hud-row"><span>style</span><b>{analysis?.facade_gates?.grammar_label ?? human(analysis?.facade_grammar_id, /^FCD-\d+-/)}</b></div>
            <div className="hud-row"><span>frame</span><b>{human(analysis?.structural_system_id, /^STR-SYS-/)}</b></div>
            <div className="hud-row"><span>elements</span><b>{compact(analysis?.element_count ?? 0)}</b></div>
            <div className="hud-row"><span>faces</span><b>{compact(manifest?.total_faces ?? 0)}</b></div>
            {assembling && (
              <div className="hud-assembly is-processing">assembling · {assembling}</div>
            )}
          </section>

          {levels.length > 0 && (
            <section className="hud-block">
              <h3>Levels</h3>
              {levels.map((level) => (
                <button
                  key={level.id}
                  type="button"
                  className="hud-level"
                  title={'Cut a plan 1.2 m above ' + level.id}
                  onClick={() => onLevelCut(level.z + 1.2)}
                >
                  <span>{level.id}</span>
                  <i>{level.kind}</i>
                  <b>{'+' + level.z.toFixed(2) + ' m'}</b>
                </button>
              ))}
              <p className="hud-note">click a level to cut its plan</p>
            </section>
          )}
        </div>
      )}

      {!feedOpen && (
      <div className="hud-col hud-tr">
        {compliance && (
          <section className="hud-block">
            <h3>Verification</h3>
            <div className="hud-row"><span>passed</span><b className="tone-ok">{compliance.passed_total}</b></div>
            <div className="hud-row"><span>failed</span><b className={compliance.failed_total ? 'tone-bad' : ''}>{compliance.failed_total}</b></div>
            <div className="hud-row"><span>open</span><b className="tone-unknown">{compliance.unevaluated_total}</b></div>
            {run.translation_report && (
              <div className="hud-row"><span>score-driven</span><b>{Math.round(run.translation_report.variable_coverage * 100)}%</b></div>
            )}
            <p className="hud-note">design preview · pending professional review</p>
          </section>
        )}
      </div>
      )}

      {!feedOpen && (
      <div className="hud-col hud-br">
        <section className="hud-block">
          <h3>Takeoff</h3>
          {layerCounts.map((row) => (
            <div className="hud-row" key={row.layer}>
              <span>{row.layer}</span><b>{compact(row.elements)}</b>
            </div>
          ))}
          <div className="hud-sep" />
          <div className="hud-row">
            <span>section</span>
            <b>{sectionOpen
              ? clipping.axis.toUpperCase() + ' ' + clipping.offset.toFixed(1) + ' m'
              : 'off'}</b>
          </div>
          {run.elapsed_seconds != null && (
            <div className="hud-row"><span>compiled</span><b>{seconds(run.elapsed_seconds)}</b></div>
          )}
        </section>
      </div>
      )}
    </div>
  );
}
