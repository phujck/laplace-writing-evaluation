"""Compile a conceptric from a substrate + a blueprint, computing the harmonisation
edges that make each level completely described by the level below
(canon://skills/conceptric_coherence).

The substrate is the atomic generative object (doors, priors, result shells); the
blueprint is the composition (sections, claims, equations, figures). Merging them is not
enough - a coarse node is only *described* by the level below when the cross-level edges
exist. Those edges are not drawn by hand, they are **computed**, the same stance the
substrate takes on induced interactions:

  - claim  -> result it realises        (the "what" rests on a result shell)
  - section -> the author guess it serves   (the "why" beneath the what/how; from `serves:`)
  - claim/shell -> def of each term it names (the "ground terms" requirement, structural)
  - def -> ground_terms requirement, figure -> interpret_figures, section ->
    motivate_sections, the function-vs-operator schematic -> its requirement, the
    intro -> bounded_knowledge   (the reader layer wired to what satisfies it)

Term grounding is HYBRID (F29, author-ruled tuning): an exact lowercase-substring hit
draws the auto edge (source="conceptric"); a stemmed-only hit draws the SAME edge marked
source="conceptric-drafted" with the matched term riding — drafted edges count toward
def-orphan rescue but ride separately in health["connectivity"]["drafted_rescues"] for
the author's review (a def rescued only by drafted edges is not silently healthy). A
short/all-caps term (SSG, AE) never fuzzy-matches: the acronym guard stems only tokens
longer than 3 chars carrying a lowercase letter.

Run it, then run conceptric_coherence.py on the output to measure whether the iteration
moved toward the self-consistency fixed point or just added nodes.

Usage:
    python build_conceptric.py <substrate.md> <blueprint.md> <out_graph.json>
"""

from __future__ import annotations

import json
import re
import sys

from laplace.pipeline.graph import CanonGraph, _parse_blueprint, _slug


def _edge(src, dst, rel, source="conceptric"):
    return {"src": src, "dst": dst, "rel": rel, "evidence": None, "source": source, "count": 1}


# F29, second half (author-ruled tuning, HYBRID: exact auto, fuzzy DRAFTED).
# A stemmed term hit that is NOT an exact substring hit emits the SAME 'draws'
# edge, but with source="conceptric-drafted" — never silently equal to an exact
# edge. Exact always wins dedup: an exact arrival upgrades a drafted duplicate
# in place; a drafted arrival never displaces anything.
_DRAFTED = "conceptric-drafted"

_TOKEN_RX = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def _stemmable(tok: str) -> bool:
    """Acronym guard (FALQON-class acronym-dense vocabularies): stem only a
    token longer than 3 chars that carries at least one lowercase letter.
    'SSG', 'AE', 'SSGS', 'FALQON' all pass through unstemmed (lowercased
    only), so a short/all-caps term can never fuzzy-match by stemming."""
    return len(tok) > 3 and any(c.islower() for c in tok)


def _stem_token(tok: str) -> str:
    """Dependency-free deterministic stemmer: lowercase, then strip ONE
    plural/verbal suffix (sses->ss, ies->y, ing, ed, es, s). One pass, no
    lookup tables; guarded tokens (see _stemmable) return lowercased as-is."""
    t = tok.lower()
    if not _stemmable(tok):
        return t
    if t.endswith("sses"):
        return t[:-2]
    if t.endswith("ies"):
        return t[:-3] + "y"
    if t.endswith("ing") and len(t) > 5:
        return t[:-3]
    if t.endswith("ed") and len(t) > 4:
        return t[:-2]
    if t.endswith("es") and len(t) > 4:
        return t[:-2]
    if t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def _seq_contains(hay: list[str], needle: tuple[str, ...]) -> bool:
    """True iff the needle token sequence appears contiguously in hay."""
    k = len(needle)
    return k > 0 and any(tuple(hay[i:i + k]) == needle
                         for i in range(len(hay) - k + 1))


