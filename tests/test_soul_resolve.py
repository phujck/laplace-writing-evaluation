"""Tests for soul_resolve - the sealed semantic upward operator (the inter-grade scale-link).

No real soul content: a synthetic tmp tree with two decoy 'people' folders. The contracts under test:
the grade-below members are gathered by index PATH (no content read), the committed handle is
content-free BY CONSTRUCTION (a secret planted in the chat-derived resolution never reaches it), the
rich local node keeps the full resolution, a different-name folder is NOT merged (the negative
control), and the faithfulness gate samples rather than sweeping."""

from __future__ import annotations

import json
from pathlib import Path

from laplace.engine import soul_resolve, soul_shard


def _raw(tmp_path: Path) -> None:
    raw = tmp_path / "archive" / "soul_dump" / "raw" / "chat_logs"
    (raw / "Foo_Bar").mkdir(parents=True)
    (raw / "Baz_Qux").mkdir(parents=True)  # the negative control - a different person
    (raw / "Foo_Bar" / "WhatsApp Chat with Foo Bar.txt").write_text(
        "\n".join(f"line {i} foo bar chat" for i in range(300)), encoding="utf-8")
    (raw / "Baz_Qux" / "WhatsApp Chat with Baz Qux.txt").write_text(
        "\n".join(f"line {i} baz qux chat" for i in range(300)), encoding="utf-8")


def _shard(tmp_path: Path):
    _raw(tmp_path)
    shards = soul_shard.shard_tree(tmp_path)
    soul_shard.write_local_index(tmp_path, shards)
    return shards


def _entity() -> dict:
    return {"key": "foo-bar", "display_name": "Foo Bar", "aliases": ["Foo Bar", "F. Bar"],
            "public_refs": [{"ref": "life_corpus/people/foo-bar.md", "kind": "person"}],
            "public_join": [{"arxiv": "1234.5678", "title": "A Shared Paper"}],
            "negative_controls": ["Baz Qux is a different person"]}


def test_gather_finds_sealed_members_by_path(tmp_path):
    _shard(tmp_path)
    node = soul_resolve.gather(tmp_path, _entity())
    assert node["counts"]["sealed_chunks"] > 0
    assert all("Foo_Bar" in m["source"] for m in node["members"]["sealed"])
    # members carry metadata only - never a content field
    assert all(set(m) <= {"id", "source", "label", "n_chars", "category"}
               for m in node["members"]["sealed"])


def test_negative_control_not_merged(tmp_path):
    _shard(tmp_path)
    node = soul_resolve.gather(tmp_path, _entity())
    assert not any("Baz_Qux" in m["source"] for m in node["members"]["sealed"])


def test_handle_is_content_free_by_construction(tmp_path):
    _shard(tmp_path)
    node = soul_resolve.gather(tmp_path, _entity())
    secret = "SECRET_CHAT_DERIVED_PROFILE_DO_NOT_LEAK"
    soul_resolve.attach(
        node,
        resolution={"same_person": True, "confidence": 0.9,
                    "identity_profile": secret, "register": secret, "evidence": [secret]},
        adjudication={"verdict": "faithful", "gap": secret})
    handle = soul_resolve.write_handle(tmp_path, node)
    text = handle.read_text(encoding="utf-8")
    assert secret not in text                       # no chat-derived content leaks to the committed handle
    assert "Foo Bar" in text                        # identity (the cross-corpus key) is preserved
    assert "true" in text.lower()                   # the verdict survives
    assert "1234.5678" in text                      # public join evidence survives
    # not one sealed member id reaches the handle (only the count does)
    assert not any(m["id"] in text for m in node["members"]["sealed"])


def test_local_node_keeps_full_resolution(tmp_path):
    _shard(tmp_path)
    node = soul_resolve.gather(tmp_path, _entity())
    secret = "rich-local-only"
    soul_resolve.attach(node, resolution={"same_person": True, "identity_profile": secret})
    local = soul_resolve.write_local(tmp_path, node)
    assert secret in local.read_text(encoding="utf-8")          # the rich layer keeps it
    assert "archive/soul_dump" in str(local).replace("\\", "/")  # and it lands in the gitignored zone


def test_local_gate_samples_and_passes(tmp_path):
    _shard(tmp_path)
    node = soul_resolve.gather(tmp_path, _entity())
    gate = soul_resolve.local_faithfulness(tmp_path, node, k=3)
    assert gate["pass"] is True
    assert gate["sampled"] <= 3                       # O(k), never O(N^2)
    assert gate["recovered"] == gate["sampled"]


def test_main_round_trips_a_spec(tmp_path, capsys, monkeypatch):
    _shard(tmp_path)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(_entity()), encoding="utf-8")
    monkeypatch.setattr(soul_resolve, "default_repo_root", lambda: tmp_path)
    rc = soul_resolve.main([str(spec)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["counts"]["sealed_chunks"] > 0 and out["gate"]["pass"] is True
    assert (tmp_path / "soul_corpus" / "sealed" / "people" / "foo-bar.md").exists()
