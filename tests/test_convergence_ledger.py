"""The convergence ledger assembler: round-ordered open-findings deltas, per-gate
transitions (hard/soft/panels, value + changed-from-previous), and the cost join off
an ``economics.json`` beside the rounds (absent -> "never captured").

Pure-logic tests over a synthetic ``rounds/harnessed`` tree — no registry project, the
assembler takes a dir directly.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from laplace.pipeline import convergence_ledger as cl

pytestmark = pytest.mark.unit

_ECON_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "workflow_economics.py"


def _load_economics():
    """The workflow_economics adapter module (Fix 0d), loaded like its own test does —
    it is a script, not an installed package."""
    spec = importlib.util.spec_from_file_location("workflow_economics", _ECON_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mech(md: Path, rnd: int, *, hard, soft, panels, date="2026-07-11"):
    h = md / "rounds" / "harnessed"
    h.mkdir(parents=True, exist_ok=True)
    (h / f"mech_r{rnd}.json").write_text(json.dumps({
        "round": rnd, "date": date,
        "panel": [{"label": lab, "clean": clean, "flags": []}
                  for lab, clean in panels.items()],
        "contract": {"hard": hard, "soft": soft},
    }), encoding="utf-8")


def _detect_post(md: Path, rnd: int, open_n: int):
    h = md / "rounds" / "harnessed"
    h.mkdir(parents=True, exist_ok=True)
    (h / f"detect_post_r{rnd}.json").write_text(json.dumps({
        "phase": "post", "round": rnd, "open_findings_n": open_n}), encoding="utf-8")


def test_three_rounds_ordered_deltas_and_transitions(tmp_path):
    md = tmp_path / "manuscript"
    md.mkdir()
    _mech(md, 1, hard={"technical_support": False}, soft={"rhythm": 0.5},
          panels={"meta_leak": True})
    _mech(md, 2, hard={"technical_support": False}, soft={"rhythm": 0.5},
          panels={"meta_leak": False})
    _mech(md, 3, hard={"technical_support": True}, soft={"rhythm": 1.0},
          panels={"meta_leak": False})
    _detect_post(md, 1, 100)
    _detect_post(md, 2, 80)
    _detect_post(md, 3, 80)

    led = cl.assemble_ledger(md)
    rounds = led["rounds"]
    assert [r["round"] for r in rounds] == [1, 2, 3]
    assert led["layout"] == "harnessed"

    # open-findings deltas: first is None, then the running difference
    assert [r["findings_delta"] for r in rounds] == [None, -20, 0]
    assert [r["open_findings"] for r in rounds] == [100, 80, 80]

    # gate transitions carry value + changed-from-previous
    assert rounds[0]["gates"]["hard"]["technical_support"] == {
        "value": False, "from": None, "changed": False}
    assert rounds[1]["gates"]["panels"]["meta_leak"] == {
        "value": False, "from": True, "changed": True}
    assert rounds[2]["gates"]["hard"]["technical_support"] == {
        "value": True, "from": False, "changed": True}
    assert rounds[2]["gates"]["soft"]["rhythm"]["changed"] is True
    assert rounds[1]["gates"]["hard"]["technical_support"]["changed"] is False


def test_missing_economics_is_never_captured(tmp_path):
    md = tmp_path / "manuscript"
    md.mkdir()
    _mech(md, 1, hard={"technical_support": True}, soft={}, panels={"caption": True})
    led = cl.assemble_ledger(md)
    assert led["rounds"][0]["cost"] == "never captured"
    # the renderer must not crash on the absent-cost ledger
    assert "never captured" in cl.to_markdown(led)


def test_economics_join_when_present(tmp_path):
    md = tmp_path / "manuscript"
    md.mkdir()
    _mech(md, 1, hard={}, soft={}, panels={"caption": True})
    (md / "rounds" / "economics.json").write_text(
        json.dumps({"1": {"usd": 0.42}}), encoding="utf-8")
    led = cl.assemble_ledger(md)
    assert led["rounds"][0]["cost"] == {"usd": 0.42}


def test_economics_join_reads_rounds_adapter_output(tmp_path):
    """Fix 0d: the round-keyed adapter (workflow_economics.render_rounds_economics) writes
    the ``{"rounds": {...}}`` wrapper; _economics unwraps it and _cost_for keys on the
    round ordinal — so the per-round cost column resolves from the adapter's own output."""
    econ_mod = _load_economics()
    md = tmp_path / "manuscript"
    md.mkdir()
    _mech(md, 2, hard={}, soft={}, panels={"caption": True})
    # a summarized economics dict (workflow_economics shape) with a round-2 phase; the
    # adapter round-keys its cost, exactly as the CLI's --rounds-out would.
    summarized = {"run_dir": "run", "totals": {"agents": 1, "cost_usd": 0.30},
                  "by_phase": {"mech_r2": {"cost_usd": 0.30}}}
    (md / "rounds").mkdir(parents=True, exist_ok=True)
    (md / "rounds" / "economics.json").write_text(
        json.dumps(econ_mod.render_rounds_economics(summarized)), encoding="utf-8")

    econ = cl._economics(md)                       # unwraps the {"rounds": {...}} wrapper
    assert cl._cost_for(econ, 2) == 0.30
    assert cl.assemble_ledger(md)["rounds"][0]["cost"] == 0.30


