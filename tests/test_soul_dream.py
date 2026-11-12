"""Tests for soul_dream - the recursive content-dreamer (the conjugate of dreamer.dream).

No real soul content: a synthetic tmp ``*_folded`` tree with hand-written friction ledgers. The
contracts under test - (1) the friction ledgers parse into a typed, priority-ranked reconsolidation
queue (his corrections lead); (2) resolved blocks drop and author-rejected merges drop; (3) THE SEAL:
no name, directive or fact from the sealed ledgers ever reaches the committed state file or the tool
return - they live only in the gitignored plan; (4) the cycle is re-entrant and idempotent."""

from __future__ import annotations

import json
from pathlib import Path

from laplace.engine import soul_dream as sd

# A distinctive fake name planted in the synthetic ledgers; the seal tests assert it NEVER reaches
# any committed/returned surface (only the gitignored plan).
SECRET = "Zylphagor Quux"


def _folded(tmp_path: Path) -> Path:
    """A synthetic tranche-folded tree with friction ledgers, slices, a wiring note and a deferred
    group - the shapes the dreamer routes over, no real content."""
    folded = tmp_path / "archive" / "soul_dump" / "_shard" / "scaledX_folded"
    (folded / "_slices").mkdir(parents=True)
    (folded / "_deferred_group").mkdir(parents=True)
    (folded / "_verdicts").mkdir(parents=True)
    # one apex entity + its recoverable slices
    (folded / "zylphagor.json").write_text("{}", encoding="utf-8")
    (folded / "_slices" / "zylphagor_A.json").write_text("{}", encoding="utf-8")
    (folded / "_slices" / "zylphagor_B.json").write_text("{}", encoding="utf-8")
    (folded / "_deferred_group" / "README.md").write_text("a group chat", encoding="utf-8")

    (folded / "_friction.md").write_text(
        f"## {SECRET} (apex adjudication flags — reconsolidation candidates, NOT patches)\n"
        f"- something to reconsolidate about {SECRET}.\n\n"
        f"## AUTHOR CORRECTION 2026-06-10 — {SECRET} IS SOMEONE ELSE (wrong-merge, REJECTED)\n"
        f"Ground truth (his): {SECRET} was mis-merged.\n"
        f"THE RE-WIRE (cycle's job, do not hand-patch):\n"
        f"- Re-fold {SECRET} clean from slices.\n\n"
        f"## OldThing (apex adjudication flags)\n"
        f"- OVER-CONSOLIDATION: re-fold from the substrate.\n"
        f"> RECONSOLIDATED 2026-06-11: done, un-merged.\n",
        encoding="utf-8")

    (folded / "_WIRING_NOTES.md").write_text(
        f"# WIRING NOTES\n"
        f"- **{SECRET} == OtherPerson.** merge these.\n"
        f"> AUTHOR-REJECTED 2026-06-10: the == merge above is WRONG; un-merge.\n"
        f"- **{SECRET} → friends circle.** wire in.\n",
        encoding="utf-8")
    return folded


# ---------------------------------------------------------------------------
# the friction parse - the reconsolidation queue
# ---------------------------------------------------------------------------

def test_author_correction_leads_the_queue(tmp_path):
    _folded(tmp_path)
    items = sd.parse_friction(tmp_path)
    kinds = [i["kind"] for i in items]
    assert "author_correction" in kinds
    author = next(i for i in items if i["kind"] == "author_correction")
    assert author["priority"] == 0                      # his ground truth is first
    assert author["op"] == "reconsolidate"


def test_resolved_block_is_dropped(tmp_path):
    _folded(tmp_path)
    items = sd.parse_friction(tmp_path)
    # the OldThing section carries a RECONSOLIDATED marker -> not in the active queue
    assert all("oldthing" not in (i["target"] or "").lower() for i in items)


def test_over_consolidation_flag_is_typed_and_prioritised(tmp_path):
    # an OVER-CONSOLIDATION not yet resolved is a priority-1 re-fold
    folded = tmp_path / "archive" / "soul_dump" / "_shard" / "scaledY_folded"
    folded.mkdir(parents=True)
    (folded / "_friction.md").write_text(
        "## WIRING (adjudication flags)\n- OVER-CONSOLIDATION: the handle coarsened; re-fold from slices.\n",
        encoding="utf-8")
    items = sd.parse_friction(tmp_path)
    oc = [i for i in items if i["kind"] == "over_consolidation"]
    assert oc and oc[0]["priority"] == 1 and oc[0]["op"] == "reconsolidate"


def test_pipeline_note_is_a_note_not_work(tmp_path):
    folded = tmp_path / "archive" / "soul_dump" / "_shard" / "scaledZ_folded"
    folded.mkdir(parents=True)
    (folded / "_CORRECTIONS.md").write_text(
        "## flags\n- **PIPELINE NOTE** — strip internal labels before the resolve.\n", encoding="utf-8")
    items = sd.parse_friction(tmp_path)
    pn = [i for i in items if i["kind"] == "pipeline_note"]
    assert pn and pn[0]["op"] == "note"                 # mechanical hygiene, not a re-fold


