#!/usr/bin/env python3
"""The fork-adjudication driver CLI — enumerate parked forks, frame them, emit the
dispatch manifest a judge consumes; and (supervised only) bank judge-returned rulings.

Answers to his steer PV-20260716T151557Z: nothing reaches his desk without the frame to
decide in seconds; a parked fork with a derivable answer is a fail. The default is
``--dry-run`` (enumerate + frames + manifest to a scratch dir, ZERO ledger writes).
``--live`` banks rulings a dispatched judge already returned (``--rulings <file>``); it is
NOT the default and no automated path fires it — the first live pass is a supervised,
in-session act, by design (builder ≠ judge; this CLI never calls a model).

    scripts/adjudicate_forks.py                      # dry-run: manifest + summary
    scripts/adjudicate_forks.py --scratch out/       # dry-run to a named dir
    scripts/adjudicate_forks.py --live --rulings judge_out.json   # supervised bank
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _bootstrap(repo: Path) -> None:
    src = str(repo / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def _cmd_dry_run(repo: Path, scratch: Path | None, as_json: bool) -> int:
    from laplace.pipeline import fork_adjudicator as fa
    summary = fa.drive(repo, mode="dry-run", scratch_dir=scratch)
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return 0
    n = summary["parked"]
    if n == 0:
        print(f"0 parked forks — every live fork carries a proxy verdict. "
              f"manifest (empty): {summary['manifest_path']}")
        return 0
    print(f"{n} parked fork(s) framed → dispatch manifest: {summary['manifest_path']}")
    print("0 ledger writes (dry-run). bank with: "
          "scripts/adjudicate_forks.py --live --rulings <judge-out>.json")
    for f in summary["forks"]:
        print(f"  {f['source']:15} {f['key']:20} {f['node'][:70]}")
    return 0


def _cmd_live(repo: Path, rulings_path: Path | None, as_json: bool) -> int:
    from laplace.pipeline import fork_adjudicator as fa
    if rulings_path is None:
        print("--live banks judge-returned rulings — it needs --rulings <file> (a JSON "
              "list of ruling dicts a dispatched judge produced from the dry-run manifest). "
              "Run --dry-run first, dispatch the manifest to a judge, then --live --rulings "
              "its output.", file=sys.stderr)
        return 2
    if not rulings_path.is_file():
        print(f"--rulings file not found: {rulings_path}", file=sys.stderr)
        return 2
    try:
        rulings = json.loads(rulings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"--rulings is not valid JSON: {e}", file=sys.stderr)
        return 2
    if not isinstance(rulings, list):
        print("--rulings must be a JSON list of ruling dicts", file=sys.stderr)
        return 2
    banked: list[dict] = []
    rejected: list[dict] = []
    for r in rulings:
        try:
            banked.append(fa.bank_fork_ruling(repo, r))
        except (ValueError, TypeError) as e:
            rejected.append({"id": (r or {}).get("id"), "reason": str(e)})
    if as_json:
        print(json.dumps({"banked": [b.get("id") for b in banked], "rejected": rejected},
                         ensure_ascii=False, indent=1))
    else:
        print(f"banked {len(banked)} ruling(s); rejected {len(rejected)}")
        for b in banked:
            print(f"  banked  {b.get('id')}  [{b.get('confidence')}]")
        for x in rejected:
            print(f"  REJECT  {x['id']}: {x['reason']}")
    return 1 if rejected else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo", default=".", help="repo root (default: cwd)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="DEFAULT: enumerate + frame + manifest, zero ledger writes")
    mode.add_argument("--live", action="store_true",
                      help="bank judge-returned rulings from --rulings (supervised; not default)")
    p.add_argument("--scratch", default=None,
                   help="dry-run manifest output dir (default: a fresh temp dir)")
    p.add_argument("--rulings", default=None,
                   help="--live: JSON list of ruling dicts a dispatched judge returned")
    p.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = p.parse_args(argv)

    repo = Path(args.repo).resolve()
    _bootstrap(repo)
    if args.live:
        return _cmd_live(repo, Path(args.rulings) if args.rulings else None, args.json)
    scratch = Path(args.scratch) if args.scratch else None
    return _cmd_dry_run(repo, scratch, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
