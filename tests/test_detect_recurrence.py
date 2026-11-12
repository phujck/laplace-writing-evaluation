"""detect_recurrence.py — the mechanical recurrence detector over
corpus_friction/*.jsonl ("the correction that recurs is a correction that
was never mechanised", EIGEN_DIARY.md).

Every test runs against a synthetic 6-row fixture ledger under tmp_path;
none touches the live corpus_friction/laplace_engine.jsonl.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import detect_recurrence as dr  # noqa: E402


def _friction(rid: str, ts: str, node: str, owning_layer: str, value: str,
              proposal: str = "", status: str = "open") -> dict:
    return {"id": rid, "ts": ts, "kind": "friction", "node": node,
            "owning_layer": owning_layer, "value": value, "proposal": proposal,
            "by": "eigen", "status": status}


def _resolution(rid: str, target: str, ts: str) -> dict:
    return {"id": rid, "record": "resolution", "kind": "", "target": target,
            "supersedes": target, "status": "resolved", "ts": ts,
            "text": f"resolved {target}"}


# The 6-row fixture:
#   RW-1, RW-2  -> same owning_layer, share "figstyle"/"suptitle" tokens,
#                  both open, no resolution => a RECURRENCE (2 witnesses).
#   RW-3        -> unrelated single friction at a different layer => no
#                  cluster (only 1 witness there).
#   RW-4, RW-5  -> same owning_layer, share tokens, but RW-5 IS resolved
#                  (RES-1 targets it) => not flagged, mechanised already.
#   RES-1       -> resolution record targeting RW-5.
FIXTURE_ROWS = [
    _friction("RW-1", "2026-07-01T00:00:00Z", "figstyle",
              "src/laplace/figstyle.py",
              "suptitle leaks past the figstyle boundary again",
              "strip suptitle at save() emit boundary"),
    _friction("RW-2", "2026-07-05T00:00:00Z", "figstyle",
              "src/laplace/figstyle.py",
              "suptitle reappeared in the DP-price figure, save() boundary",
              "strip suptitle at save() emit boundary, make it law"),
    _friction("RW-3", "2026-07-02T00:00:00Z", "voice store",
              ".codex/ sealed voice store",
              "voice wash refuses on a fresh remote container"),
    _friction("RW-4", "2026-06-01T00:00:00Z", "disclosure",
              "review_surface.py disclosure banner",
              "confidentiality banner missing once, where relevant"),
    _friction("RW-5", "2026-06-10T00:00:00Z", "disclosure",
              "review_surface.py disclosure banner",
              "confidentiality banner dropped again, once where relevant",
              status="open"),
    _resolution("RES-1", "RW-5", "2026-06-11T00:00:00Z"),
]


def _write_ledger(path: Path, records: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                            for r in records), encoding="utf-8")
    return path


def test_load_and_open_witnesses(tmp_path: Path) -> None:
    ledger = _write_ledger(tmp_path / "fixture.jsonl", FIXTURE_ROWS)
    records = dr.load_ledger_records([ledger])
    assert len(records) == 6
    witnesses = dr.open_witnesses(records)
    # RW-1..RW-5 are friction-kind + open; RES-1 is a resolution record,
    # not a witness (its status is "resolved" and its kind is "").
    assert {w["id"] for w in witnesses} == {"RW-1", "RW-2", "RW-3", "RW-4", "RW-5"}


def test_resolved_ids_links_by_target_and_supersedes(tmp_path: Path) -> None:
    ledger = _write_ledger(tmp_path / "fixture.jsonl", FIXTURE_ROWS)
    records = dr.load_ledger_records([ledger])
    assert dr.resolved_ids(records) == {"RW-5"}


def test_cluster_flags_the_unresolved_recurrence(tmp_path: Path) -> None:
    ledger = _write_ledger(tmp_path / "fixture.jsonl", FIXTURE_ROWS)
    report = dr.build_report([ledger], min_witnesses=2)

    assert report["open_witness_count"] == 5
    assert report["resolved_id_count"] == 1
    assert report["recurrence_count"] == 1

    cluster = report["recurrences"][0]
    assert set(cluster["witness_ids"]) == {"RW-1", "RW-2"}
    assert cluster["witness_count"] == 2
    assert "figstyle" in cluster["signature"] or "suptitle" in cluster["signature"]
    assert "MECHANISE" in cluster["open_stack_row"]
    assert "RW-1" in cluster["open_stack_row"] and "RW-2" in cluster["open_stack_row"]


def test_resolved_cluster_is_not_flagged(tmp_path: Path) -> None:
    ledger = _write_ledger(tmp_path / "fixture.jsonl", FIXTURE_ROWS)
    report = dr.build_report([ledger], min_witnesses=2)
    flagged_ids = {wid for c in report["recurrences"] for wid in c["witness_ids"]}
    # RW-4/RW-5 share tokens too, but RW-5 has a linked resolution (RES-1) —
    # the cluster must not appear among the recurrences.
    assert "RW-4" not in flagged_ids
    assert "RW-5" not in flagged_ids


def test_singleton_layer_is_not_a_cluster(tmp_path: Path) -> None:
    ledger = _write_ledger(tmp_path / "fixture.jsonl", FIXTURE_ROWS)
    report = dr.build_report([ledger], min_witnesses=2)
    flagged_ids = {wid for c in report["recurrences"] for wid in c["witness_ids"]}
    assert "RW-3" not in flagged_ids


def test_clean_ledger_reports_zero_recurrences(tmp_path: Path) -> None:
    clean_rows = [
        _friction("RW-10", "2026-07-01T00:00:00Z", "alpha", "layer/a.py",
                  "one-off glitch in alpha"),
        _friction("RW-11", "2026-07-01T00:00:00Z", "beta", "layer/b.py",
                  "one-off glitch in beta"),
    ]
    ledger = _write_ledger(tmp_path / "clean.jsonl", clean_rows)
    report = dr.build_report([ledger], min_witnesses=2)
    assert report["recurrence_count"] == 0
    assert report["recurrences"] == []


def test_main_check_mode_exit_codes(tmp_path: Path, capsys) -> None:
    recurring_ledger = _write_ledger(tmp_path / "fixture.jsonl", FIXTURE_ROWS)
    rc = dr.main(["--ledger", str(recurring_ledger), "--check"])
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out == ""  # --check suppresses the JSON body

    clean_rows = [
        _friction("RW-20", "2026-07-01T00:00:00Z", "alpha", "layer/a.py",
                  "isolated single glitch"),
    ]
    clean_ledger = _write_ledger(tmp_path / "clean.jsonl", clean_rows)
    rc = dr.main(["--ledger", str(clean_ledger), "--check"])
    assert rc == 0


def test_main_writes_json_to_out(tmp_path: Path, capsys) -> None:
    ledger = _write_ledger(tmp_path / "fixture.jsonl", FIXTURE_ROWS)
    out_path = tmp_path / "report.json"
    rc = dr.main(["--ledger", str(ledger), "--out", str(out_path)])
    assert rc == 1
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["recurrence_count"] == 1
    captured = capsys.readouterr()
    printed = json.loads(captured.out)
    assert printed == written


def test_main_usage_error_when_no_ledgers(tmp_path: Path, monkeypatch) -> None:
    empty_dir = tmp_path / "no_such_corpus_friction"
    monkeypatch.setattr(dr, "FRICTION_DIR", empty_dir)
    rc = dr.main([])
    assert rc == 2
