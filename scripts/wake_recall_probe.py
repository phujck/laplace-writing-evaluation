#!/usr/bin/env python3
"""The stranger bench, made real: a COLD session fires the wake and answers from it alone.

CLAUDE.md has claimed since 2026-07-28 that the stranger bench "is the wake/close's own
acceptance test and re-runs at every close". Measured 2026-09-14: holdout/STRANGER_BENCH.json
carried zero questions and no close ran it. This is the organ that makes the claim true.

The questions live in holdout/WAKE_RECALL.json, OUTSIDE the wake's surface, each with a
``truth`` the cold session never sees. The session is told one thing: run the wake, answer
from it. Its answers come back under a strict schema and the orchestrator grades them against
the truths - a recall number, not a feeling.

  /usr/bin/python3 scripts/wake_recall_probe.py [--run] [--timeout N]
"""
from __future__ import annotations
import argparse, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "holdout" / "WAKE_RECALL.json"


def schema(qids: list[str]) -> dict:
    return {"type": "object", "additionalProperties": False,
            "properties": {
                "wake_command": {"type": "string"},
                "answers": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {"id": {"type": "string", "enum": qids},
                                   "answer": {"type": "string"},
                                   "found_in_wake": {"type": "boolean"},
                                   "where": {"type": "string"}},
                    "required": ["id", "answer", "found_in_wake", "where"]}},
                "what_the_wake_did_not_carry": {"type": "array", "items": {"type": "string"}},
                "seconds_to_read": {"type": "number"}},
            "required": ["wake_command", "answers", "what_the_wake_did_not_carry", "seconds_to_read"]}


def goal(questions: list[dict]) -> str:
    qs = "\n".join(f"- {q['id']}: {q['q']}" for q in questions)
    return (
        "You are a STRANGER to this repository. You have no memory of it and you must not read its "
        "design documents, its handoffs, its rows or its source to answer. Do exactly this:\n\n"
        "1. Run the wake, and nothing else:  /usr/bin/python3 scripts/wake.py --grade 0 --person\n"
        "   (you may also run it with --full, --account or --campaign; say which you used)\n"
        "2. Answer the questions below FROM THE WAKE'S OUTPUT ALONE. If the wake does not carry an "
        "answer, say so in the answer field and set found_in_wake false - a confident invention is "
        "the worst possible result here, and an honest 'the wake does not say' is a useful one.\n"
        "3. For each answer, 'where' names the key or line of the wake payload you read it from.\n"
        "4. List what you needed and the wake did not carry.\n\n"
        "QUESTIONS:\n" + qs + "\n\n"
        "Do not read HANDOFF.md, the SESSION_HANDOFF files, DESIGN_*.md, corpus_friction/*, contract/* "
        "or any source file. The wake is the whole surface under test. Answer ONLY with the JSON the "
        "output schema demands.")


def grade(bench: dict, answers: list[dict]) -> dict:
    by = {a["id"]: a for a in answers}
    rows = []
    for q in bench["questions"]:
        a = by.get(q["id"])
        rows.append({"id": q["id"], "asked": q["q"], "truth": q["truth"],
                     "answer": (a or {}).get("answer", "(no answer)"),
                     "found_in_wake": (a or {}).get("found_in_wake"),
                     "where": (a or {}).get("where", ""), "grades": q["grades"],
                     "verdict": "UNGRADED"})
    return {"rows": rows, "answered": sum(1 for r in rows if r["answer"] != "(no answer)"),
            "claimed_in_wake": sum(1 for r in rows if r["found_in_wake"]), "of": len(rows)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--out-dir", default=".dispatch")
    a = ap.parse_args(argv)
    bench = json.loads(BENCH.read_text(encoding="utf-8"))
    qids = [q["id"] for q in bench["questions"]]
    work = ROOT / a.out_dir / f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-wake-recall"
    work.mkdir(parents=True, exist_ok=True)
    (work / "schema.json").write_text(json.dumps(schema(qids), indent=1), encoding="utf-8")
    (work / "goal.md").write_text(goal(bench["questions"]), encoding="utf-8")
    if not a.run:
        print(json.dumps({"probe": "wake-recall", "questions": len(qids), "work": str(work.relative_to(ROOT)),
                          "status": "COMPILED"}, indent=1))
        return 0
    cmd = ["/usr/bin/python3", str(ROOT / "scripts" / "dispatch_codex.py"), "scripts/wake.py",
           "wake recall probe: answer from the wake alone", "--goal-file", str(work / "goal.md"),
           "--output-schema", str(work / "schema.json"), "--sandbox", "read-only",
           "--out-dir", a.out_dir, "--run", "--timeout", str(a.timeout)]
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=a.timeout + 120)
    row = {}
    for line in proc.stdout.splitlines():
        if line.strip().startswith("{"):
            try: row = json.loads(proc.stdout[proc.stdout.index(line):])
            except Exception: pass
            break
    ret = row.get("return_path")
    result = {"probe": "wake-recall", "questions": len(qids), "seconds": round(time.time() - t0, 1),
              "dispatch": row.get("id"), "status": row.get("status"), "work": str(work.relative_to(ROOT))}
    if ret and (ROOT / ret).is_file():
        try:
            answer = json.loads((ROOT / ret).read_text(encoding="utf-8"))
            result.update(grade(bench, answer.get("answers", [])))
            result["wake_command"] = answer.get("wake_command")
            result["what_the_wake_did_not_carry"] = answer.get("what_the_wake_did_not_carry")
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
    (work / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
