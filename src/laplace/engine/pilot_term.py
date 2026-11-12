"""pilot_term.py - the pilot's honest clock.

His said-aloud commitment on the 2026-08-14 call (Andrew + Jack + Gerard): a pilot
deliverable is timestamped from DATA CREATION and stops working one year on, and what
follows is a durable-license conversation. A spoken promise without a mechanism is a
contact-law debt (WO-20260814-pilot-timestamp-mechanism), so the mechanism exists before
any client byte does.

Three properties, each load-bearing:
- The term is stamped IN the deliverable (``PILOT_TERM.json``) from the data-creation
  timestamp, never from delivery or install time.
- Expiry is graceful and plain: full function until the date, then a typed refusal whose
  message states the term and the conversation that follows. No degradation before the
  date, no silent failure after it, no dark patterns.
- The clock is injectable, so the expiry path is TESTED by fast-forward rather than
  asserted (tests/test_pilot_term.py).

Wiring the serving door is pilot-delivery work and gates with Rungs 3+8+11; this module
is the mechanism those gates require to exist first. The rotation-killswitch idea
(PENDING-20260820-rotation-killswitch) is a separate, W1-gated concept and is not built
here.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TERM_FILE = "PILOT_TERM.json"
DEFAULT_TERM_DAYS = 365

_EXPIRED_MESSAGE = (
    "This pilot's term ended on {expires}. The engine was timestamped from your data's "
    "creation ({created}) and licensed for {days} days, as agreed at delivery - it stops "
    "serving here by that agreement's own clock, whole and un-degraded until the date. "
    "For continued service, the durable-license conversation is the next step."
)


class PilotExpired(RuntimeError):
    """Raised at a serving door once the stamped term has passed."""


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def stamp(deliverable_dir: Path | str, data_creation: str,
          term_days: int = DEFAULT_TERM_DAYS) -> dict[str, Any]:
    """Write the term file into a deliverable. ``data_creation`` is ISO-8601 - the
    CUSTOMER's data-creation time, the clock the commitment runs from."""
    created = _parse(data_creation)
    expires = created + timedelta(days=term_days)
    record = {
        "data_creation": created.isoformat(),
        "expires_at": expires.isoformat(),
        "term_days": term_days,
        "statement": "Timestamped from data creation; serves in full until expiry, "
                     "then stops with the message stating why.",
    }
    out = Path(deliverable_dir) / TERM_FILE
    out.write_text(json.dumps(record, indent=1), encoding="utf-8")
    return record


def check(deliverable_dir: Path | str, now: datetime | None = None) -> dict[str, Any]:
    """The term's status. Unstamped deliverables report ``stamped: False`` - the
    mechanism never invents a term it was not given."""
    path = Path(deliverable_dir) / TERM_FILE
    if not path.is_file():
        return {"stamped": False, "active": False,
                "message": "no pilot term stamped - not a pilot deliverable"}
    rec = json.loads(path.read_text(encoding="utf-8"))
    now = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)
    expires = _parse(rec["expires_at"])
    active = now < expires
    out = {"stamped": True, "active": active, "expires_at": rec["expires_at"],
           "data_creation": rec["data_creation"],
           "days_remaining": max(0, (expires - now).days)}
    if not active:
        out["message"] = _EXPIRED_MESSAGE.format(
            expires=expires.date().isoformat(),
            created=_parse(rec["data_creation"]).date().isoformat(),
            days=rec["term_days"])
    return out


def require_active(deliverable_dir: Path | str, now: datetime | None = None) -> dict[str, Any]:
    """The serving-door gate: full function while active, a typed refusal after."""
    status = check(deliverable_dir, now=now)
    if status["stamped"] and not status["active"]:
        raise PilotExpired(status["message"])
    return status
