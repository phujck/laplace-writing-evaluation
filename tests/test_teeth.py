"""tests/test_teeth.py — THE AGING TEETH, exercised (W-TEETH, PV-20260722T165050Z).

His verbatim law: loops left open at context time fossilize; an aged ask is a destroyed
decision; "carried, named" must stop being free. These tests hold the teeth honest:

  - the age gate FIRES on a stale, undeferred author-askable row (the defect);
  - a dated defer with an owner (the note idiom) FLIPS it to deferred (carried, named);
  - an EXPIRED defer does not (no infinite defer — re-touching never resets the clock);
  - the class gates are real (author 3d vs machine 14d);
  - his-direction covenant promises are EXEMPT but counted;
  - a fork's `trigger` is its native condition-defer;
  - the close FAIL wiring is armed: `aging_teeth` is FAIL_ELIGIBLE, so its FAIL moves the
    exit code, while a stray FAIL from any non-eligible check is still refused (_verdict).
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import close_checklist as cc  # noqa: E402
import ledger_age_audit as la  # noqa: E402

TODAY = date(2026, 7, 22)


@pytest.fixture(autouse=True)
def _established_empty_authorities(tmp_path: Path) -> None:
    """The age account's three stores exist even when one fixture has no rows there."""
    for rel in (la.WORK_ORDERS, la.PROMISES, la.FORKS):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                    encoding="utf-8")


def _wo(id_, ts, requested_by, **extra) -> dict:
    return {"id": id_, "kind": "work-order", "action": "do-a-thing",
            "ts": ts, "requested_by": requested_by, "status": "open", **extra}


# --------------------------------------------------------------------------- the age gate fires
def test_stale_author_row_fails(tmp_path):
    """A gerard-requested work-order 10 days old (gate 3d), no defer, is FAILING."""
    _write_jsonl(tmp_path / la.WORK_ORDERS,
                 [_wo("WO-stale-author", "2026-07-12T00:00:00", "gerard (a real ask)")])
    rep = la.audit(tmp_path, TODAY)
    failing_ids = {r.id for r in rep.failing}
    assert "WO-stale-author" in failing_ids
    row = next(r for r in rep.rows if r.id == "WO-stale-author")
    assert row.cls == "author" and row.gate == 3 and row.quiet_age == 10


def test_fresh_machine_row_passes(tmp_path):
    """An eigen-minted work-order 10 days old is under the 14d machine gate — not failing."""
    _write_jsonl(tmp_path / la.WORK_ORDERS,
                 [_wo("WO-fresh-machine", "2026-07-12T00:00:00", "eigen (internal)")])
    rep = la.audit(tmp_path, TODAY)
    assert not rep.failing
    row = next(r for r in rep.rows if r.id == "WO-fresh-machine")
    assert row.cls == "machine" and row.gate == 14


def test_stale_machine_row_fails(tmp_path):
    """An eigen work-order 20 days old crosses even the loose 14d machine gate."""
    _write_jsonl(tmp_path / la.WORK_ORDERS,
                 [_wo("WO-stale-machine", "2026-07-02T00:00:00", "eigen (internal)")])
    rep = la.audit(tmp_path, TODAY)
    assert "WO-stale-machine" in {r.id for r in rep.failing}


# --------------------------------------------------------------------------- the defer flips it
def test_dated_defer_note_passes(tmp_path):
    """A stale author row + a later defer NOTE ROW (defer_until >= today, deferred_by set)
    is carried-and-named: deferred, not failing."""
    _write_jsonl(tmp_path / la.WORK_ORDERS, [
        _wo("WO-deferred", "2026-07-12T00:00:00", "gerard (an ask)"),
        {"record": "defer", "target": "WO-deferred", "defer_until": "2026-08-01",
         "deferred_by": "Eigen (a real owner)", "reason": "parked on X"},
    ])
    rep = la.audit(tmp_path, TODAY)
    assert not rep.failing
    assert "WO-deferred" in {r.id for r in rep.deferred}


