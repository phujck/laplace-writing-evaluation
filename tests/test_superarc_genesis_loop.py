"""The item-genesis loop: P0, lens packets, typed residue, convergence, budget,
the global submission and the append-only ledger.

The proposer is a stub — the seam exists so these run offline — but everything
under it is the real thing: real subprocess execution of every candidate, the
real submission gate, the real classifier, the real φ. The defects worth catching
(a convergence record that cannot be recomputed from the file, a withdrawal that
overwrites, a packet that offers the worker failure, an objective that reads δ)
only show up when the organs below are not stubs too.
"""
from __future__ import annotations

import inspect
import json

import pytest

from laplace.research.superarc import genesis_loop as gl
from laplace.research.superarc import phi
from laplace.research.superarc.bin_classifier import Bin

# A real dev-suite item with a known generator: period 4, a(n) = 1 iff n ≡ 3.
ITEM = gl.Item("dev-0-018", "0,0,0,1,0,0,0,1,0,0,0,1")
GENERATOR = 'print(",".join("1" if n % 4 == 3 else "0" for n in range(12)))'
FORMULA = "a(n)=1 if n mod 4 == 3 else 0"
#: Verifies byte for byte, but the gate refuses its formula as a lookup table —
#: banked as evidence, never a submission.
TABLE_FORMULA = "a(n)=[0,0,0,1][n%4]"
#: Diverges at index 2 (the same rule with the wrong modulus).
WRONG = 'print(",".join("1" if n % 3 == 2 else "0" for n in range(12)))'
#: Diverges at index 0 and never advances.
STUCK = 'print("9")'


def _ledger(tmp_path, name="genesis.jsonl"):
    return gl.Ledger(tmp_path / "genesis" / name)


def _row(row_id, *, item_id="i1", round_=0, kind="verified", subject="s",
         supersedes=(), **data):
    return gl.Row(row_id, item_id, round_, kind, subject, gl.OBSERVED_BY,
                  tuple(supersedes), data)


def _verified(row_id, round_, bin_, *, candidate_id=None, admitted=True, formula="a(n)=n"):
    return _row(row_id, round_=round_, kind="verified",
                candidate_id=candidate_id or row_id, formula=formula,
                gate_admitted=admitted, bin=bin_.value if bin_ else None)


# --------------------------------------------------------------------------- #
# P0 — the sequence, verbatim, never edited
# --------------------------------------------------------------------------- #


def test_p0_is_the_sequence_and_nothing_else():
    assert gl.prompt_zero(ITEM) == ITEM.sequence
    assert gl.carries_p0(gl.prompt_zero(ITEM), ITEM)


def test_every_rewrite_opens_with_p0_byte_for_byte():
    account = [{"class": "wrong-tail", "index": 2, "got": "1", "expected": "0",
                "round": 0, "lens": "closed-form"}]
    p1 = gl.rewrite_prompt(ITEM, account)
    assert gl.carries_p0(p1, ITEM)
    assert p1.startswith(ITEM.sequence)
    # a full rewrite from P0, not an edit of it: the residue is appended below,
    # the item's own literal is untouched above.
    assert "wrong-tail" in p1 and "index 2" in p1
    p2 = gl.rewrite_prompt(ITEM, account, {"formula": FORMULA})
    assert gl.carries_p0(p2, ITEM)
    assert "Promotion target" in p2


def test_a_prompt_that_lost_p0_cannot_be_composed():
    with pytest.raises(ValueError, match="P0"):
        gl.compose_packet(ITEM, "some rewritten framing", "closed-form", 1)


# --------------------------------------------------------------------------- #
# The packets — k lenses, the kernel, the stamp, the motive law
# --------------------------------------------------------------------------- #


