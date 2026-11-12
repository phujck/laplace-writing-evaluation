"""Explicit retained Source meaning -> pure keeper input. No ingestion or authority from a read.

Custody stays in the selected Work handoff and existing Writing body store. Logical OP identities
are derived; actual counterparts require a verified active publication, never an alias map.
"""
from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import urlencode
from laplace.core import identity,bodies
from laplace.work import source_contracts as SC

SCHEMA='laplace.source-kernel/1'
CONSUMER='kernel.declared-source'
MAX_SELECTIONS=16
MAX_PINS=32
MAX_BYTES=256*1024
MAX_RESPONSE=SC.MAX_BUDGET
PIN={'type':'string','pattern':'^sha256:[0-9a-f]{64}$'}
SELECTION={'type':'object','required':['namespace','work_id','handoff_id','obligation_id'],'additionalProperties':False,
 'properties':{key:{'type':'string','minLength':1,'maxLength':200} for key in ['namespace','work_id','handoff_id','obligation_id']}}

def contract():
 return {'type':'object','required':['facet'],'additionalProperties':False,'properties':{
  'facet':{'const':'source-kernel'},'reference':{'type':'object'},'view':{'enum':['contracts','declaration','publications','prepare','counterpart','recover','segment','standing']},
  'namespace':{'type':'string','minLength':1,'maxLength':200},'selection':SELECTION,'segments':{'type':'array','minItems':1,'maxItems':16,'uniqueItems':True,'items':{'type':'string','minLength':1,'maxLength':64}},
  'semantic_handle':PIN,'fold_receipt_handle':PIN,'publication_handle':PIN,'content_handle':PIN,
  'node_id':{'type':'string','pattern':'^OP-SOURCE-[0-9a-f]{64}$'},
  'select':{'type':'string','minLength':1,'maxLength':80},
  'budget':{'type':'integer','minimum':1,'maximum':MAX_RESPONSE}}}

def handle(payload):
 p=identity.detached(payload) if hasattr(identity,'detached') else json.loads(json.dumps(payload))
 q={k:json.dumps(v,ensure_ascii=False,separators=(',',':')) if isinstance(v,(dict,list)) else v for k,v in p.items()}
 return {'request':p,'http':{'method':'GET','url':'/work/discovery?'+urlencode(q)},'native':{'operation':'project','payload':{'view':'discovery','request':p}}}

def _read_handle(payload):
 """One exact request/HTTP pair; native callers use the same request envelope."""
 value=handle(payload)
 return {key:value[key] for key in ('request','http')}


def _fit(value,budget):
 if len(identity.canonical_bytes(value))>budget:raise ValueError('SOURCE_KERNEL_BUDGET: select fewer segments; nothing was clipped or published.')
 return json.loads(json.dumps(value))

def _normalize(value,*,retained=False):
 """SC.normalize, the one admission. Only validation of a retained edition (the ordinary close)
 may name an operation no owner declares any more; every other admission check still applies."""
 try:return SC.normalize(value)
 except SC.Refusal as exc:
  if not retained or exc.details.get('code') not in ('UNKNOWN_TARGET','WRONG_OWNER'):raise
 version=value.get('version')
 if version is not None and (not isinstance(version,dict) or set(version)!={'declaration'} or not isinstance(version['declaration'],str) or not SC._VERSION.fullmatch(version['declaration'])):
  raise SC.Refusal('UNSUPPORTED_VERSION','A source-contract version is exactly {declaration: sha256:<64 hex>}.')
 return {'owner':value['owner'],'operation':value['identity']['operation'],'version':version['declaration'] if version else None}

def _selected(root,scope,payload,*,retained=False):
 from laplace.work import project_work as W
 s=payload.get('selection')
 if not s or not scope.admits(s['namespace']):raise ValueError('SOURCE_KERNEL_NOT_IN_SCOPE')
 task=W._tasks(s['namespace'],root).get(s['work_id'])
 phase=next((r for r in (task or {}).get('phases',()) if r.get('id')==s['handoff_id'] and r.get('phase')=='handoff'),None)
 held=(phase or {}).get('source_contracts',{}).get(s['obligation_id'])
 if not held or held.get('consumer')!=CONSUMER:raise ValueError('SOURCE_KERNEL_PUBLICATION_UNAVAILABLE')
 req=_normalize(payload['reference'],retained=retained)
 if (req['owner'],req['operation'])!=(held['owner'],held['operation']) or req['version'] not in (None,held['version']):raise ValueError('SOURCE_KERNEL_PUBLICATION_MISMATCH')
 names=sorted(payload.get('segments') or held['segments'])
 if any(name not in held['segments'] for name in names):raise ValueError('SOURCE_KERNEL_SEGMENT_NOT_RETAINED')
 return s,phase,held,names

def _body(root,ref,expected):
 from laplace.representation import writing_bodies
 if int(ref.get('bytes',ref.get('size',MAX_BYTES+1)))>MAX_BYTES:raise ValueError('SOURCE_KERNEL_INPUT_BUDGET')
 with bodies.budget(MAX_BYTES):value=json.loads(writing_bodies.read_bytes(ref,root))
 if identity.canonical_digest(value)!=expected:raise ValueError('SOURCE_KERNEL_CORRUPT_BODY')
 return value

BY='work.source_kernel'
STATES=('CURRENT','CARRIED','STALE','UNKNOWN')

