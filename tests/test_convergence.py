"""The convergence contract algebra: hard gates, dominance, voice's burden of
proof, the disagreement matrix, and the stop rule (convergence != exhaustion)."""
from laplace.pipeline import convergence as C


def _ev(hard=True, **soft):
    """A candidate evaluation: all hard dims `hard`, soft dims from kwargs (default 0.5)."""
    h = {d: hard for d in C.HARD_DIMENSIONS}
    s = {d: soft.get(d, 0.5) for d in C.SOFT_DIMENSIONS}
    return {"hard": h, "soft": s}


# --- hard gates are non-compensable -----------------------------------------
def test_hard_gate_blocks_regardless_of_soft_excellence():
    great_soft = _ev(hard=True, prose_transparency=1.0, authorial_fit=1.0, rhythm=1.0)
    assert C.hard_pass(great_soft)
    broken = {"hard": {**great_soft["hard"], "semantic_identity": False},
              "soft": great_soft["soft"]}
    assert not C.hard_pass(broken)
    d = C.accept_candidate(broken, incumbent=None)
    assert d["accept"] is False and "hard gate" in d["reason"]


# --- dominance: improvement, not mere change --------------------------------
def test_dominance_requires_material_improvement_no_degradation():
    inc = _ev(prose_transparency=0.5, rhythm=0.5)
    better = _ev(prose_transparency=0.8, rhythm=0.5)       # one improves, none degrades
    churn = _ev(prose_transparency=0.51, rhythm=0.49)      # sub-eps wobble = not material
    tradeoff = _ev(prose_transparency=0.8, rhythm=0.2)     # improves one, degrades another
    assert C.dominates(better, inc)
    assert not C.dominates(churn, inc)
    assert not C.dominates(tradeoff, inc)


def test_accept_seeds_incumbent_then_requires_dominance():
    first = _ev()
    assert C.accept_candidate(first, incumbent=None)["accept"] is True   # seeds
    same = _ev()
    assert C.accept_candidate(same, incumbent=first)["accept"] is False  # no improvement


# --- voice's burden of proof against the neutral reference surface ----------
def test_voice_must_dominate_neutral_and_trigger_no_prohibition():
    neutral = _ev(prose_transparency=0.5, authorial_fit=0.5)
    voice_better = _ev(prose_transparency=0.5, authorial_fit=0.8)
    clean = {"content_delta": 0, "reader_effort_delta": 0.0, "repetition_delta": 0.0,
             "conspicuousness_delta": 0.0, "clarity_delta": 0.0}
    # dominates + clean -> accepted
    assert C.voice_dominates_neutral(voice_better, neutral, clean)
    # same soft, but adds content -> rejected (prohibition)
    added = dict(clean, content_delta=1)
    assert not C.voice_dominates_neutral(voice_better, neutral, added)
    # more conspicuous authorial presence -> rejected even though a soft dim rose
    louder = dict(clean, conspicuousness_delta=0.3)
    assert not C.voice_dominates_neutral(voice_better, neutral, louder)
    # a voice that only reshuffles (no material soft gain) -> retain neutral
    flat = _ev(prose_transparency=0.5, authorial_fit=0.51)
    assert not C.voice_dominates_neutral(flat, neutral, clean)


def test_accept_voice_falls_back_to_neutral_when_not_dominating():
    neutral = _ev(authorial_fit=0.6)
    voice = _ev(authorial_fit=0.6)  # identical -> no gain
    d = C.accept_candidate(voice, incumbent=neutral, is_voice=True, neutral=neutral,
                           prohibitions={"content_delta": 0})
    assert d["accept"] is False and "neutral" in d["reason"]


# --- the disagreement matrix -------------------------------------------------
def test_disagreement_matrix_routes_to_earliest_layer():
    assert C.classify_disagreement(
        {"fidelity": True, "cold_reader": False})["owning_layer"] == "narrative"
    assert C.classify_disagreement(
        {"prose": True, "voice": False})["owning_layer"] == "voice"
    assert C.classify_disagreement(
        {"voice": True, "prose": False})["owning_layer"] == "weld-voice"


def test_author_rejection_is_never_overruled():
    v = {"fidelity": True, "cold_reader": True, "prose": True, "voice": True,
         "structure": True, "repeated_content": True, "author": False}
    d = C.classify_disagreement(v)
    assert d["owning_layer"] == "target" and d["overruleable"] is False


