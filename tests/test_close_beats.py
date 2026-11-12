"""Tests for close_beats — the GRADED close (which Part C beats a sew-up must walk).

The gating is proved with explicit ``changed`` sets against a repo that carries a
banked close (the mark): grade-0 beats always fire, session facts always fire
(honestly flagged), and every diff-gated beat fires iff its source map moved. Two
things need a real git history, so they get real commits: the mark resolution
(``last_banked_close``) and the no-mark fail-heavy fallback.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from laplace.engine import close_beats as cb

TODAY = "2026-07-12"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")


@pytest.fixture()
def marked_repo(tmp_path):
    """A repo whose HEAD is a banked close: an "sew up" commit sits on top of a
    non-root init, so the mark resolves and "since the mark" is well defined."""
    repo = tmp_path / "repo"
    _init(repo)
    (repo / "seed.txt").write_text("seed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    (repo / "EIGEN_DIARY.md").write_text("the trace\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"sew up {TODAY} — the close")
    closed_at = subprocess.run(["git", "show", "-s", "--format=%cI", "HEAD"], cwd=repo,
                               check=True, capture_output=True, text=True).stdout.strip()
    (repo / "contract").mkdir()
    (repo / "contract/close_receipt.json").write_text(json.dumps({
        "schema_version": "laplace.close/1", "status": "PUBLISHED", "closed_at": closed_at,
        "checkpoint": {"HANDOFF.md": "sha256:checkpoint"},
        "publication": {"schema_version": "laplace.publication/1", "published": True,
                        "artifacts": {".self_graded.json": "sha256:published"}},
    }))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "record the publication boundary")
    return repo


def _beat(plan, name):
    return next(b for b in plan if b["beat"] == name)


# ------------------------------------------------------------ the mark
def test_last_banked_close_reads_publication_receipt(marked_repo):
    mark = cb.last_banked_close(marked_repo)
    assert mark is not None
    assert mark.startswith("2026-")  # an ISO timestamp of the close commit


def test_handoff_addition_alone_is_not_a_published_close(tmp_path):
    repo = tmp_path / "repo"
    _init(repo)
    (repo / "seed.txt").write_text("seed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    # a commit that ADDS a dated SESSION_HANDOFF but has an ordinary subject
    (repo / f"SESSION_HANDOFF_{TODAY}_x.md").write_text("# handoff\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "bank the dated handoff")
    assert cb.last_banked_close(repo) is None


def test_last_banked_close_none_without_git(tmp_path):
    bare = tmp_path / "not_a_repo"
    bare.mkdir()
    assert cb.last_banked_close(bare) is None


def test_last_banked_close_none_when_no_close_commit(tmp_path):
    repo = tmp_path / "repo"
    _init(repo)
    (repo / "a.txt").write_text("1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "just some work")
    (repo / "b.txt").write_text("2\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "more work")
    assert cb.last_banked_close(repo) is None


# ------------------------------------------------------- grade-0 always fires
GRADE0 = {"diary", "handoff", "session_handoff", "commit", "re-embed", "rehearsal", "open_stack_sweep"}


def test_grade0_beats_always_present_and_fire(marked_repo):
    plan = cb.beat_plan(marked_repo, changed=set())
    names = {b["beat"] for b in plan}
    assert GRADE0 <= names
    for name in GRADE0:
        assert _beat(plan, name)["fire"] is True


def test_session_facts_fire_honestly_flagged(marked_repo):
    plan = cb.beat_plan(marked_repo, changed=set())
    for name in ("standing_law", "sawbones_log"):
        b = _beat(plan, name)
        assert b["fire"] is True
        assert "not diff-derivable" in b["why"]


# ------------------------------------------------------- diff gating
def test_unmoved_source_gates_beat_off(marked_repo):
    plan = cb.beat_plan(marked_repo, changed=set())
    for name in ("architecture", "recurrence", "durable_refs", "seam_liveness", "holdout"):
        b = _beat(plan, name)
        assert b["fire"] is False
        assert "unmoved" in b["why"]


def test_moved_source_fires_architecture(marked_repo):
    plan = cb.beat_plan(marked_repo, changed={"src/laplace/foo.py"})
    b = _beat(plan, "architecture")
    assert b["fire"] is True
    assert "src/laplace/foo.py" in b["why"]


def test_moved_scripts_or_workflows_fire_architecture(marked_repo):
    for path in ("scripts/reembed.py", ".claude/workflows/close.yml"):
        b = _beat(cb.beat_plan(marked_repo, changed={path}), "architecture")
        assert b["fire"] is True, path


def test_recurrence_gated_on_friction_ledgers(marked_repo):
    b = _beat(cb.beat_plan(marked_repo, changed={"corpus_friction/laplace.jsonl"}), "recurrence")
    assert b["fire"] is True
    # an unrelated move does not fire it
    b2 = _beat(cb.beat_plan(marked_repo, changed={"README.md"}), "recurrence")
    assert b2["fire"] is False


def test_durable_refs_gated_on_durable_surfaces(marked_repo):
    b = _beat(cb.beat_plan(marked_repo, changed={"OPEN_STACK.md"}), "durable_refs")
    assert b["fire"] is True


def test_seam_liveness_gated_on_seam_artifacts(marked_repo):
    b = _beat(cb.beat_plan(marked_repo, changed={"projects/p/economics.json"}), "seam_liveness")
    assert b["fire"] is True


def test_holdout_gated_on_holdout_tree(marked_repo):
    b = _beat(cb.beat_plan(marked_repo, changed={"holdout/PREDICTION_pending.json"}), "holdout")
    assert b["fire"] is True


# ------------------------------------------------------- no mark -> all fire
def test_unresolvable_mark_fires_every_beat(tmp_path):
    bare = tmp_path / "not_a_repo"
    bare.mkdir()
    plan = cb.beat_plan(bare, changed=set())
    assert plan and all(b["fire"] for b in plan)


# ------------------------------------------------------- effect_meter (gitignored heuristic)
def test_effect_meter_fires_when_wire_ledger_touched_after_mark(marked_repo):
    # unmoved: no wire ledgers on disk -> gated off
    assert _beat(cb.beat_plan(marked_repo, changed=set()), "effect_meter")["fire"] is False
    # touch a wire ledger now (after the mark) -> the mtime heuristic fires it
    (marked_repo / ".wire_proposals.jsonl").write_text('{"query": "q", "id": "x"}\n')
    b = _beat(cb.beat_plan(marked_repo, changed=set()), "effect_meter")
    assert b["fire"] is True
    assert "mtime heuristic" in b["why"]


def test_wire_drain_substep_note_tracks_frontier(marked_repo):
    # empty frontier -> sub-step skipped
    assert "wire-drain sub-step skipped" in _beat(cb.beat_plan(marked_repo, changed=set()), "re-embed")["why"]
    (marked_repo / ".wire_proposals.jsonl").write_text('{"query": "q", "id": "x"}\n')
    assert "wire-drain sub-step active" in _beat(cb.beat_plan(marked_repo, changed=set()), "re-embed")["why"]


# ------------------------------------------------------- suite is never flat
def test_suite_is_never_flat_always_scoped(marked_repo):
    for changed in (set(), {"src/laplace/foo.py"}):
        b = _beat(cb.beat_plan(marked_repo, changed=changed), "suite")
        assert b["sources"][0] == "python3 -m laplace.engine.tests_at_grade --run"
        assert "never" in b["why"] and "flat" in b["why"]


def test_suite_inherits_green_on_clean_shard(marked_repo):
    b = _beat(cb.beat_plan(marked_repo, changed=set()), "suite")
    assert b["fire"] is False
    assert "inherits the banked-green verdict" in b["why"]


def test_suite_no_mark_fires_fail_heavy(tmp_path):
    bare = tmp_path / "not_a_repo"
    bare.mkdir()
    b = _beat(cb.beat_plan(bare, changed=set()), "suite")
    assert b["fire"] is True
    assert b["sources"][0] == "python3 -m laplace.engine.tests_at_grade --run"


# ------------------------------------------------------- entry shape
def test_every_entry_conforms_to_the_beat_dict(marked_repo):
    plan = cb.beat_plan(marked_repo, changed=set())
    for b in plan:
        assert set(b) == {"beat", "fire", "sources", "why"}
        assert isinstance(b["beat"], str) and isinstance(b["fire"], bool)
        assert isinstance(b["sources"], list) and isinstance(b["why"], str)


# ------------------------------------------------------- re-embed deposit MODE
def test_reembed_why_names_deposit_mode_and_wire(marked_repo):
    # cold: no .meaning_tree.json, empty frontier -> full rebuild + wire skipped
    why = _beat(cb.beat_plan(marked_repo, changed=set()), "re-embed")["why"]
    assert "wire-drain sub-step skipped" in why
    assert "deposit full rebuild expected" in why and "no .meaning_tree.json" in why
    # warm: persisted tree + live frontier -> incremental + wire active, changed-set counted
    (marked_repo / ".meaning_tree.json").write_text("{}\n", encoding="utf-8")
    (marked_repo / ".wire_proposals.jsonl").write_text('{"id": "x"}\n', encoding="utf-8")
    why2 = _beat(cb.beat_plan(marked_repo, changed={"src/laplace/foo.py"}), "re-embed")["why"]
    assert "wire-drain sub-step active" in why2
    assert "deposit incremental expected" in why2 and ".meaning_tree.json present" in why2
    assert "1 path(s) changed" in why2


# ------------------------------------------------------- the dream beat (day-window gated)
def test_dream_beat_fires_with_count_when_events_since_dream(marked_repo):
    from laplace.engine import telemetry
    telemetry.clear()
    telemetry.log("dream_complete")            # the day-dream marker
    telemetry.log("orient", goal="x")          # two events land strictly after it
    telemetry.log("verify")
    b = _beat(cb.beat_plan(marked_repo, changed=set()), "dream")
    assert b["fire"] is True
    assert "2 telemetry events since last day-dream" in b["why"]
    assert "revertible" in b["why"] and "forge never auto-fires" in b["why"]


def test_dream_beat_skips_when_no_events_since_dream(marked_repo):
    from laplace.engine import telemetry
    telemetry.clear()
    telemetry.log("orient", goal="x")
    telemetry.log("dream_complete")            # the dream is the LAST event -> nothing after it
    b = _beat(cb.beat_plan(marked_repo, changed=set()), "dream")
    assert b["fire"] is False
    assert "nothing to stitch" in b["why"]


def test_dream_beat_fires_fail_heavy_when_never_dreamed(marked_repo):
    # no dream_complete marker at all: like an unresolvable mark, fire fail-heavy
    from laplace.engine import telemetry
    telemetry.clear()
    b = _beat(cb.beat_plan(marked_repo, changed=set()), "dream")
    assert b["fire"] is True
    assert "no day-dream marker yet" in b["why"] and "fail-heavy" in b["why"]


def test_default_changed_is_derived_from_the_diff(marked_repo):
    # no explicit changed: on a clean tree at the mark, nothing moved -> gated off
    plan = cb.beat_plan(marked_repo)
    assert _beat(plan, "architecture")["fire"] is False
    # dirty a source file -> the default diff picks it up and architecture fires
    (marked_repo / "src").mkdir()
    (marked_repo / "src" / "laplace").mkdir()
    (marked_repo / "src" / "laplace" / "touched.py").write_text("x = 1\n")
    assert _beat(cb.beat_plan(marked_repo), "architecture")["fire"] is True


# ------------------------------------------------ banked-what-travels (W6.2)
def test_banked_what_travels_lists_untracked_round_records(marked_repo):
    """A produced-in-container round record under <manuscript>/rounds/ is untracked (the mark-
    diff cannot see it) but must be staged so it travels — the beat lists it from the dirty tree."""
    md = marked_repo / "eigenengine" / "manuscript" / "rounds" / "harnessed"
    md.mkdir(parents=True)
    (md / "mech_r2.json").write_text('{"round": 2}\n')
    (marked_repo / "eigenengine" / "manuscript" / "main.nodemap.json").write_text('{"entries": {}}\n')
    # an unrelated untracked file must NOT be listed
    (marked_repo / "scratch.txt").write_text("noise\n")

    travel = cb.banked_what_travels(marked_repo)
    assert "eigenengine/manuscript/rounds/harnessed/mech_r2.json" in travel
    assert "eigenengine/manuscript/main.nodemap.json" in travel
    assert "scratch.txt" not in travel

    plan = cb.beat_plan(marked_repo)
    beat = _beat(plan, "banked_what_travels")
    assert beat["fire"] is True
    assert "eigenengine/manuscript/rounds/harnessed/mech_r2.json" in beat["sources"]
    assert "git-add-able" in beat["why"]


def test_banked_what_travels_empty_when_nothing_pending(marked_repo):
    """Clean tree (no produced round records/sidecars) -> the beat does not fire."""
    travel = cb.banked_what_travels(marked_repo)
    assert travel == []
    beat = _beat(cb.beat_plan(marked_repo), "banked_what_travels")
    assert beat["fire"] is False
    assert "no produced round records" in beat["why"]


# ------------------------------------- an unreadable git is not a clean tree
class _Answer:
    """Stand-in for subprocess.run's CompletedProcess — rc plus the two streams."""

    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _break_git(monkeypatch, raises=None):
    """Make close_beats' `git status` read fail the way a real one does — rc 128 by
    default, or the given exception on spawn. Patched inside the test body only, so
    the fixture's own real git calls have already run."""
    def run(cmd, *a, **kw):
        if raises is not None:
            raise raises
        return _Answer(128, "", "fatal: detected dubious ownership\n")
    monkeypatch.setattr(cb.subprocess, "run", run)


