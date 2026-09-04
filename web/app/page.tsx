'use client';

/**
 * The shell: a building, a title bar, and two menus.
 *
 * Everything the pipeline computes is still reachable — that was the point of the
 * analysis bundle — but none of it is on the glass by default. A run produces forty
 * reports; showing them all at once turned the page into an instrument panel for a
 * thing whose whole argument is a building you can look at. So the model is the
 * screen, the reports open in one panel, and the diagnostics that only matter when
 * something looks wrong sit at the bottom of the menu where they belong.
 */

import { DragEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { GenerationResponse, RunSummary, WorkspaceId } from '../lib/types';
import { apiHealthy, generateArchitecture, listRuns, loadDemoRun, loadRun } from '../lib/api';
import { compact, percent, timestamp, titleCase } from '../lib/format';
import { Drawer } from '../components/Drawer';
import { ModelStage } from '../components/ModelStage';
import type { ViewportMode } from '../components/ArchitectureViewport';
import { OverviewWorkspace } from '../components/workspaces/OverviewWorkspace';
import { AudioWorkspace } from '../components/workspaces/AudioWorkspace';
import { ScoreWorkspace } from '../components/workspaces/ScoreWorkspace';
import { SelectionWorkspace } from '../components/workspaces/SelectionWorkspace';
import { DrawingsWorkspace } from '../components/workspaces/DrawingsWorkspace';
import { StructureWorkspace } from '../components/workspaces/StructureWorkspace';
import { ProgramWorkspace } from '../components/workspaces/ProgramWorkspace';
import { ComplianceWorkspace } from '../components/workspaces/ComplianceWorkspace';
import { BimHandoffWorkspace } from '../components/workspaces/BimHandoffWorkspace';
import { DependencyWorkspace } from '../components/workspaces/DependencyWorkspace';
import { SiteWorkspace } from '../components/workspaces/SiteWorkspace';
import { ArtifactsWorkspace } from '../components/workspaces/ArtifactsWorkspace';

type Status = 'idle' | 'ready' | 'processing' | 'result' | 'error';
type PanelId = Exclude<WorkspaceId, 'model'>;

interface PanelDefinition {
  id: PanelId;
  label: string;
  title: string;
  blurb: string;
  group: 'Run' | 'Music' | 'Building' | 'Evidence' | 'Diagnostics';
}

const PANELS: PanelDefinition[] = [
  {
    id: 'overview', label: 'Overview', group: 'Run', title: 'This building',
    blurb: 'What the music became: the four decisions, their reasons, and what remains open.',
  },
  {
    id: 'audio', label: 'Audio', group: 'Music', title: 'Measured audio',
    blurb: 'Twelve features and six temporal segments, each with its extractor method and confidence.',
  },
  {
    id: 'score', label: 'Shared score', group: 'Music', title: 'Shared score and datums',
    blurb: 'Ten dimensions, the rules they own, the datums they set, and how far the evidence let each one travel.',
  },
  {
    id: 'selection', label: 'Selection', group: 'Music', title: 'Type, form, style, structure',
    blurb: 'What the music asked for, what the screen allowed, and every admissible pair in the order the score prefers them.',
  },
  {
    id: 'drawings', label: 'Drawings', group: 'Building', title: 'Plans and sections',
    blurb: 'Sheets cut from the model, each with the account of what it drew and what it left out.',
  },
  {
    id: 'structure', label: 'Structure', group: 'Building', title: 'Gravity frame',
    blurb: 'Member calculations with their governing check, and every group separated into calculated and conventional.',
  },
  {
    id: 'program', label: 'Program', group: 'Building', title: 'Brief and allocation',
    blurb: 'The brief stated as areas, laid on the lattice level by level, with what could not be placed.',
  },
  {
    id: 'compliance', label: 'Compliance', group: 'Evidence', title: 'Checks and clauses',
    blurb: 'Egress, base-building support, the accessible route, massing validation and the handoff gates.',
  },
  {
    id: 'site', label: 'Site', group: 'Evidence', title: 'Site and loads',
    blurb: 'Where the building is proposed to be, who says so, and the three load cases derived from that.',
  },
  {
    id: 'bim', label: 'BIM handoff', group: 'Evidence', title: 'Revit / Dynamo handoff',
    blurb: 'Stable identity, category strategies, sync safeguards, and the live proof that remains pending.',
  },
  {
    id: 'dependencies', label: 'Dependencies', group: 'Diagnostics', title: 'Support graph and axes',
    blurb: 'What holds what up, where the members meet, and what is exempt from the construction graph.',
  },
  {
    id: 'artifacts', label: 'Artifacts', group: 'Diagnostics', title: 'Artifacts and authority',
    blurb: 'Every file the run produced, who owns it, its hash, and the downloads.',
  },
];

const GROUPS: Array<PanelDefinition['group']> = ['Run', 'Music', 'Building', 'Evidence', 'Diagnostics'];

export default function Workbench() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<Status>('idle');
  const [run, setRun] = useState<GenerationResponse | null>(null);
  const [isDemo, setIsDemo] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [apiUp, setApiUp] = useState<boolean | null>(null);

  const [panel, setPanel] = useState<PanelId | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [menu, setMenu] = useState<'reports' | 'runs' | null>(null);
  const [layersOpen, setLayersOpen] = useState(false);
  const [sectionOpen, setSectionOpen] = useState(false);

  // Blueprint is the default face of the instrument; Studio remains one click away.
  // Storage can be absent or blocked, so both reads are best-effort conveniences.
  const [mode, setMode] = useState<ViewportMode>(() => {
    try { return window.localStorage.getItem('mta.mode') === 'studio' ? 'studio' : 'blueprint'; }
    catch { return 'blueprint'; }
  });
  const [hudOn, setHudOn] = useState<boolean>(() => {
    try { return window.localStorage.getItem('mta.hud') !== 'off'; }
    catch { return true; }
  });
  const [annotateOn, setAnnotateOn] = useState(true);
  const [buildNonce, setBuildNonce] = useState(0);
  useEffect(() => {
    try {
      window.localStorage.setItem('mta.mode', mode);
      window.localStorage.setItem('mta.hud', hudOn ? 'on' : 'off');
    } catch { /* a viewer without storage still gets the session's choices */ }
  }, [mode, hudOn]);

  const refreshRuns = useCallback(async () => { setRuns(await listRuns()); }, []);

  useEffect(() => {
    let cancelled = false;
    loadDemoRun().then((demo) => {
      if (!cancelled && demo) { setRun(demo); setIsDemo(true); }
    });
    apiHealthy().then((healthy) => {
      if (cancelled) return;
      setApiUp(healthy);
      if (healthy) void refreshRuns();
    });
    return () => { cancelled = true; };
  }, [refreshRuns]);

  // One dismissal path for both menus, so a click anywhere else closes whichever is
  // open without every button having to know about the other.
  useEffect(() => {
    if (!menu) return;
    function dismiss() { setMenu(null); }
    window.addEventListener('click', dismiss);
    return () => window.removeEventListener('click', dismiss);
  }, [menu]);

  function selectFile(nextFile?: File | null) {
    if (!nextFile) return;
    if (!nextFile.name.toLowerCase().endsWith('.mp3')) {
      setError('Only MP3 uploads are supported.');
      setStatus('error');
      return;
    }
    setFile(nextFile);
    setError(null);
    setStatus('ready');
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    selectFile(event.dataTransfer.files[0]);
  }

  async function handleGenerate() {
    if (!file) { inputRef.current?.click(); return; }
    setStatus('processing');
    setError(null);
    try {
      const next = await generateArchitecture(file);
      setRun(next);
      setIsDemo(false);
      setStatus('result');
      void refreshRuns();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Generation failed.');
      setStatus('error');
    }
  }

  async function openRun(runId: string) {
    setMenu(null);
    setStatus('processing');
    try {
      const stored = await loadRun(runId);
      setRun(stored);
      setIsDemo(false);
      setStatus('result');
      setError(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'That run could not be reopened.');
      setStatus('error');
    }
  }

  const definition = useMemo(
    () => PANELS.find((entry) => entry.id === panel) ?? null, [panel]);
  const analysis = run?.analysis ?? null;
  const compliance = analysis?.compliance ?? null;
  const attention = (compliance?.failed_total ?? 0) > 0;

  return (
    <div className="shell" data-mode={mode} onDragOver={(event) => event.preventDefault()} onDrop={handleDrop}>
      <header className="topbar">
        <span className="wordmark">Music <em>→</em> Architecture</span>

        <span className="topbar-source" title={run?.audio_features.provenance.filename}>
          {run ? run.audio_features.provenance.filename : 'no run loaded'}
          {isDemo && run && <i>demo</i>}
        </span>

        <div className="topbar-actions">
          <button
            type="button"
            className={'btn btn-sm' + (layersOpen ? ' is-active' : '')}
            aria-pressed={layersOpen}
            onClick={() => setLayersOpen((value) => !value)}
          >Layers</button>
          <button
            type="button"
            className={'btn btn-sm' + (sectionOpen ? ' is-active' : '')}
            aria-pressed={sectionOpen}
            onClick={() => setSectionOpen((value) => !value)}
          >Section</button>
          <button
            type="button"
            className={'btn btn-sm' + (annotateOn ? ' is-active' : '')}
            aria-pressed={annotateOn}
            title="Leader-line annotations compiled from the run"
            onClick={() => setAnnotateOn((value) => !value)}
          >Notes</button>
          <button
            type="button"
            className={'btn btn-sm' + (hudOn ? ' is-active' : '')}
            aria-pressed={hudOn}
            title="Corner readouts: model, levels, verification, takeoff"
            onClick={() => setHudOn((value) => !value)}
          >HUD</button>
          <button
            type="button"
            className="btn btn-sm"
            title="Replay the narrated build: assembly and design rationale together"
            onClick={() => setBuildNonce((value) => value + 1)}
          >Play</button>

          <span className="topbar-divider" />

          <div className="segmented" role="group" aria-label="Viewport mode">
            <button
              type="button"
              className={mode === 'blueprint' ? 'is-active' : ''}
              onClick={() => setMode('blueprint')}
            >Blueprint</button>
            <button
              type="button"
              className={mode === 'studio' ? 'is-active' : ''}
              onClick={() => setMode('studio')}
            >Studio</button>
          </div>

          <span className="topbar-divider" />

          <div className="menu-anchor" onClick={(event) => event.stopPropagation()}>
            <button
              type="button"
              className={'btn btn-sm' + (menu === 'reports' ? ' is-active' : '')}
              aria-expanded={menu === 'reports'}
              onClick={() => setMenu(menu === 'reports' ? null : 'reports')}
            >
              Reports
              {attention && <span className="dot tone-bad" aria-label="a check failed" />}
              <span className="caret" aria-hidden="true">▾</span>
            </button>
            {menu === 'reports' && (
              <div className="menu-panel" role="menu">
                {GROUPS.map((group) => (
                  <div className="menu-group" key={group}>
                    <p className="menu-label">{group}</p>
                    {PANELS.filter((entry) => entry.group === group).map((entry) => (
                      <button
                        key={entry.id}
                        type="button"
                        role="menuitem"
                        className={'menu-item' + (panel === entry.id ? ' is-active' : '')}
                        onClick={() => { setPanel(entry.id); setMenu(null); }}
                      >
                        <span>{entry.label}</span>
                        {entry.id === 'compliance' && compliance && (
                          <em className={compliance.failed_total ? 'tone-bad' : ''}>
                            {compliance.failed_total
                              ? compliance.failed_total + ' failed'
                              : compliance.unevaluated_total + ' open'}
                          </em>
                        )}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="menu-anchor" onClick={(event) => event.stopPropagation()}>
            <button
              type="button"
              className={'btn btn-sm' + (menu === 'runs' ? ' is-active' : '')}
              aria-expanded={menu === 'runs'}
              onClick={() => setMenu(menu === 'runs' ? null : 'runs')}
            >
              Runs
              <span className="caret" aria-hidden="true">▾</span>
            </button>
            {menu === 'runs' && (
              <div className="menu-panel" role="menu">
                <div className="menu-group">
                  <p className="menu-label">
                    Library{apiUp === false && <em className="tone-warn"> · API offline</em>}
                  </p>
                  <button
                    type="button"
                    role="menuitem"
                    className={'menu-item' + (isDemo && run ? ' is-active' : '')}
                    onClick={() => {
                      setMenu(null);
                      void loadDemoRun().then((demo) => {
                        if (demo) { setRun(demo); setIsDemo(true); setError(null); }
                      });
                    }}
                  >
                    <span>Frozen demo run</span>
                    <em>ships with the page</em>
                  </button>
                  {runs.length === 0 ? (
                    <p className="menu-note">
                      {apiUp === false
                        ? 'Start the API to compile and store runs.'
                        : 'No stored runs yet. A generated run is kept here.'}
                    </p>
                  ) : runs.map((summary) => (
                    <button
                      key={summary.run_id}
                      type="button"
                      role="menuitem"
                      className={'menu-item is-run' + (run?.run_id === summary.run_id ? ' is-active' : '')}
                      onClick={() => openRun(summary.run_id)}
                    >
                      <span>
                        {summary.source_filename}
                        <small>
                          {titleCase(summary.typology)} · {compact(summary.element_count)} elements
                          {summary.variable_coverage === null
                            ? '' : ' · ' + percent(summary.variable_coverage) + ' coverage'}
                        </small>
                      </span>
                      <em>{timestamp(summary.generated_at)}</em>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <input
            ref={inputRef}
            className="sr-only"
            type="file"
            accept="audio/mpeg,.mp3"
            onChange={(event) => selectFile(event.target.files?.[0])}
          />
          <button
            type="button"
            className={'btn btn-sm btn-primary' + (status === 'processing' ? ' is-processing' : '')}
            disabled={status === 'processing'}
            onClick={handleGenerate}
            title={file ? 'Compile ' + file.name : 'Choose an MP3 to compile'}
          >
            {status === 'processing' ? 'Compiling…' : file ? 'Generate' : 'Open MP3'}
          </button>
        </div>
      </header>

      <ModelStage
        run={run}
        mode={mode}
        hud={hudOn}
        annotate={annotateOn}
        buildKey={buildNonce}
        requestSection={() => setSectionOpen(true)}
        onOpenPanel={(id) => setPanel(id as PanelId)}
        layersOpen={layersOpen}
        onCloseLayers={() => setLayersOpen(false)}
        sectionOpen={sectionOpen}
      />

      {file && status !== 'processing' && (
        <p className="stage-toast">
          {file.name} ready · press Generate
        </p>
      )}
      {status === 'processing' && (
        <p className="stage-toast is-processing">Analysing audio and authoring in Blender…</p>
      )}
      {error && (
        <p className="stage-toast tone-bad" role="alert">
          {error}
          <button type="button" className="icon-btn" aria-label="Dismiss" onClick={() => setError(null)}>×</button>
        </p>
      )}

      <Drawer
        open={Boolean(definition)}
        title={definition?.title ?? ''}
        subtitle={definition?.blurb}
        expanded={expanded}
        onToggleExpand={() => setExpanded((value) => !value)}
        onClose={() => setPanel(null)}
      >
        {panel === 'overview' && (
          <OverviewWorkspace run={run} onOpenCompliance={() => setPanel('compliance')} />
        )}
        {panel === 'audio' && <AudioWorkspace run={run} />}
        {panel === 'score' && <ScoreWorkspace run={run} />}
        {panel === 'selection' && <SelectionWorkspace run={run} />}
        {panel === 'drawings' && <DrawingsWorkspace run={run} />}
        {panel === 'structure' && <StructureWorkspace run={run} />}
        {panel === 'program' && <ProgramWorkspace run={run} />}
        {panel === 'compliance' && <ComplianceWorkspace run={run} />}
        {panel === 'bim' && <BimHandoffWorkspace run={run} />}
        {panel === 'dependencies' && <DependencyWorkspace run={run} />}
        {panel === 'site' && <SiteWorkspace run={run} />}
        {panel === 'artifacts' && <ArtifactsWorkspace run={run} />}
        {panel && !run && (
          <p className="prose" style={{ padding: 14 }}>
            No run is loaded. Open an MP3, or reopen a stored run from the Runs menu.
          </p>
        )}
      </Drawer>
    </div>
  );
}
