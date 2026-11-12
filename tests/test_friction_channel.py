"""The unified friction channel (2026-07-11 learning-loop design, §1) —
schema join, the typed write door, the drain, the evidence validator, the
digest, and the seed migration.

Every test runs against tmp_path fixtures; none writes the live
``corpus_friction/laplace_engine.jsonl``. The drain fixture mirrors
``test_evolution_consumer``'s throwaway-corpus pattern (a registry data row laid
down by the ``register_project`` door) so exit-1 delegation lands entirely under
tmp_path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.research import corpus_ingest as ci
from laplace.pipeline import adjudicate as adj
from laplace.pipeline import friction_consumer as fc
from laplace.pipeline import propagate as prop
from laplace.pipeline import schema
from laplace.pipeline.ledger import append_jsonl, read_jsonl

FIXTURE_CORPUS = "friction-fixture"


def _friction(rid: str, node: str = "wake", layer: str = "protocol/EIGEN_PROTOCOL.md",
              kind: str = "friction", **extra) -> dict:
    rec = {"id": rid, "ts": "2026-07-11T09:00:00", "kind": kind, "node": node,
           "target": "remote wake", "value": f"stumble at {node}", "by": "eigen",
           "status": "open", "owning_layer": layer}
    rec.update(extra)
    return rec


def _write_ledger(path: Path, records: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                            for r in records), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# schema join — friction/fork are pass-throughs, the spine is the L1 base
# ---------------------------------------------------------------------------

_PLAN = {
    "meta": {"project": "toy"},
    "sections": [{"id": "S1", "beats": [], "nodes_in_order": ["def:x"],
                  "figures": []}],
    "appendices": [],
}


def test_friction_fields_extend_the_exact_l1_spine():
    assert schema.FRICTION_FIELDS[:9] == schema.REWIRE_FIELDS[:9]
    assert schema.FRICTION_FIELDS[9:] == ("owning_layer", "cost", "proposal",
                                          "evidence", "chain")
    assert set(schema.FRICTION_KINDS) == {"friction", "fork"}


def test_friction_kinds_join_the_auxiliary_pass_through():
    assert set(schema.FRICTION_KINDS) <= schema.AUXILIARY_RECORD_KINDS
    # the pre-existing pass-throughs are undisturbed
    assert {"data", "schematic", "txn"} <= schema.AUXILIARY_RECORD_KINDS


def test_friction_record_on_a_manuscript_ledger_marks_no_sections_dirty():
    """The join's safety property: a friction/fork record on an L1 ledger whose
    node IS held by a section still perturbs nothing (kind, not membership,
    decides), while a substance record on the same node does."""
    for kind in schema.FRICTION_KINDS:
        recs = [_friction("RW-x-1", node="def:x", kind=kind)]
        assert prop.affected_sections(recs, _PLAN) == {}
        assert prop.changeset_classes(recs, _PLAN) == {}
    # control: the same node through a substance kind IS dirty
    assert prop.affected_sections(
        [{"kind": "edit-essence", "node": "def:x", "value": "e"}],
        _PLAN) == {"S1": {"def:x"}}


def test_friction_records_do_not_perturb_the_ledger_reducers():
    """friction_current (the L1 state reducer) ignores friction/fork records —
    reducers-skip-it safety, same contract as data/schematic/txn."""
    events = [{"id": "RW-1", "kind": "add-node", "node": "step:a",
               "node_kind": "derivation-step", "essence": "a step", "by": "t"},
              _friction("RW-2", node="step:a"),
              _friction("RW-3", node="step:a", kind="fork")]
    state = ci.friction_current(events)
    assert [r["node"] for r in state] == ["step:a"]
    assert state[0]["essence"] == "a step"


# ---------------------------------------------------------------------------
# friction_add — the typed write door
# ---------------------------------------------------------------------------

def test_friction_add_rejects_missing_node_and_owning_layer(tmp_path):
    assert "error" in ci.friction_add(tmp_path, "x", {"kind": "friction",
                                                      "owning_layer": "scripts"})
    assert "error" in ci.friction_add(tmp_path, "x", {"kind": "friction",
                                                      "node": "wake"})
    # nothing mis-shaped reached the ledger
    assert not (tmp_path / "corpus_friction" / "x.jsonl").exists()


def test_friction_add_rejects_unknown_and_rewire_kinds(tmp_path):
    assert "error" in ci.friction_add(tmp_path, "x", {
        "kind": "bogus", "node": "wake", "owning_layer": "scripts"})
    # a REWIRE kind is not admitted at THIS door (one gate per record class)
    assert "error" in ci.friction_add(tmp_path, "x", {
        "kind": "add-node", "node": "wake", "owning_layer": "scripts"})


def test_friction_add_round_trip_appends_the_exact_spine(tmp_path):
    ok = ci.friction_add(tmp_path, "laplace_engine", {
        "kind": "friction", "node": "wake", "owning_layer": "protocol",
        "target": "remote wake", "value": "MCP tools unmounted",
        "cost": "one fallback read", "proposal": "mount the server",
        "parent": "engine://laplace"})
    assert ok.get("ok")
    rec = ok["record"]
    assert set(rec) <= set(schema.FRICTION_FIELDS)
    assert rec["status"] == "open" and rec["id"] and rec["ts"]
    assert rec["owning_layer"] == "protocol" and rec["by"] == "eigen"
    on_disk = read_jsonl(tmp_path / "corpus_friction" / "laplace_engine.jsonl")
    assert on_disk == [rec]
    # the fork class rides the same door; an explicit banded id is honoured
    ok2 = ci.friction_add(tmp_path, "laplace_engine", {
        "kind": "fork", "node": "verdict-auto-apply", "id": "RW-x-500001",
        "owning_layer": "author", "value": "does verdict auto-apply?"})
    assert ok2.get("ok") and ok2["record"]["kind"] == "fork"
    assert ok2["record"]["id"] == "RW-x-500001"


# ---------------------------------------------------------------------------
# the chain of custody — validation at the door, rollup at the drain
# ---------------------------------------------------------------------------

CHAIN = ["growth-session 2026-07-11: build the one thing out",
         "learning-loop hardening: chain of custody",
         "compile_weld_dispatch(voice_on=True)"]


def _chained(rid: str, action: str, node: str = "wake",
             layer: str = "protocol/EIGEN_PROTOCOL.md", **extra) -> dict:
    return _friction(rid, node=node, layer=layer,
                     chain=CHAIN[:-1] + [action], **extra)


def test_friction_add_validates_chain_shape(tmp_path):
    base = {"kind": "friction", "node": "wake", "owning_layer": "scripts"}
    for bad in ("not a list",          # not a list
                [],                     # empty list
                ["ok", ""],             # empty frame
                ["ok", "   "],          # whitespace frame
                ["ok", 42]):            # non-string frame
        out = ci.friction_add(tmp_path, "x", dict(base, chain=bad))
        assert "error" in out and "chain" in out["error"]
    # nothing mis-shaped reached the ledger
    assert not (tmp_path / "corpus_friction" / "x.jsonl").exists()
    # a well-shaped chain is recorded verbatim (frames stripped), coarse→fine
    ok = ci.friction_add(tmp_path, "x", dict(base, chain=[" a ", "b", "c"]))
    assert ok.get("ok") and ok["record"]["chain"] == ["a", "b", "c"]
    assert set(ok["record"]) <= set(schema.FRICTION_FIELDS)
    (on_disk,) = read_jsonl(tmp_path / "corpus_friction" / "x.jsonl")
    assert on_disk["chain"] == ["a", "b", "c"]


def test_chain_is_recommended_not_required(tmp_path):
    """The 40 seed records lack a chain; the door must not break their
    writers — a chainless deposit is admitted, and the drain makes the gap
    visible instead (the chainless count, tested below)."""
    ok = ci.friction_add(tmp_path, "x", {"kind": "friction", "node": "wake",
                                         "owning_layer": "scripts"})
    assert ok.get("ok") and "chain" not in ok["record"]


def test_digest_rolls_up_by_chain_prefix():
    """Two records sharing a chain prefix (same descent, different local
    action) are ONE group with 2 witnesses; the chainless record falls back to
    its owning layer; the header counts the chainless."""
    recs = [_chained("RW-c-1", "compile r6"),
            _chained("RW-c-2", "weld r6", node="weld"),
            _friction("RW-c-3", node="suite", layer="tests/fixtures")]
    text = fc.digest_md(recs)
    assert "chainless: 1" in text
    prefix = " › ".join(CHAIN[:-1])
    assert f"## chain: {prefix} — 2 open (2 witnesses)" in text
    assert "## tests/fixtures — 1 open" in text
    # each witness line carries its own local action (the finest frame)
    assert "⟨compile r6⟩" in text and "⟨weld r6⟩" in text
    # a one-frame chain groups by that frame, not by an empty prefix
    solo = fc.digest_md([_friction("RW-c-4", chain=["only frame"])])
    assert "## chain: only frame — 1 open (1 witnesses)" in solo


def test_digest_deterministic_with_mixed_chained_and_chainless():
    recs = [_chained("RW-c-1", "compile r6"),
            _friction("RW-c-2", node="suite", layer="tests/fixtures"),
            _chained("RW-c-3", "weld r6"),
            _friction("RW-c-4", node="auto?", kind="fork", layer="author")]
    assert fc.digest_md(recs) == fc.digest_md(recs)
    # order of groups is stable: chain groups sort ahead of layer groups
    text = fc.digest_md(recs)
    assert text.index("## chain:") < text.index("## author")


def test_drain_rolls_up_by_chain_and_fix_proposals_carry_the_chain(tmp_path):
    records = [
        _chained("RW-c-1", "compile r6", layer="scripts/compile.py",
                 proposal="cache the weld"),
        _chained("RW-c-2", "weld r6", node="weld", layer="scripts/weld.py"),
        _friction("RW-c-3", node="suite", layer="tests/fixtures"),
    ]
    ledger = _write_ledger(
        tmp_path / "corpus_friction" / "laplace_engine.jsonl", records)
    summary = fc.drain(tmp_path, ledger, date="2026-07-11")

    # the rollup: one chain-prefix group (2 witnesses, across DIFFERENT owning
    # layers — the chain hierarchialises above the layer), one chainless
    # owning-layer group; the gap is counted
    assert summary["chainless"] == 1
    assert summary["drafted"] == [
        {"chain_prefix": CHAIN[:-1], "frictions": ["RW-c-1", "RW-c-2"]},
        {"owning_layer": "tests/fixtures", "frictions": ["RW-c-3"]},
    ]
    text = Path(summary["fix_proposals"]).read_text(encoding="utf-8")
    prefix = " › ".join(CHAIN[:-1])
    assert f"## chain: {prefix} — 2 open friction(s)" in text
    assert "## tests/fixtures — 1 open friction(s)" in text
    # each entry quotes the FULL chain, coarse→fine — the descent a local
    # fixer needs
    assert ("- chain of custody (coarse→fine): "
            + " → ".join(CHAIN[:-1] + ["compile r6"])) in text
    assert ("- chain of custody (coarse→fine): "
            + " → ".join(CHAIN[:-1] + ["weld r6"])) in text
    # the chainless entry carries no chain line
    chainless_block = text.split("## tests/fixtures")[1]
    assert "chain of custody" not in chainless_block
    # the re-run is byte-identical (determinism holds with mixed records)
    fix1 = Path(summary["fix_proposals"]).read_bytes()
    dig1 = Path(summary["digest"]).read_bytes()
    s2 = fc.drain(tmp_path, ledger, date="2026-07-11")
    assert Path(s2["fix_proposals"]).read_bytes() == fix1
    assert Path(s2["digest"]).read_bytes() == dig1


# ---------------------------------------------------------------------------
# the open-set query + the evidence validator
# ---------------------------------------------------------------------------

def test_evidence_carrying_resolution_consumes(tmp_path):
    target = _friction("RW-a-1")
    res = fc.make_friction_resolution("RW-a-1", evidence="commit abc123")
    recs = [target, res]
    assert fc.open_frictions(recs) == []
    assert [r["id"] for r in fc.consumed_frictions(recs)] == ["RW-a-1"]
    assert fc.invalid_resolutions(recs) == []


def test_evidence_less_resolution_leaves_the_target_open():
    target = _friction("RW-a-1")
    bare = adj.make_resolution("RW-a-1", verb="resolved")   # no evidence field
    recs = [target, bare]
    assert [r["id"] for r in fc.open_frictions(recs)] == ["RW-a-1"]
    assert fc.consumed_frictions(recs) == []
    assert [r["id"] for r in fc.invalid_resolutions(recs)] == [bare["id"]]
    # the door itself refuses to build an evidence-less resolution
    with pytest.raises(ValueError):
        fc.make_friction_resolution("RW-a-1", evidence="   ")


def test_validator_guards_only_the_friction_channel():
    """A resolution on a NON-friction record (an intent, a finding) keeps the
    existing adjudicate.live semantics — evidence is not demanded there."""
    intent = adj.make_conceptric_intent("s", "essence-wrong", note="n")
    bare = adj.make_resolution(intent["id"], verb="supersede")
    assert fc.invalid_resolutions([intent, bare]) == []
    assert adj.live([intent, bare]) == [bare]


# ---------------------------------------------------------------------------
# the drain — three exits, draft-only, idempotent, deterministic digest
# ---------------------------------------------------------------------------

@pytest.fixture
def drain_repo(tmp_path, register_project):
    """A throwaway repo root: an engine ledger with every routing class, plus a
    registered fixture corpus so exit-1 delegation lands under tmp_path."""
    register_project(tmp_path, FIXTURE_CORPUS)
    consumed_target = _friction("RW-f-3", node="reembed", layer="scripts/reembed.py")
    # Explicit, distinct rec_ids: adjudicate._rid stamps microseconds (%f) which
    # COLLIDE under the Windows clock's granularity when both resolutions are
    # built in the same tick — a shared id lets the refused (evidence-less)
    # resolution retire the valid one's target in _retired_ids, so RW-f-3 reads
    # back OPEN instead of consumed. Fixed ids keep the fixture deterministic.
    res = fc.make_friction_resolution("RW-f-3", evidence="commit abc123",
                                      rec_id="RES-f-3")
    bad_res = adj.make_resolution("RW-f-4", verb="resolved",
                                  rec_id="RES-f-4")            # evidence-less
    records = [
        _friction("RW-f-1", node="wake", layer="protocol/EIGEN_PROTOCOL.md",
                  cost="one fallback read", proposal="mount the server"),
        _friction("RW-f-2", node="handoff", layer="protocol/EIGEN_PROTOCOL.md"),
        _friction("RW-f-4", node="suite", layer="tests/fixtures"),
        _friction("RW-f-5", node="essence of s", layer=FIXTURE_CORPUS),
        _friction("RW-f-6", node="auto-apply?", kind="fork", layer="author"),
        consumed_target, res, bad_res,
        {"id": "RW-f-7", "kind": "mystery", "node": "x", "status": "open"},
        {"id": "RW-f-8", "kind": "data", "node": "fig:p", "status": "open"},
    ]
    ledger = _write_ledger(
        tmp_path / "corpus_friction" / "laplace_engine.jsonl", records)
    return tmp_path, ledger


def test_drain_routes_the_three_exits(drain_repo):
    repo, ledger = drain_repo
    before = ledger.read_bytes()
    summary = fc.drain(repo, ledger, date="2026-07-11")

    # exit 2: engine-layer frictions grouped by owning_layer, drafted
    assert {g["owning_layer"]: g["frictions"] for g in summary["drafted"]} == {
        "protocol/EIGEN_PROTOCOL.md": ["RW-f-1", "RW-f-2"],
        "tests/fixtures": ["RW-f-4"],
    }
    fix = Path(summary["fix_proposals"])
    assert fix == repo / "evolutions_engine" / "2026-07-11" / "FIX_PROPOSALS.md"
    text = fix.read_text(encoding="utf-8")
    assert "DRAFT-ONLY" in text and "SUITE + JUDGE" in text
    assert "make_friction_resolution" in text          # the designed post-apply step
    assert "mount the server" in text                  # the proposal, quoted advisory
    # exit 3: the fork is a drafted OPEN_STACK row, never a FIX section
    assert len(summary["open_stack_rows"]) == 1
    assert "RW-f-6" in summary["open_stack_rows"][0]
    assert "RW-f-6" not in text
    # exit 1: the corpus-owned friction delegated to the manuscript queue
    (dele,) = summary["delegated"]
    assert dele["deposited"] and dele["intent_id"] == "CI-RW-f-5"
    fb = repo / f"synthetics papers/{FIXTURE_CORPUS}/manuscript/whitepaper/feedback/feedback.jsonl"
    deposited = read_jsonl(fb)
    assert [r["id"] for r in deposited] == ["CI-RW-f-5"]
    assert deposited[0]["record"] == adj.CONCEPTRIC_INTENT
    assert "RW-f-5" in deposited[0]["payload"]["note"]
    # counts + the validator's flag; the evidence-less target stays OPEN
    # (open = RW-f-1/2/4/5 frictions + the RW-f-6 fork; RW-f-3 consumed)
    assert summary["open"] == 5 and summary["consumed"] == 1
    assert summary["flagged"][0]["target"] == "RW-f-4"
    assert "RW-f-4" in {r["id"] for r in fc.open_frictions(read_jsonl(ledger))}
    # escalation on unknown kind; auxiliary pass-throughs never escalate
    assert [e["id"] for e in summary["escalated"]] == ["RW-f-7"]
    # DRAFT-ONLY: the engine ledger itself is never written
    assert ledger.read_bytes() == before
    assert not (repo / "OPEN_STACK.md").exists()


def test_drain_rerun_is_idempotent_and_digest_deterministic(drain_repo):
    repo, ledger = drain_repo
    s1 = fc.drain(repo, ledger, date="2026-07-11")
    fix1 = Path(s1["fix_proposals"]).read_bytes()
    dig1 = Path(s1["digest"]).read_bytes()
    s2 = fc.drain(repo, ledger, date="2026-07-11")
    assert Path(s2["fix_proposals"]).read_bytes() == fix1
    assert Path(s2["digest"]).read_bytes() == dig1
    # the delegation re-run is a no-op, not a duplicate deposit
    assert s2["delegated"][0]["deposited"] is False
    fb = repo / f"synthetics papers/{FIXTURE_CORPUS}/manuscript/whitepaper/feedback/feedback.jsonl"
    assert len(read_jsonl(fb)) == 1


def test_digest_is_the_fold_projection(drain_repo):
    repo, ledger = drain_repo
    summary = fc.drain(repo, ledger, date="2026-07-11")
    dpath = Path(summary["digest"])
    assert dpath == ledger.with_suffix(".digest.md")   # laplace_engine.digest.md
    text = dpath.read_text(encoding="utf-8")
    assert "open: 5 (friction: 4, fork: 1)" in text
    assert "consumed: 1" in text
    assert "## protocol/EIGEN_PROTOCOL.md — 2 open" in text
    assert "`RW-f-1` [friction] wake" in text
    assert "flagged" in text and "no evidence — refused" in text


def test_drain_source_has_no_apply_path():
    src = Path(fc.__file__).read_text(encoding="utf-8")
    assert "subprocess" not in src
    assert "os.system" not in src
    # the resolution maker is DEFINED (the designed post-apply step) but the
    # drain never CALLS it: beyond its def line, every mention is drafted text
    # (a string literal the author copies into the post-apply step)
    assert src.count("def make_friction_resolution") == 1
    mentions = [ln for ln in src.splitlines()
                if "make_friction_resolution(" in ln
                and not ln.lstrip().startswith("def make_friction_resolution")]
    assert all("lines.append" in ln for ln in mentions)


def test_cli_source_has_no_apply_flag():
    cli = Path(fc.__file__).resolve().parents[3] / "scripts" / "drain_frictions.py"
    src = cli.read_text(encoding="utf-8")
    assert '"--apply"' not in src and "'--apply'" not in src
    assert "subprocess" not in src


# ---------------------------------------------------------------------------
# the seed migration — supersede re-pours, never line edits
# ---------------------------------------------------------------------------

def test_migration_repours_every_open_where_shaped_record(tmp_path):
    old1 = _friction("RW-m-1", node="wake"); old1.pop("target"); old1["where"] = "remote wake"
    old2 = _friction("RW-m-2", node="suite"); old2.pop("target"); old2["where"] = "cold container"
    already = _friction("RW-m-3", node="ok")                       # target-shaped: untouched
    retired = _friction("RW-m-4", node="gone"); retired.pop("target"); retired["where"] = "w"
    res = fc.make_friction_resolution("RW-m-4", evidence="commit beef")   # not open → not re-poured
    ledger = _write_ledger(tmp_path / "laplace_engine.jsonl",
                           [old1, old2, already, retired, res])
    n_lines = len(ledger.read_text(encoding="utf-8").splitlines())

    out = fc.migrate_where_records(ledger)
    assert {m["superseded"] for m in out["migrated"]} == {"RW-m-1", "RW-m-2"}
    assert out["open_where_shaped_after"] == 0
    assert out["open_before"] == out["open_after"] == 3   # live() open count preserved

    after = read_jsonl(ledger)
    # append-only: every original line stands verbatim, re-pours only appended
    assert after[:n_lines] == [old1, old2, already, retired, res]
    opens = {r["id"]: r for r in fc.open_frictions(after)}
    assert "RW-m-1" not in opens and "RW-m-2" not in opens   # superseded
    repours = [r for r in after if r.get("supersedes") in ("RW-m-1", "RW-m-2")]
    for new in repours:
        old = old1 if new["supersedes"] == "RW-m-1" else old2
        assert new["target"] == old["where"] and "where" not in new
        # all content preserved under the new spine
        for k, v in old.items():
            if k not in ("id", "where"):
                assert new[k] == v

    # idempotent: a second run finds zero targets
    again = fc.migrate_where_records(ledger)
    assert again["migrated"] == [] and again["open_after"] == 3
