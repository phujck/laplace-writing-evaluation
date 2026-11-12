from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "atlas_s1_gate_test", ROOT / "scripts" / "atlas_s1_gate.py"
)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def _fixture(tmp_path: Path) -> Path:
    (tmp_path / "corpus_friction").mkdir()
    receipt_root = tmp_path / "atlas" / "stores" / "blueprint"
    receipt_root.mkdir(parents=True)
    rows = [
        {"record": "resolution", "id": rid, "status": "closed"}
        for rid in GATE.REQUIRED_RESOLUTIONS
    ]
    (tmp_path / "corpus_friction" / "work_orders.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    receipt = {
        "status": "sealed",
        "ledger_schema": "atlas-conceptric-sqlite/2",
        "store_identity": {"role": "blueprint-generation"},
        "event_hive_ref": "hives/events",
        "event_count": GATE.MIN_EVENT_COUNT,
        "head_digest": "sha256:" + "a" * 64,
        "claims": {
            "zero_orphans": True,
            "all_marked_chunks_present_and_hash_verified": True,
        },
        "reachability": {"status": "exact", "event_count": GATE.MIN_EVENT_COUNT},
    }
    (receipt_root / "hive-custody-receipt.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )
    return tmp_path


def test_complete_substrate_is_done_while_walk_remains_nonblocking(tmp_path: Path) -> None:
    result = GATE.evaluate(_fixture(tmp_path))
    assert result["verdict"] == "DONE"
    assert result["walk"]["status"] == "PENDING-NONBLOCKING"
    assert result["next_stage"] == "ATLAS-S2"
    assert result["residuals"] == []


def test_missing_authority_proof_reopens_the_technical_gate(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    receipt_path = root / "atlas" / "stores" / "blueprint" / "hive-custody-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["claims"]["zero_orphans"] = False
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    result = GATE.evaluate(root)
    assert result["verdict"] == "OPEN"
    assert result["walk"]["status"] == "PENDING-NONBLOCKING"
    assert "hive custody claim failed: zero orphans" in result["residuals"]
