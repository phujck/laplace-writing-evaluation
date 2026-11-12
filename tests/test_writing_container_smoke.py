"""The container smoke uses exact row/body owners, not whole-JSON string bans."""
from laplace.core import bodies as core_bodies
import copy
import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from laplace.web import authoring as authoring_surface
from laplace.writing import provider as writing_provider
from laplace.writing import records as writing_records
from laplace.representation import writing_bodies as bodies
from laplace.core.bodies import REFERENCE_SCHEMA as PUBLIC_BODY_SCHEMA
from laplace.core import checkout

spec = importlib.util.spec_from_file_location("writing_container_smoke",
    Path(__file__).parents[1] / "deploy/writing/smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def fixture(root):
    home = root / "project"; home.mkdir()
    (root / "contract").mkdir()
    (root / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "p", "kind": "project", "project_dir": "project",
        "manifest": {"writing": {"kind": "general"}}}]}))
    writing_records.bank(root, {"record": "writing-session", "id": "WS", "project": "p"})
    writing_records.bank(root, {"record": "writing-turn", "id": "WT", "project": "p",
        "session_id": "WS", "mode": "work"})
    text = "Literal laplace.writing-public-body-ref/1 and storage_errors are prose. α\n" * 40
    def reference(value):
        raw = core_bodies.encode(value)
        return {"schema_version": PUBLIC_BODY_SCHEMA, "content_handle": bodies.store(root).put(raw),
                "store": "contract/writing_bodies", "bytes": len(raw), "encoding": "application/json"}
    facts = writing_provider._UsageFacts("codex", root, "WT", "model")
    facts.bind("native", fresh=True); facts.bind("native", "native-turn")
    facts.codex({"last": {"inputTokens": 5, "cachedInputTokens": 1, "outputTokens": 3, "totalTokens": 8}})
    metadata = facts.snapshot()
    row = {"record": "writing-reply", "id": "WR", "project": "p", "session_id": "WS",
           "turn_id": "WT", "status": "completed", "text": reference(text),
           "usage_facts": reference(metadata)}
    ledger = root / "contract/talk.jsonl"
    with ledger.open("a") as stream: stream.write(json.dumps(row) + "\n")
    return row, text, metadata


def owner_get(root, monkeypatch):
    monkeypatch.setattr(checkout, "repo_root", lambda: root)
    def get(path):
        url = urlsplit(path)
        status, _, data = authoring_surface.handle(url.path, parse_qs(url.query), "GET", b"")
        assert status == 200, (status, data)
        return json.loads(data)
    return get


def replace_row(root, row):
    ledger = root / "contract/talk.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    ledger.write_text("".join(json.dumps(row if item.get("id") == row["id"] else item) + "\n"
                              for item in rows))


def test_actual_selected_row_accepts_lazy_metadata_and_literal_prose(tmp_path, monkeypatch):
    row, text, metadata = fixture(tmp_path)
    nested = metadata["observations"][0]["raw_observation_ref"]["content_handle"]
    reads = []; read = bodies.read_bytes
    monkeypatch.setattr(bodies, "read_bytes", lambda value, root:
                        (reads.append(value["content_handle"]) or read(value, root)))
    get = owner_get(tmp_path, monkeypatch)
    def with_empty_errors(path):
        return {**get(path), "storage_errors": []}
    result = smoke.verify_history_custody(tmp_path, with_empty_errors, {"p"})
    assert result["history_record"] == "WR" and result["history_turn"] == "WT"
    assert set(result["history_body_fields"]) == {"text", "usage_facts"}
    assert reads and set(reads) == {row["text"]["content_handle"], row["usage_facts"]["content_handle"]}
    assert nested not in reads  # Body owner preserves metadata observation handles lazily.
    assert get("/authoring/history?project=p&view=record&id=activity:journal:WR")["record"]["text"] == text


@pytest.mark.parametrize("failure", ["malformed", "unsupported", "missing", "corrupt", "invalid-json"])
def test_selected_required_reference_failure_refuses(tmp_path, monkeypatch, failure):
    row, _, _ = fixture(tmp_path); row = copy.deepcopy(row); ref = row["text"]
    path = bodies.store(tmp_path).key_path(ref["content_handle"])
    if failure == "malformed": ref["bytes"] += 1
    elif failure == "unsupported": ref["schema_version"] = "laplace.writing-public-body-ref/99"
    elif failure == "missing": path.unlink()
    elif failure == "corrupt": path.write_bytes(b"corrupt fixture")
    else:
        raw = b"not-json"; ref["content_handle"] = bodies.store(tmp_path).put(raw); ref["bytes"] = len(raw)
    replace_row(tmp_path, row)
    with pytest.raises(ValueError, match="unavailable, corrupt or unsupported"):
        smoke.verify_history_custody(tmp_path, owner_get(tmp_path, monkeypatch), {"p"})


@pytest.mark.parametrize("change", ["unresolved", "wrong-text", "wrong-project", "custody-errors"])
def test_remote_selected_body_or_error_cannot_be_blessed(tmp_path, monkeypatch, change):
    row, _, _ = fixture(tmp_path); actual = owner_get(tmp_path, monkeypatch)
    def wrong(path):
        result = copy.deepcopy(actual(path))
        if change == "unresolved": result["record"]["text"] = row["text"]
        elif change == "wrong-text": result["record"]["text"] = "different served bytes"
        elif change == "wrong-project": result["project"] = "other"
        else: result["storage_errors"] = [{"field": "text", "error": "missing selected body"}]
        return result
    with pytest.raises(RuntimeError, match="differs|custody errors"):
        smoke.verify_history_custody(tmp_path, wrong, {"p"})


def test_other_project_body_is_not_hydrated(tmp_path, monkeypatch):
    row, _, _ = fixture(tmp_path)
    ledger = tmp_path / "contract/talk.jsonl"; lines = ledger.read_text().splitlines()
    other = {**row, "id": "WR-other", "project": "other", "text": {**row["text"],
        "content_handle": "sha256:" + "0" * 64}}
    lines.insert(0, json.dumps(other)); ledger.write_text("\n".join(lines) + "\n")
    assert smoke.verify_history_custody(tmp_path, owner_get(tmp_path, monkeypatch), {"p"})["history_record"] == "WR"
