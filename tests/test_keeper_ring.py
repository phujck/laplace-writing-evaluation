"""Tests for keeper_ring (Stage 3) - the recursive ring + the sealed sub-Eigen harness.

Contracts: the local constraints compute (b*, depth); DOWN-route gathers within budget and reports
SALIENT NEGATIVES (the seen-but-not-gathered); DOWN closes at a leaf and a SEALED leaf stays refs-only
(the seal doubled); the ring returns a grounded, grade-local envelope and prunes the irrelevant subtree;
coupling counts shared substrate and the enrichment pulls up the nearest COUPLED neighbours within budget
(his interactivity design); a SealedSubKeeper delegates to an injected sub and lifts only its distillate;
and the Stage-4 self-ring surfaces the same fixed-point sources as the flat path (parity, switch off)."""

from __future__ import annotations

from laplace.engine import keeper, keeper_ring


def _leaf(kind, keywords, sealed=False, essence="x"):
    return {"kind": kind, "essence": essence, "keywords": keywords, "sealed": sealed}


# --- the local constraints (his math) ---

def test_b_star_balance():
    # b* = (B - t - w) / h: a 100-budget model with size-10 handles, 20 overhead -> 8 wide
    assert keeper_ring.b_star(B=100, h=10, t=20, w=0) == 8
    assert keeper_ring.b_star(B=10, h=100) == 1                 # never below 1 (a grade holds >=1 child)


def test_depth_bound_is_log():
    assert keeper_ring.depth_bound(1, 8) == 1
    assert keeper_ring.depth_bound(64, 8) == 2                  # log_8(64) = 2
    assert keeper_ring.depth_bound(512, 8) == 3


def test_enrichment_matrix_ideation_greedy_recall_tight():
    # his one tuning knob: ideation grabs neighbours greedily, fact recall stays tight
    assert keeper_ring.pull_for("ideation") > keeper_ring.pull_for("recall")
    assert keeper_ring.pull_for("recall") == 0.0               # a fact: no neighbour grab
    assert keeper_ring.pull_for("ideation") >= 0.8             # greedy
    assert keeper_ring.pull_for("not-a-task") == keeper_ring._DEFAULT_PULL   # unknown -> modest, never greedy


# --- coupling / interactivity (his design input) ---

def test_coupling_counts_shared_substrate():
    leaves = {"a/x.py": _leaf("py", ["k"]), "a/y.py": _leaf("py", ["k"]), "a/z.py": _leaf("py", ["k"])}
    nodes = keeper.build_tree(leaves)
    # edges give real referents: x and y both point at T2 -> coupling 1; z shares nothing
    reach = keeper_ring.build_reach(nodes, {"a/x.py": ["T1", "T2"], "a/y.py": ["T2", "T3"], "a/z.py": ["Q"]})
    assert keeper_ring.coupling(reach, "a/x.py", "a/y.py") == 1
    assert keeper_ring.coupling(reach, "a/x.py", "a/z.py") == 0
    # the coarse node's reach is the union of its subtree's referents
    assert reach["a"] == {"T1", "T2", "T3", "Q"}


def test_neighbours_rank_by_coupling():
    leaves = {f"a/n{i}.py": _leaf("py", ["k"]) for i in range(3)}
    nodes = keeper.build_tree(leaves)
    reach = keeper_ring.build_reach(nodes, {"a/n0.py": ["T", "U"], "a/n1.py": ["T", "U"], "a/n2.py": ["T"]})
    nb = keeper_ring.neighbours(nodes, reach, "a/n0.py")        # siblings ranked by coupling to n0
    assert nb[0][1] == "a/n1.py" and nb[0][0] == 2             # n1 shares {T,U} -> 2 (the nearest)
    assert ("a/n2.py" in [o for _c, o in nb])                  # n2 shares {T} -> 1 (a neighbour, lower)


# --- DOWN-route: gather within budget, report salient negatives ---

def test_select_budgets_and_flags_salient_negatives():
    leaves = {"p/hit1.py": _leaf("py", ["target", "p"]),
              "p/hit2.py": _leaf("py", ["target", "p"]),
              "p/near.py": _leaf("py", ["target", "p"]),
              "p/miss.py": _leaf("py", ["unrelated", "p"])}
    nodes = keeper.build_tree(leaves)
    from laplace.pipeline.canon import _tokenize
    gathered, skipped = keeper_ring.select(nodes, nodes["p"], _tokenize("target"), "target", fanout=2)
    assert len(gathered) == 2                                   # budget respected
    near = next(s for s in skipped if s["node"] == "p/near.py")
    miss = next(s for s in skipped if s["node"] == "p/miss.py")
    assert near["salient"] is True                             # overlapped but lost the budget -> salient
    assert miss["salient"] is False                            # no overlap -> not salient


