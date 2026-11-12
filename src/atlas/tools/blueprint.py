"""Thin actuator for the self-hosted Atlas blueprint organ.

All semantics live in ``atlas.blueprint``.  This command only binds the checked-in manifest,
the canonical store, the real BGE encoder and an observed runtime/device receipt.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..blueprint import (
    BLUEPRINT_EMBEDDING_BATCH_POLICY,
    GENESIS_GENERATION,
    DesignDocument,
    EvidenceFinding,
    GenerationParentRefused,
    ImplementationBinding,
    current_blueprint_generation,
    blueprint_source_currency,
    pour_blueprint,
    reconstruct_blueprint,
)
from ..encoders.base import EncoderRuntimeEvidence, EncoderSpec
from ..encoders.bge_onnx import BgeOnnxEncoder, resolve_model_dir
from ..history import GradeAxisContract, ProducerRef, SeatRole, SourceRef
from ..ids import chash, hash_bytes
from ..runtime import collect_runtime_receipt
from ..spectral_pour import PourMetadata, SpectralPourContract
from ..store import ConceptricStore

CONTAINER_ROOT = Path(__file__).resolve().parents[3] / "atlas"  # src/atlas since core consolidation R2: the container is <checkout>/atlas
ROOT = (CONTAINER_ROOT.parent if (CONTAINER_ROOT.parent / "src/laplace").is_dir()
        else CONTAINER_ROOT)
DEFAULT_MANIFEST = CONTAINER_ROOT / "blueprint_manifest.json"
PROVIDER_EQUIVALENCE_PROBES = (
    "per-lens encoder identity and exact source custody",
    "spectral diffusion routes through retained frames",
    "GPU provider drift must not silently change vector geometry",
    "mutation repairs dirty ancestry under one atomic generation",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "atlas.blueprint-manifest/1":
        raise SystemExit("blueprint manifest schema is unknown")
    return raw


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=False,
    )
    if result.returncode:
        raise SystemExit(json.dumps({
            "status": "REFUSED",
            "reason": "blueprint-pinned-source-refused",
            "command": list(args),
            "stderr": result.stderr.decode("utf-8", errors="replace"),
        }))
    return result.stdout


def _glob_matches(path: str, pattern: str) -> bool:
    """Treat ``**/`` as zero-or-more path components, including a direct child."""

    candidates = {pattern}
    while "/**/" in pattern:
        pattern = pattern.replace("/**/", "/", 1)
        candidates.add(pattern)
    return any(fnmatch.fnmatchcase(path, candidate) for candidate in candidates)


def _pinned_documents(
    raw: dict[str, Any], repo_root: Path,
) -> tuple[tuple[DesignDocument, ...], dict[str, bytes], str, dict[str, int]]:
    """Resolve every blueprint document from the manifest's exact HEAD commit."""

    commit_sha = raw.get("commit_sha")
    if not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit_sha):
        raise SystemExit("blueprint manifest requires a full lowercase commit_sha")
    pinned = _git(repo_root, "rev-parse", "--verify", commit_sha + "^{commit}").decode().strip()
    head = _git(repo_root, "rev-parse", "HEAD").decode().strip()
    if pinned != commit_sha:
        raise SystemExit("blueprint manifest commit_sha must resolve to a commit")
    # THE PROPERTY, NOT THE SPELLING (RUL-20260914-a-gate-that-only-refuses-legitimate-work-is-
    # retired). Requiring commit_sha == HEAD is unsatisfiable by construction: the commit that
    # carries the manifest cannot know its own hash, so repinning always chases HEAD by one. What
    # the pour actually needs is that the SOURCES it reads at the pin are the sources at HEAD -
    # a manifest-only commit changes nothing the pour reads. So: the pin must be an ancestor of
    # HEAD (never ahead of it, never on another branch) and no tracked path may differ between
    # the two. A source change after the pin is still refused, by name.
    if head != commit_sha:
        try:
            _git(repo_root, "merge-base", "--is-ancestor", commit_sha, head)
        except Exception as exc:  # non-zero exit: not an ancestor
            raise SystemExit(
                f"blueprint manifest commit_sha {commit_sha[:12]} is not an ancestor of HEAD "
                f"{head[:12]}; repin the manifest"
            ) from exc
        moved = [line.split("\t", 1)[-1] for line in
                 _git(repo_root, "diff", "--name-only", commit_sha, head).decode().splitlines()
                 if line.strip() and line.strip() != "atlas/blueprint_manifest.json"]
        if moved:
            raise SystemExit(
                "blueprint manifest commit_sha is behind HEAD and these tracked paths moved "
                "between them: " + ", ".join(sorted(moved)[:8])
                + (f" (+{len(moved) - 8} more)" if len(moved) > 8 else "")
            )
    tree: dict[str, tuple[str, str, str]] = {}
    for record in _git(repo_root, "ls-tree", "-r", "-z", commit_sha).split(b"\0"):
        if not record:
            continue
        meta, raw_path = record.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        tree[raw_path.decode("utf-8")] = (mode, kind, oid)
    documents: list[DesignDocument] = []
    contents: dict[str, bytes] = {}
    selector_counts: dict[str, int] = {}
    for selector in raw["documents"]:
        keys = set(selector)
        if "path" in selector:
            if keys != {"path", "role", "document_id"}:
                raise SystemExit("blueprint path document schema is invalid")
            matches = [str(selector["path"])]
            document_ids = [str(selector["document_id"])]
            selector_name = str(selector["path"])
        elif "glob" in selector:
            if keys != {"glob", "role"}:
                raise SystemExit("blueprint glob document schema is invalid")
            pattern = str(selector["glob"])
            matches = [path for path in sorted(tree) if _glob_matches(path, pattern)]
            document_ids = matches
            selector_name = pattern
        else:
            raise SystemExit("blueprint document requires exactly one path or glob")
        if not matches:
            raise SystemExit(f"blueprint source selector matches nothing: {selector_name}")
        selector_counts[selector_name] = len(matches)
        for path, document_id in zip(matches, document_ids, strict=True):
            if path in contents:
                raise SystemExit(f"blueprint source selectors overlap: {path}")
            try:
                mode, kind, oid = tree[path]
            except KeyError as exc:
                raise SystemExit(f"blueprint pinned source is absent: {path}") from exc
            if mode not in {"100644", "100755"} or kind != "blob":
                raise SystemExit(f"blueprint pinned source is not a regular file: {path}")
            documents.append(DesignDocument(path, str(selector["role"]), document_id))
            contents[path] = _git(repo_root, "cat-file", "blob", oid)
    return tuple(documents), contents, commit_sha, selector_counts


