# A reader over a project's round history: assemble the convergence ledger (open-
# findings deltas, gate transitions, per-round cost) and print it as JSON or markdown.
# Thin wrapper on pipeline.convergence_ledger, the paper_gates -> loop_gates precedent.
#
# This is a READER, not a gate: rc is 0 for any assembled ledger (converged or not) and
# non-zero only when the project dir cannot be resolved. The last line is a SUMMARY=
# line so a truncated read (tail -1) still carries the shape.
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from laplace.pipeline.convergence_ledger import assemble_ledger, to_markdown


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="convergence ledger over a project's rounds")
    ap.add_argument("project", help="registry project name or a manuscript dir")
    fmt = ap.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="emit the raw ledger as JSON")
    fmt.add_argument("--md", action="store_true", help="emit the markdown report (default)")
    args = ap.parse_args(argv)

    ledger = assemble_ledger(args.project)
    if "error" in ledger:
        print(f"SUMMARY=MISSING {ledger['error']}")
        return 1

    if args.json:
        print(json.dumps(ledger, indent=1, ensure_ascii=False))
    else:
        print(to_markdown(ledger))

    rounds = ledger.get("rounds") or []
    print(f"SUMMARY=OK layout={ledger.get('layout') or 'none'} rounds={len(rounds)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
