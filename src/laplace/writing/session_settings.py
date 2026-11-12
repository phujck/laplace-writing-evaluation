"""Scoped next-message preferences, using existing WSS/spec custody and resolver.

Read observations are not permission grants. Exact requests/withdrawals share the
same owner lock; no settings read starts a provider or constructs a prompt.
"""
from __future__ import annotations
import copy,json,uuid
from pathlib import Path
from urllib.parse import urlencode
from laplace.core.identity import canonical_digest

SCHEMA='laplace.session-settings/1'
REQUEST_SCHEMA='laplace.session-settings-request/1'
FIELDS=('provider','model','effort')
HISTORY='session_preferences_requests'


class Refused(ValueError):
 def __init__(self,message,payload):
  self.details={'schema_version':REQUEST_SCHEMA,'effect':'NOT_ADMITTED','terminal':True,'durable':False,
    'attribution':'RESPONSE_BOUND_SCHEMA_REJECTION','request_sha256':canonical_digest(payload),'error':message}
  super().__init__(message)


def error_details(error):return copy.deepcopy(error.details) if isinstance(error,Refused) else {}


def target_contract():
 return {'oneOf':[{'type':'object','additionalProperties':False,'required':['kind','session_id'],'properties':{'kind':{'const':'conversation'},'session_id':{'type':'string','minLength':1,'maxLength':160}}},{'type':'object','additionalProperties':False,'required':['kind'],'properties':{'kind':{'const':'project-defaults'}}}]}


def values_contract():
 return {'type':'object','additionalProperties':False,'minProperties':1,'properties':{'provider':{'type':'string','enum':['codex','claude']},'model':{'type':'string','minLength':1,'maxLength':8000},'effort':{'oneOf':[{'enum':['low','medium','high','xhigh','max','ultra']},{'type':'null'}]}}}


def change_contract():
 return {'type':'object','additionalProperties':False,'required':['action','target','request_id','expected_basis','values'],'properties':{'project':{'type':'string','minLength':1},'action':{'const':'change'},'target':target_contract(),'request_id':{'type':'string','minLength':8,'maxLength':96},'expected_basis':{'type':'string','pattern':'^sha256:[a-f0-9]{64}$'},'values':values_contract()}}


def contract():
 common={'project':{'type':'string','minLength':1},'target':target_contract()}
 request_id={'type':'string','minLength':8,'maxLength':96};sha={'type':'string','pattern':'^sha256:[a-f0-9]{64}$'}
 return {'oneOf':[change_contract(),{'type':'object','additionalProperties':False,'required':['action','target'],'properties':{**common,'action':{'const':'read'}}},{'type':'object','additionalProperties':False,'required':['action','target','request_id'],'properties':{**common,'action':{'const':'request'},'request_id':request_id,'intent_digest':sha}},{'type':'object','additionalProperties':False,'required':['action','target','request_id','intent_digest','original_request'],'properties':{**common,'action':{'const':'withdraw'},'request_id':request_id,'intent_digest':sha,'original_request':change_contract()}}]}


def _wire(project,payload):
 from jsonschema import Draft202012Validator
 if not isinstance(payload,dict):raise ValueError('Settings request must be an object.')
 if payload.get('project',project)!=project:raise ValueError('Settings belong to another project.')
 value={**copy.deepcopy(payload),'project':project}
 error=next(Draft202012Validator(contract()).iter_errors(value),None)
 if error:
  # jsonschema.message may include the complete submitted object or a secret
  # supplied in an unknown field. Only schema-owned labels leave this boundary.
  path='.'.join(str(k) if k in {'project','action','target','kind','session_id','request_id','expected_basis','values','provider','model','effort','intent_digest','original_request'} else '<field>' for k in error.path) or '<request>'
  raise Refused('REJECTED_BEFORE_EFFECTS: settings schema '+str(error.validator)+' at '+path,value)
 return value


