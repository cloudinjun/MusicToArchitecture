'use client';

/**
 * The hearing lab: the recording analysed and taken apart — and nothing else.
 *
 * No building here. This is the front of the ladder, 音乐 → 图形 → 抽象, on its own,
 * so the visual of the analysis can be judged by itself. The recording is a field of
 * points: time along the width, frequency (log, 40 Hz – 7 kHz) as height, loudness as
 * relief towards the viewer — the machine's hearing, the same field the score is
 * written from. Over it, drawn stroke by stroke like a survey, is the analysis the
 * compiler actually made: the loudness and centroid curves read off the field; one
 * wire box per part with its three measurements as a caption and a small bar chart;
 * the twelve whole-piece measurements as nodes above, netted from the parts; the ten
 * score dimensions as nodes below, netted from the measurements they were read from.
 * Thin frames, small monospace captions with real numbers, straight lines crossing
 * the whole picture — the register of a point cloud under survey frames.
 *
 * Everything on screen is the run's own data or derived from the hearing on the
 * spot; nothing is authored. The GPU holds the field; positions are a function of the
 * lab's clock, so Replay just moves the origin.
 */

/* eslint-disable react-hooks/immutability -- the sweep plane, the grids and the label
   divs are scene objects written from the frame loop; none of it is React state. */

import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import Link from 'next/link';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import type { AudioFeatures, GenerationResponse } from '../lib/types';
import { assetUrl, loadDemoRun } from '../lib/api';
import { decodeHearing, type Hearing } from '../lib/hearing';
import { clock as clockText, dimensionLabel } from '../lib/format';
import { LiveSpectrum } from './LiveSpectrum';
import { NebulaSpectrum } from './NebulaSpectrum';

const BANDS = 32;
const FIELD_W = 64;
const FIELD_H = 18;
const FIELD_D = 5;
const F_LO = 40;
const F_HI = 7000;
const MEASURE_Y = FIELD_H + 7.5;
const DIMENSION_Y = -7.5;

/** When each layer of the survey is drawn: [start, duration] in seconds. */
const CUE = {
  grid: [0.2, 1.0], field: [0.6, 2.6], axes: [1.6, 1.2], curves: [3.2, 1.4],
  parts: [3.8, 2.6], measures: [6.4, 1.8], dimensions: [8.0, 1.4],
} as const;
type Cue = readonly [number, number];

const PALE = '#dbe7ff';
const WARM = '#ffd28a';

interface LabClock { t0: number }
const elapsedOf = (lab: LabClock) => (performance.now() - lab.t0) / 1000;
const clamp01 = (value: number) => Math.min(1, Math.max(0, value));
const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);

/** The twelve whole-piece measurements, named the way the workbench names them. */
const MEASURES: Array<{ key: keyof AudioFeatures; label: string; format: (value: number) => string }> = [
  { key: 'tempo_bpm', label: 'tempo', format: (v) => Math.round(v) + ' bpm' },
  { key: 'rms_energy', label: 'loudness', format: (v) => v.toFixed(3) + ' rms' },
  { key: 'onset_density_hz', label: 'onsets', format: (v) => v.toFixed(2) + '/s' },
  { key: 'spectral_centroid_hz', label: 'centroid', format: (v) => Math.round(v) + ' Hz' },
  { key: 'periodicity', label: 'periodicity', format: (v) => v.toFixed(2) },
  { key: 'timbre_variation', label: 'timbre variation', format: (v) => v.toFixed(2) },
  { key: 'dynamic_range_db', label: 'dynamic range', format: (v) => v.toFixed(1) + ' dB' },
  { key: 'novelty_peak_rate_per_min', label: 'novelty peaks', format: (v) => v.toFixed(1) + '/min' },
  { key: 'spectral_contrast_db', label: 'spectral contrast', format: (v) => v.toFixed(1) + ' dB' },
  { key: 'harmonic_ratio', label: 'harmonic ratio', format: (v) => v.toFixed(2) },
  { key: 'spectral_flatness', label: 'flatness', format: (v) => v.toFixed(3) },
  { key: 'zero_crossing_rate', label: 'zero crossings', format: (v) => v.toFixed(3) },
];

