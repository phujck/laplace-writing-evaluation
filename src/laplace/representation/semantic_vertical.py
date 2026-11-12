"""One read-only semantic projection of Eigen's live operational system.

The source of truth remains Git plus the canonical Atlas.  This module emits only a
content-addressed routing projection: safe handles, typed relations, source-class roots and exact
descent instructions.  Fabric/profile bytes are used in-process for embeddings and are never
written into the projection or graded tree.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from laplace.representation.atlas_bridge import BlobMissing

from laplace.representation import atlas_bridge
from laplace.pipeline.canon import _tokenize

SOURCE_SCHEMA = "laplace.semantic-operational-source/1"
COVERAGE_SCHEMA = "laplace.semantic-source-coverage/1"
SOURCES_PATH = Path("semantic/operational_sources.jsonl")
COVERAGE_PATH = Path(".semantic_source_coverage.json")
DIRECT_COORDINATION_PATH = Path(
    "/home/phujck/SystemCheckpoints/2026-08-28/"
    "DIRECT-COORDINATION-FALLBACK-SEMANTIC-RECOVERY.json"
)
DIRECT_COORDINATION_HANDLE = (
    "sha256:d8af14c3b8703b2d271597f2b1b9764f6f523d9d86c189dc450225eb90cf8407"
)
HIERARCHY_DERIVATION_PATH = Path(
    "/home/phujck/SystemCheckpoints/2026-08-28/"
    "HIERARCHY-PHASE-CADENCE-DERIVATION.json"
)
HIERARCHY_DERIVATION_HANDLE = (
    "sha256:818e36cd1127a6f57c47202a4f5feb1dcc551b527e24cf946e469ba2e6575f5a"
)
REGULARIZATION_RULING_PATH = Path(
    "/home/phujck/SystemCheckpoints/2026-08-28/"
    "POST-PUBLICATION-SEMANTIC-LIFECYCLE-REGULARIZATION-RULING.json"
)
REGULARIZATION_RULING_HANDLE = (
    "sha256:f4402722879368e9448282b3045352677945daaf86c1fa77d2752fcf2cc5de29"
)
REGULARIZATION_DESIGN_PATH = Path(
    "/home/phujck/SystemCheckpoints/2026-08-28/"
    "SUPEREGO-DESIGN-SEMANTIC-LIFECYCLE-REGULARIZER.md"
)
REGULARIZATION_DESIGN_HANDLE = (
    "sha256:defd086c388e347c7ecfc081f8fa714d26cc11ad56e03c1f461a11634cec8f7f"
)

REQUIRED_CLASSES = (
    "development-work-map",
    "work-orders",
    "atlas-graph-objects",
    "atlas-typed-edges",
    "atlas-current-heads",
    "lifecycle-recovery-publication",
    "fabric-exchange",
    "custody",
    "seat-profiles-goals-bindings",
    "git-source-artifacts",
    "explicit-omissions-refusals",
)

_SOURCE_CLASS_SEMANTIC_SUMMARIES = {
    "seat-profiles-goals-bindings": (
        "live and retired seat binding lineage, provider generations, routing authority, "
        "and the current Ego, Aisthesis, and Superego function reconstruction profiles "
        "with complete shared goals"
    ),
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest(value: Any) -> str:
    return digest_bytes(canonical_bytes(value))


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _read_jsonl(path: Path) -> list[tuple[int, bytes, dict[str, Any]]]:
    rows: list[tuple[int, bytes, dict[str, Any]]] = []
    offset = 0
    with path.open("rb") as handle:
        for raw in handle:
            start = offset
            offset += len(raw)
            if not raw.strip():
                continue
            try:
                value = json.loads(raw)
            except ValueError:
                value = {
                    "record": "explicit-refusal",
                    "id": f"MALFORMED-{start}",
                    "status": "REFUSED",
                    "reason": "malformed canonical JSONL row",
                }
            if isinstance(value, dict):
                rows.append((start, raw, value))
    return rows


def _summary(value: Mapping[str, Any], *, cap: int = 720) -> str:
    fields: list[str] = []
    for key in (
        "id", "record", "kind", "status", "title", "what", "ask", "target", "verdict",
        "subject", "function", "seat_id", "message_type", "relation", "note", "reason",
    ):
        item = value.get(key)
        if item not in (None, "", [], {}):
            fields.append(f"{key}={item}")
    text = value.get("text")
    if isinstance(text, str) and text.strip():
        fields.append(text.strip())
    return " | ".join(fields)[:cap] or "content-addressed operational object"


def _external_custody(
    path: Path,
    expected_handle: str,
    *,
    json_object: bool = True,
) -> tuple[bytes, dict[str, Any]]:
    data = path.read_bytes()
    if digest_bytes(data) != expected_handle:
        raise RuntimeError(f"external custody artifact moved: {path}")
    if not atlas_bridge.custody_has(expected_handle):
        raise RuntimeError(
            f"external custody artifact is not reconstructably banked: {expected_handle}"
        )
    if not json_object:
        return data, {
            "schema_version": "laplace.external-text-custody/1",
            "content_handle": expected_handle,
            "bytes": len(data),
        }
    value = json.loads(data)
    if not isinstance(value, dict):
        raise RuntimeError(f"external custody artifact is not a JSON object: {path}")
    return data, value


def _blob_inventory(blob_root: Path) -> list[dict[str, Any]]:
    """Return a deterministic inventory of content-addressed custody blobs."""

    return sorted(
        (
            {"handle": "sha256:" + path.name, "bytes": path.stat().st_size}
            for path in blob_root.glob("*/*")
            if path.is_file() and len(path.name) == 64
        ),
        key=lambda item: item["handle"],
    )


def _historical_unavailable_embedding(
    message_id: str, body_handle: str
) -> bytes | None:
    """Render an author-ratified missing legacy body as typed semantic fog.

    The bytes are never reconstructed or invented.  Only the exact frozen legacy set may
    cross this boundary; every other missing live body remains a hard refusal.
    """

    declaration, _raw, declaration_sha256 = (
        atlas_bridge._load_runtime_custody_residual_declaration(
            atlas_bridge.RUNTIME_CUSTODY_RESIDUAL_DECLARATION
        )
    )
    for row in declaration["historical_unavailable"]:
        if row["message_id"] == message_id and row["body_handle"] == body_handle:
            return canonical_bytes(
                {
                    "schema_version": "laplace.semantic-historical-unavailable-body/1",
                    "message_id": message_id,
                    "body_handle": body_handle,
                    "state": "REFUSED",
                    "reason": row["reason"],
                    "terminal_event_id": row["terminal_event_id"],
                    "declaration_sha256": declaration_sha256,
                    "content_available": False,
                    "continuation": (
                        "atlas/migrations/"
                        "runtime-message-body-residuals-20260827.json"
                    ),
                }
            )
    return None


def _relation_rows(edges: Mapping[str, Mapping[str, Any]]) -> tuple[
    dict[str, list[dict[str, str]]], dict[str, int]
]:
    outgoing: dict[str, list[dict[str, str]]] = defaultdict(list)
    relations: Counter[str] = Counter()
    for edge_id, edge in sorted(edges.items()):
        relation = str(edge.get("relation") or "related")
        source = str(edge.get("source_object_id") or "")
        target = str(edge.get("target_object_id") or "")
        if source and target:
            outgoing[source].append(
                {"edge_id": edge_id, "relation": relation, "target": target}
            )
            relations[relation] += 1
    return outgoing, dict(sorted(relations.items()))


def _profile_handle_rows(profile_handles: Mapping[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "schema_version": SOURCE_SCHEMA,
            "id": f"OP-PROFILE-{function.upper()}",
            "source_classes": ["seat-profiles-goals-bindings"],
            "canonical_handle": handle,
            "content_handle": handle,
            "kind": "seat-reconstruction-profile",
            "semantic_summary": (
                f"current {function} seat reconstruction profile and complete shared goal context"
            ),
            "semantic_parent": "operational://seat-profiles-goals-bindings",
            "exact_descent": {"kind": "atlas-custody", "reference": handle, "source": ""},
            "relations": [],
        }
        for function, handle in sorted(profile_handles.items())
    ]


def _synthetic_class_rows(class_receipts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [{
        "schema_version": SOURCE_SCHEMA,
        "id": "operational://root",
        "source_classes": list(REQUIRED_CLASSES),
        "canonical_handle": digest(list(class_receipts)),
        "content_handle": digest(list(class_receipts)),
        "kind": "operational-semantic-root",
        "semantic_summary": "Eigen operational system: exact source classes, fibres, authority history and current work",
        "semantic_parent": None,
        "exact_descent": {
            "kind": "ledger-row",
            "reference": "operational://root",
            "source": "semantic_operational_sources",
        },
        "relations": [],
    }]
    for receipt in class_receipts:
        source_class = str(receipt["source_class"])
        class_meaning = _SOURCE_CLASS_SEMANTIC_SUMMARIES.get(
            source_class, source_class
        )
        rows.append({
            "schema_version": SOURCE_SCHEMA,
            "id": f"operational://{source_class}",
            "source_classes": [source_class],
            "canonical_handle": receipt["root"],
            "content_handle": receipt["root"],
            "kind": "operational-source-class",
            "semantic_summary": (
                f"{class_meaning}: {receipt['count']} admitted canonical items; "
                f"omitted={receipt['omitted']} reason={receipt['reason']}"
            ),
            "semantic_parent": "operational://root",
            "exact_descent": {
                "kind": "ledger-row",
                "reference": f"operational://{source_class}",
                "source": "semantic_operational_sources",
            },
            "relations": [],
        })
    return rows


def capture(
    repo_root: Path | str,
    *,
    profile_handles: Mapping[str, str],
    source_tuple: Mapping[str, Any],
    sources_path: Path | str | None = None,
    coverage_path: Path | str | None = None,
    source_kernel_inputs: list[dict] | None = None,
) -> dict[str, Any]:
    """Capture one stable, content-addressed operational frontier without authority writes."""

    root = Path(repo_root).resolve()
    from laplace.engine import source_kernel_input as source_kernel
    selected_inputs = source_kernel.coverage_inputs(root) if source_kernel_inputs is None else source_kernel_inputs
    selected_source = source_kernel.input_frame(root, selected_inputs)
    if source_tuple.get('source_kernel', {}).get('basis') != selected_source['basis'] and selected_inputs:
        raise RuntimeError('Selected Source inputs differ from the admitted source tuple')
    source_file = root / (Path(sources_path) if sources_path else SOURCES_PATH)
    coverage_file = root / (Path(coverage_path) if coverage_path else COVERAGE_PATH)
    if _git(root, "status", "--porcelain"):
        raise RuntimeError("semantic source capture requires a clean committed source coordinate")

    head = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    carried_source_tuple = source_tuple.get("source_tuple_handle")
    normalized_source_tuple = {
        key: value for key, value in source_tuple.items() if key != "source_tuple_handle"
    }
    if (
        source_tuple.get("schema_version") not in {
            "laplace.semantic-fold-source-tuple/1",
            "laplace.semantic-fold-source-tuple/2",
        }
        or digest(normalized_source_tuple) != carried_source_tuple
        or source_tuple.get("git") != {"commit": head, "tree": tree}
        or source_tuple.get("profile_handles") != dict(sorted(profile_handles.items()))
    ):
        raise RuntimeError("semantic source tuple is malformed or moved from Git/profile input")
    before_drift = atlas_bridge.drift_token()
    if before_drift != (source_tuple.get("atlas") or {}).get("drift_token"):
        raise RuntimeError("Atlas moved before semantic source capture")
    provider = atlas_bridge.snapshot()["provider"]
    before = (int(provider["event_count"]), str(provider["head_event_id"]))
    events = [event.to_dict() for event in atlas_bridge._read_store().events()]
    frontier = atlas_bridge.development_review_frontier(terminal_cap=64)
    after_drift = atlas_bridge.drift_token()
    if before_drift != after_drift:
        raise RuntimeError(
            f"Atlas moved during semantic source capture: {before_drift!r} -> {after_drift!r}"
        )

    graph = provider["graph"]
    objects = graph["objects"]
    edges = graph["edges"]
    outgoing, relation_counts = _relation_rows(edges)
    rows_by_id: dict[str, dict[str, Any]] = {}
    direct_bytes, direct_coordination = _external_custody(
        DIRECT_COORDINATION_PATH, DIRECT_COORDINATION_HANDLE
    )
    hierarchy_bytes, hierarchy_derivation = _external_custody(
        HIERARCHY_DERIVATION_PATH, HIERARCHY_DERIVATION_HANDLE
    )
    ruling_bytes, regularization_ruling = _external_custody(
        REGULARIZATION_RULING_PATH, REGULARIZATION_RULING_HANDLE
    )
    design_bytes, _regularization_design = _external_custody(
        REGULARIZATION_DESIGN_PATH,
        REGULARIZATION_DESIGN_HANDLE,
        json_object=False,
    )

    # Every canonical graph object is one leaf.  The complete edge set is carried as typed outgoing
    # relations and independently rooted below; authority remains in Atlas.
    for object_id, value in sorted(objects.items()):
        attributes = value.get("attributes") or {}
        residual = value.get("residual") or {}
        semantic_summary = _summary({
            "id": object_id,
            "kind": value.get("kind"),
            "status": residual.get("status"),
            "subject": attributes.get("subject") or attributes.get("message_id"),
            "note": residual.get("note"),
            "reason": attributes.get("reason"),
        })
        axis_key = digest({
            "assumption": value.get("assumption"),
            "fibre": value.get("fibre"),
        }).removeprefix("sha256:")[:12]
        rows_by_id[object_id] = {
            "schema_version": SOURCE_SCHEMA,
            "id": object_id,
            "source_classes": ["atlas-graph-objects", "lifecycle-recovery-publication"],
            "canonical_handle": object_id,
            "content_handle": digest(value),
            "kind": str(value.get("kind") or "atlas-object"),
            "semantic_summary": semantic_summary,
            "semantic_parent": f"operational://atlas-axis/{axis_key}",
            "axis": {
                "assumption": value.get("assumption"),
                "fibre": value.get("fibre"),
                "grade_contract_id": value.get("grade_contract_id"),
                "grade_coordinate": value.get("grade_coordinate"),
            },
            "exact_descent": {"kind": "atlas-object", "reference": object_id, "source": ""},
            "relations": outgoing.get(object_id, []),
        }
        axis_id = f"operational://atlas-axis/{axis_key}"
        rows_by_id.setdefault(axis_id, {
            "schema_version": SOURCE_SCHEMA,
            "id": axis_id,
            "source_classes": ["atlas-graph-objects"],
            "canonical_handle": digest({"axis": rows_by_id[object_id]["axis"]}),
            "content_handle": digest({"axis": rows_by_id[object_id]["axis"]}),
            "kind": "atlas-assumption-fibre-axis",
            "semantic_summary": _summary(rows_by_id[object_id]["axis"]),
            "semantic_parent": "operational://atlas-graph-objects",
            "exact_descent": {
                "kind": "ledger-row", "reference": f"OP-AXIS-{axis_key}",
                "source": "semantic_operational_sources",
            },
            "relations": [],
        })

    messages = provider.get("messages") or {}
    for message_id, state in sorted(messages.items()):
        message = state.get("message") or {}
        row = rows_by_id.setdefault(message_id, {
            "schema_version": SOURCE_SCHEMA,
            "id": message_id,
            "source_classes": [],
            "canonical_handle": message_id,
            "content_handle": str(message.get("body_handle") or ""),
            "kind": "fabric-message",
            "semantic_summary": "",
            "semantic_parent": "operational://fabric-exchange",
            "exact_descent": {"kind": "fabric-message", "reference": message_id, "source": ""},
            "relations": [],
        })
        row["source_classes"] = sorted(set(row["source_classes"]) | {"fabric-exchange"})
        row["body_handle"] = message.get("body_handle")
        row["semantic_parent"] = "operational://fabric-exchange"
        row["semantic_summary"] = _summary({
            "id": message_id,
            "message_type": message.get("message_type"),
            "status": state.get("status"),
            "subject": f"{message.get('sender_seat_id')}->{message.get('recipient_seat_id')}",
            "note": state.get("supersession_note"),
        })
        row["exact_descent"] = {"kind": "fabric-message", "reference": message_id, "source": ""}

    work_path = root / "corpus_friction" / "work_orders.jsonl"
    work_rows = _read_jsonl(work_path)
    seen_ids: Counter[str] = Counter(str(value.get("id") or "") for _, _, value in work_rows)
    for index, (offset, raw, value) in enumerate(work_rows):
        raw_id = str(value.get("id") or f"OP-WORK-{index:05d}")
        row_id = raw_id if seen_ids[raw_id] == 1 else f"OP-WORK-{index:05d}-{raw_id}"
        rows_by_id[row_id] = {
            "schema_version": SOURCE_SCHEMA,
            "id": row_id,
            "source_classes": ["work-orders"],
            "canonical_handle": raw_id,
            "content_handle": digest_bytes(raw),
            "kind": str(value.get("record") or value.get("kind") or "work-order-row"),
            "semantic_summary": _summary(value),
            "semantic_parent": "operational://work-orders",
            "exact_descent": {
                "kind": "ledger-row", "reference": raw_id, "source": "work_orders",
            } if row_id == raw_id else {
                "kind": "ledger-row", "reference": row_id,
                "source": "semantic_operational_sources",
            },
            "canonical_source": "corpus_friction/work_orders.jsonl",
            "byte_offset": offset,
            "byte_length": len(raw),
            "relations": [],
        }

    rows_by_id["OP-DEVELOPMENT-WORK-MAP"] = {
        "schema_version": SOURCE_SCHEMA,
        "id": "OP-DEVELOPMENT-WORK-MAP",
        "source_classes": ["development-work-map"],
        "canonical_handle": digest(frontier),
        "content_handle": digest(frontier),
        "kind": "development-work-map-frontier",
        "semantic_summary": (
            f"canonical development work frontier at cursor {frontier.get('cursor')}; "
            f"open={frontier.get('projection_open_count')} terminal={frontier.get('projection_terminal_count')}"
        ),
        "semantic_parent": "operational://development-work-map",
        "exact_descent": {
            "kind": "ledger-row", "reference": "OP-DEVELOPMENT-WORK-MAP",
            "source": "semantic_operational_sources",
        },
        "relations": [],
        "embedding_payload": frontier,
    }

    tracked = []
    for line in _git(root, "ls-files", "-s").splitlines():
        fields = line.split(None, 3)
        if len(fields) == 4:
            tracked.append({"mode": fields[0], "object": fields[1], "stage": fields[2], "path": fields[3]})
    git_projection = {"commit": head, "tree": tree, "tracked": tracked}
    rows_by_id["OP-GIT-SOURCE-COORDINATE"] = {
        "schema_version": SOURCE_SCHEMA,
        "id": "OP-GIT-SOURCE-COORDINATE",
        "source_classes": ["git-source-artifacts"],
        "canonical_handle": digest(git_projection),
        "content_handle": digest(git_projection),
        "kind": "git-source-coordinate",
        "semantic_summary": f"current committed source {head} tree {tree} with {len(tracked)} tracked artefacts",
        "semantic_parent": "operational://git-source-artifacts",
        "exact_descent": {
            "kind": "ledger-row", "reference": "OP-GIT-SOURCE-COORDINATE",
            "source": "semantic_operational_sources",
        },
        "relations": [],
        "embedding_payload": {"commit": head, "tree": tree, "recent": _git(root, "log", "-8", "--format=%H %s").splitlines()},
    }

    blob_root = atlas_bridge.store_root() / "blobs"
    blob_inventory = _blob_inventory(blob_root)
    rows_by_id["OP-CUSTODY-INVENTORY"] = {
        "schema_version": SOURCE_SCHEMA,
        "id": "OP-CUSTODY-INVENTORY",
        "source_classes": ["custody"],
        "canonical_handle": digest(blob_inventory),
        "content_handle": digest(blob_inventory),
        "kind": "atlas-custody-inventory",
        "semantic_summary": f"Atlas content-addressed custody inventory: {len(blob_inventory)} exact blobs",
        "semantic_parent": "operational://custody",
        "exact_descent": {
            "kind": "ledger-row", "reference": "OP-CUSTODY-INVENTORY",
            "source": "semantic_operational_sources",
        },
        "relations": [],
    }

    for row in _profile_handle_rows(profile_handles):
        rows_by_id[row["id"]] = row

    refused_events = [event for event in events if (
        str(event.get("validity", "")).lower() == "refused"
        or str((event.get("residual") or {}).get("status", "")).lower() in {"unknown", "exceeds_bound"}
        or any(token in str(event.get("kind", "")) for token in ("supersed", "expired", "rollback"))
    )]
    refused_messages = [
        message_id for message_id, value in messages.items()
        if str(value.get("status", "")).lower() in {"refused", "quarantined", "superseded", "expired"}
    ]
    refusal_projection = {
        "event_ids": [event["event_id"] for event in refused_events],
        "message_ids": refused_messages,
    }
    rows_by_id["OP-EXPLICIT-OMISSIONS-REFUSALS"] = {
        "schema_version": SOURCE_SCHEMA,
        "id": "OP-EXPLICIT-OMISSIONS-REFUSALS",
        "source_classes": ["explicit-omissions-refusals"],
        "canonical_handle": digest(refusal_projection),
        "content_handle": digest(refusal_projection),
        "kind": "explicit-omission-refusal-frontier",
        "semantic_summary": f"explicit refusals/residuals: {len(refused_events)} events and {len(refused_messages)} messages",
        "semantic_parent": "operational://explicit-omissions-refusals",
        "exact_descent": {
            "kind": "ledger-row", "reference": "OP-EXPLICIT-OMISSIONS-REFUSALS",
            "source": "semantic_operational_sources",
        },
        "relations": [],
        "embedding_payload": refusal_projection,
    }
    rows_by_id["OP-EXTERNAL-DIRECT-COORDINATION"] = {
        "schema_version": SOURCE_SCHEMA,
        "id": "OP-EXTERNAL-DIRECT-COORDINATION",
        "source_classes": ["fabric-exchange", "custody", "explicit-omissions-refusals"],
        "canonical_handle": DIRECT_COORDINATION_HANDLE,
        "content_handle": DIRECT_COORDINATION_HANDLE,
        "external_custody_handle": DIRECT_COORDINATION_HANDLE,
        "kind": "external-direct-coordination-custody",
        "semantic_summary": (
            "honest direct task coordination fallback; no historical Fabric send, pull, "
            "reconstruction, acknowledgement, or reply claim; retire after exact canonical round trip"
        ),
        "semantic_parent": "operational://fabric-exchange",
        "exact_descent": {
            "kind": "atlas-custody", "reference": DIRECT_COORDINATION_HANDLE, "source": ""
        },
        "relations": [{
            "relation": "awaits-canonical-fabric-round-trip",
            "target": "operational://fabric-exchange",
        }],
    }
    rows_by_id["OP-HIERARCHY-PHASE-CADENCE"] = {
        "schema_version": SOURCE_SCHEMA,
        "id": "OP-HIERARCHY-PHASE-CADENCE",
        "source_classes": ["seat-profiles-goals-bindings", "explicit-omissions-refusals"],
        "canonical_handle": HIERARCHY_DERIVATION_HANDLE,
        "content_handle": HIERARCHY_DERIVATION_HANDLE,
        "external_custody_handle": HIERARCHY_DERIVATION_HANDLE,
        "kind": "fresh-hierarchy-phase-operating-derivation",
        "semantic_summary": (
            "minimum-sufficient hierarchy; measured protective yield; local fix-forward; "
            "review synthesis; irreversible-boundary concentration; historical source quarantined"
        ),
        "semantic_parent": "operational://seat-profiles-goals-bindings",
        "exact_descent": {
            "kind": "atlas-custody", "reference": HIERARCHY_DERIVATION_HANDLE, "source": ""
        },
        "relations": [{
            "relation": "controls-successor-fold-cadence",
            "target": "operational://root",
        }],
    }
    rows_by_id["OP-SEMANTIC-LIFECYCLE-REGULARIZATION-RULING"] = {
        "schema_version": SOURCE_SCHEMA,
        "id": "OP-SEMANTIC-LIFECYCLE-REGULARIZATION-RULING",
        "source_classes": [
            "development-work-map", "work-orders", "seat-profiles-goals-bindings",
            "explicit-omissions-refusals",
        ],
        "canonical_handle": REGULARIZATION_RULING_HANDLE,
        "content_handle": REGULARIZATION_RULING_HANDLE,
        "external_custody_handle": REGULARIZATION_RULING_HANDLE,
        "kind": "author-development-ruling",
        "semantic_summary": (
            "next publication is the compact semantic lifecycle regularizer; exact S-to-F, "
            "UP/DOWN batch receipt, shared admission, outside-view cost telemetry, smallest "
            "fix-forward, and retirement of low-yield coordination layers"
        ),
        "semantic_parent": "operational://development-work-map",
        "exact_descent": {
            "kind": "atlas-custody", "reference": REGULARIZATION_RULING_HANDLE,
            "source": "",
        },
        "relations": [
            {"relation": "governs-successor-fold", "target": "operational://root"},
            {"relation": "governs-function-profiles", "target": "operational://seat-profiles-goals-bindings"},
        ],
    }
    rows_by_id["OP-SEMANTIC-LIFECYCLE-REGULARIZER-DESIGN"] = {
        "schema_version": SOURCE_SCHEMA,
        "id": "OP-SEMANTIC-LIFECYCLE-REGULARIZER-DESIGN",
        "source_classes": ["development-work-map", "work-orders"],
        "canonical_handle": REGULARIZATION_DESIGN_HANDLE,
        "content_handle": REGULARIZATION_DESIGN_HANDLE,
        "external_custody_handle": REGULARIZATION_DESIGN_HANDLE,
        "kind": "superego-implementation-design",
        "semantic_summary": (
            "source-complete S to compact UP/DOWN F, total typed semantic-fold-object descent, "
            "CURRENT zero-deferred health before profile seal, single admission, and outside-view cadence"
        ),
        "semantic_parent": "OP-SEMANTIC-LIFECYCLE-REGULARIZATION-RULING",
        "exact_descent": {
            "kind": "atlas-custody", "reference": REGULARIZATION_DESIGN_HANDLE,
            "source": "",
        },
        "relations": [{
            "relation": "implements-author-ruling",
            "target": "OP-SEMANTIC-LIFECYCLE-REGULARIZATION-RULING",
        }],
    }

    event_kinds = Counter(str(event.get("kind")) for event in events)
    class_values: dict[str, Any] = {
        "development-work-map": frontier,
        "work-orders": {
            "canonical_rows": [value for _, _, value in work_rows],
            "active_author_ruling": REGULARIZATION_RULING_HANDLE,
            "implementation_design": REGULARIZATION_DESIGN_HANDLE,
        },
        "atlas-graph-objects": objects,
        "atlas-typed-edges": edges,
        "atlas-current-heads": {
            "event_count": provider["event_count"], "head_event_id": provider["head_event_id"],
            "corpus_heads": provider.get("corpus_heads"), "active_context": provider.get("active_context"),
        },
        "lifecycle-recovery-publication": {
            "events": [event for event in events if any(token in str(event.get("kind")) for token in (
                "lifecycle", "seat.", "region.", "revision", "rollback"
            ))],
            "event_kinds": dict(sorted(event_kinds.items())),
        },
        "fabric-exchange": {
            "canonical_messages": messages,
            "external_direct_coordination": {
                "content_handle": DIRECT_COORDINATION_HANDLE,
                "status": direct_coordination.get("status"),
                "no_fabric_claim": not any(
                    direct_coordination.get("transport", {}).get(key) is True
                    for key in (
                        "canonical_fabric_send_claim",
                        "canonical_fabric_pull_claim",
                        "canonical_fabric_reconstruction_claim",
                        "canonical_fabric_acknowledgement_claim",
                        "canonical_fabric_reply_claim",
                    )
                ),
            },
        },
        "custody": blob_inventory,
        "seat-profiles-goals-bindings": {
            "profiles": dict(sorted(profile_handles.items())),
            "occupancy": provider.get("seat_occupancy"),
            "lineage": provider.get("seat_binding_lineage"),
            "hierarchy_phase_controller": {
                "content_handle": HIERARCHY_DERIVATION_HANDLE,
                "status": hierarchy_derivation.get("status"),
            },
            "semantic_lifecycle_regularization": {
                "content_handle": REGULARIZATION_RULING_HANDLE,
                "status": regularization_ruling.get("status"),
                "outside_view_acceptance": regularization_ruling.get(
                    "outside_view_acceptance"
                ),
            },
        },
        "git-source-artifacts": git_projection,
        "explicit-omissions-refusals": {
            **refusal_projection,
            "direct_fallback": DIRECT_COORDINATION_HANDLE,
            "quarantined_historical_hierarchy_source": (
                hierarchy_derivation.get("source_qualification") or {}
            ).get("historical_status"),
        },
    }
    class_receipts = []
    for source_class in REQUIRED_CLASSES:
        value = class_values[source_class]
        if isinstance(value, Mapping):
            count = len(value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            count = len(value)
        else:
            count = 1
        class_receipts.append({
            "source_class": source_class,
            "count": count,
            "root": digest(value),
            "admitted": True,
            "omitted": 0,
            "reason": "complete canonical projection admitted",
        })

    for row in _synthetic_class_rows(class_receipts):
        # Parent links in every operational leaf point at these exact ids.  Keeping the ids
        # identical in the persisted projection prevents a syntactically valid but unreachable
        # class/root hierarchy; callers descend them through the explicitly typed ledger source.
        rows_by_id[row["id"]] = row

    rows = sorted(rows_by_id.values(), key=lambda item: str(item["id"]))
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_bytes = b"".join(canonical_bytes(row) + b"\n" for row in rows)
    source_file.write_bytes(source_bytes)
    coverage = {
        "schema_version": COVERAGE_SCHEMA,
        "source_git": {"commit": head, "tree": tree},
        "source_kernel_inputs": selected_inputs,
        "source_kernel": {"basis": selected_source["basis"], "receipts": selected_source["receipts"]},
        "source_tuple": dict(source_tuple),
        "source_tuple_handle": carried_source_tuple,
        "atlas": {
            "cursor": before[0], "head_event_id": before[1],
            "graph_object_root": digest(objects), "graph_edge_root": digest(edges),
            "event_root": digest(events), "message_root": digest(messages),
        },
        "profile_handles": dict(sorted(profile_handles.items())),
        "seat_generations": {
            seat_id: (value or {}).get("current_provider_identity_generation")
            for seat_id, value in sorted((provider.get("seat_occupancy") or {}).items())
            if isinstance(value, Mapping)
        },
        "external_custody": {
            "direct_coordination": {
                "path": str(DIRECT_COORDINATION_PATH),
                "content_handle": DIRECT_COORDINATION_HANDLE,
                "bytes": len(direct_bytes),
            },
            "hierarchy_phase_derivation": {
                "path": str(HIERARCHY_DERIVATION_PATH),
                "content_handle": HIERARCHY_DERIVATION_HANDLE,
                "bytes": len(hierarchy_bytes),
            },
            "semantic_lifecycle_regularization_ruling": {
                "path": str(REGULARIZATION_RULING_PATH),
                "content_handle": REGULARIZATION_RULING_HANDLE,
                "bytes": len(ruling_bytes),
            },
            "semantic_lifecycle_regularizer_design": {
                "path": str(REGULARIZATION_DESIGN_PATH),
                "content_handle": REGULARIZATION_DESIGN_HANDLE,
                "bytes": len(design_bytes),
            },
        },
        "classes": class_receipts,
        "required_classes": list(REQUIRED_CLASSES),
        "required_complete": all(
            row["admitted"] and row["omitted"] == 0 and row["count"] > 0
            for row in class_receipts
        ),
        "sources_path": source_file.relative_to(root).as_posix(),
        "sources_file_handle": digest_bytes(source_bytes),
        "source_row_count": len(rows),
        "typed_relation_count": len(edges),
        "typed_relation_root": digest(edges),
        "relation_counts": relation_counts,
        "fold_intent": {
            "schema_version": "laplace.semantic-fold-intent/1",
            "source_commit": head,
            "source_tree": tree,
            "builder": {
                "command": "/usr/bin/python3 scripts/reembed.py --full",
                "required_gpu": True,
                "mode": "full-rebuild",
                "source_adapter": SOURCE_SCHEMA,
            },
            "output_predicate": (
                "one Git successor containing only the declared semantic fold family and "
                "a self-verifying laplace.semantic-fold-transition/1 manifest"
            ),
        },
        "read_only": True,
        "authority_effect": "none",
        "proof_boundary": (
            "content-addressed semantic projection; Git and Atlas remain canonical; "
            "Fabric/profile bytes are embedded in-process and never copied into this projection"
        ),
    }
    coverage["coverage_handle"] = digest(coverage)
    coverage_file.write_bytes(canonical_bytes(coverage) + b"\n")
    return coverage


def load_coverage(repo_root: Path | str) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    raw = (root / COVERAGE_PATH).read_bytes()
    value = json.loads(raw)
    carried = value.pop("coverage_handle")
    if digest(value) != carried:
        raise RuntimeError("semantic source coverage handle does not verify")
    return {**value, "coverage_handle": carried}


def operational_leaves(repo_root: Path | str) -> dict[str, dict[str, Any]]:
    """Rehydrate the admitted projection as transient semantic leaves.

    Sensitive body/profile text exists only in ``embedding_text`` and is deliberately omitted by
    ``keeper.build_tree`` when the graded nodes are persisted.
    """

    root = Path(repo_root).resolve()
    coverage = load_coverage(root)
    source_path = root / coverage["sources_path"]
    source_bytes = source_path.read_bytes()
    if digest_bytes(source_bytes) != coverage["sources_file_handle"]:
        raise RuntimeError("semantic operational source rows moved after coverage capture")

    provider = atlas_bridge.snapshot()["provider"]
    if (
        int(provider["event_count"]) != int(coverage["atlas"]["cursor"])
        or str(provider["head_event_id"]) != str(coverage["atlas"]["head_event_id"])
        or digest(provider["graph"]["objects"]) != coverage["atlas"]["graph_object_root"]
        or digest(provider["graph"]["edges"]) != coverage["atlas"]["graph_edge_root"]
    ):
        raise RuntimeError("Atlas moved after semantic source coverage capture")

    objects = provider["graph"]["objects"]
    work_path = root / "corpus_friction" / "work_orders.jsonl"
    leaves: dict[str, dict[str, Any]] = {}
    for raw in source_bytes.splitlines():
        if not raw:
            continue
        row = json.loads(raw)
        node_id = str(row["id"])
        embedding_text = str(row.get("semantic_summary") or "")
        classes = tuple(str(item) for item in row.get("source_classes") or ())
        canonical = str(row.get("canonical_handle") or "")
        if "atlas-graph-objects" in classes and canonical in objects:
            embedding_text = canonical_bytes(objects[canonical]).decode("utf-8")
        if "fabric-exchange" in classes:
            body_handle = str(row.get("body_handle") or "")
            if body_handle:
                try:
                    body = atlas_bridge._blobs().get(body_handle)
                except BlobMissing:
                    unavailable = _historical_unavailable_embedding(node_id, body_handle)
                    if unavailable is None:
                        raise
                    embedding_text = unavailable.decode("utf-8")
                else:
                    if digest_bytes(body) != body_handle:
                        raise RuntimeError(f"Fabric body moved for {node_id}")
                    embedding_text = body.decode("utf-8", errors="replace")
        if "work-orders" in classes and row.get("canonical_source"):
            with work_path.open("rb") as handle:
                handle.seek(int(row["byte_offset"]))
                line = handle.read(int(row["byte_length"]))
            if digest_bytes(line) != row["content_handle"]:
                raise RuntimeError(f"work-order row moved for {node_id}")
            embedding_text = line.decode("utf-8", errors="replace")
        if row.get("kind") == "seat-reconstruction-profile":
            body = atlas_bridge._blobs().get(str(row["content_handle"]))
            if digest_bytes(body) != row["content_handle"]:
                raise RuntimeError(f"seat profile moved for {node_id}")
            embedding_text = body.decode("utf-8", errors="replace")
        if row.get("embedding_payload") is not None:
            embedding_text = canonical_bytes(row["embedding_payload"]).decode("utf-8")
        if row.get("external_custody_handle"):
            external_handle = str(row["external_custody_handle"])
            body = atlas_bridge._blobs().get(external_handle)
            if digest_bytes(body) != external_handle:
                raise RuntimeError(f"external custody moved for {node_id}")
            embedding_text = body.decode("utf-8", errors="replace")

        essence = str(row.get("semantic_summary") or "")[:720]
        keywords = sorted(
            _tokenize(" ".join((node_id, essence, " ".join(classes))))
        )[:24]
        leaves[node_id] = {
            "name": node_id,
            "kind": str(row.get("kind") or "operational-source"),
            "essence": essence,
            "keywords": keywords,
            "spine_count": len(row.get("relations") or ()),
            "lines": 1,
            "edges": [
                {"kind": str(edge["relation"]), "to": str(edge["target"])}
                for edge in row.get("relations") or ()
            ],
            "sealed": False,
            "semantic_parent": row.get("semantic_parent"),
            "embedding_text": embedding_text,
            "projection": {
                "schema_version": SOURCE_SCHEMA,
                "source_classes": list(classes),
                "canonical_handle": canonical,
                "content_handle": row.get("content_handle"),
                "exact_descent": row.get("exact_descent"),
                "axis": row.get("axis"),
                "typed_relations": row.get("relations") or [],
                "coverage_handle": coverage["coverage_handle"],
            },
        }
    return leaves


__all__ = [
    "COVERAGE_PATH", "COVERAGE_SCHEMA", "REQUIRED_CLASSES", "SOURCE_SCHEMA", "SOURCES_PATH",
    "capture", "canonical_bytes", "digest", "digest_bytes", "load_coverage",
    "operational_leaves",
]