def _validate_request(row,project,target):
 if not isinstance(row,dict) or row.get('schema_version')!=REQUEST_SCHEMA or row.get('project')!=project or row.get('target')!=target or row.get('terminal') is not True or row.get('effect') not in {'RECORDED','NOT_ADMITTED'}:raise ValueError('Settings request custody is unsupported.')
 original=_wire(project,row.get('original_request'))
 if original['action']!='change' or original['target']!=target or original['request_id']!=row.get('request_id') or intent_digest(original)!=row.get('intent_digest'):raise ValueError('Settings request intent custody is inconsistent.')
 if row['effect']=='RECORDED' and (not isinstance(row.get('receipt'),dict) or not isinstance(row['receipt'].get('values'),dict)):raise ValueError('Recorded settings receipt is unavailable.')
 return row


def intent_digest(original):
 return canonical_digest({k:v for k,v in original.items() if k not in {'action','request_id'}})


def _path(target):return '/authoring/session-settings' if target['kind']=='conversation' else '/work/session-preferences'


def handle(project,request):
 return {'http':{'method':'GET','url':_path(request['target'])+'?'+urlencode({'project':project,'request':json.dumps(request,sort_keys=True,separators=(',',':'))})},
         'sdk':{'function':'session_settings_request','project':project,'payload':copy.deepcopy(request)},
         **({'native':{'operation':'session_settings','payload':{'view':'pilot','request':copy.deepcopy(request)}}} if request['target']['kind']=='conversation' else {})}


def _snapshot(root,project,sid):
 from laplace.writing import records
 idx=records.index(root);path=Path(root)/'contract/talk.jsonl'
 if idx.malformed_rows or idx.offset!=(path.stat().st_size if path.exists() else 0):raise ValueError('Settings journal custody is incomplete or corrupt.')
 rows=[r for r in idx.by_session.get(sid,()) if r.get('record') in {'writing-session-settings','writing-binding'} and idx.project(r)==project]
 initial=[r for r in idx.by_id.get(sid,()) if r.get('record')=='writing-session' and idx.project(r)==project]
 if len(initial)!=1 or idx.journal_id_counts.get(sid)!=1:raise ValueError('Conversation is missing or ambiguous in this project.')
 fields=['id','project','provider','model','effort','model_source','tier','role','reader_profile','source_execution','workflow_event_id','dispatch_id','settings_revision','settings_provenance','settings_request','provider_changed','native_id','ts']
 session=records.selected_journal_fields(project,sid,root,fields=fields);session={k:v for k,v in session.items() if v is not None or k=='effort'};requests={}
 for meta in rows:
  row=records.selected_journal_fields(project,meta['id'],root,fields=fields)
  if meta['record']=='writing-session-settings':
   session.update({k:row[k] for k in (*FIELDS,'model_source','tier','settings_revision','settings_provenance') if row.get(k) is not None or k=='effort' and 'effort' in meta})
   request=row.get('settings_request')
   if request is not None:
    _validate_request(request,project,{'kind':'conversation','session_id':sid})
    rid=request.get('request_id')
    if not isinstance(rid,str) or rid in requests:raise ValueError('Settings request custody is ambiguous.')
    requests[rid]=request
 session['_settings_execution_bound']=any(r.get('settings_execution_bound') for r in idx.by_session.get(sid,()) if idx.project(r)==project)
 return session,requests,idx


def _spec(root,project):
 from laplace.pipeline import projection_spec
 path=projection_spec.spec_path(project,root)
 if path is None:raise ValueError('Unknown settings project.')
 raw=path.read_bytes() if path.exists() else b'{}';spec=json.loads(raw)
 if not isinstance(spec,dict) or not isinstance(spec.get('manuscript',{}),dict):raise ValueError('Project settings custody is unsupported.')
 history=spec.get('manuscript',{}).get(HISTORY,{})
 if not isinstance(history,dict) or any(not isinstance(k,str) or not isinstance(v,dict) or v.get('schema_version')!=REQUEST_SCHEMA or v.get('request_id')!=k or v.get('project')!=project or v.get('target')!={'kind':'project-defaults'} for k,v in history.items()):raise ValueError('Project settings request custody is unsupported.')
 for row in history.values():_validate_request(row,project,{'kind':'project-defaults'})
 prefs=spec.get('manuscript',{}).get('session_preferences',{})
 if not isinstance(prefs,dict):raise ValueError('Project preference custody is unsupported.')
 return path,spec,prefs,history


