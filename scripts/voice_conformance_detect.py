#!/usr/bin/env python3
"""voice_conformance_detect.py -- the meso/macro authorial-conformance DETECTOR.

His durable brief (FEEDBACK_2026-07-11_voice-altitudes-authorial-conformance.md): the local
voice washer succeeds at the lexical/sentential level, but a manuscript can be "locally voiced
while remaining mesoscopically or macroscopically alien" -- sections perform the wrong job,
supporting machinery becomes more prominent than the central contribution, presentation order
contradicts dependency order. The future high-altitude pass "would identify mismatches between
conceptual importance and rhetorical prominence, between dependency and order of presentation,
and between evidential status and prose emphasis."

This is the DETECTOR half of that: the mechanical core that reads the two structures the brief
names -- the SEMANTIC/conceptric structure (concepts, claims, defs, draws dependencies, spine,
thesis) and the RHETORICAL/storyboard structure (what is introduced when, section order, how
much space each idea receives, opening/closing slots) -- and emits TYPED findings wherever the
two rank-orders disagree beyond a threshold. It calls no model. It gates NOTHING: it is an
advisory feed to the author's editor pass and the storyboard. The acceptance-law swap and any
auto-apply of a structural patch are the AUTHOR'S fork; this tool only surfaces the mismatch.

Two substrates per section:
  SUBSTRATE importance (from the conceptric + plan):
    - contribution mass  : count of member nodes of kind result/claim (the load-bearing content)
    - draws in-degree    : how heavily the section's member nodes are drawn-upon (foundational)
    - beat count         : storyboard beats allocated to the section
    - thesis proximity   : lexical overlap of the section's job + node labels with the spine thesis
  RHETORICAL prominence (from the linear order + realised prose, degrading to plan-level):
    - prose mass         : words in the realised section .tex (or, rung-one, the plan-space proxy
                           = beats + job length when no prose exists yet)
    - position           : front-weight with a closing boost (opening and conclusion carry weight)
    - slot occupancy     : opening slot (first body section) / closing slot (last body section)

Finding kinds (each: {kind, section, node?, importance_rank, prominence_rank, delta, evidence}):
    buried-lead          : high substrate importance, low rhetorical prominence
                           (delta = prominence_rank - importance_rank >= threshold)
    inflated-minor       : low importance, high prominence
                           (delta = importance_rank - prominence_rank >= threshold)
    dependency-inversion : a node is presented before the node it draws (dependency) is
                           established -- reuses the draws edges / reader_state introduce order
    mass-mismatch        : prose-mass rank far from importance rank (prose corpora only)
                           (delta = prose_mass_rank - importance_rank, |delta| >= threshold)

Ranks are 1-based, 1 = highest. Abstract and appendices are excluded from the ranked comparison
set (their rhetorical role is structurally fixed) but reported in the table for context.

VERDICT sentinel (scripts/paper_gates.py convention): the LAST line is
    VERDICT=FINDINGS n=<K>    or    VERDICT=CLEAN
mirrored NOWHERE in the exit code -- this tool never fails; exit is always 0.

Usage:
    python scripts/voice_conformance_detect.py --corpus paper_falqon/manuscript [--table]
    python scripts/voice_conformance_detect.py --corpus eigenengine/manuscript --out report.json
    # explicit overrides:
    python scripts/voice_conformance_detect.py --plan P.json --conceptric C.json \
        [--reader-state R.json] [--manuscript-dir DIR] [--threshold N] [--table] [--out F]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from collections import Counter, defaultdict

# ---------------------------------------------------------------------------- #
# tokenisation for thesis proximity (stdlib only, no embeddings)
# ---------------------------------------------------------------------------- #
_STOP = frozenset("""
a an the of to in on for and or but with as at by from is are was were be been being it its this
that these those which who whom whose what when where how why all any each not no nor so than then
into over under out up down off we our you your they their he she his her i me my one two three
""".split())

_WORD = re.compile(r"[A-Za-z][A-Za-z_]{2,}")


def _tokens(text: str) -> set[str]:
    return {w for w in (m.group(0).lower() for m in _WORD.finditer(text or "")) if w not in _STOP}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _norm(values: dict[str, float]) -> dict[str, float]:
    """min-max normalise a {section: value} map to [0,1]; degenerate -> 0.5."""
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi - lo < 1e-12:
        return {k: 0.5 for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def _ranks(scores: dict[str, float]) -> dict[str, int]:
    """1-based dense-ish rank, 1 = highest score. Ties broken by section id for determinism."""
    order = sorted(scores, key=lambda k: (-scores[k], k))
    return {k: i + 1 for i, k in enumerate(order)}


# ---------------------------------------------------------------------------- #
# loading
# ---------------------------------------------------------------------------- #
def _load(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _resolve_corpus(args) -> dict:
    """Resolve plan / conceptric / reader_state / manuscript-dir from --corpus or overrides."""
    mdir = args.manuscript_dir or args.corpus
    plan_path = args.plan or (os.path.join(mdir, "projection_plan.json") if mdir else None)
    con_path = args.conceptric or (os.path.join(mdir, "conceptric_v1.json") if mdir else None)
    rs_path = args.reader_state
    if rs_path is None and mdir:
        cand = os.path.join(mdir, "reader_state.json")
        rs_path = cand if os.path.exists(cand) else None
    if not plan_path or not os.path.exists(plan_path):
        raise SystemExit(f"projection plan not found: {plan_path}")
    if not con_path or not os.path.exists(con_path):
        raise SystemExit(f"conceptric not found: {con_path}")
    return {"mdir": mdir, "plan": plan_path, "con": con_path, "rs": rs_path}


# ---------------------------------------------------------------------------- #
# prose mass
# ---------------------------------------------------------------------------- #
_COMMENT = re.compile(r"(?<!\\)%.*$", re.MULTILINE)


def _prose_words(text: str) -> int:
    text = _COMMENT.sub("", text)
    # strip latex command tokens so counts approximate spoken words, not markup
    text = re.sub(r"\\[A-Za-z@]+\*?", " ", text)
    text = re.sub(r"[{}\[\]$&~^_\\]", " ", text)
    return len(re.findall(r"[A-Za-z0-9]+", text))


def _prose_for_section(mdir: str, sec_id: str) -> int | None:
    """Return prose word count for a section, or None if no realised prose file exists."""
    if not mdir:
        return None
    stem = sec_id.split(":", 1)[-1]  # 'sec:gaps' -> 'gaps', 's1' -> 's1'
    for cand in (sec_id, stem, sec_id.replace(":", "_")):
        p = os.path.join(mdir, f"{cand}.tex")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as fh:
                return _prose_words(fh.read())
    return None


# ---------------------------------------------------------------------------- #
# core analysis
# ---------------------------------------------------------------------------- #
def _is_structural(sec_id: str) -> bool:
    """abstract / appendices: rhetorically fixed role, excluded from the ranked comparison."""
    low = sec_id.lower()
    return "abstract" in low or "appendix" in low or "appendices" in low


def analyse(plan: dict, con: dict, reader_state: dict | None, mdir: str,
            threshold: int | None) -> dict:
    nodes = {n["id"]: n for n in con.get("nodes", [])}
    edges = con.get("edges", [])

    # thesis: the spine domain node's meta.thesis (both corpora carry blueprint:spine)
    thesis = ""
    for n in con.get("nodes", []):
        th = (n.get("meta") or {}).get("thesis")
        if th:
            thesis = th
            if "spine" in n["id"]:
                break
    thesis_tok = _tokens(thesis)

    # draws in-degree: how many nodes DRAW (depend on) a given node -> foundational weight
    draws_indeg: Counter[str] = Counter()
    draws_edges = []
    for e in edges:
        if e.get("rel") == "draws":
            draws_indeg[e["dst"]] += 1
            draws_edges.append((e["src"], e["dst"]))

    sections = plan.get("sections", [])
    order_index = {s["id"]: i for i, s in enumerate(sections)}

    # node -> section membership (from the storyboard: nodes_in_order + beats)
    node_section: dict[str, str] = {}
    for s in sections:
        members = list(s.get("nodes_in_order") or []) + list(s.get("beats") or [])
        for nid in members:
            node_section.setdefault(nid, s["id"])

    body = [s for s in sections if not _is_structural(s["id"])]
    body_ids = [s["id"] for s in body]
    M = len(body)

    # --- per-section raw substrate + prominence components --------------------
    prose_words: dict[str, int | None] = {}
    prose_any = False
    contribution: dict[str, float] = {}
    drawsdeg: dict[str, float] = {}
    beats: dict[str, float] = {}
    thesisprox: dict[str, float] = {}
    planmass: dict[str, float] = {}

    body_positions = {sid: i for i, sid in enumerate(body_ids)}

    for s in body:
        sid = s["id"]
        members = list(s.get("nodes_in_order") or []) + list(s.get("beats") or [])
        umembers = list(dict.fromkeys(members))
        contribution[sid] = sum(1 for m in umembers
                                if nodes.get(m, {}).get("kind") in ("result", "claim"))
        drawsdeg[sid] = float(sum(draws_indeg.get(m, 0) for m in umembers))
        beats[sid] = float(len(s.get("beats") or []))
        sec_tok = _tokens(s.get("job", ""))
        for m in umembers:
            sec_tok |= _tokens(nodes.get(m, {}).get("label", ""))
        thesisprox[sid] = _jaccard(sec_tok, thesis_tok)
        pw = _prose_for_section(mdir, sid)
        prose_words[sid] = pw
        if pw is not None:
            prose_any = True
        # plan-level space proxy (rung-one degrade): beats allocation + job brief length
        planmass[sid] = len(s.get("beats") or []) + len(s.get("job", "")) / 200.0

    # corpus counts as prose-bearing only if MOST body sections have realised prose
    n_prose = sum(1 for sid in body_ids if prose_words.get(sid) is not None)
    prose_available = prose_any and n_prose >= max(1, (M + 1) // 2)

    # --- composite importance -------------------------------------------------
    c_n = _norm(contribution)
    d_n = _norm(drawsdeg)
    b_n = _norm(beats)
    t_n = _norm(thesisprox)
    importance = {sid: 0.35 * t_n[sid] + 0.25 * c_n[sid] + 0.20 * d_n[sid] + 0.20 * b_n[sid]
                  for sid in body_ids}

    # --- composite prominence -------------------------------------------------
    # position: front-weight with a closing boost
    position_raw: dict[str, float] = {}
    slot: dict[str, float] = {}
    for sid in body_ids:
        i = body_positions[sid]
        front = 1.0 - (i / (M - 1) if M > 1 else 0.0)
        closing = 1.0 if i == M - 1 else 0.0
        position_raw[sid] = max(front, 0.8 * closing)
        slot[sid] = 1.0 if (i == 0 or i == M - 1) else 0.0
    pos_n = _norm(position_raw)
    slot_n = _norm(slot)

    if prose_available:
        mass_raw = {sid: float(prose_words.get(sid) or 0) for sid in body_ids}
    else:
        mass_raw = dict(planmass)
    mass_n = _norm(mass_raw)
    prominence = {sid: 0.55 * mass_n[sid] + 0.30 * pos_n[sid] + 0.15 * slot_n[sid]
                  for sid in body_ids}

    imp_rank = _ranks(importance)
    prom_rank = _ranks(prominence)
    mass_rank = _ranks(mass_raw)

    if threshold is None:
        threshold = max(2, round(M * 0.34))

    titles = {s["id"]: s.get("title", s["id"]) for s in sections}

    # ---------------------------------------------------------------------- #
    # findings
    # ---------------------------------------------------------------------- #
    findings: list[dict] = []

    for sid in body_ids:
        ir, pr = imp_rank[sid], prom_rank[sid]
        # buried-lead: important but under-prominent
        if pr - ir >= threshold:
            findings.append({
                "kind": "buried-lead", "section": sid, "node": None,
                "importance_rank": ir, "prominence_rank": pr, "delta": pr - ir,
                "evidence": (f"'{titles[sid]}' ranks #{ir}/{M} in substrate importance "
                             f"(thesis-prox {thesisprox[sid]:.2f}, {int(contribution[sid])} "
                             f"claim/result nodes, draws-indeg {int(drawsdeg[sid])}) but only "
                             f"#{pr}/{M} in rhetorical prominence "
                             f"({'prose ' + str(prose_words.get(sid)) + 'w' if prose_available else 'plan-mass ' + f'{planmass[sid]:.1f}'}, "
                             f"position #{body_positions[sid] + 1}/{M}).")
            })
        # inflated-minor: prominent but unimportant
        if ir - pr >= threshold:
            findings.append({
                "kind": "inflated-minor", "section": sid, "node": None,
                "importance_rank": ir, "prominence_rank": pr, "delta": ir - pr,
                "evidence": (f"'{titles[sid]}' ranks #{pr}/{M} in rhetorical prominence "
                             f"({'prose ' + str(prose_words.get(sid)) + 'w' if prose_available else 'plan-mass ' + f'{planmass[sid]:.1f}'}, "
                             f"position #{body_positions[sid] + 1}/{M}) but only #{ir}/{M} in "
                             f"substrate importance (thesis-prox {thesisprox[sid]:.2f}, "
                             f"{int(contribution[sid])} claim/result nodes).")
            })
        # mass-mismatch: prose mass far from importance (prose corpora only)
        if prose_available:
            mr = mass_rank[sid]
            d = mr - ir
            if abs(d) >= threshold:
                dirn = "under-massed" if d > 0 else "over-massed"
                findings.append({
                    "kind": "mass-mismatch", "section": sid, "node": None,
                    "importance_rank": ir, "prominence_rank": mr, "delta": d,
                    "evidence": (f"'{titles[sid]}' carries prose mass rank #{mr}/{M} "
                                 f"({prose_words.get(sid)}w) against importance rank #{ir}/{M} "
                                 f"-- {dirn} by {abs(d)} ranks.")
                })

    # dependency-inversion: a node drawn upon (dependency) is established AFTER the node
    # that draws it. Reuse the draws edges mapped through storyboard membership.
    seen_inv: set[tuple] = set()
    for src, dst in draws_edges:
        s_sec, d_sec = node_section.get(src), node_section.get(dst)
        if not s_sec or not d_sec or s_sec == d_sec:
            continue
        if _is_structural(s_sec) or _is_structural(d_sec):
            continue
        si, di = order_index.get(s_sec), order_index.get(d_sec)
        if si is None or di is None:
            continue
        if si < di:  # dependent src appears before its dependency dst
            key = (src, dst)
            if key in seen_inv:
                continue
            seen_inv.add(key)
            gap = di - si
            if gap >= 1:  # any forward dependency across sections is an inversion
                findings.append({
                    "kind": "dependency-inversion", "section": s_sec, "node": src,
                    "importance_rank": imp_rank.get(s_sec), "prominence_rank": prom_rank.get(s_sec),
                    "delta": gap,
                    "evidence": (f"node '{src}' (in {s_sec}, '{titles.get(s_sec, s_sec)}') "
                                 f"draws '{dst}' which is only established later in "
                                 f"{d_sec} ('{titles.get(d_sec, d_sec)}') -- presentation "
                                 f"precedes dependency by {gap} section(s).")
                })

    # secondary inversion source: reader_state introduce/use order (cross-section, body only)
    if reader_state:
        for nid, rec in (reader_state.get("nodes") or {}).items():
            intro = rec.get("introduced")
            if not intro or _is_structural(intro):
                continue
            ii = order_index.get(intro)
            if ii is None:
                continue
            for use in rec.get("uses") or []:
                if _is_structural(use):
                    continue
                ui = order_index.get(use)
                if ui is None or ui >= ii:
                    continue
                key = ("rs", nid, use)
                if key in seen_inv:
                    continue
                seen_inv.add(key)
                findings.append({
                    "kind": "dependency-inversion", "section": use, "node": nid,
                    "importance_rank": imp_rank.get(use), "prominence_rank": prom_rank.get(use),
                    "delta": ii - ui,
                    "evidence": (f"node '{nid}' is used in {use} but not introduced until "
                                 f"{intro} -- used {ii - ui} section(s) before it is established "
                                 f"(reader_state).")
                })

    findings.sort(key=lambda f: (-abs(f["delta"]), f["kind"], f["section"]))

    # per-section table rows
    rows = []
    for s in sections:
        sid = s["id"]
        if sid in importance:
            rows.append({
                "section": sid, "title": titles[sid], "structural": False,
                "position": body_positions[sid] + 1,
                "importance": round(importance[sid], 3), "importance_rank": imp_rank[sid],
                "prominence": round(prominence[sid], 3), "prominence_rank": prom_rank[sid],
                "thesis_proximity": round(thesisprox[sid], 3),
                "contribution_nodes": int(contribution[sid]),
                "draws_indeg": int(drawsdeg[sid]),
                "beats": int(beats[sid]),
                "prose_words": prose_words.get(sid),
                "plan_mass": round(planmass[sid], 2),
            })
        else:
            rows.append({"section": sid, "title": titles[sid], "structural": True,
                         "prose_words": _prose_for_section(mdir, sid)})

    return {
        "corpus": plan.get("meta", {}).get("project", mdir or "unknown"),
        "generated": _dt.date.today().isoformat(),
        "thesis_present": bool(thesis),
        "prose_available": prose_available,
        "n_body_sections": M,
        "threshold": threshold,
        "sections": rows,
        "findings": findings,
        "summary": {
            "n_findings": len(findings),
            "by_kind": dict(Counter(f["kind"] for f in findings)),
        },
    }


# ---------------------------------------------------------------------------- #
# rendering
# ---------------------------------------------------------------------------- #
def render_table(rep: dict) -> str:
    out = []
    out.append(f"# voice-conformance: {rep['corpus']}  "
               f"(prose={'yes' if rep['prose_available'] else 'plan-level'}, "
               f"threshold={rep['threshold']})")
    out.append("")
    hdr = f"{'section':<16}{'pos':>4}{'imp#':>6}{'prom#':>6}{'thes':>6}{'c/r':>5}{'draws':>7}{'beats':>7}{'mass':>8}"
    out.append(hdr)
    out.append("-" * len(hdr))
    for r in rep["sections"]:
        if r.get("structural"):
            mass = r.get("prose_words")
            out.append(f"{r['section']:<16}{'--':>4}{'--':>6}{'--':>6}{'--':>6}{'--':>5}"
                       f"{'--':>7}{'--':>7}{(str(mass) if mass is not None else '--'):>8}  (structural)")
            continue
        mass = r["prose_words"] if r["prose_words"] is not None else f"~{r['plan_mass']}"
        out.append(f"{r['section']:<16}{r['position']:>4}{r['importance_rank']:>6}"
                   f"{r['prominence_rank']:>6}{r['thesis_proximity']:>6.2f}"
                   f"{r['contribution_nodes']:>5}{r['draws_indeg']:>7}{r['beats']:>7}{str(mass):>8}")
    out.append("")
    out.append(f"## findings ({rep['summary']['n_findings']}): {rep['summary']['by_kind']}")
    for f in rep["findings"]:
        node = f" node={f['node']}" if f.get("node") else ""
        out.append(f"  [{f['kind']}] {f['section']}{node} "
                   f"(imp#{f['importance_rank']} prom#{f['prominence_rank']} delta={f['delta']})")
        out.append(f"       {f['evidence']}")
    return "\n".join(out)


# ---------------------------------------------------------------------------- #
# main
# ---------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="meso/macro authorial-conformance detector (advisory)")
    ap.add_argument("--corpus", help="manuscript dir (auto-finds plan/conceptric/reader_state)")
    ap.add_argument("--plan", help="projection_plan.json (override)")
    ap.add_argument("--conceptric", help="conceptric_v1.json (override)")
    ap.add_argument("--reader-state", dest="reader_state", help="reader_state.json (override)")
    ap.add_argument("--manuscript-dir", dest="manuscript_dir", help="dir holding the realised .tex")
    ap.add_argument("--threshold", type=int, default=None, help="rank-delta threshold (default ~0.34*N)")
    ap.add_argument("--out", help="write the JSON report to this path")
    ap.add_argument("--table", action="store_true", help="print the human table to stderr")
    args = ap.parse_args(argv)

    if not (args.corpus or (args.plan and args.conceptric)):
        ap.error("provide --corpus, or both --plan and --conceptric")

    paths = _resolve_corpus(args)
    plan = _load(paths["plan"])
    con = _load(paths["con"])
    reader_state = _load(paths["rs"]) if paths["rs"] else None

    rep = analyse(plan, con, reader_state, paths["mdir"], args.threshold)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, indent=2)
            fh.write("\n")

    if args.table:
        sys.stderr.write(render_table(rep) + "\n")

    json.dump(rep, sys.stdout, indent=2)
    sys.stdout.write("\n")

    n = rep["summary"]["n_findings"]
    print(f"VERDICT=FINDINGS n={n}" if n else "VERDICT=CLEAN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
