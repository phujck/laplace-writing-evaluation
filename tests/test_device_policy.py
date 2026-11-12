"""The fallback recorder: a CPU landing leaves a row, the require flag makes it a refusal."""

import json

import pytest

from laplace.representation import device_policy


@pytest.fixture(autouse=True)
def _use_the_laplace_root_door(monkeypatch):
    """These tests exercise the LAPLACE_ROOT door specifically, so the suite-wide
    ``LAPLACE_FALLBACK_LOG`` isolation (tests/conftest.py) is stood down here - it would win over
    LAPLACE_ROOT by design and the assertions below would read an empty tmp file. The override's
    own door is covered by ``test_log_override_wins_over_root``."""
    monkeypatch.delenv(device_policy.LOG_OVERRIDE, raising=False)


def _rows(root):
    p = root / device_policy.LOG_FILE
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def test_cpu_landing_leaves_a_row(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LAPLACE_ROOT", str(tmp_path))
    monkeypatch.delenv(device_policy.REQUIRE_FLAG, raising=False)
    device_policy.record_fallback("fold-spectral", "cpu", "cupy missing")
    rows = _rows(tmp_path)
    assert len(rows) == 1 and rows[0]["organ"] == "fold-spectral"
    assert rows[0]["choice"] == "cpu" and not rows[0]["dialed"]
    assert "FALLBACK" in capsys.readouterr().out


def test_require_flag_turns_fallback_into_refusal(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_ROOT", str(tmp_path))
    monkeypatch.setenv(device_policy.REQUIRE_FLAG, "1")
    with pytest.raises(device_policy.DeviceRequired):
        device_policy.record_fallback("metric-distill", "cpu", "gpu absent")
    # the row lands even when the refusal fires - the record precedes the raise
    assert len(_rows(tmp_path)) == 1


def test_dialed_choice_is_lawful_under_require(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LAPLACE_ROOT", str(tmp_path))
    monkeypatch.setenv(device_policy.REQUIRE_FLAG, "1")
    device_policy.record_fallback("metric-distill", "cpu", "explicit deny", dialed=True)
    rows = _rows(tmp_path)
    assert rows[0]["dialed"] and "FALLBACK" not in capsys.readouterr().out


def test_gpu_landing_is_not_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_ROOT", str(tmp_path))
    device_policy.record_fallback("fold-spectral", "gpu", "")
    assert _rows(tmp_path) == []


def test_logging_failure_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_ROOT", str(tmp_path / "does-not-exist" / "nested"))
    monkeypatch.delenv(device_policy.REQUIRE_FLAG, raising=False)
    device_policy.record_fallback("fold-spectral", "cpu", "why")  # must not raise


# --- the census's own two repairs (2026-08-21) -----------------------------------------------

def test_log_override_wins_over_root(tmp_path, monkeypatch):
    """``LAPLACE_FALLBACK_LOG`` is the test-isolation door: it beats LAPLACE_ROOT outright, so the
    suite can never again forge the repo's census store (72 of its first 95 rows were fixtures)."""
    monkeypatch.setenv("LAPLACE_ROOT", str(tmp_path))
    monkeypatch.setenv(device_policy.LOG_OVERRIDE, str(tmp_path / "elsewhere.jsonl"))
    monkeypatch.delenv(device_policy.REQUIRE_FLAG, raising=False)
    device_policy.record_fallback("fold-spectral", "cpu", "cupy missing")
    assert not (tmp_path / device_policy.LOG_FILE).exists()   # the root store stays clean
    assert (tmp_path / "elsewhere.jsonl").is_file()


def test_disabled_is_not_a_device_landing(tmp_path, monkeypatch, capsys):
    """CENSUS C5: a missing CPU-side capability is not the GPU's fault. It records, it prints, and
    ``LAPLACE_REQUIRE_GPU`` does NOT refuse it - a false refusal on healthy hardware is what would
    otherwise stop the require flag becoming this box's default."""
    monkeypatch.setenv("LAPLACE_ROOT", str(tmp_path))
    monkeypatch.setenv(device_policy.REQUIRE_FLAG, "1")
    device_policy.record_fallback("spectral-clustering", "disabled", "sklearn missing")
    rows = _rows(tmp_path)
    assert len(rows) == 1 and rows[0]["choice"] == "disabled"
    out = capsys.readouterr().out
    assert "DISABLED" in out and "FALLBACK" not in out


def test_row_carries_provenance(tmp_path, monkeypatch):
    """A row says WHO wrote it. Under pytest ``synthetic`` is True - a test's device landing is a
    fixture, never evidence about this box - which is the column the first census had to
    reconstruct by forensics (burst arity, the word 'simulated' inside ``why``)."""
    monkeypatch.setenv("LAPLACE_ROOT", str(tmp_path))
    monkeypatch.delenv(device_policy.REQUIRE_FLAG, raising=False)
    device_policy.record_fallback("metric-distill", "cpu", "cupy missing")
    row = _rows(tmp_path)[0]
    assert row["synthetic"] is True and isinstance(row["pid"], int) and row["proc"]


# ---------------------------------------------------------------------------
# the local default (2026-08-21, the Enforce lane): the flag is now ON by default on this box,
# which makes two things load-bearing that were merely nice while it was opt-in - the dial-OUT
# must work, and the declaration must stay where the shells read it.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["0", "", "off", "no", "false"])
def test_dial_out_of_the_local_default(tmp_path, monkeypatch, capsys, value):
    """THE ESCAPE HATCH IS THE PRICE OF A BOX-WIDE DEFAULT. Once the session-start hook exports
    ``LAPLACE_REQUIRE_GPU=1`` into every Bash shell, a run that legitimately wants the CPU (a
    quick probe, a box whose device is out, bisecting a GPU regression) has exactly one way back:
    setting the flag to something falsy for that run. The recorder accepts only 1/true/yes/on, so
    every other spelling dials out - it still records and still prints loudly, because the landing
    is real; it just does not refuse. Untested, this is the difference between a default and a
    trap."""
    monkeypatch.setenv("LAPLACE_ROOT", str(tmp_path))
    monkeypatch.setenv(device_policy.REQUIRE_FLAG, value)
    device_policy.record_fallback("fold-spectral", "cpu", "cupy missing")   # must not raise
    assert len(_rows(tmp_path)) == 1
    assert "FALLBACK" in capsys.readouterr().out


def test_the_hook_declares_the_local_default_and_remote_does_not():
    """THE DECLARATION HAS A HOME AND THIS PINS IT. ``.claude/hooks/session-start.mjs`` section 3
    appends the export to ``CLAUDE_ENV_FILE``, which is sourced before every Bash-tool command -
    that file IS the engine's local dial surface on this box, and one export line is a
    declaration, never an install (the passive-startup law, INCIDENT_2026-08-21: startup touches
    nothing). It must sit on the LOCAL branch only: the remote container has no device, so
    requiring one there would refuse every run for telling the truth. A silent drop of this line
    is a silent return of the degrade class, so the pin is on the line, not on the intent."""
    from pathlib import Path
    hook = (Path(__file__).resolve().parent.parent
            / ".claude" / "hooks" / "session-start.mjs").read_text(encoding="utf-8")
    decl = f"export {device_policy.REQUIRE_FLAG}=1"
    assert decl in hook, "the local default is no longer declared in the session-start hook"
    # the local branch of the ternary is the one after the ':' - the remote arm must not carry it.
    # Comment lines are dropped first: the rationale for the LOCAL export is written between the
    # two arms and names the flag, so a raw substring test would read the prose as the code.
    remote_arm = hook.split("const lines = isRemote", 1)[1].split("?", 1)[1].split("\n    :", 1)[0]
    remote_arm = "\n".join(l for l in remote_arm.splitlines() if not l.strip().startswith("//"))
    assert device_policy.REQUIRE_FLAG not in remote_arm, \
        "the require flag leaked onto the remote arm, where there is no device to require"
