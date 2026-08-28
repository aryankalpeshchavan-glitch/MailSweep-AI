import * as THREE from "three";
import { CLUSTERS, UNIVERSE_YEARS, YEAR_Z } from "./universeConfig";
import { mulberry32 } from "./seed";

/* ============================================================================
   Email entity data — pure, deterministic generation of the email population.
   Kept separate from the React component so hot-reload refresh stays clean and
   the data layer can be unit-tested without rendering GL.
   ========================================================================== */

export type EntityKind = "sheet" | "slat" | "card";

export interface Entity {
  kind: EntityKind;
  cluster: number;
  year: number; // index into UNIVERSE_YEARS
  chaos: THREE.Vector3;
  local: THREE.Vector3; // offset within its cluster (organised pose)
  scale: number;
  rotY: number;
  rotZ: number;
  color: THREE.Color;
  rand: number;
  phase: number; // per-entity motion phase
  floatSpeed: number;
}

export const GEOMETRY: Record<EntityKind, THREE.BufferGeometry> = {
  sheet: new THREE.PlaneGeometry(1, 1.25),
  slat: new THREE.BoxGeometry(1.5, 0.16, 0.02),
  card: new THREE.PlaneGeometry(0.72, 0.92),
};

const KIND_WEIGHTS: Array<[EntityKind, number]> = [
  ["sheet", 0.45],
  ["slat", 0.3],
  ["card", 0.25],
];

/** realistic category mix — promotions/newsletters dominate a cleanup inbox */
const CLUSTER_WEIGHTS = [0.2, 0.16, 0.24, 0.12, 0.18, 0.1];
// important(0.2) notifications(0.16) promotions(0.24) personal(0.12) newsletters(0.18) social(0.1)

function pickKind(rng: () => number): EntityKind {
  const r = rng();
  let acc = 0;
  for (const [kind, w] of KIND_WEIGHTS) {
    acc += w;
    if (r <= acc) return kind;
  }
  return "sheet";
}

function weightedIndex(rng: () => number, weights: number[]): number {
  const r = rng();
  let acc = 0;
  for (let i = 0; i < weights.length; i++) {
    acc += weights[i];
    if (r <= acc) return i;
  }
  return weights.length - 1;
}

/** Build N deterministic email entities scattered in chaos → organised space. */
export function buildEntities(
  count: number,
  seed: number
): { entities: Entity[]; counts: Record<EntityKind, number> } {
  const rng = mulberry32(seed);
  const entities: Entity[] = [];
  const counts: Record<EntityKind, number> = { sheet: 0, slat: 0, card: 0 };
  const clusterPalette = CLUSTERS.map((c) => new THREE.Color(c.color));

  for (let i = 0; i < count; i++) {
    const kind = pickKind(rng);
    counts[kind]++;
    const cluster = weightedIndex(rng, CLUSTER_WEIGHTS);
    const year = Math.floor(Math.pow(rng(), 0.82) * UNIVERSE_YEARS.length); // skew recent

    // chaos: wide scattered volume, denser around the flight corridor
    const chaos = new THREE.Vector3(
      (rng() - 0.5) * 60,
      (rng() - 0.5) * 34,
      (rng() - 0.5) * 70 + 26
    );

    // organised pose: anchor + year-ring offset + tight gaussian scatter
    const yrOff = YEAR_Z[UNIVERSE_YEARS[year]] - 40;
    const spread = 2.4 + (5 - year) * 0.6; // older years spread slightly wider
    const local = new THREE.Vector3(
      (rng() + rng() + rng() - 1.5) * spread,
      (rng() + rng() + rng() - 1.5) * spread * 0.42,
      yrOff + (rng() - 0.5) * 2.6
    );

    const baseColor = clusterPalette[cluster].clone()
      .multiplyScalar(0.55 + rng() * 0.5)
      .offsetHSL(0, (rng() - 0.5) * 0.05, (rng() - 0.5) * 0.07);

    entities.push({
      kind,
      cluster,
      year,
      chaos,
      local,
      scale:
        kind === "slat"
          ? 0.55 + rng() * 0.9
          : kind === "card"
            ? 0.62 + rng() * 0.55
            : 0.85 + rng() * 1.1,
      rotY: (rng() - 0.5) * 0.7,
      rotZ: (rng() - 0.5) * 0.5,
      color: baseColor,
      rand: rng(),
      phase: rng() * Math.PI * 2,
      floatSpeed: 0.4 + rng() * 0.9,
    });
  }
  return { entities, counts };
}