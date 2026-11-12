"""Cold, bounded entry derived from verified Atlas ledger descent.

Only the container's store location is configuration. Generation identities and roots
come from completed store records. Absent registrations remain typed issues; files
beside a store are never guessed to be its current snapshot, dataset, or verdict.
"""
from __future__ import annotations

import argparse
import base64
import json
import shlex
import sys
from pathlib import Path
from typing import Any

from .cards import (_read_json as _read_cache_json, _write_json as _write_cache_json,
                    card_page, compute_registry, get_card)
from .errors import AtlasError, StoreError
from .ids import canonical_json, chash

BYTE_CAP = 8192
PAGE_SIZE = 8
CONTAINER_ROOT = Path(__file__).resolve().parents[2] / "atlas"  # src/atlas since core consolidation R2: the container is <checkout>/atlas
SNAPSHOT_RECEIPT_SCHEMA = "atlas.entry-snapshot-receipt/1"


def default_store() -> Path:
    """Resolve the self-hosting blueprint-generation store from its manifest."""
    manifest = json.loads((CONTAINER_ROOT / "blueprint_manifest.json").read_text())
    if (manifest.get("schema_version") != "atlas.blueprint-manifest/1"
            or not isinstance(manifest.get("store"), str) or not manifest["store"].strip()):
        raise StoreError("invalid blueprint store declaration", code="ENTRY-BLUEPRINT-INVALID")
    target = (CONTAINER_ROOT / manifest["store"].removeprefix("atlas/")).resolve()
    if not target.is_relative_to(CONTAINER_ROOT.resolve()):
        raise StoreError("blueprint store escapes container", code="ENTRY-BLUEPRINT-INVALID")
    return target


def _dataset_registrations(root: Path | None = None):
    """Enumerate the dataset catalog only; store directories are never discovered by walking."""
    if root is not None and not root.resolve().is_relative_to(CONTAINER_ROOT.resolve()):
        return
    for path in sorted((CONTAINER_ROOT / "datasets").glob("*.json")):
        manifest = json.loads(path.read_text())
        core = manifest["core"]
        if (manifest.get("schema_version") != "atlas.dataset-manifest/1"
                or chash({"schema_version": manifest["schema_version"], "core": core})
                != manifest["manifest_handle"]):
            raise StoreError("dataset catalog identity mismatch", code="ENTRY-DATASET-INVALID")
        target = (CONTAINER_ROOT / core["store"]).resolve()
        if not target.is_relative_to(CONTAINER_ROOT.resolve()):
            raise StoreError("dataset store escapes container", code="ENTRY-DATASET-INVALID")
        if root is None or target == root.resolve():
            yield manifest, target


def _registered_snapshot(root: Path, observations: dict[str, Any]) -> dict[str, Any] | None:
    from .snapshot import load_snapshot
    from .tools.build_spans import dataset_snapshot_dir, verified_segmentation
    # Resolve the store's provenance before consulting any dataset catalog.
    event = next((row["event"] for row in observations["events"]
                  if str(row["event"]["payload"].get("schema_version", "")).startswith(
                      "atlas.blueprint-generation/")), None)
    if event is None or not any(ref.get("source_id") == "atlas:dataset-manifest"
                               for ref in event.get("provenance", [])):
        return None
    for manifest, _ in _dataset_registrations(root):
        handle = manifest["manifest_handle"]
        # The latest completed generation is the current extent; older matching provenance
        # must not hide a newer generation poured from different inputs.
        if not any(ref.get("source_id") == "atlas:dataset-manifest"
                and ref.get("digest") == handle for ref in event.get("provenance", [])):
            continue
        path = dataset_snapshot_dir(manifest, CONTAINER_ROOT)
        if not (path / "manifest.json").is_file():
            continue
        snap = load_snapshot(path)
        core = manifest["core"]
        prefix = f"dataset:{core['dataset_id']}://"
        if (snap.manifest.manifest_handle != handle
                or snap.manifest.pinned_commit != core["pinned_commit"]
                or snap.manifest.commit_sha != core["pinned_commit"]):
            raise StoreError("snapshot disagrees with registered dataset generation",
                             code="ENTRY-SNAPSHOT-PROVENANCE-MISMATCH")
        receipt_path = (CONTAINER_ROOT / ".cache" / "entry-snapshots" /
                        (chash({"snapshot_id": snap.manifest.snapshot_id}).split(":", 1)[1] + ".json"))
        receipt = _read_cache_json(receipt_path)
        if not (receipt and receipt.get("schema_version") == SNAPSHOT_RECEIPT_SCHEMA
                and receipt.get("snapshot_id") == snap.manifest.snapshot_id
                and receipt.get("manifest_handle") == handle
                and receipt.get("pinned_commit") == core["pinned_commit"]
                and receipt.get("sources") == snap.manifest.sources
                and isinstance(receipt.get("expected_roots"), dict)):
            snap.verify()
            verified_segmentation(path)
            nodes = list(snap.iter_nodes())
            source_paths = sorted(n.path for n in nodes)
            if snap.manifest.sources != source_paths:
                raise StoreError("snapshot disagrees with registered dataset generation",
                                 code="ENTRY-SNAPSHOT-PROVENANCE-MISMATCH")
            receipt = {
                "schema_version": SNAPSHOT_RECEIPT_SCHEMA,
                "snapshot_id": snap.manifest.snapshot_id,
                "manifest_handle": handle,
                "pinned_commit": core["pinned_commit"],
                "sources": source_paths,
                "expected_roots": {prefix + n.path: n.content_hash for n in nodes},
            }
            _write_cache_json(receipt_path, receipt)
        if (event["payload"].get("source_roots") != receipt["expected_roots"]):
            raise StoreError("snapshot disagrees with registered dataset generation",
                             code="ENTRY-SNAPSHOT-PROVENANCE-MISMATCH")
        return {"snapshot_id": snap.manifest.snapshot_id, "manifest_handle": handle,
                "path": str(path), "event_id": event["event_id"]}
    return None


