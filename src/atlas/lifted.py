"""Optional reconstruction imports and compact consumed-source observations.

Ordinary Python imports own module identity, locking and failure cleanup. This
adapter never searches a checkout, aliases modules or reloads code. First-adapter
disk observations are not executed-byte attestations; an already imported module
has UNKNOWN start basis. Current-purpose consumers compare retained receipts and
refuse changed/unproved sources before issuing a successful stage receipt.

Metadata is bounded by the declared local module closure. Current comparisons
hash each shared source once per call; algorithms, tensors and results stay with
their existing owners. Numeric imports occur only on explicit load(name).
"""
from __future__ import annotations

import hashlib
import importlib
import sys
import time
import threading
from pathlib import Path
from typing import Sequence


__all__ = ["load", "receipt", "check_current", "require_current", "stable_basis", "LiftUnavailable",
           "LiftIncompatible", "LiftSourceChanged"]
_START: dict[str, dict] = {}
_MAP_START: dict | None = None
_PACKAGE_START: dict | None = None
_OBSERVATION_LOCK = threading.RLock()
_ROOT = Path(__file__).with_name("reconstruction").resolve()
_MAP = _ROOT / "_provenance.py"
_INITIALIZER = _ROOT / "__init__.py"
# One declaration shared by the retained grading guard and receipt validation.
REFUSED_BY_A35 = ("section_ingest", "section_news_ingest", "raptor_baseline", "news_projection")


class LiftUnavailable(ImportError):
    """An explicitly requested optional dependency is absent; no fallback exists."""


class LiftIncompatible(ImportError):
    """The selected implementation/dependency is present but cannot be used."""


class LiftSourceChanged(RuntimeError):
    """A current-purpose caller must cold-revalidate a changed/unproved source."""

    def __init__(self, result):
        self.result = result
        self.affected_paths = result["affected_paths"]
        self.cold_revalidation = result["cold_revalidation"]
        super().__init__("LIFT-SOURCE-" + result["status"] + ": " + ", ".join(self.affected_paths))


def _metadata():
    with _OBSERVATION_LOCK:
        return _metadata_observed()


def _metadata_observed():
    global _MAP_START, _PACKAGE_START
    qualified = "atlas.reconstruction._provenance"
    if _PACKAGE_START is None:
        work = {"files": 0, "bytes": 0, "seconds": 0.0}
        _PACKAGE_START = (_unknown(_INITIALIZER) if "atlas.reconstruction" in sys.modules
                          else _observe(_INITIALIZER, work))
    if _MAP_START is None:
        work = {"files": 0, "bytes": 0, "seconds": 0.0}
        _MAP_START = (_unknown(_MAP) if qualified in sys.modules else _observe(_MAP, work))
    try:
        metadata = importlib.import_module(qualified)
    except Exception as error:
        raise LiftIncompatible("LIFT-PROVENANCE-INCOMPATIBLE: " + str(error)) from error
    if getattr(metadata, "API_VERSION", None) != "atlas.reconstruction/1":
        raise LiftIncompatible("LIFT-PROVENANCE-API-MISMATCH")
    return metadata


def _closure(names):
    metadata = _metadata()
    seen = set()
    def visit(name):
        if name not in metadata.MODULES:
            raise KeyError("LIFT-MODULE-NOT-DECLARED: " + str(name))
        if name in seen:
            return
        seen.add(name)
        for child in metadata.MODULES[name]["local_dependencies"]:
            visit(child)
    for name in names:
        visit(name)
    return sorted(seen)


def _observe(path, work):
    started = time.perf_counter()
    try:
        raw = path.read_bytes()
    except OSError as error:
        work["seconds"] += time.perf_counter() - started
        return {"status": "MISSING", "path": str(path), "loaded_bytes_asserted": False,
                "reason": type(error).__name__}
    digest = hashlib.sha256(raw).hexdigest()
    elapsed = time.perf_counter() - started
    work["files"] += 1
    work["bytes"] += len(raw)
    work["seconds"] += elapsed
    return {"status": "OBSERVED", "path": str(path),
            "sha256": "sha256:" + digest, "bytes": len(raw), "hash_seconds": elapsed,
            "loaded_bytes_asserted": False}


