"""legB23-judge — ADVERSARIAL probes for legB-B2 (action rail + edit-in-place,
commit 4141ba4) and legB-B3 (version comparison, commit 7d3e12f).

Written by a FRESH judge who did NOT build the surface: the intent is to REFUTE the
B-2/B-3 claims, not to re-affirm them. Every fixture is a throwaway temp tree or a
SYNTHETIC git repo in a temp dir (``rv._repo_root`` monkeypatched) — the live SSG
ledger, tex and git history (mutated by a running A6 flow) are never touched.

Only PASSING probes live here; a probe that would need a code change is captured as a
FINDING in the judge verdict, not asserted as if it were correct. Where a behaviour is
merely a defensible limitation (a moved paragraph read as add+remove) the probe pins
the OBSERVED behaviour and says so.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from laplace.manuscript import review_surface as rv
from laplace.pipeline.ledger import read_jsonl

pytestmark = pytest.mark.unit


# ===========================================================================
# fixtures
# ===========================================================================

_N1 = (
    "% PLAN:N1\n"
    "% NODES: def:alpha\n"
    "\\section{Introduction}\\label{sec:N1}\n"
    "\n% N1-p1\n"
    "The quick brown fox jumps over the lazy dog.\n"
    "\n% N1-p2\n"
    "The lazy dog sleeps here in the afternoon sun.\n"
)
_MAIN = ("\\documentclass{article}\\begin{document}\n"
         "\\input{N1}\n\\input{N2}\n\\end{document}\n")
_N2 = ("% PLAN:N2\n\\section{Method}\\label{sec:N2}\n"
       "\n% N2-p1\nA steady method, unchanged across both versions.\n")


def _md(tmp_path: Path, n1: str = _N1) -> Path:
    md = tmp_path / "ms"
    md.mkdir(parents=True)
    (md / "main.tex").write_text(_MAIN, encoding="utf-8")
    (md / "N1.tex").write_text(n1, encoding="utf-8")
    (md / "N2.tex").write_text(_N2, encoding="utf-8")
    (md / "feedback").mkdir()
    return md


def _ledger(md: Path) -> list[dict]:
    p = md / "feedback" / "feedback.jsonl"
    return read_jsonl(p) if p.is_file() else []


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=False)


def _init_repo(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "work")
    _git(repo, "config", "user.email", "eigen@laplace.test")
    _git(repo, "config", "user.name", "Eigen Test")
    md = repo / "ms"
    md.mkdir()
    (md / "main.tex").write_text(_MAIN, encoding="utf-8")
    (md / "N2.tex").write_text(_N2, encoding="utf-8")
    (md / "feedback").mkdir()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed manuscript")
    monkeypatch.setattr(rv, "_repo_root", lambda: repo)
    return repo, md


def _loop_commit(repo: Path, md: Path, label: str, *files) -> str:
    for rel, content in files:
        (md / rel).write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"loop: {label} accepted incumbent")
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


_N1_V1 = (
    "% PLAN:N1\n\\section{Introduction}\\label{sec:N1}\n"
    "\n% N1-p1\nThe quick brown fox jumps over the lazy dog.\n"
    "\n% N1-p2\nThe lazy dog sleeps here in the afternoon sun.\n"
)
_N1_V2 = _N1_V1.replace(
    "The lazy dog sleeps here in the afternoon sun.",
    "The lazy dog sleeps soundly here in the warm afternoon sun.")


# ===========================================================================
# GROUP A — the edit-in-place ORGAN drives edits.py, boundary enforced server-side
# ===========================================================================

def test_A1_clean_edit_splices_disk_and_banks_exactly_one(tmp_path):
    """A clean edit in an unprotected span: bytes change on disk AND exactly one
    protection record banks — the write path IS the bank (not optional)."""
    md = _md(tmp_path)
    fp = md / "N1.tex"
    before_prose = "The lazy dog sleeps here in the afternoon sun."
    res = rv.adjudicate(md, "proj", {
        "by": "author", "verb": "edit-in-place", "section": "N1", "paragraph": "N1-p2",
        "before": before_prose, "after": "The lazy dog dozes in the sun."})
    assert res.get("ok") is True, res
    assert "The lazy dog dozes in the sun." in fp.read_text(encoding="utf-8")
    assert "% N1-p2" in fp.read_text(encoding="utf-8")     # marker survived
    led = _ledger(md)
    assert len(led) == 1 and led[0].get("record") in ("author-edit", "edit")


def test_A2_marker_mint_is_refused_zero_bytes_zero_banked(tmp_path):
    """An edit whose `after` would MINT a `% <SEC>-pN` marker is refused by the ORGAN
    (server), file+reason surfaced, and it touches ZERO bytes / banks ZERO records."""
    md = _md(tmp_path)
    fp = md / "N1.tex"
    pre_sha, pre_led = _sha(fp), len(_ledger(md))
    res = rv.adjudicate(md, "proj", {
        "by": "author", "verb": "edit-in-place", "section": "N1", "paragraph": "N1-p2",
        "before": "The lazy dog sleeps here in the afternoon sun.",
        "after": "The lazy dog sleeps.\n% N1-p3\nA smuggled new unit."})
    assert res.get("ok") is not True
    assert res.get("reason") == "marker-mutation"
    assert res.get("file") and res.get("file").endswith("N1.tex")   # file named
    assert _sha(fp) == pre_sha                              # ZERO bytes changed
    assert len(_ledger(md)) == pre_led                      # ZERO banked


def test_A3_marker_delete_via_whole_fragment_is_refused(tmp_path):
    """A whole-fragment edit that DELETES an existing marker line is refused — the
    grain machinery's markers are machine-owned, an edit can never destroy one."""
    md = _md(tmp_path)
    fp = md / "N1.tex"
    raw = fp.read_text(encoding="utf-8")
    pre_sha, pre_led = _sha(fp), len(_ledger(md))
    # a whole-fragment splice whose `before` spans the % N1-p2 marker and drops it
    res = rv.adjudicate(md, "proj", {
        "by": "author", "verb": "edit-in-place", "section": "N1", "paragraph": "",
        "before": "% N1-p2\nThe lazy dog sleeps here in the afternoon sun.",
        "after": "The lazy dog sleeps here in the afternoon sun."})
    assert res.get("ok") is not True and res.get("reason") == "marker-mutation"
    assert _sha(fp) == pre_sha and len(_ledger(md)) == pre_led


