"""Coherence audit for a conceptric (canon://skills/conceptric_coherence).

The conceptric is a living multi-scale object. A review of the draft is a demand for
structure in the conceptric, and the iteration is done only when the object reaches a
*self-consistency fixed point*: every coarse node is **completely described by the nodes
at the level below it**. A claim (a "what") is described by the result it realises and the
terms it uses; a result is described by a why (an author guess) and a how (a model prior);
a motive is described by the guess it serves; a reader requirement is real only when some
node is wired to satisfy it.

This script measures that, so "the conceptric grew" can be told apart from "the conceptric
got bigger". More nodes is not more integration. The score is the fraction of coarse nodes
whose description below them is complete, averaged over the levels.

It does NOT judge whether the physics is right - it judges whether the object is
self-consistent, the precondition for growing a draft from it.

Usage:
    python conceptric_coherence.py <conceptric_graph.json> [<other.json> ...] [--json]
"""

from __future__ import annotations

import json
import sys

# Group buckets, for the why/how check on a result shell.
_AUTHOR = {"endogenous"}          # the why (guesses, intents)
_MODEL = {"intrinsic"}            # the how (priors)
_DOORS = {"endogenous", "intrinsic", "exogenous", "reader", "glossary"}


def _load(path):
    return json.load(open(path, encoding="utf-8"))


def audit(g: dict) -> dict:
    nodes = {n["id"]: n for n in g["nodes"]}
    edges = g["edges"]

    def grp(nid):
        n = nodes.get(nid) or {}
        return n.get("group") or n.get("kind")

    # outgoing draws (what a node is fed from, downward) and all non-contains touches
    draws_out = {nid: [] for nid in nodes}
    touched = set()
    for e in edges:
        if e["rel"] == "draws":
            draws_out.setdefault(e["src"], []).append(e["dst"])
        if e["rel"] != "contains":
            touched.add(e["src"])
            touched.add(e["dst"])

    kinds = {}
    for n in nodes.values():
        kinds.setdefault(n["kind"], []).append(n["id"])

    shells = kinds.get("node", [])         # R_* result shells
    claims = kinds.get("claim", [])
    reqs = kinds.get("req", [])
    defs = kinds.get("def", [])
    figures = kinds.get("figure", [])
    sections = kinds.get("section", [])

    checks: dict[str, tuple[int, int, list]] = {}

    # 1. A result shell is described by >= 2 finer nodes.
    ok, gaps = 0, []
    for s in shells:
        if len(draws_out.get(s, [])) >= 2:
            ok += 1
        else:
            gaps.append(s)
    checks["shells_composed (>=2 draws)"] = (ok, len(shells), gaps)

    # 2. A result shell is described by a why (author) AND a how (model).
    ok, gaps = 0, []
    for s in shells:
        gs = {grp(d) for d in draws_out.get(s, [])}
        # a shell that draws from another shell inherits via that shell; count direct here
        if gs & _AUTHOR and gs & _MODEL:
            ok += 1
        else:
            gaps.append(s)
    checks["shells_why_and_how"] = (ok, len(shells), gaps)

    # 3. Every claim resolves to an existing result shell.
    ok, gaps = 0, []
    for c in claims:
        r = (nodes[c].get("meta") or {}).get("result")
        if r and r in nodes:
            ok += 1
        else:
            gaps.append(c)
    checks["claims_grounded (result exists)"] = (ok, len(claims), gaps)

    # 4. Every claim's terms are grounded: if the claim text names a glossary term,
    #    the claim must draw from that def node.
    def_terms = {}
    for d in defs:
        # def label/text holds "term: definition"; the term is before the colon
        lbl = nodes[d].get("label", "")
        term = lbl.split(":", 1)[0].strip().lower()
        if term:
            def_terms[term] = d
    if def_terms and claims:
        ok, gaps = 0, []
        for c in claims:
            txt = (nodes[c].get("meta") or {}).get("text", "") or nodes[c].get("label", "")
            used = [t for t in def_terms if t in txt.lower()]
            grounded = all(def_terms[t] in draws_out.get(c, []) for t in used) if used else True
            if grounded:
                ok += 1
            else:
                gaps.append(c)
        checks["claim_terms_grounded"] = (ok, len(claims), gaps)
    else:
        checks["claim_terms_grounded"] = (0, len(claims) or 1, ["no glossary def nodes"])

    # 5. Every reader requirement is wired to something that satisfies it.
    if reqs:
        ok, gaps = 0, []
        for r in reqs:
            if r in touched:
                ok += 1
            else:
                gaps.append(r)
        checks["reqs_wired"] = (ok, len(reqs), gaps)

    # 6. Every section's motive is grounded in an author guess (a why below the what/how).
    if sections:
        ok, gaps = 0, []
        for s in sections:
            ds = draws_out.get(s, [])
            if any(grp(d) in _AUTHOR for d in ds):
                ok += 1
            else:
                gaps.append(s)
        checks["section_motive_grounded"] = (ok, len(sections), gaps)

    # 7. No floating nodes (every node has a non-contains edge).
    ok, gaps = 0, []
    for nid in nodes:
        if nid in touched:
            ok += 1
        else:
            gaps.append(nid)
    checks["non_orphan"] = (ok, len(nodes), gaps)

    fracs = [a / b for (a, b, _) in checks.values() if b]
    score = sum(fracs) / len(fracs) if fracs else 0.0
    return {"nodes": len(nodes), "edges": len(edges), "score": round(score, 3),
            "checks": checks}


def _report(tag, a):
    print(f"\n== {tag}: {a['nodes']} nodes, {a['edges']} edges  |  integration {a['score']:.0%}")
    for name, (ok, tot, gaps) in a["checks"].items():
        bar = f"{ok}/{tot}"
        tail = "" if ok == tot else "  gaps: " + ", ".join(str(x) for x in gaps[:6]) + ("..." if len(gaps) > 6 else "")
        print(f"   {name:34s} {bar:>7s}  {ok/tot:5.0%}{tail}")


def main(argv):
    paths = [a for a in argv if not a.startswith("--")]
    as_json = "--json" in argv
    if not paths:
        print("usage: conceptric_coherence.py <graph.json> [<graph.json> ...] [--json]", file=sys.stderr)
        return 2
    results = {p: audit(_load(p)) for p in paths}
    if as_json:
        print(json.dumps({p: {"score": r["score"], "nodes": r["nodes"], "edges": r["edges"]}
                          for p, r in results.items()}, indent=2))
    else:
        print("# Conceptric coherence — is each level completely described by the level below?")
        for p, r in results.items():
            _report(p, r)
        if len(results) > 1:
            print("\nMore nodes is not more integration. Compare the score, not the size.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
