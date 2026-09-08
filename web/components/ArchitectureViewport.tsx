'use client';

import { Suspense, useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, useGLTF } from '@react-three/drei';
import * as THREE from 'three';
import type {
  ClippingSettings, Lattice, ProgramAllocation, ProgramVolumeModel,
} from '../lib/types';
import { ProgramVolumeMassing } from './ProgramVolumeMassing';
import { HearingCloud, type AnalysisNet, type AssemblyClock } from './HearingCloud';
import type { Hearing } from '../lib/hearing';

export type ViewportMode = 'studio' | 'blueprint';

/** A leader-line annotation: the model pointing at its own reasoning. */
export interface ViewportCallout {
  id: string;
  index: string;
  title: string;
  body: string;
  layer: string;
  /** Prefer an anchor object whose key contains this fragment. */
  subsystem?: string;
  /** Where on the anchor's box the line lands. */
  anchor?: 'top' | 'mid';
}

export interface ViewportProps {
  assetUrl: string;
  mode: ViewportMode;
  /** Object keys (`layer__subsystem__category`) the viewer has switched off. */
  hidden: Set<string>;
  /** One key drawn at full strength while everything else fades back. */
  focus?: string | null;
  /** One semantic layer held up while the rest recede — driven by callout hover. */
  highlightLayer?: string | null;
  /**
   * The registration lattice the score set — level lines and bay lines — drawn in
   * space before anything solid: the geometry between the score and the building.
   */
  lattice?: LatticeLines | null;
  /** Bump to draw the lattice in; it fades once the assembly has finished. */
  latticeKey?: number;
  /**
   * The layer a transfer leader should reach from the score strip's driving marks
   * (`[data-transfer-source]` on the stage): the layer assembling, or `lattice`.
   */
  /** The reading crossing right now: which layer, and the datums it set there. */
  transfer?: Transfer | null;
  /** The machine's hearing of the recording: the cloud the building is made from. */
  hearing?: Hearing | null;
  /** Bumped when the score has been written: the cloud is born with the lattice. */
  cloudKey?: number;
  /** The compiler's reading of the parts, boxed on the ribbon and netted to its numbers. */
  net?: AnalysisNet | null;
  clipping: ClippingSettings;
  showSite?: boolean;
  /** Legacy-compatible visible intermediate: the score-authored gross volumes. */
  programVolumes?: {
    lattice: Lattice;
    allocation: ProgramAllocation;
    model?: ProgramVolumeModel | null;
    visible: boolean;
  } | null;
  /** Leader-line annotations, shown once assembly has finished. */
  callouts?: ViewportCallout[];
  annotate?: boolean;
  /** Bump to replay the assembly sequence. */
  buildKey?: number;
  /** Held: every element waits below ground and the clock waits with it — until the
   *  score has been written and the lattice drawn. Releasing starts the assembly. */
  hold?: boolean;
  /** Seconds per construction stage; the narrated performance slows this down. */
  stepSeconds?: number;
  onReady?: () => void;
  /** Narrates the assembly: the semantic layer being built, or null when done. */
  onAssembly?: (layer: string | null) => void;
  onCalloutHover?: (layer: string | null) => void;
  onCalloutClick?: (id: string) => void;
}

/** The lattice as the viewport needs it: metres, in the model's own frame. */
export interface Transfer {
  layer: string;
  datums: Array<{ label: string; value: number; unit: string }>;
}

export interface LatticeLines {
  levels: Array<{ id: string; z: number }>;
  xLines: number[];
  yLines: number[];
  plan: { x_min: number; x_max: number; y_min: number; y_max: number };
}

/** The order a building actually goes up in, which is the order it assembles here. */
const LAYER_ORDER: Record<string, number> = {
  site: 0, structure: 1, envelope: 2, circulation: 3, program: 4,
};
const STEP_S = 0.55;
const RISE_S = 0.65;
const DROP_M = 14;

const BLUEPRINT = {
  ground: '#0e2f66',
  /** Lit by the blueprint rig below, this lands between #12387a in shade and #2058b0 in sun. */
  fill: '#1a4690',
  glass: '#4f86dc',
  grid: '#1c4489',
  gridSoft: '#16407f',
};

/**
 * Line weight, the way a drawing has it. A pen set has a heavy profile pen for the
 * building's fabric, a medium pen for what divides its rooms, and a fine pen for the
 * furniture and figures that give it scale. Drawn all in one weight, three and a half
 * thousand elements read as an X-ray; drawn in three, they read as a building.
 */
const LINE_TIER: Record<1 | 2 | 3, string> = { 1: '#f4f8ff', 2: '#a4bfea', 3: '#5c7fc0' };
const SUBSYSTEM_TIER: Record<string, 1 | 2 | 3> = {
  safety: 3, furniture: 3, scale_reference: 3, zones: 3,
  partitions: 2, finishes: 2, archetype: 2, context: 2, screen: 2,
};
const LAYER_TIER: Record<string, 1 | 2 | 3> = {
  structure: 1, envelope: 1, circulation: 1, site: 1, program: 2,
};

function lineTier(layer: string, subsystem: string | undefined, glass: boolean): 1 | 2 | 3 {
  if (glass) return 2; // a pane's outline is the mullion, not the wall
  return (subsystem ? SUBSYSTEM_TIER[subsystem] : undefined) ?? LAYER_TIER[layer] ?? 2;
}

function isGlass(material: THREE.Material): boolean {
  const physical = material as THREE.MeshPhysicalMaterial;
  return (typeof physical.transmission === 'number' && physical.transmission > 0.3)
    || /glass/i.test(material.name);
}

function semanticValue(object: THREE.Object3D, key: 'layer' | 'subsystem' | 'category'): string | undefined {
  let current: THREE.Object3D | null = object;
  while (current) {
    const value = current.userData['mta:' + key] ?? current.userData['mta_' + key];
    if (typeof value === 'string') return value;
    current = current.parent;
  }
  return undefined;
}

