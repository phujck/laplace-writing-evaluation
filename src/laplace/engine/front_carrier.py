"""Canonical, read-only model for the Aisthesis Front carrier.

This module is deliberately a pure join.  Callers supply already-read canonical
projections; this code neither opens a store nor owns an HTTP or write path.  The
returned model is immutable by identity: its complete semantic and shown preimages
are content addressed, and currentness is established only by rederiving both.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from laplace.engine.front_semantic_junction import embedding_health_side_ref

MODEL_SCHEMA = "laplace.aisthesis-front-model/1"
SHOWN_SCHEMA = "laplace.aisthesis-front-shown-state/1"
CURRENTNESS_SCHEMA = "laplace.aisthesis-front-currentness/1"
SEMANTIC_MEMORY_SCHEMA = "laplace.aisthesis-semantic-memory/1"
EMBEDDING_HEALTH_SCHEMA = "laplace.embedding-health/1"
BINDING_OBSERVATORY_SCHEMA = "laplace.aisthesis-binding-observatory/1"
FABRIC_OBSERVATORY_SCHEMA = "laplace.aisthesis-fabric-observatory/1"
SEMANTIC_JUNCTION_SCHEMA = "laplace.aisthesis-semantic-junction/1"
AUTHOR_RULING_SCHEMA = "laplace.aisthesis-author-ruling/1"

_CHECKPOINT_HANDLE = "sha256:c1fb0ded39bf37b595537aa1d0869a0659ba9001cbd58ed3f2834468ef0a1c62"
_FRONT_CONTRACT_HANDLE = "sha256:4bf3e15f1fb6278d25d4f921de859d12f009e95b792991abc3c0b48d111837e3"
_GRADES = ("far", "mid", "near", "audit")
_EXPOSITIONS = tuple(f"E{index}" for index in range(8))
_VIEWPORTS = ("wide", "medium", "narrow")
_SEMANTIC_SOURCE_CLASSES = ("devmap", "Atlas", "lifecycle", "Fabric", "custody", "seats")
_SEMANTIC_SOURCE_CLASS_GROUPS = {
    "devmap": ("development-work-map",),
    "Atlas": ("atlas-graph-objects", "atlas-typed-edges", "atlas-current-heads"),
    "lifecycle": ("lifecycle-recovery-publication",),
    "Fabric": ("fabric-exchange",),
    "custody": ("custody",),
    "seats": ("seat-profiles-goals-bindings",),
}
_FOG_CLASSES = (
    "COVERAGE", "DISCOVERY_MISS", "BOUNDARY_RESIDUAL", "STALE_UNKNOWN",
    "BUDGET_TRUNCATION", "AXIS_DISAGREEMENT",
)


@dataclass(frozen=True)
class RoomSpec:
    room_id: str
    label: str
    producer_key: str
    producer: str
    routes: tuple[str, ...]
    purpose: str


ROOMS: tuple[RoomSpec, ...] = (
    RoomSpec("Now", "Now", "now", "laplace.engine.wake.account + laplace.engine.wake.campaign",
             ("/front/apex",), "the present attention frontier"),
    RoomSpec("Programme", "Programme", "programme",
             "laplace.engine.wake.campaign + laplace.web.development_lens.project(programme)",
             ("/front/grid", "/front/development?lens=programme&format=json"),
             "programme, gates, causal field and next act"),
    RoomSpec("Work", "Work", "work",
             "laplace.manuscript.storyboard + laplace.manuscript.projection_viewer + laplace.manuscript.review_surface + laplace.web.pipeline_surface",
             ("/storyboard/plan", "/artefact/context", "/review/findings", "/pipeline/chain"),
             "manuscript, talk and artefact work in their own representations"),
    RoomSpec("Decision", "Decision", "decision", "author decision and walk projections",
             ("/front/apex", "/front/walk"), "exact questions and author rulings"),
    RoomSpec("Run", "Run", "run", "laplace.engine.trace + laplace.web.stream",
             ("/front/acts", "/front/trace", "/front/stream"),
             "live execution, receipts and banked outcomes"),
    RoomSpec("Conversation", "Conversation", "conversation",
             "laplace.web.conversation_serve + laplace.web.development_lens.project(continuity)",
             ("/front/serve", "/front/serve/body", "/front/serve/source",
              "/front/development?lens=continuity&format=json"),
             "author turn and exact Fabric continuity"),
    RoomSpec("Exposition", "Exposition", "exposition", "typed source and evidence descent",
             ("/front/record", "/front/field", "/front/serve/source"),
             "object-relative E0-E7 explanation and exact descent"),
    RoomSpec("Diagnostics", "Diagnostics", "diagnostics",
             "laplace.engine.sources.roster + front selftest + shared embedding health",
             ("/front/organ", "/front/sources", "/front/selftest"),
             "health, refusals, residuals and Semantic Memory"),
)


_PARITY_EVIDENCE = (
    {
        "capability": "v0 desk and present attention",
        "decision": "TRANSFORM",
        "source_node": "DESIGN_2026-08-20_the-conjugate-interface.md",
        "source_handle": "sha256:581afc693a221e12bbd82f37620593f79ab319933b19c42547ea084761197098",
        "producer": "laplace.engine.wake.account + laplace.engine.wake.campaign",
        "proof": "Now and Decision retain exact questions, jurisdiction and next act",
        "pass_predicate": "one open author fork remains exact from Now through Decision and ruling",
        "missing_implementation_proof": "fresh carrier integration and author walk",
    },
    {
        "capability": "v1 organ health",
        "decision": "SUBMERGE",
        "source_node": "CHARTER_2026-08-23_the-interface-seat.md",
        "source_handle": "sha256:e7b413d523bb11be26859dd9133b02dab3a1cc08b248b96e55cdd0c5c22acf35",
        "producer": "laplace.engine.sources.roster",
        "proof": "Diagnostics preserves source, age, absence and refusal independently",
        "pass_predicate": "an absent and an aged source remain separately visible without a green aggregate",
        "missing_implementation_proof": "Diagnostics carrier plant",
    },
    {
        "capability": "v2 campaign and apex",
        "decision": "TRANSFORM",
        "source_node": "DESIGN_2026-08-20_the-conjugate-interface.md",
        "source_handle": "sha256:581afc693a221e12bbd82f37620593f79ab319933b19c42547ea084761197098",
        "producer": "laplace.engine.wake.campaign + laplace.web.development_lens programme camera",
        "proof": "Programme retains stages, gates, causal field and omitted frontier",
        "pass_predicate": "one stage keeps identity through Far-to-Audit exact evidence descent",
        "missing_implementation_proof": "Programme organ carrier mount and visual plant",
    },
    {
        "capability": "v3 live run and interrupt",
        "decision": "TRANSFORM",
        "source_node": "DESIGN_2026-08-20_the-conjugate-interface.md",
        "source_handle": "sha256:581afc693a221e12bbd82f37620593f79ab319933b19c42547ea084761197098",
        "producer": "laplace.engine.trace + laplace.web.stream",
        "proof": "observation is live; interrupt remains UNKNOWN until an executor contract exists",
        "pass_predicate": "receipt-driven run motion is deterministic and an unbound interrupt refuses",
        "missing_implementation_proof": "authoritative interrupt executor and carrier plant",
    },
    {
        "capability": "v4 consumption and universal descent",
        "decision": "KEEP",
        "source_node": "contract/surfaces/front.yaml",
        "source_handle": _FRONT_CONTRACT_HANDLE,
        "producer": "laplace.engine.rows + typed source/body descent",
        "proof": "every visible claim reaches exact evidence or a typed omission",
        "pass_predicate": "every visible object reaches exact evidence or a hashed omission with continuation",
        "missing_implementation_proof": "carrier-wide descent coverage plant",
    },
    {
        "capability": "old Front Door composition",
        "decision": "RETIRE",
        "source_node": "src/laplace/web/front_door.html",
        "source_handle": "sha256:8f17e88dd16430bf5b7d2d2b20931007c73b7520c7f61dd7c8d585ce5f1b6e06",
        "producer": "none",
        "proof": "the carrier has one contextual room and no dependency on the historical shell",
        "pass_predicate": "new carrier contains no historical shell root, router or simultaneous panels",
        "missing_implementation_proof": "front route wiring and browser inspection",
    },
    {
        "capability": "Development mockup shell",
        "decision": "RETIRE",
        "source_node": "src/laplace/web/development_lens.py",
        "source_handle": "sha256:cd67d9fa2fd3c8bfe1888fb5f3ec0aa7de040894890db26ab94f0bbe8e23e64a",
        "producer": "development_lens projections only",
        "proof": "Programme and Continuity remain contextual organs, never carrier grammar",
        "pass_predicate": "both organs mount without importing or embedding the Development page shell",
        "missing_implementation_proof": "carrier integration dependency trace",
    },
    {
        "capability": "author conversation and Fabric custody",
        "decision": "TRANSFORM",
        "source_node": "src/laplace/web/conversation_serve.py",
        "source_handle": "sha256:94298d1880d5dad05ea379cf9e8a9939cea00607bdbf347b507237fd777f12ba",
        "producer": "conversation_serve.materialize_conversation_serve + development_lens continuity",
        "proof": "turn, delivery, reconstruction, acknowledgement, reply and authority remain distinct",
        "pass_predicate": "exact custody is acknowledgement-eligible; absent custody stays readable and ineligible",
        "missing_implementation_proof": "complete Fabric join and Conversation carrier plant",
    },
    {
        "capability": "manuscript reading, editing and exact source descent",
        "decision": "TRANSFORM",
        "source_node": "contract/surfaces/artefact.yaml",
        "source_handle": "sha256:71282bab69ba42ae71e0072e5ed22234e06fcd34dfa5d4fcd2dffbcae1ad4f30",
        "producer": "laplace.manuscript.projection_viewer + laplace.manuscript.review_surface",
        "proof": "Work preserves PDF, Synctex, findings, versions, compile, redline and restore",
        "pass_predicate": "PDF-to-source round trip and edit-to-new-version retain exact finding identity",
        "missing_implementation_proof": "Work carrier integration over the existing split producers",
    },
    {
        "capability": "manuscript conception, spine and incremental build",
        "decision": "KEEP",
        "source_node": "contract/surfaces/storyboard.yaml",
        "source_handle": "sha256:d9d9126a139ecdb31868b3b1c21d601f06cdf0e81dcbd7706ee8c6569649f62b",
        "producer": "laplace.manuscript.storyboard",
        "proof": "plan, spine, reconcile, restructure, incremental build, compile and converge remain organ-owned",
        "pass_predicate": "each verb remains separately armed, attributed and source-bearing inside Work",
        "missing_implementation_proof": "storyboard carrier mount and focused verb-boundary plant",
    },
    {
        "capability": "programme release and organ-owned run actions",
        "decision": "TRANSFORM",
        "source_node": "contract/surfaces/pipeline.yaml",
        "source_handle": "sha256:9f0dd2caceb57b5f82a380f5647f8e668bfff89807e7af42483febd9bc940d25",
        "producer": "laplace.web.pipeline_surface",
        "proof": "Programme summarizes and Run executes without proxying organ authority",
        "pass_predicate": "every next action names its organ, write, cost and PSU before arming",
        "missing_implementation_proof": "Programme/Run contextual carrier plant",
    },
    {
        "capability": "talk conception, motivated spine, staging and rendered verification",
        "decision": "TRANSFORM",
        "source_node": "src/laplace/pipeline/canon/skills/talk_smith/SKILL.md",
        "source_handle": "sha256:29ae5fa0144222a9a37056e2ef75a8db0d66ad552617e82ef72b490eea4b8336",
        "producer": "talk_smith + talk_ledger + deck_applet",
        "proof": "Work reserves task-appropriate talk representation; direct slide poking is not authority",
        "pass_predicate": "one deck binds source, audience, message, motivated spine and rendered verification receipts",
        "missing_implementation_proof": "live talk backend and carried deck render harness",
    },
    {
        "capability": "direct slide editing",
        "decision": "RETIRE",
        "source_node": "src/laplace/pipeline/canon/skills/talk_ledger/SKILL.md",
        "source_handle": "sha256:c93d3f8f12830c95be666122d274ed1e78f322b04f994d457860dfab6ce9cd2a",
        "producer": "none",
        "proof": "slides regenerate from spine, beats and assets",
        "pass_predicate": "no carrier control mutates slide layout directly and every regeneration retains provenance",
        "missing_implementation_proof": "talk backend and end-to-end regenerated-deck fixture",
    },
)


_CRUTCHES = (
    {
        "id": "CR-AIS-WALK-FEEDBACK-ATLAS-ROUTING",
        "owner": "Aisthesis + Ego",
        "retirement_predicate": (
            "one author walk-feedback act is durably banked, routed to the exact Atlas "
            "recipient, pulled and typed-reconstructed, and its visible completion receipt "
            "survives reload and idempotent retry without duplicate delivery"
        ),
    },
    {
        "id": "CR-AIS-STREAM-500MS",
        "owner": "Aisthesis",
        "retirement_predicate": (
            "p95 affected-event-to-rederived-CURRENT latency is <250ms under an "
            "adversarial gap plant with zero missed or duplicated affected events"
        ),
    },
    {
        "id": "CR-AIS-SHADOW-FOUR-PANE",
        "owner": "Aisthesis",
        "retirement_predicate": (
            "all eight contextual rooms pass deterministic 1536/768/375 and keyboard/Back "
            "plants with no historical-shell or Development-shell dependency"
        ),
    },
    {
        "id": "CR-AIS-CARRIER-HOST-ASSUMPTIONS",
        "owner": "Aisthesis",
        "retirement_predicate": (
            "the same model/shown receipts verify under the scanner host and an isolated "
            "carrier fixture at wide, medium and narrow viewports"
        ),
    },
    {
        "id": "CR-review-frontier-terminal-aggregate-without-authoritative-root",
        "owner": "inherited",
        "retirement_predicate": (
            "one authoritative review root binds the complete terminal-proof frontier "
            "with zero unrepresented terminal receipts"
        ),
    },
)


def canonical_bytes(value: Any) -> bytes:
    """Return the exact JSON preimage accepted by this model."""

    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_handle(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _copy_json(value: Any) -> Any:
    return json.loads(canonical_bytes(value))


def _handle_like(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("sha256:") and len(value) == 71


def _omission(code: str, boundary: str, reason: str, continuation: Any = None) -> dict[str, Any]:
    row = {
        "schema_version": "laplace.aisthesis-front-omission/1",
        "code": code,
        "boundary": boundary,
        "reason": reason,
        "continuation": continuation,
    }
    row["omission_handle"] = canonical_handle(row)
    return row


def _class_rows(coverage: Mapping[str, Any], omissions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    supplied = coverage.get("classes")
    rows_by_name: dict[str, Mapping[str, Any]] = {}
    if isinstance(supplied, Sequence) and not isinstance(supplied, (str, bytes)):
        for row in supplied:
            if isinstance(row, Mapping) and row.get("source_class") is not None:
                rows_by_name[str(row["source_class"]).casefold()] = row
    result = []
    for name in _SEMANTIC_SOURCE_CLASSES:
        exact_names = _SEMANTIC_SOURCE_CLASS_GROUPS.get(name, (name,))
        rows = [rows_by_name.get(exact.casefold()) for exact in exact_names]
        # Accept the earlier coarse spelling only when the exact producer-class
        # family is entirely absent.  This preserves old fixtures without letting
        # a partial real Atlas family masquerade as complete.
        if not any(rows):
            coarse = rows_by_name.get(name.casefold())
            rows = [coarse] if coarse is not None else rows
        if not rows or any(row is None for row in rows):
            omissions.append(_omission(
                "SEMANTIC_SOURCE_CLASS_ABSENT", f"Semantic Memory/{name}",
                f"laplace.embedding-health/1 has no complete {name} coverage family",
                "laplace.embedding-health/1.coverage.classes",
            ))
            result.append({
                "source_class": name, "count": None, "root": None,
                "admitted": None, "omitted": None, "reason": "UNKNOWN", "status": "UNKNOWN",
            })
            continue
        present = [row for row in rows if row is not None]
        counts = [row.get("count") for row in present]
        roots = [row.get("root") for row in present]
        omitted = [row.get("omitted") for row in present]
        admitted = [row.get("admitted") for row in present]
        complete = all((
            all(isinstance(count, int) and not isinstance(count, bool) and count > 0 for count in counts),
            all(_handle_like(root) for root in roots),
            all(value == 0 for value in omitted),
            all(value is True or (
                isinstance(value, int) and not isinstance(value, bool) and value > 0
            ) for value in admitted),
        ))
        face = {
            "source_class": name,
            "count": sum(counts) if complete else None,
            "root": canonical_handle(roots) if complete else None,
            "roots": roots,
            "admitted": sum(counts) if complete else None,
            "omitted": sum(omitted) if complete else None,
            "reason": [row.get("reason") for row in present],
        }
        face["status"] = "CURRENT" if complete else "UNKNOWN"
        result.append(face)
    return result


def _coverage_dimensions(coverage: Mapping[str, Any], omissions: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for label, keys in {
        "node": ("node_count", "nodes"),
        "vector": ("vector_count", "vectors"),
        "cluster": ("cluster_count", "clusters"),
    }.items():
        value = next((coverage.get(key) for key in keys if coverage.get(key) is not None), None)
        if isinstance(value, Mapping):
            count = value.get("count")
        else:
            count = value
        if not isinstance(count, int) or count < 0:
            omissions.append(_omission(
                "SEMANTIC_COVERAGE_DIMENSION_ABSENT", f"Semantic Memory/{label} coverage",
                f"the shared health object does not expose an exact {label} count",
                f"laplace.embedding-health/1.coverage.{keys[0]}",
            ))
            result[label] = {"status": "UNKNOWN", "count": None}
        else:
            result[label] = {"status": "CURRENT", "count": count}
    return result


def _consistent(value: Any) -> bool:
    if value is True:
        return True
    return isinstance(value, str) and value.upper() in {
        "CONSISTENT", "CURRENT", "PASS", "VERIFIED", "COHERENT",
    }


def semantic_memory(health: Mapping[str, Any] | None) -> dict[str, Any]:
    """Project exactly one stable ``laplace.embedding-health/1`` object.

    The authoritative health status is conserved separately from the carrier state.
    A claimed CURRENT is fail-closed unless the complete typed S→F proof is present.
    """

    omissions: list[dict[str, Any]] = []
    if health is None:
        omissions.append(_omission(
            "EMBEDDING_HEALTH_ABSENT", "Semantic Memory/shared health",
            "the canonical shared laplace.embedding-health/1 producer is not implemented",
            "laplace.embedding-health/1",
        ))
        health = {"schema_version": EMBEDDING_HEALTH_SCHEMA, "status": "ABSENT", "shared": True}
    else:
        health = _copy_json(health)

    schema_ok = health.get("schema_version") == EMBEDDING_HEALTH_SCHEMA
    shared_ok = health.get("shared") is True
    authority_ok = health.get("authority_effect") == "none"
    non_blocking_ok = health.get("non_blocking") is True
    side_ref = embedding_health_side_ref(health)
    declared_status = side_ref["declared_status"]
    if side_ref["status"] == "REFUSED" and declared_status not in {
        "CURRENT", "STALE", "IN_FLIGHT", "UPDATE-DUE", "UNKNOWN", "REFUSED", "ABSENT",
    }:
        omissions.append(_omission(
            "EMBEDDING_HEALTH_STATUS_REFUSED", "Semantic Memory/status",
            "the shared health object carries a status outside its exact enum",
            "laplace.embedding-health/1.status",
        ))
    for okay, code, field, reason in (
        (schema_ok, "EMBEDDING_HEALTH_SCHEMA_REFUSED", "schema_version", "wrong embedding-health schema"),
        (shared_ok, "EMBEDDING_HEALTH_NOT_SHARED", "shared", "health is not the one shared observation"),
        (authority_ok, "EMBEDDING_HEALTH_AUTHORITY_EFFECT", "authority_effect", "read health claims an authority effect"),
        (non_blocking_ok, "EMBEDDING_HEALTH_BLOCKING", "non_blocking", "health does not declare non-blocking observation"),
    ):
        if not okay:
            omissions.append(_omission(code, f"Semantic Memory/{field}", reason,
                                       f"laplace.embedding-health/1.{field}"))

    fold = health.get("fold") if isinstance(health.get("fold"), Mapping) else {}
    coverage = health.get("coverage") if isinstance(health.get("coverage"), Mapping) else {}
    artifacts = health.get("artifacts") if isinstance(health.get("artifacts"), Mapping) else {}
    runtime = health.get("runtime") if isinstance(health.get("runtime"), Mapping) else {}
    cadence = health.get("cadence") if isinstance(health.get("cadence"), Mapping) else {}
    consumption = health.get("consumption") if isinstance(health.get("consumption"), Mapping) else {}
    reachability = side_ref["reachability_witnesses"]
    baseline = health.get("baseline") if isinstance(health.get("baseline"), Mapping) else {}
    tree = side_ref.get("tree_fold") or {}
    if tree:
        coverage = {
            "node_count": tree.get("nodes"), "cluster_count": tree.get("clusters"),
            "vector_count": (tree.get("latest_receipt") or {}).get("total"),
        }

    source_classes = _class_rows(coverage, omissions)
    horizon = fold.get("semantic_horizon") if isinstance(fold.get("semantic_horizon"), Mapping) else {}
    receipt_for_dimensions = (
        health.get("latest_receipt")
        if isinstance(health.get("latest_receipt"), Mapping) else {}
    )
    embedding_counts = (
        receipt_for_dimensions.get("embedding_counts")
        if isinstance(receipt_for_dimensions.get("embedding_counts"), Mapping) else {}
    )
    coverage_for_dimensions = {
        **coverage,
        "node_count": coverage.get("node_count", horizon.get("nodes")),
        "vector_count": coverage.get("vector_count", embedding_counts.get("total")),
        "cluster_count": coverage.get("cluster_count", horizon.get("clusters")),
    }
    dimensions = _coverage_dimensions(coverage_for_dimensions, omissions)
    source_coordinate = side_ref["S"]
    fold_coordinate = side_ref["F"]
    observed_coordinate = side_ref["active_source"]

    forward = fold.get("forward_relation")
    receipt = tree.get("latest_receipt") if tree else health.get("latest_receipt")
    current_proof = side_ref["current_proof"]
    if declared_status == "CURRENT" and not current_proof:
        omissions.append(_omission(
            "FALSE_CURRENTNESS_REFUSED", "Semantic Memory/currentness",
            "CURRENT lacks the complete typed S-to-F, coherent artifact, coverage and receipt proof",
            fold.get("manifest_handle") or "laplace.embedding-health/1.fold.manifest_handle",
        ))
        effective_health_status = "REFUSED"
        state = "UNKNOWN"
    elif side_ref["status"] == "CURRENT":
        effective_health_status = "CURRENT"
        state = "CURRENT"
    elif side_ref["status"] == "UPDATE-DUE":
        effective_health_status = "UPDATE-DUE"
        state = (
            "IN_FLIGHT"
            if declared_status == "IN_FLIGHT" or bool(cadence.get("queued") or cadence.get("running"))
            else "STALE"
        )
    else:
        effective_health_status = side_ref["status"]
        state = "UNKNOWN"

    face = {
        "schema_version": SEMANTIC_MEMORY_SCHEMA,
        "source_schema": EMBEDDING_HEALTH_SCHEMA,
        "shared": bool(health.get("shared")),
        "health_status": effective_health_status,
        "state": state,
        "S": source_coordinate,
        "F": fold_coordinate,
        "active_source": observed_coordinate,
        "current_source": observed_coordinate,
        "semantic_ref": side_ref["semantic_ref"],
        "receipt_ref": side_ref["receipt_ref"],
        "source_tuple_status": side_ref["source_tuple_status"],
        "source_currentness": side_ref["source_currentness"],
        "forward_relation": forward,
        "semantic_horizon": fold.get("semantic_horizon"),
        "lag": {"commits": fold.get("lag_commits"), "status": state},
        "source_classes": source_classes,
        "coverage": {
            "required_complete": coverage.get("required_complete"),
            "handle": fold.get("coverage_handle"),
            **dimensions,
        },
        "artifacts": {
            "root": artifacts.get("root"),
            "count": artifacts.get("count"),
            "bytes": artifacts.get("bytes"),
            "manifest_handle": fold.get("manifest_handle"),
            "cache_sidecar_consistent": artifacts.get("cache_sidecar_consistent"),
        },
        "runtime": {
            "model": runtime.get("model"),
            "backend": runtime.get("backend"),
            "providers": runtime.get("providers"),
            "device": runtime.get("device"),
            "required_gpu": runtime.get("required_gpu"),
        },
        "latest_receipt": receipt,
        "semantic_reachability": reachability,
        "baseline": {
            "status": baseline.get("status"),
            "nodes": baseline.get("nodes"),
            "vectors": baseline.get("vectors"),
            "duration_seconds": baseline.get("duration_seconds"),
            "metric_redistilled": baseline.get("metric_redistilled"),
            "semantic_hello": baseline.get("semantic_hello"),
        },
        "queue_active_act": {
            "policy": cadence.get("policy"),
            "queue_key": cadence.get("queue_key"),
            "queued": cadence.get("queued"),
            "running": cadence.get("running"),
            "superseded_by": cadence.get("superseded_by"),
            "last_success": cadence.get("last_success"),
            "last_refusal": cadence.get("last_refusal"),
            "latency_seconds": cadence.get("latency_seconds"),
            "resource_effect": cadence.get("resource_effect"),
        },
        "consumption": {
            "last_wake": consumption.get("last_wake"),
            "last_descent": consumption.get("last_descent"),
        },
        "non_blocking": health.get("non_blocking"),
        "authority_effect": health.get("authority_effect"),
        "omissions": omissions,
        "exact_descent": {
            "health_schema": EMBEDDING_HEALTH_SCHEMA,
            "manifest_handle": fold.get("manifest_handle"),
            "coverage_handle": fold.get("coverage_handle"),
            "semantic_fold_receipt_handle": side_ref["fold_receipt_handle"],
            "semantic_fold_index_handle": side_ref["fold_index_handle"],
            "source_tuple": side_ref["source_tuple"],
            "latest_receipt": receipt,
            "contract_handle": _CHECKPOINT_HANDLE,
        },
    }
    face["semantic_memory_handle"] = canonical_handle(face)
    return face


def binding_observatory(observation: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep routing and enforced context injection mechanically distinct."""

    omissions: list[dict[str, Any]] = []
    if observation is None:
        observation = {}
        omissions.append(_omission(
            "BINDING_OBSERVATORY_ABSENT", "Binding Observatory/shared observation",
            "no canonical enforced-descent observation was supplied",
            "laplace.binding-observatory/1",
        ))
    else:
        observation = _copy_json(observation)
    selected = observation.get("selected") if isinstance(observation.get("selected"), Mapping) else {}
    routed = observation.get("routed_handles")
    if not isinstance(routed, Sequence) or isinstance(routed, (str, bytes)):
        routed = []
    routed = [str(value) for value in routed]
    link = observation.get("current_forward_link")
    if not isinstance(link, Mapping):
        link = {}
    regions = observation.get("regions") if isinstance(observation.get("regions"), Mapping) else {}
    fog = observation.get("fog")
    if not isinstance(fog, Sequence) or isinstance(fog, (str, bytes)):
        fog = []
    fog_rows = []
    for row in fog:
        if not isinstance(row, Mapping):
            continue
        kind = str(row.get("class") or "")
        if kind not in _FOG_CLASSES:
            omissions.append(_omission(
                "FOG_CLASS_REFUSED", "Binding Observatory/fog", "unknown semantic fog class",
                list(_FOG_CLASSES),
            ))
            continue
        face = {
            "class": kind,
            "count": row.get("count"),
            "digest": row.get("digest"),
            "continuation": row.get("continuation"),
        }
        if not isinstance(face["count"], int) or not _handle_like(face["digest"]):
            omissions.append(_omission(
                "FOG_RECEIPT_INCOMPLETE", f"Binding Observatory/fog/{kind}",
                "fog requires an exact count and digest", face["continuation"],
            ))
        fog_rows.append(face)
    descent = (
        observation.get("last_enforced_descent")
        if isinstance(observation.get("last_enforced_descent"), Mapping) else {}
    )
    receipt = descent.get("receipt")
    descended = bool(descent.get("time")) and _handle_like(receipt)
    injected = observation.get("injected_context_currentness")
    if descended:
        status = "DESCENDED"
    elif routed:
        status = "ROUTING-ONLY"
        omissions.append(_omission(
            "ENFORCED_DESCENT_RECEIPT_ABSENT", "Binding Observatory/context injection",
            "handles were routed but no successful enforced-descent receipt exists",
            routed,
        ))
    else:
        status = "UNKNOWN"
    if descended and str(injected or "").upper() != "CURRENT":
        omissions.append(_omission(
            "INJECTED_CONTEXT_CURRENTNESS_UNKNOWN", "Binding Observatory/injected context",
            "the descended context is not proven CURRENT", receipt,
        ))
    face = {
        "schema_version": BINDING_OBSERVATORY_SCHEMA,
        "status": status,
        "selected": {
            "seat": selected.get("seat"),
            "turn": selected.get("turn"),
            "task": selected.get("task"),
        },
        "routed_handles": routed,
        "current_forward_link": {
            "S": link.get("S"), "F": link.get("F"),
            "relation": link.get("relation"), "receipt": link.get("receipt"),
        },
        "regions": {
            "reached": list(regions.get("reached") or ()),
            "admitted": list(regions.get("admitted") or ()),
            "rejected": list(regions.get("rejected") or ()),
            "unvisited": list(regions.get("unvisited") or ()),
        },
        "depth": observation.get("depth"),
        "budget": observation.get("budget"),
        "fog": fog_rows,
        "last_enforced_descent": {"time": descent.get("time"), "receipt": receipt},
        "injected_context_currentness": injected if injected is not None else "UNKNOWN",
        "omissions": omissions,
        "authority_effect": "none",
    }
    face["binding_observatory_handle"] = canonical_handle(face)
    return face


