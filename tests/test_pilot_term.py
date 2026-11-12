"""The pilot clock's fast-forward test - the expiry path proven, never asserted."""

from datetime import datetime, timedelta, timezone

import pytest

from laplace.engine import pilot_term


def test_stamp_and_active_within_term(tmp_path):
    rec = pilot_term.stamp(tmp_path, "2026-08-14T00:00:00+00:00")
    assert rec["term_days"] == 365
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    status = pilot_term.check(tmp_path, now=now)
    assert status["stamped"] and status["active"]
    assert status["days_remaining"] > 200
    # full function while active: the gate passes silently
    assert pilot_term.require_active(tmp_path, now=now)["active"]


def test_fast_forward_past_expiry(tmp_path):
    pilot_term.stamp(tmp_path, "2026-08-14T00:00:00+00:00")
    later = datetime(2027, 8, 15, tzinfo=timezone.utc)
    status = pilot_term.check(tmp_path, now=later)
    assert status["stamped"] and not status["active"]
    assert status["days_remaining"] == 0
    # graceful: the message states the term, the dates, and the next step - plainly
    assert "2027-08-14" in status["message"]
    assert "durable-license" in status["message"]
    with pytest.raises(pilot_term.PilotExpired):
        pilot_term.require_active(tmp_path, now=later)


def test_term_runs_from_data_creation_not_delivery(tmp_path):
    # data created 300 days before delivery: the clock still runs from creation
    pilot_term.stamp(tmp_path, "2025-10-01T00:00:00+00:00")
    now = datetime(2026, 10, 2, tzinfo=timezone.utc)
    assert not pilot_term.check(tmp_path, now=now)["active"]


def test_unstamped_never_invents_a_term(tmp_path):
    status = pilot_term.check(tmp_path)
    assert not status["stamped"] and not status["active"]
    # and the gate does NOT refuse an unstamped (non-pilot) deliverable
    pilot_term.require_active(tmp_path)


def test_expiry_boundary_is_exact(tmp_path):
    pilot_term.stamp(tmp_path, "2026-08-14T12:00:00+00:00", term_days=10)
    just_before = datetime(2026, 8, 24, 11, 59, tzinfo=timezone.utc)
    just_after = datetime(2026, 8, 24, 12, 1, tzinfo=timezone.utc)
    assert pilot_term.check(tmp_path, now=just_before)["active"]
    assert not pilot_term.check(tmp_path, now=just_after)["active"]