def test_A4_absent_and_ambiguous_before_refused_no_write(tmp_path):
    """`before` must occur EXACTLY once: 0 → absent, >1 → ambiguous; neither writes."""
    md = _md(tmp_path)
    fp = md / "N1.tex"
    pre_sha = _sha(fp)
    absent = rv.adjudicate(md, "proj", {
        "by": "author", "verb": "edit-in-place", "section": "N1", "paragraph": "N1-p2",
        "before": "text that is simply not present", "after": "x"})
    assert absent.get("reason") == "absent" and absent.get("file")
    # duplicate the target word so `before` occurs twice in the span
    dup = _N1.replace("The lazy dog sleeps here in the afternoon sun.",
                      "sun sun.")
    md2 = _md(tmp_path / "b", n1=dup)
    amb = rv.adjudicate(md2, "proj", {
        "by": "author", "verb": "edit-in-place", "section": "N1", "paragraph": "N1-p2",
        "before": "sun", "after": "moon"})
    assert amb.get("reason") == "ambiguous" and amb.get("count") == 2
    assert _sha(fp) == pre_sha and _ledger(md) == []


def test_A5_file_param_is_fenced_no_path_traversal(tmp_path):
    """A hand-crafted API call passing a malicious `file` cannot escape the manuscript
    dir — the organ fences it (relative_to md) and degrades to a no-fragment refusal,
    never reading/writing outside the tree. Defense-in-depth (the client never sends
    `file`, but the route accepts it)."""
    md = _md(tmp_path)
    secret = tmp_path / "secret.tex"
    secret.write_text("TOP SECRET — outside the manuscript\n", encoding="utf-8")
    for evil in ("../secret.tex", "../../etc/passwd", str(secret.resolve()),
                 "/etc/passwd"):
        res = rv.adjudicate(md, "proj", {
            "by": "author", "verb": "edit-in-place", "section": "N1", "paragraph": "",
            "file": evil, "before": "TOP SECRET", "after": "pwned"})
        assert res.get("ok") is not True, (evil, res)
        assert res.get("reason") == "no-fragment", (evil, res)
    assert "pwned" not in secret.read_text(encoding="utf-8")   # untouched


