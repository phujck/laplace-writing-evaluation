"""Public source-bound comment origin, custody and request recovery."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from laplace.pipeline import authoring, correction_origin
from laplace.manuscript import manuscript_bridge, manuscript_source
from laplace.core import identity_doors


def fixture(root):
    md=root/'p/manuscript';md.mkdir(parents=True)
    (md/'main.tex').write_bytes(b'\\documentclass{article}\r\n\\begin{document}\r\nA numerical claim requires a stated assumption.\r\n\\end{document}\r\n')
    (root/'registry_projects.json').write_text(json.dumps({'projects':[{
        'name':'p','kind':'conceptric','project_dir':'p','tex_root':'p/manuscript'}]}))
    expected=list(identity_doors.identities(('prose','p::main.tex:3-3',
        b'A numerical claim requires a stated assumption.')).values())
    prepared=authoring.prepare_correction('p',{'anchor':{'file':'main.tex','line_start':3,'line_end':3,
        'quote':'A numerical claim','section':'claim'},'expected':expected},root)
    return {'project':'p','request_id':'comment-public-1','text':'Does this hold at the boundary? \u03b1',
        'kind':'note','scope':'passage','by':'author',**{k:prepared[k] for k in
        ('anchor','source_basis','base_revision')}}


def rows(root,payload):
    path=root/payload['source_basis']['ledger']
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_one_comment_replay_before_source_or_authoring_checks_and_one_text_copy(tmp_path):
    payload=fixture(tmp_path)
    saved=authoring.bank_correction('p',payload,tmp_path)
    path=tmp_path/'p/manuscript/authoring.json'
    assert payload['text'] not in path.read_text() and path.read_text().count('AC-')==0
    assert len(rows(tmp_path,payload))==1 and rows(tmp_path,payload)[0]['comment']==payload['text']
    assert saved['correction']['context_role']=='author-instruction'
    assert saved['correction']['id'].startswith('AC-') and saved['correction']['feedback_id'].startswith('FB-')
    read=authoring.correction_origin('p',saved['origin_ref'],tmp_path)
    assert read['currentness']['state']=='CURRENT'
    # A later authoring edit and physical source change cannot erase the effect.
    authoring.save('p',{'argument':'Changed argument','base_revision':saved['revision']},tmp_path)
    (tmp_path/'p/manuscript/main.tex').write_text('Changed manuscript.\n')
    assert authoring.bank_correction('p',payload,tmp_path)==saved
    assert len(rows(tmp_path,payload))==1
    assert authoring.correction_origin('p',saved['origin_ref'],tmp_path)['currentness']['state']=='CHANGED'
    changed={**payload,'text':'Different intent'}
    with pytest.raises(ValueError,match='different intent'):authoring.bank_correction('p',changed,tmp_path)


def test_feedback_appended_state_write_interrupted_projects_same_ac_and_revision(tmp_path,monkeypatch):
    payload=fixture(tmp_path);real=authoring._write
    monkeypatch.setattr(authoring,'_write',lambda *a:(_ for _ in ()).throw(OSError('public state write interrupted')))
    with pytest.raises(OSError,match='interrupted'):authoring.bank_correction('p',payload,tmp_path)
    recorded=authoring.correction_request('p',payload['request_id'],tmp_path,ledger=payload['source_basis']['ledger'])
    assert recorded['effect']=='RECORDED' and len(rows(tmp_path,payload))==1
    monkeypatch.setattr(authoring,'_write',real)
    saved=authoring.bank_correction('p',payload,tmp_path)
    assert saved==recorded['receipt']
    state=authoring.load('p',tmp_path)
    assert state['revision']==saved['revision']
    assert [r['id'] for r in state['corrections']]==[saved['correction']['id']]
    assert saved['correction']['id']!=saved['correction']['feedback_id']
    assert authoring._correction_can_constrain(state['corrections'][0])
    (tmp_path/'interrupted-origin-proof.json').write_text(json.dumps(
        {'request':payload,'lookup':recorded,'replayed':saved,'projected_state':state},ensure_ascii=False))


def test_concurrent_exact_request_has_one_ac_fb(tmp_path):
    payload=fixture(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        got=list(pool.map(lambda _:authoring.bank_correction('p',payload,tmp_path),range(2)))
    assert got[0]==got[1] and len(rows(tmp_path,payload))==1


def test_changed_raw_source_or_original_revision_cannot_borrow_a_fresh_guard(tmp_path):
    payload=fixture(tmp_path)
    original=(tmp_path/'p/manuscript/main.tex').read_bytes()
    (tmp_path/'p/manuscript/main.tex').write_bytes(original+b'% unrelated physical change\n')
    with pytest.raises(ValueError,match='Raw source changed'):authoring.bank_correction('p',payload,tmp_path)
    assert not rows(tmp_path,payload)
    (tmp_path/'p/manuscript/main.tex').write_bytes(original)
    authoring.save('p',{'argument':'Other author change','base_revision':0},tmp_path)
    with pytest.raises(ValueError,match='revision conflict'):authoring.bank_correction('p',payload,tmp_path)
    assert not rows(tmp_path,payload)


def test_status_reply_and_unrelated_feedback_do_not_change_origin_material(tmp_path):
    payload=fixture(tmp_path);saved=authoring.bank_correction('p',payload,tmp_path)
    authoring.correction_status('p',{'id':saved['correction']['id'],'status':'resolved',
        'base_revision':saved['revision']},tmp_path)
    state=authoring.load('p',tmp_path)
    authoring.bank_correction('p',{'text':'A reply','kind':'note','scope':'passage',
        'reply_to':saved['correction']['id'],'by':'author','base_revision':state['revision']},tmp_path)
    manuscript_bridge.feedback_add(tmp_path,'p',{'node_id':'other','comment':'Unrelated note','by':'author'},
        ledger=tmp_path/payload['source_basis']['ledger'])
    current=authoring.correction_origin('p',saved['origin_ref'],tmp_path)
    assert current['origin_ref']==saved['origin_ref'] and current['correction']['status']=='resolved'
    assert current['currentness']['state']=='CURRENT'
    state=authoring.load('p',tmp_path)
    authoring.bank_correction('p',{'text':'Replacement instruction','kind':'note','scope':'passage',
        'anchor':payload['anchor'],'by':'author','supersedes':saved['correction']['id'],
        'base_revision':state['revision']},tmp_path)
    exact=authoring.correction_origin('p',saved['origin_ref'],tmp_path)
    assert exact['origin_ref']==saved['origin_ref'] and exact['correction']['status']=='superseded'
    state=authoring.load('p',tmp_path)
    old=next(row for row in state['corrections'] if row['id']==saved['correction']['id'])
    assert old['status']=='superseded' and not authoring._active_corrections(
        {'corrections':[old]},[{'file':payload['anchor']['file']}])


def test_pure_absence_and_incomplete_custody_are_not_terminal_nonadmission(tmp_path):
    payload=fixture(tmp_path);home=payload['source_basis']['ledger']
    found=authoring.correction_request('p',payload['request_id'],tmp_path,ledger=home)
    assert found['effect']=='NONE' and found['receipt'] is None
    other=authoring.correction_request('p',payload['request_id'],tmp_path,
        ledger='p/manuscript/old-edition/feedback/feedback.jsonl')
    assert other['effect']=='UNKNOWN', 'a caller locator cannot authorize project-wide absence'
    path=tmp_path/home;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('{broken\n')
    found=authoring.correction_request('p',payload['request_id'],tmp_path,ledger=home)
    assert found['effect']=='UNKNOWN'
    with pytest.raises(ValueError,match='incomplete'):authoring.bank_correction('p',payload,tmp_path)
    path.unlink()
    assert authoring.correction_request('p',payload['request_id'],tmp_path,ledger=home)['effect']=='UNKNOWN'


def test_prepare_reuses_inspected_basis_and_refuses_silent_reanchor(tmp_path):
    payload=fixture(tmp_path)
    again=authoring.prepare_correction('p',{k:payload[k] for k in ('anchor','source_basis','base_revision')},tmp_path)
    assert again['source_basis']==payload['source_basis'] and again['base_revision']==payload['base_revision']
    source=tmp_path/'p/manuscript/main.tex';source.write_bytes(b'% shifted\n'+source.read_bytes())
    with pytest.raises(ValueError,match='Raw source changed'):
        authoring.prepare_correction('p',{k:payload[k] for k in ('anchor','source_basis','base_revision')},tmp_path)


def test_registered_canonical_home_keeps_project_request_unique_across_editions(tmp_path):
    payload=fixture(tmp_path);saved=authoring.bank_correction('p',payload,tmp_path)
    second=tmp_path/'p/manuscript/edition2';second.mkdir()
    second.joinpath('main.tex').write_text('\\documentclass{article}\n\\begin{document}\nA different edition passage.\n\\end{document}\n')
    selected=manuscript_source.select('p','p/manuscript/edition2/main.tex',repo_root=tmp_path)
    assert selected['manuscript_dir']=='p/manuscript/edition2'
    # Historical request and original AC remain recoverable after the source
    # state home changes. A different intent cannot reuse the project request.
    assert authoring.bank_correction('p',payload,tmp_path)==saved
    expected=list(identity_doors.identities(('prose','p::main.tex:3-3',b'A different edition passage.')).values())
    new=authoring.prepare_correction('p',{'anchor':{'file':'main.tex','line_start':3,'line_end':3},
        'expected':expected},tmp_path)
    assert new['source_basis']['ledger']==payload['source_basis']['ledger']
    changed={**payload,**{key:new[key] for key in ('source_basis','anchor','base_revision')}}
    with pytest.raises(ValueError,match='different intent'):authoring.bank_correction('p',changed,tmp_path)
    other=authoring.bank_correction('p',{**changed,'request_id':'comment-public-2'},tmp_path)
    assert len(rows(tmp_path,payload))==2
    state=authoring.load('p',tmp_path)
    assert {row['id'] for row in state['corrections']}=={saved['correction']['id'],other['correction']['id']}
    current=state['corrections'][-1]
    assert authoring._correction_applies(current,[{'file':new['anchor']['file']}])
    assert not (second/'feedback/feedback.jsonl').exists(), 'no second typed-origin ledger follows the edition'
    warm=authoring.history('p',{},tmp_path)
    manuscript_bridge.feedback_resolve(tmp_path,'p',saved['correction']['feedback_id'],'resolved',
        ledger=tmp_path/payload['source_basis']['ledger'])
    refreshed=authoring.history('p',{},tmp_path)
    assert refreshed['as_of']!=warm['as_of']
    assert next(row for row in refreshed['items'] if row['id']==saved['correction']['id'])['status']=='resolved'
    (tmp_path/'edition-origin-proof.json').write_text(json.dumps({'first':saved,'second':other,
        'new_preparation':new,'warm_history':warm,'refreshed_history':refreshed},ensure_ascii=False))


def test_owner_http_declarations_and_save_route_release_locks(tmp_path,monkeypatch):
    from laplace.web import authoring_http
    from laplace.work import work_delivery
    from laplace.native.declarations import HTTP_DECLARATIONS
    import laplace.web.writing_declared_http
    from jsonschema import Draft202012Validator
    payload=fixture(tmp_path);called=[]
    def compose(root,project,receipt,spec,*,door):
        assert not manuscript_source.source_mutation_active()
        from filelock import FileLock
        # Another thread must be able to take the authoring lock before Work.
        def lock():
            with FileLock(str(root/'p/manuscript/.authoring.lock'),timeout=0):return True
        with ThreadPoolExecutor(max_workers=1) as pool:assert pool.submit(lock).result()
        called.append((receipt,spec,door));raise OSError('route transport outcome unknown')
    monkeypatch.setattr(work_delivery,'compose_origin',compose,raising=False)
    wire={**payload,'review_route':{'fixture':'selected existing Work'}}
    schema=HTTP_DECLARATIONS['authoring/correction-request-save'].payload
    assert not list(Draft202012Validator(schema).iter_errors(wire))
    status,_,raw=authoring_http.handle(tmp_path,'/authoring/correction',{},'POST',json.dumps(wire).encode())
    response=json.loads(raw)
    assert status==200 and response['effect']=='RECORDED' and response['review_route']['effect']=='UNKNOWN'
    assert response['review_route_spec']==wire['review_route']
    assert authoring.history('p',{},tmp_path)['items'][0]['has_review_route']
    assert called[0][2]=={'origin':'human'}
    status,_,raw=authoring_http.handle(tmp_path,'/authoring/correction-request',{
        'project':['p'],'request_id':[payload['request_id']],'ledger':[payload['source_basis']['ledger']]},'GET',b'')
    assert status==200 and json.loads(raw)['receipt']['origin_ref']==response['origin_ref']
    status,_,raw=authoring_http.handle(tmp_path,'/authoring/correction-origin',{
        'project':['p'],'origin_ref':[json.dumps(response['origin_ref'])]},'GET',b'')
    assert status==200 and json.loads(raw)['correction']['text']==payload['text']
    exact=json.loads(raw)
    assert exact['review_route_spec']==wire['review_route']
    with pytest.raises(ValueError,match='different intent'):
        authoring.bank_correction('p',{**wire,'review_route':{'fixture':'different route'}},tmp_path)
    (tmp_path/'http-origin-proof.json').write_text(json.dumps({'submitted':wire,'saved':response,
        'exact_read':exact},ensure_ascii=False))


def test_cross_project_home_and_changed_material_are_not_authority(tmp_path):
    payload=fixture(tmp_path);saved=authoring.bank_correction('p',payload,tmp_path)
    bad={**saved['origin_ref'],'ledger':'foreign/feedback/feedback.jsonl'}
    with pytest.raises(ValueError,match='belong'):authoring.correction_origin('p',bad,tmp_path)
    path=tmp_path/payload['source_basis']['ledger'];row=rows(tmp_path,payload)[0]
    row['comment']='Modified body';path.write_text(json.dumps(row)+'\n')
    assert authoring.correction_request('p',payload['request_id'],tmp_path,
        ledger=payload['source_basis']['ledger'])['effect']=='UNKNOWN'
    with pytest.raises(ValueError,match='material'):authoring.correction_origin('p',saved['origin_ref'],tmp_path)
