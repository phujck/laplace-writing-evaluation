"""The seat fabric (laplace.engine.seats): identity from ROWS, not from a title.

WO-20260823-seat-fabric-discovery. The Superego charter sends a successor to
``contract/seats.jsonl`` to discover its peer; until this organ that store did not
exist, so founding fell back to the title convention and three windows were bitten
addressing a title that named a day. Four invariants:

1. founding BANKS a typed row through the journal seam (never a raw append).
2. the address (``session_ref``) and the name (``title``) are DIFFERENT fields - that
   separation is the whole cure.
3. re-founding APPENDS; ``current_seats`` is latest-per-seat, so history survives and
   the present is unambiguous.
4. an absent store is an empty list, never an exception - a successor must be able to
   read "no seat has founded itself" without crashing.
"""
from __future__ import annotations

import json
from pathlib import Path

from laplace.engine import seats


def test_founding_banks_a_typed_row_through_the_journal(tmp_path):
    row = seats.found_seat(tmp_path, "ego", "eigen-ego-2f81c4", "eigen-ego-accounting-day")

    store = tmp_path / "contract" / "seats.jsonl"
    banked = [json.loads(l) for l in store.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(banked) == 1
    assert banked[0]["record"] == "seat" and banked[0]["seat"] == "ego"
    assert banked[0]["session_ref"] == "eigen-ego-2f81c4"
    assert banked[0]["relay_state"] == "live"
    # the one stamp law owns the founding time: bank_row wrote it, nobody else
    assert banked[0]["ts"].endswith("Z") and banked[0]["ts"].startswith("20")
    assert row["founded"] == banked[0]["ts"], "current_seats must serve founded FROM ts"

    # the journal saw the bank (the seam, not a raw append)
    journal = [json.loads(l) for l in
               (tmp_path / "contract" / "journal.jsonl").read_text(encoding="utf-8").splitlines()
               if l.strip()]
    banks = [j for j in journal if j.get("record") == "bank" and j.get("store") == seats.STORE]
    assert {j["phase"] for j in banks} == {"begin", "done"}, banks


def test_the_address_is_not_the_title(tmp_path):
    """Titles are not addresses: a peer routes on session_ref, and reading the title
    as an address is exactly the defect this store exists to end."""
    seats.found_seat(tmp_path, "superego", "eigen-superego-9ab3", "the judge, accounting day")
    (seat,) = seats.current_seats(tmp_path)
    assert seat["session_ref"] == "eigen-superego-9ab3"
    assert seat["title"] == "the judge, accounting day"
    assert seat["session_ref"] != seat["title"]


def test_refounding_appends_and_the_latest_row_wins(tmp_path):
    seats.found_seat(tmp_path, "ego", "eigen-ego-old", "the outgoing ego")
    seats.found_seat(tmp_path, "superego", "eigen-superego-1", "the judge")
    seats.found_seat(tmp_path, "ego", "eigen-ego-new", "the successor ego",
                     relay_state="relayed")

    store = tmp_path / "contract" / "seats.jsonl"
    assert len(store.read_text(encoding="utf-8").strip().splitlines()) == 3, (
        "a re-founding must APPEND - the store is the seat's history")
    current = seats.current_seats(tmp_path)
    assert [s["seat"] for s in current] == ["ego", "superego"], "sorted, latest-per-seat"
    ego = current[0]
    assert ego["session_ref"] == "eigen-ego-new" and ego["relay_state"] == "relayed"


def test_an_unfounded_store_reads_as_no_seats(tmp_path):
    assert seats.current_seats(tmp_path) == []
    (tmp_path / "contract").mkdir()
    (tmp_path / "contract" / "seats.jsonl").write_text("", encoding="utf-8")
    assert seats.current_seats(tmp_path) == []


def test_a_torn_append_costs_that_line_only(tmp_path):
    """The one way to poison this single-writer store is a kill mid-append. The other
    seats must still be discoverable (the torn line is loud one level down, in the
    journal's begin-without-done row)."""
    seats.found_seat(tmp_path, "ego", "eigen-ego-1", "the ego")
    with open(tmp_path / "contract" / "seats.jsonl", "a", encoding="utf-8") as f:
        f.write('{"record": "seat", "seat": "super\n')
    seats.found_seat(tmp_path, "interface", "eigen-interface-1", "the interface seat")
    assert [s["seat"] for s in seats.current_seats(tmp_path)] == ["ego", "interface"]
