"""Read/report the existing technical friction channel; no guidance or work mutation."""
from __future__ import annotations

from laplace.core.identity import canonical_digest
from laplace.core.records import capture
from laplace.writing import records as writing_records
import copy,json,hashlib
from pathlib import Path
from urllib.parse import urlencode

PERMITTED_MODES=frozenset({'work','discuss','review','revise'})


def read_contract():
    return {'type':'object','properties':{key:{'type':'string'} for key in ('id','view','cursor','as_of')},'additionalProperties':False}


def report_contract():
    return {'type':'object','required':['owning_layer','value','chain'],
        'properties':{'owning_layer':{'type':'string','minLength':1},'value':{'type':'string','minLength':1,'maxLength':12000},
        'chain':{'type':'array','minItems':1,'maxItems':8,'items':{'type':'string','minLength':1,'maxLength':300}},
        'tool_record_id':{'type':'string'},'proposal':{'type':'string','maxLength':2000}},'additionalProperties':False}


def handle(project,payload=None):
    return {'native_request':{'verb':'read','concept':'technical-friction@project','target':project+('::'+payload['id'] if payload and payload.get('id') else ''),'expected':[],
            'payload':payload or {},'by':''},'http':{'method':'GET','url':'/corpus/friction?'+urlencode({'corpus':project,'view':'reports',**(payload or {})})}}


def _metadata(row,start,end,order,line_hash):
    from laplace.pipeline.adjudicate import RESOLUTION
    if row.get('kind') not in {'friction','fork'} and row.get('record')!=RESOLUTION and not row.get('supersedes'):return None
    value={key:row.get(key) for key in ('id','kind','record','node','ts','by','status','owning_layer','supersedes','evidence','target','chain') if key in row}
    if isinstance(row.get('value'),str):value['summary']=row['value'][:240]
    value.update(record=value.get('record') or value.get('kind'),_offset=start,_end=end,_order=order,_hash=line_hash)
    return value


def read(root,project,payload):
    from laplace.research import corpus_ingest
    from laplace.work import author_history_metrics as metadata
    from laplace.pipeline.friction_consumer import open_frictions
    query=dict(payload);unknown=set(query)-set(read_contract()['properties'])
    if unknown or any(not isinstance(value,str) for value in query.values()):raise ValueError('Invalid technical friction read fields.')
    if query.get('view') not in (None,'','reports','history'):raise ValueError('Technical report history must be requested explicitly.')
    if 'id' in query and not query['id']:raise ValueError('Exact technical report requires a returned nonempty id.')
    if query.get('id') and set(query)-{'id'}:raise ValueError('Exact technical report read accepts only its returned id; page/history selectors belong to the collection.')
    with writing_records.index_lock:
        idx=writing_records.index(root,corpus_ingest._rewire_path(root,project),_metadata)
        ident=query.get('id')
        if ident:
            rows=idx.by_id.get(ident,[])
            if len(rows)!=1:raise ValueError('Exact report is missing or ambiguous.')
            row=rows[0]
            with idx.path.open('rb') as stream:stream.seek(row['_offset']);raw=stream.read(row['_end']-row['_offset'])
            if 'sha256:'+hashlib.sha256(raw).hexdigest()!=row['_hash']:raise ValueError('Exact report changed; refresh its owner read.')
            return {'project':project,'record':json.loads(raw),'read_handle':handle(project,{'id':ident})}
        # The existing consumer validates resolution evidence before retiring reports.
        identity=canonical_digest({'project':project,'view':query.get('view') or 'reports'})
        token=capture.decode_cut(query['cursor']) if query.get('cursor') else None
        cut=capture.decode_cut(query['as_of']) if query.get('as_of') else token
        if any(value and value['query']!=identity for value in (token,cut)):raise ValueError('Report cut belongs to another scope.')
        if token and cut and any(token.get(key)!=cut.get(key) for key in ('query','upper','revision')):raise ValueError('Report cursor/cut disagree.')
        upper=cut['upper'] if cut else idx.order
        retained=[row for row in idx.rows if row['_order']<=upper]
        revision=canonical_digest([(row.get('id'),row['_hash']) for row in retained])
        if cut and cut['revision']!=revision:raise ValueError('Technical report history changed.')
        rows=retained if query.get('view')=='history' else open_frictions(retained)
        rows=sorted([row for row in rows if row.get('kind') in {'friction','fork'}],key=lambda row:row['_order'],reverse=True)
        offset=(token or {}).get('offset',0);page=rows[offset:offset+20]
        stamped={'v':1,'query':identity,'upper':upper,'revision':revision}
        return {'project':project,'records':[{**{key:value for key,value in row.items() if not key.startswith('_')},
                    'read_handle':handle(project,{'id':row['id']})} for row in page],
                'as_of':capture.encode_cut(stamped),'count':len(rows),
                'pagination':{'offset':offset,'limit':20,'next_read':handle(project,{**query,'cursor':capture.encode_cut({**stamped,'offset':offset+len(page)})}) if offset+len(page)<len(rows) else None},
                'basis':'Existing evidence-qualified friction consumer; reports never mutate manuscript guidance or automatically complete/block work.'}


def report(root,project,turn_id,payload):
    from laplace.research import corpus_ingest
    from laplace.work import author_history_metrics as metadata
    from jsonschema import Draft202012Validator
    error=next(Draft202012Validator(report_contract()).iter_errors(payload),None)
    if error:raise ValueError('Technical report shape: '+error.message)
    idx=writing_records.index(root);turn=idx.turns.get(turn_id)
    if not turn or idx.project(turn)!=project:raise ValueError('An actual bound agent turn is required to report a capability gap.')
    evidence={'owner':'authoring_surface','project':project,'session_id':turn.get('session_id'),'turn_id':turn_id,
              'work_id':turn.get('work_id'),'dispatch_id':turn.get('dispatch_id'),
              'membership':'Observed runtime/technical scope, not scientific node membership or work acceptance.'}
    if payload.get('tool_record_id'):
        matches=[row for row in idx.by_id.get(payload['tool_record_id'],[]) if row.get('turn_id')==turn_id and idx.project(row)==project and row['record'] in {'writing-tool-read','writing-tool-action','writing-tool-failure'}]
        if len(matches)!=1:raise ValueError('Technical report evidence does not name one observed tool record in this turn.')
        evidence['tool_record_id']=matches[0]['id'];evidence['tool_operation']=matches[0].get('operation');evidence['row_sha256']=matches[0]['_hash']
    result=corpus_ingest.friction_add(root,project,{'kind':'friction','node':'authoring:'+project+'::'+turn_id,
        'owning_layer':payload['owning_layer'],'value':payload['value'],'chain':payload['chain'],
        'proposal':payload.get('proposal'),'by':'eigen:session','target':turn_id,'evidence':evidence})
    if result.get('error'):raise ValueError(result['error'])
    return {**result,'read_handle':handle(project,{'id':result['record']['id']}),'effects':['technical-report-history'],
            'work_status_changed':False,'guidance_changed':False}
