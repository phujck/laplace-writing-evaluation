"""Tests for THE PROBE (``laplace.engine.probe``), fix seq 0 of the internals campaign.

The unit half exercises the before/after difference helpers on a tmp_path, because
those helpers ARE the measurement — a wrong diff makes every later fix's verdict
wrong. The integration half runs the real probe against the real repository with
``--no-bank`` and asserts that every column is present and the scratch tree is gone.

Nothing here asserts a numeric bound on a measured phase: the probe measures, it does
not judge, and a test that pinned a byte count or a wall time would be exactly the
hand-set gate this campaign exists to remove.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.engine import probe as P  # noqa: E402


# ------------------------------------------------------------------ tree diffing

def test_diff_tree_counts_created_files_and_their_bytes(tmp_path):
    before = P.snapshot_tree(tmp_path)
    (tmp_path / "a.txt").write_bytes(b"x" * 10)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.bin").write_bytes(b"y" * 100)
    d = P.diff_tree(before, P.snapshot_tree(tmp_path))
    assert d["files_created"] == 2
    assert d["bytes_written"] == 110
    assert d["files_modified"] == 0
    assert os.path.join("sub", "b.bin") in d["files_created_top"]


def test_diff_tree_counts_growth_and_truncation_as_writes(tmp_path):
    f = tmp_path / "g.log"
    f.write_bytes(b"a" * 50)
    before = P.snapshot_tree(tmp_path)
    f.write_bytes(b"a" * 70)          # +20
    d = P.diff_tree(before, P.snapshot_tree(tmp_path))
    assert d["files_created"] == 0 and d["files_modified"] == 1
    assert d["bytes_written"] == 20

    before2 = P.snapshot_tree(tmp_path)
    f.write_bytes(b"a" * 60)          # truncation is a write too
    d2 = P.diff_tree(before2, P.snapshot_tree(tmp_path))
    assert d2["files_modified"] == 1 and d2["bytes_written"] == 10


def test_diff_tree_splits_interpreter_bytecode_into_its_own_columns(tmp_path):
    before = P.snapshot_tree(tmp_path)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__pycache__").mkdir()
    (tmp_path / "pkg" / "__pycache__" / "m.cpython-312.pyc").write_bytes(b"c" * 1000)
    (tmp_path / "state.jsonl").write_bytes(b"s" * 7)
    d = P.diff_tree(before, P.snapshot_tree(tmp_path))
    assert d["files_created"] == 2 and d["bytes_written"] == 1007
    assert d["files_created_ex_cache"] == 1 and d["bytes_written_ex_cache"] == 7
    assert d["files_created_ex_cache_top"] == ["state.jsonl"]


def test_is_bytecode_cache_names_only_bytecode():
    assert P.is_bytecode_cache(os.path.join("a", "__pycache__", "x.cpython-312.pyc"))
    assert P.is_bytecode_cache("x.pyc")
    assert not P.is_bytecode_cache(os.path.join("contract", "probe_runs.jsonl"))


def test_diff_tree_reports_deletions_without_counting_them_as_bytes(tmp_path):
    (tmp_path / "dead").write_bytes(b"z" * 5)
    before = P.snapshot_tree(tmp_path)
    (tmp_path / "dead").unlink()
    d = P.diff_tree(before, P.snapshot_tree(tmp_path))
    assert d["files_deleted"] == 1 and d["bytes_written"] == 0


def test_snapshot_tree_measures_the_index_and_the_store_inside_a_clone(tmp_path):
    """The CLONE-side snapshot hides nothing but git's transient lock.

    ``.git/index`` used to be deleted from the measurement (it gets its own column
    now) and so did the probe's own store, which the probe never writes inside a
    clone — so excluding it there only created a blind spot.
    """
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "index").write_bytes(b"i" * 9)
    (tmp_path / ".git" / "index.lock").write_bytes(b"l")
    (Path(tmp_path) / "contract").mkdir()
    (tmp_path / P.STORE).write_bytes(b"r" * 9)
    snap = P.snapshot_tree(tmp_path)
    assert P.GIT_INDEX_RELPATH in snap
    assert P.STORE in snap
    assert os.path.join(".git", "index.lock") not in snap


def test_snapshot_tree_excludes_only_the_store_on_the_source_side(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "index").write_bytes(b"i" * 9)
    (Path(tmp_path) / "contract").mkdir()
    (tmp_path / P.STORE).write_bytes(b"r" * 9)
    snap = P.snapshot_tree(tmp_path, exclude=P.SOURCE_EXCLUDE_RELPATHS)
    assert P.STORE not in snap
    assert P.GIT_INDEX_RELPATH in snap


def test_split_index_gives_git_index_churn_its_own_columns(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "index").write_bytes(b"i" * 4)
    (tmp_path / ".git" / "HEAD").write_bytes(b"h" * 3)
    _work, gitd = P._split_git(P.snapshot_tree(tmp_path))
    rest, idx = P._split_index(gitd)
    assert list(idx) == [P.GIT_INDEX_RELPATH]
    assert P.GIT_INDEX_RELPATH not in rest


def test_split_git_separates_the_work_tree_from_the_object_store(tmp_path):
    (tmp_path / ".git" / "objects").mkdir(parents=True)
    (tmp_path / ".git" / "objects" / "o").write_bytes(b"o" * 4)
    (tmp_path / "w.txt").write_bytes(b"w")
    work, gitd = P._split_git(P.snapshot_tree(tmp_path))
    assert list(work) == ["w.txt"]
    assert list(gitd) == [os.path.join(".git", "objects", "o")]


# ------------------------------------------------------------------- tmp diffing

def test_diff_dirs_reports_entries_created_under_each_watched_root(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    before = P.snapshot_dirs([str(a), str(b), str(tmp_path / "missing")])
    (a / "new1").write_text("x")
    (a / "new2").mkdir()
    d = P.diff_dirs(before, P.snapshot_dirs([str(a), str(b), str(tmp_path / "missing")]))
    assert d[str(a)]["entries_created"] == 2
    assert d[str(b)]["entries_created"] == 0
    assert d[str(tmp_path / "missing")]["entries_created"] == 0
    assert d[str(a)]["entries_created_top"] == ["new1", "new2"]


def test_diff_dirs_reports_removals_separately(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    (a / "gone").write_text("x")
    before = P.snapshot_dirs([str(a)])
    (a / "gone").unlink()
    d = P.diff_dirs(before, P.snapshot_dirs([str(a)]))
    assert d[str(a)]["entries_removed"] == 1 and d[str(a)]["entries_created"] == 0


# ------------------------------------------------------------------ process diff

def test_diff_procs_separates_our_descendants_from_the_rest_of_the_box():
    me = os.getpid()
    before = {1: (0, "init")}
    after = {1: (0, "init"), 50: (me, "child"), 51: (50, "grandchild"), 52: (1, "stranger")}
    d = P.diff_procs(before, after, ancestor=me)
    assert d["procs_left"] == 3
    assert d["procs_left_descendant"] == 2
    assert any("grandchild" in s for s in d["procs_left_descendant_top"])


def test_diff_procs_survives_a_ppid_cycle():
    table = {10: (11, "a"), 11: (10, "b")}
    assert P._descends_from(10, 99, table) is False


# ------------------------------------------------------- the one bound, and caps

def test_every_subsidiary_bound_is_derived_from_the_one_banked_timeout():
    """There is one chosen number (the subprocess timeout); everything else is a
    fraction of it, so a reader of a row can see every bound that was in force."""
    b = P.derive_bounds(P.DEFAULT_TIMEOUT_S)
    assert set(b) == set(P.BOUND_FRACTIONS)
    for k, frac in P.BOUND_FRACTIONS.items():
        assert b[k] == max(1, round(P.DEFAULT_TIMEOUT_S * frac))
        assert 0 < b[k] <= P.DEFAULT_TIMEOUT_S
    # halve the one number and every derived bound halves with it
    half = P.derive_bounds(P.DEFAULT_TIMEOUT_S / 2)
    assert all(half[k] <= b[k] for k in b)
    assert P.derive_bounds(0.0001) == {k: 1 for k in P.BOUND_FRACTIONS}


def test_evidence_caps_are_declared_and_actually_applied():
    assert set(P.EVIDENCE_CAPS) == {"top", "tail_bytes", "argv_chars"}
    me = os.getpid()
    after = {i: (me, "x" * 500) for i in range(50)}
    d = P.diff_procs({}, after, ancestor=me)
    assert len(d["procs_left_top"]) == P.EVIDENCE_CAPS["top"]
    argv = d["procs_left_top"][0].split(" ", 1)[1]
    assert len(argv) == P.EVIDENCE_CAPS["argv_chars"]


def test_run_phase_truncates_its_stderr_tail_at_the_banked_cap(tmp_path):
    ph = P.run_phase("noisy", ["/usr/bin/python3", "-c",
                               "import sys; sys.stderr.write('e'*5000); raise SystemExit(2)"],
                     cwd=tmp_path, env=P.cold_env(), timeout=P.DEFAULT_TIMEOUT_S)
    assert ph["rc"] == 2
    assert len(ph["tail"]) == P.EVIDENCE_CAPS["tail_bytes"]


# ------------------------------------------------- a failed measurement is not a 0

def test_snapshot_procs_reports_a_nonzero_ps_as_an_error_not_an_empty_table():
    table, err = P.snapshot_procs(ps_argv=["/usr/bin/python3", "-c", "raise SystemExit(7)"])
    assert table == {} and err is not None and "7" in err


def test_snapshot_procs_reports_a_timed_out_ps_as_an_error():
    bounds = {**P.DEFAULT_BOUNDS, "ps": 1}
    table, err = P.snapshot_procs(
        bounds=bounds, ps_argv=["/usr/bin/python3", "-c", "import time; time.sleep(30)"])
    assert table == {} and err is not None and "Timeout" in err


def test_snapshot_procs_reports_a_missing_binary_as_an_error():
    table, err = P.snapshot_procs(ps_argv=["/nonexistent/ps-that-is-not-there"])
    assert table == {} and err is not None


def test_git_objects_reports_a_failure_as_an_error_not_a_zero_delta(tmp_path):
    """The bug this pins: a failed count returned {}, and every *_delta then read 0 —
    'the object store did not grow' and 'I could not look' were the same row."""
    fields, err = P.git_objects(tmp_path, argv=["git", "count-objects", "--no-such-flag"])
    assert fields == {} and err is not None
    assert P.diff_git({"count": 5}, fields)["count_delta"] == -5   # not a truth, an artefact


def test_run_phase_banks_an_error_column_when_a_measurement_subprocess_fails(
        tmp_path, monkeypatch):
    monkeypatch.setattr(P, "snapshot_procs",
                        lambda **kw: ({}, "ps rc=7"))
    monkeypatch.setattr(P, "git_objects",
                        lambda *a, **kw: ({}, "TimeoutExpired after 120s"))
    ph = P.run_phase("blind", ["/usr/bin/python3", "-c", "pass"],
                     cwd=tmp_path, env=P.cold_env(), timeout=P.DEFAULT_TIMEOUT_S,
                     watch_dirs=[str(tmp_path)])
    assert ph["procs_snapshot_error"] and "ps rc=7" in ph["procs_snapshot_error"]
    assert ph["git_objects_error"] and "Timeout" in ph["git_objects_error"]
    assert ph["procs_left"] == 0                      # the number is still 0 ...
    t = P.totals([ph])
    assert t["measurement_errors"] == 2               # ... but the row says it is blind
    assert t["procs_snapshot_errors"] == ["blind"]


def test_run_phase_leaves_the_error_columns_null_when_the_measurement_worked(tmp_path):
    ph = P.run_phase("clean", ["/usr/bin/python3", "-c", "pass"],
                     cwd=tmp_path, env=P.cold_env(), timeout=P.DEFAULT_TIMEOUT_S,
                     watch_dirs=[str(tmp_path)])
    assert ph["procs_snapshot_error"] is None and ph["git_objects_error"] is None


# ------------------------------------------------------------------ env stripping

def test_cold_env_strips_the_session_and_declares_the_minimal_path(monkeypatch):
    monkeypatch.setenv("CLAUDE_ENV_FILE", "/somewhere/env")
    monkeypatch.setenv("VIRTUAL_ENV", "/repo/.venv")
    monkeypatch.setenv("PYTHONPATH", "/injected")
    monkeypatch.setenv("HOME", "/home/someone")
    env = P.cold_env()
    assert env["PATH"] == P.MINIMAL_PATH == "/usr/local/bin:/usr/bin:/bin"
    assert env["HOME"] == "/home/someone"
    assert env["PYTHONUTF8"] == "1"
    for banned in ("CLAUDE_ENV_FILE", "VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME"):
        assert banned not in env


def test_cold_env_extra_is_the_only_way_anything_else_gets_in():
    env = P.cold_env(extra={"CLAUDE_PROJECT_DIR": "/clone"}, tmpdir="/tmp/x")
    assert env["CLAUDE_PROJECT_DIR"] == "/clone" and env["TMPDIR"] == "/tmp/x"


def test_which_all_resolves_against_the_given_path_only():
    assert P.which_all("python3", {"PATH": "/usr/bin"}) == ["/usr/bin/python3"]
    assert P.which_all("python3", {"PATH": "/nonexistent"}) == []


# ------------------------------------------------------------------- git objects

def test_git_objects_and_delta_on_a_real_throwaway_repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    before, err = P.git_objects(tmp_path)
    assert err is None
    assert "count" in before and "size_pack" in before
    (tmp_path / "f.txt").write_text("hello")
    env = {**os.environ, "GIT_AUTHOR_NAME": "p", "GIT_AUTHOR_EMAIL": "p@x",
           "GIT_COMMITTER_NAME": "p", "GIT_COMMITTER_EMAIL": "p@x"}
    subprocess.run(["git", "add", "f.txt"], cwd=tmp_path, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=tmp_path, check=True, env=env)
    after, err2 = P.git_objects(tmp_path)
    assert err2 is None
    d = P.diff_git(before, after)
    assert d["count_delta"] > 0


# ----------------------------------------------------------------- phase + totals

def test_run_phase_measures_a_command_that_writes_into_the_tree(tmp_path):
    ph = P.run_phase("writer", ["/usr/bin/python3", "-c",
                                "open('made.txt','w').write('q'*33); print('hi')"],
                     cwd=tmp_path, env=P.cold_env(), timeout=60,
                     watch_dirs=[str(tmp_path)], interpreter=P.SYSTEM_PYTHON)
    assert ph["rc"] == 0 and ph["timed_out"] is False
    assert ph["clone_bytes_written"] == 33 and ph["clone_files_created"] == 1
    assert ph["stdout_bytes"] == 3 and ph["stdio_bytes"] == ph["stdout_bytes"] + ph["stderr_bytes"]
    assert ph["wall_s"] >= 0 and ph["interpreter"] == P.SYSTEM_PYTHON
    assert ph["tmp"][str(tmp_path)]["entries_created"] == 1


def test_run_phase_records_a_nonzero_rc_without_raising(tmp_path):
    ph = P.run_phase("failer", ["/usr/bin/python3", "-c", "raise SystemExit(3)"],
                     cwd=tmp_path, env=P.cold_env(), timeout=60)
    assert ph["rc"] == 3            # a column, never a verdict


def test_run_phase_banks_the_timeout_instead_of_hanging(tmp_path):
    ph = P.run_phase("hang", ["/usr/bin/python3", "-c", "import time; time.sleep(30)"],
                     cwd=tmp_path, env=P.cold_env(), timeout=1)
    assert ph["timed_out"] is True and ph["rc"] is None
    assert "TIMEOUT" in ph["tail"]


def _fake_phase(name, wall, wrote, *, tmp_entries=2, procs=1, **over):
    ph = {"phase": name, "rc": 0, "wall_s": wall, "stdout_bytes": 1, "stderr_bytes": 0,
          "stdio_bytes": 1, "clone_bytes_written": wrote, "clone_files_created": 1,
          "clone_files_modified": 0, "clone_files_deleted": 0,
          "clone_bytes_written_ex_cache": wrote,
          "clone_files_created_ex_cache": 1, "clone_files_modified_ex_cache": 0,
          "clone_git_bytes_written": 0,
          "clone_git_files_created": 0, "git_index_bytes_written": 0,
          "git_index_files_created": 0, "git_size_kib_delta": 0,
          "git_size_pack_kib_delta": 0,
          "tmp": {"/tmp": {"entries_created": tmp_entries}},
          "procs": {"procs_left": procs, "procs_left_descendant": 0},
          "tmp_entries_created": tmp_entries, "procs_left": procs,
          "procs_left_descendant": 0,
          "procs_snapshot_error": None, "git_objects_error": None}
    ph.update(over)
    return ph


def test_totals_and_spread_roll_up_the_numeric_columns(tmp_path):
    fake = _fake_phase
    t = P.totals([fake("a", 1.0, 10), fake("b", 2.0, 20)])
    assert t["wall_s"] == 3.0 and t["clone_bytes_written"] == 30
    assert t["tmp_entries_created"] == 4 and t["procs_left"] == 2
    assert t["phases_nonzero_rc"] == [] and t["measurement_errors"] == 0
    s = P.spread([[fake("a", 1.0, 10)], [fake("a", 3.0, 30)]])
    assert s["a"]["wall_s"] == {"min": 1.0, "max": 3.0, "mean": 2.0, "n": 2}
    assert s["a"]["clone_bytes_written"]["mean"] == 20.0


def test_spread_covers_the_leak_columns_the_acceptance_law_is_about():
    """tmp entries, processes left resident and deletions are THE accumulate-nothing
    columns; a spread that did not carry them covered everything except the point."""
    for col in ("tmp_entries_created", "procs_left", "procs_left_descendant",
                "clone_files_deleted", "git_index_bytes_written"):
        assert col in P.NUMERIC_COLUMNS
    s = P.spread([[_fake_phase("a", 1.0, 10, tmp_entries=0, procs=0)],
                  [_fake_phase("a", 1.0, 10, tmp_entries=4, procs=3)]])
    assert s["a"]["tmp_entries_created"] == {"min": 0, "max": 4, "mean": 2.0, "n": 2}
    assert s["a"]["procs_left"]["max"] == 3


def test_totals_names_the_phases_whose_measurement_failed():
    phases = [_fake_phase("a", 1.0, 0),
              _fake_phase("b", 1.0, 0, procs_snapshot_error="ps rc=7",
                          git_objects_error="git count-objects rc=1: boom")]
    t = P.totals(phases)
    assert t["procs_snapshot_errors"] == ["b"]
    assert t["git_objects_errors"] == ["b"]
    assert t["measurement_errors"] == 2


# --------------------------------------------------------- banking and retention

def test_bank_appends_a_readable_row_and_names_the_path_it_took(tmp_path):
    (tmp_path / "contract").mkdir()
    row = {"id": "probe-x", "ts": "2026-09-16T00:00:00Z"}
    via = P.bank(row, root=tmp_path)
    assert via in {"journal.bank_row", "plain_append"}
    rows = P.read_rows(tmp_path)
    assert [r["id"] for r in rows] == ["probe-x"]
    # the durability path is stamped BEFORE the write, so the STORE carries it too
    assert row["banked_via"] == via
    assert rows[0]["banked_via"] == via


def test_bank_stamps_the_fallback_path_on_the_row_it_writes(tmp_path, monkeypatch):
    """The seam is made to fail: the plain append must still name itself on the row."""
    import builtins
    real_import = builtins.__import__

    def boom(name, *a, **kw):
        if name == "laplace.core.records.journal":
            raise ImportError("no seam under this interpreter")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", boom)
    row = {"id": "probe-fallback", "ts": "2026-09-16T00:00:00Z"}
    assert P.bank(row, root=tmp_path) == "plain_append"
    monkeypatch.undo()
    assert row["banked_via"] == "plain_append"
    assert P.read_rows(tmp_path)[0]["banked_via"] == "plain_append"


def test_prune_is_content_keyed_keeping_the_latest_per_identity(tmp_path):
    (tmp_path / "contract").mkdir()
    mk = lambda i, head, tag, ts: {  # noqa: E731
        "id": i, "head": head, "tag": tag, "ts": ts,
        "probe_interpreter": {"sys_executable": "/usr/bin/python3"}}
    for r in (mk("r1", "aaa", "baseline", "2026-09-16T01:00:00Z"),
              mk("r2", "aaa", "baseline", "2026-09-16T02:00:00Z"),
              mk("r3", "bbb", "baseline", "2026-09-16T03:00:00Z"),
              mk("r4", "aaa", "other", "2026-09-16T04:00:00Z")):
        P.bank(r, root=tmp_path)
    plan = P.prune(tmp_path, apply=True)
    assert plan["dropped_ids"] == ["r1"]          # superseded by r2, same identity
    assert {r["id"] for r in P.read_rows(tmp_path)} == {"r2", "r3", "r4"}
    assert plan["kept"] == 3


def test_prune_keeps_a_superseded_row_that_another_store_references(tmp_path):
    (tmp_path / "contract").mkdir()
    (tmp_path / "corpus_friction").mkdir()
    base = {"head": "aaa", "tag": "t", "probe_interpreter": {"sys_executable": "/usr/bin/python3"}}
    P.bank({**base, "id": "r1", "ts": "2026-09-16T01:00:00Z"}, root=tmp_path)
    P.bank({**base, "id": "r2", "ts": "2026-09-16T02:00:00Z"}, root=tmp_path)
    (tmp_path / "corpus_friction" / "campaign.jsonl").write_text(
        json.dumps({"basis": "r1"}) + "\n")
    plan = P.prune(tmp_path, apply=True)
    assert plan["dropped_ids"] == [] and plan["kept_by_reference"] == ["r1"]
    assert {r["id"] for r in P.read_rows(tmp_path)} == {"r1", "r2"}


def test_prune_never_applies_a_numeric_cap(tmp_path):
    """Retention is identity, not count: 30 rows under 30 identities all survive."""
    (tmp_path / "contract").mkdir()
    for n in range(30):
        P.bank({"id": f"r{n}", "head": f"h{n}", "tag": "t", "ts": f"2026-09-16T00:00:{n:02d}Z",
                "probe_interpreter": {"sys_executable": "/usr/bin/python3"}}, root=tmp_path)
    assert P.prune(tmp_path, apply=True)["dropped"] == 0
    assert len(P.read_rows(tmp_path)) == 30


# ------------------------------------------------------------------- integration

#: Every column the row must carry. Later fixes read these names; a rename is a break.
ROW_COLUMNS = ("schema_version", "record", "id", "ts", "tag", "repo", "head", "head_short",
               "source_dirty", "source_dirty_count", "scratch_root", "scratch",
               "origin_removed", "origin_remove_rc", "subprocess_timeout_s",
               "bounds", "bound_fractions", "evidence_caps", "repeat",
               "clone_per_iteration", "spread_temperature", "clones", "watch_dirs",
               "probe_interpreter", "declared_interpreter", "cold_path", "host",
               "close_invocation", "close_note", "clone_wall_s", "clone_rc", "clone_head",
               "which_python3_cold", "which_python3_login", "which_node_cold",
               "one_interpreter", "phases", "totals", "spread", "scratch_removed")

PHASE_COLUMNS = ("phase", "argv", "interpreter", "rc", "timed_out", "wall_s", "stdout_bytes",
                 "stderr_bytes", "stdio_bytes", "clone_bytes_written", "clone_files_created",
                 "clone_files_created_top", "clone_files_modified", "clone_files_deleted",
                 "clone_bytes_written_ex_cache", "clone_files_created_ex_cache",
                 "clone_files_created_ex_cache_top", "clone_files_modified_ex_cache",
                 "clone_git_bytes_written", "clone_git_files_created",
                 "git_index_bytes_written", "git_index_files_created", "tmp", "procs",
                 "tmp_entries_created", "procs_left", "procs_left_descendant",
                 "procs_snapshot_error", "git_objects_error",
                 "git_count_objects_delta", "git_size_kib_delta", "git_size_pack_kib_delta")


def test_probe_run_against_the_real_repo_banks_nothing_and_leaves_nothing(tmp_path):
    row = P.probe_run(ROOT, tag="pytest-integration", scratch_root=str(tmp_path))
    for col in ROW_COLUMNS:
        assert col in row, f"row is missing column {col}"
    assert row["schema_version"] == P.SCHEMA and row["record"] == "probe_run"
    assert len(row["head"]) == 40 and row["origin_removed"] is True
    assert [ph["phase"] for ph in row["phases"]] == [
        "session_start_hook", "wake_grade0", "bounded_act_reconstruct_node", "close_dry_run"]
    for ph in row["phases"]:
        for col in PHASE_COLUMNS:
            assert col in ph, f"phase {ph['phase']} is missing column {col}"
        assert set(ph["tmp"]) == set(row["watch_dirs"])
        assert "procs_left_descendant" in ph["procs"]
    for col in P.NUMERIC_COLUMNS:
        assert col in row["totals"]
    # the bounds and the caps are on the row, not buried in the source
    assert row["subprocess_timeout_s"] == P.DEFAULT_TIMEOUT_S
    assert row["bounds"] == P.derive_bounds(P.DEFAULT_TIMEOUT_S)
    assert set(row["evidence_caps"]) == {"top", "tail_bytes", "argv_chars"}
    assert row["spread_temperature"] == "cold-cold" and row["clone_per_iteration"] is True
    assert [c["origin_removed"] for c in row["clones"]] == [True]
    assert all(c["origin_remove_rc"] == 0 for c in row["clones"])
    assert all("origin" not in (c["remotes_after"] or []) for c in row["clones"])
    # the scratch tree is created by the probe and removed by it, always
    assert row["scratch_removed"] is True
    assert not Path(row["scratch"]).exists()
    assert list(tmp_path.iterdir()) == []
    # the row must be bankable as it stands
    json.dumps(row)


def test_snapshot_procs_does_not_report_its_own_ps_as_a_resident_process():
    """Two consecutive snapshots with nothing run between them must differ by nothing.

    The phantom this catches was real: ``ps`` lists itself, so before the fix every
    phase banked exactly one process left resident that was only the measurement.
    """
    before, err_b = P.snapshot_procs()
    after, err_a = P.snapshot_procs()
    assert err_b is None and err_a is None
    assert before and after
    d = P.diff_procs(before, after, ancestor=os.getpid())
    assert d["procs_left_descendant"] == 0


def _throwaway_repo(path: Path) -> Path:
    """A minimal committed git repo — enough to clone, not enough to be slow."""
    path.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "p", "GIT_AUTHOR_EMAIL": "p@x",
           "GIT_COMMITTER_NAME": "p", "GIT_COMMITTER_EMAIL": "p@x"}
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "f.txt").write_text("hello")
    subprocess.run(["git", "add", "f.txt"], cwd=path, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=path, check=True, env=env)
    return path


def test_repeat_clones_fresh_so_the_spread_is_cold_against_cold(tmp_path, monkeypatch):
    """--repeat N must measure N COLD trees, not one tree warmed by iteration 1.

    The defect this pins was real and silent: the phases were replayed inside a single
    clone, so iteration 2 wrote nothing (everything was already there) and the banked
    ``spread`` was a cold-vs-warm sequence wearing the name of a distribution.
    """
    repo = _throwaway_repo(tmp_path / "src")
    seen: list[str] = []

    def fake_iteration(clone, env_base, timeout, watch, bounds=None, caps=None):
        # a cold clone has never been touched by an earlier iteration
        assert not (Path(clone) / "WARM").exists(), "iteration ran in a warmed tree"
        (Path(clone) / "WARM").write_text("x")
        seen.append(str(clone))
        wrote = 0 if len(seen) > 1 else 0   # phase values are irrelevant here
        return [_fake_phase("only", 1.0 * len(seen), wrote)]

    monkeypatch.setattr(P, "_one_iteration", fake_iteration)
    row = P.probe_run(repo, tag="repeat", repeat=3, scratch_root=str(tmp_path))

    assert len(seen) == 3 and len(set(seen)) == 3, "every iteration needs its own clone"
    assert row["repeat"] == 3 and row["clone_per_iteration"] is True
    assert row["spread_temperature"] == "cold-cold"
    assert [c["iteration"] for c in row["clones"]] == [0, 1, 2]
    assert len(row["clone_wall_s_per_iteration"]) == 3
    assert len(row["totals_per_iteration"]) == 3
    assert row["spread"]["only"]["wall_s"]["n"] == 3
    assert row["scratch_removed"] is True


def test_origin_removed_is_checked_not_asserted(tmp_path):
    repo = _throwaway_repo(tmp_path / "src")
    dest = tmp_path / "clone"
    info = P._cold_clone(repo, dest, timeout=P.DEFAULT_TIMEOUT_S,
                         bounds=P.DEFAULT_BOUNDS, caps=P.EVIDENCE_CAPS)
    assert info["clone_rc"] == 0
    assert info["origin_remove_rc"] == 0
    assert info["origin_removed"] is True
    assert "origin" not in info["remotes_after"]
    # and the check is a real one: removing origin twice fails, and the row says so
    second = subprocess.run(["git", "remote", "remove", "origin"], cwd=dest,
                            capture_output=True, text=True)
    assert second.returncode != 0


def test_run_phase_gives_the_git_index_its_own_column(tmp_path):
    repo = _throwaway_repo(tmp_path / "r")
    ph = P.run_phase("touch_index", ["git", "add", "-A"], cwd=repo,
                     env={**P.cold_env(), "GIT_AUTHOR_NAME": "p"},
                     timeout=P.DEFAULT_TIMEOUT_S, watch_dirs=[])
    assert "git_index_bytes_written" in ph and "git_index_files_created" in ph
    assert ph["git_index_bytes_written"] >= 0
