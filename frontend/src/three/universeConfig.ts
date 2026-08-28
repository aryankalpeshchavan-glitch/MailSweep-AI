/* ============================================================================
   Universe configuration — the single source of truth for the cinematic 3D
   scene. Palette, clusters, year rings, camera path and sample data. Pure
   data + math helpers; no React / no GL state.
   ========================================================================== */

/* ---- Obsidian Orbit palette ------------------------------------------------ */

export const PALETTE = {
  obsidianDeep: "#020304",
  obsidian: "#04060a",
  surface: "#0d1218",
  surfaceRaised: "#141b23",
  dataBlue: "#00dbe9",
  dataBlueDim: "#7df4ff",
  safetyAmber: "#fe9800",
  safetyAmberDim: "#ffc080",
  neuralViolet: "#8523dd",
  neuralVioletDim: "#caa0ff",
  white: "#e9eef3",
  muted: "#8fa0ad",
  faint: "#46525c",
} as const;

/** Category tones — deliberately restrained & low-saturation. */
export const CLUSTER_IDS = [
  "important",
  "promotions",
  "newsletters",
  "social",
  "notifications",
  "personal",
] as const;

export type ClusterId = (typeof CLUSTER_IDS)[number];

export interface ClusterDef {
  id: ClusterId;
  label: string;
  anchor: [number, number, number];
  /** tiny orbit wobble speed, rad/s */
  wobble: number;
  /** base diffuse tone */
  color: string;
  /** accent used for labels / pulses */
  accent: string;
}

export const CLUSTERS: ClusterDef[] = [
  {
    id: "important",
    label: "IMPORTANT",
    anchor: [0, 0, 20],
    wobble: 0.02,
    color: "#dfe7ee",
    accent: "#e9eef3",
  },
  {
    id: "notifications",
    label: "NOTIFICATIONS",
    anchor: [-7, 3, 26],
    wobble: 0.06,
    color: "#6f7d88",
    accent: "#8fa0ad",
  },
  {
    id: "promotions",
    label: "PROMOTIONS",
    anchor: [6.5, -2, 28],
    wobble: 0.09,
    color: "#b08b58",
    accent: "#d8a05e",
  },
  {
    id: "personal",
    label: "PERSONAL",
    anchor: [-3, -4, 34],
    wobble: 0.04,
    color: "#b6a889",
    accent: "#d7c9a8",
  },
  {
    id: "newsletters",
    label: "NEWSLETTERS",
    anchor: [5, 2.5, 38],
    wobble: 0.07,
    color: "#5e8b96",
    accent: "#6fb5c4",
  },
  {
    id: "social",
    label: "SOCIAL",
    anchor: [-8.5, -1, 44],
    wobble: 0.11,
    color: "#7f6ea8",
    accent: "#9a7bcc",
  },
];

/* ---- Year rings + temporal separation -------------------------------------- */

export const UNIVERSE_YEARS = ["2026", "2025", "2024", "2023", "2022", "2021"] as const;
export type UniverseYear = (typeof UNIVERSE_YEARS)[number];

/** world-z for each year ring (camera travels toward +z) */
export const YEAR_Z: Record<UniverseYear, number> = {
  "2026": 44,
  "2025": 49,
  "2024": 54,
  "2023": 59,
  "2022": 64,
  "2021": 70,
};

/** emails at/lower than this year are "older than 5 years" (as of 2026) */
export const OLD_YEAR: UniverseYear = "2021";

/** the amber temporal boundary sits between 2022 and 2021 */
export const BOUNDARY_Z = 67;

/**
 * Fixed z-plane where "older than 5 years" emails resolve — reliably past the
 * boundary so the amber temporal tint always engages regardless of cluster.
 */
export const ARCHIVE_Z = 82;

/** world-space drift for the old zone (slight downward separation) */
export const OLD_DRIFT_Y = 2.4;

/* ---- Sample email data (demo; replaced by live API data later) -------------- */

export interface SampleEmail {
  sender: string;
  subject: string;
  tag: string;
  year: string;
}

export const SAMPLE_EMAILS: SampleEmail[] = [
  { sender: "linkedin.com", subject: "You appeared in 3 searches this week", tag: "SOCIAL", year: "2024" },
  { sender: "news@medium.com", subject: "The Weekly: AI infrastructure patterns", tag: "NEWSLETTERS", year: "2023" },
  { sender: "offers@store.example", subject: "Season sale — everything up to 40% off", tag: "PROMOTIONS", year: "2021" },
  { sender: "alerts@bank.example", subject: "Your statement is ready", tag: "NOTIFICATIONS", year: "2022" },
  { sender: "sarah@example.com", subject: "Re: project roadmap notes", tag: "IMPORTANT", year: "2025" },
  { sender: "noreply@cloud.example", subject: "Usage report — June", tag: "NEWSLETTERS", year: "2021" },
  { sender: "jobs@startup.example", subject: "Thank you for applying", tag: "PERSONAL", year: "2024" },
  { sender: "updates@github.com", subject: "[mailsweep] 12 new commits on main", tag: "NOTIFICATIONS", year: "2026" },
];

/* ---- Phase math ------------------------------------------------------------- */

export const clamp01 = (v: number): number => (v < 0 ? 0 : v > 1 ? 1 : v);

export const smoothstep = (a: number, b: number, x: number): number => {
  const t = clamp01((x - a) / Math.max(1e-6, b - a));
  return t * t * (3 - 2 * t);
};

/** gaussian pulse centred at `c` with width `w` */
export const gauss = (x: number, c: number, w: number): number =>
  Math.exp(-Math.pow((x - c) / w, 2));

/** 0..1 scroll progress → eased 0..1 (asymmetric, cinematic) */
export const easeProgress = (p: number): number => {
  const t = clamp01(p);
  return 1 - Math.pow(1 - t, 2.2);
};

/* ---- Camera path ------------------------------------------------------------ */

export interface CameraKey {
  p: number;
  pos: [number, number, number];
  look: [number, number, number];
  bank: number;
}

/** desktop cinematic path: fly through chaos, cross the boundary, swing wide. */
export const CAMERA_PATH: CameraKey[] = [
  { p: 0.0, pos: [14, 0, 14], look: [0, 0, 30], bank: 0 },
  { p: 0.1, pos: [20, 1, 18], look: [0, 0, 30], bank: 0.02 },
  { p: 0.28, pos: [26, 1.5, 24], look: [5, 0, 34], bank: 0.05 },
  { p: 0.45, pos: [30, 2, 32], look: [0, 2, 42], bank: 0.03 },
  { p: 0.6, pos: [32, 2.5, 44], look: [0, 0, 52], bank: -0.04 },
  { p: 0.78, pos: [24, 1.5, 60], look: [-6, 0, 66], bank: -0.06 },
  { p: 1.0, pos: [-10, 4, 40], look: [6, 0, 22], bank: 0.02 },
];

/** mobile: gentler arc that stays calm on small screens. */
export const CAMERA_PATH_MOBILE: CameraKey[] = [
  { p: 0.0, pos: [10, 0, 12], look: [0, 0, 28], bank: 0 },
  { p: 0.5, pos: [16, 1.5, 34], look: [0, 1, 44], bank: 0.02 },
  { p: 1.0, pos: [-2, 3, 44], look: [2, 0, 26], bank: 0 },
];

/* ---- Scene bounds (used by fog + scan sweep) -------------------------------- */

export const SCENE_NEAR_Z = 6;
export const SCENE_FAR_Z = 84;