def _basis(project,target,values,revision):
 return canonical_digest({'project':project,'target':target,'values':{k:values.get(k) for k in (*FIELDS,'model_source','tier')},'revision':revision})


def _normalise(root,values,*,origin='named'):
 from laplace.writing import provider_catalogue
 from laplace.work.project_work import resolve_session_settings
 catalogue=provider_catalogue.provider_catalogue(root)
 provider=next((p for p in catalogue.get('providers',[]) if p.get('id')==values.get('provider') and p.get('available')),None)
 if provider is None:raise ValueError('Provider is not available in the passive catalogue; inspect or explicitly refresh providers.')
 resolved=resolve_session_settings(provider,values,strict=True,origin=origin)
 if values.get('effort') is None and resolved['effort'] is not None:raise ValueError('Null effort means no flag; choose a supported effort for this model.')
 return resolved


def _provenance(before,authored,resolved):
 previous=before.get('settings_provenance') or {};result={}
 for key in FIELDS:
  known=key in authored
  origin='authored-choice' if known else 'retained-saved-value'
  item={'origin':origin,'authored':authored.get(key) if known else None,'value':resolved[key],'application_boundary':'future messages only','prior_origin':(previous.get(key) or {}).get('origin','UNKNOWN')}
  if known and authored[key]!=resolved[key]:item['normalization']='existing-provider-alias-or-effort-capability'
  result[key]=item
 return result


def _problem(root,session):
 from laplace.writing import turn_jobs,child_hosts
 if session.get('reader_profile'):return 'IMMUTABLE_READER_SETTINGS'
 if session.get('workflow_event_id') or session.get('source_execution') or session.get('dispatch_id') or session.get('_settings_execution_bound') or session.get('role') not in (None,'author','review'):return 'ADMITTED_RECIPIENT_SETTINGS_IMMUTABLE'
 if any(j.get('session_id')==session['id'] and not j.get('done') for j in turn_jobs._JOBS.values()):return 'SESSION_BUSY'
 if child_hosts.child_execution(root,session['id']).get('state') in {'STARTING','WAITING','RUNNING','ORPHANED','UNKNOWN-OWNERSHIP'}:return 'SESSION_BUSY_OR_UNKNOWN_OWNERSHIP'
 return None


def _actor(root,project,target,door,*,write=False):
 from laplace.pipeline import registry
 if registry.resolve(project,repo_root=root) is None:raise ValueError('Select an existing settings project.')
 if door.get('origin') not in {'human','sdk','native'}:raise ValueError('Settings require an actual local or native caller.')
 if door.get('origin')=='native':
  from laplace.writing.tool_sessions import _settings_caller
  turn=_settings_caller(root,project,door.get('turn_id'))
  if target['kind']=='conversation' and target['session_id']!=turn['session_id']:raise ValueError('Native settings are this conversation only.')
  if write:
   if target['kind']=='project-defaults':raise ValueError('Project defaults require human/local SDK action.')
   from laplace.writing import turn_admission
   admitted=turn_admission.native_write_admission(root,project,door.get('mode'),door.get('turn_id'))
   if not admitted['permitted']:raise ValueError(admitted['code'])


