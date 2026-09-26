// The visitor profile's browser holder (D034). Started by runtime/web_visitor.py, never by a model.
//
// Holds one headless Chrome for one session behind four layers that apply to the WHOLE browser, not only to the
// address a visitor names: (1) a local proxy that every request must pass, which lets through only the allowlist's
// host:port and answers everything else with 403 without connecting; (2) host rules that resolve every other name to
// "not found"; (3) request interception on the page, which aborts and logs anything outside the allowlist; (4) popup
// windows and new tabs, closed as they appear. After every action the page's address is checked again.
//
// The visitor never reaches this process over a socket. It writes one request file into the workspace queue, which
// this process reads without following links and checks against the shared grammar (runtime/web/grammar.json);
// the answer is written where the visitor can only read. That works inside Codex's sandbox, which allows no socket
// at all, and behind the Claude guard alike. Every request is traced outside the workspace, refused ones included.
//
// The protection exception arrives in NR_UNDANTAG, is removed from the environment at once, is attached only to
// requests for the start origin during one priming visit, and afterwards travels only as the cookie the protected
// host sets in this run's own profile. It is never written anywhere.
//
// usage: node holder.mjs <config.json>          (SIGTERM stops it, closes Chrome and removes the profile)
import { appendFileSync, closeSync, constants, existsSync, fstatSync, mkdirSync, openSync, readFileSync, readdirSync,
  renameSync, rmSync, writeFileSync } from 'node:fs';
import http from 'node:http';
import net from 'node:net';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { compileGrammar, pageAllowed as pageRule, validateAction } from './grammar.mjs';

const secret = process.env.NR_UNDANTAG || null;
delete process.env.NR_UNDANTAG;
const config = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const grammar = JSON.parse(readFileSync(config.grammar_path, 'utf8'));
const PATTERNS = compileGrammar(grammar);
const puppeteer = (await import(pathToFileURL(join(config.tools_dir, 'puppeteer-core/lib/puppeteer/puppeteer-core.js')).href)).default;

const allowed = config.allowed_origins;
mkdirSync(config.trace_dir, { recursive: true });
for (const dir of [config.answer_dir, config.shots_dir]) mkdirSync(dir, { recursive: true });
const traceFile = join(config.trace_dir, 'trace.jsonl');
const blockedFile = join(config.trace_dir, 'blockerade.jsonl');
const append = (file, entry) => { try { appendFileSync(file, JSON.stringify({ t: new Date().toISOString(), ...entry }) + '\n'); } catch {} };
const counts = { actions: 0, refused: 0, boundary: 0, blocked: 0, proxy_denied: 0, closed_targets: 0, requests: 0 };
const originOf = (url) => { try { return new URL(url).origin; } catch { return null; } };
const inAllowlist = (url) => {
  try { const u = new URL(url); return ['about:', 'data:', 'blob:', 'chrome-error:'].includes(u.protocol) || allowed.includes(u.origin); } catch { return false; }
};

// Layer 1: the proxy.
const hostPorts = new Set(allowed.map((o) => { const u = new URL(o); return `${u.hostname}:${u.port || (u.protocol === 'https:' ? '443' : '80')}`; }));
const proxy = http.createServer((req, res) => {
  let target; try { target = new URL(req.url); } catch { res.writeHead(400); return res.end(); }
  const hp = `${target.hostname}:${target.port || '80'}`;
  if (target.protocol !== 'http:' || !hostPorts.has(hp)) {
    counts.proxy_denied += 1; append(blockedFile, { layer: 'proxy', method: req.method, url: req.url.slice(0, 300) });
    res.writeHead(403, { 'Content-Type': 'text/plain' }); return res.end('utanför provets vitlista');
  }
  const upstream = http.request({ host: target.hostname, port: target.port || 80, method: req.method, path: target.pathname + target.search,
    headers: { ...req.headers, host: target.host } }, (ur) => { res.writeHead(ur.statusCode, ur.headers); ur.pipe(res); });
  upstream.on('error', () => { try { res.writeHead(502); res.end(); } catch {} });
  req.pipe(upstream);
});
proxy.on('connect', (req, socket) => {
  if (!hostPorts.has(req.url)) {
    counts.proxy_denied += 1; append(blockedFile, { layer: 'proxy-connect', url: String(req.url).slice(0, 300) });
    socket.write('HTTP/1.1 403 Forbidden\r\n\r\n'); return socket.destroy();
  }
  const [host, port] = req.url.split(':');
  const upstream = net.connect(Number(port), host, () => { socket.write('HTTP/1.1 200 Connection Established\r\n\r\n'); upstream.pipe(socket); socket.pipe(upstream); });
  upstream.on('error', () => socket.destroy()); socket.on('error', () => upstream.destroy());
});
await new Promise((r) => proxy.listen(0, '127.0.0.1', r));

