"""Scoped tests for the edge grammar (journal.bank_row edges) and the one walker
(laplace.core.records.lineage, over the engine scope laplace.engine.engine_ledger.ROW_GRAPH).

Two halves of one system, so one file. The journal half is written in
tests/test_reembed_timing.py's one-stamp-law style — a tmp root, real appends, the
banked bytes read back — because the thing under test is what reaches the STORE, not
what a validator returns in isolation. The walker half plants a small three-generation
corpus in a tmp root rather than asserting against the live stores, so the test says
what the walker does and not what today's rows happen to contain.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _plant(root: Path) -> None:
    (root / "contract").mkdir(parents=True, exist_ok=True)
    (root / "corpus_friction").mkdir(parents=True, exist_ok=True)


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _banked(root: Path, store: str) -> list[dict]:
    return [json.loads(ln) for ln in
            (root / store).read_text(encoding="utf-8").splitlines() if ln.strip()]


# --------------------------------------------------------- the edge grammar (journal)

def test_edges_bank_as_a_first_class_field(tmp_path):
    """An edge is a field on the row, not a convention inside free text. It survives the
    same durable append the row does, normalised to exactly {rel, target}."""
    from laplace.core.records import journal

    _plant(tmp_path)
    journal.bank_row("corpus_friction/demo.jsonl",
                     {"id": "R2", "record": "resolution", "text": "closed"},
                     edges=[{"rel": "resolves", "target": "R1"},
                            {"rel": "grounds", "target": "E1"}],
                     root=tmp_path)

    row = _banked(tmp_path, "corpus_friction/demo.jsonl")[0]
    assert row["edges"] == [{"rel": "resolves", "target": "R1"},
                            {"rel": "grounds", "target": "E1"}]
    assert row["ts"].endswith("Z"), "the one stamp law still owns the row's ts"


def test_a_rel_outside_the_closed_vocabulary_refuses_loudly(tmp_path):
    """THE POINT OF THE CLOSURE. Advisory-never-killing is the law for FRAMES - a frame is a
    guess about meaning and a wrong guess must not stop the work. An edge is a CLAIM, and a
    wrong claim banked silently is inherited as fact by every later walk. So this seam kills,
    and it kills BEFORE anything is written."""
    from laplace.core.records import journal

    _plant(tmp_path)
    with pytest.raises(ValueError) as exc:
        journal.bank_row("corpus_friction/demo.jsonl", {"id": "R9"},
                         edges=[{"rel": "relates-to", "target": "R1"}], root=tmp_path)
    assert "closed vocabulary" in str(exc.value)
    assert "relates-to" in str(exc.value)
    assert not (tmp_path / "corpus_friction" / "demo.jsonl").exists(), \
        "the refusal happened before the append, so no store carries the bad claim"
    assert not (tmp_path / "contract" / "journal.jsonl").exists(), \
        "nor did the journal record an intent it then never completed"


@pytest.mark.parametrize("bad,why", [
    ("notalist", "a bare string is not a list of edges"),
    ([{"rel": "grounds"}], "no target"),
    ([{"target": "R1"}], "no rel"),
    ([{"rel": "grounds", "target": ""}], "empty target"),
    ([{"rel": "grounds", "target": "R1 and also R2"}], "prose wearing a target's clothes"),
    ([{"rel": "grounds", "target": "R1", "note": "why"}], "an edge is not a note-holder"),
    ([{"rel": "grounds", "target": "store#R1"}], "a qualifier must name a .jsonl store"),
    ([{"rel": "grounds", "target": "a.jsonl#b.jsonl#R1"}], "two qualifiers"),
    (["grounds:R1"], "a string is not an edge"),
])
def test_malformed_edges_refuse(tmp_path, bad, why):
    from laplace.core.records import journal

    _plant(tmp_path)
    with pytest.raises(ValueError):
        journal.bank_row("corpus_friction/demo.jsonl", {"id": "R9"}, edges=bad, root=tmp_path)


def test_a_store_qualified_target_banks_and_resolves(tmp_path):
    """The same id can live in two stores. 'store.jsonl#id' is how a row says which one it
    meant, and the walker must honour it rather than pick the first match."""
    from laplace.core.records import lineage
    from laplace.engine.engine_ledger import ROW_GRAPH
    from laplace.core.records import journal

    _plant(tmp_path)
    _write(tmp_path / "corpus_friction" / "a.jsonl",
           [{"id": "DUP", "record": "note", "text": "the one in a"}])
    _write(tmp_path / "contract" / "b.jsonl",
           [{"id": "DUP", "record": "note", "text": "the one in b"}])
    journal.bank_row("corpus_friction/c.jsonl", {"id": "PICKER", "record": "note"},
                     edges=[{"rel": "grounds", "target": "b.jsonl#DUP"}], root=tmp_path)

    idx = lineage.index(tmp_path, scope=ROW_GRAPH, refresh=True)
    assert idx.node("DUP")["ambiguous"] is True, "two rows share the id; the index says so"
    picked = idx.refs("b.jsonl#DUP")
    assert [p["store"] for p in picked] == ["contract/b.jsonl"]
    tree = lineage.ancestors("PICKER", idx=idx)
    assert [c["stores"] for c in tree["children"]] == [["contract/b.jsonl"]]


def test_edges_given_twice_refuses(tmp_path):
    """One home per claim: a row carrying its own edges AND an edges= argument is a
    contradiction, not a merge - silently picking one would make the loser invisible."""
    from laplace.core.records import journal

    _plant(tmp_path)
    with pytest.raises(ValueError) as exc:
        journal.bank_row("corpus_friction/demo.jsonl",
                         {"id": "R9", "edges": [{"rel": "grounds", "target": "A"}]},
                         edges=[{"rel": "grounds", "target": "B"}], root=tmp_path)
    assert "twice" in str(exc.value)


def test_a_row_carrying_its_own_edges_is_validated_on_the_same_terms(tmp_path):
    """The validation belongs to the SEAM, not to the argument: a hand-built row that
    reaches bank_row with a bad edge on it must refuse exactly as the argument does."""
    from laplace.core.records import journal

    _plant(tmp_path)
    with pytest.raises(ValueError):
        journal.bank_row("corpus_friction/demo.jsonl",
                         {"id": "R9", "edges": [{"rel": "vibes", "target": "A"}]},
                         root=tmp_path)
    journal.bank_row("corpus_friction/demo.jsonl",
                     {"id": "R8", "edges": [{"rel": "cures", "target": "A"}]}, root=tmp_path)
    assert _banked(tmp_path, "corpus_friction/demo.jsonl")[0]["edges"] == \
        [{"rel": "cures", "target": "A"}]


def test_existing_callers_are_unchanged(tmp_path):
    """The param is optional and adds nothing when unused: a row banked the old way carries
    no edges field at all, so no store grows a column it never asked for."""
    from laplace.core.records import journal

    _plant(tmp_path)
    journal.bank_row("corpus_friction/demo.jsonl", {"id": "OLD", "text": "as before"},
                     root=tmp_path)
    row = _banked(tmp_path, "corpus_friction/demo.jsonl")[0]
    assert "edges" not in row


# ----------------------------------------------------------------- the walker (lineage)

def _three_generations(root: Path) -> None:
    """WO <- resolution <- verdict: one chain, three generations, mixed dialects.

    The middle link is a LEGACY resolution.target and the top link is a DECLARED edge, so a
    round trip proves the two halves compose into one graph rather than two.
    """
    _plant(root)
    _write(root / "corpus_friction" / "work_orders.jsonl", [
        {"id": "WO-1", "record": "work-order", "title": "the first generation"},
        {"id": "RES-1", "record": "resolution", "target": "WO-1", "text": "the second"},
        {"id": "VER-1", "record": "verdict", "text": "the third",
         "edges": [{"rel": "grades", "target": "RES-1"}]},
    ])


def test_a_three_generation_chain_round_trips(tmp_path):
    from laplace.core.records import lineage
    from laplace.engine.engine_ledger import ROW_GRAPH

    _three_generations(tmp_path)
    idx = lineage.index(tmp_path, scope=ROW_GRAPH, refresh=True)

    up = lineage.ancestors("VER-1", idx=idx)
    assert up["id"] == "VER-1"
    (res,) = up["children"]
    assert (res["id"], res["rel"], res["via"]) == ("RES-1", "grades", "edges")
    (wo,) = res["children"]
    assert (wo["id"], wo["rel"], wo["via"]) == ("WO-1", "resolves", "legacy:target")
    assert wo["children"] == [], "the first generation stands on nothing"

    down = lineage.descendants("WO-1", idx=idx)
    (res_d,) = down["children"]
    assert (res_d["id"], res_d["rel"]) == ("RES-1", "resolves")
    (ver_d,) = res_d["children"]
    assert (ver_d["id"], ver_d["rel"], ver_d["via"]) == ("VER-1", "grades", "edges")


def test_descendants_is_the_reverse_of_the_same_read(tmp_path):
    """The reverse index is built in the SAME pass as the forward one - descendants must
    never cost a second walk over the stores."""
    from laplace.core.records import lineage
    from laplace.engine.engine_ledger import ROW_GRAPH

    _three_generations(tmp_path)
    idx = lineage.index(tmp_path, scope=ROW_GRAPH, refresh=True)
    forward = {(e["source"], e["rel"], e["target_id"]) for es in idx.forward.values() for e in es}
    reverse = {(e["source"], e["rel"], e["target_id"]) for es in idx.reverse.values() for e in es}
    assert forward == reverse and forward, "one edge set, indexed both ways"
    assert idx.rows_read == 3 and idx.edges_declared == 1 and idx.edges_legacy == 1


def test_depth_bounds_the_walk_and_says_it_was_bounded(tmp_path):
    from laplace.core.records import lineage
    from laplace.engine.engine_ledger import ROW_GRAPH

    _three_generations(tmp_path)
    idx = lineage.index(tmp_path, scope=ROW_GRAPH, refresh=True)
    shallow = lineage.ancestors("VER-1", depth=1, idx=idx)
    (res,) = shallow["children"]
    assert res["children"] == [] and res["truncated"] is True, \
        "a bounded walk must not read as an exhausted one"


def test_the_legacy_map_reads_every_named_dialect(tmp_path):
    """Each legacy field's implied rel, exercised on rows shaped like the real ones."""
    from laplace.core.records import lineage
    from laplace.engine.engine_ledger import ROW_GRAPH

    _plant(tmp_path)
    _write(tmp_path / "corpus_friction" / "legacy.jsonl", [
        {"id": "WO-A", "record": "work-order"},
        {"id": "PKT-A", "record": "liveness-packet"},
        {"id": "OLD-A", "record": "work-order"},
        {"id": "AM-1", "record": "amendment", "target": "WO-A"},
        {"id": "DEF-1", "record": "defer", "target": "WO-A"},
        {"id": "RUL-1", "record": "ruling", "target": "WO-A"},
        {"id": "LIV-1", "record": "liveness-verdict", "packet": "PKT-A"},
        {"id": "SUP-1", "record": "note", "supersedes": "OLD-A"},
        {"id": "CON-1", "record": "resolution", "consumes": ["WO-A", "OLD-A"]},
        {"id": "EVD-1", "record": "note", "evidence": ["WO-A", "a sentence of prose"]},
    ])
    idx = lineage.index(tmp_path, scope=ROW_GRAPH, refresh=True)
    got = {(e["source"], e["rel"], e["target_id"], e["via"])
           for es in idx.forward.values() for e in es}
    assert got == {
        ("AM-1", "amends", "WO-A", "legacy:target"),
        ("DEF-1", "amends", "WO-A", "legacy:target"),
        ("RUL-1", "grades", "WO-A", "legacy:target"),
        ("LIV-1", "grades", "PKT-A", "legacy:packet"),
        ("SUP-1", "supersedes", "OLD-A", "legacy:supersedes"),
        ("CON-1", "consumes", "WO-A", "legacy:consumes"),
        ("CON-1", "consumes", "OLD-A", "legacy:consumes"),
        ("EVD-1", "grounds", "WO-A", "legacy:evidence"),
    }


