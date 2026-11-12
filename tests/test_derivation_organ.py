"""Tests for the DERIVATION ORGAN reader (src/laplace/pipeline/derivation_organ.py).

The organ is aspiration-first (PV-20260721T121500Z-author-steer-aspiration-first-isnads):
Phase 0 banks the maximal claim; the chain is the isnad from substrate toward it; the
reach metric measures HOW FAR UP the attested chain got. These tests exercise the pure
reads (honest-empty, last-wins ledger) and the reach math (total / attested / longest
attested depth / named frontier gaps) on a fixture — never the frozen manuscript.
"""
from __future__ import annotations

import json
from pathlib import Path

from laplace.pipeline import derivation_organ as organ


def _bank_aspiration(md: Path) -> None:
    (md / "aspiration").mkdir(parents=True, exist_ok=True)
    (md / "aspiration" / "aspiration.json").write_text(json.dumps({
        "record": "aspiration",
        "claim_maximal": "MEASUREMENT IS THE COST; coherence is a scaling-class win.",
        "reach_axes": {"reach": "R", "scope": "S", "impact": "I"},
        "demonstrandum": ["D1", "D2"],
        "banked_by": "test",
        "ts": "2026-07-21T00:00:00Z",
    }), encoding="utf-8")


def _bank_chain(md: Path, rows: list[dict]) -> None:
    (md / "aspiration").mkdir(parents=True, exist_ok=True)
    p = md / "aspiration" / "chain.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


# ---------------------------------------------------------------------------
# read_aspiration
# ---------------------------------------------------------------------------

def test_read_aspiration_honest_empty_when_absent(tmp_path: Path):
    got = organ.read_aspiration(tmp_path)
    assert got == {"present": False}


def test_read_aspiration_reads_banked(tmp_path: Path):
    _bank_aspiration(tmp_path)
    got = organ.read_aspiration(tmp_path)
    assert got["present"] is True
    assert got["claim_maximal"].startswith("MEASUREMENT IS THE COST")
    assert got["reach_axes"] == {"reach": "R", "scope": "S", "impact": "I"}
    assert got["demonstrandum"] == ["D1", "D2"]
    assert got["banked_by"] == "test"


def test_read_aspiration_rejects_non_aspiration_record(tmp_path: Path):
    (tmp_path / "aspiration").mkdir()
    (tmp_path / "aspiration" / "aspiration.json").write_text(
        json.dumps({"record": "something-else"}), encoding="utf-8")
    assert organ.read_aspiration(tmp_path) == {"present": False}


# ---------------------------------------------------------------------------
# read_chain
# ---------------------------------------------------------------------------

def test_read_chain_honest_empty_when_absent(tmp_path: Path):
    assert organ.read_chain(tmp_path) == []


def test_read_chain_skips_malformed_lines(tmp_path: Path):
    (tmp_path / "aspiration").mkdir()
    (tmp_path / "aspiration" / "chain.jsonl").write_text(
        '{"id": "L1", "from": "N_a: x", "to": "N_b: y", "status": "gap"}\n'
        'not json at all\n'
        '\n'
        '{"id": "L2", "from": "N_b: y", "to": "N_c: z", "status": "attested"}\n',
        encoding="utf-8")
    got = organ.read_chain(tmp_path)
    assert [r["id"] for r in got] == ["L1", "L2"]
    assert got[1]["status"] == "attested"


def test_read_chain_last_wins_ledger(tmp_path: Path):
    # the append-only forging record: a link is banked gap, then re-appended attested.
    _bank_chain(tmp_path, [
        {"id": "L1", "from": "N_a: x", "to": "N_b: y", "kind": "derived",
         "status": "gap", "attestation": None},
        {"id": "L1", "from": "N_a: x", "to": "N_b: y", "kind": "derived",
         "status": "attested", "attestation": "forged: derivations/L1.tex"},
    ])
    got = organ.read_chain(tmp_path)
    assert len(got) == 1                     # deduped by id
    assert got[0]["status"] == "attested"    # last wins
    assert got[0]["attestation"] == "forged: derivations/L1.tex"


def test_read_chain_unknown_status_degrades_to_gap(tmp_path: Path):
    _bank_chain(tmp_path, [
        {"id": "L1", "from": "N_a: x", "to": "N_b: y", "status": "pending"},
    ])
    assert organ.read_chain(tmp_path)[0]["status"] == "gap"


# ---------------------------------------------------------------------------
# reach — the metric draft-psi-v2 gates on
# ---------------------------------------------------------------------------