def test_inline_defer_field_passes(tmp_path):
    """The defer may also ride inline on the row (defer_until + deferred_by)."""
    _write_jsonl(tmp_path / la.WORK_ORDERS, [
        _wo("WO-inline", "2026-07-12T00:00:00", "gerard (an ask)",
            defer_until="2026-08-01", deferred_by="Eigen"),
    ])
    rep = la.audit(tmp_path, TODAY)
    assert not rep.failing


def test_expired_defer_still_fails(tmp_path):
    """A defer whose date has PASSED is stale — the row ages again (no infinite defer)."""
    _write_jsonl(tmp_path / la.WORK_ORDERS, [
        _wo("WO-expired", "2026-07-12T00:00:00", "gerard (an ask)"),
        {"record": "defer", "target": "WO-expired", "defer_until": "2026-07-20",
         "deferred_by": "Eigen"},
    ])
    rep = la.audit(tmp_path, TODAY)
    assert "WO-expired" in {r.id for r in rep.failing}


def test_later_expired_defer_supersedes_earlier_future_defer(tmp_path):
    """Disposition is last-in-file, not furthest-date. A later lapse cannot be hidden
    behind an older future date."""
    _write_jsonl(tmp_path / la.WORK_ORDERS, [
        _wo("WO-last-defer", "2026-07-01T00:00:00", "gerard (an ask)"),
        {"record": "defer", "target": "WO-last-defer", "defer_until": "2026-08-01",
         "deferred_by": "Eigen", "id": "DEFER-future-first"},
        {"record": "defer", "target": "WO-last-defer", "defer_until": "2026-07-20",
         "deferred_by": "Eigen", "id": "DEFER-lapsed-last"},
    ])
    rep = la.audit(tmp_path, TODAY)
    assert "WO-last-defer" in {r.id for r in rep.failing}
    assert "WO-last-defer" not in {r.id for r in rep.deferred}


def test_later_future_defer_supersedes_earlier_expired_defer(tmp_path):
    _write_jsonl(tmp_path / la.WORK_ORDERS, [
        _wo("WO-last-defer", "2026-07-01T00:00:00", "gerard (an ask)"),
        {"record": "defer", "target": "WO-last-defer", "defer_until": "2026-07-20",
         "deferred_by": "Eigen", "id": "DEFER-lapsed-first"},
        {"record": "defer", "target": "WO-last-defer", "defer_until": "2026-08-01",
         "deferred_by": "Eigen", "id": "DEFER-future-last"},
    ])
    rep = la.audit(tmp_path, TODAY)
    assert "WO-last-defer" in {r.id for r in rep.deferred}
    assert "WO-last-defer" not in {r.id for r in rep.failing}


def test_malformed_latest_defer_masks_older_date_and_is_an_integrity_fail(tmp_path):
    """A typo is UNKNOWN, never an immortal defer and never permission to resurrect an
    older scheduling act. The teeth and wake therefore agree on actionable state."""
    _write_jsonl(tmp_path / la.WORK_ORDERS, [
        _wo("WO-bad-date", "2026-07-01T00:00:00", "gerard (an ask)"),
        {"record": "defer", "target": "WO-bad-date", "defer_until": "2026-08-01",
         "deferred_by": "Eigen", "id": "DEFER-valid-old"},
        {"record": "defer", "target": "WO-bad-date", "defer_until": "2026-13-45",
         "deferred_by": "Eigen", "id": "DEFER-invalid-new"},
    ])
    rep = la.audit(tmp_path, TODAY)
    assert "WO-bad-date" in {r.id for r in rep.failing}
    assert "WO-bad-date" not in {r.id for r in rep.deferred}
    assert rep.failed
    assert any(r["defect"] == "invalid-defer-until" for r in rep.residuals)


def test_named_condition_defer_agrees_with_the_account(tmp_path):
    _write_jsonl(tmp_path / la.WORK_ORDERS, [
        _wo("WO-condition", "2026-07-01T00:00:00", "gerard (an ask)"),
        {"record": "defer", "target": "WO-condition", "defer_until": "condition",
         "trigger": "when the sample arrives", "deferred_by": "Eigen",
         "id": "DEFER-condition"},
    ])
    rep = la.audit(tmp_path, TODAY)
    assert "WO-condition" in {r.id for r in rep.deferred}
    assert "WO-condition" not in {r.id for r in rep.failing}
    assert not rep.residuals


