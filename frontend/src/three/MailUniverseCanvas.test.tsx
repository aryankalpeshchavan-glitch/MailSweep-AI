import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import type { SceneProfile } from "@/hooks/useSceneProfile";
import { MailUniverseCanvas } from "./MailUniverseCanvas";

const profile: SceneProfile = {
  tier: "high",
  particleBudget: 2600,
  dustCount: 3200,
  dpr: [1, 2],
  reducedMotion: false,
};

const progressRef = { current: 0 };

// jsdom has no canvas backing store. Provide a minimal 2D context stub so the
// fallback's render loop runs silently instead of logging "Not implemented".
beforeAll(() => {
  const ctx2d = {
    clearRect: vi.fn(),
    fillRect: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    setTransform: vi.fn(),
    createRadialGradient: () => ({ addColorStop: vi.fn() }),
  };
  Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
    configurable: true,
    value: () => ctx2d,
  });
});

afterAll(() => {
  vi.unstubAllGlobals();
});

/**
 * WebGL fallback verification (Phase 13): in the jsdom environment there is no
 * real WebGL context, so useWebGLSupport() reports `supported: false`. The
 * canvas must therefore render the elegant 2D fallback (a <canvas>) instead of
 * a broken black WebGL canvas.
 */
describe("MailUniverseCanvas", () => {
  it("renders the 2D canvas fallback when WebGL is unavailable", () => {
    render(
      <MailUniverseCanvas profile={profile} progressRef={progressRef} className="" />
    );
    // The fallback + the wrapper are aria-hidden; the 2D fallback draws to a canvas.
    const canvas = document.querySelector("canvas");
    expect(canvas).not.toBeNull();
  });

  it("marks the fallback container as aria-hidden for screen readers", () => {
    const { container } = render(
      <MailUniverseCanvas profile={profile} progressRef={progressRef} className="" />
    );
    const wrapper = container.querySelector(".mail-universe-fallback");
    expect(wrapper).not.toBeNull();
    expect(wrapper?.getAttribute("aria-hidden")).toBe("true");
  });
});
