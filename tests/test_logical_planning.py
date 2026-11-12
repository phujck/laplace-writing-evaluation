from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.research import concepts as concepts_surface, corpus_ingest
from laplace.manuscript import project_structure
from laplace.native import tools as writing_tools


def _fixture(root: Path, *, placed: bool = False) -> Path:
    manuscript = root / "logic" / "manuscript"
    manuscript.mkdir(parents=True)
    (root / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "logic", "project_dir": "logic", "tex_root": "logic/manuscript",
        "manifest": {"document": {"root": "logic/manuscript/main.tex"}},
    }]}))
    (manuscript / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n\\end{document}\n")
    plan = {"meta": {"project": "logic", "target_dir": "logic/manuscript"},
            "sections": ([{"id": "S1", "title": "Reader entry", "job": "Explain the result.",
                           "nodes_in_order": ["result:one"], "beats": [], "refs": []}]
                         if placed else []), "appendices": []}
    (manuscript / "projection_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    for ident, kind, meaning, ref in (
        ("def:one", "definition", "A quantity is admissible exactly when it is finite.",
         {"file": "main.tex", "line": 2}),
        ("premise:one", "postulate", "Assume the quantity is finite.", "main.tex#assumption"),
        ("result:one", "result", "The construction is admissible.", "main.tex#result"),
        ("evidence:negative", "support", "A boundary case violates the construction.",
         "experiment://negative"),
    ):
        result = corpus_ingest.rewire_add(root, "logic", {"kind": "add-node", "node": ident,
            "node_kind": kind, "essence": meaning, "ref": ref, "by": "fixture"})
        assert result.get("ok"), result
    return manuscript


def _change(root: Path, operation: str, **payload):
    current = concepts_surface.logical_plan("logic", root=root)
    status, result = concepts_surface.logical_plan_change({"project": "logic",
        "operation": operation, "base_revision": current["revision"], "by": "author",
        **payload}, root=root)
    assert status == 200, result
    return result


def test_no_l2_plan_still_exposes_all_logical_objects_and_exact_omissions(tmp_path):
    manuscript = _fixture(tmp_path)
    source_before = (manuscript / "main.tex").read_bytes()

    plan = concepts_surface.logical_plan("logic", root=tmp_path)
    structure = project_structure.state("logic", tmp_path)

    assert plan["reader_order"]["status"] == "UNDECLARED"
    assert plan["placed_count"] == 0 and plan["unplaced_count"] == 4
    assert plan["omission"]["objects_omitted"] == 0
    assert {row["id"] for row in plan["objects"]} == {
        "def:one", "premise:one", "result:one", "evidence:negative"}
    assert next(row for row in plan["objects"] if row["id"] == "def:one")["source_refs"] == [
        {"file": "main.tex", "line": 2}]
    assert all({"parent", "containment_grade", "members"} <= set(row)
               for row in plan["objects"])
    assert plan["containers"][0]["id"] == "paper://"
    assert plan["containers_omitted"] == 0
    assert {row["id"] for row in structure["unplaced_nodes"]} == {
        "def:one", "premise:one", "result:one", "evidence:negative"}
    assert (manuscript / "main.tex").read_bytes() == source_before


def test_attention_follows_a_premise_beyond_the_broad_plan_page(tmp_path):
    _fixture(tmp_path)
    for index in range(205):
        result = corpus_ingest.rewire_add(tmp_path, "logic", {
            "kind": "add-node", "node": f"premise:{index:03}",
            "node_kind": "postulate", "essence": f"Z premise {index:03}", "by": "fixture"})
        assert result.get("ok"), result
    _change(tmp_path, "connect", source="result:one", target="premise:204",
            relation="prerequisite", rationale="The conclusion needs this premise.")
    _change(tmp_path, "add_obligation", node="question:late-premise",
            meaning="Does the last premise hold?",
            target={"kind": "relation", "source": "result:one",
                    "target": "premise:204", "rel": "prerequisite"},
            work_kind="research", discharge_condition="Establish the final premise.")
    context = concepts_surface.logical_plan_context("logic", "result:one", root=tmp_path)
    objects = {row["id"]: row for row in context["objects"]}
    assert objects["premise:204"]["meaning"] == "Z premise 204"
    assert context["objects"][0]["id"] == "result:one"
    assert len(objects) <= 24
    assert "question:late-premise" in objects
    assert context["obligations"][0]["id"] == "question:late-premise"


def test_readable_argument_uses_typed_premises_support_counterevidence_and_placement(tmp_path):
    _fixture(tmp_path, placed=True)
    _change(tmp_path, "connect", source="result:one", target="premise:one",
            relation="prerequisite", rationale="The result uses the finiteness assumption.")
    _change(tmp_path, "connect", source="result:one", target="def:one", relation="support",
            rationale="The definition fixes the meaning of admissible.")
    _change(tmp_path, "connect", source="result:one", target="evidence:negative",
            relation="counterevidence", rationale="The boundary case challenges universality.")

    plan = concepts_surface.logical_plan("logic", focus="result:one", root=tmp_path)
    result = plan["selected"]
    assert result["placed"] is True and result["placements"][0]["id"] == "S1"
    assert [row["target"] for row in result["premises"]] == ["premise:one"]
    assert result["premises"][0]["rationale"] == "The result uses the finiteness assumption."
    assert [row["target"] for row in result["support"]] == ["def:one"]
    assert [row["target"] for row in result["counterevidence"]] == ["evidence:negative"]
    assert result["premises"][0]["inferential"] is True
    assert result["counterevidence"][0]["inferential"] is False
    assert {row["id"] for row in plan["objects"] if not row["placed"]} == {
        "def:one", "premise:one", "evidence:negative"}
    relation_question = _change(tmp_path, "add_obligation", node="question:inference",
        meaning="Is the premise sufficient for this inference?",
        target={"kind": "relation", "source": "result:one", "target": "premise:one",
                "rel": "prerequisite"}, work_kind="formal",
        discharge_condition="A derivation justifies the exact prerequisite relation.")
    obligation = next(row for row in relation_question["state"]["obligations"]
                      if row["id"] == "question:inference")
    assert obligation["target"]["kind"] == "relation" and obligation["issue"] is None


def test_source_identity_cannot_be_saved_as_a_logical_premise(tmp_path):
    _fixture(tmp_path)
    made = _change(tmp_path, "add_object", node="citation:paper", kind="citation",
                   meaning="The historical paper's source identity.")
    status, result = concepts_surface.logical_plan_change({"project": "logic",
        "operation": "connect", "base_revision": made["state"]["revision"],
        "source": "result:one", "target": "citation:paper", "relation": "prerequisite",
        "rationale": "This is where the proof is printed."}, root=tmp_path)
    assert status == 422 and "source identity" in result["error"]
    assert concepts_surface.logical_plan("logic", root=tmp_path)["revision"] == made["state"]["revision"]


def test_obligation_has_stable_identity_target_owner_and_resolution_safeguard(tmp_path):
    _fixture(tmp_path)
    created = _change(tmp_path, "add_obligation", node="question:boundary",
        meaning="Does the boundary case invalidate the result?",
        target={"kind": "node", "node_id": "result:one"}, work_kind="computation",
        discharge_condition="A banked boundary run supports or refutes the result.")
    assert created["record"]["kind"] == "add-node"
    plan = created["state"]
    question = next(row for row in plan["obligations"] if row["id"] == "question:boundary")
    assert question["state"] == "open" and question["target"]["node_id"] == "result:one"
    assert question["verification"] == "NOT_ESTABLISHED_BY_DISPOSITION"
    assert any(row["rel"] == "questions" and row["inferential"] is False
               for row in plan["selected"]["relations"])

    before = len(corpus_ingest.rewire_list(tmp_path, "logic"))
    status, refused = concepts_surface.logical_plan_change({"project": "logic",
        "operation": "update_obligation", "base_revision": plan["revision"],
        "node": "question:boundary", "state": "addressed"}, root=tmp_path)
    assert status == 422 and "require evidence" in refused["error"]
    assert len(corpus_ingest.rewire_list(tmp_path, "logic")) == before

    updated = _change(tmp_path, "update_obligation", node="question:boundary",
        state="addressed", evidence=["run://boundary-001"],
        disposition="The run supplies the requested boundary value.")
    obligation = next(row for row in updated["state"]["obligations"]
                      if row["id"] == "question:boundary")
    assert obligation["state"] == "addressed"
    assert obligation["evidence"] == ["run://boundary-001"]
    assert obligation["verification"] == "NOT_ESTABLISHED_BY_DISPOSITION"


def test_routing_is_explicit_stable_and_review_cannot_mutate(tmp_path):
    manuscript = _fixture(tmp_path)
    tex_before = (manuscript / "main.tex").read_bytes()
    _change(tmp_path, "add_obligation", node="question:proof",
        meaning="Which lemma closes the proof?",
        target={"kind": "node", "node_id": "result:one"}, work_kind="formal",
        discharge_condition="A named proof obligation is discharged with exact evidence.")
    plan = writing_tools.execute(tmp_path, "logic", "discuss", "logical_plan",
                                 {"node": "question:proof"})
    assert plan["selected"]["id"] == "question:proof"
    with pytest.raises(ValueError, match="Independent review"):
        writing_tools.execute(tmp_path, "logic", "review", "logical_plan_change", {
            "operation": "update_obligation", "base_revision": plan["revision"],
            "node": "question:proof", "state": "withdrawn",
            "disposition": "review may not mutate"}, turn_id="WT-review")

    routed = writing_tools.execute(tmp_path, "logic", "discuss", "logical_plan_change", {
        "operation": "route_obligation", "base_revision": plan["revision"],
        "node": "question:proof"}, turn_id="WT-route")
    assert routed["task"]["obligation_id"] == "question:proof"
    assert routed["state"]["selected"]["id"] == "question:proof"
    assert "meaning" not in routed["state"]["selected"] and "relations" not in routed["state"]["selected"]
    assert routed["read_more"] == "logical_plan with node, or structure for the chapter outline"
    task_id = routed["task"]["id"]
    current = concepts_surface.logical_plan("logic", root=tmp_path)
    routed_again = writing_tools.execute(tmp_path, "logic", "work", "logical_plan_change", {
        "operation": "route_obligation", "base_revision": current["revision"],
        "node": "question:proof"}, turn_id="WT-route-2")
    assert routed_again["task"]["id"] == task_id
    assert (manuscript / "main.tex").read_bytes() == tex_before


def test_machine_context_is_attention_bounded_and_help_is_source_derived(tmp_path):
    _fixture(tmp_path)
    _change(tmp_path, "connect", source="result:one", target="premise:one",
            relation="prerequisite", rationale="The conclusion assumes finiteness.")
    context = concepts_surface.logical_plan_context("logic", "result:one", root=tmp_path)
    assert context["selected"]["id"] == "result:one"
    assert {row["id"] for row in context["objects"]} == {"result:one", "premise:one"}
    assert context["omission"]["attention_limit"] == 24
    help_value = writing_tools.execute(tmp_path, "logic", "work", "help",
                                       {"operation": "logical_plan_change"})
    # `requested_payload_contract` is gone: it returned the owner's whole contract a
    # SECOND time beside the copy inside `action`, which was 75.3 per cent of
    # help structure_change. The property that mattered is unchanged and asserted
    # here instead: every variant help serves is BUILT from the owner's own
    # contract, so the owner is still the one source.
    owner = concepts_surface.logical_plan_operation_contract()
    from laplace.native import declarations as writing_declarations
    variants = writing_declarations.variants("logical_plan_change")
    assert set(variants) == set(owner["operations"])
    for name, rule in owner["operations"].items():
        assert set(rule["required"]) <= set(variants[name]["required"])
        assert variants[name]["properties"]["operation"] == {"const": name}


def test_scanner_facade_and_existing_explorer_consume_the_same_plan(tmp_path):
    _fixture(tmp_path)
    status, content_type, raw = concepts_surface.handle("/concepts/plan",
        {"project": ["logic"], "focus": ["result:one"]}, "GET", b"", repo_root=tmp_path)
    served = json.loads(raw)
    assert status == 200 and content_type.startswith("application/json")
    assert served["selected"]["id"] == "result:one"
    payload = {"project": "logic", "operation": "add_obligation",
        "base_revision": served["revision"], "node": "question:http",
        "meaning": "What evidence closes this claim?",
        "target": {"kind": "node", "node_id": "result:one"},
        "work_kind": "research", "discharge_condition": "An exact evidence reference is bound."}
    status, _, raw = concepts_surface.handle("/concepts/plan/change", {}, "POST",
        json.dumps(payload).encode(), repo_root=tmp_path)
    assert status == 200 and json.loads(raw)["state"]["selected"]["id"] == "question:http"

    explorer = Path("src/laplace/web/static_shared/concept-explorer.mjs").read_text()
    from workspace_source import workspace_source
    workspace = workspace_source()   # the shell and its domain controllers (M5 S2 F1)
    assert "mountArgumentOverview" in explorer and "/concepts/plan?" in explorer
    assert "Add open question" in explorer and "question:id=>openObligation" in workspace
    assert "laplace:logical-focus:" in workspace


def test_disposition_pins_local_target_and_question_without_awarding_verification(tmp_path):
    _fixture(tmp_path, placed=True)
    _change(tmp_path, 'add_obligation', node='question:choice', meaning='Which scope should we state?',
        target={'kind':'node','node_id':'result:one'}, work_kind='author-decision',
        discharge_condition='The author records the intended scope.')
    _change(tmp_path, 'route_obligation', node='question:choice')
    _change(tmp_path, 'update_obligation', node='question:choice', state='addressed',
        disposition='Use the finite case.')
    def question():
        return next(row for row in concepts_surface.logical_plan('logic',root=tmp_path)['obligations']
                    if row['id']=='question:choice')
    before=question()
    assert before['marker']=='DECIDE'
    assert before['currentness']['status']=='CURRENT'
    assert before['consumed_basis']['actor']=='author'
    assert before['consumed_basis']['authority']=='canonical-question-projection'
    assert before['consumed_basis']['human_consent']=='NOT_ESTABLISHED'
    assert before['decision_permission']['status']=='NOT_ESTABLISHED'
    assert before['verification']=='NOT_ESTABLISHED_BY_DISPOSITION'
    assert before['placements'][0]['id']=='S1'
    assert before['work'][0]['id'].startswith('WORK-OBL-')
    assert before['origin']['status']=='RECORDED'
    _change(tmp_path,'edit_meaning',node='def:one',meaning='An unrelated definition changed.')
    assert question()['currentness']['status']=='CURRENT'
    _change(tmp_path,'edit_meaning',node='result:one',meaning='The construction needs another assumption.')
    assert question()['currentness']['status']=='STALE'
    assert question()['state']=='addressed'
    _change(tmp_path,'update_obligation',node='question:choice',state='addressed',
        disposition='Author reviewed the changed target.')
    assert question()['currentness']['status']=='CURRENT'
    _change(tmp_path,'edit_meaning',node='question:choice',meaning='Which broader scope should we state?')
    assert question()['currentness']['status']=='STALE'


def test_legacy_resolution_and_unresolved_evidence_remain_explicit(tmp_path):
    _fixture(tmp_path)
    made=corpus_ingest.rewire_add(tmp_path,'logic',{'kind':'add-node','node':'question:legacy',
        'node_kind':'question','essence':'Does this hold?', 'projection':{'obligation':{
            'target':{'kind':'node','node_id':'result:one'},'work_kind':'research',
            'discharge_condition':'Confirm the result.','state':'addressed',
            'evidence':['unrecorded://source'],'disposition':'Earlier author disposition.'}}})
    assert made.get('ok')
    row=concepts_surface.logical_plan('logic',root=tmp_path)['obligations'][0]
    assert row['currentness']['status']=='UNPINNED_LEGACY'
    assert row['live_basis']['evidence'][0]['owner'] is None
    _change(tmp_path,'update_obligation',node='question:legacy',state='addressed')
    row=concepts_surface.logical_plan('logic',root=tmp_path)['obligations'][0]
    assert row['currentness']['status']=='UNKNOWN'
    assert row['marker']=='CONFIRM'


def test_passage_context_uses_enclosing_heading_and_same_canonical_questions(tmp_path):
    manuscript=_fixture(tmp_path)
    (manuscript/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\n'
        '\\section{First}\\label{source-first}\nFirst scientific statement.\n\n'
        '\\section{Second}\\label{source-second}\nSecond scientific statement.\n\\end{document}\n')
    (manuscript/'projection_plan.json').write_text(json.dumps({
        'meta':{'project':'logic','target_dir':'logic/manuscript'},'sections':[
            {'id':'S1','title':'First','source_file':'logic/manuscript/main.tex','source_label':'source-first','nodes_in_order':['result:one'],'beats':[],'refs':[]},
            {'id':'S2','title':'Second','source_file':'logic/manuscript/main.tex','source_label':'source-second','nodes_in_order':['def:one'],'beats':[],'refs':[]}],
        'appendices':[]}))
    _change(tmp_path,'add_obligation',node='question:first',meaning='Confirm the first statement.',
        target={'kind':'node','node_id':'result:one'},work_kind='research',
        discharge_condition='Check the finite case.')
    _change(tmp_path,'add_obligation',node='question:second',meaning='Choose the definition wording.',
        target={'kind':'node','node_id':'def:one'},work_kind='author-decision',
        discharge_condition='Author records the wording.')
    context=concepts_surface.logical_plan_context('logic',root=tmp_path,
        file='main.tex',line_start=4,line_end=4)['passage_context']
    assert context['precision']=='SECTION_ONLY'
    assert [section['id'] for section in context['basis']['automatic_sections']]==['S1']
    assert [row['id'] for row in context['obligations']]==['question:first']
    assert context['document_provenance'][0]['status']=='UNKNOWN'
    assert context['document_provenance'][0]['paragraphs'] is None
    assert context['accepted_proposals']==[]
    with pytest.raises(ValueError):
        concepts_surface.logical_plan_context('logic',root=tmp_path,file='main.tex')


def test_disposition_detects_research_bytes_changing_without_result_revision_change(tmp_path):
    from laplace.research import research_records
    manuscript=_fixture(tmp_path)
    result_file=manuscript/'measurement.json';result_file.write_text('{"score":1}\n')
    status,created=research_records.record('logic',{'kind':'result','id':'measurement:one',
        'result':'measurement.json'},tmp_path)
    assert status==201,created
    revision=created['record']['revision']
    _change(tmp_path,'add_obligation',node='question:measurement',meaning='Confirm the measurement.',
        target={'kind':'node','node_id':'result:one'},work_kind='research',
        discharge_condition='Record the measured result.')
    _change(tmp_path,'update_obligation',node='question:measurement',state='addressed',
        evidence=[{'id':'measurement:one','revision':revision}])
    def question():return concepts_surface.logical_plan('logic',root=tmp_path)['obligations'][0]
    assert question()['currentness']['status']=='CURRENT'
    assert question()['live_basis']['evidence'][0]['owner']=='research-result'
    result_file.write_text('{"score":2}\n')
    changed=question()
    assert changed['currentness']['status']=='STALE'
    assert changed['live_basis']['evidence'][0]['revision']==revision
    assert changed['verification']=='NOT_ESTABLISHED_BY_DISPOSITION'


def test_existing_document_sidecars_are_read_from_declared_fixture_root(tmp_path):
    from laplace.pipeline import document_model
    from laplace.pipeline import pathsafe,registry
    manuscript=_fixture(tmp_path)
    project=registry.resolve('logic',repo_root=tmp_path)
    for stage,payload in [('provenance',{'paragraphs':[{'spec_id':'para:one','inputs':['result:one']}]}),
                          ('decisions',{'decisions':[{'spec_id':'para:one','kind':'fork'}]})]:
        path=project.stage_path(stage,tmp_path)/f'{pathsafe.encode_sid_for_path("S1")}.json'
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload))
    assert document_model.load_provenance('logic','S1',tmp_path)[0]['inputs']==['result:one']
    assert document_model.load_decisions('logic','S1',tmp_path)[0]['kind']=='fork'
    assert document_model.load_provenance('logic','S1',tmp_path/'another-root') is None


