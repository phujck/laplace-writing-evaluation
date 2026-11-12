"""legB-B3 — VERSION COMPARISON (design B13.4, the author's ruling 6).

Server-side coverage for the version-comparison surface: the banked-state
ENUMERATION (loop-pass git commits + snapshots + tags + release, lazy/uncached) and
the two-state ALIGNMENT at SECTION/PARAGRAPH grain (the fragment-stem + ``% <SEC>-pN``
idiom, word-diff inside a changed paragraph). The presets — candidate-vs-incumbent and
neutral-vs-voiced — resolve against the states that exist, or render disabled-with-reason.

Every fixture is a SYNTHETIC git repo in a temp dir with hand-made ``loop:`` commits —
the live corpus (mutated by a running A6 flow) is never read, and no test depends on
its current state. The one repo-root coupling (``rv._repo_root`` — the git cwd + the
``_rel`` base) is monkeypatched to the throwaway repo.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from laplace.manuscript import review_surface as rv
from laplace.web import review_http

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# a synthetic git repo with a marker-bearing manuscript + hand-made loop commits
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=False)


_N1_V1 = (
    "% PLAN:N1\n"
    "% NODES: def:alpha\n"
    "\\section{Introduction}\\label{sec:N1}\n"
    "\n% N1-p1\n"
    "The quick brown fox jumps over the lazy dog.\n"
    "\n% N1-p2\n"
    "The lazy dog sleeps here in the afternoon sun.\n"
)
# v2 edits ONLY N1-p2 (a word replaced + inserted) — N1-p1 is byte-identical
_N1_V2 = _N1_V1.replace(
    "The lazy dog sleeps here in the afternoon sun.",
    "The lazy dog sleeps soundly here in the warm afternoon sun.")

_N2 = (
    "% PLAN:N2\n"
    "\\section{Method}\\label{sec:N2}\n"
    "\n% N2-p1\n"
    "A steady method, unchanged across both versions of the manuscript.\n"
)

_MAIN = ("\\documentclass{article}\\begin{document}\n"
         "\\input{N1}\n\\input{N2}\n\\end{document}\n")


def _init_repo(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """A born git repo with a manuscript dir and one committed round. Returns
    ``(repo, md)`` and points ``rv._repo_root`` at the repo."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "work")
    _git(repo, "config", "user.email", "eigen@laplace.test")
    _git(repo, "config", "user.name", "Eigen Test")
    md = repo / "ms"
    md.mkdir()
    # seed WITHOUT N1.tex — the loop commits introduce/modify it, so each round is a
    # real (non-empty) commit rather than a silent no-op on unchanged bytes.
    (md / "main.tex").write_text(_MAIN, encoding="utf-8")
    (md / "N2.tex").write_text(_N2, encoding="utf-8")
    (md / "feedback").mkdir()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed manuscript")
    monkeypatch.setattr(rv, "_repo_root", lambda: repo)
    return repo, md


def _loop_commit(repo: Path, md: Path, label: str, *files: tuple[str, str]) -> str:
    """Write ``files`` and commit them as ``loop: <label> accepted incumbent``.
    Returns the commit sha; asserts a real (non-no-op) commit landed."""
    head_before = _git(repo, "rev-parse", "HEAD").stdout.strip()
    for rel, content in files:
        (md / rel).write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    r = _git(repo, "commit", "-q", "-m", f"loop: {label} accepted incumbent")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert head != head_before, f"loop commit {label!r} was a no-op: {r.stderr or r.stdout}"
    return head


# ---------------------------------------------------------------------------
# state enumeration
# ---------------------------------------------------------------------------

def test_enumerates_loop_commits_newest_first_with_what_changed(tmp_path, monkeypatch):
    repo, md = _init_repo(tmp_path, monkeypatch)
    _loop_commit(repo, md, "r1", ("N1.tex", _N1_V1), ("main.pdf", "PDF-A"))
    sha2 = _loop_commit(repo, md, "r2", ("N1.tex", _N1_V2), ("main.pdf", "PDF-B"))

    sts = rv.banked_states(md)
    kinds = [s["kind"] for s in sts]
    assert kinds[0] == "working"                     # the working candidate pins first
    loops = [s for s in sts if s["kind"] == "loop-pass"]
    assert [s["label"] for s in loops] == ["r2", "r1"]   # newest first
    top = loops[0]
    assert top["sha"] == sha2 and top["ref"] == {"kind": "git", "sha": sha2}
    assert top["resolvable"] is True
    # what_changed folds the commit's manuscript-relative files to a summary
    assert "N1.tex" in top["what_changed"]["files"]
    assert top["what_changed"]["pdf"] is True
    assert top["what_changed"]["sections"] == ["N1"]


