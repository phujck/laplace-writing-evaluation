"""The dreamer's freeze gate, held in place by tests.

His ruling PV-20260820T114500Z-fork2-dreamer-frozen installed a gate on the one autonomy
he asked taken back: the promoter writing ``lifecycle.yaml`` on its own authority. The gate
shipped with ZERO coverage (WO-20260820-freeze-gate-untested) - nothing outside
``dreamer.py`` even named it - so a refactor could have silently un-installed it without a
single red.

These tests fix the gate's contract in three parts, and each part is the thing that would
otherwise fail silently:

  1. **the default** - what a caller with no flags set gets;
  2. **the flags** - both polarities, read off an injected env so the process is untouched;
  3. **the wiring** - that ``apply_transitions`` actually consults the gate before it
     persists, checked structurally as well as behaviourally, because a behavioural test
     alone passes if the call is deleted and the default happens to agree.

Nothing here loads a model, a network, or the real canon; the canon is a two-attribute stub,
because the gate is about the WRITE, not about what is being written.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
import yaml

from laplace.engine import dreamer


@pytest.fixture(autouse=True)
def _no_ambient_flags(monkeypatch):
    """Every test states its own flag state; none inherits the shell's."""
    monkeypatch.delenv(dreamer.DREAMER_WRITE_FLAG, raising=False)
    monkeypatch.delenv(dreamer.DREAMER_FREEZE_FLAG, raising=False)


class _StubCanon:
    """The two attributes ``apply_transitions`` touches: a root to write into and a
    lifecycle overlay to update. Not a Canon - deliberately, so this file cannot drift into
    testing the canon loader instead of the gate."""

    def __init__(self, root: Path, lifecycle: dict | None = None):
        self.root = root
        self.lifecycle = lifecycle if lifecycle is not None else {"skills": {}}


def _report():
    return {
        "skills": [{"name": "sample_widget", "fitness": 0.71}],
        "transitions": [{"name": "sample_widget", "from": "experimental", "to": "core",
                         "reason": "earned promotion: 6 uses, fitness 0.71"}],
    }


# --- 1. the default --------------------------------------------------------------------

def test_unfrozen_by_default_when_no_flag_is_set():
    """THE DEFAULT IS THE RULING, and this line is where the ruling changed.

    It read ``is True`` from 2026-08-20 morning (his freeze, PV-20260820T114500Z) until
    2026-08-20 night, when the bar that freeze pre-registered was measured and met: D1
    PV-20260820T223000Z set the polarity, D2b PV-20260820T223001Z set the bar at >= 4 of
    12, the query-conditioned residual flipped 4, and the signal was wired into
    assess._fitness so the promoter this unfreezes runs on the swapped signal rather than
    the one F23 named wrong. Asserted, not assumed, so the next change is a diff too."""
    assert dreamer.dreamer_frozen({}) is False


def test_the_default_is_read_from_the_process_environment_when_env_is_none(monkeypatch):
    monkeypatch.delenv(dreamer.DREAMER_WRITE_FLAG, raising=False)
    monkeypatch.delenv(dreamer.DREAMER_FREEZE_FLAG, raising=False)
    assert dreamer.dreamer_frozen() is False
    monkeypatch.setenv(dreamer.DREAMER_FREEZE_FLAG, "1")
    assert dreamer.dreamer_frozen() is True


# --- 2. both flags, both polarities ----------------------------------------------------

def test_the_freeze_flag_re_freezes():
    assert dreamer.dreamer_frozen({dreamer.DREAMER_FREEZE_FLAG: "1"}) is True


def test_the_write_flag_overrides_a_re_freeze():
    """Kept from the frozen era and now load-bearing in the other direction: a caller that
    means to write always can, whatever the ambient re-freeze says."""
    assert dreamer.dreamer_frozen({
        dreamer.DREAMER_FREEZE_FLAG: "1", dreamer.DREAMER_WRITE_FLAG: "1",
    }) is False