// Layer 2: host rules.
const hosts = [...new Set(allowed.map((o) => new URL(o).hostname))];
const resolverRules = ['MAP * ~NOTFOUND', ...hosts.map((h) => `EXCLUDE ${h}`)].join(', ');
const env = Object.fromEntries(Object.entries(process.env).filter(([k]) => !/SECRET|TOKEN|KEY|PASSWORD|CREDENTIAL|BYPASS|UNDANTAG/i.test(k)));
const browser = await puppeteer.launch({
  executablePath: config.chrome_path, headless: true, protocolTimeout: 60000, userDataDir: config.profile_dir, defaultViewport: null, env,
  args: ['--no-first-run', '--no-default-browser-check', '--disable-extensions', '--lang=sv-SE',
    `--proxy-server=127.0.0.1:${proxy.address().port}`, '--proxy-bypass-list=<-loopback>', `--host-resolver-rules=${resolverRules}`,
    '--disable-background-networking', '--disable-component-update', '--disable-sync', '--no-pings', '--remote-debugging-port=0'],
});

// Layer 4: popups and new tabs are not part of the scenario.
let mainPage = null;
browser.on('targetcreated', async (target) => {
  if (target.type() !== 'page') return;
  const page = await target.page().catch(() => null);
  if (page && mainPage && page !== mainPage) {
    counts.closed_targets += 1; append(blockedFile, { layer: 'target', url: target.url().slice(0, 300) });
    await page.close().catch(() => {});
  }
});
mainPage = (await browser.pages())[0] || await browser.newPage();
const page = mainPage;

// Layer 3: request interception, which also carries the exception to the start origin during priming only.
let priming = false;
await page.setRequestInterception(true);
page.on('request', (request) => {
  counts.requests += 1;
  const url = request.url();
  if (!inAllowlist(url)) {
    counts.blocked += 1; append(blockedFile, { layer: 'request', url: url.slice(0, 300), type: request.resourceType(), navigation: request.isNavigationRequest() });
    return request.abort('blockedbyclient').catch(() => {});
  }
  if (priming && secret && originOf(url) === originOf(config.start_url)) {
    return request.continue({ headers: { ...request.headers(), [config.secret.header]: secret, ...config.secret.priming } }).catch(() => {});
  }
  return request.continue().catch(() => {});
});
await page.setViewport(config.viewport);
await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);

let primed = null;
if (secret) {
  priming = true;
  const response = await page.goto(config.start_url, { waitUntil: 'networkidle2', timeout: 45000 }).catch(() => null);
  priming = false;
  primed = Boolean(response) && response.status() < 400;
  await page.goto('about:blank').catch(() => {});
}
const start = await page.goto(config.start_url, { waitUntil: 'networkidle2', timeout: 45000 }).catch((e) => ({ error: String(e.message) }));
append(traceFile, { kind: 'start', url: page.url(), status: start && !start.error && start.status ? start.status() : null, primed });

// The grammar, applied here as the authority: the visitor's own command and the Claude guard apply it too, but
// only this process can act on the browser.
const validate = (argv) => validateAction(argv, grammar, PATTERNS);
const pageAllowed = (url) => pageRule(url, allowed, grammar, PATTERNS);

