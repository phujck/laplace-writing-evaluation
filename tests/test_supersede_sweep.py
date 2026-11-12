"""Scoped tests for scripts/supersede_sweep.py — the retrospective proxy reporter.

A fixture repo with a verdict that supersedes a marker, plus two root *.md files
citing that marker: one STAMPED (a neighbouring line names SUPERSEDED) and one
UNSTAMPED. The sweep must WARN and list only the unstamped citation; rc is always 0.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "supersede_sweep.py"

spec = importlib.util.spec_from_file_location("supersede_sweep", SCRIPT)
supersede_sweep = importlib.util.module_from_spec(spec)
sys.modules["supersede_sweep"] = supersede_sweep
spec.loader.exec_module(supersede_sweep)

RULING_ID = "PV-20260712-f11-the-unseal"
MARKER = "seal-2026-06-08"


def _fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    rec = {"id": RULING_ID, "date": "2026-07-12", "supersedes": [MARKER],
           "supersedes_markers": [MARKER]}
    (repo / "proxy_verdicts.jsonl").write_text(
        json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")
    # unstamped citation — the marker stands with no SUPERSEDED nearby
    (repo / "STILL_CITED.md").write_text(
        "# a durable doc\n"
        f"the old {MARKER} interim still stated here as live\n"
        "next line\n",
        encoding="utf-8",
    )
    # stamped citation — a neighbouring line names SUPERSEDED
    (repo / "RETIRED.md").write_text(
        "# another durable doc\n"
        "SUPERSEDED by PV-20260712-f11-the-unseal (the unseal)\n"
        f"the {MARKER} reference, now retired\n",
        encoding="utf-8",
    )
    return repo


@pytest.fixture
def repo(tmp_path):
    return _fixture(tmp_path)


def test_sweep_lists_only_unstamped(repo):
    records = supersede_sweep.load_verdicts(repo)
    selected = supersede_sweep._select(records, RULING_ID, False)
    hits = supersede_sweep.sweep(repo, selected)
    files = {h["file"] for h in hits}
    assert "STILL_CITED.md" in files
    assert "RETIRED.md" not in files, "a SUPERSEDED-adjacent citation must count as stamped"
    assert all(h["marker"] == MARKER for h in hits)


def test_main_warns_and_rc0(repo, capsys):
    rc = supersede_sweep.main(["--repo", str(repo), "--ruling", RULING_ID])
    out = capsys.readouterr().out.strip().splitlines()
    assert rc == 0, "advisory in v1 — rc always 0"
    assert out[-1].startswith("VERDICT=WARN")
    assert "unstamped=1" in out[-1]
    assert "STILL_CITED.md" in out[-1]


def test_clean_when_all_stamped_is_pass(repo, capsys):
    # stamp the last live citation too, then the sweep is clean
    (repo / "STILL_CITED.md").write_text(
        "# a durable doc\n"
        "SUPERSEDED 2026-07-12\n"
        f"the old {MARKER} interim, now retired\n",
        encoding="utf-8",
    )
    rc = supersede_sweep.main(["--repo", str(repo), "--ruling", RULING_ID])
    out = capsys.readouterr().out.strip().splitlines()
    assert rc == 0
    assert out[-1] == "VERDICT=PASS unstamped=0"


def test_unknown_ruling_is_clean_pass(repo, capsys):
    rc = supersede_sweep.main(["--repo", str(repo), "--ruling", "PV-does-not-exist"])
    out = capsys.readouterr().out.strip().splitlines()
    assert rc == 0
    assert out[-1] == "VERDICT=PASS unstamped=0"


# ----------------------------------------------------------------- F7: --gate / --fix
# AUDIT_2026-07-15 §B3: advisory-only (rc always 0) meant an unstamped citation could
# stand forever without ever moving an exit code. --gate turns the report into a real
# pass/fail signal; --fix writes the missing stamp in place. Both default their
# selection to --all when neither --ruling nor --all is given, since close_checklist
# calls the gate bare.

def test_gate_rc1_on_planted_unstamped_citation(repo, capsys):
    rc = supersede_sweep.main(["--repo", str(repo), "--gate"])
    out = capsys.readouterr().out.strip().splitlines()
    assert rc == 1, "an unstamped citation must move the exit code under --gate"
    assert out[-1].startswith("VERDICT=FAIL")
    assert "unstamped=1" in out[-1]
    assert "STILL_CITED.md" in out[-1]
    gate_line = next(ln for ln in out if ln.startswith("--gate:"))
    assert "1 unstamped citation" in gate_line
    assert "STILL_CITED.md" in gate_line


def test_gate_rc0_after_hand_stamp(repo, capsys):
    # hand-stamp the same way test_clean_when_all_stamped_is_pass does
    (repo / "STILL_CITED.md").write_text(
        "# a durable doc\n"
        "SUPERSEDED 2026-07-12\n"
        f"the old {MARKER} interim, now retired\n",
        encoding="utf-8",
    )
    rc = supersede_sweep.main(["--repo", str(repo), "--gate"])
    out = capsys.readouterr().out.strip().splitlines()
    assert rc == 0
    assert out[-1] == "VERDICT=PASS unstamped=0"


def test_fix_then_gate_rc0(repo, capsys):
    rc_fix = supersede_sweep.main(["--repo", str(repo), "--fix"])
    out_fix = capsys.readouterr().out.strip().splitlines()
    assert rc_fix == 0, "--fix alone stays advisory (rc 0) unless --gate is also passed"
    assert any(ln == "--fix: stamped STILL_CITED.md" for ln in out_fix)
    assert out_fix[-1] == "VERDICT=PASS unstamped=0", "the fix must cure the citation immediately"

    # a --fix'd file must pass the VERY NEXT --gate, on a fresh invocation
    rc_gate = supersede_sweep.main(["--repo", str(repo), "--gate"])
    out_gate = capsys.readouterr().out.strip().splitlines()
    assert rc_gate == 0
    assert out_gate[-1] == "VERDICT=PASS unstamped=0"

    # the stamp actually landed in the file and names SUPERSEDED
    text = (repo / "STILL_CITED.md").read_text(encoding="utf-8")
    assert "SUPERSEDED" in text
    assert MARKER in text


def test_fix_and_gate_combined_rc0(repo, capsys):
    rc = supersede_sweep.main(["--repo", str(repo), "--fix", "--gate"])
    out = capsys.readouterr().out.strip().splitlines()
    assert rc == 0
    assert out[-1] == "VERDICT=PASS unstamped=0"
    assert any(ln == "--fix: stamped STILL_CITED.md" for ln in out)


def test_default_invocation_rc0_always(repo, capsys):
    # default: --ruling given, neither --gate nor --fix — today's advisory behaviour,
    # byte-identical to before this session's change.
    rc = supersede_sweep.main(["--repo", str(repo), "--ruling", RULING_ID])
    out = capsys.readouterr().out.strip().splitlines()
    assert rc == 0
    assert out[-1].startswith("VERDICT=WARN")

    # bare --all, still no --gate/--fix: also rc 0 always
    rc_all = supersede_sweep.main(["--repo", str(repo), "--all"])
    out_all = capsys.readouterr().out.strip().splitlines()
    assert rc_all == 0
    assert out_all[-1].startswith("VERDICT=WARN")
    assert not any(ln.startswith("--gate:") for ln in out_all)
    assert not any(ln.startswith("--fix:") for ln in out_all)


def test_gate_defaults_selection_to_all_when_neither_given(repo, capsys):
    # close_checklist calls the gate bare — no --ruling, no --all — and it must still
    # find the planted verdict's markers via the implicit --all default.
    rc = supersede_sweep.main(["--repo", str(repo), "--gate"])
    out = capsys.readouterr().out.strip().splitlines()
    assert rc == 1
    assert f"ruling {RULING_ID} supersedes" in "\n".join(out)


def test_no_selection_and_no_gate_or_fix_is_a_usage_error(repo):
    with pytest.raises(SystemExit):
        supersede_sweep.main(["--repo", str(repo)])
