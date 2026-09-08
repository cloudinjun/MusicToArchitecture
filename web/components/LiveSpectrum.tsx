'use client';

/**
 * The spectrum, live, as particles — the analysis lab with its constraints off.
 *
 * The workbench's rule that nothing moves with playback holds for the *building*.
 * Here there is no building: this is the machine listening, as a thing to watch. The
 * track plays; an analyser reads its spectrum every frame; each spectrum is written
 * as one row of a small texture, and the GPU turns the rows into the picture:
 *
 * - **the history** — every row ever written is a line of points across the width
 *   (30 Hz – 16 kHz, log), lifted by loudness, receding into the depth as newer rows
 *   arrive; as a row ages it drifts and lifts with a slow turbulence, the loud cells
 *   most, so the recording's past smears into wisps, the way a simulation render of
 *   smoke or thunder reads on a sheet;
 * - **the sparks** — fifty thousand particles on a looping life, each tied to one
 *   band; at birth a spark reads the loudness of its band in the row written when it
 *   was born, and only a loud cell throws it, up off the crest into the same
 *   turbulence, fading as it rises. Bass sparks warm and slow, treble pale and quick.
 *
 * Over that, **the analysis frames**, drawn as a survey of the simulation: the
 * spectral centroid as a thread through the history; a cross at every onset the flux
 * detector fires, with a coordinate caption `e12 [t, band, level]`; a frame around
 * every six-second stage with its mean readings; a frame around the last 1.5 s with
 * the live numbers; a ruler of seconds along the edge; the frequency scale in front.
 * The particles are GPU work from three uniforms; the frames are a few hundred line
 * segments rebuilt on the CPU each frame from the per-row readings.
 */

/* eslint-disable react-hooks/immutability -- textures, buffers, uniforms and the label
   divs are scene state written from the frame loop; none of it is React state. */

import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';

const BINS = 256;
const ROWS = 512;
const WIDTH = 64;
const DEPTH = 100;
const HEIGHT = 14;
const F_LO = 40;
const F_HI = 16000;
const SPARKS = 50000;
const SPARK_PERIOD = 3.6;
const STAGE_S = 6;
const NOW_ROWS = 90;
const MAX_EVENTS = 40;
const FRAME_SEGMENTS = 6000;
const LABEL_POOL = 72;

interface Ear {
  analyser: AnalyserNode | null;
  context: AudioContext | null;
  playing: boolean;
  /** Seconds of music heard so far: the sparks' clock; stops when the track does. */
  musicTime: number;
  bass: number;
}

interface LiveEvent { id: number; row: number; time: number; centroid: number; loud: number; flux: number }
interface Stage { index: number; startRow: number; startTime: number; sumLoud: number; sumCentroid: number; n: number }

const TERRAIN_VERTEX = /* glsl */`
attribute float aBin;
attribute float aRow;
uniform sampler2D uField;
uniform float uHead;
uniform float uRows;
uniform float uBins;
uniform float uBass;
uniform float uMusic;
uniform float uPixelRatio;
varying float vAlpha;
varying float vTone;
varying float vBand;
void main() {
  float age = mod(uHead - aRow + uRows, uRows) / uRows;   // 0 = just written, 1 = oldest
  float mag = texture2D(uField, vec2((aBin + 0.5) / uBins, (aRow + 0.5) / uRows)).r;
  float band = aBin / uBins;
  vec3 pos = vec3((band - 0.5) * ${WIDTH.toFixed(1)}, mag * ${HEIGHT.toFixed(1)}, -age * ${DEPTH.toFixed(1)});
  // The past smears: a slow turbulence that grows with age, loud cells most.
  float n1 = sin(aBin * 0.07 + age * 9.0 + uMusic * 0.25);
  float n2 = cos(aBin * 0.13 - age * 7.0 + uMusic * 0.2);
  float n3 = sin(aBin * 0.05 + age * 5.0 - uMusic * 0.15);
  float drift = age * (0.5 + 1.6 * mag);
  pos.x += n1 * drift * 2.2;
  pos.y += (n2 * 0.5 + 0.5) * drift * 3.0 * mag + age * 3.0 * mag;
  pos.z += n3 * drift * 1.5;
  vAlpha = (0.05 + 0.45 * mag) * (1.0 - age * 0.9);
  vTone = mag;
  vBand = band;
  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  gl_PointSize = (0.55 + 1.7 * mag + 0.5 * uBass) * uPixelRatio * (150.0 / -mv.z);
  gl_Position = projectionMatrix * mv;
}
`;

