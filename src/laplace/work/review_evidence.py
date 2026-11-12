"""Bounded selected-Work review delivery; truth remains project_work_review.

No stored query, caller snapshot or authority carrier. Each continuation observes
fresh selected facts and refuses mixing. Support means metadata/inspection routes,
never automatic reading of the original evidence bodies.
"""
from __future__ import annotations
import copy
import json
from collections import Counter
from pathlib import Path

SCHEMA='laplace.work-review-evidence/1'
SELECTORS=('all','required','remaining-required')


def contract():
    return {'type':'object','properties':{
        'demand':{'enum':['aggregate','enumerate','support']},'selector':{'enum':list(SELECTORS)},
        'observation':{'type':'string','pattern':'^sha256:[0-9a-f]{64}$'},
        'offset':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':24},
        'enumeration':{'type':'string','pattern':'^sha256:[0-9a-f]{64}$'},
        'ids':{'type':'array','minItems':1,'maxItems':24,'uniqueItems':True,'items':{'type':'string','minLength':1,'maxLength':48}}},'additionalProperties':False,
        'oneOf':[{'properties':{'demand':{'const':'aggregate'}},'not':{'anyOf':[{'required':[key]} for key in ('observation','offset','limit','enumeration','ids')]}},
            {'properties':{'demand':{'const':'enumerate'}},'required':['demand','observation'],'not':{'anyOf':[{'required':['enumeration']},{'required':['ids']}]}},
            {'properties':{'demand':{'const':'support'}},'required':['demand','observation','enumeration','ids']}]}


def _size(value):
    from laplace.work import project_work_navigation as N
    return N.emitted(value)
def _cap():
    from laplace.work import project_work_navigation as N
    return N.line()
def handle(project,ident,request=None):
    from laplace.work.project_work_views import handle as owner_handle
    return owner_handle(project,{'view':'review-evidence','id':ident,'request':dict(request or {'demand':'aggregate','selector':'all'})})
def _fit(value):
    if _size(value)>_cap():raise ValueError('Review evidence envelope exceeds its bounded delivery; use the existing full Work review read.')
    return value


def _capture(root,project,ident,context):
    from laplace.work import project_work as W,project_work_review as R,project_work_navigation as N
    snapshot=W.read_snapshot(project,root,read_context=context,resolve=False);raw=snapshot['raw'];task=raw.get(ident)
    if task is None:raise ValueError('Exact Work is unavailable in the admitted namespace.')
    context[('review-evidence-observe',str(root))]=True
    digests=context.setdefault(('work-evidence',str(root)),{})
    closures={item['closure_work_id'] for item in task.get('review_obligations') or () if item.get('closure_work_id')}
    relevant=set();pending=list(closures)
    while pending:
        key=pending.pop()
        if key in relevant:continue
        relevant.add(key);row=raw.get(key,{})
        pending.extend(row.get('depends_on') or ())
    resolved={}
    if closures:
        # The existing completion/prerequisite owner resolves only consumed
        # completions; no rich review facades are constructed for any Work.
        resolved={row['id']:row for row in W._resolved_tasks(raw,root,read_context=context,digests=digests,
            completion_ids=relevant,review_facets=False)}
    tasks={**raw,**{key:resolved[key] for key in relevant if key in resolved}}
    observed=R.facts(task,root,tasks=tasks,digests=digests,project=project,read_context=context)
    phases=task.get('phases') or ()
    facts=[] if observed is None else observed['obligations']
    # The owner fold keeps attached phase rows by identity. No phase body is
    # copied or hydrated merely to count it; exact phase revisions are issued
    # only when a requested inspection route needs that rowset.
    basis={'namespace':project,'work':ident,'specification':W._task_revision(task),
        'intent':R.intent_digest(task,tasks),'phase_records':[(row.get('id'),row.get('state'),row.get('ts')) for row in phases],
        'obligations':[{'definition':item['definition'],'standing':item['standing'],
            'review_inputs':{key:item['latest'].get(key) for key in ('id','pins','source_basis','source_contract','intent_digest','obligation_digest')}
                if item['latest'] is not None else None} for item in facts],
        'closures':{key:{'present':key in raw,'record':N.records_revision({key:raw[key]}) if key in raw else None,
            'status':resolved.get(key,{}).get('status'),'currentness':resolved.get(key,{}).get('currentness')} for key in sorted(relevant)},
        'consumed_inputs':context.get(('review-evidence-inputs',str(root)),{}),
        'evidence_bytes':{str(key):value for key,value in digests.items() if isinstance(key,Path)}}
    return task,observed,basis,context