/** The key the manifest uses, recomputed from the tags so a `.001` suffix cannot break it. */
export function objectKey(object: THREE.Object3D): string {
  const layer = semanticValue(object, 'layer');
  const subsystem = semanticValue(object, 'subsystem');
  const category = semanticValue(object, 'category');
  if (layer && subsystem && category) return layer + '__' + subsystem + '__' + category;
  return object.name.replace(/\.\d+$/, '');
}

interface Entry {
  mesh: THREE.Mesh;
  key: string;
  layer: string;
  order: number;
  stagger: number;
  baseY: number;
  volume: number;
  box: THREE.Box3;
  studio: THREE.Material[];
  fill: THREE.MeshLambertMaterial;
  /** 1 for fabric; below 1 for glass, which veils what stands behind it. */
  fillAlpha: number;
  edge: THREE.LineSegments;
  edgeMat: THREE.LineBasicMaterial;
}

interface BuiltScene {
  root: THREE.Object3D;
  entries: Entry[];
  center: THREE.Vector3;
  radius: number;
  maxStagger: number;
}

function easeOutCubic(t: number): number { return 1 - Math.pow(1 - t, 3); }

/* eslint-disable react-hooks/immutability -- the scene graph, its materials and the
   camera are objects three.js owns and a viewport mutates; mirroring them into React
   state would create a second source of truth for the same geometry. */

function FitToModel({ built }: { built: BuiltScene }) {
  const camera = useThree((state) => state.camera);
  const controls = useThree((state) => state.controls) as
    | { target: THREE.Vector3; update: () => void; minDistance: number; maxDistance: number }
    | null;
  // Once per Canvas lifetime: comparing two runs only works if the camera holds
  // still while the model changes underneath it.
  const fitted = useRef(false);

  useEffect(() => {
    if (fitted.current) return;
    const { center, radius } = built;
    if (radius <= 0) return;
    const perspective = camera as THREE.PerspectiveCamera;
    const fov = (perspective.fov * Math.PI) / 180;
    const distance = (radius / Math.sin(fov / 2)) * 1.02;

    const direction = new THREE.Vector3(0.78, 0.46, 0.94).normalize();
    perspective.position.copy(center.clone().add(direction.multiplyScalar(distance)));
    perspective.near = Math.max(0.1, distance / 120);
    perspective.far = distance * 6;
    perspective.updateProjectionMatrix();

    if (controls) {
      controls.target.copy(center);
      controls.minDistance = radius * 0.5;
      controls.maxDistance = distance * 2.6;
      controls.update();
    }
    fitted.current = true;
  }, [camera, controls, built]);

  return null;
}

/**
 * Atmospheric perspective for the drawing: line work at the back of the building
 * fades a little toward the ground colour, so near and far stop being the same
 * white and the X-ray flattening goes away. The fade is pinned to the camera's
 * distance from the model, so it neither vanishes on zoom-in nor swallows the
 * building on zoom-out.
 */
function DepthFade({ built, enabled }: { built: BuiltScene; enabled: boolean }) {
  const scene = useThree((state) => state.scene);
  const fog = useMemo(() => new THREE.Fog(BLUEPRINT.ground, 1, 1000), []);

  useEffect(() => {
    scene.fog = enabled ? fog : null;
    // Fog is compiled into a material's shader, so every material learns of the change.
    scene.traverse((object) => {
      const material = (object as THREE.Mesh).material as THREE.Material | THREE.Material[] | undefined;
      if (!material) return;
      (Array.isArray(material) ? material : [material]).forEach((item) => { item.needsUpdate = true; });
    });
    return () => { scene.fog = null; };
  }, [scene, fog, enabled]);

  useFrame(({ camera }) => {
    if (!enabled) return;
    const distance = camera.position.distanceTo(built.center);
    fog.near = distance - built.radius * 0.35;
    fog.far = distance + built.radius * 3.6;
  });

  return null;
}

const LATTICE_S = 2.6;
const LATTICE_DELAY_S = 1.6;
const LATTICE_PIECES = 10;

/**
 * The lattice, drawn in. Mondrian took a tree to lines before he took it to planes;
 * this compiler takes a score to a registration lattice before it takes it to
 * members — level lines at the heights the score set, bay lines at the spacing it
 * set — and every element is indexed into that lattice rather than placed. So the
 * lattice is shown: it grows in from the ground while the score is still speaking,
 * the structure then rises onto it, and it fades once the building stands.
 */
