// WALK MEDIA (S2 F4). Purpose: the canvas's lazily loaded resources: KaTeX and pdf.js (each loaded
// once), math hydration on visibility, and figure pages drawn through the owner's figure route.
// Owns: K, the math observer/frame/generation and pending set, FIGS with their render/loading tasks,
// the figure observer. Public contract: ensureKatex/ensurePdfjs, mathNode, appendEquation, drawFigure,
// repaintFigures, releaseMediaForRender. Lifetime: releaseMediaForRender (called by renderDoc) ends
// the old generation, disconnects observers and releases every figure task, so a late resolution
// cannot paint into a replaced canvas.
import {compiledPreviewWidth, dominantPreviewFont, pdfFigureRoute} from "/shared/manuscript-editing.mjs";
import {KATEX_CSS, KATEX_JS, PDFJS_SRC, WORKER_SRC, clamp, el, paper} from './walk-base.mjs';
import {D, blockById} from './walk-document.mjs';
import {measurePx, scheduleRemeasure} from './walk-position.mjs';
import {refreshPieceMap} from './walk-pieces.mjs';
import {asChrome} from './walk-blocks.mjs';
import {P} from './walk-drafts.mjs';
import {sealIslands, setEditable} from './walk-editing.mjs';
import {blockLabels} from './walk-where.mjs';

// ═════════════════════════════════════════════════════════════════════════════════════════
// 2 · the vendored libraries, loaded lazily and once
// ═════════════════════════════════════════════════════════════════════════════════════════

const K = { katex: null, tried: false, note: "" };

/** KaTeX is a classic script (window.katex) plus its own stylesheet — the vendored pair
 *  under /shared/katex/. Loaded ONCE, before the first block renders, so no equation has
 *  to be repainted under him. A failure is stated, never thrown: every equation then
 *  shows as its own source, marked. */
let katexPending = null;
function ensureKatex() {
  if (katexPending) return katexPending;
  K.tried = true;
  katexPending = new Promise((resolve) => {
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = KATEX_CSS;
    document.head.appendChild(css);
    const s = document.createElement("script");
    s.src = KATEX_JS;
    s.addEventListener("load", () => {
      K.katex = window.katex || null;
      if (!K.katex) K.note = "the vendored KaTeX loaded but exposed no renderer, so every "
                           + "equation shows as its own source, marked.";
      resolve(K.katex);
    });
    s.addEventListener("error", () => {
      K.note = "the vendored KaTeX at " + KATEX_JS + " did not load, so every equation "
             + "shows as its own source, marked.";
      resolve(null);
    });
    document.head.appendChild(s);
  });
  return katexPending;
}

let pdfjs = null;

/** pdf.js is imported ONLY for the two things that still need a pdf: the geometry face
 *  behind the head door, and figure blocks whose served route is a pdf. It is never the
 *  working canvas. */
async function ensurePdfjs() {
  if (pdfjs) return pdfjs;
  const lib = await import(PDFJS_SRC);
  lib.GlobalWorkerOptions.workerSrc = WORKER_SRC;
  pdfjs = lib;
  return lib;
}

// ═════════════════════════════════════════════════════════════════════════════════════════
// 4 · the block renderer — pieces, math, citations, refs, figures, raw
// ═════════════════════════════════════════════════════════════════════════════════════════

const FIGS = [];   // Live figure documents, released when their blocks are replaced.
let figureObserver=null, pendingFigures=new WeakMap();
function releaseFigure(figure){figure.task?.cancel();Promise.resolve(figure.loading?.destroy?.()??figure.doc?.destroy?.()).catch(()=>{});}

/** One equation or inline formula, through the vendored KaTeX with THE PAYLOAD'S MACROS.
 *  KaTeX's own macro table is copied per call: the renderer mutates what it is handed
 *  (\gdef), and the payload's table is the one producer. */