def _prepare_authority_epoch(store_path: Path) -> dict[str, Any]:
    """REFUSED BY THE SEAL, and correctly (atlas/tests/test_seal.py, 2026-09-15).

    The adoption transition is implemented engine-side in src/laplace/atlas_bridge.py, so calling
    it from inside the atlas package means the atlas importing laplace and mutating sys.path to do
    it - the seal is one-way and this is the wrong way. The first version of this function did
    exactly that and the floor caught it.

    The sequence is two acts by the orchestrator, back to back with no file change between, which
    is what the checkpoint's dirty-path pin actually requires:

        /usr/bin/python3 scripts/atlas_adopt_authority.py --store atlas/stores/blueprint --reason '<why>'
        PYTHONPATH=src /usr/bin/python3 -m atlas.tools.blueprint pour --parent-generation <id>

    Making --adopt work in one process needs prepare_authority_epoch to live in the atlas package
    with the bridge re-exporting it: WO-20260915-the-adoption-door-belongs-to-the-atlas.
    """

    raise SystemExit(
        "--adopt is refused: it would make the atlas import laplace, which the seal forbids. "
        "Run `scripts/atlas_adopt_authority.py --store <store> --reason <why>` first, then pour "
        "with no file change between (WO-20260915-the-adoption-door-belongs-to-the-atlas)."
    )


def _cluster_size_row(generation: object) -> list[dict[str, Any]]:
    rows = []
    for depth in sorted({int(cluster["depth"]) for cluster in generation.clusters}):
        nodes = [cluster for cluster in generation.clusters if int(cluster["depth"]) == depth]
        sizes = sorted(len(cluster["member_logical_ids"]) for cluster in nodes)
        rows.append({
            "grade": depth,
            "coarse_nodes": len(nodes),
            "descendant_memberships": sum(sizes),
            "sorted_sizes": sizes,
            "terminal_leaf_memberships": sum(
                len(cluster["member_logical_ids"])
                for cluster in nodes if not cluster["child_cluster_ids"]
            ),
            "stops": {
                reason: sum(cluster["stop_reason"] == reason for cluster in nodes)
                for reason in sorted({
                    cluster["stop_reason"] for cluster in nodes if cluster["stop_reason"]
                })
            },
        })
    return rows


