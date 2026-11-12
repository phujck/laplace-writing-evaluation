"""The record layer's own laws: blobs, spans, identity, the closed column list, the device.

Each test here is a planted violation of one clause, and the clause is named in the assertion
message so a failure says which rule broke rather than which line did.
"""

from __future__ import annotations

import datetime as dt

import pytest
import torch

from atlas.record import (RUNG_A, ClosedColumnViolation, ContentBlobStore, CpuNumericPathRefused,
                          DatasetDeclaration, DeclarationFrozen, FieldAliasTable, FieldSpec,
                          RelationTable, RowKindSpec, SpanTable, SurfaceSetSchema,
                          TypedRowStore)
from atlas.record.columns import NULL_OF, date_of_key, day_key, second_key
from atlas.record.declaration import RelationKindSpec
from atlas.record.json_spans import iter_jsonl_lines, scan_value
from atlas.record.relation_table import RelationKindTable

cuda = pytest.mark.skipif(not torch.cuda.is_available(),
                          reason="the record layer's numeric core is CUDA-only by policy")


def _declaration() -> DatasetDeclaration:
    kind = RowKindSpec(
        "note",
        (FieldSpec("name", "dict_utf8", RUNG_A),
         FieldSpec("colour", "enum", RUNG_A, ("red", "blue")),
         FieldSpec("when", "date", RUNG_A),
         FieldSpec("count", "int64", RUNG_A)),
        time_field="when", witness_predicate_id="surfaces_located@v1",
        anchor_fields=("name",))
    return DatasetDeclaration(
        "unit", (kind,),
        (RelationKindSpec("mentions", ("note",), ("note",), "spans_nest@v1", RUNG_A),),
        FieldAliasTable("v1", ()),
        SurfaceSetSchema("v1", anchor_columns={"note": ("name",)},
                         must_appear_columns={"note": ("name",)}),
        "json-byte-scanner", "1", "*.txt")


# --------------------------------------------------------------------------- blobs
def test_record_blob_is_written_once_and_addressed_by_content():
    store = ContentBlobStore()
    first = store.put_bytes(b"alpha beta", "text/plain")
    again = store.put_bytes(b"alpha beta", "text/plain")
    assert first == again, "B.1: the same bytes are the same blob"
    assert len(store) == 1, "an unchanged input re-mints nothing, even at the blob level"
    assert store.read(first, 0, 5) == b"alpha", "a span is recovered by blob[start:end]"
    assert store.put_bytes(b"alpha gamma", "text/plain") != first


def test_record_blob_handle_excludes_the_clock():
    store = ContentBlobStore()
    handle = store.put_bytes(b"x", "text/plain")
    assert store.blob(handle).ingested_utc, "ingested_utc is recorded beside the blob"
    assert store.blob(handle).ingested_utc not in handle, "ids.py: no clock enters an identity"


# --------------------------------------------------------------------------- columns
def test_record_null_sentinel_is_the_dtype_minimum_per_the_toy_declaration():
    assert NULL_OF[torch.int32] == -(2 ** 31), (
        "toy_corpus.py:19-22 declares INT32_MIN as the null of an int32 column")
    assert NULL_OF[torch.int8] == -(2 ** 7) and NULL_OF[torch.int64] == -(2 ** 63)
    assert 0 not in NULL_OF.values(), "a null is never zero"