def test_a_round_composes_one_packet_per_lens_with_an_explicit_clamped_stamp():
    packets = gl.compose_round(ITEM, gl.prompt_zero(ITEM), 0, k=3)
    assert [p.lens for p in packets] == list(gl.LENSES[:3])
    assert {p.model for p in packets} == {"opus"}
    for p in packets:
        assert p.round == 0 and p.item_id == ITEM.item_id
        assert "You are one node in a graded hierarchy" in p.prompt
        assert "<!-- OBJECT -->" in p.prompt and "<!-- POLICY -->" in p.prompt
        assert ITEM.sequence in p.prompt
        assert gl.LENS_FRAMES[p.lens] in p.prompt


def test_k_beyond_the_lens_set_is_refused():
    with pytest.raises(ValueError, match="exceeds"):
        gl.compose_round(ITEM, gl.prompt_zero(ITEM), 0, k=len(gl.LENSES) + 1)


def test_no_packet_offers_the_worker_an_option_of_failure():
    for p in gl.compose_round(ITEM, gl.rewrite_prompt(
            ITEM, [{"class": "no-output", "index": None, "round": 0, "lens": "automaton"}]), 1):
        assert gl.motive_violations(p.prompt) == []
    assert "generator exists and it is findable" in gl.MOTIVE


def test_a_failure_offer_is_caught_at_composition(monkeypatch):
    monkeypatch.setattr(gl, "MOTIVE", gl.MOTIVE + " If you cannot find it, report failure.")
    with pytest.raises(ValueError, match="offers failure"):
        gl.compose_packet(ITEM, gl.prompt_zero(ITEM), "closed-form", 0)


def test_a_packet_never_names_the_scorer():
    # the instrument that scores us is never what the worker optimizes against
    for p in gl.compose_round(ITEM, gl.prompt_zero(ITEM), 0):
        body = p.prompt.split("<!-- OBJECT -->", 1)[1]
        assert gl.metric_mentions(body) == []


def test_a_leaked_metric_is_caught_at_composition(monkeypatch):
    monkeypatch.setattr(gl, "MOTIVE", gl.MOTIVE + " Keep the nBDM of your answer low.")
    with pytest.raises(ValueError, match="names the scorer"):
        gl.compose_packet(ITEM, gl.prompt_zero(ITEM), "closed-form", 0)


# --------------------------------------------------------------------------- #
# The ledger — append-only, one spine, withdrawals that never overwrite
# --------------------------------------------------------------------------- #


def test_rows_append_with_a_spine_and_validate_clean(tmp_path):
    led = _ledger(tmp_path)
    led.append(item_id="i1", round_=0, kind="candidate", subject="a candidate ran",
               candidate_id="c0", passed=False)
    led.append(item_id="i1", round_=1, kind="candidate", subject="another ran",
               candidate_id="c1", passed=True)
    records = led.records()
    assert [r["row_id"] for r in records] == ["S0001", "S0002"]
    assert all(all(k in r for k in gl.SPINE) for r in records)
    assert led.validate() == []


def test_row_data_may_not_shadow_the_spine(tmp_path):
    led = _ledger(tmp_path)
    with pytest.raises(ValueError, match="spine"):
        led.append(item_id="i1", round_=0, kind="candidate", subject="s", round=3)


def test_a_non_integer_round_is_refused_not_silently_false():
    # the original compared a string state against an int and degraded to false
    with pytest.raises(ValueError, match="round must be an integer"):
        gl.Row.from_record({"row_id": "S1", "item_id": "i1", "round": "complete",
                            "kind": "candidate", "subject": "s", "observed_by": "o"})
    with pytest.raises(ValueError, match="round must be an integer"):
        gl.Row.from_record({"row_id": "S1", "item_id": "i1", "round": True,
                            "kind": "candidate", "subject": "s", "observed_by": "o"})


