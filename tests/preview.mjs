// The claude.ai preview variant (no LT_STANDALONE flag, camera blocked): start card + camera refusal message.
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');
const body = fs.readFileSync('src/app.html', 'utf8');
fs.writeFileSync('tests/out/preview.html', `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"></head><body>${body}</body></html>`);
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1024, height: 768 } }); // no camera permission
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
await page.goto('file://' + path.resolve('tests/out/preview.html'));
await page.waitForTimeout(3500);
await page.click('#btnStartCamera');
await page.waitForTimeout(1500);
await page.screenshot({ path: 'tests/out/preview-start.png' });
console.log('note:', await page.textContent('#startNote'));
console.log('errors:', errors.length ? errors : 'none');
await browser.close();
