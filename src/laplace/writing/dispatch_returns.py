"""Declared packet-return profiles and scoped publication over existing owners."""
from __future__ import annotations

import json


def profile(root, family):
    from laplace.work import project_work
    from laplace.pipeline import workflow
    registered=workflow.packet_schemas(project_work._dispatch_schema_directory(root))
    identity=max((key for key in registered if key.startswith(family)),key=lambda key:int(key.rsplit('/',1)[1]))
    return {'schema_id':identity,'schema':registered[identity][1]}


def publication(root, project, relative, *, document=None):
    from laplace.projects import artifacts
    observed=artifacts.read(root,project,{'path':relative,'scope':'project','limit':1})
    payload={'path':relative,'scope':'project','reason':'Retain the exact declared packet result.',
        **({'expected_revision':observed['revision']} if observed['exists'] else {'before':None})}
    if document is not None:payload['content']=json.dumps(document,ensure_ascii=False,indent=1)
    return {'operation':'store_artifact','project':project,'permitted':True,
        'scope':'exact-declared-packet-return','payload':payload,
        'read':{'operation':'read_artifact','payload':{'path':relative,'scope':'project'}},
        'requires':'Author the result using the supplied schema/scaffold; preserve this exact path, scope and current guard. This capability grants no other reviewer write.'}


def publication_projection(qualified):
    """One native call, with the owner's qualifications outside its envelope.

    Keep ``publication``/``child_permission`` facts intact for permission owners.
    This projection is presentation only and never grants caller authority.
    """
    return {'publish_action': {'operation': qualified['operation'], 'payload': qualified['payload']},
            'publication_context': {key: value for key, value in qualified.items()
                                    if key not in {'operation', 'payload'}}}


def owner_check(root, project, turn_id, *, paths=None):
    """Actual successful READ, independent of positive/negative result standing."""
    from laplace.writing import records
    from laplace.projects import artifacts
    idx=records.index(root)
    for row in reversed(idx.by_turn.get(turn_id,[])):
        if row.get('record')!='writing-tool-read' or row.get('operation')!='read_artifact':continue
        read=records.selected_journal_fields(project,row['id'],root,
            fields=['id','operation','payload','output_sha256'])
        if paths is not None:
            try:physical=artifacts.target(root,project,read['payload'],allow_read_only=True)[0]
            except (ValueError,OSError):continue
            if physical not in paths:continue
        return {'kind':'owner-read','state':'PASSED','operation':read['operation'],'payload':read['payload'],
            'receipt_id':read['id'],'output_sha256':read['output_sha256'],'ok':True,
            'output_tail':'This exact owner read completed successfully. The consulted evidence may establish a blocked or rejected result; read execution is not goal acceptance.'}
    return {'kind':'owner-read','state':'NOT_RUN','operation':'read_artifact','payload':{},
        'receipt_id':None,'output_sha256':None,'ok':None,
        'output_tail':'No exact artifact read has been consumed in this actor turn. Use required_reads, then refresh this owner contract.'}


def child_permission(root, project, session_id, dispatch_id, *, turn_id=None):
    from laplace.work import project_work
    from laplace.writing import records,dispatch_parent
    task=project_work._tasks(project,root).get(dispatch_id) or {}
    if not task.get('dispatch_admitted'):return None
    session=records.selected_journal_fields(project,session_id,root,fields=['id','role','dispatch_id','packet'])
    if session.get('role')!='review' or session.get('dispatch_id')!=dispatch_id:return None
    declared=dispatch_parent.plan(task,root)[1]
    item=next((item for item in declared['packets'] if item['packet']==session.get('packet') and item['role']=='judge'),None)
    if not item:return None
    from laplace.writing.dispatch_execution import continuation_for_session
    receipt=continuation_for_session(task,session_id)
    if item['packet'] in (task.get('dispatch_review_current') or {}) and not receipt:return None
    if receipt:
        if turn_id is not None:
            actor=records.selected_journal_fields(project,turn_id,root,fields=['id','session_id','dispatch_id','request_id','parent_turn_id'])
            if (actor.get('id')!=receipt['planned_turn_id'] or actor.get('session_id')!=session_id
                    or actor.get('dispatch_id')!=dispatch_id or actor.get('request_id')!=receipt['child_request_id']
                    or actor.get('parent_turn_id')!=receipt['parent_turn_id']):return None
            from laplace.writing import child_hosts
            execution=child_hosts.child_execution(root,session_id)
            if execution.get('turn_id')!=turn_id or execution.get('state')!='RUNNING':return None
        elif receipt['phase']!='LAUNCHING':return None
    result=publication(root,project,item['return_path'])
    if receipt:result.update(selected_turn_id=receipt['planned_turn_id'],admission_template=turn_id is None)
    return result