def test_a_withdrawal_is_a_new_row_naming_the_superseded_id(tmp_path):
    led = _ledger(tmp_path)
    first = led.append(item_id="i1", round_=0, kind="verified", subject="verified",
                       candidate_id="c0", bin=Bin.CORRECT_PRINTS.value, gate_admitted=True)
    before = led.raw_lines()
    gl.withdraw(led, [first.row_id], item_id="i1", round_=1,
                subject=f"SUPERSEDED: {first.row_id} replaced on bin promotion",
                scope="submission-of-record")
    after = led.raw_lines()
    assert gl.check_append_only(before, after) == []
    assert after[0] == before[0]  # the withdrawn row is untouched
    assert led.validate() == []


def test_a_withdrawal_without_a_verb_tag_or_a_target_is_refused(tmp_path):
    led = _ledger(tmp_path)
    row = led.append(item_id="i1", round_=0, kind="verified", subject="v",
                     candidate_id="c0", bin=Bin.CORRECT_NONBOTH.value, gate_admitted=True)
    with pytest.raises(ValueError, match="uppercase verb tag"):
        gl.withdraw(led, [row.row_id], item_id="i1", round_=1, subject="quietly dropped",
                    scope="verification")
    with pytest.raises(ValueError, match="scope"):
        gl.withdraw(led, [row.row_id], item_id="i1", round_=1,
                    subject="WITHDRAWN: it did not reproduce", scope="whatever")
    with pytest.raises(ValueError, match="a withdrawal names no superseded row"):
        led.append(item_id="i1", round_=1, kind="withdrawal", subject="WITHDRAWN: nothing",
                   scope="verification")


def test_a_supersedes_target_must_already_exist(tmp_path):
    led = _ledger(tmp_path)
    with pytest.raises(ValueError, match="no earlier row carries"):
        led.append(item_id="i1", round_=0, kind="withdrawal",
                   subject="WITHDRAWN: a row that was never written",
                   supersedes=["S9999"])


def test_the_validator_catches_a_mutated_history():
    rows = [
        _row("S0001").as_record(),
        _row("S0001", kind="candidate").as_record(),
    ]
    assert any("duplicate row_id" in e for e in gl.validate_rows(rows))
    assert gl.check_append_only(["a", "b"], ["a", "B"]) == ["line 1 was rewritten"]
    assert gl.check_append_only(["a", "b"], ["a"])[0].startswith("ledger shrank")


def test_a_transition_row_carries_the_six_items():
    bad = _row("S1", kind="transition", subject="P0 -> P1", prior_representation="x")
    assert any("six items" in e for e in gl.validate_rows([bad.as_record()]))


def test_a_residue_row_is_gated_by_the_benchs_own_invariants():
    smuggled = _row("S1", kind="residue", subject="r",
                    residue={"class": "wrong-tail", "index": 0, "got": "9",
                             "expected": "0", "got_len": 1, "expected_len": 12,
                             "thesis": "the item is periodic"})
    assert any("forbidden synthesis keys" in e for e in gl.validate_rows([smuggled.as_record()]))


# --------------------------------------------------------------------------- #
# The convergence organ — from append-only rows alone
# --------------------------------------------------------------------------- #


def test_convergence_fires_on_a_verified_model_not_on_shrinking_residue():
    rows = [
        _row("S1", kind="residue", round_=0, subject="r",
             residue={"class": "wrong-tail", "index": 2, "got": "1", "expected": "0",
                      "got_len": 12, "expected_len": 12}),
        _row("S2", kind="residue", round_=1, subject="r",
             residue={"class": "wrong-tail", "index": 7, "got": "1", "expected": "0",
                      "got_len": 12, "expected_len": 12}),
    ]
    assert gl.convergence(rows, "i1").converged is False
    rows.append(_verified("S3", 2, Bin.CORRECT_NONBOTH))
    record = gl.convergence(rows, "i1")
    assert record.converged is True
    assert record.signal == gl.SIGNAL_FOUND
    assert record.first_round == 2 and record.best_row_id == "S3"


