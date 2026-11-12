// WALK GEOMETRY (S2 F5). Purpose: the geometry face: the project's named review PDF behind one head
// door, its scale dial and the visible-page renderer. Owns: G (document, pages, scale and render
// tasks). Public contract: openGeometry/closeGeometry/toggleGeometry, geoSetScale, geoComputeFit,
// geoMeasure, geoRenderVisible. Lifetime: closing releases every page task and canvas (geoRelease);
// the PDF source is the exact owner handle from the document context, never another model.
import {
  GUTTER, PROBE, PURGE_MARGIN, RENDER_MARGIN, SCALE_MAX, SCALE_MIN, clamp, el, geoBack, geoDoor, geoLabel,
  geoNote, geoPages, geoScroll, paper, root, text
} from './walk-base.mjs';
import {S, measure, paintZoom, readingY, sectionAtY} from './walk-position.mjs';
import {ensurePdfjs} from './walk-media.mjs';

// ═════════════════════════════════════════════════════════════════════════════════════════
// 10 · the geometry face — the named review pdf, behind ONE head door
// ═════════════════════════════════════════════════════════════════════════════════════════
//
// The pdf is no longer the working canvas. It is the face where GEOMETRY is graded — line
// breaks, page breaks, floats, the typeset frame — and it opens on his gesture, with the
// named return door lit beside it, and closes back to exactly the text he left.

const G = {
  open: false, loaded: false, loading: false,
  pdf: null, pages: [], tops: [], heights: [], scale: 1,
  paperScroll: 0,
};

async function loadGeometryPdf() {
  if (G.loaded || G.loading) return G.loaded;
  if (!S.source) {
    geoNote.hidden = false;
    text(geoNote, "this project has no compiled pdf on disk, so there is no typeset face "
      + "to grade geometry on. The text canvas is unaffected.");
    return false;
  }
  G.loading = true;
  geoNote.hidden = false;
  text(geoNote, "opening " + S.source.pdf + "…");
  let lib;
  try {
    lib = await ensurePdfjs();
  } catch (e) {
    G.loading = false;
    text(geoNote, "the vendored pdf.js did not load, so the geometry face cannot open. "
      + e.message);
    return false;
  }
  const url = "/projection/pdf?file=" + encodeURIComponent(S.source.pdf)
            + (S.corpus ? "&corpus=" + encodeURIComponent(S.corpus) : "");
  try {
    G.loadingTask=lib.getDocument({url});
    G.pdf = await G.loadingTask.promise;
  } catch (e) {
    G.loading = false;
    text(geoNote, "the pdf at " + S.source.pdf + " did not open. " + e.message);
    return false;
  }
  const pages = [];
  for (let i = 1; i <= G.pdf.numPages; i++) {
    const page = await G.pdf.getPage(i);
    const vp1 = page.getViewport({ scale: 1 });
    pages.push({ index: i - 1, page, w1: vp1.width, h1: vp1.height,
                 el: null, canvas: null, rendered: false, task: null });
  }
  G.pages = pages;
  geoPages.textContent = "";
  for (const P of pages) {
    const node = el("div", "pg");
    node.dataset.page = String(P.index + 1);
    const canvas = el("canvas");
    node.appendChild(canvas);
    P.el = node; P.canvas = canvas;
    geoPages.appendChild(node);
  }
  G.scale = geoComputeFit();
  geoApplyScale();
  geoMeasure();
  geoNote.hidden = true;
  G.loaded = true;
  G.loading = false;
  geoRenderVisible();
  paintZoom();
  return true;
}

function geoComputeFit() {
  const avail = (geoScroll.clientWidth || 0) - 2 * GUTTER;
  const widest = G.pages.reduce((m, P) => Math.max(m, P.w1), 1);
  return clamp(avail / widest, SCALE_MIN, SCALE_MAX);
}

function geoApplyScale() {
  for (const P of G.pages) {
    P.el.style.width = Math.round(P.w1 * G.scale) + "px";
    P.el.style.height = Math.round(P.h1 * G.scale) + "px";
  }
}

function geoMeasure() {
  G.tops = G.pages.map((P) => P.el.offsetTop);
  G.heights = G.pages.map((P) => P.el.offsetHeight);
}