# F29 — derivation-step sources for term grounding. A conceptric node id is
# kind-prefixed and space-free (storyboard: "a real node id is kind-prefixed ...
# goal:x, def:y, res:z, irf:w"), so the ``irf:``/``thm:``/``ds:`` prefix is the
# authoritative signal (PREFIX WINS). The full logical-kind value is accepted as
# a fallback for a node minted without a prefixed id (corpus_ingest add-node mints
# ``kind="derivation-step"``; projection_spec maps ds->derivation-step,
# thm->theorem, irf's intermediate-result). The short prefix token is also
# accepted as a kind for a ledger that stores the compact form.
_DERIV_PREFIXES = ("irf:", "thm:", "ds:")
_DERIV_KINDS = {"irf", "thm", "ds", "intermediate-result", "theorem", "derivation-step"}


def _is_deriv_source(n) -> bool:
    """True for an irf:/thm:/ds: (IRF / theorem / derivation-step) node. Prefix
    on the id wins; the logical kind is the fallback."""
    if str(n.get("id", "")).startswith(_DERIV_PREFIXES):
        return True
    return n.get("kind") in _DERIV_KINDS


def build(substrate_path: str, blueprint_path: str) -> dict:
    gs = CanonGraph.from_substrate(substrate_path).to_json()
    gb = CanonGraph.from_blueprint(blueprint_path).to_json()

    nodes = {n["id"]: n for n in gs["nodes"]}
    for n in gb["nodes"]:
        nodes.setdefault(n["id"], n)
    edges = list(gs["edges"]) + list(gb["edges"])
    seen = {(e["src"], e["dst"], e["rel"]) for e in edges}

    computed: dict[tuple, dict] = {}   # edges THIS builder added, by key

    def add(src, dst, rel, source="conceptric", matched_term=None):
        if src not in nodes or dst not in nodes or src == dst:
            return
        key = (src, dst, rel)
        if key in seen:
            # EXACT WINS dedup: an exact arrival upgrades a drafted duplicate
            # in place; a drafted arrival never displaces an existing edge.
            prev = computed.get(key)
            if (source == "conceptric" and prev is not None
                    and prev.get("source") == _DRAFTED):
                prev["source"] = "conceptric"
                prev.pop("matched_term", None)
            return
        seen.add(key)
        e = _edge(src, dst, rel, source=source)
        if matched_term is not None:
            e["matched_term"] = matched_term
        edges.append(e)
        computed[key] = e

    # glossary terms: def node id -> its term string (label before the colon).
    # def_fuzzy carries the stemmed token sequence for fuzzy-ELIGIBLE terms
    # only: a term with no stemmable token (short / all-caps — 'SSG', 'AE')
    # never enters the fuzzy layer at all (the acronym guard, term side).
    def_terms = {}
    def_fuzzy = {}
    for n in nodes.values():
        if n["kind"] == "def":
            raw = n.get("label", "").split(":", 1)[0].strip()
            if not raw:
                continue
            def_terms[n["id"]] = raw.lower()
            toks = _TOKEN_RX.findall(raw)
            if toks and any(_stemmable(t) for t in toks):
                def_fuzzy[n["id"]] = tuple(_stem_token(t) for t in toks)

    def ground_terms(src_id, raw_txt):
        """HYBRID grounding (F29, author-ruled): an exact lowercase substring
        hit emits the auto edge (source="conceptric"); a stemmed hit that is
        NOT exact emits the DRAFTED edge (source="conceptric-drafted") with
        matched_term riding for the author's review. Text stems are built
        lazily from the raw (case-preserved) text so the acronym guard sees
        the original casing."""
        low = raw_txt.lower()
        stems = None
        for did, term in def_terms.items():
            if term in low:
                add(src_id, did, "draws")
                continue
            needle = def_fuzzy.get(did)
            if not needle:
                continue
            if stems is None:
                stems = [_stem_token(t) for t in _TOKEN_RX.findall(raw_txt)]
            if _seq_contains(stems, needle):
                add(src_id, did, "draws", source=_DRAFTED, matched_term=term)

    # 1. claim -> result shell it realises, and term grounding for claims.
    for n in nodes.values():
        if n["kind"] == "claim":
            meta = n.get("meta") or {}
            r = meta.get("result")
            if r:
                add(n["id"], r, "draws")
            ground_terms(n["id"], meta.get("text") or n.get("label", ""))
    # term grounding for result shells too (their summary names terms)
    for n in nodes.values():
        if n["kind"] == "node":
            ground_terms(n["id"], (n.get("meta") or {}).get("summary", ""))
    # F29: term grounding for derivation-step sources (irf:/thm:/ds:), the same
    # term-in-text test over their label + meta text/summary, same 'draws'
    # edge; add() dedupes (exact wins). No new edge kinds, no scoring.
    for n in nodes.values():
        if _is_deriv_source(n):
            meta = n.get("meta") or {}
            ground_terms(n["id"], " ".join((n.get("label", ""),
                                            meta.get("text") or "",
                                            meta.get("summary") or "")))

    # 2. section -> the author guess it serves (motive grounding). Re-parse the
    #    blueprint for the `serves:` field, which from_blueprint does not carry.
    _, sections = _parse_blueprint(open(blueprint_path, encoding="utf-8").read())
    for sec in sections:
        sid = f"sec:{_slug(sec['id'])}"
        guess = sec.get("serves")
        if guess:
            add(sid, guess, "draws")
        # every section is wired to the motivate_sections requirement it must meet
        add(sid, "motivate_sections", "draws")

    # 3. reader-layer wiring: defs satisfy ground_terms; figures satisfy
    #    interpret_figures; the schematic satisfies function_vs_operator; the intro
    #    assumes the bounded-knowledge floor.
    for n in nodes.values():
        if n["kind"] == "def":
            add(n["id"], "ground_terms", "supports")
        if n["kind"] == "figure":
            add(n["id"], "interpret_figures", "draws")
            if "function_vs_operator" in n["id"]:
                add(n["id"], "function_vs_operator", "draws")
    add("sec:intro", "bounded_knowledge", "draws")
    add("sec:abstract", "bounded_knowledge", "draws")

    # F29 connectivity gate report (compiler-local). The seven-gate
    # check_connectivity (laplace.pipeline.verify, wired at pipeline/evolve.GATE_CHECKS)
    # walks the corpus network's edge_index, which carries NO per-edge
    # provenance — so the drafted/exact split is reported here, at the gate the
    # compiler owns. Drafted edges COUNT toward rescue (a def they reach is not
    # an orphan), but a def rescued ONLY by drafted edges is not silently
    # healthy: each of its drafted edges is listed in drafted_rescues
    # ({src, dst, matched_term}) for the author's review.
    draws_in: dict[str, list[dict]] = {}
    for e in edges:
        if e["rel"] == "draws" and (nodes.get(e["dst"]) or {}).get("kind") == "def":
            draws_in.setdefault(e["dst"], []).append(e)
    def_orphans: list[str] = []
    drafted_rescues: list[dict] = []
    for nid, n in nodes.items():
        if n["kind"] != "def":
            continue
        ins = draws_in.get(nid, [])
        if not ins:
            def_orphans.append(nid)
        elif all(e.get("source") == _DRAFTED for e in ins):
            drafted_rescues.extend(
                {"src": e["src"], "dst": e["dst"],
                 "matched_term": e.get("matched_term")}
                for e in ins)
    health = {"connectivity": {
        "def_orphans": sorted(def_orphans),
        "drafted_rescues": drafted_rescues,
        "drafted_edge_count": sum(1 for e in edges
                                  if e.get("source") == _DRAFTED),
    }}

    return {"nodes": list(nodes.values()), "edges": edges, "health": health}


def main(argv):
    if len(argv) < 3:
        print("usage: build_conceptric.py <substrate.md> <blueprint.md> <out.json>", file=sys.stderr)
        return 2
    g = build(argv[0], argv[1])
    json.dump(g, open(argv[2], "w", encoding="utf-8"), ensure_ascii=False)
    conn = g["health"]["connectivity"]
    print(f"wrote {argv[2]}  ({len(g['nodes'])} nodes, {len(g['edges'])} edges, "
          f"{conn['drafted_edge_count']} drafted)")
    if conn["def_orphans"]:
        print(f"  def-orphans: {', '.join(conn['def_orphans'])}")
    for r in conn["drafted_rescues"]:
        print(f"  DRAFTED rescue: {r['src']} -> {r['dst']} "
              f"(term {r['matched_term']!r}) — author review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
