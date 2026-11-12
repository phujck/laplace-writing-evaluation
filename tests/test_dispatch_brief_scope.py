"""Campaign context is opt-in; the generic writing harness must not inherit Atlas."""
import importlib.util
import json
from pathlib import Path

import pytest


def module():
    path = Path(__file__).parents[1] / "scripts/distil.py"
    spec = importlib.util.spec_from_file_location("distil_scope_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_generic_brief_has_no_campaign_attachment(monkeypatch):
    mod = module()
    monkeypatch.setattr(mod, "_run", lambda _: json.dumps({"content_status": "COMPLETE"}))
    # Missing historical files cannot affect an unrelated worker.
    monkeypatch.setattr(mod, "CHARTER", "/absent/atlas/charter.json")
    monkeypatch.setattr(mod, "REGISTER", "/absent/atlas/machinery.jsonl")
    plan = {"wave": "writing", "node": "a", "goal": "write coherently",
            "agents": [{"label": "writer", "brief": "Current task"}]}
    text = mod.brief_text(plan, "writer", "build")
    assert "ENGINE WAKE" in text
    assert "Current task" in text
    assert "CHARTER" not in text and "CAMPAIGN CONTEXT" not in text
    assert "MACHINERY INDEX" not in text


def test_explicit_campaign_context_is_selective(tmp_path, monkeypatch):
    mod = module()
    monkeypatch.setattr(mod, "_run", lambda _: json.dumps({"content_status": "COMPLETE"}))
    charter = tmp_path / "charter.json"
    charter.write_text(json.dumps({"goal": "relevant goal", "unrelated": "omit this"}))
    plan = {"wave": "campaign", "node": "a", "goal": "g", "charter": str(charter),
            "charter_keys": ["goal"], "agents": [{"label": "worker"}]}
    text = mod.brief_text(plan, "worker", "build")
    assert "relevant goal" in text and "omit this" not in text


def reconstructed_node(monkeypatch, payload):
    mod = module()
    monkeypatch.setattr(mod, "_run", lambda command:
                        json.dumps(payload) if command[0] == "scripts/reconstruct_node.py"
                        else "Worker wake")
    plan = {"wave": "current", "node": "owner.md", "goal": "Continue owned work",
            "agents": [{"label": "worker"}]}
    brief = mod.brief_text(plan, "worker", "build")
    section = brief.split("\n=== 2.", 1)[1].split("\n", 1)[1].split("\n=== ", 1)[0]
    return json.loads(section)


@pytest.mark.parametrize("body,status,following", [
    ("Use the existing owner; read its exact current basis.", "COMPLETE", None),
    ("First observed slice", "TRUNCATED", 20),
    ("", "COMPLETE", None),
    (None, "BUDGET", 0),
])
def test_brief_delivers_bounded_node_without_expanding_or_duplicating_it(
        monkeypatch, body, status, following):
    observed_bytes = len((body or "").encode())
    source_bytes = observed_bytes if status == "COMPLETE" else 80
    payload = {"schema_version": "laplace.typed-descent/1", "kind": "repository-file",
               "reference": "owner.md", "content": body, "content_status": status,
               "content_contract_schema": "laplace.bounded-content/1",
               "content_encoding": "utf-8", "content_offset": 0,
               "content_next_offset": following, "content_bytes": source_bytes,
               "content_budget": 0 if status == "BUDGET" else max(20, observed_bytes),
               "content_omitted_after": source_bytes - observed_bytes,
               "content_handle": "sha256:observed-source",
               "provenance": {"resolution_mode": "exact-repository-file"},
               "value": {"duplicated_full_history": "must not be delivered"}}
    observed = reconstructed_node(monkeypatch, payload)
    assert observed["content"] == body
    assert "value" not in observed
    for key in ("content_status", "content_contract_schema", "content_encoding",
                "content_offset", "content_next_offset", "content_bytes",
                "content_budget", "content_omitted_after", "content_handle", "provenance"):
        assert observed[key] == payload[key]


def test_brief_preserves_legacy_material_only_when_content_is_absent(monkeypatch):
    observed = reconstructed_node(monkeypatch, {
        "kind": "legacy-node", "reference": "owner", "value": {"goal": "Read this"},
        "content_status": "COMPLETE"})
    assert observed["value"] == {"goal": "Read this"}
    assert "content" not in observed