def _role(root,project,target,session,idx):
 from laplace.writing import operating
 if target['kind']=='project-defaults':return {'state':'PREFERENCE_ONLY','meaning':'Future ordinary conversations; no role or permission is granted.'}
 role=session.get('role','author');mode='review' if role=='review' else 'work';declared=operating.role_permissions()[mode]
 turns=[r for r in idx.by_session.get(session['id'],()) if r.get('record')=='writing-turn' and idx.project(r)==project]
 latest=turns[-1] if turns else None
 return {'session_role':role,'role_mutable':False,'response_modes':['review'] if role=='review' else ['work','discuss','revise'],
  'description':operating.ROLES[mode],'declared_operations':declared,'conditional':'Payload, current source, actual turn/profile/recipient and scoped return authority are revalidated by existing owners; this list is not an available-action grant.',
  'review_transition':'Independent review requires a separate review conversation; settings cannot upgrade its role.',
  'latest_admitted':{'turn_id':latest['id'],'settings':copy.deepcopy(latest.get('provider_settings')),'mode':latest.get('mode'),'read':{'http':{'method':'GET','url':'/authoring/session-turn?'+urlencode({'project':project,'id':latest['id'],'view':'turn'})}}} if latest else None}


def inspect(root,project,target,*,door):
 _actor(root,project,target,door);root=Path(root).resolve()
 from laplace.writing import provider_catalogue
 if target['kind']=='conversation':
  session,_requests,idx=_snapshot(root,project,target['session_id']);values={k:session.get(k) for k in FIELDS};revision=session.get('settings_revision',0);saved=session;problem=_problem(root,session);role=_role(root,project,target,session,idx)
 else:
  _path_,spec,saved,_requests=_spec(root,project)
  from laplace.work.project_work import session_choice
  from laplace.writing.turn_admission import DEFAULT_PROVIDER
  resolved=session_choice(project,{'provider':saved.get('provider') or DEFAULT_PROVIDER,**saved},root)
  values={k:resolved.get(k) for k in FIELDS};revision=None;problem=None;role=_role(root,project,target,None,None)
 basis=_basis(project,target,saved,revision);read=handle(project,{'action':'read','target':target});rid='settings-'+uuid.uuid4().hex
 payload={'project':project,'action':'change','target':copy.deepcopy(target),'request_id':rid,'expected_basis':basis,'values':copy.deepcopy(values)}
 request_read=handle(project,{'action':'request','target':target,'request_id':rid})
 withdrawal={'http':{'method':'POST','url':_path(target),'payload':{'project':project,'action':'withdraw','target':copy.deepcopy(target),'request_id':rid}},'required_inputs':['intent_digest','original_request']}
 permitted=not problem and door.get('origin')!='native'
 facts={}
 for key in FIELDS:
  lineage=copy.deepcopy((saved.get('settings_provenance') or {}).get(key))
  if target['kind']=='project-defaults' and key not in saved:
   lineage={'origin':'ordinary-admission-provider-default' if key=='provider' else 'role-tier-default','value':values.get(key),'application_boundary':'future new ordinary conversations only','observation':'Existing resolver fallback at this read; not a stored preference.'}
  facts[key]={'value':values.get(key),'origin':lineage.get('origin') if lineage else ('recorded-'+saved['model_source'] if key=='model' and saved.get('model_source') else 'UNKNOWN'),
   'provenance':lineage,'meaning':'Current saved/normalized next-message value; equality to a default does not establish inheritance.'}
 catalogue=provider_catalogue.provider_catalogue(root)
 title=(idx.sessions.get(session['id'],{}).get('title') or next((r['catalogue_display_title'] for r in idx.by_session.get(session['id'],()) if r.get('catalogue_display_title')),'New conversation')) if target['kind']=='conversation' else 'Future conversation defaults'
 return {'schema_version':SCHEMA,'project':project,'title':title,'target':copy.deepcopy(target),'basis':basis,'settings_revision':revision,'effective':values,'settings':facts,
  'legacy':{k:saved.get(k) for k in ('model_source','tier')},'saved':{k:copy.deepcopy(saved[k]) for k in (*FIELDS,'model_source','tier') if k in saved} if target['kind']=='project-defaults' else {'id':session['id'],'role':session.get('role','author')},
  'application_boundary':'Future new ordinary conversations' if target['kind']=='project-defaults' else 'Future messages in this logical conversation; admitted turns remain unchanged',
  'authority':role,'providers':copy.deepcopy(catalogue.get('providers',[])),'provider_observation':{k:catalogue.get(k) for k in ('observed_at','updated_at','observation_scope','cached')},
  'read':read,'actions':{'change':{'permitted':permitted,'reason':problem or ('Active native turns retain the busy refusal; use human/local SDK after quiescence.' if door.get('origin')=='native' else None),
   'http':{'method':'POST','url':_path(target),'payload':payload},'values_schema':values_contract(),'request_read':request_read,'withdraw':withdrawal,'intent_projection':{'algorithm':'sha256-canonical-json-utf8','excluded_fields':['action','request_id']}}}}


