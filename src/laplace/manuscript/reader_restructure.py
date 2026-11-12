"""Paragraph restructuring delegated by the existing reader-plan owner.

The source owner controls marker changes; reader-plan artifacts, the existing
paragraph-restructure decision ART and reader-publication receipts retain custody.
This module coordinates those owners, rather than providing another file editor
or a second history. A source commit and metadata completion remain separate.
"""
from __future__ import annotations

from laplace.core import scoped as core_scoped
import copy
import hashlib
import json
import re
from pathlib import Path
import uuid

from laplace.projects import artifacts
from laplace.manuscript import reader_plan, source_effects
from laplace.writing import records

SCHEMA='laplace.paragraph-restructure/1'
KINDS=('presentation-split','presentation-join','logical-split','logical-merge')
ACTIONS=('preview-reconciliation','preview-restructure','restructure','recover-restructure','undo-restructure','reconcile-restructure')
GUARDS=('expected_plan_revision','expected_narrative_revision','expected_decision_revision',
        'expected_provenance_revision','expected_attachment_revision','expected_selection','source_guards')


def fingerprint(value):return reader_plan.fingerprint(value)
def revision(value):return reader_plan.raw_revision(value)


def action(project,section_id,name,**payload):
    from laplace.native import verbs as writing_verbs
    inspecting=name in {'preview-restructure','preview-reconciliation'}
    values=dict(payload)
    supplied_guards=values.pop('guards',None)
    bundle=supplied_guards if supplied_guards is not None else {key:values.pop(key) for key in GUARDS if key in values}
    body={'operation':'paragraph_plan','action':name,'section_id':section_id,**values}
    if not inspecting:body['guards']=bundle
    native={'view':'restructure','section_ids':[section_id],**values} if inspecting else dict(body)
    if name=='preview-reconciliation':native['reconcile_current']=True
    if not inspecting and bundle.get('expected_plan_revision') is not None:
        native['expected_plan_revision']=bundle['expected_plan_revision']
    _,request=writing_verbs.from_owner_call('structure' if inspecting else 'structure_change',native,project=project)
    return {'project':project,'operation':'structure_change','permitted':True,
        'http':{'method':'POST','route':'/work/structure/change'},'payload':body,
        'native_request':{'verb':request.verb,'concept':request.concept,'target':request.target,
            'expected':list(request.expected),'payload':request.payload,'by':''}}


def preview_handle(project,section_id,paragraph_ids):
    return action(project,section_id,'preview-restructure',draft={'paragraph_ids':list(paragraph_ids)})


def contracts():
    text={'type':'string'};pin={'type':'string','pattern':'^sha256:[a-f0-9]{64}$'}
    edit={'type':'object','required':['file','line_start','line_end','before','after','expected_source_digest','expected_selection'],'properties':{
        'file':text,'line_start':{'type':'integer','minimum':1},'line_end':{'type':'integer','minimum':1},
        'before':text,'after':text,'expected_source_digest':pin,'expected_selection':pin},'additionalProperties':False}
    draft={'type':'object','properties':{'paragraph_ids':{'type':'array','items':text,'maxItems':80},
        'source_edits':{'type':'array','items':edit,'maxItems':8},'parts':{'type':'array','items':text,'minItems':2}},
        'additionalProperties':False}
    draft['properties'].update(successor_count={'type':'integer','minimum':1},
        successors={'type':'array','items':{'type':'object','required':['paragraph_id','changes'],'properties':{
            'paragraph_id':text,'changes':{'type':'object','properties':{field:text for field in reader_plan.PARAGRAPH_STRINGS},'additionalProperties':False}},'additionalProperties':False}},
        attachment_assignments={'type':'array','items':{'type':'object','required':['attachment_id','disposition','successor_ids'],'properties':{
            'attachment_id':text,'disposition':{'enum':['assign','retain-retired','retain-unresolved']},
            'successor_ids':{'type':'array','items':text,'uniqueItems':True}},'additionalProperties':False}},
        occurrence_assignments={'type':'array','items':{'type':'object','required':['occurrence_id','successor_ids'],'properties':{
            'occurrence_id':text,'successor_ids':{'type':'array','items':text,'uniqueItems':True}},'additionalProperties':False}})
    assignments={'type':'array','items':{'type':'object','required':['expected_occurrence_id','current_occurrence_id'],
        'properties':{'expected_occurrence_id':text,'current_occurrence_id':text},'additionalProperties':False}}
    properties={'operation':{'const':'paragraph_plan'},'section_id':text,'project':text,
        'action':{'enum':list(ACTIONS)},
        'kind':{'enum':list(KINDS)},'draft':draft,'restructure_token':pin,'reconciliation_token':pin,'receipt_id':text,'intent_artifact_id':text,
        'expected_plan_revision':{'type':'string'},'current_occurrence_assignments':assignments,
        'expected_selection':pin,'source_guards':{'type':'object','additionalProperties':pin},
        'guards':{'type':'object','required':list(GUARDS),'properties':{key:({'type':'object','additionalProperties':pin} if key=='source_guards' else {'type':['string','null']}) for key in GUARDS},'additionalProperties':False},
        'expected':{'type':'array','items':{'type':'string'}}}
    properties['guards']['properties'].update(
        expected_reader_basis={'type':'object','additionalProperties':reader_plan.basis_schema()},
        expected_source_set_revision=pin)
    return {'type':'object','required':['operation','action','section_id'],'properties':properties,'additionalProperties':False,
        'allOf':[{'if':{'properties':{'action':{'enum':['preview-restructure','restructure']}}},
                  'then':{'required':['kind','draft']}},
                 {'if':{'properties':{'action':{'const':'restructure'}}},'then':{'required':['restructure_token','guards']}},
                 {'if':{'properties':{'action':{'enum':['recover-restructure','undo-restructure','reconcile-restructure']}}},
                  'then':{'required':['receipt_id','intent_artifact_id','guards']}},
                 {'if':{'properties':{'action':{'const':'reconcile-restructure'}}},'then':{'required':['reconciliation_token']}},
                 {'if':{'properties':{'action':{'const':'preview-reconciliation'}}},'then':{'required':['receipt_id','intent_artifact_id']}}]}


def read_contract():
    properties={key:value for key,value in contracts()['properties'].items() if key in {'kind','draft','restructure_token','reconciliation_token','current_occurrence_assignments','receipt_id','intent_artifact_id'}}
    return {'type':'object','required':['view','section_ids'],'properties':{
        'view':{'const':'restructure'},'section_ids':{'type':'array','minItems':1,'maxItems':1,'items':{'type':'string'}},
        'read_id':{'type':'string'},'part':{'enum':['metadata','before','after','mapping','logical'],'description':'Exact UTF-8 parts: coverage.complete means the whole body is present in this response; at_end/has_more determine continuation.'},
        'reconcile_current':{'type':'boolean'},'change_index':{'type':'integer','minimum':0,'maximum':7},'offset':{'type':'integer','minimum':0},**properties},
        'additionalProperties':False,'allOf':[{'if':{'required':['read_id']},
            'then':{'anyOf':[{'required':['restructure_token']},{'required':['reconciliation_token']}]},'else':{'anyOf':[{'required':['kind','draft']},{'required':['receipt_id','intent_artifact_id']}]}}]}


def _snapshot(project,section_id,root):
    from laplace.pipeline import registry,pathsafe
    from laplace.manuscript import bindings
    record=registry.resolve(project,repo_root=root)
    if record is None:raise ValueError('Choose a registered reader-plan project.')
    state=bindings.reader_snapshot(project,root)
    section=next((row for row in state['sections'] if row['id']==section_id),None)
    if section is None:raise ValueError('The exact declared reader section is unavailable.')
    cp,np=reader_plan._paths(project,root,section_id)
    suffix=pathsafe.encode_sid_for_path(section_id)+'.json'
    dp=record.stage_path('decisions',root)/suffix;pp=record.stage_path('provenance',root)/suffix
    documents={};raw={}
    for name,path in {'narrative':np,'decisions':dp,'provenance':pp}.items():
        documents[name],raw[name]=reader_plan._json(path)
    rows=reader_plan._paragraphs(documents['narrative'],section_id)
    return {'record':record,'section':section,'state':state,'paths':{'narrative':np,'decisions':dp,'provenance':pp},
        'documents':documents,'raw':raw,'rows':rows}


