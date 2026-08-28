import { describe, expect, it } from "vitest";
import { buildEntities } from "./emailEntities";
import {
  smoothstep,
  gauss,
  clamp01,
  easeProgress,
  CLUSTERS,
  BOUNDARY_Z,
  OLD_YEAR,
  UNIVERSE_YEARS,
  YEAR_Z,
} from "./universeConfig";

describe("email entity generation (deterministic)", () => {
  it("generates exactly N entities across all three geometry classes", () => {
    const { entities, counts } = buildEntities(1200, 20260701);
    expect(entities.length).toBe(1200);
    expect(counts.sheet + counts.slat + counts.card).toBe(1200);
    expect(counts.sheet).toBeGreaterThan(0);
    expect(counts.slat).toBeGreaterThan(0);
    expect(counts.card).toBeGreaterThan(0);
  });

  it("is deterministic for a fixed seed", () => {
    const a = buildEntities(500, 42);
    const b = buildEntities(500, 42);
    expect(a.entities[0].chaos.equals(b.entities[0].chaos)).toBe(true);
    expect(a.counts.sheet).toBe(b.counts.sheet);
    expect(a.entities[250].color.equals(b.entities[250].color)).toBe(true);
  });

  it("produces different layouts for different seeds", () => {
    const a = buildEntities(500, 1);
    const b = buildEntities(500, 2);
    expect(a.entities[0].chaos.equals(b.entities[0].chaos)).toBe(false);
  });

  it("keeps cluster and year indices in valid ranges", () => {
    const { entities } = buildEntities(800, 7);
    for (const e of entities) {
      expect(e.cluster).toBeGreaterThanOrEqual(0);
      expect(e.cluster).toBeLessThan(CLUSTERS.length);
      expect(e.year).toBeGreaterThanOrEqual(0);
      expect(e.year).toBeLessThan(UNIVERSE_YEARS.length);
    }
  });

  it("maps old-year emails past the boundary in the temporal config", () => {
    // OLD_YEAR (2021) sits at the far end of the year axis; the boundary must
    // fall between it and the next-closest year (2022)
    const oldZ = YEAR_Z[OLD_YEAR];
    const prevYear = UNIVERSE_YEARS[UNIVERSE_YEARS.indexOf(OLD_YEAR) - 1];
    const prevZ = YEAR_Z[prevYear];
    expect(oldZ).toBeGreaterThan(prevZ);
    expect(BOUNDARY_Z).toBeGreaterThan(prevZ);
    expect(BOUNDARY_Z).toBeLessThan(oldZ);
  });
});

describe("phase math helpers", () => {
  it("clamps to 0..1", () => {
    expect(clamp01(-1)).toBe(0);
    expect(clamp01(2)).toBe(1);
    expect(clamp01(0.5)).toBe(0.5);
  });

  it("smoothstep is monotonic between bounds", () => {
    expect(smoothstep(0, 1, 0)).toBe(0);
    expect(smoothstep(0, 1, 1)).toBe(1);
    expect(smoothstep(0, 1, 0.25)).toBeGreaterThan(0);
    expect(smoothstep(0, 1, 0.25)).toBeLessThan(0.25);
  });

  it("gauss peaks at its centre and decays outward", () => {
    expect(gauss(0.5, 0.5, 0.1)).toBeCloseTo(1);
    expect(gauss(0.9, 0.5, 0.1)).toBeLessThan(0.1);
  });

  it("easeProgress is monotonic and hits 0/1 at the ends", () => {
    expect(easeProgress(0)).toBe(0);
    expect(easeProgress(1)).toBe(1);
    const mid = easeProgress(0.5);
    expect(mid).toBeGreaterThan(0.2);
    expect(mid).toBeLessThan(0.9);
    for (let i = 0; i < 99; i++) {
      expect(easeProgress(i / 100)).toBeLessThanOrEqual(easeProgress((i + 1) / 100));
    }
  });
});