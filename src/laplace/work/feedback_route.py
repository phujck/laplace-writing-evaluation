"""One comment's finite review route, inside the existing Work delivery owner.

Only metadata is appended to the Work phase ledger. Origin text stays with
pipeline.authoring; WD owns each actual request/session/recovery and return.
Lock order: source save completes first, then Work dispatch lock for route and
allowance, released before WD event locks/turn transport. Admission revalidates
canonical WD/route context under the turn owner's existing Work lock.
An explicit author request-settle shares the same dispatch lock, appends one typed
settlement row through the ledger writer's final admit guard, and fences late copies
of that exact original request before CAS, inline policy, reservation or transport.
"""
from __future__ import annotations

import copy
import datetime as dt
import math
from pathlib import Path
from urllib.parse import urlencode
import json

POLICY = 'work-delivery-policy'
ROUTE = 'work-delivery-route'
SCHEMA = 'laplace.feedback-route/1'
ACTIONS = ('policy-save','route-preview','route-submit','route-status','route-recover','route-cancel','request-settle')
SETTLEMENT = 'work-delivery-request-settlement'
ASSOCIATION = 'laplace.feedback-request-association/1'
COMPARISON = 'laplace.feedback-request-comparison/1'
SETTLED_CODE = 'AUTHOR_SETTLED_UNADMITTED_REQUEST'
REQUEST_KINDS = ('route','policy')
LIMIT_FIELDS = ('max_new_admissions','max_attempts','admission_seconds','runtime_seconds')


def _owners():
    from laplace.work import project_work, work_delivery
    return project_work, work_delivery


def _closed(value, allowed, required=()):
    if not isinstance(value,dict) or set(value)-set(allowed) or set(required)-set(value):
        raise ValueError('Feedback route does not match its closed owner contract.')


def _request(value):
    from laplace.work.project_work_review import _REQUEST
    if not isinstance(value,str) or not _REQUEST.fullmatch(value):
        raise ValueError('Retain a request_id of8..96 letters, digits or ._:-.')
    return value


def _rows(task,kind):return [row for row in task.get('deliveries') or () if row.get('kind')==kind]


def _latest(task,kind,ident):return next((row for row in reversed(_rows(task,kind)) if row['id']==ident),None)


def _append(root,row):
    work,delivery=_owners()
    return work._append(root,{**row,'record':'project-work-phase','ts':delivery._now()})


def _task(root,project,ident,*,read_context=None):return _owners()[1]._task_for(root,project,ident,read_context=read_context)


def _origin(root,project,ref,*,current=False,read_context=None):
    from laplace.pipeline import authoring
    if current and read_context is not None:raise ValueError('New-effect origin validation cannot reuse a pure read frame.')
    key=('feedback_route.origin',str(Path(root).resolve()),project,_owners()[1]._digest(ref))
    if read_context is not None and key in read_context:return read_context[key]
    value=authoring.correction_origin(project,ref,repo_root=root)
    if value['origin_ref']['project']!=project:raise ValueError('Origin belongs to another project.')
    if current and value['currentness']['state']!='CURRENT':
        raise ValueError('CHANGED_INPUT: inspect the original comment/source before new review effects.')
    if read_context is not None:read_context[key]=value
    return value


def _relevant(task,origin):
    # Optional UI section/block labels are not source-owner authority. Use the
    # canonical source object and declared Work inputs/targets, without suffix
    # matching or trusting a caller's informational section name.
    basis=origin['source_basis'];actual={basis['file'],basis['source_ref']}
    declared=set(task.get('section_ids') or [])
    for home in (task.get('anchor') or {},task.get('logical_target') or {}):
        declared.update(str(home[k]) for k in ('file','source_ref') if home.get(k))
    for obligation in task.get('review_obligations') or []:declared.update(obligation.get('inputs') or [])
    return bool(actual & declared)


def _recipients(task,value):
    from laplace.work import work_delivery
    if not isinstance(value,list) or not value:raise ValueError('Select a finite nonempty set of review recipients.')
    known={row['id']:row for row in task.get('review_obligations') or []};seen=set();out=[]
    for row in value:
        _closed(row,('obligation_id','recipient_binding_id'),('obligation_id','recipient_binding_id'))
        ident=row['obligation_id'];binding_id=row['recipient_binding_id']
        if ident not in known or ident in seen:raise ValueError('Select distinct existing obligations of this Work.')
        problem=work_delivery._binding_problem(task,binding_id)
        if problem:raise ValueError('Review recipient unavailable: '+problem)
        binding=work_delivery._latest(task,work_delivery.BINDING,binding_id)
        effect=binding.get('effect')
        if (binding.get('recipient_kind')!='app-owned' or
                binding.get('role')!='review' and effect not in {'proposal-writer','research-producer'}):
            raise ValueError('This route requires exact approved review, proposal-writer or registered-producer bindings.')
        if effect and binding.get('approved_by')!='human':raise ValueError('Effect-specific recipients require explicit human approval.')
        seen.add(ident);out.append(copy.deepcopy(row))
    return out


def _policy_value(task,value):
    _closed(value,('mode','recipients','limits','parent_return'),('mode','recipients','limits'))
    if value['mode'] not in ('manual','automatic'):raise ValueError('Policy mode is manual or automatic.')
    limits=value['limits']
    if not isinstance(limits,dict) or set(limits)-set(LIMIT_FIELDS):
        raise ValueError('UNSUPPORTED_LIMIT: this route admits finite admissions, attempts, admission expiry and runtime only; no requested ceiling is dropped.')
    _closed(limits,LIMIT_FIELDS,LIMIT_FIELDS)
    from laplace.work import work_delivery
    for key in ('max_new_admissions','max_attempts','admission_seconds'):
        if type(limits[key]) is not int or limits[key]<=0:raise ValueError('Choose positive integer '+key+'.')
    if limits['max_attempts']>work_delivery.MAX_ATTEMPTS or not 60<=limits['admission_seconds']<=work_delivery.MAX_DEADLINE_S:
        raise ValueError('Transport attempt/expiry exceeds the existing delivery contract.')
    runtime=limits['runtime_seconds']
    try:
        if type(runtime) not in (int,float) or not math.isfinite(runtime) or runtime<=0:raise ValueError('Choose a positive finite running-review timeout.')
        dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=runtime)
    except OverflowError:raise ValueError('Running timeout cannot be represented by this execution owner.') from None
    recipients=_recipients(task,value['recipients'])
    for selected in recipients:
        binding=work_delivery._latest(task,work_delivery.BINDING,selected['recipient_binding_id'])
        if binding.get('effect') in {'proposal-writer','research-producer'}:
            maximum=binding.get('producer_timeout_seconds',3600)
            if type(runtime) is not int or not 1<=runtime<=maximum:
                raise ValueError('UNSUPPORTED_LIMIT: this effect requires an exact integer running ceiling within its approved owner limit.')
    parent=value.get('parent_return')
    if parent is not None:
        _closed(parent,('admit_idle','max_attempts','max_depth'),('admit_idle','max_attempts','max_depth'))
        if (type(parent['admit_idle']) is not bool or type(parent['max_attempts']) is not int or
                not 1<=parent['max_attempts']<=work_delivery.MAX_RETURN_ATTEMPTS or type(parent['max_depth']) is not int or
                not 1<=parent['max_depth']<=work_delivery.MAX_RETURN_DEPTH):raise ValueError('Invalid bounded original-parent continuation policy.')
    return {'mode':value['mode'],'recipients':recipients,'limits':copy.deepcopy(limits),
            **({'parent_return':copy.deepcopy(parent)} if parent is not None else {})}


def policy_schema():
    from laplace.work import work_delivery
    return {'type':'object','additionalProperties':False,'required':['mode','recipients','limits'],
        'properties':{'mode':{'enum':['manual','automatic']},'parent_return':{
            'type':'object','additionalProperties':False,'required':['admit_idle','max_attempts','max_depth'],
            'properties':{'admit_idle':{'type':'boolean'},'max_attempts':{'type':'integer','minimum':1,'maximum':work_delivery.MAX_RETURN_ATTEMPTS},
                          'max_depth':{'type':'integer','minimum':1,'maximum':work_delivery.MAX_RETURN_DEPTH}}},
        'recipients':{'type':'array','minItems':1,'items':{
            'type':'object','additionalProperties':False,'required':['obligation_id','recipient_binding_id'],
            'properties':{'obligation_id':{'type':'string'},'recipient_binding_id':{'type':'string'}}}},
        'limits':{'type':'object','additionalProperties':False,'required':list(LIMIT_FIELDS),'properties':{
            'max_new_admissions':{'type':'integer','minimum':1},'max_attempts':{'type':'integer','minimum':1,'maximum':work_delivery.MAX_ATTEMPTS},
            'admission_seconds':{'type':'integer','minimum':60,'maximum':work_delivery.MAX_DEADLINE_S},'runtime_seconds':{'type':'number','exclusiveMinimum':0}}}}}


def handle_read(project,payload):
    return {'operation':'work_delivery','payload':copy.deepcopy(payload),'http':{'method':'GET','url':'/work/delivery?'+urlencode({
        'project':project,'request':json.dumps(payload,sort_keys=True,separators=(',',':'))})}}