# --- the stop rule (convergence vs stagnation) ------------------------------
def test_stop_rule_continues_on_hard_fail_and_on_dominator():
    assert C.should_continue({"hard_failing": True})["continue"] is True
    assert C.should_continue(
        {"hard_failing": False, "bounded_dominator": True})["continue"] is True


def test_stop_rule_provisional_stop_in_acceptable_region_but_author_bar_open():
    s = {"hard_failing": False, "bounded_dominator": False, "systemic_failure": False,
         "representations_fixed": True, "dirty_contracted": True, "round": 1}
    r = C.should_continue(s)
    assert r["continue"] is False and r["provisional_stop"] is True and r["final"] is False


def test_stop_rule_final_only_on_author_acceptance():
    r = C.should_continue({"author_accepted": True})
    assert r["continue"] is False and r["final"] is True


def test_stop_rule_budget_backstop_is_provisional_not_final():
    s = {"hard_failing": False, "bounded_dominator": False, "systemic_failure": True,
         "representations_fixed": False, "dirty_contracted": False, "round": 4, "budget": 4}
    r = C.should_continue(s)
    assert r["continue"] is False and r["final"] is False and "budget" in r["reason"]


# --- frozen runs (no moving target) -----------------------------------------
def test_run_fingerprint_changes_start_a_new_run():
    a = {"voice_profile": "v1", "judge_panel": "p1", "renderer": "r1"}
    b = dict(a, voice_profile="v2")
    assert C.same_run(a, dict(a))
    assert not C.same_run(a, b)


# --- the bridge: a live panel -> contract state -> stop ----------------------
def _panel(**labels):
    """labels: label -> (clean, n_flags)."""
    return [{"label": lbl, "clean": cl, "flags": [{"issue": "x"}] * nf}
            for lbl, (cl, nf) in labels.items()]


def test_evaluate_round_continues_on_meta_leak():
    panel = _panel(meta_leak=(False, 2), voice=(True, 0), closure=(True, 0),
                   caption=(True, 0), claims=(True, 0), calc=(True, 0))
    r = C.evaluate_round(panel)
    assert r["hard_failing"] is True
    assert r["stop"]["continue"] is True and "hard gate" in r["stop"]["reason"]


def test_evaluate_round_provisional_stop_when_clean():
    panel = _panel(meta_leak=(True, 0), voice=(True, 0), closure=(True, 0),
                   caption=(True, 0), claims=(True, 0), calc=(True, 0))
    r = C.evaluate_round(panel, round=1)
    assert r["hard_failing"] is False
    assert r["stop"]["continue"] is False and r["stop"]["provisional_stop"] is True
    assert r["stop"]["final"] is False   # the author bar is still open


def test_evaluate_round_continues_on_soft_flags_without_hard_fail():
    panel = _panel(meta_leak=(True, 0), voice=(False, 2), closure=(True, 0),
                   caption=(True, 0), claims=(True, 0), calc=(True, 0))
    r = C.evaluate_round(panel, round=1)
    assert r["hard_failing"] is False and r["n_flags"] == 2
    assert r["stop"]["continue"] is True   # flags remain -> dirty not contracted


# --- a candidate-lock reader that RAN and CRASHED blocks its HARD dim --------
def test_hard_reader_crash_blocks_hard_dim():
    base = _panel(meta_leak=(True, 0), caption=(True, 0), claims=(True, 0),
                  voice=(True, 0), closure=(True, 0), calc=(True, 0))
    crashed = base + [{"label": lbl, "failed": True}
                      for lbl in ("referee", "apparatus", "visual", "figure_reader")]
    r = C.evaluate_round(crashed, round=1)
    hard = r["contract"]["hard"]
    assert hard["technical_support"] is False   # referee/apparatus crashed
    assert hard["artefact_integrity"] is False  # visual crashed
    assert hard["no_meta_leak"] is False        # figure_reader crashed
    assert r["hard_failing"] is True


def test_hard_reader_absent_leaves_dim_lenient():
    # the same readers simply silent (normal fixer round) do not block
    panel = _panel(meta_leak=(True, 0), caption=(True, 0), claims=(True, 0),
                   voice=(True, 0), closure=(True, 0), calc=(True, 0))
    r = C.evaluate_round(panel, round=1)
    hard = r["contract"]["hard"]
    assert hard["technical_support"] is True
    assert hard["artefact_integrity"] is True
    assert hard["no_meta_leak"] is True
    assert r["hard_failing"] is False
