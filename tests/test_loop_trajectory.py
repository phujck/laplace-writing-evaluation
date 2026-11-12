"""Pure-Python contract tests for the loop-trajectory reader organ — no browser.

The reader (:mod:`laplace.engine.loop_trajectory`) is the durable organ behind the rebuilt
/analytics loop-interrogation surface; the playwright walk drives the paint, these tests
pin the CONTRACT so rerunning the pipeline mints the same payload from the same banked
records (the infrastructure law). Two grains: a synthetic two-round fixture that exercises
the derivative + the door primitive + the census in isolation, and a read of the REAL
banked round 1-2 records so the surface's headline numbers are asserted against disk.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.engine import loop_trajectory as lt

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]


# ═══════════════════════════ synthetic fixture (isolation) ═══════════════════════════
def _fixture(tmp: Path) -> Path:
    (tmp / "evidence").mkdir(parents=True)
    (tmp / "CLAUDE.md").write_text("# Eigen\n")
    rounds = [
        {"round": 1, "date": "2026-07-16", "corpus": "demo",
         "findings": {"mechanical_open": {"total": 60, "classes": {"citation-uncited": 40, "notation": 20}},
                      "reader_new": {"claimed_total": 8, "banked_verbatim": 4}},
         "gate_scores": {"hard_failing": True, "contract_hard": {"technical_support": False}},
         "rulings_drafted": {"count": 6, "by_confidence": {"HIGH": 2}},
         "genuinely_his_parked": 2, "genuinely_his_names": ["figure organ"]},
        {"round": 2, "date": "2026-07-16", "corpus": "demo",
         "findings": {"mechanical_open": {"total": 46, "classes": {"citation-uncited": 40, "notation": 6}},
                      "reader_new": {"claimed_total": 6, "banked_verbatim": 6}},
         "gate_scores": {"hard_failing": True, "contract_hard": {"technical_support": False}},
         "rulings_drafted": {"count": 7}, "genuinely_his_parked": 2,
         "genuinely_his_names": ["figure organ"]},
    ]
    with (tmp / "evidence" / "LOOP_TRAJECTORY_2026-07-16.jsonl").open("w") as fh:
        for r in rounds:
            fh.write(json.dumps(r) + "\n")
    return tmp


def test_board_derivative_is_computed_not_narrated(tmp_path):
    repo = _fixture(tmp_path)
    b = lt.board(repo)
    cards = {c["round"]: c for c in b["rounds"]}
    # the derivative is the whole point: r1 baseline (None), r2 = 46-60 = -14
    assert cards[1]["mech_delta"] is None
    assert cards[2]["mech_total"] == 46
    assert cards[2]["mech_delta"] == -14


def test_census_counts_banked_vs_absent(tmp_path):
    repo = _fixture(tmp_path)
    c = lt.board(repo)["census"]
    assert c["rounds"] == 2
    assert c["mech_findings_banked"] == 60 + 46
    # reader: r1 claimed 8 banked 4, r2 claimed 6 banked 6 -> 4 absent, never laundered
    assert c["reader_claimed"] == 14
    assert c["reader_banked"] == 10
    assert c["reader_absent"] == 4
    assert c["genuinely_his_parked"] == 4


def test_door_marks_absent_records(tmp_path):
    repo = _fixture(tmp_path)
    present = lt._door(repo, "CLAUDE.md")
    assert present["exists"] is True and present["path"] == "CLAUDE.md"
    absent = lt._door(repo, "paper/does_not_exist.json")
    assert absent["exists"] is False
    none_door = lt._door(repo, None)
    assert none_door["path"] is None and none_door["exists"] is False


def test_round_detail_class_deltas(tmp_path):
    repo = _fixture(tmp_path)
    d = lt.round_detail(repo, 2)
    by_cls = {c["cls"]: c for c in d["findings"]["classes"]}
    # notation drained 20 -> 6; citation unchanged 40 -> 40 (the un-self-repairable basin)
    assert by_cls["notation"]["delta"] == -14
    assert by_cls["citation-uncited"]["delta"] == 0
    assert d["findings"]["mech_delta"] == -14


def test_missing_round_is_error(tmp_path):
    repo = _fixture(tmp_path)
    assert "error" in lt.round_detail(repo, 99)


def test_round_detail_detector_join_absent_when_no_census(tmp_path):
    """THE CONJUGATE WAVE (Lane 1): round_detail carries a ``detectors`` join. With no
    ``<corpus>/rounds/detector_organs_*.json`` on the synthetic tree, the join reads the
    honest-empty census — present False, matches_round False, its door NOT existing —
    never a raise (the reader's boom-guard) and never a laundered count."""
    repo = _fixture(tmp_path)
    d = lt.round_detail(repo, 2)
    assert "detectors" in d, "round_detail dropped the detector-organs join"
    det = d["detectors"]
    assert det["present"] is False and det["matches_round"] is False
    assert det["gaps"] == 0 and det["meta_leak"] == 0 and det["promise"] == 0
    assert det["door"]["exists"] is False


def test_round_detail_detector_join_is_the_readers_own_facts():
    """The join delegates to detector_organs.read_detector_organs (view=mechanism, RISK
    1) — its numbers ARE the reader's, never a re-parse. On the real tree the round whose
    date matches the banked census reads matches_round True with the reader's exact
    counts; a round of a different date reads the census but matches_round False (never
    attributing another round's detectors to it)."""
    from laplace.engine import detector_organs as det
    d3 = lt.round_detail(REPO, 3)
    if "error" in d3:
        pytest.skip("round 3 not banked in this tree")
    corpus = d3["corpus"]
    ref = det.read_detector_organs(corpus, REPO)
    if not ref.get("present"):
        pytest.skip("no detector-organs census banked for this corpus")
    dj = d3["detectors"]
    # the join carries the reader's OWN facts (delegates, never re-derives)
    assert dj["present"] is True
    assert dj["gaps"] == ref["gaps"]["gaps"]
    assert dj["meta_leak"] == ref["meta_leak"]["n"]
    assert dj["source_delta"] == ref["source_delta"]["n"]
    assert dj["promise"] == ref["promise"]["n"]
    # round 3 is dated 2026-07-17, the census date — so it is THIS round's detectors
    assert dj["matches_round"] is (ref["date"] == d3["date"])
    # a round of a different date still joins the newest census but honestly NOT as its own
    d1 = lt.round_detail(REPO, 1)
    if "error" not in d1 and d1["date"] != ref["date"]:
        assert d1["detectors"]["present"] is True
        assert d1["detectors"]["matches_round"] is False


def test_round_detail_detector_join_spawns_no_subprocess(tmp_path, monkeypatch):
    """WIRING LAW 2 — the detector join reads a banked artifact, never re-fires the
    compile-adjacent runner: round_detail spawns no subprocess (the read stays pure)."""
    import subprocess
    repo = _fixture(tmp_path)

    def _boom(*a, **k):
        raise AssertionError("round_detail spawned a subprocess (the detector join must be a pure read)")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    d = lt.round_detail(repo, 2)                 # synthetic tree — must not boom
    assert "detectors" in d


# ═══════════════════════════ the REAL banked records (on disk) ═══════════════════════════
def test_real_records_headline_numbers():
    """The surface's headline figures, asserted against the committed round 1-2 records —
    the same numbers the playwright walk cross-checks in the DOM."""
    b = lt.board(REPO)
    if not b["rounds"]:
        pytest.skip("no LOOP_TRAJECTORY records banked in this tree")
    cards = {c["round"]: c for c in b["rounds"]}
    assert cards[1]["mech_total"] == 63
    assert cards[2]["mech_total"] == 46
    assert cards[2]["mech_delta"] == -17          # 63 -> 46, the loop contracted


def test_real_round1_drill_provenance():
    d = lt.round_detail(REPO, 1)
    if "error" in d:
        pytest.skip("round 1 not banked in this tree")
    # the banked source door resolves to a real primary record
    assert d["findings"]["banked_source_door"]["exists"] is True
    # the reader gap is honest: claimed 8, banked verbatim 4 (not laundered to one number)
    assert d["reader"]["claimed"] == 8
    assert d["reader"]["banked_verbatim"] == 4
    # the lens retrieval sidecars carry exemplar rows with cosines
    assert d["lens"]["sidecars_on_disk"] > 0
    ex = d["lens"]["sidecars"][0]["exemplars"]
    assert ex and ex[0]["row_id"] and ex[0]["cos"] is not None
    # the semantic before/after is present for round 1 (the semantic md is banked)
    assert d["semantic"]["present"] is True
    assert d["semantic"]["loci"]
    # the GENUINELY-HIS residue is joined with contest doors (list, uncontested = empty)
    assert isinstance(d["rulings"]["his_residue"], list)
    for h in d["rulings"]["his_residue"]:
        assert "contests" in h
