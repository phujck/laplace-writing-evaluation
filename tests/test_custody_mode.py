"""The custody switch (laplace.representation.custody_mode, his ruling 2026-09-14): one row turns the custody /
fabric layer off; every consumer renders a stub instead of gating; one more row turns it back on.
The suite forces the live paths by default (tests/conftest.py); these tests clear that and test
the OFF path on their own fixtures - never on the repository's live row."""
from __future__ import annotations

import hashlib
import json
import shlex
from pathlib import Path

import pytest

from laplace.representation import custody_mode


@pytest.fixture
def off_root(tmp_path, monkeypatch):
    monkeypatch.delenv("LAPLACE_CUSTODY_LIVE", raising=False)
    (tmp_path / "contract").mkdir()
    (tmp_path / "contract" / "journal.jsonl").write_text("", encoding="utf-8")
    return tmp_path


def test_no_row_keeps_obsolete_custody_off(tmp_path, monkeypatch):
    monkeypatch.delenv("LAPLACE_CUSTODY_LIVE", raising=False)
    mode = custody_mode.read(tmp_path)
    assert mode["mode"] == "OFF" and "default" in mode["source"]
    assert custody_mode.is_off(tmp_path) is True


def test_set_mode_banks_a_row_and_the_latest_row_wins(off_root, monkeypatch):
    monkeypatch.setenv("LAPLACE_ROOT", str(off_root))
    row = custody_mode.set_mode(off_root, "OFF", by="test", reason="because", reintegration_trigger="two seats")
    assert row["mode"] == "OFF" and row["crutch"] == custody_mode.CRUTCH
    assert custody_mode.read(off_root)["mode"] == "OFF"
    assert custody_mode.is_off(off_root) is True
    custody_mode.set_mode(off_root, "ON", by="test", reason="reintegrated", reintegration_trigger="n/a")
    assert custody_mode.read(off_root)["mode"] == "ON"
    assert custody_mode.is_off(off_root) is False
    rows = [json.loads(l) for l in (off_root / custody_mode.STORE).read_text().splitlines() if l.strip()]
    assert [r["mode"] for r in rows] == ["OFF", "ON"], "append-only; the latest row is the mode"


def test_forced_live_overrides_an_off_row_without_moving_it(off_root, monkeypatch):
    monkeypatch.setenv("LAPLACE_ROOT", str(off_root))
    custody_mode.set_mode(off_root, "OFF", by="test", reason="because", reintegration_trigger="two seats")
    monkeypatch.setenv("LAPLACE_CUSTODY_LIVE", "1")
    assert custody_mode.read(off_root)["mode"] == "OFF"
    assert custody_mode.is_off(off_root) is False


def test_set_mode_refuses_an_unnamed_switch(off_root):
    with pytest.raises(ValueError):
        custody_mode.set_mode(off_root, "OFF", by="", reason="", reintegration_trigger="")
    with pytest.raises(ValueError):
        custody_mode.set_mode(off_root, "SIDEWAYS", by="t", reason="r", reintegration_trigger="x")


def test_stub_carries_the_row_and_the_trigger_but_never_prose_identity(off_root, monkeypatch):
    monkeypatch.setenv("LAPLACE_ROOT", str(off_root))
    custody_mode.set_mode(off_root, "OFF", by="gerard in session", reason="the triad died", reintegration_trigger="two seats")
    stub = custody_mode.stub("seat_fabric", off_root)
    assert stub["status"] == "CUSTODY-OFF" and stub["component"] == "seat_fabric"
    assert stub["crutch"] == custody_mode.CRUTCH and stub["authority_effect"] == "none"
    assert stub["reintegration_trigger"] == "two seats"
    assert "descend" in stub