function renderMathNode(tex, display) {
  const n = el("span", "mathq");
  n.dataset.tex = String(tex || "");
  if (display) n.dataset.block = "1";
  if (!K.katex) {
    n.classList.add("unknown");
    n.textContent = display ? String(tex || "") : "$" + String(tex || "") + "$";
    D.unknown += 1;
    return n;
  }
  const src = String(tex || "");
  const opts = { displayMode: !!display, macros: Object.assign({}, D.macros),
                 strict: "ignore", output: "html", trust: false };
  let html = "", refused = "";
  try {
    // strict first, so an unresolved macro is CAUGHT rather than absorbed into a colour.
    html = K.katex.renderToString(src, Object.assign({ throwOnError: true }, opts));
  } catch (err) {
    refused = String((err && err.message) || "the renderer refused it");
    try {
      // then permissive, so the rest of the formula still reads — with the refusal named.
      html = K.katex.renderToString(src,
        Object.assign({ throwOnError: false, errorColor: "var(--red-70-c)" }, opts));
    } catch (_e) { html = ""; }
  }
  if (!html) {
    n.classList.add("unknown");
    n.textContent = src;
    D.unknown += 1;
    return n;
  }
  n.innerHTML = html;
  // KaTeX marks an unresolved control sequence with a colour and a hover-only title=.
  // Colour alone is not a mark and a tooltip does not exist in this surface: the failure
  // is stated in words, in place, and counted.
  for (const bad of n.querySelectorAll(".katex-error")) {
    bad.removeAttribute("title");
    bad.classList.add("unknown");
  }
  if (refused) {
    const m = /Undefined control sequence:\s*(\\[a-zA-Z@]+)/.exec(refused);
    n.dataset.unresolved = "1";
    n.appendChild(el(display ? "div" : "span", "unknown",
      " ⟨unresolved " + (m ? m[1] : "macro") + " — the payload carried no expansion⟩"));
    D.unknown += 1;
  }
  // output:"html" hides its own tree from assistive tech; the tex is the label instead.
  for (const h of n.querySelectorAll("[aria-hidden]")) h.removeAttribute("aria-hidden");
  n.setAttribute("role", "math");
  n.setAttribute("aria-label", String(tex || ""));
  return n;
}

let mathObserver = null, mathFrame = 0, mathGeneration = 0;
const pendingMath = new Set();
function scheduleMath() {
  if (!mathFrame && pendingMath.size) mathFrame = requestAnimationFrame(hydrateMath);
}
function mathIsBeingEdited(node) {
  const block=node.closest('.blk[data-block]');
  if(block && P.has(block.dataset.block))return true;
  const host = node.closest('.blk-body[contenteditable="true"]');
  if (host && (host === document.activeElement || host.contains(document.activeElement))) return true;
  const selection = document.getSelection();
  return !!(selection?.rangeCount && !selection.isCollapsed && selection.getRangeAt(0).intersectsNode(node));
}
async function hydrateMath() {
  mathFrame = 0;
  const generation = mathGeneration;
  await ensureKatex();
  if (generation !== mathGeneration) return;
  const start = performance.now();
  let changed = false, more = false;
  const touched=new Set();
  for (const node of pendingMath) {
    if (!node.isConnected || !node.classList.contains('pending')) { pendingMath.delete(node); continue; }
    if (mathIsBeingEdited(node)) continue;
    if (performance.now() - start > 8 && changed) { more = true; break; }
    const fresh = renderMathNode(node.dataset.tex || '', node.dataset.block === '1');
    // Piece maps and selections refer to this exact host. Hydrate inside it.
    node.replaceChildren(...fresh.childNodes);
    node.classList.remove('pending');
    for (const name of fresh.classList) node.classList.add(name);
    for (const key of ['role','aria-label','data-unresolved']) {
      if (fresh.hasAttribute(key)) node.setAttribute(key, fresh.getAttribute(key));
    }
    pendingMath.delete(node); changed = true;
    const blockEl = node.closest('.blk[data-block]');
    const block = blockEl ? blockById.get(blockEl.dataset.block) : null;
    if (block && block.bodyEl) {
      block.texFace = block.kind === 'raw' || !!block.bodyEl.querySelector('.mathq.unknown');
      sealIslands(block.bodyEl); setEditable(block, block.bodyEl);
      touched.add(block);
    }
  }
  for(const block of touched)refreshPieceMap(block);
  if (changed) scheduleRemeasure();
  if (more) scheduleMath();
}
function mathNode(tex, display) {
  const node = el('span', 'mathq pending');
  node.dataset.tex = String(tex || '');
  if (display) node.dataset.block = '1';
  node.textContent = String(tex || '');
  node.setAttribute('role','math'); node.setAttribute('aria-label',String(tex || ''));
  if (!mathObserver && 'IntersectionObserver' in window) {
    mathObserver = new IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) {
        mathObserver.unobserve(entry.target); pendingMath.add(entry.target);
      }
      scheduleMath();
    }, {root:paper, rootMargin:'600px 0px'});
  }
  if (mathObserver) mathObserver.observe(node);
  else { pendingMath.add(node); scheduleMath(); }
  return node;
}
document.addEventListener('focusout', scheduleMath);
document.addEventListener('selectionchange', scheduleMath);

