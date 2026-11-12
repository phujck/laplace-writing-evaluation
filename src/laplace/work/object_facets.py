"""Owner-qualified research workbench composition at domain.work.

No new object, store, authority or runner. Scientific facts stay in Research;
this layer joins their issued reads with projects, Work and Writing facets.
"""
from __future__ import annotations
import copy,json,uuid
from pathlib import Path
from urllib.parse import urlencode
from laplace.core import identity
from laplace.work import owner_discovery as O

SCHEMA='laplace.object-facets/1'
FACETS=('purpose','standing','relationships','inputs_outputs','settings','actions','feedback','history')
FAMILIES=('all','work','concept','research-record','reference','artifact','workflow-definition')
PAGE=20
MAX_PAGE=50


def handle(payload):
    values={k:json.dumps(v,sort_keys=True,separators=(',',':')) if isinstance(v,(dict,list)) else v for k,v in payload.items() if v is not None}
    return {'http':{'method':'GET','url':'/work/discovery?'+urlencode(values)},
        'native':{'operation':'project','payload':{'view':'discovery','request':copy.deepcopy(payload)}},
        'sdk':{'method':'request','payload':copy.deepcopy(payload)}}


def ref(owner,kind,**keys):return identity.reference(owner,kind,keys)
def _project(reference):
    value=reference.get('identity') or {};return value.get('project',value.get('namespace'))
def _scope(scope,project):
    if not project or not scope.admits(project):raise O.DiscoveryRefusal('NOT_IN_SCOPE','This object is unavailable in the admitted scope.')


def _ref(value):
    if identity.reference_problems(value):raise ValueError('Select an exact owner-qualified object reference.')
    return copy.deepcopy(value)


def _state(value=None,*,state='AVAILABLE',reason=None,items=None):
    out={'state':state}
    if value is not None:out['value']=value
    if items is not None:out['items']=items
    if reason:out['reason']=reason
    return out


def _empty():return {key:_state(state='UNAVAILABLE',reason='The selected owner exposes no '+key+' facet here.') for key in FACETS}


def _projects(root,scope):
    from laplace.projects import library
    return [row for row in library._library(Path(root))['projects'] if scope.admits(row['name'])]


def _controls(root,scope,payload):
    stable={k:v for k,v in payload.items() if k not in {'as_of','offset'}}
    choices=[{'id':None,'title':'All permitted projects','read':handle({k:v for k,v in stable.items() if k!='project_lens'})}]
    choices.extend({'id':row['name'],'title':row['title'],'read':handle({**stable,'project_lens':row['name']})} for row in _projects(root,scope))
    return choices,{'family':{'value':payload.get('family','all'),'choices':[{'id':x,'title':x.replace('-',' ').title(),
        'read':handle({**stable,'family':x})} for x in FAMILIES]} if payload.get('facet')=='workspace' else {}}


def _envelope(root,scope,payload,subject,basis,facets,items=(),coverage=None):
    if payload.get('as_of') and not identity.revision_matches(payload['as_of'],basis):
        raise O.DiscoveryRefusal('CHANGED_INPUT','Owner observations changed; explicitly restart this selected read.',
            next_reads=[handle({k:v for k,v in payload.items() if k not in {'as_of','offset'}})])
    lenses,controls=_controls(root,scope,payload)
    return {'schema_version':SCHEMA,'view':payload['facet'],'subject':subject,'basis':basis,
        'scope':scope.public(),'scope_id':__import__('laplace.pipeline.workflow_definitions',fromlist=['_scope_id'])._scope_id(root,scope),'project_lens':payload.get('project_lens'),'project_lenses':lenses,'controls':controls,
        'facets':facets,'items':list(items),'coverage':coverage or {'state':'SELECTED_OWNER_READ','known':1,'omitted':0},
        'pagination':{'offset':payload.get('offset',0),'limit':payload.get('limit',PAGE),'next_read':None,
            'restart_read':handle({k:v for k,v in payload.items() if k not in {'as_of','offset'}})},
        'help':{'http':{'method':'GET','url':'/authoring/help?view=areas'}},
        **__import__('laplace.work.object_geometry',fromlist=['navigation']).navigation(subject,project_lens=payload.get('project_lens'))}


def _read(project,operation,payload,url):
    return {'native':{'operation':operation,'payload':payload},'http':{'method':'GET','url':url+('?' if '?' not in url else '&')+urlencode({'project':project,**payload})}}


def _research_entry(root,scope,project):
    """Existing project Research capability, without inventing a workspace namespace."""
    if not project or not scope.admits(project):return None
    from laplace.projects import library
    if not library.project_capabilities(project,Path(root))['capabilities'].get('research'):return None
    return {'id':'registered-research','title':'Registered methods and results','permitted':True,
        'read':_read(project,'research',{'view':'summary'},'/research/state'),
        'adapter':{'kind':'research-evidence','project':project}}


def _scientific(root,scope,reference):
    from laplace.research import object_context as R
    project=_project(reference);_scope(scope,project);local=R.read(root,project,reference);facets=_empty()
    facets['purpose']=_state({'title':local['title'],'summary':local['purpose']})
    current=local['currentness'];facets['standing']=_state({'label':current['state'],'qualification':current.get('reason') or 'Observed owner state; scientific validity is not asserted.',**current})
    facets['relationships']=_state(items=local['relations'])
    facets['inputs_outputs']=_state(items=[{'reference':x['reference'],'basis':x['basis'],'read':handle({'facet':'object','reference':x['reference']})} for x in local['consumed_bases']])
    facets['feedback']=_state(items=[{**x,'reference':R.concern_reference(project,reference['identity'].get('node'),x['id']),
        'basis':identity.canonical_digest(x),'read':handle({'facet':'object','reference':R.concern_reference(project,reference['identity'].get('node'),x['id'])})} for x in local['concerns']])
    if reference['kind']=='concept':
        actions=_question_actions(root,project,reference['identity']['node']) if local['kind']=='question' else []
        actions.append(_consumed_action(project,reference,local['basis']))
        facets['actions']=_state(items=actions)
    if reference['kind']=='research-concern' and local['value'].get('state')=='OPEN':
        target=reference['identity'];subject=R.reference('concept',project,target['node']);current=R.read(root,project,subject)
        dispositions=['ACCEPT','REVISE','WITHDRAW'] if local['value'].get('change_kind')=='assumption' else ['ACCEPT','REVISE','WITHDRAW','UNCHANGED']
        wire={'project':project,'operation':'clear-reconsideration','reference':subject,'expected_basis':current['basis'],
            'expected_concern_basis':local['basis'],'concern_id':target['concern_id'],'request_id':uuid.uuid4().hex,'evidence':[]}
        facets['actions']=_state(items=[{'id':'author-disposition','title':'Record author judgement','permitted':scope.door in {'http','sdk'},
            'fields':[{'name':'disposition','label':'Judgement','type':'select','choices':dispositions,'required':True},
                {'name':'summary','label':'Reasoned judgement','type':'textarea','required':True}],
            'http':{'method':'POST','url':'/work/object-change','payload':wire},
            'reconcile':{'http':{'method':'GET','url':'/work/discovery'},'request':{'facet':'object-request','project_lens':project},'field':'object_request'}}])
    kind=reference['kind'];target=reference['identity']
    op='concept' if kind in {'concept','research-concern'} else 'research' if kind=='research-record' else 'reference_text'
    query={'node':target['node']} if kind in {'concept','research-concern'} else {'view':'result','id':target['id']} if kind=='research-record' else {'key':target['key']}
    url='/concepts/context' if kind in {'concept','research-concern'} else '/research/result' if kind=='research-record' else '/references/text'
    facets['history']=_state({'read':_read(project,op,query,url)})
    if kind=='reference' and local.get('source_sha256'):
        from laplace.research import literature
        facets['inputs_outputs']=_state(items=[{'reference':reference,'basis':local['basis'],'read':literature._reference_handle(project,target['key'],'reference_text','/references/text',offset=0,limit=4000,expected_source_revision=local['source_sha256'])}])
    if local['kind'] in {'question','technique','method','result'}:
        entry=_research_entry(root,scope,project)
        if entry:facets['actions']=_state(items=[*facets['actions'].get('items',[]),entry])
    local['facets']=facets
    return local


