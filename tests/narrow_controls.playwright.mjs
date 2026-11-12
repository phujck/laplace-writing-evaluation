// Narrow controls, composed (M5 D; Root actuals C10/C11 Document setup at 720x800 and the C12 Conversation cue).
// The real shell page head (pipeline.html stylesheets), the real workspace shell markup (workspace.mjs) and the real
// conversation pane markup (workspace-session.mjs) are composed in Chromium; the real manuscript editor controller
// and the real task cue are mounted on them. Only the owner reads are stubbed. Geometry is measured at
// 1280/1000/720/390 wide. Nothing is clicked for the person except the disclosure under test; nothing is sent.
// Run: node tests/narrow_controls.playwright.mjs
import {createRequire} from 'module';
import {execSync} from 'child_process';
import {existsSync, readFileSync} from 'fs';
import http from 'http';
import path from 'path';
import {fileURLToPath} from 'url';

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const roots = [
  (() => {try {return execSync('npm root -g', {stdio: ['ignore', 'pipe', 'ignore']}).toString().trim() + '/playwright';} catch {return '';}})(),
  `${ROOT}/node_modules/playwright`, `${ROOT}/node_modules/playwright-core`,
  '/home/phujck/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core',
  '/usr/lib/chatgpt/resources/cua_node/lib/node_modules/playwright-core',
].filter(Boolean);
const pwRoot = roots.find(existsSync);
if (!pwRoot) throw new Error(`Playwright is absent; searched ${roots.join(', ')}`);
const {chromium} = require(pwRoot);
const chrome = execSync("find /opt/pw-browsers \"$HOME/.cache/ms-playwright\" -type f -path '*/chrome-linux*/chrome' -print -quit 2>/dev/null || true").toString().trim();

let passed = 0;
function ok(condition, message) {
  if (!condition) throw new Error('ASSERT FAILED: ' + message);
  passed += 1;
  console.log('  ok -', message);
}

