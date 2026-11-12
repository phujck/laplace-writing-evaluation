from __future__ import annotations

import json
from pathlib import Path

from laplace.web import priority
from laplace.engine import wake


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_priority_uses_effective_finding_status_and_shared_record_class(
    tmp_path: Path, monkeypatch,
) -> None:
    _write(
        tmp_path / "contract/promises.jsonl",
        [{
            "record": "promise",
            "id": "PRM-owner-only",
            "status": "open",
            "owner": "Gerard (the ruling is his)",
            "text": "choose the boundary",
        }],
    )
    _write(
        tmp_path / "corpus_friction/work_orders.jsonl",
        [
            {
                "record": "finding",
                "id": "FIND-closed",
                "status": "open",
                "severity": "blocking",
                "what": "the historical defect",
            },
            {
                "record": "resolution",
                "id": "RES-closed",
                "target": "FIND-closed",
                "status": "closed",
                "evidence": ["proof"],
            },
            {
                "kind": "finding",
                "id": "FIND-live",
                "status": "open",
                "severity": "blocking",
                "what": "the live defect",
            },
            {"record": "unknown-shape", "id": "MISC-1"},
        ],
    )
    monkeypatch.setattr(
        wake,
        "account",
        lambda _root: {
            "promises": {
                "open_rows": [{
                    "id": "PRM-owner-only",
                    "owner": "Gerard (the ruling is his)",
                    "direction": None,
                    "date": None,
                    "head": "choose the boundary",
                }],
                "open": 1,
            },
            "work_orders": {"open": 0, "deferred": 0},
        },
    )
    monkeypatch.setattr(
        wake,
        "campaign",
        lambda _root: {"stages": [], "next_act": None, "progress": {}},
    )
    monkeypatch.setattr(
        wake,
        "account_seat",
        lambda _seat, _root, acct: {
            "rows": [],
            "counts": {"open": 0, "deferred": 0, "held": 0, "total": 0},
            "terms": {},
        },
    )

    got = priority.stack(tmp_path)

    assert [row["id"] for row in got["blocking"]] == ["FIND-live"]
    assert [row["id"] for row in got["yours"]] == ["PRM-owner-only"]
    assert got["totals"]["findings_open"] == 1
    assert got["totals"]["blocking_open"] == 1
    assert "1 rows" in got["cannot_see"]
