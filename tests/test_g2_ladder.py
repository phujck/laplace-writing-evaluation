"""G2 — the growth ladder + the birth bridge (ARMING_2026-07-22_the-growth-stage.md).

The sidecar state machine conjugate to release, with the safe write discipline:
forward-only + unknown-state refused; every bar enforced (mechanical facts checked;
STOCKED fails closed naming the un-built gate; GRADED refuses without a resolving
STANDS verdict and accepts with one banked through superego.bank_verdict; READY
refuses judged-only and is author-gated; REGOALED author-gated, from STOCKED onward);
the sidecar write is atomic + locked (a concurrent race has exactly one winner and the
file never tears); the birth bridge (a scaffold through dashboard's door carries
SEEDED); the plain pre-ladder null for a released paper; and the crank shows SEEDED
through all three read paths in-process (sidecar, dashboard row, /corpus/meta).
"""
from __future__ import annotations

import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from laplace.engine import superego
from laplace.pipeline import growth

REPO = Path(__file__).resolve().parents[1]


def _tmp_root(tmp_path: Path) -> Path:
    (tmp_path / "corpus_friction").mkdir(exist_ok=True)
    return tmp_path


def _bank(root: Path, name: str, to_state: str, *, verdict="STANDS",
          judge="judge-a", builder="builder-b", extra_claim="") -> str:
    """Bank a growth-tagged verdict through the ONE door and return its id."""
    rec = {
        "station": "wave-close",
        "claim": growth.growth_claim_tag(name, to_state) + " — " + (extra_claim or "the wave stands"),
        "verdict": verdict, "judge": judge, "builder": builder,
        "questions": [{"question": "was the object's principal question served?",
                       "answer": "yes — the lift round-trips, essences not slop"
                                 if verdict == "STANDS" else "no — it does not lift",
                       "served": "yes" if verdict == "STANDS" else "no"}],
        "defects": [] if verdict == "STANDS" else [{"severity": "fatal",
                    "what": "does not lift", "evidence": "round-trip drift"}],
        "refs": [],
    }
    return superego.bank_verdict(root, rec)["id"]


# ============================================================ forward-only + unknown

def test_unknown_state_refused(tmp_path):
    root = _tmp_root(tmp_path)
    growth.seed(root, "p")
    with pytest.raises(ValueError, match="unknown target growth state"):
        growth.transition(root, "p", "NOT_A_STATE")


def test_transition_on_unseeded_project_refused(tmp_path):
    root = _tmp_root(tmp_path)
    with pytest.raises(ValueError, match="not on the growth ladder"):
        growth.transition(root, "never-seeded", "WIRED")


def test_forward_only_no_backward_slide(tmp_path, monkeypatch):
    root = _tmp_root(tmp_path)
    growth.seed(root, "p")
    monkeypatch.setattr("laplace.pipeline.verify.check_connectivity",
                        lambda name, root=None: {"pass": True, "orphans": []})
    growth.transition(root, "p", "WIRED")
    # WIRED -> SEEDED (backward) and WIRED -> WIRED (same rung) both refuse.
    with pytest.raises(ValueError, match="forward-only"):
        growth.transition(root, "p", "SEEDED")
    with pytest.raises(ValueError, match="forward-only"):
        growth.transition(root, "p", "WIRED")


# ============================================================ STOCKED fails closed

def test_stocked_fails_closed_naming_the_gate(tmp_path):
    root = _tmp_root(tmp_path)
    growth.seed(root, "p")
    with pytest.raises(ValueError, match="element-leg floors land in G3/G4"):
        growth.transition(root, "p", "STOCKED")
    # the rung did not move — a fail-closed refusal never advances silently.
    assert growth.current_growth_state(root, "p") == "SEEDED"


# ============================================================ WIRED — real machinery

def test_wired_refuses_orphans_on_the_real_crank():
    # the bar consumes the REAL verify.check_connectivity: the crank scaffold has
    # spine-unreachable orphans, so the WIRED bar-check raises naming them (no sidecar
    # write — the bar reader is called directly).
    with pytest.raises(ValueError, match="not connected"):
        growth._bar_wired(REPO, "crank-2026-07-15", {})