/** A new render releases every math and figure task of the canvas it replaces: late math frames
 *  carry the old generation and stop, pending figures are dropped and their resources released. */
function releaseMediaForRender() {
  mathGeneration++; mathObserver?.disconnect(); pendingMath.clear();
  figureObserver?.disconnect();pendingFigures=new WeakMap();
  for(const figure of FIGS)releaseFigure(figure);
  if (mathFrame) cancelAnimationFrame(mathFrame); mathFrame = 0;
}

async function drawFigure(fig, route, dimensions=null) {
  if(pdfFigureRoute(route)&&'IntersectionObserver' in window){
    if(!figureObserver)figureObserver=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){figureObserver.unobserve(
      entry.target);const pending=pendingFigures.get(entry.target);if(pending){pendingFigures.delete(entry.target);drawFigureNow(entry.target,
      pending.route,pending.dimensions);}}},{root:paper,rootMargin:'600px 0px'});
    fig.style.minHeight='140px';pendingFigures.set(fig,{route,dimensions});figureObserver.observe(fig);return;
  }
  return drawFigureNow(fig,route,dimensions);
}

async function drawFigureNow(fig, route, dimensions=null) {
  if (!pdfFigureRoute(route)) {
    const img = el("img");
    img.alt = "";
    img.loading='lazy';img.decoding='async';
    if(dimensions?.width>0&&dimensions?.height>0){img.width=dimensions.width;img.height=dimensions.height;img.style.aspectRatio=dimensions.width+'/'+dimensions.height;}
    img.addEventListener('load',scheduleRemeasure);
    img.addEventListener("error", () => {
      img.remove();
      const error=asChrome(el('div','fig-note','The figure could not load. Its source and caption are preserved.'));
      const retry=el('button','retry-figure','Retry figure');retry.onclick=()=>{error.remove();drawFigure(fig,route,dimensions);};error.appendChild(
        retry);fig.appendChild(error);scheduleRemeasure();
    });
    img.src = route;
    fig.appendChild(img);
    scheduleRemeasure();
    return;
  }
  let lib;
  try {
    lib = await ensurePdfjs();
  } catch (e) {
    fig.appendChild(el("div", "fig-note", "the vendored pdf.js did not load, so this "
      + "figure cannot be drawn here. " + e.message));
    return;
  }
  try {
    const loading=lib.getDocument({ url: route });
    const doc = await loading.promise;
    if(!fig.isConnected){await loading.destroy();return;}
    const page = await doc.getPage(1);
    if(!fig.isConnected){await loading.destroy();return;}
    const canvas = el("canvas");
    fig.appendChild(canvas);
    const F = { fig, canvas, page, doc, loading, dimensions, task:null, ticket:0 };
    if(dimensions?.scaleToText){
      try{const content=await page.getTextContent();F.bodyFontPt=dominantPreviewFont(content.items);canvas.setAttribute('role','img');
        canvas.setAttribute('aria-label',content.items.map(item=>item.str||'').join(' ')||dimensions.label||'Typeset environment');}catch{
        canvas.setAttribute('aria-label',dimensions.label||'Typeset environment');}
      if(!fig.isConnected){await loading.destroy();return;}
    }
    FIGS.push(F);
    await paintFigure(F);
    fig.style.minHeight='';
    scheduleRemeasure();
  } catch (e) {
    fig.appendChild(el("div", "fig-note",
      "the figure at " + route + " did not open. " + e.message));
  }
}

