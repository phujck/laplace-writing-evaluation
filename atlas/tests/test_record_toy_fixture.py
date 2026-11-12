"""The toy tables must EQUAL the fixture's. Both directions, every field, every edge, every posting.

``evidence/ATLAS_PROGRAMME/lane_c/toy_corpus.py`` is the row inventory every lane-C clause
executes against, and packet I1's bar is exact equality, not resemblance. So this file compares
the built store against the fixture field by field, the anchor postings against ``MENTIONS`` in
both directions, and the relations against ``RELATIONS`` as an ordered list AND as a set.
"""

from __future__ import annotations

import pytest
import torch

from atlas.record.ingest import toy

cuda = pytest.mark.skipif(not torch.cuda.is_available(),
                          reason="the record layer's numeric core is CUDA-only by policy")


@pytest.fixture(scope="module")
def built():
    return toy.ingest()


@cuda
def test_record_toy_rows_equal_the_fixture_field_by_field(built):
    fixture, store = built.fixture, built.ingestion.store
    table = store.table("toy_row")
    assert len(table) == fixture.ROW_COUNT == 10
    assert built.local_row_ids == tuple(row["row_id"] for row in fixture.ROWS), (
        "every fixture row is admitted, in the fixture's order")
    declared = [f.name for f in table.spec.fields]
    assert set(declared) | {"row_id", "span_id"} == set(fixture.COLUMNS), (
        "the closed column list is the fixture's columns, minus the two that are addresses")
    built_rows = table.rows()
    for position, name in enumerate(built.local_row_ids):
        expected = fixture.ROW_BY_ID[name]
        for column in declared:
            assert built_rows[position][column] == expected[column], (
                f"row {name} column {column} differs from the fixture")


@cuda
def test_record_toy_witness_is_the_turn_the_fixture_names(built):
    fixture = built.fixture
    store, spans, blobs = (built.ingestion.store, built.ingestion.spans, built.ingestion.blobs)
    table = store.table("toy_row")
    for position, name in enumerate(built.local_row_ids):
        span_ord = int(table.witness_span[position])
        handle, start, end = spans.address(span_ord)
        text = blobs.read(handle, start, end).decode("utf-8")
        assert text == fixture.SPAN_TEXT[fixture.ROW_BY_ID[name]["span_id"]], (
            f"row {name}'s witness bytes are not the turn the fixture names")


@cuda
def test_record_toy_anchor_postings_equal_MENTIONS_in_both_directions(built):
    fixture = built.fixture
    postings = built.ingestion.anchors.as_mapping()
    names = built.local_row_ids
    rebuilt = {surface: [names[row] for row in rows] for surface, rows in postings.items()}
    assert rebuilt == {k: sorted(v, key=names.index) for k, v in fixture.MENTIONS.items()}, (
        "the anchor index's postings are exactly the fixture's MENTIONS")
    assert set(rebuilt) == set(fixture.MENTIONS), "no surface is invented and none is lost"


@cuda
def test_record_toy_relations_equal_the_fixture(built):
    fixture, ingestion = built.fixture, built.ingestion
    names = built.local_row_ids
    spans = ingestion.spans
    span_name = {}
    for turn in fixture.SPAN_ORDER:
        for ordinal in range(len(spans)):
            handle, start, end = spans.address(ordinal)
            if ingestion.blobs.read(handle, start, end).decode("utf-8") == \
                    fixture.SPAN_TEXT[turn]:
                span_name[ordinal] = turn
                break
    produced = []
    for kind in ("meet", "corrects"):
        table = ingestion.relations.kind(kind)
        csr = table.csr(ingestion.store.row_count)
        located = {}
        for edge in range(csr.nnz):
            located[edge] = int(csr.located_count[edge])
        for position in range(len(table)):
            produced.append((kind, names[int(table.src[position])],
                             names[int(table.dst[position])],
                             span_name[int(table.witnesses_of(position)[0])], 1))
    assert produced == list(fixture.RELATIONS), (
        "the walk and residual edges are exactly the fixture's RELATIONS, in its order")
    assert set(produced) == set(fixture.RELATIONS)


@cuda
def test_record_toy_fails_closed_on_a_row_its_witness_does_not_support():
    """A planted row claiming a place its witness never names is refused, not downgraded."""
    planted = dict(toy.load_fixture().ROW_BY_ID["r8"])
    planted.update(row_id="r9-planted", object="Manchester", entity="Manchester",
                   place="Manchester", claim_id="c9")
    built = toy.ingest(extra_rows=[planted])
    assert "r9-planted" not in built.local_row_ids
    assert len(built.ingestion.store.table("toy_row")) == 10, "the fixture's ten rows, unchanged"
    refused = built.ingestion.store.refused
    assert len(refused) == 1 and refused[0].predicate_id == "surfaces_located@v1"
    assert refused[0].fields["place"] == "Manchester", (
        "B.4: the refusal is counted with its fields, extractor and rung")


@cuda
def test_record_toy_rebuild_is_byte_identical(built):
    """B.6: deleting the projection and re-deriving it reproduces it identically."""
    again = toy.ingest()
    assert again.ingestion.record_head_hash() == built.ingestion.record_head_hash()
    assert again.ingestion.generation_id() == built.ingestion.generation_id()
    assert again.ingestion.anchors.as_mapping() == built.ingestion.anchors.as_mapping()
    assert again.ingestion.store.row_ids("toy_row") == built.ingestion.store.row_ids("toy_row")


@cuda
def test_record_toy_no_duplicate_rows_under_the_identity_law(built):
    assert built.ingestion.store.table("toy_row").duplicate_rows() == 0, (
        "B.2: two rows with the same kind, fields and witness are the same row")