def origin_route_read(project,origin_ref,route_spec):
    if not isinstance(route_spec,dict) or not isinstance(route_spec.get('work_id'),str) or not route_spec['work_id']:
        raise ValueError('An origin route read requires its retained qualified Work.')
    return handle_read(project,{'action':'route-status','work_id':route_spec['work_id'],'origin':copy.deepcopy(origin_ref)})


def _action(project,payload,*,permitted=True,reason=''):
    return {'permitted':permitted,'reason':reason,'operation':'work_delivery','http':{'method':'POST','url':'/work/delivery'},
            'payload':{'project':project,**copy.deepcopy(payload)}}


def _policy(root,project,task,payload,door,*,create_inline=False):
    work,delivery=_owners();value=payload.get('policy')
    if value is not None:
        if payload.get('policy_id'):raise ValueError('Select one canonical policy or one explicit manual policy, not both.')
        checked=_policy_value(task,value)
        if not create_inline:return {**checked,'id':None,'revision':delivery._digest(checked),'prospective':True}
        if checked['mode']!='manual':raise ValueError('Automatic execution requires a previously author-saved policy.')
        saved=policy_save(root,project,{'work_id':task['id'],'expected_work_revision':work._task_revision(task),
            'request_id':'manual:'+delivery._digest(_request(payload['request_id']))[7:39],'policy':checked},door)
        if saved.get('terminal'):raise ValueError('This inline manual policy request was settled by the author; nothing new was admitted.')
        return saved['policy']
    ident=payload.get('policy_id');row=_latest(task,POLICY,ident) if ident else None
    if row is None:raise ValueError('Select or explicitly save a finite author policy; unconfigured is manual Save-only.')
    if payload.get('expected_policy_revision') and payload['expected_policy_revision']!=row['revision']:
        raise ValueError('CHANGED_INPUT: selected policy changed; inspect before new effects.')
    return copy.deepcopy(row)


def policy_save(root,project,payload,door):
    work,delivery=_owners()
    if delivery._acting(root,project,door)['kind']!='human':raise ValueError('Only the author may save or enlarge review routing policy.')
    request=_request(payload['request_id'])
    with work.dispatch_lock(root):
        _tasks,task=_task(root,project,payload['work_id'])
        ident=payload.get('policy_id') or 'FP-'+delivery._digest([project,task['id'],request])[7:31]
        prior=next((r for r in _rows(task,POLICY) if r.get('request_id')==request),None)
        if prior:
            if prior['revision']!=delivery._digest(payload['policy']) or prior['id']!=ident:raise ValueError('Policy request_id already has another intent.')
            return {'effect':'policy_saved','policy':copy.deepcopy(prior),'replayed':True,'read':handle_read(project,{'action':'route-status','work_id':task['id'],'policy_id':ident})}
        # An exact author settlement of this original request fences it before CAS, policy or any effect.
        fenced=_fence(project,task,'policy',request,delivery._digest(payload['policy']))
        if fenced:return fenced
        value=_policy_value(task,payload['policy']);old=_latest(task,POLICY,ident);revision=delivery._digest(value)
        if payload['expected_work_revision']!=work._task_revision(task):raise ValueError('CHANGED_INPUT: Work specification changed.')
        if old and payload.get('expected_policy_revision')!=old['revision']:raise ValueError('CHANGED_INPUT: policy revision changed.')
        row={'kind':POLICY,'id':ident,'project':project,'work_id':task['id'],'request_id':request,'revision':revision,
             **value,'approved_by':'author','actor':delivery._actor(root,project,payload,door)}
        _append(root,row)
        row=copy.deepcopy(_latest(_task(root,project,task['id'])[1],POLICY,ident))
    return {'effect':'policy_saved','policy':row,'replayed':False,'read':handle_read(project,{'action':'route-status','work_id':task['id'],'policy_id':ident})}


def preview(root,project,payload,door):
    work,delivery=_owners();_tasks,task=_task(root,project,payload['work_id'])
    origin=_origin(root,project,payload['origin']) if payload.get('origin') else None
    issue=None;policy=None;recipients=[]
    try:
        policy=_policy(root,project,task,payload,door)
        if policy.get('prospective') and policy['mode']=='automatic':raise ValueError('Save the automatic author policy explicitly before using it.')
        selected=payload['recipients'] if 'recipients' in payload else policy['recipients'];recipients=_recipients(task,selected)
        if any(row not in policy['recipients'] for row in recipients):raise ValueError('Recipient is outside the selected policy family.')
        if origin and (origin['currentness']['state']!='CURRENT' or not _relevant(task,origin)):
            raise ValueError('The selected Work has no current declared relation to this passage.')
        if task.get('status') in {'cancelled','withdrawn'}:raise ValueError('This Work is '+task['status']+'.')
    except ValueError as error:issue=str(error)
    latest=delivery.latest_bindings(task)
    selected_ids={row['recipient_binding_id'] for row in recipients}
    window=list(latest.values())[-16:]
    shown={row['id']:row for row in window}
    shown.update({key:row for key,row in latest.items() if key in selected_ids})
    bindings=[delivery._public_binding(row) for row in shown.values() if row.get('state')=='APPROVED']
    base={'action':'route-submit','work_id':task['id'],'expected_work_revision':work._task_revision(task),
          **{key:copy.deepcopy(payload[key]) for key in ('policy','policy_id','expected_policy_revision','recipients') if key in payload}}
    if policy and policy.get('id'):base.update(policy_id=policy['id'],expected_policy_revision=policy['revision'])
    if origin:base['origin']=origin['origin_ref']
    if payload.get('request_id'):base['request_id']=_request(payload['request_id'])
    enriched=[]
    for selected in recipients:
        obligation=next(r for r in task['review_obligations'] if r['id']==selected['obligation_id'])
        binding=delivery._latest(task,delivery.BINDING,selected['recipient_binding_id'])
        enriched.append({**selected,'selected':True,
            'obligation':{k:copy.deepcopy(obligation.get(k)) for k in ('id','label','scope','inputs')},
            'recipient':delivery._public_binding(binding),
            'relevance':{'state':'CURRENT' if origin and _relevant(task,origin) else 'PENDING_ORIGIN',
                         'reason':'Declared Work/passage relation' if origin and _relevant(task,origin) else 'Verified against the actual committed comment before delivery.'}})
    policies={r['id']:r for r in _rows(task,POLICY)}
    return {'schema_version':SCHEMA,'project':project,'effect':'preview','work':{'id':task['id'],'title':task.get('title'),'revision':work._task_revision(task),
            'declared_targets':{'section_ids':list(task.get('section_ids') or []),'anchor':{k:v for k,v in (task.get('anchor') or {}).items() if k in ('file','section','section_id','node_id')}}},
        'origin':origin,**({'origin_route_read':origin_route_read(project,origin['origin_ref'],base)} if origin else {}),
        'policy':policy,'policy_schema':policy_schema(),'bindings':bindings,
        'bindings_coverage':{'total':len(latest),'shown':len(bindings),'complete':len(bindings)==len(latest),
            'read':handle_read(project,{'action':'review-setup','work_id':task['id']})},
        'obligations':[{k:copy.deepcopy(r.get(k)) for k in ('id','label','scope','inputs')} for r in task.get('review_obligations') or []],
        'selected_recipients':recipients,'recipients':enriched,'policies':[{**copy.deepcopy(r),
            'read':handle_read(project,{'action':'route-status','work_id':task['id'],'policy_id':r['id']})} for r in list(policies.values())[-16:]],
        'issues':[issue] if issue else [],'origin_required_at_admission':True,
        **({'request_read':handle_read(project,{'action':'route-status','work_id':task['id'],'request_id':payload['request_id']})} if payload.get('request_id') else {}),
        **({'policy_request_read':handle_read(project,{'action':'route-status','work_id':task['id'],'request_id':payload['request_id'],'request_kind':'policy'})} if payload.get('request_id') else {}),
        'actions':{'submit':_action(project,base,permitted=not issue and bool(origin),reason=issue or ('Save the exact comment first.' if not origin else '')),
                   'policy_save':_action(project,{'action':'policy-save','work_id':task['id'],'expected_work_revision':work._task_revision(task),
                        **({'request_id':payload['request_id']} if payload.get('request_id') else {})},
                        permitted=delivery._acting(root,project,door)['kind']=='human',reason='Only the author saves policy.'),
                   'compose':{'permitted':not issue,'reason':issue or '', 'route_spec':base}},
        'read':handle_read(project,{'action':'route-preview',**{key:copy.deepcopy(v) for key,v in payload.items() if key!='action'}})}


def _route_for(task,ident):
    row=_latest(task,ROUTE,ident)
    if row is None:raise ValueError('Unknown feedback route of this Work.')
    return copy.deepcopy(row)


def _origin_key(ref):return (ref['project'],ref['correction_id'])


def _request_intent(payload):
    return _owners()[1]._digest({k:payload[k] for k in ('work_id','expected_work_revision','origin','policy','policy_id','expected_policy_revision','recipients') if k in payload})


def _record_route(root,row):
    _append(root,row)
    return row


