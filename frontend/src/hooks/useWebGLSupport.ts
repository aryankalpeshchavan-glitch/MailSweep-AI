import { useEffect, useMemo, useState } from "react";

/**
 * Detect WebGL availability *without* creating a full Three.js/WebGL context
 * unless needed. Used to gate the 3D hero and swap to the 2D fallback
 * (Phase 13). We cache the result so we never probe more than once per tab.
 */

export type WebGLSupport =
  | { supported: true; renderer: string }
  | { supported: false; reason: string };

let cached: WebGLSupport | null = null;

function probeWebGL(): WebGLSupport {
  try {
    const canvas = document.createElement("canvas");
    const gl =
      canvas.getContext("webgl2") ??
      canvas.getContext("webgl") ??
      (canvas.getContext("experimental-webgl") as WebGLRenderingContext | null);
    if (!gl) {
      return { supported: false, reason: "WebGL not supported by this browser/device." };
    }
    const debugInfo = gl.getExtension("WEBGL_debug_renderer_info");
    const renderer = debugInfo
      ? String((gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) as string) ?? "unknown")
      : "webgl";
    return { supported: true, renderer };
  } catch {
    return { supported: false, reason: "WebGL context creation failed." };
  }
}

/**
 * Returns WebGL support. In jsdom (tests) the probe returns false, which
 * correctly exercises the 2D fallback path.
 */
export function useWebGLSupport(): WebGLSupport {
  const initial = useMemo<WebGLSupport>(() => {
    if (typeof window === "undefined") return { supported: false, reason: "no window" };
    if (cached) return cached;
    cached = probeWebGL();
    return cached;
  }, []);

  const [support, setSupport] = useState<WebGLSupport>(initial);

  useEffect(() => {
    const onVisibility = () => {
      if (cached) setSupport(cached);
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  return support;
}