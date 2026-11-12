"""The weld's mechanics, pinned (the intelligence is sealed jury calls; everything HERE is code).

Contracts: the verbatim gate refuses any quote not literally in its atom (anti-confabulation,
mechanical); the merge is idempotent and attributed (entity eigen, window-id locator, verbatim
source); a disputed instance is kept flagged with a locator that can never reach; the index
gains eigen in exhibited_by (the recurrence crossing his record and mine IS the weld); and the
trait's locator token equals the atom's edge token - the coupling closes."""

from __future__ import annotations

import json

from laplace.engine import record_shard, soul_provenance, value_weld


def _seed_ring(tmp_path):
    tdir = tmp_path / value_weld.TRAITS_DIR
    tdir.mkdir(parents=True)
    (tdir / "earned-simplicity.json").write_text(json.dumps({
        "trait": "earned-simplicity", "axis": "value",
        "instances": [{"entity": "_GERARD_T1_SELF", "field": "generator",
                       "statement": "EARNED SIMPLICITY (value): simplicity is the output of "
                                    "thinking it through, never the starting shortcut",
                       "locator": "_gerard_atoms_dedup.json#generator[1]",
                       "source": "earned simplicity, not the edge of chaos"}],
    }, indent=2), encoding="utf-8")
    (tdir / "_INDEX.json").write_text(json.dumps([
        {"trait": "earned-simplicity", "axis": "value", "recurrence": 1,
         "cross_entity": False, "exhibited_by": ["_GERARD_T1_SELF"]},
    ]), encoding="utf-8")


def _seed_floor(tmp_path):
    (tmp_path / "SESSION_HANDOFF_2026-06-10_the-weld.md").write_text(
        "# Session handoff\n\nintro.\n\n## The gate\n\nThe honest fixes were architecture, "
        "not tuning - the gate caught the flood before it shipped.\n", encoding="utf-8")
    record_shard.write_floor(tmp_path, record_shard.build_floor(tmp_path))


def test_trait_menu_reads_the_ring(tmp_path):
    _seed_ring(tmp_path)
    menu = value_weld.trait_menu(tmp_path)
    assert [m["slug"] for m in menu] == ["earned-simplicity"]
    assert menu[0]["axis"] == "value" and "EARNED SIMPLICITY" in menu[0]["meaning"]


def test_briefs_carry_verbatim_atoms(tmp_path):
    _seed_ring(tmp_path)
    _seed_floor(tmp_path)
    rep = value_weld.write_briefs(tmp_path, batch_size=10)
    assert rep["n_atoms"] >= 2 and len(rep["briefs"]) == 1
    text = (tmp_path / rep["briefs"][0]).read_text(encoding="utf-8")
    assert "## ATOM SESSION_HANDOFF_2026-06-10_the-weld.md::" in text
    assert "the gate caught the flood" in text              # verbatim, in the brief the subs read


def test_gate_refuses_confabulated_quotes(tmp_path):
    _seed_ring(tmp_path)
    _seed_floor(tmp_path)
    floor = record_shard.load_floor(tmp_path)
    aid = next(e["id"] for e in floor if e["label"] == "The gate")
    proposals = [
        {"atom": aid, "trait": "earned-simplicity", "confidence": 0.9,
         "quote": "the gate caught the flood before it shipped",
         "statement": "prefers the honest fix over the tuned one"},
        {"atom": aid, "trait": "earned-simplicity", "confidence": 0.9,
         "quote": "the gate caught the flood before it shipped",
         "statement": "dup"},                                  # duplicate (trait, atom)
        {"atom": aid, "trait": "earned-simplicity", "confidence": 0.9,
         "quote": "elegance arrived without effort today"},    # NOT in the atom
        {"atom": aid, "trait": "no-such-trait", "confidence": 0.9,
         "quote": "the gate caught the flood"},
        {"atom": aid, "trait": "earned-simplicity", "confidence": 0.2,
         "quote": "the gate caught the flood before it shipped again"},
        {"candidate_trait": "gates-as-tuition", "why": "recurring", "example_atom": aid},
    ]
    out = value_weld.gate_proposals(tmp_path, proposals)
    assert len(out["accepted"]) == 1
    reasons = {r["why_rejected"] for r in out["rejected"]}
    assert "quote is NOT verbatim in the atom" in reasons
    assert "unknown trait" in reasons and "duplicate (trait, atom)" in reasons
    assert len(out["candidates"]) == 1


