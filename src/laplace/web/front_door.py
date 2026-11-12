"""front_door.py — the front door (front door M1): one served page over the rows.

His commission (PV-20260823-his-front-door-commission; scope ruling at the Interface
seat's founding 2026-08-24): the interface is THE PLACE HE INTERACTS WITH EIGEN. M1 is
the read surface — apex account strip, campaign grid, live tail, trace waterfall,
record descend, chats, seats — one page, every panel carrying its row-source byline
and freshness stamp, every element carrying its row address.

Scanner-dispatch idiom: ``handle(path, query, method, body)`` exactly as
``seats_surface.handle`` — the scanner owns the HTTP server; ``GET /front/stream`` is
the one exception (a stream cannot ride the whole-body contract; the scanner dispatches
it to ``laplace.web.stream.serve`` directly). ``?format=json`` is honoured on the data
doors — apex, rows, facets, acts, trace, chats, organ, sources — so the agent reads
the same views the author does; grid, record and chat are html-only (their JSON twin
is the underlying /front/rows query), named so the claim stays exact.

The seats surface is composed, not duplicated: sessions authority, seat rows, and the
permission-ask lane are imported from ``laplace.web.seats_surface`` (the read half the Ego
landed under PV-20260824-his-move-quickly-interface-first; this seat's territory since
the founding subsumption ruling).

Enforced here, per the interface law: no number renders without a link to its rows;
unverified states render loudly (UNJUDGED / UNMAPPED / ABSENT); soul content is
refs-only — this module renders engine stores and transcripts, never soul/ files.

M2's first slice, THE ASK-DOOR (his pace ruling PV-20260824-his-move-quickly-interface-
first: "route these permission asks back"): ``POST /front/decide`` banks HIS decision on
a pending ASK row. This is the module's ONE write, and it writes nothing of its own —
the row is the author's act (actor stamped, via front-door), appended through the shared
banking path ``laplace.core.records.journal.bank_row`` (journaled intent, durable append, journaled
done), landing as the resolution shape the seats' ask lane already retires on. The
design's own substrate ruling sanctions exactly this: "write endpoints so a steer posts
a typed row from the page". Everything else here remains a pure read.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import base64
import hashlib
import importlib.util
import json
import os
import re
import sys
import threading
import time
from datetime import date, datetime, timezone
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from laplace.engine import rows as _rows
from laplace.engine import sources as _sources
from laplace.engine import trace as _trace

_JSON = "application/json; charset=utf-8"
_HTML = "text/html; charset=utf-8"
_PAGE = Path(__file__).resolve().parent / "front_carrier.html"
_QUARRY_PAGE = Path(__file__).resolve().parent / "front_door.html"
_CAUSAL_WEAVE = Path(__file__).resolve().parent / "static_shared" / "causal_atlas_weave.mjs"
_DIRECT_COORDINATION_PATH = Path(
    "/home/phujck/SystemCheckpoints/2026-08-28/"
    "DIRECT-COORDINATION-FALLBACK-SEMANTIC-RECOVERY.json"
)
_DIRECT_COORDINATION_SHA256 = "d8af14c3b8703b2d271597f2b1b9764f6f523d9d86c189dc450225eb90cf8407"
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

#: chat tail read window — transcripts grow to tens of MB; the pane reads the tail.
_CHAT_TAIL_BYTES = 384 * 1024


def _repo_root() -> Path:
    return source_tree()


@lru_cache(maxsize=1)
def _atlas_board_module():
    """Load the one board producer without copying its row logic into this surface."""

    source = _repo_root() / "scripts" / "atlas_board.py"
    spec = importlib.util.spec_from_file_location("laplace_atlas_board", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"atlas board producer cannot be loaded from {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _atlas_board_payload() -> dict[str, Any]:
    """The engine register — the SAME drift-keyed payload the human register renders.

    Both registers from one producer is the board's founding law; if the JSON door
    rebuilt while the HTML door served a receipt, the two registers could disagree
    about the same instant, which is worse than either being slow.
    """
    payload, _at, _fresh = _atlas_cached_payload()
    return payload


#: Every store the atlas board reads during build(). DERIVED, not guessed: obtained by
#: running build() under a ``sys.addaudithook`` "open" trace on 2026-08-25. The two
#: conceptric files are OUTSIDE the repo and an in-repo trace misses them — that omission
#: would have frozen the causal strip while it still rendered "LIVE".
#: A key that misses a store serves stale-as-live, which is the one thing this surface
#: may not do; re-run the trace whenever a pane gains a source.
_ATLAS_REPO_SOURCES = (
    "corpus_friction/campaign.jsonl",
    "corpus_friction/atlas_inventory.jsonl",
    "corpus_friction/work_orders.jsonl",
    "corpus_friction/open_stack_forks.jsonl",
    "contract/promises.jsonl",
    # added with the crutches pane, 2026-08-25 — and NOT by remembering to: the guard in
    # tests/test_atlas_board.py failed the moment the pane shipped without it, which is
    # the whole reason that test exists. Its author was the first person it caught.
    "corpus_friction/crutches.jsonl",
    # arrived with the lapsed-defer cure: liveness_pane now asks wake.account which rows
    # are past their own defer date, and the account reads wider than the teeth do. The
    # guard caught this the moment the pane shipped — third time today it has caught its
    # own author adding a source and forgetting the key.
    "contract/predictions.jsonl",
    "corpus_friction/open_stack_wants.jsonl",
    "holdout/THREAD_PROBES.json",
    "evidence/ATLAS_UPDOWN_V0_2026-08-24/REPORT_bge-small-en-v1.5.json",
    # WO-20260825-walk-serves-the-benches: the board now mounts these receipts and the
    # canonical health rows. Every one belongs in the drift key or the served page can
    # call an old measurement current after its source has moved.
    "evidence/ATLAS_BENCH_2026-08-24/DEMAND_INVENTORY.json",
    "evidence/ATLAS_HIVED_STORAGE_2026-08-25/CURRENT_SOURCE_REATTACK_RECEIPT.json",
    "evidence/ATLAS_HIVED_STORAGE_2026-08-25/NAMING_AND_MEASUREMENT_AMENDMENT.json",
    "evidence/DIFFUSION_SCISSORS_2026-08-25/RECEIPT.json",
    "holdout/STRANGER_BENCH.json",
    "holdout/STRANGER_BENCH_VERDICTS.jsonl",
    "holdout/sb3_surfaces.txt.index.json",
    "corpus_friction/census_verdicts.jsonl",
    "contract/journal.jsonl",
)

_ATLAS_CACHE: dict[str, Any] = {}
#: serialises the cold build. Two threads arriving before anything is banked would each
#: pay the full ~12s and hold two payloads; the second waits and takes the first's.
_ATLAS_BUILD_LOCK = threading.Lock()


def _atlas_repo_sources() -> tuple[str, ...]:
    """Static board stores plus every input named by registered instrument receipts."""
    from laplace.representation import instrument_serve

    return tuple(sorted(set(_ATLAS_REPO_SOURCES) | set(
        instrument_serve.source_paths(_repo_root()))))


def _atlas_drift_key() -> tuple:
    """The cache key: identity of every source, plus HEAD.

    The conceptric half is a DECLARED INTERFACE, not a file path. It was briefly keyed on
    conceptric.sqlite3 + its -wal (CR-interface-seat-atlas-cache-mtime-key, now retired):
    keying the board on codex's file layout while codex migrated that layout to hived
    storage would have frozen the board silently while it still rendered "LIVE (chain
    verified on this read)". codex shipped ``atlas_bridge.drift_token()`` at 14dd740a —
    an O(1) compact-ledger read, measured here at 0.230ms median / 1.05ms p99 over 200
    reads, with identity proven stable across the v1 -> hived-v2 migration.

    It certifies nothing. Codex is explicit: the token never replays and makes no
    chain-verification claim, so it may ONLY invalidate a payload that was already built
    and verified. That is exactly this use — we are asking "is the receipt still current?",
    never "is the history sound?".
    """
    parts: list = []
    root = _repo_root()
    for rel in _atlas_repo_sources():
        try:
            st = (root / rel).stat()
            parts.append((rel, st.st_mtime_ns, st.st_size))
        except OSError:
            parts.append((rel, 0, -1))          # absence is part of the key, loudly
    try:
        from laplace.representation import atlas_bridge as _ab
        token = _ab.drift_token()
        parts.append(("conceptric", token["cursor"], token["head_record_digest"]))
    except Exception as exc:  # noqa: BLE001
        # LOUD FAILURE, as codex asked. An unreachable store must never collapse to the
        # same key as a reachable one — that would pin the board on the last good receipt
        # and call it live. Keying on the error text forces a rebuild attempt per distinct
        # failure, and the rebuild surfaces the refusal in the causal strip.
        parts.append(("conceptric", "UNREACHABLE", f"{type(exc).__name__}: {exc}"))
    parts.append(("head", _git_head_short()))
    # THE CLOCK IS AN INPUT. ego-seat's B1, reproduced by hand before curing: the aging
    # teeth take `today` and answer differently for it — audit(ROOT, 2026-08-25) gives
    # 0 failing, 08-26 gives 2, 08-27 gives 6 — while every other part of this key is
    # byte-identical across all three. Without a date component the receipt banked at
    # 23:59 is served all through the next day, so at midnight the board would report
    # teeth_verdict=PASS into a day that FAILS, on the very pane built to answer "what is
    # live versus what was merely banked". A stale clock is stale-presented-as-live with
    # extra steps.
    parts.append(("day", date.today().isoformat()))
    return tuple(parts)


def _git_head_short() -> str:
    """The canonical reader, imported never reimplemented (the board's standing law)."""
    try:
        from laplace.core.versioning import head_sha
        return head_sha(_repo_root()) or "?"
    except Exception:  # noqa: BLE001 - a headless tree is a valid, distinct key
        return "?"


def _atlas_cached_payload() -> tuple[dict, float, bool]:
    """build() is 2.5s and render is 4ms, so the PAYLOAD is cached and the HTML is not.

    Measured 2026-08-25: /front/atlas served in 5894 ms in the door's own census, up from
    1821 ms that morning — a hang at the exact place his walk lands. The cost is all in
    build(): live_pane alone is 1.54s because atlas_bridge.snapshot() does a full replay()
    plus a graph-projection verify; walk_pane is 1.03s. liveness_pane is 0.06s.
    """
    key = _atlas_drift_key()
    have = "payload" in _ATLAS_CACHE

    if not have:
        # nothing banked yet: someone must pay, exactly once. Whoever loses the lock
        # takes the winner's receipt instead of building a second copy of it.
        with _ATLAS_BUILD_LOCK:
            if "payload" not in _ATLAS_CACHE:
                _ATLAS_CACHE["key"] = key
                _ATLAS_CACHE["payload"] = _atlas_board_module().build()
                _ATLAS_CACHE["at"] = time.time()
                return _ATLAS_CACHE["payload"], _ATLAS_CACHE["at"], True
        return _ATLAS_CACHE["payload"], _ATLAS_CACHE["at"], False

    if _ATLAS_CACHE.get("key") != key and not _ATLAS_CACHE.get("building"):
        # THE STORES MOVED. Serve the banked receipt NOW — labelled with its true age —
        # and rebuild off-thread. A 10s block is a hang at the place his walk lands, and
        # a hang is a broken promise; a receipt that says how old it is, is not.
        _ATLAS_CACHE["building"] = True

        def _rebuild(k=key):
            _ATLAS_CACHE["refresh_attempts"] = int(
                _ATLAS_CACHE.get("refresh_attempts", 0)) + 1
            try:
                payload = _atlas_board_module().build()
                _ATLAS_CACHE["payload"], _ATLAS_CACHE["at"], _ATLAS_CACHE["key"] = \
                    payload, time.time(), k
                # A failed refresh is attached to that failed attempt, not to the cache
                # forever. Keeping it after a later successful build made a current
                # receipt continue to render REFRESH FAILED until process restart.
                _ATLAS_CACHE.pop("refresh_error", None)
                _ATLAS_CACHE["refresh_attempts"] = 0
            except Exception as exc:  # noqa: BLE001 - a failed refresh keeps the last
                _ATLAS_CACHE["refresh_error"] = f"{type(exc).__name__}: {exc}"
            finally:
                _ATLAS_CACHE["building"] = False

        threading.Thread(target=_rebuild, name="atlas-board-refresh",
                         daemon=True).start()

    return _ATLAS_CACHE["payload"], _ATLAS_CACHE["at"], False


def _page_shell(title: str, body: str, head: str = "") -> str:
    """The skeleton a standalone door cannot invent for itself: doctype, head, viewport.

    Serving a page as a bare fragment leaves the browser to guess the rest. /front/atlas
    and /front/walk are both classed ``kind: "page"`` in front_places and neither is ever
    fetched into #panel, yet both went out bare until 2026-08-25: ``curl -s
    .../front/atlas | head -c 40`` began at ``<meta charset`` across 244,292 bytes, and
    no viewport meta was served on either. No doctype is quirks mode by definition (the
    audit read document.compatMode BackCompat in the browser). They escaped the white
    flash only because the producer's own inline CSS paints ``body`` — luck, and luck
    that says nothing about mobile width or the colour a form control or scrollbar picks.

    Two callers, one doctype. A producer that already renders its own title bar, back
    link and palette (the atlas board, the founding walk) takes THIS and nothing else —
    _document's chrome would sit on top of the producer's own at the same fixed top:0.
    A door with no furniture of its own takes _document, which is built on this.
    """
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(title)}</title>'
        # No palette here: the canvas ground is the one thing a fragment cannot set for
        # itself, and color-scheme alone hands it to the UA's dark canvas without this
        # shell inventing a colour its caller may not share.
        '<style>:root{color-scheme:dark}</style>'
        f'{head}</head><body>{body}</body></html>')


def _document(title: str, body: str, subtitle: str = "") -> str:
    """Wrap a standalone door in the house register: the shell, plus the house furniture.

    Fragments are correct for anything the shell fetches into #panel. A door the shell
    never fetches is a PAGE — _page_shell carries why that matters. On top of it this
    adds the same ground, ink, accent and a way back, for doors that render none of
    their own.
    """
    style = (
        '<style>'
        ':root{color-scheme:dark;--ground:#14161B;--card:#1C1F26;--ink:#E8E6E1;'
        '--dim:#9CA1AB;--gold:#D9A441;--bad:#D97862;--line:rgba(232,230,225,.12);'
        '--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}'
        'body{background:var(--ground);color:var(--ink);margin:0;'
        'font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}'
        '.wrap{padding:14px 22px 40px}'
        'a{color:var(--gold);text-decoration:none} a:hover{text-decoration:underline}'
        '.chrome{position:fixed;left:0;right:0;top:0;z-index:9;'
        'background:rgba(20,22,26,.94);backdrop-filter:blur(6px);'
        'border-bottom:1px solid var(--line);padding:10px 22px}'
        '.chrome a{font-weight:600}'
        'h1{font-size:17px;letter-spacing:.1em;text-transform:lowercase;color:var(--gold);'
        'margin:0 0 3px} h3{font-size:13px;color:var(--dim);margin:18px 0 7px}'
        '.sub{color:var(--dim);font-size:12px;margin:0 0 14px;max-width:78ch}'
        '.tablewrap{overflow:auto;max-height:none;border:1px solid var(--line);'
        'border-radius:4px;margin-bottom:16px}'
        'table{border-collapse:collapse;width:100%;font-size:12.5px}'
        'th{position:sticky;top:0;background:#20242C;color:var(--dim);text-align:left;'
        'padding:6px 9px;border-bottom:1px solid var(--line)}'
        'td{padding:5px 9px;border-bottom:1px solid rgba(232,230,225,.06);'
        'vertical-align:top;overflow-wrap:anywhere}'
        'td.num{text-align:right;font-family:var(--mono);white-space:nowrap}'
        'tr:hover td{background:rgba(232,230,225,.05)}'
        'tr.red td{color:var(--bad)}'
        '</style>')
    return _page_shell(title, (
        '<div class="chrome"><a href="/front">← the front door</a></div>'
        '<div class="wrap" style="padding-top:52px">'
        f'<h1>{escape(title)}</h1>'
        + (f'<p class="sub">{escape(subtitle)}</p>' if subtitle else "")
        + body + '</div>'), head=style)


def prewarm_atlas(block: bool = False) -> None:
    """Bank the first receipt off the request path.

    Without this the FIRST /front/atlas after a restart pays the full ~9s build, which is
    precisely the request most likely to be his — he opens the door, the service having
    come up at login, and waits nine seconds at the surface he came to walk. Opt out with
    LAPLACE_NO_PREWARM=1 (tests, cold tooling).
    """
    if os.environ.get("LAPLACE_NO_PREWARM"):
        return

    def _go() -> None:
        try:
            t0 = time.time()
            _atlas_cached_payload()
            print(f"scanner: pre-warm done (atlas board receipt, "
                  f"{time.time() - t0:.1f}s)", flush=True)
        except Exception as exc:  # noqa: BLE001 - never take the door down to warm it
            print(f"scanner: atlas pre-warm failed ({exc})", flush=True)

    if block:
        _go()
        return
    threading.Thread(target=_go, name="atlas-board-prewarm", daemon=True).start()


# NOT called at import: scanner._prewarm() drives this, once, on its own thread. Calling
# it here as well raced the scanner's call and ran TWO full 12s builds concurrently
# (observed in the unit log: two "atlas board receipt" lines, 12.1s and 12.6s) — pure
# waste, and on a 31GB box that already OOM-killed a session today, a real risk.


def _frag_atlas_board() -> str:
    """The human register of the CACHED board receipt, whose age the page states.

    It said "from the exact same freshly built payload" until 2026-08-25. True when
    written; false from 7d59d01c, which moved both registers onto _atlas_cached_payload()
    (a fresh build is ~9s) and cured the sibling docstring in the same commit while this
    one kept asserting freshness. The body three lines down already contradicts it —
    "served from a receipt computed N ago", and "REFRESH FAILED … this board is NOT
    live" when the rebuild thread is stuck.

    AND THE SENTENCE THAT REPLACED IT WAS ALSO FALSE, which is the whole disease: it said
    ``fresh`` is True on exactly one request PER DRIFT KEY. It is True on exactly one
    request PER PROCESS. _atlas_cached_payload returns it from a single branch — the
    cold-cache path, "payload" not in _ATLAS_CACHE — and every later drift key rebuilds
    OFF-THREAD and returns False. Planted: three drift keys over eight requests produced
    fresh=True once, on request one, and never again while three builds actually ran.
    So the receipt line below reading "built on this request" is unreachable after the
    first request of a long-lived server, and this docstring asserted a cadence the code
    does not have while correcting a docstring that asserted a state the code does not
    have. The receipt line is the authority on age; nothing in this docstring may outrank
    it, including this paragraph.

    ``home="/front"`` is what makes this a room rather than a cul-de-sac: the board is
    its own page (like /seats), not a hash route of the shell, so nothing but this
    argument gives the reader a way back. Measured before the cure: 218,723 served
    bytes carrying 0 anchors and 0 buttons — his walk landed on the largest surface we
    serve and could only leave it with the browser's back button.
    """
    board = _atlas_board_module()
    payload, at, fresh = _atlas_cached_payload()
    age = max(0.0, time.time() - at)
    # AN ERROR ALWAYS WINS THE LABEL (ego-seat's B2, observed in production, not
    # simulated: pid 344745, six samples over 71s, all produced_at 11:07:42Z, the chrome
    # reading "rebuilding now — reload in a moment" while the body read "LIVE (chain
    # verified on this read)" and the pane served 52/33 against ledgers computing 48/32).
    # Root cause: _atlas_board_module is lru_cached and laplace.* is sys.modules-cached
    # at process start, so a mid-flight commit loads a NEW producer against the OLD
    # in-process package and the refresh fails forever. Testing `building` FIRST made a
    # permanently-failing refresh present as a permanently-in-progress one — the most
    # reassuring possible rendering of the worst possible state.
    failed = _ATLAS_CACHE.get("refresh_error")
    tries = int(_ATLAS_CACHE.get("refresh_attempts", 0))
    if fresh:
        # reachable ONLY on the first request of a process, by construction — see the
        # docstring. It is kept because that request is real and its age genuinely is
        # zero; it is not kept as a general "this is live" signal, which it cannot be.
        receipt = "built on this request — the first of this process, nothing banked yet"
    elif failed:
        receipt = (f"REFRESH FAILED ({escape(str(failed)[:80])}) · showing the receipt "
                   f"from {_age_words(age)} ago · this board is NOT live and will not "
                   f"become live until that error clears")
    elif _ATLAS_CACHE.get("building"):
        # bounded: an unbounded "rebuilding now" is indistinguishable from a hang, and
        # the reader has no way to tell a 2s rebuild from one that will never finish.
        stuck = age > 120 or tries > 3
        receipt = (f"the stores moved · this is the receipt from {_age_words(age)} ago, "
                   + (f"and {tries} rebuild attempt(s) have not landed — treat this as "
                      f"STALE, not as in progress"
                      if stuck else
                      "rebuilding now — reload in a moment for the new one"))
    else:
        receipt = (f"served from a receipt computed {_age_words(age)} ago · "
                   f"rebuilds the instant any source store moves")
    return board.render_html(payload, home="/front", receipt=receipt)


