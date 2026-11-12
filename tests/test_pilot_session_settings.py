"""Real scoped settings custody, passive catalogue; no provider execution."""
import copy,json,threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from test_writing_operating import _project
from laplace.writing import session_settings as S,turn_admission as T,records,provider,provider_catalogue,turn_jobs
from laplace.work import project_work as W

CATALOGUE={'providers':[{'id':p,'available':True,'models':[{'id':'public-main','name':'Public main','supports_effort':True,'efforts':['low','medium','high']},{'id':'public-small','name':'Public small','supports_effort':False,'efforts':[]}]} for p in ('codex','claude')],'observed_at':None,'cached':True,'observation_scope':'synthetic-public-test'}
HUMAN={'origin':'human'}

@pytest.fixture
def settings_root(tmp_path,monkeypatch):
 _project(tmp_path)
 monkeypatch.setattr(provider_catalogue,'provider_catalogue',lambda *a,**k:copy.deepcopy(CATALOGUE))
 monkeypatch.setattr(provider,'provider_catalogue',lambda *a,**k:copy.deepcopy(CATALOGUE))
 monkeypatch.setattr(provider,'capabilities',lambda *a,**k:copy.deepcopy(CATALOGUE))
 row=T.new_session(tmp_path,'book','codex','public-main','low')
 return tmp_path,row


def read(root,target):return S.request(root,'book',{'action':'read','target':target},door=HUMAN)
def wire(root,target,**values):
 view=read(root,target);result=copy.deepcopy(view['actions']['change']['http']['payload']);result['values'].update(values);return result

def withdraw(payload):return {'action':'withdraw','project':'book','target':payload['target'],'request_id':payload['request_id'],'intent_digest':S.intent_digest(payload),'original_request':payload}

def lookup(root,payload):return S.request(root,'book',{'action':'request','target':payload['target'],'request_id':payload['request_id']},door=HUMAN)

def retain(root,name,value):(root/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2))


def test_session_exact_noop_replay_cas_normalization_and_detached_metadata(settings_root,monkeypatch):
 root,session=settings_root;target={'kind':'conversation','session_id':session['id']}
 monkeypatch.setattr(records,'fold_records',lambda *_:(_ for _ in ()).throw(AssertionError('Pilot read must not hydrate conversation bodies')))
 initial=read(root,target);assert initial['settings']['provider']['origin']=='session-opening-provider'
 legacy={**copy.deepcopy(session),'id':'WS-public-legacy'};legacy.pop('settings_provenance',None);records.bank(root,legacy)
 assert read(root,{'kind':'conversation','session_id':legacy['id']})['settings']['provider']['origin']=='UNKNOWN'
 old=wire(root,target);saved=S.request(root,'book',old,door=HUMAN)
 assert saved['effect']=='RECORDED' and saved['terminal'] and saved['receipt']['noop'] and saved['receipt']['settings_revision']==0
 small=wire(root,target,model='public-small',effort='high');small_saved=S.request(root,'book',small,door=HUMAN)
 assert small_saved['receipt']['values']['effort'] is None and small_saved['original_request']['values']['effort']=='high'
 assert small_saved['current']['settings']['effort']['provenance']['normalization']
 replay=S.request(root,'book',old,door=HUMAN)
 assert replay['receipt']==saved['receipt'] and replay['current']['effective']['model']=='public-small'
 with pytest.raises(ValueError,match='another intent'):S.request(root,'book',{**old,'values':{'model':'public-small'}},door=HUMAN)
 stale={**old,'request_id':'stale-new-request'};refused=S.request(root,'book',stale,door=HUMAN)
 assert refused['effect']=='NOT_ADMITTED' and refused['reason']=='CHANGED_SETTINGS_BASIS'
 small_saved['current']['settings']['model']['provenance']['value']='caller mutation'
 assert read(root,target)['effective']['model']=='public-small'
 retain(root,'session-owner-proof',{'initial':initial,'noop':saved,'small':small_saved,'historical_replay':replay,'stale':refused})


def test_project_scope_atomic_history_legacy_preservation_and_workers(settings_root):
 root,session=settings_root;target={'kind':'project-defaults'};first=wire(root,target,provider='claude',model='public-main',effort='high')
 saved=S.request(root,'book',first,door=HUMAN);assert saved['effect']=='RECORDED'
 assert read(root,{'kind':'conversation','session_id':session['id']})['effective']=={'provider':'codex','model':'public-main','effort':'low'}
 from laplace.pipeline import projection_spec,schema
 path=projection_spec.spec_path('book',root);before=path.read_bytes();replay=S.request(root,'book',first,door=HUMAN);assert path.read_bytes()==before and replay['receipt']==saved['receipt']
 W.session_preferences('book',{'provider':'codex','model':'public-small','effort':'high'},root)
 assert lookup(root,first)['effect']=='RECORDED'
 worker=W.session_choice('book',{'provider':'codex'},root,role='worker')
 assert worker['model']==schema.role_model('worker','codex')['model'] and worker['model_source']=='tier-default'
 assert W.session_choice('book',{'provider':'codex'},root)['model']=='public-small'
 retain(root,'project-owner-proof',{'saved':saved,'replay':replay,'current_after_legacy':read(root,target),'original_request_after_legacy':lookup(root,first),'worker':worker})


