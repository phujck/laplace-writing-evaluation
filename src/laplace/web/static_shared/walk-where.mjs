// WALK WHERE (S2 F7). Purpose: where a paragraph sits: its place in the spine and its cross-links,
// the conceptric/storyboard joins and the linkages pane of the rail. Owns: JOIN (plan and doors) and
// LK (linkage facts). Public contract: renderLinkages, toggleWhere, blockLabels.
import store from "/shared/store.mjs";
import {$, el, text} from './walk-base.mjs';
import {D} from './walk-document.mjs';
import {
  S, jumpToBlock, jumpToIndex, keepRowInView, litNode, readingY, sectionAtY, sectionTitle
} from './walk-position.mjs';
import {C, DISPOSITIONS} from './walk-composer.mjs';
import {figLabelOf} from './walk-selection.mjs';
import {L} from './walk-band.mjs';
import {CARD, cardBlock, cardWhere, cardWhereBtn, positionCard} from './walk-card.mjs';

// ── where this sits — the paragraph's place in the spine, and its cross-links, from
// the block model itself (labels, refs, cites ride the pieces). The conceptric and
// storyboard joins are the integration leg; this view is the walk's own, always live. ──

function blockLabels(b) {
  return [].concat(b.label || [], Array.isArray(b.labels) ? b.labels : [])
    .filter((l) => typeof l === "string" && l);
}

function piecesOf(b) {
  const out = [];
  const walk = (ps) => {
    for (const p of (Array.isArray(ps) ? ps : [])) {
      if (p && typeof p === "object") {
        out.push(p);
        if (Array.isArray(p.pieces)) walk(p.pieces);
      }
    }
  };
  walk(b.pieces);
  if (Array.isArray(b.items)) {
    for (const it of b.items) {
      walk(it && it.pieces);
      walk(it && it.tail_pieces);
      if (it && it.sub) for (const s2 of (it.sub.items || [])) walk(s2 && s2.pieces);
    }
  }
  return out;
}

function whereFacts(b) {
  const sec = D.sections.find((s) => s.id === b.sectionId) || null;
  const si = sec ? D.sections.indexOf(sec) : -1;
  const paras = sec ? sec.blocks.filter((x) => (x.kind || "para") === "para") : [];
  const k = paras.indexOf(b) + 1;
  const refsOut = [], citesOut = [];
  for (const p of piecesOf(b)) {
    const t = String(p.t || p.type || "");
    if ((t === "ref" || t === "eqref" || t === "cref") && p.label) refsOut.push(String(p.label));
    if (t === "cite") for (const key of [].concat(p.keys || p.key || [])) citesOut.push(String(key));
  }
  const mine = new Set(blockLabels(b));
  const refsIn = [];
  if (mine.size) {
    for (const bb of S.blocks) {
      if (bb.id === b.id) continue;
      for (const p of piecesOf(bb)) {
        const t = String(p.t || p.type || "");
        if ((t === "ref" || t === "eqref" || t === "cref") && mine.has(String(p.label))) {
          refsIn.push({ block: bb, label: String(p.label) });
          break;
        }
      }
    }
  }
  return { sec, si, k, nParas: paras.length, refsOut: [...new Set(refsOut)],
           citesOut: [...new Set(citesOut)], refsIn, labels: [...mine] };
}

/** A label resolved to the block that DEFINES it, for the jump door. */
function blockOfLabel(label) {
  for (const bb of S.blocks) if (blockLabels(bb).includes(label)) return bb;
  return null;
}

