// Screens at tablet and phone sizes: setup (zoomed), board, CLEAR.
import { createRequire } from 'node:module';
import path from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');
const video = path.resolve('tests/out/scene_photo.mjpeg');
const browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-video-capture=${video}`] });
const errors = [];
async function run(name, viewport) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 });
  page.on('pageerror', (e) => errors.push(name + ': ' + e.message));
  await page.route(/fonts\./, (r) => r.abort());
  await page.goto('file://' + path.resolve('docs/index.html'));
  await page.click('#btnStartCamera');
  await page.waitForFunction(() => window.LaserTarget._dbg.calib, null, { timeout: 20000 });
  await page.click('#btnZoom');
  await page.waitForTimeout(9000);
  await page.screenshot({ path: `tests/out/view-${name}-setup.png` });
  const ov = await page.evaluate(() => ({ scrollW: document.documentElement.scrollWidth, w: innerWidth }));
  await page.click('#btnToBoard');
  await page.waitForTimeout(400);
  for (const [x, y] of [[0.1, 0.2], [-0.3, 0.4], [0.5, -0.2], [1.6, 0.3], [0.0, 0.0], [0.3, 0.3]]) { await page.evaluate(([x, y]) => window.LaserTarget.simulateShot(x, y), [x, y]); await page.waitForTimeout(350); }
  await page.waitForTimeout(300);
  await page.screenshot({ path: `tests/out/view-${name}-clear.png` });
  await page.click('#result');
  await page.evaluate(() => { window.LaserTarget.simulateShot(0.2, 0.1); window.LaserTarget.simulateShot(1.4, -0.6); });
  await page.waitForTimeout(500);
  await page.screenshot({ path: `tests/out/view-${name}-board.png` });
  console.log(name, 'horizontal overflow:', ov.scrollW > ov.w ? `YES (${ov.scrollW} > ${ov.w})` : 'no');
  await page.close();
}
await run('tablet', { width: 1180, height: 820 });
await run('phone', { width: 390, height: 844 });
console.log('errors:', errors.length ? errors : 'none');
await browser.close();
