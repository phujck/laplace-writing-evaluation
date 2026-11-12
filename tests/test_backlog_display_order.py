"""Display ordering over full owner eligibility, not an execution decision."""
import copy,json
import pytest
from laplace.work import backlog as B,project_work as W,project_work_views as V


def authored(root,ident,priority,*,depends=(),done=False):
    W.task('p',{'id':ident,'title':'Public '+ident,'goal':'Exact display order '+ident,'depends_on':list(depends)},root)
    raw=W._tasks('p',root)[ident];basis,_=W._work_basis(W._tasks('p',root),ident)
    if done:
        (root/'public-proof.txt').write_text('Exact public completion evidence')
        W.transition('p',{'id':ident,'status':'done','expected_work_scope_revision':basis['scope_revision'],
            'expected_work_status_revision':W._standing_revision(raw),'expected_dependency_revision':W._dependency_revision(raw,W._tasks('p',root)),
            'evidence':['public-proof.txt']},root)
    wire=copy.deepcopy(B.inspect_planning('p',ident,root)['actions']['planning']['http']['payload'])
    wire['planning'].update(priority=priority,order=0,deferred=False,reason='Public explicit preference only')
    W.task('p',wire,root)


def test_observed_high_priority_with_hidden_satisfied_history(tmp_path):
    authored(tmp_path,'completed-history',0,done=True)
    authored(tmp_path,'current-human-workspace',1000,depends=['completed-history'])
    authored(tmp_path,'campaign',900)
    authored(tmp_path,'p6',650)
    before=W._ledger(tmp_path).read_bytes()
    page=V.read('',{'view':'catalogue','namespace':'p','lifecycle_group':'unfinished','limit':100},tmp_path)
    rows=page['rows'];ids=[r['id'] for r in rows]
    (tmp_path/'observed-order-proof.json').write_text(json.dumps(page,indent=2))
    assert ids[0]=='current-human-workspace'
    full=W._resolved_tasks(W._tasks('p',tmp_path),tmp_path)
    history=next(r for r in full if r['id']=='completed-history')
    active=next(r for r in full if r['id']=='current-human-workspace')
    assert history['readiness']['satisfies_prerequisites'] is True
    assert active['readiness']['blocked_by']==[] and active['readiness']['status']=='READY'
    assert before==W._ledger(tmp_path).read_bytes()


def item(ident,priority=0,depends=(),satisfied=False,closed=False):
    return {'id':ident,'depends_on':list(depends),'planning':{'priority':priority,'order':0,'deferred':False,'reason':''},
        'readiness':{'status':'CLOSED' if closed else 'BLOCKED','satisfies_prerequisites':satisfied}}


def test_visible_dependency_hidden_unmet_bridge_and_actual_satisfaction():
    full=[item('necessary',-10),item('bridge',0,['necessary'],closed=True),item('child',1000,['bridge']),item('independent',500)]
    selected=[full[0],full[2],full[3]]
    before=copy.deepcopy(full)
    result=B.display_preferred(full,selected)
    assert [r['id'] for r in result]==['independent','necessary','child']
    assert full==before and result[-1]['depends_on']==['bridge'] # original authority/edge unchanged
    full[1]['readiness']['satisfies_prerequisites']=True
    assert [r['id'] for r in B.display_preferred(full,selected)]==['child','independent','necessary']
    # Visible unsatisfied prerequisites precede children even against priority.
    assert [r['id'] for r in B.display_preferred([full[0],item('child',1000,['necessary'])],[full[0],item('child',1000,['necessary'])])]==['necessary','child']


def test_cycles_missing_and_legacy_meaningful_order():
    full=[item('first',0,['hidden']),item('hidden',0,['second']),item('second',0,['first']),item('missing',0,['absent'])]
    assert [r['id'] for r in B.display_preferred(full,[full[0],full[2],full[3]])]==['missing','first','second']
    assert [r['id'] for r in B.display_preferred(full,full)]==['missing','first','hidden','second']
    legacy=[{'id':'old-child','depends_on':['old-prerequisite']},{'id':'old-independent'},{'id':'old-prerequisite'}]
    assert [r['id'] for r in B.display_preferred(legacy,legacy)]==['old-independent','old-prerequisite','old-child']
    assert [r['id'] for r in B.display_preferred(legacy,legacy[1:])]==['old-independent','old-prerequisite']


def test_filter_order_cut_excludes_page_knobs_and_retains_scope(tmp_path,monkeypatch):
    for ident in ('a','b','c'):authored(tmp_path,ident,0)
    query={'view':'catalogue','namespace':'p','lifecycle_group':'unfinished','limit':1}
    first=V.read('',query,tmp_path)
    assert first['pagination']['next_read']
    larger=V.read('',{**query,'limit':3},tmp_path)
    assert larger['read_cut']['revision']==first['read_cut']['revision']
    held=first['pagination']['next_read']['payload']
    assert V.read('',held,tmp_path)['rows'][0]['id']=='b'
    for change in ({'q':'Public'},{'planning_filter':'not-deferred'}):
        with pytest.raises(W.WorkConflict):V.read('',{**held,**change},tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(B,'ORDERING_VERSION','different-interpretation')
        with pytest.raises(W.WorkConflict):V.read('',held,tmp_path)
    def forbidden(*a,**k):pytest.fail('Foreign namespace lookup')
    monkeypatch.setattr(V,'_snapshot',forbidden)
    with pytest.raises(ValueError,match='scope'):B.catalogue(tmp_path,{'namespace':'foreign'},mode='review',caller_project='p')
