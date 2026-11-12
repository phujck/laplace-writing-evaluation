from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from laplace.research import concepts as concepts_surface, corpus_ingest
from laplace.manuscript import project_structure
from laplace.web import project_work_surface
from laplace.research import research_records
from laplace.research import research_presentation
from laplace.manuscript import source_application
from laplace.writing import records as writing_records
from laplace.writing import turn_context
from laplace.writing import turn_admission
from laplace.writing import session_reads
from laplace.writing import provider as writing_provider
from laplace.pipeline import authoring


def _fixture(root: Path) -> Path:
    manuscript = root / "book" / "manuscript"
    manuscript.mkdir(parents=True)
    (root / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "book", "kind": "conceptric", "project_dir": "book",
        "tex_root": "book/manuscript",
        "manifest": {"document": {"root": "book/manuscript/main.tex"}},
    }]}))
    (root / "corpus").mkdir(); (root / "corpus/corpus.bib").write_text("")
    (manuscript / "main.tex").write_text(
        "\\documentclass{book}\n\\begin{document}\n\\input{N1}\n\\input{N2}\n\\end{document}\n")
    (manuscript / "N1.tex").write_text("\\chapter{Opening}\\label{source-opening}\nOpening prose.\n")
    (manuscript / "N2.tex").write_text("\\chapter{Result}\\label{source-result}\nResult prose.\n")
    plan = {"meta": {"project": "book", "target_dir": "book/manuscript"}, "sections": [
        {"id": "N1", "title": "Opening", "job": "Orient the reader.",
         "source_file": "book/manuscript/N1.tex", "source_label": "source-opening",
         "beats": ["res:one"], "nodes_in_order": ["res:one", "def:one"], "refs": []},
        {"id": "N2", "title": "Result", "job": "State the result.",
         "source_file": "book/manuscript/N2.tex", "source_label": "source-result",
         "beats": ["res:two"], "nodes_in_order": ["res:two"], "refs": []},
    ], "appendices": []}
    (manuscript / "projection_plan.json").write_text(json.dumps(plan, indent=2))
    for ident, kind, essence in (("res:one", "result", "First result"),
                                 ("def:one", "definition", "A definition"),
                                 ("res:two", "result", "Second result"),
                                 ("def:unplanned", "definition", "Unplanned concept")):
        result = corpus_ingest.rewire_add(root, "book", {
            "kind": "add-node", "node": ident, "node_kind": kind,
            "essence": essence, "by": "fixture"})
        assert not result.get("error"), result
    for order, ident in enumerate(("res:one", "res:two")):
        assert not corpus_ingest.rewire_add(root, "book", {
            "kind": "set-spine", "node": ident, "ord": order,
            "narrative": "beat", "by": "fixture"}).get("error")
    assert not corpus_ingest.rewire_add(root, "book", {"kind": "set-projection",
        "node": "def:one", "value": {"section_ref": "res:one"}, "by": "fixture"}).get("error")
    assert not corpus_ingest.rewire_add(root, "book", {"kind": "add-edge",
        "node": "def:unplanned", "target": "res:one", "rel": "support",
        "by": "fixture"}).get("error")
    (manuscript / "result.json").write_text('{"value":1}\n')
    return manuscript


def _hashes(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file() and not path.name.endswith(".lock")}


def test_plan_citations_use_selected_bibliographies_and_refusal_names_exact_defects(tmp_path, monkeypatch):
    import importlib.util
    from laplace.manuscript import storyboard
    manuscript = _fixture(tmp_path)
    main = manuscript / "main.tex"
    main.write_text(main.read_text().replace("\\end{document}",
        "\\bibliography{refs,extra}\n\\end{document}"))
    (manuscript / "refs.bib").write_text("@article{local-primary, title={Primary}}\n")
    (manuscript / "extra.bib").write_text("@article{second-primary, title={Second}}\n")
    # A key in an unrelated global library is not a consumer of this manuscript.
    (tmp_path / "corpus/corpus.bib").write_text("@article{global-only, title={Other}}\n")
    path = Path(__file__).parents[1] / "scripts/validate_projection_plan.py"
    spec = importlib.util.spec_from_file_location("_test_live_plan_validator", path)
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    def validate(plan, corpus, repo_root=None):
        preview = tmp_path / "candidate-plan.json"
        preview.write_text(json.dumps(plan))
        return validator.validate(str(preview), corpus, repo_root=repo_root)
    monkeypatch.setattr(storyboard, "_validate_reduced", validate)
    revision = project_structure.state("book", tmp_path)["revision"]
    accepted = project_structure.change("book", {"operation": "plan", "expected_revision": revision,
        "op": {"kind": "set-refs", "section": "N1", "refs": ["local-primary", "second-primary"]}}, tmp_path)
    assert accepted["ok"]
    before = (manuscript / "projection_plan.json").read_bytes()
    with pytest.raises(ValueError) as error:
        project_structure.change("book", {"operation": "plan", "expected_revision": accepted["revision"],
            "op": {"kind": "add-section", "section": "S-new", "title": "New",
                   "refs": ["global-only"], "figures": ["unregistered-asset"]}}, tmp_path)
    assert "missing_refs" in str(error.value) and "global-only" in str(error.value)
    assert "fig_defects" in str(error.value) and "unregistered-asset" in str(error.value)
    assert "S-new" in str(error.value)
    assert (manuscript / "projection_plan.json").read_bytes() == before


def test_structure_read_joins_plan_nodes_edges_source_and_has_no_side_effect(tmp_path):
    manuscript = _fixture(tmp_path)
    before = _hashes(tmp_path)

    value = project_structure.state("book", tmp_path)

    assert value["authority"]["plan_path"] == "book/manuscript/projection_plan.json"
    assert value["selected_source"]["root"] == "book/manuscript/main.tex"
    assert [section["id"] for section in value["sections"]] == ["N1", "N2"]
    assert value["sections"][0]["beat_ids"] == ["res:one"]
    assert value["sections"][0]["beats"][0]["label"] == "First result"
    assert value["sections"][0]["source"]["source_files"] == ["book/manuscript/N1.tex"]
    assert json.loads((manuscript / "projection_plan.json").read_text())["sections"][0]["beats"] == ["res:one"]
    assert _hashes(tmp_path) == before

    code, _, raw = project_work_surface.handle(
        "/work/structure", {"project": ["book"]}, "GET", repo_root=tmp_path)
    assert code == 200 and json.loads(raw)["revision"] == value["revision"]


def test_source_delivery_has_one_exact_copy_bounded_neighbors_and_optional_numbering(tmp_path):
    from laplace.native import tools as writing_tools
    from laplace.writing import reads
    manuscript = _fixture(tmp_path)
    (manuscript / "N1.tex").write_text("Earlier unconsulted material.\n" * 800 + "Boundary.\n" * 300)
    expected = (manuscript / "N2.tex").read_text()
    value = writing_tools.execute(tmp_path, "book", "work", "source", {"files": ["N2.tex"]})
    assert value["source_format"] == "raw"
    assert value["sources"][0]["text"] == expected
    assert "numbered_text" not in value["sources"][0]
    assert value["stale"] == [] and value["staleness_scope"]["receipts_checked"] == 0
    boundary = next(row for row in value["boundaries"] if row["file"].endswith("N1.tex"))
    assert boundary["excerpt"] and len(boundary["text"]) == 2000
    assert boundary["line_start"] > 1 and boundary["character_start"] > 0
    assert boundary["read_more"]["operation"] == "source"
    assert "Earlier unconsulted material" not in boundary["text"]
    numbered = writing_tools.execute(tmp_path, "book", "work", "source",
        {"files": ["N2.tex"], "include_numbered_text": True})
    assert numbered["sources"][0]["text"] == expected
    assert "000001 | " in numbered["sources"][0]["numbered_text"]
    assert reads.read_output_digest("source", value) == reads.read_output_digest("source", numbered)
    # A change beyond the actual bounded neighbor must not stale this read.
    path = manuscript / "N1.tex"
    path.write_text(path.read_text().replace("Earlier unconsulted", "Other unconsulted", 1))
    current = writing_tools.execute(tmp_path, "book", "work", "source", {"files": ["N2.tex"]})
    assert reads.read_output_digest("source", current) == reads.read_output_digest("source", value)


def test_authored_title_survives_evidence_binding_and_reaches_research_reader(tmp_path):
    _fixture(tmp_path)
    for value in ({"title": "Controlled cutoff calculations"},
                  {"result_bindings": [{"id": "run-result", "revision": "saved-result"}]}):
        result = corpus_ingest.rewire_add(tmp_path, "book", {
            "kind": "set-projection", "node": "res:one", "value": value,
            "by": "fixture"})
        assert not result.get("error"), result

    state = project_structure.state("book", tmp_path)
    node = next(row for row in state["logical_objects"] if row["id"] == "res:one")
    assert node["label"] == "Controlled cutoff calculations"
    assert node["summary"] == "First result"
    assert state["sections"][0]["beats"][0]["label"] == node["label"]
    usage = research_presentation._result_usage("book", tmp_path)["run-result"][0]
    assert usage["concept"]["label"] == node["label"]
    assert usage["concept"]["summary"] == "First result"
    assert usage["manuscript_locations"][0]["id"] == "N1"

    # Clearing the presentation title recovers the established semantic label.
    corpus_ingest.rewire_add(tmp_path, "book", {
        "kind": "set-projection", "node": "res:one", "value": {"title": ""},
        "by": "fixture"})
    assert research_presentation._result_usage("book", tmp_path)["run-result"][0]["concept"]["label"] == "First result"


def test_structure_tool_overview_is_compact_and_descends_to_selected_science(tmp_path):
    _fixture(tmp_path)
    from laplace.native import tools as writing_tools

    overview=writing_tools.execute(tmp_path,'book','work','structure',{})
    assert overview['schema_version']=='laplace.project-structure-overview/1'
    assert overview['revision']==project_structure.state('book',tmp_path)['revision']
    assert overview['reader_plan']['sections_total']==2
    assert {row['id'] for row in overview['logical_objects']['items']} >= {
        'res:one','def:one','res:two','def:unplanned'}
    assert all('summary' not in row for row in overview['logical_objects']['items'])
    assert overview['read_routes']['inventory']['payload']['view']=='catalog'
    assert overview['gaps_omitted']==0
    assert len(json.dumps(overview,ensure_ascii=False))<12_000

    selected=writing_tools.execute(tmp_path,'book','work','structure',{'section_ids':['N1']})
    assert [row['id'] for row in selected['sections']]==['N1']
    assert selected['sections'][0]['beats'][0]['id']=='res:one'


