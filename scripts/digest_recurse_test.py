#!/usr/bin/env python3
"""digest_recurse_test.py - the two-armed standing meter for DP-A2 digests.

The design's one question: does a node's digest carry enough of its members that the descent can
still FIND them? A digest that reads well and retrieves nothing is compression that lost the thing
it compressed, and the only honest way to say so is a number. Two arms measure it:

  ARM 1, member-retrieval (cheap, every digested node). Use the digest TEXT as the query; retrieve
  against the node's own member leaves mixed with distractors drawn from SIBLING clusters. The
  fraction of the node's own members that fail to surface above the distractors IS this arm's
  ``compression_loss``. It runs per node and costs one query embed plus the candidate leaves.
  A node whose own members are ALL named by its digest's ``src_pointers`` is classed
  ``self-retrieval``: the query is quoted out of the documents it is scored against, so its perfect
  recovery is a tautology. Those nodes are counted (``n_self_retrieval``) and reported, and the
  headline ``mean_compression_loss`` is over ``n_scored_nontrivial`` only.

  ARM 2, question-form (the thread-probe shape). Given ``{query, must_reach, top_k}`` run the real
  descent (``recursive_read.descend``) and score reach with ``holdout``'s OWN helpers - the same
  ``_reach`` hit rule and the same ``_thread_status`` baseline law, imported rather than
  re-written, so a verdict here means what a verdict there means. The six red probes in
  ``holdout/THREAD_PROBES.json`` are this arm's live instances.

  Where a node has both, arm 2 is the ordering authority: ``compression_loss`` for ranking work
  comes from the question arm, and arm 1 is the cheap screen underneath it.

WHAT IT DOES NOT DO. It does not mint. It writes exactly one thing - the ``--json`` report, when
asked - and never a store: ``.digests.jsonl`` is read-only here, ``holdout/THREAD_PROBES.json`` is
read and never re-stamped (that is the close's hand, ``sewup.py --only=threads``). The
``--bank-closure`` flag and the env-var dance behind it are GONE: the closure meter's bank seam was
cut out of ``recursive_read.descend`` entirely, so a bench cannot feed the residual ledger at all.

DIGESTS ARE A LENS, NEVER LEAVES (``distillate_lens.py``'s precedent). Nothing here puts digest
text into a shard, a leaf store, or the tree. The digest is a query in arm 1 and is absent from
arm 2 entirely; if arm 2's numbers move, it is because the LENS moved the descent, not because a
digest became content to be clustered.

CALIBRATION. Arm 1's mechanics are calibrated on a planted world whose structure is known
independently of any embedding: ``synthetics papers/synthetics-genesis/genesis/genesis.jsonl`` -
22 rows, two planted partitions (``kind``, semantic: 3 clusters; ``loop``, chronological: 5), and
41 ``evidence_refs`` edges. The stand-in digest there is the node LABEL computed by the same
tf*idf-against-siblings math the fold's essence labeler uses (``meaning_upfold._label``), so the
arm is exercised end to end on ground truth before it is believed on the repo. The semantic
partition is the calibration; the chronological one is the arm's floor (no embedder recovers a
partition by date from text) and is measured to keep that floor visible.

COST LAW. Every run reports VOLUME (how many nodes, leaves, probes - and WHY that n) x RATE (per
unit ms, with the device named). M-minutes are guilty until the arithmetic is shown.

THE KEY IS THE MINT'S, NOT THE METER'S. Where ``laplace.engine.digest_mint`` is importable this harness
uses ITS ``member_sha``, ``leaf_members`` and ``digest_text`` - re-deriving any of them (newline vs
NUL join, direct children vs leaf descendants, bare claim vs claim+objects) would call every row
stale and be confidently wrong. The report always names which key served.

CLI
    --arm {member,question,both,calibrate}   default both
    --nodes  <id,id,...> | digested          default digested (every node in the digest store)
    --probes <id,id,...> | reds | all        default reds (expected_now == "fail")
    --digests <path>                         read a fixture store instead of .digests.jsonl
    --calibrate                              append the genesis calibration to any arm
    --json   <path>                          also write the report there (it always prints)
    --max-members / --distractors / --drift-dial / --beam

ONE BASELINE CAVEAT, stated rather than buried. ``expected_now`` in ``THREAD_PROBES.json`` was
minted against ``embed_router.route`` over the CONCEPTRIC network; arm 2 runs the TREE descent.
The two paths are different organs, so a probe stamped ``pass`` there that misses here is a PATH
DISAGREEMENT and not a regression - it is reported as such (``vs_router_baseline``) and never
enters the exit code. When this arm banks a baseline of its own, that stamp becomes the one it is
scored against; banking it is the orchestrator's hand, not the meter's.

EXIT   0 ran · 1 the harness could not run (no tree, no embedder, no probe file)
       2 an arm-2 probe ERRORed (the descent died) - a meter that half-ran is not a green
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

DIGESTS_FILE = ".digests.jsonl"
GENESIS_FILE = "synthetics papers/synthetics-genesis/genesis/genesis.jsonl"

#: The drift dial, DECLARED (the design's default): exact member_sha serves; Jaccard overlap at or
#: above this serves marked inherited-with-drift; below it the digest is stale.
DRIFT_DIAL = 0.8

#: The keys a digest row may carry its text under. The mint is a sibling packet's hand and may land
#: after this meter, so the reader is tolerant and REPORTS which key served rather than guessing
#: silently. A row with none of them is a defect, not an empty digest.
TEXT_KEYS = ("digest", "text", "digest_text", "claim")

DEFAULT_MAX_MEMBERS = 8      # own members carried into one arm-1 retrieval (cost bound, declared)
DEFAULT_DISTRACTORS = 24     # sibling members mixed in against them (cost bound, declared)

_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "under", "over", "its", "was",
    "are", "not", "but", "has", "had", "have", "been", "were", "which", "their", "them", "then",
    "than", "when", "what", "who", "whom", "does", "did", "own", "one", "two", "per", "via",
    "all", "any", "can", "out", "off", "now", "new", "old", "each", "both", "only", "same",
    "such", "very", "more", "most", "some", "other", "would", "could", "should", "there",
    "here", "where", "how", "why", "it's", "his", "her", "they", "you", "your", "our",
}
_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9_\-]{2,}")


# ---------------------------------------------------------------------------
# small mechanics
# ---------------------------------------------------------------------------

def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000.0, 2)


def member_sha(members: list[str]) -> str:
    """The key half that names a MEMBERSHIP: sha256 over the sorted member ids, newline-joined.

    Declared here in one place because the mint and the meter must agree byte for byte; a report
    always carries this recipe so a disagreement is visible rather than mysterious."""
    return hashlib.sha256("\n".join(sorted(members)).encode("utf-8")).hexdigest()


MEMBER_SHA_RECIPE = 'sha256(("\\n".join(sorted(member_ids))).encode("utf-8")).hexdigest()'


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _stride(seq: list[str], n: int) -> list[str]:
    """Deterministic thinning: evenly-strided picks from a sorted list. No RNG anywhere in this
    harness - two runs on one tree must produce one report."""
    seq = sorted(seq)
    if n <= 0 or len(seq) <= n:
        return seq
    step = len(seq) / float(n)
    return [seq[min(len(seq) - 1, int(i * step))] for i in range(n)]


def _tokens(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text or "")
            if w.lower() not in _STOP and not w.isdigit()]


def _tfidf_label(docs_by_cluster: dict[str, list[str]], cid: str, n: int = 6) -> str:
    """A cluster's essence by tf*idf against its SIBLINGS - the same ranking ``meaning_upfold._label``
    applies to keywords, applied here to the raw member text (the calibration world banks no
    keywords). Model-free by construction."""
    counts = {c: Counter(_tokens(" ".join(docs))) for c, docs in docs_by_cluster.items()}
    n_clusters = max(1, len(counts))
    df = Counter()
    for c in counts:
        df.update(set(counts[c]))
    own = counts.get(cid, Counter())
    if not own:
        return ""
    idf = {w: math.log(n_clusters / (1.0 + df[w])) + 1.0 for w in own}
    ranked = sorted(own, key=lambda w: (-(own[w] * idf[w]), w))
    return " ".join(ranked[:n])


# ---------------------------------------------------------------------------
# arm 1 core - one retrieval, own members against sibling distractors
# ---------------------------------------------------------------------------

def _retrieve(qvec: Any, own: dict[str, Any], distract: dict[str, Any]) -> dict[str, Any]:
    """Rank ``own | distract`` by cosine against ``qvec`` and report what the digest lost.

    ``compression_loss`` is the fraction of the node's OWN members that do not appear in the top
    ``len(own)`` of the mixed ranking - i.e. the members a sibling outranked. It is a fraction of
    the node's own membership, so it is comparable across nodes of different size."""
    rows = []
    for name, vec in own.items():
        rows.append((float(qvec @ vec), name, True))
    for name, vec in distract.items():
        rows.append((float(qvec @ vec), name, False))
    rows.sort(key=lambda r: (-r[0], r[1]))
    n_own = len(own)
    if n_own == 0:
        return {"status": "no-members", "compression_loss": None}
    top = rows[:n_own]
    recovered = sum(1 for r in top if r[2])
    own_scores = [r[0] for r in rows if r[2]]
    dis_scores = [r[0] for r in rows if not r[2]]
    ranks = {r[1]: i + 1 for i, r in enumerate(rows)}
    return {
        "status": "scored",
        "n_own": n_own,
        "n_distractors": len(distract),
        "recovered_at_n_own": recovered,
        "compression_loss": round(1.0 - recovered / n_own, 4),
        "mean_own_score": round(sum(own_scores) / len(own_scores), 4),
        "mean_distractor_score": (round(sum(dis_scores) / len(dis_scores), 4)
                                  if dis_scores else None),
        "margin": (round(sum(own_scores) / len(own_scores)
                         - sum(dis_scores) / len(dis_scores), 4) if dis_scores else None),
        "worst_own_rank": max(ranks[n] for n in own),
        "top_5": [{"id": r[1], "score": round(r[0], 4), "own": r[2]} for r in rows[:5]],
    }


