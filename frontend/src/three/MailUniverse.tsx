import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { SceneProfile } from "@/hooks/useSceneProfile";
import { mulberry32 } from "./seed";

interface MailUniverseProps {
  profile: SceneProfile;
  /** 0..1 scroll progress driving the camera fly-through + clustering. */
  progressRef: React.RefObject<number>;
  /** 0..1 pointer parallax (optional). */
  mouseRef?: React.RefObject<{ x: number; y: number }>;
}

// Year labels for the "5-year moment" — newest at the back, oldest at front.
export const UNIVERSE_YEARS = ["2026", "2025", "2024", "2023", "2022", "2021"] as const;

const EASE_OUT = (t: number) => 1 - Math.pow(1 - t, 3);

/**
 * A single instanced "email" field. Everything is baked into Float32Array
 * buffers and repositioned per-frame on the GPU — thousands of objects in a
 * handful of draw calls. No per-object React components (Phase 4).
 *
 * Scroll drives two things:
 *   - the camera retreats along +Z (flying "into" depth)
 *   - objects ease from a chaos cloud into year clusters (Phase 6)
 */
export function MailUniverse({ profile, progressRef, mouseRef }: MailUniverseProps) {
  const instancedRef = useRef<THREE.InstancedMesh>(null);
  const pointsRef = useRef<THREE.Points>(null);
  const groupRef = useRef<THREE.Group>(null);

  const count = profile.particleBudget;
  const dustCount = profile.dustCount;
  const seed = 20260701;

  // ---- deterministic buffers (positions, targets, colours, scales) ----
  const data = useMemo(() => {
    const rng = mulberry32(seed);
    const chaos = new Float32Array(count * 3);
    const target = new Float32Array(count * 3);
    const scale = new Float32Array(count);
    const chaosColor = new Float32Array(count * 3);
    const targetColor = new Float32Array(count * 3);

    // Year cluster anchors spread across depth (older = nearer camera).
    const anchors: THREE.Vector3[] = [];
    for (let i = 0; i < UNIVERSE_YEARS.length; i++) {
      const z = 6 + i * 9; // 6, 15, 24, 33, 42, 51
      anchors.push(new THREE.Vector3((rng() - 0.5) * 6, (rng() - 0.5) * 4, z));
    }

    const cyan = new THREE.Color(0x00f0ff);
    const violet = new THREE.Color(0x8523dd);
    const dimCyan = new THREE.Color(0x0a7f86);

    for (let i = 0; i < count; i++) {
      // Chaos spread (wide random volume) — emails scattered everywhere.
      const x = (rng() - 0.5) * 2 * (24 + rng() * 18);
      const y = (rng() - 0.5) * 2 * (12 + rng() * 10);
      const z = (rng() - 0.5) * 2 * (34 + rng() * 18);
      chaos[i * 3] = x;
      chaos[i * 3 + 1] = y;
      chaos[i * 3 + 2] = z;

      // Assign to a year (weighted toward newer = denser near "present").
      const yr = Math.floor(Math.pow(rng(), 0.75) * UNIVERSE_YEARS.length);
      const a = anchors[yr];
      const r = UNIVERSE_YEARS.length - yr; // older clusters spread wider
      target[i * 3] = a.x + (rng() - 0.5) * (2.2 + r * 0.7);
      target[i * 3 + 1] = a.y + (rng() - 0.5) * (1.8 + r * 0.5);
      target[i * 3 + 2] = a.z + (rng() - 0.5) * (1.6 + r * 0.6);

      scale[i] = 0.06 + rng() * 0.16;

      // Chaos colours: mostly faint cyan, a few violet sparks.
      const pick = rng();
      const c0 = pick > 0.9 ? violet : pick > 0.3 ? cyan : dimCyan;
      const c1 = dimCyan; // target settles to a calm cyan.
      chaosColor[i * 3] = c0.r;
      chaosColor[i * 3 + 1] = c0.g;
      chaosColor[i * 3 + 2] = c0.b;
      targetColor[i * 3] = c1.r;
      targetColor[i * 3 + 1] = c1.g;
      targetColor[i * 3 + 2] = c1.b;
    }

    // Distant dust points.
    const dust = new Float32Array(dustCount * 3);
    for (let i = 0; i < dustCount; i++) {
      dust[i * 3] = (rng() - 0.5) * 120;
      dust[i * 3 + 1] = (rng() - 0.5) * 70;
      dust[i * 3 + 2] = (rng() - 0.5) * 120 - 10;
    }

    return { chaos, target, scale, chaosColor, targetColor, dust };
  }, [count, dustCount]);
// Static geometry shared by the instanced mesh.
  const cardGeom = useMemo(() => new THREE.PlaneGeometry(1, 0.62), []);
  const material = useMemo(() => {
    return new THREE.MeshBasicMaterial({
      toneMapped: false,
      transparent: true,
      opacity: 0.55,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
  }, []);

  const dummy = useMemo(() => new THREE.Object3D(), []);
  const tmpColor = useMemo(() => new THREE.Color(), []);
  const ptsGeom = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(data.dust, 3));
    return g;
  }, [data.dust]);

  useFrame(({ camera, clock, pointer }, deltaRaw) => {
    const t = clock.getElapsedTime();
    const delta = Math.min(deltaRaw, 0.05);

    // ---- scroll progress (from the story controller) ----
    const raw = progressRef.current ?? 0;
    const progress = THREE.MathUtils.clamp(raw, 0, 1);
    const settle = profile.reducedMotion ? 0.85 : EASE_OUT(progress);

    // ---- camera fly-through ----
    const mx = mouseRef?.current ? mouseRef.current.x : pointer.x;
    const my = mouseRef?.current ? mouseRef.current.y : pointer.y;
    const camZ = 16 + progress * 58; // retreat into depth
    const sway = profile.reducedMotion ? 0 : Math.sin(t * 0.12) * 1.4;
    camera.position.x = THREE.MathUtils.lerp(camera.position.x, mx * 2.2, 0.04);
    camera.position.y = THREE.MathUtils.lerp(camera.position.y, sway + my * 1.4, 0.05);
    camera.position.z = THREE.MathUtils.lerp(camera.position.z, camZ, 0.06);
    camera.lookAt(0, 0, 10 + progress * 46);
    if (groupRef.current) {
      groupRef.current.rotation.z = THREE.MathUtils.lerp(
        groupRef.current.rotation.z,
        mx * 0.02,
        0.03
      );
    }

    // ---- instanced email cards: chaos -> year clusters ----
    const mesh = instancedRef.current;
    if (mesh) {
      const d = data;
      for (let i = 0; i < count; i++) {
        const ix = i * 3;
        const px = d.chaos[ix] + (d.target[ix] - d.chaos[ix]) * settle;
        const py = d.chaos[ix + 1] + (d.target[ix + 1] - d.chaos[ix + 1]) * settle;
        const pz = d.chaos[ix + 2] + (d.target[ix + 2] - d.chaos[ix + 2]) * settle;

        // Gentle float when active (suppressed once settled / reduced motion).
        const float =
          profile.reducedMotion || settle > 0.99 ? 0 : Math.sin(t * 0.0008 + i) * 0.12;
        dummy.position.set(px, py + float, pz);
        dummy.scale.setScalar(d.scale[i]);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);

        // Blend colour from chaos toward the calm target.
        tmpColor.setRGB(
          d.chaosColor[ix] + (d.targetColor[ix] - d.chaosColor[ix]) * settle,
          d.chaosColor[ix + 1] + (d.targetColor[ix + 1] - d.chaosColor[ix + 1]) * settle,
          d.chaosColor[ix + 2] + (d.targetColor[ix + 2] - d.chaosColor[ix + 2]) * settle
        );
        mesh.setColorAt(i, tmpColor);
      }
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    }

    // ---- dust points: slow rotation ----
    if (pointsRef.current) {
      pointsRef.current.rotation.y += delta * 0.01 * (profile.reducedMotion ? 0 : 1);
    }
  });

  return (
    <group ref={groupRef}>
      <instancedMesh ref={instancedRef} args={[cardGeom, material, count]} frustumCulled={false} />
      <points ref={pointsRef} geometry={ptsGeom} frustumCulled={false}>
        <pointsMaterial
          size={0.035}
          color="#5fe9f2"
          transparent
          opacity={0.5}
          sizeAttenuation
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
      <fog attach="fog" args={["#000000", 30, 90]} />
    </group>
  );
}