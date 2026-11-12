"""conceptric_dreamer.py - N26: the recursive consolidating dreamer.

The Dreamer (``dreamer.py``) reparametrises the SKILL tree from telemetry-derived
fitness. This is the SAME R&R loop with the substrate swapped: it reparametrises
the CONCEPTRIC - the directory sharded into nodes (``self_shard``) - by clustering
a region's nodes, forging the coarse parent each cluster is missing, and wiring the
orphans into it.

  a skill                      <->  a conceptric node
  assess()                     <->  assess_conceptric()   (this module)
  a lifecycle transition       <->  a reshape (cluster / lift / lower / split)
  forge_skill (write SKILL.md) <->  lift (write conceptric/<slug>.md)

The keystone: **the lift IS a forge**. A forged coarse node is a real
``conceptric/<slug>.md`` file with ``[[member]]`` links - so ``shard_repo`` picks
it up, ``_self_graph`` resolves its links to the orphan members, the lens shows the
new parent wiring them in, and ``shard_faithfulness`` certifies it round-trips. No
special node-kind, no index format hack: the conceptric is still just "the directory
sharded", and N26 grows the directory with concept-files that hierarchialise it.

Recursive: a reshape forges coarse nodes that are themselves a coarser set, so the
dreamer re-runs one level up on them (cluster -> push work up) and pushes detail one
level down. The orchestrator is a dreamer dreaming sub-dreamers - per grade.

Certified by RESULTS, not the proxy signal (his close, 2026-06-07): a reshape is kept
iff the region still does its job - ``shard_faithfulness`` holds while the orphan
count / width drops. A confabulated coarse node lowers the proxy but FAILS the result
(its members do not reconstruct through it); the why-not is the next residual. The
proxy (recurrence x coherence x poor-fit) drives candidate GENERATION only; the order
parameter (his, F1/F5/F12) drops into the ``converge.rho_star`` socket later.

This module is the ASSESS half (the read/propose - mutates nothing). The reshape
(apply / lift / sew-up) and the recursion follow.
"""

from __future__ import annotations

import re
from typing import Any

# --- the proxy knobs (his order parameter drops into the rho_star socket later) ---
CONCEPTRIC_DIR = "conceptric"
MIN_SUPPORT = 3       # a concept must cover at least this many nodes to be real
MAX_FRAC = 0.5        # a token covering more than half the region is too generic to be a concept
TARGET_SUPPORT = 12   # concepts near this size score fullest (tiny clusters weak, huge ones are groups)

# Structural noise: extension / scaffolding words that co-occur everywhere, so they recur without
# naming a concept. Kept deliberately small - over-stopping hides real concepts (the proxy is meant
# to over-propose; the sealed judge and the results gate carve the false ones).
_STOP = {
    "py", "md", "tex", "json", "txt", "yaml", "yml", "html", "bib", "png", "pdf",
    "self", "laplace", "src", "the", "and", "for", "with", "from", "this", "that",
    "doc", "file", "code", "test", "skill",
}


# ---------------------------------------------------------------------------
# the graph the lens renders (so "width collapse" is measured in the lens's units)
# ---------------------------------------------------------------------------

def _root(repo_root):
    """The repo to dream over - the given root, else the engine's own (``self_shard``'s default).
    Threaded through so the dreamer runs on - and is tested against - any tree, not a hardcoded one."""
    from pathlib import Path

    from laplace.engine.self_shard import default_repo_root

    return Path(repo_root) if repo_root is not None else default_repo_root()


def _graph(repo_root) -> tuple[list[dict], list[dict]]:
    """The repo's self-corpus as the lens renders it - ``self_shard.self_graph(root)``: the SAME
    resolved node/edge graph the per-firing tree draws, so a reshape's width-collapse is measured in
    the units the author watches. Parameterised by ``repo_root`` (not the scanner's hardcoded engine
    root) so the dreamer runs on any tree; rebuilt each call (a reshape mutates the tree between
    measurements)."""
    from laplace.engine import self_shard

    g = self_shard.self_graph(repo_root)
    return g.get("nodes", []), g.get("edges", [])


def _degree(nodes: list[dict], edges: list[dict]) -> dict[str, int]:
    """Undirected degree per node id (in + out), over resolved edges - the orphan test."""
    deg = {n["id"]: 0 for n in nodes}
    for e in edges:
        if e.get("src") in deg:
            deg[e["src"]] += 1
        if e.get("dst") in deg:
            deg[e["dst"]] += 1
    return deg