def test_an_empty_flag_value_does_not_re_freeze():
    """An exported-but-empty variable is the shell's way of saying nothing. Re-freezing is
    the deliberate act now, so an empty value must not be mistaken for one."""
    assert dreamer.dreamer_frozen({dreamer.DREAMER_FREEZE_FLAG: ""}) is False


def test_an_empty_write_flag_does_not_override(monkeypatch):
    assert dreamer.dreamer_frozen({
        dreamer.DREAMER_FREEZE_FLAG: "1", dreamer.DREAMER_WRITE_FLAG: "",
    }) is True


def test_the_injected_env_does_not_read_the_process(monkeypatch):
    """The gate is injectable so it can be tested without mutating the process - and an
    injected env must WIN, or every test here is measuring the shell instead."""
    monkeypatch.setenv(dreamer.DREAMER_FREEZE_FLAG, "1")
    assert dreamer.dreamer_frozen({}) is False


# --- 3. the wiring: the gate is consulted at the persist step --------------------------

def test_apply_transitions_skips_the_persist_while_re_frozen(tmp_path, monkeypatch):
    monkeypatch.setenv(dreamer.DREAMER_FREEZE_FLAG, "1")
    canon = _StubCanon(tmp_path)
    out = dreamer.apply_transitions(canon, _report())
    assert out["frozen"] is True
    assert out["lifecycle_path"] is None
    assert not (tmp_path / "lifecycle.yaml").exists(), "a frozen promoter wrote to disk"


def test_a_frozen_promoter_still_proposes(tmp_path, monkeypatch):
    """What freezes is the WRITE, not the thought: the transitions are still computed and
    still returned, so the dream keeps surfacing what it would have done."""
    monkeypatch.setenv(dreamer.DREAMER_FREEZE_FLAG, "1")
    out = dreamer.apply_transitions(_StubCanon(tmp_path), _report())
    assert [t["name"] for t in out["applied"]] == ["sample_widget"]
    assert out["notice"] and dreamer.DREAMER_FREEZE_FLAG in out["notice"]


def test_apply_transitions_persists_by_default(tmp_path, monkeypatch):
    """The unfreeze, at the only place it is observable: no flags at all, and the promoter
    writes lifecycle.yaml on its own authority - which is exactly the autonomy his bar
    was pre-registered to return."""
    canon = _StubCanon(tmp_path)
    out = dreamer.apply_transitions(canon, _report())
    assert out.get("frozen") is not True
    path = tmp_path / "lifecycle.yaml"
    assert out["lifecycle_path"] == path and path.is_file()
    written = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert written["skills"]["sample_widget"]["status"] == "core"
    assert written["skills"]["sample_widget"]["history"][-1]["to"] == "core"


def test_the_persist_step_structurally_consults_the_gate():
    """The behavioural tests above pass even if the gate call is deleted, as long as the
    default agrees with them by accident. This one does not: it reads the function's own
    AST and fails if the persist step stops asking."""
    tree = ast.parse(inspect.getsource(dreamer.apply_transitions))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "dreamer_frozen" in called, (
        "apply_transitions no longer consults dreamer_frozen(): the gate his ruling "
        "installed has been refactored away"
    )


def test_the_notice_is_one_loud_line_that_does_not_claim_a_pending_measurement():
    """The notice a re-frozen promoter prints must describe the world as it is. It used to
    say the write was skipped 'pending the fitness-swap-replay'; that replay has run, and a
    notice still citing it would tell a future reader the measurement is outstanding."""
    notice = dreamer._dreamer_frozen_notice()
    assert notice.count("\n") == 0
    assert "DREAMER_FROZEN" in notice
    assert "pending" not in notice.lower()
    assert dreamer.DREAMER_FREEZE_FLAG in notice, "the notice must name what re-froze it"
    assert "PV-20260820T223001Z" in notice, "and the ruling that says the bar was met"