interface Label {
  text: string;
  at: THREE.Vector3;
  kind: 'part' | 'measure' | 'dimension' | 'axis' | 'time';
  cue: Cue;
}

interface Survey {
  field: { geometry: THREE.BufferGeometry; count: number };
  strokes: Array<{ id: string; positions: number[]; cue: Cue; color: string; opacity: number }>;
  labels: Label[];
  columns: number;
}

function seg(out: number[], a: THREE.Vector3, b: THREE.Vector3) {
  out.push(a.x, a.y, a.z, b.x, b.y, b.z);
}
const v3 = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);

function bandOfHz(hz: number): number {
  return (Math.log(hz / F_LO) / Math.log(F_HI / F_LO)) * (BANDS - 1);
}

/** Everything drawn, computed once from the run and its hearing. */
function buildSurvey(run: GenerationResponse, hearing: Hearing): Survey | null {
  const columns = hearing.cells.length / BANDS;
  if (columns < 2) return null;
  const features = run.audio_features;
  const duration = features.provenance.duration_seconds || hearing.duration;
  const xAt = (seconds: number) => (seconds / duration - 0.5) * FIELD_W;
  const yAt = (band: number) => (band / (BANDS - 1)) * FIELD_H;

  // --- the field: one point per cell that has anything in it -----------------------
  const keep: number[] = [];
  for (let c = 0; c < columns; c += 1) {
    for (let b = 0; b < BANDS; b += 1) {
      if (hearing.cells[b * columns + c] > 6) keep.push(c * BANDS + b);
    }
  }
  const n = keep.length;
  const position = new Float32Array(n * 3);
  const tone = new Float32Array(n);
  const jitter = new Float32Array(n);
  const when = new Float32Array(n);
  let seed = 11;
  const random = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
  keep.forEach((cell, i) => {
    const c = Math.floor(cell / BANDS);
    const b = cell % BANDS;
    const v = hearing.cells[b * columns + c] / 255;
    position[i * 3] = ((c + random()) / columns - 0.5) * FIELD_W;
    position[i * 3 + 1] = yAt(b + random() - 0.5);
    position[i * 3 + 2] = v * FIELD_D + (random() - 0.5) * 0.3;
    tone[i] = v;
    jitter[i] = random();
    when[i] = c / columns;
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(position, 3));
  geometry.setAttribute('aTone', new THREE.BufferAttribute(tone, 1));
  geometry.setAttribute('aJitter', new THREE.BufferAttribute(jitter, 1));
  geometry.setAttribute('aWhen', new THREE.BufferAttribute(when, 1));
  geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, FIELD_H / 2, 0), 200);

  const strokes: Survey['strokes'] = [];
  const labels: Label[] = [];

  // --- axes: the frequency rule on the left, the clock along the bottom -------------
  const axes: number[] = [];
  const left = -FIELD_W / 2 - 1.2;
  seg(axes, v3(left, 0, 0), v3(left, FIELD_H, 0));
  [100, 300, 1000, 3000].forEach((hz) => {
    const y = yAt(bandOfHz(hz));
    seg(axes, v3(left - 0.6, y, 0), v3(left, y, 0));
    labels.push({ text: hz >= 1000 ? hz / 1000 + ' kHz' : hz + ' Hz', at: v3(left - 0.8, y, 0), kind: 'axis', cue: CUE.axes });
  });
  seg(axes, v3(-FIELD_W / 2, -1.2, 0), v3(FIELD_W / 2, -1.2, 0));
  for (let s = 0; s <= duration; s += 10) {
    const x = xAt(s);
    seg(axes, v3(x, -1.2, 0), v3(x, -1.8, 0));
    labels.push({ text: clockText(s), at: v3(x, -2.0, 0), kind: 'time', cue: CUE.axes });
  }
  strokes.push({ id: 'axes', positions: axes, cue: CUE.axes, color: PALE, opacity: 0.55 });

  // --- curves read off the field: loudness per column, centroid per column ---------
  const loud = new Float32Array(columns);
  const centroid = new Float32Array(columns);
  for (let c = 0; c < columns; c += 1) {
    let sum = 0; let weighted = 0;
    for (let b = 0; b < BANDS; b += 1) {
      const v = hearing.cells[b * columns + c] / 255;
      sum += v; weighted += v * b;
    }
    loud[c] = sum / BANDS;
    centroid[c] = sum > 0 ? weighted / sum : 0;
  }
  const smooth = (arr: Float32Array, radius: number) => arr.map((_, i) => {
    let total = 0; let count = 0;
    for (let k = -radius; k <= radius; k += 1) {
      const j = i + k;
      if (j >= 0 && j < arr.length) { total += arr[j]; count += 1; }
    }
    return total / count;
  });
  const loudS = smooth(loud, 6);
  const centS = smooth(centroid, 6);
  const loudMax = Math.max(...loudS, 1e-6);
  const curves: number[] = [];
  const stepC = 4;
  for (let c = 0; c + stepC < columns; c += stepC) {
    const x0 = ((c) / columns - 0.5) * FIELD_W;
    const x1 = ((c + stepC) / columns - 0.5) * FIELD_W;
    seg(curves, v3(x0, FIELD_H + 1.6 + (loudS[c] / loudMax) * 3.4, 0), v3(x1, FIELD_H + 1.6 + (loudS[c + stepC] / loudMax) * 3.4, 0));
  }
  for (let c = 0; c + stepC < columns; c += stepC) {
    const x0 = ((c) / columns - 0.5) * FIELD_W;
    const x1 = ((c + stepC) / columns - 0.5) * FIELD_W;
    seg(curves, v3(x0, yAt(centS[c]), FIELD_D + 0.8), v3(x1, yAt(centS[c + stepC]), FIELD_D + 0.8));
  }
  strokes.push({ id: 'curves', positions: curves, cue: CUE.curves, color: WARM, opacity: 0.9 });
  labels.push({ text: 'loudness, per column', at: v3(FIELD_W / 2 + 0.8, FIELD_H + 1.6 + (loudS[columns - 1] / loudMax) * 3.4, 0), kind: 'measure', cue: CUE.curves });
  labels.push({ text: 'centroid, per column', at: v3(FIELD_W / 2 + 0.8, yAt(centS[columns - 1]), FIELD_D + 0.8), kind: 'measure', cue: CUE.curves });

  // --- the parts: a box each, a caption, a small chart of its three numbers --------
  const parts = features.segments;
  const maxOf = (pick: (s: AudioFeatures['segments'][number]) => number) => Math.max(...parts.map(pick), 1e-6);
  const norms = { rms: maxOf((s) => s.rms_energy), onsets: maxOf((s) => s.onset_density_hz), centroid: maxOf((s) => s.spectral_centroid_hz) };
  const partStrokes: number[] = [];
  const partTops: THREE.Vector3[] = [];
  parts.forEach((part, index) => {
    const x0 = xAt(part.start_seconds) + 0.2;
    const x1 = xAt(part.end_seconds) - 0.2;
    const y0 = -0.4;
    const y1 = FIELD_H + 0.4;
    const z0 = -0.4;
    const z1 = FIELD_D + 0.4;
    const c = [
      v3(x0, y0, z0), v3(x1, y0, z0), v3(x1, y0, z1), v3(x0, y0, z1),
      v3(x0, y1, z0), v3(x1, y1, z0), v3(x1, y1, z1), v3(x0, y1, z1),
    ];
    [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]]
      .forEach(([a, b]) => seg(partStrokes, c[a], c[b]));
    // The chart under the box: loudness, onsets, centroid against the loudest part.
    const base = -3.2;
    const bars = [part.rms_energy / norms.rms, part.onset_density_hz / norms.onsets, part.spectral_centroid_hz / norms.centroid];
    seg(partStrokes, v3(x0, base, z1), v3(x0 + 3.2, base, z1));
    bars.forEach((bar, k) => {
      const x = x0 + 0.5 + k * 1.0;
      seg(partStrokes, v3(x, base, z1), v3(x, base + bar * 2.2, z1));
      seg(partStrokes, v3(x + 0.18, base, z1), v3(x + 0.18, base + bar * 2.2, z1));
    });
    // The stub the net leaves from.
    const top = v3((x0 + x1) / 2, y1, z0);
    seg(partStrokes, top, top.clone().add(v3(0, 0.6, 0)));
    partTops.push(top.clone().add(v3(0, 0.6, 0)));
    labels.push({
      text: 'part ' + (index + 1) + '  ' + clockText(part.start_seconds) + '–' + clockText(part.end_seconds)
        + '\n' + 'onsets ' + part.onset_density_hz.toFixed(1) + '/s · rms ' + part.rms_energy.toFixed(3)
        + ' · ' + Math.round(part.spectral_centroid_hz) + ' Hz',
      at: v3(x0 + 3.6, base + 1.0 - (index % 2) * 2.6, z1), kind: 'part', cue: [CUE.parts[0] + index * 0.35, 0.5],
    });
  });
  partTops.forEach((top, i) => { if (partTops[i + 1]) seg(partStrokes, top, partTops[i + 1]); });
  strokes.push({ id: 'parts', positions: partStrokes, cue: CUE.parts, color: PALE, opacity: 0.9 });

  // --- the twelve measurements, above; netted from the parts that feed them --------
  const measureAt = new Map<string, THREE.Vector3>();
  const measureStrokes: number[] = [];
  const diamond = (out: number[], at: THREE.Vector3, d: number) => {
    seg(out, at.clone().add(v3(-d, 0, 0)), at.clone().add(v3(0, d, 0)));
    seg(out, at.clone().add(v3(0, d, 0)), at.clone().add(v3(d, 0, 0)));
    seg(out, at.clone().add(v3(d, 0, 0)), at.clone().add(v3(0, -d, 0)));
    seg(out, at.clone().add(v3(0, -d, 0)), at.clone().add(v3(-d, 0, 0)));
  };
  MEASURES.forEach((measure, i) => {
    const metric = features[measure.key];
    if (!metric || typeof metric !== 'object' || !('value' in metric)) return;
    const at = v3(((i + 0.5) / MEASURES.length - 0.5) * (FIELD_W + 8), MEASURE_Y + (i % 2) * 2.2, 0);
    measureAt.set(measure.key, at);
    diamond(measureStrokes, at, 0.45);
    labels.push({ text: measure.label + ' ' + measure.format(metric.value), at, kind: 'measure', cue: [CUE.measures[0] + i * 0.08, 0.5] });
  });
  const fed: Array<keyof AudioFeatures> = ['rms_energy', 'onset_density_hz', 'spectral_centroid_hz'];
  partTops.forEach((top) => fed.forEach((key) => { const at = measureAt.get(key); if (at) seg(measureStrokes, top, at); }));
  strokes.push({ id: 'measures', positions: measureStrokes, cue: CUE.measures, color: PALE, opacity: 0.7 });

  // --- the ten dimensions, below; netted from the measurements they were read from --
  const dimensionStrokes: number[] = [];
  const dimensions = run.architectural_score.dimensions;
  dimensions.forEach((dimension, i) => {
    const at = v3(((i + 0.5) / dimensions.length - 0.5) * (FIELD_W + 6), DIMENSION_Y - (i % 3) * 2.6, 0);
    diamond(dimensionStrokes, at, 0.5);
    const sources = dimension.source_feature.split('+').map((s) => s.trim());
    sources.forEach((source) => { const from = measureAt.get(source); if (from) seg(dimensionStrokes, from, at); });
    const named = sources.slice(0, 2).map((s) => MEASURES.find((m) => m.key === s)?.label ?? s.replace(/_/g, ' '));
    labels.push({
      text: dimensionLabel(dimension.id) + ' ' + dimension.value.toFixed(2) + '\n← ' + named.join(' + ')
        + (sources.length > 2 ? ' + ' + (sources.length - 2) + ' more' : ''),
      at, kind: 'dimension', cue: [CUE.dimensions[0] + i * 0.1, 0.5],
    });
  });
  strokes.push({ id: 'dimensions', positions: dimensionStrokes, cue: CUE.dimensions, color: WARM, opacity: 0.8 });

  return { field: { geometry, count: n }, strokes, labels, columns };
}

