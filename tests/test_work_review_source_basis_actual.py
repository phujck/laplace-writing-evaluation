"""Actual Work/native/HTTP consumption of the frozen Source owner over public data.

Session/turn/evaluator event rows are synthetic identity controls, not paid app
admission. Grant/candidate/apply/handoff/review/currentness execute real owners.
"""
import copy
import json
import pytest
from laplace.work import project_work as W, project_work_review as R, development_source as D, work_delivery
from laplace.native import tools
from laplace.web import project_work_surface as HTTP
from test_source_use_joins import source, candidate


def ready(s):
    changed=candidate(s,edits=[{'old':'unique old','new':'new chosen'}])
    result=D.apply(s['root'],'public',{'candidate_id':changed['candidate_id']},s['door'])
    assert result['effect']['state']=='COMMITTED'
    return {'grant_id':s['grant']['id'],'candidate_id':changed['candidate_id']},{p:D._pin(s['checkout']/p) for p in ['src/answer.py','evaluator.py','guide.md']}


def guard(s,work='work'):
    return W._task_revision(W._tasks('public',s['root'])[work])


def handoff(s,selection,pins,*,request='actual-source-handoff',obligations=None,work='work',turn='WT-parent',http=False):
    payload={'id':work,'phase':'handoff','request_id':request,'expected_work_revision':guard(s,work),'source_basis':selection,'pins':pins,
             'object':{'repository':'display label only'}}
    if obligations is not None:payload['obligations']=obligations
    if http:
        code,_,body=HTTP.handle('/work/review',{},'POST',json.dumps({'project':'public',**payload}).encode(),s['root'])
        assert code==200,body
        return json.loads(body)
    return tools.execute(s['root'],'public','work','work_review',payload,turn_id=turn)


def admit_fixture_evaluator(s,revision=None):
    # Explicitly synthetic Work-delivery identity record, matching the producer fixture boundary.
    W._append(s['root'],{'record':work_delivery.RECORD,'kind':work_delivery.EVENT,'id':'WD-consumer-synthetic',
        'project':'public','work_id':'work','session_id':s['review']['id'],'state':'ADMITTED',
        'recipient':{'id':s['binding']['id'],'revision':revision or s['binding']['revision']}})


def review(s,h,obligation='source',request='actual-source-review',turn='WT-review',**extra):
    return tools.execute(s['root'],'public','review','work_review',{'id':'work','phase':'review','request_id':request,
        'expected_work_revision':guard(s),'handoff_id':h['phase']['id'],'obligation_id':obligation,'verdict':'ACCEPT',**extra},turn_id=turn)


def standing(s):
    task=W._tasks('public',s['root'])['work']
    return {row['id']:row for row in R.facet(task,s['root'])['obligations']}


def test_actual_native_covered_subset_and_original_evaluator_identity(source):
    s=source;selection,pins=ready(s);covered={p:pins[p] for p in ['src/answer.py','evaluator.py']}
    h=handoff(s,selection,covered,obligations=['source']);assert h['phase']['pins']==covered
    assert h['phase']['source_basis']['pins']==covered and 'checkout' not in h['phase']['source_basis']
    assert not (s['root']/'src/answer.py').exists() and not (s['root']/'evaluator.py').exists()
    before=W._ledger(s['root']).read_bytes()
    with pytest.raises(ValueError,match='actual original evaluator'):review(s,h)
    assert W._ledger(s['root']).read_bytes()==before
    admit_fixture_evaluator(s,revision='sha256:'+'0'*64)
    with pytest.raises(ValueError,match='actual original evaluator'):review(s,h)
    admit_fixture_evaluator(s);r=review(s,h);assert r['phase']['independence']=='INDEPENDENT'
    assert r['phase']['source_basis']==h['phase']['source_basis'];assert standing(s)['source']['satisfied']
    # Source effect != review acceptance: guide is still unhanded/unreviewed.
    assert not standing(s)['guide']['satisfied']
    (s['root']/'actual-source-native-proof.json').write_text(json.dumps({'handoff':h,'review':r,'standing':standing(s),'synthetic_identity_records':True},indent=2)+'\n')