@pytest.mark.parametrize('kind',['conversation','project-defaults'])
def test_withdrawal_serializes_original_before_or_after_effect_and_race(settings_root,kind):
 root,session=settings_root;target={'kind':kind,**({'session_id':session['id']} if kind=='conversation' else {})}
 original=wire(root,target,model='public-small');before=read(root,target)['basis'];closed=S.request(root,'book',withdraw(original),door=HUMAN)
 late=S.request(root,'book',original,door=HUMAN)
 assert closed['effect']==late['effect']=='NOT_ADMITTED' and late['reason']=='WITHDRAWN' and read(root,target)['basis']==before
 actual=wire(root,target,model='public-small');saved=S.request(root,'book',actual,door=HUMAN);after=read(root,target)['basis']
 no_undo=S.request(root,'book',withdraw(actual),door=HUMAN);assert no_undo['receipt']==saved['receipt'] and read(root,target)['basis']==after
 racing=wire(root,target,model='public-main',effort='medium');barrier=threading.Barrier(2)
 def call(value):barrier.wait();return S.request(root,'book',value,door=HUMAN)
 with ThreadPoolExecutor(max_workers=2) as pool:
  a=pool.submit(call,racing);b=pool.submit(call,withdraw(racing));outcomes=[a.result(),b.result()]
 assert outcomes[0]['effect']==outcomes[1]['effect']
 assert lookup(root,racing)['effect']==outcomes[0]['effect']
 retain(root,'withdraw-'+kind+'-proof',{'closed':closed,'late':late,'no_undo':no_undo,'race':outcomes})


def test_conversation_storage_uncertainty_and_busy_closure(settings_root,monkeypatch):
 root,session=settings_root;target={'kind':'conversation','session_id':session['id']};original=wire(root,target,effort='high');bank=records.bank
 monkeypatch.setattr(records,'bank',lambda *a,**k:(_ for _ in ()).throw(OSError('public pre-append failure')))
 failed=S.request(root,'book',original,door=HUMAN);assert failed['effect']=='UNKNOWN' and not failed['terminal'] and lookup(root,original)['effect']=='NONE'
 def committed(*a,**k):bank(*a,**k);raise OSError('public lost acknowledgement after append')
 monkeypatch.setattr(records,'bank',committed);lost=S.request(root,'book',original,door=HUMAN);assert lost['effect']=='UNKNOWN'
 assert lookup(root,original)['effect']=='RECORDED'
 monkeypatch.setattr(records,'bank',bank);busy=wire(root,target,effort='medium')
 monkeypatch.setitem(turn_jobs._JOBS,'WT-public-busy',{'session_id':session['id'],'done':False})
 refused=S.request(root,'book',busy,door=HUMAN);assert refused['effect']=='NOT_ADMITTED' and refused['reason']=='SESSION_BUSY'
 monkeypatch.delitem(turn_jobs._JOBS,'WT-public-busy');assert S.request(root,'book',busy,door=HUMAN)['effect']=='NOT_ADMITTED'
 retain(root,'uncertainty-proof',{'preappend':failed,'lost_ack':lost,'exact_lookup':lookup(root,original),'busy_closed':refused})


def test_project_atomic_failure_and_corrupt_request_custody(settings_root,monkeypatch):
 root,_=settings_root;target={'kind':'project-defaults'};original=wire(root,target,provider='codex',model='public-main',effort='low')
 from laplace.pipeline import projection_spec
 update=projection_spec.update_file
 monkeypatch.setattr(projection_spec,'update_file',lambda *a,**k:(_ for _ in ()).throw(OSError('public storage unavailable')))
 failed=S.request(root,'book',withdraw(original),door=HUMAN);assert failed['effect']=='UNKNOWN' and lookup(root,original)['effect']=='NONE'
 monkeypatch.setattr(projection_spec,'update_file',update);saved=S.request(root,'book',original,door=HUMAN);assert saved['effect']=='RECORDED'
 path=projection_spec.spec_path('book',root);doc=json.loads(path.read_text());doc['manuscript'][S.HISTORY]=[];path.write_text(json.dumps(doc));before=path.read_bytes()
 unknown=lookup(root,original);assert unknown['effect']=='UNKNOWN'
 assert S.request(root,'book',original,door=HUMAN)['effect']=='UNKNOWN' and path.read_bytes()==before
 retain(root,'project-failure-proof',{'failed':failed,'saved':saved,'corrupt':unknown})


