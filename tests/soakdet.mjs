// Deterministic false-alarm count: every frame of a scene through the detector in order (no real-time camera),
// with the same one-trigger-one-shot rule as the app. usage: node tests/soakdet.mjs out_soak [sens] [page.html]
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');
const scene = process.argv[2] || 'out_soak', sens = +(process.argv[3] || 6), pageFile = process.argv[4] || 'docs/index.html';
const buf = fs.readFileSync(`tests/out/${scene}.mjpeg`);
const meta = JSON.parse(fs.readFileSync(`tests/out/${scene}.json`, 'utf8'));
const frames = [];
for (let i = 0, s = -1; i < buf.length - 2; i++) if (buf[i] === 0xff && buf[i + 1] === 0xd8 && buf[i + 2] === 0xff) { if (s >= 0) frames.push([s, i]); s = i; }
frames.push([frames[frames.length - 1][1], buf.length]);
const url = (i) => 'data:image/jpeg;base64,' + buf.subarray(frames[i][0], frames[i][1]).toString('base64');
const browser = await chromium.launch();
const page = await browser.newPage();
await page.route(/fonts\./, (r) => r.abort());
await page.goto('file://' + path.resolve(pageFile));
await page.evaluate(async ({ u0, sens }) => {
  const d = window.LaserTarget._dbg;
  const load = (u) => new Promise((res) => { const im = new Image(); im.onload = () => res(im); im.src = u; });
  const f0 = await load(u0), cv = document.createElement('canvas'), g = cv.getContext('2d', { willReadFrequently: true });
  const k = 640 / f0.width; cv.width = 640; cv.height = Math.round(f0.height * k); g.drawImage(f0, 0, 0, cv.width, cv.height);
  const t = d.detectTarget(g.getImageData(0, 0, cv.width, cv.height));
  const e = { cx: t.cx / k, cy: t.cy / k, a: t.a / k, b: t.b / k, theta: t.theta };
  const c = Math.cos(e.theta), s = Math.sin(e.theta), k2 = 2.75;
  const hw = k2 * Math.hypot(e.a * c, e.b * s), hh = k2 * Math.hypot(e.a * s, e.b * c);
  const roi = { x: Math.floor(e.cx - hw), y: Math.floor(e.cy - hh), w: Math.ceil(2 * hw), h: Math.ceil(2 * hh) };
  const sc = Math.min(1, 400 / Math.max(roi.w, roi.h)), pw = Math.round(roi.w * sc), ph = Math.round(roi.h * sc);
  const det = new d.LaserDetector(); det.configure(sens, 'red');
  const mask = new Uint8Array(pw * ph); let x0 = pw, y0 = ph, x1 = -1, y1 = -1; const kx = roi.w / pw, ky = roi.h / ph;
  for (let y = 1; y < ph - 1; y++) for (let x = 1; x < pw - 1; x++) { const sx = roi.x + (x + 0.5) * kx - e.cx, sy = roi.y + (y + 0.5) * ky - e.cy;
    const u = (sx * c + sy * s) / e.a, v = (-sx * s + sy * c) / e.b; if (u * u + v * v <= 2.6 * 2.6) { mask[y * pw + x] = 1; x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); } }
  det.setZone(mask, { x0, y0, x1, y1 });
  const pc = document.createElement('canvas'); pc.width = pw; pc.height = ph;
  window.__S = { det, roi, pw, ph, pg: pc.getContext('2d', { willReadFrequently: true }), load, e };
}, { u0: url(0), sens });
const shots = [];
let state = 'ready', start = 0, last = -1e9, lastSeen = -1e9, best = null, n = 0;
for (let i = 1; i < frames.length; i++) {
  const r = await page.evaluate(async (u) => {
    const S = window.__S, im = await S.load(u);
    S.pg.drawImage(im, S.roi.x, S.roi.y, S.roi.w, S.roi.h, 0, 0, S.pw, S.ph);
    const b = S.det.process(S.pg.getImageData(0, 0, S.pw, S.ph));
    return b ? { x: S.roi.x + b.x * S.roi.w / S.pw, y: S.roi.y + b.y * S.roi.h / S.ph, tier: b.tier || 'A', z: b.z || 0, e: b.energy } : null;
  }, url(i));
  const t = (i * 1000) / meta.fps;
  if (state === 'ready') { if (r && t - last >= 250) { state = 'active'; start = t; best = r; n = 1; lastSeen = t; best.f = i; } }
  else if (state === 'active') {
    if (r) { n++; lastSeen = t; if (r.e > best.e) best = Object.assign(r, { f: best.f }); }
    if (!r) { state = 'cool'; last = start; shots.push({ f: best.f, x: +best.x.toFixed(0), y: +best.y.toFixed(0), tier: best.tier, z: +best.z.toFixed(1), n }); }
    else if (t - start >= 500) { state = 'cool'; last = start; }
  } else { if (r) lastSeen = t; if (t - lastSeen >= 90 && t - last >= 250) state = 'ready'; }
}
const truth = meta.shots || [];
const fa = shots.filter((s) => !truth.some((g) => Math.abs(g.frame - s.f) <= 3 && Math.hypot(g.x - s.x, g.y - s.y) < 10));
const hits = truth.filter((g) => shots.some((s) => Math.abs(g.frame - s.f) <= 3 && Math.hypot(g.x - s.x, g.y - s.y) < 10)).length;
console.log(`${scene} sens ${sens} ${path.basename(pageFile)}: shots ${shots.length} · true found ${hits}/${truth.length} · false ${fa.length}`, fa.map((s) => `f${s.f}(${s.x},${s.y})${s.tier}${s.z ? ' z' + s.z : ''}x${s.n}`).join(' '));
await browser.close();
