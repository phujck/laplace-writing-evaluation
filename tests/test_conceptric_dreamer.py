"""Tests for the conceptric dreamer (N26) - the recursive consolidating dreamer.

The reshape runs against a synthetic tmp repo (no git -> ``_tracked_files`` falls back to a tree
walk, so uncommitted concept files are visible immediately and ``commit=False`` is enough to measure
the collapse). The invariants under test: the proxy proposes a real concept, the lift wires the
orphans (width collapses), faithfulness holds, the SOUL is never clustered or leaked, and the
results gate rejects converged-but-wrong.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from laplace.engine import conceptric_dreamer as cd
from laplace.engine import self_shard


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A region 'area' of 12 orphan files: 4 cohesive 'widget reconstruction helper' files (a real
    concept) + 8 distinct singletons (residual). Plus a sealed soul fragment that must never cluster."""
    area = tmp_path / "area"
    area.mkdir(parents=True)
    for n in ("one", "two", "three", "four"):
        (area / f"widget_{n}.py").write_text(
            f'"""widget reconstruction helper {n}."""\n', encoding="utf-8"
        )
    for n in ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"):
        (area / f"{n}_singleton.py").write_text(
            f'"""the {n} singleton, standalone."""\n', encoding="utf-8"
        )
    soul = tmp_path / "soul"
    soul.mkdir()
    (soul / "secret.md").write_text("private widget reconstruction helper soul\n", encoding="utf-8")
    return tmp_path


def test_assess_proposes_a_real_concept(repo: Path):
    rep = cd.assess_conceptric("area", repo_root=repo)
    assert rep["nodes"] == 12  # soul excluded
    assert rep["orphans_before"] == 12  # nothing is wired yet
    assert rep["concepts_proposed"] >= 1
    top = rep["proposals"][0]
    # the cohesive cluster is exactly the four widget files
    assert sorted(top["members"]) == [f"area/widget_{n}.py" for n in ("four", "one", "three", "two")]
    assert top["coherence"] > 0.5


def test_lift_wires_the_orphans_width_collapses(repo: Path):
    before = cd.measure_width("area", repo_root=repo)
    rep = cd.assess_conceptric("area", repo_root=repo)
    res = cd.apply_reshape(repo, "area", rep, commit=False)
    after = cd.measure_width("area", repo_root=repo)

    assert res["forged"], "a coarse node should have been forged"
    assert (repo / "conceptric").is_dir()
    # the four widget orphans gained a parent; the eight singletons remain residual
    assert after["orphans"] == before["orphans"] - 4
    assert after["orphans"] == 8


def test_faithfulness_holds_after_the_reshape(repo: Path):
    rep = cd.assess_conceptric("area", repo_root=repo)
    cd.apply_reshape(repo, "area", rep, commit=False)
    fa = self_shard.shard_faithfulness(repo)
    assert fa["pass"], fa["issues"]


def test_soul_is_never_clustered_or_leaked(repo: Path):
    # the soul layer yields no proposals and no region nodes (it is sealed, never read)
    soul_rep = cd.assess_conceptric("soul", repo_root=repo)
    assert soul_rep["nodes"] == 0
    assert soul_rep["concepts_proposed"] == 0
    # and no proposal anywhere names a soul path
    area_rep = cd.assess_conceptric("area", repo_root=repo)
    for p in area_rep["proposals"]:
        assert not any(m.startswith("soul/") for m in p["members"])
    # forging does not break the soul seal
    cd.apply_reshape(repo, "area", area_rep, commit=False)
    fa = self_shard.shard_faithfulness(repo)
    assert not any("SOUL LEAK" in i for i in fa["issues"])


def test_certify_by_results_not_the_signal():
    before = {"orphans": 12}
    dropped = {"orphans": 8}
    same = {"orphans": 12}
    forged = [{"slug": "area-widget", "members": 4}]
    # the good case: faithful + orphans dropped
    assert cd._certify(before, dropped, True, forged) == (True, None)
    # converged-but-wrong: nothing was actually rescued
    ok, why = cd._certify(before, same, True, forged)
    assert ok is False and "did not drop" in why
    # a broken pointer / soul seal fails regardless of the proxy
    ok, why = cd._certify(before, dropped, False, forged)
    assert ok is False and "faithfulness" in why
    # every candidate carved -> nothing forged
    ok, why = cd._certify(before, same, True, [])
    assert ok is False and "forged" in why


def test_dream_conceptric_collapses_and_terminates(repo: Path):
    trace = cd.dream_conceptric(repo, "area", commit=False, max_grade=2)
    assert trace[0]["grade"] == 0
    assert trace[0]["certified"] is True
    assert trace[0]["orphans_rescued"] == 4
    assert trace[0]["faithfulness_pass"] is True
    # the recursion is bounded - it does not run away (one or two grades, coarsest last)
    assert len(trace) <= 3
    grades = [g["grade"] for g in trace]
    assert grades == sorted(grades)  # strictly increasing, coarsest last