def test_wired_passes_when_connected(tmp_path, monkeypatch):
    root = _tmp_root(tmp_path)
    growth.seed(root, "p")
    monkeypatch.setattr("laplace.pipeline.verify.check_connectivity",
                        lambda name, root=None: {"pass": True, "orphans": []})
    side = growth.transition(root, "p", "WIRED")
    assert side["state"] == "WIRED" and side["bar"] == "mechanical"


def test_wired_gap_named_or_exempt(tmp_path, monkeypatch):
    root = _tmp_root(tmp_path)
    growth.seed(root, "p")
    monkeypatch.setattr("laplace.pipeline.verify.check_connectivity",
                        lambda name, root=None: {"pass": True, "orphans": []})
    # a surviving (non-exempt) provenance gap must be named in evidence.
    monkeypatch.setattr("laplace.research.corpus_ingest.resolve_corpus",
                        lambda r, n: Path(r) / "tex")
    monkeypatch.setattr("laplace.research.corpus_ingest.corpus_network",
                        lambda troot, repo_root=None, name=None: {"nodes": {}, "edge_index": {}})
    monkeypatch.setattr("laplace.research.corpus_ingest.gaps", lambda net: ["res:unproven-1"])
    with pytest.raises(ValueError, match="provenance gap"):
        growth.transition(root, "p", "WIRED")
    # naming the survivor lets the rung flip.
    side = growth.transition(root, "p", "WIRED", evidence={"named_gaps": ["res:unproven-1"]})
    assert side["state"] == "WIRED"


# ============================================================ GRADED — judged

def _to_wired(root, name, monkeypatch):
    growth.seed(root, name)
    monkeypatch.setattr("laplace.pipeline.verify.check_connectivity",
                        lambda n, root=None: {"pass": True, "orphans": []})
    growth.transition(root, name, "WIRED")


def test_graded_refuses_without_verdict(tmp_path, monkeypatch):
    root = _tmp_root(tmp_path)
    _to_wired(root, "p", monkeypatch)
    with pytest.raises(ValueError, match="no verdict_id"):
        growth.transition(root, "p", "GRADED")


def test_graded_refuses_a_refuted_verdict(tmp_path, monkeypatch):
    root = _tmp_root(tmp_path)
    _to_wired(root, "p", monkeypatch)
    vid = _bank(root, "p", "GRADED", verdict="REFUTED")
    with pytest.raises(ValueError, match="not STANDS"):
        growth.transition(root, "p", "GRADED", evidence={"verdict_id": vid})


def test_graded_refuses_a_verdict_for_another_transition(tmp_path, monkeypatch):
    root = _tmp_root(tmp_path)
    _to_wired(root, "p", monkeypatch)
    # a STANDS verdict tagged for READY does not identify the GRADED transition.
    vid = _bank(root, "p", "READY")
    with pytest.raises(ValueError, match="does not identify this transition"):
        growth.transition(root, "p", "GRADED", evidence={"verdict_id": vid})


def test_graded_accepts_a_resolving_stands_verdict(tmp_path, monkeypatch):
    root = _tmp_root(tmp_path)
    _to_wired(root, "p", monkeypatch)
    vid = _bank(root, "p", "GRADED")
    side = growth.transition(root, "p", "GRADED", evidence={"verdict_id": vid})
    assert side["state"] == "GRADED" and side["bar"] == "judged"
    assert side["history"][-1]["evidence"]["verdict_id"] == vid


# ============================================================ READY — author

def _to_graded(root, name, monkeypatch):
    _to_wired(root, name, monkeypatch)
    vid = _bank(root, name, "GRADED")
    growth.transition(root, name, "GRADED", evidence={"verdict_id": vid})


def test_ready_refuses_judged_only(tmp_path, monkeypatch):
    root = _tmp_root(tmp_path)
    _to_graded(root, "p", monkeypatch)
    vid = _bank(root, "p", "READY")
    with pytest.raises(ValueError, match="must be an actor-guarded record"):
        growth.transition(root, "p", "READY", evidence={"verdict_id": vid})


def test_ready_refuses_a_defaulted_actor(tmp_path, monkeypatch):
    root = _tmp_root(tmp_path)
    _to_graded(root, "p", monkeypatch)
    vid = _bank(root, "p", "READY")
    with pytest.raises(ValueError, match="by .explicit actor. is required"):
        growth.transition(root, "p", "READY",
                          evidence={"verdict_id": vid, "ruling": {"by": "  ", "ref": "x"}})


