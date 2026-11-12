"""Human/root read consumer of existing engine obligation semantics; never app Work migration."""
from pathlib import Path
import json
from laplace.core.identity import canonical_digest
from laplace.work.source_kernel import handle
SCHEMA='laplace.historical-obligations/1'
MAX_SCAN=64*1024*1024
MAX_ROWS=20000

def contract():
 return {'type':'object','required':['facet','source'],'additionalProperties':False,'properties':{
  'facet':{'const':'historical-obligations'},'source':{'enum':['work_orders','promises']},'view':{'enum':['catalogue','record']},
  'state':{'enum':['open','deferred','closed','all']},'offset':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':50},
  'as_of':{'type':'string','pattern':'^sha256:[0-9a-f]{64}$'},'id':{'type':'string','minLength':1,'maxLength':200},
  'expected_sha256':{'type':'string','pattern':'^sha256:[0-9a-f]{64}$'},'content_offset':{'type':'integer','minimum':0},'budget':{'type':'integer','minimum':1,'maximum':12000}}}

def read(root,scope,payload):
 from jsonschema import Draft202012Validator
 # Authority before any source lookup, metadata count or row read.
 if scope.kind!='owned-workspace' or scope.door not in {'http','sdk'}:raise ValueError('HISTORICAL_OBLIGATIONS_HUMAN_ROOT_ONLY')
 if next(Draft202012Validator(contract()).iter_errors(payload),None):raise ValueError('HISTORICAL_OBLIGATIONS_INVALID_REQUEST')
 from laplace.engine import sources,wake,engine_ledger
 from laplace.core.perimeter import public_repository_path as _safe
 from laplace.core.records.capture import line_hash,read_captured_row
 spec=sources.SOURCES[payload['source']];path=_safe(Path(root),spec['path'])
 rows=[];meta={};owned_meta={};cls='work_order' if payload['source']=='work_orders' else 'promise'
 malformed=0;complete=True;size=path.stat().st_size if path.exists() else 0
 if size>MAX_SCAN:raise ValueError('HISTORICAL_OBLIGATIONS_SCAN_BOUND')
 stamp=None if not path.exists() else (path.stat().st_dev,path.stat().st_ino,path.stat().st_size,path.stat().st_mtime_ns,path.stat().st_ctime_ns)
 if path.exists():
  with path.open('rb') as stream:
   while True:
    start=stream.tell();raw=stream.readline()
    if not raw:break
    if not raw.endswith(b'\n'):complete=False;break
    if len(rows)>=MAX_ROWS:raise ValueError('HISTORICAL_OBLIGATIONS_ROW_BOUND')
    try:row=json.loads(raw)
    except ValueError:malformed+=1;continue
    if not isinstance(row,dict):malformed+=1;continue
    rows.append(row)
    if row.get('id'):
     captured={'offset':start,'end':stream.tell(),'sha256':line_hash(raw),'row':row}
     kind=engine_ledger.record_class(row)
     meta[(str(row['id']),kind,captured['sha256'])]=captured
     if kind==cls:owned_meta[str(row['id'])]=captured
 def current():
  return None if not path.exists() else (path.stat().st_dev,path.stat().st_ino,path.stat().st_size,path.stat().st_mtime_ns,path.stat().st_ctime_ns)
 if current()!=stamp:raise ValueError('HISTORICAL_OBLIGATIONS_CUT_CHANGED')
 from datetime import datetime,timezone
 today=datetime.now(timezone.utc).date().isoformat()
 cut=canonical_digest({'source':payload['source'],'stamp':stamp,'account_date':today})
 if payload.get('as_of') and payload['as_of']!=cut:raise ValueError('HISTORICAL_OBLIGATIONS_CUT_CHANGED')
 if payload.get('view')=='record':
  if not payload.get('id') or not payload.get('expected_sha256'):raise ValueError('HISTORICAL_OBLIGATIONS_EXACT_RECORD_REQUIRED')
  selected=meta.get((payload['id'],cls,payload['expected_sha256']))
  if not selected or selected['sha256']!=payload['expected_sha256']:raise ValueError('HISTORICAL_OBLIGATIONS_RECORD_CHANGED')
  value,raw=read_captured_row(path,selected['offset'],selected['end'],selected['sha256'])
  if value!=selected['row'] or str(value.get('id'))!=payload['id'] or engine_ledger.record_class(value)!=cls or current()!=stamp:raise ValueError('HISTORICAL_OBLIGATIONS_RECORD_CHANGED')
  from laplace.engine.descent import _bounded_projection
  projected=_bounded_projection(handle=payload['id'],content_handle=selected['sha256'],media_type='application/json',total_bytes=len(raw),chunk=raw[payload.get('content_offset',0):payload.get('content_offset',0)+payload.get('budget',6000)],offset=payload.get('content_offset',0),budget=payload.get('budget',6000))
  nxt=projected.get('content_next_offset');return {**projected,'schema_version':SCHEMA,'view':'record','source':payload['source'],'id':payload['id'],'read_cut':cut,
    'next_read':handle({**payload,'content_offset':nxt}) if nxt is not None else None,'read':handle(payload),'qualification':'Exact historical engine record; not canonical app Work or evidence of promise fulfillment.'}
 account=wake.ledger_account(rows,cls,payload['source'],as_of=today)
 own={str(r['id']):r for r in rows if r.get('id') and engine_ledger.record_class(r)==cls}
 opens={r['id'] for r in account['open_rows']};deferred={r['id'] for r in account['deferred_rows']};state=payload.get('state','open')
 candidates=[]
 for ident,row in own.items():
  standing='open' if ident in opens else 'deferred' if ident in deferred else 'closed'
  if state!='all' and standing!=state:continue
  m=owned_meta[ident]
  candidates.append({'id':ident,'state':standing,'recorded_status':row.get('status'),
    'title':str(row.get('title') or row.get('what') or row.get('ask') or ident)[:300],
    'read':handle({'facet':'historical-obligations','source':payload['source'],'view':'record','id':ident,'expected_sha256':m['sha256']}),
    'canonical_app_work':False})
 candidates.sort(key=lambda r:r['id']);offset=payload.get('offset',0);limit=payload.get('limit',20);page=candidates[offset:offset+limit]
 if offset>len(candidates):raise ValueError('HISTORICAL_OBLIGATIONS_OFFSET')
 value={'schema_version':SCHEMA,'view':'catalogue','source':payload['source'],'title':'Historical engine work orders' if cls=='work_order' else 'Historical engine promises',
  'rows':page,'state':state,'scope':scope.public(),'read_cut':cut,
  'coverage':{'source_state':'AVAILABLE' if stamp is not None else 'ABSENT','source_available':stamp is not None,'known':len(own),'matching':len(candidates),'returned':len(page),'malformed_rows':malformed,'incomplete_tail':not complete,
   'scan_bytes':size,'qualification':'One selected registered source scanned and folded through engine wake.ledger_account; bounded returned metadata, not constant-I/O or a historical audit.'},
  'pagination':{'offset':offset,'next_read':handle({**payload,'offset':offset+len(page),'as_of':cut}) if offset+len(page)<len(candidates) else None},
  'read':handle(payload),'states':[{ 'value':v,'read':handle({'facet':'historical-obligations','source':payload['source'],'state':v})} for v in ['open','deferred','closed','all']],
  'qualification':'Separate historical engine obligations. No migration, priority, closure, scientific acceptance or execution authority; canonical namespace Work is a different owner.'}
 if len(json.dumps(value,ensure_ascii=False).encode())>28672:raise ValueError('HISTORICAL_OBLIGATIONS_RESPONSE_BOUND')
 return value