def _answer(root,project,target,rid,row=None,*,unknown=None,replayed=False):
 result={'schema_version':REQUEST_SCHEMA,'project':project,'target':copy.deepcopy(target),'request_id':rid,'effect':'UNKNOWN' if unknown else row['effect'] if row else 'NONE','terminal':bool(row and row.get('terminal')),'replayed':replayed,'current_read':handle(project,{'action':'read','target':target}), 'read':handle(project,{'action':'request','target':target,'request_id':rid})}
 if unknown:result['reason']=str(unknown)
 if row:result.update({k:copy.deepcopy(row[k]) for k in ('intent_digest','original_request','receipt','reason') if k in row})
 return result


def _existing(requests,payload,digest=None):
 old=requests.get(payload['request_id'])
 if old and digest and old.get('intent_digest')!=digest:raise ValueError('Settings request_id was already used with another intent.')
 return old


def _row(project,payload,digest,effect,*,receipt=None,reason=None):
 return {'schema_version':REQUEST_SCHEMA,'project':project,'target':copy.deepcopy(payload['target']),'request_id':payload['request_id'],'intent_digest':digest,'original_request':copy.deepcopy(payload),'effect':effect,'terminal':True,**({'receipt':receipt} if receipt else {}),**({'reason':reason} if reason else {})}


def _decision(root,project,payload,current,basis):
 if payload['expected_basis']!=basis:return None,'CHANGED_SETTINGS_BASIS'
 if payload['target']['kind']=='conversation':
  problem=_problem(root,current)
  if problem:return None,problem
 base={k:current.get(k) for k in FIELDS}
 if payload['target']['kind']=='project-defaults':
  from laplace.work.project_work import session_choice
  from laplace.writing.turn_admission import DEFAULT_PROVIDER
  base=session_choice(project,{'provider':current.get('provider') or DEFAULT_PROVIDER,**current},root)
 try:values=_normalise(root,{**base,**payload['values']},origin='project-preference' if payload['target']['kind']=='project-defaults' else 'named')
 except ValueError as error:return None,str(error)
 if payload['target']['kind']=='conversation' and 'model' not in payload['values'] and values['model']==current.get('model') and current.get('model_source'):
  values['model_source']=current['model_source']
 return values,None


