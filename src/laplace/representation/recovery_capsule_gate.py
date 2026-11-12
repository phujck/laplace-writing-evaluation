"""Read-only stage-zero gate for the Superego/Sensorium recovery capsule.

The gate proves preservation, not adoption.  It accepts an explicit immutable runtime-custody
snapshot, reconstructs its authority history through the normal custody verifier, and compares
the result with repository-pinned evidence.  It never selects a live store and has no write door.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CAPSULE_PATH = Path(
    "atlas/packets/recovery/RECOVERY-CAPSULE-20260827-SUPEREGO-SENSORIUM-MIGRATION.md"
)
TAIL_PATH = Path("atlas/packets/recovery/SUPEREGO-WORK-ORDERS-20260827-TAIL.jsonl")
PROJECTION_PATH = Path("atlas/packets/recovery/RECOVERY-STARTUP-PROJECTION-20260827.json")
WORK_ORDERS_PATH = Path("corpus_friction/work_orders.jsonl")
DESIGN_PATH = Path("DESIGN_2026-08-24_the-interface-merge.md")

CAPSULE_HANDLE = "sha256:241d2ba48342309cd1cc265515b98e6695296167aa5b4405b5ca8ee803ce960b"
TAIL_HANDLE = "sha256:36bf4a6258417331a315c654c981a96c96dc2fd33797a0a39c6cdf9596864d96"
FULL_WORK_ORDERS_HANDLE = "sha256:4b956f14b04ca5a9f55809926c596d62fd8dc830b529caa3423254018c51c080"
DESIGN_ACTUAL_HANDLE = "sha256:ca55581359787551cae56403d93aeb7f434cf7d0c667270d238e2f0b2d7c0c02"
DESIGN_WRONG_HANDLE = "sha256:ca555813c3c0272a2647a162f566d54351c448762298239662630196bf3c0c02"
MALFORMED_MESSAGE_ROOT = "message:23fd368d8f10c598240898771397f8f649a433ca412b8e8a4c2da5da53c68a14"
CORRECT_BLUEPRINT_MESSAGE = (
    "message:23fd368d8c13594fdc17a24a1ba242f8cc56e96ecaac0edd556882bb13c0fe37"
)
CORRECTION_MESSAGE = "message:e776db421f421c8febb911575c8c6cd72a63a4ce7c54aa0a23a7c21cab05a406"

CLEAN_PARENT = "4d223e0bee89b39d8f496f5799a355656b31e386"
CLEAN_PARENT_TREE = "16f90992d497a52dd0ea0f6348cc4ce478b4270a"
PUBLISHED_ORIGIN = "2873c75df1d5241ba586f35367be4733e84319ba"
LIFECYCLE_REF = "refs/eigen/provisional/ego-p0-a0-v2-20260827"
LIFECYCLE_COMMIT = "95138a66cc1be0cca8cbd4d0143a4d43aa4eb5f4"
LIFECYCLE_TREE = "a20c59e77f7bc34a7e6cd960a8bbd5f622390d1b"
LIFECYCLE_DIFF = "b8fa0f91fc6393d51a867db03b1c4e6ff1f635e19804bef3b0688d3d9573f602"
LIFECYCLE_PATHS = (
    "atlas/src/atlas/history.py",
    "atlas/src/atlas/state.py",
    "atlas/src/atlas/store.py",
    "atlas/tests/test_conceptric.py",
    "scripts/attention_boundary.py",
    "src/laplace/representation/atlas_bridge.py",
    "tests/test_atlas_bridge.py",
    "tests/test_attention_boundary.py",
    "tests/test_startup_mail_gate.py",
)

SENSORIUM_COMMIT = "79d0ad5cef500908dec4aab3534d56eac870cfdf"
SENSORIUM_TREE = "bd0eaa0c5eb0229edfaab4fd9413435d29b49fe3"
SENSORIUM_DIFF = "f1ab99867009f1b42113c3d11e2ca999fd2b538bab0ad7916f1032b35887c624"
SENSORIUM_PATHS = (
    "contract/surfaces/front.yaml",
    "src/laplace/web/development_lens.html",
    "src/laplace/web/development_lens.py",
    "src/laplace/web/front_door.py",
    "src/laplace/web/front_places.py",
    "tests/development_lens.playwright.mjs",
    "tests/test_development_lens.py",
)

SCREENSHOT_HANDLES = (
    "sha256:7f7cdd3b2bb3e214bca14b2533225695637922f3fbcc3a7340302b7f7a16895c",
    "sha256:7c19a560f8061116a2f5cb39891da7b79af512852f20813bf158f7c193b8a4d9",
)

# Status, exact body, exact reconstruction output when capsule-pinned, exact terminal event when
# capsule-pinned.  Every delivered row must additionally retain its typed proof edge in replay.
MESSAGE_CONTRACT: Mapping[str, Mapping[str, str | None]] = {
    "message:839ebe7d0f2174ed6f8b554a33077ff6cab36a294a7de35918a295de6e96e9c1": {
        "status": "delivered",
        "body_handle": "sha256:687aae118e01df0e6eacb7ec165c64b720ba4324ade441430ce95dc5e350ff71",
        "reconstruction_handle": None,
        "acknowledgement_event_id": None,
    },
    "message:a2f69d3afe559faa002df963ee1d60990d6d554faa6784240254d5f7de8eb1db": {
        "status": "delivered",
        "body_handle": "sha256:681ea8c6d18a14c7715d9d33ee6a246574570dcb9dc3f26388e1472117f78745",
        "reconstruction_handle": None,
        "acknowledgement_event_id": None,
    },
    "message:9c0bc8c53bdb90e03f6dcdbf07f90a60c5159452c62fc6175961e4bb6989f126": {
        "status": "delivered",
        "body_handle": "sha256:5759bf75067e75d5835affe1684d265130d056c4ff56f96373be215872c4f0e2",
        "reconstruction_handle": None,
        "acknowledgement_event_id": None,
    },
    "message:52094fd1f82d3bb5e5a77ad478af744a387157817685b284d7486335fc21591b": {
        "status": "delivered",
        "body_handle": "sha256:cdc87f585d627ad33ef4ceb61322a28a8c3baa6cdacea8e94bdf012758cad888",
        "reconstruction_handle": None,
        "acknowledgement_event_id": None,
    },
    "message:14b560ca5bb3d82c704c321c7324c2ab6bb51aef42d19dc8e3ec13142bb438d6": {
        "status": "delivered",
        "body_handle": "sha256:153cfcbcdefafde7996a8360384993689cb04a119f162b982134c9a89c65edfa",
        "reconstruction_handle": None,
        "acknowledgement_event_id": None,
    },
    CORRECT_BLUEPRINT_MESSAGE: {
        "status": "delivered",
        "body_handle": "sha256:d678fbc99bf02464c1d37e9cfc94a02f2370d978c6476c59e236bde807b0a3ec",
        "reconstruction_handle": None,
        "acknowledgement_event_id": None,
    },
    CORRECTION_MESSAGE: {
        "status": "delivered",
        "body_handle": "sha256:06b84002eab19cd5dd724115080ab00e0bb5aca417113fe3b2c9442c4fd25d9e",
        "reconstruction_handle": None,
        "acknowledgement_event_id": None,
    },
    "message:13473b5d9f3ef7a830fab837edfed9c18b471eefee61af3b412fcc7299d24681": {
        "status": "delivered",
        "body_handle": "sha256:34ce3b11c44bb4b3ff7680da79f2087f854a59069c22e2ffba191174dd1d9c6e",
        "reconstruction_handle": "sha256:6bdb34610a2ab5f69125d8f5ec423ef626736b8714a21dcf482eedf5cd654c35",
        "acknowledgement_event_id": None,
    },
    "message:58f006fd96d2e72f21aa892c4135df868f23cc7142fb493ed572ca9e511a9ba2": {
        "status": "refused",
        "body_handle": "sha256:1959db29a47c59a0610f64d242509745e83c660b5e106aa5b2ea4a48c4887a22",
        "reconstruction_handle": None,
        "acknowledgement_event_id": None,
    },
    "message:a4c130422e74d0e6caf0e162d8814bf9de66d447a238110185a8c6c6ce2f2f94": {
        "status": "delivered",
        "body_handle": "sha256:421bd07ee43a42271c347687d288064b23371d2b8d88390e95dcb7539a509edd",
        "reconstruction_handle": "sha256:c78f0004c1accadb2b2273b5a9d7acb99dea27e43d340b88c34770c7a0953911",
        "acknowledgement_event_id": "sha256:741a0c90ac13d2b8b51226be8bab79ed525146dea75b88f1d1a7854a5e391f4a",
    },
}

HISTORICAL_LEASES: Mapping[str, Mapping[str, str]] = {
    "region-lease:0317300bf02a8094db3b0c59162a1cabd0b3fa89edd78689a304124476025d70": {
        "holder_ref": "codex:01a04233-38a4-7e01-8d95-eba41ff138db",
        "checkout_event_id": "sha256:cad4ef80a7a579dd0d7d11ce26943a50250b7c0bf1db01c8d423bcafd016c0ab",
    },
    "region-lease:d56782d20102f1b44846b2496e69e07a8f05707ddba1c9c68a58edd9725a71b8": {
        "holder_ref": "codex:01a04236-f0bb-7761-86c6-ee383b76981f",
        "checkout_event_id": "sha256:6b14d5041e3295b24858033e03d70d1fa723ca0915632af4c881d04626dc5611",
    },
}


class RecoveryCapsuleRefusal(RuntimeError):
    """One exact fail-closed recovery-capsule refusal."""

    def __init__(self, code: str, detail: str, **evidence: Any) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.evidence = evidence


@dataclass(frozen=True)
class SnapshotEvidence:
    receipt: Mapping[str, Any]
    messages: Mapping[str, Mapping[str, Any]]
    leases: Mapping[str, Mapping[str, Any]]
    nonterminal_messages: tuple[tuple[str, str], ...]
    present_blob_handles: frozenset[str]
    snapshot_unchanged: bool
    event_ids: tuple[str, ...] = field(default_factory=tuple)
    event_record_digests: tuple[str, ...] = field(default_factory=tuple)
    event_kinds: tuple[str, ...] = field(default_factory=tuple)


POST_PROJECTION_EVENT_KINDS = frozenset(
    {
        "reconstruction.moved",
        "reconstruction.materialized",
    }
)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_handle(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return _sha256(encoded)


def _require(condition: bool, code: str, detail: str, **evidence: Any) -> None:
    if not condition:
        raise RecoveryCapsuleRefusal(code, detail, **evidence)


def _load_json(path: Path, *, code: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RecoveryCapsuleRefusal(
            code, "JSON input is absent or malformed", path=str(path)
        ) from exc
    _require(isinstance(value, Mapping), code, "JSON input must be an object", path=str(path))
    return value


def _git(repo_root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ("git", "-C", str(repo_root), *args),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise RecoveryCapsuleRefusal(
            "GIT_COORDINATE_UNAVAILABLE",
            "Git could not resolve a pinned recovery coordinate",
            args=list(args),
            stderr=completed.stderr.decode("utf-8", errors="replace").strip(),
        )
    return completed.stdout


def _git_text(repo_root: Path, *args: str) -> str:
    return _git(repo_root, *args).decode("utf-8").strip()


def _verify_repository(repo_root: Path) -> dict[str, Any]:
    actual_root = Path(_git_text(repo_root, "rev-parse", "--show-toplevel")).resolve()
    _require(
        actual_root == repo_root.resolve(),
        "REPOSITORY_ROOT_MISMATCH",
        "gate repository root is not the selected Git worktree",
        expected=str(repo_root.resolve()),
        actual=str(actual_root),
    )
    _require(
        _git_text(repo_root, "rev-parse", f"{CLEAN_PARENT}^{{tree}}") == CLEAN_PARENT_TREE,
        "CLEAN_PARENT_TREE_MISMATCH",
        "clean parent tree moved",
    )
    _require(
        _git_text(repo_root, "show-ref", "--hash", "--verify", LIFECYCLE_REF) == LIFECYCLE_COMMIT,
        "LIFECYCLE_CUSTODY_REF_MISMATCH",
        "frozen lifecycle custody ref does not select the preserved candidate",
    )
    _require(
        _git_text(repo_root, "rev-parse", f"{LIFECYCLE_COMMIT}^{{tree}}") == LIFECYCLE_TREE,
        "LIFECYCLE_CUSTODY_TREE_MISMATCH",
        "frozen lifecycle custody tree moved",
    )
    lifecycle_diff = _sha256(_git(repo_root, "diff", "--binary", CLEAN_PARENT, LIFECYCLE_COMMIT))
    _require(
        lifecycle_diff == "sha256:" + LIFECYCLE_DIFF,
        "LIFECYCLE_CUSTODY_DIFF_MISMATCH",
        "frozen lifecycle parent-to-candidate diff moved",
        actual=lifecycle_diff,
    )
    lifecycle_paths = tuple(
        line
        for line in _git_text(
            repo_root, "diff", "--name-only", CLEAN_PARENT, LIFECYCLE_COMMIT
        ).splitlines()
        if line
    )
    _require(
        lifecycle_paths == LIFECYCLE_PATHS,
        "LIFECYCLE_CUSTODY_PATH_SET_MISMATCH",
        "frozen lifecycle changed-path set moved",
        actual=list(lifecycle_paths),
    )
    _require(
        _git_text(repo_root, "rev-parse", f"{SENSORIUM_COMMIT}^{{tree}}") == SENSORIUM_TREE,
        "SENSORIUM_TREE_MISMATCH",
        "frozen Sensorium candidate tree moved",
    )
    sensorium_diff = _sha256(
        _git(repo_root, "diff", "--binary", PUBLISHED_ORIGIN, SENSORIUM_COMMIT)
    )
    _require(
        sensorium_diff == "sha256:" + SENSORIUM_DIFF,
        "SENSORIUM_DIFF_MISMATCH",
        "frozen Sensorium parent-to-candidate diff moved",
        actual=sensorium_diff,
    )
    sensorium_paths = tuple(
        line
        for line in _git_text(
            repo_root, "diff", "--name-only", PUBLISHED_ORIGIN, SENSORIUM_COMMIT
        ).splitlines()
        if line
    )
    _require(
        sensorium_paths == SENSORIUM_PATHS,
        "SENSORIUM_PATH_SET_MISMATCH",
        "frozen Sensorium changed-path set moved",
        actual=list(sensorium_paths),
    )
    for descendant in ("master", LIFECYCLE_REF):
        completed = subprocess.run(
            (
                "git",
                "-C",
                str(repo_root),
                "merge-base",
                "--is-ancestor",
                SENSORIUM_COMMIT,
                descendant,
            ),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        _require(
            completed.returncode == 0,
            "SENSORIUM_CANDIDATE_UNREACHABLE",
            "frozen Sensorium candidate is not reachable from a required local custody root",
            descendant=descendant,
        )
    _require(
        _git_text(repo_root, "rev-parse", "origin/master") == PUBLISHED_ORIGIN,
        "PUBLISHED_ORIGIN_MOVED",
        "published origin/master no longer matches the stage-zero input",
    )
    design_handle = _sha256((repo_root / DESIGN_PATH).read_bytes())
    _require(
        design_handle == DESIGN_ACTUAL_HANDLE,
        "DESIGN_ACTUAL_DIGEST_MISMATCH",
        "the exact interface-merge design bytes moved",
        actual=design_handle,
    )
    return {
        "clean_parent": CLEAN_PARENT,
        "clean_parent_tree": CLEAN_PARENT_TREE,
        "lifecycle_custody_ref": LIFECYCLE_REF,
        "lifecycle_custody_commit": LIFECYCLE_COMMIT,
        "lifecycle_custody_tree": LIFECYCLE_TREE,
        "lifecycle_diff_handle": lifecycle_diff,
        "lifecycle_changed_paths": list(lifecycle_paths),
        "published_origin": PUBLISHED_ORIGIN,
        "sensorium_commit": SENSORIUM_COMMIT,
        "sensorium_tree": SENSORIUM_TREE,
        "sensorium_diff_handle": sensorium_diff,
        "sensorium_changed_paths": list(sensorium_paths),
        "sensorium_reachable_from": ["master", LIFECYCLE_REF],
        "design_actual_handle": design_handle,
    }


def _verify_preservation_files(repo_root: Path) -> dict[str, Any]:
    capsule = (repo_root / CAPSULE_PATH).read_bytes()
    tail = (repo_root / TAIL_PATH).read_bytes()
    work_orders = (repo_root / WORK_ORDERS_PATH).read_bytes()
    _require(
        _sha256(capsule) == CAPSULE_HANDLE,
        "CAPSULE_HANDLE_MISMATCH",
        "recovery capsule bytes moved",
        actual=_sha256(capsule),
    )
    _require(
        _sha256(tail) == TAIL_HANDLE,
        "WORK_ORDER_TAIL_HANDLE_MISMATCH",
        "Superego work-order tail bytes moved",
        actual=_sha256(tail),
    )
    _require(
        _sha256(work_orders) == FULL_WORK_ORDERS_HANDLE,
        "FULL_WORK_ORDERS_HANDLE_MISMATCH",
        "full work-order ledger no longer matches the preserved append frontier",
        actual=_sha256(work_orders),
    )
    rows: list[Mapping[str, Any]] = []
    for line_number, raw in enumerate(tail.splitlines(), start=1):
        try:
            row = json.loads(raw)
        except ValueError as exc:
            raise RecoveryCapsuleRefusal(
                "WORK_ORDER_TAIL_JSON_INVALID",
                "Superego work-order tail contains invalid JSON",
                line=line_number,
            ) from exc
        _require(
            isinstance(row, Mapping),
            "WORK_ORDER_TAIL_ROW_NOT_OBJECT",
            "Superego work-order tail row is not a JSON object",
            line=line_number,
        )
        rows.append(row)
    _require(
        len(rows) == 48,
        "WORK_ORDER_TAIL_ROW_COUNT_MISMATCH",
        "Superego work-order tail is not exactly 48 rows",
        actual=len(rows),
    )
    row_ids = [str(row.get("id") or "") for row in rows]
    _require(
        all(row_ids) and len(row_ids) == len(set(row_ids)),
        "WORK_ORDER_TAIL_IDENTITY_INVALID",
        "Superego work-order tail has a missing or repeated typed row id",
    )
    _require(
        work_orders.endswith(tail),
        "WORK_ORDER_TAIL_NOT_EXACT_APPEND",
        "full work-order ledger does not end with the exact preserved 48-row append",
    )
    return {
        "capsule_path": str(CAPSULE_PATH),
        "capsule_handle": CAPSULE_HANDLE,
        "capsule_bytes": len(capsule),
        "tail_path": str(TAIL_PATH),
        "tail_handle": TAIL_HANDLE,
        "tail_bytes": len(tail),
        "tail_row_count": len(rows),
        "tail_row_ids_root": _canonical_handle({"row_ids": row_ids}),
        "full_work_orders_handle": FULL_WORK_ORDERS_HANDLE,
        "append_mode": "exact-byte-suffix",
    }


def _verify_projection(repo_root: Path) -> tuple[Mapping[str, Any], dict[str, str]]:
    path = repo_root / PROJECTION_PATH
    projection = _load_json(path, code="STARTUP_PROJECTION_INVALID")
    _require(
        projection.get("schema_version") == "laplace.recovery-startup-projection/1",
        "STARTUP_PROJECTION_SCHEMA_UNKNOWN",
        "recovery startup projection schema is unknown",
    )
    _require(
        projection.get("migration_root") == CAPSULE_HANDLE,
        "STARTUP_PROJECTION_CAPSULE_UNBOUND",
        "startup projection does not select the exact recovery capsule",
    )
    capsule = projection.get("capsule")
    tail = projection.get("work_order_tail")
    _require(
        isinstance(capsule, Mapping)
        and capsule.get("path") == str(CAPSULE_PATH)
        and capsule.get("content_handle") == CAPSULE_HANDLE,
        "STARTUP_PROJECTION_CAPSULE_UNBOUND",
        "startup projection capsule reference is incomplete",
    )
    _require(
        isinstance(tail, Mapping)
        and tail.get("path") == str(TAIL_PATH)
        and tail.get("content_handle") == TAIL_HANDLE
        and tail.get("row_count") == 48
        and tail.get("full_work_orders_handle") == FULL_WORK_ORDERS_HANDLE,
        "STARTUP_PROJECTION_TAIL_UNBOUND",
        "startup projection does not bind the exact Superego append",
    )
    sensorium = projection.get("sensorium_candidate")
    _require(
        isinstance(sensorium, Mapping)
        and sensorium.get("commit") == SENSORIUM_COMMIT
        and sensorium.get("tree") == SENSORIUM_TREE
        and sensorium.get("diff_sha256") == SENSORIUM_DIFF
        and sensorium.get("classification") == "frozen-subordinate-evidence-not-accepted-state"
        and sensorium.get("accepted") is False
        and sensorium.get("adopted") is False
        and sensorium.get("publication_authority") is False,
        "SENSORIUM_CANDIDATE_SILENTLY_ACCEPTED",
        "startup projection does not keep Sensorium as frozen subordinate evidence",
    )
    historical = projection.get("historical_authority")
    _require(
        isinstance(historical, Mapping)
        and historical.get("reuse_policy") == "forbidden"
        and historical.get("predecessor_bindings") == "historical-only"
        and historical.get("watcher_generations") == "historical-only",
        "HISTORICAL_AUTHORITY_REUSE_ALLOWED",
        "startup projection does not refuse predecessor authority reuse",
    )
    projected_leases = {
        str(row.get("lease_id")): row
        for row in historical.get("leases", ())
        if isinstance(row, Mapping)
    }
    _require(
        set(projected_leases) == set(HISTORICAL_LEASES),
        "HISTORICAL_LEASE_SET_MISMATCH",
        "startup projection historical lease set moved",
    )
    for lease_id, expected in HISTORICAL_LEASES.items():
        row = projected_leases[lease_id]
        _require(
            row.get("holder_ref") == expected["holder_ref"]
            and row.get("checkout_event_id") == expected["checkout_event_id"]
            and row.get("authority") == "historical-only"
            and row.get("reused") is False,
            "HISTORICAL_LEASE_REUSE_ALLOWED",
            "startup projection does not preserve one lease as non-authoritative history",
            lease_id=lease_id,
        )
    defects = projection.get("preserved_reference_defects")
    _require(
        isinstance(defects, list) and len(defects) == 2,
        "REFERENCE_RESIDUAL_SET_MISMATCH",
        "startup projection does not expose both known reference defects",
    )
    defect_by_kind = {str(row.get("kind")): row for row in defects if isinstance(row, Mapping)}
    malformed = defect_by_kind.get("malformed-message-root", {})
    wrong_digest = defect_by_kind.get("incorrect-repository-digest", {})
    _require(
        malformed.get("claimed") == MALFORMED_MESSAGE_ROOT
        and malformed.get("correct") == CORRECT_BLUEPRINT_MESSAGE
        and malformed.get("typed_successor") == CORRECTION_MESSAGE
        and malformed.get("alias_allowed") is False,
        "MALFORMED_ROOT_VISIBILITY_LOST",
        "malformed message root is absent, aliased, or not tied to its typed successor",
    )
    _require(
        wrong_digest.get("claimed") == DESIGN_WRONG_HANDLE
        and wrong_digest.get("correct") == DESIGN_ACTUAL_HANDLE
        and wrong_digest.get("alias_allowed") is False
        and wrong_digest.get("state") == "visible-unresolved-typed-successor-required",
        "WRONG_DIGEST_VISIBILITY_LOST",
        "wrong full design digest is absent, aliased, or falsely repaired",
    )
    roles = projection.get("role_contexts")
    _require(
        isinstance(roles, list) and len(roles) == 3,
        "ROLE_CONTEXT_SET_MISMATCH",
        "startup projection must carry exactly three role-specialized contexts",
    )
    role_by_function = {str(row.get("function")): row for row in roles if isinstance(row, Mapping)}
    _require(
        set(role_by_function) == {"ego", "sensorium", "superego"},
        "ROLE_CONTEXT_SET_MISMATCH",
        "startup projection role functions are not the replacement trinity",
    )
    specializations = set()
    role_receipts: dict[str, str] = {}
    for function, row in role_by_function.items():
        specialization = str(row.get("specialization") or "")
        _require(
            specialization
            and row.get("authority") == "none-before-authenticated-successor-binding"
            and row.get("active_lease_ids") == []
            and row.get("capsule_handle") == CAPSULE_HANDLE
            and row.get("work_order_tail_handle") == TAIL_HANDLE,
            "ROLE_CONTEXT_NOT_SPECIALIZED_OR_SAFE",
            "one startup role context is generic or pre-authorized",
            function=function,
        )
        specializations.add(specialization)
        role_receipts[function] = _canonical_handle(row)
    _require(
        len(specializations) == 3,
        "ROLE_CONTEXTS_NOT_DISTINCT",
        "replacement trinity contexts are not role-specialized",
    )
    return projection, role_receipts


def _tree_stat_token(root: Path) -> tuple[tuple[str, int, int], ...]:
    return tuple(
        (str(path.relative_to(root)), path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def _filesystem_device(root: Path) -> int:
    """Return the filesystem device that physically holds one custody root."""

    return root.stat().st_dev


def _load_snapshot_evidence(snapshot_root: Path) -> SnapshotEvidence:
    # Importing the bridge first is the repository's one allowlisted Atlas package boundary.
    from laplace.representation.atlas_bridge import BlobStore, ConceptricStore

    from laplace.representation import atlas_bridge

    root = snapshot_root.resolve()
    before = _tree_stat_token(root)
    receipt = atlas_bridge.verify_runtime_custody(root)
    store = ConceptricStore(
        root, read_only=True, immutable=True,
        extra_authority_files=atlas_bridge.EXTRA_AUTHORITY_FILES,
    )
    state = store.replay_authority_only()
    with sqlite3.connect(
        (root / "conceptric.sqlite3").resolve().as_uri() + "?mode=ro&immutable=1",
        uri=True,
    ) as connection:
        event_rows = connection.execute(
            "SELECT event_id, record_digest, event_kind FROM events ORDER BY sequence"
        ).fetchall()
    blobs = BlobStore(root / "blobs")
    present: set[str] = set()
    messages: dict[str, dict[str, Any]] = {}
    for message_id in MESSAGE_CONTRACT:
        record = state.messages.get(message_id)
        if record is None:
            messages[message_id] = {"missing": True}
            continue
        body_handle = record.message.body_handle
        blobs.get(body_handle)
        present.add(body_handle)
        proof_event_ids = tuple(
            sorted(
                edge.source_object_id.removeprefix("reconstruction:")
                for edge in state.graph_edges.values()
                if edge.relation == "proved-by"
                and edge.target_object_id == f"acknowledgement:{record.acknowledgement_event_id}"
                and edge.source_object_id.startswith("reconstruction:")
            )
        )
        proof_valid = False
        if record.status.value == "delivered" and len(proof_event_ids) == 1:
            proof_event_id = proof_event_ids[0]
            evaluation = state.repl_evaluations.get(proof_event_id)
            proof_valid = bool(
                evaluation is not None
                and body_handle in evaluation.input_handles
                and record.reconstruction_handle in evaluation.output_handles
                and state.repl_contexts.get(proof_event_id, ())[:2]
                == (record.assumption, record.fibre)
            )
        elif record.status.value == "refused":
            acknowledgement = state.graph_objects.get(
                f"acknowledgement:{record.acknowledgement_event_id}"
            )
            proof_valid = bool(
                acknowledgement is not None
                and acknowledgement.attributes.get("disposition") == "refused"
                and not proof_event_ids
            )
        messages[message_id] = {
            "missing": False,
            "body_handle": body_handle,
            "status": record.status.value,
            "reconstruction_handle": record.reconstruction_handle,
            "acknowledgement_event_id": record.acknowledgement_event_id,
            "dependency_roots": dict(record.message.dependency_roots),
            "proof_event_ids": list(proof_event_ids),
            "proof_valid": proof_valid,
        }
    for handle in SCREENSHOT_HANDLES:
        blobs.get(handle)
        present.add(handle)
    for handle in (DESIGN_WRONG_HANDLE,):
        if blobs.has(handle):
            # A false reference becoming a blob is not accepted implicitly; verify and expose it.
            blobs.get(handle)
            present.add(handle)
    leases = {
        lease_id: {
            "holder_ref": lease.checkout.holder_ref,
            "checkout_event_id": lease.checkout_event_id,
            "seat_id": lease.checkout.seat_id,
            "function": lease.checkout.function.value,
        }
        for lease_id, lease in state.region_leases.items()
        if lease_id in HISTORICAL_LEASES
    }
    nonterminal = tuple(
        sorted(
            (message_id, record.status.value)
            for message_id, record in state.messages.items()
            if record.status.value in {"queued", "pulled"}
        )
    )
    after = _tree_stat_token(root)
    return SnapshotEvidence(
        receipt=receipt,
        messages=messages,
        leases=leases,
        nonterminal_messages=nonterminal,
        present_blob_handles=frozenset(present),
        snapshot_unchanged=before == after,
        event_ids=tuple(str(row[0]) for row in event_rows),
        event_record_digests=tuple(str(row[1]) for row in event_rows),
        event_kinds=tuple(str(row[2]) for row in event_rows),
    )


def _verify_snapshot_contract(
    evidence: SnapshotEvidence, projection: Mapping[str, Any]
) -> dict[str, Any]:
    expected_receipt = projection.get("runtime_custody")
    _require(
        isinstance(expected_receipt, Mapping),
        "RUNTIME_CUSTODY_PROJECTION_MISSING",
        "startup projection does not bind a runtime custody generation",
    )
    invariant_receipt_fields = (
        "complete_message_body_relation_root",
        "historical_unavailable_message_count",
    )
    mismatches = {
        field: {"expected": expected_receipt.get(field), "actual": evidence.receipt.get(field)}
        for field in invariant_receipt_fields
        if expected_receipt.get(field) != evidence.receipt.get(field)
    }
    _require(
        not mismatches,
        "RUNTIME_CUSTODY_GENERATION_MISMATCH",
        "explicit runtime custody snapshot does not match the recovery projection",
        mismatches=mismatches,
    )
    generation_fields = (
        "snapshot_id",
        "event_count",
        "head_event_id",
        "head_record_digest",
    )
    exact_generation = all(
        expected_receipt.get(field) == evidence.receipt.get(field)
        for field in generation_fields
    )
    projection_relation = "exact-generation"
    if not exact_generation:
        expected_count = expected_receipt.get("event_count")
        actual_count = evidence.receipt.get("event_count")
        _require(
            isinstance(expected_count, int)
            and isinstance(actual_count, int)
            and actual_count > expected_count
            and len(evidence.event_ids) == actual_count
            and len(evidence.event_record_digests) == actual_count
            and len(evidence.event_kinds) == actual_count,
            "RUNTIME_CUSTODY_GENERATION_MISMATCH",
            "newer runtime custody is not a provable append-only extension",
            expected_count=expected_count,
            actual_count=actual_count,
        )
        _require(
            evidence.event_ids[expected_count - 1] == expected_receipt.get("head_event_id")
            and evidence.event_record_digests[expected_count - 1]
            == expected_receipt.get("head_record_digest"),
            "RUNTIME_CUSTODY_PREFIX_ANCHOR_MISMATCH",
            "newer runtime custody does not retain the projected head as its exact prefix",
            expected_event_id=expected_receipt.get("head_event_id"),
            actual_event_id=evidence.event_ids[expected_count - 1],
        )
        appended_kinds = evidence.event_kinds[expected_count:]
        unexpected_kinds = tuple(
            kind for kind in appended_kinds if kind not in POST_PROJECTION_EVENT_KINDS
        )
        _require(
            not unexpected_kinds,
            "RUNTIME_CUSTODY_POST_PROJECTION_EVENT_REFUSED",
            "newer runtime custody contains a non-reconstruction event after the pinned head",
            appended_kinds=list(appended_kinds),
            unexpected_kinds=list(unexpected_kinds),
        )
        projection_relation = "append-only-reconstruction-extension"
    _require(
        evidence.snapshot_unchanged,
        "RUNTIME_CUSTODY_MUTATED_DURING_GATE",
        "read-only recovery gate changed the supplied snapshot",
    )
    for message_id, expected in MESSAGE_CONTRACT.items():
        actual = evidence.messages.get(message_id)
        _require(
            isinstance(actual, Mapping) and actual.get("missing") is False,
            "CAPSULE_MESSAGE_MISSING",
            "one capsule-pinned Sensorium/Superego message is absent",
            message_id=message_id,
        )
        _require(
            actual.get("body_handle") == expected["body_handle"]
            and actual.get("status") == expected["status"],
            "CAPSULE_MESSAGE_STATE_MISMATCH",
            "one capsule-pinned message body or terminal status moved",
            message_id=message_id,
            expected=dict(expected),
            actual=dict(actual),
        )
        if expected["reconstruction_handle"] is not None:
            _require(
                actual.get("reconstruction_handle") == expected["reconstruction_handle"],
                "CAPSULE_RECONSTRUCTION_HANDLE_MISMATCH",
                "one capsule-pinned reconstruction output moved",
                message_id=message_id,
            )
        if expected["acknowledgement_event_id"] is not None:
            _require(
                actual.get("acknowledgement_event_id") == expected["acknowledgement_event_id"],
                "CAPSULE_TERMINAL_EVENT_MISMATCH",
                "one capsule-pinned terminal acknowledgement moved",
                message_id=message_id,
            )
        _require(
            actual.get("proof_valid") is True,
            "CAPSULE_RECONSTRUCTION_PROOF_MISSING",
            "one capsule-pinned terminal message lost its typed proof/refusal edge",
            message_id=message_id,
        )
    _require(
        set(SCREENSHOT_HANDLES).issubset(evidence.present_blob_handles),
        "SENSORIUM_SCREENSHOT_MISSING",
        "one frozen Sensorium screenshot blob is absent or corrupt",
    )
    _require(
        DESIGN_WRONG_HANDLE not in evidence.present_blob_handles,
        "WRONG_DIGEST_FABRICATED_AS_BLOB",
        "the known-wrong design digest appeared as a content blob",
    )
    correction = evidence.messages[CORRECTION_MESSAGE]["dependency_roots"]
    preparatory = evidence.messages[
        "message:14b560ca5bb3d82c704c321c7324c2ab6bb51aef42d19dc8e3ec13142bb438d6"
    ]["dependency_roots"]
    _require(
        correction.get("malformed_root") == MALFORMED_MESSAGE_ROOT
        and correction.get("correct_root") == CORRECT_BLUEPRINT_MESSAGE
        and preparatory.get("declared_blueprint_amendment") == MALFORMED_MESSAGE_ROOT
        and preparatory.get("candidate_blueprint_amendment") == CORRECT_BLUEPRINT_MESSAGE,
        "MALFORMED_ROOT_LINEAGE_MISSING",
        "the malformed message root is no longer explicit beside its typed correction",
    )
    _require(
        preparatory.get("interface_merge") == DESIGN_WRONG_HANDLE,
        "WRONG_DIGEST_LINEAGE_MISSING",
        "the historical wrong full digest was erased or silently changed",
    )
    projected_nonterminal = tuple(
        sorted(
            (str(row.get("message_id")), str(row.get("status")))
            for row in projection.get("expected_snapshot_nonterminal_messages", ())
            if isinstance(row, Mapping)
        )
    )
    _require(
        evidence.nonterminal_messages == projected_nonterminal,
        "UNEXPECTED_NONTERMINAL_MESSAGE",
        "snapshot queued/pulled obligations differ from the explicit recovery projection",
        expected=[list(row) for row in projected_nonterminal],
        actual=[list(row) for row in evidence.nonterminal_messages],
    )
    _require(
        set(evidence.leases) == set(HISTORICAL_LEASES),
        "HISTORICAL_LEASE_EVIDENCE_MISSING",
        "one capsule-pinned historical lease is absent",
    )
    for lease_id, expected in HISTORICAL_LEASES.items():
        actual = evidence.leases[lease_id]
        _require(
            actual.get("holder_ref") == expected["holder_ref"]
            and actual.get("checkout_event_id") == expected["checkout_event_id"],
            "HISTORICAL_LEASE_EVIDENCE_MISMATCH",
            "one historical lease lineage moved",
            lease_id=lease_id,
        )
    return {
        **dict(evidence.receipt),
        "capsule_message_count": len(MESSAGE_CONTRACT),
        "screenshot_handles": list(SCREENSHOT_HANDLES),
        "expected_nonterminal_messages": [
            {"message_id": message_id, "status": status}
            for message_id, status in evidence.nonterminal_messages
        ],
        "historical_lease_ids": sorted(evidence.leases),
        "snapshot_unchanged": evidence.snapshot_unchanged,
        "projection_relation": projection_relation,
        "projection_baseline": dict(expected_receipt),
    }


def evaluate_recovery_capsule(
    *,
    repo_root: Path,
    snapshot_root: Path,
    snapshot_probe: Callable[[Path], SnapshotEvidence] | None = None,
) -> dict[str, Any]:
    """Return the exact ready receipt or raise one fail-closed refusal."""

    repository = _verify_repository(repo_root)
    preservation = _verify_preservation_files(repo_root)
    projection, role_receipts = _verify_projection(repo_root)
    evidence = (snapshot_probe or _load_snapshot_evidence)(snapshot_root)
    snapshot = _verify_snapshot_contract(evidence, projection)
    return {
        "schema_version": "laplace.recovery-capsule-gate/1",
        "state": "RECOVERY_CAPSULE_READY",
        "read_only": True,
        "repository": repository,
        "preservation": preservation,
        "startup_projection": {
            "path": str(PROJECTION_PATH),
            "handle": _sha256((repo_root / PROJECTION_PATH).read_bytes()),
            "migration_root": CAPSULE_HANDLE,
            "role_context_receipts": role_receipts,
        },
        "runtime_custody": snapshot,
        "sensorium_candidate": {
            "classification": "frozen-subordinate-evidence-not-accepted-state",
            "accepted": False,
            "adopted": False,
            "publication_authority": False,
        },
        "historical_authority": {
            "lease_ids": sorted(HISTORICAL_LEASES),
            "authority": "historical-only",
            "reuse": "forbidden",
        },
        "reference_residuals": {
            "malformed_message_root": MALFORMED_MESSAGE_ROOT,
            "wrong_design_digest": DESIGN_WRONG_HANDLE,
            "fuzzy_aliasing": "forbidden",
        },
        "proof_boundary": (
            "preservation and declarative startup contexts proved; live successor bindings, "
            "provider processes, and interface acceptance remain outside this read-only gate"
        ),
    }


def run_recovery_capsule_gate(
    *,
    repo_root: Path,
    snapshot_root: Path,
    snapshot_probe: Callable[[Path], SnapshotEvidence] | None = None,
) -> dict[str, Any]:
    try:
        return evaluate_recovery_capsule(
            repo_root=repo_root,
            snapshot_root=snapshot_root,
            snapshot_probe=snapshot_probe,
        )
    except RecoveryCapsuleRefusal as exc:
        return {
            "schema_version": "laplace.recovery-capsule-gate/1",
            "state": "RECOVERY_CAPSULE_REFUSED",
            "read_only": True,
            "refusal": {
                "code": exc.code,
                "detail": exc.detail,
                "evidence": exc.evidence,
            },
        }
    except Exception as exc:  # fail closed without erasing the concrete exception class
        return {
            "schema_version": "laplace.recovery-capsule-gate/1",
            "state": "RECOVERY_CAPSULE_REFUSED",
            "read_only": True,
            "refusal": {
                "code": "RECOVERY_GATE_INTERNAL_REFUSAL",
                "detail": str(exc),
                "evidence": {"exception": type(exc).__name__},
            },
        }


def _flip_one_byte(path: Path) -> None:
    with path.open("r+b") as stream:
        first = stream.read(1)
        if not first:
            raise RecoveryCapsuleRefusal(
                "BIT_FLIP_TARGET_EMPTY", "bit-flip rehearsal target is empty", path=str(path)
            )
        stream.seek(0)
        stream.write(bytes((first[0] ^ 0x01,)))
        stream.flush()


def _first_hive_relative_path(snapshot_root: Path) -> Path:
    ledger = snapshot_root / "conceptric.sqlite3"
    with sqlite3.connect(
        ledger.resolve().as_uri() + "?mode=ro&immutable=1", uri=True
    ) as connection:
        row = connection.execute(
            "SELECT event_handle FROM events ORDER BY sequence LIMIT 1"
        ).fetchone()
    _require(
        row is not None and isinstance(row[0], str) and row[0].startswith("sha256:"),
        "EVENT_HIVE_TARGET_MISSING",
        "runtime custody snapshot has no hived event target",
    )
    hexdigest = str(row[0]).removeprefix("sha256:")
    return Path("hives/events") / hexdigest[:2] / f"{hexdigest}.zlib"


def rehearse_bit_flip_recovery(
    *, snapshot_root: Path, independent_custody_root: Path
) -> dict[str, Any]:
    """Plant blob/hive flips only in disposable copies, then restore from independent custody."""

    from laplace.representation import atlas_bridge

    source = snapshot_root.resolve()
    independent = independent_custody_root.resolve()
    _require(
        source != independent,
        "INDEPENDENT_CUSTODY_NOT_INDEPENDENT",
        "bit-flip recovery requires a distinct custody path",
    )
    source_device = _filesystem_device(source)
    independent_device = _filesystem_device(independent)
    _require(
        source_device != independent_device,
        "INDEPENDENT_CUSTODY_SAME_FILESYSTEM",
        "bit-flip recovery requires custody on a different filesystem device",
        source_device=source_device,
        independent_device=independent_device,
    )
    source_before = _tree_stat_token(source)
    independent_before = _tree_stat_token(independent)
    source_receipt = atlas_bridge.verify_runtime_custody(source)
    independent_receipt = atlas_bridge.verify_runtime_custody(independent)
    _require(
        source_receipt.get("snapshot_id") == independent_receipt.get("snapshot_id"),
        "INDEPENDENT_CUSTODY_GENERATION_MISMATCH",
        "independent custody does not carry the same snapshot generation",
    )
    body_hex = str(
        MESSAGE_CONTRACT[
            "message:a4c130422e74d0e6caf0e162d8814bf9de66d447a238110185a8c6c6ce2f2f94"
        ]["body_handle"]
    ).removeprefix("sha256:")
    targets = {
        "message-blob": Path("blobs") / body_hex[:2] / body_hex,
        "event-hive": _first_hive_relative_path(source),
    }
    outcomes: dict[str, Any] = {}
    for kind, relative in targets.items():
        with tempfile.TemporaryDirectory(prefix=f"laplace-{kind}-flip-") as raw_temp:
            trial = Path(raw_temp) / "snapshot"
            shutil.copytree(source, trial)
            target = trial / relative
            _require(
                target.is_file() and (independent / relative).is_file(),
                "BIT_FLIP_TARGET_MISSING",
                "source or independent custody lacks the planted target",
                kind=kind,
                relative_path=str(relative),
            )
            _flip_one_byte(target)
            detected = False
            refusal = None
            try:
                atlas_bridge.verify_runtime_custody(trial)
            except Exception as exc:  # the exact integrity exception is part of the receipt
                detected = True
                refusal = {"exception": type(exc).__name__, "detail": str(exc)}
            _require(
                detected,
                "BIT_FLIP_NOT_DETECTED",
                "planted custody corruption passed verification",
                kind=kind,
            )
            shutil.copy2(independent / relative, target)
            recovered = atlas_bridge.verify_runtime_custody(trial)
            _require(
                recovered.get("snapshot_id") == source_receipt.get("snapshot_id"),
                "BIT_FLIP_RECOVERY_MISMATCH",
                "independent custody restore did not recover the exact snapshot",
                kind=kind,
            )
            outcomes[kind] = {
                "relative_path": str(relative),
                "detected": True,
                "refusal": refusal,
                "restored_snapshot_id": recovered.get("snapshot_id"),
            }
    source_final_receipt = atlas_bridge.verify_runtime_custody(source)
    independent_final_receipt = atlas_bridge.verify_runtime_custody(independent)
    _require(
        source_final_receipt.get("snapshot_id") == source_receipt.get("snapshot_id"),
        "SOURCE_CUSTODY_IDENTITY_MOVED",
        "source custody identity changed during the disposable corruption rehearsal",
        before=source_receipt.get("snapshot_id"),
        after=source_final_receipt.get("snapshot_id"),
    )
    _require(
        independent_final_receipt.get("snapshot_id") == independent_receipt.get("snapshot_id"),
        "INDEPENDENT_CUSTODY_IDENTITY_MOVED",
        "independent custody identity changed during the disposable corruption rehearsal",
        before=independent_receipt.get("snapshot_id"),
        after=independent_final_receipt.get("snapshot_id"),
    )
    _require(
        source_before == _tree_stat_token(source)
        and independent_before == _tree_stat_token(independent),
        "BIT_FLIP_REHEARSAL_MUTATED_CUSTODY",
        "bit-flip rehearsal changed source or independent custody",
    )
    return {
        "schema_version": "laplace.recovery-capsule-bit-flip-rehearsal/1",
        "state": "BIT_FLIP_RECOVERY_READY",
        "snapshot_id": source_receipt.get("snapshot_id"),
        "source_filesystem_device": source_device,
        "independent_filesystem_device": independent_device,
        "final_source_snapshot_id": source_final_receipt.get("snapshot_id"),
        "final_independent_snapshot_id": independent_final_receipt.get("snapshot_id"),
        "disposable_only": True,
        "source_and_independent_custody_unchanged": True,
        "outcomes": outcomes,
    }