def _source_change(project,section_id,draft,snapshot,root):
    from laplace.manuscript import blocks as manuscript_blocks, projection_viewer, manuscript_source
    supplied=draft.get('source_edits') or []
    if not supplied:return None,[],[]
    blocks=[]
    for edit in supplied:
        source,md,path=manuscript_blocks._path(root,project,edit.get('file',''))
        if edit.get('expected_source_digest')!=revision(path.read_bytes()):
            raise ValueError('CHANGED_INPUT: source file changed since the body was inspected.')
        manuscript_source.source_access(project,path,root,writable=True,expected_selection=edit.get('expected_selection'))
        if not edit.get('expected_selection'):raise ValueError('The inspected source selection guard is required.')
        # The current typed-block owner uses normalized text for its digest.
        # Adapt only AFTER proving the caller's physical bytes/selection pin.
        checked={**edit,'expected_source_digest':revision(path.read_text().encode())}
        source,md,path,raw,block=manuscript_blocks._block(root,project,checked,allowed=frozenset({'para'}))
        spans=projection_viewer.parse_paragraphs(raw)
        matches=[span for span in spans if span['start_line']<=edit['line_start']<=span['end_line']]
        if len(matches)>1:raise ValueError('The body marker occurrence is ambiguous.')
        span=copy.deepcopy(matches[0]) if matches else {'start_line':edit['line_start'],'end_line':edit['line_end'],'spec_ids':[],'section':''}
        # A distant marker must not silently adopt intervening unmarked prose.
        prefix=raw.split('\n')[span['start_line']-1:edit['line_start']-1]
        if any(line.strip() and not line.lstrip().startswith('%') for line in prefix):
            span={'start_line':edit['line_start'],'end_line':edit['line_end'],'spec_ids':[],'section':''}
        else:
            following=raw.split('\n')[edit['line_end']:span['end_line']]
            for offset,line in enumerate(following):
                if line.strip():span['end_line']=edit['line_end']+offset;break
        if any(ident not in {row.get('paragraph_id') for row in snapshot['rows']} for ident in span['spec_ids']):
            raise ValueError('Presentation restructuring requires one declared section owning the complete current logical ID set.')
        blocks.append((edit,source,md,path,raw,span))
    if not any(item[5]['spec_ids'] for item in blocks):raise ValueError('Use the ordinary source editor for untagged prose.')
    if len({str(item[3]) for item in blocks})!=1:raise ValueError('A presentation operation requires one exact source file.')
    return blocks,source,md


def _stage_presentation(kind,blocks,draft,root):
    from laplace.manuscript import projection_viewer, proposal_preflight
    first,source,md,path,raw,span=blocks[0];lines=raw.split('\n')
    ids=list(dict.fromkeys(ident for item in blocks for ident in item[5]['spec_ids']))
    if set(draft.get('paragraph_ids') or [])!=set(ids):
        raise ValueError('Copy the complete owner paragraph ID set; presentation does not drop logical IDs.')
    for edit,*_ in blocks:
        if any(projection_viewer._PARA_RE.match(line) for line in edit['after'].splitlines()):
            raise ValueError('Paragraph markers are supplied by this owner, never authored inside body text.')
    marker='\n'.join('% '+ident for ident in ids)
    lo=span['start_line'];hi=first['line_end']
    if kind=='presentation-split':
        parts=draft.get('parts')
        if len(blocks)!=1 or not isinstance(parts,list) or len(parts)<2 or first['after']!='\n\n'.join(parts):
            raise ValueError('Presentation split requires all exact authored paragraph parts matching the body postimage.')
        if any(not part.strip() or re.search(r'\n[ \t]*\n',part.replace('\r\n','\n')) for part in parts):
            raise ValueError('Retain the draft: type into each empty paragraph or remove its break, and supply every nonempty physical paragraph part.')
        prefix='\n'.join(lines[lo-1:first['line_start']-1])
        after=prefix+'\n'+parts[0]+''.join('\n\n'+marker+'\n'+part for part in parts[1:])
    else:
        if len(blocks)!=2 or blocks[1][0]['after']!='':raise ValueError('Presentation join requires the two exact body spans and one joined postimage.')
        second=blocks[1][0]
        if second['line_start']<=first['line_end'] or any(line.strip() and not projection_viewer._PARA_RE.match(line)
            for line in lines[first['line_end']:second['line_start']-1]):
            raise ValueError('Only adjacent paragraph occurrences with no intervening substance can join.')
        if not first['after'].strip() or '\n\n' in first['after'].replace('\r\n','\n'):
            raise ValueError('Retain the draft: a joined body must be one physical paragraph.')
        hi=second['line_end'];after=marker+'\n'+first['after']
    before='\n'.join(lines[lo-1:hi]);after_text='\n'.join(lines[:lo-1]+after.split('\n')+lines[hi:])
    # Generic source editing still rejects marker changes. This semantic owner
    # permits only the marker mapping it just constructed, preserving all others.
    strip=lambda text:'\n'.join(line for line in text.split('\n') if not projection_viewer._PARA_RE.match(line))
    errors=proposal_preflight.staged_integrity_errors(strip(raw),strip(after_text),is_root=path==root/source['root'])
    if errors:raise ValueError('; '.join(errors))
    physical=path.read_bytes();newline='\r\n' if b'\r\n' in physical else '\n'
    physical_lines=physical.decode('utf-8').splitlines(keepends=True)
    old=''.join(physical_lines[lo-1:hi]);ending=newline if old.endswith(('\n','\r')) else ''
    new=after.replace('\n',newline)+ending
    observed=''.join(physical_lines[:lo-1])+new+''.join(physical_lines[hi:])
    change={'file':path.relative_to(root).as_posix(),'line_start':lo,'line_end':hi,'before':old,'after':new,
        'before_sha256':'sha256:'+hashlib.sha256(physical).hexdigest(),
        'after_sha256':'sha256:'+hashlib.sha256(observed.encode()).hexdigest(),
        'after_line_end':lo+len(new.splitlines())-1}
    old_spans=[{key:item[5][key] for key in ('start_line','end_line','spec_ids','section')} for item in blocks]
    new_spans=[span for span in projection_viewer.parse_paragraphs(observed) if span['start_line']>=lo and span['start_line']<=change['after_line_end']]
    return change,old_spans,new_spans


def preview(project,section_id,kind,draft,root):
    from laplace.manuscript import manuscript_source
    root=Path(root).resolve()
    if kind not in KINDS:raise ValueError('Choose an explicit supported paragraph restructuring kind.')
    if kind.startswith('logical-'):
        from laplace.manuscript.reader_logical_publication import preview as logical_preview
        return logical_preview(project,section_id,kind,draft,root)
    snapshot=_snapshot(project,section_id,root);draft=copy.deepcopy(draft)
    ids=draft.get('paragraph_ids') or []
    if len(ids)!=len(set(ids)) or any(ident not in {row.get('paragraph_id') for row in snapshot['rows']} for ident in ids):
        raise ValueError('Choose exact current planned paragraph identities.')
    blocks,source,md=_source_change(project,section_id,draft,snapshot,root)
    changes=[];mapping={'before':[],'after':[]}
    if blocks:
        if kind=='presentation-split' and not blocks[0][5]['spec_ids']:raise ValueError('An untagged split has no reader-plan identities; use ordinary source editing.')
        change,mapping['before'],mapping['after']=_stage_presentation(kind,blocks,draft,root);changes=[change]
    guards={'expected_plan_revision':snapshot['state']['authority']['plan_revision'],
        'expected_narrative_revision':revision(snapshot['raw']['narrative']),
        'expected_decision_revision':revision(snapshot['raw']['decisions']),
        'expected_provenance_revision':revision(snapshot['raw']['provenance']),
        'expected_attachment_revision':fingerprint([row for row in snapshot['rows'] if row.get('paragraph_id') in ids]),
        'expected_selection':manuscript_source.selection_identity(source,project) if blocks else None,
        'source_guards':{change['file']:change['before_sha256'] for change in changes}}
    token=fingerprint({'project':project,'section_id':section_id,'kind':kind,'guards':guards,'draft':draft})
    return {'schema_version':SCHEMA,'project':project,'section_id':section_id,'kind':kind,'draft':draft,'guards':guards,
        'restructure_token':token,'source_changes':changes,'occurrence_mapping':mapping,'complete':False,
        'review_obligations':([core_scoped.obligation('UNATTRIBUTED_SOURCE_JOINED','Unmarked content remains scientifically unreviewed; marker union does not certify its claims.',subject=section_id)] if blocks and any(not row['spec_ids'] for row in mapping['before']) else []),
        'preview_only':True,'apply_action':action(project,section_id,'restructure',kind=kind,restructure_token=token,**guards) if changes else None,
        'preview_action':preview_handle(project,section_id,ids)}