def test_structure_overview_pages_more_than_200_section_identities_and_declares_gap_omission(
        tmp_path,monkeypatch):
    from laplace.native import tools as writing_tools
    sections=[{'id':f'section-{index:03d}','title':f'Section {index}','kind':'section',
               'order':index,'node_ids':[],'beat_ids':[]} for index in range(205)]
    synthetic={'status':'AVAILABLE','eligible_for_authoring':True,'revision':'sha256:structure-page',
        'authority':{'plan_path':'projection_plan.json'},
        'selected_source':{'status':'resolved','root':'main.tex','revision':'sha256:source'},
        'sections':sections,'logical_objects':[],'unplaced_nodes':[],'evidence':[],
        'gaps':[{'kind':'fixture','id':f'gap-{index}'} for index in range(95)],'edges':[]}
    monkeypatch.setattr(project_structure,'state',lambda *a,**k:synthetic)

    first=writing_tools.execute(tmp_path,'book','work','structure',{})
    second=writing_tools.execute(tmp_path,'book','work','structure',
                                 first['reader_plan']['next_read']['payload'])

    assert first['revision']==second['revision']=='sha256:structure-page'
    assert [row['id'] for row in first['reader_plan']['sections']]==[
        f'section-{index:03d}' for index in range(200)]
    assert [row['id'] for row in second['reader_plan']['sections']]==[
        f'section-{index:03d}' for index in range(200,205)]
    assert first['reader_plan']['sections_omitted']==5
    assert 'next_read' not in second['reader_plan']
    assert first['counts']['gaps']==95 and first['gaps_omitted']==15


def test_logical_plan_exposes_paged_complete_inventory_with_exact_descent_routes(tmp_path):
    _fixture(tmp_path)
    from laplace.native import tools as writing_tools

    attention=writing_tools.execute(tmp_path,'book','work','logical_plan',{'node':'res:one'})
    route=attention['complete_inventory']
    assert route=={'operation':'logical_plan','payload':{'view':'catalog','offset':0,'limit':80},
                   'purpose':"Page every canonical logical identity without copying each object's scientific body."}
    first=writing_tools.execute(tmp_path,'book','work','logical_plan',{'view':'catalog','offset':0,'limit':2})
    second=writing_tools.execute(tmp_path,'book','work','logical_plan',first['next_read']['payload'])
    assert first['total']==4 and first['next_offset']==2
    assert {row['id'] for row in first['items']+second['items']}=={
        'res:one','def:one','res:two','def:unplanned'}
    assert first['read_routes']['item']=={'operation':'concept','payload':{'node':'<item_id>'}}


def test_local_read_digests_ignore_only_incidental_global_revisions(tmp_path):
    _fixture(tmp_path)
    from laplace.native import tools as writing_tools
    from laplace.writing import reads
    concept_before=writing_tools.execute(tmp_path,'book','work','concept',{'node':'res:one'})
    structure_before=writing_tools.execute(tmp_path,'book','work','structure',{'node_id':'res:one'})
    overview_before=writing_tools.execute(tmp_path,'book','work','structure',{})

    unrelated=corpus_ingest.rewire_add(tmp_path,'book',{
        'kind':'edit-essence','node':'res:two','value':'Changed only in another section.'})
    assert unrelated.get('ok'),unrelated
    concept_unrelated=writing_tools.execute(tmp_path,'book','work','concept',{'node':'res:one'})
    structure_unrelated=writing_tools.execute(tmp_path,'book','work','structure',{'node_id':'res:one'})
    assert concept_before['revision']!=concept_unrelated['revision']
    assert concept_before['mutation_revision']==concept_unrelated['mutation_revision']
    assert reads.read_output_digest('concept',concept_before)==reads.read_output_digest(
        'concept',concept_unrelated)
    assert structure_before['revision']==structure_unrelated['revision']
    assert structure_before['structure_revision'] is None and structure_unrelated['structure_revision'] is None
    assert structure_before['full_guard_read']['payload']=={'view':'full'}
    assert reads.read_output_digest('structure',structure_before)==reads.read_output_digest(
        'structure',structure_unrelated)
    overview_unrelated=writing_tools.execute(tmp_path,'book','work','structure',{})

    hidden=corpus_ingest.rewire_add(tmp_path,'book',{'kind':'set-projection','node':'res:two',
        'value':{'mathematics':{'proof':{'text':'Unreturned proof detail.'}}}})
    assert hidden.get('ok'),hidden
    overview_hidden=writing_tools.execute(tmp_path,'book','work','structure',{})
    assert reads.read_output_digest('structure',overview_unrelated)==reads.read_output_digest(
        'structure',overview_hidden)

    added=corpus_ingest.rewire_add(tmp_path,'book',{'kind':'add-node','node':'support:new-map-item',
        'node_kind':'support','essence':'A new overview identity.','parent':'paper://'})
    assert added.get('ok'),added
    overview_after=writing_tools.execute(tmp_path,'book','work','structure',{})
    assert reads.read_output_digest('structure',overview_before)!=reads.read_output_digest(
        'structure',overview_after)

    relevant=corpus_ingest.rewire_add(tmp_path,'book',{
        'kind':'edit-essence','node':'res:one','value':'Changed selected result.'})
    assert relevant.get('ok'),relevant
    concept_relevant=writing_tools.execute(tmp_path,'book','work','concept',{'node':'res:one'})
    structure_relevant=writing_tools.execute(tmp_path,'book','work','structure',{'node_id':'res:one'})
    assert reads.read_output_digest('concept',concept_unrelated)!=reads.read_output_digest(
        'concept',concept_relevant)
    assert reads.read_output_digest('structure',structure_unrelated)!=reads.read_output_digest(
        'structure',structure_relevant)


def test_local_reads_allow_precise_source_apply_after_unrelated_edit_but_premise_change_blocks(
        tmp_path,monkeypatch):
    manuscript=_fixture(tmp_path)
    from laplace.manuscript import review_surface
    from laplace.native import tools as writing_tools
    for payload in ({'kind':'add-node','node':'support:elsewhere','node_kind':'support',
                     'essence':'Outside the selected argument.','parent':'paper://'},
                    {'kind':'add-edge','node':'res:one','target':'def:one','rel':'prerequisite',
                     'rationale':'The result requires this definition.'}):
        assert corpus_ingest.rewire_add(tmp_path,'book',payload).get('ok')

    def seed(suffix,before,after):
        selection={'files':['N1.tex'],'line_start':2,'line_end':2,'node_id':'res:one'}
        context=authoring.build_context('book',selection,repo_root=tmp_path)
        session,turn='WS-'+suffix,'WT-'+suffix
        writing_records.bank(tmp_path,{'record':'writing-session','id':session,
            'project':'book','provider':'codex','model':'fixture','effort':'low'})
        writing_records.bank(tmp_path,{'record':'writing-turn','id':turn,'session_id':session,
            'project':'book','mode':'revise','selection':selection,'context_id':context['context_id'],
            'dependencies':context['dependencies'],'document':context['document'],
            'consumed':context['consumed'],'science_context_digest':context['science_context_digest']})
        from laplace.manuscript import proposal_preflight
        proposal={'answer':'fixture','edits':[{'file':'N1.tex','line_start':2,'line_end':2,
            'before':before,'after':after,'reason':'precise fixture edit'}]}
        checked=proposal_preflight.preflight(tmp_path,'book',session_reads._records(tmp_path)['turns'][turn],proposal)
        assert checked['valid'],checked
        writing_records.bank(tmp_path,{'record':'writing-reply','id':'WR-'+suffix,
            'turn_id':turn,'session_id':session,'project':'book','status':'completed',
            'proposal':checked['proposal']})
        writing_tools.execute(tmp_path,'book','work','concept',{'node':'res:one'},turn_id=turn)
        writing_tools.execute(tmp_path,'book','work','structure',{'node_id':'res:one'},turn_id=turn)
        return turn

    monkeypatch.setattr(review_surface,'manuscript_dir',lambda project:manuscript)
    allowed=seed('local-unrelated','Opening prose.','Applied after unrelated change.')
    assert corpus_ingest.rewire_add(tmp_path,'book',{'kind':'edit-essence',
        'node':'support:elsewhere','value':'Changed elsewhere.'}).get('ok')
    applied=source_application.apply_proposal(tmp_path,{'turn_id':allowed,'proposal_version':session_reads.session_turn_detail(tmp_path,"book",allowed,"turn")["turn"]["proposal_version"]})
    assert applied['complete'] is True

    blocked=seed('local-premise','Applied after unrelated change.','Must not apply stale premise.')
    assert corpus_ingest.rewire_add(tmp_path,'book',{'kind':'edit-essence',
        'node':'def:one','value':'Changed required definition.'}).get('ok')
    with pytest.raises(ValueError,match='changed'):
        source_application.apply_proposal(tmp_path,{'turn_id':blocked,'proposal_version':session_reads.session_turn_detail(tmp_path,"book",blocked,"turn")["turn"]["proposal_version"]})
    assert 'Must not apply stale premise.' not in (manuscript/'N1.tex').read_text()


def test_group_focus_prompt_keeps_exact_members_and_routes_without_copying_53_bodies():
    descendants = [{"id": f"result:{index}", "title": f"Result {index}", "label": f"BODY-{index}",
                    "summary": f"BODY-{index}", "kind": "result", "depth": 1,
                    "parent": "goal:book", "child_count": 0}
                   for index in range(53)]
    structure = {"focus": {"node": {"id": "goal:book", "kind": "goal", "title": "Book goal",
                                           "summary": "Exact project purpose.", "child_count": 53},
                           "containment": {"authority": {"hierarchy": "canonical"},
                                           "current": {"id": "goal:book", "kind": "goal",
                                                       "title": "Book goal", "summary": "Exact project purpose.",
                                                       "child_count": 53},
                                           "descendants": descendants, "dependencies": [],
                                           "boundary_nodes": [], "omission_residual": {},
                                           "revision": "focus-revision"},
                           "neighbors": [], "edges": [], "revision": "joined-revision"}}

    projected = authoring._prompt_structure_projection(structure)
    encoded = json.dumps(projected, ensure_ascii=False)
    overview = projected["focus"]["containment"]

    assert overview["immediate_parts_total"] == 53
    assert len(overview["immediate_parts"]) == 53
    assert overview["current"]["purpose"] == "Exact project purpose."
    assert overview["read_routes"]["parts_and_dependencies"]["operation"] == "concept_tree"
    assert all(f'"id": "result:{index}"' in encoded for index in range(53))
    assert "BODY-0" not in encoded and "BODY-52" not in encoded
    assert len(encoded) < 20_000