def _retained_repository(root,phase):
 qualified=phase.get('source_basis')
 if qualified:return {'id':qualified['repository'],'checkout_identity':qualified['checkout_identity'],'base':qualified['base']}
 return {'id':'owned-workspace','identity':identity.canonical_digest(str(Path(root).resolve()))}

def _source(root,selection,phase):
 """Today's bytes of every retained pin, as provenance only.

 Raises only on retained values (pin custody). A pinned file that moved, vanished, became
 excluded or outgrew its bound is an observation the row's state reports, never a refusal.
 """
 from laplace.work import source_inventory as I,development_source as D
 from laplace.projects import project_data as C
 pins=phase.get('pins') or {}
 if not pins or len(pins)>MAX_PINS:raise ValueError('SOURCE_KERNEL_PINNED_PUBLIC_INPUTS_REQUIRED')
 qualified=phase.get('source_basis')
 observation={'repository':_retained_repository(root,phase),'observed':[],'moved':[],'unknown':None}
 if qualified:
  current=D.validate_review_basis(root,selection['namespace'],selection['work_id'],qualified,consumed_pins=pins)
  if current['status']!='CURRENT':
   # No function reads meaning at another checkout: only the retained edition can be stated.
   observation['unknown']='qualified source basis is %s (%s); meaning is compared only in the live tree'%(current['status'],current['reason'])
   return observation
  checkout=D.basis_checkout(root,selection['namespace'],selection['work_id'],qualified['repository'],'currentness')
 else:
  checkout=Path(root).resolve()
 total=0
 for path,expected in sorted(pins.items()):
  if not I._eligible(path):observation['unknown']='pinned file is now excluded from Source inputs: '+path;break
  try:item=C._file_record(checkout,C._safe(checkout,path))
  except FileNotFoundError:
   observation['moved'].append({'path':path,'retained_sha256':expected,'observed_sha256':None})
   observation['unknown']='pinned file is deleted: '+path;break
  except (OSError,ValueError) as exc:observation['unknown']='pinned file is unreadable: %s (%s)'%(path,type(exc).__name__);break
  total+=item['bytes']
  if item['bytes']>I.MAX_FILE or total>MAX_BYTES:observation['unknown']='pinned file is now over the Source input bound: '+path;break
  observation['observed'].append({'path':path,'sha256':item['sha256'],'bytes':item['bytes']})
  if not identity.revision_matches(expected,item['sha256']):
   observation['moved'].append({'path':path,'retained_sha256':expected,'observed_sha256':item['sha256']})
 if qualified and observation['moved'] and not observation['unknown']:
  observation['unknown']='qualified source bytes moved at another checkout; meaning is compared only in the live tree'
 return observation

def _meaning(root,phase,held):
 """The retained meaning only: its declaring path is the retained one, never loaded code."""
 context=held.get('kernel_context')
 if not context:raise ValueError('SOURCE_KERNEL_TYPED_CONTEXT_NOT_RETAINED')
 meaning=_body(root,context['body'],context['basis']);pins=phase.get('pins') or {}
 declaring=meaning.get('declaring_source') if isinstance(meaning.get('declaring_source'),dict) else {}
 if not isinstance(declaring.get('path'),str):raise ValueError('SOURCE_KERNEL_DECLARATION_EDITION_UNQUALIFIED')
 if declaring['path'] not in pins:raise ValueError('SOURCE_KERNEL_DECLARING_SOURCE_PIN_REQUIRED')
 if declaring.get('sha256')!=pins[declaring['path']]:raise ValueError('SOURCE_KERNEL_DECLARATION_EDITION_UNQUALIFIED')
 return context,meaning

def _current_meaning(held):
 """Today's declaration from loaded code, or None when no owner declares the operation any more."""
 for provider in SC.providers():
  value=provider()
  if (value['owner'],value['operation'])==(held['owner'],held['operation']):
   return {'declaring':'src/'+provider.__module__.replace('.','/')+'.py','declaration':value,'bases':SC.bases(value)}
 return None

def _context_basis(meaning,name):
 """The leaf context digest exactly as _content and _project compute it."""
 return identity.canonical_digest({'purpose':meaning.get('purpose'),'authority':meaning.get('authority'),'recovery':meaning.get('recovery'),
  'relations':[r for r in meaning.get('relations') or [] if name in r['segments']]})

def _state(observation,held,meaning,name,current):
 """One row's currentness. Meaning is equal when the segment basis and the leaf context both are.

 Every row checks the loaded declaration's module against the retained declaring path: a
 declaration that moved to another module is compared even when no pinned byte moved.
 """
 row={'state':'CURRENT','moved':json.loads(json.dumps(observation['moved'])),'changed_segments':[],
  'reason':'every pinned file has its retained bytes and the declaration is in its retained module','by':BY}
 if observation['unknown']:return {**row,'state':'UNKNOWN','reason':observation['unknown']}
 if current is None:return {**row,'state':'UNKNOWN','reason':'no owner declares this operation any more; no current meaning exists'}
 retained=meaning['declaring_source']['path'];relocated=current['declaring']!=retained
 if not observation['moved'] and not relocated:return row
 if relocated:row['declaring_moved']={'from':retained,'to':current['declaring']}
 cause=' and '.join((['pinned bytes moved'] if observation['moved'] else [])+(['the declaration moved to another module'] if relocated else []))
 differs=[]
 if current['bases'].get(name)!=held['segments'][name]['basis']:differs.append('segment')
 if _context_basis(current['declaration'],name)!=_context_basis(meaning,name):differs.append('leaf context (purpose, authority, recovery or relations)')
 if differs:
  return {**row,'state':'STALE','changed_segments':[name],'reason':cause+' and the current declaration differs in this '+' and '.join(differs)}
 return {**row,'state':'CARRIED','reason':cause+'; the consumed segment and its leaf context are unchanged'}

