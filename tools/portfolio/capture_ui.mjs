/**
 * Capture the workbench UI at 2x for the portfolio.
 *
 * Every shot is the real app driven by real clicks against the dev server; nothing is
 * mocked and nothing is retouched. The model has to be on the stage before the clock
 * starts or the first frames catch an empty viewport.
 *
 *   node capture_ui.mjs --out <dir> [--base http://localhost:3000]
 */
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const argv = process.argv.slice(2);
const arg = (name, fallback) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 ? argv[i + 1] : fallback;
};

const BASE = arg('base', 'http://localhost:3000');
const OUT = arg('out', path.resolve('ui'));
const W = Number(arg('width', 1600));
const H = Number(arg('height', 1000));
const SCALE = Number(arg('scale', 2));

mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({
  channel: 'chrome',
  headless: true,
  args: ['--hide-scrollbars', '--autoplay-policy=no-user-gesture-required'],
});
const context = await browser.newContext({
  viewport: { width: W, height: H },
  deviceScaleFactor: SCALE,
});
const page = await context.newPage();

const shots = [];
const shot = async (name, note) => {
  const file = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: file, animations: 'disabled' });
  shots.push({ name, note, file });
  console.log(`  ${name}  ${note}`);
};
const pause = (ms) => page.waitForTimeout(ms);
const click = async (name, timeout = 6000) => {
  try {
    await page.getByRole('button', { name, exact: false }).first().click({ timeout });
    return true;
  } catch {
    console.log(`  (no button "${name}")`);
    return false;
  }
};

await page.goto(BASE, { waitUntil: 'load' });
await page.waitForFunction(
  () => !document.querySelector('.viewport-busy')
    && !!document.querySelector('.stage canvas')
    && !!document.querySelector('.hud-row b')?.textContent?.trim(),
  null, { timeout: 240000 },
).catch(() => console.log('  (the run never reached the stage)'));

// The opening performance narrates itself; a still frame of it is a loading screen.
await click('Skip');
await pause(2500);
await click('Close rationale');
await pause(1200);
await click('Hide the score');
await pause(1200);

await shot('01_stage_blueprint', 'the compiled model on the stage, Blueprint ground');

await click('Studio');
await pause(2600);
await shot('02_stage_studio', 'the same component set on the Studio ground');
await click('Blueprint');
await pause(2200);

await click('Layers');
await pause(900);
await shot('03_layers', 'the semantic layer tree over the model');
await click('Layers');
await pause(500);

await click('Section');
await pause(1400);
await shot('04_section', 'the section plane cutting the model');
await click('Section');
await pause(600);

await page.getByRole('button', { name: 'Reports', exact: false }).first().click();
await pause(700);
await shot('05_reports_menu', 'every report the run produced, grouped');
// Leave the menu closed: the loop below opens it itself, and a second click on
// Reports would only toggle this one shut again and lose the first panel.
await page.keyboard.press('Escape').catch(() => {});
await page.mouse.click(W / 2, H - 40).catch(() => {});
await pause(600);

const PANELS = [
  ['overview', 'Overview', 'what the music became: four decisions and their reasons'],
  ['audio', 'Audio', 'twelve measured features and six temporal segments'],
  ['score', 'Shared score', 'ten dimensions, the datums they set, how far each travelled'],
  ['selection', 'Selection', 'what the score asked for and what the screen allowed'],
  ['drawings', 'Drawings', 'the issued set with each sheet’s own account'],
  ['structure', 'Structure', 'member calculations and their governing check'],
  ['program', 'Program', 'the brief as areas, allocated level by level'],
  ['compliance', 'Compliance', 'checks and clauses, passed / failed / unevaluated'],
  ['derivation', 'Derivation', 'one reasoning chain per element family'],
  ['bim', 'BIM handoff', 'the Revit / Dynamo handoff and what stays pending'],
  ['dependencies', 'Dependencies', 'the support graph: what holds what up'],
  ['site', 'Site', 'the proposed site and the three load cases'],
  ['artifacts', 'Artifacts', 'every file the run produced, with its hash'],
];

let index = 6;
for (const [id, label, note] of PANELS) {
  const opened = await page.getByRole('button', { name: 'Reports', exact: false })
    .first().click().then(() => true).catch(() => false);
  if (!opened) break;
  await pause(400);
  // The drawer's entries are menuitems, not buttons; an exact match keeps
  // "Program" from also selecting nothing when "Programme" style labels appear.
  let hit = true;
  try {
    await page.getByRole('menuitem', { name: label, exact: false }).first()
      .click({ timeout: 5000 });
  } catch {
    console.log(`  (no menuitem "${label}")`);
    hit = false;
  }
  if (!hit) continue;
  await pause(1800);
  await shot(`${String(index).padStart(2, '0')}_panel_${id}`, note);
  index += 1;
}

writeFileSync(path.join(OUT, 'shots_manifest.json'),
  JSON.stringify({ base: BASE, viewport: [W, H], deviceScaleFactor: SCALE, shots }, null, 1),
  'utf-8');
console.log(`\n${shots.length} screenshots -> ${OUT}`);

await context.close();
await browser.close();
