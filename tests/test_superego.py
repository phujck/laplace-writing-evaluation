"""Scoped tests for src/laplace/engine/superego.py — the standing judge organ and its door.

Fixture-driven, tmp_path style: each test writes a fake repo tree (a proxy verdict
ledger, a promise ledger, a surface yaml, a corpus friction ledger) and exercises the
organ against it. Proven: the write door validates the verdict spine and refuses bad
station/verdict/severity; the principal-questions spine is required and the overall
verdict derives from its answers; the actor guard refuses judge == builder on a
casefold comparison and carries the law in its message; the ledger is append-only and
reads newest first; assemble_packet is deterministic, carries principal_questions, and
never exceeds its caps; the taste channel surfaces a planted ruling refs-only and
matches on word boundaries; the knowledge channel surfaces a planted clause with its
bar; derive_principal_questions pulls a surface purpose and a goal node; an unknown
station raises.
"""
import json
from pathlib import Path

import pytest

from laplace.engine import superego


# ----------------------------------------------------------------- fixtures
def _write_proxy_ledger(root: Path, rows: list[dict]) -> None:
    (root / "proxy_verdicts.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _write_promises(root: Path, rows: list[dict]) -> None:
    (root / "contract").mkdir(parents=True, exist_ok=True)
    (root / "contract" / "promises.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _write_surface(root: Path, name: str, data: dict) -> None:
    import yaml
    d = root / "contract" / "surfaces"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(yaml.safe_dump(data), encoding="utf-8")


def _write_corpus(root: Path, name: str, rows: list[dict]) -> None:
    d = root / "corpus_friction"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _good_verdict(**over) -> dict:
    rec = {
        "station": "wave-close",
        "claim": "the growth ladder renders on every project card",
        "verdict": "STANDS",
        "judge": "judge-instance-b",
        "builder": "builder-instance-a",
        # a partial row satisfies both directions of the derivation law (a STANDS
        # forbids served=no; a REFUTED forbids all-served=yes) so the default fixture
        # is legal whichever verdict a test overrides it with.
        "questions": [{
            "question": "does the growth ladder render on every project card?",
            "answer": "it renders on most cards; one card still clips the top rung",
            "served": "partial"}],
        "defects": [{"severity": "note", "what": "a cosmetic label", "evidence": "card.mjs:12"}],
        "refs": ["contract/surfaces/conceptric.yaml"],
    }
    rec.update(over)
    return rec


# ----------------------------------------------------------------- (1) shape validation
def test_bank_verdict_validates_shape(tmp_path):
    stored = superego.bank_verdict(tmp_path, _good_verdict())
    assert stored["verdict"] == "STANDS"
    assert stored["id"].startswith("SEV-")
    assert "ts" in stored
    assert stored["questions"][0]["served"] == "partial"    # questions kept verbatim

    with pytest.raises(ValueError):
        superego.bank_verdict(tmp_path, _good_verdict(station="not-a-station"))
    with pytest.raises(ValueError):
        superego.bank_verdict(tmp_path, _good_verdict(verdict="MAYBE"))
    with pytest.raises(ValueError):
        superego.bank_verdict(tmp_path, _good_verdict(claim="  "))
    with pytest.raises(ValueError):
        superego.bank_verdict(
            tmp_path,
            _good_verdict(defects=[{"severity": "catastrophic", "what": "x", "evidence": "y"}]))
    with pytest.raises(ValueError):
        superego.bank_verdict(tmp_path, _good_verdict(judge=""))
    with pytest.raises(ValueError):
        superego.bank_verdict(tmp_path, _good_verdict(refs="not-a-list"))


# ----------------------------------------------------------------- (1b) questions spine
def test_questions_field_required_and_shaped(tmp_path):
    # missing / empty questions is refused
    with pytest.raises(ValueError):
        superego.bank_verdict(tmp_path, _good_verdict(questions=[]))
    rec = _good_verdict()
    del rec["questions"]
    with pytest.raises(ValueError):
        superego.bank_verdict(tmp_path, rec)

    # a row missing its answer prose is refused
    with pytest.raises(ValueError):
        superego.bank_verdict(tmp_path, _good_verdict(
            questions=[{"question": "did it serve?", "served": "yes"}]))
    # a blank answer is refused
    with pytest.raises(ValueError):
        superego.bank_verdict(tmp_path, _good_verdict(
            questions=[{"question": "did it serve?", "answer": "   ", "served": "yes"}]))
    # a blank question is refused
    with pytest.raises(ValueError):
        superego.bank_verdict(tmp_path, _good_verdict(
            questions=[{"question": "  ", "answer": "yes it did", "served": "yes"}]))
    # an unknown served value is refused
    with pytest.raises(ValueError) as exc:
        superego.bank_verdict(tmp_path, _good_verdict(
            questions=[{"question": "did it serve?", "answer": "yes", "served": "sortof"}]))
    assert "served" in str(exc.value)


# ----------------------------------------------------------------- (1c) the derivation law
def test_derivation_law_both_directions(tmp_path):
    # STANDS may not carry a served=no answer
    with pytest.raises(ValueError) as exc_stands:
        superego.bank_verdict(tmp_path, _good_verdict(
            verdict="STANDS",
            questions=[{"question": "did it serve?", "answer": "no, it clips", "served": "no"}]))
    assert "derives from the principal questions" in str(exc_stands.value)

    # REFUTED may not have every answer served=yes
    with pytest.raises(ValueError) as exc_ref:
        superego.bank_verdict(tmp_path, _good_verdict(
            verdict="REFUTED",
            questions=[{"question": "did it serve?", "answer": "yes fully", "served": "yes"}]))
    assert "derives from the principal questions" in str(exc_ref.value)

    # the legal pairings bank cleanly: STANDS with all-yes, REFUTED with a no
    ok_stands = superego.bank_verdict(tmp_path, _good_verdict(
        verdict="STANDS",
        questions=[{"question": "did it serve?", "answer": "yes fully", "served": "yes"}]))
    assert ok_stands["verdict"] == "STANDS"
    ok_ref = superego.bank_verdict(tmp_path, _good_verdict(
        verdict="REFUTED",
        questions=[{"question": "did it serve?", "answer": "no, a rung clips", "served": "no"}]))
    assert ok_ref["verdict"] == "REFUTED"


# ----------------------------------------------------------------- (2) the actor guard
def test_actor_guard_refuses_self_certification(tmp_path):
    with pytest.raises(ValueError) as exc:
        superego.bank_verdict(
            tmp_path, _good_verdict(judge="same-instance", builder="same-instance"))
    # the refusal quotes the law it enforces
    assert "production never self-certifies" in str(exc.value)


def test_actor_guard_casefold_and_whitespace(tmp_path):
    # casing games cannot dodge the guard: 'Builder-A' is 'builder-a'
    with pytest.raises(ValueError) as exc:
        superego.bank_verdict(
            tmp_path, _good_verdict(judge="Builder-A", builder="builder-a"))
    assert "production never self-certifies" in str(exc.value)
    # trailing whitespace cannot dodge it either
    with pytest.raises(ValueError):
        superego.bank_verdict(
            tmp_path, _good_verdict(judge="  reviewer ", builder="reviewer"))


def test_actor_guard_unicode_games(tmp_path):
    # the v2 refutation's three demonstrated dodges, all closed by _actor_key:
    # a zero-width space inside the judge name (format character, dropped)
    with pytest.raises(ValueError):
        superego.bank_verdict(
            tmp_path, _good_verdict(judge="rev\u200biewer", builder="reviewer"))
    # a full-width letter (NFKC collapses it to ascii)
    with pytest.raises(ValueError):
        superego.bank_verdict(
            tmp_path, _good_verdict(judge="\uff42uilder", builder="builder"))
    # combining-vs-precomposed accents (NFKC composes them equal)
    with pytest.raises(ValueError):
        superego.bank_verdict(
            tmp_path, _good_verdict(judge="cafe\u0301", builder="caf\u00e9"))


def test_stands_cannot_carry_a_fatal_defect(tmp_path):
    # severity coherence: fatal is refutation-grade by the module's own vocabulary,
    # so a STANDS carrying one is refused as a self-contradictory record
    with pytest.raises(ValueError) as exc:
        superego.bank_verdict(tmp_path, _good_verdict(
            defects=[{"severity": "fatal", "what": "x", "evidence": "y"}]))
    assert "refutation-grade" in str(exc.value)
    # the same defect under a REFUTED verdict banks cleanly
    rec = superego.bank_verdict(tmp_path, _good_verdict(
        verdict="REFUTED",
        questions=[{"question": "served?", "answer": "no, broken", "served": "no"}],
        defects=[{"severity": "fatal", "what": "x", "evidence": "y"}]))
    assert rec["verdict"] == "REFUTED"


# ----------------------------------------------------------------- (3) append-only, newest first
def test_ledger_is_append_only_newest_first(tmp_path):
    first = superego.bank_verdict(
        tmp_path, _good_verdict(claim="first claim", verdict="REFUTED",
                                questions=[{"question": "served?", "answer": "no",
                                            "served": "no"}]))
    second = superego.bank_verdict(
        tmp_path, _good_verdict(claim="second claim", verdict="STANDS"))

    ledger = superego._ledger_path(tmp_path)
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2                                   # both present, nothing overwritten
    recs = [json.loads(x) for x in lines]
    assert recs[0]["claim"] == "first claim"                # append order on disk
    assert recs[1]["claim"] == "second claim"

    got = superego.verdicts_for(tmp_path)
    assert len(got) == 2
    # newest first by ts; second was banked after first
    assert got[0]["ts"] >= got[1]["ts"]
    assert {r["claim"] for r in got} == {"first claim", "second claim"}

    only_refuted = superego.verdicts_for(tmp_path, claim_substr="first")
    assert len(only_refuted) == 1 and only_refuted[0]["verdict"] == "REFUTED"
    assert first["id"].startswith("SEV-") and second["id"].startswith("SEV-")


# ----------------------------------------------------------------- (4) determinism + caps
def test_assemble_packet_deterministic_and_capped(tmp_path):
    # many matching rows so the caps actually bind
    proxy = []
    for i in range(12):
        proxy.append({
            "id": f"PV-{i:02d}", "date": f"2026-07-{i + 1:02d}",
            "question": "does the superego hold the growth ladder whole",
            "ruling": "yes — the ladder is the growth stance " + ("x" * 800)})
    _write_proxy_ledger(tmp_path, proxy)
    _write_promises(tmp_path, [
        {"id": f"PRM-{i}", "date": f"2026-06-{i + 1:02d}",
         "ask": "the superego holds the growth ladder as one thing " + ("y" * 800)}
        for i in range(6)])
    for j in range(3):
        _write_surface(tmp_path, f"s{j}.yaml", {
            "surface": f"s{j}",
            "structural": [
                {"clause": f"growth-ladder-clause-{j}-{k}", "bar": "mechanical",
                 "red": "W-growth", "note": "the growth ladder renders"}
                for k in range(5)],
            "counts": {"law": "growth-chip-equals-filter"},
        })

    p1 = superego.assemble_packet(tmp_path, "the growth ladder", "wave-close", "builder-a")
    p2 = superego.assemble_packet(tmp_path, "the growth ladder", "wave-close", "builder-a")
    assert p1 == p2                                          # deterministic, token-free

    assert p1["kind"] == "superego-packet"
    assert "principal_questions" in p1                       # the questions slot rides
    assert len(p1["frame"]["taste"]) <= 6
    assert len(p1["frame"]["knowledge"]) <= 8
    for entry in p1["frame"]["taste"]:
        assert len(entry["quote"]) <= 400                   # bounded quote


# ----------------------------------------------------------------- (4b) explicit questions ride
def test_assemble_packet_carries_explicit_questions(tmp_path):
    packet = superego.assemble_packet(
        tmp_path, "some claim", "close", "builder-a",
        principal_questions=["does it serve the reader?", "does it serve the reader?",
                             "is it fast?"])
    # explicit questions ride first, deduplicated, order preserved; a close-class
    # station also carries the standing essential-path question (his ruling
    # 2026-07-22 - a standing organ, never a session-ephemeral check).
    assert packet["principal_questions"] == [
        "does it serve the reader?", "is it fast?", superego.ESSENTIAL_PATH_QUESTION]


# ----------------------------------------------------------------- (4c) derive from a tree
def test_derive_principal_questions_from_surface_and_goal(tmp_path):
    _write_surface(tmp_path, "widget.yaml", {
        "surface": "widget",
        "purpose": "one substrate seen at rising altitudes — the read-only instrument",
    })
    _write_corpus(tmp_path, "eigenengine", [
        {"id": "RW-1", "kind": "add-node", "node": "n-goal", "node_kind": "goal",
         "essence": "the engine reconstructs a self from a cold repo in seconds"},
        {"id": "RW-2", "kind": "add-node", "node": "n-step", "node_kind": "derivation-step",
         "essence": "a helper lemma nobody should surface as a principal question"},
        {"id": "RW-3", "kind": "add-node", "node": "n-retagged",
         "essence": "the retagged node promoted to goal by a later set-kind"},
        {"id": "RW-4", "kind": "set-kind", "node": "n-retagged", "value": "goal"},
    ])

    qs = superego.derive_principal_questions(tmp_path, corpus="eigenengine", surface="widget")
    joined = " || ".join(qs)
    assert "one substrate seen at rising altitudes" in joined     # surface purpose pulled
    assert "reconstructs a self from a cold repo" in joined       # add-node goal essence
    assert "retagged node promoted to goal" in joined             # set-kind goal essence
    assert "helper lemma nobody should surface" not in joined     # non-goal not pulled
    assert len(qs) <= 6                                           # bounded

    # missing surface / corpus degrade to empty, never crash
    assert superego.derive_principal_questions(tmp_path) == []
    assert superego.derive_principal_questions(tmp_path, surface="no-such") == []


# ----------------------------------------------------------------- (5) taste channel, refs-only
def test_taste_channel_surfaces_planted_ruling_refs_only(tmp_path):
    _write_proxy_ledger(tmp_path, [
        {"id": "PV-plant", "date": "2026-07-21",
         "question": "should the parallax navigation be respined",
         "ruling": "yes, respine the parallax section into a ladder"},
        {"id": "PV-noise", "date": "2026-07-20",
         "question": "an unrelated matter about bibliography keys",
         "ruling": "mint the keys British"}])
    _write_promises(tmp_path, [
        {"id": "PRM-plant", "date": "2026-07-22",
         "ask": "the parallax boundary must never drift from its seed"}])

    packet = superego.assemble_packet(
        tmp_path, "how should the parallax section be handled",
        "candidate-lock", "builder-a", keywords=["parallax"])
    taste = packet["frame"]["taste"]
    refs = {e["ref"] for e in taste}
    assert "PV-plant" in refs                                # planted ruling surfaced
    assert "PRM-plant" in refs                               # planted promise ask surfaced
    assert "PV-noise" not in refs                            # non-matching row not pulled

    # refs-only discipline: the only free text is the bounded quote; the rest are refs
    for e in taste:
        assert set(e.keys()) == {"source", "ref", "quote", "date"}
        assert len(e["quote"]) <= 400


# ----------------------------------------------------------------- (5b) token-boundary matching
def test_matches_on_word_boundary_not_substring(tmp_path):
    # a ruling that contains 'threshold' but never the word 'hold'
    _write_proxy_ledger(tmp_path, [
        {"id": "PV-threshold", "date": "2026-07-21",
         "question": "is the threshold respected",
         "ruling": "the threshold policy is set high and stable"}])

    packet = superego.assemble_packet(
        tmp_path, "the gate must hold", "close", "builder-a", keywords=["hold"])
    refs = {e["ref"] for e in packet["frame"]["taste"]}
    # 'hold' must not match 'threshold' — the boundary-anchored matcher excludes it
    assert "PV-threshold" not in refs

    # sanity: the same keyword DOES surface a row that uses the word 'hold'
    _write_proxy_ledger(tmp_path, [
        {"id": "PV-hold", "date": "2026-07-21",
         "question": "does the gate hold",
         "ruling": "yes, the gate holds and the invariant is kept"}])
    packet2 = superego.assemble_packet(
        tmp_path, "the gate must hold", "close", "builder-a", keywords=["hold"])
    refs2 = {e["ref"] for e in packet2["frame"]["taste"]}
    assert "PV-hold" in refs2


# ----------------------------------------------------------------- (6) knowledge channel + bar
def test_knowledge_channel_surfaces_clause_with_bar(tmp_path):
    _write_surface(tmp_path, "conceptric.yaml", {
        "surface": "conceptric",
        "structural": [
            {"clause": "goal-versioned-regoal-loop", "bar": "author", "red": "W-growth",
             "note": "the goal node is versioned by supersede through the one ledger"},
            {"clause": "unrelated-axis-thing", "bar": "mechanical",
             "note": "something about edges and tokens"}],
        "counts": {"law": "chip-equals-filter"},
    })
    packet = superego.assemble_packet(
        tmp_path, "does the goal versioned regoal loop hold",
        "close", "builder-a", keywords=["regoal", "versioned"])
    knowledge = packet["frame"]["knowledge"]
    planted = [e for e in knowledge if e["clause"] == "goal-versioned-regoal-loop"]
    assert len(planted) == 1
    assert planted[0]["bar"] == "author"                    # bar field carried
    assert planted[0]["red"] == "W-growth"
    assert planted[0]["source"] == "conceptric.yaml"


# ----------------------------------------------------------------- (7) unknown station raises
def test_unknown_station_raises(tmp_path):
    with pytest.raises(ValueError):
        superego.assemble_packet(tmp_path, "some claim", "not-a-station", "builder-a")
    with pytest.raises(ValueError):
        superego.assemble_packet(tmp_path, "", "close", "builder-a")       # empty claim
    with pytest.raises(ValueError):
        superego.assemble_packet(tmp_path, "some claim", "close", "  ")    # empty builder


def test_superseded_goal_asks_no_stale_question(tmp_path):
    # the G1 judge's must-fix: goal-v2 supersedes goal-v1, and the question set
    # follows the substrate - only the live goal is asked about
    _write_corpus(tmp_path, "proj", [
        {"kind": "add-node", "node": "goal:v1", "node_kind": "goal",
         "essence": "the v1 goal"},
        {"kind": "add-node", "node": "goal:v2", "node_kind": "goal",
         "essence": "the v2 goal", "supersedes": "goal:v1"},
    ])
    qs = superego.derive_principal_questions(tmp_path, corpus="proj")
    assert any("the v2 goal" in q for q in qs)
    assert not any("the v1 goal" in q for q in qs)


# ------------------------------------------- (9) the judge identity + staleness
# WO-20260817-verdict-versioning. Proven both ways: a verdict banked now carries WHO
# judged it, in what version, on which artefacts, fingerprinted; and a verdict banked
# BEFORE the block existed (a bare `judge` string) is still read, still classed, and
# never reads fresh.
def test_bank_verdict_stamps_the_judge_identity(tmp_path):
    stored = superego.bank_verdict(tmp_path, _good_verdict(
        judge_model="opus", judge_version="panel-v3",
        judge_artifacts={"metric_M": "abc123"}))
    ident = stored["judge_identity"]
    assert ident["schema"] == superego.JUDGE_IDENTITY_SCHEMA
    assert ident["name"] == "judge-instance-b"          # forced to the record's judge
    assert ident["judge_class"] == "instance"
    assert ident["model"] == "opus" and ident["version"] == "panel-v3"
    assert ident["artifacts"] == {"metric_M": "abc123"}
    assert ident["evaluator_version"] == superego.EVALUATOR_VERSION
    assert ident["complete"] is True and ident["unstamped"] == []
    assert len(ident["fingerprint"]) == 16
    # and it survives the round trip through the ledger
    read_back = superego.verdicts_for(tmp_path)[0]
    assert read_back["judge_identity"]["fingerprint"] == ident["fingerprint"]


def test_unstamped_judge_lands_incomplete_not_green(tmp_path):
    stored = superego.bank_verdict(tmp_path, _good_verdict())   # no model, no version
    ident = stored["judge_identity"]
    assert ident["complete"] is False
    assert set(ident["unstamped"]) == {"model", "version"}
    current = superego.judge_identity("judge-instance-b", model="opus", version="panel-v3")
    report = superego.verdict_staleness(stored, current)
    assert report["state"] == "unknown"                  # not fresh, and not a false stale
    assert "incomplete" in report["reason"]


def test_judge_change_makes_dependent_verdicts_stale(tmp_path):
    # the lived specimen: the judge leans on the distilled metric M, M is retrained,
    # and every verdict resting on the old M must stop reading as current.
    old = superego.judge_identity("judge-instance-b", model="opus", version="panel-v3",
                                  artifacts={"metric_M": "auc-0.9317"})
    stored = superego.bank_verdict(tmp_path, _good_verdict(
        judge_model="opus", judge_version="panel-v3",
        judge_artifacts={"metric_M": "auc-0.9317"}))
    assert superego.verdict_staleness(stored, old)["state"] == "fresh"

    retrained = superego.judge_identity("judge-instance-b", model="opus",
                                        version="panel-v3",
                                        artifacts={"metric_M": "auc-0.9908"})
    report = superego.verdict_staleness(stored, retrained)
    assert report["state"] == "stale"
    assert report["banked_fingerprint"] != report["current_fingerprint"]
    assert "re-derive" in report["reason"]
    # a version bump on the judge itself does the same
    rev = superego.judge_identity("judge-instance-b", model="opus", version="panel-v4",
                                  artifacts={"metric_M": "auc-0.9317"})
    assert superego.verdict_staleness(stored, rev)["state"] == "stale"

    # the sweep names it, and skips the fresh reading of the same row
    sweep = superego.stale_verdicts(tmp_path, retrained)
    assert [r["id"] for r in sweep] == [stored["id"]]
    assert superego.stale_verdicts(tmp_path, old) == []


def test_mechanical_floor_never_goes_stale(tmp_path):
    # the evaluator-independent class: unit tests, walker floors, the register audit.
    stored = superego.bank_verdict(tmp_path, _good_verdict(
        judge="the-unit-suite", judge_class="mechanical", judge_version="pytest-8"))
    assert stored["judge_identity"]["judge_class"] == "mechanical"
    assert stored["judge_identity"]["complete"] is True     # no model to change under it
    other = superego.judge_identity("a-wholly-different-judge", model="opus",
                                    version="panel-v9")
    assert superego.verdict_staleness(stored, other)["state"] == "evaluator-independent"
    assert superego.stale_verdicts(tmp_path, other) == []

    with pytest.raises(ValueError):
        superego.bank_verdict(tmp_path, _good_verdict(judge_class="oracular"))
    with pytest.raises(ValueError):
        superego.bank_verdict(tmp_path, _good_verdict(judge_artifacts="not-a-dict"))


def test_reader_tolerates_rows_banked_before_identity_existed(tmp_path):
    # a pre-WO row, written straight to the ledger with a bare judge string and no
    # identity block at all — exactly what contract/judged_verdicts.jsonl holds today.
    ledger = superego._ledger_path(tmp_path)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    legacy = _good_verdict(claim="an old claim")
    legacy.update({"id": "SEV-20260101T000000Z", "ts": "2026-01-01T00:00:00+00:00"})
    ledger.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

    rows = superego.verdicts_for(tmp_path)
    assert len(rows) == 1 and "judge_identity" not in rows[0]   # the row is untouched
    ident = superego.judge_identity_of(rows[0])
    assert ident["judge_class"] == "legacy"
    assert ident["name"] == "judge-instance-b"                  # the name is preserved
    assert ident["complete"] is False
    current = superego.judge_identity("judge-instance-b", model="opus", version="panel-v3")
    report = superego.verdict_staleness(rows[0], current)
    assert report["state"] == "unknown"                         # never fresh
    assert [r["id"] for r in superego.stale_verdicts(tmp_path, current)] \
        == ["SEV-20260101T000000Z"]
    assert superego.stale_verdicts(tmp_path, current, include_unknown=False) == []

    # a row with no judge field at all still reads, rather than raising
    assert superego.judge_identity_of({})["name"] == "unnamed-judge"
    # and with no current judge supplied, freshness is simply not decidable
    assert superego.verdict_staleness(rows[0])["state"] == "unknown"