def _projection_pins(projection):
 try:target=json.loads(projection['exact_descent']['reference']);return target['repository'],target['source_inputs']
 except (KeyError,TypeError,ValueError) as exc:raise ValueError('SOURCE_KERNEL_INVALID_PUBLISHED_PROJECTION') from exc

def _check_pins(pins,phase):
 """Retained-value binding of stated source inputs to the selected custody's pins."""
 if not isinstance(pins,list) or not 1<=len(pins)<=MAX_PINS:raise ValueError('SOURCE_KERNEL_PUBLISHED_SOURCE_MISMATCH')
 observed={};total=0
 for pin in pins:
  if not isinstance(pin,dict) or set(pin)!={'path','sha256','bytes'} or not isinstance(pin['path'],str) or type(pin['bytes']) is not int or pin['bytes']<0 or pin['path'] in observed:
   raise ValueError('SOURCE_KERNEL_PUBLISHED_SOURCE_MISMATCH')
  observed[pin['path']]=pin['sha256'];total+=pin['bytes']
 if total>MAX_BYTES or set(observed)!=set(phase.get('pins') or {}) or any(not identity.revision_matches(expected,observed[path]) for path,expected in (phase.get('pins') or {}).items()):
  raise ValueError('SOURCE_KERNEL_PUBLISHED_SOURCE_MISMATCH')

def _carried_inputs(phase,observation,meaning,projection):
 """The retained pins with their retained sizes; None when no retained value states a moved pin's size."""
 pins=phase.get('pins') or {}
 if projection is not None:
  _,inputs=_projection_pins(projection);_check_pins(inputs,phase)
  return json.loads(json.dumps(inputs))
 moved={row['path'] for row in observation['moved']}
 kept={row['path']:row for row in observation['observed'] if row['path'] not in moved}
 declaring=meaning['declaring_source']
 rows=[]
 for path in sorted(pins):
  if path in kept:rows.append(dict(kept[path]))
  elif path==declaring['path'] and type(declaring.get('bytes')) is int:rows.append({'path':path,'sha256':pins[path],'bytes':declaring['bytes']})
  else:return None
 return rows

def _once(retained):
 """A lazy retained-leaf source is read at most once per validation."""
 if not callable(retained):return retained
 held=[]
 def value():
  if not held:held.append(retained() or {})
  return held[0]
 return value

def _lookup(retained):
 def lookup(lid):
  if retained is None:return None
  value=retained() if callable(retained) else retained
  return (value or {}).get(lid)
 return lookup

def _mode(retained,publish_retained):
 # Fresh selection keeps prepare's original call shape; only a close-validation call names its mode.
 return {'retained':retained,'publish_retained':True} if publish_retained else ({'retained':retained} if retained is not None else {})

def _active_selected(root):
 """The active publication's retained leaves; none when no verified publication exists."""
 try:
  from laplace.representation.source_publication import current
  return current(root).get('selected_content') or {}
 except (ImportError,ValueError,OSError,RuntimeError):return {}

def _content(held,name,facts,meaning,repository,pins):
 return {'schema_version':'laplace.source-kernel-facts/1','subject':SC.reference(held['owner'],held['operation']),'segment':name,'basis':held['segments'][name]['basis'],
  'facts':facts,'relations':[r for r in meaning['relations'] if name in r['segments']],
  'purpose':meaning['purpose'],'authority':meaning.get('authority'),'recovery':meaning.get('recovery'),
  'repository':repository,'source_inputs':pins,'runtime_source_linkage':'UNVERIFIED_LOADED_CODE'}

def _logical_id(repository,subject,name):
 logical_repository={k:v for k,v in repository.items() if k!='base'}
 return 'OP-SOURCE-'+identity.canonical_digest({'repository':logical_repository,'subject':subject,'segment':name})[7:]

def _project(content):
 repository=content['repository'];subject=content['subject'];name=content['segment'];digest=identity.canonical_digest(content)
 lid=_logical_id(repository,subject,name)
 context_basis=identity.canonical_digest({k:content[k] for k in ['purpose','authority','recovery','relations']})
 target={'reference':subject,'segment':name,'basis':content['basis'],'repository':repository,'source_inputs':content['source_inputs'],'context_basis':context_basis}
 route={'kind':'source-contract','reference':json.dumps(target,sort_keys=True,separators=(',',':')),'source':'','fold':''}
 projection={'schema_version':SCHEMA,'content_handle':digest,'exact_descent':route,'source_reference':subject,'segment_basis':content['basis'],'typed_relations':content['relations']}
 semantic=identity.canonical_digest({'schema_version':'laplace.semantic-leaf-evidence/1','node_id':lid,'content_handle':digest,'exact_descent':route})
 return lid,projection,semantic