def test_200_member_workspace_scope_keeps_all_ids_with_bounded_identity_preview():
    ids = [f"claim:{index:03d}" for index in range(220)]
    selected = [{"id": ident, "label": f"LONG-BODY-{ident}-" + "x" * 4000,
                 "summary": f"LONG-BODY-{ident}-" + "x" * 4000, "kind": "result"}
                for ident in ids[:40]]
    structure = {"selected_node_ids": ids, "selected_nodes": selected,
                 "selected_nodes_total": len(ids), "selected_nodes_omitted": len(ids) - len(selected),
                 "selected_node_read_routes": {"concept": {"operation": "concept",
                                                             "payload": {"node": "<selected_node_id>"}}}}

    projected = authoring._prompt_structure_projection(structure)
    encoded = json.dumps(projected, ensure_ascii=False)

    assert projected["selected_node_ids"] == ids
    assert projected["selected_nodes_total"] == 220
    assert projected["selected_nodes_omitted"] == 180
    assert len(projected["selected_nodes"]) == 40
    assert all(ident in encoded for ident in ids)
    assert "LONG-BODY" not in encoded
    assert len(encoded) < 30_000


def test_leaf_focus_prompt_keeps_scientific_body_and_direct_prerequisite():
    structure = {"focus": {"node": {"id": "theorem:leaf", "kind": "theorem",
                                           "summary": "Exact leaf statement."},
                           "containment": {"current": {"id": "theorem:leaf", "kind": "theorem"},
                                           "descendants": []},
                           "mathematical_record": {"node": "theorem:leaf",
                                                   "statement_tex": "x=x"}},
                 "direct_dependencies": [{"id": "definition:x", "statement": "Exact prerequisite.",
                                           "relation": "prerequisite"}]}

    projected = authoring._prompt_structure_projection(structure)

    assert projected["focus"]["node"]["summary"] == "Exact leaf statement."
    assert projected["focus"]["containment"]["current"]["id"] == "theorem:leaf"
    assert projected["direct_dependencies"] == {
        "total": 1, "details": "DIRECT PREREQUISITE STATEMENTS FOR THIS SCOPE below"}
    assert structure["direct_dependencies"][0]["statement"] == "Exact prerequisite."
    assert "mathematical_record" not in projected["focus"]


def test_plan_change_uses_canonical_storyboard_with_revision_guard_and_never_edits_tex(tmp_path):
    manuscript = _fixture(tmp_path)
    state = project_structure.state("book", tmp_path)
    tex_before = {path.name: path.read_bytes() for path in manuscript.glob("*.tex")}

    with pytest.raises(ValueError, match="revision conflict"):
        project_structure.change("book", {"operation": "plan", "expected_revision": "wrong",
            "op": {"kind": "retitle", "section": "N1", "title": "New opening"}}, tmp_path)
    changed = project_structure.change("book", {"operation": "plan",
        "expected_revision": state["revision"],
        "op": {"kind": "retitle", "section": "N1", "title": "New opening"}}, tmp_path)

    assert changed["ok"] and changed["writer_result"]["rebuild_class"] == "cheap"
    plan = json.loads((manuscript / "projection_plan.json").read_text())
    assert plan["sections"][0]["title"] == "New opening"
    assert plan["sections"][0]["beats"] == ["res:one"]
    assert (manuscript / "projection_plan.friction.jsonl").is_file()
    assert {path.name: path.read_bytes() for path in manuscript.glob("*.tex")} == tex_before


def test_result_binding_requires_current_exact_revision_and_invalidates_authoring_context(tmp_path):
    manuscript = _fixture(tmp_path)
    created_status, created = research_records.record("book", {
        "kind": "result", "id": "result:one", "result": "result.json"}, tmp_path)
    assert created_status == 201
    revision = created["record"]["revision"]
    current = project_structure.state("book", tmp_path)
    concept_revision = concepts_surface.state("book", node="res:one", root=tmp_path)["revision"]
    with pytest.raises(ValueError, match="unavailable|stale|different"):
        project_structure.change("book", {"operation": "bind_results", "node": "res:one",
            "results": [{"id": "result:one", "revision": "wrong"}],
            "expected_concept_revision": concept_revision,
            "expected_revision": current["revision"]}, tmp_path)
    before = len(corpus_ingest.rewire_list(tmp_path, "book"))
    with pytest.raises(ValueError, match="concept revision conflict"):
        project_structure.change("book", {"operation": "bind_results", "node": "res:one",
            "results": [{"id": "result:one", "revision": revision}],
            "expected_concept_revision": "stale", "expected_revision": current["revision"]}, tmp_path)
    assert len(corpus_ingest.rewire_list(tmp_path, "book")) == before

    bound = project_structure.change("book", {"operation": "bind_results", "node": "res:one",
        "results": [{"id": "result:one", "revision": revision}],
        "expected_concept_revision": concept_revision,
        "expected_revision": current["revision"]}, tmp_path)
    evidence = bound["state"]["sections"][0]["evidence"]
    assert evidence[0]["id"] == "result:one" and evidence[0]["revision_match"] is True
    context = authoring.build_context("book", {"files": ["N1.tex"], "section_ids": ["N1"]}, tmp_path)
    assert context["consumed"]["structure"]["sections"][0]["id"] == "N1"
    assert "Canonical joined structure" in context["prompt"]

    (manuscript / "result.json").write_text('{"value":2}\n')
    live = project_structure.state("book", tmp_path)
    assert any(gap["kind"] == "evidence" for gap in live["gaps"])
    stale = authoring.inspect("book", repo_root=tmp_path)["stale"]
    receipt = next(row for row in stale if row["context_id"] == context["context_id"])
    assert "structure-plan-conceptric-or-evidence-changed" in receipt["reasons"]


def test_bind_results_action_refreshes_research_concept_and_structure_reads(tmp_path):
    manuscript=_fixture(tmp_path)
    status,created=research_records.record('book',{
        'kind':'result','id':'result:linked','result':'result.json'},tmp_path)
    assert status==201
    writing_records.bank(tmp_path,{'record':'writing-session','id':'WS-bind-views',
        'project':'book','provider':'codex','model':'','effort':'low'})
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-bind-views',
        'session_id':'WS-bind-views','project':'book','mode':'work','selection':{}})
    from laplace.native import tools as writing_tools
    writing_tools.execute(tmp_path,'book','work','research',{},turn_id='WT-bind-views')
    concept=writing_tools.execute(tmp_path,'book','work','concept',{'node':'res:one'},turn_id='WT-bind-views')
    structure=writing_tools.execute(tmp_path,'book','work','structure',{},turn_id='WT-bind-views')

    bound=writing_tools.execute(tmp_path,'book','work','structure_change',{
        'operation':'bind_results','node':'res:one','expected_revision':structure['revision'],
        'expected_concept_revision':concept['revision'],
        'results':[{'id':'result:linked','revision':created['record']['revision']}]},
        turn_id='WT-bind-views')

    assert bound['effects']==['structure','concepts','research','pipeline']
    assert bound['action_receipt']['views']==['structure','concepts','research','pipeline']
    assert bound['action_receipt']['mutation_attribution']['exact'] is True
    assert bound['action_receipt']['refreshed_read_baselines']==3
    refreshed=writing_tools.execute(tmp_path,'book','work','research',{})
    usage=next(row for row in refreshed['results'] if row['id']=='result:linked')['usage']
    assert usage[0]['concept']['id']=='res:one'


def test_exact_own_concept_change_refreshes_consumed_structure_but_external_change_stales_it(tmp_path):
    _fixture(tmp_path)
    selection={'node_id':'res:one'}
    context=authoring.build_context('book',selection,repo_root=tmp_path)
    turn='WT-own-concept-structure'
    writing_records.bank(tmp_path,{'record':'writing-session','id':'WS-own-concept-structure',
        'project':'book','provider':'codex','model':'fixture','effort':'low'})
    writing_records.bank(tmp_path,{'record':'writing-turn','id':turn,
        'session_id':'WS-own-concept-structure','project':'book','mode':'work',
        'selection':selection,'context_id':context['context_id'],
        'dependencies':context['dependencies'],'document':context['document'],
        'consumed':context['consumed'],'science_context_digest':context['science_context_digest']})
    from laplace.native import tools as writing_tools
    writing_tools.execute(tmp_path,'book','work','structure',{},turn_id=turn)
    concept=writing_tools.execute(tmp_path,'book','work','concept',{'node':'res:one'},turn_id=turn)

    changed=writing_tools.execute(tmp_path,'book','work','concept_change',{
        'operation':'edit_node','node':'res:one','mutation_revision':concept['mutation_revision'],
        'value':'First result, clarified by this writer.'},turn_id=turn)

    assert changed['action_receipt']['views']==['concepts','structure','pipeline']
    assert changed['action_receipt']['mutation_attribution']['exact'] is True
    assert changed['action_receipt']['context_refreshed'] is True
    current_turn=session_reads._records(tmp_path)['turns'][turn]
    assert not any(row.get('context_id')==current_turn['context_id'] for row in
                   authoring.inspect('book',selection,repo_root=tmp_path)['stale'])

    external=corpus_ingest.rewire_add(tmp_path,'book',{'kind':'edit-essence','node':'res:one',
        'value':'Externally changed after the exact owner receipt.','by':'external-fixture'})
    assert external.get('ok'),external
    stale=authoring.inspect('book',selection,repo_root=tmp_path)['stale']
    assert 'structure-plan-conceptric-or-evidence-changed' in next(
        row for row in stale if row['context_id']==current_turn['context_id'])['reasons']


def test_unplanned_live_logical_node_can_bind_current_result(tmp_path):
    _fixture(tmp_path)
    from laplace.research import corpus_ingest
    corpus_ingest.rewire_add(tmp_path,'book',{'kind':'add-node','node':'res:unplanned','node_kind':'result','essence':'Evidence first','parent':'paper://'})
    status,row=research_records.record('book',{'kind':'result','id':'result:unplanned','result':'result.json'},tmp_path)
    assert status==201
    state=project_structure.state('book',tmp_path)
    concept_revision=concepts_surface.state('book',node='res:unplanned',root=tmp_path)['revision']
    bound=project_structure.change('book',{'operation':'bind_results','node':'res:unplanned','results':[{'id':'result:unplanned','revision':row['record']['revision']}],'expected_revision':state['revision'],'expected_concept_revision':concept_revision},tmp_path)
    assert bound['ok']
    focused = project_structure.context('book', {'node_id': 'res:unplanned'}, tmp_path)
    assert focused['sections'] == []
    assert [(item['node_id'], item['id'], item['revision_match']) for item in focused['evidence']] == [
        ('res:unplanned', 'result:unplanned', True)]


