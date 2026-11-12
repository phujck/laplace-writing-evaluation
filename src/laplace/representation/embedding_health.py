"""Read-only health of the router's worktree fold, with the retired Git fold as history.

Tree currentness compares tracked worktree mtimes with the latest deposit receipt.
The historical source-to-manifest transition retains its separate validation rules.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from laplace.core.checkout import source_tree
from laplace.representation.semantic_vertical import canonical_bytes, digest, digest_bytes, load_coverage

HEALTH_SCHEMA = "laplace.embedding-health/1"
MANIFEST_SCHEMA = "laplace.semantic-fold-transition/1"
MANIFEST_PATH = Path(".semantic_fold_manifest.json")
SEMANTIC_FOLD_RECEIPT_SCHEMA = "laplace.semantic-fold-receipt/1"
SEMANTIC_FOLD_INDEX_SCHEMA = "laplace.semantic-fold-descent-index/1"
SEMANTIC_FOLD_DOWN_SCHEMA = "laplace.semantic-fold-down/1"
REGISTER_SCHEMA = "laplace.semantic-register-dictionary/1"
SEMANTIC_FOLD_INDEX_PATH = Path(".semantic_fold_descent.json")
SEMANTIC_FOLD_RECEIPT_REF = "refs/eigen/semantic-fold-receipt"
SEMANTIC_FOLD_REF = "refs/eigen/semantic-fold"
SEMANTIC_FOLD_SHARDS = tuple(f"{value:02x}" for value in range(256))
SEMANTIC_FOLD_SHARD_CAP = 1024
SEMANTIC_FOLD_UP_PATHS = tuple(
    f"semantic/fold_up/{shard}.jsonl" for shard in SEMANTIC_FOLD_SHARDS
)
SEMANTIC_FOLD_DOWN_PATHS = tuple(
    f"semantic/fold_down/{shard}.json" for shard in SEMANTIC_FOLD_SHARDS
)

def publication_artifacts(repo_root: Path | str | None = None) -> tuple[dict, ...]:
    """The shared producer/consumer artifact declaration, separate from Git retention."""
    import tomllib
    root = Path(repo_root) if repo_root else source_tree()
    document = tomllib.loads((root / "runtime_profiles.toml").read_text())
    declaration = document["publication"]
    if declaration["schema"] != "laplace.publication-artifacts/1":
        raise ValueError("unsupported publication artifact declaration")
    rows = declaration["artifacts"]
    if len({row["path"] for row in rows}) != len(rows) or len({row["key"] for row in rows}) != len(rows):
        raise ValueError("duplicate publication artifact")
    for row in rows:
        path = Path(row["path"])
        if path.is_absolute() or len(path.parts) != 1 or not row.get("producer") or not row.get("consumers"):
            raise ValueError("publication artifacts require a local name, producer and consumers")
    return tuple(rows)


# One explicit family.  The producer may leave a member byte-identical, but it may not create a
# semantic sidecar outside this set and later ask health to bless it by globbing the worktree.
FOLD_ARTIFACT_PATHS = tuple(dict.fromkeys((
    *(row["path"] for row in publication_artifacts()),
    ".meaning_tree.json",
    ".meaning_vectors.f32.npy",
    ".meaning_vectors.index.json",
    ".metric_M.npz",
    ".reembed_timing.jsonl",
    ".residue.jsonl",
    ".self_embeddings.json",
    ".self_graded.json",
    ".semantic_source_coverage.json",
    ".semantic_fold_descent.json",
    *SEMANTIC_FOLD_UP_PATHS,
    *SEMANTIC_FOLD_DOWN_PATHS,
    ".upfold_triggers.jsonl",
    ".wire_proposals.jsonl",
    ".wire_verdicts.jsonl",
    "SELF_GRADED_INDEX.md",
    "SELF_SHARD_INDEX.md",
    "contract/journal.jsonl",
    "semantic/operational_sources.jsonl",
    "semantic/seat_context_heads.json",
)))


def _verified_object(path: Path, *, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"{name} is unreadable: {type(exc).__name__}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{name} is not an object")
    return value


def _route(parent_map: Mapping[str, Any], node_id: str) -> list[str]:
    route = [node_id]
    seen = {node_id}
    current = node_id
    for _step in range(65):
        parent = parent_map.get(current)
        if parent in (None, ""):
            return route
        parent = str(parent)
        if parent in seen:
            raise RuntimeError(f"semantic fold parent cycle at {parent!r}")
        route.append(parent)
        seen.add(parent)
        current = parent
    raise RuntimeError(f"semantic fold route exceeds 64 parents for {node_id!r}")


def _register_dictionary(
    *, generation_seed: Mapping[str, Any], persisted_tokens: Sequence[str]
) -> dict[str, Any]:
    """Compile only registers with positive measured persisted-byte savings."""

    from collections import Counter

    counts = Counter(str(token) for token in persisted_tokens if str(token))
    candidates = []
    for token, frequency in counts.items():
        literal_bytes = len(canonical_bytes(token))
        encoded_bytes = len(canonical_bytes("r00"))
        benefit = frequency * max(0, literal_bytes - encoded_bytes)
        if benefit > 0:
            candidates.append((benefit, frequency, token, literal_bytes))
    registers = [
        {
            "symbol": f"r{position:02x}",
            "handle": token,
            "measured_frequency": frequency,
            "literal_bytes": literal_bytes,
            "measured_saved_bytes": benefit,
        }
        for position, (benefit, frequency, token, literal_bytes) in enumerate(
            sorted(candidates, key=lambda row: (-row[0], -row[1], row[2]))[:256]
        )
    ]
    generation = digest({"seed": dict(generation_seed), "registers": registers})
    body = {
        "schema_version": REGISTER_SCHEMA,
        "generation": generation,
        "operand_registers": registers,
        "measurement": "frequency in persisted fold receipt/index rows",
        "literal_escape": "LITERAL",
        "law": (
            "registers are generation-scoped lossless encodings only; unknown or moved "
            "generations refuse and every unprofitable or absent token stays LITERAL"
        ),
    }
    body["dictionary_handle"] = digest(body)
    return body


def _semantic_leaf_route(root: Path, node_id: str, node: Mapping[str, Any]) -> dict[str, str]:
    from laplace.engine import descent

    projection = node.get("projection") if isinstance(node.get("projection"), Mapping) else {}
    declared = projection.get("exact_descent")
    if declared is None and (root / node_id).is_file():
        declared = {"kind": "repository-file", "reference": node_id, "source": ""}
    if not isinstance(declared, Mapping):
        raise RuntimeError(f"semantic leaf {node_id!r} has no total typed route")
    normalized = descent.normalize_target(
        str(declared.get("reference") or ""),
        explicit_kind=str(declared.get("kind") or ""),
        source=str(declared.get("source") or ""),
        fold=str(declared.get("fold") or ""),
    )
    if normalized is None:
        raise RuntimeError(f"semantic leaf {node_id!r} route is not registered")
    return normalized


def _semantic_vector(entries: Mapping[str, Any], node_id: str) -> tuple[float, ...]:
    from laplace.representation.embed_router import _dequantize_entry

    row = entries.get(node_id)
    if not isinstance(row, dict):
        raise RuntimeError(f"semantic vector is absent for {node_id!r}")
    return tuple(float(value) for value in _dequantize_entry(row))


def _cluster_depth(parent_map: Mapping[str, Any], node_id: str) -> int:
    return len(_route(parent_map, node_id))


def _shard_for_handle(handle: str) -> str:
    if not isinstance(handle, str) or not handle.startswith("sha256:"):
        raise RuntimeError("semantic node handle is not a canonical sha256 identity")
    shard = handle.removeprefix("sha256:")[:2]
    if shard not in SEMANTIC_FOLD_SHARDS:
        raise RuntimeError("semantic node handle has no canonical prefix shard")
    return shard


def build_semantic_fold_index(repo_root: Path | str) -> dict[str, Any]:
    """Build canonical UP receipts and a capped keyed read-only DOWN index."""

    from laplace.representation.atlas_bridge import ChildLeaf, UpInputs, up
    from laplace.representation.atlas_bridge import UpActReceipt, bind_up_result

    from laplace.engine import descent

    root = Path(repo_root).resolve()
    coverage = load_coverage(root)
    meaning = _verified_object(root / ".meaning_tree.json", name="meaning tree")
    graded = _verified_object(root / ".self_graded.json", name="graded self")
    embeddings = _verified_object(root / ".self_embeddings.json", name="semantic embeddings")
    parent_map = meaning.get("parent_map")
    clusters = meaning.get("clusters")
    leaf_sha = meaning.get("leaf_sha")
    vector_entries = embeddings.get("nodes")
    if not all(isinstance(value, dict) for value in (
        parent_map, clusters, leaf_sha, vector_entries,
    )):
        raise RuntimeError("meaning fold omits clusters, membership, leaves, or vectors")

    leaf_rows: dict[str, dict[str, Any]] = {}
    leaf_children: dict[str, ChildLeaf] = {}
    persisted_tokens: list[str] = []
    for node_id, text_handle in sorted(leaf_sha.items()):
        node = graded.get(node_id)
        if not isinstance(node, Mapping):
            raise RuntimeError(f"meaning leaf {node_id!r} is absent from the graded self")
        route = _semantic_leaf_route(root, str(node_id), node)
        projection = node.get("projection") if isinstance(node.get("projection"), Mapping) else {}
        content_handle = str(projection.get("content_handle") or f"sha1:{text_handle}")
        semantic_handle = digest({
            "schema_version": "laplace.semantic-leaf-evidence/1",
            "node_id": node_id,
            "content_handle": content_handle,
            "exact_descent": route,
        })
        leaf_children[str(node_id)] = ChildLeaf(
            semantic_handle,
            str(node.get("essence") or node.get("label") or node_id),
            _semantic_vector(vector_entries, str(node_id)),
        )
        leaf_rows[semantic_handle] = {
            "kind": "leaf",
            "semantic_handle": semantic_handle,
            "node_id": str(node_id),
            "content_handle": content_handle,
            "exact_descent": route,
            "parent_id": parent_map.get(node_id),
        }
        persisted_tokens.extend((semantic_handle, content_handle, *route.values()))

    children_by_parent: dict[str, list[str]] = {}
    for child_id, parent_id in parent_map.items():
        children_by_parent.setdefault(str(parent_id), []).append(str(child_id))

    receipts_by_cluster: dict[str, UpActReceipt] = {}
    for cluster_id in sorted(
        (str(value) for value in clusters),
        key=lambda value: (-_cluster_depth(parent_map, value), value),
    ):
        direct_ids = sorted(children_by_parent.get(cluster_id) or ())
        if not direct_ids:
            raise RuntimeError(f"semantic cluster {cluster_id!r} has no direct children")
        children: list[ChildLeaf] = []
        member_objects: dict[str, str] = {}
        for child_id in direct_ids:
            if child_id in leaf_children:
                child = leaf_children[child_id]
            else:
                child_receipt = receipts_by_cluster.get(child_id)
                if child_receipt is None:
                    raise RuntimeError(
                        f"semantic cluster {cluster_id!r} has unresolved child {child_id!r}"
                    )
                child = ChildLeaf(
                    child_receipt.node_handle,
                    child_receipt.semantic_face,
                    child_receipt.centroid,
                )
            children.append(child)
            member_objects[child.handle] = f"semantic-fold-object:{child_id}"
            persisted_tokens.extend((child.handle, member_objects[child.handle]))
        inputs = UpInputs(
            assumption="laplace.semantic-fold",
            fibre="operational-universal",
            axis="semantic-grade",
            from_grade="fine",
            to_grade="coarse",
            metric_version=str(embeddings.get("backend") or "UNKNOWN"),
            grade_contract_id="laplace.semantic-fold-grade-axis/1",
            chi=min(8, len(children)),
            phi=0.20,
            coarse_to_fine=("coarse", "fine"),
            children=tuple(children),
        )
        receipt = UpActReceipt.from_dict(bind_up_result(inputs, up(inputs), member_objects).to_dict())
        receipts_by_cluster[cluster_id] = receipt
        persisted_tokens.extend((receipt.node_handle, receipt.act_handle, receipt.inputs_handle))

    receipt_buckets: dict[str, list[tuple[str, bytes]]] = {
        shard: [] for shard in SEMANTIC_FOLD_SHARDS
    }
    leaf_buckets: dict[str, list[tuple[str, dict[str, Any]]]] = {
        shard: [] for shard in SEMANTIC_FOLD_SHARDS
    }
    for receipt in receipts_by_cluster.values():
        receipt_buckets[_shard_for_handle(receipt.node_handle)].append(
            (receipt.node_handle, canonical_bytes(receipt.to_dict()) + b"\n")
        )
    for handle, row in leaf_rows.items():
        leaf_buckets[_shard_for_handle(handle)].append((handle, row))
    down_shards: list[dict[str, Any]] = []
    up_rows: list[dict[str, Any]] = []
    for shard in SEMANTIC_FOLD_SHARDS:
        rows = sorted(receipt_buckets[shard])
        leaves = sorted(leaf_buckets[shard])
        if len(rows) + len(leaves) > SEMANTIC_FOLD_SHARD_CAP:
            raise RuntimeError(
                f"semantic DOWN shard {shard} exceeds cap {SEMANTIC_FOLD_SHARD_CAP}"
            )
        receipt_path = root / f"semantic/fold_up/{shard}.jsonl"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        offset = 0
        payload = bytearray()
        entries: dict[str, dict[str, Any]] = {
            handle: {
                "kind": "leaf",
                "row": row,
                "row_handle": digest(row),
            }
            for handle, row in leaves
        }
        for handle, row_bytes in rows:
            receipt = UpActReceipt.from_dict(json.loads(row_bytes))
            receipt_handle = digest(receipt.to_dict())
            entries[handle] = {
                "kind": "cluster",
                "receipt_path": f"semantic/fold_up/{shard}.jsonl",
                "offset": offset,
                "length": len(row_bytes),
                "row_handle": digest_bytes(row_bytes),
                "up_act_handle": receipt.act_handle,
                "up_receipt_handle": receipt_handle,
            }
            up_rows.append({
                "node_handle": handle,
                "up_act_handle": receipt.act_handle,
                "up_receipt_handle": receipt_handle,
            })
            payload.extend(row_bytes)
            offset += len(row_bytes)
        receipt_path.write_bytes(bytes(payload))
        shard_body = {
            "schema_version": "laplace.semantic-fold-down-shard/1",
            "shard": shard,
            "cap": SEMANTIC_FOLD_SHARD_CAP,
            "entries": entries,
        }
        shard_body["shard_handle"] = digest(shard_body)
        down_path = root / f"semantic/fold_down/{shard}.json"
        down_path.parent.mkdir(parents=True, exist_ok=True)
        down_path.write_bytes(canonical_bytes(shard_body) + b"\n")
        down_shards.append({
            "shard": shard,
            "entries": len(entries),
            "leaves": len(leaves),
            "clusters": len(rows),
            "receipt_bytes_handle": digest_bytes(bytes(payload)),
            "index_handle": shard_body["shard_handle"],
        })

    samples: dict[str, Mapping[str, Any]] = {}
    for row in leaf_rows.values():
        samples.setdefault(str(row["exact_descent"]["kind"]), row["exact_descent"])
    route_witnesses = []
    for kind, route in sorted(samples.items()):
        result = descent.descend(
            kind=kind,
            reference=str(route["reference"]),
            source=str(route.get("source") or ""),
            fold=str(route.get("fold") or ""),
            goal="prove semantic-fold typed route totality",
            content_budget=4_096,
            record_telemetry=False,
        )
        if result.get("content_status") not in {"COMPLETE", "BUDGET", "TRUNCATED"}:
            raise RuntimeError(f"semantic route witness refused for {kind!r}")
        route_witnesses.append({
            "kind": kind,
            "reference": route["reference"],
            "content_status": result.get("content_status"),
            "content_handle": result.get("content_handle"),
            "read_only": result.get("read_only"),
        })

    ordered_receipts = sorted(receipts_by_cluster.values(), key=lambda row: row.node_handle)
    roots = {
        "leaf_content_root": digest([
            {"semantic_handle": handle, "content_handle": row["content_handle"]}
            for handle, row in sorted(leaf_rows.items())
        ]),
        "membership_cluster_root": digest([
            {
                "node_handle": receipt.node_handle,
                "members": [member.to_dict() for member in receipt.members],
            }
            for receipt in ordered_receipts
        ]),
        "canonical_up_receipt_root": digest(sorted(up_rows, key=lambda row: row["node_handle"])),
        "bounded_down_index_root": digest(down_shards),
        "retained_state_reconstruction_root": digest([
            {
                "node_handle": receipt.node_handle,
                "frame": receipt.frame.to_dict(),
                "centroid": list(receipt.centroid),
            }
            for receipt in ordered_receipts
        ]),
        "residual_fog_omission_root": digest({
            "classes": coverage["classes"],
            "required_complete": coverage["required_complete"],
            "explicit_omission_node": "OP-EXPLICIT-OMISSIONS-REFUSALS",
            "down_history": "SUCCESSOR-RESIDUAL: atlas.down-history-act/2",
        }),
    }
    dictionary = _register_dictionary(
        generation_seed={
            "source": coverage["source_git"],
            "coverage_handle": coverage["coverage_handle"],
            **roots,
        },
        persisted_tokens=persisted_tokens,
    )
    body = {
        "schema_version": SEMANTIC_FOLD_INDEX_SCHEMA,
        "source": coverage["source_git"],
        "coverage_handle": coverage["coverage_handle"],
        "roots": roots,
        "down_shards": down_shards,
        "register_dictionary": dictionary,
        "typed_route_totality": {
            "status": "COMPLETE",
            "leaf_count": len(leaf_rows),
            "cluster_count": len(receipts_by_cluster),
            "untyped": 0,
            "route_kinds": sorted(samples),
            "deep_witnesses": route_witnesses,
            "bare_hash_law": "REFUSED unless carried by semantic-fold-object plus receipt",
        },
        "reference_law": {
            "up": "atlas.up-history-act/2",
            "down": "atlas.down-act/1",
            "down_history": "SUCCESSOR-RESIDUAL: atlas.down-history-act/2",
            "relation": "canonical batch of exact UP receipts; read-only DOWN has no cluster event",
        },
        "atlas_event_delta": 0,
    }
    body["index_handle"] = digest(body)
    (root / SEMANTIC_FOLD_INDEX_PATH).write_bytes(canonical_bytes(body) + b"\n")
    return body


def build_outer_receipt(repo_root: Path | str, *, output_commit: str) -> dict[str, Any]:
    """Bind the actual committed F outside F, avoiding recursive self-hash."""

    root = Path(repo_root).resolve()
    manifest = _load_manifest(root, output_commit)
    candidate = manifest.get("semantic_fold_candidate")
    if not isinstance(candidate, Mapping):
        raise RuntimeError("committed fold omits its canonical UP/DOWN candidate")
    source_tuple = manifest["source"].get("source_tuple")
    if (
        not isinstance(source_tuple, Mapping)
        or source_tuple.get("source_tuple_handle")
        != manifest["source"].get("source_tuple_handle")
    ):
        raise RuntimeError("committed fold omits its normalized source tuple")
    body = {
        "schema_version": SEMANTIC_FOLD_RECEIPT_SCHEMA,
        "form": "CANONICAL-UP-RECEIPT-BATCH-READ-ONLY-DOWN",
        "source_root_s": digest({
            "git": {key: manifest["source"][key] for key in ("commit", "tree")},
            "atlas": manifest["source"]["atlas"],
            "classes": manifest["source"]["source_classes"],
        }),
        "source_commit": manifest["source"]["commit"],
        "source_tree": manifest["source"]["tree"],
        "source_tuple": dict(source_tuple),
        "source_tuple_handle": str(source_tuple["source_tuple_handle"]),
        "output_commit": output_commit,
        "output_tree": _git(root, "rev-parse", f"{output_commit}^{{tree}}"),
        "manifest_handle": manifest["manifest_handle"],
        "artifact_root": manifest["artifact_root"],
        "exact_descent_index": dict(candidate["exact_descent_index"]),
        "roots": dict(candidate["roots"]),
        "register_dictionary": dict(candidate["register_dictionary"]),
        "hierarchy_phase_consumption": dict(candidate["hierarchy_phase_consumption"]),
        "health": {
            "schema_version": HEALTH_SCHEMA,
            "status": "CURRENT-CANDIDATE",
            "authenticated": False,
            "claim": "validated before the atomic semantic ref transaction",
        },
        "reference_law": dict(candidate["reference_law"]),
        "forward_currentness": {
            "relation": "EXACT-SINGLE-SUCCESSOR",
            "source_commit": manifest["source"]["commit"],
            "output_commit": output_commit,
        },
    }
    body["receipt_handle"] = digest(body)
    return body


def _read_outer_receipt(root: Path, object_id: str | None = None) -> dict[str, Any]:
    selected = object_id or _git(root, "rev-parse", "--verify", SEMANTIC_FOLD_RECEIPT_REF)
    raw = subprocess.run(
        ["git", "cat-file", "blob", selected], cwd=root, capture_output=True, check=True
    ).stdout
    value = json.loads(raw)
    carried = value.pop("receipt_handle", None)
    if value.get("schema_version") != SEMANTIC_FOLD_RECEIPT_SCHEMA or digest(value) != carried:
        raise RuntimeError("outer semantic fold receipt is malformed or moved")
    return {**value, "receipt_handle": carried, "receipt_object": selected}


def _verified_source_tuple(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError("semantic fold source tuple is absent")
    carried = value.get("source_tuple_handle")
    body = {key: item for key, item in value.items() if key != "source_tuple_handle"}
    if (
        value.get("schema_version") not in {
            "laplace.semantic-fold-source-tuple/1",
            "laplace.semantic-fold-source-tuple/2",
        }
        or not isinstance(carried, str)
        or digest(body) != carried
    ):
        raise RuntimeError("semantic fold source tuple is malformed or moved")
    return dict(value)


def _tuple_delta(expected: Mapping[str, Any], observed: Mapping[str, Any]) -> list[str]:
    if (
        expected.get("schema_version") == "laplace.semantic-fold-source-tuple/2"
        and observed.get("schema_version") == "laplace.semantic-fold-source-tuple/2"
    ):
        from laplace.representation.semantic_cadence import semantic_source_identity

        expected = semantic_source_identity(expected)
        observed = semantic_source_identity(observed)
    return sorted(
        key
        for key in set(expected) | set(observed)
        if expected.get(key) != observed.get(key)
    )


def semantic_fold_down(
    repo_root: Path | str,
    *,
    semantic_handle: str,
    receipt_handle: str,
    register_generation: str | None = None,
    original_children: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Select one exact cluster/leaf through F and execute canonical read-only DOWN."""

    from laplace.representation.atlas_bridge import CoarseNode, SpectralFrame, down
    from laplace.representation.atlas_bridge import UpActReceipt

    root = Path(repo_root).resolve()
    health = _read_side_ref_health(root)
    if health.get("status") != "CURRENT":
        raise RuntimeError("semantic DOWN requires a CURRENT exact S-to-F fold")
    fold = health["fold"]
    receipt = _read_outer_receipt(root)
    if receipt.get("receipt_handle") != receipt_handle:
        raise RuntimeError("semantic fold receipt handle moved")
    raw = subprocess.run(
        ["git", "show", f"{fold['output_commit']}:{SEMANTIC_FOLD_INDEX_PATH.as_posix()}"],
        cwd=root, capture_output=True, check=True,
    ).stdout
    index = json.loads(raw)
    carried = index.pop("index_handle", None)
    if digest(index) != carried or carried != receipt["exact_descent_index"]["handle"]:
        raise RuntimeError("semantic DOWN index moved from the outer fold receipt")
    expected_generation = index["register_dictionary"]["generation"]
    if register_generation is not None and register_generation != expected_generation:
        raise RuntimeError("semantic register generation is moved or unknown")
    shard = _shard_for_handle(semantic_handle)
    raw_shard = subprocess.run(
        ["git", "show", f"{fold['output_commit']}:semantic/fold_down/{shard}.json"],
        cwd=root, capture_output=True, check=True,
    ).stdout
    shard_body = json.loads(raw_shard)
    shard_handle = shard_body.pop("shard_handle", None)
    if digest(shard_body) != shard_handle:
        raise RuntimeError("semantic DOWN prefix shard is malformed")
    location = (shard_body.get("entries") or {}).get(semantic_handle)
    if not isinstance(location, Mapping):
        raise RuntimeError("semantic DOWN handle is unknown in this generation")
    if location.get("kind") == "leaf":
        row = location.get("row")
        if not isinstance(row, Mapping) or digest(row) != location.get("row_handle"):
            raise RuntimeError("semantic leaf route row is malformed or moved")
        if row.get("semantic_handle") != semantic_handle:
            raise RuntimeError("semantic leaf route key contradicts its exact handle")
        selected = dict(row)
        route_proof = {
            "canonical_down": None,
            "verification": "exact leaf route; no coarse prolongation required",
            "reconstruction": row["exact_descent"],
        }
    elif location.get("kind") == "cluster":
        receipt_bytes = subprocess.run(
            ["git", "show", f"{fold['output_commit']}:{location['receipt_path']}"],
            cwd=root, capture_output=True, check=True,
        ).stdout
        start = int(location["offset"])
        row_bytes = receipt_bytes[start : start + int(location["length"])]
        if digest_bytes(row_bytes) != location["row_handle"]:
            raise RuntimeError("semantic DOWN receipt row moved")
        promotion = UpActReceipt.from_dict(json.loads(row_bytes))
        if (
            promotion.node_handle != semantic_handle
            or promotion.act_handle != location["up_act_handle"]
            or digest(promotion.to_dict()) != location["up_receipt_handle"]
        ):
            raise RuntimeError("semantic DOWN receipt identity contradicts its keyed row")
        frame = promotion.frame
        node = CoarseNode(
            node_handle=promotion.node_handle,
            semantic_face=promotion.semantic_face,
            semantic_sources=promotion.semantic_sources,
            frame=SpectralFrame(
                frame.basis, frame.weights, frame.chi_declared, frame.chi_kept,
                frame.truncation_residual, frame.degenerate_cut, frame.coordinates,
            ),
            member_handles=tuple(member.content_handle for member in promotion.members),
            centroid=promotion.centroid,
        )
        result = down(node, children=original_children)
        selected = {
            "kind": "cluster",
            "semantic_handle": semantic_handle,
            "up_act_handle": promotion.act_handle,
            "up_receipt_handle": digest(promotion.to_dict()),
            "semantic_face": promotion.semantic_face,
            "membership_handles": [member.content_handle for member in promotion.members],
        }
        route_proof = {
            "canonical_down": {
                "schema_version": result.schema_version,
                "act_handle": result.act_handle,
                "node_handle": result.node_handle,
                "child_handles": list(result.child_handles),
                "reconstructions": {
                    handle: list(vector)
                    for handle, vector in sorted(result.reconstructions.items())
                },
                "verified": result.verified,
                "round_trip_residual": result.round_trip_residual,
            },
            "verification": "MEASURED" if result.verified else "UNVERIFIED-NO-ORIGINALS-SUPPLIED",
            "up_receipt": promotion.to_dict(),
        }
    else:
        raise RuntimeError("semantic DOWN shard row has an unknown kind")
    body = {
        "schema_version": SEMANTIC_FOLD_DOWN_SCHEMA,
        "status": "COMPLETE",
        "fold_receipt_handle": receipt["receipt_handle"],
        "index_handle": carried,
        "register_generation": expected_generation,
        "selected": selected,
        "route_proof": route_proof,
        "reference_law": receipt["reference_law"],
        "authority_effect": "none",
    }
    body["down_handle"] = digest(body)
    return body


