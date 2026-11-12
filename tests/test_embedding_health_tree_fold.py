from __future__ import annotations

import builtins
import io
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from laplace.engine import conceptric
from laplace.representation import embedding_health as health
from laplace.engine.front_semantic_junction import embedding_health_side_ref, _fold_projection
from laplace.engine.front_carrier import semantic_memory


@pytest.fixture
def deposited_repo(tmp_path: Path):
    def git(*args: str) -> bytes:
        return subprocess.run(
            ["git", "--no-optional-locks", "-c", "diff.autoRefreshIndex=false", *args],
            cwd=tmp_path, check=True, capture_output=True,
        ).stdout

    git("init")
    source = tmp_path / "tracked source.py"
    source.write_text("source\n")
    git("add", source.name)
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "-m", "source")
    graded = tmp_path / ".self_graded.json"
    graded.write_text(json.dumps({"root": {
        "id": "root", "kind": "concept", "grade": 1, "parent": None,
        "members": [], "keywords": [], "leaf": False,
    }}))
    # The real router adds two MIND nodes to the one banked concept. The deposit
    # receipt distinguishes that banked count from the three embedding entries.
    (tmp_path / ".self_embeddings.json").write_text('{"nodes": {}}')
    (tmp_path / ".meaning_tree.json").write_text('{"clusters": {"root": {}}}')
    receipt = {
        "ts": datetime.now(timezone.utc).isoformat(), "mode": "incremental",
        "total": 0.1, "nodes": 1, "clusters": 1,
        "embedding_counts": {"embedded": 3, "total": 3},
        "device": {"embedding_backend": "fixture"},
    }
    timing = tmp_path / ".reembed_timing.jsonl"
    timing.write_text(json.dumps(receipt) + "\n")
    return tmp_path, source, timing, receipt


def test_tree_fold_current_touch_stale_corrupt_receipt_unknown(deposited_repo) -> None:
    root, source, timing, receipt = deposited_repo
    network = conceptric.load_network(root)
    assert len(network["nodes"]) == 3
    index_before = (root / ".git/index").read_bytes()
    current = health.read_health(root)
    tree = current["tree_fold"]
    assert current["status"] == current["ui_status"] == tree["status"] == "CURRENT"
    assert tree["nodes"] == len(network["nodes"])
    assert tree["clusters"] == sum(n.get("kind") == "concept" for n in network["nodes"].values())
    assert tree["stale_paths"] == 0
    for row in tree["files"]:
        stat = (root / row["path"]).stat()
        assert (row["size"], row["mtime_ns"], row["inode"]) == (stat.st_size, stat.st_mtime_ns, stat.st_ino)
        assert "sha256" not in row
    assert embedding_health_side_ref(current)["current_proof"] is True
    assert embedding_health_side_ref(current)["status"] == "CURRENT"
    assert _fold_projection(current)[0]["status"] == "CURRENT"
    front = semantic_memory(current)
    assert front["health_status"] == "CURRENT"
    assert front["coverage"]["node"]["count"] == len(network["nodes"])
    assert front["coverage"]["cluster"]["count"] == 1
    assert front["latest_receipt"] == tree["latest_receipt"]
    assert "FALSE_CURRENTNESS_REFUSED" not in json.dumps(front)
    deposited = datetime.fromisoformat(receipt["ts"]).timestamp()
    os.utime(source, (deposited + 1, deposited + 1))
    assert source.read_text() == "source\n"
    stale = health.read_health(root)
    assert stale["status"] == stale["ui_status"] == stale["tree_fold"]["status"] == "STALE"
    assert stale["tree_fold"]["stale_paths"] == 1
    assert stale["tree_fold"]["nodes"] == len(conceptric.load_network(root)["nodes"])
    assert embedding_health_side_ref(stale)["status"] == "UPDATE-DUE"
    assert (root / ".git/index").read_bytes() == index_before
    timing.write_text('{"ts":')
    unknown = health.read_health(root)
    assert unknown["status"] == unknown["ui_status"] == unknown["tree_fold"]["status"] == "UNKNOWN"
    assert embedding_health_side_ref(unknown)["status"] == "UNKNOWN"


def test_health_contract_keys_and_alias(tmp_path):
    result = health.read_health(tmp_path)
    assert {"fold", "tree_fold", "side_ref_fold", "status", "ui_status"} <= result.keys()
    assert result["fold"] is result["tree_fold"]
    assert result["side_ref_fold"] is not result["fold"]


def test_health_never_opens_tree_artifacts(deposited_repo, monkeypatch):
    root, *_ = deposited_repo
    opened = []
    real_open = io.open

    def recording_open(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(io, "open", recording_open)
    monkeypatch.setattr(builtins, "open", recording_open)
    result = health.read_health(root)
    assert result["status"] == "CURRENT"
    assert opened
    assert not [p for p in opened if Path(p).name in health.TREE_FOLD_PATHS]


def test_legacy_receipt_does_not_invent_cluster_count(deposited_repo):
    root, _, timing, receipt = deposited_repo
    del receipt["clusters"]
    timing.write_text(json.dumps(receipt) + "\n")
    tree = health.read_health(root)["tree_fold"]
    assert tree["clusters"] is None
    assert tree["cluster_count_issue"]["code"] == "DEPOSIT-CLUSTER-COUNT-ABSENT"


@pytest.mark.parametrize("bad", ["null", "[]", '{"nodes": true}', '{"ts":'])
def test_invalid_latest_receipt_never_falls_back(deposited_repo, bad):
    root, _, timing, _ = deposited_repo
    with timing.open("a") as stream:
        stream.write(bad + "\n")
    assert health.read_health(root)["status"] == "UNKNOWN"