def fabric_observatory(
    observation: Mapping[str, Any] | None,
    fallback: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Keep canonical delivery, watcher attention and direct fallback disjoint."""

    omissions: list[dict[str, Any]] = []
    observation = _copy_json(observation) if isinstance(observation, Mapping) else {}
    fallback = _copy_json(fallback) if isinstance(fallback, Mapping) else {}
    canonical = (
        observation.get("canonical")
        if isinstance(observation.get("canonical"), Mapping) else {}
    )
    phases = []
    for phase in (
        "send", "queued", "pull", "typed-reconstruction",
        "acknowledgement", "delivered", "reply",
    ):
        supplied = canonical.get(phase)
        if not isinstance(supplied, Mapping):
            supplied = {}
        state = str(supplied.get("state") or "UNKNOWN").upper()
        if state not in {"COMPLETE", "PENDING", "REFUSED", "INERT", "UNKNOWN"}:
            state = "REFUSED"
        phases.append({
            "phase": phase,
            "state": state,
            "event": supplied.get("event"),
            "receipt": supplied.get("receipt"),
            "latency_ms": supplied.get("latency_ms"),
        })
    if not canonical:
        omissions.append(_omission(
            "FABRIC_CANONICAL_OBSERVATION_ABSENT", "Fabric/canonical delivery",
            "no shared send-pull-reconstruct-ack-reply observation was supplied",
            "laplace.fabric-observatory/1",
        ))
    watcher = (
        observation.get("watcher")
        if isinstance(observation.get("watcher"), Mapping) else {}
    )
    watcher_face = {
        "state": str(watcher.get("state") or "UNKNOWN").upper(),
        "attention_tokens": watcher.get("attention_tokens"),
        "seat": watcher.get("seat"),
        "target_task": watcher.get("target_task"),
        "generation": watcher.get("generation"),
        "loaded_implementation": watcher.get("loaded_implementation"),
        "current_implementation": watcher.get("current_implementation"),
        "implementation_state": watcher.get("implementation_state") or "UNKNOWN",
        "delivery_claim": False,
    }
    fallback_active = bool(fallback.get("active"))
    provenance_complete = bool(fallback.get("message_ref") and fallback.get("body_digest"))
    fallback_face = {
        "mode": "EXTERNAL-DIRECT-COORDINATION",
        "state": "ACTIVE" if fallback_active else "INACTIVE",
        "transport": fallback.get("transport") or "UNKNOWN",
        "coordination_reference": fallback.get("coordination_reference"),
        "source_task_ref": fallback.get("source_task_ref"),
        "target_task_ref": fallback.get("target_task_ref"),
        "message_ref": fallback.get("message_ref"),
        "body_digest": fallback.get("body_digest"),
        "message_count": fallback.get("message_count") or "UNKNOWN",
        "custody_artifact_digest": fallback.get("custody_artifact_digest"),
        "provenance_state": "EXACT" if provenance_complete else "UNKNOWN",
        # Direct task traffic cannot acquire Fabric semantics by supplied assertion.
        "canonical_claims": {
            "send": False,
            "pull": False,
            "reconstruction": False,
            "acknowledgement": False,
            "reply": False,
        },
        "delivery_claim": False,
        "acknowledgement_claim": False,
        "retirement_predicate": fallback.get("retirement_predicate"),
    }
    if fallback_active and not provenance_complete:
        omissions.append(_omission(
            "DIRECT_COORDINATION_PROVENANCE_INCOMPLETE", "Fabric/direct fallback",
            "the direct task interval lacks a canonical message reference or body digest",
            "first canonical Fabric round trip after shared source freeze",
        ))
    metrics = (
        observation.get("metrics")
        if isinstance(observation.get("metrics"), Mapping) else {}
    )
    supplied_loss = (
        observation.get("loss_budget")
        if isinstance(observation.get("loss_budget"), Mapping) else {}
    )
    recoverable = list(supplied_loss.get("recoverable") or (
        "dropped watcher nudge", "delayed attention", "missed telemetry sample",
        "temporary interface unavailability",
    ))
    forbidden = list(supplied_loss.get("forbidden") or (
        "canonical message or body loss", "false acknowledgement", "duplicate action",
        "wrong-seat routing", "custody loss", "source or authority corruption",
    ))
    face = {
        "schema_version": FABRIC_OBSERVATORY_SCHEMA,
        "canonical": {
            "state": str(canonical.get("state") or "UNKNOWN").upper(),
            "phases": phases,
            "event_delta": canonical.get("event_delta"),
            "queue": canonical.get("queue"),
            "seat_mail": canonical.get("seat_mail"),
            "backpressure": canonical.get("backpressure"),
            "compaction_state": canonical.get("compaction_state") or "UNKNOWN",
            "binding_summary": canonical.get("binding_summary"),
        },
        "watcher_attention": watcher_face,
        "external_direct_fallback": fallback_face,
        "counts": {
            "batch": metrics.get("batch_count"),
            "process": metrics.get("process_count"),
            "replay": metrics.get("replay_count"),
            "consumed": metrics.get("consumed_count"),
            "inert": metrics.get("inert_count"),
        },
        "loss_budget": {
            "recoverable": recoverable,
            "forbidden": forbidden,
        },
        "fix_forward": {
            "state": observation.get("fix_forward_state") or "UNKNOWN",
            "next": observation.get("fix_forward_next"),
            "non_blocking": True,
        },
        "omissions": omissions,
        "authority_effect": "none",
    }
    face["fabric_observatory_handle"] = canonical_handle(face)
    return face


def _room_face(spec: RoomSpec, supplied: Any) -> dict[str, Any]:
    omissions: list[dict[str, Any]] = []
    if not isinstance(supplied, Mapping):
        payload = None
        status = "UNKNOWN"
        omissions.append(_omission(
            "ROOM_PRODUCER_ABSENT", f"room/{spec.room_id}",
            f"the canonical {spec.producer} projection was not supplied",
            list(spec.routes),
        ))
    else:
        payload = _copy_json(supplied)
        raw_status = str(payload.get("status") or payload.get("state") or "UNKNOWN").upper()
        status = raw_status if raw_status in {
            "CURRENT", "STALE", "IN_FLIGHT", "UNKNOWN", "REFUSED", "ABSENT",
        } else "UNKNOWN"
        if status == "UNKNOWN" and not (payload.get("status") or payload.get("state")):
            omissions.append(_omission(
                "ROOM_CURRENTNESS_ABSENT", f"room/{spec.room_id}",
                "the supplied projection has no typed currentness state",
                list(spec.routes),
            ))
    preimage = {
        "room_id": spec.room_id,
        "producer": spec.producer,
        "routes": list(spec.routes),
        "status": status,
        "payload": payload,
        "omissions": omissions,
    }
    return {
        **preimage,
        "label": spec.label,
        "purpose": spec.purpose,
        "room_handle": canonical_handle(preimage),
    }


def _joined_evidence_face(
    supplied: Mapping[str, Any] | None,
    *,
    schema: str,
    subject: str,
    handle_key: str,
    missing_dependency: str,
) -> dict[str, Any]:
    """Bind optional evidence bytes without trusting a producer-owned handle."""

    if supplied is None:
        preimage: dict[str, Any] = {
            "schema_version": schema,
            "status": "UNKNOWN",
            "human_summary": {
                "title": subject,
                "reason": "the shared read projection is unavailable",
            },
            "missing_dependency": missing_dependency,
            "read_only": True,
            "authority_effect": "none",
        }
    elif not isinstance(supplied, Mapping):
        preimage = {
            "schema_version": schema,
            "status": "REFUSED",
            "human_summary": {
                "title": subject,
                "reason": "the supplied read projection is not an object",
            },
            "observed_type": type(supplied).__name__,
            "read_only": True,
            "authority_effect": "none",
        }
    elif supplied.get("schema_version") != schema:
        preimage = {
            "schema_version": schema,
            "status": "REFUSED",
            "human_summary": {
                "title": subject,
                "reason": "the supplied read projection has the wrong schema",
            },
            "expected_schema": schema,
            "observed_schema": supplied.get("schema_version"),
            "read_only": True,
            "authority_effect": "none",
        }
    else:
        preimage = _copy_json(supplied)
        status = str(preimage.get("status") or "").upper()
        if status not in {
            "CURRENT", "UPDATE-DUE", "STALE", "IN_FLIGHT", "UNKNOWN", "REFUSED",
        }:
            preimage = {
                "schema_version": schema,
                "status": "REFUSED",
                "human_summary": {
                    "title": subject,
                    "reason": "the supplied read projection has no typed state",
                },
                "observed_status": supplied.get("status"),
                "read_only": True,
                "authority_effect": "none",
            }
        else:
            preimage["status"] = status
    preimage.pop(handle_key, None)
    preimage[handle_key] = canonical_handle(preimage)
    return preimage


def _validated_selection(
    *, room: str, lens: str | None, focus: str | None, edge: str | None, grade: str,
    exposition: str, viewport: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    omissions: list[dict[str, Any]] = []
    room_ids = {item.room_id for item in ROOMS}
    by_lens = {item.room_id.casefold(): item.room_id for item in ROOMS}
    raw_lens = lens if lens is not None else room.casefold()
    normalized_room = by_lens.get(str(raw_lens).casefold())
    if normalized_room is None:
        omissions.append(_omission("ROOM_REFUSED", "carrier/room", "unknown room", sorted(room_ids)))
        normalized_room = "Now"
    if grade not in _GRADES:
        omissions.append(_omission("GRADE_REFUSED", "carrier/grade", "unknown grade", list(_GRADES)))
        grade = "far"
    if exposition not in _EXPOSITIONS:
        omissions.append(_omission(
            "EXPOSITION_REFUSED", "carrier/exposition", "unknown exposition grade",
            list(_EXPOSITIONS),
        ))
        exposition = "E0"
    if viewport not in _VIEWPORTS:
        omissions.append(_omission(
            "VIEWPORT_REFUSED", "carrier/viewport", "unknown viewport class", list(_VIEWPORTS),
        ))
        viewport = "wide"
    return {
        "room": normalized_room, "focus": focus, "selected_edge": edge,
        "grade": grade, "exposition": exposition, "viewport": viewport,
        "raw_selection": {
            "lens": raw_lens, "focus": focus, "edge": edge, "grade": grade,
            "exposition": exposition, "viewport": viewport,
        },
    }, omissions


def project(
    *,
    producers: Mapping[str, Mapping[str, Any]] | None = None,
    embedding_health: Mapping[str, Any] | None = None,
    binding_observation: Mapping[str, Any] | None = None,
    fabric_observation: Mapping[str, Any] | None = None,
    direct_coordination: Mapping[str, Any] | None = None,
    coordination_profile: Mapping[str, Any] | None = None,
    semantic_junction: Mapping[str, Any] | None = None,
    author_ruling: Mapping[str, Any] | None = None,
    room: str = "Now",
    lens: str | None = None,
    focus: str | None = None,
    edge: str | None = None,
    grade: str = "far",
    exposition: str = "E0",
    viewport: str = "wide",
) -> dict[str, Any]:
    """Materialize one deterministic front model from supplied read projections."""

    producers = producers or {}
    selection, selection_omissions = _validated_selection(
        room=room, lens=lens, focus=focus, edge=edge, grade=grade,
        exposition=exposition, viewport=viewport,
    )
    rooms = [_room_face(spec, producers.get(spec.producer_key)) for spec in ROOMS]
    memory = semantic_memory(embedding_health)
    binding = binding_observatory(binding_observation)
    from laplace.engine import front_coordination

    fabric = fabric_observatory(fabric_observation, direct_coordination)
    coordination = front_coordination.project(coordination_profile)
    junction = _joined_evidence_face(
        semantic_junction,
        schema=SEMANTIC_JUNCTION_SCHEMA,
        subject="Semantic junction",
        handle_key="semantic_junction_handle",
        missing_dependency=(
            "shared verified Atlas UP/DOWN, meaning-upfold, compact-fold, bounded-DOWN, "
            "and register-dictionary projections"
        ),
    )
    ruling = _joined_evidence_face(
        author_ruling,
        schema=AUTHOR_RULING_SCHEMA,
        subject="Author ruling",
        handle_key="author_ruling_handle",
        missing_dependency="exact pinned author-ruling and publication-cut custody",
    )
    model_preimage = {
        "schema_version": MODEL_SCHEMA,
        "room_manifest": [
            {
                "room_id": spec.room_id, "label": spec.label,
                "producer": spec.producer, "routes": list(spec.routes),
                "purpose": spec.purpose,
            }
            for spec in ROOMS
        ],
        "rooms": rooms,
        "semantic_memory": memory,
        "binding_observatory": binding,
        "fabric_observatory": fabric,
        "coordination_phase": coordination,
        "semantic_junction": junction,
        "author_ruling": ruling,
        "parity_evidence": list(_PARITY_EVIDENCE),
        "owned_crutches": list(_CRUTCHES),
        "authority": {"read_only": True, "second_truth_store": "forbidden", "write_paths": []},
        "contract_handles": {
            "front": _FRONT_CONTRACT_HANDLE,
            "semantic_memory_nonregression": _CHECKPOINT_HANDLE,
        },
    }
    model_handle = canonical_handle(model_preimage)
    active = next(item for item in rooms if item["room_id"] == selection["room"])
    omitted = [*selection_omissions, *active["omissions"]]
    if selection["room"] == "Diagnostics":
        omitted.extend(memory["omissions"])
    shown_preimage = {
        "schema_version": SHOWN_SCHEMA,
        "model_handle": model_handle,
        **selection,
        "active_room_handle": active["room_handle"],
        "visible_handles": [
            active["room_handle"], memory["semantic_memory_handle"],
            binding["binding_observatory_handle"],
            fabric["fabric_observatory_handle"],
            coordination["coordination_phase_handle"],
            junction["semantic_junction_handle"],
            ruling["author_ruling_handle"],
        ],
        "omitted_handles": [row["omission_handle"] for row in omitted],
        "omitted_digest": canonical_handle([row["omission_handle"] for row in omitted]),
        "semantic_memory_state": memory["state"],
        "semantic_memory_handle": memory["semantic_memory_handle"],
        "binding_observatory_status": binding["status"],
        "binding_observatory_handle": binding["binding_observatory_handle"],
        "fabric_observatory_state": fabric["canonical"]["state"],
        "fabric_observatory_handle": fabric["fabric_observatory_handle"],
        "coordination_phase_status": coordination["status"],
        "coordination_phase_handle": coordination["coordination_phase_handle"],
        "semantic_junction_status": junction["status"],
        "semantic_junction_handle": junction["semantic_junction_handle"],
        "author_ruling_status": ruling["status"],
        "author_ruling_handle": ruling["author_ruling_handle"],
    }
    shown_handle = canonical_handle(shown_preimage)
    return {
        **model_preimage,
        "model_preimage": model_preimage,
        "model_handle": model_handle,
        "active_room": active,
        "selection_omissions": selection_omissions,
        "shown_state": {**shown_preimage, "shown_preimage": shown_preimage,
                        "shown_handle": shown_handle},
    }


def currentness(
    served: Mapping[str, Any],
    *,
    producers: Mapping[str, Mapping[str, Any]] | None = None,
    embedding_health: Mapping[str, Any] | None = None,
    binding_observation: Mapping[str, Any] | None = None,
    fabric_observation: Mapping[str, Any] | None = None,
    direct_coordination: Mapping[str, Any] | None = None,
    coordination_profile: Mapping[str, Any] | None = None,
    semantic_junction: Mapping[str, Any] | None = None,
    author_ruling: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Rederive, never echo, the complete model and shown preimages."""

    shown = served.get("shown_state") if isinstance(served, Mapping) else None
    preimage = shown.get("shown_preimage") if isinstance(shown, Mapping) else None
    if not isinstance(preimage, Mapping):
        return {
            "schema_version": CURRENTNESS_SCHEMA,
            "status": "REFUSED",
            "reason": "served model lacks the complete shown preimage",
            "served_model_handle": served.get("model_handle") if isinstance(served, Mapping) else None,
            "served_shown_handle": shown.get("shown_handle") if isinstance(shown, Mapping) else None,
            "rederived_model_handle": None,
            "rederived_shown_handle": None,
            "mismatches": ["shown_preimage"],
        }
    rederived = project(
        producers=producers,
        embedding_health=embedding_health,
        binding_observation=binding_observation,
        fabric_observation=fabric_observation,
        direct_coordination=direct_coordination,
        coordination_profile=coordination_profile,
        semantic_junction=semantic_junction,
        author_ruling=author_ruling,
        room=str(preimage.get("room") or "Now"),
        lens=(preimage.get("raw_selection") or {}).get("lens"),
        focus=preimage.get("focus"),
        edge=preimage.get("selected_edge"),
        grade=str(preimage.get("grade") or "far"),
        exposition=str(preimage.get("exposition") or "E0"),
        viewport=str(preimage.get("viewport") or "wide"),
    )
    served_model_handle = served.get("model_handle")
    served_shown_handle = shown.get("shown_handle")
    mismatches = []
    if served.get("model_preimage") != rederived["model_preimage"]:
        mismatches.append("model_preimage")
    if served_model_handle != rederived["model_handle"]:
        mismatches.append("model_handle")
    if preimage != rederived["shown_state"]["shown_preimage"]:
        mismatches.append("shown_preimage")
    if served_shown_handle != rederived["shown_state"]["shown_handle"]:
        mismatches.append("shown_handle")
    if mismatches:
        status = "STALE"
    elif rederived["semantic_memory"]["state"] == "CURRENT":
        status = "CURRENT"
    else:
        status = rederived["semantic_memory"]["state"]
    result = {
        "schema_version": CURRENTNESS_SCHEMA,
        "status": status,
        "served_model_handle": served_model_handle,
        "served_shown_handle": served_shown_handle,
        "rederived_model_handle": rederived["model_handle"],
        "rederived_shown_handle": rederived["shown_state"]["shown_handle"],
        "served_preimage": {"model": served.get("model_preimage"), "shown": preimage},
        "rederived_preimage": {
            "model": rederived["model_preimage"],
            "shown": rederived["shown_state"]["shown_preimage"],
        },
        "mismatches": mismatches,
        "semantic_memory_state": rederived["semantic_memory"]["state"],
        "semantic_junction_status": rederived["semantic_junction"]["status"],
        "author_ruling_status": rederived["author_ruling"]["status"],
    }
    result["currentness_handle"] = canonical_handle(result)
    return result


__all__ = [
    "BINDING_OBSERVATORY_SCHEMA", "CURRENTNESS_SCHEMA", "EMBEDDING_HEALTH_SCHEMA",
    "FABRIC_OBSERVATORY_SCHEMA", "SEMANTIC_JUNCTION_SCHEMA", "AUTHOR_RULING_SCHEMA",
    "MODEL_SCHEMA", "ROOMS",
    "SEMANTIC_MEMORY_SCHEMA", "SHOWN_SCHEMA", "canonical_bytes", "canonical_handle",
    "binding_observatory", "currentness", "fabric_observatory", "project", "semantic_memory",
]
