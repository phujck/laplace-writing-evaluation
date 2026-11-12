"""Current resolved revisions in the existing proposal/application custody.

Historical provider turns are provenance only. A resolved candidate is an exact
writing-proposal record, never a fabricated writing-turn or a second ledger.
"""
from __future__ import annotations

from laplace.core import scoped as core_scoped
import difflib
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlencode
import uuid

SCHEMA='laplace.proposal-resolution/1'
# Same UTF-8 payload limit as the existing explicit merged_after owner.
MAX_TEXT=2_000_000
# Bound optional fine comparison work, never the retained or editable prose.
MAX_COMPARE_PAIRS=262_144
MAX_COMPARE_REGIONS=128
COARSE_REASON='Fine comparison work is bounded. This change groups a complete passage; inspect or edit its full text. No text has been omitted.'
TARGET_GUARDS=('file','line_start','line_end','expected_source_digest','expected_selection')
NATIVE_TEXT_BYTES=4096
NATIVE_RESPONSE_BYTES=8_000
NATIVE_HUNKS=6


def digest(value):
    return 'sha256:'+hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
        separators=(',',':')).encode()).hexdigest()


def _selected(root,project,ident,fields):
    from laplace.writing import records
    return records.selected_journal_fields(project,ident,root,fields=fields)


def resolve(root,project,payload):
    """Resolve one exact carrier and its original association, not rich history."""
    from laplace.writing import records
    idx=records.index(root);ref=payload.get('candidate_ref')
    if ref:
        row=_selected(root,project,ref['id'],['id','record','project','proposal','proposal_instance_version',
            'proposal_basis','document','predecessor','resolution','origin_turn_id','author','review_obligations','candidate_kind'])
        if row.get('record')!='writing-proposal' or row.get('candidate_kind')!='current-source-resolution':
            raise ValueError('candidate_ref must name an exact current-source proposal carrier.')
        if row.get('proposal_instance_version')!=ref['version']:raise ValueError('The current-source candidate version changed or was not inspected.')
        return row
    tid=payload.get('turn_id');version=payload.get('proposal_version')
    if not tid or not version:raise ValueError('Select an exact historical proposal version or candidate_ref.')
    turn=idx.turns.get(tid)
    if not turn or idx.project(turn)!=project:raise ValueError('The selected proposal belongs to another project or is unavailable.')
    candidates=[row for row in idx.by_turn.get(tid,[]) if row.get('has_proposal')
        and row.get('proposal_instance_version')==version]
    if len(candidates)>1:
        identities={(item.get('proposal_projection') or {}).get('content_sha256') for item in candidates}
        minted=[item for item in candidates if item['record']=='writing-proposal']
        if len(identities)==1 and None not in identities and minted:candidates=[minted[0]]
    if len(candidates)!=1:
        # Legacy content aliases can be inspected only when exactly one carrier
        # in this selected turn has that identity; they are never fresh authority.
        candidates=[row for row in idx.by_turn.get(tid,[]) if row.get('has_proposal')
            and (row.get('proposal_projection') or {}).get('content_sha256')==version]
    if len(candidates)!=1:raise ValueError('The exact historical candidate is missing or ambiguous.')
    row=_selected(root,project,candidates[0]['id'],['id','record','proposal','proposal_basis','proposal_instance_version'])
    origin=_selected(root,project,tid,['id','document','selection','dependencies','project'])
    return {**row,'project':project,'document':origin.get('document'),'origin_turn_id':tid,
        'origin_subject':origin,'selected_version':version}


def subject(row,edit_id):
    if row.get('candidate_kind')=='current-source-resolution':
        return {'candidate_ref':{'id':row['id'],'version':row['proposal_instance_version']},'edit_id':edit_id}
    return {'turn_id':row['origin_turn_id'],'proposal_version':row.get('selected_version') or row['proposal_instance_version'],'edit_id':edit_id}


def action(project,decision,payload):
    from laplace.core import grammar
    values={'project':project,**payload,'decision':decision}
    inspecting=decision in {'prepare-resolution','preview-resolution'}
    native_values=values
    if inspecting:
        native_values={key:value for key,value in payload.items() if key not in {'turn_id','candidate_ref'}}
        ref=payload.get('candidate_ref') or {}
        native_values.update(id=payload.get('turn_id') or ref.get('id'),
            proposal_version=payload.get('proposal_version') or ref.get('version'),
            view='resolution' if decision=='prepare-resolution' else 'resolution-preview')
    return {'project':project,'operation':'authoring/proposal-decision','permitted':True,
        'http':{'method':'POST','url':'/authoring/proposal-decision'},
        'payload':values,'native_request':{'verb':'read' if inspecting else 'delete','concept':'proposal@paragraph',
            'target':project+'::'+str(payload.get('turn_id') or (payload.get('candidate_ref') or {}).get('id') or ''),
            'expected':[],'payload':grammar.to_payload(native_values),'by':''}}


def target_files(root,project):
    from laplace.manuscript import manuscript_source
    source=manuscript_source.resolve(project,repo_root=root,include_candidates=False)
    tree=manuscript_source.traversal(root/source['root'],root)
    return [{'file':name,'label':Path(name).name,'read':{'http':{'method':'GET','url':
        '/projection/tex?'+urlencode({'corpus':project,'file':name,'view':'source'})}}}
        for name in tree.get('files') or []]