def _git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=check
    )
    return result.stdout.strip()


def _file_receipt(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    if not path.is_file():
        raise RuntimeError(f"semantic fold artifact is absent: {relative}")
    body = path.read_bytes()
    git_blob = _git(root, "hash-object", "--path", relative, relative)
    return {
        "path": relative,
        "bytes": len(body),
        "content_handle": digest_bytes(body),
        "git_blob": git_blob,
    }


def _tree_blobs(root: Path, commit: str, paths: Sequence[str]) -> dict[str, str]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "-z", commit, "--", *paths],
        cwd=root, capture_output=True, check=True,
    )
    rows: dict[str, str] = {}
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        metadata, relative = record.split(b"\t", 1)
        _mode, kind, object_id = metadata.decode("ascii").split()
        if kind == "blob":
            rows[relative.decode("utf-8")] = object_id
    return rows


def _latest_timing(root: Path) -> dict[str, Any]:
    lines = (root / ".reembed_timing.jsonl").read_text(
        encoding="utf-8", errors="strict"
    ).splitlines()
    for line in reversed(lines):
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("latest deposit receipt is not an object")
            return value
    raise RuntimeError("full semantic fold has no timing receipt")


def _validate_deposit_receipt(receipt: Mapping[str, Any]) -> None:
    device = receipt.get("device") or {}
    counts = receipt.get("embedding_counts") or {}
    providers = device.get("embedding_providers") or []
    failures = []
    mode = receipt.get("mode")
    if mode == "full-rebuild":
        # A full rebuild is justified in one of two recorded ways: the operator asked for it
        # (`--full`), or the producer's own trigger receipt demanded it and was allowed to run it
        # (meaning_upfold._full_or_deny: churn over the threshold on a full compute home). The
        # first close after a long gap (7 November 2026, churn 27%) ran the second way with
        # full_requested False and could never be read back; the demand with its reason is the
        # justification the law wants, not the flag alone.
        trigger = receipt.get("trigger_receipt")
        events = (trigger or {}).get("events") if isinstance(trigger, Mapping) else None
        demanded = any(
            isinstance(event, Mapping) and event.get("kind") == "full_rebuild_demanded"
            and event.get("allowed") is True and str(event.get("reason") or "").strip()
            for event in (events or [])
        ) and isinstance(trigger, Mapping) and trigger.get("gate") == "rung-12a" and bool(trigger.get("deposit_act_id"))
        if receipt.get("full_requested") is not True and not demanded:
            failures.append("full rebuild was neither requested (full_requested) nor demanded and allowed by the trigger receipt")
    elif mode == "incremental":
        if receipt.get("full_requested") is not False:
            failures.append("full_requested is not false for incremental deposit")
        trigger = receipt.get("trigger_receipt")
        events = (trigger or {}).get("events") if isinstance(trigger, Mapping) else None
        kinds = {
            str(event.get("kind"))
            for event in (events or [])
            if isinstance(event, Mapping)
        }
        if (
            not isinstance(trigger, Mapping)
            or trigger.get("gate") != "rung-12a"
            or not trigger.get("deposit_act_id")
            or "delta_measured" not in kinds
            or "incremental_applied" not in kinds
            or "full_rebuild_demanded" in kinds
        ):
            failures.append("incremental trigger receipt is absent, incomplete, or contradictory")
        if int(counts.get("cached", 0)) <= 0:
            failures.append("incremental deposit proves no reused cached embedding")
    else:
        failures.append(f"mode={mode!r}")
    if device.get("required") is not True:
        failures.append("required GPU was not asserted")
    if device.get("embedding_backend") != "gpu" or "CUDAExecutionProvider" not in providers:
        failures.append("embedding backend/providers are not device-honest GPU")
    if int(counts.get("deferred", -1)) != 0:
        failures.append(f"n_deferred={counts.get('deferred')!r}")
    if int(counts.get("total", 0)) <= 0:
        failures.append("embedding basis is empty")
    if failures:
        raise RuntimeError("semantic fold receipt refused: " + "; ".join(failures))


