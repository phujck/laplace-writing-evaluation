#!/usr/bin/env python3
"""ledger_age_audit.py — THE AGING TEETH (W-TEETH, PV-20260722T165050Z).

His verbatim law tonight: *loops left open at context time fossilize; an aged ask is a
destroyed decision; "carried, named" must stop being free.* The census found open rows
riding close after close with no defer and no owner — the fossilized-loop class. This is
the mechanical gate that makes carrying cost something: every OPEN row in the accumulating
ledgers, once past its class's max quiet age, must carry a **dated defer with an owner**
(the ``defer_until`` / ``deferred_by`` note idiom) or it is NAMED as a defect — and the
close FAILs on it (``scripts/close_checklist.py`` → ``aging_teeth``, FAIL_ELIGIBLE).

THE ASK-OR-DECIDE LAW (PV-20260722T165050Z): an author-askable row older than the session
that minted it is a defect unless it is deferred-with-date. You either ask him, decide it,
or defer it out loud with an owner and a date — you may not carry it silently.

THE LEDGERS (the accumulating stores this walks):
  corpus_friction/work_orders.jsonl  the work-order pickup loop (open == status open and not
                                     retired by an EVIDENCE-carrying resolution, mirroring
                                     storyboard.open_work_orders).
  contract/promises.jsonl            the promise ledger, both directions. ``direction: "his"``
                                     rows are HIS covenant — "longer-horizon by nature,
                                     carried not collected" (contract/README.md) — EXEMPT
                                     from the FAIL but NAMED in the report (carried, not free).
  corpus_friction/open_stack_forks.jsonl  the Stratum-1 typed fork store (the render-owned
                                     table's machine twin). Open == status 🔴/🟡; a fork's
                                     ``trigger`` (the legend's ⚪ "re-deferred-with-trigger")
                                     is its native condition-defer.

THE CLASSES + THEIR MAX QUIET AGE (tuned to the census's real ages, 2026-07-22):
  author-gated  3 days   author-askable rows — a work-order ``requested_by`` gerard, or an
                         Eigen-promise to him (no ``direction``). The tightest loop: you
                         could just ask him, so a stale one is the destroyed decision.
  machine       14 days  Eigen-minted work-orders and research forks — real work that takes
                         longer, but still cannot ride silently past a fortnight.

THE DEFER (the note idiom — additive, append-only, never a mutation of the row):
  A row is DEFERRED-WITH-DATE when EITHER
    - its own record carries ``defer_until`` (an ISO date >= today) AND ``deferred_by``, OR
    - a later NOTE ROW ``{"record": "defer", "target": <id>, "defer_until": <YYYY-MM-DD>,
      "deferred_by": <owner>, ...}`` is appended to the SAME ledger (the newest such note
      wins), OR
    - a defer act carries a non-empty ``trigger`` and owner (historical rows may also
      carry the explicit ``defer_until: condition`` sentinel), OR
    - a fork carries a non-empty ``trigger`` (the ⚪ condition-defer the OPEN_STACK
      legend already sanctions).
  A defer whose date has PASSED is itself stale — the row ages again (no infinite defer;
  re-touching a row never resets its clock, because age is measured from the ORIGINATING
  date/ts, not the last write).

QUIET AGE is measured from the row's ORIGIN (work-order ``ts``, promise ``date``, fork
``opened``) — never from when the row was last rewritten. Re-minting a row does not buy it
a fresh clock; that would be exactly the gaming this gate forbids. Mechanically (promises,
where lines accumulate per id — ``_collapse_by_id``): **disposition is last-wins, the age
clock is first-wins** — the newest line's ``status``/``direction`` rule, while the age runs
from the FIRST line that carried a ``date``.

VERDICT: the last stdout line is the sentinel
    VERDICT=PASS failing=0 exempt=<n> deferred=<n> warns=<n>
    VERDICT=FAIL failing=<n> exempt=<n> deferred=<n> warns=<n>
and the exit code is 1 iff any row is FAILING (past its gate, undeferred). Exempt and
deferred rows never move the exit code — but they are printed, every run, so nothing
carried is ever free.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

# the ONE ledger reading-convention module (WO-20260820-ledger-semantics-hardening):
# repo/scripts/<this> -> repo/src on sys.path so the kind/status join helper imports
# whether or not the package is installed in the running interpreter.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

WORK_ORDERS = "corpus_friction/work_orders.jsonl"
PROMISES = "contract/promises.jsonl"
FORKS = "corpus_friction/open_stack_forks.jsonl"

CLASS_MAX_QUIET_AGE = {"author": 3, "machine": 14}

_FORK_OPEN_STATUSES = {"🔴", "🟡"}


@dataclass
class Row:
    ledger: str
    id: str
    cls: str                       # "author" | "machine"
    origin: Optional[str]          # ISO date the clock runs from (None => undateable)
    quiet_age: Optional[int]       # days since origin (None => undateable)
    deferred_until: Optional[str]  # the live defer date, if any
    deferred_by: Optional[str]     # the defer's named owner, if any
    exempt_reason: Optional[str]   # non-None => carried-not-collected, never FAILs
    label: str = ""                # a short human handle

    @property
    def gate(self) -> int:
        return CLASS_MAX_QUIET_AGE[self.cls]

    @property
    def deferred(self) -> bool:
        return self.deferred_until is not None

    @property
    def failing(self) -> bool:
        if self.exempt_reason is not None:
            return False
        if self.quiet_age is None:
            return False  # undateable: cannot age it, so cannot fail it (reported as a warn)
        if self.deferred:
            return False
        return self.quiet_age > self.gate

    @property
    def undateable(self) -> bool:
        return self.exempt_reason is None and self.quiet_age is None and not self.deferred


@dataclass
class Report:
    rows: list[Row] = field(default_factory=list)
    residuals: list[dict] = field(default_factory=list)
    # The exact diagnosed rows used to derive ``rows``.  Consumers such as the
    # Atlas liveness pane enrich this same read instead of silently reparsing the
    # ledgers through a second tolerance policy.
    records: dict[str, list[dict]] = field(default_factory=dict, repr=False)

    @property
    def failing(self) -> list[Row]:
        return [r for r in self.rows if r.failing]

    @property
    def exempt(self) -> list[Row]:
        return [r for r in self.rows if r.exempt_reason is not None]

    @property
    def deferred(self) -> list[Row]:
        return [r for r in self.rows if r.deferred and r.exempt_reason is None]

    @property
    def undateable(self) -> list[Row]:
        return [r for r in self.rows if r.undateable]

    @property
    def failed(self) -> bool:
        """Aged rows or an incomplete physical read both invalidate the gate."""
        return bool(self.failing or self.residuals)


# --------------------------------------------------------------------------- io helpers
def _read_jsonl(path: Path) -> list[dict]:
    """Compatibility row projection that refuses to erase diagnosed incompleteness."""
    from laplace.pipeline.ledger import read_jsonl_diagnosed
    rows, residuals = read_jsonl_diagnosed(path, required=True)
    if residuals:
        first = residuals[0]
        raise OSError(
            f"{path} wounded: {len(residuals)} residual(s); "
            f"{first.get('defect')} at {first.get('line') or first.get('path')}")
    return [r for r in rows if isinstance(r, dict)]


def _age_days(origin: Optional[str], today: date) -> Optional[int]:
    if not origin:
        return None
    try:
        return (today - date.fromisoformat(origin[:10])).days
    except (ValueError, TypeError):
        return None


def _parse_iso(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def _defer_notes(records: list[dict]) -> dict[str, tuple[Optional[str], Optional[str]]]:
    """{target_id: (defer_until, deferred_by)} — the LAST valid defer act per target.

    A defer note is ``record == "defer"`` (or a ``defer_until`` on any note-kind row) that
    names a ``target`` (accepts ``target`` / ``supersedes`` / ``consumes``) and carries an
    ISO ``defer_until`` or named condition and a ``deferred_by`` owner. File order is the append-only
    disposition order: a later expired defer supersedes an earlier future one and must
    surface as lapsed. Choosing the furthest date lets old scheduling intent overrule a
    newer act and makes these teeth disagree with the canonical account.

    Inline defers participate in the same order under their own row id, so a later defer
    note supersedes the mint's inline date and a later restatement can supersede the note.
    """
    from laplace.engine import engine_ledger

    best: dict[str, tuple[Optional[str], Optional[str]]] = {}
    for r in records:
        if r.get("record") != "defer" and "defer_until" not in r:
            continue
        if r.get("record") == "defer":
            target = r.get("target") or r.get("supersedes") or r.get("consumes")
        else:
            target = (r.get("target") or r.get("supersedes")
                      or r.get("consumes") or r.get("id"))
        du = r.get("defer_until")
        by = r.get("deferred_by") or r.get("by")
        if not target:
            continue
        state, parsed = engine_ledger.defer_date_state(r)
        trigger = r.get("trigger")
        if state == engine_ledger.DEFER_DATE_VALID and parsed is not None and by:
            best[str(target)] = (str(du).strip(), str(by))
        elif state == engine_ledger.DEFER_DATE_CONDITION and by:
            best[str(target)] = ("condition", str(by))
        elif (state == engine_ledger.DEFER_DATE_ABSENT and by
              and isinstance(trigger, str) and trigger.strip()):
            best[str(target)] = ("condition", str(by))
        else:
            # The latest attempted scheduling act owns file-order precedence even
            # when malformed.  It masks an older defer but does not itself defer;
            # obligation_semantic_diagnostics makes the UNKNOWN a hard residual.
            best[str(target)] = (None, None)
    return best


def _live_defer(row: dict,
                notes: dict[str, tuple[Optional[str], Optional[str]]], today: date
                ) -> tuple[Optional[str], Optional[str]]:
    """The live (date >= today or named condition) LAST defer disposition for a row."""
    disposition = notes.get(str(row.get("id")))
    if disposition is None:
        return None, None
    du, by = disposition
    if du == "condition" and by is not None:
        return du, by
    parsed = _parse_iso(du)
    if parsed is None or parsed < today or by is None:
        return None, None
    return du, by


# --------------------------------------------------------------------------- work-orders
#: the fields an EVIDENCE-carrying resolution may use to name the order it retires,
#: joined in the schema's own precedence (``laplace.engine.engine_ledger._LINK_FIELDS``).
#: ``consumes`` is the field the resolution schema defines for the join; ``supersedes``
#: is the fallback the older rows carry. Bare ``target`` is DELIBERATELY NOT joined on
#: here: it is the loose pointer amendments and notes also use, and a resolution that
#: deliberately HOLDS a row open carries it too (RES-20260820-blind-surfacing-bench-
#: both-halves-executed, ``status: "open"``, verdict "executed-not-consumed") — joining
#: on it would retire rows their own adjudication says are still owed.
_RETIREMENT_LINK_FIELDS = ("consumes", "supersedes")


def _open_work_orders(records: list[dict]) -> list[dict]:
    """The live, OPEN work-orders — status open, not retired by an EVIDENCE-carrying
    resolution (a resolution row that names the order through ``consumes`` or
    ``supersedes`` and whose ``evidence`` is a non-empty ref list).

    THE JOIN FIELD, WIDENED 2026-08-25 (the aging-teeth cure under
    WO-20260825-close-red-override). Reading ``supersedes`` ALONE hid 21 live closures
    and this gate FAILed on every one of them: the 2026-08-20 jubilee resolutions write
    the order's id into ``consumes`` and leave ``supersedes`` an EMPTY STRING, so an
    evidence-carrying retirement adjudicated five days earlier still read as a
    fossilized open row. ``consumes`` is the join field the resolution schema defines —
    ``laplace.engine.engine_ledger`` exists precisely so readers stop re-deriving this join by
    hand (a consumes-only index misses 35 closures; a supersedes-only index misses
    these 21), and its sibling readers (handoff_render, obligation_probe_sweep, the
    wake's account layer) already join on both. The EVIDENCE requirement is unchanged:
    an evidence-less resolution still retires nothing, so its order rides the next wake.

    NOTE (residual, 2026-08-25): ``storyboard.open_work_orders`` still joins on
    ``supersedes`` alone and is now the remaining straggler — this audit no longer
    mirrors it exactly on the ``consumes`` case."""
    # One live-state door. The aging teeth add clocks and ownership; they do not
    # invent a second retirement join beside the pickup loop.
    from laplace.manuscript import storyboard
    return storyboard.live_work_orders(records)


def _wo_class(rec: dict) -> str:
    rb = (rec.get("requested_by") or "").strip().lower()
    return "author" if rb.startswith("gerard") else "machine"


def _work_order_rows(repo: Path, today: date,
                     records: Optional[list[dict]] = None) -> list[Row]:
    records = _read_jsonl(repo / WORK_ORDERS) if records is None else records
    notes = _defer_notes(records)
    rows: list[Row] = []
    for r in _open_work_orders(records):
        rid = r.get("id") or "?"
        origin = r.get("ts")
        du, by = _live_defer(r, notes, today)
        rows.append(Row(
            ledger=WORK_ORDERS, id=rid, cls=_wo_class(r),
            origin=origin, quiet_age=_age_days(origin, today),
            deferred_until=du, deferred_by=by, exempt_reason=None,
            label=(r.get("action") or r.get("what") or "")[:60],
        ))
    return rows


# --------------------------------------------------------------------------- promises
def _collapse_by_id(records: list[dict], origin_field: str
                    ) -> list[tuple[dict, Optional[str]]]:
    """``(latest row, FIRST-seen origin)`` per id — id-less rows kept as-is.

    TWO CLOCKS, DELIBERATELY OPPOSITE. **Disposition is last-wins; the AGE CLOCK is
    first-wins.**

    - *status / direction / labels* come from the LAST line in file order. THE
      RAISE-TIME-STATUS CONVENTION (``laplace.engine.engine_ledger``): a row's stored ``status``
      is written at mint and a later line re-stating the SAME id is the newer word.
      Reading every line independently failed PRM-20260803-hampson-plan on its
      ``status: "open"`` mint line while the same id's later line carries
      ``status: "delivered"`` with evidence (including the CONFIRMED
      SEV-20260807-hampson-plan-delivery verdict). ``laplace.engine.wake``'s account layer
      already collapses this way (``latest[rid] = r`` in file order); the teeth agree.
    - *the origin the clock runs from* comes from the FIRST line that carries one — the
      mint, since these stores are append-only. THE ANTI-GAMING HOLE THIS CLOSES
      (2026-08-25): collapsing the whole row last-wins let a re-mint of an OPEN id buy a
      fresh clock — append the same id again with today's ``date`` and a 40-day-old ask
      reads as one day old, which is exactly the reset this gate's own law forbids
      (module docstring: "Re-minting a row does not buy it a fresh clock; that would be
      exactly the gaming this gate forbids"). Dropping the ``date`` field on the re-mint
      is closed by the same rule: the first-seen origin still stands, so a later dateless
      line cannot demote an aged row to an undateable warn.

    Appended, never mutated — no history is rewritten, the older line still stands."""
    latest: dict[str, dict] = {}
    origin: dict[str, Optional[str]] = {}
    order: list[str] = []
    loose: list[tuple[dict, Optional[str]]] = []
    for r in records:
        rid = r.get("id")
        if not isinstance(rid, str) or not rid:
            loose.append((r, r.get(origin_field)))
            continue
        if rid not in latest:
            order.append(rid)
            origin[rid] = None
        latest[rid] = r
        if origin[rid] is None:
            val = r.get(origin_field)
            if isinstance(val, str) and _parse_iso(val.strip()) is not None:
                origin[rid] = val.strip()
    return [(latest[i], origin[i]) for i in order] + loose


def _promise_rows(repo: Path, today: date,
                  records: Optional[list[dict]] = None) -> list[Row]:
    records = _read_jsonl(repo / PROMISES) if records is None else records
    notes = _defer_notes(records)
    rows: list[Row] = []
    for r, origin in _collapse_by_id(
            [x for x in records if x.get("record") != "defer"], "date"):
        if (r.get("status") or "open") != "open":
            continue
        rid = r.get("id") or "?"
        du, by = _live_defer(r, notes, today)
        exempt = None
        if str(r.get("direction") or "").strip().lower() == "his":
            exempt = ("direction:his — his covenant, carried-not-collected "
                      "(contract/README.md); longer-horizon by nature")
        rows.append(Row(
            ledger=PROMISES, id=rid, cls="author",
            origin=origin, quiet_age=_age_days(origin, today),
            deferred_until=du, deferred_by=by, exempt_reason=exempt,
            label=(r.get("owner") or r.get("ask") or "")[:60],
        ))
    return rows


# --------------------------------------------------------------------------- forks
def _fork_rows(repo: Path, today: date,
               records: Optional[list[dict]] = None) -> list[Row]:
    records = _read_jsonl(repo / FORKS) if records is None else records
    notes = _defer_notes(records)
    rows: list[Row] = []
    for r in records:
        if r.get("record") == "defer":
            continue
        if str(r.get("status") or "").strip() not in _FORK_OPEN_STATUSES:
            continue
        rid = r.get("id") or "?"
        origin = r.get("opened")
        du, by = _live_defer(r, notes, today)
        # the fork-native defer: a non-empty trigger IS the ⚪ condition-defer the legend
        # already sanctions. It has no date, so it satisfies the "named defer" requirement
        # without a defer_until — surfaced as deferred_by="trigger" so the report is honest.
        if du is None:
            trig = (r.get("trigger") or "").strip()
            if trig:
                du, by = "condition", "trigger"
        rows.append(Row(
            ledger=FORKS, id=rid, cls="machine",
            origin=origin, quiet_age=_age_days(origin, today),
            deferred_until=du, deferred_by=by, exempt_reason=None,
            label=(r.get("title") or "").replace("*", "")[:60],
        ))
    return rows


# --------------------------------------------------------------------------- the walk
def audit(repo: Path, today: Optional[date] = None) -> Report:
    """Walk the accumulating ledgers and classify every open row: failing (past its gate,
    undeferred), deferred (carried but named+dated), exempt (his covenant), or fresh."""
    today = today or date.today()
    from laplace.engine import engine_ledger
    from laplace.pipeline.ledger import read_jsonl_diagnosed

    rep = Report()
    for rel in (WORK_ORDERS, PROMISES, FORKS):
        records, residuals = read_jsonl_diagnosed(
            repo / rel, store=rel, required=True)
        rep.records[rel] = [r for r in records if isinstance(r, dict)]
        rep.residuals.extend(residuals)
        if rel in (WORK_ORDERS, PROMISES):
            rep.residuals.extend(engine_ledger.obligation_semantic_diagnostics(
                rep.records[rel], store=rel, path=repo / rel))
    rep.rows.extend(_work_order_rows(repo, today, rep.records[WORK_ORDERS]))
    rep.rows.extend(_promise_rows(repo, today, rep.records[PROMISES]))
    rep.rows.extend(_fork_rows(repo, today, rep.records[FORKS]))
    return rep


def _fmt(r: Row) -> str:
    age = f"{r.quiet_age}d" if r.quiet_age is not None else "?age"
    d = ""
    if r.deferred:
        d = f" defer_until={r.deferred_until} by={r.deferred_by}"
    return f"[{r.cls:7}] {r.id}  age={age} gate={r.gate}d{d}  {r.label}"


def main(argv: Optional[list[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="THE AGING TEETH — open ledger rows past "
                                 "their class max quiet age must carry a dated defer.")
    ap.add_argument("--repo", default=".", help="repo root (default: cwd)")
    ap.add_argument("--today", default=None, help="override today (YYYY-MM-DD) for tests")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    today = _parse_iso(args.today) or date.today()
    rep = audit(repo, today)

    if args.json:
        print(json.dumps({
            "repo": str(repo), "today": today.isoformat(),
            "failing": [r.__dict__ for r in rep.failing],
            "deferred": [r.__dict__ for r in rep.deferred],
            "exempt": [r.__dict__ for r in rep.exempt],
            "undateable": [r.__dict__ for r in rep.undateable],
            "residuals": rep.residuals,
        }, indent=1))
    else:
        print(f"aging_teeth — {repo}  (today={today.isoformat()})")
        if rep.failing:
            print(f"\nFAILING ({len(rep.failing)}) — past the gate, no dated defer, no owner:")
            for r in sorted(rep.failing, key=lambda r: (-(r.quiet_age or 0), r.id)):
                print("  FAIL  " + _fmt(r))
        if rep.deferred:
            print(f"\nDEFERRED ({len(rep.deferred)}) — carried, but named + dated:")
            for r in rep.deferred:
                print("  ok    " + _fmt(r))
        if rep.exempt:
            print(f"\nEXEMPT ({len(rep.exempt)}) — his covenant, carried-not-collected "
                  "(NAMED, never free):")
            for r in rep.exempt:
                print("  his   " + _fmt(r))
        if rep.undateable:
            print(f"\nUNDATEABLE ({len(rep.undateable)}) — no origin date, cannot age "
                  "(reported as a warn, never a gate):")
            for r in rep.undateable:
                print("  warn  " + _fmt(r))
        if rep.residuals:
            print(f"\nINTEGRITY ({len(rep.residuals)}) — the ledger projection is a "
                  "lower bound, never a clean census:")
            for residual in rep.residuals:
                where = (f"line {residual.get('line')}"
                         if residual.get("line") is not None else "store")
                print(f"  FAIL  [integrity] {residual.get('store')} {where}  "
                      f"{residual.get('error', residual.get('defect'))}")

    n_fail = len(rep.failing)
    print(f"VERDICT={'FAIL' if rep.failed else 'PASS'} failing={n_fail} "
          f"residuals={len(rep.residuals)} exempt={len(rep.exempt)} "
          f"deferred={len(rep.deferred)} warns={len(rep.undateable)}")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