def test_addressing_with_an_old_declared_evidence_revision_stays_stale(tmp_path):
    _fixture(tmp_path)
    _change(tmp_path,'add_obligation',node='question:old-evidence',meaning='Is the definition usable?',
        target={'kind':'node','node_id':'result:one'},work_kind='concept',
        discharge_condition='Check the intended definition.')
    _change(tmp_path,'update_obligation',node='question:old-evidence',state='addressed',
        evidence=[{'id':'def:one','content_revision':'older-revision'}])
    question=concepts_surface.logical_plan('logic',root=tmp_path)['obligations'][0]
    assert question['currentness']['status']=='STALE'
    assert question['live_basis']['evidence'][0]['reason'].startswith('Declared evidence revision differs')


def test_passage_outside_single_placed_heading_is_unbound(tmp_path):
    manuscript=_fixture(tmp_path)
    (manuscript/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\n'
        'Opening prose before the section.\n\\section{Only section}\nScoped prose.\n\\end{document}\n')
    (manuscript/'projection_plan.json').write_text(json.dumps({'meta':{'project':'logic'},
        'sections':[{'id':'S1','title':'Only section','nodes_in_order':['result:one'],
                     'beats':[],'refs':[]}],'appendices':[]}))
    context=concepts_surface.logical_plan_context('logic',root=tmp_path,
        file='main.tex',line_start=3,line_end=3)['passage_context']
    assert context['precision']=='UNBOUND'
    assert context['obligations']==[]
    assert context['basis']['automatic_section_concepts']==[]