def test_off_diagnostic_reads_account_without_entering_wake_or_custody(off_root, monkeypatch, capsys):
    from laplace.engine import eigen_authority, wake

    monkeypatch.setattr(wake, "_repo_root", lambda: off_root)
    monkeypatch.setattr(wake, "wake_payload", lambda *a, **k: pytest.fail("diagnostic entered wake"))
    monkeypatch.setattr(eigen_authority, "observe_authority", lambda *a, **k: pytest.fail("retired holder consulted"))
    monkeypatch.setattr(custody_mode, "set_mode", lambda *a, **k: pytest.fail("diagnostic changed custody mode"))
    before = {str(path.relative_to(off_root)): path.read_bytes()
              for path in off_root.rglob("*") if path.is_file()}
    command = shlex.split(custody_mode.stub("seat_fabric", off_root)["descend"])
    assert command[:2] == ["scripts/laplace-python", "scripts/wake.py"]
    assert wake.main(command[2:]) == 0
    account = json.loads(capsys.readouterr().out)
    assert {"promises", "work_orders", "open_stack", "defects"} <= account.keys()
    assert account["defects"], "missing local evidence must stay visible"
    assert before == {str(path.relative_to(off_root)): path.read_bytes()
                      for path in off_root.rglob("*") if path.is_file()}


def test_turn_reconstruction_answers_custody_off_not_fog(off_root, monkeypatch):
    from laplace.engine import turn_reconstruction
    monkeypatch.setattr(custody_mode, "is_off", lambda root=None: True)
    out = turn_reconstruction.reconstruct_turn(off_root, event_name="Wake", prompt="", function="", seat_id="", thread_id="")
    assert out["status"] == "CUSTODY-OFF" and out["fog"] == [] and out["read_only"] is True
    assert out["authority_effect"] == "none"


@pytest.mark.parametrize("mode", ["engine", "person"])
def test_wake_renders_stubs_and_takes_the_eigen_path_while_off(tmp_path, monkeypatch, mode):
    from laplace.engine import wake, eigen_authority, self_corpus
    from laplace.web import scanner
    from laplace.pipeline import dial_profiles as dials
    from laplace.representation import embedding_health
    ROOT = tmp_path
    monkeypatch.setattr(eigen_authority, "observe_authority", lambda *a, **k: pytest.fail("retired holder consulted"))
    monkeypatch.setattr(scanner, "probe", lambda: {"status": "fixture"})
    monkeypatch.setattr(self_corpus, "reconstruct_self", lambda *a, **k: {"status": "fixture"})
    monkeypatch.setattr(dials, "projection", lambda: [])
    monkeypatch.setattr(embedding_health, "read_health", lambda *a: {"status": "fixture"})
    monkeypatch.setattr(wake, "_semantic_block", lambda *a: {"status": "fixture"})
    monkeypatch.setattr(wake, "development_work_map_glow", lambda *a, **k: pytest.fail("Atlas custody projection loaded"))
    (ROOT / "ATLAS_DEVELOPMENT_STATE.md").write_text("Dated programme fixture; no live authority claim.")
    monkeypatch.delenv("LAPLACE_CUSTODY_LIVE", raising=False)
    fake = {"mode": "OFF", "id": "CUSTODY-OFF-TEST", "since": "2026-09-14T00:00:00Z", "reintegration_trigger": "two seats", "forced_live": False}
    monkeypatch.setattr(custody_mode, "is_off", lambda root=None: True)
    monkeypatch.setattr(custody_mode, "read", lambda root=None: dict(fake))
    payload = wake.wake_payload(ROOT, grade_delta=False, mode=mode)
    assert next(iter(payload)) == "custody_mode", "the first key says why the fabric is absent"
    for key in ("seat_fabric", "recovery_coordinate", "development_work_map", "turn_reconstruction", "successor_profile"):
        assert payload[key]["status"] == "CUSTODY-OFF", key
    assert payload["fixed_point"], "the self still reconstructs"
    assert payload["eigen_authority"]["status"] == "NOT_REQUIRED"
    work_map = payload["development_work_map"]
    assert work_map["programme_source"]["path"] == "ATLAS_DEVELOPMENT_STATE.md"
    assert work_map["programme_source"]["status"] == "AVAILABLE"
    assert work_map["programme_source"]["authority_effect"] == "none"
    assert "--kind repository-file" in work_map["descend"]
    assert "LAPLACE_CUSTODY_LIVE" not in work_map["descend"]
    # Force the hard compact projection; neither engine nor person loses the source pointer.
    payload["eigen_authority"]["details"] = "large diagnostic detail " * 20_000
    payload["fixed_point"] = {"wake_mode": mode, "identity": {"you_are": "fixture"}}
    bounded = wake._bound_authored_payload(payload, mode=mode)
    assert bounded["development_work_map"]["programme_source"] == work_map["programme_source"]
    assert bounded["development_work_map"]["descend"] == work_map["descend"]
    cap = wake._AUTHORED_WAKE_CAP_PERSON if mode == "person" else wake._AUTHORED_WAKE_CAP_ENGINE
    assert wake._json_size(bounded) <= cap


