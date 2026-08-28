/* Shared mutable frame state. Computed once per frame by the parent MailUniverse
   system and read by the child systems (BackgroundField, EmailField, DataTrails,
   ScanSystem, TemporalField, CameraRig). Avoids React re-renders at 60&nbsp;fps. */

export interface UniverseRuntime {
  reduced: boolean;
  /** 0..1 raw scroll progress */
  progress: number;
  /** elapsed time (s) */
  time: number;
  /** clamped per-frame delta (s) */
  delta: number;

  /* derived phases — all 0..1, shaped from the scroll progress */
  /** how much original chaos remains visible (1 = full noise) */
  chaos: number;
  /** scanning sweep intensity (analysis event, pulses ~mid scroll) */
  scan: number;
  /** world-z of the scan front (moves with the camera) */
  scanFront: number;
  /** how much clusters have formed (0 = scattered) */
  organize: number;
  /** classification labels opacity (brief, during scan) */
  classify: number;
  /** 5-year separation: how much old email has drifted past the boundary */
  temporal: number;
  /** amber temporal boundary visibility */
  boundary: number;
  /** final calm/clarity state (end of story) */
  clarity: number;
  /** "you decide" amber emphasis near the safety beat */
  review: number;

  /* pointer parallax (-1..1) */
  mouseX: number;
  mouseY: number;

  /* camera position + look target (written by CameraRig, read nowhere yet but
     useful for the future dashboard reveal) */
  camPos: { x: number; y: number; z: number };
}

export function createRuntime(): UniverseRuntime {
  return {
    reduced: false,
    progress: 0,
    time: 0,
    delta: 0.016,
    chaos: 1,
    scan: 0,
    scanFront: 6,
    organize: 0,
    classify: 0,
    temporal: 0,
    boundary: 0,
    clarity: 0,
    review: 0,
    mouseX: 0,
    mouseY: 0,
    camPos: { x: 14, y: 0, z: 14 },
  };
}