async function paintFigure(F) {
  if (!F.fig.isConnected) return;
  const ticket=++F.ticket;
  if(F.task){const previous=F.task;F.task=null;previous.cancel();await previous.promise.catch(()=>{});}
  if(ticket!==F.ticket||!F.fig.isConnected)return;
  const availableWidth = Math.max(120, F.fig.clientWidth || measurePx());
  const dpr = clamp(window.devicePixelRatio || 1, 1, 2);
  const vp1 = F.page.getViewport({ scale: 1 });
  const width=F.dimensions?.scaleToText?compiledPreviewWidth({pageWidth:vp1.width,availableWidth,readerFontPx:parseFloat(getComputedStyle(
    F.fig).fontSize),bodyFontPt:F.bodyFontPt}):availableWidth;
  const vp = F.page.getViewport({ scale: width / (vp1.width || width) });
  F.canvas.width = Math.floor(vp.width * dpr);
  F.canvas.height = Math.floor(vp.height * dpr);
  F.canvas.style.width = Math.round(vp.width) + "px";
  F.canvas.style.height = Math.round(vp.height) + "px";
  try {
    const task=F.page.render({ canvasContext: F.canvas.getContext("2d", { alpha: false }),
                          viewport: vp,
                          transform: dpr === 1 ? null : [dpr, 0, 0, dpr, 0, 0] });F.task=task;
    await task.promise;if(F.task===task)F.task=null;
  } catch (_e) { /* a cancelled or superseded render leaves the last good pixels */ }
}

function repaintFigures() {
  for (const F of FIGS.slice()) {
    if (!F.fig.isConnected) { releaseFigure(F);FIGS.splice(FIGS.indexOf(F), 1); continue; }
    paintFigure(F);
  }
}

/** The block's rendered body. ONE reader: the source flip and every re-render call this,
 *  so the canvas and the model can never disagree about what a block looks like. */
/** Normalize display environments for the vendored renderer. Numbered rows use
 * explicit tags from compiled label identities inside starred environments;
 * no browser counter is allowed to invent missing manuscript numbers. Displays
 * without row tags retain the existing aligned/gathered inner wrappers. */
const KATEX_ALIGNED = new Set(["align", "align*", "alignat", "alignat*", "eqnarray",
                               "eqnarray*", "split", "flalign", "flalign*"]);
const KATEX_GATHERED = new Set(["gather", "gather*", "multline", "multline*"]);

function equationTex(b) {
  let math = b.math || b.tex || "";
  const env = String(b.env || "").trim();
  const rowEnvironment={align:'align*',alignat:'alignat*',flalign:'align*',eqnarray:'align*',gather:'gather*'}[env.replace(/\*$/,'')];
  if(rowEnvironment){
    // Use only the compiled labels on each row. The starred renderer never
    // invents counters for rows with no retained number.
    if(!env.endsWith('*')&&!/\\tag\*?\s*\{/.test(math)){
      const seen=new Set();const tags=(b.equation_labels||[]).filter(row=>{const n=D.refs[row.label];if(n==null||n===''||seen.has(String(n))||
        !Number.isInteger(row.offset)||row.offset<0||row.offset>math.length)return false;seen.add(String(n));return true;}).sort((a,b)=>b.offset-a.offset);
      for(const row of tags)math=math.slice(0,row.offset)+'\\tag{'+D.refs[row.label]+'}'+math.slice(row.offset);
    }
    if(/\\tag\*?\s*\{/.test(math))return '\\begin{'+rowEnvironment+'}'+math+'\\end{'+rowEnvironment+'}';
  }
  if (/^alignat\*?$/.test(env)) return "\\begin{alignedat}" + math + "\\end{alignedat}";
  if (KATEX_ALIGNED.has(env)) return "\\begin{aligned}" + math + "\\end{aligned}";
  if (KATEX_GATHERED.has(env)) return "\\begin{gathered}" + math + "\\end{gathered}";
  return math;
}

function appendEquation(b,host){
  const tex=equationTex(b),m=mathNode(tex,true);host.appendChild(m);
  const unnumbered=/\*$/.test(b.env||'')||['displaymath','aligned','gathered','split','cases'].includes(b.env);
  const number=unnumbered?'':b.number||blockLabels(b).map(label=>D.refs[label]).find(value=>value!=null&&value!=='');
  if(number&&!/\\tag\*?\s*\{/.test(tex)){const tag=asChrome(el('span','equation-number','('+number+')'));tag.setAttribute('aria-label','Equation '+number);host.appendChild(tag);}
  return m;
}

export {
  FIGS, K, appendEquation, drawFigure, ensureKatex, ensurePdfjs, mathNode, releaseMediaForRender,
  repaintFigures
};