# ---------------------------------------------------------------------------
# the mint's own key and text - BOUND, not re-derived
# ---------------------------------------------------------------------------

def bind_mint(repo_root: Path) -> dict[str, Any]:
    """Bind to ``laplace.engine.digest_mint`` when it is present, and use ITS ``member_sha``,
    ``leaf_members`` and ``digest_text``.

    The mint is the authority on its own key: a meter that re-derived the sha (newline vs NUL join)
    or the membership (direct children vs leaf descendants) would call every row stale and be
    confidently wrong. Where the module is absent the fallbacks below run and the report SAYS the
    key is local, because a number computed under a different recipe must never look like the same
    number.

    Membership comes from the mint's own source (the graded network, ``.self_graded.json``) so the
    meter and the mint compare like with like."""
    try:
        from laplace.engine import digest_mint
    except Exception as exc:  # noqa: BLE001 - the mint may not have landed yet
        return {"source": "local-fallback",
                "detail": f"laplace.engine.digest_mint unavailable ({type(exc).__name__}: {exc})",
                "member_sha": member_sha, "recipe": MEMBER_SHA_RECIPE,
                "members_of": None, "digest_text": None, "dial": DRIFT_DIAL}
    try:
        nodes = digest_mint.load_nodes(repo_root)
    except Exception as exc:  # noqa: BLE001
        return {"source": "local-fallback",
                "detail": f"digest_mint.load_nodes failed ({type(exc).__name__}: {exc})",
                "member_sha": member_sha, "recipe": MEMBER_SHA_RECIPE,
                "members_of": None, "digest_text": None, "dial": DRIFT_DIAL}
    return {
        "source": "laplace.engine.digest_mint",
        "detail": "member_sha, leaf_members and digest_text taken from the mint",
        "member_sha": digest_mint.member_sha,
        "recipe": 'sha256(("\\x00".join(sorted(leaf_descendants))).encode()).hexdigest()',
        "members_of": lambda nid: digest_mint.leaf_members(nodes, nid),
        "digest_text": digest_mint.digest_text,
        "dial": float(getattr(digest_mint, "DRIFT_FLOOR", DRIFT_DIAL)),
        "n_nodes": len(nodes),
    }