function LatticeLines({ lattice, mode, drawKey, done }: {
  lattice: LatticeLines | null; mode: ViewportMode; drawKey: number; done: boolean;
}) {
  const geometry = useMemo(() => {
    const positions: number[] = [];
    if (lattice) {
      const { plan, levels, xLines, yLines } = lattice;
      const top = Math.max(...levels.map((l) => l.z), 0);
      // Model Z-up → viewer Y-up; model y runs along viewer −z (see useSectionPlane).
      const push = (ax: number, ay: number, az: number, bx: number, by: number, bz: number) => {
        for (let i = 0; i < LATTICE_PIECES; i += 1) {
          const t0 = i / LATTICE_PIECES;
          const t1 = (i + 1) / LATTICE_PIECES;
          positions.push(ax + (bx - ax) * t0, ay + (by - ay) * t0, az + (bz - az) * t0,
            ax + (bx - ax) * t1, ay + (by - ay) * t1, az + (bz - az) * t1);
        }
      };
      // Level outlines, bottom to top: the floor episodes the tempo set.
      levels.forEach((level) => {
        const y = level.z;
        push(plan.x_min, y, -plan.y_min, plan.x_max, y, -plan.y_min);
        push(plan.x_max, y, -plan.y_min, plan.x_max, y, -plan.y_max);
        push(plan.x_max, y, -plan.y_max, plan.x_min, y, -plan.y_max);
        push(plan.x_min, y, -plan.y_max, plan.x_min, y, -plan.y_min);
      });
      // Bay lines, rising: the grid the density set, at every crossing.
      xLines.forEach((x) => yLines.forEach((yy) => push(x, 0, -yy, x, top, -yy)));
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geo.setDrawRange(0, 0);
    return geo;
  }, [lattice]);
  const material = useMemo(() => new THREE.LineBasicMaterial({
    color: mode === 'blueprint' ? '#9cc4ff' : '#0071e3', transparent: true, opacity: 0.9, toneMapped: false,
  }), [mode]);
  const stateRef = useRef({ key: -1, start: 0, fadeFrom: -1 });
  const total = geometry.getAttribute('position')?.count ?? 0;

  useFrame(({ clock }) => {
    const now = clock.getElapsedTime();
    const state = stateRef.current;
    if (state.key !== drawKey) { state.key = drawKey; state.start = now; state.fadeFrom = -1; }
    if (drawKey === 0 || total === 0) { geometry.setDrawRange(0, 0); return; }
    const p = Math.min(1, Math.max(0, (now - state.start - LATTICE_DELAY_S) / LATTICE_S));
    geometry.setDrawRange(0, Math.floor(easeOutCubic(p) * total));
    if (done && state.fadeFrom < 0) state.fadeFrom = now;
    if (!done) state.fadeFrom = -1;
    material.opacity = state.fadeFrom >= 0 ? Math.max(0, 0.9 * (1 - (now - state.fadeFrom) / 1.2)) : 0.9;
    if (material.opacity === 0) geometry.setDrawRange(0, 0);
  });

  return <lineSegments geometry={geometry} material={material} />;
}

interface Dimension {
  key: string;
  positions: number[];
  anchor: THREE.Vector3;
  text: string;
}

const TICK_M = 1.2;
const DIM_S = 0.45;

function seg(out: number[], ax: number, ay: number, az: number, bx: number, by: number, bz: number) {
  out.push(ax, ay, az, bx, by, bz);
}

/**
 * The datum a reading set, drawn the way a drawing states a rule: one dimension
 * string across the whole lattice — a tick at every level, at every bay line — so
 * "floor to floor 4.2 m" is seen holding everywhere at once. A datum with no lattice
 * geometry is stated once, over the whole layer, never on one element.
 */
function datumDimension(transfer: Transfer | null, lattice: LatticeLines | null, built: BuiltScene): Dimension | null {
  if (!transfer || transfer.datums.length === 0) return null;
  const pick = (test: (label: string) => boolean) => transfer.datums.find((d) => test(d.label.toLowerCase())) ?? null;
  const positions: number[] = [];
  const key = (label: string) => transfer.layer + ':' + label;
  const plan = lattice?.plan ?? null;
  const levels = lattice?.levels ?? [];
  const xs = lattice?.xLines ?? [];
  const ys = lattice?.yLines ?? [];
  const longIsX = plan ? (plan.x_max - plan.x_min) >= (plan.y_max - plan.y_min) : true;

  const floor = pick((l) => l.includes('floor to floor'));
  const count = pick((l) => l.includes('levels'));
  const vertical = floor ?? count;
  if (vertical && plan && levels.length > 1) {
    const x = plan.x_max + 1.6;
    const z = -plan.y_min + 1.6;
    const top = Math.max(...levels.map((l) => l.z));
    seg(positions, x, 0, z, x, top, z);
    levels.forEach((l) => seg(positions, x - TICK_M / 2, l.z, z, x + TICK_M / 2, l.z, z));
    const text = floor
      ? (levels.length - 1) + ' × ' + floor.value.toFixed(1) + ' m · ' + floor.label
      : vertical.label + ' ' + vertical.value.toFixed(1) + ' · ' + levels.length + ' level lines';
    return { key: key(vertical.label), positions, anchor: new THREE.Vector3(x + 0.6, top / 2, z), text };
  }
  const bay = pick((l) => l.includes('bay'));
  if (bay && plan) {
    const alongX = bay.label.toLowerCase().includes('short') ? !longIsX : longIsX;
    const lines = alongX ? xs : ys;
    if (lines.length > 1) {
      const y = 0.05;
      const first = lines[0];
      const last = lines[lines.length - 1];
      if (alongX) {
        const z = -plan.y_min + 2.2;
        seg(positions, first, y, z, last, y, z);
        lines.forEach((x) => seg(positions, x, y, z - TICK_M / 2, x, y, z + TICK_M / 2));
        return {
          key: key(bay.label), positions, anchor: new THREE.Vector3(last + 0.6, y, z + 0.8),
          text: (lines.length - 1) + ' × ' + bay.value.toFixed(1) + ' m · ' + bay.label,
        };
      }
      const x = plan.x_max + 2.2;
      seg(positions, x, y, -first, x, y, -last);
      lines.forEach((yy) => seg(positions, x - TICK_M / 2, y, -yy, x + TICK_M / 2, y, -yy));
      return {
        key: key(bay.label), positions, anchor: new THREE.Vector3(x + 0.8, y, -first),
        text: (lines.length - 1) + ' × ' + bay.value.toFixed(1) + ' m · ' + bay.label,
      };
    }
  }
  // No lattice geometry for it: state it once, over the whole layer.
  const datum = transfer.datums[0];
  const box = new THREE.Box3();
  built.entries.forEach((entry) => { if (entry.layer === transfer.layer) box.union(entry.box); });
  if (box.isEmpty()) return null;
  const centre = box.getCenter(new THREE.Vector3());
  seg(positions, centre.x, box.max.y, centre.z, centre.x, box.max.y + 4, centre.z);
  const value = (Number.isInteger(datum.value) ? String(datum.value) : datum.value.toFixed(1))
    + (datum.unit && datum.unit !== 'levels' && !datum.label.toLowerCase().includes(datum.unit) ? ' ' + datum.unit : '');
  return {
    key: key(datum.label), positions, anchor: new THREE.Vector3(centre.x, box.max.y + 4.4, centre.z),
    text: datum.label + ' ' + value + ' · whole layer',
  };
}

function DatumDimension({ dimension, mode }: { dimension: Dimension | null; mode: ViewportMode }) {
  const geometry = useMemo(() => new THREE.BufferGeometry(), []);
  const material = useMemo(() => new THREE.LineBasicMaterial({
    color: mode === 'blueprint' ? '#ffd28a' : '#0071e3', transparent: true, opacity: 0, toneMapped: false, depthTest: false,
  }), [mode]);
  const stateRef = useRef({ key: '', start: 0, total: 0, fadeFrom: -1 });
  useEffect(() => {
    if (!dimension) return;   // the last string stays for its fade
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(dimension.positions, 3));
    geometry.computeBoundingSphere();
    stateRef.current.total = dimension.positions.length / 3;
  }, [dimension, geometry]);
  useFrame(({ clock }) => {
    const now = clock.getElapsedTime();
    const state = stateRef.current;
    if (dimension) {
      if (state.key !== dimension.key) { state.key = dimension.key; state.start = now; }
      const p = Math.min(1, (now - state.start) / DIM_S);
      geometry.setDrawRange(0, Math.floor(easeOutCubic(p) * state.total));
      material.opacity = 0.95;
      state.fadeFrom = -1;
      return;
    }
    if (state.key === '') return;
    if (state.fadeFrom < 0) state.fadeFrom = now;
    const k = Math.max(0, 1 - (now - state.fadeFrom) / 0.5);
    material.opacity = 0.95 * k;
    if (k === 0) { geometry.setDrawRange(0, 0); state.key = ''; }
  });
  return <lineSegments geometry={geometry} material={material} renderOrder={10} />;
}

