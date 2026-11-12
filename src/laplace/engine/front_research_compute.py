"""Pure read model for the Aisthesis Research / Compute work surface.

This is deliberately a projection boundary, not a new research service.  It joins
already-materialised Atlas query/descent evidence, campaign/run evidence and comparable
result rows into three job-specific representations:

* a query-to-evidence path with accepted, rejected and unvisited regions;
* an experiment matrix whose cells carry the exact run altitude and observed measures; and
* a result-comparison field over only the metrics actually supplied by the producer.

Nothing in this module queries a network, opens Atlas, starts a run, writes a row or guesses a
missing producer.  Missing joins remain typed ``UNKNOWN`` omissions with continuations.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA = "laplace.aisthesis-research-compute/1"
QUERY_SCHEMA = "laplace.aisthesis-query-evidence-path/1"
MATRIX_SCHEMA = "laplace.aisthesis-experiment-matrix/1"
COMPARISON_SCHEMA = "laplace.aisthesis-result-comparison/1"

_EVIDENCE_STATES = frozenset({"COMPLETE", "IN_FLIGHT", "STALE", "UNKNOWN", "REFUSED"})
_CURRENTNESS_STATES = frozenset({"CURRENT", "STALE", "LAST-TRUSTED", "UNKNOWN", "REFUSED"})
_REGION_CLASSES = frozenset({"ACCEPTED", "REJECTED", "UNVISITED"})
_FOG_CLASSES = frozenset(
    {
        "COVERAGE",
        "DISCOVERY_MISS",
        "BOUNDARY_RESIDUAL",
        "STALE_UNKNOWN",
        "BUDGET_TRUNCATION",
        "AXIS_DISAGREEMENT",
    }
)
_RUN_PHASES = (
    "QUESTION_FROZEN",
    "ARMED",
    "RUNNING",
    "METERED",
    "BLIND_GRADING",
    "SEALED",
)


def _canon(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def _handle(kind: str, value: Any) -> str:
    return f"{kind}:sha256:{hashlib.sha256(_canon(value)).hexdigest()}"


def _words(value: Any, *, fallback: str = "") -> str:
    text = " ".join(str(value or "").split())
    return text or fallback


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _evidence_state(value: Any, *, default_reason: str) -> tuple[str, str]:
    if value is None:
        return "UNKNOWN", default_reason
    if not isinstance(value, Mapping):
        return "REFUSED", "producer returned a malformed non-object value"
    if value.get("error") or value.get("ok") is False:
        return "REFUSED", _words(value.get("error") or value.get("reason"), fallback="producer refused")
    stated = _words(value.get("state") or value.get("status")).upper()
    if stated:
        if stated not in _EVIDENCE_STATES:
            return "REFUSED", f"producer supplied unsupported state {stated!r}"
        return stated, _words(value.get("reason"), fallback="state supplied by the joined producer")
    if not value:
        return "UNKNOWN", default_reason
    return "COMPLETE", _words(value.get("reason"), fallback="joined from supplied read evidence")


def _currentness(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {
            "status": "UNKNOWN",
            "reason": "no source-currentness face has been joined",
            "source": {},
            "observation_time": "",
        }
    if not isinstance(value, Mapping):
        return {
            "status": "REFUSED",
            "reason": "source-currentness producer returned a malformed non-object value",
            "source": {},
            "observation_time": "",
        }
    status = _words(value.get("status") or value.get("state"), fallback="UNKNOWN").upper()
    if status not in _CURRENTNESS_STATES:
        return {
            "status": "REFUSED",
            "reason": f"unsupported source-currentness state {status!r}",
            "source": {},
            "observation_time": "",
        }
    source = value.get("source") if isinstance(value.get("source"), Mapping) else {}
    return {
        "status": status,
        "reason": _words(value.get("reason"), fallback="source-currentness producer supplied no explanation"),
        "source": dict(source),
        "observation_time": _words(value.get("observation_time")),
    }


def _omission(
    ident: str,
    label: str,
    *,
    cause: str,
    continuation: str,
    count: int = 1,
    members: Sequence[str] = (),
) -> dict[str, Any]:
    ordered = [str(item) for item in members]
    return {
        "id": ident,
        "semantic_anchor": f"research:omission:{ident}",
        "label": label,
        "cause": cause,
        "count": int(count),
        "ordered_members": ordered,
        "member_digest": _handle("research-omission-members", ordered),
        "continuation": continuation,
    }


def _query_path(query: str, evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    evidence_state, evidence_reason = _evidence_state(
        evidence, default_reason="no Atlas routing or typed-descent receipt has been joined"
    )
    data = evidence if isinstance(evidence, Mapping) else {}
    query_text = _words(query or data.get("query"))
    query_state = "COMPLETE" if query_text else "UNKNOWN"
    planner = data.get("planner") if isinstance(data.get("planner"), Mapping) else {}
    declared = {
        key: planner[key]
        for key in (
            "goal",
            "assumption",
            "fibre",
            "grade",
            "altitude",
            "budget",
            "beam",
            "retained_rank",
            "boundary",
            "reopening",
            "search",
        )
        if key in planner
    }

    stage_specs = (
        ("question", "Question", query_state, "the human query that conditions the read"),
        ("routing", "Atlas routing", None, "candidate reach is evidence, never authority"),
        ("descent", "Typed descent", None, "materialise only the bounded regions actually traversed"),
        ("evidence", "Evidence quarry", None, "admitted source-bearing objects and exact residuals"),
    )
    stages: list[dict[str, Any]] = []
    for order, (ident, label, fixed_state, fallback_reason) in enumerate(stage_specs):
        joined = data.get(ident) if ident != "question" else None
        if fixed_state is None:
            stage_state, stage_reason = _evidence_state(joined, default_reason=fallback_reason)
        else:
            stage_state = fixed_state
            stage_reason = query_text and fallback_reason or "no query was supplied"
        stage_value = joined if isinstance(joined, Mapping) else {}
        stages.append(
            {
                "id": ident,
                "semantic_anchor": f"research:query-stage:{ident}",
                "label": label,
                "state": stage_state,
                "reason": _words(stage_value.get("reason"), fallback=stage_reason),
                "order": order,
                "count": stage_value.get("count"),
                "latency_ms": stage_value.get("latency_ms"),
                "continuation": _words(stage_value.get("continuation")),
            }
        )

    regions: list[dict[str, Any]] = []
    region_refusal = ""
    seen_region_ids: set[str] = set()
    for index, row in enumerate(_sequence(data.get("regions"))):
        if not isinstance(row, Mapping):
            region_refusal = "query regions contain a malformed non-object row"
            break
        ident = _words(row.get("id"), fallback=f"region-{index + 1}")
        if ident in seen_region_ids:
            region_refusal = f"query regions contain duplicate id {ident!r}"
            break
        seen_region_ids.add(ident)
        region_class = _words(row.get("class") or row.get("disposition"), fallback="UNVISITED").upper()
        if region_class not in _REGION_CLASSES:
            region_refusal = f"query region {ident!r} has unsupported class {region_class!r}"
            break
        state, reason = _evidence_state(row, default_reason="region has no typed evidence")
        regions.append(
            {
                "id": ident,
                "semantic_anchor": f"research:query-region:{ident}",
                "label": _words(row.get("label"), fallback=ident.replace("-", " ").title()),
                "class": region_class,
                "state": state,
                "reason": reason,
                "source_class": _words(row.get("source_class"), fallback="UNKNOWN"),
                "count": int(row.get("count") or 0),
                "score": row.get("score"),
                "depth": row.get("depth"),
                "bytes": row.get("bytes"),
                "continuation": _words(row.get("continuation")),
                "order": index,
            }
        )

    fog: list[dict[str, Any]] = []
    fog_refusal = ""
    for index, row in enumerate(_sequence(data.get("fog"))):
        if not isinstance(row, Mapping):
            fog_refusal = "fog rows contain a malformed non-object value"
            break
        cause = _words(row.get("cause"), fallback="STALE_UNKNOWN").upper().replace("/", "_")
        if cause not in _FOG_CLASSES:
            fog_refusal = f"fog row {index + 1} has unsupported typed cause {cause!r}"
            break
        ident = _words(row.get("id"), fallback=f"fog-{index + 1}")
        members = [str(item) for item in _sequence(row.get("members"))]
        count = int(row.get("count") or len(members) or 1)
        fog.append(
            {
                "id": ident,
                "semantic_anchor": f"research:fog:{ident}",
                "label": _words(row.get("label"), fallback=cause.replace("_", " ").title()),
                "cause": cause,
                "count": count,
                "ordered_members": members,
                "member_digest": _handle("research-fog-members", members),
                "continuation": _words(row.get("continuation")),
                "reason": _words(row.get("reason"), fallback="producer supplied a typed unresolved region"),
            }
        )

    omissions: list[dict[str, Any]] = []
    if not query_text:
        omissions.append(
            _omission(
                "query-absent",
                "No research question is selected",
                cause="UNKNOWN",
                continuation="research://select-query",
            )
        )
    if not regions:
        omissions.append(
            _omission(
                "regions-unavailable",
                "Accepted, rejected and unvisited regions are not available",
                cause="REFUSED" if region_refusal else evidence_state,
                continuation=_words(data.get("continuation"), fallback="atlas://query/descent"),
            )
        )
    if not fog:
        omissions.append(
            _omission(
                "fog-unavailable",
                "The producer supplied no typed fog map",
                cause="REFUSED" if fog_refusal else "UNKNOWN",
                continuation=_words(data.get("continuation"), fallback="atlas://query/descent"),
            )
        )

    state = evidence_state
    reason = evidence_reason
    if region_refusal or fog_refusal:
        state = "REFUSED"
        reason = region_refusal or fog_refusal
    elif query_state == "UNKNOWN" or any(row["state"] in {"UNKNOWN", "REFUSED"} for row in stages):
        state = "UNKNOWN" if evidence_state != "REFUSED" else "REFUSED"
        reason = "the query path is incomplete; inspect its typed stages and omissions"

    return {
        "schema_version": QUERY_SCHEMA,
        "semantic_anchor": "research:query-path",
        "state": state,
        "reason": reason,
        "query": query_text,
        "declared_parameters": declared,
        "stages": stages,
        "regions": regions,
        "fog": fog,
        "omissions": omissions,
        "continuation": _words(data.get("continuation"), fallback="atlas://query/descent"),
    }


def _experiment_matrix(
    campaigns: Sequence[Mapping[str, Any]] | None,
    runs: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    campaign_rows = _sequence(campaigns)
    run_rows = _sequence(runs)
    refusals: list[str] = []
    normalized_runs: list[dict[str, Any]] = []
    run_by_campaign_arm: dict[tuple[str, str], dict[str, Any]] = {}

    for index, row in enumerate(run_rows):
        if not isinstance(row, Mapping):
            refusals.append("run evidence contains a malformed non-object row")
            continue
        ident = _words(row.get("id") or row.get("run_id"), fallback=f"run-{index + 1}")
        campaign_id = _words(row.get("campaign_id"), fallback="unassigned")
        arm_id = _words(row.get("arm_id") or row.get("arm"), fallback="unassigned")
        phase = _words(row.get("phase"), fallback="UNKNOWN").upper()
        state, reason = _evidence_state(row, default_reason="run has no live evidence")
        if phase not in _RUN_PHASES and phase != "UNKNOWN":
            state = "REFUSED"
            reason = f"run supplied unsupported phase {phase!r}"
            refusals.append(reason)
        metrics = dict(row.get("metrics")) if isinstance(row.get("metrics"), Mapping) else {}
        run = {
            "id": ident,
            "semantic_anchor": f"research:run:{ident}",
            "label": _words(row.get("label"), fallback=ident.replace("-", " ").title()),
            "campaign_id": campaign_id,
            "arm_id": arm_id,
            "phase": phase,
            "state": state,
            "reason": reason,
            "metrics": metrics,
            "started_at": _words(row.get("started_at")),
            "observation_time": _words(row.get("observation_time")),
            "continuation": _words(row.get("continuation")),
            "manifest_state": _words(row.get("manifest_state"), fallback="UNKNOWN").upper(),
        }
        normalized_runs.append(run)
        key = (campaign_id, arm_id)
        if key in run_by_campaign_arm:
            refusals.append(f"multiple runs claim campaign/arm cell {campaign_id!r}/{arm_id!r}")
        else:
            run_by_campaign_arm[key] = run

    arms: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    seen_campaigns: set[str] = set()
    for index, row in enumerate(campaign_rows):
        if not isinstance(row, Mapping):
            refusals.append("campaign evidence contains a malformed non-object row")
            continue
        ident = _words(row.get("id") or row.get("campaign_id"), fallback=f"campaign-{index + 1}")
        if ident in seen_campaigns:
            refusals.append(f"campaign evidence contains duplicate id {ident!r}")
            continue
        seen_campaigns.add(ident)
        state, reason = _evidence_state(row, default_reason="campaign has no admitted evidence")
        declared_arms: list[str] = []
        for arm_index, arm in enumerate(_sequence(row.get("arms"))):
            if isinstance(arm, Mapping):
                arm_id = _words(arm.get("id") or arm.get("name"), fallback=f"arm-{arm_index + 1}")
                arm_label = _words(arm.get("label") or arm.get("name"), fallback=arm_id)
            else:
                arm_id = _words(arm, fallback=f"arm-{arm_index + 1}")
                arm_label = arm_id
            arms.setdefault(arm_id, arm_label)
            declared_arms.append(arm_id)
        rows.append(
            {
                "id": ident,
                "semantic_anchor": f"research:campaign:{ident}",
                "label": _words(row.get("label") or row.get("name"), fallback=ident.replace("-", " ").title()),
                "state": state,
                "reason": reason,
                "question_count": row.get("question_count"),
                "budget": row.get("budget"),
                "declared_arms": declared_arms,
                "continuation": _words(row.get("continuation")),
            }
        )

    for run in normalized_runs:
        arms.setdefault(run["arm_id"], run["arm_id"].replace("-", " ").title())
    columns = [
        {"id": arm_id, "label": arms[arm_id], "semantic_anchor": f"research:arm:{arm_id}"}
        for arm_id in sorted(arms)
    ]
    for row in rows:
        cells: list[dict[str, Any]] = []
        for column in columns:
            run = run_by_campaign_arm.get((row["id"], column["id"]))
            if run is None:
                cell = {
                    "semantic_anchor": f"research:matrix:{row['id']}:{column['id']}",
                    "campaign_id": row["id"],
                    "arm_id": column["id"],
                    "state": "UNKNOWN",
                    "reason": "no run evidence is joined for this declared cell",
                    "phase": "UNKNOWN",
                    "metrics": {},
                    "run_id": "",
                    "continuation": row["continuation"],
                }
            else:
                cell = {
                    "semantic_anchor": f"research:matrix:{row['id']}:{column['id']}",
                    "campaign_id": row["id"],
                    "arm_id": column["id"],
                    "state": run["state"],
                    "reason": run["reason"],
                    "phase": run["phase"],
                    "metrics": run["metrics"],
                    "run_id": run["id"],
                    "continuation": run["continuation"],
                }
            cells.append(cell)
        row["cells"] = cells

    omissions: list[dict[str, Any]] = []
    if not rows:
        omissions.append(
            _omission(
                "campaigns-unavailable",
                "No experiment or campaign producer is joined",
                cause="UNKNOWN",
                continuation="campaign://frontier",
            )
        )
    if rows and not normalized_runs:
        omissions.append(
            _omission(
                "runs-unavailable",
                "Campaigns are visible but no live or sealed run evidence is joined",
                cause="UNKNOWN",
                continuation="campaign://runs",
                count=sum(max(1, len(row["declared_arms"])) for row in rows),
            )
        )
    state = "REFUSED" if refusals else ("COMPLETE" if rows and normalized_runs else "UNKNOWN")
    reason = refusals[0] if refusals else (
        "campaign and run evidence are joined" if state == "COMPLETE"
        else "experiment evidence is incomplete; omissions remain visible"
    )
    return {
        "schema_version": MATRIX_SCHEMA,
        "semantic_anchor": "research:experiment-matrix",
        "state": state,
        "reason": reason,
        "columns": columns,
        "rows": rows,
        "runs": normalized_runs,
        "phase_order": list(_RUN_PHASES),
        "omissions": omissions,
    }


def _result_comparison(result_sets: Sequence[Mapping[str, Any]] | None) -> dict[str, Any]:
    supplied = _sequence(result_sets)
    entries: list[dict[str, Any]] = []
    refusals: list[str] = []
    axes: set[str] = set()
    for index, row in enumerate(supplied):
        if not isinstance(row, Mapping):
            refusals.append("result comparison contains a malformed non-object row")
            continue
        ident = _words(row.get("id") or row.get("run_id"), fallback=f"result-{index + 1}")
        metrics = row.get("metrics") if isinstance(row.get("metrics"), Mapping) else {}
        clean_metrics: dict[str, float] = {}
        for key, value in metrics.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            clean_metrics[str(key)] = float(value)
            axes.add(str(key))
        state, reason = _evidence_state(row, default_reason="result row has no admitted evidence")
        if not clean_metrics and state == "COMPLETE":
            state = "UNKNOWN"
            reason = "result row contains no numeric comparable measures"
        entries.append(
            {
                "id": ident,
                "semantic_anchor": f"research:result:{ident}",
                "label": _words(row.get("label") or row.get("arm"), fallback=ident.replace("-", " ").title()),
                "state": state,
                "reason": reason,
                "metrics": clean_metrics,
                "provenance": dict(row.get("provenance")) if isinstance(row.get("provenance"), Mapping) else {},
                "continuation": _words(row.get("continuation")),
            }
        )
    ordered_axes: list[dict[str, Any]] = []
    for key in sorted(axes):
        values = [entry["metrics"][key] for entry in entries if key in entry["metrics"]]
        ordered_axes.append(
            {
                "id": key,
                "semantic_anchor": f"research:metric:{key}",
                "label": key.replace("_", " ").title(),
                "minimum": min(values),
                "maximum": max(values),
            }
        )
    omissions: list[dict[str, Any]] = []
    if not entries:
        omissions.append(
            _omission(
                "results-unavailable",
                "No comparable result sets are joined",
                cause="UNKNOWN",
                continuation="campaign://results",
            )
        )
    elif not ordered_axes:
        omissions.append(
            _omission(
                "metrics-unavailable",
                "Result rows contain no producer-declared numeric comparison axis",
                cause="UNKNOWN",
                continuation="campaign://results/metrics",
                count=len(entries),
                members=[entry["id"] for entry in entries],
            )
        )
    state = "REFUSED" if refusals else (
        "COMPLETE" if len(entries) >= 2 and ordered_axes else "UNKNOWN"
    )
    reason = refusals[0] if refusals else (
        "result sets are comparable over producer-supplied numeric axes" if state == "COMPLETE"
        else "comparison needs at least two result sets and one shared numeric axis"
    )
    return {
        "schema_version": COMPARISON_SCHEMA,
        "semantic_anchor": "research:result-comparison",
        "state": state,
        "reason": reason,
        "axes": ordered_axes,
        "entries": entries,
        "omissions": omissions,
    }


def project(
    *,
    query: str = "",
    query_evidence: Mapping[str, Any] | None = None,
    campaigns: Sequence[Mapping[str, Any]] | None = None,
    runs: Sequence[Mapping[str, Any]] | None = None,
    result_sets: Sequence[Mapping[str, Any]] | None = None,
    source_currentness: Mapping[str, Any] | None = None,
    observation_time: str = "",
) -> dict[str, Any]:
    """Join supplied read evidence into one immutable Research / Compute surface."""
    currentness = _currentness(source_currentness)
    query_path = _query_path(query, query_evidence)
    matrix = _experiment_matrix(campaigns, runs)
    comparison = _result_comparison(result_sets)
    components = [query_path, matrix, comparison]
    if currentness["status"] == "REFUSED" or any(item["state"] == "REFUSED" for item in components):
        state = "REFUSED"
        reason = "one or more joined research/compute faces refused exact interpretation"
    elif currentness["status"] != "CURRENT" or any(item["state"] != "COMPLETE" for item in components):
        state = "UNKNOWN"
        reason = "the surface is usable read-only, but one or more exact evidence faces are incomplete"
    else:
        state = "COMPLETE"
        reason = "all supplied research/compute evidence is current and complete"

    omissions = [
        omission
        for component in components
        for omission in component.get("omissions", [])
    ]
    ordered_visible_handles = [
        query_path["semantic_anchor"],
        *[row["semantic_anchor"] for row in query_path["stages"]],
        *[row["semantic_anchor"] for row in query_path["regions"]],
        matrix["semantic_anchor"],
        *[row["semantic_anchor"] for row in matrix["rows"]],
        *[run["semantic_anchor"] for run in matrix["runs"]],
        comparison["semantic_anchor"],
        *[entry["semantic_anchor"] for entry in comparison["entries"]],
    ]
    model: dict[str, Any] = {
        "schema_version": SCHEMA,
        "semantic_anchor": "research:compute-surface",
        "state": state,
        "reason": reason,
        "currentness": currentness,
        "query_path": query_path,
        "experiment_matrix": matrix,
        "result_comparison": comparison,
        "ordered_visible_handles": ordered_visible_handles,
        "omissions": omissions,
        "omitted_digest": _handle("research-omissions", omissions),
        "observation_time": _words(observation_time or currentness["observation_time"]),
        "provenance": {
            "query": ["atlas.routing", "laplace.engine.recursive_read", "laplace.research.lit_search"],
            "campaign": ["campaign.harness", "laplace.research.superarc.genesis_loop"],
            "historical_quarry": ["synthetics-genesis", "Synthetics Genesis", "SuperARC"],
        },
        "read_only": True,
        "authority_effect": "none",
        "second_truth_store": False,
        "network_effect": "none",
    }
    model["model_handle"] = _handle("research-compute-model", model)
    return model


__all__ = [
    "COMPARISON_SCHEMA",
    "MATRIX_SCHEMA",
    "QUERY_SCHEMA",
    "SCHEMA",
    "project",
]
