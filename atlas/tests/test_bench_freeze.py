"""test_bench_freeze.py - the freeze refusals and the decay DETECTOR (Phase 2 gates b and d).

Gate (b): a bundle does not mint unless every atom resolves, post-normalizer, inside its declared
anchor span - and a DELIBERATELY CORRUPTED anchor must refuse. Three corruptions are tested
because they fail differently: an anchor pointing at a span that holds no such atom, an anchor
whose declared span content hash has been tampered with, and an anchor naming a span id that is
not in the view at all.

Gate (d): the decay detector. A week of repository drift is not available inside a test, so the
drift is CONSTRUCTED: the same corpus is exported twice, the second time with one paragraph
rewritten, and the detector must classify the moved atom as ``decayed`` and the untouched ones as
``stable``. A detector that reported everything stable would be hiding exactly the defect it
exists to catch - which is what the v1 bench did for a day - so ``test_a_moved_atom_is_decayed``
is the load-bearing one here.
"""

from __future__ import annotations

import dataclasses

import pytest
from bench_fixture import DOC, build_bundle, open_bundle

from atlas.bench.freeze import anchor_task, freeze_bundle, re_anchor, verify_bundle, verify_task
from atlas.bench.task import Anchor
from atlas.bench.universe import BENCH_FILTERED, SnapshotView
from atlas.errors import AnchorHashMismatch, AnchorUnresolved, BundleIdMismatch


@pytest.fixture()
def view(tmp_path):
    return SnapshotView(open_bundle(build_bundle(tmp_path / "snap")), BENCH_FILTERED)


def _task(view, task_id="T1", atoms=None, window=None):
    return anchor_task(view, task_id=task_id, task_class="current-aim",
                       question="What is the next move and what ordering does it impose?",
                       atoms=atoms or ["run the widget sweep", "correctness comes before cost"],
                       window=window, source="HANDOFF.md", truth_date="2026-08-01")


# --- the clean path --------------------------------------------------------

def test_anchoring_finds_the_span_that_holds_each_atom(view):
    task = _task(view)
    assert len(task.anchors) == 2
    for anchor in task.anchors:
        assert anchor.node_id == "HANDOFF.md"
        assert view.span_by_id(anchor.span_id) is not None


def test_a_frozen_bundle_verifies_and_its_id_is_its_hash(view):
    bundle = freeze_bundle(view, "sha256:" + "a" * 64, [_task(view)])
    assert bundle.bundle_id == bundle.computed_id()
    verify_bundle(bundle, view)


def test_bundle_id_covers_the_corpus_and_the_ground_truth(view):
    """One hash over snapshot + segmentation + universe + tasks + scoring version."""
    a = freeze_bundle(view, "sha256:" + "a" * 64, [_task(view)])
    b = freeze_bundle(view, "sha256:" + "b" * 64, [_task(view)])
    assert a.bundle_id != b.bundle_id, "a different segmentation must be a different bundle"
    c = freeze_bundle(view, "sha256:" + "a" * 64, [_task(view, atoms=["run the widget sweep"])])
    assert a.bundle_id != c.bundle_id, "different ground truth must be a different bundle"


def test_the_clock_is_not_in_the_bundle_id(view):
    a = freeze_bundle(view, "sha256:" + "a" * 64, [_task(view)], frozen_ts="2020-01-01T00:00:00Z")
    b = freeze_bundle(view, "sha256:" + "a" * 64, [_task(view)], frozen_ts="2031-01-01T00:00:00Z")
    assert a.bundle_id == b.bundle_id


# --- the refusals ----------------------------------------------------------

def test_an_atom_that_is_nowhere_refuses_at_anchor_time(view):
    with pytest.raises(AnchorUnresolved) as exc:
        _task(view, atoms=["this string is not in the corpus at all"])
    assert exc.value.reason == "bench-anchor-unresolved"