function renderWhere(b) {
  const w = whereFacts(b);
  cardWhere.textContent = "";
  const pos = el("div", "ec-w-row");
  pos.appendChild(el("span", "ec-lead", "sits:"));
  pos.appendChild(document.createTextNode(
    (w.sec ? "§" + (w.si + 1) + " " + w.sec.title : "an unnamed section")
    + (w.k > 0 ? " · paragraph " + w.k + " of " + w.nParas : "")));
  cardWhere.appendChild(pos);
  if (w.sec && S.sections[w.si] && S.sections[w.si].el) {
    keepRowInView(S.sections[w.si].el);
    litNode(S.sections[w.si].el);
  }
  const door = (label, target) => {
    const btn = el("button", "ec-w-door", label);
    btn.type = "button";
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      if (target) jumpToBlock(target.id);
    });
    return btn;
  };
  if (w.refsOut.length || w.citesOut.length) {
    const out = el("div", "ec-w-row");
    out.appendChild(el("span", "ec-lead", "links out:"));
    for (const label of w.refsOut) {
      const tgt = blockOfLabel(label);
      const num = D.refs[label];
      out.appendChild(door((num != null ? "(" + num + ") " : "") + label, tgt));
    }
    for (const key of w.citesOut) {
      const n = D.citations[key];
      out.appendChild(el("span", "ec-w-cite", "[" + (n && n.num != null ? n.num : "?")
        + "] " + key));
    }
    cardWhere.appendChild(out);
  }
  const inRow = el("div", "ec-w-row");
  inRow.appendChild(el("span", "ec-lead", "referenced by:"));
  if (w.refsIn.length) {
    for (const r of w.refsIn) {
      const t = sectionTitle(r.block.sectionId);
      inRow.appendChild(door((t ? "§" + t : r.block.id) + " → " + r.label, r.block));
    }
  } else {
    inRow.appendChild(document.createTextNode(
      w.labels.length ? "nothing references " + w.labels.join(", ") + " yet"
                      : "this block defines no label, so nothing can reference it"));
  }
  cardWhere.appendChild(inRow);
}

// ── the conceptric / storyboard joins (clause 7, first leg). The plan door names the
// section's nodes and beats; the walk-only gate may refuse the other surfaces over this
// serving, so doors render live only where a probe says they serve — otherwise the ids
// are named as facts, which is the view he asked for. Paragraph-grain joins ride the
// instrumented nodemap — the next leg. ──────────────────────────────────────────────────

const JOIN = { plan: undefined, doors: undefined };

async function ensurePlan() {
  if (JOIN.plan !== undefined) return JOIN.plan;
  try {
    JOIN.plan = await store.fetchJSON("/shared/plan?corpus=" + encodeURIComponent(S.corpus));
  } catch (_e) {
    JOIN.plan = null;
  }
  return JOIN.plan;
}

async function ensureDoors() {
  if (JOIN.doors !== undefined) return JOIN.doors;
  try {
    const r = await fetch("/conceptric", { method: "HEAD" });
    JOIN.doors = r.ok;
  } catch (_e) {
    JOIN.doors = false;
  }
  return JOIN.doors;
}

function planSectionFor(b, plan) {
  const secs = [].concat(plan && plan.sections || [], plan && plan.appendices || []);
  const matches = b.source_section ? secs.filter(section=>section.id===b.source_section) : [];
  return matches.length===1 ? matches[0] : null;
}

