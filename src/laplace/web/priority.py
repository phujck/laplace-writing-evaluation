"""THE WORK PRIORITY STACK — what to work on next, what is blocked, on both sides.

His ask, banked verbatim in contract/talk.jsonl at 2026-08-25T19:14:00Z: "current campaign
shows we're still on S1 with nothing updated. I'm finding it quite hard to _read_ the
current status of everything, in terms of what's built and what everything is running
towards. In some sense a work priority stack would be helpful on both sides of the fabric.
Also this interface is still pretty mid."

WHAT THIS IS NOT: new bookkeeping. Every number here is already computed — wake.account()
rules WHICH rows are live, wake.account_seat() rules WHOSE they are, wake.campaign() rules
what the campaign says is next. A reconstruction-fence probe before building this found no
ordering organ but did find those three, and the whole defect this seat keeps repeating is
authoring over a state it had not reconstructed. So the only new thing here is the ORDER.

THE ORDER IS BY BLAST RADIUS, NOT BY TASTE — the sequencing SYNTH-20260825-the-unknown-
collapses established for the day's findings, applied to work:

  1 YOURS        nothing else can move until he rules. Author-direction promises, stages
                 blocked on him, permission asks. Smallest tier, highest cost of delay.
  2 BLOCKING     open findings that gate other work. A finding that says "blocking" and
                 sits unread is the cheapest thing here to fix and the most expensive to
                 leave, because everything downstream is being built on it.
  3 NEXT ACT     what the campaign itself computes as next, with its refs.
  4 BY SEAT      who owes what, so each side of the fabric can read its own column.

HONESTY CLAUSE: this ranks what is BANKED. Work nobody has banked a row for is invisible
here, and the surface says so rather than presenting its silence as an empty queue — the
absence-becomes-present collapse, applied to a worklist.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from laplace.engine import engine_ledger
from laplace.core.records.rows import load_records

SCHEMA = "laplace.web.priority-stack/1"

#: banked row ids, in every spelling the stores use. Stripped from any DERIVED face.
_ID = re.compile(r"\b(?:WO|PRM|RUL|NOTE|AMEND|RES|ASK|CAMP|VERDICT|FIND|PV|INV|CR|CRUTCH|"
                 r"SYNTH|LIV|SB)-[A-Za-z0-9.\-]+|\bsha256:[0-9a-f]{6,}")

#: the seats a stack is served for. gerard-seat is deliberately absent: his column is
#: tier 1, which is the whole point of the ordering.
SEATS = ("interface", "codex", "superego", "ego")

#: a row is HIS when it says so in its own typed fields, never by keyword sniffing the prose
_AUTHOR_DIRECTIONS = {"his", "him", "author", "gerard"}


def _is_author_owned(row: dict[str, Any], served: dict[str, Any]) -> bool:
    """Read the typed direction first, then the leading identity of the owner field."""

    direction = str(served.get("direction") or row.get("direction") or "").casefold().strip()
    if direction in _AUTHOR_DIRECTIONS:
        return True
    owner = str(served.get("owner") or row.get("owner") or "").casefold().strip()
    first = re.split(r"[^a-z]+", owner, maxsplit=1)[0] if owner else ""
    return first in _AUTHOR_DIRECTIONS


def _live_rows(root: Path, rel: str, record: str) -> dict[str, dict[str, Any]]:
    """Last-wins by id over one store, through the shared record-class grammar.

    ``engine_ledger.record_class`` already joins record/kind spelling drift and the historical
    id-prefix grammar.  Re-stating that vocabulary here made the first priority projection
    disagree with the account it claimed to serve.
    """
    out: dict[str, dict[str, Any]] = {}
    p = root / rel
    for r in load_records(p):
        if r.get("id") and engine_ledger.record_class(r) == record:
            out[str(r["id"])] = r
    return out


def _head(row: dict[str, Any], served: dict[str, Any] | None = None) -> str:
    """One caller more on the organ that already does this, instead of a second organ.

    This was eighteen lines re-implementing front_door._row_face — the same law, the same
    purpose, and the implementation my own banked note names as canonical. I wrote it while
    quoting the law that names it. That is the defect the superego measured five times in a
    day and stated as: THE ORGAN IS ALWAYS ALREADY BUILT, WIRED TO ONE CALLER, NEVER
    GENERALIZED — and the defect recurs one layer down every time.

    _row_face is also strictly better than what I wrote: it refuses to end a face on a
    colon, because rows open label-then-body and a face cut at the label says nothing.
    What survives from mine is the id strip, kept here as a thin post-step rather than
    forked into a rival: a row's prose carries its NEIGHBOURS' ids, and deriving a face
    imports them into the default register — one leaked onto the apex, the only pane that
    scored zero bare handles in the stranger audit.

    OWED, and declared rather than done: the strip belongs INSIDE _row_face, so every
    caller gets it and not just this one. front_door.py is held by another agent this
    minute; folding it in is the next act, and until then this wrapper is the crutch.
    """
    from laplace.web.front_door import _row_face

    # ADAPT THE CALLER, DO NOT FORK THE ORGAN. _row_face reads face/title/what/text/note/why;
    # a promise carries its prose in `ask`, a finding in `one_line`, a served account row in
    # `head`. Those are the same field under three names, so they are mapped in rather than
    # a second face-deriver being written — which is exactly what I did the first time.
    merged = dict(row)
    for src in ("one_line", "head", "ask"):
        val = (served or {}).get(src) or row.get(src)
        if val and not merged.get("what"):
            merged["what"] = val
            break
    face = _row_face(merged)
    return _ID.sub("", face).replace("  ", " ").strip(" -\u2014\u00b7,")


#: one stack per store state. It is 476ms of the ~1.1s his BRIEF costs to build, and the
#: brief is the page he opens — so it rebuilt on every request of the surface whose whole
#: job is to be the first thing he reads. The key is the mtime+size of the four stores it
#: folds; touch any of them and the next read rebuilds. Same discipline as the board's
#: drift key, and the same reason: a landing that recomputes what has not changed is a
#: tollbooth on his attention.
_CACHE: dict[str, Any] = {}
_KEYED_ON = ("contract/promises.jsonl", "corpus_friction/work_orders.jsonl",
             "corpus_friction/campaign.jsonl", "corpus_friction/open_stack_wants.jsonl")


def _store_key(root: Path) -> tuple:
    out = []
    for rel in _KEYED_ON:
        try:
            st = (root / rel).stat()
            out.append((rel, int(st.st_mtime_ns), st.st_size))
        except OSError:
            out.append((rel, None, None))
    return tuple(out)


def stack(repo_root: Path | str | None = None) -> dict[str, Any]:
    """The four tiers, ordered by blast radius. Rows only; no render decisions here."""
    from laplace.engine import wake

    root = Path(repo_root).resolve() if repo_root else wake._repo_root()
    key = _store_key(root)
    if _CACHE.get("key") == key:
        # the rows have not moved; built_at is restamped so the pane never wears a
        # freshness it does not have, which is the trap every cache here has to dodge.
        out = dict(_CACHE["stack"])
        out["built_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        out["from_cache"] = True
        return out
    acct = wake.account(root)
    camp = wake.campaign(root)

    promises = _live_rows(root, "contract/promises.jsonl", "promise")
    orders = _live_rows(root, "corpus_friction/work_orders.jsonl", "work_order")
    work_path = root / "corpus_friction" / "work_orders.jsonl"
    work_records = load_records(work_path)
    findings = _live_rows(root, "corpus_friction/work_orders.jsonl", "finding")
    dispositions = engine_ledger.build_consumption_index(work_records)

    # ---- tier 1: HIS, and nothing moves until he rules ------------------------
    yours: list[dict[str, Any]] = []
    for served in (acct.get("promises") or {}).get("open_rows") or []:
        rid = str(served.get("id"))
        row = promises.get(rid, {})
        if _is_author_owned(row, served):
            yours.append({"kind": "promise", "id": rid, "face": _head(row, served),
                          "date": served.get("date"), "why": "his to keep or release"})
    for st in camp.get("stages") or []:
        if str(st.get("status", "")).upper().startswith("BLOCKED-ON-AUTHOR"):
            yours.append({"kind": "stage", "id": st.get("id"),
                          "face": str(st.get("title") or st.get("id")),
                          "date": None, "why": "no seat may move this stage"})

    # ---- tier 2: BLOCKING findings -------------------------------------------
    # SEVERITY IS A TYPED FIELD AND I GREPPED PROSE FOR IT. The first cut of this scanned
    # one_line+status+text for the substring "block" and returned ZERO while thirteen open
    # findings carry severity="blocking" — the superego said four were open tonight and the
    # tier said none. Exactly the defect this organ's own docstring warns about, committed
    # inside the organ: a convention was invented instead of the banked one being read.
    # The vocabulary, measured: blocking 13 · major 12 · minor 3 · untyped 6.
    _RANK = {"blocking": 0, "major": 1, "minor": 2}
    blocking: list[dict[str, Any]] = []
    untyped_sev = 0
    findings_open: list[dict[str, Any]] = []
    for rid, row in findings.items():
        effective, status_reason = engine_ledger.effective_status_for_row(row, dispositions)
        if effective.lower() not in ("open", "banked"):
            continue
        findings_open.append(row)
        sev = str(row.get("severity") or "").lower()
        if not sev:
            untyped_sev += 1
            continue
        if sev not in ("blocking", "major"):
            continue
        blocking.append({"kind": "finding", "id": rid, "face": _head(row),
                         "severity": sev,
                         "effective_status": effective,
                         "status_reason": status_reason,
                         "date": row.get("date") or str(row.get("ts", ""))[:10],
                         "owner": row.get("owner") or row.get("owed_by")})
    blocking.sort(key=lambda r: (_RANK.get(r["severity"], 9),
                                 str(r.get("date") or "")), reverse=False)

    # ---- tier 3: what the campaign itself says is next ------------------------
    nxt = camp.get("next_act")
    stage = next((s for s in camp.get("stages") or [] if s.get("id") == nxt), {})
    prog = camp.get("progress") or {}
    next_act = {"id": nxt, "face": str(stage.get("title") or nxt or ""),
                "status": stage.get("status"),
                "refs": (prog.get("refs") or [])[:8],
                "latest_verdict": (prog.get("latest_verdict") or {}).get("id"),
                "defects": prog.get("defects") or []}

    # ---- tier 4: whose work, per side of the fabric ---------------------------
    by_seat: list[dict[str, Any]] = []
    for seat in SEATS:
        try:
            s = wake.account_seat(seat, root, acct=acct)
        except Exception as exc:  # noqa: BLE001 - a seat that cannot be read says so
            by_seat.append({"seat": seat, "error": f"{type(exc).__name__}: {exc}"})
            continue
        rows = [r for r in s["rows"] if r["partition"] == "open"]
        by_seat.append({
            "seat": seat, "counts": s["counts"], "terms": s["terms"],
            "top": [{"id": r["id"], "face": _head(orders.get(r["id"], {}), r),
                     "store": r["store"], "date": r["date"]} for r in rows[:5]],
        })
    by_seat.sort(key=lambda r: -(r.get("counts", {}).get("open", 0)))

    wo = acct.get("work_orders") or {}
    unclassified = sum(
        1 for row in work_records if engine_ledger.record_class(row) is None
    )

    built = {
        "schema_version": SCHEMA,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "wake.account() (which rows are live) · wake.account_seat() (whose they "
                  "are) · wake.campaign() (what is next) · engine_ledger (record class and "
                  "effective disposition) — this organ computes only the ORDER",
        "order": "by blast radius of delay, not by taste: his rulings, then blocking "
                 "findings, then the campaign's own next act, then each seat's column",
        "yours": yours,
        "blocking": blocking,
        "next_act": next_act,
        "by_seat": by_seat,
        "totals": {"orders_open": wo.get("open"), "orders_deferred": wo.get("deferred"),
                   "promises_open": (acct.get("promises") or {}).get("open"),
                   "findings_open": len(findings_open),
                   "blocking_open": sum(1 for r in blocking if r["severity"] == "blocking"),
                   "major_open": sum(1 for r in blocking if r["severity"] == "major"),
                   "findings_untyped_severity": untyped_sev,
                   "yours_open": len(yours)},
        "severity_vocabulary": "typed field on the finding row: blocking / major / minor. "
                               f"{untyped_sev} open finding(s) carry NO severity and are "
                               "absent from this tier — untyped is not the same as unimportant.",
        "from_cache": False,
        "cannot_see": (
            f"this ranks what is BANKED. {unclassified} rows in the work-orders store cannot "
            f"be classified by the shared record/kind/prefix grammar and are invisible here; "
            f"work nobody has banked a row for is invisible entirely. An empty tier here "
            f"means nothing was banked, never that nothing is owed."),
    }
    _CACHE["key"], _CACHE["stack"] = key, built
    return built


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="laplace-priority", description=__doc__)
    ap.add_argument("--seat", default=None, help="serve one seat's column only")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    s = stack()
    if a.json:
        print(json.dumps(s, indent=1, default=str))
        return 0
    print(f"THE STACK — {s['built_at']}   ({s['order']})\n")
    print(f"1. YOURS ({len(s['yours'])}) — nothing moves until you rule")
    for r in s["yours"]:
        print(f"     {r['kind']:8s} {r['face'][:96]}\n              {r['id']}")
    t = s["totals"]
    print(f"\n2. BLOCKING ({t['blocking_open']} blocking, {t['major_open']} major) — "
          f"findings that gate other work")
    for r in s["blocking"][:8]:
        print(f"     [{r['severity']:8s}] {r['face'][:88]}\n                {r['id']}")
    n = s["next_act"]
    print(f"\n3. NEXT ACT — {n['id']}  {n['face']}")
    print("\n4. BY SEAT")
    for c in s["by_seat"]:
        if c.get("error"):
            print(f"     {c['seat']:10s} UNREADABLE {c['error']}")
            continue
        print(f"     {c['seat']:10s} {c['counts']['open']:3d} open  "
              f"{c['counts']['deferred']:3d} deferred")
        for t in (c["top"][:2] if not a.seat or a.seat == c["seat"] else []):
            print(f"                {t['face'][:88]}")
    print(f"\n{s['cannot_see']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