def test_round_integer_ordering_beats_lexical(tmp_path):
    md = tmp_path / "manuscript"
    md.mkdir()
    _mech(md, 2, hard={"technical_support": False}, soft={}, panels={})
    _mech(md, 10, hard={"technical_support": True}, soft={}, panels={})
    _detect_post(md, 2, 30)
    _detect_post(md, 10, 5)

    rounds = cl.assemble_ledger(md)["rounds"]
    assert [r["round"] for r in rounds] == [2, 10]         # not lexical ("10" < "2")
    # r10's delta and flip are computed against r2, its true integer predecessor
    assert rounds[1]["findings_delta"] == -25
    assert rounds[1]["gates"]["hard"]["technical_support"]["from"] is False
    assert rounds[1]["gates"]["hard"]["technical_support"]["changed"] is True


def test_orphaned_econ_round_is_emitted_econ_only(tmp_path):
    """A cost banked in economics.json for a round with no mech/detect record surfaces
    as an econ_only round — labeled, cost present, no fabricated findings/gates. The
    joined rounds carry NO econ_only key (byte-identical for existing consumers)."""
    md = tmp_path / "manuscript"
    md.mkdir()
    _mech(md, 1, hard={"technical_support": False}, soft={}, panels={"caption": True})
    _mech(md, 2, hard={"technical_support": True}, soft={}, panels={"caption": True})
    (md / "rounds" / "economics.json").write_text(
        json.dumps({"rounds": {"2": 1.0, "6": 4.58}}), encoding="utf-8")

    rounds = cl.assemble_ledger(md)["rounds"]
    assert [r["round"] for r in rounds] == [1, 2, 6]
    orphan = rounds[-1]
    assert orphan["econ_only"] is True
    assert orphan["cost"] == 4.58
    assert orphan["open_findings"] is None
    assert orphan["gates"] == {"hard": {}, "soft": {}, "panels": {}}
    # joined rounds keep the byte-identical shape — the key is entirely absent
    assert "econ_only" not in rounds[0]
    assert "econ_only" not in rounds[1]
    # and it renders labeled, not as a silent phantom
    assert "economics-only" in cl.to_markdown(cl.assemble_ledger(md))


def test_non_integer_econ_key_is_skipped(tmp_path):
    """A non-integer econ key ("total") is never guessed into a phantom round."""
    md = tmp_path / "manuscript"
    md.mkdir()
    _mech(md, 2, hard={}, soft={}, panels={"caption": True})
    (md / "rounds" / "economics.json").write_text(
        json.dumps({"rounds": {"2": 1.0, "total": 9.9}}), encoding="utf-8")

    rounds = cl.assemble_ledger(md)["rounds"]
    assert [r["round"] for r in rounds] == [2]
    assert all("econ_only" not in r for r in rounds)


def test_econ_only_round_does_not_pollute_transitions(tmp_path):
    """An interleaved econ-only round must not pollute the prev_* bookkeeping: r3's
    transitions and findings-delta compare against r1, its true predecessor with a record."""
    md = tmp_path / "manuscript"
    md.mkdir()
    _mech(md, 1, hard={"technical_support": False}, soft={}, panels={})
    _mech(md, 3, hard={"technical_support": True}, soft={}, panels={})
    _detect_post(md, 1, 40)
    _detect_post(md, 3, 25)
    (md / "rounds" / "economics.json").write_text(
        json.dumps({"rounds": {"2": 2.0}}), encoding="utf-8")

    rounds = cl.assemble_ledger(md)["rounds"]
    assert [r["round"] for r in rounds] == [1, 2, 3]
    assert rounds[1]["econ_only"] is True
    # r3 compares against r1, not the interleaved econ-only r2
    assert rounds[2]["gates"]["hard"]["technical_support"] == {
        "value": True, "from": False, "changed": True}
    assert rounds[2]["findings_delta"] == -15


def test_missing_project_dir_errors_without_crash(tmp_path):
    led = cl.assemble_ledger(tmp_path / "nope")
    assert "error" in led
    assert "convergence ledger" in cl.to_markdown(led)