let step = 0;
const label = () => String(++step).padStart(3, '0');

async function elements() {
  return page.evaluate(() => {
    const selector = 'a[href], button, input, select, textarea, summary, [role="button"], [role="link"], [role="checkbox"], [role="radio"], [role="tab"], [role="menuitem"], [tabindex]:not([tabindex="-1"])';
    const seen = new Set(); const els = []; const out = [];
    const name = (el) => {
      const aria = el.getAttribute('aria-label'); if (aria) return aria.trim();
      if (el.labels && el.labels.length) return Array.from(el.labels).map((l) => l.innerText).join(' ').replace(/\s+/g, ' ').trim().slice(0, 80);
      return (el.innerText || el.value || el.getAttribute('placeholder') || el.getAttribute('title') || el.getAttribute('alt') || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    };
    for (const el of document.querySelectorAll(selector)) {
      if (seen.has(el)) continue;
      const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
      if (r.width < 2 || r.height < 2 || s.visibility === 'hidden' || s.display === 'none' || el.disabled || el.type === 'hidden') continue;
      seen.add(el); els.push(el);
      const role = el.getAttribute('role') || ({ A: 'länk', BUTTON: 'knapp', SELECT: 'val', TEXTAREA: 'textfält' })[el.tagName] || (el.tagName === 'INPUT' ? ({ checkbox: 'kryssruta', radio: 'radioknapp', submit: 'knapp' })[el.type] || 'fält' : el.tagName.toLowerCase());
      const state = el.type === 'checkbox' || el.type === 'radio' ? (el.checked ? '[ikryssad]' : '[ej ikryssad]') : el.tagName === 'SELECT' ? `[valt: ${el.options[el.selectedIndex]?.text?.trim() || ''}]` : (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') && el.value ? `[innehåll: ${String(el.value).slice(0, 40)}]` : '';
      out.push({ n: els.length, role, label: name(el), state, inView: r.bottom > 0 && r.top < window.innerHeight });
    }
    window.__nr_elements = els;
    return out;
  });
}

async function observe(kind, note) {
  const n = label();
  const shot = join(config.shots_dir, `${n}-${kind}.png`);
  await page.screenshot({ path: shot, fullPage: false });
  const list = await elements();
  writeFileSync(join(config.shots_dir, `${n}-element.json`), JSON.stringify(list, null, 1));
  const inView = list.filter((e) => e.inView).map((e) => `${e.n}. ${e.role}: ${e.label}${e.state ? ' ' + e.state : ''}`);
  const hidden = list.filter((e) => !e.inView).length;
  const text = [`ADRESS: ${page.url()}`, `TITEL: ${await page.title().catch(() => '')}`, `SKÄRMBILD: spar/${n}-${kind}.png`,
    `HANDLINGAR KVAR: ${Math.max(0, config.max_actions - counts.actions)}`, 'ELEMENT I VY (interaktionsstöd, inte visuell observation):', ...inView,
    hidden ? `(${hidden} element utanför vyn; rulla för att se dem)` : '', note || ''].filter(Boolean).join('\n');
  return { text, shot: `spar/${n}-${kind}.png`, elements: list.length };
}

let finished = false;
let lastUrl = null;
async function perform(verb, args) {
  if (finished) throw new Error('sessionen är avslutad; skriv din slutrapport');
  if (verb === 'done') { finished = true; return { text: 'Sessionen är klar. Skriv nu din slutrapport som ditt sista meddelande: vad du gjorde, vad du såg, om du nådde målet och vad som var oklart.' }; }
  if (counts.actions >= config.max_actions) throw new Error(`handlingstaket ${config.max_actions} är nått; avsluta med done`);
  let note = '';
  if (verb === 'open') {
    if (!pageAllowed(args[0])) throw new Error('adressen är inte en sida inom provets vitlista');
    const response = await page.goto(args[0], { waitUntil: 'networkidle2', timeout: 30000 }).catch((e) => ({ error: String(e.message) }));
    const type = response && !response.error && typeof response.headers === 'function' ? String(response.headers()['content-type'] || '') : '';
    if (type && !/text\/html/.test(type)) { counts.boundary += 1; append(traceFile, { kind: 'boundary', verb, reason: 'inte en HTML-sida' }); await page.goto('about:blank').catch(() => {}); note = 'ÖPPNING: adressen gav inte en HTML-sida; den visas inte'; }
    else note = response && response.error ? `LADDNING: fel (${response.error.slice(0, 120)})` : `LADDNING: status ${response?.status?.() ?? '?'}`;
  } else if (verb === 'click' || verb === 'type' || verb === 'select') {
    const count = await page.evaluate(() => (window.__nr_elements || []).length);
    const n = Number(args[0]);
    if (!(n >= 1 && n <= count)) throw new Error(`ange ett elementnummer 1–${count} från senaste look`);
    const box = await page.evaluate((i) => { const el = window.__nr_elements[i - 1]; if (!el) return null; el.scrollIntoView({ block: 'center', inline: 'nearest' }); const r = el.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, tag: el.tagName }; }, n);
    if (!box) throw new Error('elementet finns inte längre; gör look igen');
    await page.mouse.click(box.x, box.y);
    if (verb === 'click') { await page.waitForNetworkIdle({ idleTime: 400, timeout: 8000 }).catch(() => {}); note = `KLICK på element ${n}`; }
    else if (verb === 'type') {
      if (box.tag === 'INPUT' || box.tag === 'TEXTAREA') { await page.evaluate((i) => { const el = window.__nr_elements[i - 1]; if (el && typeof el.select === 'function') el.select(); }, n); await page.keyboard.press('Backspace'); }
      await page.keyboard.type(args[1], { delay: 15 }); note = `SKREV i element ${n} (${args[1].length} tecken)`;
    } else {
      // A visitor picks the option by its visible text. No Enter: in a form, Enter on a list submits the form.
      const chosen = await page.evaluate((i, wanted) => {
        const el = window.__nr_elements[i - 1];
        if (!el || el.tagName !== 'SELECT') return { kind: 'other' };
        const want = wanted.toLowerCase();
        const options = Array.from(el.options);
        const option = options.find((o) => o.text.trim().toLowerCase() === want) || options.find((o) => o.text.trim().toLowerCase().startsWith(want));
        if (!option) return { kind: 'none' };
        el.value = option.value;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return { kind: 'select', text: option.text.trim() };
      }, n, args[1]);
      if (chosen.kind === 'none') throw new Error('hittar inget alternativ som börjar med den texten');
      if (chosen.kind === 'other') await page.keyboard.type(args[1], { delay: 40 });
      note = chosen.kind === 'select' ? `VALDE "${chosen.text.slice(0, 40)}" i element ${n}` : `SKREV i element ${n} för att välja`;
    }
  } else if (verb === 'scroll') {
    await page.evaluate((d) => window.scrollBy({ top: d * window.innerHeight * 0.85, behavior: 'instant' }), args[0] === 'up' ? -1 : 1);
    await new Promise((r) => setTimeout(r, 250)); note = `RULLADE ${args[0]}`;
  } else if (verb === 'back') {
    await page.goBack({ waitUntil: 'networkidle2', timeout: 15000 }).catch(() => {}); note = 'GICK TILLBAKA';
  } else if (verb === 'read') {
    counts.actions += 1;
    const text = await page.evaluate(() => document.body ? document.body.innerText : '');
    const n = label();
    writeFileSync(join(config.shots_dir, `${n}-text.txt`), text);
    return { text: `ADRESS: ${page.url()}\nHANDLINGAR KVAR: ${Math.max(0, config.max_actions - counts.actions)}\nSIDTEXT (${text.length} tecken, även i spar/${n}-text.txt):\n${text.slice(0, 6000)}` };
  }
  counts.actions += 1;
  const after = page.url();
  if (after && after !== 'about:blank' && !inAllowlist(after) && !after.startsWith('chrome-error://')) {
    counts.boundary += 1; append(traceFile, { kind: 'boundary', verb, url: after.slice(0, 200), reason: 'sidan lämnade vitlistan' });
    await page.goBack({ timeout: 10000 }).catch(() => {});
    note += ' | GRÄNS: adressen låg utanför provets vitlista; sidan återställdes';
  }
  return observe(verb, note);
}

function writeAnswer(id, answer) {
  const tmp = join(config.answer_dir, `.${id}.tmp`);
  writeFileSync(tmp, JSON.stringify(answer));
  renameSync(tmp, join(config.answer_dir, `${id}.json`));
}

const processed = new Set();
let handled = 0;
let busy = false;
async function poll() {
  if (busy) return; busy = true;
  try {
    const names = existsSync(config.queue_dir) ? readdirSync(config.queue_dir).filter((n) => /^[0-9a-f]{16}\.json$/.test(n) && !processed.has(n)).sort() : [];
    for (const name of names) {
      processed.add(name);
      const id = name.slice(0, 16);
      let argv = null; let raw = null;
      try {
        const fd = openSync(join(config.queue_dir, name), constants.O_RDONLY | constants.O_NOFOLLOW);
        try { const st = fstatSync(fd); if (!st.isFile() || st.size > 4096) throw new Error('ogiltig begäran'); raw = readFileSync(fd, 'utf8'); } finally { closeSync(fd); }
        const request = JSON.parse(raw);
        if (request.id !== id || !Array.isArray(request.argv)) throw new Error('ogiltig begäran');
        argv = request.argv;
      } catch (e) {
        counts.refused += 1; append(traceFile, { kind: 'refused', id, reason: 'ogiltig begäran' }); writeAnswer(id, { id, code: 2, text: 'FEL: ogiltig begäran' }); continue;
      }
      handled += 1;
      if (handled > config.max_actions * 4) { counts.refused += 1; append(traceFile, { kind: 'refused', id, reason: 'för många anrop' }); writeAnswer(id, { id, code: 2, text: 'FEL: för många anrop' }); continue; }
      let verb; let args;
      try { [verb, args] = validate(argv); } catch (e) {
        counts.refused += 1; append(traceFile, { kind: 'refused', id, verb: String(argv[0]).slice(0, 20), args: argv.length - 1, reason: e.message });
        writeAnswer(id, { id, code: 2, text: `FEL: ${e.message}` }); continue;
      }
      try {
        const result = await perform(verb, args);
        const shown = verb === 'type' || verb === 'select' ? [args[0], `${args[1].length} tecken`] : args;
        lastUrl = page.url();
        append(traceFile, { kind: verb === 'done' ? 'done' : 'action', id, verb, args: shown, url: lastUrl, shot: result.shot || null, elements: result.elements ?? null });
        writeAnswer(id, { id, code: 0, text: result.text });
      } catch (e) {
        counts.refused += 1; append(traceFile, { kind: 'refused', id, verb, reason: e.message });
        writeAnswer(id, { id, code: 2, text: `FEL: ${e.message}` });
      }
    }
  } finally { busy = false; }
}

writeFileSync(config.ready_file, JSON.stringify({ ready: true, primed, start: page.url(), proxy: `127.0.0.1:${proxy.address().port}`, resolver_rules: resolverRules }) + '\n');
const timer = setInterval(() => { poll().catch((e) => append(traceFile, { kind: 'holder-error', reason: String(e.message).slice(0, 200) })); }, 100);

async function shutdown() {
  clearInterval(timer);
  while (busy) await new Promise((r) => setTimeout(r, 50));
  try { await browser.close(); } catch {}
  rmSync(config.profile_dir, { recursive: true, force: true });
  try { proxy.close(); } catch {}
  writeFileSync(config.stop_file, JSON.stringify({ stopped: true, ...counts, done: finished, final_url: lastUrl }) + '\n');
  process.stdout.write(`STOPPED ${JSON.stringify(counts)}\n`);
  process.exit(0);
}
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
