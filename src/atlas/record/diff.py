"""diff.py - O(diff): append one item, and report exactly what it touched.

The charter's law, and B.29's clause: "a single inserted, changed or deleted item recomputes only
what it touches". This module is the demonstration and the measurement of that, not a claim about
it. ``apply_case`` appends one LongMemEval haystack and ``apply_paper`` appends one QASPER paper
- B.33 and B.34 each make that one blob, so both are clean item boundaries - and each returns a
``TouchedSet`` naming the blobs, spans, rows, neighbours, edges and postings that moved. An
unchanged input returns an EMPTY touched set with ``cache_hit`` true, and that is enforced by two
independent mechanisms rather than by care: the blob store is content-addressed, and the per-item
extraction cache is keyed on content.

B.28's CACHE KEY, AS AMENDED. Packet I1 found and measured the defect: B.28 keyed the per-item
cache on ``{source_content_hash, item_span, extractor_id, dataset_declaration_hash}`` while B.31
makes a CHANGE to a source item a new blob with a new ``source_content_hash``, so appending one
turn to a haystack missed the cache for all 551 items inside it, though B.29's touched set for
that edit was three rows. The measured pair was 0-of-551 against 550-of-551 under a key computed
from the item's own bytes. This packet's report carries the patch that replaces the clause's key
with ``chash({item_content_hash, extractor_id, dataset_declaration_hash})``, and this module now
USES that key: ``measure_change_locality`` reports one number - the item-keyed hit count - with
the superseded container-keyed count kept beside it as the "before" it replaces.

B.31's supersedes_blob. A change now MINTS the typed relation the clause names, between the two
generations' ROOT rows (one haystack is one ``question`` row, one paper is one ``paper`` row), so
"the old objects are marked superseded" is a queryable edge rather than a paragraph of prose.

Complexity: ``apply_case``/``apply_paper`` are O(item bytes) host parse and check plus
O(k log k) device work for the item's own rows and edges, and O(1) in the size of everything
already stored.
"""

from __future__ import annotations

import time
from typing import Any

import torch

from ..ids import chash, hash_bytes
from .ingestion import Ingestion, TouchedSet, item_cache_key
from .ingest import longmem, qasper

__all__ = ["apply_case", "apply_paper", "measure_change_locality", "item_bytes_cache_key",
           "mint_supersedes_blob", "measure_cross_batch_duplicates", "measure_compaction"]


def item_bytes_cache_key(item_bytes: bytes, extractor_id: str,
                         dataset_declaration_hash: str) -> str:
    """B.28 as amended: the ITEM's own content hash, not its container's.

    Same field set as the original minus the container: an item's extraction is a pure function
    of the item's bytes and the declaration (B.28's own justification), so those are the only
    things its identity needs. Complexity: O(len(item_bytes)).
    """
    return chash({"item_content_hash": hash_bytes(item_bytes),
                  "extractor_id": extractor_id,
                  "dataset_declaration_hash": dataset_declaration_hash})


def _apply(ingestion: Ingestion, raw: bytes, extractor_id: str, media_type: str,
           mint_rows: Any) -> TouchedSet:
    """Shared body of the two item appends: cache, mint, neighbourhood, postings, touched set."""
    declaration_hash = ingestion.declaration.declaration_hash
    handle = hash_bytes(raw)
    key = item_bytes_cache_key(raw, extractor_id, declaration_hash)
    if handle in ingestion.blobs and ingestion.cache.get(key) is not None:
        return TouchedSet(cache_hit=True)

    before_rows = ingestion.store.row_count
    before_spans = len(ingestion.spans)
    before_edges = {name: len(table) for name, table in ingestion.relations.kinds.items()}
    before_blobs = set(ingestion.blobs.handles())

    ingestion.blobs.put_bytes(raw, media_type)
    mint_rows(ingestion, handle, raw, before_rows)
    ingestion.cache.put(key, {"rows": ingestion.store.row_count - before_rows})

    new_rows = torch.arange(before_rows, ingestion.store.row_count, dtype=torch.int64,
                            device=ingestion.device)
    neighbours = ingestion.neighbourhood(new_rows.tolist())
    surfaces = ()
    if ingestion.anchors is not None:
        surfaces = ingestion.anchors.extend(ingestion.store, new_rows)
    return TouchedSet(
        blobs=tuple(h for h in ingestion.blobs.handles() if h not in before_blobs),
        span_ordinals=tuple(range(before_spans, len(ingestion.spans))),
        row_ordinals=tuple(new_rows.tolist()),
        neighbour_ordinals=tuple(neighbours.tolist()),
        edges={name: len(table) - before_edges[name]
               for name, table in ingestion.relations.kinds.items()
               if len(table) != before_edges[name]},
        posting_surfaces=surfaces, cache_hit=False)


