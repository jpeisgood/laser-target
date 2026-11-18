// End-to-end: headless Chromium uses a synthetic video as its webcam; the app runs exactly as on a tablet.
// Phase 1 (setup screen): every detected flash is compared with ground truth (position, hit/miss, score).
// Phase 2 (scoreboard): the game must light LEDs, reach CLEAR and reset by itself.
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const { chromium } = createRequire(import.meta.url)('playwright');
const scene = process.argv[2] || 'scene_a4';
const sens = process.argv[3] ? Number(process.argv[3]) : null;
const meta = JSON.parse(fs.readFileSync(`tests/out/${scene}.json`, 'utf8'));
const videoPath = path.resolve(`tests/out/${scene}.mjpeg`);
const root = path.resolve('docs');

const server = http.createServer((req, res) => {
  const p = path.join(root, decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, '') || 'index.html');
  fs.readFile(p, (err, data) => {
    if (err) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'content-type': p.endsWith('.html') ? 'text/html; charset=utf-8' : 'application/octet-stream' });
    res.end(data);
  });
}).listen(0);
const url = `http://localhost:${server.address().port}/index.html`;

const browser = await chromium.launch({
  args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-video-capture=${videoPath}`],
});
const page = await browser.newPage({ viewport: { width: 1180, height: 820 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
await page.goto(url);
if (sens) await page.evaluate((s) => window.LaserTarget.configure({ sensitivity: s }), sens);
// the synthetic scenes are filmed at an angle; only front_* scenes are head-on
if (!scene.startsWith('front')) await page.evaluate(() => window.LaserTarget.configure({ frontal: false }));
await page.click('#btnStartCamera');
await page.evaluate(() => window.LaserTarget._dbg.openSetup()); // phase 1 runs as test shots in settings mode
await page.waitForFunction(() => window.LaserTarget._dbg.calib, null, { timeout: 20000 });
const startAt = await page.evaluate(() => window.LaserTarget._dbg.perf.startAt);
const calibAt = await page.evaluate(() => performance.now());
const loopMs = (meta.frames / meta.fps) * 1000;
await page.waitForFunction((end) => performance.now() > end, startAt + loopMs + 300, { timeout: loopMs + 30000, polling: 250 });
const r1 = await page.evaluate(() => {
  const d = window.LaserTarget._dbg;
  return { shots: d.allShots.map((s) => ({ t: s.t, x: s.x, y: s.y, rho: s.rho, hit: s.hit, score: s.score, frames: s.frames })), calib: d.calib, perf: d.perf, src: [document.getElementById('video').videoWidth, document.getElementById('video').videoHeight] };
});
await page.screenshot({ path: `tests/out/${scene}-setup.png` });

// ---- match detections to ground truth ----
const fps = meta.fps;
const det = r1.shots.filter((s) => s.t - startAt < loopMs - 100).map((s) => ({ ...s, f: ((s.t - startAt) / 1000) * fps }));
const offs = [];
for (const d of det) for (const g of meta.shots) if (Math.hypot(d.x - g.x, d.y - g.y) < 6) offs.push(d.f - g.frame);
offs.sort((a, b) => a - b);
const off = offs.length ? offs[Math.floor(offs.length / 2)] : 0;
const used = new Set();
const rows = [];
for (const g of meta.shots) {
  let best = null;
  det.forEach((d, i) => {
    if (used.has(i)) return;
    const dist = Math.hypot(d.x - g.x, d.y - g.y), df = Math.abs(d.f - g.frame - off);
    if (dist < 8 && df < 6 && (!best || dist < best.dist)) best = { i, dist, d };
  });
  if (best) used.add(best.i);
  rows.push({ g, m: best });
}
const fps_ = r1.perf.fps.toFixed(1), proc = r1.perf.procMs.toFixed(2);
const before = rows.filter((r) => r.g.frame / fps * 1000 < calibAt - startAt + 200);
console.log(`\n=== ${scene}  (camera ${r1.src.join('x')}, processed ${fps_} fps, ${proc} ms/frame, frame offset ${off.toFixed(1)}) ===`);
console.log(`calibration: center (${r1.calib.cx.toFixed(1)}, ${r1.calib.cy.toFixed(1)})  a=${r1.calib.a.toFixed(1)} b=${r1.calib.b.toFixed(1)}  true center (${meta.truth.center.map((v) => v.toFixed(1)).join(', ')})`);
console.log('frame  true-rho  hit | found  err(px)  app-rho  app-hit  score  frames  note');
let found = 0, agree = 0, fp = 0, rhoErr = [];
for (const { g, m } of rows) {
  const note = [g.dur === 1 && g.strength[0] < 0.4 ? 'weak 1-frame flash' : '', Math.abs(g.rho - 1) < 0.07 ? 'edge' : ''].filter(Boolean).join(', ');
  if (m) {
    found++; rhoErr.push(Math.abs(m.d.rho - g.rho));
    const ok = m.d.hit === g.hit; if (ok) agree++;
    console.log(`${String(g.frame).padStart(5)}  ${g.rho.toFixed(3).padStart(7)}  ${g.hit ? 'HIT ' : 'miss'}| yes   ${m.dist.toFixed(2).padStart(6)}  ${m.d.rho.toFixed(3).padStart(7)}  ${m.d.hit ? 'HIT ' : 'miss'}${ok ? '   ' : ' ✗ '}  ${String(m.d.score).padStart(3)}/${String(g.score).padEnd(3)} ${String(m.d.frames).padStart(3)}/${g.dur}   ${note}`);
  } else {
    console.log(`${String(g.frame).padStart(5)}  ${g.rho.toFixed(3).padStart(7)}  ${g.hit ? 'HIT ' : 'miss'}| NO                                         ${note}`);
  }
}
det.forEach((d, i) => { if (!used.has(i)) { fp++; console.log(`FALSE DETECTION at frame ~${(d.f - off).toFixed(0)} (${d.x.toFixed(0)}, ${d.y.toFixed(0)}) rho ${d.rho?.toFixed(2)}`); } });
rhoErr.sort((a, b) => a - b);
console.log(`detected ${found}/${meta.shots.length} · hit/miss agree ${agree}/${found} · false detections ${fp} · rho error median ${(rhoErr[Math.floor(rhoErr.length / 2)] || 0).toFixed(3)} max ${(rhoErr[rhoErr.length - 1] || 0).toFixed(3)}`);

// ---- phase 2: scoreboard ----
await page.click('#btnToBoard');
const p2 = await page.evaluate(() => performance.now());
const seen = [];
await page.exposeFunction('__ev', (m) => seen.push(m));
await page.evaluate(() => window.LaserTarget.on('*', (m) => window.__ev({ type: m.type, hits: m.series && m.series.hits, shots: m.series && m.series.shots })));
await page.waitForTimeout(loopMs);
await page.screenshot({ path: `tests/out/${scene}-board.png` });
const counts = seen.reduce((a, m) => ((a[m.type] = (a[m.type] || 0) + 1), a), {});
console.log('scoreboard events in one loop:', JSON.stringify(counts), '| clears:', seen.filter((m) => m.type === 'clear').map((m) => `${m.hits}/${m.shots}`).join(' '));
console.log('page errors:', errors.length ? errors : 'none');
await browser.close();
server.close();
