"""G1 — the typed base. The three atomic ops of the growth-stage arming's typed
base, each landed schema + reducer + build-threading + test in one motion:

  1. set-status — the epistemic status, one home, one enum, with the legacy
     carriers folded through schema.STATUS_ALIASES (reconciliation, not a fourth
     vocabulary).
  2. the axis registry — relation families typed, minted/parsed through one home,
     the wire tokens held stable (concept_lens stops discarding kind/strength).
  3. goal supersede — apply_overlay honours a `supersedes` add-node field so
     exactly one live goal remains; a dangling target is a no-op, record kept.

The base surgery is proven inert by an EXACT round-trip on a real corpus
(subset-sum-itqde): the built network is byte-identical to the pre-change build,
so nothing moves until a new op is actually used.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from laplace.engine import concept_lens as cl
from laplace.research import corpus_ingest as ci
from laplace.engine import keeper
from laplace.pipeline import schema

REPO = Path(__file__).resolve().parents[1]


def _mini_corpus(tmp_path: Path) -> Path:
    """A minimal atomisable paper: main.tex -> one section with one equation.
    Atomising yields paper://, references, sec:intro, eq:one."""
    tex = tmp_path / "tex"
    tex.mkdir()
    (tex / "main.tex").write_text(r"\input{s1}", encoding="utf-8")
    (tex / "s1.tex").write_text(
        "\\section{Intro}\\label{sec:intro}\n"
        "\\begin{equation}\\label{eq:one} a=b \\end{equation}\n",
        encoding="utf-8")
    return tex


# ============================================================ 1. set-status

def test_set_status_end_to_end(tmp_path):
    # rewire -> overlay -> corpus_network -> the built node carries `status`
    tex = _mini_corpus(tmp_path)
    r = ci.rewire_add(tmp_path, "c", {"kind": "set-status", "node": "eq:one",
                                      "value": "proven"})
    assert r.get("ok") and r["record"]["value"] == "proven"
    net = ci.corpus_network(tex, tmp_path, "c")
    assert net["nodes"]["eq:one"]["status"] == "proven"


def test_bad_status_refused_at_rewire_add(tmp_path):
    # a value outside the enum-or-aliases is refused at the write gate
    bad = ci.rewire_add(tmp_path, "c", {"kind": "set-status", "node": "eq:one",
                                        "value": "banana"})
    assert "error" in bad and "resolve to one of" in bad["error"]
    # a canonical value and a known alias both pass the gate
    assert ci.rewire_add(tmp_path, "c", {"kind": "set-status", "node": "eq:one",
                                         "value": "proven"}).get("ok")
    assert ci.rewire_add(tmp_path, "c2", {"kind": "set-status", "node": "eq:one",
                                          "value": "cited"}).get("ok")


def test_status_aliases_fold_correctly():
    # the two carriers reconciled into the one enum (schema.canonical_status)
    assert schema.canonical_status("cited") == "imported"          # gap_ledger/citation
    assert schema.canonical_status("mined") == "exploratory"       # machine-proposal marker
    assert schema.canonical_status("literature_supported") == "imported"   # ingest tier
    assert schema.canonical_status("numerical_check") == "computed"        # ingest tier
    assert schema.canonical_status("motivation") == "exploratory"          # ingest tier
    # enum members pass through, case/space forgiving; unknowns resolve to None
    assert schema.canonical_status("proven") == "proven"
    assert schema.canonical_status("  CONJECTURED ") == "conjectured"
    assert schema.canonical_status("no-such-status") is None
    # every alias target is itself a canonical enum member (the fold closes)
    for target in schema.STATUS_ALIASES.values():
        assert target in schema.EPISTEMIC_STATUSES


def test_aliases_fold_through_the_build(tmp_path):
    # a set-status carrying an alias builds a node wearing the canonical enum value
    tex = _mini_corpus(tmp_path)
    ci.rewire_add(tmp_path, "c", {"kind": "set-status", "node": "eq:one",
                                  "value": "cited"})
    net = ci.corpus_network(tex, tmp_path, "c")
    assert net["nodes"]["eq:one"]["status"] == "imported"


