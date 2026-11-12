"""F25 automated - the hold-out banked in-repo, scored at wake, blind where it must be."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from laplace.engine import holdout

ROOT = Path(__file__).resolve().parents[1]


def _bank_fixture(root: Path):
    return holdout.bank(
        root, "test-session",
        mechanical=[
            {"id": "m-pass", "cmd": "true", "expect": "rc0"},
            {"id": "m-fail", "cmd": "false", "expect": "rc0"},
            {"id": "m-substr", "cmd": "echo the-needle", "expect": "the-needle"},
        ],
        behavioral=[{"id": "b1", "claim": "SECRET-CLAIM next-me will forget the delta"}],
    )


def test_bank_score_mechanical(tmp_path):
    _bank_fixture(tmp_path)
    scores = holdout.score_mechanical(tmp_path)
    verdicts = {r["id"]: r["verdict"] for r in scores["mechanical"]}
    assert verdicts == {"m-pass": "PASS", "m-fail": "FAIL", "m-substr": "PASS"}
    assert scores["behavioral_pending"] == ["b1"]
    assert "SECRET-CLAIM" not in json.dumps(scores)  # ids only - the blindness law


def test_archive_folds_and_clears(tmp_path):
    _bank_fixture(tmp_path)
    out = holdout.archive(tmp_path, [{"id": "b1", "verdict": "PASS", "note": "held"}])
    assert out is not None and out.is_file()
    assert not (tmp_path / holdout.PENDING).is_file()
    folded = json.loads(out.read_text(encoding="utf-8"))
    assert folded["behavioral_scores"][0]["verdict"] == "PASS"
    assert {r["id"] for r in folded["mechanical_scores"]} == {"m-pass", "m-fail", "m-substr"}


def test_no_pending_is_quiet(tmp_path):
    assert holdout.score_mechanical(tmp_path) is None
    assert holdout.archive(tmp_path, []) is None


def test_wake_cli_scores_holdout_blind():
    """The real wake surfaces mechanical verdicts + behavioral IDS ONLY."""
    pending = ROOT / holdout.PENDING
    existed = pending.is_file()
    original = pending.read_text(encoding="utf-8") if existed else None
    # AP-13: this test drives the REAL repo, so it must restore EVERYTHING it moves. Since
    # WO-20260817-holdout-scores-deposit a scoring wake also banks holdout/LAST_SCORE.json —
    # left behind, this test's fixture scorecard would be what the close's holdout check reads.
    card = ROOT / holdout.LAST_SCORE
    card_existed = card.is_file()
    card_original = card.read_text(encoding="utf-8") if card_existed else None
    try:
        holdout.bank(ROOT, "cli-test",
                     mechanical=[{"id": "cli-m", "cmd": "true", "expect": "rc0"}],
                     behavioral=[{"id": "cli-b", "claim": "SECRET-CLI-CLAIM"}])
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "wake.py"), "--grade", "0"],
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0
        payload = json.loads(r.stdout)
        hv = {x["id"]: x["verdict"] for x in payload["holdout"]["mechanical"]}
        assert hv == {"cli-m": "PASS"}
        assert payload["holdout"]["behavioral_pending"] == ["cli-b"]
        assert "SECRET-CLI-CLAIM" not in r.stdout
    finally:
        if existed and original is not None:
            pending.write_text(original, encoding="utf-8")
        else:
            pending.unlink(missing_ok=True)
        if card_existed and card_original is not None:
            card.write_text(card_original, encoding="utf-8")
        else:
            card.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# THE THREAD PROBES - the rehearsal made quantitative (2026-08-19, the
# design-thread miss). The router is stubbed here on purpose: these tests are
# about the VERDICT LAW (expected-red vs CLEARED vs REGRESSION), the shared
# wall, and the honest fallback. That the probes fire the REAL router is the
# meter-faithfulness law and is exercised live at the close (sewup: threads).
# --------------------------------------------------------------------------- #

def _probe(pid, must_reach, expected, query="q"):
    return {"id": pid, "query": query, "must_reach": must_reach, "top_k": 3,
            "expected_now": expected}


def _stub_router(monkeypatch, top_files, members=("ATLAS.md", "other.md"), route_none=False):
    """One stubbed network + router. `top_files` is what route() returns."""
    net = {"nodes": {"n": {"members": list(members)}}, "root": "n"}
    monkeypatch.setattr("laplace.engine.conceptric.load_network", lambda root: net)

    def fake_route(root, network, goal, limit=10):
        if route_none:
            return None
        return {"files": [{"file": f} for f in top_files[:limit]]}

    monkeypatch.setattr("laplace.representation.embed_router.route", fake_route)


def test_thread_verdict_law(tmp_path, monkeypatch):
    """HIT/MISS x expected pass/fail = the four statuses, and only REGRESSION is a defect."""
    _stub_router(monkeypatch, ["ATLAS.md", "noise.md"])
    holdout.bank_probes(tmp_path, "t", [
        _probe("hit-expected", ["ATLAS.md"], "pass"),      # reachable, banked reachable
        _probe("red-expected", ["ABSENT.md"], "fail"),     # known red, cure pending
        _probe("cleared", ["ATLAS.md"], "fail"),           # red that now hits: improvement
        _probe("regressed", ["other.md"], "pass"),         # HAD it, lost it
    ])
    block = holdout.score_threads(tmp_path, budget_s=None)
    status = {r["id"]: (r["verdict"], r["status"]) for r in block["probes"]}
    assert status == {"hit-expected": ("HIT", "as-expected"),
                      "red-expected": ("MISS", "expected-red"),
                      "cleared": ("HIT", "CLEARED"),
                      "regressed": ("MISS", "REGRESSION")}
    assert block["summary"] == {"total": 4, "scored": 4, "hit": 2, "red": 2, "unrun": [],
                                "cleared": ["cleared"], "regressions": ["regressed"]}
    assert "REGRESSION" in block["headline"] and "re-stamp" in block["headline"]


def test_thread_absent_target_names_the_right_cure(tmp_path, monkeypatch):
    """A must_reach the CORPUS does not contain is an ingest miss, not a ranking miss - the
    meter must say which, or the close chases the wrong cure."""
    _stub_router(monkeypatch, ["noise.md"], members=("ATLAS.md",))
    holdout.bank_probes(tmp_path, "t", [
        _probe("not-ingested", ["NEVER_INGESTED.md"], "fail"),
        _probe("unreached", ["ATLAS.md"], "fail"),
    ])
    rows = {r["id"]: r["detail"] for r in holdout.score_threads(tmp_path, budget_s=None)["probes"]}
    assert "ABSENT from the live network" in rows["not-ingested"]
    assert "present in the corpus, unreached" in rows["unreached"]


def test_thread_budget_refuses_at_the_door_and_falls_back(tmp_path, monkeypatch):
    """A spent wall cannot pay for live routing: every probe is BUDGET (never a silent drop,
    never a PASS), and the block reports the LAST CLOSE'S scores instead of nothing."""
    _stub_router(monkeypatch, ["ATLAS.md"])
    holdout.bank_probes(tmp_path, "t", [_probe("p1", ["ATLAS.md"], "fail")])
    holdout.score_threads(tmp_path, budget_s=None, record=True)     # a real close's scores
    block = holdout.score_threads(tmp_path, wall=holdout.Wall(0.0))
    assert [r["verdict"] for r in block["probes"]] == ["BUDGET"]
    assert block["live"] is False
    assert block["summary"]["unrun"] == ["p1"]
    assert "not scored live" in block["headline"]
    assert block["last_close"]["hit"] == 1 and "1/1 threads reached" in block["headline"]
    assert block["delta"] == []          # an unrun probe never "changed"