def _unknown(path):
    return {"status": "UNKNOWN", "path": str(path), "loaded_bytes_asserted": False}


def load(name: str):
    """Settle first observations atomically; Python still owns actual imports."""
    with _OBSERVATION_LOCK:
        return _load_observed(name)


def _load_observed(name):
    closure = _closure([name])
    work = {"files": 0, "bytes": 0, "seconds": 0.0}
    pending = {}
    for child in closure:
        if child not in _START:
            path = _ROOT / (child + ".py")
            qualified = "atlas.reconstruction." + child
            pending[child] = (_unknown(path) if qualified in sys.modules else _observe(path, work))
    try:
        module = importlib.import_module("atlas.reconstruction." + name)
    except ModuleNotFoundError as error:
        # A missing selected canonical module is a packaging fault, not an extra.
        if error.name and not error.name.startswith("atlas"):
            raise LiftUnavailable("LIFT-DEPENDENCY-UNAVAILABLE: " + error.name) from error
        raise LiftIncompatible("LIFT-IMPLEMENTATION-MISSING: " + name) from error
    except Exception as error:
        raise LiftIncompatible("LIFT-IMPLEMENTATION-INCOMPATIBLE: " + name + ": " + str(error)) from error
    finally:
        # Python removes failed imports. Retain observations only for modules it
        # actually kept; dependencies completed before a failure keep their basis.
        for child, observation in pending.items():
            qualified = "atlas.reconstruction." + child
            if qualified in sys.modules:
                _START.setdefault(child, observation)
    if getattr(module, "__name__", None) != "atlas.reconstruction." + name:
        raise LiftIncompatible("LIFT-QUALIFIED-IDENTITY-MISMATCH: " + name)
    if (not getattr(module, "__file__", None)
            or Path(module.__file__).resolve() != _ROOT / (name + ".py")):
        raise LiftIncompatible("LIFT-SELECTED-ORIGIN-MISMATCH: " + name)
    return module


def _file_basis(observation):
    # Only this producer's known per-file duration leaves the source basis.
    return {key: value for key, value in observation.items() if key != "hash_seconds"}


def stable_basis(value: dict) -> dict:
    """Project this producer's two versioned schemas, excluding only diagnostics.

    No recursive key filter is used: files/bytes, source/status and every other
    semantic field remain. Consumers retain diagnostics outside addressed payloads.
    """
    schema = value.get("schema_version")
    required = ({"requested", "closure", "modules", "provenance_map", "hash_work",
                 "first_adapter_hash_work", "api_version", "proof", "package_initializer"}
                if schema == "atlas.lift-receipt/2" else
                {"status", "affected_paths", "issues", "observations", "hash_work",
                 "cold_revalidation", "loaded_bytes_asserted"}
                if schema == "atlas.lift-currentness/1" else None)
    if required is None or not required.issubset(value):
        raise ValueError("LIFT-BASIS-SCHEMA-MISMATCH")
    if set(value["hash_work"]) != {"files", "bytes"}:
        raise ValueError("LIFT-BASIS-HASH-WORK-MISMATCH")
    return {key: item for key, item in value.items() if key != "diagnostics"}


def receipt(names: Sequence[str], *, observe_current: bool = True) -> dict:
    """Read the supported observation settlement under the same local lock."""
    with _OBSERVATION_LOCK:
        return _receipt_observed(names, observe_current=observe_current)


