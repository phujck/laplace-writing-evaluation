"""Ingest a synthetic paper-project (the physics_paper_orchestra evidence-first workspaces)
into the engine's structural-lens schema - DETERMINISTICALLY, by parsing the author's own
curation, never by re-deriving it with an LLM.

The synthetics are not external corpora: each carries a hand-authored claim ladder
(`inputs/evidence_ledger.md`: LOL-CLM-* claims, each with a status + supporting bibkeys +
validation data file), a derivation spine (`workflow/state/derivation_spine.md`: definitions/
assumptions/propositions), a citation map (`literature/citation_map.json`: every source's
conceptual_role), and a reference set (`literature/references.bib`: the ground-truth bibkey set).
So the pour is a PARSE of that structure - confabulation-proof by construction (bibkeys are
set-membership-checked against references.bib; claim ids against the ledger).

Two artifacts per project, written under `synthetics_corpus/_structural/`:
  <key>_regraded.json  - the engine structural schema (generators -> rungs -> papers), routable
                         through structural_lens with no new materialiser.
  <key>_edges.json     - the DIRECTED cross-link layer (claim->source, claim->evidence,
                         claim<->claim co-citation, claim->other-paper companion) + a derived
                         within-paper ordering scaffold. This is what the project-ordering goal
                         is computed from; the symmetric cosine wire (drain_proposals) is added
                         on top by the engine, it does not replace these authored directed edges.

  python scripts/ingest_synthetic.py <project-dir> [--key KEY] [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# src-path bootstrap (whole-class guard, tests/test_script_bootstrap.py): a script that
# top-level-imports laplace must put the repo's src/ on sys.path so it runs standalone
# (python scripts/ingest_synthetic.py) with no editable install.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from laplace.pipeline.schema import token_for   # noqa: E402  the one edge-token minter (validates axis)

# claim status -> derivation tier (the deterministic spine order: foundations precede results).
# A within-paper ordering scaffold falls out of (tier, then ledger id); the cosine wire refines it.
_TIER = {
    "motivation": 0, "definition": 1, "assumption": 1,
    "proposition": 2, "derivation_and_numerical_check": 2, "finite_local_form_derived": 2,
    "finite_stage_supported": 2, "finite_rg_recursion_added": 2, "proved_finite_dimensional": 2,
    "toy_verified": 3, "numerical_check": 3, "literature_supported": 3,
    "geometry_supported": 3, "boundary_resolved": 3, "interpretation_boundary": 3,
    "definition_with_explicit_two_mode_obstruction": 1,
    "philosophical_after_technical_work": 4,
    "finite_obstruction_memory_example": 3,
}

# bibkey detection is KEYSET-DRIVEN, not shape-guessed: the synthetics don't share a convention
# (law-of-laws uses `wilson1971renormalization`, wigners uses CamelCase `WilsonKogut`/`Godel`), and the
# Source column is sometimes a section pointer (`Section 2`) not a citation. So we extract candidate
# tokens and keep only those that ARE keys in references.bib - set-membership, confabulation-proof, and
# blind to the key style. Candidates: any word-ish token (covers both conventions) + "seed <Key>" forms.
_CAND = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
_SEED = re.compile(r"\bseed\s+([A-Za-z][A-Za-z0-9_]+)\b", re.I)  # wigners "Bibliography seed McCaulLawOfLaws:"
_CLMID = re.compile(r"\b((?:[A-Z]{2,5}-)?CLM-\d{3})\b")   # optional project prefix: LOL-CLM-001 or CLM-001
NEST_SEP = "//"   # mirrors structural_lens.NEST_SEP - the edge layer must reference the materialized node ids
# known cross-paper citation keys -> the orchestra paper they point at (explicit inter-paper dependency)
_XPAPER_KEY = {"mccaullawoflaws": "law-of-laws", "mccaul2026law": "law-of-laws"}
# A validation POINTER — the evidence a claim's status rests on. Four families:
#   legacy file pointers (validation/data/*, *_summary.{json,csv}) — a file on disk;
#   readings:resource:<keypath> / readings:witness:<keypath> — a key path into the
#     project's numerics/<store>_readings.json (falqon's convention);
#   ledger:<param> — a row of the project's ASSUMPTION_LEDGER.md.
# The readings/ledger families are DEREFERENCED (_classify_valref): a pointer that
# does not resolve into its store is a dangling-evidence row, never a silent live
# edge. The legacy file families keep their prior behaviour (live as before).
_VALREF = re.compile(
    r"`?("
    r"validation/data/[\w./-]+"
    r"|[\w./-]*_summary\.(?:json|csv)"
    r"|readings:(?:resource|witness):[\w.\[\]]+"
    r"|ledger:\w+"
    r")`?")
# explicit cross-paper companions named in prose ("cost-of-complexity companion")
_COMPANION = re.compile(r"\b([a-z][a-z0-9-]+(?:-[a-z0-9]+)+)\s+companion\b", re.I)

# one keypath STEP: a dotted dict key, or a ``[i]`` index / ``[i..j]`` inclusive range.
_KP_STEP = re.compile(r"([A-Za-z_]\w*)|\[(\d+)(?:\.\.(\d+))?\]")


def _load_evidence_stores(project: Path) -> dict:
    """The readings stores a ``readings:<store>:*`` pointer dereferences into, keyed
    by store token. Falqon's convention: ``numerics/resource_readings.json`` and
    ``numerics/witness_readings.json``. An absent / unparseable store is simply
    absent from the map, so every pointer into it reads as dangling — never a silent
    live edge."""
    out: dict = {}
    num = project / "numerics"
    for token, fname in (("resource", "resource_readings.json"),
                         ("witness", "witness_readings.json")):
        f = num / fname
        if f.is_file():
            try:
                out[token] = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
    return out


def _deref_keypath(root, keypath: str) -> bool:
    """True iff ``keypath`` RESOLVES into the loaded JSON ``root``. Grammar: dotted
    dict keys, ``[i]`` list indices, ``[i..j]`` inclusive ranges (every index in the
    range must resolve). Covers the falqon shapes ``headline[0].logical_depth_per_layer``,
    ``sweeps.layers[0..2]``, ``cancellation.rows[0]``, ``flag_vs_prediction[4]``, and
    the bare ``dark_p_flag`` / ``evolution`` keys. Any miss (bad key, out-of-range
    index, wrong container type) is False — a dangling pointer, never a raise."""
    steps: list[tuple[str, object]] = []
    for m in _KP_STEP.finditer(keypath):
        if m.group(1) is not None:
            steps.append(("key", m.group(1)))
        else:
            lo = int(m.group(2))
            hi = int(m.group(3)) if m.group(3) is not None else lo
            steps.append(("range", (lo, hi)))
    if not steps:
        return False
    current = [root]
    for kind, val in steps:
        nxt = []
        for node in current:
            if kind == "key":
                if isinstance(node, dict) and val in node:
                    nxt.append(node[val])
                else:
                    return False
            else:                                    # an index / inclusive range
                lo, hi = val                         # type: ignore[misc]
                if not isinstance(node, list):
                    return False
                for i in range(lo, hi + 1):
                    if 0 <= i < len(node):
                        nxt.append(node[i])
                    else:
                        return False
        current = nxt
    return bool(current)


def _ledger_param_present(project: Path, param: str) -> bool:
    """True iff ``param`` is a row of the project's ``ASSUMPTION_LEDGER.md`` (the
    ``| `param` | value | … |`` table the resource model emits). Absent ledger →
    False (dangling — can't attest what isn't there, never a silent pass)."""
    p = project / "ASSUMPTION_LEDGER.md"
    if not p.is_file():
        return False
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return re.search(r"\|\s*`" + re.escape(param) + r"`\s*\|", text) is not None


def _classify_valref(ref: str, stores: dict, project: Path) -> bool:
    """LIVE (True) iff the pointer resolves; else it is a dangling-evidence row.
    A ``readings:<store>:<keypath>`` derefs into the loaded numerics store; a
    ``ledger:<param>`` resolves against ASSUMPTION_LEDGER.md; a legacy file pointer
    (validation/data/*, *_summary.*) stays LIVE as before (never dereferenced — the
    round-trip law: existing synthetics do not move)."""
    m = re.match(r"readings:(resource|witness):(.+)$", ref)
    if m:
        store = stores.get(m.group(1))
        return store is not None and _deref_keypath(store, m.group(2))
    m = re.match(r"ledger:(\w+)$", ref)
    if m:
        return _ledger_param_present(project, m.group(1))
    if v.startswith("readings:"):
        return False  # an unknown readings store never falls through to live (the G3
        # judge's coupling catch: the regex gates today, this gate holds if it widens)
    return True   # legacy file pointer — live as before


def _bibkeys(repo_bib: Path) -> set[str]:
    txt = repo_bib.read_text(encoding="utf-8", errors="ignore")
    return {m.group(1) for m in re.finditer(r"@\w+\{([^,]+),", txt)}


def _citation_map(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def _bib_titles(p: Path) -> dict[str, str]:
    """key -> 'Title (year)' from references.bib, for the citation backfill essence."""
    if not p.is_file():
        return {}
    out: dict[str, str] = {}
    for m in re.finditer(r"@\w+\{([^,]+),(.*?)\n\}", p.read_text(encoding="utf-8", errors="ignore"), re.S):
        key, body = m.group(1).strip(), m.group(2)
        t = re.search(r"title\s*=\s*[{\"]+(.+?)[}\"]+", body, re.S)
        y = re.search(r"year\s*=\s*[{\"]?(\d{4})", body)
        ttl = re.sub(r"\s+", " ", t.group(1)).strip() if t else key
        out[key] = f"{ttl} ({y.group(1)})" if y else ttl
    return out


def _tier_of(status: str) -> int:
    """Map a status string to a derivation tier, forgiving of phrasing (section ledgers write prose
    like 'Proved from definitions'). Exact match first, then first-word, then a keyword sweep."""
    s = (status or "").strip().lower()
    if s in _TIER:
        return _TIER[s]
    first = s.split()[0] if s else ""
    if first in _TIER:
        return _TIER[first]
    for kw, t in (("motivat", 0), ("definit", 1), ("assum", 1), ("propos", 2), ("proved", 2),
                  ("deriv", 2), ("numeric", 3), ("verif", 3), ("literature", 3), ("philos", 4)):
        if kw in s:
            return t
    return 2


def _parse_ledger(p: Path, keyset: set[str]) -> list[dict]:
    """Parse an evidence_ledger -> claims, format-agnostic across the orchestra's four conventions:
    prefixed table (LOL-CLM-001), un-prefixed table (CLM-001), and section blocks (## EPT-CLM-001:
    with **Claim:**/**Literature:**/**Status:**). A claim STARTS at a line whose stripped form is a
    table row whose first cell is a claim-id, or a '## ' header naming a claim-id; its BLOCK runs to
    the next such start. Citations are keyset-scanned over the whole block (set-membership = confab-safe,
    convention-blind). The graph projects (operatorial-loss) take the separate _parse_graph path."""
    lines = p.read_text(encoding="utf-8").splitlines()
    lower = {k.lower(): k for k in keyset}
    starts: list[tuple[int, str, list[str] | str]] = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if cells and _CLMID.fullmatch(cells[0]):
                starts.append((i, "table", cells))
        elif s.startswith("##"):
            m = _CLMID.search(s)
            if m and s.lstrip("#").strip().startswith(m.group(1)):
                starts.append((i, "section", m.group(1)))

    claims: list[dict] = []
    for n, (i, kind, payload) in enumerate(starts):
        j = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        block = "\n".join(lines[i:j])
        if kind == "table":
            cells = payload  # type: ignore[assignment]
            cid = cells[0]
            statement = cells[1] if len(cells) > 1 else ""
            status = cells[3] if len(cells) > 3 else ""
        else:
            cid = payload  # type: ignore[assignment]
            mst = re.search(r"\*\*Claim:?\*\*\s*(.+)", block)
            statement = (mst.group(1).strip() if mst else lines[i].split(":", 1)[-1].strip())
            mss = re.search(r"\*\*Status:?\*\*\s*(.+)", block)
            status = (mss.group(1).strip() if mss else "")
        cands = set(_CAND.findall(block)) | set(_SEED.findall(block))
        cited = sorted({lower[c.lower()] for c in cands if c.lower() in lower})   # set-membership: no confab
        xpaper = sorted({_XPAPER_KEY[c.lower()] for c in cands if c.lower() in _XPAPER_KEY})
        valrefs = sorted({m for m in _VALREF.findall(block) if m})
        companions = sorted({c.lower() for c in _COMPANION.findall(block)} | set(xpaper))
        claims.append({"id": cid, "statement": statement, "status": status,
                       "tier": _tier_of(status), "cites": cited, "unknown_cites": [],
                       "validation": valrefs, "companions": companions, "notes": ""})
    return claims


def _slug(s: str, n: int = 6) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", s.lower()))[:60] or "x"


def build(project: Path, key: str) -> tuple[dict, dict]:
    lit = project / "literature"
    keyset = _bibkeys(lit / "references.bib")
    cmap = _citation_map(lit / "citation_map.json")
    claims = _parse_ledger(project / "inputs" / "evidence_ledger.md", keyset)

    # thesis = the generator essence (the paper's meta-goal), read verbatim from idea.md core thesis.
    idea = (project / "inputs" / "idea.md").read_text(encoding="utf-8") if (project / "inputs" / "idea.md").is_file() else ""
    m = re.search(r"## Core Thesis\s*(.+?)(?:\n##|\Z)", idea, re.S)
    thesis = re.sub(r"\s+", " ", m.group(1)).strip() if m else key
    title = (re.search(r"\*\*(.+?)\*\*", idea) or [None, key])[1]

    # ENGINE SCHEMA: one generator (the paper's program) -> rungs (the 23 claims, in derivation
    # order via the ledger) -> papers (each claim's verified supporting bibkeys).
    rungs = []
    for c in claims:
        ess = f"[{c['status']}] {c['statement']}"
        if c["cites"]:
            roles = [cmap.get(k, {}).get("conceptual_role", "") for k in c["cites"]]
            roles = [r for r in roles if r]
            if roles:
                ess += "  GROUNDS: " + " | ".join(roles[:3])
        rungs.append({"name": f"{c['id'].lower()}-{_slug(c['statement'])}",
                      "essence": ess[:480], "papers": c["cites"]})
    generator = {"label": title, "essence": thesis[:480], "mode": "split", "moves": [],
                 "note": f"{len(claims)} authored claims; {sum(len(c['cites']) for c in claims)} grounded citations.",
                 "rungs": rungs}
    generators = [generator]

    # CITATION BACKFILL (his call): the literature as FIRST-CLASS nodes, independent of whether a ledger
    # row named the bibkey - so the prose-citing papers (sources = section pointers) still get their
    # sources in the conceptric. conceptual_role (citation_map) is the essence; else the references.bib
    # title. Each cited work becomes a rung carrying its semantic role, routable + cosine-wireable.
    bib_titles = _bib_titles(lit / "references.bib")
    lit_rungs = []
    for k in sorted(set(bib_titles) | set(cmap)):
        rec = cmap.get(k, {}) if isinstance(cmap.get(k), dict) else {}
        role = rec.get("conceptual_role", "")
        ttl = bib_titles.get(k) or rec.get("title", "") or k
        ess = (f"{ttl}. {role}".strip(". ") or k)
        lit_rungs.append({"name": _slug(f"{k}-{ttl}", 8) or k.lower(), "essence": ess[:480], "papers": [k]})
    if lit_rungs:
        generators.append({"label": f"{title} - literature & sources", "mode": "enrich", "moves": [],
                           "essence": f"The {len(lit_rungs)} cited works grounding {title}, each carrying its conceptual role.",
                           "note": "citation backfill (his call): literature as first-class nodes.",
                           "rungs": lit_rungs})
    regraded = {
        "_key": key, "name": title,
        "source": str(project),
        "generators": generators,
        "_coverage": {"claims": len(claims),
                      "citations_verified": sorted({k for c in claims for k in c["cites"]}).__len__(),
                      "literature_backfilled": len(lit_rungs),
                      "citations_in_map": len(cmap), "bibkeys_total": len(keyset)},
        "_provenance": "deterministic parse of evidence_ledger.md + citation_map.json + references.bib "
                       "(no LLM; bibkeys set-membership-verified against references.bib).",
    }

    # DIRECTED EDGE LAYER (the ordering substrate). gid/rid mirror structural_lens id construction.
    rel = f"synthetics_corpus/_structural/{key}_regraded.json"
    gid = f"{rel}::{_slug(title)}"
    # the evidence stores a readings pointer dereferences into (falqon's numerics/);
    # absent for the ledger-file synthetics, whose valrefs stay live file pointers.
    stores = _load_evidence_stores(project)
    edges = {"claim_to_source": {}, "claim_to_validation": {}, "validates": {},
             "dangling_evidence": {}, "co_citation": [],
             "cross_paper": [], "order_scaffold": [], "unknown_citations": {}}
    for c in claims:
        rid = f"{gid}{NEST_SEP}{c['id'].lower()}-{_slug(c['statement'])}"  # match structural_lens node ids
        edges["claim_to_source"][c["id"]] = c["cites"]
        if c["validation"]:
            # a validation pointer counts as a LIVE claim->validation edge only when
            # it dereferences (readings into numerics/*.json, ledger into the
            # assumption ledger; legacy file pointers stay live). A pointer that does
            # not resolve lands as a dangling-evidence row — surfaced, never silent.
            live = [r for r in c["validation"] if _classify_valref(r, stores, project)]
            dangling = [r for r in c["validation"] if r not in live]
            if live:
                edges["claim_to_validation"][c["id"]] = live
                # each live edge ALSO mints the validates-axis token through the one
                # home (the result carries a validates edge to its evidence reading).
                edges["validates"][c["id"]] = [token_for("validates", r) for r in live]
            if dangling:
                edges["dangling_evidence"][c["id"]] = dangling
        if c["unknown_cites"]:
            edges["unknown_citations"][c["id"]] = c["unknown_cites"]
        for comp in c["companions"]:
            edges["cross_paper"].append({"from": c["id"], "to_paper": comp, "via": "ledger-companion"})
    # co-citation: directed-agnostic affinity by shared verified bibkeys (>=1 shared source)
    for i in range(len(claims)):
        for j in range(i + 1, len(claims)):
            shared = set(claims[i]["cites"]) & set(claims[j]["cites"])
            if shared:
                edges["co_citation"].append({"a": claims[i]["id"], "b": claims[j]["id"],
                                             "shared": sorted(shared), "w": len(shared)})
    # ordering scaffold: (tier, ledger-id). foundations -> propositions -> verified -> philosophical.
    edges["order_scaffold"] = [c["id"] for c in sorted(claims, key=lambda c: (c["tier"], c["id"]))]
    return regraded, edges


def build_graph(graph_path: Path, key: str, merge_with: str = "") -> tuple[dict, dict]:
    """INFORMATION-PRESERVING ingest of a paper's own conceptric graph (operatorial-loss's
    graph_v*_conceptric.json: {nodes, edges}). His call: the merge is a lossless UNION - every node
    becomes a node (cluster->generator, everything else->rung; citations->leaves), EVERY typed edge is
    preserved in the directed layer, and the laplace-side `paper_operatorial_loss` is NOT touched
    (adding a synthetics view never deletes the existing one; overlaps link by cosine + a recorded
    same_as at the project level)."""
    import collections
    g = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in g.get("nodes", [])}
    gedges = g.get("edges", [])
    children: dict[str, list[str]] = collections.defaultdict(list)
    for e in gedges:
        if e.get("rel") in ("contains", "has_project"):
            children[e["src"]].append(e["dst"])

    def ess(n: dict) -> str:
        return (f"[{n.get('kind','node')}] {n.get('label','') or n.get('id','')}")[:480]

    gen_kinds = {"domain", "cluster", "intent"}
    placed: set[str] = set()
    generators = []
    for nid, n in nodes.items():
        if n.get("kind") not in gen_kinds:
            continue
        rungs = []
        for cid in children.get(nid, []):
            cn = nodes.get(cid)
            if not cn or cn.get("kind") == "citation":
                continue
            papers = [m for m in children.get(cid, []) if nodes.get(m, {}).get("kind") == "citation"]
            rungs.append({"name": _slug(cn.get("label") or cid, 8) or cid, "essence": ess(cn), "papers": papers})
            placed.add(cid)
        generators.append({"label": n.get("label", nid), "essence": ess(n), "mode": "split", "moves": [],
                           "note": f"graph node {nid}", "rungs": rungs})
        placed.add(nid)
    # info-preserving catch-all: every non-citation node not yet under a generator still lands as a rung
    orphans = [nid for nid, n in nodes.items()
               if nid not in placed and n.get("kind") not in ("citation",)]
    if orphans:
        generators.append({"label": f"{key} - unclustered graph nodes", "mode": "enrich", "moves": [],
                           "essence": "graph nodes not under a cluster - preserved (information-preserving merge).",
                           "note": "catch-all", "rungs": [{"name": _slug(nodes[o].get("label") or o, 8) or o,
                                                           "essence": ess(nodes[o]), "papers": []} for o in orphans]})
    title = next((n.get("label", key) for n in nodes.values() if n.get("kind") == "domain"), key)
    regraded = {"_key": key, "name": title, "source": str(graph_path),
                "generators": generators,
                "_coverage": {"graph_nodes": len(nodes), "graph_edges": len(gedges),
                              "node_kinds": dict(collections.Counter(n.get("kind") for n in nodes.values()))},
                "_merge": {"with": merge_with, "policy": "information-preserving union - orchestra graph "
                           "added as the synthetics view; laplace paper_operatorial_loss retained intact; "
                           "overlapping entities link by cosine wire + project same_as, none deleted."} if merge_with else {},
                "_provenance": "deterministic parse of the paper's own conceptric graph (no LLM)."}
    # DIRECTED EDGE LAYER: preserve ALL typed edges + lift precedes/cites into the ordering substrate.
    edges = {"graph_edges": [{"src": e.get("src"), "dst": e.get("dst"), "rel": e.get("rel")} for e in gedges],
             "precedes": [[e["src"], e["dst"]] for e in gedges if e.get("rel") == "precedes"],
             "cites": [[e["src"], e["dst"]] for e in gedges if e.get("rel") == "cites"],
             "supports": [[e["src"], e["dst"]] for e in gedges if e.get("rel") in ("supports", "supported_by")],
             "cross_paper": ([{"from": key, "to_paper": merge_with, "via": "same_as (info-preserving merge)"}]
                             if merge_with else [])}
    return regraded, edges


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--key", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--graph", default=None, help="ingest a conceptric graph json instead of a ledger")
    ap.add_argument("--merge-with", default="", help="existing node-set this graph unions with (info-preserving)")
    a = ap.parse_args()
    project = Path(a.project).resolve()
    key = a.key or project.name
    root = Path(__file__).resolve().parent.parent
    out = Path(a.out) if a.out else (root / "synthetics_corpus" / "_structural")
    out.mkdir(parents=True, exist_ok=True)

    if a.graph:
        regraded, edges = build_graph(Path(a.graph).resolve(), key, a.merge_with)
        (out / f"{key}_regraded.json").write_text(json.dumps(regraded, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / f"{key}_edges.json").write_text(json.dumps(edges, ensure_ascii=False, indent=1), encoding="utf-8")
        cov = regraded["_coverage"]
        print(f"INGESTED {key} (graph): {cov['graph_nodes']} nodes, {cov['graph_edges']} edges preserved; "
              f"{len(regraded['generators'])} generators; kinds {cov['node_kinds']}")
        print(f"  directed: {len(edges['precedes'])} precedes, {len(edges['cites'])} cites, "
              f"{len(edges['supports'])} supports; merge: {regraded.get('_merge',{}).get('with') or 'none'}")
        print(f"  -> {out}/{key}_regraded.json , {key}_edges.json")
        return 0

    regraded, edges = build(project, key)
    (out / f"{key}_regraded.json").write_text(json.dumps(regraded, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / f"{key}_edges.json").write_text(json.dumps(edges, ensure_ascii=False, indent=1), encoding="utf-8")

    cov = regraded["_coverage"]
    print(f"INGESTED {key}: {cov['claims']} claims -> rungs, {cov['citations_verified']} verified "
          f"citations grounded (of {cov['bibkeys_total']} bibkeys, {cov['citations_in_map']} in map)")
    print(f"  edges: {sum(len(v) for v in edges['claim_to_source'].values())} claim->source, "
          f"{sum(len(v) for v in edges['claim_to_validation'].values())} claim->validation "
          f"({sum(len(v) for v in edges['validates'].values())} validates-axis tokens, "
          f"{sum(len(v) for v in edges['dangling_evidence'].values())} dangling-evidence), "
          f"{len(edges['co_citation'])} co-citation, {len(edges['cross_paper'])} cross-paper")
    unk = edges["unknown_citations"]
    if unk:
        print(f"  WARNING: {sum(len(v) for v in unk.values())} cited keys NOT in references.bib "
              f"(confab-catch): {dict(list(unk.items())[:3])}")
    print(f"  -> {out}/{key}_regraded.json , {key}_edges.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
