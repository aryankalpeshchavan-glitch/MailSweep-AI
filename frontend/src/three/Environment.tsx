import { useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { SceneProfile } from "@/hooks/useSceneProfile";
import type { UniverseRuntime } from "./universeRuntime";
import { PALETTE } from "./universeConfig";
import { drawGlowTexture } from "./canvasTextures";

/* ============================================================================
   Environment — soft cinematic lighting layered over the instanced shader
   field. One cool key light, faint ambient, plus two additive glow "nebulas"
   (Data Blue front, Neural Violet back) that give the darkness atmosphere.
   No shadows, no post-processing, no HDR downloads — stays cheap.
   ========================================================================== */
export function Environment({ profile, runtime }: { profile: SceneProfile; runtime: UniverseRuntime }) {
  const blueGlowTex = useMemo(() => drawGlowTexture(), []);
  const violetGlowTex = useMemo(() => drawGlowTexture(), []);

  const blueGlow = useMemo(
    () =>
      new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: blueGlowTex,
          color: PALETTE.dataBlue,
          transparent: true,
          opacity: 0.14,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        })
      ),
    [blueGlowTex]
  );
  const violetGlow = useMemo(
    () =>
      new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: violetGlowTex,
          color: PALETTE.neuralViolet,
          transparent: true,
          opacity: 0.1,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        })
      ),
    [violetGlowTex]
  );

  blueGlow.position.set(-14, 6, 16);
  blueGlow.scale.setScalar(70);
  violetGlow.position.set(16, -8, 60);
  violetGlow.scale.setScalar(90);

  useFrame(() => {
    // the blue glow gently breathes with the scan; violet recedes after clarity
    blueGlow.material.opacity = 0.1 + runtime.scan * 0.12 + runtime.classify * 0.06;
    violetGlow.material.opacity = runtime.reduced
      ? 0.1
      : 0.1 + runtime.classify * 0.08 - runtime.clarity * 0.05;
  });

  return (
    <group>
      <ambientLight intensity={profile.tier === "low" ? 0.5 : 0.35} color="#2a3440" />
      <directionalLight position={[-18, 22, 10]} intensity={profile.tier === "low" ? 0.6 : 0.45} color="#9fd6e6" />
      <directionalLight position={[20, -8, 40]} intensity={0.12} color={PALETTE.neuralViolet} />
      <primitive object={blueGlow} />
      <primitive object={violetGlow} />
    </group>
  );
}