def test_prose_in_a_legacy_field_never_becomes_an_edge(tmp_path):
    """packet, cures and evidence hold PROSE as often as ids in the real stores ('AB_RUN_4
    under JUDGE4-STAMP-...', a five-paragraph defect list). An inference over an untyped
    field is only made when the value actually resolves - that guard IS what makes reading
    these fields safe."""
    from laplace.core.records import lineage
    from laplace.engine.engine_ledger import ROW_GRAPH

    _plant(tmp_path)
    _write(tmp_path / "corpus_friction" / "prose.jsonl", [
        {"id": "REAL-1", "record": "work-order"},
        {"id": "V-1", "record": "verdict",
         "packet": "AB_RUN_4 under JUDGE4-STAMP-20260824-CPRIME-GRANT (amendments 6-7)"},
        {"id": "V-2", "record": "resolution",
         "cures": ["C1 meaning_upfold.py:444 - the backend passed no dialed at all", "REAL-1"]},
        {"id": "V-3", "record": "note", "evidence": "NO-SUCH-ROW-EVER"},
    ])
    idx = lineage.index(tmp_path, scope=ROW_GRAPH, refresh=True)
    assert "V-1" not in idx.forward, "prose does not resolve, so prose is not an edge"
    assert [e["target_id"] for e in idx.forward["V-2"]] == ["REAL-1"]
    assert "V-3" not in idx.forward, "an unresolvable id is an inference that did not check out"