def _edge(root,project,task,origin,policy,selected):
    work,delivery=_owners();from laplace.work import project_work_review as review
    obligation=next(r for r in task['review_obligations'] if r['id']==selected['obligation_id'])
    binding=delivery._latest(task,delivery.BINDING,selected['recipient_binding_id'])
    basis,issue=work._work_basis(work._tasks(project,root),task['id'])
    if issue:raise ValueError(issue)
    pins={path:review._file_digest(root,path) for path in obligation.get('inputs') or []}
    review._pins(root,pins,'pins')
    edge_id='FE-'+delivery._digest([project,task['id'],origin['origin_ref']['correction_id'],selected])[7:31]
    generation=delivery._digest({'origin':origin['origin_ref']['material_revision'],'work_scope':basis['scope_revision'],
        'obligation':obligation,'binding_revision':binding['revision'],'pins':pins,
        'policy_revision':policy['revision'],'runtime_seconds':policy['limits']['runtime_seconds']})
    request='feedback:'+edge_id+':'+generation[7:31]
    handoff_id='PHASE-'+review._digest([project,task['id'],'handoff',request])[7:31]
    obj={'kind':'feedback-review','aggregate':generation}
    content_pin=delivery._digest({'pins':pins,'object':obj,'feedback_origin':origin['origin_ref'],
        'feedback_route':{'edge_id':edge_id,'generation':generation}})
    event_id='WD-'+delivery._digest({'handoff_id':handoff_id,'binding_id':binding['id'],'binding_revision':binding['revision'],
        'obligation_id':obligation['id'],'work_scope_revision':basis['scope_revision'],'content_pin':content_pin})[7:31]
    return {'edge_id':edge_id,'generation':generation,'obligation_id':obligation['id'],
        'obligation':{'id':obligation['id'],'label':obligation.get('label'),'scope':obligation.get('scope')},'binding_id':binding['id'],
        'binding_revision':binding['revision'],'pins':pins,'object':obj,'handoff_request':request,'handoff_id':handoff_id,
        'event_id':event_id,'origin':copy.deepcopy(origin['origin_ref']),'work_scope_revision':basis['scope_revision'],
        'runtime_seconds':policy['limits']['runtime_seconds'],'max_attempts':policy['limits']['max_attempts'],
        'admission_seconds':policy['limits']['admission_seconds'],
        **({'parent_return':copy.deepcopy(policy['parent_return'])} if 'parent_return' in policy else {})}


def submit(root,project,payload,door):
    work,delivery=_owners();actor=delivery._acting(root,project,door)
    if actor.get('role')=='review':raise ValueError('Reviewers cannot submit or enlarge feedback routes.')
    request=_request(payload['request_id']);intent=_request_intent(payload)
    with work.dispatch_lock(root):
        _tasks,task=_task(root,project,payload['work_id'])
        # Receipt lookup comes before changed source/policy/work checks.
        for prior in reversed(_rows(task,ROUTE)):
            if request in prior.get('requests',{}):
                if prior['requests'][request]!=intent:raise ValueError('Route request_id already recorded another exact intent.')
                return {'effect':'route_recorded','route_id':prior['id'],'replayed':True,
                        'aggregate':aggregate(root,project,task['id'],prior['id']),
                        'read':handle_read(project,{'action':'route-status','work_id':task['id'],'route_id':prior['id']})}
        # A matching recorded result won above; an exact author settlement now wins before CAS, inline policy,
        # reservation, handoff or transport. Unrelated routes of this Work/origin are not this request.
        fenced=_fence(project,task,'route',request,intent)
        if fenced:return fenced
        if payload['expected_work_revision']!=work._task_revision(task):raise ValueError('CHANGED_INPUT: Work specification changed.')
        origin=_origin(root,project,payload['origin'],current=True)
        if not _relevant(task,origin):raise ValueError('This Work has no declared relation to the selected passage.')
        policy=_policy(root,project,task,payload,door)
        if policy.get('prospective'):
            if policy['mode']!='manual' or actor['kind']!='human':raise ValueError('Only a human may explicitly compose a manual policy; automatic/native needs a saved author policy.')
        selected=_recipients(task,payload['recipients'] if 'recipients' in payload else policy['recipients'])
        if any(row not in policy['recipients'] for row in selected):raise ValueError('Recipient is outside the author policy.')
        edges=[_edge(root,project,task,origin,policy,row) for row in selected]
        ident='FR-'+delivery._digest([project,task['id'],_origin_key(origin['origin_ref'])])[7:31]
        route=_latest(task,ROUTE,ident)
        route=copy.deepcopy(route) if route else {'kind':ROUTE,'id':ident,'project':project,'work_id':task['id'],
            'state':'ACTIVE','origin':origin['origin_ref'],'requests':{},'review_edges':[],'reservations':{},
            'actor':delivery._actor(root,project,payload,door)}
        if route['state']=='CANCELLED':raise ValueError('This origin route was stopped; its effects remain inspectable.')
        if len(route['reservations'])>policy['limits']['max_new_admissions']:
            raise ValueError('The selected policy is below this route existing reservations; it cannot erase them.')
        route.update(origin=origin['origin_ref'],policy=policy)
        known={edge['event_id'] for edge in route['review_edges']}
        new=[edge for edge in edges if edge['event_id'] not in known]
        if len(route['reservations'])+len(new)>policy['limits']['max_new_admissions']:
            raise ValueError('ALLOCATION_EXHAUSTED: existing reservations plus new reviewers exceed the selected allowance.')
        if policy.get('prospective'):
            policy=_policy(root,project,task,payload,door,create_inline=True)
            route['policy']=policy
        for edge in new:
            # The admitting door is retained once per intended effect. Recovery
            # cannot redirect a native review's result to its own caller.
            edge['admission_door']=({'origin':'native','turn_id':actor['turn_id']} if actor['kind']=='native' else {'origin':'human'})
            edge['submitted_by']=delivery._actor(root,project,payload,door)
            edge['policy_id']=policy['id'];edge['policy_revision']=policy['revision']
            route['review_edges'].append(edge)
            route['reservations'][edge['event_id']]={'state':'RESERVED','generation':edge['generation']}
        route['requests'][request]=intent
        _record_route(root,route)  # all intended allocations durable before handoff or transport
    _advance(root,project,ident,task['id'],door)
    return {'effect':'route_recorded','route_id':ident,'replayed':False,
            'aggregate':aggregate(root,project,task['id'],ident),
            'read':handle_read(project,{'action':'route-status','work_id':task['id'],'route_id':ident})}


def _advance(root,project,route_id,work_id,door):
    work,delivery=_owners();from laplace.work import project_work_review as review
    route=_route_for(_task(root,project,work_id)[1],route_id)
    for edge in route['review_edges']:
        try:
            current=_route_for(_task(root,project,work_id)[1],route_id)
            if current['state']=='CANCELLED':break
            task=_task(root,project,work_id)[1]
            if delivery._history(task,edge['event_id']):
                delivery.recover(root,project,{'event_id':edge['event_id']},door)
                _clear_error(root,project,work_id,route_id,edge['event_id'])
                continue
            effect_door=edge['admission_door']
            _origin(root,project,edge['origin'],current=True)
            # The phase is a current owner-validated typed reference, not a copied comment.
            review.feedback_handoff(root,project,work_id,edge,route_id,effect_door)
            delivery.submit(root,project,{'work_id':work_id,'expected_work_revision':work._task_revision(_task(root,project,work_id)[1]),
                'handoff_id':edge['handoff_id'],'obligation_id':edge['obligation_id'],'recipient_binding_id':edge['binding_id'],
                'max_attempts':edge['max_attempts'],'deadline_s':edge['admission_seconds'],
                **({'parent_return':edge['parent_return']} if 'parent_return' in edge else {})},effect_door)
            _clear_error(root,project,work_id,route_id,edge['event_id'])
        except Exception as error:
            # A sibling effect stays visible; this is observation, never permission to reset a reservation.
            with work.dispatch_lock(root):
                latest=_route_for(_task(root,project,work_id)[1],route_id)
                latest.setdefault('edge_errors',{})[edge['event_id']]=str(error)[:500]
                _record_route(root,latest)


def _clear_error(root,project,work_id,route_id,event_id):
    work,_delivery=_owners()
    with work.dispatch_lock(root):
        latest=_route_for(_task(root,project,work_id)[1],route_id)
        if event_id in latest.get('edge_errors',{}):
            del latest['edge_errors'][event_id]
            _record_route(root,latest)


def event_context(root,project,task,handoff):
    """Called only by WD under Work admission; canonical reserve must already exist."""
    material=handoff.get('feedback_route')
    if not material:return None
    route=_route_for(task,material['route_id'])
    if route['state']!='ACTIVE':raise ValueError('Feedback route is stopped.')
    edge=next((r for r in route['review_edges'] if r['edge_id']==material['edge_id'] and r['generation']==material['generation']),None)
    if not edge or edge['event_id'] not in route['reservations']:raise ValueError('No canonical allowance reservation for this delivery.')
    policy=_latest(task,POLICY,edge['policy_id'])
    if policy is None or policy['revision']!=edge['policy_revision']:raise ValueError('Author policy changed before this new effect.')
    if len(route['reservations'])>route['policy']['limits']['max_new_admissions']:raise ValueError('Route allowance exceeded.')
    _origin(root,project,edge['origin'],current=True)
    return {'route_id':route['id'],'work_id':task['id'],'edge_id':edge['edge_id'],'generation':edge['generation'],
        'event_id':edge['event_id'],'runtime_seconds':edge['runtime_seconds']}