def _source(root,scope,reference,selection=None):
    from laplace.projects import project_data,writing_sources,artifacts
    project=_project(reference);_scope(scope,project);target=reference['identity'];kind=reference['kind']
    selection=dict(selection or {});offset=selection.get('offset',0);limit=selection.get('limit',4000)
    if type(offset)!=int or offset<0 or type(limit)!=int or not 1<=limit<=40000:raise ValueError('Use the existing 1-40000 character read window.')
    if kind=='artifact':
        if reference['owner']!='domain.projects' or set(target)!={'project','id'}:raise ValueError('Select an exact existing artifact ID.')
        indexed=artifacts._artifact_record(Path(root),project,target['id'])
        indexed['reader_metadata']=artifacts.reader_receipt(Path(root),project,target['id'])
        path,rel,scope_name,row=artifacts._artifact_target(Path(root),project,{'id':target['id']},record_lookup=lambda ident:indexed)
        if not path.is_file():raise ValueError('Selected artifact is unavailable.')
        basis=project_data._file_record(Path(root),path)['sha256'];title=Path(rel).name
        from laplace.projects import material_intake
        controls={'id':target['id'],'expected_sha256':basis,**selection}
        if not any(k in selection for k in ('page','page_count','pointer')):controls.update(offset=offset,limit=limit)
        read=material_intake.artifact_handle(project,controls)
        read['native']={'operation':'read_artifact','payload':controls}
        original=(material_intake.artifact_handle(project,{'id':target['id'],'expected_sha256':basis},'original') if indexed.get('original_metadata') else artifacts.artifact_human_read(project,rel,scope_name,basis,target['id']))
        # Original bytes may be binary. Metadata reads never decode them.
        return {'basis':basis,'title':title,'path':path,'read':read,'original_read':original,'artifact':indexed,'kind':kind,'selection':selection}
    if kind=='repository-file':
        if reference['owner']!='domain.projects' or set(target)!={'project','repository','path'}:raise ValueError('Select one configured repository coordinate.')
        info=writing_sources.reference_identity(Path(root),{k:target[k] for k in ('repository','path')})
        basis='sha256:'+info['revision'].removeprefix('sha256:')
        from laplace.projects import library
        values={'view':'preview','target':{'owner':'repository','repository':target['repository'],'path':target['path']},'expected_sha256':basis,**selection}
        return {'basis':basis,'title':Path(target['path']).name,'read':library.material_read_handle(project,values),
            'kind':kind,'selection':selection}
    if kind!='source-file' or reference['owner']!='domain.projects' or set(target)!={'project','path','scope'}:raise ValueError('Selected file reference is unsupported.')
    path,relative,pin=project_data.selected_file(Path(root),project,target['path'],target['scope'])
    basis=pin['sha256'];read=handle({'facet':'object','reference':reference,'section':'body','offset':offset,'limit':limit,'as_of':basis})
    return {'basis':basis,'title':Path(target['path']).name,'path':path,'relative':relative,'read':read,'kind':kind,'selection':selection}