def _target(root,project,row,edit,offered):
    from laplace.manuscript import manuscript_source, proposal_preflight
    from laplace.manuscript import proposal_currentness
    source=manuscript_source.resolve(project,repo_root=root,include_candidates=False)
    if not source.get('root') or source.get('read_only'):raise ValueError('An editable current manuscript is required.')
    md=(root/source['manuscript_dir']).resolve()
    previous=row.get('document') or {}
    if offered is None:
        if any(previous.get(key)!=source.get(key) for key in ('root','manuscript_dir','edition')):
            return source,None,'The historical candidate belongs to another edition. Choose an inspected current passage explicitly.'
        path=proposal_preflight._resolve(root,md,edit['file'])
        if path is None:return source,None,'The historical file is unavailable; choose a current passage.'
        raw,facts=proposal_currentness._source_text_facts(path.read_bytes())
        span=proposal_preflight.proven_current_span(raw,edit,turn=row.get('origin_subject') or row,root=root,path=path)
        if span is None:return source,None,'Historical offsets do not prove a current occurrence. Choose an inspected current passage explicitly.'
        lo,hi=span
        offered={'file':path.relative_to(root).as_posix(),'line_start':lo,'line_end':hi,
            'before':'\n'.join(raw.split('\n')[lo-1:hi]),'expected_source_digest':facts['byte_sha256'],
            'expected_selection':manuscript_source.selection_identity(source,project)}
    else:offered=dict(offered)
    if any(key not in offered or offered[key] is None for key in TARGET_GUARDS):
        raise ValueError('Choose an inspected current passage with exact file, range, source and selection guards.')
    path=proposal_preflight._resolve(root,md,offered.get('file',''))
    if path is None:raise ValueError('The explicit target must be current manuscript source.')
    manuscript_source.source_access(project,path,root,writable=True,
        expected_selection=offered.get('expected_selection'),source=source)
    raw,facts=proposal_currentness._source_text_facts(path.read_bytes())
    if offered.get('expected_source_digest')!=facts['byte_sha256']:
        raise ValueError('CHANGED_INPUT: current source changed; retain choices and inspect the target again.')
    lo,hi=offered.get('line_start'),offered.get('line_end')
    if type(lo)!=int or type(hi)!=int or lo<1 or hi<lo or hi>len(raw.split('\n')):
        raise ValueError('Choose a complete exact current source span.')
    before='\n'.join(raw.split('\n')[lo-1:hi])
    if 'before' in offered and before!=offered['before']:
        raise ValueError('CHANGED_INPUT: inspected current passage does not match its source.')
    offered['before']=before
    offered['file']=path.relative_to(root).as_posix()
    offered['source_anchor']=proposal_preflight.source_anchor(raw,lo,hi)
    return source,offered,None


def _span(opcodes,lo,hi):
    spans=[]
    for tag,a,b,c,d in opcodes:
        if a==b:
            if lo<=a<=hi:spans.append((c,d))
        elif a<hi and lo<b:
            if tag=='equal':spans.append((c+max(a,lo)-a,c+min(b,hi)-a))
            else:spans.append((c,d))
    if spans:return min(row[0] for row in spans),max(row[1] for row in spans)
    for tag,a,b,c,d in opcodes:
        if a<=lo<=b:return (c+lo-a,c+lo-a) if tag=='equal' else (c,c)
    return (opcodes[-1][4],)*2 if opcodes else (0,0)