def test_A6_terminal_reedit_is_NOT_refused_by_organ_documented(tmp_path):
    """DESIGN NOTE (not a defect): terminal protection is the AUTHOR's authority, so
    the organ does NOT refuse the author re-editing their own terminal span. The lock
    is INFORMATIONAL on the surface; the ENFORCED refusals are marker-mutation + the
    non-unique match. This probe pins that observed contract so a future 'lock should
    block the author' regression is caught as an intent change."""
    md = _md(tmp_path)
    r1 = rv.adjudicate(md, "proj", {
        "by": "author", "verb": "edit-in-place", "section": "N1", "paragraph": "N1-p2",
        "before": "The lazy dog sleeps here in the afternoon sun.",
        "after": "The lazy dog rests."})
    assert r1.get("ok") is True
    fv = rv.fragment_view(md, "", "N1-p2")
    assert fv["protected"] is True                          # now locked (informational)
    r2 = rv.adjudicate(md, "proj", {                        # re-edit the terminal span
        "by": "author", "verb": "edit-in-place", "section": "N1", "paragraph": "N1-p2",
        "before": "The lazy dog rests.", "after": "The lazy dog rests soundly."})
    assert r2.get("ok") is True                             # allowed, by design
    assert "rests soundly" in (md / "N1.tex").read_text(encoding="utf-8")


# ===========================================================================
# GROUP B — ANCHOR HONESTY: never a silent wrong anchor, never a fabricated one
# ===========================================================================

def test_B1_fragment_view_unknown_section_is_honest_refusal(tmp_path):
    md = _md(tmp_path)
    fv = rv.fragment_view(md, "N9", "")
    assert fv["ok"] is False and fv["reason"] == "no-fragment"


def test_B2_fragment_view_unresolvable_pid_is_no_paragraph_not_fabricated(tmp_path):
    """A pid that does not resolve to a marker → honest 'no-paragraph' (file named),
    NEVER a fabricated span."""
    md = _md(tmp_path)
    fv = rv.fragment_view(md, "", "N1-p99")
    assert fv["ok"] is False and fv["reason"] == "no-paragraph"
    assert fv["section"] == "N1" and fv["file"].endswith("N1.tex")
    assert "before" not in fv and "text" not in fv          # nothing fabricated


def test_B3_section_grain_is_visibly_coarse_and_targets_the_beat(tmp_path):
    md = _md(tmp_path)
    fv = rv.fragment_view(md, "N1", "")
    assert fv["ok"] is True and fv["coarse"] is True and fv["grain"] == "section"
    assert fv["paragraph"] == "N1-p1"                       # the section's first beat
    assert fv["text"].startswith("The quick brown fox")


def test_B4_section_first_para_picks_lowest_ordinal_unordered(tmp_path):
    """`_section_first_para` picks the LOWEST -pN regardless of dict order, and returns
    None (no fabrication) when the section has no mapped paragraph."""
    entries = {"N1-p7": [], "N1-p2": [], "N1-p10": [], "N2-p1": []}
    assert rv._section_first_para(entries, "N1") == "N1-p2"
    assert rv._section_first_para(entries, "NX") is None