def annotate_walk(project,root,sections,source,tree):
    """Bind canvas gestures to declared logical owners, not parser PLAN names."""
    from laplace.pipeline import registry,schema
    from laplace.manuscript import manuscript_source
    record=registry.resolve(project,repo_root=root)
    if record is None:return []
    owners={};pending_rows=[]
    for section in schema.plan_sections(record.read_plan(root) or {}):
        sid=section['id']
        try:
            _,path=reader_plan._paths(project,root,sid)
            document,_=reader_plan._json(path)
        except ValueError:continue
        for row in reader_plan._paragraphs(document,sid):owners.setdefault(row.get('paragraph_id'),set()).add(sid)
        pending_rows.extend(pending(project,sid,root))
    selection=manuscript_source.selection_identity(source,project)
    pins={row['file']:row.get('raw_file_sha256') or revision((root/row['file']).read_bytes()) for row in tree.get('sources',[])}
    for section in sections:
        for block in section.get('blocks',[]):
            ids=block.get('spec_ids') or [];src=block.get('src') or {}
            possible=set.intersection(*(owners.get(ident,set()) for ident in ids)) if ids else set()
            if block.get('kind')!='para' or len(possible)!=1 or src.get('repo_file') not in pins:continue
            handle=preview_handle(project,next(iter(possible)),ids)
            handle['payload'].update(expected_selection=selection,source_guards={src['repo_file']:pins[src['repo_file']]})
            block['restructure_preview']=handle
    return pending_rows


def read(project,payload,root):
    if payload.get('receipt_id'):
        if any(key in payload for key in ('draft','kind','read_id')) or payload.get('part') not in (None,'metadata','mapping','logical'):raise ValueError('Receipt inspection cannot rebind a structural draft.')
        value=copy.deepcopy(_receipt(project,root,payload['receipt_id'],payload['intent_artifact_id']))
        intent=_intent(project,root,payload['intent_artifact_id'])
        if value['section_id']!=payload['section_ids'][0]:raise ValueError('Structural receipt belongs to another declared section.')
        if payload.get('part')=='logical' and not payload.get('reconcile_current'):
            # Historical detail is an immutable RPUB/ART projection. Live inverse
            # currentness is deliberately observed only by the metadata read.
            if not records.index(root).by_id.get(payload['receipt_id']):
                value={'schema_version':SCHEMA,'project':project,'section_id':intent['section_id'],
                    'kind':intent['kind'],'receipt':{'id':payload['receipt_id'],'intent_artifact_id':payload['intent_artifact_id']},
                    'source_disposition':'UNKNOWN_NO_RECORDED_RPUB'}
            value.pop('inverse_currentness',None)
            value['inverse_direction']='REDO' if (_provenance_inverse(intent) if not intent['kind'].startswith('logical-') else intent.get('inverse',False)) else 'UNDO'
            value['retained_operation']=intent
            if records.index(root).by_id.get(payload['receipt_id']):value=_actions(project,value['section_id'],value)
            value['action_currentness']='AS_RECORDED_ONLY; inspect live metadata currentness before executing any historical action.'
            return value
        if intent['kind'].startswith('logical-'):
            from laplace.manuscript.reader_logical_publication import disposition_summary
            value['disposition_summary']=disposition_summary(intent,value)
        value['inverse_direction']='REDO' if (_provenance_inverse(intent) if not intent['kind'].startswith('logical-') else intent.get('inverse',False)) else 'UNDO'
        value['inverse_currentness']=inverse_currentness(project,root,intent,value)
        if value['section_id']!=payload['section_ids'][0]:raise ValueError('Structural receipt belongs to another declared section.')
        if payload.get('reconcile_current'):
            from laplace.manuscript.reader_restructure_reconciliation import inspect
            value=copy.deepcopy(value);value['metadata_reconciliation']=inspect(project,root,_intent(project,root,payload['intent_artifact_id']),value,payload.get('current_occurrence_assignments'))
            if payload.get('reconciliation_token') and payload['reconciliation_token']!=value['metadata_reconciliation']['reconciliation_token']:
                raise ValueError('CHANGED_INPUT: current-source reconciliation basis changed between exact reads.')
        if payload.get('part')=='logical' and value['kind'].startswith('logical-'):
            value=copy.deepcopy(value);value['retained_operation']=_intent(project,root,payload['intent_artifact_id'])
        if payload.get('part')=='mapping':
            value=copy.deepcopy(value);value['occurrence_mapping']=_intent(project,root,payload['intent_artifact_id'])['occurrence_mapping']
        return _actions(project,value['section_id'],value)
    if payload.get('read_id'):
        row=records.selected_journal_fields(project,payload['read_id'],root,fields=['record','operation','payload'])
        original=row.get('payload') or {}
        if row.get('record')!='writing-tool-read' or row.get('operation')!='structure' or original.get('view')!='restructure':
            raise ValueError("Use this project's exact structural preview read receipt.")
        if any(key in payload for key in ('draft','kind','current_occurrence_assignments')) or original.get('section_ids')!=payload['section_ids']:
            raise ValueError('Structural part reads cannot rebind the admitted draft or section.')
        if original.get('receipt_id'):
            if not original.get('reconcile_current'):raise ValueError('This exact read does not carry a current-source reconciliation preview.')
            return read(project,{**original,**{key:payload[key] for key in ('part','offset','reconciliation_token') if key in payload}},root)
        value=preview(project,original['section_ids'][0],original['kind'],original['draft'],root)
        if value['restructure_token']!=payload['restructure_token']:
            raise ValueError('CHANGED_INPUT: the retained structural preview is no longer current; inspect again without discarding the draft.')
        return value
    return preview(project,payload['section_ids'][0],payload['kind'],payload['draft'],root)