def _comparison(a,b,budget):
    """Linear equality/edge/sparse-alignment paths, bounded optional matching."""
    if a==b:return [('equal',0,len(a),0,len(b))],False
    prefix=0
    while prefix<min(len(a),len(b)) and a[prefix]==b[prefix]:prefix+=1
    suffix=0
    while suffix<min(len(a),len(b))-prefix and a[len(a)-suffix-1]==b[len(b)-suffix-1]:suffix+=1
    end_a=len(a)-suffix;end_b=len(b)-suffix
    x=a[prefix:end_a];y=b[prefix:end_b]
    leading=[('equal',0,prefix,0,prefix)] if prefix else []
    trailing=[('equal',end_a,len(a),end_b,len(b))] if suffix else []
    if not x or not y:
        return leading+[('insert' if not x else 'delete',prefix,end_a,prefix,end_b)]+trailing,False
    # Repetitive prose with a few substitutions has exact aligned equal runs;
    # asking a quadratic matcher to rediscover those runs is unnecessary.
    if len(x)==len(y):
        changed=[];start=None;count=0
        for index,(old,new) in enumerate(zip(x,y)):
            if old!=new:
                count+=1
                if start is None:start=index
            elif start is not None:changed.append((start,index));start=None
        if start is not None:changed.append((start,len(x)))
        if count<=max(8,len(x)//8) and len(changed)<=MAX_COMPARE_REGIONS:
            ops=[];cursor=0
            for lo,hi in changed:
                if cursor<lo:ops.append(('equal',prefix+cursor,prefix+lo,prefix+cursor,prefix+lo))
                ops.append(('replace',prefix+lo,prefix+hi,prefix+lo,prefix+hi));cursor=hi
            if cursor<len(x):ops.append(('equal',prefix+cursor,end_a,prefix+cursor,end_b))
            return leading+ops+trailing,False
    pairs=len(x)*len(y)
    if pairs<=budget[0]:
        budget[0]-=pairs
        middle=difflib.SequenceMatcher(a=x,b=y,autojunk=False).get_opcodes()
        if sum(tag!='equal' for tag,*_ in middle)<=MAX_COMPARE_REGIONS:
            return leading+[(tag,lo+prefix,hi+prefix,start+prefix,end+prefix)
                for tag,lo,hi,start,end in middle]+trailing,False
    # Preserve complete interior bytes and exact prefix/suffix. The author can
    # choose either complete passage or edit it; this is not a rejection/truncation.
    return leading+[('replace',prefix,end_a,prefix,end_b)]+trailing,True


def _unit_hunks(base,mine,theirs,predecessor,*,region=None,offset=0,budget=None):
    budget=budget if budget is not None else [MAX_COMPARE_PAIRS]
    left,left_coarse=_comparison(base,mine,budget);right,right_coarse=_comparison(base,theirs,budget)
    regions=sorted((a,b) for tag,a,b,_,_ in left+right if tag!='equal')
    merged=[]
    for lo,hi in regions:
        if merged and (lo<merged[-1][1] or lo==hi==merged[-1][1] or merged[-1][0]==merged[-1][1]==lo):
            merged[-1]=(merged[-1][0],max(hi,merged[-1][1]))
        elif not merged or (lo,hi)!=merged[-1]:merged.append((lo,hi))
    coarse=left_coarse or right_coarse
    if len(merged)>MAX_COMPARE_REGIONS:
        merged=[(merged[0][0],merged[-1][1])];coarse=True
    if not merged:return []
    mine_offsets=[offset]
    for unit in mine:mine_offsets.append(mine_offsets[-1]+len(unit))
    out=[]
    for lo,hi in merged:
        a,b=_span(left,lo,hi);c,d=_span(right,lo,hi)
        old=''.join(base[lo:hi]);now=''.join(mine[a:b]);new=''.join(theirs[c:d])
        out.append({'id':'HUNK-'+digest([predecessor,region,lo,hi,old,now,new]).removeprefix('sha256:')[:24],
            'original':old,'current':now,'proposed':new,'original_range':[lo,hi],
            'current_range':[mine_offsets[a],mine_offsets[b]],
            **({'comparison_scope':'coarse','comparison_reason':COARSE_REASON} if coarse else {}),
            'kind':'proposal' if now==old else 'current' if new==old else 'conflict','default_choice':'current'})
    return out


def hunks(original,current,proposed,predecessor):
    """Owner diff3 regions, refining separated changes inside one source line.

    Coordinates address exact current characters only inside this owner. Neither
    visual highlights nor caller coordinates grant application authority.
    """
    budget=[MAX_COMPARE_PAIRS]
    rows=_unit_hunks(original.splitlines(keepends=True),current.splitlines(keepends=True),
        proposed.splitlines(keepends=True),predecessor,budget=budget)
    result=[]
    for row in rows:
        pieces=[row[key] for key in ('original','current','proposed')]
        if all('\n' not in text.rstrip('\n') for text in pieces):
            units=[re.findall(r'\s+|[^\s]+',text) for text in pieces]
            refined=_unit_hunks(*units,predecessor,region=row['original_range'],offset=row['current_range'][0],budget=budget)
            if len(refined)>1:result.extend(refined)
            else:
                if refined and refined[0].get('comparison_scope')=='coarse':
                    row.update(comparison_scope='coarse',comparison_reason=COARSE_REASON)
                result.append(row)
        else:result.append(row)
        if len(result)>MAX_COMPARE_REGIONS:
            return [{'id':'HUNK-'+digest([predecessor,'complete-passage',original,current,proposed]).removeprefix('sha256:')[:24],
                'original':original,'current':current,'proposed':proposed,'current_range':[0,len(current)],
                'kind':'proposal' if current==original else 'current' if proposed==original else 'conflict',
                'default_choice':'current','comparison_scope':'coarse','comparison_reason':COARSE_REASON}]
    return result


def prepare(root,project,payload,*,actor=None):
    from laplace.manuscript import manuscript_proposals, proposal_basis
    root=Path(root).resolve();row=resolve(root,project,payload)
    edit=next((item for item in row['proposal']['edits'] if manuscript_proposals.edit_id(item)==payload.get('edit_id')),None)
    if edit is None:raise ValueError('The exact predecessor edit is unavailable.')
    source,target,reason=_target(root,project,row,edit,payload.get('target'))
    selected=subject(row,payload['edit_id'])
    result={'schema_version':SCHEMA,'project':project,'subject':selected,
        'original':edit['before'],'proposed':edit['after'],'target_required':target is None,
        'target_files':target_files(root,project),'predecessor':{'record_id':row['id'],**selected}}
    if target is None:return {**result,'reason':reason,'current':None,'hunks':[],
        'resolution_action':action(project,'prepare-resolution',selected)}
    token=digest({'predecessor':result['predecessor'],'target':target})
    basis=proposal_basis.assess(root,project,{**edit,**target},selected_source=source)
    observations=payload.get('input_observations') or {key:basis[key] for key in ('develops','evidence','automatic_section_concepts')}
    # One subject form for this result in every phase: the exact predecessor edit (validate_candidate reads the same).
    reviewed=result['predecessor']
    obligations=core_scoped.merge([core_scoped.obligation('SEMANTIC_REVIEW_REQUIRED',reason,subject=reviewed) for reason in basis.get('errors') or []])
    if edit.get('develops') or edit.get('evidence_refs'):
        obligations.append(core_scoped.obligation('SOURCE_REVISION_REVIEW_REQUIRED',
            'This current-source revision does not renew the predecessor scientific acceptance.',subject=reviewed))
    values={**selected,'resolution_token':token,'target':{key:target[key] for key in TARGET_GUARDS},
        'input_observations':observations}
    changes=hunks(edit['before'],target['before'],edit['after'],result['predecessor'])
    comparison={'scope':'coarse' if any(row.get('comparison_scope')=='coarse' for row in changes) else 'exact-regions',
        'max_match_pairs':MAX_COMPARE_PAIRS,'max_regions':MAX_COMPARE_REGIONS}
    if comparison['scope']=='coarse':comparison['reason']=COARSE_REASON
    return {**result,'target':target,'current':target['before'],'resolution_token':token,
        'hunks':changes,'comparison':comparison,
        'input_observations':observations,'review_obligations':obligations,
        'basis':basis,'actions':{name:action(project,name+'-resolution',values) for name in ('preview','apply')}}


def preview(root,project,payload,*,actor=None):
    result=prepare(root,project,payload,actor=actor)
    if result['target_required']:raise ValueError(result['reason'])
    if payload.get('resolution_token')!=result['resolution_token']:
        raise ValueError('CHANGED_INPUT: resolution predecessor or current target changed; preserve choices and inspect again.')
    if ('choices' in payload)==('resolved_after' in payload):raise ValueError('Supply exact hunk choices or an explicitly authored full resolved_after.')
    if 'resolved_after' in payload:resolved=payload['resolved_after']
    else:
        choices=payload['choices']
        if not isinstance(choices,list) or len(choices)!=len(result['hunks']):raise ValueError('Choose every exact owner-issued hunk once.')
        by_id={row.get('hunk_id'):row for row in choices if isinstance(row,dict)}
        if set(by_id)!={row['id'] for row in result['hunks']}:raise ValueError('Hunk choices do not match this inspected comparison.')
        resolved=result['current']
        for hunk in reversed(result['hunks']):
            choice=by_id[hunk['id']];kind=choice.get('choice')
            if kind not in {'current','proposed','custom'}:raise ValueError('Choose current, proposed or custom for each hunk.')
            text=choice.get('text') if kind=='custom' else hunk[kind]
            if not isinstance(text,str):raise ValueError('Custom hunk text must be a string.')
            lo,hi=hunk['current_range'];resolved=resolved[:lo]+text+resolved[hi:]
    if not isinstance(resolved,str) or len(resolved.encode())>MAX_TEXT:raise ValueError('Resolved text must be bounded UTF-8 text.')
    return {**result,'resolved_after':resolved,'changed':resolved!=result['current']}


def validate_candidate(root,project,record,*,source=None):
    """Only new current-source authority is current; old scientific basis stays old."""
    from laplace.manuscript import proposal_basis
    edit=record['proposal']['edits'][0]
    _target(root,project,record,edit,record['proposal_basis']['target'])
    basis=proposal_basis.assess(root,project,edit,selected_source=source)
    subject_ref=record.get('predecessor')
    observed={key:basis[key] for key in ('develops','evidence','automatic_section_concepts')}
    obligations=core_scoped.merge(record.get('review_obligations'),
        [core_scoped.obligation('SEMANTIC_REVIEW_REQUIRED',reason,subject=subject_ref) for reason in basis.get('errors') or []],
        [core_scoped.obligation('DISPLAYED_SUPPORT_CHANGED','Supporting inputs changed after this comparison; safe source '
            'application does not accept the changed science.',subject=subject_ref)]
        if observed!=record['proposal_basis'].get('input_observations') else [])
    return {'currentness':'CURRENT','basis_kind':'current-source-resolution','semantic_currentness':core_scoped.semantic_currentness(obligations),
        'review_obligations':obligations,'transition_ids':[]}


def _candidate_subject(root,project,record):
    from laplace.writing import records
    version=record['proposal_instance_version'];ref={'id':record['id'],'version':version}
    idx=records.index(root)
    applications=[_selected(root,project,row['id'],['id','record','project','candidate_id','candidate_ref','candidate_version','candidate_edit_ids',
        'complete','edits','owned_changes','source_effect','receipts','rollbacks','origin','review_obligations',
        'actor','validation_basis','application_tracking','status','warning'])
        for row in idx.by_candidate.get(record['id'],[]) if row.get('record')=='writing-application']
    return {**record,'candidate_ref':ref,'pending_proposal':record['proposal'],
        '_selected_proposal_version':version,'proposal_versions':{version:record['proposal']},
        'proposal_bases':{version:record['proposal_basis']},'applications':applications,
        'proposal_decisions':[{key:value for key,value in row.items() if not key.startswith('_')}
            for row in idx.by_candidate.get(record['id'],[]) if row.get('record')=='writing-proposal-decision']}


def disposition(root,project,record,application):
    """Exact per-edit retirement, distinct from acceptance of the old proposal."""
    from laplace.writing import records
    predecessor=record.get('predecessor') or {};ref={'id':record['id'],'version':record['proposal_instance_version']}
    if not application or not application.get('complete') or not predecessor.get('edit_id'):
        return {'status':'NOT_APPLICABLE','successor_ref':ref}
    ident='DECISION-'+digest([ref,predecessor,application['id']]).removeprefix('sha256:')[:32]
    selected=[row for row in records.index(root).by_id.get(ident,[]) if row.get('record')=='writing-proposal-decision']
    if selected:
        old=predecessor.get('candidate_ref') or {}
        expected={'decision':'resolved-into-successor','proposal_version':old.get('version') or predecessor.get('proposal_version'),
            'edit_id':predecessor['edit_id'],'successor_ref':ref,'resolution_application_id':application['id'],
            **({'candidate_id':old['id']} if old else {'turn_id':predecessor['turn_id']})}
        if len(selected)!=1 or records.index(root).project(selected[0])!=project or any(selected[0].get(key)!=value for key,value in expected.items()):
            raise ValueError('The exact reconciliation disposition is ambiguous or has different custody bindings.')
    result={'status':'RECORDED' if selected else 'PENDING','successor_ref':ref,
        'resolution_application_id':application['id'],'predecessor':predecessor,'decision_id':ident}
    if not selected:
        result['recovery_action']={**action(project,'finish-resolution-record',{
            'candidate_ref':ref,'resolution_application_id':application['id'],'predecessor':predecessor}),
            'recovery_kind':'finalize-predecessor-only','title':'Finish reconciliation record'}
    return result


def pending_successors(root,project,ident,version,edit_id):
    """Indexed exact predecessor links; no project history/body traversal."""
    from laplace.writing import records
    from laplace.manuscript.proposal_navigation import handle
    idx=records.index(root);found=[]
    for candidate in idx.by_predecessor.get((project,ident,version,edit_id),[]):
        apps=[row for row in idx.by_candidate.get(candidate['id'],[]) if row.get('record')=='writing-application'
            and row.get('complete') and row.get('candidate_version')==candidate.get('proposal_instance_version')]
        if not apps:continue
        status=disposition(root,project,candidate,apps[-1])
        if status['status']!='PENDING':continue
        ref=status['successor_ref'];found.append({'successor_ref':ref,'resolution_application_id':apps[-1]['id'],
            'disposition_status':'PENDING','successor_read':handle(project,{'id':ref['id'],'proposal_version':ref['version'],'view':'preview'})})
    return found


def finish_resolution_record(root,project,payload,*,actor=None):
    """Metadata-only recovery from an exact completed application; no source lease."""
    from laplace.writing import records as writing_records
    record=resolve(root,project,payload);predecessor=record.get('predecessor') or {}
    if payload.get('predecessor')!=predecessor:raise ValueError('Finish the exact recorded predecessor edit; retargeting is refused.')
    app=_selected(root,project,payload.get('resolution_application_id'),['id','record','candidate_id','candidate_ref','candidate_version','complete','actor','source_effect'])
    ref=payload['candidate_ref']
    if (app.get('record')!='writing-application' or not app.get('complete') or app.get('candidate_id')!=record['id']
            or app.get('candidate_ref')!=ref or app.get('candidate_version')!=ref['version']):
        raise ValueError('Reconciliation disposition requires the exact completed successor application.')
    status=disposition(root,project,record,app)
    warning=None
    if status['status']=='PENDING':
        old=predecessor.get('candidate_ref')
        row={'record':'writing-proposal-decision','id':status['decision_id'],'project':project,
            **({'candidate_id':old['id']} if old else {'turn_id':predecessor['turn_id']}),
            'proposal_version':old['version'] if old else predecessor['proposal_version'],'edit_id':predecessor['edit_id'],
            'decision':'resolved-into-successor','resolution':'current-source-reconciliation',
            'successor_ref':ref,'successor_candidate_id':ref['id'],'resolution_application_id':app['id'],
            'actor':actor or {'kind':'human','basis':'explicit reconciliation record finalization'},
            'by':'eigen:session' if (actor or {}).get('kind')=='agent' else 'author'}
        with writing_records.proposal_write_lock(Path(root)):
            if disposition(root,project,record,app)['status']=='PENDING':
                try:writing_records.bank(Path(root),row)
                except (ValueError,OSError) as error:warning='Source application is saved; predecessor disposition publication is unproved: '+str(error)
    result={**read_candidate(root,project,ref),'metadata_only':True}
    if warning:result['warning']=warning
    return result


def read_candidate(root,project,ref,*,render=False):
    from laplace.manuscript import manuscript_proposals, proposal_navigation
    from laplace.manuscript import source_effects
    row=resolve(root,project,{'candidate_ref':ref});subject_row=_candidate_subject(root,project,row)
    application=next(iter(reversed(subject_row['applications'])),None)
    application_state=source_effects.application_source_state(root,application) if application else None
    retired=next((item for item in subject_row['proposal_decisions'] if item.get('proposal_version')==ref['version']
        and item.get('decision')=='resolved-into-successor'),None)
    state='applied' if application and application.get('complete') else 'resolved-into-successor' if retired else 'pending'
    apply_action=action(project,'apply-candidate',{'candidate_ref':ref}) if state=='pending' else None
    if apply_action:
        try:validate_candidate(root,project,row)
        except (ValueError,OSError) as error:
            apply_action={**apply_action,'permitted':False,'reason':str(error)}
    read=proposal_navigation.handle(project,{'id':ref['id'],'proposal_version':ref['version'],'view':'preview'})
    predecessor=row.get('predecessor') or {};previous=predecessor.get('candidate_ref')
    predecessor_read=proposal_navigation.handle(project,{
        'id':previous['id'] if previous else predecessor['turn_id'],
        'proposal_version':previous['version'] if previous else predecessor['proposal_version'],
        'edit_id':predecessor['edit_id'],'view':'preview',
        **({'record_id':predecessor['record_id']} if not previous and predecessor.get('record_id') else {})}) if previous or predecessor.get('turn_id') else None
    edits=[{**edit,'edit_id':manuscript_proposals.edit_id(edit),'status':'accepted' if state=='applied' else state,
            'candidate_ref':ref,'allowed_actions':[],
            **({'application_source_state':application_state} if application_state else {}),
            **({'successor_ref':retired['successor_ref'],'successor_read':proposal_navigation.handle(project,{
                'id':retired['successor_ref']['id'],'proposal_version':retired['successor_ref']['version'],'view':'preview'}),
                'resolution_application_id':retired['resolution_application_id']} if retired else {}),
            **({'resolution_action':action(project,'prepare-resolution',{'candidate_ref':ref,'edit_id':manuscript_proposals.edit_id(edit)})} if state=='pending' else {})}
        for edit in row['proposal']['edits']]
    if render:
        for edit in edits:
            edit['before_blocks']=render_blocks(root,project,row['document'],edit['file'],edit['before'])
            edit['after_blocks']=render_blocks(root,project,row['document'],edit['file'],edit['after'])
    return {'project':project,'id':ref['id'],'candidate_ref':ref,'proposal_version':ref['version'],
        'reviewable':True,'read_only':state!='pending','turn_active':False,
        'author':row['author'],'predecessor':row.get('predecessor'),'proposal_state':state,
        'predecessor_read':predecessor_read,'read_handle':read,'edits':edits,
        'application':application,'review_obligations':(application or row).get('review_obligations') or [],
        'apply_action':apply_action,'disposition':disposition(root,project,row,application)}


def render_blocks(root,project,source,file,text):
    from laplace.manuscript import walk, projection_viewer, manuscript_figure_preview
    md=root/source['manuscript_dir'];root_tex=root/source['root']
    blocks=walk.blocks_for(text,file_rel=file,repo_file=file,md=md,corpus=project,dir_param='',
        para_spans=projection_viewer.parse_paragraphs(text),known_macros=walk.preamble_macros(root_tex),
        declared_envs=manuscript_figure_preview.declared_environments(root_tex,root),
        declared_presentation=manuscript_figure_preview.declared_environment_presentation(root_tex,root))
    for block in blocks:block['suggestion']=True
    return blocks


def resolution_read_guard(value):
    """Exact state selected by an existing read receipt, without echoed prose."""
    return {'resolution_token':value.get('resolution_token'),
        'target':{key:value['target'][key] for key in TARGET_GUARDS} if value.get('target') else None,
        'input_observations':value.get('input_observations') or {},'state_sha256':digest(value)}


def _native_part_read(project,query,read_id,**part):
    from laplace.core import grammar
    payload={key:query[key] for key in ('id','proposal_version','edit_id','view')}
    if query.get('hunk_offset'):payload['hunk_offset']=query['hunk_offset']
    payload.update(read_id=read_id,**part)
    return {'native_request':{'verb':'read','concept':'proposal@paragraph','target':project+'::'+query['id'],
        'expected':[],'payload':grammar.to_payload(payload),'by':''}}


def _text_part(text,offset,limit=NATIVE_TEXT_BYTES):
    """Exact UTF-8 coverage: complete is whole text here; at_end ends the stream."""
    budget=min(limit,NATIVE_TEXT_BYTES)
    if type(budget)!=int or budget<1:raise ValueError('Text part limit must be a positive byte budget.')
    raw=text.encode('utf-8');end=min(offset+budget,len(raw))
    if offset>len(raw):raise ValueError('Resolution part offset exceeds the exact text.')
    try:raw[:offset].decode('utf-8')
    except UnicodeDecodeError as error:raise ValueError('Resolution part offset must be an exact UTF-8 boundary.') from error
    while True:
        try:content=raw[offset:end].decode('utf-8')
        except UnicodeDecodeError:end-=1
        else:
            encoded_bytes=len(json.dumps(content,ensure_ascii=False).encode('utf-8'))
            if encoded_bytes<=budget:break
            reduced=offset+max(1,(end-offset)*budget//encoded_bytes)
            if reduced>=end:raise ValueError('The byte budget cannot hold one complete encoded text character.')
            end=reduced
    return {'content':content,'coverage':{'unit':'utf8-bytes','start':offset,'end':end,'total':len(raw),
        'complete':offset==0 and end==len(raw),'at_end':end==len(raw),'has_more':end<len(raw),'sha256':'sha256:'+hashlib.sha256(raw).hexdigest()}},end


def native_resolution(value,query,read_id):
    """Bounded native projection; full human editing uses the same owner via POST.

    Part handles name an exact existing read receipt. No text/choice is copied
    into those handles, and a fresh source check still precedes every part/action.
    """
    project=value['project'];part=query.get('part','metadata');offset=query.get('offset',0)
    read=lambda **fields:_native_part_read(project,query,read_id,**fields)
    head={key:value[key] for key in ('schema_version','project','subject','predecessor','resolution_token','target_required','comparison','changed') if key in value}
    head.update(projection=part,source_currentness='UNRESOLVED' if value.get('target_required') else 'EXACT_GUARDED_CURRENT_SOURCE',
        semantic_currentness='NOT_REASSERTED',read_id=read_id)
    if part in {'original','current','proposed','resolved','hunk'}:
        field=query.get('field','current') if part=='hunk' else 'resolved_after' if part=='resolved' else part
        selected=value
        if part=='hunk':
            selected=next((row for row in value['hunks'] if row['id']==query.get('hunk_id')),None)
            if selected is None:raise ValueError('The exact owner hunk is unavailable in this read.')
        text=selected.get(field)
        if not isinstance(text,str):raise ValueError('This resolution read has no selected text part.')
        chunk,end=_text_part(text,offset);result={**head,**chunk,'field':field}
        if part=='hunk':result['hunk_id']=selected['id']
        result['coverage']['basis']=('RECORDED_PREDECESSOR' if field in {'original','proposed'} else
            'UNAPPLIED_RESOLVED_PREVIEW' if field=='resolved_after' else 'EXACT_GUARDED_CURRENT_SOURCE')
        if end<result['coverage']['total']:
            result['next_read']=read(part=part,offset=end,**({'hunk_id':selected['id'],'field':field} if part=='hunk' else {}))
        return result
    changes=value.get('hunks') or [];summaries=[];hunk_offset=query.get('hunk_offset',0)
    for row in changes[hunk_offset:hunk_offset+NATIVE_HUNKS]:
        summary={key:row[key] for key in ('id','kind','default_choice','comparison_scope','comparison_reason') if key in row}
        summary['text_bytes']={key:len(row[key].encode('utf-8')) for key in ('original','current','proposed')}
        summary['text_inline']=sum(summary['text_bytes'].values())<=256
        if summary['text_inline']:summary.update({key:row[key] for key in ('original','current','proposed')})
        summary['read']=read(part='hunk',hunk_id=row['id'],field='current');summaries.append(summary)
    metadata={**head,'projection':'metadata','target':{key:value['target'][key] for key in TARGET_GUARDS} if value.get('target') else None,
        'hunks':summaries,'pagination':{'offset':hunk_offset,'returned':len(summaries),'total':len(changes)},
        # only parts whose exact text exists: an unresolved target has no current text to read
        'text_reads':{key:read(part=key) for key in ('original','current','proposed') if isinstance(value.get(key),str)},
        'actions':{key:{field:action[field] for field in ('operation','permitted','native_request')}
            for key,action in (value.get('actions') or {}).items()},
        'review_obligation_count':len(value.get('review_obligations') or []),
        'review_obligations':(value.get('review_obligations') or [])[:6]}
    if value.get('target_required'):
        metadata.update(reason=value.get('reason'),target_files=value.get('target_files') or [])
        if isinstance(value.get('resolution_action'),dict):   # the owner's one guarded preparation route, kept
            metadata['resolution_action']={field:value['resolution_action'][field] for field in ('operation','permitted','native_request','http','payload')
                                          if field in value['resolution_action']}
    if 'resolved_after' in value:metadata['text_reads']['resolved']=read(part='resolved')
    if hunk_offset+len(summaries)<len(changes):metadata['next_read']=read(part='metadata',hunk_offset=hunk_offset+len(summaries))
    encoded=json.dumps(metadata,ensure_ascii=False,separators=(',',':'))
    if part=='contract' or len(encoded.encode('utf-8'))>NATIVE_RESPONSE_BYTES:
        chunk,end=_text_part(encoded,offset if part=='contract' else 0)
        result={**head,'projection':'contract-part','format':'json','reason':'Read exact bounded contract parts; no complete action contract is implied by this partial content.',**chunk}
        if end<chunk['coverage']['total']:result['next_read']=read(part='contract',offset=end)
        return result
    return metadata


def native_candidate(value):
    """Mutation acknowledgement with exact retained reads, without prose copies."""
    if not value.get('proposal_version') or not isinstance(value.get('edits'),list):return value
    from laplace.manuscript import manuscript_proposals, proposal_navigation
    result={key:value[key] for key in ('project','id','turn_id','candidate_ref','carrier_ref','proposal_version','author','predecessor','predecessor_read','proposal_state','read_only','reviewable','turn_active','candidate_retained','error','source_effect','apply_action','disposition','metadata_only','coverage','read_scope','identities','remaining') if key in value}
    ref=value.get('candidate_ref') or {'id':value['turn_id'],'version':value['proposal_version']}
    carrier=(value.get('carrier_ref') or {}).get('id')
    scope={'id':ref['id'],'proposal_version':ref['version'],**({'record_id':carrier} if carrier and carrier!=ref['id'] else {})}
    result['read_handle']=proposal_navigation.handle(value['project'],{**scope,'view':'summary'})
    result['edits']=[]
    for edit in value['edits']:
        # An owner projection already carries its semantic identity. Never hash
        # absent before/after fields into a new edit ID on a second projection.
        if 'before' in edit and 'after' in edit:
            summary={key:item for key,item in manuscript_proposals.edit_metadata(edit).items() if key!='source_anchor'}
        else:summary={key:edit[key] for key in ('file','line_start','line_end','before_sha256','after_sha256','after_line_count','declaration_schema','develops','evidence_refs') if key in edit}
        summary.update({key:edit[key] for key in ('edit_id','status','candidate_ref','allowed_actions','basis_currentness','semantic_currentness','basis_reason','application_source_state',
            'read_handle','basis_read','preview_read','resolution_action','successor_ref','successor_read','resolution_application_id','resolution_note','disposition_status','pending_successors') if key in edit})
        summary['text_reads']={part:proposal_navigation.handle(value['project'],{**scope,'view':'edit','edit_id':edit['edit_id'],'part':part})
            for part in ('original','proposed')}
        result['edits'].append(summary)
    application=value.get('application')
    if application:
        result['application']={key:application[key] for key in ('id','complete','status','result_grade','actor','candidate_version','application_tracking','source_applied','source_effect_retained','warning') if key in application}
        result['application']['read']={'operation':'author_history','payload':{'view':'record','id':'activity:journal:'+application['id']}} if application.get('id') else None
    if result.get('apply_action'):
        result['apply_action']={key:result['apply_action'][key] for key in ('operation','permitted','reason','native_request') if key in result['apply_action']}
    # The pending local review an applied effect carries (laplace.core.scoped) reaches the agent on every
    # decision: the owner reply's own list, else the application's (a generated-candidate decision).
    obligations=value.get('review_obligations') or (application or {}).get('review_obligations') or []
    result['review_obligation_count']=len(obligations)
    result['review_obligations']=obligations[:6]
    return result


def apply_candidate(root,project,payload,*,actor=None):
    from laplace.manuscript import source_application
    from laplace.manuscript import source_effects
    from laplace.writing import records as writing_records
    root=Path(root).resolve();record=resolve(root,project,payload)
    if record.get('candidate_kind')!='current-source-resolution':raise ValueError('Apply the exact independently authored current candidate.')
    subject_row=_candidate_subject(root,project,record);ref=subject_row['candidate_ref'];changes=[]
    subject_row['application_actor']=actor or {'kind':'human','basis':'explicit current-source candidate application'}
    with writing_records.proposal_write_lock(root):
        application=source_application._apply_proposal_locked(root,{'project':project,'candidate_id':record['id']},
            proposal_override=record['proposal'],candidate_subject=subject_row,candidate_version=ref['version'],
            allow_multiple=True,human_reviewed=True,application_origin='current-resolution',source_changes=changes)
    if changes:source_effects.finish_source_changes(root,project,application,changes)
    if application.get('complete'):
        result=finish_resolution_record(root,project,{'candidate_ref':ref,
            'resolution_application_id':application['id'],'predecessor':record['predecessor']},actor=actor)
        result.pop('metadata_only',None)
    else:result=read_candidate(root,project,ref)
    return {**result,'application':application,'source_effect':application.get('source_effect')}


def apply_resolution(root,project,payload,*,actor=None):
    from laplace.manuscript import manuscript_proposals
    from laplace.writing import records as writing_records
    root=Path(root).resolve()
    with writing_records.proposal_write_lock(root):
        compared=preview(root,project,payload,actor=actor)
        if not compared['changed']:return {**compared,'changed':False,'application':None}
        predecessor=resolve(root,project,payload)
        old=next(row for row in predecessor['proposal']['edits'] if manuscript_proposals.edit_id(row)==payload['edit_id'])
        target=compared['target'];edit={**{key:old[key] for key in ('develops','evidence_refs') if key in old},
            **{key:target[key] for key in ('file','line_start','line_end','before','source_anchor')},
            'after':compared['resolved_after'],'reason':'Explicit current-source reconciliation.'}
        record={'record':'writing-proposal','id':'PROP-'+uuid.uuid4().hex,'project':project,'candidate_kind':'current-source-resolution',
            'author':actor or {'kind':'human','basis':'explicit current-source reconciliation'},
            'origin_turn_id':predecessor.get('origin_turn_id'),'predecessor':compared['predecessor'],
            'document':__import__('laplace.manuscript.manuscript_source',fromlist=['resolve']).resolve(project,repo_root=root,include_candidates=False),
            'proposal':{'answer':'Resolved current revision','edits':[edit]},
            'proposal_basis':{'schema_version':'laplace.proposal-basis/1','basis_kind':'current-source-resolution',
                'target':target,'input_observations':compared['input_observations']},
            'resolution':{'hunk_choices':[{key:value for key,value in choice.items() if key!='text'} for choice in payload.get('choices') or []],
                'mode':'full-text' if 'resolved_after' in payload else 'hunks'},
            'review_obligations':compared['review_obligations']}
        version=digest({'proposal':record['proposal'],'basis':record['proposal_basis'],'predecessor':record['predecessor']})
        record['proposal_instance_version']=version
        writing_records.bank(root,record)
        ref={'id':record['id'],'version':version}
        try:return apply_candidate(root,project,{'candidate_ref':ref},actor=actor)
        except (ValueError,OSError) as error:
            return {**read_candidate(root,project,ref),'changed':False,'candidate_retained':True,
                'error':str(error),'source_effect':getattr(error,'source_effect',None)}


def decide(root,project,payload,*,actor=None):
    operations={'prepare-resolution':prepare,'preview-resolution':preview,'apply-resolution':apply_resolution,'apply-candidate':apply_candidate,
        'finish-resolution-record':finish_resolution_record}
    if payload.get('decision') not in operations:raise ValueError('Unknown current-resolution decision.')
    if payload.get('decision') in {'apply-resolution','apply-candidate','finish-resolution-record'} and actor and (actor.get('mode')=='review' or actor.get('dispatch_id')):
        raise ValueError('Independent reviewers and dispatched children cannot apply source candidates; the authorised parent applies.')
    result=operations[payload['decision']](root,project,payload,actor=actor)
    if payload['decision']=='preview-resolution' and actor is None:
        from laplace.manuscript import manuscript_source
        source=manuscript_source.resolve(project,repo_root=root,include_candidates=False)
        try:result['after_blocks']=render_blocks(Path(root),project,source,result['target']['file'],result['resolved_after'])
        except (ValueError,OSError) as error:result['preview_render_unavailable']=str(error)
    return result


def decision_contract(*,project_required=True):
    # RD-EDITOR-DECLARATION: `expected` is the ONE canonical owner-token field (identity_doors.EXPECTED_FIELD,
    # shared as every editor door shares it), not an unconstrained array the admission would then refuse.
    from laplace.core.identity_doors import EXPECTED_FIELD
    text={'type':'string'};pin={'type':'string','pattern':'^sha256:[a-f0-9]{64}$'}
    ref={'type':'object','required':['id','version'],'properties':{'id':{'type':'string','pattern':'^PROP-[a-f0-9]{32}$'},'version':pin},'additionalProperties':False}
    target={'type':'object','required':list(TARGET_GUARDS),
        'properties':{'file':text,'line_start':{'type':'integer','minimum':1},'line_end':{'type':'integer','minimum':1},
            'before':text,'expected_source_digest':pin,'expected_selection':pin},'additionalProperties':False}
    properties={key:text for key in ('project','turn_id','proposal_version','edit_id','review_token','merged_after','application_id','resolved_after')}
    properties.update(candidate_ref=ref,resolution_token=pin,target=target,input_observations={'type':'object'},expected=EXPECTED_FIELD,
        resolution_application_id=text,predecessor={'type':'object','required':['edit_id'],'properties':{
            **{key:text for key in ('record_id','turn_id','proposal_version','edit_id')},'candidate_ref':ref},'additionalProperties':False},
        decision={'enum':['accept','reject','keep-current','replace-current','merge','supersede','prepare-resolution','preview-resolution','apply-resolution','apply-candidate','finish-resolution-record']},
        choices={'type':'array','items':{'type':'object','required':['hunk_id','choice'],'properties':{
            'hunk_id':text,'choice':{'enum':['current','proposed','custom']},'text':text},'additionalProperties':False}})
    return {'type':'object','required':(['project'] if project_required else [])+['decision'],'properties':properties,'additionalProperties':False,
        'anyOf':[{'required':['turn_id','edit_id']},{'required':['candidate_ref']}],
        'allOf':[{'if':{'properties':{'decision':{'const':'finish-resolution-record'}}},
            'then':{'required':['candidate_ref','resolution_application_id','predecessor']}}]}
