import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { SceneProfile } from "@/hooks/useSceneProfile";
import type { UniverseRuntime } from "./universeRuntime";
import {
  CLUSTERS,
  UNIVERSE_YEARS,
  OLD_YEAR,
  BOUNDARY_Z,
  ARCHIVE_Z,
  OLD_DRIFT_Y,
  PALETTE,
  smoothstep,
} from "./universeConfig";
import { GEOMETRY, buildEntities, type Entity, type EntityKind } from "./emailEntities";
import { PANEL_VERT, PANEL_FRAG, PANEL_UNIFORMS } from "./shaders";

/* ============================================================================
   The instanced email field. Three geometry classes share one shader material
   → 3 draw calls for the entire email population. Positions are recomposed on
   the CPU each frame: chaos → cluster (analyze) → old drift (5-year moment).
   ========================================================================== */
export function EmailField({ profile, runtime }: { profile: SceneProfile; runtime: UniverseRuntime }) {
  const count = Math.round(profile.particleBudget);
  const data = useMemo(() => buildEntities(count, 20260701), [count]);

  const sheetRef = useRef<THREE.InstancedMesh>(null);
  const slatRef = useRef<THREE.InstancedMesh>(null);
  const cardRef = useRef<THREE.InstancedMesh>(null);

  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: PANEL_VERT,
        fragmentShader: PANEL_FRAG,
        uniforms: THREE.UniformsUtils.clone(PANEL_UNIFORMS),
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
      }),
    []
  );

  const dummy = useMemo(() => new THREE.Object3D(), []);
  const colorTmp = useMemo(() => new THREE.Color(), []);
  const posTmp = useMemo(() => new THREE.Vector3(), []);
  const blueTmp = useMemo(() => new THREE.Color(PALETTE.dataBlue), []);
  const amberTmp = useMemo(() => new THREE.Color(PALETTE.safetyAmberDim), []);

  // bake per-instance colors once (deterministic)
  useEffect(() => {
    const byKind: Record<EntityKind, Entity[]> = { sheet: [], slat: [], card: [] };
    for (const e of data.entities) byKind[e.kind].push(e);
    const meshes: Array<[EntityKind, React.RefObject<THREE.InstancedMesh>]> = [
      ["sheet", sheetRef],
      ["slat", slatRef],
      ["card", cardRef],
    ];
    for (const [kind, ref] of meshes) {
      const mesh = ref.current;
      if (!mesh) continue;
      byKind[kind].forEach((e, i) => {
        colorTmp.copy(e.color);
        mesh.setColorAt(i, colorTmp);
      });
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    }
  }, [data, colorTmp]);

  useFrame(() => {
    const u = material.uniforms;
    u.uTime.value = runtime.time;
    u.uScan.value = runtime.scan;
    u.uScanZ.value = runtime.scanFront;
    u.uTemporal.value = runtime.temporal;
    u.uBoundaryZ.value = BOUNDARY_Z;
    u.uClarity.value = runtime.clarity;
    u.uFogDepth.value = 120;
    // THREE accepts a Color object for a vec3 uniform — cheaper than arrays.
    u.uDataBlue.value = blueTmp;
    u.uAmber.value = amberTmp;

    const settle = smoothstep(0.15, 0.7, runtime.organize);
    const old = smoothstep(0.1, 0.85, runtime.temporal);
    const reduced = runtime.reduced;
    const t = runtime.time;

    const byKind: Record<EntityKind, Entity[]> = { sheet: [], slat: [], card: [] };
    for (const e of data.entities) byKind[e.kind].push(e);

    const draw = (
      _kind: EntityKind,
      list: Entity[],
      mesh: THREE.InstancedMesh | null
    ) => {
      if (!mesh) return;
      for (let i = 0; i < list.length; i++) {
        const e = list[i];
        const [ax, ay, az] = CLUSTERS[e.cluster].anchor;

        // organised target: anchor + local (incl. year-ring z offset)
        posTmp.set(ax, ay, az).add(e.local);

        // older-than-5-years: slide onto the archive plane past the boundary
        const isOld = e.year >= UNIVERSE_YEARS.indexOf(OLD_YEAR);
        if (isOld) {
          posTmp.z = posTmp.z + (ARCHIVE_Z - posTmp.z) * old;
          posTmp.y -= OLD_DRIFT_Y * old;
          posTmp.x *= 1 - 0.25 * old; // archive zone drifts slightly inward
        }

        // chaos → organised blend
        const px = e.chaos.x + (posTmp.x - e.chaos.x) * settle;
        const py = e.chaos.y + (posTmp.y - e.chaos.y) * settle;
        const pz = e.chaos.z + (posTmp.z - e.chaos.z) * settle;

        // coordinated micro-motion; chaos-stage flutter before analysis
        const microY = reduced ? 0 : Math.sin(t * e.floatSpeed * 0.22 + e.phase) * 0.12;
        const microX = reduced ? 0 : Math.cos(t * e.floatSpeed * 0.14 + e.phase * 1.7) * 0.09;
        const flutter = reduced ? 0 : (1 - settle) * Math.sin(t * 1.3 + e.phase * 3.1) * 0.5;

        dummy.position.set(px + microX + flutter, py + microY, pz);
        dummy.rotation.set(0, e.rotY + (reduced ? 0 : Math.sin(t * 0.1 + e.phase) * 0.08), e.rotZ);
        dummy.scale.setScalar(e.scale * (isOld && old > 0.4 ? 0.82 : 1));
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
      }
      mesh.instanceMatrix.needsUpdate = true;
    };

    draw("sheet", byKind.sheet, sheetRef.current);
    draw("slat", byKind.slat, slatRef.current);
    draw("card", byKind.card, cardRef.current);
  });

  return (
    <group>
      <instancedMesh ref={sheetRef} args={[GEOMETRY.sheet, material, data.counts.sheet]} frustumCulled={false} />
      <instancedMesh ref={slatRef} args={[GEOMETRY.slat, material, data.counts.slat]} frustumCulled={false} />
      <instancedMesh ref={cardRef} args={[GEOMETRY.card, material, data.counts.card]} frustumCulled={false} />
    </group>
  );
}