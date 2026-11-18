// Screenshot of the 진단 panel after a few detections (settings mode, fake camera).
import { createRequire } from 'node:module';
import path from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');
const video = path.resolve('tests/out/front_room.mjpeg');
const browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-video-capture=${video}`] });
const page = await browser.newPage({ viewport: { width: 1180, height: 820 } });
await page.route(/fonts\./, (r) => r.abort());
await page.goto('file://' + path.resolve('docs/index.html'));
await page.click('#btnStartCamera');
await page.waitForFunction(() => window.LaserTarget._dbg.calib, null, { timeout: 20000 });
await page.click('#btnSetup');
await page.waitForTimeout(9000);
await page.evaluate(() => document.getElementById('diagCanvas').scrollIntoView({ block: 'end' }));
await page.waitForTimeout(400);
await page.screenshot({ path: 'tests/out/diag-panel.png' });
console.log('diag events:', await page.evaluate(() => window.LaserTarget._dbg.diag.length), '| chip:', await page.textContent('#chipSrc'));
await browser.close();
