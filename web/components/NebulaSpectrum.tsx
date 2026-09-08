'use client';

/**
 * The spectrum as a living mass — solid, and pulling on itself.
 *
 * No frames, no box, no captions. A quarter of a million particles fill one body: a
 * GPU simulation (positions and velocities in ping-pong float textures) in which
 * every particle keeps a radial slot of its own inside a ball — so the body stays
 * solid and volume-filling — and eight *cores* live inside it, one per band group of
 * the spectrum, bass to treble. A core drifts slowly on its own orbit; when its bands
 * are loud it moves outward and pulls its particles hard toward it, so the body
 * throws a limb, a knot, a tongue out of itself; when they quieten the springs drag
 * the limb back in. The cores pull against each other, which is the tug: the mass
 * stretches between them and snaps back. An onset in the music throws the whole body
 * outward for a moment, a curl-noise flow keeps its inside moving like a fluid, and
 * damping settles it — a thing breathing and wrestling with itself.
 *
 * Drawn twice, additively: faint small points whose overlap makes the dense body
 * glow from within, and a sparse pass of large soft points for the cores' light.
 * Colour runs from the workbench's pale blue at the surface to its warm accent where
 * the spectrum is loud.
 *
 * The idiom is TouchDesigner's particlesGPU with attractors and a noise force, done
 * here as three shader passes per frame: velocity, position, points.
 */

/* eslint-disable react-hooks/immutability -- render targets, uniforms and the audio
   graph are scene state written from the frame loop; none of it is React state. */