def admit_execution(root,project,event_id,session_id):
    """Internal turn-admission recheck. No public payload can create this context."""
    work,delivery=_owners();task=delivery._task_of_event(root,project,event_id)
    history=delivery._history(task,event_id);intent=history[0];latest=history[-1]
    context=intent.get('feedback_execution')
    if not context:raise ValueError('Selected event carries no admitted feedback execution policy.')
    if latest.get('session_id')!=session_id or latest.get('state')!='RESERVED':raise ValueError('Review session is not this event original reservation.')
    handoff=next(r for r in task['phases'] if r['id']==intent['handoff_id'])
    observed=event_context(root,project,task,handoff)
    if observed!=context:raise ValueError('Feedback execution context changed before turn admission.')
    problem=delivery._revalidate(root,project,task,intent)
    if problem:raise ValueError(problem)
    row=_route_for(task,context['route_id']);edge=next(e for e in row['review_edges'] if e['event_id']==event_id)
    # Absolute runtime is issued once at actual admission, not refreshed by transport recovery.
    reservation=row['reservations'][event_id]
    if 'runtime_deadline_at' not in reservation:
        reservation['runtime_deadline_at']=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=context['runtime_seconds'])).isoformat()
        _record_route(root,row)
    return {**context,'runtime_deadline_at':reservation['runtime_deadline_at']}


def admit_research_execution(root,project,event_id):
    """The same reserved author policy, with a Research job rather than a WS/WT."""
    _work,delivery=_owners();task=delivery._task_of_event(root,project,event_id)
    history=delivery._history(task,event_id);intent,latest=history[0],history[-1]
    if (latest.get('state')!='RESERVED' or latest.get('research_request_id')!=event_id
            or intent['recipient'].get('effect')!='research-producer'):
        raise ValueError('Research effect requires its original reserved delivery request.')
    handoff=next(r for r in task['phases'] if r['id']==intent['handoff_id'])
    if event_context(root,project,task,handoff)!=intent.get('feedback_execution'):
        raise ValueError('Research feedback policy changed before admission.')
    problem=delivery._revalidate(root,project,task,intent)
    if problem:raise ValueError(problem)


def record_research_execution(root,project,event_id,run):
    """Project the existing runtime owner's absolute deadline; never renew it."""
    work,delivery=_owners();task=delivery._task_of_event(root,project,event_id)
    intent=delivery._history(task,event_id)[0];context=intent.get('feedback_execution')
    if not context:return
    if run.get('request_id')!=event_id or run.get('project')!=project:
        raise ValueError('Research deadline belongs to another actual request.')
    with work.dispatch_lock(root):
        route=_route_for(_task(root,project,task['id'])[1],context['route_id'])
        reservation=route['reservations'][event_id]
        deadline=dt.datetime.fromtimestamp(run['deadline_at'],dt.timezone.utc).isoformat()
        if reservation.get('runtime_deadline_at',deadline)!=deadline:
            raise ValueError('Original Research runtime deadline custody changed.')
        if 'runtime_deadline_at' not in reservation:
            reservation['runtime_deadline_at']=deadline
            reservation['research_run_id']=run['id'];_record_route(root,route)



JOIN_SCHEMA = 'laplace.feedback-revision-join/1'
_APPLIED = {'COMMITTED', 'UNCHANGED'}
_JOIN_MEANING = ('Production, application, source effect and build are separate owner facts. None is comment disposition, '
                 'review acceptance or scientific acceptance, and this read never retries, applies or builds.')


def _session_turn_read(project, turn_id, **extra):
    return {'http': {'method': 'GET', 'url': '/authoring/session-turn?' + urlencode({'project': project, 'id': turn_id, **extra})}}


def _effect_view(effect):
    """The application's own laplace.source-effect/1 receipt, bounded; never a re-inspection of current bytes."""
    from laplace.manuscript import source_effects
    if (not isinstance(effect, dict) or effect.get('schema_version') != source_effects.SCHEMA
            or effect.get('state') not in source_effects.STATES):
        return {'state': 'UNAVAILABLE', 'complete': False, 'files': [], 'files_total': 0,
                'reason': 'This application recorded no laplace.source-effect/1 receipt; current bytes are not a substitute.'}
    files = [row for row in effect.get('files') or () if isinstance(row, dict)]
    required = (effect.get('follow_through') or {}).get('required') or ()
    complete = effect.get('complete') is True
    return {'schema_version': effect['schema_version'], 'state': effect['state'], 'complete': complete,
            'selection_identity': effect.get('selection_identity'),
            'files': [{key: row.get(key) for key in ('path', 'before_sha256', 'after_sha256', 'observed_after_sha256', 'observation_error')
                       if key in row} for row in files[:32]],
            'files_total': len(files),
            'required': [copy.deepcopy(row) for row in list(required)[:16] if isinstance(row, dict)],
            'recovery': None if effect['state'] in _APPLIED and complete else
                'Inspect this exact receipt and its required follow-through; never repeat the application automatically.'}


_SUCCESSOR_LIMIT = 4
_SUCCESSOR_MEANING = ('A resolved successor is a separately authored current-source candidate that names this exact predecessor '
    'version and edit in the reconciliation index. Its application, source effect and build are its own and never '
    'relabel the direct facts of the original version; nothing here renews scientific acceptance, rewrites a record or repeats an Apply or build.')


def _successor_application(root, project, ref, row, fields, problem):
    """One successor-owned application row -> its own source_effect receipt -> the build owner's proof for its pins."""
    from laplace.manuscript import build_jobs
    raw_effect = fields.get('source_effect')
    effect = _effect_view(raw_effect)
    if problem:
        effect = {**effect, 'state': 'UNAVAILABLE', 'reason': problem}
    document = fields.get('document') if isinstance(fields.get('document'), dict) else (row.get('document') or {})
    # A successor application is a candidate-owned journal row with no writing turn: its exact read is the journal record
    # owner's (author_history record of this row), never a session-turn view keyed by the candidate id.
    from laplace.work.author_history_metrics import _read_handle
    read = _read_handle(project, {'view': 'record', 'id': 'activity:journal:' + row['id']})
    if effect['state'] in _APPLIED:
        build = build_jobs.source_observation(project, root, root_tex=document.get('root'),
            selection_identity=effect.get('selection_identity'), files=list((raw_effect or {}).get('files') or []))
    else:
        build = {'state': 'NOT_APPLICABLE', 'next_read': read,
                 'reason': 'Source effect %s: no build can show this successor application.' % effect['state']}
    return {'id': row['id'], 'row_sha256': row['_hash'], 'candidate_ref': dict(ref), 'complete': row.get('complete') is True,
            'document_root': document.get('root'), 'read': read, 'source_effect': effect, 'build': build}


def _successor_lineage(root, project, selected, total, predecessor_read):
    """Bounded resolved-successor facts of ONE predecessor version, each from its existing owner read."""
    from laplace.manuscript import proposal_navigation, reconciliation, build_targets
    items = []
    for edit_id, row, apps, deeper in selected:
        ref = {'id': row['id'], 'version': row.get('proposal_instance_version')}
        pred = row.get('predecessor') or {}
        read = proposal_navigation.handle(project, {'id': ref['id'], 'proposal_version': ref['version'], 'view': 'summary'})
        try:
            owner = reconciliation.read_candidate(root, project, ref)
            disposition = owner.get('disposition') or {}
            candidate = {'state': 'READ', 'proposal_state': owner.get('proposal_state'), 'author': copy.deepcopy(owner.get('author')),
                         'disposition': {key: disposition.get(key) for key in ('status', 'decision_id', 'resolution_application_id')},
                         'read_handle': copy.deepcopy(owner.get('read_handle'))}
        except (ValueError, OSError, LookupError, TypeError, AttributeError) as error:
            candidate = {'state': 'UNAVAILABLE', 'reason': (type(error).__name__ + ': ' + str(error))[:300]}
        shown, mismatched = [], []
        for app, fields, problem in apps:
            if app.get('candidate_version') != ref['version'] or app.get('candidate_id') not in (None, ref['id']):
                mismatched.append({'id': app['id'], 'row_sha256': app['_hash'], 'candidate_version': app.get('candidate_version'),
                    'reason': 'This application does not name the exact successor version; it is not counted as applied or built.'})
                continue
            shown.append(_successor_application(root, project, ref, app, fields, problem))
        applied = [item for item in shown if item['source_effect']['state'] in _APPLIED]
        built = [item for item in applied if item['build']['state'] == 'BUILT']
        if not shown:
            state, next_read = 'NOT_APPLIED', read
        elif not applied:
            state, next_read = 'APPLICATION_INCOMPLETE', shown[-1]['read']
        elif not built:
            state, next_read = 'NOT_BUILT', applied[-1]['build'].get('next_read') or build_targets.read_handle(project)
        else:
            state, next_read = 'BUILT', built[-1]['build']['job_status_read']
        items.append({'candidate_ref': ref, 'row_sha256': row['_hash'], 'state': state, 'next_read': next_read, 'read': read,
            'predecessor': {'edit_id': edit_id, **{key: copy.deepcopy(pred[key]) for key in ('record_id', 'turn_id', 'proposal_version', 'candidate_ref') if key in pred}},
            'candidate': candidate, 'links': {'applied': bool(applied), 'built': bool(built)},
            'applications': shown, 'mismatched_applications': mismatched,
            'deeper': {'state': 'PARTIAL' if deeper else 'NONE', 'successors': deeper, 'next_read': read if deeper else None,
                       **({'reason': 'A later resolution of this successor exists and is not expanded here; follow its own read.'} if deeper else {})}})
    omitted = max(0, total - len(selected))
    return {'state': 'NONE' if not total else 'PARTIAL' if omitted else 'COMPLETE', 'total': total, 'omitted': omitted,
            'limit': _SUCCESSOR_LIMIT, 'items': items, 'meaning': _SUCCESSOR_MEANING,
            **({'continuation': {'reason': '%d further resolved successors are not shown; read the predecessor proposal.' % omitted,
                                 'next_read': predecessor_read}} if omitted else {})}


