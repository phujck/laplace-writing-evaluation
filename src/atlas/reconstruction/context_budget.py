"""Cached canonical context packing under an exact whole-JSON token budget."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Mapping, Protocol, Sequence


class Tokenizer(Protocol):
    def encode(self, text: str) -> Sequence[int]: ...


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class CachedObservation:
    observation_id: str
    public: Mapping[str, object]
    canonical_json: str
    standalone_tokens: int
    first_fragment_tokens: int
    next_fragment_tokens: int


@dataclass(frozen=True, slots=True)
class ContextCacheReceipt:
    observations: int
    serialization_calls: int
    tokenization_calls: int
    canonical_utf8_bytes: int
    public_fields: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ContextCache:
    observations: tuple[CachedObservation, ...]
    by_id: Mapping[str, CachedObservation]
    empty_list_tokens: int
    closing_fragment_tokens: int
    receipt: ContextCacheReceipt


@dataclass(frozen=True, slots=True)
class PackReceipt:
    planning_rule: str
    planning_token_estimate: int
    exact_encode_calls: int
    repair_removals: int
    fill_attempts: int
    fill_acceptances: int
    final_exact_tokens: int
    token_budget: int
    max_objects: int
    canonical_serializations_during_pack: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PackedContext:
    observation_ids: tuple[str, ...]
    public_items: tuple[Mapping[str, object], ...]
    canonical_json: str
    token_count: int
    rejected_ids: tuple[str, ...]
    receipt: PackReceipt


def cache_context_observations(
    observations: Sequence[Mapping[str, object]],
    tokenizer: Tokenizer,
    *,
    public_fields: Sequence[str] = ("id", "text", "sources", "dates"),
    id_field: str = "id",
) -> ContextCache:
    """Serialize and tokenize each public observation once at ingestion."""
    fields = tuple(str(field) for field in public_fields)
    if not fields or id_field not in fields:
        raise ValueError("public_fields must be nonempty and include id_field")
    if len(set(fields)) != len(fields):
        raise ValueError("public_fields must not contain duplicates")
    cached = []
    seen = set()
    utf8_bytes = 0
    tokenization_calls = 0
    for observation in observations:
        missing = [field for field in fields if field not in observation]
        if missing:
            raise KeyError(f"observation missing public fields: {missing}")
        observation_id = str(observation[id_field])
        if not observation_id:
            raise ValueError("observation IDs must be nonempty")
        if observation_id in seen:
            raise ValueError(f"duplicate observation ID: {observation_id}")
        seen.add(observation_id)
        public = {field: observation[field] for field in fields}
        serialized = canonical(public)
        standalone = len(tokenizer.encode(serialized))
        first = len(tokenizer.encode("[" + serialized))
        following = len(tokenizer.encode("," + serialized))
        tokenization_calls += 3
        utf8_bytes += len(serialized.encode("utf-8"))
        cached.append(CachedObservation(
            observation_id, public, serialized,
            standalone, first, following))
    empty = len(tokenizer.encode("[]"))
    closing = len(tokenizer.encode("]"))
    tokenization_calls += 2
    by_id = {item.observation_id: item for item in cached}
    receipt = ContextCacheReceipt(
        len(cached), len(cached), tokenization_calls, utf8_bytes, fields)
    return ContextCache(tuple(cached), by_id, empty, closing, receipt)


def _render(items: Sequence[CachedObservation]) -> str:
    # Item JSON bytes are cached.  Packing joins fragments and never serializes
    # a growing Python list.
    return "[" + ",".join(item.canonical_json for item in items) + "]"


def _exact_tokens(items: Sequence[CachedObservation], tokenizer: Tokenizer) -> tuple[str, int]:
    rendered = _render(items)
    return rendered, len(tokenizer.encode(rendered))


def pack_context(
    cache: ContextCache,
    ordered_ids: Sequence[str],
    tokenizer: Tokenizer,
    *,
    token_budget: int = 2000,
    max_objects: int = 20,
    max_fill_attempts: int | None = None,
) -> PackedContext:
    """Pack ordered IDs and certify the final whole canonical JSON exactly.

    Cached fragment token counts are a planning estimate, not an additive BPE
    theorem.  One exact whole-list encode is mandatory.  Any overrun is repaired
    by exact re-encoding after removal; bounded exact fill attempts recover space
    lost when the planning estimate was conservative.  All such work is reported.
    """
    if token_budget <= 0 or max_objects <= 0:
        raise ValueError("token_budget and max_objects must be positive")
    if cache.empty_list_tokens > token_budget:
        raise ValueError("token budget cannot encode the empty canonical list")
    fill_limit = max_objects if max_fill_attempts is None else int(max_fill_attempts)
    if fill_limit < 0:
        raise ValueError("max_fill_attempts must be nonnegative")

    unique_ids = []
    seen = set()
    for raw_id in ordered_ids:
        observation_id = str(raw_id)
        if observation_id in seen:
            continue
        if observation_id not in cache.by_id:
            raise KeyError(f"uncached observation ID: {observation_id}")
        seen.add(observation_id)
        unique_ids.append(observation_id)
    position = {observation_id: index for index, observation_id in enumerate(unique_ids)}

    selected: list[CachedObservation] = []
    planning_rejected: list[CachedObservation] = []
    planned = cache.closing_fragment_tokens
    for observation_id in unique_ids:
        item = cache.by_id[observation_id]
        if len(selected) >= max_objects:
            planning_rejected.append(item)
            continue
        marginal = item.first_fragment_tokens if not selected else item.next_fragment_tokens
        if planned + marginal <= token_budget:
            selected.append(item)
            planned += marginal
        else:
            planning_rejected.append(item)

    exact_calls = 1
    rendered, exact = _exact_tokens(selected, tokenizer)
    repair_removals = 0
    while exact > token_budget and selected:
        planning_rejected.append(selected.pop())
        repair_removals += 1
        exact_calls += 1
        rendered, exact = _exact_tokens(selected, tokenizer)
    if exact > token_budget:
        raise AssertionError("empty canonical list exceeded a prechecked budget")

    # The estimate may be conservative.  Try a bounded number of rejected
    # observations, preserving the caller's exact order on successful insertion.
    fill_attempts = fill_acceptances = 0
    rejected_by_id = {item.observation_id: item for item in planning_rejected}
    for item in sorted(rejected_by_id.values(), key=lambda value: position[value.observation_id]):
        if fill_attempts >= fill_limit or len(selected) >= max_objects:
            break
        trial = sorted((*selected, item), key=lambda value: position[value.observation_id])
        fill_attempts += 1
        exact_calls += 1
        trial_rendered, trial_exact = _exact_tokens(trial, tokenizer)
        if trial_exact <= token_budget:
            selected = list(trial)
            rendered, exact = trial_rendered, trial_exact
            fill_acceptances += 1

    selected_ids = tuple(item.observation_id for item in selected)
    selected_set = set(selected_ids)
    rejected = tuple(observation_id for observation_id in unique_ids
                     if observation_id not in selected_set)
    if exact != len(tokenizer.encode(rendered)):
        raise AssertionError("final exact token count is not reproducible")
    exact_calls += 1
    if exact > token_budget or len(selected) > max_objects:
        raise AssertionError("context pack violates its declared bounds")
    receipt = PackReceipt(
        planning_rule="cached fragment estimate; not assumed BPE-additive",
        planning_token_estimate=planned, exact_encode_calls=exact_calls,
        repair_removals=repair_removals, fill_attempts=fill_attempts,
        fill_acceptances=fill_acceptances, final_exact_tokens=exact,
        token_budget=token_budget, max_objects=max_objects,
        canonical_serializations_during_pack=0)
    return PackedContext(
        selected_ids, tuple(item.public for item in selected), rendered, exact,
        rejected, receipt)


__all__ = [
    "CachedObservation", "ContextCache", "PackedContext", "cache_context_observations",
    "canonical", "pack_context",
]
