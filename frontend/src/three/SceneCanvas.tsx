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
 * R3F canvas tuned for the cinematic background: transparent GL, fixed camera,
 * capped DPR, and a render loop that halts when the tab is hidden.
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
      camera={{ position: [0, 0, 16], fov: 60, near: 0.1, far: 120 }}
      style={{ position: "absolute", inset: 0 }}
    >
      {children}
    </Canvas>
  );
}