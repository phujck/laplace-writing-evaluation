#!/usr/bin/env python
"""Bake a CanonGraph JSON projection into a self-contained, server-free,
clickable static HTML snapshot in the deck dark palette.

One engine, two graphs (the talk's derivation spine, and the canon/wiki
name-only map). The output replicates the live laplace viewer's read model -
a scale-local network you click to inspect a node's detail and neighbours -
but bakes the graph inline so it needs no localhost server. Fits a 16:9 embed
with no scroll.

Usage:
  python scripts/bake_graph_snapshot.py <graph.json> <out.html> \
      --title "..." --subtitle "..." --kind talk|wiki

AUDITED 2026-08-15 (WO-20260815, the honest-refusal sweep): this script contacts NO
service. It is a pure file→file baker — the only "localhost" in it is the docstring line
above promising the OUTPUT needs no server — so the service-absence contract has nothing
to bind to here. Its one degrade path is an absent or unreadable INPUT graph, which used
to surface as a bare traceback; that now refuses in words with exit 3, and writes nothing.

Exit: 0 baked · 3 REFUSED TO BAKE (the input graph is absent or unreadable — no output
file was created or overwritten).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service_probe import REFUSAL_EXIT, refusal_line  # noqa: E402

# Deck dark palette - matched to conceptric_snapshot.html / engine-facsimile.html.
PALETTE = {
    "bg": "#0e1116", "panel": "#161b22", "ink2": "#0b0f14", "line": "#283041",
    "ink": "#e6edf3", "dim": "#7d8794", "accent": "#4A90D9", "math": "#9B5DE5",
}

# Group -> colour, lifted verbatim from viewer_app.html GROUP_COLOR so the
# static snapshot reads identically to the live viewer.
GROUP_COLOR = {
    "endogenous": "#2ECC71", "exogenous": "#E67E22", "intrinsic": "#9B5DE5",
    "result": "#D35400", "artefact": "#E74C3C", "goal": "#F1C40F", "section": "#5C7AA0",
    "assumption": "#27AE60", "definition": "#16A085", "knowledge": "#E67E22",
    "equation": "#9B5DE5", "figure": "#16A085", "citation": "#7F8C8D", "missing": "#C0392B",
    "aesthetics": "#EC4899", "operations": "#4A90D9", "structure": "#84CC16",
    "workflow": "#F39C12", "templates": "#95A5A6", "author": "#2ECC71",
    "voice_corpus": "#1ABC9C", "domains": "#E67E22", "generating": "#F39C12",
    "staging": "#4A90D9", "evaluating": "#9B5DE5", "domain": "#E74C3C", "agent": "#F1C40F",
}

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>__TITLE__</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<style>
  :root{ --bg:__BG__; --panel:__PANEL__; --ink2:__INK2__; --line:__LINE__;
    --ink:__INK__; --dim:__DIM__; --accent:__ACCENT__; --math:__MATH__; }
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{height:100%;width:100%;overflow:hidden;background:var(--bg);color:var(--ink);
    font:14px/1.5 ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif;-webkit-font-smoothing:antialiased}
  .wrap{display:flex;height:100%;width:100%}
  .macro{flex:0 0 60%;position:relative;min-width:0}
  .macro canvas{position:absolute;top:0;left:0;width:100%;height:100%;display:block;cursor:pointer}
  .lbl{position:absolute;top:11px;left:15px;font-size:11px;color:var(--dim);
    text-transform:uppercase;letter-spacing:.6px;pointer-events:none;z-index:2}
  .hint{position:absolute;bottom:11px;left:15px;right:15px;font-size:10.5px;color:var(--dim);
    font-style:italic;pointer-events:none;z-index:2;line-height:1.4}
  .detail{flex:1;border-left:1px solid var(--line);background:var(--panel);
    display:flex;flex-direction:column;min-width:0;overflow:hidden}
  .detail .lbl{position:static;padding:13px 22px 0}
  .body{flex:1;overflow-y:auto;padding:6px 22px 16px}
  .kind{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.5px;margin-top:6px}
  .body h2{font-size:16.5px;margin:3px 0 2px;line-height:1.3}
  .badge{display:inline-block;padding:2px 9px;border-radius:11px;font-size:11px;margin:7px 7px 0 0;
    background:#10243a;color:var(--accent)}
  .row{margin:11px 0;padding-top:10px;border-top:1px solid var(--line)}
  .k{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px}
  .summary{color:#c2c8d2;font-size:13px;line-height:1.5}
  .math{background:var(--ink2);border:1px solid var(--line);border-left:3px solid var(--math);
    border-radius:6px;padding:9px 12px;margin:5px 0;font-size:15px;overflow-x:auto}
  .chips{display:flex;flex-wrap:wrap;gap:6px}
  .chip{display:inline-flex;align-items:center;gap:7px;background:var(--ink2);border:1px solid var(--line);
    border-radius:13px;padding:4px 11px;font-size:12.5px;cursor:pointer;color:var(--ink);transition:background .12s}
  .chip:hover{background:#10243a;border-color:var(--accent)}
  .chip .dot{width:9px;height:9px;border-radius:50%;flex:0 0 auto}
  .note{padding:12px 22px;border-top:1px solid var(--line);color:var(--dim);font-size:10.5px;
    font-style:italic;line-height:1.45;flex:0 0 auto}
  .placeholder{color:var(--dim);font-size:13px;line-height:1.55;margin-top:14px}
  .katex{font-size:1em}
</style></head>
<body>
<div class="wrap">
  <div class="macro">
    <div class="lbl">__MACROLABEL__</div>
    <canvas id="cv"></canvas>
    <div class="hint">__HINT__</div>
  </div>
  <div class="detail">
    <div class="lbl">node — click the graph to inspect</div>
    <div class="body" id="body">
      <p class="placeholder">__PLACEHOLDER__</p>
    </div>
    <div class="note">__NOTE__</div>
  </div>
</div>

<script>
const GRAPH = __GRAPH_JSON__;
const GROUP_COLOR = __GROUP_COLOR__;
const KIND = "__KIND__";   // talk | wiki
const ACCENT = "__ACCENT__", DIM = "__DIM__", INK = "__INK__", LINE = "__LINE__",
      BG = "__BG__", PANEL = "__PANEL__", MATHC = "__MATH__";

// ── index ──────────────────────────────────────────────────────────────
const byId = {}; GRAPH.nodes.forEach(n => byId[n.id] = n);
const node = id => byId[id];
function col(n){ return (n && (GROUP_COLOR[n.group] || GROUP_COLOR[n.kind])) || "#7F8C8D"; }

// Containment: a node is "interior" if some `contains` edge points at it; the
// macro level is everything NOT contained (the viewer's projTop rule). draws is
// lineage, not nesting, so it does not hide a node.
const contained = new Set(GRAPH.edges.filter(e => e.rel === "contains").map(e => e.dst));
const VERT = new Set(["contains"]);          // nesting (interior)
const LINEAGE = "draws";                      // fed-from / feeds-into
const LAT = new Set(["shares", "supports", "contradicts"]);  // peer interaction

function interiorOf(id){ const o = [], s = new Set();
  for(const e of GRAPH.edges) if(VERT.has(e.rel) && e.src === id && !s.has(e.dst)){ s.add(e.dst); const n = node(e.dst); if(n) o.push(n);} return o; }
function drawsOf(id){ const o = [], s = new Set();   // what this node is fed from (down)
  for(const e of GRAPH.edges) if(e.rel === LINEAGE && e.src === id && !s.has(e.dst)){ s.add(e.dst); const n = node(e.dst); if(n) o.push(n);} return o; }
function feedsOf(id){ const o = [], s = new Set();   // what draws on this node (up)
  for(const e of GRAPH.edges) if(e.rel === LINEAGE && e.dst === id && !s.has(e.src)){ s.add(e.src); const n = node(e.src); if(n) o.push(n);} return o; }
function parentsOf(id){ const o = [], s = new Set(); // coarse nodes that contain this (for an interior node)
  for(const e of GRAPH.edges) if(VERT.has(e.rel) && e.dst === id && !s.has(e.src)){ s.add(e.src); const n = node(e.src); if(n) o.push(n);} return o; }
function peersOf(id){ const o = [], s = new Set();
  for(const e of GRAPH.edges){ if(!LAT.has(e.rel)) continue;
    let other = e.src === id ? e.dst : (e.dst === id ? e.src : null);
    if(other && !s.has(other)){ s.add(other); const n = node(other); if(n) o.push({n, rel:e.rel}); } } return o; }
// canon prose links: this page/skill -> the targets it names, and <- who names it.
const LINKREL = new Set(["links_to","belongs_to_domain","has_axioms","has_project"]);
function linksOutOf(id){ const o=[], s=new Set();
  for(const e of GRAPH.edges) if(LINKREL.has(e.rel) && e.src===id && !s.has(e.dst)){ s.add(e.dst); const n=node(e.dst); if(n) o.push(n);} return o; }
function linksInOf(id){ const o=[], s=new Set();
  for(const e of GRAPH.edges) if(LINKREL.has(e.rel) && e.dst===id && !s.has(e.src)){ s.add(e.src); const n=node(e.src); if(n) o.push(n);} return o; }
function hasInterior(id){ return interiorOf(id).length > 0; }

// Two read models, one engine:
//  - talk: the curated SPINE. Macro = top-level (not contained) nodes - the three
//    roots + the B0..B10 beats - wired by lineage (draws) + peer edges. Click a
//    beat to open its interior (objects, equations) in the panel.
//  - wiki: the FLAT canon web. Every real node, wired by its REAL links
//    (links_to wikilinks + the structural belongs/contains/has_* spine), so the
//    whole connected canon is one navigable object on a single screen.
const FLAT = (KIND === "wiki");
// link relations that connect the canon: prose wikilinks + the structural spine.
const STRUCT = new Set(["links_to", "belongs_to_domain", "has_axioms", "has_project", "contains"]);
const MACRO = GRAPH.nodes.filter(n =>
  n.kind !== "missing" && (FLAT ? true : !contained.has(n.id)));
const MACRO_IDS = new Set(MACRO.map(n => n.id));
let MACRO_EDGES = GRAPH.edges.filter(e =>
  MACRO_IDS.has(e.src) && MACRO_IDS.has(e.dst) && e.src !== e.dst &&
  (FLAT ? (STRUCT.has(e.rel) || e.rel === LINEAGE || LAT.has(e.rel))
        : (e.rel === LINEAGE || LAT.has(e.rel))));
// Talk spine: a beat draws ATOMS that live inside the three roots (self_consistency
// inside intrinsic, endogeneity inside endogenous, ...). Lift those to a faint
// root->beat edge so the three roots visibly feed the spine at the macro level,
// rather than floating disconnected. This is the lift the live viewer computes;
// here we surface it as a derived macro edge (deduped, marked rel:"draws").
if(!FLAT){
  const parentOfAtom = {};
  for(const e of GRAPH.edges) if(e.rel==="contains") parentOfAtom[e.dst] = e.src;
  const seen = new Set(MACRO_EDGES.map(e=>e.src+">"+e.dst+">"+e.rel));
  const lifted = [];
  for(const e of GRAPH.edges){
    if(e.rel!==LINEAGE) continue;
    const beat = e.src, atomParent = parentOfAtom[e.dst];
    if(MACRO_IDS.has(beat) && atomParent && MACRO_IDS.has(atomParent) && beat!==atomParent){
      const key = atomParent+">"+beat+">draws";       // root -> beat (root feeds beat)
      if(!seen.has(key)){ seen.add(key); lifted.push({src:atomParent, dst:beat, rel:"draws", count:1}); }
    }
  }
  MACRO_EDGES = MACRO_EDGES.concat(lifted);
}

// ── deterministic layout: seeded force simulation, frozen (no live wiggle) ──
// A fixed seed makes the layout identical on every load - the no-wiggle rule.
function mulberry32(a){ return function(){ a |= 0; a = a + 0x6D2B79F5 | 0;
  let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
  return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const pos = {};   // id -> {x,y} in a unit-ish space, centred on 0
// Layout params scale with node count: the dense flat canon wants a shorter
// ideal edge length and more iterations than the curated spine.
const N0 = MACRO.length;
const LO = FLAT
  ? { K: 78, iters: 620, seedR: 360, rep: 0.95, att: 0.10, centre: 0.020 }
  : { K: 150, iters: 400, seedR: 250, rep: 1.0,  att: 0.06, centre: 0.012 };
function layout(){
  const rnd = mulberry32(0x1A2B3C);
  const ids = MACRO.map(n => n.id);
  const n = ids.length;
  // seed on a circle (deterministic) so the force start is stable
  ids.forEach((id, i) => { const a = 2*Math.PI*i/n - Math.PI/2;
    pos[id] = { x: Math.cos(a)*LO.seedR*1.15 + (rnd()-0.5)*30, y: Math.sin(a)*LO.seedR + (rnd()-0.5)*30 }; });
  const adj = MACRO_EDGES.map(e => [e.src, e.dst]);
  const K = LO.K;
  for(let it = 0; it < LO.iters; it++){
    const fx = {}, fy = {}; ids.forEach(id => { fx[id]=0; fy[id]=0; });
    // repulsion (all pairs)
    for(let i=0;i<n;i++) for(let j=i+1;j<n;j++){
      const a=ids[i], b=ids[j]; let dx=pos[a].x-pos[b].x, dy=pos[a].y-pos[b].y;
      let d2=dx*dx+dy*dy; if(d2<1) d2=1; const d=Math.sqrt(d2);
      const rep = (K*K)/d2 * LO.rep; fx[a]+=dx/d*rep; fy[a]+=dy/d*rep; fx[b]-=dx/d*rep; fy[b]-=dy/d*rep;
    }
    // attraction (edges)
    for(const [a,b] of adj){ let dx=pos[a].x-pos[b].x, dy=pos[a].y-pos[b].y;
      const d=Math.sqrt(dx*dx+dy*dy)||1; const att=(d*d)/K * LO.att;
      fx[a]-=dx/d*att; fy[a]-=dy/d*att; fx[b]+=dx/d*att; fy[b]+=dy/d*att; }
    // gentle centring
    const cool = 0.85 * (1 - it/LO.iters) + 0.05;
    ids.forEach(id => { fx[id] -= pos[id].x*LO.centre; fy[id] -= pos[id].y*LO.centre;
      pos[id].x += Math.max(-30,Math.min(30,fx[id]))*cool;
      pos[id].y += Math.max(-30,Math.min(30,fy[id]))*cool; });
  }
}
layout();

// fit the laid-out cloud into the canvas with margins
function bounds(){ let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;
  for(const id in pos){ const p=pos[id]; x0=Math.min(x0,p.x); y0=Math.min(y0,p.y); x1=Math.max(x1,p.x); y1=Math.max(y1,p.y);} return {x0,y0,x1,y1}; }

const cv = document.getElementById("cv"), ctx = cv.getContext("2d");
let W=0, H=0, T={s:1,ox:0,oy:0};
function fit(){
  const b = bounds(), pad = 64;
  const gw = (b.x1-b.x0)||1, gh=(b.y1-b.y0)||1;
  const s = Math.min((W-2*pad)/gw, (H-2*pad)/gh);
  T.s = s;
  T.ox = W/2 - s*(b.x0+b.x1)/2;
  T.oy = H/2 - s*(b.y0+b.y1)/2;
}
function sx(p){ return T.ox + p.x*T.s; }
function sy(p){ return T.oy + p.y*T.s; }

function rad(n){
  if(["cluster","domain","artefact"].includes(n.kind)) return 17;
  if(n.kind === "result") return 14;
  if(n.kind === "goal") return 13;
  if(n.kind === "wiki") return (n.meta && n.meta.coarse) ? 14 : 10;
  if(n.kind === "skill") return 10;
  return 9;
}
// short symbol drawn beside a node
function sym(n){
  if(n.kind === "result") return n.id;
  if(n.kind === "cluster") return String(n.group||"").slice(0,3).toUpperCase();
  if(n.kind === "artefact") return (n.label||"").split(/[ (]/)[0];
  if(n.kind === "domain") return n.label;
  const s = String(n.label || n.id);
  return s.length <= 16 ? s : s.slice(0,15) + "…";
}

let sel = null, hover = null;
const EDGE_COL = rel => rel === "contradicts" ? "#E74C3C" : rel === "supports" ? "#2ECC71"
  : rel === LINEAGE ? "#3a455c" : "#41597a";

function resize(){ const d = window.devicePixelRatio||1; const r = cv.parentElement.getBoundingClientRect();
  W = Math.round(r.width); H = Math.round(r.height);
  cv.width = W*d; cv.height = H*d; ctx.setTransform(d,0,0,d,0,0); fit(); draw(); }
window.addEventListener("resize", resize);

function draw(){
  ctx.clearRect(0,0,W,H); ctx.fillStyle = BG; ctx.fillRect(0,0,W,H);
  // edges
  for(const e of MACRO_EDGES){ const A=pos[e.src], B=pos[e.dst]; if(!A||!B) continue;
    const on = sel && (e.src===sel||e.dst===sel);
    ctx.strokeStyle = EDGE_COL(e.rel);
    ctx.globalAlpha = on ? 0.95 : (e.rel===LINEAGE ? 0.45 : 0.6);
    ctx.lineWidth = (on?2.2:1) + Math.min(3,(e.count||1)-1)*0.5;
    ctx.beginPath(); ctx.moveTo(sx(A),sy(A)); ctx.lineTo(sx(B),sy(B)); ctx.stroke();
  }
  ctx.globalAlpha = 1;
  // nodes
  ctx.textBaseline = "middle";
  for(const n of MACRO){ const p = pos[n.id]; if(!p) continue;
    const x=sx(p), y=sy(p), r=rad(n), c=col(n);
    const dim = sel && sel!==n.id && !isNeighbour(sel,n.id);
    ctx.globalAlpha = dim ? 0.34 : 1;
    // interior ring (a coarse node that opens)
    if(hasInterior(n.id)){ ctx.lineWidth=1.4; ctx.strokeStyle=c; ctx.beginPath(); ctx.arc(x,y,r+3.5,0,7); ctx.stroke(); }
    ctx.beginPath(); ctx.arc(x,y,r,0,7); ctx.fillStyle=c; ctx.fill();
    // loose nodes get a dashed orange ring (the viewer's convention)
    if(n.link === "loose"){ ctx.save(); ctx.setLineDash([3,3]); ctx.lineWidth=2; ctx.strokeStyle="#E67E22";
      ctx.beginPath(); ctx.arc(x,y,r+3,0,7); ctx.stroke(); ctx.restore(); }
    if(n.id === sel || n.id === hover){ ctx.lineWidth=2.5; ctx.strokeStyle="#fff"; ctx.beginPath(); ctx.arc(x,y,r,0,7); ctx.stroke(); }
    // label. In the dense flat canon, labelling all 79 nodes overlaps into mush,
    // so there label only the structural anchors (domains, coarse pages) plus the
    // hovered/selected node and its immediate neighbours; the curated spine labels
    // every node.
    const anchor = ["cluster","domain","artefact","result"].includes(n.kind) || (n.meta && n.meta.coarse);
    const near = sel && (n.id===sel || isNeighbour(sel,n.id));
    const showLabel = !FLAT || anchor || n.id===hover || near;
    if(showLabel){
      ctx.fillStyle = dim ? DIM : "#aebcce";
      ctx.font = (anchor ? "600 11px" : "10px") + " ui-sans-serif,Segoe UI,sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(sym(n), x+r+6, y+0.5);
    }
    ctx.globalAlpha = 1;
  }
}
function isNeighbour(a,b){
  for(const e of MACRO_EDGES){ if((e.src===a&&e.dst===b)||(e.src===b&&e.dst===a)) return true; } return false;
}

// ── picking ────────────────────────────────────────────────────────────
function pick(mx,my){ let best=null, bd=1e9;
  for(const n of MACRO){ const p=pos[n.id]; if(!p) continue;
    const d=Math.hypot(sx(p)-mx, sy(p)-my); const hit=Math.max(13, rad(n)+8);
    if(d<hit && d<bd){ bd=d; best=n; } } return best; }
cv.addEventListener("mousemove", e=>{ const r=cv.getBoundingClientRect();
  const n=pick(e.clientX-r.left, e.clientY-r.top); const id=n?n.id:null;
  if(id!==hover){ hover=id; cv.style.cursor=id?"pointer":"default"; draw(); } });
cv.addEventListener("mouseleave", ()=>{ if(hover){ hover=null; draw(); } });
cv.addEventListener("click", e=>{ const r=cv.getBoundingClientRect();
  const n=pick(e.clientX-r.left, e.clientY-r.top); if(n){ select(n.id); } });

// ── detail panel ─────────────────────────────────────────────────────────
function esc(s){ return (s==null?"":String(s)).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }
function mathHTML(s){ if(typeof katex==="undefined") return "<code>"+esc(s)+"</code>";
  try{ return katex.renderToString(String(s||""),{throwOnError:false,displayMode:true}); }
  catch(err){ return "<code>"+esc(s)+"</code>"; } }
function eqLatex(n){ const m=n.meta||{}; return (m.latex && String(m.latex).trim()) || n.label || ""; }
function chip(n){ const c=col(n); return `<span class="chip" data-go="${esc(n.id)}"><span class="dot" style="background:${c}"></span>${esc((n.label||n.id).slice(0,46))}</span>`; }
function chipsRow(label, arr){ if(!arr.length) return "";
  return `<div class="row"><div class="k">${esc(label)}</div><div class="chips">${arr.map(chip).join("")}</div></div>`; }

function select(id){ sel=id; draw();
  const n=node(id); if(!n){ return; }
  const m=n.meta||{};
  const body=document.getElementById("body");
  let html=`<div class="kind">${esc(n.kind)}${m.scope&&m.scope!=="global"?" · "+esc(m.scope):""}${m.domain&&m.domain!=="global"&&m.domain?" · "+esc(m.domain):""}</div>`;
  html+=`<h2>${esc(n.label)}</h2>`;
  if(n.link) html+=`<span class="badge">${esc(n.link)}</span>`;
  if(n.status) html+=`<span class="badge">${esc(n.status)}</span>`;
  // provenance: an outside door or a generating node id
  if(n.source){ const sn=node(n.source);
    html+=`<div class="row"><div class="k">provenance</div>`
      + (sn ? `<div class="chips">${chip(sn)}</div>` : `<span class="badge" style="background:#2c3a4d;color:#c9a96a">${esc(n.source)}</span>`)
      + `</div>`; }
  if(m.summary) html+=`<div class="row"><div class="k">summary</div><div class="summary">${esc(m.summary)}</div></div>`;
  if(m.ref) html+=`<div class="row"><div class="k">reference</div><code style="color:${ACCENT}">${esc(m.ref)}</code></div>`;
  // canon link-topology (the flat wiki graph): what this names, and who names it.
  if(FLAT){
    html += chipsRow("links to →", linksOutOf(id));
    html += chipsRow("linked from ←", linksInOf(id));
  }
  // lineage up (the talk spine)
  html += chipsRow("feeds into ↑", feedsOf(id));
  // the mathematics this node encodes (its contained equations), KaTeX-rendered
  const interior = interiorOf(id);
  const eqs = interior.filter(x=>x.kind==="equation");
  if(n.kind==="equation") html+=`<div class="row"><div class="k">mathematics</div><div class="math">${mathHTML(eqLatex(n))}</div></div>`;
  if(eqs.length){ html+=`<div class="row"><div class="k">derivation</div>`; for(const q of eqs) html+=`<div class="math">${mathHTML(eqLatex(q))}</div>`; html+=`</div>`; }
  // peers (lateral interactions): peersOf returns {n:id, rel}
  const supports = peersOf(id).filter(x=>x.rel==="supports").map(x=>node(x.n)).filter(Boolean);
  const shares = peersOf(id).filter(x=>x.rel==="shares").map(x=>node(x.n)).filter(Boolean);
  const contra = peersOf(id).filter(x=>x.rel==="contradicts").map(x=>node(x.n)).filter(Boolean);
  html += chipsRow("supports / supported by", supports);
  html += chipsRow("shares inputs with", shares);
  html += chipsRow("in tension with", contra);
  // fed from (lineage down) + other interior (objects, defs, assumptions)
  html += chipsRow("fed from ↓", drawsOf(id));
  const rest = interior.filter(x=>x.kind!=="equation");
  html += chipsRow("contains", rest);
  // parents, for an interior node reached via a chip
  const par = parentsOf(id);
  if(par.length && !MACRO_IDS.has(id)) html += chipsRow("inside", par);
  body.innerHTML = html;
  body.scrollTop = 0;
  // wire chips -> navigate
  for(const c of body.querySelectorAll("[data-go]")) c.onclick = ()=>select(c.dataset.go);
  // re-render KaTeX if it loaded late
  if(typeof katex==="undefined"){ /* katex defers; selecting again after load re-renders */ }
}

// initial: select the climax (talk -> B10 turn; wiki -> first domain) so the
// panel is populated on load and the snapshot reads as live, not empty.
function boot(){
  resize();
  const start = KIND==="talk" ? (node("B10")?"B10":(MACRO[0]&&MACRO[0].id))
                              : (MACRO.find(n=>n.kind==="domain")||MACRO[0]||{}).id;
  if(start) select(start);
}
// KaTeX is deferred; re-run the current selection once it arrives so math renders.
window.addEventListener("load", ()=>{ if(sel) select(sel); });
boot();
</script>
</body></html>
"""