function geoSetScale(next) {
  const target = clamp(next, SCALE_MIN, SCALE_MAX);
  if (!G.pages.length || Math.abs(target - G.scale) < 0.001) { paintZoom(); return; }
  // the focal point on the geometry face: the page under its own reading line.
  const y = geoScroll.scrollTop + geoScroll.clientHeight * PROBE;
  let i = 0;
  for (let k = 0; k < G.tops.length; k++) if (G.tops[k] <= y) i = k;
  const frac = (y - (G.tops[i] || 0)) / (G.heights[i] || 1);
  for (const P of G.pages) geoRelease(P);
  G.scale = target;
  geoApplyScale();
  geoMeasure();
  geoScroll.scrollTop = Math.max(0, (G.tops[i] || 0) + frac * (G.heights[i] || 1)
    - geoScroll.clientHeight * PROBE);
  geoRenderVisible();
  paintZoom();
}

function geoRelease(P) {
  if (P.task) { try { P.task.cancel(); } catch (_e) { /* already settled */ } P.task = null; }
  P.rendered = false;
  if (P.canvas) { P.canvas.width = 0; P.canvas.height = 0; }
}

async function geoRenderPage(P) {
  if (P.rendered || P.task) return;
  const scaleAtStart = G.scale;
  const dpr = clamp(window.devicePixelRatio || 1, 1, 2);
  const vp = P.page.getViewport({ scale: scaleAtStart });
  P.canvas.width = Math.floor(vp.width * dpr);
  P.canvas.height = Math.floor(vp.height * dpr);
  const task = P.page.render({
    canvasContext: P.canvas.getContext("2d", { alpha: false }), viewport: vp,
    transform: dpr === 1 ? null : [dpr, 0, 0, dpr, 0, 0],
  });
  P.task = task;
  try {
    await task.promise;
  } catch (_e) { P.task = null; return; }
  P.task = null;
  if (G.scale !== scaleAtStart) { geoRelease(P); return; }
  P.rendered = true;
}

function geoRenderVisible() {
  if (!G.pages.length) return;
  const top = geoScroll.scrollTop, h = geoScroll.clientHeight;
  const near = [top - h * RENDER_MARGIN, top + h * (1 + RENDER_MARGIN)];
  const far = [top - h * PURGE_MARGIN, top + h * (1 + PURGE_MARGIN)];
  for (let i = 0; i < G.pages.length; i++) {
    const a = G.tops[i] || 0, b = a + (G.heights[i] || 0);
    if (b >= near[0] && a <= near[1]) geoRenderPage(G.pages[i]);
    else if ((b < far[0] || a > far[1]) && G.pages[i].rendered) geoRelease(G.pages[i]);
  }
}

/** G4 on the door: the visit is named on the way in, and the way home is lit. */
async function openGeometry() {
  if (G.open) return true;
  if (!S.source) {
    geoNote.hidden = false;
    text(geoNote, "this project has no compiled pdf on disk, so there is no typeset face.");
  }
  G.paperScroll = paper.scrollTop;
  const sec = S.sections[S.current >= 0 ? S.current : sectionAtY(readingY())];
  G.open = true;
  root.dataset.geo = "1";
  geoDoor.dataset.open = "1";
  text(geoBack, "back to the text" + (sec ? " at §" + sec.title : "") + " (Esc)");
  text(geoLabel, (S.source ? S.source.label : "no typeset face on disk")
    + "  ·  geometry is graded here: line breaks, page breaks, floats. The text is the "
    + "working canvas.");
  paintZoom();
  await loadGeometryPdf();
  geoScroll.focus();
  return true;
}

function closeGeometry() {
  if (!G.open) return false;
  G.open = false;
  delete root.dataset.geo;
  delete geoDoor.dataset.open;
  // the pane was display:none while the face stood: the scroll is restored explicitly, so
  // he lands on exactly the line he left (G1 across the door).
  paper.scrollTop = G.paperScroll;
  measure();
  paper.scrollTop = G.paperScroll;
  paintZoom();
  paper.focus();
  return true;
}

const toggleGeometry = () => (G.open ? closeGeometry() : openGeometry());

export {
  G, closeGeometry, geoComputeFit, geoMeasure, geoRenderVisible, geoSetScale, openGeometry, toggleGeometry
};