def test_convergence_deduplicates_by_candidate_id_before_counting():
    # the original counted rows, not entities: one card with two rows satisfied
    # a ">= 2 other cards" test on its own
    rows = [
        _verified("S1", 0, Bin.CORRECT_NONBOTH, candidate_id="c0"),
        _verified("S2", 1, Bin.CORRECT_NONBOTH, candidate_id="c0"),
        _verified("S3", 1, Bin.CORRECT_NONBOTH, candidate_id="c1"),
    ]
    assert gl.convergence(rows, "i1").distinct_verified == 2


def test_only_a_verification_withdrawal_can_un_converge_an_item():
    verified = _verified("S1", 0, Bin.CORRECT_NONBOTH, candidate_id="c0")
    denied = gl.convergence([
        verified,
        _row("S2", round_=1, kind="withdrawal", supersedes=["S1"], scope="verification",
             subject="WITHDRAWN: S1's byte-compare did not reproduce on re-run"),
    ], "i1")
    assert denied.converged is False
    assert denied.withdrawn == ("S1",)

    # a promotion retires the ANSWER, not the verification behind it
    retired = gl.convergence([
        verified,
        _verified("S3", 1, Bin.CORRECT_NONBOTH, candidate_id="c1"),
        _row("S2", round_=1, kind="withdrawal", supersedes=["S1"],
             scope="submission-of-record",
             subject="SUPERSEDED: S1's submission of record, replaced by S3"),
    ], "i1")
    assert retired.converged is True
    assert retired.best_row_id == "S3"
    assert retired.distinct_verified == 2


def test_convergence_records_a_bin_promotion():
    rows = [
        _verified("S1", 0, None, candidate_id="c0", admitted=False, formula=TABLE_FORMULA),
        _verified("S2", 1, Bin.CORRECT_NONBOTH, candidate_id="c1", formula=FORMULA),
    ]
    record = gl.convergence(rows, "i1")
    assert record.signal == gl.SIGNAL_PROMOTED
    assert record.best_row_id == "S2" and record.best_bin is Bin.CORRECT_NONBOTH
    assert record.promotions[0]["round"] == 1


def test_convergence_reads_only_this_items_rows():
    rows = [_verified("S1", 0, Bin.CORRECT_NONBOTH), _row("S2", item_id="other", kind="verified",
                                                          candidate_id="c9", gate_admitted=True,
                                                          bin=Bin.CORRECT_NONBOTH.value)]
    assert gl.convergence(rows, "other").best_row_id == "S2"
    assert gl.convergence(rows, "i1").best_row_id == "S1"


# --------------------------------------------------------------------------- #
# δ is measured, never optimized
# --------------------------------------------------------------------------- #


def test_selection_ranks_by_bin_and_reads_no_complexity_measure():
    rows = [
        _verified("S1", 0, Bin.CORRECT_ORDINAL, candidate_id="c0"),
        _verified("S2", 1, Bin.CORRECT_NONBOTH, candidate_id="c1"),
        _verified("S3", 2, None, candidate_id="c2", admitted=False),
    ]
    assert gl.select_best(rows).row_id == "S2"
    # the objective itself, docstring stripped: no complexity measure is read
    body = inspect.getsource(gl.select_best).lower().split('"""')[-1]
    assert "bdm" not in body and "delta" not in body and "len(" not in body


def test_an_unadmitted_formula_is_never_the_submission_of_record():
    rows = [_verified("S1", 0, None, candidate_id="c0", admitted=False)]
    assert gl.select_best(rows) is None


# --------------------------------------------------------------------------- #
# Budget — allocated, not merely spent
# --------------------------------------------------------------------------- #


def test_p_closure_rewards_advances_and_decays_with_the_rounds_left():
    assert gl.p_closure(0, 0, 0) == 0.0
    stalled = gl.p_closure(0, 5, 1)
    advancing = gl.p_closure(3, 5, 1)
    assert 0.0 < stalled < advancing < 1.0
    assert gl.p_closure(0, 5, 3) > gl.p_closure(0, 5, 1)


