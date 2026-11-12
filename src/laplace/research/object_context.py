"""Local scientific object facets and explicit consumed bases in existing owners.

No Writing imports, actor inference, new entity identity, store or execution.
Cross-family composition belongs to domain.work.object_facets.
"""
from __future__ import annotations
import copy
from pathlib import Path
from laplace.core import identity

KINDS = {'concept': {'project','node'}, 'research-record': {'project','id'}, 'reference': {'project','key'}, 'research-concern': {'project','node','concern_id'}}


def reference(kind, project, ident):
    key = 'node' if kind == 'concept' else 'key' if kind == 'reference' else 'id'
    return identity.reference('domain.research',kind,{'project':project,key:ident})


def concern_reference(project,node,concern_id):
    return identity.reference('domain.research','research-concern',{'project':project,'node':node,'concern_id':concern_id})


def check_reference(value, project=None):
    problems=identity.reference_problems(value)
    if problems or value.get('owner')!='domain.research' or value.get('kind') not in KINDS:
        raise ValueError('Select an existing scientific owner reference.')
    target=value['identity']
    if set(target)!=KINDS[value['kind']] or any(not isinstance(v,str) or not v for v in target.values()):
        raise ValueError('Scientific reference identity fields do not match its owner.')
    if project is not None and target['project']!=project:raise ValueError('Scientific reference is outside the admitted project.')
    return copy.deepcopy(value)


def checked_consumed(value, project):
    if not isinstance(value,list) or len(value)>80:raise ValueError('consumed_bases must be a bounded list of inspected references.')
    result=[];seen=set()
    for item in value:
        if not isinstance(item,dict) or set(item)!={'reference','basis'} or identity.reference_problems(item['reference']):
            raise ValueError('Each consumed basis names exactly reference and basis.')
        ref=item['reference'];target=ref.get('identity') or {}
        namespace=target.get('project',target.get('namespace'))
        if namespace!=project:raise ValueError('Consumed inputs must belong to the admitted project.')
        if not isinstance(item['basis'],str) or not identity.revision_matches(item['basis'],item['basis']):
            raise ValueError('Consumed basis must be an owner-issued digest.')
        key=identity.reference_key(ref)
        if key in seen:raise ValueError('Consumed input reference is duplicated.')
        seen.add(key);result.append(copy.deepcopy(item))
    return result



def validate_consumed(root,project,items):
    values=checked_consumed(items,project)
    from laplace.projects import project_data,artifacts,writing_sources
    for item in values:
        reference=item['reference'];target=reference['identity'];kind=reference['kind']
        if reference['owner']=='domain.research':basis=read(root,project,reference)['basis']
        elif reference['owner']=='domain.projects' and kind=='source-file' and set(target)=={'project','path','scope'}:
            basis=project_data.selected_file(Path(root),project,target['path'],target['scope'])[2]['sha256']
        elif reference['owner']=='domain.projects' and kind=='artifact' and set(target)=={'project','id'}:
            basis=artifacts.identity(Path(root),project,{'id':target['id']})['revision']
        elif reference['owner']=='domain.projects' and kind=='repository-file' and set(target)=={'project','repository','path'}:
            basis=writing_sources.reference_identity(Path(root),{k:target[k] for k in ('repository','path')})['revision']
        else:raise ValueError('This scientific owner cannot validate that consumed input family.')
        if not identity.revision_matches(item['basis'],basis):raise ValueError('CHANGED_INPUT: consumed scientific input changed.')
    return values

def _concept_basis(node):
    projection=node.get('projection') or {}
    return identity.canonical_digest({k:node.get(k) for k in ('id','kind','essence','source','sources','ref')} |
        {'mathematics':projection.get('mathematics'),'consumed_bases':projection.get('consumed_bases',[])})


def _concept_title(node):
    return node.get('title') or node.get('label') or {'question':'Question','result':'Claim','technique':'Method','support':'Evidence note','definition':'Definition','postulate':'Assumption'}.get(node.get('kind'),str(node.get('kind') or 'Scientific object').replace('-',' ').title())


