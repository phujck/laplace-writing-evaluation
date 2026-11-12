"""Typed closure for author walk verdicts.

Campaign gates and interface surfaces must fold the same rows.  A handle containing
``front-door-m4-walked`` is never evidence by itself: only a typed, author-attributed acceptance
counts, and an explicit retraction removes exactly the acceptance it names.
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "laplace.front-door-walk-closure/1"
DEFAULT_STAGES = ("m1", "m2", "m3", "m4")


def fold_walk_verdicts(
    rows: Iterable[dict[str, Any]], stages: Sequence[str] = DEFAULT_STAGES
) -> dict[str, Any]:
    """Fold typed acceptances and retractions for the requested programme stages."""

    programme = tuple(dict.fromkeys(str(stage).strip().lower() for stage in stages if stage))
    candidates: dict[str, list[dict[str, Any]]] = {stage: [] for stage in programme}
    redlines: dict[str, list[str]] = {stage: [] for stage in programme}
    retracted: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        record = str(raw.get("record", ""))
        row_id = str(raw.get("id", ""))
        if record == "walk-verdict-retraction" and raw.get("retracts"):
            retracted.add(str(raw["retracts"]))
            continue
        stage_name = str(raw.get("stage", ""))
        short = stage_name.removeprefix("front-door-")
        if short not in candidates or stage_name != f"front-door-{short}":
            continue
        if record == "walk-redline":
            redlines[short].append(row_id)
        if (
            record == "walk-verdict"
            and raw.get("verdict") == "accepted"
            and raw.get("actor") == "gerard"
            and raw.get("via") == "front-door"
        ):
            candidates[short].append(raw)

    state: dict[str, dict[str, Any]] = {}
    for stage in programme:
        accepted = [row for row in candidates[stage] if str(row.get("id", "")) not in retracted]
        if accepted:
            row = accepted[-1]
            state[stage] = {
                "walked": True,
                "row": str(row.get("id", "")),
                "ts": row.get("ts"),
                "redlines": redlines[stage],
            }
        elif candidates[stage]:
            state[stage] = {
                "retracted": True,
                "row": str(candidates[stage][-1].get("id", "")),
                "redlines": redlines[stage],
            }
        else:
            state[stage] = {"redlines": redlines[stage]}
    accepted_stages = [stage for stage in programme if state[stage].get("walked")]
    return {
        "schema_version": SCHEMA_VERSION,
        "stages": list(programme),
        "state": state,
        "accepted_stages": accepted_stages,
        "missing_stages": [stage for stage in programme if stage not in accepted_stages],
        "retracted_acceptance_ids": sorted(retracted),
    }


def evaluate_front_door_program(
    repo_root: Path | str, stages: Sequence[str] = DEFAULT_STAGES
) -> dict[str, Any]:
    """Read the one diagnosed ledger and fail closed on any physical integrity wound."""

    from laplace.pipeline.ledger import integrity_projection, read_jsonl_diagnosed

    root = Path(repo_root).resolve()
    relative = "corpus_friction/work_orders.jsonl"
    rows, diagnostics = read_jsonl_diagnosed(
        root / relative, store=relative, required=True)
    result = fold_walk_verdicts(rows, stages)
    integrity = integrity_projection(diagnostics)
    return {
        **result,
        "integrity": integrity,
        "passed": not result["missing_stages"] and not integrity["cracked"],
        "authority": (
            "typed record=walk-verdict + verdict=accepted + stage + actor=gerard + "
            "via=front-door, minus exact retractions; ids and prose are never authority"
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the typed front-door walk gate")
    parser.add_argument("--root", default=".")
    parser.add_argument("--stages", nargs="+", default=list(DEFAULT_STAGES))
    args = parser.parse_args(argv)
    result = evaluate_front_door_program(args.root, args.stages)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if result["passed"] else 1


if __name__ == "__main__":  # pragma: no cover - exercised through the bootstrap script
    raise SystemExit(main())
