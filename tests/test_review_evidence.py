"""Public scoped Work review evidence delivery; no provider or live state."""
import hashlib,json
import pytest
from laplace.work import project_work as W,project_work_review as R,project_work_views as V,owner_discovery as O


def scene(root,monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE',str(root/'state'))
    (root/'contract').mkdir();(root/'src').mkdir();(root/'src/input.py').write_text('public = 1\n')
    obligations=[{'id':'source','scope':'source','label':'Source correctness','independent':False,'inputs':['src/input.py']},
        {'id':'hold','scope':'guide','label':'Guide qualification','independent':False,'inputs':['src/input.py']},
        {'id':'optional','scope':'other','label':'Optional review','required':False}]
    W.task('p',{'id':'selected','title':'A public change','goal':'Read exact review evidence','review_obligations':obligations},root)
    W.task('p',{'id':'legacy','title':'Legacy work','goal':'Unmanaged remains unmanaged'},root)
    guard=W._task_revision(W._tasks('p',root)['selected']);pin='sha256:'+hashlib.sha256((root/'src/input.py').read_bytes()).hexdigest()
    handoff=R.record('p',{'id':'selected','phase':'handoff','request_id':'public-handoff-001','expected_work_revision':guard,'object':{'kind':'source'},'pins':{'src/input.py':pin}},root)
    for ident,verdict in [('source','ACCEPT'),('hold','HOLD')]:
        R.record('p',{'id':'selected','phase':'review','request_id':'public-review-'+ident,'expected_work_revision':guard,'handoff_id':handoff['phase']['id'],'obligation_id':ident,'verdict':verdict},root)
    return O.owned_workspace('sdk')


def read(root,scope,request=None,ident='selected'):
    return V.read('',{'namespace':'p','view':'review-evidence','id':ident,'request':request or {}},root,native_caller=scope)


def test_aggregate_one_fact_path_no_rich_or_body_delivery(tmp_path,monkeypatch):
    scope=scene(tmp_path,monkeypatch)
    expected=R.facet(W._tasks('p',tmp_path)['selected'],tmp_path,tasks=W._tasks('p',tmp_path))
    monkeypatch.setattr(R,'_facet',lambda *a,**k:(_ for _ in ()).throw(AssertionError('rich facade')))
    monkeypatch.setattr(R,'phase_read',lambda *a,**k:(_ for _ in ()).throw(AssertionError('phase hydration')))
    a=read(tmp_path,scope)
    assert a['counts']['required']==2 and a['counts']['satisfied_required']==1 and a['counts']['remaining_required']==len(expected['remaining'])==1
    assert a['counts']['by_independence']=={'SELF':2,'NOT_RECORDED':1} and a['inspection']=={'metadata':'NOT_EXPANDED','bodies':'NOT_READ'}
    assert read(tmp_path,scope,ident='legacy')['managed'] is False and read(tmp_path,scope,ident='legacy')['counts'] is None


def test_issued_page_support_phase_and_second_stale_input(tmp_path,monkeypatch):
    scope=scene(tmp_path,monkeypatch);a=read(tmp_path,scope);page=V.read('',a['enumerate_reads']['all']['payload'],tmp_path,native_caller=scope)
    support=V.read('',page['items'][0]['support_read']['payload'],tmp_path,native_caller=scope)
    item=support['support']['items'][0];assert item['body_inspection']=='NOT_READ' and item['declared_inputs']==['src/input.py']
    phase=next(row['read'] for row in item['inspection_routes'] if row['kind']=='review')
    assert phase['payload']['phase_revision'];V.read('',phase['payload'],tmp_path,native_caller=scope)
    (tmp_path/'src/input.py').write_text('public = 2\n');b=read(tmp_path,scope)
    (tmp_path/'src/input.py').write_text('public = 3\n');c=read(tmp_path,scope)
    assert b['counts']==c['counts'] and a['observation']['token']!=b['observation']['token']!=c['observation']['token']
    with pytest.raises(W.WorkConflict) as error:V.read('',a['enumerate_reads']['all']['payload'],tmp_path,native_caller=scope)
    assert error.value.details['restart_read']['payload']['request']['demand']=='aggregate'


def test_scope_refuses_before_lookup(tmp_path,monkeypatch):
    monkeypatch.setattr(W,'_tasks',lambda *a,**k:(_ for _ in ()).throw(AssertionError('lookup before Scope')))
    for scope in (None,O.project_scope('foreign','native')):
        with pytest.raises(ValueError,match='scope'):read(tmp_path,scope)


def test_empty_guard_fields_never_reach_lookup(tmp_path,monkeypatch):
    monkeypatch.setattr(V,'_snapshot',lambda *a,**k:(_ for _ in ()).throw(AssertionError('foreign lookup')))
    for extra in ({'obligation_id':''},{'phase_revision':'','phase_id':'PHASE-absent'}):
        with pytest.raises(ValueError):V.read('p',{'namespace':'foreign','view':'review','id':'selected',**extra},tmp_path,native_caller=O.project_scope('p','native'))


def test_selected_support_sharing_roundtrip_and_guarded_phase_append(tmp_path,monkeypatch):
    from laplace.work import review_evidence as E
    import copy
    scope=scene(tmp_path,monkeypatch);a=read(tmp_path,scope)
    page=V.read('',a['enumerate_reads']['all']['payload'],tmp_path,native_caller=scope)
    full=V.read('',page['support_read']['payload'],tmp_path,native_caller=scope)
    support=full['support'];assert support['binding']['ids']==[item['id'] for item in page['items']]
    # Three units share one exact handed phase. One-unit response remains inline.
    assert support['encoding']=='descriptor-table'
    decoded=[]
    for item in support['items']:
        routes=[]
        for index in item['inspection_refs']:
            descriptor=support['descriptors'][index]
            assert descriptor['id']==index and descriptor['sha256']==R._digest(descriptor['route'])
            routes.append(descriptor['route'])
        decoded.append({**{k:v for k,v in item.items() if k!='inspection_refs'},'inspection_routes':routes})
    inline={'encoding':'inline','binding':support['binding'],'items':decoded}
    assert E._size(support)<E._size(inline)
    for item in decoded:
        individual=V.read('',next(row['support_read']['payload'] for row in page['items'] if row['id']==item['id']),tmp_path,native_caller=scope)
        assert individual['support']['encoding']=='inline' and individual['support']['items']==[item]
    # Preserve repeated descriptor positions, not just a set.
    repeated=copy.deepcopy(inline)
    repeated['items']=[{**decoded[0],'inspection_routes':[decoded[0]['inspection_routes'][-1]]*12}]
    packed=E._share_routes(repeated);assert packed['encoding']=='descriptor-table' and packed['items'][0]['inspection_refs']==[0]*12
    bad=copy.deepcopy(page['support_read']['payload']);bad['request']['ids']=['not-enumerated']
    with pytest.raises(ValueError,match='enumerated page'):V.read('',bad,tmp_path,native_caller=scope)
    route=next(route['read'] for route in decoded[0]['inspection_routes'] if route['kind']=='review')
    tasks=W._tasks('p',tmp_path);record=next(row for row in tasks['selected']['phases'] if row['id']==route['payload']['phase_id'])
    W._append(tmp_path,{**record,'summary':'appended public same-ID row'})
    with pytest.raises(W.WorkConflict) as error:V.read('',route['payload'],tmp_path,native_caller=scope)
    assert error.value.details['kind']=='PHASE_CHANGED'
    V.read('',error.value.details['current_read']['payload'],tmp_path,native_caller=scope)
    old={k:v for k,v in route['payload'].items() if k!='phase_revision'}
    assert len(V.read('',old,tmp_path)['phase']['rows'])==2
    (tmp_path/'support-proof.json').write_text(json.dumps({'page':page,'support':full,'decoded_inline':inline,'shared_bytes':E._size(support),'inline_bytes':E._size(inline)},indent=2))


def test_zero_missing_and_declared_work_restart(tmp_path,monkeypatch):
    scope=scene(tmp_path,monkeypatch)
    W.task('p',{'id':'zero','title':'Optional only','goal':'No required ratio','review_obligations':[{'id':'optional','scope':'other','label':'Optional','required':False}]},tmp_path)
    zero=read(tmp_path,scope,ident='zero');assert zero['counts']['required']==zero['counts']['remaining_required']==0
    assert not any('ratio' in key or 'percentage' in key for key in zero['counts'])
    a=read(tmp_path,scope);(tmp_path/'src/input.py').unlink();missing=read(tmp_path,scope)
    raw=W._tasks('p',tmp_path);rich=R.facet(raw['selected'],tmp_path,tasks=raw)
    assert missing['counts']['remaining_required']==len(rich['remaining']) and missing['observation']['token']!=a['observation']['token']
    W.task('p',{'id':'selected','goal':'A revised material goal','expected_work_revision':W._task_revision(raw['selected'])},tmp_path)
    with pytest.raises(W.WorkConflict):V.read('',missing['enumerate_reads']['all']['payload'],tmp_path,native_caller=scope)


def test_source_consumed_segment_locality_and_partial_coverage(tmp_path,monkeypatch):
    from laplace.work import source_contracts as SC
    scope=scene(tmp_path,monkeypatch)
    declaration={'schema':SC.SCHEMA,'owner':'public.owner','operation':'public.operation','purpose':'Public source fixture',
        'segments':{'consumed':{'value':1},'missing':{'value':2},'unrelated':{'value':3}},
        'relations':[{'consumer':'public.consumer','relation':'consumes','segments':['consumed','missing']}]}
    def current(owner,operation):
        if owner!='public.owner':raise ValueError('Not public owner')
        return SC.detached(declaration)
    monkeypatch.setattr(SC,'declaration',current)
    binding={'owner':'public.owner','operation':'public.operation','consumer':'public.consumer','segments':['consumed']}
    W.task('p',{'id':'bound','title':'Bound Source','goal':'Observe exact consumed segments','review_obligations':[
        {'id':'source','scope':'source','label':'Partial Source','independent':False,'source_contract':binding}]},tmp_path)
    guard=W._task_revision(W._tasks('p',tmp_path)['bound'])
    h=R.record('p',{'id':'bound','phase':'handoff','request_id':'bound-handoff-001','expected_work_revision':guard,'object':{'kind':'source'}},tmp_path)
    R.record('p',{'id':'bound','phase':'review','request_id':'bound-review-001','expected_work_revision':guard,'handoff_id':h['phase']['id'],'obligation_id':'source','verdict':'ACCEPT'},tmp_path)
    a=read(tmp_path,scope,ident='bound');assert a['counts']['obligations_with_known_missing_source_segments']==1 and a['counts']['source_bound_obligations']==1
    declaration['segments']['unrelated']['value']=4
    assert read(tmp_path,scope,ident='bound')['observation']==a['observation']
    declaration['segments']['consumed']['value']=5;b=read(tmp_path,scope,ident='bound')
    declaration['segments']['consumed']['value']=6;c=read(tmp_path,scope,ident='bound')
    assert b['counts']==c['counts'] and a['observation']!=b['observation']!=c['observation']
    monkeypatch.setattr(SC,'declaration',lambda *args:(_ for _ in ()).throw(ValueError('Public owner unavailable')))
    unavailable=read(tmp_path,scope,ident='bound');assert unavailable['counts']['by_currentness']=={'UNKNOWN':1}
    (tmp_path/'source-proof.json').write_text(json.dumps({'partial':a,'changed':b,'second_changed':c,'unavailable':unavailable},indent=2))


def test_effective_closure_work_and_existing_delivery_line(tmp_path,monkeypatch):
    from laplace.work import review_evidence as E,project_work_navigation as N
    from laplace.writing import delivery
    scope=scene(tmp_path,monkeypatch)
    W.task('p',{'id':'closure','title':'Close public follow-up','goal':'Complete with real evidence'},tmp_path)
    raw=W._tasks('p',tmp_path);child=raw['closure']
    W.transition('p',{'id':'closure','status':'done','evidence':['src/input.py'],
        'expected_work_scope_revision':W._work_basis(raw,'closure')[0]['scope_revision'],
        'expected_dependency_revision':W._dependency_revision(child,raw),'expected_work_status_revision':W._standing_revision(child)},tmp_path)
    W.task('p',{'id':'parent-closure','title':'Parent closure','goal':'Effective closure meaning','review_obligations':[{'id':'closure','scope':'closure','label':'Required closure','closure_work_id':'closure'}]},tmp_path)
    assert read(tmp_path,scope,ident='parent-closure')['counts']['satisfied_required']==1
    (tmp_path/'src/input.py').write_text('changed closure evidence')
    assert W._tasks('p',tmp_path)['closure']['status']=='done'
    assert read(tmp_path,scope,ident='parent-closure')['counts']['remaining_required']==1
    # The owner consumes the exact existing effective line, including smaller native plans.
    with delivery.planned(line=8000):
        assert E._cap()==N.line()==8000
        a=read(tmp_path,scope);page=V.read('',a['enumerate_reads']['all']['payload'],tmp_path,native_caller=scope)
        assert E._size(a)<=8000 and E._size(page)<=8000
        ids=[]
        while True:
            ids.extend(item['id'] for item in page['items'])
            if not page['enumeration']['next_read']:break
            page=V.read('',page['enumeration']['next_read']['payload'],tmp_path,native_caller=scope);assert E._size(page)<=8000
        assert ids==['source','hold','optional']
    (tmp_path/'closure-proof.json').write_text(json.dumps({'closure':read(tmp_path,scope,ident='parent-closure'),'line':8000,'enumerated_ids':ids},indent=2))


def test_issued_support_survives_delivery_line_change(tmp_path,monkeypatch):
    from laplace.writing import delivery
    from laplace.work import review_evidence as E
    scope=scene(tmp_path,monkeypatch)
    with delivery.planned(line=8000):
        a=read(tmp_path,scope);page=V.read('',a['enumerate_reads']['all']['payload'],tmp_path,native_caller=scope)
        assert page['enumeration']['covered']<page['enumeration']['known']
    result=V.read('',page['support_read']['payload'],tmp_path,native_caller=scope)
    assert result['support']['binding']['ids']==[row['id'] for row in page['items']]
    # No current-budget page construction is required to inspect a held prefix.
    monkeypatch.setattr(E,'_page',lambda *a,**k:(_ for _ in ()).throw(AssertionError('repacked old page')))
    with delivery.planned(line=8000):
        assert V.read('',page['items'][0]['support_read']['payload'],tmp_path,native_caller=scope)['support']['items'][0]['id']=='source'
