"""The atlas board's own teeth — the surface his ATLAS-S0 walk lands on.

Written 2026-08-25 by the interface seat, after the board was found serving 218,723 bytes
containing ZERO anchors and ZERO buttons: a reader could enter the largest surface the
engine serves and not leave it. These tests exist so that specific class of defect —
a surface that cannot be navigated, or that renders a stale receipt as live — fails here
instead of failing at his walk.

Runtime law: /usr/bin/python3, system + user site, read-only against every store.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src"))


def _board():
    spec = importlib.util.spec_from_file_location(
        "laplace_atlas_board_test", ROOT / "scripts" / "atlas_board.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_board_authored_route_handle_names_the_mounted_planes():
    """The coarse handle is part of the implementation: when the surface grows, its handle must
    mutate too, or semantic descent can bank fresh hashes around an obsolete description."""
    from laplace.engine import self_shard

    leaf = self_shard.shard_file(ROOT, ROOT / "scripts" / "atlas_board.py")
    assert {"bench", "health", "observability", "diffusion"} <= set(leaf["keywords"])


@pytest.fixture(scope="module")
def board():
    return _board()


@pytest.fixture(scope="module")
def payload(board):
    return board.build()


# ----------------------------------------------------------------- navigation

def test_served_register_can_be_left(board, payload):
    """The cure for the dead end: the served board carries a way back to the front door.

    Regression guard for the measured defect — 218,723 bytes, 0 anchors, 0 buttons.
    """
    html = board.render_html(payload, home="/front")
    assert 'href="/front"' in html, "the served board has no route back to the front door"
    assert html.count("<a ") >= 2, "a board with one anchor is still nearly a cul-de-sac"


def test_standalone_register_claims_no_front_door(board, payload):
    """The file register has no server to return to and must not pretend otherwise."""
    html = board.render_html(payload, home=None)
    assert 'href="/front"' not in html
    assert "no front door" in html, "the standalone file must say why there is no way back"


def test_section_index_is_derived_and_cannot_drift(board, payload):
    """h2() is the ONLY door into the section register, so the index is exactly the
    sections that rendered — same set, same order. An index entry that names a section
    not on the page, or a section the index cannot reach, is the drift this forbids."""
    html = board.render_html(payload, home="/front")
    ids = re.findall(r'<h2 id="([^"]+)"', html)
    toc = re.search(r'<div class="toc">(.*?)</div>', html, re.S)
    assert toc, "the board renders no section index"
    links = re.findall(r'href="#([^"]+)"', toc.group(1))
    assert ids == links, f"index drifted from sections: {ids!r} vs {links!r}"
    assert len(set(ids)) == len(ids), "two sections share an anchor id"


def test_every_class_used_is_styled(board, payload):
    """The board ships one <style> block and no external asset. A class used but never
    styled is how the anchor bug hid in plain sight: the CSS declared a{color:#7fb3ff}
    for anchors the renderer could not emit."""
    html = board.render_html(payload, home="/front")
    css = html[:html.find("</style>")]
    used = set()
    for chunk in re.findall(r'class="([a-z][a-z0-9 _-]*)"', html):
        used |= set(chunk.split())
    missing = sorted(c for c in used if f".{c}" not in css)
    assert not missing, f"classes used but never styled: {missing}"


# ------------------------------------------------------------------- liveness

def test_liveness_counts_are_internally_consistent(payload):
    """His question: live and necessary vs simply banked and never returned to.

    A row never touched at all is necessarily also never adjudicated — if that ever
    inverts, the predicate has been miswired and the headline number is a lie.
    """
    c = payload["liveness"]["counts"]
    assert c["never_touched_at_all"] <= c["never_adjudicated"] <= c["open_carried"]
    assert c["loud_but_undecided"] <= c["never_adjudicated"]
    assert c["never_touched_at_all"] + c["loud_but_undecided"] == \
        c["never_adjudicated"], "untouched and loud must partition, never overlap"


def test_liveness_names_its_predicate_and_sources(payload):
    """Renders-of-rows: a pane that partitions his ledgers must say, on the surface,
    what rule it partitioned them by — the answer moves from 33 rows to 2 depending on
    whether a note counts as returning to something."""
    ln = payload["liveness"]
    assert "adjudicated" in ln["predicate"]
    assert "ledger_age_audit" in ln["source"], "the canonical classifier must be named"
    assert ln["staleness"], "a pane without a staleness law is a stale pane waiting"
    assert "residuals" in ln and "cracked" in ln, (
        "malformed liveness rows must be a named residual, never a smaller sure count")


def test_liveness_rows_carry_their_evidence(payload):
    """Every row must carry the counts a reader would need to argue with it."""
    for row in payload["liveness"]["rows"]:
        for field in ("id", "quiet_age", "touches", "defers", "adjudications", "notes",
                      "defer_chain", "max_cohort"):
            assert field in row, f"liveness row missing {field}: {row.get('id')}"


# ------------------------------------------------------ bench / health / observability

def test_bench_plane_is_an_exact_projection_of_named_receipts(payload):
    """The walk may render measurements; it may not improve or rederive them."""
    demand = json.loads((ROOT / "evidence/ATLAS_BENCH_2026-08-24/"
                                "DEMAND_INVENTORY.json").read_text())
    recall = json.loads((ROOT / "evidence/ATLAS_UPDOWN_V0_2026-08-24/"
                                "REPORT_bge-small-en-v1.5.json").read_text())
    pane = payload["bench"]
    assert pane["errors"] == []
    assert pane["demand"]["queries_total"] == demand["totals"]["queries_total"]
    assert pane["demand"]["queries_unresolved_provenance"] == \
        demand["totals"]["queries_unresolved_provenance"]
    assert pane["demand"]["aspects"] == [
        {"aspect_class": row.get("aspect_class"), "count": row.get("count"),
         "coverage_hint": row.get("current_coverage_hint"),
         "coverage_basis": row.get("coverage_basis"),
         "measured_fraction": row.get("measured_fraction")}
        for row in demand["aspect_classes"]
    ]
    assert pane["recall"]["descent_hit_at_1"] == recall["headline"]["descent_hit_at_1"]
    assert pane["recall"]["historic_misses_reasked"] == \
        recall["headline"]["historic_misses_reasked"]


def test_storage_measurement_keeps_its_non_authorizing_scope(payload):
    """A size receipt is not permission to migrate; the amendment must ride beside it."""
    receipt = json.loads((ROOT / "evidence/ATLAS_HIVED_STORAGE_2026-08-25/"
                                 "CURRENT_SOURCE_REATTACK_RECEIPT.json").read_text())
    amendment = json.loads((ROOT / "evidence/ATLAS_HIVED_STORAGE_2026-08-25/"
                                   "NAMING_AND_MEASUREMENT_AMENDMENT.json").read_text())
    storage = payload["bench"]["storage"]
    assert storage["thin_ledger_bytes"] == receipt["candidate"]["thin_ledger_bytes"]
    assert storage["tree_allocated_bytes"] == receipt["candidate"]["tree_allocated_bytes"]
    assert storage["equivalence"]["reachability_status"] == \
        receipt["equivalence"]["reachability_status"]
    assert storage["measurement_scope"] == amendment["authorization_scope"]
    assert storage["production_mutated"] is False


def test_health_plane_uses_the_latest_banked_wake_measurement(payload):
    """The board reads the last banked check; it never times a wake on a GET."""
    rows = [json.loads(line) for line in
            (ROOT / "holdout/STRANGER_BENCH_VERDICTS.jsonl").read_text().splitlines()
            if line.strip()]
    latest = [r for r in rows if r.get("record") == "check"
              and r.get("check") == "sb6-budget"][-1]
    budget = payload["health"]["wake_budget"]
    assert budget["latest_banked_seconds"] == latest.get("seconds")
    assert budget["latest_banked_status"] == latest.get("status")
    assert budget["latest_banked_at"] == latest.get("ts")
    assert payload["health"]["in_flight"]["acts_total"] >= \
        len(payload["health"]["in_flight"]["acts"])
    assert "banked-with-age" in payload["health"]["staleness"]


def test_diffusion_instrument_serves_exact_banked_samples(board, payload):
    """The slider is a view over the receipt, not a browser-side substitute eigensolve."""
    receipt = json.loads((ROOT / "evidence/DIFFUSION_SCISSORS_2026-08-25/"
                                 "RECEIPT.json").read_text())
    instrument = payload["observability"]["instruments"][0]
    expected = [{"t": int(float(t)), **values}
                for t, values in receipt["results"]["per_t"].items()]
    expected.sort(key=lambda row: row["t"])
    assert instrument["series"] == expected
    assert instrument["dial_values"] == receipt["dials"]["t_sweep"]
    assert instrument["fidelity_preview_vs_real_ari"] == \
        receipt["fidelity_preview_vs_real_ari"]
    assert instrument["status"] == "CURRENT"
    assert instrument["custody"]["status"] == "PASS"
    assert {row["status"] for row in instrument["inputs"]} == {"PASS"}
    assert instrument["class"] == "INSTRUMENT"
    assert instrument["channel_class"] == "DERIVED"
    assert instrument["reader"] and instrument["preimage"] and instrument["retirement"]
    assert instrument["census"]["organ"] == "instrument:diffusion-scissors/1"
    assert instrument["receipt_content_handle"].startswith("sha256:")
    assert "does not promote" in instrument["non_claim"]
    html = board.render_html(payload, home="/front")
    assert 'class="diffusion-dial"' in html
    assert "DERIVED" in html and "receipt content handle" in html
    assert "fidelity preview↔real ARI" in html and "census" in html
    assert "NON-CLAIM" in html and "NON-AUTHORIZING MEASUREMENT" in html
    assert ("DIFFUSION_SCISSORS_2026-08-25/scissors.py" in html), (
        "the instrument receipt must name its own renewal act, not the notes pour")
    assert ("ATLAS_BENCH_2026-08-24/demand_inventory.py" in html), (
        "the demand receipt must name its own renewal act")


@pytest.fixture
def clean_cache():
    """_ATLAS_CACHE lives for the life of the server process, which is right in
    production and wrong in a suite: without this, one test's banked key leaves a
    background rebuild in flight and the next test's `building` guard silently
    suppresses the very rebuild it is trying to observe. Ask me how I know.
    """
    from laplace.web import front_door as fd

    for _ in range(100):                            # let any in-flight refresh land
        if not fd._ATLAS_CACHE.get("building"):
            break
        time.sleep(0.1)
    saved = dict(fd._ATLAS_CACHE)
    fd._ATLAS_CACHE.clear()
    yield fd
    for _ in range(100):
        if not fd._ATLAS_CACHE.get("building"):
            break
        time.sleep(0.1)
    fd._ATLAS_CACHE.clear()
    fd._ATLAS_CACHE.update(saved)


# ---------------------------------------------------------------- the cache key

def test_cache_key_covers_every_store_the_board_reads():
    """THE GUARD THAT MATTERS MOST, and the reason this file exists.

    /front/atlas serves a drift-keyed receipt (17ms warm, against ~9s to build). If the
    key misses a store the board reads, the door serves a frozen board while still
    rendering "LIVE (chain verified on this read)" — stale presented as live, on the
    surface his walk lands on.

    So the read set is DERIVED here, by tracing build() under a sys.addaudithook, and
    compared against the key's declared sources. Add a pane with a new source and forget
    the key, and this fails. It is also the tripwire for codex's storage migration: when
    the conceptric layout moves, this test says so.
    """
    from laplace.web import front_door as fd

    opened: set[str] = set()
    root = str(ROOT)

    def hook(event, args):
        if event in ("open", "os.open") and args:
            target = args[0]
            if isinstance(target, (str, bytes, os.PathLike)):
                try:
                    path = os.path.abspath(os.fsdecode(target))
                except Exception:  # noqa: BLE001
                    return
                if (path.startswith(root) and not path.endswith((".py", ".pyc"))
                        and "/__pycache__/" not in path):
                    opened.add(os.path.relpath(path, root))

    sys.addaudithook(hook)
    _board().build()

    # only the accumulating stores and instrument custody inputs matter; transient
    # reads are not state.  Instrument paths are derived from their receipt rather than
    # repeated here, so a new generation cannot silently leave the key behind.
    read = {p for p in opened if p.endswith((".jsonl", ".json", ".npy", ".sha256"))}
    declared = set(fd._atlas_repo_sources())
    missed = read - declared
    assert not missed, (
        "build() reads stores the cache key does not cover, so the board can serve a "
        f"frozen render as live: {sorted(missed)}. Add them to _ATLAS_REPO_SOURCES.")


def test_cache_key_derives_instrument_inputs_from_the_receipt():
    from laplace.web import front_door as fd
    from laplace.representation import instrument_serve

    registered = set(instrument_serve.source_paths(ROOT))
    declared = set(fd._atlas_repo_sources())
    key = {part[0] for part in fd._atlas_drift_key() if isinstance(part, tuple)}
    assert registered <= declared
    assert registered <= key


def test_cache_key_uses_the_declared_drift_token_not_a_file_path():
    """The conceptric half of the key must be codex's DECLARED token, never its filenames.

    This is the migration tripwire. The board was briefly keyed on
    conceptric.sqlite3 + -wal; had that survived codex's move to hived storage, those
    paths would have stopped moving and the board would have frozen while still rendering
    "LIVE (chain verified on this read)". atlas_bridge.drift_token() is identity-stable
    across v1 -> hived-v2, so the key survives the migration by construction.
    """
    from laplace.representation import atlas_bridge as ab
    from laplace.web import front_door as fd

    key = dict((p[0], p) for p in fd._atlas_drift_key() if isinstance(p, tuple))
    assert "head" in key, "the drift key does not cover git HEAD"
    assert "conceptric" in key, "the drift key does not cover the conceptric store"
    assert not any("sqlite" in str(p) for p in key), (
        "the key names a conceptric FILE — it must key on drift_token(), which survives "
        "the storage migration; a path-keyed board freezes silently when the layout moves")

    # The suite sandboxes the store root, so an absent store is the NORMAL case here.
    # Both branches are asserted, because the unreachable branch is the dangerous one:
    # if it collapsed to the same key as a reachable store, the board would pin itself
    # on the last good receipt and go on calling it live.
    try:
        token = ab.drift_token()
    except Exception:                                    # noqa: BLE001
        assert key["conceptric"][1] == "UNREACHABLE", (
            "an unreachable store must produce a DISTINCT, loud key — never one that "
            "silently matches the last good one")
        return
    assert key["conceptric"][1] == token["cursor"]
    assert key["conceptric"][2] == token["head_record_digest"]


def test_drift_token_is_cheap_enough_to_call_per_request():
    """The key is computed on EVERY /front/atlas request; if the token were expensive we
    would have swapped a 9s build for a slow stat. Codex measured 0.289ms median; assert
    a loose ceiling so a regression in the store shows up here, not at his walk."""
    from laplace.representation import atlas_bridge as ab

    try:
        ab.drift_token()                                # warm
    except Exception as exc:                            # noqa: BLE001
        pytest.skip(f"no conceptric store in this sandbox: {type(exc).__name__}")
    t0 = time.perf_counter()
    for _ in range(50):
        ab.drift_token()
    per_ms = (time.perf_counter() - t0) * 1000 / 50
    assert per_ms < 25, f"drift_token() is {per_ms:.1f}ms per call — too slow for the key"


def test_repeated_reads_do_not_rebuild(monkeypatch, clean_cache):
    """The receipt must actually be a receipt: a second read with nothing moved must not
    pay the build again. This is the no-tollbooth law, asserted rather than hoped."""
    fd = clean_cache

    # The key is FROZEN for this test on purpose. Unfrozen, it fails honestly and
    # uselessly: the other seats append to the conceptric WAL while the suite runs, so
    # the stores really do move and the board really should rebuild. Freezing isolates
    # the question actually under test — given no drift, does it rebuild anyway?
    monkeypatch.setattr(fd, "_atlas_drift_key", lambda: ("frozen-for-test",))
    fd._atlas_cached_payload()                      # bank one under the frozen key
    calls = {"n": 0}
    real = fd._atlas_board_module

    def counting():
        calls["n"] += 1
        return real()

    monkeypatch.setattr(fd, "_atlas_board_module", counting)
    for _ in range(3):
        fd._atlas_cached_payload()
    assert calls["n"] == 0, "the board rebuilt with no store movement — the cache is dead"


def test_store_movement_does_trigger_a_rebuild(monkeypatch, clean_cache):
    """The other half, and the one that keeps the cache honest: when a source moves, the
    receipt must be replaced. A cache that never invalidates is just a stale page."""
    fd = clean_cache

    monkeypatch.setattr(fd, "_atlas_drift_key", lambda: ("gen-1",))
    fd._atlas_cached_payload()          # cache empty -> synchronous bank, no thread
    calls = {"n": 0}
    real = fd._atlas_board_module

    def counting():
        calls["n"] += 1
        return real()

    monkeypatch.setattr(fd, "_atlas_board_module", counting)
    monkeypatch.setattr(fd, "_atlas_drift_key", lambda: ("gen-2",))
    fd._atlas_cached_payload()                      # spawns the background refresh
    for _ in range(60):                             # ~6s ceiling; build is ~9s cold but
        if not fd._ATLAS_CACHE.get("building"):     # the module is warm here
            break
        time.sleep(0.1)
    assert calls["n"] >= 1, "a source moved and the board never rebuilt — stale as live"


def test_a_successful_refresh_clears_the_prior_failure(monkeypatch, clean_cache):
    """A transient refresh failure belongs to one attempt, not every later receipt."""
    fd = clean_cache
    monkeypatch.setattr(fd, "_atlas_drift_key", lambda: ("gen-1",))
    fd._atlas_cached_payload()
    fd._ATLAS_CACHE["refresh_error"] = "old transient failure"

    real = fd._atlas_board_module()

    class SuccessfulBoard:
        @staticmethod
        def build():
            return real.build()

    monkeypatch.setattr(fd, "_atlas_board_module", lambda: SuccessfulBoard)
    monkeypatch.setattr(fd, "_atlas_drift_key", lambda: ("gen-2",))
    fd._atlas_cached_payload()
    for _ in range(100):
        if not fd._ATLAS_CACHE.get("building"):
            break
        time.sleep(0.05)
    assert "refresh_error" not in fd._ATLAS_CACHE


# ---------------------------------------------------- ego-seat's B1/B2 (2026-08-25)

def test_the_drift_key_covers_the_clock():
    """B1, and it was hours from biting.

    The aging teeth take `today` and answer differently for it — measured on this tree:
    audit(2026-08-25) 0 failing, audit(2026-08-26) 2 failing, audit(2026-08-27) 6 failing
    — while every other component of the drift key is byte-identical across all three.
    Without a date the receipt banked at 23:59 is served all through the next day, so at
    midnight the board reports teeth_verdict=PASS into a day that FAILS, on the pane built
    to answer "what is live versus what was merely banked".
    """
    from datetime import date

    from laplace.web import front_door as fd

    key = dict((p[0], p) for p in fd._atlas_drift_key() if isinstance(p, tuple))
    assert "day" in key, "the drift key has no date component — it expires at midnight"
    assert key["day"][1] == date.today().isoformat()


def test_the_liveness_pane_names_the_day_it_was_judged_against():
    """A verdict that is a function of the clock must say which clock reading produced
    it, or a reader cannot tell a fresh PASS from yesterday's."""
    board = _board()
    pane = board.liveness_pane()
    assert pane.get("judged_on"), "the teeth verdict does not name the date it judged"
    html = board.render_html(board.build(), home="/front")
    assert "judged against" in html


def test_a_failed_refresh_never_presents_as_in_progress(monkeypatch, clean_cache):
    """B2, observed in production: the chrome read "rebuilding now — reload in a moment"
    for 71 seconds while the body read "LIVE (chain verified on this read)" and the pane
    served counts the ledgers disagreed with. Testing `building` before `refresh_error`
    made a permanently-failing refresh present as a permanently-in-progress one — the most
    reassuring possible rendering of the worst possible state.
    """
    fd = clean_cache
    monkeypatch.setattr(fd, "_atlas_drift_key", lambda: ("frozen",))
    fd._atlas_cached_payload()                       # bank one good receipt

    # both flags set at once: the state the production window was actually in
    fd._ATLAS_CACHE["building"] = True
    fd._ATLAS_CACHE["refresh_error"] = "AttributeError: laplace.manuscript.storyboard has no attribute"
    try:
        html = fd._frag_atlas_board()
    finally:
        fd._ATLAS_CACHE.pop("building", None)
        fd._ATLAS_CACHE.pop("refresh_error", None)

    assert "REFRESH FAILED" in html, "the error must win the label over 'rebuilding'"
    assert "rebuilding now" not in html
    assert "is NOT live" in html, "a board that cannot refresh must say it is not live"


def test_a_live_pane_never_wears_an_age(board, payload):
    """His challenge, 2026-08-25: "colour coding freshness is all well and good, but
    isn't the better solution simply to make sure everything is fresh?"

    Right — and measuring showed a blanket age chip was the wrong instrument. The walk
    gate is EXECUTED by subprocess on every build, and the first cut aged
    scripts/atlas_s0_gate.py and printed "20.3h old" beside it: a false staleness signal
    on a live computation. A pane that recomputes shows no age at all; only a banked
    receipt does, and it names the act that renews it.
    """
    html = board.render_html(payload, home="/front")
    lines = re.findall(r'<div class="src">(.*?)</div>', html, re.S)
    assert lines, "no pane names its source"

    for line in lines:
        plain = re.sub(r"<[^>]+>", "", line)
        if "atlas_s0_gate" in plain or "wake.campaign" in plain:
            assert "ago" not in plain and "old" not in plain, (
                f"a live pane is wearing an age: {plain[:90]}")

    banked = [re.sub(r"<[^>]+>", "", x) for x in lines if 'class="age' in x]
    assert banked, "the frozen receipt lost its age — it is the one pane that needs one"
    for line in banked:
        assert "renew it with" in line, (
            "a receipt must name the act that refreshes it, never just its age")


def test_a_held_pane_says_why_it_is_held_not_how_old_it_is(board, payload):
    """The S0 inventory is frozen on purpose: it is the exact generation his walk
    ratifies, so re-minting it would move what he is approving. "Stale" is the wrong
    word for that and "20h old" is the wrong number to show him."""
    html = board.render_html(payload, home="/front")
    held = [x for x in re.findall(r'<div class="src">(.*?)</div>', html, re.S)
            if "atlas_inventory" in x]
    assert held, "the inventory pane vanished"
    plain = re.sub(r"<[^>]+>", "", held[0])
    assert "held for your walk" in plain
    assert "h old" not in plain and "ago" not in plain
