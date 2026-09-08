'use client';

/**
 * The music, as the score it was read as.
 *
 * The building is frozen music: the compiler heard the recording once, took its
 * measurements, and everything after that was drawn from those numbers. So the
 * strip shows the recording the way a score sits on a stand — whole, still, read
 * left to right — and never as a player. Nothing on it moves with playback except a
 * hairline and the measure it is in; nothing on it is a live spectrum.
 *
 * It is engraved, not drawn: Bravura, the SMuFL reference font, sets the clef, the
 * noteheads, the dynamics and the metronome mark, and the strokes — staff, bar
 * lines, stems, beams, hairpins — are at Bravura's engraving thicknesses, with one em
 * equal to four staff spaces. Every mark is a measurement the compiler reported:
 *
 * - six segments → six measures, bar lines at the compiler's cuts;
 * - onset density → how many notes a measure holds (a sparse part is one quarter
 *   note; a busy one is a beamed run of eighths);
 * - spectral centroid → where the notes sit on the staff (brighter sits higher);
 * - loudness against the track's mean → the dynamic under the measure, p to f, and a
 *   hairpin where the next measure is louder or softer;
 * - tempo → the metronome mark at the head.
 *
 * The motion is the score's own, borrowed from where scores already move (see
 * docs/sound_strip_references.md): a reading is *written* — the staff, then bar
 * lines, stems, beams and hairpins as strokes, with heads, dynamics and clef pooling
 * in as ink — out of the machine's hearing as it dissolves (Legumes' stroke-by-stroke
 * rendering); listening lights the measure the cursor is in, as abcjs, OSMD and
 * alphaTab follow a score; a measure lifts under the pointer and its patch of the
 * hearing returns beneath it. Nothing here touches the 3D scene.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { animate, createTimeline, stagger, svg as animeSvg } from 'animejs';
import type { AudioSource, GenerationResponse, SegmentFeatures, WorkspaceId } from '../lib/types';
import { clock, dimensionLabel } from '../lib/format';
import { datumValue, layerLabel, type Link } from '../lib/links';
import { decodeHearing, hearingImage, parseRgb, type Hearing } from '../lib/hearing';
import { EASE_OUT, reducedMotion } from '../lib/motion';
import { ENGRAVING, GLYPH, SMUFL, dynamicGlyph } from '../lib/smufl';
import type { ViewportMode } from './ArchitectureViewport';

export interface CompileStatus {
  startedAt: number;
  /** The previous run's wall time, if one is known, so the wait has a scale. */
  estimateSeconds: number | null;
}

type Dynamic = 'p' | 'mp' | 'mf' | 'f';
const LEVEL: Record<Dynamic, number> = { p: 0, mp: 1, mf: 2, f: 3 };

interface Measure {
  index: number;
  start: number;
  end: number;
  x0: number;
  x1: number;
  /** 1..8 note heads, from onset density. */
  notes: number;
  /** 0..8: staff position from the bottom line up, from spectral centroid. */
  pitch: number;
  dynamic: Dynamic;
  /** The measured words a hover reveals. */
  words: string[];
  segment: SegmentFeatures;
}

interface Heard {
  source: AudioSource;
  hearing: Hearing | null;
  error: string | null;
}

type FontState = 'loading' | 'ready' | 'missing';

const STAFF_LINES = 5;
const RIGHT = 18;
const CLEF_X = 6;

/** Loudness against the track's mean, as the dynamic a score would print. */
function dynamicOf(rms: number, mean: number): Dynamic {
  if (mean <= 0) return 'mf';
  const ratio = rms / mean;
  return ratio < 0.7 ? 'p' : ratio < 0.95 ? 'mp' : ratio < 1.25 ? 'mf' : 'f';
}

function relative(value: number, base: number, up: string, down: string, mid: string, band: number): string {
  if (base <= 0) return mid;
  const ratio = value / base;
  return ratio > 1 + band ? up : ratio < 1 - band ? down : mid;
}

