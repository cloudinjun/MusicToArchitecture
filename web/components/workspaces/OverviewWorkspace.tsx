'use client';

/**
 * What this piece of music became.
 *
 * This is the panel a viewer meets first, so it speaks like a person, not like a
 * build log: the renders, one sentence about the building, the four decisions with
 * their reasons, and a plain-language account of the brief and the checks. Machine
 * identifiers, KPI grids and clause tables live in the Evidence and Diagnostics
 * panels — reachable in one click, never the opening image.
 */

import type { GenerationResponse } from '../../lib/types';
import { assetUrl } from '../../lib/api';
import { compact, seconds, titleCase } from '../../lib/format';
import { Disclosure, Empty, Meter, Panel } from '../ui';

/** `STR-SYS-GLULAM-POST-BEAM` → “Glulam post beam”: ids stay in Diagnostics. */
function humanize(id: string | null | undefined, strip?: RegExp): string {
  if (!id) return '';
  const bare = strip ? id.replace(strip, '') : id;
  return titleCase(bare.toLowerCase());
}

function DecisionCard({
  step, label, value, reasons,
}: {
  step: string; label: string; value: string; reasons?: string[];
}) {
  return (
    <div className="panel" style={{ padding: 16 }}>
      <p className="section-label">{step} · {label}</p>
      <p style={{ margin: '6px 0 0', fontSize: 19, fontWeight: 640, letterSpacing: '-.025em' }}>
        {value}
      </p>
      {reasons && reasons.length > 0 && (
        <ul className="list-reasons" style={{ marginTop: 10 }}>
          {reasons.slice(0, 3).map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
      )}
    </div>
  );
}

export function OverviewWorkspace({
  run, onOpenCompliance, onReplay,
}: {
  run: GenerationResponse | null;
  onOpenCompliance?: () => void;
  /** Closes the panel and replays the narrated build on the stage. */
  onReplay?: () => void;
}) {
  if (!run) {
    return (
      <Empty title="No run loaded">
        Open an MP3 to compile a building, or reopen a stored run from the Runs menu.
      </Empty>
    );
  }

  const analysis = run.analysis ?? null;
  const selection = analysis?.selection ?? null;
  const compliance = analysis?.compliance ?? null;
  const allocation = analysis?.program_allocation ?? null;

  const typology = titleCase(analysis?.typology ?? run.architectural_score.typology);
  const massing = selection?.massing_label ?? null;
  const grammar = analysis?.facade_gates?.grammar_label
    ?? humanize(analysis?.facade_grammar_id, /^FCD-\d+-/);
  const structure = humanize(analysis?.structural_system_id, /^STR-SYS-/);
  const storeys = analysis?.lattice.levels.filter((level) => level.kind === 'occupied').length ?? 0;
  const duration = run.audio_features.provenance.duration_seconds;

  const [hero, ...stills] = run.renders;
  const facts = [
    analysis ? compact(analysis.element_count) + ' elements' : null,
    analysis ? Object.keys(analysis.element_counts).length + ' kinds of part' : null,
    storeys ? storeys + ' storeys' : null,
    run.drawing_sheets.length ? run.drawing_sheets.length + ' drawing sheets' : null,
    run.elapsed_seconds ? 'compiled in ' + seconds(run.elapsed_seconds) : null,
  ].filter(Boolean) as string[];

  return (
    <div className="stack">
      {hero && (
        <figure className="render-card">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={assetUrl(hero.url)} alt={titleCase(hero.id.replace(/^\d+_/, ''))} />
        </figure>
      )}

      <p className="prose" style={{ fontSize: 14, lineHeight: 1.6, maxWidth: '62ch' }}>
        From {Math.round(duration)} seconds of{' '}
        <b>{run.audio_features.provenance.filename.replace(/\.mp3$/i, '')}</b>, the score
        proposed a <b>{typology.toLowerCase()}</b>
        {massing ? <> — {massing.toLowerCase()}</> : null}
        {grammar ? <>, dressed in <b>{grammar}</b></> : null}
        {structure ? <>, carried on a {structure.toLowerCase()} frame</> : null}.
        Nothing below was configured by hand: each decision was compiled from the music
        and can be traced back to it.
      </p>

      <div className="cols-2">
        <DecisionCard
          step="01" label="Type"
          value={typology}
          reasons={selection ? [selection.note] : undefined}
        />
        <DecisionCard
          step="02" label="Form"
          value={massing ?? '—'}
          reasons={selection?.massing_reason}
        />
        <DecisionCard
          step="03" label="Style"
          value={grammar || '—'}
          reasons={selection && selection.runner_up_grammar_id ? [
            'Preferred over ' + humanize(selection.runner_up_grammar_id, /^FCD-\d+-/)
            + ' by a clear margin of the score’s own affinity.',
          ] : undefined}
        />
        <DecisionCard
          step="04" label="Structure"
          value={structure || '—'}
          reasons={selection ? [
            selection.admissible_systems.length
            + ' structural systems survived the hard screen; the music chose among them.',
            ...(selection.sizing_fallback ? [selection.sizing_fallback] : []),
          ] : undefined}
        />
      </div>

      {selection?.overruled_by_screen && (
        <Panel title="Where the screen said no">
          <p className="prose">
            The music preferred <b>{humanize(selection.preferred_grammar_id, /^FCD-\d+-/)}</b> on{' '}
            <b>{humanize(selection.preferred_system_id, /^STR-SYS-/)}</b>.{' '}
            {(selection.overrule_reason ?? '').replace(
              /(STR-SYS|FCD-\d+|FRM|ENV)-[A-Z0-9-]+/g,
              (id) => humanize(id, /^(STR-SYS|FCD-\d+|FRM|ENV)-/))}
          </p>
        </Panel>
      )}

      {allocation && (
        <Panel title="The brief">
          <p className="prose">
            The building offers{' '}
            <b>{compact(allocation.delivered_area_m2)} m²</b> of the{' '}
            {compact(allocation.required_area_m2)} m² the brief asks for
            {allocation.unplaced.length > 0
              ? <> — {allocation.unplaced.length} spaces did not fit and are reported
                  rather than shrunk to fit</>
              : <> — every briefed space found a place</>}.
          </p>
          <div style={{ marginTop: 12, maxWidth: 420 }}>
            <Meter
              value={allocation.delivered_area_m2 / (allocation.required_area_m2 || 1)}
              tone={allocation.unplaced.length ? 'warn' : 'ok'}
            />
          </div>
          {allocation.unplaced.length > 0 && (
            <div style={{ margin: '14px -16px -16px' }}>
              <Disclosure summary="What did not fit, and why" count={allocation.unplaced.length}>
                <ul className="list-reasons">
                  {allocation.unplaced.map((space) => (
                    <li key={space.space_id}>
                      <b>{space.label}</b> ({compact(space.area_required_m2)} m²) — {space.reason}
                    </li>
                  ))}
                </ul>
              </Disclosure>
            </div>
          )}
        </Panel>
      )}

      {facts.length > 0 && (
        <div className="chip-row">
          {facts.map((fact) => <span key={fact} className="chip">{fact}</span>)}
        </div>
      )}

      {compliance && (
        <Panel title="Checked, not assumed">
          <p className="prose">
            {compliance.failed_total > 0 ? (
              <><b style={{ color: 'var(--bad)' }}>{compliance.failed_total} checks failed.</b>{' '}
                {compliance.passed_total} passed, and </>
            ) : (
              <>All <b>{compliance.passed_total}</b> evaluable checks passed —
                egress, base-building support, the accessible route, and the facade
                grammar’s own gates. </>
            )}
            {compliance.unevaluated_total > 0 && (
              <><b>{compliance.unevaluated_total}</b> could not be evaluated with the
                information this run has; they are reported as open, never as passes. </>
            )}
            Previews are presentation only — accepted geometry is owned by Rhino, and
            every result remains subject to professional review.
          </p>
          <div className="btn-row" style={{ marginTop: 12 }}>
            {onReplay && (
              <button type="button" className="btn btn-primary" onClick={onReplay}>
                Play the story
              </button>
            )}
            {onOpenCompliance && (
              <button type="button" className="btn" onClick={onOpenCompliance}>
                Review every check
              </button>
            )}
          </div>
        </Panel>
      )}

      {stills.length > 0 && (
        <div className="render-grid">
          {stills.map((render) => (
            <figure key={render.id} className="render-card">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={assetUrl(render.url)} alt={render.id} loading="lazy" />
              <figcaption>{titleCase(render.id.replace(/^\d+_/, ''))}</figcaption>
            </figure>
          ))}
        </div>
      )}

      {(analysis?.limitations.length ?? 0) > 0 && (
        <div className="panel">
          <Disclosure
            summary="What this run does not claim"
            count={analysis!.limitations.length}
          >
            <ul className="list-reasons">
              {analysis!.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
            </ul>
          </Disclosure>
        </div>
      )}
    </div>
  );
}