# --- DOWN closes: the seal is doubled at the leaf ---

def test_base_seals_soul_leaf():
    leaves = {"soul/s.md": _leaf("soul", ["soul"], sealed=True, essence="(sealed)")}
    nodes = keeper.build_tree(leaves)
    env = keeper_ring.base(nodes, nodes["soul/s.md"], "anything")
    assert "refs only" in env["result"].lower()                # content never rises
    assert env["leaves"] == ["soul/s.md"]


# --- the ring: grounded, grade-local, pruned ---

def test_ring_is_grounded_and_grade_local():
    leaves = {"alpha/one.py": _leaf("py", ["widget", "alpha"]),
              "alpha/two.py": _leaf("py", ["widget", "alpha"]),
              "beta/three.py": _leaf("py", ["gadget", "beta"]),
              "beta/four.py": _leaf("py", ["gadget", "beta"])}
    nodes = keeper.build_tree(leaves)
    tr: dict = {}
    env = keeper_ring.reconstruct(nodes, "", "widget", trace=tr)
    assert set(env["leaves"]) == {"alpha/one.py", "alpha/two.py"}   # found A, grounded in real leaves
    assert all(l in nodes for l in env["leaves"])                   # every provenance leaf resolves
    assert not any("beta" in l for l in env["leaves"])              # pruned B
    assert tr["visited"] < len(nodes)                              # grade-local, not a flat scan


def test_ring_default_is_pure_recall_no_neighbours():
    # pull_fraction defaults to 0 -> the ring reproduces simple recall: no coupled neighbours pulled
    leaves = {"a/x.py": _leaf("py", ["q"]), "a/y.py": _leaf("py", ["q"])}
    nodes = keeper.build_tree(leaves)
    env = keeper_ring.reconstruct(nodes, "", "q")
    assert env["pulled"] == [] and env["enriched"] is False


# --- the enrichment: nearest coupled neighbours within budget (his neighbour pull-up) ---

def test_enrichment_pulls_coupled_neighbour_within_budget():
    # x and y hit the query; z does NOT (different keyword) but is COUPLED to x via a shared referent.
    # with pull_fraction>0 the return lifts z (real coupled substrate) - the enrichment, never invention.
    leaves = {"p/x.py": _leaf("py", ["hit", "p"]),
              "p/y.py": _leaf("py", ["hit", "p"]),
              "p/z.py": _leaf("py", ["other", "p"])}
    nodes = keeper.build_tree(leaves)
    reach = keeper_ring.build_reach(nodes, {"p/x.py": ["SHARED"], "p/z.py": ["SHARED"], "p/y.py": ["U"]})
    kp = keeper_ring.MechanicalKeeper(nodes, reach, budget=8, pull_fraction=0.5)
    env = keeper_ring.reconstruct(nodes, "", "hit", kp)
    pulled = {p["node"] for p in env["pulled"]}
    assert "p/z.py" in pulled                                   # the coupled non-hit neighbour rose
    assert env["enriched"] is True


# --- the sealed sub-Eigen harness: delegate the link, lift only the distillate ---

def test_sealed_sub_keeper_delegates_and_lifts_distillate():
    calls = []

    def sub(brief):
        calls.append(brief)
        if brief["op"] == "push_down":
            return {"subgoal": brief["message"]}
        # pull_up: synthesise from the children's returns + the offered coupled candidates
        return {"result": "SYNTH(" + ",".join(r["node"] for r in brief["returns"]) + ")",
                "enriched": True}

    leaves = {"a/x.py": _leaf("py", ["q"]), "a/y.py": _leaf("py", ["q"])}
    nodes = keeper.build_tree(leaves)
    reach = keeper_ring.build_reach(nodes)
    kp = keeper_ring.SealedSubKeeper(sub, nodes, reach, budget=8, pull_fraction=0.5)
    env = keeper_ring.reconstruct(nodes, "", "q", kp)
    assert env["result"].startswith("SYNTH(")                  # the sub's distillate rose
    assert env["enriched"] is True
    ops = {c["op"] for c in calls}
    assert ops == {"push_down", "pull_up"}                      # both hooks fired through the ring
    pu = next(c for c in calls if c["op"] == "pull_up")
    assert "coupled_candidates" in pu and "purpose" in pu       # neighbours offered + purpose carried


