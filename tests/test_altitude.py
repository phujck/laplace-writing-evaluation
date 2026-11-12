"""The altitude tower — the resolver's join correctness and the read-only contract.

One substrate viewed at rising altitudes (nodes -> grade-shells -> spine ->
plan/prose). These tests pin the JOIN at every rung — pid -> node ids -> grades
-> beats -> section -> artefact — on a synthetic fixture network (the grade
mechanics in isolation) AND on the live subset-sum-itqde corpus (the real
counts). They also pin the read-only contract: GET serves, POST is refused, an
unknown/traversal corpus is fenced to a 404.

handle() / resolve() are called directly, as test_storyboard_endpoints.py does —
the scanner owns HTTP, the handler owns the contract.
"""

from __future__ import annotations

import json
from pathlib import Path

from laplace.engine import altitude as alt

RR = Path(__file__).resolve().parent.parent
CORPUS = "subset-sum-itqde"


def _get(path: str, **params):
    return alt.handle(path, {k: [v] for k, v in params.items()}, "GET", b"")


def _json(res) -> tuple[int, dict]:
    status, ctype, payload = res
    assert ctype.startswith("application/json")
    return status, json.loads(payload)


# ── the anchor classifier ────────────────────────────────────────────────────

def test_detect_anchor_kinds():
    assert alt.detect_anchor("N5-p2") == {"raw": "N5-p2", "kind": "pid",
                                          "section": "N5", "node": None}
    assert alt.detect_anchor("NA1-p10")["section"] == "NA1"
    assert alt.detect_anchor("N5") == {"raw": "N5", "kind": "section",
                                       "section": "N5", "node": None}
    assert alt.detect_anchor("NA3")["kind"] == "section"
    assert alt.detect_anchor("def:staircase") == {"raw": "def:staircase",
                                                  "kind": "node", "section": None,
                                                  "node": "def:staircase"}
    assert alt.detect_anchor("")["kind"] is None


# ── the grade mechanics on a SYNTHETIC fixture (dep_grade + derivation) ──────

def _fixture_net() -> dict:
    """A tiny hand-built network: a (postulate) -> b -> c, plus d (off a),
    with the spine = [d] so spine elevation lifts d to g_max. Exercises the
    floor, the 1+max rule, and the spine-elevation branch in isolation."""
    nodes = {
        "def:a": {"id": "def:a", "kind": "definition", "essence": "atom $a$",
                  "grade": 0, "projection": {}},
        "res:b": {"id": "res:b", "kind": "result", "essence": "from $a$",
                  "grade": 0, "projection": {"section_ref": "res:spine"}},
        "res:c": {"id": "res:c", "kind": "result", "essence": "from $b$",
                  "grade": 0, "projection": {"section_ref": "res:spine"}},
        "res:spine": {"id": "res:spine", "kind": "result", "essence": "the beat",
                      "grade": 0, "projection": {}},
    }
    edge_index = {
        "res:b": ["def:a"],
        "res:c": ["res:b"],
        # res:spine is dependency-free (depth 0) but spine-elevated to g_max
    }
    return {
        "nodes": nodes,
        "edge_index": edge_index,
        "postulates": {"def:a"},
        "spine": [{"id": "res:spine", "ord": 0, "narrative": "beat"}],
    }


def test_dep_grade_floor_and_chain():
    from laplace.research import corpus_ingest as ci
    net = _fixture_net()
    dg = ci.dep_grade(net)
    assert dg["def:a"] == 0, "a postulate sits at the floor"
    assert dg["res:b"] == 1, "1 + max(dep grades) = 1 + 0"
    assert dg["res:c"] == 2, "1 + max(dep grades) = 1 + 1"
    # spine elevation: res:spine has dep_depth 0 but is lifted to g_max (=2)
    assert dg["res:spine"] == 2, "the spine node is elevated to g_max"


def test_derivation_exposes_grade_setter():
    from laplace.research import corpus_ingest as ci
    net = _fixture_net()
    dg = ci.dep_grade(net)
    d = alt._derivation(net, dg, "res:c")
    assert d["grade"] == 2
    assert d["rule"].startswith("grade = 1 + max")
    dep_ids = {x["id"] for x in d["deps"]}
    assert dep_ids == {"res:b"}
    setter = [x for x in d["deps"] if x["is_grade_setter"]]
    assert [x["id"] for x in setter] == ["res:b"], "the grade-setting dep is flagged"
    # the spine node's derivation names the elevation honestly
    ds = alt._derivation(net, dg, "res:spine")
    assert ds["spine_elevated"] is True
    assert ds["dep_depth"] == 0 and ds["grade"] == 2


# ── the section -> nodes join from % NODES markers (real corpus) ────────────

def test_section_nodes_join_real_corpus():
    from laplace.pipeline import registry
    proj = registry.resolve(CORPUS)
    target = proj.path(proj.target_dir, RR)
    sec = alt.section_nodes(target)
    # the % NODES markers, verified against the live whitepaper (command-checked)
    assert len(sec["N5"]) == 52, "N5 pins 52 nodes"
    assert len(sec["NA1"]) == 59, "NA1 pins 59 nodes"
    assert sec["N1"] == [], "the intro pins no % NODES (written last)"
    assert "def:staircase" in sec["N2"], "N2 claims def:staircase"


# ── the full four-altitude resolve on the LIVE corpus ───────────────────────