def test_defer_without_owner_does_not_count(tmp_path):
    """A defer_until with NO deferred_by is not a valid defer — carrying must be OWNED."""
    _write_jsonl(tmp_path / la.WORK_ORDERS, [
        _wo("WO-ownerless", "2026-07-12T00:00:00", "gerard (an ask)",
            defer_until="2026-08-01"),
    ])
    rep = la.audit(tmp_path, TODAY)
    assert "WO-ownerless" in {r.id for r in rep.failing}


# ------------------------------------------------------- the retirement join (2026-08-25)
def test_evidence_resolution_retires_through_consumes(tmp_path):
    """A resolution naming the order through ``consumes`` — with ``supersedes`` left an
    EMPTY STRING, the 2026-08-20 jubilee writer's exact shape — RETIRES it. Reading
    ``supersedes`` alone hid 21 live closures and FAILed this gate on every one."""
    _write_jsonl(tmp_path / la.WORK_ORDERS, [
        _wo("WO-consumed", "2026-07-02T00:00:00", "eigen (internal)"),
        {"record": "resolution", "id": "RES-consumed", "target": "WO-consumed",
         "supersedes": "", "consumes": "WO-consumed", "status": "absorbed",
         "evidence": ["evidence/somewhere/README.md"]},
    ])
    rep = la.audit(tmp_path, TODAY)
    assert not rep.failing
    assert "WO-consumed" not in {r.id for r in rep.rows}


def test_evidenceless_consumes_retires_nothing(tmp_path):
    """The EVIDENCE requirement is unchanged by the widening: a ``consumes`` resolution
    with no evidence refs retires nothing, so its order still ages."""
    _write_jsonl(tmp_path / la.WORK_ORDERS, [
        _wo("WO-bare", "2026-07-02T00:00:00", "eigen (internal)"),
        {"record": "resolution", "id": "RES-bare", "consumes": "WO-bare",
         "status": "merged-retired"},
    ])
    rep = la.audit(tmp_path, TODAY)
    assert "WO-bare" in {r.id for r in rep.failing}


def test_bare_target_does_not_retire_a_held_open_row(tmp_path):
    """Bare ``target`` is NOT joined on. A resolution that deliberately HOLDS a row open
    carries ``target`` + evidence (RES-20260820-blind-surfacing-bench-both-halves-executed,
    status "open") — joining on it would retire a row its own adjudication still owes."""
    _write_jsonl(tmp_path / la.WORK_ORDERS, [
        _wo("WO-held", "2026-07-02T00:00:00", "eigen (internal)"),
        {"record": "resolution", "id": "RES-held", "target": "WO-held", "status": "open",
         "evidence": ["evidence/executed-not-consumed.json"]},
    ])
    rep = la.audit(tmp_path, TODAY)
    assert "WO-held" in {r.id for r in rep.failing}


# --------------------------------------------------------------------------- promises: exempt + gated
def test_promise_restated_later_reads_the_last_line(tmp_path):
    """LAST WRITE WINS PER ID. A promise re-stated later in the file with
    ``status: "delivered"`` is delivered — reading every line independently failed
    PRM-20260803-hampson-plan on its own superseded ``status: "open"`` mint line."""
    _write_jsonl(tmp_path / la.PROMISES, [
        {"id": "PRM-restated", "date": "2026-07-01", "status": "open", "owner": "Eigen",
         "ask": "a thing owed"},
        {"id": "PRM-restated", "date": "2026-07-01", "status": "delivered",
         "owner": "Eigen", "ask": "a thing owed", "evidence": ["the banked artefact"]},
    ])
    rep = la.audit(tmp_path, TODAY)
    assert not rep.failing
    assert "PRM-restated" not in {r.id for r in rep.rows}