async function renderJoins(b) {
  const plan = await ensurePlan();
  if (!cardWhere || cardWhere.hidden || (CARD.dataset.block !== b.id)) return;
  const row = el("div", "ec-w-row");
  if (!plan) {
    row.appendChild(el("span", "ec-lead", "joins:"));
    row.appendChild(document.createTextNode(
      "the plan door did not answer for this corpus, so no node or beat joins show."));
    cardWhere.appendChild(row);
    positionCard(b);
    return;
  }
  const sec = planSectionFor(b, plan);
  if (!sec) {
    row.appendChild(el("span", "ec-lead", "joins:"));
    row.appendChild(document.createTextNode(
      "no plan section matches this block's ids — the joins are §-grain and need one."));
    cardWhere.appendChild(row);
    positionCard(b);
    return;
  }
  const doors = await ensureDoors();
  const q = encodeURIComponent(S.corpus);
  const nodes = (sec.nodes_in_order || []).slice(0, 6);
  if (nodes.length) {
    row.appendChild(el("span", "ec-lead", "argues here (§-grain):"));
    for (const nid of nodes) {
      if (doors) {
        const a2 = el("a", "ec-w-door", nid);
        a2.href = "/conceptric?corpus=" + q + "&node=" + encodeURIComponent(nid);
        a2.rel = "noreferrer";
        row.appendChild(a2);
      } else {
        row.appendChild(el("span", "ec-w-cite", nid));
      }
    }
    const more = (sec.nodes_in_order || []).length - nodes.length;
    if (more > 0) row.appendChild(el("span", "ec-w-cite", "+" + more + " more"));
    cardWhere.appendChild(row);
  }
  const beats = sec.beats || [];
  const brow = el("div", "ec-w-row");
  brow.appendChild(el("span", "ec-lead", "beat:"));
  if (beats.length) {
    for (const bt of beats.slice(0, 3)) {
      if (doors) {
        const a3 = el("a", "ec-w-door", String(bt));
        a3.href = "/storyboard?corpus=" + q + "#" + encodeURIComponent(String(bt));
        a3.rel = "noreferrer";
        brow.appendChild(a3);
      } else {
        brow.appendChild(el("span", "ec-w-cite", String(bt)));
      }
    }
  } else {
    brow.appendChild(document.createTextNode("§" + (sec.title || sec.id)
      + " carries no beats in the plan"));
  }
  cardWhere.appendChild(brow);
  if (!doors) {
    const note = el("div", "ec-w-row");
    note.appendChild(el("span", "ec-lead", ""));
    note.appendChild(document.createTextNode(
      "the conceptric and storyboard surfaces are gated off this walk-only serving; "
      + "the ids are named for the record."));
    cardWhere.appendChild(note);
  }
  positionCard(b);
}

// ── the linkages pane — the rail's view of the paper (his pick: "a linkages pane").
// The CURRENT section's beats, nodes, refs in/out, figures, and this walk's deposits on
// it. It repaints at section boundaries and in the frame of a bank — never on a timer,
// never mid-read (the no-motion law's coarse-boundary class, same as the tints). ────────

const LK = { secId: "", facts: new Map() };
const lkBody = $("lk-body"), lkHead = $("lk-head");

function sectionLinkFacts(secId) {
  if (LK.facts.has(secId)) return LK.facts.get(secId);
  const sec = D.sections.find((s2) => s2.id === secId);
  const out = { refsOut: new Set(), cites: new Set(), labels: new Set(),
                figs: new Set(), refsIn: [] };
  if (sec) {
    for (const b of sec.blocks) {
      for (const l of blockLabels(b)) out.labels.add(l);
      const fl = figLabelOf(b);
      if (fl) out.figs.add(fl);
      for (const p2 of piecesOf(b)) {
        const t = String(p2.t || p2.type || "");
        if ((t === "ref" || t === "eqref" || t === "cref") && p2.label) {
          out.refsOut.add(String(p2.label));
        }
        if (t === "cite") for (const k of [].concat(p2.keys || p2.key || [])) {
          out.cites.add(String(k));
        }
      }
    }
    for (const s2 of D.sections) {
      if (s2.id === secId) continue;
      let hit = false;
      for (const b of s2.blocks) {
        for (const p2 of piecesOf(b)) {
          const t = String(p2.t || p2.type || "");
          if ((t === "ref" || t === "eqref" || t === "cref")
              && out.labels.has(String(p2.label))) { hit = true; break; }
        }
        if (hit) break;
      }
      if (hit) out.refsIn.push(s2);
    }
  }
  LK.facts.set(secId, out);
  return out;
}