def test_structure_tool_write_is_receipted_and_route_refusal_is_loud(tmp_path):
    _fixture(tmp_path)
    from laplace.native import tools as writing_tools
    current = writing_tools.execute(tmp_path, "book", "discuss", "structure", {},
                                    turn_id="WT-structure")
    changed = writing_tools.execute(tmp_path, "book", "work", "structure_change", {
        "operation": "plan", "expected_revision": current["revision"],
        "op": {"kind": "edit-job", "section": "N1", "job": "A sharper opening."}},
        turn_id="WT-structure")
    assert changed["action_receipt"]["views"] == ["structure", "manuscript", "pipeline"]
    assert changed['state']['revision']==changed['revision']
    assert 'sections' not in changed['state'] and 'logical_objects' not in changed['state']
    assert changed['read_more']=={'operation':'structure','payload':{}}
    with pytest.raises(ValueError, match="Independent review"):
        writing_tools.execute(tmp_path, "book", "review", "structure_change", {
            "operation": "plan", "expected_revision": changed["revision"],
            "op": {"kind": "retitle", "section": "N1", "title": "No"}},
            turn_id="WT-structure")
    rows = [json.loads(line) for line in (tmp_path / "contract/talk.jsonl").read_text().splitlines()]
    assert [row["record"] for row in rows if row.get("turn_id") == "WT-structure"].count(
        "writing-tool-action") == 1


def test_machine_contract_matches_real_add_retitle_and_edge_paths_and_rejects_guessing(tmp_path):
    _fixture(tmp_path)
    from laplace.research import concepts as concepts_surface
    from laplace.native import tools as writing_tools
    from laplace.pipeline.schema import EDGE_RELATIONS

    structure_contract = project_structure.operation_contract()
    add = structure_contract["plan_operations"]["add-section"]
    assert "section" in add["required"] and "id" not in add["properties"]
    help_value = writing_tools.execute(tmp_path, "book", "work", "help",
                                       {"operation": "structure_change"})
    # `requested_payload_contract` is gone: it returned the owner's whole contract a
    # SECOND time beside the copy inside `action`, which was 75.3 per cent of
    # help structure_change. The property that mattered is unchanged and asserted
    # here instead: every variant help serves is BUILT from the owner's own
    # contract, so the owner is still the one source.
    from laplace.native import declarations as writing_declarations
    plan_variants = writing_declarations.variants("structure_change")
    assert set(plan_variants) == set(structure_contract["operations"])
    for name, rule in structure_contract["operations"].items():
        exposed = plan_variants[name]
        identity_legacy = {field for clause in exposed.get("allOf") or []
                           for branch in clause.get("anyOf") or []
                           if "expected" not in (branch.get("required") or [])
                           for field in branch.get("required") or []}
        assert set(rule["required"]) <= set(exposed["required"]) | identity_legacy

    current = project_structure.state("book", tmp_path)
    plan_ledger = tmp_path / "book/manuscript/projection_plan.friction.jsonl"
    before_plan = plan_ledger.read_bytes() if plan_ledger.is_file() else b""
    with pytest.raises(ValueError, match="requires section|unknown keys: id"):
        project_structure.change("book", {"operation": "plan",
            "expected_revision": current["revision"],
            "op": {"kind": "add-section", "id": "guessed", "title": "Wrong key"}}, tmp_path)
    assert (plan_ledger.read_bytes() if plan_ledger.is_file() else b"") == before_plan

    created = project_structure.change("book", {"operation": "plan",
        "expected_revision": current["revision"],
        "op": {"kind": "add-section", "section": "S3", "title": "Third"}}, tmp_path)
    retitled = project_structure.change("book", {"operation": "plan",
        "expected_revision": created["revision"],
        "op": {"kind": "retitle", "section": "S3", "title": "Third result"}}, tmp_path)
    assert next(row for row in retitled["state"]["sections"] if row["id"] == "S3")["title"] == "Third result"

    concept_contract = concepts_surface.operation_contract()
    assert set(concept_contract["edge_relations"]) == set(EDGE_RELATIONS)
    concept_variants = writing_declarations.variants("concept_change")
    assert set(concept_variants) == set(concept_contract["operations"])
    assert writing_tools.execute(tmp_path, "book", "work", "help",
        {"operation": "concept_change"})["action"]["variants"].keys() == concept_variants.keys()
    concept_revision = concepts_surface.state("book", root=tmp_path)["revision"]
    before_edges = len(corpus_ingest.rewire_list(tmp_path, "book"))
    status, refused = concepts_surface.change({"project": "book", "operation": "add_edge",
        "base_revision": concept_revision, "node": "res:two", "destination": "def:one",
        "rel": "support"}, root=tmp_path)
    assert status == 422 and ("requires target" in refused["error"] or "unknown keys" in refused["error"])
    assert len(corpus_ingest.rewire_list(tmp_path, "book")) == before_edges
    status, accepted = concepts_surface.change({"project": "book", "operation": "add_edge",
        "base_revision": concept_revision, "node": "res:two", "target": "def:one",
        "rel": "support", "by": "author"}, root=tmp_path)
    assert status == 200 and accepted["record"]["target"] == "def:one"


def test_work_task_section_scope_reaches_joined_authoring_context(tmp_path, monkeypatch):
    _fixture(tmp_path)
    from laplace.work import project_work
    from laplace.writing import turn_admission
    from laplace.writing import turn_jobs
    from laplace.writing import session_reads
    task = project_work.task("book", {"id": "WORK-N1", "title": "Opening work",
        "goal": "Strengthen the opening.", "section_ids": ["N1"]}, tmp_path)
    prompts = []

    class _Provider:
        def __init__(self, *args, **kwargs): pass
        def run(self, prompt):
            prompts.append(prompt); return {"status": "completed", "text": "Scoped."}

    monkeypatch.setattr(writing_provider, "WritingTurn", _Provider)
    # The selected Work is admitted only with its CURRENT exact observation (M5 S3): the scope and dependency
    # guards of a fresh detail read travel with work_id. Omitted or stale guards refuse before any turn exists.
    detail = project_work.read("book", {"view": "detail", "id": task["id"]}, tmp_path)
    guards = {"expected_work_scope_revision": detail["task"]["work_scope_revision"],
              "expected_dependency_revision": detail["task"]["dependency_revision"]}
    for label, sent in (("omitted", {}), ("stale scope", {**guards, "expected_work_scope_revision": "sha256:" + "0" * 64})):
        jobs = set(turn_jobs._JOBS)
        with pytest.raises(project_work.WorkConflict):
            turn_admission.start_turn(tmp_path, {"project": "book", "provider": "codex", "mode": "work",
                "work_id": task["id"], "text": "Continue this task.", **sent})
        assert prompts == [] and set(turn_jobs._JOBS) == jobs, label + " guards deliver nothing"
    started = turn_admission.start_turn(tmp_path, {"project": "book", "provider": "codex",
        "mode": "work", "work_id": task["id"], "text": "Continue this task.", **guards})
    job = turn_jobs._JOBS[started["turn_id"]]
    with job["condition"]:
        assert job["condition"].wait_for(lambda: job["done"], timeout=5)
    session = session_reads.session_state(tmp_path, started["session_id"])
    structure = session["turns"][0]["dependencies"]["structure"]
    assert [section["id"] for section in structure["sections"]] == ["N1"]
    assert "CURRENT PROJECT WORK" in prompts[0] and "Canonical joined structure" in prompts[0]


def test_new_book_missing_plan_is_readable_then_initialises_and_adds_section_without_tex_write(tmp_path):
    from laplace.projects import library as writing_projects
    status, created = writing_projects.create({"name": "new-book", "title": "New Book",
        "kind": "book", "purpose": "Explain it.", "audience": "readers"}, tmp_path)
    assert status == 201, created
    manuscript = tmp_path / "synthetics papers/new-book/manuscript"
    before = {path.relative_to(manuscript).as_posix(): path.read_bytes()
              for path in manuscript.rglob("*.tex")}

    missing = project_structure.state("new-book", tmp_path)
    assert missing["status"] == "MISSING" and missing["sections"] == []
    assert missing["source_outline"] and missing["gaps"][0]["kind"] == "plan"
    initialised = project_structure.change("new-book", {"operation": "initialize",
        "expected_revision": missing["revision"],
        "expected_source_revision": missing["selected_source"]["revision"]}, tmp_path)
    assert initialised["state"]["status"] == "AVAILABLE"
    assert all(section["node_ids"] == [] and section["beat_ids"] == []
               for section in initialised["state"]["sections"])

    first = initialised["state"]["sections"][0]
    retitled = project_structure.change("new-book", {"operation": "plan",
        "expected_revision": initialised["revision"],
        "op": {"kind": "retitle", "section": first["id"], "title": "Retitled plan section"}}, tmp_path)
    retitled_first = next(section for section in retitled["state"]["sections"] if section["id"] == first["id"])
    assert retitled_first["source"]["mapping"] == "explicit-source-file"
    assert retitled_first["source"]["source_files"] == first["source"]["source_files"]
    assert retitled_first["source"]["title_status"] == "INDEPENDENT"
    assert not any(gap["kind"] == "source-title-drift" for gap in retitled["state"]["gaps"])

    added = project_structure.change("new-book", {"operation": "plan",
        "expected_revision": retitled["revision"],
        "op": {"kind": "add-section", "section": "future", "title": "Future work",
               "job": "State the remaining question."}}, tmp_path)
    assert any(section["id"] == "future" for section in added["state"]["sections"])
    plan = json.loads((manuscript / "projection_plan.json").read_text())
    future = next(section for section in plan["sections"] if section["id"] == "future")
    assert future["beats"] == [] and future["nodes_in_order"] == []
    assert {path.relative_to(manuscript).as_posix(): path.read_bytes()
            for path in manuscript.rglob("*.tex")} == before
    rows = [json.loads(line) for line in (tmp_path / "contract/talk.jsonl").read_text().splitlines()]
    assert any(row.get("record") == "manuscript-plan-initialize" for row in rows)


