#!/usr/bin/env python3
"""Compute ATLAS-S1's technical completion without making Gerard's walk a blocker.

S1 is a substrate gate.  Its implementation is complete when the closed landing rows and the
sealed hived authority agree mechanically.  Gerard's walk remains a separately rendered,
confirmatory act: it can discover a new defect and thereby open new work, but its absence does not
rewrite landed implementation as OPEN.

Read-only.  The JSON result deliberately distinguishes ``verdict`` from ``walk``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent.parent
WORK_ORDERS = ROOT / "corpus_friction" / "work_orders.jsonl"
HIVE_RECEIPT = ROOT / "atlas" / "stores" / "blueprint" / "hive-custody-receipt.json"

REQUIRED_RESOLUTIONS = (
    "RES-20260826-atlas-hived-storage-morphology-landed",
    "RES-20260826-blueprint-first-corpus-landed",
    "RES-20260826-conjugate-serve-founding-landed",
)
MIN_EVENT_COUNT = 2668


def _rows(path: Path) -> Iterator[dict[str, Any]]:
    if not path.is_file():
        return
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: unparseable JSONL row") from exc
        if isinstance(row, dict):
            yield row


def evaluate(root: Path = ROOT) -> dict[str, Any]:
    residuals: list[str] = []
    work_orders = root / "corpus_friction" / "work_orders.jsonl"
    receipt_path = root / "atlas" / "stores" / "blueprint" / "hive-custody-receipt.json"

    by_id: dict[str, dict[str, Any]] = {}
    try:
        for row in _rows(work_orders):
            if row.get("id"):
                by_id[str(row["id"])] = row
    except ValueError as exc:
        residuals.append(str(exc))

    resolutions: dict[str, str] = {}
    for resolution_id in REQUIRED_RESOLUTIONS:
        row = by_id.get(resolution_id)
        state = str((row or {}).get("status") or "MISSING")
        resolutions[resolution_id] = state
        if row is None or row.get("record") != "resolution" or state != "closed":
            residuals.append(f"{resolution_id} is not a closed resolution")

    receipt: dict[str, Any] = {}
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        residuals.append(f"blueprint hive custody receipt is unavailable: {type(exc).__name__}")

    reachability = receipt.get("reachability") if isinstance(receipt, dict) else {}
    claims = receipt.get("claims") if isinstance(receipt, dict) else {}
    identity = receipt.get("store_identity") if isinstance(receipt, dict) else {}
    event_count = receipt.get("event_count") if isinstance(receipt, dict) else None
    required_receipt_claims = {
        "status=sealed": receipt.get("status") == "sealed",
        "ledger_schema=v2": receipt.get("ledger_schema") == "atlas-conceptric-sqlite/2",
        "blueprint identity": identity.get("role") == "blueprint-generation",
        "hived event authority": receipt.get("event_hive_ref") == "hives/events",
        "zero orphans": claims.get("zero_orphans") is True,
        "all marked chunks verified": claims.get("all_marked_chunks_present_and_hash_verified") is True,
        "reachability exact": reachability.get("status") == "exact",
        "event counts agree": (
            isinstance(event_count, int)
            and event_count >= MIN_EVENT_COUNT
            and reachability.get("event_count") == event_count
        ),
        "head digest present": str(receipt.get("head_digest") or "").startswith("sha256:"),
    }
    for claim, held in required_receipt_claims.items():
        if not held:
            residuals.append(f"hive custody claim failed: {claim}")

    return {
        "stage": "ATLAS-S1",
        "gate": "atlas_s1_gate/1",
        "verdict": "DONE" if not residuals else "OPEN",
        "walk": {
            "status": "PENDING-NONBLOCKING",
            "effect": (
                "confirmatory acceptance; a finding opens or amends subsequent work, "
                "but absence never rewrites technical completion"
            ),
        },
        "closed_resolutions": resolutions,
        "hive_custody": {
            "event_count": event_count,
            "head_digest": receipt.get("head_digest") if isinstance(receipt, dict) else None,
            "claims": required_receipt_claims,
        },
        "next_stage": "ATLAS-S2" if not residuals else None,
        "residuals": residuals,
    }


def main() -> int:
    result = evaluate()
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if result["verdict"] == "DONE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
