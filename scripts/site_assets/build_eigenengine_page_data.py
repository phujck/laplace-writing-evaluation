#!/usr/bin/env python3
"""build_eigenengine_page_data.py — the ONE data file behind the eigenengine page's
visual exhibits (his ruling 2026-07-23: every asset a mini information-design project,
derived from real repo data by a generator, never hand-drawn).

Emits ``assets/js/eigenengine-page-data.js`` in the site clone: ``window.EE = {...}``.
The page's own JS draws every exhibit FROM this object, so a drawing cannot disagree
with the data, and a re-run against a moved tree refreshes every number at once.

Exhibits carried (falqon = the demo subject, per the tour ruling):
  hourglass   the production walk with real stage counts (corpus → conceptric →
              storyboard → converge → artefact)
  gates       the harnessed-loop gate matrix: per-round detector verdicts + open
              findings count. HONESTY NOTE: falqon's loop has NOT converged — findings
              RISE across rounds as the detector suite widens, and the loop refuses to
              lock while hard gates fail. The exhibit states that; it does not draw a
              triumphant descent that never happened.
  conceptric  the real concept graph (nodes/edges/kinds) for the static render
  lineage     the joins band (concepts realised / objects traced / equations resolved /
              the unresolved band) + one concrete claim thread

Sources: conceptric_v1.json, rounds/harnessed/detect_*.json (on disk), and the live
scanner's /storyboard, /artefact, /review, /lineage reads (the same bake-by-crawl
idiom as export_demo; the scanner is raised on demand). Volatile stamp-times are
frozen to the bake commit — reruns at the same commit are byte-stable.

    python scripts/site_assets/build_eigenengine_page_data.py [--out <site>/assets/js/...]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import export_demo as ed  # noqa: E402 — the crawl idiom + guards, reused

CORPUS = "paper_falqon"
DEFAULT_OUT = ROOT.parent / "phujck.github.io" / "assets" / "js" / "eigenengine-page-data.js"
HARNESSED = ROOT / "paper_falqon" / "manuscript" / "rounds" / "harnessed"


def _get_json(port: int, path: str, params: dict) -> dict | list | None:
    key = ed._canon(path, params)
    status, body, _ = ed._http_get(port, key)
    if status != 200:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None


def build_gate_matrix() -> dict:
    """rounds × detector-labels truth table from the loop's own detect records.
    post_rN = the state after round N's fixing pass (pre_r1 = the starting state)."""
    rows = []
    for p in sorted(HARNESSED.glob("detect_*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        rows.append({
            "phase": d.get("phase"), "round": d.get("round"),
            "open_findings": d.get("open_findings_n"),
            "hard_failing": bool(d.get("hard_failing")),
            "labels": d.get("labels") or {},
        })
    rows.sort(key=lambda r: (r["round"], 0 if r["phase"] == "pre" else 1))
    # one row per round: the post state (plus the pre state of round 1 as the start)
    series = [r for r in rows if r["phase"] == "post" or (r["phase"] == "pre" and r["round"] == 1)]
    gates = sorted({g for r in series for g in r["labels"]})
    post_rounds = sorted(r["round"] for r in series if r["phase"] == "post")
    last_round = post_rounds[-1] if post_rounds else 0
    missing = [f"r{n}" for n in range(1, last_round + 1) if n not in post_rounds]
    return {
        "gates": gates,
        "rounds": [{"label": ("start" if r["phase"] == "pre" else f"r{r['round']}"),
                    "open_findings": r["open_findings"],
                    "hard_failing": r["hard_failing"],
                    "clean": {g: bool(r["labels"].get(g)) for g in gates}} for r in series],
        "last_round": last_round,
        "missing_rounds": missing,   # rounds run without a banked post-detect record
        "converged": False,
        "note": ("findings rise across rounds because the detector suite widens as it "
                 "learns the manuscript; the loop refuses to lock while any hard gate "
                 "fails"),
    }


def _layout(nodes: list[dict], edges: list[dict], w: float = 1000.0, h: float = 620.0,
            iters: int = 260) -> None:
    """Deterministic force layout, computed HERE so the page draws dots — it never runs
    physics. Seeded by node id (no randomness), spring on edges, repulsion between all
    pairs, mild pull toward the canvas centre. 91 nodes — plain Python is plenty."""
    import hashlib
    import math

    idx = {n["id"]: i for i, n in enumerate(nodes)}
    pos = []
    for n in nodes:
        hsh = int(hashlib.sha1(n["id"].encode()).hexdigest()[:12], 16)
        a = (hsh % 62832) / 10000.0
        r = 0.18 + ((hsh >> 16) % 1000) / 2400.0
        pos.append([w / 2 + math.cos(a) * r * w / 2.6, h / 2 + math.sin(a) * r * h / 2.6])
    links = [(idx[e["src"]], idx[e["dst"]]) for e in edges
             if e["src"] in idx and e["dst"] in idx]
    for it in range(iters):
        t = 1.0 - it / iters
        disp = [[0.0, 0.0] for _ in nodes]
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                dx = pos[i][0] - pos[j][0]
                dy = pos[i][1] - pos[j][1]
                d2 = dx * dx + dy * dy + 0.01
                f = 3400.0 / d2
                disp[i][0] += dx * f; disp[i][1] += dy * f
                disp[j][0] -= dx * f; disp[j][1] -= dy * f
        for i, j in links:
            dx = pos[i][0] - pos[j][0]
            dy = pos[i][1] - pos[j][1]
            d = math.sqrt(dx * dx + dy * dy) + 0.01
            f = (d - 74.0) * 0.015
            disp[i][0] -= dx / d * f * d; disp[i][1] -= dy / d * f * d
            disp[j][0] += dx / d * f * d; disp[j][1] += dy / d * f * d
        for i in range(len(nodes)):
            disp[i][0] += (w / 2 - pos[i][0]) * 0.035
            disp[i][1] += (h / 2 - pos[i][1]) * 0.035 * (w / h)
            m = math.sqrt(disp[i][0] ** 2 + disp[i][1] ** 2) + 1e-9
            step = min(m, 22.0 * t + 1.5)
            pos[i][0] += disp[i][0] / m * step
            pos[i][1] += disp[i][1] / m * step
            pos[i][0] = min(w - 24, max(24, pos[i][0]))
            pos[i][1] = min(h - 24, max(24, pos[i][1]))
    for n, p in zip(nodes, pos):
        n["x"] = round(p[0], 1)
        n["y"] = round(p[1], 1)


