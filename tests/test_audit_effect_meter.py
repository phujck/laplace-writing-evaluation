"""N38's audit-effect meter, proved against a synthetic fixture ledger (not the live one —
the live checkout's .wire_verdicts.jsonl is currently empty, see the script's own
data_status.context_note). Fixture shape mirrors embed_router.py's real write schema
exactly (query/id/verdict/method/cos), including a reversal (wire -> noise on re-judgment)
and a re-grade under both methods, so every computed rate is checked against a hand-counted
expectation, not just "it runs".
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from laplace.representation import embed_router as er  # noqa: E402


def _load_meter():
    spec = importlib.util.spec_from_file_location(
        "audit_effect_meter", ROOT / "scripts" / "audit_effect_meter.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("audit_effect_meter", mod)
    spec.loader.exec_module(mod)
    return mod


# The synthetic ledger (8 verdict records, in append order):
#   1. (q1,a) wire      mechanical   <- later reversed
#   2. (q2,b) noise     mechanical
#   3. (q3,c) grit      jury
#   4. (q1,a) noise     jury         <- the reversal of #1
#   5. (q4,d) wire      mechanical   <- re-graded by jury below, same verdict
#   6. (q5,e) noise     mechanical
#   7. (q4,d) wire      jury         <- agrees with #5 (mechanical==jury=='wire')
#   8. (q6,f) noise     mechanical
#
# Distinct pairs, LATEST verdict wins: (q1,a)=noise, (q2,b)=noise, (q3,c)=grit,
# (q4,d)=wire, (q5,e)=noise, (q6,f)=noise  -> 6 judged pairs: wire=1, grit=1, noise=4.
_VERDICTS = [
    {"query": "q1", "id": "a", "verdict": "wire", "method": "mechanical", "cos": 0.81},
    {"query": "q2", "id": "b", "verdict": "noise", "method": "mechanical", "cos": 0.41},
    {"query": "q3", "id": "c", "verdict": "grit", "method": "jury", "cos": 0.61},
    {"query": "q1", "id": "a", "verdict": "noise", "method": "jury", "cos": 0.55,
     "why": "reconsidered on regrade"},
    {"query": "q4", "id": "d", "verdict": "wire", "method": "mechanical", "cos": 0.91},
    {"query": "q5", "id": "e", "verdict": "noise", "method": "mechanical", "cos": 0.31},
    {"query": "q4", "id": "d", "verdict": "wire", "method": "jury", "cos": 0.72},
    {"query": "q6", "id": "f", "verdict": "noise", "method": "mechanical", "cos": 0.45},
]

# The current proposals frontier: one genuinely-new pair, plus two RECURRENCES —
# (q4,d) recurred after a 'wire' verdict, (q5,e) recurred after a 'noise' verdict.
_PROPOSALS = [
    {"query": "q7", "id": "g", "cos": 0.60, "heat": 0.5, "via": None},
    {"query": "q4", "id": "d", "cos": 0.50, "heat": 0.4, "via": None},
    {"query": "q5", "id": "e", "cos": 0.35, "heat": 0.3, "via": None},
]


def _write_fixture(repo_root: Path) -> None:
    with (repo_root / er.VERDICTS_FILE).open("w", encoding="utf-8") as fh:
        for v in _VERDICTS:
            fh.write(json.dumps(v) + "\n")
    with (repo_root / er.PROPOSALS_FILE).open("w", encoding="utf-8") as fh:
        for p in _PROPOSALS:
            fh.write(json.dumps(p) + "\n")


def test_headline_pre_audit_rate(tmp_path):
    _write_fixture(tmp_path)
    mod = _load_meter()
    report = mod.build_report(tmp_path, n_bins=2)
    h = report["headline"]
    assert h["n"] == 6
    assert h["verdict_counts"] == {"wire": 1, "grit": 1, "noise": 4}
    assert h["pre_audit_false_association_rate"] == round(4 / 6, 4)


def test_wire_reversal_uses_ever_wire_denominator(tmp_path):
    _write_fixture(tmp_path)
    mod = _load_meter()
    report = mod.build_report(tmp_path)
    post = report["post_audit"]
    # (q1,a) and (q4,d) were EACH banked 'wire' at some point -> denominator 2, not 1
    # (the current latest-wins wire count is only 1, since (q1,a) got reversed away from it).
    assert post["n_ever_wire"] == 2
    assert post["n_wire_reversed"] == 1
    assert post["wire_reversal_rate"] == 0.5
    assert post["reversals"] == [{"query": "q1", "id": "a", "first_verdict": "wire",
                                  "later_verdict": "noise",
                                  "later_why": "reconsidered on regrade"}]


def test_recurrence_after_verdict_both_wire_and_noise(tmp_path):
    _write_fixture(tmp_path)
    mod = _load_meter()
    report = mod.build_report(tmp_path)
    rec = report["post_audit"]["recurred_after_verdict_counts"]
    assert rec == {"wire": 1, "grit": 0, "noise": 1}
    assert report["frontier"]["n_total"] == 3
    assert report["frontier"]["n_never_judged"] == 1       # only (q7, g)
    assert report["frontier"]["n_recurred_after_verdict"] == 2


def test_method_agreement_proxy_on_regraded_pair(tmp_path):
    _write_fixture(tmp_path)
    mod = _load_meter()
    report = mod.build_report(tmp_path)
    jp = report["jury_precision_proxy"]
    # two pairs were banked under BOTH methods: (q4,d) mechanical=wire/jury=wire (agree),
    # and (q1,a) mechanical=wire/jury=noise (disagree, the same reversal counted above).
    assert jp["n_pairs_regraded_both_methods"] == 2
    assert jp["agree"] == 1
    assert jp["agreement_rate"] == 0.5
    assert jp["jury_bench_applicable"] is False


def test_per_period_is_order_bins_not_calendar(tmp_path):
    _write_fixture(tmp_path)
    mod = _load_meter()
    report = mod.build_report(tmp_path, n_bins=2)
    pp = report["per_period"]
    assert pp["supported_as_calendar_time"] is False
    bins = pp["order_bins"]
    assert len(bins) == 2
    assert sum(b["n"] for b in bins) == 8                  # every raw line, not just distinct pairs
    assert bins[0]["seq_range"] == [0, 3]
    assert bins[1]["seq_range"] == [4, 7]


def test_empty_ledger_reports_zero_honestly_not_fabricated(tmp_path):
    mod = _load_meter()
    report = mod.build_report(tmp_path)
    assert report["headline"]["n"] == 0
    assert report["headline"]["pre_audit_false_association_rate"] is None
    assert report["data_status"]["context_note"] is not None
    assert "different ledger" in report["data_status"]["context_note"] \
        or "DIFFERENT ledger" in report["data_status"]["context_note"]
    assert report["post_audit"]["wire_reversal_rate"] is None
    assert report["jury_precision_proxy"]["n_pairs_regraded_both_methods"] == 0
    assert report["per_period"]["order_bins"] == []


# A fixture where EVERY verdict row carries `ts`, spread over two calendar days -
# ts coverage 4/4 = 1.0, well above CALENDAR_MIN_FRACTION (0.5) -> calendar bins supported.
_TS_VERDICTS = [
    {"query": "q1", "id": "a", "verdict": "wire", "method": "mechanical", "cos": 0.81,
     "ts": "2026-07-10T09:00:00+00:00"},
    {"query": "q2", "id": "b", "verdict": "noise", "method": "mechanical", "cos": 0.41,
     "ts": "2026-07-10T10:00:00+00:00"},
    {"query": "q3", "id": "c", "verdict": "grit", "method": "jury", "cos": 0.61,
     "ts": "2026-07-11T09:00:00+00:00"},
    {"query": "q4", "id": "d", "verdict": "noise", "method": "mechanical", "cos": 0.31,
     "ts": "2026-07-11T11:00:00+00:00"},
]

# A fixture MIXING a ts-less legacy prefix (3 rows, pre-fix) with a ts-covered suffix
# (2 rows, post-fix, same calendar day) - ts coverage 2/5 = 0.4, BELOW the 0.5 threshold, so
# the calendar portion is real but reported as not-yet-supported.
_MIXED_VERDICTS = [
    {"query": "m1", "id": "x", "verdict": "noise", "method": "mechanical", "cos": 0.30},
    {"query": "m2", "id": "y", "verdict": "wire", "method": "mechanical", "cos": 0.80},
    {"query": "m3", "id": "z", "verdict": "grit", "method": "jury", "cos": 0.60},
    {"query": "m4", "id": "w", "verdict": "noise", "method": "mechanical", "cos": 0.40,
     "ts": "2026-07-12T08:00:00+00:00"},
    {"query": "m5", "id": "v", "verdict": "wire", "method": "mechanical", "cos": 0.85,
     "ts": "2026-07-12T09:30:00+00:00"},
]


def _write_verdicts(repo_root: Path, rows: list[dict]) -> None:
    with (repo_root / er.VERDICTS_FILE).open("w", encoding="utf-8") as fh:
        for v in rows:
            fh.write(json.dumps(v) + "\n")


def test_calendar_bins_supported_when_ts_coverage_sufficient(tmp_path):
    """Fix 0c: once verdict rows carry `ts`, the meter must group them by calendar day
    (ts[:10]) instead of only append order, and say so honestly via
    supported_as_calendar_time."""
    _write_verdicts(tmp_path, _TS_VERDICTS)
    mod = _load_meter()
    report = mod.build_report(tmp_path, n_bins=4)
    pp = report["per_period"]
    assert pp["calendar_ts_coverage_fraction"] == 1.0
    assert pp["supported_as_calendar_time"] is True
    cbins = {b["day"]: b for b in pp["calendar_bins"]}
    assert set(cbins) == {"2026-07-10", "2026-07-11"}
    assert cbins["2026-07-10"]["n"] == 2
    assert cbins["2026-07-10"]["wire"] == 1 and cbins["2026-07-10"]["noise"] == 1
    assert cbins["2026-07-10"]["noise_rate"] == 0.5
    assert cbins["2026-07-11"]["n"] == 2
    assert cbins["2026-07-11"]["grit"] == 1 and cbins["2026-07-11"]["noise"] == 1
    # every row carried ts, so there is no ts-less prefix left for the append-order fallback
    assert pp["order_bins"] == []


def test_mixed_ts_and_ts_less_rows_honest_split(tmp_path):
    """A ledger straddling the `ts` fix: the ts-less prefix still falls back to append-order
    bins, the ts-covered suffix gets real calendar-day bins, and supported_as_calendar_time
    honestly reports that this particular ledger's coverage is still too thin to trust."""
    _write_verdicts(tmp_path, _MIXED_VERDICTS)
    mod = _load_meter()
    report = mod.build_report(tmp_path, n_bins=1)
    pp = report["per_period"]
    assert pp["calendar_ts_coverage_fraction"] == 0.4
    assert pp["supported_as_calendar_time"] is False        # 0.4 < CALENDAR_MIN_FRACTION (0.5)

    # the ts-less prefix (m1, m2, m3) is what the order bins cover - not the whole ledger
    assert len(pp["order_bins"]) == 1
    ob = pp["order_bins"][0]
    assert ob["n"] == 3
    assert ob["seq_range"] == [0, 2]
    assert ob["wire"] == 1 and ob["grit"] == 1 and ob["noise"] == 1

    # the ts-covered suffix (m4, m5) is still reported, honestly, as its own calendar bin
    assert len(pp["calendar_bins"]) == 1
    cb = pp["calendar_bins"][0]
    assert cb["day"] == "2026-07-12"
    assert cb["n"] == 2
    assert cb["wire"] == 1 and cb["noise"] == 1
    assert cb["noise_rate"] == 0.5


def test_table_render_does_not_crash_on_empty_or_populated(tmp_path):
    mod = _load_meter()
    empty_report = mod.build_report(tmp_path)
    assert "N/A (n=0)" in mod.render_table(empty_report)
    _write_fixture(tmp_path)
    full_report = mod.build_report(tmp_path)
    table = mod.render_table(full_report)
    assert "pre-audit false-association rate" in table
    assert "wire reversal rate" in table