def published_facts(root,scope,request,projection):
 """Canonical retained facts after the active owner proves this exact published projection.

 No current checkout/file reads: the verified publication projection supplies its
 original source coordinates, which must still bind the selected Work custody.
 This helper is no publication proof or fresh admission on its own.
 """
 s,phase,held,names=_selected(root,scope,{'facet':'source-kernel','view':'prepare',**request})
 if len(names)!=1:raise ValueError('SOURCE_KERNEL_SELECT_ONE_SEGMENT')
 if not isinstance(projection,dict) or len(identity.canonical_bytes(projection))>MAX_RESPONSE:raise ValueError('SOURCE_KERNEL_INVALID_PUBLISHED_PROJECTION')
 _,pins=_projection_pins(projection)
 from laplace.work import source_inventory as I
 if isinstance(pins,list) and any(isinstance(pin,dict) and (not isinstance(pin.get('path'),str) or not I._eligible(pin['path'])
   or type(pin.get('bytes')) is not int or pin['bytes']>I.MAX_FILE) for pin in pins):
  raise ValueError('SOURCE_KERNEL_PUBLISHED_SOURCE_MISMATCH')
 return _retained_facts(root,phase,held,names[0],projection)

def _retained_facts(root,phase,held,name,projection):
 """The exact retained content a published projection states; reads no current file or loaded declaration."""
 if not isinstance(projection,dict) or len(identity.canonical_bytes(projection))>MAX_RESPONSE:raise ValueError('SOURCE_KERNEL_INVALID_PUBLISHED_PROJECTION')
 repository,pins=_projection_pins(projection)
 if repository!=_retained_repository(root,phase):raise ValueError('SOURCE_KERNEL_PUBLISHED_SOURCE_MISMATCH')
 _check_pins(pins,phase)
 _,meaning=_meaning(root,phase,held)
 content=_content(held,name,_body(root,held['segments'][name]['body'],held['segments'][name]['basis']),meaning,repository,pins)
 if _project(content)[1]!=projection:raise ValueError('SOURCE_KERNEL_PUBLISHED_MEANING_CHANGED')
 return content

def prepare(root,scope,payload,*,retained=None,publish_retained=False):
 """Private detached complete leaf projection of one explicit canonical publication; no writes.

 This owner gives every leaf one state: CURRENT, CARRIED, STALE or UNKNOWN (`currentness`).
 Fresh selection admits CURRENT and CARRIED only. With publish_retained (the ordinary close
 validating an existing packet) a STALE or UNKNOWN leaf is the exact parent leaf in `retained`
 (node id -> published projection, or a callable returning that mapping), labelled.
 """
 s,phase,held,names=_selected(root,scope,payload,**({'retained':True} if publish_retained else {}));context,meaning=_meaning(root,phase,held)
 lookup=_lookup(_once(retained));observation=_source(root,s,phase);repository=observation['repository']
 # Today's declaration for every row: its module is compared with the retained declaring path.
 current=None if observation['unknown'] else _current_meaning(held)
 subject=SC.reference(held['owner'],held['operation']);versioned=SC.reference(held['owner'],held['operation'],held['version'])
 leaves={};metadata=[];states={};pins=None;total=0
 for name in names:
  segment=held['segments'][name];facts=_body(root,segment['body'],segment['basis']);total+=len(identity.canonical_bytes(facts))
  if total>MAX_BYTES:raise ValueError('SOURCE_KERNEL_INPUT_BUDGET')
  lid=_logical_id(repository,subject,name);state=_state(observation,held,meaning,name,current);inputs=None
  if state['state']=='CURRENT':inputs=observation['observed']
  elif state['state']=='CARRIED':
   inputs=_carried_inputs(phase,observation,meaning,lookup(lid))
   if inputs is None:state={**state,'state':'UNKNOWN','reason':'pinned bytes moved with unchanged meaning, but no retained edition states the size of every moved pin'}
  if state['state'] in ('STALE','UNKNOWN'):
   if not publish_retained:raise ValueError('SOURCE_KERNEL_SOURCE_%s: %s'%(state['state'],state['reason']))
   parent=lookup(lid)
   if parent is None:raise ValueError('SOURCE_KERNEL_RETAINED_LEAF_UNAVAILABLE')
   content=_retained_facts(root,phase,held,name,parent)
  else:
   content=_content(held,name,facts,meaning,repository,inputs)
  if pins is None:pins=content['source_inputs']
  elif pins!=content['source_inputs']:raise ValueError('SOURCE_KERNEL_RETAINED_INPUTS_DISAGREE')
  lid,projection,semantic=_project(content);states[lid]=state
  leaves[lid]={'kind':'declared-source-contract','name':lid,'essence':meaning['purpose']['text']+' · '+name,
   'keywords':sorted({held['owner'],held['operation'],name,CONSUMER}), 'sealed':False,'semantic_parent':'operational://declared-source',
   'embedding_text':identity.canonical_bytes(content).decode(),'projection':projection,'ref':subject}
  metadata.append({'id':lid,'segment':name,'basis':segment['basis'],'content_handle':projection['content_handle'],'semantic_handle':semantic,
   'prepare_read':handle({'facet':'source-kernel','reference':versioned,'selection':s,'namespace':s['namespace'],'segments':[name],'view':'prepare'}),
   'retained_read':handle({'facet':'source-kernel','reference':versioned,'view':'segment','selection':s,'namespace':s['namespace'],'segments':[name],'budget':MAX_RESPONSE}),'typed_relations':content['relations']})
 # Detect an input moving while selected bodies were resolved: one observation states every row.
 if _source(root,s,phase)!=observation:raise ValueError('SOURCE_KERNEL_SOURCE_MOVED_DURING_READ')
 return {'leaves':leaves,'metadata':metadata,'selection':s,'reference':versioned,'repository':repository,'source_inputs':pins,
  'retained_segments':sorted(held['segments']),
  'purpose':meaning['purpose'],
  'custody':{'handoff_id':s['handoff_id'],'obligation_id':s['obligation_id'],'kernel_context_basis':context['basis']},
  'currentness':states}

