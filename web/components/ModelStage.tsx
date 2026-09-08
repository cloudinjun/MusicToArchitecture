'use client';

/**
 * The building, performing itself.
 *
 * The stage no longer just displays the model: it assembles it in construction order,
 * narrates the stage being built, annotates its own reasoning with leader lines, and
 * keeps technical readouts in the corners. Every callout body is compiled provenance —
 * the group reasons and selection records the pipeline wrote — never authored copy.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  AudioSource, ClippingSettings, GenerationResponse, GlbManifest, SectionAxis, WorkspaceId,
} from '../lib/types';
import { assetUrl, loadGlbManifest } from '../lib/api';
import { linksByLayer } from '../lib/links';
import { clock, compact, dimensionLabel, titleCase } from '../lib/format';
import type { Hearing } from '../lib/hearing';
import type { AnalysisNet } from './HearingCloud';
import {
  ArchitectureViewport, type LatticeLines, type Transfer, type ViewportCallout, type ViewportMode,
} from './ArchitectureViewport';
import { StageHud } from './StageHud';
import { ScoreStrip, type CompileStatus } from './ScoreStrip';
import { buildStory, cleanReason, trimWords } from '../lib/story';
import { Empty, ToggleRow } from './ui';

const SECTION_AXES: SectionAxis[] = ['x', 'y', 'z'];

interface TreeNode {
  layer: string;
  elements: number;
  faces: number;
  children: Array<{ key: string; subsystem: string; category: string; elements: number; faces: number }>;
}

function buildTree(manifest: GlbManifest | null): TreeNode[] {
  if (!manifest) return [];
  const byLayer = new Map<string, TreeNode>();
  Object.values(manifest.objects).forEach((record) => {
    const key = record.layer + '__' + record.subsystem + '__' + record.category;
    const node = byLayer.get(record.layer)
      ?? { layer: record.layer, elements: 0, faces: 0, children: [] };
    node.elements += record.elements;
    node.faces += record.faces;
    node.children.push({
      key,
      subsystem: record.subsystem,
      category: record.category,
      elements: record.elements,
      faces: record.faces,
    });
    byLayer.set(record.layer, node);
  });
  return [...byLayer.values()]
    .map((node) => ({ ...node, children: node.children.sort((a, b) => b.elements - a.elements) }))
    .sort((a, b) => b.elements - a.elements);
}

function human(id: string | null | undefined, strip?: RegExp): string {
  if (!id) return '';
  return titleCase((strip ? id.replace(strip, '') : id).toLowerCase());
}

/**
 * The four decisions and the route, as annotations on the model.
 *
 * Same register as the feed: finished sentences a visitor can read, every number
 * lifted from the run. The compiler's verbatim wording — thresholds, clause ids,
 * evidence keys — stays one click away in the panel each callout opens.
 */
function buildCallouts(run: GenerationResponse): ViewportCallout[] {
  const analysis = run.analysis;
  if (!analysis) return [];
  const selection = analysis.selection;
  const callouts: ViewportCallout[] = [];

  if (selection) {
    callouts.push({
      id: 'form', index: '01', layer: 'envelope', anchor: 'top',
      title: selection.massing_label,
      body: cleanReason(selection.massing_reason[0]),
    });
  }
  const envelopeGroups = analysis.element_groups
    .filter((group) => group.semantic_layer === 'envelope');
  const styleHost = envelopeGroups.reduce<typeof envelopeGroups[number] | null>(
    (best, group) => (!best || group.instance_count > best.instance_count ? group : best), null);
  const gates = analysis.facade_gates;
  const gatesPassed = gates?.gates.filter((gate) => gate.verdict === 'passed').length ?? 0;
  callouts.push({
    id: 'style', index: '02', layer: 'envelope', subsystem: styleHost?.subsystem,
    title: gates?.grammar_label ?? human(analysis.facade_grammar_id, /^FCD-\d+-/),
    body: gates
      ? 'This facade follows written rules of its style — and passes '
      + (gatesPassed === gates.gates.length ? 'all ' + gates.gates.length
        : gatesPassed + ' of ' + gates.gates.length) + ' of them.'
      : cleanReason(styleHost?.reason),
  });
  callouts.push({
    id: 'structure', index: '03', layer: 'structure', subsystem: 'beams',
    title: human(analysis.structural_system_id, /^STR-SYS-/),
    body: selection
      ? 'Of the systems screened, ' + selection.admissible_systems.length
      + ' could carry this building. The music chose this one.'
      : '',
    anchor: 'mid',
  });
  if (analysis.accessible_route) {
    callouts.push({
      id: 'circulation', index: '04', layer: 'circulation', subsystem: 'ramps',
      title: 'Accessible ramp geometry',
      body: 'The ramp slope and landings were checked. Its facade portal and continuous '
        + 'supported route into the building still require verification.',
      anchor: 'mid',
    });
  } else {
    const circulationGroup = analysis.element_groups.find((group) =>
      group.semantic_layer === 'circulation' && group.reason
      && (group.kind.includes('stair') || group.kind.includes('ramp')));
    if (circulationGroup) {
      callouts.push({
        id: 'circulation', index: '04', layer: 'circulation',
        subsystem: circulationGroup.subsystem,
        title: titleCase(circulationGroup.kind),
        body: cleanReason(circulationGroup.reason),
        anchor: 'mid',
      });
    }
  }
  const allocation = analysis.program_allocation;
  callouts.push({
    id: 'program', index: '05', layer: 'program', anchor: 'mid',
    title: titleCase(analysis.typology),
    body: allocation
      ? 'Holds ' + Math.round(allocation.delivered_area_m2) + ' of the '
      + Math.round(allocation.required_area_m2) + ' m² the brief asked for.'
      : trimWords(selection?.note, 100),
  });
  return callouts.filter((callout) => callout.title && callout.body);
}

