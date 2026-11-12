"""The operator adopts an explicit fixture, preserves history, then really appends."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from laplace.representation import atlas_bridge as bridge

ROOT = Path(__file__).resolve().parents[1]


def wake():
    return bridge._event(
        bridge.EventKind.LIFECYCLE,
        bridge.LifecycleTransition(bridge.LifecycleAction.COLD_WAKE,
                                   bridge.LifecyclePhase.SLEEPING,
                                   bridge.LifecyclePhase.AWAKE,
                                   "cold:authority-adoption-test").to_dict(),
        actor=bridge.SeatRole.SYSTEM, subject="test:authority-adoption",
        provider="pytest", model="fixture", correlation_id="authority-adoption-test",
        note="wake an isolated fixture for its append proof",
    )


def observation(index):
    return bridge._event(
        bridge.EventKind.OBSERVATION,
        {"schema_version": "test.authority-adoption-observation/1", "index": index},
        actor=bridge.SeatRole.SYSTEM, subject="test:authority-adoption",
        provider="pytest", model="fixture", correlation_id="authority-adoption-test",
        note="fixture observation; no lifecycle transition",
    )


def fingerprint(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def command(root, *args):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/atlas_adopt_authority.py"),
         "--store", str(root), "--reason", "test re-adoption after source landing", *args],
        cwd=ROOT, env=dict(os.environ), capture_output=True, text=True,
    )


def test_operator_preview_banks_receipt_and_opens_real_append(tmp_path):
    root = tmp_path / "explicit"
    store = bridge.ConceptricStore(root, expected_store_role="adoption-fixture")
    first = store.append(wake())
    store.seal_custody(store_role="adoption-fixture")
    before = fingerprint(root)
    preview = command(root, "--dry-run")
    assert preview.returncode == 0, preview.stdout + preview.stderr
    planned = json.loads(preview.stdout)
    assert planned["status"] == "DRY-RUN"
    assert planned["checkpoint"]["cursor"] == 1
    assert fingerprint(root) == before
    adopted = command(root)
    assert adopted.returncode == 0, adopted.stdout + adopted.stderr
    result = json.loads(adopted.stdout)
    assert result["checkpoint_digest"] == planned["checkpoint_digest"]
    assert result["store_role"] == "adoption-fixture"
    assert result["beat"] == "ATLAS-AUTHORITY-RE-ADOPTION"
    assert result["cost"]["diff"] == 0
    assert result["cost"]["rows_verified"] == 1
    assert result["cost"]["reason"] == "test re-adoption after source landing"
    assert result["reachability_status"] == "exact"
    assert result["ordering_rule"].endswith("re-adopt every store -> measure")
    assert result["wal_checkpoint"][0] == 0
    assert result["custody_resealed"] is True
    assert result["custody_ledger_sha256"].startswith("sha256:")
    wal = root / "conceptric.sqlite3-wal"
    assert not wal.exists() or wal.stat().st_size == 0
    with sqlite3.connect(root / "conceptric.sqlite3") as db:
        body = json.loads(db.execute("SELECT value FROM meta WHERE key=?",
                                    (result["receipt_key"],)).fetchone()[0])
    assert bridge.chash(body) == result["receipt_handle"]
    writer = bridge.ConceptricStore(
        root, expected_store_role="adoption-fixture",
    )
    second = writer.append(observation(2))
    assert second.sequence == first.sequence + 1
    writer.seal_custody(store_role="adoption-fixture")
    cold = bridge.ConceptricStore(root, read_only=True)
    assert [event.event_id for event in cold.events()] == [first.event.event_id, second.event.event_id]
    assert cold.verify_custody()["event_count"] == 2
    assert bridge.ConceptricStore.verify_authority_checkpoint_deep(
        root, expected_store_role="adoption-fixture",
    )["fast_deep_equal"]


def test_missing_store_is_refused_without_genesis(tmp_path):
    root = tmp_path / "absent"
    result = command(root)
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "REFUSED"
    assert not root.exists()


def test_operator_re_adopts_unanchored_store(tmp_path):
    root = tmp_path / "unanchored"
    store = bridge.ConceptricStore(root)
    store.append(wake())

    adopted = command(root)

    assert adopted.returncode == 0, adopted.stdout + adopted.stderr
    result = json.loads(adopted.stdout)
    assert result["store_role"] is None
    assert result["verified_status"] == "CURRENT"
    assert result["custody_resealed"] is False
    assert bridge.ConceptricStore.read_authority_checkpoint(root)["status"] == "CURRENT"


def test_moved_predecessor_leaves_store_unchanged(tmp_path):
    root = tmp_path / "explicit"
    store = bridge.ConceptricStore(root, expected_store_role="adoption-fixture")
    store.append(wake())
    store.seal_custody(store_role="adoption-fixture")
    before = fingerprint(root)
    with pytest.raises(bridge.StoreError, match="predecessor moved"):
        bridge.prepare_authority_epoch(root=root, expected_predecessor="sha256:" + "0" * 64,
                                       dry_run=True)
    assert fingerprint(root) == before


def test_preview_refuses_uncheckpointed_wal_without_writing(tmp_path):
    root = tmp_path / "explicit"
    store = bridge.ConceptricStore(root, expected_store_role="adoption-fixture")
    store.append(wake())
    store.seal_custody(store_role="adoption-fixture")
    with sqlite3.connect(store.path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("INSERT INTO meta(key, value) VALUES ('test-wal', 'pending')")
        db.commit()
        before = fingerprint(root)
        result = command(root, "--dry-run")
        assert result.returncode == 1
        assert "checkpointed WAL" in json.loads(result.stdout)["cause"]
        assert fingerprint(root) == before


def test_preview_refuses_forged_predecessor_prefix(tmp_path):
    root = tmp_path / "explicit"
    store = bridge.ConceptricStore(root, expected_store_role="adoption-fixture")
    store.append(wake())
    store.seal_custody(store_role="adoption-fixture")
    with sqlite3.connect(store.path) as db:
        body = json.loads(db.execute("SELECT checkpoint_json FROM authority_checkpoint").fetchone()[0])
        body["head_record_digest"] = "sha256:" + "f" * 64
        db.execute("UPDATE authority_checkpoint SET checkpoint_json=?, checkpoint_digest=?",
                   (bridge.canonical_json(body), bridge.chash(body)))
        db.commit()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    before = fingerprint(root)
    result = command(root, "--dry-run")
    assert result.returncode == 1
    assert "not on the ledger prefix" in json.loads(result.stdout)["cause"]
    assert fingerprint(root) == before