def _is_soul(n: dict) -> bool:
    return n.get("group") == "soul" or n.get("kind") == "soul" or n.get("meta", {}).get("sealed")


def _region_nodes(nodes: list[dict], region: str) -> list[dict]:
    """Nodes in a region (a self-layer ``group`` like 'src/laplace'). Soul is excluded - it stays
    sealed, never clustered. A node matches by its group or by a path-prefix within the region."""
    pref = region.rstrip("/") + "/"
    return [
        n for n in nodes
        if not _is_soul(n)
        and (n.get("group") == region or n.get("meta", {}).get("path", "").startswith(pref))
    ]


def _keywords(n: dict) -> set[str]:
    """The concept-bearing words a node surfaces at - its shard keywords, minus structural noise."""
    kws = n.get("meta", {}).get("keywords") or []
    return {k for k in kws if len(k) >= 3 and not k.isdigit() and k not in _STOP}


# ---------------------------------------------------------------------------
# the proxy: recurrence x coherence x poor-fit  (candidate generation only)
# ---------------------------------------------------------------------------

def _invert(region_nodes: list[dict]) -> dict[str, set[str]]:
    """token -> the node ids it surfaces - the recurrence index. A token covering many nodes is a
    candidate concept axis (the word the cluster recurs on)."""
    inv: dict[str, set[str]] = {}
    for n in region_nodes:
        for kw in _keywords(n):
            inv.setdefault(kw, set()).add(n["id"])
    return inv


def _coherence(member_ids: set[str], by_id: dict[str, dict]) -> float:
    """Avg pairwise Jaccard of member keyword sets - do these nodes share MORE than the one token
    that grouped them? A real concept is dense; co-located-but-unrelated files are not. This is the
    proxy's guard against the false cluster (recurrence alone over-groups)."""
    sets = [_keywords(by_id[i]) for i in member_ids if i in by_id]
    sets = [s for s in sets if s]
    if len(sets) < 2:
        return 0.0
    total = 0.0
    pairs = 0
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            union = sets[i] | sets[j]
            if union:
                total += len(sets[i] & sets[j]) / len(union)
                pairs += 1
    return total / pairs if pairs else 0.0


def _proxy(support: int, coherence: float, orphan_frac: float) -> float:
    """The PROXY fitness - NOT the certifier (results are; his close). recurrence = support (capped
    at TARGET, so a group-sized blob does not outscore a real concept), coherence = density,
    poor-fit = the orphan fraction the lift would rescue (undoing the loss is the point). The real
    order parameter (F1/F5/F12) replaces this body via the ``converge.rho_star`` socket."""
    support_w = min(1.0, support / TARGET_SUPPORT)
    fit_w = 1.0 + orphan_frac
    return round(coherence * support_w * fit_w, 4)


def _candidates(region_nodes: list[dict], deg: dict[str, int]) -> list[dict]:
    """Every token that recurs enough to be a candidate concept, scored by the proxy, best first."""
    by_id = {n["id"]: n for n in region_nodes}
    inv = _invert(region_nodes)
    n_region = len(region_nodes)
    cands: list[dict] = []
    for token, members in inv.items():
        support = len(members)
        if support < MIN_SUPPORT or support > MAX_FRAC * n_region:
            continue
        coh = _coherence(members, by_id)
        orphans = sum(1 for i in members if deg.get(i, 0) == 0)
        cands.append({
            "token": token,
            "members": members,
            "support": support,
            "coherence": round(coh, 4),
            "orphan_members": orphans,
            "proxy": _proxy(support, coh, orphans / support if support else 0.0),
        })
    cands.sort(key=lambda c: (-c["proxy"], -c["support"], c["token"]))
    return cands


def _assign(cands: list[dict], region_nodes: list[dict]) -> tuple[list[dict], set[str]]:
    """Partition: each node joins the highest-proxy concept that covers it (one parent, v1). A
    concept whose members were mostly claimed by stronger concepts drops out. Returns (proposals,
    residual) where residual = nodes under no surviving concept - the why-not the next pass chases."""
    taken: set[str] = set()
    proposals: list[dict] = []
    for c in cands:  # already best-first
        members = sorted(m for m in c["members"] if m not in taken)
        if len(members) < MIN_SUPPORT:
            continue
        taken.update(members)
        proposals.append({**c, "members": members, "assigned": len(members)})
    residual = {n["id"] for n in region_nodes} - taken
    return proposals, residual


