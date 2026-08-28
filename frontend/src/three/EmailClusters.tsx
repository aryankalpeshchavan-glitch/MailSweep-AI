import { useMemo } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import type { UniverseRuntime } from "./universeRuntime";
import { CLUSTERS, gauss, smoothstep } from "./universeConfig";
import { drawGlowTexture } from "./canvasTextures";

/* ============================================================================
   Email clusters — the "galaxy" anchors. Each category gets a soft halo of its
   accent colour at its cluster centre; the halos stay barely-visible until the
   scan classifies that group, then pulse once and settle. They give the eye a
   point of reference as objects visibly reorganise into groups.
   ========================================================================== */
export function EmailClusters({ runtime }: { runtime: UniverseRuntime }) {
  const { camera } = useThree();

  const halos = useMemo(
    () =>
      CLUSTERS.map((def) => {
        const tex = drawGlowTexture(128);
        const mat = new THREE.SpriteMaterial({
          map: tex,
          color: def.accent,
          transparent: true,
          opacity: 0,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        });
        const s = new THREE.Sprite(mat);
        const [x, y, z] = def.anchor;
        s.position.set(x, y, z - 4);
        s.scale.setScalar(8);
        return { def, sprite: s, mat, progress: 0 };
      }),
    []
  );

  useFrame(() => {
    const scan = runtime.scan;
    const organize = smoothstep(0.15, 0.7, runtime.organize);
    const reduced = runtime.reduced;
    const t = runtime.time;
    for (const h of halos) {
      const [, , z] = h.def.anchor;
      // halo surfaces around the scan front sweeping past the cluster
      const front = runtime.scanFront;
      const pass = gauss(z - front, 0, 4) * scan;
      h.progress = THREE.MathUtils.lerp(h.progress, Math.max(pass, organize * 0.18), 0.04);
      const proximityFade = gauss(-(camera.position.z - z), 0, 22);
      h.mat.opacity = reduced ? organize * 0.15 : Math.min(0.4, h.progress * (0.6 + proximityFade * 0.6));
      // gentle cluster pulsation
      const pulse = reduced ? 0 : Math.sin(t * 0.3 + h.progress * 3.0) * 0.5;
      h.sprite.scale.setScalar(8 + pulse);
    }
  });

  return (
    <group>
      {halos.map((h) => (
        <primitive key={h.def.id} object={h.sprite} />
      ))}
    </group>
  );
}