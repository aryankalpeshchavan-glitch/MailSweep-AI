import { useMemo } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import type { UniverseRuntime } from "./universeRuntime";
import { SAMPLE_EMAILS, CLUSTERS } from "./universeConfig";
import { drawEmailCardTexture } from "./canvasTextures";

/* ============================================================================
   Cluster detail cards — the RARE near-field email cards that read as real
   mail (sender, subject, preview, category chip, year). Placed at the leading
   edge of each cluster; fade in as the camera approaches and the scan labels
   the cluster, then recede. Only ~1 per cluster → negligible GPU cost.
   ========================================================================== */

const CARD_Y_OFFSET = 3.4;
const CARD_Z_OFFSET = 1.1;

export function ClusterDetailCards({ runtime }: { runtime: UniverseRuntime }) {
  const { camera } = useThree();

  // one detailed card per cluster, looped through sample emails
  const cards = useMemo(
    () =>
      CLUSTERS.map((def, ci) => {
        const email = SAMPLE_EMAILS[ci % SAMPLE_EMAILS.length];
        const tex = drawEmailCardTexture({
          sender: email.sender,
          subject: email.subject,
          preview: `Demo metadata — class ${def.label.toLowerCase()}.`,
          tag: email.tag,
          year: email.year,
          accent: def.accent,
        });
        const mat = new THREE.MeshBasicMaterial({
          map: tex,
          transparent: true,
          opacity: 0,
          depthWrite: false,
          side: THREE.DoubleSide,
        });
        const geo = new THREE.PlaneGeometry(1.7, 2.12);
        const mesh = new THREE.Mesh(geo, mat);
        const [ax, ay, az] = def.anchor;
        mesh.position.set(ax + 1.4, ay + CARD_Y_OFFSET, az - CARD_Z_OFFSET);
        mesh.visible = false;
        return { def, mesh, mat, phase: ci * 0.11 };
      }),
    []
  );

  useFrame(() => {
    const classify = runtime.classify;
    const clarity = runtime.clarity;
    const reduced = runtime.reduced;
    const t = runtime.time;

    for (const c of cards) {
      const d = camera.position.distanceTo(c.mesh.position);
      // approach region: within ~8 units, and only once analysis has labelled it
      const proximity = Math.max(0, 1 - (d - 4) / 5);
      const labelled = Math.max(0, Math.min(1, classify - c.phase * 2));
      const calm = clarity; // after clarity the cards gently recede
      const target = Math.max(0, proximity * labelled * 0.92 * (1 - calm * 0.45));
      const o = reduced
        ? target
        : THREE.MathUtils.lerp(c.mat.opacity, target, 0.05);
      c.mat.opacity = o;
      c.mesh.visible = o > 0.01;
      if (c.mesh.visible && !reduced) {
        c.mesh.rotation.y = Math.sin(t * 0.18 + c.phase * 2.0) * 0.08;
      }
    }
  });

  return (
    <group>
      {cards.map((c) => (
        <primitive key={c.def.id} object={c.mesh} />
      ))}
    </group>
  );
}