def test_enumeration_is_lazy_new_commit_appears_uncached(tmp_path, monkeypatch):
    """A loop commit landing BETWEEN two calls (a running A6 flow) shows on the next —
    enumeration re-runs git every time, never cache-assumes."""
    repo, md = _init_repo(tmp_path, monkeypatch)
    _loop_commit(repo, md, "r1", ("N1.tex", _N1_V1))
    n_before = len([s for s in rv.banked_states(md) if s["kind"] == "loop-pass"])
    _loop_commit(repo, md, "r2", ("N1.tex", _N1_V2))
    n_after = len([s for s in rv.banked_states(md) if s["kind"] == "loop-pass"])
    assert n_after == n_before + 1


def test_states_route_200_and_404(tmp_path, monkeypatch):
    repo, md = _init_repo(tmp_path, monkeypatch)
    _loop_commit(repo, md, "r1", ("N1.tex", _N1_V1))
    monkeypatch.setattr(rv, "manuscript_dir", lambda *a, **k: md)
    st, _, body = review_http.handle("/review/states", {"dir": ["ms"]}, "GET", b"")
    assert st == 200
    data = json.loads(body)
    assert data["states"][0]["kind"] == "working"
    assert "presets" in data
    monkeypatch.setattr(rv, "manuscript_dir", lambda *a, **k: None)
    st2, _, _ = review_http.handle("/review/states", {"dir": ["nope"]}, "GET", b"")
    assert st2 == 404


# ---------------------------------------------------------------------------
# the presets
# ---------------------------------------------------------------------------

def test_candidate_vs_incumbent_available_neutral_vs_voiced_disabled(tmp_path, monkeypatch):
    repo, md = _init_repo(tmp_path, monkeypatch)
    _loop_commit(repo, md, "r1", ("N1.tex", _N1_V2))
    pre = rv.states(md)["presets"]
    avail = {p["id"]: p for p in pre["available"]}
    disabled = {p["id"]: p for p in pre["disabled_with_reason"]}
    assert "candidate-vs-incumbent" in avail
    # baseline (incumbent) on A, candidate (working) on B — old→new
    assert avail["candidate-vs-incumbent"]["b"] == "working"
    # incumbent falls back to the newest loop-pass commit (no snapshot on disk)
    assert avail["candidate-vs-incumbent"]["a"] != "working"
    # no voiced state banked -> disabled WITH a reason (honest, not a dead button)
    assert "neutral-vs-voiced" in disabled
    assert "voiced" in disabled["neutral-vs-voiced"]["reason"].lower()


def test_neutral_vs_voiced_lights_up_when_a_voice_pass_is_banked(tmp_path, monkeypatch):
    """A loop-pass labelled a voice pass marks the state voiced -> the preset resolves
    to (neutral predecessor, voiced) and becomes one-click."""
    repo, md = _init_repo(tmp_path, monkeypatch)
    _loop_commit(repo, md, "neutral-r1", ("N1.tex", _N1_V1))
    _loop_commit(repo, md, "voice-wash-r2", ("N1.tex", _N1_V2))   # 'voice' in the label
    sts = rv.banked_states(md)
    voiced = [s for s in sts if s.get("voiced")]
    assert len(voiced) == 1 and voiced[0]["label"] == "voice-wash-r2"
    pre = rv._presets(sts)
    avail = {p["id"]: p for p in pre["available"]}
    assert "neutral-vs-voiced" in avail
    nv = avail["neutral-vs-voiced"]
    assert sts[[s["id"] for s in sts].index(nv["b"])]["voiced"] is True
    # the neutral partner is the older, non-voiced predecessor
    assert nv["a"] != nv["b"]


# ---------------------------------------------------------------------------
# two-state alignment at section/paragraph grain
# ---------------------------------------------------------------------------

def test_two_state_alignment_changed_paragraph_shows_word_diff(tmp_path, monkeypatch):
    repo, md = _init_repo(tmp_path, monkeypatch)
    sha1 = _loop_commit(repo, md, "r1", ("N1.tex", _N1_V1))
    sha2 = _loop_commit(repo, md, "r2", ("N1.tex", _N1_V2))

    cmp = rv.compare(md, sha1, sha2)
    assert "error" not in cmp
    assert cmp["a"]["id"] == sha1 and cmp["b"]["id"] == sha2
    secs = {s["stem"]: s for s in cmp["sections"]}
    # N1 changed, N2 identical (collapses on the surface)
    assert secs["N1"]["changed"] is True and secs["N1"]["status"] == "changed"
    assert secs["N2"]["changed"] is False and secs["N2"]["status"] == "unchanged"
    # exactly N1-p2 changed; N1-p1 is 'same'; the section preamble is 'same'
    units = {u["pid"]: u for u in secs["N1"]["units"]}
    assert units["N1-p1"]["status"] == "same"
    assert units["N1-p2"]["status"] == "changed"
    # the machine-owned marker line is EXCLUDED from the compared prose
    assert "% N1-p2" not in units["N1-p2"]["a"] and "% N1-p2" not in units["N1-p2"]["b"]
    # the word-diff carries the inserted words, reconstructs each side exactly
    diff = units["N1-p2"]["diff"]
    assert "".join(seg["a"] for seg in diff) == units["N1-p2"]["a"]
    assert "".join(seg["b"] for seg in diff) == units["N1-p2"]["b"]
    inserted = "".join(seg["b"] for seg in diff if seg["op"] in ("insert", "replace"))
    assert "soundly" in inserted and "warm" in inserted
    # the tally + top-line counts agree
    assert secs["N1"]["tally"]["changed"] == 1
    assert cmp["counts"]["sections_changed"] == 1
    assert cmp["counts"]["paragraphs_changed"] == 1


