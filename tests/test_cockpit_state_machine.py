"""ACT 4 (E4b) — the release state machine gets its honest driver.

The board renders FROM ``release.STATES`` but nothing ever drove the machine, so
falqon reads ``NEVER_RUN`` under a minted r2. :func:`candidate_lock.record_lock` is
the lock organ's stage-completion call: a lock-eligible round advances the machine
to ``CANDIDATE_LOCKED`` (through ``UNDER_CONVERGENCE``). Proven here ENTIRELY on a
tmp-path fixture manuscript dir — NEVER a live transition on falqon or any real
project (the hard law: an authored/live ledger is never touched by a test).
"""
from __future__ import annotations

from pathlib import Path

from laplace.pipeline import candidate_lock, release


def _eligible_evidence() -> tuple[dict, dict, bool]:
    """A round that IS lock-eligible: hard dims pass, compile clean, round complete
    (the exact shape ``candidate_lock.lock_eligible`` — and ``release.transition``'s
    own CANDIDATE_LOCKED precondition — consume)."""
    round_eval = {"hard_failing": False}
    compile_report = {"ok": True, "errors": 0, "undefined": 0}
    return round_eval, compile_report, True


def test_record_lock_drives_the_machine_to_candidate_locked(tmp_path: Path):
    md = tmp_path / "manuscript"
    md.mkdir()
    # a fresh manuscript dir has no release sidecar → NEVER-touched machine.
    assert not (md / "release" / "state.json").is_file()
    assert release.current_state(md) == "STAGED"       # the absent-sidecar default

    res = candidate_lock.record_lock(md, *_eligible_evidence(), by="gerard")

    assert res["eligible"] is True
    assert res["advanced"] is True
    assert res["state"] == "CANDIDATE_LOCKED"
    # the DRIVEN OUTCOME: the sidecar now exists and the machine really moved.
    assert (md / "release" / "state.json").is_file()
    assert release.current_state(md) == "CANDIDATE_LOCKED"
    # the machine passed THROUGH UNDER_CONVERGENCE on the way (ensure_at_least), so the
    # history is honest, not a teleport.
    hist = release._load_state(md).get("history", [])
    tos = [h.get("to") for h in hist]
    assert "UNDER_CONVERGENCE" in tos and "CANDIDATE_LOCKED" in tos


def test_record_lock_transitions_nothing_off_the_eligible_path(tmp_path: Path):
    md = tmp_path / "manuscript"
    md.mkdir()
    # an INELIGIBLE round (a hard dim fails) must drive NOTHING — no sidecar written.
    res = candidate_lock.record_lock(
        md, {"hard_failing": True}, {"ok": True, "errors": 0}, True, by="gerard")
    assert res["eligible"] is False
    assert res["advanced"] is False
    assert res["reasons"]                               # names the failing gate
    assert not (md / "release" / "state.json").is_file()
    assert release.current_state(md) == "STAGED"


def test_record_lock_is_idempotent_when_already_locked(tmp_path: Path):
    md = tmp_path / "manuscript"
    md.mkdir()
    ev = _eligible_evidence()
    first = candidate_lock.record_lock(md, *ev, by="gerard")
    assert first["advanced"] is True
    # a second eligible call is a monotone no-op — the machine never slides backward
    # and never double-appends a lock transition.
    second = candidate_lock.record_lock(md, *ev, by="gerard")
    assert second["eligible"] is True
    assert second["advanced"] is False
    assert second["state"] == "CANDIDATE_LOCKED"
