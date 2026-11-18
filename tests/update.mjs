// Update check: an old copy (different LT_VERSION) must reload itself to ?v=<new>, keep ?lane, and then stop.
import { createRequire } from 'node:module';
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');
const root = path.resolve('docs');
const fresh = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const old = fresh.replace(/LT_VERSION = "[^"]*"/, 'LT_VERSION = "old0000000"');
const server = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  if (u.pathname.endsWith('/') || u.pathname.endsWith('index.html')) { res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }); res.end(u.searchParams.has('v') ? fresh : old); return; }
  fs.readFile(path.join(root, u.pathname), (e, d) => { if (e) { res.writeHead(404); res.end(); } else { res.writeHead(200); res.end(d); } });
}).listen(0);
const browser = await chromium.launch();
const page = await browser.newPage();
await page.route(/fonts\./, (r) => r.abort());
await page.goto(`http://localhost:${server.address().port}/?lane=3`);
await page.waitForTimeout(2500);
console.log('url after load:', page.url().replace(/^http:\/\/localhost:\d+/, ''), '| running version:', await page.evaluate(() => window.LT_VERSION), '| lane shown:', await page.textContent('#laneNo'));
await browser.close(); server.close();