def test_issued_http_sdk_native_scope_and_actual_admitted_projection(settings_root,monkeypatch):
 from urllib.parse import urlsplit,parse_qs
 from laplace.web import authoring_http,project_work_surface
 from laplace.native import tools
 from laplace import sdk
 from laplace.writing import turn_execution as X,child_hosts,session_reads
 root,session=settings_root;target={'kind':'conversation','session_id':session['id']};launches=[];monkeypatch.setattr(X,'start',launches.append)
 started=T.start_turn(root,{'project':'book','session_id':session['id'],'mode':'work','text':'Public pilot settings authority and unchanged admitted values.','request_id':'settings-parent-public-001'})
 launch=launches[-1];tid=started['turn_id'];before=copy.deepcopy(records.index(root).turns[tid]['provider_settings'])
 assert started['settings_read']
 actual=child_hosts.child_execution
 monkeypatch.setattr(child_hosts,'child_execution',lambda r,sid,**kw:({'state':'RUNNING','project':'book','session_id':sid,'turn_id':tid} if sid==session['id'] and not launch.job.get('done') else actual(r,sid,**kw)))
 try:
  pilot=tools.execute(root,'book','work','session_settings',{'view':'pilot'},turn_id=tid)
  assert pilot['target']==target and pilot['authority']['latest_admitted']['turn_id']==tid
  assert not pilot['actions']['change']['permitted']
  pending=copy.deepcopy(pilot['actions']['change']['http']['payload']);pending['values']['effort']='high'
  refused=tools.execute(root,'book','work','session_settings_change',pending,turn_id=tid)
  assert refused['effect']=='NOT_ADMITTED' and refused['reason']=='SESSION_BUSY'
  assert records.index(root).turns[tid]['provider_settings']==before
  native_default=wire(root,{'kind':'project-defaults'},provider='codex',model='public-main')
  with pytest.raises(ValueError,match='human/local SDK'):S.request(root,'book',native_default,door={'origin':'native','turn_id':tid,'mode':'work'})
 finally:X._finish(launch,{'status':'interrupted'})
 idle=sdk.session_settings_request('book',{'action':'read','target':target},root=root)
 assert idle['authority']['latest_admitted']['settings']==before and idle['actions']['change']['permitted']
 entry=session_reads.session_state(root,session['id'],view='summary',limit=1)['settings_read']
 parsed=urlsplit(entry['http']['url']);status,_,body=authoring_http.handle(root,parsed.path,parse_qs(parsed.query),'GET',b'')
 assert status==200 and json.loads(body)['target']==target
 effect=copy.deepcopy(idle['actions']['change']['http']['payload']);effect['values']['effort']='high'
 status,_,body=authoring_http.handle(root,'/authoring/session-settings',{},'POST',json.dumps(effect).encode());saved=json.loads(body)
 assert status==200 and saved['effect']=='RECORDED' and saved['receipt']['values']['effort']=='high'
 assert records.index(root).turns[tid]['provider_settings']==before
 invalid={**effect,'request_id':'invalid-public-001','values':{'role':'author','credential':'PUBLIC_SECRET_MUST_NOT_ECHO'}}
 status,_,body=authoring_http.handle(root,'/authoring/session-settings',{},'POST',json.dumps(invalid).encode());bad=json.loads(body)
 assert status==409 and bad['attribution']=='RESPONSE_BOUND_SCHEMA_REJECTION' and bad['request_sha256']==S.canonical_digest(invalid)
 assert 'PUBLIC_SECRET_MUST_NOT_ECHO' not in body.decode() and 'credential' not in body.decode()
 defaults=project_work_surface.handle('/work/session-preferences',{'project':['book']},'GET',repo_root=root)
 assert json.loads(defaults[2])['settings_read']
 projected=tools.execute(root,'book','review','help',{'operation':'session_settings_change'},turn_id=tid)
 assert projected['action']['permitted'] is False
 retain(root,'http-native-admitted-proof',{'pilot_active':pilot,'native_busy':refused,'idle':idle,'saved':saved,'schema_refusal':bad,'initial_settings_read':entry,'admitted_unchanged':before})


