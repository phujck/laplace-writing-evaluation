"""Public selected-input fixtures; no provider process or inference is started."""
import copy
import hashlib
import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from laplace.projects import library
from laplace.pipeline import projection_spec
from laplace.writing import sealed_reader as S, records, turn_admission as T, turn_execution as E, turn_jobs
from laplace.writing import session_reads, turn_control, operating, provider
from laplace.native import tools
from laplace.core import identity


@pytest.fixture
def case(tmp_path, monkeypatch):
    assert library.create({'name':'book','kind':'book','title':'Public reader fixture'},tmp_path)[0]==201
    inputs=tmp_path/'inputs';inputs.mkdir()
    primary='SELECTED_PRIMARY é中🌱\nThe visible claim uses the explicitly selected reference.\n'
    reference='SELECTED_REFERENCE\nPublic supporting text.\n'
    (inputs/'primary.txt').write_text(primary);(inputs/'reference.txt').write_text(reference)
    (inputs/'unselected.txt').write_text('EXCLUDED_UNSELECTED_FILE')
    (tmp_path/'profiles').mkdir(exist_ok=True)
    (tmp_path/'profiles/writing_sources.json').write_text(json.dumps({'repositories':{'public':'inputs'}}))
    project=tmp_path/'synthetics papers/book'
    (project/'WORKING_GUIDE.md').write_text('EXCLUDED_PROJECT_GUIDANCE')
    projection_spec.write_spec('book',{'manuscript':{'working_guides':['WORKING_GUIDE.md']}},tmp_path)
    voice=tmp_path/'profiles/voice/gerard-technical-v1.md';voice.parent.mkdir();voice.write_text('EXCLUDED_STYLE_CONTEXT')
    cache=tmp_path/'.laplace-cache';cache.mkdir()
    catalogue={'schema_version':'laplace.provider-catalogue/1','observed_at':99999999999,
        'providers':[{'id':'claude','available':True,'models':[{'id':'fixture-reader','efforts':['low'],'default_effort':'low'}]}]}
    (cache/'writing-provider-catalogue.json').write_text(json.dumps(catalogue))
    binary=tmp_path/'fixture-claude';binary.write_text('PUBLIC FAKE CLI; never executable or launched.')
    real_which=S.shutil.which
    monkeypatch.setattr(S.shutil,'which',lambda name: str(binary) if name=='claude' else real_which(name))
    monkeypatch.setattr(S,'HELP_EXECUTABLE_SHA',hashlib.sha256(binary.read_bytes()).hexdigest())
    monkeypatch.setattr(provider,'capabilities',lambda *a,**k:pytest.fail('Implicit provider discovery'))
    records.bank(tmp_path,{'record':'writing-session','id':'WS-informed','project':'book','role':'author','provider':'claude','model':'fixture-reader','effort':'low'})
    records.bank(tmp_path,{'record':'writing-turn','id':'WT-history','session_id':'WS-informed','project':'book','text':'EXCLUDED_HISTORY','mode':'work'})
    def item(name):return {'target':{'owner':'repository','repository':'public','path':name},
        'expected_sha256':identity.bytes_digest((inputs/name).read_bytes()),'representation':'utf8-text'}
    payload={'project':'book','view':'prepare','primary':item('primary.txt'),'references':[item('reference.txt')],
        'missing_references':[{'label':'Visible missing source','reason':'Declared unavailable; not fetched.'}],
        'task':'Explain the visible claim and its limitations.','model':'fixture-reader','effort':'low'}
    yield tmp_path,payload,primary,reference
    from laplace.writing import child_hosts
    for ident,job in list(turn_jobs._JOBS.items()):
        if job.get('root')==tmp_path:
            turn_jobs._JOBS.pop(ident,None)
            child_hosts._finish_child_execution(tmp_path,job['session_id'],ident,'completed')