def validate_continuation_publication(root, project, path, content, turn_id):
    """Artifact owner calls this under its existing dispatch lock before any write."""
    from laplace.work import project_work
    from laplace.writing import dispatch_execution,dispatch_parent,records
    for task in project_work._tasks(project,root).values():
        if not task.get('dispatch_review_current'):continue
        for packet,request in task['dispatch_review_current'].items():
            receipt=task['dispatch_review_continuations'][request]
            relative=receipt['guard']['return']['artifact_path']
            if artifacts_path(root,project,relative)!=path:continue
            declared=dispatch_parent.plan(task,root)[1]
            packets={row['packet']:row for row in declared['packets']}
            item=packets[packet]
            if artifacts_path(root,project,item['return_path'])!=path:raise ValueError('The declared continuation path changed.')
            if not turn_id or turn_id!=receipt['planned_turn_id']:
                raise ValueError('Only the selected continuation attempt may publish this return.')
            if not child_permission(root,project,receipt['session_id'],task['id'],turn_id=turn_id):
                raise ValueError('The selected continuation turn is not admitted.')
            dispatch_execution.guard_continuation_inputs(root,project,task,receipt)
            current=dispatch_execution._artifact_pin(root,project,item['return_path'])
            prior=receipt['guard']['return']
            if current!=prior:
                latest=records.selected_journal_fields(project,current['id'],root,fields=['id','turn_id']) if current.get('id') else {}
                if not latest or latest.get('turn_id')!=turn_id:
                    raise ValueError('The guarded prior return changed outside this attempt.')
            try:document=json.loads(content)
            except ValueError as error:raise ValueError('Continuation return must be its valid typed document.') from error
            errors=project_work._dispatch_return_errors(document,item,packets,root=root,project=project,
                session_id=receipt['session_id'],dispatch_id=task['id'],turn_id=turn_id)
            if errors:raise ValueError('Continuation return refused: '+'; '.join(errors))


def reserved_child_return(root, project, path):
    """(dispatch task, packet) when ``path`` is an admitted child's reserved return path, else None.

    The reservation is the exact admission receipt (``dispatch_return_reservations``, recorded beside the admitted plan
    hash), never whatever later bytes sit at the plan path. Dispatches admitted before that receipt keep their historical
    read-side validation only; nothing is retrofitted.
    """
    from laplace.work import project_work
    for task in project_work._tasks(project,root).values():
        reserved=task.get('dispatch_return_reservations')
        if task.get('task_kind')!='dispatch' or not task.get('dispatch_admitted') or not isinstance(reserved,dict):continue
        for packet,relative in reserved.items():
            if (root/str(relative)).resolve()==path:return task,str(packet)
    return None


def return_coordinates(task, packet, item):
    """The exact declared coordinates a refused or correcting child needs, from the admitted plan row."""
    declared=(item or {}).get('output')
    output=declared.get('path') if isinstance(declared,dict) else declared
    return {'dispatch_id':task.get('id'),'packet':packet,'return_path':(item or {}).get('return_path'),
            'declared_output':output or None,'contract_read':{'operation':'session_settings','payload':{'view':'return-schema'}}}


