"""Existing author-update and turn-input owners joined at project tool results."""
from __future__ import annotations

from laplace.core import bodies as core_bodies
from laplace.writing import records as writing_records
from laplace.representation import writing_bodies as bodies
import copy,threading
from pathlib import Path

_PATHS={}
_LOCK=threading.RLock()


def _mark(path):
    try:
        stat=path.stat();return (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
    except FileNotFoundError:return None


def correction_snapshot(root,project):
    """Existing correction metadata cache; unchanged boundaries resolve no bodies."""
    from laplace.pipeline import authoring,registry
    root=Path(root).resolve();key=(str(root),project)
    with _LOCK:
        saved=_PATHS.get(key)
        watched=[root/'registry_projects.json',root/'project_manifests.json']
        if saved:watched.extend(saved[2])
        signature=tuple(_mark(path) for path in watched)
        if saved is None or saved[0]!=signature:
            path,source=authoring._state_path(project,root)
            directories={path.parent}
            if source.get('manuscript_dir'):directories.add((root/source['manuscript_dir']).resolve())
            extra=sorted(directories)
            signature=tuple(_mark(path) for path in [*watched[:2],*extra])
            saved=(signature,(path,source),extra);_PATHS[key]=saved
        return authoring._history_snapshot(project,root,path_source=saved[1])


def turn_scope(root,project,turn_id):
    from laplace.writing.records import index as index, index_lock as index_lock
    with index_lock:
        idx=index(root);turn=idx.turns.get(turn_id)
        if not turn or idx.project(turn)!=project:return None
        result=copy.deepcopy(turn)
        for row in idx.by_turn.get(turn_id,[]):
            if row['record']=='writing-turn-context-baseline':
                result.update({key:copy.deepcopy(row[key]) for key in ('selection','consumed_correction_ids','workspace_context') if key in row})
        result['author_update_acks']={row['correction_id']:row for row in idx.by_turn.get(turn_id,[])
            if row['record']=='writing-author-update-ack' and row.get('correction_id') and row.get('status')=='EXACT_SCOPED_AUTHOR_HISTORY_READ'}
        result['author_update_deliveries']=[copy.deepcopy(row) for row in idx.by_turn.get(turn_id,[]) if row['record']=='writing-author-update-delivery']
        return result


def _read_handle(project,operation,payload):
    from laplace.native.verbs import native_example
    proof=native_example(operation,payload,project=project)
    return {'operation':operation,'payload':payload,
        **({'native_request':proof['native_request']} if proof.get('available') else {})}


def author_offer(root,project,turn_id,*,bank=True,eligible=None):
    """The author-update offer of this tool boundary. ``bank=False`` computes the same offer without banking its
    OFFERED row: the shared delivery plan's question of how much room the offer will need. ``eligible`` (an iterable of
    correction ids) is THE CUT that plan fixed: only those corrections are offered and banked by this delivery; a
    correction admitted after the plan stays pending, unoffered and unacknowledged, for the next boundary
    (writing.delivery, steps 2-3)."""
    from laplace.writing import records as writing_records
    from laplace.pipeline import authoring
    with writing_records.author_update_delivery_lock(root,turn_id):
        turn=turn_scope(root,project,turn_id)
        if turn is None:return None
        state,_source,cut=correction_snapshot(root,project)
        selection=turn.get('selection') or {};files=selection.get('files') or ([selection['file']] if selection.get('file') else [])
        if isinstance(files,str):files=[files]
        selected=[{'file':file,'line_start':selection.get('line_start'),'line_end':selection.get('line_end'),'text':''} for file in files]
        consumed=set(turn.get('consumed_correction_ids') or [])
        acked=set(turn['author_update_acks'])
        pending=[row for row in authoring._active_corrections(state,selected,selection)
            if row.get('instruction_eligible') is True and row.get('id') not in consumed|acked and not str(row.get('by') or '').lower().startswith(('eigen','agent','pipeline','machine'))]
        if eligible is not None:
            chosen=set(eligible);pending=[row for row in pending if row['id'] in chosen]
        if not pending:return None
        offered={ident for row in turn['author_update_deliveries'] if row.get('status')=='OFFERED_AT_TOOL_BOUNDARY' for ident in row.get('correction_ids') or []}
        fresh=[row for row in pending if row['id'] not in offered][:3]
        ids=[row['id'] for row in fresh or pending[:20]]
        if fresh and bank:
            import uuid
            writing_records.bank(Path(root),{'record':'writing-author-update-delivery','id':'AUTHORUPDATE-'+uuid.uuid4().hex,
                'project':project,'turn_id':turn_id,'correction_ids':ids,'status':'OFFERED_AT_TOOL_BOUNDARY','authoring_cut':cut})
        result={'schema_version':'laplace.author-updates/1','status':'OFFERED_AT_TOOL_BOUNDARY' if fresh else 'AWAITING_EXACT_READ',
            'correction_ids':ids,'pending_total':len(pending),'omitted':max(0,len(pending)-len(ids)),
            'required_reads':[_read_handle(project,'author_history',{'id':ident}) for ident in ids],
            'basis':'Tool result offer does not prove model attention, acknowledgement, approval or context consumption.'}
        if fresh:
            from laplace.work.history import _actor
            result['updates']=[{**copy.deepcopy(row),'actor_basis':'owner-recorded instruction intent; actor label is not authentication',
                'actor_label_kind':_actor(label=row.get('by')).get('kind','unknown'),'human_actor_proof':'unproven'} for row in fresh]
        return result


def author_notice(offer):
    """The offer without its correction bodies, for a tool result that has no room for them. The ids and their
    required author_history reads stay, and the banked offer row names exactly these ids; an offer is not an
    acknowledgement, which still needs the exact read."""
    if not offer or not offer.get('updates'):return offer
    return {**{key:value for key,value in offer.items() if key!='updates'},
        'updates_omitted':{'count':len(offer['updates']),
            'says':'Correction bodies are not in this tool result; each is its required author_history read.'}}


def acknowledge(root,project,turn_id,correction_id):
    from laplace.writing import records as writing_records
    import uuid
    with writing_records.author_update_delivery_lock(root,turn_id):
        turn=turn_scope(root,project,turn_id)
        if not turn or correction_id in turn['author_update_acks']:return
        offered={ident for row in turn['author_update_deliveries'] if row.get('status')=='OFFERED_AT_TOOL_BOUNDARY' for ident in row.get('correction_ids') or []}
        if correction_id not in offered:return
        writing_records.bank(Path(root),{'record':'writing-author-update-ack','id':'AUTHORACK-'+uuid.uuid4().hex,
            'project':project,'turn_id':turn_id,'correction_id':correction_id,'status':'EXACT_SCOPED_AUTHOR_HISTORY_READ'})


# A tool-boundary publication is a constructed transport result, not evidence of
# model reading, understanding or action. Exact reads remain a separate observation.
# Reuse the existing input preview budget; completeness is explicit per part.
_INPUT_MESSAGE_LIMIT = 2000


def _input_scope(root, project, turn, *, with_parts=True):
    """Only the fields preparation consumes, from exact current-turn rows.

    Equivalent to the rich fold for project, context_parts and the latest basis:
    later baselines without context_parts retain the last explicitly carried map.
    No unrelated body resolution, rich-history fold or new persistent cache.
    """
    with writing_records.index_lock:
        idx=writing_records.index(root)
        admissions=[row for row in idx.by_id.get(turn['id'],()) if row['record']=='writing-turn' and idx.project(row)==project]
        if len(admissions)!=1:raise ValueError('Input turn admission is unavailable or ambiguous.')
        bases=[row for row in idx.by_turn.get(turn['id'],()) if row['record']=='writing-turn-context-baseline' and idx.project(row)==project]
        result={**turn,'context_basis_record_id':bases[-1]['id'] if bases else turn['id']}
        if not with_parts:return result
        for meta in reversed([admissions[0],*bases]):
            if len(idx.by_id.get(meta['id'],()))!=1:raise ValueError('Input context basis identity is ambiguous.')
            raw=writing_records.raw_indexed_record(idx,meta)
            if 'context_parts' in raw:
                if raw['context_parts'] is not None and not isinstance(raw['context_parts'],dict):raise ValueError('Retained input part basis is unsupported.')
                result['context_parts']=copy.deepcopy(raw['context_parts']);break
        return result


def _previous_context(root, project, turn_id, *, basis_id=None):
    """Exact selected turn/baselines, through the existing fold with bodies unresolved."""
    keys=('context_id','dependencies','document','consumed','selection','workspace_context','science_context_digest','context_parts')
    with writing_records.index_lock:
        idx=writing_records.index(root)
        origins=[row for row in idx.by_id.get(turn_id,()) if row['record']=='writing-turn' and idx.project(row)==project]
        if len(origins)!=1:raise ValueError('Input previous attention is unavailable or ambiguous.')
        bases=[row for row in idx.by_turn.get(turn_id,()) if row['record']=='writing-turn-context-baseline' and idx.project(row)==project]
        if basis_id is not None:
            target=[row for row in [origins[0],*bases] if row['id']==basis_id]
            if len(target)!=1:raise ValueError('Retained previous context identity is unavailable or ambiguous.')
            bases=[row for row in bases if row['_order']<=target[0]['_order']]
        rows=[origins[0],*bases]
        state={'turns':{},'sessions':{},'orders':{},'sequence':0}
        for meta in rows:
            raw=writing_records.raw_indexed_record(idx,meta)
            selected={key:raw[key] for key in ('record','id','project','turn_id','session_id',*keys) if key in raw}
            writing_records.fold_record(state,selected,root,resolve=False,order=meta['_order'])
        current=state['turns'][turn_id]
        return {**{key:current.get(key) for key in keys},'context_parts':current.get('context_parts') or {}}


def invalidate_unpublished_input(root, project, turn_id, receipt, *, request):
    """Restore once only from verified evidence; otherwise invalidate without guessing."""
    from laplace.writing import child_hosts
    from laplace.writing import records as writing_records
    control_id=request.name.removesuffix('.request.json').split('-',1)[-1]
    command=child_hosts._read_host(request);payload=command.get('payload') or {}
    current=writing_records.turn_context_basis(root,project,turn_id)
    actual=writing_records.exact_record(project,current,root)
    owned=bool(actual and actual[0].get('record')=='writing-turn-context-baseline' and actual[0].get('turn_id')==turn_id and actual[0].get('control_id')==control_id)
    row=actual[0] if actual else {}
    if not owned and not receipt.get('preparation') and receipt.get('state')!='PREPARED_AT_TOOL_BOUNDARY':return {'status':'NOT_PREPARED'}
    restoration=None;error=None
    try:
        if (receipt.get('control_id')!=control_id or command.get('control_id')!=control_id
            or command.get('sequence')!=receipt.get('sequence') or payload.get('turn_id')!=turn_id
            or payload.get('project',project)!=project):raise ValueError('Control request identity is unavailable or changed.')
        prepared,_message=_retained_input(root,project,turn_id,receipt,payload)
        baseline=prepared.get('baseline')
        if owned and row.get('cause') not in {'input-publication-unproved','input-attention-unproved'} and (not baseline or baseline['id']!=current):raise ValueError('Current input attention differs from its retained planned row.')
        previous=prepared.get('previous_context')
        observed=_previous_context(root,project,turn_id,basis_id=prepared['previous_context_basis_record_id'])
        if previous!=observed:raise ValueError('Retained rollback snapshot differs from its exact previous context.')
        errors=[];bodies.resolve_value(previous,root,errors,'previous_context')
        if errors:raise ValueError('Retained rollback body is unavailable or changed.')
        restoration=previous
    except (ValueError,OSError) as failure:
        error=_bounded(failure)
    if not owned:return {'status':'NOT_OWNED',**({'error':error} if error else {})}
    if row.get('cause') in {'input-publication-unproved','input-attention-unproved'}:return {'status':'ALREADY_INVALIDATED',**({'error':error} if error else {})}
    # Corruption cannot restore sidecar fields. The immutable current row still
    # proves this control owns the undelivered attention; clear its authority,
    # requiring a fresh read rather than keeping unproved tokens or guessing scope.
    if restoration is None:
        restoration={key:None for key in ('context_id','dependencies','document','consumed','selection','workspace_context','science_context_digest')}
        restoration['context_parts']={}
    restored={'record':'writing-turn-context-baseline','id':'CTX-INPUT-INVALIDATED-'+control_id,
        'project':project,'turn_id':turn_id,'control_id':control_id,**restoration,
        'cause':'input-publication-unproved' if error is None else 'input-attention-unproved'}
    _bank_input_once(root,project,restored,expected_context_basis=current)
    return {'status':'RESTORED' if error is None else 'UNPROVED_INVALIDATED',
        'record_id':restored['id'],**({'error':error} if error else {})}


def _fail_input(root,project,turn,receipt,request,ack,error,sequence):
    from laplace.writing import child_hosts
    disposition=invalidate_unpublished_input(root,project,turn['id'],receipt,request=request)
    failed={**receipt,'state':'FAILED','terminal':True,'error':str(error)[:500],
        'context_disposition':disposition,'basis':_INPUT_FAILED_BASIS}
    child_hosts._write_host(ack,failed)
    child_hosts._update_child_execution(root,turn['session_id'],{'last_control':{key:value for key,value in failed.items() if key!='preparation'},
        'control_completed_sequence':sequence},expected_turn_id=turn['id'])
    return _input_failed_answer(receipt,error,disposition)


# THE BOUNDED LATE ANSWERS of one input control. Each is composed by the function the real path uses, with its error text
# held to delivery.bounded_text, so the delivery plan can reserve the exact largest form before the page is selected
# (input_forms) and every outcome after the commit fits what was reserved (writing.delivery, steps 2-3).
_INPUT_FAILED_BASIS='This input failed before publication; original request retained. Explicit new admission is required.'
_PREPARATION_FAILED_BASIS='Original admitted input retained; no context baseline or publication advanced.'
_UNCONFIRMED_PREPARATION_BASIS='Execution changed during preparation; no context baseline or publication advanced.'
_UNCONFIRMED_PUBLICATION_BASIS='Publication record unavailable; context delivery unproved.'
_SCOPE_CHANGED_ERROR='Context changed after preparation; no stale attention was published.'


def _bounded(error):
    from laplace.writing import delivery
    return delivery.bounded_text(error)


def _input_failed_answer(receipt,error,disposition):
    return {'status':'INPUT_FAILED','control_id':receipt['control_id'],'error':_bounded(error),
        'context_disposition':disposition,'basis':_INPUT_FAILED_BASIS}


def _preparation_failed_answer(receipt,error):
    return {'status':'PREPARATION_FAILED','delivery_mode':'project_tool_boundary',
        'control_id':receipt['control_id'],'error':_bounded(error),'basis':_PREPARATION_FAILED_BASIS}


def _unconfirmed_answer(receipt,basis,error=None):
    return {'status':'PUBLICATION_UNCONFIRMED','control_id':receipt['control_id'],'basis':basis,
        **({'error':_bounded(error)} if error is not None else {})}


def _scope_changed_answer(receipt):
    return {'status':'SCOPE_CHANGED','control_id':receipt['control_id'],'basis':_SCOPE_CHANGED_ERROR}


def _maintenance_warning(error):
    return {'stage':'execution-observation','error':_bounded(error),
        'basis':'Exact publication receipt confirmed; constructed input retained.'}


def input_forms(project,turn,receipt):
    """Every bounded answer this pending control may deliver instead of its published offer, at its largest: the
    deferred notice and the owner's failure answers with error texts at the bounded_text limit. The plan reserves the
    largest; the published offer is measured at commit beside the largest maintenance warning."""
    big='x'*500
    disposition={'status':'UNPROVED_INVALIDATED','record_id':'CTX-INPUT-INVALIDATED-'+receipt['control_id'],'error':big}
    return [_deferred_offer(project,turn,receipt),_preparation_failed_answer(receipt,big),
            _unconfirmed_answer(receipt,_UNCONFIRMED_PREPARATION_BASIS),_unconfirmed_answer(receipt,_UNCONFIRMED_PUBLICATION_BASIS,big),
            _scope_changed_answer(receipt),_input_failed_answer(receipt,big,disposition)]


def _retained_input(root, project, turn_id, receipt, payload):
    prepared = receipt.get('preparation')
    if not isinstance(prepared, dict) or prepared.get('schema_version') != 'laplace.turn-input-preparation/1':
        raise ValueError('Prepared input has no supported retained basis; inspect its exact control.')
    if prepared.get('request_sha256') != writing_records.proposal_digest(payload):
        raise ValueError('Prepared input disagrees with its original request; nothing is replayed.')
    if receipt.get('preparation_sha256') != writing_records.proposal_digest(prepared):
        raise ValueError('Prepared input receipt changed; nothing is replayed.')
    if type(prepared.get('full_publication')) is not bool or not isinstance(prepared.get('previous_context_basis_record_id'),str):
        raise ValueError('Retained input publication basis is unsupported.')
    for key,kind,prefix in [('delivery','writing-steer','WST-INPUT-'),('baseline','writing-turn-context-baseline','CTX-INPUT-')]:
        row=prepared.get(key)
        if row is None and key=='baseline':continue
        if (not isinstance(row,dict) or row.get('record')!=kind or row.get('project')!=project
            or row.get('turn_id')!=turn_id or row.get('control_id')!=receipt.get('control_id')
            or not isinstance(row.get('id'),str) or not row['id'].startswith(prefix)):
            raise ValueError('Retained input row attribution differs from its exact control.')
    if prepared['delivery'].get('text')!=payload.get('text') or prepared['delivery'].get('delivery_mode')!='project_tool_boundary':
        raise ValueError('Retained input delivery differs from its admitted request.')
    errors = []
    message = bodies.resolve_value(prepared.get('message'), root, errors, 'input.message')
    if errors or not isinstance(message, str) or prepared.get('message_sha256') != writing_records.proposal_digest(message):
        raise ValueError('Retained prepared input is unavailable or changed; nothing is replayed.')
    parts=prepared.get('message_parts')
    if (not isinstance(parts,dict) or set(parts)!={'context','author_request'}
        or any(not isinstance(parts[key],list) or len(parts[key])!=2 or any(type(n) is not int for n in parts[key]) for key in parts)
        or parts['context'][0]!=0 or parts['context'][1]!=parts['author_request'][0]
        or parts['author_request'][1]!=len(message) or not 0<=parts['context'][1]<=len(message)
        or message[slice(*parts['author_request'])]!=str(payload.get('text') or '').strip()):
        raise ValueError('Retained prepared message parts disagree with the owner request.')
    return prepared, message


def _bank_input_once(root, project, row, *, require_existing=False, expected_context_basis=None):
    """Recover exactly the planned existing row, never accept a same-ID substitute."""
    if row is None:return
    from laplace.writing import records as writing_records
    with writing_records.index_lock:
        found = list(writing_records.index(root).by_id.get(row['id'], ()))
    if found:
        if len(found) != 1 or found[0].get('project') != project or found[0].get('record') != row['record']:
            raise ValueError('Prepared input row identity is ambiguous or belongs to another owner.')
        actual = writing_records.exact_record(project,row['id'],root)[0]
        expected = bodies.resolve_fields(row,root,strict=True)
        if any(actual.get(key) != value for key,value in expected.items()):
            raise ValueError('Prepared input row differs from its retained publication basis.')
        return
    if require_existing:raise ValueError('Published input has no exact retained delivery row.')
    try:
        writing_records.bank(root,row,**({'expected_context_basis':expected_context_basis} if expected_context_basis is not None else {}))
    except Exception as error:
        # An append may have landed before its later journal/adapter error.
        # Recover only the exact planned row in this same invocation.
        try:_bank_input_once(root,project,row,require_existing=True)
        except Exception:raise error
        return


def _input_entry(project, turn, receipt, prepared, message, payload):
    parts=prepared['message_parts'];context=message[slice(*parts['context'])];text=message[slice(*parts['author_request'])]
    if prepared['full_publication']:
        content={'message':message};text_count=len(text);context_count=len(context)
    else:
        text_count=min(len(text),_INPUT_MESSAGE_LIMIT);context_count=min(len(context),max(0,_INPUT_MESSAGE_LIMIT-text_count))
        content={'text':text[:text_count],'text_truncated':text_count<len(text),
                 'context_preview':context[:context_count],'context_truncated':context_count<len(context)}
    return {'control_id':receipt['control_id'],'sequence':receipt['sequence'],**content,
        'message_truncated':not prepared['full_publication'],'message_sha256':prepared['message_sha256'],
        'publication_parts':{'author_request':{'included_chars':text_count,'total_chars':len(text),'complete':text_count==len(text)},
                             'context':{'included_chars':context_count,'total_chars':len(context),'complete':context_count==len(context)}},
        'published_chars':text_count+context_count,'total_chars':len(message),
        'context_delivery':receipt['context_delivery'],
        'exact_read':_input_read(project,turn,receipt['control_id'])}


def _input_read(project,turn,control_id):
    """The exact read of one admitted input control (its request and receipt); reading it acknowledges a published
    input and never adopts an unpublished one. The turn names its session: the conversation_history contract admits
    view, turn_id and item_id (an earlier handle also carried session_id, which that contract refuses)."""
    return _read_handle(project,'conversation_history',{'view':'controls','turn_id':turn['id'],'item_id':control_id})


def _deferred_offer(project,turn,receipt):
    """THE DEFERRED INPUT NOTICE: this tool result has no room for the prepared publication, so nothing is published,
    no context baseline is banked and the frontier stays; the retained preparation is published unchanged by a later
    tool result that has room. Its size is planned before a bounded page is selected (pending_input_notice)."""
    return {'status':'DEFERRED_AT_TOOL_BOUNDARY','delivery_mode':'project_tool_boundary',
        'inputs':[{'control_id':receipt['control_id'],'sequence':receipt['sequence'],
                   'exact_read':_input_read(project,turn,receipt['control_id'])}],
        'basis':'No room in this tool result: the input is not published, no context advanced. A later tool result with '
                'room publishes it unchanged; its exact read shows the admitted request now without adopting its context.'}


def _published_offer(project,turn,receipt,prepared,message,payload):
    """The PUBLISHED receipt and the tool-result offer of one retained preparation, composed before any effect so the
    space guard measures exactly what will be delivered. The scope is the retained plan's (FULL when the preparation
    chose full publication, else PREVIEW); a later tool's budget never changes it."""
    full=prepared['full_publication']
    delivery={'record_id':prepared['delivery']['id'],
        'baseline_record_id':prepared['baseline']['id'] if full and prepared['baseline'] else None}
    published={**receipt,'state':'PUBLISHED_AT_TOOL_BOUNDARY','context_delivery':delivery,
        'publication':{'scope':'FULL' if full else 'PREVIEW',
            'included_chars':min(len(message),_INPUT_MESSAGE_LIMIT),'total_chars':len(message),
            'text_complete':len(str(payload.get('text') or ''))<=_INPUT_MESSAGE_LIMIT,
            'context_baseline_advanced':bool(full and prepared['baseline']),
            'basis':'Scoped input constructed in this project tool result; model attention/reading/understanding/action unproven.'}}
    entry=_input_entry(project,turn,published,prepared,message,payload)
    published['publication']['parts']=entry['publication_parts']
    published['publication']['text_complete']=entry['publication_parts']['author_request']['complete']
    return published,{'status':'PUBLISHED_AT_TOOL_BOUNDARY','delivery_mode':'project_tool_boundary','inputs':[entry],
        'basis':'Full included message needs no ceremonial reread. Preview/omitted content requires its exact read before use; publication is not evidence of model attention.'}


def _frontier(root,project,turn,execution,*,settle=True):
    """The next unsettled input control of this running turn as (sequence, request, ack, receipt, payload), or None.
    With ``settle`` a passed or finished control advances the frontier and a published one recovers its exact rows;
    without it the same scan only observes (pending_input_notice)."""
    from laplace.writing import child_hosts
    turn_id=turn['id']
    frontier=int(execution.get('control_completed_sequence') or 0);admitted=int(execution.get('control_sequence') or 0)
    for sequence in range(frontier+1,admitted+1):
        requests=list(child_hosts._steer_mailbox(root,turn['session_id']).glob(f'{sequence:020d}-*.request.json'))
        if len(requests)!=1:return None
        request=requests[0];ack=request.with_name(request.name.replace('.request.json','.ack.json'))
        receipt=child_hosts._read_host(ack);command=child_hosts._read_host(request);payload=command.get('payload') or {}
        if command.get('control_id')!=receipt.get('control_id') or command.get('sequence')!=receipt.get('sequence'):return None
        if receipt.get('turn_id') and receipt['turn_id']!=turn_id and payload.get('turn_id')==receipt['turn_id']:
            # Session ordinals are monotone across turns. Passing an old
            # turn is not publication or replay of its retained input.
            if settle:child_hosts._update_child_execution(root,turn['session_id'],{'control_completed_sequence':sequence},expected_turn_id=turn_id)
            continue
        if (receipt.get('turn_id')!=turn_id or receipt.get('delivery_mode')!='project_tool_boundary'
            or receipt.get('execution_host')!=execution.get('host') or payload.get('turn_id')!=turn_id
            or payload.get('project',project)!=project):return None
        state=receipt.get('state')
        if state in {'PUBLISHED_AT_TOOL_BOUNDARY','EXACT_SCOPED_CONTROL_READ'}:
            if settle:
                prepared,message=_retained_input(root,project,turn_id,receipt,payload)
                _bank_input_once(root,project,prepared['baseline'] if prepared['full_publication'] else None,require_existing=True)
                _bank_input_once(root,project,prepared['delivery'],require_existing=True)
                child_hosts._update_child_execution(root,turn['session_id'],{'control_completed_sequence':sequence},expected_turn_id=turn_id)
            continue # Recover settled frontier without republishing context.
        if state=='FAILED' or receipt.get('terminal') is True:
            if settle:child_hosts._update_child_execution(root,turn['session_id'],{'control_completed_sequence':sequence},expected_turn_id=turn_id)
            continue
        return sequence,request,ack,receipt,payload
    return None


def pending_input(root,project,turn_id):
    """The input control the next tool result of this turn may publish: {'eligible': (sequence, control_id), 'forms':
    [its bounded late answers]} or None. Pure: the delivery plan asks it before a bounded page is selected, fixes
    ``eligible`` as THE CUT and reserves the largest form, so every answer always has room."""
    from laplace.writing import child_hosts
    turn=turn_scope(root,project,turn_id)
    if not turn:return None
    try:child_hosts._host_path(root,str(turn.get('session_id') or ''))
    except ValueError:return None
    execution=child_hosts.child_execution(root,turn['session_id'])
    if execution.get('turn_id')!=turn_id or execution.get('state')!='RUNNING':return None
    found=_frontier(root,project,turn,execution,settle=False)
    if found is None or found[3].get('state') not in {'ADMITTED','OFFERED_AT_TOOL_BOUNDARY','PREPARED_AT_TOOL_BOUNDARY'}:return None
    return {'eligible':(found[0],found[3]['control_id']),'forms':input_forms(project,turn,found[3])}


def pending_input_notice(root,project,turn_id):
    """The deferred notice alone (an unplanned boundary's later form), or None."""
    pending=pending_input(root,project,turn_id)
    return None if pending is None else pending['forms'][0]


def turn_input_offer(root,project,turn_id,*,fits=None,eligible=None):
    """Prepare once, retain before advancing context, then construct ordered publication.

    ``fits`` (a bounded tool result's admission, writing.delivery) qualifies the PREPARED->PUBLISHED transition: the
    exact offer (beside the largest maintenance warning it may still gain) is composed first and, when it does not fit,
    nothing is banked or published and the deferred notice is returned; the retained preparation waits unchanged for a
    tool result with room. ``eligible`` is THE CUT the delivery plan fixed, the (sequence, control_id) it reserved room
    for: any other pending control (one admitted after the plan, or the next after a cancellation) is left untouched,
    unprepared and unpublished, for the next boundary; the frontier does not move for it. The cancellation, host and
    basis checks of the transition still apply to the eligible control at commit."""
    from laplace.work import project_work
    from laplace.writing import child_hosts
    from laplace.writing import turn_control
    from laplace.writing import records as writing_records
    import uuid
    root=Path(root);turn=turn_scope(root,project,turn_id)
    if not turn:return None
    try:child_hosts._host_path(root,str(turn.get('session_id') or ''))
    except ValueError:return None
    with writing_records.author_update_delivery_lock(root,turn_id):
        with project_work.dispatch_lock(root):
            execution=child_hosts.child_execution(root,turn['session_id'])
            if execution.get('turn_id')!=turn_id or execution.get('state')!='RUNNING':return None
            found=_frontier(root,project,turn,execution)
            if found is None:return None
            sequence,request,ack,receipt,payload=found;state=receipt.get('state')
            if eligible is not None and (sequence,receipt.get('control_id'))!=tuple(eligible):return None
            if state not in {'ADMITTED','OFFERED_AT_TOOL_BOUNDARY','PREPARED_AT_TOOL_BOUNDARY'}:return None
            if state!='PREPARED_AT_TOOL_BOUNDARY':
                receipt={**receipt,'state':'PREPARING_AT_TOOL_BOUNDARY'}
                child_hosts._write_host(ack,receipt)
                child_hosts._update_child_execution(root,turn['session_id'],{'last_control':receipt},expected_turn_id=turn_id)
        if state!='PREPARED_AT_TOOL_BOUNDARY':
            # No dispatch lock around source/context assembly. The per-turn owner
            # lock prevents competing boundaries from preparing the same input twice.
            try:
                current=_input_scope(root,project,turn,with_parts='selection' in payload or 'workspace_context' in payload)
                if not current or current.get('project')!=project:raise ValueError('Current turn scope unavailable.')
                value=turn_control._prepare_steering_input(root,current,payload)
                message=value['message'];full=len(message)<=_INPUT_MESSAGE_LIMIT
                context=value['context'];baseline=None
                if context is not None:
                    baseline=writing_records.prepare_custody_row(root,{'record':'writing-turn-context-baseline','id':'CTX-INPUT-'+uuid.uuid4().hex,
                        'turn_id':turn_id,'project':project,'control_id':receipt['control_id'],
                        'selection':value['selection'],'workspace_context':value['workspace'],
                        'unsaved_draft':value['unsaved_draft'],'context_parts':value['held'],
                        'science_context_digest':context.get('science_context_digest'),
                        **{key:context.get(key) for key in ('context_id','dependencies','document','consumed')}})
                delivery={'record':'writing-steer','id':'WST-INPUT-'+uuid.uuid4().hex,'turn_id':turn_id,'project':project,
                    'control_id':receipt['control_id'],'delivery_mode':'project_tool_boundary','text':payload['text'],
                    'selection':value['selection'],'workspace_context':value['workspace'],'unsaved_draft':value['unsaved_draft']}
                diagnostic=core_bodies.degradation()
                retained_message=bodies.retain_leaves(root,{'message':message},('message',),diagnostic=diagnostic)['message']
                if diagnostic['failed_attempts'] or baseline and baseline.get('custody_degradation'):
                    raise ValueError('Prepared input custody unavailable; original input retained, no baseline or publication advanced.')
                prepared={'schema_version':'laplace.turn-input-preparation/1','request_sha256':writing_records.proposal_digest(payload),
                    'message':retained_message,'message_sha256':writing_records.proposal_digest(message),
                    'baseline':baseline,'delivery':delivery,'full_publication':full,'message_parts':value['message_parts'],
                    'previous_context_basis_record_id':current.get('context_basis_record_id') or current['id'],
                    'previous_context_parts':current.get('context_parts') or {},
                    'previous_context':_previous_context(root,project,turn_id)}
            except (ValueError,OSError) as error:
                with project_work.dispatch_lock(root):
                    observed=child_hosts._read_host(ack)
                    if observed.get('state')=='PREPARING_AT_TOOL_BOUNDARY':
                        failed={**receipt,'state':'FAILED','error':str(error)[:500],
                            'basis':'Context preparation failed before baseline advancement or publication; input retained.',
                            **({'custody_degradation':diagnostic} if 'diagnostic' in locals() and diagnostic['failed_attempts'] else {})}
                        child_hosts._write_host(ack,failed)
                        child_hosts._update_child_execution(root,turn['session_id'],{'last_control':failed,
                            'control_completed_sequence':sequence},expected_turn_id=turn_id)
                return _preparation_failed_answer(receipt,error)
            with project_work.dispatch_lock(root):
                active=child_hosts.child_execution(root,turn['session_id']);observed=child_hosts._read_host(ack)
                if active.get('turn_id')!=turn_id or active.get('state')!='RUNNING' or active.get('host')!=execution.get('host') or observed.get('state')!='PREPARING_AT_TOOL_BOUNDARY':
                    child_hosts._write_host(ack,{**receipt,'state':'PUBLICATION_UNCONFIRMED','error':'Execution changed during preparation; no context baseline or publication was advanced.'})
                    return _unconfirmed_answer(receipt,_UNCONFIRMED_PREPARATION_BASIS)
                receipt={**receipt,'state':'PREPARED_AT_TOOL_BOUNDARY','preparation':prepared,
                    'preparation_sha256':writing_records.proposal_digest(prepared),
                    **({'custody_degradation':diagnostic} if diagnostic['failed_attempts'] else {})}
                # Durable replayable preparation BEFORE either journal effect.
                child_hosts._write_host(ack,receipt)
                child_hosts._update_child_execution(root,turn['session_id'],{'last_control':{key:value for key,value in receipt.items() if key!='preparation'}},expected_turn_id=turn_id)
        with project_work.dispatch_lock(root):
            active=child_hosts.child_execution(root,turn['session_id']);receipt=child_hosts._read_host(ack)
            if active.get('turn_id')!=turn_id or active.get('state')!='RUNNING' or active.get('host')!=execution.get('host') or receipt.get('state')!='PREPARED_AT_TOOL_BOUNDARY':return None
            prepared,message=_retained_input(root,project,turn_id,receipt,payload)
            # THE SPACE GUARD: the exact offer this transition would deliver must fit before any baseline, delivery row
            # or receipt advances; otherwise the retained preparation waits and only the planned notice is delivered.
            published,offer=_published_offer(project,turn,receipt,prepared,message,payload)
            if fits is not None and not fits({**offer,'maintenance_warning':_maintenance_warning('x'*500)}):
                return _deferred_offer(project,turn,receipt)
            if prepared['full_publication'] and prepared['baseline'] is not None:
                basis=writing_records.turn_context_basis(root,project,turn_id)
                if basis not in {prepared['previous_context_basis_record_id'],prepared['baseline']['id']}:
                    refused={**receipt,'state':'FAILED','error':_SCOPE_CHANGED_ERROR}
                    child_hosts._write_host(ack,refused)
                    child_hosts._update_child_execution(root,turn['session_id'],{'last_control':{key:value for key,value in refused.items() if key!='preparation'},'control_completed_sequence':sequence},expected_turn_id=turn_id)
                    return _scope_changed_answer(receipt)
                try:
                    _bank_input_once(root,project,prepared['baseline'],expected_context_basis=basis)
                    _bank_input_once(root,project,prepared['delivery'])
                except Exception as error:
                    return _fail_input(root,project,turn,receipt,request,ack,error,sequence)
            else:
                try:_bank_input_once(root,project,prepared['delivery'])
                except Exception as error:return _fail_input(root,project,turn,receipt,request,ack,error,sequence)
            delivery=published['context_delivery']
            warning=None
            try:
                child_hosts._write_host(ack,published)
                child_hosts._update_child_execution(root,turn['session_id'],{'last_control':{key:value for key,value in published.items() if key!='preparation'},
                    'control_completed_sequence':max(sequence,int(active.get('control_completed_sequence') or 0))},expected_turn_id=turn_id)
            except Exception as error:
                # The exact durable construction is stronger than later sidecar
                # maintenance. Never discard a known entry and silently withhold it.
                if child_hosts._read_host(ack)==published:
                    warning=_maintenance_warning(error)
                else:
                    unknown={**receipt,'state':'PUBLICATION_UNCONFIRMED','terminal':True,'context_delivery':delivery,
                        'error':str(error)[:500],'basis':_UNCONFIRMED_PUBLICATION_BASIS}
                    try:child_hosts._write_host(ack,unknown)
                    except OSError:pass
                    # A failed publication must not leave new part tokens claiming
                    # delivery. Only our still-current baseline can be invalidated;
                    # never touch a newer ordinary read/attention basis.
                    invalidate_unpublished_input(root,project,turn_id,receipt,request=request)
                    return _unconfirmed_answer(receipt,_UNCONFIRMED_PUBLICATION_BASIS,error)
            return {**offer,**({'maintenance_warning':warning} if warning else {})}



def acknowledge_turn_input(root,project,turn_id,control_id):
    """Observe an explicit exact read; never prepare or regress a later context."""
    from laplace.work import project_work
    from laplace.writing import child_hosts
    from laplace.writing import records as writing_records
    root=Path(root);turn=turn_scope(root,project,turn_id)
    if not turn:return None
    with writing_records.author_update_delivery_lock(root,turn_id):
        with project_work.dispatch_lock(root):
            requests=list(child_hosts._steer_mailbox(root,turn['session_id']).glob('*-'+control_id+'.request.json'))
            if len(requests)!=1:return None
            request=requests[0];ack=request.with_name(request.name.replace('.request.json','.ack.json'))
            receipt=child_hosts._read_host(ack);payload=(child_hosts._read_host(request).get('payload') or {})
            if receipt.get('turn_id')!=turn_id or payload.get('turn_id')!=turn_id or payload.get('project',project)!=project:return None
            if receipt.get('state') not in {'PUBLISHED_AT_TOOL_BOUNDARY','EXACT_SCOPED_CONTROL_READ'}:return None
            prepared,message=_retained_input(root,project,turn_id,receipt,payload)
            already=receipt['state']=='EXACT_SCOPED_CONTROL_READ'
            context_read=receipt.get('context_read')
            delivery=dict(receipt.get('context_delivery') or {})
            if not already:
                baseline=prepared['baseline'];execution=child_hosts.child_execution(root,turn['session_id'])
                current=_input_scope(root,project,turn,with_parts=False) if baseline is not None else None
                basis=(current or {}).get('context_basis_record_id') or turn_id
                same_basis=(baseline is not None and basis in {prepared['previous_context_basis_record_id'],baseline['id']})
                newer=(execution.get('turn_id')!=turn_id or execution.get('state')!='RUNNING' or execution.get('host')!=receipt.get('execution_host') or int(execution.get('control_completed_sequence') or 0)>receipt['sequence'])
                if baseline is not None and not prepared['full_publication'] and not newer and same_basis:
                    _bank_input_once(root,project,baseline,expected_context_basis=prepared['previous_context_basis_record_id'])
                    delivery['baseline_record_id']=baseline['id']
                context_read={'complete_message':True,'baseline_record_id':delivery.get('baseline_record_id'),
                    'basis':'Retained original scoped message, never re-prepared.',
                    'scope':'CURRENT' if baseline is None or not newer and same_basis else 'HISTORICAL',
                    'newer_scope_preserved':bool(newer or baseline is not None and not same_basis)}
            observed={**receipt,'state':'EXACT_SCOPED_CONTROL_READ','context_delivery':delivery,'context_read':context_read,
                'ack_basis':'Explicit exact input read; preparation/baseline not replayed, attention/understanding/action unproven.'}
            if not already:
                child_hosts._write_host(ack,observed)
                execution=child_hosts.child_execution(root,turn['session_id'])
                if execution.get('turn_id')==turn_id and (execution.get('last_control') or {}).get('control_id')==control_id:
                    child_hosts._update_child_execution(root,turn['session_id'],{'last_control':{key:value for key,value in observed.items() if key!='preparation'}},expected_turn_id=turn_id)
            return {'control_id':control_id,'status':'ALREADY_READ' if already else 'EXACT_SCOPED_CONTROL_READ',
                'message':message,'context_delivery':delivery,'context_read':context_read,'basis':observed['ack_basis']}
