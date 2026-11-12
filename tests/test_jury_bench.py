"""N27's instrument, pinned (mechanical parts only - the model under test is the experiment).

Contracts: gold pairing reads the banked verdicts; controls are deterministic trait-swaps whose
gold is refuse and whose trait genuinely differs; the verdict parser survives think-blocks and
fences; the score separates agreement from discrimination and counts the unparsed honestly."""

from __future__ import annotations

import json

from laplace.engine import jury_bench


def test_make_controls_swaps_traits_deterministically():
    inst = [{"trait": f"t{i % 4}", "atom": f"a{i}", "quote": "q" * 20, "statement": "s",
             "gold": "accept", "tranche": "judge", "control": False} for i in range(12)]
    c1 = jury_bench.make_controls(inst, 6, seed=11)
    c2 = jury_bench.make_controls(inst, 6, seed=11)
    assert [c["atom"] for c in c1] == [c["atom"] for c in c2]      # seeded, reproducible
    assert all(c["gold"] == "refuse" and c["control"] for c in c1)
    by_atom = {p["atom"]: p["trait"] for p in inst}
    assert all(c["trait"] != by_atom[c["atom"]] for c in c1)       # the trait genuinely swapped


def test_sample_keeps_all_refusals():
    inst = ([{"trait": "t", "atom": f"r{i}", "quote": "q" * 20, "statement": "",
              "gold": "refuse", "tranche": "judge", "control": False} for i in range(3)]
            + [{"trait": "t2", "atom": f"a{i}", "quote": "q" * 20, "statement": "",
                "gold": "accept", "tranche": "judge", "control": False} for i in range(20)])
    tasks = jury_bench.sample_tasks(inst, n_accepts=5, n_controls=4, seed=7)
    refusal_atoms = {t["atom"] for t in tasks if t["gold"] == "refuse" and not t["control"]}
    assert refusal_atoms == {"r0", "r1", "r2"}                     # few and precious - all kept
    assert sum(1 for t in tasks if t["control"]) == 4
    assert sum(1 for t in tasks if t["gold"] == "accept") == 5


def test_parse_verdict_survives_think_blocks_and_fences():
    assert jury_bench.parse_verdict(
        '<think>hmm, the quote is topical only...</think>\n{"verdict": "refuse", "why": "topical"}'
    ) == "refuse"
    assert jury_bench.parse_verdict('```json\n{"verdict": "accept", "why": "enacted"}\n```') == "accept"
    assert jury_bench.parse_verdict("I would REFUSE this instance.") == "refuse"
    assert jury_bench.parse_verdict("<think>accept? no...</think>") is None   # think text never counts


def test_score_separates_agreement_from_discrimination():
    rows = [
        {"gold": "accept", "pred": "accept", "control": False, "ms": 1000},
        {"gold": "accept", "pred": "refuse", "control": False, "ms": 1000},
        {"gold": "refuse", "pred": "refuse", "control": False, "ms": 1000},
        {"gold": "refuse", "pred": "refuse", "control": True, "ms": 1000},
        {"gold": "refuse", "pred": "accept", "control": True, "ms": 1000},
        {"gold": "accept", "pred": "unparsed", "control": False, "ms": 1000},
    ]
    m = jury_bench.score(rows)
    assert m["n_real"] == 3 and m["n_controls"] == 2 and m["n_unparsed"] == 1
    assert m["agreement_overall"] == round(2 / 3, 3)
    assert m["agreement_on_accepts"] == 0.5
    assert m["agreement_on_refusals"] == 1.0
    assert m["control_refuse_rate"] == 0.5


def test_prompt_carries_the_pieces(tmp_path):
    from laplace.engine import record_shard, value_weld
    tdir = tmp_path / value_weld.TRAITS_DIR
    tdir.mkdir(parents=True)
    (tdir / "earned-simplicity.json").write_text(json.dumps({
        "trait": "earned-simplicity", "axis": "value",
        "instances": [{"statement": "EARNED SIMPLICITY (value): thought through"}]}),
        encoding="utf-8")
    (tmp_path / "SESSION_HANDOFF_2026-06-10_x.md").write_text(
        "# H\n\n## S\n\nthe honest fix was architecture.\n", encoding="utf-8")
    record_shard.write_floor(tmp_path, record_shard.build_floor(tmp_path))
    floor = record_shard.load_floor(tmp_path)
    aid = next(e["id"] for e in floor if e["label"] == "S")
    p = jury_bench.prompt_for(tmp_path, {"trait": "earned-simplicity", "atom": aid,
                                         "quote": "the honest fix", "statement": ""})
    assert "EARNED SIMPLICITY" in p and "the honest fix was architecture." in p
    assert '"verdict"' in p
