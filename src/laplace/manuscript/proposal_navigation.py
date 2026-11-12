"""Bounded navigation through existing proposal owners; no proposal/status store."""
from __future__ import annotations

from laplace.core import bodies as core_bodies
from laplace.core.identity import canonical_digest
from laplace.core.records import capture
from laplace.writing import records as writing_records
from laplace.representation import writing_bodies as bodies
import copy,json,hashlib
from pathlib import Path
from urllib.parse import urlencode
RESOLUTION_INPUT_FIELDS=('target','resolution_token','input_observations','choices','resolved_after')
TEXT_PART_FIELDS=('part','offset')


def contract(detail=False):
    from laplace.manuscript.reconciliation import decision_contract
    properties={key:{'type':'string'} for key in ('id','record_id','proposal_version','edit_id','session_id','turn_id','work_id','file','cursor','as_of')}
    resolution_inputs=RESOLUTION_INPUT_FIELDS
    resolution_fields=(*resolution_inputs,'read_id','part','hunk_id','field','offset','hunk_offset')
    properties.update({key:decision_contract()['properties'][key] for key in resolution_inputs})
    properties.update(read_id={'type':'string'},part={'enum':['metadata','original','current','proposed','resolved','hunk','contract']},
        hunk_id={'type':'string'},field={'enum':['original','current','proposed']},offset={'type':'integer','minimum':0},
        hunk_offset={'type':'integer','minimum':0})
    properties.update(view={'enum':['queue','history','summary','edit','basis','preview','resolution','resolution-preview','changed-reads']},limit={'type':'integer','minimum':1,'maximum':20})
    return {'type':'object','properties':properties,'additionalProperties':False,
        'allOf':[{'if':{'required':['id']},'then':{'properties':{'view':{'enum':['summary','edit','basis','preview','resolution','resolution-preview','changed-reads']}},
                    'not':{'anyOf':[{'required':[field]} for field in ('session_id','work_id','file','as_of')]},
                    # a selected candidate pages only its changed consulted reads (CR-R1)
                    'if':{'not':{'required':['view'],'properties':{'view':{'const':'changed-reads'}}}},
                    'then':{'not':{'anyOf':[{'required':['cursor']},{'required':['limit']}]}}},
                 'else':{'properties':{'view':{'enum':['queue','history']}},'not':{'anyOf':[{'required':[field]} for field in ('record_id','proposal_version','edit_id')]}}},
                 {'if':{'required':['view'],'properties':{'view':{'enum':['resolution','resolution-preview']}}},
                  'then':{'required':['id','proposal_version','edit_id']},
                  'else':{'if':{'required':['view'],'properties':{'view':{'const':'edit'}}},
                          'then':{'not':{'anyOf':[{'required':[field]} for field in resolution_fields if field not in TEXT_PART_FIELDS]},
                                  'properties':{'part':{'enum':['original','proposed']}},
                                  'dependentRequired':{'part':['id','proposal_version','edit_id']}},
                          'else':{'not':{'anyOf':[{'required':[field]} for field in resolution_fields]}}}},
                 {'if':{'required':['part'],'properties':{'part':{'const':'hunk'}}},
                  'then':{'required':['hunk_id']},'else':{'not':{'anyOf':[{'required':['hunk_id']},{'required':['field']}]}}}]}


def http_contract(*, preview=False):
    """Declare the existing HTTP adapter over the canonical proposal read schema.

    Logical query values retain native types (HTTP encodes limit as text). The
    adapter accepts project/corpus, ignores legacy summary, and supplies id from
    turn_id plus view=preview at the preview entrance. Alias equality and actual
    owner availability remain read-owner checks; this does not change admission.
    """
    schema = contract()
    schema['properties'].update(project={'type': 'string'}, corpus={'type': 'string'})
    project = {'anyOf': [{'required': ['project']}, {'required': ['corpus']}]}
    if preview:
        # The adapter normalizes either identity before the canonical detail branch.
        detail = schema['allOf'][0]['then']
        schema['allOf'] = [project, {'anyOf': [{'required': ['id']}, {'required': ['turn_id']}]}, detail]
    else:
        schema['properties']['summary'] = {'enum': ['0', '1']}
        schema['allOf'].append(project)
    return schema


def handle(project,payload):
    """The existing generic verb, at collection and selected child scope."""
    ident=payload.get('id')
    request={'verb':'read','concept':'proposal@paragraph','target':project+('::'+ident if ident else ''),
             'expected':[],'payload':payload,'by':''}
    route='/authoring/proposal-preview' if ident else '/authoring/proposals'
    return {'native_request':request,'http':{'method':'GET','url':route+'?'+urlencode({'project':project,**payload})}}


def _raw(idx,meta):
    return writing_records.raw_indexed_record(idx,meta)


