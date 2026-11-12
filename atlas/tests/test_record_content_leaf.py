"""test_record_content_leaf.py - the leaf carries its content, and the switch has an OFF.

Six properties, each the mechanical form of one must_achieve of packet
P1-THE-LEAF-CARRIES-ITS-CONTENT:

  1. the segmentation recipe is DECLARED and an invalid dial refuses BY NAME, with the same
     names the old store path uses (``src/atlas/dataset.py:167-171``);
  2. with no axis declared the declaration hash is what every earlier wave measured - the
     QASPER rung-(ab) hash is asserted against the one banked in E1's own measurement file;
  3. the cut honours the declared cap and PARTITIONS the text (no hole, no overlap);
  4. the stored form is D.7's, with eps measured rather than assumed, and the bytes on disk are
     D.9's published function of (arity, rank, dtype);
  5. the token column is ``extension/lexical_index.py``'s own function, asserted equal to it;
  6. a segment round-trips: ingest -> store -> open in a fresh process state gives the SAME
     content digests, the same leaf count, and an open that extracts nothing and parses nothing.

Run: ``scripts/laplace-python -m pytest atlas/tests/test_record_content_leaf.py
--basetemp=/tmp/pytest-p1-leaf``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from atlas.encoders.span_encoder import dequantise, quantise
from atlas.record import content as CT
from atlas.record import segments as S
from atlas.record.declaration import SegmentationRecipe
from atlas.record.errors import DeclarationRefused
from atlas.record.extract import extractor_roster_hash
from atlas.record.ingest import longmem, qasper

REPO = Path(__file__).resolve().parents[2]
E1 = (REPO / "evidence/ATLAS_PROGRAMME/waves/F2-assembly/E1/measurement.json")

CONTENT = {"target_tokens": 96, "hard_cap_tokens": 256,
           "axes": [{"axis": "content", "encoder_id": "bge-small-en-v1.5/onnx-fp16/1",
                     "dim": 384, "dtype": "int8", "tokens": True}]}


# --------------------------------------------------------------- 1 the declared dial refuses
@pytest.mark.parametrize("dials, code", [
    ({"target_tokens": 300, "hard_cap_tokens": 200}, "SEGMENTATION-DIAL-INVALID"),
    ({"target_tokens": 96, "hard_cap_tokens": 600}, "SEGMENTATION-DIAL-INVALID"),
    ({"target_tokens": 0, "hard_cap_tokens": 200}, "SEGMENTATION-DIAL-INVALID"),
    ({"target_tokens": 96.0, "hard_cap_tokens": 200}, "SEGMENTATION-DIAL-INVALID"),
])
def test_an_invalid_segmentation_dial_refuses_by_name(dials, code):
    with pytest.raises(DeclarationRefused) as raised:
        longmem.declaration("ab", content={**dials, "axes": CONTENT["axes"]})
    assert raised.value.detail["code"] == code


def test_an_unknown_recipe_generation_refuses_by_name():
    with pytest.raises(DeclarationRefused) as raised:
        longmem.declaration("ab", content={**CONTENT, "generation": "seg/0"})
    assert raised.value.detail["code"] == "SEGMENTATION-GENERATION-UNKNOWN"


def test_an_axis_without_a_recipe_refuses_by_name():
    from atlas.record.declaration import ContentAxisSpec, ContentCarrier, DatasetDeclaration
    base = longmem.declaration("ab")
    axis = ContentAxisSpec("content", "bge-small-en-v1.5/onnx-fp16/1", 384, "int8",
                           (ContentCarrier("turn", "content_span", "json_string"),))
    with pytest.raises(DeclarationRefused) as raised:
        DatasetDeclaration(dataset_id=base.dataset_id, row_kinds=base.row_kinds,
                           relation_kinds=base.relation_kinds, alias_table=base.alias_table,
                           surface_set=base.surface_set, segmenter_id=base.segmenter_id,
                           seg_version=base.seg_version, blob_glob=base.blob_glob,
                           content_axes=(axis,))
    assert raised.value.detail["code"] == "CONTENT-AXIS-WITHOUT-A-RECIPE"


def test_an_unknown_stored_form_refuses_by_name():
    with pytest.raises(DeclarationRefused) as raised:
        longmem.declaration("ab", content={**CONTENT, "axes": [
            {**CONTENT["axes"][0], "dtype": "float64"}]})
    assert raised.value.detail["code"] == "CONTENT-AXIS-DTYPE-INVALID"


# ----------------------------------------------------- 2 the OFF position is bit for bit
def test_with_no_axis_declared_the_declaration_hash_is_the_one_E1_measured():
    """The ablation's OFF position, asserted against a BANKED number rather than a rerun."""
    banked = json.loads(E1.read_text())["qasper"]["rung_ab"]["dataset_declaration_hash"]
    assert qasper.declaration("ab").declaration_hash == banked
    assert qasper.declaration("ab").content_axes == ()
    assert qasper.declaration("ab").segmentation is None


def test_declaring_an_axis_changes_the_declaration_hash_and_nothing_else_does():
    off = longmem.declaration("ab")
    on = longmem.declaration("ab", content=CONTENT)
    assert off.declaration_hash != on.declaration_hash
    assert [k.kind for k in off.row_kinds] == [k.kind for k in on.row_kinds]
    assert [k.hashed() for k in off.row_kinds] == [k.hashed() for k in on.row_kinds]
    assert off.hashed() == {k: v for k, v in on.hashed().items()
                            if k not in ("segmentation", "content_axes")}


