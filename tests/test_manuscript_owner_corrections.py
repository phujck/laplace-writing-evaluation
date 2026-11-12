"""The independent owner-join counterexamples, now requiring honest shared views."""
import json
import pytest
from laplace.research import concepts as cs, corpus_ingest as ci
from laplace.work import project_work as work
from laplace.pipeline import registry,pathsafe
from test_logical_planning import _fixture,_change
from work_read_helpers import guarded_transition

def _question(root):return cs.logical_plan('logic',root=root)['obligations'][0]

def test_obligation_work_joins_one_effective_fold_and_retains_recorded_status(tmp_path,monkeypatch):
    _fixture(tmp_path)
    _change(tmp_path,'add_obligation',node='question:join',meaning='Confirm the result.',target={'kind':'node','node_id':'result:one'},work_kind='research',discharge_condition='Report independent evidence.')
    task=_change(tmp_path,'route_obligation',node='question:join')['task']
    report=tmp_path/'report.txt';report.write_text('retained evidence')
    guarded_transition('logic',{'id':task['id'],'status':'done','evidence':['report.txt']},tmp_path)
    work.task('logic',{'id':task['id'],'goal':'Prove the broader claim',
        'expected_work_revision':work._task_revision(work._tasks('logic',tmp_path)[task['id']])},tmp_path)
    original=work._resolved_tasks;calls=[]
    def observed(*args,**kwargs):calls.append(True);return original(*args,**kwargs)
    monkeypatch.setattr(work,'_resolved_tasks',observed)
    linked=_question(tmp_path)['work'][0]
    assert len(calls)==1
    assert linked['status']=='blocked' and linked['currentness']['status']=='STALE'
    assert linked['recorded_status']=='done'
    owner=next(row for row in work.summary('logic',tmp_path)['tasks'] if row['id']==task['id'])
    assert linked['currentness']==owner['currentness'] and linked['blocked_by']==owner['blocked_by']
    guarded_transition('logic',{'id':task['id'],'status':'done','evidence':['report.txt']},tmp_path)
    work.task('logic',{'id':'unrelated','title':'Other work','goal':'Separate goal'},tmp_path)
    assert _question(tmp_path)['work'][0]['status']=='done'
    report.write_text('changed evidence')
    assert _question(tmp_path)['work'][0]['currentness']['status']=='STALE'

def test_missing_relation_can_retain_disposition_but_never_claim_current(tmp_path):
    _fixture(tmp_path)
    _change(tmp_path,'connect',source='result:one',target='premise:one',relation='prerequisite',rationale='The result consumes the premise.')
    _change(tmp_path,'add_obligation',node='question:edge',meaning='Confirm dependency.',target={'kind':'relation','source':'result:one','target':'premise:one','rel':'prerequisite'},work_kind='research',discharge_condition='Check exact dependency.')
    _change(tmp_path,'update_obligation',node='question:edge',state='addressed',disposition='Checked exact edge.')
    assert _question(tmp_path)['currentness']['status']=='CURRENT'
    assert ci.rewire_add(tmp_path,'logic',{'kind':'remove-edge','node':'result:one','target':'premise:one','rel':'prerequisite','by':'fixture'}).get('ok')
    assert _question(tmp_path)['currentness']['status']=='STALE'
    _change(tmp_path,'update_obligation',node='question:edge',state='addressed',disposition='Reconsidered after deletion.')
    observed=_question(tmp_path)
    assert observed['state']=='addressed' and observed['issue']['kind']=='unbound-obligation'
    assert observed['live_basis']['relation'] is None and observed['currentness']['status']=='UNKNOWN'
    _change(tmp_path,'connect',source='result:one',target='premise:one',relation='prerequisite',rationale='Restored explicit dependency.')
    _change(tmp_path,'update_obligation',node='question:edge',state='addressed',disposition='Checked restored dependency.')
    assert _question(tmp_path)['currentness']['status']=='CURRENT'

@pytest.mark.parametrize('records',[[None],['legacy text'],{'wrong':'shape'},[{'spec_id':'S1-p1','nodes_realised':'not-an-array'}],[{'spec_ids':'S1-p1'}]])
def test_malformed_paragraph_sidecar_has_diagnostic_section_fallback(tmp_path,records):
    manuscript=_fixture(tmp_path,placed=True)
    (manuscript/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\n\\section{Reader entry}\n% PLAN:S1\n% S1-p1\nA marked scientific passage.\n\\end{document}\n')
    project=registry.resolve('logic',repo_root=tmp_path)
    path=project.stage_path('provenance',tmp_path)/(pathsafe.encode_sid_for_path('S1')+'.json')
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps({'paragraphs':records}))
    before=path.read_bytes()
    context=cs.logical_plan_context('logic',root=tmp_path,file='main.tex',line_start=6,line_end=6)['passage_context']
    assert context['precision']=='SECTION_ONLY' and context['paragraph_concepts']==[]
    provenance=context['document_provenance'][0]
    assert provenance['status']=='UNKNOWN' and provenance['paragraphs'] is None
    assert 'Malformed or unavailable paragraphs sidecar' in provenance['diagnostics'][0]
    assert path.read_bytes()==before