def _fixture_chain() -> list[dict]:
    # a->b->c->d is a depth-3 attested path; x->y an isolated attested pair;
    # a join link (b + c -> f) exercises multi-from; d->e is the NAMED gap frontier.
    return [
        {"id": "l1", "from": "N_a: sub", "to": "N_b: mid1", "kind": "derived",
         "status": "attested", "attestation": "d/l1.tex"},
        {"id": "l2", "from": "N_b: mid1", "to": "N_c: mid2", "kind": "derived",
         "status": "attested", "attestation": "d/l2.tex"},
        {"id": "l3", "from": "N_c: mid2", "to": "N_d: near", "kind": "derived",
         "status": "attested", "attestation": "d/l3.tex"},
        {"id": "l4", "from": "N_x: other", "to": "N_y: other2", "kind": "computed",
         "status": "attested", "attestation": "c/l4.json"},
        {"id": "l5", "from": "N_b: mid1 + N_c: mid2", "to": "N_f: join",
         "kind": "derived", "status": "attested", "attestation": "d/l5.tex"},
        {"id": "l6", "from": "N_d: near", "to": "N_goal: aspiration", "kind": "computed",
         "status": "gap", "attestation": None,
         "_gap_named": "THE RESIDUAL: unforgeable at this stage; named, not weakened."},
    ]


def test_reach_honest_empty(tmp_path: Path):
    got = organ.reach(tmp_path)
    assert got["present"] is False
    assert got["links_total"] == 0
    assert got["links_attested"] == 0
    assert got["depth_attested"] == 0
    assert got["frontier_gap"] == []


def test_reach_counts_and_depth(tmp_path: Path):
    _bank_aspiration(tmp_path)
    _bank_chain(tmp_path, _fixture_chain())
    got = organ.reach(tmp_path)
    assert got["present"] is True
    assert got["aspiration_present"] is True
    assert got["links_total"] == 6
    assert got["links_attested"] == 5
    # longest ATTESTED path a->b->c->d = 3 links (the gap l6 does NOT extend it).
    assert got["depth_attested"] == 3


def test_reach_frontier_names_the_gap(tmp_path: Path):
    _bank_chain(tmp_path, _fixture_chain())
    got = organ.reach(tmp_path)
    assert len(got["frontier_gap"]) == 1
    fg = got["frontier_gap"][0]
    assert fg["id"] == "l6"
    assert "RESIDUAL" in fg["why"]           # the named reason surfaces, not swallowed
    assert fg["to"].startswith("N_goal")


def test_reach_gap_does_not_count_toward_depth(tmp_path: Path):
    # flip the frontier gap to attested: depth must grow by exactly one (d->goal).
    rows = _fixture_chain()
    rows.append({"id": "l6", "from": "N_d: near", "to": "N_goal: aspiration",
                 "kind": "computed", "status": "attested", "attestation": "c/l6.json"})
    _bank_chain(tmp_path, rows)
    got = organ.reach(tmp_path)
    assert got["links_attested"] == 6
    assert got["depth_attested"] == 4        # a->b->c->d->goal


def test_reach_present_with_chain_only(tmp_path: Path):
    # a chain but no aspiration banked yet — still "present" (the organ has links).
    _bank_chain(tmp_path, _fixture_chain())
    got = organ.reach(tmp_path)
    assert got["present"] is True
    assert got["aspiration_present"] is False


# ---------------------------------------------------------------------------
# THE GENERIC GROWTH LEG — mint_growth_intents / record_growth_nodes
# ---------------------------------------------------------------------------

from laplace.pipeline import adjudicate as adj                 # noqa: E402
from laplace.pipeline import evolution_consumer as ec          # noqa: E402


def _read_feedback(md: Path) -> list[dict]:
    p = md / "feedback" / "feedback.jsonl"
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


CORPUS = "growth-fixture"


def test_mint_growth_intents_mints_attested_and_dedups(tmp_path: Path):
    md = tmp_path / "manuscript"
    _bank_chain(md, _fixture_chain())        # 5 attested + 1 gap (l6)
    got = organ.mint_growth_intents(md, CORPUS, by="gerard")
    # every ATTESTED link mints once; the gap l6 NEVER mints (it is skipped).
    assert len(got["minted"]) == 5
    assert {m["id"] for m in got["minted"]} == {"l1", "l2", "l3", "l4", "l5"}
    assert "l6" not in {m["id"] for m in got["minted"]}

    # the feedback ledger carries 5 conceptric-intents, each with a gap {quote, context}.
    fb = _read_feedback(md)
    intents = [r for r in fb if r.get("record") == adj.CONCEPTRIC_INTENT]
    assert len(intents) == 5
    for it in intents:
        assert it["intent"] == "content-missing"
        assert it["gap"]["quote"] and it["gap"]["context"]

    # each attested link is now STAMPED with its intent_id (read_chain carries it).
    by_id = {l["id"]: l for l in organ.read_chain(md)}
    assert all("intent_id" in by_id[lid] for lid in ("l1", "l2", "l3", "l4", "l5"))
    assert "intent_id" not in by_id["l6"]    # the gap is never stamped

    # re-run DEDUPS: nothing new minted, the five are skipped (plus the gap).
    again = organ.mint_growth_intents(md, CORPUS, by="gerard")
    assert again["minted"] == []
    assert again["skipped"] == 6
    assert len([r for r in _read_feedback(md)
                if r.get("record") == adj.CONCEPTRIC_INTENT]) == 5