def _is_scoped(beat) -> bool:
    return any("tests_at_grade --run" in s for s in beat["sources"])


def test_dirty_paths_is_none_when_git_does_not_answer(marked_repo, monkeypatch):
    assert cb._dirty_paths(marked_repo) == set()   # real git, clean tree: read and empty
    _break_git(monkeypatch)
    assert cb._dirty_paths(marked_repo) is None    # unread, which is not the same fact
    _break_git(monkeypatch, raises=OSError("no such file: git"))
    assert cb._dirty_paths(marked_repo) is None


def test_unreadable_git_fires_the_plan_fail_heavy(marked_repo, monkeypatch):
    # control: real git, clean tree at the mark -> the gated beats stay off
    plan = cb.beat_plan(marked_repo)
    assert _beat(plan, "architecture")["fire"] is False
    assert _beat(plan, "suite")["fire"] is False
    assert _beat(plan, "banked_what_travels")["fire"] is False

    _break_git(monkeypatch)
    plan = cb.beat_plan(marked_repo)
    for name in ("architecture", "recurrence", "durable_refs", "seam_liveness", "holdout",
                 "banked_what_travels", "suite"):
        beat = _beat(plan, name)
        assert beat["fire"] is True, name
        assert "git unreadable" in beat["why"], name
    assert "fail-heavy" in _beat(plan, "suite")["why"]
    assert _is_scoped(_beat(plan, "suite"))   # still scoped, never the flat suite


def test_explicit_changed_is_never_treated_as_git_blind(marked_repo, monkeypatch):
    """An explicit diff never consults git, so a broken git must not change its plan."""
    _break_git(monkeypatch)
    plan = cb.beat_plan(marked_repo, changed=set())
    assert _beat(plan, "architecture")["fire"] is False
    assert _beat(plan, "suite")["fire"] is False
    assert "git unreadable" not in _beat(plan, "suite")["why"]
