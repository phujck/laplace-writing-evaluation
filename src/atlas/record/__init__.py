"""atlas.record - LEVEL 0 of the conceptric: the permanent, byte-addressed record.

Six provider obligations, named by packet I1 as interfaces other lanes already consume and
nobody had built, live here:

  1. ``content_blob``      - ``content_blob.ContentBlobStore``: the write-once content-addressed
                             blob store that gives B.1's spans a bottom to address.
  2. ``typed_row_store``   - ``typed_row_store.TypedRowStore``: one columnar table per row kind,
                             closed column list, integer tensors on device, witness per row.
  3. ``relation_table``    - ``relation_table.RelationTable``: one CSR per relation kind with
                             int64 located witness counts and a side table of witness addresses.
  4. ``anchor_index``      - ``anchor_index.AnchorIndex``: deterministic surface -> resolved ROW
                             ID postings, built at ingest from the declared surface set.
  5. ``field_alias_table`` - ``declaration.FieldAliasTable``: versioned, hashed, frozen.
  6. ``surface_set_schema``- ``declaration.SurfaceSetSchema``: which surfaces resolve to which
                             node per carrier kind, with the declared principals per transcript.

The record is permanent and identified by bytes; everything else in the system is a projection
of it (B.6). Nothing in this package computes an embedding, a cosine or any score - the word
does not appear in it - because B.21 puts similarity behind its own declared fibre and the
charter's first fatal default is a store that quietly becomes a dense ranker.
"""

from __future__ import annotations

from .anchor_index import AnchorIndex
from .content_blob import ContentBlob, ContentBlobStore
from .declaration import (RUNG_A, RUNG_B, RUNG_C, AliasRow, DatasetDeclaration, FieldAliasTable,
                          FieldSpec, RelationKindSpec, RowKindSpec, SurfaceSetSchema)
from .errors import (BlobRewriteRefused, ClosedColumnViolation, CpuNumericPathRefused,
                     DeclarationFrozen, MalformedSource, UnknownPredicate, UnknownSurface,
                     WitnessRefused)
from .ingestion import Ingestion, ItemCache, TouchedSet, item_cache_key
from .relation_table import CSR, RelationTable
from .spans import SpanTable
from .typed_row_store import Admission, RefusedProposal, TypedRowStore, TypedTable
from .witness import PREDICATES, WitnessCandidate, check_candidates

__all__ = [
    "AnchorIndex", "ContentBlob", "ContentBlobStore", "CSR", "RelationTable", "SpanTable",
    "TypedRowStore", "TypedTable", "Admission", "RefusedProposal", "Ingestion", "ItemCache",
    "TouchedSet", "item_cache_key", "DatasetDeclaration", "FieldAliasTable", "SurfaceSetSchema",
    "AliasRow", "FieldSpec", "RowKindSpec", "RelationKindSpec", "RUNG_A", "RUNG_B", "RUNG_C",
    "PREDICATES", "WitnessCandidate", "check_candidates",
    "BlobRewriteRefused", "ClosedColumnViolation", "CpuNumericPathRefused", "DeclarationFrozen",
    "MalformedSource", "UnknownPredicate", "UnknownSurface", "WitnessRefused",
]
