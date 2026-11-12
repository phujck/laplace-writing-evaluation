"""Golden master for the paper_eigen collapse: pipeline.loop_gates.run_gates
must REPRODUCE the archived scripts/_archive/paper_gates.py on the real
paper_eigen/_loop/ drafts.

"Reproduces" means: the archived script is executed once (subprocess), its JSON
report parsed from stdout, and the two verdict structures compared for exact
equality after a JSON round-trip — the same sections, and per section the same
flag lists/counts (orphan numerals, bad claim tags, bad citekeys, banned
constructions, friction blocks, word count), plus the same whole-object
verdicts (lexicon ladder statuses, banned-jargon counts, full word count).

The archive move changed the script's ``__file__``-relative ROOT (it resolved
paths as ``parent.parent`` from ``scripts/``), so the driver execs the archived
SOURCE with ``__file__`` re-anchored at its original ``scripts/`` location —
the source runs verbatim, nothing is copied into the tree. Both runs rewrite
``_loop/draft_full.md`` with identical mechanical content (verified byte-stable
before the collapse), so the tree is left as found.
"""

from __future__ import annotations

import json
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

from laplace.pipeline import loop_gates, registry

RR = Path(__file__).resolve().parents[1]


def _load_paper_gates_shim() -> dict:
    """Execute scripts/paper_gates.py's module body (imports + def _verdict/main)
    WITHOUT the ``if __name__ == "__main__":`` guard, so no real project is run
    and no output is printed -- just the namespace, for unit-testing ``_verdict``
    and ``main`` against synthetic reports."""
    return runpy.run_path(str(RR / "scripts" / "paper_gates.py"), run_name="paper_gates_under_test")


def _run_archived() -> dict:
    driver = (
        "import pathlib, sys\n"
        f"root = pathlib.Path({str(RR)!r})\n"
        "src = (root / 'scripts' / '_archive' / 'paper_gates.py')"
        ".read_text(encoding='utf-8')\n"
        "g = {'__file__': str(root / 'scripts' / 'paper_gates.py'),"
        " '__name__': '__main__'}\n"
        "try:\n"
        "    exec(compile(src, 'paper_gates.py', 'exec'), g)\n"
        "except SystemExit:\n"
        "    pass\n"
    )
    out = subprocess.run([sys.executable, "-c", driver], capture_output=True,
                         encoding="utf-8", cwd=RR, timeout=120)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_run_gates_reproduces_the_archived_verdicts():
    golden = _run_archived()
    mine = json.loads(json.dumps(loop_gates.run_gates("paper_eigen", RR)))
    assert mine == golden


def test_gates_profile_is_registry_data():
    prof = registry.resolve("paper_eigen").gates_profile
    assert prof["sections"] == 8
    assert "spine" in prof["banned_jargon"]           # machine vocabulary stays banned
    assert ["em-dash", "—"] in prof["banned_constructions"]


def test_run_gates_fences_non_loop_projects():
    assert "error" in loop_gates.run_gates("no-such-project")
    assert "error" in loop_gates.run_gates("subset-sum-itqde")   # conceptric, not loop


# ---------------------------------------------------------------------------
# Gate purity: run_gates is a pure reporter by default. draft_full.md is
# derived state, materialised ONLY when a caller opts in with write_draft=True.
# The whole-object passes read the in-memory concatenation, not the file, so
# suppressing the write leaves the report identical (guarded by the golden
# master above). These run against an isolated repo_root copy of _loop so the
# real tree is never mutated.
# ---------------------------------------------------------------------------


def _isolated_loop(tmp_path: Path) -> Path:
    """Copy the real paper_eigen/_loop into a throwaway repo_root and drop any
    pre-existing draft_full.md so absence is a clean signal."""
    loop = tmp_path / "paper_eigen" / "_loop"
    shutil.copytree(RR / "paper_eigen" / "_loop", loop)
    (loop / "draft_full.md").unlink(missing_ok=True)
    return loop