def test_promise_reopened_by_a_later_line_still_ages(tmp_path):
    """Last-wins runs BOTH ways, and THE RE-MINT BUYS NO FRESH CLOCK. The two lines carry
    DISTINCT dates — origin 2026-07-01 (21d, past the 3d author gate), re-mint 2026-07-21
    (1d, comfortably inside it). The reopened promise is open again (disposition
    last-wins) and ages from its FIRST-seen origin (the clock is first-wins): 21d, FAILING.
    Reading ``date`` off the collapsed latest row read 1d and let a re-mint of an open id
    launder its age — exactly the gaming the module docstring forbids."""
    _write_jsonl(tmp_path / la.PROMISES, [
        {"id": "PRM-reopened", "date": "2026-07-01", "status": "delivered",
         "owner": "Eigen", "ask": "a thing owed"},
        {"id": "PRM-reopened", "date": "2026-07-21", "status": "open", "owner": "Eigen",
         "ask": "a thing owed, again"},
    ])
    rep = la.audit(tmp_path, TODAY)
    row = next(r for r in rep.rows if r.id == "PRM-reopened")
    assert row.origin == "2026-07-01"
    assert row.quiet_age == 21
    assert "PRM-reopened" in {r.id for r in rep.failing}


def test_remint_cannot_launder_age_by_dropping_the_date(tmp_path):
    """The other half of the same hole: a re-mint that DROPS the ``date`` field must not
    demote an aged row to an undateable warn. The first-seen origin still stands."""
    _write_jsonl(tmp_path / la.PROMISES, [
        {"id": "PRM-dateless-remint", "date": "2026-07-01", "status": "open",
         "owner": "Eigen", "ask": "a thing owed"},
        {"id": "PRM-dateless-remint", "status": "open", "owner": "Eigen",
         "ask": "a thing owed, restated with no date"},
    ])
    rep = la.audit(tmp_path, TODAY)
    row = next(r for r in rep.rows if r.id == "PRM-dateless-remint")
    assert row.origin == "2026-07-01" and row.quiet_age == 21
    assert not rep.undateable
    assert "PRM-dateless-remint" in {r.id for r in rep.failing}


def test_his_direction_promise_exempt(tmp_path):
    """A direction:his covenant promise (40d) is EXEMPT (carried-not-collected) — counted,
    never failing."""
    _write_jsonl(tmp_path / la.PROMISES, [
        {"id": "PRM-his", "date": "2026-06-12", "status": "open", "direction": "his",
         "owner": "him", "ask": "the house"},
    ])
    rep = la.audit(tmp_path, TODAY)
    assert not rep.failing
    assert "PRM-his" in {r.id for r in rep.exempt}


def test_eigen_promise_gated(tmp_path):
    """An Eigen-promise to him (no direction), 10 days old, crosses the 3d author gate."""
    _write_jsonl(tmp_path / la.PROMISES, [
        {"id": "PRM-eigen", "date": "2026-07-12", "status": "open", "owner": "Eigen",
         "ask": "a thing owed"},
    ])
    rep = la.audit(tmp_path, TODAY)
    assert "PRM-eigen" in {r.id for r in rep.failing}


# --------------------------------------------------------------------------- forks: trigger = defer
def test_fork_with_trigger_is_condition_deferred(tmp_path):
    """A live fork (🔴) carrying a trigger is condition-deferred (the ⚪ idiom) — not failing,
    however old."""
    _write_jsonl(tmp_path / la.FORKS, [
        {"id": "F-trig", "kind": "open-stack-fork", "stratum": 1, "status": "🔴",
         "opened": "2026-06-01", "title": "a fork", "trigger": "when X lands"},
    ])
    rep = la.audit(tmp_path, TODAY)
    assert not rep.failing
    assert "F-trig" in {r.id for r in rep.deferred}


def test_fork_without_trigger_fails(tmp_path):
    """A live fork with NO trigger and no defer, past the machine gate, is failing."""
    _write_jsonl(tmp_path / la.FORKS, [
        {"id": "F-bare", "kind": "open-stack-fork", "stratum": 1, "status": "🔴",
         "opened": "2026-06-01", "title": "a fork", "trigger": ""},
    ])
    rep = la.audit(tmp_path, TODAY)
    assert "F-bare" in {r.id for r in rep.failing}