# ---------------------------------------------------------------------------
# the wiring parse - author-rejected merges drop, cross-links stand
# ---------------------------------------------------------------------------

def test_author_rejected_merge_drops_but_circle_stands(tmp_path):
    _folded(tmp_path)
    wires = sd.parse_wiring(tmp_path)
    labels = [w["target"] for w in wires]
    assert not any("==" in lbl for lbl in labels)       # the rejected identity-merge is gone
    assert any("circle" in lbl for lbl in labels)       # the cross-link wire stands


# ---------------------------------------------------------------------------
# the frontier rank - reconsolidate before wire before fold before reshape
# ---------------------------------------------------------------------------

def test_frontier_ranks_corrections_first(tmp_path):
    _folded(tmp_path)
    a = sd.assess_soul(tmp_path, grade=0)
    ops = [i["op"] for i in a["frontier"]]
    # the first item is a reconsolidation (his correction); fold/reshape never precede a reconsolidate
    assert a["frontier"][0]["op"] == "reconsolidate"
    assert ops.index("reconsolidate") < (ops.index("fold") if "fold" in ops else 99)
    # every work item carries a sealed-sub brief
    assert all(i.get("brief") for i in a["frontier"])


def test_deferred_group_becomes_a_fold(tmp_path):
    _folded(tmp_path)
    a = sd.assess_soul(tmp_path, grade=0)
    assert any(i["op"] == "fold" and i["kind"] == "deferred_group" for i in a["frontier"])


# ---------------------------------------------------------------------------
# THE SEAL - the load-bearing contract: no content on a committed/returned surface
# ---------------------------------------------------------------------------

def test_safe_view_carries_no_name(tmp_path):
    _folded(tmp_path)
    a = sd.assess_soul(tmp_path, grade=0)
    blob = json.dumps(sd.safe_view(a), ensure_ascii=False)
    assert SECRET not in blob
    assert "Re-fold" not in blob and "slices" not in blob   # no directive text either


def test_committed_state_file_carries_no_name(tmp_path):
    _folded(tmp_path)
    a = sd.assess_soul(tmp_path, grade=0)
    state = sd.write_dream_state(tmp_path, a)
    text = state.read_text(encoding="utf-8")
    assert SECRET not in text
    assert "AUTHOR CORRECTION" not in text                  # no ledger prose, only counts


def test_rich_plan_is_local_and_holds_the_detail(tmp_path):
    _folded(tmp_path)
    a = sd.assess_soul(tmp_path, grade=0)
    plan = sd.write_plan_local(tmp_path, a)
    # the plan lives under the gitignored sealed tree...
    assert "archive/soul_dump" in plan.as_posix()
    # ...and it DOES hold the detail (so the wave can act) - the seal is on the COMMITTED surface
    assert SECRET in plan.read_text(encoding="utf-8")


def test_soul_dream_return_carries_no_name(tmp_path):
    _folded(tmp_path)
    out = sd.soul_dream(tmp_path, apply=True, grade=1, commit=False)
    assert SECRET not in json.dumps(out, ensure_ascii=False)
    assert out["applied"] is True
    assert "archive/soul_dump" in out["plan_local"].replace("\\", "/")   # the wave reads the sealed plan


# ---------------------------------------------------------------------------
# the cycle - dry vs apply, boundary clock, idempotency
# ---------------------------------------------------------------------------

def test_dry_run_writes_nothing(tmp_path):
    _folded(tmp_path)
    out = sd.soul_dream(tmp_path, apply=False, grade=0, commit=False)
    assert out["applied"] is False
    assert not (tmp_path / sd.DREAM_STATE).exists()
    assert not (tmp_path / sd.PLAN_LOCAL).exists()


def test_apply_writes_both_surfaces(tmp_path):
    _folded(tmp_path)
    sd.soul_dream(tmp_path, apply=True, grade=1, commit=False)
    assert (tmp_path / sd.DREAM_STATE).exists()             # committed, content-free
    assert (tmp_path / sd.PLAN_LOCAL).exists()              # gitignored, rich


def test_grade0_apply_advances_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "_state"))
    _folded(tmp_path)
    out = sd.soul_dream(tmp_path, apply=True, grade=0, commit=False)
    assert out["boundary_advanced"] is True
    from laplace.engine import telemetry
    assert telemetry.last_soul_dream_ts() is not None       # the conjugate clock ticked


def test_assess_is_idempotent(tmp_path):
    _folded(tmp_path)
    a1 = sd.assess_soul(tmp_path, grade=0)
    a2 = sd.assess_soul(tmp_path, grade=0)
    shape1 = [(i["op"], i["kind"], i["priority"]) for i in a1["frontier"]]
    shape2 = [(i["op"], i["kind"], i["priority"]) for i in a2["frontier"]]
    assert shape1 == shape2                                  # same read, same frontier (re-entrant)
