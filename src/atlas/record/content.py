"""content.py - THE LEAF CARRIES ITS CONTENT: a span of text WITH its observations.

Until this module the record ingested every byte and indexed none of its words. A LongMemEval
turn row was ``(question_id, session_index, turn_index, speaker, content_span)`` and "the row
stores no copy" (``ingest/longmem.py:120-128``); there was no vector column and no token column
anywhere under ``atlas/record``. A question therefore reached a row only through an extracted
surface or a typed column condition, so a lowercase content word that is not a name, a number or
a date reached nothing - which is the whole of the E1 result (19 of 94 questions isolated: the
fraction whose gold shares a capitalised name, number or date with the question, and a
statement about the CONDITION SET, not a method result).

WHAT A LEAF IS HERE. S4 ``def:S4-store`` makes the leaf row of axis a a UNIT VECTOR per declared
field, stored separately; S3 ``prop:S3-separable`` requires one unit vector per axis per item for
the corpus state to be the separable object the later theorems are about. So a leaf is:

  * a SPAN of a content-bearing row's text, cut by the DECLARED recipe
    (``declaration.SegmentationRecipe``) - never a literal inside an ingester;
  * one unit vector per DECLARED content axis, in that axis's declared stored form (D.7), with
    its per-row quantisation error eps measured at encode time;
  * its normalised token set, when the axis declares one;
  * and, through ``carrier_row``, the typed row it came out of - so its typed fields, its
    polarity, its time and its speaker are one gather away and are never asked of the vector
    (D.2's five classes stay with the rows).

WHY THIS IS NOT "CHUNK AND EMBED". The chunk size is a declared row with provenance and a named
refusal; the encoder is chosen against D.1-D.17 and recorded by content hash; the vector is an
OBSERVATION OF A SPAN that keeps its typed fields and its tokens beside it; and the axis exists
to be a declared FACTOR - it can be left undeclared, in which case nothing here runs and the
record is what it was, bit for bit. Nothing in this module computes a similarity, holds an index
or ranks anything: B.21 and D.1 put that behind an authored fibre, and this is level 0.

WHAT IS ITEM-LOCAL, AND WHY IT HAS TO BE. B.28 requires an extractor to be a pure function of
ONE item's bytes plus the declaration, because a corpus statistic destroys the cache. So the
token column stores per-item CODES against a per-item surface list and no document frequency;
IDF and the token-major postings are a PROJECTION built over the whole opened record
(``extension/lexical_index.py:165-294``'s job), never an ingestion step.

Complexity: O(total content bytes) to cut and decode, O(total tokens) of device work to encode
in bounded batches, O(n d) to quantise. One host-to-device copy per axis when a caller asks for
the device form; none at all during the build.
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

from ..encoders.span_encoder import SpanEncoder, dequantise, quantise, span_encoder
from ..ids import hash_bytes
from ..segment.base import pack_cuts
from .declaration import (SEGMENTATION_RECIPE_GENERATION, ContentAxisSpec, ContentCarrier,
                          DatasetDeclaration, SegmentationRecipe)
from .errors import DeclarationRefused, MalformedSource

__all__ = ["CONTENT_SEGMENTER_ID", "ContentTable", "ContentBuild", "build_content",
           "normalize_tokens", "cut_by_recipe", "content_arrays", "content_from_arrays",
           "content_digest", "axis_matrix", "declared_axes"]

#: The leaf segmenter's own id, so a span cut by this recipe is told apart from one cut by the
#: old store path's file segmenters. It travels in ``seg_version`` through the declaration.
CONTENT_SEGMENTER_ID = "record-leaf-window@v1"

#: The separator ladder, coarse to fine. Same shape as ``segment/base.split_block``'s, in
#: CHARACTER space because a content axis reads decoded text: paragraph, line, sentence, word.
#: A text with none of them left is cut at fixed offsets and the cut is COUNTED, never silent.
SEPARATORS = ("\n\n", "\n", ". ", " ")

#: ``segment/base.est_tokens`` is bytes/4 rounded up; the same estimate reads a character budget
#: off a token dial. It is an ESTIMATE and is treated as one: the encoder's own tokenizer
#: measures the truth afterwards and ``tokens_dropped`` reports what the window actually lost
#: (D.6(3)). Nothing is tuned on it.
CHARS_PER_TOKEN = 4

#: LIFTED VERBATIM from ``synthetics papers/corpus-as-a-state/reconstruction/extension/
#: lexical_index.py:28-34`` - the same regex and the same NFKC-casefold-apostrophe rule, so the
#: record's tokens and the extension's lexical index agree by construction rather than by
#: coincidence. No stemming and no entity inference: these are observable word forms.
_TOKEN = re.compile(r"[^\W_]+(?:[-'’][^\W_]+)*", re.UNICODE)


def normalize_tokens(text: str) -> tuple[str, ...]:
    """Return observable word-form tokens; no stemming or entity inference. O(len(text))."""
    normalized = unicodedata.normalize("NFKC", str(text)).casefold().replace("’", "'")
    return tuple(match.group(0) for match in _TOKEN.finditer(normalized))


# --------------------------------------------------------------------------- the declaration
def declared_axes(row: Mapping[str, Any] | None, carriers: Sequence[ContentCarrier],
                  seg_version: str) -> tuple[SegmentationRecipe | None,
                                             tuple[ContentAxisSpec, ...]]:
    """Read ONE declared-draw row's content block into a recipe and its axes, for one dataset.

    This is the ablation switch's only construction site, and it is why the four ingesters share
    it instead of each growing its own copy: a draw row that names no content block returns
    ``(None, ())`` and the dataset declares exactly what it declared before, so the OFF position
    is one code path rather than four. The carriers are the DATASET's - its own content-bearing
    row kinds - and the dials are the DRAW's. Complexity: O(axes).
    """
    if not row:
        return None, ()
    # The dials are passed through UNCOERCED. An ``int(...)`` here would turn 96.0 into 96 and a
    # draw row carrying a float would be accepted silently; the recipe's own type check is the
    # refusal and it only fires if it is given what the row actually said.
    recipe = SegmentationRecipe(
        generation=str(row.get("generation", SEGMENTATION_RECIPE_GENERATION)),
        target_tokens=row["target_tokens"], hard_cap_tokens=row["hard_cap_tokens"],
        segmenter_version=seg_version, declared_by=str(row.get("declared_by", "")))
    axes = tuple(
        ContentAxisSpec(axis=str(entry["axis"]), encoder_id=str(entry["encoder_id"]),
                        dim=int(entry["dim"]), dtype=str(entry["dtype"]),
                        carriers=tuple(carriers), tokens=bool(entry.get("tokens", True)),
                        why=str(entry.get("why", "")))
        for entry in row["axes"])  # loop-ok: the declared axes of one draw row
    return recipe, axes


# --------------------------------------------------------------------------- the cut
def cut_by_recipe(text: str, recipe: SegmentationRecipe) -> tuple[list[tuple[int, int]], int]:
    """Cut one text into leaf ranges by the DECLARED recipe. Returns (ranges, blind cuts).

    The ladder is ``SEPARATORS`` coarse to fine and the packing is ``segment/base.pack_cuts`` -
    the organ the old store path already uses - so a leaf never falls below the target while a
    coarser boundary would have served. A block with no separator left is cut at fixed offsets
    and counted in the second return value, which is the number the receipt reports rather than
    hides. Complexity: O(len(text) * |SEPARATORS|).
    """
    if not text:
        return [], 0
    target = max(1, recipe.target_tokens * CHARS_PER_TOKEN)
    cap = max(target, recipe.hard_cap_tokens * CHARS_PER_TOKEN)
    tiles: list[tuple[int, int]] = [(0, len(text))]
    for separator in SEPARATORS:                   # loop-ok: the declared separator ladder
        nxt: list[tuple[int, int]] = []
        for lo, hi in tiles:                       # loop-ok: the tiles of ONE text
            if hi - lo <= cap:
                nxt.append((lo, hi))
                continue
            cuts: list[int] = []
            position = text.find(separator, lo, hi)
            while position != -1:                  # loop-ok: one step per separator occurrence
                cut = position + len(separator)
                if lo < cut < hi:
                    cuts.append(cut)
                position = text.find(separator, cut, hi)
            packed = pack_cuts(lo, hi, cuts, target) if cuts else [(lo, hi)]
            nxt.extend(packed)
        tiles = nxt
    out: list[tuple[int, int]] = []
    blind = 0
    for lo, hi in tiles:                           # loop-ok: the tiles of ONE text
        if hi - lo <= cap:
            out.append((lo, hi))
            continue
        position = lo
        while position < hi:                       # loop-ok: one step per fixed-offset window
            out.append((position, min(position + target, hi)))
            position += target
            blind += 1
    return [(lo, hi) for lo, hi in out if hi > lo], blind  # loop-ok: the tiles of ONE text


# --------------------------------------------------------------------------- the table
@dataclass(slots=True)
class ContentTable:
    """The content leaves of one record: their spans, their carriers and their observations.

    Held as HOST arrays. The device form of an axis is a projection a lens asks for
    (``axis_matrix``) and is not built here, because B.6 makes every vector a disposable
    projection and the 3.7 GiB card is not where a store lives.
    """

    span: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    carrier_kind: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    carrier_row: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    ordinal: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    tokens_emitted: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    tokens_dropped: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    axes: dict[str, dict[str, np.ndarray]] = field(default_factory=dict)
    token_codes: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    token_offsets: np.ndarray = field(default_factory=lambda: np.zeros(1, dtype=np.int64))
    surfaces: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return int(self.span.size)

    def host_bytes(self) -> int:
        """Every byte this table holds on the host. Deterministic, O(axes)."""
        total = sum(int(array.nbytes) for array in
                    (self.span, self.carrier_kind, self.carrier_row, self.ordinal,
                     self.tokens_emitted, self.tokens_dropped, self.token_codes,
                     self.token_offsets))  # loop-ok: the table's own fixed column list
        for arrays in self.axes.values():            # loop-ok: the declared content axes
            total += sum(int(array.nbytes) for array in arrays.values())  # loop-ok: code/scale/eps
        total += sum(len(surface.encode("utf-8")) for surface in self.surfaces)  # loop-ok: the
        return int(total)                                                        # item surfaces

    def receipt(self, declaration: DatasetDeclaration) -> dict[str, Any]:
        """What the content layer holds, per declared axis. Every field is counted. O(axes)."""
        out: dict[str, Any] = {
            "leaves": len(self), "surfaces": len(self.surfaces),
            "token_occurrences": int(self.token_codes.size),
            "tokens_emitted": int(self.tokens_emitted.sum()) if len(self) else 0,
            "tokens_dropped": int(self.tokens_dropped.sum()) if len(self) else 0,
            "host_bytes": self.host_bytes(), "axes": {}}
        for axis in declaration.content_axes:        # loop-ok: the declared content axes
            arrays = self.axes.get(axis.axis)
            if arrays is None:
                continue
            eps = arrays["eps"]
            out["axes"][axis.axis] = {
                "encoder_id": axis.encoder_id, "dim": axis.dim, "dtype": axis.dtype,
                "rows": int(arrays["code"].shape[0]),
                "declared_bytes_per_span_D9": axis.bytes_per_span(),
                "stored_bytes": int(arrays["code"].nbytes + arrays["scale"].nbytes
                                    + arrays["eps"].nbytes),
                "eps_max": float(eps.max()) if eps.size else 0.0,
                "eps_mean": float(eps.mean()) if eps.size else 0.0}
        return out


def axis_matrix(table: ContentTable, axis: ContentAxisSpec) -> np.ndarray:
    """One axis's stored rows dequantised to float32 - what a read actually scores (D.7).

    The PROJECTION, built on demand and thrown away; the record holds the codes. Complexity:
    O(n d), one allocation.
    """
    arrays = table.axes.get(axis.axis)
    if arrays is None:
        return np.zeros((0, axis.dim), dtype=np.float32)
    return dequantise(arrays["code"], arrays["scale"], axis.dtype)


@dataclass(slots=True)
class ContentBuild:
    table: ContentTable
    receipt: dict[str, Any]


# --------------------------------------------------------------------------- the build
def build_content(ingestion: Any, *, encoders: Mapping[str, SpanEncoder] | None = None,
                  device: str = "cuda") -> ContentBuild:
    """Cut, encode and tokenise every declared carrier's text. The whole content pass.

    Runs ONCE per ingest, over the carrier rows this run actually minted - a row whose leaves
    arrived from a segment (the warm path) is skipped by mask, so a mixed run encodes exactly the
    diff. With no axis declared it returns an empty table and touches nothing, which is the
    ablation's OFF position and the reason the record is bit-for-bit what it was.

    Complexity: O(content bytes) to read and cut, O(total tokens) of device work to encode,
    O(n d) to quantise. The texts of ALL carriers of ALL axes are encoded in ONE batched call per
    axis, so the device sees a bounded number of launches whatever the row count.
    """
    declaration: DatasetDeclaration = ingestion.declaration
    existing: ContentTable | None = getattr(ingestion, "content", None)
    if not declaration.content_axes:
        return ContentBuild(existing or ContentTable(), {"axes": 0, "skipped": "no axis declared"})
    recipe = declaration.segmentation
    assert recipe is not None                      # the declaration refuses the other case
    started = time.perf_counter()

    already = np.zeros(0, dtype=np.int64)
    if existing is not None and len(existing):
        already = np.unique(existing.carrier_row)

    kind_index = {spec.kind: position for position, spec in enumerate(declaration.row_kinds)}
    carriers: list[tuple[str, str, str]] = []
    for axis in declaration.content_axes:          # loop-ok: the declared content axes
        for carrier in axis.carriers:              # loop-ok: that axis's declared carriers
            entry = (carrier.kind, carrier.span_field, carrier.decoder)
            if entry not in carriers:
                carriers.append(entry)

    texts: list[str] = []
    keys: list[str] = []
    item_of_leaf: list[int] = []
    span_ranges: dict[str, list[tuple[int, int]]] = {}
    rows_kind: list[np.ndarray] = []
    rows_carrier: list[np.ndarray] = []
    rows_ordinal: list[np.ndarray] = []
    blind_cuts = 0
    carrier_rows = 0
    cut_started = time.perf_counter()
    for kind, span_field, decoder in carriers:     # loop-ok: the declared content carriers
        table = ingestion.store.table(kind)
        if not len(table):
            continue
        spans = (table.column(span_field) if span_field else table.witness_span)
        span_ords = spans.to("cpu").numpy().astype(np.int64, copy=False)
        globals_ = table.global_ordinals.to("cpu").numpy().astype(np.int64, copy=False)
        live = span_ords >= 0
        if already.size:
            live &= ~np.isin(globals_, already)
        picked = np.flatnonzero(live)
        if not picked.size:
            continue
        carrier_rows += int(picked.size)
        addresses = ingestion.spans.host_columns[span_ords[picked]]
        emitted = _cut_carrier(ingestion, decoder, recipe, addresses, picked, globals_,
                               kind_index[kind], texts, keys, item_of_leaf, span_ranges,
                               rows_kind, rows_carrier, rows_ordinal)
        blind_cuts += emitted
    cut_seconds = time.perf_counter() - cut_started

    if not texts:
        return ContentBuild(existing or ContentTable(),
                            {"axes": len(declaration.content_axes), "leaves": 0,
                             "carrier_rows": carrier_rows,
                             "why": "no content-bearing row of a declared carrier is new"})

    # --- the leaves' own spans, minted one append per BLOB (never one per leaf)
    span_ordinals: list[np.ndarray] = []
    for handle, ranges in span_ranges.items():     # loop-ok: one step per BLOB of this run
        span_ordinals.append(ingestion.add_spans(handle, ranges).to("cpu").numpy())
    leaf_spans = np.concatenate(span_ordinals).astype(np.int64, copy=False)

    fresh = ContentTable(
        span=leaf_spans,
        carrier_kind=np.concatenate(rows_kind).astype(np.int64, copy=False),
        carrier_row=np.concatenate(rows_carrier).astype(np.int64, copy=False),
        ordinal=np.concatenate(rows_ordinal).astype(np.int64, copy=False))

    # --- the axes: ONE batched encode per axis over every leaf of its carriers
    axis_seconds: dict[str, float] = {}
    encoder_counters: dict[str, Any] = {}
    held: dict[str, SpanEncoder] = dict(encoders or {})
    for axis in declaration.content_axes:          # loop-ok: the declared content axes
        encoder = held.get(axis.encoder_id)
        if encoder is None:
            encoder = span_encoder(axis.encoder_id, device=device)
            held[axis.encoder_id] = encoder
        if encoder.max_tokens < recipe.hard_cap_tokens:
            raise DeclarationRefused(
                "the declared hard cap is wider than this axis's encoder window, so every leaf "
                "at the cap would be silently truncated",
                code="SEGMENTATION-CAP-EXCEEDS-ENCODER-WINDOW", axis=axis.axis,
                hard_cap_tokens=recipe.hard_cap_tokens, encoder_window=encoder.max_tokens)
        if encoder.dim != axis.dim:
            raise DeclarationRefused(
                "the declared stored rank is not this encoder's native dimension; D.4 forbids "
                "post-hoc truncation of an encoder without a trained nested prefix",
                code="CONTENT-AXIS-RANK-INVALID", axis=axis.axis, declared=axis.dim,
                native=encoder.dim)
        started_axis = time.perf_counter()
        vectors = _encode_by_item(encoder, keys, texts,
                                  np.asarray(item_of_leaf, dtype=np.int64), axis.dim)
        fresh.axes[axis.axis] = quantise(vectors, axis.dtype)
        axis_seconds[axis.axis] = time.perf_counter() - started_axis
        encoder_counters[axis.encoder_id] = dict(encoder.counters)

    # --- the token axis and D.6's window honesty, measured with the encoder's own tokenizer
    token_started = time.perf_counter()
    wants_tokens = any(axis.tokens for axis in declaration.content_axes)  # loop-ok: the axes
    if wants_tokens:
        fresh.token_codes, fresh.token_offsets, fresh.surfaces = _token_columns(texts)
    window = held[declaration.content_axes[0].encoder_id]
    lengths = window.token_lengths(texts)
    fresh.tokens_emitted = np.minimum(lengths, window.max_tokens).astype(np.int64, copy=False)
    fresh.tokens_dropped = np.maximum(lengths - window.max_tokens, 0).astype(np.int64,
                                                                            copy=False)
    token_seconds = time.perf_counter() - token_started

    merged = _merge(existing, fresh, declaration)
    receipt = {
        "axes": len(declaration.content_axes),
        "carrier_rows": carrier_rows,
        "leaves_built": len(fresh),
        "leaves_total": len(merged),
        "blind_cuts": blind_cuts,
        "segmentation": recipe.hashed(),
        "segmenter_id": CONTENT_SEGMENTER_ID,
        "cut_seconds": cut_seconds,
        "axis_seconds": axis_seconds,
        "token_seconds": token_seconds,
        "build_seconds": time.perf_counter() - started,
        "encoders": encoder_counters,
        "table": merged.receipt(declaration),
    }
    return ContentBuild(merged, receipt)


def _encode_by_item(encoder: SpanEncoder, keys: list[str], texts: list[str],
                    item_of_leaf: np.ndarray, dim: int) -> np.ndarray:
    """One batched encode PER ITEM, because B.28 makes the item the unit of purity.

    MEASURED 2026-09-22, and it is why this function exists rather than one call over the corpus.
    One call over every leaf of the run gave haystack 0 a different segment key when it was
    ingested alone than when it was ingested beside haystack 1 - two sha256s in the test
    ``test_an_items_segment_does_not_depend_on_what_else_is_in_the_store``. The cause is
    batch composition: the ONNX fp16 graph is not batch-invariant (D.12 calls determinism and
    batch invariance MEASURED properties, not assumptions), and with length-sorted batching a
    leaf's neighbours - and so its padded sequence length - depend on what else was in the run.
    A few components of the fp32 output move in the last bits, one or two int8 codes flip, and
    the item's bytes are no longer a pure function of the item.

    Grouping the encode by item removes the dependence at the source instead of papering over it:
    a leaf's batch now contains only leaves of its own item, whatever else the run holds. The
    batches stay large (one LongMemEval haystack cuts about 1,600 leaves, one QASPER paper about
    60), so this costs one ONNX session call per item rather than one per corpus and nothing per
    leaf. Complexity: O(total tokens) device, one host gather per item.
    """
    out = np.zeros((len(texts), dim), dtype=np.float32)
    if not texts:
        return out
    order = np.argsort(item_of_leaf, kind="stable")
    ordered = item_of_leaf[order]
    edges = np.concatenate([np.zeros(1, dtype=np.int64),
                            np.flatnonzero(np.diff(ordered)) + 1,
                            np.asarray([ordered.size], dtype=np.int64)])
    starts = edges[:-1].tolist()
    stops = edges[1:].tolist()
    for lo, hi in zip(starts, stops):    # loop-ok: ONE batched encode per ITEM (B.28 purity)
        index = order[lo:hi].tolist()
        rows = encoder.embed_cached([keys[position] for position in index],  # loop-ok: one host
                                    [texts[position] for position in index])  # gather per leaf
        out[order[lo:hi]] = rows
    return out


def _cut_carrier(ingestion: Any, decoder: str, recipe: SegmentationRecipe,
                 addresses: np.ndarray, picked: np.ndarray, globals_: np.ndarray,
                 kind_code: int, texts: list[str], keys: list[str], item_of_leaf: list[int],
                 span_ranges: dict[str, list[tuple[int, int]]], rows_kind: list[np.ndarray],
                 rows_carrier: list[np.ndarray], rows_ordinal: list[np.ndarray]) -> int:
    """Cut every picked row of one carrier. One blob read per BLOB, one decode per ROW.

    The address arithmetic is whole-array; what happens once per row is a slice of bytes already
    in memory, a declared decode and the recipe's cut - a constant number of Python calls per
    row, which is what the charter's host-path rule allows. Complexity: O(content bytes).
    """
    blob_ords = addresses[:, 0]
    starts = addresses[:, 1]
    ends = addresses[:, 2]
    order = np.argsort(blob_ords, kind="stable")
    ordered_blobs = blob_ords[order]
    blind = 0
    kinds: list[np.ndarray] = []
    carriers: list[np.ndarray] = []
    ordinals: list[np.ndarray] = []
    for blob in np.unique(ordered_blobs).tolist():   # loop-ok: one step per BLOB (one item's
        lo = int(np.searchsorted(ordered_blobs, blob, "left"))   # bytes), never per row
        hi = int(np.searchsorted(ordered_blobs, blob, "right"))
        here = order[lo:hi]
        handle = ingestion.spans.handle(int(blob))
        data = ingestion.blobs.blob(handle).read()
        bucket = span_ranges.setdefault(handle, [])
        row_starts = starts[here].tolist()
        row_ends = ends[here].tolist()
        row_globals = globals_[picked[here]].tolist()
        counts: list[int] = []
        for position, (row_start, row_end) in enumerate(zip(row_starts, row_ends)):  # loop-ok:
            raw = data[row_start:row_end]            # one declared decode per carrier ROW
            if decoder == "json_string":
                from .extract import locator_for_json_string
                locator = locator_for_json_string(raw, int(row_start))
                text = locator.text
                place = locator.span
            else:
                text = raw.decode("utf-8", "replace")
                offsets = _utf8_char_starts(raw, int(row_start))
                def place(a: int, b: int, _o: np.ndarray = offsets) -> tuple[int, int]:
                    return int(_o[a]), int(_o[b])
            ranges, blind_here = cut_by_recipe(text, recipe)
            blind += blind_here
            counts.append(len(ranges))
            for a, b in ranges:                      # loop-ok: the leaves of ONE carrier row
                bucket.append(place(a, b))
                piece = text[a:b]
                texts.append(piece)
                keys.append(hash_bytes(piece.encode("utf-8")))
                # The ITEM this leaf belongs to. For every dataset here one item is one blob
                # (B.33, B.34), so the blob ordinal IS the item and the encode groups by it.
                item_of_leaf.append(int(blob))
            _ = position
        count_array = np.asarray(counts, dtype=np.int64)
        kinds.append(np.full(int(count_array.sum()), kind_code, dtype=np.int64))
        carriers.append(np.repeat(np.asarray(row_globals, dtype=np.int64), count_array))
        prefix = np.cumsum(count_array) - count_array
        ordinals.append(np.arange(int(count_array.sum()), dtype=np.int64)
                        - np.repeat(prefix, count_array))
    if kinds:
        rows_kind.append(np.concatenate(kinds))
        rows_carrier.append(np.concatenate(carriers))
        rows_ordinal.append(np.concatenate(ordinals))
    return blind


def _utf8_char_starts(raw: bytes, base: int) -> np.ndarray:
    """Absolute byte offset of each decoded character, plus one past the end. O(len(raw)).

    Whole-array: a UTF-8 continuation byte is ``(b & 0xC0) == 0x80``, so the character starts are
    a boolean mask and the map is one ``flatnonzero``. This is the ``utf8`` decoder's half of the
    same job ``extract.locator_for_json_string`` does for a JSON string node.
    """
    if not raw:
        return np.zeros(1, dtype=np.int64) + base
    octets = np.frombuffer(raw, dtype=np.uint8)
    heads = np.flatnonzero((octets & 0xC0) != 0x80).astype(np.int64)
    return np.concatenate([heads, np.asarray([len(raw)], dtype=np.int64)]) + base


def _token_columns(texts: Sequence[str]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """The token axis: flat codes, per-leaf offsets and the ITEM-LOCAL surface list.

    No document frequency and no corpus vocabulary - B.28 forbids an ingestion pass to consult
    one. The postings and the IDF are a projection over the opened record. Complexity: O(total
    characters); one dictionary store per DISTINCT surface.
    """
    surfaces: list[str] = []
    index: dict[str, int] = {}
    codes: list[int] = []
    counts: list[int] = []
    for text in texts:                              # loop-ok: one regex pass per LEAF
        tokens = normalize_tokens(text)
        counts.append(len(tokens))
        for token in tokens:                        # loop-ok: the tokens of ONE leaf
            code = index.get(token)
            if code is None:
                code = len(surfaces)
                surfaces.append(token)
                index[token] = code
            codes.append(code)
    count_array = np.asarray(counts, dtype=np.int64)
    offsets = np.concatenate([np.zeros(1, dtype=np.int64), np.cumsum(count_array)])
    return np.asarray(codes, dtype=np.int64), offsets, surfaces


def _merge(existing: ContentTable | None, fresh: ContentTable,
           declaration: DatasetDeclaration) -> ContentTable:
    """Append a freshly built block to what a warm open already installed. O(total)."""
    if existing is None or not len(existing):
        return fresh
    return concatenate([existing, fresh], declaration)


def concatenate(tables: Sequence[ContentTable],
                declaration: DatasetDeclaration) -> ContentTable:
    """One table out of several, re-interning the token surfaces. O(total), no per-row Python."""
    live = [table for table in tables if len(table)]  # loop-ok: the tables being joined
    if not live:
        return ContentTable()
    if len(live) == 1:
        return live[0]
    out = ContentTable(
        span=np.concatenate([t.span for t in live]),              # loop-ok: the tables joined
        carrier_kind=np.concatenate([t.carrier_kind for t in live]),      # loop-ok: as above
        carrier_row=np.concatenate([t.carrier_row for t in live]),        # loop-ok: as above
        ordinal=np.concatenate([t.ordinal for t in live]),                # loop-ok: as above
        tokens_emitted=np.concatenate([t.tokens_emitted for t in live]),  # loop-ok: as above
        tokens_dropped=np.concatenate([t.tokens_dropped for t in live]))  # loop-ok: as above
    surfaces: list[str] = []
    index: dict[str, int] = {}
    code_blocks: list[np.ndarray] = []
    offset_blocks: list[np.ndarray] = []
    running = 0
    for table in live:                              # loop-ok: the tables being joined
        mapping = np.asarray([_intern(surfaces, index, surface)
                              for surface in table.surfaces], dtype=np.int64)  # loop-ok: the
        code_blocks.append(mapping[table.token_codes] if mapping.size       # table's surfaces
                           else table.token_codes)
        offset_blocks.append(table.token_offsets[1:] + running)
        running += int(table.token_offsets[-1])
    out.token_codes = np.concatenate(code_blocks) if code_blocks else np.zeros(0, dtype=np.int64)
    out.token_offsets = np.concatenate([np.zeros(1, dtype=np.int64)] + offset_blocks)
    out.surfaces = surfaces
    for axis in declaration.content_axes:           # loop-ok: the declared content axes
        blocks = [t.axes[axis.axis] for t in live if axis.axis in t.axes]  # loop-ok: as above
        if len(blocks) != len(live):
            continue
        out.axes[axis.axis] = {
            "code": np.concatenate([b["code"] for b in blocks]),     # loop-ok: the blocks joined
            "scale": np.concatenate([b["scale"] for b in blocks]),   # loop-ok: as above
            "eps": np.concatenate([b["eps"] for b in blocks])}       # loop-ok: as above
    return out


def _intern(surfaces: list[str], index: dict[str, int], surface: str) -> int:
    found = index.get(surface)
    if found is None:
        found = len(surfaces)
        surfaces.append(surface)
        index[surface] = found
    return found


# --------------------------------------------------------------------------- persistence
def content_arrays(table: ContentTable, rows: np.ndarray, span_local: np.ndarray,
                   kind_local: np.ndarray,
                   declaration: DatasetDeclaration) -> tuple[dict[str, np.ndarray],
                                                             dict[str, Any]]:
    """One item's slice of the content table, as segment arrays plus its header entry.

    ``rows`` are this item's content rows; ``span_local`` their item-local span indices and
    ``kind_local`` their carrier's item-local row ordinal. The token surfaces are re-interned
    over the surfaces THIS item uses, which is what makes the segment bytes a pure function of
    the item (B.28). Complexity: O(rows + this item's token occurrences).
    """
    if not rows.size:
        return {}, {}
    arrays: dict[str, np.ndarray] = {
        "content.span": span_local.astype("<i8", copy=False),
        "content.carrier_kind": table.carrier_kind[rows].astype("<i8", copy=False),
        "content.carrier_local": kind_local.astype("<i8", copy=False),
        "content.ordinal": table.ordinal[rows].astype("<i8", copy=False),
        "content.tokens_emitted": table.tokens_emitted[rows].astype("<i8", copy=False),
        "content.tokens_dropped": table.tokens_dropped[rows].astype("<i8", copy=False),
    }
    header: dict[str, Any] = {"count": int(rows.size), "axes": {}, "surfaces": []}
    lengths = (table.token_offsets[rows + 1] - table.token_offsets[rows]).astype(np.int64)
    if int(lengths.sum()):
        gather = (np.arange(int(lengths.sum()), dtype=np.int64)
                  - np.repeat(np.concatenate([np.zeros(1, dtype=np.int64),
                                              np.cumsum(lengths)])[:-1], lengths)
                  + np.repeat(table.token_offsets[rows], lengths))
        codes = table.token_codes[gather]
        used, local = np.unique(codes, return_inverse=True)
        header["surfaces"] = [table.surfaces[int(code)] for code in used.tolist()]  # loop-ok:
        arrays["content.token_codes"] = local.reshape(-1).astype("<i8", copy=False)  # the item's
    else:                                                                            # surfaces
        arrays["content.token_codes"] = np.zeros(0, dtype="<i8")
    arrays["content.token_lengths"] = lengths.astype("<i8", copy=False)
    for axis in declaration.content_axes:           # loop-ok: the declared content axes
        block = table.axes.get(axis.axis)
        if block is None:
            continue
        arrays[f"content.axis.{axis.axis}.code"] = np.ascontiguousarray(block["code"][rows])
        arrays[f"content.axis.{axis.axis}.scale"] = np.ascontiguousarray(block["scale"][rows])
        arrays[f"content.axis.{axis.axis}.eps"] = np.ascontiguousarray(block["eps"][rows])
        header["axes"][axis.axis] = {"dim": axis.dim, "dtype": axis.dtype,
                                     "encoder_id": axis.encoder_id}
    return arrays, header


def content_from_arrays(arrays: Mapping[str, np.ndarray], header: Mapping[str, Any],
                        declaration: DatasetDeclaration) -> ContentTable:
    """One segment's content back as a table, with item-local ordinals still item-local. O(n)."""
    count = int(header.get("count", 0))
    if not count:
        return ContentTable()
    lengths = np.asarray(arrays["content.token_lengths"], dtype=np.int64)
    table = ContentTable(
        span=np.asarray(arrays["content.span"], dtype=np.int64),
        carrier_kind=np.asarray(arrays["content.carrier_kind"], dtype=np.int64),
        carrier_row=np.asarray(arrays["content.carrier_local"], dtype=np.int64),
        ordinal=np.asarray(arrays["content.ordinal"], dtype=np.int64),
        tokens_emitted=np.asarray(arrays["content.tokens_emitted"], dtype=np.int64),
        tokens_dropped=np.asarray(arrays["content.tokens_dropped"], dtype=np.int64),
        token_codes=np.asarray(arrays["content.token_codes"], dtype=np.int64),
        token_offsets=np.concatenate([np.zeros(1, dtype=np.int64), np.cumsum(lengths)]),
        surfaces=list(header.get("surfaces", ())))
    for axis in declaration.content_axes:           # loop-ok: the declared content axes
        key = f"content.axis.{axis.axis}.code"
        if key not in arrays:
            continue
        table.axes[axis.axis] = {
            "code": np.asarray(arrays[key]),
            "scale": np.asarray(arrays[f"content.axis.{axis.axis}.scale"], dtype=np.float32),
            "eps": np.asarray(arrays[f"content.axis.{axis.axis}.eps"], dtype=np.float32)}
    if int(table.span.size) != count:
        raise MalformedSource("a content segment's span count is not its declared count",
                              declared=count, spans=int(table.span.size))
    return table


def content_digest(table: ContentTable, spans: np.ndarray,
                   declaration: DatasetDeclaration) -> dict[str, str]:
    """The content layer hashed through its OWN identities: addresses, not ordinals.

    A leaf is its span ADDRESS (blob rank, start, end), its carrier's kind and its ordinal within
    that carrier; its observations are the stored code bytes and the sorted surfaces of its token
    set. Nothing here is a span ordinal, a global row ordinal or an arrival order, so a cold run
    and a warm one agree without sharing a layout. Complexity: O(n log n + n d).
    """
    if not len(table):
        return {}
    address = spans[table.span]
    order = np.lexsort((table.ordinal, table.carrier_kind, address[:, 2], address[:, 1],
                        address[:, 0]))
    matrix = np.concatenate([address[order], table.carrier_kind[order][:, None],
                             table.ordinal[order][:, None]], axis=1)
    out = {"content.leaves": hash_bytes(np.ascontiguousarray(matrix, dtype="<i8").tobytes())}
    lengths = (table.token_offsets[order + 1] - table.token_offsets[order]).astype(np.int64)
    if int(lengths.sum()):
        gather = (np.arange(int(lengths.sum()), dtype=np.int64)
                  - np.repeat(np.concatenate([np.zeros(1, dtype=np.int64),
                                              np.cumsum(lengths)])[:-1], lengths)
                  + np.repeat(table.token_offsets[order], lengths))
        surfaces = np.asarray(table.surfaces, dtype=object)[table.token_codes[gather]]
        joined = chr(0).join(surfaces.tolist()).encode("utf-8")
        out["content.tokens"] = hash_bytes(joined + b"|" + lengths.tobytes())
    for axis in declaration.content_axes:           # loop-ok: the declared content axes
        block = table.axes.get(axis.axis)
        if block is None:
            continue
        out[f"content.axis.{axis.axis}"] = hash_bytes(
            np.ascontiguousarray(block["code"][order]).tobytes()
            + np.ascontiguousarray(block["scale"][order], dtype="<f4").tobytes())
    return out


# Content-build receipt fields, not encoder parameters or quantization error data.

# The inert closed receipt contract; numeric execution remains owned here.
from ..receipt_diagnostics import content_build_parts