def test_a_declared_edge_survives_a_dangling_target(tmp_path):
    """The asymmetry, stated: an inference must check out, but a CLAIM is shown because
    someone made it - a declared edge to a row that is not there reads UNRESOLVED rather
    than disappearing, which is the only way a broken claim is ever repairable."""
    from laplace.core.records import lineage
    from laplace.engine.engine_ledger import ROW_GRAPH

    _plant(tmp_path)
    _write(tmp_path / "corpus_friction" / "claim.jsonl", [
        {"id": "C-1", "record": "note", "edges": [{"rel": "cures", "target": "GHOST"}]},
    ])
    idx = lineage.index(tmp_path, scope=ROW_GRAPH, refresh=True)
    (ghost,) = lineage.ancestors("C-1", idx=idx)["children"]
    assert ghost["id"] == "GHOST" and ghost["found"] is False and ghost["rel"] == "cures"


def test_an_edge_row_links_its_from_row_not_itself(tmp_path):
    """THE RETROFIT'S WHOLE POINT. `bank_row(edges=...)` can only type the links of a row
    being written NOW, and the stores are append-only, so a row banked yesterday has no
    home for its links. An edge row is that home - and it must read as a LINK BETWEEN TWO
    OTHER ROWS, never as a node hanging off the graph, or the retrofit buys nothing."""
    from laplace.core.records import lineage
    from laplace.engine.engine_ledger import ROW_GRAPH

    _plant(tmp_path)
    _write(tmp_path / "corpus_friction" / "rows.jsonl", [
        {"id": "A-1", "record": "note", "text": "the ground"},
        {"id": "B-1", "record": "note", "text": "the ruling"},
    ])
    _write(tmp_path / "corpus_friction" / "edges.jsonl", [
        {"id": "EDGE-B-1--grounds--1", "record": "edge",
         "from": "B-1", "rel": "grounds", "to": "A-1"},
        {"id": "EDGE-BAD--1", "record": "edge",
         "from": "B-1", "rel": "related", "to": "A-1"},      # outside REL: skipped
    ])
    idx = lineage.index(tmp_path, scope=ROW_GRAPH, refresh=True)
    (ground,) = lineage.ancestors("B-1", idx=idx)["children"]
    assert ground["id"] == "A-1" and ground["rel"] == "grounds"
    assert lineage.descendants("A-1", idx=idx)["children"][0]["id"] == "B-1"
    assert "EDGE-B-1--grounds--1" not in idx.forward, "an edge row is a link, not a source"
    assert idx.edges_declared == 1, "the rel outside the closed vocabulary is not walked"