def geometry_observation(root,project,ref):
    """Recorded scientific metadata for one local hop, without source/body hydration.

    Scope admission and privacy of cross-owner references belongs to the composing
    Work owner. Currentness of raw sources is deliberately not asserted here.
    """
    ref=check_reference(ref,project);kind=ref['kind'];target=ref['identity']
    from laplace.research import concepts,research_context,research_records
    net=concepts._network(project,Path(root)) or {};nodes=net.get('nodes') or {}
    records=[];home=None
    if kind=='research-record':
        _item,home=research_context.project(project,Path(root))
        if home is None:raise ValueError('Scientific record custody unavailable.')
        records,error=research_records._records(home)
        if error:raise ValueError('Scientific record custody unavailable.')
    metadata={};relations=[];events=[]
    if kind in {'concept','research-concern'}:
        if target['node'] not in nodes:raise ValueError('Scientific object unavailable.')
        for ident,node in nodes.items():
            r=reference('concept',project,ident)
            metadata[identity.reference_key(r)]={'reference':r,'title':_concept_title(node),'basis':_concept_basis(node),
                'kind':node.get('kind'),'standing':{'state':'RECORDED','scientific_validity':'NOT_ASSERTED'}}
            p=node.get('projection') or {}
            if node.get('parent') in nodes:
                relations.append({'source':reference('concept',project,node['parent']),'target':r,'kind':'contains','qualification':'RECORDED_CONTAINMENT'})
            for member in node.get('members') or []:
                if isinstance(member,str) and member in nodes:relations.append({'source':r,'target':reference('concept',project,member),'kind':'contains','qualification':'RECORDED_CONTAINMENT'})
            for consumed in p.get('consumed_bases') or []:
                if isinstance(consumed,dict) and isinstance(consumed.get('reference'),dict):
                    relations.append({'source':consumed['reference'],'target':r,'kind':'consumed','consumed_basis':consumed.get('basis'),'qualification':'PINNED'})
            for rid in p.get('result_bindings') or []:
                if isinstance(rid,str):relations.append({'source':reference('research-record',project,rid),'target':r,'kind':'related-unpinned','qualification':'RESULT_BINDING_UNPINNED'})
        typed,rewires=concepts._relations(project,Path(root),net)
        for row in typed:
            if row.get('source') in nodes and row.get('target') in nodes:
                relations.append({'source':reference('concept',project,row['source']),'target':reference('concept',project,row['target']),
                    'kind':'requires' if row.get('rel')=='prerequisite' else 'related-unpinned','label':row.get('rel'),'qualification':'RELATED_UNPINNED'})
        # Canonical rewire rows are the event order. A current concern snapshot
        # is not an additional invented history event.
        for row in rewires:
            if row.get('node')!=target['node']:continue
            history=(row.get('value') or {}).get('research_object_history') if isinstance(row.get('value'),dict) else None
            event=history[-1] if history else {}
            operation=event.get('operation') or row.get('kind') or 'scientific-change'
            events.append({'kind':operation,'title':operation.replace('-',' ').title(),'timestamp':row.get('ts'),
                'basis':identity.canonical_digest(row),'record_id':row.get('id')})
    elif kind=='research-record':
        row=next((x for x in records if x.get('id')==target['id']),None)
        if row is None:raise ValueError('Scientific record unavailable.')
        for item in records:
            r=reference('research-record',project,item['id'])
            metadata[identity.reference_key(r)]={'reference':r,'title':item.get('title') or item['id'],
                'basis':item.get('revision') or research_records._record_revision(item),'kind':item['kind'],
                'standing':{'state':'RECORDED','currentness':'NOT_CHECKED','scientific_validity':'NOT_ASSERTED'}}
        for consumed in row.get('consumed_bases') or []:
            relations.append({'source':consumed['reference'],'target':ref,'kind':'consumed','consumed_basis':consumed['basis'],'qualification':'PINNED'})
        # Existing canonical renewal history retains actual editions in owner order.
        history=research_records._renewal_history(home).get(target['id'],[])
        for item in history:
            events.append({'kind':'record-renewal','title':'Recorded result edition','timestamp':item.get('archived_at') or item.get('recorded_at'),
                'basis':item.get('revision')})
        events.append({'kind':'record-current','title':'Current recorded result edition','timestamp':row.get('updated_at') or row.get('ts') or (row.get('provenance') or {}).get('recorded_at'),
            'basis':row.get('revision') or research_records._record_revision(row)})
    elif kind=='reference':
        from laplace.research import literature
        _provider,item=literature.resolve_item(project,target['key'],Path(root))
        if item is None:raise ValueError('Retained reference metadata unavailable.')
        metadata[identity.reference_key(ref)]={'reference':ref,'title':(item.get('metadata') or {}).get('title') or item.get('title') or target['key'],
            'basis':None,'kind':'reference','standing':{'state':'CATALOGUED','source_currentness':'NOT_CHECKED'}}
    else:raise ValueError('No compact scientific geometry for this family.')
    if kind=='research-concern':
        selected=nodes[target['node']];concern=next((x for x in (selected.get('projection') or {}).get('reconsiderations') or [] if x.get('id')==target['concern_id']),None)
        if concern is None:raise ValueError('Scientific concern unavailable.')
        parent=reference('concept',project,target['node'])
        metadata[identity.reference_key(ref)]={'reference':ref,'title':'Scientific reconsideration','basis':identity.canonical_digest(concern),
            'kind':'research-concern','standing':{'state':concern['state'],'scientific_validity':'NOT_ASSERTED'}}
        relations=[{'source':parent,'target':ref,'kind':'contains','qualification':'CANONICAL_CONCERN'}]
        events=[]
        for row in rewires:
            history=(row.get('value') or {}).get('research_object_history') if isinstance(row.get('value'),dict) else None
            event=history[-1] if history else {}
            if row.get('node')==target['node'] and event.get('concern_id')==target['concern_id']:
                operation=event.get('operation') or 'scientific-change'
                events.append({'kind':operation,'title':operation.replace('-',' ').title(),'timestamp':row.get('ts'),'basis':identity.canonical_digest(row)})

    return {'metadata':metadata,'relations':relations,'events':events,'coverage':{'state':'RECORDED_OWNER_METADATA','source_currentness':'NOT_CHECKED','history':'Canonical rewire order for concepts; current record and existing bounded renewal history for records. Exact source bytes are not read.'}}