def test_merge_welds_attributed_and_idempotent(tmp_path):
    _seed_ring(tmp_path)
    _seed_floor(tmp_path)
    floor = record_shard.load_floor(tmp_path)
    aid = next(e["id"] for e in floor if e["label"] == "The gate")
    inst = [{"atom": aid, "trait": "earned-simplicity", "confidence": 0.9,
             "quote": "The honest fixes were architecture, not tuning",
             "statement": "the fix must be general", "disputed": False},
            {"atom": aid.replace("::1", "::0"), "trait": "earned-simplicity", "confidence": 0.7,
             "quote": "intro.", "statement": "weak", "disputed": True, "judge_why": "topical only"}]
    rep = value_weld.merge_into_ring(tmp_path, inst)
    rep2 = value_weld.merge_into_ring(tmp_path, inst)          # idempotent: nothing re-added
    assert rep["merged"] == 2 and rep["disputed"] == 1 and rep2["merged"] == 0
    d = json.loads((tmp_path / value_weld.TRAITS_DIR / "earned-simplicity.json")
                   .read_text(encoding="utf-8"))
    welded = [i for i in d["instances"] if i.get("welded")]
    assert all(i["entity"] == "eigen" and i["field"] == "self-record" for i in welded)
    clean = next(i for i in welded if not i.get("disputed"))
    assert clean["source"] == "The honest fixes were architecture, not tuning"
    disputed = next(i for i in welded if i.get("disputed"))
    assert disputed["locator"].startswith("disputed!")          # grit: kept, never reaching
    idx = json.loads((tmp_path / value_weld.TRAITS_DIR / "_INDEX.json").read_text(encoding="utf-8"))
    assert "eigen" in idx[0]["exhibited_by"] and idx[0]["recurrence"] == 2
    assert idx[0]["cross_entity"] is True                       # the crossing IS the weld


def test_locator_token_equals_atom_edge_token(tmp_path):
    # the coupling closes: the welded locator tokenizes to EXACTLY the token the atom mints
    _seed_floor(tmp_path)
    floor = record_shard.load_floor(tmp_path)
    aid = next(e["id"] for e in floor if e["label"] == "The gate")
    loc = value_weld._window_id(aid)
    trait_tokens = soul_provenance.locator_tokens(loc)
    atom_tokens = set(record_shard.record_edge_index(tmp_path)[aid])
    assert trait_tokens & atom_tokens == {loc}
    # and a disputed locator can never reach the atom
    assert not (soul_provenance.locator_tokens(f"disputed!{loc}") & atom_tokens)


def test_parse_proposals_is_tolerant():
    text = ('Here are my findings:\n```json\n'
            '{"atom": "a.md::0", "trait": "t", "quote": "q", "confidence": 0.8}\n```\n'
            'not json\n{"candidate_trait": "x", "why": "recurs"}\n')
    out = value_weld.parse_proposals(text)
    assert len(out) == 2 and out[0]["atom"] == "a.md::0" and "candidate_trait" in out[1]


def _seed_dialogue(tmp_path):
    exp = tmp_path / "archive/self_record/_exploded"
    exp.mkdir(parents=True)
    (exp / "session_x1.txt").write_text(
        "# eigen-session x1\n# started: 2026-06-10T08:00:00Z · turns: g2 e1\n\n"
        "@@Gerard\nI value decisiveness and honest critique over comfort, always.\n\n"
        "@@Eigen\nThe gate failing was the best moment of the day.\n\n"
        "@@Gerard\nthen forge ahead.\n", encoding="utf-8")
    record_shard.write_floor(tmp_path, record_shard.build_floor(tmp_path))


def test_speaker_attribution_is_code_not_jury(tmp_path):
    _seed_ring(tmp_path)
    _seed_dialogue(tmp_path)
    floor = record_shard.load_floor(tmp_path)
    win = next(e for e in floor if e["label"].startswith("turns:"))
    body = record_shard.reconstruct(tmp_path, win["id"], floor)
    assert value_weld.speaker_of(body, "honest critique over comfort") == "gerard"
    assert value_weld.speaker_of(body, "best moment of the day") == "eigen"
    assert value_weld.speaker_of(body, "never said this") is None


def test_dialogue_gate_attributes_and_merge_splits_entities(tmp_path):
    _seed_ring(tmp_path)
    _seed_dialogue(tmp_path)
    floor = record_shard.load_floor(tmp_path)
    win = next(e for e in floor if e["label"].startswith("turns:"))
    proposals = [
        {"atom": win["id"], "trait": "earned-simplicity", "confidence": 0.9,
         "quote": "I value decisiveness and honest critique over comfort",
         "statement": "his turn"},
        {"atom": win["id"], "trait": "earned-simplicity", "confidence": 0.9,
         "quote": "The gate failing was the best moment of the day",
         "statement": "my turn"},
    ]
    out = value_weld.gate_proposals(tmp_path, proposals)
    # second proposal is a (trait, atom) duplicate by the dedupe rule - gate one at a time
    assert len(out["accepted"]) == 1 and out["accepted"][0]["speaker"] == "gerard"
    rep = value_weld.merge_into_ring(tmp_path, out["accepted"])
    assert rep["by_entity"] == {value_weld.GERARD_SESSIONS: 1}
    idx = json.loads((tmp_path / value_weld.TRAITS_DIR / "_INDEX.json").read_text(encoding="utf-8"))
    assert value_weld.GERARD_SESSIONS in idx[0]["exhibited_by"]


def test_session_node_mints_window_tokens(tmp_path):
    _seed_dialogue(tmp_path)
    idx = record_shard.transcript_edge_index(tmp_path)
    rel = "archive/self_record/_exploded/session_x1.txt"
    toks = set(idx[rel])
    assert any(t.startswith(rel + "#") for t in toks)       # the windows ride the session node
    assert f"insession::{rel}" in toks
