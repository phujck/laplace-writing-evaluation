#!/usr/bin/env python3
"""Run or inspect Laplace's finite independent work/review/synthesis carrier."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src")]


def main(argv=None) -> int:
    from laplace.core.runtime import require_runtime
    from laplace.pipeline import workflow as W
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="compile and execute fresh independent provider contexts")
    run.add_argument("spec")
    run.add_argument("--node", required=True, help="exact repository-relative text file")
    run.add_argument("--goal", required=True)
    run.add_argument("--model", required=True, help="actual Codex model, separate from authored role stamps")
    run.add_argument("--effort", required=True)
    run.add_argument("--state", required=True, type=Path, help="explicit Laplace state path; never implicitly grant sandbox writes")
    run.add_argument("--output", "--builder-write", dest="builder_write", action="append", default=[],
                     help="suggested output path to track; not a write permission list; repeatable")
    run.add_argument("--gpu-stage", action="append", default=[], metavar="ID",
                     help="trusted host GPU execution, without OS sandbox, for this stage; repeatable")
    run.add_argument("--timeout", type=int, default=300, help="seconds per stage")
    run.add_argument("--stop-after", help="pause after this completed stage for a recoverability check")
    resume = sub.add_parser("resume", help="continue unstarted stages after verifying exact completed evidence")
    resume.add_argument("run_dir", type=Path)
    resume.add_argument("--stop-after")
    status = sub.add_parser("status", help="read stored evidence without dispatching or repairing")
    status.add_argument("run_dir", type=Path)
    plan = sub.add_parser("plan", help="validate a role graph; no compiler, provider, or state writes")
    plan.add_argument("spec")
    sub.add_parser("list", help="observe a bounded ledger tail; recorded state is not proof of live activity")
    args = parser.parse_args(argv)
    try:
        require_runtime(ROOT)
        if args.command in {"run", "plan"}:
            spec = W._load(W._relative(ROOT, args.spec, must_exist=True))
            stages = W.validate_spec(spec)
        if args.command == "list":
            result = W.recent_workflows(ROOT)
        elif args.command == "plan":
            result = {"schema_version": W.SPEC_SCHEMA, "status": "PLAN", "provider_calls": 0,
                      "spec_handle": W.digest(W.canonical(spec)), "stages": stages}
        elif args.command == "run":
            directory = W.create_run(ROOT, spec, node=args.node, goal=args.goal, model=args.model,
                                     effort=args.effort, state=args.state, write_paths=args.builder_write,
                                     timeout=args.timeout, gpu_stages=args.gpu_stage)
            print(json.dumps({"run_path": str(directory), "status": "DECLARED"}), file=sys.stderr, flush=True)
            result = W.run_workflow(directory, stop_after=args.stop_after)
        else:
            directory = args.run_dir.resolve()
            if not directory.is_relative_to(ROOT / "evidence/WORKFLOWS"):
                raise W.WorkflowRefused("RUN-BELONGS-TO-ANOTHER-CHECKOUT")
            result = (W.inspect_run(directory) if args.command == "status"
                      else W.run_workflow(directory, stop_after=args.stop_after))
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0 if args.command in {"plan", "status", "list"} or result["status"] in {"COMPLETED", "PENDING"} else 1
    except (W.WorkflowRefused, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "REFUSED", "accepted": False, "reason": f"{type(exc).__name__}: {exc}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