def request(root,project,payload,*,door):
 payload=_wire(project,payload);target=payload['target'];_actor(root,project,target,door);root=Path(root).resolve()
 if door.get('origin')=='native' and target['kind']=='project-defaults' and payload['action'] in {'change','withdraw'}:
  raise ValueError('Project defaults require explicit human/local SDK authority.')
 if payload['action']=='read':return inspect(root,project,target,door=door)
 if payload['action']=='request':
  try:
   history=_snapshot(root,project,target['session_id'])[1] if target['kind']=='conversation' else _spec(root,project)[3]
   old=_existing(history,payload,payload.get('intent_digest'))
   return _answer(root,project,target,payload['request_id'],old)
  except (OSError,ValueError) as error:
   if 'another intent' in str(error):raise
   return _answer(root,project,target,payload['request_id'],unknown=error)
 original=payload
 if payload['action']=='withdraw':
  original=_wire(project,payload['original_request'])
  if original['action']!='change' or original['target']!=target or original['request_id']!=payload['request_id']:raise ValueError('Withdrawal must name the exact original settings request.')
 digest=intent_digest(original)
 if payload['action']=='withdraw' and payload['intent_digest']!=digest:raise ValueError('Withdrawal intent differs from the exact original settings request.')
 if target['kind']=='conversation':
  from laplace.writing import turn_admission,turn_jobs,records
  with turn_jobs._LOCK,turn_admission.session_settings_lock(root,target['session_id']):
   try:current,history,_idx=_snapshot(root,project,target['session_id'])
   except (OSError,ValueError) as error:return _answer(root,project,target,payload['request_id'],unknown=error)
   old=_existing(history,original,digest)
   if old:
    result=_answer(root,project,target,payload['request_id'],old,replayed=True)
    try:result['current']=inspect(root,project,target,door=door)
    except Exception as error:result['current_observation']={'state':'UNAVAILABLE','reason':str(error)}
    return result
   _actor(root,project,target,door,write=True)
   basis=_basis(project,target,current,current.get('settings_revision',0));values=None;reason='WITHDRAWN'
   if payload['action']=='change':values,reason=_decision(root,project,payload,current,basis)
   record={'record':'writing-session-settings','id':'WSS-'+uuid.uuid4().hex,'project':project,'session_id':target['session_id']}
   if values is not None:
    changed=any(values.get(k)!=current.get(k) for k in (*FIELDS,'model_source','tier'))
    revision=current.get('settings_revision',0)+(1 if changed else 0)
    provenance=_provenance(current,payload['values'],values)
    after={**current,**values,'settings_revision':revision}
    receipt={'before_basis':basis,'after_basis':_basis(project,target,after,revision),'values':values,'settings_revision':revision,'record_id':record['id'],'noop':not changed}
    if changed:record.update(**values,settings_revision=revision,settings_provenance=provenance,provider_changed=values['provider']!=current['provider'],previous_native_id=current.get('native_id'))
    outcome=_row(project,original,digest,'RECORDED',receipt=receipt)
   else:outcome=_row(project,original,digest,'NOT_ADMITTED',reason=reason)
   if values is not None:record['settings_provenance']=provenance
   record['settings_request']=outcome
   try:records.bank(root,record)
   except Exception as error:return _answer(root,project,target,payload['request_id'],unknown=error)
   result=_answer(root,project,target,payload['request_id'],outcome)
 else:
  from laplace.pipeline import projection_spec
  answer={}
  class Replay(Exception):pass
  def update(spec):
   nonlocal answer
   if not isinstance(spec,dict) or not isinstance(spec.get('manuscript',{}),dict):raise ValueError('Project settings custody is unsupported.')
   manuscript=spec.setdefault('manuscript',{});current=manuscript.get('session_preferences',{});history=manuscript.setdefault(HISTORY,{})
   if not isinstance(current,dict) or not isinstance(history,dict):raise ValueError('Project settings custody is unsupported.')
   for key,prior in history.items():
    if not isinstance(prior,dict) or prior.get('request_id')!=key:raise ValueError('Project request key custody is inconsistent.')
    _validate_request(prior,project,target)
   old=_existing(history,original,digest)
   if old:answer={'row':copy.deepcopy(old),'replayed':True};raise Replay()
   _actor(root,project,target,door,write=True)
   basis=_basis(project,target,current,None);values=None;reason='WITHDRAWN'
   if payload['action']=='change':values,reason=_decision(root,project,payload,current,basis)
   if values is not None:
    after={**current,**values,'settings_provenance':_provenance(current,payload['values'],values)}
    outcome=_row(project,original,digest,'RECORDED',receipt={'before_basis':basis,'after_basis':_basis(project,target,after,None),'values':values,'noop':all(values.get(k)==current.get(k) for k in (*FIELDS,'model_source','tier'))})
    manuscript['session_preferences']=after
   else:outcome=_row(project,original,digest,'NOT_ADMITTED',reason=reason)
   history[payload['request_id']]=outcome;answer={'row':copy.deepcopy(outcome),'replayed':False};return spec
  try:
   path,*_=_spec(root,project);projection_spec.update_file(path,update)
   result=_answer(root,project,target,payload['request_id'],answer['row'],replayed=answer['replayed'])
  except Replay:
   result=_answer(root,project,target,payload['request_id'],answer['row'],replayed=True)
  except ValueError as error:
   if 'another intent' in str(error):raise
   return _answer(root,project,target,payload['request_id'],unknown=error)
  except Exception as error:return _answer(root,project,target,payload['request_id'],unknown=error)
 try:result['current']=inspect(root,project,target,door=door)
 except Exception as error:result['current_observation']={'state':'UNAVAILABLE','reason':str(error)}
 return result