def _refusal_field(error):
    text=str(error);head=text.split(':',1)[0]
    return head if ':' in text and head and ' ' not in head else 'document'


def validate_child_publication(root, project, path, content, turn_id):
    """The Artifact owner's prewrite guard for an admitted child's reserved typed return.

    Called under the existing dispatch lock before any journal entry, directory or file. Only the admitted child turn of
    that packet may publish there, and only a document the shared Work validator accepts: honest incomplete or blocked
    returns and negative judgements remain valid documents. A refusal writes nothing, names the failing field and the
    exact declared coordinates, and the same live child may correct and store again. Every other path is untouched.
    """
    found=reserved_child_return(root,project,path)
    if found is None:return
    task,packet=found
    if packet in (task.get('dispatch_review_current') or {}):return   # validate_continuation_publication owns this path
    from laplace.work import project_work
    from laplace.writing import dispatch_parent,records
    _plan_path,declared,revision=dispatch_parent.plan(task,root)
    packets={str(row.get('packet')):row for row in declared.get('packets') or []}
    item=packets.get(packet)
    coordinates=return_coordinates(task,packet,item)
    def refuse(field,reason,recovery=None):
        raise ValueError('Typed return refused before publication; nothing was written. Field: %s. %s. Declared coordinates: %s. %s'
                         % (field,reason,json.dumps(coordinates,sort_keys=True),recovery or
                            'Read the current return contract (session_settings {"view": "return-schema"}), correct the document '
                            'and store it again at return_path in this same turn.'))
    if item is None or revision.removeprefix('sha256:')!=str(task.get('dispatch_plan_sha256') or '').removeprefix('sha256:'):
        refuse('plan','the admitted dispatch plan changed, so its reserved return cannot be transferred by drift')
    def fields(ident,names):
        try:return records.selected_journal_fields(project,ident,root,fields=names) if ident else {}
        except (ValueError,KeyError,OSError):return {}
    actor=fields(turn_id,['id','project','session_id','dispatch_id','parent_turn_id'])
    session=fields(actor.get('session_id'),['id','packet','dispatch_id'])
    # Authority is the exact admitted child turn while it is live: the turn the dispatch owner banked with this dispatch and
    # parent, in the child session of this packet, whose session execution record is RUNNING for that same turn, dispatch
    # and parent. A later ordinary turn of the same session, or the settled or displaced child turn, holds no such record,
    # whatever its Artifact guard or content. Explicit guarded recovery is owned by the continuation branch above.
    from laplace.writing import child_hosts
    # one validated execution projection supplies both the observed identity and its liveness, from one generation
    try:execution=child_hosts.child_execution(root,actor['session_id']) if actor.get('session_id') else {}
    except (ValueError,OSError):execution={}
    admitted_parent=task.get('dispatch_parent_turn_id')
    if (not turn_id or actor.get('id')!=turn_id or actor.get('project')!=project or actor.get('dispatch_id')!=task.get('id')
            or not actor.get('parent_turn_id') or (admitted_parent and actor.get('parent_turn_id')!=admitted_parent)
            or session.get('dispatch_id')!=task.get('id') or session.get('packet')!=packet
            or execution.get('turn_id')!=turn_id or execution.get('state')!='RUNNING' or execution.get('project')!=project
            or execution.get('dispatch_id')!=task.get('id') or execution.get('parent_turn_id')!=actor.get('parent_turn_id')):
        refuse('actor','only the admitted live child turn of packet %s in dispatch %s may publish at this reserved path; '
               'a later, settled or displaced turn of the same session cannot replace it' % (packet,task.get('id')),
               'This turn cannot correct the reserved return. For a new attempt use the dispatch\'s guarded continuation; '
               'otherwise store this result at an ordinary unreserved artifact path.')
    try:document=json.loads(content)
    except (TypeError,ValueError):refuse('document','the content is not one JSON typed document')
    errors=project_work._dispatch_return_errors(document,item,packets,root=root,project=project,
        session_id=actor['session_id'],dispatch_id=task['id'],turn_id=turn_id)
    if errors and isinstance(document,dict) and str(document.get('schema_version') or '').endswith('/1'):
        # Legacy /1 self-output: this proposed publication IS the claimed output, so it cannot exist before the write.
        output=document.get('output');output=output.get('path') if isinstance(output,dict) else output
        try:own=bool(output) and project_work._dispatch_pin_path(root,project,output,artifact_only=True)==path
        except (OSError,ValueError):own=False
        if own:errors=[error for error in errors if error!='output: claimed report artifact is missing']
    if errors:refuse(_refusal_field(errors[0]),'; '.join(errors)[:1500])


