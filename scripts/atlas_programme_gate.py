"""Gate for the Atlas programme stages ATLAS-P1..P7 and the proof slice ATLAS-P2S (charter: atlas/programme/charter.json).

Exit 0 iff the named stage is accepted. A stage is accepted only when three typed
facts exist, none of which the builder can write for itself:

  1. the stage's acceptance receipt, produced by the stage's own checks
     (evidence/ATLAS_PROGRAMME/<stage>/acceptance.json, ``status == "PASS"``),
  2. an independent purpose judgement that accepts it
     (evidence/ATLAS_PROGRAMME/<stage>/purpose_judgement.json, ``verdict == "accept"``,
     ``judge_context`` different from the receipt's ``builder_context``),
  3. for stages the author walks (P1 and P6), his walk row in
     corpus_friction/work_orders.jsonl with an id containing ``<stage>-walked``.

The gate reads files only. It runs no tests and no model, so it cannot time out
inside the wake's budget.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "ATLAS_PROGRAMME"
WALKED_BY_AUTHOR = {"ATLAS-P1", "ATLAS-P6"}
STAGES = {f"ATLAS-P{n}" for n in range(1, 8)} | {"ATLAS-P0", "ATLAS-P2S"}


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _walk_row_exists(stage: str) -> bool:
    store = ROOT / "corpus_friction" / "work_orders.jsonl"
    needle = f"{stage.lower()}-walked"
    try:
        with store.open(encoding="utf-8") as handle:
            for line in handle:
                if needle not in line.lower():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if needle in str(row.get("id", "")).lower() and row.get("by") == "gerard":
                    return True
    except OSError:
        return False
    return False


def verdict(stage: str) -> dict:
    residuals: list[str] = []
    receipt = _load(EVIDENCE / stage / "acceptance.json")
    judgement = _load(EVIDENCE / stage / "purpose_judgement.json")
    if not receipt:
        residuals.append("no acceptance receipt")
    elif receipt.get("status") != "PASS":
        residuals.append(f"acceptance receipt status {receipt.get('status')!r}")
    if not judgement:
        residuals.append("no independent purpose judgement")
    elif judgement.get("verdict") != "accept":
        residuals.append(f"purpose judgement verdict {judgement.get('verdict')!r}")
    if receipt and judgement:
        builder = receipt.get("builder_context")
        judge = judgement.get("judge_context")
        if not builder or not judge or builder == judge:
            residuals.append("builder and judge contexts are missing or identical")
    if stage in WALKED_BY_AUTHOR and not _walk_row_exists(stage):
        residuals.append("the author's walk row is absent")
    return {"stage": stage, "gate": "atlas_programme_gate/1",
            "status": "DONE" if not residuals else "OPEN", "residuals": residuals}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in STAGES:
        print(json.dumps({"error": "usage: atlas_programme_gate.py ATLAS-P<0..7> | ATLAS-P2S"}))
        return 2
    out = verdict(argv[1])
    print(json.dumps(out, indent=1))
    if out["residuals"] == ["the author's walk row is absent"]:
        # Everything the engine can do is done; only the author's walk remains.
        print(f"{argv[1]} READY-FOR-WALK")
    return 0 if out["status"] == "DONE" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
