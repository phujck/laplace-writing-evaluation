"""Sparse CUDA lexical observations for BM25 proposals and exact token support.

String normalization and collision-free token-ID assignment are host ingestion
serialization.  Term/document statistics, posting aggregation, BM25 values and
query scoring are CUDA operations.  Token support is an observed lexical
predicate; this module never promotes it to entailment or answer truth.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import re
import unicodedata
from typing import Mapping, Sequence

import torch


from .gpu_budget import resolve_gpu_budget


_TOKEN = re.compile(r"[^\W_]+(?:[-'’][^\W_]+)*", re.UNICODE)


def normalize_tokens(text: str) -> tuple[str, ...]:
    """Return observable word-form tokens; no stemming or entity inference."""
    normalized = unicodedata.normalize("NFKC", str(text)).casefold().replace("’", "'")
    return tuple(match.group(0) for match in _TOKEN.finditer(normalized))


@dataclass(frozen=True, slots=True)
class JurisdictionColumn:
    field: str
    values: tuple[str, ...]
    value_to_code: Mapping[str, int]
    codes: torch.Tensor


@dataclass(frozen=True, slots=True)
class LexicalBuildReceipt:
    observations: int
    normalized_token_occurrences: int
    vocabulary_size: int
    posting_rows: int
    posting_chunks: int
    numeric_device: str
    numeric_aggregation: str
    gpu_stored_bytes: int
    host_stored_bytes: int
    stored_bytes: int
    storage_accounting: str
    preflight_peak_upper_bytes: int
    budget: dict
    source_text_sha256: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LexicalIndex:
    observation_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    id_to_token: tuple[str, ...]
    token_to_id: Mapping[str, int]
    posting_offsets: torch.Tensor       # [V+1], token-major
    posting_observation_rows: torch.Tensor
    term_frequency: torch.Tensor
    document_frequency: torch.Tensor
    inverse_document_frequency: torch.Tensor
    document_lengths: torch.Tensor
    bm25_values: torch.Tensor
    jurisdictions: Mapping[str, JurisdictionColumn]
    k1: float
    b: float
    receipt: LexicalBuildReceipt

    @property
    def device(self) -> torch.device:
        return self.posting_offsets.device

    @property
    def observations(self) -> int:
        return len(self.observation_ids)


@dataclass(frozen=True, slots=True)
class SparseLexicalScores:
    rows: torch.Tensor
    scores: torch.Tensor
    valid: torch.Tensor
    unknown_tokens: tuple[tuple[str, ...], ...]
    work: dict


def _tensor_bytes(value: torch.Tensor) -> int:
    return value.numel() * value.element_size()


def _host_bytes(strings: Sequence[str]) -> int:
    return sum(len(value.encode("utf-8")) for value in strings)


def _validate_metadata(
    texts: Sequence[str],
    observation_ids: Sequence[str] | None,
    source_ids: Sequence[str] | None,
    jurisdictions: Mapping[str, Sequence[str]] | None,
) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, tuple[str, ...]]]:
    n = len(texts)
    raw_observation_ids = (observation_ids if observation_ids is not None
                           else tuple(f"observation:{i}" for i in range(n)))
    obs = tuple(str(value) for value in raw_observation_ids)
    src = tuple(str(value) for value in (source_ids if source_ids is not None else obs))
    if len(obs) != n or len(src) != n:
        raise ValueError("observation_ids and source_ids must align with texts")
    if any(not value for value in obs):
        raise ValueError("observation_ids must be nonempty")
    if len(set(obs)) != n:
        raise ValueError("observation_ids must be unique")
    fields: dict[str, tuple[str, ...]] = {"source_id": src}
    for field, values in (jurisdictions or {}).items():
        name = str(field)
        if not name or name == "source_id":
            raise ValueError("jurisdiction fields must be nonempty and cannot replace source_id")
        rows = tuple(str(value) for value in values)
        if len(rows) != n:
            raise ValueError(f"jurisdiction field {name!r} does not align with texts")
        fields[name] = rows
    return obs, src, fields


def _jurisdiction_columns(fields: Mapping[str, tuple[str, ...]], device: torch.device) -> dict[str, JurisdictionColumn]:
    result = {}
    for field, rows in fields.items():
        values = tuple(sorted(set(rows)))
        value_to_code = {value: index for index, value in enumerate(values)}
        codes = torch.tensor([value_to_code[value] for value in rows], dtype=torch.int64, device=device)
        result[field] = JurisdictionColumn(field, values, value_to_code, codes)
    return result


def _build_chunks(offsets: Sequence[int], max_occurrences: int) -> list[tuple[int, int]]:
    chunks = []
    start = 0
    n = len(offsets) - 1
    while start < n:
        stop = start + 1
        if offsets[stop] - offsets[start] > max_occurrences:
            raise MemoryError("one observation exceeds the lexical CUDA work-chunk budget")
        while stop < n and offsets[stop + 1] - offsets[start] <= max_occurrences:
            stop += 1
        chunks.append((start, stop))
        start = stop
    return chunks


@torch.no_grad()
def build_lexical_index(
    texts: Sequence[str],
    device: str | torch.device = "cuda",
    *,
    observation_ids: Sequence[str] | None = None,
    source_ids: Sequence[str] | None = None,
    jurisdictions: Mapping[str, Sequence[str]] | None = None,
    max_bytes: int | None = None,
    k1: float = 1.2,
    b: float = 0.75,
) -> LexicalIndex:
    """Build token-major postings with CUDA TF/DF/IDF aggregation.

    ``texts`` are source-visible observations only.  Answer aliases, evidence
    annotations and evaluator labels do not belong in this interface.
    """
    device = torch.device(device)
    if device.type != "cuda":
        raise TypeError("lexical numeric construction requires CUDA")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable")
    if not texts:
        raise ValueError("at least one source observation is required")
    if k1 <= 0 or not 0 <= b <= 1:
        raise ValueError("BM25 requires k1>0 and 0<=b<=1")
    text_rows = tuple(str(text) for text in texts)
    obs, src, jurisdiction_rows = _validate_metadata(
        text_rows, observation_ids, source_ids, jurisdictions)

    # Host-only ingestion serialization: normalize each source string once,
    # assign exact token strings to a collision-free sorted vocabulary.
    token_rows = tuple(normalize_tokens(text) for text in text_rows)
    id_to_token = tuple(sorted({token for row in token_rows for token in row}))
    token_to_id = {token: index for index, token in enumerate(id_to_token)}
    if len(token_to_id) != len(id_to_token):
        raise AssertionError("collision-free vocabulary construction failed")
    n, vocabulary = len(text_rows), len(id_to_token)
    if vocabulary == 0:
        raise ValueError("source observations contain no lexical tokens")
    if n > (torch.iinfo(torch.int64).max // vocabulary):
        raise OverflowError("document/token pair encoding exceeds int64")
    token_ids = tuple(tuple(token_to_id[token] for token in row) for row in token_rows)
    offsets = [0]
    for row in token_ids:
        offsets.append(offsets[-1] + len(row))
    occurrences = offsets[-1]

    jurisdiction_bytes = n * 8 * len(jurisdiction_rows)
    # P<=occurrences.  This is a conservative final-resident preflight, not a
    # host-computed posting count; posting aggregation itself remains on CUDA.
    # The 80-byte per-occurrence construction allowance covers the P<=T final
    # postings, chunk-list tensors, concatenated copies, global token-major sort
    # keys/order and sorted outputs while Python references are still live.
    # Actual retained storage is measured separately in the receipt.
    resident_upper = occurrences * 80 + (vocabulary + 1) * 8
    resident_upper += vocabulary * (8 + 4) + n * 4 + jurisdiction_bytes
    budget = resolve_gpu_budget(device, max_bytes=max_bytes, resident_bytes=resident_upper)
    fixed_upper = resident_upper
    available_work = budget.max_bytes - fixed_upper
    per_occurrence_work = 8 * 6
    max_occurrences = available_work // per_occurrence_work
    if max_occurrences <= 0:
        raise MemoryError("lexical resident upper bound leaves no CUDA aggregation workspace")
    chunks = _build_chunks(offsets, int(max_occurrences))
    largest = max(offsets[stop] - offsets[start] for start, stop in chunks)
    peak_upper = fixed_upper + largest * per_occurrence_work
    if peak_upper > budget.max_bytes:
        raise MemoryError("lexical CUDA preflight exceeds budget")

    posting_docs = []
    posting_tokens = []
    posting_tf = []
    document_lengths = torch.zeros(n, dtype=torch.float32, device=device)
    for start, stop in chunks:
        flat_tokens = [token for row in token_ids[start:stop] for token in row]
        flat_docs = [doc for doc, row in enumerate(token_ids[start:stop], start)
                     for _ in row]
        doc_tensor = torch.tensor(flat_docs, dtype=torch.int64, device=device)
        token_tensor = torch.tensor(flat_tokens, dtype=torch.int64, device=device)
        document_lengths.add_(torch.bincount(doc_tensor, minlength=n).to(torch.float32))
        pairs = doc_tensor * vocabulary + token_tensor
        unique_pairs, counts = torch.unique(pairs, sorted=True, return_counts=True)
        posting_docs.append(torch.div(unique_pairs, vocabulary, rounding_mode="floor"))
        posting_tokens.append(torch.remainder(unique_pairs, vocabulary))
        posting_tf.append(counts.to(torch.float32))

    docs = torch.cat(posting_docs)
    tokens = torch.cat(posting_tokens)
    tf = torch.cat(posting_tf)
    del posting_docs, posting_tokens, posting_tf
    order = torch.argsort(tokens * n + docs)
    docs, tokens, tf = docs[order], tokens[order], tf[order]
    del order
    df = torch.bincount(tokens, minlength=vocabulary)
    posting_offsets = torch.zeros(vocabulary + 1, dtype=torch.int64, device=device)
    posting_offsets[1:] = torch.cumsum(df, dim=0)
    idf = torch.log1p((n - df.to(torch.float32) + 0.5) / (df.to(torch.float32) + 0.5))
    average_length = document_lengths.mean().clamp_min(1.0)
    normalizer = tf + k1 * (1.0 - b + b * document_lengths[docs] / average_length)
    bm25_values = idf[tokens] * (tf * (k1 + 1.0) / normalizer)
    del normalizer
    del tokens
    jurisdiction_columns = _jurisdiction_columns(jurisdiction_rows, device)

    tensors = (posting_offsets, docs, tf, df, idf, document_lengths, bm25_values,
               *(column.codes for column in jurisdiction_columns.values()))
    gpu_bytes = sum(_tensor_bytes(value) for value in tensors)
    extra_jurisdiction_strings = []
    for field, column in jurisdiction_columns.items():
        if field != "source_id":
            extra_jurisdiction_strings.extend((field, *column.values))
    host_bytes = _host_bytes((*obs, *src, *id_to_token, *extra_jurisdiction_strings))
    digest = sha256()
    for observation_id, source_id, text in zip(obs, src, text_rows):
        digest.update(observation_id.encode("utf-8")); digest.update(b"\0")
        digest.update(source_id.encode("utf-8")); digest.update(b"\0")
        digest.update(text.encode("utf-8")); digest.update(b"\0")
    receipt = LexicalBuildReceipt(
        observations=n, normalized_token_occurrences=occurrences,
        vocabulary_size=vocabulary, posting_rows=docs.numel(),
        posting_chunks=len(chunks), numeric_device=str(device),
        numeric_aggregation="CUDA unique/bincount/cumsum/scatter-compatible token-major postings",
        gpu_stored_bytes=gpu_bytes, host_stored_bytes=host_bytes,
        stored_bytes=gpu_bytes + host_bytes,
        storage_accounting="tensor payload plus UTF-8 ID/vocabulary/jurisdiction payload; Python object overhead excluded",
        preflight_peak_upper_bytes=peak_upper,
        budget=budget.receipt(), source_text_sha256=digest.hexdigest())
    return LexicalIndex(obs, src, id_to_token, token_to_id, posting_offsets, docs, tf,
                        df, idf, document_lengths, bm25_values,
                        jurisdiction_columns, float(k1), float(b), receipt)


def _query_bank(index: LexicalIndex, querytexts: Sequence[str]):
    normalized = tuple(normalize_tokens(text) for text in querytexts)
    known_rows = []
    unknown = []
    for row in normalized:
        ids = [index.token_to_id[token] for token in row if token in index.token_to_id]
        known_rows.append(tuple(ids))
        unknown.append(tuple(dict.fromkeys(token for token in row if token not in index.token_to_id)))
    return tuple(known_rows), tuple(unknown)


def _jurisdiction_mask(index: LexicalIndex, jurisdiction: Mapping[str, str] | None) -> torch.Tensor:
    mask = torch.ones(index.observations, dtype=torch.bool, device=index.device)
    for field, value in (jurisdiction or {}).items():
        if field not in index.jurisdictions:
            return torch.zeros_like(mask)
        column = index.jurisdictions[field]
        code = column.value_to_code.get(str(value))
        if code is None:
            return torch.zeros_like(mask)
        mask &= column.codes == code
    return mask


def _route_batch(index: LexicalIndex, query_rows: Sequence[tuple[int, ...]], *, unique: bool):
    query_ids, token_ids = [], []
    for query, row in enumerate(query_rows):
        for token in row:
            query_ids.append(query); token_ids.append(token)
    if not token_ids:
        empty = torch.empty(0, dtype=torch.int64, device=index.device)
        return (empty, empty, torch.empty(0, dtype=torch.float32, device=index.device),
                empty, empty)
    q_occurrence = torch.tensor(query_ids, dtype=torch.int64, device=index.device)
    token_occurrence = torch.tensor(token_ids, dtype=torch.int64, device=index.device)
    query_token_pairs = q_occurrence * len(index.id_to_token) + token_occurrence
    unique_pairs, counts = torch.unique(query_token_pairs, sorted=True, return_counts=True)
    q = torch.div(unique_pairs, len(index.id_to_token), rounding_mode="floor")
    token = torch.remainder(unique_pairs, len(index.id_to_token))
    weight = (torch.ones_like(counts, dtype=torch.float32) if unique
              else counts.to(torch.float32))
    starts = index.posting_offsets[token]
    lengths = index.posting_offsets[token + 1] - starts
    total = int(lengths.sum().item())
    if total == 0:
        empty = torch.empty(0, dtype=torch.int64, device=index.device)
        return (empty, empty, torch.empty(0, dtype=torch.float32, device=index.device),
                empty, q)
    repeated_starts = torch.repeat_interleave(starts, lengths)
    repeated_q = torch.repeat_interleave(q, lengths)
    repeated_weight = torch.repeat_interleave(weight, lengths)
    prefix = torch.cumsum(lengths, 0) - lengths
    local = torch.arange(total, device=index.device) - torch.repeat_interleave(prefix, lengths)
    routes = repeated_starts + local
    return repeated_q, index.posting_observation_rows[routes], repeated_weight, routes, q


def _query_batch_size(
    index: LexicalIndex,
    queries: int,
    budget_bytes: int,
    *,
    output_bytes: int,
    workspace_per_document: int,
) -> int:
    # One query can route every posting at most once because query token IDs are
    # uniqued before expansion.  The 48-byte route allowance covers expanded
    # starts/query IDs/weights/prefix/local/routes plus contribution storage.
    per_query = index.observations * workspace_per_document
    per_query += index.receipt.posting_rows * 48
    available = budget_bytes - index.receipt.gpu_stored_bytes - output_bytes
    if available < per_query:
        raise MemoryError("lexical query workspace exceeds CUDA budget")
    return max(1, min(queries, available // max(per_query, 1)))


@torch.no_grad()
def score_token_queries(
    index: LexicalIndex,
    querytexts: Sequence[str],
    *,
    top_k: int | None = None,
    max_bytes: int | None = None,
    jurisdiction: Mapping[str, str] | None = None,
) -> torch.Tensor | SparseLexicalScores:
    """Score a bounded query bank from token postings; no corpus text is scanned."""
    if not querytexts:
        raise ValueError("at least one query is required")
    if top_k is not None and top_k <= 0:
        raise ValueError("top_k must be positive")
    rows, unknown = _query_bank(index, tuple(str(text) for text in querytexts))
    budget = resolve_gpu_budget(index.device, max_bytes=max_bytes,
                                resident_bytes=index.receipt.gpu_stored_bytes)
    selected_k = min(top_k, index.observations) if top_k is not None else None
    output_bytes = (len(rows) * index.observations * 4 if selected_k is None
                    else len(rows) * selected_k * (8 + 4 + 1))
    batch_size = _query_batch_size(
        index, len(rows), budget.max_bytes, output_bytes=output_bytes,
        workspace_per_document=4)
    jurisdiction_mask = _jurisdiction_mask(index, jurisdiction)
    dense_parts = []
    top_rows, top_scores, top_valid = [], [], []
    postings_read = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        scores = torch.zeros((len(batch), index.observations), dtype=torch.float32,
                             device=index.device)
        query_ids, docs, qtf, routes, _ = _route_batch(index, batch, unique=False)
        if isinstance(routes, torch.Tensor) and routes.numel():
            contribution = index.bm25_values[routes] * qtf
            scores.view(-1).index_add_(0, query_ids * index.observations + docs, contribution)
            postings_read += routes.numel()
        scores.masked_fill_(~jurisdiction_mask[None, :], -torch.inf)
        for local, token_row in enumerate(batch):
            if not token_row:
                scores[local].fill_(-torch.inf)
        if top_k is None:
            dense_parts.append(scores)
        else:
            k = selected_k
            values, selected = torch.topk(scores, k, dim=1)
            top_rows.append(selected); top_scores.append(values)
            top_valid.append(torch.isfinite(values) & (values > 0))
    if top_k is None:
        return torch.cat(dense_parts, 0)
    return SparseLexicalScores(
        torch.cat(top_rows, 0), torch.cat(top_scores, 0), torch.cat(top_valid, 0), unknown,
        {"postings_read": postings_read, "corpus_text_rows_scanned": 0,
         "query_batches": (len(rows) + batch_size - 1) // batch_size,
         "budget": budget.receipt(), "semantic_certificate": False})


@torch.no_grad()
def exact_and_support(
    index: LexicalIndex,
    querytexts: Sequence[str],
    *,
    jurisdiction: Mapping[str, str] | None = None,
    max_bytes: int | None = None,
) -> torch.Tensor:
    """Return exact normalized-token AND incidence, distinct from BM25 relevance."""
    if not querytexts:
        raise ValueError("at least one token observation query is required")
    rows, unknown = _query_bank(index, tuple(str(text) for text in querytexts))
    budget = resolve_gpu_budget(index.device, max_bytes=max_bytes,
                                resident_bytes=index.receipt.gpu_stored_bytes)
    output_bytes = len(rows) * index.observations  # bool output
    batch_size = _query_batch_size(
        index, len(rows), budget.max_bytes, output_bytes=output_bytes,
        workspace_per_document=8)
    jurisdiction_mask = _jurisdiction_mask(index, jurisdiction)
    output = []
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        hits = torch.zeros((len(batch), index.observations), dtype=torch.int32,
                           device=index.device)
        query_ids, docs, _, routes, unique_query_ids = _route_batch(index, batch, unique=True)
        if isinstance(routes, torch.Tensor) and routes.numel():
            hits.view(-1).index_add_(
                0, query_ids * index.observations + docs,
                torch.ones_like(query_ids, dtype=torch.int32))
        required = torch.bincount(unique_query_ids, minlength=len(batch)).to(torch.int32)[:, None]
        supported = (hits == required) & (required > 0) & jurisdiction_mask[None, :]
        for local, missed in enumerate(unknown[start:start + len(batch)]):
            if missed:
                supported[local].zero_()
        output.append(supported)
    return torch.cat(output, 0)


__all__ = [
    "LexicalBuildReceipt", "LexicalIndex", "SparseLexicalScores",
    "build_lexical_index", "exact_and_support", "normalize_tokens", "score_token_queries",
]