def _receipt_observed(names, *, observe_current):
    """Name consumed closure and separate first-adapter/current disk editions.

    Receipt creation does not import the requested algorithms. Call load first to
    establish a basis; direct earlier imports remain UNKNOWN. No code fingerprint
    or scientific correctness claim is attached to file observations.
    """
    metadata = _metadata()
    work = {"files": 0, "bytes": 0, "seconds": 0.0}
    requested = sorted(set(names))
    modules = []
    current_times = {}
    for name in _closure(requested):
        path = _ROOT / (name + ".py")
        original = metadata.MODULES[name]
        row = {"name": name, "qualified_name": "atlas.reconstruction." + name,
               "origin": str(path), "provenance": {k: original[k] for k in
                   ("original_path", "original_sha256", "inventory_verdict", "used_for")},
               "first_adapter": _file_basis(_START.get(name, _unknown(path)))}
        if observe_current:
            current = _observe(path, work)
            row["current_disk"] = _file_basis(current)
            current_times[name] = current.get("hash_seconds", 0.0)
        modules.append(row)
    provenance = {"first_adapter": _file_basis(_MAP_START or _unknown(_MAP))}
    if observe_current:
        current = _observe(_MAP, work)
        provenance["current_disk"] = _file_basis(current)
        current_times["_provenance"] = current.get("hash_seconds", 0.0)
    package = {"first_adapter": _file_basis(_PACKAGE_START or _unknown(_INITIALIZER))}
    if observe_current:
        current = _observe(_INITIALIZER, work)
        package["current_disk"] = _file_basis(current)
        current_times["__init__"] = current.get("hash_seconds", 0.0)
    first = [_START.get(m["name"], {}) for m in modules] + [_MAP_START or {}, _PACKAGE_START or {}]
    first_work = {"files": sum(x.get("status") == "OBSERVED" for x in first),
                  "bytes": sum(x.get("bytes", 0) for x in first)}
    return {"schema_version": "atlas.lift-receipt/2", "api_version": metadata.API_VERSION,
            "requested": requested, "closure": [m["name"] for m in modules],
            "modules": modules, "provenance_map": provenance, "package_initializer": package,
            "hash_work": {"files": work["files"], "bytes": work["bytes"]},
            "first_adapter_hash_work": first_work,
            "diagnostics": {"hash_work_seconds": work["seconds"],
                "first_adapter_hash_work_seconds": sum(x.get("hash_seconds", 0.0) for x in first),
                "first_adapter_file_hash_seconds": {m["name"]: _START.get(m["name"], {}).get("hash_seconds", 0.0) for m in modules},
                "provenance_first_adapter_hash_seconds": (_MAP_START or {}).get("hash_seconds", 0.0),
                "package_first_adapter_hash_seconds": (_PACKAGE_START or {}).get("hash_seconds", 0.0),
                "current_file_hash_seconds": current_times},
            "proof": "disk observations only; loaded_bytes_asserted:false"}


def check_current(consumed: dict) -> dict:
    """Validate and compare the exact retained, current-root consumed basis."""
    with _OBSERVATION_LOCK:
        return _check_current_observed(consumed)


def _validate_observation(value, path):
    if not isinstance(value, dict) or value.get("loaded_bytes_asserted") is not False:
        raise ValueError("LIFT-RECEIPT-PROOF-MISMATCH")
    if value.get("path") != str(path):
        raise ValueError("LIFT-RECEIPT-PATH-MISMATCH: current-root revalidation required")
    status = value.get("status")
    required = {"status", "path", "loaded_bytes_asserted"}
    if status == "OBSERVED":
        required |= {"sha256", "bytes"}
        digest = value.get("sha256")
        if (not isinstance(digest, str) or len(digest) != 71 or not digest.startswith("sha256:")
                or any(c not in "0123456789abcdef" for c in digest[7:])):
            raise ValueError("LIFT-RECEIPT-HASH-MISMATCH")
        if type(value.get("bytes")) is not int or value["bytes"] < 0:
            raise ValueError("LIFT-RECEIPT-BYTES-MISMATCH")
    elif status == "MISSING":
        required |= {"reason"}
        if not isinstance(value.get("reason"), str) or not value["reason"]:
            raise ValueError("LIFT-RECEIPT-REASON-MISMATCH")
    elif status != "UNKNOWN":
        raise ValueError("LIFT-RECEIPT-OBSERVATION-STATUS-MISMATCH")
    if set(value) != required:
        raise ValueError("LIFT-RECEIPT-OBSERVATION-FIELDS-MISMATCH")


