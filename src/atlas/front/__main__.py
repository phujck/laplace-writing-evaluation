"""The front door's entry point.

    scripts/laplace-python -m atlas.front <manifest.json> [--out PATH] [--datasets a,b]
                                         [--tolerance 0|1|2]

The manifest names where the record and the tree hive live and which of the declared draw's
datasets to run; it carries no dial. Everything printed comes from a stage receipt.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .receipts import canonical_dataset_of_run, questions_of_run, verify_run, ReceiptProtocolError
from .comparison import oracle_agreement_of_question, EvidenceUnproved


def summarize_run(payload: dict) -> dict:
    """Summarize the validated owner view; no local version or fallback parser."""
    verify_run(payload)
    if not payload["datasets"]:
        raise ReceiptProtocolError("CLI summary requires nonempty dataset coverage")
    datasets = {}
    for name, observed in payload["datasets"].items():
        run = canonical_dataset_of_run(observed)
        questions = questions_of_run(run)
        if not questions:
            raise ReceiptProtocolError("CLI summary requires nonempty question coverage")
        for row in questions:
            if not isinstance(row.get("partial"), dict) or any(
                    key not in row["partial"] for key in ("answer", "certificate", "refusal")):
                raise ReceiptProtocolError("CLI summary requires the retained partial answer/certificate/refusal")
            key = "answer_equals_the_flat_control"
            if key not in row or (row[key] is not None and type(row[key]) is not bool):
                raise ReceiptProtocolError("CLI summary requires explicit flat-control agreement")
            try:
                oracle_agreement_of_question(row)
            except EvidenceUnproved as exc:
                raise ReceiptProtocolError(str(exc)) from exc
        datasets[name] = {
            "stages": [stage["stage"] for stage in run["receipt"]["stages"]],
            "chain_verified": True,  # The owner recomputed the full chain above.
            "questions": [
                {"qid": row["qid"], "answer": row["partial"]["answer"],
                 "certified": row["partial"]["certificate"] is not None,
                 "equals_the_flat_control": row["answer_equals_the_flat_control"],
                 "equals_the_known_answer": oracle_agreement_of_question(row)}
                for row in questions],
        }
    return {"datasets": datasets, "seconds": payload["seconds"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atlas.front", description=__doc__)
    parser.add_argument("manifest", help="the run manifest: {root, datasets}")
    parser.add_argument("--out", default="", help="write the whole receipt chain here")
    parser.add_argument("--datasets", default="",
                        help="comma-separated subset of the declared draw's datasets")
    parser.add_argument("--tolerance", type=int, default=0,
                        help="which of the question's three DERIVED tolerances to read at")
    args = parser.parse_args(argv)
    datasets = [name for name in args.datasets.split(",") if name] or None  # loop-ok: the named dataset subset
    from ..lifted import (load, receipt, require_current, LiftUnavailable,
                          LiftIncompatible, LiftSourceChanged)
    try:
        # The full command reaches numeric kernels. Refuse missing capability
        # before run_front_door creates record/tree state; help stays core-only.
        load("gpu_state")
        load("contraction_kernels")
        load("query_plan")
        load("query_obligations")
        require_current(receipt(("query_plan", "query_obligations"), observe_current=False))
        from .door import run_front_door, FrontInputUnavailable
        from .draw import DatasetSelectionRefused
        try:
            payload = run_front_door(args.manifest, datasets=datasets,
                                     tolerance_index=args.tolerance)
        except (FrontInputUnavailable, DatasetSelectionRefused) as exc:
            print(json.dumps({"record": "atlas.front-unavailable/1", "status": "REFUSED",
                              "reason": exc.result["reason"], "input": exc.result}))
            return 2
    except (LiftUnavailable, LiftIncompatible, LiftSourceChanged) as exc:
        refusal = {"record": "atlas.front-unavailable/1", "status": "REFUSED",
                   "reason": type(exc).__name__, "message": str(exc)}
        if isinstance(exc, LiftSourceChanged):
            refusal["source_currentness"] = exc.result
        print(json.dumps(refusal))
        return 2
    try:
        summary = {**summarize_run(payload), "out": args.out}
    except ReceiptProtocolError as exc:
        print(json.dumps({"record": "atlas.front-unavailable/1", "status": "REFUSED",
                          "reason": "ReceiptProtocolError", "message": str(exc)}))
        return 2
    if args.out:
        Path(args.out).write_text(json.dumps(payload, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
