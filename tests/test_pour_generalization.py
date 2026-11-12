"""B16c — the pour, generalized over its four paper-shaped whitelists.

The pour derived a spine only from ``kind == "section"``, a parent only from ``rel == "contains"``,
an edge only from ``rel ∈ {draws, shares}`` and a reconciliation only from ``kind == "result" ∧
group == "literature"``. Each is now the DEFAULT under a declaration the conceptric itself carries
(``arc`` / ``kind_map`` / ``rel_map`` / ``reconcile``), and nothing unmapped is dropped: an unknown
kind lands in KIND_FALLBACK, an unknown relation in REL_FALLBACK, and both are named in the report.

Two belts hold the change honest:

* REGRESSION — falqon and eigenengine carry no declarations, so their poured ledgers must be
  BYTE-IDENTICAL to the pre-change bank in ``tests/fixtures/pour_<corpus>.jsonl`` (id/ts stripped:
  ``rewire_add`` stamps both from the wall clock). Those two are the only projects that worked
  before this change; a diff of the ledgers, not a green verdict, is what proves they still do.
* LOSS — engine-devplan poured 35 add-node records and NOTHING else: 0 spine beats and all 42 of
  its edges silently dropped. It must now pour a declared 4-beat spine and all 42 edges.

Every pour here writes into a TEMPORARY repo root (the registered tex root symlinked in), so no
test touches a banked ledger.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
VOLATILE = ("id", "ts")          # wall-clock stamps rewire_add mints per record


def _pour_module():
    """scripts/ is not a package; load the pour the way its shebang runs it."""
    sys.path.insert(0, str(ROOT / "src"))
    spec = importlib.util.spec_from_file_location(
        "pour_conceptric", ROOT / "scripts" / "pour_conceptric.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pc = _pour_module()

from laplace.pipeline import registry  # noqa: E402  (after the src bootstrap above)


def _repo(tmp_path: Path, corpus: str) -> Path:
    """A tmp repo root carrying only the corpus's tex root (symlinked, never copied), so the
    pour's ledger write lands in tmp and the banked ledger is untouched."""
    proj = registry.resolve(corpus)
    assert proj is not None and proj.tex_root, f"{corpus} is not a registered corpus"
    dst = tmp_path / proj.tex_root
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(ROOT / proj.tex_root, dst)
    return tmp_path


def _ledger(root: Path, corpus: str) -> list[dict]:
    path = root / "corpus_friction" / f"{corpus}.jsonl"
    if not path.is_file():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _normalised(root: Path, corpus: str) -> list[str]:
    out = []
    for rec in _ledger(root, corpus):
        for k in VOLATILE:
            rec.pop(k, None)
        out.append(json.dumps(rec, ensure_ascii=False, sort_keys=True))
    return out