def native_projection(value,payload,read_id=None):
    """Same owner identities/actions, exact prose through existing read receipts."""
    if value.get('schema_version')!=SCHEMA or value.get('projection') in {'metadata','source-part','mapping-part'}:return value
    if value.get('kind','').startswith('logical-') or value.get('metadata_reconciliation') or payload.get('part')=='logical':
        from laplace.manuscript.reader_logical_publication import native_projection as logical_projection
        return logical_projection(value,payload,read_id)
    result={key:copy.deepcopy(item) for key,item in value.items() if key not in {'draft','source_changes','read_receipt','action_receipt','occurrence_mapping','remapped_occurrences'}}
    for key in ('read_receipt','action_receipt'):
        if key in value:result[key]={name:copy.deepcopy(item) for name,item in value[key].items() if name not in {'payload','source_effect','plan_publication'}}
    for key in ('apply_action','preview_action','recovery_action','undo_action'):
        if isinstance(result.get(key),dict):result[key]={name:result[key][name] for name in ('operation','permitted','native_request','title') if name in result[key]}
    changes=value.get('source_changes') or []
    def handle(index,part,offset=0):
        from laplace.core import grammar
        fields={'view':'restructure','section_ids':[value['section_id']],'part':part,'offset':offset}
        if value.get('receipt'):
            fields.update(receipt_id=value['receipt']['id'],intent_artifact_id=value['receipt']['intent_artifact_id'])
        else:fields.update(read_id=read_id,restructure_token=value['restructure_token'],change_index=index)
        return {'native_request':{'verb':'read','concept':'plan@plan','target':value['project'],
            'expected':[],'payload':grammar.to_payload(fields),'by':''}}
    mapping=value.get('occurrence_mapping')
    if payload.get('part')=='mapping':
        if mapping is None:raise ValueError('Read the exact retained structural mapping through its issued receipt handle.')
        from laplace.manuscript.reconciliation import _text_part
        text=json.dumps(mapping,ensure_ascii=False,separators=(',',':'))
        chunk,end=_text_part(text,payload.get('offset',0))
        head={key:copy.deepcopy(value[key]) for key in ('schema_version','project','section_id','kind','receipt','restructure_token') if key in value}
        head.update(projection='mapping-part',format='json',source_currentness='HISTORICAL_MAPPING_ONLY' if value.get('receipt') else 'EXACT_GUARDED_CURRENT_SOURCE',**chunk)
        if end<chunk['coverage']['total']:head['next_read']=handle(0,'mapping',end)
        return head
    counts={key:len(rows) for key,rows in mapping.items()} if mapping else value.get('occurrence_counts') or {'after':len(value.get('remapped_occurrences') or [])}
    result['occurrence_mapping']={'counts':counts,'inline':False}
    if read_id or value.get('receipt'):result['occurrence_mapping']['read']=handle(0,'mapping')
    if read_id and payload.get('part') in {'before','after'}:
        index=payload.get('change_index',0)
        if index>=len(changes):raise ValueError('The exact structural source change is unavailable.')
        from laplace.manuscript.reconciliation import _text_part
        chunk,end=_text_part(changes[index][payload['part']],payload.get('offset',0))
        result={key:result[key] for key in ('schema_version','project','section_id','kind','restructure_token')}
        result.update(projection='source-part',field=payload['part'],change_index=index,source_currentness='EXACT_GUARDED_CURRENT_SOURCE',**chunk)
        if end<chunk['coverage']['total']:result['next_read']=handle(index,payload['part'],end)
        return result
    result['projection']='metadata'
    result['source_changes']=[{**{key:item for key,item in change.items() if key not in {'before','after'}},
        'text_bytes':{key:len(change[key].encode('utf-8')) for key in ('before','after')},
        **({'text_reads':{key:handle(index,key) for key in ('before','after')}} if read_id else {})}
        for index,change in enumerate(changes)]
    if value.get('draft'):result['draft_retained_in']='Exact initial structure read receipt; reuse the originally authored draft when applying.'
    return result


def _store(project,root,path,document,before,*,metadata=None):
    base=artifacts.project_root(root,project)
    value=json.dumps(document,ensure_ascii=False,indent=2)+'\n'
    return artifacts.store(root,project,{'scope':'project','path':path.relative_to(base).as_posix(),
        'content':value,'reason':'Explicit paragraph restructuring',
        **({'before':None} if before is None else {'expected_revision':revision(before).removeprefix('sha256:')})},
        owner_metadata=metadata or {'path':path.relative_to(root).as_posix(),'subjects':{},'reserved_ids':[]})


def _record_receipt(project,root,value):
    from laplace.writing import records as writing_records
    ident=value['receipt'].get('id') or 'RPUB-'+uuid.uuid4().hex
    value={**value,'receipt_recorded':True,'receipt':{**value['receipt'],'id':ident}}
    if 'remapped_occurrences' in value:value['occurrence_counts']={'after':len(value['remapped_occurrences'])}
    writing_records.bank(root,{'record':'writing-reader-publication','id':ident,'project':project,
        'artifact_id':value['receipt']['intent_artifact_id'],
        'reader_metadata':{'path':value['metadata_path'],'subjects':{},'reserved_ids':[],
            'restructure':{key:copy.deepcopy(item) for key,item in value.items() if key not in {'source_changes','draft','remapped_occurrences','occurrence_mapping'}}}})
    return value


def _intent(project,root,artifact_id):
    row=records.selected_journal_fields(project,artifact_id,root,fields=['record','after','path'])
    if row.get('record')!='writing-artifact':raise ValueError('The exact restructuring intent ART is unavailable.')
    value=json.loads(row['after'])
    if value.get('schema_version')!=SCHEMA or value.get('project')!=project:
        raise ValueError('The selected ART is not this project\'s exact single-operation restructuring intent.')
    return value


def _phase(project,root,intent,artifact_id,*,recorded=False):
    if intent['kind'].startswith('logical-'):
        from laplace.manuscript.reader_logical_publication import phase
        return phase(project,root,intent,artifact_id)
    from laplace.manuscript import storyboard
    files=[]
    for row in intent['source_changes']:
        path=root/row['file']
        file={'scope':'repository','path':row['file'],'before_sha256':row['before_sha256'],'after_sha256':row['after_sha256']}
        try:file['observed_after_sha256']=revision(path.read_bytes()) if path.is_file() else None
        except OSError as exc:file.update(observed_after_sha256=None,observation_error=str(exc))
        files.append(file)
    effect=source_effects.receipt(project,intent['guards']['expected_selection'],files,complete=False,
        required=[{'owner':'paragraph-metadata','status':'UNPROVED'}])
    decision_path=root/intent['decision_path']
    try:decision_revision=revision(decision_path.read_bytes()) if decision_path.is_file() else None
    except OSError:decision_revision=None
    remaining=['source-history','author-protection','provenance-publication','receipt-publication']
    return {'schema_version':SCHEMA,'project':project,'section_id':intent['section_id'],'kind':intent['kind'],
        'inverse_direction':'REDO' if _provenance_inverse(intent) else 'UNDO',
        'complete':False,'source_committed':effect['state'] in {'COMMITTED','UNCHANGED'},'source_effect':effect,
        'source_observation':'EXACT_CURRENT_BYTES_AGAINST_RETAINED_ADMISSION','receipt_recorded':recorded,
        'source_scope':{key:intent['source_changes'][0][key] for key in ('file','line_start','line_end','after_line_end')},
        'review_obligations':copy.deepcopy(intent.get('review_obligations') or []),
        'metadata_path':intent['metadata_path'],'remaining_steps':remaining,
        'guards':{**intent['guards'],'expected_decision_revision':decision_revision,
            'source_guards':{row['file']:row['after_sha256'] for row in intent['source_changes']}},
        'receipt':{'id':intent['source_receipt_id'],'intent_artifact_id':artifact_id,'kind':intent['kind'],'remaining_steps':remaining},
        'source_changes':intent['source_changes'],'remapped_occurrences':intent['occurrence_mapping']['after'],
        'plan_publication':storyboard.reader_publication('paragraph-restructure','PARTIAL',False,0)}


def _receipt(project,root,ident,artifact_id):
    idx=records.index(root)
    if not idx.by_id.get(ident):
        intent=_intent(project,root,artifact_id)
        if intent.get('source_receipt_id')!=ident:raise ValueError('The exact structural receipt is unavailable.')
        return _phase(project,root,intent,artifact_id)
    row=records.selected_journal_fields(project,ident,root,fields=['record','reader_metadata'])
    value=(row.get('reader_metadata') or {}).get('restructure')
    if (row.get('record')!='writing-reader-publication' or not isinstance(value,dict)
            or value.get('receipt',{}).get('id')!=ident or value['receipt'].get('intent_artifact_id')!=artifact_id):
        raise ValueError('Copy the exact project-scoped structural receipt and intent ART.')
    return value


def pending(project,section_id,root):
    """One current intent pointer and its latest indexed receipt, never a fold."""
    idx=records.index(root);meta=idx.reader_restructure_intents.get((project,section_id))
    if not meta:return []
    latest=idx.reader_restructure_receipts.get((project,meta['id']))
    if latest:
        value=copy.deepcopy(latest['reader_metadata']['restructure'])
        if value.get('complete') or value.get('publication_not_attempted') or value.get('source_effect',{}).get('state')=='ROLLED_BACK':return []
    else:
        intent=_intent(project,root,meta['id'])
        value=_phase(project,root,intent,meta['id'])
        if value['source_effect']['state']=='ROLLED_BACK':return []
    return [_actions(project,section_id,value)]


