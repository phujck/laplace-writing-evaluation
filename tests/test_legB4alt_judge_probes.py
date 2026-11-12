"""legB4alt — a FRESH ADVERSARIAL JUDGE's probes for the final two Leg-B bites:
B-4 comment-anywhere + the figure gesture (commit 15298e6) and the ALTITUDE
TOWER (commit c834dd1).

Every probe here is FIXTURE-ONLY — the live manuscript tree and the live
feedback ledger are never touched (the canonised run owns them). The probes
either CONFIRM a load-bearing claim or PIN a defect the judge found so the fix
queue has a mechanical anchor.

The headline defect the judge PINNED
(``test_derivation_rule_is_incoherent_for_spine_consumers``) has been FIXED and,
per the judge's own instruction, that characterisation test is deleted and
replaced by the COHERENT assertions below
(``test_derivation_rule_reconciles_for_spine_consumers`` on the isolated fixture,
``test_derivation_coheres_node_by_node_over_full_corpus`` as the recompute idiom
over all 494 live nodes). ``altitude._derivation`` now reads the grade-setter and
the ``1 + max`` rule off each dependency's pre-elevation ``dep_depth`` (the
quantity ``dep_grade`` recurses on), and surfaces spine elevation as its own
explicit step — so the drawer's arithmetic reconciles for every node, the
15-node spine tier and its ~54 consumers included.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from laplace.engine import altitude as alt
from laplace.manuscript import review_surface as rv
from laplace.pipeline.ledger import read_jsonl

pytestmark = pytest.mark.unit


# ===========================================================================
# HEADLINE FINDING — the grade-derivation drawer is INCOHERENT for any node
# that consumes a spine-elevated dependency (altitude._derivation)
# ===========================================================================

def _spine_consumer_net() -> dict:
    """A fixture reproducing the live-corpus pathology in isolation.

    A deep chain ``def:a -> r1 -> r2 -> r3 -> r4`` sets ``g_max = 4``. A
    dependency-free ``res:spine`` is spine-elevated to 4. ``res:consumer``
    depends on ``r1`` (grade 1) and ``res:spine`` (elevated to 4); its OWN
    derivational depth is only 2 (``1 + max(depth r1=1, depth spine=0)``), so
    ``dep_grade`` leaves it at 2 — it is not itself a spine node, so it is not
    elevated.

    The result exposes the bug: ``_derivation`` computes ``is_grade_setter`` and
    the ``rule`` off the deps' ELEVATED grades, so it flags ``res:spine`` (grade
    4) as the grade-setter and prints rule "grade = 1 + max(dependency grades)",
    which would imply grade 5 — while the shown grade is 2, set by ``r1``.
    """
    def n(nid, sr=None):
        return {"id": nid, "kind": "result", "essence": f"body {nid}",
                "grade": 0, "projection": {"section_ref": sr} if sr else {}}
    nodes = {
        "def:a": {"id": "def:a", "kind": "definition", "essence": "atom",
                  "grade": 0, "projection": {}},
        "r1": n("r1"), "r2": n("r2"), "r3": n("r3"), "r4": n("r4"),
        "res:spine": n("res:spine"),
        "res:consumer": n("res:consumer"),
    }
    edge_index = {
        "r1": ["def:a"], "r2": ["r1"], "r3": ["r2"], "r4": ["r3"],
        "res:consumer": ["r1", "res:spine"],
        # res:spine is dependency-free but spine-elevated to g_max
    }
    return {"nodes": nodes, "edge_index": edge_index,
            "postulates": {"def:a"},
            "spine": [{"id": "res:spine", "ord": 0, "narrative": "beat"}]}


def test_spine_elevation_grades_are_as_expected():
    """First pin the grades so the incoherence below is unambiguous."""
    from laplace.research import corpus_ingest as ci
    net = _spine_consumer_net()
    dg = ci.dep_grade(net)
    assert dg["r4"] == 4 and max(dg.values()) == 4, "the deep chain sets g_max=4"
    assert dg["res:spine"] == 4, "the dependency-free spine node is elevated to g_max"
    assert dg["res:consumer"] == 2, "the consumer's real derivational grade is 2 (via r1)"


def test_derivation_rule_reconciles_for_spine_consumers():
    """COHERENT REPLACEMENT (the judge's instruction) for the deleted
    ``test_derivation_rule_is_incoherent_for_spine_consumers``. For a node that
    consumes a spine-elevated dependency the drawer now RECONCILES: the grade-setter
    is the deepest-DEPTH dep, the rule's arithmetic yields exactly the shown grade,
    and the elevated dep carries its pre-elevation depth so the reader sees why a
    grade-4 dependency did not set a grade-2 consumer.

    For ``res:consumer`` (shown grade 2, deps {r1: grade1/depth1, res:spine:
    grade4/depth0}):
      * the setter is ``r1`` (depth 1), NOT ``res:spine`` (elevated grade 4);
      * ``1 + max(setter dep_depth) == 1 + 1 == 2`` == the shown grade;
      * ``res:spine`` is flagged ``spine_elevated`` and contributes depth 0, not 4;
      * the rule string carries the concrete arithmetic ("… = 1 + 1 = 2").
    """
    from laplace.research import corpus_ingest as ci
    net = _spine_consumer_net()
    dg = ci.dep_grade(net)
    d = alt._derivation(net, dg, "res:consumer")

    assert d["grade"] == 2 and d["dep_depth"] == 2
    assert d["spine_elevated"] is False, "the consumer is not itself a spine node"

    setters = [x for x in d["deps"] if x["is_grade_setter"]]
    assert {x["id"] for x in setters} == {"r1"}, "the DEEPEST-DEPTH dep sets the grade"
    # the stated rule's arithmetic now yields the shown grade — no contradiction
    assert 1 + max(x["dep_depth"] for x in setters) == d["grade"]
    assert d["rule"].startswith("grade = 1 + max") and d["rule"].endswith("= 2")

    # the spine-elevated dep is flagged and contributes its DEPTH, not its grade
    spine_dep = next(x for x in d["deps"] if x["id"] == "res:spine")
    assert spine_dep["spine_elevated"] is True
    assert spine_dep["grade"] == 4 and spine_dep["dep_depth"] == 0
    assert spine_dep["is_grade_setter"] is False, "the elevated dep did NOT set the grade"


def test_derivation_dep_depth_is_the_basis_for_setters():
    """The honest quantity (``dep_depth`` == the real grade before elevation) is now
    what the grade-setter is read off — so the ACTUAL setter ``r1`` (depth 1 ->
    consumer 2) IS flagged and the incidentally-higher elevated grade of
    ``res:spine`` is not mistaken for the setter."""
    from laplace.research import corpus_ingest as ci
    net = _spine_consumer_net()
    dg = ci.dep_grade(net)
    d = alt._derivation(net, dg, "res:consumer")
    assert d["dep_depth"] == 2, "dep_depth is the true (pre-elevation) grade"
    r1 = next(x for x in d["deps"] if x["id"] == "r1")
    assert r1["is_grade_setter"] is True, "the real grade-setter r1 is now flagged"


def _reconcile_node(net: dict, dg: dict, g_max: int, nid: str) -> None:
    """The recompute idiom for ONE node: assert the drawer's rule + setter let a
    reader redo the arithmetic and land on the shown grade. Two stages, matching
    ``dep_grade`` exactly — derivational depth (``1 + max CONTRIBUTED depth``) then
    optional spine elevation to ``g_max`` — surfaced as separate, self-consistent
    steps. The setter reconciles on the CONTRIBUTED depth (what each dep actually
    gave this node under the cycle-guarded DFS), never a dep's elevated grade nor its
    own final depth — the two bases that fail for spine consumers and cycle members.
    """
    d = alt._derivation(net, dg, nid)
    deps = d["deps"]
    setters = [x for x in deps if x["is_grade_setter"]]
    is_free = d["is_postulate"] or not deps
    if is_free:
        assert d["dep_depth"] == 0, f"{nid}: a postulate / dependency-free node has depth 0"
        assert setters == [], f"{nid}: a free node's grade is set by no dependency"
    else:
        max_c = max(x["contributed"] for x in deps)
        assert setters, f"{nid}: a derived node must expose a grade-setter"
        assert all(x["contributed"] == max_c for x in setters), \
            f"{nid}: every setter is a deepest-CONTRIBUTED dep (not highest grade/own-depth)"
        assert d["dep_depth"] == 1 + max_c, \
            f"{nid}: derivational depth = 1 + max(dependency contributed depth) reconciles"
        # each dep's contributed depth never exceeds its own final depth; a cut back-edge
        # is flagged so the reader sees why a deep dep did not set this grade
        for x in deps:
            assert x["contributed"] <= x["dep_depth"]
            assert x["cycle_broken"] == (x["contributed"] < x["dep_depth"])
    # stage 2: the DISPLAYED grade is either the derivational depth, or an explicit
    # spine-elevation to g_max — and the rule string says which, with no contradiction
    if d["spine_elevated"]:
        assert d["grade"] == g_max and d["grade"] > d["dep_depth"], \
            f"{nid}: spine elevation lifts the shown grade to g_max"
        assert "spine-elevated to g_max" in d["rule"], f"{nid}: the rule names the elevation step"
    else:
        assert d["grade"] == d["dep_depth"], \
            f"{nid}: without elevation the shown grade IS the derivational depth"
        assert "spine-elevated" not in d["rule"], f"{nid}: no elevation claimed when none applied"


def test_derivation_coheres_node_by_node_over_full_corpus():
    """FULL-CORPUS COHERENCE (the judge's mandate: the recompute idiom over the
    whole corpus). READ-ONLY: a fresh in-memory corpus network is built and graded;
    the manuscript tree is never written. Every one of the 494 live nodes' drawer
    ``rule`` + ``is_grade_setter`` must let a reader redo the arithmetic and land on
    the shown grade — the pathology the deleted characterisation test pinned (the
    15-node spine tier + its ~54 consumers, plus the ~40 cycle members a naive fix
    would still miss) is proven GONE for ALL nodes.
    """
    from laplace.research import corpus_ingest as ci
    from laplace.pipeline import registry
    name = "subset-sum-itqde"
    rr = Path(__file__).resolve().parents[1]
    if registry.resolve(name) is None:
        pytest.skip("live corpus not registered in this checkout")
    troot = ci.resolve_corpus(rr, name)
    if troot is None:
        pytest.skip("live corpus tex root absent in this checkout")
    net = ci.corpus_network(troot, repo_root=rr, name=name)
    dg = ci.dep_grade(net)
    g_max = max(dg.values(), default=0)
    nodes = net["nodes"]
    assert len(nodes) >= 1
    spine_ids = {s["id"] for s in net.get("spine", [])}
    assert spine_ids, "the corpus has a spine tier to elevate"
    consumers = [nid for nid in nodes
                 if any(dd in spine_ids for dd in ci._dep_ids(net["edge_index"], nid, set(nodes)))]
    for nid in nodes:
        _reconcile_node(net, dg, g_max, nid)
    # the setter's contributed depth is always the max over deps (never a mis-flag off a
    # high elevated grade or a high-but-cut cycle dep)
    for nid in consumers:
        d = alt._derivation(net, dg, nid)
        for x in d["deps"]:
            if x["is_grade_setter"]:
                assert x["contributed"] == max(y["contributed"] for y in d["deps"])

    # the finding's NAMED cycle case, locked: res:classical-hardness-frontier (grade
    # 22) cites thm:…-advantage whose own depth is higher but which contributed 0 as a
    # broken back-edge — so it is NOT the setter, and the arithmetic still lands on 22.
    nid = "res:classical-hardness-frontier"
    if nid in nodes:
        d = alt._derivation(net, dg, nid)
        assert d["grade"] == 22 and d["dep_depth"] == 22
        thm = next((x for x in d["deps"]
                    if x["id"] == "thm:c-shaped-staircase-extraction-advantage"), None)
        if thm is not None:
            assert thm["dep_depth"] > d["dep_depth"], "the cited thm's own depth exceeds the node's"
            assert thm["contributed"] == 0 and thm["cycle_broken"] is True
            assert thm["is_grade_setter"] is False, "a cut back-edge never sets the grade"
        setters = [x for x in d["deps"] if x["is_grade_setter"]]
        assert setters and 1 + max(x["contributed"] for x in setters) == d["grade"]


# ===========================================================================
# B-4 FND-1 — _align_units aligns bodies POSITIONALLY (duplicate pids kept)
# ===========================================================================

def test_align_units_keeps_both_bodies_of_a_duplicate_pid():
    """A fragment can legitimately carry a duplicate ``% <SEC>-pN`` marker. The
    old ``dict(units)`` collapsed it, dropping the first body. The positional
    alignment keeps BOTH occurrences' real text (FND-1)."""
    unitsA = [("N1-p1", "the FIRST body"), ("N1-p1", "the SECOND body")]
    unitsB = [("N1-p1", "the FIRST body"), ("N1-p1", "the SECOND body")]
    rows, tally = rv._align_units(unitsA, unitsB)
    bodies = [r.get("a") for r in rows]
    assert "the FIRST body" in bodies, "the first occurrence's body must survive"
    assert "the SECOND body" in bodies, "the second occurrence's body must survive"
    # the old dict-keyed bug would have shown 'the SECOND body' for BOTH rows
    assert bodies.count("the SECOND body") == 1, "the first body is not clobbered by the dupe"


def test_align_units_dupe_pid_edit_surfaces_the_right_occurrence():
    """When the FIRST occurrence's text changes, the change is reported against
    the first occurrence — not silently attributed to the (unchanged) second."""
    unitsA = [("N1-p1", "original one"), ("N1-p1", "steady two")]
    unitsB = [("N1-p1", "edited one"), ("N1-p1", "steady two")]
    rows, tally = rv._align_units(unitsA, unitsB)
    changed = [r for r in rows if r["status"] == "changed"]
    assert any(r["a"] == "original one" and r["b"] == "edited one" for r in changed), \
        "the real first-occurrence edit surfaces positionally"
    assert all(r["a"] != "steady two" for r in changed), "the steady dupe never leaks as changed"


# ===========================================================================
# B-4 region tier — banked honestly, node=None in findings, never fabricated
# ===========================================================================

_MAIN = ("\\documentclass{article}\\begin{document}\n\\input{N1}\n\\end{document}\n")
_N1 = ("% PLAN:N1\n\\section{Intro}\\label{sec:N1}\n\n% N1-p1\nA sentence.\n")


def _md(tmp_path: Path) -> Path:
    md = tmp_path / "ms"
    md.mkdir(parents=True)
    (md / "main.tex").write_text(_MAIN, encoding="utf-8")
    (md / "N1.tex").write_text(_N1, encoding="utf-8")
    (md / "feedback").mkdir()
    return md


def _comments(md: Path) -> list[dict]:
    p = md / "feedback" / "feedback.jsonl"
    recs = read_jsonl(p) if p.is_file() else []
    return [r for r in recs if r.get("kind") in ("comment", "figure-standard")]


def test_region_record_carries_page_rect_and_never_surfaces_as_node(tmp_path, monkeypatch):
    """A bare-page-region comment banks {page, rect, grade='region'}; the finding
    lists UNANCHORED with node=None even though the pseudo-key is node-shaped."""
    md = _md(tmp_path)
    nm = {"present": True, "fresh": True, "entries": {"N1-p1": [{"page": 1}]}, "coverage": {}}
    monkeypatch.setattr(rv, "nodemap_state", lambda _md: nm)
    res = rv.adjudicate(md, "proj", {"by": "author", 
        "verb": "comment", "page": 7,
        "region": {"page": 7, "x0": 5.0, "y0": 6.0, "x1": 9.0, "y1": 10.0},
        "comment": "margin note far from any node"})
    assert res.get("ok") is True and res.get("grade") == "region"
    rec = _comments(md)[-1]
    assert rec["node_id"] == "region:p7", "the honest page-region pseudo-key, never a fake node"
    anc = rec["anchor"] or {}
    assert anc.get("grade") == "region" and anc.get("region", {}).get("x1") == 9.0

    board = rv.findings(md, "proj")
    reg = [f for f in board["unanchored"] if f.get("grade") == "region"]
    assert len(reg) == 1 and reg[0]["node"] is None
    assert all(g["node"] != "region:p7" for g in board["by_node"]), \
        "the region pseudo-key never masquerades as a conceptric node group"


def test_region_pseudo_key_is_node_shaped_but_forced_unanchored(tmp_path):
    """The pseudo-key matches NODE_ID_RE (so the door accepts it) yet
    _feedback_findings forces node=None on the region grade — the honesty seam."""
    from laplace.pipeline import schema
    assert schema.NODE_ID_RE.match("region:p7"), "the pseudo-key is syntactically node-shaped"


# ===========================================================================
# B-4 figure gesture -> F31 intake (owning_stage='figures')
# ===========================================================================

def test_figure_comment_routes_to_the_figures_stage(tmp_path):
    from laplace.pipeline import propagate
    md = _md(tmp_path)
    rv.adjudicate(md, "proj", {"by": "author", 
        "verb": "comment", "figure": "sweep-panel", "section": "N1",
        "comment": "panel (b) axes swapped"})
    rec = _comments(md)[-1]
    assert rec["kind"] == "figure-standard" and rec["node_id"] == "fig:sweep-panel"
    plan = {"meta": {"project": "proj"},
            "sections": [{"id": "N1", "nodes_in_order": ["fig:sweep-panel"]}]}
    items = propagate.intake_items([rec], plan, {"fig:sweep-panel": {}})
    assert len(items) == 1
    assert items[0]["kind"] == "figure" and items[0]["owning_stage"] == "figures"


def test_comment_kind_routes_as_none_no_work_item(tmp_path):
    """A plain kind='comment' record (the region/node/section tiers) routes to
    None — no generation work — so a live comment never halts the intake door.

    NOTE (judge finding, characterised elsewhere): this depends on
    ``KIND_TO_WORK['comment'] = None`` being present. At the time of writing that
    entry is an UNCOMMITTED working-tree edit to pipeline/schema.py; at the
    committed HEAD 'comment' is ABSENT and intake_items RAISES on it. This test
    asserts the CURRENT (working-tree) behaviour."""
    from laplace.pipeline import propagate, schema
    md = _md(tmp_path)
    rv.adjudicate(md, "proj", {"by": "author", "verb": "comment", "section": "N1", "coarse": True,
                               "comment": "the section drifts"})
    rec = _comments(md)[-1]
    assert rec["kind"] == "comment"
    if "comment" in schema.KIND_TO_WORK:
        items = propagate.intake_items([rec], {"meta": {"project": "proj"},
                                               "sections": [{"id": "N1"}]}, {})
        assert items == [], "a comment routes to None -> no work item, no raise"
    else:  # committed-HEAD reality: unrouted kind halts the door
        with pytest.raises(ValueError):
            propagate.intake_items([rec], {"meta": {"project": "proj"},
                                           "sections": [{"id": "N1"}]}, {})


# ===========================================================================
# ALTITUDE — anchor honesty on adversarial input (no live corpus needed)
# ===========================================================================

def test_detect_anchor_degrades_garbage_to_a_node_never_crashes():
    """A garbage anchor is treated as a node id (resolves to 'missing' downstream,
    never a 400/crash); an empty anchor highlights nothing."""
    assert alt.detect_anchor(")(*&^garbage")["kind"] == "node"
    assert alt.detect_anchor("../etc/passwd")["kind"] == "node"   # not a path touch — just a token
    assert alt.detect_anchor("")["kind"] is None


def test_unknown_and_traversal_corpus_are_fenced_to_404():
    """resolve() returns None for an unregistered / traversal corpus name; the
    handler maps that to 404 with no filesystem touch."""
    assert alt.resolve("../etc/passwd", "N5-p2") is None
    assert alt.resolve("no-such-corpus", "") is None
    import json as _json
    st, _ct, body = alt.handle("/altitude/data",
                               {"corpus": ["../etc/passwd"], "anchor": ["N5"]}, "GET", b"")
    assert st == 404 and "unknown corpus" in _json.loads(body)["error"]


def test_post_is_refused_read_only():
    st, _ct, _b = alt.handle("/altitude/data", {"corpus": ["subset-sum-itqde"]}, "POST", b"{}")
    assert st == 404, "POST is not a route on the read-only tower"


# ===========================================================================
# F3 — trace-up is LIVE for dir-based reviews (dir -> corpus reverse-lookup)
# ===========================================================================

def test_dir_reverse_lookup_resolves_a_registered_manuscript():
    """A dir-based review (/review?dir=…) carries no corpus, so trace-up now passes
    ?dir=; the tower reverse-resolves it to the registered corpus key through the
    same registry fence — the dead ``corpus=&anchor=`` 400 is gone."""
    from laplace.pipeline import registry
    name = "subset-sum-itqde"
    proj = registry.resolve(name)
    if proj is None:
        pytest.skip("live corpus not registered")
    rr = Path(__file__).resolve().parents[1]
    td = proj.resolved_target_dir(rr) or proj.path(proj.target_dir, rr)
    if td is None or not td.is_dir():
        pytest.skip("live manuscript dir absent")
    rel = td.relative_to(rr).as_posix()
    assert alt.corpus_for_dir(rel) == name, "the dir maps back to its corpus key"
    # and the data route accepts dir= and returns the SAME payload corpus= would
    import json as _json
    st, _ct, body = alt.handle("/altitude/data", {"dir": [rel], "anchor": ["N5"]}, "GET", b"")
    assert st == 200, "dir-addressed tower data resolves 200, not a 400"
    payload = _json.loads(body)
    assert payload["corpus"] == name
    assert payload["altitudes"]["grade_shells"]["shells"], "the real tower is built"


def test_dir_reverse_lookup_degrades_honestly_when_unresolvable():
    """A dir that is not a registered manuscript (or is traversal-shaped) does NOT
    resolve — corpus_for_dir returns None and the data route answers a 400 that
    NAMES why, never a silent empty-corpus 400 and never a filesystem touch."""
    assert alt.corpus_for_dir("../etc") is None
    assert alt.corpus_for_dir("synthetics papers/nope/manuscript/whitepaper") is None
    assert alt.corpus_for_dir("") is None
    import json as _json
    st, _ct, body = alt.handle("/altitude/data",
                               {"dir": ["../etc/passwd"], "anchor": ["N5"]}, "GET", b"")
    assert st == 400 and "does not resolve" in _json.loads(body)["error"]
    # neither corpus nor dir -> the honest "required" 400
    st2, _ct2, body2 = alt.handle("/altitude/data", {"anchor": ["N5"]}, "GET", b"")
    assert st2 == 400 and "required" in _json.loads(body2)["error"]


# ===========================================================================
# F4 — a section anchor opens at the NODE substrate (altitude 0), like pid/node
# ===========================================================================

def test_section_anchor_opens_at_the_node_substrate():
    """Every grain that resolves to a node set — pid, node AND section — opens at
    altitude 0 (nodes), the substrate-first landing the report promised; the empty
    anchor alone opens at the spine overview. (Was: section opened at plan_prose.)"""
    from laplace.pipeline import registry
    if registry.resolve("subset-sum-itqde") is None:
        pytest.skip("live corpus not registered")
    assert alt.resolve("subset-sum-itqde", "N5")["open_at"] == "nodes", "section -> nodes"
    assert alt.resolve("subset-sum-itqde", "N5-p2")["open_at"] == "nodes", "pid -> nodes"
    assert alt.resolve("subset-sum-itqde", "def:staircase")["open_at"] == "nodes", "node -> nodes"
    assert alt.resolve("subset-sum-itqde", "")["open_at"] == "spine", "no anchor -> spine overview"


# ===========================================================================
# F5 — the region pseudo-key contract, pinned to the CODE (node=None holds)
# ===========================================================================

def test_region_pseudo_key_stored_only_when_no_section_and_stays_unanchored(tmp_path, monkeypatch):
    """The region tier is reached ONLY when no node/section/paragraph anchor exists,
    so the stored ``node_id`` in a region bank is ALWAYS the ``region:p<page>``
    pseudo-key (the ``section or pseudo`` fallback's ``section`` arm is unreachable
    here — a section present routes to the section tier, grade 'section', instead).
    Either way the honesty contract holds: the finding surfaces with node=None.
    """
    md = _md(tmp_path)
    nm = {"present": True, "fresh": True, "entries": {"N1-p1": [{"page": 1}]}, "coverage": {}}
    monkeypatch.setattr(rv, "nodemap_state", lambda _md: nm)

    # (a) a region WITH a section present -> the SECTION tier claims it (grade
    #     'section'), NOT the region tier; the region pseudo-key is never stored here.
    res_sec = rv.adjudicate(md, "proj", {"by": "author", 
        "verb": "comment", "section": "N1", "coarse": True,
        "region": {"page": 3, "x0": 1.0, "y0": 1.0, "x1": 2.0, "y1": 2.0},
        "comment": "coarse section note that also carried a rect"})
    assert res_sec.get("ok") is True and res_sec.get("grade") == "section"
    assert _comments(md)[-1]["node_id"] == "N1", "a section present -> section-keyed, not region:p"

    # (b) a region with NO section -> the region tier, stored under the pseudo-key
    res_reg = rv.adjudicate(md, "proj", {"by": "author", 
        "verb": "comment", "page": 7,
        "region": {"page": 7, "x0": 5.0, "y0": 6.0, "x1": 9.0, "y1": 10.0},
        "comment": "bare margin note"})
    assert res_reg.get("ok") is True and res_reg.get("grade") == "region"
    assert _comments(md)[-1]["node_id"] == "region:p7", "no section -> the honest region pseudo-key"

    # the honesty contract holds regardless: the region finding is node=None
    board = rv.findings(md, "proj")
    reg = [f for f in board["unanchored"] if f.get("grade") == "region"]
    assert len(reg) == 1 and reg[0]["node"] is None
    assert all(g["node"] != "region:p7" for g in board["by_node"])
