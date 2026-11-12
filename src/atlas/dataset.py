"""A pinned dataset manifest and the single source-to-blueprint ingest door.

Identity covers only the versioned core. Later judgements are separately hashed and
reference that core; adding a verdict never renames the dataset or its receipts.
"""
from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .blueprint import DesignDocument, GENESIS_GENERATION, pour_blueprint
from .encoders.base import EncoderSpec
from .errors import AtlasError
from .history import GradeAxisContract, SourceRef
from .ids import chash
from .segment import SEGMENTATION_RECIPE_VERSION, segmenter_for
from .spectral_pour import SpectralPourContract
from .store import ConceptricStore

SCHEMA = "atlas.dataset-manifest/1"
# scripts/export_atlas_snapshot.py: SEALED_PREFIXES, without importing the engine.
SEALED_PREFIXES = ("soul/", "soul_corpus/sealed/", "archive/soul_dump/",
                   "soul_corpus/", "soul_vectors/")
DERIVED_FROM_SEALED_PATHS = (
    "archive/self_shard/.upfold_vec_cache.json", ".meaning_tree.json", ".self_graded.json",
    ".self_embeddings.json", "SELF_SHARD_INDEX.md",
)
CORE_FIELDS = {"dataset_id", "store", "sources", "pinned_commit", "segmentation",
               "encoder", "spectral", "sealed_prefixes"}


class DatasetRefused(AtlasError):
    reason = "dataset-refused"


def _require(ok: bool, issue: str, **detail: Any) -> None:
    if not ok:
        raise DatasetRefused(issue, owner="WO-20260914-s2-04-one-door-the-dataset-manifest",
                             issue=issue, **detail)


def _relative(value: str) -> str:
    _require(isinstance(value, str) and bool(value), "RELATIVE-PATH-REQUIRED")
    path = PurePosixPath(value)
    _require(not path.is_absolute() and ".." not in path.parts and "\\" not in value,
             "PATH-ESCAPES-ROOT", path=value)
    return path.as_posix()


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    _require(result.returncode == 0, "PINNED-SOURCE-UNAVAILABLE",
             command=list(args), error=result.stderr.decode(errors="replace"))
    return result.stdout


def _sealed(path: str, prefixes: list[str]) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix.rstrip("/") + "/")
               for prefix in prefixes)