def test_B5_findings_section_anchor_fallback_and_no_fabrication(tmp_path, monkeypatch):
    """An unanchored finding carrying a section but no mapped node gets the section's
    coarse BEAT; a finding whose section has no beat gets NO section_anchor (honest).
    The findings are banked through the REAL feedback door (the comment verb)."""
    md = _md(tmp_path)
    nm = {"present": True, "fresh": True,
          "entries": {"N1-p1": [{"page": 3}], "N1-p2": [{"page": 3}]},
          "coverage": {}}
    monkeypatch.setattr(rv, "nodemap_state", lambda _md: nm)
    # a section-anchored comment (node_id = the section 'N1', not a conceptric node) →
    # surfaces as an UNANCHORED, section-keyed finding
    r1 = rv.adjudicate(md, "proj", {"by": "author", "verb": "comment", "section": "N1",
                                    "comment": "unanchored but sectioned"})
    assert r1.get("ok") is True, r1
    r2 = rv.adjudicate(md, "proj", {"by": "author", "verb": "comment", "section": "NZ",
                                    "comment": "no beat anywhere"})
    assert r2.get("ok") is True, r2
    out = rv.findings(md, "proj")
    by_sec = {f.get("section"): f for f in out["unanchored"]}
    assert "N1" in by_sec and "NZ" in by_sec
    assert by_sec["N1"]["section_anchor"] == {
        "node": "N1-p1", "coarse": True, "page": 3}          # coarse beat, marked
    assert "section_anchor" not in by_sec["NZ"]             # NOT fabricated


# ===========================================================================
# GROUP C — STATE ENUMERATION + LAZINESS
# ===========================================================================

def test_C1_enumerates_all_kinds_with_correct_what_changed(tmp_path, monkeypatch):
    repo, md = _init_repo(tmp_path, monkeypatch)
    _loop_commit(repo, md, "r1", ("N1.tex", _N1_V1), ("main.pdf", "PDF-A"))
    sha2 = _loop_commit(repo, md, "r2", ("N1.tex", _N1_V2))
    _git(repo, "tag", "v1-milestone", sha2)
    # a candidate_lock snapshot
    snap = md / "rounds" / "incumbent_r3"
    snap.mkdir(parents=True)
    (snap / "N1.tex").write_text(_N1_V1, encoding="utf-8")
    (snap / "SNAPSHOT.json").write_text(json.dumps(
        {"round": 3, "ts": "2026-07-10_090000"}), encoding="utf-8")

    sts = rv.banked_states(md)
    kinds = {s["kind"] for s in sts}
    assert {"working", "loop-pass", "incumbent", "tag"} <= kinds
    loops = [s for s in sts if s["kind"] == "loop-pass"]
    assert [s["label"] for s in loops] == ["r2", "r1"]      # newest first
    r2 = loops[0]
    assert r2["what_changed"]["sections"] == ["N1"]
    assert r2["what_changed"]["pdf"] is False               # r2 did not touch the pdf
    r1 = loops[1]
    assert r1["what_changed"]["pdf"] is True and "N1.tex" in r1["what_changed"]["files"]
    tag = next(s for s in sts if s["kind"] == "tag")
    assert tag["label"] == "v1-milestone" and tag["sha"] == sha2


def test_C2_lazy_new_commit_appears_no_stale_cache(tmp_path, monkeypatch):
    repo, md = _init_repo(tmp_path, monkeypatch)
    _loop_commit(repo, md, "r1", ("N1.tex", _N1_V1))
    n_before = len([s for s in rv.banked_states(md) if s["kind"] == "loop-pass"])
    _loop_commit(repo, md, "r2", ("N1.tex", _N1_V2))       # lands mid-session
    n_after = len([s for s in rv.banked_states(md) if s["kind"] == "loop-pass"])
    assert n_after == n_before + 1                          # uncached: the new one shows


