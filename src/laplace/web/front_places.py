"""THE PLACES TABLE — the one typed answer to "where can I go, and what is there?"

His question, 2026-08-25: "think about the navigation _process_ — where do I land, what
are my options, how do you make the dashboard navigation in effect explain itself as I
process through it."

The answer this module implements: **the label IS the explanation.** A nav entry does not
say "the engine room", it says "the engine room · 22 stores · 3 past budget". A count is
read on the first visit and on the two-hundredth; there is nothing to get bored of,
because there is no effect, only state.

WHY IT IS A TABLE AND NOT MARKUP. Before this, front_door.html carried THREE
hand-maintained maps of the application:
    :241-250  the <nav>            — 8 entries, hand-typed
    :285      the TABS const       — 6 entries, and it already disagreed with the nav
    :571-573  the "Served here:"   — a hand-typed sentence, which even hand-apologised
                                     for /seats being its own page
and meanwhile front_door.py served ``/front/walk`` — a real, working door named in NONE
of them. That is a broken promise manufactured by hand-maintained maps: the surface could
not tell him about a room it was already serving. Three maps, three chances to drift, and
they had already drifted from each other.

So: one row per place, and the nav, the digit keymap, the no-route message and the arrival
strip are all renders of these rows.

WHAT IS ACTUALLY ASSERTED, AND WHERE. This docstring claimed for a day that "a route
cannot exist without a census row, and a census row cannot name a route that is not served
— ``tests/test_front_places.py`` asserts both directions". Both halves were false:
test_front_places.py contains no route test at all, and only the easy direction was ever
checked anywhere. The two guards live in ``tests/test_front_door.py``:
    test_every_place_in_the_census_is_actually_served — every row here whose href starts
        ``/front/`` is fetched through handle() and must answer 200 with a body.
    test_every_place_is_censused — every ``/front/`` row here must also appear in
        front_door._SELFTEST_DOORS (only /front/selftest is exempt, since censusing itself
        recurses), so a room he can reach cannot sit outside the door census. That was the
        never-checked direction, and its absence is how /front/conceptric shipped as a nav
        place while the QA chip read "12 doors · 0 not answering" over it.
The converse — a served ``/front/`` path with NO row here, which is exactly how /front/walk
stayed invisible for a day — is asserted by nothing, and cannot be asserted as it was
written: 14 of the 17 doors in the census have no row here and should not. Some are pure
data endpoints (/front/places, /front/record, /front/facets); the rest are the fetch
endpoint BEHIND a hash-route room the shell already lists (/front/apex fills #apex,
/front/organ fills #organ). "Every place is served" is mechanical; "every served path is a
place" is a judgement, and it is still made by hand in the PLACES table below.

THE OPENNESS RULE is not reimplemented here. ``laplace.engine.wake.account`` owns the ratified,
typed, last-disposition-per-id projection, including resolution, defer, undefer, held-open
and malformed-row residuals. The first candidate used a resolution-only join and rendered
47 open orders while the canonical account rendered 55 open plus 26 deferred. That was not
a rounding error: it collapsed a named state partition and made the map disagree with the
brief it linked to.

NO TOLLBOOTHS. Every count is cached on (mtime, size) of the store it counts, so a repeat
read is a stat call. Nothing here may make the front door slower; the whole census is one
payload of a few KB, served at /front/places and rendered entirely client-side.

Runtime law: /usr/bin/python3, system + user site, read-only against every store.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import threading
import time
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from laplace.engine import sources as _sources


def _repo_root() -> Path:
    return source_tree()


# --------------------------------------------------------------- counting, cheaply

#: (path, mtime, size) -> counted value + parse residual. A repeat read is one stat().
_COUNT_CACHE: dict[tuple, Any] = {}

#: the canonical campaign reader, memoised on campaign.jsonl identity
_CAMPAIGN_CACHE: dict[tuple, Any] = {}

#: the canonical account, memoised on the two ledgers it projects. This is a cache of the
#: typed reader's answer, never a second implementation of its rules.
_ACCOUNT_CACHE: dict[str, Any] = {}

#: the founding walk's (walked, open) split, memoised on work_orders.jsonl identity
_WALK_CACHE: dict[tuple, Any] = {}


def _cached(path: Path, tag: str,
            fn: Callable[[list[dict]], Any]) -> dict[str, Any] | None:
    """Project a JSONL store without turning corruption into a confident smaller count.

    A malformed completed row is a named residual and cracks the place. A newline-less
    malformed tail is reported separately because it may be an append in progress. Both
    remain visible beside the usable projection; neither kills the navigation shell.
    """
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_mtime_ns, st.st_size, tag)
    if key in _COUNT_CACHE:
        return _COUNT_CACHE[key]
    rows: list[dict] = []
    malformed: list[dict[str, Any]] = []
    partial_tail = False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        has_partial_tail = bool(text and not text.endswith("\n"))
        for n, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception as exc:  # noqa: BLE001 - a bad line is data, carried below
                if has_partial_tail and n == len(lines):
                    partial_tail = True
                else:
                    malformed.append({"line": n, "error": f"{type(exc).__name__}: {exc}"})
    except OSError:
        return None
    value = {"value": fn(rows), "malformed_rows": malformed,
             "partial_tail": partial_tail}
    _COUNT_CACHE.clear() if len(_COUNT_CACHE) > 64 else None
    _COUNT_CACHE[key] = value
    return value


def _chip(n: Any, unit: str, warn: bool = False) -> dict[str, Any]:
    """A state token. Composed of {n, unit} ONLY — never a hand-authored sentence.

    The moment a census returns prose, "the label is the explanation" is dead and this
    has quietly become a fourth hand-maintained map. tests assert the grammar.
    """
    return {"n": n, "unit": unit, "warn": bool(warn)}


# --------------------------------------------------------------- the census functions

def _lines(path: Path) -> int | None:
    """Count rows WITHOUT parsing them.

    contract/journal.jsonl is 1.5MB and grows on every banked act — including this
    session's own — so its identity changes almost continuously and the memo never hits.
    Parsing 7,723 rows to learn that there are 7,723 of them cost ~200ms on every
    /front/places fetch. A nav chip that needs the row COUNT does not need the rows.
    """
    try:
        with path.open("rb") as fh:
            return sum(block.count(b"\n") for block in iter(lambda: fh.read(1 << 20), b""))
    except OSError:
        return None


def _census_rows() -> dict[str, Any]:
    st = _sources.stat("journal")
    n = _lines(_repo_root() / "contract" / "journal.jsonl")
    return {"chips": [_chip(n, "journal rows")], "source": "contract/journal.jsonl",
            "stat": st}


def _canonical_account() -> dict[str, Any]:
    """The one account projection, cached only until either source ledger moves."""
    root = _repo_root()
    stamp: list[tuple[str, int, int]] = []
    for rel in ("corpus_friction/work_orders.jsonl", "contract/promises.jsonl"):
        path = root / rel
        try:
            st = path.stat()
            stamp.append((rel, st.st_mtime_ns, st.st_size))
        except OSError:
            stamp.append((rel, 0, -1))
    key = tuple(stamp)
    if _ACCOUNT_CACHE.get("key") != key:
        from laplace.engine import wake as _wake

        _ACCOUNT_CACHE.clear()
        _ACCOUNT_CACHE.update(key=key, value=_wake.account(root))
    return _ACCOUNT_CACHE["value"]


def _census_apex() -> dict[str, Any]:
    account = _canonical_account()
    wo, promises = account["work_orders"], account["promises"]
    # PHYSICAL integrity defects crack this pane. The interface probe of 2026-08-25
    # (codex's requested attack on 4b6fb7c6) broke the previous version two ways:
    #   BREAK 2 — the filter enumerated {unparseable-row, store-unreadable} and did not
    #   know "non-object-row", so a store the aging teeth called FAIL rendered a green
    #   census chip here. Enumerating kinds is the bug shape; matching the CLASS is the
    #   cure — any reader-level defect (rows/bytes/tails) cracks, while semantic defects
    #   (evidence-less resolutions etc., 67 standing) stay the account's business and
    #   must not permanently crack the nav.
    #   BREAK 4 — the raw defect list rode the payload: 10,000 poisoned rows made
    #   /front/places a 3.09 MB response. Scale-bounded now: count + first three + a
    #   sha256 commitment over the full set, the same shape codex's reader serves.
    from laplace.pipeline.ledger import integrity_projection, is_physical_store_defect
    integrity = [d for d in account.get("defects", [])
                 if d.get("store") in {"work_orders", "promises"}
                 and is_physical_store_defect(d)]
    projected = integrity_projection(integrity, cap=3)
    residuals: dict[str, Any] = {
        "count": projected["residual_count"],
        "first": projected["residuals"],
        "omitted": projected["residuals_omitted"],
        "sha256": projected["residual_handle"],
    }
    return {
        "chips": [
            _chip(wo["open"], "orders open"),
            _chip(wo["deferred"], "orders deferred", warn=bool(wo["deferred"])),
            _chip(wo["lapsed_deferred"], "order defers lapsed",
                  warn=bool(wo["lapsed_deferred"])),
            _chip(promises["open"], "promises open"),
            _chip(promises["deferred"], "promises deferred",
                  warn=bool(promises["deferred"])),
            _chip(promises["lapsed_deferred"], "promise defers lapsed",
                  warn=bool(promises["lapsed_deferred"])),
        ],
        "source": "laplace.engine.wake.account() — canonical typed open/deferred projection",
        "stat": _sources.stat("work_orders"),
        "residuals": residuals,
        "cracked": bool(integrity),
        "error": (f"canonical account has {len(integrity)} unreadable row residual(s)"
                  if integrity else None),
    }


def _census_organ() -> dict[str, Any]:
    roster = _sources.roster()
    # CONCERNS, never reds. `red` means "older than its budget"; two stores are past
    # budget right now and BOTH are event ledgers whose quiet is the healthy case
    # (seats: no seat founded today; liveness: the archaeology campaign closed with all
    # 13 packets graded). Warning about them is the same false alarm the brief was
    # cured of this morning, one layer up, and it teaches him to stop reading the chip.
    concern = sum(1 for r in roster if r.get("concern"))
    quiet = sum(1 for r in roster if r.get("red") and not r.get("concern"))
    absent = sum(1 for r in roster if r.get("absent"))
    return {"chips": [_chip(len(roster), "stores"),
                      _chip(concern, "past budget", warn=bool(concern)),
                      _chip(quiet, "quiet by design"),
                      _chip(absent, "absent", warn=bool(absent))],
            # no `stat`, and no lag either: roster() stats every store on THIS request,
            # so the answer is as of now. That is why it declares `live` rather than
            # leaving freshness to default — see census()'s freshness vocabulary.
            "source": "laplace.engine.sources.roster()", "stat": None, "freshness": "live"}


def _census_campaign() -> dict[str, Any]:
    """CANONICAL READER, never reimplemented. My first cut filtered on
    record == "campaign-stage" and reported "0 stages open · 0 stages" while the board
    rendered seven — the record is actually "stage", and stage status is
    laplace.engine.wake.campaign's to decide, not mine. Two surfaces disagreeing about the same
    rows is the precise defect this module exists to remove, so it must not start by
    committing it. run_gates=False: the gates are expensive and this is a nav chip.
    """
    store = _repo_root() / "corpus_friction" / "campaign.jsonl"
    try:
        st = store.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        stamp = None
    got = _CAMPAIGN_CACHE.get(stamp) if stamp else None
    if got is None:
        try:
            from laplace.engine import wake as _wake
            c = _wake.campaign(_repo_root(), run_gates=False)
            stages = [s for s in c.get("stages", []) if str(s["id"]).startswith("ATLAS-")]
            got = (sum(1 for s in stages if s.get("status") == "OPEN"), len(stages),
                   c.get("next_act"))
        except Exception:  # noqa: BLE001
            return {"chips": [], "source": "laplace.engine.wake.campaign", "stat": None,
                    "cracked": True}
        # the canonical reader costs ~45ms — the single most expensive thing left in this
        # census once the row counts stopped parsing. Memoised on the store's identity,
        # which is the same drift rule every other count here uses.
        _CAMPAIGN_CACHE.clear()
        if stamp:
            _CAMPAIGN_CACHE[stamp] = got
    open_n, total, nxt = got
    stages = [None] * total
    return {"chips": [_chip(open_n, "stages open"), _chip(len(stages), "stages"),
                      _chip(nxt, "is next")],
            "source": "corpus_friction/campaign.jsonl via laplace.engine.wake.campaign",
            "stat": _sources.stat("campaign")}


def _inventory_generation_rows(rows: list[dict]) -> int:
    """THE HOUSE RULE, matched to the board exactly: last-wins by id, then filtered to the
    CURRENT generation. Counting raw lines gives 1987; the board says 466. A nav chip that
    disagrees with the page it links to is worse than no chip at all.
    """
    generation = None
    by_id: dict[str, dict] = {}
    for r in rows:
        if r.get("record") == "inventory-generation":
            generation = r.get("id")
        elif r.get("record") == "inventory" and r.get("id"):
            by_id[r["id"]] = r
    return sum(1 for r in by_id.values() if r.get("generation") == generation)


def _census_atlas() -> dict[str, Any]:
    inv = _cached(_repo_root() / "corpus_friction" / "atlas_inventory.jsonl",
                  "generation", _inventory_generation_rows)
    if inv is None:
        return {"chips": [], "source": "corpus_friction/atlas_inventory.jsonl",
                "stat": None, "cracked": True, "error": "inventory store unreadable"}
    malformed = list(inv.get("malformed_rows") or [])
    return {"chips": [_chip(inv["value"], "rows to disposition")],
            "source": "corpus_friction/atlas_inventory.jsonl (last-wins by id, "
                      "current generation — the board's own rule)",
            "stat": _sources.stat("atlas_inventory"),
            "residuals": malformed,
            "partial_tail": bool(inv.get("partial_tail")),
            "cracked": bool(malformed),
            "error": (f"inventory has {len(malformed)} malformed completed row(s)"
                      if malformed else None)}


def _census_development() -> dict[str, Any]:
    """The canonical work-map lens at grade zero; never a ledger census."""

    from laplace.web import development_lens

    return development_lens.census()


def _census_walk() -> dict[str, Any]:
    """DORMANT IS NOT PENDING, and this place taught me the difference the hard way.

    His catch, 2026-08-25: "did you notice you're still serving the founding walk?" All
    five founding cards were walked and custody-confirmed on 08-24; the page says so
    plainly ("No open founding cards"). It nonetheless held a permanent nav slot
    advertising "0 cards await you" — a live-shaped label on a finished room, which is
    the same category error as a founding ledger judged against a freshness budget or a
    closed archaeology campaign flagged red. I did not merely miss it: I put it in the
    nav that morning and called it a broken promise CURED.

    It is not dead either — the serve names queued cards for a next sitting. So the
    honest state is DORMANT: nothing awaits him, something would wake it. A place says
    which of those it is, exactly as a pane says whether it is live, held or a receipt.

    DERIVED — AFTER SHIPPING A CONSTANT BEHIND A DEAD GUARD. The first cut read
    ``module.open_card_ids() if hasattr(module, "open_card_ids") else []``. That function
    has never existed on scripts/atlas_walk_serve.py (``git log -S open_card_ids`` returns
    one commit, 917c1ae3, which added the CALL and nothing else), so hasattr was False on
    every request since birth, n was always 0, the live branch was unreachable, and the
    chip was the literal ``_chip(5, "cards walked")`` — it would have gone on reading
    "5 cards walked · dormant" on the day a sixth card opened. The producer's own two
    readers stand behind it now: _walked_cards() folds the closure rows out of
    work_orders.jsonl, _cards() is the served card list. That is the same pair build()
    derives ``open_count`` from, so the nav and the page cannot disagree.

    NOT DERIVED, AND SAID SO. The queued classes are a literal inside build(), and build()
    mints a serve-custody object as a side effect. A nav chip fetched on his boot path may
    not write to custody — this module is read-only against every store — so the count of
    queued classes stays with the page that legitimately builds the serve, and this census
    points at it instead of restating a number it cannot check.
    """
    # _walked_cards() re-reads and re-parses work_orders.jsonl on every call — 11.0ms
    # measured warm on /front/places, which the shell fetches at boot and on every store
    # event. Memoised on the store's identity, the same drift rule the campaign and
    # account readers above use, so a repeat read is one stat().
    store = _repo_root() / "corpus_friction" / "work_orders.jsonl"
    try:
        st = store.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        stamp = None
    got = _WALK_CACHE.get(stamp) if stamp else None
    if got is None:
        try:
            from laplace.web import front_door as _fd
            module = _fd._walk_serve_module()
            walked = module._walked_cards()
            open_ids = [c["id"] for c in module._cards() if c["id"] not in walked]
        except Exception:  # noqa: BLE001 - a door we cannot count is CRACKED, not hidden
            return {"chips": [_chip(None, "cards")],
                    "source": "scripts/atlas_walk_serve.py",
                    "stat": None, "cracked": True, "freshness": "unknown"}
        got = (walked, open_ids)
        _WALK_CACHE.clear()
        if stamp:
            _WALK_CACHE[stamp] = got
    walked, open_ids = got
    source = ("scripts/atlas_walk_serve.py — _walked_cards() over "
              "corpus_friction/work_orders.jsonl, _cards() for what the serve carries")
    if open_ids:
        return {"chips": [_chip(len(open_ids), "cards await you", warn=True)],
                "standing": "live", "source": source, "stat": None,
                "freshness": "live"}
    if not walked:
        # NEITHER FINISHED NOR WAITING. No card served and none walked is a third state,
        # and it must not borrow the finished room's words: "0 cards walked" would be read
        # as a walk that has not started, and the renderer drops a non-warn zero entirely,
        # so the nav would carry a founding walk with no state at all.
        return {"chips": [_chip(None, "no cards served")], "standing": "dormant",
                "dormant_why": "the serve carries no founding cards at all",
                "source": source, "stat": None, "freshness": "live"}
    # Custody is part of the closure claim, not decoration: _walked_cards() stamps a card
    # "resolves" only when its shown object is actually in serve custody, and the
    # pre-custody projections it can also stamp are a named RED this chip must not swallow.
    unconfirmed = sorted(k for k, v in walked.items() if v.get("custody") != "resolves")
    chips = [_chip(len(walked), "cards walked")]
    if unconfirmed:
        chips.append(_chip(len(unconfirmed), "walked without custody", warn=True))
    why = f"all {len(walked)} founding cards are walked"
    # names the cards rather than counting them: the count is already the chip, and a
    # tooltip is the summonable register where "which one" is the useful half.
    if unconfirmed:
        why += (" — serve custody does not resolve the shown object for "
                + ", ".join(unconfirmed))
    else:
        why += " and custody-confirmed"
    return {"chips": chips,
            "standing": "dormant",
            "dormant_why": why + "; the queued classes for the next sitting are named on "
                                 "the page itself",
            "source": source, "stat": None, "freshness": "live"}


#: seat counts, banked against the drift token that produced them
_SEATS_CACHE: dict[str, Any] = {}
_SEATS_LOCK = threading.Lock()


def _census_selftest() -> dict[str, Any]:
    """A RENDER OF THE LAST RUN, never a fresh fire.

    This census used to fire all twelve GET doors in-process — /front/atlas among them,
    which is a whole board build — to produce one nav chip. Measured on his boot path:
    16,971ms of an 18,879ms /front/places, which the shell fetches AT BOOT. It was the
    single largest cost in opening his front door, it grew with every door anyone added,
    and his steer naming the chrome "hilariously inefficient" was measuring exactly this.

    A chip is not worth a measurement. It is worth the LAST measurement, stamped with its
    age — the same banked-with-age law the census and bench verdicts already run under.
    The run itself happens when he opens /front/selftest, which is what that page is for.
    NEVER RUN is a state with a name here, not a zero: a chip reading `0 not answering`
    over a census that has never executed is absence rendered as reassurance.
    """
    from laplace.web import front_door as _fd

    path = _fd._repo_root() / _fd._SELFTEST_BANK
    if not path.exists():
        return {"chips": [_chip(0, "doors never certified", warn=True)],
                "source": f"{_fd._SELFTEST_BANK} — absent; the door census has not run "
                          f"in this repo. Open the door census to certify.",
                "stat": None, "freshness": "banked"}
    try:
        bank = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"chips": [], "error": f"selftest bank unreadable: {exc}",
                "source": _fd._SELFTEST_BANK, "residuals": [],
                "freshness": "unknown"}
    down = int(bank.get("down", 0))
    hours = None
    try:
        from datetime import datetime, timezone
        ran = datetime.fromisoformat(str(bank["ran_at"]).replace("Z", "+00:00"))
        hours = (datetime.now(timezone.utc) - ran).total_seconds() / 3600.0
    except (KeyError, TypeError, ValueError):
        pass
    chips = [_chip(int(bank.get("doors", 0)), "doors"),
             _chip(down, "not answering", warn=bool(down))]
    if hours is None:
        chips.append(_chip(None, "census age unknown", warn=True))
    else:
        # A banked green is historical evidence, never a live door probe.  Age belongs
        # in the default register beside its status; leaving it only in ``source`` made
        # an arbitrarily old 0-down run wear the same chrome as a fresh certification.
        chips.append(_chip(round(max(0.0, hours), 1), "hours since census"))
    return {"chips": chips,
            "source": f"{_fd._SELFTEST_BANK} — banked by the door census at "
                      f"{bank.get('ran_at')}"
                      + (f" ({hours:.1f}h ago)" if hours is not None else "")
                      + "; this chip fires no door",
            # `banked`, not `store-age`: nothing in laplace.engine.sources dates this bank, so
            # as_of stays null and `stale` can never fire. The age chip above is this
            # place's whole freshness axis, which is why it rides the default register.
            "stat": None, "freshness": "banked"}


def _census_conceptric() -> dict[str, Any]:
    """W12. Cheap by the same law this file just applied to the door census: a nav chip
    may not mint a measurement on his boot path.

    A full projection is a ~960-event replay at 1.4s. read_drift_token() answers in 0.2ms
    and carries the cursor, so the size of the engine's record is free. The dark-vocabulary
    count needs the replay, so it rides ONLY when a projection is already cached — and
    when it is not, the pane says it has not been measured rather than showing a zero that
    would read as "nothing is dark".
    """
    try:
        from laplace.representation import atlas_bridge as ab
        from laplace.engine import descent_telemetry as dt
        token = ab.ConceptricStore.read_drift_token(dt.DEFAULT_STORE)
        cursor = token.get("cursor")
        chips = [_chip(cursor, "events", warn=False)]
        cached = (dt._CACHE.get("payload") or {}).get("totals")
        freshness = "live"
        if cached:
            dark = cached["kinds_declared"] - cached["kinds_fired"]
            chips.append(_chip(dark, "kinds never fired", warn=bool(dark)))
            # THE CACHED COUNT CARRIES ITS OWN LAG. dt._CACHE is keyed
            # (store, head_event_id, cursor), and reading its payload without checking
            # that key against the token just read renders an arbitrarily old replay in
            # the same chrome as a fresh one. This pane has no clock — no store dates it —
            # so the cursor delta IS its freshness axis, and it belongs in the chips,
            # because the shell renders chips and does not render `source`.
            key = dt._CACHE.get("key") or ()
            at = key[2] if len(key) > 2 else None
            behind = (cursor - at) if (isinstance(at, int)
                                       and isinstance(cursor, int)) else None
            if behind:
                chips.append(_chip(behind, "events behind", warn=True))
            elif behind is None:
                chips.append(_chip(None, "kinds count age unknown", warn=True))
            freshness = "banked"
            source = ("laplace.representation.atlas_bridge.ConceptricStore.read_drift_token (cursor) + "
                      "the cached descent_telemetry projection (dark kinds) — no replay "
                      "on this path")
        else:
            source = ("laplace.representation.atlas_bridge.ConceptricStore.read_drift_token — cursor only; "
                      "the dark-vocabulary count needs a full replay and is measured when "
                      "you open the pane, never on this one")
        return {"chips": chips, "source": source, "residuals": [], "error": None,
                "freshness": freshness}
    except Exception as exc:  # noqa: BLE001 - a census that cannot read says so
        return {"chips": [], "error": f"{type(exc).__name__}: {exc}",
                "source": "laplace.engine.descent_telemetry", "residuals": [],
                "freshness": "unknown"}


def _census_seats() -> dict[str, Any]:
    """The one expensive census, made cheap by codex's token.

    atlas_bridge.snapshot() calls replay(), which folds every row AND verifies the graph
    projection — measured at 1148.9ms, by far the most expensive place here and far too
    slow for a nav chip fetched at boot. drift_token() answers "has the fabric moved?" in
    0.23ms, so the counts are banked against the token that produced them and the replay
    runs only when the answer is yes. Same shape as the atlas board's receipt, and for the
    same reason: nothing on this surface may become a tollbooth.
    """
    try:
        from laplace.representation import atlas_bridge as _ab
        token = _ab.drift_token()
        stamp = (token["cursor"], token["head_record_digest"])
    except Exception as exc:  # noqa: BLE001 - loud, never silent
        return {"chips": [], "source": "laplace.representation.atlas_bridge.drift_token()",
                "stat": None, "cracked": True, "error": f"{type(exc).__name__}: {exc}",
                "freshness": "unknown"}

    def _recount() -> None:
        try:
            view = _ab.snapshot()["provider"]
            result = {
                "stamp": stamp,
                "seats": len(view.get("seats", {})),
                "pending": sum(1 for m in view.get("messages", {}).values()
                               if m.get("status") in ("queued", "pulled")),
            }
            with _SEATS_LOCK:
                _SEATS_CACHE.update(result)
                _SEATS_CACHE.pop("error", None)
        except Exception as exc:  # noqa: BLE001
            with _SEATS_LOCK:
                _SEATS_CACHE["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            with _SEATS_LOCK:
                _SEATS_CACHE["counting"] = False

    start = False
    with _SEATS_LOCK:
        if _SEATS_CACHE.get("stamp") != stamp and not _SEATS_CACHE.get("counting"):
            _SEATS_CACHE["counting"] = True
            start = True
        cached = dict(_SEATS_CACHE)
    if start:
        # Cold is not a special permission to block. The first candidate called
        # _recount() inline when no receipt existed, putting 2.2s back on the first
        # /front/places request — the very tollbooth the cache claimed to remove.
        threading.Thread(target=_recount, name="front-places-seats",
                         daemon=True).start()

    if "seats" not in cached:
        error = cached.get("error")
        return {"chips": [_chip(None, "seats warming")],
                "source": "laplace.representation.atlas_bridge.snapshot() — prewarming off-request",
                "stat": None, "cracked": bool(error), "freshness": "banked",
                "error": error, "refresh_after_ms": 500}

    at = cached.get("stamp", ("?",))[0]
    moving = at != stamp[0] or bool(cached.get("counting"))
    error = cached.get("error")
    chips = [_chip(cached["seats"], "seats"),
             _chip(cached["pending"], "in flight", warn=bool(cached["pending"]))]
    # THE COUNT'S OWN LAG, in the register he actually reads. These numbers are banked
    # against a fabric cursor and no store dates them, so `as_of` is null and `stale` can
    # never fire: "6 seats · 84 in flight" rendered identically whether the replay behind
    # it was 0 or 900 events old, and the only hint lived in `source`, which the shell
    # does not render at all. The delta comes free from the token read three lines up.
    behind = ((stamp[0] - at) if isinstance(at, int) and isinstance(stamp[0], int)
              else None)
    if behind:
        chips.append(_chip(behind, "events behind", warn=True))
    elif behind is None:
        chips.append(_chip(None, "count age unknown", warn=True))
    return {"chips": chips,
            "source": f"laplace.representation.atlas_bridge.snapshot() @ cursor {at}"
                      + ("" if at == stamp[0] else f" · fabric now at {stamp[0]}, "
                                                   f"recounting"),
            "stat": None, "cracked": bool(error), "error": error,
            "freshness": "banked",
            "refresh_after_ms": 500 if moving else None}


def prewarm() -> None:
    """Start the only expensive places census before a browser asks for it."""
    _census_seats()


def _census_chats() -> dict[str, Any]:
    st = _sources.stat("talk")
    return {"chips": [_chip(st.get("bytes"), "bytes") if st and not st.get("absent")
                      else _chip(None, "sessions")],
            "source": "the talk store", "stat": st}


# --------------------------------------------------------------------- the table

#: ONE ROW PER PLACE. `kind` is how a reader gets there: "route" = a hash route inside the
#: shell; "page" = its own document (the atlas board, the seats surface). `affords` is what
#: he can DO there — it is what the arrival strip's third cell renders, and it is also the
#: honest place to say that a verb is his alone.
PLACES: list[dict[str, Any]] = [
    {"id": "apex", "noun": "the brief", "href": "#apex", "kind": "route", "key": "1",
     "band": "attention", "census": _census_apex,
     "why": "what needs you, ranked — the landing",
     "affords": ["read the delta", "accept or redline a walk gate"]},
    {"id": "development", "noun": "the development field", "href": "/front/development",
     "kind": "page", "key": "D", "band": "attention", "census": _census_development,
     "why": "what exists, what matters now, what is blocked, and the next exact descent",
     "affords": ["read the canonical work frontier", "descend into exact evidence"]},
    {"id": "atlas", "noun": "the atlas", "href": "/front/atlas", "kind": "page", "key": "A",
     "band": "campaign", "census": _census_atlas,
     "why": "the S0 disposition, the campaign spine, the walk",
     "affords": ["read the disposition", "copy the walk command"]},
    {"id": "walk", "noun": "the founding walk", "href": "/front/walk", "kind": "page",
     "key": "W", "band": "campaign", "census": _census_walk,
     # no count in this sentence: the walked/open split is the census's to say, and a
     # hand-typed "all five walked" here is the fourth map creeping back in one row.
     "why": "the founding cards — what you already ruled, and what waits for a sitting",
     "affords": ["read what you ruled", "descend to a card's ground"]},
    {"id": "campaign", "noun": "the campaign", "href": "#campaign", "kind": "route",
     "key": "2", "band": "campaign", "census": _census_campaign,
     "why": "the stages, and which one is next",
     "affords": ["read the spine"]},
    {"id": "run", "noun": "what ran", "href": "#run", "kind": "route", "key": "3",
     "band": "history", "census": _census_rows,
     "why": "the acts, newest first — what the engine did",
     "affords": ["descend into an act's tree"]},
    {"id": "chats", "noun": "the chats", "href": "#chats", "kind": "route", "key": "4",
     "band": "history", "census": _census_chats,
     "why": "the sessions, and what was said",
     "affords": ["read a session"]},
    {"id": "organ", "noun": "the engine room", "href": "#organ", "kind": "route", "key": "5",
     "band": "machine", "census": _census_organ,
     "why": "every store, its age, and whether it is past its own budget",
     "affords": ["see which store has rotted"]},
    {"id": "explore", "noun": "the rows", "href": "#explore/journal", "kind": "route",
     "key": "6", "band": "machine", "census": _census_rows,
     "why": "the stores themselves, filterable, row by row",
     "affords": ["filter", "descend to one record"]},
    {"id": "selftest", "noun": "the door census", "href": "/front/selftest",
     "kind": "page", "key": "T", "band": "machine", "census": lambda: _census_selftest(),
     "why": "every door fired in-process — which are answering, and how slowly",
     "affords": ["see which door is down before you walk into it"]},
    {"id": "seats", "noun": "the seats", "href": "/seats", "kind": "page", "key": "S",
     "band": "machine", "census": _census_seats,
     "why": "the fabric — who is working, and what is in flight",
     "affords": ["read the causal chain"]},
    {"id": "conceptric", "noun": "the conceptric", "href": "/front/conceptric",
     "kind": "page", "key": "C", "band": "machine", "census": _census_conceptric,
     "why": "the engine as a graph — seats, the calls between them, and what returns",
     "affords": ["watch the causal tail move", "see which event kinds have never fired"]},
]

BANDS = ["attention", "campaign", "history", "machine"]


def census(only: str | None = None) -> dict[str, Any]:
    """The whole places payload. Small, cheap, and rendered entirely client-side.

    Every place carries its `source` and a `freshness` naming what "current" MEANS for it:

        store-age  a dated store stands behind it, so `as_of` is that store's age,
                   `budget_s` its budget and `stale` a real verdict.
        live       recomputed from source on this very request; there is no lag for it to
                   be stale about.
        banked     a render of an earlier run or replay. `as_of` is null because no store
                   dates it, so its lag rides in the CHIPS instead — hours since the door
                   census, events behind the fabric cursor.
        unknown    the census could not read enough to say. Cracked places land here.

    Which place is which is NOT listed here. Every row carries its own `freshness` in the
    payload, and a hand-typed membership list in a docstring is the fourth map this module
    was written to kill — a place can even change axis between requests (conceptric is
    live on its cursor alone and banked once a replay is cached behind it).

    This docstring used to read "every place carries as_of", and five of the eleven places
    served ``as_of: null, budget_s: null, stale: false`` — which in a payload is
    indistinguishable from a store stat'd one second ago and found current. seats reported
    "84 in flight" off a replay of unbounded age with no way to be marked stale; the door
    census invoked "the same banked-with-age law" in its own docstring while shipping no
    age at all. Absence rendered as reassurance is the defect class this whole table exists
    to remove: an unstaleable place must say it has no clock, not wear a fresh one's chrome.

    A place whose census raises is marked ``cracked`` and renders hatched — a door known to
    be broken BEFORE he walks into it, which is the mechanical answer to "my walk runs into
    broken promises".
    """
    out = []
    for row in PLACES:
        if only and row["id"] != only:
            continue
        place = {k: v for k, v in row.items() if k != "census"}
        t0 = time.time()
        try:
            got = row["census"]() or {}
        except Exception as exc:  # noqa: BLE001 - a cracked door is data, shown loudly
            got = {"chips": [], "source": "?", "stat": None, "cracked": True,
                   "error": f"{type(exc).__name__}: {exc}"}
        place.update({k: v for k, v in got.items() if k != "stat"})
        st = got.get("stat") or {}
        place["as_of"] = round(st.get("age_s"), 1) if st.get("age_s") is not None else None
        place["budget_s"] = st.get("budget_s")
        place["stale"] = bool(st.get("red"))
        # UNSTALEABLE IS NOT FRESH — the axis is named per row, never inferred from the
        # three nulls above. A census that returns no `stat` and declares no freshness is
        # the drift this field exists to catch, so it lands as `unknown` rather than
        # silently inheriting the shape of a store checked a second ago.
        place["freshness"] = "store-age" if st else (got.get("freshness") or "unknown")
        place["cost_ms"] = round((time.time() - t0) * 1000, 1)
        out.append(place)

    digest = sha256(json.dumps(
        [[p["id"], [c["n"] for c in p.get("chips", [])]] for p in out],
        sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return {
        "schema": "laplace.front-places/1",
        "law": "RENDER OF ROWS — the nav, the keymap and the no-route message are all "
               "renders of this payload. tests/test_front_door.py fetches every /front "
               "row here and requires it in the door census; the converse (a served path "
               "with no row) is a hand judgement, not a mechanical one. `freshness` says "
               "what current means per place — a null as_of is no clock, never a fresh one",
        "bands": BANDS,
        "places": out,
        "digest": digest,
        "served_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
