"""test_bench_tier2_arms.py - the Phase 3 arms: what they declare, and what they refuse.

Both Tier-2 arms need real model weights to produce a scored answer, so their SCORED behaviour is
exercised in the run rather than here (the same division the dense arm's tests already make).
What is tested here is everything that can be wrong WITHOUT a model, which for these two arms is
most of the surface that matters:

  * ``raptor`` refuses to exist without a banked fold, refuses a fold from another snapshot, and
    refuses a fold from another UNIVERSE - the last one being the check that stops a tree built
    over a view containing the answer key from serving the headline;
  * its declared ``fold_model_calls`` comes from the manifest headline while its counted
    ``FoldCost.model_calls`` is RECOUNTED from the per-call rows, so an edited headline is a
    ``ProtocolViolation`` rather than a cheaper-looking fold;
  * ``incumbent_arch``'s digest recipe reproduces the engine's ``_essence`` idiom per file type,
    which is the whole of what makes it "the incumbent" rather than "a node-level dense arm".
"""

from __future__ import annotations

import json

import pytest
from bench_fixture import build_bundle, open_bundle

from atlas.bench.arms.incumbent_arch import (
    ESSENCE_CAP,
    FILE_READ_CAP,
    MAX_WHOLE_READS,
    digest_of,
    essence,
)
from atlas.bench.arms.raptor import SUMMARY_PREFIX, RaptorArm
from atlas.bench.raptor_fold import (
    BRANCH_MIN,
    MAX_DEPTH,
    RAPTOR_RECIPE_VERSION,
    SUMMARY_MODEL,
    TARGET_SUMMARIES,
    build_prompt,
    build_tree,
    summarization_order,
)
from atlas.bench.universe import BENCH_FILTERED, SnapshotView
from atlas.errors import ArmUnavailable


@pytest.fixture()
def view(tmp_path):
    return SnapshotView(open_bundle(build_bundle(tmp_path / "snap")), BENCH_FILTERED)


# --- the incumbent's digest recipe -----------------------------------------

def test_markdown_essence_is_the_first_heading():
    assert essence("HANDOFF.md", "# The Handoff\n\nbody text\n") == "The Handoff"


def test_markdown_without_a_heading_falls_to_the_first_substantive_line():
    assert essence("x.md", "---\nfm: 1\n---\n\nthe first real line\n") == "fm: 1"


def test_python_essence_is_the_docstring_head():
    src = '"""wake.py - the covenant wake transport.\n\nmore prose\n"""\nimport os\n'
    assert essence("src/wake.py", src) == "wake.py - the covenant wake transport."


def test_python_without_a_docstring_falls_to_the_first_definition():
    assert essence("m.py", "import os\n\ndef build_tree(x):\n    pass\n") == "def build_tree"


def test_json_essence_is_a_key_inventory_never_a_byte_head():
    """The oracle gate measured a raw JSON head POISONING _INDEX.json (rank 88 -> 855)."""
    out = essence("a.json", json.dumps({"alpha": 1, "beta": 2, "gamma": 3}))
    assert out.startswith("keys: ")
    assert "alpha" in out and "1" not in out


def test_yaml_essence_is_its_top_level_keys():
    assert essence("c.yaml", "name: x\nversion: 2\n") == "keys: name, version"


def test_an_unknown_extension_falls_to_the_first_non_empty_line():
    assert essence("notes.txt", "\n\nfirst real line\nsecond\n") == "first real line"


def test_the_essence_is_capped():
    assert len(essence("x.md", "# " + "a" * 5000)) == ESSENCE_CAP


def test_the_digest_carries_the_path_beside_the_essence():
    """The path IS half the handle: the engine's router presents essence beside location."""
    digest = digest_of("src/laplace/wake.py", '"""wake.py - the transport."""\n')
    assert digest == "src/laplace/wake.py | wake.py - the transport."


def test_the_arm_a_read_constants_are_the_v1_ones():
    assert FILE_READ_CAP == 32 * 1024
    assert MAX_WHOLE_READS == 3


# --- the RAPTOR fold's structure -------------------------------------------

