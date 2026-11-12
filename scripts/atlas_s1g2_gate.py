#!/usr/bin/env python3
"""ATLAS-S1 generation 2 - the substrate's second generation, computed as a gate.

His ruling, 2026-09-14, verbatim: "We may actually want to reopen the S1 stage - since the store etc.
and the blueprint corpus should all be updated with it." S1 generation 1 stays DONE (RUL-20260826);
generation 2 opens with four clauses and this gate, which fails until each clause's own test lands
and passes. The atlas's law: current design is a completed generation, never the latest file - so
generation 2 names generation 1 as its parent rather than un-doing it.

Read-only. Exit 0 = every clause green (S1-g2 DONE-PENDING-WALK; his walk accepts); exit 1 = the
residuals name what has not landed. Each clause is admitted by a TEST FILE it names, never by a
sentence: a missing file is a residual, a red file is a residual, and only a green run passes.

  /usr/bin/python3 scripts/atlas_s1g2_gate.py [--json]
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CLAUSES = [
    {"id": "S1G2-C1-relocates", "title": "the container relocates: a bare copy of atlas/{src,pyproject.toml} imports and serves outside this tree",
     "test": "atlas/tests/test_container_relocates.py", "law": "store.py must not root authority at the engine repo nor hash an engine file at import; the two live stores adopt the new authority context by receipt"},
    {"id": "S1G2-C2-envelope-and-entry", "title": "the envelope and the entry kernel: content-hashed members, torn-member refusal at seal, stale-owner refusal at publication, and a cold entry computed by descent",
     "test": "atlas/tests/test_envelope_and_entry.py", "law": "a cold process holding only the entry handle reaches any record by bounded descent with no supplied handle and zero store enumerations; the entry is never a hand-written projection"},
    {"id": "S1G2-C3-rows-as-leaves", "title": "typed rows are a leaf kind: a jsonl dataset pours through the one door and a row is reachable by the same descent as a design clause",
     "test": "atlas/tests/test_rows_as_leaves.py", "law": "blueprint identity mints a row kind; a work order's rows nest under it; DISPLACED random-query success on a rows dataset is above zero"},
    {"id": "S1G2-C4-generation-parent", "title": "the blueprint corpus re-poured as generation 2 naming generation 1 as parent_generation, a required field",
     "test": "atlas/tests/test_generation_parent.py", "law": "a pour that cannot name its parent refuses; the live store's current generation carries parent_generation and the receipt names the rows that moved"},
]


def run_test(path: Path) -> dict:
    if not path.is_file():
        return {"status": "NOT-LANDED", "detail": f"{path.relative_to(ROOT)} does not exist"}
    t0 = time.time()
    try:
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=line", str(path)],
                              cwd=str(ROOT), capture_output=True, text=True, timeout=600,
                              env={**__import__("os").environ, "PYTHONPATH": "src"})
    except subprocess.TimeoutExpired:
        return {"status": "RED", "detail": "timeout 600s"}
    tail = (proc.stdout or "").strip().splitlines()[-1:] or [""]
    return {"status": "GREEN" if proc.returncode == 0 else "RED", "detail": tail[0][:200], "seconds": round(time.time() - t0, 1)}


def evaluate() -> dict:
    out = {"stage": "ATLAS-S1", "generation": 2, "gate": "atlas_s1g2_gate/1", "parent_generation": "ATLAS-S1 generation 1 (RUL-20260826-s0-done-s1-technically-done-walk-nonblocking)",
           "clauses": [], "residuals": [], "walk": {"status": "PENDING-NONBLOCKING", "effect": "confirmatory acceptance; a finding opens or amends subsequent work, absence does not rewrite landed implementation as OPEN"}}
    for c in CLAUSES:
        r = run_test(ROOT / c["test"])
        row = {**c, **r}
        out["clauses"].append(row)
        if r["status"] != "GREEN":
            out["residuals"].append(f"{c['id']}: {r['status']} - {r['detail']}")
    out["verdict"] = "DONE-PENDING-WALK" if not out["residuals"] else "OPEN"
    out["next_stage"] = "ATLAS-S2" if not out["residuals"] else None
    return out


def main(argv: list[str] | None = None) -> int:
    out = evaluate()
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0 if out["verdict"] == "DONE-PENDING-WALK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
