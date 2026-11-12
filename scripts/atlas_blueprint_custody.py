#!/usr/bin/env python3
"""Build the custody tier for the Atlas's first real corpus: its own blueprint.

This is deliberately the *mechanical* tier only.  It inventories exact source objects,
content digests and stable logical ids.  It makes no CONFIRMS / CONTRADICTS /
SUPERSEDES / REFINES claims; those belong to the proposal and independent-judgement
tiers.  The output is a deterministic receipt, not a second live store.

    /usr/bin/python3 scripts/atlas_blueprint_custody.py --write
    /usr/bin/python3 scripts/atlas_blueprint_custody.py --check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SCHEMA = "atlas-blueprint-custody/1"
OUT = ROOT / "evidence" / "ATLAS_BLUEPRINT_CUSTODY_2026-08-24"

# The blueprint's design-bearing authored record.  Outward deliverables, personal
# profiles and soul are intentionally outside this corpus.  Session handoffs are in:
# they carry the historical design deltas the authored DESIGN nodes consolidated.
AUTHORED_PREFIXES = (
    "ARMING_", "AUDIT_", "BRIEF_", "CALIBRATION_", "CENSUS_", "CHARTER_",
    "DECISION_", "DESIGN_", "EVIDENCE_", "FEEDBACK_", "FRICTION_", "INCIDENT_",
    "META_TEST_", "PLAN_", "PROXY_", "REMOTE_", "RULING_", "SCOUT_",
    "SESSION_HANDOFF_", "SYNTHESIS_",
)
AUTHORED_SINGLETONS = (
    "ATLAS_MATHEMATICS.md", "ATLAS_SYSTEM.md", "EIGEN_ARCHITECTURE.md",
)

# The eleven typed decision/account stores commissioned with the first pour.  The
# list is explicit so widening the custody perimeter is a reviewable change.
TYPED_STORES = (
    "contract/promises.jsonl",
    "contract/predictions.jsonl",
    "contract/seats.jsonl",
    "contract/talk.jsonl",
    "corpus_friction/campaign.jsonl",
    "corpus_friction/work_orders.jsonl",
    "corpus_friction/atlas_inventory.jsonl",
    "corpus_friction/edges.jsonl",
    "corpus_friction/methods.jsonl",
    "corpus_friction/open_stack_forks.jsonl",
    "corpus_friction/open_stack_wants.jsonl",
)

EVIDENCE_NAMES = (
    "report", "verdict", "comparison", "design_spec", "preregistration", "packet",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _record(kind: str, logical_id: str, source: str, content: bytes,
            **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "kind": kind,
        "logical_id": logical_id,
        "source": source,
        "content_handle": _sha(content),
        "size_bytes": len(content),
        **extra,
    }


def authored_records(root: Path) -> list[dict[str, Any]]:
    paths = [
        path for path in root.glob("*.md")
        if path.name in AUTHORED_SINGLETONS
        or ("2026-" in path.name and path.name.startswith(AUTHORED_PREFIXES))
    ]
    return [
        _record("authored-design", f"atlas-blueprint:file:{path.name}", path.name,
                path.read_bytes())
        for path in sorted(paths)
    ]


def evidence_records(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base = root / "evidence"
    records: list[dict[str, Any]] = []
    residuals: list[dict[str, Any]] = []
    for tree in sorted(path for path in base.iterdir() if path.is_dir()):
        if tree.resolve() == OUT.resolve():
            continue  # a custody receipt never ingests or residualises itself
        selected = []
        for path in sorted(p for p in tree.rglob("*") if p.is_file()):
            stem = path.stem.casefold()
            if any(stem.startswith(name) for name in EVIDENCE_NAMES):
                selected.append(path)
        if not selected:
            residuals.append({
                "kind": "evidence-tree-without-report-grain",
                "source": tree.relative_to(root).as_posix(),
                "cost": "unrepresented until a report/verdict-grain carrier is adjudicated",
            })
        for path in selected:
            rel = path.relative_to(root).as_posix()
            records.append(_record(
                "evidence-grain", f"atlas-blueprint:file:{rel}", rel, path.read_bytes(),
                evidence_tree=tree.name,
            ))
    return records, residuals


def typed_row_records(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    residuals: list[dict[str, Any]] = []
    for rel in TYPED_STORES:
        path = root / rel
        if not path.is_file():
            residuals.append({"kind": "missing-typed-store", "source": rel, "cost": "absent"})
            continue
        with path.open("rb") as handle:
            for line_no, raw in enumerate(handle, start=1):
                content = raw.rstrip(b"\r\n")
                if not content.strip():
                    continue
                try:
                    row = json.loads(content)
                except ValueError as exc:
                    residuals.append({
                        "kind": "malformed-typed-row", "source": f"{rel}:{line_no}",
                        "cost": str(exc),
                    })
                    continue
                row_key = str(row.get("id") or row.get("event_id") or row.get("target") or "")
                stable = row_key or _sha(content).removeprefix("sha256:")[:20]
                logical_id = f"atlas-blueprint:row:{rel}#{stable}@{line_no}"
                records.append(_record(
                    "typed-row", logical_id, f"{rel}:{line_no}", content,
                    store=rel, row_id=row_key or None,
                ))
    return records, residuals


def fabric_records() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Project the verified external Atlas chain without copying message bodies.

    Body handles remain resolvable in Atlas's own blob store.  Missing body blobs are
    loud custody residuals.  The chain rows themselves are included whole, with their
    record digests, so a later pour can check rather than trust this projection.
    """
    from laplace.representation import atlas_bridge

    store = atlas_bridge._store()
    blobs = atlas_bridge._blobs()
    records: list[dict[str, Any]] = []
    residuals: list[dict[str, Any]] = []
    for stored in store._read_rows():
        payload = _canonical(stored.to_dict()).encode("utf-8")
        event = stored.event
        records.append(_record(
            "fabric-event", f"atlas-blueprint:fabric:{event.event_id}",
            f"atlas-fabric:event:{stored.sequence}", payload,
            sequence=stored.sequence, event_id=event.event_id,
            record_digest=stored.record_digest,
        ))
        for ref in event.provenance:
            if (ref.locator or "").startswith("blob:") and not blobs.has(ref.digest):
                residuals.append({
                    "kind": "missing-fabric-body", "source": event.event_id,
                    "content_handle": ref.digest, "cost": "unresolvable body",
                })
    return records, residuals


