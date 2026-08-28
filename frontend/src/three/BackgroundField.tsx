import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { SceneProfile } from "@/hooks/useSceneProfile";
import type { UniverseRuntime } from "./universeRuntime";
import { PALETTE, UNIVERSE_YEARS, YEAR_Z } from "./universeConfig";
import { mulberry32 } from "./seed";
import { POINT_VERT, POINT_FRAG } from "./shaders";

/* ============================================================================
   Background field — two bands of distant points of light ("distant email
   signals") with GPU-side twinkle. Band 1: faint neutral dust that fills the
   entire flight volume. Band 2: sparse Data-Blue / Neural-Violet "signal"
   points that read as far-away activity. No per-particle React components.
   ========================================================================== */
export function BackgroundField({
  profile,
  runtime,
}: {
  profile: SceneProfile;
  runtime: UniverseRuntime;
}) {
  const dustRef = useRef<THREE.Points>(null);
  const signalRef = useRef<THREE.Points>(null);

  const dust = useMemo(() => {
    const rng = mulberry32(777);
    const n = Math.round(profile.dustCount * 0.8);
    const pos = new Float32Array(n * 3);
    const size = new Float32Array(n);
    const phase = new Float32Array(n);
    const color = new Float32Array(n * 3);
    const c = new THREE.Color(PALETTE.muted);
    for (let i = 0; i < n; i++) {
      pos[i * 3] = (rng() - 0.5) * 180;
      pos[i * 3 + 1] = (rng() - 0.5) * 110;
      pos[i * 3 + 2] = (rng() - 0.5) * 190;
      size[i] = 0.4 + rng() * 1.1;
      phase[i] = rng() * Math.PI * 2;
      c.set(PALETTE.muted).multiplyScalar(0.8 + rng() * 0.5);
      color[i * 3] = c.r;
      color[i * 3 + 1] = c.g;
      color[i * 3 + 2] = c.b;
    }
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geom.setAttribute("aSize", new THREE.BufferAttribute(size, 1));
    geom.setAttribute("aPhase", new THREE.BufferAttribute(phase, 1));
    geom.setAttribute("aColor", new THREE.BufferAttribute(color, 3));
    return geom;
  }, [profile.dustCount]);

  const signal = useMemo(() => {
    const rng = mulberry32(778);
    const n = Math.max(60, Math.round(profile.dustCount * 0.12));
    const pos = new Float32Array(n * 3);
    const size = new Float32Array(n);
    const phase = new Float32Array(n);
    const color = new Float32Array(n * 3);
    const palette = [new THREE.Color(PALETTE.dataBlue), new THREE.Color(PALETTE.neuralViolet)];
    for (let i = 0; i < n; i++) {
      pos[i * 3] = (rng() - 0.5) * 150;
      pos[i * 3 + 1] = (rng() - 0.5) * 90;
      pos[i * 3 + 2] = (rng() - 0.5) * 170;
      size[i] = 1.4 + rng() * 2.2;
      phase[i] = rng() * Math.PI * 2;
      const c = palette[Math.floor(rng() * 2)];
      color[i * 3] = c.r;
      color[i * 3 + 1] = c.g;
      color[i * 3 + 2] = c.b;
    }
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geom.setAttribute("aSize", new THREE.BufferAttribute(size, 1));
    geom.setAttribute("aPhase", new THREE.BufferAttribute(phase, 1));
    geom.setAttribute("aColor", new THREE.BufferAttribute(color, 3));
    return geom;
  }, [profile.dustCount]);

  const dustMat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: POINT_VERT,
        fragmentShader: POINT_FRAG,
        uniforms: {
          uTime: { value: 0 },
          uPixelRatio: { value: 1 },
          uOpacity: { value: 0.5 },
          uFogDepth: { value: 190 },
          uVoid: { value: new THREE.Color(PALETTE.obsidian) },
        },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    []
  );
  const signalMat = dustMat.clone();
  signalMat.uniforms.uOpacity.value = 0.85;

  // keep pixel ratio uniform in sync with the renderer
  useFrame(({ gl }) => {
    const pr = gl.getPixelRatio();
    dustMat.uniforms.uPixelRatio.value = pr;
    signalMat.uniforms.uPixelRatio.value = pr;
    dustMat.uniforms.uTime.value = runtime.time;
    signalMat.uniforms.uTime.value = runtime.time;

    // far objects stay near-static; the signal band drifts almost imperceptibly
    const rot = runtime.reduced ? 0 : runtime.delta * 0.0035;
    if (dustRef.current) dustRef.current.rotation.y += rot;
    if (signalRef.current) signalRef.current.rotation.y += rot * 1.4;

    // classification labels / clarity subtly raise the signal band's life
    signalMat.uniforms.uOpacity.value = 0.55 + runtime.classify * 0.3 - runtime.clarity * 0.2;
  });

  // precompute year-ring line objects once (avoid geometry churn every render)
  const yearLines = useMemo(() => {
    const lines: THREE.Line[] = [];
    for (const y of UNIVERSE_YEARS) {
      const r = 16 + (5 - UNIVERSE_YEARS.indexOf(y)) * 2.2;
      const segs = 128;
      const pos = new Float32Array(segs * 3);
      for (let i = 0; i < segs; i++) {
        const a = (i / segs) * Math.PI * 2;
        pos[i * 3] = Math.cos(a) * r;
        pos[i * 3 + 1] = Math.sin(a) * r * 0.42;
        pos[i * 3 + 2] = YEAR_Z[y];
      }
      const geom = new THREE.BufferGeometry();
      geom.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      const mat = new THREE.LineBasicMaterial({
        color: PALETTE.faint,
        transparent: true,
        opacity: 0.22,
        depthWrite: false,
      });
      lines.push(new THREE.Line(geom, mat));
    }
    return lines;
  }, []);

  return (
    <group>
      <points ref={dustRef} geometry={dust} material={dustMat} frustumCulled={false} />
      <points ref={signalRef} geometry={signal} material={signalMat} frustumCulled={false} />
      {/* year rings — faint signature markers on the temporal axis */}
      {yearLines.map((line) => (
        <primitive key={line.uuid} object={line} />
      ))}
    </group>
  );
}