def input_frame(root,selections,*,scope=None,retained=None,publish_retained=False):
 """One finite explicit selection. Equal leaves deduplicate; conflicting editions never win by order."""
 from laplace.work import owner_discovery as O
 if not isinstance(selections,list) or len(selections)>MAX_SELECTIONS:raise ValueError('SOURCE_KERNEL_SELECTION_BUDGET')
 scope=scope or O.owned_workspace('kernel-publication');leaves={};receipts=[];currentness={};retained=_once(retained)
 for request in selections:
  _validate(request,retained=publish_retained);item=prepare(root,scope,request,**_mode(retained,publish_retained))
  for lid,leaf in item['leaves'].items():
   if lid in leaves and (leaves[lid]!=leaf or currentness[lid]!=item['currentness'][lid]):raise ValueError('SOURCE_KERNEL_CONFLICTING_EDITIONS')
   leaves[lid]=leaf;currentness[lid]=item['currentness'][lid]
  receipts.append({k:item[k] for k in ['selection','reference','repository','source_inputs','custody']})
 return {'leaves':leaves,'receipts':receipts,'basis':identity.canonical_digest({'content':{k:v['projection']['content_handle'] for k,v in sorted(leaves.items())},'receipts':receipts}),
  'currentness':currentness}

PUBLICATION_INPUT_SCHEMA='laplace.source-publication-inputs/1'

def _operator_scope(scope):
 # This is an actual adapter carrier, never a request field or a read capability.
 if getattr(scope,'kind',None)!='owned-workspace' or getattr(scope,'door',None) not in {'sdk','http','publication-cli'}:
  raise ValueError('SOURCE_PUBLICATION_OPERATOR_REQUIRED')

def publication_request_contract():
 return {'type':'object','required':['reference','selection','segments'],'additionalProperties':False,'properties':{
  'reference':{'type':'object'},'selection':SELECTION,'segments':{'type':'array','minItems':1,'maxItems':16,'uniqueItems':True,'items':{'type':'string','minLength':1,'maxLength':64}}}}

def _publication_request(value,*,retained=False):
 from jsonschema import Draft202012Validator
 schema=publication_request_contract()
 if next(Draft202012Validator(schema).iter_errors(value),None):raise ValueError('SOURCE_PUBLICATION_INVALID_INPUT')
 ref=_normalize(value['reference'],retained=retained)
 if ref['version'] is None:raise ValueError('SOURCE_PUBLICATION_VERSION_REQUIRED')
 return {'reference':SC.reference(ref['owner'],ref['operation'],ref['version']),
  'selection':json.loads(json.dumps(value['selection'])),'segments':sorted(value['segments'])}

def _prepared_bases(item):
 return {'prepared_basis':identity.canonical_digest({
  'selection':item['selection'],'reference':item['reference'],'custody':item['custody'],
  'leaves':sorted([{'id':row['id'],'content_handle':row['content_handle']} for row in item['metadata']],key=lambda row:row['id'])}),
  'source_basis':identity.canonical_digest({'repository':item['repository'],'source_inputs':item['source_inputs']})}

def publication_packet_contract():
 return {'type':'object','required':['schema_version','inputs'],'additionalProperties':False,'properties':{
  'schema_version':{'const':PUBLICATION_INPUT_SCHEMA},'inputs':{'type':'array','minItems':1,'maxItems':MAX_SELECTIONS*16,'items':{
   'type':'object','required':['request','node_id','prepared_basis','source_basis'],'additionalProperties':False,
   'properties':{'request':{'type':'object'},'node_id':{'type':'string','pattern':'^OP-SOURCE-[0-9a-f]{64}$'},'prepared_basis':PIN,'source_basis':PIN}}}}}

def _packet(value,*,retained=False):
 from jsonschema import Draft202012Validator
 schema=publication_packet_contract()
 if next(Draft202012Validator(schema).iter_errors(value),None):raise ValueError('SOURCE_PUBLICATION_INVALID_PACKET')
 rows=[]
 for row in value['inputs']:
  req=_publication_request(row['request'],retained=retained)
  if len(req['segments'])!=1:raise ValueError('SOURCE_PUBLICATION_PACKET_ONE_SEGMENT')
  rows.append({**row,'request':req})
 if len(identity.canonical_bytes(value))>MAX_BYTES:raise ValueError('SOURCE_PUBLICATION_PACKET_BUDGET')
 # Canonical normalization is not a mutable observation or an acknowledgement.
 unique={identity.canonical_bytes(row):row for row in rows}
 packet={'schema_version':PUBLICATION_INPUT_SCHEMA,'inputs':[unique[key] for key in sorted(unique)]}
 _grouped_requests(packet)
 return json.loads(json.dumps(packet))