@pytest.mark.parametrize("variant", [None, "initialize"])
def test_initialize_help_uses_canonical_tokens_and_all_public_identity_paths(tmp_path, variant):
    from laplace.core import grammar, identity_doors
    from laplace.native import declarations as writing_declarations, tools as writing_tools, verbs as writing_verbs
    from laplace.projects import library as writing_projects

    def new_project(name):
        status, created = writing_projects.create({"name": name, "title": name,
            "kind": "book", "purpose": "Identity fixture.", "audience": "test"}, tmp_path)
        assert status == 201, created
        return project_structure.state(name, tmp_path)

    def source_bytes(name):
        selected = project_structure.state(name, tmp_path)["selected_source"]["root"]
        return (tmp_path / selected).read_bytes()

    def plan_path(name):
        return tmp_path / project_structure.state(name, tmp_path)["authority"]["plan_path"]

    # The named tool path consumes the exact example the model sees.
    state = new_project("named-book")
    source_before = source_bytes("named-book")
    help_value = writing_tools.execute(tmp_path, "named-book", "work", "help", {
        "operation": "structure_change", **({"variant": variant} if variant else {})})["action"]
    example = help_value["example"]
    assert set(example) == {"operation", "expected"}
    assert example["expected"] == [state["identities"]["plan:named-book"],
                                   state["identities"]["selected-edition:named-book"]]
    assert "expected_revision" not in example and "expected_source_revision" not in example
    import jsonschema
    schema = help_value.get("input") or writing_declarations.variants("structure_change")["initialize"]
    jsonschema.Draft202012Validator(schema).validate(example)
    changed = writing_tools.execute(tmp_path, "named-book", "work", "structure_change", example,
                                    turn_id="WT-canonical-action")
    assert changed["ok"] and changed["state"]["status"] == "AVAILABLE"
    assert source_bytes("named-book") == source_before
    actions = [row for row in (json.loads(line) for line in
               (tmp_path / "contract/talk.jsonl").read_text().splitlines())
               if row.get("record") == "writing-tool-action"]
    action = next(row for row in actions if row["turn_id"] == "WT-canonical-action")
    assert (action["verb"], action["concept"], action["altitude"], action["dispatch"]) == (
        "create", "plan@plan", "plan", "exact")
    from laplace.representation import writing_bodies
    exact_action = writing_bodies.resolve_fields(action, tmp_path, strict=True)
    assert exact_action["payload"]["expected"] == example["expected"]
    assert "expected_revision" not in exact_action["payload"]

    # The grammar request path carries the same tokens, then restores owner spellings once.
    state = new_project("verb-book")
    request = grammar.Request(verb="create", concept="plan@plan", target="verb-book",
        expected=(state["identities"]["plan:verb-book"],
                  state["identities"]["selected-edition:verb-book"]), payload={})
    receipt = writing_tools.request(tmp_path, "verb-book", "work", request)
    assert receipt["ok"] and receipt["outcome"] == "applied"

    # Requests derived by the existing owner adapter retain their established bare project
    # target even when the concept object's id_is prose is more specific than "project".
    state = new_project("public-help-book")
    _route, help_request = writing_verbs.from_owner_call(
        "help", {}, project="public-help-book")
    assert help_request.target == "public-help-book"
    help_receipt = writing_tools.request(
        tmp_path, "public-help-book", "work", help_request)
    assert help_receipt["ok"] and help_receipt["outcome"] == "read"

    state = new_project("public-chapter-book")
    _route, chapter_request = writing_verbs.from_owner_call(
        "chapter", {"title": "A new chapter"}, project="public-chapter-book")
    assert chapter_request.target == "public-chapter-book"
    chapter_receipt = writing_tools.request(
        tmp_path, "public-chapter-book", "work", chapter_request)
    assert chapter_receipt["ok"] and chapter_receipt["outcome"] == "applied"
    chapter_file = (tmp_path / project_structure.state(
        "public-chapter-book", tmp_path)["selected_source"]["root"]).parent \
        / "chapters/a-new-chapter.tex"
    assert b"A new chapter" in chapter_file.read_bytes()

    # Canonical order is not identity semantics. The public verb path carries the reversed
    # list to the owner unchanged and its durable action remains exact in that same order.
    state = new_project("reversed-book")
    reversed_expected = (state["identities"]["selected-edition:reversed-book"],
                         state["identities"]["plan:reversed-book"])
    receipt = writing_tools.request(tmp_path, "reversed-book", "work", grammar.Request(
        verb="create", concept="plan@plan", target="reversed-book",
        expected=reversed_expected, payload={}), turn_id="WT-reversed-canonical")
    assert receipt["ok"] and receipt["banked_row"]["verb"] == "create"
    reversed_action = next(row for row in (json.loads(line) for line in
        (tmp_path / "contract/talk.jsonl").read_text().splitlines())
        if row.get("record") == "writing-tool-action"
        and row.get("turn_id") == "WT-reversed-canonical")
    reversed_action = writing_bodies.resolve_fields(
        reversed_action, tmp_path, strict=True)
    assert reversed_action["dispatch"] == "exact"
    assert reversed_action["payload"]["expected"] == list(reversed_expected)

    # A current digest under another project id is not authority for this project. The
    # public Request reaches the owner gate and returns its exact cure without mutation.
    state = new_project("wrong-scope-book")
    wrong_scope_plan = str(grammar.mint("plan", "another-project", state["revision"]))
    plan = plan_path("wrong-scope-book")
    plan_before = plan.read_bytes() if plan.is_file() else None
    source_before = source_bytes("wrong-scope-book")
    refused = writing_tools.request(tmp_path, "wrong-scope-book", "work", grammar.Request(
        verb="create", concept="plan@plan", target="wrong-scope-book",
        expected=(wrong_scope_plan,
                  state["identities"]["selected-edition:wrong-scope-book"]), payload={}))
    assert refused["ok"] is False and refused["refused"]["kind"] == "unknown-home"
    assert state["identities"]["plan:wrong-scope-book"] in refused["refused"]["needed"]["expected"]
    # Exact routing preserves the owner call; the owner still refuses its scope.
    assert refused["banked_row"]["dispatch"] == "exact"
    assert (plan.read_bytes() if plan.is_file() else None) == plan_before
    assert source_bytes("wrong-scope-book") == source_before

    # The bound project and advertised request destination are one target. Valid identities
    # cannot authorize a differently advertised destination, while the documented empty
    # spelling remains valid for a whole-project act.
    state = new_project("target-book")
    plan = plan_path("target-book"); plan_before = plan.read_bytes() if plan.is_file() else None
    source_before = source_bytes("target-book")
    refused = writing_tools.request(tmp_path, "target-book", "work", grammar.Request(
        verb="create", concept="plan@plan", target="other-project",
        expected=(state["identities"]["plan:target-book"],
                  state["identities"]["selected-edition:target-book"]), payload={}))
    assert refused["ok"] is False and refused["refused"]["kind"] == "shape"
    assert refused["refused"]["needed"] == {"target": "target-book"}
    assert (plan.read_bytes() if plan.is_file() else None) == plan_before
    assert source_bytes("target-book") == source_before

    state = new_project("empty-target-book")
    accepted = writing_tools.request(tmp_path, "empty-target-book", "work", grammar.Request(
        verb="create", concept="plan@plan", target="",
        expected=(state["identities"]["plan:empty-target-book"],
                  state["identities"]["selected-edition:empty-target-book"]), payload={}))
    assert accepted["ok"] and accepted["outcome"] == "applied"

    # Equal bytes at a fabricated same-project file home cannot authorize an insertion into
    # the selected source. The refusal names the actual selected source home and current token.
    state = new_project("wrong-file-book")
    writing_tools.execute(tmp_path, "wrong-file-book", "work", "structure_change", {
        "operation": "initialize", "expected": [
            state["identities"]["plan:wrong-file-book"],
            state["identities"]["selected-edition:wrong-file-book"]]})
    state = project_structure.state("wrong-file-book", tmp_path)
    source_rel = state["selected_source"]["root"]
    source_path = tmp_path / source_rel
    source_before = source_path.read_bytes()
    plan = plan_path("wrong-file-book"); plan_before = plan.read_bytes()
    wrong_file = str(grammar.mint("source-file", "wrong-file-book::wrong-file.tex",
                                  state["selected_source"]["revision"]))
    refused = writing_tools.request(tmp_path, "wrong-file-book", "work", grammar.Request(
        verb="create", concept="heading@section", target="wrong-file-book::" + source_rel,
        expected=(state["identities"]["plan:wrong-file-book"], wrong_file),
        payload={"kind": "section", "title": "Scoped", "file": source_rel,
                 "after_line": 2, "after_before": "\\begin{document}"}))
    assert refused["ok"] is False and refused["refused"]["kind"] == "unknown-home"
    current_source = str(grammar.mint(
        "source-file", "wrong-file-book::" + source_rel,
        state["selected_source"]["revision"]))
    assert current_source in refused["refused"]["needed"]["expected"]
    assert any(row["home"] == "source-file:wrong-file-book::" + source_rel
               and row["current_token"] for row in refused["refused"]["homes"])
    assert source_path.read_bytes() == source_before and plan.read_bytes() == plan_before

    # Both spellings still reach the same owner refusal.  The canonical named call keeps
    # its home-bearing token; the verb door restores the owner's legacy digest spelling.
    refusals = []
    for name, via_verb in (("named-refusal-book", False), ("verb-refusal-book", True)):
        state = new_project(name)
        stale_plan = state["identities"][f"plan:{name}"][:-1] + (
            "0" if state["identities"][f"plan:{name}"][-1] != "0" else "1")
        expected = (stale_plan, state["identities"][f"selected-edition:{name}"])
        payload = {"operation": "initialize", "expected": list(expected)}
        if via_verb:
            route = writing_verbs.choose("create", "plan@plan", {})
            _operation, payload = writing_verbs.to_owner_call(grammar.Request(
                verb="create", concept="plan@plan", target=name, expected=expected,
                payload={}), route=route)
        with pytest.raises(identity_doors.IdentityRefused) as caught:
            project_structure.change(name, payload, tmp_path)
        refusals.append(caught.value)
        assert caught.value.refused["kind"] == "identity-stale"
        assert caught.value.refused["needed"]["expected"] == [
            state["identities"][f"plan:{name}"]]
    assert str(refusals[0]) == str(refusals[1])

    # The existing public HTTP adapter accepts the canonical spelling too.
    state = new_project("http-book")
    source_before = source_bytes("http-book")
    help_value = writing_tools.execute(tmp_path, "http-book", "work", "help", {
        "operation": "structure_change", **({"variant": variant} if variant else {})})["action"]
    body = {"project": "http-book", **help_value["example"]}
    code, _, raw = project_work_surface.handle(
        "/work/structure/change", {}, "POST", json.dumps(body).encode(), repo_root=tmp_path)
    assert code == 200 and json.loads(raw)["state"]["status"] == "AVAILABLE"
    assert source_bytes("http-book") == source_before

    # Legacy fields remain valid only with their historical bare owner values.
    state = new_project("legacy-book")
    legacy = project_structure.change("legacy-book", {"operation": "initialize",
        "expected_revision": state["revision"],
        "expected_source_revision": state["selected_source"]["revision"]}, tmp_path)
    assert legacy["ok"]

    # Typed tokens under legacy fields reproduce the paid-smoke refusal and write nothing.
    state = new_project("typed-legacy-book"); before = source_bytes("typed-legacy-book")
    plan = plan_path("typed-legacy-book")
    plan_before = plan.read_bytes() if plan.is_file() else None
    with pytest.raises(identity_doors.IdentityRefused) as caught:
        project_structure.change("typed-legacy-book", {"operation": "initialize",
            "expected_revision": state["identities"]["plan:typed-legacy-book"],
            "expected_source_revision": state["identities"][
                "selected-edition:typed-legacy-book"]}, tmp_path)
    assert caught.value.refused["kind"] == "shape"
    assert caught.value.refused["needed"]["expected"] == [
        state["identities"]["plan:typed-legacy-book"]]
    assert caught.value.refused["needed_old_names"]["expected_revision"] == \
        state["revision"].removeprefix("sha256:")
    assert (plan.read_bytes() if plan.is_file() else None) == plan_before
    assert source_bytes("typed-legacy-book") == before

    # Stale, wrong-home, wrong-project and malformed canonical identities all refuse
    # with the current recoverable token and no plan/source write.
    for suffix, mutate in (
        ("stale", lambda plan_token, source_token: [plan_token[:-1] + (
            "0" if plan_token[-1] != "0" else "1"), source_token]),
        ("wrong-home", lambda plan_token, source_token: [source_token]),
        ("wrong-project", lambda plan_token, source_token: [
            plan_token.replace("plan:wrong-project-book:", "plan:another-project:", 1),
            source_token]),
        ("malformed", lambda plan_token, source_token: ["not-a-token", source_token]),
        ("stale-source", lambda plan_token, source_token: [plan_token,
            source_token[:-1] + ("0" if source_token[-1] != "0" else "1")]),
    ):
        name = "wrong-project-book" if suffix == "wrong-project" else suffix + "-book"
        state = new_project(name); before = source_bytes(name)
        current_plan_path = plan_path(name)
        plan_before = current_plan_path.read_bytes() if current_plan_path.is_file() else None
        expected = mutate(state["identities"][f"plan:{name}"],
                          state["identities"][f"selected-edition:{name}"])
        if suffix in {'wrong-home', 'malformed'}:
            with pytest.raises(writing_declarations.PayloadAdmissionError):
                writing_tools.execute(tmp_path, name, 'work', 'structure_change',
                                      {'operation': 'initialize', 'expected': expected})
        else:
            with pytest.raises(identity_doors.IdentityRefused) as caught:
                writing_tools.execute(tmp_path, name, "work", "structure_change",
                                      {"operation": "initialize", "expected": expected})
            assert caught.value.refused["kind"] in {"shape", "identity-stale", "unknown-home"}
            assert (caught.value.refused["needed"].get("expected")
                    or caught.value.refused["needed"].get("unresolved"))
        assert (current_plan_path.read_bytes() if current_plan_path.is_file() else None) == plan_before
        assert source_bytes(name) == before

    # D1/D-R1 (2026-10-15) replaces SI-C1's compatibility: an empty canonical `expected` is malformed
    # presence at this required-guard owner, alone or beside valid legacy guards. The public schema and
    # the owner's own entry refuse both before any plan or source read; legacy guards alone still write.
    state = new_project("empty-only-book"); before = source_bytes("empty-only-book")
    schema = writing_declarations.variants("structure_change")["initialize"]
    empty_only = {"operation": "initialize", "expected": []}
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(empty_only))
    empty_plan = plan_path("empty-only-book")
    plan_before = empty_plan.read_bytes() if empty_plan.is_file() else None
    with pytest.raises(identity_doors.IdentityRefused, match="canonical guard is malformed"):
        project_structure.change("empty-only-book", empty_only, tmp_path)
    assert (empty_plan.read_bytes() if empty_plan.is_file() else None) == plan_before
    assert source_bytes("empty-only-book") == before

    state = new_project("empty-legacy-book"); before = source_bytes("empty-legacy-book")
    legacy = {"expected_revision": state["revision"], "expected_source_revision": state["selected_source"]["revision"]}
    empty_plus_legacy = {"operation": "initialize", "expected": [], **legacy}
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(empty_plus_legacy))
    legacy_plan = plan_path("empty-legacy-book")
    plan_before = legacy_plan.read_bytes() if legacy_plan.is_file() else None
    with pytest.raises(identity_doors.IdentityRefused, match="canonical guard is malformed"):
        project_structure.change("empty-legacy-book", empty_plus_legacy, tmp_path)
    assert (legacy_plan.read_bytes() if legacy_plan.is_file() else None) == plan_before
    assert source_bytes("empty-legacy-book") == before
    jsonschema.Draft202012Validator(schema).validate({"operation": "initialize", **legacy})
    compatible = project_structure.change("empty-legacy-book", {"operation": "initialize", **legacy}, tmp_path)
    assert compatible["ok"] and compatible["state"]["status"] == "AVAILABLE"