import { Suspense, useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { dimensionLabel } from '../lib/format';
import { Builders, BUILD_X, BUILD_Z, BUILD_HEIGHT, BUILD_BASE_Y, BUILD_START, CLOUD_Z, CLOUD_BACK_Z, CYCLE, FADE_S, TAIL_S, type Show } from './Builders';

const SIZE = 512;
const COUNT = SIZE * SIZE;
const BINS = 256;
const F_LO = 40;
const F_HI = 16000;
const CORES = 14;
const WAVES = 3;
const SURVEY_SEGMENTS = 4000;
const LABEL_POOL = 48;
const SAMPLE = 40;
/** The cloud's angular radius, as a fraction of the distance: it always fills this
 *  much of the view and overflows the frame, whatever it is doing or where it has
 *  withdrawn to. */
const SCREEN_R = 0.5;
const GROUPS = 10;
const BODY = 11.0;

interface Ear {
  analyser: AnalyserNode | null;
  context: AudioContext | null;
  playing: boolean;
  bass: number;
  flux: number;
  fluxAvg: number;
  energy: number;
  treble: number;
  windAngle: number;
  gust: number;
  survey: boolean;
  /** 0 = the camera is on the cloud, 1 = on the building; the survey fades with it. */
  focus: number;
  /** The cloud's own entrance, and the timeline's gate on the survey. */
  appear: number;
  /** The opening breath: one scripted swing so the mass moves in the first seconds. */
  openPulse: number;
  /** How much the draw enlarges the body to hold its size as it withdraws. */
  scale: number;
  surveyGate: number;
  loud: number;
  centroid: number;
  fluxRaw: number;
  events: Array<{ id: number; time: number; at: THREE.Vector3; band: number; level: number }>;
  eventId: number;
  clock: number;
  /** Seconds since the last three onsets, oldest first; 99 = none. */
  waves: number[];
  /** The slow swell: the passage's energy, smoothed over a breath. */
  breath: number;
}

/** A cheap 3D noise from folded sines, and its curl by central differences: a smooth,
 *  divergence-free flow the whole mass follows together. */
const NOISE = /* glsl */`
float n3(vec3 p) {
  return sin(p.x * 1.31 + p.y * 0.57) * 0.5 + sin(p.y * 1.13 - p.z * 0.61) * 0.5
       + sin(p.z * 1.07 + p.x * 0.43) * 0.5 + sin((p.x + p.y + p.z) * 0.71) * 0.35;
}
vec3 potential(vec3 p, float t) {
  return vec3(n3(p + vec3(0.0, t, 0.0)), n3(p + vec3(31.4, 0.0, t * 0.8)), n3(p + vec3(t * 0.6, 62.8, 0.0)));
}
vec3 curl(vec3 p, float t) {
  float e = 0.05;
  vec3 dx = potential(p + vec3(e, 0.0, 0.0), t) - potential(p - vec3(e, 0.0, 0.0), t);
  vec3 dy = potential(p + vec3(0.0, e, 0.0), t) - potential(p - vec3(0.0, e, 0.0), t);
  vec3 dz = potential(p + vec3(0.0, 0.0, e), t) - potential(p - vec3(0.0, 0.0, e), t);
  return vec3(dy.z - dz.y, dz.x - dx.z, dx.y - dy.x) / (2.0 * e);
}
`;

const QUAD_VERTEX = /* glsl */`
varying vec2 vUv;
void main() { vUv = uv; gl_Position = vec4(position, 1.0); }
`;

const INIT_FRAGMENT = /* glsl */`
varying vec2 vUv;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
void main() {
  // Every particle belongs to one band and keeps one radial slot inside the body.
  float band = hash(vUv * 3.1);
  float a = hash(vUv * 7.3) * 6.2832;
  float c = hash(vUv * 5.7) * 2.0 - 1.0;
  float s = sqrt(1.0 - c * c);
  float slot = pow(hash(vUv * 9.1), 0.45) * ${BODY.toFixed(1)};
  vec3 p = vec3(s * cos(a), c, s * sin(a)) * slot;
  gl_FragColor = vec4(p, band);
}
`;

const VELOCITY_FRAGMENT = /* glsl */`
uniform sampler2D uPos;
uniform sampler2D uVel;
uniform sampler2D uSpectrum;
uniform vec3 uCore[${CORES}];
uniform float uCoreEnergy[${CORES}];
uniform float uWave[${WAVES}];
uniform vec3 uAxis;
uniform vec3 uAnchor;
uniform vec3 uWind;
uniform float uGust;
uniform float uTime;
uniform float uDt;
uniform float uBass;
uniform float uTreble;
uniform float uFlux;
uniform float uBreath;
varying vec2 vUv;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
${NOISE}
void main() {
  vec4 P = texture2D(uPos, vUv);
  vec3 p = P.xyz;
  float band = P.w;
  vec3 v = texture2D(uVel, vUv).xyz;
  float e = texture2D(uSpectrum, vec2(band, 0.5)).r;
  // The body leans downwind; its slots are measured from where it has leaned to.
  vec3 lean = uAnchor + uWind * (0.5 + 1.2 * uGust);
  vec3 q = p - lean;
  float r = length(q);
  vec3 dir = q / max(r, 0.001);
  // The body: each particle keeps its own radial slot, so the mass stays solid and
  // full; the slot swells with the passage's energy and pulses with the bass. Held
  // loosely enough to be bent.
  // The body keeps its size whatever the passage: a fixed envelope with only a
  // breath of swell. Loudness goes into the inside — more lobes, more shake — never
  // into the area.
  float slot = pow(hash(vUv * 9.1), 0.45) * ${BODY.toFixed(1)} * (0.94 + 0.12 * uBreath) * (1.0 + 0.05 * uBass);
  // Breathing is a change of shape, not of area: the body draws up tall and narrow
  // when the passage is quiet and settles wide and low when it fills.
  vec3 stretch = vec3(0.68 + 0.45 * uBreath, 1.72 - 0.80 * uBreath, 0.68 + 0.45 * uBreath);
  vec3 body = -(q - dir * slot * length(dir * stretch)) * 2.6;
  // A cage: nothing wanders far outside the envelope, whatever throws it.
  vec3 cage = -dir * max(0.0, r - ${(BODY * 1.22).toFixed(1)}) * 9.0;
  // The wind: a slow-turning direction gusting with the bass, and a wave that travels
  // through the body along it, so the sheets bend in S-curves and flutter — stronger
  // higher up, the way a curtain moves more at its free edge.
  vec3 sideways = normalize(cross(uWind, vec3(0.0, 1.0, 0.0)) + vec3(0.0001));
  float along = dot(p, uWind);
  float across = dot(p, sideways);
  float wave = sin(along * 0.28 - uTime * 1.3 + p.y * 0.18) * 0.65
             + sin(along * 0.8 - uTime * 2.2 + across * 0.3) * 0.35;
  float height = clamp(p.y / ${BODY.toFixed(1)} + 0.5, 0.0, 1.2);
  vec3 gust = (uWind * (0.3 + 0.7 * uGust) + sideways * wave * (3.2 + 4.0 * uGust)) * (0.35 + 0.75 * height)
            + vec3(0.0, wave * 1.2, 0.0);
  vec3 rel = p - uAnchor;
  vec3 hold = vec3(-rel.x * 0.6, -rel.y * 1.2, -rel.z * 0.6);
  // My core: one per band group. Three kinds by turn — a puller, a spinner (its pull
  // has a swirl, so the limb it throws is a vortex), and a pulser (it grips in beats).
  int k = int(floor(band * float(${CORES})));
  vec3 core = uCore[0]; float ce = uCoreEnergy[0];
  for (int i = 1; i < ${CORES}; i++) { if (i == k) { core = uCore[i]; ce = uCoreEnergy[i]; } }
  int kind = k - 3 * (k / 3);
  vec3 toCore = core - p;
  float dc = length(toCore);
  float grip = min(0.9 + 20.0 * ce * ce, 9.0);
  if (kind == 2) grip *= 0.55 + 0.45 * sin(uTime * 6.0 + float(k));
  vec3 pull = toCore / max(dc, 0.5) * (grip * smoothstep(1.2, 5.0, dc) - 2.5 * (1.0 - smoothstep(0.0, 1.6, dc)));
  if (kind == 1) pull += cross(normalize(core + vec3(0.0001)), toCore) * (1.5 + 6.0 * ce) * smoothstep(0.5, 6.0, dc) / max(dc, 1.0);
  // Two octaves of turbulence: the slow one everyone shares, a fine one the treble stirs.
  vec3 flow = (curl(p * 0.07, uTime * 0.3) * (1.6 + 2.5 * uBass + 1.5 * e)
            + curl(p * 0.4 + 7.0, uTime * 0.9) * (0.6 + 5.0 * uTreble) * (0.3 + band)
            + curl(p * 1.1 + vec3(hash(vUv * 3.7) * 9.0), uTime * 1.7) * (1.0 + 7.0 * e + 4.0 * uBreath)) * vec3(0.85, 1.5, 0.85);
  // Torsion: the upper and lower halves turn against each other, slowly reversing.
  vec3 twist = cross(vec3(0.0, 1.0, 0.0), rel) * sin(uTime * 0.3) * 0.5 * (rel.y / ${BODY.toFixed(1)});
  // Heavy bass splits the body into two lobes along a slowly wandering axis.
  float side = dot(dir, uAxis);
  vec3 split = uAxis * sign(side) * smoothstep(0.35, 0.75, uBass) * 1.2 * (0.4 + abs(side));
  // Onsets: a shock ring travels out through the body from the centre.
  vec3 shock = vec3(0.0);
  for (int w = 0; w < ${WAVES}; w++) {
    float age = uWave[w];
    float front = age * 24.0;
    float amp = exp(-age * 2.2) * 26.0;
    float band_ = exp(-pow((r - front) / 2.2, 2.0));
    shock += dir * amp * band_;
  }
  // Treble fizz on the surface.
  vec3 fizz = dir * uTreble * e * smoothstep(0.7, 1.0, r / max(slot, 0.1)) * 3.5 * (hash(vUv * 21.3 + floor(uTime * 7.0)) - 0.5);
  // The climax is felt as agitation: every particle trembles with its own band.
  float tick = floor(uTime * 9.0);
  vec3 shake = (vec3(hash(vUv * 31.7 + tick), hash(vUv * 57.1 + tick), hash(vUv * 83.3 + tick)) - 0.5)
             * (1.2 + 16.0 * e) * (0.25 + uBreath);
  v += (body + cage + pull + flow + twist + split + shock + fizz + shake + gust + hold) * uDt;
  v *= 1.0 - 1.5 * uDt;
  gl_FragColor = vec4(v, 1.0);
}
`;

const POSITION_FRAGMENT = /* glsl */`
uniform sampler2D uPos;
uniform sampler2D uVel;
uniform float uDt;
varying vec2 vUv;
void main() {
  vec4 P = texture2D(uPos, vUv);
  vec3 v = texture2D(uVel, vUv).xyz;
  gl_FragColor = vec4(P.xyz + v * uDt, P.w);
}
`;

const POINT_VERTEX = /* glsl */`
attribute vec2 aUv;
uniform sampler2D uPos;
uniform sampler2D uVel;
uniform sampler2D uSpectrum;
uniform float uPixelRatio;
uniform float uGlow;
uniform vec3 uCentre;
uniform float uRadius;
uniform float uScale;
varying float vEnergy;
varying float vBand;
varying float vSpeed;
varying float vGlow;
varying float vCore;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
void main() {
  vec4 P = texture2D(uPos, aUv);
  vec3 v = texture2D(uVel, aUv).xyz;
  float band = P.w;
  float e = texture2D(uSpectrum, vec2(band, 0.5)).r;
  float h = hash(aUv * 11.7);
  float glow = uGlow > 0.5 ? step(0.94, h) : 1.0;   // the glow pass draws only a sparse few
  vEnergy = e;
  vBand = band;
  vSpeed = length(v);
  vGlow = uGlow;
  // How deep in the body this particle sits: the relief the eye reads as density.
  vec3 rel = P.xyz - uCentre;
  vCore = 1.0 - smoothstep(0.05, 1.30, length(rel) / max(uRadius, 0.001));
  // Held at one size on screen: as it withdraws it is drawn larger by exactly the
  // ratio of the distances, which the springs could never have chased in time.
  vec3 shown = uCentre + rel * uScale;
  vec4 mv = modelViewMatrix * vec4(shown, 1.0);
  float base = (uGlow > 0.5 ? (3.5 + 6.0 * e) : (0.6 + 0.7 * e + 0.4 * h)) * (0.82 + 0.45 * vCore);
  gl_PointSize = min(base * glow * uPixelRatio * (150.0 / -mv.z), 6.0 * uPixelRatio);
  gl_Position = projectionMatrix * mv;
}
`;

const POINT_FRAGMENT = /* glsl */`
uniform vec3 uLow;
uniform vec3 uMid;
uniform vec3 uHigh;
uniform vec3 uHot;
uniform float uFocus;
uniform float uAppear;
varying float vEnergy;
varying float vBand;
varying float vSpeed;
varying float vGlow;
varying float vCore;
void main() {
  vec2 d = gl_PointCoord - 0.5;
  float r = dot(d, d);
  if (r > 0.25) discard;
  float soft = vGlow > 0.5 ? pow(1.0 - r * 4.0, 2.2) : smoothstep(0.25, 0.04, r);
  // Aurora: green at the bass, cyan through the mids, violet at the treble, and a
  // warm white where the spectrum is hot.
  vec3 tint = mix(mix(uLow, uMid, smoothstep(0.0, 0.5, vBand)), uHigh, smoothstep(0.5, 1.0, vBand));
  // Depth in the body lifts both the colour and the weight, so the dense parts stand
  // out of the haze instead of everything reading as one flat veil.
  vec3 color = mix(tint, uHot, smoothstep(0.75, 1.0, vEnergy) * 0.22 + 0.2 * vCore * vCore)
             * (0.22 + 0.8 * vEnergy + 0.04 * vSpeed) * (0.62 + 0.8 * vCore);
  float alpha = (vGlow > 0.5 ? 0.0012 + 0.003 * vEnergy : 0.028 + 0.05 * vEnergy) * (1.0 - 0.55 * uFocus) * uAppear * (0.55 + 0.9 * vCore * vCore);
  gl_FragColor = vec4(color, alpha * soft);
}
`;

/** The feedback: last frame, faded towards the ground colour, is the bed the new
 *  frame is drawn on — so every particle leaves a ribbon. */
const FADE_FRAGMENT = /* glsl */`
uniform sampler2D uPrev;
uniform vec3 uGround;
uniform float uFade;
varying vec2 vUv;
void main() {
  vec3 prev = texture2D(uPrev, vUv).rgb;
  gl_FragColor = vec4(mix(uGround, prev, uFade), 1.0);
}
`;

const PRESENT_FRAGMENT = /* glsl */`
uniform sampler2D uFrame;
uniform vec2 uTexel;
varying vec2 vUv;
void main() {
  // A five-tap softening and a soft shoulder, so the bright ribbons bloom instead of clip.
  vec3 c = texture2D(uFrame, vUv).rgb;
  vec3 ground = vec3(0.016, 0.051, 0.141);
  vec3 lift = max(c - ground, 0.0);
  vec3 shaped = lift / (1.0 + lift) * 0.95;
  gl_FragColor = vec4(ground + shaped, 1.0);
}
`;

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

function makeTarget() {
  return new THREE.WebGLRenderTarget(SIZE, SIZE, {
    type: THREE.FloatType, format: THREE.RGBAFormat,
    minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter,
    depthBuffer: false, stencilBuffer: false, generateMipmaps: false,
  });
}

export interface Dimension { id: string; value: number }

function Mass({ ear, holder, dimensions, building, show }: { ear: RefObject<Ear>; holder: RefObject<HTMLDivElement | null>; dimensions: Dimension[]; building: boolean; show: { current: Show } }) {
  const { size, gl: renderer, scene, camera } = useThree();
  const controls = useThree((state) => state.controls) as unknown as { target: THREE.Vector3 } | null;
  // The feedback: two screen-sized targets, last frame faded under this one.
  const feedback = useMemo(() => {
    const dpr = renderer.getPixelRatio();
    const width = Math.max(2, Math.floor(size.width * dpr));
    const height = Math.max(2, Math.floor(size.height * dpr));
    const make = () => new THREE.WebGLRenderTarget(width, height, {
      type: THREE.HalfFloatType, format: THREE.RGBAFormat,
      minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, depthBuffer: false, stencilBuffer: false,
    });
    const quadScene = new THREE.Scene();
    const quadCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const fade = new THREE.ShaderMaterial({
      vertexShader: QUAD_VERTEX, fragmentShader: FADE_FRAGMENT, depthTest: false, depthWrite: false,
      uniforms: { uPrev: { value: null }, uGround: { value: new THREE.Color('#040d24') }, uFade: { value: 0.9 } },
    });
    const present = new THREE.ShaderMaterial({
      vertexShader: QUAD_VERTEX, fragmentShader: PRESENT_FRAGMENT, depthTest: false, depthWrite: false,
      uniforms: { uFrame: { value: null }, uTexel: { value: new THREE.Vector2(1 / width, 1 / height) } },
    });
    const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), fade);
    quadScene.add(quad);
    return { targets: [make(), make()], quadScene, quadCamera, quad, fade, present, swap: 0 };
  }, [renderer, size.width, size.height]);
  useEffect(() => () => {
    feedback.targets.forEach((t) => t.dispose()); feedback.fade.dispose(); feedback.present.dispose(); feedback.quad.geometry.dispose();
  }, [feedback]);

  // The survey: its own scene, drawn crisp over the presented picture so it never
  // smears — a grid behind, scales on the edges, and a segment buffer rebuilt each
  // frame for the core boxes, the onset crosses and the net to the readouts.
  const survey = useMemo(() => {
    const sceneS = new THREE.Scene();
    const grid = new THREE.GridHelper(200, 50, '#9cc4ff', '#9cc4ff');
    grid.rotation.x = Math.PI / 2;
    grid.position.set(0, 0, -26);
    const gm = grid.material as THREE.LineBasicMaterial;
    gm.transparent = true; gm.opacity = 0.07; gm.toneMapped = false; gm.depthTest = false;
    sceneS.add(grid);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(SURVEY_SEGMENTS * 6), 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(new Float32Array(SURVEY_SEGMENTS * 6), 3));
    geometry.setDrawRange(0, 0);
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 400);
    const material = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.9, toneMapped: false, depthTest: false });
    const lines = new THREE.LineSegments(geometry, material);
    lines.frustumCulled = false;
    sceneS.add(lines);
    const readouts = [
      { key: 'loud', at: new THREE.Vector3(-17, 16.5, 0) },
      { key: 'centroid', at: new THREE.Vector3(-6, 18, 0) },
      { key: 'flux', at: new THREE.Vector3(6, 18, 0) },
      { key: 'bass', at: new THREE.Vector3(17, 16.5, 0) },
    ];
    return {
      scene: sceneS, grid, geometry, material, lines, readouts,
      pale: new THREE.Color('#dbe7ff'), warm: new THREE.Color('#ffd28a'),
      labels: [] as Array<{ text: string; at: THREE.Vector3; kind: string; alpha: number }>, point: new THREE.Vector3(),
    };
  }, []);
  useEffect(() => () => { survey.geometry.dispose(); survey.material.dispose(); }, [survey]);

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
    const tagEls: HTMLElement[] = [];
    for (let i = 0; i < GROUPS; i += 1) {
      const el = document.createElement('div');
      el.className = 'survey-tag';
      el.style.opacity = '0';
      root.appendChild(el);
      tagEls.push(el);
    }
    tags.current = tagEls;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'survey-net');
    const edges: SVGLineElement[] = [];
    for (let i = 0; i < 64; i += 1) {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('visibility', 'hidden');
      svg.appendChild(line);
      edges.push(line);
    }
    root.appendChild(svg);
    net.current = edges;
    return () => { els.forEach((el) => el.remove()); tagEls.forEach((el) => el.remove()); svg.remove(); pool.current = []; tags.current = []; net.current = []; };
  }, [holder]);
  const net = useRef<SVGLineElement[]>([]);
  const tags = useRef<HTMLElement[]>([]);
  // A small read-back of the simulation each frame — SAMPLE × SAMPLE particles, their
  // bands in the alpha channel — so the boxes can frame where the cloud actually is.
  const sample = useMemo(() => ({
    buffer: new Float32Array(SAMPLE * SAMPLE * 4),
    xs: Array.from({ length: GROUPS }, () => [] as number[]),
    ys: Array.from({ length: GROUPS }, () => [] as number[]),
    near: Array.from({ length: GROUPS }, () => [] as Array<[number, number, number]>),
    knot: new THREE.Vector3(),
    boxes: Array.from({ length: GROUPS }, () => ({ x0: 0, y0: 0, x1: 0, y1: 0, seen: false })),
    vis: new Float32Array(GROUPS),
    centre: new THREE.Vector3(),
    radii: [] as number[],
    distance: 24,
    refRadius: 0,
    point: new THREE.Vector3(),
  }), []);

  // The spectrum the simulation reads: 256 bands, one row, refreshed every frame.
  const spectrum = useMemo(() => {
    const data = new Uint8Array(BINS);
    const texture = new THREE.DataTexture(data, BINS, 1, THREE.RedFormat, THREE.UnsignedByteType);
    texture.minFilter = THREE.LinearFilter; texture.magFilter = THREE.LinearFilter;
    texture.needsUpdate = true;
    return { data, texture, raw: new Uint8Array(1024), prev: new Uint8Array(BINS), ranges: null as Array<[number, number]> | null };
  }, []);

  // The simulation: a quad, an orthographic camera, three materials, two ping-pongs.
  const sim = useMemo(() => {
    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const geometry = new THREE.PlaneGeometry(2, 2);
    const init = new THREE.ShaderMaterial({ vertexShader: QUAD_VERTEX, fragmentShader: INIT_FRAGMENT, depthTest: false, depthWrite: false });
    const velocity = new THREE.ShaderMaterial({
      vertexShader: QUAD_VERTEX, fragmentShader: VELOCITY_FRAGMENT, depthTest: false, depthWrite: false,
      uniforms: {
        uPos: { value: null }, uVel: { value: null }, uSpectrum: { value: spectrum.texture },
        uTime: { value: 0 }, uDt: { value: 1 / 60 }, uBass: { value: 0 }, uFlux: { value: 0 }, uBreath: { value: 0 },
        uCore: { value: Array.from({ length: CORES }, () => new THREE.Vector3()) },
        uCoreEnergy: { value: new Float32Array(CORES) },
        uWave: { value: new Float32Array(WAVES).fill(99) },
        uAxis: { value: new THREE.Vector3(0, 1, 0) },
        uAnchor: { value: new THREE.Vector3() },
        uWind: { value: new THREE.Vector3(1, 0, 0) },
        uGust: { value: 0 },
        uTreble: { value: 0 },
      },
    });
    const position = new THREE.ShaderMaterial({
      vertexShader: QUAD_VERTEX, fragmentShader: POSITION_FRAGMENT, depthTest: false, depthWrite: false,
      uniforms: { uPos: { value: null }, uVel: { value: null }, uDt: { value: 1 / 60 } },
    });
    const mesh = new THREE.Mesh(geometry, init);
    scene.add(mesh);
    return {
      scene, camera, mesh, init, velocity, position,
      pos: [makeTarget(), makeTarget()], vel: [makeTarget(), makeTarget()],
      ready: false, swap: 0,
    };
  }, [spectrum]);
  useEffect(() => () => {
    sim.pos.forEach((t) => t.dispose()); sim.vel.forEach((t) => t.dispose());
    sim.init.dispose(); sim.velocity.dispose(); sim.position.dispose(); sim.mesh.geometry.dispose();
    spectrum.texture.dispose();
  }, [sim, spectrum]);

  // The points: one per texel, addressed by its uv.
  const cloud = useMemo(() => {
    const uv = new Float32Array(COUNT * 2);
    for (let i = 0; i < COUNT; i += 1) {
      uv[i * 2] = ((i % SIZE) + 0.5) / SIZE;
      uv[i * 2 + 1] = (Math.floor(i / SIZE) + 0.5) / SIZE;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(COUNT * 3), 3));
    geometry.setAttribute('aUv', new THREE.BufferAttribute(uv, 2));
    geometry.setDrawRange(0, Math.floor(COUNT * 0.72));
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 200);
    const uniforms = {
      uPos: { value: null as THREE.Texture | null }, uVel: { value: null as THREE.Texture | null },
      uSpectrum: { value: spectrum.texture }, uPixelRatio: { value: 1 }, uGlow: { value: 0 },
      uLow: { value: new THREE.Color('#c9a6ec') }, uMid: { value: new THREE.Color('#9fc0ff') },
      uHigh: { value: new THREE.Color('#e4d8ff') }, uHot: { value: new THREE.Color('#dfe6ff') }, uFocus: { value: 0 }, uAppear: { value: 1 },
      uCentre: { value: new THREE.Vector3(0, 0, CLOUD_Z) }, uRadius: { value: BODY }, uScale: { value: 1 },
    };
    const points = new THREE.ShaderMaterial({
      uniforms, vertexShader: POINT_VERTEX, fragmentShader: POINT_FRAGMENT,
      transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending,
    });
    const glow = new THREE.ShaderMaterial({
      uniforms: { ...uniforms, uGlow: { value: 1 } }, vertexShader: POINT_VERTEX, fragmentShader: POINT_FRAGMENT,
      transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending,
    });
    return { geometry, points, glow, uniforms };
  }, [spectrum]);
  useEffect(() => () => { cloud.geometry.dispose(); cloud.points.dispose(); cloud.glow.dispose(); }, [cloud]);

  useFrame(({ gl, clock }, delta) => {
    const live = ear.current;
    const dt = Math.min(delta, 1 / 30);

    // ---- the ear: one spectrum, decaying to silence when the track is paused --------
    const analyser = live.analyser;
    if (analyser && live.playing) {
      if (!spectrum.ranges || spectrum.raw.length !== analyser.frequencyBinCount) {
        spectrum.raw = new Uint8Array(analyser.frequencyBinCount);
        spectrum.ranges = logRanges(live.context?.sampleRate ?? 44100, analyser.frequencyBinCount);
      }
      analyser.getByteFrequencyData(spectrum.raw);
      let bass = 0; let energy = 0; let flux = 0; let treble = 0; let weighted = 0;
      for (let k = 0; k < BINS; k += 1) {
        const [i0, i1] = spectrum.ranges[k];
        let peak = 0;
        for (let i = i0; i < i1; i += 1) { if (spectrum.raw[i] > peak) peak = spectrum.raw[i]; }
        spectrum.data[k] = peak;
        if (peak > spectrum.prev[k]) flux += peak - spectrum.prev[k];
        spectrum.prev[k] = peak;
        energy += peak;
        weighted += peak * k;
        if (k < 40) bass += peak;
        if (k >= 170) treble += peak;
      }
      const fluxNorm = flux / BINS / 255;
      live.fluxAvg = live.fluxAvg * 0.96 + fluxNorm * 0.04;
      live.flux = Math.max(0, fluxNorm - live.fluxAvg * 1.3);
      live.bass = live.bass * 0.75 + (bass / 40 / 255) * 0.25;
      live.treble = live.treble * 0.6 + (treble / (BINS - 170) / 255) * 0.4;
      if (live.flux > 0.02 && live.waves[WAVES - 1] > 0.35) {
        live.waves.shift(); live.waves.push(0);
        live.eventId += 1;
        live.events.push({ id: live.eventId, time: live.clock, at: new THREE.Vector3(), band: live.centroid, level: live.energy });
        if (live.events.length > 24) live.events.shift();
      }
      live.energy = energy / BINS / 255;
      live.loud = live.energy;
      live.centroid = energy > 0 ? weighted / energy / BINS : 0.5;
      live.fluxRaw = fluxNorm;
      live.breath = live.breath * 0.8 + live.energy * 0.2;
    } else {
      for (let k = 0; k < BINS; k += 1) spectrum.data[k] = Math.floor(spectrum.data[k] * 0.92);
      live.flux *= 0.8; live.bass *= 0.95; live.energy *= 0.95; live.breath *= 0.97; live.treble *= 0.9;
    }
    spectrum.texture.needsUpdate = true;

    // ---- the simulation: init once, then velocity and position, ping-pong ----------
    const previous = gl.getRenderTarget();
    if (!sim.ready) {
      sim.mesh.material = sim.init;
      [sim.pos[0], sim.pos[1]].forEach((target) => { gl.setRenderTarget(target); gl.render(sim.scene, sim.camera); });
      sim.ready = true;
    }
    const read = sim.swap;
    const write = 1 - sim.swap;
    sim.velocity.uniforms.uPos.value = sim.pos[read].texture;
    sim.velocity.uniforms.uVel.value = sim.vel[read].texture;
    sim.velocity.uniforms.uTime.value = clock.getElapsedTime();
    sim.velocity.uniforms.uDt.value = dt;
    sim.velocity.uniforms.uBass.value = live.bass;
    sim.velocity.uniforms.uFlux.value = live.flux;
    // A floor under the breath: even a quiet passage holds the body in a shape, so the
    // first bar already shows it move.
    sim.velocity.uniforms.uBreath.value = Math.min(1, 0.32 + 1.5 * live.breath + live.openPulse);
    sim.velocity.uniforms.uTreble.value = live.treble;
    for (let w = 0; w < WAVES; w += 1) live.waves[w] = Math.min(99, live.waves[w] + dt);
    (sim.velocity.uniforms.uWave.value as Float32Array).set(live.waves);
    live.windAngle += dt * (0.18 + 0.5 * live.bass);
    live.gust = live.gust * 0.9 + (live.bass * 0.8 + live.flux * 6.0) * 0.1;
    (sim.velocity.uniforms.uWind.value as THREE.Vector3).set(Math.cos(live.windAngle), 0, Math.sin(live.windAngle));
    sim.velocity.uniforms.uGust.value = Math.min(1.5, live.gust);
    // The cloud keeps its size on screen: as the building takes the foreground it
    // withdraws in depth and grows in the world by exactly as much, so it recedes
    // without shrinking — only its presence drops.
    const anchor = sim.velocity.uniforms.uAnchor.value as THREE.Vector3;
    anchor.set(0, 0, building ? CLOUD_Z + (CLOUD_BACK_Z - CLOUD_Z) * live.focus : 0);
    cloud.uniforms.uScale.value = live.scale;
    const axisT = clock.getElapsedTime() * 0.3;
    (sim.velocity.uniforms.uAxis.value as THREE.Vector3).set(Math.sin(axisT) * 0.8, Math.cos(axisT * 0.7), Math.sin(axisT * 0.5) * 0.6).normalize();
    // The cores: one per band group, each on its own slow orbit inside the body,
    // pushed outward by its group's loudness — the limbs the body throws.
    const cores = sim.velocity.uniforms.uCore.value as THREE.Vector3[];
    const coreEnergy = sim.velocity.uniforms.uCoreEnergy.value as Float32Array;
    const t = clock.getElapsedTime();
    for (let k = 0; k < CORES; k += 1) {
      let sum = 0;
      const b0 = Math.floor((k / CORES) * BINS);
      const b1 = Math.floor(((k + 1) / CORES) * BINS);
      for (let b = b0; b < b1; b += 1) sum += spectrum.data[b];
      const energy = sum / Math.max(1, b1 - b0) / 255;
      coreEnergy[k] = coreEnergy[k] * 0.45 + energy * 0.55;
      const speed = 0.2 + 0.08 * k;
      const theta = k * 2.399 + t * speed;
      const phi = Math.sin(t * (0.2 + 0.08 * k) + k) * 0.9;
      const reach = BODY * (0.12 + 0.5 * Math.pow(coreEnergy[k], 0.7));
      cores[k].set(Math.cos(theta) * Math.cos(phi) * reach, Math.sin(phi) * reach, Math.sin(theta) * Math.cos(phi) * reach);
    }
    sim.mesh.material = sim.velocity;
    gl.setRenderTarget(sim.vel[write]);
    gl.render(sim.scene, sim.camera);
    sim.position.uniforms.uPos.value = sim.pos[read].texture;
    sim.position.uniforms.uVel.value = sim.vel[write].texture;
    sim.position.uniforms.uDt.value = dt;
    sim.mesh.material = sim.position;
    gl.setRenderTarget(sim.pos[write]);
    gl.render(sim.scene, sim.camera);
    gl.setRenderTarget(previous);
    sim.swap = write;

    cloud.uniforms.uPos.value = sim.pos[write].texture;
    cloud.uniforms.uVel.value = sim.vel[write].texture;
    cloud.uniforms.uPixelRatio.value = gl.getPixelRatio();
    cloud.uniforms.uFocus.value = live.focus;
    cloud.uniforms.uAppear.value = live.appear;
    (cloud.uniforms.uCentre.value as THREE.Vector3).copy(sim.velocity.uniforms.uAnchor.value as THREE.Vector3);
    cloud.uniforms.uRadius.value = BODY * 1.1;
    cloud.glow.uniforms.uPos.value = sim.pos[write].texture;
    cloud.glow.uniforms.uVel.value = sim.vel[write].texture;
    cloud.glow.uniforms.uPixelRatio.value = gl.getPixelRatio();

    // ---- the picture: last frame faded, this frame drawn on it, then presented ---
    const fb = feedback;
    const readFb = fb.swap;
    const writeFb = 1 - fb.swap;
    fb.fade.uniforms.uPrev.value = fb.targets[readFb].texture;
    fb.fade.uniforms.uFade.value = 0.06 + 0.08 * Math.min(1, live.breath * 2.0);
    fb.quad.material = fb.fade;
    gl.setRenderTarget(fb.targets[writeFb]);
    gl.autoClear = true;
    gl.render(fb.quadScene, fb.quadCamera);
    gl.autoClear = false;
    gl.render(scene, camera);
    gl.autoClear = true;
    fb.present.uniforms.uFrame.value = fb.targets[writeFb].texture;
    fb.quad.material = fb.present;
    gl.setRenderTarget(null);
    gl.render(fb.quadScene, fb.quadCamera);
    fb.swap = writeFb;

    // ---- the frames: one per translated dimension, around the part of the cloud its
    // band group occupies — read back from the simulation, trimmed to the middle of
    // the spread, smoothed so they do not jitter --------------------------------------
    live.clock += dt;
    const els = pool.current;
    const nodes: Array<{ k: number; x: number; y: number; e: number; hw: number; hh: number }> = [];
    let used = 0;
    const surveyShow = live.survey ? live.surveyGate : 0;
    if (sim.ready) {
      gl.readRenderTargetPixels(sim.pos[write], 0, 0, SAMPLE, SAMPLE, sample.buffer);
      for (let g = 0; g < GROUPS; g += 1) { sample.xs[g].length = 0; sample.ys[g].length = 0; }
      // The camera follows the cloud: its sampled centre, eased, is the orbit target.
      sample.centre.set(0, 0, 0);
      for (let i = 0; i < SAMPLE * SAMPLE; i += 1) {
        sample.centre.x += sample.buffer[i * 4]; sample.centre.y += sample.buffer[i * 4 + 1]; sample.centre.z += sample.buffer[i * 4 + 2];
      }
      sample.centre.multiplyScalar(1 / (SAMPLE * SAMPLE));
      show.current.centre.copy(sample.centre);
      if (controls) controls.target.lerp(sample.centre, 0.04);
      // And keeps its distance so the cloud fills about three quarters of the frame,
      // quiet or loud: the 85th-percentile radius sets it, eased.
      sample.radii.length = 0;
      for (let i = 0; i < SAMPLE * SAMPLE; i += 1) {
        const dx = sample.buffer[i * 4] - sample.centre.x; const dy = sample.buffer[i * 4 + 1] - sample.centre.y; const dz = sample.buffer[i * 4 + 2] - sample.centre.z;
        sample.radii.push(Math.sqrt(dx * dx + dy * dy + dz * dz));
      }
      sample.radii.sort((a, b) => a - b);
      const radius = sample.radii[Math.floor(sample.radii.length * 0.92)] ?? 8;
      // Hold the cloud at one angular size: whatever the body is doing and however far
      // it has withdrawn, the draw is enlarged so it subtends the same half-angle.
      const camDist = camera.position.distanceTo(sim.velocity.uniforms.uAnchor.value as THREE.Vector3);
      const target = Math.min(14, Math.max(0.4, (SCREEN_R * camDist) / Math.max(1, radius)));
      live.scale += (target - live.scale) * 0.09;
      // The framing the cloud asks for, remembered while it is the subject so that its
      // own growth as it withdraws cannot feed back into the camera.
      if (sample.refRadius === 0) sample.refRadius = radius;
      if (live.focus < 0.05) sample.refRadius += (radius - sample.refRadius) * 0.05;
      // Close enough that the cloud overflows the frame: it is the subject, not a speck.
      let wanted = Math.min(60, Math.max(17, sample.refRadius * 2.4));
      let focus = 0;
      let appear = 1;
      let surveyIn = 1;
      if (building && controls) {
        // The cycle has acts. 0–3.5 s: the cloud gathers, alone. 3.5–5 s: the survey
        // reads it. 5–10 s: both hold. From 10 s the cloud recedes into the background
        // and the building grows in front of the dark. At the end everything returns.
        // The cycle starts when the listener does, not when the page loaded — so the
        // opening act is always the opening act.
        if (live.playing && show.current.start === null) show.current.start = clock.getElapsedTime();
        const local = show.current.start === null ? 0 : (clock.getElapsedTime() - show.current.start) % CYCLE;
        const ease = (a: number, b: number, x: number) => { const k = Math.min(1, Math.max(0, (x - a) / (b - a))); return k * k * (3 - 2 * k); };
        // The building's own fade window; the cloud comes back as it goes.
        const back = 1 - ease(CYCLE - FADE_S, CYCLE - TAIL_S, local);
        // The cloud is the thing that opens and closes the cycle: it gathers over the
        // first three seconds, holds the stage alone once the building has gone, and
        // only breathes out in the last second so the loop has no seam.
        appear = ease(0.15, 1.6, local) * (1 - ease(CYCLE - 1.0, CYCLE - 0.1, local));
        // One deliberate breath as it arrives: whatever the passage is doing, the body
        // draws in and swells out once inside the first three seconds.
        live.openPulse = Math.sin(Math.min(1, Math.max(0, (local - 0.35) / 2.1)) * Math.PI) * 0.62;
        surveyIn = ease(2.2, 6.0, local);
        focus = ease(BUILD_START, BUILD_START + 4, local) * back;
        // One axis, two planes: the camera only tilts and pushes a little; the exchange
        // is the cloud receding and the building emerging behind it.
        const buildCentre = new THREE.Vector3(BUILD_X, BUILD_BASE_Y + BUILD_HEIGHT / 2 - 3, BUILD_Z);
        const aim = sample.centre.clone().setZ(CLOUD_Z).lerp(buildCentre, focus * 0.85);
        controls.target.lerp(aim, 0.05);
        wanted = wanted * (1 - focus) + 64 * focus;
      }
      live.focus = focus;
      live.appear = show.current.start === null ? 1 : appear;
      show.current.focus = focus;
      live.surveyGate = show.current.start === null ? 1 : surveyIn * (1 - focus);
      sample.distance += (wanted - sample.distance) * 0.03;
      if (controls) {
        const offset = camera.position.clone().sub(controls.target);
        camera.position.copy(controls.target).add(offset.setLength(sample.distance));
      }
      for (let i = 0; i < SAMPLE * SAMPLE; i += 1) {
        const band = sample.buffer[i * 4 + 3];
        const g = Math.min(GROUPS - 1, Math.floor(band * GROUPS));
        sample.point.set(sample.buffer[i * 4], sample.buffer[i * 4 + 1], sample.buffer[i * 4 + 2])
          .sub(sample.centre).multiplyScalar(live.scale).add(sample.centre).project(camera);
        if (sample.point.z > 1) continue;
        sample.xs[g].push(((sample.point.x + 1) / 2) * size.width);
        sample.ys[g].push(((1 - sample.point.y) / 2) * size.height);
      }
      const pick = (arr: number[], q: number) => arr[Math.min(arr.length - 1, Math.max(0, Math.floor(q * arr.length)))];
      const coresNow = sim.velocity.uniforms.uCore.value as THREE.Vector3[];
      const lean = (sim.velocity.uniforms.uWind.value as THREE.Vector3).clone().multiplyScalar(0.5 + 1.2 * Math.min(1.5, live.gust));
      const loudness: number[] = [];
      for (let g = 0; g < GROUPS; g += 1) {
        let sum = 0;
        const k0 = Math.floor((g / GROUPS) * BINS); const k1 = Math.floor(((g + 1) / GROUPS) * BINS);
        for (let k = k0; k < k1; k += 1) sum += spectrum.data[k];
        loudness.push(sum / Math.max(1, k1 - k0) / 255);
      }
      // A frame is never switched on: each one fades to its place over a second or so,
      // and fades out the same way when its band goes quiet.
      const loudest = new Set(loudness.map((e, g) => [e, g] as [number, number]).sort((a, b) => b[0] - a[0])
        .slice(0, 5).filter(([e]) => e > 0.16).map(([, g]) => g));
      for (let g = 0; g < GROUPS; g += 1) {
        sample.vis[g] += ((loudest.has(g) ? 1 : 0) - sample.vis[g]) * 0.045;
      }
      const placed: Array<{ x0: number; x1: number; y0: number; y1: number }> = [];
      const cloudPx = (radius / sample.distance) * (size.height / (2 * Math.tan((38 / 2) * Math.PI / 180))) * 2;

      for (let g = 0; surveyShow > 0.01 && g < GROUPS && used < els.length; g += 1) {
        if (sample.vis[g] < 0.02 || sample.xs[g].length < 6) continue;
        // The group's knot: where its core has gathered it. Box the half of the group's
        // particles nearest that knot, trimmed — a real part of the cloud, not its middle.
        const core = coresNow[Math.min(CORES - 1, Math.floor(((g + 0.5) / GROUPS) * CORES))];
        sample.knot.copy(core).multiplyScalar(0.55).add(lean.clone().multiplyScalar(0.45))
          .multiplyScalar(live.scale).add(sim.velocity.uniforms.uAnchor.value as THREE.Vector3).project(camera);
        const kx = ((sample.knot.x + 1) / 2) * size.width;
        const ky = ((1 - sample.knot.y) / 2) * size.height;
        const near = sample.near[g];
        near.length = 0;
        for (let i = 0; i < sample.xs[g].length; i += 1) {
          const dx = sample.xs[g][i] - kx; const dy = sample.ys[g][i] - ky;
          near.push([dx * dx + dy * dy, sample.xs[g][i], sample.ys[g][i]]);
        }
        near.sort((a, b) => a[0] - b[0]);
        const keep = Math.max(4, Math.floor(near.length * 0.3));
        const xs = near.slice(0, keep).map((n) => n[1]).sort((a, b) => a - b);
        const ys = near.slice(0, keep).map((n) => n[2]).sort((a, b) => a - b);
        const target = { x0: pick(xs, 0.15), x1: pick(xs, 0.85), y0: pick(ys, 0.15), y1: pick(ys, 0.85) };
        // Never larger than a fifth of the cloud's own extent on screen.
        const cap = Math.max(40, cloudPx * 0.2);
        const cx = (target.x0 + target.x1) / 2; const cy = (target.y0 + target.y1) / 2;
        const hw = Math.min(cap, target.x1 - target.x0) / 2; const hh = Math.min(cap, target.y1 - target.y0) / 2;
        target.x0 = cx - hw; target.x1 = cx + hw; target.y0 = cy - hh; target.y1 = cy + hh;
        const b = sample.boxes[g];
        if (!b.seen) { Object.assign(b, target); b.seen = true; }
        b.x0 += (target.x0 - b.x0) * 0.18; b.x1 += (target.x1 - b.x1) * 0.18;
        b.y0 += (target.y0 - b.y0) * 0.18; b.y1 += (target.y1 - b.y1) * 0.18;
        const ce = loudness[g];
        const dimension = dimensions[g];
        // Skip a box whose centre already lies inside a placed one: no piles.
        const bcx = (b.x0 + b.x1) / 2; const bcy = (b.y0 + b.y1) / 2;
        // Two inversions cancel where boxes overlap, so a box that would overlap a placed
        // one by more than a fifth of its area is skipped as well.
        const area = Math.max(1, (b.x1 - b.x0) * (b.y1 - b.y0));
        const crowded = placed.some((q) => {
          const ix = Math.max(0, Math.min(b.x1, q.x1) - Math.max(b.x0, q.x0));
          const iy = Math.max(0, Math.min(b.y1, q.y1) - Math.max(b.y0, q.y0));
          return (bcx > q.x0 && bcx < q.x1 && bcy > q.y0 && bcy < q.y1) || (ix * iy) / area > 0.2;
        });
        if (crowded) continue;
        placed.push({ x0: b.x0, x1: b.x1, y0: b.y0, y1: b.y1 });
        const el = els[used];
        if (el.dataset.kind !== 'box') { el.className = 'survey-box'; el.dataset.kind = 'box'; }
        const text = dimension ? dimensionLabel(dimension.id) + ' ' + dimension.value.toFixed(2) : '';
        const w = Math.max(28, b.x1 - b.x0); const h = Math.max(22, b.y1 - b.y0);
        el.style.left = b.x0.toFixed(1) + 'px';
        el.style.top = b.y0.toFixed(1) + 'px';
        el.style.width = w.toFixed(1) + 'px';
        el.style.height = h.toFixed(1) + 'px';
        el.style.opacity = ((0.8 + 0.2 * Math.min(1, ce * 1.6)) * surveyShow * sample.vis[g]).toFixed(2);
        const tag = tags.current[used];
        if (tag) {
          const below = g % 2 === 1;
          if (tag.dataset.side !== (below ? 'b' : 'a')) { tag.className = 'survey-tag' + (below ? ' is-below' : ''); tag.dataset.side = below ? 'b' : 'a'; }
          if (tag.textContent !== text) tag.textContent = text;
          const index = String(g + 1).padStart(2, '0');
          if (tag.dataset.index !== index) tag.dataset.index = index;
          tag.style.left = b.x0.toFixed(1) + 'px';
          tag.style.top = (below ? b.y0 + h : b.y0).toFixed(1) + 'px';
          tag.style.opacity = (surveyShow * sample.vis[g]).toFixed(2);
        }
        nodes.push({ k: g, x: b.x0 + w / 2, y: b.y0 + h / 2, e: ce * sample.vis[g], hw: w / 2, hh: h / 2 });
        used += 1;
      }
    }
    for (let i = used; i < els.length; i += 1) els[i].style.opacity = '0';
    for (let i = used; i < tags.current.length; i += 1) tags.current[i].style.opacity = '0';

    // The network: a chain through the bands, a hub from the loudest box, and each
    // box's nearest neighbour; the weight of an edge is the loudness it joins.
    const edges = net.current;
    const pairs: Array<[number, number, number]> = [];
    const seen = new Set<string>();
    const join = (a: number, b: number, w: number) => {
      if (a === b) return;
      const key = a < b ? a + ':' + b : b + ':' + a;
      if (seen.has(key)) return;
      seen.add(key);
      pairs.push([a, b, w]);
    };
    if (nodes.length > 1) {
      for (let i = 0; i + 1 < nodes.length; i += 1) join(i, i + 1, Math.min(nodes[i].e, nodes[i + 1].e));
      let hub = 0;
      nodes.forEach((node, i) => { if (node.e > nodes[hub].e) hub = i; });
      nodes.forEach((node, i) => join(hub, i, nodes[hub].e * node.e));
      nodes.forEach((node, i) => {
        let best = -1; let bestD = Infinity;
        nodes.forEach((other, j) => {
          if (j === i) return;
          const d = (other.x - node.x) ** 2 + (other.y - node.y) ** 2;
          if (d < bestD) { bestD = d; best = j; }
        });
        if (best >= 0) join(i, best, 0.5 * (node.e + nodes[best].e));
      });
    }
    for (let i = 0; i < edges.length; i += 1) {
      const line = edges[i];
      const pair = pairs[i];
      if (!pair || surveyShow <= 0.01) { line.setAttribute('visibility', 'hidden'); continue; }
      const a = nodes[pair[0]]; const b = nodes[pair[1]];
      // Clip the run to the outside of both frames: the line meets an edge, it never
      // crosses into the frame or reaches its centre.
      const dx = b.x - a.x; const dy = b.y - a.y;
      const exit = (n: { hw: number; hh: number }) => {
        const tx = Math.abs(dx) > 0.001 ? n.hw / Math.abs(dx) : 9;
        const ty = Math.abs(dy) > 0.001 ? n.hh / Math.abs(dy) : 9;
        return Math.min(0.48, Math.min(tx, ty));
      };
      const gap = 3 / Math.max(1, Math.hypot(dx, dy));
      const ta = exit(a) + gap; const tb = exit(b) + gap;
      if (ta + tb >= 0.98) { line.setAttribute('visibility', 'hidden'); continue; }
      line.setAttribute('x1', (a.x + dx * ta).toFixed(1)); line.setAttribute('y1', (a.y + dy * ta).toFixed(1));
      line.setAttribute('x2', (b.x - dx * tb).toFixed(1)); line.setAttribute('y2', (b.y - dy * tb).toFixed(1));
      const heavy = pair[2] > 0.45;
      line.setAttribute('stroke-width', heavy ? '1.6' : '0.9');
      line.setAttribute('stroke-dasharray', heavy && pair[2] > 0.7 ? '6 4' : '');
      line.setAttribute('stroke-opacity', ((0.6 + 0.4 * Math.min(1, pair[2] * 1.4)) * surveyShow).toFixed(2));
      line.removeAttribute('visibility');
    }
  }, 1);

  return (
    <>
      <points geometry={cloud.geometry} material={cloud.glow} frustumCulled={false} renderOrder={1} />
      <points geometry={cloud.geometry} material={cloud.points} frustumCulled={false} renderOrder={2} />
    </>
  );
}