def _successor_summary(proposals):
    rows = [item for proposal in proposals for item in (proposal.get('resolved_successors') or {}).get('items', ())]
    states = [item['state'] for item in rows]
    state = 'NONE' if not rows else next(name for name in ('BUILT', 'NOT_BUILT', 'APPLICATION_INCOMPLETE', 'NOT_APPLIED') if name in states)
    partial = (any((proposal.get('resolved_successors') or {}).get('state') == 'PARTIAL' for proposal in proposals)
               or any(item['deeper']['state'] == 'PARTIAL' for item in rows))
    return {'state': state, 'total': len(rows), 'applied': sum(item['links']['applied'] for item in rows),
            'built': sum(item['links']['built'] for item in rows), 'partial': partial, 'meaning': _SUCCESSOR_MEANING}


def revision_join(root, project, turn_id):
    """Produced proposal -> guarded application/source effect -> matching build of ONE admitted producer turn.

    Every link comes from its existing owner at one index cut: the indexed proposal carriers of this exact turn (their
    sealed proposal_instance_version, never reply prose), writing-application rows of this project whose recorded
    candidate_version names that version, each application's own source_effect receipt (never matching current bytes)
    and the build owner's dependency proof for that effect's observed after-pins (build_jobs.source_observation, never a
    nearest or latest PDF). An absent or uncorroborated link stays explicit (NOT_PRODUCED, NOT_APPLIED,
    APPLICATION_INCOMPLETE, NOT_BUILT, UNAVAILABLE) with the owner's next read. Read-only: nothing is retried."""
    from laplace.writing import records
    from laplace.writing.records import _index as owner_index
    from laplace.manuscript import proposal_navigation, build_jobs, build_targets
    root = Path(root).resolve()
    turn_read = _session_turn_read(project, turn_id, view='turn')
    base = {'schema_version': JOIN_SCHEMA, 'project': project, 'turn_id': turn_id, 'turn_read': turn_read, 'meaning': _JOIN_MEANING}
    with records.index_lock:
        idx = records.index(root)
        try:
            resolved = owner_index.resolve_record_family(idx, project, turn_id, kind='writing-turn')
        except ValueError as error:   # AmbiguousRecord, stale pin or changed captured row: no partial join
            return {**base, 'state': 'UNAVAILABLE', 'reason': str(error)[:300], 'next_read': turn_read}
        if resolved is None:
            return {**base, 'state': 'UNAVAILABLE', 'reason': 'The admitted producer turn is not recorded in this project.', 'next_read': turn_read}
        rows = [row for row in idx.by_turn.get(turn_id, ()) if idx.project(row) == project]
        versions = {}
        for row in rows:
            version = row.get('proposal_instance_version')
            if row.get('record') in ('writing-reply', 'writing-proposal') and row.get('has_proposal') and isinstance(version, str):
                versions.setdefault(version, []).append(copy.deepcopy(row))
        applications = []
        for row in rows:
            if row.get('record') != 'writing-application':
                continue
            try:
                fields = records.selected_journal_fields(project, row['id'], root, fields=['source_effect', 'document'],
                                                         expected_row_sha256=row['_hash'])
                problem = None
            except ValueError as error:
                fields, problem = {}, str(error)[:300]
            applications.append((copy.deepcopy(row), fields, problem))
        # Resolved successors: the reconciliation owner's indexed exact predecessor key (project, predecessor id,
        # version, edit), never latest or text matching; each successor's own applications come from by_candidate.
        lineage = {}
        for version, carriers in versions.items():
            first = carriers[0]
            ident = first['id'] if first.get('record') == 'writing-proposal' and first.get('candidate_kind') else turn_id
            found = sorted(((key[3], row) for key, group in idx.by_predecessor.items()
                            if key[0] == project and key[1] == ident and key[2] == version
                            for row in group if row.get('record') == 'writing-proposal' and idx.project(row) == project),
                           key=lambda pair: pair[1]['_order'])
            chosen = []
            for edit_id, row in found[:_SUCCESSOR_LIMIT]:
                owned = []
                for app in idx.by_candidate.get(row['id'], ()):
                    if app.get('record') != 'writing-application' or idx.project(app) != project:
                        continue
                    try:
                        fields = records.selected_journal_fields(project, app['id'], root, fields=['source_effect', 'document'],
                                                                 expected_row_sha256=app['_hash'])
                        problem = None
                    except ValueError as error:
                        fields, problem = {}, str(error)[:300]
                    owned.append((copy.deepcopy(app), fields, problem))
                deeper = sum(len(group) for key, group in idx.by_predecessor.items() if key[0] == project and key[1] == row['id'])
                chosen.append((edit_id, copy.deepcopy(row), owned, deeper))
            lineage[version] = (chosen, len(found))
        cut = idx.order
    proposals, attributed_ids = [], set()
    for version, carriers in versions.items():
        first = carriers[0]
        standalone = first.get('record') == 'writing-proposal' and bool(first.get('candidate_kind'))
        items = []
        for row, fields, problem in applications:
            if row.get('candidate_version') != version:
                continue
            attributed_ids.add(row['id'])
            raw_effect = fields.get('source_effect')
            effect = _effect_view(raw_effect)
            if problem:
                effect = {**effect, 'state': 'UNAVAILABLE', 'reason': problem}
            document = fields.get('document') if isinstance(fields.get('document'), dict) else (row.get('document') or {})
            if effect['state'] in _APPLIED:
                build = build_jobs.source_observation(project, root, root_tex=document.get('root'),
                    selection_identity=effect.get('selection_identity'), files=list(raw_effect.get('files') or []))
            else:
                build = {'state': 'NOT_APPLICABLE', 'next_read': _session_turn_read(project, turn_id, view='application', item_id=row['id']),
                         'reason': 'Source effect %s: no build can show this application.' % effect['state']}
            items.append({'id': row['id'], 'row_sha256': row['_hash'], 'candidate_version': version,
                          'candidate_edit_ids': list(row.get('candidate_edit_ids') or []), 'complete': row.get('complete') is True,
                          'read': _session_turn_read(project, turn_id, view='application', item_id=row['id']),
                          'source_effect': effect, 'build': build})
        ident = first['id'] if standalone else turn_id
        proposals.append({'version': version, 'carrier_record_ids': [row['id'] for row in carriers],
                          **({'candidate_ref': {'id': first['id'], 'version': version}} if standalone
                             else {'turn_proposal': {'turn_id': turn_id, 'proposal_version': version}}),
                          'read': proposal_navigation.handle(project, {'id': ident, 'proposal_version': version, 'view': 'summary'}),
                          'applications': items,
                          'resolved_successors': _successor_lineage(root, project, *lineage.get(version, ([], 0)),
                              proposal_navigation.handle(project, {'id': ident, 'proposal_version': version, 'view': 'summary'}))})
    unattributed = [{'id': row['id'], 'row_sha256': row['_hash'], 'candidate_version': row.get('candidate_version'),
                     'read': _session_turn_read(project, turn_id, view='application', item_id=row['id']),
                     'reason': 'No owner-corroborated proposal version of this turn names this application; it is not counted as applied.'}
                    for row, _fields, _problem in applications if row['id'] not in attributed_ids]
    every = [item for proposal in proposals for item in proposal['applications']]
    applied = [item for item in every if item['source_effect']['state'] in _APPLIED]
    built = [item for item in applied if item['build']['state'] == 'BUILT']
    incomplete = [item for item in every if item['source_effect']['state'] not in _APPLIED or not item['source_effect']['complete']]
    if not proposals:
        state, next_read = 'NOT_PRODUCED', turn_read
    elif not every:
        state, next_read = 'NOT_APPLIED', proposals[-1]['read']
    elif not applied:
        state, next_read = 'APPLICATION_INCOMPLETE', incomplete[-1]['read']
    elif not built:
        state, next_read = 'NOT_BUILT', applied[-1]['build'].get('next_read') or build_targets.read_handle(project)
    else:
        state, next_read = 'BUILT', built[-1]['build']['job_status_read']
    return {**base, 'state': state, 'index_cut': cut, 'next_read': next_read,
            'links': {'produced': bool(proposals), 'applied': bool(applied), 'built': bool(built),
                      'incomplete_applications': len(incomplete), 'unattributed_applications': len(unattributed)},
            'proposals': proposals, 'unattributed_applications': unattributed,
            'resolved_successors': _successor_summary(proposals)}


