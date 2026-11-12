"""THE GENERATION LEDGER — heredity's stamp (generation_ledger) + the forcing-defect
fix in the reprojection gate + the additive dated read in the fitness panel.

The stamp is refs-only (identity + pointers, never a copied number); it refuses a
double-stamp and an unattributed stamp; the read is tolerant; the gate's dated
archives never overwrite; and the fitness debt trajectory picks a dated archive up
additively. Pattern: tests/test_evolution_surface.py fixtures.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from laplace.pipeline import adjudicate as adj
from laplace.pipeline import generation_ledger as gl

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def md(tmp_path):
    """A bare manuscript dir with a feedback ledger — the stamp derives its refs
    from what sits under here (nothing, until a test writes an artifact)."""
    m = tmp_path / "manuscript"
    (m / "feedback").mkdir(parents=True)
    (m / "feedback" / "feedback.jsonl").write_text("", encoding="utf-8")
    return m


def _append_fb(md_dir: Path, rec: dict) -> None:
    with (md_dir / "feedback" / "feedback.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def _rop(rec_id: str, intent_id: str, ts: str) -> dict:
    return adj.make_ratified_operation(intent_id, outcome="applied", op_kind="set-meta",
                                       actor="gerard", rec_id=rec_id, ts=ts)


# --------------------------------------------------------------------------- #
# 1 — the stamp banks REFS ONLY (identity + pointers, never a copied number)
# --------------------------------------------------------------------------- #

def test_stamp_banks_refs_only(md):
    rep = md / "reprojection"
    rep.mkdir()
    (rep / "run_record_2026-07-20.json").write_text(
        json.dumps({"kind": "reprojection-run-record", "at": "2026-07-20T10:00:00",
                    "source_delta_after": {"n": 20}}), encoding="utf-8")
    (rep / "freeze_verdict_2026-07-20.json").write_text(json.dumps({"pass": True}),
                                                        encoding="utf-8")
    rec = gl.stamp_generation(md, "cx", by="gerard")
    assert "error" not in rec
    assert rec["id"] == "GEN-cx-1" and rec["record"] == "generation" and rec["n"] == 1
    assert rec["stamped_by"] == "gerard"
    # the ref is a manuscript-relative POINTER string — not the run's number copied in
    assert rec["reprojection"]["run_record"] == "reprojection/run_record_2026-07-20.json"
    assert isinstance(rec["reprojection"]["run_record"], str)
    assert rec["reprojection"]["freeze_verdict"] == "reprojection/freeze_verdict_2026-07-20.json"
    # refs-only: the block is exactly two pointer strings — no copied debt number
    # (no source_delta_after / n / counts value hoisted out of the run record)
    assert set(rec["reprojection"]) == {"run_record", "freeze_verdict"}
    assert all(isinstance(v, str) for v in rec["reprojection"].values())
    assert "source_delta_after" not in rec["reprojection"] and "n" not in rec["reprojection"]
    # and it landed on the ledger
    assert gl.read_generations(md) == [rec]


# --------------------------------------------------------------------------- #
# 2 — an absent artifact banks a NULL ref; the stamp is still lawful
# --------------------------------------------------------------------------- #

def test_absent_artifacts_stamp_lawfully_with_null_refs(md):
    rec = gl.stamp_generation(md, "cx", by="gerard")
    assert "error" not in rec and rec["id"] == "GEN-cx-1"
    assert rec["reprojection"] == {"run_record": None, "freeze_verdict": None}
    assert rec["converge"] == {"detect_pre": None, "detect_post": None}
    assert rec["minted"] == {"pdf": None, "finalize": None}
    assert rec["r10"] == {"report_id": None, "clean": None}
    assert gl.read_generations(md)[0]["id"] == "GEN-cx-1"


# --------------------------------------------------------------------------- #
# 3 — a double-stamp REFUSES (every ref identical → nothing moved, banks nothing)
# --------------------------------------------------------------------------- #

def test_double_stamp_refuses(md):
    first = gl.stamp_generation(md, "cx", by="gerard")
    assert "error" not in first
    again = gl.stamp_generation(md, "cx", by="gerard")
    assert "error" in again and "identical" in again["error"]
    assert len(gl.read_generations(md)) == 1        # nothing banked on the refusal


# --------------------------------------------------------------------------- #
# 4 — the ENTERED window: two stamps, ops between, only the after-ops enter gen2
# --------------------------------------------------------------------------- #

def test_entered_window_derivation(md):
    # op A pre-dates gen1 → belongs to gen1 (all ops enter generation 1)
    _append_fb(md, _rop("ROP-A", "CI-A", "2000-01-01T00:00:00"))
    gen1 = gl.stamp_generation(md, "cx", by="gerard")
    assert gen1["entered"]["ratified_op_ids"] == ["ROP-A"]
    assert gen1["entered"]["intent_ids"] == ["CI-A"]

    # move a ref so gen2 is not a double-stamp
    rep = md / "reprojection"
    rep.mkdir()
    (rep / "run_record_2026-07-20.json").write_text(
        json.dumps({"at": "2026-07-20T10:00:00", "source_delta_after": {"n": 7}}),
        encoding="utf-8")
    # op B is AFTER gen1's stamp; op C is far-past (before gen1) → only B enters gen2
    _append_fb(md, _rop("ROP-B", "CI-B", "2099-01-01T00:00:00"))
    _append_fb(md, _rop("ROP-C", "CI-C", "2000-06-01T00:00:00"))
    gen2 = gl.stamp_generation(md, "cx", by="gerard")
    assert "error" not in gen2 and gen2["n"] == 2
    assert gen2["entered"]["ratified_op_ids"] == ["ROP-B"]
    assert gen2["entered"]["intent_ids"] == ["CI-B"]


# --------------------------------------------------------------------------- #
# 5 — an unattributed stamp REFUSES (no generation in nobody's name)
# --------------------------------------------------------------------------- #

def test_unattributed_stamp_refuses(md):
    out = gl.stamp_generation(md, "cx", by="")
    assert "error" in out and "by" in out["error"]
    assert gl.read_generations(md) == []            # nothing banked
    assert not (md / "generations.jsonl").exists()


# --------------------------------------------------------------------------- #
# 6 — the read is TOLERANT of a corrupt line (skips it, never raises)
# --------------------------------------------------------------------------- #

def test_read_tolerant_of_a_corrupt_line(md):
    good = gl.stamp_generation(md, "cx", by="gerard")
    with (md / "generations.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("{ this is not json\n")
    got = gl.read_generations(md)
    assert got == [good]                            # poison line skipped, good kept


# --------------------------------------------------------------------------- #
# 7 — the gate's dated archive helper NEVER overwrites (same-day → _2)
# --------------------------------------------------------------------------- #

def _load_gate_module():
    spec = importlib.util.spec_from_file_location(
        "reprojection_gate", REPO / "scripts" / "reprojection_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_gate_dated_archives_never_overwrite(tmp_path):
    gate = _load_gate_module()
    out = tmp_path / "manuscript" / "reprojection"
    a = gate.write_run_archives(out, {"run": 1}, {"pass": True}, date="2026-07-21")
    b = gate.write_run_archives(out, {"run": 2}, {"pass": False}, date="2026-07-21")
    assert a["run_record"].endswith("run_record_2026-07-21.json")
    assert b["run_record"].endswith("run_record_2026-07-21_2.json")
    assert b["freeze_verdict"].endswith("freeze_verdict_2026-07-21_2.json")
    # the first archive is untouched by the second same-day run (never overwritten)
    assert json.loads(Path(a["run_record"]).read_text())["run"] == 1
    assert json.loads(Path(b["run_record"]).read_text())["run"] == 2
    assert {p.name for p in out.glob("run_record_*.json")} == {
        "run_record_2026-07-21.json", "run_record_2026-07-21_2.json"}


# --------------------------------------------------------------------------- #
# 8 — the fitness debt trajectory picks a dated archive up ADDITIVELY (dedup by at,n)
# --------------------------------------------------------------------------- #

def test_fitness_picks_up_dated_archive_additively(tmp_path, monkeypatch):
    from laplace.pipeline import fitness_panel as fp
    from laplace.pipeline import registry

    class _FakeProj:
        manuscript_dir = "manuscript"
        def path(self, rel, repo_root=None):
            return Path(repo_root) / rel

    monkeypatch.setattr(registry, "resolve", lambda name: _FakeProj())
    rep = tmp_path / "manuscript" / "reprojection"
    rep.mkdir(parents=True)
    # the latest pointer (n=20 on 2026-07-20)
    (rep / "run_record.json").write_text(
        json.dumps({"at": "2026-07-20T10:00:00", "source_delta_after": {"n": 20}}),
        encoding="utf-8")
    # a dated archive DUPLICATING the pointer's run → deduped (at,n) == (2026-07-20,20)
    (rep / "run_record_2026-07-20.json").write_text(
        json.dumps({"at": "2026-07-20T10:00:00", "source_delta_after": {"n": 20}}),
        encoding="utf-8")
    # a DISTINCT dated archive (older run, n=25) → additive point
    (rep / "run_record_2026-07-19.json").write_text(
        json.dumps({"at": "2026-07-19T10:00:00", "source_delta_after": {"n": 25}}),
        encoding="utf-8")

    out = fp.read_fitness("cx", tmp_path)
    traj = out["debt_trajectory"]
    keys = {(p["at"], p["n"]) for p in traj}
    assert ("2026-07-20", 20) in keys                # the pointer point
    assert ("2026-07-19", 25) in keys                # the additive dated point
    # dedup: the pointer's run is not double-counted despite the identical archive
    assert sum(1 for p in traj if (p["at"], p["n"]) == ("2026-07-20", 20)) == 1
    assert any(p["source"] == "reprojection/run_record_2026-07-19.json" for p in traj)
