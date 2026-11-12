"""The selector proves itself — on a synthetic repo, where the right answer is known.

WO-20260820-test-what-moved. These tests are the reason `src/laplace/engine/suite_map.py` and
`scripts/suite_select.py` sit in the map's own ALWAYS_FULL set: a selector that could
select itself out of the run that catches its bugs is a selector with no floor.

The synthetic repo below is small enough to reason about by hand — one hub, one leaf, a
lazy chain, a data file, a scanning test — so every assertion here is a claim about the
*rule*, not about the live repository's shape.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from laplace.engine import suite_map as sm  # noqa: E402


@pytest.fixture
def synth(tmp_path: Path) -> Path:
    """A miniature repo: hard chain, lazy chain, a data file, a scanner."""
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "tests").mkdir()
    (root / "data").mkdir()

    (root / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    # leaf <- mid <- hub, all module-level (hard) edges
    (root / "src" / "pkg" / "leaf.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "src" / "pkg" / "mid.py").write_text(
        "from pkg.leaf import VALUE\n", encoding="utf-8")
    (root / "src" / "pkg" / "hub.py").write_text(
        "from pkg.mid import VALUE\n", encoding="utf-8")
    # a file that READS a data path but is imported by nobody at module scope
    (root / "src" / "pkg" / "reader.py").write_text(
        'def read(root):\n    return (root / "data/rows.jsonl").read_text()\n',
        encoding="utf-8")
    # a lazy chain: lazy1 -> lazy2 -> lazy3, each import inside a function
    for i, nxt in ((1, 2), (2, 3)):
        (root / "src" / "pkg" / f"lazy{i}.py").write_text(
            f"def go():\n    from pkg.lazy{nxt} import go as g\n    return g()\n",
            encoding="utf-8")
    (root / "src" / "pkg" / "lazy3.py").write_text(
        "def go():\n    return 3\n", encoding="utf-8")

    (root / "tests" / "conftest.py").write_text("", encoding="utf-8")
    (root / "tests" / "test_hub.py").write_text(
        "from pkg.hub import VALUE\n\ndef test_v():\n    assert VALUE == 1\n",
        encoding="utf-8")
    (root / "tests" / "test_reader.py").write_text(
        "from pkg import reader\n\ndef test_r():\n    assert reader\n", encoding="utf-8")
    (root / "tests" / "test_lazy.py").write_text(
        "from pkg.lazy1 import go\n\ndef test_g():\n    assert go() == 3\n",
        encoding="utf-8")
    (root / "tests" / "test_scan.py").write_text(
        'from pathlib import Path\n\n'
        'def test_all_docs():\n'
        '    assert list(Path(".").glob("*.md")) is not None\n', encoding="utf-8")
    (root / "data" / "rows.jsonl").write_text("{}\n", encoding="utf-8")
    (root / "NOTES.md").write_text("hi\n", encoding="utf-8")
    return root


def _sel(root: Path, moved: list[str]) -> dict:
    smap = sm.build_map(root)
    return sm.select(root, moved, smap)


# --------------------------------------------------------------------------- the map


def test_map_is_derived_not_hand_listed(synth: Path):
    """Every test file in the tree appears; the edges come from the source, not a list."""
    m = sm.build_map(synth)
    assert m["kind"] == "suite-shard-map" and m["version"] == sm.SCHEMA_VERSION
    assert set(m["tests"]) == {"tests/test_hub.py", "tests/test_reader.py",
                               "tests/test_lazy.py", "tests/test_scan.py"}
    assert m["files"]["src/pkg/hub.py"]["imp"] == ["src/pkg/mid.py"]
    # a function-local import is banked as lazy, never as hard
    assert m["files"]["src/pkg/lazy1.py"]["imp"] == []
    assert m["files"]["src/pkg/lazy1.py"]["lazy"] == ["src/pkg/lazy2.py"]


def test_transitive_hard_imports_reach_the_test(synth: Path):
    """test_hub -> hub -> mid -> leaf: a change to the leaf selects the test three hops up."""
    s = _sel(synth, ["src/pkg/leaf.py"])
    assert s["mode"] == "impacted"
    assert s["selected"] == ["tests/test_hub.py"]


def test_a_moved_test_file_selects_itself(synth: Path):
    s = _sel(synth, ["tests/test_scan.py"])
    assert s["selected"] == ["tests/test_scan.py"]
    assert "the test file itself moved" in s["reasons"]["tests/test_scan.py"][0]


def test_a_data_file_is_reached_by_the_path_literal(synth: Path):
    """reader.py never imports the data file — it NAMES it. That is the second edge."""
    s = _sel(synth, ["data/rows.jsonl"])
    assert s["mode"] == "impacted"
    assert "tests/test_reader.py" in s["selected"]


def test_a_glob_literal_catches_a_document_no_test_names(synth: Path):
    """The scanning test globs '*.md'; a brand-new .md nobody names still reaches it."""
    s = _sel(synth, ["NOTES.md"])
    assert s["mode"] == "impacted"
    assert s["selected"] == ["tests/test_scan.py"]


# ------------------------------------------------------------------- the lazy bound


def test_lazy_hops_are_bounded_and_the_bound_is_visible(synth: Path):
    """One lazy hop selects; two do not — the measured bound, asserted where it is set.

    This is the selector's ONE declared under-selection: a dependency reachable only
    through two or more conditional (function-local) imports. It is deliberate (the
    unbounded graph measured 138 of this repo's source files in one mutual blob reaching
    ~236 of 311 test files, i.e. no selection at all), and it is what the jubilee cadence
    exists to bound.
    """
    smap = sm.build_map(synth)
    rev = sm._reverse(smap)
    tests = set(smap["tests"])
    one = sm._tests_reaching(["src/pkg/lazy2.py"], rev, tests, 1)
    two = sm._tests_reaching(["src/pkg/lazy3.py"], rev, tests, 1)
    assert one == {"tests/test_lazy.py"}, "one lazy hop must still select"
    assert two == set(), "two lazy hops is the declared bound"
    assert sm._tests_reaching(["src/pkg/lazy3.py"], rev, tests, 99) == {"tests/test_lazy.py"}


# --------------------------------------------------------------------- the fail-open


def test_an_unclassified_path_forces_the_full_suite(synth: Path):
    s = _sel(synth, ["some/thing/nobody/knows.bin"])
    assert s["mode"] == "full"
    assert s["unclassified"] == ["some/thing/nobody/knows.bin"]
    assert "fail-open" in s["full_reasons"][0]


def test_conftest_forces_the_full_suite(synth: Path):
    s = _sel(synth, ["tests/conftest.py"])
    assert s["mode"] == "full"
    assert "always-full" in s["full_reasons"][0]


def test_the_selectors_own_machinery_forces_the_full_suite():
    """The selector may not select itself out of the run that would catch its bugs."""
    for own in ("src/laplace/engine/suite_map.py", "scripts/suite_select.py",
                "tests/test_suite_map.py", "pyproject.toml"):
        assert any(sm.fnmatch.fnmatch(own, g) for g in sm.ALWAYS_FULL), own


def test_a_test_file_the_map_predates_forces_the_full_suite(synth: Path):
    """A NEW test file cannot be in the banked map, and may collect anything."""
    smap = sm.build_map(synth)
    s = sm.select(synth, ["tests/test_brand_new.py"], smap)
    assert s["mode"] == "full"
    assert "predates" in s["full_reasons"][0]


def test_an_unknown_moved_set_forces_the_full_suite(synth: Path):
    """None is not an empty delta — it is an unknown one, and unknown means full."""
    smap = sm.build_map(synth)
    s = sm.select(synth, None, smap, failures=["git status: rc=128"])
    assert s["mode"] == "full"
    assert any("UNKNOWN" in r for r in s["full_reasons"])
    assert any("rc=128" in r for r in s["full_reasons"])


def test_first_party_code_no_test_reaches_is_reported_not_hidden(synth: Path):
    """An unreferenced source file selects nothing, and says so rather than passing silently."""
    (synth / "scripts" / "orphan.py").write_text("X = 1\n", encoding="utf-8")
    s = _sel(synth, ["scripts/orphan.py"])
    assert s["mode"] == "impacted" and s["selected"] == []
    assert s["uncovered"] == ["scripts/orphan.py"]


# --------------------------------------------------------- literals that carry no path


def test_information_free_globs_are_not_edges(synth: Path):
    """'*' / '**' / '**/*' name no path; treating them as edges selected everything.

    MEASURED on the live repo before this filter: a moved path no test knew of
    ('some/unknown/thing.bin') selected 254 of 311 test files, all of them through a bare
    '*' owned by a widely-reached module.
    """
    top = {"src", "tests", "data", "scripts"}
    for junk in ("*", "**", "**/*", "*.*", "***"):
        assert not sm._looks_like_path(junk, top), junk
    for real in ("*.md", "DESIGN_*.md", "corpus_friction/*.jsonl", "data/rows.jsonl"):
        assert sm._looks_like_path(real, top), real


def test_a_regex_literal_never_reaches_the_filesystem(synth: Path):
    """A regex that looks path-ish was stat'ed and raised PermissionError on /root/."""
    top = {"src", "tests"}
    assert not sm._looks_like_path(r"/root/\.ccr/[^\s]+", top)
    assert not sm._looks_like_path("/etc/passwd", top)
    assert not sm._looks_like_path("~/secrets.txt", top)
    assert not sm._is_repo_dir(synth, "../..")
    assert not sm._is_repo_dir(synth, "/etc")
    assert sm._is_repo_dir(synth, "src")