def bake(graph_path: Path, out_path: Path, title: str, subtitle: str,
         kind: str, macrolabel: str, hint: str, placeholder: str, note: str) -> None:
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    graph_json = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    html = TEMPLATE
    repl = {
        "__TITLE__": title, "__MACROLABEL__": macrolabel, "__HINT__": hint,
        "__PLACEHOLDER__": placeholder, "__NOTE__": note, "__KIND__": kind,
        "__GRAPH_JSON__": graph_json,
        "__GROUP_COLOR__": json.dumps(GROUP_COLOR, separators=(",", ":")),
        "__BG__": PALETTE["bg"], "__PANEL__": PALETTE["panel"], "__INK2__": PALETTE["ink2"],
        "__LINE__": PALETTE["line"], "__INK__": PALETTE["ink"], "__DIM__": PALETTE["dim"],
        "__ACCENT__": PALETTE["accent"], "__MATH__": PALETTE["math"],
    }
    for k, v in repl.items():
        html = html.replace(k, v)
    out_path.write_text(html, encoding="utf-8")
    print(f"wrote {out_path}  ({len(html)} bytes, {len(data['nodes'])} nodes, {len(data['edges'])} edges)")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("graph_json")
    p.add_argument("out_html")
    p.add_argument("--title", required=True)
    p.add_argument("--kind", choices=["talk", "wiki"], required=True)
    p.add_argument("--macrolabel", default="")
    p.add_argument("--hint", default="")
    p.add_argument("--placeholder", default="")
    p.add_argument("--note", default="")
    a = p.parse_args()

    # The refusal fence: no readable graph means no bake. Checked BEFORE anything is
    # written, so a refusal can never leave a half-baked or clobbered <out.html> behind.
    graph = Path(a.graph_json)
    if not graph.is_file():
        print(refusal_line("GRAPH BAKE", "the input graph",
                           [f"{graph} does not exist"], verb="BAKE"), file=sys.stderr)
        return REFUSAL_EXIT
    try:
        data = json.loads(graph.read_text(encoding="utf-8"))
        missing = [k for k in ("nodes", "edges") if k not in data]
    except Exception as exc:                                       # noqa: BLE001
        print(refusal_line("GRAPH BAKE", "a readable input graph",
                           [f"{graph}: {type(exc).__name__}: {str(exc)[:160]}"], verb="BAKE"),
              file=sys.stderr)
        return REFUSAL_EXIT
    if missing:
        print(refusal_line("GRAPH BAKE", f"the graph's {'/'.join(missing)} key(s)",
                           [f"{graph} parsed, but carries no {', '.join(missing)}"], verb="BAKE"),
              file=sys.stderr)
        return REFUSAL_EXIT

    bake(graph, Path(a.out_html), a.title, "", a.kind,
         a.macrolabel, a.hint, a.placeholder, a.note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