def test_resolve_four_altitudes_pid():
    out = alt.resolve(CORPUS, "N5-p2")
    assert out is not None
    assert out["ladder"] == ["nodes", "grade_shells", "spine", "plan_prose"]
    assert out["open_at"] == "nodes"
    assert out["grade_derivation_exposed"] is True
    A = out["altitudes"]
    # altitude 0 — the anchor's nodes (the section's % NODES)
    assert len(A["nodes"]["anchor_ids"]) == 52
    # altitude 1 — grade-shells: floor at 0, spine tier at g_max, live dep_grade
    shells = A["grade_shells"]["shells"]
    assert shells[0]["grade"] == 0 and shells[0]["is_floor"]
    assert shells[-1]["grade"] == out["g_max"] and shells[-1]["is_spine_tier"]
    assert sum(s["global_count"] for s in shells) == out["n_nodes"], \
        "every node lands in exactly one shell"
    # the anchor's nodes are highlighted inside their shells
    highlighted = sum(len(s["anchor_ids"]) for s in shells)
    assert highlighted == 52, "all 52 anchor nodes are placed in a shell"
    # altitude 2 — spine reused from the storyboard rail
    assert len(A["spine"]["rail"]) == 15, "the 15-beat spine rail"
    assert "res:subset-sum-spectral-encoding" in A["spine"]["anchor_beats"]
    # altitude 3 — plan/prose, materialized + stale-aware
    assert A["plan_prose"]["owning_section_id"] == "N5"
    assert "staleness" in A["plan_prose"]["artefact"]
    assert A["plan_prose"]["links"]["review"].endswith(f"corpus={CORPUS}")


def test_resolve_spine_matches_storyboard():
    """The spine altitude REUSES storyboard.enriched_plan — same beat ids, not a
    parallel data layer."""
    from laplace.manuscript import storyboard as sb
    out = alt.resolve(CORPUS, "")
    rail_ids = [b["id"] for b in out["altitudes"]["spine"]["rail"]]
    sb_ids = [b["id"] for b in (sb.enriched_plan(CORPUS) or {})["spine"]]
    assert rail_ids == sb_ids, "the rail is the storyboard's spine, verbatim"


def test_wiring_back_keys_concrete():
    """Every layer carries its concrete join key to the layer below — the
    transparency clause, with VALUES not just labels."""
    out = alt.resolve(CORPUS, "N5-p2")
    w = out["wiring_back"]
    assert w["pid"] == "N5-p2"
    assert len(w["pid_to_nodes"]["node_ids"]) == 52
    assert w["pid_to_nodes"]["section"] == "N5"
    assert set(w["nodes_to_grades"]["grades"]) == set(w["pid_to_nodes"]["node_ids"])
    assert "res:subset-sum-spectral-encoding" in w["grades_to_beats"]["beats"]
    assert w["beats_to_section"]["section"] == "N5"
    assert w["section_to_artefact"]["tex"] == "N5.tex"


def test_grade_derivation_exposed_per_node():
    out = alt.resolve(CORPUS, "def:staircase")
    deriv = out["altitudes"]["grade_shells"]["derivation"]["def:staircase"]
    assert deriv["grade"] >= 0
    assert "deps" in deriv and "rule" in deriv
    # def:staircase derives from something (it is not a floor atom in this corpus)
    if deriv["deps"]:
        assert any("grade" in d for d in deriv["deps"])


def test_grade_mismatch_surfaced_honestly():
    """The stored-vs-derived divergence is EXPOSED, never hidden, and framed
    honestly with the live stored-grade histogram (the Leg-D hard-gate input)."""
    out = alt.resolve(CORPUS, "N5")
    gm = out["altitudes"]["grade_shells"]["grade_mismatch"]
    assert gm["count"] >= 1, "the vestigial stored grade diverges from derived"
    hist = gm["stored_grade_histogram"]
    # the honesty: stored grade is overwhelmingly the 0 containment default
    assert hist.get(0, 0) > sum(v for k, v in hist.items() if k != 0), \
        "the histogram substantiates 'stored is a vestigial default'"
    assert "vestigial" in gm["note"] or "containment default" in gm["note"]
    for row in gm["rows"]:
        assert set(row) == {"id", "stored", "derived"}
        assert row["stored"] != row["derived"]


# ── the read-only HTTP contract ─────────────────────────────────────────────

def test_handle_serves_html():
    res = _get("/altitude")
    status, ctype, body = res
    assert status == 200 and ctype.startswith("text/html")
    assert b"altitude" in body.lower()


def test_handle_data_ok_and_errors():
    status, obj = _json(_get("/altitude/data", corpus=CORPUS, anchor="N5-p2"))
    assert status == 200 and obj["corpus"] == CORPUS
    # missing corpus -> 400
    status, _ = _json(_get("/altitude/data"))
    assert status == 400
    # unknown / traversal corpus -> 404, never a filesystem touch
    status, _ = _json(_get("/altitude/data", corpus="../etc/passwd"))
    assert status == 404
    status, _ = _json(_get("/altitude/data", corpus="no-such-corpus"))
    assert status == 404


def test_handle_is_read_only():
    """No write verb lives on /altitude — a POST is refused (rulings are
    /review's, plan edits are /storyboard's)."""
    res = alt.handle("/altitude/data", {"corpus": [CORPUS]}, "POST", b"{}")
    status, _, _ = res
    assert status == 404, "POST is not a route here — read-only surface"


def test_not_our_path_falls_through():
    assert alt.handle("/storyboard", {}, "GET", b"") is None
    assert alt.handle("/review", {}, "GET", b"") is None
