import * as THREE from "three";
const FONT_MONO = '"JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace';
const FONT_BODY = '"Inter", system-ui, -apple-system, sans-serif';

/**
 * Draw an email-detail card onto a canvas for use as a mesh texture.
 * These are the RARE near-field cards that read as real email.
 */
export function drawEmailCardTexture(opts: {
  sender: string;
  subject: string;
  preview?: string;
  tag: string;
  year: string;
  accent: string;
}): THREE.CanvasTexture {
  const W = 512;
  const H = 640;
  const cv = document.createElement("canvas");
  cv.width = W;
  cv.height = H;
  const g = cv.getContext("2d");
  if (!g) return new THREE.CanvasTexture(cv);

  // obsidian card body
  g.fillStyle = "rgba(8, 11, 15, 0.92)";
  g.beginPath();
  g.roundRect(2, 2, W - 4, H - 4, 18);
  g.fill();
  g.strokeStyle = "rgba(255, 255, 255, 0.16)";
  g.lineWidth = 2;
  g.stroke();

  // sender row with accent dot
  g.fillStyle = opts.accent;
  g.beginPath();
  g.arc(44, 70, 9, 0, Math.PI * 2);
  g.fill();
  g.fillStyle = "rgba(233, 238, 243, 0.86)";
  g.font = `600 30px ${FONT_BODY}`;
  g.textBaseline = "middle";
  g.fillText(opts.sender.slice(0, 26), 66, 70);

  // subject
  g.fillStyle = "rgba(233, 238, 243, 0.96)";
  g.font = `600 34px ${FONT_BODY}`;
  wrapText(g, opts.subject, 44, 128, W - 88, 42, 3);

  // preview (dim)
  g.fillStyle = "rgba(143, 160, 173, 0.7)";
  g.font = `400 26px ${FONT_BODY}`;
  wrapText(g, opts.preview ?? "No preview stored — metadata only.", 44, 292, W - 88, 34, 2);

  // footer hairline
  g.strokeStyle = "rgba(255,255,255,0.1)";
  g.beginPath();
  g.moveTo(44, 560);
  g.lineTo(W - 44, 560);
  g.stroke();

  // category tag (mono, colored)
  g.fillStyle = opts.accent;
  g.font = `600 24px ${FONT_MONO}`;
  g.textBaseline = "alphabetic";
  g.fillText(opts.tag.toUpperCase(), 44, 600);

  // year (mono, dim)
  g.fillStyle = "rgba(143, 160, 173, 0.85)";
  g.textAlign = "right";
  g.fillText(opts.year, W - 44, 600);
  g.textAlign = "left";

  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}
/** Soft radial glow sprite (for environment nebulas / scan bloom accents). */
export function drawGlowTexture(radius = 256): THREE.CanvasTexture {
  const cv = document.createElement("canvas");
  cv.width = radius * 2;
  cv.height = radius * 2;
  const g = cv.getContext("2d");
  if (!g) return new THREE.CanvasTexture(cv);
  const grad = g.createRadialGradient(radius, radius, 0, radius, radius, radius);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(0.25, "rgba(255,255,255,0.35)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, radius * 2, radius * 2);
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** Classification label sprite (e.g. "PROMOTIONS") used during the scan. */
export function drawLabelTexture(text: string, accent: string): THREE.CanvasTexture {
  const W = 512;
  const H = 96;
  const cv = document.createElement("canvas");
  cv.width = W;
  cv.height = H;
  const g = cv.getContext("2d");
  if (!g) return new THREE.CanvasTexture(cv);
  g.clearRect(0, 0, W, H);
  g.font = `600 34px ${FONT_MONO}`;
  g.textBaseline = "middle";
  const tw = Math.ceil(g.measureText(text.toUpperCase()).width);

  // dark pill behind label for legibility
  g.fillStyle = "rgba(4, 6, 10, 0.72)";
  g.beginPath();
  g.roundRect((W - tw) / 2 - 26, 6, tw + 52, H - 12, 8);
  g.fill();
  g.strokeStyle = "rgba(255,255,255,0.14)";
  g.lineWidth = 2;
  g.stroke();

  g.fillStyle = accent;
  g.textAlign = "center";
  g.fillText(text.toUpperCase(), W / 2, H / 2);
  g.textAlign = "left";

  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** The amber temporal boundary texture (thin line + faint grid). */
export function drawBoundaryTexture(): THREE.CanvasTexture {
  const W = 1024;
  const H = 512;
  const cv = document.createElement("canvas");
  cv.width = W;
  cv.height = H;
  const g = cv.getContext("2d");
  if (!g) return new THREE.CanvasTexture(cv);

  // very faint vertical hairlines (precision grid)
  g.strokeStyle = "rgba(254, 152, 0, 0.045)";
  g.lineWidth = 1;
  for (let x = 0; x <= W; x += 64) {
    g.beginPath();
    g.moveTo(x + 0.5, 0);
    g.lineTo(x + 0.5, H);
    g.stroke();
  }

  // full-width amber line — the "temporal boundary"
  g.strokeStyle = "rgba(254, 152, 0, 0.9)";
  g.lineWidth = 3;
  g.beginPath();
  g.moveTo(0, H / 2);
  g.lineTo(W, H / 2);
  g.stroke();
  g.strokeStyle = "rgba(254, 152, 0, 0.22)";
  g.lineWidth = 12;
  g.beginPath();
  g.moveTo(0, H / 2);
  g.lineTo(W, H / 2);
  g.stroke();

  // mono captions
  g.font = `500 26px ${FONT_MONO}`;
  g.fillStyle = "rgba(254, 152, 0, 0.85)";
  g.textAlign = "center";
  g.fillText("TEMPORAL  BOUNDARY", W / 2, H / 2 - 30);
  g.fillText("5 YEARS", W / 2, H / 2 + 52);
  g.textAlign = "left";

  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function wrapText(
  g: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  lineHeight: number,
  maxLines: number
): number {
  const words = text.split(" ");
  let line = "";
  let lines = 0;
  for (const word of words) {
    const test = line ? `${line} ${word}` : word;
    if (g.measureText(test).width > maxWidth && line) {
      g.fillText(line, x, y + lines * lineHeight);
      lines++;
      if (lines >= maxLines) return lines;
      line = word;
    } else {
      line = test;
    }
  }
  if (line && lines < maxLines) {
    g.fillText(line, x, y + lines * lineHeight);
    lines++;
  }
  return lines;
}