const FIELD_VERTEX = /* glsl */`
attribute float aTone;
attribute float aJitter;
attribute float aWhen;
uniform float uElapsed;
uniform float uTime;
uniform float uPixelRatio;
uniform float uSweepStart;
uniform float uSweepDur;
varying float vAlpha;
varying float vTone;
void main() {
  float sweep = clamp((uElapsed - uSweepStart) / uSweepDur, 0.0, 1.0);
  float born = clamp((sweep - aWhen) * 14.0, 0.0, 1.0);
  vec3 pos = position;
  pos.y += sin(uTime * 0.8 + aJitter * 30.0) * 0.05;
  pos.z += (1.0 - born) * 4.0;
  vAlpha = born * (0.22 + 0.78 * aTone) * (0.86 + 0.14 * sin(uTime * 2.0 + aJitter * 50.0));
  vTone = aTone;
  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  gl_PointSize = (1.1 + 3.2 * aTone) * uPixelRatio * (130.0 / -mv.z);
  gl_Position = projectionMatrix * mv;
}
`;
const FIELD_FRAGMENT = /* glsl */`
uniform vec3 uColor;
varying float vAlpha;
varying float vTone;
void main() {
  vec2 d = gl_PointCoord - 0.5;
  float r = dot(d, d);
  if (r > 0.25) discard;
  float soft = smoothstep(0.25, 0.03, r);
  gl_FragColor = vec4(uColor * (0.5 + 0.7 * vTone), vAlpha * soft);
}
`;

