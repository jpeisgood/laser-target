// Smoke test: load the page, let the attract-mode demo run, then open setup with the demo source.
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('playwright');
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(process.argv[2] || 'docs');
const outDir = path.resolve('tests/out');
const server = http.createServer((req, res) => {
  const p = path.join(root, decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, '') || 'index.html');
  fs.readFile(p, (err, data) => { if (err) { res.writeHead(404); res.end(); return; } res.writeHead(200, { 'content-type': p.endsWith('.html') ? 'text/html; charset=utf-8' : 'application/octet-stream' }); res.end(data); });
}).listen(0);
const port = server.address().port;
const browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
const page = await browser.newPage({ viewport: { width: 1180, height: 820 }, deviceScaleFactor: 1 });
const errors = [];
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
await page.goto(`http://localhost:${port}/index.html`);
await page.waitForTimeout(9000);
const s1 = await page.evaluate(() => ({ calib: window.LaserTarget._dbg.calib, game: window.LaserTarget._dbg.game.phase, hits: window.LaserTarget._dbg.game.hits, shots: window.LaserTarget._dbg.game.shots, perf: window.LaserTarget._dbg.perf, recent: window.LaserTarget._dbg.recent.map(r => ({hit: r.hit, score: r.score, rho: +r.rho?.toFixed(2)})) }));
console.log('attract:', JSON.stringify(s1, null, 0));
await page.screenshot({ path: path.join(outDir, 'smoke-start.png') });
await page.click('#btnStartDemo');
await page.waitForTimeout(500);
await page.evaluate(() => window.LaserTarget._dbg.openSetup());
await page.waitForTimeout(4000);
await page.screenshot({ path: path.join(outDir, 'smoke-setup.png') });
await page.click('#btnToBoard');
await page.waitForTimeout(6000);
await page.screenshot({ path: path.join(outDir, 'smoke-board.png') });
console.log('errors:', errors.length ? errors : 'none');
await browser.close(); server.close();