def apply_case(ingestion: Ingestion, raw: bytes) -> TouchedSet:
    """Append one LongMemEval haystack; return exactly what it touched (B.29)."""
    rungs = "ab" if "entity" in ingestion.store.tables else "a"

    def mint(ing: Ingestion, handle: str, data: bytes, since: int) -> None:
        case, _ = longmem.scan_value(data, 0, 0)
        longmem._ingest_case(ing, handle, case, rungs)
        longmem._build_relations_for_new_rows(ing, since)
        if rungs == "ab":
            longmem._build_rung_b_relations(ing, since)
            ing.pending_edges.clear()

    return _apply(ingestion, raw, longmem.EXTRACTOR_ID, longmem.BLOB_MEDIA_TYPE, mint)


def apply_paper(ingestion: Ingestion, raw: bytes, paper_id: str) -> TouchedSet:
    """Append one QASPER paper; return exactly what it touched (B.29).

    The QASPER analogue of ``apply_case``, and the measurement the packet's "adding one paper
    touches only its own rows" claim is made of. The relation pass runs over the whole store, as
    it does at ingest, but every edge it can mint is item-local by declaration, so the edges it
    adds are this paper's - which is what the returned ``edges`` count shows.
    """
    def mint(ing: Ingestion, handle: str, data: bytes, since: int) -> None:
        rungs = "ab" if "entity" in ing.store.tables else "a"
        ing.pending_edges.clear()
        ing.pending_labels.clear()
        qasper._ingest_paper(ing, handle, qasper.PaperItem(paper_id, data, 0), rungs)
        qasper._build_relations(ing, rungs, since)
        ing.pending_edges.clear()
        ing.pending_labels.clear()

    return _apply(ingestion, raw, qasper.EXTRACTOR_ID_A, qasper.BLOB_MEDIA_TYPE, mint)


# ------------------------------------------------------------------ B.31: supersedes_blob
def mint_supersedes_blob(ingestion: Ingestion, root_kind: str, id_column: str) -> int:
    """Mint B.31's ``supersedes_blob`` between the root rows of two generations of one item.

    A relation's endpoints are declared ROW kinds, so the edge that marks a blob superseded is
    carried by the row that owns the blob: one haystack is one ``question`` row, one paper is one
    ``paper`` row. The witness tuple is the two root rows' own witness spans, which address the
    two blobs - so re-reading the witness re-reads exactly the superseded and superseding bytes.
    Uncounted: it is a fact about generations, not a structural relation of the corpus, and
    B.19's stationary law must not see it.

    Returns the number of edges offered. Complexity: O(R log R) for R root rows.
    """
    if "supersedes_blob" not in ingestion.relations.kinds:
        return 0
    table = ingestion.store.table(root_kind)
    if len(table) < 2:
        return 0
    identifiers = table.decode(id_column)
    witness = table.witness_span.tolist()
    globals_ = table.global_ordinals.tolist()
    blob_of = ingestion.spans.columns[:, 0].tolist()
    seen: dict[str, int] = {}
    src, dst, spans, contexts = [], [], [], []
    for local, identifier in enumerate(identifiers):
        previous = seen.get(identifier)
        if previous is not None and blob_of[witness[local]] != blob_of[witness[previous]]:
            src.append(globals_[local])
            dst.append(globals_[previous])
            spans.append((witness[local], witness[previous]))
            contexts.append({"source_fields": {id_column: identifier},
                             "target_fields": {id_column: identifier}})
        seen[identifier] = local
    if not src:
        return 0
    ingestion.append_relations("supersedes_blob", src, dst, spans, contexts=contexts,
                               extractor_id="record-generation@v1",
                               witness_options={"equal_fields": (id_column,)})
    return len(src)


