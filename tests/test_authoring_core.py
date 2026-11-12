"""Authoring contexts are durable dependency receipts, not section membership tags."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.pipeline import authoring


def _source(project: str, repo_root=None):
    root = Path(repo_root)
    return {
        "project": project, "root": "manuscript/main.tex", "manuscript_dir": "manuscript",
        "edition": None, "status": "resolved", "revision": "root-only",
        "candidates": [], "foreign": False, "read_only": False, "diagnostics": [],
    }


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "manuscript"
    directory.mkdir()
    (directory / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n\\input{sec_one}\n\\input{sec_two}\n\\input{sec_three}\n\\end{document}\n",
        encoding="utf-8")
    (directory / "sec_one.tex").write_text(
        "\\section{Need}\nThe obstacle motivates the construction.\\cite{need-source}\n",
        encoding="utf-8")
    (directory / "sec_two.tex").write_text(
        "\\section{Consequence}\nThe construction changes what the reader can do.\\cite{result-source}\n",
        encoding="utf-8")
    (directory / "sec_three.tex").write_text("\\section{Return}\nThe consequence raises a final question.\n", encoding="utf-8")
    monkeypatch.setattr(authoring, "_source", _source)


def test_context_has_full_scope_boundaries_and_consumed_corrections(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    saved = authoring.save("fixture", {
        "base_revision": 0, "argument": "The problem creates a need; the construction resolves it.",
        "framing": {"purpose": "explain", "audience": "reader", "question": "why this construction?"},
        "section_ids": ["sec_one"],
    }, repo_root=tmp_path)
    correction = authoring.bank_correction("fixture", {
        "base_revision": saved["revision"], "text": "State the limitation before the construction.",
        "kind": "style", "scope": "passage", "anchor": {"file": "sec_one.tex"},
    }, repo_root=tmp_path)
    context = authoring.build_context("fixture", {"section_ids": ["sec_one"]}, repo_root=tmp_path)

    assert "NUMBERED SOURCE ADDRESS GUIDE [manuscript/sec_one.tex]" in context["prompt"]
    assert "The obstacle motivates the construction." in context["prompt"]
    assert "BOUNDARY PROSE [manuscript/sec_two.tex]" in context["prompt"]
    assert correction["correction"]["id"] in context["consumed"]["corrections"]
    assert context["consumed"]["source_ids"] == ["need-source"]
    assert context["dependencies"]["argument_revision"] == 1


def test_current_receipt_inspection_does_not_rebuild_other_conversations(tmp_path, monkeypatch):
    from laplace.manuscript import project_structure
    from laplace.native import tools as writing_tools
    _fixture(tmp_path, monkeypatch)
    calls = {"structure": [], "references": [], "glossary": []}
    def structure(project, selection, root):
        calls["structure"].append(selection)
        return {"scope": selection, "science": "unchanged"}
    def references(project, keys, root):
        calls["references"].append(tuple(keys))
        return []
    def glossary(project, root):
        calls["glossary"].append(project)
        return []
    monkeypatch.setattr(project_structure, "context", structure)
    monkeypatch.setattr(authoring, "_reference_context", references)
    monkeypatch.setattr(authoring, "_glossary", glossary)
    selection = {"files": ["manuscript/sec_one.tex"]}
    first = authoring.build_context("fixture", selection, repo_root=tmp_path)
    authoring.build_context("fixture", selection, repo_root=tmp_path)
    authoring.build_context("fixture", {"files": ["manuscript/sec_two.tex"]}, repo_root=tmp_path)
    for values in calls.values(): values.clear()

    # A fresh source read has no reason to audit any old conversation receipt.
    read = writing_tools.execute(tmp_path, "fixture", "work", "source", selection)
    assert read["staleness_scope"]["receipts_checked"] == 0
    assert all(not values for values in calls.values())
    assert "The obstacle" in read["sources"][0]["text"]

    (tmp_path / "manuscript/sec_one.tex").write_text("\\section{Need}\nChanged scientific content.\n")
    scoped = authoring.inspect("fixture", selection, repo_root=tmp_path,
                               context_id=first["context_id"])
    assert [row["context_id"] for row in scoped["stale"]] == [first["context_id"]]
    assert any(reason.startswith("source-revision-changed") for reason in scoped["stale"][0]["reasons"])
    assert len(calls["structure"]) == len(calls["references"]) == len(calls["glossary"]) == 1

    # Full historical inspection remains available and shares identical reads.
    for values in calls.values(): values.clear()
    full = authoring.inspect("fixture", selection, repo_root=tmp_path)
    assert next(row for row in full["stale"] if row["context_id"] == first["context_id"]) == scoped["stale"][0]
    assert full["staleness_scope"] == "all"
    assert len(calls["glossary"]) == 1
    assert len(calls["structure"]) == len(calls["references"]) == 2

    for values in calls.values(): values.clear()
    authoring.build_context("fixture", selection, repo_root=tmp_path)
    assert len(calls["structure"]) == len(calls["references"]) == len(calls["glossary"]) == 1


def test_new_contexts_content_address_repeated_bodies_and_legacy_reads_stay_full(
        tmp_path, monkeypatch):
    from laplace.manuscript import project_structure
    _fixture(tmp_path, monkeypatch)
    structure = {"sections": [{"id": "sec-one", "summary": "x" * 1000}],
                 "revision": "sha256:fixture"}
    monkeypatch.setattr(project_structure, "context",
                        lambda project, selection, root: structure)

    first = authoring.build_context("fixture", {"files": ["manuscript/sec_one.tex"]},
                                    repo_root=tmp_path)
    path = tmp_path / "manuscript" / "authoring.json"
    stored_first = json.loads(path.read_text())
    first_row = next(row for row in stored_first["contexts"] if row["id"] == first["context_id"])
    reference = first_row["structure"]["$laplace_context_blob"]
    assert stored_first["context_blobs"][reference] == structure
    bytes_after_first=path.read_bytes()

    second = authoring.build_context("fixture", {"files": ["manuscript/sec_one.tex"]},
                                     repo_root=tmp_path)
    stored_second = json.loads(path.read_text())
    second_row = next(row for row in stored_second["contexts"] if row["id"] == second["context_id"])
    assert second["context_reused"] is True and second["context_id"]==first["context_id"]
    assert second_row["structure"] == {"$laplace_context_blob": reference}
    assert stored_second["contexts"][0] == first_row
    assert len(stored_second["contexts"])==1
    assert path.read_bytes()==bytes_after_first
    assert sum(value == structure for value in stored_second["context_blobs"].values()) == 1

    loaded = authoring.load("fixture", repo_root=tmp_path)
    assert [row["structure"] for row in loaded["contexts"]] == [structure]

    corrupted = json.loads(path.read_text())
    corrupted["context_blobs"][reference] = {"wrong": "content"}
    path.write_text(json.dumps(corrupted), encoding="utf-8")
    unavailable = authoring.load("fixture", repo_root=tmp_path)["contexts"][0]
    assert unavailable["structure"] == {"$laplace_context_blob": reference}
    assert unavailable["storage"] == {"status": "MISSING", "missing_blobs": [{
        "field": "structure", "blob": reference,
        "reason": "content identity mismatch"}]}
    path.write_text(json.dumps(stored_second), encoding="utf-8")

    # A legacy inline receipt is read as-is and survives a later unrelated save
    # without being silently migrated or discarded.
    legacy = {"id": "CTX-legacy", "structure": {"legacy": "y" * 200}}
    raw = json.loads(path.read_text()); raw["contexts"].append(legacy)
    path.write_text(json.dumps(raw), encoding="utf-8")
    current = authoring.load("fixture", repo_root=tmp_path)
    authoring.save("fixture", {"base_revision": current["revision"],
                                "argument": "Unrelated framing update."}, repo_root=tmp_path)
    rewritten = json.loads(path.read_text())
    assert next(row for row in rewritten["contexts"] if row["id"] == "CTX-legacy") == legacy


def test_argument_source_and_new_correction_propagate_to_context_staleness(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    saved = authoring.save("fixture", {"base_revision": 0, "argument": "Initial argument", "section_ids": ["sec_one"]}, repo_root=tmp_path)
    context = authoring.build_context("fixture", repo_root=tmp_path)
    authoring.save("fixture", {"base_revision": saved["revision"], "argument": "Reframed argument"}, repo_root=tmp_path)
    inspected = authoring.inspect("fixture", repo_root=tmp_path)
    assert any("argument-or-framing-changed" in row["reasons"] for row in inspected["stale"])

    current = authoring.load("fixture", repo_root=tmp_path)
    authoring.bank_correction("fixture", {
        "base_revision": current["revision"], "text": "Do not overstate the result.", "kind": "factual",
        "scope": "project", "anchor": {},
    }, repo_root=tmp_path)
    inspected = authoring.inspect("fixture", repo_root=tmp_path)
    assert any(any(reason.startswith("correction-unconsumed:") for reason in row["reasons"])
               for row in inspected["stale"])

    (tmp_path / "manuscript" / "sec_one.tex").write_text("Changed source evidence.", encoding="utf-8")
    inspected = authoring.inspect("fixture", repo_root=tmp_path)
    row = next(item for item in inspected["stale"] if item["context_id"] == context["context_id"])
    assert any(reason.startswith("source-revision-changed:") for reason in row["reasons"])


def test_agent_project_progress_is_history_while_author_and_anchored_review_constrain_context(
        tmp_path,monkeypatch):
    _fixture(tmp_path,monkeypatch)
    selection={'files':['manuscript/sec_one.tex'],'line_start':1,'line_end':2}
    initial=authoring.build_context('fixture',selection,repo_root=tmp_path)
    progress=authoring.bank_correction('fixture',{'text':'Progress handoff; acquisition remains pending.',
        'kind':'factual','scope':'project','by':'eigen:session'},repo_root=tmp_path)['correction']
    assert progress['context_role']=='agent-history'
    inspected=authoring.inspect('fixture',selection,repo_root=tmp_path,context_id=initial['context_id'])
    assert not any(reason.startswith('correction-unconsumed:') for row in inspected['stale']
                   for reason in row['reasons'])
    fresh=authoring.build_context('fixture',selection,repo_root=tmp_path)
    assert progress['id'] not in fresh['consumed']['corrections']
    assert progress['text'] not in fresh['prompt']
    assert authoring.history('fixture',{'id':progress['id']},repo_root=tmp_path)['item']['text']==progress['text']

    human=authoring.bank_correction('fixture',{'text':'Keep the author qualification.',
        'kind':'factual','scope':'project','by':'author'},repo_root=tmp_path)['correction']
    review=authoring.bank_correction('fixture',{'text':'Check the claim at this passage.',
        'kind':'factual','scope':'passage','anchor':{'file':'manuscript/sec_one.tex'},
        'by':'eigen:review'},repo_root=tmp_path)['correction']
    assert human['context_role']=='author-instruction' and review['context_role']=='anchored-review'
    stale=authoring.inspect('fixture',selection,repo_root=tmp_path,context_id=fresh['context_id'])['stale'][0]
    assert {human['id'],review['id']} <= {reason.partition(':')[2] for reason in stale['reasons']
                                         if reason.startswith('correction-unconsumed:')}


def test_reply_links_history_without_superseding_parent_and_superseded_parent_can_reopen(
        tmp_path,monkeypatch):
    _fixture(tmp_path,monkeypatch)
    parent=authoring.bank_correction('fixture',{'text':'Original six-point author review.',
        'kind':'request','scope':'project','by':'author'},repo_root=tmp_path)['correction']
    reply=authoring.bank_correction('fixture',{'text':'Progress reply with a source URL.',
        'kind':'note','scope':'project','by':'author','reply_to':parent['id']},repo_root=tmp_path)['correction']
    state=authoring.load('fixture',repo_root=tmp_path)
    indexed={row['id']:row for row in state['corrections']}
    assert indexed[parent['id']]['status']=='open'
    assert reply['reply_to']==parent['id'] and reply['context_role']=='author-instruction'
    assert reply['scope']==parent['scope'] and reply['anchor']==parent['anchor']
    assert 'supersedes' not in reply
    context=authoring.build_context('fixture',repo_root=tmp_path)
    assert parent['id'] in context['consumed']['corrections']
    assert reply['id'] in context['consumed']['corrections']

    agent_reply=authoring.bank_correction('fixture',{'text':'Agent progress only.',
        'kind':'note','scope':'passage','by':'eigen:session','reply_to':parent['id']},repo_root=tmp_path)['correction']
    assert agent_reply['scope']=='project' and agent_reply['context_role']=='agent-history'
    assert agent_reply['id'] not in authoring.build_context('fixture',repo_root=tmp_path)['consumed']['corrections']

    replacement=authoring.bank_correction('fixture',{'text':'Legitimate replacement instruction.',
        'kind':'request','scope':'project','by':'author','supersedes':parent['id']},repo_root=tmp_path)['correction']
    assert replacement['supersedes']==parent['id']
    restored=authoring.correction_status('fixture',{'id':parent['id'],'status':'open',
        'note':'Restored after an accidental replacement.'},repo_root=tmp_path)
    assert restored['correction']['status']=='open'
    assert restored['correction']['status_history'][-1]['status']=='open'


def test_node_anchored_review_stales_and_enters_only_matching_source_proposal_context(
        tmp_path,monkeypatch):
    from laplace.manuscript import manuscript_source, proposal_preflight
    _fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(manuscript_source,'resolve',lambda project,repo_root=None:_source(project,repo_root))
    selection={'files':['manuscript/sec_one.tex'],'line_start':1,'line_end':2,
               'node_id':'claim:selected'}
    before=authoring.build_context('fixture',selection,repo_root=tmp_path)
    other_selection={**selection,'node_id':'claim:other'}
    before_other=authoring.build_context('fixture',other_selection,repo_root=tmp_path)
    finding=authoring.bank_correction('fixture',{'text':'Qualify this selected claim.',
        'kind':'factual','scope':'passage','anchor':{'node_id':'claim:selected'},
        'by':'eigen:review'},repo_root=tmp_path)['correction']

    matching=authoring.inspect('fixture',selection,repo_root=tmp_path,context_id=before['context_id'])
    assert any('correction-unconsumed:'+finding['id'] in row['reasons'] for row in matching['stale'])
    other=authoring.inspect('fixture',other_selection,repo_root=tmp_path,
                            context_id=before_other['context_id'])
    assert not any('correction-unconsumed:'+finding['id'] in row['reasons'] for row in other['stale'])

    current=authoring.build_context('fixture',selection,repo_root=tmp_path)
    assert finding['id'] in current['consumed']['corrections']
    assert finding['text'] in current['prompt']
    turn={'project':'fixture','selection':selection,'context_id':current['context_id'],
          'dependencies':current['dependencies'],'document':current['document']}
    checked=proposal_preflight.preflight(tmp_path,'fixture',turn,{'answer':'Address review.',
        'edits':[{'file':'sec_one.tex','line_start':2,'line_end':2,
            'before':'The obstacle motivates the construction.\\cite{need-source}',
            'after':'Under the stated qualification, the obstacle motivates the construction.\\cite{need-source}',
            'reason':'Address the anchored review finding.'}]})
    assert checked['valid'],checked['errors']


def test_correction_status_resolves_feedback_omits_active_context_and_reopens(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    created = authoring.bank_correction("fixture", {
        "text": "Keep the finite-size qualification.", "kind": "factual",
        "scope": "project", "anchor": {}}, repo_root=tmp_path)
    correction_id = created["correction"]["id"]
    feedback_id = created["correction"]["feedback_id"]
    before = authoring.build_context("fixture", repo_root=tmp_path)
    assert correction_id in before["consumed"]["corrections"]
    assert "Keep the finite-size qualification." in before["prompt"]

    resolved = authoring.correction_status("fixture", {
        "id": correction_id, "status": "resolved", "base_revision": created["revision"],
        "note": "Addressed in the current explanation."}, repo_root=tmp_path)
    after = authoring.build_context("fixture", repo_root=tmp_path)
    history = authoring.history("fixture", {"id": correction_id}, repo_root=tmp_path)
    from laplace.manuscript import manuscript_bridge
    ledger = tmp_path / "manuscript" / "feedback" / "feedback.jsonl"
    feedback = next(row for row in manuscript_bridge.feedback_list(
        tmp_path, "fixture", ledger=ledger)["records"] if row["id"] == feedback_id)

    assert resolved["status"] == "resolved"
    assert resolved["correction"]["status_note"] == "Addressed in the current explanation."
    assert correction_id not in after["consumed"]["corrections"]
    assert "Keep the finite-size qualification." not in after["prompt"]
    assert history["item"]["status"] == "resolved"
    assert feedback["status"] == "resolved"
    assert feedback["status_history"][-1]["note"] == "Addressed in the current explanation."

    reopened = authoring.correction_status("fixture", {
        "id": correction_id, "status": "open", "base_revision": resolved["revision"]},
        repo_root=tmp_path)
    restored = authoring.build_context("fixture", repo_root=tmp_path)

    assert reopened["status"] == "open"
    assert len(reopened["correction"]["status_history"]) == 2
    assert correction_id in restored["consumed"]["corrections"]
    assert "Keep the finite-size qualification." in restored["prompt"]


def test_applied_edit_is_history_and_cannot_be_reopened_as_unresolved_work(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    from laplace.pipeline import edits, ledger
    row = edits.make_author_edit("sec_one", "p1", "sec_one.tex", "Before.", "After.",
                                 project="fixture")
    ledger.append_jsonl(tmp_path / "manuscript" / "feedback" / "feedback.jsonl", row)

    state = authoring.load("fixture", repo_root=tmp_path)
    context = authoring.build_context("fixture", repo_root=tmp_path)

    projected = next(item for item in state["corrections"] if item["id"] == row["id"])
    assert projected["applied"] is True and projected["status"] == "resolved"
    assert row["id"] not in context["consumed"]["corrections"]
    with pytest.raises(ValueError, match="applied edit history"):
        authoring.correction_status("fixture", {
            "id": row["id"], "status": "open", "base_revision": state["revision"]},
            repo_root=tmp_path)


def test_feedback_only_comment_stays_in_history_when_closed(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    from laplace.manuscript import manuscript_bridge
    ledger = tmp_path / "manuscript" / "feedback" / "feedback.jsonl"
    made = manuscript_bridge.feedback_add(tmp_path, "fixture", {
        "node_id": "sec_one", "comment": "Check this transition.",
        "kind": "note", "anchor": {"file": "sec_one.tex"}, "by": "author"}, ledger=ledger)
    correction_id = made["record"]["id"]
    current = authoring.load("fixture", repo_root=tmp_path)

    closed = authoring.correction_status("fixture", {
        "id": correction_id, "status": "dismissed", "base_revision": current["revision"],
        "note": "Superseded by the new structure."}, repo_root=tmp_path)
    history = authoring.history("fixture", {"id": correction_id}, repo_root=tmp_path)
    context = authoring.build_context("fixture", repo_root=tmp_path)

    assert closed["correction"]["_ledger_projection"] is True
    assert history["item"]["status"] == "dismissed"
    assert history["item"]["status_note"] == "Superseded by the new structure."
    assert correction_id not in context["consumed"]["corrections"]


def test_optimistic_revision_and_explicit_passage_anchor(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    authoring.save("fixture", {"base_revision": 0, "argument": "A"}, repo_root=tmp_path)
    with pytest.raises(ValueError, match="revision conflict"):
        authoring.save("fixture", {"base_revision": 0, "argument": "B"}, repo_root=tmp_path)
    with pytest.raises(ValueError, match="requires an anchor"):
        authoring.bank_correction("fixture", {"text": "x", "kind": "note", "scope": "passage"}, repo_root=tmp_path)


def test_multi_section_selection_keeps_the_connected_intermediate_source(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    authoring.save("fixture", {"base_revision": 0, "argument": "A connected account"}, repo_root=tmp_path)
    context = authoring.build_context("fixture", {"section_ids": ["sec_one", "sec_three"]}, repo_root=tmp_path)
    assert "NUMBERED SOURCE ADDRESS GUIDE [manuscript/sec_two.tex]" in context["prompt"]


def test_explicit_root_and_chapter_file_read_does_not_expand_the_intermediate_book(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    from laplace.native import tools as writing_tools
    result = writing_tools.execute(tmp_path, "fixture", "work", "source",
                                   {"files": ["main.tex", "sec_three.tex"]})
    assert [row["file"] for row in result["sources"]] == [
        "manuscript/main.tex", "manuscript/sec_three.tex"]
    assert result["sources"][0]["text"] == (tmp_path / "manuscript/main.tex").read_text()
    assert result["sources"][1]["text"] == (tmp_path / "manuscript/sec_three.tex").read_text()
    assert "The obstacle motivates" not in str(result)


def test_multifile_selection_does_not_apply_one_files_line_bounds_to_all(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    context = authoring.build_context("fixture", {
        "files": ["sec_one.tex", "sec_three.tex"], "line_start": 1, "line_end": 1,
        "quote": "The obstacle motivates the construction."}, repo_root=tmp_path)
    assert "The obstacle motivates the construction." in context["prompt"]
    assert "The construction changes what the reader can do." in context["prompt"]
    assert "The consequence raises a final question." in context["prompt"]


def test_quote_only_selection_rejects_repeated_text_and_line_bounds_recover(tmp_path,monkeypatch):
    _fixture(tmp_path,monkeypatch)
    path=tmp_path/'manuscript'/'sec_one.tex'
    path.write_text('Repeated sentence.\nMiddle.\nRepeated sentence.\n',encoding='utf-8')
    with pytest.raises(ValueError,match='occurs more than once.*line_start'):
        authoring.inspect('fixture',{'files':['sec_one.tex'],'quote':'Repeated sentence.'},
                          repo_root=tmp_path)
    exact=authoring.inspect('fixture',{'files':['sec_one.tex'],'quote':'Repeated sentence.',
        'line_start':3,'line_end':3},repo_root=tmp_path)
    assert exact['sources'][0]['text']=='Repeated sentence.\n'


def test_unrelated_source_change_does_not_stale_a_receipted_scope(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    authoring.save("fixture", {"base_revision": 0, "argument": "A", "section_ids": ["sec_one"]}, repo_root=tmp_path)
    context = authoring.build_context("fixture", repo_root=tmp_path)
    (tmp_path / "manuscript" / "sec_three.tex").write_text("Unrelated change", encoding="utf-8")
    inspected = authoring.inspect("fixture", repo_root=tmp_path)
    assert context["context_id"] not in {item["context_id"] for item in inspected["stale"]}


def test_monolithic_tex_selection_uses_explicit_lines_and_canonical_def_ids(tmp_path, monkeypatch):
    directory = tmp_path / "manuscript"
    directory.mkdir()
    (directory / "main.tex").write_text("before\nACTIVE ONE\nACTIVE TWO\nafter\n", encoding="utf-8")
    monkeypatch.setattr(authoring, "_source", _source)
    from laplace.pipeline import verify
    monkeypatch.setattr(verify, "_load_corpus_network", lambda *a: ({"nodes": {
        "def:active-concept": {"projection": {"term": "Active concept", "aliases": ["AC"]}}}}, ""))
    authoring.save("fixture", {"base_revision": 0, "argument": "A"}, repo_root=tmp_path)
    context = authoring.build_context("fixture", {"files": ["main.tex"], "line_start": 2, "line_end": 3}, repo_root=tmp_path)
    assert "000002 | ACTIVE ONE\n000003 | ACTIVE TWO" in context["prompt"]
    assert "before" not in context["prompt"]
    assert context["consumed"]["glossary"][0]["id"] == "def:active-concept"


def test_missing_document_still_accepts_project_framing(tmp_path, monkeypatch):
    missing = {**_source("fixture", tmp_path), "status": "missing", "root": None,
               "diagnostics": ["no manuscript yet"]}
    monkeypatch.setattr(authoring, "_source", lambda *args, **kwargs: missing)
    saved = authoring.save("fixture", {"base_revision": 0, "argument": "Frame before TeX"}, repo_root=tmp_path)
    assert saved["argument"] == "Frame before TeX"
    assert authoring.inspect("fixture", repo_root=tmp_path)["sources"] == []


def test_passage_correction_respects_receipted_line_span(tmp_path, monkeypatch):
    directory = tmp_path / "manuscript"
    directory.mkdir()
    (directory / "main.tex").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    monkeypatch.setattr(authoring, "_source", _source)
    authoring.save("fixture", {"base_revision": 0, "argument": "A"}, repo_root=tmp_path)
    context = authoring.build_context("fixture", {"files": ["main.tex"], "line_start": 2, "line_end": 2}, repo_root=tmp_path)
    current = authoring.load("fixture", repo_root=tmp_path)
    authoring.bank_correction("fixture", {"base_revision": current["revision"], "text": "line four", "kind": "style",
                                            "scope": "passage", "anchor": {"file": "main.tex", "line_start": 4, "line_end": 4}}, repo_root=tmp_path)
    assert context["context_id"] not in {item["context_id"] for item in authoring.inspect("fixture", repo_root=tmp_path)["stale"]}
    current = authoring.load("fixture", repo_root=tmp_path)
    authoring.bank_correction("fixture", {"base_revision": current["revision"], "text": "line two", "kind": "style",
                                            "scope": "passage", "anchor": {"file": "main.tex", "line_start": 2, "line_end": 2}}, repo_root=tmp_path)
    row = next(item for item in authoring.inspect("fixture", repo_root=tmp_path)["stale"] if item["context_id"] == context["context_id"])
    assert any(reason.startswith("correction-unconsumed:") for reason in row["reasons"])


def test_real_book_relative_chapter_selection_consumes_its_annotation(tmp_path):
    from laplace.projects import library as writing_projects
    status, made = writing_projects.create({'name':'connected-book','title':'Connected Book',
        'kind':'book','purpose':'Explain the construction.','audience':'New readers'},root=tmp_path)
    assert status == 201
    correction = authoring.bank_correction('connected-book', {'text':'Retain the hypothesis.',
        'kind':'note','scope':'passage','anchor':{'file':'chapters/chapter-01.tex','line_start':1,'line_end':4}}, tmp_path)
    ctx = authoring.build_context('connected-book',{'files':['chapters/chapter-01.tex'],'line_start':1,'line_end':4},tmp_path)
    assert ctx['selection'] == ['synthetics papers/connected-book/manuscript/chapters/chapter-01.tex']
    assert 'Explain the construction.' in ctx['prompt']
    assert correction['correction']['id'] in ctx['consumed']['corrections']
