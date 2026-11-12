"""Public selected Work provenance/support owner controls; no provider turn."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from laplace.work import project_work as W,project_work_views as V,project_work_evidence as E,owner_discovery as O
from laplace.projects import artifacts
from laplace.writing import records,session_reads


def scene(root):
    (root/'contract').mkdir();(root/'proj/manuscript').mkdir(parents=True)
    (root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'conceptric','project_dir':'proj','manuscript_dir':'proj/manuscript','tex_root':'proj/manuscript'}]}))
    (root/'proj/manuscript/main.tex').write_text('\\documentclass{article}\n\\begin{document}Public\\end{document}\n')
    W.task('p',{'id':'work','title':'Public soil task Ω','goal':'Retain an inspectable answer'},root)
    records.bank(root,{'record':'writing-session','id':'WS-public','project':'p','role':'author','title':'Controlled public conversation'})
    records.bank(root,{'record':'writing-turn','id':'WT-public','project':'p','session_id':'WS-public','work_id':'work','mode':'work','text':'Controlled saved request; not a provider run'})
    records.bank(root,{'record':'writing-turn','id':'WT-unbound','project':'p','session_id':'WS-public','text':'This unbound turn mentions work but is not bound'})
    records.bank(root,{'record':'writing-reply','id':'WR-public','project':'p','session_id':'WS-public','turn_id':'WT-public','text':'Controlled public answer Ω'})
    answer=artifacts.store(root,'p',{'path':'answer.md','scope':'project','before':None,'content':'Retained answer Ω'},turn_id='WT-public')
    return O.project_scope('p','native'),answer


def read(root,scope,request=None):
    return V.read('p',{'view':'provenance','id':'work','request':request or {}},root,native_caller=scope)

def manifest(root,answer,*,items=None,name='support.json'):
    task=W._tasks('p',root)['work'];basis,_=W._work_basis({'work':task},'work')
    document={'schema_version':E.SUPPORT_SCHEMA,'work':{'namespace':'p','id':'work','scope_revision':basis['scope_revision']},
        'items':items if items is not None else [{'id':'answer','required':True,'role':'answer','retention':'retained','owner':'project-artifact',
            'reference':{'id':answer['id'],'expected_sha256':answer['revision']}}]}
    created=artifacts.store(root,'p',{'path':name,'scope':'project','before':None,'content':json.dumps(document)})
    return {'id':created['id'],'expected_sha256':created['revision']},document

def complete(root,reference=None):
    detail=V.read('p',{'view':'detail','id':'work'},root)
    payload={**detail['allowed_actions']['task_status']['payload'],'status':'done','evidence':['proj/answer.md']}
    if reference is not None:payload['completion_support']=reference
    result=W.transition('p',payload,root)
    return payload,result


def test_aggregate_metadata_and_exact_bound_turn_reply_artifact(tmp_path,monkeypatch):
    scope,answer=scene(tmp_path)
    monkeypatch.setattr(session_reads,'_records',lambda *a,**k:pytest.fail('rich session fold'))
    monkeypatch.setattr(artifacts,'read',lambda *a,**k:pytest.fail('body read for aggregate'))
    a=read(tmp_path,scope);assert a['counts']['bound_turns']==1 and a['support']['state']=='NOT_DECLARED'
    page=V.read('',a['reads']['relationships']['payload'],tmp_path,native_caller=scope)
    turn=next(x for x in page['items'] if x['kind']=='conversation-turn');artifact=next(x for x in page['items'] if x['kind']=='artifact-receipt')
    assert turn['target']['turn_id']=='WT-public' and artifact['target']['artifact_id']==answer['id']
    reply=session_reads.public_message(tmp_path,turn['reply_read']['sdk']['payload'])
    assert reply['content']=='Controlled public answer Ω'
    assert 'expected_sha256' in artifact['read']['http']['url'] and artifact['scope']=='project'
    (tmp_path/'actual-sample.json').write_text(json.dumps({'aggregate':a,'relationships':page,'reply':reply},indent=2))


def test_scope_and_closed_query_refuse_before_lookup(tmp_path,monkeypatch):
    monkeypatch.setattr(W,'_tasks',lambda *a,**k:pytest.fail('Work lookup before scope'))
    for scope in (None,O.project_scope('foreign','native')):
        with pytest.raises(ValueError,match='scope'):read(tmp_path,scope)
    with pytest.raises(ValueError):read(tmp_path,O.project_scope('p','native'),{'demand':'aggregate','path':'/tmp/private'})


def test_selected_page_change_and_unrelated_append(tmp_path):
    scope,_=scene(tmp_path);a=read(tmp_path,scope)
    records.bank(tmp_path,{'record':'writing-session','id':'WS-other','project':'other'})
    assert read(tmp_path,scope)['observation']['token']==a['observation']['token']
    records.bank(tmp_path,{'record':'writing-turn','id':'WT-later','project':'p','session_id':'WS-public','work_id':'work','text':'later controlled'})
    with pytest.raises(W.WorkConflict) as err:V.read('',a['reads']['relationships']['payload'],tmp_path,native_caller=scope)
    assert err.value.details['kind']=='CHANGED_INPUT'


def test_required_support_survives_done_but_absence_is_visible_and_refuses_new_claim(tmp_path):
    scope,answer=scene(tmp_path);reference,_=manifest(tmp_path,answer);original,result=complete(tmp_path,reference)
    assert W._tasks('p',tmp_path)['work']['completion_support']['reference']==reference
    # Lost acknowledgement retries keep the exact existing guard; no new transition.
    before=W._ledger(tmp_path).read_bytes()
    with pytest.raises(W.WorkConflict):W.transition('p',original,tmp_path)
    assert W._ledger(tmp_path).read_bytes()==before
    observation=read(tmp_path,scope,{'demand':'evidence'})
    assert observation['direct_completion']['status']=='CURRENT'
    item=next(x for x in observation['items'] if x['kind']=='declared-support')
    assert item['integrity']=='VERIFIED' and item['availability']=='PRESENT'
    # Direct report remains while separately required support disappears.
    (tmp_path/'proj/answer.md').unlink()
    missing=read(tmp_path,scope,{'demand':'evidence'})
    assert W._tasks('p',tmp_path)['work']['status']=='done'
    assert next(x for x in missing['items'] if x['kind']=='declared-support')['availability']=='MISSING'
    with pytest.raises(ValueError,match='evidence'):complete(tmp_path)
    with pytest.raises(W.WorkConflict):read(tmp_path,scope,{'demand':'evidence','as_of':observation['observation']['token']})
    (tmp_path/'support-sample.json').write_text(json.dumps({'present':observation,'missing':missing},indent=2))


def test_legacy_done_and_separate_direct_report_currentness(tmp_path):
    scope,answer=scene(tmp_path)
    # Completion report is independent of its declared raw answer.
    (tmp_path/'report.json').write_text('{"historical_observation":true}')
    reference,_=manifest(tmp_path,answer)
    detail=V.read('p',{'view':'detail','id':'work'},tmp_path)
    W.transition('p',{**detail['allowed_actions']['task_status']['payload'],'status':'done','evidence':['report.json'],'completion_support':reference},tmp_path)
    (tmp_path/'proj/answer.md').write_text('Changed retained support')
    result=read(tmp_path,scope,{'demand':'evidence'})
    assert result['direct_completion']['status']=='CURRENT'
    assert next(x for x in result['items'] if x['kind']=='declared-support')['availability']=='CHANGED'
    W.task('p',{'id':'legacy','title':'Historical legacy','goal':'Direct proof only'},tmp_path)
    d=V.read('p',{'view':'detail','id':'legacy'},tmp_path)
    W.transition('p',{**d['allowed_actions']['task_status']['payload'],'status':'done','evidence':['report.json']},tmp_path)
    assert V.read('p',{'view':'provenance','id':'legacy'},tmp_path,native_caller=scope)['support']['state']=='NOT_DECLARED'


def test_disposable_foreign_pin_and_duplicate_manifest_refuse(tmp_path):
    scope,answer=scene(tmp_path);reference,doc=manifest(tmp_path,answer)
    bad=copy.deepcopy(doc['items']);bad[0]['retention']='disposable-scratch'
    scratch,_=manifest(tmp_path,answer,items=bad,name='scratch.json')
    with pytest.raises(ValueError,match='Disposable'):complete(tmp_path,scratch)
    bad=copy.deepcopy(doc['items']);bad[0]['reference']={'path':'../../outside','scope':'project','expected_sha256':answer['revision']}
    escape,_=manifest(tmp_path,answer,items=bad,name='escape.json')
    with pytest.raises(ValueError,match='evidence'):complete(tmp_path,escape)
    bad=copy.deepcopy(doc['items']);bad[0]['reference']['expected_sha256']='0'*64
    wrong,_=manifest(tmp_path,answer,items=bad,name='wrong.json')
    with pytest.raises(ValueError,match='evidence'):complete(tmp_path,wrong)
    dup,_=manifest(tmp_path,answer,items=doc['items']*2,name='duplicate.json')
    with pytest.raises(ValueError,match='ambiguous'):complete(tmp_path,dup)


def test_exact_scope_resolution_and_owner_issued_choices(tmp_path):
    scope,answer=scene(tmp_path)
    (tmp_path/'proj/manuscript/answer.md').write_text('Different manuscript scoped bytes')
    desc,target=artifacts.evidence_descriptor(tmp_path,'p',{'id':answer['id'],'expected_sha256':answer['revision']})
    assert target==tmp_path/'proj/answer.md' and desc['scope']=='project'
    with pytest.raises(ValueError):artifacts.evidence_descriptor(tmp_path,'p',{'id':answer['id'],'scope':'manuscript','expected_sha256':answer['revision']})
    choices=read(tmp_path,scope,{'demand':'choices'})
    chosen=next(x for x in choices['items'] if x['id']==answer['id'])
    assert chosen['evidence_value']=='proj/answer.md' and chosen['completion_support']['id']==answer['id']
    (tmp_path/'choices-sample.json').write_text(json.dumps(choices,indent=2))


def test_run_metadata_choice_and_explicit_run_support(tmp_path,monkeypatch):
    from laplace.research import research_context as C,research_runs as Runs,research_observation as Obs
    scope,answer=scene(tmp_path);_,manuscript=C.project('p',tmp_path)
    home=manuscript/'research_runs';home.mkdir()
    result=manuscript/'public-result.json';result.write_text('{"controlled_saved_result":true}')
    producer=manuscript/'public-producer.py';producer.write_text('# controlled metadata only; never executed\n')
    declaration={'id':'public','executable':'public-producer.py','modes':['smoke'],'allowed_args':{}}
    (manuscript/'research_producers.json').write_text(json.dumps({'producers':[declaration]}))
    pin=hashlib.sha256(result.read_bytes()).hexdigest()
    job={'id':'RUN-public','project':'p','launch_token':'public-owned-token','state':'COMPLETE','producer_id':'public',
        'producer_path':'public-producer.py','producer_base':str(manuscript),'result_absolute':str(result),'result_path':result.relative_to(manuscript).as_posix(),
        'provenance':{'producer':{**Obs._digest(producer),'path':'public-producer.py','scope':'manuscript'},'producer_config':Obs._object_digest(declaration),'dependencies':[]}}
    (home/'RUN-public.json').write_text(json.dumps(job))
    (home/'RUN-public.receipt.json').write_text(json.dumps({'state':'COMPLETE','result_sha256':pin}))
    (home/'index.json').write_text(json.dumps({'runs':['RUN-public']}))
    original=Path.read_bytes
    def no_result_body(path):
        if path==result:pytest.fail('Result body read for picker')
        return original(path)
    with monkeypatch.context() as patch:
        patch.setattr(Path,'read_bytes',no_result_body)
        choices=read(tmp_path,scope,{'demand':'choices'})
    item=next(row for row in choices['items'] if row.get('owner')=='research-run-output')
    assert item['evidence_value']==result.relative_to(tmp_path).as_posix() and item['currentness']=='NOT_CHECKED'
    reference,doc=manifest(tmp_path,answer,items=[{'id':'run','required':True,'role':'result','retention':'retained','owner':'research-run-output','reference':item['support_item_reference']}])
    complete(tmp_path,reference)
    value=read(tmp_path,scope,{'demand':'evidence'})
    row=next(row for row in value['items'] if row.get('owner')=='research-run-output')
    assert row['integrity']=='VERIFIED' and row['run_state']=='COMPLETE'
    result.unlink()
    with pytest.raises(ValueError,match='evidence'):complete(tmp_path)
    (tmp_path/'run-output-sample.json').write_text(json.dumps({'choices':choices,'support':value,'qualification':'Controlled public saved job/receipt; no run was launched.'},indent=2))


def test_duplicate_turn_and_bad_manifest_do_not_infer_or_complete(tmp_path):
    scope,answer=scene(tmp_path)
    records.bank(tmp_path,{'record':'writing-turn','id':'WT-public','project':'p','session_id':'WS-public','work_id':'work','text':'duplicate public identity'})
    a=read(tmp_path,scope)
    assert a['counts']['bound_turns']==0 and a['coverage']['identity_issues']
    invalid=artifacts.store(tmp_path,'p',{'path':'invalid-manifest.json','scope':'project','before':None,
        'content':'{"schema_version":"laplace.work-evidence-support/1","work":{},"work":{},"items":[]}'})
    with pytest.raises(ValueError,match='duplicate'):complete(tmp_path,{'id':invalid['id'],'expected_sha256':invalid['revision']})


def test_reply_metadata_change_invalidates_held_relationships(tmp_path):
    scope,_=scene(tmp_path);first=read(tmp_path,scope)
    records.bank(tmp_path,{'record':'writing-reply','id':'WR-second','project':'p','session_id':'WS-public','turn_id':'WT-public','text':'second controlled reply'})
    with pytest.raises(W.WorkConflict):V.read('',first['reads']['relationships']['payload'],tmp_path,native_caller=scope)
    page=read(tmp_path,scope,{'demand':'relationships'})
    turn=next(row for row in page['items'] if row['kind']=='conversation-turn')
    assert turn['reply_state']=='UNAVAILABLE' and turn['reply_read'] is None


def test_manifest_budget_optional_missing_and_changed_required_scope(tmp_path):
    scope,answer=scene(tmp_path)
    optional={'id':'missing-optional','required':False,'role':'optional supporting note','retention':'disposable-scratch','owner':'project-artifact',
        'reference':{'path':'missing.md','scope':'project','expected_sha256':'0'*64}}
    reference,doc=manifest(tmp_path,answer,items=[optional])
    complete(tmp_path,reference)
    result=read(tmp_path,scope,{'demand':'evidence'})
    assert result['support']['required']==0 and next(x for x in result['items'] if x['kind']=='declared-support')['availability']=='MISSING'
    # A material scope edit cannot silently use the old manifest for a new completion.
    current=W._tasks('p',tmp_path)['work']
    W.task('p',{'id':'work','goal':'Changed current purpose','expected_work_revision':W._task_revision(current)},tmp_path)
    with pytest.raises(ValueError,match='scope'):complete(tmp_path)
    large=tmp_path/'proj/oversized.json';large.write_bytes(b' '*2_000_001)
    with pytest.raises(ValueError,match='budget'):complete(tmp_path,{'path':'oversized.json','scope':'project','expected_sha256':hashlib.sha256(large.read_bytes()).hexdigest()})


def test_new_dependent_completion_checks_required_support_of_prerequisite(tmp_path):
    scope,answer=scene(tmp_path);reference,_=manifest(tmp_path,answer);complete(tmp_path,reference)
    W.task('p',{'id':'consumer','title':'Consume actual retained result','goal':'Needs the prerequisite evidence','depends_on':['work']},tmp_path)
    (tmp_path/'consumer-report.md').write_text('A direct report is not its required prerequisite support.')
    (tmp_path/'proj/answer.md').unlink()
    d=V.read('p',{'view':'detail','id':'consumer'},tmp_path)
    with pytest.raises(ValueError,match='evidence|blocked'):
        W.transition('p',{**d['allowed_actions']['task_status']['payload'],'status':'done','evidence':['consumer-report.md']},tmp_path)


def test_run_result_coordinates_refuse_before_foreign_stat_or_body(tmp_path,monkeypatch):
    from laplace.research import research_context as C,research_runs as Runs
    scope,_=scene(tmp_path);_,home=C.project('p',tmp_path)
    runs=home/'research_runs';runs.mkdir()
    foreign=tmp_path/'foreign-output.json';foreign.write_text('Controlled foreign sentinel, not private.')
    job={'id':'RUN-forged','project':'p','launch_token':'public','state':'COMPLETE',
        'result_path':'public-result.json','result_absolute':str(foreign)}
    (runs/'RUN-forged.json').write_text(json.dumps(job))
    (runs/'RUN-forged.receipt.json').write_text(json.dumps({'state':'COMPLETE','result_sha256':hashlib.sha256(foreign.read_bytes()).hexdigest()}))
    (runs/'index.json').write_text(json.dumps({'runs':['RUN-forged']}))
    original=Path.stat
    def no_foreign_stat(path,*a,**kw):
        if path==foreign:pytest.fail('Foreign result stat before owner fence')
        return original(path,*a,**kw)
    with monkeypatch.context() as patch:
        patch.setattr(Path,'stat',no_foreign_stat)
        choices=Runs.evidence_candidates(tmp_path,'p')
        code,status=Runs.run_status_read('p','RUN-forged',tmp_path)
    assert not choices['items'] and choices['issues']
    assert code==200 and status['state']=='UNAVAILABLE' and 'Research home' in status['reason']


def test_run_locator_cannot_authorize_foreign_job_read(tmp_path,monkeypatch):
    from laplace.research import research_context as C,research_runs as Runs
    scene(tmp_path);_,home=C.project('p',tmp_path)
    index_home=home/'research_runs';index_home.mkdir()
    foreign_home=tmp_path/'another-project/research_runs';foreign_home.mkdir(parents=True)
    foreign=foreign_home/'RUN-foreign.json';foreign.write_text('{"controlled":"not opened"}')
    (index_home/'index.json').write_text(json.dumps({'runs':['RUN-foreign'],'run_handles':{'RUN-foreign':{
        'id':'RUN-foreign','project':'p','launch_token':'forged','job_path':foreign.relative_to(tmp_path).as_posix()}}}))
    original=Path.open
    def no_foreign(path,*a,**kw):
        if path==foreign:pytest.fail('Foreign job read before actual project locator scope')
        return original(path,*a,**kw)
    with monkeypatch.context() as patch:
        patch.setattr(Path,'open',no_foreign)
        choices=Runs.evidence_candidates(tmp_path,'p')
        code,value=Runs.run_status_read('p','RUN-foreign',tmp_path)
    assert not choices['items'] and choices['issues'] and code==200 and value['state']=='UNAVAILABLE'


def test_exact_owner_target_for_http_only_and_pinned_source_evidence(tmp_path):
    scope,_=scene(tmp_path)
    source=tmp_path/'public-source';source.mkdir();code=source/'input.py';code.write_text('PUBLIC = 1\n')
    (tmp_path/'profiles').mkdir();(tmp_path/'profiles/writing_sources.json').write_text(json.dumps({'repositories':{'public':str(source)}}))
    task=W._tasks('p',tmp_path)['work'];basis,_=W._work_basis(W._tasks('p',tmp_path),'work')
    W.transition('p',{'id':'work','status':'done','expected_work_scope_revision':basis['scope_revision'],
        'expected_work_status_revision':W._standing_revision(task),'evidence':['proj/manuscript/main.tex','public-source/input.py']},tmp_path)
    page=read(tmp_path,scope,{'demand':'relationships','limit':24})
    rows=[r for r in page['items'] if r['kind']=='associated-evidence']
    tex=next(r for r in rows if r['target']['path'].endswith('.tex'))
    assert tex['owner_target']['path']=='manuscript/main.tex' and tex['owner_target']['scope']=='project'
    assert 'operation' not in tex['read'] and tex['owner_target']['expected_sha256']==tex['consumed_revision']
    code_row=next(r for r in rows if r['target']['path'].endswith('.py'))
    assert code_row['owner_target']['target']=={'owner':'repository','repository':'public','path':'input.py'}
    assert code_row['read']['payload']['expected_sha256']==code_row['consumed_revision']
    assert 'expected_sha256' not in code_row['current_read']['payload']
    from laplace.projects import library
    value=library.material_references('p',tmp_path,**code_row['read']['payload'])
    assert 'PUBLIC = 1' in json.dumps(value)
    code.write_text('PUBLIC = 2\n')
    with pytest.raises(ValueError):library.material_references('p',tmp_path,**code_row['read']['payload'])
    (tmp_path/'owner-target-sample.json').write_text(json.dumps(page,indent=2))


def test_trail_uses_only_existing_session_header_title(tmp_path,monkeypatch):
    scope,_=scene(tmp_path)
    from laplace.representation import writing_bodies
    monkeypatch.setattr(writing_bodies,'read_bytes',lambda *a,**k:pytest.fail('Conversation body for a label'))
    page=read(tmp_path,scope,{'demand':'relationships','limit':24})
    turn=next(row for row in page['items'] if row['kind']=='conversation-turn')
    assert turn['label']==turn['session_title']=='Controlled public conversation'
    assert turn['label_complete'] and turn['request_preview_state']=='NOT_CAPTURED_IN_METADATA'
    artifact=next(row for row in page['items'] if row['kind']=='artifact-receipt')
    assert artifact['label']=='answer.md' and artifact['label_origin']=='recorded-artifact-path'
    (tmp_path/'human-trail-metadata-sample.json').write_text(json.dumps(page,indent=2))


def test_declared_writing_source_choice_without_art_or_source_body(tmp_path,monkeypatch):
    from laplace.projects import library
    from laplace.pipeline import registry
    code,result=library.create({'name':'book','kind':'book','title':'Public Writing source Ω'},tmp_path)
    assert code==201
    W.task('book',{'id':'write','title':'Finish a useful paragraph','goal':'Keep the ordinary Writing output selectable'},tmp_path)
    item=registry.resolve('book',repo_root=tmp_path);document=item.manifest['document'];main=item.path(document['manuscript_dir'],tmp_path)/document['root']
    assert main.is_file()
    with records.index_lock:
        assert not [r for r in records.index(tmp_path).by_project.get('book',[]) if r.get('record')=='writing-artifact']
    original_text=Path.read_text;original_bytes=Path.read_bytes
    def no_text(path,*a,**kw):
        if path.suffix=='.tex':pytest.fail('Source body read to enumerate evidence')
        return original_text(path,*a,**kw)
    def no_bytes(path,*a,**kw):
        if path.suffix=='.tex':pytest.fail('Source body hash to enumerate evidence')
        return original_bytes(path,*a,**kw)
    with monkeypatch.context() as patch:
        patch.setattr(Path,'read_text',no_text);patch.setattr(Path,'read_bytes',no_bytes)
        value=V.read('book',{'view':'provenance','id':'write','request':{'demand':'choices'}},tmp_path,native_caller=O.project_scope('book','native'))
    selected=next(row for row in value['items'] if row['owner']=='manuscript-source')
    assert selected['evidence_value']==main.relative_to(tmp_path).as_posix() and selected['currentness']=='NOT_CHECKED'
    assert 'completion_support' not in selected and selected['owner_target']['path'].endswith(main.name)
    before=main.read_bytes()
    (tmp_path/'writing-choice-sample.json').write_text(json.dumps(value,indent=2))
    assert main.read_bytes()==before


def test_research_work_facet_reuses_detail_lifecycle_activity_and_titles(tmp_path,monkeypatch):
    from laplace.work import object_facets as F
    from laplace.writing import workflow_progression
    scope,_=scene(tmp_path)
    W.task('p',{'id':'needed','title':'Read the actual source first','goal':'A real prerequisite'},tmp_path)
    task=W._tasks('p',tmp_path)['work']
    W.task('p',{'id':'work','depends_on':['needed'],'expected_work_revision':W._task_revision(task)},tmp_path)
    calls=[];original=W.read
    def counted(*a,**kw):
        value=original(*a,**kw);calls.append(value);return value
    monkeypatch.setattr(W,'read',counted)
    monkeypatch.setattr(workflow_progression,'work_facet',lambda *a,**kw:None) # unrelated run attachment omitted
    value=F.request(tmp_path,scope,{'facet':'object','reference':O.work_reference('p','work')})
    assert len(calls)==1
    standing=value['facets']['standing']['value'];row=calls[0]['task']
    for key in ('lifecycle','activity','standing','readiness','current_acceptance','status','recorded_status'):
        assert standing[key]==row[key]
    relation=value['facets']['relationships']['items'][0]
    assert relation['title']=='Read the actual source first' and relation['title_state']=='AVAILABLE'
    (tmp_path/'research-task-standing-sample.json').write_text(json.dumps(value,indent=2))


def test_logical_run_id_never_selects_outside_metadata_family(tmp_path,monkeypatch):
    from laplace.research import research_context as C,research_runs as Runs
    scene(tmp_path);_,home=C.project('p',tmp_path);runs=home/'research_runs';runs.mkdir()
    outside=home/'RUN-confused.json';outside.write_text('{"id":"../RUN-confused","project":"p"}')
    (runs/'index.json').write_text(json.dumps({'runs':['../RUN-confused']}))
    original=Path.open
    def forbidden(path,*a,**kw):
        if path==outside:pytest.fail('A Run ID escaped its metadata family')
        return original(path,*a,**kw)
    with monkeypatch.context() as patch:
        patch.setattr(Path,'open',forbidden)
        candidates=Runs.evidence_candidates(tmp_path,'p')
        code,value=Runs.run_status_read('p','../RUN-confused',tmp_path)
    assert candidates['items']==[] and candidates['issues'] and code==400 and 'logical Run ID' in value['error']