def test_record_time_keys_are_lossless_and_ordered():
    assert day_key(dt.date(1970, 1, 1)) == 0
    assert date_of_key(day_key(dt.date(2026, 3, 15))) == dt.date(2026, 3, 15)
    assert day_key(dt.date(1969, 12, 31)) == -1, "dates before the epoch are negative, not null"
    aware = dt.datetime(2026, 7, 14, 23, 56, 2, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    assert second_key(aware) == second_key(dt.datetime(2026, 7, 14, 21, 56, 2)), (
        "an explicit offset is applied, never dropped")


# --------------------------------------------------------------------------- declaration
def test_record_declaration_is_frozen_and_hashed():
    declaration = _declaration()
    assert declaration.declaration_hash == _declaration().declaration_hash, (
        "B.5: the declaration hash is a function of the declaration alone")
    with pytest.raises(DeclarationFrozen):
        declaration.amend(dataset_id="other")


def test_record_declaration_refuses_an_undeclared_column_type():
    with pytest.raises(ClosedColumnViolation):
        DatasetDeclaration("bad", (RowKindSpec("k", (FieldSpec("f", "float64", RUNG_A),)),),
                           (), FieldAliasTable("v1", ()), SurfaceSetSchema("v1", {}),
                           "s", "1", "*")


# --------------------------------------------------------------------------- store
@cuda
def test_record_store_refuses_a_field_outside_the_closed_column_list():
    declaration = _declaration()
    blobs = ContentBlobStore()
    handle = blobs.put_bytes(b"ana", "text/plain")
    spans = SpanTable("json-byte-scanner", "1", torch.device("cuda"))
    span = spans.append([spans.blob_ordinal(handle)], [0], [3])
    store = TypedRowStore(declaration, blobs, spans)
    with pytest.raises(ClosedColumnViolation):
        store.append_rows("note", [{"name": "ana", "mood": "sunny"}], span.tolist(),
                          rung=RUNG_A, extractor_id="unit",
                          witness_options={"must_appear": ("name",)})


@cuda
def test_record_store_fails_closed_when_the_witness_does_not_contain_the_row():
    declaration = _declaration()
    blobs = ContentBlobStore()
    handle = blobs.put_bytes(b"ana lives in porto", "text/plain")
    spans = SpanTable("json-byte-scanner", "1", torch.device("cuda"))
    span_ords = spans.append([spans.blob_ordinal(handle)] * 2, [0, 0], [18, 18]).tolist()
    store = TypedRowStore(declaration, blobs, spans)
    admission = store.append_rows(
        "note", [{"name": "ana", "colour": "red", "when": None, "count": 1},
                 {"name": "miso", "colour": "red", "when": None, "count": 2}],
        span_ords, rung=RUNG_A, extractor_id="unit",
        witness_options={"must_appear": ("name",)})
    assert admission.admitted == 1, "B.4: a row whose witness does not contain it is not stored"
    assert len(admission.refused) == 1 and admission.refused[0].fields["name"] == "miso"
    assert len(store.table("note")) == 1, "the refusal is not downgraded to a weaker row"
    assert store.receipt()["refused_proposals"] == 1, "B.4: it is counted in the receipt"


@cuda
def test_record_row_identity_is_kind_fields_and_witness_only():
    declaration = _declaration()
    blobs = ContentBlobStore()
    handle = blobs.put_bytes(b"ana ana", "text/plain")
    spans = SpanTable("json-byte-scanner", "1", torch.device("cuda"))
    ords = spans.append([spans.blob_ordinal(handle)] * 2, [0, 4], [3, 7]).tolist()
    store = TypedRowStore(declaration, blobs, spans)
    fields = {"name": "ana", "colour": "blue", "when": dt.date(2026, 1, 5), "count": 7}
    store.append_rows("note", [dict(fields), dict(fields)], ords, rung=RUNG_A,
                      extractor_id="unit", witness_options={"must_appear": ("name",)})
    first, second = store.row_ids("note")
    assert first != second, "B.2: two rows with the same fields but different witnesses differ"
    assert store.row_ids("note", [0])[0] == first, "row_id is a pure function of its content"


@cuda
def test_record_store_keeps_no_python_object_in_the_numeric_path():
    declaration = _declaration()
    blobs = ContentBlobStore()
    handle = blobs.put_bytes(b"ana", "text/plain")
    spans = SpanTable("json-byte-scanner", "1", torch.device("cuda"))
    ords = spans.append([spans.blob_ordinal(handle)], [0], [3]).tolist()
    store = TypedRowStore(declaration, blobs, spans)
    store.append_rows("note", [{"name": "ana", "colour": "red", "when": None, "count": 3}],
                      ords, rung=RUNG_A, extractor_id="unit",
                      witness_options={"must_appear": ("name",)})
    table = store.table("note")
    for column in table.spec.columns:
        tensor = table.column(column)
        assert isinstance(tensor, torch.Tensor) and tensor.device.type == "cuda"
        assert tensor.dtype in (torch.int8, torch.int16, torch.int32, torch.int64), (
            "every column is an integer tensor; no Python object reaches the numeric path")
    assert int(table.column("when")[0]) == NULL_OF[torch.int64], "null is the explicit sentinel"


def test_record_numeric_core_refuses_the_host():
    with pytest.raises(CpuNumericPathRefused):
        SpanTable("s", "1", torch.device("cpu"))


# --------------------------------------------------------------------------- relations
@cuda
def test_record_relation_csr_counts_distinct_witness_tuples_once_per_pair():
    spec = RelationKindSpec("meets", ("a",), ("a",), "spans_nest@v1", RUNG_A)
    table = RelationKindTable(spec, torch.device("cuda"))
    # Same ordered pair, three instances: two share a witness tuple, one differs. B.16 counts
    # once per DISTINCT witness tuple, so the located count is 2, not 3 and not 1.
    table.append([0, 0, 0], [1, 1, 1], [(5,), (5,), (6,)])
    csr = table.csr(2)
    assert csr.nnz == 1, "one distinct pair"
    assert int(csr.located_count[0]) == 2, "B.16: one count per distinct witness_span_ids tuple"
    assert csr.indptr.dtype == torch.int32 and csr.indices.dtype == torch.int32


@cuda
def test_record_relation_refuses_an_edge_with_no_witness():
    spec = RelationKindSpec("meets", ("a",), ("a",), "spans_nest@v1", RUNG_A)
    table = RelationKindTable(spec, torch.device("cuda"))
    table.append([0], [1], [()])
    with pytest.raises(ClosedColumnViolation):
        table.csr(2)


@cuda
def test_record_relation_walk_is_two_calls_not_a_squared_incidence():
    spec = RelationKindSpec("meets", ("a",), ("a",), "spans_nest@v1", RUNG_A)
    table = RelationKindTable(spec, torch.device("cuda"))
    table.append([0, 1], [1, 2], [(0,), (1,)])
    seeds = torch.tensor([0], dtype=torch.int64, device="cuda")
    one_hop = table.neighbours(seeds, 3)
    assert one_hop.tolist() == [1]
    assert table.neighbours(one_hop, 3).tolist() == [2], (
        "B.17: two hops is a second walk, never B B^T")


@cuda
def test_record_degree_is_a_scatter_not_a_dense_matrix():
    declaration = _declaration()
    relations = RelationTable(declaration.relation_kinds, torch.device("cuda"))
    relations.kind("mentions").append([0, 2], [1, 1], [(0,), (1,)])
    degree = relations.degree(3)
    assert degree.tolist() == [1, 2, 1], "d_i is the located witness degree of row i"
    assert degree.dtype == torch.int64, "located counts are int64"


# --------------------------------------------------------------------------- scanner
def test_record_json_scanner_returns_byte_offsets_that_recover_the_value():
    raw = b'{"a": "x\\u00e9", "b": [1, 2], "c": {"d": true}}'
    node, _ = scan_value(raw, 0, 0)
    a = node.member("a")
    assert raw[a.start:a.end] == b'"x\\u00e9"', "a string span includes its quotes"
    assert a.text == "xé"
    assert node.member("c").member("d").value is True
    assert node.start == 0 and node.end == len(raw)


def test_record_jsonl_lines_are_exact_byte_ranges():
    data = b'{"a":1}\n\n{"b":2}\r\n{"c":3}'
    ranges = list(iter_jsonl_lines(data))
    assert [data[s:e] for s, e in ranges] == [b'{"a":1}', b'{"b":2}', b'{"c":3}']