def qualify(root):
    current=S.support(root,'book')
    path=root/S.QUALIFICATION;path.parent.mkdir(parents=True,exist_ok=True)
    evidence=[]
    for kind in ('startup','tool-read-canary','input-delivery'):
        observation=S._put(root,{'fixture':True,'actual_provider':False,'kind':kind,
            'note':'Public deterministic adapter boundary only; not a production qualification.'})
        envelope=S._put(root,{'schema_version':'laplace.sealed-reader-evidence/1','profile':S.PROFILE,
            'fingerprint':current['fingerprint'],'kind':kind,'outcome':'PASS','observation':observation})
        evidence.append({'kind':kind,'body':envelope})
    path.write_text(json.dumps({'schema_version':'laplace.sealed-reader-qualification/1','fingerprint':current['fingerprint'],
        'outcome':'QUALIFIED','evidence':evidence}))
    return S.support(root,'book')


def prepare_start(case):
    root,payload,_,_=case
    value=S.prepare(root,payload);qualify(root)
    value=S.request(root,{'project':'book','view':'input','input':value['input']})
    return value,{**value['start']['payload'],'request_id':'reader-start-é'}


def test_actual_complete_inputs_canaries_and_informed_review_control(case):
    root,payload,primary,reference=case
    result=S.prepare(root,payload);manifest=S._manifest(root,'book',result['input'])
    packet=S._get(root,manifest['packet'])
    assert primary in packet and reference in packet and 'Declared unavailable' in packet
    assert all(token not in packet+S.KERNEL for token in ('EXCLUDED_PROJECT_GUIDANCE','EXCLUDED_STYLE_CONTEXT','EXCLUDED_HISTORY','EXCLUDED_UNSELECTED_FILE'))
    ordinary=operating.build('book','review',root)
    assert 'EXCLUDED_PROJECT_GUIDANCE' in operating.process_instructions(ordinary,'claude',resumed=False)['turn_prefix']
    assert result['support']['state']=='CANDIDATE' and not result['start']['permitted']
    assert S.prepare(root,payload)['input']==result['input']
    raw=[json.loads(line) for line in (root/'contract/talk.jsonl').read_text().splitlines()]
    assert sum(row['record']=='writing-reader-input' for row in raw)==1
    (root/'prepared-input-proof.json').write_text(json.dumps({'input':result,'manifest':manifest,'packet':packet,
        'ordinary_informed_control_detected_guidance':True,'provider_calls':0},indent=2,ensure_ascii=False))


def test_document_larger_than_human_message_bound_is_complete_and_task_bound_separate(case):
    root,payload,_,_=case;path=root/'inputs/primary.txt';text='LARGE_SELECTED_DOC\n'+'é中🌱\n'*30000;path.write_text(text)
    payload['primary']['expected_sha256']=identity.bytes_digest(path.read_bytes())
    result=S.prepare(root,payload);manifest=S._manifest(root,'book',result['input'])
    assert text in S._get(root,manifest['packet']) and manifest['sizes']['packet']['characters']>100000
    assert manifest['sizing']['packet_truncated'] is False
    with pytest.raises(ValueError):S.prepare(root,{**payload,'task':'x'*100001})