def test_thread_router_unavailable_is_error_not_pass(tmp_path, monkeypatch):
    """route() -> None (no embedding backend) is an ERROR. An instrument that cannot run is
    not an instrument that passed."""
    _stub_router(monkeypatch, [], route_none=True)
    holdout.bank_probes(tmp_path, "t", [_probe("p1", ["ATLAS.md"], "pass")])
    block = holdout.score_threads(tmp_path, budget_s=None)
    assert block["probes"][0]["verdict"] == "ERROR"
    assert block["live"] is False and block["summary"]["unrun"] == ["p1"]


def test_thread_record_only_on_a_live_run(tmp_path, monkeypatch):
    """record=True stamps last_scored at the close; a budget-clipped wake must never
    overwrite a real close's scores with its own non-run."""
    _stub_router(monkeypatch, ["ATLAS.md"])
    holdout.bank_probes(tmp_path, "t", [_probe("p1", ["ATLAS.md"], "fail")])
    holdout.score_threads(tmp_path, budget_s=None, record=True)
    stamped = holdout.load_probes(tmp_path)["last_scored"]
    assert stamped["by_id"] == {"p1": "HIT"} and stamped["hit"] == 1
    holdout.score_threads(tmp_path, wall=holdout.Wall(0.0), record=True)
    assert holdout.load_probes(tmp_path)["last_scored"] == stamped