def _validate_consumed(consumed):
    """Validate only this owner's bounded receipt, including exact selected root.

    Historical/relocated receipts remain readable data. They are not a current
    basis for another root: callers must explicitly cold-revalidate/adopt there.
    """
    stable_basis(consumed)
    metadata = _metadata()
    fields = {"schema_version", "api_version", "requested", "closure", "modules",
              "provenance_map", "package_initializer", "hash_work",
              "first_adapter_hash_work", "proof"}
    grade_fields = {"clause", "lifted", "refused"}
    extra = set(consumed) - fields - {"diagnostics"}
    if extra and extra != grade_fields:
        raise ValueError("LIFT-RECEIPT-FIELDS-MISMATCH")
    if consumed.get("api_version") != metadata.API_VERSION:
        raise ValueError("LIFT-RECEIPT-API-MISMATCH")
    if consumed.get("proof") != "disk observations only; loaded_bytes_asserted:false":
        raise ValueError("LIFT-RECEIPT-PROOF-MISMATCH")
    requested = consumed.get("requested")
    if (not isinstance(requested, list) or not all(isinstance(x, str) for x in requested)
            or requested != sorted(set(requested))):
        raise ValueError("LIFT-RECEIPT-REQUESTED-MISMATCH")
    closure = _closure(requested)
    if consumed.get("closure") != closure:
        raise ValueError("LIFT-RECEIPT-CLOSURE-MISMATCH")
    rows = consumed.get("modules")
    if (not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows)
            or [row.get("name") for row in rows] != closure):
        raise ValueError("LIFT-RECEIPT-UNIQUE-MODULES-MISMATCH")
    first = []
    current = []
    for row in rows:
        name = row["name"]
        path = _ROOT / (name + ".py")
        if set(row) not in ({"name", "qualified_name", "origin", "provenance", "first_adapter"},
                            {"name", "qualified_name", "origin", "provenance", "first_adapter", "current_disk"}):
            raise ValueError("LIFT-RECEIPT-MODULE-FIELDS-MISMATCH")
        if (row.get("qualified_name") != "atlas.reconstruction." + name
                or row.get("origin") != str(path)):
            raise ValueError("LIFT-RECEIPT-QUALIFIED-ORIGIN-MISMATCH")
        record = metadata.MODULES[name]
        expected = {k: record[k] for k in
            ("original_path", "original_sha256", "inventory_verdict", "used_for")}
        if row.get("provenance") != expected:
            raise ValueError("LIFT-RECEIPT-PROVENANCE-MISMATCH")
        _validate_observation(row.get("first_adapter"), path)
        first.append(row["first_adapter"])
        if "current_disk" in row:
            _validate_observation(row["current_disk"], path)
            current.append(row["current_disk"])
    for key, path in [("provenance_map", _MAP), ("package_initializer", _INITIALIZER)]:
        value = consumed.get(key)
        if not isinstance(value, dict) or set(value) not in (
                {"first_adapter"}, {"first_adapter", "current_disk"}):
            raise ValueError("LIFT-RECEIPT-SUPPORT-FIELDS-MISMATCH")
        _validate_observation(value["first_adapter"], path)
        first.append(value["first_adapter"])
        if "current_disk" in value:
            _validate_observation(value["current_disk"], path)
            current.append(value["current_disk"])
    if current and len(current) != len(first):
        raise ValueError("LIFT-RECEIPT-CURRENT-CLOSURE-MISMATCH")
    for key, observations in [("first_adapter_hash_work", first), ("hash_work", current)]:
        counts = consumed.get(key)
        expected = {"files": sum(x["status"] == "OBSERVED" for x in observations),
                    "bytes": sum(x.get("bytes", 0) for x in observations)}
        if (not isinstance(counts, dict) or set(counts) != {"files", "bytes"}
                or any(type(counts.get(k)) is not int for k in expected) or counts != expected):
            raise ValueError("LIFT-RECEIPT-WORK-COUNTERS-MISMATCH")
    if extra:
        # The retained grading wrapper adds only these derived legacy labels.
        expected = {row["name"]: row.get("current_disk", row["first_adapter"])
                    for row in rows if row["name"] in requested}
        if (consumed["clause"] != "A.35(a)" or consumed["lifted"] != expected
                or consumed["refused"] != {"refused_by_A35b": list(REFUSED_BY_A35),
                    "present_in_process": [], "verdict": "clean"}):
            raise ValueError("LIFT-RECEIPT-GRADING-LABELS-MISMATCH")
    return closure