def test_allocate_reserves_a_round_for_every_unattempted_item():
    assert gl.allocate(3, 3, 6) == 1
    assert gl.allocate(10, 2, 6) == 6
    assert gl.allocate(2, 3, 6) == 1      # the tail starves, never the head
    assert gl.allocate(0, 2, 6) == 0


def test_a_stalled_item_is_abandoned_before_its_rounds_run_out(tmp_path):
    led = _ledger(tmp_path)
    result = gl.run_item(ITEM, lambda p: [gl.Proposal(STUCK, "a(n)=9")], ledger=led,
                         max_rounds=4, k=1, abandon_threshold=0.6)
    assert result.abandoned is True
    assert result.closed is False
    assert result.rounds_used < 4
    kinds = [r.kind for r in led.rows()]
    assert "abandonment" in kinds
    assert result.gap.why_iteration_cannot == "budget-exhausted"


def test_freed_rounds_reallocate_to_unattempted_items(tmp_path):
    led = _ledger(tmp_path)
    items = [gl.Item(f"i{i}", ITEM.sequence) for i in range(3)]
    campaign = gl.run_campaign(
        items, lambda p: [gl.Proposal(STUCK, "a(n)=9")], ledger=led,
        budget=gl.Budget(total_rounds=3, max_rounds_per_item=6, abandon_threshold=0.0),
        k=1, score=False)
    assert [r.rounds_used for r in campaign.results] == [1, 1, 1]
    assert campaign.rounds_spent == 3


def test_an_item_the_pool_cannot_reach_is_never_attempted(tmp_path):
    led = _ledger(tmp_path)
    items = [gl.Item(f"i{i}", ITEM.sequence) for i in range(3)]
    campaign = gl.run_campaign(
        items, lambda p: [gl.Proposal(STUCK, "a(n)=9")], ledger=led,
        budget=gl.Budget(total_rounds=2, max_rounds_per_item=1), k=1, score=False)
    assert [r.rounds_used for r in campaign.results] == [1, 1, 0]
    assert campaign.results[-1].gap.why_iteration_cannot == "budget-exhausted"
    assert campaign.results[-1].abandoned is True


# --------------------------------------------------------------------------- #
# The rounds — residue rewrites the next prompt, and only when there is any
# --------------------------------------------------------------------------- #


def test_residue_rewrites_the_next_rounds_prompt_and_that_is_what_closes_it(tmp_path):
    """The stub only produces the generator once the prompt carries the residue —
    so a loop that failed to rewrite could not close this item at all."""
    seen: list[str] = []

    def proposer(packet):
        seen.append(packet.prompt)
        if "off-by-index" in packet.prompt:
            return [gl.Proposal(GENERATOR, FORMULA)]
        return [gl.Proposal(WRONG, "a(n)=1 if n mod 3 == 2 else 0")]

    led = _ledger(tmp_path)
    result = gl.run_item(ITEM, proposer, ledger=led, max_rounds=3, k=1)
    assert result.closed is True
    assert result.rounds_used == 2
    assert ITEM.sequence not in seen[0].split("<!-- OBJECT -->")[0]  # P0 rides the OBJECT
    transitions = [r for r in led.rows() if r.kind == "transition"]
    assert len(transitions) == 1
    six = transitions[0].data
    assert all(str(six[k]).strip() for k in gl.SIX_ITEMS)
    assert "off-by-index" in six["residue_unabsorbed"]


def test_a_round_that_adds_no_residue_banks_the_absence_instead_of_a_rewrite(tmp_path):
    led = _ledger(tmp_path)
    gl.run_item(ITEM, lambda p: [gl.Proposal(WRONG, "a(n)=?")], ledger=led,
                max_rounds=2, k=1, abandon_threshold=0.0)
    kinds = [r.kind for r in led.rows()]
    assert kinds.count("transition") == 1   # round 0 only
    assert kinds.count("no-rewrite") == 1   # round 1 repeated the same divergence


