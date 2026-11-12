"""The places census is a typed, live map — never a fourth account or a tollbooth."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from laplace.web import front_places
from laplace.engine import wake


def test_apex_counts_are_the_canonical_account_partitions() -> None:
    got = front_places._census_apex()
    canonical = wake.account(Path(__file__).resolve().parents[1])
    chips = {c["unit"]: c["n"] for c in got["chips"]}

    assert chips == {
        "orders open": canonical["work_orders"]["open"],
        "orders deferred": canonical["work_orders"]["deferred"],
        "order defers lapsed": canonical["work_orders"]["lapsed_deferred"],
        "promises open": canonical["promises"]["open"],
        "promises deferred": canonical["promises"]["deferred"],
        "promise defers lapsed": canonical["promises"]["lapsed_deferred"],
    }
    assert "laplace.engine.wake.account" in got["source"]


def test_apex_cracks_on_the_physical_class_not_an_enumerated_defect_list(
        monkeypatch) -> None:
    empty = {"open": 0, "deferred": 0, "lapsed_deferred": 0}
    account = {
        "work_orders": empty, "promises": empty,
        "defects": [{
            "integrity_class": "physical-store-integrity",
            "defect": "future-reader-defect", "store": "work_orders",
            "path": "/" + "x" * 10_000,
        }],
    }
    monkeypatch.setattr(front_places, "_canonical_account", lambda: account)
    got = front_places._census_apex()
    assert got["cracked"] and got["residuals"]["count"] == 1
    assert len(got["residuals"]["first"][0]["path"]) <= 240


def test_a_cold_seat_census_schedules_replay_instead_of_blocking(monkeypatch) -> None:
    """The first receipt used to call the ~2s snapshot inline — cache warm, cold tollbooth."""
    from laplace.representation import atlas_bridge

    scheduled = []

    class DeferredThread:
        def __init__(self, *, target, **_kwargs):
            self.target = target

        def start(self):
            scheduled.append(self.target)

    monkeypatch.setattr(front_places, "_SEATS_CACHE", {})
    monkeypatch.setattr(atlas_bridge, "drift_token", lambda: {
        "cursor": 12, "head_record_digest": "sha256:tip"})
    monkeypatch.setattr(atlas_bridge, "snapshot",
                        lambda: (_ for _ in ()).throw(AssertionError("inline replay")))
    monkeypatch.setattr(front_places.threading, "Thread", DeferredThread)

    t0 = time.perf_counter()
    got = front_places._census_seats()
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.1
    assert scheduled, "the recount was neither served nor scheduled"
    assert got["refresh_after_ms"] and "warming" in got["chips"][0]["unit"]


def test_cached_jsonl_projection_names_malformed_rows_and_partial_tail(tmp_path) -> None:
    path = tmp_path / "inventory.jsonl"
    path.write_text('{"id":"good"}\nnot-json\n{"id":', encoding="utf-8")

    got = front_places._cached(path, "fixture", lambda rows: len(rows))

    assert got["value"] == 1
    assert got["malformed_rows"][0]["line"] == 2
    assert got["partial_tail"] is True


def test_help_and_refresh_are_renders_of_the_places_contract() -> None:
    html = (Path(__file__).resolve().parents[1] / "src" / "laplace" /
            "web" / "front_door.html").read_text(encoding="utf-8")

    assert "<dt>1–6</dt>" not in html, "the retired hand-maintained key map returned"
    assert "function renderPlaceKeys()" in html and "placeKeyOrder()" in html
    assert 's.addEventListener("atlas:changed", placesMoved)' in html
    assert 's.addEventListener("rows:" + n, placesMoved)' in html
    assert 's.addEventListener("source:changed", placesMoved)' in html
    assert "startPlacesWatch();" in html


def test_banked_door_census_carries_its_age_in_the_default_register(
    tmp_path: Path, monkeypatch,
) -> None:
    from laplace.web import front_door

    bank = tmp_path / front_door._SELFTEST_BANK
    bank.write_text(
        json.dumps({
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "doors": 12,
            "down": 0,
            "detail": [],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(front_door, "_repo_root", lambda: tmp_path)

    got = front_places._census_selftest()
    chips = {chip["unit"]: chip for chip in got["chips"]}

    assert "hours since census" in chips
    assert chips["hours since census"]["n"] == 0.0
