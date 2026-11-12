"""W5.2 — THE LAUNCH SPLIT (Fork 6, RULED): the run panel's launch side split by
COST CLASS.

Two disjoint rosters behind ONE door (``POST /storyboard/run/launch``):

  LOCAL-SAFE {storyboard-rebuild, dispatch-compile, projection-compile,
  nodemap-rebuild} — cheap, deterministic, ZERO model calls. Each fires its REAL
  executor exactly once through the EXISTING door, behind an EXPLICIT gesture
  (POST + ``by``; arm-to-fire where it overwrites a primary artifact). The compile
  action rides the W4.4 recompile MUTEX, so a double-fire can never double-compile.

  MODEL-HEAVY {harnessed-round, re-projection, dream} — the button banks EXACTLY
  ONE ``kind="work-order"`` record and spawns NOTHING (no subprocess, no agent);
  the server never spends tokens (the storyboard dispatch-manifest law).

The FAIL-CLOSED contract these tests hold (the stage's list, verbatim):
  * each local-safe door fires its real executor exactly once (mutex where
    applicable), and REFUSES an unattributed launch (no ``by``) → 422;
  * a model-heavy gesture writes EXACTLY a work-order record and spawns NOTHING —
    proved at the PROCESS level (subprocess + thread both boom);
  * the work-order record shape is honest (what, why, requested_by, ts, cost class);
  * arm-to-fire: an arm-required local action without ``armed:true`` fires nothing.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from laplace.manuscript import storyboard as sb

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# helpers — drive the door both directly (run_launch) and through the route (handle).
# ---------------------------------------------------------------------------

def _route(payload: dict) -> tuple[int, dict]:
    st, _ctype, raw = sb.handle("/storyboard/run/launch", {}, "POST",
                                json.dumps(payload).encode("utf-8"))
    return st, json.loads(raw)


class _Spy:
    """A one-call executor spy: records args, returns a canned dict."""
    def __init__(self, ret: dict) -> None:
        self.calls: list[tuple] = []
        self._ret = ret

    def __call__(self, *a, **k):
        self.calls.append((a, k))
        return dict(self._ret)


# ---------------------------------------------------------------------------
# FAIL-CLOSED #1 — each LOCAL-SAFE door fires its real executor EXACTLY ONCE.
# ---------------------------------------------------------------------------

def test_storyboard_rebuild_fires_rebuild_once(monkeypatch) -> None:
    spy = _Spy({"ok": True, "mode": "expensive"})
    monkeypatch.setattr(sb, "rebuild", spy)
    monkeypatch.setattr(sb, "_load_plan", lambda c: (Path("p.json"), {"meta": {}}))
    st, obj = sb.run_launch("c", "storyboard-rebuild", "gerard", armed=True)
    assert st == 200 and obj["ok"] is True and obj["cost_class"] == "local-safe"
    assert len(spy.calls) == 1                       # the real executor, exactly once
    assert spy.calls[0][0][0] == "c"


def test_dispatch_compile_fires_dispatch_report_once(monkeypatch) -> None:
    spy = _Spy({"ok": True, "n_items": 3})
    monkeypatch.setattr(sb, "dispatch_report", spy)
    monkeypatch.setattr(sb, "_load_plan", lambda c: (Path("p.json"), {"meta": {}}))
    # dispatch-compile is NOT arm-required (it regenerates derived manifests).
    st, obj = sb.run_launch("c", "dispatch-compile", "gerard")
    assert st == 200 and obj["ok"] is True and obj["cost_class"] == "local-safe"
    assert len(spy.calls) == 1


def test_projection_compile_delegates_to_the_w44_mutex_door(monkeypatch) -> None:
    spy = _Spy({})                                   # returns (status, row) — see below
    def _recompile(file_param, corpus, by):
        spy.calls.append(((file_param, corpus, by), {}))
        return 200, {"status": "started", "coalesced": False}
    import laplace.manuscript.projection_viewer as pv
    monkeypatch.setattr(pv, "recompile", _recompile)
    monkeypatch.setattr(sb, "_load_plan",
                        lambda c: (Path("p.json"), {"meta": {"target_dir": "eigenengine/x"}}))
    st, obj = sb.run_launch("c", "projection-compile", "gerard", armed=True)
    assert st == 200 and obj["cost_class"] == "local-safe"
    assert len(spy.calls) == 1
    # the real W4.4 door is the executor; the compile-root is the plan's target/main.tex
    (fp, corpus, by), _ = spy.calls[0]
    assert fp == "eigenengine/x/main.tex" and corpus == "c" and by == "gerard"


def test_nodemap_rebuild_fires_review_surface_rebuild_once(monkeypatch) -> None:
    spy = _Spy({"ok": True, "coverage": 1.0})
    import laplace.manuscript.review_surface as rs
    monkeypatch.setattr(rs, "rebuild", spy)
    monkeypatch.setattr(sb, "_load_plan", lambda c: (Path("p.json"), {"meta": {}}))

    class _Proj:
        manuscript_dir = "eigenengine/manuscript"
        def path(self, rel, root=None):
            return Path("/tmp") / rel
    from laplace.pipeline import registry
    monkeypatch.setattr(registry, "resolve", lambda c, **kwargs: _Proj())
    st, obj = sb.run_launch("c", "nodemap-rebuild", "gerard", armed=True)
    assert st == 200 and obj["ok"] is True and obj["cost_class"] == "local-safe"
    assert len(spy.calls) == 1


# ---------------------------------------------------------------------------
# FAIL-CLOSED #1b — an UNATTRIBUTED launch is refused 422, and fires NOTHING.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action", ["storyboard-rebuild", "dispatch-compile",
                                    "projection-compile", "nodemap-rebuild",
                                    "harnessed-round", "re-projection", "dream"])
def test_unattributed_launch_refused_422_and_fires_nothing(monkeypatch, action) -> None:
    for name in ("rebuild", "dispatch_report", "bank_work_order"):
        monkeypatch.setattr(sb, name, _Spy({"ok": True}))
    import laplace.manuscript.projection_viewer as pv
    import laplace.manuscript.review_surface as rs
    pv_spy, rs_spy = _Spy((200, {})), _Spy({"ok": True})
    monkeypatch.setattr(pv, "recompile", pv_spy)
    monkeypatch.setattr(rs, "rebuild", rs_spy)
    monkeypatch.setattr(sb, "_load_plan", lambda c: (Path("p.json"), {"meta": {}}))

    st, obj = sb.run_launch("c", action, "", armed=True)     # NO by
    assert st == 422 and obj["ok"] is False and "by required" in obj["error"]
    # not one executor fired
    assert sb.rebuild.calls == [] and sb.dispatch_report.calls == []
    assert sb.bank_work_order.calls == [] and pv_spy.calls == [] and rs_spy.calls == []


# ---------------------------------------------------------------------------
# FAIL-CLOSED #1c — ARM-TO-FIRE: an arm-required action without armed fires nothing.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action", ["storyboard-rebuild", "projection-compile",
                                    "nodemap-rebuild"])
def test_arm_required_without_armed_previews_and_fires_nothing(monkeypatch, action) -> None:
    spy = _Spy({"ok": True})
    monkeypatch.setattr(sb, "rebuild", spy)
    import laplace.manuscript.projection_viewer as pv
    import laplace.manuscript.review_surface as rs
    pv_spy, rs_spy = _Spy((200, {})), _Spy({"ok": True})
    monkeypatch.setattr(pv, "recompile", pv_spy)
    monkeypatch.setattr(rs, "rebuild", rs_spy)
    monkeypatch.setattr(sb, "_load_plan", lambda c: (Path("p.json"), {"meta": {}}))

    st, obj = sb.run_launch("c", action, "gerard", armed=False)     # not armed
    assert st == 200 and obj["ok"] is False and obj["needs_arming"] is True
    assert obj["armed"] is False and obj["what"]
    assert spy.calls == [] and pv_spy.calls == [] and rs_spy.calls == []


def test_dispatch_compile_is_not_arm_required(monkeypatch) -> None:
    """dispatch-compile regenerates derived manifests (idempotent) — it fires without
    arming, so it is deliberately NOT in the arm-required set."""
    spy = _Spy({"ok": True})
    monkeypatch.setattr(sb, "dispatch_report", spy)
    monkeypatch.setattr(sb, "_load_plan", lambda c: (Path("p.json"), {"meta": {}}))
    st, obj = sb.run_launch("c", "dispatch-compile", "gerard", armed=False)
    assert st == 200 and obj["ok"] is True and len(spy.calls) == 1


# ---------------------------------------------------------------------------
# FAIL-CLOSED #2 — MODEL-HEAVY banks EXACTLY one work-order and SPAWNS NOTHING.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action", ["harnessed-round", "re-projection", "dream"])
def test_model_heavy_banks_one_work_order_and_spawns_nothing(monkeypatch, tmp_path,
                                                             action) -> None:
    import laplace.web.scanner as scanner
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)

    # PROVE-AT-THE-PROCESS-LEVEL: no subprocess, no thread may be born on this path.
    import subprocess, threading
    def _boom(*a, **k):
        raise AssertionError("a model-heavy launch spawned a process/thread — "
                             "the server must only bank a work-order")
    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    monkeypatch.setattr(threading, "Thread", _boom)

    st, obj = sb.run_launch("eigenengine", action, "gerard")
    assert st == 200 and obj["ok"] is True
    assert obj["cost_class"] == "model-heavy" and obj["spawned"] is False

    store = tmp_path / "corpus_friction" / "work_orders.jsonl"
    lines = [l for l in store.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1                           # EXACTLY one record, nothing else
    rec = json.loads(lines[0])
    assert rec == obj["work_order"]


# ---------------------------------------------------------------------------
# FAIL-CLOSED #3 — the work-order record shape is HONEST.
# ---------------------------------------------------------------------------

def test_work_order_shape_is_honest(monkeypatch, tmp_path) -> None:
    import laplace.web.scanner as scanner
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)
    st, obj = sb.run_launch("eigenengine", "harnessed-round", "gerard")
    rec = obj["work_order"]
    # what / why / requested_by / ts / cost class — the honest five, plus provenance.
    assert rec["kind"] == "work-order"
    assert rec["action"] == "harnessed-round"
    assert rec["corpus"] == "eigenengine"
    assert rec["what"] and "harnessed" in rec["what"]
    assert rec["why"] and "eigenengine" in rec["why"]
    assert rec["requested_by"] == "gerard"
    assert rec["cost_class"] == "model-heavy"
    assert rec["status"] == "open"
    assert rec["id"].startswith("WO-")
    time.strptime(rec["ts"][:19], "%Y-%m-%dT%H:%M:%S")   # a real ISO timestamp


# ---------------------------------------------------------------------------
# FAIL-CLOSED #2b — the MUTEX where applicable: a double projection-compile
# coalesces to EXACTLY ONE latexmk (the W4.4 recompile mutex, driven through the
# launch door with a fake slow binary — the same proof W4.4 makes for its own door).
# ---------------------------------------------------------------------------

_FAKE_LATEXMK_OK = r"""
echo call >> "$LMK_COUNTER"
sleep "${LMK_SLEEP:-0}"
job=main
for a in "$@"; do case "$a" in *.tex) job=$(basename "$a" .tex);; esac; done
: > "$job.pdf"
sleep 0.05
: > "$job.synctex.gz"
exit 0
"""


def _calls(counter: Path) -> int:
    try:
        return len([l for l in counter.read_text().splitlines() if l.strip()])
    except OSError:
        return 0


def test_projection_compile_double_fire_coalesces_to_one_latexmk(monkeypatch,
                                                                 tmp_path) -> None:
    import laplace.web.scanner as scanner
    import laplace.manuscript.projection_viewer as pv
    repo = tmp_path / "repo"
    (repo / "proj").mkdir(parents=True)
    (repo / "proj" / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}hi\\end{document}\n", encoding="utf-8")
    monkeypatch.setattr(scanner, "_repo_root", lambda: repo)
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("LMK_COUNTER", str(tmp_path / "calls.log"))
    monkeypatch.setenv("LMK_SLEEP", "1.5")                    # overlap the 2nd fire
    fake = tmp_path / "latexmk-slow"
    fake.write_text("#!/bin/sh\n" + _FAKE_LATEXMK_OK, encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("LAPLACE_LATEXMK_BIN", str(fake))
    monkeypatch.setattr(sb, "_load_plan",
                        lambda c: (repo / "p.json", {"meta": {"target_dir": "proj"}}))

    st1, r1 = sb.run_launch("c", "projection-compile", "gerard", armed=True)
    st2, r2 = sb.run_launch("c", "projection-compile", "gerard", armed=True)
    assert st1 == 200 and r1["status"] == "started" and r1["coalesced"] is False
    assert st2 == 200 and r2["status"] == "running" and r2["coalesced"] is True

    counter = tmp_path / "calls.log"
    deadline = time.time() + 20
    while _calls(counter) < 1 and time.time() < deadline:
        time.sleep(0.1)
    time.sleep(0.5)                                           # let any stray 2nd land
    assert _calls(counter) == 1, (
        f"latexmk ran {_calls(counter)}× — the mutex did not coalesce the double-fire")


# ---------------------------------------------------------------------------
# ROUTING + the pure-read roster.
# ---------------------------------------------------------------------------

def test_get_launch_roster_is_a_pure_read(monkeypatch) -> None:
    def _boom(*a, **k):
        raise AssertionError("GET /storyboard/run/launch executed something — "
                             "the roster is a pure read")
    monkeypatch.setattr(sb, "rebuild", _boom)
    monkeypatch.setattr(sb, "bank_work_order", _boom)
    st, _ct, raw = sb.handle("/storyboard/run/launch", {}, "GET", b"")
    out = json.loads(raw)
    assert st == 200
    la = {r["action"] for r in out["local_safe"]}
    assert la == set(sb._LOCAL_SAFE)
    mh = {r["action"] for r in out["model_heavy"]}
    assert mh == set(sb._MODEL_HEAVY)
    assert all(r["spends_tokens"] is False for r in out["model_heavy"])
    # arm-to-fire flagged exactly on the arm-required actions
    armed = {r["action"] for r in out["local_safe"] if r["arm_to_fire"]}
    assert armed == sb._ARM_REQUIRED


def test_route_requires_corpus_and_action(monkeypatch) -> None:
    st, obj = _route({"action": "dream", "by": "gerard"})
    assert st == 400 and "corpus" in obj["error"]
    st, obj = _route({"corpus": "eigenengine", "by": "gerard"})
    assert st == 400 and "action" in obj["error"]


def test_route_bad_json_400() -> None:
    st, _ct, raw = sb.handle("/storyboard/run/launch", {}, "POST", b"{not json")
    assert st == 400


def test_unknown_action_400(monkeypatch) -> None:
    st, obj = sb.run_launch("eigenengine", "delete-everything", "gerard")
    assert st == 400 and obj["ok"] is False
    assert "unknown launch action" in obj["error"]
    assert set(obj["local_safe"]) == set(sb._LOCAL_SAFE)


def test_model_heavy_through_the_route_banks_and_returns(monkeypatch, tmp_path) -> None:
    import laplace.web.scanner as scanner
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)
    st, obj = _route({"corpus": "eigenengine", "action": "dream", "by": "gerard"})
    assert st == 200 and obj["ok"] is True and obj["work_order"]["kind"] == "work-order"
    store = tmp_path / "corpus_friction" / "work_orders.jsonl"
    assert len([l for l in store.read_text().splitlines() if l.strip()]) == 1


# ---------------------------------------------------------------------------
# THE CONJUGATE WAVE (SCOUT_2026-07-17) — the night-organ launches. The three
# model-heavy fires bank a work-order; the two local-safe fires call their real
# organ executor once. No dead buttons; unattributed launches fire nothing.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action", ["detector-run", "citation-direction-run",
                                    "figure-materialize"])
def test_conjugate_model_heavy_banks_a_work_order(monkeypatch, tmp_path, action) -> None:
    import laplace.web.scanner as scanner
    import subprocess, threading
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)

    def _boom(*a, **k):
        raise AssertionError(f"{action} spawned a process/thread — it must only bank")
    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    monkeypatch.setattr(threading, "Thread", _boom)

    st, obj = sb.run_launch("paper_falqon", action, "gerard")
    assert st == 200 and obj["ok"] is True
    assert obj["cost_class"] == "model-heavy" and obj["spawned"] is False
    rec = obj["work_order"]
    assert rec["action"] == action and rec["kind"] == "work-order" and rec["what"]
    store = tmp_path / "corpus_friction" / "work_orders.jsonl"
    assert len([l for l in store.read_text().splitlines() if l.strip()]) == 1


def test_bibliography_run_is_arm_required_and_fires_the_stage(tmp_path, monkeypatch) -> None:
    """bibliography-run overwrites main.tex (\\bibliography) + the manifest, so it arms
    first; armed, it fires bibliography_stage.run(apply=True) exactly once."""
    from laplace.pipeline import registry
    from laplace.pipeline import bibliography_stage as bib

    class _Res:
        cited = ["a"]; resolved = ["a"]; dangling = []; wired = True
        intents = []; probe = {"renders": True}
    spy = _Spy(None)

    def _run(md, **k):
        spy.calls.append((md, k)); return _Res()
    monkeypatch.setattr(bib, "run", _run)

    class _Proj:
        manuscript_dir = "m"
        def path(self, *a): return tmp_path/"m"
    monkeypatch.setattr(registry, "resolve", lambda c: _Proj())
    monkeypatch.setattr(sb, "_load_plan", lambda c: (tmp_path/"p.json", {"meta": {"target_dir":"m"}}))
    monkeypatch.setattr(sb, "_repo_root", lambda:tmp_path)
    # This dispatch/arming test receives a positive fence result. Actual selected
    # and derived targets are exercised through the owner in source-effect repairs.
    monkeypatch.setattr(sb, "_derived_target_refusal", lambda *args, **kwargs:None)

    st, obj = sb.run_launch("c", "bibliography-run", "gerard", armed=False)
    assert st == 200 and obj.get("needs_arming") is True and spy.calls == []

    st, obj = sb.run_launch("c", "bibliography-run", "gerard", armed=True)
    assert st == 200 and obj["ok"] is True and len(spy.calls) == 1
    assert spy.calls[0][1].get("apply") is True
    assert obj["renders"] is True and obj["resolved"] == 1


def test_structural_conformance_run_is_arm_required_and_fires_the_read_leg_once(monkeypatch) -> None:
    """structural-conformance-run OVERWRITES the dispatch manifest (write=True) — a
    primary artifact — so it ARMS first (the roster's own law); armed, it fires
    structural_conformance.build_conformance_manifest exactly once and reports the
    patch count. Unarmed, it previews and writes NOTHING (no empty-patch overwrite on
    a bare click)."""
    from laplace.pipeline import structural_conformance as sc
    spy = _Spy({"count": 4, "conformant": [1, 2], "unscored": [],
                "stores": {"section_architecture": "served: k=3"},
                "manifest_path": "/tmp/x.json"})
    monkeypatch.setattr(sc, "build_conformance_manifest", spy)
    monkeypatch.setattr(sb, "_load_plan", lambda c: (Path("p.json"), {"meta": {}}))

    st, obj = sb.run_launch("c", "structural-conformance-run", "gerard", armed=False)
    assert st == 200 and obj.get("needs_arming") is True and spy.calls == []

    st, obj = sb.run_launch("c", "structural-conformance-run", "gerard", armed=True)
    assert st == 200 and obj["ok"] is True and len(spy.calls) == 1
    assert obj["patch_count"] == 4 and obj["conformant"] == 2


@pytest.mark.parametrize("action", ["detector-run", "citation-direction-run",
                                    "figure-materialize", "bibliography-run",
                                    "structural-conformance-run"])
def test_conjugate_launch_unattributed_refused_422(monkeypatch, action) -> None:
    """Every conjugate-wave fire refuses an unattributed launch (no ``by``) → 422 and
    fires/banks nothing (the fail-closed contract extends to the new organs)."""
    import laplace.web.scanner as scanner

    def _boom(*a, **k):
        raise AssertionError("an unattributed launch banked/fired something")
    monkeypatch.setattr(sb, "bank_work_order", _boom)
    st, obj = sb.run_launch("paper_falqon", action, "", armed=True)
    assert st == 422 and obj["ok"] is False and "by required" in obj["error"]


# ---------------------------------------------------------------------------
# BLOCKER-A closed (2026-07-19, C01): the per-run dials profile at the door —
# allowlist-fenced at launch, threaded to the dials-consuming executors, carried
# on a model-heavy work-order for the worker session.
# ---------------------------------------------------------------------------

def test_launch_refuses_an_unlawful_profile(monkeypatch) -> None:
    """An unallowlisted / traversal profile refuses 422 at the door — never a
    silent v1 fallback."""
    st, obj = sb.run_launch("c", "dispatch-compile", "gerard",
                            profile="../evil.yaml")
    assert st == 422 and "profile refused" in obj["error"]


def test_launch_threads_the_profile_into_dispatch_compile(monkeypatch) -> None:
    spy = _Spy({"ok": True})
    monkeypatch.setattr(sb, "dispatch_report", spy)
    monkeypatch.setattr(sb, "_load_plan", lambda c: (Path("p.json"), {"meta": {}}))
    st, obj = sb.run_launch("c", "dispatch-compile", "gerard",
                            profile="dials-v2.yaml")
    assert st == 200
    assert spy.calls == [(("c",), {"dials_profile": "dials-v2.yaml"})]


def test_model_heavy_work_order_carries_the_profile(monkeypatch) -> None:
    """The banked WO carries dials_profile so the worker session runs with the
    launcher's dials, not a hand-edit."""
    spy = _Spy({"id": "WO-test", "status": "open"})
    monkeypatch.setattr(sb, "bank_work_order", spy)
    action = sorted(sb._MODEL_HEAVY)[0]
    st, obj = sb.run_launch("c", action, "gerard", profile="dials-v2.yaml")
    assert st == 200 and obj["spawned"] is False
    assert spy.calls[0][1] == {"profile": "dials-v2.yaml"}


def test_route_accepts_the_profile_field(monkeypatch) -> None:
    spy = _Spy({"ok": True})
    monkeypatch.setattr(sb, "dispatch_report", spy)
    monkeypatch.setattr(sb, "_load_plan", lambda c: (Path("p.json"), {"meta": {}}))
    st, obj = _route({"corpus": "c", "action": "dispatch-compile",
                      "by": "gerard", "profile": "dials-v2.yaml"})
    assert st == 200
    assert spy.calls[0][1]["dials_profile"] == "dials-v2.yaml"


def test_profile_none_is_byte_identical_default(monkeypatch) -> None:
    """No profile = the exact pre-thread call shape (the inert default)."""
    spy = _Spy({"ok": True})
    monkeypatch.setattr(sb, "dispatch_report", spy)
    monkeypatch.setattr(sb, "_load_plan", lambda c: (Path("p.json"), {"meta": {}}))
    sb.run_launch("c", "dispatch-compile", "gerard")
    assert spy.calls == [(("c",), {"dials_profile": None})]