def test_thread_delta_reports_the_change_since_the_last_close(tmp_path, monkeypatch):
    _stub_router(monkeypatch, ["ATLAS.md"])
    holdout.bank_probes(tmp_path, "t", [_probe("p1", ["ATLAS.md"], "fail"),
                                        _probe("gone", ["ATLAS.md"], "fail")])
    holdout.score_threads(tmp_path, budget_s=None, record=True)
    holdout.bank_probes(tmp_path, "t", [_probe("p1", ["MOVED.md"], "fail")], replace=False)
    doc = holdout.load_probes(tmp_path)
    doc["probes"] = [p for p in doc["probes"] if p["id"] != "gone"]
    holdout.save_probes(tmp_path, doc)
    block = holdout.score_threads(tmp_path, budget_s=None)
    assert block["delta"] == ["p1: HIT -> MISS", "gone: RETIRED (was HIT)"]


def test_bank_probes_extends_and_dedupes(tmp_path):
    """The standing set ACCUMULATES: a close that mints one probe must never drop the ones
    measuring the older threads (this is why the set is not the pending prediction, which
    archive() unlinks at every close)."""
    holdout.bank_probes(tmp_path, "s1", [_probe("a", ["A.md"], "fail")])
    holdout.bank_probes(tmp_path, "s2", [_probe("b", ["B.md"], "fail"),
                                         _probe("a", ["A.md"], "pass")])
    doc = holdout.load_probes(tmp_path)
    assert [p["id"] for p in doc["probes"]] == ["a", "b"]
    assert doc["probes"][0]["expected_now"] == "pass"          # re-stamped in place
    holdout.bank_probes(tmp_path, "s3", [_probe("c", ["C.md"], "fail")], replace=True)
    assert [p["id"] for p in holdout.load_probes(tmp_path)["probes"]] == ["c"]


def test_thread_probes_survive_archive(tmp_path):
    """The lifecycle reason the standing set is its own file: archive() clears the pending
    prediction at every close and must not take the standing instrument with it."""
    _bank_fixture(tmp_path)
    holdout.bank_probes(tmp_path, "t", [_probe("a", ["A.md"], "fail")])
    holdout.archive(tmp_path, [])
    assert not (tmp_path / holdout.PENDING).is_file()
    assert holdout.load_probes(tmp_path)["probes"][0]["id"] == "a"


def test_one_wall_spans_both_scorecards(tmp_path, monkeypatch):
    """Two scorers each honouring a 5 s budget is a 10 s wake. They share one Wall."""
    _stub_router(monkeypatch, ["ATLAS.md"])
    _bank_fixture(tmp_path)
    holdout.bank_probes(tmp_path, "t", [_probe("p1", ["ATLAS.md"], "fail")])
    wall = holdout.Wall(0.0)
    mech = holdout.score_mechanical(tmp_path, wall=wall)
    threads = holdout.score_threads(tmp_path, wall=wall)
    assert {r["verdict"] for r in mech["mechanical"]} == {"BUDGET"}
    assert {r["verdict"] for r in threads["probes"]} == {"BUDGET"}
    assert mech["budget"]["spent"] and threads["budget"]["spent"]


def test_no_banked_probe_set_is_quiet(tmp_path):
    assert holdout.score_threads(tmp_path) is None


# --- minting: a new DESIGN_/ARMING_ doc mints its own probe ------------------ #


def test_title_terms_strips_the_filing_metadata(tmp_path):
    p = tmp_path / "DESIGN_2026-08-19_the-renormalized-atlas.md"
    p.write_text("# DESIGN 2026-08-19 - The renormalized atlas: the closure-residual loop\n",
                 encoding="utf-8")
    assert holdout.title_terms(p) == "The renormalized atlas: the closure-residual loop"
    assert holdout.probe_id_for(p) == "thread-design-2026-08-19-the-renormalized-atlas"
    bare = tmp_path / "ARMING_2026-08-19_the-pilot-night.md"
    bare.write_text("no heading here\n", encoding="utf-8")
    assert holdout.title_terms(bare) == "the pilot night"


