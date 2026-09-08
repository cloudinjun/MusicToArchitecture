'use client';

/**
 * Clumps of particles leave the cloud and build the building, layer by layer.
 *
 * The lab's mass is the recording; this is the recording becoming the model. The
 * run's GLB is sampled by surface area, layer by layer — site, structure, envelope,
 * circulation, program — and every sample point is a particle that waits inside the
 * cloud until its clump's turn: then the clump leaves from one spot of the cloud
 * together, arcs across, and settles on its element. Layer after layer the building
 * stands beside the cloud as points; when it is complete it holds for a while, fades,
 * and the cycle begins again — the cloud never stops giving.
 *
 * All motion is a pure function of the clock (a cycle, a birth per particle, a
 * flight time), so it costs nothing per frame beyond the draw.
 */

import { useEffect, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import * as THREE from 'three';
import { MeshSurfaceSampler } from 'three/examples/jsm/math/MeshSurfaceSampler.js';

export const BUILD_X = 0;
export const BUILD_Z = -15;
export const BUILD_HEIGHT = 26;
export const BUILD_BASE_Y = -13;
/** The cloud hangs in front of it, on the same axis. */
export const CLOUD_Z = 11;
/** Where it withdraws to while the building stands: well behind it. */
export const CLOUD_BACK_Z = -46;
const LAYERS = ['site', 'structure', 'envelope', 'circulation', 'program'];
/** The cloud has the stage to itself until this moment; then the casting starts. */
export const BUILD_START = 6.0;
export const LAYER_S = 3.0;
export const HOLD_S = 4.0;
export const FADE_S = 3.2;
/** The building is wholly gone this long before the cycle ends, leaving the cloud alone. */
export const TAIL_S = 1.6;
const FLIGHT_S = 2.6;
const COUNT = 60000;
export const CYCLE = BUILD_START + LAYERS.length * LAYER_S + HOLD_S;
/** Where the threads leave from: the cloud, which does not move. */
export const CLOUD_CENTRE = new THREE.Vector3(0, 0, CLOUD_Z);

function semanticLayer(object: THREE.Object3D): string {
  let current: THREE.Object3D | null = object;
  while (current) {
    const value = current.userData['mta:layer'] ?? current.userData['mta_layer'];
    if (typeof value === 'string' && value) return value;
    current = current.parent;
  }
  return 'site';
}

function meshArea(mesh: THREE.Mesh): number {
  const position = mesh.geometry.getAttribute('position');
  if (!position) return 0;
  const index = mesh.geometry.getIndex();
  const a = new THREE.Vector3(); const b = new THREE.Vector3(); const c = new THREE.Vector3();
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

const VERTEX = /* glsl */`
attribute vec3 aStart;
attribute vec3 aTarget;
attribute float aLayer;
attribute float aBirth;
attribute float aSeed;
uniform float uTime;
uniform float uCycle;
uniform float uFlight;
uniform float uFade;
uniform float uPixelRatio;
uniform vec3 uCloud;
uniform float uFocus;
varying float vAlpha;
varying float vLayer;
varying float vFly;
varying float vSpark;
varying float vSeed;
void main() {
  float local = mod(uTime, uCycle);
  float t = (local - aBirth) / uFlight;
  float end = 1.0 - smoothstep(uCycle - uFade, uCycle - 1.6, local);
  if (t < 0.0 || end <= 0.0) {
    vAlpha = 0.0; vLayer = aLayer; vFly = 0.0; vSpark = 0.0; vSeed = aSeed;
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    gl_PointSize = 0.0;
    return;
  }
  float f = clamp(t, 0.0, 1.0);
  float e = f * f * (3.0 - 2.0 * f);
  // Every thread is drawn out of the cloud's own heart: one source, a hand's breadth
  // wide, so the stream reads as coming from the mass and not from the air near it.
  vec3 from = uCloud + normalize(aStart + vec3(0.0001)) * (0.25 + 0.55 * aSeed);
  // A graceful arc, and a helix around it that tightens as it lands.
  vec3 mid = mix(from, aTarget, 0.5) + vec3(0.0, 8.0 + 5.0 * aSeed, 0.0);
  vec3 pos = mix(mix(from, mid, e), mix(mid, aTarget, e), e);
  vec3 axis = normalize(aTarget - from + vec3(0.0001));
  vec3 side = normalize(cross(axis, vec3(0.0, 1.0, 0.0)) + vec3(0.0001));
  vec3 upP = cross(side, axis);
  float ang = f * 14.0 + aSeed * 6.2832;
  float rad = (1.0 - f) * f * 2.6 + 0.12;
  pos += (side * cos(ang) + upP * sin(ang)) * rad;
  float flying = 1.0 - step(1.0, t);
  float twinkle = 0.62 + 0.38 * sin(uTime * 7.0 + aSeed * 90.0);
  float spark = exp(-max(0.0, t - 1.0) * uFlight * 2.5);
  vFly = flying;
  vSeed = aSeed;
  vSpark = spark * (1.0 - flying);
  // Settled points come forward with the focus; the flying dust always reads.
  // In flight the dust is as quiet as the cloud it came from; it only gains weight
  // when it lands.
  vAlpha = end * mix((0.5 + 0.32 * spark) * (0.3 + 0.7 * uFocus), 0.22 * twinkle, flying);
  vLayer = aLayer;
  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  float size = mix(0.9 + 1.3 * spark, (0.55 + 0.6 * aSeed) * (0.6 + 0.6 * twinkle), flying);
  gl_PointSize = min(size * uPixelRatio * (150.0 / -mv.z), 4.2 * uPixelRatio);
  gl_Position = projectionMatrix * mv;
}
`;

const FRAGMENT = /* glsl */`
uniform vec3 uColors[5];
uniform vec3 uDustLow;
uniform vec3 uDustHigh;
varying float vAlpha;
varying float vLayer;
varying float vFly;
varying float vSpark;
varying float vSeed;
void main() {
  if (vAlpha <= 0.0) discard;
  vec2 d = gl_PointCoord - 0.5;
  float r = dot(d, d);
  if (r > 0.25) discard;
  float soft = smoothstep(0.25, 0.04, r);
  int k = int(clamp(vLayer + 0.5, 0.0, 4.0));
  vec3 color = uColors[0];
  for (int i = 1; i < 5; i++) { if (i == k) color = uColors[i]; }
  // In flight the dust wears the cloud's own lilac and pale blue, so the stream and
  // the mass read as one material; the white spark marks the landing, and only the
  // settled point takes its layer's colour.
  vec3 dust = mix(uDustLow, uDustHigh, vSeed);
  color = mix(mix(color, vec3(1.0), vSpark * 0.85), dust, vFly);
  gl_FragColor = vec4(color, vAlpha * soft);
}
`;

/** The show's clock: null until the listener presses play, then the cycle's origin. */
export interface Show { start: number | null; focus: number; centre: THREE.Vector3 }

export function Builders({ url, show }: { url: string; show: { current: Show } }) {
  const { scene } = useGLTF(url);

  const cloud = useMemo(() => {
    // Fit the model beside the cloud: BUILD_HEIGHT tall, standing on BUILD_BASE_Y.
    scene.updateMatrixWorld(true);
    const bounds = new THREE.Box3().setFromObject(scene);
    const size = bounds.getSize(new THREE.Vector3());
    const scale = BUILD_HEIGHT / Math.max(size.y, 1e-3);
    const centre = bounds.getCenter(new THREE.Vector3());
    const fit = new THREE.Matrix4().makeScale(scale, scale, scale);
    const shift = new THREE.Matrix4().makeTranslation(BUILD_X - centre.x * scale, BUILD_BASE_Y - bounds.min.y * scale, BUILD_Z - centre.z * scale);
    const world = shift.multiply(fit);

    const meshes: Array<{ mesh: THREE.Mesh; layer: number; area: number }> = [];
    scene.traverse((object) => {
      if (!(object instanceof THREE.Mesh)) return;
      const layer = LAYERS.indexOf(semanticLayer(object));
      meshes.push({ mesh: object, layer: layer < 0 ? 0 : layer, area: meshArea(object) });
    });
    const areaByLayer = LAYERS.map((_, l) => meshes.filter((m) => m.layer === l).reduce((sum, m) => sum + m.area, 0));
    const present = areaByLayer.filter((a) => a > 0).length || 1;
    const perLayerFull = Math.floor(COUNT / present);

    const start = new Float32Array(COUNT * 3);
    const target = new Float32Array(COUNT * 3);
    const layerAttr = new Float32Array(COUNT);
    const birth = new Float32Array(COUNT);
    const seed = new Float32Array(COUNT);
    let s = 17;
    const random = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
    const point = new THREE.Vector3();
    let i = 0;
    LAYERS.forEach((_, l) => {
      if (areaByLayer[l] <= 0) return;
      const layerStart = BUILD_START + l * LAYER_S;
      const perLayer = l === 0 ? Math.floor(perLayerFull * 0.35) : perLayerFull;
      const own = meshes.filter((m) => m.layer === l);
      // Each mesh gets particles by its share of the layer's area, capped so no slab hogs.
      const shares = own.map((m) => Math.min(m.area / areaByLayer[l], 0.04));
      const shareSum = shares.reduce((sum, v) => sum + v, 0);
      const counts = shares.map((v) => Math.round((perLayer * v) / shareSum));
      let placedInLayer = 0;
      own.forEach((entry, m) => {
        const count = counts[m];
        if (count === 0) return;
        entry.mesh.updateWorldMatrix(true, false);
        const sampler = new MeshSurfaceSampler(entry.mesh).build();
        for (let k = 0; k < count && i < COUNT; k += 1, i += 1, placedInLayer += 1) {
          sampler.sample(point);
          point.applyMatrix4(entry.mesh.matrixWorld).applyMatrix4(world);
          target[i * 3] = point.x; target[i * 3 + 1] = point.y; target[i * 3 + 2] = point.z;
          // A random point of the cloud (the thread is drawn toward the wand's tip in the
          // shader), and a birth spread evenly through the layer's window, element after
          // element — the wand traces the building.
          const a = random() * 6.2832; const c = random() * 2 - 1; const sn = Math.sqrt(1 - c * c);
          const r = 3 + 6 * random();
          start[i * 3] = sn * Math.cos(a) * r;
          start[i * 3 + 1] = c * r * 1.3;
          start[i * 3 + 2] = sn * Math.sin(a) * r;
          layerAttr[i] = l;
          birth[i] = layerStart + (placedInLayer / Math.max(1, perLayer)) * (LAYER_S - 0.3) + random() * 0.08;
          seed[i] = random();
        }
      });
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(COUNT * 3), 3));
    geometry.setAttribute('aStart', new THREE.BufferAttribute(start, 3));
    geometry.setAttribute('aTarget', new THREE.BufferAttribute(target, 3));
    geometry.setAttribute('aLayer', new THREE.BufferAttribute(layerAttr, 1));
    geometry.setAttribute('aBirth', new THREE.BufferAttribute(birth, 1));
    geometry.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1));
    geometry.setDrawRange(0, i);
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(BUILD_X / 2, 0, 0), 200);
    const material = new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 }, uCycle: { value: CYCLE }, uFlight: { value: FLIGHT_S }, uFade: { value: FADE_S }, uPixelRatio: { value: 1 },
        uCloud: { value: CLOUD_CENTRE.clone() }, uFocus: { value: 0 },
        uDustLow: { value: new THREE.Color('#c9a6ec') }, uDustHigh: { value: new THREE.Color('#9fc0ff') },
        // Kin to the cloud: the same lilac and pale blue, parted only enough to tell
        // the layers apart.
        uColors: { value: [
          new THREE.Color('#7e8bb0'), new THREE.Color('#cfd8f2'), new THREE.Color('#a8c6f0'),
          new THREE.Color('#e0c9a8'), new THREE.Color('#c3aee8'),
        ] },
      },
      vertexShader: VERTEX, fragmentShader: FRAGMENT,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    return { geometry, material, count: i };
  }, [scene]);
  useEffect(() => () => { cloud.geometry.dispose(); cloud.material.dispose(); }, [cloud]);

  useFrame(({ clock, gl }) => {
    const started = show.current.start;
    cloud.material.uniforms.uTime.value = started === null ? 0 : clock.getElapsedTime() - started;
    cloud.material.uniforms.uPixelRatio.value = gl.getPixelRatio();
    cloud.material.uniforms.uFocus.value = show.current.focus;
    // The source follows the cloud's own centre, measured from the simulation.
    (cloud.material.uniforms.uCloud.value as THREE.Vector3).lerp(show.current.centre, 0.12);
  });

  return <points geometry={cloud.geometry} material={cloud.material} frustumCulled={false} renderOrder={3} />;
}