# ---------------------------------------------------------------------------
# the sealed-judgment brief (executed by a clean-context dreamer in the run)
# ---------------------------------------------------------------------------

def _slug(region: str, token: str) -> str:
    base = region.rstrip("/").split("/")[-1]
    return re.sub(r"[^a-z0-9]+", "-", f"{base}-{token}".lower()).strip("-")


def _judge_brief(region: str, prop: dict, by_id: dict[str, dict]) -> str:
    """The brief a SEALED dreamer (clean context, E1) runs to certify + name one candidate concept.
    The mechanical proxy proposes; the sealed judge decides coherence, names it, and carves out the
    members that do not belong - the half that needs taste, kept out of the saturated transcript."""
    def _line(m: str) -> str:
        meta = by_id[m].get("meta", {})
        return f"- {meta.get('path', m)} - {(meta.get('essence') or '')[:90]}"

    members = prop["members"]
    shown = "\n".join(_line(m) for m in members[:24])
    more = f"\n  (+{len(members) - 24} more)" if len(members) > 24 else ""
    return (
        f"SEALED CONCEPTRIC DREAMER - region '{region}', candidate concept '{prop['token']}' "
        f"({prop['support']} members, coherence {prop['coherence']}, {prop['orphan_members']} orphans).\n"
        f"These nodes recur on the word '{prop['token']}':\n{shown}{more}\n\n"
        "Judge, sealed (you see only this brief): (1) Is this a COHERENT concept, or just co-located "
        "files? (2) Name it - a short slug + a one-line essence a member would reconstruct THROUGH. "
        "(3) List any members that do NOT belong (carve them out). (4) One line: what coarser concept "
        "is THIS a part of? Return strict JSON: "
        '{"coherent": bool, "slug": str, "essence": str, "drop": [paths], "parent_hint": str}.'
    )


# ---------------------------------------------------------------------------
# assess_conceptric - the read/propose (the conjugate open of the reshape close)
# ---------------------------------------------------------------------------

def assess_conceptric(region: str = "src/laplace", repo_root=None, refresh: bool = False) -> dict[str, Any]:
    """``assess()`` generalised to conceptric nodes. Cluster a region by recurrence, score coherence,
    flag poor-fit; emit PROPOSED lifts (mutating nothing) + a sealed-judgment brief per concept.

    The output is the proposed reshape: what the dreamer would forge and which orphans each lift
    would rescue. Nothing is written - the apply half forges the conceptric/<slug>.md files and the
    results gate certifies them."""
    repo_root = _root(repo_root)
    nodes, edges = _graph(repo_root)
    deg = _degree(nodes, edges)
    region_nodes = _region_nodes(nodes, region)
    by_id = {n["id"]: n for n in region_nodes}
    orphan_ids = {n["id"] for n in region_nodes if deg.get(n["id"], 0) == 0}

    proposals, residual = _assign(_candidates(region_nodes, deg), region_nodes)
    for p in proposals:
        # orphan_members on the ASSIGNED members (what THIS lift actually rescues) - the candidate's
        # pre-assignment count overstates once stronger concepts have claimed shared orphans.
        p["orphan_members"] = sum(1 for m in p["members"] if m in orphan_ids)
        p["slug"] = _slug(region, p["token"])
        p["brief"] = _judge_brief(region, p, by_id)
        p["members"] = [by_id[m].get("meta", {}).get("path", m) for m in p["members"]]  # ids -> paths

    rescued = {m for p in proposals for m in p["members"]}
    rescued_orphans = sum(
        1 for p in proposals for m in p["members"]
        if f"file:{m}" in orphan_ids
    )
    return {
        "region": region,
        "nodes": len(region_nodes),
        "orphans_before": len(orphan_ids),
        "concepts_proposed": len(proposals),
        "orphans_rescued_if_applied": rescued_orphans,
        "orphans_residual_if_applied": len(orphan_ids - {f"file:{m}" for m in rescued}),
        "proposals": proposals,
        "residual_unconcepted": sorted(n[5:] if n.startswith("file:") else n for n in residual),
        "note": "PROXY proposal - mutates nothing. Lifts are forged (conceptric/<slug>.md) + certified "
                "by RESULTS (shard_faithfulness held while orphans drop), not by the proxy (his close).",
    }