def test_ready_refuses_a_non_author_actor(tmp_path, monkeypatch):
    root = _tmp_root(tmp_path)
    _to_graded(root, "p", monkeypatch)
    vid = _bank(root, "p", "READY")
    with pytest.raises(ValueError, match="is not an author actor"):
        growth.transition(root, "p", "READY",
                          evidence={"verdict_id": vid, "ruling": {"by": "impostor", "ref": "x"}})


def test_ready_accepts_verdict_plus_author_waiver(tmp_path, monkeypatch):
    root = _tmp_root(tmp_path)
    _to_graded(root, "p", monkeypatch)
    vid = _bank(root, "p", "READY")
    side = growth.transition(root, "p", "READY",
                             evidence={"verdict_id": vid,
                                       "ruling": {"by": "gerard", "ref": "waiver: the two open gaps are his to hold"}})
    assert side["state"] == "READY" and side["bar"] == "author"
    assert side["history"][-1]["evidence"]["waiver_by"] == "gerard"


# ============================================================ REGOALED — author

def test_regoal_refused_below_stocked(tmp_path):
    root = _tmp_root(tmp_path)
    growth.seed(root, "p")   # SEEDED — nothing stocked yet
    with pytest.raises(ValueError, match="nothing is stocked yet"):
        growth.regoal(root, "p", evidence={"ruling": {"by": "gerard", "verb": "REGOAL", "ref": "c"}})


def test_regoal_is_author_gated(tmp_path, monkeypatch):
    root = _tmp_root(tmp_path)
    _to_wired(root, "p", monkeypatch)
    with pytest.raises(ValueError, match="is not an author actor"):
        growth.regoal(root, "p", evidence={"ruling": {"by": "impostor", "verb": "REGOAL", "ref": "c"}})
    with pytest.raises(ValueError, match="verb must be 'REGOAL'"):
        growth.regoal(root, "p", evidence={"ruling": {"by": "gerard", "verb": "HOLD", "ref": "c"}})


def test_regoal_bumps_version_and_resumes_seeded(tmp_path, monkeypatch):
    root = _tmp_root(tmp_path)
    _to_wired(root, "p", monkeypatch)
    side = growth.regoal(root, "p",
                         evidence={"ruling": {"by": "gerard", "verb": "REGOAL", "ref": "tension-card-9"}})
    assert side["state"] == "SEEDED" and side["goal_version"] == 2
    tos = [h["to"] for h in side["history"]]
    assert "REGOALED" in tos and tos[-1] == "SEEDED"


# ============================================================ atomic + locked write