def _grouped_requests(packet):
 grouped={}
 for row in packet['inputs']:
  req=row['request'];key=identity.canonical_bytes({k:req[k] for k in ['reference','selection']})
  item=grouped.setdefault(key,{'facet':'source-kernel','reference':req['reference'],'selection':req['selection'],'segments':[],'view':'prepare'})
  item['segments']=sorted(set(item['segments']+req['segments']))
  if len(item['segments'])>16:raise ValueError('SOURCE_KERNEL_SELECTION_BUDGET')
 if len(grouped)>MAX_SELECTIONS:raise ValueError('SOURCE_KERNEL_SELECTION_BUDGET')
 return [grouped[key] for key in sorted(grouped)]

def prepare_publication_inputs(root,actual_scope,inputs):
 """Pure operator preparation: exact per-segment expected facts, no publication authority in JSON."""
 _operator_scope(actual_scope)
 if not isinstance(inputs,list) or not 1<=len(inputs)<=MAX_SELECTIONS:raise ValueError('SOURCE_KERNEL_SELECTION_BUDGET')
 requests=[_publication_request(value) for value in inputs];rows=[]
 for request in requests:
  for segment in request['segments']:
   req={**request,'segments':[segment]};item=prepare(root,actual_scope,{'facet':'source-kernel','view':'prepare',**req})
   rows.append({'request':req,'node_id':item['metadata'][0]['id'],**_prepared_bases(item)})
 packet=_packet({'schema_version':PUBLICATION_INPUT_SCHEMA,'inputs':rows})
 # Revalidation closes movement between the per-segment and joined observations.
 return validate_publication_inputs(root,actual_scope,packet)

def validate_publication_inputs(root,actual_scope,owner_packet,*,retained=None):
 """Re-resolve canonical custody and compare every expected basis before consuming private leaves.

 Without `retained` this is fresh selection: CURRENT and CARRIED rows only. With `retained` (the
 parent publication's leaves) it is the ordinary close's validation of an existing packet: STALE
 and UNKNOWN rows publish their exact parent leaf, labelled in frame['currentness'].
 """
 publish=retained is not None;retained=_once(retained)
 _operator_scope(actual_scope);packet=_packet(owner_packet,retained=publish);observed={}
 for row in packet['inputs']:
  item=prepare(root,actual_scope,{'facet':'source-kernel','view':'prepare',**row['request']},**_mode(retained,publish))
  if row['node_id']!=item['metadata'][0]['id'] or any(row[key]!=value for key,value in _prepared_bases(item).items()):
   raise ValueError('SOURCE_PUBLICATION_INPUT_CHANGED')
  observed[identity.canonical_bytes(row)]={
   'content':item['metadata'][0]['content_handle'],'state':item['currentness'][row['node_id']],
   'receipt':{k:item[k] for k in ['selection','reference','repository','source_inputs','custody']}}
 frame=input_frame(root,_grouped_requests(packet),scope=actual_scope,**_mode(retained,publish))
 # Each source resolver checks before/after body reads. The joined observation
 # must still contain those exact validated leaf contents, states and custody receipts.
 for row in packet['inputs']:
  expected=observed[identity.canonical_bytes(row)]
  if (frame['leaves'][row['node_id']]['projection']['content_handle']!=expected['content'] or expected['receipt'] not in frame['receipts']
    or frame['currentness'][row['node_id']]!=expected['state']):
   raise ValueError('SOURCE_PUBLICATION_INPUT_CHANGED')
 return {'packet':packet,'frame':frame}

def merge_publication_inputs(root,actual_scope,parent_packet,new_packet,replaced_leaf_ids):
 """Carry unselected owner receipt entries unchanged; no live refresh of retained Source."""
 _operator_scope(actual_scope);new=validate_publication_inputs(root,actual_scope,new_packet)
 replaced=set(replaced_leaf_ids)
 if not replaced<=set(new['frame']['leaves']):raise ValueError('SOURCE_PUBLICATION_REPLACEMENT_MISMATCH')
 parent=_packet(parent_packet) if parent_packet is not None else {'inputs':[]}
 return _packet({'schema_version':PUBLICATION_INPUT_SCHEMA,'inputs':
  [row for row in parent['inputs'] if row['node_id'] not in replaced]+new['packet']['inputs']})

def _validate(payload,*,retained=False):
 from jsonschema import Draft202012Validator
 if next(Draft202012Validator(contract()).iter_errors(payload),None):raise ValueError('SOURCE_KERNEL_INVALID_REQUEST')
 if 'select' in payload and payload.get('view')!='declaration':raise ValueError('SOURCE_KERNEL_SELECT_REQUIRES_DECLARATION')
 if payload.get('view')=='contracts':
  if set(payload)-{'facet','view','namespace','budget'}:raise ValueError('SOURCE_KERNEL_UNEXPECTED_SELECTION')
 else:_normalize(payload.get('reference'),retained=retained)

