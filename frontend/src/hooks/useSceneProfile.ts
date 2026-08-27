import { useMemo } from "react";
import { useIsMobile, useMediaQuery } from "@/hooks/useMediaQuery";
import { useReducedMotion } from "@/hooks/useReducedMotion";

export type QualityTier = "low" | "med" | "high";

export interface SceneProfile {
  tier: QualityTier;
  /** instanced email-card count */
  particleBudget: number;
  /** point-cloud count (distant dust) */
  dustCount: number;
  /** capped devicePixelRatio for the R3F canvas */
  dpr: [number, number];
  /** reduce live animation to near-static (public motion) */
  reducedMotion: boolean;
}

/**
 * Compute a render profile. Desktop = "high" (several thousand objects in a
 * few GPU draws), tablet = "med", phone = "low". `prefers-reduced-motion`
 * drops live animation regardless of tier (Phase 13).
 */
export function useSceneProfile(): SceneProfile {
  const reducedMotion = useReducedMotion();
  const isMobile = useIsMobile();
  const isMid = useMediaQuery("(min-width: 768px) and (max-width: 1023px)");

  return useMemo<SceneProfile>(() => {
    if (isMobile) {
      return {
        tier: "low",
        particleBudget: 650,
        dustCount: 900,
        dpr: [1, 1.5],
        reducedMotion,
      };
    }
    if (isMid) {
      return {
        tier: "med",
        particleBudget: 1400,
        dustCount: 1800,
        dpr: [1, 2],
        reducedMotion,
      };
    }
    return {
      tier: "high",
      particleBudget: 2600,
      dustCount: 3200,
      dpr: [1, 2],
      reducedMotion,
    };
  }, [isMobile, isMid, reducedMotion]);
}