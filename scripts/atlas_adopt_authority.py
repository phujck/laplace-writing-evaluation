#!/usr/bin/env python3
"""Run the named Atlas writer-authority re-adoption beat.

The receipt is banked atomically in the store's ledger metadata. Dry-run verifies the
ledger and reports the checkpoint it would seal without writing any store files.
Every landed change to errors.py, history.py, ids.py, state.py, or store.py invalidates
every store checkpoint: land code, re-adopt every store, then measure. Travelling custody
sealing remains a separate, explicit commit-boundary act.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src"))

# THE SEAL (tests/test_atlas_seal.py): src/laplace/representation/atlas_bridge.py is the ONE door into the atlas
# package. This script reached past it on 2026-09-15 and the seal caught it, which is the first
# time that gate has caught anything real - it stays.
from laplace.representation.atlas_bridge import AtlasError, StoreError, ConceptricStore  # noqa: E402


def _store_role(reader: ConceptricStore) -> str | None:
    with reader._locked(shared=True), reader._connect() as connection:
        identities = [
            json.loads(row["value"])
            for row in connection.execute(
                "SELECT value FROM meta WHERE key IN "
                "('store_identity_json', 'store_role_anchor_json')"
            )
        ]
    if not identities:
        return None
    for identity in identities:
        reader._validate_store_identity(identity, operation="authority re-adoption")
    if any(identity != identities[0] for identity in identities):
        raise StoreError("authority re-adoption store identity and role anchor disagree")
    return str(identities[0]["role"])


def re_adopt(root: Path, *, reason: str, dry_run: bool) -> dict:
    root = Path(root).expanduser().resolve()
    reason = str(reason).strip()
    if not reason:
        raise StoreError("authority re-adoption requires a reason")
    if dry_run:
        wal = root / "conceptric.sqlite3-wal"
        if wal.is_file() and wal.stat().st_size:
            raise StoreError("dry-run authority re-adoption requires a checkpointed WAL")
    reader = ConceptricStore(root, read_only=True, immutable=dry_run)
    role = _store_role(reader)
    reachability = reader.hive_reachability()
    reader._require_exact_reachability(reachability)
    context = ConceptricStore.authority_context_manifest(root, store_role=role)
    inspection = ConceptricStore.verify_authority_checkpoint_deep(
        root,
        expected_context=context,
        expected_store_role=role,
        immutable=dry_run,
    )
    predecessor = inspection.get("verified_predecessor")
    if not predecessor:
        raise StoreError(
            "authority re-adoption predecessor verification refused",
            inspection=inspection,
        )
    candidate = inspection["candidate_checkpoint"]
    anchor = inspection.get("checkpoint")
    anchor_cursor = 0 if not isinstance(anchor, dict) else int(anchor["cursor"])
    cost = {
        "schema_version": "atlas.authority-re-adoption-cost/1",
        "unit": "ledger-events",
        "diff": int(candidate["cursor"]) - anchor_cursor,
        "rows_verified": int(candidate["cursor"]),
        "reason": reason,
    }
    if dry_run:
        return {
            "schema_version": "atlas.authority-re-adoption-preview/1",
            "status": "DRY-RUN",
            "beat": "ATLAS-AUTHORITY-RE-ADOPTION",
            "store": os.fspath(root),
            "store_role": role,
            "expected_predecessor": predecessor,
            "checkpoint": candidate,
            "checkpoint_digest": inspection["candidate_checkpoint_digest"],
            "authority_context": context,
            "event_append": False,
            "reachability_status": reachability["status"],
            "ledger_checkpoint_write": False,
            "would_reseal_existing_custody": reader.custody_receipt_path.is_file(),
            "cost": cost,
            "ordering_rule": (
                "land code touching errors.py/history.py/ids.py/state.py/store.py -> "
                "re-adopt every store -> measure"
            ),
        }
    prepared = ConceptricStore.prepare_authority_checkpoint(
        root,
        expected_predecessor=predecessor,
        authority_context=context,
        expected_store_role=role,
        reason=reason,
    )
    custody_receipt = None
    if reader.custody_receipt_path.is_file():
        if role is None:
            raise StoreError("sealed store has no role for custody re-sealing")
        writer = ConceptricStore(
            root,
            expected_store_role=role,
            authority_context=context,
        )
        custody_receipt = writer.seal_custody(store_role=role)
    verified = ConceptricStore.read_authority_checkpoint(root, expected_context=context)
    if verified["status"] != "CURRENT":
        raise StoreError("re-adopted authority checkpoint did not verify", verification=verified)
    return {
        **prepared,
        "store": os.fspath(root),
        "store_role": role,
        "reachability_status": reachability["status"],
        "verified_status": verified["status"],
        "custody_resealed": custody_receipt is not None,
        "custody_ledger_sha256": (
            None if custody_receipt is None else custody_receipt["ledger_sha256"]
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = re_adopt(args.store, reason=args.reason, dry_run=args.dry_run)
    except (AtlasError, OSError, ValueError) as exc:
        print(json.dumps({"status": "REFUSED", "error_type": type(exc).__name__,
                          "cause": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
