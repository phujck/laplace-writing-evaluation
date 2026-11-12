"""The reusable INSTRUMENT serve contract: banked math, verified before projection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from laplace.representation import instrument_serve

ROOT = Path(__file__).resolve().parents[1]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_real_diffusion_instrument_has_current_custody_and_inputs():
    projection = instrument_serve.project(ROOT, "diffusion-scissors/1")
    receipt = ROOT / projection["receipt"]

    assert projection["class"] == "INSTRUMENT"
    assert projection["status"] == "CURRENT"
    assert projection["custody"]["status"] == "PASS"
    assert projection["receipt_content_handle"] == f"sha256:{_sha(receipt)}"
    assert projection["inputs"]
    assert {row["status"] for row in projection["inputs"]} == {"PASS"}
    assert projection["channel_class"] == "DERIVED"
    assert projection["registry"] == {
        "preimage": projection["preimage"],
        "reader": projection["reader"],
        "retirement": projection["retirement"],
    }


def test_input_drift_and_detached_custody_fail_loudly(tmp_path, monkeypatch):
    store = tmp_path / "store"
    store.mkdir()
    source = store / "vectors.bin"
    source.write_bytes(b"banked-input")
    receipt = {
        "instrument": "test/1",
        "dials": {"corpus_store": "store", "t_sweep": [0, 1]},
        "input_sha256": {"vectors.bin": _sha(source)},
        "results": {"per_t": {"0": {"channel": 1.0}}},
    }
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    sidecar = tmp_path / "receipt.sha256"
    sidecar.write_text(f"{_sha(receipt_path)}  receipt.json\n", encoding="utf-8")
    monkeypatch.setitem(instrument_serve.REGISTRY, "test/1", {
        "receipt": "receipt.json",
        "custody_sidecar": "receipt.sha256",
        "producer": "this-producer-does-not-exist.py",
        "preimage": ["test-preimage"],
        "reader": "test reader",
        "retirement": "test retirement",
        "derived_channels": ["channel"],
        "non_claim": "test nonclaim",
    })

    current = instrument_serve.project(tmp_path, "test/1")
    assert current["status"] == "CURRENT"
    assert current["renew"].endswith("this-producer-does-not-exist.py")
    assert instrument_serve.source_paths(tmp_path, "test/1") == (
        "receipt.json", "receipt.sha256", "store/vectors.bin")

    source.write_bytes(b"moved-input")
    stale = instrument_serve.project(tmp_path, "test/1")
    assert stale["status"] == "STALE-RED"
    assert stale["inputs"][0]["status"] == "FAIL"
    assert any("input digest moved" in error for error in stale["errors"])

    sidecar.write_text("0" * 64, encoding="utf-8")
    custody_red = instrument_serve.project(tmp_path, "test/1")
    assert custody_red["status"] == "CUSTODY-RED"
    assert custody_red["custody"]["status"] == "FAIL"
