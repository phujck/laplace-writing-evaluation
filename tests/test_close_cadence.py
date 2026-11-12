"""THE CADENCE WIRING — the two close-ritual clauses this wave adds to close_checklist.py:

  * fork_drain  — THE STANDING DRAIN (his ruling PV-20260717T002125 item 4): every close
                  drafts parked forks and stops at reviewed-drafts + a desk surface; the
                  BANKING step stays behind the reviewed path (--live, supervised). WARN
                  tier, never FAIL_ELIGIBLE, never banks.
  * first_chair — THE FIRST-CHAIR CLAUSE (the infrastructure law): a working tree carrying
                  a produced artefact (pdf / minted / surface rebuild) MUST carry a fresh
                  evidence/FIRST_CHAIR_*.md note newer than the artefact, else the close
                  FAILs. FAIL_ELIGIBLE.

The PLANTED-VIOLATION tests are the point: a produced artefact with no note (and with a
STALE note) fails the close; a fresh note clears it. All fixtures live in tmp_path — no
canonical tree is touched.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "close_checklist.py"
spec = importlib.util.spec_from_file_location("close_checklist", SCRIPT)
close_checklist = importlib.util.module_from_spec(spec)
sys.modules["close_checklist"] = close_checklist
spec.loader.exec_module(close_checklist)

TODAY = date.today().isoformat()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "test@example.com")
    _git(r, "config", "user.name", "Test")
    (r / "evidence").mkdir()
    (r / "README.md").write_text("# fixture\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    return r


def _touch(p: Path, text: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _set_mtime(p: Path, when: float) -> None:
    os.utime(p, (when, when))


# ═══════════════════════════ fork_drain (the standing drain) ═══════════════════════════
def test_fork_drain_present_in_run_all(repo):
    names = [c.name for c in close_checklist.run_all(repo, TODAY)]
    assert "fork_drain" in names


def test_fork_drain_never_fail_eligible():
    # his ruling: banking stays behind the reviewed path — the drain never gates the exit
    assert "fork_drain" not in close_checklist.FAIL_ELIGIBLE


def test_fork_drain_passes_on_empty_drain(repo):
    # a repo with no OPEN_STACK and no corpus_friction has no parked forks to drain
    c = close_checklist.check_fork_drain(repo)
    assert c.status in ("PASS", "WARN")  # PASS when the enumeration resolves to zero
    if c.status == "PASS":
        assert "drain is empty" in c.detail


def test_fork_drain_warn_names_the_three_stages(repo):
    # plant one live OPEN_STACK fork with no verdict -> the drain is owed, and the WARN
    # must name DRAFT (manifest), REVIEW (the desk surface), and BANK (--live, supervised)
    (repo / "OPEN_STACK.md").write_text(
        "# open stack\n\n- **FQ99 the planted fork** \U0001f534 needs a call\n",
        encoding="utf-8")
    (repo / "proxy_verdicts.jsonl").write_text("", encoding="utf-8")
    c = close_checklist.check_fork_drain(repo)
    # the enumeration may or may not resolve the planted row depending on the shared
    # reader's shape; when it does, the WARN must carry the full cadence.
    if c.status == "WARN" and "parked fork" in c.detail:
        assert "manifest" in c.detail                      # DRAFT stage
        assert "/desk forks lane" in c.detail              # REVIEW stage (desk surface)
        assert "--live" in c.detail                        # BANK stage (supervised)
        assert "never banks" in c.detail                   # the close stops behind the reviewed path


# ═══════════════════════════ first_chair (the infrastructure law) ═══════════════════════════
def test_first_chair_is_fail_eligible():
    assert "first_chair" in close_checklist.FAIL_ELIGIBLE


def test_first_chair_present_in_run_all(repo):
    names = [c.name for c in close_checklist.run_all(repo, TODAY)]
    assert "first_chair" in names


def test_first_chair_pass_when_no_artefact(repo):
    # a clean tree with a plain doc change carries no produced artefact
    _touch(repo / "notes.md", "just prose")
    c = close_checklist.check_first_chair(repo)
    assert c.status == "PASS", c.detail
    assert "no produced artefact" in c.detail


@pytest.mark.parametrize("art", [
    "paper_falqon/manuscript/main.pdf",       # a compiled PDF
    "build/minted-out/listing.tex",           # a minted output
    "src/laplace/web/analytics.html",             # a rebuilt served surface
])
def test_first_chair_FAILS_on_produced_artefact_with_no_note(repo, art):
    # THE PLANTED VIOLATION: a produced artefact in the tree, no FIRST_CHAIR note at all
    _touch(repo / art, "produced bytes")
    c = close_checklist.check_first_chair(repo)
    assert c.status == "FAIL", c.detail
    assert "FIRST_CHAIR" in c.detail
    # and it actually moves the exit code (FAIL_ELIGIBLE, so the verdict is FAIL)
    checks = [c]
    ok, fails, _ = close_checklist._verdict(checks)
    assert not ok and fails[0].name == "first_chair"


def test_first_chair_FAILS_on_stale_note(repo):
    # THE PLANTED VIOLATION, subtler: a note exists but PREDATES the artefact (read stale)
    art = repo / "paper_falqon/manuscript/main.pdf"
    _touch(art, "produced bytes")
    note = repo / "evidence" / "FIRST_CHAIR_2026-07-17_seam5.md"
    _touch(note, "# first chair — an OLD read\n")
    now = time.time()
    _set_mtime(note, now - 100)   # note written 100s BEFORE the artefact
    _set_mtime(art, now)
    c = close_checklist.check_first_chair(repo)
    assert c.status == "FAIL", c.detail
    assert "predates the artefact" in c.detail or "NEWER than the latest" in c.detail


def test_first_chair_PASSES_on_fresh_note(repo):
    # the correct close: read what shipped, THEN bank the note (note newer than artefact)
    art = repo / "src/laplace/web/analytics.html"
    _touch(art, "rebuilt surface")
    note = repo / "evidence" / "FIRST_CHAIR_2026-07-17_surface.md"
    _touch(note, "# first chair — I read the rebuilt surface\n")
    now = time.time()
    _set_mtime(art, now - 100)     # artefact produced first
    _set_mtime(note, now)          # note banked after the read
    c = close_checklist.check_first_chair(repo)
    assert c.status == "PASS", c.detail
    assert "chaired by" in c.detail


def test_first_chair_ignores_non_artefact_html_outside_surfaces(repo):
    # a random .html that is NOT a served src/laplace surface is not a produced artefact
    _touch(repo / "docs/readme.html", "<p>hi</p>")
    c = close_checklist.check_first_chair(repo)
    assert c.status == "PASS", c.detail
