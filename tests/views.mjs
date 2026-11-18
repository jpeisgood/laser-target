// Screens on a fake camera: iPad landscape + portrait. Board (target left 2/3, side 1/3), settings mode, CLEAR.
import { createRequire } from 'node:module';
import path from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');
const video = path.resolve('tests/out/' + (process.argv[2] || 'scene_photo') + '.mjpeg');
const browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-video-capture=${video}`] });
const errors = [];
async function run(name, viewport) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 });
  page.on('pageerror', (e) => errors.push(name + ': ' + e.message));
  await page.route(/fonts\./, (r) => r.abort());
  await page.goto('file://' + path.resolve('docs/index.html'));
  await page.screenshot({ path: `tests/out/view-${name}-start.png` });
  await page.click('#btnStartCamera');
  const afterStart = await page.evaluate(() => ({ mode: window.LaserTarget._dbg.mode, setupHidden: document.getElementById('setup').hidden }));
  await page.evaluate(() => window.LaserTarget.configure({ roster: '3-2 김민준\n3-2 이서연\n3-2 박도윤', shooterIdx: 0 }));
  await page.waitForFunction(() => window.LaserTarget._dbg.calib, null, { timeout: 20000 });
  await page.waitForTimeout(1500);
  await page.evaluate(() => window.LaserTarget.reset());
  for (const [x, y] of [[0.1, 0.2], [-0.3, 0.4], [1.6, 0.3]]) { await page.evaluate(([x, y]) => window.LaserTarget.simulateShot(x, y), [x, y]); await page.waitForTimeout(300); }
  await page.waitForTimeout(600);
  await page.screenshot({ path: `tests/out/view-${name}-board.png` });
  const ov = await page.evaluate(() => ({ scrollW: document.documentElement.scrollWidth, w: innerWidth, led: getComputedStyle(document.getElementById('leds')).getPropertyValue('--led-size') }));
  for (const [x, y] of [[0.5, -0.2], [0.0, 0.0], [0.3, 0.3]]) { await page.evaluate(([x, y]) => window.LaserTarget.simulateShot(x, y), [x, y]); await page.waitForTimeout(300); }
  await page.waitForTimeout(400);
  await page.screenshot({ path: `tests/out/view-${name}-clear.png` });
  await page.click('#result');
  const next = await page.textContent('#shooterName');
  await page.click('#btnSetup');
  await page.waitForTimeout(800);
  await page.screenshot({ path: `tests/out/view-${name}-setup.png` });
  console.log(name, '| after start:', JSON.stringify(afterStart), '| LED size', ov.led, '| overflow', ov.scrollW > ov.w ? 'YES' : 'no', '| next shooter after CLEAR:', next);
  await page.close();
}
await run('ipad-land', { width: 1180, height: 820 });
await run('ipad-port', { width: 820, height: 1180 });
await run('phone', { width: 390, height: 844 });
console.log('errors:', errors.length ? errors : 'none');
await browser.close();
