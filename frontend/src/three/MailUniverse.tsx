import { useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import type { SceneProfile } from "@/hooks/useSceneProfile";
import { smoothstep, gauss } from "./universeConfig";
import { createRuntime } from "./universeRuntime";
import { BackgroundField } from "./BackgroundField";
import { EmailField } from "./EmailField";
import { DataTrails } from "./DataTrails";
import { ScanSystem } from "./ScanSystem";
import { TemporalField } from "./TemporalField";
import { EmailClusters } from "./EmailClusters";
import { ClusterDetailCards } from "./ClusterDetailCards";
import { Environment } from "./Environment";
import { CameraRig } from "./CameraRig";

interface MailUniverseProps {
  profile: SceneProfile;
  /** 0..1 scroll progress from the story controller. */
  progressRef: React.RefObject<number>;
  /** 0..1 pointer parallax (optional). */
  mouseRef?: React.RefObject<{ x: number; y: number }>;
}

/**
 * MailUniverse — the cinematic 3D experience behind the landing story.
 *
 * Systems:
 *   BackgroundField    distant points of light + year rings
 *   EmailField         instanced email population (sheet/slat/card)
 *   EmailClusters      category anchor halos
 *   DataTrails         connective data-flow lines + travelling particles
 *   ScanSystem         sweeping analysis front + classification labels
 *   TemporalField      5-year amber boundary + old zone
 *   ClusterDetailCards rare near-field email detail cards
 *   Environment        cinematic lights + fog
 *   CameraRig          authored camera path (banking, parallax)
 *
 * One useFrame computes the derived narrative phases and writes them into a
 * shared runtime, so every child system reads a consistent snapshot — the
 * single-writer frame composition.
 */
export function MailUniverse({ profile, progressRef, mouseRef }: MailUniverseProps) {
  const runtime = useMemo(() => createRuntime(), []);

  useFrame((state, deltaRaw) => {
    const delta = Math.min(deltaRaw, 0.05);
    const p = Math.min(1, Math.max(0, progressRef.current ?? 0));

    // ---- narrative phases derived from scroll progress --------------------
    // story order: chaos → analyze → organize → 5-year → decide → clarity
    const chaos = 1 - smoothstep(0.08, 0.3, p);
    const scanGate = smoothstep(0.18, 0.28, p) * (1 - smoothstep(0.4, 0.52, p));
    const classify = gauss(p, 0.34, 0.055);
    const organize = smoothstep(0.22, 0.5, p);
    const temporal = smoothstep(0.48, 0.72, p);
    const boundary = smoothstep(0.54, 0.74, p);
    const review = gauss(p, 0.78, 0.05);
    const clarity = smoothstep(0.78, 0.95, p);

    runtime.reduced = profile.reducedMotion;
    runtime.progress = p;
    runtime.time = state.clock.getElapsedTime();
    runtime.delta = delta;
    runtime.chaos = chaos;
    runtime.scan = scanGate;
    runtime.classify = classify;
    runtime.organize = organize;
    runtime.temporal = temporal;
    runtime.boundary = boundary;
    runtime.review = review;
    runtime.clarity = clarity;
    runtime.mouseX = mouseRef?.current?.x ?? state.pointer.x;
    runtime.mouseY = mouseRef?.current?.y ?? state.pointer.y;
  });

  return (
    <group>
      <fogExp2 attach="fog" args={["#04060a", 0.013]} />
      <CameraRig profile={profile} runtime={runtime} />
      <Environment profile={profile} runtime={runtime} />
      <BackgroundField profile={profile} runtime={runtime} />
      <EmailField profile={profile} runtime={runtime} />
      <EmailClusters runtime={runtime} />
      <DataTrails runtime={runtime} />
      <ScanSystem runtime={runtime} />
      <TemporalField runtime={runtime} />
      <ClusterDetailCards runtime={runtime} />
    </group>
  );
}