def test_a_directory_literal_matches_direct_children_only(synth: Path):
    """'src' as a literal must not mean 'every file anywhere under src/'."""
    dirs = {"src", "data"}
    assert sm._literal_hit("src/thing.py", "src", dirs)
    assert not sm._literal_hit("src/pkg/deep.py", "src", dirs)
    assert sm._literal_hit("data/rows.jsonl", "data/rows.jsonl", dirs)


# ------------------------------------------------------------------- the banked map


def test_the_map_rebuilds_when_the_code_moves(synth: Path):
    m1, why1 = sm.load_map(synth)
    assert why1.startswith("rebuilt")
    assert (synth / sm.MAP_REL).is_file()
    m2, why2 = sm.load_map(synth)
    assert why2.startswith("banked")
    assert m2["fingerprint"] == m1["fingerprint"]
    (synth / "src" / "pkg" / "leaf.py").write_text("VALUE = 2\nimport json\n", encoding="utf-8")
    _, why3 = sm.load_map(synth)
    assert "fingerprint moved" in why3


def test_the_banked_map_is_json_and_typed(synth: Path):
    sm.load_map(synth)
    m = json.loads((synth / sm.MAP_REL).read_text(encoding="utf-8"))
    assert m["record"] == "suite_map" and m["kind"] == "suite-shard-map"
    assert set(m["counts"]) >= {"tests", "first_party_files", "hard_edges", "lazy_edges"}