def _actions(project,section_id,value):
    from urllib.parse import urlencode
    for key in ('recovery_action','undo_action','reconciliation_read'):value.pop(key,None)
    receipt=value['receipt'];guards=value['guards']
    fields={'view':'restructure','section_ids':[section_id],'receipt_id':receipt['id'],'intent_artifact_id':receipt['intent_artifact_id']}
    value['read_handle']={'operation':'structure','payload':fields,
        'http':{'method':'GET','route':'/work/structure','query':{'project':project,**fields},
            'url':'/work/structure?'+urlencode({'project':project,**{key:json.dumps(item) if isinstance(item,list) else item for key,item in fields.items()}})}}
    base={'receipt_id':receipt['id'],'intent_artifact_id':receipt['intent_artifact_id'],'guards':guards}
    if value['remaining_steps']:
        from laplace.manuscript.reader_restructure_reconciliation import read_handle as reconciliation_read
        value['reconciliation_read']=reconciliation_read(project,section_id,receipt)
        value['recovery_action']=action(project,section_id,'recover-restructure',**base)
    elif value.get('source_effect',{}).get('state') in {'COMMITTED','UNCHANGED'} or value.get('source_unchanged'):
        if value.get('inverse_currentness',{}).get('status','CURRENT')=='CURRENT':
            value['undo_action']=action(project,section_id,'undo-restructure',**base)
            value['undo_action']['title']='Redo this structural operation' if value.get('inverse_direction')=='REDO' else 'Undo this structural operation'
        else:value['undo_unavailable']=value['inverse_currentness'].get('reason','The exact inverse is unavailable on the current basis.')
    if value.get('metadata_only'):
        value.pop('undo_action',None)
        value['undo_unavailable']=('Current reader inputs were separately adopted; use a new inspected structural change.' if value.get('source_required') is False else 'Current source was separately edited; use a new inspected structural action instead of replaying a historical inverse.')
    return value


def _source_file_keys(value,root,manuscript_dir):
    if not isinstance(value,str):return set()
    return {(root/value).resolve(),(root/manuscript_dir/value).resolve()}


def _same_source_file(value,source_file,root,manuscript_dir):
    return (root/source_file).resolve() in _source_file_keys(value,root,manuscript_dir)


def _provenance_after(snapshot,preview_value,root):
    """Transform only witnessed physical occurrences; IDs alone are not location."""
    document=copy.deepcopy(snapshot['documents']['provenance'] or {'section_id':preview_value['section_id'],'paragraphs':[]})
    rows=document.setdefault('paragraphs',[]);change=preview_value['source_changes'][0]
    old_spans=preview_value['occurrence_mapping']['before'];new_spans=preview_value['occurrence_mapping']['after']
    source_file=change['file'];selected=[];retained=[]
    delta=change['after_line_end']-change['line_end']
    from laplace.manuscript import manuscript_source
    md=manuscript_source.resolve(snapshot['record'].name,repo_root=root)['manuscript_dir']
    same_file=lambda value:_same_source_file(value,source_file,root,md)
    for index,row in enumerate(rows):
        loc=row.get('source') if isinstance(row.get('source'),dict) else {}
        lo,hi=loc.get('line_start'),loc.get('line_end')
        ids=list(row.get('spec_ids') or [row.get('spec_id')])
        matching=[span for span in old_spans if type(lo)==int and type(hi)==int
            and span['start_line']<=lo<=hi<=span['end_line'] and set(ids)==set(span['spec_ids'])]
        if same_file(loc.get('file')) and len(matching)==1:
            selected.append((index,row));continue
        kept=copy.deepcopy(row)
        if same_file(loc.get('file')) and type(lo)==int and lo>change['line_end']:
            kept['source']={**loc,'line_start':lo+delta,'line_end':hi+delta if type(hi)==int else hi}
        retained.append(kept)
    for span in new_spans:
        inherited=copy.deepcopy(selected[0][1]) if len(selected)==1 else {}
        if len(selected)>1:
            keys=set.intersection(*(set(row) for _,row in selected))
            inherited={key:copy.deepcopy(selected[0][1][key]) for key in keys
                if all(row[key]==selected[0][1][key] for _,row in selected)}
            inherited['retained_provenance_indices']=[index for index,_ in selected]
            inherited['attachment_reconciliation']='CONFLICTING_FIELDS_REMAIN_IN_RETAINED_INTENT'
        inherited.update(spec_id=span['spec_ids'][0],spec_ids=span['spec_ids'],source_section=span['section'],
            source={'file':source_file,'line_start':span['start_line'],'line_end':span['end_line']},
            origin='explicit-presentation-restructure',scientific_acceptance='NOT_ASSERTED',
            retained_provenance_indices=[index for index,_ in selected])
        retained.append(inherited)
    inserted=retained[len(rows)-len(selected):]
    existing=retained[:len(rows)-len(selected)]
    position=min((index for index,_ in selected),default=len(existing))
    document['paragraphs']=existing[:position]+inserted+existing[position:]
    patch={'removed':[{'index':index,'row':row} for index,row in selected],'inserted':inserted,'insert_at':position,
        'source_file':source_file,'line_end':change['line_end'],'after_line_end':change['after_line_end'],'delta':delta,
        'before_absent':snapshot['documents']['provenance'] is None,
        'manuscript_dir':md}
    return document,patch


def _provenance_inverse(intent):
    direction=intent.get('provenance_direction')
    if direction is None:return bool(intent.get('inverse_of'))  # Existing B1 ARTs.
    if direction not in {'forward','inverse'}:raise ValueError('Retained provenance direction is unsupported.')
    return direction=='inverse'


def _apply_provenance_patch(document,patch,*,inverse=False,section_id,root):
    if inverse and patch['before_absent']:return None
    result=copy.deepcopy(document or {'section_id':section_id,'paragraphs':[]});rows=result.setdefault('paragraphs',[])
    if inverse:
        at=patch['insert_at'];inserted=patch['inserted']
        if rows[at:at+len(inserted)]!=inserted:
            raise ValueError('Exact structural inverse provenance rows are unavailable.')
        left=rows[:at]+rows[at+len(inserted):]
        for row in left:
            loc=row.get('source') or {}
            if _same_source_file(loc.get('file'),patch['source_file'],root,patch['manuscript_dir']) and type(loc.get('line_start'))==int and loc['line_start']>patch['after_line_end']:
                loc['line_start']-=patch['delta']
                if type(loc.get('line_end'))==int:loc['line_end']-=patch['delta']
        removed=patch['removed'];restored=[];old_index=left_index=0
        previous=-1;total=len(left)+len(removed)
        for old in removed:
            if type(old['index'])!=int or not previous<old['index']<total:
                raise ValueError('The scoped inverse provenance order is unavailable.')
            previous=old['index']
        for position in range(total):
            if old_index<len(removed) and removed[old_index]['index']==position:
                restored.append(copy.deepcopy(removed[old_index]['row']));old_index+=1
            else:
                restored.append(left[left_index]);left_index+=1
        result['paragraphs']=restored
    else:
        removed={row['index']:row['row'] for row in patch['removed']};left=[]
        for index,row in enumerate(rows):
            if index in removed:
                if row!=removed[index]:raise ValueError('The scoped provenance preimage changed.')
                continue
            loc=row.get('source') or {}
            if _same_source_file(loc.get('file'),patch['source_file'],root,patch['manuscript_dir']) and type(loc.get('line_start'))==int and loc['line_start']>patch['line_end']:
                loc['line_start']+=patch['delta']
                if type(loc.get('line_end'))==int:loc['line_end']+=patch['delta']
            left.append(row)
        at=patch['insert_at'];result['paragraphs']=left[:at]+copy.deepcopy(patch['inserted'])+left[at:]
    return result


def _protection_index(root,feedback):
    # Feedback has legacy note/decision rows without a writing-journal `record`.
    # Reuse its existing owner projection and cache path, not the talk extractor.
    from laplace.work.author_history_metrics import _feedback_metadata
    return records.index(root,path=feedback,extractor=_feedback_metadata)