def _observe_value(root,scope,reference,*,read_context=None):
    reference=_ref(reference);kind=reference['kind'];project=_project(reference)
    if reference['owner']=='domain.research':return _scientific(root,scope,reference)
    if kind in {'artifact','source-file','repository-file'}:
        value=_source(root,scope,reference);facets=_empty();facets['purpose']=_state({'title':value['title'],'summary':'Selected owner-retained source bytes.'})
        facets['standing']=_state({'label':'CURRENT_AT_READ','qualification':'Exact raw-byte identity observed; acceptance is separate.','raw_source_sha256':value['basis']})
        facets['inputs_outputs']=_state(items=[{'reference':reference,'basis':value['basis'],'read':value['read']}]);facets['actions']=_state(items=[])
        if kind=='artifact' and (value['artifact'].get('reader_metadata') or {}).get('schema_version')=='laplace.research-handover/1':
            from laplace.projects import project_handover as H
            H._retained_manifest(root,project,reference['identity']['id'])
            facets['actions']=_state(items=[{'id':'inspect-handover','title':'Inspect selected handover','permitted':True,'read':handle({'facet':'handover','reference':reference})}])
        return {**value,'reference':reference,'facets':facets}
    if kind=='workflow-definition':
        from laplace.pipeline import workflow_definitions as D
        if reference['owner']!=D.OWNER:raise ValueError('Workflow definition owner mismatch.')
        value=D.read(root,scope,{'reference':reference});facets=_empty()
        facets['purpose']=_state({'title':value['definition']['title'],'summary':value['definition'].get('description') or ''})
        facets['standing']=_state({'label':value['currentness'],'qualification':'Saved definition; run preparation and actual admission are separate.'})
        facets['settings']=_state(value['effective_settings']);facets['actions']=_state(items=[{'id':'open-definition','title':'Open workflow editor','permitted':True,'read':value['read'],
            'adapter':{'kind':'workflow-definition-editor','reference':value['reference']}}])
        facets['history']=_state(items=value['history']);facets['inputs_outputs']=_state(items=[{'read':value['app_runs_read']}])
        return {'reference':reference,'basis':value['version'],'title':value['definition']['title'],'facets':facets,
            'value':{'reference':value['reference'],'definition':value['definition'],'effective_settings':value['effective_settings']},'project':value['scope'].get('namespace')}
    if kind=='section':
        from laplace.manuscript import project_structure
        if reference['owner']!='domain.manuscript' or set(reference['identity'])!={'project','id'}:raise ValueError('Select one canonical section.')
        _scope(scope,project);value=project_structure.read(project,{'view':'detail','section_ids':[reference['identity']['id']],'projection':'display'},root,http=True)
        rows=value.get('sections') or []
        if not rows:raise ValueError('Selected section is unavailable.')
        row=rows[0];facets=_empty();facets['purpose']=_state({'title':row.get('title') or row['id'],'summary':row.get('job') or ''})
        facets['standing']=_state({'label':'OBSERVED_AT_READ','qualification':'Selected manuscript owner facts; application remains a separate guarded human effect.'})
        facets['inputs_outputs']=_state(items=row.get('source_reads') or []);facets['actions']=_state(items=row.get('actions') or [])
        return {'reference':reference,'basis':identity.canonical_digest(row),'title':row.get('title') or row['id'],'facets':facets,'value':row}
    if kind=='work':
        admitted=O.admit_reference(root,scope,reference,read_context=read_context);project=reference['identity']['namespace']
        from laplace.work import project_work
        detail=project_work.read(project,{'view':'detail','id':reference['identity']['id']},root,read_context=read_context);row=detail['task'];facets=_empty()
        facets['purpose']=_state({'title':row['title'],'summary':row['goal']})
        facets['standing']=_state({'label':row['standing']['group'],'qualification':row['standing'],
            **{key:copy.deepcopy(row[key]) for key in ('status','recorded_status','standing','lifecycle','activity','currentness','readiness','current_acceptance') if key in row}})
        known={item['id']:item for item in (detail.get('requires') or {}).get('items',[]) if item.get('id')}
        facets['relationships']=_state(items=[{'relation':'requires','reference':O.work_reference(project,x),
            'title':known.get(x,{}).get('title'),'title_state':'AVAILABLE' if known.get(x,{}).get('title') else 'NOT_LOADED',
            'read':handle({'facet':'object','reference':O.work_reference(project,x)})} for x in row.get('depends_on',[])])
        facets['inputs_outputs']=_state(items=row.get('evidence_reads') or []);facets['feedback']=_state(items=[{'deliveries':row.get('deliveries'),'feedback_routes':row.get('feedback_routes')}])
        facets['actions']=_state(items=[]);facets['history']=_state({'read':O.handle({'facet':'inspect','reference':reference})})
        from laplace.writing import workflow_progression
        run=workflow_progression.work_facet(root,project,row['id'],door={'origin':'human'} if scope.door in {'http','sdk'} else None,read_context=read_context)
        if run is not None:
            offered={'id':'research-run','title':'Plan and run','read':run['read']}
            facets['feedback']=_state({'title':'Plan and run','read':run['read']},items=[offered],state='UNAVAILABLE' if run.get('state')=='UNAVAILABLE' else 'AVAILABLE',reason=run.get('reason'))
            facets['actions']=_state(items=[{'id':'open-run','title':'Plan and run','permitted':True,'read':run['read'],'adapter':{'kind':'research-workflow-run','project':project,'work_id':row['id']}}])
        return {'reference':reference,'basis':row['work_revision'],'title':row['title'],'facets':facets,'value':row}
    if kind in {'subsystem','capability'}:
        value=O.admit_reference(root,scope,reference);facets=_empty();facets['purpose']=_state({'title':reference['identity']['id'],'summary':'Declared system owner; discover its current bound Work.'});facets['standing']=_state({'label':'DECLARED','qualification':'Structural owner declaration; execution/acceptance is not implied.'});facets['actions']=_state(items=[]);facets['history']=_state({'read':O.handle({'facet':'discover','subsystem':reference['identity']['id']})})
        return {'reference':reference,'basis':identity.canonical_digest(value),'title':reference['identity']['id'],'facets':facets}
    raise ValueError('Selected object owner/facet is unavailable here.')


def _observe(root,scope,reference,*,read_context=None):
    observed=_observe_value(root,scope,reference,read_context=read_context)
    if reference.get('version') is not None:
        key='definition_revision' if reference['kind']=='workflow-definition' else 'work_revision' if reference['kind']=='work' else 'basis'
        version=reference['version']
        if not isinstance(version,dict) or set(version)!={key} or not identity.revision_matches(version[key],observed['basis']):
            raise ValueError('CHANGED_INPUT: requested owner version is unavailable; no current version was substituted.')
    return observed


def resolve_object_context(root,project,value):
    if not isinstance(value,dict) or set(value)-{'reference','expected_basis','coordinate'} or not {'reference','expected_basis'}<=set(value):raise ValueError('Object context names reference, expected_basis and an optional owner local coordinate.')
    if 'coordinate' in value:
        from jsonschema import Draft202012Validator
        from laplace.work.object_geometry import COORDINATE,resolve_coordinate
        if not Draft202012Validator(COORDINATE).is_valid(value['coordinate']):raise ValueError('Invalid local object coordinate.')
        return resolve_coordinate(root,O.project_scope(project,'native'),value['reference'],value['coordinate'],expected_basis=value['expected_basis'])
    reference=_ref(value['reference'])
    if _project(reference) is not None:_scope(O.project_scope(project,'native'),_project(reference))
    observed=_observe(root,O.project_scope(project,'native'),reference)
    if not identity.revision_matches(value['expected_basis'],observed['basis']):raise ValueError('CHANGED_INPUT: selected object basis changed.')
    return {'reference':reference,'basis':observed['basis'],'summary':{'title':observed['title'],'owner':reference['owner'],'kind':reference['kind']},'read':handle({'facet':'object','reference':reference})}