def resolve_sources(core: Mapping[str, Any], repo_root: Path) -> tuple[tuple[DesignDocument, ...], dict[str, bytes]]:
    """Resolve Git tree names and blobs, never use a working-tree source as input."""
    pin = core.get("pinned_commit")
    _require(isinstance(pin, str) and bool(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", pin)),
             "PINNED-COMMIT-REQUIRED")
    _require(_git(repo_root, "rev-parse", "--verify", pin + "^{commit}").decode().strip() == pin,
             "PINNED-COMMIT-NOT-EXACT")
    tree = {}
    for record in _git(repo_root, "ls-tree", "-r", "-z", pin).split(b"\0"):
        if record:
            meta, raw_path = record.split(b"\t", 1)
            mode, kind, oid = meta.decode().split()
            tree[raw_path.decode("utf-8")] = (mode, kind, oid)
    documents, contents, document_ids = [], {}, set()
    prefixes = list(core["sealed_prefixes"])
    for source in core["sources"]:
        _require(set(source) <= {"path", "glob", "include", "exclude", "role", "document_id_from", "kind", "row_id_field"}
                 and {"include", "exclude", "role", "document_id_from", "kind"} <= set(source)
                 and ("path" in source) != ("glob" in source), "SOURCE-SCHEMA-INVALID")
        pattern = _relative(source.get("path", source.get("glob")))
        _require(not _sealed(pattern, prefixes), "SEALED-SOURCE", path=pattern)
        _require(isinstance(source["role"], str) and bool(source["role"].strip()), "SOURCE-ROLE-REQUIRED")
        _require(source["kind"] in {"source", "typed-row"}, "SOURCE-KIND-UNIMPLEMENTED", kind=source["kind"])
        if source["kind"] == "typed-row":
            _require(isinstance(source.get("row_id_field"), str)
                     and bool(source["row_id_field"].strip()), "ROW-ID-FIELD-REQUIRED")
        else:
            _require("row_id_field" not in source, "ROW-ID-FIELD-ONLY-FOR-TYPED-ROWS")
        _require(source["document_id_from"] in {"path", "stem"}, "DOCUMENT-ID-LAW-UNKNOWN")
        for key in ("include", "exclude"):
            _require(isinstance(source[key], list) and all(isinstance(x, str) for x in source[key]),
                     "SOURCE-FILTER-INVALID", field=key)
        matches = [path for path in sorted(tree)
                   if (path == pattern if "path" in source else PurePosixPath(path).match(pattern))]
        _require(bool(matches), "SOURCE-MATCHES-NOTHING", pattern=pattern)
        # Refuse any sealed resolution before filtering: excludes cannot launder a broad root.
        for path in matches:
            _require(not _sealed(path, prefixes), "SEALED-SOURCE", path=path)
            _require(path not in DERIVED_FROM_SEALED_PATHS, "DERIVED-FROM-SEALED-SOURCE", path=path)
        selected = [path for path in matches
                    if (not source["include"] or any(fnmatch.fnmatchcase(path, x) for x in source["include"]))
                    and not any(fnmatch.fnmatchcase(path, x) for x in source["exclude"])]
        _require(bool(selected), "SOURCE-FILTER-EMPTY", pattern=pattern)
        for path in selected:
            mode, kind, oid = tree[path]
            # Symlinks cannot smuggle sealed or out-of-tree content through an innocent name.
            _require(mode in {"100644", "100755"} and kind == "blob", "SOURCE-NOT-REGULAR", path=path)
            _require(path not in contents, "SOURCE-OVERLAP", path=path)
            if source["kind"] == "typed-row":
                _require(path.lower().endswith(".jsonl"), "TYPED-ROWS-REQUIRE-JSONL", path=path)
            identity = path if source["document_id_from"] == "path" else PurePosixPath(path).stem
            identity = f"{core['dataset_id']}:{identity}"
            _require(identity not in document_ids, "DOCUMENT-ID-COLLISION", document_id=identity)
            document_ids.add(identity)
            documents.append(DesignDocument(path, source["role"], identity, source["kind"],
                                             source.get("row_id_field")))
            contents[path] = _git(repo_root, "cat-file", "blob", oid)
    # A single-file entry cannot masquerade as a manuscript root. Explicit multi-file
    # selectors define a byte extent, not a transitive TeX build; outside edges ride the receipt.
    frontier = tex_include_frontier(contents)
    _require(len(contents) != 1 or not frontier, "TEX-INCLUDE-OUTSIDE-DECLARED-ROOT",
             frontier=frontier)
    return tuple(documents), contents


def tex_include_frontier(contents: Mapping[str, bytes]) -> list[dict[str, str]]:
    frontier = []
    for path, data in contents.items():
        if not path.endswith(".tex"):
            continue
        uncommented = re.sub(rb"(?m)(?<!\\)%[^\n]*", b"", data)
        for ref in re.findall(rb"\\(?:input|include)\s*\{([^}]+)\}", uncommented):
            name = ref.decode("utf-8")
            name = name if name.endswith(".tex") else name + ".tex"
            candidates = [str(PurePosixPath(path).parent / name), name]
            if not any(candidate in contents for candidate in candidates):
                frontier.append({"path": path, "include": name,
                                 "issue": "TEX-INCLUDE-OUTSIDE-DECLARED-ROOT",
                                 "disposition": "not-followed; coverage is declared source bytes only"})
    return frontier


def validate_core(core: Mapping[str, Any]) -> None:
    _require(bool(core.get("pinned_commit")), "PINNED-COMMIT-REQUIRED")
    _require(set(core) - {"source_repo"} == CORE_FIELDS, "MANIFEST-CORE-FIELDS", missing=sorted(CORE_FIELDS-set(core)),
             unexpected=sorted(set(core)-CORE_FIELDS-{"source_repo"}))
    if "source_repo" in core:
        _require(_relative(core["source_repo"]) == ".", "SOURCE-REPO-MUST-BE-ROOT")
    _require(isinstance(core["dataset_id"], str) and re.fullmatch(r"[A-Za-z0-9_.-]+", core["dataset_id"]) is not None,
             "DATASET-ID-INVALID")
    store = _relative(core["store"])
    _require(store not in {".", "src"}, "STORE-PATH-INVALID")
    prefixes = core["sealed_prefixes"]
    _require(isinstance(prefixes, list) and bool(prefixes), "SEALED-PREFIXES-REQUIRED")
    for prefix in prefixes:
        _relative(prefix)
    _require(all(_sealed(prefix.rstrip("/"), prefixes) for prefix in SEALED_PREFIXES),
             "SEALED-PREFIXES-NARROWED")
    _require(not _sealed(store, prefixes), "SEALED-STORE", path=store)
    _require(isinstance(core["sources"], list) and bool(core["sources"]), "SOURCES-REQUIRED")
    seg = core["segmentation"]
    _require(set(seg) == {"generation", "target_tokens", "hard_cap_tokens", "segmenters"}
             and seg["generation"] == SEGMENTATION_RECIPE_VERSION, "SEGMENTATION-GENERATION-UNKNOWN")
    _require(all(type(seg[k]) is int and seg[k] > 0 for k in ("target_tokens", "hard_cap_tokens"))
             and seg["target_tokens"] <= seg["hard_cap_tokens"] <= 512, "SEGMENTATION-DIAL-INVALID")
    enc = core["encoder"]
    _require(set(enc) == {"generation", "model_dir", "spec"} and bool(enc["model_dir"]), "ENCODER-MODEL-DIR-REQUIRED")
    spec = EncoderSpec.from_dict(enc["spec"])
    _require(enc["generation"] == spec.spec_id, "ENCODER-GENERATION-MISMATCH")
    spectral_contract(core)


def spectral_contract(core: Mapping[str, Any]) -> SpectralPourContract:
    spectral = core["spectral"]
    required = {"assumption", "fibre", "grade_contract_id", "axis", "lens_id",
                "metric_version", "cluster_count", "chi", "phi", "placement_operator", "entry_role"}
    recursive = {"leaf_max", "branching", "max_depth", "grade_chi", "grade_phi"}
    _require(required <= set(spectral) <= required | recursive, "SPECTRAL-DIALS-REQUIRED")
    depth = spectral.get("max_depth")
    _require(depth is None or (type(depth) is int and depth >= 1), "SPECTRAL-DEPTH-INVALID")
    order = (("cluster",) + tuple(f"cluster:{i}" for i in range(2, depth + 1)) + ("leaf",)
             if depth is not None else ("cluster", "leaf"))
    branching = spectral.get("branching")
    return SpectralPourContract(
        spectral["assumption"], spectral["fibre"],
        GradeAxisContract(spectral["grade_contract_id"], spectral["axis"], order),
        spectral["lens_id"], EncoderSpec.from_dict(core["encoder"]["spec"]), spectral["metric_version"],
        spectral["cluster_count"], spectral["chi"], spectral["phi"], spectral["placement_operator"],
        leaf_max=spectral.get("leaf_max"), branching=tuple(branching) if isinstance(branching, list) else branching,
        max_depth=depth, grade_chi=tuple(spectral.get("grade_chi", ())),
        grade_phi=tuple(spectral.get("grade_phi", ())),
    )


def mint_manifest(core: Mapping[str, Any], repo_root: Path, *, judgement: Mapping[str, Any] | None = None) -> dict[str, Any]:
    core = json.loads(json.dumps(core))
    core.setdefault("sealed_prefixes", list(SEALED_PREFIXES))
    validate_core(core)
    documents, _ = resolve_sources(core, repo_root)
    for doc in documents:
        seg = segmenter_for(doc.path)
        _require(core["segmentation"]["segmenters"].get(seg.segmenter_id) == seg.version,
                 "SEGMENTER-GENERATION-MISMATCH", path=doc.path)
    handle = chash({"schema_version": SCHEMA, "core": core})
    block = {"schema_version": "atlas.dataset-judgement/1", "manifest_handle": handle,
             "body": dict(judgement or {})}
    return {"schema_version": SCHEMA, "manifest_handle": handle, "core": core,
            "judgement_ref": chash(block), "judgement": block}


def load_manifest(path: Path, repo_root: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    _require(raw.get("schema_version") == SCHEMA, "MANIFEST-SCHEMA-UNKNOWN")
    _require("sealed_prefixes" in raw["core"], "SEALED-PREFIXES-REQUIRED")
    expected = mint_manifest(raw["core"], repo_root, judgement=raw["judgement"]["body"])
    _require(raw == expected, "MANIFEST-HANDLE-MISMATCH")
    return raw


def extra_authority_files(repo_root: Path) -> tuple[Path, ...]:
    """Same caller tuple as the bridge/adopter; detached containers carry no engine file."""
    bridge = Path(repo_root).resolve() / "src/laplace/atlas_bridge.py"
    return (bridge,) if bridge.is_file() else ()


def pour_dataset(manifest: Mapping[str, Any], repo_root: Path, container_root: Path,
                 encoder: Any, metadata: Any, *,
                 parent_generation: str = GENESIS_GENERATION) -> dict[str, Any]:
    core = manifest["core"]
    _require("sealed_prefixes" in core, "SEALED-PREFIXES-REQUIRED")
    _require(dict(manifest) == mint_manifest(core, repo_root, judgement=manifest["judgement"]["body"]),
             "MANIFEST-HANDLE-MISMATCH")
    _require(encoder.spec.spec_id == core["encoder"]["generation"], "ENCODER-GENERATION-MISMATCH")
    documents, contents = resolve_sources(core, repo_root)
    target = (container_root / core["store"]).resolve()
    _require(target.is_relative_to(container_root.resolve()), "STORE-ESCAPES-CONTAINER")
    metadata = replace(metadata, provenance=(*metadata.provenance,
        SourceRef("atlas:dataset-manifest", manifest["manifest_handle"], None),
        SourceRef("atlas:dataset-judgement", manifest["judgement_ref"], None)))
    report: dict[str, Any] = {}
    store = ConceptricStore(target, extra_authority_files=extra_authority_files(repo_root))
    generation = pour_blueprint(
        store, repo_root, documents, (), encoder, spectral_contract(core), metadata,
        parent_generation=parent_generation,
        entry_role=core["spectral"]["entry_role"], findings=(), container_root=container_root,
        dataset_roots={core["dataset_id"]: repo_root}, source_contents=contents,
        segmentation={key: core["segmentation"][key] for key in ("target_tokens", "hard_cap_tokens")},
        segmentation_report=report,
    )
    files = report["files"]
    total = sum(row["bytes"] for row in files)
    covered = sum(row["covered_bytes"] for row in files)
    receipt = {"schema_version": "atlas.dataset-pour-receipt/1", "manifest_handle": manifest["manifest_handle"],
               "dataset_id": core["dataset_id"], "pinned_commit": core["pinned_commit"],
               "generation_id": generation.generation_id, "store": core["store"],
               "parent_generation": generation.parent_generation,
               "pour_receipt": generation.receipt.to_dict(),
               "segmentation_coverage": covered / total if total else 1.0,
               "source_files": len(files), "source_bytes": total, "covered_bytes": covered,
               "source_lines": sum(len(data.splitlines()) for data in contents.values()),
               "source_newlines": sum(data.count(b"\n") for data in contents.values()),
               "spans": sum(row["spans"] for row in files), "leaves": len(generation.clauses),
               "structure_violations": sum(row["structure_violations"] for row in files),
               "oversize": [item for row in files for item in row["oversize"]],
               "cluster_sizes": [len(row["member_logical_ids"]) for row in generation.clusters],
               "encoder_generation": encoder.spec.spec_id, "files": files,
               "tex_include_frontier": tex_include_frontier(contents),
               "encoder_window": report.get("encoder_window", {"status": "UNMEASURED"}),
               "seal_check": {"prefixes": core["sealed_prefixes"],
                              "known_derived_paths": list(DERIVED_FROM_SEALED_PATHS),
                              "matched": []}}
    return receipt
