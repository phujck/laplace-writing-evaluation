"""Tests for tests_at_grade - the test shard for what changed (the at-grade probe's dirty branch).

The mapping is tested with explicit ``changed`` sets so it is pure (no git): a clean tree inherits,
a source module pulls its own test plus the cross-cutting ripple, a changed test pulls itself, an
untested source change is surfaced (never silently passed), and non-source files map to nothing.

The git read has its own tests with a faked ``subprocess.run``: a git that does not answer must be
distinguishable from a clean tree, all the way out to the exit code.
"""

from __future__ import annotations

import pytest

from laplace.engine import tests_at_grade as tag


@pytest.fixture()
def tree(tmp_path):
    (tmp_path / "src" / "laplace" / "pipeline").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    for mod in ("widget", "canon", "lonely"):
        (tmp_path / "src" / "laplace" / f"{mod}.py").write_text("x = 1\n", encoding="utf-8")
    # widget has its own test; canon has its own test AND is imported by another (cross-cutting)
    (tmp_path / "tests" / "test_widget.py").write_text(
        "from laplace.widget import x\n", encoding="utf-8")
    (tmp_path / "tests" / "test_canon.py").write_text(
        "from laplace.pipeline.canon import x\n", encoding="utf-8")
    (tmp_path / "tests" / "test_router.py").write_text(
        "from laplace.pipeline.canon import x  # depends on canon\n", encoding="utf-8")
    # 'lonely' has no test at all

    # subpackage module: own-test resolution is by the LAST segment, not the dotted tail
    for mod in ("growth_adjudicator", "lonely_sub"):
        (tmp_path / "src" / "laplace" / "pipeline" / f"{mod}.py").write_text(
            "x = 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_growth_adjudicator.py").write_text(
        "from laplace.pipeline.growth_adjudicator import x\n", encoding="utf-8")
    # 'pipeline/lonely_sub' has no test at all

    # script module: own-test resolution mirrors flat modules; importer needle is "<name>.py",
    # the spec_from_file_location loader idiom (see tests/test_deslop_gate.py)
    for name in ("gizmo", "lonely_script"):
        (tmp_path / "scripts" / f"{name}.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_gizmo.py").write_text(
        "import importlib.util\n"
        "spec = importlib.util.spec_from_file_location('gizmo', 'scripts/gizmo.py')\n",
        encoding="utf-8")
    # 'lonely_script' has no test at all
    return tmp_path


def test_clean_tree_inherits(tree):
    rep = tag.test_shard(tree, changed=[])
    assert rep["inherit"] is True
    assert rep["shard"] == []


def test_source_change_pulls_own_test(tree):
    rep = tag.test_shard(tree, changed=["src/laplace/widget.py"])
    assert rep["shard"] == ["tests/test_widget.py"]
    assert rep["inherit"] is False


def test_cross_cutting_module_pulls_every_importer(tree):
    rep = tag.test_shard(tree, changed=["src/laplace/pipeline/canon.py"])
    # its own test AND the test that imports it
    assert rep["shard"] == ["tests/test_canon.py", "tests/test_router.py"]
    assert rep["untested_changes"] == []


def test_changed_test_file_runs_itself(tree):
    rep = tag.test_shard(tree, changed=["tests/test_widget.py"])
    assert rep["shard"] == ["tests/test_widget.py"]


def test_untested_source_change_is_surfaced_not_swallowed(tree):
    rep = tag.test_shard(tree, changed=["src/laplace/lonely.py"])
    assert rep["shard"] == []
    assert rep["untested_changes"] == ["src/laplace/lonely.py"]


def test_docs_and_config_map_to_nothing(tree):
    rep = tag.test_shard(tree, changed=["HANDOFF.md", ".claude/settings.json"])
    assert rep["shard"] == []
    assert rep["untested_changes"] == []   # not source, so not a gap


def test_dedupes_when_module_and_its_test_both_change(tree):
    rep = tag.test_shard(tree, changed=["src/laplace/widget.py", "tests/test_widget.py"])
    assert rep["shard"] == ["tests/test_widget.py"]


def test_flat_module_behavior_is_unchanged(tree):
    # the flat-module path is the dotted-tail == last-segment case; must resolve exactly as before
    rep = tag.test_shard(tree, changed=["src/laplace/widget.py"])
    assert rep["shard"] == ["tests/test_widget.py"]
    assert rep["untested_changes"] == []