def capture_inputs(root,project,value):
    if not isinstance(value,dict) or set(value)!={'entries'} or not isinstance(value['entries'],list) or not 1<=len(value['entries'])<=MAX_PAGE:
        raise ValueError('Select a bounded explicit evidence entries list.')
    scope=O.project_scope(project,'native');entries=[];consumed=[];seen=set()
    from laplace.projects import artifacts,writing_sources
    from laplace.research import literature
    for entry in value['entries']:
        if not isinstance(entry,dict) or set(entry)-{'reference','expected_basis','selection'} or not {'reference','expected_basis'}<=set(entry):raise ValueError('Each selected input carries reference and expected_basis.')
        reference=_ref(entry['reference'])
        if _project(reference) is not None:_scope(scope,_project(reference))
        key=identity.reference_key(reference)
        if key in seen:raise ValueError('Selected input reference is duplicated.')
        seen.add(key);observed=_observe(root,scope,reference)
        if not identity.revision_matches(entry['expected_basis'],observed['basis']):raise ValueError('CHANGED_INPUT: selected evidence basis changed.')
        selection=copy.deepcopy(entry.get('selection') or {})
        if set(selection)-{'offset','limit','page','page_count','pointer'}:raise ValueError('Selected read controls are unsupported.')
        kind=reference['kind'];target=reference['identity'];read=handle({'facet':'object','reference':reference});receipt={}
        if kind=='artifact':
            from laplace.projects import material_intake
            result=material_intake.read(Path(root),project,{'id':target['id'],'expected_sha256':observed['basis'],**selection})
            content=result.get('content',result.get('text'));read=result.get('page_read') or observed['read']
            whole=result.get('next_offset') is None and selection.get('offset',0)==0 and not result.get('truncated',False) and 'pointer' not in selection
            if result.get('media_type')=='application/pdf':whole=whole and result.get('pdf_page_start')==1 and result.get('pdf_page_end')==result.get('pdf_total_pages')
            receipt={'source_sha256':observed['basis'],'offset':result.get('offset'),'end':(result.get('next_offset') if result.get('next_offset') is not None else result.get('offset',0)+len(content) if 'pointer' in selection or result.get('media_type')=='application/pdf' else result.get('size_bytes')) if isinstance(content,str) else None,
                'units':result.get('units') or ('Unicode characters of selected JSON value' if 'pointer' in selection else 'UTF-8 bytes'),'whole_source':whole,
                **{k:result[k] for k in ('units','total_characters','pdf_page_start','pdf_page_end','pdf_total_pages','value_sha256','extraction_state') if k in result}}
        elif kind=='repository-file':
            result=writing_sources.execute(Path(root),{'action':'read','repository':target['repository'],'path':target['path'],'expected_sha256':observed['basis'],**selection});content=result.get('text',result.get('content'));read=result.get('page_read') or observed['read'];receipt={'source_sha256':observed['basis'],'offset':result.get('offset'),'next_offset':result.get('next_offset'),'whole_source':not result.get('truncated',False) and selection.get('offset',0)==0 and 'pointer' not in selection,**{k:result[k] for k in ('units','pdf_page_start','pdf_page_end','pdf_total_pages') if k in result}}
            if result.get('pdf_total_pages'):receipt['whole_source']=receipt['whole_source'] and result.get('pdf_page_start')==1 and result.get('pdf_page_end')==result['pdf_total_pages']
        elif kind=='source-file':
            if set(selection)-{'offset','limit'}:raise ValueError('This source owner supports character windows only; retain a page/pointer through its actual source owner.')
            file=_source(root,scope,reference,selection);raw=file['path'].read_bytes()
            if identity.bytes_digest(raw)!=observed['basis']:raise ValueError('CHANGED_INPUT: selected source changed during capture.')
            text=raw.decode('utf-8');offset=selection.get('offset',0);limit=selection.get('limit',4000)
            if offset>len(text):raise ValueError('Selected source offset is unavailable.')
            content=text[offset:offset+limit];read=file['read'];receipt={'source_sha256':observed['basis'],'offset':offset,'end':offset+len(content),'total_characters':len(text),'whole_source':offset==0 and len(content)==len(text)}
        elif kind=='reference':
            if set(selection)-{'offset','limit'}:raise ValueError('This reference text reader uses exact character windows, not PDF-page or JSON selectors.')
            info,_path=literature.source_info(project,target['key'],Path(root))
            result=literature.observe_read(project,target['key'],Path(root),**selection,persist=False,expected_source_revision=info.get('sha256') or '')
            read=result.get('page_read') or read
            if result.get('source_currentness')=='STALE':raise ValueError('CHANGED_INPUT: retained reference source changed.')
            content=result.get('text');receipt={'source_sha256':(result.get('attachment') or {}).get('sha256'),'offset':result.get('offset'),'next_offset':result.get('next_offset'),'whole_source':not result.get('truncated',False) and selection.get('offset',0)==0}
        else:
            if selection:raise ValueError('Scientific metadata selection has no source paging controls.')
            content=copy.deepcopy(observed.get('value'));receipt={'representation':'selected owner metadata','scientific_validity':'NOT_ASSERTED'}
        if content is None:raise ValueError('Selected input representation is unavailable.')
        if _observe(root,scope,reference)['basis']!=observed['basis']:raise ValueError('CHANGED_INPUT: selected owner changed during capture.')
        entries.append({'reference':reference,'basis':observed['basis'],'representation':'text' if isinstance(content,str) else 'metadata',
            'content':content,'read':read,'source_receipt':receipt,'coverage':{'complete_selected':True,'whole_source':receipt.get('whole_source',False)}})
        consumed.append({'reference':reference,'basis':observed['basis']})
    packet={'schema_version':'laplace.selected-evidence-packet/1','entries':entries,'consumed_bases':consumed,
        'qualification':'Exactly selected representations/windows; no hidden sources, scientific acceptance or model-fit assertion.'}
    packet['measurements']={'encoding':'core.identity.canonical_bytes UTF-8 JSON','utf8_bytes':0,'characters':0}
    for _ in range(8):
        wire=identity.canonical_bytes(packet);counts={'encoding':'core.identity.canonical_bytes UTF-8 JSON','utf8_bytes':len(wire),'characters':len(wire.decode('utf-8'))}
        if packet['measurements']==counts:break
        packet['measurements']=counts
    else:raise ValueError('Selected input size did not stabilize.')
    return packet