def artifacts_path(root, project, relative):
    from laplace.projects import artifacts
    return artifacts.resolve_path(root,project,relative)


REVIEW_PERMISSION={
    'operation':'store_artifact','condition':'Only an actual admitted dispatch judge may publish at its own exact declared project return_path.',
    'scope':'exact-declared-packet-return','discovery':{'operation':'session_settings','payload':{}},
    'otherwise':'Ordinary independent review cannot store arbitrary artifacts or modify reviewed source.'}


def child_diagnostics(root, project, child):
    from laplace.writing import records
    from urllib.parse import urlencode
    failures=[row for row in records.index(root).by_turn.get(child.get('turn_id'),[])
        if row.get('record')=='writing-tool-failure']
    value={'failure_count':len(failures)}
    if child.get('state')=='NO-RETURN':value['failure_summary']='The child ended without its declared typed return; inspect its exact saved turn and publication contract.'
    elif failures:value['failure_summary']=str(len(failures))+' recorded tool failure(s); inspect the exact child failure receipts.'
    if failures:
        selected=records.selected_journal_fields(project,failures[-1]['id'],root,fields=['operation','error'])
        value['failure_summary']=(str(selected.get('operation') or 'tool')+': '+str(selected.get('error') or 'Recorded operation failed.'))[:500]
    if child.get('state')=='NO-RETURN':
        replies=[row for row in records.index(root).by_turn.get(child.get('turn_id'),[]) if row.get('record')=='writing-reply']
        if replies:
            selected=records.selected_journal_fields(project,replies[-1]['id'],root,fields=['text','display_text'])
            excerpt=selected.get('display_text') or selected.get('text')
            if isinstance(excerpt,str) and excerpt:value['reply_excerpt']=excerpt[:500]
    if child.get('turn_id'):value['publication_read']={'http':{'method':'GET','url':'/authoring/help?'+urlencode({
        'project':project,'turn_id':child['turn_id'],'operation':'store_artifact'})}}
    return value


# ---------------------------------------------------------------- the returns projection
# One pure envelope for actual return consumption and exact receipt checks (moved from the gateway, family 2).

def dispatch_returns_projection(root, project, ident, plan, payload, *, read=None):
    """One pure envelope for actual return consumption and exact receipt checks."""
    from laplace.projects import artifacts
    read=read or (lambda values:artifacts.read(root,project,values))
    packets={str(item['packet']):item for item in plan['packets']}
    wanted=payload.get('packet');labels=[wanted] if wanted else sorted(packets)
    results=[]
    for label in labels:
        item=packets[label];relative=item['return_path']
        returned=read({'path':relative,'scope':'project',
            **{key:payload[key] for key in ('offset','limit') if key in payload}})
        results.append({'packet':label,'role':item['role'],'return_path':relative,'return':returned})
    return {'dispatch_id':ident,'returns':results,
        'validated_by':'scripts/distil.py check-return against profiles/workflows/packet-return.schema.json and packet-judgement.schema.json; its exit code is the dispatch row\'s evidence'}