function ArchitecturalModel({
  assetUrl, mode, hidden, focus, highlightLayer, plane, showSite, callouts = [],
  annotate = true, buildKey = 0, hold = false, stepSeconds = STEP_S, overlayRef,
  lattice = null, latticeKey = 0, transfer = null, hearing = null, cloudKey = 0, net = null,
  onReady, onAssembly,
}: Omit<ViewportProps, 'clipping' | 'onCalloutHover' | 'onCalloutClick'> & {
  plane: THREE.Plane | null;
  overlayRef: RefObject<HTMLDivElement | null>;
}) {
  const { scene } = useGLTF(assetUrl);
  // 'building' → 'done'; transitions happen only inside the frame loop, which is the
  // one place that knows where the clock is.
  const [phase, setPhase] = useState<'building' | 'done'>('building');
  const builtDone = phase === 'done';
  const animRef = useRef<{
    pending: boolean; start: number; stage: number;
    /** When set, only these keys animate — the quick diff on a run switch. */
    fresh: Map<string, number> | null;
  }>({ pending: true, start: 0, stage: -1, fresh: null });
  const fingerprintRef = useRef<Map<string, string> | null>(null);
  // The tempo may change mid-flight (Skip fast-forwards); the loop reads it fresh
  // from a ref, updated post-render — a one-frame lag on a tempo change is invisible.
  const stepRef = useRef(stepSeconds);
  useEffect(() => { stepRef.current = stepSeconds; }, [stepSeconds]);
  const holdRef = useRef(hold);
  useEffect(() => { holdRef.current = hold; }, [hold]);
  // What the loop knows each frame, for the cloud that pours into the building.
  const assemblyRef = useRef<AssemblyClock>({ elapsed: -1000, step: STEP_S, rise: 1, live: false, done: false });
  const reduced = useMemo(
    () => typeof window !== 'undefined'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    []);

  useEffect(() => { onReady?.(); }, [onReady, scene]);

  /**
   * One construction pass per GLB: clone the scene, and give every mesh its two
   * wardrobes — the exporter's materials for studio, and a shaded blue fill plus a
   * pale edge overlay for blueprint. The opaque fill is what makes blueprint read as
   * a drawing: it occludes the line work behind it, which is hidden-line removal by
   * the oldest trick there is. The shading is what makes it read as a solid: a face
   * in sun and a face in shade are two tones of the same blue, so a volume has sides.
   */
  const built = useMemo<BuiltScene>(() => {
    const root = scene.clone(true);
    root.updateMatrixWorld(true);
    const entries: Entry[] = [];
    const perLayer: Record<string, number> = {};

    root.traverse((object) => {
      if (!(object instanceof THREE.Mesh)) return;
      const key = objectKey(object);
      const layer = semanticValue(object, 'layer') ?? 'site';
      const subsystem = semanticValue(object, 'subsystem');
      const order = LAYER_ORDER[layer] ?? 2;

      const sources = Array.isArray(object.material) ? object.material : [object.material];
      const glass = sources.some(isGlass);
      const studio = sources.map((material) => {
        const next = material.clone();
        next.side = THREE.DoubleSide;
        next.clipShadows = true;
        return next;
      });

      const fillAlpha = glass ? 0.42 : 1;
      const fill = new THREE.MeshLambertMaterial({
        color: glass ? BLUEPRINT.glass : BLUEPRINT.fill,
        side: THREE.DoubleSide,
        transparent: glass, opacity: fillAlpha, depthWrite: !glass,
        polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
        toneMapped: false,
      });
      const edgeMat = new THREE.LineBasicMaterial({
        color: LINE_TIER[lineTier(layer, subsystem, glass)], toneMapped: false,
      });
      const edge = new THREE.LineSegments(new THREE.EdgesGeometry(object.geometry, 28), edgeMat);
      edge.name = '__edges';
      object.add(edge);

      const box = new THREE.Box3().setFromObject(object);
      const size = box.getSize(new THREE.Vector3());
      const stagger = Math.min((perLayer[layer] = (perLayer[layer] ?? 0) + 1) - 1, 5) * 0.07;

      entries.push({
        mesh: object, key, layer, order,
        stagger,
        baseY: object.position.y,
        volume: size.x * size.y * size.z,
        box,
        studio, fill, fillAlpha, edge, edgeMat,
      });
      object.material = studio.length === 1 ? studio[0] : studio;
      object.castShadow = true;
      object.receiveShadow = true;
    });

    const buildingBox = new THREE.Box3();
    entries.forEach((entry) => { if (entry.layer !== 'site') buildingBox.union(entry.box); });
    if (buildingBox.isEmpty()) entries.forEach((entry) => buildingBox.union(entry.box));
    const center = buildingBox.getCenter(new THREE.Vector3());
    const size = buildingBox.getSize(new THREE.Vector3());
    const radius = Math.max(size.x, size.y, size.z) * 0.5 || 1;
    const maxStagger = entries.reduce((max, entry) => Math.max(max, entry.stagger), 0);

    return { root, entries, center, radius, maxStagger };
  }, [scene]);

  // The section plane cuts every wardrobe, or the cut lies depending on the mode.
  useEffect(() => {
    const planes = plane ? [plane] : null;
    built.entries.forEach((entry) => {
      entry.studio.forEach((material) => { material.clippingPlanes = planes; });
      entry.fill.clippingPlanes = planes;
      entry.edgeMat.clippingPlanes = planes;
    });
  }, [built, plane]);

  // Steady-state appearance: which wardrobe, who is visible, who recedes.
  useEffect(() => {
    built.entries.forEach((entry) => {
      const isSite = entry.layer === 'site';
      entry.mesh.visible = (showSite !== false || !isSite) && !hidden.has(entry.key);
      entry.edge.visible = mode === 'blueprint';
      entry.mesh.material = mode === 'blueprint'
        ? entry.fill
        : (entry.studio.length === 1 ? entry.studio[0] : entry.studio);

      if (!builtDone) return; // the assembly loop owns opacity until it finishes
      const dimmed = focus
        ? entry.key !== focus
        : (highlightLayer ? entry.layer !== highlightLayer && !isSite : false);
      if (mode === 'blueprint') {
        // The fill stays opaque so occlusion — the drawing itself — survives dimming.
        entry.fill.transparent = entry.fillAlpha < 1;
        entry.fill.opacity = entry.fillAlpha;
        entry.edgeMat.transparent = dimmed;
        entry.edgeMat.opacity = dimmed ? 0.08 : 1;
      } else {
        entry.studio.forEach((material) => {
          const target = material as THREE.Material & { opacity: number; transparent: boolean };
          target.transparent = dimmed;
          target.opacity = dimmed ? 0.08 : 1;
          target.depthWrite = !dimmed;
        });
      }
    });
  }, [built, builtDone, focus, hidden, highlightLayer, mode, showSite]);

  // A Play replay winds the whole clock back.
  useEffect(() => {
    animRef.current.pending = true;
    animRef.current.stage = -1;
    animRef.current.fresh = null;
  }, [buildKey]);

  // A new model under a held camera assembles only what changed: same key and same
  // size means the element carried over; anything new or resized rises in quickly.
  useEffect(() => {
    const snapshot = new Map<string, string>();
    built.entries.forEach((entry) => {
      const size = entry.box.getSize(new THREE.Vector3());
      snapshot.set(
        entry.key + '·' + entry.mesh.name,
        size.x.toFixed(2) + '/' + size.y.toFixed(2) + '/' + size.z.toFixed(2));
    });
    const previous = fingerprintRef.current;
    fingerprintRef.current = snapshot;
    if (previous === null) return; // first model: the full narrated assembly owns it

    const fresh = new Map<string, number>();
    let index = 0;
    built.entries.forEach((entry) => {
      const id = entry.key + '·' + entry.mesh.name;
      if (previous.get(id) !== snapshot.get(id)) fresh.set(id, index++);
    });
    animRef.current.pending = true;
    animRef.current.stage = -1;
    animRef.current.fresh = fresh;
  }, [built]);

  useFrame(({ clock }) => {
    const anim = animRef.current;
    if (holdRef.current) {
      // Held below ground: the score is still being written, or the lattice drawn.
      anim.pending = true;
      assemblyRef.current.live = false;
      assemblyRef.current.done = false;
      built.entries.forEach((entry) => {
        entry.mesh.position.y = entry.baseY - DROP_M;
        if (mode === 'blueprint') {
          entry.fill.transparent = true; entry.fill.opacity = 0;
          entry.edgeMat.transparent = true; entry.edgeMat.opacity = 0;
        } else {
          entry.studio.forEach((material) => {
            const target = material as THREE.Material & { opacity: number; transparent: boolean };
            target.transparent = true; target.opacity = 0;
          });
        }
      });
      if (builtDone) setPhase('building');
      return;
    }
    if (anim.pending) {
      anim.pending = false;
      anim.start = clock.getElapsedTime();
      assemblyRef.current.live = false;
      assemblyRef.current.done = false;
      if (reduced) {
        // Reduced motion: the building arrives finished, with no apology.
        built.entries.forEach((entry) => { entry.mesh.position.y = entry.baseY; });
        onAssembly?.(null);
        setPhase('done');
        return;
      }
      if (builtDone) setPhase('building');
      return;
    }
    if (builtDone) {
      assemblyRef.current.live = false;
      assemblyRef.current.done = true;
      return;
    }

    const diff = anim.fresh;
    const step = diff ? 0.06 : stepRef.current;
    const rise = diff ? 0.5 : Math.min(1.0, step * 0.45 + RISE_S * 0.6);
    const elapsed = clock.getElapsedTime() - anim.start;
    assemblyRef.current.elapsed = elapsed;
    assemblyRef.current.step = step;
    assemblyRef.current.rise = rise;
    assemblyRef.current.live = !diff;
    assemblyRef.current.done = false;
    let finished = true;
    built.entries.forEach((entry) => {
      if (diff) {
        const order = diff.get(entry.key + '·' + entry.mesh.name);
        if (order === undefined) {
          // Carried over unchanged: already standing, at full strength.
          entry.mesh.position.y = entry.baseY;
          return;
        }
        const p = Math.min(Math.max((elapsed - order * step) / rise, 0), 1);
        if (p < 1) finished = false;
        const eased = easeOutCubic(p);
        entry.mesh.position.y = entry.baseY - 6 * (1 - eased);
        if (mode === 'blueprint') {
          entry.fill.transparent = p < 1 || entry.fillAlpha < 1;
          entry.fill.opacity = eased * entry.fillAlpha;
          entry.edgeMat.transparent = p < 1;
          entry.edgeMat.opacity = eased;
        } else {
          entry.studio.forEach((material) => {
            const target = material as THREE.Material & { opacity: number; transparent: boolean };
            target.transparent = p < 1;
            target.opacity = eased;
          });
        }
        return;
      }
      const delay = entry.order * step + entry.stagger;
      const p = Math.min(Math.max((elapsed - delay) / rise, 0), 1);
      if (p < 1) finished = false;
      const eased = easeOutCubic(p);
      entry.mesh.position.y = entry.baseY - DROP_M * (1 - eased);
      if (mode === 'blueprint') {
        entry.fill.transparent = p < 1 || entry.fillAlpha < 1;
        entry.fill.opacity = eased * entry.fillAlpha;
        entry.edgeMat.transparent = p < 1;
        entry.edgeMat.opacity = eased;
      } else {
        entry.studio.forEach((material) => {
          const target = material as THREE.Material & { opacity: number; transparent: boolean };
          target.transparent = p < 1;
          target.opacity = eased;
        });
      }
    });

    const stage = Math.min(Math.floor(elapsed / step), 4);
    if (!diff && stage !== anim.stage && !finished) {
      anim.stage = stage;
      const name = Object.keys(LAYER_ORDER).find((layer) => LAYER_ORDER[layer] === stage);
      if (name) onAssembly?.(name);
    }

    const horizon = diff
      ? diff.size * step + rise + 0.3
      : 4 * step + built.maxStagger + rise + 0.5;
    if (finished || elapsed > horizon) {
      built.entries.forEach((entry) => { entry.mesh.position.y = entry.baseY; });
      anim.fresh = null;
      if (!diff) onAssembly?.(null);
      setPhase('done');
    }
  });

  /** Anchor each callout to the biggest object of its layer. */
  const anchored = useMemo<Anchored[]>(() => {
    return callouts.map((callout) => {
      const candidates = built.entries.filter((entry) => entry.layer === callout.layer
        && (!callout.subsystem || entry.key.includes(callout.subsystem)));
      const pool = candidates.length > 0
        ? candidates
        : built.entries.filter((entry) => entry.layer === callout.layer);
      if (pool.length === 0) return null;
      const host = pool.reduce((best, entry) => (entry.volume > best.volume ? entry : best));
      const boxCenter = host.box.getCenter(new THREE.Vector3());
      const anchor = callout.anchor === 'top'
        ? new THREE.Vector3(boxCenter.x, host.box.max.y, boxCenter.z)
        : boxCenter;
      return { callout, host, anchor };
    }).filter((item): item is Anchored => item !== null);
  }, [built, callouts]);

  useCalloutLayout(overlayRef, anchored, built, hidden, plane, annotate && builtDone);
  // The datum in transfer, as a dimension string across the whole lattice or layer.
  const dimension = useMemo(() => datumDimension(transfer, lattice, built), [transfer, lattice, built]);
  useTransferLeader(overlayRef, dimension);

  return (
    <>
      <primitive object={built.root} />
      <FitToModel built={built} />
      <DepthFade built={built} enabled={mode === 'blueprint'} />
      <LatticeLines lattice={lattice} mode={mode} drawKey={latticeKey} done={builtDone} />
      <DatumDimension dimension={dimension} mode={mode} />
      <HearingCloud
        hearing={hearing}
        entries={built.entries}
        plan={lattice?.plan ?? null}
        net={net}
        mode={mode}
        cloudKey={cloudKey}
        assemblyRef={assemblyRef}
        overlayRef={overlayRef}
        reduced={reduced}
      />
    </>
  );
}

