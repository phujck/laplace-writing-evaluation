"""W5.1 — THE RUN PANEL: WATCH is pure file reads.

``GET /storyboard/run?corpus=`` derives a corpus's current/most-recent round's LIVE
state ENTIRELY from the run's own artifacts on disk — no orchestrator, no subprocess,
no daemon. Polling it DURING a live run *is* watching it (each artifact a round writes
advances ``last_mtime``; ``phase`` climbs the harnessed ladder as evidence lands).

The contract these tests fail-close on (the stage's FAIL-CLOSED list, verbatim):
  * a fabricated mid-round set (mech_r1 present, detect_post absent) derives the honest
    IN-FLIGHT phase — never a finished state, never a fabricated one;
  * completed rounds (the crank's REAL on-disk evidence) derive their FINAL state;
  * round evidence genuinely absent => ``not-yet-travelled`` (F9); a project the release
    machine never touched => ``never-run``; the two are DISTINCT;
  * the GET is PURE (zero writes, zero subprocess — the W1.2 purity idiom);
  * the payload is BOUNDED (≤16KB, shed LOUDLY beyond);
  * paths are repo-relative; 400/404 fail-close.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.manuscript import storyboard as sb

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# fixture builders — a manuscript dir with a fabricated harnessed round.
# ---------------------------------------------------------------------------

def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")


def _mech(md: Path, n: int, *, date: str = "2026-07-14T00:00:00Z",
          hard: dict | None = None) -> None:
    _write(md / "rounds" / "harnessed" / f"mech_r{n}.json",
           {"date": date, "contract": {"hard": hard or {"artefact_integrity": True},
                                       "soft": {"prose": True}}})


def _detect_post(md: Path, n: int, open_findings: int) -> None:
    _write(md / "rounds" / "harnessed" / f"detect_post_r{n}.json",
           {"open_findings_n": open_findings})


# ---------------------------------------------------------------------------
# FAIL-CLOSED #1 — a fabricated mid-round derives the honest IN-FLIGHT phase.
# ---------------------------------------------------------------------------

def test_mid_round_mech_only_is_in_flight_detecting(tmp_path: Path) -> None:
    md = tmp_path / "proj" / "manuscript"
    md.mkdir(parents=True)
    _mech(md, 1)                                   # mech present, detect_post ABSENT

    out = sb.run_panel(md, tmp_path)
    assert out["phase"] == "detecting", out["phase"]   # honest in-flight, NOT finished
    assert out["in_flight"] is True
    assert out["never_run"] is False
    assert out["current_round"] == 1
    assert out["rounds_so_far"] == 1
    assert {a["kind"] for a in out["artifacts"]} == {"mech"}


def test_ladder_climbs_with_the_evidence(tmp_path: Path) -> None:
    """Each rung is proved only by its own artifact; the highest present wins."""
    md = tmp_path / "proj" / "manuscript"
    md.mkdir(parents=True)
    _mech(md, 2)
    assert sb.run_panel(md, tmp_path)["phase"] == "detecting"

    (md / "rounds" / "incumbent_r2").mkdir(parents=True)          # Fix ran
    assert sb.run_panel(md, tmp_path)["phase"] == "fixing"

    _detect_post(md, 2, 7)                                        # Verify banked
    p = sb.run_panel(md, tmp_path)
    assert p["phase"] == "verified"
    assert p["open_findings"] == 7 and p["in_flight"] is True

    _write(md / "rounds" / "lock_r2.json", {"eligible": True})    # Lock
    assert sb.run_panel(md, tmp_path)["phase"] == "locked"

    _write(md / "release" / "finalize.json", {"slug": "p", "title": "P"})  # Finalize
    fin = sb.run_panel(md, tmp_path)
    assert fin["phase"] == "finalized" and fin["in_flight"] is False        # terminal


# ---------------------------------------------------------------------------
# FAIL-CLOSED #2 — the crank's REAL on-disk evidence derives its FINAL state.
# ---------------------------------------------------------------------------

def test_real_eigenengine_finalize_record_present_and_pdf_recovered() -> None:
    """DISK TRUTH (recovery landed 2026-07-22 — WO-20260715-002324 drained).

    eigenengine's ``release/`` carries a ``finalize.json`` (the finalize step ran and
    recorded on 2026-07-14) whose ``pdf_path`` names ``eigenengine-2026-07-14-r1.pdf``. That
    PDF was originally dropped by a wholesale ``*.pdf`` line in the manuscript ``.gitignore``
    (absent in every fresh container); the hole is fixed and the artifact RE-MINTED through
    the release finalize recipe (slug jobname + metadata pretex — the reproduced ``title_check``
    is byte-identical to the recorded one, revision 1), so it now commits and travels. The
    honest reading is threefold: the harnessed ladder reached the finalize RUNG (finalize.json
    on disk ⇒ ``phase == 'finalized'`` — a process step, not a release verdict); the minted-PDF
    artefact is now PRESENT (``'minted_pdf' in kinds`` — the recovered blob, not a fabricated
    'present'); and the ONE authoritative position is STILL ``UNDER_CONVERGENCE`` — recovering
    the artifact does NOT advance the release STATE MACHINE (release/state.json is untouched;
    the PDF bytes were the loss, not a missed transition)."""
    out = sb.run_payload("eigenengine")
    assert out is not None
    assert out["corpus"] == "eigenengine"
    # the harnessed-ladder rung (finalize.json on disk) — a process step, NOT the verdict
    assert out["phase"] == "finalized"
    assert out["in_flight"] is False
    assert out["never_run"] is False
    assert out["rounds_so_far"] >= 1
    assert out["current_round"] >= 1
    # THE ONE TRUTH the run tray renders — the release position the dashboard/cockpit read,
    # joined server-side so no 'finalized' verdict can stand beside it (defect #1). The
    # recovery does not touch the state machine, so this stays UNDER_CONVERGENCE.
    assert out["position"] == "UNDER_CONVERGENCE"
    kinds = {a["kind"] for a in out["artifacts"]}
    assert "finalize" in kinds              # the finalize RECORD is on disk...
    assert "minted_pdf" in kinds            # ...and the PDF it names is now RECOVERED on disk
    for a in out["artifacts"]:
        assert not a["path"].startswith("/")     # repo-relative on the real tree


def test_real_subset_sum_joins_harnessed_and_judge_rounds() -> None:
    """The two-root repair: subset-sum-itqde's target (``whitepaper/``) holds the
    release state + the harnessed ladder, its manuscript dir holds the OLDER
    ``judge_rounds`` layout — both real evidence. release_state now reads
    TARGET-FIRST (agreeing with the pipeline ladder's ``registry.project_states``,
    which has always read UNDER_CONVERGENCE here — the pre-repair NEVER_RUN was the
    manuscript-only misread this closes), and the judge_rounds evidence JOINS the
    harnessed evidence rather than being dropped: both layouts, both round families,
    visible together."""
    out = sb.run_payload("subset-sum-itqde")
    assert out is not None
    assert out["release_state"] == "UNDER_CONVERGENCE"   # target-first (was NEVER_RUN)
    assert out["layout"] == "harnessed+judge_rounds"      # BOTH layouts, joined
    assert out["never_run"] is False
    # rounds_so_far folds BOTH round families in (2 harnessed + 2 judge_rounds)
    assert out["rounds_so_far"] >= 4
    kinds = {a["kind"] for a in out["artifacts"]}
    # the harnessed (target-side) ladder is primary evidence...
    assert {"mech", "detect_post"} <= kinds
    # ...and the manuscript-side judge round rides ALONGSIDE it, never dropped.
    assert "judge_round" in kinds
    for a in out["artifacts"]:
        assert not a["path"].startswith("/")     # repo-relative on the real tree


# ---------------------------------------------------------------------------
# FAIL-CLOSED #3 — absent evidence: not-yet-travelled vs never-run, DISTINCT.
# ---------------------------------------------------------------------------

def test_never_run_says_so(tmp_path: Path) -> None:
    md = tmp_path / "proj" / "manuscript"
    md.mkdir(parents=True)                        # nothing: no state, no rounds
    out = sb.run_panel(md, tmp_path)
    assert out["phase"] == "never-run"
    assert out["never_run"] is True
    assert out["in_flight"] is False
    assert out["current_round"] is None
    assert out["artifacts"] == [] and out["last_mtime"] is None


def test_run_posture_but_no_rounds_is_not_yet_travelled(tmp_path: Path) -> None:
    """F9: a release-touched project whose round records are absent from the tree reads
    not-yet-travelled — never a spinner, never a fabricated phase, never never-run."""
    md = tmp_path / "proj" / "manuscript"
    md.mkdir(parents=True)
    _write(md / "release" / "state.json",
           {"state": "UNDER_CONVERGENCE", "history": []})   # the machine touched it
    out = sb.run_panel(md, tmp_path)
    assert out["phase"] == "not-yet-travelled"
    assert out["never_run"] is False
    assert out["in_flight"] is False
    assert out["release_state"] == "UNDER_CONVERGENCE"


def test_empty_rounds_dir_is_not_yet_travelled(tmp_path: Path) -> None:
    """A rounds/ shell present but holding no round records (a remote committed the
    dir; the evidence has not travelled) also reads not-yet-travelled, not never-run."""
    md = tmp_path / "proj" / "manuscript"
    (md / "rounds" / "harnessed").mkdir(parents=True)   # dir exists, no mech/detect
    out = sb.run_panel(md, tmp_path)
    assert out["phase"] == "not-yet-travelled"
    assert out["never_run"] is False


# ---------------------------------------------------------------------------
# FAIL-CLOSED #4 — the GET is PURE (zero writes, zero subprocess).
# ---------------------------------------------------------------------------

def _tree(md: Path) -> set[Path]:
    return {p for p in md.rglob("*")}


def test_pure_no_writes(tmp_path: Path) -> None:
    md = tmp_path / "proj" / "manuscript"
    md.mkdir(parents=True)
    _mech(md, 1)
    _detect_post(md, 1, 3)
    before = _tree(md)
    sb.run_panel(md, tmp_path)
    sb.run_panel(md, tmp_path)                    # idempotent: polling never mutates
    assert _tree(md) == before                    # not one byte written


def test_pure_no_subprocess(monkeypatch) -> None:
    import subprocess
    def _boom(*a, **k):
        raise AssertionError("run panel spawned a subprocess — not a pure read")
    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    out = sb.run_payload("eigenengine")
    assert out is not None and out["phase"] == "finalized"


# ---------------------------------------------------------------------------
# FAIL-CLOSED #5 — the payload is BOUNDED (≤16KB), shed LOUDLY beyond.
# ---------------------------------------------------------------------------

def test_payload_bound_enforced_loudly(tmp_path: Path) -> None:
    md = tmp_path / "proj" / "manuscript"
    md.mkdir(parents=True)
    # a round whose mech carries a huge panel set — the widest gate field.
    panel = [{"label": f"R{i}-a-long-enough-panel-label-to-blow-the-budget-{i:04d}",
              "clean": bool(i % 2)} for i in range(4000)]
    _write(md / "rounds" / "harnessed" / "mech_r1.json",
           {"date": "2026-07-14T00:00:00Z",
            "contract": {"hard": {"artefact_integrity": True}, "soft": {}},
            "panel": panel})
    _detect_post(md, 1, 5)

    out = sb.run_panel(md, tmp_path)
    size = len(json.dumps(out, ensure_ascii=False).encode("utf-8"))
    assert size <= sb._RUN_MAX_BYTES, size       # ENFORCED, not asserted
    assert out["truncated"] is True
    assert out["gates_omitted"] > 0              # the shed was LOUD
    # the honest core survives the shed:
    assert out["phase"] == "verified"
    assert out["open_findings"] == 5
    assert out["gates"]["hard"]["artefact_integrity"]["value"] is True


# ---------------------------------------------------------------------------
# THE ENDPOINT — corpus resolution + fail-closed status.
# ---------------------------------------------------------------------------

def test_endpoint_requires_corpus() -> None:
    st, _, body = sb.handle("/storyboard/run", {}, "GET", b"")
    assert st == 400
    assert b"corpus" in body


def test_endpoint_unknown_corpus_404() -> None:
    st, _, _ = sb.handle("/storyboard/run", {"corpus": "no-such-project"}, "GET", b"")
    assert st == 404
    # a path-shaped name never resolves (traversal fence)
    st2, _, _ = sb.handle("/storyboard/run", {"corpus": "../etc"}, "GET", b"")
    assert st2 == 404


def test_endpoint_real_corpus_derives() -> None:
    st, ctype, body = sb.handle("/storyboard/run", {"corpus": "eigenengine"}, "GET", b"")
    assert st == 200
    assert "application/json" in ctype
    out = json.loads(body)
    assert out["corpus"] == "eigenengine"
    assert out["phase"] == "finalized"
