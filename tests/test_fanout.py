"""THE FANOUT (audit §A4): the pipeline's fan-out width / batch bound.

pack() is the greedy char-budget batcher (the wf_fold_up precedent); chunk() is
the fixed-width slicer (the wf_fold_person precedent); width()/batch_max_chars()
read the fanout dial group with honest defaults. The banked law: the DEFAULT is
uncapped (max_width=0 → one batch = the whole list), byte-identical to the
pre-F2 uncapped fan-out.
"""
import json

import pytest

from laplace.pipeline import fanout
from laplace.pipeline import dials


# ---- pack: greedy char-budget batches --------------------------------------

def test_pack_respects_budget():
    # each item is 3 chars ("aaa"); budget 7 fits at most 2 per batch (6 <= 7).
    items = ["aaa", "bbb", "ccc", "ddd", "eee"]
    batches = fanout.pack(items, 7)
    assert batches == [["aaa", "bbb"], ["ccc", "ddd"], ["eee"]]
    for b in batches:
        assert sum(len(x) for x in b) <= 7


def test_pack_preserves_order():
    items = [str(i) for i in range(20)]
    batches = fanout.pack(items, 5)
    assert [x for b in batches for x in b] == items   # flatten == input, in order


def test_pack_oversized_item_is_its_own_batch():
    # a single item larger than the budget can never fit — it gets its own batch,
    # never dropped, never wedged in with a neighbour.
    items = ["a", "TOOBIG_WAY_OVER_BUDGET", "b"]
    batches = fanout.pack(items, 5)
    assert ["TOOBIG_WAY_OVER_BUDGET"] in batches
    assert batches == [["a"], ["TOOBIG_WAY_OVER_BUDGET"], ["b"]]
    # every item survives exactly once
    assert [x for b in batches for x in b] == items


def test_pack_never_empty_batch():
    for batches in (fanout.pack(["a", "b", "c"], 1),
                    fanout.pack(["xx", "yy"], 100)):
        assert all(len(b) >= 1 for b in batches)


def test_pack_empty_input():
    assert fanout.pack([], 100) == []


def test_pack_size_fn_json():
    # the wf_fold idiom: budget on the JSON-serialised size.
    items = [{"k": 1}, {"k": 2}, {"k": 3}]
    size = lambda it: len(json.dumps(it))
    batches = fanout.pack(items, len(json.dumps({"k": 1})) * 2, size_fn=size)
    # each JSON blob is 8 chars ('{"k": 1}'), budget 16 => 2 per batch
    assert batches == [[{"k": 1}, {"k": 2}], [{"k": 3}]]
    for b in batches:
        assert sum(size(x) for x in b) <= 16


# ---- chunk: fixed-width slices ---------------------------------------------

def test_chunk_fixed_width():
    assert fanout.chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    assert fanout.chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]
    assert fanout.chunk([1, 2, 3], 1) == [[1], [2], [3]]
    assert fanout.chunk([1, 2, 3], 10) == [[1, 2, 3]]


def test_chunk_width_zero_is_uncapped():
    # width 0 (the default) = one batch = the whole list: byte-identical to the
    # pre-F2 uncapped fan-out. Empty input still yields no batch.
    assert fanout.chunk([1, 2, 3], 0) == [[1, 2, 3]]
    assert fanout.chunk([1, 2, 3], -1) == [[1, 2, 3]]
    assert fanout.chunk([], 0) == []


def test_chunk_preserves_order_and_completeness():
    items = list(range(23))
    for w in (1, 3, 7, 23, 100):
        batches = fanout.chunk(items, w)
        assert [x for b in batches for x in b] == items
        assert all(len(b) <= w for b in batches)


def test_chunk_empty_input():
    assert fanout.chunk([], 5) == []


# ---- width()/batch_max_chars(): read the dial group ------------------------

def test_width_reads_dials_default_uncapped():
    d = dials.load_dials()
    assert fanout.width(d) == 0                 # UNCAPPED by default
    assert fanout.batch_max_chars(d) == 140000


def test_width_reads_dial_override(tmp_path):
    prof = tmp_path / "dials.yaml"
    prof.write_text("fanout:\n  max_width: 12\n  batch_max_chars: 5000\n",
                    encoding="utf-8")
    d = dials.load_dials(prof)
    assert fanout.width(d) == 12
    assert fanout.batch_max_chars(d) == 5000


def test_width_honest_default_on_missing_group():
    # a dials object with no fanout group reads as uncapped, never a surprise cap.
    assert fanout.width({}) == 0
    assert fanout.width({"fanout": {}}) == 0
    assert fanout.batch_max_chars({}) == 140000


def test_width_then_chunk_is_uncapped_at_default():
    # the integration invariant: chunk(items, width(defaults)) is ONE batch =
    # the whole list — the JS chunkList(_, FANOUT=0) inertness, mirrored.
    d = dials.load_dials()
    items = list(range(50))
    assert fanout.chunk(items, fanout.width(d)) == [items]
