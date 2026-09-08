'use client';

/**
 * The hearing as a cloud: the recording, as particles, becoming the building.
 *
 * The machine's hearing — the whole piece's log-frequency picture, the same one the
 * score was written out of — hangs in the model's own space as a ribbon of particles
 * in front of the plan: time along the plan's long side, frequency as height, every
 * particle seeded from a cell of the field, louder cells more often. It is the
 * material. When a layer's turn comes in the assembly, the particles that belong to
 * that layer leave the ribbon, spiral across, and land on the surfaces of its
 * elements just as those elements arrive — then go out, because the element is solid
 * now. The ribbon thins as the building stands; when the building is complete the
 * recording has been spent. That is the whole of "frozen music", as a motion.
 *
 * It is a whole-field motion, never a local one: each layer's particles come from
 * everywhere on the ribbon (their cell is drawn at random) and land everywhere on the
 * layer (their point is drawn by surface area), so nothing reads as "this note built
 * that column". The ribbon also carries the analysis the compiler made of the parts:
 * one box per part of the recording, framing that part's particles and naming its
 * rhythm reading, and a net of lines from every box up to the whole-piece numbers
 * those readings were folded into.
 *
 * The idiom is TouchDesigner's — a field of instanced points moved by analysed values
 * (`Audio Spectrum CHOP → CHOP to TOP → instancing`), the number moving the whole
 * field at once — done here as one GPU point cloud whose every position is a pure
 * function of the assembly clock: no per-frame CPU work, and Skip, Play and reduced
 * motion all fall out of the same three uniforms.
 */

import { useEffect, useMemo, useRef, type RefObject } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { MeshSurfaceSampler } from 'three/examples/jsm/math/MeshSurfaceSampler.js';
import type { Hearing } from '../lib/hearing';
import type { ViewportMode } from './ArchitectureViewport';

export interface CloudEntry {
  mesh: THREE.Mesh;
  layer: string;
  order: number;
  stagger: number;
  baseY: number;
}

export interface CloudPlan { x_min: number; x_max: number; y_min: number; y_max: number }

/** What the assembly loop knows each frame; the cloud reads it, never writes it. */
export interface AssemblyClock {
  elapsed: number;
  step: number;
  rise: number;
  /** A narrated, full assembly is running (not a quick diff on a run switch). */
  live: boolean;
  /** The assembly has finished: everything stands. */
  done: boolean;
}

/** The compiler's reading of the parts, and the whole-piece numbers they fold into. */
export interface AnalysisNet {
  duration: number;
  parts: Array<{ start: number; end: number; label: string }>;
  nodes: Array<{ label: string }>;
  /** part index → node index */
  links: Array<[number, number]>;
}

const COUNT = 14000;
const BANDS = 32;
const RIBBON_Y0 = 4;
const RIBBON_H = 7;
const RIBBON_GAP = 4;
const NODE_LIFT = 6;
const FLIGHT_S = 1.1;
const SHARE_CAP = 0.03;
const BIRTH_S = 1.2;
const NET_DRAW_S = 1.4;

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function meshArea(mesh: THREE.Mesh): number {
  const geometry = mesh.geometry;
  const position = geometry.getAttribute('position');
  if (!position) return 0;
  const index = geometry.getIndex();
  const a = new THREE.Vector3();
  const b = new THREE.Vector3();
  const c = new THREE.Vector3();
  const triangles = index ? index.count / 3 : position.count / 3;
  let area = 0;
  for (let i = 0; i < triangles; i += 1) {
    const ia = index ? index.getX(i * 3) : i * 3;
    const ib = index ? index.getX(i * 3 + 1) : i * 3 + 1;
    const ic = index ? index.getX(i * 3 + 2) : i * 3 + 2;
    a.fromBufferAttribute(position, ia);
    b.fromBufferAttribute(position, ib).sub(a);
    c.fromBufferAttribute(position, ic).sub(a);
    area += b.cross(c).length() / 2;
  }
  return area;
}

/**
 * Where the ribbon hangs: in front of the plan's near edge and off to its left, at
 * the height of the lower floors — the open air beside the building as the stage's
 * camera sees it, clear of the score strip below and of the model behind.
 */
function ribbonFrame(plan: CloudPlan) {
  const width = plan.x_max - plan.x_min;
  return { x0: plan.x_min - width * 0.55, x1: plan.x_min + width * 0.45, z: -plan.y_min + RIBBON_GAP };
}