def _store_target(raw: dict[str, Any], candidate_store: Path | None) -> tuple[Path, str]:
    """Resolve the manifest authority or an explicitly non-authoritative candidate.

    A candidate is never promotion: it can be poured, queried and compared, but the
    checked-in manifest remains the only path production readers open.  Refusing an
    override that resolves back to that path prevents a command labelled candidate from
    mutating authority under a reassuring name.
    """
    # Accept the old engine-relative manifest spelling in an exported container too.
    store_key = str(raw["store"]).removeprefix("atlas/")
    authority = (CONTAINER_ROOT / store_key).resolve()
    if candidate_store is None:
        return authority, "manifest-authority"
    candidate = candidate_store.expanduser().resolve()
    if candidate == authority:
        raise SystemExit(
            "--candidate-store resolves to the manifest authority; omit the flag for an "
            "authoritative act or choose an isolated candidate path"
        )
    return candidate, "candidate-no-promotion-claim"


def _provider_names(encoder: BgeOnnxEncoder) -> tuple[str, ...]:
    model: object = encoder._load()  # the CLI intentionally fires the lazy runtime boundary
    current: object = model
    for name in ("model", "model"):
        current = getattr(current, name, current)
    getter = getattr(current, "get_providers", None)
    if getter is None:
        return ()
    return tuple(str(item) for item in getter())


def _runtime_encoder(
    batch_size: int, model_dir: Path | None = None, *, repo_root: Path = ROOT,
) -> tuple[BgeOnnxEncoder, object, tuple[str, ...], EncoderRuntimeEvidence]:
    requested = ("CUDAExecutionProvider", "CPUExecutionProvider")
    model_dir = resolve_model_dir(model_dir, repo_root=repo_root)
    encoder = BgeOnnxEncoder(model_dir=model_dir, providers=requested, batch_size=batch_size, threads=1)
    selected_vectors = [encoder.embed([probe])[0] for probe in PROVIDER_EQUIVALENCE_PROBES]
    providers = _provider_names(encoder)
    cuda = "CUDAExecutionProvider" in providers
    compared_providers = ("CUDAExecutionProvider", "CPUExecutionProvider") if cuda else (
        "CPUExecutionProvider",
    )
    observed_max_drift = 0.0
    if cuda:
        cpu = BgeOnnxEncoder(
            model_dir=model_dir, threads=1,
            providers=("CPUExecutionProvider",),
            batch_size=batch_size,
        )
        cpu_vectors = [cpu.embed([probe])[0] for probe in PROVIDER_EQUIVALENCE_PROBES]
        cpu_providers = _provider_names(cpu)
        if cpu_providers != ("CPUExecutionProvider",):
            raise SystemExit(
                "provider-equivalence CPU reference did not bind only CPUExecutionProvider: "
                f"{cpu_providers!r}"
            )
        observed_max_drift = max(
            abs(left - right)
            for selected, reference in zip(selected_vectors, cpu_vectors, strict=True)
            for left, right in zip(selected, reference, strict=True)
        )
    evidence = EncoderRuntimeEvidence(
        encoder.spec.spec_id,
        chash({
            "schema_version": "atlas.provider-equivalence-probes/1",
            "embedding_batch_policy": BLUEPRINT_EMBEDDING_BATCH_POLICY,
            "probes": list(PROVIDER_EQUIVALENCE_PROBES),
        }),
        compared_providers,
        encoder.spec.determinism_metric,
        observed_max_drift,
        encoder.spec.determinism_tolerance,
    )
    runtime = collect_runtime_receipt(
        ROOT,
        requested_device="cuda",
        observed_devices=("cpu", "cuda") if cuda else ("cpu",),
        selected_device="cuda" if cuda else "cpu",
        utilization={"cuda": None, "cpu": None} if cuda else {"cpu": None},
        fallback_reason=None if cuda else "ONNX runtime did not expose CUDAExecutionProvider",
        observed_at=_now(),
    )
    return encoder, runtime, providers, evidence


def _metadata(
    manifest_path: Path,
    runtime: object,
    encoder_runtime_evidence: EncoderRuntimeEvidence,
) -> PourMetadata:
    return PourMetadata(
        _now(),
        SeatRole.EGO,
        SeatRole.EGO,
        "atlas-s1-live-blueprint",
        (
            SourceRef(
                "atlas:blueprint-manifest",
                hash_bytes(manifest_path.read_bytes()),
                str(manifest_path.relative_to(ROOT)),
            ),
        ),
        runtime,  # type: ignore[arg-type]
        ProducerRef("openai", "gpt-5.6-sol", "atlas-s1-live"),
        encoder_runtime_evidence,
    )


