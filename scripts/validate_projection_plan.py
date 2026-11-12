"""Validate a projection plan against its conceptric and the global corpus.

The plan (projection_plan.json) is the contract between the author and the orchestration:
content selection + pinned linear order. This gate holds it honest:
- every node id exists in the corpus network and is NOT retired
- no live claim node the spine reaches is silently absent (coverage report, advisory)
- every ref key resolves in the selected manuscript's bibliography consumers
  (the registered bibliography is the fallback before source setup)
- every figure id exists and carries a provenance block

Usage: python scripts/validate_projection_plan.py <plan.json> [<corpus-name>]
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from laplace.research import corpus_ingest as ci
from laplace.web.scanner import _repo_root
from laplace.pipeline import registry
from laplace.pipeline.schema import (bib_keys as _bib_keys, proj_of,
                                     contribution_rank_id,
                                     unwrap_contribution_rank)
from laplace.pipeline.proportionality_audit import check_plan_proportionality


def _rank_list(meta: dict):
    """The bare ``contribution_rank`` list for these readers, read through the ONE
    respine-envelope unwrap (``schema.unwrap_contribution_rank``): the 2026-07-22
    ratified ``{value:[...], projection_ruling:{...}}`` yields its ``.value``; a
    bare list / absent passes through. READ-ONLY — the store's ratified shape is
    never rewritten here (the wrapper's ``projection_ruling`` provenance stands);
    the readers adapt to the shape, they do not normalise the store."""
    return unwrap_contribution_rank((meta or {}).get("contribution_rank"))


def check_contribution_rank(meta: dict) -> list:
    """Validate ``meta.contribution_rank`` additively (2026-07-13, the return-path
    push): the ONE authored judgement the dispatch compiler threads into every
    builder packet. ABSENT draws no complaint (``[]``); PRESENT, it must be a
    NON-EMPTY list of plain strings OR ``{rank:int, claim:str, role:str}`` dicts.
    Returns a list of ``(where, why)`` defects — empty means clean. A malformed
    rank would silently mis-render (or vanish) in the kernel block, so it is loud."""
    defects: list = []
    rank = _rank_list(meta)
    if rank is None:
        return defects
    if not isinstance(rank, list) or not rank:
        defects.append(("contribution_rank", "must be a non-empty list"))
        return defects
    for i, item in enumerate(rank):
        if isinstance(item, str):
            continue
        if isinstance(item, dict) and isinstance(item.get("rank"), int) \
                and isinstance(item.get("claim"), str) \
                and isinstance(item.get("role"), str):
            continue
        defects.append((f"contribution_rank[{i}]",
                        "must be a str or {rank:int, claim:str, role:str}"))
    return defects


def _rank_keys(n) -> list:
    """The rank-NUMBER keys an authored ``rank`` field contributes to an index —
    ``[n, str(n)]`` for a real number, ``[]`` for anything else.

    Fail-closed against a MALFORMED authored rank: ``{"rank": [], …}`` /
    ``{"rank": {…}, …}`` is unhashable, and indexing on it raised ``TypeError``
    inside ``validate`` — a CRASH in place of the FAIL report (the whole run's
    defect lists and the loud unserved count died with it). The shape defect is
    already reported by ``check_contribution_rank``; here the entry simply loses
    its rank-number door and keeps its content-id one (the id is IDENTITY, the
    rank is a position). ``bool`` is excluded FIRST — ``True == 1`` and
    ``hash(True) == hash(1)``, so a ``{"rank": true}`` entry would otherwise
    seize the rank-1 key and answer a legitimate ``serves: 1``."""
    if isinstance(n, bool) or not isinstance(n, (int, str)):
        return []
    return [n, str(n)]


def contribution_index(meta: dict) -> dict:
    """Map every resolvable ``serves`` target -> the claim it names. A contribution
    (C3.1, section ownership) is addressable by its STABLE content-id
    (``schema.contribution_rank_id``) OR by its 1-based rank number (as int and as
    its string form). Empty when the plan carries no ``contribution_rank`` — under
    which any ``serves`` cannot resolve and every reference is a defect."""
    rank = _rank_list(meta)
    index: dict = {}
    if not isinstance(rank, list):
        return index
    for i, item in enumerate(rank, 1):
        if isinstance(item, dict):
            claim = str(item.get("claim") or "").strip()
            n = item.get("rank", i)
        elif isinstance(item, str):
            claim, n = item.strip(), i
        else:
            continue
        if not claim:
            continue
        index[contribution_rank_id(claim)] = claim
        for key in _rank_keys(n):   # rank number as int and as its string form
            index[key] = claim
    return index


def _excluded_index(meta: dict) -> dict:
    """The subset of contributions carrying an EXCLUDED/exploratory role — the only
    legitimate members of ``meta.exclusions``. Keyed by content-id, rank number
    (int + str), and the raw claim text, so an exclusion may name any of them."""
    rank = _rank_list(meta)
    idx: dict = {}
    if not isinstance(rank, list):
        return idx
    for i, item in enumerate(rank, 1):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").lower()
        if "excluded" not in role and "exploratory" not in role:
            continue
        claim = str(item.get("claim") or "").strip()
        if not claim:
            continue
        n = item.get("rank", i)
        idx[contribution_rank_id(claim)] = claim
        for key in _rank_keys(n):   # skipped for a malformed (unhashable/bool) rank
            idx[key] = claim
        idx[claim] = claim
    return idx


def check_serves(plan: dict, meta: dict) -> tuple:
    """Validate section ``serves`` references (C3.1 section ownership). A section
    MAY declare ``serves`` — a contribution id or rank number (or a list of them).
    Every reference MUST resolve to an actual contribution in
    ``meta.contribution_rank`` (unknown => FAIL); a declared-but-empty ``serves``
    is also a defect. Sections WITHOUT ``serves`` are COUNTED, never faulted —
    adoption is incremental, absence is not yet an error, but the count is loud.
    Returns ``(defects, served_count, unserved_count)``."""
    index = contribution_index(meta)
    defects: list = []
    served = unserved = 0
    sections = list(plan.get("sections") or []) + list(plan.get("appendices") or [])
    for sec in sections:
        sid = sec.get("id", "?")
        if "serves" not in sec:
            unserved += 1
            continue
        raw = sec.get("serves")
        refs = raw if isinstance(raw, list) else [raw]
        refs = [r for r in refs if r is not None and r != ""]
        if not refs:
            defects.append((sid, "serves declared but empty"))
            continue
        served += 1
        for ref in refs:
            if isinstance(ref, bool) or not isinstance(ref, (str, int)):
                # a non-scalar ref (dict/list) can never resolve and is unhashable —
                # emit a proper DEFECT row instead of raising on `ref in index`.
                # bool excluded FIRST (as check_exclusions already does): True == 1,
                # so a bare `serves: true` would silently resolve as rank 1
                defects.append((sid, f"serves reference must be a str/int contribution ref, got {ref!r}"))
                continue
            if ref not in index:
                defects.append((sid, f"serves references unknown contribution {ref!r}"))
    return defects, served, unserved


def check_exclusions(meta: dict) -> list:
    """Validate ``meta.exclusions`` membership shape (present-only; absent => clean).
    ``exclusions`` is the explicit roster of contributions deliberately left out.
    Shape: a NON-EMPTY list; each entry a plain string ref OR a
    ``{ref|claim|contribution[, reason]}`` dict. Each ref must resolve to a
    contribution carrying an EXCLUDED/exploratory role (addressable by content-id,
    rank number, or claim text). A shapeless or unknown exclusion is a FAIL — a
    silent typo would drop a real exclusion from the roster. Returns a list of
    ``(where, why)`` defects, empty when clean."""
    excl = (meta or {}).get("exclusions")
    defects: list = []
    if excl is None:
        return defects
    if not isinstance(excl, list) or not excl:
        defects.append(("exclusions", "must be a non-empty list when present"))
        return defects
    idx = _excluded_index(meta)
    for i, item in enumerate(excl):
        if isinstance(item, bool):          # bool is an int subclass — never a ref
            defects.append((f"exclusions[{i}]",
                            "must be a str/int ref or a {ref|claim|contribution[, reason]} dict"))
            continue
        if isinstance(item, int):
            ref: object = item              # a rank number
        elif isinstance(item, str):
            ref = item.strip()
        elif isinstance(item, dict):
            ref = str(item.get("ref") or item.get("claim")
                      or item.get("contribution") or "").strip()
        else:
            defects.append((f"exclusions[{i}]",
                            "must be a str/int ref or a {ref|claim|contribution[, reason]} dict"))
            continue
        if ref == "":
            defects.append((f"exclusions[{i}]", "empty exclusion reference"))
            continue
        if ref not in idx:
            defects.append((f"exclusions[{i}]",
                            f"references {ref!r}, not an excluded-role contribution"))
    return defects


def validate(plan_path: str, corpus: str, repo_root: str | Path | None = None) -> dict:
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    rr = Path(repo_root).resolve() if repo_root is not None else _repo_root()
    net = ci.corpus_network(ci.resolve_corpus(rr, corpus), repo_root=rr, name=corpus)
    nodes = net["nodes"]

    proj = registry.resolve(corpus, repo_root=rr)
    from laplace.manuscript import manuscript_source
    from laplace.research import references_surface
    selected = manuscript_source.resolve(corpus, repo_root=rr)
    selected_root = rr / selected["root"] if selected.get("root") else None
    names = references_surface._bibliography_names(selected_root) if selected_root else []
    bib_paths = [selected_root.parent / (name if name.endswith(".bib") else name + ".bib")
                 for name in names] if names else [
                     proj.path(proj.bib, rr) if proj else rr / "corpus" / "corpus.bib"]
    bib_keys = set()
    for bib_path in bib_paths:
        if bib_path and bib_path.is_file():
            bib_keys.update(_bib_keys(bib_path.read_text(encoding="utf-8")))

    # Stage C (structural resolution) may settle an appendix to an intentionally
    # EMPTY pool: every candidate node is introduced in the body, so any listing
    # would be a duplicate introduction or a forward reference under the
    # reader-state law. The distinguisher from an unresolved placeholder is the
    # authored section contract (function non-empty) for that appendix id.
    contracted: set[str] = set()
    try:
        cp = proj.stage_path("contracts", rr) if proj else None
        if cp is not None and cp.is_file():
            _cs = json.loads(cp.read_text(encoding="utf-8")).get("sections") or {}
            contracted = {sid for sid, c in _cs.items() if (c or {}).get("function")}
    except (OSError, json.JSONDecodeError):
        pass

    missing_nodes, retired_used, missing_refs, fig_defects = [], [], [], []
    planned_nodes: set[str] = set()

    # meta.contribution_rank (2026-07-13, the return-path push): the ONE authored
    # judgement the dispatch compiler threads into every builder packet — validated
    # additively (absent draws no complaint).
    _meta = plan.get("meta") or {}
    meta_defects = check_contribution_rank(_meta)
    # C3.1 section ownership: `serves` must resolve to a real contribution
    # (unknown => FAIL); sections without `serves` are counted, not faulted.
    serves_defects, served_count, unserved_count = check_serves(plan, _meta)
    # C3.1 exclusion membership shape (present-only; absent => clean).
    exclusion_defects = check_exclusions(_meta)
    # C3.2 the pre-render proportionality gate: does manuscript mass follow the
    # contribution ranking? WARN-tier — reported, NOT folded into `ok` (the gate
    # flags before prose; the crank consumes the flags, it does not yet block).
    proportionality = check_plan_proportionality(plan)
    for sec in plan.get("sections", []):
        for nid in sec.get("nodes_in_order", []) + sec.get("beats", []):
            planned_nodes.add(nid)
            if nid not in nodes:
                missing_nodes.append((sec["id"], nid))
            elif proj_of(nodes[nid]).get("retired"):
                retired_used.append((sec["id"], nid))
        for fid in sec.get("figures", []):
            planned_nodes.add(fid)
            if fid not in nodes:
                fig_defects.append((sec["id"], fid, "missing node"))
            elif not proj_of(nodes[fid]).get("provenance"):
                fig_defects.append((sec["id"], fid, "no provenance block"))
        for key in sec.get("refs", []):
            if key not in bib_keys:
                missing_refs.append((sec["id"], key))
    for app in plan.get("appendices", []):
        node_ids = app.get("nodes_in_order") or []
        if not node_ids and not isinstance(app.get("nodes"), list) \
                and app["id"] not in contracted:
            fig_defects.append((app["id"], "-", "appendix nodes unresolved (run "
                                "scripts/resolve_appendix_nodes.py)"))
        for nid in node_ids or app.get("nodes", []):
            planned_nodes.add(nid)
            if nid not in nodes:
                missing_nodes.append((app["id"], nid))
            elif proj_of(nodes[nid]).get("retired"):
                retired_used.append((app["id"], nid))
            elif nid.startswith("fig:") and not proj_of(nodes[nid]).get("provenance"):
                fig_defects.append((app["id"], nid, "no provenance block"))
        for key in app.get("refs", []):
            if key not in bib_keys:
                missing_refs.append((app["id"], key))

    # advisory coverage: live claim nodes not planned anywhere (main text or beats)
    unplanned_claims = [
        nid for nid, nd in sorted(nodes.items())
        if nid.startswith(("res:", "thm:")) and not proj_of(nd).get("retired")
        and nid not in planned_nodes
    ]
    ok = (not missing_nodes and not retired_used and not missing_refs
          and not fig_defects and not meta_defects
          and not serves_defects and not exclusion_defects)
    return {"pass": ok, "missing_nodes": missing_nodes, "retired_used": retired_used,
            "missing_refs": missing_refs, "fig_defects": fig_defects,
            "meta_defects": meta_defects,
            "serves_defects": serves_defects,
            "exclusion_defects": exclusion_defects,
            "sections_serving": served_count,
            "sections_without_serves": unserved_count,
            "advisory_unplanned_claims": unplanned_claims,
            "proportionality": proportionality,
            "planned_node_count": len(planned_nodes)}


if __name__ == "__main__":
    # defaults through the registry: the active project, its registered plan -
    # never a hardcoded project name
    corpus = sys.argv[2] if len(sys.argv) > 2 else registry.default_project()
    _proj = registry.resolve(corpus)
    if _proj is None or not _proj.plan_path:
        sys.exit(f"unknown or plan-less project: {corpus!r}")
    plan = sys.argv[1] if len(sys.argv) > 1 else _proj.plan_path
    r = validate(plan, corpus)
    print(json.dumps(r, indent=1))
    sys.exit(0 if r["pass"] else 1)