def format_assessment(rep: dict) -> str:
    """A compact human read of the proposed reshape - the width before, and what each lift fixes."""
    out = [
        f"region {rep['region']}: {rep['nodes']} nodes, {rep['orphans_before']} orphans",
        f"proposed {rep['concepts_proposed']} concepts -> rescue "
        f"{rep['orphans_rescued_if_applied']} orphans, {rep['orphans_residual_if_applied']} residual",
        "",
    ]
    for p in rep["proposals"][:40]:
        out.append(
            f"  [{p['proxy']:.3f}] {p['slug']:<30} n={p['assigned']:<3} "
            f"coh={p['coherence']:.2f} orphans={p['orphan_members']}"
        )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# the reshape: lift = forge (write conceptric/<slug>.md), apply, measure
# ---------------------------------------------------------------------------

def _default_essence(region: str, prop: dict) -> str:
    """A deterministic handle when no sealed judge has named the concept yet (tests / dry-run). Plain
    about being mechanical; the sealed run replaces it with a reconstruct-THROUGH essence."""
    return (f"the '{prop['token']}' concept in {region}: {prop['assigned']} nodes that recur on "
            f"'{prop['token']}' (coherence {prop['coherence']}). Coarse parent forged by N26.")


def _concept_markdown(slug: str, essence: str, members: list[str], parent_hint: str = "") -> str:
    """The forged coarse node AS A FILE: a frontmatter handle + ``[[member]]`` links. The links are
    exactly what ``self_shard._edges`` extracts and ``self_shard.self_graph`` resolves, so writing this
    file wires the members in - the lift IS a forge, and the conceptric stays 'the directory sharded'.
    Members are capped at 40 (``_edges``' own cap); v1 concepts are smaller, the recursion splits big
    ones one grade up."""
    head = ["---", f"concept: {slug}", f"essence: {essence}"]
    if parent_hint:
        head.append(f"part_of: {parent_hint}")
    head += [
        "---", "", f"# {slug}", "", essence, "",
        "<!-- forged by the conceptric dreamer (N26): a coarse node lifted above its members,",
        "     wiring them into the conceptric. Members are [[linked]] so the shard resolves the edges",
        "     - the lift IS a forge (dreamer.forge_skill, pointed at the conceptric). -->",
        "", "## Members", "",
    ]
    body = [f"- [[{m}]]" for m in members[:40]]
    return "\n".join(head + body) + "\n"


def lift(repo_root, slug: str, essence: str, members: list[str], parent_hint: str = ""):
    """Forge one coarse node: write ``conceptric/<slug>.md`` wiring its members. Returns the path."""
    from pathlib import Path

    repo_root = Path(repo_root)
    cdir = repo_root / CONCEPTRIC_DIR
    cdir.mkdir(parents=True, exist_ok=True)
    path = cdir / f"{slug}.md"
    path.write_text(_concept_markdown(slug, essence, members, parent_hint), encoding="utf-8")
    return path


def measure_width(region: str = "src/laplace", repo_root=None, refresh: bool = True) -> dict[str, Any]:
    """The region's width right now (node + orphan count) in the lens's units - the before/after the
    reshape is judged on. The RESULT that certifies, not the proxy."""
    repo_root = _root(repo_root)
    nodes, edges = _graph(repo_root)
    deg = _degree(nodes, edges)
    region_nodes = _region_nodes(nodes, region)
    orphans = sum(1 for n in region_nodes if deg.get(n["id"], 0) == 0)
    return {"region": region, "nodes": len(region_nodes), "orphans": orphans}


def apply_reshape(repo_root, region: str, report: dict[str, Any],
                  judgments: dict[str, dict] | None = None, commit: bool = True) -> dict[str, Any]:
    """Forge the proposed lifts as ``conceptric/<slug>.md`` files (one revertible commit). ``judgments``
    (slug -> sealed verdict) overrides the essence, carves dropped members, and skips incoherent
    concepts; without it the mechanical default essence is used (dry-run / tests). Mutates the tree -
    the conjugate close of ``assess_conceptric``'s open."""
    from pathlib import Path

    from laplace.core import versioning as gitio

    repo_root = Path(repo_root)
    judgments = judgments or {}
    written: list[Path] = []
    forged: list[dict[str, Any]] = []
    for p in report["proposals"]:
        verdict = judgments.get(p["slug"], {})
        if verdict and not verdict.get("coherent", True):
            continue  # the sealed judge rejected it - a co-located group, not a concept
        drop = set(verdict.get("drop", []))
        members = [m for m in p["members"] if m not in drop]
        if len(members) < MIN_SUPPORT:
            continue
        slug = verdict.get("slug") or p["slug"]
        essence = verdict.get("essence") or _default_essence(region, p)
        path = lift(repo_root, slug, essence, members, verdict.get("parent_hint", ""))
        written.append(path)
        forged.append({"slug": slug, "members": len(members), "path": str(path)})
    sha = None
    if commit and written:
        sha = gitio.commit(
            repo_root, written,
            f"conceptric dream: forge {len(written)} coarse nodes in {region}",
        )
    return {"region": region, "forged": forged, "written": [str(w) for w in written], "commit": sha}