def _contract(raw: dict[str, Any]) -> SpectralPourContract:
    spectral = raw["spectral"]
    if spectral.get("embedding_batch_policy") != BLUEPRINT_EMBEDDING_BATCH_POLICY:
        raise SystemExit("blueprint embedding batch policy is absent or unsupported")
    depth = spectral.get("max_depth")
    order = (
        ("cluster",) + tuple(f"cluster:{grade}" for grade in range(2, depth + 1))
        + ("leaf",)
        if depth is not None else ("cluster", "leaf")
    )
    branching = spectral.get("branching")
    return SpectralPourContract(
        spectral["assumption"],
        spectral["fibre"],
        GradeAxisContract(
            spectral["grade_contract_id"],
            spectral["axis"],
            order,
        ),
        spectral["lens_id"],
        EncoderSpec.from_dict(spectral["encoder_spec"]),
        spectral["metric_version"],
        spectral["cluster_count"],
        spectral["chi"],
        spectral["phi"],
        placement_operator=spectral.get(
            "placement_operator", "cosine-affinity-spectral-fixed-k/1"
        ),
        leaf_max=spectral.get("leaf_max"),
        branching=tuple(branching) if isinstance(branching, list) else branching,
        max_depth=depth,
        grade_chi=tuple(spectral.get("grade_chi", ())),
        grade_phi=tuple(spectral.get("grade_phi", ())),
    )


