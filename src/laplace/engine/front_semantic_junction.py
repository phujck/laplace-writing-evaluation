"""Pure read projection for the Aisthesis semantic UP/DOWN junction.

This module owns no producer, filesystem read, clock, cache, store, or write path.  It
turns already-observed canonical values into one human-facing contract while keeping
three things deliberately separate:

* Atlas ``UP``/``DOWN`` promotion and prolongation history;
* the whole-system ``meaning_upfold`` concept-tree lineage; and
* the latest compact semantic-fold receipt and its exact source-to-successor relation.

Exact handles are retained only beneath the explicitly Audit-only envelope.  The
resting face carries human meaning, typed state, counts, residuals, and continuations.
Producer absence therefore remains useful and truthful ``UNKNOWN`` rather than an
empty success or an invented reconstruction statistic.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

SEMANTIC_JUNCTION_SCHEMA = "laplace.aisthesis-semantic-junction/1"
ATLAS_LINEAGE_SCHEMA = "laplace.atlas-updown-lineage/1"
MEANING_UPFOLD_SCHEMA = "laplace.meaning-upfold-lineage/1"
COMPACT_FOLD_SCHEMA = "laplace.semantic-fold-receipt/1"
EMBEDDING_HEALTH_SCHEMA = "laplace.embedding-health/1"
SEMANTIC_MEMORY_SCHEMA = "laplace.aisthesis-semantic-memory/1"
REGISTER_DICTIONARY_SCHEMA = "laplace.semantic-register-dictionary/1"
REGISTER_EXPANSION_SCHEMA = "laplace.semantic-register-expansion/1"
TYPED_DESCENT_COVERAGE_SCHEMA = "laplace.typed-descent-coverage/1"
OUTER_FOLD_VERIFICATION_SCHEMA = "laplace.semantic-fold-outer-verification/1"
CANONICAL_UP_FAMILY_SCHEMA = "laplace.canonical-up-family-verification/1"
BOUNDED_DOWN_SCHEMA = "laplace.semantic-fold-bounded-down/1"
REGISTER_MEASUREMENT_SCHEMA = "laplace.persisted-register-frequency/1"
EMBEDDING_HEALTH_SIDE_REF_SCHEMA = "laplace.embedding-health-side-ref-proof/1"
SEMANTIC_FOLD_RECEIPT_SCHEMA = "laplace.semantic-fold-receipt/1"
SEMANTIC_SOURCE_TUPLE_SCHEMAS = {
    "laplace.semantic-fold-source-tuple/1",
    "laplace.semantic-fold-source-tuple/2",
}
SEMANTIC_FOLD_REF = "refs/eigen/semantic-fold"
SEMANTIC_FOLD_RECEIPT_REF = "refs/eigen/semantic-fold-receipt"

_LINEAGE_STATES = {"CURRENT", "STALE", "IN_FLIGHT", "UNKNOWN", "REFUSED", "ABSENT"}
_FOLD_STATES = {"CURRENT", "UPDATE-DUE", "UNKNOWN", "REFUSED", "ABSENT"}
_RESIDUAL_CLASSES = {
    "REPRESENTATION",
    "GOAL_CLOSURE",
    "DOWN_RECONSTRUCTION",
    "COVERAGE",
    "DISCOVERY_MISS",
    "BOUNDARY_RESIDUAL",
    "BUDGET_TRUNCATION",
    "STALE_UNKNOWN",
    "AXIS_DISAGREEMENT",
    "OMISSION",
}
_RESIDUAL_STATES = {"OPEN", "RESOLVED", "UNKNOWN", "REFUSED", "TRUNCATED"}
_HANDLE_TOKEN = re.compile(
    r"(?:sha256|message|event|record|region-lease):[A-Za-z0-9._:-]+|\b[0-9a-f]{40,64}\b"
)
_EXACT_IDENTIFIER = re.compile(
    r"^(?:(?:sha256|message|event|record|region-lease|atlas|object|node|cluster):"
    r"[A-Za-z0-9._:-]+|[0-9a-f]{40}|[0-9a-f]{64})$"
)
_OPCODE = re.compile(r"^[A-Z][A-Z0-9._-]{0,7}$")


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _handle(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _human(value: Any, fallback: str = "Evidence available in Audit") -> str:
    """Return human prose without leaking exact identifiers into the resting face."""

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if not isinstance(value, str) or not value.strip():
        return fallback
    cleaned = _HANDLE_TOKEN.sub("exact evidence in Audit", value.strip())
    return cleaned if cleaned else fallback


def _public_value(value: Any) -> Any:
    """Preserve numeric structure while submerging exact identifiers in public metadata."""

    if isinstance(value, Mapping):
        return {
            _human(str(key), "field"): _public_value(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_public_value(item) for item in value]
    if isinstance(value, str):
        return _human(value)
    return value


def _exact_identifier(value: Any) -> bool:
    return isinstance(value, str) and bool(_EXACT_IDENTIFIER.fullmatch(value))


def _handles(value: Any) -> tuple[list[str], bool]:
    rows = _sequence(value)
    valid = all(_exact_identifier(item) for item in rows)
    strings = [str(item) for item in rows if isinstance(item, str) and item.strip()]
    valid = valid and len(strings) == len(set(strings))
    return strings, valid


def _count_face(count: int | None, status: str) -> dict[str, Any]:
    return {
        "status": status if count is not None else "UNKNOWN",
        "count": count,
    }


def _unknown_gap(code: str, subject: str, reason: str, continuation: str) -> dict[str, Any]:
    return {
        "class": "STALE_UNKNOWN",
        "state": "UNKNOWN",
        "code": code,
        "subject": subject,
        "meaning": reason,
        "count": None,
        "budget": None,
        "continuation": continuation,
    }


def _residual_faces(
    raw_rows: Any,
    *,
    subject: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Split human residual faces from exact Audit evidence."""

    rows = _sequence(raw_rows)
    public: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    valid = True
    for index, item in enumerate(rows):
        raw = _mapping(item)
        residual_class = str(raw.get("class") or "STALE_UNKNOWN").upper()
        state = str(raw.get("state") or "UNKNOWN").upper()
        if residual_class not in _RESIDUAL_CLASSES:
            residual_class = "STALE_UNKNOWN"
            state = "REFUSED"
            valid = False
        if state not in _RESIDUAL_STATES:
            state = "REFUSED"
            valid = False
        count = raw.get("count")
        if count is not None and (
            not isinstance(count, int) or isinstance(count, bool) or count < 0
        ):
            count = None
            state = "REFUSED"
            valid = False
        budget = raw.get("budget")
        if budget is not None and not isinstance(budget, Mapping):
            budget = None
            state = "REFUSED"
            valid = False
        continuation = _human(
            raw.get("continuation"),
            "Descend through the producer's exact evidence when it becomes available",
        )
        public.append({
            "class": residual_class,
            "state": state,
            "code": _human(raw.get("code"), f"{subject.upper()}_RESIDUAL_{index + 1}"),
            "subject": _human(raw.get("subject"), subject),
            "meaning": _human(raw.get("meaning"), "Unresolved semantic remainder"),
            "count": count,
            "budget": _public_value(budget) if budget is not None else None,
            "continuation": continuation,
        })
        audit.append({
            "index": index,
            "receipt_handle": raw.get("receipt_handle"),
            "digest": raw.get("digest"),
            "continuation": raw.get("continuation"),
        })
    return public, audit, valid