def test_fresh_admission_lookup_exact_replay_and_one_attempt_fences(case,monkeypatch):
    root,_,_,_=case;value,payload=prepare_start(case);launches=[]
    monkeypatch.setattr(E,'start',lambda launch:launches.append(launch))
    monkeypatch.setattr(operating,'build',lambda *a,**k:pytest.fail('Ordinary project context assembly'))
    answer=T.start_turn(root,payload);assert len(launches)==1
    launch=launches[0];assert launch.session_id!='WS-informed' and launch.session.get('native_id') is None
    assert launch.native_source_paths==frozenset() and launch.operating_brief['permissions']==[]
    assert 'EXCLUDED_HISTORY' not in launch.prompt and 'SELECTED_PRIMARY' in launch.prompt
    lookup=session_reads.reader_request(root,'book',payload['request_id'],value['manifest_id'])
    assert lookup['effect']=='RECORDED' and lookup['receipt']['turn_id']==answer['turn_id']
    (root/'inputs/primary.txt').write_text('Changed after admission.')
    (root/S.QUALIFICATION).unlink()
    replay=T.start_turn(root,copy.deepcopy(payload));assert replay['reused'] and replay['turn_id']==answer['turn_id'] and len(launches)==1
    with pytest.raises(ValueError,match='intent changed'):T.start_turn(root,{**payload,'expected_support_basis':'sha256:'+'b'*64})
    for attempt in (
        lambda:T.start_turn(root,{'project':'book','session_id':answer['session_id'],'mode':'review','text':'Ordinary follow-up'}),
        lambda:T.configure_session(root,'book',answer['session_id'],{'model':'fixture-reader'}),
        lambda:turn_control.steer_turn(root,{'project':'book','turn_id':answer['turn_id'],'text':'Inject project context'}),
        lambda:tools.execute(root,'book','review','project',{},turn_id=answer['turn_id'])):
        with pytest.raises(ValueError):attempt()
    state=session_reads.session_state(root,answer['session_id'],view='summary')
    assert state['session']['reader_capabilities']['can_send'] is False
    stopped=turn_control.interrupt_turn(root,{'project':'book','turn_id':answer['turn_id']})
    assert launch.job['interrupt_requested']
    E._bank_reply(launch,{'status':'interrupted','text':'Partial exact public report.','provider_stage':'pre-inference'})
    result=S.request(root,{'project':'book','view':'result','input':value['input'],'turn_id':answer['turn_id']})
    assert result['turn']['reply']['text']=='Partial exact public report.' and not result['currentness']['unchanged']
    (root/'reader-admission-proof.json').write_text(json.dumps({'answer':answer,'lookup':lookup,'replay':replay,
        'reader_profile':launch.reader_profile,'prompt':launch.prompt,'result':result,'provider_calls':0},indent=2,ensure_ascii=False))


@pytest.mark.parametrize('fault',['unqualified','source','support','session','context','forged-input'])
def test_refusals_before_fresh_session_effects(case,monkeypatch,fault):
    root,_,_,_=case;value,payload=prepare_start(case)
    if fault=='unqualified':(root/S.QUALIFICATION).unlink()
    if fault=='source':(root/'inputs/primary.txt').write_text('Changed selected bytes.')
    if fault=='support':payload['expected_support_basis']='sha256:'+'b'*64
    if fault=='session':payload['session_id']='WS-informed'
    if fault=='context':payload['workspace_context']={'surface':'project'}
    if fault=='forged-input':
        manifest=S._manifest(root,'book',value['input']);manifest['task']=S._put(root,'Forged task')
        payload['input']=S._put(root,manifest)
    before=(root/'contract/talk.jsonl').read_bytes()
    monkeypatch.setattr(T,'new_session',lambda *a,**k:pytest.fail('Reached fresh session effects'))
    with pytest.raises(ValueError) as caught:T.start_turn(root,payload)
    after=(root/'contract/talk.jsonl').read_bytes()
    if isinstance(caught.value,S.NotAdmitted):
        assert caught.value.terminal
        assert [json.loads(line)['record'] for line in after[len(before):].splitlines()]==['writing-reader-refusal']
    else:assert after==before


def test_lookup_without_WS_and_overlapping_identical_start_have_one_admission(case,monkeypatch):
    root,_,_,_=case;value,payload=prepare_start(case);entered=threading.Event();release=threading.Event();starts=[]
    original=S.admit
    def gated(*args):entered.set();assert release.wait(5);return original(*args)
    monkeypatch.setattr(S,'admit',gated);monkeypatch.setattr(E,'start',lambda launch:starts.append(launch))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(T.start_turn,root,payload);assert entered.wait(5)
        assert session_reads.reader_request(root,'book',payload['request_id'],value['manifest_id'])['effect']=='NONE'
        second=pool.submit(T.start_turn,root,copy.deepcopy(payload));release.set()
        one,two=first.result(),second.result()
    assert one['turn_id']==two['turn_id'] and one['session_id']==two['session_id'] and len(starts)==1