def _work(records_limit=None):
    """What a selected projection actually opened: raw journal records and their line bytes (by role), and the custody
    bodies the shared resolver actually read at every depth (core_bodies.budget ledger). ``records_limit`` bounds
    the raw opens; the active ledger bounds raw line bytes and expanded custody bytes together. Evidence replays are
    counted by their owner."""
    return {'raw_records':0,'raw_line_bytes':0,'raw_by_role':{},'custody_reads':0,'custody_bytes':0,'records_limit':records_limit}


def _refused_preparation(what):
    return core_bodies.BudgetExceeded(what+' Use the refusal summary and each consulted receipt, then request a fresh proposal.')


def _opened(idx,meta,work,role):
    if work is not None:   # checked BEFORE the record is opened
        line=int(meta['_end'])-int(meta['_offset']);limit=work.get('records_limit')
        if limit is not None and work['raw_records']+1>limit:
            raise _refused_preparation('Opening another journal record would exceed this preparation\'s %d-record budget.' % limit)
        ledger=core_bodies.active_budget()
        if ledger is not None:
            try:core_bodies.charge(ledger,line,'journal record')
            except core_bodies.BudgetExceeded as exceeded:raise _refused_preparation(str(exceeded)) from exceeded
    row=_raw(idx,meta)
    if work is not None:
        work['raw_records']+=1;work['raw_line_bytes']+=line
        work['raw_by_role'][role]=work['raw_by_role'].get(role,0)+1
    return row


def _resolved(value,root,work):
    """The shared custody resolver; the bodies it actually reads (every depth) are counted from the active ledger."""
    ledger=core_bodies.active_budget()
    before=(ledger['reads'],ledger['read_bytes']) if ledger is not None else None
    try:
        return bodies.resolve_fields(value,root,strict=True)
    except core_bodies.BudgetExceeded as exceeded:
        raise _refused_preparation(str(exceeded)) from exceeded
    finally:
        if work is not None and ledger is not None:
            work['custody_reads']+=ledger['reads']-before[0];work['custody_bytes']+=ledger['read_bytes']-before[1]


def _body(idx,meta,field,work=None):
    row=_opened(idx,meta,work,'candidate-body')
    # Only requested typed fields, never a whole historical turn/reply body tree.
    return _resolved({field:row.get(field)},idx.root,work).get(field)


def _projection(idx,meta,budget,work=None):
    from laplace.manuscript import manuscript_proposals as owner
    value=meta.get('proposal_projection')
    if not value and meta.get('has_proposal') and budget[0]>0:
        body=_body(idx,meta,'proposal',work);budget[0]-=1;budget[1]+=1
        if isinstance(body,dict) and isinstance(body.get('edits'),list):
            value=owner.proposal_metadata(body)
            meta['proposal_projection']=value # Disposable index enrichment, original row untouched.
    return owner.identity_proposal(value) if value else None


def _records(idx,project,selected=None,*,body_budget=0,upper=None,row_scope=None,positional=frozenset(),work=None):
    from laplace.manuscript import manuscript_proposals as owner
    rows=[row for row in (row_scope if row_scope is not None else idx.by_project.get(project,[])) if idx.project(row)==project and (upper is None or row['_order']<=upper)]
    state={'sessions':{},'turns':{},'orders':{},'sequence':0,'artifact_records':{},'artifact_ambiguities':set(),'read_receipts':{}}
    budget=[body_budget,0]; selected=selected or set()
    for meta in rows:
        row={key:copy.deepcopy(value) for key,value in meta.items() if not key.startswith('_')}
        kind=row['record']
        if kind in {'writing-turn','writing-turn-context-baseline'}:
            # Selected candidate's exact retained admission/basis is loaded only for detail.
            if row.get('id') in selected:
                original=_opened(idx,meta,work,'turn-basis')
                row.update({key:original.get(key) for key in ('document','selection','context_parts','dependencies','context_id') if key in original})
                row=_resolved(row,idx.root,work)
        if meta.get('has_proposal'):
            proposal=_projection(idx,meta,budget,work)
            if row.get('id') in selected:
                proposal=_body(idx,meta,'proposal',work);budget[1]+=1
            if proposal is not None:row['proposal']=proposal
            elif kind=='writing-proposal':continue
        if kind=='writing-application' and row.get('id') in selected:
            row=_resolved(_opened(idx,meta,work,'application'),idx.root,work)
        elif kind=='writing-application':
            edits=meta.get('edit_projection')
            if edits:row['edits']=[owner.EditIdentity(edit) for edit in edits]
        # A candidate seal names original reads and owner-produced baseline reads.
        # Metadata intentionally omits their payloads; folding it as a consumed
        # baseline would collapse every payload of an operation onto the {} key.
        # ``positional`` reads are not consumed; their exact payloads only give a read key the position its
        # first read gave it, so the selected candidate replays the seal's own identity sequence (CR-R2).
        if kind in {'writing-tool-read','writing-tool-read-baseline'} and (row.get('id') in selected or row.get('id') in positional):
            row=_opened(idx,meta,work,'positional-read' if row.get('id') in positional else 'sealed-read');budget[1]+=row.get('id') in positional
        writing_records.fold_record(state,row,idx.root,resolve=False,order=meta['_order'])
    return state,budget[1]