def test_alignment_added_and_removed_paragraphs(tmp_path, monkeypatch):
    repo, md = _init_repo(tmp_path, monkeypatch)
    sha1 = _loop_commit(repo, md, "r1", ("N1.tex", _N1_V1))
    # r2 drops N1-p2 and adds N1-p3 (a paragraph add + remove, pids stable)
    n1_v3 = (_N1_V1.replace(
        "\n% N1-p2\nThe lazy dog sleeps here in the afternoon sun.\n", "\n")
        + "\n% N1-p3\nA brand new closing paragraph.\n")
    sha2 = _loop_commit(repo, md, "r2", ("N1.tex", n1_v3))
    cmp = rv.compare(md, sha1, sha2)
    units = {u["pid"]: u for u in next(s for s in cmp["sections"] if s["stem"] == "N1")["units"]}
    assert units["N1-p2"]["status"] == "removed" and units["N1-p2"]["b"] is None
    assert units["N1-p3"]["status"] == "added" and units["N1-p3"]["a"] is None
    assert cmp["counts"]["removed"] == 1 and cmp["counts"]["added"] == 1


def test_working_state_resolves_the_worktree(tmp_path, monkeypatch):
    """The working candidate resolves to the CURRENT (uncommitted) tree bytes, so a
    dirty edit compares against the last banked commit."""
    repo, md = _init_repo(tmp_path, monkeypatch)
    sha1 = _loop_commit(repo, md, "r1", ("N1.tex", _N1_V1))
    (md / "N1.tex").write_text(_N1_V2, encoding="utf-8")   # dirty, uncommitted
    cmp = rv.compare(md, sha1, "working")
    n1 = next(s for s in cmp["sections"] if s["stem"] == "N1")
    units = {u["pid"]: u for u in n1["units"]}
    assert units["N1-p2"]["status"] == "changed"
    assert "soundly" in units["N1-p2"]["b"]


def test_compare_route_200_and_422_on_unknown_and_unresolvable(tmp_path, monkeypatch):
    repo, md = _init_repo(tmp_path, monkeypatch)
    sha1 = _loop_commit(repo, md, "r1", ("N1.tex", _N1_V1))
    monkeypatch.setattr(rv, "manuscript_dir", lambda *a, **k: md)
    st, _, body = review_http.handle("/review/compare",
                            {"dir": ["ms"], "a": ["working"], "b": [sha1]}, "GET", b"")
    assert st == 200 and "error" not in json.loads(body)
    # an unknown state id -> 422 with a structured reason
    st2, _, body2 = review_http.handle("/review/compare",
                              {"dir": ["ms"], "a": ["working"], "b": ["deadbeef"]},
                              "GET", b"")
    assert st2 == 422 and json.loads(body2)["reason"] == "unknown-b"


# ---------------------------------------------------------------------------
# the alignment primitives (pure, no git)
# ---------------------------------------------------------------------------

def test_split_units_excludes_markers_and_keeps_preamble():
    units = rv._split_units(_N1_V1)
    d = dict(units)
    assert "§preamble" in d and "\\section{Introduction}" in d["§preamble"]
    assert d["N1-p1"] == "The quick brown fox jumps over the lazy dog."
    assert "% N1-p1" not in d["N1-p1"]


def test_split_units_markerless_fragment_is_one_whole_unit():
    units = rv._split_units("\\begin{figure}\\caption{hi}\\end{figure}\n")
    assert len(units) == 1 and units[0][0] == "§whole"


def test_word_diff_reconstructs_and_flags_change():
    segs = rv._word_diff("the cat sat", "the calm cat sat")
    assert "".join(s["a"] for s in segs) == "the cat sat"
    assert "".join(s["b"] for s in segs) == "the calm cat sat"
    assert any(s["op"] != "equal" for s in segs)


def test_align_units_same_when_identical():
    a = [("§preamble", "H"), ("N1-p1", "same body")]
    rows, tally = rv._align_units(a, list(a))
    assert tally == {"changed": 0, "added": 0, "removed": 0, "same": 2}
    assert all(r["status"] == "same" for r in rows)