def test_sealed_sub_never_receives_sealed_content():
    # a sealed leaf's brief carries only its refs-only marker, never content
    seen = []

    def sub(brief):
        seen.append(brief)
        return {"result": "ok", "enriched": True} if brief["op"] == "pull_up" else {"subgoal": brief["message"]}

    leaves = {"m/code.py": _leaf("py", ["soul"]),
              "m/secret.md": _leaf("soul", ["soul"], sealed=True, essence="(sealed)")}
    nodes = keeper.build_tree(leaves)
    kp = keeper_ring.SealedSubKeeper(sub, nodes, keeper_ring.build_reach(nodes))
    keeper_ring.reconstruct(nodes, "", "soul", kp)
    for brief in seen:
        for r in brief.get("returns", []):
            if r["node"] == "m/secret.md":
                assert "refs only" in r["result"].lower()      # sealed content never reached the sub


# --- the gate ---

def test_ring_faithfulness_gate_passes():
    leaves = {f"d/f{i}.py": _leaf("py", ["alpha" if i % 2 else "beta", f"u{i}"]) for i in range(6)}
    nodes = keeper.build_tree(leaves)
    gate = keeper_ring.ring_faithfulness(nodes)
    assert gate["pass"] is True
    assert gate["grade_local"].split("/")[0] != "0"            # at least some probes stayed grade-local


# --- Stage 4: the self-ring surfaces the same fixed-point sources as the flat path (parity, switch off) ---

def test_self_ring_parity_surfaces_fixed_point(tmp_path):
    (tmp_path / "HANDOFF.md").write_text("# Handoff\n\nthe live entry point\n", encoding="utf-8")
    (tmp_path / "OPEN_STACK.md").write_text("# Open stack\n\n| F1 | a fork | open |\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text('"""A module about widgets."""\n', encoding="utf-8")
    proj = keeper_ring.reconstruct_self_ring(tmp_path, grade=0)
    assert "HANDOFF.md" in proj["grade_self"]                   # the flat path's grade-0 sources...
    assert "OPEN_STACK.md" in proj["grade_self"]                # ...both NAMED as the grade-self
    # the grade-self reconstructs the fixed point as orientation ATOMS (the self is now folded;
    # record_shard atomises HANDOFF/OPEN_STACK), or as whole-file content if a file was never
    # atomised - either way the REAL text is reconstructed, not a route-match.
    handoff = next(g for g in proj["grade_self_content"] if g["source"] == "HANDOFF.md")
    handoff_text = handoff.get("content", "") + " ".join(
        a["content"] for a in handoff.get("orientation_atoms", []))
    assert "live entry point" in handoff_text                   # real content reconstructed, not a route-match
    assert proj["scaling"]["grade_self"] < proj["scaling"]["total_nodes"]   # the fixed point meets the agent
    assert proj["via"] == "keeper-ring" and "coarse_map_below" in proj


def test_coarse_map_is_bounded_handles_no_content():
    # the coarse map below = handles of coarse nodes only (no leaves, no content), bounded
    leaves = {f"top/mid{i}/leaf{j}.py": _leaf("py", [f"k{i}"]) for i in range(3) for j in range(3)}
    nodes = keeper.build_tree(leaves)
    cmap = keeper_ring.coarse_map(nodes, "", min_grade=1, cap=4)
    assert len(cmap) <= 4                                       # bounded (~ b*)
    assert all(h["members"] >= 1 for h in cmap)                # coarse nodes, not leaves
    assert all("content" not in h for h in cmap)               # handles only - never content


def test_coarse_map_seals_soul_handle():
    leaves = {"soul/a.md": _leaf("soul", ["soul"], sealed=True, essence="(sealed)"),
              "soul/b.md": _leaf("soul", ["soul"], sealed=True, essence="(sealed)")}
    nodes = keeper.build_tree(leaves)
    cmap = keeper_ring.coarse_map(nodes, "", min_grade=1, cap=8)
    soul = next((h for h in cmap if h["id"] == "soul"), None)
    assert soul is not None and soul["sealed"] is True and soul["essence"] == ""   # count only, no content
