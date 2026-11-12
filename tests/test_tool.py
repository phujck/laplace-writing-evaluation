"""Smoke tests for the laplace_shard MCP verb - the thin glue over self_shard.

tool.py is thin dispatch (the engine's convention), but the at-grade runner flags any source
change that resolves to no test as a gap. This closes that gap for ``laplace_shard``: the three
actions dispatch correctly, the empty-query path is defensive, and the soul covenant survives the
verb boundary. The repo root is redirected to a tmp tree (hermetic - no real index/telemetry
side-effects).
"""

from __future__ import annotations

import pytest

from laplace.engine import self_shard, telemetry
from laplace import tool


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    (tmp_path / "src" / "laplace").mkdir(parents=True)
    (tmp_path / "note.md").write_text("# A Note\n\nbody about widgets\n", encoding="utf-8")
    (tmp_path / "soul").mkdir()
    (tmp_path / "soul" / "0001_x.md").write_text(
        "# a secret heading\n\nverbatim soul content\n", encoding="utf-8")
    monkeypatch.setattr(self_shard, "default_repo_root", lambda: tmp_path)
    monkeypatch.setattr(telemetry, "reconstruction", lambda **k: None)
    return tmp_path


def test_verb_name_reconstructs_an_object(tree):
    res = tool.laplace_shard(action="name", query="note", grade=0)
    assert any(m["name"] == "note.md" for m in res["matches"])


def test_verb_name_empty_query_is_defensive(tree):
    res = tool.laplace_shard(action="name", query="")
    assert res["matches"] == []


def test_verb_build_writes_index_and_gate_passes(tree):
    res = tool.laplace_shard(action="build")
    assert res["index"] == "SELF_SHARD_INDEX.md"
    assert res["faithfulness"]["pass"] is True
    assert (tree / "SELF_SHARD_INDEX.md").exists()


def test_verb_verify_seals_soul_at_the_boundary(tree):
    import json

    res = tool.laplace_shard(action="verify")
    rep = res["faithfulness"]
    assert rep["pass"] is True and rep["sealed"] == 1
    # the verb must not leak soul content even on a full verify
    assert "verbatim" not in json.dumps(res).lower()