def _route_revision(origin, edges):
    """Route-level join summary plus the separately owned disposition facts; nothing is inferred between them."""
    comment = {key: copy.deepcopy(origin.get(key)) for key in ('status', 'status_note', 'status_history') if key in origin}
    return {'schema_version': JOIN_SCHEMA,
            'edges': [{'edge_id': edge['edge_id'], 'state': (edge.get('revision') or {}).get('state'),
                       'links': copy.deepcopy((edge.get('revision') or {}).get('links')),
                       'resolved_successors': copy.deepcopy((edge.get('revision') or {}).get('resolved_successors'))} for edge in edges],
            'disposition': {'comment': comment, 'comment_owner': 'correction_origin',
                            'review_reads': [edge['review_read'] for edge in edges],
                            'meaning': 'Disposition is recorded only by the comment owner and the Work review; produced, '
                                       'applied or built never implies it, and transport never implies acceptance.'}}


def _edge_view(root,project,task,edge,route,*,read_context=None):
    _work,delivery=_owners();from laplace.work.project_work_views import handle
    history=delivery._history(task,edge['event_id']);event=delivery._facet_event(root,project,task,edge['event_id'],read_context=read_context) if history else None
    binding=delivery._latest(task,delivery.BINDING,edge['binding_id'])
    value={key:edge[key] for key in ('edge_id','generation','obligation_id')}
    value.update(submitted_by=edge.get('submitted_by'),policy_basis={'id':edge['policy_id'],'revision':edge['policy_revision']},
        execution_limits={key:edge[key] for key in ('runtime_seconds','max_attempts','admission_seconds')},recipient=delivery._public_binding(binding) if binding else {'id':edge['binding_id'],'state':'UNAVAILABLE'},
        execution_deadline_at=(route['reservations'].get(edge['event_id']) or {}).get('runtime_deadline_at'),
        handoff_read=handle(project,{'view':'review','id':task['id'],'phase_id':edge['handoff_id']}),event=event,
        error=(route.get('edge_errors') or {}).get(edge['event_id']),
        review_read=handle(project,{'view':'review','id':task['id'],'obligation_id':edge['obligation_id']}))
    # The review focus is the question AUTHORED for this request: a new edge retains its snapshot; a legacy edge is
    # qualified to its exact handed phase and never silently borrows a changed current Work question.
    snapshot=edge.get('obligation')
    value['obligation']=({'state':'AUTHORED_SNAPSHOT',**copy.deepcopy(snapshot)} if isinstance(snapshot,dict) and snapshot.get('id')==edge['obligation_id']
        else {'state':'LEGACY_UNSNAPSHOTTED','id':edge['obligation_id'],'label':None,'scope':None,'next_read':value['handoff_read'],
              'reason':'This request predates retained review-focus snapshots; its exact historical question is the handed phase, not the current Work question.'})
    value['revision']={'schema_version':JOIN_SCHEMA,'state':'NO_ADMITTED_PRODUCER','meaning':_JOIN_MEANING,
        'links':{'produced':False,'applied':False,'built':False},'next_read':value['handoff_read']}
    if event and event.get('admitted'):
        admitted=event['admitted']
        if admitted.get('research_run_id'):
            value['result_read']=event['research_run_read'];value['recipient_ack']=admitted.get('recipient_ack')
            value['revision']={'schema_version':JOIN_SCHEMA,'state':'NOT_APPLICABLE','meaning':_JOIN_MEANING,
                'reason':'A registered research producer returns a research result, not a manuscript proposal.',
                'links':{'produced':False,'applied':False,'built':False},'next_read':value['result_read']}
            return value
        sid,tid=admitted['session_id'],admitted['turn_id']
        from laplace.writing import session_reads,records
        read=session_reads._message_handle({'project':project,'session_id':sid,'turn_id':tid,'part':'reply','limit':4000},offset=0)
        value['public_reply_read']={key:read[key] for key in ('identity','http','sdk')}
        value['turn_read']={'http':{'method':'GET','url':'/authoring/session-turn?'+urlencode({'project':project,'id':tid,'view':'turn'})}}
        reply=(delivery._read_fold(root,read_context).get('turns',{}).get(tid) or {}).get('reply') or {}
        if reply.get('id'):
            from laplace.work.author_history_metrics import _read_handle
            value['exact_reply_read']=_read_handle(project,{'view':'record','id':'activity:journal:'+reply['id']})
        value['recipient_ack']=event.get('admitted',{}).get('recipient_ack')
        value['revision']=revision_join(root,project,tid)
        if event.get('result',{}).get('available'):
            event['result']['preview_characters']=len(event['result'].get('text') or '')
            event['result']['preview']=True;event['result']['complete']=False
            if reply.get('feedback_execution'):event['result']['execution']=reply['feedback_execution']
    return value


def aggregate(root,project,work_id,route_id,*,read_context=None):
    context={} if read_context is None else read_context
    work,delivery=_owners();task=_task(root,project,work_id,read_context=context)[1];route=_route_for(task,route_id)
    try:origin=_origin(root,project,route['origin'],read_context=context)
    except ValueError as error:origin={'origin_ref':route['origin'],'currentness':{'state':'UNAVAILABLE','reason':str(error)}}
    edges=[_edge_view(root,project,task,e,route,read_context=context) for e in route['review_edges']]
    admitted=sum(bool(e.get('event',{}).get('admitted')) for e in edges if e.get('event'))
    ready=sum(bool((e.get('event') or {}).get('result',{}).get('available')) for e in edges)
    if route['state']=='CANCELLED':state='cancelled'
    elif ready==len(edges) and edges:state='response_ready'
    elif ready:state='partial'
    elif any((e.get('event') or {}).get('admitted') for e in edges):state='waiting'
    elif any(e.get('error') or (e.get('event') or {}).get('state') in {'STALE','UNSUPPORTED','UNCONFIRMED'} for e in edges):state='unavailable'
    else:state='sending'
    target={'work_id':work_id,'route_id':route_id}
    from laplace.work import owner_discovery,object_geometry
    reference=owner_discovery.work_reference(project,work_id)
    review_context={'schema_version':'laplace.feedback-review-context/1','project':project,'project_lens':project,
        'reference':reference,'basis':work._task_revision(task),'basis_kind':'work-specification',
        'association':{'kind':'recorded-route','route_id':route_id,'origin_ref':route['origin']},
        'observation':'Work reference at aggregate read; geometry and its separate owner cuts have not been inspected.',
        'neighbourhood_read':object_geometry.handle({'facet':'neighbourhood','reference':reference,'project_lens':project})}
    return copy.deepcopy({'schema_version':SCHEMA,'project':project,'route_id':route_id,'state':state,
        'work':{'id':work_id,'title':task.get('title'),'revision':work._task_revision(task)},'origin':origin,'policy':route['policy'],
        'review_context':review_context,
        'allowance':{'max_new_admissions':route['policy']['limits']['max_new_admissions'],'reserved':len(route['reservations']),
                     'admitted':admitted,'unconfirmed':len(route['reservations'])-admitted,
                     'basis':'Admitted is retained WD coordinates; unconfirmed reservations are not zero use.',
                     'remaining':max(0,route['policy']['limits']['max_new_admissions']-len(route['reservations']))},
        'edges':edges,'revision':_route_revision(origin,edges),'read':handle_read(project,{'action':'route-status',**target}),
        'actions':{'recover':_action(project,{'action':'route-recover',**target},permitted=state!='cancelled'),
                   'cancel':_action(project,{'action':'route-cancel',**target},permitted=state!='cancelled')}})


