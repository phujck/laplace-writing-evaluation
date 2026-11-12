"""Bounded metadata descent through the existing captured definition owner.

No saved query or body fanout. A cut is an observation, never caller authority.
The legacy rich/v1 definition readers keep their own existing limits.
"""
from __future__ import annotations
import copy
from pathlib import Path
from laplace.core import identity
from laplace.core.records import capture

HISTORY='laplace.workflow-definition-history/1'
LINEAGE='laplace.workflow-definition-lineage/1'
FACETS=('history-page','lineage','lineage-page','saved-version')
CAPTURE_BYTES=100*1024*1024
METADATA_ROWS=100_000


def _D():
    from laplace.pipeline import workflow_definitions
    return workflow_definitions


def request_contract():
    return {'type':'object','properties':{'facet':{'enum':list(FACETS)},'reference':{'type':'object'},
        'definition_id':{'type':'string'},'version':{'type':'string'},'project_lens':{'type':'string'},
        'selected_version':{'type':'string','pattern':'^sha256:[0-9a-f]{64}$'},
        'body_offset':{'type':'integer','minimum':0},'body_limit':{'type':'integer','minimum':1,'maximum':8000},
        'as_of':{'type':'string','maxLength':4096},'offset':{'type':'integer','minimum':0},
        'limit':{'type':'integer','minimum':1,'maximum':50},
        'capture_max_bytes':{'type':'integer','minimum':1},'metadata_max_rows':{'type':'integer','minimum':1}},
        'required':['facet'],'additionalProperties':False,'anyOf':[{'required':['reference']},{'required':['definition_id']}]}


def _limits(payload):
    values={'capture_max_bytes':payload.get('capture_max_bytes',CAPTURE_BYTES),
            'metadata_max_rows':payload.get('metadata_max_rows',METADATA_ROWS)}
    if any(type(v)!=int or v<=0 for v in values.values()):raise _D().Refused('INVALID_CAPTURE_BUDGET')
    return values


def entry(caller,ident,head=None,*,selected_version=None,facet='history-page',**extra):
    return _D().scoped_handle(caller,ident,head,facet=facet,
        **({'selected_version':selected_version} if selected_version else {}),**extra)


def _select(root,caller,payload,*,transfer_project=None):
    from laplace.pipeline import workflow_definition_records as R
    D=_D();R._admit(caller);limits=_limits(payload)
    ident,version=D._selector(payload,strict=True)
    # Scope/selector precede even this existing log's admission metadata.
    if transfer_project is not None and not caller.admits(transfer_project):raise D.Refused('NOT_IN_SCOPE')
    path=R._path(root)
    if path.exists() and path.stat().st_size>limits['capture_max_bytes']:
        raise D.Refused('CAPTURE_RESOURCE_BOUND','Dispatch capture exceeds the explicitly admitted byte budget')
    frame=R.select(root,caller,{'definition_id':ident,**({'version':version} if version else {})},transfer_project=transfer_project,detach=False,**limits)
    if frame['index'].order>limits['metadata_max_rows']:
        raise D.Refused('CAPTURE_RESOURCE_BOUND','Captured log row cardinality exceeds the admitted metadata budget')
    return frame,limits


def _cut(root,caller,frame,selected_version,limits):
    row=frame['selected']['row']
    return {'v':1,'upper':frame['selected']['order'],'query':identity.canonical_digest({
        'interpretation':LINEAGE,'scope_id':_D()._scope_id(root,caller),'definition_id':row['definition_id'],
        'head':row['definition_revision'],'unit':'definition-version','limits':limits}),
        'revision':identity.canonical_digest(frame['signature'])}


def capture_lineage(root,caller,reference,*,transfer_project=None,capture_max_bytes=CAPTURE_BYTES,metadata_max_rows=METADATA_ROWS):
    """Private lightweight captured prefix; metadata only, actual Scope first."""
    return _select(root,caller,{'reference':reference,'capture_max_bytes':capture_max_bytes,'metadata_max_rows':metadata_max_rows},transfer_project=transfer_project)[0]


