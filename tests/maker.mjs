// Target maker: drag the SE corner, check the size readout, and that print layout is true A4 / 1 unit = 1 mm.
import { createRequire } from 'node:module';
import path from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');
const browser = await chromium.launch();
const errors = [];
for (const [name, vp] of [['tablet', { width: 1180, height: 820 }], ['phone', { width: 390, height: 844 }]]) {
  const page = await browser.newPage({ viewport: vp });
  page.on('pageerror', (e) => errors.push(name + ': ' + e.message));
  await page.goto('file://' + path.resolve('docs/target.html'));
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.waitForTimeout(800);
  const before = await page.textContent('#outBlack');
  const h = await page.locator('.handle.se circle').nth(1).boundingBox();
  await page.mouse.move(h.x + h.width / 2, h.y + h.height / 2);
  await page.mouse.down();
  await page.mouse.move(h.x + h.width / 2 + 40, h.y + h.height / 2 + 40, { steps: 8 });
  await page.mouse.up();
  const after = await page.textContent('#outBlack');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
  await page.screenshot({ path: `tests/out/maker-${name}.png` });
  console.log(name, 'black diameter', before, '→', after, 'mm | horizontal overflow:', overflow ? 'YES' : 'no');
  if (name === 'tablet') {
    await page.click('[data-rings="7"]'); await page.click('[data-preset="max"]');
    console.log('black-only, A4 full:', await page.textContent('#outBlack'), 'mm |', await page.textContent('#outAll'));
    await page.click('[data-rings="1"]'); await page.click('[data-preset="59.5"]');
    await page.emulateMedia({ media: 'print' });
    const m = await page.evaluate(() => {
      const s = document.getElementById('sheet').getBoundingClientRect();
      const black = [...document.querySelectorAll('#sheet circle')].find((c) => c.getAttribute('fill') === '#000');
      const visibleAids = [...document.querySelectorAll('.noprint')].filter((e) => getComputedStyle(e).display !== 'none').length;
      return { wpx: s.width, hpx: s.height, r: +black.getAttribute('r'), visibleAids };
    });
    const mmPerPx = 25.4 / 96;
    console.log(`print: sheet ${(m.wpx * mmPerPx).toFixed(1)} x ${(m.hpx * mmPerPx).toFixed(1)} mm, black disk diameter ${(2 * m.r).toFixed(1)} mm, editing aids visible in print: ${m.visibleAids}`);
    await page.pdf({ path: 'tests/out/maker-print.pdf', preferCSSPageSize: true, printBackground: true });
  }
  await page.close();
}
console.log('errors:', errors.length ? errors : 'none');
await browser.close();
