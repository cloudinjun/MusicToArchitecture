'use client';

import { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Html, Line, OrbitControls, useGLTF } from '@react-three/drei';
import * as THREE from 'three';
import type { ClippingSettings } from '../lib/types';

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
  clipping: ClippingSettings;
  showSite?: boolean;
  /** Leader-line annotations, shown once assembly has finished. */
  callouts?: ViewportCallout[];
  annotate?: boolean;
  /** Bump to replay the assembly sequence. */
  buildKey?: number;
  /** Seconds per construction stage; the narrated performance slows this down. */
  stepSeconds?: number;
  onReady?: () => void;
  /** Narrates the assembly: the semantic layer being built, or null when done. */
  onAssembly?: (layer: string | null) => void;
  onCalloutHover?: (layer: string | null) => void;
  onCalloutClick?: (id: string) => void;
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
  fill: '#123a7c',
  line: '#dbe9ff',
  grid: '#1c4489',
  gridSoft: '#16407f',
};

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
  fill: THREE.MeshBasicMaterial;
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

function ArchitecturalModel({
  assetUrl, mode, hidden, focus, highlightLayer, plane, showSite, callouts = [],
  annotate = true, buildKey = 0, stepSeconds = STEP_S,
  onReady, onAssembly, onCalloutHover, onCalloutClick,
}: Omit<ViewportProps, 'clipping'> & { plane: THREE.Plane | null }) {
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
  const reduced = useMemo(
    () => typeof window !== 'undefined'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    []);

  useEffect(() => { onReady?.(); }, [onReady, scene]);

  /**
   * One construction pass per GLB: clone the scene, and give every mesh its two
   * wardrobes — the exporter's materials for studio, and an opaque ground-colour fill
   * plus a white edge overlay for blueprint. The opaque fill is what makes blueprint
   * read as a drawing: it occludes the line work behind it, which is hidden-line
   * removal by the oldest trick there is.
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
      const order = LAYER_ORDER[layer] ?? 2;

      const studio = (Array.isArray(object.material) ? object.material : [object.material])
        .map((material) => {
          const next = material.clone();
          next.side = THREE.DoubleSide;
          next.clipShadows = true;
          return next;
        });

      const fill = new THREE.MeshBasicMaterial({
        color: BLUEPRINT.fill, side: THREE.DoubleSide,
        polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
      });
      const edgeMat = new THREE.LineBasicMaterial({ color: BLUEPRINT.line });
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
        studio, fill, edge, edgeMat,
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
        entry.fill.transparent = false;
        entry.fill.opacity = 1;
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
    if (anim.pending) {
      anim.pending = false;
      anim.start = clock.getElapsedTime();
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
    if (builtDone) return;

    const diff = anim.fresh;
    const step = diff ? 0.06 : stepRef.current;
    const rise = diff ? 0.5 : Math.min(1.0, step * 0.45 + RISE_S * 0.6);
    const elapsed = clock.getElapsedTime() - anim.start;
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
          entry.fill.transparent = p < 1;
          entry.fill.opacity = eased;
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
        entry.fill.transparent = p < 1;
        entry.fill.opacity = eased;
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

  /** Anchor each callout to the biggest object of its layer, label pushed outward. */
  const anchored = useMemo(() => {
    return callouts.map((callout, index) => {
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
      // Fan the labels around the building rather than letting them pile on the
      // roof: each one takes its anchor's outward bearing, rotated into its own
      // sector, pushed well clear of the envelope, and stepped in height.
      const out = new THREE.Vector3(anchor.x - built.center.x, 0, anchor.z - built.center.z);
      if (out.lengthSq() < 0.01) out.set(1, 0, 0.4);
      out.normalize();
      const sector = (index - (callouts.length - 1) / 2) * 1.05;
      out.applyAxisAngle(new THREE.Vector3(0, 1, 0), sector);
      const label = anchor.clone()
        .add(out.multiplyScalar(built.radius * 0.7))
        .add(new THREE.Vector3(0, built.radius * 0.2 + index * 3.2, 0));
      return { callout, host, anchor, label };
    }).filter((item): item is NonNullable<typeof item> => item !== null);
  }, [built, callouts]);

  const lineColor = mode === 'blueprint' ? BLUEPRINT.line : '#3a3a3f';

  return (
    <>
      <primitive object={built.root} />
      <FitToModel built={built} />
      {annotate && builtDone && anchored.map(({ callout, host, anchor, label }) => (
        !hidden.has(host.key) && (
          <group key={callout.id}>
            <Line
              points={[anchor.toArray(), label.toArray()]}
              color={lineColor}
              lineWidth={1}
              transparent
              opacity={0.85}
            />
            <Html position={label.toArray()} zIndexRange={[24, 10]} style={{ pointerEvents: 'none' }}>
              <button
                type="button"
                className="callout"
                style={{ pointerEvents: 'auto' }}
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
            </Html>
          </group>
        )
      ))}
    </>
  );
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
  callouts, annotate, buildKey, stepSeconds,
  onReady, onAssembly, onCalloutHover, onCalloutClick,
}: ViewportProps) {
  const plane = useSectionPlane(clipping);
  const blueprint = mode === 'blueprint';
  return (
    <Canvas
      shadows={!blueprint}
      camera={{ position: [52, 34, 60], fov: 34, near: 0.5, far: 900 }}
      dpr={[1, 1.5]}
      gl={{ antialias: true, alpha: false }}
      onCreated={({ gl }) => { gl.localClippingEnabled = true; }}
    >
      <color attach="background" args={[blueprint ? BLUEPRINT.ground : '#f5f5f7']} />
      <ambientLight intensity={1.35} />
      <directionalLight
        castShadow={!blueprint}
        intensity={2.15}
        position={[34, 52, 24]}
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
          stepSeconds={stepSeconds}
          onReady={onReady}
          onAssembly={onAssembly}
          onCalloutHover={onCalloutHover}
          onCalloutClick={onCalloutClick}
        />
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
  );
}