# The preparation a changed-read page may open before it observes anything: raw journal records and their line
# bytes (sealed reads, positional reads, the selected turn/basis rows, candidate bodies and applications).
PREPARATION_RECORDS, PREPARATION_BYTES = 4096, 16 << 20


def selected_records(root,project,turn_id,version=None,*,application_id=None,work=None):
    """Exact candidate, admitted reads and same-file application metadata only. The raw rows it would open are planned
    from index metadata first; under a bounded ``work``/ledger a selection that cannot fit what remains is refused
    before anything is opened, and custody expansion is charged as it is read (core_bodies.budget)."""
    idx=writing_records.index(root);admitted=idx.turns.get(turn_id)
    if not admitted or idx.project(admitted)!=project:raise ValueError('This suggestion does not belong to the selected project or is unavailable.')
    owned=list(idx.by_turn.get(turn_id,[]))
    carriers=[row for row in owned if row.get('has_proposal')]
    selected=next((row for row in reversed(carriers) if not version or row.get('proposal_instance_version')==version
        or (row.get('proposal_projection') or {}).get('content_sha256')==version),None)
    if selected is None:raise ValueError('This saved proposal version is unavailable.')
    seal=selected.get('proposal_basis') or {}
    required={turn_id,selected['id'],seal.get('turn_basis_record_id'),*seal.get('read_ids',[])}
    if not seal:
        required.update(row['id'] for row in owned if row['_order']<=selected['_order']
            and row['record'] in {'writing-tool-read','writing-tool-read-baseline','writing-turn-context-baseline'})
    required.update(row['id'] for row in owned if row['record']=='writing-application'
        and row.get('candidate_version')==selected.get('proposal_instance_version'))
    required.update(row['application_id'] for row in owned if row['record']=='writing-proposal-decision'
        and row.get('application_id') and row.get('proposal_version')==selected.get('proposal_instance_version'))
    # A read key keeps the position its FIRST read gave it in the warm fold, and the seal hashes the reads in
    # that key order. Only a read of the same operation can share a key, so the earlier same-operation reads of
    # this turn are folded with their exact payloads too (bounded by this turn and the carrier's position);
    # nothing else is opened and none of them joins the consumed basis.
    reads={'writing-tool-read','writing-tool-read-baseline'}
    sealed={row.get('operation') for row in owned if row['record'] in reads and row.get('id') in required}
    positional=frozenset(row['id'] for row in owned if row['record'] in reads and row['_order']<selected['_order']
        and row.get('operation') in sealed and row.get('id') not in required) if seal else frozenset()
    document=admitted.get('document') or {}
    related={}
    for edit in (selected.get('proposal_projection') or {}).get('edits') or []:
        file=writing_records.recorded_source_file(document,edit.get('file'))
        related.update(idx.applications_by_file.get((project,file),{}))
    if application_id:
        exact=[row for row in idx.by_id.get(application_id,[]) if row['record']=='writing-application' and idx.project(row)==project]
        if len(exact)!=1:raise ValueError('The exact related application is unavailable or ambiguous.')
        related[application_id]=exact[0];required.add(application_id)
    subjects={turn_id}|{row['turn_id'] for row in related.values() if row.get('turn_id')}
    scoped={row['_order']:row for tid in subjects for row in idx.by_turn.get(tid,[])
        if row['record'] in {'writing-turn','writing-turn-context-baseline','writing-proposal','writing-reply',
            'writing-application','writing-proposal-decision','writing-proposal-anchor','writing-tool-read','writing-tool-read-baseline'}}
    for tid in subjects:
        sid=(idx.turns.get(tid) or {}).get('session_id')
        for row in idx.by_session.get(sid,[]):
            if row['record'] in {'writing-session','writing-session-settings'}:scoped[row['_order']]=row
    rows=[scoped[key] for key in sorted(scoped)]
    planned=[row for row in rows if (row.get('id') in required or row.get('id') in positional) and (row.get('has_proposal')
        or row['record'] in reads or row['record'] in {'writing-turn','writing-turn-context-baseline','writing-application'})]
    plan={'records':len(planned),'line_bytes':sum(int(row['_end'])-int(row['_offset']) for row in planned)}
    work=work if work is not None else _work()
    with core_bodies.budget() as ledger:   # joins the invocation's ledger; observes when there is none
        limit=work.get('records_limit')
        if (limit is not None and work['raw_records']+plan['records']>limit) or (ledger['limit'] is not None and ledger['spent']+plan['line_bytes']>ledger['limit']):
            raise _refused_preparation('This candidate\'s selected projection would open %d more journal records (%d bytes); this '
                'preparation allows %s records and %s bytes, %d records and %d bytes already used.' % (plan['records'],plan['line_bytes'],
                limit,ledger['limit'],work['raw_records'],ledger['spent']))
        state,_opened_bodies=_records(idx,project,required,row_scope=rows,positional=positional,work=work)
        spent,budget=ledger['spent'],ledger['limit']
    state['selected_candidate_record_id']=selected['id']
    state['coverage']={'whole_history_loaded':False,'selected_turns':len(subjects),'selected_rows':len(scoped),
        'body_reads':work['raw_records'],'positional_reads':len(positional),'planned':plan,
        **{key:value for key,value in work.items() if key!='records_limit'},
        'budget':{'records':work.get('records_limit'),'bytes':budget,'spent':spent}}
    return state


