/**
 * Crop the two workbench artifacts the pipeline figure needs, as elements rather than
 * as rectangles guessed out of a full-page screenshot.
 *
 *   node capture_figure_assets.mjs --out <dir>
 */
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

const argv = process.argv.slice(2);
const arg = (n, d) => { const i = argv.indexOf(`--${n}`); return i >= 0 ? argv[i + 1] : d; };
const BASE = arg('base', 'http://localhost:3000');
const OUT = arg('out', path.resolve('figure-assets'));
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true,
  args: ['--hide-scrollbars'] });
const context = await browser.newContext({
  viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 3 });
const page = await context.newPage();

await page.goto(BASE, { waitUntil: 'load' });
await page.waitForFunction(
  () => !document.querySelector('.viewport-busy') && !!document.querySelector('.stage canvas'),
  null, { timeout: 240000 }).catch(() => {});
await page.getByRole('button', { name: 'Skip', exact: false }).first().click().catch(() => {});
await page.waitForTimeout(2500);
await page.getByRole('button', { name: 'Close rationale', exact: false }).first().click()
  .catch(() => {});
await page.waitForTimeout(1500);

// The recording, drawn as the score the compiler read it as.
const strip = page.locator('.score-sheet').first();
if (await strip.count()) {
  await strip.screenshot({ path: path.join(OUT, 'score_strip.png') });
  console.log('  score_strip.png');
}

// The ten dimensions as one shape. It lives in the Shared score report.
await page.getByRole('button', { name: 'Reports', exact: false }).first().click();
await page.waitForTimeout(500);
await page.getByRole('menuitem', { name: 'Shared score', exact: false }).first().click();
await page.waitForTimeout(2200);
const signature = page.locator('svg[aria-label="The ten score dimensions as one shape"]').first();
if (await signature.count()) {
  await signature.screenshot({ path: path.join(OUT, 'signature.png') });
  console.log('  signature.png');
}

await context.close();
await browser.close();
