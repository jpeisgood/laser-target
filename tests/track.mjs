// Does the target tracking follow a camera nudge? Runs scene_a4 (nudge of (+4,-3) px at frame 465).
import { createRequire } from 'node:module';
import path from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');
const video = path.resolve('tests/out/scene_a4.mjpeg');
const browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-video-capture=${video}`] });
const page = await browser.newPage({ viewport: { width: 1180, height: 820 } });
await page.route(/fonts\./, (r) => r.abort());
await page.goto('file://' + path.resolve('docs/index.html'));
await page.click('#btnStartCamera');
await page.waitForFunction(() => window.LaserTarget._dbg.calib, null, { timeout: 20000 });
const t0 = await page.evaluate(() => window.LaserTarget._dbg.perf.startAt);
const samples = [];
for (let i = 0; i < 26; i++) {
  await page.waitForTimeout(1000);
  samples.push(await page.evaluate((t0) => { const d = window.LaserTarget._dbg; return { s: ((performance.now() - t0) / 1000).toFixed(1), cx: d.calib.cx.toFixed(1), cy: d.calib.cy.toFixed(1), fails: d.trackFails, tracks: d.trackRuns }; }, t0));
}
console.log(samples.map((s) => `${s.s}s c=(${s.cx},${s.cy}) runs=${s.tracks} fails=${s.fails}`).join('\n'));
await browser.close();