def test_a_candidate_that_prints_nothing_never_converges(tmp_path):
    led = _ledger(tmp_path)
    result = gl.run_item(ITEM, lambda p: [gl.Proposal("pass", FORMULA)], ledger=led,
                         max_rounds=1, k=1)
    assert result.closed is False
    residues = [r.data["residue"] for r in led.rows() if r.kind == "residue"]
    assert [r["class"] for r in residues] == ["no-output"]
    assert result.gap.why_iteration_cannot == "budget-exhausted"


# --------------------------------------------------------------------------- #
# Promotion, end to end
# --------------------------------------------------------------------------- #


def test_a_verified_but_unsubmittable_model_is_promoted_and_the_old_one_withdrawn(tmp_path):
    def proposer(packet):
        if "Promotion target" in packet.prompt:
            return [gl.Proposal(GENERATOR, FORMULA)]
        return [gl.Proposal(GENERATOR, TABLE_FORMULA)]

    led = _ledger(tmp_path)
    result = gl.run_item(ITEM, proposer, ledger=led, max_rounds=3, k=1)
    rows = led.rows()
    assert [r.kind for r in rows].count("promotion") == 1
    withdrawal = next(r for r in rows if r.kind == "withdrawal")
    assert withdrawal.supersedes and withdrawal.subject.startswith("SUPERSEDED")
    assert result.bin is Bin.CORRECT_NONBOTH
    assert result.answer == FORMULA
    assert result.convergence.signal == gl.SIGNAL_PROMOTED
    assert led.validate() == []


def test_a_verified_model_whose_formula_the_gate_refuses_is_a_capability_gap(tmp_path):
    led = _ledger(tmp_path)
    result = gl.run_item(ITEM, lambda p: [gl.Proposal(GENERATOR, TABLE_FORMULA)],
                         ledger=led, max_rounds=1, k=1)
    assert result.closed is True and result.submitted is False
    assert result.gap.why_iteration_cannot == "capability"
    assert result.gap.why_iteration_cannot != "budget-exhausted"


def test_capability_gap_reasons_are_typed():
    with pytest.raises(ValueError, match="why_iteration_cannot"):
        gl.CapabilityGap("i1", "g", "o", "we ran out of ideas", 0, "e")
    assert "budget-exhausted" in gl.WHY_ITERATION_CANNOT
    assert set(gl.WHY_ITERATION_CANNOT) == {"missing-math", "capability", "budget-exhausted"}


def test_capability_gaps_append_to_their_own_file(tmp_path):
    gap = gl.CapabilityGap("i1", "g", "o", "missing-math", 0, "e")
    path = gl.write_capability_gaps([gap], tmp_path / "capability_gaps.jsonl")
    gl.write_capability_gaps([gap], path)
    rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert set(rows[0]) == {"item_id", "gap", "what_organ_would_close_it",
                            "why_iteration_cannot", "first_seen_round", "evidence"}


# --------------------------------------------------------------------------- #
# The global submission
# --------------------------------------------------------------------------- #


def _row_for(item_id, nbdm_input, nbdm_answer, bin_=Bin.CORRECT_NONBOTH):
    return phi.LedgerRow(item_id, "a(n)=n", bin_, nbdm_input, nbdm_answer)


def test_the_preregistered_rule_submits_every_item_including_the_unclosed(tmp_path):
    led = _ledger(tmp_path)

    def proposer(packet):
        return [gl.Proposal(GENERATOR, FORMULA)] if packet.item_id == "closes" \
            else [gl.Proposal(STUCK, "a(n)=9")]

    items = [gl.Item("closes", ITEM.sequence), gl.Item("stalls", ITEM.sequence)]
    campaign = gl.run_campaign(items, proposer, ledger=led,
                               budget=gl.Budget(total_rounds=2, max_rounds_per_item=1), k=1)
    sub = campaign.submission
    assert sub.rule == gl.SUBMISSION_RULE
    assert len(sub.rows) == 2                      # every item, no dropped rows
    assert sub.submitted == ("closes",) and sub.withheld == ("stalls",)
    assert sub.score.counts == (1, 0, 0, 1)        # the incorrect bin is in the denominator
    assert 0.0 < sub.score.phi < 1.0