function layMeasures(segments: SegmentFeatures[], duration: number, left: number, width: number): Measure[] {
  if (segments.length === 0 || width <= left + RIGHT + 20) return [];
  const span = width - left - RIGHT;
  const total = duration > 0 ? duration : segments[segments.length - 1].end_seconds;
  const mean = (pick: (s: SegmentFeatures) => number) =>
    segments.reduce((sum, s) => sum + pick(s), 0) / segments.length;
  const meanRms = mean((s) => s.rms_energy);
  const meanOnset = mean((s) => s.onset_density_hz);
  const meanCentroid = mean((s) => s.spectral_centroid_hz);
  const maxOnset = Math.max(...segments.map((s) => s.onset_density_hz), 0.0001);
  const logs = segments.map((s) => Math.log(Math.max(s.spectral_centroid_hz, 1)));
  const lo = Math.min(...logs);
  const hi = Math.max(...logs);
  return segments.map((segment, index) => ({
    index,
    start: segment.start_seconds,
    end: segment.end_seconds,
    x0: left + (segment.start_seconds / total) * span,
    x1: left + (segment.end_seconds / total) * span,
    notes: 1 + Math.round((segment.onset_density_hz / maxOnset) * 7),
    pitch: hi > lo ? Math.round(((logs[index] - lo) / (hi - lo)) * 8) : 4,
    dynamic: dynamicOf(segment.rms_energy, meanRms),
    words: [
      relative(segment.onset_density_hz, meanOnset, 'busier', 'sparser', 'even', 0.15),
      relative(segment.spectral_centroid_hz, meanCentroid, 'brighter', 'darker', 'mid-toned', 0.1),
    ],
    segment,
  }));
}

