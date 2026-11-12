"""Qualified Source delivery through real owners to a withheld paid execution boundary.

Public separate-checkout fixture and synthetic original-holder rows are reused.
Session and turn admission, WD reservation/recovery, native review and terminal
hooks are real. turn_execution.start alone is replaced; no provider runs.
"""
import copy
import json
from urllib.parse import urlsplit,parse_qs
import pytest
from laplace.work import project_work as W,development_source as D,work_delivery as WD
from laplace.writing import records,turn_admission,turn_execution,turn_jobs,provider
from laplace.native import tools
from laplace.projects import writing_sources
from laplace.web import project_work_surface as HTTP
from test_source_use_joins import source
from test_work_review_source_basis_actual import ready,handoff,guard


@pytest.fixture
def transport(source,monkeypatch):
    s=source;launches=[]
    # Ordinary turn admission requires a voice; this exact public fixture owns its
    # synthetic default-profile bytes. No author/deployed profile is copied.
    profile=s['root']/'profiles/voice/gerard-technical-v1.md';profile.parent.mkdir(parents=True);profile.write_text('# Public fixture voice\nVersion: public-v1\nUse precise public language.\n')
    catalogue={'providers':[{'id':'codex','available':True,'models':[{'id':'gpt-6.1-sol','efforts':['low','medium','high'],'supports_effort':True}]}]}
    monkeypatch.setattr(provider,'capabilities',lambda *a,**k:catalogue)
    monkeypatch.setattr(provider,'context_window_advertised',lambda *a,**k:None)
    monkeypatch.setattr(turn_execution,'start',lambda launch:launches.append(launch))
    yield s,launches
    # No execution thread was started. Finish only these fixture-owned jobs via
    # their existing cleanup, without inventing a provider reply or rerunning work.
    for launch in launches:
        if not launch.job.get('done'):turn_execution._finish(launch,{'status':'interrupted'})


def submit(s,h,**extra):
    return WD.submit(s['root'],'public',{'action':'submit','work_id':'work','expected_work_revision':guard(s),
        'handoff_id':h['phase']['id'],'obligation_id':'source','recipient_binding_id':s['binding']['id'],
        'max_attempts':2,'deadline_s':60,'parent_return':{'admit_idle':True,'max_attempts':1,'max_depth':1},**extra},s['door'])


def original(s):
    selection,pins=ready(s);return handoff(s,selection,pins)


def test_retained_submit_counterexample_reaches_original_recipient_and_exact_reads(transport):
    s,launches=transport;h=original(s)
    assert D.validate_review_basis(s['root'],'public','work',h['phase']['source_basis'])['status']=='CURRENT'
    assert not (s['root']/'src/answer.py').exists()
    result=submit(s,h);event=result['event'];assert event['state']=='ADMITTED',event
    assert len(launches)==1 and launches[0].mode=='review';launch=launches[0]
    assert event['recipient']['id']==s['binding']['id'] and event['recipient']['revision']==s['binding']['revision']
    assert event['continuation']['parent_session_id']==s['parent']['id']
    assert event['source_basis']==h['phase']['source_basis']
    text=records.fold_records(s['root'])['turns'][launch.turn_id]['text']
    reads=json.loads(next(line.removeprefix('Pinned repository reads (follow each owner-issued next page): ').split('. Read permission',1)[0]
        for line in text.splitlines() if line.startswith('Pinned repository reads')))
    assert {x['payload']['path'] for x in reads}=={'src/answer.py','evaluator.py'} and 'guide.md' not in text
    for handle in reads:
        page=writing_sources.execute(s['root'],handle['payload']);assert 'sha256:'+page['source']['sha256'].removeprefix('sha256:')==h['phase']['pins'][handle['payload']['path']]
        native_page=tools.execute(s['root'],'public','review',handle['operation'],handle['payload'],turn_id=launch.turn_id)
        assert native_page['content']==page['content']
    issued=json.loads(next(line.removeprefix('Exact qualified handoff read: ') for line in text.splitlines() if line.startswith('Exact qualified handoff read: ')))
    code,_,raw=HTTP.handle('/work/state',parse_qs(urlsplit(issued['http']['url']).query),'GET',repo_root=s['root']);assert code==200 and h['phase']['id'] in raw.decode()
    event['source_basis']['pins']['src/answer.py']='caller edit'
    assert WD.status(s['root'],'public',{'event_id':event['id']},s['door'])['event']['source_basis']==h['phase']['source_basis']
    (s['root']/'qualified-delivery-proof.json').write_text(json.dumps({'handoff':h,'delivery':result,'reviewer_request':text,'read_handles':reads,'exact_phase_read':issued,
        'qualification':'Real admission up to withheld turn_execution.start; synthetic provider metadata, no model/inference'},indent=2)+'\n')