const head = readFileSync(`${ROOT}/src/laplace/web/pipeline.html`, 'utf8').match(/<head>([\s\S]*?)<\/head>/)[1];
const shell = readFileSync(`${ROOT}/src/laplace/web/static_shared/workspace.mjs`, 'utf8').match(/root\.className='workspace';root\.innerHTML=`([^`]*)`/)[1];
const page = `<!doctype html><html><head>${head}</head><body><div class="workspace" id="root">${shell}</div><script type="module" src="/harness.mjs"></script></body></html>`;

// the Document setup: the real editor controller over a stubbed current-document owner read
const SETUP = `import {createManuscriptEditor} from '/shared/manuscript-editor.mjs';
try{
 const main=document.querySelector('[data-main]'),host=document.createElement('div'),frame=document.createElement('iframe');host.style.height='100%';host.append(frame);main.append(host);
 const long='chapters/an-exceptionally-long-exact-source-file-name-without-any-break-for-the-narrow-layout-check.tex';
 const doc={schema_version:'laplace.current-document/1',selection_identity:'sha256:'+'b'.repeat(64),selected_source:{root:'main.tex'},files:[{file:'main.tex'},{file:long}],
  source_observation:{file_revisions:{'main.tex':'sha256:'+'a'.repeat(64)}},status:'CURRENT',current_build:{},template:{available:true,class_name:'article'}};
 const editor=createManuscriptEditor(host,{project:'fixture',frame,request:async p=>{if(p.startsWith('/authoring/document'))return structuredClone(doc);throw Error('unexpected owner read '+p);},storage:sessionStorage});
 await editor.observe?.();window.__editor=editor;window.__ready=true;
}catch(e){window.__error=e.message+'\\n'+e.stack}`;

// the Conversation cue: the real pane markup and the real task cue at the declared step 2 (conversation:context)
const CUE = `import {mountGuide} from '/shared/workspace-guide.mjs';
try{
 const source=await (await fetch('/shared/workspace-session.mjs')).text();
 const root=document.getElementById('root');root.classList.add('session-open');
 const pane=document.querySelector('[data-session]');pane.hidden=false;pane.classList.add('workspace-session');pane.innerHTML=source.match(/host\\.innerHTML=\`([\\s\\S]*?)\`;/)[1];
 const send=pane.querySelector('[data-send]');send.disabled=false;send.textContent='Send';
 window.__sent=0;pane.querySelector('form').addEventListener('submit',event=>{event.preventDefault();window.__sent++;});
 pane.querySelector('[data-message]').value='Root-owned 27 char draft..';
 const steps=[{id:'open',title:'Open the conversation',control:'conversation:toggle',say:'Use Conversation in the top bar. The composer names its target above the message box.'},
  {id:'context',title:'Inspect the context',control:'conversation:context',say:'Open Context. The target chip says what the next message is attached to; Next message shows provider, model and effort.'}];
 window.__guide=mountGuide(root,{project:'fixture',steps,journeyId:'what-a-message-carries',store:{journey:()=>({step:1,closed:false}),update(){}},page:document});
 window.__ready=true;
}catch(e){window.__error=e.message+'\\n'+e.stack}`;

const types = {'.mjs': 'text/javascript', '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml'};
let harness = SETUP;
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://local');
  if (url.pathname === '/harness.html') {res.writeHead(200, {'content-type': 'text/html'});return res.end(page);}
  if (url.pathname === '/harness.mjs') {res.writeHead(200, {'content-type': 'text/javascript'});return res.end(harness);}
  if (url.pathname.startsWith('/shared/')) {
    const file = path.join(ROOT, 'src/laplace/web/static_shared', path.normalize(url.pathname.slice(8)));
    if (file.startsWith(path.join(ROOT, 'src/laplace/web/static_shared')) && existsSync(file)) {res.writeHead(200, {'content-type': types[path.extname(file)] || 'application/octet-stream'});return res.end(readFileSync(file));}
  }
  res.writeHead(404);res.end('{}');
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch(chrome ? {executablePath: chrome} : {});
const rect = (page, selector) => page.evaluate(s => {const n = document.querySelector(s);if (!n || n.hidden) return null;const b = n.getBoundingClientRect();return {left: b.left, right: b.right, top: b.top, bottom: b.bottom, width: b.width, height: b.height};}, selector);
const hit = (a, b) => !!(a && b && a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top);
async function open(width, height, code, extraStyle = '') {
  harness = code;
  const context = await browser.newContext({viewport: {width, height}});const page = await context.newPage();const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(base + '/harness.html');
  if (extraStyle) await page.addStyleTag({content: extraStyle});
  await page.waitForFunction(() => window.__ready || window.__error, null, {timeout: 15000});
  const failure = await page.evaluate(() => window.__error || null);
  if (failure) throw new Error('harness failed: ' + failure);
  return {page, context, errors};
}

try {
  console.log('Document setup popover');
  for (const [width, edge] of [[1280, false], [1000, false], [720, false], [390, false], [720, true], [390, true]]) {
    const label = `${width}px${edge ? ' with the summary at the left edge' : ''}`;
    const {page, context, errors} = await open(width, 800, SETUP, edge ? '.workspace .manuscript-document-setup{margin:0!important}' : '');
    // the edge anchor sits under the narrow navigation drawer's place; the person's closed-drawer state is the shell's own class
    if (edge) await page.evaluate(() => document.getElementById('root').classList.add('nav-closed'));
    const storage = await page.evaluate(() => JSON.stringify(sessionStorage));
    const summary = 'details[data-control="manuscript:document-setup"] > summary';
    await page.locator(summary).click();await page.waitForTimeout(100);
    const panel = await rect(page, '.manuscript-document-setup-panel'), template = await rect(page, '[data-control="manuscript:template-layout"]');
    const main = await page.evaluate(() => {const m = document.querySelector('[data-main]'), b = m.getBoundingClientRect();return {left: b.left, right: b.left + m.clientWidth, client: m.clientWidth, scroll: m.scrollWidth};});
    const doc = await page.evaluate(() => document.documentElement.scrollWidth);
    ok(panel && panel.left >= main.left && panel.right <= main.right && panel.right <= width, `${label}: the panel ${Math.round(panel?.left)}..${Math.round(panel?.right)} is inside main ${Math.round(main.left)}..${Math.round(main.right)}`);
    ok(template && template.left >= panel.left && template.right <= panel.right && template.right <= width, `${label}: Template & layout ${Math.round(template?.left)}..${Math.round(template?.right)} is reachable inside the panel`);
    ok(main.scroll <= main.client && doc <= width, `${label}: no horizontal scroll (main ${main.scroll}/${main.client}, document ${doc}/${width})`);
    ok(await page.evaluate(() => {const p = document.querySelector('.manuscript-document-setup-panel');return p.scrollWidth <= p.clientWidth;}), `${label}: the long exact-source label wraps inside the panel`);
    ok(panel.width >= Math.min(520, main.client - 16) - 1, `${label}: the panel keeps its useful width (${Math.round(panel.width)} px)`);
    ok(await page.evaluate(s => document.activeElement === document.querySelector(s), summary), `${label}: focus stays on the Document setup summary`);
    await page.locator(summary).click();
    ok(await page.evaluate(() => JSON.stringify(sessionStorage)) === storage, `${label}: opening and closing setup leaves retained drafts untouched`);
    ok(!errors.length, `${label}: no page errors`);
    await context.close();
  }

  console.log('Conversation task cue');
  for (const width of [1280, 1000, 720, 390]) {
    const {page, context, errors} = await open(width, 800, CUE);
    await page.waitForTimeout(150);
    const focused = await page.evaluate(() => {document.querySelector('[data-message]').focus();return document.activeElement?.id;});
    for (const phase of ['inspector open', 'inspector closed']) {
      await page.evaluate(hidden => {document.querySelector('[data-inspector]').hidden = hidden;window.__guide.place();}, phase === 'inspector closed');
      await page.waitForTimeout(80);
      const cue = await rect(page, '.workspace-guide'), disposition = await page.evaluate(() => document.querySelector('.workspace-guide')?.dataset.disposition);
      ok(cue && cue.width >= 240 && cue.left >= 0 && cue.right <= width && cue.top >= 0 && cue.bottom <= 800, `${width}px, ${phase}: the cue is readable and inside the viewport (${Math.round(cue?.width)} x ${Math.round(cue?.height)}, ${disposition})`);
      for (const [name, selector] of [['Send', '[data-send]'], ['the message', '[data-message]'], ['the step target', '[data-control="conversation:context"]'], ['the composer target', '[data-composer-target]'], ['Expand', '[data-compose-expand]'], ['the inspector Close', '[data-inspector-close]']]) {
        const kept = await rect(page, selector);
        if (kept && kept.width > 0) ok(!hit(cue, kept), `${width}px, ${phase}: the cue leaves ${name} clear`);
      }
      ok(await page.evaluate(() => document.documentElement.scrollWidth) <= width, `${width}px, ${phase}: no horizontal scroll`);
    }
    ok(await page.evaluate(() => document.querySelector('[data-message]').value) === 'Root-owned 27 char draft..', `${width}px: the draft is retained`);
    ok(await page.evaluate(() => document.activeElement?.id) === focused, `${width}px: placement never moves focus`);
    ok(await page.evaluate(() => window.__sent) === 0, `${width}px: nothing was sent`);
    ok(!errors.length, `${width}px: no page errors`);
    await context.close();
  }

  console.log('Conversation cue without room');
  // each finite disposition at a real height: a height-capped band, the one-line compact cue, then withheld
  for (const [height, expected] of [[230, 'band'], [100, 'compact'], [50, 'withheld']]) {
    const {page, context} = await open(720, height, CUE);
    await page.waitForTimeout(150);await page.evaluate(() => window.__guide.place());
    const disposition = await page.evaluate(() => document.querySelector('.workspace-guide')?.dataset.disposition);
    const cue = await rect(page, '.workspace-guide');
    ok(disposition === expected, `720 x ${height}: the cue takes the ${expected} fallback (${disposition})`);
    if (expected === 'withheld') ok(cue === null, `720 x ${height}: a withheld cue is not shown`);
    else ok(cue.width >= 240 && cue.bottom <= height && cue.right <= 720, `720 x ${height}: the ${expected} cue stays readable and inside the viewport`);
    for (const selector of ['[data-send]', '[data-message]', '[data-control="conversation:context"]']) {const kept = await rect(page, selector);if (kept && kept.width > 0) ok(!hit(cue, kept), `720 x ${height}: the ${expected} cue leaves ${selector} clear`);}
    await page.keyboard.press('Escape');
    ok(await page.evaluate(() => window.__guide.alive === false && !document.querySelector('.workspace-guide')), `720 x ${height}: Escape stops the ${expected} cue`);
    await context.close();
  }
  console.log(`\n${passed} assertions passed`);
} finally {
  await browser.close();
  server.close();
}
