"""Exact whole-JSON packing with mandatory atomic witness groups first."""
from __future__ import annotations

from dataclasses import dataclass

from . import context_budget
from .context_budget import ContextCache
from . import memory_packing


@dataclass(frozen=True, slots=True)
class MandatoryPackResult:
    status: str
    observation_ids: tuple[str, ...]
    public_items: tuple[dict, ...]
    canonical_json: str
    token_count: int
    mandatory_group_ids: tuple[str, ...]
    optional_group_ids: tuple[str, ...]
    rejected_optional_group_ids: tuple[str, ...]
    receipt: dict


def _render(cache: ContextCache, observation_ids):
    return "[" + ",".join(cache.by_id[value].canonical_json for value in observation_ids) + "]"


def pack_witness_groups(
    cache: ContextCache,
    readout: dict,
    tokenizer,
    *,
    token_budget: int,
    max_objects: int,
    seam_cache=None,
) -> MandatoryPackResult:
    if token_budget <= 0 or max_objects <= 0:
        raise ValueError("token_budget and max_objects must be positive")
    mandatory = list(readout.get("mandatory_groups", ()))
    sequence = list(readout.get("group_sequence", ()))
    mandatory_ids = {row["group_id"] for row in mandatory}
    sequence_group_ids = tuple(dict.fromkeys(
        group["group_id"] for group in sequence))
    selected = []
    selected_set = set()
    for group in mandatory:
        observation_ids = group.get("observation_ids")
        if observation_ids is None:
            observation_ids = tuple(cache.observations[row].observation_id
                                    for row in group["indices"])
        for observation_id in observation_ids:
            if observation_id not in selected_set:
                selected.append(observation_id); selected_set.add(observation_id)
    empty_json = "[]"
    if seam_cache is not None:
        mandatory_sequences = [tuple(group.get("observation_ids") or
                               tuple(cache.observations[row].observation_id
                                     for row in group["indices"]))
                               for group in mandatory]
        mandatory_union = tuple(dict.fromkeys(
            value for group in mandatory_sequences for value in group))
        mandatory_plan = memory_packing.plan_atomic_groups(
            seam_cache, mandatory_sequences, tokenizer,
            token_budget=token_budget, max_objects=max_objects)
        if (not mandatory_plan.status.startswith("planned_")
                or mandatory_plan.accepted_group_indices != tuple(range(len(mandatory_sequences)))):
            required_json = _render(cache, mandatory_union)
            required_tokens = len(tokenizer.encode(required_json))
            empty_tokens = len(tokenizer.encode(empty_json))
            return MandatoryPackResult(
                "budget_infeasible", (), (), empty_json, empty_tokens,
                tuple(group["group_id"] for group in mandatory), (), (), {
                    "exact_encode_calls": 2,
                    "mandatory_required_observation_ids": mandatory_union,
                    "mandatory_required_tokens": required_tokens,
                    "token_budget": token_budget, "max_objects": max_objects,
                    "reason": "mandatory atomic witness union exceeds budget; safe empty prompt emitted",
                    "seam_status": mandatory_plan.status,
                    "accepted_group_ids": (),
                    "rejected_group_ids": sequence_group_ids,
                })
        sequence_groups = []
        unique_groups = []
        seen_group_ids = set()
        for group in sequence:
            group_id = group["group_id"]
            if group_id in seen_group_ids:
                continue
            seen_group_ids.add(group_id)
            unique_groups.append(group)
            sequence_groups.append(tuple(group.get("observation_ids") or
                                   tuple(cache.observations[row].observation_id
                                         for row in group["indices"])))
        plan = memory_packing.plan_atomic_groups(
            seam_cache, sequence_groups, tokenizer,
            token_budget=token_budget, max_objects=max_objects)
        if not plan.status.startswith("planned_"):
            # Independently verified seam invariant failed: use the exact
            # reference path rather than accepting an approximate count.
            seam_cache = None
        else:
            selected = list(plan.observation_ids)
            rendered = _render(cache, selected)
            final_tokens = len(tokenizer.encode(rendered))
            if final_tokens != plan.token_count:
                seam_cache = None
            else:
                selected_set = set(selected)
                accepted_set = set(plan.accepted_group_indices)
                rejected_set = set(plan.rejected_group_indices)
                optional_ids = []
                rejected = []
                for group_index, (group, ids) in enumerate(zip(unique_groups, sequence_groups)):
                    if group["group_id"] in mandatory_ids:
                        continue
                    if group_index in accepted_set:
                        optional_ids.append(group["group_id"])
                    elif group_index in rejected_set:
                        rejected.append(group["group_id"])
                return MandatoryPackResult(
                    "packed", tuple(selected),
                    tuple(dict(cache.by_id[value].public) for value in selected),
                    rendered, final_tokens,
                    tuple(group["group_id"] for group in mandatory),
                    tuple(dict.fromkeys(optional_ids)), tuple(dict.fromkeys(rejected)), {
                        "exact_encode_calls": 1,
                        "seam_encodes": plan.seam_encodes,
                        "object_additions_evaluated": plan.object_additions_evaluated,
                        "mandatory_rows": len(mandatory_union),
                        "packed_rows": len(selected), "token_budget": token_budget,
                        "max_objects": max_objects,
                        "cost_role": "feasibility only; ranking unchanged",
                        "seam_status": plan.status,
                        "accepted_group_ids": tuple(
                            unique_groups[index]["group_id"]
                            for index in plan.accepted_group_indices),
                        "rejected_group_ids": tuple(
                            unique_groups[index]["group_id"]
                            for index in plan.rejected_group_indices),
                    })

    exact_calls = 1
    rendered = _render(cache, selected)
    tokens = len(tokenizer.encode(rendered))
    if len(selected) > max_objects or tokens > token_budget:
        return MandatoryPackResult(
            "budget_infeasible", (), (), empty_json,
            len(tokenizer.encode(empty_json)), tuple(group["group_id"] for group in mandatory),
            (), (), {
                "exact_encode_calls": exact_calls + 1,
                "mandatory_required_observation_ids": tuple(selected),
                "mandatory_required_tokens": tokens,
                "mandatory_rows": len(selected), "token_budget": token_budget,
                "max_objects": max_objects,
                "reason": "mandatory atomic witness union exceeds budget; safe empty prompt emitted",
                "accepted_group_ids": (),
                "rejected_group_ids": sequence_group_ids,
            })
    optional_ids = []
    rejected = []
    for group in sequence:
        group_id = group["group_id"]
        if group_id in mandatory_ids or group_id in optional_ids:
            continue
        additions = []
        observation_ids = group.get("observation_ids")
        if observation_ids is None:
            observation_ids = tuple(cache.observations[row].observation_id
                                    for row in group["indices"])
        for observation_id in observation_ids:
            if observation_id not in selected_set and observation_id not in additions:
                additions.append(observation_id)
        trial = [*selected, *additions]
        if len(trial) > max_objects:
            rejected.append(group_id); continue
        trial_rendered = _render(cache, trial)
        exact_calls += 1
        trial_tokens = len(tokenizer.encode(trial_rendered))
        if trial_tokens > token_budget:
            rejected.append(group_id); continue
        selected = trial; selected_set.update(additions)
        rendered, tokens = trial_rendered, trial_tokens
        optional_ids.append(group_id)
    final_tokens = len(tokenizer.encode(rendered)); exact_calls += 1
    if final_tokens != tokens or final_tokens > token_budget or len(selected) > max_objects:
        raise AssertionError("mandatory pack final exact verification failed")
    return MandatoryPackResult(
        "packed", tuple(selected),
        tuple(dict(cache.by_id[value].public) for value in selected),
        rendered, final_tokens, tuple(group["group_id"] for group in mandatory),
        tuple(optional_ids), tuple(rejected), {
            "exact_encode_calls": exact_calls,
            "mandatory_rows": sum(len(group["indices"]) for group in mandatory),
            "packed_rows": len(selected), "token_budget": token_budget,
            "max_objects": max_objects,
            "cost_role": "feasibility only; ranking unchanged",
            "accepted_group_ids": tuple(dict.fromkeys(
                [group["group_id"] for group in mandatory] + optional_ids)),
            "rejected_group_ids": tuple(dict.fromkeys(rejected)),
        })


__all__ = ["MandatoryPackResult", "pack_witness_groups"]