def status(root,project,payload,*,read_context=None):
    context={} if read_context is None else read_context
    task=_task(root,project,payload['work_id'],read_context=context)[1]
    if payload.get('policy_id'):
        row=_latest(task,POLICY,payload['policy_id'])
        if row is None:raise ValueError('Unknown author policy.')
        return {'effect':'RECORDED','policy':copy.deepcopy(row),'read':handle_read(project,payload)}
    if payload.get('route_id'):return aggregate(root,project,task['id'],payload['route_id'],read_context=context)
    if payload.get('origin'):
        ref=_origin(root,project,payload['origin'],read_context=context)['origin_ref']
        ident='FR-'+_owners()[1]._digest([project,task['id'],_origin_key(ref)])[7:31]
        if _latest(task,ROUTE,ident):return aggregate(root,project,task['id'],ident,read_context=context)
        return {'effect':'NONE','origin_ref':copy.deepcopy(ref),'meaning':'No route for this original comment at the current Work cut.'}
    if payload.get('request_id'):
        _request(payload['request_id'])
        kind=payload.get('request_kind') or 'route'
        if kind not in REQUEST_KINDS:raise ValueError('Select route or policy request kind.')
        if 'submission' in payload:return associate(project,task,payload)
        # The legacy lookup is unchanged; it additionally issues the owner's exact comparison template.
        issued={'compare':_compare(project,task['id'],kind,payload['request_id'])}
        settled=_settlement_rows(task,kind,payload['request_id'])
        if kind=='policy':
            prior=next((r for r in _rows(task,POLICY) if r.get('request_id')==payload['request_id']),None)
            if prior:return {'effect':'RECORDED','policy':copy.deepcopy(prior),
                     'read':handle_read(project,{'action':'route-status','work_id':task['id'],'policy_id':prior['id']}),**issued}
            if settled:return {**_terminal(project,task['id'],settled[-1]),**issued}
            return {'effect':'NONE','request_id':payload['request_id'],'meaning':'No policy request at this Work read; retain exact wire for explicit same-request retry.',**issued}
        for row in reversed(_rows(task,ROUTE)):
            if payload['request_id'] in row.get('requests',{}):
                return {'effect':'RECORDED','intent_sha256':row['requests'][payload['request_id']],
                        'aggregate':aggregate(root,project,task['id'],row['id'],read_context=context),'read':handle_read(project,{'action':'route-status','work_id':task['id'],'route_id':row['id']}),**issued}
        if settled:return {**_terminal(project,task['id'],settled[-1]),**issued}
        manual='manual:'+_owners()[1]._digest(payload['request_id'])[7:39]
        partial=next((r for r in _rows(task,POLICY) if r.get('request_id')==manual),None)
        if partial:return {'effect':'UNKNOWN','request_id':payload['request_id'],'policy':copy.deepcopy(partial),
                           'meaning':'Manual policy recorded; route publication unconfirmed. Retain the exact submit identity.',**issued}
        return {'effect':'NONE','request_id':payload['request_id'],'meaning':'No route at this captured Work read; retain exact request for explicit retry.',**issued}
    policies={row['id']:row for row in _rows(task,POLICY)};routes={row['id']:row for row in _rows(task,ROUTE)}
    return {'policies':[copy.deepcopy(r) for r in list(policies.values())[-16:]],'routes':[
        {'route_id':r['id'],'origin_ref':r['origin'],'read':handle_read(project,{'action':'route-status','work_id':task['id'],'route_id':r['id']})}
        for r in list(routes.values())[-16:]],'policies_total':len(policies),'routes_total':len(routes),'policy_schema':policy_schema()}


_SUBMISSIONS={
    'route':('route-submit',{'project','action','work_id','expected_work_revision','request_id','origin','policy','policy_id',
                             'expected_policy_revision','recipients'},{'action','work_id','expected_work_revision','request_id','origin'}),
    'policy':('policy-save',{'project','action','work_id','expected_work_revision','request_id','policy','policy_id',
                             'expected_policy_revision'},{'action','work_id','expected_work_revision','request_id','policy'})}


def _submission(project,work_id,kind,request,value):
    """The closed ORIGINAL route-submit/policy-save wire. Its nested CAS stays history: never refreshed or reused."""
    if kind not in REQUEST_KINDS:raise ValueError('Select route or policy request kind.')
    action,allowed,required=_SUBMISSIONS[kind]
    _closed(value,allowed,required)
    if (value['action']!=action or value.get('project',project)!=project or value['work_id']!=work_id
            or value['request_id']!=request):
        raise ValueError('The original submission belongs to another project, Work, request kind or request; nothing is compared.')
    _request(request)
    if kind=='policy' or value.get('policy') is not None:_policy_identity(value['policy'])
    return copy.deepcopy(value)


def _policy_identity(value):
    """_policy_value's own normalized shape WITHOUT current-binding revalidation (historical intent only)."""
    _closed(value,('mode','recipients','limits','parent_return'),('mode','recipients','limits'))
    return {key:copy.deepcopy(value[key]) for key in ('mode','recipients','limits','parent_return')
            if key in value and not (key=='parent_return' and value[key] is None)}


def _intent_of(kind,submission):
    # Owner domains: route = _request_intent's selected fields; policy = its exact replay revision. Never a raw wire SHA.
    return _request_intent(submission) if kind=='route' else _owners()[1]._digest(submission['policy'])


def _settlement_rows(task,kind,request):
    return [row for row in _rows(task,SETTLEMENT) if row.get('request_kind')==kind and row.get('request_id')==request]


def _public_settlement(row):
    return {key:copy.deepcopy(row.get(key)) for key in ('id','request_kind','request_id','intent_sha256','code','outcome_scope','by','ts')}


def _terminal(project,work_id,row):
    return {'effect':'NOT_ADMITTED','terminal':True,'replayed':True,'request_kind':row['request_kind'],'request_id':row['request_id'],
            'intent_sha256':row['intent_sha256'],'settlement':_public_settlement(row),
            'preserved_effects':copy.deepcopy(row.get('preserved_effects') or []),
            'meaning':'The author settled this exact original request; a later copy is refused before CAS, policy, reservation or transport. '
                      'Recorded partial effects stay recorded in preserved_effects; nothing was refunded, deleted or cancelled.',
            'read':handle_read(project,{'action':'route-status','work_id':work_id,'request_id':row['request_id'],'request_kind':row['request_kind']})}


def _fence(project,task,kind,request,intent):
    rows=_settlement_rows(task,kind,request)
    if not rows:return None
    if len(rows)>1:raise ValueError('Request settlement custody is ambiguous; nothing new was admitted.')
    if rows[0].get('intent_sha256')!=intent:raise ValueError('Request_id was already settled for another exact intent; nothing new was admitted.')
    return _terminal(project,task['id'],rows[0])


def _compare(project,work_id,kind,request):
    """Owner-issued pure comparison template; a client fills only `field` inside the issued request JSON."""
    return {'schema_version':COMPARISON,'kind':kind,'project':project,'context':work_id,'request_id':request,
            'requires':['submission'],'carrier':'request-json','field':'submission',
            'read':handle_read(project,{'action':'route-status','work_id':work_id,'request_id':request,'request_kind':kind}),
            'meaning':'Pure read: compares the exact original request intent; it saves, reserves, settles and transports nothing.'}


def _unknown(reason):
    return {'effect':'UNKNOWN','state':'UNKNOWN','settle':False,'scope':None,'preserved':[],'reason':reason}


def _observe(project,task,kind,request,submission,intent):
    """Pure association of ONE exact original request at this Work fold: no write, reservation or refreshed CAS."""
    delivery=_owners()[1];settled=_settlement_rows(task,kind,request)
    if len(settled)>1:return _unknown('Settlement custody for this request is ambiguous; nothing is inferred.')
    if kind=='route':
        recorded=[row for row in _rows(task,ROUTE) if request in (row.get('requests') or {})]
        values={row['requests'][request] for row in recorded}
        if len(values)>1 or (recorded and settled):return _unknown('Recorded custody for this request is ambiguous; nothing is inferred.')
        if recorded:
            return {'effect':'RECORDED','state':'MATCH' if values=={intent} else 'MISMATCH','settle':False,'scope':None,
                    'preserved':[],'route_id':recorded[-1]['id']}
    else:
        ident=submission.get('policy_id') or 'FP-'+delivery._digest([project,task['id'],request])[7:31]
        priors=[row for row in _rows(task,POLICY) if row.get('request_id')==request]
        if priors and settled:return _unknown('Recorded custody for this request is ambiguous; nothing is inferred.')
        if priors:
            same=priors[0].get('revision')==intent and priors[0].get('id')==ident
            return {'effect':'RECORDED','state':'MATCH' if same else 'MISMATCH','settle':False,'scope':None,'preserved':[],
                    **({'policy':copy.deepcopy(priors[0])} if same else {})}
    if settled:
        return {'effect':'NOT_ADMITTED','state':'MATCH' if settled[0].get('intent_sha256')==intent else 'MISMATCH',
                'settle':False,'scope':None,'preserved':[],'settlement':copy.deepcopy(settled[0])}
    if kind=='route':
        manual='manual:'+delivery._digest(request)[7:39]
        partials=[row for row in _rows(task,POLICY) if row.get('request_id')==manual]
        if partials:
            inline=submission.get('policy')
            if inline is None or len({row.get('revision') for row in partials})!=1 or partials[0].get('mode')!='manual':
                return _unknown('A manual policy for this request is recorded but cannot be attributed to this exact submission; nothing is settled.')
            if partials[0].get('revision')!=delivery._digest(_policy_identity(inline)):
                return {**_unknown('The recorded manual policy of this request_id has another exact intent.'),'state':'MISMATCH'}
            policy=partials[-1]
            return {'effect':'UNKNOWN','state':'UNKNOWN','settle':True,'scope':'route-admission-only','qualified':True,
                    'preserved':[{'kind':POLICY,'id':policy['id'],'revision':policy['revision'],'request_id':manual,
                        'read':handle_read(project,{'action':'route-status','work_id':task['id'],'policy_id':policy['id']})}],
                    'reason':'The exact matching manual policy of this request was recorded; this route request was not published.'}
    return {'effect':'NONE','state':'UNRECORDED','settle':True,'scope':'request','preserved':[]}


_SETTLE_REFUSALS={'RECORDED':'This original request is recorded; settlement cannot cancel, refund or tombstone it.',
                  'NOT_ADMITTED':'This original request is already settled.',
                  'UNKNOWN':'Publication of this request is not attributable; inspect it before any settlement.'}