# ---------------------------------------------------------------------------
# the recursive R&R loop - dream() generalised to the conceptric, per grade
# ---------------------------------------------------------------------------

def _certify(before: dict, after: dict, faithful: bool, forged: list) -> tuple[bool, str | None]:
    """Certify a reshape BY RESULTS (his close, 2026-06-07), not the proxy: the region must still do
    its job (``shard_faithfulness`` holds) AND the width must actually drop (orphans down). A
    confabulated coarse node - converged on the proxy but wrong - FAILS here: it breaks a pointer or
    wires nothing real, so it rescues no orphans / regresses faithfulness, and is reverted. The
    why-not is the residual the next pass chases. ``rho_star`` (his order parameter) drops in as the
    threshold later; today the threshold is 'does the result do its job', which is the real gate."""
    rescued = before["orphans"] - after["orphans"]
    if not forged:
        return False, "no coarse nodes forged (every candidate was carved)"
    if not faithful:
        return False, "faithfulness broke (a pointer or the soul seal regressed)"
    if rescued <= 0:
        return False, "orphans did not drop (the lift wired nothing real)"
    return True, None


def dream_conceptric(repo_root, region: str = "src/laplace", judge=None, recurse: bool = True,
                     max_grade: int = 2, commit: bool = True, _grade: int = 0) -> list[dict[str, Any]]:
    """``dream()`` generalised to conceptric nodes - the recursive consolidating dreamer (N26).

    Per grade: assess (the proxy proposes lifts) -> judge (a sealed dreamer certifies/names/carves;
    optional - ``None`` uses the mechanical defaults) -> apply (forge the coarse nodes, one revertible
    commit - the lift) -> measure width before/after -> certify by results (faithfulness held +
    orphans dropped, else REVERT) -> RECURSE one grade up (the forged concepts are themselves a
    coarser set, so dream the ``conceptric`` region into super-concepts). The orchestrator is a
    dreamer dreaming sub-dreamers, per grade, each running its own close.

    ``judge`` is ``proposals -> {slug: verdict}``; the live run supplies it by spawning sealed
    clean-context agents (E1). Returns the per-grade trace (a list, coarsest grade last)."""
    from laplace.core import versioning as gitio
    from laplace.engine.self_shard import shard_faithfulness

    repo_root = _root(repo_root)
    before = measure_width(region, repo_root=repo_root, refresh=True)
    report = assess_conceptric(region, repo_root=repo_root, refresh=False)
    judgments = judge(report["proposals"]) if judge else None
    res = apply_reshape(repo_root, region, report, judgments=judgments, commit=commit)

    after = measure_width(region, repo_root=repo_root, refresh=True)  # re-shard sees the new files
    faithful = shard_faithfulness(repo_root)["pass"]
    certified, why_not = _certify(before, after, faithful, res["forged"])

    reverted = False
    if commit and res["commit"] and not certified:
        gitio.revert(repo_root, res["commit"])          # converged-but-wrong: undo it, bank the why-not
        after = measure_width(region, repo_root=repo_root, refresh=True)
        reverted = True

    grade = {
        "grade": _grade, "region": region,
        "width_before": before, "width_after": after,
        "orphans_rescued": (before["orphans"] - after["orphans"]) if certified else 0,
        "concepts_forged": len(res["forged"]) if certified else 0,
        "faithfulness_pass": faithful, "certified": certified,
        "reverted": reverted, "why_not": why_not, "commit": res["commit"] if certified else None,
    }
    trace = [grade]
    if recurse and certified and _grade < max_grade and res["forged"]:
        trace += dream_conceptric(repo_root, CONCEPTRIC_DIR, judge=judge, recurse=recurse,
                                  max_grade=max_grade, commit=commit, _grade=_grade + 1)
    return trace


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    region = args[0] if args else "src/laplace"
    rep = assess_conceptric(region, refresh=True)
    print(format_assessment(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