# ------------------------------------------------------------------- the instrument


def test_the_run_ledger_reads_back_the_last_green(synth: Path):
    sm.append_run(synth, {"record": "suite_run", "verdict": "green", "head": "aaa",
                          "chain_depth": 0})
    sm.append_run(synth, {"record": "suite_run", "verdict": "red", "head": "bbb"})
    sm.append_run(synth, {"record": "suite_run", "verdict": "green", "head": "ccc",
                          "chain_depth": 3})
    row = sm.last_green(synth)
    assert row["head"] == "ccc" and row["chain_depth"] == 3
    assert sm.last_green(synth / "nowhere") is None


def test_a_malformed_row_does_not_break_the_reader(synth: Path):
    (synth / sm.RUNS_REL).parent.mkdir(parents=True, exist_ok=True)
    (synth / sm.RUNS_REL).write_text('{"record": "suite_run", "verdict": "green", '
                                     '"head": "aaa"}\nnot json\n\n', encoding="utf-8")
    assert sm.last_green(synth)["head"] == "aaa"


def test_no_banked_green_means_the_full_suite(synth: Path):
    pl = sm.plan(synth)
    assert pl["mode"] == "full"
    assert "no banked green" in pl["full_reasons"][0]


def test_the_jubilee_cadence_re_grounds_the_chain(synth: Path):
    sm.append_run(synth, {"record": "suite_run", "verdict": "green", "head": "HEAD",
                          "chain_depth": sm.JUBILEE_EVERY})
    pl = sm.plan(synth)
    assert pl["mode"] == "full"
    assert "jubilee cadence" in pl["full_reasons"][0]


def test_a_near_total_selection_is_promoted_to_the_jubilee(synth: Path, monkeypatch):
    """Above the threshold an 'impacted' run is the full walk with partial-run paperwork."""
    monkeypatch.setattr(sm, "FULL_THRESHOLD", 0.5)
    sm.append_run(synth, {"record": "suite_run", "verdict": "green", "head": "HEAD",
                          "chain_depth": 0})
    # every test file in the synthetic tree reaches the conftest-free hub chain via '*.py'
    monkeypatch.setattr(sm, "moved_paths", lambda root, since: (["src/pkg/leaf.py",
                                                                 "data/rows.jsonl",
                                                                 "NOTES.md"], []))
    pl = sm.plan(synth)
    assert pl["mode"] == "full"
    assert "run it as the jubilee it already is" in pl["full_reasons"][0]
    assert pl["would_have_selected"] >= 3


def test_the_jubilee_override_is_full_whatever_moved(synth: Path):
    sm.append_run(synth, {"record": "suite_run", "verdict": "green", "head": "HEAD",
                          "chain_depth": 0})
    pl = sm.plan(synth, force_full=True)
    assert pl["mode"] == "full" and "jubilee was asked for" in pl["full_reasons"][0]


def test_an_untracked_directory_is_enumerated_not_collapsed(tmp_path: Path):
    """Bare `git status --porcelain` collapses an untracked directory to ONE entry with a
    trailing slash — a path form that matches no import edge and no path literal, so it
    fail-opens to the FULL suite by construction. MEASURED before the fix: 13/13 banked
    suite_run rows were mode=full, and every close that wrote an evidence directory paid
    the whole walk for files no test can reach. The delta must name the files.
    """
    root = tmp_path / "repo"
    (root / "evidence" / "AUDIT_2026").mkdir(parents=True)
    (root / "kept.txt").write_text("x\n", encoding="utf-8")
    for a in ("git", "init", "-q"), ("git", "add", "kept.txt"):
        subprocess.run(a, cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=root, check=True, capture_output=True)
    (root / "evidence" / "AUDIT_2026" / "report.md").write_text("r\n", encoding="utf-8")
    (root / "evidence" / "AUDIT_2026" / "census.py").write_text("x = 1\n", encoding="utf-8")

    moved, failures = sm.moved_paths(root, None)
    assert not failures
    assert "evidence/AUDIT_2026/" not in moved, "the directory was collapsed, not enumerated"
    assert {"evidence/AUDIT_2026/report.md",
            "evidence/AUDIT_2026/census.py"} <= set(moved)