def test_concurrent_transition_has_exactly_one_winner(tmp_path, monkeypatch):
    root = _tmp_root(tmp_path)
    _to_wired(root, "race", monkeypatch)
    vid = _bank(root, "race", "GRADED")

    outcomes: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(6)

    def worker():
        barrier.wait()
        try:
            growth.transition(root, "race", "GRADED", evidence={"verdict_id": vid})
            with lock:
                outcomes.append("won")
        except ValueError:
            with lock:
                outcomes.append("lost")

    threads = [threading.Thread(target=worker) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert outcomes.count("won") == 1, f"exactly one winner, got {outcomes}"
    assert outcomes.count("lost") == 5
    # the file never tore: it parses clean and reads the winner's state.
    sidecar = root / "corpus_friction" / "race.growth.json"
    loaded = json.loads(sidecar.read_text(encoding="utf-8"))
    assert loaded["state"] == "GRADED"


# ============================================================ the birth bridge

def test_scaffold_born_through_the_dashboard_door_carries_seeded(tmp_path, monkeypatch):
    from laplace.web import dashboard
    from laplace.projects import project_creation
    # a name not in the real registry passes _validate_new; the door writes into tmp.
    name = "g2-birth-probe"
    status, payload = project_creation.create_project(name, "conceptric", root=tmp_path)
    assert status == 201 and payload["ok"]
    # the sidecar path is reported as written by the door.
    assert f"corpus_friction/{name}.growth.json" in payload["created"]
    # and the ladder reads SEEDED end-to-end through the one producer.
    gs = growth.growth_state(tmp_path, name)
    assert gs["present"] and gs["state"] == "SEEDED" and gs["goal_version"] == 1


# ============================================================ plain pre-ladder null

def test_released_project_renders_pre_ladder_not_fake_seeded():
    # paper_falqon (9 harnessed rounds, a minted PDF) has no growth sidecar and is NOT
    # retro-laddered: the read renders a plain pre-ladder null, never a fake SEEDED.
    gs = growth.growth_state(REPO, "paper_falqon")
    assert gs["present"] is False and gs["state"] is None and gs["pre_ladder"] is True
    # a project with genuinely no history reads "not yet seeded" (distinct, in the read).
    gs2 = growth.growth_state(REPO, "no-such-project-xyz")
    assert gs2["present"] is False and gs2["pre_ladder"] is False


# ============================================================ the crank, three paths

def _serve():
    from laplace.web import scanner
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def test_crank_shows_seeded_through_all_three_read_paths():
    from laplace.web import dashboard
    sidecar = REPO / "corpus_friction" / "crank-2026-07-15.growth.json"
    pre_existed = sidecar.is_file()
    try:
        growth.seed(REPO, "crank-2026-07-15")
        # PATH 1 — the sidecar, read through the one producer.
        gs = growth.growth_state(REPO, "crank-2026-07-15")
        assert gs["present"] and gs["state"] == "SEEDED"
        # PATH 2 — the dashboard data row.
        data = dashboard.dashboard_data(REPO)
        row = next(r for r in data["projects"] if r["name"] == "crank-2026-07-15")
        assert row["growth"]["state"] == "SEEDED"
        # PATH 3 — the /corpus/meta payload, over a live in-process server.
        httpd, port = _serve()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("GET", "/corpus/meta?corpus=crank-2026-07-15")
            body = conn.getresponse().read()
            conn.close()
        finally:
            httpd.shutdown()
        meta = json.loads(body)
        assert meta.get("growth", {}).get("state") == "SEEDED", meta
    finally:
        if not pre_existed and sidecar.is_file():
            sidecar.unlink()
        lock = sidecar.with_name(sidecar.name + ".lock")
        if lock.is_file():
            lock.unlink()


# ============================================================ the G2 judge's folds
def test_ladder_refuses_a_coherence_broken_forged_row(tmp_path, monkeypatch):
    # a hand-forged STANDS row the bank door would refuse (a fatal defect on a
    # STANDS) must be refused by the ladder's full-spine re-validation too
    import json as _json
    root = _tmp_root(tmp_path)
    _to_wired(root, "p", monkeypatch)
    forged = {
        "id": "SEV-FORGED", "ts": "2026-07-22T00:00:00Z",
        "station": "wave-close",
        "claim": growth.growth_claim_tag("p", "GRADED") + " — forged coherence break",
        "verdict": "STANDS", "judge": "judge-a", "builder": "builder-b",
        "questions": [{"question": "served?", "answer": "yes", "served": "yes"}],
        "defects": [{"severity": "fatal", "what": "x", "evidence": "y"}],
        "refs": [],
    }
    ledger = root / "contract" / "judged_verdicts.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(_json.dumps(forged) + "\n")
    with pytest.raises(ValueError, match="fails the verdict spine"):
        growth.transition(root, "p", "GRADED", evidence={"verdict_id": "SEV-FORGED"})


def test_regoal_names_the_pairing_debt(tmp_path, monkeypatch):
    # without the banked goal-v2 supersede record id the sidecar carries the debt
    # visibly; with it, the id is recorded and the flag is absent
    root = _tmp_root(tmp_path)
    _to_wired(root, "p", monkeypatch)
    side = growth.regoal(root, "p",
                         evidence={"ruling": {"by": "gerard", "verb": "REGOAL", "ref": "card-1"}})
    assert side.get("pending_goal_supersede") is True
    _to_wired(root, "q", monkeypatch)
    side_q = growth.regoal(root, "q",
                           evidence={"ruling": {"by": "gerard", "verb": "REGOAL", "ref": "card-2"},
                                     "supersede_record_id": "RW-20260722-000000-000001"})
    assert "pending_goal_supersede" not in side_q
    regoal_row = [h for h in side_q["history"] if h["to"] == "REGOALED"][-1]
    assert regoal_row["evidence"]["supersede_record_id"] == "RW-20260722-000000-000001"