function Field({ survey, lab }: { survey: Survey; lab: RefObject<LabClock> }) {
  const material = useMemo(() => new THREE.ShaderMaterial({
    uniforms: {
      uElapsed: { value: 0 }, uTime: { value: 0 }, uPixelRatio: { value: 1 },
      uSweepStart: { value: CUE.field[0] }, uSweepDur: { value: CUE.field[1] },
      uColor: { value: new THREE.Color('#cfe4ff') },
    },
    vertexShader: FIELD_VERTEX, fragmentShader: FIELD_FRAGMENT,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  }), []);
  useEffect(() => () => material.dispose(), [material]);
  const sweepRef = useRef<THREE.Mesh>(null);
  useFrame(({ clock, gl }) => {
    material.uniforms.uTime.value = clock.getElapsedTime();
    material.uniforms.uElapsed.value = elapsedOf(lab.current);
    material.uniforms.uPixelRatio.value = gl.getPixelRatio();
    const plane = sweepRef.current;
    if (plane) {
      const p = clamp01((elapsedOf(lab.current) - CUE.field[0]) / CUE.field[1]);
      plane.position.x = (p - 0.5) * FIELD_W;
      (plane.material as THREE.MeshBasicMaterial).opacity = p > 0 && p < 1 ? 0.18 : 0;
    }
  });
  return (
    <>
      <points geometry={survey.field.geometry} material={material} frustumCulled={false} />
      {/* The reading window: a plane that crosses the field once, left to right. */}
      <mesh ref={sweepRef} position={[-FIELD_W / 2, FIELD_H / 2, FIELD_D / 2]} rotation-y={Math.PI / 2}>
        <planeGeometry args={[FIELD_D + 3, FIELD_H + 3]} />
        <meshBasicMaterial color="#cfe4ff" transparent opacity={0} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
    </>
  );
}

