"""The ledger to pool fold: his judgements in a feedback ledger become pool exemplars.

The calibration pool (calibration_pool.json) is the two-sided exemplar set the tension
panel draws from. Until now it was hand-distilled - somebody read the ledger and typed a
line. This module does the same step mechanically, with provenance, so the raw judgement
history becomes a receipt rather than reading material.

The mechanics, once:

  SELECT   Rows whose actor is the author (``AUTHOR_ACTORS`` in manuscript_bridge), which
           this ledger has not already given the pool, and which carry judgement
           substance: an explicit before/after pair, or his words. Machine rows never
           fold. Neither do three kinds of row that carry his actor without carrying his
           verdict - the action-on-a-finding records (deferrals, ratified operations),
           the orchestrator's wrapper records that quote him and then analyse him, and
           the review surface's flag stubs with no comment typed into them.
           ``feedback.jsonl`` is read and never written.

  GATE     What has already folded is the set of row ids the pool records, scoped to the
           ledger they came from. Not a timestamp: every project's ledger is named
           ``feedback.jsonl`` and they share one pool, so a timestamp position keyed by
           name discards the rows of every project whose ledger runs behind the one
           folded last. Ids are exact, and a row the substance rule declined today is
           still reachable if the rule widens tomorrow.

  PLACE    Only where the side is measurable from the row itself. A rewrite whose after
           is materially shorter than its before samples the compression-favouring pole
           of the economy/orientation tension (``against_emptiness``); materially longer
           samples the orientation pole (``against_starvation``). Materially means both
           a length ratio past ``SHORTER_RATIO`` / ``LONGER_RATIO`` and an absolute
           change of at least ``MIN_DELTA_CHARS`` characters - a small edit carries no
           reliable direction. No other side is derivable from a row's bytes, so no
           other side is ever written by machine.

  PEND     Everything the rule does not confidently place goes to
           ``pending_exemplars`` as a verbatim-preserving rendering of the row. The pool
           keeps every one of them whole; the panel prompt takes the most recent under an
           unplaced tag, at the width every exemplar enters at (``panel.MAX_PENDING``,
           ``panel.MAX_EXEMPLAR_CHARS``), so an unplaced verdict reaches the judges
           without a page of one verdict burying twenty samples of the rest.

  APPEND   Existing entries are never rewritten or removed, and a rendering already in
           the pool is never appended twice. A re-run with no new rows writes nothing at
           all, so the fold is idempotent.

Rows of his that carry words the rule declines are counted and named in the return under
``skipped``, so declining something he wrote is never silent either. Rows carrying no
words at all - a status flip, a bare anchor - are not counted: a ledger is mostly those,
and a tally of them reports the ledger's size rather than the fold's judgement.

No model is called here; the fold runs offline and is pure text mechanics.

Run: python3 -m laplace.pipeline.writing_organ.pool_fold <manuscript-dir|ledger.jsonl> [pool.json]
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import pathlib
import re
import sys
import time

from laplace.manuscript.manuscript_bridge import AUTHOR_ACTORS

POOL_PATH = pathlib.Path(__file__).with_name("calibration_pool.json")
REPO_ROOT = source_tree()

#: the element pair whose two poles a length change samples, and its two side keys.
#: Both are checked against the live pool before anything is placed - if the pool does
#: not carry this pair and these sides, every row pends rather than inventing a key.
LENGTH_TENSION = "economy_vs_orientation"
SIDE_SHORTER = "against_emptiness"
SIDE_LONGER = "against_starvation"

#: the confidence rule for a length-derived placement (see PLACE above).
SHORTER_RATIO = 0.75
LONGER_RATIO = 1.34
MIN_DELTA_CHARS = 40

#: kinds whose rows are edits by construction. A row of any kind still places when it
#: carries an explicit ``after`` field beside a non-empty before.
REWRITE_KINDS = frozenset({"rewrite", "author-exemplar"})

#: the fields a judgement's words may arrive in, in the order they are read.
NOTE_FIELDS = ("note", "comment", "text")

#: kinds that record an interaction with him rather than a judgement of his about text -
#: a read being logged, a ratification being granted. Their words are the orchestrator's
#: report, and the pool holds verdicts, not reports of verdicts.
PROCESS_KINDS = frozenset({"author-read", "ratification-grant"})

#: the wrapper the orchestrator writes around a quote of his: an ALL-CAPS declarative
#: header, his words, then machine-composed analysis ("HIS READ OF R2, VERBATIM: '...'
#: CONFIRMED by the orchestrator's own first-chair read (evidence/...): provenance
#: meta-commentary ..."). The general form of PROCESS_KINDS, so a wrapper minted under a
#: kind nobody listed is still not mistaken for his verdict.
WRAPPER_HEAD = re.compile(r"^[^a-z:]{0,80}?[A-Z]{2,}[^a-z:]{0,60}:")

#: a row carrying only words must carry a sentence's worth of them. Under this floor the
#: note is the review surface's own flag text with nothing typed into it ("reader flag
#: - p s1-p4"): it folds a location into the pool and no judgement at all. Measured
#: against both live ledgers the stubs run to three words and the shortest real verdict
#: to seventy-eight, so the floor separates them with room on either side.
MIN_NOTE_WORDS = 6

_LETTER = re.compile(r"[A-Za-z]")


def bookkeeping_records() -> frozenset:
    """Ledger ``record`` types that are ACTIONS on a finding - deferrals, ratified
    operations, intent revokes, the txn journal. His actor stamps them, but their text is
    machine-composed process language ("applied RESPINE meta:contribution_rank via
    set-meta"), which is the opposite of what the pool holds. Taken from the canonical
    ``manuscript_bridge._non_finding_records`` so the two agree, minus ``author-edit``:
    that record IS his rewrite, before and after, and is the pool's strongest signal."""
    from laplace.manuscript.manuscript_bridge import _non_finding_records
    from laplace.pipeline import edits as _ed
    return frozenset(_non_finding_records() - {_ed.RECORD_KIND})

_HEAD = re.compile(r"[:\s(]")


# ------------------------------------------------------------------ row reading


def _rows(ledger: pathlib.Path) -> list[dict]:
    out: list[dict] = []
    for ln in ledger.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def is_author_row(rec: dict) -> bool:
    """True when the row's actor is the author. Three forms occur in the real ledgers:
    an explicit ``by``; a ``source`` whose leading token is his actor name
    (``gerard:the-field-cut``); and the relay form ``<someone>-via-<actor>``. Anything
    else - a machine panel, a reader, a visitor - is not his and never folds."""
    by = str(rec.get("by") or "").strip().lower()
    if by in AUTHOR_ACTORS:
        return True
    head = _HEAD.split(str(rec.get("source") or "").strip().lower(), 1)[0]
    if head in AUTHOR_ACTORS:
        return True
    return any(head.endswith(f"-via-{a}") for a in AUTHOR_ACTORS)


def _note(rec: dict) -> str:
    for f in NOTE_FIELDS:
        v = str(rec.get(f) or "").strip()
        if v:
            return v
    return ""


def _before_after(rec: dict) -> tuple[str, str, bool]:
    """The row's edit, if it carries one: ``(before, after, explicit)``. ``before`` falls
    back to ``scope_source`` (the walk writes the quoted passage there). ``explicit`` is
    True only when the row actually carries an ``after`` field - a quoted passage with no
    replacement is a comment on a passage, not a deletion."""
    before = str(rec.get("before") or rec.get("scope_source") or "").strip()
    after = str(rec.get("after") or "").strip()
    return before, after, "after" in rec


def _words(text: str) -> int:
    """Words in a stretch of text: whitespace-separated tokens carrying a letter. Locator
    debris (a bullet, a pilcrow) is not a word; ``s1-p4`` is one, which is why the floor
    sits above three rather than at one."""
    return sum(1 for t in text.split() if _LETTER.search(t))


def decline_reason(rec: dict, bookkeeping: frozenset | None = None) -> str | None:
    """Why this row is not a judgement, or None when it is one. Five ways a row carries
    his actor without carrying his verdict:

      ``bookkeeping``    an action on a finding - a deferral, a ratified operation, an
                         intent revoke - whose text is machine-composed process language.
      ``process-kind``   a record of an interaction with him (PROCESS_KINDS).
      ``wrapper``        the orchestrator quoting him and then analysing him
                         (WRAPPER_HEAD).
      ``stub``           a flag with no comment typed into it (MIN_NOTE_WORDS).
      ``no-judgement``   no edit and no words at all - a status change, a bare anchor.

    An edit clears the last of these on its own: a before/after pair is a judgement in
    full whatever its note says, and a rewrite of two words is still a rewrite. Short of
    an edit the floor counts the passage he quoted as well as the words he typed - three
    words on a paragraph he pulled out is a verdict, three words on a bare anchor is not.
    """
    bookkeeping = bookkeeping_records() if bookkeeping is None else bookkeeping
    if str(rec.get("record") or "") in bookkeeping:
        return "bookkeeping"
    if str(rec.get("kind") or "") in PROCESS_KINDS:
        return "process-kind"
    note = _note(rec)
    if note and WRAPPER_HEAD.match(note):
        return "wrapper"
    before, _after, explicit = _before_after(rec)
    if (explicit and before) or (str(rec.get("kind") or "") in REWRITE_KINDS and before):
        return None
    if not note:
        return "no-judgement"
    return "stub" if _words(f"{before} {note}") < MIN_NOTE_WORDS else None


def has_substance(rec: dict, bookkeeping: frozenset | None = None) -> bool:
    """True when the row carries judgement, not bookkeeping: an edit, or his words."""
    return decline_reason(rec, bookkeeping) is None


def _where(rec: dict) -> str:
    a = rec.get("anchor")
    lbl = (a.get("section") or a.get("where") or "") if isinstance(a, dict) else (a or "")
    return str(lbl or rec.get("section") or rec.get("scope") or "").strip()


def render_row(rec: dict) -> str:
    """A compact rendering of the row that preserves his words verbatim: the quoted
    passage, his replacement, and his note, under the anchor the judgement sits on."""
    before, after, explicit = _before_after(rec)
    parts: list[str] = []
    if before and after:
        parts.append(f"'{before}' -> '{after}'")
    elif before and explicit:
        parts.append(f"cut: '{before}'")
    elif before:
        parts.append(f"on: '{before}'")
    elif after:
        parts.append(f"added: '{after}'")
    note = _note(rec)
    if note:
        parts.append(note)
    body = " - ".join(parts)
    where = _where(rec)
    return f"[{where}] {body}" if where else body


# ------------------------------------------------------------------ placement


def place_side(rec: dict) -> str | None:
    """The pool side this row samples, or None when the row's bytes do not decide it.
    The only mechanical signal is length: a materially shorter replacement samples the
    pole that argues against emptiness, a materially longer one the pole that argues
    against starvation. Anything else pends for a human read."""
    before, after, explicit = _before_after(rec)
    if not explicit or not before:
        return None
    lb, la = len(before), len(after)
    if lb - la >= MIN_DELTA_CHARS and la <= SHORTER_RATIO * lb:
        return SIDE_SHORTER
    if la - lb >= MIN_DELTA_CHARS and la >= LONGER_RATIO * lb:
        return SIDE_LONGER
    return None


def _sides_available(pool: dict) -> bool:
    pairs = {e.get("pair") for e in pool.get("elements") or [] if isinstance(e, dict)}
    ex = pool.get("exemplars") or {}
    return LENGTH_TENSION in pairs and SIDE_SHORTER in ex and SIDE_LONGER in ex


# ------------------------------------------------------------------ pool state


def _provenance(pool: dict) -> dict:
    """The pool's provenance block as a dict carrying ``folds``. The hand-written pool
    holds a prose provenance string; the first fold promotes it to
    ``{"note": <that string>, "folds": []}`` so his words survive untouched."""
    prov = pool.get("provenance")
    if isinstance(prov, str):
        prov = {"note": prov, "folds": []}
        pool["provenance"] = prov
    elif not isinstance(prov, dict):
        prov = {"folds": []}
        pool["provenance"] = prov
    prov.setdefault("folds", [])
    return prov


def _pool_entries(pool: dict):
    """Every exemplar object in the pool, placed and pending alike. Hand-typed strings
    are skipped - they carry no provenance to read."""
    for entries in (pool.get("exemplars") or {}).values():
        for e in entries or []:
            if isinstance(e, dict):
                yield e
    for e in pool.get("pending_exemplars") or []:
        if isinstance(e, dict):
            yield e


def _pool_folds(pool: dict) -> list[dict]:
    prov = pool.get("provenance")
    return [f for f in ((prov.get("folds") or []) if isinstance(prov, dict) else [])
            if isinstance(f, dict)]


def _folded_ids(pool: dict, lid: str) -> set[str]:
    """The row ids this ledger has already given the pool. Scoped by ledger identity
    because two projects can mint the same id and neither may mask the other. A record
    written before identity was kept names no ledger; it counts against every ledger,
    which risks declining a row rather than folding one twice."""
    ids: set[str] = set()
    for e in _pool_entries(pool):
        if str(e.get("ledger") or lid) == lid:
            ids.update(str(i) for i in e.get("from") or [])
    for f in _pool_folds(pool):
        if str(f.get("ledger") or lid) == lid:
            ids.update(str(i) for i in f.get("row_ids") or [])
    return ids


def _pool_texts(pool: dict) -> set[str]:
    """Every exemplar line already in the pool. A verdict logged twice - the same flag
    raised on the same paragraph on two days - is one sample, not two."""
    out: set[str] = set()
    for entries in (pool.get("exemplars") or {}).values():
        for e in entries or []:
            t = e.strip() if isinstance(e, str) else str(e.get("text") or "").strip()
            if t:
                out.add(t)
    for e in pool.get("pending_exemplars") or []:
        t = e.strip() if isinstance(e, str) else str(e.get("text") or "").strip()
        if t:
            out.add(t)
    return out


def ledger_id(ledger: pathlib.Path) -> str:
    """The ledger's identity in the pool: its path from the repo root. The file name
    identifies nothing - every project's ledger is called ``feedback.jsonl`` - and the
    absolute path identifies the machine as well as the ledger. Outside the repo the
    absolute path is all there is, and stands in."""
    p = pathlib.Path(ledger).resolve()
    try:
        return p.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def resolve_ledger(source: str | pathlib.Path) -> pathlib.Path | None:
    """A ledger path, a manuscript directory, or a project directory - all resolve to
    the one ``feedback/feedback.jsonl``."""
    p = pathlib.Path(source)
    if p.is_file():
        return p
    for rel in ("feedback/feedback.jsonl", "manuscript/feedback/feedback.jsonl"):
        c = p / rel
        if c.is_file():
            return c
    return None


# ------------------------------------------------------------------ the fold


def fold(source: str | pathlib.Path, pool_path: str | pathlib.Path | None = None) -> dict:
    """Fold his judgement rows from one ledger into the calibration pool.

    Returns ``{ok, folded, placed, pending, position, skipped}`` - folded is the number
    of his rows consumed this run, placed and pending how they landed, position the
    newest row timestamp this ledger has given the pool. ``skipped`` tallies by reason
    every row of his in the ledger that the substance rule declines; it is a standing
    report of what the ledger holds, so it reads the same on a run that folds nothing.
    Writes the pool only when something folded; the ledger is never written.
    """
    ledger = resolve_ledger(source)
    if ledger is None:
        return {"ok": False, "error": f"no feedback ledger under {source}",
                "folded": 0, "placed": 0, "pending": 0, "position": ""}
    lid = ledger_id(ledger)
    pool_path = pathlib.Path(pool_path or POOL_PATH)
    pool = json.loads(pool_path.read_text(encoding="utf-8"))

    prov = _provenance(pool)
    folds = prov["folds"]
    position = max((str(f.get("max_row_ts") or "") for f in folds
                    if str(f.get("ledger") or "") == lid), default="")
    seen = _folded_ids(pool, lid)
    texts = _pool_texts(pool)
    sides_ok = _sides_available(pool)

    placed_entries: dict[str, list[dict]] = {}
    pending_entries: list[dict] = []
    folded_ids: list[str] = []
    folded_ts: list[str] = []
    no_id = 0
    skipped: dict[str, int] = {}
    bookkeeping = bookkeeping_records()
    for rec in _rows(ledger):
        if not is_author_row(rec):
            continue
        rid = str(rec.get("id") or "").strip()
        if rid and rid in seen:
            continue
        why = decline_reason(rec, bookkeeping)
        if why:
            if why != "no-judgement":
                skipped[why] = skipped.get(why, 0) + 1
            continue
        if not rid:
            no_id += 1
            continue
        text = render_row(rec)
        if text in texts:
            skipped["duplicate"] = skipped.get("duplicate", 0) + 1
            continue
        entry = {"text": text, "from": [rid], "ts": str(rec.get("ts") or ""),
                 "ledger": lid}
        side = place_side(rec) if sides_ok else None
        if side:
            placed_entries.setdefault(side, []).append(entry)
        else:
            pending_entries.append(entry)
        folded_ids.append(rid)
        folded_ts.append(str(rec.get("ts") or ""))
        seen.add(rid)
        texts.add(text)

    n_placed = sum(len(v) for v in placed_entries.values())
    n_pending = len(pending_entries)
    if not folded_ids:
        return {"ok": True, "folded": 0, "placed": 0, "pending": 0, "position": position,
                "ledger": str(ledger), "ledger_id": lid, "skipped": skipped,
                "skipped_without_id": no_id,
                "detail": "no unfolded author judgement rows"}

    position = max([position] + [t for t in folded_ts if t])
    for side, entries in placed_entries.items():
        pool["exemplars"].setdefault(side, []).extend(entries)
    if pending_entries:
        pool.setdefault("pending_exemplars", []).extend(pending_entries)
    folds.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                  "ledger": lid,
                  "max_row_ts": position,
                  "rows": len(folded_ids),
                  "row_ids": folded_ids})
    pool_path.write_text(json.dumps(pool, ensure_ascii=False, indent=1) + "\n",
                         encoding="utf-8")
    return {"ok": True, "folded": len(folded_ids), "placed": n_placed,
            "pending": n_pending, "position": position, "ledger": str(ledger),
            "ledger_id": lid,
            "sides": {s: len(v) for s, v in sorted(placed_entries.items())},
            "skipped": skipped, "skipped_without_id": no_id}


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[-1])
        return 2
    r = fold(argv[0], argv[1] if len(argv) > 1 else None)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
