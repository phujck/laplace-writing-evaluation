#!/usr/bin/env python3
"""ATLAS-S0's gate — the stage status COMPUTED FROM ROWS, never re-derived or re-authored.

Gerard's directive (2026-08-24 evening, the goal to all seats): the wake must recover the
stage status cold, and the reauthoring ends. This gate is the mechanism: `wake.py
--campaign` runs stage gates live, so once the ATLAS-S0 stage row cites this command (the
ego pen's amendment), every wake on every provider recovers S0's exact state from the
stores — generation health, judge verdict, the two-part gate law's position — without any
session re-deriving or re-explaining it.

Exit law (the two-part gate law, CHARTER_2026-08-24 §3): exit 0 only at
SERVED + JUDGE-VERIFIED (= done-pending-walk; the walk stays Gerard's and is never
claimed here). Anything less exits 1 with the exact residual named on stdout.

Read-only against every store. Runtime law: /usr/bin/python3, system + user site.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "corpus_friction" / "atlas_inventory.jsonl"
CAMPAIGN = ROOT / "corpus_friction" / "campaign.jsonl"
WORK_ORDERS = ROOT / "corpus_friction" / "work_orders.jsonl"


def _rows(path: Path):
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except ValueError:
            continue  # a torn tail must not blind the reader to the rows above it


def main() -> int:
    status: dict = {"stage": "ATLAS-S0", "gate": "atlas_s0_gate/1"}
    residuals: list[str] = []

    # 1. SERVED half: the latest inventory generation, whole and typed.
    latest_gen, gen_rows, classes = None, 0, {}
    for r in _rows(INVENTORY):
        if r.get("record") == "inventory-generation":
            latest_gen, gen_rows, classes = r["id"], 0, {}
        elif r.get("generation") == latest_gen:
            gen_rows += 1
            classes[r.get("class", "?")] = classes.get(r.get("class", "?"), 0) + 1
    status["latest_generation"] = latest_gen
    status["generation_rows"] = gen_rows
    status["classes"] = classes
    if latest_gen is None or gen_rows == 0:
        residuals.append("no inventory generation found — the enumerator has not served S0")
    if "mathematical-inheritance" not in classes:
        residuals.append("latest generation lacks mathematical-inheritance rows "
                         "(the UP amendment's inheritance is unrepresented)")

    # 2. JUDGE-VERIFIED half: the judged row minted through the ego pen.
    judged = None
    for store in (CAMPAIGN, WORK_ORDERS):
        for r in _rows(store):
            rid = str(r.get("id", ""))
            if "atlas-s0-judged" in rid.lower() or (
                    r.get("stage") == "ATLAS-S0" and "judged" in str(r.get("record", ""))):
                judged = {"id": rid or r.get("stage"), "store": store.name,
                          "ts": r.get("ts")}
    status["judged_row"] = judged
    if judged is None:
        residuals.append("no atlas-s0-judged row minted yet (requested from the ego pen: "
                         "fabric message atlas-m0:claude-to-codex:s0-judged-mint-request:1)")

    # 3. The walk: named, never claimed.
    status["walk"] = "Gerard's — done-pending-walk is this gate's ceiling by law"

    status["verdict"] = "DONE-PENDING-WALK" if not residuals else "OPEN"
    status["residuals"] = residuals
    print(json.dumps(status, ensure_ascii=False, indent=1))
    return 0 if not residuals else 1


if __name__ == "__main__":
    raise SystemExit(main())
