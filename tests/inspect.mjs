// Frame-by-frame look at the detector on a synthetic video (deterministic, no real-time camera).
// usage: node tests/inspect.mjs scene_a4 230 240
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');
const [scene, a, b] = [process.argv[2], +process.argv[3], +process.argv[4]];
const buf = fs.readFileSync(`tests/out/${scene}.mjpeg`);
const frames = [];
for (let i = 0, s = -1; i < buf.length - 1; i++) if (buf[i] === 0xff && buf[i + 1] === 0xd8 && buf[i + 2] === 0xff) { if (s >= 0) frames.push([s, i]); s = i; if (i > buf.length - 4) break; }
frames.push([frames.length ? frames[frames.length - 1][1] : 0, buf.length]);
const pick = (i) => 'data:image/jpeg;base64,' + buf.subarray(frames[i][0], frames[i][1]).toString('base64');
const browser = await chromium.launch();
const page = await browser.newPage();
await page.route(/fonts\./, (r) => r.abort());
await page.goto('file://' + path.resolve('docs/index.html'));
const warm = Math.max(1, a - 40);
const list = [0]; for (let i = warm; i <= b; i++) list.push(i);
const out = await page.evaluate(async ({ urls, idx, a }) => {
  const d = window.LaserTarget._dbg;
  const load = (u) => new Promise((res) => { const im = new Image(); im.onload = () => res(im); im.src = u; });
  const cv = document.createElement('canvas'), g = cv.getContext('2d', { willReadFrequently: true });
  const f0 = await load(urls[0]);
  const k = 640 / f0.width; cv.width = 640; cv.height = Math.round(f0.height * k); g.drawImage(f0, 0, 0, cv.width, cv.height);
  const t = d.detectTarget(g.getImageData(0, 0, cv.width, cv.height));
  const e = { cx: t.cx / k, cy: t.cy / k, a: t.a / k, b: t.b / k, theta: t.theta };
  const c = Math.cos(e.theta), s = Math.sin(e.theta), k2 = 2.75;
  const hw = k2 * Math.hypot(e.a * c, e.b * s), hh = k2 * Math.hypot(e.a * s, e.b * c);
  const roi = { x: Math.floor(e.cx - hw), y: Math.floor(e.cy - hh), w: Math.ceil(2 * hw), h: Math.ceil(2 * hh) };
  const sc = Math.min(1, 480 / Math.max(roi.w, roi.h)), pw = Math.round(roi.w * sc), ph = Math.round(roi.h * sc);
  const det = new d.LaserDetector(); det.configure(6, 'red');
  { const mask = new Uint8Array(pw * ph); let x0 = pw, y0 = ph, x1 = -1, y1 = -1; const kx = roi.w / pw, ky = roi.h / ph;
    for (let y = 1; y < ph - 1; y++) for (let x = 1; x < pw - 1; x++) { const sx = roi.x + (x + 0.5) * kx - e.cx, sy = roi.y + (y + 0.5) * ky - e.cy;
      const u = (sx * c + sy * s) / e.a, v = (-sx * s + sy * c) / e.b; if (u * u + v * v <= 2.6 * 2.6) { mask[y * pw + x] = 1; x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); } }
    det.setZone(mask, { x0, y0, x1, y1 }); }
  const pc = document.createElement('canvas'); pc.width = pw; pc.height = ph; const pg = pc.getContext('2d', { willReadFrequently: true });
  const rows = [];
  for (let n = 1; n < urls.length; n++) {
    const im = await load(urls[n]);
    pg.drawImage(im, roi.x, roi.y, roi.w, roi.h, 0, 0, pw, ph);
    const bl = det.process(pg.getImageData(0, 0, pw, ph));
    if (idx[n] >= a) rows.push({ f: idx[n], peak: +det.peak.toFixed(2), pz: +(det.peakZ||0).toFixed(2), moved: det.moved || 0, stale: det.stale || 0, blobs: det.blobs, gain: +det.gain?.toFixed(3), best: bl && { tier: bl.tier || 'A', z: bl.z && +bl.z.toFixed(1), x: +(roi.x + bl.x * roi.w / pw).toFixed(1), y: +(roi.y + bl.y * roi.h / ph).toFixed(1), area: bl.area, red: bl.red, pk: Math.round(bl.peak) } });
  }
  return { e, roi, pw, ph, rows };
}, { urls: list.map(pick), idx: list, a });
console.log('ellipse', JSON.stringify(out.e), 'roi', JSON.stringify(out.roi), out.pw + 'x' + out.ph);
for (const r of out.rows) console.log(JSON.stringify(r));
await browser.close();