def _token(basis,selector):
    from laplace.work.project_work_review import _digest
    return _digest({'interpretation':SCHEMA,'unit':'review-obligation','selector':selector,'facts':basis})
def _selected(observed,selector):
    rows=[] if observed is None else observed['obligations']
    return [row for row in rows if selector=='all' or row['standing'].get('required') and
        (selector=='required' or not row['standing']['satisfied'])]
def _counts(observed):
    if observed is None:return None
    rows=[item['standing'] for item in observed['obligations']];required=[row for row in rows if row.get('required')]
    return {'unit':'review-obligation','total':len(rows),'required':len(required),
        'satisfied_required':sum(bool(row['satisfied']) for row in required),
        'remaining_required':sum(not row['satisfied'] for row in required),
        'by_currentness':dict(Counter(row['currentness'] for row in rows)),
        'by_status':dict(Counter(row['status'] for row in rows)),
        'by_independence':dict(Counter(row.get('independence','NOT_RECORDED') for row in rows)),
        'source_bound_obligations':sum(bool(item['definition'].get('source_contract')) for item in observed['obligations']),
        'obligations_with_known_missing_source_segments':sum(bool((row.get('coverage') or {}).get('missing')) for row in rows)}


def _metrics(root,context):
    facts=context.get(('read-metrics',str(root)),{});digests=context.get(('work-evidence',str(root)),{});io=digests.get(('evidence-io',),{})
    return {'task_snapshots':facts.get('task_snapshots',0),'review_decisions':facts.get('review_decisions',0),
        'phase_revision_computations':facts.get('phase_revision_computations',0),
        'support_items_constructed':context.get('support_items_constructed',0),
        'evidence_visits':io.get('visits',0),'evidence_bytes_hashed':io.get('bytes',0),'evidence_bytes_from_stat_cache':io.get('cached_bytes',0),
        'qualification':'Shared Work evidence cache only; qualified Source/other owner observation may add I/O. Ledger discovery/fold can remain linear.'}


def _base(project,ident,task,observed,basis,selector,scope):
    from laplace.work.project_work_views import handle as owner_handle
    phases=task.get('phases') or ();followups={} if observed is None else observed['followups']
    pending=sum(not (row.get('joined') and row.get('state','COMPLETE')=='COMPLETE') for row in followups.values())
    title=task.get('title','');goal=task.get('goal','')
    return {'schema_version':SCHEMA,'read_only':True,'work':{'namespace':project,'id':ident,'title':title[:200],
        'title_complete':len(title)<=200,'purpose':goal[:320],'purpose_complete':len(goal)<=320,
        'detail_read':owner_handle(project,{'view':'detail','id':ident})},
        'managed':observed is not None,'outcome':'Review obligations observed' if observed is not None else 'Reviews are not configured for this Work',
        'counts':_counts(observed),'phases':{'unit':'phase-record','recorded':len(phases)},
        'pending_joins':{'unit':'follow-up','count':pending},'caller_scope':scope.public(),
        'observation':{'token':_token(basis,selector),'selector':selector,'unit':'review-obligation',
            'qualification':'Selected owner facts and actually consumed inputs; files observed, not an atomic filesystem snapshot.'},
        'enumerate_reads':{name:handle(project,ident,{'demand':'enumerate','selector':name,'observation':_token(basis,name),'offset':0,'limit':6}) for name in SELECTORS},
        'read':handle(project,ident,{'demand':'aggregate','selector':selector}),
        'restart_read':handle(project,ident,{'demand':'aggregate','selector':selector}),
        'inspection':{'metadata':'NOT_EXPANDED','bodies':'NOT_READ'},
        'qualification':'Counts use the existing local satisfaction decision. Actual independence and Source coverage remain separate. Zero required obligations is not a percentage.'}