def test_set_status_threads_through_build_tree():
    # the keeper threading, in isolation: a leaf's status travels onto the built node
    leaves = {"a": {"kind": "result", "essence": "e", "keywords": [], "status": "computed"},
              "b": {"kind": "result", "essence": "e", "keywords": []}}
    nodes = keeper.build_tree(leaves, lambda n: None, root_id="root")
    assert nodes["a"]["status"] == "computed"
    assert "status" not in nodes["b"]           # only present when the leaf carries it


def test_set_status_registered_in_the_vocabulary():
    assert "set-status" in schema.REWIRE_KINDS
    assert ci._REWIRE_KINDS is schema.REWIRE_KINDS      # identity, not a copy


# ============================================================ 2. the axis registry

def test_axis_minter_parser_round_trip_every_row():
    # every registry row round-trips through the one minter/parser
    for row in schema.AXES:
        ax = row["axis"]
        if row.get("pair"):                             # the conn:: kind/strength grammar
            t = schema.token_for(ax, lo="p:a", hi="p:b", atoms="x|y",
                                 kind="shared-mechanism", strength="high")
            assert schema.parse_edge_token(t) == {
                "axis": ax, "lo": "p:a", "hi": "p:b", "atoms": "x|y",
                "kind": "shared-mechanism", "strength": "high"}
            # strengthless mint is the prior 4-field form, byte-identical
            t0 = schema.token_for(ax, lo="p:a", hi="p:b", atoms="x|y", kind="k",
                                 strength="")
            assert t0 == "conn::p:a<->p:b::x|y::k"
            assert schema.parse_edge_token(t0)["strength"] == ""
        elif row.get("modes"):                          # derives: the mode is the prefix
            for m in row["modes"]:
                t = schema.token_for(ax, "eq:x", mode=m)
                assert schema.parse_edge_token(t) == {"axis": ax, "target": "eq:x",
                                                      "mode": m}
            assert schema.token_for("derives", "eq:x", mode="confirmed") == "confirmed::eq:x"
        else:                                           # target-bearing prefix families
            t = schema.token_for(ax, "n:1")
            assert schema.parse_edge_token(t) == {"axis": ax, "target": "n:1"}


def test_parse_edge_token_bare_referent_is_none():
    # a plain node id / bib key is not an axis token
    assert schema.parse_edge_token("res:foo") is None
    assert schema.parse_edge_token("wilson1971") is None
    assert schema.parse_edge_token("unknown::x") is None    # unregistered prefix
    assert schema.parse_edge_token(123) is None


def test_add_edge_with_axis_mints_registered_token(tmp_path):
    # apply_overlay mints the typed edge through the one minter
    tex = _mini_corpus(tmp_path)
    ci.rewire_add(tmp_path, "c", {"kind": "add-node", "node": "res:x",
                                  "node_kind": "result", "essence": "r",
                                  "parent": "sec:intro"})
    ci.rewire_add(tmp_path, "c", {"kind": "add-edge", "node": "res:x",
                                  "target": "eq:one", "axis": "validates"})
    net = ci.corpus_network(tex, tmp_path, "c")
    row = net["edge_index"]["res:x"]
    assert "eq:one" in row and "validates::eq:one" in row


def test_add_edge_refuses_unregistered_or_pair_axis(tmp_path):
    bogus = ci.rewire_add(tmp_path, "c", {"kind": "add-edge", "node": "a",
                                          "target": "b", "axis": "bogus"})
    assert "error" in bogus and "axis must be one of" in bogus["error"]
    # a pair family (connects) is not a valid edge-target axis
    pair = ci.rewire_add(tmp_path, "c", {"kind": "add-edge", "node": "a",
                                         "target": "b", "axis": "connects"})
    assert "error" in pair and "lateral pair family" in pair["error"]


def test_untyped_add_edge_is_byte_identical_to_the_prior_wire(tmp_path):
    # no axis -> the human-confirmed derives token, unchanged from before G1
    tex = _mini_corpus(tmp_path)
    ci.rewire_add(tmp_path, "c", {"kind": "add-node", "node": "res:x",
                                  "node_kind": "result", "essence": "r",
                                  "parent": "sec:intro"})
    ci.rewire_add(tmp_path, "c", {"kind": "add-edge", "node": "res:x",
                                  "target": "eq:one"})
    net = ci.corpus_network(tex, tmp_path, "c")
    assert "confirmed::eq:one" in net["edge_index"]["res:x"]