def read(root,project,ref):
    ref=check_reference(ref,project);kind=ref['kind'];target=ref['identity']
    from laplace.research import concepts, research_context, research_records, literature
    if kind in {'concept','research-concern'}:
        net=concepts._network(project,Path(root))
        node=(net or {}).get('nodes',{}).get(target['node'])
        if node is None:raise ValueError('Selected scientific object is unavailable.')
        node=copy.deepcopy(node);projection=node.get('projection') or {}
        if kind=='research-concern':
            concern=next((x for x in projection.get('reconsiderations') or [] if x.get('id')==target['concern_id']),None)
            if concern is None:raise ValueError('Selected scientific concern is unavailable.')
            return {'reference':ref,'basis':identity.canonical_digest(concern),'title':'Scientific reconsideration',
                'purpose':concern.get('summary') or '', 'kind':kind,'value':copy.deepcopy(concern),
                'consumed_bases':[],'concerns':[],'relations':[],
                'currentness':{'state':concern['state'],'scientific_validity':'JUDGEMENT_RECORDED' if concern['state']=='DISPOSED' else 'NOT_ASSERTED'}}
        # Authored meaning and recorded consumption are distinct from collection
        # CAS, history and reconsideration presentation.
        basis=_concept_basis(node)
        plan=concepts.logical_plan(project,focus=target['node'],root=Path(root),limit=1)
        return {'reference':ref,'basis':basis,'title':_concept_title(node),
            'purpose':node.get('essence') or '', 'kind':node.get('kind'),'value':node,
            'mutation_revision':plan['revision'],'consumed_bases':copy.deepcopy(projection.get('consumed_bases') or []),
            'concerns':copy.deepcopy(projection.get('reconsiderations') or []),
            'relations':copy.deepcopy(next((r['relations'] for r in plan.get('objects',[]) if r['id']==target['node']),[])),
            'currentness':{'state':'CURRENT_AT_READ','scientific_validity':'NOT_ASSERTED'}}
    if kind=='research-record':
        item,home=research_context.project(project,Path(root))
        if home is None:raise ValueError('Research owner home is unavailable.')
        rows,error=research_records._records(home)
        if error:raise ValueError('Research record custody is unavailable.')
        row=next((r for r in rows if r.get('id')==target['id']),None)
        if row is None:raise ValueError('Selected research record is unavailable.')
        current=research_records._currentness(home,[row],research_context.project_root(item,Path(root)))
        return {'reference':ref,'basis':row.get('revision') or research_records._record_revision(row),
            'title':row.get('title') or row['id'],'purpose':row.get('summary') or row.get('question') or '',
            'kind':row['kind'],'value':copy.deepcopy(row),'consumed_bases':copy.deepcopy(row.get('consumed_bases') or []),
            'concerns':[],'relations':[], 'currentness':{'state':current['status'],'reason':current['reason'],'scientific_validity':'NOT_ASSERTED'}}
    provider,item=literature.resolve_item(project,target['key'],Path(root))
    if item is None:raise ValueError('Selected retained reference is unavailable.')
    try:source_info,_path=literature.source_info(project,target['key'],Path(root))
    except (OSError,ValueError):source_info={'available':False,'sha256':None}
    return {'reference':ref,'basis':identity.canonical_digest({'item':item,'source_sha256':source_info.get('sha256')}),'title':(item.get('metadata') or {}).get('title') or item.get('title') or target['key'],
        'purpose':(item.get('metadata') or {}).get('abstract') or '', 'kind':'reference','value':copy.deepcopy(item),
        'provider':provider,'source_sha256':source_info.get('sha256'),'consumed_bases':[], 'concerns':[], 'relations':[],
        'currentness':{'state':'OBSERVED_AT_READ','scientific_validity':'NOT_ASSERTED'}}