const clockText = (seconds: number) => Math.floor(seconds / 60) + ':' + String(Math.floor(seconds % 60)).padStart(2, '0');

export function NebulaSpectrum({ url, name, dimensions, glbUrl = null }: { url: string; name: string; dimensions: Dimension[]; glbUrl?: string | null }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const holder = useRef<HTMLDivElement | null>(null);
  const ear = useRef<Ear>({ analyser: null, context: null, playing: false, bass: 0, flux: 0, fluxAvg: 0.02, energy: 0, treble: 0, windAngle: 0, gust: 0, survey: true, appear: 1, openPulse: 0, scale: 1, surveyGate: 1, focus: 0, loud: 0, centroid: 0.5, fluxRaw: 0, events: [], eventId: 0, clock: 0, waves: [99, 99, 99], breath: 0 });
  const show = useRef<Show>({ start: null, focus: 0, centre: new THREE.Vector3(0, 0, CLOUD_Z) });
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [surveyOn, setSurveyOn] = useState(true);
  const toggleSurvey = useCallback(() => {
    setSurveyOn((on) => { ear.current.survey = !on; return !on; });
  }, []);

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
    if (audio.paused) { await live.context.resume(); await audio.play(); } else { audio.pause(); }
  }, []);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const onPlay = () => { ear.current.playing = true; setPlaying(true); };
    const onPause = () => { ear.current.playing = false; setPlaying(false); };
    const onTime = () => setTime(audio.currentTime);
    audio.addEventListener('play', onPlay); audio.addEventListener('pause', onPause);
    audio.addEventListener('ended', onPause); audio.addEventListener('timeupdate', onTime);
    return () => {
      audio.removeEventListener('play', onPlay); audio.removeEventListener('pause', onPause);
      audio.removeEventListener('ended', onPause); audio.removeEventListener('timeupdate', onTime);
    };
  }, []);
  useEffect(() => { const live = ear.current; return () => { void live.context?.close(); }; }, []);

  return (
    <>
      <Canvas camera={{ position: [0, 4, 30], fov: 38, near: 0.5, far: 600 }} dpr={[1, 2]} gl={{ antialias: false, alpha: false }}>
        <Mass ear={ear} holder={holder} dimensions={dimensions} building={Boolean(glbUrl)} show={show} />
        {glbUrl && (
          <Suspense fallback={null}>
            <Builders url={glbUrl} show={show} />
          </Suspense>
        )}
        <OrbitControls makeDefault target={[0, 1, 0]} enableDamping dampingFactor={0.06} autoRotate autoRotateSpeed={0.12} minDistance={20} maxDistance={220} />
      </Canvas>
      <div ref={holder} className="lab-labels" aria-hidden="true" />
      <audio ref={audioRef} src={url} preload="auto" crossOrigin="anonymous" loop />
      <div className="live-controls">
        <button type="button" className={'topbar-btn' + (playing ? ' is-active' : '')} onClick={() => { void toggle(); }}>
          {playing ? 'Pause' : 'Listen'}
        </button>
        <button type="button" className={'topbar-btn' + (surveyOn ? ' is-active' : '')} onClick={toggleSurvey}>Survey</button>
        <span className="live-clock">{name} · {clockText(time)}</span>
      </div>
    </>
  );
}