function Strokes({ positions, cue, color, opacity, lab }: {
  positions: number[]; cue: Cue; color: string; opacity: number; lab: RefObject<LabClock>;
}) {
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    g.setDrawRange(0, 0);
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, FIELD_H / 2, 0), 400);
    return g;
  }, [positions]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  const material = useMemo(() => new THREE.LineBasicMaterial({ color, transparent: true, opacity, toneMapped: false }), [color, opacity]);
  useEffect(() => () => material.dispose(), [material]);
  const total = positions.length / 3;
  useFrame(() => {
    const p = clamp01((elapsedOf(lab.current) - cue[0]) / cue[1]);
    geometry.setDrawRange(0, Math.floor(easeOut(p) * total));
  });
  return <lineSegments geometry={geometry} material={material} frustumCulled={false} />;
}

function Backdrop({ lab }: { lab: RefObject<LabClock> }) {
  const wall = useMemo(() => {
    const grid = new THREE.GridHelper(220, 88, '#9cc4ff', '#9cc4ff');
    grid.rotation.x = Math.PI / 2;
    grid.position.set(0, FIELD_H / 2, -9);
    const material = grid.material as THREE.LineBasicMaterial;
    material.transparent = true; material.opacity = 0; material.toneMapped = false;
    return grid;
  }, []);
  const floor = useMemo(() => {
    const grid = new THREE.GridHelper(220, 88, '#9cc4ff', '#9cc4ff');
    grid.position.set(0, -12, 0);
    const material = grid.material as THREE.LineBasicMaterial;
    material.transparent = true; material.opacity = 0; material.toneMapped = false;
    return grid;
  }, []);
  useFrame(() => {
    const p = clamp01((elapsedOf(lab.current) - CUE.grid[0]) / CUE.grid[1]);
    (wall.material as THREE.LineBasicMaterial).opacity = 0.12 * p;
    (floor.material as THREE.LineBasicMaterial).opacity = 0.08 * p;
  });
  return (
    <>
      <primitive object={wall} />
      <primitive object={floor} />
    </>
  );
}