def test_actual_http_handoff_and_native_reviews_keep_consumed_locality_and_detachment(source):
    s=source;selection,pins=ready(s);h=handoff(s,selection,pins,http=True);admit_fixture_evaluator(s)
    sr=review(s,h);gr=review(s,h,'guide','actual-guide-review')
    assert standing(s)['source']['satisfied'] and standing(s)['guide']['satisfied']
    original=copy.deepcopy(h['phase']['source_basis']);sr['phase']['source_basis']['pins']['src/answer.py']='caller edit'
    assert W._tasks('public',s['root'])['work']['phases'][-1]['source_basis']==original
    (s['checkout']/'guide.md').write_text('later unrelated guide')
    state=standing(s);assert state['source']['satisfied'] and state['guide']['currentness']=='STALE'
    (s['checkout']/'src/answer.py').write_text('later source change')
    state=standing(s);assert state['source']['currentness']=='STALE'
    (s['checkout']/'src/answer.py').unlink()
    state=standing(s);assert state['source']['currentness']=='UNKNOWN'
    (s['root']/'actual-source-locality-proof.json').write_text(json.dumps({'handoff':h,'source_review':sr,'guide_review':gr,'standing_after_missing':state,'synthetic_identity_records':True},indent=2)+'\n')


def test_actual_expired_write_grant_preserves_replay_and_new_historical_review(source):
    s=source;selection,pins=ready(s);h=handoff(s,selection,pins);admit_fixture_evaluator(s)
    task=W._tasks('public',s['root'])['work'];grant=copy.deepcopy(D._latest(task,'grant',s['grant']['id']));grant['expires_at']='2000-01-01T00:00:00+00:00';W._append(s['root'],grant)
    assert handoff(s,selection,pins)['status']=='REUSED'
    r=review(s,h);assert r['phase']['independence']=='INDEPENDENT' and standing(s)['source']['satisfied']
    before=W._ledger(s['root']).read_bytes()
    with pytest.raises(D.GrantRefused):handoff(s,selection,pins,request='fresh-expired-handoff')
    assert W._ledger(s['root']).read_bytes()==before
    # Historical validation never makes the same source grant writable again.
    with pytest.raises(D.GrantRefused):candidate(s,edits=[{'old':'new chosen','new':'forbidden later edit'}])
    (s['root']/'actual-source-expiry-proof.json').write_text(json.dumps({'review':r,'standing':standing(s),'expired_grant':grant['id'],'new_write_refused':True,'synthetic_identity_records':True},indent=2)+'\n')


def test_actual_wrong_work_holder_and_coverage_refuse_before_work_phase(source):
    s=source;selection,pins=ready(s);before=W._ledger(s['root']).read_bytes()
    with pytest.raises(ValueError,match='holder|session'):handoff(s,selection,pins,turn='WT-other')
    with pytest.raises(ValueError,match='every declared input'):handoff(s,selection,{'src/answer.py':pins['src/answer.py']})
    assert W._ledger(s['root']).read_bytes()==before
    W.task('public',{'id':'other-work','title':'Other Work','goal':'No adoption','review_obligations':[{'id':'source','scope':'source','label':'source','inputs':['src/answer.py']}]},s['root'])
    before=W._ledger(s['root']).read_bytes()
    with pytest.raises(ValueError,match='another Work'):handoff(s,selection,pins,work='other-work')
    assert W._ledger(s['root']).read_bytes()==before


def test_actual_retarget_missing_and_typed_review_payload_never_fall_back(source):
    s=source;selection,pins=ready(s);h=handoff(s,selection,pins);admit_fixture_evaluator(s);r=review(s,h)
    config=s['root']/'profiles/writing_sources.json';old=config.read_bytes();config.write_text(json.dumps({'repositories':{'selected':str(s['root'])}}))
    assert standing(s)['source']['currentness']=='STALE'
    before=W._ledger(s['root']).read_bytes()
    with pytest.raises(ValueError,match='CHANGED_INPUT'):review(s,h,request='retargeted-review')
    assert W._ledger(s['root']).read_bytes()==before
    config.write_bytes(old);(s['checkout']/'evaluator.py').unlink()
    assert standing(s)['source']['currentness']=='UNKNOWN'
    payload={'project':'public','id':'work','phase':'review','request_id':'cannot-replace-source-basis','expected_work_revision':guard(s),
             'handoff_id':h['phase']['id'],'obligation_id':'source','verdict':'ACCEPT','source_basis':selection}
    code,_,body=HTTP.handle('/work/review',{},'POST',json.dumps(payload).encode(),s['root']);assert code>=400 and json.loads(body)['error']
    assert W._ledger(s['root']).read_bytes()==before