def carrier_scope(idx,project,query):
    """Exact saved carrier -> its recorded turn association; no inferred/latest turn."""
    matches=[row for row in idx.by_id.get(query['id'],[]) if row.get('has_proposal') and row.get('turn_id')]
    if not matches:return dict(query)
    if len(matches)!=1 or idx.project(matches[0])!=project:
        raise ValueError('The exact proposal carrier is ambiguous or belongs to another project.')
    row=matches[0];version=row.get('proposal_instance_version') or (row.get('proposal_projection') or {}).get('content_sha256')
    if query.get('record_id') not in (None,row['id']) or query.get('proposal_version') not in (None,version):
        raise ValueError('The exact proposal carrier/version selectors disagree.')
    return {**query,'id':row['turn_id'],'record_id':row['id'],'proposal_version':version}


def stored_text_part(idx,project,query):
    """Immutable candidate text, independent of current source/application standing."""
    from laplace.manuscript import manuscript_proposals
    from laplace.manuscript import reconciliation
    query=carrier_scope(idx,project,query)
    rows=[row for row in (idx.by_id.get(query['id'],[]) if query['id'] not in idx.turns else idx.by_turn.get(query['id'],[]))
        if row.get('has_proposal') and idx.project(row)==project
        and row.get('proposal_instance_version')==query['proposal_version']
        and (not query.get('record_id') or row['id']==query['record_id'])]
    if not rows:raise ValueError('The exact immutable proposal carrier is unavailable.')
    if len(rows)>1:
        identities={(row.get('proposal_projection') or {}).get('content_sha256') for row in rows}
        if len(identities)!=1 or None in identities:raise ValueError('The immutable proposal carrier is ambiguous.')
    selected=rows[0]
    proposal=writing_records.selected_journal_fields(project,selected['id'],idx.root,fields=['proposal'],expected_row_sha256=selected['_hash'])['proposal']
    edit=next((row for row in proposal.get('edits') or [] if manuscript_proposals.edit_id(row)==query['edit_id']),None)
    if edit is None:raise ValueError('The exact immutable proposal edit is unavailable.')
    field='before' if query['part']=='original' else 'after';chunk,end=reconciliation._text_part(edit[field],query.get('offset',0))
    chunk['coverage']['basis']='IMMUTABLE_SAVED_CANDIDATE'
    result={'project':project,'projection':'stored-candidate-text','carrier_ref':{'id':selected['id'],'version':query['proposal_version']},
        'edit_id':query['edit_id'],'part':query['part'],'source_currentness':'NOT_ASSERTED','semantic_currentness':'NOT_REASSERTED',**chunk}
    if end<chunk['coverage']['total']:result['next_read']=handle(project,{**query,'offset':end})
    return result