def relations(root,project):
    """Recorded scientific consumption only, with unpinned relations kept separate."""
    from laplace.research import concepts, research_context, research_records
    net=concepts._network(project,Path(root)) or {};result=[]
    for ident,node in (net.get('nodes') or {}).items():
        dependent=reference('concept',project,ident);p=node.get('projection') or {}
        for consumed in p.get('consumed_bases') or []:
            if isinstance(consumed,dict) and 'reference' in consumed and 'basis' in consumed:
                result.append({'dependent':dependent,**copy.deepcopy(consumed),'relation':'consumed','qualification':'PINNED'})
        for ident2 in p.get('result_bindings') or []:
            if isinstance(ident2,str):result.append({'dependent':dependent,'reference':reference('research-record',project,ident2),'basis':None,'relation':'result-binding','qualification':'RELATED_UNPINNED'})
    for relation in (net.get('relations') or []):
        if relation.get('source') and relation.get('target'):
            result.append({'dependent':reference('concept',project,relation['source']),
                'reference':reference('concept',project,relation['target']),'basis':None,
                'relation':relation.get('rel'),'qualification':'RELATED_UNPINNED'})
    item,home=research_context.project(project,Path(root))
    if home is not None:
        rows,error=research_records._records(home)
        if error:raise ValueError('Research dependency custody is unavailable.')
        for row in rows:
            for consumed in row.get('consumed_bases') or []:
                result.append({'dependent':reference('research-record',project,row['id']),**copy.deepcopy(consumed),
                    'relation':'consumed','qualification':'PINNED'})
            for obs in (row.get('provenance') or {}).get('dependencies') or []:
                digest=obs.get('sha256')
                if obs.get('path') and digest:
                    result.append({'dependent':reference('research-record',project,row['id']),
                        'reference':identity.reference('domain.projects','source-file',{'project':project,
                            'path':obs['path'],'scope':obs.get('scope',row.get('scope','manuscript'))}),
                        'basis':digest,'relation':'recorded-input','qualification':'PINNED'})
    return result


