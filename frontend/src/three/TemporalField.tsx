import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { UniverseRuntime } from "./universeRuntime";
import { UNIVERSE_YEARS, YEAR_Z, BOUNDARY_Z, PALETTE } from "./universeConfig";
import { drawBoundaryTexture } from "./canvasTextures";
import { POINT_VERT, POINT_FRAG } from "./shaders";

/* ============================================================================
   Temporal field — the signature 5-year moment. Year markers drift past the
   amber boundary into an "old zone" of slow amber points as the camera crosses
   time. Old emails (driven in EmailField) blur dimmer and amber past it.
   ========================================================================== */
export function TemporalField({ runtime }: { runtime: UniverseRuntime }) {
  const boundaryTex = useMemo(drawBoundaryTexture, []);
  const planeGeo = useMemo(() => new THREE.PlaneGeometry(120, 60), []);
  const boundaryMat = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        map: boundaryTex,
        transparent: true,
        opacity: 0,
        depthWrite: false,
        blending: THREE.NormalBlending,
        side: THREE.DoubleSide,
      }),
    [boundaryTex]
  );
  const boundaryRef = useRef<THREE.Mesh>(null);

  // old-zone ambient points: amber specks that drift beyond the boundary
  const old = useMemo(() => {
    const n = 700;
    const pos = new Float32Array(n * 3);
    const size = new Float32Array(n);
    const phase = new Float32Array(n);
    const color = new Float32Array(n * 3);
    const c = new THREE.Color(PALETTE.safetyAmberDim);
    for (let i = 0; i < n; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 70;
      pos[i * 3 + 1] = (Math.random() - 0.5) * 30;
      pos[i * 3 + 2] = BOUNDARY_Z + 8 + Math.random() * 22;
      size[i] = 0.5 + Math.random() * 1.4;
      phase[i] = Math.random() * Math.PI * 2;
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
  }, []);

  const oldMat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: POINT_VERT,
        fragmentShader: POINT_FRAG,
        uniforms: {
          uTime: { value: 0 },
          uPixelRatio: { value: 1 },
          uOpacity: { value: 0 },
          uFogDepth: { value: 180 },
          uVoid: { value: new THREE.Color(PALETTE.obsidian) },
        },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    []
  );
  const oldRef = useRef<THREE.Points>(null);

  const yearLabels = useMemo(
    () =>
      UNIVERSE_YEARS.map((y) => {
        const cv = document.createElement("canvas");
        cv.width = 256;
        cv.height = 48;
        const g = cv.getContext("2d");
        if (g) {
          g.font = "600 28px 'JetBrains Mono', monospace";
          g.fillStyle = "rgba(233,238,243,0.55)";
          g.textAlign = "center";
          g.fillText(y, 128, 34);
        }
        const tex = new THREE.CanvasTexture(cv);
        tex.colorSpace = THREE.SRGBColorSpace;
        const sp = new THREE.Sprite(
          new THREE.SpriteMaterial({ map: tex, transparent: true, opacity: 0, depthWrite: false })
        );
        sp.position.set(19, 4.5, YEAR_Z[y]);
        sp.scale.setScalar(6);
        return sp;
      }),
    []
  );

  useFrame(({ gl }) => {
    boundaryMat.opacity = runtime.boundary * 0.5;
    if (boundaryRef.current) {
      boundaryRef.current.position.set(0, 0, BOUNDARY_Z);
      boundaryRef.current.rotation.y = 0;
    }
    oldMat.uniforms.uTime.value = runtime.time;
    oldMat.uniforms.uPixelRatio.value = gl.getPixelRatio();
    oldMat.uniforms.uOpacity.value = runtime.boundary * 0.5;
    if (oldRef.current) {
      oldRef.current.position.z = runtime.boundary * 3; // ambience approaches camera
    }
    for (const sp of yearLabels) {
      sp.material.opacity = runtime.boundary * 0.5;
    }
  });

  return (
    <group>
      <mesh ref={boundaryRef} geometry={planeGeo} material={boundaryMat} frustumCulled={false} />
      <points ref={oldRef} geometry={old} material={oldMat} frustumCulled={false} />
      {yearLabels.map((sp) => (
        <primitive key={sp.uuid} object={sp} />
      ))}
    </group>
  );
}