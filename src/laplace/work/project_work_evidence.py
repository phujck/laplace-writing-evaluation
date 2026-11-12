"""Selected Work provenance and explicitly retained support, over existing owners.

This read composes recorded identities, never guesses missing bindings or crawls
JSON for paths. A support manifest is an explicitly selected Artifact, not a store.
"""
from __future__ import annotations
import copy
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlencode

SCHEMA='laplace.work-provenance/1'
SUPPORT_SCHEMA='laplace.work-evidence-support/1'
PIN='^(?:sha256:)?[0-9a-f]{64}$'

def contract():
    return {'type':'object','properties':{
        'demand':{'enum':['aggregate','relationships','evidence','choices']},
        'offset':{'type':'integer','minimum':0},
        'limit':{'type':'integer','minimum':1,'maximum':24},
        'as_of':{'type':'string','pattern':'^sha256:[0-9a-f]{64}$'}},'additionalProperties':False}

def artifact_reference_contract():
    return {'type':'object','properties':{'id':{'type':'string','pattern':'^ART-[A-Za-z0-9-]+$'},
        'path':{'type':'string','minLength':1},'scope':{'enum':['project','manuscript']},
        'expected_sha256':{'type':'string','pattern':PIN}},'required':['expected_sha256'],
        'oneOf':[{'required':['id'],'not':{'anyOf':[{'required':['path']},{'required':['scope']}]}},
                 {'required':['path','scope'],'not':{'required':['id']}}], 'additionalProperties':False}

def support_contract():
    artifact=artifact_reference_contract()
    run={'type':'object','properties':{'id':{'type':'string','minLength':1},
        'expected_sha256':{'type':'string','pattern':PIN}},'required':['id','expected_sha256'],'additionalProperties':False}
    return {'type':'object','properties':{'schema_version':{'const':SUPPORT_SCHEMA},
        'work':{'type':'object','properties':{'namespace':{'type':'string','minLength':1},'id':{'type':'string','minLength':1},
            'scope_revision':{'type':'string','pattern':'^sha256:[0-9a-f]{64}$'}},'required':['namespace','id','scope_revision'],'additionalProperties':False},
        'items':{'type':'array','items':{'type':'object','properties':{'id':{'type':'string','minLength':1,'maxLength':160},
            'required':{'type':'boolean'},'role':{'type':'string','minLength':1,'maxLength':160},
            'retention':{'enum':['retained','disposable-scratch']},'owner':{'enum':['project-artifact','research-run-output']},'reference':{'type':'object'}},
            'required':['id','required','role','retention','owner','reference'],'additionalProperties':False,
            'allOf':[{'if':{'properties':{'owner':{'const':'project-artifact'}}},'then':{'properties':{'reference':artifact}}},
                     {'if':{'properties':{'owner':{'const':'research-run-output'}}},'then':{'properties':{'reference':run}}}]}}},
        'required':['schema_version','work','items'],'additionalProperties':False}

def handle(project,ident,request=None):
    from laplace.work.project_work_views import handle as h
    return h(project,{'view':'provenance','id':ident,'request':dict(request or {'demand':'aggregate'})})

def _digest(value):
    return 'sha256:'+hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def _validate(schema,value):
    from jsonschema import Draft202012Validator
    error=next(Draft202012Validator(schema).iter_errors(value),None)
    if error:raise ValueError('Evidence request does not match its closed owner contract: '+error.message[:400])

def _admit(scope,project):
    from laplace.work.owner_discovery import Scope
    if not isinstance(scope,Scope) or not scope.admits(project):raise ValueError('Evidence is outside the actual caller scope.')

def _artifact(root,project,reference,*,verify=False,context=None):
    from laplace.projects import artifacts
    from laplace.work import project_work as W
    descriptor,target=artifacts.evidence_descriptor(root,project,reference)
    stamp=W._stamp(target)
    value={'reference':copy.deepcopy(reference),'owner':'project-artifact',**descriptor,
        'availability':'PRESENT' if stamp else 'MISSING','integrity':'NOT_CHECKED','observed_sha256':None}
    if verify and stamp:
        observed=W._evidence_digest(target,context)
        value.update(observed_sha256=observed,integrity='VERIFIED' if observed==descriptor['expected_sha256'] else 'MISMATCH',
                     availability='PRESENT' if observed==descriptor['expected_sha256'] else 'CHANGED')
    if not stamp:value['read']=None
    return value,stamp