def input_from_read(root,scope,reference,read):
    """Project an actual pinned owner page handle, never infer offsets from text."""
    reference=_ref(reference);observed=_observe(root,scope,reference);project=_project(reference)
    if not isinstance(read,dict):raise ValueError('Select an actual owner-issued pinned page read.')
    native=read.get('native') or read
    operation=native.get('operation');payload=native.get('payload')
    if not isinstance(payload,dict):raise ValueError('The selected page read has no owner payload.')
    target=reference['identity'];kind=reference['kind'];controls=dict(payload)
    if operation=='material_references':
        source=controls.get('target')
        if isinstance(source,str):source=json.loads(source)
        if not isinstance(source,dict):raise ValueError('Selected Material target unavailable.')
        if kind=='repository-file':
            matches=source.get('owner')=='repository' and source.get('repository')==target['repository'] and source.get('path')==target['path']
        elif kind=='artifact':
            artifact=observed['artifact'];matches=source.get('owner') in {'artifact','writing-artifact'} and source.get('project',project)==project and source.get('path')==artifact.get('artifact_path') and source.get('scope','project')==artifact.get('scope','project')
        else:matches=False
        if not matches:raise ValueError('Selected page read targets a different qualified owner.')
    elif operation=='read_artifact':
        if kind!='artifact' or controls.get('id')!=target['id']:raise ValueError('Selected artifact page names another original.')
    elif operation=='repository':
        if kind!='repository-file' or controls.get('action')!='read' or any(controls.get(k)!=target[k] for k in ('repository','path')):raise ValueError('Selected repository page names another source.')
    elif operation=='reference_text':
        if kind!='reference' or controls.get('key')!=target['key'] or controls.get('source_index',0)!=0:raise ValueError('Selected reference page names another source.')
        from laplace.research import literature
        info,_path=literature.source_info(project,target['key'],Path(root))
        if not identity.revision_matches(controls.get('expected_source_revision'),info.get('sha256')):raise ValueError('CHANGED_INPUT: reference page is unpinned or stale.')
        controls={**controls,'expected_sha256':observed['basis']}
    elif operation=='project':
        request=(controls.get('request') or {})
        if kind!='source-file' or controls.get('view')!='discovery' or request.get('reference')!=reference:raise ValueError('Selected source page names another object.')
        controls={**request,'expected_sha256':request.get('as_of')}
    else:raise ValueError('Only an existing exact source page can be selected as evidence.')
    if controls.get('project',project)!=project or not identity.revision_matches(controls.get('expected_sha256'),observed['basis']):raise ValueError('CHANGED_INPUT: page is unpinned, stale or outside the selected project.')
    selected={k:controls[k] for k in ('offset','limit','page','page_count','pointer') if k in controls}
    for old,new in [('pdf_page','page'),('pdf_page_count','page_count')]:
        if old in controls:
            if new in selected and selected[new]!=controls[old]:raise ValueError('Ambiguous selected PDF page controls.')
            selected[new]=controls[old]
    return {'reference':reference,'expected_basis':observed['basis'],**({'selection':selected} if selected else {})}

def _mutation_result(root,scope,value):
    project=value['project'];original=value['original_request']
    from laplace.pipeline.workflow_definitions import _scope_id
    value['scope']=scope.public();value['scope_id']=_scope_id(root,scope)
    value['reconcile']=handle({'facet':'object-request','project_lens':project,'object_request':original})
    if original['operation'] in {'save-question','save-object'}:value['settle']={'http':{'method':'POST','url':'/work/object-change','payload':{'project':project,'operation':'settle-question','original_request':original}},
        'native':{'operation':'research_object_change','payload':{'operation':'settle-question','original_request':original}}}
    value['new_decision_read']=handle({'facet':'object','reference':original['reference']} if original.get('reference') else {'facet':'object','reference':ref('domain.research','concept',project=project,node=original['parent'])} if original.get('parent') else {'facet':'workspace','project_lens':project})
    if value.get('reference'):value['read']=handle({'facet':'object','reference':value['reference']})
    return value


def _consumed_action(project,reference,basis):
    wire={'project':project,'operation':'bind-consumed','reference':reference,'expected_basis':basis,'request_id':uuid.uuid4().hex}
    return {'id':'bind-consumed','title':'Record selected consumed inputs','permitted':True,
        'fields':[{'name':'inputs','label':'Inputs actually consumed by this object','type':'selected-inputs','required':True}],
        'http':{'method':'POST','url':'/work/object-change','payload':wire},
        'reconcile':{'http':{'method':'GET','url':'/work/discovery'},'request':{'facet':'object-request','project_lens':project},'field':'object_request'}}


def _question_actions(root,project,parent=None):
    from laplace.research import concepts
    plan=concepts.logical_plan(project,root=Path(root),limit=1)
    if not plan:return [{'id':'add-question','title':'Write a question','permitted':False,'reason':'The selected scope has no editable logical-plan owner.','fields':[]}]
    from laplace.manuscript import manuscript_source
    permitted=not manuscript_source.resolve(project,repo_root=root).get('read_only')
    rows=[]
    variants=[('question','Save question','Your question')] if parent is None else [('result','Save claim','Claim'),('technique','Save method','Method'),('support','Save result or evidence note','Result or evidence note')]
    for kind,title,label in variants:
        payload={'project':project,'operation':'save-question' if kind=='question' else 'save-object','node':kind+':'+uuid.uuid4().hex,
            'base_revision':plan['revision'],'request_id':uuid.uuid4().hex}
        if parent is not None:payload.update(object_kind=kind,parent=parent)
        rows.append({'id':'create-'+kind,'title':title,'permitted':permitted,'reason':None if permitted else 'The selected source is read-only.',
            'fields':[{'name':'meaning','label':label,'type':'textarea','required':True},{'name':'inputs','label':'Selected evidence and methods','type':'selected-inputs','required':False}],
            'http':{'method':'POST','url':'/work/object-change','payload':payload},'native':{'operation':'research_object_change','payload':{k:v for k,v in payload.items() if k!='project'}},
            'reconcile':{'http':{'method':'GET','url':'/work/discovery'},'request':{'facet':'object-request','project_lens':project},'field':'object_request'},
            'settle':{'http':{'method':'POST','url':'/work/object-change'},'payload':{'project':project,'operation':'settle-question'},'field':'original_request'}})
    return rows


def _handover_action(project,scope):
    from laplace.projects import project_handover as H
    return {'id':'prepare-handover','title':'Prepare selected portable handover','permitted':scope.kind=='owned-workspace',
        'reason':'Choose explicitly permitted bytes and omission standing; host qualification and credentials never travel.',
        'fields':[{'name':'entries','label':'Selected objects and sharing decisions','type':'handover-selection','required':True},
            {'name':'max_files','label':'Maximum copied files','type':'number','value':1000,'required':True},
            {'name':'max_rows','label':'Maximum retained records','type':'number','value':10000,'required':True},
            {'name':'max_bytes','label':'Maximum output bytes','type':'number','value':134217728,'required':True}],
        **H.object_handle(project,{'action':'prepare','request_id':uuid.uuid4().hex}),
        'reconcile':H.object_handle(project,{'action':'request'}),'request_field':'request_id'}