# ---------------------------------------------------------------------------
# the digest store (read-only)
# ---------------------------------------------------------------------------

def load_digests(repo_root: Path, path: Path | None = None,
                 digest_text: Any = None) -> dict[str, Any]:
    """Read ``.digests.jsonl``. Absent or empty is a clean, named state - the mint may land after
    this meter, and a harness that crashes on a missing store is a harness nobody runs first.

    ``path`` points the read at a file OTHER than the repo store; it is how arm 1 is exercised
    against a fixture without the meter ever touching the real store."""
    path = path or (repo_root / DIGESTS_FILE)
    if not path.is_file():
        return {"status": "no digests", "detail": f"{path} is absent", "rows": [],
                "defects": []}
    rows, defects = [], []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            defects.append({"line": i, "defect": "unparseable", "detail": str(exc)})
            continue
        text, key = None, None
        if digest_text is not None:
            try:
                cand = digest_text(row)
            except Exception:  # noqa: BLE001 - a row the mint cannot render falls to the keys below
                cand = None
            if isinstance(cand, str) and cand.strip():
                text, key = cand, "digest_mint.digest_text"
        for k in (() if text else TEXT_KEYS):
            if isinstance(row.get(k), str) and row[k].strip():
                text, key = row[k], k
                break
        if text is None:
            defects.append({"line": i, "node_id": row.get("node_id"), "defect": "no-text",
                            "detail": f"row carries none of {TEXT_KEYS}"})
            continue
        # The contract's own defect: a composed digest with nothing to point at.
        if str(row.get("method", "")) == "composed" and not row.get("src_pointers"):
            defects.append({"line": i, "node_id": row.get("node_id"), "defect": "composed-no-src",
                            "detail": 'method="composed" with no src_pointers'})
        row["_text"] = text
        row["_text_key"] = key
        rows.append(row)
    if not rows:
        return {"status": "no digests", "detail": f"{path} banks no usable rows",
                "rows": [], "defects": defects}
    return {"status": "ok", "rows": rows, "defects": defects}


def _serve_verdict(row: dict[str, Any], current: list[str], basis: str, dial: float,
                   sha: Any = None) -> dict[str, Any]:
    """Exact / inherited-with-drift / stale, plus the basis check. ``node_id`` derives from FOUNDING
    membership while accretion moves the CURRENT one, so the pair (node_id, member_sha) is what
    drift detection reads. Banking the stale transition is the orchestrator's hand, never this
    harness's - a drift-serve only FLAGS here."""
    now_sha = (sha or member_sha)(current)
    banked_sha = str(row.get("member_sha", ""))
    out: dict[str, Any] = {"member_sha_banked": banked_sha, "member_sha_now": now_sha,
                           "basis_banked": row.get("basis"), "basis_now": basis,
                           "basis_match": row.get("basis") == basis}
    if banked_sha and banked_sha == now_sha:
        out["serve"] = "exact"
        out["jaccard"] = 1.0
        return out
    banked_members = row.get("members")
    if isinstance(banked_members, list) and banked_members:
        j = _jaccard({str(m) for m in banked_members}, set(current))
        out["jaccard"] = round(j, 4)
        out["dial"] = dial
        out["serve"] = "inherited-with-drift" if j >= dial else "stale"
    else:
        out["jaccard"] = None
        out["serve"] = "stale"
        out["detail"] = ("member_sha differs and the row banks no member list - Jaccard drift "
                         "cannot be computed, so the honest verdict is stale")
    return out


_SERVE_RANK = {"exact": 0, "inherited-with-drift": 1, "stale": 2}