/** The captions: divs in the overlay, placed every frame, faded in on their cue. */
function Labels({ labels, holder, lab }: { labels: Label[]; holder: RefObject<HTMLDivElement | null>; lab: RefObject<LabClock> }) {
  const { camera, size } = useThree();
  const made = useRef<HTMLElement[]>([]);
  useEffect(() => {
    const root = holder.current;
    if (!root) return;
    const els = labels.map((label) => {
      const el = document.createElement('div');
      el.className = 'lab-label is-' + label.kind;
      el.textContent = label.text;
      root.appendChild(el);
      return el;
    });
    made.current = els;
    return () => { els.forEach((el) => el.remove()); made.current = []; };
  }, [labels, holder]);
  const point = useMemo(() => new THREE.Vector3(), []);
  useFrame(() => {
    const t = elapsedOf(lab.current);
    made.current.forEach((el, i) => {
      const label = labels[i];
      const alpha = clamp01((t - label.cue[0]) / Math.max(0.2, label.cue[1]));
      point.copy(label.at).project(camera);
      if (point.z > 1 || alpha <= 0) { el.style.opacity = '0'; return; }
      el.style.left = (((point.x + 1) / 2) * size.width).toFixed(1) + 'px';
      el.style.top = (((1 - point.y) / 2) * size.height).toFixed(1) + 'px';
      el.style.opacity = alpha.toFixed(2);
    });
  });
  return null;
}

function Scene({ survey, holder, lab }: { survey: Survey; holder: RefObject<HTMLDivElement | null>; lab: RefObject<LabClock> }) {
  return (
    <>
      <color attach="background" args={['#0e2f66']} />
      <Backdrop lab={lab} />
      <Field survey={survey} lab={lab} />
      {survey.strokes.map((stroke) => (
        <Strokes key={stroke.id} positions={stroke.positions} cue={stroke.cue} color={stroke.color} opacity={stroke.opacity} lab={lab} />
      ))}
      <Labels labels={survey.labels} holder={holder} lab={lab} />
      <OrbitControls
        target={[0, FIELD_H / 2 + 1, 0]}
        enableDamping
        dampingFactor={0.08}
        autoRotate
        autoRotateSpeed={0.35}
        minDistance={30}
        maxDistance={160}
        maxPolarAngle={Math.PI * 0.62}
      />
    </>
  );
}

