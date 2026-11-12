"""test_bench_universe.py - the declared filtered view: exclusions as data, refusals as behaviour.

The author's ruling makes the bench corpus a declared filtered VIEW, hashed into the bundle's
identity, with the full universe run as a control. Three properties follow and each is tested:

  * the exclusion list IS the identity - two specs with different exclusions have different
    universe ids, and a rename is visible because the name is hashed too;
  * a view REFUSES what it excludes rather than serving it quietly - an arm cannot accidentally
    read a vendored bundle and then report a corpus-wide number;
  * the FULL universe is a view like any other, with an empty exclusion list and the same code
    path, so the control is a control and not a special case.

The glob semantics are pinned by a test as well, because ``*`` crossing ``/`` is the difference
between excluding the nested vector cache and leaving it in the corpus.
"""

from __future__ import annotations

import pytest
from bench_fixture import build_bundle, open_bundle

from atlas.bench.universe import (
    BENCH_FILTERED,
    FULL_UNIVERSE,
    RULED_ONLY,
    PlantedSpan,
    SnapshotView,
    UniverseSpec,
    with_planted,
)
from atlas.errors import UniverseViolation


@pytest.fixture()
def bundle(tmp_path):
    return open_bundle(build_bundle(tmp_path / "snap"))


def test_the_exclusion_list_is_the_identity():
    a = UniverseSpec(name="x", exclude_prefixes=("a/",))
    b = UniverseSpec(name="x", exclude_prefixes=("b/",))
    c = UniverseSpec(name="y", exclude_prefixes=("a/",))
    d = UniverseSpec(name="x", exclude_prefixes=("a/",), reason="prose does not define identity")
    assert a.universe_id != b.universe_id
    assert a.universe_id != c.universe_id
    assert a.universe_id == d.universe_id


def test_the_filtered_view_excludes_and_the_full_view_does_not(bundle):
    filtered = SnapshotView(bundle, BENCH_FILTERED)
    full = SnapshotView(bundle, FULL_UNIVERSE)
    assert "node_modules/vendor.md" not in filtered.node_ids
    assert "node_modules/vendor.md" in full.node_ids
    assert filtered.stats()["nodes_excluded"] == 1
    assert full.stats()["nodes_excluded"] == 0


def test_reading_an_excluded_node_refuses(bundle):
    view = SnapshotView(bundle, BENCH_FILTERED)
    with pytest.raises(UniverseViolation) as exc:
        view.node_text("node_modules/vendor.md")
    assert exc.value.reason == "bench-universe-violation"


def test_sealed_nodes_are_in_no_view(bundle):
    for spec in (BENCH_FILTERED, FULL_UNIVERSE):
        view = SnapshotView(bundle, spec)
        assert "soul/private.md" not in view.node_ids
        with pytest.raises(UniverseViolation):
            view.node_text("soul/private.md")


def test_leaf_spans_of_an_excluded_node_are_not_in_the_view(bundle):
    filtered = SnapshotView(bundle, BENCH_FILTERED)
    full = SnapshotView(bundle, FULL_UNIVERSE)
    assert all(s.node_id != "node_modules/vendor.md" for s in filtered.leaf_spans)
    assert any(s.node_id == "node_modules/vendor.md" for s in full.leaf_spans)
    assert len(full.leaf_spans) > len(filtered.leaf_spans)


def test_the_glob_star_crosses_path_separators():
    """Pinned because it decides whether the nested vector cache is in the corpus."""
    spec = UniverseSpec(name="t", exclude_globs=("corpus_stores/*/embeddings.json",))
    assert spec.excludes("corpus_stores/a/embeddings.json")
    assert spec.excludes("corpus_stores/a/b/embeddings.json")
    assert not spec.excludes("corpus_stores/a/other.json")


def test_the_ruled_universe_names_exactly_the_three_ruled_families():
    """The author's ruling, as data. A change here is a change to the measured corpus."""
    assert RULED_ONLY.exclude_prefixes == (
        "node_modules/", "src/laplace/static_shared/", "atlas/stores/")
    assert RULED_ONLY.exclude_globs == ("corpus_stores/*/embeddings.json", "*.npz")
    assert FULL_UNIVERSE.exclude_prefixes == () and FULL_UNIVERSE.exclude_globs == ()


def test_the_derived_ground_truth_exclusion_is_a_superset_of_the_ruled_one():
    """The derived fourth family adds to the ruling and never quietly edits it."""
    assert set(RULED_ONLY.exclude_prefixes) < set(BENCH_FILTERED.exclude_prefixes)
    assert set(RULED_ONLY.exclude_globs) < set(BENCH_FILTERED.exclude_globs)
    assert RULED_ONLY.universe_id != BENCH_FILTERED.universe_id


def test_the_answer_key_is_outside_the_headline_universe_and_inside_the_ruled_one():
    """The measured contamination: the v1 task file pairs every question with its atoms."""
    key = "scripts/reconstruction_bench_tasks.json"
    assert BENCH_FILTERED.excludes(key)
    assert not RULED_ONLY.excludes(key)
    assert not FULL_UNIVERSE.excludes(key)
    for frozen in ("atlas/bench/tasks/abc/tasks.json",
                   "atlas/tests/fixtures/scoring_parity_2026-07-28.json"):
        assert BENCH_FILTERED.excludes(frozen)
        assert not RULED_ONLY.excludes(frozen)


def test_the_v1_evidence_bundle_stays_in_every_universe():
    """One task's correct answer is prose in that bundle; excluding it would be over-reach."""
    for path in ("evidence/reconstruction_bench_2026-07-28/README.md",
                 "evidence/reconstruction_bench_2026-07-28/rows.json"):
        for spec in (BENCH_FILTERED, RULED_ONLY, FULL_UNIVERSE):
            assert not spec.excludes(path), (spec.name, path)


def test_span_content_hash_is_the_span_not_the_node(bundle):
    view = SnapshotView(bundle, BENCH_FILTERED)
    spans = [s for s in view.leaf_spans if s.node_id == "HANDOFF.md"]
    assert len(spans) > 1, "the fixture doc must cut into several spans for this to mean anything"
    hashes = {view.span_content_hash(s) for s in spans}
    assert len(hashes) == len(spans)
    assert all(h != spans[0].source_content_hash for h in hashes)


def test_planting_never_touches_the_snapshot(bundle):
    view = SnapshotView(bundle, BENCH_FILTERED)
    before = len(view.leaf_spans)
    planted = [PlantedSpan(planted_id="planted:x", node_id="planted/x.md",
                           text="a plausible but wrong answer", targets_task="T1",
                           wrong_atoms=["wrong answer"])]
    copy = with_planted(view, planted)
    assert len(copy.leaf_spans) == before + 1
    assert len(view.leaf_spans) == before, "the original view must be untouched"
    span = copy.span_by_id("planted:x")
    assert copy.span_text(span) == "a plausible but wrong answer"
    assert view.span_by_id("planted:x") is None