interface Anchored {
  callout: ViewportCallout;
  host: Entry;
  anchor: THREE.Vector3;
}

const LABEL_PAD = 14;
const LABEL_GAP = 8;

function overlaps(a: DOMRectReadOnly, b: DOMRectReadOnly, margin: number): boolean {
  return a.left < b.right + margin && a.right > b.left - margin
    && a.top < b.bottom + margin && a.bottom > b.top - margin;
}

/**
 * Keynotes, not floating tags. Each callout's anchor is projected to the screen every
 * frame; the label itself sits in a notes column at the side of the drawing — the
 * side its element is nearer — stacked so no two labels overlap, steered around
 * everything on the stage marked `data-avoid` (the HUD, the feed, the caption), and
 * joined to its element by a leader with a dot at the end. The layout is written
 * straight to the DOM: nothing here re-renders React at 60 Hz.
 */
function useCalloutLayout(
  overlayRef: RefObject<HTMLDivElement | null>,
  anchored: Anchored[],
  built: BuiltScene,
  hidden: Set<string>,
  plane: THREE.Plane | null,
  shown: boolean,
) {
  const sideRef = useRef(new Map<string, 'left' | 'right'>());
  const frameRef = useRef(0);
  const cacheRef = useRef<{
    obstacles: DOMRectReadOnly[];
    labels: Map<string, { el: HTMLElement; leader: SVGGElement | null; w: number; h: number }>;
  }>({ obstacles: [], labels: new Map() });
  const point = useMemo(() => new THREE.Vector3(), []);

  useFrame(({ camera, size }) => {
    const overlay = overlayRef.current;
    if (!overlay) return;
    overlay.dataset.shown = shown ? '1' : '0';
    if (!shown) return;

    // Geometry reads (rects, label sizes) are the expensive part; a stale one for a
    // few frames is invisible, so they refresh at 15 Hz while positions run at 60.
    const cache = cacheRef.current;
    if (frameRef.current++ % 4 === 0 || cache.labels.size !== anchored.length) {
      const origin = overlay.getBoundingClientRect();
      const stage = overlay.parentElement ?? overlay;
      cache.obstacles = Array.from(stage.querySelectorAll<HTMLElement>('[data-avoid]'))
        .filter((el) => el.offsetParent !== null)
        .map((el) => {
          const r = el.getBoundingClientRect();
          return new DOMRectReadOnly(r.left - origin.left, r.top - origin.top, r.width, r.height);
        });
      cache.labels = new Map();
      anchored.forEach(({ callout }) => {
        const el = overlay.querySelector<HTMLElement>('[data-callout="' + callout.id + '"]');
        if (!el) return;
        const leader = overlay.querySelector<SVGGElement>('[data-leader="' + callout.id + '"]');
        cache.labels.set(callout.id, { el, leader, w: el.offsetWidth, h: el.offsetHeight });
      });
    }

    const W = size.width;
    const H = size.height;
    point.copy(built.center).project(camera);
    const centerX = ((point.x + 1) / 2) * W;

    // Project every anchor; decide its side with a little hysteresis so a label does
    // not flit across the drawing when its element hovers near the middle.
    const items = anchored.flatMap((item) => {
      const label = cache.labels.get(item.callout.id);
      if (!label) return [];
      // A note whose element is switched off, or cut away by the section plane, would
      // point at nothing — so it steps out with the element.
      const visible = !hidden.has(item.host.key)
        && !(plane && plane.distanceToPoint(item.anchor) < 0);
      point.copy(item.anchor).project(camera);
      const ax = ((point.x + 1) / 2) * W;
      const ay = ((1 - point.y) / 2) * H;
      const behind = point.z > 1;
      let side = sideRef.current.get(item.callout.id);
      const swing = W * 0.05;
      if (!side || (side === 'left' && ax > centerX + swing) || (side === 'right' && ax < centerX - swing)) {
        side = ax < centerX ? 'left' : 'right';
        sideRef.current.set(item.callout.id, side);
      }
      return [{ item, label, ax, ay, side, visible: visible && !behind }];
    });

    const placed: DOMRectReadOnly[] = [];
    (['left', 'right'] as const).forEach((side) => {
      const column = items.filter((entry) => entry.side === side && entry.visible)
        .sort((a, b) => a.ay - b.ay);
      if (column.length === 0) return;
      const labelW = column[0].label.w;
      // The column starts at the stage edge and steps inboard past anything tall
      // enough that notes could not flow around it — the HUD stack, the layers panel,
      // the feed. "Tall enough" is measured against the notes themselves rather than
      // as a share of the viewport: a share turns on the window height, and the same
      // HUD then blocks the column on a short screen and not on a tall one.
      const blocking = Math.max(160, column[0].label.h * 2 + LABEL_GAP);
      let cx = side === 'left' ? LABEL_PAD : W - LABEL_PAD - labelW;
      cache.obstacles.forEach((rect) => {
        if (rect.height < blocking) return;
        if (side === 'left' && rect.left < cx + labelW + LABEL_GAP) cx = Math.max(cx, rect.right + LABEL_GAP);
        if (side === 'right' && rect.right > cx - LABEL_GAP) cx = Math.min(cx, rect.left - LABEL_GAP - labelW);
      });

      column.forEach(({ label, ax, ay }) => {
        const desired = Math.min(Math.max(ay - label.h / 2, LABEL_PAD), H - LABEL_PAD - label.h);
        let y = desired;
        for (let k = 0; k <= 80; k += 1) {
          const candidates = k === 0 ? [desired] : [desired + k * 6, desired - k * 6];
          const fit = candidates.find((cy) => {
            if (cy < LABEL_PAD || cy + label.h > H - LABEL_PAD) return false;
            const rect = new DOMRectReadOnly(cx, cy, label.w, label.h);
            return !cache.obstacles.some((o) => overlaps(rect, o, LABEL_GAP))
              && !placed.some((p) => overlaps(rect, p, LABEL_GAP));
          });
          if (fit !== undefined) { y = fit; break; }
        }
        placed.push(new DOMRectReadOnly(cx, y, label.w, label.h));
        label.el.dataset.hidden = '0';
        label.el.style.transform = 'translate3d(' + cx.toFixed(1) + 'px,' + y.toFixed(1) + 'px,0)';
        label.el.dataset.side = side;
        if (label.leader) {
          const lx = side === 'left' ? cx + label.w : cx;
          const ly = y + Math.min(label.h / 2, 18);
          label.leader.removeAttribute('visibility');
          const line = label.leader.querySelector('line');
          const dot = label.leader.querySelector('circle');
          line?.setAttribute('x1', lx.toFixed(1));
          line?.setAttribute('y1', ly.toFixed(1));
          line?.setAttribute('x2', ax.toFixed(1));
          line?.setAttribute('y2', ay.toFixed(1));
          dot?.setAttribute('cx', ax.toFixed(1));
          dot?.setAttribute('cy', ay.toFixed(1));
        }
      });
    });

    items.filter((entry) => !entry.visible).forEach(({ label }) => {
      label.el.dataset.hidden = '1';
      label.leader?.setAttribute('visibility', 'hidden');
    });
  });
}
/**
 * The transfer leader: from the score's driving marks to the part of the building
 * they became. The strip marks its highlighted marks with `data-transfer-source`
 * (and where on itself they sit); each frame that point is joined, by a flowing
 * dashed curve, to the layer being assembled — or to the lattice's ground while the
 * lattice is drawing. It is the one line that crosses from music to architecture,
 * and it crosses only while the crossing is happening.
 */