def test_undateable_fork_is_a_warn_not_a_fail(tmp_path):
    """A fork with no `opened` date cannot be aged — reported as a warn, never a fail."""
    _write_jsonl(tmp_path / la.FORKS, [
        {"id": "F-nodate", "kind": "open-stack-fork", "stratum": 1, "status": "🔴",
         "title": "a fork", "trigger": ""},
    ])
    rep = la.audit(tmp_path, TODAY)
    assert not rep.failing
    assert "F-nodate" in {r.id for r in rep.undateable}


# --------------------------------------------------------------------------- the CLI exit code
def test_cli_exits_1_on_a_failing_row(tmp_path, capsys):
    """The audit CLI returns rc=1 (and a VERDICT=FAIL sentinel) when a row is failing —
    the signal close_checklist.check_aging_teeth reads."""
    _write_jsonl(tmp_path / la.WORK_ORDERS,
                 [_wo("WO-cli", "2026-07-12T00:00:00", "gerard (an ask)")])
    rc = la.main(["--repo", str(tmp_path), "--today", "2026-07-22"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "VERDICT=FAIL" in out.splitlines()[-1]


def test_cli_exits_0_when_clean(tmp_path, capsys):
    _write_jsonl(tmp_path / la.WORK_ORDERS,
                 [_wo("WO-ok", "2026-07-21T00:00:00", "eigen (internal)")])
    rc = la.main(["--repo", str(tmp_path), "--today", "2026-07-22"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "VERDICT=PASS" in out.splitlines()[-1]


def test_malformed_ledger_is_an_integrity_fail_not_a_smaller_pass(tmp_path, capsys):
    """A poisoned control row may be the disposition that changes the census."""
    _write_jsonl(tmp_path / la.WORK_ORDERS,
                 [_wo("WO-fresh", "2026-07-21T00:00:00", "eigen (internal)")])
    with (tmp_path / la.WORK_ORDERS).open("a", encoding="utf-8") as fh:
        fh.write('{"record":"resolution","consumes":\n')
    rep = la.audit(tmp_path, TODAY)
    assert not rep.failing and rep.failed
    assert rep.residuals[0]["store"] == la.WORK_ORDERS
    assert rep.residuals[0]["line"] == 2

    rc = la.main(["--repo", str(tmp_path), "--today", "2026-07-22"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "[integrity]" in out
    assert "VERDICT=FAIL failing=0 residuals=1" in out.splitlines()[-1]


def test_missing_authoritative_ledger_is_an_integrity_fail(tmp_path):
    (tmp_path / la.WORK_ORDERS).unlink()
    rep = la.audit(tmp_path, TODAY)
    assert rep.failed
    assert any(r["defect"] == "store-unreadable"
               and r["store"] == la.WORK_ORDERS for r in rep.residuals)


# --------------------------------------------------------------------------- the close FAIL wiring
def test_aging_teeth_is_fail_eligible():
    """The tooth has teeth: aging_teeth is in FAIL_ELIGIBLE, so its FAIL moves the close's
    exit code (unlike an advisory WARN check)."""
    assert "aging_teeth" in cc.FAIL_ELIGIBLE


def test_verdict_admits_aging_teeth_fail():
    """A Check('aging_teeth', 'FAIL') passes _verdict's eligibility assertion and gates the
    exit code (ok=False), because aging_teeth is registered FAIL_ELIGIBLE."""
    checks = [cc.Check("aging_teeth", "FAIL", "a stale row"),
              cc.Check("git_state", "PASS", "clean")]
    ok, fails, _warns = cc._verdict(checks)
    assert ok is False
    assert [c.name for c in fails] == ["aging_teeth"]


def test_verdict_refuses_a_stray_fail():
    """A FAIL from a check NOT in FAIL_ELIGIBLE is refused — only trace-artifact/ledger gates
    may move the exit code (the guard against an advisory check silently starting to gate)."""
    checks = [cc.Check("effect_meter", "FAIL", "should never FAIL")]
    with pytest.raises(AssertionError, match="FAIL_ELIGIBLE"):
        cc._verdict(checks)


def test_landing_sweep_is_advisory():
    """The landing sweep is WARN-tier by design (a name-match is a heuristic, not proof) —
    it must NOT be FAIL_ELIGIBLE."""
    assert "landing_sweep" not in cc.FAIL_ELIGIBLE