def test_mint_watermark_and_cap(tmp_path, monkeypatch):
    """Only docs at/after the watermark are candidates, the cap bounds one close's mint, and
    the clipped remainder is NAMED rather than dropped."""
    _stub_router(monkeypatch, ["noise.md"])
    for day in ("15", "17", "18", "19"):
        (tmp_path / f"DESIGN_2026-08-{day}_doc-{day}.md").write_text(
            f"# DESIGN 2026-08-{day} - thread {day}\n", encoding="utf-8")
    holdout.bank_probes(tmp_path, "t", [_probe("a", ["A.md"], "fail")])
    doc = holdout.load_probes(tmp_path)
    doc["minted_through"] = "2026-08-17"
    holdout.save_probes(tmp_path, doc)
    r = holdout.mint_from_docs(tmp_path, cap=2)
    assert r["candidates"] == 3 and len(r["minted"]) == 2
    assert r["clipped"] == ["DESIGN_2026-08-19_doc-19.md"]
    assert r["queries"][r["minted"][0]] == "thread 17"
    ids = [p["id"] for p in holdout.load_probes(tmp_path)["probes"]]
    assert ids[0] == "a" and len(ids) == 3          # additive, never a replacement
    # the clipped remainder is CARRIED, not dropped: the next close mints it...
    second = holdout.mint_from_docs(tmp_path, cap=2)
    assert second["minted"] == ["thread-design-2026-08-19-doc-19"]
    # ...and once every doc has its probe, minting is a no-op (dedupe by id, not by date)
    assert holdout.mint_from_docs(tmp_path, cap=2)["candidates"] == 0


def test_mint_stamps_expected_now_from_a_live_route(tmp_path, monkeypatch):
    """A minted probe's expected_now is MEASURED, not assumed: a doc that is reachable today
    is banked as pass, so a later miss is a REGRESSION the close catches."""
    (tmp_path / "DESIGN_2026-08-19_reachable.md").write_text("# DESIGN - reachable\n",
                                                             encoding="utf-8")
    (tmp_path / "DESIGN_2026-08-19_unreachable.md").write_text("# DESIGN - unreachable\n",
                                                               encoding="utf-8")
    _stub_router(monkeypatch, ["DESIGN_2026-08-19_reachable.md"])
    holdout.mint_from_docs(tmp_path, since="2026-08-01")
    minted = {p["id"]: p["expected_now"] for p in holdout.load_probes(tmp_path)["probes"]}
    assert minted["thread-design-2026-08-19-reachable"] == "pass"
    assert minted["thread-design-2026-08-19-unreachable"] == "fail"


def test_a_supplied_network_is_used_and_never_reloaded(tmp_path, monkeypatch):
    """WO-20260821-route-basis-memo C3b: the close scores and then mints, and each half used to
    load its own network - a second full load_network, and (since the router's basis memo holds
    per network OBJECT) a second cold basis. Both now take the caller's network, and neither
    loads when it is given one."""
    loads, seen = {"n": 0}, []
    net = {"nodes": {"n": {"members": ["ATLAS.md"]}}, "root": "n"}
    monkeypatch.setattr("laplace.engine.conceptric.load_network",
                        lambda root: loads.__setitem__("n", loads["n"] + 1) or net)
    monkeypatch.setattr("laplace.representation.embed_router.route",
                        lambda root, network, goal, limit=10:
                        seen.append(network) or {"files": [{"file": "ATLAS.md"}]})

    holdout.bank_probes(tmp_path, "t", [_probe("hit", ["ATLAS.md"], "pass")])
    (tmp_path / "DESIGN_2026-08-19_doc.md").write_text("# DESIGN - a thread\n", encoding="utf-8")
    holdout.score_threads(tmp_path, budget_s=None, net=net)
    holdout.mint_from_docs(tmp_path, since="2026-08-01", net=net)

    assert loads["n"] == 0, "a supplied network must never be reloaded"
    assert len(seen) == 2 and all(n is net for n in seen), "both halves route against the SAME object"