function useTransferLeader(
  overlayRef: RefObject<HTMLDivElement | null>,
  dimension: Dimension | null,
) {
  const point = useMemo(() => new THREE.Vector3(), []);
  useFrame(({ camera, size }) => {
    const overlay = overlayRef.current;
    const stage = overlay?.parentElement;
    const path = stage?.querySelector<SVGPathElement>('.transfer-leader');
    const dot = stage?.querySelector<SVGCircleElement>('.transfer-dot');
    const label = stage?.querySelector<HTMLElement>('.transfer-label');
    if (!overlay || !stage || !path || !dot || !label) return;
    const hide = () => {
      path.setAttribute('visibility', 'hidden');
      dot.setAttribute('visibility', 'hidden');
      label.hidden = true;
    };
    const source = dimension ? stage.querySelector<HTMLElement>('[data-transfer-source]') : null;
    if (!dimension || !source) { hide(); return; }
    const origin = overlay.getBoundingClientRect();
    const rect = source.getBoundingClientRect();
    const sx = rect.left - origin.left + Number(source.dataset.transferX ?? rect.width / 2);
    const sy = rect.top - origin.top + Number(source.dataset.transferY ?? 0);
    point.copy(dimension.anchor).project(camera);
    if (point.z > 1) { hide(); return; }
    const ax = ((point.x + 1) / 2) * size.width;
    const ay = ((1 - point.y) / 2) * size.height;
    // The leader lands on the dimension's label, which floats just above its string.
    label.hidden = false;
    if (label.textContent !== dimension.text) label.textContent = dimension.text;
    label.style.left = ax.toFixed(1) + 'px';
    label.style.top = (ay - 8).toFixed(1) + 'px';
    const ly = ay - 8;
    const lift = Math.max(60, (sy - ly) * 0.45);
    path.setAttribute('d', `M ${sx.toFixed(1)} ${sy.toFixed(1)} C ${sx.toFixed(1)} ${(sy - lift).toFixed(1)}, ${ax.toFixed(1)} ${(ly + lift).toFixed(1)}, ${ax.toFixed(1)} ${ly.toFixed(1)}`);
    path.removeAttribute('visibility');
    dot.setAttribute('cx', ax.toFixed(1));
    dot.setAttribute('cy', ay.toFixed(1));
    dot.removeAttribute('visibility');
  });
}
/* eslint-enable react-hooks/immutability */

