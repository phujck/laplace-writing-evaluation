"""The stage-corpus census (Wave 2E arming) — the script runs and emits valid JSON.

A tiny net: the census is stdlib-only and must run on any clone (cold, no venv), so
this loads it by path (it lives under ``scripts/`` with no package) and asserts its
output is well-formed and internally consistent — the demo pick is a subset of the
enumerated tex papers, the summary counts match the enumerated lists, and the schema
tag is present.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_SCRIPT = REPO / "scripts" / "census_stage_corpus.py"


def _load():
    spec = importlib.util.spec_from_file_location("census_stage_corpus", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(not _SCRIPT.is_file(), reason="census script absent")
def test_census_builds_and_is_consistent():
    mod = _load()
    census = mod.build_census(REPO)

    assert census["schema"] == "stage-corpus-census/0.1"
    s = census["summary"]
    # the enumerated lists agree with the summary counts
    assert s["papers_tex"] == len(census["papers_tex"])
    assert s["distillates"] == len(census["distillates"])
    assert s["physics_corpus"] == census["physics_corpus"]["count"]
    # lens arithmetic (5 FORM lenses)
    assert s["lens_reads_today"] == s["papers_tex"] * 5
    # the demo pick is a real subset of the tex papers, each with >= 2 sections
    ids = {p["paper_id"] for p in census["papers_tex"]}
    for d in census["demo_papers"]:
        assert d in ids
    by_id = {p["paper_id"]: p for p in census["papers_tex"]}
    for d in census["demo_papers"]:
        assert by_id[d]["sections"] >= 2
    # every tex paper carries the structural signal fields the design's richness uses
    for p in census["papers_tex"]:
        for f in ("sections", "subsections", "figures", "equations", "paragraphs_est", "richness"):
            assert isinstance(p[f], int)
    # source_kind is one of the two sanctioned tex homes — never anything else
    for p in census["papers_tex"]:
        assert p["source_kind"] in ("tex", "arxiv")
    # paper_id is unique across BOTH homes (voice_corpus/exemplars ∪ published_corpus/tex)
    ids_list = [p["paper_id"] for p in census["papers_tex"]]
    assert len(ids_list) == len(set(ids_list))


@pytest.mark.skipif(not _SCRIPT.is_file(), reason="census script absent")
def test_census_counts_published_corpus_tex_as_second_home(tmp_path):
    """published_corpus/tex/<paper_id>/ is a second sanctioned papers_tex home
    (source_kind "arxiv") alongside voice_corpus/exemplars ("tex") — the acquisition
    leg (scripts/acquire_paper_tex.py) writes there, and the census must count it."""
    mod = _load()
    fake_root = tmp_path / "repo"
    exemplars = fake_root / "voice_corpus" / "exemplars" / "already-had-tex"
    exemplars.mkdir(parents=True)
    (exemplars / "main.tex").write_text(
        "\\section{Intro}\nSome paragraph text that is long enough to count as prose here.\n",
        encoding="utf-8",
    )
    acquired = fake_root / "published_corpus" / "tex" / "fetched-from-arxiv"
    acquired.mkdir(parents=True)
    (acquired / "main.tex").write_text(
        "\\section{Intro}\n\\section{Method}\nAnother paragraph long enough to count as prose here too.\n",
        encoding="utf-8",
    )

    papers = mod.census_papers_tex(fake_root)
    by_id = {p["paper_id"]: p for p in papers}
    assert set(by_id) == {"already-had-tex", "fetched-from-arxiv"}
    assert by_id["already-had-tex"]["source_kind"] == "tex"
    assert by_id["fetched-from-arxiv"]["source_kind"] == "arxiv"


@pytest.mark.skipif(not _SCRIPT.is_file(), reason="census script absent")
def test_census_writes_valid_json(tmp_path):
    mod = _load()
    out = tmp_path / "census.json"
    rc = mod.main(["--repo-root", str(REPO), "--out", str(out), "--quiet"])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema"] == "stage-corpus-census/0.1"
    assert "summary" in data and "papers_tex" in data