def _status_summary(
    generation: object,
    store: ConceptricStore,
    *,
    dataset_roots: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Bounded operator truth; ``status --full`` remains the forensic projection."""
    source_roots = generation.source_roots
    clauses = generation.clauses
    clusters = generation.clusters
    bindings = generation.bindings
    findings = generation.findings
    entry_role = generation.entry_role
    role_fibres = generation.role_fibres
    currency = blueprint_source_currency(
        ROOT, generation, container_root=CONTAINER_ROOT, dataset_roots=dataset_roots,
    )
    moved = currency["moved"]
    proof_counts: dict[str, int] = {}
    for binding in bindings:
        state = str(binding["proof_state"])
        proof_counts[state] = proof_counts.get(state, 0) + 1
    missing_trails = sum(not clause.get("trail") for clause in clauses)
    replayed = store.replay()
    broken_subject_versions = []
    for clause in clauses:
        subject = replayed.graph_objects.get(str(clause.get("subject_id", "")))
        edge = replayed.graph_edges.get(str(clause.get("version_edge_id", "")))
        if (
            not clause.get("subject_handle")
            or subject is None
            or subject.content_handle != clause.get("subject_handle")
            or edge is None
            or edge.relation != "version-of"
            or edge.source_object_id != clause.get("object_id")
            or edge.target_object_id != clause.get("subject_id")
        ):
            broken_subject_versions.append(str(clause.get("logical_id", "unknown")))
    unreceipted_placement_roles = []
    fibre_pours = generation.fibre_pours
    for role, receipt in fibre_pours.items():
        observation = replayed.observation_events.get(receipt["observation_event_id"])
        if observation is None or not observation.payload.get("placement_operator"):
            unreceipted_placement_roles.append(role)
    role_by_logical = {
        clause["logical_id"]: clause.get("design_role") for clause in clauses
    }
    mixed_role_clusters = []
    misplaced_role_clusters = []
    for cluster in clusters:
        roles = sorted({
            role_by_logical.get(logical_id)
            for logical_id in cluster["member_logical_ids"]
            if role_by_logical.get(logical_id)
        })
        if len(roles) > 1:
            mixed_role_clusters.append({"cluster_id": cluster["cluster_id"], "roles": roles})
        declared_role = cluster.get("design_role")
        if cluster.get("fibre") != role_fibres.get(declared_role):
            misplaced_role_clusters.append({
                "cluster_id": cluster["cluster_id"],
                "design_role": declared_role,
                "actual_fibre": cluster.get("fibre"),
                "declared_fibre": role_fibres.get(declared_role),
            })
    finding_by_id = {item["finding_id"]: item for item in findings}
    derivation_gaps = []
    for binding in bindings:
        operator_roles = tuple(binding.get("operator_roles", ()))
        required = tuple(binding.get("required_finding_ids", ()))
        if operator_roles and not required:
            derivation_gaps.append({
                "implementation_path": binding["implementation_path"],
                "reason": "operator proposal has no required findings",
            })
        for finding_id in required:
            finding = finding_by_id.get(finding_id)
            if finding is None:
                derivation_gaps.append({
                    "implementation_path": binding["implementation_path"],
                    "finding_id": finding_id,
                    "reason": "required finding absent from generation",
                })
                continue
            linked = any(
                (edge := replayed.graph_edges.get(edge_id)) is not None
                and edge.relation == "derives-from-evidence"
                and edge.source_object_id == binding["implementation_object_id"]
                and edge.target_object_id == finding["object_id"]
                for edge_id in finding["derivation_edge_ids"]
            )
            if not linked:
                derivation_gaps.append({
                    "implementation_path": binding["implementation_path"],
                    "finding_id": finding_id,
                    "reason": "typed derivation edge absent",
                })
    gates = {
        "source_roots_fresh": "PASS" if not moved else "WARNING",
        "heading_identity": "PASS" if missing_trails == 0 else "RED",
        "fibre_local_routing": (
            "PASS" if not mixed_role_clusters and not misplaced_role_clusters else "RED"
        ),
        "stable_subject_version_topology": (
            "PASS" if not broken_subject_versions else "RED"
        ),
        "placement_operator_receipted": (
            "PASS" if not unreceipted_placement_roles else "RED"
        ),
        "operator_evidence_derivation": (
            "PASS" if not derivation_gaps else "RED"
        ),
        "diffusion_placement_admission": "NOT_YET",
        "independent_implementation_proof": (
            "PASS" if any(
                state in {"planted-proved", "scale-validated"}
                for state in proof_counts
            ) else "NOT_YET"
        ),
        "cold_mutation_durability": "NOT_YET",
    }
    return {
        "schema_version": "atlas.blueprint-status/1",
        "overall": "RED" if "RED" in gates.values() else "IN_PROGRESS",
        "generation_id": generation.generation_id,
        "encoder_id": generation.encoder_id,
        "embedding_batch_policy": generation.embedding_batch_policy,
        "entry_role": entry_role,
        "role_fibres": dict(sorted(role_fibres.items())),
        "counts": {
            "clauses": len(clauses),
            "clusters": len(clusters),
            "implementation_bindings": len(bindings),
            "evidence_findings": len(findings),
            "events": len(store.events()),
        },
        "proof_states": dict(sorted(proof_counts.items())),
        "gates": gates,
        "source_currency": currency,
        "reds": {
            "clauses_missing_heading_identity": missing_trails,
            "clusters_mixing_design_fibres": mixed_role_clusters,
            "clusters_outside_declared_role_fibre": misplaced_role_clusters,
            "broken_subject_versions": broken_subject_versions,
            "unreceipted_placement_roles": unreceipted_placement_roles,
            "derivation_gaps": derivation_gaps,
        },
        "activity": "idle; commands are discrete acts, not a background build",
        "next": "judged version authority, sparse diffusion admission, cold mutation durability",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--candidate-store",
        type=Path,
        default=None,
        help=(
            "pour/query/status against an isolated non-authoritative store; the manifest "
            "authority is never promoted or replaced"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    pour = sub.add_parser("pour")
    pour.add_argument(
        "--parent-generation",
        default=GENESIS_GENERATION,
        help="current generation id; genesis is valid only for an empty store",
    )
    pour.add_argument(
        "--adopt", action="store_true",
        help="adopt the current authority epoch and immediately pour in this process",
    )
    query = sub.add_parser("query")
    query.add_argument("goal")
    query.add_argument("--top-k", type=int, default=5)
    query.add_argument("--beam", type=int, default=3)
    query.add_argument(
        "--role",
        default=None,
        help="explicit supporting jurisdiction; omitted means the governing entry role",
    )
    status = sub.add_parser("status")
    status.add_argument("--full", action="store_true")
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    raw = _load(manifest_path)
    dataset_roots = {
        name: (manifest_path.parent / root).resolve()
        for name, root in raw.get("dataset_roots", {}).items()
    }
    store_path, custody = _store_target(raw, args.candidate_store)
    store_role = "blueprint-generation" if args.candidate_store is None else None
    extra_authority_files = (
        (ROOT / "src/laplace/atlas_bridge.py",)
        if (ROOT / "src/laplace/atlas_bridge.py").is_file() else ()
    )

    if args.command == "status":
        store = ConceptricStore(
            store_path, read_only=True, expected_store_role=store_role,
            extra_authority_files=extra_authority_files,
        )
        generation = current_blueprint_generation(store)
        projection = generation.to_dict() if args.full else _status_summary(
            generation, store, dataset_roots=dataset_roots,
        )
        projection = {
            **projection,
            "store_root": str(store_path),
            "custody": custody,
            "promotion_claim": "none" if args.candidate_store else "manifest authority",
        }
        print(json.dumps(projection, indent=1, ensure_ascii=False))
        return 0

    encoder, runtime, providers, encoder_runtime_evidence = _runtime_encoder(
        raw["spectral"]["batch_size"], args.model_dir
    )
    metadata = _metadata(manifest_path, runtime, encoder_runtime_evidence)
    if args.command == "pour":
        documents, source_contents, commit_sha, selector_counts = _pinned_documents(raw, ROOT)
        adoption_receipt = _prepare_authority_epoch(store_path) if args.adopt else None
        store = ConceptricStore(
            store_path, expected_store_role=store_role,
            extra_authority_files=extra_authority_files,
        )
        try:
            generation = pour_blueprint(
                store,
                ROOT,
                documents,
                tuple(ImplementationBinding(
                    item["clause_anchor"],
                    item["implementation_path"],
                    item["implementation_kind"],
                    item["proof_state"],
                    tuple(item["evidence_handles"]),
                    item["builder"],
                    item["judge"],
                    item.get("implementation_scope", "entire-clause"),
                    tuple(item.get("operator_roles", ())),
                    tuple(item.get("required_finding_ids", ())),
                ) for item in raw["bindings"]),
                encoder,
                _contract(raw),
                metadata,
                parent_generation=args.parent_generation,
                container_root=CONTAINER_ROOT,
                dataset_roots=dataset_roots,
                entry_role=raw["authority"]["entry_role"],
                findings=tuple(EvidenceFinding(
                    item["finding_id"],
                    item["evidence_path"],
                    item["file_digest"],
                    item["line_start"],
                    item["line_end"],
                    item["evidence_needle"],
                    item["statement"],
                    item["relation"],
                    item["evidence_state"],
                    tuple(item["operator_roles"]),
                    item["proof_scope"],
                    item["design_role"],
                    tuple(item.get("dependency_handles", ())),
                ) for item in raw.get("findings", ())),
                source_contents=source_contents,
                commit_sha=commit_sha,
            )
        except GenerationParentRefused as exc:
            print(json.dumps({
                "status": "REFUSED", "reason": exc.reason,
                "message": exc.message, **exc.detail,
            }))
            return 1
        print(json.dumps({
            "generation_id": generation.generation_id,
            "pour_handle": generation.pour_handle,
            "clauses": len(generation.clauses),
            "clusters": len(generation.clusters),
            "bindings": len(generation.bindings),
            "entry_role": generation.entry_role,
            "role_fibres": generation.role_fibres,
            "onnx_providers": providers,
            "runtime_receipt": runtime.to_dict(),
            "encoder_runtime_evidence": encoder_runtime_evidence.to_dict(),
            "commit_sha": commit_sha,
            "document_selectors": selector_counts,
            "documents": len(documents),
            "pour_receipt": generation.receipt.to_dict(),
            "cluster_size_by_grade": _cluster_size_row(generation),
            "adoption_receipt": adoption_receipt,
            "store_root": str(store_path),
            "custody": custody,
            "promotion_claim": "none" if args.candidate_store else "manifest authority",
        }, indent=1, ensure_ascii=False))
        return 0

    store = ConceptricStore(
        store_path, read_only=True, expected_store_role=store_role,
        extra_authority_files=extra_authority_files,
    )
    result = reconstruct_blueprint(
        store,
        ROOT,
        args.goal,
        encoder,
        metadata,
        top_k=args.top_k,
        beam=args.beam,
        role=args.role,
        container_root=CONTAINER_ROOT,
        dataset_roots=dataset_roots,
    )
    print(json.dumps({
        "generation_id": result.generation_id,
        "materialization_id": result.materialization_id,
        "cache_hit": result.cache_hit,
        "source_currency": result.source_currency,
        "traversed_cluster_ids": result.traversed_cluster_ids,
        "rejected_cluster_ids": result.rejected_cluster_ids,
        "coverage": result.coverage,
        "results": result.results,
        "onnx_providers": providers,
        "encoder_runtime_evidence": encoder_runtime_evidence.to_dict(),
        "store_root": str(store_path),
        "custody": custody,
        "promotion_claim": "none" if args.candidate_store else "manifest authority",
    }, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