def test_wrapped_canonical_refusal_is_identical_through_named_verb_and_provider_paths(tmp_path):
    from laplace.core import grammar as g, identity_doors
    from laplace.native import tools as writing_tools, verbs as writing_verbs
    from laplace.writing import operations
    _fixture(tmp_path)
    token = g.identity(g.Home('concept-network', 'book'), project='book', root=tmp_path)
    wrong = str(g.mint(token.kind, 'other-project', token.digest))
    payload = {'operation': 'add_node', 'node': 'claim:new',
               'node_kind': 'result', 'essence': 'Must not be created.', 'expected': [wrong]}
    before = _hashes(tmp_path)
    with pytest.raises(operations.OwnerError) as caught:
        writing_tools.execute(tmp_path, 'book', 'work', 'concept_change', payload)
    original = caught.value.details['refused']
    assert original['kind'] == 'unknown-home'
    route = writing_verbs.route_for_operation('concept_change', payload)
    request = g.Request(verb=route.verb, concept=route.concept,
                        target=writing_verbs.target_for('book', route.concept, payload),
                        expected=(wrong,), payload={k: v for k, v in payload.items()
                                                   if k not in ('operation', 'expected')})
    result = writing_tools.request(tmp_path, 'book', 'work', request)
    assert result['ok'] is False
    assert {k: v for k, v in result['refused'].items() if k != 'owner'} == original
    response = writing_tools.failure_response(tmp_path, 'book', 'work',
                                              'concept_change', payload, caught.value)
    assert response['refused'] == original
    outer = RuntimeError('transport wrapper')
    outer.__cause__ = caught.value
    assert identity_doors.body(outer)['refused'] == original
    assert _hashes(tmp_path) == before


def test_validated_workspace_context_selects_node_owner_and_is_receipted(tmp_path, monkeypatch):
    _fixture(tmp_path)
    from laplace.writing import turn_admission
    from laplace.writing import turn_jobs
    from laplace.writing import session_reads
    prompts = []

    class _Provider:
        def __init__(self, *args, **kwargs): pass
        def run(self, prompt):
            prompts.append(prompt); return {"status": "completed", "text": "Viewed."}

    monkeypatch.setattr(writing_provider, "WritingTurn", _Provider)
    started = turn_admission.start_turn(tmp_path, {"project": "book", "provider": "codex",
        "mode": "discuss", "text": "Explain this node.",
        "workspace_context": {"surface": "structure", "node_id": "res:one"}})
    job = turn_jobs._JOBS[started["turn_id"]]
    with job["condition"]:
        assert job["condition"].wait_for(lambda: job["done"], timeout=5)
    turn = session_reads.session_state(tmp_path, started["session_id"])["turns"][0]
    assert turn["workspace_context"] == {"surface": "structure", "node_id": "res:one",
                                          "node_ids": [], "label": None,
                                          "beat_id": None, "section_ids": ["N1"]}
    assert [section["id"] for section in turn["dependencies"]["structure"]["sections"]] == ["N1"]
    assert '"surface": "structure"' in prompts[0] and '"node_id": "res:one"' in prompts[0]


def test_large_canonical_group_preserves_all_ids_with_bounded_explicit_previews(tmp_path):
    _fixture(tmp_path)
    ids=[]
    for index in range(85):
        ident=f'def:group-{index:03d}';ids.append(ident)
        assert corpus_ingest.rewire_add(tmp_path,'book',{'kind':'add-node','node':ident,
            'node_kind':'definition','essence':f'Group member {index}','parent':'paper://',
            'by':'fixture'}).get('ok')
    workspace=turn_context._workspace_context(tmp_path,'book',{
        'surface':'structure','node_ids':ids,'label':'All group members'})
    assert workspace['node_ids']==ids
    scoped=project_structure.context('book',{'node_ids':ids},tmp_path)
    assert scoped['selected_node_ids']==ids and scoped['selected_nodes_total']==85
    assert len(scoped['selected_nodes'])==40 and scoped['selected_nodes_omitted']==45
    assert scoped['source_support_total']==85 and scoped['source_support_omitted']==45
    assert scoped['selected_node_read_routes']['concept']['payload']['node']=='<selected_node_id>'
    context=authoring.build_context('book',{'node_ids':ids},repo_root=tmp_path,
                                    include_guidance=False,include_orientation=False)
    assert '"selected_nodes_total": 85' in context['prompt']
    assert '"selected_nodes_omitted": 45' in context['prompt']
    with pytest.raises(ValueError,match='at most 500'):
        turn_context._workspace_context(tmp_path,'book',{
            'surface':'structure','node_ids':ids*6,'label':'Too many'})


def test_section_id_source_read_banks_exact_file_scope_for_proposal_preflight(tmp_path):
    _fixture(tmp_path)
    from laplace.manuscript import proposal_preflight
    from laplace.native import tools as writing_tools
    writing_records.bank(tmp_path,{'record':'writing-session','id':'WS-section-source',
        'project':'book','provider':'codex','model':'','effort':'low'})
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-section-source',
        'session_id':'WS-section-source','project':'book','mode':'work','selection':{}})
    read=writing_tools.execute(tmp_path,'book','work','source',{'section_ids':['N1']},
                               turn_id='WT-section-source')
    assert [Path(row['file']).name for row in read['sources']]==['N1.tex']
    turn=session_reads._records(tmp_path)['turns']['WT-section-source']
    source_read=next(row for row in turn['tool_reads'].values() if row['operation']=='source')
    assert [Path(row['file']).name for row in source_read['source_scope']]==['N1.tex']
    checked=proposal_preflight.preflight(tmp_path,'book',turn,{'answer':'','edits':[{
        'file':'N1.tex','line_start':2,'line_end':2,'before':'Opening prose.',
        'after':'Opening prose, now qualified.','reason':'Use the consumed section.'}]})
    assert checked['valid'],checked['errors']

    with pytest.raises(ValueError, match="unavailable canonical concept node"):
        turn_admission.start_turn(tmp_path, {"project": "book", "provider": "codex",
            "mode": "discuss", "text": "Invent context.",
            "workspace_context": {"surface": "structure", "node_id": "res:missing"}})