def _run(root,project,reference):
    from laplace.research import research_runs
    code,run=research_runs.run_status_read(project,reference['id'],root)
    observed=(run.get('result_provenance') or {}).get('sha256') if isinstance(run,dict) else None
    expected=reference['expected_sha256'].removeprefix('sha256:')
    value={'owner':'research-run-output','reference':copy.deepcopy(reference),
        'availability':'PRESENT' if code==200 and run.get('state')=='COMPLETE' and observed==expected else
            'CHANGED' if code==200 and observed and observed!=expected else 'UNAVAILABLE',
        'integrity':'VERIFIED' if code==200 and run.get('state')=='COMPLETE' and observed==expected else 'UNKNOWN',
        'observed_sha256':observed,'run_state':run.get('state') if isinstance(run,dict) else 'UNKNOWN',
        'read':{'operation':'run_status','payload':{'id':reference['id']},'http':{'method':'GET','url':'/research/run/status?'+urlencode({'project':project,'id':reference['id']})}}}
    return value,_digest({k:v for k,v in value.items() if k!='read'})

def _no_duplicates(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Evidence manifest contains duplicate object keys.')
        result[key]=value
    return result

def _manifest(root,project,ident,reference):
    from laplace.projects import artifacts
    _validate(artifact_reference_contract(),reference)
    descriptor,target=artifacts.evidence_descriptor(root,project,reference)
    if not target.is_file():raise ValueError('Declared support manifest is missing.')
    if target.stat().st_size>artifacts._ARTIFACT_TEXT_MAX:raise ValueError('Support manifest exceeds the existing Artifact text budget.')
    with target.open('rb') as stream:raw=stream.read(artifacts._ARTIFACT_TEXT_MAX+1)
    if len(raw)>artifacts._ARTIFACT_TEXT_MAX:raise ValueError('Support manifest exceeds the existing Artifact text budget.')
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=descriptor['expected_sha256']:raise ValueError('Declared support manifest changed; original support was not substituted.')
    value=json.loads(raw,object_pairs_hook=_no_duplicates)
    _validate(support_contract(),value)
    if value['work']['namespace']!=project or value['work']['id']!=ident:
        raise ValueError('Support manifest belongs to another Work.')
    ids=[row['id'] for row in value['items']]
    if len(ids)!=len(set(ids)):raise ValueError('Support manifest item identities are ambiguous.')
    for row in value['items']:
        if row['required'] and row['retention']!='retained':raise ValueError('Disposable scratch cannot be required retained support.')
    return value,descriptor,digest

def support_observation(root,scope,project,task,*,verify=False,context=None,require_current=False):
    """Observe only explicitly declared support, never report prose or arbitrary paths."""
    _admit(scope,project)
    saved=task.get('completion_support')
    if not saved:return {'state':'NOT_DECLARED','items':[],'required':0,'verified_required':0},None
    reference=saved.get('reference')
    try:
        manifest,read,digest=_manifest(root,project,task['id'],reference)
        if require_current and manifest['work']['scope_revision']!=task['work_scope_revision']:
            raise ValueError('Support manifest consumes a different current Work scope.')
        items=[];basis=[]
        for row in manifest['items']:
            try:
                if row['owner']=='project-artifact':observed,stamp=_artifact(root,project,row['reference'],verify=verify,context=context)
                else:observed,stamp=_run(root,project,row['reference'])
            except (OSError,ValueError) as e:
                observed={'availability':'UNAVAILABLE','integrity':'UNKNOWN','reason':str(e),'read':None};stamp=None
            items.append({**copy.deepcopy(row),**observed});basis.append((row['id'],stamp))
        required=[row for row in items if row['required']]
        return {'state':'OBSERVED','reference':copy.deepcopy(reference),'manifest_read':read['read'],
            'manifest_revision':digest,'consumed_scope_revision':manifest['work']['scope_revision'],
            'required':len(required),'verified_required':sum(row['integrity']=='VERIFIED' for row in required) if verify else None,
            'verification_scope':'ALL_REQUIRED' if verify else 'SELECTED_PAGE_ONLY',
            'items':items,'qualification':'Declared support only; source/producer currentness and historical acceptance remain separate.'},basis
    except (OSError,ValueError,TypeError) as e:
        return {'state':'UNAVAILABLE','reference':copy.deepcopy(reference),'items':[],'required':None,
                'verified_required':0,'reason':str(e)},None

def prepare_completion_support(root,project,task,reference):
    """Within the existing guarded transition/lock; no independent write or ledger."""
    from laplace.work.owner_discovery import project_scope
    # The transition owner already admitted the human/native mutation. This is
    # a private composition scope, never a caller payload permission carrier.
    candidate={**task,'completion_support':{'reference':reference}}
    observation,_=support_observation(root,project_scope(project,'completion-owner'),project,candidate,verify=True,context={},require_current=True)
    if observation['state']!='OBSERVED' or observation['verified_required']!=observation['required']:
        raise ValueError('Completion requires retained, verified declared support: '+str(observation.get('reason') or [r['id'] for r in observation['items'] if r['required'] and r['integrity']!='VERIFIED']))
    return {'reference':copy.deepcopy(reference),'manifest_revision':observation['manifest_revision'],
            'consumed_scope_revision':observation['consumed_scope_revision'],'required':observation['required']}

def _captured(root,project,ident):
    from laplace.work import project_work as W
    from laplace.writing import records
    task=W._tasks(project,root).get(ident)
    if task is None:raise ValueError('Exact Work is unavailable in the admitted namespace.')
    with records.index_lock:
        idx=records.index(root)
        # Only index headers, never rich turn/action/reply or artifact bodies.
        selected=[r for r in idx.by_project.get(project,()) if r.get('record')=='writing-turn' and r.get('work_id')==ident]
        turns=[];issues=[]
        for row in selected:
            sessions=idx.by_id.get(row.get('session_id'),())
            if len(idx.by_id.get(row['id'],()))!=1 or len(sessions)!=1 or sessions[0].get('record')!='writing-session' or idx.project(sessions[0])!=project:
                issues.append({'kind':'AMBIGUOUS_OR_FOREIGN_TURN','id':row['id']});continue
            item=copy.deepcopy(row)
            item['_session_hash']=sessions[0].get('_hash')
            item['_session_title']=sessions[0].get('title')
            replies=[v for v in idx.by_turn.get(row['id'],()) if v.get('record')=='writing-reply']
            item['_reply_basis']=[(v.get('id'),v.get('_hash')) for v in replies]
            item['_reply_state']='ABSENT' if not replies else 'RECORDED' if len(replies)==1 and idx.project(replies[0])==project and len(idx.by_id.get(replies[0].get('id'),()))==1 else 'UNAVAILABLE'
            turns.append(item)
        turn_ids={r['id'] for r in turns}
        artifacts=[copy.deepcopy(r) for r in idx.by_project.get(project,()) if r.get('record')=='writing-artifact' and r.get('turn_id') in turn_ids]
        artifacts=[r for r in artifacts if sum(v.get('record')=='writing-artifact' and v.get('project')==project for v in idx.by_id.get(r['id'],()))==1]
        coverage={'talk_source_status':idx.source_status,'malformed_rows':idx.malformed_rows,'identity_issues':issues,
                  'body_reads':0,'body_reads_scope':'Relationship index headers only; evidence demand separately hashes declared bytes.','scope':'Exact recorded Work binding; unbound sessions and contained Work are not inferred.'}
    refs=[('conversation-turn',r) for r in turns]+[('artifact-receipt',r) for r in artifacts]
    for phase in task.get('phases') or ():
        refs.append(('review-phase',phase))
        if phase.get('source_basis') is not None:refs.append(('source-basis',phase))
    for path in task.get('evidence') or ():refs.append(('associated-evidence',path))
    seen=set()
    for event in task.get('deliveries') or ():
        if event.get('kind')=='work-delivery' and event.get('id') not in seen:
            refs.append(('delivery-event',event));seen.add(event['id'])
    token=_digest({'namespace':project,'work':ident,'specification':W._task_revision(task),
        'standing':W._standing_revision(task),'metadata':[(r.get('id'),r.get('_hash')) for r in turns+artifacts],
        'reply_and_session_metadata':[(r['id'],r['_session_hash'],r['_reply_basis']) for r in turns],
        'phases':task.get('phases') or (),'deliveries':task.get('deliveries') or (),
        'evidence':task.get('evidence') or [],'completion_support':task.get('completion_support'),'coverage':coverage})
    return task,refs,token,coverage

def _relation(root,project,task,kind,value,context):
    from laplace.work import project_work_views as V,project_work_review as R
    from laplace.projects import artifacts
    if kind=='conversation-turn':
        from laplace.writing.session_reads import _message_handle
        target={'project':project,'session_id':value['session_id'],'turn_id':value['id']}
        request={**target,'part':'reply','limit':4000}
        read={'operation':'author_history','payload':{'view':'record','id':'activity:journal:'+value['id']},
            'http':{'method':'GET','url':'/authoring/session-turn?'+urlencode({'project':project,'id':value['id'],'view':'summary'})}}
        return {'kind':kind,'state':'RECORDED','label':value.get('_session_title') or 'Conversation response',
            'label_complete':len(value.get('_session_title') or '')<200,'label_origin':'session-title' if value.get('_session_title') else 'plain',
            'session_title':value.get('_session_title'),'session_title_complete':len(value.get('_session_title') or '')<200,
            'request_preview_state':'NOT_CAPTURED_IN_METADATA','target':target,
            'recorded_at':value.get('ts'),'relation_basis':'Exact saved turn.work_id; not a live execution observation',
            'read':read,'reply_state':value['_reply_state'],'reply_read':_message_handle(request,offset=0) if value['_reply_state']!='UNAVAILABLE' else None,
            'conversation_read':{'http':{'method':'GET','url':'/authoring/session?'+urlencode({'project':project,'id':value['session_id'],'view':'summary','limit':20})}}}
    if kind=='artifact-receipt':
        reference={'id':value['id'],'expected_sha256':value.get('sha256','')}
        descriptor,_=artifacts.evidence_descriptor(root,project,reference)
        return {'kind':kind,'state':'RECORDED','label':Path(descriptor['path']).name,'label_origin':'recorded-artifact-path','label_complete':True,'recorded_at':value.get('ts'),
            'target':{'project':project,'artifact_id':value['id'],'turn_id':value['turn_id']},
            'relation_basis':'Exact saved artifact receipt.turn_id; open the turn to inspect its store-action linkage',**descriptor}
    if kind in {'review-phase','source-basis'}:
        return {'kind':kind,'state':'RECORDED','label':'Recorded '+('Source basis' if kind=='source-basis' else str(value.get('phase') or 'review phase')),
            'target':{'project':project,'work_id':task['id'],'phase_id':value['id']},
            'recorded_at':value.get('ts'),'relation_basis':'Exact phase attached to this Work; acceptance is interpreted by the review owner',
            'read':R.phase_read(task,root,value['id'],project=project,read_context=context)}
    if kind=='delivery-event':
        request={'action':'status','event_id':value['id']}
        return {'kind':kind,'state':'RECORDED','label':'Recorded recipient delivery',
            'target':{'project':project,'work_id':task['id'],'event_id':value['id']},
            'relation_basis':'Actual Work delivery event; no live or distributed software publication is inferred',
            'read':{'operation':'work_delivery','payload':request,'http':{'method':'GET','url':'/work/delivery?'+urlencode({'project':project,'request':json.dumps(request,separators=(',',':'))})}}}
    receipts=[r for r in task.get('evidence_receipts') or [] if r.get('path')==value]
    descriptor=V._evidence_reads({'evidence':[value],'evidence_receipts':receipts},project,root,read_context=context)[0]
    read={key:descriptor[key] for key in ('operation','payload','http') if key in descriptor}
    owner_target=descriptor.get('owner_target');current_read=None
    if owner_target and owner_target['kind']=='material-source' and descriptor.get('consumed_revision'):
        from laplace.projects.library import material_read_handle
        current_read=copy.deepcopy(read)
        read=material_read_handle(project,{**descriptor['payload'],'expected_sha256':descriptor['consumed_revision']})
    return {'kind':'associated-evidence','state':'ASSOCIATED' if read else 'UNAVAILABLE','label':'Declared completion evidence',
        'target':{'project':project,'path':value},'relation_basis':'Explicit Work evidence association; report contents are not automatically typed relationships',
        'read':read or None,'current_read':current_read,'owner_target':copy.deepcopy(owner_target),'consumed_revision':descriptor.get('consumed_revision'),
        'qualification':descriptor.get('capability_gap') or 'Reader availability is not a transitive supporting-evidence check.'}

def _choices(root,project):
    from laplace.projects import artifacts
    from laplace.writing import records
    with records.index_lock:
        idx=records.index(root)
        rows=[copy.deepcopy(r) for r in idx.by_project.get(project,()) if r.get('record')=='writing-artifact']
        ambiguous=[r['id'] for r in rows if sum(v.get('record')=='writing-artifact' and v.get('project')==project for v in idx.by_id.get(r.get('id'),()))!=1]
        rows=[r for r in rows if r['id'] not in ambiguous]
    items=[];basis=[];issues=[{'owner':'project-artifact','id':ident,'reason':'Ambiguous recorded artifact identity.'} for ident in sorted(set(ambiguous))]
    for row in rows:
        try:
            reference={'id':row['id'],'expected_sha256':row.get('sha256','')}
            descriptor,target=artifacts.evidence_descriptor(root,project,reference)
            relative=target.relative_to(root).as_posix()
            if not target.is_file():continue
            # A candidate is a saved owner item, not a fresh byte verification.
            items.append({'id':row['id'],'label':(row.get('original_metadata') or {}).get('display_name') or target.name,
                'owner':'project-artifact','state':'OFFERED','evidence_value':relative,'completion_support':reference,
                'support_reference_owner':'project-artifact','support_manifest_qualification':'Choose as support only when its contents have the declared support schema.',
                'recorded_revision':row.get('sha256'),'read':descriptor['read'],'currentness':'NOT_CHECKED'})
            from laplace.work.project_work import _stamp
            basis.append((row['id'],row.get('_hash'),_stamp(target)))
        except (OSError,ValueError) as error:issues.append({'owner':'project-artifact','id':row['id'],'reason':str(error)[:240]})
    from laplace.manuscript import manuscript_source
    try:
        writing=manuscript_source.declared_evidence_choices(project,root)
        items.extend(writing['items']);basis.append(('manuscript-source',writing))
        if writing.get('coverage')=='UNAVAILABLE':issues.append({'owner':'manuscript-source','reason':writing.get('reason','Declared Writing source unavailable')})
    except (OSError,ValueError) as error:issues.append({'owner':'manuscript-source','reason':str(error)[:240]})
    from laplace.research import research_runs
    try:
        runs=research_runs.evidence_candidates(root,project)
        items.extend(runs['items']);basis.append(('research-run-output',runs));issues.extend(runs.get('issues',[]))
        if runs.get('coverage')=='UNAVAILABLE':issues.append({'owner':'research-run-output','reason':runs.get('reason','Run metadata unavailable')})
    except (OSError,ValueError) as error:
        basis.append(('research-run-output-unavailable',str(error)));issues.append({'owner':'research-run-output','reason':str(error)[:240]})
    return items,{'observed':basis,'gaps':issues}

def read(root,scope,project,ident,request):
    from laplace.work import project_work as W,project_work_navigation as N,review_evidence
    _admit(scope,project);_validate(contract(),request)
    root=Path(root).resolve();context={};task,refs,token,coverage=_captured(root,project,ident)
    demand=request.get('demand','aggregate');offset=request.get('offset',0);limit=request.get('limit',6)
    all_items=None;support=None;standing=None
    if demand=='evidence':
        standing=W._completion_currentness(task,root,digests=context,tasks=W._tasks(project,root)) if task.get('status') in {'done','verified'} else {'status':'NOT_COMPLETED'}
        support,support_basis=support_observation(root,scope,project,task,context=context)
        # The whole selected declared support metadata is observed for stable pages;
        # hashes are requested only for the selected page below.
        direct=[];stamps=[]
        for path in task.get('evidence') or ():
            raw=Path(path);target=(root/raw).resolve()
            if raw.is_absolute() or '..' in raw.parts or not target.is_relative_to(root):continue
            stamps.append((path,W._stamp(target)))
            direct.append({**_relation(root,project,task,'associated-evidence',path,context),'kind':'direct-completion-evidence'})
        all_items=direct+[{**row,'kind':'declared-support'} for row in support['items']]
        token=_digest({'metadata':token,'support':{k:v for k,v in support.items() if k!='items'},'support_observations':support_basis,'direct_stamps':stamps,'direct_standing':standing})
    elif demand=='choices':
        all_items,choice_basis=_choices(root,project);token=_digest({'metadata':token,'choices':choice_basis})
        coverage['evidence_choices']={'status':'PARTIAL' if choice_basis['gaps'] else 'OBSERVED','gaps':choice_basis['gaps'],
            'qualification':'Recorded project artifacts, declared Writing root and run index only; unrecorded files, source trees and unindexed legacy runs are not enumerated.'}
    base={'schema_version':SCHEMA,'read_only':True,'work':{'namespace':project,'id':ident,'title':task.get('title','')[:200],
        'title_complete':len(task.get('title',''))<=200,'purpose':task.get('goal','')[:320],'purpose_complete':len(task.get('goal',''))<=320,'recorded_status':task.get('status'),
        'detail_read':__import__('laplace.work.project_work_views',fromlist=['handle']).handle(project,{'view':'detail','id':ident})},
        'caller_scope':scope.public(),'observation':{'token':token,'qualification':'Selected owner facts, not an atomic filesystem snapshot.'},
        'counts':{'relationships':len(refs),'direct_evidence':len(task.get('evidence') or ()),'bound_turns':sum(k=='conversation-turn' for k,v in refs)},
        'coverage':coverage,'support':{'state':'DECLARED' if task.get('completion_support') else 'NOT_DECLARED'},
        'reads':{'relationships':handle(project,ident,{'demand':'relationships','as_of':token}) if demand=='aggregate' else handle(project,ident,{'demand':'relationships'}),
                 'evidence':handle(project,ident,{'demand':'evidence'}),'choices':handle(project,ident,{'demand':'choices'}),
                 'review':review_evidence.handle(project,ident)},
        'restart_read':handle(project,ident,{'demand':demand}),
        'inspection':{'metadata':'AGGREGATE_ONLY' if demand=='aggregate' else 'SELECTED_PAGE','bodies':'NOT_READ'},
        'qualification':'Recorded, associated and unavailable remain distinct. No unbound session, review acceptance, live version or release is inferred.'}
    if request.get('as_of') and request['as_of']!=token:
        e=W.WorkConflict('Selected provenance inputs changed; pages were not mixed.',project,ident,expected=request['as_of'],observed=token)
        e.details.update(kind='CHANGED_INPUT',restart_read=base['restart_read'],next_reads=[base['restart_read']]);raise e
    if demand=='aggregate':return _fit(base)
    if demand=='evidence':
        base['direct_completion']=standing;base['support']={k:v for k,v in support.items() if k!='items'}
        base['inspection']['bodies']='EVIDENCE_BYTES_HASHED_NOT_RETURNED'
    count=len(refs) if demand=='relationships' else len(all_items)
    if offset>count:raise ValueError('Page offset exceeds the selected owner observation.')
    items=[];covered=0
    for position in range(offset,min(count,offset+limit)):
        try:
            if demand=='relationships':item=_relation(root,project,task,*refs[position],context)
            else:
                item=copy.deepcopy(all_items[position])
                if demand=='evidence' and item.get('kind')=='declared-support' and item.get('owner')=='project-artifact':
                    observed,_=_artifact(root,project,item['reference'],verify=True,context=context);item.update(observed)
        except (OSError,ValueError) as e:item={'state':'UNAVAILABLE','reason':str(e),'read':None,'position':position}
        tentative={**base,'items':items+[item],'pagination':{'total':count,'offset':offset,'limit':limit,'covered':covered+1,'next_read':handle(project,ident,{'demand':demand,'offset':position+1,'limit':limit,'as_of':token})}}
        if N.emitted(tentative)>N.line():
            if items:break
            item={'state':'OVERSIZED','position':position,'qualification':'Use the selected Work full owner read. No body or relationship was silently treated as absent.'}
        items.append(item);covered+=1
    next_offset=offset+covered
    base.update(items=items,pagination={'total':count,'offset':offset,'limit':limit,'covered':covered,
        'next_read':handle(project,ident,{'demand':demand,'offset':next_offset,'limit':limit,'as_of':token}) if next_offset<count else None})
    return _fit(base)

def _fit(value):
    from laplace.work import project_work_navigation as N
    if N.emitted(value)>N.line():raise ValueError('Provenance exceeds the existing Work delivery line; use the exact full Work read.')
    return value
