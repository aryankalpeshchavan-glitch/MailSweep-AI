import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { UniverseRuntime } from "./universeRuntime";
import { CLUSTERS, SCENE_NEAR_Z, SCENE_FAR_Z, PALETTE, smoothstep, gauss } from "./universeConfig";
import { drawLabelTexture } from "./canvasTextures";

/* ============================================================================
   Scan system — the MailSweep "analysis" moment. A thin data-blue sweep band
   travels from near to far as analysis progresses; cluster labels surface one
   by one as the scan classifies each category. Reads runtime phases only.
   ========================================================================== */
export function ScanSystem({ runtime }: { runtime: UniverseRuntime }) {
  const bandRef = useRef<THREE.Mesh>(null);
  const edgeRef = useRef<THREE.Mesh>(null);

  const bandGeo = useMemo(() => new THREE.PlaneGeometry(120, 60), []);
  const bandMat = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: PALETTE.dataBlue,
        transparent: true,
        opacity: 0,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
      }),
    []
  );
  const edgeMat = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: PALETTE.dataBlueDim,
        transparent: true,
        opacity: 0,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
      }),
    []
  );

  // classification label sprites (one per cluster), canvas-drawn
  const labels = useMemo(
    () =>
      CLUSTERS.map((c) => {
        const mat = new THREE.SpriteMaterial({
          map: drawLabelTexture(c.label, c.accent),
          transparent: true,
          depthWrite: false,
          opacity: 0,
        });
        return { def: c, sprite: new THREE.Sprite(mat), mat };
      }),
    []
  );

  useFrame(() => {
    const scan = runtime.scan;
    // scan front travels the full depth of the scene as analysis proceeds
    const front = SCENE_NEAR_Z + (SCENE_FAR_Z - SCENE_NEAR_Z) * smoothstep(0.15, 0.8, runtime.organize);
    runtime.scanFront = front;

    if (bandRef.current) {
      bandRef.current.position.z = front;
      bandMat.opacity = scan * 0.10;
      bandRef.current.lookAt(bandRef.current.position.x, bandRef.current.position.y, front + 1);
    }
    if (edgeRef.current) {
      edgeRef.current.position.z = front + 1.2;
      edgeMat.opacity = scan * 0.28;
      edgeRef.current.lookAt(edgeRef.current.position.x, edgeRef.current.position.y, front + 2);
    }

    // sequential classification: each cluster's label lights up as the scan
    // front reaches it, then fades back after the card clusters form
    for (const l of labels) {
      const [x, y, z] = l.def.anchor;
      l.sprite.position.set(x, y + 4.6, z - 2);
      const distanceFromFront = Math.abs(z - front);
      const pulse = gauss(distanceFromFront, 0, 5) * runtime.scan;
      l.sprite.material.opacity = Math.max(0, pulse * 0.9);
      l.sprite.scale.setScalar(5);
    }
  });

  return (
    <group>
      <mesh ref={bandRef} geometry={bandGeo} material={bandMat} frustumCulled={false} />
      <mesh ref={edgeRef} geometry={bandGeo} material={edgeMat} frustumCulled={false} />
      {labels.map((l) => (
        <primitive key={l.def.id} object={l.sprite} />
      ))}
    </group>
  );
}