def test_an_edge_row_beats_the_legacy_inference_of_the_same_link(tmp_path):
    """One claim, one display. A retrofit edge over a row whose legacy field already
    implies the same link must not double the branch - and the surviving branch must be
    the one someone STATED, so the walk names the row that made the claim."""
    from laplace.core.records import lineage
    from laplace.engine.engine_ledger import ROW_GRAPH

    _plant(tmp_path)
    _write(tmp_path / "corpus_friction" / "rows.jsonl", [
        {"id": "WO-1", "record": "work_order"},
        {"id": "RES-1", "record": "resolution", "target": "WO-1"},
    ])
    _write(tmp_path / "corpus_friction" / "edges.jsonl", [
        {"id": "EDGE-RES-1--resolves--1", "record": "edge",
         "from": "RES-1", "rel": "resolves", "to": "WO-1"},
    ])
    idx = lineage.index(tmp_path, scope=ROW_GRAPH, refresh=True)
    kids = lineage.ancestors("RES-1", idx=idx)["children"]
    assert [(k["id"], k["rel"]) for k in kids] == [("WO-1", "resolves")]
    assert kids[0]["via"] == "edge-row:EDGE-RES-1--resolves--1"


def test_the_meters_count_what_is_indexed_never_what_was_read(tmp_path):
    """The render prints these two numbers and nothing else about the graph's size, so a
    meter that counts a link the walk then DROPS is the first lie a reader believes. Three
    links are read here and only one is indexed: a declared self-link (noise), a legacy
    inference an edge row already states (one claim, one display), and the edge row itself."""
    from laplace.core.records import lineage
    from laplace.engine.engine_ledger import ROW_GRAPH

    _plant(tmp_path)
    _write(tmp_path / "corpus_friction" / "rows.jsonl", [
        {"id": "WO-1", "record": "work_order"},
        {"id": "RES-1", "record": "resolution", "target": "WO-1",
         "edges": [{"rel": "grounds", "target": "RES-1"}]},
    ])
    _write(tmp_path / "corpus_friction" / "edges.jsonl", [
        {"id": "EDGE-RES-1--resolves--1", "record": "edge",
         "from": "RES-1", "rel": "resolves", "to": "WO-1"},
    ])
    idx = lineage.index(tmp_path, scope=ROW_GRAPH, refresh=True)
    indexed = [e for es in idx.forward.values() for e in es]
    assert len(indexed) == 1
    assert (idx.edges_declared, idx.edges_legacy) == (1, 0), \
        "the dropped self-link must not inflate declared, nor the suppressed inference legacy"