def read(root,project,payload):
    from laplace.manuscript import manuscript_proposals as owner
    from laplace.core import identity_doors
    from laplace.manuscript import proposal_currentness
    from laplace.pipeline import registry
    query=dict(payload);unknown=set(query)-set(contract()['properties'])
    if unknown:raise ValueError('Unknown proposal read fields: '+','.join(sorted(unknown)))
    if query.get('view')=='edit' and query.get('part') in {'original','proposed'}:
        from jsonschema import Draft202012Validator
        if isinstance(query.get('offset'),str) and query['offset'].isdigit():query['offset']=int(query['offset'])
        error=next(Draft202012Validator(contract()).iter_errors(query),None)
        if error:raise ValueError('Invalid immutable proposal text read: '+error.message)
        return stored_text_part(writing_records.index(root),project,query)
    if query.get('view') in {'resolution','resolution-preview'}:
        from jsonschema import Draft202012Validator
        from laplace.manuscript import reconciliation
        error=next(Draft202012Validator(contract()).iter_errors(query),None)
        if error:raise ValueError('Invalid resolution read: '+error.message)
        if registry.resolve(project,repo_root=root) is None:raise ValueError('Select a registered project.')
        idx=writing_records.index(root)
        if query.get('read_id'):
            retained=writing_records.selected_journal_fields(project,query['read_id'],root,
                fields=['record','operation','payload','resolution_read'])
            original=retained.get('payload') or {};guard=retained.get('resolution_read') or {}
            if retained.get('record')!='writing-tool-read' or retained.get('operation')!='authoring/proposal-preview' or not guard:
                raise ValueError('The exact resolution read receipt is unavailable.')
            if any(query.get(key)!=original.get(key) for key in ('id','proposal_version','edit_id','view')):
                raise ValueError('Resolution part coordinates differ from the exact retained read.')
            if any(key in query for key in RESOLUTION_INPUT_FIELDS):
                raise ValueError('A retained resolution part uses its exact admitted read inputs; do not replace them.')
            query={**{key:value for key,value in original.items() if key!='project'},
                **{key:guard[key] for key in ('target','resolution_token','input_observations')},
                **{key:query[key] for key in ('part','hunk_id','field','offset','hunk_offset') if key in query}}
        canonical=carrier_scope(idx,project,query)
        standalone=any(row.get('candidate_kind')=='current-source-resolution' for row in idx.by_id.get(canonical['id'],[]))
        values={key:value for key,value in canonical.items() if key not in {'id','view','record_id','proposal_version','read_id','part','hunk_id','field','offset','hunk_offset'}}
        values.update({'candidate_ref':{'id':canonical['id'],'version':canonical['proposal_version']}} if standalone
                      else {'turn_id':canonical['id'],'proposal_version':canonical['proposal_version']})
        result=(reconciliation.prepare if query['view']=='resolution' else reconciliation.preview)(root,project,values)
        if values.get('resolution_token') and result.get('resolution_token')!=values['resolution_token']:
            raise ValueError('CHANGED_INPUT: resolution source or predecessor changed since this exact read.')
        if payload.get('read_id') and reconciliation.digest(result)!=guard.get('state_sha256'):
            raise ValueError('CHANGED_INPUT: the exact resolution read state changed; retain choices and inspect a new preparation.')
        return result
    for key,value in query.items():
        if key!='limit' and not isinstance(value,str):raise ValueError('Proposal '+key+' must be a string.')
    raw_limit=query.get('limit',20)
    if isinstance(raw_limit,bool) or not str(raw_limit).isdigit():raise ValueError('Proposal limit must be an integer.')
    limit=int(raw_limit)
    if not 1<=limit<=20:raise ValueError('Proposal limit must be1..20.')
    view=query.get('view') or ('summary' if query.get('id') else 'queue')
    if view not in contract()['properties']['view']['enum']:raise ValueError('Unknown proposal view.')
    if query.get('id'):
        if view in {'queue','history'}:raise ValueError('An exact proposal requires a detail projection.')
        paged=('cursor','limit') if view=='changed-reads' else ()   # its own page cursor, never a queue cut
        if any(key in query and key not in paged for key in ('session_id','work_id','file','cursor','as_of','limit')):
            raise ValueError('Exact proposal detail is a fresh current-source read; queue filters/cuts are not accepted.')
        if 'limit' in query:query['limit']=limit
        if query.get('turn_id') and query['turn_id']!=query['id']:raise ValueError('Conflicting turn identities.')
    else:
        if view not in {'queue','history'} or any(key in query for key in ('record_id','proposal_version','edit_id')):
            raise ValueError('Detail/version/edit/basis projections require an exact proposal turn id.')
    if registry.resolve(project,repo_root=root) is None:raise ValueError('Select a registered project.')
    # ONE LOCK ORDER: the journal fold lock before the metadata index lock. The fold refresh (records._fold._records,
    # under every rich session read and reply bank) takes fold then index; this read used to take index and then,
    # inside proposal_currentness.proposal_view and manuscript_proposals.preview, fold, and the two orders together
    # froze the process. Taking fold first keeps the same single index cut and makes those inner fold reads reentrant.
    from laplace.writing import turn_jobs
    with turn_jobs._LOCK, writing_records.index_lock:
        idx=writing_records.index(root)
        if query.get('id'):return _detail(idx,project,query,view)
        candidates=[row for row in idx.by_project.get(project,[]) if row.get('has_proposal') and row.get('candidate_kind')!='profile-change']
        candidates.sort(key=lambda row:row['_order'],reverse=True)
        if query.get('session_id'):candidates=[row for row in candidates if (idx.turns.get(row.get('turn_id')) or {}).get('session_id')==query['session_id']]
        if query.get('turn_id'):candidates=[row for row in candidates if row.get('turn_id')==query['turn_id']]
        if query.get('work_id'):candidates=[row for row in candidates if (idx.turns.get(row.get('turn_id')) or {}).get('work_id')==query['work_id']]
        selected_id=query.get('id')
        if selected_id:
            return _detail(idx,project,query,view)
        identity=canonical_digest({'project':project,'query':{key:val for key,val in query.items() if key not in ('cursor','as_of','limit')}})
        cursor=capture.decode_cut(query['cursor']) if query.get('cursor') else None
        token=capture.decode_cut(query['as_of']) if query.get('as_of') else cursor
        if any(value and value['query']!=identity for value in (cursor,token)):raise ValueError('Proposal continuation belongs to another scope.')
        if cursor and token and any(cursor.get(key)!=token.get(key) for key in ('query','upper','revision')):raise ValueError('Proposal cursor and cut disagree.')
        upper=token['upper'] if token else idx.order
        candidates=[row for row in candidates if row['_order']<=upper]
        revision=canonical_digest([(row.get('id'),row['_hash']) for row in idx.rows if idx.project(row)==project and row['_order']<=upper])
        if token and token['revision']!=revision:raise ValueError('Proposal owner history changed; refresh the queue.')
        offset=(cursor or {}).get('offset',0);page=candidates[offset:offset+limit]
        rows=[];unavailable=[];seen=set();projected_page=[];opened=0
        for meta in page:
            budget=[1,0]
            try:proposal=_projection(idx,meta,budget)
            except ValueError:
                unavailable.append(meta.get('id'));continue
            opened+=budget[1]
            if proposal is None:unavailable.append(meta.get('id'));continue
            projected_page.append((meta,proposal))
        records,_unused=_records(idx,project,body_budget=0,upper=upper)
        for meta,proposal in projected_page:
            if meta.get('candidate_kind')=='current-source-resolution':
                ref={'id':meta['id'],'version':meta['proposal_instance_version']}
                applications=[row for row in idx.by_candidate.get(meta['id'],[]) if row['record']=='writing-application']
                applied=any(row.get('complete') for row in applications)
                retired=any(row.get('decision')=='resolved-into-successor' and row.get('proposal_version')==ref['version']
                    for row in idx.by_candidate.get(meta['id'],[]) if row['record']=='writing-proposal-decision')
                if view!='history' and (applied or retired):continue
                files=sorted({edit['file'] for edit in proposal['edits']})
                if query.get('file') and query['file'] not in files:continue
                rows.append({'id':meta['id'],'candidate_ref':ref,'origin_turn_id':meta.get('origin_turn_id'),
                    'project':project,'proposal_label':'Current-source revision','label_basis':'owner-type',
                    'proposal_version':ref['version'],'proposal_state':'applied' if applied else 'resolved-into-successor' if retired else 'pending',
                    'edit_count':len(proposal['edits']),'files':files,'turn_ts':meta.get('ts'),
                    'basis_currentness':'NOT_CHECKED','allowed_actions':[],
                    'read_handle':handle(project,{'id':meta['id'],'proposal_version':ref['version'],'view':'preview'})})
                continue
            turn=records['turns'].get(meta.get('turn_id'))
            if not turn:unavailable.append(meta.get('id'));continue
            version=meta.get('proposal_instance_version') or proposal['content_sha256']
            if (turn['id'],version) in seen:continue
            seen.add((turn['id'],version))
            projected=proposal_currentness.proposal_view(turn,records=records,version=version)
            state=projected.get('proposal_state')
            if view!='history' and (not projected.get('proposal') or state in {'applied','rejected','consumed-alternative','applied-elsewhere','superseded','resolved-into-successor'}):continue
            remaining=(projected.get('proposal') or {}).get('edits') or []
            if query.get('file') and not any(edit.get('file')==query['file'] for edit in remaining):continue
            application=turn.get('application') or {}
            app_summary={key:application.get(key) for key in ('id','complete','candidate_version','candidate_edit_ids','origin','approval_mode','ts') if key in application}
            if app_summary:app_summary['detail']={'turn_id':turn['id'],'view':'application','item_id':application.get('id')}
            session=idx.sessions.get(turn.get('session_id')) or {}
            title=session.get('title') or next((item.get('catalogue_display_title') for item in idx.by_session.get(turn.get('session_id'),[]) if item.get('catalogue_display_title')),None)
            context=turn.get('workspace_context') or {}
            label=str(context.get('label') or '').strip()
            rows.append({'id':turn['id'],'turn_id':turn['id'],'project':project,'session_id':turn.get('session_id'),
                'proposal_label':label or 'Manuscript proposal','label_basis':'stored-turn-context' if label else 'owner-type',
                'label_truncated':bool(context.get('label_truncated')),'turn_ts':turn.get('ts'),
                'conversation_title':title or 'Conversation '+str(turn.get('session_id') or ''),'application':app_summary or None,'proposal_version':version,'proposal_state':state,'edit_count':len(remaining),'files':sorted({edit['file'] for edit in remaining}),
                'basis_currentness':'NOT_CHECKED','allowed_actions':[],
                'identities':identity_doors.identities(('proposal',project+'::'+turn['id'],version)),
                'action_basis':'Exact current-source preview is required; queue metadata is not mutation authority.',
                'read_handle':handle(project,{'id':turn['id'],'record_id':meta['id'],'proposal_version':version,'view':'summary'})})
        cut={'v':1,'query':identity,'upper':upper,'revision':revision};next_read=None
        if offset+len(page)<len(candidates):next_read=handle(project,{**query,'cursor':capture.encode_cut({**cut,'offset':offset+len(page)}),'limit':limit})
        return {'project':project,'view':view,'proposals':rows,'count':len(rows),'count_basis':'current rows on this inspected page; total unknown until complete traversal',
            'as_of':capture.encode_cut(cut),'pagination':{'examined':len(page),'candidate_total':len(candidates),'remaining_candidates':max(0,len(candidates)-offset-len(page)),'next_read':next_read},
            'scope_basis':'Queue lifecycle at retained owner cut; exact child reads inspect fresh source and do not renew old candidate basis.',
            'coverage':{'unavailable_candidate_records':unavailable,'body_reads':opened,'body_read_basis':'Only this selected candidate page; enrichment is disposable metadata','historical_bodies_returned':False},'read_handle':handle(project,query)}