const CALLOUT_PANEL: Record<string, WorkspaceId> = {
  form: 'selection', style: 'selection', structure: 'structure',
  circulation: 'compliance', program: 'program',
};

export function ModelStage({
  run, layersOpen, onCloseLayers, sectionOpen, requestSection,
  mode, hud, annotate, buildKey, onOpenPanel,
  audio = null, compile = null, performNonce = 0,
}: {
  run: GenerationResponse | null;
  layersOpen: boolean;
  onCloseLayers: () => void;
  sectionOpen: boolean;
  requestSection: () => void;
  mode: ViewportMode;
  hud: boolean;
  annotate: boolean;
  buildKey: number;
  onOpenPanel?: (panel: WorkspaceId) => void;
  /** The recording the stage can hear, if any. */
  audio?: AudioSource | null;
  /** Set while a compile is running: the strip takes the stage. */
  compile?: CompileStatus | null;
  /** Bumped when a compile lands: that run performs once its model has loaded. */
  performNonce?: number;
}) {
  const [manifest, setManifest] = useState<GlbManifest | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [focus, setFocus] = useState<string | null>(null);
  const [highlightLayer, setHighlightLayer] = useState<string | null>(null);
  const [showSite, setShowSite] = useState(true);
  const [showProgramVolumes, setShowProgramVolumes] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [assembling, setAssembling] = useState<string | null>(null);
  // Labels get out of the way while the model is being turned, and come back the
  // moment the pointer lifts — the building is what you are looking at mid-orbit.
  const [orbiting, setOrbiting] = useState(false);
  // The performance: which rationale stage is speaking, how many of its lines are
  // out, and whether the whole argument has landed. `fast` is Skip — it shrinks the
  // live tempo so the assembly fast-forwards instead of being torn down.
  const [story, setStory] = useState<{ idx: number; reveal: number; done: boolean } | null>(null);
  const [fast, setFast] = useState(false);
  const [viewNonce, setViewNonce] = useState(0);
  const reduced = useMemo(
    () => typeof window !== 'undefined'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    []);
  // The toolbar's Section toggle is the only source of truth for whether the plane is
  // on, so it is composed in at render rather than mirrored into state here.
  const [plane, setPlane] = useState<Omit<ClippingSettings, 'enabled'>>({
    axis: 'z', offset: 3, inverted: true,
  });
  const clipping: ClippingSettings = { ...plane, enabled: sectionOpen };

  const asset = run?.model_asset_v3 ?? null;
  const manifestUrl = asset?.manifest_url ?? null;
  const glbUrl = asset?.asset_url ?? run?.model_asset?.asset_url ?? null;

  // The stage is no longer remounted per run — the Canvas, and with it the camera,
  // survives a run switch so two variants can be compared from the same viewpoint.
  // Per-run interaction state resets here, during render, the way React sanctions
  // adjusting state when a prop changes.
  // How many GLBs have reported ready, and whether the next one should perform.
  const [readyNonce, setReadyNonce] = useState(0);
  const [performSeen, setPerformSeen] = useState(performNonce);
  const [performArmed, setPerformArmed] = useState<number | null>(null);
  const [seenRunId, setSeenRunId] = useState(run?.run_id ?? null);
  if ((run?.run_id ?? null) !== seenRunId) {
    setSeenRunId(run?.run_id ?? null);
    setHidden(new Set());
    setFocus(null);
    setHighlightLayer(null);
    setShowProgramVolumes(false);
    setManifest(null);
    setAssembling(null);
    // Comparison is quiet: the feed belongs to a performance, not to a switch.
    setStory(null);
    setFast(false);
    setPerformArmed(null);
  }
  // A freshly compiled run is a first open, not a comparison: once its model is in,
  // it performs the way the page did on load. Arming records the ready count at the
  // moment the compile lands; the story starts only after that count has moved, so
  // it never opens over the previous building. The run-change reset above disarms a
  // switch to a stored run; this block, running after it, re-arms only for a compile.
  const [seenGlb, setSeenGlb] = useState(glbUrl);
  if (performSeen !== performNonce) {
    setPerformSeen(performNonce);
    // An identical re-run compiles to the same GLB, which is already in and will not
    // report ready again — so that one performs at once.
    setPerformArmed(glbUrl === seenGlb && loaded ? readyNonce - 1 : readyNonce);
  }
  if (glbUrl !== seenGlb) setSeenGlb(glbUrl);
  // A compile takes the stage: the previous run's feed steps aside for the recording.
  const [seenCompile, setSeenCompile] = useState<CompileStatus | null>(compile);
  if (compile !== seenCompile) {
    setSeenCompile(compile);
    if (compile) { setStory(null); setFast(false); }
  }

  // This effect therefore only fetches.
  useEffect(() => {
    let cancelled = false;
    if (!manifestUrl) return;
    loadGlbManifest(manifestUrl).then((next) => { if (!cancelled) setManifest(next); });
    return () => { cancelled = true; };
  }, [manifestUrl]);

  const handleReady = useCallback(() => {
    setLoaded(true);
    setReadyNonce((value) => value + 1);
  }, []);

  const stages = useMemo(() => (run ? buildStory(run) : []), [run]);

  const startStory = useCallback(() => {
    setFast(false);
    if (reduced || stages.length === 0) {
      setStory({ idx: Math.max(stages.length - 1, 0), reveal: 99, done: true });
      setViewNonce((value) => value + 1);
      return;
    }
    setStory({ idx: 0, reveal: 0, done: false });
    // A performance is always the whole assembly, from the ground.
    setViewNonce((value) => value + 1);
  }, [reduced, stages.length]);

  // The lattice the score set, in the viewer's frame.
  const latticeLines = useMemo<LatticeLines | null>(() => {
    const lattice = run?.analysis?.lattice;
    if (!lattice) return null;
    const xs = lattice.x_lines ?? [];
    const ys = lattice.y_lines ?? [];
    const plan = (lattice as { plan?: LatticeLines['plan'] }).plan ?? {
      x_min: Math.min(...xs), x_max: Math.max(...xs), y_min: Math.min(...ys), y_max: Math.max(...ys),
    };
    return { levels: lattice.levels.map((level) => ({ id: level.id, z: level.z })), xLines: xs, yLines: ys, plan };
  }, [run]);

  // The performance opens the page: once the first GLB is in, the score speaks first.
  // Once only — later runs perform through Play or a compile, never through a switch.
  // If a compile is already running when that first model lands, this opening is
  // spent unspoken: the compiled run performs instead, and nothing speaks over the
  // recording taking the stage.
  // One arc, three phases: the hearing becomes a score, the score becomes a lattice,
  // the lattice becomes a building. So the narrated build is *armed* by an opening, a
  // Play or a landed compile, and *starts* only once the score strip has written its
  // reading (it says so through `onEntered`) — with a five-second fallback so a
  // recording that cannot be decoded never stalls the building.
  const [armed, setArmed] = useState<'load' | 'play' | 'compile' | null>(null);
  const [scoreReady, setScoreReady] = useState(false);
  const [scoreReplay, setScoreReplay] = useState(0);
  const [gateFallback, setGateFallback] = useState(false);
  const [latticeKey, setLatticeKey] = useState(0);
  // While the lattice is being drawn the elements still wait: the lines first, then
  // what stands on them.
  const [latticeDrawing, setLatticeDrawing] = useState(false);
  const handleScoreEntered = useCallback(() => setScoreReady(true), []);
  // The hearing the strip decoded, handed up: the cloud the building is made from.
  const [hearing, setHearing] = useState<Hearing | null>(null);
  const handleHearing = useCallback((next: Hearing | null) => setHearing(next), []);
  // The compiler's reading of the parts, boxed on the ribbon: one box per part with
  // its rhythm number, netted to the whole-piece numbers those readings fold into.
  const net = useMemo<AnalysisNet | null>(() => {
    const features = run?.audio_features;
    const duration = features?.provenance.duration_seconds ?? 0;
    if (!run || !features || duration <= 0 || features.segments.length === 0) return null;
    const parts = features.segments.map((segment, index) => ({
      start: segment.start_seconds, end: segment.end_seconds,
      label: 'part ' + (index + 1) + '   ' + clock(segment.start_seconds) + '–' + clock(segment.end_seconds)
        + '\n' + 'onsets ' + segment.onset_density_hz.toFixed(1) + '/s · rms ' + segment.rms_energy.toFixed(3)
        + ' · ' + Math.round(segment.spectral_centroid_hz) + ' Hz',
    }));
    const nodes: AnalysisNet['nodes'] = [];
    const links: AnalysisNet['links'] = [];
    ['density', 'tension_release'].forEach((id) => {
      const dimension = run.architectural_score.dimensions.find((item) => item.id === id);
      if (!dimension) return;
      const at = nodes.length;
      nodes.push({ label: dimensionLabel(dimension.id) + ' ' + dimension.value.toFixed(2) });
      parts.forEach((_, index) => links.push([index, at]));
    });
    return { duration, parts, nodes, links };
  }, [run]);

  // The opening: true until the first model has armed its performance (or a compile
  // has taken that opening). It holds the model below ground from the first frame.
  const [opening, setOpening] = useState(true);
  useEffect(() => {
    if (!opening) return;
    if (compile) {
      const timer = window.setTimeout(() => setOpening(false), 0);
      return () => window.clearTimeout(timer);
    }
    if (!loaded) return;
    const timer = window.setTimeout(() => { setOpening(false); setArmed('load'); }, 0);
    return () => window.clearTimeout(timer);
  }, [loaded, compile, opening]);

  // The topbar's Play button replays the whole arc: the score is written again first.
  const playSeen = useRef(buildKey);
  useEffect(() => {
    if (playSeen.current === buildKey) return;
    playSeen.current = buildKey;
    const timer = window.setTimeout(() => {
      setScoreReady(false);
      setScoreReplay((value) => value + 1);
      setArmed('play');
    }, 0);
    return () => window.clearTimeout(timer);
  }, [buildKey]);

  useEffect(() => {
    if (!armed || scoreReady || !audio) return;
    const timer = window.setTimeout(() => setGateFallback(true), 5000);
    return () => window.clearTimeout(timer);
  }, [armed, scoreReady, audio]);

  useEffect(() => {
    if (!armed) return;
    if (audio && !scoreReady && !gateFallback) return;
    const timer = window.setTimeout(() => {
      setArmed(null);
      setGateFallback(false);
      setLatticeKey((value) => value + 1);
      setLatticeDrawing(Boolean(latticeLines) && !reduced);
      startStory();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [armed, audio, scoreReady, gateFallback, startStory, latticeLines, reduced]);

  // Held below ground: before the opening has armed, while a performance waits on the
  // score, while a compiled run waits on its model, and while the lattice is drawn
  // under stage 00 (Skip, or closing the feed, lets go of it at once).
  const hold = opening || armed !== null || performArmed !== null
    || (latticeDrawing && story !== null && !story.done && story.idx === 0 && !fast);

  useEffect(() => {
    if (performArmed === null || readyNonce === performArmed) return;
    const timer = window.setTimeout(() => {
      setPerformArmed(null);
      setScoreReady(false);
      setArmed('compile');
    }, 350);
    return () => window.clearTimeout(timer);
  }, [performArmed, readyNonce]);

  // Stage 00 has no geometry of its own — the lattice is drawn under it — and the
  // assembly starts, on the lattice, when the score finishes speaking. The wait is
  // keyed to the stage, not the story object, so each revealed line does not restart it.
  const storyPhase = story ? (story.done ? 'done' : story.idx) : null;
  useEffect(() => {
    if (storyPhase !== 0 || reduced) return;
    const wait = Math.max((stages[0]?.lines.length ?? 0) * 700 + 900, 2000);
    const timer = window.setTimeout(() => {
      setLatticeDrawing(false);
      setViewNonce((value) => value + 1);
    }, wait);
    return () => window.clearTimeout(timer);
  }, [storyPhase, stages, reduced]);

  // One line every 640 ms; Skip dumps the rest of the stage at once.
  useEffect(() => {
    if (!story) return;
    const lineCount = stages[story.idx]?.lines.length ?? 0;
    if (story.reveal >= lineCount) return;
    const timer = window.setInterval(() => {
      setStory((current) => (current
        ? { ...current, reveal: Math.min(current.reveal + 1, lineCount) }
        : current));
    }, fast ? 60 : 640);
    return () => window.clearInterval(timer);
  }, [story, stages, fast]);

  const handleAssembly = useCallback((layer: string | null) => {
    setAssembling(layer);
    setStory((current) => {
      if (!current || current.done) return current;
      if (layer === null) {
        return { idx: stages.length - 1, reveal: 0, done: true };
      }
      const idx = stages.findIndex((stage) => stage.layer === layer);
      return idx > 0 && idx !== current.idx
        ? { idx, reveal: 0, done: false }
        : current;
    });
  }, [stages]);
  const handleCalloutHover = useCallback((layer: string | null) => setHighlightLayer(layer), []);
  const handleCalloutClick = useCallback((id: string) => {
    const panel = CALLOUT_PANEL[id];
    if (panel) onOpenPanel?.(panel);
  }, [onOpenPanel]);

  const tree = useMemo(() => buildTree(manifest), [manifest]);
  const callouts = useMemo(() => (run ? buildCallouts(run) : []), [run]);
  const groupsByKey = useMemo(() => {
    const map = new Map<string, number>();
    (run?.analysis?.element_groups ?? []).forEach((group) => {
      const key = group.semantic_layer + '__' + group.subsystem + '__' + group.category;
      map.set(key, (map.get(key) ?? 0) + group.instance_count);
    });
    return map;
  }, [run]);

  const feedRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const feed = feedRef.current;
    if (feed) feed.scrollTop = feed.scrollHeight;
  }, [story]);

  const levels = run?.analysis?.lattice.levels ?? [];
  const handleLevelCut = useCallback((z: number) => {
    setPlane({ axis: 'z', offset: z, inverted: true });
    requestSection();
  }, [requestSection]);

  // Which layer is crossing from the score right now — the one assembling, the
  // lattice while the score speaks, or the one a keynote is holding up.
  const transferLayer = (assembling === 'site' ? 'lattice' : assembling)
    ?? (story && !story.done ? 'lattice' : null)
    ?? highlightLayer;
  // One reading at a time crosses: the layer's links, each spoken in turn — its
  // number on the sheet, its datum as a dimension string across the whole lattice.
  const links = useMemo(() => linksByLayer(run), [run]);
  const focusLinks = useMemo(() => (transferLayer ? links.get(transferLayer) ?? [] : []), [transferLayer, links]);
  const [linkIdx, setLinkIdx] = useState(0);
  const [seenLinks, setSeenLinks] = useState(focusLinks);
  if (seenLinks !== focusLinks) {
    setSeenLinks(focusLinks);
    setLinkIdx(0);
  }
  useEffect(() => {
    if (focusLinks.length < 2) return;
    const timer = window.setInterval(() => setLinkIdx((index) => index + 1), 1700);
    return () => window.clearInterval(timer);
  }, [focusLinks]);
  const focusLink = focusLinks.length > 0 ? focusLinks[linkIdx % focusLinks.length] : null;
  const reading = useMemo(() => (transferLayer && focusLink
    ? { layer: transferLayer, link: focusLink, index: linkIdx % focusLinks.length, count: focusLinks.length }
    : null), [transferLayer, focusLink, linkIdx, focusLinks.length]);
  const transfer = useMemo<Transfer | null>(() => (reading ? { layer: reading.layer, datums: reading.link.datums } : null), [reading]);

  const soundStrip = (
    <ScoreStrip
      source={audio}
      run={run}
      mode={mode}
      prominent={Boolean(compile)}
      compile={compile}
      focus={reading}
      replayKey={scoreReplay}
      onEntered={handleScoreEntered}
      onHearing={handleHearing}
      onOpenPanel={onOpenPanel}
    />
  );

  if (!run || !glbUrl) {
    return (
      <div className={'stage-empty' + (compile ? ' has-prominent' : '')}>
        <Empty title="No model loaded">
          Open an MP3 to compile a building, or reopen a stored run.
        </Empty>
        {soundStrip}
      </div>
    );
  }

  function toggle(key: string) {
    setHidden((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }

  function toggleLayer(node: TreeNode) {
    const keys = node.children.map((child) => child.key);
    const allHidden = keys.every((key) => hidden.has(key));
    setHidden((current) => {
      const next = new Set(current);
      keys.forEach((key) => { if (allHidden) next.delete(key); else next.add(key); });
      return next;
    });
  }

  function isolate(layer: string | null) {
    if (!layer) { setHidden(new Set()); return; }
    const next = new Set<string>();
    tree.forEach((node) => {
      if (node.layer === layer) return;
      node.children.forEach((child) => next.add(child.key));
    });
    setHidden(next);
  }

  // Counted against what the GLB holds rather than against the model's element count:
  // the exporter merges drawable geometry only, so quoting the model total here would
  // report a shortfall that is not one.
  const drawnTotal = tree.reduce(
    (sum, node) => sum + node.children.reduce((inner, child) => inner + child.elements, 0), 0);
  const visibleElements = tree.reduce((sum, node) => sum + node.children
    .filter((child) => !hidden.has(child.key))
    .reduce((inner, child) => inner + child.elements, 0), 0);
  return (
    <div
      className={'stage' + (audio && !compile ? ' has-strip' : '') + (compile ? ' has-prominent' : '')}
      onPointerDown={(event) => {
        if (event.target instanceof HTMLCanvasElement) setOrbiting(true);
      }}
      onPointerUp={() => setOrbiting(false)}
      onPointerLeave={() => setOrbiting(false)}
    >
      <ArchitectureViewport
        assetUrl={assetUrl(glbUrl)}
        mode={mode}
        hidden={hidden}
        focus={focus}
        highlightLayer={highlightLayer}
        lattice={latticeLines}
        latticeKey={latticeKey}
        transfer={transfer}
        hearing={hearing}
        cloudKey={latticeKey}
        net={net}
        clipping={clipping}
        showSite={showSite}
        programVolumes={run.analysis ? {
          lattice: run.analysis.lattice,
          allocation: run.analysis.program_allocation,
          model: run.analysis.program_volume_model,
          visible: showProgramVolumes,
        } : null}
        callouts={callouts}
        annotate={annotate && !orbiting && !layersOpen && story === null}
        buildKey={viewNonce}
        hold={hold}
        stepSeconds={story && !story.done && !fast ? 3.0 : 0.55}
        onReady={handleReady}
        onAssembly={handleAssembly}
        onCalloutHover={handleCalloutHover}
        onCalloutClick={handleCalloutClick}
      />

      {!loaded && <div className="viewport-busy">Loading the model…</div>}

      {soundStrip}

      {hud && (
        <StageHud
          run={run}
          assembling={assembling}
          layersOpen={layersOpen}
          onOpenCompliance={() => onOpenPanel?.('compliance')}
        />
      )}

      {story && (
        <aside className="story-feed" data-avoid aria-label="Design rationale, narrated">
          <header>
            <h2>The design, explained</h2>
            {!story.done && (
              <button
                type="button" className="btn btn-sm btn-ghost"
                onClick={() => {
                  setFast(true);
                  setStory((current) => (current ? { ...current, reveal: 99 } : current));
                }}
              >Skip</button>
            )}
            <button
              type="button" className="icon-btn" aria-label="Close rationale"
              onClick={() => setStory(null)}
            >×</button>
          </header>
          <div className="story-feed-body" ref={feedRef}>
            {stages.slice(0, story.idx + 1).map((stage, stageIndex) => {
              const isCurrent = stageIndex === story.idx;
              const shown = isCurrent && !story.done
                ? stage.lines.slice(0, story.reveal)
                : stage.lines;
              return (
                <section key={stage.id} className="story-stage">
                  <h4><i>{stage.index}</i>{stage.title}</h4>
                  {shown.map((line, lineIndex) => (
                    <p
                      key={lineIndex}
                      className={'story-line'
                        + (isCurrent && !story.done && lineIndex === shown.length - 1
                          ? ' is-live' : '')}
                    >{line}</p>
                  ))}
                </section>
              );
            })}
            {!story.done && <p className="story-caret">▌</p>}
          </div>
        </aside>
      )}

      {/* The building's name and its three choices are the HUD's first block; the
          caption that repeated them at the foot of the stage is gone. */}
      <p className="stage-hint" data-avoid>
        {assembling
          ? 'Assembling · ' + assembling
          : sectionOpen
            ? 'Cut at ' + clipping.axis.toUpperCase() + ' ' + clipping.offset.toFixed(1)
              + ' m · Section clears it'
            : hidden.size > 0 || focus
              ? compact(visibleElements) + ' of ' + compact(drawnTotal)
                + ' elements shown · Layers to change'
              : ''}
      </p>

      {layersOpen && (
        <aside className="floating-panel layers-panel" data-avoid aria-label="Layers">
          <header>
            <h2>Layers</h2>
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => isolate(null)}>
              Show all
            </button>
            <button
              type="button" className="icon-btn" aria-label="Close layers"
              onClick={onCloseLayers}
            >×</button>
          </header>

          <div className="floating-panel-body">
            {tree.length === 0 ? (
              <p className="prose" style={{ padding: 12 }}>
                The GLB manifest for this run could not be read, so the tree is empty.
                The model still draws.
              </p>
            ) : tree.map((node) => (
              <div key={node.layer} className="layer-group">
                <ToggleRow
                  on={!node.children.every((child) => hidden.has(child.key))}
                  label={titleCase(node.layer)}
                  count={compact(node.elements)}
                  swatch={node.layer}
                  onToggle={() => toggleLayer(node)}
                />
                <div className="tree-children">
                  {node.children.map((child) => (
                    <div key={child.key} className="tree-row">
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <ToggleRow
                          on={!hidden.has(child.key)}
                          label={titleCase(child.subsystem) + ' · ' + child.category}
                          count={compact(groupsByKey.get(child.key) ?? child.elements)}
                          onToggle={() => toggle(child.key)}
                        />
                      </div>
                      <button
                        type="button"
                        className={'btn btn-sm btn-ghost' + (focus === child.key ? ' is-active' : '')}
                        title="Draw this subsystem alone, with the rest faded back"
                        onClick={() => setFocus(focus === child.key ? null : child.key)}
                      >focus</button>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <footer>
            <button
              type="button"
              className={'btn btn-sm' + (showSite ? ' is-active' : '')}
              onClick={() => setShowSite((value) => !value)}
            >Site context</button>
            <button
              type="button"
              className={'btn btn-sm' + (showProgramVolumes ? ' is-active' : '')}
              onClick={() => setShowProgramVolumes((value) => !value)}
            >Program volumes</button>
            {focus && (
              <button type="button" className="btn btn-sm" onClick={() => setFocus(null)}>
                Clear focus
              </button>
            )}
          </footer>
        </aside>
      )}

      {sectionOpen && (
        <div className="section-dock" data-avoid role="group" aria-label="Section plane">
          <div className="segmented">
            {SECTION_AXES.map((axis) => (
              <button
                key={axis} type="button"
                className={clipping.axis === axis ? 'is-active' : ''}
                onClick={() => setPlane((current) => ({ ...current, axis, offset: 0 }))}
              >{axis.toUpperCase()}</button>
            ))}
          </div>
          <input
            className="slider"
            aria-label="Section plane position"
            type="range" min={-30} max={30} step={0.1}
            value={clipping.offset}
            onChange={(event) => setPlane(
              (current) => ({ ...current, offset: Number(event.target.value) }))}
          />
          <span className="num">{clipping.offset.toFixed(1)} m</span>
          <button
            type="button"
            className={'btn btn-sm' + (clipping.inverted ? ' is-active' : '')}
            onClick={() => setPlane((current) => ({ ...current, inverted: !current.inverted }))}
          >Flip</button>
          {levels.length > 0 && (
            <div className="dock-levels" role="group" aria-label="Cut a level's plan">
              {levels.map((level) => (
                <button
                  key={level.id}
                  type="button"
                  className={'dock-level'
                    + (clipping.axis === 'z' && Math.abs(clipping.offset - (level.z + 1.2)) < 0.05 ? ' is-active' : '')}
                  title={titleCase(level.kind) + ' · +' + level.z.toFixed(2) + ' m'}
                  onClick={() => handleLevelCut(level.z + 1.2)}
                >{level.id}</button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