def read(root,caller,payload):
    from jsonschema import Draft202012Validator
    from laplace.pipeline import workflow_definition_records as R
    from laplace.work import project_work_navigation as N
    D=_D();R._admit(caller)
    if next(Draft202012Validator(request_contract()).iter_errors(payload),None):raise D.Refused('INVALID_HISTORY_REQUEST')
    if payload['facet']!='saved-version' and {'body_offset','body_limit'}&set(payload):raise D.Refused('INVALID_HISTORY_REQUEST')
    frame,limits=_select(root,caller,payload);row=frame['selected']['row'];ident=row['definition_id'];head=row['definition_revision']
    selected=payload.get('selected_version',head)
    if selected not in {m['row']['definition_revision'] for m in frame['prefix']}:raise D.Refused('UNAVAILABLE_VERSION')
    token=capture.encode_cut(_cut(root,caller,frame,selected,limits));facet=payload['facet']
    if 'as_of' in payload:
        try:
            previous=capture.decode_cut(payload['as_of'])
            if set(previous)!={'v','upper','query','revision'} or previous!=_cut(root,caller,frame,selected,limits):raise ValueError('changed cut')
        except (ValueError,TypeError):raise D.Refused('HISTORY_CUT_CHANGED','Read the explicit current history; no pages were mixed',restart_read=entry(caller,ident,facet='history-page',**limits))
    known=len(frame['prefix']);offset=payload.get('offset',0);limit=payload.get('limit',20)
    if offset>known:raise D.Refused('INVALID_PAGE')
    fixed=lambda target,**more:entry(caller,ident,head,selected_version=selected,facet=target,**limits,**more)
    restart=entry(caller,ident,facet='history-page',**limits)
    base={'schema_version':LINEAGE if facet!='history-page' else HISTORY,'definition_id':ident,
        'reference':D.reference(ident,head),'scope':copy.deepcopy(row['scope']),'caller_scope':caller.public(),'scope_id':D._scope_id(root,caller),
        'head_at_start':head,'selected_version':selected,'cut':token,'known':known,'unit':'definition-version',
        'order':'newest-first' if facet=='history-page' else 'oldest-first','ordinal_base':1,
        'body_verification':'NOT_INSPECTED','restart_read':restart,'current_head_read':entry(caller,ident,facet='history-page',**limits),
        'limits':limits,'qualification':'End-at-cut does not mean all pages were loaded or bodies inspected. Current head is a separate explicit read.',
        'capture':{'log_bytes':frame['index'].offset,'metadata_rows':frame['index'].order,
            'prefix_versions':known,'history_detached_versions':0,'body_reads':0,
            'qualification':'Cold capture/chain/prefix metadata may remain linear; selected rows are rehashed. Anchor heuristics do not prove every unselected middle byte.'}}
    if facet=='saved-version':
        selected_meta=next(m for m in frame['prefix'] if m['row']['definition_revision']==selected)
        actual,_=R.raw(frame,selected_meta);body,body_raw=R.body(frame,actual,with_raw=True)
        D.validate(body)
        if D.W.digest(D.W.canonical(D._revision_payload(actual,body)))!=selected:raise D.Refused('INVALID_EXPORT_CHAIN')
        from laplace.work import object_facets as F
        object_payload={'facet':'object','reference':D.reference(ident,selected)}
        if caller.kind=='project':object_payload['project_lens']=caller.namespace
        result={**base,'schema_version':D.SCHEMA,'reference':D.reference(ident,selected),'version':selected,
            'definition':body,'scope':copy.deepcopy(actual['scope']),'read_only':True,
            'ordinal':frame['prefix'].index(selected_meta)+1,'body_verification':'VERIFIED',
            'currentness':'CURRENT' if selected==frame['head']['definition_revision'] else 'HISTORICAL',
            'observed_head_revision':frame['head']['definition_revision'],
            'currentness_qualification':'Separate metadata observation at this read; the fixed prefix/body cut is unchanged.',
            'object_read':F.handle(object_payload),'settings_observation':'NOT_REQUESTED; policy is not frozen executable binding',
            'history_read':fixed('history-page',as_of=token)}
        if N.emitted(result)>N.line() or 'body_offset' in payload:
            try:text=body_raw.decode('utf-8')
            except UnicodeError as exc:raise D.Refused('UNAVAILABLE_VERSION','This exact saved body has no supported UTF-8 text reading') from exc
            offset=payload.get('body_offset',0);size=payload.get('body_limit',4000)
            if offset>len(text):raise D.Refused('INVALID_BODY_PAGE')
            result={k:v for k,v in result.items() if k!='definition'}
            while True:
                end=min(len(text),offset+size)
                page={**result,'state':'BODY_PAGE','definition':None,'content':text[offset:end],
                    'body_page':{'offset':offset,'returned':end-offset,'total_chars':len(text),'sha256':actual['body_handle'],
                        'unit':'Unicode-code-point','at_end':end==len(text)},
                    'next_body_read':fixed('saved-version',as_of=token,body_offset=end,body_limit=payload.get('body_limit',4000)) if end<len(text) else None,
                    'display_coverage':'PARTIAL_UNTIL_ALL_EXPLICIT_BODY_PAGES_ARE_ASSEMBLED'}
                if N.emitted(page)<=N.line():result=page;break
                if size<=1:raise D.Refused('HISTORY_DELIVERY_BOUND')
                size=max(1,size//2)
        R.finish(frame);return _fit(result)
    if facet=='lineage':
        fields=[{'name':'destination','label':'Fresh local recipient directory','type':'text','required':True},
            *[{'name':k,'label':label,'type':'number','required':True} for k,label in [('max_files','Maximum output files'),('max_rows','Maximum selected rows'),('max_bytes','Maximum output bytes')]]]
        from laplace.projects import project_handover as H
        action={'action':'request','definition_transport':'lineage-v2','definitions':[D.reference(ident,head)],
            'request_id':'lineage-'+__import__('uuid').uuid4().hex}
        if row['scope']['kind']=='project':action['project']=row['scope']['namespace']
        base['handover_action']={**H.object_handle(action.get('project'),action),'title':'Prepare complete lineage export',
            'fields':fields,'permitted':caller.kind=='owned-workspace' and caller.door!='native',
            'reason':'Human/local SDK explicit destination and budgets; native stays read-only. No execution/settings grants are transferred.'}
        base.update(known_versions=known,first_page=fixed('lineage-page',as_of=token,offset=0,limit=limit),
            v1_export_read=D.scoped_handle(caller,ident,head,facet='export'))
        R.finish(frame);return _fit(base)
    indices=range(known-1-offset,max(-1,known-1-offset-limit),-1) if facet=='history-page' else range(offset,min(known,offset+limit))
    items=[];covered=0
    def envelope(current,advance):
        end=offset+advance
        return {**base,'offset':offset,'limit':limit,'returned':len(current),'covered':advance,'at_end':end==known,'items':current,
            'next_read':fixed(facet,as_of=token,offset=end,limit=limit) if end<known else None,
            'previous_read':fixed(facet,as_of=token,offset=max(0,offset-limit),limit=limit) if offset else None}
    for index in indices:
        meta=frame['prefix'][index];actual,_=R.raw(frame,meta)
        item={'ordinal':index+1,'version':actual['definition_revision'],
            'read':entry(caller,ident,head,facet='saved-version',selected_version=actual['definition_revision'],
                as_of=capture.encode_cut(_cut(root,caller,frame,actual['definition_revision'],limits)),**limits),
            **({'recorded_at':actual['ts']} if 'ts' in actual else {}),
            **({'claimed_at':actual['ts_claimed'],'claimed_at_qualification':'Original claimed custody; not the local recording time or ordering authority.'} if 'ts_claimed' in actual else {})}
        if facet=='lineage-page':item.update(row=copy.deepcopy(actual),raw_line_sha256=meta['hash'],physical_order=meta['order'])
        if N.emitted(envelope(items+[item],covered+1))>N.line():
            if items:break
            item={'ordinal':index+1,'version':actual['definition_revision'],'state':'OVERSIZED','read':item['read']}
            if N.emitted(envelope([item],1))>N.line():raise D.Refused('HISTORY_DELIVERY_BOUND')
        items.append(item);covered+=1
    R.finish(frame)
    return _fit(envelope(items,covered))


def _fit(value):
    from laplace.work import project_work_navigation as N
    if N.emitted(value)>N.line():raise _D().Refused('HISTORY_DELIVERY_BOUND')
    return value