def test_the_same_id_in_two_stores_states_a_link_once(tmp_path):
    """`forward` is keyed on the bare id, so two rows sharing an id are already ONE node.
    Letting each contribute the same link would print the same child twice on the tree."""
    from laplace.core.records import lineage
    from laplace.engine.engine_ledger import ROW_GRAPH

    _plant(tmp_path)
    _write(tmp_path / "corpus_friction" / "a.jsonl",
           [{"id": "TARGET", "record": "note"},
            {"id": "DUP", "record": "resolution", "target": "TARGET"}])
    _write(tmp_path / "contract" / "b.jsonl",
           [{"id": "DUP", "record": "resolution", "target": "TARGET"}])
    idx = lineage.index(tmp_path, scope=ROW_GRAPH, refresh=True)
    assert idx.node("DUP")["ambiguous"] is True
    assert [(e["rel"], e["target_id"]) for e in idx.forward["DUP"]] == [("resolves", "TARGET")]
    assert idx.edges_legacy == 1
    assert [c["id"] for c in lineage.descendants("TARGET", idx=idx)["children"]] == ["DUP"]


def test_the_graph_corpus_dialect_is_not_spliced_in(tmp_path):
    """add-node/add-edge/set-spine carry a `target` too, but theirs is a NODE id inside a
    conceptric graph - a different address space that shares a field name. Walking them
    would silently weld two graphs together."""
    from laplace.core.records import lineage
    from laplace.engine.engine_ledger import ROW_GRAPH

    _plant(tmp_path)
    _write(tmp_path / "corpus_friction" / "graphy.jsonl", [
        {"id": "RW-1", "kind": "add-edge", "node": "goal:x", "target": "RW-2"},
        {"id": "RW-2", "kind": "add-node", "node": "goal:y"},
    ])
    idx = lineage.index(tmp_path, scope=ROW_GRAPH, refresh=True)
    assert idx.forward == {} and idx.rows_read == 2