def test_concept_lens_preserves_kind_and_strength(tmp_path):
    # a parsed conceptric edge minted through the one home keeps its kind — and now
    # its strength, which concept_lens.py:198 discarded before. before/after is the
    # parse (kind, strength) vs the token recovered by parse_edge_token, on a
    # synthetic parse (never the real corpus).
    cdir = tmp_path / "concept_corpus" / "conceptric"
    cdir.mkdir(parents=True)
    (cdir / "T.md").write_text(
        "# Connectome\n\n## Edges\n"
        "- **paper-a:mechanism-one** -> **paper-b:mechanism-two**  _(shared-mechanism, high, haiku)_\n",
        encoding="utf-8")
    before = cl.parse_conceptric(tmp_path)[0]                   # BEFORE: parsed kind + strength
    ei = cl.lens_edge_index(tmp_path)
    pa = "concept_corpus/atoms/paper-a.md"
    tok = next(t for t in ei[pa] if t.startswith("conn::"))
    after = schema.parse_edge_token(tok)                        # AFTER: recovered from the token
    assert after["kind"] == before["kind"] == "shared-mechanism"
    assert after["strength"] == before["strength"] == "high"   # the field that was lost


def test_concept_lens_coupling_count_unchanged_by_the_token_change(tmp_path):
    # both endpoints mint the identical token, so the coupling COUNT is what it was —
    # the metric keyed on the count is untouched (its retrain is a banked later order)
    from laplace.engine import keeper_ring
    cdir = tmp_path / "concept_corpus" / "conceptric"
    cdir.mkdir(parents=True)
    (cdir / "T.md").write_text(
        "# Connectome\n\n## Edges\n"
        "- **paper-a:mechanism-one** -> **paper-b:mechanism-two**  _(shared-mechanism, high, haiku)_\n"
        "- **paper-a:concept-z** -> **paper-b:concept-w**  _(method-reuse, medium, haiku)_\n",
        encoding="utf-8")
    ei = cl.lens_edge_index(tmp_path)
    a, b = "concept_corpus/atoms/paper-a.md", "concept_corpus/atoms/paper-b.md"
    leaf = lambda nid: {"id": nid, "leaf": True, "members": [], "keywords": [],
                        "coverage": []}
    reach = keeper_ring.build_reach({a: leaf(a), b: leaf(b)}, ei)
    assert keeper_ring.coupling(reach, a, b) == 2               # two shared conceptric edges


# ============================================================ 3. goal supersede

def test_goal_supersede_leaves_one_live_goal(tmp_path):
    tex = _mini_corpus(tmp_path)
    ci.rewire_add(tmp_path, "c", {"kind": "add-node", "node": "goal:v1",
                                  "node_kind": "goal", "essence": "the v1 goal",
                                  "parent": "paper://"})
    ci.rewire_add(tmp_path, "c", {"kind": "add-node", "node": "goal:v2",
                                  "node_kind": "goal", "essence": "the v2 goal",
                                  "parent": "paper://", "supersedes": "goal:v1"})
    net = ci.corpus_network(tex, tmp_path, "c")
    goals = sorted(n for n in net["nodes"] if n.startswith("goal:"))
    assert goals == ["goal:v2"]                                 # exactly one live goal


def test_goal_supersede_survives_a_full_rebuild(tmp_path):
    # the overlay-hash cache key invalidates on the new record, so the rebuilt tree
    # re-derives with the superseded goal retired
    tex = _mini_corpus(tmp_path)
    ci.rewire_add(tmp_path, "c", {"kind": "add-node", "node": "goal:v1",
                                  "node_kind": "goal", "essence": "v1",
                                  "parent": "paper://"})
    first = ci.corpus_network(tex, tmp_path, "c")
    assert "goal:v1" in first["nodes"]
    ci.rewire_add(tmp_path, "c", {"kind": "add-node", "node": "goal:v2",
                                  "node_kind": "goal", "essence": "v2",
                                  "parent": "paper://", "supersedes": "goal:v1"})
    second = ci.corpus_network(tex, tmp_path, "c")
    assert "goal:v1" not in second["nodes"] and "goal:v2" in second["nodes"]


