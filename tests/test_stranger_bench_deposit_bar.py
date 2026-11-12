"""CAMP-00's deposit gate, normalized to the comparable-volume class.

WO-20260823-camp00-gate-normalization: the gate read the newest .reembed_timing
row RAW, so a fold on a loaded box re-opened the stage while the cure was healthy
(64.61s under three sessions; 61.29s with three windows, both at ~22.37k nodes).
The contract these tests pin: PASS iff ANY of the trailing K=5 rows at comparable
volume (within 1% of the newest row's nodes) is at or under the 60s bar, with the
winning row NAMED and a breaching newest row named beside it as contention-class;
FAIL only when no comparable-volume row in the window clears it - the true
regression branch, which is NOTE-20260823-deposit-drift-watch's re-opening
condition. The arithmetic (volumes + totals of the window) rides in the result.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "score_stranger_bench", ROOT / "holdout" / "score_stranger_bench.py")
sbench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sbench)


def _store(tmp_path: Path, rows: list[dict], name: str = ".reembed_timing.jsonl") -> Path:
    p = tmp_path / name
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def _row(ts: str, total: float, nodes: int) -> dict:
    return {"ts": ts, "total": total, "nodes": nodes,
            "phases": {"embed": total * 0.3, "metric_distill": total * 0.35,
                       "wire": total * 0.2}}


# the day's own rows: the quiet pair, the loaded close, the two digest-arm folds.
TODAY = [
    _row("2026-08-23T12:21:33+00:00", 40.5073, 22350),
    _row("2026-08-23T12:28:10+00:00", 42.3171, 22351),
    _row("2026-08-23T16:50:43+00:00", 64.6086, 22371),
    _row("2026-08-23T17:15:53+00:00", 56.2685, 22373),
    _row("2026-08-23T18:51:29+00:00", 57.5259, 22376),
    _row("2026-08-23T18:53:07+00:00", 61.2897, 22377),
]


def test_breach_at_equal_volume_is_acquitted_and_the_winning_row_is_named(tmp_path):
    """The live case: newest row breached at 61.3s, a comparable row cleared it."""
    r = sbench.sb7_deposit_bar(_store(tmp_path, TODAY))
    assert r["status"] == "PASS"
    # the acquitting row is named by ts + total + volume, not merely counted
    assert r["winning_row"] == {"ts": "2026-08-23T18:51:29+00:00",
                                "total": 57.5259, "nodes": 22376}
    assert "2026-08-23T18:51:29+00:00" in r["detail"] and "57.5s" in r["detail"]
    assert "22,376" in r["detail"]
    # and the breach is named beside it as contention-class, never silently dropped
    assert r["breach_row"] == {"ts": "2026-08-23T18:53:07+00:00",
                               "total": 61.2897, "nodes": 22377}
    assert "BREACHED" in r["detail"] and "contention-class, not regression" in r["detail"]


def test_the_window_arithmetic_serves_in_the_result(tmp_path):
    """Volumes + totals of the trailing K=5, with comparability shown not asserted."""
    r = sbench.sb7_deposit_bar(_store(tmp_path, TODAY))
    w = r["window"]
    assert len(w) == 5                                   # K=5, the oldest row falls out
    assert [x["nodes"] for x in w] == [22351, 22371, 22373, 22376, 22377]
    assert [round(x["total"], 2) for x in w] == [42.32, 64.61, 56.27, 57.53, 61.29]
    assert all(x["comparable"] for x in w)               # all within 1% of 22377
    assert [x["under_bar"] for x in w] == [True, False, True, True, False]
    assert r["bar_s"] == 60.0


def test_a_clean_newest_row_still_passes_and_names_no_breach(tmp_path):
    r = sbench.sb7_deposit_bar(_store(tmp_path, TODAY[:-1]))
    assert r["status"] == "PASS"
    assert r["breach_row"] is None
    assert r["winning_row"]["total"] == 57.5259
    assert "BREACHED" not in r["detail"]


def test_all_rows_over_the_bar_at_one_volume_is_the_regression_branch(tmp_path):
    """No comparable row clears it -> FAIL, named as the drift watch's re-opening."""
    rows = [_row(f"2026-08-24T09:{m:02d}:00+00:00", t, n) for m, t, n in
            [(0, 71.10, 22370), (20, 68.40, 22372), (40, 74.90, 22374),
             (50, 66.05, 22376), (59, 72.33, 22378)]]
    r = sbench.sb7_deposit_bar(_store(tmp_path, rows))
    assert r["status"] == "FAIL"
    assert "TRUE REGRESSION" in r["detail"]
    assert "NOTE-20260823-deposit-drift-watch" in r["detail"]
    assert r["winning_row"] is None
    assert r["breach_row"]["total"] == 72.33
    assert [x["under_bar"] for x in r["window"]] == [False] * 5