def test_run_gates_default_does_not_write_draft_full(tmp_path):
    loop = _isolated_loop(tmp_path)
    loop_gates.run_gates("paper_eigen", tmp_path)
    assert not (loop / "draft_full.md").exists()


def test_run_gates_write_draft_materialises_draft_full(tmp_path):
    loop = _isolated_loop(tmp_path)
    loop_gates.run_gates("paper_eigen", tmp_path, write_draft=True)
    assert (loop / "draft_full.md").is_file()
    assert (loop / "draft_full.md").read_text(encoding="utf-8").strip()


def test_run_gates_report_identical_regardless_of_write(tmp_path):
    loop = _isolated_loop(tmp_path)
    pure = json.loads(json.dumps(loop_gates.run_gates("paper_eigen", tmp_path)))
    assert not (loop / "draft_full.md").exists()
    written = json.loads(json.dumps(
        loop_gates.run_gates("paper_eigen", tmp_path, write_draft=True)))
    assert pure == written


# ---------------------------------------------------------------------------
# scripts/paper_gates.py -- the exit-0-on-RED fix. The shim used to
# json.dumps() the raw report (no aggregated ok) and fall off the end,
# exiting 0 whether the report was clean or RED. _verdict aggregates the
# report; main() must emit VERDICT=PASS/FAIL as its LAST line and mirror it
# in the return code.
# ---------------------------------------------------------------------------


def _clean_report() -> dict:
    return {"sections": {1: {"orphan_numerals": [], "bad_claim_tags": [], "bad_citekeys": [],
                              "banned_constructions": [], "friction_blocks": 0, "words": 10}},
            "full": {"lexicon_ladder": {"term": "ok"}, "banned_jargon": {}, "words": 10}}


def _dirty_report() -> dict:
    return {"sections": {1: {"orphan_numerals": ["7"], "bad_claim_tags": [], "bad_citekeys": [],
                              "banned_constructions": [], "friction_blocks": 0, "words": 10},
                          2: {"error": "draft missing"}},
            "full": {"lexicon_ladder": {"term": "UNUSED"}, "banned_jargon": {"spine": 2}, "words": 10}}


def test_paper_gates_verdict_ok_on_clean_report():
    ns = _load_paper_gates_shim()
    ok, reasons = ns["_verdict"](_clean_report())
    assert ok is True
    assert reasons == []


def test_paper_gates_verdict_names_every_failure_on_dirty_report():
    ns = _load_paper_gates_shim()
    ok, reasons = ns["_verdict"](_dirty_report())
    assert ok is False
    assert reasons == ["banned_jargon", "draft_missing", "lexicon_ladder", "orphan_numerals"]


def test_paper_gates_verdict_fences_project_errors():
    ns = _load_paper_gates_shim()
    ok, reasons = ns["_verdict"]({"error": "unknown project 'nope'"})
    assert ok is False
    assert reasons == ["error"]


def test_paper_gates_cli_emits_sentinel_as_last_line_on_pass(monkeypatch, capsys):
    ns = _load_paper_gates_shim()
    # main()'s globals are a distinct dict from ns (runpy copies it out), so the
    # patch target is main's own __globals__, not ns itself.
    monkeypatch.setitem(ns["main"].__globals__, "run_gates", lambda project: _clean_report())
    rc = ns["main"]("fake_project")
    lines = capsys.readouterr().out.rstrip("\n").splitlines()
    assert lines[-1] == "VERDICT=PASS"
    assert rc == 0


def test_paper_gates_cli_emits_sentinel_as_last_line_on_fail_and_exits_nonzero(monkeypatch, capsys):
    ns = _load_paper_gates_shim()
    monkeypatch.setitem(ns["main"].__globals__, "run_gates", lambda project: _dirty_report())
    rc = ns["main"]("fake_project")
    lines = capsys.readouterr().out.rstrip("\n").splitlines()
    assert lines[-1] == "VERDICT=FAIL checks=4/7 reasons=banned_jargon,draft_missing,lexicon_ladder,orphan_numerals"
    assert rc == 1