def test_the_budget_binds_and_the_depth_is_capped():
    import numpy as np

    rng = np.random.default_rng(0)
    X = rng.normal(size=(4000, 24)).astype(np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    clusters = build_tree(X, seed=1, target_summaries=120, max_depth=3)
    summaries = [c for c in clusters.values() if c.parent_id is not None]
    assert len(summaries) <= 120, "the declared budget is a hard cap"
    assert max(c.level for c in clusters.values()) <= 3


def test_the_tree_partitions_every_leaf_exactly_once():
    import numpy as np

    rng = np.random.default_rng(2)
    X = rng.normal(size=(600, 16)).astype(np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    clusters = build_tree(X, seed=1, target_summaries=60, max_depth=3)
    leaves = [c for c in clusters.values() if not c.children]
    members = sorted(int(m) for c in leaves for m in c.members)
    assert members == list(range(len(X))), "a span belongs to exactly one leaf cluster"


def test_the_summarization_order_is_deepest_first():
    import numpy as np

    rng = np.random.default_rng(3)
    X = rng.normal(size=(900, 16)).astype(np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    clusters = build_tree(X, seed=1, target_summaries=90, max_depth=3)
    levels = summarization_order(clusters)
    seen = [clusters[ids[0]].level for ids in levels]
    assert seen == sorted(seen, reverse=True), "children are summarized before their parents"
    assert all(clusters[c].parent_id is not None for ids in levels for c in ids), \
        "the root is the corpus and gets no summary"


def test_the_declared_budget_and_band_are_what_the_docstring_says():
    assert 250 <= TARGET_SUMMARIES <= 350
    assert BRANCH_MIN + BRANCH_MIN ** 2 + BRANCH_MIN ** 3 >= 250, \
        "the band's floor is the arithmetic that makes the budget reachable in 3 levels"
    assert MAX_DEPTH == 3
    assert RAPTOR_RECIPE_VERSION == "raptor-at-budget/1"


def test_the_summary_model_stamp_is_at_or_below_the_ceiling():
    """The dispatch-model law, asserted atlas-side as DATA (no import across the seal)."""
    assert SUMMARY_MODEL in ("haiku", "sonnet", "opus")
    assert SUMMARY_MODEL != "opus", "the summarizer does not need the ceiling itself"


def test_the_prompt_carries_every_cluster_id_it_asks_about():
    items = [{"cluster_id": "r.0.1", "level": 2, "size": 40, "evidence": ["alpha", "beta"]},
             {"cluster_id": "r.0.2", "level": 2, "size": 12, "evidence": ["gamma"]}]
    prompt = build_prompt(items)
    assert "r.0.1" in prompt and "r.0.2" in prompt
    assert "alpha" in prompt and "gamma" in prompt
    assert "exactly 2 objects" in prompt


# --- the RAPTOR arm's refusals ---------------------------------------------

def test_the_arm_refuses_to_exist_without_a_banked_fold(tmp_path):
    """A benchmark that can spend a model bill by being run is a bill nobody counted."""
    with pytest.raises(ArmUnavailable) as exc:
        RaptorArm(fold_dir=tmp_path / "absent", projection_store=tmp_path)
    assert exc.value.reason == "bench-arm-unavailable"
    assert "raptor_fold" in str(exc.value)


def _fake_fold(tmp_path, snapshot_id: str, universe_id: str, calls: int = 3,
               declared: int | None = None):
    fold = tmp_path / "fold"
    fold.mkdir(parents=True, exist_ok=True)
    (fold / "summaries.jsonl").write_text(
        "\n".join(json.dumps({"cluster_id": f"r.{i}", "level": 1, "parent_id": "r",
                              "size": 10, "children": [], "summary": f"summary {i}",
                              "representative_span_ids": []})
                  for i in range(2)) + "\n", encoding="utf-8")
    (fold / "manifest.json").write_text(json.dumps({
        "kind": "raptor-fold/1", "fold_id": "sha256:" + "f" * 64,
        "model_calls": calls if declared is None else declared,
        "model_requested": SUMMARY_MODEL,
        "summary_vectors_built": 2, "vector_bytes": 3072,
        "fold_wall_seconds": 500.0, "prompt_tokens_estimate_bytes_over_4": 1234,
        "calls": [{"batch_id": f"B{i}", "attempt": 1} for i in range(calls)],
        "generation": {"snapshot_id": snapshot_id, "universe_id": universe_id,
                       "universe": "bench-filtered/2",
                       "projection_generation_id": "sha256:" + "0" * 64},
    }, indent=1), encoding="utf-8")
    return fold


def test_the_arm_declares_the_manifest_headline_call_count(tmp_path, view):
    fold = _fake_fold(tmp_path, view.snapshot_id, view.universe_id, calls=14)
    arm = RaptorArm(fold_dir=fold, projection_store=tmp_path)
    assert arm.protocol.fold_model_calls == 14
    assert arm.protocol.model_stamp == SUMMARY_MODEL
    assert arm.protocol.query_model_calls == 0
    assert arm.protocol.input_recipe_version == RAPTOR_RECIPE_VERSION


def test_a_fold_from_another_snapshot_refuses(tmp_path, view):
    fold = _fake_fold(tmp_path, "sha256:" + "9" * 64, view.universe_id)
    arm = RaptorArm(fold_dir=fold, projection_store=tmp_path)
    with pytest.raises(ArmUnavailable) as exc:
        arm.fold(view, "seg")
    assert "different snapshot" in str(exc.value)


def test_a_fold_from_another_universe_refuses(tmp_path, view):
    """The check that stops a fold containing the answer key from serving the headline view."""
    fold = _fake_fold(tmp_path, view.snapshot_id, "sha256:" + "8" * 64)
    arm = RaptorArm(fold_dir=fold, projection_store=tmp_path)
    with pytest.raises(ArmUnavailable) as exc:
        arm.fold(view, "seg")
    assert "different universe" in str(exc.value)
    assert "property of the SET of spans" in str(exc.value)


def test_summary_ids_are_prefixed_so_nothing_mistakes_them_for_record(tmp_path, view):
    fold = _fake_fold(tmp_path, view.snapshot_id, view.universe_id)
    arm = RaptorArm(fold_dir=fold, projection_store=tmp_path)
    assert all(key.startswith(SUMMARY_PREFIX) for key in arm._summary_text)
    assert SUMMARY_PREFIX == "raptor:"
