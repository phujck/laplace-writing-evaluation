#!/usr/bin/env python3
"""reconstruction_fence.py — ask the record whether it already holds this work.

The command-line face of :mod:`laplace.engine.reconstruction_fence`, for the authoring moment:
before writing a module or dispatching a builder, put the intent to the banked record and
read what comes back. Advisory at this tier — the probe reports, the author decides.

    python3 scripts/reconstruction_fence.py probe "a fence that checks the record before authoring"
    python3 scripts/reconstruction_fence.py probe "..." --tree --json
    python3 scripts/reconstruction_fence.py probe "..." --stamp 2026-08-17 --site "authoring"
    python3 scripts/reconstruction_fence.py judge FP-20260817-01 true-catch --by gerard --stamp 2026-08-17
    python3 scripts/reconstruction_fence.py rate --landed WO-1,WO-2 --stamp 2026-08-17
    python3 scripts/reconstruction_fence.py ledger

Timestamps enter through --stamp only. A probe without one prints its answer and banks
nothing; judge and rate require one before they write.
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from laplace.engine import reconstruction_fence as fence  # noqa: E402


def _root(args):
    return os.path.abspath(getattr(args, "root", None) or ROOT)


def cmd_probe(args):
    """A PROBE IS AN ACT, AND ACTS BANK. Banking is now the default.

    THE CLOSED LOOP THIS OPENS, measured 2026-08-25: the fence is the cure for the defect
    that costs this engine most — authoring over a state nobody reconstructed. It is
    ADVISORY by DECISION_2026-08-17, which promotes it to FAIL once a false-negative rate
    is measured over >=10 landed work orders spanning >=5 closes. That rate is computed
    from corpus_friction/fence_probes.jsonl. That ledger holds THREE ROWS, all stamped
    2026-08-17, the day the fence shipped — because banking required remembering an
    optional flag, and eight days of authoring did not remember it. So the denominator
    could never accumulate, the bar could never be met, the fence could never promote, and
    it fires for nobody while the defect it exists to stop recurs weekly.

    A cure whose promotion depends on a human remembering a flag is not wired; it is
    decorative. The default inverts: every probe banks, and --no-bank is the deliberate
    dry read. A banked act still requires an explicit stamp; omission refuses instead of
    silently degrading to an unbanked probe or reading the machine clock.
    """
    legs = list(fence.ALL_LEGS) if args.tree else list(fence.DEFAULT_LEGS)
    root = _root(args)
    if not args.no_bank and not args.stamp:
        raise fence.FenceError(
            "banking is the default and requires --stamp YYYY-MM-DD; "
            "pass --no-bank for a deliberate dry read"
        )
    if args.stamp:
        record = fence.advise(root, args.intent, site=args.site, stamp=args.stamp,
                              cap=args.cap, legs=legs)
        if args.json:
            print(json.dumps(record, indent=2, sort_keys=True))
        else:
            print(fence.render({"rows": record.get("hits", []),
                                "provenance": record["provenance"]}, args.intent))
            print("banked %s -> %s" % (record.get("id", "nothing"), fence.LEDGER))
        return 0
    result = fence.probe(root, args.intent, cap=args.cap, legs=legs)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(fence.render(result, args.intent))
        print("nothing banked (--no-bank): this probe does not reach the ledger the "
              "promotion bar is measured from")
    return 0


def cmd_judge(args):
    row = fence.judge(_root(args), args.probe_id, args.verdict, by=args.by,
                      stamp=args.stamp, hit=args.hit, note=args.note)
    if args.json:
        print(json.dumps(row, indent=2, sort_keys=True))
    else:
        print("%s: %s judged %s by %s" % (row["id"], row["target"], row["verdict"], row["by"]))
        if row["hit"]:
            print("  hit: %s" % row["hit"])
    return 0


def cmd_rate(args):
    landed = [x.strip() for x in (args.landed or "").split(",") if x.strip()]
    if args.landed_file:
        with open(args.landed_file, encoding="utf-8") as fh:
            landed += [ln.strip() for ln in fh if ln.strip()]
    report = fence.false_negative_report(_root(args), landed, stamp=args.stamp)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    print("fence probes banked: %d (%d carried a hit)"
          % (report["probes_banked"], report["probes_with_hits"]))
    print("landed work-orders measured against: %d" % len(report["landed"]))
    print("caught at authoring time: %s"
          % (", ".join(c["id"] for c in report["caught"]) or "none"))
    print("missed: %s" % (", ".join(report["missed"]) or "none"))
    print("false-negative rate: %s — %s"
          % (report["false_negative_rate"], report["rate_note"]))
    print("judged rows: %s" % json.dumps(report["judged"]))
    if args.stamp:
        print("banked %s -> %s" % (report["id"], fence.LEDGER))
    return 0


def cmd_ledger(args):
    rows = fence.ledger_rows(_root(args))
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0
    if not rows:
        print("no rows in %s" % fence.LEDGER)
        return 0
    for r in rows:
        if r.get("schema") == fence.PROBE_SCHEMA:
            print("%s  [%s]  %s" % (r.get("id"), r.get("stamp"), r.get("site")))
            print("      %s" % r.get("intent"))
            for h in r.get("hits") or []:
                print("      hit %s (%s, %s) score %s" % (h.get("id"), h.get("leg"),
                                                          h.get("status"), h.get("score")))
            if not r.get("hits"):
                print("      no hit")
        elif r.get("schema") == fence.VERDICT_SCHEMA:
            print("%s  [%s]  %s on %s by %s" % (r.get("id"), r.get("stamp"),
                                                r.get("verdict"), r.get("target"),
                                                r.get("by")))
        elif r.get("schema") == fence.RATE_SCHEMA:
            print("%s  [%s]  false-negative rate %s over %d landed"
                  % (r.get("id"), r.get("stamp"), r.get("false_negative_rate"),
                     len(r.get("landed") or [])))
    print("\n%d row(s)" % len(rows))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="reconstruction_fence", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None, help="repo root (default: this repo)")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("probe", help="does the record already hold this?")
    p.add_argument("intent", help="what is about to be authored or dispatched")
    p.add_argument("--cap", type=int, default=fence.DEFAULT_CAP)
    p.add_argument("--tree", action="store_true",
                   help="also read the graded tree (large; off by default)")
    p.add_argument("--site", default="cli",
                   help="where the probe was called from, recorded on a banked row")
    p.add_argument("--no-bank", action="store_true",
                   help="print the answer and write nothing. The deliberate dry read — "
                        "banking is the default, because the promotion bar is measured "
                        "from the probe ledger and a ledger that only grows when someone "
                        "remembers a flag never grows")
    p.add_argument("--stamp", default=None,
                   help="ISO 8601; required for the default banked probe")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_probe)

    j = sub.add_parser("judge", help="record whether a probe's hit was a real catch")
    j.add_argument("probe_id")
    j.add_argument("verdict", choices=list(fence.VERDICTS))
    j.add_argument("--by", required=True)
    j.add_argument("--stamp", required=True, help="ISO 8601; never read from the clock")
    j.add_argument("--hit", default="", help="which hit row the verdict is about")
    j.add_argument("--note", default="")
    j.add_argument("--json", action="store_true")
    j.set_defaults(func=cmd_judge)

    r = sub.add_parser("rate", help="false-negative rate against landing-sweep catches")
    r.add_argument("--landed", default="",
                   help="comma-separated work-order ids the landing sweep flagged")
    r.add_argument("--landed-file", default=None, help="one work-order id per line")
    r.add_argument("--stamp", default=None, help="ISO 8601; bank the report as a row")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_rate)

    led = sub.add_parser("ledger", help="list the banked probe rows")
    led.add_argument("--json", action="store_true")
    led.set_defaults(func=cmd_ledger)

    args = ap.parse_args(argv)
    if not getattr(args, "cmd", None):
        ap.print_help()
        return 1
    try:
        return args.func(args)
    except fence.FenceError as e:
        sys.stderr.write("error: %s\n" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
