#!/usr/bin/env python3
"""The author's walk, executable — the ONE command the atlas board hands Gerard.

ONE truth, then one projection (the codex mount-refusal cure, 2026-08-24):
  1. FIRST the canonical migration act through the one write door — set_progress(walked=True)
     with actor=SeatRole.AUTHOR. The canonical event is the SOLE walked truth. If the store
     refuses, NOTHING has claimed a walk anywhere.
  2. ONLY AFTER success, the walked row in corpus_friction/work_orders.jsonl — a DERIVED
     PROJECTION citing the canonical event id, carrying his words verbatim and any vetoes
     (vetoed INV-* ids re-enter HOLD-FOR-RULING at the enumerator's next generation). If this
     append fails the truth already stands canonically; the row is regenerable.

THE AUTHENTICATION BOUNDARY, stated honestly (codex's audit was right to demand this): the
AUTHOR guard at migration.py:372 validates a ROLE LABEL, not Gerard's identity — any caller
can pass it. This script therefore CARRIES his hand, it does not PROVE it. The proof is
procedural under standing law ("he speaks in user turns, nothing else is him"): this command
is lawful only run by him at his shell, or by a seat in the same session as his explicit
walk words. Every run banks a forensic receipt (interpreter, user, tty, cwd) inside the
canonical event's runtime, so a walk claimed against that law is visible, not silent.

Run BY HIM (his box, his hand — the standing PV law: his words bank verbatim):
    /usr/bin/python3 scripts/atlas_walk.py ATLAS-S0 --accept "the walk verdict, in his words" \
        [--veto INV-...]...

Runtime law: /usr/bin/python3, system + user site.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", nargs="?", default="ATLAS-S0")
    ap.add_argument("--accept", required=True, help="his walk verdict, verbatim")
    ap.add_argument("--veto", action="append", default=[],
                    help="an INV-* row id vetoed at the walk (repeatable)")
    a = ap.parse_args(argv)
    words = a.accept.strip()
    if not words:
        print("REFUSED: an empty walk is not a walk", file=sys.stderr)
        return 1

    import getpass
    import os

    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    stamp = ts.replace(":", "").replace("-", "")[:15]
    slug = a.stage.lower().replace("_", "-")
    row_id = f"VERDICT-{stamp}-{slug}-walked"

    from laplace.representation import atlas_bridge as ab

    tty = "no-tty"
    try:
        tty = os.ttyname(sys.stdin.fileno())
    except OSError:
        pass
    forensic = (f"forensic: user={getpass.getuser()} tty={tty} cwd={os.getcwd()} — the "
                f"AUTHOR label is procedural, not cryptographic; this receipt makes a "
                f"walk claimed outside the law visible")
    ctx = ab.MigrationEventContext(
        occurred_at=ts,
        correlation_id=row_id,
        provenance=(ab.SourceRef(
            "author-walk-words",
            "sha256:" + sha256(words.encode("utf-8")).hexdigest(),
            forensic),),
        residual=ab.Residual(ab.ResidualStatus.WITHIN_BOUND, 0.0, 0.0, "author-walk",
                          f"vetoes: {len(a.veto)}; {forensic}"),
        runtime=ab.collect_runtime_receipt(ROOT, observed_at=ts),
        producer_ref=ab.ProducerRef("cli", "atlas_walk", "author-hand"),
        producer=ab.SeatRole.EGO,
        actor=ab.SeatRole.AUTHOR,
    )
    # THE ONE TRUTH FIRST: if this refuses, nothing anywhere claims a walk.
    ledger = ab.MigrationLedger(ab._store())
    stored = ledger.set_progress(a.stage, ctx, walked=True)
    event_id = stored.event.event_id
    print(f"banked: canonical walk event {event_id[:28]}... (actor=AUTHOR, {a.stage})")

    # THE DERIVED PROJECTION SECOND, citing the canonical truth it renders.
    row = {
        "record": "verdict", "id": row_id, "ts": ts, "status": "banked",
        "text": (f"THE AUTHOR'S WALK of {a.stage}, verbatim: \"{words}\""
                 + (f" VETOED ROWS ({len(a.veto)}): {', '.join(a.veto)} — each re-enters "
                    f"HOLD-FOR-RULING at the enumerator's next generation." if a.veto
                    else " No vetoes.")
                 + f" DERIVED PROJECTION of canonical event {event_id} — the event is the "
                   f"sole walked truth; this row is regenerable."),
        "by": "the author's hand at the CLI (scripts/atlas_walk.py); words banked unedited",
    }
    wo = ROOT / "corpus_friction" / "work_orders.jsonl"
    with wo.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"banked: {row_id} (projection of {event_id[:20]}...) -> work_orders.jsonl")
    replay = ledger.replay()
    st = replay.stages[a.stage]
    print(json.dumps({"stage": a.stage, "revision": st.revision, "material": st.material,
                      "judged": st.judged, "walked": st.walked}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
