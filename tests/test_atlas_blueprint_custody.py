from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "atlas_blueprint_custody", ROOT / "scripts" / "atlas_blueprint_custody.py")
assert SPEC and SPEC.loader
custody = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(custody)


def test_first_corpus_contains_both_founding_interface_designs():
    manifest, records = custody.build(ROOT)
    sources = {row["source"] for row in records}
    assert "DESIGN_2026-08-24_the-conjugate-serve.md" in sources
    assert "DESIGN_2026-08-24_the-front-door-is-the-session.md" in sources
    assert manifest["corpus_id"] == "atlas-blueprint"
    assert manifest["tier"] == "mechanical-custody"


def test_custody_ids_are_unique_and_semantic_judgement_is_not_forged():
    manifest, records = custody.build(ROOT)
    logical_ids = [row["logical_id"] for row in records]
    assert len(logical_ids) == len(set(logical_ids))
    assert manifest["semantic_edge_status"].startswith("NOT-MINTED")
    assert len(manifest["typed_stores"]) == 11


def test_fabric_chain_and_typed_rows_are_part_of_custody(monkeypatch):
    # The suite deliberately redirects Atlas's external state root.  Plant one
    # verified-shape event here; the script's write/check invocation measures the
    # real external chain outside pytest.
    planted = custody._record(
        "fabric-event", "atlas-blueprint:fabric:event:test",
        "atlas-fabric:event:1", b'{"event":"test"}', sequence=1,
        event_id="event:test", record_digest="sha256:test")
    monkeypatch.setattr(custody, "fabric_records", lambda: ([planted], []))
    manifest, records = custody.build(ROOT)
    kinds = {row["kind"] for row in records}
    assert {"fabric-event", "typed-row", "authored-design", "evidence-grain", "commit"} <= kinds
    assert manifest["counts"]["fabric-event"] > 0
    assert manifest["counts"]["typed-row"] > 0
