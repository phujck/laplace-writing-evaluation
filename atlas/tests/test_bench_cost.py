"""test_bench_cost.py - THE COUNTING WRAPPER GATE (Phase 2 gate e).

The claim the whole cost shape rests on is that query-time model calls are COUNTED, not declared,
and that every byte reaching a scoring context is measured as it passes. This file proves both
mechanically:

  * ``tokens_touched`` is zero before a read and moves by exactly the span's size after it;
  * a whole-file read counts against the whole-file budget and the excerpt form charges only the
    excerpt while reporting the rest as scan bytes;
  * the reader REFUSES past the arm's declared caps, so an arm cannot quietly read deeper than
    its competitors and win on spend (seam J6);
  * an arm that declared zero query model calls and makes one is ``ProtocolViolation``;
  * EVERY TIER-1 ARM DECLARES ZERO, asserted here on the protocols themselves.

The five cost dimensions are also checked for the one property that makes them five: no method
on ``ArmCost`` returns a total, and the amortized fold refuses to exist without a stated
reference query count.
"""

from __future__ import annotations

import pytest
from bench_fixture import build_bundle, open_bundle

from atlas.bench.arms import Bm25Arm, DenseFlatArm, FlatReadArm, GrepSkilledArm
from atlas.bench.cost import ArmCost, FoldCost, ModelCounter, SpanReader, tokens_of
from atlas.bench.universe import BENCH_FILTERED, SnapshotView
from atlas.errors import ProtocolViolation


@pytest.fixture()
def view(tmp_path):
    return SnapshotView(open_bundle(build_bundle(tmp_path / "snap")), BENCH_FILTERED)


# --- the reading wrapper ---------------------------------------------------

def test_tokens_touched_starts_at_zero_and_moves_on_a_span_read(view):
    reader = SpanReader(view)
    assert reader.tokens_touched == 0
    assert reader.spans_read == 0
    span = view.leaf_spans[0]
    text = reader.read_span(span)
    assert reader.spans_read == 1
    assert reader.bytes_served == len(text.encode("utf-8"))
    assert reader.tokens_touched == tokens_of(text)
    assert reader.tokens_touched > 0


def test_a_second_read_adds_to_the_count(view):
    reader = SpanReader(view)
    a = reader.read_span(view.leaf_spans[0])
    b = reader.read_span(view.leaf_spans[1])
    assert reader.bytes_served == len(a.encode("utf-8")) + len(b.encode("utf-8"))
    assert reader.spans_read == 2


def test_a_whole_file_read_counts_against_the_whole_file_budget(view):
    reader = SpanReader(view, max_whole_file_reads=1)
    reader.read_node("HANDOFF.md")
    assert reader.whole_file_reads == 1
    with pytest.raises(ProtocolViolation) as exc:
        reader.read_node("STANDING_LAW.md")
    assert exc.value.reason == "bench-protocol-violation"


def test_an_excerpt_charges_the_excerpt_and_scans_the_rest(view):
    reader = SpanReader(view)
    whole = view.node_text("HANDOFF.md")
    excerpt = whole[:20]
    reader.read_node_excerpt("HANDOFF.md", excerpt)
    assert reader.bytes_served == len(excerpt.encode("utf-8"))
    assert reader.scan_bytes == len(whole.encode("utf-8")) - len(excerpt.encode("utf-8"))
    assert reader.whole_file_reads == 1


def test_scan_bytes_are_never_inside_tokens_touched(view):
    reader = SpanReader(view)
    reader.scan(10_000)
    assert reader.scan_bytes == 10_000
    assert reader.tokens_touched == 0


def test_the_span_read_cap_refuses(view):
    reader = SpanReader(view, max_spans_read=1)
    reader.read_span(view.leaf_spans[0])
    with pytest.raises(ProtocolViolation):
        reader.read_span(view.leaf_spans[1])


def test_the_byte_budget_refuses_before_serving(view):
    reader = SpanReader(view, read_budget_bytes=5)
    with pytest.raises(ProtocolViolation):
        reader.read_span(view.leaf_spans[0])
    assert reader.bytes_served == 0, "a refused read must not be charged"


# --- the model counter -----------------------------------------------------

def test_the_model_counter_counts():
    counter = ModelCounter("test")
    assert counter.calls == 0
    counter.call(lambda: "answer", tokens=17)
    assert counter.calls == 1 and counter.tokens == 17


def test_a_declared_zero_that_calls_once_refuses():
    counter = ModelCounter("test")
    counter.assert_declared(0)
    counter.call(lambda: None)
    with pytest.raises(ProtocolViolation) as exc:
        counter.assert_declared(0)
    assert exc.value.detail == {"arm": "test", "declared": 0, "counted": 1}


def test_every_tier_1_arm_declares_zero_query_model_calls():
    """The cost-shape floor: mechanical arms, and the count is checked at every row."""
    arms = [FlatReadArm("B"), FlatReadArm("B+"), GrepSkilledArm(), Bm25Arm(), DenseFlatArm()]
    for arm in arms:
        assert arm.protocol.query_model_calls == 0, arm.protocol.full_id
        assert arm.protocol.fold_model_calls == 0, arm.protocol.full_id
        assert arm.protocol.model_stamp == "none", arm.protocol.full_id


# --- the five dimensions ---------------------------------------------------

def test_the_fold_bill_is_not_the_reload_cost():
    """Seam J7 in one assertion: a cached fold reports what the index COST, not what it cost to
    reload. An arm whose fold bill vanishes when the cache is warm has hidden the bill."""
    warm = FoldCost(wall_seconds=4160.5, wall_seconds_this_call=0.19, vectors_built=0,
                    cached=True)
    assert warm.to_dict()["wall_seconds"] == 4160.5
    assert warm.to_dict()["wall_seconds_this_call"] == 0.19
    assert warm.amortized(21)["wall_seconds_per_query"] > 100, (
        "the amortized fold must amortize the BILL, not the reload")


def test_the_amortized_fold_needs_a_stated_reference_count():
    fold = FoldCost(wall_seconds=10.0, vectors_built=100)
    assert fold.amortized(20)["reference_query_count"] == 20
    assert fold.amortized(20)["wall_seconds_per_query"] == 0.5
    with pytest.raises(ProtocolViolation):
        fold.amortized(0)


def test_arm_cost_never_serves_a_total():
    cost = ArmCost(arm_id="x", fold=FoldCost(wall_seconds=1.0), fold_reference_query_count=2,
                   tokens_touched_median=5, latency_median_ms=3.0)
    d = cost.to_dict()
    assert "total" not in d
    assert set(d) == {"arm", "fold", "fold_amortized_per_query", "query_model_calls",
                      "query_model_tokens", "tokens_touched", "scan_bytes_total_uncharged",
                      "latency_ms"}