def test_reader_request_uses_captured_bounded_headers_and_replacement_detection(case,monkeypatch):
    root,_,_,_=case;value,payload=prepare_start(case);launches=[]
    monkeypatch.setattr(E,'start',lambda launch:launches.append(launch))
    answer=T.start_turn(root,payload)
    monkeypatch.setattr(records,'fold_records',lambda *a,**k:pytest.fail('Reader lookup hydrated the rich fold'))
    actual=session_reads.reader_request(root,'book',payload['request_id'],value['manifest_id'])
    assert actual['receipt']['turn_id']==answer['turn_id']
    with pytest.raises(ValueError):session_reads.reader_request(root,'foreign',payload['request_id'],value['manifest_id'])
    log=root/'contract/talk.jsonl';rows=[json.loads(line) for line in log.read_text().splitlines()]
    # Public fixture replacement proves this remains the captured journal index,
    # not an unowned in-memory request registry.
    log.write_text(''.join(json.dumps(row)+'\n' for row in rows if row.get('id')!=answer['turn_id']))
    assert session_reads.reader_request(root,'book',payload['request_id'],value['manifest_id'])['effect']=='NONE'
    log.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    assert session_reads.reader_request(root,'book',payload['request_id'],value['manifest_id'])['effect']=='RECORDED'
    (root/'bounded-request-proof.json').write_text(json.dumps({'lookup':actual,'replacement_absence_and_restore':True,
        'rich_fold_called':False,'provider_calls':0},indent=2))


def test_plain_input_needs_no_manuscript_and_HTTP_native_SDK_share_owner(case):
    from laplace import sdk
    from laplace.web import authoring_http, writing_declared_http
    from laplace.native.declarations import HTTP_DECLARATIONS
    from jsonschema import Draft202012Validator
    from urllib.parse import parse_qs,urlsplit
    root,payload,_,_=case
    assert library.create({'name':'data-only','kind':'general','title':'Source-optional public custody'},root)[0]==201
    selected={**payload,'project':'data-only'}
    value=sdk.reader_request(selected,root=root)
    native=tools.execute(root,'data-only','work','project',{'view':'sealed-text-reader','request':selected})
    assert native['input']==value['input']
    code,_,raw=authoring_http.handle(root,'/authoring/reader',{},'POST',json.dumps({**selected,'action':'prepare'}).encode())
    assert code==200 and json.loads(raw)['input']==value['input']
    request={**value['start']['payload'],'request_id':'unqualified-wire'}
    Draft202012Validator(HTTP_DECLARATIONS['authoring/turn'].payload).validate(request)
    assert list(Draft202012Validator(HTTP_DECLARATIONS['authoring/turn'].payload).iter_errors({**request,'session_id':'WS-informed'}))
    lookup={'project':'data-only','view':'reader-request','request_id':'unseen','manifest_id':value['manifest_id']}
    Draft202012Validator(HTTP_DECLARATIONS['authoring/session-turn'].payload).validate(lookup)
    code,_,raw=authoring_http.handle(root,'/authoring/session-turn',{k:[v] for k,v in lookup.items()},'GET',b'')
    assert code==200 and json.loads(raw)['effect']=='NONE'