def _manuscript_choices(root,scope,project):
    """Actual selected manuscript membership, not a caller path or file scan."""
    _scope(scope,project)
    from laplace.manuscript import manuscript_source as M
    source=M.resolve(project,repo_root=root,include_candidates=False)
    if source.get('status')!='resolved' or source.get('read_only') or source.get('foreign'):
        return {'state':'UNAVAILABLE','project':project,'choices':[],
            'reason':'Choose an existing editable registered manuscript source; the workbench does not create or readdress it.'}
    tree=M.traversal(Path(root)/source['root'],root)
    observation=M.observation(project,root,source=source,source_tree=tree);choices=[]
    for file,pin in observation['file_revisions'].items():
        access=M.source_access(project,Path(root)/file,root,source=source,source_tree=tree)
        if access['read_only']:continue
        selected_path=(Path(root)/file).relative_to(Path(root)/source['manuscript_dir']).as_posix()
        reference=ref('domain.projects','source-file',project=project,path=selected_path,scope='manuscript')
        issued=handle({'facet':'object','reference':reference,'section':'body','offset':0,'limit':4000,'as_of':'sha256:'+pin.removeprefix('sha256:')})
        choices.append({'id':file,'title':Path(file).name,'selection':{'files':[file],'source_observation':{'selection_identity':observation['selection_identity'],'file_revisions':{file:pin}}},
            'basis':{'selection_identity':observation['selection_identity'],'source_digest':'sha256:'+pin.removeprefix('sha256:')},
            'read':issued,'read_title':'Inspect selected source file'})
    if choices:
        document_selection={'files':[row['id'] for row in choices],'source_observation':{'selection_identity':observation['selection_identity'],
            'file_revisions':{row['id']:observation['file_revisions'][row['id']] for row in choices}}}
        choices.insert(0,{'id':'selected-manuscript','title':'Current manuscript source','selection':document_selection,
            'basis':{'selection_identity':observation['selection_identity'],'source_revision':observation['source_revision']},
            'read':choices[0]['read'],'read_title':'Inspect first selected source file'})
    return {'state':'AVAILABLE' if choices else 'UNAVAILABLE','project':project,'basis':observation['revision'],
        'choices':choices,'meaning':'Explicit current source choice. Existing preparation/admission revalidates the actual manuscript and its source guards; this read grants no application authority.'}


def _workspace(root,scope,payload):
    from laplace import system
    from laplace.work import project_work
    from laplace.research import concepts,research_context,research_records
    from laplace.projects import artifacts
    projects=_projects(root,scope);lens=payload.get('project_lens');family=payload.get('family','all');items=[];unknown=[]
    if lens is not None:_scope(scope,lens);projects=[x for x in projects if x['name']==lens]
    for project_row in projects:
        project=project_row['name']
        if family in {'all','work'}:
            for row in project_work._tasks(project,root).values():
                reference=O.work_reference(project,row['id']);items.append({'reference':reference,'title':row['title'],'kind':'work','read':handle({'facet':'object','reference':reference})})
        if family in {'all','concept'}:
            catalogue=concepts.catalog(project,limit=MAX_PAGE,root=Path(root))
            if catalogue:
                for row in catalogue['items']:
                    reference=ref('domain.research','concept',project=project,node=row['id']);items.append({'reference':reference,'title':row.get('title') or row['label'],'kind':row['kind'],'read':handle({'facet':'object','reference':reference})})
                if catalogue['next_offset'] is not None:unknown.append({'project':project,'family':'concept','read':_read(project,'logical_plan',{'view':'catalog','offset':catalogue['next_offset'],'limit':MAX_PAGE},'/concepts/catalog')})
        if family in {'all','research-record'}:
            _item,home=research_context.project(project,Path(root))
            if home:
                rows,error=research_records._records(home)
                if error:unknown.append({'project':project,'family':'research-record','state':'UNAVAILABLE'})
                else:
                    for row in rows:
                        reference=ref('domain.research','research-record',project=project,id=row['id']);items.append({'reference':reference,'title':row.get('title') or row['id'],'kind':row['kind'],'basis':row.get('revision'),'read':handle({'facet':'object','reference':reference})})
        if family in {'all','artifact'}:
            catalogue=artifacts.catalogue(Path(root),project,{'offset':0,'limit':50})
            for row in catalogue.get('materials',[]):
                if not row.get('id'):continue
                reference=ref('domain.projects','artifact',project=project,id=row['id'])
                items.append({'reference':reference,'title':row.get('display_name') or Path(row.get('artifact_path') or row.get('path') or row['id']).name,'kind':'artifact','read':handle({'facet':'object','reference':reference})})
            if catalogue['pagination'].get('next_offset') is not None:unknown.append({'project':project,'family':'artifact','read':_read(project,'materials',{'offset':catalogue['pagination']['next_offset'],'limit':50},'/work/materials')})
        if family in {'all','reference'}:
            from laplace.research import references_surface as RS
            home=RS._manuscript(project,Path(root))
            if home:
                associations=RS._load_associations(home,require_supported=True)
                for key in dict.fromkeys(r.get('key') for r in associations if r.get('key')):
                    reference=ref('domain.research','reference',project=project,key=key)
                    item=next(r for r in associations if r.get('key')==key)
                    items.append({'reference':reference,'title':(item.get('metadata') or {}).get('title') or key,'kind':'reference','read':handle({'facet':'object','reference':reference})})
    if family in {'all','workflow-definition'}:
        from laplace.pipeline import workflow_definitions as D
        caller=O.project_scope(lens,scope.door) if lens else scope
        definitions=D.read(root,caller,{'offset':0,'limit':50})
        for row in definitions['definitions']:
            reference=D.reference(row['definition_id'],row['version'])
            items.append({'reference':reference,'title':row['title'],'kind':'workflow-definition','basis':row['version'],'read':handle({'facet':'object','reference':reference})})
        if definitions.get('next'):unknown.append({'family':'workflow-definition','read':definitions['next']})
    items.sort(key=lambda x:identity.reference_key(x['reference']));basis=identity.canonical_digest({'items':items,'lens':lens,'scope':{'kind':scope.kind,'namespace':scope.namespace},'family':family})
    start=payload.get('offset',0);limit=payload.get('limit',PAGE);facets=_empty();facets['purpose']=_state({'title':'Research workbench','summary':'Discover existing scientific objects, Work and their owners. Projects are optional lenses.'});facets['standing']=_state({'label':'Workspace','qualification':'Owner-observed catalogue, not a global scientific acceptance.'});facets['relationships']=_state(items=system.entry()['subsystems']);facets['actions']=_state(items=_question_actions(root,lens) if lens else [{'id':'add-question','title':'Write a question','permitted':False,'reason':'Choose an existing editable logical-plan context; workspace navigation creates no manuscript.','fields':[]}])
    result=_envelope(root,scope,payload,None,basis,facets,items[start:start+limit],{'state':'PARTIAL' if unknown else 'PERMITTED_NAMESPACES','known':len(items),'omitted':max(0,len(items)-start-limit),'unavailable':unknown,'qualification':'Existing permitted namespace owners only; no unrecorded relationships inferred.'})
    from laplace.pipeline import workflow_definitions as D
    workflow_caller=O.project_scope(lens,scope.door) if lens else scope
    result['workflow_library']={'id':'workflow-library','title':'Workflows and starter definitions','permitted':True,
        'read':D.scoped_handle(workflow_caller),'adapter':{'kind':'workflow-definition-editor'}}
    if lens:
        research=_research_entry(root,scope,lens)
        if research:result['facets']['actions']['items'].append(research)
        result['handover_prepare']=_handover_action(lens,scope)
        result['manuscript_choices_read']=handle({'facet':'manuscript-selection','project_lens':lens})
    if start+limit<len(items):result['pagination']['next_read']=handle({**payload,'offset':start+limit,'as_of':basis})
    return result