def _complete_metadata(project,root,intent,source_value):
    """Only metadata follows a proved physical source receipt; never source replay."""
    from laplace.manuscript import storyboard, manuscript_source, projection_viewer
    from laplace.core.records import journal
    from laplace.pipeline import edits
    snapshot=_snapshot(project,intent['section_id'],root)
    original=intent['guards'];source=manuscript_source.resolve(project,repo_root=root)
    reconciled=source_value.get('metadata_reconciliation')
    if reconciled:
        from laplace.manuscript.reader_restructure_reconciliation import verify_adopted
        verify_adopted(project,root,intent,source_value)
    if source_value.get('source_effect',{}).get('state') not in {'COMMITTED','UNCHANGED'}:
        raise ValueError('The retained source effect is not a proved commit; inspect it before metadata recovery.')
    if manuscript_source.selection_identity(source,project)!=original['expected_selection']:
        raise ValueError('CHANGED_INPUT: structural source selection changed; no metadata publication was attempted.')
    for change in intent['source_changes']:
        if revision((root/change['file']).read_bytes())!=(reconciled['current_observation']['guards']['source_guards'][change['file']] if reconciled else change['after_sha256']):
            raise ValueError('CHANGED_INPUT: committed structural source changed; do not replay it.')
    if (snapshot['state']['authority']['plan_revision']!=original['expected_plan_revision']
        or revision(snapshot['raw']['narrative'])!=original['expected_narrative_revision']):
        raise ValueError('CHANGED_INPUT: reader plan changed after source commit; inspect the retained structural receipt.')
    if revision(snapshot['raw']['decisions'])!=source_value['guards']['expected_decision_revision']:
        raise ValueError('CHANGED_INPUT: exact restructuring decision artifact changed after admission.')
    decision_rows=(snapshot['documents']['decisions'] or {}).get('decisions',[])
    if fingerprint([row for row in decision_rows if row.get('owner')!='reader-restructure'])!=intent['decision_other_revision']:
        raise ValueError('CHANGED_INPUT: unrelated retained reader decisions changed after admission.')
    refs=[row for row in decision_rows if row.get('owner')=='reader-restructure']
    if len(refs)!=1 or refs[0].get('intent_artifact_id')!=source_value['receipt']['intent_artifact_id'] or refs[0].get('restructure_token')!=intent['restructure_token']:
        raise ValueError('CHANGED_INPUT: structural intent pointer no longer matches its exact ART.')
    target=snapshot['paths']['provenance']
    observed=snapshot['raw']['provenance'];complete=False;error=None
    if reconciled:
        from laplace.manuscript.reader_restructure_reconciliation import provenance_document
        document=provenance_document(project,root,intent,snapshot,reconciled)
        intended=(json.dumps(document,ensure_ascii=False,indent=2)+'\n').encode() if document is not None else None
        if revision(intended)!=reconciled['provenance_after_revision']:raise ValueError('The explicitly selected current provenance postimage changed.')
    elif revision(observed)==intent['provenance_after_revision']:
        document=snapshot['documents']['provenance'];intended=observed
    else:
        if revision(observed)!=original['expected_provenance_revision']:
            raise ValueError('CHANGED_INPUT: provenance changed outside the pending exact publication.')
        document=_apply_provenance_patch(snapshot['documents']['provenance'],intent['provenance_patch'],
            inverse=_provenance_inverse(intent),section_id=intent['section_id'],root=root)
        intended=(json.dumps(document,ensure_ascii=False,indent=2)+'\n').encode() if document is not None else None
        if revision(intended)!=intent['provenance_after_revision']:
            raise ValueError('The scoped provenance patch does not reproduce its admitted postimage.')
    steps=['source-history','author-protection','provenance-publication'];finished=[]
    try:
        change=intent['source_changes'][0];path=root/change['file']
        home=root/source['manuscript_dir'];history_source='paragraph-restructure:'+source_value['receipt']['intent_artifact_id']
        versions=projection_viewer._load_saves_index(home).get('saves',[])
        matches=[row for row in versions if row.get('source')==history_source
            and row.get('sha')==change['after_sha256'].removeprefix('sha256:')]
        if len(matches)>1:raise ValueError('Ambiguous exact structural source history; inspect retained saves.')
        if matches:
            inspected=projection_viewer.read_editor_save(home,matches[0]['version_id'],repo_root=root)
            if (revision(inspected['data'])!=change['after_sha256'] if reconciled else inspected['data']!=path.read_bytes()) or inspected['live_file']!=path:
                raise ValueError('The structural source-history bytes or target do not match.')
        version=matches[0] if matches else None if reconciled else projection_viewer.bank_editor_save(home,path,path.read_bytes(),
            author=intent['actor'].get('kind','unknown'),surface='reader-restructure',source=history_source)
        finished.append('source-history')
        ids=list(dict.fromkeys(ident for row in intent['occurrence_mapping']['after'] for ident in row['spec_ids']))
        feedback=root/source['manuscript_dir']/'feedback/feedback.jsonl';feedback.parent.mkdir(parents=True,exist_ok=True)
        rec_id='EDIT-RESTRUCT-'+source_value['receipt']['intent_artifact_id']
        indexed=_protection_index(root,feedback)
        edit=edits.make_author_edit(intent['section_id'],ids[0] if ids else '',change['file'],change['before'],change['after'],
            kind='paragraph-restructure',lines=[change['line_start'],change['line_end']],project=project,
            actor='eigen:session' if intent['actor'].get('kind')=='agent' else 'author',rec_id=rec_id,spec_ids=ids)
        matches=indexed.by_id.get(rec_id) or []
        if matches:
            if len(matches)!=1:raise ValueError('Ambiguous structural author-protection receipt.')
            actual=records.raw_indexed_record(indexed,matches[0])
            if any(actual.get(key)!=edit.get(key) for key in ('record','id','project','before','after','anchor','kind','source')):
                raise ValueError('The exact structural protection receipt disagrees with admission.')
        else:journal.bank_row(feedback.relative_to(root).as_posix(),edit,root=root)
        finished.append('author-protection')
        if observed!=intended:
            if revision(observed)!=(reconciled['guards']['expected_provenance_revision'] if reconciled else original['expected_provenance_revision']):
                raise ValueError('CHANGED_INPUT: provenance changed outside the exact pending publication.')
            if document is None:
                artifacts.restore_owned_absence(root,project,target,revision(observed).removeprefix('sha256:'),
                    {'path':target.relative_to(root).as_posix(),'subjects':{},'reserved_ids':[]})
            else:_store(project,root,target,document,observed)
        complete=True
        finished.append('provenance-publication')
    except Exception as failure:error=str(failure)
    remaining=[name for name in steps if name not in finished]
    guards={**original,'expected_decision_revision':revision(snapshot['raw']['decisions']),
        'expected_provenance_revision':revision(target.read_bytes()) if target.is_file() else None,
        'source_guards':{row['file']:row['after_sha256'] for row in intent['source_changes']}}
    effect=source_effects.receipt(project,original['expected_selection'],source_value['source_effect']['files'],complete=complete,
        required=[{'owner':'paragraph-source','status':'COMPLETE'},
            *[{'owner':name,'status':'COMPLETE' if name in finished else 'FAILED' if name==remaining[0] else 'UNPROVED'}
              for name in steps]])
    value={'schema_version':SCHEMA,'project':project,'section_id':intent['section_id'],'kind':intent['kind'],
        'inverse_direction':'REDO' if _provenance_inverse(intent) else 'UNDO',
        'complete':complete,'source_committed':True,'source_effect':effect,'guards':guards,
        'source_scope':{key:intent['source_changes'][0][key] for key in ('file','line_start','line_end','after_line_end')},
        'review_obligations':copy.deepcopy(intent.get('review_obligations') or []),
        'metadata_path':target.relative_to(root).as_posix(),'remaining_steps':remaining,
        'source_receipt_id':source_value.get('source_receipt_id') or source_value['receipt']['id'],
        'receipt':{'intent_artifact_id':source_value['receipt']['intent_artifact_id'],'kind':intent['kind'],'remaining_steps':remaining,
            **({'versions':[version.get('version_id')]} if locals().get('version') else {})},
        'plan_publication':storyboard.reader_publication('paragraph-restructure','COMMITTED' if complete else 'PARTIAL',complete,1 if complete else 0),
        'remapped_occurrences':intent['occurrence_mapping']['after'],
        'source_changes':intent['source_changes']}
    from laplace.core.receipts import bundle
    value['owned_changes']=bundle(files=[*effect['files'],{'scope':'repository','path':target.relative_to(root).as_posix(),
        'before_sha256':original['expected_provenance_revision'],'after_sha256':intent['provenance_after_revision'],
        'observed_after_sha256':revision(target.read_bytes()) if target.is_file() else None}],views=['manuscript','document','structure','history'])
    effect['impact'].update(status='REOBSERVE',reads=[reader_plan.read_handle(project,intent['section_id'])],
        coverage='Exact source occurrence mapping and reader provenance only; unchanged logical plan and scientific acceptance are not renewed.')
    if reconciled:
        from laplace.manuscript.reader_restructure_reconciliation import qualify_result
        value=qualify_result(value,source_value,history_unavailable=not locals().get('version'))
    if error:value['error']=error
    return _actions(project,intent['section_id'],_record_receipt(project,root,value))


