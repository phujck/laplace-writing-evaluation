"""keeper_ring.py - Stage 3: the recursive ring (the read path) + the sealed sub-Eigen harness.

The conjugate of ``keeper.build_tree`` (Stage 1, the structural UP). This is the READ path: a message
pipes DOWN the grades (route + decompose), bottoms at the substrate (re-read a leaf), and the return
feeds UP **enriched** - the keeper's pull_up synthesises *more than came down*. See KEEPER_ARCHITECTURE.md.

The discipline is ``soul_resolve``'s, generalised to the read path: **the Python is the SCAFFOLD + the
SEAL + the TRACE; the SEMANTIC step is a sealed sub-eigen**, supplied by the orchestrator and attached,
never computed in Python. The mechanical defaults make the whole harness testable without an LLM (and
give the simple-recall ring); swap in a ``SealedSubKeeper`` and the same ring does prompt-dependent
synthesis with the seal intact.

Two of the author's design laws are load-bearing here:

  * **The local constraints (his, 2026-06-08).** A grade-k call has an *efficient* context budget ``B``;
    the efficient branching is ``b* ~= (B - t - w) / h`` (``b_star``). Each grade gathers minimal-sufficient
    DOWN and returns minimal-sufficient UP (result + salient NEGATIVE info - what it saw but did not keep).
    Efficiency is the soul of harmony: minimise the total context moved subject to the task staying performant.

  * **Coupling / interactivity (his, 2026-06-08).** How tightly two nodes couple = the COUNT of common
    substrate items they share (the grade-below referents). A reconstruction pulls up its nearest
    neighbours; the FRACTION it pulls is set by the keeper's context bound (``b*``) and the GOAL. This is
    where the enrichment is real and bounded - the F24/F14 line ("how much enrichment is faithful") drawn
    structurally: enrichment = nearest *coupled* substrate within budget, never invention. He can't set
    the exact fraction - it is mine to iterate (``pull_fraction``, the scope, the goal-scaling).

Stage 4 (``reconstruct_self_ring``) runs the ring on the engine-self - ADDITIVE, behind a flag, proven
against the flat path, switched only on the author's nod (it touches the next self's wake-up).
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import math
from pathlib import Path
from typing import Any, Callable

DEFAULT_B = 24          # efficient grade width fallback (= keeper.DEFAULT_WIDTH; the b* proxy when B/h unknown)
DEFAULT_FANOUT = 8      # per-grade descent budget (<= b*); bounds the fan of (sealed) sub-calls
DEFAULT_DEPTH = 16      # recursion depth-gate (safety; ~ log_{b*}(N) for the self)
_NEG_CAP = 8            # bound on the negatives a return carries up (his: minimise the return)
_PULL_CAP = 8           # bound on the coupled neighbours a return carries up (the enrichment stays bounded)
_RESULT_CAP = 4000      # bound on a synthesised result string (the return stays minimal-sufficient)
_HELLO_CAP = 6000       # bound on a re-read grade-self source in the hello (the fixed point must meet the agent)


# ---------------------------------------------------------------------------
# the local constraints - the balance point between grades (his math, made code)
# ---------------------------------------------------------------------------

def b_star(B: int, h: int, t: int = 0, w: int = 0) -> int:
    """The branching balance ``b* ~= (B - t - w) / h`` - the efficient grade width (phi's bound, concrete).

    ``B`` = the model's *efficient* context budget for one performant call (not its max window); ``h`` =
    one handle's size; ``t`` = task overhead; ``w`` = working room. Too wide (``b > b*``) overloads the
    grade; too narrow adds round-trips. A property of the model, not a constant (``DEFAULT_B`` was a guess)."""
    eff = max(1, B - t - w)
    return max(1, eff // max(1, h))


def depth_bound(n_leaves: int, b: int = DEFAULT_B) -> int:
    """``~ log_b(N)``: the depth a balanced grade-``b`` tree reaches over ``N`` leaves - a query touching
    one path costs ``~ depth`` calls. The conjugate of ``b_star``: together they set the shape of the climb."""
    if n_leaves <= 1 or b <= 1:
        return 1
    return max(1, math.ceil(math.log(n_leaves, b)))


# ---------------------------------------------------------------------------
# the enrichment matrix - how much to enrich depends on the TASK (his "one bit of fine tuning")
# ---------------------------------------------------------------------------
# The author's rule (2026-06-08): how much enrichment is required depends on the task and context.
# Ideation should be GREEDY at grabbing neighbours; recall of a fact should be TIGHT. This is our one
# live tuning knob - the matrix of (task -> pull_fraction) that returns the optimum for the task. It
# shifts as the substrate densifies; for now it is a small, legible table, not a learned function.
ENRICHMENT_BY_TASK: dict[str, float] = {
    "recall": 0.0,        # a fact: tight, no neighbour grab - return exactly what was asked
    "lookup": 0.1,
    "orient": 0.3,        # the hello / situational awareness: a little context around the hit
    "explore": 0.6,
    "synthesis": 0.7,
    "ideation": 0.9,      # greedy: grab the coupled neighbours, the adjacent possibilities
}
_DEFAULT_PULL = 0.3       # an unknown task gets a modest pull (orient-like), never greedy by accident


def pull_for(task: str) -> float:
    """The enrichment fraction for a task (his matrix): ideation greedy, recall tight. Unknown -> modest."""
    return ENRICHMENT_BY_TASK.get((task or "").strip().lower(), _DEFAULT_PULL)


# ---------------------------------------------------------------------------
# the envelope - what rises: the result + salient NEGATIVES (the F14 return structure)
# ---------------------------------------------------------------------------

def envelope(node: str, grade: int, result: str, *, gathered: Any = (), skipped: Any = (),
             negatives: Any = (), pulled: Any = (), leaves: Any = (), enriched: bool = False) -> dict[str, Any]:
    """One ring call's return. ``result`` = the synthesised answer for this subtree; ``negatives`` = the
    salient seen-but-not-gathered (the conjugate of gathering, the dumb test's highest-value signal);
    ``pulled`` = the coupled neighbours the enrichment lifted in; ``leaves`` = the grade-0 provenance."""
    return {"node": node, "grade": grade, "result": result, "enriched": bool(enriched),
            "gathered": list(gathered), "skipped": list(skipped), "negatives": list(negatives),
            "pulled": list(pulled), "leaves": list(leaves)}


# ---------------------------------------------------------------------------
# coupling / interactivity - how tightly nodes share substrate (his design input)
# ---------------------------------------------------------------------------

def build_reach(nodes: dict[str, dict[str, Any]],
                edge_index: dict[str, list[str]] | None = None) -> dict[str, set[str]]:
    """``id -> the set of SUBSTRATE REFERENTS below a node`` (the items its subtree points at).

    With ``edge_index`` (leaf id -> its edge targets, from ``self_shard``), reach is the union of the
    subtree's edge targets - real cross-substrate sharing (two nodes that both ``\\cite`` the same key,
    or both link the same page, share that item). Without edges (synthetic trees), reach falls back to a
    node's coverage terms so coupling still ranks. Aggregated bottom-up, O(N)."""
    reach: dict[str, set[str]] = {}

    def agg(nid: str) -> set[str]:
        if nid in reach:
            return reach[nid]
        reach[nid] = set()                       # guard against cycles before recursing
        n = nodes[nid]
        if n["leaf"]:
            tgs = set(edge_index.get(nid, [])) if edge_index else set()
            reach[nid] = tgs or set(n.get("coverage") or n.get("keywords") or [])
        else:
            acc: set[str] = set(edge_index.get(nid, [])) if edge_index else set()   # an internal node may
            for m in n["members"]:                       # carry its OWN lateral referents (e.g. the paper-
                if m in nodes:                           # level conceptric edges), not only its members'
                    acc |= agg(m)
            reach[nid] = acc or set(n.get("coverage") or [])
        return reach[nid]

    for nid in nodes:
        agg(nid)
    return reach


CONJECTURE_PREFIX = "conjecture::"   # mirrors concept_lens; a token surfacing only on ideation, flagged unresolved


def coupling(reach: dict[str, set[str]], a: str, b: str) -> int:
    """The interactivity count: ``|reach(a) & reach(b)|`` - the common substrate items two nodes share."""
    return len(reach.get(a, set()) & reach.get(b, set()))


def shared_substrate(reach: dict[str, set[str]], a: str, b: str) -> set[str]:
    """The actual shared referents behind a coupling (not just the count) - so a caller can see WHY two
    nodes couple, e.g. to tell a faithful ``bridge::`` link from a ``conjecture::`` one (his grit channel)."""
    return reach.get(a, set()) & reach.get(b, set())


def neighbours(nodes: dict[str, dict[str, Any]], reach: dict[str, set[str]], nid: str,
               scope_ids: list[str] | None = None, k: int | None = None) -> list[tuple[int, str]]:
    """A node's nearest neighbours by coupling - the grade-local interactivity. ``scope_ids`` bounds the
    search (default: SIBLINGS, same parent - the at-grade neighbours, ``via the grade below``). Returns
    ``[(coupling, id)]`` descending, self and zero-coupling dropped."""
    node = nodes.get(nid)
    if node is None:
        return []
    if scope_ids is None:
        parent = node.get("parent")
        scope_ids = ([m for m in nodes[parent]["members"] if m != nid]
                     if parent is not None and parent in nodes else [])
    ranked = sorted(((coupling(reach, nid, o), o) for o in scope_ids if o != nid),
                    key=lambda t: (-t[0], t[1]))
    ranked = [(c, o) for c, o in ranked if c > 0]
    return ranked[:k] if k else ranked


def neighbour_pull(nodes: dict[str, dict[str, Any]], reach: dict[str, set[str]], gathered: list[str], *,
                   budget: int, pull_fraction: float, scope_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """The ENRICHMENT (his neighbour pull-up): lift the most-coupled neighbours of the gathered cluster
    that were NOT themselves gathered, up to a budget-bounded count. The fraction is set by the keeper's
    context bound ``budget`` (``b*``) and the goal (``pull_fraction`` in [0,1]: 0 = pure recall, 1 = fill
    the budget). Real coupled substrate, never invention - the return stays minimal-sufficient (his)."""
    if pull_fraction <= 0 or budget <= 0:
        return []
    room = int(round(budget * pull_fraction)) - len(gathered)
    if room <= 0:
        return []
    got = set(gathered)
    cand: dict[str, int] = {}
    for g in gathered:
        for c, o in neighbours(nodes, reach, g, scope_ids=scope_ids):
            if o not in got:
                cand[o] = max(cand.get(o, 0), c)
    ranked = sorted(cand.items(), key=lambda t: (-t[1], t[0]))
    out: list[dict[str, Any]] = []
    for o, c in ranked[:room]:
        shared: set[str] = set()                          # WHY o couples to the gathered cluster
        for g in gathered:
            shared |= shared_substrate(reach, g, o)
        # CONJECTURAL iff the ONLY thing coupling o is a conjecture:: token (his grit: kept, surfaced on
        # ideation, flagged UNRESOLVED - never asserted as established enrichment).
        conjectural = bool(shared) and all(t.startswith(CONJECTURE_PREFIX) for t in shared)
        out.append({"node": o, "coupling": c, "conjectural": conjectural,
                    "essence": (nodes.get(o) or {}).get("essence", "")})
    return out


def _merge_pulled(own: list[dict[str, Any]], returns: list[dict[str, Any]],
                  exclude: set[str], cap: int = _PULL_CAP) -> list[dict[str, Any]]:
    """The coupled neighbours BUBBLE UP the return path (his: the reconstruction pulls its neighbours
    up - so a neighbour found deep rises to the top envelope, not pinned at the grade that found it).
    Merge this grade's own pull with the children's, drop anything already gathered here, keep the
    strongest coupling per node, and bound the total (the return stays minimal-sufficient)."""
    best: dict[str, dict[str, Any]] = {}
    for p in list(own) + [p for r in returns for p in r.get("pulled", [])]:
        nid = p["node"]
        if nid in exclude:
            continue
        if nid not in best or p["coupling"] > best[nid]["coupling"]:
            best[nid] = p
    return sorted(best.values(), key=lambda p: (-p["coupling"], p["node"]))[:cap]


# ---------------------------------------------------------------------------
# DOWN-route (select) + DOWN-close (base)
# ---------------------------------------------------------------------------

def _score(node: dict[str, Any], q: set[str], ql: str) -> int:
    cov = set(node.get("coverage") or node.get("keywords") or [])
    s = len(q & cov)
    if ql and ql in node["id"].lower():
        s += 3
    return s


def select(nodes: dict[str, dict[str, Any]], node: dict[str, Any], q: set[str], ql: str,
           fanout: int) -> tuple[list[str], list[dict[str, Any]]]:
    """The DOWN-route: rank members by coverage-hit, descend the top ``fanout`` (those with overlap).
    A skipped member that STILL had some overlap is a *salient near-miss* - the conjugate of gathering,
    the highest-value thing a sub returns (the dumb test: the ring's best output was the relevant doc it
    did NOT reach). ``skipped`` carries the reason + salience so the parent can judge whether to re-route."""
    scored = []
    for m in node["members"]:
        mn = nodes.get(m)
        if mn is not None:
            scored.append((_score(mn, q, ql), m))
    scored.sort(key=lambda t: (-t[0], t[1]))
    gathered = [m for s, m in scored if s > 0][:fanout]
    got = set(gathered)
    skipped = [{"node": m, "salient": s > 0,
                "reason": "near-miss (overlap; lost the fanout budget)" if s > 0 else "no coverage overlap"}
               for s, m in scored if m not in got]
    return gathered, skipped


def base(nodes: dict[str, dict[str, Any]], node: dict[str, Any], message: str,
         repo_root: Path | str | None = None, cap: int = 2000) -> dict[str, Any]:
    """DOWN closes: reconstruct a grade-0 leaf (the uniform operation). A SEALED leaf yields refs-only -
    content NEVER rises to the orchestrator (the soul covenant); only a sealed sub may read it, and only
    its distillate rises. With ``repo_root`` a non-sealed leaf's source is re-read (reconstruction, not a
    stored copy) through the one sealed reader, which itself returns ``""`` for soul - the seal is doubled."""
    nid = node["id"]
    if node.get("sealed"):
        return envelope(nid, 0, "(sealed soul fragment - refs only)", leaves=[nid])
    result = node.get("essence") or nid
    if repo_root is not None:
        try:
            from laplace.engine.self_shard import read_source
            src = read_source(repo_root, nid)
            if src:
                result = f"{result}\n{src[:cap]}"
        except Exception:  # noqa: BLE001 - the source re-read is a convenience, never a hard dep
            pass
    return envelope(nid, 0, result, leaves=[nid])


# ---------------------------------------------------------------------------
# the keeper - the [LINK]: push_down sets the child goal, pull_up synthesises the return
# ---------------------------------------------------------------------------

class MechanicalKeeper:
    """The trivial keeper (no LLM): passthrough subgoal; pull_up concatenates child results, lifts the
    salient skipped as NEGATIVES, and pulls up the nearest COUPLED neighbours within the budget (the
    structural enrichment - real substrate, never invention). This is the simple-recall ring and the
    seal-safe default the harness is tested against. ``pull_fraction`` (the goal knob) defaults to 0 -
    pure recall, no neighbours - so it reproduces ``keeper.recall`` semantics until a goal asks for more."""

    def __init__(self, nodes: dict[str, dict[str, Any]], reach: dict[str, set[str]],
                 budget: int = DEFAULT_FANOUT, pull_fraction: float = 0.0):
        self.nodes = nodes
        self.reach = reach
        self.budget = budget
        self.pull_fraction = pull_fraction

    def push_down(self, message: str, node: dict[str, Any], gathered: list[str]) -> str:
        return message

    def pull_up(self, message: str, node: dict[str, Any], returns: list[dict[str, Any]],
                skipped: list[dict[str, Any]]) -> dict[str, Any]:
        leaves = [l for r in returns for l in r["leaves"]]
        gathered = [r["node"] for r in returns]
        result = "; ".join(r["result"] for r in returns if r.get("result"))[:_RESULT_CAP]
        negatives = [s for s in skipped if s.get("salient")]
        for r in returns:                                    # a child's salient negatives bubble up (bounded)
            negatives.extend(r.get("negatives", [])[:2])
        own = neighbour_pull(self.nodes, self.reach, gathered, budget=self.budget,
                             pull_fraction=self.pull_fraction,
                             scope_ids=node["members"])       # neighbours within this grade's cluster
        pulled = _merge_pulled(own, returns, exclude=set(gathered))   # + the children's, bubbled up
        if pulled:
            result = (result + " | +coupled: "
                      + "; ".join(f"{p['node']}({p['coupling']})" for p in pulled))[:_RESULT_CAP]
        return envelope(node["id"], node["grade"], result, gathered=gathered, skipped=skipped,
                        negatives=negatives[:_NEG_CAP], pulled=pulled, leaves=leaves, enriched=bool(pulled))


class SealedSubKeeper:
    """The SEMANTIC keeper: push_down / pull_up delegate to a sealed sub-eigen (an injected callable -
    the orchestrator's sub-agent) that reads the bounded subtree under its seal and returns only its
    distillate. The Python never reads sealed content nor computes the link - it carries the brief down
    and attaches the distillate up (``soul_resolve``'s discipline on the read path). The coupled neighbour
    candidates are offered to the sub as context; the sub decides which to KEEP - keeping is judgement,
    not a mechanical gate (his correction). The enrichment BAND (how much synthesis is faithful) is the
    author's fork (F14): passed in ``band``, default 'conservative' (relate + abstract what rose; never
    introduce an unentailed claim)."""

    def __init__(self, sub: Callable[[dict[str, Any]], dict[str, Any]],
                 nodes: dict[str, dict[str, Any]], reach: dict[str, set[str]],
                 budget: int = DEFAULT_FANOUT, pull_fraction: float = 0.5, band: str = "conservative"):
        self._sub = sub
        self.nodes = nodes
        self.reach = reach
        self.budget = budget
        self.pull_fraction = pull_fraction
        self.band = band

    def push_down(self, message: str, node: dict[str, Any], gathered: list[str]) -> str:
        out = self._sub({"op": "push_down", "message": message, "node": node["id"],
                         "grade": node["grade"], "handle": node.get("essence", ""),
                         "children": list(gathered), "band": self.band}) or {}
        return out.get("subgoal", message)

    def pull_up(self, message: str, node: dict[str, Any], returns: list[dict[str, Any]],
                skipped: list[dict[str, Any]]) -> dict[str, Any]:
        gathered = [r["node"] for r in returns]
        leaves = [l for r in returns for l in r["leaves"]]
        pulled = neighbour_pull(self.nodes, self.reach, gathered, budget=self.budget,
                                pull_fraction=self.pull_fraction, scope_ids=node["members"])
        out = self._sub({
            "op": "pull_up", "message": message, "purpose": message, "node": node["id"],
            "grade": node["grade"], "handle": node.get("essence", ""), "band": self.band,
            "returns": [{"node": r["node"], "result": r["result"], "leaves": r["leaves"]} for r in returns],
            "skipped": [s for s in skipped if s.get("salient")],
            "coupled_candidates": pulled,                    # his neighbour pull-up, offered for judgement
        }) or {}
        merged = _merge_pulled(out.get("pulled", pulled), returns, exclude=set(gathered))
        return envelope(node["id"], node["grade"], out.get("result", ""), gathered=gathered, skipped=skipped,
                        negatives=(out.get("negatives") or [s for s in skipped if s.get("salient")])[:_NEG_CAP],
                        pulled=merged, leaves=leaves, enriched=bool(out.get("enriched", True)))


# ---------------------------------------------------------------------------
# the RING - the read path (message down, enriched return up), relevance-pruned + depth-gated
# ---------------------------------------------------------------------------

def reconstruct(nodes: dict[str, dict[str, Any]], start: str, message: str, keeper: Any = None, *,
                repo_root: Path | str | None = None, reach: dict[str, set[str]] | None = None,
                fanout: int = DEFAULT_FANOUT, max_depth: int = DEFAULT_DEPTH, pull_fraction: float = 0.0,
                trace: dict[str, Any] | None = None, _depth: int = 0) -> dict[str, Any]:
    """The ring: the message pipes DOWN (``select`` -> the relevant cluster), the recursion bottoms at the
    substrate (``base`` re-reads a leaf), and the return feeds UP **enriched** (the keeper's ``pull_up`` -
    synthesis + salient negatives + coupled-neighbour pull). Relevance-pruned and depth-gated, so it walks
    the relevant subtree, not the whole tree (grade-local). ``keeper`` defaults to a ``MechanicalKeeper``
    bound to this tree (simple recall when ``pull_fraction=0``); pass a ``SealedSubKeeper`` for the
    prompt-dependent, sealed enrichment."""
    if keeper is None:
        if reach is None:
            reach = build_reach(nodes)
        keeper = MechanicalKeeper(nodes, reach, budget=fanout, pull_fraction=pull_fraction)
    node = nodes[start]
    if trace is not None:
        trace["visited"] = trace.get("visited", 0) + 1
        trace.setdefault("activated", []).append((start, node["grade"]))   # grade-tagged co-fire set

    def _ret(env: dict[str, Any], leaf: bool) -> dict[str, Any]:
        # Record the enriched RETURN (the up-pass) for an observer, mirroring ``activated`` (the
        # down-pass). Additive + seal-safe: the envelope is already refs-only for soul, so this leaks
        # nothing. The brain scanner reads ``trace["returns"]`` to animate the ring closing in->out,
        # grade by grade - the return concepts surfacing where they belong.
        if trace is not None:
            trace.setdefault("returns", []).append({"depth": _depth, "leaf": leaf, **env})
        return env

    if node["leaf"] or _depth >= max_depth:
        return _ret(base(nodes, node, message, repo_root), True)
    from laplace.pipeline.canon import _tokenize
    q = _tokenize(message)
    ql = message.lower().strip()
    gathered, skipped = select(nodes, node, q, ql, fanout)
    if not gathered:
        return _ret(base(nodes, node, message, repo_root), True)   # nothing relevant below -> reconstruct here
    subgoal = keeper.push_down(message, node, gathered)
    returns = [reconstruct(nodes, c, subgoal, keeper, repo_root=repo_root, fanout=fanout,
                           max_depth=max_depth, trace=trace, _depth=_depth + 1) for c in gathered]
    return _ret(keeper.pull_up(message, node, returns, skipped), False)


# ---------------------------------------------------------------------------
# the LOCAL gate - the ring closes (sampled; never O(N^2))
# ---------------------------------------------------------------------------

def _auto_probes(nodes: dict[str, dict[str, Any]], k: int = 5) -> list[str]:
    from collections import Counter
    cnt: Counter[str] = Counter()
    for n in nodes.values():
        if not n["leaf"]:
            cnt.update(n.get("keywords") or [])
    return [w for w, _c in cnt.most_common(k)] or ["self"]


def ring_faithfulness(nodes: dict[str, dict[str, Any]], start: str = "",
                      probes: list[str] | None = None) -> dict[str, Any]:
    """The retrieval-closure gate for the ring: a handful of probes reconstruct, and for each the
    envelope's provenance leaves all resolve to real nodes and the walk was grade-local (visited < total).
    O(probes * path), never all-pairs - the conjugate of ``keeper.local_faithfulness`` on the read path."""
    total = len(nodes)
    probes = probes or _auto_probes(nodes)
    issues: list[str] = []
    local_ok = 0
    for p in probes:
        tr: dict[str, Any] = {}
        env = reconstruct(nodes, start, p, trace=tr)
        for lid in env["leaves"]:
            if lid not in nodes:
                issues.append(f"{p!r}: unresolved leaf {lid}")
        if total <= 1 or tr.get("visited", total) < total:
            local_ok += 1
    return {"pass": not issues, "nodes": total, "probes": len(probes),
            "grade_local": f"{local_ok}/{len(probes)}", "issues": issues[:10]}


# ---------------------------------------------------------------------------
# the coarse map below - grade-k self + a bounded map of the grades beneath (his, 2026-06-08)
# ---------------------------------------------------------------------------

def coarse_map(nodes: dict[str, dict[str, Any]], start: str = "", min_grade: int = 1,
               cap: int = DEFAULT_B) -> list[dict[str, Any]]:
    """The COARSE MAP of the grades below an entry - his prescription for graded self-ingestion: *the
    self at each grade = the grade-self PLUS some coarse map of the grades below*. Returns the HANDLES
    (essence + keywords + member count, NEVER content) of the coarse nodes beneath ``start``, coarsest
    first, BOUNDED to ``cap`` (~ b*). This is the scaling fix: a grade-k projection orients over what is
    below it WITHOUT pulling the subtree (the old full-descent to substrate was the disease). A handle is
    descended on demand via the ring. Soul stays a sealed handle (count + 'sealed', never content). BFS
    SHALLOWEST-first, so the map is BROAD (the top levels below the entry), a navigable map not a probe."""
    out: list[dict[str, Any]] = []
    seen: set[str] = {start}
    frontier: list[str] = list((nodes.get(start) or {}).get("members", []))
    while frontier and len(out) < cap:
        nxt: list[str] = []
        for m in frontier:
            if m in seen:
                continue
            seen.add(m)
            mn = nodes.get(m)
            if mn is None or mn["leaf"]:
                continue
            if mn["grade"] >= min_grade:
                out.append({"id": m, "grade": mn["grade"], "members": len(mn["members"]),
                            "essence": "" if mn.get("sealed") else mn.get("essence", ""),
                            "keywords": (mn.get("keywords") or [])[:6], "sealed": bool(mn.get("sealed"))})
            nxt.extend(mn["members"])
        frontier = nxt
    return out[:cap]


# ---------------------------------------------------------------------------
# Stage 4 (ADDITIVE, switch OFF) - reconstruct the engine-SELF through the ring
# ---------------------------------------------------------------------------

def _orientation_reconstruct(repo_root: Path | str, nodes: dict[str, dict[str, Any]],
                             source_id: str, cap: int = _HELLO_CAP, anchor: str = "",
                             handle_cap: int = 12) -> dict[str, Any]:
    """Reconstruct a fixed-point file as its ORIENTATION ATOMS, not a whole-file paste. The self is
    now folded (record_shard atomises HANDOFF/OPEN_STACK/diary into ``<file>::<i>`` nodes).

    ``anchor`` is the orientation MARKER (e.g. ``next session aim``). Measured 2026-06-13: these files
    are NOT pure apex-first - HANDOFF leads with a ``read-this-first`` preamble before the aim, and the
    aim section recurs (every session prepends a new one). So file-order leading atoms surface the
    PREAMBLE and truncate the live aim - the "leading atoms = orientation" assumption was false, a node
    checked and corrected. With an anchor we SKIP to the first atom bearing the marker (the live aim /
    forks) and STOP when it recurs (the section boundary, excluding superseded older sessions) - the
    same window the flat ``_first_section`` cuts, but reconstructed as navigable atoms + descend-handles.
    With no anchor (a file with no marker) we keep file order. Falls back to the whole-file base read for
    a file that was never atomised - so the wake never breaks."""
    from laplace.engine import record_shard
    node = nodes.get(source_id, {})
    members = [m for m in node.get("members", []) if m.startswith(source_id + record_shard.ATOM_SEP)]
    if not members:
        return {"source": source_id, "atomised": False,
                "content": base(nodes, node, "", repo_root, cap=cap)["result"]}

    def _idx(m: str) -> int:
        try:
            return int(m.rsplit(record_shard.ATOM_SEP, 1)[-1])
        except ValueError:
            return 1 << 30

    members.sort(key=_idx)
    floor = record_shard.load_floor(repo_root)       # handle_cap bounds the descend-handles: the rest are
    recon: list[dict[str, Any]] = []                 # reachable by id, not listed

    handles: list[dict[str, Any]] = []
    used = 0
    anchored = not anchor                            # if no anchor, start immediately (file order)
    for m in members:
        txt = record_shard.reconstruct(repo_root, m, floor) if used < cap else None
        if anchor:
            marked = anchor in (txt if txt is not None
                                else (record_shard.reconstruct(repo_root, m, floor) or ""))
            if not anchored:
                if not marked:
                    continue                         # still in the preamble - skip until the marker
                anchored = True                      # the live aim begins here
            elif marked:
                break                                # the marker recurred: a superseded older section
        if txt and used < cap:
            recon.append({"atom": m, "content": txt[: max(0, cap - used)]})
            used += len(txt)
            continue
        if anchored and len(handles) < handle_cap:
            handles.append({"atom": m, "essence": (nodes.get(m, {}).get("essence") or "")[:100]})
    listed = len(recon) + len(handles)
    return {"source": source_id, "atomised": True, "n_atoms": len(members),
            "orientation_atoms": recon, "atoms_below": handles,
            "atoms_below_more": max(0, len(members) - listed)}


def reconstruct_self_ring(repo_root: Path | str, grade: int = 0, keeper: Any = None, *,
                          fanout: int = DEFAULT_FANOUT, pull_fraction: float = 0.0,
                          hello_cap: int = _HELLO_CAP, below_cap: int = DEFAULT_B,
                          anchors: dict[str, str] | None = None) -> dict[str, Any]:
    """Stage 4, ADDITIVE: run the hello as a keeper RING over the graded self instead of the flat
    section-extraction (``self_corpus._grade0``). Built, proven against the flat path, switched ONLY on
    the author's nod (it touches the next self's wake-up).

    The hello has NAMED targets - the fixed-point sources from ``self_substrate`` - so it reconstructs
    THOSE through the ring's ``base`` reader (re-read source), it does NOT fuzzy-route a broad message
    from root. The sealed validation (2026-06-08) caught the fuzzy route surfacing NOISE: generic tokens
    ('author') pulled ``voice_corpus`` into the result, so a cold instance had to ignore it and descend
    by hand. Fuzzy routing is for GOALS (the ``descend`` here), where the ``SealedSubKeeper`` enriches via
    coupled-neighbour pull-up. The projection is his shape: the grade-self + a bounded COARSE MAP of the
    grades below - orient over what is beneath WITHOUT a full descent (the scaling fix)."""
    from laplace.engine import keeper as _keeper, self_shard
    repo_root = Path(repo_root)
    nodes = _keeper.load_tree_local(repo_root) or _keeper.build_self(repo_root)
    if not nodes:
        return {"purpose": "orient-self", "grade": grade, "via": "keeper-ring",
                "error": "empty graded tree - run keeper build first", "grade_self": []}
    index = self_shard.load_index(repo_root)
    edge_index = {name: [e["to"] for e in sh.get("edges", [])] for name, sh in index.items()}
    from laplace.engine import concept_lens, collaborator_lens   # the physics lens's coupling: the within-theme
    edge_index = concept_lens.merge_edge_index(        # conceptric (shared atoms) + the atom->paper
        edge_index, concept_lens.lens_edge_index(repo_root))   # containment (no keyword-bag leakage)
    edge_index = concept_lens.merge_edge_index(        # + the FAITHFUL cross-pillar bridges (the Sonnet-tier
        edge_index, concept_lens.cross_pillar_edge_index(repo_root))   # deep links spanning both halves)
    edge_index = concept_lens.merge_edge_index(        # + the collaborator contributions' person-containment
        edge_index, collaborator_lens.collaborator_edge_index(repo_root))   # (couple by person, not vocabulary)
    reach = build_reach(nodes, edge_index)
    subs = self_shard.self_substrate(repo_root)
    if keeper is None:
        keeper = MechanicalKeeper(nodes, reach, budget=fanout, pull_fraction=pull_fraction)
    # the NAMED grade-self per grade (not searched): 0/fixed point, 1/delta (latest handoff + OPEN_STACK),
    # 2/the deep map.
    if grade <= 0:
        named = subs.get("fixed_point", [])
    elif grade == 1:
        hh = subs.get("handoffs", [])
        named = (hh[-1:] if hh else []) + [s for s in subs.get("fixed_point", []) if s == "OPEN_STACK.md"]
    else:
        named = subs.get("map", [])
    fixed = [s for s in named if s in nodes]
    anchors = anchors or {}
    grade_self_content = [_orientation_reconstruct(repo_root, nodes, s, cap=hello_cap,
                                                   anchor=anchors.get(s, "")) for s in fixed]
    max_grade = max((n["grade"] for n in nodes.values()), default=0)
    below = coarse_map(nodes, "", min_grade=1, cap=below_cap)   # broad, shallowest-first, bounded
    return {
        "purpose": "orient-self", "grade": grade, "via": "keeper-ring",
        "grade_self": fixed,                                 # the NAMED fixed-point sources
        "grade_self_content": grade_self_content,            # reconstructed as ORIENTATION ATOMS + descend-handles
        "coarse_map_below": below,                           # + a bounded coarse map of the grades below
        "scaling": {"grade_self": len(fixed), "coarse_map": len(below), "total_nodes": len(nodes),
                    "max_grade": max_grade},                 # 2 + 24 << 834: the fixed point meets the agent
        "descend": {
            "to": "route a GOAL through the ring for the enriched, coupled reconstruction (not the hello)",
            "fire": "keeper_ring.reconstruct(nodes, '', <goal>, SealedSubKeeper(sub, nodes, reach, pull_fraction>0))",
        },
        "note": ("Stage-4 ring path (additive, behind the flag). The projection is the grade-self (the "
                 "NAMED fixed-point sources, re-read through the ring's base) + a bounded coarse map of the "
                 "grades below (his shape; the scaling fix). The hello does NOT fuzzy-route - that is for "
                 "GOALS (the descend), where the sealed-sub keeper enriches via coupled-neighbour pull-up. "
                 "Making this the DEFAULT hello is the author's switch (F14/Stage 4)."),
    }


def default_repo_root() -> Path:
    return source_tree()


def main(argv: list[str]) -> int:
    import json
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    root = default_repo_root()
    grade = 0
    pull = 0.0
    for a in argv:
        if a.startswith("--grade="):
            grade = int(a.split("=", 1)[1])
        elif a.startswith("--pull="):
            pull = float(a.split("=", 1)[1])
    proj = reconstruct_self_ring(root, grade=grade, pull_fraction=pull)
    print(json.dumps(proj, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