def commit_records(root: Path) -> list[dict[str, Any]]:
    fmt = "%H%x1f%cI%x1f%s"
    proc = subprocess.run(
        ["git", "log", "--reverse", f"--format={fmt}", "--since=2026-06-01"],
        cwd=root, check=True, capture_output=True, text=True,
    )
    records = []
    for line in proc.stdout.splitlines():
        commit, occurred_at, subject = line.split("\x1f", 2)
        content = _canonical({"commit": commit, "occurred_at": occurred_at,
                              "subject": subject}).encode("utf-8")
        records.append(_record(
            "commit", f"atlas-blueprint:commit:{commit}", f"git:{commit}", content,
            commit=commit, occurred_at=occurred_at,
        ))
    return records


def build(root: Path = ROOT) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    evidence, evidence_residuals = evidence_records(root)
    typed, typed_residuals = typed_row_records(root)
    fabric, fabric_residuals = fabric_records()
    records = [
        *authored_records(root), *evidence, *typed, *fabric, *commit_records(root),
    ]
    records.sort(key=lambda row: row["logical_id"])
    logical_ids = [row["logical_id"] for row in records]
    if len(logical_ids) != len(set(logical_ids)):
        raise RuntimeError("custody logical ids are not unique")
    residuals = sorted(
        [*evidence_residuals, *typed_residuals, *fabric_residuals],
        key=lambda row: (row["kind"], row["source"]),
    )
    records_bytes = b"".join((_canonical(row) + "\n").encode("utf-8") for row in records)
    counts: dict[str, int] = {}
    for row in records:
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True,
    ).stdout.strip()
    status_lines = subprocess.run(
        ["git", "status", "--porcelain=v1"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.splitlines()
    out_rel = OUT.relative_to(root).as_posix() + "/"
    dirty_paths = sorted(
        line[3:] for line in status_lines
        if len(line) > 3 and not line[3:].replace("\\", "/").startswith(out_rel)
    )
    manifest_core = {
        "schema_version": SCHEMA,
        "corpus_id": "atlas-blueprint",
        "tier": "mechanical-custody",
        "head": git_head,
        "tree_posture": {
            "rebuildable_from_head": not dirty_paths,
            "dirty_paths_excluding_this_receipt": dirty_paths,
            "note": ("content handles pin the observed bytes; HEAD alone does not reproduce "
                     "an observed dirty or untracked source"),
        },
        "records_handle": _sha(records_bytes),
        "record_count": len(records),
        "counts": counts,
        "typed_stores": list(TYPED_STORES),
        "residuals": residuals,
        "semantic_edge_status": "NOT-MINTED — proposal and judgement tiers are separate",
        "soul_posture": "refs-only; soul paths are outside this custody universe",
    }
    manifest = {
        **manifest_core,
        "generation_id": _sha(_canonical(manifest_core).encode("utf-8")),
    }
    return manifest, records


def _bytes(manifest: dict[str, Any], records: Iterable[dict[str, Any]]) -> tuple[bytes, bytes]:
    manifest_bytes = (_canonical(manifest) + "\n").encode("utf-8")
    records_bytes = b"".join((_canonical(row) + "\n").encode("utf-8") for row in records)
    return manifest_bytes, records_bytes


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    try:
        with tmp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        manifest_path, records_path = OUT / "manifest.json", OUT / "custody.jsonl"
        if not manifest_path.is_file() or not records_path.is_file():
            print(json.dumps({"status": "ABSENT", "out": str(OUT.relative_to(ROOT))}, indent=1))
            return 1
        try:
            stored = json.loads(manifest_path.read_text(encoding="utf-8"))
            stored_records_bytes = records_path.read_bytes()
            stored_records = [json.loads(line) for line in stored_records_bytes.splitlines()
                              if line.strip()]
            core = dict(stored)
            generation_id = core.pop("generation_id")
            integrity_errors = []
            if generation_id != _sha(_canonical(core).encode("utf-8")):
                integrity_errors.append("generation_id")
            if stored.get("records_handle") != _sha(stored_records_bytes):
                integrity_errors.append("records_handle")
            if stored.get("record_count") != len(stored_records):
                integrity_errors.append("record_count")
            ids = [row.get("logical_id") for row in stored_records]
            if len(ids) != len(set(ids)):
                integrity_errors.append("logical_id uniqueness")
        except (OSError, ValueError, TypeError) as exc:
            print(json.dumps({"status": "INVALID", "error": f"{type(exc).__name__}: {exc}"},
                             indent=1))
            return 1
        current, _ = build(ROOT)
        fresh = current["generation_id"] == stored["generation_id"]
        if integrity_errors:
            print(json.dumps({"status": "INVALID", "errors": integrity_errors,
                              "generation_id": stored.get("generation_id")}, indent=1))
            return 1
        print(json.dumps({
            "status": "CURRENT" if fresh else "VALID-PINNED; LIVE FRONTIER MOVED",
            "generation_id": stored["generation_id"],
            "current_generation_id": current["generation_id"],
            "fresh": fresh,
            "record_count": stored["record_count"],
            "residual_count": len(stored.get("residuals", [])),
            "out": str(OUT.relative_to(ROOT)),
        }, indent=1))
        return 0
    else:
        manifest, records = build(ROOT)
        manifest_bytes, records_bytes = _bytes(manifest, records)
        _atomic(OUT / "manifest.json", manifest_bytes)
        _atomic(OUT / "custody.jsonl", records_bytes)
    print(json.dumps({
        "status": "CURRENT", "generation_id": manifest["generation_id"],
        "record_count": manifest["record_count"], "counts": manifest["counts"],
        "residual_count": len(manifest["residuals"]), "out": str(OUT.relative_to(ROOT)),
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