def test_pipeline_module_change_resolves_to_its_shard(tree):
    # subpackage module: own-test resolution is by the LAST segment (growth_adjudicator),
    # not the dotted tail (pipeline.growth_adjudicator)
    rep = tag.test_shard(tree, changed=["src/laplace/pipeline/growth_adjudicator.py"])
    assert rep["shard"] == ["tests/test_growth_adjudicator.py"]
    assert rep["untested_changes"] == []


def test_script_change_resolves_to_its_shard(tree):
    rep = tag.test_shard(tree, changed=["scripts/gizmo.py"])
    assert rep["shard"] == ["tests/test_gizmo.py"]
    assert rep["untested_changes"] == []


def test_unmatched_pipeline_module_still_surfaced_as_untested(tree):
    rep = tag.test_shard(tree, changed=["src/laplace/pipeline/lonely_sub.py"])
    assert rep["shard"] == []
    assert rep["untested_changes"] == ["src/laplace/pipeline/lonely_sub.py"]


def test_unmatched_script_still_surfaced_as_untested(tree):
    rep = tag.test_shard(tree, changed=["scripts/lonely_script.py"])
    assert rep["shard"] == []
    assert rep["untested_changes"] == ["scripts/lonely_script.py"]


# ---- the git read: "git did not answer" is not "nothing changed" ----

class _Answer:
    """Stand-in for subprocess.run's CompletedProcess — rc plus the two streams."""

    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_git(monkeypatch, answer=None, raises=None):
    def run(cmd, *a, **kw):
        if raises is not None:
            raise raises
        return answer
    monkeypatch.setattr(tag.subprocess, "run", run)


def test_git_answering_parses_the_changed_set(tree, monkeypatch):
    _fake_git(monkeypatch, _Answer(0, " M src/laplace/widget.py\0?? tests/test_widget.py\0"))
    rep = tag.test_shard(tree)
    assert rep["changed"] == ["src/laplace/widget.py", "tests/test_widget.py"]
    assert rep["shard"] == ["tests/test_widget.py"]
    assert rep["inherit"] is False
    assert rep["git_unreadable"] == ""


def test_read_clean_tree_still_inherits(tree, monkeypatch):
    _fake_git(monkeypatch, _Answer(0, ""))
    rep = tag.test_shard(tree)
    assert rep["inherit"] is True
    assert rep["git_unreadable"] == ""


def test_nonzero_git_is_unreadable_not_clean(tree, monkeypatch):
    _fake_git(monkeypatch, _Answer(128, "", "fatal: not a git repository\n"))
    rep = tag.test_shard(tree)
    assert rep["changed"] == []
    assert rep["inherit"] is False           # the tree was never read, so nothing is inherited
    assert "128" in rep["git_unreadable"]
    assert "not a git repository" in rep["git_unreadable"]


def test_failed_git_spawn_is_unreadable_not_clean(tree, monkeypatch):
    _fake_git(monkeypatch, raises=OSError("no such file: git"))
    rep = tag.test_shard(tree)
    assert rep["inherit"] is False
    assert "no such file: git" in rep["git_unreadable"]


def test_git_timeout_is_unreadable_not_clean(tree, monkeypatch):
    _fake_git(monkeypatch, raises=tag.subprocess.TimeoutExpired(["git", "status"], 30))
    rep = tag.test_shard(tree)
    assert rep["inherit"] is False
    assert rep["git_unreadable"]


def test_explicit_changed_never_consults_git(tree, monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("an explicit changed set must not shell out to git")
    monkeypatch.setattr(tag.subprocess, "run", forbidden)
    rep = tag.test_shard(tree, changed=[])
    assert rep["inherit"] is True
    assert rep["git_unreadable"] == ""


def test_run_refuses_to_inherit_when_git_is_unreadable(monkeypatch, capsys):
    monkeypatch.setattr(tag, "test_shard", lambda root: {
        "changed": [], "shard": [], "untested_changes": [],
        "inherit": False, "git_unreadable": "git status exited 128: fatal: not a git repository",
    })
    rc = tag.main(["--run"])
    out = capsys.readouterr().out
    assert rc != 0                                  # a caller reading the code can tell
    assert "git unreadable" in out
    assert "inheriting the last banked-green verdict" not in out


def test_run_still_inherits_on_a_read_clean_tree(monkeypatch, capsys):
    monkeypatch.setattr(tag, "test_shard", lambda root: {
        "changed": [], "shard": [], "untested_changes": [],
        "inherit": True, "git_unreadable": "",
    })
    rc = tag.main(["--run"])
    assert rc == 0
    assert "inheriting the last banked-green verdict" in capsys.readouterr().out