def build_manifest(
    repo_root: Path | str,
    *,
    witnesses: Sequence[Mapping[str, Any]],
    cadence: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the post-fold manifest before the single output commit is created."""

    root = Path(repo_root).resolve()
    coverage = load_coverage(root)
    source = coverage["source_git"]
    if _git(root, "rev-parse", "HEAD") != source["commit"]:
        raise RuntimeError("manifest must be built at its declared source commit S")
    if _git(root, "rev-parse", "HEAD^{tree}") != source["tree"]:
        raise RuntimeError("manifest source tree moved")
    timing = _latest_timing(root)
    _validate_deposit_receipt(timing)
    class_rows = coverage.get("classes") or []
    class_names = {row.get("source_class") for row in class_rows if isinstance(row, Mapping)}
    if set(coverage.get("required_classes") or ()) != class_names or not coverage.get(
        "required_complete"
    ):
        raise RuntimeError("operational source-class coverage is incomplete")
    fold_index = build_semantic_fold_index(root)
    artifacts = [_file_receipt(root, path) for path in FOLD_ARTIFACT_PATHS]
    meaning = json.loads((root / ".meaning_tree.json").read_text(encoding="utf-8"))
    graded = json.loads((root / ".self_graded.json").read_text(encoding="utf-8"))
    from laplace.engine.compaction_submergence import consume_hierarchy_derivation

    phase = consume_hierarchy_derivation(
        semantic_fold_handle=digest(artifacts)
    )
    if phase.get("status") != "CONSUMED":
        raise RuntimeError("hierarchy phase derivation is not consumed by the semantic fold")
    fold_candidate = {
        "schema_version": "laplace.semantic-fold-candidate/1",
        "exact_descent_index": {
            "path": SEMANTIC_FOLD_INDEX_PATH.as_posix(),
            "handle": fold_index["index_handle"],
            "generation": fold_index["register_dictionary"]["generation"],
            "entries": sum(row["entries"] for row in fold_index["down_shards"]),
        },
        "roots": dict(fold_index["roots"]),
        "register_dictionary": dict(fold_index["register_dictionary"]),
        "hierarchy_phase_consumption": dict(phase["receipt"]),
        "reference_law": dict(fold_index["reference_law"]),
        "validation_order": "validate complete candidate before atomic semantic ref CAS",
    }
    body = {
        "schema_version": MANIFEST_SCHEMA,
        "status": "CANDIDATE",
        "shared": True,
        "source": {
            **source,
            "coverage_handle": coverage["coverage_handle"],
            "source_classes": class_rows,
            "profile_handles": coverage["profile_handles"],
            "atlas": coverage["atlas"],
            "source_tuple": coverage["source_tuple"],
            "source_tuple_handle": coverage["source_tuple_handle"],
        },
        "forward_transition": {
            "kind": "git-single-successor",
            "expected_parent": source["commit"],
            "allowed_paths": sorted((*FOLD_ARTIFACT_PATHS, MANIFEST_PATH.as_posix())),
            "unrelated_source_change": "UPDATE-DUE",
        },
        "builder": (coverage.get("fold_intent") or {}).get("builder"),
        "artifacts": artifacts,
        "artifact_root": digest(artifacts),
        "semantic_fold_candidate": fold_candidate,
        "semantic_horizon": {
            "source_commit": source["commit"],
            "source_tree": source["tree"],
            "atlas_cursor": coverage["atlas"]["cursor"],
            "atlas_head_event_id": coverage["atlas"]["head_event_id"],
            "nodes": len(graded),
            "clusters": len(meaning.get("clusters") or {}),
            "leaves": len(meaning.get("leaf_sha") or {}),
        },
        "runtime": {"latest_receipt": timing},
        "semantic_reachability": list(witnesses),
        "cadence": dict(cadence),
        "outside_view_acceptance": {
            "product_delta": "complete operational source classes plus exact UP/DOWN reach",
            "coordination_cost_fields": [
                "elapsed_ms", "cpu_ms", "subprocesses", "reconstructions",
                "review_cycles", "waiting_ms", "rework", "unique_fault_catches",
            ],
            "fix_forward": "one smallest causally implicated region",
            "submerge_rule": "unique protective yield must exceed delay/context/transmission/control cost",
        },
        "currentness_law": (
            "CURRENT iff the manifest-writing commit is the exact single successor of S, "
            "S..F changes only the declared fold family, and the complete live compact "
            "Atlas/profile/goal/policy source tuple equals the one banked at S"
        ),
        "authority_effect": "none",
        "non_blocking": True,
    }
    body["manifest_handle"] = digest(body)
    (root / MANIFEST_PATH).write_bytes(canonical_bytes(body) + b"\n")
    return body


def _load_manifest(root: Path, commit: str | None = None) -> dict[str, Any]:
    raw = (
        subprocess.run(
            ["git", "show", f"{commit}:{MANIFEST_PATH.as_posix()}"],
            cwd=root,
            capture_output=True,
            check=True,
        ).stdout
        if commit
        else (root / MANIFEST_PATH).read_bytes()
    )
    value = json.loads(raw)
    carried = value.pop("manifest_handle", None)
    if value.get("schema_version") != MANIFEST_SCHEMA or digest(value) != carried:
        raise RuntimeError("semantic fold manifest is malformed or moved")
    return {**value, "manifest_handle": carried}


def validate_fold_candidate(
    repo_root: Path | str, *, output_commit: str, outer_receipt: Mapping[str, Any]
) -> dict[str, Any]:
    """Deeply validate F and every canonical UP row before either semantic ref moves."""

    from laplace.representation.atlas_bridge import UpActReceipt

    root = Path(repo_root).resolve()
    manifest = _load_manifest(root, output_commit)
    source = manifest["source"]
    if _git(root, "rev-parse", f"{output_commit}^") != source["commit"]:
        raise RuntimeError("semantic output F is not the exact single successor of S")
    changed = {
        line for line in _git(root, "diff", "--name-only", source["commit"], output_commit).splitlines()
        if line
    }
    if not changed.issubset(set(manifest["forward_transition"]["allowed_paths"])):
        raise RuntimeError("semantic output moved a path outside the declared fold family")
    artifact_rows = manifest["artifacts"]
    expected_blobs = {row["path"]: row["git_blob"] for row in artifact_rows}
    if _tree_blobs(root, output_commit, list(expected_blobs)) != expected_blobs:
        raise RuntimeError("semantic output artifact blobs disagree with the inner manifest")
    if digest(artifact_rows) != manifest["artifact_root"]:
        raise RuntimeError("semantic output artifact root does not verify")
    timing = manifest["runtime"]["latest_receipt"]
    _validate_deposit_receipt(timing)

    carried_outer = outer_receipt.get("receipt_handle")
    if digest({key: value for key, value in outer_receipt.items() if key != "receipt_handle"}) != carried_outer:
        raise RuntimeError("outer semantic receipt does not verify")
    if (
        outer_receipt.get("output_commit") != output_commit
        or outer_receipt.get("output_tree") != _git(root, "rev-parse", f"{output_commit}^{{tree}}")
        or outer_receipt.get("manifest_handle") != manifest["manifest_handle"]
        or outer_receipt.get("artifact_root") != manifest["artifact_root"]
        or outer_receipt.get("source_tuple") != source.get("source_tuple")
        or outer_receipt.get("source_tuple_handle")
        != source.get("source_tuple_handle")
    ):
        raise RuntimeError("outer semantic receipt contradicts committed F")

    raw_index = subprocess.run(
        ["git", "show", f"{output_commit}:{SEMANTIC_FOLD_INDEX_PATH.as_posix()}"],
        cwd=root, capture_output=True, check=True,
    ).stdout
    index = json.loads(raw_index)
    index_handle = index.pop("index_handle", None)
    if digest(index) != index_handle:
        raise RuntimeError("semantic descent index does not verify")
    candidate = manifest["semantic_fold_candidate"]
    if (
        candidate["exact_descent_index"]["handle"] != index_handle
        or outer_receipt["exact_descent_index"] != candidate["exact_descent_index"]
        or outer_receipt["roots"] != index["roots"]
        or candidate["roots"] != index["roots"]
        or outer_receipt["register_dictionary"] != index["register_dictionary"]
    ):
        raise RuntimeError("inner/outer fold roots or register generation disagree")
    if (index.get("typed_route_totality") or {}).get("status") != "COMPLETE":
        raise RuntimeError("semantic fold contains an untyped or unreachable emitted route")

    up_rows: list[dict[str, Any]] = []
    membership_rows: list[dict[str, Any]] = []
    retained_rows: list[dict[str, Any]] = []
    leaf_content_rows: list[dict[str, Any]] = []
    down_shards: list[dict[str, Any]] = []
    if "leaf_entries" in index or "entries" in index:
        raise RuntimeError("top semantic index embeds unbounded object rows")
    for shard in SEMANTIC_FOLD_SHARDS:
        receipt_bytes = subprocess.run(
            ["git", "show", f"{output_commit}:semantic/fold_up/{shard}.jsonl"],
            cwd=root, capture_output=True, check=True,
        ).stdout
        raw_down = subprocess.run(
            ["git", "show", f"{output_commit}:semantic/fold_down/{shard}.json"],
            cwd=root, capture_output=True, check=True,
        ).stdout
        down_body = json.loads(raw_down)
        down_handle = down_body.pop("shard_handle", None)
        if digest(down_body) != down_handle or down_body.get("shard") != shard:
            raise RuntimeError(f"semantic DOWN shard {shard} does not verify")
        entries = down_body.get("entries") or {}
        if len(entries) > SEMANTIC_FOLD_SHARD_CAP:
            raise RuntimeError(f"semantic DOWN shard {shard} exceeds its declared cap")
        for node_handle, location in sorted(entries.items()):
            if location.get("kind") == "leaf":
                row = location.get("row")
                if (
                    not isinstance(row, Mapping)
                    or digest(row) != location.get("row_handle")
                    or row.get("semantic_handle") != node_handle
                ):
                    raise RuntimeError("semantic leaf route row does not verify")
                leaf_content_rows.append({
                    "semantic_handle": node_handle,
                    "content_handle": row["content_handle"],
                })
                continue
            if location.get("kind") != "cluster":
                raise RuntimeError("semantic DOWN shard row has an unknown kind")
            start = int(location["offset"])
            row_bytes = receipt_bytes[start : start + int(location["length"])]
            if digest_bytes(row_bytes) != location["row_handle"]:
                raise RuntimeError(f"canonical UP receipt row moved in shard {shard}")
            promotion = UpActReceipt.from_dict(json.loads(row_bytes))
            receipt_handle = digest(promotion.to_dict())
            if (
                promotion.node_handle != node_handle
                or promotion.act_handle != location["up_act_handle"]
                or receipt_handle != location["up_receipt_handle"]
            ):
                raise RuntimeError("canonical UP receipt identity contradicts its DOWN key")
            up_rows.append({
                "node_handle": node_handle,
                "up_act_handle": promotion.act_handle,
                "up_receipt_handle": receipt_handle,
            })
            membership_rows.append({
                "node_handle": node_handle,
                "members": [member.to_dict() for member in promotion.members],
            })
            retained_rows.append({
                "node_handle": node_handle,
                "frame": promotion.frame.to_dict(),
                "centroid": list(promotion.centroid),
            })
        down_shards.append({
            "shard": shard,
            "entries": len(entries),
            "leaves": sum(1 for row in entries.values() if row.get("kind") == "leaf"),
            "clusters": sum(1 for row in entries.values() if row.get("kind") == "cluster"),
            "receipt_bytes_handle": digest_bytes(receipt_bytes),
            "index_handle": down_handle,
        })
    roots = index["roots"]
    if digest(sorted(leaf_content_rows, key=lambda row: row["semantic_handle"])) != roots["leaf_content_root"]:
        raise RuntimeError("semantic leaf-content root does not rederive")
    if digest(sorted(up_rows, key=lambda row: row["node_handle"])) != roots["canonical_up_receipt_root"]:
        raise RuntimeError("canonical UP receipt root does not rederive")
    if digest(sorted(membership_rows, key=lambda row: row["node_handle"])) != roots["membership_cluster_root"]:
        raise RuntimeError("canonical UP membership root does not rederive")
    if digest(sorted(retained_rows, key=lambda row: row["node_handle"])) != roots["retained_state_reconstruction_root"]:
        raise RuntimeError("canonical retained-state root does not rederive")
    if digest(down_shards) != roots["bounded_down_index_root"]:
        raise RuntimeError("bounded DOWN shard root does not rederive")
    return {
        "status": "VALIDATED",
        "output_commit": output_commit,
        "output_tree": outer_receipt["output_tree"],
        "receipt_handle": carried_outer,
        "index_handle": index_handle,
        "up_receipts": len(up_rows),
        "down_shards": len(down_shards),
        "atlas_event_delta": 0,
    }


def publish_fold_refs(
    repo_root: Path | str,
    *,
    output_commit: str,
    outer_receipt: Mapping[str, Any],
    expected_previous_fold: str | None = None,
    expected_previous_receipt: str | None = None,
    expected_previous_pinned: bool = False,
) -> dict[str, Any]:
    """Validate first, then atomically CAS F and its outer receipt in one ref transaction."""

    root = Path(repo_root).resolve()
    validation = validate_fold_candidate(
        root, output_commit=output_commit, outer_receipt=outer_receipt
    )
    receipt_bytes = canonical_bytes(outer_receipt) + b"\n"
    receipt_object = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"], cwd=root, input=receipt_bytes,
        capture_output=True, check=True,
    ).stdout.decode("ascii").strip()
    old_fold = _git(root, "rev-parse", "--verify", SEMANTIC_FOLD_REF, check=False)
    old_receipt = _git(root, "rev-parse", "--verify", SEMANTIC_FOLD_RECEIPT_REF, check=False)
    if expected_previous_pinned:
        if old_fold != (expected_previous_fold or "") or old_receipt != (
            expected_previous_receipt or ""
        ):
            raise RuntimeError("semantic side refs moved after enqueue")
    source_commit = str(outer_receipt["source_commit"])
    if bool(old_fold) != bool(old_receipt):
        raise RuntimeError("prior semantic fold and receipt refs are incomplete")
    if old_fold:
        prior = _read_outer_receipt(root, old_receipt)
        if prior.get("output_commit") != old_fold:
            raise RuntimeError("prior semantic fold ref contradicts its exact receipt")
        prior_source = str(prior.get("source_commit") or "")
        if not prior_source or subprocess.run(
            ["git", "merge-base", "--is-ancestor", prior_source, source_commit], cwd=root
        ).returncode != 0:
            raise RuntimeError("requested semantic source does not descend from prior source S")
    zero = "0" * 40
    script = (
        "start\n"
        f"update {SEMANTIC_FOLD_REF} {output_commit} {old_fold or zero}\n"
        f"update {SEMANTIC_FOLD_RECEIPT_REF} {receipt_object} {old_receipt or zero}\n"
        "prepare\ncommit\n"
    )
    result = subprocess.run(
        ["git", "update-ref", "--stdin"], cwd=root, input=script,
        text=True, capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"atomic semantic ref CAS refused: {result.stderr.strip()}")
    return {
        **validation,
        "receipt_object": receipt_object,
        "previous_fold": old_fold or None,
        "previous_receipt_object": old_receipt or None,
        "ref_transaction": "COMMITTED",
    }


def _fired_node_ids(
    fired: Mapping[str, Any], network: Mapping[str, Any] | None = None
) -> set[str]:
    """Return every node the graded fire actually reached.

    ``fire_by_grade`` has two truthful result faces: terminal hits with their descent paths, and
    direct at-grade hits.  The old witness inspected only the former, so an internal source-class
    node could be the query's direct semantic answer and still be reported missing merely because
    none of its children occupied the terminal top-k.  That confused *where the router landed*
    with *which leaves it also recovered*.
    """

    reached = {
        str(item)
        for hit in fired.get("hits") or ()
        for item in (
            hit.get("recovered"),
            *(step.get("id") for step in hit.get("path") or ()),
        )
        if item
    }
    reached.update(
        str(item["id"])
        for rows in (fired.get("per_grade") or {}).values()
        for item in rows or ()
        if isinstance(item, Mapping) and item.get("id")
    )
    if network is not None:
        nodes = network.get("nodes") or {}
        frontier = list(reached)
        while frontier:
            node_id = frontier.pop()
            node = nodes.get(node_id)
            parent = node.get("parent") if isinstance(node, Mapping) else None
            if parent and parent not in reached:
                reached.add(str(parent))
                frontier.append(str(parent))
    return reached


def _fired_trace_node_ids(fired: Mapping[str, Any]) -> set[str]:
    """Return only nodes explicitly present in the router's result trace."""

    return {
        str(item)
        for hit in fired.get("hits") or ()
        for item in (
            hit.get("recovered"),
            *(step.get("id") for step in hit.get("path") or ()),
        )
        if item
    } | {
        str(item["id"])
        for rows in (fired.get("per_grade") or {}).values()
        for item in rows or ()
        if isinstance(item, Mapping) and item.get("id")
    }


def _bounded_discovery_region(
    fired: Mapping[str, Any],
    network: Mapping[str, Any],
    expected: str,
    *,
    budget: int,
) -> dict[str, Any]:
    """Prove that semantic fire landed in a bounded cluster containing ``expected``.

    Reconstruction is not database lookup.  A direct result is useful, but the intended success
    criterion is a routed region whose complete member closure is small enough for deterministic
    local search.  The global root is never such a region: otherwise every query would vacuously
    succeed.  Candidate regions come only from the explicit fire trace and its structural ancestry.
    """

    trace = _fired_trace_node_ids(fired)
    if expected in trace:
        return {
            "status": "DIRECT-HIT",
            "anchor_node": expected,
            "region_member_count": 1,
            "budget": budget,
            "target_contained": True,
        }
    nodes = network.get("nodes") or {}
    root = network.get("root")
    candidates = set(trace)
    frontier = list(trace)
    while frontier:
        node_id = frontier.pop()
        node = nodes.get(node_id)
        parent = node.get("parent") if isinstance(node, Mapping) else None
        if parent and parent not in candidates:
            candidates.add(str(parent))
            frontier.append(str(parent))

    bounded: list[tuple[int, str]] = []
    for anchor in candidates:
        if anchor == root or anchor not in nodes:
            continue
        region = {anchor}
        pending = [anchor]
        while pending and len(region) <= budget:
            current = pending.pop()
            node = nodes.get(current)
            members = node.get("members") if isinstance(node, Mapping) else ()
            for member in members or ():
                member_id = str(member)
                if member_id not in region:
                    region.add(member_id)
                    pending.append(member_id)
        if len(region) <= budget and expected in region:
            bounded.append((len(region), anchor))
    if bounded:
        region_size, anchor = min(bounded, key=lambda item: (item[0], item[1]))
        return {
            "status": "REGION-HIT",
            "anchor_node": anchor,
            "region_member_count": region_size,
            "budget": budget,
            "target_contained": True,
        }
    return {
        "status": "MISS",
        "anchor_node": None,
        "region_member_count": None,
        "budget": budget,
        "target_contained": False,
    }


def build_reachability_witnesses(
    repo_root: Path | str, *, local_search_budget: int = 256
) -> list[dict[str, Any]]:
    """Prove six known identities descend exactly and measure region discovery separately.

    Semantic routing succeeds when it returns the target directly or lands in a complete cluster
    that contains it within ``local_search_budget``.  Exact registered identity remains the
    authority path after that selection: a discovery miss cannot erase an object whose typed route
    and bytes are already known and independently reconstructible.
    """

    from laplace.engine import conceptric, descent

    root = Path(repo_root).resolve()
    coverage = load_coverage(root)
    rows = {
        str(row["id"]): row
        for row in (
            json.loads(line)
            for line in (root / coverage["sources_path"]).read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        )
    }
    specs = (
        ("current P0 P1 P2 development frontier and next work", "OP-DEVELOPMENT-WORK-MAP"),
        ("publication lifecycle recovery and local ref finalization", "operational://lifecycle-recovery-publication"),
        ("Fabric causal send pull reconstruction acknowledgement reply", "operational://fabric-exchange"),
        (
            "live and retired seat binding lineage, provider generations, routing authority, "
            "and the current Ego, Aisthesis, and Superego function reconstruction profiles "
            "with complete shared goals",
            "operational://seat-profiles-goals-bindings",
        ),
        ("current residual crutch refusal omission and retirement", "OP-EXPLICIT-OMISSIONS-REFUSALS"),
        ("recent committed source Git coordinate and tree", "OP-GIT-SOURCE-COORDINATE"),
    )
    network = conceptric.load_network(root)
    witnesses: list[dict[str, Any]] = []
    for query, expected in specs:
        fired = conceptric.fire_by_grade(root, network, query, limit=24)
        discovery = _bounded_discovery_region(
            fired, network, expected, budget=local_search_budget
        )
        discovery_reached = discovery["target_contained"]
        row = rows[expected]
        route = row["exact_descent"]
        exact = _complete_exact_descent(
            descent.descend, route=route, query=query, expected=expected
        )
        witnesses.append({
            "query": query,
            "router": fired.get("router"),
            "visited": fired.get("n_visited"),
            "expected_semantic_node": expected,
            "reached": True,
            "reachability_mode": "BOUNDED-REGION-THEN-EXACT-DESCENT",
            "discovery_reached": discovery_reached,
            "discovery_status": discovery["status"],
            "discovery_region_anchor": discovery["anchor_node"],
            "discovery_region_member_count": discovery["region_member_count"],
            "local_search_budget": discovery["budget"],
            "exact_route": route,
            "exact_content_handle": exact.get("content_handle"),
            "exact_content_status": exact.get("content_status"),
            "exact_content_pages": exact.get("content_pages"),
            "exact_content_bytes": exact.get("content_bytes"),
            "descent_authority_write": exact.get("authority_write"),
        })
    return witnesses


def _complete_exact_descent(
    descend_fn: Callable[..., dict[str, Any]],
    *,
    route: Mapping[str, Any],
    query: str,
    expected: str,
    page_budget: int = 65_536,
    max_pages: int = 512,
) -> dict[str, Any]:
    """Verify one exact typed route through every bounded continuation page."""

    offset = 0
    pages = 0
    content_handle: str | None = None
    content_bytes: int | None = None
    authority_write: str | None = None
    while pages < max_pages:
        page = descend_fn(
            kind=route["kind"],
            reference=route["reference"],
            source=route.get("source") or "",
            goal=query,
            content_budget=page_budget,
            content_offset=offset,
            record_telemetry=False,
        )
        status = page.get("content_status")
        observed_handle = page.get("content_handle")
        if page.get("refused") or status not in {"COMPLETE", "TRUNCATED", "FINAL"}:
            raise RuntimeError(f"exact descent refused for {expected}: {page}")
        if not isinstance(observed_handle, str) or not observed_handle.startswith("sha256:"):
            raise RuntimeError(f"exact descent lacks a content handle for {expected}")
        if content_handle is None:
            content_handle = observed_handle
            authority_write = page.get("authority_write")
        elif observed_handle != content_handle:
            raise RuntimeError(f"exact descent content moved between pages for {expected}")
        observed_bytes = page.get("content_bytes")
        if (
            not isinstance(observed_bytes, int)
            or isinstance(observed_bytes, bool)
            or observed_bytes < 0
            or page.get("content_offset") != offset
        ):
            raise RuntimeError(f"exact descent byte accounting is malformed for {expected}")
        if content_bytes is None:
            content_bytes = observed_bytes
        elif observed_bytes != content_bytes:
            raise RuntimeError(f"exact descent size moved between pages for {expected}")
        pages += 1
        next_offset = page.get("content_next_offset")
        if next_offset is None:
            terminal_status = "COMPLETE" if offset == 0 else "FINAL"
            if (
                status != terminal_status
                or page.get("content_omitted_after") != 0
                or page.get("content_omitted_before") != offset
            ):
                raise RuntimeError(f"exact descent terminal page is malformed for {expected}")
            return {
                **page,
                "content_handle": content_handle,
                "content_status": "COMPLETE",
                "content_pages": pages,
                "content_bytes": content_bytes,
                "authority_write": authority_write,
            }
        if (
            status != "TRUNCATED"
            or not isinstance(next_offset, int)
            or isinstance(next_offset, bool)
            or next_offset <= offset
            or (content_bytes is not None and next_offset > content_bytes)
        ):
            raise RuntimeError(f"exact descent continuation is malformed for {expected}")
        offset = next_offset
    raise RuntimeError(
        f"exact descent exceeded {max_pages} bounded pages for {expected}"
    )


TREE_FOLD_PATHS = (".self_embeddings.json", ".self_graded.json", ".meaning_tree.json")


def _read_tree_fold(root: Path) -> dict[str, Any]:
    """Observe artifact stat identities and the receipt; never open the tree bodies."""

    result: dict[str, Any] = {
        "role": "primary", "status": "UNKNOWN", "files": [],
        "nodes": None, "clusters": None, "latest_receipt": None,
        "stale_paths": None,
        "identity_basis": "stat:size+mtime_ns+inode; not a content hash",
        "node_count_basis": "latest deposit receipt.embedding_counts.total (router embedding entries)",
        "staleness_basis": "tracked worktree mtimes after latest deposit ts; missing tracked paths are stale",
    }
    try:
        for relative in TREE_FOLD_PATHS:
            path = root / relative
            after = path.stat()
            result["files"].append({
                "path": relative, "mtime": after.st_mtime,
                "size": after.st_size, "mtime_ns": after.st_mtime_ns,
                "inode": after.st_ino,
            })
        timing = _latest_timing(root)
        if timing.get('publication',{}).get('mode')=='selected-source-contribution':
            from laplace.representation import source_publication
            actual=source_publication.current(root)
            return {**result,'status':'SCOPED','ui_status':'SCOPED',
                'reason':'Selected Source contribution; unrelated kernel basis/currentness carried, not renewed.',
                'publication_handle':actual['publication_handle'],'mode':actual['mode'],
                'parent_basis':actual['parent_basis'],'retained_basis':actual['retained_basis'],
                'latest_receipt':{'ts':timing['ts'],'mode':actual['mode']},
                'nodes':timing['embedding_counts']['total'],'node_count_basis':'Actual contributed tree/cache count, not a fresh world observation.'}
        counts = timing.get("embedding_counts") or timing
        if any(
            not isinstance(counts.get(key), int) or isinstance(counts.get(key), bool)
            or counts[key] < 0 for key in ("embedded", "total")
        ):
            raise ValueError("deposit receipt lacks integer embedded/total node counts")
        nodes = counts["total"]
        clusters = timing.get("clusters")
        if clusters is not None and (
            not isinstance(clusters, int) or isinstance(clusters, bool) or clusters < 0
        ):
            raise ValueError("DEPOSIT-CLUSTER-COUNT-MALFORMED")
        result.update(nodes=nodes, clusters=clusters)
        if clusters is None:
            result["cluster_count_issue"] = {
                "code": "DEPOSIT-CLUSTER-COUNT-ABSENT", "owner": "scripts/reembed.py",
                "reason": "legacy receipt predates cluster counts; next deposit supplies it",
            }
        result["latest_receipt"] = {
            "ts": timing["ts"], "mode": timing["mode"],
            "embedded": counts["embedded"], "total": counts["total"],
            "device": timing["device"],
            "nodes": nodes, "clusters": clusters,
        }
        deposited = datetime.fromisoformat(timing["ts"].replace("Z", "+00:00"))
        if deposited.tzinfo is None:
            raise ValueError("deposit ts has no timezone")
        deposit_ns = int(deposited.timestamp() * 1_000_000_000)

        def git_paths(*args: str) -> list[str]:
            output = subprocess.run(
                ["git", "--no-optional-locks", "-c", "diff.autoRefreshIndex=false", *args], cwd=root,
                capture_output=True, check=True,
            ).stdout
            return [path for path in os.fsdecode(output).split("\0") if path]

        # Scan tracked mtimes too: a touch or an already-committed edit need not
        # appear in diff/status. NUL records preserve whitespace and odd filenames.
        # HEAD retains staged deletions; the index includes staged additions.
        tracked = set(git_paths("ls-files", "--cached", "--with-tree=HEAD", "-z"))
        untracked = set(git_paths("ls-files", "--others", "--exclude-standard", "-z"))
        consumed_untracked = set(timing.get("untracked_inputs", []))
        stale = []
        generated = set(FOLD_ARTIFACT_PATHS) | {
            "contract/act_costs.jsonl", "contract/close_receipt.json", "contract/close_recovery.json",
        }
        consumed_missing = set(timing.get("missing_tracked_inputs", []))
        root_prefix = os.fspath(root) + os.sep
        for relative in tracked | untracked | consumed_untracked:
            if relative in generated or relative.startswith("contract/reconstruction_receipts/"):
                continue  # producer receipts are observed directly, not recursively re-embedded for freshness
            if "untracked_inputs" in timing and relative in untracked and relative not in consumed_untracked:
                stale.append(relative)
                continue
            try:
                modified = os.lstat(root_prefix + relative).st_mtime_ns
            except FileNotFoundError:
                if relative not in consumed_missing:
                    stale.append(relative)
                continue
            if modified > deposit_ns:
                stale.append(relative)
        result.update(status="STALE" if stale else "CURRENT", stale_paths=len(stale),
                      stale_path_sample=sorted(stale)[:12], consumed_missing_inputs=sorted(consumed_missing))
        result["reason"] = "tracked worktree paths changed since deposit or are missing" if stale else None
    except Exception as exc:  # health faults must not hide the other fold
        result["reason"] = f"{type(exc).__name__}: {exc}"
    return result


def read_health(repo_root: Path | str) -> dict[str, Any]:
    """Report the tree the router opens; historical faults cannot certify or hide it."""

    root = Path(repo_root).resolve()
    tree = _read_tree_fold(root)
    history = _read_side_ref_health(root, history_only=True)
    side = history.pop("fold", {})
    side.update({
        "role": "history",
        "note": "written by the retired semantic cadence; no router reads it",
        "status": history["status"], "reason": history.get("reason"),
        "ui_status": history.get("ui_status", history["status"]),
    })
    return {
        **history, "fold": tree, "tree_fold": tree, "side_ref_fold": side,
        "status": tree["status"], "ui_status": tree["status"],
        "reason": tree.get("reason"),
        "currentness_scope": (
            "tracked source mtimes and deposit receipt; metric integrity and cold recovery "
            "are separate observations"
        ),
    }


def _read_side_ref_health(repo_root: Path | str, *, history_only: bool = False) -> dict[str, Any]:
    """Return the shared fold face; faults are typed data and never block a seat turn."""

    root = Path(repo_root).resolve()
    base = {
        "schema_version": HEALTH_SCHEMA,
        "shared": True,
        "non_blocking": True,
        "authority_effect": "none",
    }
    try:
        fold_ref = _git(root, "rev-parse", "--verify", SEMANTIC_FOLD_REF, check=False)
        if fold_ref:
            output_commit = fold_ref.splitlines()[0]
            manifest = _load_manifest(root, output_commit)
        else:
            if not (root / MANIFEST_PATH).is_file():
                return {**base, "status": "UNKNOWN", "reason": "semantic fold manifest is absent"}
            manifest = _load_manifest(root)
            log = _git(
                root, "log", "-n", "1", "--format=%H", "--", MANIFEST_PATH.as_posix()
            )
            if not log:
                raise RuntimeError("manifest exists outside committed Git history")
            output_commit = log.splitlines()[0]
        source = manifest["source"]
        if history_only:
            # Historical identities are carried as history, never re-certified against
            # live Atlas/source/profile heads on the router's latency-sensitive read.
            return {
                **base, "status": "RETIRED", "reason": "SEMANTIC-SIDE-REF-CADENCE-RETIRED",
                "fold": {
                    "source_commit": source["commit"], "source_tree": source["tree"],
                    "output_commit": output_commit,
                    "manifest_handle": manifest["manifest_handle"],
                    "coverage_handle": source.get("coverage_handle"),
                    "semantic_horizon": manifest.get("semantic_horizon"),
                    "identity_basis": "historical manifest; live currentness not evaluated",
                },
            }
        parent = _git(root, "rev-parse", f"{output_commit}^")
        output_tree = _git(root, "rev-parse", f"{output_commit}^{{tree}}")
        changed = tuple(
            line for line in _git(root, "diff", "--name-only", source["commit"], output_commit).splitlines()
            if line
        )
        allowed = set(manifest["forward_transition"]["allowed_paths"])
        if parent != source["commit"]:
            raise RuntimeError("fold output F is not the declared single successor of S")
        if not set(changed).issubset(allowed):
            raise RuntimeError("S..F contains a path outside the declared fold family")
        artifact_rows = manifest["artifacts"]
        paths = [row["path"] for row in artifact_rows]
        committed_blobs = _tree_blobs(root, output_commit, paths)
        expected_blobs = {row["path"]: row["git_blob"] for row in artifact_rows}
        if committed_blobs != expected_blobs:
            raise RuntimeError("committed semantic artifact blobs disagree with the manifest")
        receipt = _read_outer_receipt(root)
        carried_receipt = receipt["receipt_handle"]
        claimed_source_tuple = _verified_source_tuple(source.get("source_tuple"))
        outer_source_tuple = _verified_source_tuple(receipt.get("source_tuple"))
        if (
            receipt.get("artifact_root") != manifest["artifact_root"]
            or receipt.get("manifest_handle") != manifest["manifest_handle"]
            or receipt.get("output_commit") != output_commit
            or receipt.get("output_tree") != output_tree
            or receipt.get("source_commit") != source["commit"]
            or receipt.get("source_tree") != source["tree"]
            or source.get("source_tuple_handle")
            != claimed_source_tuple["source_tuple_handle"]
            or receipt.get("source_tuple_handle")
            != claimed_source_tuple["source_tuple_handle"]
            or outer_source_tuple != claimed_source_tuple
        ):
            raise RuntimeError("compact semantic fold receipt contradicts S or F")
        candidate = manifest.get("semantic_fold_candidate") or {}
        if (
            receipt.get("exact_descent_index") != candidate.get("exact_descent_index")
            or receipt.get("roots") != candidate.get("roots")
            or receipt.get("register_dictionary") != candidate.get("register_dictionary")
        ):
            raise RuntimeError("outer receipt moved from the committed UP/DOWN candidate")
        head = _git(root, "rev-parse", "HEAD")
        head_tree = _git(root, "rev-parse", "HEAD^{tree}")
        git_current = head in {output_commit, source["commit"]}
        output_ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", output_commit, head], cwd=root
        ).returncode == 0
        source_ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", source["commit"], head], cwd=root
        ).returncode == 0
        if not git_current and not (output_ancestor or source_ancestor):
            raise RuntimeError("current source does not descend from fold output F")
        from laplace.representation.semantic_cadence import current_atlas_observation, current_source_tuple, read_consumption, read_state

        try:
            atlas_observation = current_atlas_observation(root)
        except Exception as exc:  # observatory telemetry cannot erase a valid semantic fold
            atlas_observation = {
                "schema_version": "laplace.semantic-atlas-observation/1",
                "state": "UNKNOWN",
                "reason": f"{type(exc).__name__}: {exc}",
            }
        live_source_tuple = current_source_tuple(
            root,
            source_commit=source["commit"] if git_current else head,
            source_tree=source["tree"] if git_current else head_tree,
            atlas_observation=(
                atlas_observation if atlas_observation.get("state") != "UNKNOWN" else None
            ),
        )
        tuple_delta = _tuple_delta(claimed_source_tuple, live_source_tuple)
        claimed_atlas = claimed_source_tuple.get("atlas")
        live_atlas = live_source_tuple.get("atlas")
        operational_atlas_delta = sorted(
            key
            for key in (
                "drift_token",
                "effective_checkpoint_digest",
                "authority_roots",
            )
            if isinstance(claimed_atlas, Mapping)
            and isinstance(live_atlas, Mapping)
            and claimed_atlas.get(key) != live_atlas.get(key)
        )
        current = git_current and not tuple_delta

        cadence = read_state()
        status = "CURRENT" if current else "STALE"
        if (
            not current
            and cadence.get("status") in {"QUEUED", "RUNNING"}
            and (
                (cadence.get("desired_source") or {}).get("commit") == head
                or ((cadence.get("pending") or {}).get("desired_source") or {}).get("commit")
                == head
            )
        ):
            status = "IN_FLIGHT"
        consumption = read_consumption()
        return {
            **base,
            "status": status,
            "ui_status": "UPDATE-DUE" if status == "STALE" else status,
            "current_source": {"commit": head, "tree": head_tree},
            "source_currentness": {
                "schema_version": "laplace.semantic-fold-source-currentness/1",
                "status": "CURRENT" if current else "MOVED",
                "source_tuple": claimed_source_tuple,
                "claimed_source_tuple_handle": claimed_source_tuple[
                    "source_tuple_handle"
                ],
                "active_source_tuple_handle": live_source_tuple[
                    "source_tuple_handle"
                ],
                "moved_fields": tuple_delta,
                "atlas_token_handle": live_source_tuple["atlas"]["token_handle"],
                "atlas_observation": atlas_observation,
                "operational_atlas_moved_fields": operational_atlas_delta,
                "profile_heads_handle": live_source_tuple["profile_heads_handle"],
                "goal_context_handle": live_source_tuple["goal_context_handle"],
                "policy_roots": live_source_tuple["policy_roots"],
                "read_law": (
                    "semantic development root plus bounded profile/goal/policy heads; exact "
                    "volatile Atlas authority and lifecycle remain adjacent observatory telemetry"
                ),
            },
            "side_refs": {
                "semantic_fold": {
                    "ref": SEMANTIC_FOLD_REF,
                    "commit": output_commit,
                    "tree": output_tree,
                },
                "semantic_fold_receipt": {
                    "ref": SEMANTIC_FOLD_RECEIPT_REF,
                    "object": receipt.get("receipt_object"),
                    "receipt_handle": carried_receipt,
                },
            },
            "fold": {
                "source_commit": source["commit"],
                "source_tree": source["tree"],
                "output_commit": output_commit,
                "output_tree": output_tree,
                "forward_relation": "EXACT" if current else "EXACT-PREDECESSOR",
                "semantic_horizon": manifest["semantic_horizon"],
                "lag_commits": int(_git(root, "rev-list", "--count", f"{output_commit}..{head}"))
                if not current else 0,
                "manifest_handle": manifest["manifest_handle"],
                "coverage_handle": source["coverage_handle"],
                "semantic_fold_receipt_handle": carried_receipt,
                "semantic_fold_index_handle": receipt["exact_descent_index"]["handle"],
                "semantic_register_generation": receipt["exact_descent_index"]["generation"],
            },
            "up_down": {
                "status": "CANONICAL-UP-BATCH-READ-ONLY-DOWN",
                "receipt_handle": carried_receipt,
                "index_handle": receipt["exact_descent_index"]["handle"],
                "register_generation": receipt["exact_descent_index"]["generation"],
                "entries": receipt["exact_descent_index"]["entries"],
                "reference_law": receipt["reference_law"],
            },
            "coverage": {
                "required_complete": True,
                "classes": source["source_classes"],
            },
            "profile_handles": source["profile_handles"],
            "artifacts": {
                "root": manifest["artifact_root"],
                "count": len(manifest["artifacts"]),
                "bytes": sum(row["bytes"] for row in manifest["artifacts"]),
                "cache_sidecar_consistent": True,
            },
            "runtime": manifest["runtime"],
            "latest_receipt": manifest["runtime"]["latest_receipt"],
            "semantic_reachability": manifest["semantic_reachability"],
            "cadence": {**manifest["cadence"], "live_state": cadence},
            "consumption": {
                **consumption,
                "state": "OBSERVED" if consumption.get("latest") else "AWAITING-LIVE-CONSUMPTION",
            },
            "reason": None if current else (
                "source tuple moved: " + ", ".join(tuple_delta)
                if tuple_delta else "source advanced outside the declared S->F transition"
            ),
        }
    except Exception as exc:  # noqa: BLE001 - health is a read-only observation face
        return {**base, "status": "REFUSED", "reason": f"{type(exc).__name__}: {exc}"}


__all__ = [
    "FOLD_ARTIFACT_PATHS",
    "HEALTH_SCHEMA",
    "MANIFEST_PATH",
    "MANIFEST_SCHEMA",
    "SEMANTIC_FOLD_RECEIPT_REF",
    "SEMANTIC_FOLD_REF",
    "build_outer_receipt",
    "build_manifest",
    "build_reachability_witnesses",
    "build_semantic_fold_index",
    "publish_fold_refs",
    "read_health",
    "semantic_fold_down",
    "validate_fold_candidate",
]