def test_unplanned_canonical_node_context_carries_typed_neighborhood_and_stales(tmp_path, monkeypatch):
    _fixture(tmp_path)
    from laplace.writing import turn_admission
    from laplace.writing import turn_jobs
    from laplace.writing import session_reads
    prompts = []
    class _Provider:
        def __init__(self, *args, **kwargs): pass
        def run(self, prompt): prompts.append(prompt); return {"status": "completed", "text": "Focused."}
    monkeypatch.setattr(writing_provider, "WritingTurn", _Provider)

    started = turn_admission.start_turn(tmp_path, {"project": "book", "provider": "codex",
        "mode": "discuss", "text": "Develop this concept.",
        "workspace_context": {"surface": "structure", "node_id": "def:unplanned"}})
    job = turn_jobs._JOBS[started["turn_id"]]
    with job["condition"]:
        assert job["condition"].wait_for(lambda: job["done"], timeout=5)
    turn = session_reads.session_state(tmp_path, started["session_id"])["turns"][0]
    structure = turn["dependencies"]["structure"]
    assert structure["sections"] == []
    assert structure["focus"]["node"]["id"] == "def:unplanned"
    assert structure["focus"]["edges"][0]["target"] == "res:one"
    assert "Unplanned concept" in prompts[0]

    corpus_ingest.rewire_add(tmp_path, "book", {"kind": "edit-essence",
        "node": "def:unplanned", "value": "Changed unplanned concept", "by": "author"})
    stale = authoring.inspect("book", repo_root=tmp_path)["stale"]
    row = next(item for item in stale if item["context_id"] == turn["context_id"])
    assert "structure-plan-conceptric-or-evidence-changed" in row["reasons"]


def test_focused_math_context_uses_authoritative_record_and_named_prerequisite_source(tmp_path):
    """A node-only scope still receives its own premise and exact external source."""
    _fixture(tmp_path)
    sources = tmp_path / "original"
    sources.mkdir()
    (tmp_path / "profiles").mkdir()
    (tmp_path / "profiles" / "writing_sources.json").write_text(
        json.dumps({"repositories": {"original": "original"}}), encoding="utf-8")
    law = sources / "law.tex"
    law.write_text(
        "\\begin{theorem}\\label{thm:goal}Goal statement.\\end{theorem}\n"
        "\\begin{proof}Goal proof.\\end{proof}\n"
        "\\begin{theorem}\\label{thm:axiom}Axiom evidence one.\\end{theorem}\n",
        encoding="utf-8")

    revision = concepts_surface.state("book", root=tmp_path)["revision"]
    for node, kind, essence, ref in (
        ("thm:goal", "theorem", "Goal statement", "original:law.tex#thm:goal"),
        ("thm:axiom", "theorem", "Axiom statement", "original:law.tex#thm:axiom"),
    ):
        status, changed = concepts_surface.change({"project": "book", "operation": "add_node",
            "node": node, "node_kind": kind, "essence": essence, "parent": "paper://",
            "ref": ref, "base_revision": revision}, root=tmp_path)
        assert status == 200, changed
        revision = changed["state"]["revision"]
    status, changed = concepts_surface.change({"project": "book", "operation": "add_edge",
        "node": "thm:goal", "target": "thm:axiom", "rel": "prerequisite",
        "base_revision": revision}, root=tmp_path)
    assert status == 200, changed

    scope = {"node_id": "thm:goal"}
    structure = project_structure.context("book", scope, tmp_path)
    assert structure["sections"] == []
    assert structure["focus"]["mathematical_record"]["node"] == "thm:goal"
    assert [(row["id"], row["required_by"], row["relation"])
            for row in structure["direct_dependencies"]] == [("thm:axiom", "thm:goal", "prerequisite")]

    first = authoring.build_context("book", scope, tmp_path)
    assert "Axiom evidence one." in first["prompt"]
    assert first["prompt"].count("Axiom evidence one.") == 1
    assert first["prompt"].count("Goal statement.") == 1
    assert "original:law.tex#thm:goal" in first["prompt"]

    law.write_text(law.read_text(encoding="utf-8").replace("Axiom evidence one.", "Axiom evidence two."),
                   encoding="utf-8")
    second = authoring.build_context("book", scope, tmp_path)
    assert first["science_context_digest"] != second["science_context_digest"]
    assert "Axiom evidence two." in second["prompt"]


def test_declared_proposal_basis_uses_placed_node_snapshot_not_whole_graph_revision(tmp_path):
    _fixture(tmp_path)
    from laplace.manuscript import proposal_basis, proposal_preflight
    current = concepts_surface.state("book", node="res:one", root=tmp_path)
    edit = {"file": "N1.tex", "line_start": 2, "line_end": 2,
            "before": "Opening prose.", "after": "A source-backed opening.", "reason": "Develop the result.",
            "develops": [{"id": "res:one", "content_revision": current["content_revision"]}]}
    basis = proposal_basis.assess(tmp_path, "book", edit)
    assert basis["status"] == "DECLARED"
    assert {row["id"] for row in basis["automatic_section_concepts"]} == {"res:one", "def:one"}
    turn = {"selection": {"files": ["N1.tex"]}, "dependencies": {}, "tool_reads": {}}
    assert proposal_preflight.preflight(tmp_path, "book", turn, {"answer": "", "edits": [edit]})["valid"]

    corpus_ingest.rewire_add(tmp_path, "book", {"kind": "edit-essence", "node": "res:two",
        "value": "An unrelated changed result", "by": "fixture"})
    assert proposal_preflight.preflight(tmp_path, "book", turn, {"answer": "", "edits": [edit]})["valid"]

    corpus_ingest.rewire_add(tmp_path, "book", {"kind": "edit-essence", "node": "res:one",
        "value": "The placed result changed", "by": "fixture"})
    invalid = proposal_preflight.preflight(tmp_path, "book", turn, {"answer": "", "edits": [edit]})
    assert not invalid["valid"] and "develops concept changed: res:one" in invalid["errors"][0]


def test_empty_response_schema_arrays_do_not_claim_a_declared_scientific_basis(tmp_path):
    _fixture(tmp_path)
    from laplace.manuscript import proposal_basis
    editorial = {"file": "N1.tex", "line_start": 2, "line_end": 2,
                 "before": "Opening prose.", "after": "Opening sentence.",
                 "develops": [], "evidence_refs": []}
    basis = proposal_basis.assess(tmp_path, "book", editorial)
    assert basis["status"] == "SECTION_CONTEXT"
    assert basis["develops"] == [] and basis["evidence"] == []
    assert basis["automatic_section_concepts"]


def test_proposal_basis_maps_nested_same_file_sections_by_edit_line(tmp_path):
    manuscript = _fixture(tmp_path)
    source = manuscript / "N1.tex"
    source.write_text("\\chapter{Opening}\\label{source-opening}\nOpening prose.\n\\section{Inner  title}\\label{source-inner}\nInner prose.\n", encoding="utf-8")
    plan_path = manuscript / "projection_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["sections"][0].update(kind="chapter", source_file="book/manuscript/N1.tex")
    plan["sections"].insert(1, {"id": "inner", "title": "Inner title", "kind": "section", "parent_id": "N1",
        "source_file": "book/manuscript/N1.tex", "source_label": "source-inner", "job": "Develop the inner claim.",
        "beats": [], "nodes_in_order": ["def:one"], "refs": []})
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    from laplace.manuscript import proposal_basis

    inner = proposal_basis.assess(tmp_path, "book", {"file": "book/manuscript/N1.tex", "line_start": 4, "line_end": 4})
    assert [row["id"] for row in inner["automatic_sections"]] == ["inner"]
    assert {row["id"] for row in inner["automatic_section_concepts"]} == {"def:one"}
    attention=project_structure.context('book',{'files':['N1.tex'],'line_start':4,'line_end':4},tmp_path)
    assert [section['id'] for section in attention['sections']]==['inner']
    assert attention['focus'] is None

    chapter = proposal_basis.assess(tmp_path, "book", {"file": "N1.tex", "line_start": 1, "line_end": 4})
    assert [row["id"] for row in chapter["automatic_sections"]] == ["N1", "inner"]

    selection = {"files": ["N1.tex"], "line_start": 4, "line_end": 4}
    context = authoring.build_context("book", selection, repo_root=tmp_path)
    assert [row["id"] for row in context["consumed"]["structure"]["sections"]] == ["inner"]
    # Revalidation must not silently widen a passage to every section sharing its
    # file and immediately declare its freshly created context stale.
    current = authoring.inspect("book", selection, repo_root=tmp_path)
    assert context["context_id"] not in {row["context_id"] for row in current["stale"]}


def test_accepted_declared_links_are_read_back_only_while_after_text_is_unique(tmp_path):
    _fixture(tmp_path)
    from laplace.manuscript import proposal_basis, manuscript_source
    from laplace.writing import records as writing_records
    from laplace.writing.records import _fold as records_fold
    path = tmp_path / "book/manuscript/N1.tex"
    path.write_text("\\chapter{Opening}\\label{source-opening}\nOpening prose.\n", encoding="utf-8")
    plan_path = tmp_path / "book/manuscript/projection_plan.json"
    plan = json.loads(plan_path.read_text())
    plan["sections"][0].update(source_file="book/manuscript/N1.tex", source_label="source-opening")
    plan_path.write_text(json.dumps(plan))
    records_fold._CACHE.clear()
    writing_records.bank(tmp_path, {"record": "writing-session", "id": "WS-links", "project": "book",
        "provider": "codex", "model": "", "effort": "low"})
    writing_records.bank(tmp_path, {"record": "writing-turn", "id": "WT-links", "session_id": "WS-links",
        "project": "book", "mode": "revise",
        "document": manuscript_source.resolve("book",repo_root=tmp_path)})
    revision = concepts_surface.state("book", node="res:one", root=tmp_path)["content_revision"]
    edit = {"file": "N1.tex", "line_start": 2, "line_end": 2, "before": "Opening prose.",
        "after": "Opening prose.", "develops": [{"id": "res:one", "content_revision": revision}]}
    writing_records.bank(tmp_path, {"record": "writing-application", "id": "WA-links", "turn_id": "WT-links",
        "project": "book", "complete": True, "edits": [edit]})
    links = proposal_basis.accepted_links(tmp_path, "book")["links"]
    assert links[0]["status"] == "LIVE_CURRENT_BASIS" and links[0]["develops"][0]["id"] == "res:one"
    corpus_ingest.rewire_add(tmp_path, "book", {"kind": "edit-essence", "node": "res:one",
        "value": "Changed concept", "by": "fixture"})
    assert proposal_basis.accepted_links(tmp_path, "book")["links"][0]["status"] == "LIVE_TEXT_STALE_BASIS"
    path = tmp_path / "book/manuscript/N1.tex"
    path.write_text("\\chapter{Opening}\nChanged.\n", encoding="utf-8")
    assert proposal_basis.accepted_links(tmp_path, "book")["links"][0]["status"] == "STALE_OR_AMBIGUOUS"