def test_a_selective_submission_rule_is_refused_at_the_door():
    with pytest.raises(ValueError, match="declared before the run"):
        gl.global_submission([], rule="drop-the-low-delta-items")


def test_the_bin_interaction_is_disclosed_not_acted_on():
    """A correct-but-low-δ answer can LOWER φ — δ_k is a harmonic mean, so one
    near-zero ratio drags its whole bin down. The comparison exists so the
    fragility is on the record; the preregistered rule still submits everything."""
    rows = [_row_for("a", 0.6, 0.6), _row_for("b", 0.6, 0.6), _row_for("c", 0.05, 5.0)]
    scores = gl.compare_submission_sets(rows, {
        "preregistered": ["a", "b", "c"],
        "drop-the-low-delta-item": ["a", "b"],
    })
    assert scores["drop-the-low-delta-item"].phi > scores["preregistered"].phi
    assert scores["drop-the-low-delta-item"].counts == (2, 0, 0, 1)
    assert scores["preregistered"].n == scores["drop-the-low-delta-item"].n == 3


# --------------------------------------------------------------------------- #
# The acceptance clause — one dev fixture closes, and the record is recomputable
# --------------------------------------------------------------------------- #


def test_a_dev_item_with_a_known_generator_closes_end_to_end(tmp_path):
    def proposer(packet):
        if "PRIOR ATTEMPTS" in packet.prompt:
            return [gl.Proposal(GENERATOR, FORMULA, note="modulus corrected from the residue")]
        return [gl.Proposal(WRONG, "a(n)=1 if n mod 3 == 2 else 0")]

    path = tmp_path / "genesis" / "genesis.jsonl"
    campaign = gl.run_campaign([ITEM], proposer, ledger=gl.Ledger(path),
                               budget=gl.Budget(total_rounds=4, max_rounds_per_item=4), k=2)
    result = campaign.results[0]
    assert result.closed is True and result.submitted is True
    assert result.answer == FORMULA and result.bin is Bin.CORRECT_NONBOTH
    assert campaign.gaps == ()
    assert campaign.submission.score.phi > 0.0

    # …and the whole record is recomputable from the append-only file ALONE.
    records = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()]
    assert gl.validate_rows(records) == []
    # every P_n the run wrote still opens with P0, byte for byte
    assert all(r["prompt"].startswith(ITEM.sequence)
               for r in records if r["kind"] == "transition")
    replayed = gl.convergence(records, ITEM.item_id)
    assert replayed.as_record() == result.convergence.as_record()
    assert replayed.converged and replayed.signal == gl.SIGNAL_FOUND
    assert replayed.best_formula == FORMULA

    # φ too: the submission rows carry both nBDM values, so the score survives as
    # arithmetic over the ledger with no item bank and no BDM engine.
    recomputed = phi.from_ledger([r.as_record() for r in gl.phi_rows(records)], expected_n=None)
    assert recomputed.phi == pytest.approx(campaign.submission.score.phi)


def test_the_ledger_is_append_only_across_a_second_run(tmp_path):
    path = tmp_path / "genesis" / "genesis.jsonl"
    led = gl.Ledger(path)
    gl.run_item(ITEM, lambda p: [gl.Proposal(GENERATOR, FORMULA)], ledger=led,
                max_rounds=1, k=1)
    before = led.raw_lines()
    reopened = gl.Ledger(path)
    gl.run_item(gl.Item("dev-0-000", "0,0,0,0"), lambda p: [gl.Proposal('print("0,0,0,0")', "a(n)=0")],
                ledger=reopened, max_rounds=1, k=1)
    after = reopened.raw_lines()
    assert gl.check_append_only(before, after) == []
    assert len(after) > len(before)
    assert reopened.validate() == []
    assert len({r["row_id"] for r in reopened.records()}) == len(after)
