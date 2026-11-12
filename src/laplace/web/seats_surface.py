"""THE SEATS SURFACE (front door M1, the read half) — the night's three stopgaps, one page.

His commission (PV-20260823-his-front-door-commission) and his pace ruling
(PV-20260824-his-move-quickly-interface-first: "move quickly until the interface is set
up to route these permission asks back"): one served page subsuming the seat board, the
live-session view, and the account/campaign panels — every number carrying its row
source, every session id resolved through THE ONE AUTHORITY
(``~/.claude/sessions/<pid>.json`` sessionId = the transcript uuid;
NOTE-20260824-resume-canonical-form: no id travels to the author unverified).

THE PERMISSION-ASK LANE (the reason this surface exists tonight): a seat that would hit
a permission prompt does NOT fire the act (AMEND-20260824-seats-never-prompt layer 1) —
it banks an ``ASK-*`` row into ``corpus_friction/work_orders.jsonl`` naming the blocked
act, and THIS surface renders those rows to his eyes with the seat, the act, and the why.
The write half (his click approving back) is M2/M3 territory - the interface seat's,
behind his gates; M1 makes the asks VISIBLE, which is the half that kills silent hangs.

THE QUIET-SEAT DETECTOR (layer 4, mechanized — with its honesty bar): the sessions
panel joins the socket dir against transcript mtimes; a live socket whose transcript
froze past the threshold renders "quiet — may be hung". Quiet-watching and prompt-hung
are mechanically indistinguishable from outside (the surface's own first fire flagged
the grandfather's deliberately-quiet porch), so the label claims only what the mtime
knows; the ASK lane is the panel that says a seat is definitely waiting on him.

TWO REGISTERS, ONE WORD "SEAT" (FIND-20260825-seats-one-label-two-registries). The nav
chip for this page read "6 seats · 81 in flight" in amber while the page it opened read
"3 seats · none pending — no seat is blocked on you" in calm grey. Neither was wrong and
neither was lying: they count different stores. The FABRIC register (the conceptric
store behind ``laplace.representation.atlas_bridge``) is an address book — every process that has ever
registered to send or receive fabric mail — plus that mail. The LIFECYCLE register
(``contract/seats.jsonl``) is the charter roll — the seats founded by the author's hand
under the two-seat charter. A fabric address is not a founded seat, so 6 and 3 are not
two answers to one question. This module now serves BOTH, each naming its own store, and
serves the nav chip's own numbers beside its own so a divergence renders as a divergence
instead of as two confident numbers on two surfaces.

Scanner-dispatch idiom: ``handle(path, query, method, body)`` — ``GET /seats/data`` is
the one fetch; the bare ``/seats`` page is served by the scanner from
``seats_surface.html``. Read-only against every store it reads: this module writes no
row, ever (the fabric census banks an in-memory receipt, and nothing else).
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_JSON = "application/json; charset=utf-8"

#: a live socket whose transcript is older than this is served as HUNG (judge-2 sat
#: invisible for hours; judge-4 for nine minutes — five minutes catches both shapes
#: without flagging a seat that is merely thinking between tool calls).
HUNG_AFTER_S = 300

#: A fabric message is IN FLIGHT while it is ``queued`` (nobody has pulled it) or
#: ``pulled`` (a seat holds it and has not acknowledged). This is the nav chip's rule
#: verbatim — ``front_places._census_seats`` sums the same two statuses — and the two
#: must stay identical or the chip and the page it opens disagree again. ``_fabric_registry``
#: therefore serves the chip's own count beside this one and compares them at render time,
#: which is the check a comment here could only assert.
IN_FLIGHT_STATUSES = ("queued", "pulled")

_FABRIC_LOCK = threading.Lock()
_FABRIC_CACHE: dict[str, Any] = {}


def _repo_root() -> Path:
    return source_tree()


def _sessions_authority() -> list[dict[str, Any]]:
    """The CLI's own session records — THE id authority — joined to transcript
    freshness and socket liveness. Serves name, canonical sessionId, resume command,
    freshness, and the hung verdict. Missing dirs serve empty, never raise."""
    out: list[dict[str, Any]] = []
    sess_dir = Path.home() / ".claude" / "sessions"
    sock_dir = Path(os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000")) / "cc-socks"
    proj_root = Path.home() / ".claude" / "projects"
    now = time.time()
    try:
        records = sorted(sess_dir.glob("*.json"))
    except OSError:
        return out
    for rec in records:
        try:
            d = json.loads(rec.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        sid = str(d.get("sessionId") or "")
        pid = str(d.get("pid") or rec.stem)
        socket_alive = (sock_dir / f"{pid}.sock").exists()
        transcript = None
        t_age: float | None = None
        for cand in proj_root.glob(f"*/{sid}.jsonl"):
            transcript = cand
            try:
                t_age = now - cand.stat().st_mtime
            except OSError:
                pass
            break
        hung = bool(socket_alive and t_age is not None and t_age > HUNG_AFTER_S)
        out.append({
            "name": d.get("name"),
            "pid": pid,
            "session_id": sid,
            "cwd": d.get("cwd"),
            "socket_alive": socket_alive,
            "transcript_age_s": round(t_age, 1) if t_age is not None else None,
            "transcript_known": transcript is not None,
            "hung": hung,
            "resume": f"claude --resume {sid}" if sid else None,
        })
    out.sort(key=lambda r: (not r["socket_alive"], r["transcript_age_s"] or 1e12))
    return out


def _seat_rows(root: Path) -> dict[str, Any]:
    """contract/seats.jsonl — current (latest-per-seat) plus the raw history tail."""
    try:
        from laplace.engine.seats import current_seats
        current = current_seats(root)
    except Exception as e:  # noqa: BLE001 - a broken store serves its error, not a crash
        return {"current": [], "error": f"{type(e).__name__}: {e}", "history_tail": []}
    tail: list[dict[str, Any]] = []
    store = root / "contract" / "seats.jsonl"
    try:
        lines = store.read_text(encoding="utf-8").splitlines()[-8:]
        for line in lines:
            try:
                tail.append(json.loads(line))
            except ValueError:
                pass
    except OSError:
        pass
    return {"current": current, "history_tail": tail}


def _pending_asks(root: Path) -> list[dict[str, Any]]:
    """The permission-ask lane: open ``ASK-*`` rows in the work-orders store — the
    route-around rows a promptless seat banks instead of firing a promptable act
    (AMEND-20260824-seats-never-prompt layer 1). Resolution rows retire them exactly
    as work orders retire (target/supersedes, latest wins)."""
    store = root / "corpus_friction" / "work_orders.jsonl"
    asks: dict[str, dict[str, Any]] = {}
    closed: set[str] = set()
    try:
        for line in store.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            rid = str(r.get("id") or "")
            if rid.startswith("ASK-"):
                asks[rid] = r
            t = r.get("target") or r.get("supersedes")
            if r.get("record") == "resolution" and str(t or "").startswith("ASK-"):
                closed.add(str(t))
    except OSError:
        pass
    return [r for rid, r in sorted(asks.items()) if rid not in closed]


def _nav_chip_counts() -> dict[str, Any]:
    """What the nav chip for "the seats" is claiming right now, from the chip's OWN
    producer — never a second implementation of its arithmetic.

    The point is not to display the chip twice. It is that this page can no longer
    contradict the chip silently: if ``front_places`` ever changes what it counts, the
    comparison in ``_fabric_registry`` goes False and the page says so on the pane.
    """
    try:
        from laplace.web import front_places
        census = front_places._census_seats()
    except Exception as e:  # noqa: BLE001 - the chip's absence is a value, not a crash
        return {"state": "unreadable", "seats": None, "in_flight": None,
                "error": f"{type(e).__name__}: {e}"}
    out: dict[str, Any] = {"state": "measured", "seats": None, "in_flight": None,
                           "source": census.get("source")}
    for chip in census.get("chips") or []:
        unit, n = str(chip.get("unit") or ""), chip.get("n")
        if unit.startswith("seats"):      # "seats", and "seats warming" while cold
            out["seats"] = n
        elif unit == "in flight":
            out["in_flight"] = n
    if census.get("error"):
        out["state"], out["error"] = "unreadable", census["error"]
    elif out["seats"] is None:
        out["state"] = "counting"
    return out


def _fabric_registry() -> dict[str, Any]:
    """The OTHER register called "seats": the fabric's address book and its mail.

    ``atlas_bridge.snapshot()`` replays the whole event log and re-verifies the graph
    projection — measured at 1355ms on this box, against 0.5ms for ``drift_token()``.
    A page that refreshes every 20s cannot pay that per fetch, so the census is banked
    against the drift token that produced it and the replay runs off-request in a
    thread. Same shape and same reason as the nav chip's census.

    Cold serves ``state="counting"``, never zeroes. An unread register rendered as 0 is
    precisely the reassurance-shaped absence this panel was added to remove.
    """
    try:
        from laplace.representation import atlas_bridge as _ab
        token = _ab.drift_token()
        stamp = (token["cursor"], token["head_record_digest"])
    except Exception as e:  # noqa: BLE001 - loud, never silent
        return {"state": "unreadable", "error": f"{type(e).__name__}: {e}",
                "source": "laplace.representation.atlas_bridge.drift_token()",
                "nav_chip": _nav_chip_counts()}

    def _recount() -> None:
        try:
            snap = _ab.snapshot()
            view = snap["provider"]
            by_status: dict[str, int] = {}
            for m in (view.get("messages") or {}).values():
                key = str(m.get("status") or "unknown")
                by_status[key] = by_status.get(key, 0) + 1
            seats = [{"id": sid, "role": (row or {}).get("role"),
                      "status": (row or {}).get("status")}
                     for sid, row in sorted((view.get("seats") or {}).items())]
            result = {
                "stamp": stamp,
                "seats": seats,
                "seat_count": len(seats),
                "by_status": by_status,
                "in_flight": sum(by_status.get(s, 0) for s in IN_FLIGHT_STATUSES),
                "store_root": snap.get("store_root"),
            }
            with _FABRIC_LOCK:
                _FABRIC_CACHE.update(result)
                _FABRIC_CACHE.pop("error", None)
        except Exception as e:  # noqa: BLE001
            with _FABRIC_LOCK:
                _FABRIC_CACHE["error"] = f"{type(e).__name__}: {e}"
        finally:
            with _FABRIC_LOCK:
                _FABRIC_CACHE["counting"] = False

    start = False
    with _FABRIC_LOCK:
        if _FABRIC_CACHE.get("stamp") != stamp and not _FABRIC_CACHE.get("counting"):
            _FABRIC_CACHE["counting"] = True
            start = True
        cached = dict(_FABRIC_CACHE)
    if start:
        threading.Thread(target=_recount, name="seats-surface-fabric",
                         daemon=True).start()

    chip = _nav_chip_counts()
    out: dict[str, Any] = {
        "source": "laplace.representation.atlas_bridge.snapshot() — the fabric event log, replayed",
        "store_root": cached.get("store_root"),
        "nav_chip": chip,
        "error": cached.get("error"),
        "chip_agrees": None,
    }
    if "seat_count" not in cached:
        out["state"] = "unreadable" if cached.get("error") else "counting"
        return out
    at = cached.get("stamp", ("?",))[0]
    out.update({
        "state": "unreadable" if cached.get("error") else "measured",
        "seats": cached["seats"],
        "seat_count": cached["seat_count"],
        "in_flight": cached["in_flight"],
        "by_status": cached["by_status"],
        "measured_at_cursor": at,
        "fabric_now_at_cursor": stamp[0],
        "moving": at != stamp[0] or bool(cached.get("counting")),
    })
    # Only a comparison of two SETTLED counts means anything. While either side is
    # recounting the fabric has moved under one of them, and a difference is the clock,
    # not a fault — so it stays None rather than renders a false alarm.
    if (chip.get("state") == "measured" and chip.get("seats") is not None
            and not out["moving"]):
        out["chip_agrees"] = (chip.get("seats") == out["seat_count"]
                              and chip.get("in_flight") == out["in_flight"])
    return out


def _payload(root: Path) -> dict[str, Any]:
    from laplace.engine import wake

    body: dict[str, Any] = {
        "rendered_at": datetime.now(timezone.utc).isoformat(),
        "row_sources": {
            "seats": "contract/seats.jsonl (the charter roll — seats founded by hand)",
            "fabric": "the conceptric store via laplace.representation.atlas_bridge.snapshot() — the fabric "
                      "address book and its mail; THIS is the register the nav chip counts",
            "sessions": "~/.claude/sessions/*.json (THE id authority) + transcript mtimes + the socket dir",
            "asks": "corpus_friction/work_orders.jsonl (open ASK-* rows)",
            "account": "python3 scripts/wake.py --account (capped projection, same code path)",
            "campaign": "corpus_friction/campaign.jsonl (banked gate verdicts, age-stamped; re-run --campaign to refresh)",
        },
        "seats": _seat_rows(root),
        "fabric": _fabric_registry(),
        "sessions": _sessions_authority(),
        "pending_asks": _pending_asks(root),
    }
    try:
        body["account"] = wake.account_capped(root)
    except Exception as e:  # noqa: BLE001
        body["account"] = {"error": f"{type(e).__name__}: {e}"}
    try:
        body["campaign"] = wake.campaign(root, run_gates=False)
    except Exception as e:  # noqa: BLE001
        body["campaign"] = {"error": f"{type(e).__name__}: {e}"}
    return body


def handle(path: str, query: dict[str, Any], method: str, body: bytes):
    """The scanner-dispatch door. ``GET /seats/data`` only; everything else is None
    (the bare /seats page is the scanner's, served from seats_surface.html)."""
    if method == "GET" and path == "/seats/data":
        payload = json.dumps(_payload(_repo_root())).encode("utf-8")
        return 200, _JSON, payload
    return None