def test_gap_link_never_mints(tmp_path: Path):
    md = tmp_path / "manuscript"
    # ONLY a gap link — nothing forged, so nothing enters the conceptric as growth.
    _bank_chain(md, [{"id": "g1", "from": "N_a: x", "to": "N_b: y", "kind": "derived",
                      "status": "gap", "attestation": None}])
    got = organ.mint_growth_intents(md, CORPUS, by="gerard")
    assert got["minted"] == [] and got["skipped"] == 1
    assert _read_feedback(md) == []


def test_mint_honest_empty_on_no_chain(tmp_path: Path):
    got = organ.mint_growth_intents(tmp_path / "manuscript", CORPUS, by="gerard")
    assert got == {"minted": [], "skipped": 0}


def test_minted_intent_drafts_a_contract_cleanly(tmp_path: Path):
    # the minted intent must ride the REAL drafter (evolution_consumer.draft_contract)
    # cleanly — the shape is contract-draftable, not merely well-formed.
    md = tmp_path / "manuscript"
    _bank_chain(md, [{"id": "l1", "from": "N_a: substrate", "to": "N_b: result",
                      "kind": "derived", "status": "attested",
                      "attestation": "forged: derivations/l1.tex"}])
    organ.mint_growth_intents(md, CORPUS, by="gerard")
    intent = next(r for r in _read_feedback(md)
                  if r.get("record") == adj.CONCEPTRIC_INTENT)
    res = ec.draft_contract(intent, None, CORPUS, md / "evolution", repo_root=tmp_path)
    assert not res.get("escalated"), res
    assert res["intent_id"] == intent["id"]
    assert (Path(res["evolution_dir"]) / "evolution_plan.json").is_file()


def test_record_growth_nodes_joins_after_ratify(tmp_path: Path):
    md = tmp_path / "manuscript"
    _bank_chain(md, [{"id": "l1", "from": "N_a: substrate", "to": "N_b: result",
                      "kind": "derived", "status": "attested",
                      "attestation": "forged: derivations/l1.tex"}])
    organ.mint_growth_intents(md, CORPUS, by="gerard")
    iid = next(r["id"] for r in _read_feedback(md)
               if r.get("record") == adj.CONCEPTRIC_INTENT)

    # BEFORE the ratify: no join (the intent is still open at the desk).
    assert organ.record_growth_nodes(md, CORPUS)["joined"] == []

    # simulate the ONE apply path's outcome: the revoke + ratified-operation pair the
    # ratify door banks (adjudicate.make_ratified_operation), carrying the applied node.
    node_key = "derivation:result"
    fb = md / "feedback" / "feedback.jsonl"
    with fb.open("a", encoding="utf-8") as f:
        f.write(json.dumps(adj.make_intent_revocation(
            iid, reason="consumed by evolution", actor="gerard", project=CORPUS)) + "\n")
        f.write(json.dumps(adj.make_ratified_operation(
            iid, outcome="applied", op_kind="add-node", object_kind="node",
            object_key=node_key, corpus=CORPUS, actor="gerard", project=CORPUS)) + "\n")

    got = organ.record_growth_nodes(md, CORPUS)
    assert len(got["joined"]) == 1
    assert got["joined"][0] == {"id": "l1", "intent_id": iid, "node_id": node_key}

    # the chain card now carries the node_id — the isnad<->conceptric join is explicit.
    l1 = next(l for l in organ.read_chain(md) if l["id"] == "l1")
    assert l1["node_id"] == node_key and l1["intent_id"] == iid

    # DEDUP: a re-run joins nothing (the link already carries node_id).
    assert organ.record_growth_nodes(md, CORPUS)["joined"] == []


def test_record_growth_nodes_honest_empty(tmp_path: Path):
    # no chain, no ledger — nothing to join, no raise.
    assert organ.record_growth_nodes(tmp_path / "manuscript", CORPUS) == {"joined": []}
