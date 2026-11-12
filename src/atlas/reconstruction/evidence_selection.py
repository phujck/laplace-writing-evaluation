"""GPU evidence controls and query-conditioned spectral source-column selection.

The selector operates inside one source-visible jurisdiction.  Scores are
observations and numerical heuristics, never truth certificates.  Exact metadata
constraints apply only through explicitly namespaced prepared columns.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
import time
from typing import Any, Mapping, Sequence

import torch

try:
    import triton
    import triton.language as tl
except ImportError:  # guarded fallback remains independently testable
    triton = None
    tl = None


_FUSED_VARIANTS: set[tuple[int, float, bool]] = set()


if triton is not None:
    @triton.jit
    def _fused_residual_pivot_kernel(
        residual_ptr,
        cost_ptr,
        forced_ptr,
        order_ptr,
        gain_ptr,
        valid_ptr,
        M,
        REQUESTED_STEPS,
        BLOCK: tl.constexpr,
        COST_POWER: tl.constexpr,
        USE_COST: tl.constexpr,
        EPS: tl.constexpr,
    ):
        index = tl.arange(0, BLOCK)
        rows = index[:, None]
        cols = index[None, :]
        matrix_mask = (rows < M) & (cols < M)
        residual = tl.load(
            residual_ptr + rows * M + cols, mask=matrix_mask, other=0.0)
        selected = tl.zeros((BLOCK,), tl.int1)
        costs = tl.load(cost_ptr + index, mask=index < M, other=1.0)
        step = 0
        while step < REQUESTED_STEPS:
            diagonal = tl.sum(tl.where(rows == cols, residual, 0.0), axis=0)
            norm_squared = tl.sum(residual * residual, axis=0)
            score = norm_squared / tl.maximum(diagonal, EPS)
            if USE_COST:
                score /= tl.exp(tl.log(tl.maximum(costs, 1.0)) * COST_POWER)
            eligible = (index < M) & (~selected) & (diagonal > EPS)
            score = tl.where(eligible, score, -float("inf"))
            automatic = tl.argmax(score, axis=0, tie_break_left=True)
            forced = tl.load(forced_ptr + step)
            pivot = tl.where(forced >= 0, forced, automatic)
            pivot_diagonal = tl.sum(tl.where(index == pivot, diagonal, 0.0), axis=0)
            pivot_selected = tl.sum(
                tl.where(index == pivot, selected.to(tl.int32), 0), axis=0) != 0
            automatic_valid = (forced < 0) & (pivot_diagonal > EPS) & (~pivot_selected)
            forced_valid = (forced >= 0) & (forced < M) & (~pivot_selected)
            output_valid = automatic_valid | forced_valid
            update_valid = output_valid & (pivot_diagonal > EPS)
            column = tl.sum(tl.where(cols == pivot, residual, 0.0), axis=1)
            raw_gain = tl.sum(column * column, axis=0) / tl.maximum(pivot_diagonal, EPS)
            correction = column[:, None] * column[None, :] / tl.maximum(pivot_diagonal, EPS)
            residual -= tl.where(update_valid, correction, 0.0)
            selected |= (index == pivot) & output_valid
            tl.store(order_ptr + step, pivot)
            tl.store(gain_ptr + step, tl.where(update_valid, raw_gain, 0.0))
            tl.store(valid_ptr + step, output_valid)
            step += 1
        tl.store(residual_ptr + rows * M + cols, residual, mask=matrix_mask)


@dataclass(frozen=True, slots=True)
class MetadataColumn:
    key: str
    values: tuple[str, ...]
    value_to_code: Mapping[str, int]
    codes: torch.Tensor


@dataclass(frozen=True, slots=True)
class PreparedSection:
    observation_ids: tuple[str, ...]
    metadata: Mapping[str, MetadataColumn]
    device: torch.device
    stored_bytes: int
    receipt: dict

    def mask(self, key: str, value: object) -> torch.Tensor | None:
        column = self.metadata.get(key)
        if column is None:
            return None
        code = column.value_to_code.get(str(value))
        if code is None:
            return torch.zeros(len(self.observation_ids), dtype=torch.bool, device=self.device)
        return column.codes == code


@dataclass(frozen=True, slots=True)
class SelectionConfig:
    name: str = "declared-default-v1"
    semantic_weight: float = 0.5
    query_power: float = 4.0
    cost_power: float = 1.0
    seed_per_obligation: int = 1

    def validate(self) -> "SelectionConfig":
        if not self.name or not 0 <= self.semantic_weight <= 1:
            raise ValueError("config requires a name and 0<=semantic_weight<=1")
        if self.query_power <= 0 or self.cost_power < 0 or self.seed_per_obligation < 0:
            raise ValueError("query_power>0, cost_power>=0 and seed_per_obligation>=0 required")
        return self


@dataclass(frozen=True, slots=True)
class _Scope:
    obligation_id: str
    facet_index: int
    mask: torch.Tensor
    constrained: bool
    usable: bool
    issue: str | None


def _get(value: object, key: str, default=None):
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _observation_id(value: object, index: int) -> str:
    for key in ("observation_id", "unit_id", "id", "passage_id"):
        found = _get(value, key)
        if found is not None:
            return str(found)
    return f"observation:{index}"


def _flatten_metadata(raw: Mapping[str, object]) -> dict[str, str]:
    out = {}
    for key, value in raw.items():
        if isinstance(value, Mapping):
            for field, item in value.items():
                out[f"{key}.{field}"] = str(item)
        elif "." in str(key):
            out[str(key)] = str(value)
        else:
            raise ValueError(
                "metadata must be explicitly namespaced, e.g. news.source or memory.role")
    return out


def prepare_section(
    observations: Sequence[object],
    *,
    device: str | torch.device = "cuda",
    metadata: Mapping[str, Sequence[object]] | None = None,
    observation_ids: Sequence[str] | None = None,
) -> PreparedSection:
    """Cache exact namespaced metadata codes once; source text is never parsed."""
    device = torch.device(device)
    if device.type != "cuda" or not torch.cuda.is_available():
        raise TypeError("prepared evidence sections require CUDA")
    if device.index is None:
        device = torch.device("cuda", torch.cuda.current_device())
    n = len(observations)
    ids = (tuple(str(value) for value in observation_ids) if observation_ids is not None
           else tuple(_observation_id(value, index) for index, value in enumerate(observations)))
    if len(ids) != n or len(set(ids)) != n or any(not value for value in ids):
        raise ValueError("observation IDs must align, be nonempty, and be unique")

    if metadata is None:
        flattened = []
        keys = set()
        for observation in observations:
            raw = _get(observation, "metadata", {})
            if not isinstance(raw, Mapping):
                raise TypeError("observation metadata must be a mapping")
            one = _flatten_metadata(raw)
            flattened.append(one); keys.update(one)
        metadata_rows = {key: tuple(row.get(key, "") for row in flattened) for key in sorted(keys)}
    else:
        metadata_rows = {str(key): tuple(str(value) for value in values)
                         for key, values in metadata.items()}
        if any("." not in key for key in metadata_rows):
            raise ValueError("every metadata key must have an authoritative namespace")
        if any(len(values) != n for values in metadata_rows.values()):
            raise ValueError("metadata columns must align with observations")

    columns = {}
    tensor_bytes = 0
    for key, rows in metadata_rows.items():
        values = tuple(sorted(set(rows)))
        value_to_code = {value: index for index, value in enumerate(values)}
        codes = torch.tensor([value_to_code[value] for value in rows],
                             dtype=torch.int64, device=device)
        tensor_bytes += codes.numel() * codes.element_size()
        columns[key] = MetadataColumn(key, values, value_to_code, codes)
    payload_bytes = sum(len(value.encode("utf-8")) for value in ids)
    payload_bytes += sum(len(key.encode("utf-8")) +
                         sum(len(value.encode("utf-8")) for value in column.values)
                         for key, column in columns.items())
    receipt = {
        "observations": n,
        "metadata_columns": sorted(columns),
        "gpu_code_bytes": tensor_bytes,
        "host_payload_bytes": payload_bytes,
        "stored_bytes": tensor_bytes + payload_bytes,
        "source_text_scans_per_query": 0,
        "namespace_rule": "only explicitly namespaced metadata is authoritative",
    }
    return PreparedSection(ids, columns, device, tensor_bytes + payload_bytes, receipt)


def _as_cuda_vector(value: torch.Tensor, n: int, name: str) -> torch.Tensor:
    if not isinstance(value, torch.Tensor) or not value.is_cuda:
        raise TypeError(f"{name} must be a CUDA tensor")
    if value.shape != (n,):
        raise ValueError(f"{name} must have shape [{n}]")
    return value.float()


def _feature_weights(dense: torch.Tensor, lexical: torch.Tensor | None,
                     config: SelectionConfig):
    semantic = dense.clamp_min(0)
    semantic = torch.where(semantic.max() > 0, semantic / semantic.max().clamp_min(1e-12),
                           torch.zeros_like(semantic))
    if lexical is None:
        return semantic, None, semantic
    observed = lexical.clamp_min(0)
    observed = torch.where(observed.max() > 0, observed / observed.max().clamp_min(1e-12),
                           torch.zeros_like(observed))
    flat = config.semantic_weight * semantic + (1.0 - config.semantic_weight) * observed
    return semantic, observed, flat


def _plan_parts(plan):
    return {
        "sources": tuple(_get(plan, "source_bindings", ()) or ()),
        "dates": tuple(_get(plan, "dates", ()) or ()),
        "context": tuple(_get(plan, "context_bindings", ()) or ()),
        "obligations": tuple(_get(plan, "evidence_obligations", ()) or ()),
        "identity": tuple(_get(plan, "identity", ()) or ()),
        "alternatives": tuple(_get(plan, "binding_alternatives", ()) or ()),
    }


def _reference_context(plan) -> list[dict]:
    if plan is None:
        return []
    retained = []
    for binding in _plan_parts(plan)["context"]:
        scope = str(_get(binding, "scope", "question"))
        role = str(_get(binding, "role", "reference"))
        if scope == "question" or role == "reference":
            retained.append({
                "id": str(_get(binding, "id", "")),
                "namespace": str(_get(binding, "namespace", "")),
                "field": str(_get(binding, "field", "")),
                "value": _get(binding, "value"),
                "role": role, "scope": scope,
                "applied_as_row_filter": False,
            })
    return retained


def _index_by_id(rows: Sequence[object]) -> dict[str, object]:
    return {str(_get(row, "id")): row for row in rows}


def _exact_mask(section: PreparedSection, key: str, value: object):
    mask = section.mask(key, value)
    if mask is None:
        return (torch.zeros(len(section.observation_ids), dtype=torch.bool, device=section.device),
                False, f"authoritative metadata column unavailable: {key}")
    if not bool(mask.any().item()):
        return mask, False, f"authoritative value unavailable: {key}={value}"
    return mask, True, None


def _compile_scopes(section: PreparedSection, plan) -> tuple[list[_Scope], torch.Tensor, list[str], bool]:
    n = len(section.observation_ids)
    all_rows = torch.ones(n, dtype=torch.bool, device=section.device)
    if plan is None:
        return [_Scope("unscoped", 0, all_rows, False, True, None)], all_rows, [], False
    parts = _plan_parts(plan)
    sources = _index_by_id(parts["sources"])
    dates = _index_by_id(parts["dates"])
    context = _index_by_id(parts["context"])
    issues: list[str] = []
    scopes: list[_Scope] = []
    authoritative_requested = False

    for facet_index, obligation in enumerate(parts["obligations"]):
        obligation_id = str(_get(obligation, "id", f"evidence:{facet_index}"))
        source_ids = tuple(_get(obligation, "source_binding_ids", ()) or ())
        date_ids = tuple(_get(obligation, "publication_date_ids", ()) or ())
        context_ids = tuple(_get(obligation, "context_binding_ids", ()) or ())
        # Several required sources are separate evidence scopes, not an empty
        # intersection of mutually exclusive source values.
        variants = source_ids or (None,)
        for source_id in variants:
            mask = all_rows.clone()
            constrained = False
            usable = True
            local_issues = []
            if source_id is not None:
                constrained = authoritative_requested = True
                binding = sources.get(str(source_id))
                if binding is None or _get(binding, "resolution") != "resolved":
                    mask.zero_(); usable = False
                    local_issues.append(f"unavailable requested news source binding: {source_id}")
                else:
                    one, ok, issue = _exact_mask(section, "news.source", _get(binding, "canonical"))
                    mask &= one; usable &= ok
                    if issue: local_issues.append(issue)
            for date_id in date_ids:
                constrained = authoritative_requested = True
                date = dates.get(str(date_id))
                if date is None or _get(date, "role") != "publication":
                    mask.zero_(); usable = False
                    local_issues.append(f"unresolved publication binding: {date_id}")
                else:
                    one, ok, issue = _exact_mask(section, "news.publication_date", _get(date, "iso_date"))
                    mask &= one; usable &= ok
                    if issue: local_issues.append(issue)
            for context_id in context_ids:
                binding = context.get(str(context_id))
                if binding is None:
                    constrained = authoritative_requested = True
                    mask.zero_(); usable = False
                    local_issues.append(f"unresolved context binding: {context_id}")
                    continue
                binding_scope = str(_get(binding, "scope", "question"))
                binding_role = str(_get(binding, "role", "reference"))
                if binding_scope == "question" or binding_role == "reference":
                    # Reference coordinates (notably question_date) orient the
                    # query but are not facts every source row must equal.
                    continue
                licensed_scope = binding_scope in {"source", "evidence", "jurisdiction"}
                licensed_role = binding_role in {"exact", "filter", "jurisdiction"}
                if not (licensed_scope and licensed_role):
                    local_issues.append(
                        f"unlicensed context filter retained without row masking: {context_id}")
                    continue
                constrained = authoritative_requested = True
                if _get(binding, "resolution") != "provided":
                    mask.zero_(); usable = False
                    local_issues.append(f"unresolved context binding: {context_id}")
                    continue
                key = f"{_get(binding, 'namespace')}.{_get(binding, 'field')}"
                one, ok, issue = _exact_mask(section, key, _get(binding, "value"))
                mask &= one; usable &= ok
                if issue: local_issues.append(issue)
            issue = "; ".join(local_issues) or None
            if issue: issues.append(f"{obligation_id}: {issue}")
            scopes.append(_Scope(obligation_id, facet_index, mask, constrained,
                                 usable and bool(mask.any().item()), issue))

    # Ambiguous one/other links restrict the section to the union of mentioned
    # sources but do not silently choose one assignment.
    if parts["alternatives"]:
        issues.append("ambiguous binding alternatives retained; no assignment certified")
        mentioned = set()
        for alternative in parts["alternatives"]:
            for assignment in (_get(alternative, "assignments", ()) or ()):
                for _, source_id in assignment:
                    mentioned.add(str(source_id))
        union = torch.zeros(n, dtype=torch.bool, device=section.device)
        authoritative_requested = True
        for source_id in sorted(mentioned):
            binding = sources.get(source_id)
            if binding is not None and _get(binding, "resolution") == "resolved":
                one, ok, issue = _exact_mask(section, "news.source", _get(binding, "canonical"))
                if ok: union |= one
                elif issue: issues.append(issue)
        scopes = [_Scope(scope.obligation_id, scope.facet_index, scope.mask & union,
                         True, scope.usable and bool((scope.mask & union).any().item()),
                         scope.issue) for scope in scopes]

    if not scopes:
        scopes = [_Scope("unscoped", 0, all_rows, False, True, None)]
    if authoritative_requested:
        allowed = torch.zeros(n, dtype=torch.bool, device=section.device)
        for scope in scopes:
            if scope.constrained and scope.usable:
                allowed |= scope.mask
    else:
        allowed = all_rows
    return scopes, allowed, list(dict.fromkeys(issues)), authoritative_requested


def _apply_shared_witnesses(
    section: PreparedSection,
    plan,
    scopes: list[_Scope],
    scope_values: torch.Tensor,
) -> tuple[list[_Scope], list[str], dict]:
    if plan is None:
        return scopes, [], {}
    parts = _plan_parts(plan)
    issues = []
    witnesses = {}
    for identity in parts["identity"]:
        relation = str(_get(identity, "relation", ""))
        members = set(str(value) for value in (_get(identity, "member_ids", ()) or ()))
        relevant = [index for index, scope in enumerate(scopes)
                    if not members or scope.obligation_id in members]
        if len(relevant) < 2:
            issues.append(
                f"identity link retained inside a compound obligation without witness certification: {relation}")
            continue
        if relation == "same_article":
            key = "news.article_id"
        elif relation == "same_entity":
            key = "binding.entity_id"
        else:
            issues.append(f"identity relation retained unresolved: {relation}")
            continue
        column = section.metadata.get(key)
        if column is None:
            issues.append(f"shared witness unresolved; missing authoritative {key}")
            continue
        article_count = len(column.values)
        per_scope = []
        for scope_index in relevant:
            facet_index = min(scopes[scope_index].facet_index, scope_values.shape[0] - 1)
            values = scope_values[facet_index].masked_fill(~scopes[scope_index].mask, -torch.inf)
            maxima = torch.full((article_count,), -torch.inf, device=section.device)
            maxima.scatter_reduce_(0, column.codes, values, reduce="amax", include_self=True)
            per_scope.append(maxima)
        table = torch.stack(per_scope)
        valid = (torch.isfinite(table) & (table > 0)).all(0)
        totals = torch.where(valid, table.sum(0), -torch.inf)
        if not bool(torch.isfinite(totals).any().item()):
            issues.append(f"no consistent witness satisfies {relation}")
            for scope_index in relevant:
                old = scopes[scope_index]
                scopes[scope_index] = _Scope(old.obligation_id, old.facet_index,
                                             torch.zeros_like(old.mask), True, False,
                                             f"no consistent {relation} witness")
            continue
        winner = torch.argmax(totals)
        witnesses[str(_get(identity, "witness_key", relation))] = {
            "metadata_key": key, "code": int(winner.item()), "verified": True}
        for scope_index in relevant:
            old = scopes[scope_index]
            mask = old.mask & (column.codes == winner)
            scopes[scope_index] = _Scope(old.obligation_id, old.facet_index, mask,
                                         True, bool(mask.any().item()), old.issue)
    return scopes, issues, witnesses


def _scope_matrix(scopes: Sequence[_Scope], values: torch.Tensor) -> torch.Tensor:
    rows = []
    for scope in scopes:
        row_index = min(scope.facet_index, values.shape[0] - 1)
        rows.append(values[row_index].masked_fill(~scope.mask, -torch.inf))
    return torch.stack(rows)


def _seed_rows(scopes: Sequence[_Scope], values: torch.Tensor, *,
               require_constrained: bool, per_obligation: int):
    eligible_scopes = [scope for scope in scopes
                       if scope.obligation_id != "unscoped"
                       and (scope.constrained or not require_constrained)]
    if not eligible_scopes:
        return torch.empty(0, dtype=torch.int64, device=values.device), []
    if per_obligation == 0:
        return torch.empty(0, dtype=torch.int64, device=values.device), []
    matrix = _scope_matrix(eligible_scopes, values)
    seed_k = min(per_obligation, matrix.shape[1])
    top_values, pivots = torch.topk(matrix, seed_k, dim=1)
    valid = torch.isfinite(top_values) & (top_values > 0)
    rows = pivots[valid].detach().cpu().tolist()
    obligations = []
    for scope, keep_row in zip(eligible_scopes, valid.detach().cpu().tolist()):
        obligations.extend([scope.obligation_id for keep in keep_row if keep])
    assignments = [{"row": row, "obligation_id": obligation}
                   for row, obligation in zip(rows, obligations)]
    seen = set(); ordered = []
    for row, obligation in zip(rows, obligations):
        if row not in seen:
            seen.add(row); ordered.append(row)
    return torch.tensor(ordered, dtype=torch.int64, device=values.device), assignments


def _deduplicate_ordered(values: torch.Tensor, limit: int) -> torch.Tensor:
    if values.numel() == 0:
        return values
    positions = torch.arange(values.numel(), device=values.device)
    earlier = (values[:, None] == values[None, :]) & (positions[None, :] < positions[:, None])
    return values[~earlier.any(1)][:limit]


def _candidate_rows(flat: torch.Tensor, allowed: torch.Tensor, seeds: torch.Tensor,
                    cap: int) -> torch.Tensor:
    if seeds.numel() > cap:
        raise MemoryError("candidate_cap cannot preserve all distinct scoped obligation seeds")
    finite = flat.masked_fill(~allowed, -torch.inf)
    top = torch.topk(finite, min(cap, flat.numel())).indices
    top = top[torch.isfinite(finite[top])]
    return _deduplicate_ordered(torch.cat((seeds, top)), cap)


def _rank_control(scores: torch.Tensor, allowed: torch.Tensor, k: int):
    masked = scores.masked_fill(~allowed, -torch.inf)
    values, rows = torch.topk(masked, min(k, scores.numel()))
    valid = torch.isfinite(values)
    return rows[valid], values[valid]


def _coverage_select(g: torch.Tensor, candidates: torch.Tensor, seeds: torch.Tensor,
                     k: int, costs: torch.Tensor | None, cost_power: float):
    if candidates.numel() == 0 or k == 0:
        return candidates[:0], []
    local_for_global = {int(row): index for index, row in enumerate(candidates.detach().cpu().tolist())}
    seed_local = [local_for_global[int(row)] for row in seeds.detach().cpu().tolist()
                  if int(row) in local_for_global]
    selected = torch.zeros(candidates.numel(), dtype=torch.bool, device=candidates.device)
    covered = torch.zeros(g.shape[0], dtype=torch.float32, device=candidates.device)
    order = []
    gains = []
    active_steps = []
    for local in seed_local:
        if len(order) >= k or local in order:
            continue
        order.append(local); selected[local] = True
        covered = torch.maximum(covered, g[:, local])
        gains.append(float("nan")); active_steps.append(True)
    for _ in range(max(0, k - len(order))):
        gain = (torch.maximum(covered[:, None], g) - covered[:, None]).sum(0)
        if costs is not None:
            gain = gain / costs[candidates].clamp_min(1).float().pow(cost_power)
        gain = gain.masked_fill(selected, -torch.inf)
        pivot = torch.argmax(gain)
        valid = torch.isfinite(gain[pivot]) & (gain[pivot] > 1e-12)
        selected[pivot] |= valid
        covered = torch.where(valid, torch.maximum(covered, g[:, pivot]), covered)
        order.append(pivot); gains.append(gain[pivot]); active_steps.append(valid)
    if not order:
        return candidates[:0], []
    order_tensor = torch.stack([value if isinstance(value, torch.Tensor)
                                else torch.tensor(value, device=candidates.device) for value in order])
    gain_tensor = torch.stack([value if isinstance(value, torch.Tensor)
                               else torch.tensor(value, device=candidates.device) for value in gains])
    active_tensor = torch.stack([
        value if isinstance(value, torch.Tensor)
        else torch.tensor(value, device=candidates.device, dtype=torch.bool)
        for value in active_steps])
    reported = gain_tensor[active_tensor].detach().cpu().tolist()
    reported = [None if math.isnan(value) else value for value in reported]
    return candidates[order_tensor[active_tensor]], reported


def _spectral_select_torch(embeddings: torch.Tensor, weights: torch.Tensor,
                           candidates: torch.Tensor, seeds: torch.Tensor, k: int,
                           costs: torch.Tensor | None, cost_power: float):
    if candidates.numel() == 0 or k == 0:
        return candidates[:0], {"initial_trace": 0.0, "final_trace": 0.0,
                                "pivot_gains": [], "pivot_steps": 0,
                                "estimated_gpu_kernel_launches": 0, "milliseconds": 0.0,
                                "candidate_rows": int(candidates.numel()),
                                "candidate_weight_sum": 0.0,
                                "positive_candidate_weights": 0,
                                "execution": "torch_reference_fallback",
                                "pivot_kernel_launches": 0,
                                "cold_build_seconds": 0.0}
    vectors = torch.nn.functional.normalize(embeddings[candidates].float(), dim=-1)
    kernel = ((1.0 + (vectors @ vectors.T).clamp(-1, 1)) / 2.0).square()
    root = weights[candidates].clamp_min(0).sqrt()
    residual = root[:, None] * kernel * root[None, :]
    initial_trace = torch.trace(residual)
    local_for_global = {int(row): index for index, row in enumerate(candidates.detach().cpu().tolist())}
    seed_local = [local_for_global[int(row)] for row in seeds.detach().cpu().tolist()
                  if int(row) in local_for_global]
    selected = torch.zeros(candidates.numel(), dtype=torch.bool, device=candidates.device)
    order = torch.full((k,), -1, dtype=torch.int64, device=candidates.device)
    valid = torch.zeros(k, dtype=torch.bool, device=candidates.device)
    pivot_gain = torch.zeros(k, dtype=torch.float32, device=candidates.device)
    start_event = torch.cuda.Event(enable_timing=True); stop_event = torch.cuda.Event(enable_timing=True)
    start_event.record()
    step = 0
    for local in seed_local:
        if step >= k:
            continue
        pivot = torch.tensor(local, dtype=torch.int64, device=candidates.device)
        diagonal = residual[pivot, pivot]
        column = residual[:, pivot].clone()
        gain = column.square().sum() / diagonal.clamp_min(1e-12)
        active = diagonal > 1e-12
        residual -= active * (column[:, None] * column[None, :]) / diagonal.clamp_min(1e-12)
        selected[pivot] = True; order[step] = pivot; valid[step] = True
        pivot_gain[step] = torch.where(active, gain, torch.zeros_like(gain)); step += 1
    for slot in range(step, k):
        diagonal = torch.diagonal(residual)
        gains = residual.square().sum(0) / diagonal.clamp_min(1e-12)
        if costs is not None:
            gains = gains / costs[candidates].clamp_min(1).float().pow(cost_power)
        gains = gains.masked_fill(selected | (diagonal <= 1e-12), -torch.inf)
        pivot = torch.argmax(gains)
        active = torch.isfinite(gains[pivot])
        column = residual[:, pivot].clone()
        raw_gain = column.square().sum() / diagonal[pivot].clamp_min(1e-12)
        residual -= active * (column[:, None] * column[None, :]) / diagonal[pivot].clamp_min(1e-12)
        selected[pivot] |= active; order[slot] = pivot; valid[slot] = active
        pivot_gain[slot] = torch.where(active, raw_gain, torch.zeros_like(raw_gain))
    stop_event.record(); stop_event.synchronize()
    chosen = candidates[order[valid]]
    return chosen, {
        "initial_trace": float(initial_trace.item()),
        "final_trace": float(torch.trace(residual).item()),
        "pivot_gains": pivot_gain[valid].detach().cpu().tolist(),
        "pivot_steps": int(valid.sum().item()),
        "pivot_iterations": k,
        "estimated_gpu_kernel_launches": k * 6,
        "milliseconds": float(start_event.elapsed_time(stop_event)),
        "candidate_kernel_shape": list(kernel.shape),
        "candidate_rows": int(candidates.numel()),
        "candidate_weight_sum": float(weights[candidates].sum().item()),
        "positive_candidate_weights": int((weights[candidates] > 0).sum().item()),
        "execution": "torch_reference_fallback",
        "pivot_kernel_launches": k,
        "cold_build_seconds": 0.0,
    }


@torch.no_grad()
def spectral_pivot_reference_float64(
    embeddings: torch.Tensor,
    weights: torch.Tensor,
    candidates: torch.Tensor,
    seeds: torch.Tensor,
    k: int,
    costs: torch.Tensor | None = None,
    cost_power: float = 1.0,
) -> dict:
    """Independent tiny-fixture oracle; never used by the production selector."""
    vectors = torch.nn.functional.normalize(embeddings.detach().cpu().double(), dim=-1)
    candidate_rows = candidates.detach().cpu().long()
    local_weights = weights.detach().cpu().double()[candidate_rows].clamp_min(0)
    kernel = ((1.0 + (vectors[candidate_rows] @ vectors[candidate_rows].T).clamp(-1, 1)) / 2).square()
    root = local_weights.sqrt()
    residual = root[:, None] * kernel * root[None, :]
    initial_trace = float(torch.trace(residual))
    local_for_global = {int(row): index for index, row in enumerate(candidate_rows.tolist())}
    forced = [local_for_global[int(row)] for row in seeds.detach().cpu().tolist()
              if int(row) in local_for_global]
    local_costs = (None if costs is None
                   else costs.detach().cpu().double()[candidate_rows].clamp_min(1).pow(cost_power))
    selected = torch.zeros(candidate_rows.numel(), dtype=torch.bool)
    order = []
    gains = []
    for local in forced:
        if len(order) >= min(k, candidate_rows.numel()) or selected[local]:
            continue
        diagonal = residual[local, local]
        column = residual[:, local].clone()
        gain = column.square().sum() / diagonal.clamp_min(1e-15)
        active = bool((diagonal > 1e-15).item())
        if active:
            residual -= column[:, None] * column[None, :] / diagonal
        selected[local] = True; order.append(local)
        gains.append(float(gain) if active else 0.0)
    while len(order) < min(k, candidate_rows.numel()):
        diagonal = torch.diagonal(residual)
        score = residual.square().sum(0) / diagonal.clamp_min(1e-15)
        if local_costs is not None:
            score /= local_costs
        score[selected | (diagonal <= 1e-15)] = -torch.inf
        pivot = int(torch.argmax(score))
        if not torch.isfinite(score[pivot]):
            break
        column = residual[:, pivot].clone()
        raw_gain = column.square().sum() / diagonal[pivot]
        residual -= column[:, None] * column[None, :] / diagonal[pivot]
        selected[pivot] = True; order.append(pivot); gains.append(float(raw_gain))
    return {
        "indices": candidate_rows[torch.tensor(order, dtype=torch.int64)],
        "pivot_gains": gains,
        "initial_trace": initial_trace,
        "final_trace": float(torch.trace(residual)),
        "kernel_min_eigenvalue": float(torch.linalg.eigvalsh(kernel).min()),
        "execution": "torch_cpu_float64_independent_oracle",
    }


def _spectral_select(embeddings: torch.Tensor, weights: torch.Tensor,
                     candidates: torch.Tensor, seeds: torch.Tensor, k: int,
                     costs: torch.Tensor | None, cost_power: float):
    """Use one fused Triton pivot launch; retain Torch as guarded oracle/fallback."""
    steps = min(k, int(candidates.numel()))
    if candidates.numel() == 0 or steps == 0:
        return _spectral_select_torch(
            embeddings, weights, candidates, seeds, k, costs, cost_power)
    block = triton.next_power_of_2(int(candidates.numel())) if triton is not None else 0
    # Retrieval@50/8k uses k=50.  Keep that exact recurrence fused; only larger
    # experimental ranks fall back to the independently tested Torch path.
    supported = triton is not None and block <= 128 and steps <= 64
    if not supported:
        return _spectral_select_torch(
            embeddings, weights, candidates, seeds, k, costs, cost_power)

    vectors = torch.nn.functional.normalize(embeddings[candidates].float(), dim=-1)
    kernel = ((1.0 + (vectors @ vectors.T).clamp(-1, 1)) / 2.0).square()
    root = weights[candidates].clamp_min(0).sqrt()
    residual = (root[:, None] * kernel * root[None, :]).contiguous()
    initial_trace = torch.trace(residual)
    local_for_global = {int(row): index for index, row in enumerate(candidates.detach().cpu().tolist())}
    seed_local = [local_for_global[int(row)] for row in seeds.detach().cpu().tolist()
                  if int(row) in local_for_global][:steps]
    compiled_steps = 64
    forced = torch.full((compiled_steps,), -1, dtype=torch.int64, device=candidates.device)
    if seed_local:
        forced[:len(seed_local)] = torch.tensor(seed_local, dtype=torch.int64,
                                                device=candidates.device)
    order = torch.empty(compiled_steps, dtype=torch.int64, device=candidates.device)
    gains = torch.empty(compiled_steps, dtype=torch.float32, device=candidates.device)
    valid = torch.empty(compiled_steps, dtype=torch.bool, device=candidates.device)
    local_costs = (costs[candidates].float().contiguous() if costs is not None
                   else torch.ones(candidates.numel(), dtype=torch.float32,
                                   device=candidates.device))
    variant = (block, float(cost_power if costs is not None else 0.0), costs is not None)
    cold = variant not in _FUSED_VARIANTS
    event_start = torch.cuda.Event(enable_timing=True)
    event_stop = torch.cuda.Event(enable_timing=True)
    wall_start = time.perf_counter()
    event_start.record()
    _fused_residual_pivot_kernel[(1,)](
        residual, local_costs, forced, order, gains, valid,
        M=int(candidates.numel()), REQUESTED_STEPS=steps,
        BLOCK=block,
        COST_POWER=float(cost_power), USE_COST=costs is not None,
        EPS=1e-12, num_warps=8 if block >= 128 else 4,
    )
    event_stop.record(); event_stop.synchronize()
    wall_seconds = time.perf_counter() - wall_start
    _FUSED_VARIANTS.add(variant)
    requested_valid = valid[:steps]
    chosen = candidates[order[:steps][requested_valid]]
    return chosen, {
        "initial_trace": float(initial_trace.item()),
        "final_trace": float(torch.trace(residual).item()),
        "pivot_gains": gains[:steps][requested_valid].detach().cpu().tolist(),
        "pivot_steps": int(requested_valid.sum().item()),
        "pivot_iterations": steps,
        "estimated_gpu_kernel_launches": 1,
        "pivot_kernel_launches": 1,
        "milliseconds": float(event_start.elapsed_time(event_stop)),
        "candidate_kernel_shape": list(kernel.shape),
        "candidate_rows": int(candidates.numel()),
        "candidate_weight_sum": float(weights[candidates].sum().item()),
        "positive_candidate_weights": int((weights[candidates] > 0).sum().item()),
        "execution": "triton_fused_one_launch",
        "cold_build_seconds": wall_seconds if cold else 0.0,
        "warm_call_wall_seconds": 0.0 if cold else wall_seconds,
        "compiled_variant_count": len(_FUSED_VARIANTS),
        "variant": {"candidate_rows_runtime": int(candidates.numel()), "block": block,
                    "requested_steps_runtime": steps, "loop_capacity": compiled_steps,
                    "loop_execution": "runtime_while",
                    "use_cost": costs is not None,
                    "cost_power": float(cost_power if costs is not None else 0.0)},
    }


@torch.no_grad()
def select_evidence(
    observations,
    query,
    dense_scores,
    lexical_scores=None,
    *,
    k=20,
    method="skein",
    facet_scores=None,
    plan=None,
    embeddings=None,
    token_costs=None,
    candidate_cap=96,
    config=None,
):
    """Select local observation rows in selection order on CUDA."""
    methods = {"dense", "lexical", "hybrid", "coverage", "skein"}
    if method not in methods:
        raise ValueError(f"method must be one of {sorted(methods)}")
    if k < 0 or candidate_cap <= 0 or candidate_cap > 128:
        raise ValueError("require k>=0 and 1<=candidate_cap<=128")
    if config is None:
        config = SelectionConfig()
    elif isinstance(config, Mapping):
        config = SelectionConfig(**config)
    if not isinstance(config, SelectionConfig):
        raise TypeError("config must be SelectionConfig or a compatible mapping")
    config = config.validate()
    if isinstance(observations, PreparedSection):
        section = observations; prepared_here = False
    else:
        if not isinstance(dense_scores, torch.Tensor):
            raise TypeError("dense_scores must establish the CUDA device")
        section = prepare_section(observations, device=dense_scores.device); prepared_here = True
    n = len(section.observation_ids)
    dense = _as_cuda_vector(dense_scores, n, "dense_scores")
    lexical = None if lexical_scores is None else _as_cuda_vector(lexical_scores, n, "lexical_scores")
    if dense.device != section.device or (lexical is not None and lexical.device != section.device):
        raise ValueError("scores and prepared section must share one CUDA device")
    if token_costs is not None:
        costs = _as_cuda_vector(token_costs, n, "token_costs")
        if bool((costs <= 0).any().item()):
            raise ValueError("token_costs must be positive")
    else:
        costs = None
    if facet_scores is not None:
        if not isinstance(facet_scores, torch.Tensor) or not facet_scores.is_cuda:
            raise TypeError("facet_scores must be a CUDA tensor")
        if facet_scores.ndim != 2 or facet_scores.shape[1] != n:
            raise ValueError("facet_scores must have shape [facets, observations]")
        facets = facet_scores.float().clamp(0, 1)
    else:
        facets = None

    started = time.perf_counter()
    compute_start = torch.cuda.Event(enable_timing=True)
    compute_stop = torch.cuda.Event(enable_timing=True)
    compute_start.record()
    semantic_weight, lexical_weight, flat = _feature_weights(dense, lexical, config)
    spectral_weight = flat.pow(config.query_power)
    scopes, allowed, issues, authoritative = _compile_scopes(section, plan)
    if facets is None:
        scope_values = flat[None, :].expand(len(scopes), -1)
    else:
        if facets.shape[0] < max(scope.facet_index for scope in scopes) + 1:
            raise ValueError("facet_scores omits a planned evidence obligation")
        scope_values = facets
    scopes, witness_issues, witnesses = _apply_shared_witnesses(
        section, plan, scopes, scope_values)
    issues.extend(witness_issues)
    if authoritative:
        allowed = torch.zeros(n, dtype=torch.bool, device=section.device)
        for scope in scopes:
            if scope.constrained and scope.usable:
                allowed |= scope.mask
    seed_values = facets if facets is not None else flat[None, :]
    seeds, seed_assignments = _seed_rows(
        scopes, seed_values, require_constrained=(method == "skein"),
        per_obligation=config.seed_per_obligation)
    requested = min(int(k), n)
    if seeds.numel() > requested:
        issues.append(
            f"k={requested} cannot preserve all {seeds.numel()} distinct scoped obligation seeds")

    spectral_work = {}
    coverage_gains = []
    if method == "dense":
        indices, scores = _rank_control(semantic_weight, allowed, requested)
    elif method == "lexical":
        if lexical is None:
            raise ValueError("lexical method requires lexical_scores")
        indices, scores = _rank_control(lexical_weight, allowed & (lexical_weight > 0), requested)
    elif method == "hybrid":
        if lexical is None:
            raise ValueError("hybrid method requires lexical_scores")
        indices, scores = _rank_control(flat, allowed & (flat > 0), requested)
    else:
        candidates = _candidate_rows(flat, allowed, seeds, min(candidate_cap, n))
        if method == "coverage":
            coverage = facets[:, candidates] if facets is not None else flat[candidates][None, :]
            coverage = coverage.clamp(0, 1)
            indices, coverage_gains = _coverage_select(
                coverage, candidates, seeds, requested, costs, config.cost_power)
        else:
            if embeddings is None or not isinstance(embeddings, torch.Tensor) or not embeddings.is_cuda:
                raise TypeError("skein method requires CUDA embeddings")
            if embeddings.ndim != 2 or embeddings.shape[0] != n or embeddings.device != section.device:
                raise ValueError("embeddings must have shape [observations, dimension] on the section device")
            indices, spectral_work = _spectral_select(
                embeddings, spectral_weight, candidates, seeds, requested, costs,
                config.cost_power)
        scores = flat[indices]

    unresolved = bool(issues) or bool(_get(plan, "binding_alternatives", ()) if plan is not None else False)
    if authoritative and not bool(allowed.any().item()):
        status = "unsupported_constraints"
    elif unresolved:
        status = "selected_with_unresolved_constraints"
    elif method in {"skein", "coverage"} and indices.numel() == 0:
        status = "zero_demand"
    else:
        status = "selected"
    selected_cost = None if costs is None else float(costs[indices].sum().item())
    compute_stop.record(); compute_stop.synchronize()
    compute_milliseconds = float(compute_start.elapsed_time(compute_stop))
    query_digest = sha256(str(query).encode("utf-8")).hexdigest()
    work = {
        "method": method, "query_sha256": query_digest,
        "selection_config": {
            "name": config.name, "semantic_weight": config.semantic_weight,
            "query_power": config.query_power, "cost_power": config.cost_power,
            "seed_per_obligation": config.seed_per_obligation,
            "status": "declared heuristic; not theory-derived semantic truth",
        },
        "observations": n, "selected": indices.numel(),
        "candidate_cap": candidate_cap, "prepared_here": prepared_here,
        "metadata": section.receipt, "source_text_rows_scanned_per_query": 0,
        "authoritative_scope_requested": authoritative,
        "allowed_rows": int(allowed.sum().item()),
        "seed_rows": seeds.detach().cpu().tolist(),
        "seed_obligations": [item["obligation_id"] for item in seed_assignments],
        "seed_assignments": seed_assignments,
        "constraint_issues": list(dict.fromkeys(issues)),
        "binding_witnesses": witnesses,
        "reference_context": _reference_context(plan),
        "coverage_gains": coverage_gains,
        "selected_declared_token_cost": selected_cost,
        "token_cost_policy": ("gain_per_declared_cost" if costs is not None else "cardinality"),
        "spectral": spectral_work,
        "candidate_relative": method == "skein",
        "global_query_weight_sum": (float(spectral_weight.sum().item())
                                    if method == "skein" else None),
        "binding_section_fixed": not unresolved,
        "coverage_guarantee": (
            "fixed-binding cardinality objective only"
            if method == "coverage" and not unresolved and costs is None
            else "none"),
        "global_pivot_optimality_claim": False,
        "semantic_certificate": False,
        "complete_linked_evidence_certificate": False,
        "compute_stage_milliseconds": compute_milliseconds,
        "seconds": time.perf_counter() - started,
    }
    return {"indices": indices.to(torch.int64), "scores": scores, "work": work, "status": status}


__all__ = [
    "MetadataColumn", "PreparedSection", "SelectionConfig", "prepare_section",
    "select_evidence", "spectral_pivot_reference_float64"
]