# ------------------------------------------------------------- 3 the cut is a partition
@pytest.mark.parametrize("target, cap", [(8, 16), (96, 256), (1, 2)])
def test_the_cut_partitions_the_text_and_honours_the_declared_cap(target, cap):
    recipe = SegmentationRecipe("record-seg/1", target, cap, "1")
    text = ("alpha beta gamma. delta epsilon zeta.\n\n" * 20) + ("x" * 900)
    ranges, blind = CT.cut_by_recipe(text, recipe)
    assert ranges
    assert ranges[0][0] == 0 and ranges[-1][1] == len(text)
    for (a, b), (c, _d) in zip(ranges, ranges[1:]):
        assert a < b == c                       # contiguous, no hole and no overlap
    assert max(b - a for a, b in ranges) <= cap * CT.CHARS_PER_TOKEN
    assert blind >= 0


def test_an_empty_text_cuts_to_nothing():
    assert CT.cut_by_recipe("", SegmentationRecipe("record-seg/1", 96, 256, "1")) == ([], 0)


# ------------------------------------------------- 4 the stored form is D.7's, eps measured
def test_the_int8_store_measures_its_own_eps_and_costs_what_D9_publishes():
    rng = np.random.default_rng(20260922)
    exact = rng.normal(size=(64, 384)).astype(np.float32)
    exact /= np.linalg.norm(exact, axis=1, keepdims=True)
    stored = quantise(exact, "int8")
    back = dequantise(stored["code"], stored["scale"], "int8")
    measured = np.linalg.norm(back - exact, axis=1)
    assert np.allclose(measured, stored["eps"], atol=1e-6)      # eps is MEASURED, not assumed
    assert stored["code"].dtype == np.int8
    axis = longmem.declaration("ab", content=CONTENT).content_axes[0]
    assert axis.bytes_per_span() == 384 * 1 + 8                 # D.9: r*bits/8 + overhead(int8)
    per_row = (stored["code"].nbytes + stored["scale"].nbytes + stored["eps"].nbytes) / 64
    assert per_row == axis.bytes_per_span()

    exact_form = quantise(exact, "f32")
    assert float(exact_form["eps"].max()) == 0.0                # D.7: eps is identically zero


# ------------------------------------------------------- 5 the token column is the lift
def test_normalize_tokens_is_the_extensions_own_function():
    path = (REPO / "synthetics papers/corpus-as-a-state/reconstruction/extension"
                   "/lexical_index.py")
    source = path.read_text(encoding="utf-8")
    # Import the extension module's function without importing the module (it pulls torch and a
    # sibling gpu_budget): compile just the two objects the lift names, :28-34.
    namespace: dict = {}
    start = source.index("_TOKEN = re.compile")
    end = source.index("@dataclass", start)
    exec("import re, unicodedata\n" + source[start:end], namespace)   # noqa: S102
    theirs = namespace["normalize_tokens"]
    for text in ("The Farmer's fox-cage, 2023!", "naive naïve NAÏVE",
                 "don’t stop — keep_going", ""):
        assert CT.normalize_tokens(text) == theirs(text)


# ------------------------------------------------ 6 the segment round trip, cold == warm
@pytest.mark.skipif(not longmem.DATASET_PATH.exists(), reason="LongMemEval-S is not on disk")
def test_the_leaf_and_its_observations_survive_the_segment_store(tmp_path):
    store = S.SegmentStore(tmp_path / "record")
    cold = longmem.ingest(histories=2, rungs="ab", segments=store, content=CONTENT)
    cold_receipt = cold.persistence
    assert cold_receipt is not None
    assert cold_receipt.content["leaves_built"] > 0
    cold_digests = S.content_digests(cold)
    assert any(key.startswith("content.") for key in cold_digests)

    opened = S.open_record(store, longmem.declaration("ab", content=CONTENT), rung=1)
    assert opened.receipt.extractions == 0 and opened.receipt.parses == 0
    assert opened.receipt.source_reads == 0
    assert len(opened.ingestion.content) == len(cold.content)
    for key, value in cold_digests.items():
        assert opened.receipt.digests[key] == value, key

    # a SECOND ingest against the same store parses nothing and extracts nothing
    warm = longmem.ingest(histories=2, rungs="ab", segments=store, content=CONTENT)
    assert warm.counters["item_parses"] == 0
    assert warm.counters["extractions"] == 0
    assert warm.counters["segment_hits"] == 2
    assert len(warm.content) == len(cold.content)


@pytest.mark.skipif(not longmem.DATASET_PATH.exists(), reason="LongMemEval-S is not on disk")
def test_an_items_segment_does_not_depend_on_what_else_is_in_the_store(tmp_path):
    """B.28's purity, with the content leaves inside the segment.

    The first haystack's segment is cut twice: once in an ingestion that holds only it, once in
    an ingestion that holds it and a second haystack. If the two segment keys agree, the item's
    bytes - vectors, token codes, surfaces and all - are a pure function of THAT item, which is
    the single property that makes the store a cache rather than a snapshot.
    """
    alone = S.SegmentStore(tmp_path / "alone")
    longmem.ingest(histories=1, rungs="ab", segments=alone, content=CONTENT)
    together = S.SegmentStore(tmp_path / "together")
    longmem.ingest(histories=2, rungs="ab", segments=together, content=CONTENT)

    one, two = alone.cache_index(), together.cache_index()
    assert len(one) == 1 and len(two) == 2
    shared = set(one) & set(two)
    assert shared, "the same haystack must take the same B.28 cache key in both ingestions"
    for key in shared:
        assert one[key] == two[key]
