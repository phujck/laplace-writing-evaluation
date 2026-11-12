"""Exact incremental token counts for canonical JSON observation lists.

tiktoken first partitions text with its frozen regex, then applies BPE inside
each match. Concatenating canonical JSON objects can therefore change only the
last regex match of the previous object and the first match of the next object.
This module caches every object's interior token count and recomputes only those
boundary seams. A final full encode is mandatory; any failed regex invariant or
count disagreement falls back to the caller's exact whole-context path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import regex


@dataclass(frozen=True, slots=True)
class SeamObject:
    observation_id: str
    prefix: str
    suffix: str
    middle_tokens: int
    start_tokens: int
    close_tokens: int


@dataclass(frozen=True, slots=True)
class SeamCache:
    objects: Mapping[str, SeamObject]
    valid: bool
    issue: str | None
    regex_pattern: str
    object_encodes: int


@dataclass(frozen=True, slots=True)
class SeamPackPlan:
    observation_ids: tuple[str, ...]
    token_count: int
    rejected_groups: int
    seam_encodes: int
    object_additions_evaluated: int
    final_full_encodes: int
    status: str
    accepted_group_indices: tuple[int, ...]
    rejected_group_indices: tuple[int, ...]


def build_seam_cache(context_cache, tokenizer) -> SeamCache:
    encoding = getattr(tokenizer, "encoding", None)
    pattern_text = getattr(encoding, "_pat_str", None)
    if not pattern_text:
        return SeamCache({}, False, "tokenizer exposes no frozen regex", "", 0)
    pattern = regex.compile(pattern_text)
    objects = {}
    encodes = 0
    for cached in context_cache.observations:
        text = cached.canonical_json
        matches = [match.group(0) for match in pattern.finditer(text)]
        if "".join(matches) != text:
            return SeamCache({}, False, f"regex does not fully partition {cached.observation_id}", pattern_text, encodes)
        if len(matches) < 2:
            return SeamCache({}, False, f"object has fewer than two regex chunks: {cached.observation_id}", pattern_text, encodes)
        first_tokens = len(tokenizer.encode(matches[0]))
        last_tokens = len(tokenizer.encode(matches[-1]))
        start = len(tokenizer.encode("[" + matches[0]))
        close = len(tokenizer.encode(matches[-1] + "]"))
        encodes += 4
        middle = cached.standalone_tokens - first_tokens - last_tokens
        if middle < 0:
            return SeamCache({}, False, f"cached standalone token count disagrees for {cached.observation_id}", pattern_text, encodes)
        objects[cached.observation_id] = SeamObject(
            cached.observation_id, matches[0], matches[-1], middle, start, close
        )
    return SeamCache(objects, True, None, pattern_text, encodes)


def plan_atomic_groups(
    seam_cache: SeamCache,
    groups: Sequence[Sequence[str]],
    tokenizer,
    *,
    token_budget: int,
    max_objects: int,
) -> SeamPackPlan:
    if not seam_cache.valid:
        return SeamPackPlan((), 0, 0, 0, 0, 0, "fallback_invalid_seam_cache", (), ())
    selected, seen = [], set()
    count = len(tokenizer.encode("[]")); seam_encodes = 1
    last: SeamObject | None = None
    rejected = evaluated = 0
    accepted_indices = []
    rejected_indices = []
    seam_memo: dict[tuple[str, str], int] = {}
    for group_index, group in enumerate(groups):
        additions = [value for value in group if value not in seen]
        if not additions:
            accepted_indices.append(group_index)
            continue
        if len(selected) + len(additions) > max_objects:
            rejected += 1; rejected_indices.append(group_index); continue
        trial_count, trial_last = count, last
        for observation_id in additions:
            item = seam_cache.objects.get(observation_id)
            if item is None:
                return SeamPackPlan(tuple(selected), count, rejected, seam_encodes, evaluated, 0,
                                    "fallback_missing_seam_object", tuple(accepted_indices),
                                    tuple(rejected_indices))
            if trial_last is None:
                trial_count = item.start_tokens + item.middle_tokens + item.close_tokens
            else:
                key = (trial_last.observation_id, item.observation_id)
                seam = seam_memo.get(key)
                if seam is None:
                    seam = len(tokenizer.encode(trial_last.suffix + "," + item.prefix))
                    seam_memo[key] = seam; seam_encodes += 1
                trial_count = trial_count - trial_last.close_tokens + seam + item.middle_tokens + item.close_tokens
            trial_last = item; evaluated += 1
        if trial_count > token_budget:
            rejected += 1; rejected_indices.append(group_index); continue
        selected.extend(additions); seen.update(additions)
        count, last = trial_count, trial_last
        accepted_indices.append(group_index)
    return SeamPackPlan(tuple(selected), count, rejected, seam_encodes, evaluated, 0,
                        "planned_seam_exact", tuple(accepted_indices),
                        tuple(rejected_indices))


__all__ = ["SeamCache", "SeamObject", "SeamPackPlan", "build_seam_cache", "plan_atomic_groups"]
