// The measurement profile's browser half (D034). Started by runtime/web_measure.py, never by a model.
//
// Renders one page in the two fixed views, takes the first view, section images and the whole page, measures the
// heading lines and the named action in view, runs axe and Lighthouse, and writes a self-contained snapshot per view
// (the rendered DOM without scripts, every stylesheet inlined as read through the browser's own CSS channel) for the
// detector, which the host runs separately without network. No clicks, no forms, no consent: only scrolling.
//
// The protection exception, when used, arrives in the environment variable NR_UNDANTAG, is removed from the
// environment at once, is attached only to requests for the target origin while priming, and afterwards travels only
// as the cookie the protected host sets in this run's own temporary profile. It is never written anywhere.
//
// usage: node measure.mjs <config.json>
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const secret = process.env.NR_UNDANTAG || null;
delete process.env.NR_UNDANTAG;

const config = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const TOOLS = config.tools_dir;
const importTool = async (rel) => (await import(pathToFileURL(join(TOOLS, rel)).href)).default;
const puppeteer = await importTool('puppeteer-core/lib/puppeteer/puppeteer-core.js');

const out = config.out_dir;
for (const sub of ['skarm', 'matning', 'axe', 'lighthouse', 'ogonblick']) mkdirSync(join(out, sub), { recursive: true });
const result = { parts: {}, views: {}, primed: null, started_at: new Date().toISOString() };
const wants = new Set(config.parts);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const originOf = (url) => { try { return new URL(url).origin; } catch { return null; } };

const env = Object.fromEntries(Object.entries(process.env).filter(([k]) => !/SECRET|TOKEN|KEY|PASSWORD|CREDENTIAL|BYPASS|UNDANTAG/i.test(k)));
const browser = await puppeteer.launch({
  executablePath: config.chrome_path,
  headless: true,
  userDataDir: config.profile_dir,
  defaultViewport: null,
  protocolTimeout: 120000,
  env,
  args: ['--no-first-run', '--no-default-browser-check', '--disable-extensions', '--hide-scrollbars', '--lang=sv-SE',
    '--disable-background-networking', '--disable-component-update', '--disable-sync', '--no-pings',
    '--remote-debugging-port=0'],
});
// Registered after the launch, so it runs after puppeteer's own exit hook has ended Chrome: however this process ends,
// the profile, which may hold a protected host's cookie, goes with it (D036).
process.on('exit', () => { try { rmSync(config.profile_dir, { recursive: true, force: true }); } catch {} });
// Should the command that started this measurement die without ending it (SIGKILL), end with it: close Chrome and
// exit (D035). Unreferenced, so it never keeps a finished measurement alive.
let orphaned = false;
setInterval(() => {
  if (orphaned || process.ppid !== 1) return;
  orphaned = true;
  Promise.race([browser.close().catch(() => {}), wait(5000)]).finally(() => process.exit(3));
}, 1000).unref();

async function prime() {
  const page = await browser.newPage();
  await page.setRequestInterception(true);
  page.on('request', (request) => {
    if (originOf(request.url()) === config.target_origin) {
      request.continue({ headers: { ...request.headers(), [config.secret.header]: secret, ...config.secret.priming } }).catch(() => {});
    } else {
      request.continue().catch(() => {});
    }
  });
  const response = await page.goto(config.target_url, { waitUntil: 'load', timeout: 45000 }).catch(() => null);
  const status = response ? response.status() : null;
  await page.close();
  return { status, ok: status !== null && status < 400 };
}

async function settle(page) {
  await page.waitForNetworkIdle({ idleTime: 500, timeout: 30000 }).catch(() => {});
  await page.evaluate(() => document.fonts && document.fonts.ready).catch(() => {});
  await wait(250);
}