@lru_cache(maxsize=1)
def _walk_serve_module():
    """The founding walk-serve producer (the cursor-260 slice) — one producer, two registers."""

    source = _repo_root() / "scripts" / "atlas_walk_serve.py"
    spec = importlib.util.spec_from_file_location("laplace_walk_serve", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"walk serve producer cannot be loaded from {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _walk_serve_get(query: dict) -> tuple[int, str, bytes]:
    """GET /front/walk — the founding cards, or (?handle=) an exact-span descent.

    Descent REFUSES on any miss (absent file, bad range, escape) — never a parent echo;
    the span's own bytes carry the sha256 (the seam's granularity cure).

    Every HTML arm here is a PAGE — front_places classes /front/walk ``kind: "page"`` and
    the shell never fetches it — so every one leaves through _page_shell. All three were
    served bare until 2026-08-25 (doctype absent, quirks mode); the descent arm was worse
    than the others, opening a naked ``<body style=…>`` inside what the browser had
    already made a body, so its ground survived only by the parser's attribute-merge rule.
    """
    m = _walk_serve_module()
    h = _q1(query, "handle").strip()
    if h:
        expect = _q1(query, "expect").strip() or None
        r = m.resolve_handle(h, expect_text_sha=expect)
        status = 200 if "error" not in r else 404
        if _q1(query, "format") == "json":
            return status, _JSON, json.dumps(r, ensure_ascii=False).encode("utf-8")
        if "error" in r:
            return status, _HTML, _page_shell(
                "walk descent refused",
                f'<p style="color:#ef9a9a;font-family:monospace">'
                f'{escape(r["error"])}</p>'
                f'<p><a style="color:#7fb3ff" href="/front/walk">back to the walk</a></p>',
                head='<style>body{background:#14161a;color:#d7dae0;'
                     'font:14px/1.5 monospace;margin:0;padding:18px 22px}</style>',
            ).encode("utf-8")
        drift = ""
        if r.get("drift"):
            drift = (f'<div style="color:#ffd54f;margin-bottom:7px">DRIFT — this ground '
                     f'moved since minting (shown-then {escape(r["drift"]["expected"][:16])}…, '
                     f'now {escape(r["drift"]["found"][:16])}…); the shown-then object lives '
                     f'in serve custody.</div>')
        return 200, _HTML, _page_shell(
            f"walk descent · {h}",
            f'<div style="color:#5f6b7a;margin-bottom:9px">{escape(h)} · text-span sha256:'
            f'{escape(r["span_text_sha256"][:24])}… · file sha256:'
            f'{escape(r["file_sha256"][:16])}…'
            f' · <a style="color:#7fb3ff" href="/front/walk">back to the walk</a></div>'
            f'{drift}'
            f'<pre style="white-space:pre-wrap;margin:0">{escape(r["content"])}</pre>',
            head='<style>body{background:#14161a;color:#d7dae0;'
                 'font:14px/1.5 monospace;margin:0;padding:18px 22px}</style>',
        ).encode("utf-8")
    b = m.build()
    if _q1(query, "format") == "json":
        return 200, _JSON, json.dumps(b, ensure_ascii=False).encode("utf-8")
    # The producer renders its own chrome, back link, title and palette; the shell adds
    # only the skeleton it cannot emit from inside a fragment.
    return 200, _HTML, _page_shell("the founding walk",
                                   m.render_html(b, home="/front")).encode("utf-8")


def _walk_serve_verdict(body: bytes) -> tuple[int, str, bytes]:
    """POST /front/walkserve — bank HIS verdict on a founding card, shown-digest gated.

    The anti-generic gates, live: no verdict without its shown digest; a moved serve
    REFUSES as 409 (refuse-stale is a status code, not a badge); an amend/redline without
    words cures nothing.

    THE ID SUFFIX IS NOT AUTHORITY, and this said it was: "an ACCEPT id ends in
    ``-walked`` — the exact substring the producer's open-state scan closes on". The
    producer is scripts/atlas_walk_serve.py, whose own stated law is "TYPED CLOSURE …
    No id-suffix authority": _walked_cards() closes on record=walk-verdict ·
    verdict=accepted · actor=gerard · stage starting ``founding-`` · a shown_handle that
    RESOLVES in custody, or on an exact id in HISTORICAL_CLOSURES. ``-walked`` appears
    there once, as one of three cheap line substrings that decide what is worth
    json.loads-ing, beside "walk-verdict" — which every accept row carries anyway.
    Measured against a temp store: an accept row minted with a NO-SUFFIX id still closed
    its card ({'cardX': {'row': 'RES-…-founding-cardX-NO-SUFFIX', …, 'custody':
    'resolves'}}). The suffix minted below is a readable convention in the id and
    nothing more; the five typed fields are what make an accept an accept."""
    from laplace.core.records import journal as _journal
    try:
        req = json.loads(body or b"{}")
        assert isinstance(req, dict)
    except (ValueError, AssertionError):
        return 400, _JSON, b'{"error": "body must be a JSON object"}'
    card = str(req.get("card", "")).strip()
    verdict = str(req.get("verdict", "")).strip().lower()
    text = str(req.get("text", "")).strip()[:4000]
    shown = str(req.get("shown_handle", "")).strip()
    if verdict not in ("accept", "amend", "refuse"):
        return 400, _JSON, b'{"error": "verdict must be accept, amend, or refuse"}'
    if verdict != "accept" and not text:
        return 400, _JSON, b'{"error": "words first - a bare amend/redline cures nothing"}'
    if not shown:
        return 400, _JSON, (b'{"error": "a walk without its shown digest is refused - '
                            b'the ruling must cite exactly what was seen"}')
    m = _walk_serve_module()
    b = m.build()
    open_ids = [c["id"] for c in ([b["anchor"]] if b["anchor"] else []) + b["rails"]]
    if card not in open_ids:
        return 400, _JSON, json.dumps(
            {"error": f"card {card!r} is not open (walked already, or unknown) - reload"}
        ).encode("utf-8")
    if shown != b["serve_digest"]:
        return 409, _JSON, (b'{"error": "the serve moved since you were shown it - '
                            b'REFUSED stale; reload re-derives"}')
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%S")
    if verdict == "accept":
        row = {"record": "walk-verdict", "id": f"RES-{stamp}-founding-{card}-walked",
               "stage": f"founding-{card}", "verdict": "accepted"}
    elif verdict == "amend":
        row = {"record": "walk-amendment", "id": f"AMEND-{stamp}-founding-{card}",
               "stage": f"founding-{card}", "verdict": "amend"}
    else:
        row = {"record": "walk-redline", "id": f"WALKRED-{stamp}-founding-{card}",
               "stage": f"founding-{card}", "verdict": "redline"}
    row.update({"text": text, "shown_handle": shown, "actor": "gerard",
                "via": "front-door", "ts": now.isoformat()})
    try:
        _journal.bank_row("corpus_friction/work_orders.jsonl", row, root=_repo_root())
    except Exception as e:  # noqa: BLE001
        return 500, _JSON, json.dumps(
            {"error": f"the bank failed and NOTHING was appended: "
                      f"{type(e).__name__}: {e}"}).encode("utf-8")
    remaining = len(open_ids) - (1 if verdict == "accept" else 0)
    return 200, _JSON, json.dumps({"banked": row["id"], "card": card,
                                   "verdict": row["verdict"],
                                   "open_count": remaining}).encode("utf-8")


def _q1(query: dict, key: str, default: str = "") -> str:
    v = query.get(key, [default])
    return v[0] if isinstance(v, list) else (v or default)


def _qint(query: dict, key: str, default: int, max_: int) -> int:
    """A query integer that can NEVER raise through the door. The scanner's do_GET has
    no top-level handler, so a ValueError here kills the request with no HTTP response
    at all — a hand-typed `?limit=abc` took the connection down (the review's finding,
    2026-08-24). Junk and absurdities serve the default or the cap, in that order."""
    raw = _q1(query, key, "").strip()
    if not raw:
        return default
    try:
        n = int(raw)
    except ValueError:
        return default
    return default if n < 1 else min(n, max_)


def _qoff(query: dict, key: str = "off") -> int | None:
    """A byte offset from the query, or None. Digits alone are not enough: CPython
    refuses int() past 4300 digits, which raises exactly like the junk above."""
    raw = _q1(query, key).strip()
    return int(raw) if raw.isdigit() and len(raw) <= 18 else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age_words(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    s = max(0, int(seconds))
    if s < 90:
        return f"{s}s"
    if s < 5400:
        return f"{s // 60}m"
    if s < 172800:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def _ts_age(ts: Any) -> str:
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
        return _age_words(time.time() - t)
    except (TypeError, ValueError):
        return "?"


def _byline(name: str, extra: str = "") -> str:
    """The panel footer the interface law demands: source path + freshness, RED past
    budget. Every fragment ends in one."""
    st = _sources.stat(name)
    if st.get("error"):
        return (f'<div class="byline red">[source] {escape(name)} — '
                f'{escape(str(st["error"]))}</div>')
    if st.get("absent"):
        return (f'<div class="byline red">[source] {escape(st.get("path", name))} '
                f'— ABSENT</div>')
    red = ' red' if st.get("red") else ''
    return (f'<div class="byline{red}">[source] {escape(st["path"])} · '
            f'{st["bytes"]:,} B · mtime {_age_words(st["age_s"])} ago'
            f'{" · " + escape(extra) if extra else ""}</div>')


def _chip(text: str, cls: str = "") -> str:
    return f'<span class="chip {cls}">{escape(str(text))}</span>'


# ------------------------------------------------------------------ apex

def _apex_data() -> dict[str, Any]:
    from laplace.web import seats_surface as _seats
    from laplace.engine import wake
    root = _repo_root()
    out: dict[str, Any] = {"rendered_at": _now_iso(), "row_sources": {
        "account": "laplace.engine.wake.account_capped (same code path as scripts/wake.py --account)",
        "campaign": "laplace.engine.wake.campaign(run_gates=False) — banked verdicts, age-stamped",
        "asks": "corpus_friction/work_orders.jsonl (open ASK-* rows)",
        "sources": "the front-door registry (laplace.engine.sources) + os.stat per store",
    }}
    try:
        out["account"] = wake.account_capped(root)
    except Exception as e:  # noqa: BLE001 — a broken organ serves its error, never a crash
        out["account"] = {"error": f"{type(e).__name__}: {e}"}
    try:
        out["campaign"] = wake.campaign(root, run_gates=False)
    except Exception as e:  # noqa: BLE001
        out["campaign"] = {"error": f"{type(e).__name__}: {e}"}
    try:
        out["asks"] = _seats._pending_asks(root)
    except Exception as e:  # noqa: BLE001
        out["asks"] = []
        out["asks_error"] = f"{type(e).__name__}: {e}"
    out["sources"] = _sources.roster()
    return out


#: campaign status enums -> the author's words (the _STATE_WORDS discipline from
#: dashboard.py: never serve a raw state enum as a position; the picture reads in
#: words, not machine caps).
_CAMP_WORDS = {
    "DONE": "done", "OPEN": "open", "UNRUN": "never run",
    "ABSORBED": "absorbed into the Atlas rebuild",
    "BLOCKED-ON-AUTHOR": "waiting on your ruling",
}


def _first_clause(text: str, n: int = 110) -> str:
    t = " ".join(str(text).split())
    for stop in (". ", " — ", " - ", "; "):
        i = t.find(stop)
        if 0 < i < n:
            return t[: i + (1 if stop == ". " else 0)]
    return t[:n] + ("…" if len(t) > n else "")


def _last_close_ts() -> tuple[float | None, str]:
    """The newest session handoff's mtime — 'since the last close' anchors here.
    The handoff file is a render; only its TIMESTAMP is used, never its content."""
    newest, name = None, ""
    try:
        for p in _repo_root().glob("SESSION_HANDOFF_*.md"):
            m = p.stat().st_mtime
            if newest is None or m > newest:
                newest, name = m, p.name
    except OSError:
        pass
    return newest, name


def _frag_apex(seen: float | None = None) -> str:
    """THE BRIEF — the author's register (his redline at the first walk, 2026-08-24:
    the engine's internal vocabulary is the wrong projection for his eyes; the fibre
    law's register(audience) applied). Delta-and-ask PROSE composed from rows at
    render — the _compose_glance discipline generalized — with the descend behind
    the words: every load-bearing phrase links to the rows that ground it. No id
    renders where a sentence can carry it; ids live one click down.

    ``seen`` is the author's own last-look instant (client-held, never a store):
    when given, the now-zone adds a since-YOUR-last-look count — the attention law's
    second face: what changed for HIM glows, what he has already seen recedes."""
    d = _apex_data()
    acct = d.get("account", {})
    camp = d.get("campaign", {})
    asks = d.get("asks", [])
    # no source is exempt from its own budget: the brief and the engine room must
    # answer "which stores are stale" with the SAME list, or the brief is a second
    # opinion (the review's finding, 2026-08-24 — liveness was hardcoded out here
    # and counted there).
    # `concern`, not `red`: a founding ledger that has not moved in 24h has nothing wrong
    # with it. Spending his attention on healthy silence is how a brief teaches him to
    # stop reading it. An ABSENT store is always a concern — that is a missing file, not
    # a quiet one.
    stale = [s for s in d["sources"] if s.get("concern") or s.get("absent")]
    paras: list[str] = []

    if acct.get("error"):
        paras.append(f'<p class="red">The account organ itself failed: '
                     f'{escape(acct["error"])} — nothing below can be trusted '
                     f'until it fires.</p>')
    # (his second redline, 2026-08-24: the emission below this point is composed
    # into ZONES for attention, not paragraphs for reading — see the board build
    # at the foot of this function; the sentence composition above it survives
    # only as captions under anchors.)

    # -- since the last close: the delta, in words --------------------------------
    since_ts, handoff = _last_close_ts()
    acts_n = banks_n = 0
    seen_acts = 0
    running: list[dict[str, Any]] = []
    for a in _trace.acts(200):
        if seen and a.get("start") and a["start"] >= seen:
            seen_acts += 1
        if a["state"] == "in-flight":
            running.append(a)
        if since_ts and a.get("start") and a["start"] >= since_ts:
            acts_n += 1
            banks_n += a.get("n_banks", 0)
    gates_since = reds_since = 0
    if since_ts:
        for _o, row in _rows.scan("campaign"):
            if row.get("record") == "gate-verdict":
                try:
                    t = datetime.fromisoformat(
                        str(row.get("ts")).replace("Z", "+00:00")).timestamp()
                except (TypeError, ValueError):
                    continue
                if t >= since_ts:
                    gates_since += 1
                    if row.get("exit") != 0:
                        reds_since += 1
    # -- what needs him: anchors, not sentences ------------------------------------
    needs: list[dict[str, Any]] = []
    # a CAUGHT organ failure is not a seen one: _apex_data swallows these so a broken
    # organ never takes the door down, and before this they rendered as silence on his
    # primary panel (the review's finding, 2026-08-24). They lead the zone, loudly.
    if d.get("asks_error"):
        needs.append(dict(
            anchor="ORGAN DOWN", age="", hot="hot bad", mine=False,
            cap=f'the permission-ask lane could not be read — {d["asks_error"]} — '
                f'asks may be waiting that this board cannot see',
            clears="it clears when the lane reads again; until then this board cannot "
                   "promise you have seen everything waiting on you",
            hand="a seat clears this, not you",
            href="/seats"))
    if camp.get("error"):
        needs.append(dict(
            anchor="ORGAN DOWN", age="", hot="hot bad", mine=False,
            cap=f'the campaign organ could not be read — {camp["error"]} — the next '
                f'act, its gates and any ruling waiting on you are unknown',
            clears="it clears when the campaign organ reads again",
            hand="a seat clears this, not you",
            href="#campaign"))
    for a in sorted(asks, key=lambda r: str(r.get("ts", "")))[:3]:
        needs.append(dict(
            anchor="permission", age=_ts_age(a.get("ts")), hot="hot", mine=True,
            cap=_first_clause(str(a.get("text") or a.get("what") or a.get("id")), 88),
            clears="approve or refuse, right here — your click banks the decision row",
            hand="· yours",
            href="/seats", ask=str(a.get("id", ""))))
    for st in (camp.get("stages") or []):
        juris = str(st.get("jurisdiction", ""))
        if "blocked_on=author" in juris or st.get("status") == "BLOCKED-ON-AUTHOR":
            needs.append(dict(
                anchor="your ruling", age="", hot="", mine=True,
                cap=_first_clause(str(st.get("title", st.get("id"))), 88),
                clears="this stage is blocked on you and no seat may move it — it "
                       "clears when you rule",
                hand="· yours alone",
                href="#campaign"))
    if stale:
        worst = stale[0]
        absent = bool(worst.get("absent"))
        needs.append(dict(
            anchor="gone quiet", hot="", mine=False,
            age=("absent" if absent else _age_words(worst.get("age_s"))),
            cap=f'{len(stale)} store{"s" if len(stale) != 1 else ""} past freshness '
                f'budget — worst {worst["name"]} ({worst.get("label", "")})',
            clears=("the file is missing entirely — the organ that writes it must run, "
                    "or the source is retired and should leave the registry"
                    if absent else
                    f'this is a live feed that has stopped: whatever writes '
                    f'{worst["name"]} has not run inside its '
                    f'{_age_words(worst.get("budget_s"))} budget. It clears when that '
                    f'organ next writes — not by anything done here.'),
            hand="a seat clears this, not you",
            href="#organ"))

    # -- the pile, computed --------------------------------------------------------
    wo = acct.get("work_orders_open")
    open_rows = []
    try:
        from laplace.engine import wake
        open_rows = (wake.account(_repo_root()).get("work_orders", {})
                     .get("open_rows", []) or [])
    except Exception:  # noqa: BLE001
        pass
    now = time.time()
    fresh = stale_wo = 0
    for r in open_rows:
        # the account's open_rows carry a bare `date` (YYYY-MM-DD), not a ts —
        # verified against wake.account() 2026-08-24; parse what is actually there.
        raw = r.get("date") or r.get("ts") or ""
        try:
            t = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            continue
        if now - t < 7 * 86400:
            fresh += 1
        elif now - t > 14 * 86400:
            stale_wo += 1

    # ============================ EMISSION: THE BOARD ============================
    # His second redline (2026-08-24): he has neither this seat's bandwidth nor its
    # linear reading capacity — the compensation is ATTENTION. Stable zones whose
    # positions never move between visits; state pre-attentive (size, weight,
    # colour, position); one large anchor per zone; sentences demoted to captions
    # read only AFTER attention lands. Every anchor still descends to its rows.
    # HIS ATTENTION IS THE SCARCE THING, so the count is of what HE can discharge.
    # His steer, 2026-08-25, standing at this zone: the door "is complaining about ages
    # on stores and yet tells me it needs me but that I don't need to do anything."
    # It was true. The previous cure gave every entry a `hand` line saying "a seat clears
    # this, not you" and then LEFT IT IN THE COUNT — so the badge read `1 NEEDS YOU` over
    # a body saying he could do nothing about it. An explanation of a contradiction is
    # not a resolution of one. The partition is now structural: `mine` decides the zone,
    # and nothing a seat clears may ever inflate the number over his name.
    mine_needs = [n for n in needs if n.get("mine")]
    owed_needs = [n for n in needs if not n.get("mine")]
    n_need = len(mine_needs)
    n_owed = len(owed_needs)

    z1 = [f'<section class="zone z-needs{" hot" if n_need else ""}">',
          f'<div class="bignum{" warn" if n_need else " ok"}">{n_need}</div>',
          f'<div class="zlabel">need{"s" if n_need == 1 else ""} you</div>']
    if mine_needs:
        z1.append('<ul class="anchors">')
        for n in mine_needs:
            age = (f'<span class="age">{escape(n["age"])}</span>' if n["age"] else "")
            # THE ASK-DOOR (M2 slice): a pending permission carries its act buttons
            # right on the anchor — his click banks his decision row; the surface
            # never decides, it only carries his hand.
            acts = ""
            if n.get("ask"):
                aid = escape(n["ask"])
                acts = (f'<span class="actbtns" data-ask="{aid}">'
                        f'<button type="button" class="act ok" data-decide="approve">'
                        f'approve</button>'
                        f'<button type="button" class="act bad" data-decide="refuse">'
                        f'refuse</button></span>')
            # WHOSE HAND, AND WHAT WOULD CLEAR IT. His steer, 2026-08-25, standing at
            # exactly this zone: "I see seats is red but know neither what that means or
            # what I'm supposed to do about it. Indeed, what I _can_ do about it."
            # An anchor that names a state without naming the act that ends it is a
            # demand on his attention with no way to discharge it. Every entry now
            # carries one, and `hand` says plainly when the answer is "not yours".
            hand = ""
            if n.get("clears"):
                whose = n.get("hand", "")
                hand = (f'<div class="clears">{escape(n["clears"])}'
                        + (f' <span class="whose">{escape(whose)}</span>' if whose else "")
                        + "</div>")
            z1.append(f'<li class="{n["hot"]}"><a href="{escape(n["href"])}">'
                      f'<b>{escape(n["anchor"])}</b></a>{age}{acts}'
                      f'<div class="cap">{escape(n["cap"])}</div>{hand}</li>')
        z1.append("</ul>")
    else:
        z1.append('<div class="cap dim">nothing is waiting on you</div>')
    if owed_needs:
        # NOT HIDDEN — degraded organs and stopped feeds are exactly what he should be
        # able to see. Only DEMOTED, under their own heading, outside his count, so the
        # zone that asks for his hand only ever contains things his hand can finish.
        z1.append(f'<div class="owed"><div class="zlabel owedlbl">'
                  f'the engine owes itself {n_owed}</div>'
                  f'<div class="cap dim">visible so nothing rots unseen — a seat clears '
                  f'these, and none of them is waiting on you</div>'
                  f'<ul class="anchors quiet">')
        for n in owed_needs:
            age = (f'<span class="age">{escape(n["age"])}</span>' if n["age"] else "")
            # the hand phrase rides the CARD as well as the heading: a reader who
            # lands on one anchor from a deep link never sees the zone label above it.
            whose = n.get("hand", "")
            clears = (f'<div class="clears">{escape(n["clears"])}'
                      + (f' <span class="whose">{escape(whose)}</span>' if whose else "")
                      + "</div>") if n.get("clears") else ""
            z1.append(f'<li><a href="{escape(n["href"])}">'
                      f'<b>{escape(n["anchor"])}</b></a>{age}'
                      f'<div class="cap">{escape(n["cap"])}</div>{clears}</li>')
        z1.append('</ul></div>')
    z1.append("</section>")

    glyph, gcls, gword = (("◐", "warn", f"{len(running)} in flight") if running
                          else ("●", "ok", "quiet"))
    dstats = []
    if since_ts:
        ago = _age_words(time.time() - since_ts)
        dstats.append(f'<a class="dstat" href="#run"><b>{acts_n}</b>'
                      f'<i>acts since close ({ago})</i></a>')
        dstats.append(f'<a class="dstat" href="#run"><b>{banks_n}</b>'
                      f'<i>rows banked</i></a>')
    if seen is not None:
        cls = " okst" if seen_acts == 0 else ""
        word = "nothing new" if seen_acts == 0 else f"{seen_acts} new"
        dstats.append(f'<a class="dstat{cls}" href="#run"><b>{seen_acts or "✓"}</b>'
                      f'<i>{word} since your last look '
                      f'({_age_words(time.time() - seen)})</i></a>')
        if gates_since and reds_since:
            dstats.append(f'<a class="dstat bad" href="#campaign"><b>{reds_since}✗</b>'
                          f'<i>of {gates_since} gates fired</i></a>')
        elif gates_since:
            dstats.append(f'<a class="dstat okst" href="#campaign"><b>{gates_since}✓</b>'
                          f'<i>gates, all green</i></a>')
    run_href = (f'#trace/{escape(running[0]["act_id"])}' if running else "#run")
    z2 = (f'<section class="zone z-now"><a href="{run_href}">'
          f'<div class="glyphbig {gcls}">{glyph}</div></a>'
          f'<div class="zlabel">{escape(gword)}</div>'
          f'<div class="dstats">{"".join(dstats)}</div></section>')

    total = max(1, len(open_rows))
    mid = max(0, len(open_rows) - fresh - stale_wo)
    agebar = ""
    if open_rows:
        agebar = (
            '<div class="agebar" title="age of the open orders">'
            f'<span class="seg s-fresh" style="width:{100 * fresh / total:.0f}%"></span>'
            f'<span class="seg s-mid" style="width:{100 * mid / total:.0f}%"></span>'
            f'<span class="seg s-dead" style="width:{100 * stale_wo / total:.0f}%"></span>'
            "</div>"
            f'<div class="cap">{fresh} this week · {mid} older · {stale_wo} '
            f'look{"s" if stale_wo == 1 else ""} dead — retiring one is your call</div>')
    # the number and its rows share ONE producer: `open:account` resolves through the
    # account organ's own open set, not a `status:open` substring that matched 298 rows
    # against a headline of 41 (the review's finding, 2026-08-24). The defects count
    # has no store to descend to — that gap is DECLARED in the title, never silent.
    z3 = (f'<section class="zone z-pile">'
          f'<a href="#explore/work_orders/{escape(_rows.ACCOUNT_OPEN)}">'
          f'<div class="bignum">{wo}</div></a>'
          f'<div class="zlabel">orders open</div>{agebar}'
          f'<div class="cap dim">'
          f'<a href="#explore/promises/status:open">'
          f'{acct.get("promises_open", "?")} promises</a> · '
          f'<span title="the defects ledger rides the account '
          f'(scripts/wake.py --account) — no store to descend to yet">'
          f'{acct.get("defects", "?")} defects</span></div></section>')

    z4 = ""
    next_act = camp.get("next_act")
    if next_act:
        title = next((str(s.get("title", "")) for s in camp.get("stages", [])
                      if s.get("id") == next_act), "")
        z4 = (f'<section class="zone z-next">'
              f'<div class="zlabel">the engine’s next act</div>'
              f'<a class="anchorbig" href="#campaign">'
              f'{escape(_first_clause(title or str(next_act), 70))}</a>'
''
              f"</section>")

    # THE WORK PRIORITY STACK — his ask at contract/talk.jsonl 19:14Z: "I'm finding it
    # quite hard to _read_ the current status of everything... a work priority stack would
    # be helpful on both sides of the fabric." It lands HERE, on the brief he already
    # opens, rather than as a twelfth tab — he has said three times that a new capability
    # arriving as a new row of chrome is the failure, not the fix.
    # THE APEX IS THE ONE PANE THAT SCORES ZERO BARE HANDLES IN THE DEFAULT REGISTER
    # (stranger audit, 2026-08-25: 0 here against 201 / 175 / 123 / 63 / 53 elsewhere).
    # So every row below leads with its FACE and carries its id in title= only.
    z5 = ""
    try:
        from laplace.web import priority as _prio
        pst = _prio.stack(_repo_root())
        pt = pst["totals"]
        blocked = pst["blocking"][:5]
        z5 = (f'<section class="zone z-stack"><div class="zlabel">what to work on next</div>'
              f'<div class="cap dim">{escape(pst["order"])}</div>')
        if blocked:
            z5 += (f'<div class="stacklab">{pt["blocking_open"]} blocking · '
                   f'{pt["major_open"]} major — these gate other work</div><ul class="anchors">')
            for r in blocked:
                # EVERY THING HE IS TOLD ABOUT IS A THING HE CAN OPEN, WHERE HE IS.
                # The zero-context law says context is summonable WITH his attention and
                # invisible otherwise — so a blocking finding that renders as text is a
                # demand on his attention with no way to satisfy it, and a tab bar is the
                # surface making him navigate by hand because it cannot route him.
                # #record/<store>/id:<id> is the descent that already exists and already
                # opens in the slide-over with Escape returning. No new machinery.
                z5 += (f'<li title="{escape(str(r["id"]))}">'
                       f'<a href="#record/work_orders/id:{escape(str(r["id"]))}">'
                       # NO SECOND TRUNCATION. face is already capped at 110 upstream
                       # WITH an rstrip and a comment saying a face must not end badly;
                       # this cut had neither, and shipped three of five blocking
                       # headlines ending mid-word with no ellipsis and no title:
                       # "...WHILE THE BODY SAYS LIVE - observed in ",
                       # "...ACHIEVING NOTHING, ON THE STORE EVERY I",
                       # "...it is advisory by a ruling whose ".
                       f'<b>{escape(r["face"])}</b></a>'
                       f'<span class="age">{escape(r["severity"])}</span></li>')
            z5 += "</ul>"
        cols = [c for c in pst["by_seat"] if not c.get("error")]
        if cols:
            z5 += '<div class="stacklab">both sides of the fabric — open work by seat</div>'
            z5 += '<div class="seatcols">'
            for c in cols:
                # a count he cannot open is a number; a count he can open is a door.
                z5 += (f'<a class="seatcol" '
                       f'href="#explore/work_orders/seat:{escape(c["seat"])}" '
                       f'title="{c["counts"]["typed"]} of these carry a typed '
                       f'owner/owed_by naming {escape(c["seat"])}; the rest are matched '
                       f'on prose and are a guess">'
                       f'<b>{escape(c["seat"])}</b>'
                       f'<span class="n">{c["counts"]["by_store"]["work_orders"]["open"]}</span>'
                       f'<span class="d">'
                       f'{c["counts"]["by_store"]["work_orders"]["typed"]} typed · '
                       f'{c["counts"]["by_store"]["promises"]["open"]} promises</span></a>')
            z5 += "</div>"
        z5 += (f'<div class="clears">{escape(pst["cannot_see"])}</div>'
               f'<div class="clears">{escape(pst["severity_vocabulary"])}</div></section>')
    except Exception as exc:  # noqa: BLE001 - a stack that cannot build says so, loudly
        z5 = (f'<section class="zone z-stack"><div class="zlabel">what to work on next</div>'
              f'<div class="cap">the priority stack could not be built — '
              f'{escape(f"{type(exc).__name__}: {exc}")}</div>'
              f'<div class="clears">this zone is the only thing affected; every other panel '
              f'on this page reads its own rows.</div></section>')

    pull = (f'{n_need} thing{"s" if n_need != 1 else ""} need you'
            if n_need else "nothing needs you right now")
    # the owed count rides BESIDE his, never inside it — the strip is the first thing he
    # reads and it must not promise a demand it cannot cash.
    if n_owed:
        pull += f' · {n_owed} the engine owes itself'
    pull += " · " + (f"{len(running)} in flight" if running else "engine quiet")
    strip = (f'<div class="strip"><a class="stat{" warn" if n_need else ""}" '
             f'href="#apex">{escape(pull)}</a></div>')
    return (strip + "".join(paras)
            + '<div class="board">' + "".join(z1) + z2 + z3 + z4 + "</div>" + z5
            + _frag_walkstrip()
            + f'<div class="byline" title="{escape(d["row_sources"]["account"])} · '
            f'anchor {escape(handoff or "no close yet")} · rendered '
            f'{escape(d["rendered_at"])}">source: the account · journal and campaign, '
            f'read at render · {escape(str(d["rendered_at"])[11:16])} · raw rows in '
            f'<a href="#organ">the engine room</a></div>')


# ------------------------------------------------------------------ campaign grid

#: row-id shapes that resolve to a record pane, routed by prefix (PV/RUL rulings live
#: in proxy_verdicts; everything else banks in the work-orders store).
_REF_RE = re.compile(r"\b((?:PV|RUL|NOTE|WO|AMEND|RES|PRM|ASK|CAMP|VERDICT)-[A-Za-z0-9.\-]+)")


def _linkify_refs(text: str) -> str:
    """Escape, then turn every banked row id in free text into its descend link —
    the WHY of a stage names the rulings that commissioned it, and those must be
    one click away, never bare ids (his campaign redline, 2026-08-24)."""
    out = escape(text)

    def _sub(m: re.Match) -> str:
        rid = m.group(1)
        src = "proxy_verdicts" if rid.startswith(("PV-", "RUL-")) else "work_orders"
        return f'<a href="#record/{src}/id:{rid}">{rid}</a>'

    return _REF_RE.sub(_sub, out)


def _why_card(st: dict[str, Any], raw: dict[str, Any] | None = None) -> str:
    """The stage's WHY, unfolded on demand (his campaign redline, 2026-08-24: 'why
    are these campaign stages existing, what are they trying to find?'). Two
    producers, both verbatim-faithful: the campaign organ's flattened stage
    (``gate_expect``, ``source``) and the store's own raw stage row (which alone
    carries ``jurisdiction`` and the full ``gate.expect``). Where neither banks a
    why, that absence renders loudly and travels as a row-gap."""
    raw = raw or {}
    bits: list[str] = []
    source = str(st.get("source") or raw.get("source") or "").strip()
    if source:
        bits.append(f'<div class="whyrow"><span class="whylabel">why it exists</span> '
                    f'{_linkify_refs(source)}</div>')
    else:
        bits.append('<div class="whyrow warn">no why banked on this stage row — '
                    'a row-gap; it travels to the Ego</div>')
    expect = str(st.get("gate_expect")
                 or (raw.get("gate") or {}).get("expect") or "").strip()
    if expect:
        bits.append(f'<div class="whyrow"><span class="whylabel">what the gate proves'
                    f'</span> {_linkify_refs(expect)}</div>')
    juris = str(raw.get("jurisdiction") or st.get("jurisdiction") or "").strip()
    if juris:
        who = ("yours" if "author" in juris else
               "the engine's" if juris == "eigen" else juris)
        extra = f' <span class="dim">({escape(juris)})</span>' if who != juris else ""
        bits.append(f'<div class="whyrow"><span class="whylabel">whose call</span> '
                    f'{escape(who)}{extra}</div>')
    deps = [str(x) for x in (st.get("depends_on") or raw.get("depends_on") or []) if x]
    if deps:
        bits.append(f'<div class="whyrow"><span class="whylabel">waits on</span> '
                    f'{_linkify_refs(", ".join(deps))}</div>')
    return '<div class="whycard">' + "".join(bits) + "</div>"


def _frag_grid(cols: int = 8) -> str:
    from laplace.engine import wake
    try:
        camp = wake.campaign(_repo_root(), run_gates=False)
    except Exception as e:  # noqa: BLE001
        return f'<p class="red">campaign organ error: {escape(str(e))}</p>'
    verdicts: dict[str, list[dict]] = {}
    raw_stages: dict[str, dict] = {}
    for _off, row in _rows.scan("campaign"):
        if row.get("record") == "gate-verdict":
            verdicts.setdefault(str(row.get("stage")), []).append(row)
        elif row.get("record") == "stage":
            raw_stages[str(row.get("id"))] = row     # latest wins, append-only
    head = "".join(f"<th>{-i}</th>" for i in range(cols - 1, 0, -1)) + "<th>latest</th>"
    # his register: the stage's TITLE carries the row; the id is the dim suffix one
    # reads only when descending. Order by what matters now: the computed next act
    # first, then live stages, done last — never registry order.
    next_act = camp.get("next_act")
    stages = list(camp.get("stages", []))
    stages.sort(key=lambda s: (0 if s.get("id") == next_act else
                               1 if s.get("status") != "DONE" else 2))
    body: list[str] = []
    for st in stages:
        sid = str(st.get("id"))
        vs = verdicts.get(sid, [])[-cols:]
        cells = []
        for v in [None] * (cols - len(vs)) + vs:
            if v is None:
                cells.append('<td class="cell unjudged" title="never ran">·</td>')
            else:
                ok = v.get("exit") == 0
                cells.append(f'<td class="cell {"ok" if ok else "bad"}" '
                             f'title="exit {v.get("exit")} · {_ts_age(v.get("ts"))} ago">'
                             f'{"✓" if ok else "✗"}</td>')
        status = str(st.get("status", "?"))
        cls = {"DONE": "ok", "OPEN": "pend"}.get(status, "warn")
        words = _CAMP_WORDS.get(status, status.lower().replace("-", " "))
        mark = ' <span class="warn">← next act</span>' if sid == next_act else ""
        body.append(f'<tr><td class="stagename"><details>'
                    f'<summary>{escape(_first_clause(str(st.get("title", "")) or sid, 96))}'
                    f'{mark}<div class="dim small">{_chip(words, cls)} '
                    f'{escape(sid)}</div></summary>'
                    f'{_why_card(st, raw_stages.get(sid))}</details></td>'
                    f'{"".join(cells)}</tr>')
    return (f'<div class="tablewrap"><table class="grid">'
            f'<tr><th>stage (status computed at query time)</th>{head}</tr>'
            f'{"".join(body)}</table></div>'
            + _byline("campaign", f'{len(camp.get("stages", []))} stages · '
                                  f'next_act {escape(str(camp.get("next_act")))}'))


# ------------------------------------------------------------------ rows / facets

def _cell(flat: dict[str, Any], col: str) -> str:
    v = flat.get(col)
    if v is None:
        return "<td></td>"
    if isinstance(v, dict) and v.get("truncated"):
        return (f'<td class="dim">[{v["bytes"]:,} B truncated] '
                f'{escape(str(v.get("head", ""))[:80])}…</td>')
    return f"<td>{escape(str(v)[:160])}</td>"


def _frag_rows(source: str, expr: str, limit: int) -> str:
    res = _rows.query(source, expr, limit)
    if res.get("error"):
        return f'<p class="red">{escape(res["error"])}</p>'
    cols = res["columns"]
    head = "".join(f"<th>{escape(c)}</th>" for c in cols)
    trs = []
    for m in res["rows"]:
        flat = _rows.flatten(m["row"])
        trs.append(
            f'<tr class="rowline" data-row="{escape(source)}@{m["offset"]}" tabindex="0">'
            f'<td><a href="#record/{escape(source)}/{m["offset"]}">@{m["offset"]}</a></td>'
            + "".join(_cell(flat, c) for c in cols) + "</tr>")
    return (f'<div class="parsed dim">matching: {escape(res["parsed"])} — '
            f'{res["matched"]} of {res["total"]} rows, {res["shown"]} shown</div>'
            f'<div class="tablewrap"><table><tr><th>@</th>{head}</tr>{"".join(trs)}</table></div>'
            + _byline(source, f'{res["total"]} rows scanned at render'))


def _frag_facets(source: str, expr: str) -> str:
    res = _rows.facets(source, expr)
    bits = []
    for field, vals in res.get("facets", {}).items():
        chips = "".join(
            f'<button class="facet" data-term="{escape(field)}:{escape(v)}">'
            f'{escape(str(v)[:40])} <b>{n}</b></button>' for v, n in vals)
        bits.append(f'<div class="facetrow"><span class="dim">{escape(field)}</span> {chips}</div>')
    return "".join(bits) or '<span class="dim">no facets</span>'


# ------------------------------------------------------------------ trace

_STATE_GLYPH = {"done": ("●", "ok"), "in-flight": ("◐", "warn"), "died": ("○", "bad")}


def _frag_acts(limit: int) -> str:
    items = []
    for a in _trace.acts(limit):
        glyph, cls = _STATE_GLYPH.get(a["state"], ("?", ""))
        status = f' · {escape(str(a["status"]))}' if a.get("status") else ""
        dur = f'{a["duration_s"]:.1f}s' if a.get("duration_s") is not None else "—"
        orphan_label = f'{a["n_orphans"]} orphan'
        orph = f' {_chip(orphan_label, "bad")}' if a["n_orphans"] else ""
        items.append(
            f'<li><span class="{cls}">{glyph}</span> '
            f'<a href="#trace/{escape(a["act_id"])}">{escape(str(a["act"]))}</a> '
            f'<span class="dim">{escape(str(a["act_id"])[:44])}{status} · '
            f'{a["n_steps"]} steps · {a["n_banks"]} banked · {dur}</span>{orph}</li>')
    return (f'<ol class="acts">{"".join(items)}</ol>'
            + _byline("journal", "acts grouped at render; in-flight vs died via /proc"))


def _frag_trace(act_id: str) -> str:
    a = _trace.act_tree(act_id)
    if a is None:
        return f'<p class="red">no act {escape(act_id)} in the journal</p>'
    glyph, cls = _STATE_GLYPH.get(a["state"], ("?", ""))
    total = a.get("duration_s") or sum(
        s.get("duration_s") or 0 for s in a.get("steps", [])) or 1.0
    rows_html = []
    for s in a.get("steps", []):
        d = s.get("duration_s")
        width = max(1.5, min(100.0, (d / total) * 100)) if d else 1.5
        state = ("open" if s.get("open") else "")
        label = f'{d:.2f}s' if d is not None else ("in flight" if s.get("open") else "?")
        rows_html.append(
            f'<div class="step"><span class="stepname">{s.get("index")}. '
            f'{escape(str(s.get("name")))}</span>'
            f'<span class="bar {state}" style="width:{width:.1f}%"></span>'
            f'<span class="dim">{label}</span></div>')
    bank_items = []
    for b in a.get("banks", []):
        rid, store = escape(str(b.get("row_id"))), escape(str(b.get("store")))
        src = _bank_source(b)
        if src:
            bank_items.append(
                f'<li>banked <a href="#record/{escape(src)}/id:{rid}">{rid}</a> '
                f'<span class="dim">→ {store}</span></li>')
        else:
            # an unregistered store is an honest gap, never a link into another
            # store's rows (the review's finding, 2026-08-24).
            bank_items.append(
                f'<li>banked <code>{rid}</code> {_chip("UNMAPPED", "bad")} '
                f'<span class="dim">→ {store} — not in the front-door registry, '
                f'so there is no row to descend to</span></li>')
    banks = "".join(bank_items)
    orphans = "".join(
        f'<li class="bad">ORPHAN {escape(str(o.get("kind")))} — '
        f'{escape(str(o.get("name", "")))} @{o.get("offset")}</li>'
        for o in a.get("orphans", []))
    adj = "".join(
        f'<li class="warn">adjudication: {escape(str(x.get("status")))} — '
        f'{escape(str(x.get("note", ""))[:160])}</li>' for x in a.get("adjudications", []))
    return (f'<h3><span class="{cls}">{glyph}</span> {escape(str(a["act"]))} '
            f'<span class="dim">{escape(a["act_id"])} · pid {a.get("pid")} · '
            f'{a["state"]}{" · " + escape(str(a.get("status"))) if a.get("status") else ""}</span></h3>'
            f'<div class="steps">{"".join(rows_html)}</div>'
            f'<ul>{banks}{orphans}{adj}</ul>'
            + _byline("journal", f'act {escape(a["act_id"])}'))


def _bank_source(bank: dict[str, Any]) -> str | None:
    """The registry name for a bank row's store, or None when nothing maps it.

    Total, never fabricated: the old fallback returned ``work_orders`` for every
    unregistered store, so the waterfall rendered a row address that contradicted the
    store name printed beside it and dead-ended. Any store can bank before it is
    registered, so this guard stays even after the registry catches up."""
    store = str(bank.get("store", ""))
    for name, spec in _sources.SOURCES.items():
        if spec["path"] == store:
            return name
    return None


# ------------------------------------------------------------------ record

# ---------------------------------------------------------------- the edge seam
#
# ONE RESOLVER, never scattered joins. Every relation in an obligation row is a STRING
# whose meaning is inferred at read time; W11 carries his ruling that declared edges are
# the reliability cure and codex owns that migration. This function is the seam it would
# re-point: change what an edge IS here, and every surface follows.
#
# SIX STATES, because a design audit measured 3,829 relation values and found the unknown
# collapsing at every boundary. My own first pass classed ~450 LIVE files as dead by
# testing the whole string as a path — "scripts/audit_local_parity.py -> parity:
# VERDICT=PASS ..." is a real file with its result stapled on. Extract the token, stat it,
# THEN decide. Rendering all six alike would be the same collapse in a nicer font.
_REL_VERBS = {
    "target":      ("aims at",     "aimed at by"),
    "supersedes":  ("replaces",    "replaced by"),
    "consumes":    ("absorbs",     "absorbed by"),
    "refs":        ("cites",       "cited by"),
    "evidence":    ("rests on",    "evidence for"),
    "depends_on":  ("waits on",    "blocks"),
    "blocked_on":  ("blocked by",  "blocking"),
    "retracts":    ("withdraws",   "withdrawn by"),
    "packet":      ("belongs to",  "holds"),
    "consumed_by": ("consumed by", "consumes"),
}
#: attribution is NOT an edge — it is a person and often a verbatim quote. Conjugating
#: `requested_by = "gerard (2026-07-15: 'this will probably delay the check')"` into a
#: link would manufacture a relation nobody asserted.
_ATTRIB_FIELDS = ("requested_by", "owed_by", "by", "source", "rater", "actor", "deferred_by")

_PATH_TOKEN = re.compile(r"[\w][\w./-]*\.(?:py|md|json|jsonl|html|txt|css|mjs|yaml|toml)")
_FOREIGN_REF = re.compile(r"\b(?:commit\s+[0-9a-f]{7,40}|PR:[\w./-]+#\d+)\b")
_IDLIKE = re.compile(r"^[A-Z][A-Z0-9]*-[\w.-]+$")


def _edge_state(value: str, known_ids: set[str], root: Path) -> dict[str, Any]:
    """Classify ONE relation value. Parse structure; never infer a target."""
    text = value.strip()
    if text in known_ids:
        return {"state": "row", "handle": text, "gloss": ""}

    m = _PATH_TOKEN.search(text)
    if m:
        token = m.group(0)
        gloss = (text[:m.start()] + text[m.end():]).strip(" -–—:>")
        if (root / token).exists():
            return {"state": "file", "handle": token, "gloss": gloss}
        return {"state": "dead", "handle": token, "gloss": gloss}

    m = _FOREIGN_REF.search(text)
    if m:
        gloss = (text[:m.start()] + text[m.end():]).strip(" ()-–—:")
        return {"state": "outside", "handle": m.group(0), "gloss": gloss}

    if _IDLIKE.match(text):
        return {"state": "foreign", "handle": text, "gloss": ""}

    return {"state": "prose", "handle": "", "gloss": text}


_INDEX_CACHE: dict[str, Any] = {}


def _edge_index(source: str) -> dict[str, Any]:
    """Every row's id set and its INBOUND edges, one pass, cached on store identity.

    Without the inbound half a node view teaches that the graph is a one-way street.
    Measured: 17.8ms to load + 5.0ms to index the whole obligation store, once; 0.008ms
    to resolve one node. The flat scan is not the bottleneck anyone assumes it is.
    """
    spec = _sources.get(source)
    if spec is None:
        return {"ids": set(), "inbound": {}}
    try:
        st = Path(spec["abspath"]).stat()
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        key = (0, -1)
    cached = _INDEX_CACHE.get(source)
    if cached and cached["key"] == key:
        return cached

    ids: set[str] = set()
    rows: list[dict] = []
    for _off, row in _rows.scan(source):
        rows.append(row)
        rid = row.get("id")
        if isinstance(rid, str):
            ids.add(rid)
    inbound: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        rid = str(row.get("id", ""))
        for field in _REL_VERBS:
            v = row.get(field)
            for tok in ([v] if isinstance(v, str) else (v if isinstance(v, list) else [])):
                if isinstance(tok, str) and tok.strip() in ids:
                    inbound.setdefault(tok.strip(), []).append((field, rid))
    out = {"key": key, "ids": ids, "inbound": inbound}
    _INDEX_CACHE[source] = out
    return out


def _frag_record(source: str, off: int | None, rid: str | None) -> str:
    """A row as a NODE, not as its storage layout.

    His complaint, 2026-08-25, mid-walk: the campaign page "has some of that click
    through but it terminates in a JSON that's again uninterpretable" — and, separately,
    "the orders themselves and their relations to different engine features could be
    graphified... access to every axis of context."

    Measured before the cure: this view served 2,414 bytes, two distinct tags, one
    <pre>, and ZERO anchors — the terminus of every click-through path in the system,
    at once unreadable and untraversable. It showed the one aspect of a row he never
    came for: its storage shape. Field names he did not ask about, escaped twice, in a
    monospace wall, directly above the only three things he wanted.

    Five bands — what it is · what it says · what it points at · what points at it ·
    who asked — then an honesty line counting how much of it resolved. The JSON does not
    disappear; it demotes to a fold, where a storage view belongs.
    """
    spec = _sources.get(source)
    if spec is None:
        return f'<p class="red">unknown source {escape(source)}</p>'
    hit = None
    if off is not None:
        row = _rows.row_at(source, off)
        hit = (off, row) if row else None
    elif rid:
        hit = _rows.find_by_id(source, rid)
    if not hit or hit[1] is None:
        return (f'<p class="red">no row at {escape(source)}'
                f'{"@" + str(off) if off is not None else " id " + escape(str(rid))}</p>')
    offset, row = hit
    root = _repo_root()
    idx = _edge_index(source)
    known, inbound = idx["ids"], idx["inbound"]
    row_id = str(row.get("id", ""))

    face = _row_face(row)
    kind = str(row.get("record") or row.get("kind") or "row").replace("_", " ")
    state = str(row.get("status") or "")
    chips = _chip(kind, "dim")
    if state:
        chips += _chip(state, "ok" if state in ("closed", "resolved", "done") else "pend")
    head = (f'<div class="nodehead"><b class="nodeface" title="{escape(row_id)}">'
            f'{escape(face)}</b> {chips}</div>')

    body = ""
    for key in ("what", "text", "law", "title"):
        v = row.get(key)
        if isinstance(v, str) and v.strip() and v.strip()[:80] != face[:80]:
            full = v.strip()
            body += (f'<div class="nodesay">{escape(full[:260])}'
                     + (f'<details class="more"><summary>more</summary>'
                        f'<div class="morebody">{escape(full)}</div></details>'
                        if len(full) > 260 else "") + '</div>')
            break
    why = row.get("why")
    if isinstance(why, str) and why.strip():
        body += (f'<div class="nodesay"><span class="lbl">why</span> '
                 f'{escape(why.strip()[:260])}</div>')

    counts = {"row": 0, "file": 0, "dead": 0, "foreign": 0, "outside": 0, "prose": 0}

    def edge_html(verb: str, value: str, incoming: bool) -> str:
        e = _edge_state(value, known, root)
        st = e["state"]
        gloss = (f' <span class="e-gloss">{escape(e["gloss"][:90])}</span>'
                 if e["gloss"] and st != "prose" else "")
        cls = {"row": "e-row", "file": "e-file", "dead": "e-dead",
               "foreign": "e-foreign", "outside": "e-outside", "prose": "e-prose"}[st]
        tag = {"file": "file", "dead": "not found", "foreign": "not in this store",
               "outside": "outside"}.get(st, "")
        tag_html = f'<span class="e-tag">{tag}</span>' if tag else ""
        if st == "row":
            target = _rows.find_by_id(source, e["handle"])
            label = _row_face(target[1]) if target and target[1] else e["handle"]
            inner = (f'<a href="#record/{quote(source)}/id:{quote(e["handle"])}" '
                     f'title="{escape(e["handle"])}">{escape(label)}</a>')
        elif st == "prose":
            inner = f'<span class="t">{escape(e["gloss"][:240])}</span>'
        else:
            inner = f'<span class="t">{escape(e["handle"])}</span>'
        return (f'<div class="e {cls}{" e-in" if incoming else ""}">'
                f'<span class="e-verb">{escape(verb)}</span>'
                f'<span class="e-body">{inner}{gloss}</span>{tag_html}</div>')

    outs = []
    for field, verbs in _REL_VERBS.items():
        v = row.get(field)
        for tok in ([v] if isinstance(v, str) else (v if isinstance(v, list) else [])):
            if not isinstance(tok, str) or not tok.strip():
                continue
            counts[_edge_state(tok, known, root)["state"]] += 1
            outs.append(edge_html(verbs[0], tok, False))
    ins = [edge_html(_REL_VERBS[f][1], sid, True)
           for f, sid in inbound.get(row_id, [])]

    edges = ""
    if outs:
        edges += (f'<div class="band"><div class="bandhead">points at'
                  f'<span class="n">{len(outs)}</span></div>{"".join(outs)}</div>')
    if ins:
        edges += (f'<div class="band"><div class="bandhead">pointed at by'
                  f'<span class="n">{len(ins)}</span></div>{"".join(ins)}</div>')
    if not outs and not ins:
        edges = ('<div class="band"><div class="bandhead">relations</div>'
                 '<div class="e e-prose"><span class="e-body">this row names nothing, '
                 'and nothing names it</span></div></div>')

    attrib = ""
    for field in _ATTRIB_FIELDS:
        v = row.get(field)
        if isinstance(v, str) and v.strip():
            attrib += (f'<div class="attrib"><span class="lbl">'
                       f'{escape(field.replace("_", " "))}</span> '
                       f'{escape(v.strip()[:240])}</div>')
    if attrib:
        attrib = f'<div class="band">{attrib}</div>'

    total = sum(counts.values())
    reachable = counts["row"] + counts["file"]
    unchecked = counts["foreign"] + counts["outside"]
    honest = (f'{total} relation(s) · {reachable} reachable · {counts["dead"]} not found '
              f'· {unchecked} not checkable from here · {counts["prose"]} read as prose'
              if total else "no relations on this row")

    shown = _rows.truncate_row(row)
    raw = escape(json.dumps(shown, indent=1, ensure_ascii=False))
    expand = "".join(
        f'<a class="expand" href="/front/field?source={escape(source)}&off={offset}'
        f'&path={escape(k)}" target="_blank">expand {escape(k)} '
        f'({v["bytes"]:,} B)</a> '
        for k, v in shown.items() if isinstance(v, dict) and v.get("truncated"))
    return (f'<div class="node">{head}{body}{edges}{attrib}'
            f'<div class="honest">{escape(honest)} · paths checked at render</div>'
            f'<details class="mech"><summary>the stored row</summary>'
            f'<div class="mechbody"><pre class="record">{raw}</pre>{expand}</div>'
            f'</details></div>' + _byline(source, f'row @{offset}'))


def _field_value(source: str, off: int, path: str) -> tuple[int, str, bytes]:
    row = _rows.row_at(source, off)
    if row is None:
        return 404, _JSON, b'{"error": "no row"}'
    cur: Any = row
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return 404, _JSON, b'{"error": "no such field"}'
        cur = cur[part]
    text = cur if isinstance(cur, str) else json.dumps(cur, indent=1, ensure_ascii=False)
    return 200, "text/plain; charset=utf-8", text.encode("utf-8")


# ------------------------------------------------------------------ chats

def _seat_titles() -> dict[str, str]:
    """session uuid → seat title, from contract/seats.jsonl session_ref text ONLY
    (founding refusal R3: no hand-authored uuid map, ever). Ambiguity maps nothing."""
    titles: dict[str, str] = {}
    try:
        from laplace.engine.seats import current_seats
        for row in current_seats(_repo_root()):
            ref = str(row.get("session_ref", ""))
            uuids = _UUID_RE.findall(ref)
            title = str(row.get("title") or row.get("seat") or "")
            for u in uuids:
                titles[u] = title
    except Exception:  # noqa: BLE001 — a broken store yields UNMAPPED, never a crash
        pass
    return titles


def _transcript_dir_state() -> tuple[str, str]:
    """``(state, resolved path)`` — ``absent`` (missing or unreadable), ``empty``
    (readable, holding no transcripts) or ``ok``. The two failure shapes rendered
    identically before — an unreadable directory and a quiet one both produced an
    empty list under a byline that asserted the source as though it had been read
    (the review's finding, 2026-08-24). The path is the RESOLVED one, never the
    unexpanded constant."""
    d = _sources.transcript_dir()
    try:
        if not d.is_dir():
            return "absent", str(d)
        for _p in d.glob("*.jsonl"):
            return "ok", str(d)
    except OSError:
        return "absent", str(d)
    return "empty", str(d)


def _chats_data() -> list[dict[str, Any]]:
    from laplace.web import seats_surface as _seats
    titles = _seat_titles()
    by_sid = {s["session_id"]: s for s in _seats._sessions_authority() if s.get("session_id")}
    now = time.time()
    out: list[dict[str, Any]] = []
    # ONE guarded stat per file: a transcript rotated or removed between the listing
    # and the read is a moment, not a defect — it drops out of the list, it does not
    # take the pane down (the review's finding, 2026-08-24).
    entries: list[tuple[Any, Path]] = []
    try:
        for p in _sources.transcript_dir().glob("*.jsonl"):
            try:
                entries.append((p.stat(), p))
            except OSError:
                continue
    except OSError:
        return []
    entries.sort(key=lambda e: e[0].st_mtime, reverse=True)
    for st, p in entries[:20]:
        sid = p.stem
        sess = by_sid.get(sid, {})
        out.append({
            "sid": sid,
            "seat": titles.get(sid) or ("UNMAPPED"),
            "fabric": sess.get("name"),
            "alive": bool(sess.get("socket_alive")),
            "hung": bool(sess.get("hung")),
            "age_s": round(now - st.st_mtime, 1),
            "bytes": st.st_size,
        })
    return out


def _frag_chats() -> str:
    state, dpath = _transcript_dir_state()
    if state == "absent":
        return (f'<div class="byline red">[source] HOST-OWNED {escape(dpath)}/*.jsonl '
                f'— ABSENT or unreadable; no chat can be read until it resolves, and '
                f'this pane is empty for that reason, not for quiet</div>')
    items = []
    for c in _chats_data():
        seat = (_chip(c["seat"], "warn") if c["seat"] == "UNMAPPED"
                else _chip(c["seat"], "ok"))
        live = _chip("live", "ok") if c["alive"] else _chip("off", "dim")
        hung = _chip("quiet — may be hung", "bad") if c["hung"] else ""
        items.append(
            f'<li>{seat} {live} {hung} '
            f'<a href="#chat/{escape(c["sid"])}">{escape(str(c["sid"])[:8])}…</a> '
            f'<span class="dim">{escape(str(c.get("fabric") or ""))} · '
            f'{_age_words(c["age_s"])} ago · {c["bytes"]:,} B</span></li>')
    body = ("".join(items) if items else
            '<li class="dim">the directory is present and readable and holds no '
            'sessions — empty, not unread</li>')
    return (f'<ul class="chats">{body}</ul>'
            f'<div class="byline">[source] HOST-OWNED {escape(dpath)}'
            f'/*.jsonl · seat names ONLY via contract/seats.jsonl + ~/.claude/sessions '
            f'(the id authority) — unmapped renders UNMAPPED, never guessed</div>')


def render_chat_line(raw: bytes | str) -> str | None:
    """One transcript line → one chat bubble, or None for non-message lines.
    Text parts render; tool uses render as a name list; soul refs stay refs."""
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return None
    m = obj.get("message") if isinstance(obj, dict) else None
    if not isinstance(m, dict):
        return None
    role = m.get("role")
    if role not in ("user", "assistant"):
        return None
    texts: list[str] = []
    tools: list[str] = []
    c = m.get("content")
    if isinstance(c, str) and c.strip():
        texts.append(c)
    elif isinstance(c, list):
        for part in c:
            if not isinstance(part, dict):
                continue
            t = part.get("type")
            if t == "text" and str(part.get("text", "")).strip():
                texts.append(str(part["text"]))
            elif t == "tool_use":
                tools.append(str(part.get("name", "?")))
            elif t == "tool_result":
                return None
    if not texts and not tools:
        return None
    body = escape("\n\n".join(texts)[:6000])
    tline = (f'<div class="tools">⚙ {escape(", ".join(tools))}</div>' if tools else "")
    return (f'<div class="msg {escape(str(role))}">'
            f'<div class="role">{escape(str(role))}</div>'
            f'<pre>{body}</pre>{tline}</div>')


def _frag_chat(sid: str, limit: int = 80) -> str:
    if not _UUID_RE.fullmatch(sid):
        return '<p class="red">bad session id</p>'
    p = _sources.transcript_dir() / f"{sid}.jsonl"
    try:
        size = p.stat().st_size
        with open(p, "rb") as fh:
            if size > _CHAT_TAIL_BYTES:
                fh.seek(size - _CHAT_TAIL_BYTES)
                fh.readline()  # drop the partial line
            data = fh.read()
    except OSError:
        return f'<p class="red">no transcript for {escape(sid)}</p>'
    msgs = [h for h in (render_chat_line(ln) for ln in data.splitlines()) if h]
    seat = _seat_titles().get(sid, "UNMAPPED")
    return (f'<div class="chathead">{_chip(seat, "ok" if seat != "UNMAPPED" else "warn")} '
            f'<code>{escape(sid)}</code> · tail cursor {size}</div>'
            f'<div class="chatpane" data-sid="{escape(sid)}" data-cursor="{size}">'
            + "".join(msgs[-limit:]) + "</div>"
            f'<div class="byline">[source] HOST-OWNED transcript {escape(sid)}.jsonl · '
            f'last {min(limit, len(msgs))} messages of the {_CHAT_TAIL_BYTES // 1024} KB tail</div>')


# ------------------------------------------------------------------ stream renderers

def render_stream_row(name: str, off: int, row: dict[str, Any]) -> str:
    spec = _sources.get(name) or {"columns": []}
    flat = _rows.flatten(_rows.truncate_row(row))
    cells = " · ".join(
        f'{escape(str(flat.get(c, ""))[:60])}' for c in spec["columns"][:5] if flat.get(c))
    return (f'<div class="tailrow fresh" data-row="{escape(name)}@{off}">'
            f'{_chip(name)} <a href="#record/{escape(name)}/{off}">@{off}</a> '
            f'{cells}</div>')


# ------------------------------------------------------------------ liveness grades

_LIV_CHIP = {"CONFIRMED": "ok", "REFUTED": "bad", "INSUFFICIENT": "warn"}


def _frag_liveness() -> str:
    """The archaeology join (RUL-20260824-judge5-liveness-packet-form; store named by
    the Ego, NOTE-20260824-liveness-store-born): latest claim packet per organ joined
    to the latest judge verdict that grades it. The surface renders GRADES with the
    verdict row's id as cell provenance — never its own reads, never an ungraded
    packet as green. Packet-without-verdict is UNGRADED, loud."""
    packets: dict[str, dict[str, Any]] = {}
    verdicts: dict[str, dict[str, Any]] = {}
    for _off, row in _rows.scan("liveness"):
        rec = row.get("record")
        if rec == "liveness-packet" and row.get("id"):
            packets[str(row.get("organ") or row["id"])] = row
        elif rec == "liveness-verdict" and row.get("packet"):
            verdicts[str(row["packet"])] = row
    if not packets and not verdicts:
        return ('<p class="dim">no liveness packets banked yet — batch 1 fires today '
                '(the archaeology wave)</p>'
                + _byline("liveness"))
    trs = []
    for organ, pkt in sorted(packets.items()):
        v = verdicts.get(str(pkt.get("id")))
        if v is None:
            chip = _chip("UNGRADED", "pend")
            claim = str(pkt.get("claim", "?"))
            prov = '<span class="dim">awaiting the judge</span>'
        else:
            chip = _chip(str(v.get("verdict", "?")),
                         _LIV_CHIP.get(str(v.get("verdict")), "warn"))
            claim = str(v.get("claim_as_graded") or pkt.get("claim", "?"))
            vid = str(v.get("id", "?"))
            prov = (f'<a href="#record/liveness/id:{escape(vid)}">{escape(vid)}</a> '
                    f'<span class="dim">rater {escape(str(v.get("rater", "?")))}</span>')
        cmd = str(pkt.get("evidence_cmd", ""))
        trs.append(
            f'<tr><td>{escape(organ)}</td><td>{chip} {escape(claim[:60])}</td>'
            f'<td>{prov}</td>'
            # slice BEFORE escape: the budget must mean 90 COMMAND characters, and a
            # cut inside an entity would render a command that is not fireable
            f'<td><code>{escape(cmd[:90])}</code></td></tr>')
    return (f'<div class="tablewrap"><table>'
            f'<tr><th>organ</th><th>graded claim</th><th>verdict provenance</th>'
            f'<th>evidence_cmd (fireable verbatim)</th></tr>{"".join(trs)}</table></div>'
            + _byline("liveness",
                      f'{len(packets)} packets · {len(verdicts)} verdicts · '
                      f'ungraded renders UNGRADED, never green'))


# ------------------------------------------------------------------ the ask-door (M2)

#: the decisions the door accepts, mapped to the words the banked row carries.
_DECISIONS = {"approve": "approved", "refuse": "refused"}


def _decide(body: bytes) -> tuple[int, str, bytes]:
    """Bank the author's decision on one pending ASK row. Validates against the LIVE
    pending set (never a blind append), builds the resolution shape the ask lane
    retires on, and appends it through the shared banking path. The row is HIS act:
    actor stamped, via front-door, correctable only by a later row — nothing here
    ever mutates."""
    from laplace.core.records import journal as _journal
    from laplace.web import seats_surface as _seats
    try:
        req = json.loads(body or b"{}")
        assert isinstance(req, dict)
    except (ValueError, AssertionError):
        return 400, _JSON, b'{"error": "body must be a JSON object"}'
    ask_id = str(req.get("ask", "")).strip()
    decision = _DECISIONS.get(str(req.get("decision", "")).strip())
    text = str(req.get("text", req.get("note", ""))).strip()[:2000]
    if decision is None:
        return 400, _JSON, b'{"error": "decision must be approve or refuse"}'
    root = _repo_root()
    try:
        pending = {str(a.get("id")) for a in _seats._pending_asks(root)}
    except Exception as e:  # noqa: BLE001
        return 500, _JSON, json.dumps(
            {"error": f"the ask lane could not be read: {type(e).__name__}: {e}"}
        ).encode("utf-8")
    if ask_id not in pending:
        return 404, _JSON, json.dumps(
            {"error": f"{ask_id or '(empty)'} is not an open ask — the pending set is "
                      f"recomputed from rows at every request; refresh and look again"}
        ).encode("utf-8")
    now = datetime.now(timezone.utc)
    row = {
        "record": "resolution",
        "id": f"RES-{now.strftime('%Y%m%dT%H%M%S')}-front-door-decide",
        "target": ask_id,
        "status": "resolved",
        "decision": decision,
        "text": text,
        "actor": "gerard",
        "via": "front-door",
        # forward-binding to the substrate wave's typed-edges law (the Ego's note,
        # 2026-08-24): harmless JSON today, first-class the day bank_row types it.
        "edges": [{"rel": "resolves", "target": ask_id}],
        "ts": now.isoformat(),
    }
    try:
        _journal.bank_row("corpus_friction/work_orders.jsonl", row, root=root)
    except Exception as e:  # noqa: BLE001
        return 500, _JSON, json.dumps(
            {"error": f"the bank failed and NOTHING was appended: "
                      f"{type(e).__name__}: {e}"}).encode("utf-8")
    return 200, _JSON, json.dumps({"banked": row["id"], "target": ask_id,
                                   "decision": decision}).encode("utf-8")


# ------------------------------------------------------------------ the walk-verdict door

#: stages whose build exists and can therefore be walked; grows as stages land.
#: THE STAGES THAT MAY ACTUALLY BE WALKED — built, and ready for his verdict.
#: This is NOT the same set as the gate's, and conflating the two cost a forged row:
#: widening the accept path to every milestone the gate greps removed the "only built
#: stages walk" refusal, and a diagnostic call then banked
#: RES-20260825T114838-front-door-m4-walked with actor="gerard" for a milestone that is
#: not built (retracted: RETRACT-20260825-front-door-m4-walked-not-his). The gate names
#: the whole PROGRAMME; this names what his hand can rule on today. Display shows both.
_WALKABLE = ("m1", "m2")

#: fallback for the gate's programme set when the campaign cannot be read.
_WALKABLE_FALLBACK = ("m1", "m2", "m3", "m4")


def _walkable() -> tuple[str, ...]:
    """The milestones the campaign gate actually greps for, read from the gate itself.

    CAMP-R3-front-door-program's gate command names ('m1','m2','m3','m4') and exits 0
    only when every one carries a front-door-<m>-walked row. A strip offering a different
    set than the gate tests is a promise the gate will not keep.
    """
    try:
        from laplace.engine import wake as _wake
        for stage in _wake.campaign(_repo_root(), run_gates=False).get("stages", []):
            if stage.get("id") == "CAMP-R3-front-door-program":
                cmd = str((stage.get("gate") or {}).get("cmd", ""))
                found = tuple(dict.fromkeys(re.findall(r"'(m\d+)'", cmd)))
                if found:
                    return found
    except Exception:  # noqa: BLE001 - an unreadable campaign falls back, loudly below
        pass
    return _WALKABLE_FALLBACK


_MILESTONE_NOTE = "NOTE-20260823-front-door-program"

#: AUTHORED VOCABULARY, grounded — never quoted (M-interface-authored-vocabulary).
#: The first cut derived these glosses verbatim from the programme note and the design
#: audit measured the result: 0 of 4 passed his laws — the note's register leaked
#: wholesale ("the standing Ego", "the chaining machinery", a raw file path in the
#: default register, "tonight's" decaying by morning) while the authored faces passed.
#: A note is written by the system for the system. Language is authored here, in one
#: typed place, each entry grounded by the row that minted the milestone; facts
#: (counts, states, dates) stay derived from rows.
_MILESTONE_FACES: dict[str, dict[str, str]] = {
    "m1": {"name": "the read surface",
           "gloss": "chats, the seat board, and the account and campaign panels, "
                    "readable on one page",
           "ground": _MILESTONE_NOTE},
    "m2": {"name": "the talk path",
           "gloss": "you type here; the message is saved as a row, sent to the serving "
                    "session, and the reply streams back",
           "ground": _MILESTONE_NOTE},
    "m3": {"name": "the router",
           "gloss": "picks or starts the session that serves each request",
           "ground": _MILESTONE_NOTE},
    "m4": {"name": "the conjugate view",
           "gloss": "walk, desk, campaign board, and run views on this one surface",
           "ground": _MILESTONE_NOTE},
}


def _clip_words(text: str, cap: int) -> str:
    """Cut at a WORD BOUNDARY and say you cut. Never mid-word, never on a dangling word.

    A hard slice shipped three of the five headlines on his brief ending as
    "...observed in production dur", "...ACHIEVING NOTHING, ON THE STORE EVERY I" and
    "...it is advisory by a ruling whose" — mid-word or on a preposition, with no ellipsis
    and no title to recover the rest. A truncation the reader cannot SEE is worse than a
    short face: it reads as the whole sentence, and the sentence appears to end in
    nonsense. The rstrip that was here removed trailing punctuation and did nothing about
    the word it had just broken in half.

    Trailing function words are dropped too — a face ending "by a ruling whose" promises a
    clause that never arrives, which is the same defect as ending on a colon.
    """
    text = text.strip()
    if len(text) <= cap:
        return text.rstrip(" -\u2013,(")
    cut = text[:cap]
    if " " in cut:
        cut = cut[:cut.rindex(" ")]
    words = cut.rstrip(" -\u2013,:(").split()
    DANGLING = {"a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "by",
                "with", "from", "into", "whose", "which", "that", "is", "was", "are",
                "its", "it", "this", "these", "as", "but", "so", "if", "when", "while"}
    while words and words[-1].lower().strip(",;:-") in DANGLING:
        words.pop()
    return (" ".join(words) + "\u2026") if words else text[:cap]


def _row_face(row: dict[str, Any]) -> str:
    """The human register of one row: its own prose, first clause, never its id.

    His law at this surface, 2026-08-25: he arrives with zero context, so context must
    be summonable with his attention and invisible otherwise — and printing internal
    handles is the surface talking to itself in front of him. Most rows already carry
    their face in their own text; the id is the machine register and renders only in
    the summonable layer (title=, the mechanics fold).
    """
    for key in ("face", "title", "what", "text", "note", "why"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            text = value.strip()
            head = re.split(r"(?<=[.;:])\s", text, maxsplit=1)[0]
            head = _clip_words(head, 110)
            # A FACE MUST NOT END ON A COLON. Rows open label-then-body — "HIS JOIN,
            # verbatim: ...", "THE WALK SERVES THE BENCHES: ..." — and a label ending
            # in ':' is a promise the sentence never keeps. The design audit named the
            # same defect one level shallower ("DECLARED: carries zero information").
            # Take what FOLLOWS the label when there is enough of it to be a sentence.
            if head.endswith(":"):
                tail = text[len(head):].strip()
                head = (_clip_words(re.split(r"(?<=[.;])\s", tail, maxsplit=1)[0], 110)
                        if len(tail) >= 12 else head.rstrip(":"))
            if head.count("(") > head.count(")"):
                head = head.split("(", 1)[0].strip()
            return head or str(row.get("id", "?"))
    return str(row.get("id", "?"))


def _milestone_faces(note_text: str) -> dict[str, dict[str, str]]:
    """Parse the milestone definitions out of the row that minted them.

    The programme note defines every token in plain technical English — "M2 THE TALK
    PATH - his message into the surface -> banked as a row -> ..." — and the strip spent
    two days printing "M2" instead. Derived verbatim (first clause), never re-authored:
    the only edits are mechanical — an unmatched "(" becomes a dash, "his" reads "your"
    on his own dashboard, "->" renders as an arrow.
    """
    faces: dict[str, dict[str, str]] = {}
    for m in re.finditer(r"\bM([0-9]) ([A-Z][A-Z ]+?) - (.*?)(?=\.\s+M[0-9] [A-Z]|\Z)",
                         note_text, re.S):
        token = f"m{m.group(1)}"
        name = m.group(2).strip().lower()
        clause = m.group(3).split(";", 1)[0].strip().rstrip(".")
        if clause.count("(") > clause.count(")"):
            clause = clause.replace("(", "— ", 1)
        clause = clause.replace("->", "→")
        clause = re.sub(r"\bhis\b", "your", clause)
        if not name.startswith("the "):
            name = "the " + name
        faces[token] = {"name": name, "gloss": clause}
    return faces


def _walk_scan() -> dict[str, Any]:
    """One pass over work_orders for everything the strip needs: per-stage walk state,
    the rows that mention each milestone, and the programme note's text. This replaced
    one scan for state plus one scan PER STAGE for evidence — five passes of the same
    1,200-row file per apex render, on the fragment already measured slowest (278ms)."""
    programme = _walkable()
    mentions: dict[str, list[dict[str, str]]] = {s: [] for s in programme}
    note_text = ""
    all_rows: list[dict[str, Any]] = []
    pats = {s: re.compile(rf"\b{re.escape(s)}\b", re.I) for s in programme}
    for _off, row in _rows.scan("work_orders"):
        all_rows.append(row)
        rid = str(row.get("id", ""))
        if rid == _MILESTONE_NOTE:
            note_text = str(row.get("text", ""))          # last wins
        if row.get("record") in ("verdict", "resolution", "note", "finding"):
            blob = json.dumps(row)
            if "front" in blob.lower():
                for s in programme:
                    if pats[s].search(blob):
                        mentions[s].append({"id": rid, "face": _row_face(row),
                                            "ts": str(row.get("ts", ""))[:10]})
    # ONE FOLD. Closure — typed acceptance minus exact retraction — is codex's
    # walk_verdicts.fold_walk_verdicts, the same code the CAMP-R3 campaign gate now
    # runs (dfaf2483, their cure for the substring gate I reported). This scan carried
    # its own copy of the same rules for one afternoon, which is exactly how the strip
    # and the gate would have drifted apart the first time only one of them was fixed.
    from laplace.manuscript.walk_verdicts import fold_walk_verdicts
    state = fold_walk_verdicts(all_rows, programme)["state"]
    faces = dict(_milestone_faces(note_text))     # parser: fallback for unnamed tokens
    faces.update(_MILESTONE_FACES)                # authored vocabulary wins
    return {"state": state, "mentions": mentions, "faces": faces}


#: /2 DROPPED ``unreached``. Under /1 that field was the literal ``[]`` on every path,
#: banked into every talk-routed row in contract/talk.jsonl — so any consumer folding
#: those rows computed "0 unreached" and read it as full delivery, which is the exact
#: reassurance-from-absence this door keeps having to unlearn. Nothing available here
#: proves a seat was NOT reached, and FIND-20260825-unreached-can-name-a-reached-seat is
#: the standing proof that a list of that name can be wrong in the other direction too.
#: The version moves so a fold can tell the two shapes apart instead of reading a missing
#: key as an empty one.
_SEAT_ROUTING_SCHEMA = "laplace.front-door-seat-routing/2"

#: seats we ATTEMPT when HE acts. A literal, resolved at import: it excludes gerard-seat
#: (he is the actor) and nothing else. It said it also excluded "any seat that cannot be
#: reached" — a constant cannot know that, and reading it as an outcome is how the walk
#: door came to answer every POST with the same three names whether atlas_bridge imported
#: or not. Reachability is measured per send, in _tell_the_seats, after this is read.
_ACT_AUDIENCE = ("ego-seat", "codex-seat", "claude-seat")


def _tell_the_seats(kind: str, row: dict[str, Any], summary: str,
                    audience: tuple[str, ...] | list[str] | None = None) -> dict[str, Any]:
    """His act reaches the seats, or nothing does.

    His question, 2026-08-25, before approving: "if I approve the walk in the interface
    are you going to get it?" Measured answer at the time: NO. _walked banked the row and
    returned; grep for any seat notification across the whole front door gave 0, and the
    fabric does not watch corpus_friction/work_orders.jsonl. His approval would land
    durably and correctly — the gate would see it, the account would see it, a later wake
    would see it — and no seat would be TOLD. Approve at 11pm and it sits until someone
    happens to read the store.

    That is the mirror of every defect cured today: the surface could receive his act and
    had no path back. The seat fabric already exists and every seat already watches it.

    FAILURE IS NEVER HIS PROBLEM: the row is banked BEFORE this runs and nothing here is
    ever raised — every seat leaves with a typed outcome. This used to add "reported in
    the response", which was true while routing ran on the request thread and false from
    6621b316, which moved it onto _dispatch_notice's daemon thread: the HTTP response is
    already written before the first send returns. The outcomes reach him through the
    talk-routed row in contract/talk.jsonl, never through the response to his click.

    TOLD IS QUEUED, NOT DELIVERED, AND THERE IS NO THIRD LIST. ``told`` names seats whose
    send returned an Atlas append receipt; ``unknown`` names seats whose send raised,
    where the append state is not observable from here. No failure result available to
    this caller proves non-append — atlas_bridge itself now returns
    ``status_observation.state = "unknown-after-append"`` rather than raising when only
    the post-append status read fails — so a seat is NEVER recorded as unreached, and
    this shape carries no field claiming otherwise. Read ``outcomes`` for the per-seat
    detail; the two lists are its index, not a delivery verdict.
    """
    from datetime import timedelta

    seats = [
        seat for seat in (audience if audience is not None else _ACT_AUDIENCE)
        if seat != "interface-seat"
    ]
    told: list[str] = []
    unknown: list[str] = []
    outcomes: list[dict[str, Any]] = []
    try:
        from laplace.representation import atlas_bridge as _ab
    except Exception as exc:  # noqa: BLE001 - preserve the unknown, never invent absence
        error = {"type": type(exc).__name__, "message": str(exc)}
        return {
            "schema_version": _SEAT_ROUTING_SCHEMA,
            "told": [],
            "unknown": seats,
            "outcomes": [
                {"seat_id": seat, "state": "unknown", "error": error}
                for seat in seats
            ],
        }
    expires = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat()
    body = (f"THE AUTHOR ACTED AT THE FRONT DOOR — {kind}.\n\n{summary}\n\n"
            f"banked row: {row.get('id')}\n"
            f"store: corpus_friction/work_orders.jsonl\n"
            f"his words: {str(row.get('text') or '(none given)')[:800]}\n\n"
            f"This is a notification, not the truth. The ROW is the truth; read it.")
    for seat in seats:
        try:
            sent = _ab.send(
                sender_seat_id="interface-seat", recipient_seat_id=seat,
                message_type="author-act", body=body,
                dependency_roots={"row": str(row.get("id", "")),
                                  "store": "corpus_friction/work_orders.jsonl"},
                idempotency_key=f"author-act-{row.get('id')}-{seat}",
                expires_at=expires, provider="front-door", model="none",
            )
            told.append(seat)
            observation = sent.get("status_observation") or {"state": "known", "error": None}
            outcomes.append({
                "seat_id": seat,
                "state": (
                    "queued-status-unknown"
                    if observation.get("state") == "unknown-after-append"
                    else "queued"
                ),
                "message_id": sent.get("message_id"),
                "send_event_id": (sent.get("receipt") or {}).get("event_id"),
                "status_observation": observation,
            })
        except Exception as exc:  # noqa: BLE001 - location is unknown; absence is not inferred
            unknown.append(seat)
            outcomes.append({
                "seat_id": seat,
                "state": "unknown",
                "error": {"type": type(exc).__name__, "message": str(exc)},
            })
    return {
        "schema_version": _SEAT_ROUTING_SCHEMA,
        "told": told,
        "unknown": unknown,
        "outcomes": outcomes,
    }


def _dispatch_notice(kind: str, row: dict[str, Any], summary: str,
                     audience: tuple[str, ...] | list[str]) -> None:
    """Notify OFF the request path, and bank what actually happened.

    Historical trigger, not a current benchmark: the first cut measured ONE send at
    52,958 ms and moved routing off-thread.  ce02f05b replaced lifetime replay with verified
    suffix reads; later live sends measured 4.38s, so the old number must never be used as a
    current architectural premise.  The request path remains decoupled because transport
    availability is independent of banking his act, not because 53 seconds is assumed forever.

    So the row is banked before this runs, the response never waits, and the OUTCOME of
    routing banks as its own row — delivery stays a separate, visible fact rather than a
    claim made in advance.
    """
    # THE ROOT IS CAPTURED HERE, ON THE CALLER'S THREAD, NEVER INSIDE _go.
    # claude-seat's finding, three lenses deep and re-verified against committed history
    # (FIND-20260825-test-suite-forges-production-receipts): resolving _repo_root() inside
    # the daemon thread resolved it AFTER pytest tore its monkeypatch down, so the test
    # suite banked rows into the REAL contract/talk.jsonl. 23 of 24 talk-routed receipts
    # were minted by pytest, not by the front door — 42.5% of that store (6,682 of 15,710
    # bytes) is test residue, attributed by pid+argv on the ambient act rows.
    #
    # A background thread must capture every ambient it depends on at DISPATCH time. What
    # the caller could see is the only thing the thread may trust; anything it re-resolves
    # later belongs to whatever process state happens to exist then.
    _root = _repo_root()

    def _go() -> None:
        routing = _tell_the_seats(kind, row, summary, audience=audience)
        try:
            from laplace.core.records import journal as _j
            _j.bank_row("contract/talk.jsonl", {
                "record": "talk-routed", "id": f"ROUTED-{row.get('id')}",
                "target": row.get("id"),
                "schema_version": routing["schema_version"],
                "told": routing["told"],
                "unknown": routing["unknown"],
                "outcomes": routing["outcomes"],
                "ts": datetime.now(timezone.utc).isoformat(),
            }, root=_root)
        except Exception as exc:  # noqa: BLE001 - message stands; receipt failure is loud
            print(
                "[front-door] routing receipt could not be banked: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )

    threading.Thread(target=_go, name="front-door-notice", daemon=True).start()


def _walked(body: bytes) -> tuple[int, str, bytes]:
    """Bank HIS walk verdict on a front-door stage (the eyes-and-fingers gate made a
    door: acceptance is his hands on the walked surface, banked as his row).

    THE GATE DOES NOT GREP THE ID, and this said it did: "an ACCEPT row's id carries the
    ``-walked`` substring the campaign gate greps". True of the gate that preceded
    dfaf2483 — a python -c that ran ``'front-door-'+m+'-walked' not in txt`` over the raw
    store — and false from it. scripts/front_door_walk_gate.py now runs
    laplace.manuscript.walk_verdicts.fold_walk_verdicts, which reads record · verdict · stage ·
    actor · via, minus exact retractions, and never looks at id; the CAMP-R3 row moved in
    the same commit and its expect field states it verbatim: "ids and raw prose are never
    authority". This docstring is the last copy of the old gate left standing. Measured:
    an accept row minted with a NO-SUFFIX id closes m4 (``accepted_stages == ['m4']``),
    and a row whose id ends ``-front-door-m4-walked`` with ``actor='claude'`` closes
    nothing (``[]``). What makes an accept an accept is the five typed fields set below;
    the suffix is a readable convention in the id and nothing more, and a REDLINE is
    excluded by ``record``/``verdict``, not by lacking it."""
    from laplace.core.records import journal as _journal
    try:
        req = json.loads(body or b"{}")
        assert isinstance(req, dict)
    except (ValueError, AssertionError):
        return 400, _JSON, b'{"error": "body must be a JSON object"}'
    stage = str(req.get("stage", "")).strip().lower()
    verdict = str(req.get("verdict", "")).strip().lower()
    text = str(req.get("text", "")).strip()[:4000]
    if stage not in _WALKABLE:   # BUILT stages only — see the note on _WALKABLE
        return 400, _JSON, json.dumps(
            {"error": f"stage must be one of {list(_WALKABLE)} — only built stages walk"}
        ).encode("utf-8")
    if verdict not in ("accept", "redline"):
        return 400, _JSON, b'{"error": "verdict must be accept or redline"}'
    if verdict == "redline" and not text:
        return 400, _JSON, b'{"error": "a redline without words cures nothing - say what failed your eye"}'
    now = datetime.now(timezone.utc)
    if verdict == "accept":
        row = {"record": "walk-verdict",
               "id": f"RES-{now.strftime('%Y%m%dT%H%M%S')}-front-door-{stage}-walked",
               "stage": f"front-door-{stage}", "verdict": "accepted",
               "text": text, "actor": "gerard", "via": "front-door",
               "ts": now.isoformat()}
    else:
        row = {"record": "walk-redline",
               "id": f"WALKRED-{now.strftime('%Y%m%dT%H%M%S')}-front-door-{stage}",
               "stage": f"front-door-{stage}", "verdict": "redline",
               "text": text, "actor": "gerard", "via": "front-door",
               "ts": now.isoformat()}
    try:
        _journal.bank_row("corpus_friction/work_orders.jsonl", row, root=_repo_root())
    except Exception as e:  # noqa: BLE001
        return 500, _JSON, json.dumps(
            {"error": f"the bank failed and NOTHING was appended: "
                      f"{type(e).__name__}: {e}"}).encode("utf-8")
    _dispatch_notice(f"walk verdict on {stage.upper()}", row,
                     f"He recorded {row['verdict']} on the front-door stage {stage}.",
                     _ACT_AUDIENCE)
    # DELIVERY IS NOT KNOWN YET, AND THE RESPONSE MAY NOT LOOK LIKE IT IS. This carried
    # "notifying": list(_ACT_AUDIENCE) — a constant read on the request thread, so the
    # door answered with the same three seat names whether atlas_bridge imported or not,
    # and 6621b316 had replaced a real per-seat result with it. _dispatch_notice has only
    # just STARTED the thread; the sends have not run. What this can honestly say is that
    # dispatch began, which seats it will attempt, and where the outcome lands — and that
    # row is the only thing that ever knows.
    return 200, _JSON, json.dumps({
        "banked": row["id"], "stage": stage, "verdict": row["verdict"],
        "delivery": {
            "state": "dispatching",
            "known": False,
            "attempting": [s for s in _ACT_AUDIENCE if s != "interface-seat"],
            "outcome_row": f"ROUTED-{row['id']}",
            "outcome_store": "contract/talk.jsonl",
        },
    }).encode("utf-8")


def _frag_walkstrip() -> str:
    """The walk gate, rendered under his three laws (methods.jsonl, task_class
    interface): zero-context — the default register is readable with no session history;
    conjugate handles — faces lead, ids live in the mechanics fold and title=; plain
    technical English — every string passes "would an engineer write this on an
    internal tool".

    What it replaced: "M1 [awaiting your walk] [accept] [redline]" — an irreversible
    ruling offered on a bare token. His verdict on it, verbatim: "what am I meant to do
    with that?"
    """
    scan = _walk_scan()
    state, mentions, faces = scan["state"], scan["mentions"], scan["faces"]
    programme = _walkable()
    items = []
    for s in programme:
        st = state.get(s, {})
        face = faces.get(s, {})
        name = face.get("name", s.upper())
        gloss = face.get("gloss", "")
        built = s in _WALKABLE

        rows_known = mentions.get(s, [])
        shown = rows_known[-5:]
        trail = "".join(
            f'<div>{escape(m.get("record", "row"))} · '
            f'<a href="#record/work_orders/id:{quote(m["id"])}" '
            f'title="{escape(m["id"])}">{escape(m["face"])}</a> '
            f'<span class="dim">{escape(m["ts"])}</span></div>'
            for m in shown)
        # the count and the trail must agree: the audit measured "7 rows mention M1"
        # over a trail of 5, with nothing saying so — an honest surface says which five
        count_line = (f'{len(rows_known)} rows mention {s.upper()}'
                      + (f' — {len(shown)} most recent:' if len(shown) < len(rows_known)
                         else ':')) if rows_known else f'no rows mention {s.upper()} yet.'
        ground = face.get("ground", _MILESTONE_NOTE)
        mech = (f'<details class="mech"><summary>mechanics</summary>'
                f'<div class="mechbody">token <code>{s.upper()}</code> · approve '
                f'records a row with stage <code>front-door-{s}</code>, verdict '
                f'<code>accepted</code>; the campaign gate (<code>CAMP-R3</code>) '
                f'opens when all 4 stages have one. Defined in '
                f'<a href="#record/work_orders/id:{quote(ground)}" '
                f'title="{escape(ground)}">the programme note</a>.'
                f'<div style="margin-top:5px">{count_line}</div>{trail}'
                + '</details>')

        if st.get("walked"):
            head = (f'<b>{escape(name)}</b> {_chip("approved", "ok")} '
                    f'<a class="dim" href="#record/work_orders/id:{quote(st["row"])}" '
                    f'title="{escape(st["row"])}">your approval, recorded '
                    f'{escape(str(st.get("ts", ""))[:10])}</a>')
            body = ""
        elif st.get("retracted"):
            # a retracted acceptance does not change what the stage IS: an unbuilt stage
            # stays "not built", a built one stays walkable. The retraction is a fact
            # about the ledger, told after the state, not instead of it.
            head = (f'<b>{escape(name)}</b> '
                    + (_chip("awaiting your walk", "pend") if built
                       else _chip("not built", "dim")))
            when = str(st.get("ts", "") or "")[:10]
            recorded = (f"recorded automatically on {escape(when)} and withdrawn the "
                        f"same day" if when else
                        "recorded automatically and withdrawn")
            body = ((f'<div class="wgloss">{escape(gloss)}</div>' if gloss else "")
                    + f'<div class="wnotice"><b>Correction.</b> An approval for this '
                      f'stage was {recorded}. Nothing you approved is affected'
                    + ('.' if built else
                       '; this stage is not built, so no approval is expected from '
                       'you yet.') + '</div>')
            if built:
                body += ('<span data-walk="' + s + '">'
                         '<button type="button" class="act ok" data-verdict="accept">'
                         'approve</button>'
                         '<button type="button" class="act bad" data-verdict="redline">'
                         'redline…</button></span>')
        elif built:
            reds = len(st.get("redlines", []))
            head = (f'<b>{escape(name)}</b> {_chip("awaiting your walk", "pend")}'
                    + (f' <span class="dim">{reds} redline{"s" if reds != 1 else ""} '
                       f'banked</span>' if reds else ""))
            body = (f'<div class="wgloss">{escape(gloss)}</div>' if gloss else "")
            body += ('<span data-walk="' + s + '">'
                     '<button type="button" class="act ok" data-verdict="accept">'
                     'approve</button>'
                     '<button type="button" class="act bad" data-verdict="redline">'
                     'redline…</button></span>')
        else:
            head = f'<b>{escape(name)}</b> {_chip("not built", "dim")}'
            body = (f'<div class="wgloss">{escape(gloss)}</div>' if gloss else "")
        items.append(f'<div class="walkitem">{head}{body}{mech}</div>')

    open_built = [faces.get(s, {}).get("name", s.upper()) for s in _WALKABLE
                  if not state.get(s, {}).get("walked")]
    unbuilt = [faces.get(s, {}).get("name", s.upper()) for s in programme
               if s not in _WALKABLE]
    cap = ('Approve records your ruling as a row. The campaign gate opens when all '
           f'{len(programme)} stages are approved'
           + (f' — {escape(", ".join(open_built))} await you' if open_built else "")
           + (f'; {escape(", ".join(unbuilt))} are not built yet' if unbuilt else "")
           + '.')
    return ('<div class="walkstrip"><span class="zlabel">the walk gate</span>'
            + "".join(items)
            + f'<div class="cap">{cap}</div></div>')


# ------------------------------------------------------------------ the talk path (M2)


def _conversation_serve_projection(
    author_turn: dict[str, Any],
    provider: dict[str, Any],
    blueprint: dict[str, Any],
) -> dict[str, Any]:
    """Read exact custody, then call the one pure conversation projection.

    Missing custody is an input to the projection, never an invitation for a GET to
    self-heal it.  Any present receipt must reproduce the exact bytes it claims.
    """

    from laplace.representation import atlas_bridge
    from laplace.web import conversation_serve

    handle = conversation_serve.turn_handle(author_turn)
    custody_bytes = None
    try:
        custody = atlas_bridge.custody_body(handle=handle)
    except atlas_bridge.BlobMissing:
        pass
    else:
        if custody.get("content_handle") != handle:
            raise ValueError("author-turn custody receipt returned a different handle")
        text = custody.get("text")
        encoded = custody.get("base64")
        if isinstance(text, str) and encoded is None:
            custody_bytes = text.encode("utf-8")
        elif text is None and isinstance(encoded, str):
            custody_bytes = base64.b64decode(encoded, validate=True)
        else:
            raise ValueError("author-turn custody receipt has no exact byte representation")
        if custody.get("bytes") != len(custody_bytes):
            raise ValueError("author-turn custody receipt byte count disagrees")
    return conversation_serve.materialize_conversation_serve(
        author_turn,
        provider,
        blueprint,
        author_turn_custody_bytes=custody_bytes,
    )


def _conversation_serve_data(talk_id: str = "") -> dict[str, Any]:
    """Build one live conjugate serve without copying Atlas state into the front door."""

    from laplace.representation import atlas_bridge
    from laplace.web import conversation_serve

    talks = [
        row for _off, row in _rows.scan("talk")
        if row.get("record") == "talk"
        and row.get("schema_version") == "laplace.author-turn/1"
        and (not talk_id or row.get("id") == talk_id)
    ]
    if not talks:
        raise conversation_serve.AuthorTurnAbsent(f"author turn {talk_id!r} is absent")
    provider = atlas_bridge.snapshot()["provider"]
    blueprint = atlas_bridge.blueprint_projection(
        materialization_limit=None,
        result_limit=None,
    )
    return _conversation_serve_projection(talks[-1], provider, blueprint)


def _source_href(row: dict[str, Any]) -> str:
    return (
        "/front/serve/source?path=" + quote(str(row["source_path"]), safe="")
        + "&start=" + str(row["start"])
        + "&end=" + str(row["end"])
        + "&expect=" + quote(str(row["exact_byte_hash"]), safe="")
    )


def _implementation_href(row: dict[str, Any]) -> str:
    return (
        "/front/serve/source?path=" + quote(str(row["implementation_path"]), safe="")
        + "&start=0&end=" + str(row["implementation_size"])
        + "&expect=" + quote(str(row["implementation_hash"]), safe="")
    )


def _frag_conversation_serve(serve: dict[str, Any]) -> str:
    """The bounded author register; diagnostics remain behind explicit descent."""

    states = []
    for row in serve["recipient_states"]:
        label = escape(str(row["logical_recipient"]))
        phase = escape(str(row["phase"]))
        cls = "ok" if row["phase"] in {"reconstructed", "replied", "closed"} else "warn"
        states.append(
            f'<span class="walkitem">{label} {_chip(phase, cls)}</span>'
        )
    routes = []
    for route in serve["blueprint"]["routes"]:
        targets = []
        for result in route.get("results", ()):
            trail = " › ".join(str(item) for item in result.get("trail", ()))
            impl = result.get("implements", ())
            implementation_note = (
                " · " + ", ".join(
                    f'<a href="{escape(_implementation_href(item))}">'
                    f'{escape(str(item.get("implementation_path")))}</a>'
                    + " [" + escape(str(item.get("proof_state"))) + "]"
                    for item in impl
                    if item.get("implementation_size") is not None
                ) if impl else " · no implementation join"
            )
            targets.append(
                f'<li><a href="{escape(_source_href(result))}">{escape(trail)}</a>'
                f'<div class="cap mono">stable {escape(str(result["subject_id"]))}<br>'
                f'version {escape(str(result["content_handle"]))}{implementation_note}</div></li>'
            )
        routes.append(
            f'<div class="card"><div class="zlabel">spectral route · '
            f'{escape(str(route["materialization_id"]))}</div>'
            f'<div>{escape(str(route["goal"]))}</div>'
            f'<div class="cap dim">coverage {float(route["coverage"]):.3f} · '
            f'{len(targets)} exact mutation targets · '
            f'{int(route.get("omitted_results", 0))} more omitted at this grade'
            f'</div><ol>{"".join(targets)}</ol></div>'
        )
    residuals = "".join(
        f'<li><b>{escape(str(item["class"]))}</b> — {escape(str(item["cost"]))}</li>'
        for item in (*serve["omission_residual"], *serve.get("projection_residual", ()))
    )
    return (
        f'<div class="card"><div class="zlabel">conversation serve</div>'
        f'<h3>{escape(str(serve["author_lifecycle"]))}</h3>'
        f'<div class="facetrow">{"".join(states)}</div>'
        f'<div class="cap mono">shown {escape(str(serve["shown_handle"]))}<br>'
        f'blueprint {escape(str(serve["blueprint"]["generation_id"]))}</div></div>'
        + "".join(routes)
        + f'<div class="card"><div class="zlabel">priced omissions</div><ul>{residuals}</ul></div>'
        + _byline("talk", "one joined projection; talk is the saga root, Atlas is delivery truth")
    )


def _conversation_serve_get(query: dict[str, Any]) -> tuple[int, str, bytes]:
    from laplace.web.conversation_serve import AuthorTurnAbsent

    try:
        serve = _conversation_serve_data(_q1(query, "talk").strip())
    except AuthorTurnAbsent as exc:
        return 404, _JSON, json.dumps({"error": str(exc)}).encode("utf-8")
    except Exception as exc:  # noqa: BLE001 — stale ground refuses as a whole serve
        message = f"conversation serve refused: {type(exc).__name__}: {exc}"
        status = 409 if "stale" in str(exc).lower() or "frontier moved" in str(exc) else 503
        return status, _JSON, json.dumps({"error": message}).encode("utf-8")
    if _q1(query, "format") == "json":
        diagnostic = _q1(query, "diagnostic") == "1"
        if diagnostic:
            from laplace.web.conversation_serve import broker_projection

            serve["diagnostic"] = {
                "conversation_broker": broker_projection(),
                "browser_event_cursor": serve.get("browser_event_cursor"),
                "browser_head_event_id": serve.get("browser_head_event_id"),
                "recipient_transport": [
                    {
                        "seat_id": row.get("diagnostic_seat_id"),
                        "message_id": row.get("recipient_message_id"),
                        "state": row.get("transport_state"),
                    }
                    for row in serve["recipient_states"]
                ],
            }
        else:
            serve.pop("browser_event_cursor", None)
            serve.pop("browser_head_event_id", None)
            serve.pop("dependency_frontier", None)
            for key in ("recipient_states", "recipients"):
                for row in serve[key]:
                    row.pop("diagnostic_seat_id", None)
                    row.pop("transport_state", None)
                    row.pop("recipient_message_id", None)
            for reply in serve.get("replies", ()):
                reply.pop("status", None)
        return 200, _JSON, json.dumps(serve, ensure_ascii=False).encode("utf-8")
    return 200, _HTML, _frag_conversation_serve(serve).encode("utf-8")


def _conversation_body_get(query: dict[str, Any]) -> tuple[int, str, bytes]:
    from laplace.representation import atlas_bridge

    message_id = _q1(query, "message").strip()
    if not message_id:
        return 400, _JSON, b'{"error": "message required"}'
    try:
        body = atlas_bridge.message_body(message_id=message_id)
    except Exception as exc:  # noqa: BLE001 — exact descent refuses, never substitutes
        return 404, _JSON, json.dumps(
            {"error": f"exact body descent refused: {type(exc).__name__}: {exc}"}
        ).encode("utf-8")
    return 200, _JSON, json.dumps(body, ensure_ascii=False).encode("utf-8")


def _conversation_source_get(query: dict[str, Any]) -> tuple[int, str, bytes]:
    """Resolve an exact current blueprint span; never fuzzy-substitute its parent."""

    from laplace.representation import atlas_bridge

    relative = _q1(query, "path").strip()
    expected = _q1(query, "expect").strip()
    try:
        start = int(_q1(query, "start", "0"))
        end = int(_q1(query, "end", "0"))
    except ValueError:
        return 400, _JSON, b'{"error": "start and end must be integers"}'
    if not relative or not expected or start < 0 or end <= start:
        return 400, _JSON, b'{"error": "path, positive span and expect are required"}'
    try:
        blueprint = atlas_bridge.blueprint_projection(materialization_limit=12)
        if not blueprint.get("current"):
            moved = [str(row.get("path")) for row in blueprint.get("moved_source_roots", ())]
            raise ValueError(
                "stale blueprint frontier moved; exact descent is refused for the whole "
                f"generation ({', '.join(moved[:4]) or 'unknown source'})"
            )
        if relative not in blueprint["source_roots"]:
            raise ValueError("path is outside the current blueprint frontier")
        target = (_repo_root() / relative).resolve()
        if _repo_root().resolve() not in target.parents or not target.is_file():
            raise ValueError("source path escapes or is absent")
        data = target.read_bytes()
        if end > len(data):
            raise ValueError("span exceeds current source bytes")
        span = data[start:end]
        actual = "sha256:" + hashlib.sha256(span).hexdigest()
        if actual != expected:
            raise ValueError(f"exact span moved (expected {expected}, actual {actual})")
        text = span.decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        return 409, _JSON, json.dumps(
            {"error": f"exact blueprint descent refused: {type(exc).__name__}: {exc}"}
        ).encode("utf-8")
    payload = {
        "schema_version": "laplace.blueprint-span/1",
        "path": relative,
        "start": start,
        "end": end,
        "exact_byte_hash": actual,
        "content": text,
        "generation_id": blueprint["generation_id"],
    }
    if _q1(query, "format") == "json":
        return 200, _JSON, json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return 200, _HTML, (
        f'<meta charset="utf-8"><body style="background:#14161a;color:#d7dae0;'
        f'font:14px/1.5 monospace;margin:0;padding:18px 22px">'
        f'<div style="color:#5f6b7a">{escape(relative)} · {start}:{end} · '
        f'{escape(actual)}</div><pre style="white-space:pre-wrap">{escape(text)}</pre>'
    ).encode("utf-8")


def _prepare_talk_audience(requested: str) -> tuple[str, tuple[str, ...], str | None]:
    """Resolve the logical audience before banking; a read fault never loses his words."""

    from laplace.representation import atlas_bridge
    from laplace.web import conversation_serve

    try:
        provider = atlas_bridge.snapshot()["provider"]
        audience, recipients = conversation_serve.resolve_audience(provider, requested)
        error = None if recipients else "no active logical seat resolved"
        return audience, recipients, error
    except Exception as exc:  # noqa: BLE001
        return requested or "eigen", (), f"Atlas audience unavailable: {type(exc).__name__}: {exc}"


def _talk(body: bytes) -> tuple[int, str, bytes]:
    """Bank the author's message BEFORE it travels (T1, the relay-expiry cure made
    law: a dead relay leaves a visibly undelivered row, never silence). The row is
    his act through the shared banking path; delivery is a SEPARATE fact — a seat
    banks ``talk-read`` / ``talk-reply`` rows targeting the talk id, and the pane
    threads them at render. The scanner process has no living channel of its own to
    any seat (sockets are doorbells, rows are the wire — PV-20260824-his-durable-is-
    the-wire); the seats sweep this store at their rounds, and an unswept row GLOWS."""
    from laplace.core.records import journal as _journal
    try:
        req = json.loads(body or b"{}")
        assert isinstance(req, dict)
    except (ValueError, AssertionError):
        return 400, _JSON, b'{"error": "body must be a JSON object"}'
    text = str(req.get("text", "")).strip()
    if not text:
        return 400, _JSON, b'{"error": "an empty message banks nothing"}'
    if len(text) > 8000:
        return 400, _JSON, b'{"error": "over 8000 chars - split it"}'
    now = datetime.now(timezone.utc)
    audience, recipients, resolution_error = _prepare_talk_audience(
        str(req.get("audience", req.get("to", "eigen"))).strip() or "eigen"
    )
    seed = json.dumps(
        {"text": text, "audience": audience, "ts": now.isoformat()},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    row = {
        "schema_version": "laplace.author-turn/1",
        "record": "talk",
        "id": f"TALK-{now.strftime('%Y%m%dT%H%M%S%f')}-{hashlib.sha256(seed).hexdigest()[:10]}",
        "actor": "gerard",
        # WHAT HE WAS LOOKING AT WHEN HE ASKED. His steer, 2026-08-25: "if there's
        # anything like that, why don't I have the option to address or query it from
        # there?" A question asked from a pane arrives stripped of the pane unless the
        # act carries it — and then the seat that sweeps this store has to guess, which
        # is the same context-loss the surfaces themselves were committing. Free text
        # capped; absent when he asks from the composer rather than from a thing.
        "about": (str(req.get("about", "")).strip()[:300] or None),
        "to": audience,
        "audience": audience,
        "recipient_seat_ids": list(recipients),
        "text": text,
        "via": "front-door",
        "ts": now.isoformat(),
    }
    try:
        from laplace.representation import atlas_bridge
        from laplace.web import conversation_serve

        # Bind against the complete materialization frontier, then store a bounded selection plus
        # its exact residue.  Viewport caps must never decide a new turn's durable route identity.
        blueprint = atlas_bridge.blueprint_projection(
            materialization_limit=None, result_limit=1
        )
        binding = conversation_serve.bind_blueprint_routes(row, blueprint)
        row["blueprint_generation_id"] = blueprint["generation_id"]
        row["blueprint_materialization_ids"] = binding["selected_ids"]
        row["blueprint_route_binding"] = binding
    except Exception:
        # The author row still banks. The broker and serve price the absent design frontier;
        # inability to read a projection is never permission to lose his words.
        pass
    try:
        _journal.bank_row("contract/talk.jsonl", row, root=_repo_root())
    except Exception as e:  # noqa: BLE001
        return 500, _JSON, json.dumps(
            {"error": f"the bank failed and NOTHING was appended: "
                      f"{type(e).__name__}: {e}"}).encode("utf-8")
    from laplace.representation import atlas_bridge
    from laplace.web import conversation_serve

    turn = conversation_serve.turn_handle(row)
    custody = atlas_bridge.put_custody(conversation_serve.canonical_bytes({
        "schema_version": conversation_serve.AUTHOR_TURN_SCHEMA,
        "row": row,
    }))
    if custody != turn:
        return 500, _JSON, b'{"error": "author turn custody disagreement"}'
    payload = {
        "banked": row["id"],
        "audience": audience,
        "turn_handle": turn,
        # routed_count WAS THE LITERAL 0 with a "banked-for-broker" residual: his
        # message banked durably, resolved three recipients, and reached NONE of them,
        # reporting "0/3 routed; repair pending" in small text under the box. His
        # question: "who does it route to how and does it actually work? And how does
        # the feedback/acknowledgment arrive?" It did not work — the broker the residual
        # deferred to does not exist, and the acknowledgment path (a seat banking
        # talk-read/talk-reply) could never START because no seat was ever told.
        # It routes now, off the request path, and the outcome banks as talk-routed.
        # The count stays None until the sends land: a number here would be a delivery
        # claim made in advance, which is the thing this door was already doing.
        "routed_count": None,
        "intended_count": len([s for s in recipients if s != "interface-seat"]),
        "routing_complete": False,
        "routing_residual": [
            *([] if resolution_error is None else [{"error": resolution_error}]),
            # THIS SHIPPED A NUMBER NOBODY HAD MEASURED SINCE. It read "one fabric send
            # is ~53s (it replays the store)" — both clauses false by ce02f05b, which
            # replaced lifetime replay with verified suffix reads, as _dispatch_notice's
            # own docstring 600 lines up already said. Routing is off-thread because
            # transport availability is independent of banking his act, and that reason
            # holds at any send cost, so it is the reason the string states. No latency
            # is quoted here again without a fresh measurement to quote.
            {"state": "dispatching",
             "to": [s for s in recipients if s != "interface-seat"],
             "why": "routing runs off the request path so transport availability can "
                    "never delay or endanger the banking of his words; the per-seat "
                    "outcome banks as the talk-routed row ROUTED-"
                    f"{row['id']} in contract/talk.jsonl"},
        ],
    }
    _dispatch_notice(
        "a message for you", row,
        f"He wrote to '{audience}'. Reply by banking a talk-reply row targeting "
        f"{row['id']} in contract/talk.jsonl — the front door threads it back to him.",
        recipients)
    return 202, _JSON, json.dumps(payload).encode("utf-8")


def _frag_talk() -> str:
    """The talk pane: his messages threaded with the seats' read/reply rows — every
    delivery state computed from rows at render, never remembered. A talk row with
    no read/reply targeting it renders AWAITING loudly: banked is not delivered,
    and the pane never pretends otherwise."""
    talks: list[tuple[int, dict[str, Any]]] = []
    receipts: dict[str, list[dict[str, Any]]] = {}
    for off, row in _rows.scan("talk"):
        rec = row.get("record")
        if rec == "talk":
            talks.append((off, row))
        elif rec in ("talk-read", "talk-reply") and row.get("target"):
            receipts.setdefault(str(row["target"]), []).append(row)
    provider = blueprint = None
    serve_fault = None
    if any(row.get("schema_version") == "laplace.author-turn/1" for _off, row in talks):
        try:
            from laplace.representation import atlas_bridge

            provider = atlas_bridge.snapshot()["provider"]
            blueprint = atlas_bridge.blueprint_projection(
                materialization_limit=None,
                result_limit=None,
            )
        except Exception as exc:  # noqa: BLE001 — joined truth refuses loudly
            serve_fault = f"{type(exc).__name__}: {exc}"
    items: list[str] = []
    for off, t in talks[-30:]:
        tid = str(t.get("id", ""))
        got = receipts.get(tid, [])
        replies = [r for r in got if r.get("record") == "talk-reply"]
        joined = t.get("schema_version") == "laplace.author-turn/1"
        recipient_line = ""
        if joined and provider is not None and blueprint is not None:
            serve = _conversation_serve_projection(t, provider, blueprint)
            phase = str(serve["author_lifecycle"])
            state = _chip(
                phase,
                "ok" if phase in {"reconstructed", "replied", "closed"} else "warn",
            )
            recipient_line = '<div class="cap">' + " · ".join(
                f'{escape(str(row["logical_recipient"]))}: '
                f'{escape(str(row["phase"]))}'
                for row in serve["recipient_states"]
            ) + (
                f' · <a href="/front/serve?talk={quote(tid, safe="")}">'
                f'descend serve + blueprint</a></div>'
            )
        elif joined:
            state = _chip("serve refused", "bad")
            recipient_line = (
                f'<div class="cap red">{escape(str(serve_fault))} · '
                f'<a href="/front/serve?talk={quote(tid, safe="")}">exact refusal</a></div>'
            )
        elif replies:
            state = _chip("replied", "ok")
        elif got:
            state = _chip("read", "pend")
        else:
            state = _chip("awaiting a seat's round", "warn")
        thread = "".join(
            f'<div class="msg assistant"><div class="role">'
            f'{escape(str(r.get("actor", "seat")))}</div>'
            f'<pre>{escape(str(r.get("text", ""))[:4000])}</pre></div>'
            for r in replies)
        items.append(
            f'<div class="talkitem" data-row="talk@{off}">'
            f'<div class="msg user"><div class="role">you · {_ts_age(t.get("ts"))} ago '
            f'{state}</div><pre>{escape(str(t.get("text", ""))[:4000])}</pre>'
            f'{recipient_line}</div>'
            f'{thread}</div>')
    empty = ('' if items else
             '<div class="cap dim">nothing said yet — the first message founds the store</div>')
    return ('<div class="talkpane">' + "".join(items) + empty + "</div>"
            + _byline("talk", "banked-before-travelled; new turns join canonical Atlas "
                              "delivery, legacy read/reply rows remain visibly legacy"))


# ------------------------------------------------------------------ organ

def _frag_organ() -> str:
    trs = []
    for s in _sources.roster():
        if s.get("absent"):
            trs.append(f'<tr class="red"><td>{escape(s["name"])}</td>'
                       f'<td colspan="4">ABSENT — {escape(s.get("path", ""))}</td></tr>')
            continue
        red = ' class="red"' if s.get("red") else ""
        scan_note = "" if s.get("scan") else " (metadata-only)"
        trs.append(
            f'<tr{red}><td><a href="#explore/{escape(s["name"])}">{escape(s["name"])}</a>'
            f'{scan_note}</td><td class="num">{s["bytes"]:,} B</td>'
            f'<td>{_age_words(s["age_s"])} ago</td>'
            f'<td>{_age_words(s["budget_s"])} budget</td>'
            f'<td class="dim">{escape(s["label"])}</td></tr>')
    return (f'<div class="tablewrap"><table>'
            f'<tr><th>source</th><th>bytes</th><th>freshness</th><th>budget</th><th>label</th></tr>'
            f'{"".join(trs)}</table></div>'
            f'<div class="byline">[source] the registry (laplace.engine.sources) + os.stat, '
            f'recomputed at render {escape(_now_iso())}</div>'
            f'<h3>archaeology liveness — the judge&#8217;s grades</h3>'
            + _frag_liveness())


# ------------------------------------------------------------------ selftest

#: Doors that REQUIRE a parameter to mean anything. Fired bare they answer 404 — and
#: that is the door working, not failing: /front/serve says {"error": "author turn ''
#: is absent"}. The census used to flag it RED, so the one instrument whose job is to
#: prove the surface is honest carried a permanent false alarm. Same category error as a
#: founding ledger judged against a freshness budget: silence, or a refusal to guess, is
#: not death. (The 404 should arguably be a 400; that is the door's own bug, not the
#: census's, and it is not this seat's file.)
_PARAMETERISED_DOORS = frozenset({"/front/serve"})

#: the doors the census fires. Module scope so front_places can count them without a
#: second hand-typed list — the mistake this whole places table exists to stop.
#: THE CENSUSED SET. It is a NAMED LIST and drifted the moment a route was added without
#: one: /front/conceptric shipped as a route AND a nav place while staying out of this
#: tuple, so the QA chip read "12 doors · 0 not answering" over a door whose seat pane was
#: raising TypeError. A hand-maintained map that nothing checks is the standing defect
#: (FIND-20260825-handmaintained-nav-maps-drift); test_every_place_is_censused now holds
#: the places half of it, which is the half that reaches him.
_SELFTEST_DOORS = ("/front/conceptric", "/front/places", "/front/record", "/front/trace",
                   "/front/field", "/front/apex", "/front/atlas", "/front/development",
                   "/front/walk", "/front/serve",
                   "/front/grid", "/front/rows",
                   "/front/facets", "/front/acts", "/front/chats", "/front/talkpane",
                   "/front/organ", "/front/sources")

#: the door census banks its run here so the NAV CHIP can be a render of it rather than
#: a fresh fire. Firing all 12 doors costs ~17s — /front/atlas alone is a whole board
#: build — and it was happening inside /front/places, which the shell fetches AT BOOT.
#: Every door anyone adds made his front door slower to open. A chip is not worth a
#: measurement; it is worth the LAST measurement, stamped with its age.
_SELFTEST_BANK = ".selftest_doors.json"


def _bank_selftest(doors: int, down: int, detail: list[dict[str, Any]]) -> None:
    """Best-effort: a census that cannot bank still renders, it just cannot be cheap.

    NEVER FROM A TEST. FIND-20260825-test-suite-forges-production-receipts: _dispatch_notice
    resolved its root inside a daemon thread after pytest's monkeypatch had been torn down,
    and 42.5% of contract/talk.jsonl turned out to be pytest residue. codex cured that at
    6be772d5 this morning and I reintroduced the same class here within the hour - a test
    that fires the door census banked ITS door outcomes into the production bank, and the
    nav chip then rendered a test fixture's failure as a live door being down. A receipt is
    a claim about the running system; a test is not the running system.
    """
    import os
    if os.environ.get("LAPLACE_TEST_PROCESS") == "1" or "PYTEST_CURRENT_TEST" in os.environ:
        return
    try:
        (_repo_root() / _SELFTEST_BANK).write_text(json.dumps({
            "schema_version": "laplace.selftest-doors/1",
            "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "doors": doors, "down": down, "detail": detail}, indent=1), encoding="utf-8")
    except OSError:
        pass


def _frag_selftest() -> str:
    """The door census + the stores' honesty line — the QA department this surface
    has instead of one. Fires every GET door in-process (real stores, real timings),
    and reports each store's parse honesty (rows / malformed / partial tail / absent).
    A door that errors or a store that rots shows up HERE first, before his walk."""
    doors = list(_SELFTEST_DOORS)
    trs = []
    detail: list[dict[str, Any]] = []
    for door in doors:
        t0 = time.time()
        try:
            res = handle(door, {}, "GET", b"")
            ms = (time.time() - t0) * 1000
            if res is None:
                trs.append(f'<tr class="red"><td>{escape(door)}</td>'
                           f'<td colspan="3">fell through — no handler</td></tr>')
                detail.append({"door": door, "ok": False, "why": "no handler"})
                continue
            status, _ctype, payload = res
            wants_arg = door in _PARAMETERISED_DOORS and status in (400, 404)
            cls = "" if (status == 200 or wants_arg) else ' class="red"'
            note = (' <span style="color:#9CA1AB">— refused for want of a parameter, '
                    'which is the door working</span>' if wants_arg else "")
            trs.append(f'<tr{cls}><td>{escape(door)}{note}</td><td>{status}</td>'
                       f'<td class="num">{len(payload):,} B</td>'
                       f'<td class="num">{ms:.0f} ms</td></tr>')
            detail.append({"door": door, "ok": bool(status == 200 or wants_arg),
                           "status": status, "ms": round(ms)})
        except Exception as e:  # noqa: BLE001 — the census must outlive any one door
            trs.append(f'<tr class="red"><td>{escape(door)}</td>'
                       f'<td colspan="3">RAISED {escape(type(e).__name__)}: '
                       f'{escape(str(e)[:120])}</td></tr>')
            detail.append({"door": door, "ok": False,
                           "why": f"{type(e).__name__}: {str(e)[:120]}"})
    _bank_selftest(len(doors), sum(1 for d in detail if not d["ok"]), detail)
    doors_html = (f'<h3>the doors</h3><div class="tablewrap"><table>'
                  f'<tr><th>door</th><th>status</th><th>bytes</th><th>time</th></tr>'
                  f'{"".join(trs)}</table></div>')
    strs = []
    for name in _sources.SOURCES:
        rep = _rows.scan_report(name)
        if rep.get("absent"):
            strs.append(f'<tr class="red"><td>{escape(name)}</td>'
                        f'<td colspan="3">ABSENT</td></tr>')
        elif not rep.get("scanned", True):
            strs.append(f'<tr class="dim"><td>{escape(name)}</td>'
                        f'<td colspan="3">metadata-only, never scanned</td></tr>')
        else:
            bad = rep.get("malformed", 0)
            cls = ' class="red"' if bad else ""
            tail = " · partial tail (mid-append)" if rep.get("partial_tail") else ""
            strs.append(f'<tr{cls}><td>{escape(name)}</td>'
                        f'<td class="num">{rep.get("rows", 0):,} rows</td>'
                        f'<td class="num">{bad} malformed</td>'
                        f'<td class="dim">{tail}</td></tr>')
    stores_html = (f'<h3>the stores’ honesty line</h3><div class="tablewrap"><table>'
                   f'<tr><th>store</th><th>parsed</th><th>malformed</th><th></th></tr>'
                   f'{"".join(strs)}</table></div>')
    return (doors_html + stores_html
            + f'<div class="byline">[source] every door fired in-process against the '
              f'live stores at {escape(_now_iso())} — no number cached, no fixture</div>')


# ------------------------------------------------------------------ dispatch

def _respond(query: dict, html_fn, payload_fn=None) -> tuple[int, str, bytes]:
    """One door, two serializers — LAZY on both arms (the build wave's own review:
    eager evaluation ran every scan twice on the agent path). ``?format=json`` serves
    the payload where a payload producer exists; doors without one serve HTML and are
    named in handle()'s docstring — the json claim is exact, not aspirational."""
    if _q1(query, "format") == "json" and payload_fn is not None:
        return 200, _JSON, json.dumps(payload_fn()).encode("utf-8")
    return 200, _HTML, html_fn().encode("utf-8")


def _carrier_baseline_health() -> dict[str, Any]:
    """The admitted recovery baseline while the shared live health producer is pending.

    This is deliberately UPDATE-DUE, never CURRENT: the rebuild did not yet include the
    operational Atlas/devmap/lifecycle/Fabric/custody/seat adapters.  The values are the
    exact 2026-08-28T10:21:50Z full-rebuild receipt supplied by its producer; absent S/F
    coordinates remain absent rather than being guessed from this checkout.
    """

    return {
        "schema_version": "laplace.embedding-health/1",
        "status": "UPDATE-DUE",
        "shared": True,
        "current_source": {"commit": None, "tree": None},
        "fold": {
            "source_commit": None,
            "source_tree": None,
            "output_commit": None,
            "output_tree": None,
            "forward_relation": None,
            "semantic_horizon": "2026-08-28T10:21:50Z",
            "lag_commits": None,
            "manifest_handle": None,
            "coverage_handle": None,
        },
        "coverage": {
            "required_complete": False,
            "node_count": 23217,
            "vector_count": 24872,
            "cluster_count": None,
            "classes": [
                {"source_class": name, "count": None, "root": None,
                 "admitted": None, "omitted": None,
                 "reason": "OPERATIONAL-SOURCES-PENDING"}
                for name in ("devmap", "Atlas", "lifecycle", "Fabric", "custody", "seats")
            ],
        },
        "artifacts": {
            "root": "sha256:62e19106c6c9396f02a4e2abbe44f4affd931603681fc0e334e88d46ebaa5761",
            "count": None,
            "bytes": None,
            "cache_consistency": "UNKNOWN",
            "sidecar_consistency": "UNKNOWN",
        },
        "runtime": {
            "model": "baseline full rebuild",
            "backend": "spectral + embedding",
            "providers": ["CUDA", "CPU"],
            "device": "GPU",
            "required_gpu": True,
        },
        "latest_receipt": {
            "kind": "BASELINE-RECOVERED",
            "observed_at": "2026-08-28T10:21:50Z",
            "semantic_hello": {"passed": 5, "total": 5},
        },
        "semantic_reachability": {
            "status": "BASELINE-RECOVERED",
            "witnesses": ["semantic hello 5/5 PASS"],
        },
        "cadence": {
            "policy": "OPERATIONAL-SOURCES-PENDING",
            "queue_key": None,
            "queued": False,
            "running": False,
            "superseded_by": None,
            "last_success": "2026-08-28T10:21:50Z",
            "last_refusal": None,
            "latency_seconds": 135.7495,
            "resource_effect": "GPU required and used; metric redistilled",
        },
        "consumption": {"last_wake": None, "last_descent": None},
        "baseline": {
            "status": "BASELINE-RECOVERED / OPERATIONAL-SOURCES-PENDING",
            "nodes": 23217,
            "vectors": {"embedded": 2487, "content_identical_cached": 22385,
                        "deferred": 0, "pruned": 2421, "total": 24872},
            "duration_seconds": 135.7495,
            "metric_redistilled": True,
            "semantic_hello": "5/5 PASS",
        },
        "non_blocking": True,
        "authority_effect": "none",
    }


def _carrier_embedding_health() -> dict[str, Any]:
    """Read the one verified semantic side-ref face; never preserve a stale green cache.

    ``read_health`` owns currentness, receipt validation and the S->F relation.  The carrier
    deliberately performs no second Git/Atlas join.  A typed REFUSED/UNKNOWN face is still more
    truthful than falling back to the historical baseline now that the live producer exists.
    """

    from laplace.representation.embedding_health import read_health

    return read_health(_repo_root())


def _carrier_coordination_source() -> tuple[dict[str, Any] | None, str | None]:
    """Read the exact external custody capsule or return its loud integrity refusal."""

    try:
        raw = _DIRECT_COORDINATION_PATH.read_bytes()
    except OSError as exc:
        return None, f"direct coordination custody unavailable: {type(exc).__name__}: {exc}"
    observed = hashlib.sha256(raw).hexdigest()
    if observed != _DIRECT_COORDINATION_SHA256:
        return None, (
            "direct coordination custody digest mismatch: "
            f"expected {_DIRECT_COORDINATION_SHA256}, observed {observed}"
        )
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"direct coordination custody is not JSON: {exc}"
    if value.get("schema_version") != "laplace.external-direct-coordination-custody/1":
        return None, "direct coordination custody schema mismatch"
    return value, None


def _carrier_fabric_faces() -> tuple[dict[str, Any], dict[str, Any]]:
    capsule, refusal = _carrier_coordination_source()
    if capsule is None:
        return ({"fix_forward_state": "REFUSED", "fix_forward_next": refusal}, {
            "active": True,
            "coordination_reference": "CR-DIRECT-TASK-COORDINATION-SEMANTIC-RECOVERY-20260828",
            "source_task_ref": "UNKNOWN",
            "target_task_ref": "01a04236-f0bb-7761-86c6-ee383b76981f",
            "message_ref": None,
            "body_digest": None,
            "custody_artifact_digest": None,
            "retirement_predicate": "exact custody capsule is restored, then its canonical Fabric round trip succeeds",
        })
    live = capsule.get("live_fabric_observation") or {}
    watcher = live.get("watchers") or {}
    crutch = capsule.get("crutch") or {}
    source = capsule.get("source_provider") or {}
    recipients = capsule.get("recipient_tasks") or {}
    loss = capsule.get("development_loss_budget") or {}
    transport = capsule.get("transport") or {}
    seat_mail = live.get("seat_mail") if isinstance(live.get("seat_mail"), dict) else {}
    pending_count = sum(
        int(row.get("pending_count") or 0)
        for row in seat_mail.values()
        if isinstance(row, dict)
    )
    fabric = {
        "canonical": {
            "state": "UNKNOWN",
            "event_delta": None,
            "queue": pending_count,
            "seat_mail": seat_mail,
            "backpressure": None,
            "compaction_state": "UNKNOWN",
            "binding_summary": live.get("bindings"),
        },
        "watcher": {
            "state": watcher.get("status"),
            "attention_tokens": None,
            "seat": "sensorium-seat",
            "target_task": recipients.get("aisthesis"),
            "generation": None,
            "loaded_implementation": watcher.get("loaded_implementation_digest"),
            "current_implementation": watcher.get("current_implementation_digest"),
            "implementation_state": watcher.get("status"),
        },
        "metrics": {},
        "loss_budget": {
            "recoverable": loss.get("accepted_transient_loss"),
            "forbidden": loss.get("never_accepted"),
        },
        "fix_forward_state": "ACTIVE",
        "fix_forward_next": loss.get("recovery_loop"),
    }
    fallback = {
        "active": capsule.get("status") == "ACTIVE-EXTERNAL-FALLBACK",
        "transport": transport.get("kind"),
        "coordination_reference": crutch.get("id"),
        "source_task_ref": source.get("task_id"),
        "target_task_ref": recipients.get("aisthesis"),
        "message_ref": None,
        "body_digest": None,
        "message_count": transport.get("exact_direct_message_count"),
        "custody_artifact_digest": "sha256:" + _DIRECT_COORDINATION_SHA256,
        "canonical_claims": {
            "send": transport.get("canonical_fabric_send_claim"),
            "pull": transport.get("canonical_fabric_pull_claim"),
            "reconstruction": transport.get("canonical_fabric_reconstruction_claim"),
            "acknowledgement": transport.get("canonical_fabric_acknowledgement_claim"),
            "reply": transport.get("canonical_fabric_reply_claim"),
        },
        "retirement_predicate": crutch.get("retirement_predicate"),
    }
    return fabric, fallback


def _carrier_development(query: dict[str, Any]) -> dict[str, Any]:
    from laplace.web import development_lens

    request = {
        "format": "json",
        "lens": "programme",
        "focus": _q1(query, "focus"),
        "edge": _q1(query, "edge"),
        "grade": _q1(query, "grade", "mid"),
        "exposition": _q1(query, "exposition", "E0"),
        "viewport": _q1(query, "viewport", "wide"),
    }
    status, _ctype, body = development_lens.handle(request)
    try:
        payload = json.loads(body)
    except (TypeError, json.JSONDecodeError):
        return {"status": "REFUSED", "reason": "Development projection returned non-JSON"}
    if status != 200:
        return {"status": "REFUSED", "reason": payload.get("error", f"HTTP {status}")}
    return payload


def _carrier_semantic_junction(
    embedding_health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project the live compact fold while preserving genuinely absent producers."""

    from laplace.engine import front_semantic_junction

    return front_semantic_junction.project_semantic_junction(
        atlas_updown=None,
        meaning_upfold=None,
        compact_fold=embedding_health,
        register_dictionary=None,
        active_register_generation=None,
    )


def _carrier_author_ruling(grade: str) -> dict[str, Any]:
    """Admit pinned ruling bytes and preserve refusal beside current cut law."""

    from laplace.engine import front_author_ruling

    grade = grade if grade in {"far", "mid", "near", "audit"} else "far"
    cut = None
    cut_refusal = None
    try:
        cut = front_author_ruling.load_publication_cut_law()
    except front_author_ruling.AuthorRulingRefusal as exc:
        cut_refusal = exc.as_dict()
    try:
        custody = front_author_ruling.load_exact()
    except front_author_ruling.AuthorRulingRefusal as exc:
        # The author-ruling file has moved beyond its admitted bytes.  Preserve that
        # exact refusal while retaining the independently pinned publication-cut law.
        policy = front_author_ruling._publication_cut_policy(cut, grade=grade)
        face = {
            "schema_version": front_author_ruling.PROJECTION_SCHEMA,
            "status": "REFUSED",
            "human_summary": {
                "title": "Post-publication semantic and lifecycle regularization",
                "state": "REFUSED",
                "reason": exc.detail,
            },
            "currentness": {
                "schema_version": front_author_ruling.CURRENTNESS_SCHEMA,
                "status": "REFUSED",
                "reason": exc.detail,
                "refusal_code": exc.code,
            },
            "publication_cut_policy": policy,
            "exact_descent": {
                "visibility": "AUDIT_ONLY",
                "author_ruling_refusal": exc.as_dict(),
                "publication_cut_refusal": cut_refusal,
            },
            "read_only": True,
            "authority_effect": "none",
        }
        face["projection_handle"] = front_author_ruling.canonical_handle(face)
        return face
    face = front_author_ruling.project(custody, publication_cut=cut, grade=grade)
    if cut_refusal is not None:
        face["publication_cut_refusal"] = cut_refusal
        preimage = dict(face)
        preimage.pop("projection_handle", None)
        face["projection_handle"] = front_author_ruling.canonical_handle(preimage)
    return face


def _carrier_projection(query: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Join existing read producers once, then hand their bytes to the pure carrier."""

    from laplace.engine import front_carrier
    from laplace.web import front_places, front_work
    from laplace.pipeline import registry

    requested_lens = (_q1(query, "lens", "now") or "now").casefold()
    if requested_lens in {"now", "decision"}:
        apex = _apex_data()
    else:
        apex = {"account": {}, "asks": [], "campaign": {}, "rendered_at": None}
    if requested_lens in {"programme", "conversation", "exposition"}:
        development = _carrier_development(query)
    else:
        development = {
            "status": "UNKNOWN",
            "reason": (
                "the Development projection is room-scoped and has not been "
                "materialized for this camera"
            ),
            "objects": [],
            "edges": [],
        }
    places = front_places.census() if requested_lens == "diagnostics" else {"places": []}
    account = apex.get("account") if isinstance(apex.get("account"), dict) else {}
    asks = apex.get("asks") if isinstance(apex.get("asks"), list) else []

    attention_objects = [
        {"handle": f"attention:{key}", "human_label": label, "state": "OPEN",
         "summary": f"{value} currently recorded", "count": value}
        for key, label in (
            ("work_orders_open", "Open work"),
            ("promises_open", "Open promises"),
            ("thread_reds", "Thread refusals"),
            ("defects", "Known defects"),
        )
        if isinstance(account.get(key), int) and account.get(key)
        for value in (account[key],)
    ]
    now = {
        "status": "UNKNOWN",
        "human_label": "What needs you",
        "summary": (
            "The account is exact, but active seat goals have not yet joined this carrier; "
            "the present frontier is therefore not claimed complete."
        ),
        "facts": {"open work": account.get("work_orders_open"),
                  "open promises": account.get("promises_open"),
                  "thread refusals": account.get("thread_reds"),
                  "known defects": account.get("defects")},
        "objects": attention_objects,
        "omission": {
            "class": "UNRESOLVED", "count": 1,
            "reason": "canonical active-seat-goals projection is not yet exposed",
            "continuation": "laplace.three-seat-goals/1 adapter",
        },
    }
    programme = {
        "status": development.get("status", "UNKNOWN"),
        "human_label": "Canonical review frontier",
        "summary": "The admitted programme projection; active seat goals remain a named omission.",
        "objects": development.get("objects", []),
        "edges": development.get("edges", []),
        "field": development.get("causal_atlas_weave"),
        "shown_state": development.get("shown_state"),
        "questions": development.get("questions"),
        "omission": now["omission"],
    }
    selected_project = _q1(query, "project") or _q1(query, "corpus")
    projects = [
        {
            "handle": f"project:{name}",
            "project": name,
            "human_label": name.replace("-", " ").replace("_", " "),
            "summary": "Open the manuscript walk and governed pipeline around this project.",
            "state": "AVAILABLE",
        }
        for name in registry.all_projects()
    ]
    if selected_project:
        work_model = front_work.read(
            project_name=selected_project,
            corpus=selected_project,
            repo_root=_repo_root(),
            observation_time="",
            source_currentness={"status": development.get("status", "UNKNOWN")},
        )
    else:
        work_model = front_work.project(
            observation_time="",
            source_currentness={"status": development.get("status", "UNKNOWN")},
        )
    work_objects = [
        {
            "handle": capability.get("semantic_anchor"),
            "human_label": capability.get("label"),
            "summary": capability.get("reason"),
            "state": capability.get("state"),
            "family": capability.get("family"),
            "disposition": capability.get("disposition"),
            "continuation": capability.get("continuation"),
            "evidence": capability.get("evidence"),
            "sources": capability.get("source"),
            "reads": capability.get("reads"),
            "acts": capability.get("acts"),
        }
        for organ in work_model.get("organs", [])
        if isinstance(organ, dict)
        for capability in organ.get("capabilities", [])
        if isinstance(capability, dict) and capability.get("disposition") != "RETIRE"
    ]
    work = {
        **work_model,
        "status": (
            "CURRENT" if work_model.get("state") == "COMPLETE"
            else work_model.get("state", "UNKNOWN")
        ),
        "human_label": "Work under custody",
        "summary": (
            f"The manuscript walk and pipeline for {selected_project}."
            if selected_project
            else "Choose a project; its real Walk/editor and Pipeline mechanisms open here without importing their old shells."
        ),
        "selected_project": selected_project or None,
        "projects": projects,
        "objects": work_objects if selected_project else projects,
    }
    decisions = {
        "status": "CURRENT" if requested_lens == "decision" else "UNKNOWN",
        "human_label": "Your judgment",
        "summary": "Only exact pending author asks are shown.", "objects": asks,
    }
    acts = _trace.acts(40) if requested_lens == "run" else []
    run = {
        "status": "CURRENT" if requested_lens == "run" else "UNKNOWN",
        "human_label": "What is happening",
        "summary": "Exact recent act records; no decorative traffic.", "events": acts,
    }
    continuity = development.get("continuity_field")
    conversation = {
        "status": ((continuity or {}).get("state", "UNKNOWN")
                   if isinstance(continuity, dict) else "UNKNOWN"),
        "human_label": "The causal conversation",
        "summary": "Attention remains distinct from delivery, reconstruction and acknowledgement.",
        "phases": ((continuity or {}).get("objects", [])
                   if isinstance(continuity, dict) else []),
        "field": continuity,
    }
    selected = development.get("selected") if isinstance(development.get("selected"), dict) else {}
    exposition = {
        "status": development.get("status", "UNKNOWN"),
        "human_label": "Understand this object", "object": selected,
        "purpose": selected.get("label"),
        "evidence": development.get("projection_evidence_edges", []),
    }
    diagnostic_objects = [
        {"handle": f"place:{row.get('id')}", "human_label": row.get("noun"),
         "summary": row.get("why"), "status": row.get("freshness", "UNKNOWN"),
         "chips": row.get("chips", []), "route": row.get("href")}
        for row in places.get("places", [])
    ]
    diagnostics = {
        "status": "UNKNOWN", "human_label": "Where trust breaks",
        "summary": "Source health and Semantic Memory are shown without collapsing missing evidence into green.",
        "objects": diagnostic_objects,
    }
    producers = {
        "now": now, "programme": programme, "work": work,
        "decision": decisions, "run": run, "conversation": conversation,
        "exposition": exposition, "diagnostics": diagnostics,
    }
    fabric_observation, direct_coordination = _carrier_fabric_faces()
    embedding_health = _carrier_embedding_health()
    grade = _q1(query, "grade", "mid")
    kwargs = {
        "producers": producers,
        "embedding_health": embedding_health,
        "binding_observation": None,
        "fabric_observation": fabric_observation,
        "direct_coordination": direct_coordination,
        "coordination_profile": None,
        "semantic_junction": _carrier_semantic_junction(embedding_health),
        "author_ruling": _carrier_author_ruling(grade),
        "lens": _q1(query, "lens", "now"),
        "focus": _q1(query, "focus") or None,
        "edge": _q1(query, "edge") or None,
        "grade": grade,
        "exposition": _q1(query, "exposition", "E0"),
        "viewport": _q1(query, "viewport", "wide"),
    }
    return front_carrier.project(**kwargs), kwargs


def _carrier_model_get(query: dict[str, Any]) -> tuple[int, str, bytes]:
    from laplace.engine import front_carrier

    model, kwargs = _carrier_projection(query)
    if _q1(query, "format") == "currentness":
        payload = front_carrier.currentness(model, **{
            key: kwargs[key] for key in (
                "producers", "embedding_health", "binding_observation",
                "fabric_observation", "direct_coordination", "coordination_profile",
                "semantic_junction", "author_ruling",
            )
        })
    else:
        active = model.get("active_room", {})
        payload = {
            **model,
            "foreground_room": active.get("payload"),
            "shown_handle": model.get("shown_state", {}).get("shown_handle"),
            "currentness": {
                "state": model.get("semantic_memory", {}).get("state", "UNKNOWN"),
                "reason": model.get("semantic_memory", {}).get("health_status"),
            },
        }
    return 200, _JSON, json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _front_feedback_adapter():
    """Return the one canonical Atlas-backed carrier feedback adapter."""

    from laplace.representation.atlas_bridge import AtlasFrontFeedbackAdapter

    return AtlasFrontFeedbackAdapter()


def _front_feedback_get(query: dict[str, Any]) -> tuple[int, str, bytes]:
    """Read carrier-wide feedback from canonical Atlas history only."""

    from laplace.engine import front_feedback

    visible = query.get("visible_anchor", [])
    if isinstance(visible, str):
        visible = [visible]
    elif not isinstance(visible, list):
        visible = []
    payload = front_feedback.read(
        _front_feedback_adapter(),
        visible_anchor_ids=[str(item) for item in visible if str(item).strip()],
    )
    return 200, _JSON, json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _front_feedback_post(body: bytes) -> tuple[int, str, bytes]:
    """Append through canonical Atlas history; never fall back to another ledger."""

    from laplace.engine import front_feedback

    try:
        command = json.loads(body or b"{}")
    except (TypeError, json.JSONDecodeError):
        return 400, _JSON, json.dumps({
            "ok": False,
            "status": "REFUSED",
            "refusal": "INVALID_FEEDBACK_JSON",
            "reason": "feedback command body must be one JSON object",
            "authority_effect": "none",
        }).encode("utf-8")
    payload = front_feedback.execute(
        _front_feedback_adapter(),
        command,
        occurred_at=datetime.now(timezone.utc).isoformat(),
    )
    status = 200 if payload.get("ok") is True else 503
    return status, _JSON, json.dumps(payload, ensure_ascii=False).encode("utf-8")


def handle(path: str, query: dict[str, Any], method: str, body: bytes):
    """The scanner-dispatch door. GET only at M1 (the read stage); ``None`` means
    "not mine, fall through". ``/front/stream`` never arrives here — the scanner
    routes it to ``laplace.web.stream.serve`` directly (a stream cannot ride this
    whole-body contract)."""
    if method == "POST":
        # M2's two writes — the ask-door and the talk path; both bank HIS acts
        # through the shared banking path. Every other POST falls through loudly.
        if path == "/front/decide":
            return _decide(body)
        if path == "/front/talk":
            return _talk(body)
        if path == "/front/walked":
            return _walked(body)
        if path == "/front/walkserve":
            return _walk_serve_verdict(body)
        if path == "/front/feedback":
            return _front_feedback_post(body)
        return None
    if method != "GET":
        return None
    if path == "/front":
        try:
            return 200, _HTML, _PAGE.read_bytes()
        except OSError:
            return 500, _JSON, b'{"error": "front_carrier.html missing"}'
    if path == "/front/model":
        return _carrier_model_get(query)
    if path == "/front/feedback":
        return _front_feedback_get(query)
    if path == "/front/apex":
        seen_raw = _q1(query, "seen").strip()
        seen = float(seen_raw) if seen_raw.replace(".", "", 1).isdigit() else None
        return _respond(query, lambda: _frag_apex(seen), _apex_data)
    if path == "/front/atlas":
        try:
            # A PAGE, NOT A FRAGMENT — see _page_shell for the measurement. The board
            # producer renders its own chrome, back link, title and palette, so it takes
            # the bare shell: _document's fixed chrome would land on top of the board's
            # own at the same top:0.
            return _respond(query,
                            lambda: _page_shell("the atlas board", _frag_atlas_board()),
                            _atlas_board_payload)
        except Exception as exc:  # noqa: BLE001 - a broken mount refuses loudly
            message = f"atlas board refused: {type(exc).__name__}: {exc}"
            if _q1(query, "format") == "json":
                return 500, _JSON, json.dumps({"error": message}).encode("utf-8")
            # A refusal is the one page here with no producer to dress it, so it takes
            # the full house register — and a way back off a dead end.
            return 500, _HTML, _document(
                "the atlas board refused",
                f'<p style="color:var(--bad)">{escape(message)}</p>').encode("utf-8")
    if path == "/front/development":
        from laplace.web import development_lens

        return development_lens.handle(query)
    if path == "/front/development/causal_atlas_weave.mjs":
        try:
            return 200, "text/javascript; charset=utf-8", _CAUSAL_WEAVE.read_bytes()
        except OSError:
            return 500, _JSON, b'{"error": "Causal Atlas Weave module missing"}'
    if path == "/front/walk":
        try:
            return _walk_serve_get(query)
        except Exception as exc:  # noqa: BLE001 - a broken serve refuses loudly
            message = f"walk serve refused: {type(exc).__name__}: {exc}"
            if _q1(query, "format") == "json":
                return 500, _JSON, json.dumps({"error": message}).encode("utf-8")
            return 500, _HTML, _document(
                "the founding walk refused",
                f'<p style="color:var(--bad)">{escape(message)}</p>').encode("utf-8")
    if path == "/front/serve":
        return _conversation_serve_get(query)
    if path == "/front/serve/body":
        return _conversation_body_get(query)
    if path == "/front/serve/source":
        return _conversation_source_get(query)
    if path == "/front/grid":
        return _respond(query, _frag_grid)          # html-only door
    if path == "/front/rows":
        src = _q1(query, "source", "journal")
        expr = _q1(query, "q")
        limit = _qint(query, "limit", 50, _rows.MAX_LIMIT)
        return _respond(query, lambda: _frag_rows(src, expr, limit),
                        lambda: _rows.query(src, expr, limit))
    if path == "/front/facets":
        src = _q1(query, "source", "journal")
        return _respond(query, lambda: _frag_facets(src, _q1(query, "q")),
                        lambda: _rows.facets(src, _q1(query, "q")))
    if path == "/front/acts":
        n = _qint(query, "limit", 40, 500)
        return _respond(query, lambda: _frag_acts(n), lambda: _trace.acts(n))
    if path == "/front/trace":
        act = _q1(query, "act")
        return _respond(query, lambda: _frag_trace(act), lambda: _trace.act_tree(act))
    if path == "/front/record":
        src = _q1(query, "source")
        off, rid = _qoff(query), _q1(query, "id")
        return _respond(query, lambda: _frag_record(src, off, rid or None))  # html-only
    if path == "/front/field":
        src = _q1(query, "source")
        off = _qoff(query)
        if off is None:
            return 400, _JSON, b'{"error": "off required"}'
        return _field_value(src, off, _q1(query, "path"))
    if path == "/front/talkpane":
        return _respond(query, _frag_talk)          # html-only door
    if path == "/front/places":
        # THE PLACES CENSUS — the nav, the digit keymap and the no-route message are all
        # renders of this one payload. It replaces three hand-maintained maps in
        # front_door.html that had already drifted from each other, and it is how
        # /front/walk finally becomes reachable: it was served here all along and named
        # in none of them.
        from laplace.web import front_places as _places
        return 200, _JSON, json.dumps(_places.census()).encode("utf-8")
    if path == "/front/selftest":
        # A DOCUMENT, NOT A FRAGMENT. This door is never fetched by the shell (it is not
        # a route of the router — grep: 0 references), so it is only ever visited
        # directly, and it was being served as a bare fragment: no doctype, no title, no
        # stylesheet, transparent body. Measured, it rendered as 16px black Times New
        # Roman on WHITE — a flashbang, in a dark-only instrument, on the one page whose
        # job is to certify that every other page works.
        return _respond(query, lambda: _document(
            "the door census", _frag_selftest(),
            f"{len(_SELFTEST_DOORS)} of the door's GET routes, fired in-process against "
            f"real stores. It is a NAMED LIST, not every route — a route absent from it is "
            f"uncertified, not certified green, and test_every_place_is_censused holds the "
            f"places map inside it."))
    if path.startswith("/front/conceptric/"):
        # THE INTERROGATION DOORS. The page holds no copy of the store: a seat, an event
        # and the live delta are each fetched when he asks for them, so what he opens is
        # what is true now rather than what was true when the page rendered.
        from laplace.engine import descent_telemetry as _dt
        leaf = path.rsplit("/", 1)[-1]
        try:
            if leaf == "delta":
                raw = _q1(query, "after").strip()
                after = int(raw) if raw.lstrip("-").isdigit() else 0
                body = _dt.delta(after)
            elif leaf in ("seat", "event"):
                # AN EMPTY ID IS A CALLER ERROR, NEVER A WILDCARD. `?id=` fell through to
                # the first row in the store and rendered a real, plausible, WRONG record —
                # a descend link that loses its id showed a confident answer instead of
                # saying it was missing. A bogus id already refused correctly; only empty
                # slipped, which is the same shape as re.compile("") matching every row
                # that account_seat was hardened against.
                ident = _q1(query, "id").strip()
                if not ident:
                    return 400, _JSON, json.dumps({
                        "absent": "", "door": path,
                        "why": "this door needs an id; an empty one is a caller error, "
                               "not a request for whatever happens to be first"},
                    ).encode("utf-8")
                body = (_dt.seat_detail(ident) if leaf == "seat"
                        else _dt.event_detail(ident))
            else:
                return None
            return 200, _JSON, json.dumps(body, default=str).encode("utf-8")
        except Exception as exc:  # noqa: BLE001 - a broken door refuses loudly, in JSON
            return 500, _JSON, json.dumps({
                "error": f"{type(exc).__name__}: {exc}", "door": path}).encode("utf-8")
    if path == "/front/conceptric":
        # W12, his commission: the seats, the calls they make through the conceptric, and
        # what returns. A DOCUMENT, not a fragment (the /front/selftest precedent) — it is
        # a whole instrument with its own SVG and its own palette, and serving it bare
        # leaves the browser to invent a white page around a dark graph.
        try:
            from laplace.engine import descent_telemetry
            # A DOCUMENT, AND NOW ACTUALLY ONE. This comment claimed the
            # /front/selftest precedent while the door returned a bare fragment:
            # document.compatMode measured BackCompat, doctype null, no viewport meta.
            # It escaped the white flash only because its own inline CSS paints the body,
            # which is luck, not correctness — and mobile layout was wrong throughout.
            return _respond(
                query,
                lambda: _document("the conceptric",
                                  descent_telemetry.render(descent_telemetry.project())),
                descent_telemetry.project)
        except Exception as exc:  # noqa: BLE001 - a broken instrument refuses loudly
            message = f"conceptric telemetry refused: {type(exc).__name__}: {exc}"
            if _q1(query, "format") == "json":
                return 500, _JSON, json.dumps({"error": message}).encode("utf-8")
            return 500, _HTML, f'<p class="red">{escape(message)}</p>'.encode("utf-8")
    if path == "/front/chats":
        return _respond(query, _frag_chats, _chats_data)
    if path == "/front/chat":
        n = _qint(query, "limit", 80, 1000)
        return _respond(query, lambda: _frag_chat(_q1(query, "sid"), n))  # html-only
    if path == "/front/organ":
        return _respond(query, _frag_organ, _sources.roster)
    if path == "/front/sources":
        return 200, _JSON, json.dumps(_sources.roster()).encode("utf-8")
    return None