const VERTEX = /* glsl */`
attribute vec3 aStart;
attribute vec3 aTarget;
attribute float aOrder;
attribute float aStagger;
attribute float aJitter;
attribute float aTone;
uniform float uElapsed;
uniform float uStep;
uniform float uRise;
uniform float uFlight;
uniform float uBirth;
uniform float uTime;
uniform float uPixelRatio;
varying float vAlpha;
varying float vTone;
float easeOut(float t) { return 1.0 - pow(1.0 - t, 3.0); }
void main() {
  float delay = aOrder * uStep + aStagger;
  float arrive = delay + uRise;
  float depart = arrive - uFlight;
  float t = clamp((uElapsed - depart) / uFlight, 0.0, 1.0);
  float e = easeOut(t);
  vec3 pos = mix(aStart, aTarget, e);
  // The spiral across: wide when it leaves, tight as it lands.
  float ang = aJitter * 6.2832 + t * 9.0;
  float amp = (1.0 - t) * t * 6.0;
  pos += vec3(cos(ang), sin(ang * 0.7), sin(ang)) * amp;
  // Idle on the ribbon: a slow shimmer, the field breathing.
  float idle = 1.0 - step(0.0001, t);
  pos += idle * vec3(0.0, sin(uTime * 1.3 + aJitter * 40.0) * 0.15, cos(uTime * 0.9 + aJitter * 25.0) * 0.15);
  float landed = clamp((uElapsed - arrive) / 0.45, 0.0, 1.0);
  float born = clamp(uBirth / ${BIRTH_S.toFixed(1)}, 0.0, 1.0);
  float flicker = 0.4 + 0.25 * sin(uTime * 4.0 + aJitter * 60.0);
  vAlpha = born * mix(flicker * (0.35 + 0.65 * aTone), 1.0, t) * (1.0 - landed);
  vTone = aTone;
  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  gl_PointSize = (1.4 + 2.4 * aTone + 2.0 * t * (1.0 - t)) * uPixelRatio * (150.0 / -mv.z);
  gl_Position = projectionMatrix * mv;
}
`;

const FRAGMENT = /* glsl */`
uniform vec3 uColor;
varying float vAlpha;
varying float vTone;
void main() {
  vec2 d = gl_PointCoord - 0.5;
  float r = dot(d, d);
  if (r > 0.25) discard;
  float soft = smoothstep(0.25, 0.02, r);
  gl_FragColor = vec4(uColor * (0.55 + 0.6 * vTone), vAlpha * soft);
}
`;