def change(root,project,payload,*,admit,inspect_only=False):
    """A fixed scientific projection mutation, through canonical rewire precondition.

    `admit` is a trusted owner callback supplied by the actual Work/human door,
    never JSON. It validates the effective judgement/actor before publication.
    """
    from laplace.research import concepts, corpus_ingest
    if not callable(admit):raise TypeError('The actual owner supplies judgement admission.')
    allowed={'reference','expected_basis','expected_concern_basis','request_id','operation','consumed_bases','inputs','concern_id','changed','change_kind','summary','disposition','evidence'}
    if not isinstance(payload,dict) or set(payload)-allowed:raise ValueError('Scientific object change contains unsupported fields.')
    ref=check_reference(payload.get('reference'),project)
    if ref['kind']!='concept':raise ValueError('Scientific concern disposition selects a canonical claim/question.')
    operation=payload.get('operation');request_id=payload.get('request_id')
    if operation not in {'bind-consumed','mark-reconsideration','clear-reconsideration'} or not isinstance(request_id,str) or not 1<=len(request_id)<=96:
        raise ValueError('Select a supported operation and stable request identity.')
    intent=identity.canonical_digest(payload)
    current=read(root,project,ref);projection=current['value'].get('projection') or {}
    history=projection.get('research_object_history') or []
    for event in history:
        if event.get('request_id')==request_id:
            if event.get('intent')!=intent:raise ValueError('Scientific request identity names different intent.')
            response={'state':'RECORDED','reused':True,'reference':ref,'event':copy.deepcopy(event),'basis':current['basis']}
            rows=[row for row in corpus_ingest.rewire_list(root,project) if row.get('node')==ref['identity']['node']
                and ((row.get('value') or {}).get('research_object_history') or [{}])[-1].get('request_id')==request_id]
            if len(rows)!=1:raise ValueError('Recorded scientific request custody is unavailable or ambiguous.')
            response['event']['record_id']=rows[0]['id']
            if payload.get('concern_id'):
                pointer=concern_reference(project,ref['identity']['node'],payload['concern_id'])
                response['concern']={'reference':pointer,'basis':read(root,project,pointer)['basis'],'record_id':rows[0]['id']}
            return response
    if inspect_only:return {'state':'NONE','reference':ref,'request_id':request_id,'terminal':False}
    if not identity.revision_matches(payload.get('expected_basis'),current['basis']):raise ValueError('CHANGED_INPUT: selected scientific meaning changed.')
    evidence=payload.get('evidence') or []
    if not isinstance(evidence,list) or any(identity.reference_problems(r) for r in evidence):raise ValueError('Disposition evidence must be qualified references.')
    concerns=copy.deepcopy(projection.get('reconsiderations') or []);value={}
    if operation=='bind-consumed':
        selected=payload.get('inputs')
        if selected is not None:
            if 'consumed_bases' in payload or not isinstance(selected,list) or any(not isinstance(x,dict) or set(x)-{'reference','expected_basis','selection'} or not {'reference','expected_basis'}<=set(x) for x in selected):raise ValueError('Use one exact selected-input list.')
            value['consumed_bases']=validate_consumed(root,project,[{'reference':x['reference'],'basis':x['expected_basis']} for x in selected])
            value['selected_inputs']=copy.deepcopy(selected)
        else:value['consumed_bases']=validate_consumed(root,project,payload.get('consumed_bases'))
    else:
        ident=payload.get('concern_id')
        if not isinstance(ident,str) or not ident:raise ValueError('A concern has an exact identity.')
        old=next((x for x in concerns if x.get('id')==ident),None)
        if operation=='mark-reconsideration':
            changed=checked_consumed([payload.get('changed')],project)[0]
            if payload.get('change_kind') not in {'version','assumption'}:raise ValueError('Select version or assumption concern.')
            if not any(identity.reference_key(x['reference'])==identity.reference_key(changed['reference']) and identity.revision_matches(x['basis'],changed['basis']) for x in current['consumed_bases']):
                raise ValueError('No recorded consumed basis supports this concern.')
            if old is not None:raise ValueError('Concern already exists; retain its original identity/history.')
            concerns.append({'id':ident,'state':'OPEN','change_kind':payload['change_kind'],'changed':changed,'summary':str(payload.get('summary') or '')})
        else:
            if old is None or old.get('state')!='OPEN':raise ValueError('No open concern matches this disposition.')
            if not identity.revision_matches(payload.get('expected_concern_basis'),identity.canonical_digest(old)):
                raise ValueError('CHANGED_INPUT: inspect the exact canonical concern before disposition.')
            if payload.get('disposition') not in {'ACCEPT','REVISE','WITHDRAW','UNCHANGED'}:raise ValueError('Select an explicit disposition.')
            # A provenance assertion cannot discharge scientific meaning.
            if old['change_kind']=='assumption' and payload['disposition']=='UNCHANGED':raise ValueError('Unchanged producer bytes do not answer a scientific assumption.')
            old.update(state='DISPOSED',disposition=payload['disposition'],summary=str(payload.get('summary') or ''),evidence=copy.deepcopy(evidence))
        value['reconsiderations']=concerns
    admitted=admit(copy.deepcopy(payload),copy.deepcopy(current))
    if not isinstance(admitted,dict) or admitted.get('kind') not in {'author','judgement','revalidation'}:
        raise ValueError('Actual owner admission is unavailable.')
    if operation=='clear-reconsideration' and old.get('change_kind')=='assumption' and admitted['kind'] not in {'author','judgement'}:
        raise ValueError('A scientific assumption requires bound judgement or author disposition.')
    event={'request_id':request_id,'intent':intent,'operation':operation,'authority':copy.deepcopy(admitted),
        'concern_id':payload.get('concern_id'),'disposition':payload.get('disposition')}
    value['research_object_history']=[*copy.deepcopy(history),event]
    def precondition():
        now=read(root,project,ref)
        if now['basis']!=current['basis'] or (now['value'].get('projection') or {}).get('research_object_history',[])!=history:
            raise ValueError('CHANGED_INPUT: scientific projection changed before publication.')
        if operation=='bind-consumed':validate_consumed(root,project,value['consumed_bases'])
        admit(copy.deepcopy(payload),copy.deepcopy(now))
    out=corpus_ingest.rewire_add(root,project,{'kind':'set-projection','node':ref['identity']['node'],'value':value,'by':str(admitted.get('actor') or 'owner')},precondition=precondition)
    if out.get('error'):raise ValueError('Scientific projection publication refused: '+str(out['error']))
    response={'state':'RECORDED','reused':False,'reference':ref,'event':{**event,'record_id':out['record']['id']},'basis':read(root,project,ref)['basis'],'owned_changes':out.get('owned_changes')}
    if payload.get('concern_id'):
        pointer=concern_reference(project,ref['identity']['node'],payload['concern_id'])
        response['concern']={'reference':pointer,'basis':read(root,project,pointer)['basis'],'record_id':out['record']['id']}
    return response



