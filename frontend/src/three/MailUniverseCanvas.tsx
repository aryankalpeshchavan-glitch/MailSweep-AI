import { useEffect, useRef } from "react";
import { useDocumentVisibility } from "@/hooks/useMediaQuery";
import type { SceneProfile } from "@/hooks/useSceneProfile";
import { useWebGLSupport } from "@/hooks/useWebGLSupport";
import { UniverseFallback2D } from "@/three/fallback/UniverseFallback2D";
import { SceneCanvas } from "@/three/SceneCanvas";
import { MailUniverse } from "@/three/MailUniverse";

interface MailUniverseCanvasProps {
  profile: SceneProfile;
  /** 0..1 scroll progress from the story controller. */
  progressRef: React.RefObject<number>;
  className?: string;
}

/**
 * Composable entry point for the 3D background. Gated on WebGL support:
 * when unavailable it renders {@link UniverseFallback2D} instead of a broken
 * black canvas (Phase 13). The render loop pauses while the tab is hidden.
 */
export function MailUniverseCanvas({ profile, progressRef, className }: MailUniverseCanvasProps) {
  const { supported } = useWebGLSupport();
  const visible = useDocumentVisibility();
  const nodeRef = useRef<HTMLDivElement>(null);
  const mouseRef = useRef({ x: 0, y: 0 });

  // Absolute pointer tracking for subtle parallax (works across the overlay).
  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      // Normalise to -1..1. Store on the ref — no React re-render per move.
      mouseRef.current.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouseRef.current.y = (e.clientY / window.innerHeight) * 2 - 1;
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, []);

  if (!supported) {
    return (
      <div
        ref={nodeRef}
        className={`mail-universe-fallback ${className ?? ""}`}
        aria-hidden="true"
      >
        <UniverseFallback2D profile={profile} />
      </div>
    );
  }

  return (
    <div ref={nodeRef} className={className} aria-hidden="true">
      <SceneCanvas profile={profile} active={visible}>
        <MailUniverse profile={profile} progressRef={progressRef} mouseRef={mouseRef} />
      </SceneCanvas>
    </div>
  );
}