def _check_current_observed(consumed):
    if consumed.get("schema_version") != "atlas.lift-receipt/2":
        raise ValueError("LIFT-RECEIPT-SCHEMA-MISMATCH")
    closure = _validate_consumed(consumed)
    recorded = {m["name"]: m for m in consumed["modules"]}
    work = {"files": 0, "bytes": 0, "seconds": 0.0}
    changes = []
    observations = []
    current_times = {}
    for name in [*closure, "_provenance", "__init__"]:
        path = _MAP if name == "_provenance" else _INITIALIZER if name == "__init__" else _ROOT / (name + ".py")
        start = (consumed["provenance_map"]["first_adapter"] if name == "_provenance"
                 else consumed["package_initializer"]["first_adapter"] if name == "__init__"
                 else recorded[name]["first_adapter"])
        current = _observe(path, work)
        observations.append({"name": name, "current_disk": _file_basis(current)})
        current_times[name] = current.get("hash_seconds", 0.0)
        live = (_MAP_START if name == "_provenance" else _PACKAGE_START
                if name == "__init__" else _START.get(name))
        if (start.get("status") != "OBSERVED" or not live
                or live.get("status") != "OBSERVED"):
            changes.append({"path": str(path), "reason": "UNKNOWN_START_BASIS"})
        elif start.get("sha256") != live.get("sha256"):
            changes.append({"path": str(path), "reason": "CONSUMED_START_BASIS_CHANGED"})
        elif start.get("bytes") != live.get("bytes"):
            raise ValueError("LIFT-RECEIPT-LIVE-BYTE-COUNT-MISMATCH")
        elif current.get("status") != "OBSERVED" or start.get("sha256") != current.get("sha256"):
            changes.append({"path": str(path), "reason": "SOURCE_CHANGED"})
        elif start.get("bytes") != current.get("bytes"):
            raise ValueError("LIFT-RECEIPT-CURRENT-BYTE-COUNT-MISMATCH")
    status = "CURRENT" if not changes else "UNPROVED" if any(
        x["reason"] == "UNKNOWN_START_BASIS" for x in changes) else "CHANGED"
    return {"schema_version": "atlas.lift-currentness/1", "status": status, "affected_paths": [x["path"] for x in changes],
            "issues": changes, "observations": observations,
            "hash_work": {"files": work["files"], "bytes": work["bytes"]},
            "diagnostics": {"hash_work_seconds": work["seconds"], "current_file_hash_seconds": current_times},
            "cold_revalidation": "Start a fresh interpreter with the selected Atlas package; rerun the consuming stage and explicitly adopt its new receipt.",
            "loaded_bytes_asserted": False}


def require_current(consumed: dict) -> dict:
    result = check_current(consumed)
    if result["status"] != "CURRENT":
        raise LiftSourceChanged(result)
    return result