def _strict_json(raw):
 def closed(pairs):
  result={}
  for key,value in pairs:
   if key in result:raise ValueError('Duplicate settings JSON field: '+key)
   result[key]=value
  return result
 return json.loads(raw,object_pairs_hook=closed)


def http_request(root,project,path,query,method,payload,*,raw_body=None):
 """Existing family adapter; guarded requests have one exact query carrier."""
 if method=='GET':
  if set(query)-{'project','request'} or any(isinstance(v,list) and len(v)!=1 for v in query.values()):raise ValueError('Settings query is closed and single-valued.')
  raw=query.get('request');raw=raw[0] if isinstance(raw,list) else raw
  if not raw:raise ValueError('Follow the issued settings read request.')
  payload=_strict_json(raw)
  if not isinstance(payload,dict):raise ValueError('Settings request must be a JSON object.')
  if payload.get('action') not in {'read','request'}:raise ValueError('Settings GET is inspection only.')
 elif method!='POST':raise ValueError('Settings accepts GET or POST.')
 elif payload.get('action') not in {'change','withdraw'}:raise ValueError('Settings POST changes or explicitly withdraws one request.')
 if method=='POST' and raw_body is not None:
  if _strict_json(raw_body)!=payload:raise ValueError('Settings body differs from the submitted exact JSON.')
 expected='conversation' if path=='/authoring/session-settings' else 'project-defaults'
 if payload.get('target',{}).get('kind')!=expected:raise ValueError('Settings target differs from this family.')
 return request(root,project,payload,door={'origin':'human'})


def _scoped_variants(kind):
 variants=contract()['oneOf'];target=target_contract()['oneOf'][0 if kind=='conversation' else 1]
 for variant in variants:
  variant['properties']['target']=copy.deepcopy(target)
  if 'original_request' in variant['properties']:variant['properties']['original_request']['properties']['target']=copy.deepcopy(target)
 return variants


def native_change_contract(legacy):
 variants=_scoped_variants('conversation')
 return {'oneOf':[copy.deepcopy(legacy),variants[0],variants[3]]}


def http_contract(method,kind):
 variants=_scoped_variants(kind);project={'type':'string','minLength':1}
 if method=='GET':
  rich={'type':'object','additionalProperties':False,'required':['project','request'],'properties':{'project':project,'request':{'oneOf':[variants[1],variants[2]]}}}
  return {'oneOf':[rich,{'type':'object','additionalProperties':False,'required':['project'],'properties':{'project':project}}]} if kind=='project-defaults' else rich
 properties={'project':project,**{key:{'type':['string','null']} if key=='effort' else {'type':'string'} for key in FIELDS}}
 required=['project']
 if kind=='conversation':properties['session_id']={'type':'string','minLength':1};required.append('session_id')
 legacy={'type':'object','additionalProperties':False,'required':required,'properties':properties}
 return {'oneOf':[legacy,*[{'allOf':[variant,{'required':['project']}]} for variant in (variants[0],variants[3])]]}
