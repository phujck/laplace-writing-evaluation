"""The carried ``record=work-order`` ledger has an explicit disposition.

The 2026-09-14 packet selected the newer row dialect deliberately: immediately
before the packet's own order was minted it contained 90 work orders, 53 from
before 2026-09-14, of which 10 already had resolution targets and 43 did not.
The age gate below uses 2026-09-28 as its minimum audit horizon so those August
rows exercise the 30-day rule immediately rather than leaving a vacuous test.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "corpus_friction" / "work_orders.jsonl"
CLUSTER_NOTE = "NOTE-20260914-carried-ledger-adjudication-clusters"
AUDIT_HORIZON_FLOOR = date(2026, 9, 28)
ALLOWED_VERDICTS = {"RESOLVED", "SUPERSEDED", "RETIRED-INERT", "STILL-LIVE"}


def _rows() -> list[dict]:
    return [
        json.loads(line)
        for line in LEDGER.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _origin(row: dict) -> date | None:
    raw = row.get("ts") or row.get("date")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw.strip().replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _unadjudicated_older_than(
    rows: list[dict], *, as_of: date, max_age_days: int = 30
) -> list[str]:
    targets = {
        row.get("target")
        for row in rows
        if row.get("record") == "resolution"
        and isinstance(row.get("target"), str)
        and row.get("target")
    }
    stale: list[str] = []
    for row in rows:
        if row.get("record") != "work-order":
            continue
        origin = _origin(row)
        if origin is not None and (as_of - origin).days > max_age_days:
            if row.get("id") not in targets:
                stale.append(str(row.get("id")))
    return stale


def test_every_work_order_older_than_30_days_has_an_adjudicating_row() -> None:
    as_of = max(date.today(), AUDIT_HORIZON_FLOOR)
    assert _unadjudicated_older_than(_rows(), as_of=as_of) == []


def test_age_gate_detects_a_missing_adjudication() -> None:
    planted = [
        {
            "record": "work-order",
            "id": "WO-PLANTED-STALE",
            "ts": "2026-01-01T00:00:00Z",
        }
    ]
    assert _unadjudicated_older_than(planted, as_of=date(2026, 2, 1)) == [
        "WO-PLANTED-STALE"
    ]


def test_carried_packet_has_one_typed_adjudication_per_order() -> None:
    rows = _rows()
    by_id = {row.get("id"): row for row in rows if row.get("id")}
    note = by_id[CLUSTER_NOTE]
    adjudications = [
        row
        for row in rows
        if row.get("record") == "resolution"
        and row.get("cluster_note") == CLUSTER_NOTE
    ]

    assert note["selection"]["selected"] == 43
    assert len(adjudications) == 43
    assert len({row["target"] for row in adjudications}) == 43
    assert Counter(row.get("verdict") for row in adjudications) == Counter(
        note["counts"]
    )
    assert set(note["counts"]) == ALLOWED_VERDICTS

    for row in adjudications:
        target = by_id[row["target"]]
        assert target.get("record") == "work-order"
        assert _origin(target) < date(2026, 9, 14)
        assert CLUSTER_NOTE in row.get("evidence", [])
        assert any(
            edge == {"rel": "grounds", "target": CLUSTER_NOTE}
            for edge in row.get("edges", [])
        )
        if row["verdict"] == "STILL-LIVE":
            assert row.get("effect") == "reopen"
            assert row.get("blocks")
        else:
            assert row.get("effect") in {"close", "retire"}