def question_request(root,project,original,*,action='read',admit=None):
    """Same-question Save/reconcile/settle in the existing canonical rewire owner.

    Terminal non-admission is an existing root projection event, not a phantom
    question or a new request ledger. Exact late copies consult it before guards.
    """
    from laplace.research import concepts,corpus_ingest
    from laplace.projects import project_data
    allowed={'project','operation','node','meaning','base_revision','request_id'}
    optional={'object_kind','parent','inputs'}
    if not isinstance(original,dict) or not allowed<=set(original) or set(original)-allowed-optional or original.get('project')!=project or original.get('operation') not in {'save-question','save-object'}:raise ValueError('Retain the exact closed original question Save request.')
    for key in ('node','meaning','base_revision','request_id'):
        if not isinstance(original[key],str) or not original[key].strip():raise ValueError('Question Save requires nonempty '+key+'.')
    if len(original['node'])>160 or len(original['request_id'])>96:raise ValueError('Question identity is outside the supported bound.')
    intent=identity.canonical_digest(original);request_id=original['request_id'];root=Path(root).resolve()
    object_kind=original.get('object_kind','question')
    if object_kind not in {'question','result','technique','support'}:raise ValueError('Unsupported scientific object kind.')
    if original['operation']=='save-question' and object_kind!='question':raise ValueError('Question operation requires question kind.')
    inputs=original.get('inputs',[])
    if not isinstance(inputs,list) or len(inputs)>80 or any(not isinstance(x,dict) or set(x)-{'reference','expected_basis','selection'} or not {'reference','expected_basis'}<=set(x) for x in inputs):raise ValueError('Retain exact selected input descriptors.')
    def response(state,**extra):
        return {'schema_version':'laplace.research-object-mutation/1','operation':original['operation'],'project':project,
            'request_id':request_id,'intent_sha256':intent,'original_request':copy.deepcopy(original),
            'state':state,'terminal':state in {'RECORDED','NOT_ADMITTED'},**extra}
    def lookup():
        try:
            path=corpus_ingest._rewire_path(root,project)
            rows=project_data._rows(root,path.relative_to(root).as_posix(),max_bytes=project_data.MAX_JSON,max_rows=100000)
        except (ValueError,OSError):return response('UNKNOWN',reason_code='REQUEST_CUSTODY_UNAVAILABLE')
        found=[]
        for _rel,_line,_raw,row in rows:
            receipt=(row.get('projection') or {}).get('research_object_request') if row.get('kind')=='add-node' else (row.get('value') or {}).get('research_object_request_outcome')
            if isinstance(receipt,dict) and receipt.get('request_id')==request_id:found.append((row,receipt))
        if len(found)>1:return response('UNKNOWN',reason_code='REQUEST_CUSTODY_AMBIGUOUS')
        if not found:return response('NONE',reason_code='NO_RETAINED_OUTCOME')
        row,outcome=found[0]
        if outcome.get('intent')!=intent:raise ValueError('Question request identity belongs to different original intent.')
        state=outcome.get('state')
        if (state=='RECORDED' and (row.get('kind')!='add-node' or row.get('node')!=original['node'])) or (state=='NOT_ADMITTED' and row.get('kind')!='set-projection'):return response('UNKNOWN',reason_code='REQUEST_CUSTODY_MISMATCH')
        if state not in {'RECORDED','NOT_ADMITTED'}:return response('UNKNOWN',reason_code='REQUEST_CUSTODY_UNSUPPORTED')
        extra={'record_id':row['id'],'reason_code':outcome.get('reason_code')}
        if state=='RECORDED':
            reference_value=reference('concept',project,original['node']);extra.update(reference=reference_value)
        return response(state,**extra)
    prior=lookup()
    if prior['state']!='NONE' or action=='read':return prior
    if action not in {'save','settle'} or not callable(admit):raise ValueError('An actual owner supplies question mutation admission.')
    current=concepts.logical_plan(project,root=root,limit=1)
    if not current:return response('UNKNOWN',reason_code='LOGICAL_OWNER_UNAVAILABLE')
    root_node=(concepts._network(project,root) or {}).get('root')
    if not root_node:return response('UNKNOWN',reason_code='LOGICAL_OWNER_UNAVAILABLE')
    from laplace.manuscript import manuscript_source
    def source_ok():return not manuscript_source.resolve(project,repo_root=root).get('read_only')
    consumed=[{'reference':x['reference'],'basis':x['expected_basis']} for x in inputs]
    terminal=action=='settle' or not identity.revision_matches(original['base_revision'],current['revision']) or not source_ok()
    if not terminal:validate_consumed(root,project,consumed)
    if not terminal and original.get('parent'):
        parent=read(root,project,reference('concept',project,original['parent']))
        if parent['kind']!='question':raise ValueError('Selected parent must be an existing question.')
    reason='EXPLICITLY_SETTLED' if action=='settle' else 'CHANGED_INPUT' if terminal else None
    def precondition():
        prior=lookup()
        if prior['state']!='NONE':raise ValueError('Question outcome already exists or is uncertain.')
        now=concepts.logical_plan(project,root=root,limit=1)
        if not now:raise ValueError('Question owner is unavailable.')
        admit(copy.deepcopy(original),{'revision':now['revision']})
        if not terminal:validate_consumed(root,project,consumed)
        if not terminal and (not source_ok() or not identity.revision_matches(original['base_revision'],now['revision'])):
            raise ValueError('CHANGED_INPUT: question owner changed before admission.')
        if terminal and action!='settle' and source_ok() and identity.revision_matches(original['base_revision'],now['revision']):
            raise ValueError('Question refusal standing changed before settlement; retain uncertainty.')
    marker={'request_id':request_id,'intent':intent,'state':'NOT_ADMITTED' if terminal else 'RECORDED','reason_code':reason}
    if terminal:payload={'kind':'set-projection','node':root_node,'value':{'research_object_request_outcome':marker},'by':'question-owner'}
    else:payload={'kind':'add-node','node':original['node'],'node_kind':object_kind,'essence':original['meaning'],
        'parent':original.get('parent') or root_node,'projection':{'research_object_request':marker,'consumed_bases':consumed,'selected_inputs':copy.deepcopy(inputs)},'by':'question-owner'}
    try:
        out=corpus_ingest.rewire_add(root,project,payload,precondition=precondition)
        if out.get('error'):raise ValueError('Question owner refused publication.')
    except (ValueError,OSError):
        observed=lookup()
        if observed['state']!='NONE':return observed
        return response('UNKNOWN',reason_code='PUBLICATION_OR_ADMISSION_UNCERTAIN')
    return lookup()