const SPARK_VERTEX = /* glsl */`
attribute float aBand;
attribute float aPhase;
attribute float aSeed;
uniform sampler2D uField;
uniform float uHead;
uniform float uRows;
uniform float uMusic;
uniform float uRate;
uniform float uPixelRatio;
varying float vAlpha;
varying float vTone;
varying float vBand;
void main() {
  float life = fract(uMusic / ${SPARK_PERIOD.toFixed(1)} + aPhase);
  float age = life * ${SPARK_PERIOD.toFixed(1)};
  float rowsBack = age * uRate;
  float row = mod(uHead - rowsBack + uRows * 4.0, uRows);
  float mag = texture2D(uField, vec2(aBand, (row + 0.5) / uRows)).r;
  float strength = smoothstep(0.32, 0.9, mag);
  vec3 birth = vec3((aBand - 0.5) * ${WIDTH.toFixed(1)}, mag * ${HEIGHT.toFixed(1)}, -rowsBack / uRows * ${DEPTH.toFixed(1)});
  vec3 vel = vec3((aSeed - 0.5) * 3.0, 2.5 + 6.0 * mag, (fract(aSeed * 7.31) - 0.5) * 2.5);
  vec3 swirl = vec3(
    sin(age * 2.2 + aSeed * 20.0 + uMusic * 0.3),
    0.4 * sin(age * 3.1 + aSeed * 9.0),
    cos(age * 1.9 + aSeed * 13.0 - uMusic * 0.2)) * 2.4 * age;
  vec3 pos = birth + vel * age + swirl;
  float fade = (1.0 - life) * (1.0 - life);
  vAlpha = strength * fade * 0.38;
  vTone = mag;
  vBand = aBand;
  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  gl_PointSize = (0.7 + 1.8 * strength) * (0.5 + 0.5 * fade) * uPixelRatio * (150.0 / -mv.z);
  gl_Position = projectionMatrix * mv;
}
`;

const FRAGMENT = /* glsl */`
uniform vec3 uWarm;
uniform vec3 uPale;
varying float vAlpha;
varying float vTone;
varying float vBand;
void main() {
  vec2 d = gl_PointCoord - 0.5;
  float r = dot(d, d);
  if (r > 0.25) discard;
  float soft = smoothstep(0.25, 0.03, r);
  vec3 color = mix(uWarm, uPale, sqrt(vBand)) * (0.5 + 0.7 * vTone);
  gl_FragColor = vec4(color, vAlpha * soft);
}
`;

/** The analyser's linear bins → 256 log bins, 30 Hz – 16 kHz, computed once. */
function logRanges(sampleRate: number, fftBins: number): Array<[number, number]> {
  const hzPerBin = sampleRate / 2 / fftBins;
  const ranges: Array<[number, number]> = [];
  for (let k = 0; k < BINS; k += 1) {
    const f0 = F_LO * Math.pow(F_HI / F_LO, k / BINS);
    const f1 = F_LO * Math.pow(F_HI / F_LO, (k + 1) / BINS);
    const i0 = Math.min(fftBins - 1, Math.floor(f0 / hzPerBin));
    const i1 = Math.min(fftBins, Math.max(i0 + 1, Math.ceil(f1 / hzPerBin)));
    ranges.push([i0, i1]);
  }
  return ranges;
}

const hzOfBand = (band: number) => F_LO * Math.pow(F_HI / F_LO, band);
const bandOfHz = (hz: number) => Math.log(hz / F_LO) / Math.log(F_HI / F_LO);
const hzText = (hz: number) => (hz >= 1000 ? (hz / 1000).toFixed(hz >= 10000 ? 0 : 1) + ' kHz' : Math.round(hz) + ' Hz');
const clockText = (seconds: number) => Math.floor(seconds / 60) + ':' + String(Math.floor(seconds % 60)).padStart(2, '0');

