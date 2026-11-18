// Diagnosis recorder + diagnosis panel on a fake camera: records 12 s, checks the video and the log file,
// and screenshots the panel (position map, crops, frame numbers).
// usage: node tests/rec.mjs [scene]
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');
const scene = process.argv[2] || 'front_room';
const root = path.resolve('docs');
const server = http.createServer((req, res) => {
  const p = path.join(root, decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, '') || 'index.html');
  fs.readFile(p, (err, data) => { if (err) { res.writeHead(404); res.end(); return; } res.writeHead(200, { 'content-type': p.endsWith('.html') ? 'text/html; charset=utf-8' : 'application/octet-stream' }); res.end(data); });
}).listen(0);
const browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-video-capture=${path.resolve(`tests/out/${scene}.mjpeg`)}`] });
const page = await browser.newPage({ viewport: { width: 1180, height: 820 }, deviceScaleFactor: 2 });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
await page.goto(`http://localhost:${server.address().port}/index.html`);
await page.click('#btnStartCamera');
await page.evaluate(() => window.LaserTarget._dbg.openSetup());
await page.waitForFunction(() => window.LaserTarget._dbg.calib && window.LaserTarget._dbg.rd.mode !== 'starting', null, { timeout: 20000 });
await page.click('#btnRec');
await page.waitForFunction(() => !!window.LaserTarget._dbg.rec.file, null, { timeout: 30000 });
const r = await page.evaluate(async () => {
  const d = window.LaserTarget._dbg, rec = d.rec;
  const log = JSON.parse(await rec.json.text());
  return { video: { name: rec.file.name, type: rec.file.type, size: rec.file.size }, logName: rec.json.name, frames: log.frames.length, events: log.events.length,
    firstEvent: log.events[0], reader: log.reader, lost: log.end.lostTotal, cam: log.camera && Object.keys(log.camera.caps || {}).length, keys: Object.keys(log),
    hasRoster: 'roster' in log.settings, info: document.getElementById('recInfo').textContent, saveShown: !document.getElementById('btnRecSave').hidden };
});
console.log(JSON.stringify(r, null, 1));
// keep both files, so tests/replay.py can be tried on a real recording of the app
const files = await page.evaluate(async () => {
  const rec = window.LaserTarget._dbg.rec, b64 = async (f) => { const u = new Uint8Array(await f.arrayBuffer()); let s = ''; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); };
  return { video: await b64(rec.file), log: await rec.json.text() };
});
fs.writeFileSync(`tests/out/rec_${scene}.mp4`, Buffer.from(files.video, 'base64'));
fs.writeFileSync(`tests/out/rec_${scene}-log.txt`, files.log);
console.log(`saved tests/out/rec_${scene}.mp4 + -log.txt`);
await page.evaluate(() => document.getElementById('diagCanvas').scrollIntoView());
await page.waitForTimeout(400);
const box = await page.evaluate(() => { const s = document.getElementById('diagCanvas').closest('section').getBoundingClientRect(); return { x: s.x, y: s.y, width: s.width, height: Math.min(s.height, 1400) }; });
await page.screenshot({ path: `tests/out/${scene}-diag.png`, clip: box, fullPage: true });
console.log('page errors:', errors.length ? errors : 'none');
await browser.close(); server.close();
