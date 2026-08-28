import { useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import type { SceneProfile } from "@/hooks/useSceneProfile";
import type { UniverseRuntime } from "./universeRuntime";
import { CAMERA_PATH, CAMERA_PATH_MOBILE, smoothstep } from "./universeConfig";

/* ============================================================================
   Camera rig — authored cinematic path sampled with smooth easing. Slow
   acceleration into the flight, deceleration as it swings, subtle banking
   (roll) on the lateral segments and gentle mouse parallax. Reduced motion:
   camera eases to a stable composition instead of banking.
   ========================================================================== */

function buildCurves(keyframes: typeof CAMERA_PATH_MOBILE) {
  const pos = new THREE.CatmullRomCurve3(
    keyframes.map((k) => new THREE.Vector3(...k.pos)),
    false,
    "catmullrom",
    0.5
  );
  const look = new THREE.CatmullRomCurve3(
    keyframes.map((k) => new THREE.Vector3(...k.look)),
    false,
    "catmullrom",
    0.5
  );
  return { pos, look, banks: keyframes.map((k) => k.bank), keys: keyframes };
}

/** sample the authored path at raw progress p (0..1), returning pos/look/bank. */
function samplePath(
  curves: ReturnType<typeof buildCurves>,
  p: number,
  out: { pos: THREE.Vector3; look: THREE.Vector3; bank: number }
) {
  const t = Math.min(Math.max(p, 0), 1);
  curves.pos.getPoint(t, out.pos);
  curves.look.getPoint(t, out.look);
  // piecewise bank: interpolate between authored roll values
  const keys = curves.keys;
  let bank = keys[0].bank;
  for (let i = 0; i < keys.length - 1; i++) {
    if (t >= keys[i].p && t <= keys[i + 1].p) {
      const seg = smoothstep(keys[i].p, keys[i + 1].p, t);
      bank = keys[i].bank + (keys[i + 1].bank - keys[i].bank) * seg;
      break;
    }
  }
  out.bank = bank;
}

export function CameraRig({
  profile,
  runtime,
}: {
  profile: SceneProfile;
  runtime: UniverseRuntime;
}) {
  const { camera } = useThree();
  const curves = useMemo(
    () => buildCurves(profile.tier === "low" ? CAMERA_PATH_MOBILE : CAMERA_PATH),
    [profile.tier]
  );

  const out = useMemo(() => ({ pos: new THREE.Vector3(), look: new THREE.Vector3(), bank: 0 }), []);
  const dampX = useRef({ x: 0, y: 0 });
  const bankRef = useRef(0);

  useFrame(() => {
    const p = runtime.progress;
    samplePath(curves, p, out);

    // gentle mouse parallax (reduced on mobile / reduced-motion)
    const parallax =
      runtime.reduced || profile.tier === "low"
        ? 0.4
        : 1.2;
    const mx = runtime.mouseX * parallax;
    const my = runtime.mouseY * parallax;
    dampX.current.x = THREE.MathUtils.lerp(dampX.current.x, mx, 0.04);
    dampX.current.y = THREE.MathUtils.lerp(dampX.current.y, my, 0.04);

    // bond camera motion to eased flight speed
    camera.position.set(
      out.pos.x + dampX.current.x,
      out.pos.y + dampX.current.y * 0.8,
      out.pos.z
    );
    camera.lookAt(out.look.x + dampX.current.x * 0.4, out.look.y, out.look.z);

    // banking: smooth toward authored roll (suppressed for reduced motion)
    const targetBank = runtime.reduced ? 0 : out.bank;
    bankRef.current = THREE.MathUtils.lerp(bankRef.current, targetBank, 0.02);
    camera.rotation.z = bankRef.current * 0.12;

    runtime.camPos = { x: camera.position.x, y: camera.position.y, z: camera.position.z };
  });

  return null;
}