function renderLinkages() {
  if (!lkBody) return;
  const i = S.current >= 0 ? S.current : sectionAtY(readingY());
  const sec = S.sections[i];
  if (!sec) { text(lkBody, "no section under the reading line yet."); return; }
  LK.secId = sec.id;
  lkBody.textContent = "";
  lkBody.appendChild(el("div", "lk-sec", "§" + (i + 1) + " " + sec.title));
  const facts = sectionLinkFacts(sec.id);
  const row = (lead, fill) => {
    const r = el("div", "lk-row");
    r.appendChild(el("span", "lk-lead", lead));
    fill(r);
    lkBody.appendChild(r);
  };
  const deps = C.rows.filter((r2) => r2.section === sec.id);
  row("deposits:", (r) => r.appendChild(document.createTextNode(
    deps.length ? String(deps.length) + " this walk" : "none this walk")));
  // THE RULINGS ON THIS SECTION, LISTED (WRITING-CONSOLIDATION-W1). Counted over this walk's
  // rows AND the project's ledger when it has been opened, because a keep/cut he left last
  // week rules this passage exactly as much as one he left a minute ago — and the band, by its
  // own law, holds only this walk. The line says which source it counted, so a reader is never
  // shown a partial count as a total.
  const rulings = [...deps, ...(L.loaded ? L.rows.filter((r2) => r2.section === sec.id) : [])]
    .filter((r2) => r2.disposition);
  if (rulings.length) {
    const tally = DISPOSITIONS
      .map((d) => [d, rulings.filter((r2) => r2.disposition === d).length])
      .filter(([, n]) => n);
    row("rulings:", (r) => {
      for (const [d, n] of tally) {
        const chip = el("span", "dep-ruling", d + " " + n);
        chip.dataset.ruling = d;
        r.appendChild(chip);
      }
      r.appendChild(document.createTextNode(
        L.loaded ? "  this walk and the ledger" : "  this walk (press l for the ledger)"));
    });
  }
  if (facts.refsOut.size) {
    row("refs out:", (r) => {
      for (const l of [...facts.refsOut].slice(0, 8)) {
        const tgt = blockOfLabel(l);
        const d = el("button", "lk-door", (D.refs[l] != null ? "(" + D.refs[l] + ") " : "") + l);
        d.type = "button";
        d.addEventListener("click", () => { if (tgt) jumpToBlock(tgt.id); });
        r.appendChild(d);
      }
      if (facts.refsOut.size > 8) {
        r.appendChild(el("span", "lk-chip", "+" + (facts.refsOut.size - 8)));
      }
    });
  }
  row("referenced by:", (r) => {
    if (!facts.refsIn.length) {
      r.appendChild(document.createTextNode(
        facts.labels.size ? "no other section references this one's labels"
                          : "this section defines no labels"));
      return;
    }
    for (const s2 of facts.refsIn) {
      const j = D.sections.indexOf(s2);
      const d = el("button", "lk-door", "§" + (j + 1) + " " + s2.title);
      d.type = "button";
      d.addEventListener("click", () => { if (j >= 0) jumpToIndex(j); });
      r.appendChild(d);
    }
  });
  if (facts.cites.size) {
    row("cites:", (r) => r.appendChild(document.createTextNode(
      String(facts.cites.size) + " key" + (facts.cites.size === 1 ? "" : "s"))));
  }
  if (facts.figs.size) {
    row("figures:", (r) => {
      for (const f of facts.figs) r.appendChild(el("span", "lk-chip", f));
    });
  }
  renderLinkJoins(sec);
}

async function renderLinkJoins(sec) {
  const plan = await ensurePlan();
  if (!plan || LK.secId !== sec.id || !lkBody) return;
  const dsec = D.sections.find((s2) => s2.id === sec.id);
  const sourceSections = [...new Set((dsec?.blocks || []).map(block=>block.source_section).filter(Boolean))];
  const psec = sourceSections.length===1 ? planSectionFor({source_section:sourceSections[0]},plan) : null;
  const r = el("div", "lk-row");
  r.appendChild(el("span", "lk-lead", "plan:"));
  if (!psec) {
    r.appendChild(document.createTextNode("no plan section matches this one"));
  } else {
    const beats = (psec.beats || []).slice(0, 3);
    const nodes = psec.nodes_in_order || [];
    r.appendChild(document.createTextNode(
      (beats.length ? "beats " + beats.join(" · ") : "no beats")
      + " · " + nodes.length + " node" + (nodes.length === 1 ? "" : "s") + " argue here"));
  }
  lkBody.appendChild(r);
}

function toggleWhere() {
  const b = cardBlock();
  if (!b || !cardWhere) return;
  if (cardWhere.hidden) {
    renderWhere(b);
    cardWhere.hidden = false;
    text(cardWhereBtn, "close the links view");
    renderJoins(b);
  } else {
    cardWhere.hidden = true;
    text(cardWhereBtn, "where this sits · links");
  }
  positionCard(b);
}

export {LK, blockLabels, renderLinkages, toggleWhere};