@pytest.mark.parametrize('case',['changed','missing','retarget','wrong-approved','renewed-approval'])
def test_qualified_refusals_do_not_reserve_or_start_transport(transport,case):
    s,launches=transport;h=original(s);binding=s['binding']
    if case=='changed':(s['checkout']/'src/answer.py').write_text('drift')
    if case=='missing':
        # Identical canonical twins cannot rescue unavailable qualified input.
        for path in ['src/answer.py','evaluator.py']:
            p=s['root']/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((s['checkout']/path).read_bytes())
        (s['checkout']/'evaluator.py').unlink()
    if case=='retarget':(s['root']/'profiles/writing_sources.json').write_text(json.dumps({'repositories':{'selected':str(s['root'])}}))
    if case=='wrong-approved':
        binding=WD.bind(s['root'],'public',{'action':'bind','work_id':'work','expected_work_revision':guard(s),'kind':'app-owned',
            'provider':'codex','model':'gpt-6.1-sol','effort':'high','label':'Another approved reviewer'}, {'origin':'human'})['binding']
    if case=='renewed-approval':
        binding=WD.handle(s['root'],'public',{'action':'renew','work_id':'work','expected_work_revision':guard(s),'recipient_binding_id':binding['id'],
            'expected_binding_revision':binding['revision'],'request_id':'renew-for-source-control','lifetime_s':604800},{'origin':'human'})['binding']
    before=len(records.index(s['root']).sessions)
    result=submit(s,h,recipient_binding_id=binding['id']);event=result['event'];assert event['state']=='STALE',event
    assert not launches and len(records.index(s['root']).sessions)==before and not event.get('admitted')
    assert 'original Source evaluator' in event['reason'] if case in {'wrong-approved','renewed-approval'} else 'qualified Source' in event['reason']


def test_unrelated_guide_drift_does_not_stale_source_obligation(transport):
    s,launches=transport;h=original(s);(s['checkout']/'guide.md').write_text('unrelated guide drift')
    assert submit(s,h)['event']['state']=='ADMITTED' and len(launches)==1


def test_source_content_identity_is_bound_and_legacy_hash_is_unchanged(source):
    s=source;h=original(s);row=h['phase'];old={'pins':row['pins'],'object':row['object']}
    assert WD._content_pin(old)==WD._digest(old)
    changed=copy.deepcopy(row);changed['source_basis']['candidate_id']='different-candidate'
    assert WD._content_pin(row)!=WD._content_pin(changed)
    before=WD._content_pin(row);changed=copy.deepcopy(row);changed['source_basis']=None
    assert WD._content_pin(changed)!=before
    # No typed basis is inferred for an ordinary legacy event.
    assert WD._content_pin({**old,'object':{'repository':'selected'}})==WD._digest({**old,'object':{'repository':'selected'}})



def test_malformed_or_missing_typed_basis_has_no_canonical_fallback(source,monkeypatch):
    s=source;h=original(s);task=W._tasks('public',s['root'])['work'];basis,_=W._work_basis(W._tasks('public',s['root']),'work')
    intent={'handoff_id':h['phase']['id'],'binding_id':s['binding']['id'],'binding_revision':s['binding']['revision'],
        'recipient':s['binding'],'obligation_id':'source','work_scope_revision':basis['scope_revision'],
        'content_pin':WD._content_pin(h['phase']),'source_basis':h['phase']['source_basis']}
    from laplace.work import project_work_review
    monkeypatch.setattr(project_work_review,'_file_digest',lambda *a,**k: (_ for _ in ()).throw(AssertionError('canonical fallback')))
    missing=copy.deepcopy(intent);del missing['source_basis']
    assert 'Source basis' in WD._revalidate(s['root'],'public',task,missing)
    bad=copy.deepcopy(task);hand=next(row for row in bad['phases'] if row['id']==h['phase']['id']);hand['source_basis']=None
    broken={**intent,'source_basis':None,'content_pin':WD._content_pin(hand)}
    assert 'UNKNOWN' in WD._revalidate(s['root'],'public',bad,broken)


def test_recovery_and_parent_return_keep_original_event_and_source_basis(transport,monkeypatch):
    s,launches=transport;h=original(s);real_append=W._append
    def lost_ack(root,row):
        if row.get('kind')==WD.EVENT and row.get('state')=='ADMITTED':raise RuntimeError('public lost admission acknowledgement')
        return real_append(root,row)
    monkeypatch.setattr(W,'_append',lost_ack)
    with pytest.raises(RuntimeError,match='lost admission'):submit(s,h)
    monkeypatch.setattr(W,'_append',real_append)
    task=W._tasks('public',s['root'])['work'];event_id=[r for r in task['deliveries'] if r.get('kind')==WD.EVENT][-1]['id']
    recovered=WD.recover(s['root'],'public',{'event_id':event_id},s['door'])['event'];assert recovered['state']=='ADMITTED' and len(launches)==1
    launch=launches[0];assert recovered['admitted']['turn_id']==launch.turn_id and recovered['admitted']['recovered']
    tools.execute(s['root'],'public','review','work_review',{'id':'work','phase':'review','request_id':'actual-delivery-source-review',
        'expected_work_revision':guard(s),'handoff_id':h['phase']['id'],'obligation_id':'source','verdict':'ACCEPT'},turn_id=launch.turn_id)
    result={'status':'completed','text':'Public deterministic execution result; no provider.'}
    turn_execution._bank_reply(launch,result);turn_execution._finish(launch,result)
    current=WD.status(s['root'],'public',{'event_id':event_id},s['door'])['event']
    assert current['state']=='CONTINUED',current
    assert current['acceptance']['satisfied'] and current['acceptance']['by_this_delivery']
    assert len(launches)==2 and launches[1].session_id==s['parent']['id'] and launches[1].mode=='work'
    parent=launches[1];text=records.fold_records(s['root'])['turns'][parent.turn_id]['text']
    assert 'Qualified configured Source:' in text and event_id in text and h['phase']['source_basis']['candidate_id'] in text
    assert current['source_basis']==h['phase']['source_basis']
    assert WD.recover(s['root'],'public',{'event_id':event_id},s['door'])['event']['state']=='CONTINUED' and len(launches)==2
    (s['root']/'qualified-parent-recovery-proof.json').write_text(json.dumps({'event':current,'parent_request':text,'withheld_executions':len(launches),
        'qualification':'Real admission, review and terminal hooks; deterministic result supplied at withheld paid execution boundary, no inference'},indent=2)+'\n')