export function HearingCloud({
  hearing, entries, plan, net, mode, cloudKey, assemblyRef, overlayRef, reduced,
}: {
  hearing: Hearing | null;
  entries: CloudEntry[];
  plan: CloudPlan | null;
  net: AnalysisNet | null;
  mode: ViewportMode;
  /** Bumped when the score has been written and the lattice starts: the cloud is born. */
  cloudKey: number;
  assemblyRef: RefObject<AssemblyClock>;
  overlayRef: RefObject<HTMLDivElement | null>;
  reduced: boolean;
}) {
  const blueprint = mode === 'blueprint';

  // The particles: one buffer for the whole assembly, every position a function of
  // the clock. Built once per model and per hearing.
  const cloud = useMemo(() => {
    if (!hearing || !plan || entries.length === 0 || reduced) return null;
    const columns = hearing.cells.length / BANDS;
    if (columns < 2) return null;
    const pool = entries.filter((entry) => entry.layer !== 'site');
    const areas = pool.map((entry) => meshArea(entry.mesh));
    const total = areas.reduce((sum, area) => sum + area, 0);
    if (total <= 0) return null;
    const shares = areas.map((area) => Math.min(area / total, SHARE_CAP));
    const shareSum = shares.reduce((sum, share) => sum + share, 0);
    const counts = shares.map((share) => Math.round((COUNT * share) / shareSum));
    const n = counts.reduce((sum, count) => sum + count, 0);
    const start = new Float32Array(n * 3);
    const target = new Float32Array(n * 3);
    const order = new Float32Array(n);
    const stagger = new Float32Array(n);
    const jitter = new Float32Array(n);
    const tone = new Float32Array(n);
    const random = mulberry32(7);
    const frame = ribbonFrame(plan);
    const point = new THREE.Vector3();
    let i = 0;
    pool.forEach((entry, e) => {
      const count = counts[e];
      if (count === 0) return;
      entry.mesh.updateWorldMatrix(true, false);
      const sampler = new MeshSurfaceSampler(entry.mesh).build();
      const lift = entry.baseY - entry.mesh.position.y;   // sample the element at rest
      for (let k = 0; k < count; k += 1, i += 1) {
        sampler.sample(point);
        point.applyMatrix4(entry.mesh.matrixWorld);
        point.y += lift;
        target[i * 3] = point.x; target[i * 3 + 1] = point.y; target[i * 3 + 2] = point.z;
        // A cell of the hearing, louder cells more often — from anywhere in the piece.
        let column = 0; let band = 0; let value = 0;
        for (let tries = 0; tries < 8; tries += 1) {
          column = Math.floor(random() * columns);
          band = Math.floor(random() * BANDS);
          value = hearing.cells[band * columns + column] / 255;
          if (random() < value * 0.9 + 0.1) break;
        }
        start[i * 3] = frame.x0 + ((column + random()) / columns) * (frame.x1 - frame.x0);
        start[i * 3 + 1] = RIBBON_Y0 + ((band + random()) / BANDS) * RIBBON_H;
        start[i * 3 + 2] = frame.z + (random() - 0.5) * 0.8;
        order[i] = entry.order;
        stagger[i] = entry.stagger;
        jitter[i] = random();
        tone[i] = value;
      }
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(start.slice(), 3));
    geometry.setAttribute('aStart', new THREE.BufferAttribute(start, 3));
    geometry.setAttribute('aTarget', new THREE.BufferAttribute(target, 3));
    geometry.setAttribute('aOrder', new THREE.BufferAttribute(order, 1));
    geometry.setAttribute('aStagger', new THREE.BufferAttribute(stagger, 1));
    geometry.setAttribute('aJitter', new THREE.BufferAttribute(jitter, 1));
    geometry.setAttribute('aTone', new THREE.BufferAttribute(tone, 1));
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1e5);
    return { geometry, count: n };
  }, [hearing, entries, plan, reduced]);
  useEffect(() => () => { cloud?.geometry.dispose(); }, [cloud]);

  const material = useMemo(() => new THREE.ShaderMaterial({
    uniforms: {
      uElapsed: { value: -1000 }, uStep: { value: 0.55 }, uRise: { value: 1 }, uFlight: { value: FLIGHT_S },
      uBirth: { value: 0 }, uTime: { value: 0 }, uPixelRatio: { value: 1 },
      uColor: { value: new THREE.Color(blueprint ? '#c6e2ff' : '#0071e3') },
    },
    vertexShader: VERTEX,
    fragmentShader: FRAGMENT,
    transparent: true,
    depthWrite: false,
    blending: blueprint ? THREE.AdditiveBlending : THREE.NormalBlending,
  }), [blueprint]);
  useEffect(() => () => material.dispose(), [material]);

  // The analysis on the ribbon: a box per part, a node per whole-piece number, and
  // the net between them. Drawn as strokes, labelled in the overlay.
  const web = useMemo(() => {
    if (!net || !plan || net.parts.length === 0 || net.duration <= 0 || reduced) return null;
    const frame = ribbonFrame(plan);
    const xAt = (seconds: number) => frame.x0 + (seconds / net.duration) * (frame.x1 - frame.x0);
    const positions: number[] = [];
    const seg = (a: THREE.Vector3, b: THREE.Vector3) => positions.push(a.x, a.y, a.z, b.x, b.y, b.z);
    const anchors: THREE.Vector3[] = [];
    const tops: THREE.Vector3[] = [];
    const y0 = RIBBON_Y0 - 0.4;
    const y1 = RIBBON_Y0 + RIBBON_H + 0.4;
    net.parts.forEach((part, index) => {
      const x0 = xAt(part.start) + 0.15;
      const x1 = xAt(part.end) - 0.15;
      const z0 = frame.z - 0.7;
      const z1 = frame.z + 0.7;
      const corner = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
      const c = [
        corner(x0, y0, z0), corner(x1, y0, z0), corner(x1, y0, z1), corner(x0, y0, z1),
        corner(x0, y1, z0), corner(x1, y1, z0), corner(x1, y1, z1), corner(x0, y1, z1),
      ];
      [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]]
        .forEach(([a, b]) => seg(c[a], c[b]));
      // The caption hangs off the box's near bottom corner, the way a survey labels a
      // frame; the net leaves from a stub on its top edge.
      // Captions alternate two rows, the way a survey staggers labels that would touch.
      anchors.push(new THREE.Vector3(x0, y0 - 0.5 - (index % 3) * 1.6, z1));
      const top = new THREE.Vector3((x0 + x1) / 2, y1, frame.z);
      seg(top, top.clone().add(new THREE.Vector3(0, 0.5, 0)));
      tops.push(top.clone().add(new THREE.Vector3(0, 0.5, 0)));
    });
    // The chain along the parts: the piece is read in order.
    tops.forEach((top, i) => { if (tops[i + 1]) seg(top, tops[i + 1]); });
    const nodes = net.nodes.map((_, i) => new THREE.Vector3(
      frame.x0 + ((i + 0.5) / net.nodes.length) * (frame.x1 - frame.x0), y1 + NODE_LIFT, frame.z,
    ));
    net.links.forEach(([p, q]) => { if (tops[p] && nodes[q]) seg(tops[p], nodes[q]); });
    nodes.forEach((node) => {
      const d = 0.45;
      seg(node.clone().add(new THREE.Vector3(-d, 0, 0)), node.clone().add(new THREE.Vector3(0, d, 0)));
      seg(node.clone().add(new THREE.Vector3(0, d, 0)), node.clone().add(new THREE.Vector3(d, 0, 0)));
      seg(node.clone().add(new THREE.Vector3(d, 0, 0)), node.clone().add(new THREE.Vector3(0, -d, 0)));
      seg(node.clone().add(new THREE.Vector3(0, -d, 0)), node.clone().add(new THREE.Vector3(-d, 0, 0)));
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.setDrawRange(0, 0);
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1e5);
    const labels = [
      ...net.parts.map((part, i) => ({ text: part.label, at: anchors[i], node: false })),
      ...net.nodes.map((node, i) => ({ text: node.label, at: nodes[i], node: true })),
    ];
    return { geometry, total: positions.length / 3, labels };
  }, [net, plan, reduced]);
  useEffect(() => () => { web?.geometry.dispose(); }, [web]);
  const webMaterial = useMemo(() => new THREE.LineBasicMaterial({
    color: blueprint ? '#dbe7ff' : '#1d1d1f', transparent: true, opacity: 0, toneMapped: false, depthTest: false,
  }), [blueprint]);
  useEffect(() => () => webMaterial.dispose(), [webMaterial]);

  // The labels live in the stage's transfer layer, one div each, placed every frame.
  const labelsRef = useRef<HTMLElement[]>([]);
  useEffect(() => {
    const layer = overlayRef.current?.parentElement?.querySelector<HTMLElement>('.transfer-layer');
    if (!layer || !web) return;
    const holder = document.createElement('div');
    holder.className = 'net-labels';
    const made = web.labels.map((label) => {
      const el = document.createElement('div');
      el.className = 'net-label' + (label.node ? ' is-node' : ' is-part');
      el.textContent = label.text;
      el.hidden = true;
      holder.appendChild(el);
      return el;
    });
    layer.appendChild(holder);
    labelsRef.current = made;
    return () => { holder.remove(); labelsRef.current = []; };
  }, [web, overlayRef]);

  const stateRef = useRef({ key: -1, bornAt: 0, doneAt: -1 });
  const point = useMemo(() => new THREE.Vector3(), []);
  useFrame(({ clock, gl, camera, size }) => {
    const now = clock.getElapsedTime();
    const state = stateRef.current;
    const assembly = assemblyRef.current;
    if (state.key !== cloudKey) { state.key = cloudKey; state.bornAt = now; state.doneAt = -1; }
    const born = cloudKey > 0 ? Math.min(1, (now - state.bornAt) / BIRTH_S) : 0;
    if (assembly.done && state.doneAt < 0) state.doneAt = now;
    if (!assembly.done) state.doneAt = -1;
    const gone = state.doneAt >= 0 ? Math.min(1, (now - state.doneAt) / 0.8) : 0;

    const u = material.uniforms;
    u.uTime.value = now;
    u.uPixelRatio.value = gl.getPixelRatio();
    u.uElapsed.value = assembly.live ? assembly.elapsed : (assembly.done ? 1e4 : -1000);
    u.uStep.value = assembly.step;
    u.uRise.value = assembly.rise;
    u.uBirth.value = cloudKey > 0 ? now - state.bornAt : 0;

    if (web) {
      const drawn = Math.min(1, Math.max(0, (now - state.bornAt - 0.3) / NET_DRAW_S));
      web.geometry.setDrawRange(0, cloudKey > 0 ? Math.floor(drawn * web.total) : 0);
      const alpha = born * (1 - gone) * 0.9;
      webMaterial.opacity = alpha;
      labelsRef.current.forEach((el, i) => {
        const label = web.labels[i];
        if (!label || alpha <= 0.02) { el.hidden = true; return; }
        point.copy(label.at).project(camera);
        if (point.z > 1) { el.hidden = true; return; }
        el.hidden = false;
        el.style.left = (((point.x + 1) / 2) * size.width).toFixed(1) + 'px';
        el.style.top = (((1 - point.y) / 2) * size.height).toFixed(1) + 'px';
        el.style.opacity = alpha.toFixed(2);
      });
    }
  });

  if (!cloud && !web) return null;
  return (
    <>
      {cloud && <points geometry={cloud.geometry} material={material} frustumCulled={false} renderOrder={12} />}
      {web && <lineSegments geometry={web.geometry} material={webMaterial} frustumCulled={false} renderOrder={11} />}
    </>
  );
}