def read(root,scope,payload):
 _validate(payload);root=Path(root).resolve();view=payload.get('view','publications');budget=payload.get('budget',16384)
 from laplace.work import owner_discovery as O
 if payload.get('namespace'):
  if not scope.admits(payload['namespace']):raise ValueError('SOURCE_KERNEL_NOT_IN_SCOPE')
  scope=O.project_scope(payload['namespace'],scope.door)
 # Every selected publication is confined to its exact Work namespace, including
 # human/root reads following a project-issued child handle. This only narrows.
 if payload.get('selection'):
  namespace=payload['selection']['namespace']
  if not scope.admits(namespace):raise ValueError('SOURCE_KERNEL_NOT_IN_SCOPE')
  scope=O.project_scope(namespace,scope.door)
 if scope.kind=='project':payload={**payload,'namespace':scope.namespace}
 if view=='contracts':
  rows=[]
  for declaration in SC.declarations():
   ref=SC.reference(declaration['owner'],declaration['operation'])
   base={'facet':'source-kernel','reference':ref,**({'namespace':scope.namespace} if scope.kind=='project' else {})}
   rows.append({'reference':ref,'purpose':declaration['purpose']['text'],
    'declaration_read':handle({**base,'view':'declaration'}),'publications_read':handle({**base,'view':'publications'}),
    'inventory_read':handle({'facet':'source-inventory','projection':'inputs','reference':identity.reference('core.identity','subsystem',{'id':declaration['owner']}),**({'project_lens':scope.namespace} if scope.kind=='project' else {})})})
  return _fit({'schema_version':SCHEMA,'state':'CONTRACTS','scope':scope.public(),'contracts':rows,'read':handle(payload),
   'qualification':'Declared Source owner facts; not kernel ingestion, review acceptance or execution authority.'},budget)
 req=SC.normalize(payload['reference'])
 if view=='declaration':
  value=SC.read(root,SC.normalize(payload['reference'],select=payload.get('select'),budget=budget),admits=scope.admits,read_scope=scope)
  base={key:value for key,value in payload.items() if key!='select'}
  result={'schema_version':SCHEMA,'state':'DECLARATION','scope':scope.public(),'declaration':value,'read':_read_handle(payload)}
  if payload.get('select'):
   result['up_read']=_read_handle(base)
  elif value['state']=='CURRENT_DECLARATION':
   choices={row['next']['select']:row['next']['select'] for row in value['segments']+value['steps']}
   result['constituent_read']={**_read_handle(base),'field':'select','query_field':'select','values':choices,
    'observation':{'declaration':value['reference']['version']['declaration'],'segment_bases':{row['id']:row['basis'] for row in value['segments']}}}
  return _fit(result,budget)
 if view in {'segment','standing'}:
  s,phase,held,names=_selected(root,scope,payload)
  if view=='standing':
   return _fit({'schema_version':SCHEMA,'state':'CURRENT_STANDING','scope':scope.public(),'selection':s,
    'standing':SC.canonical_standing(root,held['owner'],held['operation'],admits=lambda ns:ns==s['namespace'] and scope.admits(ns)),
    'read':handle(payload),'qualification':'Current owner review standing, separate from retained facts and kernel publication.'},budget)
  if len(names)!=1:raise ValueError('SOURCE_KERNEL_SELECT_ONE_SEGMENT')
  name=names[0];facts=_body(root,held['segments'][name]['body'],held['segments'][name]['basis'])
  context=held.get('kernel_context')
  if context:
   meaning=_body(root,context['body'],context['basis'])
   relations=[row for row in meaning.get('relations',[]) if name in row['segments']]
   relation_coverage={'state':'AVAILABLE','known':len(relations),'returned':len(relations),'basis':context['basis']}
  else:
   relations=[];relation_coverage={'state':'UNAVAILABLE','reason':'Original handoff retained no typed kernel context; facts are not backfilled.'}
  return _fit({'schema_version':SCHEMA,'state':'RETAINED_SEGMENT','scope':scope.public(),'selection':s,
   'reference':SC.reference(held['owner'],held['operation'],held['version']),'segment':name,'basis':held['segments'][name]['basis'],'facts':facts,
   'typed_relations':relations,'relation_coverage':relation_coverage,
   'read':_read_handle(payload),'qualification':'Exact retained segment and original context; not a current declaration or kernel publication.'},budget)
 if view=='publications':
  if payload.get('selection') or payload.get('segments'):raise ValueError('SOURCE_KERNEL_UNEXPECTED_SELECTION')
  records=SC.record(root,req['owner'],req['operation'],admits=scope.admits)
  choices=[]
  for row in records['publications']:
   if row['consumer']!=CONSUMER or req['version'] not in (None,row['version']):continue
   namespace,_,wid=row['work'].partition('::');selection={'namespace':namespace,'work_id':wid,'handoff_id':row['handoff_id'],'obligation_id':row['obligation_id']}
   choices.append({'selection':selection,'version':row['version'],'segments':sorted(row['segments']),
    'read':_read_handle({'facet':'source-kernel','reference':SC.reference(req['owner'],req['operation'],row['version']),'view':'prepare','selection':selection,'segments':[sorted(row['segments'])[0]],'budget':15360,**({'namespace':scope.namespace} if scope.kind=='project' else {})})})
  return _fit({'schema_version':SCHEMA,'state':'PUBLICATIONS','reference':payload['reference'],'scope':scope.public(),'publications':choices,
   'kernel':{'state':'UNRESOLVED','reason':'Only explicitly selected retained kernel-consumer publications can prepare a leaf; preparation is not publication.'},'coverage':{'known':len(choices),'returned':len(choices)},'read':handle(payload)},budget)
 if view=='recover':
  # Exact published reading is not a new source admission. The active owner
  # verifies its retained packet, artifact and content identities; today's raw
  # source pins belong to fresh preparation/commit, never this recovery path.
  keys=['semantic_handle','publication_handle','node_id','content_handle']
  if not all(payload.get(key) for key in keys) or payload.get('fold_receipt_handle'):raise ValueError('SOURCE_KERNEL_ACTIVE_PUBLICATION_REQUIRED')
  if not req['version'] or not payload.get('selection') or len(payload.get('segments') or [])!=1:raise ValueError('SOURCE_KERNEL_EXACT_PUBLICATION_SELECTION_REQUIRED')
  from laplace.representation.source_publication import read_object
  reference=SC.reference(req['owner'],req['operation'],req['version'])
  target={'reference':reference,'selection':payload['selection'],'segments':payload['segments'],**{key:payload[key] for key in keys}}
  observed=read_object(root,scope,target)
  return _fit({'schema_version':SCHEMA,'state':'RECOVERED','scope':scope.public(),'selection':payload['selection'],'reference':reference,
   **{key:observed[key] for key in keys},'publication':observed['publication'],
   'facts':observed['facts'],'read':handle(payload),
   'qualification':'Exact active selected contribution and retained typed meaning; not Source review acceptance, adoption or new effect authority.'},budget)
 # The counterpart view reads what is published: a STALE or UNKNOWN row there is its retained
 # edition, labelled by the publication owner. Prepare itself stays fresh selection.
 item=prepare(root,scope,payload,**({'retained':lambda:_active_selected(root),'publish_retained':True} if view=='counterpart' else {}))
 result={'schema_version':SCHEMA,'state':'PREPARED','reference':item['reference'],'selection':item['selection'],'scope':scope.public(),
  'purpose':item['purpose'],'retained':item['custody'],'source_inputs':item['source_inputs'],'repository':item['repository'],
  'leaves':[{**{key:value for key,value in row.items() if key not in {'prepare_read','typed_relations','retained_read'}},
   'retained_read':{field:value for field,value in row['retained_read'].items() if field in {'request','http'}},
   'relation_coverage':{'known':len(row['typed_relations']),'returned':0,'qualification':'Exact typed relations are in this selected retained fact read.'}} for row in item['metadata']],
  'current_standing_read':_read_handle({**payload,'view':'standing'}),
  'kernel':{'state':'UNRESOLVED','reason':'Pure prepared projection; no verified fold was inspected.'},
  'counterpart_read':_read_handle({**payload,'view':'counterpart'}),'read':_read_handle(payload),
  'qualification':'Retained meaning, current owner standing and published kernel are separate. No authority or knowledge effect from this read.'}
 result.update(_prepared_bases(item))
 names=item['retained_segments'];selected=[row['segment'] for row in item['metadata']]
 if len(names)>1:
  result.pop('current_standing_read');result.pop('counterpart_read')
  result['view_read']={**_read_handle(payload),'field':'view','query_field':'view','values':{'Current owner standing':'standing','Published counterpart':'counterpart'}}
 navigation={'known':len(names),'selected':len(selected),'segments':selected,
  'up_read':_read_handle({'facet':'source-kernel','reference':item['reference'],'namespace':item['selection']['namespace'],'view':'publications','budget':budget})}
 if len(selected)==1:
  index=names.index(selected[0]);navigation.update(segment=selected[0],position=index)
  for key,offset in [('previous_read',-1),('next_read',1)]:
   if 0<=index+offset<len(names):navigation[key]=_read_handle({**payload,'view':'prepare','segments':[names[index+offset]],'budget':budget})
 result['segment_navigation']=navigation
 if view=='counterpart':
  from laplace.representation.source_publication import counterparts
  result['kernel']=counterparts(root,scope,item)
  for row in result['kernel'].get('counterparts',[]):
   row['typed_descent']=row['read']
   leaf=next(value for value in item['metadata'] if value['id']==row['id'])
   row['read']=handle({'facet':'source-kernel','reference':item['reference'],'namespace':item['selection']['namespace'],
    'selection':item['selection'],'segments':[leaf['segment']],'view':'recover','node_id':row['id'],
    'content_handle':row['content_handle'],'semantic_handle':row['semantic_handle'],
    'publication_handle':row['publication_handle'],'budget':MAX_RESPONSE})
 return _fit(result,budget)