export function HearingLab() {
  const [run, setRun] = useState<GenerationResponse | null>(null);
  const [hearing, setHearing] = useState<Hearing | null>(null);
  const [status, setStatus] = useState('Loading the run…');
  // 'live': the spectrum as particles while the track plays — the lab with its
  // constraints off. 'survey': the recording taken apart, still.
  const [view, setView] = useState<'live' | 'frames' | 'survey'>('live');
  const lab = useRef<LabClock>({ t0: 0 });
  const holder = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const demo = await loadDemoRun();
      if (cancelled) return;
      if (!demo) { setStatus('No demo run reachable.'); return; }
      setRun(demo);
      setStatus('Listening…');
      const filename = demo.audio_features.provenance.filename;
      try {
        const response = await fetch('/audio/' + filename);
        const buffer = await response.arrayBuffer();
        const heard = await decodeHearing(buffer);
        if (cancelled) return;
        setHearing(heard);
        setStatus('');
        lab.current.t0 = performance.now() + 200;
      } catch (error) {
        if (!cancelled) setStatus('Could not decode ' + filename + ': ' + (error instanceof Error ? error.message : 'unknown'));
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const survey = useMemo(() => (run && hearing ? buildSurvey(run, hearing) : null), [run, hearing]);
  const replay = useCallback(() => { lab.current.t0 = performance.now() + 100; }, []);
  const features = run?.audio_features ?? null;

  const filename = features?.provenance.filename ?? null;
  return (
    <div className="hearing-lab">
      {view === 'live' && filename && (
        <NebulaSpectrum
          url={'/audio/' + filename}
          name={filename}
          dimensions={run?.architectural_score.dimensions ?? []}
          glbUrl={run?.model_asset_v3 ? assetUrl(run.model_asset_v3.asset_url) : null}
        />
      )}
      {view === 'frames' && filename && (
        <LiveSpectrum url={'/audio/' + filename} name={filename} />
      )}
      {view === 'survey' && survey && (
        <Canvas camera={{ position: [26, 24, 78], fov: 34, near: 0.5, far: 1000 }} dpr={[1, 2]} gl={{ antialias: true }}>
          <Scene survey={survey} holder={holder} lab={lab} />
        </Canvas>
      )}
      <div ref={holder} className="lab-labels" aria-hidden="true" />
      <div className="lab-title">
        <h1>{view === 'live' ? 'The recording, as a mass' : view === 'frames' ? 'The recording, live' : 'The recording, taken apart'}</h1>
        {features && (
          <p>
            {features.provenance.filename} · {clockText(features.provenance.duration_seconds)}
            {survey ? ' · ' + survey.field.count.toLocaleString() + ' points' : ''}
            {' · ' + features.segments.length + ' parts · ' + MEASURES.length + ' measurements · '
              + (run?.architectural_score.dimensions.length ?? 0) + ' dimensions'}
          </p>
        )}
        {status && <p className="lab-status">{status}</p>}
      </div>
      <div className="lab-actions">
        <button type="button" className={'topbar-btn' + (view === 'live' ? ' is-active' : '')} onClick={() => setView('live')}>Live</button>
        <button type="button" className={'topbar-btn' + (view === 'frames' ? ' is-active' : '')} onClick={() => setView('frames')}>Frames</button>
        <button type="button" className={'topbar-btn' + (view === 'survey' ? ' is-active' : '')} onClick={() => { setView('survey'); replay(); }}>Survey</button>
        {view === 'survey' && <button type="button" className="topbar-btn" onClick={replay}>Replay</button>}
        <Link className="topbar-btn" href="/">Workbench</Link>
      </div>
    </div>
  );
}