def _settle_template(project,work_id,kind,request,seen):
    permitted=bool(seen.get('settle')) and seen['state']!='MISMATCH'
    reason=('' if permitted else 'This request_id has another exact intent; nothing may be settled from this copy.'
            if seen['state']=='MISMATCH' else _SETTLE_REFUSALS.get(seen['effect'],'Not settleable.'))
    return {**_action(project,{'action':'request-settle','work_id':work_id,'request_kind':kind,'request_id':request},
                      permitted=permitted,reason=reason),
            'requires':['submission'],'authority':'human','outcome_scope':seen.get('scope') if permitted else None,
            'meaning':'Explicit author terminal of this exact original request only: never a retry, refund, policy deletion or cancellation of another request.'}


def _association_reply(project,work_id,kind,request,intent,seen):
    value={'effect':seen['effect'],'request_id':request,'request_kind':kind,
           'association':{'schema_version':ASSOCIATION,'kind':kind,'project':project,'context':work_id,
                          'request_id':request,'state':seen['state'],'intent_sha256':intent},
           'compare':_compare(project,work_id,kind,request),'settle':_settle_template(project,work_id,kind,request,seen)}
    if seen['state']=='MISMATCH':
        return {**value,'effect':'MISMATCH','meaning':'This request_id records another exact intent; retain this copy and do not settle or retry it.'}
    if seen.get('route_id'):value.update(route_id=seen['route_id'],read=handle_read(project,{'action':'route-status','work_id':work_id,'route_id':seen['route_id']}))
    if seen.get('policy'):value.update(policy=seen['policy'],read=handle_read(project,{'action':'route-status','work_id':work_id,'policy_id':seen['policy']['id']}))
    if seen.get('settlement'):
        value.update(terminal=True,settlement=_public_settlement(seen['settlement']),
                     preserved_effects=copy.deepcopy(seen['settlement'].get('preserved_effects') or []))
    elif seen.get('qualified'):value['preserved_effects']=copy.deepcopy(seen['preserved'])
    if seen.get('reason'):value['reason']=seen['reason']
    return copy.deepcopy(value)


def associate(project,task,payload):
    """route-status with an ORIGINAL submission: the scoped owner association, read-only."""
    kind=payload.get('request_kind') or 'route';request=_request(payload['request_id'])
    submission=_submission(project,task['id'],kind,request,payload['submission'])
    intent=_intent_of(kind,submission)
    return _association_reply(project,task['id'],kind,request,intent,_observe(project,task,kind,request,submission,intent))


def _guard(seen):
    return json.dumps([seen['effect'],seen['state'],bool(seen.get('settle')),seen.get('scope'),seen.get('preserved')],sort_keys=True,default=str)


def settle(root,project,payload,door):
    """HUMAN-only terminal of one exact unadmitted original request, in the existing Work ledger.

    Lock order: Work dispatch lock (shared with policy_save/submit), then the ledger writer's final admit guard.
    A matching recorded result wins; only verified absence (or the exact matching partial manual policy, scoped to
    route admission) is settled, and only a successful readback is reported terminal. No transport, no CAS refresh."""
    work,delivery=_owners();actor=delivery._acting(root,project,door)
    if actor.get('kind')!='human':
        raise ValueError('Only the author may settle an original route or policy request; native producers and reviewers may only inspect it.')
    kind=payload['request_kind'];request=_request(payload['request_id'])
    submission=_submission(project,payload['work_id'],kind,request,payload['submission'])
    intent=_intent_of(kind,submission)
    with work.dispatch_lock(root):
        _tasks,task=_task(root,project,payload['work_id'])
        seen=_observe(project,task,kind,request,submission,intent)
        if seen['state']=='MISMATCH':raise ValueError('This request_id already has another exact intent; nothing was settled.')
        if not seen.get('settle'):return {**_association_reply(project,task['id'],kind,request,intent,seen),'settled':False}
        ident='FS-'+delivery._digest([project,task['id'],kind,request])[7:31]
        row={'kind':SETTLEMENT,'id':ident,'project':project,'work_id':task['id'],'request_kind':kind,'request_id':request,
             'intent_sha256':intent,'code':SETTLED_CODE,'outcome_scope':seen['scope'],'preserved_effects':copy.deepcopy(seen['preserved']),
             'by':'author','actor':delivery._actor(root,project,payload,door)}
        basis=_guard(seen)
        def admit():
            # Final guard under the ledger writer lock: this exact request is still in the observed custody.
            if _guard(_observe(project,_task(root,project,task['id'])[1],kind,request,submission,intent))!=basis:
                raise ValueError('CHANGED_INPUT: this request changed before settlement; nothing was settled.')
        problem=None
        try:work._append(root,{**row,'record':'project-work-phase','ts':delivery._now()},admit=admit)
        except ValueError:raise
        except Exception as error:problem=(type(error).__name__+': '+str(error))[:240]
        try:after=_observe(project,_task(root,project,task['id'])[1],kind,request,submission,intent)
        except Exception as error:after=_unknown('Settlement readback failed: '+(type(error).__name__+': '+str(error))[:200])
    reply=_association_reply(project,task['id'],kind,request,intent,after)
    if after['effect']=='NOT_ADMITTED' and after['state']=='MATCH' and after['settlement'].get('id')==ident:
        return {**reply,'settled':True,'replayed':False,
                'meaning':'Settled by the author: later copies of this exact request are refused before any further effect; preserved_effects stay recorded.'}
    return {**reply,'effect':'UNKNOWN','settled':False,
            'reason':problem or after.get('reason') or 'Settlement was not confirmed by readback; retain the original request.'}


def recover(root,project,payload,door):
    actor=_owners()[1]._acting(root,project,door)
    if actor.get('role')=='review':raise ValueError('Reviewers cannot recover paid routing effects.')
    _advance(root,project,payload['route_id'],payload['work_id'],door)
    return {'effect':'route_recorded','aggregate':aggregate(root,project,payload['work_id'],payload['route_id'])}


def cancel(root,project,payload,door):
    work,delivery=_owners();actor=delivery._acting(root,project,door)
    if actor.get('role')=='review':raise ValueError('Reviewers cannot stop another route by naming its id.')
    with work.dispatch_lock(root):
        row=_route_for(_task(root,project,payload['work_id'])[1],payload['route_id']);row['state']='CANCELLED';_record_route(root,row)
    from laplace.writing import turn_control,turn_admission,records
    # Cancellation never transports a request. Reconcile an already banked
    # WT whose WD acknowledgement was lost before interrupting its owned job.
    for edge in row['review_edges']:
        task=_task(root,project,payload['work_id'])[1]
        history=delivery._history(task,edge['event_id'])
        if not history:continue
        with delivery._event_lock(root,edge['event_id']),work.dispatch_lock(root):
            task=_task(root,project,payload['work_id'])[1];history=delivery._history(task,edge['event_id'])
            found=turn_admission.reused_turn(records.fold_records(root),{'request_id':edge['event_id'],'project':project,'mode':'review'})
            if found and not any(r.get('turn_id')==found['turn_id'] for r in history):
                work._append(root,delivery._admitted_row(history[0],history[-1].get('attempts',0),found['session_id'],found['turn_id'],reused=True,recovered=True))
        if found:
            try:turn_control.interrupt_turn(root,{'project':project,'turn_id':found['turn_id']})
            except ValueError:pass  # already settled is not another effect
    return {'effect':'route_cancelled','aggregate':aggregate(root,project,payload['work_id'],payload['route_id'])}


def compose_origin(root,project,origin_receipt,route_spec,*,door):
    """Only the trusted correction door calls this after the canonical Save lock releases."""
    if not isinstance(origin_receipt,dict) or not origin_receipt.get('origin_ref'):raise ValueError('Compose requires actual committed origin receipt.')
    payload=copy.deepcopy(route_spec);payload['origin']=origin_receipt['origin_ref'];payload['action']='route-submit'
    return handle(root,project,payload,door)


def handle(root,project,payload,door):
    action=payload.get('action')
    shared={'project','action','work_id'}
    fields={
      'policy-save':({'expected_work_revision','request_id','policy','policy_id','expected_policy_revision'},{'expected_work_revision','request_id','policy'}),
      'route-preview':({'origin','policy','policy_id','expected_policy_revision','recipients','request_id'},set()),
      'route-submit':({'expected_work_revision','request_id','origin','policy','policy_id','expected_policy_revision','recipients'}, {'expected_work_revision','request_id','origin'}),
      'route-status':({'route_id','request_id','policy_id','origin','request_kind','submission'},set()),
      'request-settle':({'request_kind','request_id','submission'},{'request_kind','request_id','submission'}),
      'route-recover':({'route_id'},{'route_id'}),'route-cancel':({'route_id'},{'route_id'})}
    if action not in fields:raise ValueError('Unknown feedback route action.')
    allowed,required=fields[action];_closed(payload,shared|allowed,{'action','work_id'}|required)
    if payload.get('project',project)!=project:raise ValueError('Route belongs to another project.')
    if action=='policy-save':return policy_save(root,project,payload,door)
    if action=='route-preview':return preview(root,project,payload,door)
    if action=='route-submit':return submit(root,project,payload,door)
    if action=='route-status':
        if 'submission' in payload and (not payload.get('request_id') or any(key in payload for key in ('route_id','policy_id','origin'))):
            raise ValueError('An original submission is compared only by its exact request_id.')
        return status(root,project,payload)
    if action=='request-settle':return settle(root,project,payload,door)
    if action=='route-recover':return recover(root,project,payload,door)
    return cancel(root,project,payload,door)
