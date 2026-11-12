import json

import pytest

from laplace.projects import library as wp
from laplace.native import tools as writing_tools, contracts as writing_contracts


def setup(root):
    status, result = wp.create({"name": "independent-book", "title": "A Working Title",
        "kind": "book", "purpose": "Explain a measured construction.",
        "question": "Which predictions survive reduction?"}, root)
    assert status == 201, result
    return root / result["source"]["root"]


def test_project_title_change_preserves_source_question_and_other_projects(tmp_path):
    source = setup(tmp_path)
    wp.create({"name": "other-book", "title": "Other", "kind": "book"}, tmp_path)
    before_source = source.read_bytes()
    auth = source.parent / "authoring.json"
    before_auth = auth.read_bytes()
    before = wp.metadata("independent-book", tmp_path)
    # An unrelated registry entry changes without invalidating this row guard.
    other = wp.metadata("other-book", tmp_path)
    wp.change_metadata("other-book", {"title": "Other revised", "expected_revision": other["revision"]}, tmp_path)
    result = wp.change_metadata("independent-book", {"title": "The Book", "expected_revision": before["revision"]}, tmp_path)
    assert result["title"] == "The Book" and result["project"] == "independent-book"
    assert wp.metadata("other-book", tmp_path)["title"] == "Other revised"
    assert source.read_bytes() == before_source and auth.read_bytes() == before_auth
    assert result["owned_changes"]["files"][0]["observed_after_sha256"] == result["owned_changes"]["files"][0]["after_sha256"]
    with pytest.raises(ValueError, match="revision conflict"):
        wp.change_metadata("independent-book", {"title": "Stale", "expected_revision": before["revision"]}, tmp_path)


def test_metadata_noop_does_not_write_and_routes_share_the_owner(tmp_path):
    setup(tmp_path)
    code, _, body = wp.handle("/projects/metadata", {"project": ["independent-book"]}, "GET", b"", tmp_path)
    record = json.loads(body)
    assert code == 200
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = wp.change_metadata("independent-book", {"title": record["title"], "expected_revision": record["revision"]}, tmp_path)
    assert result["unchanged"] is True
    assert {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    code, _, body = wp.handle("/projects/metadata", {}, "POST", json.dumps({
        "project": "independent-book", "title": "New display title", "expected_revision": record["revision"]}).encode(), tmp_path)
    assert code == 200 and json.loads(body)["title"] == "New display title"
    assert next(p for p in wp._library(tmp_path)["projects"] if p["name"] == "independent-book")["title"] == "New display title"


def test_new_project_title_is_not_its_research_question(tmp_path):
    status, result = wp.create({"name": "untitled-question", "title": "A Title", "kind": "book"}, tmp_path)
    assert status == 201
    from laplace.pipeline import authoring
    auth = authoring.load("untitled-question", tmp_path)
    assert auth["framing"]["question"] == ""
    assert wp.metadata("untitled-question", tmp_path)["title"] == "A Title"


def test_native_metadata_contract_keeps_title_question_and_actor_distinct(tmp_path):
    source=setup(tmp_path);before_source=source.read_bytes()
    current=writing_tools.execute(tmp_path,"independent-book","work","project_metadata",{})
    contract=writing_contracts.exact_contract("project_metadata_change",permitted=True)
    assert contract["input"]["required"]==["title","expected_revision"]
    changed=writing_tools.execute(tmp_path,"independent-book","work","project_metadata_change",{
        "title":"Native Display Title","expected_revision":current["revision"],
        "reason":"Author-approved library title."},turn_id=None)
    assert changed["title"]=="Native Display Title" and source.read_bytes()==before_source
    rows=[json.loads(line) for line in (tmp_path/"contract/talk.jsonl").read_text().splitlines()]
    record=next(row for row in reversed(rows) if row.get("record")=="project-metadata-change")
    assert record["by"]=="eigen:session"
    from laplace.writing import mutation_attribution
    snapshot=mutation_attribution._mutation_file_snapshot(
        tmp_path,"independent-book","project_metadata_change",{})
    assert "registry_projects.json" in snapshot


def test_native_metadata_receipt_has_exact_mutation_attribution(tmp_path):
    setup(tmp_path)
    from laplace.writing import records as writing_records
    writing_records.bank(tmp_path,{"record":"writing-session","id":"WS-meta",
        "project":"independent-book","provider":"codex","model":"m","effort":"low"})
    writing_records.bank(tmp_path,{"record":"writing-turn","id":"WT-meta",
        "session_id":"WS-meta","project":"independent-book"})
    current=writing_tools.execute(tmp_path,"independent-book","work","project_metadata",{},turn_id="WT-meta")
    changed=writing_tools.execute(tmp_path,"independent-book","work","project_metadata_change",{
        "title":"Exact metadata receipt","expected_revision":current["revision"]},turn_id="WT-meta")
    assert changed["action_receipt"]["mutation_attribution"]["exact"] is True