def _publish_metadata(project,root,intent,source_value):
    try:return _complete_metadata(project,root,intent,source_value)
    except Exception as exc:
        # A failed check or receipt bank occurs after a physical attempt. Keep
        # the observed effect and exact ART recovery; never turn it into refusal.
        value=copy.deepcopy(source_value);value['complete']=False;value['error']=str(exc)
        value['receipt_recorded']=bool(records.index(root).by_id.get(value['receipt']['id']))
        if 'receipt-publication' not in value['remaining_steps']:value['remaining_steps'].append('receipt-publication')
        value['source_effect']['complete']=False
        return _actions(project,intent['section_id'],value)


def _apply_staged(project,root,preview_value,*,actor=None,inverse=None):
    from laplace.manuscript import manuscript_source, manuscript_structure, projection_viewer
    from laplace.core.records import journal
    from laplace.pipeline import edits
    sid=preview_value['section_id'];snapshot=_snapshot(project,sid,root);guards=preview_value['guards']
    change=preview_value['source_changes'][0];path=root/change['file']
    before=path.read_bytes();lines=before.decode('utf-8').splitlines(keepends=True)
    if revision(before)!=change['before_sha256']:raise ValueError('CHANGED_INPUT: source changed before structural publication.')
    lo,hi=change['line_start'],change['line_end']
    if ''.join(lines[lo-1:hi])!=change['before']:raise ValueError('CHANGED_INPUT: source occurrence changed before structural publication.')
    after=(''.join(lines[:lo-1])+change['after']+''.join(lines[hi:])).encode()
    if revision(after)!=change['after_sha256']:raise ValueError('Structural postimage does not match its exact prepared bytes.')
    provenance_inverse=False
    if inverse is not None:
        patch=inverse['provenance_patch']
        provenance_inverse=not _provenance_inverse(inverse)
        provenance=_apply_provenance_patch(snapshot['documents']['provenance'],patch,inverse=provenance_inverse,section_id=sid,root=root)
    else:
        provenance,patch=_provenance_after(snapshot,preview_value,root)
    intent={'schema_version':SCHEMA,'project':project,'section_id':sid,'kind':preview_value['kind'],
        'guards':guards,'restructure_token':preview_value['restructure_token'],
        'decision_other_revision':fingerprint([row for row in (snapshot['documents']['decisions'] or {}).get('decisions',[]) if row.get('owner')!='reader-restructure']),
        'source_changes':preview_value['source_changes'],
        'occurrence_mapping':preview_value['occurrence_mapping'],'provenance_patch':patch,
        'provenance_direction':'inverse' if provenance_inverse else 'forward','actor':actor or {'kind':'human'},
        'review_obligations':copy.deepcopy(preview_value.get('review_obligations') or []),
        'source_receipt_id':'RPUB-'+uuid.uuid4().hex,
        'metadata_path':snapshot['paths']['provenance'].relative_to(root).as_posix(),
        'decision_path':snapshot['paths']['decisions'].relative_to(root).as_posix(),
        'provenance_after_revision':revision((json.dumps(provenance,ensure_ascii=False,indent=2)+'\n').encode()) if provenance is not None else None,
        **({'inverse_of':inverse['restructure_token']} if inverse is not None else {})}
    decisions=copy.deepcopy(snapshot['documents']['decisions'] or {'section_id':sid,'decisions':[]})
    intent_path=snapshot['paths']['decisions'].with_suffix('.restructure-intent.json')
    _,old_intent=reader_plan._json(intent_path)
    retained=_store(project,root,intent_path,intent,old_intent,
        metadata={'path':intent_path.relative_to(root).as_posix(),'subjects':{},'reserved_ids':[],
            'restructure_intent':{'section_id':sid,'kind':preview_value['kind'],'token':preview_value['restructure_token'],
                'source_receipt_id':intent['source_receipt_id']}})
    saved=retained['id']
    # The current decision file is a projection, not an archive of archived
    # intents. Exact historical operations remain their own immutable ART/RPUB.
    decisions['decisions']=[row for row in decisions.get('decisions',[]) if row.get('owner')!='reader-restructure']
    decisions['decisions'].append({'kind':'paragraph-restructure','section':sid,'owner':'reader-restructure','state':'INTENT',
        'spec_ids':list(dict.fromkeys(ident for row in preview_value['occurrence_mapping']['before'] for ident in row['spec_ids'])),
        'rationale':'Explicit presentation inverse' if inverse else 'Explicit presentation restructuring; logical identities are unchanged.',
        'intent_artifact_id':saved,'restructure_token':preview_value['restructure_token']})
    _store(project,root,snapshot['paths']['decisions'],decisions,snapshot['raw']['decisions'])
    # The immutable existing ART precedes physical effect. All later publication
    # recovery addresses that exact ART and a retained source-effect receipt.
    source=manuscript_source.resolve(project,repo_root=root)
    write_error=None
    with manuscript_source.selection_mutation(project,root),manuscript_source.source_mutation([path]):
        try:
            manuscript_source.source_access(project,path,root,writable=True,expected_selection=guards['expected_selection'])
            manuscript_structure._write_source(path,after.decode(),change['before_sha256'])
        except Exception as exc:write_error=str(exc)
        phase=_phase(project,root,intent,saved)
    try:
        phase=_record_receipt(project,root,phase);phase['receipt_recorded']=True
    except Exception as exc:
        phase['error']='Physical effect observed; receipt publication unavailable: '+str(exc)
        return _actions(project,sid,phase)
    if write_error or phase['source_effect']['state'] not in {'COMMITTED','UNCHANGED'}:
        phase['error']=write_error or 'Physical source disposition requires inspection.'
        phase.pop('recovery_action',None)
        return phase
    return _publish_metadata(project,root,intent,phase)