def test_mint_dry_run_writes_nothing(tmp_path, monkeypatch):
    _stub_router(monkeypatch, ["x.md"])
    (tmp_path / "DESIGN_2026-08-19_doc.md").write_text("# DESIGN - a thread\n", encoding="utf-8")
    r = holdout.mint_from_docs(tmp_path, since="2026-08-01", dry_run=True)
    assert r["minted"] == ["thread-design-2026-08-19-doc"]
    assert holdout.load_probes(tmp_path) is None


def test_budget_fallback_keeps_the_expected_red_framing(tmp_path, monkeypatch):
    """The wake's fallback line must distinguish a pending cure from a defect exactly as the
    live line does: "3 red (3 expected)" is a status report; a bare "3 red" is an alarm."""
    _stub_router(monkeypatch, ["ATLAS.md"])
    holdout.bank_probes(tmp_path, "t", [_probe("red-a", ["GONE.md"], "fail"),
                                        _probe("red-b", ["GONE.md"], "fail"),
                                        _probe("lost", ["GONE.md"], "pass")])
    holdout.score_threads(tmp_path, budget_s=None, record=True)
    head = holdout.score_threads(tmp_path, wall=holdout.Wall(0.0))["headline"]
    assert "0/3 threads reached, 3 red (2 expected, the cure is pending)" in head
    assert "REGRESSION at that close: lost" in head


# --- WO-20260817-holdout-scores-deposit: scoring is ONE ACT with its deposit ---

def test_scoring_banks_what_it_scored(tmp_path):
    """The wake used to score the author's verbatim holdout, PRINT the verdicts, and record
    nothing - so the close's holdout check had nothing to read and fell back to comparing file
    mtimes (which can only ever WARN). The scorecard is now deposited."""
    _bank_fixture(tmp_path)
    scores = holdout.score_mechanical(tmp_path)

    dep = tmp_path / holdout.LAST_SCORE
    assert dep.is_file(), "a scoring wake must bank what it scored"
    card = json.loads(dep.read_text(encoding="utf-8"))
    assert card["mechanical"] == scores["mechanical"]
    assert card["banked"] == scores["banked"]
    assert card.get("scored_at")
    assert "SECRET-CLAIM" not in dep.read_text(encoding="utf-8")   # the blindness law holds


def test_archive_clears_the_per_wake_deposit_with_the_pending(tmp_path):
    """The deposit describes the PENDING prediction; once archived, that prediction has a
    permanent SCORED_<ts>.json and the transient card must not linger to be re-read."""
    _bank_fixture(tmp_path)
    holdout.score_mechanical(tmp_path)
    assert (tmp_path / holdout.LAST_SCORE).is_file()

    holdout.archive(tmp_path, [{"id": "b1", "verdict": "PASS", "note": "held"}])

    assert not (tmp_path / holdout.PENDING).is_file()
    assert not (tmp_path / holdout.LAST_SCORE).is_file()


def test_desk_score_verb_refuses_to_archive_without_behavioral_scores(monkeypatch):
    """archive() UNLINKS the pending prediction. The desk's `score` verb used to hardcode
    behavioral_scores=[] and archive unconditionally, settling the author's behavioral claims
    UNREAD. Now the mechanical half always runs; the archive is refused without scores."""
    from laplace.web import desk

    calls = {"archive": 0}
    monkeypatch.setattr(desk, "_REPO_ROOT", ROOT, raising=False)
    monkeypatch.setattr(holdout, "score_mechanical",
                        lambda root, **kw: {"mechanical": [{"id": "m", "verdict": "PASS"}]})

    def _spy_archive(root, behavioral_scores):
        calls["archive"] += 1
        calls["scores"] = behavioral_scores
        return Path(root) / "holdout" / "SCORED_stub.json"

    monkeypatch.setattr(holdout, "archive", _spy_archive)

    refused = desk._dispatch_desk_verb("holdout", "score", {}, "tester")
    assert refused["archived"] is False and refused["still_open"] is True
    assert "behavioral_scores" in refused["refused"]
    assert calls["archive"] == 0, "an empty behavioral set must not clear the pending prediction"
    assert refused["scored"]["mechanical"], "the mechanical scorecard still runs and returns"

    settled = desk._dispatch_desk_verb(
        "holdout", "score", {"behavioral_scores": [{"id": "b1", "verdict": "PASS"}]}, "tester")
    assert settled["archived"] is True
    assert calls["archive"] == 1 and calls["scores"] == [{"id": "b1", "verdict": "PASS"}]