def _page(project,ident,observed,basis,selector,offset,limit,base):
    from laplace.work.project_work_review import _digest
    from laplace.work.project_work_views import handle as owner_handle
    selected=_selected(observed,selector);items=[];covered=0;oversized=[]
    token=_token(basis,selector);placeholder='sha256:'+'0'*64
    def row(item):
        state=item['standing'];reason=state.get('currentness_reason','')
        return {'id':state['id'],'label':state['label'],'scope':state['scope'],'required':state.get('required',True),
            'independent_required':state.get('independent',True),'standing':{key:copy.deepcopy(state[key]) for key in
            ('status','currentness','independence','satisfied','coverage','closure_work_id') if key in state},
            'reason':reason[:240],'reason_complete':len(reason)<=240,
            'support_read':handle(project,ident,{'demand':'support','selector':selector,'observation':token,
                'offset':offset,'limit':limit,'enumeration':placeholder,'ids':[state['id']]})}
    def finish():
        ids=[item['id'] for item in items]
        next_offset=offset+covered if offset+covered<len(selected) else None
        return {**base,'enumeration':{'selector':selector,'known':len(selected),'returned':len(items),'covered':covered,
            'offset':offset,'limit':limit,'basis':placeholder,'complete':offset==0 and covered==len(selected),'oversized':oversized,
            'next_read':handle(project,ident,{'demand':'enumerate','selector':selector,'observation':token,'offset':next_offset,'limit':limit}) if next_offset is not None else None},'items':items,
            'support_read':handle(project,ident,{'demand':'support','selector':selector,'observation':token,
                'offset':offset,'limit':limit,'enumeration':placeholder,'ids':ids}) if ids else None}
    for item in selected[offset:offset+limit]:
        candidate=row(item);items.append(candidate);covered+=1
        if _size(finish())>_cap():
            items.pop();covered-=1
            if covered:break
            state=item['standing'];notice={'id':state['id'],'label':state['label'][:80],'metadata_state':'OVERSIZED',
                'inspection_read':owner_handle(project,{'view':'review','id':ident,'obligation_id':state['id']})}
            items.append(notice);covered=1;oversized.append(state['id']);_fit(finish());break
    result=finish();ids=[item['id'] for item in items]
    page_basis=_digest({'observation':token,'selector':selector,'offset':offset,'limit':limit,'ids':ids})
    result['enumeration']['basis']=page_basis
    if ids:result['support_read']=handle(project,ident,{'demand':'support','selector':selector,'observation':token,
        'offset':offset,'limit':limit,'enumeration':page_basis,'ids':ids})
    for item in items:
        if 'support_read' in item:
            item['support_read']=handle(project,ident,{'demand':'support','selector':selector,'observation':token,
                'offset':offset,'limit':limit,'enumeration':page_basis,'ids':[item['id']]})
    return _fit(result)


def _share_routes(support):
    """Intern exact inspection descriptors within this response, only if smaller."""
    from laplace.work.project_work_review import _digest
    table=[];indices={};items=[]
    for item in support['items']:
        refs=[]
        for route in item['inspection_routes']:
            key=json.dumps(route,sort_keys=True,separators=(',',':'),ensure_ascii=False)
            if key not in indices:
                indices[key]=len(table);table.append({'id':len(table),'sha256':_digest(route),'route':route})
            refs.append(indices[key])
        items.append({**{key:value for key,value in item.items() if key!='inspection_routes'},'inspection_refs':refs})
    candidate={**support,'encoding':'descriptor-table','items':items,'descriptors':table}
    return candidate if _size(candidate)<_size(support) else support


def _support(project,ident,task,observed,ids,context):
    from laplace.work import project_work_review as R
    from laplace.work.project_work_views import handle as owner_handle
    by={row['standing']['id']:row for row in observed['obligations']};items=[]
    for ident_ in ids:
        fact=by[ident_];declared=fact['definition'];review=fact['latest']
        handoff=next((row for row in reversed(observed['handoffs']) if row['id']==review.get('handoff_id')),None) if review is not None else next((row for row in reversed(observed['handoffs']) if ident_ in row.get('obligations',())),None)
        context['support_items_constructed']=context.get('support_items_constructed',0)+1
        routes=[{'kind':'obligation','title':'Read declared inputs and recorded history',
            'read':owner_handle(project,{'view':'review','id':ident,'obligation_id':ident_})}]
        for kind,phase in (('review',fact['latest']),('handoff',handoff)):
            if phase is not None:routes.append({'kind':kind,'title':'Read recorded '+kind,
                'read':R.phase_read(task,Path(context['root']),phase['id'],project=project,read_context=context)})
        items.append({'id':ident_,'label':declared['label'],'scope':declared['scope'],
            'metadata_state':'EXPANDED','expanded_fields':['declared_inputs','standing','inspection_routes'],
            'declared_inputs':copy.deepcopy(declared.get('inputs') or []),'standing':copy.deepcopy(fact['standing']),
            **({'source_contract':copy.deepcopy(declared['source_contract'])} if declared.get('source_contract') else {}),
            'inspection_routes':routes,'body_inspection':'NOT_READ',
            'qualification':'Metadata and container/phase inspection routes; original evidence bodies have not been read.'})
    return {'encoding':'inline','items':items}