def test_missing_programme_source_is_named_without_loading_custody(tmp_path, monkeypatch):
    from laplace.engine import wake
    monkeypatch.delenv("LAPLACE_CUSTODY_LIVE", raising=False)
    out = wake._development_work_map_off(tmp_path)
    assert out["status"] == "CUSTODY-OFF"
    assert out["programme_source"]["status"] == "MISSING"
    assert out["programme_source"]["path"] == "ATLAS_DEVELOPMENT_STATE.md"
    assert not list(tmp_path.iterdir())


def test_close_custody_step_is_inert_while_off(monkeypatch):
    import importlib.util, sys
    ROOT = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("sewup_under_test", ROOT / "scripts" / "sewup.py")
    sewup = importlib.util.module_from_spec(spec); spec.loader.exec_module(sewup)
    monkeypatch.setattr(custody_mode, "is_off", lambda root=None: True)
    monkeypatch.setattr(custody_mode, "read", lambda root=None: {"mode": "OFF", "since": "s", "by": "b", "reason": "r", "reintegration_trigger": "t"})
    out = sewup.step_custody()
    assert out["pass"] is None and out["verdict"] == "INERT" and "not a gate while OFF" in out["detail"]


def test_dispatch_admits_an_exact_typed_descent_by_hash_while_off():
    from laplace.pipeline import dispatch as D
    content = "# node\n\nexact bytes\n"
    handle = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
    good = {"reference": "n.md", "goal": "g", "kind": "repository-file", "content": content, "content_handle": handle,
            "content_status": "COMPLETE", "read_only": True, "transition_claim": "none", "authority_write": "none"}
    ok = D._admit_typed_descent_custody_off(target="n.md", goal="g", worker="derive", reconstruction=good)
    assert ok["admission_result"] == {"status": "ADMITTED", "reason": "CUSTODY-OFF-TYPED-DESCENT-BY-HASH"}
    for bad, reason in (
        ({**good, "content": content + "x"}, "CONTENT_HANDLE_MISMATCH"),
        ({**good, "content_status": "TRUNCATED"}, "RECONSTRUCTION_TRUNCATED"),
        ({**good, "goal": "other"}, "GOAL_MISMATCH"),
        ({**good, "reference": "m.md"}, "NODE_MISMATCH"),
        ({**good, "read_only": False}, "READ_AUTHORITY_MISMATCH"),
        (None, "MISSING_RECONSTRUCTION"),
    ):
        out = D._admit_typed_descent_custody_off(target="n.md", goal="g", worker="derive", reconstruction=bad)
        assert out["admission_result"]["status"] == "REFUSED" and out["admission_result"]["reason"] == reason, reason


def test_torn_declaration_cannot_resurrect_an_old_on_row(off_root):
    path = off_root / custody_mode.STORE
    path.write_text(json.dumps({"record": "custody-mode", "mode": "ON"}) + '\n{"record":')
    before = path.read_bytes()
    assert custody_mode.is_off(off_root)
    assert path.read_bytes() == before
    with path.open("a") as handle:
        handle.write('\n' + json.dumps({"record": "custody-mode", "mode": "ON"}) + '\n')
    assert not custody_mode.is_off(off_root), "a later explicit declaration can reintegrate"