def test_project_after_commit_unknown_and_immutable_reader_recipient_metadata(settings_root,monkeypatch):
 root,session=settings_root;target={'kind':'project-defaults'};original=wire(root,target,provider='codex',model='public-main')
 from laplace.pipeline import projection_spec
 update=projection_spec.update_file
 def committed(*a,**k):update(*a,**k);raise OSError('public project acknowledgement lost after atomic replace')
 monkeypatch.setattr(projection_spec,'update_file',committed)
 lost=S.request(root,'book',original,door=HUMAN);assert lost['effect']=='UNKNOWN' and lookup(root,original)['effect']=='RECORDED'
 monkeypatch.setattr(projection_spec,'update_file',update)
 outcomes=[]
 for key,value in [('reader_profile',{'profile':'public-immutable-test-marker'}),('dispatch_id','WORK-public-child'),('source_execution',{'schema_version':'public-no-authority-marker'})]:
  restricted={**copy.deepcopy(session),'id':'WS-public-'+key.replace('_','-'),key:value};records.bank(root,restricted)
  request=wire(root,{'kind':'conversation','session_id':restricted['id']},effort='high')
  result=S.request(root,'book',request,door=HUMAN);assert result['effect']=='NOT_ADMITTED';outcomes.append(result)
  with pytest.raises(ValueError,match='immutable'):T.configure_session(root,'book',restricted['id'],{'effort':'high'})
 retain(root,'atomic-and-ceilings-proof',{'project_lost_ack':lost,'exact_project_request':lookup(root,original),'immutable_public_marker_fixtures':outcomes,'qualification':'Markers exercise refusal only, do not claim admitted reader/Source/dispatch authority.'})


def test_authored_alias_partial_origin_and_null_effort_are_truthful(settings_root):
 root,session=settings_root;target={'kind':'conversation','session_id':session['id']}
 alias=wire(root,target,model='public-main[1m]');saved=S.request(root,'book',alias,door=HUMAN)
 assert saved['effect']=='RECORDED' and saved['receipt']['values']['model']=='public-main' and saved['original_request']['values']['model']=='public-main[1m]'
 null=wire(root,target,effort=None);refused=S.request(root,'book',null,door=HUMAN)
 assert refused['effect']=='NOT_ADMITTED' and 'Null effort means no flag' in refused['reason'] and read(root,target)['effective']['effort']=='low'
 defaults=wire(root,{'kind':'project-defaults'},provider='codex',model='public-main',effort='low')
 preference=S.request(root,'book',defaults,door=HUMAN);assert preference['receipt']['values']['model_source']=='project-preference'
 from_default=T.new_session(root,'book','codex','','')
 assert from_default['model_source']=='project-preference'
 partial=wire(root,{'kind':'conversation','session_id':from_default['id']},effort='high');partial['values']={'effort':'high'}
 changed=S.request(root,'book',partial,door=HUMAN)
 assert changed['receipt']['values']['model_source']=='project-preference' and changed['current']['settings']['model']['provenance']['origin']=='retained-saved-value'
 retain(root,'alias-and-origin-proof',{'alias':saved,'null_refused':refused,'preference':preference,'partial':changed})


def test_owned_settings_declarations_help_and_reader_sources(settings_root):
 root,session=settings_root
 from laplace.native import declarations as D
 from laplace.web import writing_declared_http
 from laplace.writing.schemas import SCHEMAS
 from jsonschema import Draft202012Validator
 D.validate_help_declarations()
 payload=wire(root,{'kind':'conversation','session_id':session['id']})
 Draft202012Validator(SCHEMAS['session_settings_change']).validate(payload)
 Draft202012Validator(SCHEMAS['session_settings']).validate({'view':'pilot','request':{'action':'read','target':payload['target']}})
 for name in ('authoring/session-settings-read','work/session-preferences-read'):
  declaration=D.HTTP_DECLARATIONS[name]
  assert declaration.payload==S.http_contract('GET','conversation' if name.startswith('authoring') else 'project-defaults') and declaration.methods==('GET',)
 for name in ('authoring/session-settings-change','work/session-preferences-change'):
  assert D.HTTP_DECLARATIONS[name].payload==S.http_contract('POST','conversation' if name.startswith('authoring') else 'project-defaults')
 areas=D.help_areas('book');controls=D.help_areas('book','controls')
 encoded=len(json.dumps(areas).encode());canonical=len(json.dumps(areas,ensure_ascii=False,separators=(',',':')).encode())
 assert encoded<28672,(encoded,canonical)
 assert any(x['id']=='conversation:next-message' for x in areas['controls'])
 (root/'generated-help-areas.json').write_text(json.dumps(areas,ensure_ascii=False,indent=2)+'\n')
 (root/'generated-help-controls.json').write_text(json.dumps(controls,ensure_ascii=False,indent=2)+'\n')
 retain(root,'declarations-and-budget-proof',{'default_serializer_bytes':encoded,'canonical_bytes':canonical,'native_shared_schema':True,'HTTP_same_owner':True})