def _write(tmp_path: Path, concept: dict) -> str:
    path = tmp_path / "conceptric_v1.json"
    path.write_text(json.dumps(concept, ensure_ascii=False), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# the regression belt: the two projects that already worked pour byte-identically
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("corpus,conceptric", [
    ("paper_falqon", "paper_falqon/manuscript/conceptric_v1.json"),
    ("eigenengine", "eigenengine/manuscript/conceptric_v1.json"),
])
def test_undeclared_conceptrics_pour_byte_identically(tmp_path, corpus, conceptric):
    root = _repo(tmp_path, corpus)
    report = pc.pour(str(ROOT / conceptric), corpus, str(root))
    assert report["arc_source"] == "legacy:kind==section"
    assert (report["kind_map_source"], report["rel_map_source"],
            report["reconcile_source"]) == ("default", "default", "default")
    banked = (FIXTURES / f"pour_{corpus}.jsonl").read_text(encoding="utf-8").splitlines()
    assert _normalised(root, corpus) == banked


def test_legacy_spine_keeps_its_meta_order_ords(tmp_path):
    """The fallback is the OLD rule verbatim — ord off meta.order, not the list index. falqon's
    section ords collide with its cluster ords, which is why no order heuristic can replace it."""
    root = _repo(tmp_path, "paper_falqon")
    pc.pour(str(ROOT / "paper_falqon/manuscript/conceptric_v1.json"), "paper_falqon", str(root))
    concept = json.loads((ROOT / "paper_falqon/manuscript/conceptric_v1.json")
                         .read_text(encoding="utf-8"))
    order = {n["id"]: int((n.get("meta") or {}).get("order", 0) or 0)
             for n in concept["nodes"] if n["kind"] == "section"}
    beats = [r for r in _ledger(root, "paper_falqon") if r["kind"] == "set-spine"]
    assert beats and {b["node"]: b["ord"] for b in beats} == order


# ---------------------------------------------------------------------------
# the loss belt: engine-devplan, 0 -> 4 beats and 0 -> 42 edges
# ---------------------------------------------------------------------------

DEVPLAN = "synthetics papers/engine-devplan/manuscript/conceptric_v1.json"
DEVPLAN_BEATS = ["stage:V1", "stage:V2", "stage:V3", "stage:V4"]


def test_engine_devplan_pours_its_declared_arc_and_every_edge(tmp_path):
    concept = json.loads((ROOT / DEVPLAN).read_text(encoding="utf-8"))
    root = _repo(tmp_path, "engine-devplan")
    report = pc.pour(str(ROOT / DEVPLAN), "engine-devplan", str(root))

    assert report["arc_source"] == "declared"
    assert report["spine_beats"] == len(DEVPLAN_BEATS) == 4
    # 42 edges, none of them contains/draws/shares: under the old whitelist every one was dropped.
    assert report["conceptric_edge_count"] == 42
    assert report["record_counts_by_kind"]["add-edge"] == 42
    assert report["edges_by_role"] == {"edge": 42}
    assert sum(report["edges_by_role"].values()) == report["conceptric_edge_count"]
    # the fallback is NAMED, never silent: every native rel appears with its count.
    assert sum(row["count"] for row in report["rel_fallbacks"]) == 42
    assert all(row["role"] == pc.REL_FALLBACK for row in report["rel_fallbacks"])
    assert report["edges_dropped"] == []

    recs = _ledger(root, "engine-devplan")
    beats = [r for r in recs if r["kind"] == "set-spine"]
    assert [b["node"] for b in beats] == DEVPLAN_BEATS
    assert [b["ord"] for b in beats] == [0, 1, 2, 3]          # ord is the LIST INDEX
    declared = {b["node"]: b.get("narrative", "") for b in concept["arc"]["beats"]}
    assert {b["node"]: b["narrative"] for b in beats} == declared
    # an untyped add-edge is the confirmed-derives token apply_overlay already applies, so the
    # default axis is never written out (writing it would change bytes, not the graph).
    assert all("axis" not in r for r in recs if r["kind"] == "add-edge")


def test_engine_devplan_banked_ledger_carries_the_repour(tmp_path):
    """The landed state, not just the mechanism: the banked ledger was 35 add-node records and
    nothing else before this change."""
    recs = _ledger(ROOT, "engine-devplan")
    poured = [r for r in recs if r.get("by") == pc.POUR_TAG]
    kinds = {k: sum(1 for r in poured if r["kind"] == k)
             for k in {r["kind"] for r in poured}}
    assert kinds == {"add-node": 35, "set-spine": 4, "add-edge": 42}


def test_engine_devplan_network_reconstructs_the_ordered_spine():
    """The read layer's verdict — a spine beat only exists if corpus_network rebuilds it."""
    from laplace.research import corpus_ingest as ci
    tex_root = ci.resolve_corpus(ROOT, "engine-devplan")
    assert tex_root is not None
    net = ci.corpus_network(tex_root, ROOT, "engine-devplan")
    assert [b["id"] for b in net["spine"]] == DEVPLAN_BEATS


# ---------------------------------------------------------------------------
# superarc: the declaration B16a authored drives the spine
# ---------------------------------------------------------------------------

SUPERARC_DECL = ROOT / "synthetics papers/superarc/conceptric_overlay.json"


def _superarc_conceptric() -> dict:
    """superarc's B16a declaration in the compiled-conceptric shape. Only the node/edge key names
    differ between the two forms (`parent`/`term` vs `meta.parent`/`label`, `node`/`target` vs
    `src`/`dst`); the declarations the pour reads — arc, kind_map — ride across verbatim, which
    is the point of the test. The overlay builder stays the one writer of superarc's ledger."""
    decl = json.loads(SUPERARC_DECL.read_text(encoding="utf-8"))
    nodes = [{"id": decl["goal"]["id"], "kind": decl["goal"]["kind"],
              "label": decl["goal"]["essence"], "meta": {"parent": "paper://"}}]
    nodes += [{"id": n["id"], "kind": n["kind"], "label": n["essence"],
               "meta": {"parent": n["parent"]}} for n in decl["nodes"]]
    edges = [{"src": e["node"], "dst": e["target"], "rel": e["rel"]} for e in decl["edges"]]
    return {"nodes": nodes, "edges": edges, "arc": decl["arc"], "kind_map": decl["kind_map"]}


def test_superarc_declared_arc_pours_a_non_empty_spine(tmp_path):
    concept = _superarc_conceptric()
    declared = [b["node"] for b in concept["arc"]["beats"]]
    root = _repo(tmp_path, "superarc")
    report = pc.pour(_write(tmp_path, concept), "superarc", str(root))

    assert report["arc_source"] == "declared"
    assert report["spine_beats"] == len(declared) > 0
    assert report["kind_map_source"] == "declared"
    beats = [r for r in _ledger(root, "superarc") if r["kind"] == "set-spine"]
    assert [b["node"] for b in beats] == declared
    assert [b["ord"] for b in beats] == list(range(len(declared)))
    # the campaign's native kinds ride the declared map, not the fallback: a claim is a result.
    claims = [n["id"] for n in concept["nodes"] if n["kind"] == "claim"]
    poured = {r["node"]: r.get("node_kind") for r in _ledger(root, "superarc")
              if r["kind"] == "add-node"}
    assert claims and all(poured[c] == "result" for c in claims)
    # its 24 edges use campaign relations (run-over-items, tests-hypothesis, ...) — none of them
    # draws/shares, so the old whitelist poured zero.
    assert report["record_counts_by_kind"]["add-edge"] == len(concept["edges"])


def test_the_pour_never_writes_superarcs_own_ledger(tmp_path):
    """B16a's overlay builder owns corpus_friction/superarc.jsonl; two writers on one ledger is
    the desync class the one-truth wave exists to kill."""
    before = (ROOT / "corpus_friction" / "superarc.jsonl").read_text(encoding="utf-8")
    root = _repo(tmp_path, "superarc")
    pc.pour(_write(tmp_path, _superarc_conceptric()), "superarc", str(root))
    assert (ROOT / "corpus_friction" / "superarc.jsonl").read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# the declarations, exercised one at a time on a synthetic conceptric
# ---------------------------------------------------------------------------

def _synthetic(**extra) -> dict:
    concept = {
        "nodes": [
            {"id": "d", "kind": "domain", "label": "the domain"},
            {"id": "a", "kind": "widget", "label": "A"},
            {"id": "b", "kind": "widget", "label": "B"},
        ],
        "edges": [
            {"src": "d", "dst": "a", "rel": "holds"},
            {"src": "a", "dst": "b", "rel": "leans_on"},
            {"src": "b", "dst": "a", "rel": "chatter"},
        ],
    }
    concept.update(extra)
    return concept


ARC_AB = {"label": "a then b", "beats": [{"node": "a", "narrative": "first"}, {"node": "b"}]}


def test_a_zero_beat_spine_is_a_hard_failure_and_writes_nothing(tmp_path):
    root = _repo(tmp_path, "engine-devplan")     # any registered tex root; the graph is synthetic
    with pytest.raises(pc.PourError) as e:
        pc.pour(_write(tmp_path, _synthetic()), "engine-devplan", str(root))
    assert "ZERO spine beats" in str(e.value)
    assert _ledger(root, "engine-devplan") == []   # validation runs before the ledger is touched


def test_allow_spineless_is_the_explicit_opt_out(tmp_path):
    root = _repo(tmp_path, "engine-devplan")
    report = pc.pour(_write(tmp_path, _synthetic()), "engine-devplan", str(root),
                     allow_spineless=True)
    assert report["spine_beats"] == 0 and report["arc_source"] == "legacy:kind==section"


@pytest.mark.parametrize("beats,msg", [
    ([{"node": "nope"}], "names no node"),
    ([{"node": "a"}, {"node": "a"}], "declared twice"),
])
def test_a_broken_arc_fails_loudly(beats, msg):
    """apply_overlay drops a set-spine on an unknown id silently — the gate has to be here."""
    nodes = {n["id"]: n for n in _synthetic()["nodes"]}
    with pytest.raises(pc.PourError) as e:
        pc._arc_beats({"arc": {"beats": beats}}, nodes)
    assert msg in str(e.value)


def test_narrative_falls_back_through_intent_then_thesis():
    nodes = {"a": {"kind": "widget", "meta": {"intent": "the intent"}},
             "b": {"kind": "widget", "meta": {"thesis": "the thesis"}},
             "c": {"kind": "widget", "meta": {}}}
    beats, source = pc._arc_beats(
        {"arc": {"beats": [{"node": "a", "narrative": "declared"}, {"node": "b"}, {"node": "c"}]}},
        nodes)
    assert source == "declared"
    assert [b["narrative"] for b in beats] == ["declared", "the thesis", ""]
    beats, _ = pc._arc_beats({"arc": {"beats": [{"node": "a"}]}}, nodes)
    assert beats[0]["narrative"] == "the intent"


def test_rel_map_declares_containment_typing_and_drops(tmp_path):
    root = _repo(tmp_path, "engine-devplan")
    concept = _synthetic(arc=ARC_AB, rel_map={"holds": "parent", "leans_on": "supports",
                                              "chatter": "drop"})
    report = pc.pour(_write(tmp_path, concept), "engine-devplan", str(root))

    assert report["rel_map_source"] == "declared"
    assert report["edges_by_role"] == {"parent": 1, "edge": 1, "drop": 1}
    assert report["edges_dropped"] == [{"rel": "chatter", "count": 1}]
    assert report["rel_fallbacks"] == []
    recs = _ledger(root, "engine-devplan")
    parents = {r["node"]: r["parent"] for r in recs if r["kind"] == "add-node"}
    assert parents["a"] == "d"                      # containment came from the declared rel
    edges = [r for r in recs if r["kind"] == "add-edge"]
    assert [(r["node"], r["target"], r.get("axis")) for r in edges] == [("a", "b", "supports")]


def test_an_unmapped_relation_pours_rather_than_vanishing(tmp_path):
    root = _repo(tmp_path, "engine-devplan")
    report = pc.pour(_write(tmp_path, _synthetic(arc=ARC_AB)), "engine-devplan", str(root))
    assert report["edges_by_role"] == {"edge": 3}
    assert sorted(row["rel"] for row in report["rel_fallbacks"]) == ["chatter", "holds", "leans_on"]
    assert report["rel_roles"] == {"chatter": "derives", "holds": "derives",
                                   "leans_on": "derives"}


@pytest.mark.parametrize("declared,msg", [
    ({"holds": "connects"}, "target-bearing axis"),      # a pair family has no single target
    ({"holds": "sideways"}, "target-bearing axis"),
    ("not-a-map", "must be an object"),
])
def test_an_unregistered_rel_map_target_fails_loudly(declared, msg):
    with pytest.raises(pc.PourError) as e:
        pc._rel_map({"rel_map": declared})
    assert msg in str(e.value)


def test_a_kind_map_target_outside_the_logical_taxonomy_fails_loudly():
    from laplace.research import corpus_ingest as ci
    assert "widget" not in ci.LOGICAL_KINDS
    with pytest.raises(pc.PourError) as e:
        pc._kind_map({"kind_map": {"widget": "widget"}})
    assert "outside LOGICAL_KINDS" in str(e.value)
    merged, source = pc._kind_map({"kind_map": {"widget": "result"}})
    assert source == "declared" and merged["widget"] == "result"
    assert merged["domain"] == pc.KIND_MAP["domain"]     # merged OVER the defaults, not replacing


def test_an_unmapped_kind_still_lands_on_the_fallback(tmp_path):
    root = _repo(tmp_path, "engine-devplan")
    report = pc.pour(_write(tmp_path, _synthetic(arc=ARC_AB)), "engine-devplan", str(root))
    assert report["kind_fallbacks"] == ["widget"]
    assert report["kind_translation"]["widget"] == pc.KIND_FALLBACK
    kinds = {r["node"]: r["node_kind"] for r in _ledger(root, "engine-devplan")
             if r["kind"] == "add-node"}
    assert kinds == {"d": "goal", "a": pc.KIND_FALLBACK, "b": pc.KIND_FALLBACK}


def test_reconcile_is_declared_and_its_misses_are_named(tmp_path):
    """The fourth whitelist. A rule that matches a node whose base leaf does not exist must say
    so in the report — the node is added instead, and the pour never pretends it reconciled."""
    root = _repo(tmp_path, "engine-devplan")
    concept = _synthetic(arc=ARC_AB, reconcile=[{"kind": "widget", "leaf": "ref:{id}"}])
    report = pc.pour(_write(tmp_path, concept), "engine-devplan", str(root))
    assert report["reconcile_source"] == "declared"
    assert report["reconciliation"] == []
    assert [m["expected_leaf"] for m in report["reconcile_misses"]] == ["ref:a", "ref:b"]
    added = {r["node"] for r in _ledger(root, "engine-devplan") if r["kind"] == "add-node"}
    assert {"a", "b"} <= added

    with pytest.raises(pc.PourError):
        pc._reconcile_rules({"reconcile": [{"kind": "widget", "leaf": "ref:"}]})


def test_falqon_reconciles_its_literature_under_the_default_rule(tmp_path):
    """The default rule is the old literature branch verbatim, and it still fires."""
    root = _repo(tmp_path, "paper_falqon")
    report = pc.pour(str(ROOT / "paper_falqon/manuscript/conceptric_v1.json"),
                     "paper_falqon", str(root))
    assert report["reconcile_source"] == "default"
    assert len(report["reconciliation"]) == report["record_counts_by_kind"]["edit-essence"] > 0
    assert all(row["tex_walk_leaf"].startswith("ref:") for row in report["reconciliation"])