def test_exact_paragraph_markers_join_merged_and_split_provenance_without_guessing(tmp_path):
    from laplace.pipeline import registry,pathsafe
    manuscript=_fixture(tmp_path,placed=True)
    (manuscript/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\n'
        '\\section{Reader entry}\n% PLAN:S1\n% S1-p1\n% S1-p2\n'
        'Merged paragraph with the result.\n\n% S1-p3\n'
        'First part of a split paragraph.\n\n% S1-p3\n'
        'Second part of the split paragraph.\n\\end{document}\n')
    project=registry.resolve('logic',repo_root=tmp_path)
    provenance=project.stage_path('provenance',tmp_path)/f'{pathsafe.encode_sid_for_path("S1")}.json'
    provenance.parent.mkdir(parents=True,exist_ok=True)
    records=[{'spec_id':'S1-p1','spec_ids':['S1-p1','S1-p2'],'nodes_realised':['result:one']},
             {'spec_id':'S1-p3','nodes_realised':['def:one']},
             {'spec_id':'S1-p3','nodes_realised':['premise:one']}]
    provenance.write_text(json.dumps({'paragraphs':records}))
    _change(tmp_path,'add_obligation',node='question:result-marker',meaning='Confirm marked result.',
        target={'kind':'node','node_id':'result:one'},work_kind='research',discharge_condition='Check it.')
    merged=concepts_surface.logical_plan_context('logic',root=tmp_path,
        file='main.tex',line_start=7,line_end=7)['passage_context']
    assert merged['precision']=='PARAGRAPH_MARKER'
    assert merged['paragraph_marker']['spec_ids']==['S1-p1','S1-p2']
    assert [row['id'] for row in merged['paragraph_concepts']]==['result:one']
    assert merged['obligations'][0]['id']=='question:result-marker'
    split=concepts_surface.logical_plan_context('logic',root=tmp_path,
        file='main.tex',line_start=13,line_end=13)['passage_context']
    assert [row['id'] for row in split['paragraph_concepts']]==['premise:one']
    assert split['obligations']==[]
    records.reverse();provenance.write_text(json.dumps({'paragraphs':records}))
    untrusted=concepts_surface.logical_plan_context('logic',root=tmp_path,
        file='main.tex',line_start=7,line_end=7)['passage_context']
    assert untrusted['precision']=='SECTION_ONLY'
    assert untrusted['paragraph_concepts']==[]
    assert 'do not agree' in untrusted['document_provenance'][0]['reason']


