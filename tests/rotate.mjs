// Does the page still fit the screen after rotating / resizing? Checks several iPad sizes and a portrait->landscape turn.
import { createRequire } from 'node:module';
import path from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');
const video = path.resolve('tests/out/' + (process.argv[2] || 'scene_photo') + '.mjpeg');
const browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-video-capture=${video}`] });
const page = await browser.newPage({ viewport: { width: 820, height: 1180 } });
await page.route(/fonts\./, (r) => r.abort());
await page.addInitScript(() => { try { localStorage.clear(); } catch (e) {} });
await page.goto('file://' + path.resolve('docs/index.html'));
await page.click('#btnStartCamera');
await page.waitForFunction(() => window.LaserTarget._dbg.calib, null, { timeout: 20000 });
await page.waitForTimeout(800);
const measure = () => page.evaluate(() => {
  const r = (id) => document.getElementById(id).getBoundingClientRect();
  const worst = [...document.querySelectorAll('#app *:not(.stage *)')].filter((e) => e.offsetParent !== null || e.id === 'stage').reduce((m, e) => { const b = e.getBoundingClientRect(); return { right: Math.max(m.right, b.right), bottom: Math.max(m.bottom, b.bottom) }; }, { right: 0, bottom: 0 });
  return { vw: innerWidth, vh: innerHeight, docW: document.documentElement.scrollWidth, docH: document.documentElement.scrollHeight, stage: Math.round(r('stage').width) + 'x' + Math.round(r('stage').height), leds: Math.round(r('leds').width), side: Math.round(document.querySelector('.side').getBoundingClientRect().left), maxRight: Math.round(worst.right), maxBottom: Math.round(worst.bottom) };
});
console.log('portrait  820x1180', JSON.stringify(await measure()));
for (const [w, h] of [[1180, 820], [1180, 740], [1133, 744], [1024, 700], [1366, 980]]) {
  await page.setViewportSize({ width: w, height: h });
  await page.waitForTimeout(600);
  const m = await measure();
  const bad = m.maxRight > m.vw + 1 || m.maxBottom > m.vh + 1 || m.docW > m.vw || m.docH > m.vh;
  console.log(`${bad ? 'OVERFLOW' : 'fits    '} ${w}x${h}`, JSON.stringify(m));
}
await page.screenshot({ path: 'tests/out/rotate-last.png' });
await browser.close();