def _detail(idx,project,query,view):
    # One invocation-local ledger for the whole selected preparation: for changed-reads it is the preparation budget,
    # opened BEFORE any carrier projection (legacy carriers included) and released before evidence is observed;
    # otherwise it only observes, so custody counts are actual reads at every depth.
    import contextlib
    with contextlib.ExitStack() as stack:
        stack.enter_context(core_bodies.budget(PREPARATION_BYTES if view=='changed-reads' else None))
        return _detail_scoped(idx,project,query,view,stack.close)


def _detail_scoped(idx,project,query,view,release):
    from laplace.manuscript import manuscript_proposals as owner
    from laplace.manuscript import proposal_currentness
    profiles_meta=[row for row in idx.by_id.get(query['id'],[]) if row.get('candidate_kind')=='profile-change' and idx.project(row)==project]
    if profiles_meta:
        if len(profiles_meta)!=1: raise ValueError('The profile carrier is ambiguous; inspect its exact family owner.')
        from laplace.manuscript import profiles
        ref={'id':profiles_meta[0]['id'],'version':query.get('proposal_version') or profiles_meta[0]['proposal_instance_version']}
        if view not in {'summary','preview'}: raise ValueError('This is a profile preference candidate. Read its exact profile-candidate owner, not paragraph hunks.')
        return profiles.inspect(project,{'view':'candidate','candidate_ref':ref},idx.root)
    query=carrier_scope(idx,project,query);tid=query['id'];detail=_work(PREPARATION_RECORDS if view=='changed-reads' else None)
    human=[row for row in idx.by_id.get(tid,[]) if row.get('candidate_kind')=='current-source-resolution' and idx.project(row)==project]
    if len(human)==1:
        from laplace.manuscript import reconciliation
        ref={'id':tid,'version':query.get('proposal_version') or human[0]['proposal_instance_version']}
        result=reconciliation.read_candidate(idx.root,project,ref,render=view=='preview')
        if view=='summary':result['edits']=[{**owner.edit_metadata(row),**{key:row.get(key) for key in ('edit_id','status','candidate_ref','application_source_state')}} for row in result['edits']]
        return result
    turn=idx.turns.get(tid)
    if not turn or idx.project(turn)!=project:raise ValueError('This proposal belongs to another project or is unavailable.')
    candidates=[row for row in idx.by_turn.get(tid,[]) if row.get('has_proposal')]
    selected=None
    if query.get('record_id'):
        matching=[row for row in candidates if row.get('id')==query['record_id']]
        if len(matching)!=1:raise ValueError('Exact proposal record is missing or ambiguous.')
        selected=matching[0]
        # a sealed carrier names its own version; only a pre-instance carrier is projected (inside the preparation)
        known=selected.get('proposal_instance_version') or (_projection(idx,selected,[1,0],detail) or {}).get('content_sha256')
        if query.get('proposal_version') and query['proposal_version']!=known:raise ValueError('Selected record/version identities disagree.')
    elif not query.get('proposal_version'):
        selected=next(iter(reversed(candidates)),None)
    else:
        selected=next((row for row in reversed(candidates) if query['proposal_version']==row.get('proposal_instance_version')
            or query['proposal_version']==(row.get('proposal_projection') or {}).get('content_sha256')),None)
        if selected is None:
            # An explicit historical version can predate indexed component headers.
            # Inspect only this selected turn's candidate bodies, never other turns.
            for row in reversed(candidates):
                if row.get('proposal_projection'):continue
                projection=_projection(idx,row,[1,0],detail)
                if projection and query['proposal_version']==projection['content_sha256']:
                    selected=row;break
    if selected is None:raise ValueError('Exact saved proposal version is unavailable.')
    basis=selected.get('proposal_basis') or {}
    required={tid,selected['id'],basis.get('turn_basis_record_id'),*basis.get('read_ids',[])}
    if not selected.get('proposal_basis'):
        prior=[row for row in idx.by_turn.get(tid,[]) if row['_order']<selected['_order']]
        required.update(row['id'] for row in prior if row['record'] in {'writing-tool-read','writing-tool-read-baseline'})
        last_basis=next((row for row in reversed(prior) if row['record']=='writing-turn-context-baseline'),None)
        if last_basis:required.add(last_basis['id'])
    selected_version=query.get('proposal_version') or selected.get('proposal_instance_version') or (selected.get('proposal_projection') or {}).get('content_sha256')
    required.update(row['id'] for row in idx.by_turn.get(tid,[]) if row['record']=='writing-application' and row.get('candidate_version')==selected_version)
    records=selected_records(idx.root,project,tid,selected_version,work=detail if view=='changed-reads' else None)
    opened=records['coverage']['body_reads']
    version=query.get('proposal_version') or selected.get('proposal_instance_version') or writing_records.proposal_digest(_body(idx,selected,'proposal',detail))
    selected_turn=owner.select_version(records['turns'][tid],version)
    original=owner.original_proposal(selected_turn)
    if view=='changed-reads':
        # the candidate's changed consulted reads, in bounded pages through the same currentness owner (CR-R1)
        from laplace.manuscript.proposal_currentness import changed_read_page
        sealed,_=owner.proposal_version(selected_turn)
        # one preparation (carrier projection + selection) under one budget; evidence is observed after it is released
        ledger=core_bodies.active_budget()
        coverage={'whole_history_loaded':False,**records['coverage'],**{key:value for key,value in detail.items() if key!='records_limit'},
            'budget':{'records':PREPARATION_RECORDS,'bytes':ledger['limit'],'spent':ledger['spent']}}
        release()
        return changed_read_page(idx.root,selected_turn,sealed,owner.saved_proposals(selected_turn).get(sealed) or {},records=records,
            cursor=query.get('cursor'),limit=query.get('limit') or 8,coverage=coverage)
    if query.get('edit_id') and query['edit_id'] not in {owner.edit_id(edit) for edit in original.get('edits') or []}:
        raise ValueError('Exact selected edit is unavailable in this proposal version.')
    linked=set()
    for matches in proposal_currentness.refinements_for_edits(records,selected_turn,original).values():
        linked.update(item['id'] for item in matches)
    linked.update(item['application_id'] for item in owner.decisions(selected_turn,version).values() if item.get('application_id'))
    for record_id in linked:
        meta=next((row for row in idx.by_id.get(record_id,[]) if row.get('record')=='writing-application' and idx.project(row)==project),None)
        if meta:
            full=_resolved(_opened(idx,meta,detail,'linked-application'),idx.root,detail)
            owner_turn=records['turns'].get(meta.get('turn_id'))
            if owner_turn:
                owner_turn['applications']=[full if app.get('id')==record_id else app for app in owner_turn.get('applications',[])]
                if (owner_turn.get('application') or {}).get('id')==record_id:owner_turn['application']=full
    result=owner.preview(idx.root,project,tid,version,records=records,render=view=='preview',selected_edit=query.get('edit_id',''))
    for edit in result['edits']:
        edit['read_handle']=handle(project,{'id':tid,'record_id':selected['id'],'proposal_version':version,'edit_id':edit['edit_id'],'view':'edit'})
        edit['basis_read']=handle(project,{'id':tid,'record_id':selected['id'],'proposal_version':version,'edit_id':edit['edit_id'],'view':'basis'})
        edit['preview_read']=handle(project,{'id':tid,'record_id':selected['id'],'proposal_version':version,'edit_id':edit['edit_id'],'view':'preview'})
    if view=='summary':
        result.pop('answer',None)
        result['edits']=[{key:edit.get(key) for key in ('edit_id','file','line_start','line_end','status','lifecycle','candidate_id','basis_currentness','basis_reason','allowed_actions','read_handle','basis_read','preview_read','successor_ref','successor_read','resolution_application_id','resolution_note','disposition_status','pending_successors')} for edit in result['edits']]
    elif view=='basis':result['edits']=[{key:edit.get(key) for key in ('edit_id','file','basis','basis_currentness','basis_reason','target_proof','source_anchor','allowed_actions','basis_read')} for edit in result['edits']]
    result['read_handle']=handle(project,{'id':tid,'record_id':selected['id'],'proposal_version':version,'view':view,**({'edit_id':query['edit_id']} if query.get('edit_id') else {})})
    result['carrier_ref']={'id':selected['id'],'version':version}
    # remaining counts the returned owner rows; selected body is not the parent total.
    result['read_scope']={'kind':'selected-edit' if query.get('edit_id') else 'candidate',
        'selected_edit_id':query.get('edit_id') or None,'remaining_scope':'returned-edits'}
    result['coverage']={'selected_candidate_bodies':1,'whole_history_loaded':False,'related_body_reads':opened+detail['raw_records'],
        'raw_line_bytes':records['coverage']['raw_line_bytes']+detail['raw_line_bytes'],
        'custody_reads':records['coverage']['custody_reads']+detail['custody_reads'],'custody_bytes':records['coverage']['custody_bytes']+detail['custody_bytes']}
    return result