export function ScoreStrip({
  source, run, mode, prominent, compile, focus = null, replayKey = 0, onEntered, onHearing, onOpenPanel,
}: {
  source: AudioSource | null;
  run: GenerationResponse | null;
  mode: ViewportMode;
  /** The compile-phase face: centred, large, the only thing on the stage. */
  prominent: boolean;
  compile: CompileStatus | null;
  /** The reading crossing to the building right now: one score dimension, read from
   *  the whole piece, on its way to one layer — with its place in that layer's list. */
  focus?: { layer: string; link: Link; index: number; count: number } | null;
  /** Bump to write the reading in again — the Play button replays the whole arc. */
  replayKey?: number;
  /** The reading has been written: the stage may start building on it. */
  onEntered?: () => void;
  /** The hearing, once decoded (null when there is none): the stage's cloud is made of it. */
  onHearing?: (hearing: Hearing | null) => void;
  onOpenPanel?: (id: WorkspaceId) => void;
}) {
  const sheetRef = useRef<SVGSVGElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const cursorRef = useRef<SVGLineElement>(null);
  const rafRef = useRef(0);
  const loopRef = useRef<() => void>(() => {});
  const [width, setWidth] = useState(0);
  const [hover, setHover] = useState<number | null>(null);
  const [live, setLive] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [now, setNow] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [heard, setHeard] = useState<Heard | null>(null);
  const [font, setFont] = useState<FontState>(
    () => (typeof document !== 'undefined' && 'fonts' in document ? 'loading' : 'missing'));
  // Which recording's entrance has finished: until then the marks stay unseen so a
  // reading is written exactly once, out of its hearing, and never blinks.
  const [enteredFor, setEnteredFor] = useState<AudioSource | null>(null);
  // A replay writes the reading in again from its hearing.
  const [seenReplay, setSeenReplay] = useState(replayKey);
  if (seenReplay !== replayKey) {
    setSeenReplay(replayKey);
    setEnteredFor(null);
  }
  const onEnteredRef = useRef(onEntered);
  useEffect(() => { onEnteredRef.current = onEntered; }, [onEntered]);
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try { return window.localStorage.getItem('mta.score') === 'off'; } catch { return false; }
  });
  const reduced = useMemo(() => reducedMotion(), []);

  // The compiler's reading is shown only when it is this recording's.
  const matches = Boolean(run && source && run.audio_features.provenance.filename === source.name);
  const features = matches && run ? run.audio_features : null;
  const segments = useMemo(() => features?.segments ?? [], [features]);
  const hearing = heard && heard.source === source ? heard.hearing : null;
  const settled = heard?.source === source;
  const onHearingRef = useRef(onHearing);
  useEffect(() => { onHearingRef.current = onHearing; }, [onHearing]);
  useEffect(() => { onHearingRef.current?.(hearing); }, [hearing]);
  const entered = enteredFor === source;
  const glyphs = font === 'ready';
  const duration = features?.provenance.duration_seconds ?? hearing?.duration ?? 0;
  const bpm = features ? Math.round(features.tempo_bpm.value) : null;

  const link = focus?.link ?? null;

  // Geometry of the sheet, in staff spaces: one scale for the small strip, a larger one
  // for the face that takes the stage during a compile. One em is four spaces.
  const gap = prominent ? 9 : 6;
  const em = gap * 4;
  const top = prominent ? 46 : 32;
  const bottom = top + gap * (STAFF_LINES - 1);
  // Room under the dynamics for the analysis bracket a reading in focus draws.
  const height = Math.round(bottom + gap * 5.4);
  const left = Math.round(CLEF_X + GLYPH.gClef.width * gap + gap * 1.4);
  const span = Math.max(0, width - left - RIGHT);
  const measures = useMemo(() => layMeasures(segments, duration, left, width), [segments, duration, left, width]);

  // The music font, or its absence: the sheet waits at most three seconds, then
  // engraves with drawn heads and a serif dynamic rather than glyph boxes.
  useEffect(() => {
    if (typeof document === 'undefined' || !('fonts' in document)) return;
    let cancelled = false;
    const timer = window.setTimeout(() => { if (!cancelled) setFont((state) => (state === 'loading' ? 'missing' : state)); }, 3000);
    document.fonts.load('24px Bravura').then((faces) => {
      if (!cancelled) setFont(faces.length > 0 ? 'ready' : 'missing');
    }).catch(() => { if (!cancelled) setFont('missing'); });
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, []);

  // The hearing: decoded once per recording, offline. It is raw material for the
  // entrance and the hover, never a meter.
  useEffect(() => {
    if (!source) return;
    const controller = new AbortController();
    fetch(source.url, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('The recording could not be fetched (' + response.status + ').');
        return response.arrayBuffer();
      })
      .then(decodeHearing)
      .then((next) => { if (!controller.signal.aborted) setHeard({ source, hearing: next, error: null }); })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setHeard({ source, hearing: null, error: error instanceof Error ? error.message : 'undecodable' });
      });
    return () => controller.abort();
  }, [source]);

  // The hearing as an image in the theme's accent, repainted when either changes.
  const imageUrl = useMemo(() => {
    if (!hearing || typeof document === 'undefined') return '';
    return hearingImage(hearing, parseRgb(mode === 'blueprint' ? '#9cc4ff' : '#0071e3', [0, 113, 227]));
  }, [hearing, mode]);

  // The sheet follows its box.
  useEffect(() => {
    const sheet = sheetRef.current;
    if (!sheet) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    observer.observe(sheet);
    return () => observer.disconnect();
  }, [prominent, collapsed]);

  // The compile clock.
  useEffect(() => {
    if (!compile) return;
    const started = compile.startedAt;
    const timer = window.setInterval(() => setElapsed((Date.now() - started) / 1000), 250);
    return () => window.clearInterval(timer);
  }, [compile]);

  // The reading is written — once its hearing and its font have both resolved. The
  // hearing surfaces; the staff draws across it; the clef and the mark pool in; then
  // measure by measure the bar line is ruled, the heads rise out of the field, the
  // stems are drawn, the beam is ruled, the dynamic and its hairpin follow — while
  // the hearing dissolves. Stroke by stroke, the way a score is put on paper.
  useEffect(() => {
    const sheet = sheetRef.current;
    if (!sheet || reduced || !settled || font === 'loading' || entered || width === 0 || measures.length === 0) return;
    const lines = sheet.querySelectorAll<SVGLineElement>('.score-line');
    const bars = sheet.querySelectorAll<SVGGElement>('.score-measure');
    const field = sheet.querySelector<SVGImageElement>('.score-hearing');
    const head = sheet.querySelectorAll<SVGElement>('.score-clef, .score-tempo');
    const finals = sheet.querySelectorAll<SVGLineElement>('.score-final');
    if (lines.length === 0) return;
    const withField = Boolean(field && imageUrl);
    const arrived = source;
    const tl = createTimeline({
      defaults: { ease: EASE_OUT },
      onComplete: () => { setEnteredFor(arrived); onEnteredRef.current?.(); },
    });

    // Everything starts unseen, set at time zero rather than assumed.
    tl.set(head, { opacity: 0 }, 0);
    tl.set(finals, { opacity: 0 }, 0);
    bars.forEach((bar) => {
      tl.set(bar, { opacity: 1 }, 0);
      tl.set(bar.querySelectorAll('.score-head'), { opacity: 0, scale: 0.3, translateY: gap * 1.4 }, 0);
      tl.set(bar.querySelectorAll('.score-stem, .score-bar, .score-hairpin'), { opacity: 0 }, 0);
      tl.set(bar.querySelectorAll('.score-beam'), { scaleX: 0 }, 0);
      tl.set(bar.querySelectorAll('.score-dynamic, .score-number'), { opacity: 0 }, 0);
    });

    if (withField && field) tl.add(field, { opacity: [0, 0.8], duration: 520 }, 0);
    const staffAt = withField ? 360 : 0;
    tl.add(animeSvg.createDrawable(lines), {
      draw: ['0 0', '0 1'], duration: 620, ease: 'linear', delay: stagger(45),
    }, staffAt);
    tl.add(head, { opacity: 1, duration: 360, delay: stagger(120) }, staffAt + 420);

    let at = staffAt + 720;
    bars.forEach((bar) => {
      const rule = bar.querySelectorAll<SVGLineElement>('.score-bar');
      const heads = bar.querySelectorAll<SVGElement>('.score-head');
      const stems = bar.querySelectorAll<SVGLineElement>('.score-stem');
      const beam = bar.querySelectorAll<SVGRectElement>('.score-beam');
      const marks = bar.querySelectorAll<SVGElement>('.score-dynamic, .score-number');
      const pins = bar.querySelectorAll<SVGPolylineElement>('.score-hairpin');
      if (rule.length) {
        tl.add(rule, { opacity: 1, duration: 1 }, at);
        tl.add(animeSvg.createDrawable(rule), { draw: ['0 0', '0 1'], duration: 160, ease: 'linear' }, at);
      }
      tl.add(heads, { opacity: 1, scale: 1, translateY: 0, duration: 420, delay: stagger(36) }, at + 80);
      if (stems.length) {
        tl.add(stems, { opacity: 1, duration: 1, delay: stagger(36) }, at + 200);
        tl.add(animeSvg.createDrawable(stems), { draw: ['0 0', '0 1'], duration: 140, ease: 'linear', delay: stagger(36) }, at + 200);
      }
      if (beam.length) tl.add(beam, { scaleX: 1, duration: 240 }, at + 260 + stems.length * 36);
      tl.add(marks, { opacity: 1, duration: 260 }, at + 300);
      if (pins.length) {
        tl.add(pins, { opacity: 1, duration: 1 }, at + 380);
        tl.add(animeSvg.createDrawable(pins), { draw: ['0 0', '0 1'], duration: 260, ease: 'linear' }, at + 380);
      }
      at += 150;
    });
    tl.add(finals, { opacity: 1, duration: 200 }, at + 100);
    if (withField && field) tl.add(field, { opacity: 0, duration: 900, ease: 'inOutSine' }, staffAt + 820);
    return () => { tl.cancel(); };
    // The entrance belongs to a reading's arrival, not to a resize or a hover.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, measures.length, settled, font === 'loading', entered, reduced, width === 0]);

  // With nothing to write (no reading yet) or no motion wanted, the reading counts as
  // entered at once, so the stage is never left waiting on a score that will not come.
  useEffect(() => {
    if (entered || !source || !settled || font === 'loading' || width === 0) return;
    if (!(reduced || segments.length === 0)) return;
    const arrived = source;
    const timer = window.setTimeout(() => { setEnteredFor(arrived); onEnteredRef.current?.(); }, 0);
    return () => window.clearTimeout(timer);
  }, [entered, source, settled, font, width, reduced, segments.length]);

  // The analysis bracket: under all the measures, the way a theorist brackets the
  // whole passage a reading is about. The whole field votes into it — a reading
  // window sweeps the entire staff and every part of it sends a vote to the bracket's
  // label, which is where the leader to the building starts: the number, not a note.
  const bracketY = bottom + gap * 3.4;
  const labelY = bracketY + gap * 1.5;
  const voteSeeds = useMemo(() => {
    const seeds: Array<{ x: number; y: number }> = [];
    measures.forEach((m) => {
      for (let k = 0; k < 4; k += 1) {
        for (let r = 0; r < 3; r += 1) {
          seeds.push({ x: m.x0 + ((k + 0.5) / 4) * (m.x1 - m.x0), y: top + gap * (0.6 + r * 1.4) });
        }
      }
    });
    return seeds;
  }, [measures, top, gap]);
  const focusKey = focus ? focus.layer + ':' + focus.link.id : null;
  useEffect(() => {
    const sheet = sheetRef.current;
    if (!sheet) return;
    if (!focusKey || !entered) { delete sheet.dataset.transferSource; return; }
    sheet.dataset.transferSource = focusKey;
    sheet.dataset.transferX = (left + span / 2).toFixed(1);
    sheet.dataset.transferY = (labelY - 9).toFixed(1);
    if (reduced) return;
    const sweep = sheet.querySelector<SVGRectElement>('.score-sweep');
    const votes = sheet.querySelectorAll<SVGCircleElement>('.score-vote');
    const anims: Array<{ cancel: () => void }> = [];
    if (sweep) {
      anims.push(animate(sweep, {
        x: [left, left + span - gap * 2], opacity: [0, 0.35, 0], duration: 620, ease: 'inOutQuad',
      }));
    }
    if (votes.length > 0) {
      anims.push(animate(votes, {
        cx: left + span / 2, cy: labelY - 3,
        opacity: [{ to: 0.9, duration: 120 }, { to: 0, duration: 520 }],
        duration: 640, delay: stagger(5), ease: 'inQuad',
      }));
    }
    return () => anims.forEach((anim) => anim.cancel());
  }, [focusKey, entered, reduced, left, span, gap, labelY]);

  // While a compile runs, a reading line sweeps the empty staff.
  useEffect(() => {
    const sheet = sheetRef.current;
    if (!sheet || !compile || reduced || width === 0) return;
    const reader = sheet.querySelector<SVGLineElement>('.score-reader');
    if (!reader) return;
    const sweep = createTimeline({ loop: true, alternate: true }).add(reader, {
      translateX: [0, span], duration: 5200, ease: 'inOutSine',
    });
    return () => { sweep.cancel(); };
  }, [compile, reduced, width, span]);

  // Listening: a hairline follows the score and the measure it is in takes the
  // accent, the way a score-follower does. Nothing outside the sheet responds.
  useEffect(() => {
    loopRef.current = () => {
      const audio = audioRef.current;
      const cursor = cursorRef.current;
      if (!audio || !cursor) { rafRef.current = 0; return; }
      const total = audio.duration || duration || 1;
      const t = audio.currentTime;
      const x = left + Math.min(1, t / total) * span;
      cursor.setAttribute('x1', x.toFixed(1));
      cursor.setAttribute('x2', x.toFixed(1));
      const quarter = Math.floor(t * 4) / 4;
      setNow((current) => (current === quarter ? current : quarter));
      const index = measures.findIndex((m) => t >= m.start && t < m.end);
      setLive((current) => (current === index ? current : index >= 0 ? index : null));
      rafRef.current = !audio.paused && !audio.ended ? requestAnimationFrame(loopRef.current) : 0;
    };
  }, [duration, span, left, measures]);
  useEffect(() => () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); }, []);

  const toggle = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || !source) return;
    if (audio.paused) audio.play().catch(() => { /* blocked until a gesture; the button stays */ });
    else audio.pause();
  }, [source]);

  const remember = (next: boolean) => {
    setCollapsed(next);
    try { window.localStorage.setItem('mta.score', next ? 'off' : 'on'); } catch { /* fine */ }
  };

  if (!source) return null;

  const audioElement = (
    <audio
      ref={audioRef}
      src={source.url}
      preload="metadata"
      onPlay={() => {
        setPlaying(true);
        if (rafRef.current) cancelAnimationFrame(rafRef.current);
        rafRef.current = requestAnimationFrame(loopRef.current);
      }}
      onPause={() => { setPlaying(false); setLive(null); }}
      onEnded={() => { setPlaying(false); setLive(null); }}
    />
  );

  if (collapsed && !prominent) {
    return (
      <>
        {audioElement}
        <button type="button" className="score-pill" data-avoid onClick={() => remember(false)} title="Show the score">
          {glyphs ? <span className="score-glyph-inline">{SMUFL.metNoteQuarterUp}</span> : '♩'} {source.name}
        </button>
      </>
    );
  }

  const hovered = hover !== null ? measures[hover] : null;
  const estimate = compile?.estimateSeconds ?? null;
  const fieldTop = top - gap * 1.6;
  const fieldHeight = bottom - top + gap * 3.2;
  const headW = GLYPH.noteheadBlack.width * gap;
  const stemW = Math.max(0.9, ENGRAVING.stemThickness * gap);
  const thin = Math.max(1, ENGRAVING.thinBarlineThickness * gap);
  const thick = ENGRAVING.thickBarlineThickness * gap;
  const dynY = bottom + gap * 2.2;
  const marksVisible = reduced || entered;
  const lineStart = CLEF_X - 2;

  return (
    <>
      {audioElement}
      <section
        key={prominent ? 'prominent' : 'strip'}
        className={'score-strip' + (prominent ? ' is-prominent' : '')}
        data-avoid
        aria-label="The recording, as the score it was read as"
      >
        <header className="score-head">
          <button
            type="button" className="score-title"
            onClick={() => { if (features) onOpenPanel?.('audio'); }}
            title={features ? 'Every measurement, in the Audio report' : source.name}
          >
            <b>{source.name}</b>
            <span>
              {features
                ? `${clock(duration)} · ${measures.length || segments.length} measures · ♩ ${bpm}`
                : compile ? 'being read' : (duration > 0 ? clock(duration) + ' · ' : '') + 'not yet read'}
            </span>
          </button>
          {features && (
            <button
              type="button" className={'score-play' + (playing ? ' is-on' : '')}
              onClick={toggle}
              aria-label={playing ? 'Pause' : 'Listen'}
              title={playing ? 'Pause' : 'Listen to the recording'}
            >
              {playing ? '❚❚' : '▶'}
              {playing && <span className="score-time">{clock(now)}</span>}
            </button>
          )}
          {!prominent && (
            <button type="button" className="icon-btn" aria-label="Hide the score" onClick={() => remember(true)}>×</button>
          )}
        </header>

        <svg
          ref={sheetRef}
          className="score-sheet"
          height={height}
          onPointerLeave={() => setHover(null)}
          aria-hidden="true"
        >
          {width > 0 && (
            <>
              <defs>
                {measures.map((m) => (
                  <clipPath key={m.index} id={`score-clip-${m.index}`}>
                    <rect x={m.x0} y={fieldTop} width={m.x1 - m.x0} height={fieldHeight} />
                  </clipPath>
                ))}
              </defs>
              {imageUrl && measures.length > 0 && (
                <image
                  className="score-hearing" href={imageUrl}
                  x={left} y={fieldTop} width={span} height={fieldHeight}
                  preserveAspectRatio="none" opacity={0}
                />
              )}
              {imageUrl && hovered && (
                <image
                  className="score-hearing-hover" href={imageUrl}
                  x={left} y={fieldTop} width={span} height={fieldHeight}
                  preserveAspectRatio="none" clipPath={`url(#score-clip-${hovered.index})`}
                />
              )}

              {/* The staff, the clef on its G line, and the metronome mark above. */}
              {Array.from({ length: STAFF_LINES }, (_, i) => (
                <line
                  key={i} className="score-line"
                  x1={lineStart} x2={width - RIGHT} y1={top + i * gap} y2={top + i * gap}
                  strokeWidth={Math.max(1, ENGRAVING.staffLineThickness * gap)}
                />
              ))}
              {glyphs && (
                <text
                  className="score-glyph score-clef" x={CLEF_X} y={bottom - gap} fontSize={em}
                  style={{ opacity: marksVisible || measures.length === 0 ? 1 : 0 }}
                >{SMUFL.gClef}</text>
              )}
              {bpm !== null && (
                <g className="score-tempo" style={{ opacity: marksVisible ? 1 : 0 }}>
                  {/* Above the first measure, clear of the clef's ascender, as a score sets it. */}
                  {glyphs ? (
                    <>
                      <text className="score-glyph" x={left + 1} y={top - gap * 1.1} fontSize={em * 0.72}>{SMUFL.metNoteQuarterUp}</text>
                      <text className="score-tempo-text" x={left + 1 + GLYPH.metNoteQuarterUp.width * gap * 0.72 + 5} y={top - gap * 1.1}>= {bpm}</text>
                    </>
                  ) : (
                    <text className="score-tempo-text" x={left + 1} y={top - gap * 1.1}>♩ = {bpm}</text>
                  )}
                </g>
              )}

              {measures.map((m, k) => {
                const pad = Math.min(gap * 1.6, (m.x1 - m.x0) * 0.14);
                const inner = Math.max(4, m.x1 - m.x0 - pad * 2);
                const step = m.notes > 1 ? inner / (m.notes - 1) : 0;
                const cy = bottom - (m.pitch * gap) / 2;
                const stemTop = cy - ENGRAVING.stemLength * gap;
                const heads = Array.from({ length: m.notes }, (_, i) =>
                  m.notes > 1 ? m.x0 + pad + i * step : (m.x0 + m.x1) / 2);
                const stemX = (cx: number) => cx - headW / 2 + GLYPH.noteheadBlack.stemUpSE[0] * gap - stemW / 2;
                const stemY = cy - GLYPH.noteheadBlack.stemUpSE[1] * gap;
                const beamed = m.notes >= 3;
                const next = measures[k + 1];
                const rise = next ? LEVEL[next.dynamic] - LEVEL[m.dynamic] : 0;
                const dyn = GLYPH.dynamic[m.dynamic];
                const dynX = m.x0 + gap * 0.5 + dyn.left * gap;
                const pinFrom = dynX + dyn.width * gap + gap * 0.6;
                const pinTo = m.x1 - gap * 0.6;
                const pinOpen = gap * 0.9;
                return (
                  <g
                    key={m.index}
                    className={'score-measure' + (hover === m.index ? ' is-hover' : '') + (live === m.index ? ' is-live' : '')}
                    style={{ opacity: marksVisible ? undefined : 0 }}
                    onPointerEnter={() => setHover(m.index)}
                  >
                    {m.index > 0 && (
                      <line className="score-bar" x1={m.x0} x2={m.x0} y1={top} y2={bottom} strokeWidth={thin} />
                    )}
                    {m.index > 0 && (
                      <text className="score-number" x={m.x0 + 4} y={top - gap * 1.1}>{m.index + 1}</text>
                    )}
                    {heads.map((cx, i) => (
                      <g key={i}>
                        {glyphs ? (
                          <text
                            className="score-glyph score-head score-note"
                            x={cx - headW / 2} y={cy} fontSize={em}
                            style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
                          >{SMUFL.noteheadBlack}</text>
                        ) : (
                          <ellipse
                            className="score-head score-note"
                            cx={cx} cy={cy} rx={gap * 0.62} ry={gap * 0.44}
                            transform={`rotate(-20 ${cx} ${cy})`}
                            style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
                          />
                        )}
                        <line
                          className="score-stem"
                          x1={stemX(cx)} x2={stemX(cx)} y1={stemY} y2={stemTop}
                          strokeWidth={stemW}
                        />
                      </g>
                    ))}
                    {beamed && (
                      <rect
                        className="score-beam"
                        x={stemX(heads[0]) - stemW / 2} y={stemTop}
                        width={stemX(heads[heads.length - 1]) - stemX(heads[0]) + stemW}
                        height={ENGRAVING.beamThickness * gap}
                        style={{ transformBox: 'fill-box', transformOrigin: 'left center' }}
                      />
                    )}
                    {glyphs ? (
                      <text className="score-glyph score-dynamic" x={dynX} y={dynY} fontSize={em}>{dynamicGlyph(m.dynamic)}</text>
                    ) : (
                      <text className="score-dynamic is-fallback" x={dynX} y={dynY}>{m.dynamic}</text>
                    )}
                    {rise !== 0 && pinTo - pinFrom > gap * 2.5 && (
                      <polyline
                        className="score-hairpin"
                        strokeWidth={Math.max(1, ENGRAVING.hairpinThickness * gap)}
                        points={rise > 0
                          ? `${pinTo},${dynY - pinOpen / 2 - gap * 0.3} ${pinFrom},${dynY - gap * 0.3} ${pinTo},${dynY + pinOpen / 2 - gap * 0.3}`
                          : `${pinFrom},${dynY - pinOpen / 2 - gap * 0.3} ${pinTo},${dynY - gap * 0.3} ${pinFrom},${dynY + pinOpen / 2 - gap * 0.3}`}
                      />
                    )}
                    <rect className="score-hit" x={m.x0} y={0} width={m.x1 - m.x0} height={height} />
                  </g>
                );
              })}
              {measures.length > 0 && (
                <g style={{ opacity: marksVisible ? undefined : 0 }}>
                  <line
                    className="score-bar score-final"
                    x1={width - RIGHT - thick - ENGRAVING.barlineSeparation * gap}
                    x2={width - RIGHT - thick - ENGRAVING.barlineSeparation * gap}
                    y1={top} y2={bottom} strokeWidth={thin}
                  />
                  <line
                    className="score-bar score-final is-final"
                    x1={width - RIGHT - thick / 2} x2={width - RIGHT - thick / 2}
                    y1={top} y2={bottom} strokeWidth={thick}
                  />
                </g>
              )}
              {compile && (
                <line className="score-reader" x1={left} x2={left} y1={top - 8} y2={bottom + 8} />
              )}
              {focus && link && entered && (
                <g className="score-bracket" key={focus.layer + ':' + link.id}>
                  {!reduced && (
                    <rect className="score-sweep" x={left} y={top - gap} width={gap * 2} height={bottom - top + gap * 2} />
                  )}
                  {!reduced && voteSeeds.map((seed, index) => (
                    <circle key={index} className="score-vote" cx={seed.x} cy={seed.y} r={1.5} />
                  ))}
                  <line className="score-bracket-line" x1={left} x2={left + span} y1={bracketY} y2={bracketY} />
                  <line className="score-bracket-tick" x1={left} x2={left} y1={bracketY - gap * 0.8} y2={bracketY} />
                  <line className="score-bracket-tick" x1={left + span} x2={left + span} y1={bracketY - gap * 0.8} y2={bracketY} />
                  <text className="score-bracket-label" x={left + span / 2} y={labelY} textAnchor="middle">
                    {'all ' + measures.length + ' measures → ' + dimensionLabel(link.id)
                      + (Number.isFinite(link.value) ? ' ' + link.value.toFixed(2) : '')}
                  </text>
                </g>
              )}
              {playing && (
                <line ref={cursorRef} className="score-cursor" x1={left} x2={left} y1={top - 8} y2={bottom + 8} />
              )}
              {!features && !compile && span > 0 && (
                <text className="score-empty" x={left + span / 2} y={dynY} textAnchor="middle">
                  nothing read yet
                </text>
              )}
            </>
          )}
        </svg>

        <footer className="score-read">
          {compile ? (
            <>
              <b className="is-processing">Reading</b>
              <span className="score-clock">
                {elapsed.toFixed(0)} s{estimate ? ` · the previous run took ${estimate.toFixed(0)} s` : ''}
              </span>
              <span>Measuring the music · scoring ten dimensions · choosing type, form, style and structure · laying out rooms · drawing</span>
            </>
          ) : hovered ? (
            <>
              <b>Measure {hovered.index + 1}</b>
              <span>{hovered.dynamic} · {hovered.words.join(' · ')} · {clock(hovered.start)}–{clock(hovered.end)}</span>
            </>
          ) : focus && link ? (
            <>
              <b>
                {layerLabel(focus.layer)} ← {dimensionLabel(link.id)}
                {Number.isFinite(link.value) ? ' ' + link.value.toFixed(2) : ''}
              </b>
              <span>
                {link.datums.length > 0
                  ? '→ ' + link.datums.slice(0, 3).map((d) => d.label + ' ' + datumValue(d)).join(' · ')
                  : 'read from ' + link.features.map((feature) => feature.replace(/_/g, ' ')).join(', ')}
                {focus.count > 1 ? ' · ' + (focus.index + 1) + '/' + focus.count : ''}
              </span>
            </>
          ) : features ? (
            <span>
              Read once, before anything was drawn. Notes are onsets, height is brightness, the
              dynamic is loudness. Hover a measure to see what it was drawn from.
            </span>
          ) : (
            <span>Press Generate to read it as a score.</span>
          )}
        </footer>
      </section>
    </>
  );
}
