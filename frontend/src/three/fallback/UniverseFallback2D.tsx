import { useEffect, useRef } from "react";
import type { SceneProfile } from "@/hooks/useSceneProfile";
import { mulberry32 } from "@/three/seed";

interface Particle {
  x: number;
  y: number;
  z: number; // 0..1 depth for parallax drift
  size: number;
  speed: number;
  hue: "blue" | "violet";
  phase: number;
}

/**
 * Elegant 2D fallback for when WebGL is unavailable. A lightweight canvas-2D
 * drifting starfield keeps the cinematic feel without the 3D context. Honors
 * reduced motion (static composition) and pauses offscreen (Phase 13/14).
 */
export function UniverseFallback2D({ profile }: { profile: SceneProfile }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let w = 0;
    let h = 0;
    const reduced = profile.reducedMotion;
    const rng = mulberry32(20260701);
    const count = Math.min(profile.dustCount, 420); // 2D budget is far cheaper
    const particles: Particle[] = [];

    for (let i = 0; i < count; i++) {
      particles.push({
        x: rng(),
        y: rng(),
        z: 0.2 + rng() * 0.8,
        size: 0.5 + rng() * 1.6,
        speed: 0.0004 + rng() * 0.001,
        hue: rng() > 0.88 ? "violet" : "blue",
        phase: rng() * Math.PI * 2,
      });
    }

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width = Math.max(1, Math.floor(w * dpr));
      canvas.height = Math.max(1, Math.floor(h * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();

    const draw = (_t: number) => {
      ctx.clearRect(0, 0, w, h);

      // Deep obsidian base with subtle radial tint fields.
      const grad = ctx.createRadialGradient(w * 0.3, h * 0.25, 0, w / 2, h / 2, Math.max(w, h) * 0.7);
      grad.addColorStop(0, "rgba(0,240,255,0.05)");
      grad.addColorStop(0.5, "rgba(0,0,0,0)");
      grad.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);

      for (const p of particles) {
        if (!reduced) {
          // slow vertical/diagonal drift
          p.y += p.speed * p.z;
          if (p.y > 1) p.y -= 1;
          p.phase += 0.004;
        }
        const px = p.x * w;
        const py = p.y * h;
        const twinkle = reduced ? 0.7 : 0.55 + 0.45 * Math.sin(p.phase);
        const isBlue = p.hue === "blue";
        const base = isBlue ? "0,240,255" : "133,35,221";
        ctx.beginPath();
        ctx.arc(px, py, p.size * p.z, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${base},${0.35 * twinkle * p.z})`;
        ctx.fill();
      }
      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    const onResize = () => resize();
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
    };
  }, [profile.dustCount, profile.reducedMotion]);

  return <canvas ref={canvasRef} className="h-full w-full" aria-hidden="true" />;
}