# ------------------------------------------------------------------ measurements
def measure_change_locality(ingestion: Ingestion, raw: bytes,
                            appended_turn: tuple[str, str]) -> dict[str, Any]:
    """Append one TURN to an already-ingested haystack and measure what the cache key saves.

    One number under the amended clause: ``item_keyed_hits`` of ``items_in_changed_blob``. The
    superseded container-keyed count is reported beside it as ``b28_container_keyed_hits_before_
    the_amendment`` so the pair packet I1 measured stays readable rather than being quietly
    dropped once the clause moved.
    """
    declaration_hash = ingestion.declaration.declaration_hash
    case, _ = longmem.scan_value(raw, 0, 0)
    sessions = case.member("haystack_sessions")
    last = (sessions.items or ())[-1]
    turn_json = ('{"role": "%s", "content": %s}'
                 % (appended_turn[0], _json_string(appended_turn[1])))
    changed = raw[:last.end - 1] + (", " + turn_json).encode("utf-8") + raw[last.end - 1:]

    item_keys_before = {
        item_bytes_cache_key(raw[turn.start:turn.end], longmem.EXTRACTOR_ID, declaration_hash)
        for session in (sessions.items or ()) for turn in (session.items or ())}
    container_keys_before = {
        item_cache_key(hash_bytes(raw), (turn.start, turn.end), longmem.EXTRACTOR_ID,
                       declaration_hash)
        for session in (sessions.items or ()) for turn in (session.items or ())}

    new_case, _ = longmem.scan_value(changed, 0, 0)
    new_sessions = new_case.member("haystack_sessions")
    item_keys_after = [
        item_bytes_cache_key(changed[turn.start:turn.end], longmem.EXTRACTOR_ID,
                             declaration_hash)
        for session in (new_sessions.items or ()) for turn in (session.items or ())]
    container_keys_after = [
        item_cache_key(hash_bytes(changed), (turn.start, turn.end), longmem.EXTRACTOR_ID,
                       declaration_hash)
        for session in (new_sessions.items or ()) for turn in (session.items or ())]

    started = time.perf_counter()
    touched = apply_case(ingestion, changed)
    elapsed = time.perf_counter() - started
    superseded = mint_supersedes_blob(ingestion, "question", "question_id")
    return {
        "edit": "one turn appended to the last session of one haystack",
        "clause": "B.28 as amended: key = chash({item_content_hash, extractor_id, "
                  "dataset_declaration_hash})",
        "items_in_changed_blob": len(item_keys_after),
        "item_keyed_hits": sum(1 for k in item_keys_after if k in item_keys_before),
        "b28_container_keyed_hits_before_the_amendment":
            sum(1 for k in container_keys_after if k in container_keys_before),
        "touched": {k: v for k, v in touched.to_dict().items()
                    if k not in ("row_ordinals", "posting_surfaces")},
        "supersedes_blob_edges_minted": superseded,
        "supersedes_blob_instances_in_store": len(
            ingestion.relations.kind("supersedes_blob"))
        if "supersedes_blob" in ingestion.relations.kinds else 0,
        "apply_seconds": elapsed,
        "blob_bytes_reparsed": len(changed),
    }