def build(out: Path, port: int) -> dict:
    ed._ensure_scanner(port)
    meta = ed._bake_meta()

    # ── conceptric (from the same F4-ruled source the demo bakes) ──
    cv = json.loads((ROOT / "paper_falqon" / "manuscript" / "conceptric_v1.json")
                    .read_text(encoding="utf-8"))
    nodes = [{"id": n["id"], "kind": n.get("kind", ""), "label": n.get("label", n["id"]),
              "group": n.get("group", ""), "weight": n.get("weight", 1)}
             for n in cv.get("nodes", [])]
    edges = [{"src": e["src"], "dst": e["dst"], "rel": e.get("rel", "")}
             for e in cv.get("edges", [])]
    health = json.loads((ROOT / "paper_falqon" / "manuscript" / "conceptric_health.json")
                        .read_text(encoding="utf-8"))
    health = health.get("connectivity") or health   # def_orphans moved under connectivity
    kinds: dict[str, int] = {}
    for n in nodes:
        kinds[n["kind"]] = kinds.get(n["kind"], 0) + 1
    _layout(nodes, edges)

    # ── storyboard / artefact / lineage numbers (live reads, then frozen) ──
    plan = _get_json(port, "/storyboard/plan", {"corpus": CORPUS}) or {}
    ctx = _get_json(port, "/artefact/context", {"corpus": CORPUS}) or {}
    findings = _get_json(port, "/review/findings", {"corpus": CORPUS}) or {}
    versions = _get_json(port, "/shared/versions", {"corpus": CORPUS}) or {}
    lin = _get_json(port, "/lineage/whole", {"corpus": CORPUS}) or {}
    lin_brief = _get_json(port, "/lineage/brief", {"corpus": CORPUS}) or {}

    art = (ctx.get("current_artefact") or {})
    n_sections = len(plan.get("sections") or [])
    n_appendices = len(plan.get("appendices") or [])
    f_counts = (findings.get("counts") or {}) if isinstance(findings, dict) else {}
    n_findings = f_counts.get("total")
    n_versions = len(versions.get("rows") or []) if isinstance(versions, dict) else None

    data = {
        "meta": {**meta, "generator": "scripts/site_assets/build_eigenengine_page_data.py"},
        "hourglass": {
            "corpus": {"label": "corpus",
                       "detail": "manuscript sources, numerics readings, feedback ledgers"},
            "conceptric": {"label": "conceptric", "nodes": len(nodes), "edges": len(edges),
                           "def_orphans": len(health.get("def_orphans") or [])},
            "storyboard": {"label": "storyboard", "sections": n_sections,
                           "appendices": n_appendices},
            "converge": {"label": "converge", "rounds": None,   # filled from gates below
                         "open_findings": None, "locked": False},
            "artefact": {"label": "artefact", "version": art.get("version_id"),
                         "kind": art.get("kind"), "versions": n_versions,
                         "findings": n_findings, "findings_counts": f_counts},
        },
        "gates": build_gate_matrix(),
        "conceptric": {"nodes": nodes, "edges": edges, "kinds": kinds,
                       "def_orphans": health.get("def_orphans") or []},
        "lineage": {"whole": ed._stabilize(lin, meta["bake_iso"]),
                    "brief": ed._stabilize(lin_brief, meta["bake_iso"])},
    }
    g = data["gates"]["rounds"]
    data["hourglass"]["converge"]["rounds"] = data["gates"]["last_round"]
    data["hourglass"]["converge"]["open_findings"] = g[-1]["open_findings"] if g else None
    data["hourglass"]["converge"]["last_label"] = g[-1]["label"] if g else None

    payload = "window.EE = " + json.dumps(data, ensure_ascii=False, sort_keys=True,
                                          separators=(",", ":")) + ";\n"
    ed._seal_law_scan("eigenengine-page-data.js", payload)
    ed._ssg_guard("eigenengine-page-data.js", payload)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload, encoding="utf-8")
    return {"out": str(out), "bytes": len(payload),
            "nodes": len(nodes), "edges": len(edges), "sections": n_sections,
            "rounds": data["hourglass"]["converge"]["rounds"],
            "open_findings": data["hourglass"]["converge"]["open_findings"],
            "version": art.get("version_id")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--port", type=int, default=ed.DEFAULT_PORT)
    a = ap.parse_args()
    try:
        rep = build(Path(a.out), a.port)
    except (ed.SealViolation, ed.SSGViolation) as e:
        print(f"GUARD VIOLATION — refused to build: {e}", file=sys.stderr)
        return 2
    print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