def test_existing_PDF_text_transport_proves_full_pages_without_visual_claim(case,monkeypatch):
    from laplace.projects import writing_sources
    root,payload,_,_=case;path=root/'inputs/public.pdf';path.write_bytes(b'%PDF public deterministic source')
    extractor=root/'public-extractor';extractor.write_bytes(b'Public deterministic extractor identity')
    monkeypatch.setattr(writing_sources,'_tool',lambda name:str(extractor) if name=='pdftotext' else 'public-pdfinfo')
    def run(argv):
        if argv[0]=='public-pdfinfo':return b'Pages: 2\n'
        return ('PUBLIC PDF PAGE '+argv[argv.index('-f')+1]).encode()
    monkeypatch.setattr(writing_sources,'_run',run)
    item={'target':{'owner':'repository','repository':'public','path':'public.pdf'},
        'expected_sha256':identity.bytes_digest(path.read_bytes()),'representation':'pdf-text'}
    value=S.prepare(root,{**payload,'primary':item,'references':[]})
    manifest=S._manifest(root,'book',value['input']);selected=manifest['inputs'][0]
    assert selected['derivation']['coverage'][0]['pdf_page_start']==1
    assert selected['derivation']['coverage'][-1]['pdf_page_end']==2
    assert not selected['derivation']['visual_pages_supplied']
    assert 'PUBLIC PDF PAGE 1' in S._get(root,manifest['packet']) and 'PUBLIC PDF PAGE 2' in S._get(root,manifest['packet'])


class Input(io.StringIO):
    def close(self):self.was_closed=True


@pytest.mark.parametrize('inventory',['empty','tool','customization','attempt','missing'])
def test_existing_adapter_fake_stream_exact_profile_and_unqualified_inventory(case,monkeypatch,inventory):
    root,_,_,_=case;value,payload=prepare_start(case);launches=[]
    monkeypatch.setattr(E,'start',lambda launch:launches.append(launch))
    T.start_turn(root,payload);launch=launches[0];events=[];processes=[]
    init={'type':'system','subtype':'init','session_id':'public-native-reader','model':'fixture-reader',
          'tools':[],'mcp_servers':[],'slash_commands':[],'agents':[],'skills':[],'plugins':[],'output_style':'default'}
    if inventory=='tool':init['tools']=['PUBLIC_UNEXPECTED_TOOL']
    if inventory=='customization':init['skills']=['PUBLIC_UNEXPECTED_SKILL']
    messages=[] if inventory=='missing' else [init]
    if inventory=='attempt':messages.append({'type':'assistant','message':{'content':[{'type':'tool_use','name':'PUBLIC_TOOL','input':{}}]}})
    messages.extend([{'type':'assistant','message':{'model':'fixture-reader','content':[{'type':'text','text':'Selected-text report.'}]}},
        {'type':'result','subtype':'success','is_error':False,'result':'Selected-text report.','usage':{'input_tokens':1,'output_tokens':1}}])
    class Process:
        pid=999999999
        def __init__(self,argv,**kwargs):
            self.argv=argv;self.kwargs=kwargs;self.stdin=Input();self.stdout=iter(json.dumps(row)+'\n' for row in messages);processes.append(self)
        def wait(self,timeout=None):return 0
        def poll(self):return 0
    monkeypatch.setattr(provider.subprocess,'Popen',Process)
    live=provider.WritingTurn(root,'claude','fixture-reader','low',None,events.append,'review',project='book',session_id=launch.session_id)
    live.reader_profile=launch.reader_profile;live.operating_brief=launch.operating_brief
    if inventory=='empty':
        answer=live.run(launch.prompt);assert answer['status']=='completed'
        assert live.delivery['reader']['state']==S.STARTUP_STATE
    else:
        with pytest.raises(provider.ProviderError):live.run(launch.prompt)
        assert live.delivery['reader']['state']=='UNQUALIFIED'
    assert processes[0].stdin.getvalue()==launch.prompt
    S.validate_arguments(processes[0].argv[1:],'fixture-reader','low')
    assert live.control_capabilities()['can_steer'] is False
    for extra in (['--resume','old'],['--tools','Read'],['--mcp-config','{"mcpServers":{"other":{}}}']):
        with pytest.raises(ValueError):S.validate_arguments(processes[0].argv[1:]+extra,'fixture-reader','low')
    (root/'adapter-proof.json').write_text(json.dumps({'inventory_case':inventory,'argv':processes[0].argv,
        'delivery':live.delivery,'provider_processes':0,'fake_process_boundaries':len(processes)},indent=2))