def _typed_descent_projection(
    raw_value: Any,
    *,
    expected_emitted_count: int | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Project the producer's totality receipt without maintaining a private type table.

    The UI verifies the receipt shape and its arithmetic.  The canonical target registry,
    not this module, decides which kinds exist.  Consequently an absent coverage receipt is
    ``UNKNOWN`` and a contradictory ``COMPLETE`` claim is ``REFUSED``.
    """

    if not isinstance(raw_value, Mapping):
        return ({
            "status": "UNKNOWN",
            "meaning": "Typed descent coverage has not been observed",
            "emitted": expected_emitted_count,
            "typed": None,
            "untyped": None,
            "types": [],
            "continuation": "Consume the shared target-registry totality receipt",
        }, {"source_schema": None})

    raw = _copy(raw_value)
    declared = str(raw.get("status") or "UNKNOWN").upper()
    emitted = raw.get("emitted_count")
    typed = raw.get("typed_count")
    untyped = raw.get("untyped_count")
    count_values = (emitted, typed, untyped)
    counts_ok = all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for value in count_values
    )
    kinds: list[dict[str, Any]] = []
    audit_kinds: list[dict[str, Any]] = []
    kinds_ok = True
    seen: set[str] = set()
    for item in _sequence(raw.get("kinds")):
        row = _mapping(item)
        kind = row.get("kind")
        count = row.get("count")
        valid = all((
            isinstance(kind, str) and bool(kind.strip()),
            isinstance(count, int) and not isinstance(count, bool) and count >= 0,
            isinstance(kind, str) and kind not in seen,
        ))
        if not valid:
            kinds_ok = False
            continue
        seen.add(kind)
        kinds.append({"kind": _human(kind, "Typed target"), "count": count})
        audit_kinds.append({"kind": kind, "root": row.get("root")})
    exact_receipts = all(
        _exact_identifier(raw.get(field))
        for field in (
            "receipt_handle", "target_registry_handle", "emitted_root", "typed_root"
        )
    )
    arithmetic_ok = bool(counts_ok) and (
        typed + untyped == emitted
        and sum(row["count"] for row in kinds) == typed
        and (expected_emitted_count is None or emitted == expected_emitted_count)
    )
    complete = all((
        raw.get("schema_version") == TYPED_DESCENT_COVERAGE_SCHEMA,
        declared == "COMPLETE",
        exact_receipts,
        kinds_ok,
        bool(kinds) or emitted == 0,
        arithmetic_ok,
        untyped == 0,
    ))
    if complete:
        status = "COMPLETE"
    elif (
        declared == "UNKNOWN"
        and raw.get("schema_version") == TYPED_DESCENT_COVERAGE_SCHEMA
    ):
        status = "UNKNOWN"
    elif (
        declared in {"BUDGET", "TRUNCATED"}
        and raw.get("schema_version") == TYPED_DESCENT_COVERAGE_SCHEMA
        and counts_ok
        and kinds_ok
    ):
        status = declared
    else:
        status = "REFUSED"
    return ({
        "status": status,
        "meaning": {
            "COMPLETE": "Every emitted object has one target-registry typed descent route",
            "BUDGET": "Typed-route enumeration stopped at the declared budget",
            "TRUNCATED": "Typed-route enumeration is incomplete with a continuation",
            "UNKNOWN": "Typed descent coverage is not yet proven",
            "REFUSED": "Typed descent coverage contradicts its totality receipt",
        }[status],
        "emitted": emitted if counts_ok else expected_emitted_count,
        "typed": typed if counts_ok else None,
        "untyped": untyped if counts_ok else None,
        "types": sorted(kinds, key=lambda row: (row["kind"], row["count"])),
        "continuation": _human(
            raw.get("continuation"),
            "Descend through the shared target registry and totality receipt",
        ),
    }, {
        "source_schema": raw.get("schema_version"),
        "declared_status": declared,
        "receipt_handle": raw.get("receipt_handle"),
        "target_registry_handle": raw.get("target_registry_handle"),
        "emitted_root": raw.get("emitted_root"),
        "typed_root": raw.get("typed_root"),
        "kinds": audit_kinds,
    })


def _lineage_projection(
    raw_value: Mapping[str, Any] | None,
    *,
    expected_schema: str,
    kind: str,
    label: str,
    purpose: str,
    missing_dependency: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if raw_value is None:
        face = {
            "kind": kind,
            "label": label,
            "purpose": purpose,
            "status": "UNKNOWN",
            "summary": f"{label} producer is unavailable",
            "reach": {
                "leaves": _count_face(None, "UNKNOWN"),
                "members": _count_face(None, "UNKNOWN"),
                "clusters": _count_face(None, "UNKNOWN"),
            },
            "residuals": [_unknown_gap(
                "PRODUCER_ABSENT", label,
                f"No current {label} observation was supplied",
                missing_dependency,
            )],
        }
        return face, {"source_schema": None, "missing_dependency": missing_dependency}

    raw = _copy(raw_value)
    declared = str(raw.get("status") or "UNKNOWN").upper()
    status = declared if declared in _LINEAGE_STATES else "REFUSED"
    schema_ok = raw.get("schema_version") == expected_schema
    if not schema_ok:
        status = "REFUSED"

    reach = _mapping(raw.get("reach"))
    leaf_handles, leaves_ok = _handles(reach.get("leaf_handles"))
    member_handles, members_ok = _handles(reach.get("member_handles"))
    cluster_handles, clusters_ok = _handles(reach.get("cluster_handles"))
    reach_supplied = isinstance(raw.get("reach"), Mapping)
    if status == "CURRENT" and not (reach_supplied and leaves_ok and members_ok and clusters_ok):
        status = "REFUSED"
    if status == "CURRENT" and not _exact_identifier(raw.get("receipt_handle")):
        status = "REFUSED"
    expected_emitted = (
        len(set(leaf_handles) | set(cluster_handles))
        if reach_supplied and leaves_ok and clusters_ok else None
    )
    typed_face, typed_audit = _typed_descent_projection(
        raw.get("typed_descent"), expected_emitted_count=expected_emitted,
    )
    if status == "CURRENT" and typed_face["status"] == "REFUSED":
        status = "REFUSED"
    reach_status = status if typed_face["status"] == "COMPLETE" else typed_face["status"]

    public_residuals, residual_audit, residuals_ok = _residual_faces(
        raw.get("residuals"), subject=label,
    )
    if not public_residuals:
        public_residuals = [_unknown_gap(
            "RESIDUAL_PROJECTION_ABSENT", label,
            "The lineage supplied no typed residual projection",
            f"{expected_schema}.residuals",
        )]
    if status == "CURRENT" and not residuals_ok:
        status = "REFUSED"

    operation = _mapping(raw.get("latest_operation"))
    face = {
        "kind": kind,
        "label": label,
        "purpose": purpose,
        "status": "UNKNOWN" if status == "ABSENT" else status,
        "summary": _human(raw.get("summary"), f"{label} evidence is {status.lower()}"),
        "latest_operation": {
            "kind": _human(operation.get("kind"), "No current operation"),
            "from_grade": _human(operation.get("from_grade"), "Unknown source grade"),
            "to_grade": _human(operation.get("to_grade"), "Unknown target grade"),
            "assumption": _human(operation.get("assumption"), "Unknown assumption"),
            "fibre": _human(operation.get("fibre"), "Unknown fibre"),
            "representation": _human(
                operation.get("representation"), "Representation sufficiency is unknown"
            ),
        },
        "reach": {
            "leaves": _count_face(
                len(leaf_handles) if reach_supplied and leaves_ok else None, reach_status
            ),
            "members": _count_face(
                len(member_handles) if reach_supplied and members_ok else None, reach_status
            ),
            "clusters": _count_face(
                len(cluster_handles) if reach_supplied and clusters_ok else None, reach_status
            ),
        },
        "typed_descent": typed_face,
        "residuals": public_residuals,
    }
    audit = {
        "source_schema": raw.get("schema_version"),
        "declared_status": declared,
        "receipt_handle": raw.get("receipt_handle"),
        "event_handle": raw.get("event_handle"),
        "operator_generation": raw.get("operator_generation"),
        "reach": {
            "leaf_handles": leaf_handles,
            "member_handles": member_handles,
            "cluster_handles": cluster_handles,
        },
        "latest_operation": {
            "act_handle": operation.get("act_handle"),
            "node_handle": operation.get("node_handle"),
            "metric_version": operation.get("metric_version"),
            "grade_contract": operation.get("grade_contract"),
        },
        "residuals": residual_audit,
        "typed_descent": typed_audit,
    }
    return face, audit


def _down_projection(
    atlas_raw: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if atlas_raw is None or not isinstance(atlas_raw.get("latest_down"), Mapping):
        return ({
            "status": "UNKNOWN",
            "verification": "UNKNOWN",
            "meaning": "No canonical DOWN reconstruction receipt is available",
            "requested": None,
            "reconstructed": None,
            "verified": None,
            "missing": None,
            "coverage_ratio": None,
            "round_trip_residual": None,
            "continuation": "Supply a typed atlas.down-history-act receipt",
        }, {"source_schema": None})

    down = _copy(atlas_raw["latest_down"])
    requested, requested_ok = _handles(down.get("member_handles"))
    reconstructed, reconstructed_ok = _handles(down.get("reconstructed_handles"))
    verified, verified_ok = _handles(down.get("verified_handles"))
    requested_set = set(requested)
    reconstructed_set = set(reconstructed)
    verified_set = set(verified)
    subset_ok = reconstructed_set <= requested_set and verified_set <= reconstructed_set
    receipt_ok = _exact_identifier(down.get("receipt_handle"))
    result_ok = all((
        down.get("schema_version") == "atlas.down-history-act/1",
        _exact_identifier(down.get("act_handle")),
        down.get("route_only") is False,
    ))
    round_trip = down.get("round_trip_residual")
    residual_ok = round_trip is None or (_finite(round_trip) and 0.0 <= float(round_trip))
    valid = all((
        requested_ok, reconstructed_ok, verified_ok, subset_ok,
        receipt_ok, result_ok, residual_ok,
    ))
    verified_truth = all((
        down.get("verified") is True,
        down.get("originals_supplied") is True,
        requested_set == reconstructed_set == verified_set,
        _finite(round_trip),
    ))
    unverified_truth = all((
        down.get("verified") is False,
        down.get("originals_supplied") is False,
        not verified,
        round_trip is None,
    ))

    if not valid:
        status = "REFUSED"
        verification = "REFUSED"
    elif not requested:
        status = "UNKNOWN"
        verification = "UNKNOWN"
    elif verified_truth:
        status = "COMPLETE"
        verification = "VERIFIED"
    elif requested_set == reconstructed_set and unverified_truth:
        status = "COMPLETE"
        verification = "UNVERIFIED"
    elif reconstructed and unverified_truth:
        status = "PARTIAL"
        verification = "UNVERIFIED"
    else:
        status = "REFUSED"
        verification = "REFUSED"
    missing_count = len(requested_set - reconstructed_set) if requested_ok else None
    ratio = len(reconstructed) / len(requested) if requested else None
    return ({
        "status": status,
        "verification": verification,
        "meaning": {
            "VERIFIED": "Every requested member was reconstructed against supplied originals",
            "UNVERIFIED": "DOWN reconstructed from retained state without complete original proof",
            "REFUSED": "The supplied DOWN coverage contradicts its typed membership",
            "UNKNOWN": "DOWN reconstruction coverage is not yet measurable",
        }[verification],
        "requested": len(requested) if requested_ok else None,
        "reconstructed": len(reconstructed) if reconstructed_ok else None,
        "verified": len(verified) if verified_ok else None,
        "missing": missing_count,
        "coverage_ratio": ratio,
        "round_trip_residual": float(round_trip) if _finite(round_trip) else None,
        "continuation": _human(
            down.get("continuation"),
            "Descend to the canonical DOWN receipt and unresolved member set",
        ),
    }, {
        "source_schema": down.get("schema_version"),
        "receipt_handle": down.get("receipt_handle"),
        "act_handle": down.get("act_handle"),
        "event_handle": down.get("event_handle"),
        "node_handle": down.get("node_handle"),
        "member_handles": requested,
        "reconstructed_handles": reconstructed,
        "verified_handles": verified,
        "originals_supplied": down.get("originals_supplied"),
        "verified": down.get("verified"),
        "route_only": down.get("route_only"),
    })


def _coordinate(raw: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = _mapping(raw.get(key))
    return {"commit": value.get("commit"), "tree": value.get("tree")}


def _coordinate_complete(value: Mapping[str, Any]) -> bool:
    if "root" in value:
        return _exact_identifier(value.get("root"))
    return all(_exact_identifier(value.get(key)) for key in ("commit", "tree"))


def _receipt_handle(value: Any) -> Any:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in ("handle", "receipt_handle", "event_id", "act_handle"):
            if value.get(key):
                return value.get(key)
    return None


def _embedding_witnesses_complete(value: Any) -> tuple[list[dict[str, Any]], bool]:
    """Normalize the producer's direct reachability-witness list.

    A reached semantic node is not enough.  The frozen producer proves that each
    planted query reached its expected node *and* completed one registered exact
    descent without an authority effect.  Keep that exact boundary here so the
    carrier never upgrades routing metadata into reconstruction evidence.
    """

    rows = _sequence(value)
    normalized: list[dict[str, Any]] = []
    for supplied in rows:
        row = _mapping(supplied)
        route = _mapping(row.get("exact_route"))
        face = {
            "query": row.get("query"),
            "router": row.get("router"),
            "visited": row.get("visited"),
            "expected_semantic_node": row.get("expected_semantic_node"),
            "reached": row.get("reached"),
            "reachability_mode": row.get("reachability_mode"),
            "discovery_reached": row.get("discovery_reached"),
            "discovery_status": row.get("discovery_status"),
            "discovery_region_anchor": row.get("discovery_region_anchor"),
            "discovery_region_member_count": row.get("discovery_region_member_count"),
            "local_search_budget": row.get("local_search_budget"),
            "exact_route": _copy(route),
            "exact_content_handle": row.get("exact_content_handle"),
            "exact_content_status": row.get("exact_content_status"),
            "descent_authority_write": row.get("descent_authority_write"),
        }
        normalized.append(face)
    complete = bool(normalized) and all(
        row["reached"] is True
        and isinstance(row["expected_semantic_node"], str)
        and bool(row["expected_semantic_node"])
        and isinstance(row["exact_route"].get("kind"), str)
        and bool(row["exact_route"].get("kind"))
        and isinstance(row["exact_route"].get("reference"), str)
        and bool(row["exact_route"].get("reference"))
        and _exact_identifier(row["exact_content_handle"])
        and row["exact_content_status"] == "COMPLETE"
        and row["descent_authority_write"] == "none"
        for row in normalized
    )
    return normalized, complete


def embedding_health_side_ref(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return the one consumer proof for the shared semantic side-ref health.

    ``laplace.embedding-health/1`` is already the producer-owned currentness
    implementation.  This function does not open Git, Atlas, a manifest, or a
    receipt and therefore does not found a second authority.  It only checks that
    the supplied, already-verified producer face is internally complete enough to
    show: repository source ``S``; sole-child semantic output ``F``; the live
    repository coordinate; and the semantic ref which names ``F``.

    In the ordinary side-ref state the repository remains at ``S`` while
    ``refs/eigen/semantic-fold`` names ``F``.  Requiring ``HEAD == F`` would turn a
    healthy side-ref into a false refusal, so the live source may equal ``S`` (the
    normal state) or ``F`` (the producer's compatible transitional observation).
    """

    raw = _copy(value) if isinstance(value, Mapping) else {}
    if isinstance(raw.get("tree_fold"), Mapping):
        tree = raw["tree_fold"]
        # Preserve the consumer shape without importing the historical S-to-F proof.
        proof = embedding_health_side_ref({
            "schema_version": raw.get("schema_version"), "status": "UNKNOWN",
        })
        files = tree.get("files") or []
        receipt = _mapping(tree.get("latest_receipt"))
        stat_complete = (
            len(files) == 3
            and {row.get("path") for row in files if isinstance(row, Mapping)}
            == {".self_embeddings.json", ".self_graded.json", ".meaning_tree.json"}
            and all(isinstance(row, Mapping) and all(
                isinstance(row.get(key), int) and not isinstance(row.get(key), bool)
                and row[key] >= 0 for key in ("size", "mtime_ns", "inode")
            ) for row in files)
        )
        receipt_complete = (
            isinstance(receipt.get("ts"), str) and bool(receipt["ts"])
            and isinstance(receipt.get("nodes"), int)
            and not isinstance(receipt.get("nodes"), bool)
            and receipt["nodes"] >= 0 and receipt["nodes"] == tree.get("nodes")
        )
        declared = str(raw.get("status") or "UNKNOWN").upper()
        current = all((
            raw.get("schema_version") == EMBEDDING_HEALTH_SCHEMA,
            raw.get("shared") is True, raw.get("non_blocking") is True,
            raw.get("authority_effect") == "none", tree.get("role") == "primary",
            tree.get("status") == declared == "CURRENT",
            tree.get("stale_paths") == 0, stat_complete, receipt_complete,
        ))
        status = {"CURRENT": "CURRENT" if current else "REFUSED",
                  "STALE": "UPDATE-DUE", "UNKNOWN": "UNKNOWN"}.get(declared, "REFUSED")
        proof.update(
            declared_status=declared, status=status, current_proof=current,
            tree_fold=_copy(tree), source_tuple_status="NOT-APPLICABLE",
            semantic_ref={"name": "worktree tree fold", "commit": None, "tree": None},
            receipt_ref={"name": ".reembed_timing.jsonl", "receipt_handle": None,
                         "ts": receipt.get("ts")},
            source_currentness={"status": tree.get("status"),
                                "basis": tree.get("staleness_basis"),
                                "stale_paths": tree.get("stale_paths")},
        )
        proof["checks"].update(tree_stat_complete=stat_complete,
                               deposit_receipt_complete=receipt_complete)
        return proof
    fold = _mapping(raw.get("fold"))
    coverage = _mapping(raw.get("coverage"))
    artifacts = _mapping(raw.get("artifacts"))
    up_down = _mapping(raw.get("up_down"))
    latest_receipt = _mapping(raw.get("latest_receipt"))
    counts = _mapping(latest_receipt.get("embedding_counts"))
    source = {"commit": fold.get("source_commit"), "tree": fold.get("source_tree")}
    successor = {"commit": fold.get("output_commit"), "tree": fold.get("output_tree")}
    active_source = _coordinate(raw, "current_source")
    declared = str(raw.get("status") or "UNKNOWN").upper()
    ui_status = str(raw.get("ui_status") or "").upper()
    if declared == "STALE" and ui_status == "UPDATE-DUE":
        normalized_status = "UPDATE-DUE"
    elif declared == "IN_FLIGHT":
        normalized_status = "UPDATE-DUE"
    elif declared in _FOLD_STATES:
        normalized_status = declared
    else:
        normalized_status = "REFUSED"

    class_rows = _sequence(coverage.get("classes"))
    classes_complete = coverage.get("required_complete") is True and bool(class_rows) and all(
        isinstance(row, Mapping)
        and isinstance(row.get("source_class"), str)
        and bool(row.get("source_class"))
        and isinstance(row.get("count"), int)
        and not isinstance(row.get("count"), bool)
        and row.get("count") > 0
        and row.get("admitted") is True
        and row.get("omitted") == 0
        and _exact_identifier(row.get("root"))
        for row in class_rows
    )
    profiles = _mapping(raw.get("profile_handles"))
    profiles_complete = set(profiles) == {"ego", "aisthesis", "superego"} and all(
        _exact_identifier(handle) for handle in profiles.values()
    )
    horizon = _mapping(fold.get("semantic_horizon"))
    atlas_source_complete = all((
        horizon.get("source_commit") == source.get("commit"),
        horizon.get("source_tree") == source.get("tree"),
        isinstance(horizon.get("atlas_cursor"), int),
        not isinstance(horizon.get("atlas_cursor"), bool),
        _exact_identifier(horizon.get("atlas_head_event_id")),
    ))

    witness_rows, witnesses_complete = _embedding_witnesses_complete(
        raw.get("semantic_reachability")
    )
    zero_deferred = (
        isinstance(counts.get("deferred"), int)
        and not isinstance(counts.get("deferred"), bool)
        and counts.get("deferred") == 0
    )
    fold_receipt_handle = fold.get("semantic_fold_receipt_handle")
    fold_index_handle = fold.get("semantic_fold_index_handle")
    outer_receipt_complete = all((
        _exact_identifier(fold_receipt_handle),
        _exact_identifier(fold_index_handle),
        up_down.get("status") == "CANONICAL-UP-BATCH-READ-ONLY-DOWN",
        up_down.get("receipt_handle") == fold_receipt_handle,
        up_down.get("index_handle") == fold_index_handle,
        _exact_identifier(up_down.get("register_generation")),
        up_down.get("register_generation") == fold.get("semantic_register_generation"),
    ))
    source_complete = _coordinate_complete(source)
    successor_complete = _coordinate_complete(successor)
    active_complete = _coordinate_complete(active_source)
    source_matches = active_source in (source, successor)
    exact_forward = fold.get("forward_relation") == "EXACT"
    roots_complete = all((
        _exact_identifier(fold.get("manifest_handle")),
        _exact_identifier(fold.get("coverage_handle")),
        _exact_identifier(artifacts.get("root")),
        artifacts.get("cache_sidecar_consistent") is True,
    ))

    # The candidate producer carries its producer-owned currentness result and the
    # exact tuple it compared to live Git/Atlas/profile heads.  We verify only that
    # carried tuple's own content address and its agreement with the visible S; the
    # live comparison remains the producer's responsibility.
    source_currentness = _mapping(raw.get("source_currentness"))
    source_tuple = _mapping(
        source_currentness.get("source_tuple") or raw.get("source_tuple")
    )
    source_tuple_present = bool(source_tuple)
    source_tuple_complete = False
    if source_tuple_present:
        carried_tuple_handle = source_tuple.get("source_tuple_handle")
        tuple_preimage = {
            key: item for key, item in source_tuple.items() if key != "source_tuple_handle"
        }
        source_tuple_complete = all((
            source_tuple.get("schema_version") in SEMANTIC_SOURCE_TUPLE_SCHEMAS,
            _handle(tuple_preimage) == carried_tuple_handle,
            source_tuple.get("git") == source,
            source_tuple.get("profile_handles") == dict(sorted(profiles.items())),
            isinstance(source_tuple.get("atlas"), Mapping),
            _exact_identifier(_mapping(source_tuple.get("atlas")).get("token_handle")),
        ))
    source_currentness_complete = all((
        source_currentness.get("status") == "CURRENT",
        source_tuple_complete,
        source_currentness.get(
            "claimed_source_tuple_handle", source_currentness.get("source_tuple_handle")
        ) == source_tuple.get("source_tuple_handle"),
        source_currentness.get(
            "active_source_tuple_handle", source_currentness.get("source_tuple_handle")
        ) == source_tuple.get("source_tuple_handle"),
        source_currentness.get("moved_fields") == [],
    ))

    side_refs = _mapping(raw.get("side_refs"))
    fold_ref = _mapping(side_refs.get(SEMANTIC_FOLD_REF) or side_refs.get("semantic_fold"))
    receipt_ref = _mapping(
        side_refs.get(SEMANTIC_FOLD_RECEIPT_REF) or side_refs.get("semantic_fold_receipt")
    )
    side_refs_complete = all((
        fold_ref.get("ref", SEMANTIC_FOLD_REF) == SEMANTIC_FOLD_REF,
        fold_ref.get("commit", fold_ref.get("target_commit")) == successor.get("commit"),
        fold_ref.get("tree", fold_ref.get("target_tree")) == successor.get("tree"),
        receipt_ref.get("ref", SEMANTIC_FOLD_RECEIPT_REF) == SEMANTIC_FOLD_RECEIPT_REF,
        receipt_ref.get("receipt_handle", receipt_ref.get("target_handle"))
        == fold_receipt_handle,
    ))

    current_proof = all((
        raw.get("schema_version") == EMBEDDING_HEALTH_SCHEMA,
        raw.get("shared") is True,
        raw.get("non_blocking") is True,
        raw.get("authority_effect") == "none",
        source_complete,
        successor_complete,
        active_complete,
        source_matches,
        source != successor,
        exact_forward,
        outer_receipt_complete,
        roots_complete,
        classes_complete,
        profiles_complete,
        atlas_source_complete,
        zero_deferred,
        witnesses_complete,
        source_currentness_complete,
        side_refs_complete,
    ))
    effective_status = normalized_status
    if declared == "CURRENT" and not current_proof:
        effective_status = "REFUSED"

    return {
        "schema_version": EMBEDDING_HEALTH_SIDE_REF_SCHEMA,
        "declared_status": declared,
        "status": effective_status,
        "current_proof": current_proof,
        "S": source,
        "F": successor,
        "active_source": active_source,
        "semantic_ref": {
            "name": SEMANTIC_FOLD_REF,
            "commit": successor.get("commit"),
            "tree": successor.get("tree"),
        },
        "receipt_ref": {
            "name": SEMANTIC_FOLD_RECEIPT_REF,
            "receipt_handle": fold_receipt_handle,
        },
        "source_tuple": _copy(source_tuple) if source_tuple_present else None,
        "source_tuple_status": (
            "VERIFIED" if source_currentness_complete else "UNKNOWN"
        ),
        "source_currentness": {
            "status": source_currentness.get("status"),
            "claimed_source_tuple_handle": source_currentness.get(
                "claimed_source_tuple_handle", source_currentness.get("source_tuple_handle")
            ),
            "active_source_tuple_handle": source_currentness.get(
                "active_source_tuple_handle", source_currentness.get("source_tuple_handle")
            ),
            "moved_fields": _copy(source_currentness.get("moved_fields") or []),
        },
        "profile_handles": _copy(profiles),
        "atlas_source": {
            "cursor": horizon.get("atlas_cursor"),
            "head_event_id": horizon.get("atlas_head_event_id"),
        },
        "fold_receipt_handle": fold_receipt_handle,
        "fold_index_handle": fold_index_handle,
        "manifest_handle": fold.get("manifest_handle"),
        "coverage_handle": fold.get("coverage_handle"),
        "artifact_root": artifacts.get("root"),
        "zero_deferred": zero_deferred,
        "reachability_witnesses": witness_rows,
        "checks": {
            "source_complete": source_complete,
            "successor_complete": successor_complete,
            "active_source_complete": active_complete,
            "active_source_matches_S_or_F": source_matches,
            "exact_forward_relation": exact_forward,
            "outer_receipt_congruent": outer_receipt_complete,
            "artifact_roots_complete": roots_complete,
            "source_classes_complete": classes_complete,
            "profile_heads_complete": profiles_complete,
            "atlas_source_complete": atlas_source_complete,
            "zero_deferred": zero_deferred,
            "typed_reachability_complete": witnesses_complete,
            "source_currentness_complete": source_currentness_complete,
            "side_refs_complete": side_refs_complete,
        },
    }


def _outer_fold_verification(
    raw_value: Any,
    *,
    receipt_handle: Any,
    source_root: Any,
    successor_root: Any,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    if not isinstance(raw_value, Mapping):
        return ({
            "status": "UNKNOWN",
            "meaning": "The outer semantic-fold receipt has not been verified",
            "zero_deferred": "UNKNOWN",
            "source_unchanged": "UNKNOWN",
            "continuation": "Consume the shared outer-receipt verification",
        }, {"source_schema": None}, False)
    raw = _copy(raw_value)
    required_truth = (
        "candidate_validated",
        "artifact_family_coherent",
        "canonical_up_verified",
        "down_index_verified",
        "runtime_verified",
        "source_unchanged",
    )
    truth_ok = all(raw.get(field) is True for field in required_truth)
    roots_ok = all((
        raw.get("receipt_handle") == receipt_handle,
        raw.get("sole_parent_root") == source_root,
        raw.get("successor_root") == successor_root,
        _exact_identifier(raw.get("verification_receipt_handle")),
        _exact_identifier(raw.get("candidate_manifest_root")),
    ))
    deferred = raw.get("deferred_count")
    deferred_ok = isinstance(deferred, int) and not isinstance(deferred, bool) and deferred == 0
    status = (
        "VERIFIED"
        if all((
            raw.get("schema_version") == OUTER_FOLD_VERIFICATION_SCHEMA,
            raw.get("status") == "VERIFIED",
            truth_ok,
            roots_ok,
            deferred_ok,
        ))
        else "REFUSED"
    )
    return ({
        "status": status,
        "meaning": (
            "The actual outer fold receipt verifies as the sole-parent successor"
            if status == "VERIFIED"
            else "The outer fold receipt is incomplete or contradicts its source boundary"
        ),
        "zero_deferred": deferred_ok,
        "source_unchanged": raw.get("source_unchanged") is True,
        "continuation": _human(
            raw.get("continuation"), "Open the outer receipt verification evidence"
        ),
    }, {
        "source_schema": raw.get("schema_version"),
        "receipt_handle": raw.get("receipt_handle"),
        "verification_receipt_handle": raw.get("verification_receipt_handle"),
        "sole_parent_root": raw.get("sole_parent_root"),
        "successor_root": raw.get("successor_root"),
        "candidate_manifest_root": raw.get("candidate_manifest_root"),
        "declared_status": raw.get("status"),
    }, status == "VERIFIED")


def _canonical_up_family(
    raw_value: Any,
    *,
    membership_root: Any,
    expected_clusters: int | None,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    if not isinstance(raw_value, Mapping):
        return ({
            "status": "UNKNOWN",
            "meaning": "Canonical UP receipt coverage has not been observed",
            "clusters": expected_clusters,
            "verified_clusters": None,
            "unverified_clusters": None,
            "continuation": "Consume the canonical UpActReceipt family verification",
        }, {"source_schema": None}, False)
    raw = _copy(raw_value)
    clusters = raw.get("cluster_count")
    verified = raw.get("verified_cluster_count")
    unverified = raw.get("unverified_cluster_count")
    counts_ok = all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for value in (clusters, verified, unverified)
    )
    arithmetic_ok = bool(counts_ok) and all((
        verified + unverified == clusters,
        unverified == 0,
        expected_clusters is None or clusters == expected_clusters,
    ))
    roots_ok = all((
        raw.get("membership_root") == membership_root,
        _exact_identifier(raw.get("family_root")),
        _exact_identifier(raw.get("receipt_rows_root")),
        _exact_identifier(raw.get("node_handle_root")),
        _exact_identifier(raw.get("up_act_handle_root")),
        _exact_identifier(raw.get("up_receipt_handle_root")),
        _exact_identifier(raw.get("verification_receipt_handle")),
    ))
    status = (
        "VERIFIED"
        if all((
            raw.get("schema_version") == CANONICAL_UP_FAMILY_SCHEMA,
            raw.get("status") == "VERIFIED",
            arithmetic_ok,
            roots_ok,
        ))
        else "REFUSED"
    )
    return ({
        "status": status,
        "meaning": (
            "Every cluster is backed by a canonical verified UpActReceipt"
            if status == "VERIFIED"
            else "Cluster membership is not backed by one coherent canonical UP receipt family"
        ),
        "clusters": clusters if counts_ok else expected_clusters,
        "verified_clusters": verified if counts_ok else None,
        "unverified_clusters": unverified if counts_ok else None,
        "continuation": _human(
            raw.get("continuation"), "Open the canonical UP family verification"
        ),
    }, {
        "source_schema": raw.get("schema_version"),
        "membership_root": raw.get("membership_root"),
        "family_root": raw.get("family_root"),
        "receipt_rows_root": raw.get("receipt_rows_root"),
        "node_handle_root": raw.get("node_handle_root"),
        "up_act_handle_root": raw.get("up_act_handle_root"),
        "up_receipt_handle_root": raw.get("up_receipt_handle_root"),
        "verification_receipt_handle": raw.get("verification_receipt_handle"),
    }, status == "VERIFIED")


def _bounded_down_projection(
    raw_value: Any,
    *,
    fold_receipt_handle: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(raw_value, Mapping):
        return ({
            "status": "UNKNOWN",
            "verification": "UNKNOWN",
            "meaning": "No bounded fold-backed DOWN result was supplied",
            "requested": None,
            "reconstructed": None,
            "verified": None,
            "shards_read": None,
            "rows_read": None,
            "round_trip_residual": None,
            "continuation": "Run one bounded typed DOWN query through the shared producer",
        }, {"source_schema": None})
    raw = _copy(raw_value)
    declared = str(raw.get("status") or "UNKNOWN").upper()
    requested = raw.get("requested_count")
    reconstructed = raw.get("reconstructed_count")
    verified_count = raw.get("verified_count")
    shards_read = raw.get("shards_read")
    rows_read = raw.get("rows_read")
    numbers_ok = all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for value in (requested, reconstructed, verified_count, shards_read, rows_read)
    )
    bounded = bool(numbers_ok) and shards_read <= 1 and rows_read <= 1
    counts_ok = bool(numbers_ok) and verified_count <= reconstructed <= requested
    result_exact = all((
        raw.get("fold_receipt_handle") == fold_receipt_handle,
        _exact_identifier(raw.get("down_result_handle")),
        _exact_identifier(raw.get("up_act_handle")),
        _exact_identifier(raw.get("up_receipt_handle")),
        _exact_identifier(raw.get("row_hash")),
    ))
    originals_supplied = raw.get("originals_supplied") is True
    verified_declared = raw.get("verified") is True
    residual = raw.get("round_trip_residual")
    verified_truth = all((
        originals_supplied,
        verified_declared,
        counts_ok,
        requested == reconstructed == verified_count,
        _finite(residual),
        float(residual) >= 0.0 if _finite(residual) else False,
    ))
    unverified_truth = all((
        not originals_supplied,
        raw.get("verified") is False,
        counts_ok,
        requested == reconstructed,
        verified_count == 0,
        residual is None,
    ))
    route_only = raw.get("route_only") is True
    structural_ok = all((
        raw.get("schema_version") == BOUNDED_DOWN_SCHEMA,
        declared in {"COMPLETE", "BUDGET", "TRUNCATED", "REFUSED", "UNKNOWN"},
        bounded,
        counts_ok,
    ))
    if route_only and (reconstructed or verified_count or declared == "COMPLETE"):
        status = "REFUSED"
        verification = "REFUSED"
    elif declared == "COMPLETE" and structural_ok and result_exact and verified_truth:
        status = "COMPLETE"
        verification = "VERIFIED"
    elif declared == "COMPLETE" and structural_ok and result_exact and unverified_truth:
        status = "COMPLETE"
        verification = "UNVERIFIED"
    elif all((
        declared in {"BUDGET", "TRUNCATED"},
        structural_ok,
        raw.get("route_only") is False,
        _exact_identifier(raw.get("continuation_handle")),
        not reconstructed or result_exact,
    )):
        status = declared
        verification = "UNVERIFIED"
    elif declared == "UNKNOWN" and structural_ok and not reconstructed and not verified_count:
        status = "UNKNOWN"
        verification = "UNKNOWN"
    else:
        status = "REFUSED"
        verification = "REFUSED"
    return ({
        "status": status,
        "verification": verification,
        "meaning": {
            "VERIFIED": "Canonical DOWN reconstructed every member and measured the originals",
            "UNVERIFIED": "Canonical DOWN reconstructed members without complete original verification",
            "UNKNOWN": "No reconstruction result is proven",
            "REFUSED": "Route metadata or contradictory evidence cannot count as DOWN",
        }[verification],
        "requested": requested if numbers_ok else None,
        "reconstructed": reconstructed if numbers_ok else None,
        "verified": verified_count if numbers_ok else None,
        "shards_read": shards_read if numbers_ok else None,
        "rows_read": rows_read if numbers_ok else None,
        "round_trip_residual": float(residual) if _finite(residual) else None,
        "continuation": _human(
            raw.get("continuation"), "Open the exact bounded DOWN result and continuation"
        ),
    }, {
        "source_schema": raw.get("schema_version"),
        "fold_receipt_handle": raw.get("fold_receipt_handle"),
        "down_result_handle": raw.get("down_result_handle"),
        "up_act_handle": raw.get("up_act_handle"),
        "up_receipt_handle": raw.get("up_receipt_handle"),
        "row_hash": raw.get("row_hash"),
        "continuation_handle": raw.get("continuation_handle"),
        "route_only": route_only,
    })


def _fold_projection(
    fold_value: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if fold_value is None:
        return ({
            "status": "UNKNOWN",
            "label": "Compact semantic fold unavailable",
            "source_to_successor": "No typed source-to-successor receipt is available",
            "lag_commits": None,
            "reach": {
                "leaves": _count_face(None, "UNKNOWN"),
                "members": _count_face(None, "UNKNOWN"),
                "clusters": _count_face(None, "UNKNOWN"),
            },
            "residuals": [_unknown_gap(
                "COMPACT_FOLD_PRODUCER_ABSENT", "Compact semantic fold",
                "No shared fold/profile output was supplied",
                "Consume the shared Ego-owned fold/profile producer",
            )],
        }, {"source_schema": None})

    raw = _copy(fold_value)
    schema = raw.get("schema_version")
    reach_raw: Mapping[str, Any] = {}
    residual_raw: Any = None
    if schema == COMPACT_FOLD_SCHEMA:
        declared = str(raw.get("status") or "UNKNOWN").upper()
        source = {"root": raw.get("source_root")}
        successor = {"root": raw.get("successor_root")}
        observed = {"root": raw.get("current_source_root")}
        relation = {
            "schema_version": "laplace.semantic-successor-relation/1",
            "successor_of": raw.get("successor_of"),
        }
        receipt = raw.get("receipt_handle")
        lag = raw.get("lag_commits")
        reach_raw = _mapping(raw.get("coverage"))
        residual_raw = raw.get("residuals")
        required_roots = (
            "source_class_receipts_root",
            "leaf_object_root",
            "leaf_content_root",
            "membership_root",
            "cluster_root",
            "retained_state_root",
            "semantic_source_root",
            "descent_index_root",
            "residual_root",
            "fog_omission_root",
            "artifact_family_root",
        )
        compact_roots_ok = all(_exact_identifier(raw.get(key)) for key in required_roots)
        exact_successor_relation = raw.get("successor_of") == raw.get("source_root")
    elif schema == EMBEDDING_HEALTH_SCHEMA:
        proof = embedding_health_side_ref(raw)
        status = str(proof["status"])
        if status == "ABSENT":
            status = "UNKNOWN"
        horizon = _mapping(_mapping(raw.get("fold")).get("semantic_horizon"))
        leaves = horizon.get("leaves")
        clusters = horizon.get("clusters")
        leaves = leaves if isinstance(leaves, int) and not isinstance(leaves, bool) else None
        clusters = (
            clusters if isinstance(clusters, int) and not isinstance(clusters, bool) else None
        )
        typed_complete = proof["checks"]["typed_reachability_complete"]
        typed_status = "COMPLETE" if typed_complete else "UNKNOWN"
        if proof["declared_status"] == "CURRENT" and not typed_complete:
            typed_status = "REFUSED"
        receipt_verified = proof["checks"]["outer_receipt_congruent"]
        face = {
            "status": status,
            "label": {
                "CURRENT": "Compact semantic fold is current on its semantic side-ref",
                "UPDATE-DUE": "Compact semantic fold is behind the current source",
                "REFUSED": "Compact semantic fold claim is internally inconsistent",
                "UNKNOWN": "Compact semantic fold currentness is unknown",
            }.get(status, "Compact semantic fold currentness is unknown"),
            "source_to_successor": (
                "Repository source S and sole-child semantic output F are distinct and current"
                if status == "CURRENT"
                else "Typed source-to-successor relation requires descent"
            ),
            "lag_commits": (
                _mapping(raw.get("fold")).get("lag_commits")
                if isinstance(_mapping(raw.get("fold")).get("lag_commits"), int)
                else None
            ),
            "reach": {
                "leaves": _count_face(leaves, typed_status),
                "members": _count_face(None, "UNKNOWN"),
                "clusters": _count_face(clusters, typed_status),
            },
            "outer_verification": {
                "status": "VERIFIED" if receipt_verified else "REFUSED",
                "meaning": (
                    "Producer-validated outer receipt binds S, sole-child F, roots and semantic ref"
                    if receipt_verified
                    else "The carried side-ref receipt/index face is incomplete or contradictory"
                ),
                "zero_deferred": proof["zero_deferred"],
                "source_unchanged": proof["checks"]["active_source_matches_S_or_F"],
                "continuation": "Open the producer-owned outer fold receipt",
            },
            "canonical_up_membership": {
                "status": "VERIFIED" if receipt_verified else "UNKNOWN",
                "meaning": "Canonical UP membership is rooted by the verified semantic index",
                "clusters": clusters,
                "continuation": "Descend through the semantic fold index",
            },
            "bounded_down": {
                "status": "UNKNOWN",
                "verification": "UNKNOWN",
                "requested": None,
                "reconstructed": None,
                "verified": None,
                "continuation": "Select a semantic object and request one bounded DOWN result",
            },
            "typed_descent": {
                "status": typed_status,
                "emitted": len(proof["reachability_witnesses"]),
                "typed": len(proof["reachability_witnesses"]) if typed_complete else None,
                "untyped": 0 if typed_complete else None,
                "continuation": "Open the exact typed reachability witnesses",
            },
            "residuals": (
                [] if status == "CURRENT" else [_unknown_gap(
                    "SEMANTIC_SIDE_REF_NOT_CURRENT", "Compact semantic fold",
                    "The producer does not currently prove the side-ref fold CURRENT",
                    "Descend through the shared embedding-health reason and cadence",
                )]
            ),
        }
        audit = {
            "source_schema": schema,
            "declared_status": proof["declared_status"],
            "S": _copy(proof["S"]),
            "F": _copy(proof["F"]),
            "active_source": _copy(proof["active_source"]),
            "semantic_ref": _copy(proof["semantic_ref"]),
            "receipt_ref": _copy(proof["receipt_ref"]),
            "source_tuple": _copy(proof["source_tuple"]),
            "source_tuple_status": proof["source_tuple_status"],
            "source_currentness": _copy(proof["source_currentness"]),
            "fold_receipt_handle": proof["fold_receipt_handle"],
            "fold_index_handle": proof["fold_index_handle"],
            "manifest_handle": proof["manifest_handle"],
            "coverage_handle": proof["coverage_handle"],
            "artifact_root": proof["artifact_root"],
            "profile_handles": _copy(proof["profile_handles"]),
            "atlas_source": _copy(proof["atlas_source"]),
            "reachability_witnesses": _copy(proof["reachability_witnesses"]),
            "checks": _copy(proof["checks"]),
        }
        if isinstance(raw.get("tree_fold"), Mapping):
            tree = raw["tree_fold"]
            face.update(
                label=f"Router worktree fold: {status.lower()}",
                source_to_successor=tree.get("staleness_basis"),
                reach={"leaves": _count_face(None, "UNKNOWN"),
                       "members": _count_face(tree.get("nodes"), status),
                       "clusters": _count_face(tree.get("clusters"), status)},
                outer_verification={
                    "status": "VERIFIED" if proof["current_proof"] else "UNKNOWN",
                    "meaning": "Worktree stat identities and latest deposit receipt",
                    "continuation": "Open tree_fold.latest_receipt and tree_fold.files",
                },
                residuals=[] if status == "CURRENT" else [_unknown_gap(
                    "TREE_FOLD_NOT_CURRENT", "Router worktree fold",
                    tree.get("reason") or "Tree fold currentness is unknown",
                    "Open tree_fold.latest_receipt and tree_fold.stale_paths",
                )],
            )
            # Stat currentness does not establish the old side-ref's UP/DOWN proof.
            face["typed_descent"]["status"] = "UNKNOWN"
            audit["tree_fold"] = _copy(tree)
        return face, audit
    elif schema == SEMANTIC_MEMORY_SCHEMA:
        declared = str(raw.get("health_status") or "UNKNOWN").upper()
        source = _mapping(raw.get("S"))
        successor = _mapping(raw.get("F"))
        observed = _mapping(raw.get("current_source"))
        relation = raw.get("forward_relation")
        receipt = _receipt_handle(raw.get("latest_receipt"))
        lag = _mapping(raw.get("lag")).get("commits")
        reach_raw = _mapping(raw.get("coverage"))
        residual_raw = raw.get("omissions")
    else:
        declared = "REFUSED"
        source = successor = observed = {}
        relation = receipt = lag = None
    if schema != COMPACT_FOLD_SCHEMA:
        compact_roots_ok = True
        exact_successor_relation = True

    if declared not in _FOLD_STATES:
        declared = "REFUSED"
    relation_typed = (
        isinstance(relation, str)
        and relation.upper() in {"EXACT", "EXACT_SUCCESSOR", "SEMANTIC_FORWARD", "FORWARD"}
    ) or (
        isinstance(relation, Mapping)
        and isinstance(relation.get("schema_version"), str)
        and bool(relation.get("schema_version"))
    )
    proof_complete = all((
        _coordinate_complete(source),
        _coordinate_complete(successor),
        relation_typed,
        _exact_identifier(receipt),
        compact_roots_ok,
        exact_successor_relation,
    ))
    observed_complete = _coordinate_complete(observed)
    if declared == "CURRENT":
        status = (
            "CURRENT"
            if proof_complete and observed_complete and dict(observed) == dict(successor)
            else "REFUSED"
        )
    elif declared == "UPDATE-DUE":
        status = (
            "UPDATE-DUE"
            if proof_complete and observed_complete and dict(observed) != dict(successor)
            else "REFUSED"
        )
    elif declared in {"ABSENT", "UNKNOWN"}:
        status = "UNKNOWN"
    else:
        status = "REFUSED"

    def producer_count(name: str) -> int | None:
        direct = reach_raw.get(name)
        if isinstance(direct, int) and not isinstance(direct, bool) and direct >= 0:
            return direct
        plural = reach_raw.get(f"{name}_count")
        if isinstance(plural, int) and not isinstance(plural, bool) and plural >= 0:
            return plural
        handles, valid = _handles(reach_raw.get(f"{name}_handles"))
        return len(handles) if valid and f"{name}_handles" in reach_raw else None

    leaves = producer_count("leaves")
    members = producer_count("members")
    clusters = producer_count("clusters")
    source_boundary = (
        raw.get("source_root")
        if schema == COMPACT_FOLD_SCHEMA else source.get("commit")
    )
    successor_boundary = (
        raw.get("successor_root")
        if schema == COMPACT_FOLD_SCHEMA else successor.get("commit")
    )
    outer_face, outer_audit, outer_verified = _outer_fold_verification(
        raw.get("outer_verification"),
        receipt_handle=receipt,
        source_root=source_boundary,
        successor_root=successor_boundary,
    )
    up_face, up_audit, up_verified = _canonical_up_family(
        raw.get("canonical_up"),
        membership_root=(raw.get("membership_root") if schema == COMPACT_FOLD_SCHEMA else None),
        expected_clusters=clusters,
    )
    bounded_down_face, bounded_down_audit = _bounded_down_projection(
        raw.get("bounded_down"), fold_receipt_handle=receipt,
    )
    if declared in {"CURRENT", "UPDATE-DUE"} and not (outer_verified and up_verified):
        status = "REFUSED"
    expected_emitted = leaves + clusters if leaves is not None and clusters is not None else None
    typed_face, typed_audit = _typed_descent_projection(
        raw.get("typed_descent"), expected_emitted_count=expected_emitted,
    )
    if declared == "CURRENT" and typed_face["status"] != "COMPLETE":
        status = "REFUSED"
    reach_status = status if typed_face["status"] == "COMPLETE" else typed_face["status"]
    residuals, residual_audit, residuals_ok = _residual_faces(
        residual_raw, subject="Compact semantic fold",
    )
    if not residuals:
        residuals = [_unknown_gap(
            "COMPACT_FOLD_RESIDUALS_ABSENT", "Compact semantic fold",
            "No typed compact-fold residual projection was supplied",
            "Descend through the fold receipt's coverage and omission evidence",
        )]
    if status == "CURRENT" and not residuals_ok:
        status = "REFUSED"

    face = {
        "status": status,
        "label": {
            "CURRENT": "Compact semantic fold is current",
            "UPDATE-DUE": "Compact semantic fold is behind the current source",
            "REFUSED": "Compact semantic fold claim is internally inconsistent",
            "UNKNOWN": "Compact semantic fold currentness is unknown",
        }[status],
        "source_to_successor": (
            "Typed source-to-successor relation is current"
            if status == "CURRENT"
            else "Typed source-to-successor relation requires descent"
        ),
        "lag_commits": lag if isinstance(lag, int) and not isinstance(lag, bool) and lag >= 0 else None,
        "reach": {
            "leaves": _count_face(leaves, reach_status),
            "members": _count_face(members, reach_status),
            "clusters": _count_face(clusters, reach_status),
        },
        "outer_verification": outer_face,
        "canonical_up_membership": up_face,
        "bounded_down": bounded_down_face,
        "typed_descent": typed_face,
        "residuals": residuals,
    }
    audit = {
        "source_schema": schema,
        "declared_status": declared,
        "S": _copy(source),
        "F": _copy(successor),
        "current_source": _copy(observed),
        "forward_relation": _copy(relation),
        "latest_receipt": receipt,
        "manifest_handle": (
            raw.get("artifact_family_root")
            if schema == COMPACT_FOLD_SCHEMA
            else _mapping(raw.get("fold")).get("manifest_handle")
        ),
        "coverage_handle": (
            raw.get("source_class_receipts_root")
            if schema == COMPACT_FOLD_SCHEMA
            else _mapping(raw.get("fold")).get("coverage_handle")
        ),
        "compact_roots": {
            key: raw.get(key)
            for key in (
                "source_class_receipts_root", "leaf_object_root", "leaf_content_root",
                "membership_root", "cluster_root", "retained_state_root",
                "semantic_source_root", "descent_index_root", "residual_root",
                "fog_omission_root", "artifact_family_root", "register_dictionary_root",
                "predecessor_fold_root",
            )
            if schema == COMPACT_FOLD_SCHEMA
        },
        "residuals": residual_audit,
        "outer_verification": outer_audit,
        "canonical_up_membership": up_audit,
        "bounded_down": bounded_down_audit,
        "typed_descent": typed_audit,
    }
    return face, audit


def _register_projection(
    dictionary_value: Mapping[str, Any] | None,
    *,
    active_generation: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if dictionary_value is None:
        return ({
            "status": "UNKNOWN",
            "label": "Compact register dictionary is not yet observed",
            "generation_state": "UNKNOWN",
            "entries": [],
            "frequency_basis": "UNKNOWN",
            "continuation": "Consume the shared generation-scoped register producer",
        }, {"source_schema": None, "active_generation": active_generation})

    raw = _copy(dictionary_value)
    schema_ok = raw.get("schema_version") == REGISTER_DICTIONARY_SCHEMA
    producer_generation = raw.get("generation")
    mode = str(raw.get("mode") or "DICTIONARY").upper()
    measurement = _mapping(raw.get("measurement"))
    frequency_receipt = measurement.get("receipt_handle")
    supplied_entries = _sequence(raw.get("entries"))
    generation_known = bool(active_generation)
    generation_ok = generation_known and producer_generation == active_generation
    measured_tokens = measurement.get("persisted_token_count")
    measurement_ok = all((
        measurement.get("schema_version") == REGISTER_MEASUREMENT_SCHEMA,
        measurement.get("status") == "MEASURED",
        measurement.get("source") == "persisted-token-frequency",
        isinstance(measured_tokens, int),
        not isinstance(measured_tokens, bool),
        isinstance(measured_tokens, int) and measured_tokens >= 0,
        _exact_identifier(frequency_receipt),
    ))
    allocation_ok = (
        raw.get("allocation_algorithm") == "benefit-descending-then-canonical-handle"
    )
    entries: list[dict[str, Any]] = []
    audit_entries: list[dict[str, Any]] = []
    entries_ok = True
    seen: set[str] = set()
    for item in supplied_entries:
        row = _mapping(item)
        opcode = row.get("opcode")
        kind = row.get("kind")
        meaning = row.get("meaning")
        count = row.get("count")
        canonical_bytes = row.get("canonical_bytes")
        encoded_bytes = row.get("encoded_bytes")
        canonical_handle = row.get("canonical_handle")
        benefit = (
            count * (canonical_bytes - encoded_bytes)
            if all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in (count, canonical_bytes, encoded_bytes)
            )
            else None
        )
        valid = all((
            isinstance(opcode, str) and bool(_OPCODE.fullmatch(opcode)),
            isinstance(kind, str) and bool(kind.strip()),
            isinstance(meaning, str) and bool(meaning.strip()),
            isinstance(count, int) and not isinstance(count, bool) and count >= 0,
            isinstance(canonical_bytes, int) and not isinstance(canonical_bytes, bool),
            isinstance(encoded_bytes, int) and not isinstance(encoded_bytes, bool),
            isinstance(encoded_bytes, int) and encoded_bytes == len(str(opcode).encode("utf-8")),
            isinstance(canonical_bytes, int) and canonical_bytes > encoded_bytes,
            isinstance(benefit, int) and benefit > 0,
            _exact_identifier(canonical_handle),
            _exact_identifier(row.get("evidence_handle")),
            isinstance(opcode, str) and opcode not in seen,
        ))
        if not valid:
            entries_ok = False
            continue
        seen.add(opcode)
        entries.append({
            "opcode": opcode,
            "kind": _human(kind, "Typed distinction"),
            "meaning": _human(meaning, "Canonical meaning available in Audit"),
            "count": count,
            "measured_byte_benefit": benefit,
        })
        audit_entries.append({
            "opcode": opcode,
            "canonical_handle": canonical_handle,
            "evidence_handle": row.get("evidence_handle"),
            "canonical_bytes": canonical_bytes,
            "encoded_bytes": encoded_bytes,
            "measured_byte_benefit": benefit,
        })

    expected_order = sorted(
        audit_entries,
        key=lambda row: (-row["measured_byte_benefit"], row["canonical_handle"]),
    )
    order_ok = audit_entries == expected_order
    observed_frequency_ok = bool(measurement_ok) and (
        sum(row["count"] for row in entries) <= measured_tokens
    )

    if not schema_ok or not entries_ok or mode not in {"DICTIONARY", "LITERAL"}:
        status = "REFUSED"
        public_entries: list[dict[str, Any]] = []
        generation_state = "REFUSED"
    elif not generation_known:
        status = "UNKNOWN"
        public_entries = []
        generation_state = "UNKNOWN"
    elif not generation_ok:
        status = "REFUSED"
        public_entries = []
        generation_state = "STALE_GENERATION"
    elif not measurement_ok or not observed_frequency_ok:
        status = "REFUSED" if supplied_entries or mode == "DICTIONARY" else "UNKNOWN"
        public_entries = []
        generation_state = "CURRENT"
    elif mode == "LITERAL" and not supplied_entries:
        status = "LITERAL"
        public_entries = []
        generation_state = "CURRENT"
    elif mode == "LITERAL" or not allocation_ok or not order_ok or not supplied_entries:
        status = "REFUSED"
        public_entries = []
        generation_state = "REFUSED"
    else:
        status = "CURRENT"
        public_entries = entries
        generation_state = "CURRENT"
    return ({
        "status": status,
        "label": {
            "CURRENT": "Generation-scoped semantic register",
            "LITERAL": "Measured register uses literal canonical values",
            "UNKNOWN": "Register frequencies are not yet observed",
            "REFUSED": "Register dictionary refused stale or malformed evidence",
        }[status],
        "generation_state": generation_state,
        "entries": public_entries,
        "frequency_basis": (
            "MEASURED_PERSISTED_TOKENS"
            if status in {"CURRENT", "LITERAL"} else "UNKNOWN"
        ),
        "observed_tokens": measured_tokens if measurement_ok else None,
        "continuation": {
            "CURRENT": "Select an opcode to expand its canonical meaning",
            "LITERAL": "Use the canonical literal form; no measured opcode is allocated",
            "UNKNOWN": "Supply a matching generation and persisted-token measurement",
            "REFUSED": "Descend to the rejected generation, measurement, or allocation proof",
        }[status],
    }, {
        "source_schema": raw.get("schema_version"),
        "producer_generation": producer_generation,
        "active_generation": active_generation,
        "frequency_receipt": frequency_receipt,
        "measurement": _copy(measurement),
        "mode": mode,
        "allocation_algorithm": raw.get("allocation_algorithm"),
        "entries": audit_entries,
    })


def expand_register_opcode(
    dictionary_value: Mapping[str, Any] | None,
    *,
    opcode: str,
    requested_generation: str | None,
    active_generation: str | None,
) -> dict[str, Any]:
    """Expand one short opcode, refusing stale generation or unreceipted frequency data."""

    face, audit = _register_projection(
        dictionary_value, active_generation=active_generation,
    )
    base = {
        "schema_version": REGISTER_EXPANSION_SCHEMA,
        "opcode": opcode,
        "status": "REFUSED",
        "meaning": "Register expansion refused",
        "reason": "The requested generation is not the current producer generation",
        "audit": {"visibility": "AUDIT_ONLY", **audit},
        "authority_effect": "none",
    }
    if requested_generation != active_generation or face["status"] != "CURRENT":
        base["audit"]["expansion_handle"] = _handle(base)
        return base
    match = next((row for row in face["entries"] if row["opcode"] == opcode), None)
    if match is None:
        base["reason"] = "The opcode is not present in the current dictionary"
        base["audit"]["expansion_handle"] = _handle(base)
        return base
    base.update({
        "status": "CURRENT",
        "meaning": match["meaning"],
        "reason": "Expanded from the current generation-scoped dictionary",
    })
    base["audit"]["selected"] = next(
        row for row in audit["entries"] if row["opcode"] == opcode
    )
    base["audit"]["expansion_handle"] = _handle(base)
    return base


def project_semantic_junction(
    *,
    atlas_updown: Mapping[str, Any] | None,
    meaning_upfold: Mapping[str, Any] | None,
    compact_fold: Mapping[str, Any] | None,
    register_dictionary: Mapping[str, Any] | None,
    active_register_generation: str | None,
) -> dict[str, Any]:
    """Project one immutable, human-facing semantic-junction observation."""

    atlas_face, atlas_audit = _lineage_projection(
        atlas_updown,
        expected_schema=ATLAS_LINEAGE_SCHEMA,
        kind="CANONICAL_ATLAS_UP_DOWN",
        label="Atlas promotion and descent",
        purpose="typed local coarsening and exact prolongation under one declared metric",
        missing_dependency="shared atlas.up-history-act and atlas.down-history-act projection",
    )
    meaning_face, meaning_audit = _lineage_projection(
        meaning_upfold,
        expected_schema=MEANING_UPFOLD_SCHEMA,
        kind="WHOLE_SYSTEM_MEANING_UPFOLD",
        label="Whole-system meaning fold",
        purpose="incremental concept-tree maintenance over the repository meaning residue",
        missing_dependency="shared meaning_upfold tree and trigger receipt projection",
    )
    down_face, down_audit = _down_projection(atlas_updown)
    fold_face, fold_audit = _fold_projection(compact_fold)
    register_face, register_audit = _register_projection(
        register_dictionary, active_generation=active_register_generation,
    )

    core_states = {atlas_face["status"], meaning_face["status"], fold_face["status"]}
    if "REFUSED" in core_states:
        status = "REFUSED"
    elif "UPDATE-DUE" in core_states or "STALE" in core_states or "IN_FLIGHT" in core_states:
        status = "STALE"
    elif core_states == {"CURRENT"}:
        status = "CURRENT"
    else:
        status = "UNKNOWN"

    face = {
        "schema_version": SEMANTIC_JUNCTION_SCHEMA,
        "title": "Semantic junction",
        "status": status,
        "summary": (
            "Atlas operators, whole-system fold, and compact fold are shown as distinct evidence"
        ),
        "lineages": [atlas_face, meaning_face],
        "compact_fold": fold_face,
        "down_reconstruction": down_face,
        "register_dictionary": register_face,
        "interaction": {
            "resting_face": "human meaning, typed state, counts, residuals and continuations",
            "descent": "select any lineage, residual, omission or register entry to open Audit",
            "exact_handles": "Audit only",
            "reversible": True,
        },
        "producer_boundary": {
            "read_only": True,
            "second_truth_store": False,
            "producer_absence": "UNKNOWN",
            "authority_effect": "none",
        },
    }
    audit = {
        "visibility": "AUDIT_ONLY",
        "atlas_up_down": atlas_audit,
        "meaning_upfold": meaning_audit,
        "compact_fold": fold_audit,
        "down_reconstruction": down_audit,
        "register_dictionary": register_audit,
    }
    preimage = {**face, "audit": audit}
    audit["projection_handle"] = _handle(preimage)
    face["audit"] = audit
    return face


__all__ = [
    "ATLAS_LINEAGE_SCHEMA",
    "BOUNDED_DOWN_SCHEMA",
    "CANONICAL_UP_FAMILY_SCHEMA",
    "COMPACT_FOLD_SCHEMA",
    "EMBEDDING_HEALTH_SCHEMA",
    "MEANING_UPFOLD_SCHEMA",
    "OUTER_FOLD_VERIFICATION_SCHEMA",
    "REGISTER_DICTIONARY_SCHEMA",
    "REGISTER_EXPANSION_SCHEMA",
    "REGISTER_MEASUREMENT_SCHEMA",
    "SEMANTIC_JUNCTION_SCHEMA",
    "SEMANTIC_MEMORY_SCHEMA",
    "TYPED_DESCENT_COVERAGE_SCHEMA",
    "expand_register_opcode",
    "project_semantic_junction",
]