def test_supersede_children_reparent_to_keep_the_tree_whole():
    # apply_overlay directly: a superseded node's children reparent to its parent
    leaves = {"old": {"kind": "goal", "essence": "old"},
              "child": {"kind": "result", "essence": "c"}}
    edge_index = {"old": ["old"], "child": ["child"]}
    parent_map = {"old": "root", "child": "old"}
    recs = [{"kind": "add-node", "node": "new", "node_kind": "goal",
             "essence": "new", "parent": "root", "supersedes": "old"}]
    ci.apply_overlay(leaves, edge_index, recs, parent_map)
    assert "old" not in leaves and "new" in leaves
    assert parent_map["child"] == "root"                       # reparented to old's parent


def test_dangling_supersede_is_a_noop_record_kept(tmp_path):
    # supersedes naming a nonexistent node: the new node still lands, nothing retired
    tex = _mini_corpus(tmp_path)
    ci.rewire_add(tmp_path, "c", {"kind": "add-node", "node": "goal:v9",
                                  "node_kind": "goal", "essence": "v9",
                                  "parent": "paper://",
                                  "supersedes": "goal:does-not-exist"})
    net = ci.corpus_network(tex, tmp_path, "c")
    assert "goal:v9" in net["nodes"]
    # the record survives on the ledger (append-only: never dropped)
    recs = ci.rewire_list(tmp_path, "c")
    assert any(r.get("node") == "goal:v9" and r.get("supersedes") == "goal:does-not-exist"
               for r in recs)


def test_supersedes_only_honoured_on_add_node():
    # a non-add-node record carrying supersedes retires nothing
    leaves = {"old": {"kind": "goal", "essence": "old"}}
    edge_index = {"old": ["old"]}
    parent_map = {"old": "root"}
    recs = [{"kind": "edit-essence", "node": "old", "value": "edited",
             "supersedes": "old"}]
    ci.apply_overlay(leaves, edge_index, recs, parent_map)
    assert "old" in leaves and leaves["old"]["essence"] == "edited"


# ============================================================ the round-trip proof

# Frozen from the PRE-CHANGE build (git-clean HEAD, captured before this wave):
# the subset-sum-itqde network built through corpus_network with its live overlay.
# If the base surgery moved anything, these hashes diverge.
_BASE = {"n_nodes": 494, "node_hash": "df0595a17a0f2f30",
         "n_edge_refs": 2926, "ei_hash": "e0b18b819150292f", "n_spine": 15}


def test_exact_round_trip_on_a_real_corpus():
    tex_root = REPO / "synthetics papers/subset-sum-itqde/manuscript/tex"
    if not (tex_root / "main.tex").is_file():
        pytest.skip("subset-sum-itqde corpus not present")
    net = ci.corpus_network(tex_root, REPO, "subset-sum-itqde")
    node_ids = sorted(net["nodes"])
    ei = net["edge_index"]
    node_hash = hashlib.sha256("\n".join(node_ids).encode()).hexdigest()[:16]
    ei_hash = hashlib.sha256(
        json.dumps({k: sorted(v) for k, v in ei.items()}, sort_keys=True).encode()
    ).hexdigest()[:16]
    assert len(node_ids) == _BASE["n_nodes"]
    assert node_hash == _BASE["node_hash"]
    assert sum(len(v) for v in ei.values()) == _BASE["n_edge_refs"]
    assert ei_hash == _BASE["ei_hash"]
    assert len(net["spine"]) == _BASE["n_spine"]


# ----------------------------------------------------- the G1 judge's two notes
def test_pair_grammar_fences_its_inner_fields():
    # a field carrying '::' or the joiner would mint a token the parser misreads;
    # token_for refuses instead (the docstring's promise, made true)
    for bad in ({"kind": "k::inject"}, {"atoms": "x::y"}, {"strength": "hi::gh"}):
        kwargs = {"lo": "p:a", "hi": "p:b", "atoms": "x", "kind": "k"}
        kwargs.update(bad)
        with pytest.raises(ValueError):
            schema.token_for("connects", **kwargs)
    with pytest.raises(ValueError):
        schema.token_for("connects", lo="p<->a", hi="p:b", atoms="x", kind="k")


def test_bare_mode_prefix_is_not_an_edge():
    # 'sem::' / 'confirmed::' with no target parse to None, symmetric with 'conn::'
    assert schema.parse_edge_token("sem::") is None
    assert schema.parse_edge_token("confirmed::") is None
    assert schema.parse_edge_token("tentative::") is None