def test_a_corrupted_anchor_span_refuses(view):
    """THE GATE: an anchor moved to a span that does not hold its atom must refuse."""
    task = _task(view)
    other = next(s for s in view.leaf_spans if s.node_id == "STANDING_LAW.md")
    corrupted = dataclasses.replace(task, anchors=[
        Anchor(node_id=other.node_id, span_id=other.span_id,
               span_content_hash=view.span_content_hash(other), atom_index=0),
        task.anchors[1],
    ])
    with pytest.raises(AnchorUnresolved):
        verify_task(view, corrupted)


def test_a_tampered_anchor_content_hash_refuses(view):
    task = _task(view)
    bad = dataclasses.replace(task.anchors[0], span_content_hash="sha256:" + "0" * 64)
    corrupted = dataclasses.replace(task, anchors=[bad, task.anchors[1]])
    with pytest.raises(AnchorHashMismatch):
        verify_task(view, corrupted)


def test_an_anchor_naming_an_absent_span_refuses(view):
    task = _task(view)
    bad = dataclasses.replace(task.anchors[0], span_id="sha256:" + "f" * 64)
    corrupted = dataclasses.replace(task, anchors=[bad, task.anchors[1]])
    with pytest.raises(AnchorUnresolved):
        verify_task(view, corrupted)


def test_a_bundle_whose_tasks_were_edited_after_freezing_refuses(view):
    bundle = freeze_bundle(view, "sha256:" + "a" * 64, [_task(view)])
    edited = dataclasses.replace(bundle, tasks=[
        dataclasses.replace(bundle.tasks[0], question="a different question entirely")])
    with pytest.raises(BundleIdMismatch):
        verify_bundle(edited, view)


def test_a_bundle_frozen_against_another_snapshot_refuses(view, tmp_path):
    bundle = freeze_bundle(view, "sha256:" + "a" * 64, [_task(view)])
    moved = DOC.replace("run the widget sweep", "run the gizmo sweep")
    other = SnapshotView(open_bundle(build_bundle(tmp_path / "snap2", doc=moved)),
                         BENCH_FILTERED)
    with pytest.raises(BundleIdMismatch):
        verify_bundle(bundle, other)


# --- the decay detector (gate d) -------------------------------------------

def test_a_moved_atom_is_decayed(view, tmp_path):
    """THE GATE: a task whose atom no longer exists must classify as decayed, never as stable."""
    bundle = freeze_bundle(view, "sha256:" + "a" * 64, [_task(view)])
    moved = DOC.replace("run the widget sweep", "run the gizmo sweep")
    newer = SnapshotView(open_bundle(build_bundle(tmp_path / "snap-moved", doc=moved)),
                         BENCH_FILTERED)
    report = re_anchor(bundle, newer)
    assert report["counts"]["decayed"] == 1, report["counts"]
    statuses = [a["status"] for a in report["tasks"][0]["atoms"]]
    assert statuses[0] == "decayed"
    # The SURVIVING atom is re-anchored, not stable, and that is right: rewriting one paragraph
    # changes the node's content hash, which changes every span id in it. "stable" is reserved for
    # an anchor that is still byte-for-byte the span it was frozen against.
    assert statuses[1] == "re-anchored"


def test_an_atom_that_moved_house_is_re_anchored_not_decayed(view, tmp_path):
    """The middle verdict: the atom survives, its span does not. That is re-anchored."""
    bundle = freeze_bundle(view, "sha256:" + "a" * 64, [_task(view)])
    shifted = DOC.replace("## superseded", "## a new heading\n\nfiller line\n\n## superseded")
    newer = SnapshotView(open_bundle(build_bundle(tmp_path / "snap-shift", doc=shifted)),
                         BENCH_FILTERED)
    report = re_anchor(bundle, newer)
    assert report["counts"]["decayed"] == 0
    assert report["counts"]["stable"] + report["counts"]["re-anchored"] == 1


def test_an_unchanged_corpus_re_anchors_to_all_stable(view, tmp_path):
    bundle = freeze_bundle(view, "sha256:" + "a" * 64, [_task(view)])
    same = SnapshotView(open_bundle(build_bundle(tmp_path / "snap-same")), BENCH_FILTERED)
    report = re_anchor(bundle, same)
    assert report["counts"] == {"stable": 1, "re-anchored": 0, "decayed": 0}
