/* Custom GLSL for the instanced email field + background points.
   Uses three's instancing: `instanceMatrix` is injected automatically for
   InstancedMesh, and we declare our own per-instance attributes (aColor, aRand).
   ShaderMaterial ignores three's scene-fog chunks, so atmospheric depth fade is
   computed manually with uFogDepth (distance at which fade reaches 1.0). */

export const PANEL_VERT = /* glsl */ `
uniform float uTime;
uniform float uScan;
uniform float uScanZ;
uniform float uTemporal;
uniform float uBoundaryZ;
uniform float uFogDepth;

attribute vec3 aColor;
attribute float aRand;

varying vec3 vColor;
varying vec2 vUv;
varying float vRand;
varying float vFlash;
varying float vOld;
varying float vFade;

void main() {
  vUv = uv;
  vec4 world = modelMatrix * instanceMatrix * vec4(position, 1.0);
  vec4 mvPos = viewMatrix * world;

  float worldZ = world.z;

  // scan flash: panels near the scan front light up in data blue
  float d = worldZ - uScanZ;
  vFlash = uScan * exp(-d * d * 0.02);

  // 5-year separation: amber tint once objects drift past the boundary
  vOld = uTemporal * smoothstep(uBoundaryZ, uBoundaryZ + 12.0, worldZ);

  // manual atmospheric depth fade (ShaderMaterial ignores scene fog chunks)
  vFade = 1.0 - smoothstep(0.0, 1.0, (-mvPos.z) / max(1.0, uFogDepth));

  vRand = aRand;
  vColor = aColor;

  gl_Position = projectionMatrix * mvPos;
}
`;

export const PANEL_FRAG = /* glsl */ `
uniform vec3 uDataBlue;
uniform vec3 uAmber;
uniform vec3 uVoid;
uniform float uClarity;

varying vec3 vColor;
varying vec2 vUv;
varying float vRand;
varying float vFlash;
varying float vOld;
varying float vFade;

void main() {
  // precision border: a thin brighter edge, faint translucent interior
  vec2 d = abs(vUv - 0.5) * 2.0;
  float edge = smoothstep(0.78, 1.0, max(d.x, d.y));
  float inner = 0.35 + 0.65 * smoothstep(0.25, 1.0, max(d.x, d.y));

  vec3 base = vColor;

  // analysis flash in data blue, then amber for old drifting mail
  vec3 col = mix(base, uDataBlue, vFlash * 0.75);
  col = mix(col, uAmber, vOld * 0.8);

  // subtle per-object shimmer so identical shapes never read as a grid
  float tw = 0.9 + 0.1 * sin(uTime * 0.9 + vRand * 6.28318);

  float alpha = tw * (0.12 + 0.55 * inner) + vFlash * 0.85 + vOld * 0.35;

  // precision edges catch the light
  col += uDataBlue * edge * (0.18 + vFlash * 0.85);

  // final clarity: a calm, slightly brighter neutral
  col = mix(col, col * 1.06, uClarity * 0.35);

  // atmospheric depth falloff toward the void
  col = mix(uVoid, col, vFade);
  alpha *= 0.35 + 0.65 * vFade;

  gl_FragColor = vec4(col, min(alpha, 1.0));
}
`;

export const POINT_VERT = /* glsl */ `
uniform float uPixelRatio;
uniform float uFogDepth;

attribute vec3 aColor;
attribute float aSize;
attribute float aPhase;

varying vec3 vColor;
varying float vPhase;
varying float vFade;

void main() {
  vColor = aColor;
  vPhase = aPhase;
  vec4 mvPos = modelViewMatrix * vec4(position, 1.0);
  gl_PointSize = aSize * uPixelRatio * (1.0 / max(0.1, -mvPos.z));
  vFade = 1.0 - smoothstep(0.0, 1.0, (-mvPos.z) / max(1.0, uFogDepth));
  gl_Position = projectionMatrix * mvPos;
}
`;

export const POINT_FRAG = /* glsl */ `
uniform float uTime;
uniform float uOpacity;
uniform vec3 uVoid;

varying vec3 vColor;
varying float vPhase;
varying float vFade;

void main() {
  // soft circular point of light (hardware-accelerated radial falloff)
  vec2 c = gl_PointCoord - 0.5;
  float r = length(c);
  float alpha = smoothstep(0.5, 0.0, r);
  // gentle twinkle per particle
  float tw = 0.6 + 0.4 * sin(uTime * 1.4 + vPhase);
  vec3 col = mix(uVoid, vColor, vFade);
  gl_FragColor = vec4(col, alpha * tw * uOpacity * (0.3 + 0.7 * vFade));
}
`;

/* Shared uniforms for the instanced panel material. */
export const PANEL_UNIFORMS = {
  uTime: { value: 0 },
  uScan: { value: 0 },
  uScanZ: { value: 0 },
  uTemporal: { value: 0 },
  uBoundaryZ: { value: 67 },
  uFogDepth: { value: 120 },
  uDataBlue: { value: [0.0, 0.858, 0.914] },
  uAmber: { value: [1.0, 0.6, 0.25] },
  uVoid: { value: [0.016, 0.024, 0.04] },
  uClarity: { value: 0 },
};