def test_C3_only_tags_whose_own_commit_touches_the_manuscript(tmp_path, monkeypatch):
    """FND-2 FIXED: `_tag_states` now filters by the TOUCHED FILES of the tagged commit
    itself (``git show --name-only``), not ancestry (``git log <sha> -- <md>``):
      * a tag on a commit BEFORE the manuscript existed is EXCLUDED (as before);
      * a tag ON the manuscript commit is INCLUDED (its commit touches ms/);
      * a tag on a LATER DOCS-ONLY commit — whose ancestry merely CONTAINS a manuscript
        commit but whose OWN commit touches no manuscript file — is now EXCLUDED. The
        old ancestry test wrongly enumerated it as a manuscript version.
    This is the docstring's honest reading: 'tags whose commit touches this manuscript'.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "work")
    _git(repo, "config", "user.email", "eigen@laplace.test")
    _git(repo, "config", "user.name", "Eigen Test")
    (repo / "README.md").write_text("pre-manuscript\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "pre-manuscript")
    _git(repo, "tag", "pre-tag")                            # BEFORE the manuscript
    md = repo / "ms"
    md.mkdir()
    (md / "feedback").mkdir()
    (md / "main.tex").write_text(_MAIN, encoding="utf-8")
    (md / "N1.tex").write_text(_N1_V1, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "loop: r1 accepted incumbent")
    _git(repo, "tag", "ms-tag")                             # ON the manuscript commit
    (repo / "DOCS.md").write_text("docs\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "docs only")
    _git(repo, "tag", "docs-tag")                           # AFTER, docs-only commit
    # a LATER manuscript commit + tag: its own commit DOES touch ms/, so it stays in
    _git(repo, "tag", "docs-tag2")                          # second docs-only alias tag
    (md / "N1.tex").write_text(_N1_V2, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "loop: r2 accepted incumbent")
    _git(repo, "tag", "ms-tag2")                            # ON a later manuscript commit
    monkeypatch.setattr(rv, "_repo_root", lambda: repo)
    tags = [s["label"] for s in rv.banked_states(md) if s["kind"] == "tag"]
    assert "pre-tag" not in tags                            # correctly excluded
    assert "ms-tag" in tags                                 # commit touches ms/
    assert "ms-tag2" in tags                                # later commit ALSO touches ms/
    assert "docs-tag" not in tags                           # FND-2: docs-only, now excluded
    assert "docs-tag2" not in tags                          # docs-only alias, excluded


def test_C4_release_is_pdf_only_honest_unresolvable(tmp_path, monkeypatch):
    repo, md = _init_repo(tmp_path, monkeypatch)
    _loop_commit(repo, md, "r1", ("N1.tex", _N1_V1))
    rel = md / "release"
    rel.mkdir()
    (rel / "finalize.json").write_text(json.dumps(
        {"slug": "no-such-tag-slug", "created": "2026-07-10_100000",
         "pdf_path": "no-such-tag-slug.pdf", "revision": 2}), encoding="utf-8")
    st = next(s for s in rv.banked_states(md) if s["kind"] == "release")
    assert st["resolvable"] is False and "unresolvable_reason" in st
    # and compare against it fails SAFE (422 with the reason), never crashes
    res = rv.compare(md, st["id"], "working")
    assert "error" in res and res["reason"].startswith("unresolvable")


# ===========================================================================
# GROUP D — COMPARE ALIGNMENT + WORD-DIFF
# ===========================================================================

def _two_state_repo(tmp_path, monkeypatch, va, vb):
    repo, md = _init_repo(tmp_path, monkeypatch)
    a = _loop_commit(repo, md, "ra", ("N1.tex", va))
    b = _loop_commit(repo, md, "rb", ("N1.tex", vb))
    return md, a, b


def test_D1_edited_paragraph_is_changed_with_word_diff(tmp_path, monkeypatch):
    md, a, b = _two_state_repo(tmp_path, monkeypatch, _N1_V1, _N1_V2)
    cmp = rv.compare(md, a, b)
    n1 = next(s for s in cmp["sections"] if s["stem"] == "N1")
    assert n1["changed"] is True
    changed = [u for u in n1["units"] if u["status"] == "changed"]
    assert [u["pid"] for u in changed] == ["N1-p2"]
    ins = [seg["b"] for seg in changed[0]["diff"] if seg["op"] in ("insert", "replace")]
    assert any("soundly" in x or "warm" in x for x in ins)


def test_D2_D3_added_and_removed_paragraph_classified(tmp_path, monkeypatch):
    v_add = _N1_V1 + "\n% N1-p3\nA brand new third paragraph.\n"
    md, a, b = _two_state_repo(tmp_path, monkeypatch, _N1_V1, v_add)
    n1 = next(s for s in rv.compare(md, a, b)["sections"] if s["stem"] == "N1")
    added = [u for u in n1["units"] if u["status"] == "added"]
    assert [u["pid"] for u in added] == ["N1-p3"]
    # reverse: the same edit read the other way is a REMOVAL
    n1r = next(s for s in rv.compare(md, b, a)["sections"] if s["stem"] == "N1")
    removed = [u for u in n1r["units"] if u["status"] == "removed"]
    assert [u["pid"] for u in removed] == ["N1-p3"]


def test_D4_moved_paragraph_reads_as_add_remove_observed(tmp_path, monkeypatch):
    """OBSERVED (a defensible limitation, not a bug): a paragraph whose content is
    IDENTICAL but whose ORDER changed reads as removed+added (its body shown on both
    sides), not as a 'moved/same' unit. Pinned so the behaviour is explicit."""
    v_moved = (
        "% PLAN:N1\n\\section{Introduction}\\label{sec:N1}\n"
        "\n% N1-p2\nThe lazy dog sleeps here in the afternoon sun.\n"
        "\n% N1-p1\nThe quick brown fox jumps over the lazy dog.\n")
    md, a, b = _two_state_repo(tmp_path, monkeypatch, _N1_V1, v_moved)
    n1 = next(s for s in rv.compare(md, a, b)["sections"] if s["stem"] == "N1")
    statuses = {u["pid"]: u["status"] for u in n1["units"]}
    # both p1 and p2 have identical content; the reorder surfaces as add/remove pairs
    assert "added" in statuses.values() or "removed" in statuses.values()
    assert n1["changed"] is True


def test_D5_word_diff_is_whitespace_preserving_reconstructs_each_side(tmp_path):
    a = "The lazy   dog sleeps here."
    b = "The lazy dog sleeps soundly here."
    segs = rv._word_diff(a, b)
    assert "".join(s["a"] for s in segs) == a               # A reconstructs EXACTLY
    assert "".join(s["b"] for s in segs) == b               # B reconstructs EXACTLY (incl. WS)


def test_D8_duplicate_pid_aligns_positionally_no_body_dropped(tmp_path):
    """FND-1 FIXED: a fragment with a DUPLICATE ``% <SEC>-pN`` marker aligns bodies
    POSITIONALLY, never through a pid-keyed dict that silently drops the first body.
    Plant a dupe pid whose two occurrences carry DIFFERENT text; the change on the
    first occurrence must surface (not be masked by the second's body)."""
    dupA = ("% PLAN:N1\n\\section{Introduction}\\label{sec:N1}\n"
            "\n% N1-p1\nFirst occurrence, original text.\n"
            "\n% N1-p2\nA middle paragraph.\n"
            "\n% N1-p1\nSecond occurrence, steady text.\n")
    dupB = dupA.replace("First occurrence, original text.",
                        "First occurrence, EDITED text.")
    rowsA = rv._split_units(dupA)
    # the split keeps BOTH N1-p1 occurrences (dupes are real units, not collapsed)
    assert [p for p, _ in rowsA].count("N1-p1") == 2
    rows, tally = rv._align_units(rv._split_units(dupA), rv._split_units(dupB))
    changed = [r for r in rows if r["status"] == "changed"]
    # exactly the FIRST N1-p1 changed; its A-body is the ORIGINAL, not the last dupe's
    assert tally["changed"] == 1 and len(changed) == 1
    assert changed[0]["pid"] == "N1-p1"
    assert "original text" in changed[0]["a"] and "EDITED text" in changed[0]["b"]
    # the untouched second N1-p1 body ('steady text') never leaked onto the changed row
    assert "steady text" not in changed[0]["a"]
    same_p1 = [r for r in rows if r["pid"] == "N1-p1" and r["status"] == "same"]
    assert len(same_p1) == 1 and "steady text" in same_p1[0]["a"]


def test_D6_unchanged_section_is_collapsed_not_changed(tmp_path, monkeypatch):
    md, a, b = _two_state_repo(tmp_path, monkeypatch, _N1_V1, _N1_V2)
    n2 = next(s for s in rv.compare(md, a, b)["sections"] if s["stem"] == "N2")
    assert n2["changed"] is False and n2["status"] == "unchanged"


def test_D7_unknown_state_fails_safe_422(tmp_path, monkeypatch):
    md, a, b = _two_state_repo(tmp_path, monkeypatch, _N1_V1, _N1_V2)
    res = rv.compare(md, "no-such-state", b)
    assert "error" in res and res["reason"] == "unknown-a"  # 422, never a crash


# ===========================================================================
# GROUP E — PRESETS honesty + fail-safe
# ===========================================================================

def test_E1_no_voiced_state_disables_neutral_vs_voiced_with_reason(tmp_path, monkeypatch):
    repo, md = _init_repo(tmp_path, monkeypatch)
    _loop_commit(repo, md, "r1", ("N1.tex", _N1_V1))
    pr = rv._presets(rv.banked_states(md))
    avail = {p["id"] for p in pr["available"]}
    dis = {p["id"]: p for p in pr["disabled_with_reason"]}
    assert "candidate-vs-incumbent" in avail                # a loop-pass exists
    assert "neutral-vs-voiced" in dis and "voiced" in dis["neutral-vs-voiced"]["reason"]


def test_E2_candidate_vs_incumbent_prefers_snapshot_over_loop(tmp_path, monkeypatch):
    repo, md = _init_repo(tmp_path, monkeypatch)
    _loop_commit(repo, md, "r1", ("N1.tex", _N1_V1))
    snap = md / "rounds" / "incumbent_r2"
    snap.mkdir(parents=True)
    (snap / "N1.tex").write_text(_N1_V2, encoding="utf-8")
    (snap / "SNAPSHOT.json").write_text(json.dumps({"round": 2}), encoding="utf-8")
    pr = rv._presets(rv.banked_states(md))
    cvi = next(p for p in pr["available"] if p["id"] == "candidate-vs-incumbent")
    assert cvi["a"] == "incumbent-r2"                       # snapshot beats the loop commit
    assert cvi["b"] == "working"


def test_E3_voiced_loop_lights_up_neutral_vs_voiced(tmp_path, monkeypatch):
    repo, md = _init_repo(tmp_path, monkeypatch)
    n = _loop_commit(repo, md, "neutral-pass", ("N1.tex", _N1_V1))  # noqa: F841
    _loop_commit(repo, md, "the voice pass", ("N1.tex", _N1_V2))    # 'voice' in label
    pr = rv._presets(rv.banked_states(md))
    nvv = next((p for p in pr["available"] if p["id"] == "neutral-vs-voiced"), None)
    assert nvv is not None, "voiced state should light up neutral-vs-voiced"
    # a = the neutral predecessor, b = the voiced state
    assert nvv["a_label"] == "neutral-pass" and nvv["b_label"] == "the voice pass"


def test_E4_empty_corpus_disables_candidate_vs_incumbent_no_crash(tmp_path, monkeypatch):
    repo, md = _init_repo(tmp_path, monkeypatch)      # only the seed, no loop/snap
    pr = rv._presets(rv.banked_states(md))
    dis = {p["id"] for p in pr["disabled_with_reason"]}
    assert "candidate-vs-incumbent" in dis and "neutral-vs-voiced" in dis
    assert pr["available"] == []                            # nothing fabricated


# ===========================================================================
# GROUP F — the C1(a) _escs tombstone: actor, never free-text
# ===========================================================================

def test_F1_surface_source_has_no_text_escalation_scan():
    """Static: the surface source carries NO `_escs` symbol and NO 'escalate:' free-text
    sniff — the text-vs-actor conflation is confined to the off-limits mechround."""
    src = Path(rv.__file__).read_text(encoding="utf-8")
    assert "_escs" not in src
    assert "escalate:" not in src
    # the escalation class is keyed on the record KIND (DEFER), not a text match
    assert "escalate" not in src.lower().replace("escalation", "")


def test_F2_scope_commits_touch_only_review_surface_and_tests():
    """Static scope gate: neither 4141ba4 (B-2) nor 7d3e12f (B-3) touches the radioactive
    trio, pipeline/**, or scanner.py — only review_surface.{py,html} + tests."""
    repo = Path(__file__).resolve().parents[1]
    # RETIREMENT-BY-XFAIL (W-TRIAGE 2026-07-22): this static scope gate reads two specific commits
    # (4141ba4 B-2, 7d3e12f B-3) that the branch rebase (claude/eigen-engine-instrument-*) squashed out
    # of history — `git show` can no longer resolve them (verified: git cat-file -e fails on both). The
    # probe's SUBJECT (those commits' file-scope) is UNREACHABLE. Matching test_canonised_judge_probes.py's
    # sibling discipline, an absent-commit scope probe is a BANKED KNOWN-FAIL (non-strict xfail), never a
    # hard red nor a silent delete: the assertions stay verbatim and re-arm if the commits are re-anchored.
    _present = lambda rev: subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{rev}^{{commit}}"],
                                          capture_output=True).returncode == 0
    if not (_present("4141ba4") and _present("7d3e12f")):
        pytest.xfail("legB23 scope commits 4141ba4 / 7d3e12f absent from history after the branch "
                     "rebase — unreachable (banked known-fail, W-TRIAGE 2026-07-22)")
    radioactive = {"src/laplace/review_static.html",
                   "src/laplace/export_review.py", "src/laplace/web/site_seal.py"}
    for commit in ("4141ba4", "7d3e12f"):
        out = subprocess.run(
            ["git", "-C", str(repo), "show", "--stat", "--format=", "--name-only", commit],
            capture_output=True, text=True, check=False).stdout
        files = {ln.strip() for ln in out.splitlines() if ln.strip()}
        assert files, f"{commit}: no files?"
        assert not (files & radioactive), f"{commit} touched radioactive: {files & radioactive}"
        assert not any(f.startswith("src/laplace/pipeline/") for f in files), files
        assert "src/laplace/web/scanner.py" not in files, files
        for f in files:
            assert (f in ("src/laplace/manuscript/review_surface.py",
                          "src/laplace/review_surface.html")
                    or f.startswith("tests/")), f"{commit}: out-of-scope file {f!r}"


def test_F3_surface_does_not_import_the_radioactive_trio():
    """Static: review_surface.py imports none of export_review / site_seal / review_static
    (no pattern-copy vector either — the module names never appear)."""
    src = Path(rv.__file__).read_text(encoding="utf-8")
    for banned in ("export_review", "site_seal", "review_static"):
        assert banned not in src, f"radioactive reference {banned!r} in review_surface.py"