def _select_row(candidates: list[dict[str, Any]], current: list[str], basis: str,
                dial: float, sha: Any = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Which of a node's banked rows SERVES this membership, and its drift verdict."""
    scored = [(r, _serve_verdict(r, current, basis, dial, sha)) for r in candidates]
    scored.sort(key=lambda p: (not p[1]["basis_match"],
                               _SERVE_RANK.get(p[1]["serve"], 3),
                               -(p[1].get("jaccard") or 0.0)))
    return scored[0]


# ---------------------------------------------------------------------------
# ARM 1 on the repo tree
# ---------------------------------------------------------------------------

def _materialize(dsc: Any, names: list[str], missed: list[str]) -> dict[str, Any]:
    """``Descender.materialize`` in bounded batches, skipping (and NAMING) leaves whose source text
    cannot be recovered. A leaf the shard has lost must not become a zero vector."""
    out: dict[str, Any] = {}
    stale: list[str] = []
    for i in range(0, len(names), 32):
        batch = names[i:i + 32]
        try:
            out.update(dsc.materialize(batch, stale, False))
        except Exception:  # noqa: BLE001 - one bad leaf must not cost the batch
            for name in batch:
                try:
                    out.update(dsc.materialize([name], stale, False))
                except Exception as exc:  # noqa: BLE001
                    missed.append(f"{name}: {type(exc).__name__}")
    return out


def _siblings_of(dsc: Any, node_id: str) -> tuple[list[str], str]:
    """The distractor source, in declared order of preference: true siblings (same parent), then
    uncles (the grandparent's other branches), then a strided sample of the corpus. Whichever ran
    is reported, because 'no siblings' changes what the number means."""
    if node_id in dsc.leaf_sha:      # a FILE-grade digest: its peers are its parent's other leaves
        return [dsc.parent_map.get(node_id, "")], "parent-cluster"
    parent = dsc.parent_map.get(node_id)
    sibs = [c for c in dsc.cluster_children.get(parent, ()) if c != node_id]
    if sibs:
        return sibs, "siblings"
    grand = dsc.parent_map.get(parent) if parent is not None else None
    uncles = [c for c in dsc.cluster_children.get(grand, ()) if c not in (node_id, parent)]
    if uncles:
        return uncles, "uncles"
    return [], "corpus"


def _distractor_pool(dsc: Any, node_id: str, n: int, members_of: Any,
                     own: set[str]) -> tuple[list[str], str]:
    sibs, source = _siblings_of(dsc, node_id)
    pool: list[str] = []
    for cid in sorted(sibs):
        pool.extend(m for m in members_of(cid) if m not in own)
    if not pool:
        source = "corpus"
        pool = [leaf for leaf in dsc.leaf_sha if leaf not in own]
    return _stride(pool, n), source


def _self_retrieval(row: dict[str, Any], current: list[str]) -> tuple[bool, int]:
    """``(is this retrieval a tautology, how many files the pointers name)``.

    THE GUARD (the verify wave's cure C2). Arm 1 asks whether a node's digest still FINDS the node's
    members. When the digest's ``src_pointers`` already name every member being retrieved, the query
    is quoted out of the very documents it is scored against and a perfect recovery measures
    nothing - the live headline of 0.3333 was half made of such nodes. They are classed
    ``self-retrieval``, reported, and kept OUT of the headline mean rather than deleted: the number
    is real, it just answers a different question, and a mean that mixes the two answers neither."""
    ptr_files = {str(p[0]) for p in (row.get("src_pointers") or [])
                 if isinstance(p, (list, tuple)) and p}
    return (bool(current) and set(current) <= ptr_files), len(ptr_files)


def arm_member(repo_root: Path, dsc: Any, digests: dict[str, Any], nodes_arg: str,
               max_members: int, n_distractors: int, dial: float,
               mint: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    if digests["status"] != "ok":
        return {"status": digests["status"], "detail": digests["detail"],
                "defects": digests["defects"], "nodes": [], "key": mint["source"]}
    basis = str(dsc.tree.get("lens_hash") or "")
    sha = mint["member_sha"]

    def members_of(nid: str) -> list[str]:
        """The node's membership as the MINT reads it (leaf descendants over the graded network),
        falling back to the tree's direct leaf children when the mint is not importable."""
        fn = mint.get("members_of")
        if fn is not None:
            try:
                # UNFILTERED, exactly as the mint reads it (the re-verify wave's defect: an
                # `in dsc.leaf_sha` filter here dropped every lens-claimed '::' member, so
                # member_sha disagreed with the banked rows on 13/36 nodes and real 'exact'
                # servings classed stale). Members the tree cannot materialize are tolerated
                # downstream: _materialize reports them in `missed`/`unmaterialized`.
                return list(fn(nid))
            except Exception:  # noqa: BLE001
                pass
        return list(dsc.clusters.get(nid, {}).get("members") or [])
    by_node: dict[str, list[dict[str, Any]]] = {}
    for r in digests["rows"]:
        by_node.setdefault(str(r.get("node_id", "")), []).append(r)
    if nodes_arg.strip() == "digested":
        wanted = sorted(by_node)
        why_n = "every node with a row in the digest store"
    else:
        wanted = [x.strip() for x in nodes_arg.split(",") if x.strip()]
        why_n = "the --nodes list"
    rows, embeds, leaves_seen = [], 0, 0
    t_arm = time.perf_counter()
    for node_id in wanted:
        candidates = by_node.get(node_id)
        if not candidates:
            rows.append({"node_id": node_id, "status": "no-digest",
                         "detail": "no row in the digest store for this node"})
            continue
        current = members_of(node_id)
        if node_id not in dsc.clusters and node_id not in dsc.leaf_sha:
            rows.append({"node_id": node_id, "status": "node-absent",
                         "detail": "the node is neither a cluster nor a leaf of the folded tree - "
                                   "its digest cannot be scored against a membership"})
            continue
        # The store is keyed (node_id, member_sha, basis), so a node can carry several LINEAGES.
        # Serving is the contract's own rule and not a coincidence of file order: same basis first,
        # then exact member_sha over drift over stale, then the largest Jaccard.
        row, drift = _select_row(candidates, current, basis, dial, sha)
        tautology, n_ptr_files = _self_retrieval(row, current)
        rec: dict[str, Any] = {"node_id": node_id, "text_key": row["_text_key"],
                               "grade": row.get("grade"), "method": row.get("method"),
                               "n_rows_for_node": len(candidates),
                               "n_src_pointers": len(row.get("src_pointers") or []),
                               "n_src_pointer_files": n_ptr_files,
                               "self_retrieval": tautology,
                               "drift": drift}
        if not current:
            rec.update(status="no-members",
                       detail="the node banks no member leaves (a pure branch) - arm 1 needs "
                              "members to retrieve and does not score")
            rows.append(rec)
            continue
        own_ids = _stride(current, max_members)
        dis_ids, dis_source = _distractor_pool(dsc, node_id, n_distractors, members_of,
                                               set(current))
        missed: list[str] = []
        t0 = time.perf_counter()
        vecs = _materialize(dsc, own_ids + dis_ids, missed)
        leaves_seen += len(vecs)
        embeds += len(vecs)
        qv = np.asarray(dsc.backend.query(row["_text"]), dtype=np.float64)
        embeds += 1
        norm = float(np.linalg.norm(qv))
        if norm == 0.0:
            rec.update(status="query-malformed", detail="the digest text embedded to a zero vector")
            rows.append(rec)
            continue
        qv = qv / norm
        own = {k: v for k, v in vecs.items() if k in set(own_ids)}
        dis = {k: v for k, v in vecs.items() if k in set(dis_ids)}
        rec.update(_retrieve(qv, own, dis))
        rec["distractor_source"] = dis_source
        rec["unmaterialized"] = missed
        rec["ms"] = _ms(t0)
        rows.append(rec)
    scored = [r for r in rows if r.get("compression_loss") is not None]
    trivial = [r for r in scored if r.get("self_retrieval")]
    nontrivial = [r for r in scored if not r.get("self_retrieval")]
    return {
        "status": "ok",
        "why_n": why_n,
        "basis": basis,
        "key": {"source": mint["source"], "detail": mint["detail"],
                "member_sha_recipe": mint["recipe"],
                "membership": ("the mint's leaf descendants over the graded network"
                               if mint.get("members_of") else
                               "the tree's direct leaf children (mint unavailable)")},
        "drift_dial": dial,
        "caps": {"max_members": max_members, "distractors": n_distractors},
        "defects": digests["defects"],
        "nodes": rows,
        "summary": {
            "requested": len(wanted),
            "n_scored": len(scored),
            "n_scored_nontrivial": len(nontrivial),
            "n_self_retrieval": len(trivial),
            "self_retrieval_nodes": sorted(r["node_id"] for r in trivial),
            # THE HEADLINE EXCLUDES SELF-RETRIEVAL (cure C2) - see `_self_retrieval`.
            "mean_compression_loss": (round(sum(r["compression_loss"] for r in nontrivial)
                                            / len(nontrivial), 4) if nontrivial else None),
            "mean_compression_loss_self_retrieval": (
                round(sum(r["compression_loss"] for r in trivial) / len(trivial), 4)
                if trivial else None),
            "mean_compression_loss_all_scored": (round(sum(r["compression_loss"] for r in scored)
                                                       / len(scored), 4) if scored else None),
            "perfect": sum(1 for r in nontrivial if r["compression_loss"] == 0.0),
            "serve": dict(Counter(r["drift"]["serve"] for r in rows if "drift" in r)),
            "reading": ("mean_compression_loss is over the NON-TRIVIAL nodes; a node whose own "
                        "members are all named by its digest's src_pointers is quoting the "
                        "documents it retrieves and is reported separately"),
        },
        "cost": {"embeds": embeds, "leaves": leaves_seen, "ms": _ms(t_arm)},
    }


# ---------------------------------------------------------------------------
# ARM 2 - the question form, scored the way the close scores it
# ---------------------------------------------------------------------------

def _vs_baseline(row: dict[str, Any]) -> str:
    """This descent's verdict against the ROUTER's last banked one. Not a regression check - the
    two are different organs (see the module header); this names the delta and nothing more."""
    was = row.get("was")
    if was not in ("HIT", "MISS"):
        return "no-router-baseline"
    if was == row.get("verdict"):
        return "agree"
    return "descent-only-miss" if was == "HIT" else "descent-only-hit"


def _in_tree(dsc: Any, must_reach: list[str]) -> bool:
    """``holdout._in_corpus``'s question asked of the TREE: is the target even a leaf here? A target
    the fold never ingested cannot be descended to, and calling that a ranking miss mis-names the
    cure."""
    for leaf in dsc.leaf_sha:
        low = str(leaf).lower()
        for frag in must_reach:
            if frag and frag.lower() in low:
                return True
    return False


def arm_question(repo_root: Path, dsc: Any, probes_arg: str, beam: int) -> dict[str, Any]:
    from laplace.engine import holdout

    doc = holdout.load_probes(repo_root)
    if not doc:
        return {"status": "no-probes", "detail": f"{holdout.THREAD_PROBES} is absent/unreadable"}
    probes = list(doc.get("probes") or [])
    sel = probes_arg.strip()
    if sel == "reds":
        chosen = [p for p in probes if str(p.get("expected_now", "fail")) == "fail"]
        why_n = "the probes stamped expected_now=fail (the standing reds)"
    elif sel == "all":
        chosen = probes
        why_n = "every banked thread probe"
    else:
        want = {x.strip() for x in sel.split(",") if x.strip()}
        chosen = [p for p in probes if str(p.get("id")) in want]
        why_n = "the --probes list"
    rows: list[dict[str, Any]] = []
    t_arm = time.perf_counter()
    for probe in chosen:
        pid = str(probe.get("id", "?"))
        query = str(probe.get("query", ""))
        must_reach = [str(x) for x in (probe.get("must_reach") or [])]
        top_k = int(probe.get("top_k") or 5)
        expected = str(probe.get("expected_now", "fail"))
        row: dict[str, Any] = {"id": pid, "expected_now": expected,
                               "was": (doc.get("last_scored") or {}).get("by_id", {}).get(pid)}
        t0 = time.perf_counter()
        try:
            packet = dsc.descend(query, k=top_k, beam=beam, fire="dutiful")
        except Exception as exc:  # noqa: BLE001 - a dead descent is ERROR, never a pass
            row.update(verdict="ERROR", detail=f"{type(exc).__name__}: {exc}")
            row["status_vs_router_baseline"] = holdout._thread_status(row)
            rows.append(row)
            continue
        files = [{"file": h["id"]} for h in packet["hits"]]
        hit = holdout._reach(files, must_reach)
        row["top_k"] = [f["file"] for f in files]
        row["ms"] = _ms(t0)
        row["materialized"] = packet["materialized"]
        row["n_visited_clusters"] = packet["n_visited_clusters"]
        if hit:
            row.update(verdict="HIT", detail=f"reached {hit}", loss=0.0)
        elif not _in_tree(dsc, must_reach):
            row.update(verdict="MISS", loss=1.0,
                       detail="target ABSENT from the folded tree (not ingested) - the cure is a "
                              "re-fold before it is a ranking fix")
        else:
            row.update(verdict="MISS", loss=1.0,
                       detail=f"present in the tree, unreached in top-{top_k} at beam {beam}")
        row["status_vs_router_baseline"] = holdout._thread_status(row)
        row["vs_router_baseline"] = _vs_baseline(row)
        rows.append(row)
    scored = [r for r in rows if r["verdict"] in ("HIT", "MISS")]
    hits = [r for r in scored if r["verdict"] == "HIT"]
    return {
        "status": "ok",
        "why_n": why_n,
        "path": "recursive_read.descend (the tree), scored with holdout._reach / _thread_status",
        "beam": beam,
        "probes": rows,
        "summary": {
            "total": len(rows), "scored": len(scored), "hit": len(hits),
            "red": len(scored) - len(hits),
            "compression_loss": (round((len(scored) - len(hits)) / len(scored), 4)
                                 if scored else None),
            "errors": [r["id"] for r in rows if r["verdict"] == "ERROR"],
            "vs_router_baseline": dict(Counter(r.get("vs_router_baseline", "-")
                                               for r in rows)),
            "descent_only_miss": [r["id"] for r in rows
                                  if r.get("vs_router_baseline") == "descent-only-miss"],
            "descent_only_hit": [r["id"] for r in rows
                                 if r.get("vs_router_baseline") == "descent-only-hit"],
        },
        "baseline": {
            "stamped_by": "embed_router.route over the conceptric network (holdout.score_threads)",
            "this_arm_runs": "recursive_read.descend over .meaning_tree.json",
            "reading": "a disagreement is a PATH difference, not a regression; this arm has no "
                       "banked baseline of its own yet, and banking one is the orchestrator's hand",
        },
        "ordering_authority": "this arm - compression_loss for ordering comes from the question arm",
        "cost": {"descents": len(rows), "ms": _ms(t_arm)},
    }


# ---------------------------------------------------------------------------
# CALIBRATION - arm 1's mechanics on the genesis planted world
# ---------------------------------------------------------------------------

_GENESIS_SKIP = {"g_id", "kind", "loop", "observed_by"}


def _genesis_text(row: dict[str, Any]) -> str:
    parts = [str(v) for k, v in sorted(row.items())
             if k not in _GENESIS_SKIP and isinstance(v, str)]
    refs = row.get("evidence_refs") or []
    if refs:
        parts.append(" ".join(str(r) for r in refs))
    return " ".join(parts)[:2000]


def _calibration_partition(np: Any, backend: Any, field: str, clusters: dict[str, list[str]],
                           texts: dict[str, str], vecs: dict[str, Any], max_members: int,
                           n_distractors: int) -> dict[str, Any]:
    docs = {cid: [texts[m] for m in mem] for cid, mem in clusters.items()}
    out_rows = []
    for cid in sorted(clusters):
        label = _tfidf_label(docs, cid)
        own_ids = _stride(clusters[cid], max_members)
        pool = [m for c, mem in clusters.items() if c != cid for m in mem]
        dis_ids = _stride(pool, n_distractors)
        qv = np.asarray(backend.query(label), dtype=np.float64)
        n = float(np.linalg.norm(qv))
        qv = qv / n if n else qv
        rec = {"node": cid, "label_standin": label, "n_members": len(clusters[cid])}
        rec.update(_retrieve(qv, {i: vecs[i] for i in own_ids},
                             {i: vecs[i] for i in dis_ids}))
        out_rows.append(rec)
    scored = [r for r in out_rows if r.get("compression_loss") is not None]
    margins = [r["margin"] for r in out_rows if r.get("margin") is not None]
    return {
        "field": field,
        "clusters": len(clusters),
        "members_per_cluster": {c: len(m) for c, m in sorted(clusters.items())},
        "nodes": out_rows,
        "scored": len(scored),
        "mean_compression_loss": (round(sum(r["compression_loss"] for r in scored)
                                        / len(scored), 4) if scored else None),
        "perfect": sum(1 for r in scored if r["compression_loss"] == 0.0),
        "mean_margin_own_minus_distractor": (round(sum(margins) / len(margins), 4)
                                             if margins else None),
        "queries_embedded": len(clusters),
    }


def calibrate(repo_root: Path, backend: Any, max_members: int,
              n_distractors: int) -> dict[str, Any]:
    """Run arm 1 against ground truth. The genesis ledger carries TWO planted partitions and they
    are not the same kind of truth, so both are measured:

      ``loop`` - the ledger's own chronology (5 loops). A temporal partition is NOT recoverable
      from text by an embedder, so this is the arm's expected FLOOR, not its failure.
      ``kind``  - prompt / corpus-internal / architecture. A semantic partition, and the one the
      arm is actually supposed to recover.

    A retrieval failure on ``kind`` is the ARM's failure; the gap between the two is the meter
    telling the truth about what a digest-as-query can and cannot separate."""
    import numpy as np

    path = repo_root / GENESIS_FILE
    if not path.is_file():
        return {"status": "absent", "detail": f"{GENESIS_FILE} is missing"}
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_loop: dict[str, list[str]] = {}
    by_kind: dict[str, list[str]] = {}
    texts: dict[str, str] = {}
    for r in rows:
        gid = str(r["g_id"])
        by_loop.setdefault(f"loop::{r['loop']}", []).append(gid)
        by_kind.setdefault(f"kind::{r['kind']}", []).append(gid)
        texts[gid] = _genesis_text(r)

    # the edges, verified: every evidence_refs entry is one row->artifact edge, and an edge whose
    # first token names a path under the genesis root RESOLVES to a file (the rest cite documents
    # by section, e.g. "interrogation_P0.md I1-I12", or name corpus ids with no file of their own).
    root = path.parent.parent
    edges, resolved, targets = 0, 0, set()
    for r in rows:
        for ref in (r.get("evidence_refs") or []):
            edges += 1
            head = str(ref).split()[0] if str(ref).split() else ""
            targets.add(head)
            if head and list(root.glob(f"**/{head}")):
                resolved += 1

    t0 = time.perf_counter()
    all_ids = sorted(texts)
    vecs_raw = backend.embed([texts[i] for i in all_ids])
    vecs = {}
    for name, raw in zip(all_ids, vecs_raw):
        v = np.asarray(raw, dtype=np.float64)
        n = float(np.linalg.norm(v))
        vecs[name] = v / n if n else v
    embed_ms = _ms(t0)

    parts = {
        "kind": _calibration_partition(np, backend, "kind", by_kind, texts, vecs,
                                       max_members, n_distractors),
        "loop": _calibration_partition(np, backend, "loop", by_loop, texts, vecs,
                                       max_members, n_distractors),
    }
    return {
        "status": "ok",
        "world": GENESIS_FILE,
        "planted_truth": "the rows' own fields partition the ledger (`kind` semantic, `loop` "
                         "chronological); labels are tf*idf stand-in digests (model-free), so "
                         "only the ARM is under test",
        "structure": {"rows": len(rows),
                      "kinds": dict(Counter(str(r["kind"]) for r in rows)),
                      "loops": dict(Counter(str(r["loop"]) for r in rows))},
        "edges_verified": {"kind": "evidence_refs (row -> cited artifact)",
                           "count": edges,
                           "rows_with_edges": sum(1 for r in rows if r.get("evidence_refs")),
                           "distinct_targets": len(targets),
                           "edges_resolving_to_a_file_under_the_genesis_root": resolved},
        "partitions": parts,
        "reading": ("arm 1 recovers the SEMANTIC partition and does not recover the chronological "
                    "one; the semantic number is the arm's calibration, the chronological one is "
                    "its floor"),
        "cost": {"embeds": len(all_ids) + sum(p["queries_embedded"] for p in parts.values()),
                 "member_embed_ms": embed_ms,
                 "ms_per_member_embed": round(embed_ms / max(1, len(all_ids)), 2)},
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--arm", choices=("member", "question", "both", "calibrate"), default="both")
    ap.add_argument("--nodes", default="digested",
                    help='comma-separated node ids, or "digested" (every .digests.jsonl row)')
    ap.add_argument("--probes", default="reds",
                    help='comma-separated probe ids, "reds" (expected_now=fail), or "all"')
    ap.add_argument("--digests", default=None,
                    help=f"read the digest store from here instead of <repo>/{DIGESTS_FILE} "
                         f"(a fixture path; the meter never writes either)")
    ap.add_argument("--json", dest="json_out", default=None,
                    help="also write the report to this path (it always prints)")
    ap.add_argument("--calibrate", action="store_true",
                    help="append the genesis calibration to any arm")
    ap.add_argument("--max-members", type=int, default=DEFAULT_MAX_MEMBERS)
    ap.add_argument("--distractors", type=int, default=DEFAULT_DISTRACTORS)
    # DEFAULT None, TESTED `is None` (the verify wave's cure C1). The first form defaulted to
    # DRIFT_DIAL and fell back to the mint's dial whenever `args.drift_dial == DRIFT_DIAL` - so an
    # operator who typed `--drift-dial 0.8` had it silently discarded, and the flag could not
    # express the mint's own default at all. A sentinel that collides with a legal value is not a
    # sentinel.
    ap.add_argument("--drift-dial", type=float, default=None,
                    help=f"the serve dial (default: the mint's DRIFT_FLOOR, else {DRIFT_DIAL})")
    ap.add_argument("--beam", type=int, default=None, help="descent beam (default: the module's)")
    ap.add_argument("--repo-root", default=str(REPO_ROOT))
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    t_total = time.perf_counter()
    report: dict[str, Any] = {
        "tool": "scripts/digest_recurse_test.py",
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "repo_root": str(repo_root),
        "arm": args.arm,
        "arms": {},
    }

    need_tree = args.arm in ("member", "question", "both")
    dsc = None
    backend = None
    t0 = time.perf_counter()
    try:
        from laplace.engine import recursive_read
        if need_tree:
            dsc = recursive_read.open_descender(repo_root)
            backend = dsc.backend
        else:
            from laplace.representation.embed_router import get_backend
            backend = get_backend()
            if backend is None:
                raise RuntimeError("no embedding backend (fastembed absent or the model failed)")
    except Exception as exc:  # noqa: BLE001
        report["status"] = "REFUSED"
        report["detail"] = f"{type(exc).__name__}: {exc}"
        print(json.dumps(report, indent=2))
        return 1
    open_ms = _ms(t0)
    report["device"] = {
        "backend": getattr(backend, "name", "?"),
        "gpu": bool(getattr(backend, "gpu", False)),
        "providers": list(getattr(backend, "providers", []) or []),
        "open_ms": open_ms,
        "what_open_paid_for": ("the .meaning_tree.json parse + the model load"
                               if need_tree else "the model load"),
    }
    if dsc is not None:
        report["tree"] = {"version": dsc.tree.get("version"),
                          "lens_hash": dsc.tree.get("lens_hash"),
                          "n_clusters": len(dsc.clusters), "n_leaves": len(dsc.leaf_sha)}

    exit_code = 0
    if args.arm in ("member", "both"):
        store = Path(args.digests).resolve() if args.digests else None
        mint = bind_mint(repo_root)
        dial = mint["dial"] if args.drift_dial is None else args.drift_dial
        digests = load_digests(repo_root, store, mint.get("digest_text"))
        report["arms"]["member"] = arm_member(repo_root, dsc, digests, args.nodes,
                                              args.max_members, args.distractors, dial, mint)
        report["arms"]["member"]["store"] = str(store or (repo_root / DIGESTS_FILE))
    if args.arm in ("question", "both"):
        beam = args.beam if args.beam is not None else __import__(
            "laplace.engine.recursive_read", fromlist=["DEFAULT_BEAM"]).DEFAULT_BEAM
        block = arm_question(repo_root, dsc, args.probes, beam)
        report["arms"]["question"] = block
        if block.get("summary", {}).get("errors"):
            exit_code = 2
    if args.arm == "calibrate" or args.calibrate:
        report["arms"]["calibration"] = calibrate(repo_root, backend, args.max_members,
                                                  args.distractors)

    # THE COST LAW: volume x rate, device named. Guilty until the arithmetic is shown.
    mem = report["arms"].get("member", {})
    qst = report["arms"].get("question", {})
    cal = report["arms"].get("calibration", {})
    total_ms = _ms(t_total)
    volume = {
        "arm1_nodes": len(mem.get("nodes", []) or []),
        "arm1_leaves_materialized": (mem.get("cost", {}) or {}).get("leaves", 0),
        "arm2_descents": (qst.get("cost", {}) or {}).get("descents", 0),
        "calibration_members": (cal.get("structure", {}) or {}).get("rows", 0),
        "why": {
            "arm1_nodes": mem.get("why_n", "arm not run"),
            "arm2_descents": qst.get("why_n", "arm not run"),
            "arm1_leaves": f"<= max_members({args.max_members}) + distractors({args.distractors}) "
                           f"per node, strided deterministically",
        },
    }
    rate = {
        "device": report["device"]["backend"]
                  + (" [GPU]" if report["device"]["gpu"] else " [CPU]"),
        "open_ms_once": open_ms,
        "arm1_ms_per_node": (round((mem.get("cost", {}) or {}).get("ms", 0)
                                   / max(1, volume["arm1_nodes"]), 2)
                             if volume["arm1_nodes"] else None),
        "arm1_ms_per_leaf": (round((mem.get("cost", {}) or {}).get("ms", 0)
                                   / max(1, volume["arm1_leaves_materialized"]), 2)
                             if volume["arm1_leaves_materialized"] else None),
        "arm2_ms_per_descent": (round((qst.get("cost", {}) or {}).get("ms", 0)
                                      / max(1, volume["arm2_descents"]), 2)
                                if volume["arm2_descents"] else None),
        "calibration_ms_per_member_embed": (cal.get("cost", {}) or {}).get("ms_per_member_embed"),
        "total_ms": total_ms,
    }
    report["cost"] = {"volume": volume, "rate": rate}
    report["status"] = "ok"
    report["exit"] = exit_code

    text = json.dumps(report, indent=2)
    print(text)
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