interface LabelRequest { text: string; at: THREE.Vector3; kind: string; alpha: number }

const WARM = new THREE.Color('#ffd28a');
const PALE = new THREE.Color('#dbe7ff');

function Scene({ ear, holder }: { ear: RefObject<Ear>; holder: RefObject<HTMLDivElement | null> }) {
  const { camera, size } = useThree();

  // The field: ROWS rows of BINS bytes, the write head walking down it; and beside
  // it the per-row readings the frames are drawn from.
  const field = useMemo(() => ({
    data: new Uint8Array(BINS * ROWS),
    texture: null as THREE.DataTexture | null,
    head: 0, rows: 0,
    ranges: null as Array<[number, number]> | null,
    raw: new Uint8Array(1024),
    prev: new Uint8Array(BINS),
    loud: new Float32Array(ROWS), centroid: new Float32Array(ROWS), thread: new Float32Array(ROWS), flux: new Float32Array(ROWS), time: new Float32Array(ROWS),
    threadPrev: 0.5,
    fluxAvg: 0.02, lastEventRow: -100, eventId: 0,
    events: [] as LiveEvent[], stages: [] as Stage[], nextStageAt: 0,
    ticks: [] as Array<{ second: number; row: number }>, lastSecond: -1,
  }), []);
  const texture = useMemo(() => {
    const t = new THREE.DataTexture(field.data, BINS, ROWS, THREE.RedFormat, THREE.UnsignedByteType);
    t.minFilter = THREE.NearestFilter; t.magFilter = THREE.NearestFilter;
    t.wrapS = THREE.ClampToEdgeWrapping; t.wrapT = THREE.RepeatWrapping;
    t.needsUpdate = true;
    field.texture = t;
    return t;
  }, [field]);
  useEffect(() => () => texture.dispose(), [texture]);

  const terrain = useMemo(() => {
    const n = BINS * ROWS;
    const bin = new Float32Array(n);
    const row = new Float32Array(n);
    for (let r = 0; r < ROWS; r += 1) for (let k = 0; k < BINS; k += 1) { bin[r * BINS + k] = k; row[r * BINS + k] = r; }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    geometry.setAttribute('aBin', new THREE.BufferAttribute(bin, 1));
    geometry.setAttribute('aRow', new THREE.BufferAttribute(row, 1));
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, HEIGHT / 2, -DEPTH / 2), 400);
    return geometry;
  }, []);
  const sparks = useMemo(() => {
    const band = new Float32Array(SPARKS); const phase = new Float32Array(SPARKS); const seed = new Float32Array(SPARKS);
    let s = 3;
    const random = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
    for (let i = 0; i < SPARKS; i += 1) { band[i] = random(); phase[i] = random(); seed[i] = random(); }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(SPARKS * 3), 3));
    geometry.setAttribute('aBand', new THREE.BufferAttribute(band, 1));
    geometry.setAttribute('aPhase', new THREE.BufferAttribute(phase, 1));
    geometry.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1));
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, HEIGHT / 2, -DEPTH / 2), 400);
    return geometry;
  }, []);
  useEffect(() => () => { terrain.dispose(); sparks.dispose(); }, [terrain, sparks]);

  const shared = useMemo(() => ({
    uField: { value: texture }, uHead: { value: 0 }, uRows: { value: ROWS }, uBins: { value: BINS },
    uBass: { value: 0 }, uMusic: { value: 0 }, uRate: { value: 60 }, uPixelRatio: { value: 1 },
    uWarm: { value: WARM }, uPale: { value: new THREE.Color('#cfe4ff') },
  }), [texture]);
  const terrainMaterial = useMemo(() => new THREE.ShaderMaterial({
    uniforms: shared, vertexShader: TERRAIN_VERTEX, fragmentShader: FRAGMENT,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  }), [shared]);
  const sparkMaterial = useMemo(() => new THREE.ShaderMaterial({
    uniforms: shared, vertexShader: SPARK_VERTEX, fragmentShader: FRAGMENT,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  }), [shared]);
  useEffect(() => () => { terrainMaterial.dispose(); sparkMaterial.dispose(); }, [terrainMaterial, sparkMaterial]);

  // The thread: the centroid through the history, a line rebuilt each frame.
  const spine = useMemo(() => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(ROWS * 3), 3));
    geometry.setDrawRange(0, 0);
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, HEIGHT / 2, -DEPTH / 2), 400);
    return geometry;
  }, []);
  const spineMaterial = useMemo(() => new THREE.LineBasicMaterial({ color: WARM, transparent: true, opacity: 0.85, toneMapped: false }), []);
  const spineLine = useMemo(() => { const line = new THREE.Line(spine, spineMaterial); line.frustumCulled = false; return line; }, [spine, spineMaterial]);

  // The frames: crosses, stage boxes, the now box, the ruler — one segment buffer,
  // coloured per vertex, rebuilt each frame.
  const frames = useMemo(() => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(FRAME_SEGMENTS * 6), 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(new Float32Array(FRAME_SEGMENTS * 6), 3));
    geometry.setDrawRange(0, 0);
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, HEIGHT / 2, -DEPTH / 2), 400);
    return geometry;
  }, []);
  const framesMaterial = useMemo(() => new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.9, toneMapped: false }), []);
  useEffect(() => () => { spine.dispose(); spineMaterial.dispose(); frames.dispose(); framesMaterial.dispose(); }, [spine, spineMaterial, frames, framesMaterial]);

  const grid = useMemo(() => {
    const helper = new THREE.GridHelper(280, 112, '#9cc4ff', '#9cc4ff');
    helper.position.set(0, -0.3, -DEPTH / 2);
    const material = helper.material as THREE.LineBasicMaterial;
    material.transparent = true; material.opacity = 0.1; material.toneMapped = false;
    return helper;
  }, []);

  // The captions: a pool of divs in the overlay, handed a fresh list each frame.
  const pool = useRef<HTMLElement[]>([]);
  useEffect(() => {
    const root = holder.current;
    if (!root) return;
    const els: HTMLElement[] = [];
    for (let i = 0; i < LABEL_POOL; i += 1) {
      const el = document.createElement('div');
      el.className = 'lab-label';
      el.style.opacity = '0';
      root.appendChild(el);
      els.push(el);
    }
    pool.current = els;
    return () => { els.forEach((el) => el.remove()); pool.current = []; };
  }, [holder]);

  const scratch = useMemo(() => ({ point: new THREE.Vector3(), labels: [] as LabelRequest[] }), []);

  useFrame(({ gl }, delta) => {
    const live = ear.current;
    const analyser = live.analyser;

    // ---- one row of hearing, and its readings -----------------------------------------
    if (analyser && live.playing) {
      if (!field.ranges || field.raw.length !== analyser.frequencyBinCount) {
        field.raw = new Uint8Array(analyser.frequencyBinCount);
        field.ranges = logRanges(live.context?.sampleRate ?? 44100, analyser.frequencyBinCount);
      }
      analyser.getByteFrequencyData(field.raw);
      const head = field.head;
      const rowStart = head * BINS;
      let bass = 0; let sum = 0; let weighted = 0; let flux = 0;
      for (let k = 0; k < BINS; k += 1) {
        const [i0, i1] = field.ranges[k];
        let peak = 0;
        for (let i = i0; i < i1; i += 1) { if (field.raw[i] > peak) peak = field.raw[i]; }
        field.data[rowStart + k] = peak;
        const v = peak / 255;
        sum += v; weighted += v * k;
        if (peak > field.prev[k]) flux += peak - field.prev[k];
        field.prev[k] = peak;
        if (k < 40) bass += v;
      }
      texture.needsUpdate = true;
      const loud = sum / BINS;
      const centroid = sum > 0 ? weighted / sum / BINS : 0.5;
      const fluxNorm = flux / BINS / 255;
      field.loud[head] = loud; field.centroid[head] = centroid; field.flux[head] = fluxNorm; field.time[head] = live.musicTime;
      field.threadPrev = field.threadPrev * 0.85 + centroid * 0.15;
      field.thread[head] = field.threadPrev;
      field.fluxAvg = field.fluxAvg * 0.96 + fluxNorm * 0.04;
      if (fluxNorm > field.fluxAvg * 1.7 + 0.012 && field.rows - field.lastEventRow >= 8) {
        field.eventId += 1;
        field.events.push({ id: field.eventId, row: head, time: live.musicTime, centroid, loud, flux: fluxNorm });
        if (field.events.length > MAX_EVENTS) field.events.shift();
        field.lastEventRow = field.rows;
      }
      if (live.musicTime >= field.nextStageAt) {
        field.stages.push({ index: field.stages.length + 1 + (field.stages[0]?.index ?? 1) - 1, startRow: head, startTime: live.musicTime, sumLoud: 0, sumCentroid: 0, n: 0 });
        if (field.stages.length > 12) field.stages.shift();
        field.nextStageAt += STAGE_S;
      }
      const stage = field.stages[field.stages.length - 1];
      if (stage) { stage.sumLoud += loud; stage.sumCentroid += centroid; stage.n += 1; }
      const second = Math.floor(live.musicTime);
      if (second !== field.lastSecond) { field.lastSecond = second; field.ticks.push({ second, row: head }); if (field.ticks.length > 120) field.ticks.shift(); }
      shared.uHead.value = head;
      field.head = (head + 1) % ROWS;
      field.rows += 1;
      live.musicTime += delta;
      live.bass = live.bass * 0.8 + (bass / 40) * 0.2;
      shared.uRate.value = field.rows / Math.max(0.5, live.musicTime);
    }
    shared.uBass.value = live.bass;
    shared.uMusic.value = live.musicTime;
    shared.uPixelRatio.value = gl.getPixelRatio();

    // ---- the frames, from the readings -------------------------------------------------
    const written = Math.min(field.rows, ROWS);
    const last = (field.head - 1 + ROWS) % ROWS;
    const ageOf = (row: number) => ((last - row + ROWS) % ROWS) / ROWS;
    const zOf = (row: number) => -ageOf(row) * DEPTH;
    const xOf = (band: number) => (band - 0.5) * WIDTH;

    const spinePos = spine.getAttribute('position') as THREE.BufferAttribute;
    for (let i = 0; i < written; i += 1) {
      const row = (last - i + ROWS) % ROWS;
      spinePos.setXYZ(i, xOf(field.thread[row]), field.loud[row] * HEIGHT * 1.05 + 0.5, -(i / ROWS) * DEPTH);
    }
    spinePos.needsUpdate = true;
    spine.setDrawRange(0, written);

    const pos = frames.getAttribute('position') as THREE.BufferAttribute;
    const col = frames.getAttribute('color') as THREE.BufferAttribute;
    let n = 0;
    const put = (ax: number, ay: number, az: number, bx: number, by: number, bz: number, c: THREE.Color, k: number) => {
      if (n + 2 > FRAME_SEGMENTS * 2) return;
      pos.setXYZ(n, ax, ay, az); col.setXYZ(n, c.r * k, c.g * k, c.b * k); n += 1;
      pos.setXYZ(n, bx, by, bz); col.setXYZ(n, c.r * k, c.g * k, c.b * k); n += 1;
    };
    const box = (x0: number, x1: number, y0: number, y1: number, z0: number, z1: number, c: THREE.Color, k: number) => {
      put(x0, y0, z0, x1, y0, z0, c, k); put(x1, y0, z0, x1, y0, z1, c, k); put(x1, y0, z1, x0, y0, z1, c, k); put(x0, y0, z1, x0, y0, z0, c, k);
      put(x0, y1, z0, x1, y1, z0, c, k); put(x1, y1, z0, x1, y1, z1, c, k); put(x1, y1, z1, x0, y1, z1, c, k); put(x0, y1, z1, x0, y1, z0, c, k);
      put(x0, y0, z0, x0, y1, z0, c, k); put(x1, y0, z0, x1, y1, z0, c, k); put(x1, y0, z1, x1, y1, z1, c, k); put(x0, y0, z1, x0, y1, z1, c, k);
    };
    const labels = scratch.labels;
    labels.length = 0;
    const edge = WIDTH / 2 + 1.5;

    // The frequency scale, in front, and the ruler of seconds along the left edge.
    [50, 100, 300, 1000, 3000, 10000].forEach((hz) => {
      const x = xOf(bandOfHz(hz));
      put(x, -0.2, 1.2, x, -0.2, 2.4, PALE, 0.7);
      labels.push({ text: hzText(hz), at: new THREE.Vector3(x, -0.3, 3.4), kind: 'hz', alpha: 0.8 });
    });
    put(-edge, -0.2, 0, -edge, -0.2, -DEPTH, PALE, 0.5);
    field.ticks.forEach((tick) => {
      if (ageOf(tick.row) > 0.99 || tick.row >= written && field.rows < ROWS) return;
      const z = zOf(tick.row);
      const major = tick.second % 5 === 0;
      put(-edge, -0.2, z, -edge - (major ? 1.6 : 0.7), -0.2, z, PALE, 0.7);
      if (major) labels.push({ text: clockText(tick.second), at: new THREE.Vector3(-edge - 2.2, -0.2, z), kind: 'tick', alpha: 0.85 * (1 - ageOf(tick.row)) });
    });

    // Stage frames: six seconds each, mean readings on the caption.
    field.stages.forEach((stage, i) => {
      const startAge = ageOf(stage.startRow);
      if (startAge > 0.98 && field.rows >= ROWS) return;
      const next = field.stages[i + 1];
      const z0 = zOf(stage.startRow);
      const z1 = next ? zOf(next.startRow) + 0.3 : 0.3;
      const k = 0.85 * Math.max(0, 1 - startAge * 1.1);
      box(-edge, edge, -0.3, HEIGHT + 0.6, z0, z1, PALE, k);
      const meanLoud = stage.n ? stage.sumLoud / stage.n : 0;
      const meanCentroid = stage.n ? stage.sumCentroid / stage.n : 0.5;
      labels.push({
        text: 'stage ' + stage.index + ' (' + stage.startTime.toFixed(1) + ' s)\nloud ' + meanLoud.toFixed(3) + ' · centroid ' + hzText(hzOfBand(meanCentroid)),
        at: new THREE.Vector3(-edge + 0.4, HEIGHT + 0.8, z0), kind: 'stage', alpha: k,
      });
    });

    // The now frame: the last 1.5 s, with the live numbers.
    if (written > 0) {
      const nowRow = (last - Math.min(NOW_ROWS, written - 1) + ROWS) % ROWS;
      box(-edge - 0.4, edge + 0.4, -0.5, HEIGHT + 1.0, zOf(nowRow), 0.6, WARM, 0.95);
      const loud = field.loud[last];
      const centroid = field.centroid[last];
      labels.push({
        text: 'now  ' + clockText(live.musicTime) + '\nloud ' + loud.toFixed(3) + ' · centroid ' + hzText(hzOfBand(centroid)) + ' · flux ' + field.flux[last].toFixed(3),
        at: new THREE.Vector3(-edge + 0.4, HEIGHT + 1.4, 0.6), kind: 'now', alpha: 1,
      });
    }

    // Crosses at the onsets, captioned with their coordinates.
    field.events.forEach((event, i) => {
      const age = ageOf(event.row);
      if (age > 0.97 && field.rows >= ROWS) return;
      const x = xOf(event.centroid);
      const y = HEIGHT + 2.4 + (event.id % 3) * 1.3;
      const z = zOf(event.row);
      const k = Math.max(0, 1 - age * 1.1);
      put(x - 0.8, y, z, x + 0.8, y, z, PALE, k);
      put(x, y - 0.8, z, x, y + 0.8, z, PALE, k);
      put(x, y - 0.8, z, x, event.loud * HEIGHT, z, PALE, k * 0.4);
      if (i >= field.events.length - 6) {
        labels.push({
          text: 'e' + event.id + ' [' + event.time.toFixed(1) + ', ' + Math.round(event.centroid * BINS) + ', ' + event.loud.toFixed(2) + ']',
          at: new THREE.Vector3(x + 1.2, y + 0.3, z), kind: 'event', alpha: k,
        });
      }
    });
    pos.needsUpdate = true;
    col.needsUpdate = true;
    frames.setDrawRange(0, n);

    // ---- the captions -----------------------------------------------------------------
    const els = pool.current;
    for (let i = 0; i < els.length; i += 1) {
      const el = els[i];
      const label = labels[i];
      if (!label) { el.style.opacity = '0'; continue; }
      scratch.point.copy(label.at).project(camera);
      if (scratch.point.z > 1) { el.style.opacity = '0'; continue; }
      if (el.dataset.kind !== label.kind) { el.className = 'lab-label is-' + label.kind; el.dataset.kind = label.kind; }
      if (el.textContent !== label.text) el.textContent = label.text;
      el.style.left = (((scratch.point.x + 1) / 2) * size.width).toFixed(1) + 'px';
      el.style.top = (((1 - scratch.point.y) / 2) * size.height).toFixed(1) + 'px';
      el.style.opacity = label.alpha.toFixed(2);
    }
  });

  return (
    <>
      <color attach="background" args={['#0e2f66']} />
      <primitive object={grid} />
      <points geometry={terrain} material={terrainMaterial} frustumCulled={false} />
      <points geometry={sparks} material={sparkMaterial} frustumCulled={false} />
      <primitive object={spineLine} />
      <lineSegments geometry={frames} material={framesMaterial} frustumCulled={false} />
      <OrbitControls
        target={[0, HEIGHT * 0.4, -DEPTH * 0.28]}
        enableDamping
        dampingFactor={0.08}
        autoRotate
        autoRotateSpeed={0.18}
        minDistance={24}
        maxDistance={240}
        maxPolarAngle={Math.PI * 0.55}
      />
    </>
  );
}