def _dependents(root,scope,payload):
    from laplace.research import object_context as R
    reference=_ref(payload['reference']);project=_project(reference);_scope(scope,project)
    rows=[];related=[]
    from laplace.writing import workflow_progression
    workflow_relations=workflow_progression.consumed_relations(root,project)
    for row in [*R.relations(root,project),*workflow_relations['items']]:
        if identity.reference_key(row['reference'])!=identity.reference_key(reference):continue
        target=rows if row.get('qualification')=='PINNED' else related
        dependent=_observe(root,scope,row['dependent'])
        actions=[]
        if row.get('qualification')=='PINNED' and row['dependent'].get('owner')=='domain.research' and row['dependent'].get('kind')=='concept':
            wire={'project':project,'operation':'mark-reconsideration','reference':row['dependent'],'expected_basis':dependent['basis'],
                'request_id':uuid.uuid4().hex,'concern_id':uuid.uuid4().hex,
                'changed':{'reference':row['reference'],'basis':row['basis']},'change_kind':payload.get('change_kind','version')}
            actions.append({'id':'mark-reconsideration','title':'Mark for reconsideration','permitted':scope.door in {'http','sdk'},
                'fields':[{'name':'summary','label':'Why this needs reconsideration','type':'textarea','required':True}],
                'http':{'method':'POST','url':'/work/object-change','payload':wire},
                'reconcile':{'http':{'method':'GET','url':'/work/discovery'},'request':{'facet':'object-request','project_lens':project},'field':'object_request'}})
        target.append({**row,'title':dependent['title'],'current':dependent['basis'],'actions':actions,
            'read':handle({'facet':'object','reference':row['dependent']}),
            'clearance':{'owner':row['dependent']['owner'],'kind':'judgement' if payload.get('change_kind')=='assumption' else 'revalidation',
                'permitted':False,'reason':'Use the actual review/author or revalidation owner admission; this pure read grants no disposition.',
                'read':handle({'facet':'object','reference':row['dependent']})}})
    basis=identity.canonical_digest({'reference':reference,'rows':rows,'related':related,'changed_basis':payload.get('changed_basis'),'change_kind':payload.get('change_kind','version')});start=payload.get('offset',0);limit=payload.get('limit',PAGE)
    facets=_empty();facets['purpose']=_state({'title':'Recorded consumed-basis dependents','summary':'Only explicitly pinned dependencies can be reconsidered. This read creates no flags.'});facets['relationships']=_state(items=related)
    out=_envelope(root,scope,payload,reference,basis,facets,rows[start:start+limit],{'state':'RECORDED_ONLY','known':len(rows),'related_unpinned':len(related),'admitted_workflow_coverage':workflow_relations['coverage'],'omitted':max(0,len(rows)-start-limit),'qualification':'No recorded basis is not proof of independence or absence; proximity and containment are not causality.'})
    out['controls']['change_kind']={'value':payload.get('change_kind','version'),'choices':[{'id':kind,'title':'Changed version' if kind=='version' else 'Changed scientific assumption','read':handle({**{k:v for k,v in payload.items() if k not in {'as_of','offset'}},'change_kind':kind})} for kind in ('version','assumption')]}
    if start+limit<len(rows):out['pagination']['next_read']=handle({**payload,'offset':start+limit,'as_of':basis})
    return out