def descend(root,scope,target):
 """Resolve an exact retained meaning, independently of which equal publication selected it."""
 required={'reference','segment','basis','repository','source_inputs','context_basis'}
 if not isinstance(target,dict) or set(target)!=required or len(identity.canonical_bytes(target))>32768:raise ValueError('SOURCE_KERNEL_INVALID_DESCENT')
 req=SC.normalize(target['reference'])
 if req['version'] is not None:raise ValueError('SOURCE_KERNEL_DESCENT_USES_EXACT_SEGMENT_BASIS')
 records=SC.record(root,req['owner'],req['operation'],admits=scope.admits)
 for row in records['publications']:
  if row['consumer']!=CONSUMER or target['segment'] not in row['segments'] or row['segments'][target['segment']]['basis']!=target['basis']:continue
  ns,_,wid=row['work'].partition('::')
  payload={'facet':'source-kernel','reference':SC.reference(req['owner'],req['operation'],row['version']),'selection':{'namespace':ns,'work_id':wid,'handoff_id':row['handoff_id'],'obligation_id':row['obligation_id']},'segments':[target['segment']],'view':'prepare'}
  try:item=prepare(root,scope,payload)
  except (ValueError,OSError):continue
  content=json.loads(next(iter(item['leaves'].values()))['embedding_text'])
  context_basis=identity.canonical_digest({k:content[k] for k in ['purpose','authority','recovery','relations']})
  if item['repository']==target['repository'] and item['source_inputs']==target['source_inputs'] and context_basis==target['context_basis']:
   return content
 raise ValueError('SOURCE_KERNEL_EXACT_MEANING_UNAVAILABLE')