def test_internal_node_context_consumes_bounded_descendants_and_apply_stales_on_nested_edit_and_move(
        tmp_path, monkeypatch):
    manuscript = _fixture(tmp_path)
    from laplace.research import concepts as concepts_surface
    from laplace.manuscript import review_surface
    from laplace.writing import records as writing_records
    from laplace.writing.records import _fold as records_fold
    from laplace.writing import turn_jobs
    from laplace.manuscript import source_application
    from laplace.writing import session_reads
    for payload in ({"kind":"add-node","node":"def:nested","node_kind":"definition",
                     "essence":"Nested definition","parent":"res:one","ref":"N1.tex#nested"},
                    {"kind":"add-node","node":"res:deep","node_kind":"result",
                     "essence":"Deep result","parent":"def:nested","ref":"N1.tex#deep"}):
        result=corpus_ingest.rewire_add(tmp_path,"book",{**payload,"by":"author"})
        assert result.get("ok"),result
    selection={"files":["N1.tex"],"node_id":"res:one"}
    context=authoring.build_context("book",selection,tmp_path)
    focus=context["consumed"]["structure"]["focus"]
    contained=focus["containment"]
    assert focus["node"]["summary"]=="First result"
    assert [(row["id"],row["depth"],row["parent"]) for row in contained["descendants"]]==[
        ("def:nested",1,"res:one"),("res:deep",2,"def:nested")]
    assert contained["identity_chain"]==[]
    assert contained["omission_residual"]["complete"] is True
    assert '"id": "def:nested"' in context["prompt"]
    assert "Nested definition" not in context["prompt"] and "Deep result" not in context["prompt"]
    assert '"operation": "concept_tree"' in context["prompt"]
    bounded=concepts_surface.focus_projection("book","res:one",tmp_path,max_nodes=2,max_depth=1)
    assert bounded["omission_residual"]["complete"] is False
    assert bounded["omission_residual"]["known_children_beyond_depth"]==1
    assert bounded["omission_residual"]["deeper_descendant_count_unknown"] is True

    records_fold._CACHE.clear();turn_jobs._JOBS.clear()
    writing_records.bank(tmp_path,{"record":"writing-session","id":"WS-nested",
        "project":"book","provider":"codex","model":"","effort":"medium"})
    writing_records.bank(tmp_path,{"record":"writing-turn","id":"WT-nested",
        "session_id":"WS-nested","project":"book","text":"Revise parent scope","mode":"revise",
        "selection":selection,"context_id":context["context_id"],
        "dependencies":context["dependencies"],"document":context["document"]})
    writing_records.bank(tmp_path,{"record":"writing-reply","id":"WR-nested",
        "turn_id":"WT-nested","session_id":"WS-nested","project":"book","status":"completed",
        "proposal":{"answer":"proposal","edits":[{"file":"N1.tex","line_start":2,"line_end":2,
            "before":"Opening prose.","after":"Changed opening.","reason":"explain nested result"}]}})
    source_before=(manuscript/"N1.tex").read_text()
    edited=corpus_ingest.rewire_add(tmp_path,"book",{"kind":"edit-essence","node":"res:deep",
        "value":"Deep result changed below the parent","by":"author"})
    assert edited.get("ok")
    live=project_structure.focused_node("book","res:one",tmp_path)
    assert live["node"]["summary"]=="First result"
    assert live["revision"]!=focus["revision"]
    stale=authoring.inspect("book",repo_root=tmp_path)["stale"]
    assert "structure-plan-conceptric-or-evidence-changed" in next(
        row for row in stale if row["context_id"]==context["context_id"])["reasons"]
    monkeypatch.setattr(review_surface,"adjudicate",
                        lambda *args,**kwargs:pytest.fail("stale nested proposal wrote source"))
    with pytest.raises(ValueError,match="changed"):
        source_application.apply_proposal(tmp_path,{"turn_id":"WT-nested","proposal_version":session_reads.session_turn_detail(tmp_path,"book","WT-nested","turn")["turn"]["proposal_version"]})
    assert (manuscript/"N1.tex").read_text()==source_before

    moved_context=authoring.build_context("book",selection,tmp_path)
    moved=corpus_ingest.rewire_add(tmp_path,"book",{"kind":"move-node","node":"res:deep",
        "target":"res:one","by":"author"})
    assert moved.get("ok")
    moved_stale=authoring.inspect("book",repo_root=tmp_path)["stale"]
    assert "structure-plan-conceptric-or-evidence-changed" in next(
        row for row in moved_stale if row["context_id"]==moved_context["context_id"])["reasons"]


def test_concept_tool_cannot_claim_author_origin(tmp_path):
    _fixture(tmp_path)
    from laplace.research import concepts as concepts_surface
    from laplace.native import tools as writing_tools
    revision = concepts_surface.state("book", root=tmp_path)["revision"]
    writing_tools.execute(tmp_path, "book", "work", "concept_change", {
        "operation": "edit_node", "node": "def:unplanned",
        "essence": "Session-authored change", "base_revision": revision, "by": "author"},
        turn_id="WT-concept")
    rows = corpus_ingest.rewire_list(tmp_path, "book")
    assert rows[-1]["by"] == "eigen:session"

    revision = concepts_surface.state("book", root=tmp_path)["revision"]
    with pytest.raises(ValueError, match="cannot award"):
        writing_tools.execute(tmp_path, "book", "work", "concept_change", {
            "operation": "set_status", "node": "res:one", "value": "proven",
            "base_revision": revision, "by": "author"}, turn_id="WT-status")


def test_spine_reorder_requires_exact_live_permutation(tmp_path):
    _fixture(tmp_path)
    from laplace.manuscript import storyboard
    before = len(corpus_ingest.rewire_list(tmp_path, "book"))
    guard = project_structure.state("book", tmp_path)["authority"]["spine_revision"]
    refused = storyboard.spine_write("book", {"kind": "reorder-spine",
        "order": ["res:one", "res:one"], "expected_spine_revision": guard}, repo_root=tmp_path)
    assert refused["ok"] is False and "exact duplicate-free permutation" in refused["error"]
    assert len(corpus_ingest.rewire_list(tmp_path, "book")) == before
    accepted = storyboard.spine_write("book", {"kind": "reorder-spine",
        "order": ["res:two", "res:one"], "expected_spine_revision": guard}, repo_root=tmp_path)
    assert accepted["ok"] is True
    assert [beat["id"] for beat in corpus_ingest.corpus_network(
        corpus_ingest.resolve_corpus(tmp_path, "book"), repo_root=tmp_path,
        name="book")["spine"]] == ["res:two", "res:one"]


def test_plan_with_failed_required_mirror_is_explicitly_pending_and_ineligible(tmp_path, monkeypatch):
    _fixture(tmp_path)
    current = project_structure.state("book", tmp_path)
    real = corpus_ingest.rewire_add
    def fail_mirror(root, project, payload):
        if payload.get("kind") == "set-projection" and payload.get("by") == "storyboard":
            return {"error": "fixture mirror refused"}
        return real(root, project, payload)
    monkeypatch.setattr(corpus_ingest, "rewire_add", fail_mirror)

    result = project_structure.change("book", {"operation": "plan",
        "expected_revision": current["revision"],
        "op": {"kind": "move-node", "node": "res:two", "from": "N2", "to": "N1"}}, tmp_path)

    assert result["ok"] is False and result["status"] == "MIRROR_PENDING"
    assert result["state"]["eligible_for_authoring"] is False
    scoped = project_structure.context("book", {"section_ids": ["N1"]}, tmp_path)
    assert scoped["eligible_for_authoring"] is False
    assert any(gap["kind"] == "mirror" and gap["id"] == "res:two"
               for gap in result["state"]["gaps"])

    from laplace.manuscript import review_surface
    from laplace.writing import turn_admission
    from laplace.writing import turn_jobs
    from laplace.manuscript import source_application
    from laplace.writing import session_reads

    monkeypatch.setattr(corpus_ingest, "rewire_add", real)
    repaired = project_structure.change("book", {"operation": "reconcile",
        "expected_revision": result["revision"]}, tmp_path)
    assert repaired["ok"] is True and repaired["state"]["eligible_for_authoring"] is True

    class _Provider:
        def __init__(self, *args, **kwargs): pass
        def run(self, prompt):
            return {"status": "completed", "text": "Proposed.", "proposal": {"answer": "Proposed.",
                "edits": [{"file": "N1.tex", "line_start": 2, "line_end": 2,
                           "before": "Opening prose.", "after": "Revised opening prose.",
                           "reason": "fixture"}]}}
    monkeypatch.setattr(writing_provider, "WritingTurn", _Provider)
    monkeypatch.setattr(review_surface, "_repo_root", lambda: tmp_path)
    started = turn_admission.start_turn(tmp_path, {"project": "book", "provider": "codex",
        "mode": "revise", "text": "Revise after repair.",
        "selection": {"files": ["N1.tex"], "section_ids": ["N1"]}})
    job = turn_jobs._JOBS[started["turn_id"]]
    with job["condition"]:
        assert job["condition"].wait_for(lambda: job["done"], timeout=5)
    applied = source_application.apply_proposal(tmp_path, {"turn_id": started["turn_id"], "proposal_version": session_reads.session_turn_detail(tmp_path,"book",started["turn_id"],"turn")["turn"]["proposal_version"], "project": "book"})
    assert applied["complete"] is True
    assert "Revised opening prose." in (tmp_path / "book/manuscript/N1.tex").read_text()