def test_a_fast_row_outside_the_volume_class_cannot_acquit_a_breach(tmp_path):
    """The normalization cuts both ways: a 20k-node row is not evidence about 22.4k."""
    rows = [_row("2026-08-24T08:00:00+00:00", 38.0, 19000),   # far smaller fold, fast
            _row("2026-08-24T09:00:00+00:00", 71.1, 22370),
            _row("2026-08-24T10:00:00+00:00", 72.3, 22378)]
    r = sbench.sb7_deposit_bar(_store(tmp_path, rows))
    assert r["status"] == "FAIL"
    assert r["window"][0]["comparable"] is False          # 19,000 is >1% off 22,378
    assert [x["comparable"] for x in r["window"][1:]] == [True, True]


def test_a_row_without_volume_is_ungradeable_and_that_is_a_fail(tmp_path):
    rows = [_row("2026-08-24T09:00:00+00:00", 40.0, 22370),
            {"ts": "2026-08-24T10:00:00+00:00", "total": 41.0}]   # no nodes
    r = sbench.sb7_deposit_bar(_store(tmp_path, rows))
    assert r["status"] == "FAIL"
    assert "never a free pass" in r["detail"]


def test_a_row_without_a_total_is_ungradeable_and_that_is_a_fail(tmp_path):
    rows = [_row("2026-08-24T09:00:00+00:00", 40.0, 22370),
            {"ts": "2026-08-24T10:00:00+00:00", "nodes": 22371}]  # no total
    r = sbench.sb7_deposit_bar(_store(tmp_path, rows))
    assert r["status"] == "FAIL"
    assert "no total field" in r["detail"]


def test_a_missing_or_empty_store_fails(tmp_path):
    assert sbench.sb7_deposit_bar(tmp_path / "absent.jsonl")["status"] == "FAIL"
    assert sbench.sb7_deposit_bar(_store(tmp_path, []))["status"] == "FAIL"


def test_the_live_store_is_gradeable_by_this_predicate():
    """The gate must read the real store today - a green wired to nothing is not a green."""
    r = sbench.sb7_deposit_bar()
    assert r["status"] in {"PASS", "FAIL"}
    assert len(r["window"]) >= 1
    assert all("nodes" in x and "total" in x for x in r["window"])


def test_probe_rollup_preserves_fail_awaiting_and_absence_as_distinct_states():
    assert sbench._probe_verdict(["PASS", "PASS"]) == "GREEN"
    assert sbench._probe_verdict(["PASS", "FAIL"]) == "FAIL"
    assert sbench._probe_verdict(["PASS", "AWAITING-JUDGE"]) == "AWAITING-JUDGE"
    assert sbench._probe_verdict([]) == "NOT-RECORDED"
    assert sbench._probe_verdict(["PASS", "SKIPPED-NO-FIXTURE"]) == "UNRECOGNISED"


def test_run_rollup_counts_by_name_and_never_banks_a_red_complement():
    summary = {
        "green": {"verdict": "GREEN"},
        "failed": {"verdict": "FAIL"},
        "unjudged": {"verdict": "AWAITING-JUDGE"},
        "absent": {"verdict": "NOT-RECORDED"},
        "new-state": {"verdict": "SOMETHING-NEW"},
    }
    rollup = sbench._run_rollup(summary)
    assert rollup == {
        "green": 1, "fail": 1, "awaiting_judge": 1, "not_recorded": 1,
        "unrecognised": 1, "unresolved": 4, "total": 5, "sums_to_total": True,
    }
    assert "red" not in rollup