def _command(root: Path, *args: str) -> str:
    # Carry the actual interpreter and this container's source, rather than let a
    # subsequent shell choose a legacy virtual environment's `python` from PATH.
    return shlex.join(["env", f"PYTHONPATH={CONTAINER_ROOT / 'src'}", sys.executable,
                       "-s", "-B", "-m", "atlas.entry", "--json", "--store", str(root),
                       *(str(arg) for arg in args)])


def encode_entry(value: dict[str, Any], *, byte_cap: int = BYTE_CAP) -> bytes:
    data = (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    if len(data) > byte_cap:
        raise StoreError("entry exceeds declared byte cap", code="BUDGET", bytes=len(data), cap=byte_cap)
    return data


def build_entry(root: Path | None = None, *, before: int | None = None,
                expected_head: str | None = None) -> dict[str, Any]:
    from .history import EventKind
    from .store import ConceptricStore
    default = root is None
    root = Path(root) if root is not None else default_store()
    page = ConceptricStore.read_event_descent(root, before=before, limit=PAGE_SIZE,
                                             expected_head=expected_head)
    head = page["head"]
    # Observation is a typed, indexed family. This read is bounded even in a store
    # whose last completed generation is older than this page; the omission carries
    # the continuation instead of silently scanning lifetime history.
    observations = ConceptricStore.read_event_descent(
        root, limit=PAGE_SIZE, kind=EventKind.OBSERVATION.value, expected_head=head)
    result: dict[str, Any] = {
        "schema_version": "atlas.entry/1", "status": "PARTIAL", "byte_cap": BYTE_CAP,
        "serving_store": {"path": str(root), "reason":
            "default: blueprint_manifest.json selects the self-hosting blueprint-generation store"
            if default else "explicit store selection"},
        "head": head, "event_count": page["event_count"],
        "blueprint_generation": None, "fibre_roots": [], "dataset_manifests": [],
        "latest_bench_verdicts": [], "snapshot_id": None, "records": [],
        "omissions": [], "issues": [], "enumerated_store_dirs": False,
        "descend_command": _command(root, "--event", "<event_id>", "--head", head),
    }
    for manifest, target in (_dataset_registrations() if default else ()):
        result["dataset_manifests"].append({"handle": manifest["manifest_handle"],
            "descend": _command(target)})
    registry = compute_registry()
    for field in ("verbs", "structure"):
        result[field] = [{"face": card["face"], "id": card["id"]} for card in registry[field][:PAGE_SIZE]]
        result["omissions"].append({
            "field": field, "reason": "full cards and remaining ids descend separately",
            "total": len(registry[field]), "descend": "python -m atlas.entry --card <id>",
            "index": f"python -m atlas.entry --cards {field}",
        })
    result["issues"].extend(registry["issues"][:PAGE_SIZE])
    if len(registry["issues"]) > PAGE_SIZE:
        result["omissions"].append({"field": "card issues", "count": len(registry["issues"]) - PAGE_SIZE,
                                    "descend": "python -m atlas.entry --cards issues"})
    seen_benches = set()
    for row in observations["events"]:
        event = row["event"]
        body = event["payload"]
        schema = str(body.get("schema_version", ""))
        descend = _command(root, "--event", event["event_id"], "--head", head)
        if schema.startswith("atlas.blueprint-generation/") and result["blueprint_generation"] is None:
            from .blueprint import BlueprintGeneration
            generation = BlueprintGeneration.from_dict(body)
            result["blueprint_generation"] = {"handle": generation.generation_id,
                                               "event_id": event["event_id"], "descend": descend}
            for cluster in generation.clusters:
                result["fibre_roots"].append({
                    "fibre": cluster["fibre"], "object_id": cluster["coarse_object_id"],
                    "handle": cluster["node_handle"],
                    "event_id": cluster["promotion_event_id"],
                })
        if schema == "atlas.dataset-manifest/1":
            result["dataset_manifests"].append({"handle": body["manifest_handle"], "descend": descend})
        if "bench" in schema and "verdict" in body:
            name = str(body.get("bench_id", body.get("benchmark", schema)))
            if name not in seen_benches:
                seen_benches.add(name)
                result["latest_bench_verdicts"].append({"bench": name, "verdict": body["verdict"], "descend": descend})
        if result["snapshot_id"] is None and schema == "record-snapshot/1":
            result["snapshot_id"] = body["snapshot_id"]
    if result["snapshot_id"] is None:
        registered = _registered_snapshot(root, observations)
        if registered:
            result["snapshot_id"] = registered["snapshot_id"]
            result["snapshot"] = registered
            if not any(row["handle"] == registered["manifest_handle"] for row in result["dataset_manifests"]):
                result["dataset_manifests"].append({"handle": registered["manifest_handle"],
                    "descend": _command(root, "--event", registered["event_id"], "--head", head)})
    for row in page["events"]:
        event = row["event"]
        result["records"].append({"sequence": row["sequence"], "handle": event["event_id"],
                                  "kind": event["kind"],
                                  "event_id": event["event_id"]})
    for name, selected in (("records", page), ("observation-family", observations)):
        if selected["next_before"] is not None:
            result["omissions"].append({"field": name, "reason": "older records outside this page",
                "descend": _command(root, "--before", selected["next_before"], "--head", head)})
    for field, owner in (("blueprint_generation", "blueprint-pour"),
                         ("dataset_manifests", "dataset-pour"),
                         ("latest_bench_verdicts", "bench-publication"),
                         ("snapshot_id", "snapshot-export-registration")):
        if not result[field]:
            result["issues"].append({"code": "ENTRY-REGISTRATION-NOT-REACHED", "field": field,
                                     "owner": owner, "reason": "no declaration in the bounded observation page"})
    result["omissions"].append({"field": "record bodies", "reason": "exact envelopes descend in 1024-byte base64 pages"})
    # Trim only with a continuation to the complete generation/event envelope.
    for field in ("fibre_roots", "records", "structure", "verbs", "dataset_manifests", "latest_bench_verdicts"):
        omitted = 0
        removed = None
        minimum = 4 if field in {"verbs", "structure"} else 1
        while len((json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n").encode()) > BYTE_CAP - 450 and len(result[field]) > minimum:
            removed = result[field].pop()
            omitted += 1
        if omitted:
            if field in {"verbs", "structure"}:
                next(o for o in result["omissions"] if o["field"] == field)["shown"] = len(result[field])
                continue
            continuation = (f"python -m atlas.entry --cards {field}" if field in {"verbs", "structure"} else
                            result["blueprint_generation"]["descend"] if field == "fibre_roots"
                            else _command(root, "--before", removed["sequence"] + 1, "--head", head)
                            if field == "records" else removed["descend"])
            result["omissions"].append({"field": field, "count": omitted, "reason": "entry byte cap",
                                         "descend": continuation})
    encode_entry(result)
    return result


def descend_event(root: Path, event_id: str, *, offset: int = 0,
                  expected_head: str | None = None) -> dict[str, Any]:
    from .store import ConceptricStore
    if offset < 0:
        raise StoreError("negative byte offset", code="BUDGET")
    page = ConceptricStore.read_event_descent(root, event_id=event_id, limit=1, expected_head=expected_head)
    if not page["events"]:
        raise StoreError("event does not resolve", code="NOT_FOUND", event_id=event_id)
    row = page["events"][0]
    data = canonical_json(row["event"]).encode()
    chunk = data[offset:offset + 1024]
    return {"schema_version": "atlas.entry-bytes/1", "byte_cap": BYTE_CAP,
            "head": page["head"], "content_hash": row["event_handle"], "total_bytes": len(data),
            "offset": offset, "bytes_base64": base64.b64encode(chunk).decode(),
            "next": _command(root, "--event", event_id, "--offset", offset + len(chunk), "--head", page["head"])
                    if offset + len(chunk) < len(data) else None,
            "omitted_before": min(offset, len(data)), "omitted_after": max(0, len(data) - offset - len(chunk))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--store", type=Path)
    parser.add_argument("--before", type=int)
    parser.add_argument("--head")
    parser.add_argument("--event")
    parser.add_argument("--card")
    parser.add_argument("--cards", choices=("verbs", "structure", "issues"))
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()
    try:
        if args.card:
            value = get_card(args.card)
        elif args.cards:
            value = card_page(args.cards, args.offset)
        else:
            value = descend_event(args.store or default_store(), args.event, offset=args.offset,
                expected_head=args.head) if args.event else build_entry(
                args.store, before=args.before, expected_head=args.head)
        print(encode_entry(value).decode(), end="")
        return 0
    except (AtlasError, OSError, ValueError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc), "owner": "store-entry"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