def test_rerouting_preserves_authored_work_and_does_not_renew_acceptance(tmp_path):
 from laplace.work import project_work
 _fixture(tmp_path)
 _change(tmp_path,'add_obligation',node='question:route',meaning='Which evidence closes this?',
    target={'kind':'node','node_id':'result:one'},work_kind='formal',discharge_condition='A bound proof result.')
 created=_change(tmp_path,'route_obligation',node='question:route')
 ident=created['task']['id']
 focused=project_work.read('logic',{'view':'detail','id':ident},tmp_path)
 project_work.task('logic',{**focused['allowed_actions']['task']['payload'],
     'title':'Authored investigation','goal':'A stronger author-approved criterion'},tmp_path)
 output=tmp_path/'proof.txt';output.write_text('accepted result')
 focused=project_work.read('logic',{'view':'detail','id':ident},tmp_path)
 project_work.transition('logic',{**focused['allowed_actions']['task_status']['payload'],'status':'done','evidence':['proof.txt']},tmp_path)
 before=project_work._ledger(tmp_path).read_bytes()
 repeated=_change(tmp_path,'route_obligation',node='question:route')
 assert repeated['routing']=='EXISTING_WORK_PRESERVED'
 assert repeated['task']['id']==ident and repeated['task']['goal']=='A stronger author-approved criterion'
 assert repeated['task']['title']=='Authored investigation' and repeated['task']['recorded_status']=='done'
 assert project_work._ledger(tmp_path).read_bytes()==before
 assert repeated['work_read_handle']['payload']['id']==ident
