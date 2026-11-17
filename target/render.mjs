// Render the SVG targets to A4 PDFs (for printing) and PNG textures (for the synthetic test videos).
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');
const dir = path.dirname(new URL(import.meta.url).pathname);
const browser = await chromium.launch();
const page = await browser.newPage();
for (const f of fs.readdirSync(dir).filter((f) => f.endsWith('.svg'))) {
  const svg = fs.readFileSync(path.join(dir, f), 'utf8');
  const html = `<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=IBM+Plex+Sans+KR:wght@400;600&display=swap"><style>@page{size:A4;margin:0}html,body{margin:0;padding:0}svg{display:block}</style></head><body>${svg}</body></html>`;
  await page.setContent(html, { waitUntil: 'networkidle' }).catch(() => {});
  await page.evaluate(() => document.fonts && document.fonts.ready);
  const base = f.replace(/\.svg$/, '');
  await page.pdf({ path: path.join(dir, base + '.pdf'), width: '210mm', height: '297mm', printBackground: true, margin: { top: 0, right: 0, bottom: 0, left: 0 } });
  // texture: 4 px per mm
  await page.setViewportSize({ width: 840, height: 1188 });
  await page.evaluate(() => { const s = document.querySelector('svg'); s.setAttribute('width', '840px'); s.setAttribute('height', '1188px'); });
  await page.screenshot({ path: path.join(dir, base + '.png'), clip: { x: 0, y: 0, width: 840, height: 1188 } });
  console.log('rendered', base);
}
await browser.close();