function useSectionPlane(settings: ClippingSettings): THREE.Plane | null {
  return useMemo(() => {
    if (!settings.enabled) return null;
    // The GLB is Y-up after export while the model is Z-up, so the world axes the
    // viewer names are remapped here and nowhere else.
    const normal = settings.axis === 'x'
      ? new THREE.Vector3(1, 0, 0)
      : settings.axis === 'y'
        ? new THREE.Vector3(0, 0, -1)
        : new THREE.Vector3(0, 1, 0);
    if (settings.inverted) normal.negate();
    return new THREE.Plane(normal, settings.inverted ? settings.offset : -settings.offset);
  }, [settings.axis, settings.enabled, settings.inverted, settings.offset]);
}

export function ArchitectureViewport({
  assetUrl, mode, hidden, focus, highlightLayer, clipping, showSite = true,
  programVolumes = null, callouts = [], annotate, buildKey, hold = false, stepSeconds,
  lattice = null, latticeKey = 0, transfer = null, hearing = null, cloudKey = 0, net = null,
  onReady, onAssembly, onCalloutHover, onCalloutClick,
}: ViewportProps) {
  const plane = useSectionPlane(clipping);
  const blueprint = mode === 'blueprint';
  const overlayRef = useRef<HTMLDivElement>(null);
  return (
    <>
    <Canvas
      shadows={!blueprint}
      camera={{ position: [52, 34, 60], fov: 34, near: 0.5, far: 900 }}
      dpr={[1, 1.5]}
      gl={{ antialias: true, alpha: false }}
      onCreated={({ gl }) => { gl.localClippingEnabled = true; }}
    >
      <color attach="background" args={[blueprint ? BLUEPRINT.ground : '#f5f5f7']} />
      {/* The blueprint rig is a drafting lamp: high, from the front-left, with enough
          ambient that a face in shade is still a blue and not a hole. */}
      <ambientLight intensity={blueprint ? 0.9 : 1.35} />
      <directionalLight
        castShadow={!blueprint}
        intensity={blueprint ? 1.3 : 2.15}
        position={blueprint ? [-28, 64, 44] : [34, 52, 24]}
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-56}
        shadow-camera-right={56}
        shadow-camera-top={56}
        shadow-camera-bottom={-56}
        shadow-camera-far={180}
      />
      <Suspense fallback={null}>
        <ArchitecturalModel
          assetUrl={assetUrl}
          mode={mode}
          hidden={hidden}
          focus={focus}
          highlightLayer={highlightLayer}
          plane={plane}
          showSite={showSite}
          callouts={callouts}
          annotate={annotate}
          buildKey={buildKey}
          hold={hold}
          stepSeconds={stepSeconds}
          overlayRef={overlayRef}
          lattice={lattice}
          latticeKey={latticeKey}
          transfer={transfer}
          hearing={hearing}
          cloudKey={cloudKey}
          net={net}
          onReady={onReady}
          onAssembly={onAssembly}
        />
        {programVolumes && (
          <ProgramVolumeMassing
            lattice={programVolumes.lattice}
            allocation={programVolumes.allocation}
            programVolumeModel={programVolumes.model}
            visible={programVolumes.visible}
          />
        )}
      </Suspense>
      {blueprint ? (
        // Graph paper under the drawing; the site plate outlines itself on top of it.
        <gridHelper
          args={[320, 64, BLUEPRINT.grid, BLUEPRINT.gridSoft]}
          position={[0, -0.24, 0]}
        />
      ) : (
        <mesh receiveShadow rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.22, 0]}>
          <planeGeometry args={[220, 220]} />
          <shadowMaterial color="#111111" opacity={0.1} />
        </mesh>
      )}
      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.08}
        minDistance={6}
        maxDistance={400}
        maxPolarAngle={Math.PI / 2.02}
      />
    </Canvas>
    {/* The keynote layer: laid out by useCalloutLayout, frame by frame. */}
    {/* The one line from music to architecture, drawn only while the crossing happens. */}
    <div className="transfer-layer" aria-hidden="true">
      <svg className="transfer-svg">
        <path className="transfer-leader" d="M0 0" visibility="hidden" />
        <circle className="transfer-dot" r="4" visibility="hidden" />
      </svg>
      <div className="transfer-label" hidden />
    </div>
    <div ref={overlayRef} className="callout-layer" data-shown="0" aria-hidden={!annotate}>
      <svg className="callout-leaders" aria-hidden="true">
        {callouts.map((callout) => (
          <g key={callout.id} data-leader={callout.id} visibility="hidden">
            <line x1="0" y1="0" x2="0" y2="0" />
            <circle cx="0" cy="0" r="3.5" />
          </g>
        ))}
      </svg>
      {callouts.map((callout) => (
        <button
          key={callout.id}
          type="button"
          className="callout"
          data-callout={callout.id}
          data-hidden="1"
          onPointerEnter={() => onCalloutHover?.(callout.layer)}
          onPointerLeave={() => onCalloutHover?.(null)}
          onMouseEnter={() => onCalloutHover?.(callout.layer)}
          onMouseLeave={() => onCalloutHover?.(null)}
          onClick={() => onCalloutClick?.(callout.id)}
        >
          <i>{callout.index}</i>
          <b>{callout.title}</b>
          <span>{callout.body}</span>
        </button>
      ))}
    </div>
    </>
  );
}