def change(project,payload,root,*,actor=None):
    from filelock import FileLock
    from jsonschema import Draft202012Validator
    payload=copy.deepcopy(payload)
    issue=next(Draft202012Validator(contracts()).iter_errors(payload),None)
    if issue:raise ValueError('Paragraph restructuring: '+issue.message)
    if payload['action'] not in {'preview-restructure','preview-reconciliation'} and any(key in payload for key in ('expected_selection','source_guards')):
        raise ValueError('Mutation source guards belong to the exact nested structural guard bundle.')
    if 'guards' in payload:
        from laplace.core.identity import revision_matches
        nested=payload.pop('guards')
        for key,item in nested.items():
            if key in payload and not (revision_matches(payload[key],item) if key=='expected_plan_revision' else payload[key]==item):
                raise ValueError('The structural guard bundle crosses a supplied owner identity.')
            payload[key]=item
    payload.pop('expected',None)
    root=Path(root).resolve();sid=payload['section_id'];name=payload['action']
    if name not in {'preview-restructure','preview-reconciliation'} and actor and (actor.get('dispatch_id') or actor.get('mode')=='review'):
        raise ValueError('Independent reviewers and dispatched children may inspect restructuring; the authorised parent applies it.')
    if name=='preview-reconciliation':
        return read(project,{'view':'restructure','section_ids':[sid],'receipt_id':payload['receipt_id'],
            'intent_artifact_id':payload['intent_artifact_id'],'reconcile_current':True,
            'current_occurrence_assignments':payload.get('current_occurrence_assignments',[])},root)
    if name=='preview-restructure':
        value=preview(project,sid,payload['kind'],payload['draft'],root)
        for key in ('expected_selection','source_guards'):
            if key in payload and payload[key]!=value['guards'][key]:raise ValueError('CHANGED_INPUT: the emitted block source lease changed; retain the draft.')
        return value
    snapshot=_snapshot(project,sid,root)
    plan=snapshot['record'].plan(root)
    with FileLock(str(plan)+'.structure.lock'),FileLock(str(plan)+'.publication.lock'),FileLock(str(snapshot['paths']['decisions'])+'.restructure.lock'):
        if name=='restructure':
            held=pending(project,sid,root)
            if held:raise ValueError('Complete the exact pending structural publication before another restructure: '+held[0]['receipt']['intent_artifact_id'])
            logical_kind=payload['kind'].startswith('logical-')
            if logical_kind:
                from laplace.manuscript import reader_logical_publication as logical_owner
                prepared,current,patch=logical_owner._prepared(project,sid,payload['kind'],payload['draft'],root)
            else:prepared=preview(project,sid,payload['kind'],payload['draft'],root)
            if not logical_kind and not prepared['source_changes']:raise ValueError('Supply the exact source body edit before applying.')
            if payload['restructure_token']!=prepared['restructure_token'] or any(payload.get(key)!=prepared['guards'][key] for key in prepared['guards']):
                raise ValueError('CHANGED_INPUT: structural preview/draft/basis changed; retain the authored draft and inspect again.')
            if logical_kind:
                from laplace.manuscript.reader_logical_publication import apply as logical_apply
                return logical_apply(project,root,prepared,actor=actor,admitted=(current,patch))
            return _apply_staged(project,root,prepared,actor=actor)
        value=_receipt(project,root,payload['receipt_id'],payload['intent_artifact_id'])
        if value['section_id']!=sid:raise ValueError('Structural receipt belongs to another section.')
        intent=_intent(project,root,payload['intent_artifact_id'])
        if name=='reconcile-restructure':
            from laplace.manuscript.reader_restructure_reconciliation import reconcile
            return reconcile(project,root,intent,value,payload,actor=actor)
        if any(key in payload and payload[key]!=value['guards'][key] for key in GUARDS):
            raise ValueError('The structural follow-through action crosses its exact receipt guards.')
        if intent['kind'].startswith('logical-'):
            from laplace.manuscript import reader_logical_publication as logical_owner
            if any(payload.get(key)!=value['guards'][key] for key in value['guards']):
                raise ValueError('Copy the exact logical follow-through guard bundle.')
            if name=='recover-restructure':return logical_owner.publish_metadata(project,root,intent,value)
            if not value['complete']:raise ValueError('Complete logical publication before its exact inverse.')
            snapshot=_snapshot(project,sid,root)
            if (revision(snapshot['raw']['narrative'])!=value['guards']['expected_narrative_revision']
                or revision(snapshot['raw']['provenance'])!=value['guards']['expected_provenance_revision']
                or revision(snapshot['raw']['decisions'])!=value['guards']['expected_decision_revision']
                or snapshot['state']['authority']['plan_revision']!=value['guards']['expected_plan_revision']):
                raise ValueError('CHANGED_INPUT: the logical inverse is no longer exact.')
            prepared={**value,'restructure_token':fingerprint(['inverse',payload['receipt_id'],value['guards']])}
            return logical_owner.apply(project,root,prepared,actor=actor,inverse_intent=intent)
        if name=='recover-restructure':return _publish_metadata(project,root,intent,value)
        if not value['complete'] or any(payload.get(key)!=value['guards'][key] for key in GUARDS):
            raise ValueError('Copy the exact complete structural inverse action; incomplete effects require recovery.')
        snapshot=_snapshot(project,sid,root)
        actual={'expected_plan_revision':snapshot['state']['authority']['plan_revision'],
            'expected_narrative_revision':revision(snapshot['raw']['narrative']),
            'expected_decision_revision':revision(snapshot['raw']['decisions']),
            'expected_provenance_revision':revision(snapshot['raw']['provenance'])}
        if any(actual[key]!=value['guards'][key] for key in actual):raise ValueError('CHANGED_INPUT: structural inverse is no longer exact.')
        old=intent['source_changes'][0]
        reversed_change={**old,'before':old['after'],'after':old['before'],
            'before_sha256':old['after_sha256'],'after_sha256':old['before_sha256'],
            'line_end':old['after_line_end'],'after_line_end':old['line_end']}
        prepared={'section_id':sid,'kind':value['kind'],'guards':value['guards'],
            'source_changes':[reversed_change],'occurrence_mapping':{'before':intent['occurrence_mapping']['after'],'after':intent['occurrence_mapping']['before']},
            'restructure_token':fingerprint(['inverse',payload['receipt_id'],value['guards']])}
        return _apply_staged(project,root,prepared,actor=actor,inverse=intent)


def latest_operation(project,section_id,root):
    """One indexed pointer/receipt summary; exact bodies/currentness stay lazy."""
    idx=records.index(root);meta=idx.reader_restructure_intents.get((project,section_id))
    if not meta:return None
    latest=idx.reader_restructure_receipts.get((project,meta['id']))
    if not latest:return None # pending() retains the ART-only unknown case.
    value=(latest.get('reader_metadata') or {}).get('restructure') or {}
    if not value.get('complete'):return None # Already shown by pending().
    receipt=value.get('receipt') or {}
    fields={'view':'restructure','section_ids':[section_id],'receipt_id':receipt['id'],'intent_artifact_id':receipt['intent_artifact_id']}
    read={'operation':'structure','payload':fields,
        'http':{'method':'GET','route':'/work/structure','query':{'project':project,**fields}}}
    return {'schema_version':SCHEMA,'project':project,'section_id':section_id,'kind':value['kind'],
        'complete':True,'receipt':{key:receipt[key] for key in ('id','intent_artifact_id','kind') if key in receipt},
        'metadata_only':bool(value.get('metadata_only')),'read_handle':read,'inverse_inspection_read':read,
        'currentness':{'status':'NOT_REOBSERVED','reason':'The operation is retained. Inspect its exact receipt to recheck source, reader metadata and consumed dependencies before its inverse.'}}


def inverse_currentness(project,root,intent,value):
    """Recheck the same inverse admission gates without publishing or searching."""
    if not value.get('complete') or value.get('metadata_only'):
        return {'status':'UNAVAILABLE','reason':'Complete pending metadata first, or use a new inspected structural change after later edits were retained.'}
    from laplace.manuscript import manuscript_source
    try:
        snapshot=_snapshot(project,intent['section_id'],Path(root))
        actual={'expected_plan_revision':snapshot['state']['authority']['plan_revision'],
            **{'expected_'+name+'_revision':revision(snapshot['raw'][name]) for name in ('narrative','decisions','provenance')}}
        # The public spelling is singular, as in the canonical guard bundle.
        actual['expected_decision_revision']=actual.pop('expected_decisions_revision')
        if any(actual[key]!=value['guards'][key] for key in actual):
            return {'status':'CHANGED','reason':'Reader metadata or its declared plan changed after this operation.'}
        source=manuscript_source.resolve(project,repo_root=root)
        if manuscript_source.selection_identity(source,project)!=value['guards']['expected_selection']:
            return {'status':'CHANGED','reason':'The selected manuscript identity changed after this operation.'}
        if any(revision((Path(root)/file).read_bytes())!=pin for file,pin in value['guards']['source_guards'].items()):
            return {'status':'CHANGED','reason':'The physical source postimage changed; the historical inverse cannot replay it.'}
        if intent['kind'].startswith('logical-'):
            from laplace.manuscript.reader_logical_publication import _verify_inputs
            _verify_inputs(project,Path(root),intent,snapshot)
            expected=dict(intent['source_file_guards'])
            expected.update({row['file']:row['after_sha256'].removeprefix('sha256:') for row in intent['source_changes']})
            if manuscript_source.observation(project,root)['file_revisions']!=expected:
                return {'status':'CHANGED','reason':'The selected source file set or another consumed source file changed after this operation.'}
    except (ValueError,OSError) as exc:
        return {'status':'CHANGED','reason':str(exc)[:500]}
    return {'status':'CURRENT','reason':'Exact source and metadata postimages and consumed reader inputs still match. The inverse rechecks these guards before writing.'}