export function LiveSpectrum({ url, name }: { url: string; name: string }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const holder = useRef<HTMLDivElement | null>(null);
  const ear = useRef<Ear>({ analyser: null, context: null, playing: false, musicTime: 0, bass: 0 });
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);

  const toggle = useCallback(async () => {
    const audio = audioRef.current;
    if (!audio) return;
    const live = ear.current;
    if (!live.context) {
      const context = new AudioContext();
      const source = context.createMediaElementSource(audio);
      const analyser = context.createAnalyser();
      analyser.fftSize = 2048;
      analyser.smoothingTimeConstant = 0.5;
      source.connect(analyser);
      analyser.connect(context.destination);
      live.context = context;
      live.analyser = analyser;
    }
    if (audio.paused) {
      await live.context.resume();
      await audio.play();
    } else {
      audio.pause();
    }
  }, []);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const onPlay = () => { ear.current.playing = true; setPlaying(true); };
    const onPause = () => { ear.current.playing = false; setPlaying(false); };
    const onTime = () => setTime(audio.currentTime);
    audio.addEventListener('play', onPlay);
    audio.addEventListener('pause', onPause);
    audio.addEventListener('ended', onPause);
    audio.addEventListener('timeupdate', onTime);
    return () => {
      audio.removeEventListener('play', onPlay);
      audio.removeEventListener('pause', onPause);
      audio.removeEventListener('ended', onPause);
      audio.removeEventListener('timeupdate', onTime);
    };
  }, []);
  useEffect(() => {
    const live = ear.current;
    return () => { void live.context?.close(); };
  }, []);

  return (
    <>
      <Canvas camera={{ position: [40, 26, 58], fov: 36, near: 0.5, far: 1200 }} dpr={[1, 2]} gl={{ antialias: true }}>
        <Scene ear={ear} holder={holder} />
      </Canvas>
      <div ref={holder} className="lab-labels" aria-hidden="true" />
      <audio ref={audioRef} src={url} preload="auto" crossOrigin="anonymous" loop />
      <div className="live-controls">
        <button type="button" className={'topbar-btn' + (playing ? ' is-active' : '')} onClick={() => { void toggle(); }}>
          {playing ? 'Pause' : 'Listen'}
        </button>
        <span className="live-clock">{name} · {clockText(time)}</span>
      </div>
    </>
  );
}
