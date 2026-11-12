"""Run the native restructure operator against a registered project.

Usage: python scripts/restructure.py <project> <arc.json> [--apply]

Default is a DRY RUN — the full report (new plan, validation, dirty diff, spine
payloads, prose bundles) printed as JSON, nothing written. ``--apply`` freezes,
writes plan+base, clears the L2 friction ledger and reconciles section_refs.
The arc schema lives in ``laplace.pipeline.restructure`` (TARGET_ARC_*).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from laplace.pipeline import restructure


def main(argv: list[str]) -> int:
    args = [a for a in argv if a != "--apply"]
    if len(args) != 2:
        print(__doc__.strip())
        return 2
    project, arc_path = args
    arc = json.loads(Path(arc_path).read_text(encoding="utf-8"))
    report = restructure.execute(project, arc, dry_run="--apply" not in argv)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
