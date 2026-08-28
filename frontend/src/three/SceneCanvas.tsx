import { Canvas } from "@react-three/fiber";
import type { ReactNode } from "react";
import type { SceneProfile } from "@/hooks/useSceneProfile";

interface SceneCanvasProps {
  profile: SceneProfile;
  /** pause the render loop when the tab is hidden (Phase 14). */
  active: boolean;
  children: ReactNode;
}

/**
 * R3F canvas tuned for the cinematic background: transparent GL, capped DPR,
 * and a render loop that halts when the tab is hidden. The camera is fully
 * driven by CameraRig once mounted — this only seeds position + near/far.
 */
export function SceneCanvas({ profile, active, children }: SceneCanvasProps) {
  return (
    <Canvas
      dpr={profile.dpr}
      frameloop={active ? "always" : "never"}
      gl={{
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
        stencil: false,
      }}
      camera={{ position: [14, 0, 14], fov: 55, near: 0.1, far: 220 }}
      style={{ position: "absolute", inset: 0 }}
    >
      {children}
    </Canvas>
  );
}