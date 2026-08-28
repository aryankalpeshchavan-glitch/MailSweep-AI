import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { UniverseRuntime } from "./universeRuntime";
import { CLUSTERS, PALETTE, smoothstep } from "./universeConfig";
import { mulberry32 } from "./seed";

/* ============================================================================
   Data trails — thin low-opacity lines connecting related clusters ("data
   flow" not laser beams), with a handful of particles travelling along the
   routes. Draw calls: 1 line + 1 point cloud. Opacity ramps up as analysis
   organises the mailbox and peaks on classification labels.
   ========================================================================== */

const HUB: [number, number, number] = [0, 0, 26];

/** build a deterministic trail network between clusters + the hub */
function buildTrails() {
  const rng = mulberry32(4242);
  const pts: number[] = [];
  const clusters = CLUSTERS.map((c) => c.anchor);
  const routes: Array<[THREE.Vector3, THREE.Vector3]> = [];

  const push = (a: [number, number, number], b: [number, number, number]) => {
    // each route gets a little sag so it reads as an organic pathway
    routes.push([new THREE.Vector3(...a), new THREE.Vector3(...b)]);
  };

  // hub → every cluster
  for (const c of clusters) push(HUB, c);
  // rings between adjacent clusters (promotions↔newsletters, social↔notifications…)
  push(clusters[2], clusters[4]); // promotions ↔ newsletters
  push(clusters[5], clusters[1]); // social ↔ notifications
  push(clusters[3], clusters[0]); // personal ↔ important
  push(clusters[1], clusters[5]); // notifications ↔ social (denser exchange)

  for (const [a, b] of routes) {
    const mid = a.clone().lerp(b, 0.5);
    mid.x += (rng() - 0.5) * 2.4;
    mid.y += (rng() - 0.5) * 2.4;
    // quad bezier
    const steps = 24;
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const p = quadBezier(a, mid, b, t);
      pts.push(p.x, p.y, p.z);
    }
  }

  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));

  // travelling particles
  const pCount = 40;
  const pPos = new Float32Array(pCount * 3);
  const pMeta = new Float32Array(pCount * 2); // route + progress
  for (let i = 0; i < pCount; i++) {
    pMeta[i * 2] = Math.floor(rng() * routes.length);
    pMeta[i * 2 + 1] = rng();
  }
  const pGeom = new THREE.BufferGeometry();
  pGeom.setAttribute("position", new THREE.BufferAttribute(pPos, 3));

  return { geom, pGeom, pMeta, pPos, routes };
}

function quadBezier(a: THREE.Vector3, mid: THREE.Vector3, b: THREE.Vector3, t: number) {
  const mt = 1 - t;
  return new THREE.Vector3(
    mt * mt * a.x + 2 * mt * t * mid.x + t * t * b.x,
    mt * mt * a.y + 2 * mt * t * mid.y + t * t * b.y,
    mt * mt * a.z + 2 * mt * t * mid.z + t * t * b.z
  );
}

export function DataTrails({ runtime }: { runtime: UniverseRuntime }) {
  const { geom, pGeom, pMeta, pPos, routes } = useMemo(buildTrails, []);
  const pointsRef = useRef<THREE.Points>(null);
  const midTmp = useMemo(() => new THREE.Vector3(), []);
  const aTmp = useMemo(() => new THREE.Vector3(), []);
  const bTmp = useMemo(() => new THREE.Vector3(), []);

  const lineMat = useMemo(
    () =>
      new THREE.LineBasicMaterial({
        color: PALETTE.dataBlue,
        transparent: true,
        opacity: 0.05,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    []
  );
  const pMat = useMemo(
    () =>
      new THREE.PointsMaterial({
        color: PALETTE.dataBlueDim,
        size: 0.14,
        transparent: true,
        opacity: 0.0,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        sizeAttenuation: true,
      }),
    []
  );

  const lineObj = useMemo(() => new THREE.Line(geom, lineMat), [geom, lineMat]);

  useFrame(() => {
    const active = smoothstep(0.25, 0.7, runtime.organize);
    const classify = runtime.classify;
    const clarity = runtime.clarity;
    const reduced = runtime.reduced;

    lineMat.opacity = 0.03 + active * 0.09 - clarity * 0.04;
    const pOpacity = reduced ? 0 : (active * 0.55 + classify * 0.4) * (1 - clarity * 0.3);
    pMat.opacity = Math.max(0, pOpacity);

    if (!reduced) {
      for (let i = 0; i < pMeta.length / 2; i++) {
        const route = routes[Math.floor(pMeta[i * 2])];
        if (!route) continue;
        const prog = (pMeta[i * 2 + 1] + runtime.delta * (0.05 + active * 0.06)) % 1;
        pMeta[i * 2 + 1] = prog;
        aTmp.copy(route[0]);
        bTmp.copy(route[1]);
        midTmp.copy(aTmp).lerp(bTmp, 0.5);
        midTmp.x += Math.sin(route[0].x * 3.0 + route[0].z * 0.1) * 1.2;
        midTmp.y += Math.cos(route[1].z * 0.2) * 1.2;
        const p = quadBezier(aTmp, midTmp, bTmp, prog);
        pPos[i * 3] = p.x;
        pPos[i * 3 + 1] = p.y;
        pPos[i * 3 + 2] = p.z;
      }
      (pGeom.attributes.position as THREE.BufferAttribute).needsUpdate = true;
    }
  });

  return (
    <group>
      <primitive object={lineObj} />
      <points ref={pointsRef} geometry={pGeom} material={pMat} frustumCulled={false} />
    </group>
  );
}