def read(root,scope,project,ident,request):
    from jsonschema import Draft202012Validator
    from laplace.work import owner_discovery as O,project_work as W
    if not isinstance(scope,O.Scope) or not scope.admits(project):raise ValueError('Review evidence is outside the actual caller scope.')
    error=next(Draft202012Validator(contract()).iter_errors(request),None)
    if error:raise ValueError('Review evidence demand does not match its closed owner contract.')
    demand=request.get('demand','aggregate');selector=request.get('selector','all')
    allowed={'demand','selector'} if demand=='aggregate' else {'demand','selector','observation','offset','limit'} | ({'enumeration','ids'} if demand=='support' else set())
    if set(request)-allowed or demand!='aggregate' and not request.get('observation') or demand=='support' and not all(request.get(k) for k in ('enumeration','ids')):
        raise ValueError('Review evidence demand is incomplete or carries fields for another demand.')
    root=Path(root).resolve();context={'root':str(root)};task,observed,basis,context=_capture(root,project,ident,context)
    base=_base(project,ident,task,observed,basis,selector,scope);base['read_metrics']=_metrics(root,context);token=base['observation']['token']
    if demand!='aggregate' and request['observation']!=token:
        conflict=W.WorkConflict('Review evidence inputs changed; held pages were not mixed.',project,ident,expected=request['observation'],observed=token)
        conflict.details.update(kind='CHANGED_INPUT',restart_read=base['restart_read'],next_reads=[base['restart_read']]);raise conflict
    if demand=='aggregate':return _fit(base)
    offset=request.get('offset',0);limit=request.get('limit',6)
    if demand=='enumerate':return _page(project,ident,observed,basis,selector,offset,limit,base)
    # A delivery line can change between doors/calls. The issued enumeration
    # digest binds its original ordered prefix, not today's descriptor packing.
    # Reconstruct at most the closed page limit of identities, without building
    # another page or hydrating any unrequested support.
    from laplace.work.project_work_review import _digest
    candidates=[row['standing']['id'] for row in _selected(observed,selector)[offset:offset+limit]]
    page_ids=None
    for count in range(1,len(candidates)+1):
        prefix=candidates[:count]
        if _digest({'observation':token,'selector':selector,'offset':offset,'limit':limit,'ids':prefix})==request['enumeration']:
            page_ids=set(prefix);break
    ids=request['ids']
    if page_ids is None or not set(ids)<=page_ids:raise ValueError('Selected support does not belong to this exact enumerated page.')
    support=_support(project,ident,task,observed,ids,context)
    binding={'namespace':project,'work_id':ident,'observation':token,'selector':selector,'enumeration':request['enumeration'],'ids':list(ids)}
    support['binding']=binding
    result={**base,'support':_share_routes(support)}
    if _size(result)>_cap():
        from laplace.work.project_work_views import handle as owner_handle
        result['support']={'encoding':'inline','binding':binding,'items':[{'id':key,'label':next(row['definition']['label'] for row in observed['obligations'] if row['standing']['id']==key)[:80],
            'metadata_state':'OVERSIZED','body_inspection':'NOT_READ','inspection_routes':[{'kind':'obligation','title':'Read full declared inputs and recorded history',
            'read':owner_handle(project,{'view':'review','id':ident,'obligation_id':key})}]} for key in ids]}
    result['inspection']={'metadata':'EXPANDED_OR_EXPLICIT_OVERSIZED','bodies':'NOT_READ'}
    result['read_metrics']=_metrics(root,context)
    return _fit(result)