def measure_cross_batch_duplicates(ingestion: Ingestion, items: list[bytes],
                                   apply: Any) -> dict[str, Any]:
    """Feed the same items through a SECOND batch and check B.2's identity across batches.

    The standing diagnostic named in the amended B.28: the per-item cache is what guarantees a
    second batch re-mints nothing, and ``duplicate_rows`` is the scan that catches a store where
    that guarantee was bypassed. Both are reported, so "the cache is the guarantee" is a
    statement with a number under it. Complexity: O(N c log N) on device per kind.
    """
    before = dict(ingestion.store.receipt()["rows_by_kind"])
    hits_before = ingestion.cache.hits
    replays = [apply(ingestion, item) for item in items]
    after = dict(ingestion.store.receipt()["rows_by_kind"])
    duplicates = ingestion.duplicate_rows()
    # The PLANTED VIOLATION, so "duplicate_rows is the standing diagnostic" is a claim with a
    # demonstration under it: bypass the cache by clearing it, replay one item, and check the
    # scan reports the duplicates that appear. The store is left holding them, so the caller
    # measures on a copy or reports the number and stops using that store.
    bypassed = None
    if items:
        ingestion.cache._entries.clear()
        rows_before_bypass = ingestion.store.row_count
        apply(ingestion, items[0])
        bypassed = {
            "what_was_bypassed": "the per-item cache was cleared, which is what B.28 names as "
                                 "the guarantee; nothing else was changed",
            "rows_minted_again": ingestion.store.row_count - rows_before_bypass,
            "duplicate_rows_total_after_the_bypass": sum(
                ingestion.duplicate_rows().values()),
        }
    return {
        "items_replayed": len(items),
        "cache_hits_on_replay": ingestion.cache.hits - hits_before,
        "planted_violation": bypassed,
        "rows_before": before, "rows_after": after,
        "rows_added_by_the_replay": {k: after[k] - before.get(k, 0) for k in after
                                     if after[k] != before.get(k, 0)},
        "touched_counts_on_replay": [t.touched_count for t in replays],
        "duplicate_rows_by_kind": duplicates,
        "duplicate_rows_total": sum(duplicates.values()),
    }


def measure_compaction(ingestion: Ingestion, surfaces: list[str]) -> dict[str, Any]:
    """Show ``resolve`` leaves the merge path and returns to the CSR after ``compact``.

    The residual packet I1 named: ``extend`` is O(diff) and leaves a COO delta, and while that
    delta is non-empty ``resolve`` cannot use the CSR gather. The measurement is the pair of wall
    times for the SAME resolve call either side of one compaction, with the delta size that
    separates them, plus the equality of the two answers - a faster path that returned a
    different set would be a bug, not an optimisation.
    """
    index = ingestion.anchors
    if index is None:
        return {"anchors": None}
    wanted = [s for s in surfaces if index.ordinal_of(s) >= 0]
    torch.cuda.synchronize(ingestion.device)
    started = time.perf_counter()
    before_rows = index.resolve(wanted)
    torch.cuda.synchronize(ingestion.device)
    before_seconds = time.perf_counter() - started
    delta = index.delta_postings
    moved = index.compact()
    torch.cuda.synchronize(ingestion.device)
    started = time.perf_counter()
    after_rows = index.resolve(wanted)
    torch.cuda.synchronize(ingestion.device)
    after_seconds = time.perf_counter() - started
    return {
        "surfaces_resolved": len(wanted),
        "delta_postings_before": delta,
        "delta_postings_after": index.delta_postings,
        "resolve_seconds_with_delta": before_seconds,
        "resolve_seconds_after_compact": after_seconds,
        "speedup": (before_seconds / after_seconds) if after_seconds else 0.0,
        "same_rows": bool(before_rows.numel() == after_rows.numel()
                          and bool((torch.sort(before_rows).values
                                    == torch.sort(after_rows).values).all())),
        "rows_resolved": int(after_rows.numel()),
        "compaction": moved,
    }


def _json_string(text: str) -> str:
    import json
    return json.dumps(text)