def test_a_malformed_line_is_counted_never_fatal(tmp_path):
    """An append-only store acquires bad lines and partial final writes. A reader that
    halts on one goes dark exactly when it is needed."""
    from laplace.core.records import lineage
    from laplace.engine.engine_ledger import ROW_GRAPH

    _plant(tmp_path)
    p = tmp_path / "corpus_friction" / "torn.jsonl"
    p.write_text('{"id": "OK-1", "record": "note"}\n'
                 'not json at all\n'
                 '["a list, not a row"]\n'
                 '{"id": "OK-2", "record": "resolution", "target": "OK-1"}\n'
                 '{"id": "TORN", "reco', encoding="utf-8")
    idx = lineage.index(tmp_path, scope=ROW_GRAPH, refresh=True)
    assert idx.rows_read == 2 and idx.rows_unparseable == 3
    assert [e["target_id"] for e in idx.forward["OK-2"]] == ["OK-1"]


def test_a_cycle_terminates(tmp_path):
    """The stores are append-only, not acyclic: two rows can supersede each other across
    an era. The walk marks the loop and stops rather than recursing forever."""
    from laplace.core.records import lineage
    from laplace.engine.engine_ledger import ROW_GRAPH

    _plant(tmp_path)
    _write(tmp_path / "corpus_friction" / "loop.jsonl", [
        {"id": "A", "record": "note", "supersedes": "B"},
        {"id": "B", "record": "note", "supersedes": "A"},
    ])
    idx = lineage.index(tmp_path, scope=ROW_GRAPH, refresh=True)
    tree = lineage.ancestors("A", idx=idx)
    (b,) = tree["children"]
    (a_again,) = b["children"]
    assert a_again["id"] == "A" and a_again.get("cycle") is True
    assert a_again["children"] == []


def test_neighborhood_serves_both_directions_and_its_own_meter(tmp_path):
    from laplace.core.records import lineage
    from laplace.engine.engine_ledger import ROW_GRAPH

    _three_generations(tmp_path)
    lineage.index(tmp_path, scope=ROW_GRAPH, refresh=True)
    n = lineage.neighborhood("RES-1", depth=1, idx=lineage.index(tmp_path, scope=ROW_GRAPH))
    assert [c["id"] for c in n["ancestors"]["children"]] == ["WO-1"]
    assert [c["id"] for c in n["descendants"]["children"]] == ["VER-1"]
    assert n["index"]["rows"] == 3 and n["index"]["ids"] == 3
    json.dumps(n)  # the whole neighborhood is JSON, which is what --json prints


def test_an_unknown_row_answers_instead_of_raising(tmp_path):
    from laplace.core.records import lineage
    from laplace.engine.engine_ledger import ROW_GRAPH

    _plant(tmp_path)
    n = lineage.neighborhood("NOPE-1", root=tmp_path, idx=lineage.index(tmp_path, scope=ROW_GRAPH, refresh=True))
    assert n["row"]["found"] is False
    assert "UNRESOLVED" in lineage.render(n)


def test_the_cli_walks_a_real_row_of_the_live_stores():
    """The one end-to-end: the module's own CLI, against the repo's real corpus_friction/
    and contract/. Asserts the SHAPE of the answer, never today's row count."""
    out = subprocess.run(
        [sys.executable, "-m", "laplace.engine.engine_ledger",
         "VERDICT-20260824-ab-run-4-conclusive", "--depth", "2"],
        cwd=str(ROOT), capture_output=True, text=True,
        env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin", "LAPLACE_EMBED_BUDGET": "0"})
    assert out.returncode == 0, out.stderr
    assert "ROW  VERDICT-20260824-ab-run-4-conclusive" in out.stdout
    assert "ANCESTORS (what it stands on)" in out.stdout
    assert "DESCENDANTS (what stands on it)" in out.stdout
    assert "work_orders.jsonl" in out.stdout


def test_the_cli_emits_json():
    out = subprocess.run(
        [sys.executable, "-m", "laplace.engine.engine_ledger",
         "VERDICT-20260824-ab-run-4-conclusive", "--depth", "1", "--json"],
        cwd=str(ROOT), capture_output=True, text=True,
        env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin", "LAPLACE_EMBED_BUDGET": "0"})
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    assert payload["row"]["id"] == "VERDICT-20260824-ab-run-4-conclusive"
    assert payload["row"]["found"] is True
    assert set(payload) == {"row", "depth", "ancestors", "descendants", "index"}
