"""drain_feedback.py — fold remote-review comments into the manuscript's ledger.

The desk side of the remote loop: a phone commits each comment as one JSON file into
``<manuscript_dir>/feedback/inbox/`` (via the GitHub Contents API). After ``git pull``,
this drains that inbox into ``feedback/feedback.jsonl`` through the ONE ledger producer
(``manuscript_bridge.feedback_ingest``), preserving each comment's device-minted id and
timestamp so a commute comment is the same object as a desk one. Idempotent: a re-run on
an already-drained inbox is a no-op.

GENERAL: give it any manuscript root; every path derives from it.

    python scripts/drain_feedback.py <manuscript_root.tex> --corpus <name>
    python scripts/drain_feedback.py <manuscript_root.tex> --corpus <name> --keep   # don't delete inbox
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.manuscript import manuscript_bridge as mb   # noqa: E402


def _manuscript_dir(root_arg: str) -> Path:
    p = Path(root_arg)
    if not p.is_absolute():
        p = ROOT / root_arg
    return p.resolve().parent


def drain(root_arg: str, corpus: str, keep: bool = False, channel: str = "local") -> dict:
    mdir = _manuscript_dir(root_arg)
    inbox = mdir / "feedback" / "inbox"
    ledger = mdir / "feedback" / "feedback.jsonl"
    if not inbox.is_dir():
        return {"inbox": str(inbox), "found": 0, "ingested": 0, "skipped": 0,
                "note": "no inbox dir — nothing to drain"}
    files = sorted(inbox.glob("*.json"))
    ingested = skipped = bad = refused = 0
    refusals = []
    for f in files:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            bad += 1
            continue
        rec.pop("_state", None)
        out = mb.feedback_ingest(ROOT, corpus, rec, ledger=ledger, channel=channel)
        if out.get("ok"):
            ingested += 1
        elif out.get("skipped"):
            skipped += 1
        elif out.get("error"):
            # REFUSED (e.g. an actorless or author-attributed remote record): the
            # file is evidence of a forgery attempt, so it is left in the inbox
            # rather than deleted — never folded into the ledger, never destroyed.
            refused += 1
            refusals.append({"file": f.name, "reason": out["error"]})
            print(f"REFUSED {f.name}: {out['error']}")
            continue
        else:
            bad += 1
            continue
        if not keep:
            try:
                f.unlink()
            except OSError:
                pass
    return {"inbox": str(inbox), "ledger": str(ledger), "found": len(files),
            "ingested": ingested, "skipped": skipped, "bad": bad,
            "refused": refused, "refusals": refusals}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", help="the manuscript compile root (a main.tex)")
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--keep", action="store_true", help="do not delete drained inbox files")
    ap.add_argument("--channel", choices=["local", "remote"], default="local",
                     help="local (default, today's behavior) or remote (the public "
                          "demo genre — actor guard: refuses actorless/author-"
                          "attributed records; see manuscript_bridge.feedback_ingest)")
    a = ap.parse_args()
    out = drain(a.root, a.corpus, keep=a.keep, channel=a.channel)
    print(json.dumps(out, indent=2))
    if out.get("ingested"):
        print(f"\n{out['ingested']} comment(s) folded into the ledger — "
              "commit feedback.jsonl and start the comment-driven revision pass.")
    if out.get("refused"):
        print(f"\n{out['refused']} record(s) REFUSED (actor guard) and left in the "
              "inbox for inspection — see refusals above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