// Heading lines are counted from the rendered line boxes of the heading's text, not from height divided by
// line-height, which misreads headings with padding or mixed sizes.
function measurePage(actionText, actionSelector) {
  const firstViewHeight = window.innerHeight;
  const box = (el) => { const r = el.getBoundingClientRect(); return { top: Math.round(r.top + window.scrollY), bottom: Math.round(r.bottom + window.scrollY), left: Math.round(r.left), right: Math.round(r.right) }; };
  const visible = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const textOf = (el) => (el.getAttribute('aria-label') || el.innerText || el.value || el.getAttribute('title') || '').replace(/\s+/g, ' ').trim();
  const lines = (el) => {
    const range = document.createRange(); range.selectNodeContents(el);
    const tops = new Set(); for (const r of range.getClientRects()) if (r.width > 0 && r.height > 0) tops.add(Math.round(r.top));
    const merged = [...tops].sort((a, b) => a - b).filter((t, i, a) => i === 0 || t - a[i - 1] > 2);
    return merged.length;
  };
  const inFirstView = (b) => b.top >= 0 && b.bottom <= firstViewHeight;
  const headings = [...document.querySelectorAll('h1')].filter(visible).map((el) => {
    const s = getComputedStyle(el); const b = box(el);
    return { text: textOf(el).slice(0, 120), lines: lines(el), font_family: s.fontFamily.slice(0, 80), font_size_px: parseFloat(s.fontSize), line_height: s.lineHeight, box: b, in_first_view: inFirstView(b) };
  });
  const interactiveSelector = 'a[href], button, [role="button"], input[type="submit"], input[type="button"], select, textarea, input:not([type="hidden"])';
  const interactive = [...document.querySelectorAll(interactiveSelector)].filter(visible);
  let action = { given: { text: actionText, selector: actionSelector }, found: false, match: null };
  let target = null; let match = null;
  if (actionSelector) { try { target = document.querySelector(actionSelector); match = target ? 'selektor' : null; } catch { action.selector_error = true; } }
  if (!target && actionText) {
    const want = actionText.replace(/\s+/g, ' ').trim().toLowerCase();
    target = interactive.find((el) => textOf(el).toLowerCase() === want) || null; match = target ? 'exakt' : null;
    if (!target) { target = interactive.find((el) => textOf(el).toLowerCase().includes(want)) || null; match = target ? 'innehaller' : null; }
  }
  if (target) { const b = box(target); action = { ...action, found: true, match, text: textOf(target).slice(0, 80), box: b, fully_in_first_view: inFirstView(b) }; }
  const firstView = interactive.map((el) => ({ el, b: box(el) })).filter(({ b }) => b.bottom > 0 && b.top < firstViewHeight).slice(0, 40)
    .map(({ el, b }) => ({ tag: el.tagName.toLowerCase(), role: el.getAttribute('role'), text: textOf(el).slice(0, 80), box: b, fully_in_first_view: inFirstView(b) }));
  const fonts = [...new Set([...document.querySelectorAll('h1,h2,h3,h4,p,a,button,li')].map((el) => getComputedStyle(el).fontFamily.split(',')[0].replace(/["']/g, '').trim()))].slice(0, 12);
  return { title: document.title, document_height: document.documentElement.scrollHeight, viewport: { width: window.innerWidth, height: firstViewHeight }, h1: headings, action, interactive_in_first_view: firstView, fonts };
}

async function snapshot(page) {
  const session = await page.createCDPSession();
  const sheets = [];
  session.on('CSS.styleSheetAdded', (event) => sheets.push(event.header));
  await session.send('DOM.enable');
  await session.send('CSS.enable');
  await wait(200);
  const texts = [];
  for (const header of sheets) {
    if (header.origin !== 'regular') continue;
    const { text } = await session.send('CSS.getStyleSheetText', { styleSheetId: header.styleSheetId }).catch(() => ({ text: null }));
    if (typeof text === 'string') texts.push({ source: String(header.sourceURL || (header.isInline ? 'inline' : '')).slice(0, 200), text });
  }
  await session.detach().catch(() => {});
  const html = await page.evaluate((collected) => {
    const clone = document.documentElement.cloneNode(true);
    clone.querySelectorAll('script, noscript, link[rel~="stylesheet"], style, link[rel="preload"], link[rel="modulepreload"]').forEach((el) => el.remove());
    const head = clone.querySelector('head') || clone.insertBefore(document.createElement('head'), clone.firstChild);
    for (const sheet of collected) {
      const style = document.createElement('style');
      style.setAttribute('data-nr-kalla', sheet.source);
      style.textContent = sheet.text;
      head.appendChild(style);
    }
    return '<!doctype html>\n' + clone.outerHTML;
  }, texts);
  return { html, sheets: texts.length };
}

async function axeRun(page) {
  const source = readFileSync(join(TOOLS, 'axe-core/axe.min.js'), 'utf8');
  await page.evaluate(source);
  return page.evaluate(async (tags) => {
    const r = await window.axe.run(document, { runOnly: { type: 'tag', values: tags }, resultTypes: ['violations', 'incomplete'] });
    const slim = (list) => list.map((v) => ({ id: v.id, impact: v.impact, help: v.help, tags: v.tags, nodes: v.nodes.slice(0, 20).map((n) => ({ target: n.target, summary: n.failureSummary })) }));
    return { axe_version: window.axe.version, violations: slim(r.violations), incomplete: slim(r.incomplete), passes: r.passes.length };
  }, config.axe_tags);
}

async function view(name, spec) {
  const record = { status: null, final_url: null, errors: [] };
  const page = await browser.newPage();
  try {
    await page.setViewport(spec);
    await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);
    const response = await page.goto(config.target_url, { waitUntil: 'load', timeout: 45000 }).catch((e) => { record.errors.push('laddning: ' + String(e.message).slice(0, 160)); return null; });
    record.status = response ? response.status() : null;
    await settle(page);
    record.final_url = page.url();
    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    await page.evaluate(() => window.scrollTo(0, 0)); await wait(200);
    await page.screenshot({ path: join(out, 'skarm', `${name}-forsta-vyn.png`), fullPage: false });
    // A section exists only where the page extends below it; a shorter page would repeat the first view.
    record.sections_taken = 0;
    for (let k = 1; k <= config.sections; k += 1) {
      if (k * spec.height >= height) break;
      await page.evaluate((y) => window.scrollTo(0, y), k * spec.height); await wait(400);
      await page.screenshot({ path: join(out, 'skarm', `${name}-sektion-${k}.png`), fullPage: false });
      record.sections_taken = k;
    }
    record.sections_requested = config.sections;
    await page.evaluate(() => window.scrollTo(0, 0)); await wait(300);
    record.full_page_truncated = height > config.full_page_max;
    if (record.full_page_truncated) {
      await page.screenshot({ path: join(out, 'skarm', `${name}-hela.png`), clip: { x: 0, y: 0, width: spec.width, height: config.full_page_max }, captureBeyondViewport: true });
    } else {
      await page.screenshot({ path: join(out, 'skarm', `${name}-hela.png`), fullPage: true });
    }
    await page.evaluate(() => window.scrollTo(0, 0)); await wait(200);
    if (wants.has('rubrik')) {
      const measured = await page.evaluate(measurePage, config.action_text, config.action_selector);
      writeFileSync(join(out, 'matning', `${name}.json`), JSON.stringify({ address: config.target_url, final_url: record.final_url, status: record.status, ...measured }, null, 1) + '\n');
    }
    if (wants.has('axe')) {
      try { writeFileSync(join(out, 'axe', `${name}.json`), JSON.stringify(await axeRun(page), null, 1) + '\n'); } catch (e) { record.errors.push('axe: ' + String(e.message).slice(0, 160)); }
    }
    if (wants.has('detektor')) {
      try { const snap = await snapshot(page); writeFileSync(join(out, 'ogonblick', `${name}.html`), snap.html); record.snapshot_sheets = snap.sheets; } catch (e) { record.errors.push('ogonblick: ' + String(e.message).slice(0, 160)); }
    }
  } finally {
    await page.close().catch(() => {});
  }
  return record;
}

async function lighthouseRun() {
  const lighthouse = await importTool('lighthouse/core/index.js');
  const desktopConfig = await importTool('lighthouse/core/config/desktop-config.js');
  const port = Number(new URL(browser.wsEndpoint()).port);
  const runs = {};
  for (const form of ['mobil', 'desktop']) {
    try {
      const flags = { port, output: 'json', logLevel: 'error', disableStorageReset: Boolean(secret) };
      const runner = await lighthouse(config.target_url, flags, form === 'desktop' ? desktopConfig : undefined);
      writeFileSync(join(out, 'lighthouse', `${form}.json`), runner.report);
      const lhr = runner.lhr;
      runs[form] = { lighthouse_version: lhr.lighthouseVersion, final_url: lhr.finalDisplayedUrl, runtime_error: lhr.runtimeError ? lhr.runtimeError.code : null,
        scores: Object.fromEntries(Object.entries(lhr.categories).map(([k, v]) => [k, v.score === null ? null : Math.round(v.score * 100)])),
        lcp_ms: Math.round(lhr.audits['largest-contentful-paint']?.numericValue ?? -1), cls: lhr.audits['cumulative-layout-shift']?.numericValue ?? null,
        tbt_ms: Math.round(lhr.audits['total-blocking-time']?.numericValue ?? -1), warnings: lhr.runWarnings };
    } catch (e) { runs[form] = { error: String(e.message).slice(0, 200) }; }
  }
  return runs;
}

try {
  if (secret) { result.primed = await prime(); }
  if (secret && !result.primed.ok) {
    result.fatal = 'undantaget kunde inte förberedas (status ' + result.primed.status + ')';
  } else {
    for (const [name, spec] of Object.entries(config.viewports)) result.views[name] = await view(name, spec);
    if (wants.has('lighthouse')) result.lighthouse = await lighthouseRun();
  }
} catch (e) {
  result.fatal = String(e && e.message ? e.message : e).slice(0, 300);
} finally {
  await browser.close().catch(() => {});
  rmSync(config.profile_dir, { recursive: true, force: true });
  result.finished_at = new Date().toISOString();
  writeFileSync(join(out, 'matning-resultat.json'), JSON.stringify(result, null, 1) + '\n');
}
process.exit(result.fatal ? 2 : 0);
