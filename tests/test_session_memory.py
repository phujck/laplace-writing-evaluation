import json
from pathlib import Path
import pytest
from laplace.engine import session_memory as memory


def seed(root):
    return memory.apply(root, {"basis": "Explicit fixture policy", "changes": [
        {"key": "session-entry", "kind": "procedure", "text": "Use the current records.", "scope": "fixture"},
        {"key": "law/example", "kind": "law", "text": "Preserve evidence.", "scope": "fixture"},
    ]})


def test_views_never_override_records_and_revision_reaches_readers(tmp_path):
    seed(tmp_path)
    (tmp_path / "STANDING_LAW.md").write_text("invented stale instruction")
    assert memory.law_lines(tmp_path) == ["Preserve evidence."]
    assert memory.view_status(tmp_path)["STANDING_LAW.md"] == "STALE"
    old = memory.resolve(tmp_path)["entries"]["law/example"]["version"]
    memory.apply(tmp_path, {"basis": "Author amendment", "changes": [
        {"key": "law/example", "kind": "law", "text": "Preserve exact evidence.", "scope": "fixture"}]})
    assert memory.law_lines(tmp_path) == ["Preserve exact evidence."]
    assert memory.resolve(tmp_path)["entries"]["law/example"]["previous"] == old
    assert set(memory.view_status(tmp_path).values()) == {"CURRENT"}
    assert (tmp_path / "CLAUDE.md").read_bytes() == (tmp_path / "AGENTS.md").read_bytes()


def test_warm_reads_write_nothing_and_process_only_appended_bytes(tmp_path):
    seed(tmp_path)
    cache = memory._cache_path(tmp_path)
    before = cache.read_bytes(), cache.stat().st_mtime_ns
    state = memory.resolve(tmp_path)
    assert state["read_cost"] == {"history_bytes": (tmp_path / memory.STORE).stat().st_size,
                                  "delta_bytes_read": 0, "index_reused": True}
    addition = (json.dumps({"id": "new-ruling", "kind": "author-instruction", "ruling": "An amended task"}) + "\n").encode()
    with (tmp_path / memory.STORE).open("ab") as stream:
        stream.write(addition)
    state = memory.resolve(tmp_path)
    assert state["status"] == "REVIEW_REQUIRED"
    assert state["read_cost"]["delta_bytes_read"] == len(addition)
    assert (cache.read_bytes(), cache.stat().st_mtime_ns) == before
    memory.refresh_index(tmp_path)
    assert memory.resolve(tmp_path)["read_cost"]["delta_bytes_read"] == 0


def test_same_update_does_not_accumulate_history_or_rewrite_views(tmp_path):
    seed(tmp_path)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir() if p.is_file()}
    assert seed(tmp_path)["changed_records"] == 0
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir() if p.is_file()} == before


def test_source_rewrite_invalidates_index_and_bad_revision_refuses(tmp_path):
    seed(tmp_path)
    path = tmp_path / memory.STORE
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["session_memory"]["changes"][0]["previous"] = "wrong-parent"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    with pytest.raises(ValueError, match="revision conflict"):
        memory.resolve(tmp_path)


def test_imported_source_survives_original_removal_and_patch_is_not_reauthoring(tmp_path):
    seed(tmp_path)
    original = tmp_path / "provider-note.md"
    original.write_text("# Exact note\nWords with café and \"quotes\".\n")
    body = original.read_text()
    handle = memory.digest(body.encode())
    memory.apply(tmp_path, {"basis": "import an existing source", "sources": {handle: {"path": str(original), "content": body}},
        "changes": [{"key": "imported", "kind": "historical", "status": "historical", "text": "source reference", "scope": "history", "source_handle": handle}]})
    original.unlink()
    recovered, _ = memory.get_entry(tmp_path, "source/" + handle[7:])
    assert recovered["text"] == body and recovered["version"] == handle
    memory.apply(tmp_path, {"basis": "amend one field", "changes": [{"key": "law/example", "text": "Preserve recoverable evidence."}]})
    updated, _ = memory.get_entry(tmp_path, "law/example")
    assert updated["scope"] == "fixture" and updated["kind"] == "law"
    assert updated["text"] == "Preserve recoverable evidence."
