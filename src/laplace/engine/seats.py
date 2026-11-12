"""seats.py - the standing seats as ROWS: discovery from the store, never from a title.

Why (2026-08-23, WO-20260823-seat-fabric-discovery, the successor judge's seating
exchange): the relay banks state faithfully and ADDRESSES none of it. The Superego
charter already sends a successor to discover its peer through "the seat rows in
contract/seats.jsonl" - a store that did not exist - so every founding fell back to the
TITLE convention (``eigen-ego-<day-name>``), and three windows were bitten addressing a
title that named a DAY instead of a SEAT. Titles are not addresses; rows are.

The store: ``contract/seats.jsonl``, append-only, one JSON line per founding::

    {"record": "seat", "seat", "session_ref", "title", "relay_state", "ts"}

Founding APPENDS - a re-founding is a new row, never an edit - so the store is the
seat's history and ``current_seats`` (latest-per-seat) is its present.

TWO DELIBERATE READINGS of the ruled row shape, named here so the judge rules against
the row instead of guessing:

* ``founded`` is not a banked field. ``journal.bank_row`` owns the stamp outright (the
  one stamp law): it writes true UTC ``ts`` at write time and demotes any timestamp the
  caller brought. A second founding timestamp would be exactly the second dialect that
  law was minted to kill. ``current_seats`` serves ``founded`` FROM that ``ts``, so the
  projection carries the ruled name and the store carries one clock.
* the row carries no ``id``: the seat name is the key, and latest-per-seat is the whole
  read. The cost is a journal bank line reading ``row_id "?"``; the cure for a torn
  append is the journal's own begin-without-done row, not a second identifier here.

A malformed line is skipped rather than served: this store has exactly one writer, so
the only way to produce one is a kill mid-append, and that kill is already loud one
level down (``python3 -m laplace.core.records.journal --recover``).
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import json
from pathlib import Path
from typing import Any

#: repo-relative, as ``journal.bank_row`` takes it
STORE = "contract/seats.jsonl"


def _root(repo_root: Path | str | None = None) -> Path:
    return Path(repo_root) if repo_root else source_tree()


def found_seat(repo_root: Path | str | None, seat: str, session_ref: str, title: str,
               *, relay_state: str = "live") -> dict[str, Any]:
    """Bank one seat row and return it as banked (``ts`` included).

    ``session_ref`` is how a peer ADDRESSES this seat (the live session handle), and
    ``title`` is only what it calls itself - the whole point of the row is that the two
    are different fields. ``relay_state`` is ``live`` at founding; a seat handing over
    re-founds with ``relay_state='relayed'``, which is why it is a parameter and not a
    constant.
    """
    from laplace.core.records import journal
    # the first founding mints the store: bank_row appends and never creates the dir,
    # and the journal line lands beside it in the same contract/ directory.
    (_root(repo_root) / STORE).parent.mkdir(parents=True, exist_ok=True)
    row = {"record": "seat", "seat": str(seat), "session_ref": str(session_ref),
           "title": str(title), "relay_state": str(relay_state)}
    journal.bank_row(STORE, row, root=repo_root)
    banked = current_seats(repo_root)
    return next((r for r in banked if r["seat"] == str(seat)), row)


def current_seats(repo_root: Path | str | None = None) -> list[dict[str, Any]]:
    """The present seats: the latest row per seat, sorted by seat name.

    An absent store is an empty list - no seat has founded itself yet, which is a
    state a successor must be able to read without an exception.
    """
    path = _root(repo_root) / STORE
    latest: dict[str, dict] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("record") == "seat" and r.get("seat"):
                latest[str(r["seat"])] = r
    return [{"seat": name,
             "session_ref": latest[name].get("session_ref"),
             "title": latest[name].get("title"),
             "relay_state": latest[name].get("relay_state"),
             "founded": latest[name].get("ts")}
            for name in sorted(latest)]
