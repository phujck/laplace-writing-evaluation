"""Execute an evolution contract through the native operator.

Usage: python scripts/evolve.py [<project>] [<evolution_dir>] [--apply]

Default is a DRY RUN against temp copies of the ledgers — the report is the
rehearsal, the repo is untouched. ``--apply`` routes through the B10 apply-gate:
all seven build-completion gates must pass the POST-evolution state or the apply
is refused (repo untouched), the failing gate names printed on stderr and the
full verdict banked to ``<evolution_dir>/gates.json``. There is NO --force —
loosening the gates is a dials change made with evidence from real refusals.
Defaults resolve through the registry: the active project, its newest contract dir.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from laplace.pipeline import evolve, registry

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project", nargs="?", default=None)
    ap.add_argument("evolution_dir", nargs="?", default=None)
    ap.add_argument("--apply", action="store_true",
                    help="write the real ledgers (default: dry-run on temp copies)")
    args = ap.parse_args()

    project = args.project or registry.default_project()
    proj = registry.resolve(project)
    if proj is None:
        sys.exit(f"unknown project: {project!r}")
    evo_dir = args.evolution_dir or evolve.latest_evolution_dir(proj)
    if evo_dir is None:
        sys.exit(f"no evolution contracts for {project!r}")

    if args.apply:
        # the B10 apply-gate: all seven gates or the apply is refused
        try:
            verdict = evolve.gated_apply(project, evo_dir)
        except evolve.EvolveError as e:
            print(f"apply refused: {e}", file=sys.stderr)
            gates_path = Path(evo_dir) / "gates.json"
            if gates_path.is_file():
                try:
                    verdict = json.loads(gates_path.read_text(encoding="utf-8"))
                    failed = verdict.get("failed_gates") or []
                    if failed:
                        print(f"failing gates: {', '.join(failed)}", file=sys.stderr)
                except (OSError, json.JSONDecodeError):
                    pass
            sys.exit(1)
        print(json.dumps(verdict, indent=1, ensure_ascii=False))
        sys.exit(0 if verdict.get("applied") else 1)

    try:
        report = evolve.execute(project, evo_dir, dry_run=True)
    except evolve.EvolveError as e:
        sys.exit(f"contract error: {e}")
    print(json.dumps(report, indent=1, ensure_ascii=False))
    sys.exit(0 if report.get("ok") else 1)
