// Per-frame cost of the laser detector at a given processing size (deterministic, no camera).
// usage: node tests/bench.mjs front_room 480 [frames]
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');
const [scene, size, nF] = [process.argv[2] || 'front_room', +(process.argv[3] || 480), +(process.argv[4] || 240)];
const buf = fs.readFileSync(`tests/out/${scene}.mjpeg`);
const frames = [];
for (let i = 0, s = -1; i < buf.length - 2; i++) if (buf[i] === 0xff && buf[i + 1] === 0xd8 && buf[i + 2] === 0xff) { if (s >= 0) frames.push([s, i]); s = i; }
const pick = (i) => 'data:image/jpeg;base64,' + buf.subarray(frames[i][0], frames[i][1]).toString('base64');
const browser = await chromium.launch();
const page = await browser.newPage();
await page.route(/fonts\./, (r) => r.abort());
await page.goto('file://' + path.resolve('docs/index.html'));
const urls = []; for (let i = 0; i < Math.min(nF, frames.length); i++) urls.push(pick(i));
const out = await page.evaluate(async ({ urls, size }) => {
  const d = window.LaserTarget._dbg;
  const load = (u) => new Promise((res) => { const im = new Image(); im.onload = () => res(im); im.src = u; });
  const ims = []; for (const u of urls) ims.push(await load(u));
  const cv = document.createElement('canvas'), g = cv.getContext('2d', { willReadFrequently: true });
  const f0 = ims[0], k = 640 / f0.width; cv.width = 640; cv.height = Math.round(f0.height * k); g.drawImage(f0, 0, 0, cv.width, cv.height);
  const t = d.detectTarget(g.getImageData(0, 0, cv.width, cv.height));
  const e = { cx: t.cx / k, cy: t.cy / k, a: t.a / k, b: t.b / k, theta: t.theta };
  const k2 = 2.75, roi = { x: Math.floor(e.cx - k2 * e.a), y: Math.floor(e.cy - k2 * e.b), w: Math.ceil(2 * k2 * e.a), h: Math.ceil(2 * k2 * e.b) };
  const pw = size, ph = size; // as if the camera were zoomed in so the ROI is bigger than the processing size
  const det = new d.LaserDetector(); det.configure(6, 'red');
  const mask = new Uint8Array(pw * ph); let x0 = pw, y0 = ph, x1 = -1, y1 = -1;
  for (let y = 1; y < ph - 1; y++) for (let x = 1; x < pw - 1; x++) { const u = (x + 0.5 - pw / 2) / (pw / 2 / 2.75), v = (y + 0.5 - ph / 2) / (ph / 2 / 2.75); if (u * u + v * v <= 2.6 * 2.6) { mask[y * pw + x] = 1; x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); } }
  det.setZone(mask, { x0, y0, x1, y1 });
  const pc = document.createElement('canvas'); pc.width = pw; pc.height = ph; const pg = pc.getContext('2d', { willReadFrequently: true });
  const tb = det.tierB.bind(det); let tB = 0; det.tierB = (...a) => { const s = performance.now(); const r = tb(...a); tB += performance.now() - s; return r; };
  const gn = det.gains.bind(det); let tG = 0; det.gains = (...a) => { const s = performance.now(); const r = gn(...a); tG += performance.now() - s; return r; };
  let tRead = 0, tProc = 0, n = 0;
  for (let rep = 0; rep < 2; rep++) for (const im of ims) {
    const s0 = performance.now();
    pg.drawImage(im, roi.x, roi.y, roi.w, roi.h, 0, 0, pw, ph);
    const id = pg.getImageData(0, 0, pw, ph);
    const s1 = performance.now();
    det.process(id);
    const s2 = performance.now();
    if (rep === 1) { tRead += s1 - s0; tProc += s2 - s1; n++; } else { tB = 0; tG = 0; }
  }
  return { n, read: tRead / n, proc: tProc / n, tierB: tB / n, gains: tG / n };
}, { urls, size });
console.log(scene, size + 'px', 'read+draw', out.read.toFixed(2), 'ms · detect', out.proc.toFixed(2), 'ms (gains', out.gains.toFixed(2), '· tierB', out.tierB.toFixed(2), ') over', out.n, 'frames');
await browser.close();