def request(root,scope,payload):
    root=Path(root).resolve();facet=payload.get('facet','workspace');read_context={}
    if payload.get('project_lens') is not None:_scope(scope,payload['project_lens'])
    if facet=='workspace':return _workspace(root,scope,payload)
    if facet=='manuscript-selection':
        value=_manuscript_choices(root,scope,payload.get('project_lens'))
        from laplace.pipeline.workflow_definitions import _scope_id
        return {'schema_version':'laplace.manuscript-selection-choices/1','view':'manuscript-selection','scope':scope.public(),'scope_id':_scope_id(root,scope),
            **value,'read':handle(payload)}
    if facet=='object-request':
        project=payload.get('project_lens');_scope(scope,project)
        from laplace.research import object_context
        original=payload['object_request']
        if original.get('operation') in {'save-question','save-object'}:value=object_context.question_request(root,project,original)
        else:value=object_context.change(root,project,{k:v for k,v in original.items() if k!='project'},admit=lambda *_:None,inspect_only=True)
        return _mutation_result(root,scope,{**value,'project':project,'operation':original['operation'],'original_request':original,'request_id':original['request_id'],'intent_sha256':identity.canonical_digest(original),'terminal':value['state'] in {'RECORDED','NOT_ADMITTED'}})
    if facet=='input':
        descriptor=input_from_read(root,scope,payload['reference'],payload['read'])
        from laplace.pipeline.workflow_definitions import _scope_id
        return {'schema_version':'laplace.selected-input-descriptor/1','view':'input','scope':scope.public(),'scope_id':_scope_id(root,scope),
            'input_descriptor':descriptor,'read':handle({'facet':'object','reference':payload['reference']})}
    if facet=='dependents':return _dependents(root,scope,payload)
    if facet=='handover':
        from laplace.projects import project_handover
        return project_handover.object_request(root,scope,{'action':'read','reference':payload['reference']},door={'origin':'read'})
    reference=_ref(payload['reference'])
    if reference['kind']=='workflow-definition' and payload.get('project_lens'):
        from laplace.pipeline import workflow_definitions as D
        try:observed=_observe(root,O.project_scope(payload['project_lens'],scope.door),reference,read_context=read_context)
        except D.Refused as error:
            if error.details.get('code')!='NOT_IN_SCOPE' or scope.kind!='owned-workspace':raise
            observed=_observe(root,scope,reference,read_context=read_context)
    else:observed=_observe(root,scope,reference,read_context=read_context)
    facets=copy.deepcopy(observed['facets']);items=[]
    input_descriptor={'reference':reference,'expected_basis':observed['basis']}
    if payload.get('section')=='body':
        source=_source(root,scope,reference,{k:payload[k] for k in ('offset','limit') if k in payload})
        raw=source['path'].read_bytes()
        if identity.bytes_digest(raw)!=observed['basis']:raise ValueError('CHANGED_INPUT: selected file bytes changed.')
        text=raw.decode('utf-8');start=payload.get('offset',0);limit=payload.get('limit',4000)
        items=[{'reference':reference,'content':text[start:start+limit],'offset':start,'end':min(len(text),start+limit),'total_characters':len(text),'basis':observed['basis']}]
    out=_envelope(root,scope,payload,reference,observed['basis'],facets,items)
    if payload.get('section')=='body':
        input_descriptor['selection']={'offset':start,'limit':limit}
        if start+limit<len(text):out['pagination']['next_read']=handle({**payload,'offset':start+limit,'as_of':observed['basis']})
        out['coverage'].update(complete_selected=True,whole_source=start==0 and len(items[0]['content'])==len(text))
    conversation_project=_project(reference) or observed.get('project')
    if conversation_project and scope.admits(conversation_project):
        from laplace.projects import library
        capability=library.project_capabilities(conversation_project,root)
        available=bool((capability.get('capabilities') or {}).get('turns'))
        out['conversation']={'project':conversation_project,'available':available,'reason':None if available else 'The selected owner has no conversation capability.',
            'object_context':{'reference':reference,'expected_basis':observed['basis']},
            'session_list':{'http':{'method':'GET','url':'/authoring/state?'+urlencode({'project':conversation_project,'view':'sessions'})}}}
    else:out['conversation']={'project':None,'available':False,'reason':'This system-level object has no owner-admitted conversation namespace. Select an explicit owned Work/context rather than inventing a project.'}
    out['handover_entry']={'class':'included','reference':reference,'expected_basis':observed['basis'],'permit_export':False}
    if conversation_project and scope.admits(conversation_project):out['handover_prepare']=_handover_action(conversation_project,scope)
    if conversation_project and scope.admits(conversation_project):
        out['dependents_read']=handle({'facet':'dependents','reference':reference,'changed_basis':observed['basis']})
        out['manuscript_choices_read']=handle({'facet':'manuscript-selection','project_lens':conversation_project})
    out['input_descriptor']=input_descriptor
    if reference['kind'] in {'artifact','source-file','repository-file','reference'}:
        out['input_from_read']={'http':{'method':'GET','url':'/work/discovery'},'request':{'facet':'input','reference':reference},'field':'read','says':'Supply the actual owner-issued pinned page handle, not offsets inferred from rendered text.'}
    return out



def change_contract():
    return {'type':'object','additionalProperties':False,'required':['operation'], 'properties':{
        'project':{'type':'string'},'operation':{'enum':['save-question','save-object','settle-question','bind-consumed','mark-reconsideration','clear-reconsideration']},
        'reference':{'type':'object'},'expected_basis':{'type':'string'},'expected_concern_basis':{'type':'string'},
        'request_id':{'type':'string'},'node':{'type':'string'},'meaning':{'type':'string'},'base_revision':{'type':'string'},
        'object_kind':{'enum':['question','result','technique','support']},'parent':{'type':'string'},'inputs':{'type':'array','maxItems':80,'items':{'type':'object'}},
        'original_request':{'type':'object'},'consumed_bases':{'type':'array','items':{'type':'object'}},
        'concern_id':{'type':'string'},'changed':{'type':'object'},'change_kind':{'enum':['version','assumption']},
        'summary':{'type':'string'},'disposition':{'enum':['ACCEPT','REVISE','WITHDRAW','UNCHANGED']},'evidence':{'type':'array','items':{'type':'object'}}}}


def change(root,scope,payload,*,door):
    from jsonschema import Draft202012Validator
    from laplace.research import object_context
    issue=next(Draft202012Validator(change_contract()).iter_errors(payload),None)
    if issue:raise ValueError('Object mutation does not match its closed owner contract.')
    project=payload.get('project') or _project(payload.get('reference') or {}) or (payload.get('original_request') or {}).get('project')
    _scope(scope,project);operation=payload['operation']
    def admit(request,current):
        if door.get('origin') in {'human','sdk'}:return {'actor':door.get('origin'),'authority':'explicit local owner operation','kind':'author'}
        if door.get('origin')=='native' and door.get('mode')=='work':
            from laplace.writing.turn_admission import native_write_admission
            admitted=native_write_admission(root,project,door.get('mode'),door.get('turn_id'))
            if not admitted.get('permitted'):raise ValueError('An actual current authorised native turn is required.')
            if request.get('operation')=='clear-reconsideration':raise ValueError('Scientific disposition needs the responsible bound review or explicit human author owner.')
            return {'actor':door.get('turn_id'),'authority':'actual scoped native author effect','kind':'author'}
        raise ValueError('This caller has no admitted object mutation authority.')
    if operation in {'save-question','save-object','settle-question'}:
        original=payload['original_request'] if operation=='settle-question' else payload
        prior=object_context.question_request(root,project,original)
        if prior['state']!='NONE':return _mutation_result(root,scope,prior)
        admit(original,{})
        if operation!='settle-question' and original.get('inputs'):capture_inputs(root,project,{'entries':original['inputs']})
        return _mutation_result(root,scope,object_context.question_request(root,project,original,action='settle' if operation=='settle-question' else 'save',admit=admit))
    original={k:v for k,v in payload.items() if k!='project'}
    prior=object_context.change(root,project,original,admit=admit,inspect_only=True)
    if prior['state']!='RECORDED':
        admit(payload,{})
        if payload.get('inputs'):capture_inputs(root,project,{'entries':payload['inputs']})
    result=object_context.change(root,project,original,admit=admit)
    return _mutation_result(root,scope,{**result,'project':project,'operation':operation,'original_request':payload,'request_id':payload['request_id'],'intent_sha256':identity.canonical_digest(payload),'terminal':True})
