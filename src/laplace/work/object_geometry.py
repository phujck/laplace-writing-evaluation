"""Bounded relational observations composed by the existing Work discovery owner.

One local hop, detached owner lanes, explicit expansion and actual recorded
history. This is a pure projection: no graph store, body fanout or permission.
"""
from __future__ import annotations
import copy
from pathlib import Path
from laplace.core import identity
from laplace.work import owner_discovery as O, project_work as W

SCHEMA='laplace.object-neighbourhood/1'
RELATIONS=('contains','requires','consumed','related-unpinned','configured-route','admitted-route','owner-binding')
COORDINATE={'type':'object','additionalProperties':False,'required':['kind','id'],'properties':{
    'kind':{'enum':['workflow-step','work-phase','delivery-event']},'id':{'type':'string','minLength':1,'maxLength':160}}}


def handle(payload):
    from laplace.work.object_facets import handle as issued
    return issued(payload)


def navigation(reference=None,*,project_lens=None,coordinate=None):
    values={**({'reference':reference} if reference else {}),**({'project_lens':project_lens} if project_lens else {}),
        **({'coordinate':coordinate} if coordinate else {})}
    return {key:handle({'facet':facet,**values}) for key,facet in
        (('neighbourhood_read','neighbourhood'),('scope_read','semantic-scope'),('timeline_read','timeline')) if reference or facet!='timeline'}


def _key(reference,coordinate=None):
    return identity.canonical_digest({'object':identity.reference_key(reference),'version':reference.get('version'),'coordinate':coordinate})


def _ref_project(reference):
    value=reference['identity'];return value.get('project',value.get('namespace'))


def _admit_metadata(root,scope,reference,context):
    """Admit cross-owner coordinates before names, hashes or counts enter wire data."""
    if identity.reference_problems(reference):raise ValueError('Unavailable coordinate.')
    project=_ref_project(reference)
    if project is not None and not scope.admits(project):raise ValueError('Unavailable coordinate.')
    kind=reference['kind'];owner=reference['owner'];target=reference['identity']
    if kind in {'subsystem','capability','work'}:
        return O.admit_reference(root,scope,reference,read_context=context)['reference']
    if owner=='domain.research':
        from laplace.research.object_context import check_reference
        admitted=check_reference(reference)
        metadata=context.setdefault(('geometry-scientific-coordinates',project),{})
        key=identity.reference_key(reference)
        if key not in metadata:
            from laplace.research import object_context as R
            observation=R.geometry_observation(root,project,reference)
            metadata.update(observation['metadata'])
        if key not in metadata:raise ValueError('Unavailable scientific coordinate.')
        if reference.get('version') and reference['version']!={'basis':metadata[key]['basis']}:raise ValueError('Selected scientific version unavailable.')
        return admitted
    if owner=='domain.projects' and kind=='source-file' and set(target)=={'project','path','scope'}:
        from laplace.projects.project_data import selected_file_coordinate
        selected_file_coordinate(root,target['project'],target['path'],target['scope']);return copy.deepcopy(reference)
    if owner=='domain.projects' and kind=='artifact' and set(target)=={'project','id'}:
        from laplace.projects import artifacts
        row=artifacts._artifact_record(root,project,target['id'])
        path,_,_,_=artifacts._artifact_target(root,project,{'id':target['id']},record_lookup=lambda ident:row)
        from laplace.projects import project_data
        relative=path.relative_to(Path(root))
        if project_data._excluded(relative) or {'.laplace-state','.laplace-cache','.auth','.credentials'} & set(relative.parts):raise ValueError('Unavailable artifact coordinate.')
        return copy.deepcopy(reference)
    if kind=='workflow-definition':
        from laplace.pipeline import workflow_definitions as D
        D._select(D._rows(root),scope,{'reference':reference});return copy.deepcopy(reference)
    raise ValueError('No metadata admission for selected family.')


class Frame:
    def __init__(self,root,scope,payload,context):
        self.root,self.scope,self.payload,self.context=root,scope,payload,context
        self.nodes={};self.edges=[];self.events=[];self.lanes=[];self.hidden=False;self.unavailable=[]
        self.allowed=set(payload.get('relations') or RELATIONS)
        self.focus=None;self.coordinate=payload.get('coordinate');self.parent_read=handle({'facet':'neighbourhood'})
        self.semantic_kind='system';self.title='Research workspace';self.project_context=None

    def add(self,reference,title=None,*,basis=None,standing=None,coordinate=None,detail=None,adapter=None,admit=True,kind=None):
        if self.focus and identity.reference_key(reference)==identity.reference_key(self.focus) and self.focus.get('version') and not reference.get('version'):reference=copy.deepcopy(self.focus)
        if admit:reference=_admit_metadata(self.root,self.scope,reference,self.context)
        key=_key(reference,coordinate)
        if key in self.nodes:return key
        if title is None and reference['kind']=='source-file':title=Path(reference['identity']['path']).name
        if title is None and reference['kind']=='artifact':
            from laplace.projects import artifacts
            record=artifacts._artifact_record(self.root,reference['identity']['project'],reference['identity']['id'])
            title=(record.get('original_metadata') or {}).get('display_name') or Path(record.get('artifact_path') or record.get('path') or 'Retained source').name
        nav=navigation(reference,project_lens=self.payload.get('project_lens'),coordinate=coordinate)
        detail=detail or handle({'facet':'object','reference':reference,**({'project_lens':self.payload['project_lens']} if self.payload.get('project_lens') else {})})
        title=title or reference['kind'].replace('-',' ').title()
        complete=len(title)<=400
        if not complete:title=title[:399]+'…'
        self.nodes[key]={'key':key,'reference':copy.deepcopy(reference),'coordinate':copy.deepcopy(coordinate),
            'title':title,'title_complete':complete,'kind':kind or reference['kind'],'owner':reference['owner'],
            'basis':basis,'standing':standing or {'state':'NOT_INSPECTED','qualification':'Metadata only; currentness and acceptance require the owner read.'},
            'detail_read':detail,'expand_read':nav['neighbourhood_read'],'scope_read':nav['scope_read'],'timeline_read':nav.get('timeline_read'),
            **({'adapter':adapter} if adapter else {})}
        project=_ref_project(reference) or self.project_context
        conversation={'available':False,'project':None,'reason':'This metadata observation has no admitted conversation context; read the object or select an owned context explicitly.'}
        if basis and project and self.scope.admits(project):
            from laplace.projects import library
            cache=('geometry-conversation-capability',project)
            if cache not in self.context:self.context[cache]=bool(library.project_capabilities(project,self.root)['capabilities'].get('turns'))
            if self.context[cache]:
                from urllib.parse import urlencode
                conversation={'available':True,'project':project,'reason':None,
                    'object_context':{'reference':copy.deepcopy(reference),'expected_basis':basis,**({'coordinate':copy.deepcopy(coordinate)} if coordinate else {})},
                    'session_list':{'http':{'method':'GET','url':'/authoring/state?'+urlencode({'project':project,'view':'sessions'})}}}
        self.nodes[key]['conversation']=conversation
        return key

    def edge(self,source,target,kind,*,owner,basis=None,label=None,consumed_basis=None,qualification='RECORDED',read=None):
        if kind not in self.allowed:return
        value={'source':source,'target':target,'kind':kind,'owner':owner,'basis':basis,'qualification':qualification}
        if label:value['label']=label
        if consumed_basis is not None:value['consumed_basis']=consumed_basis
        if read:value['read']=read
        value['key']=identity.canonical_digest(value)
        if not any(row['key']==value['key'] for row in self.edges):self.edges.append(value)

    def lane(self,name,owner,basis,*,timestamp=None,coverage=None,read=None):
        self.lanes.append({'lane':name,'owner':owner,'basis':basis,'cut':basis,
            'timestamp':{'state':'RECORDED','value':timestamp} if timestamp else {'state':'UNAVAILABLE'},
            'coverage':coverage or {'state':'SELECTED_OWNER_METADATA'},'read':read})

    def event(self,parent,kind,title,*,basis,timestamp=None,coordinate=None,read=None,lane=None):
        self.events.append({'key':identity.canonical_digest({'parent':parent,'kind':kind,'basis':basis,'ordinal':len(self.events)}),
            'parent':copy.deepcopy(parent),'coordinate':coordinate,'owner':parent['owner'],'kind':kind,'title':title,
            'timestamp':{'state':'RECORDED','value':timestamp} if timestamp else {'state':'UNAVAILABLE'},'basis':basis,'read':read,
            'lane':lane or parent['owner']})


def _declared(frame,reference):
    from laplace import system
    description=O._description();entry=system.entry(description)
    by_id={row['id']:row for row in description['subsystems']}
    caps={row['id']:row for row in description.get('capabilities',[])}
    if reference is None:
        frame.lane('declarations','core.identity',identity.canonical_digest(entry),coverage={'state':'DECLARED_SYSTEM'})
        for row in entry['subsystems']:
            frame.add(row['reference'],row['reference']['identity']['id'],basis=identity.canonical_digest(row),standing={'state':'DECLARED'})
        return
    admitted=O.admit_reference(frame.root,frame.scope,reference,description=description,read_context=frame.context)['reference']
    selected=by_id[admitted['identity']['id']] if admitted['kind']=='subsystem' else caps[admitted['identity']['id']]
    frame.focus=admitted;frame.title=selected.get('title') or selected['id'];frame.semantic_kind=admitted['kind']
    own=frame.add(admitted,frame.title,basis=identity.canonical_digest(selected),standing={'state':'DECLARED'})
    frame.lane('declarations','core.identity',identity.canonical_digest(selected))
    if admitted['kind']=='subsystem':
        for cap in caps.values():
            if cap['owner']==selected['id']:
                ref=system.capability_reference(cap);key=frame.add(ref,cap.get('title') or cap['id'],basis=identity.canonical_digest(cap),standing={'state':'DECLARED'})
                frame.edge(own,key,'contains',owner='core.identity',basis=identity.canonical_digest(selected))
        for used in selected.get('uses') or []:
            if used not in by_id:continue
            ref=system.subsystem_reference(by_id[used]);key=frame.add(ref,used,standing={'state':'DECLARED'})
            frame.edge(own,key,'requires',owner='core.identity',basis=identity.canonical_digest(selected),label='Declared dependency')
    else:
        owner=by_id.get(selected['owner'])
        if owner:
            ref=system.subsystem_reference(owner);key=frame.add(ref,owner['id'],standing={'state':'DECLARED'})
            frame.edge(key,own,'contains',owner='core.identity',basis=identity.canonical_digest(selected))
            frame.parent_read=handle({'facet':'semantic-scope','reference':ref})
    # Existing bindings only, restricted before counts/hashes or node names.
    bindings=[]
    for namespace,ident,binding in O._in_scope(frame.root,frame.scope,read_context=frame.context):
        if frame.payload.get('project_lens') and namespace!=frame.payload['project_lens']:continue
        matched=[x for x in binding['relations'] if identity.reference_key(x['target'])==identity.reference_key(admitted)]
        if not matched:continue
        snap=W.read_snapshot(namespace,frame.root,read_context=frame.context,resolve=False)
        task=snap['raw'][ident];ref=O.work_reference(namespace,ident);key=frame.add(ref,task['title'],basis=W._task_revision(task))
        for relation in matched:frame.edge(key,own,'owner-binding',owner='domain.work',basis=binding['binding_revision'],label=relation['relation'])
        bindings.append({'project':namespace,'work':ident,'binding':binding['binding_revision']})
    frame.lane('owner-bindings','domain.work',identity.canonical_digest(bindings),coverage={'state':'BOUND_WORK_ONLY','qualification':O.UNBOUND})


def _work(frame,reference):
    from laplace.work import project_work_views as V,project_work_navigation as N
    admitted=O.admit_reference(frame.root,frame.scope,reference,read_context=frame.context)['reference']
    project,ident=admitted['identity']['namespace'],admitted['identity']['id']
    snap=W.read_snapshot(project,frame.root,read_context=frame.context);rows=snap['by_id'];row=rows[ident]
    frame.focus=admitted;frame.title=row['title'];frame.semantic_kind='work';frame.project_context=project
    def add(task):return frame.add(O.work_reference(project,task['id']),task['title'],basis=task['work_revision'],standing=V._standing(task),admit=False)
    own=add(row);parent=row.get('parent_work_id')
    if parent in rows:
        key=add(rows[parent]);frame.edge(key,own,'contains',owner='domain.work',basis=snap['ledger_revision'])
        frame.parent_read=handle({'facet':'semantic-scope','reference':O.work_reference(project,parent)})
    for candidate in rows.values():
        if candidate.get('parent_work_id')==ident:frame.edge(own,add(candidate),'contains',owner='domain.work',basis=snap['ledger_revision'])
        if candidate['id'] in row.get('depends_on',[]):frame.edge(own,add(candidate),'requires',owner='domain.work',basis=row.get('dependency_revision'))
        if ident in candidate.get('depends_on',[]):frame.edge(add(candidate),own,'requires',owner='domain.work',basis=candidate.get('dependency_revision'))
    binding=O.current_binding(frame.root,project,ident)
    if binding:
        for rel in binding['relations']:
            try:key=frame.add(rel['target'])
            except ValueError:frame.hidden=True;continue
            frame.edge(own,key,'owner-binding',owner='domain.work',basis=binding['binding_revision'],label=rel['relation'])
        frame.lane('owner-bindings','domain.work',binding['binding_revision'],timestamp=binding.get('ts'))
    phases=row.get('phases') or []
    for phase in phases:
        coord={'kind':'work-phase','id':phase['id']};read=V.handle(project,{'view':'review','id':ident,'phase_id':phase['id']})
        detail={'http':read['http'],'native':{'operation':'project','payload':read['payload']}}
        title=(phase.get('phase') or 'Review phase').replace('-',' ').title()
        key=frame.add(admitted,title,basis=identity.canonical_digest({k:phase.get(k) for k in ('id','phase','state','verdict','intent')}),
            coordinate=coord,detail=detail,adapter={'kind':'work-review-phase','project':project,'work_id':ident,'phase_id':phase['id']},admit=False,
            standing={'state':phase.get('state') or 'RECORDED'},kind='work-phase')
        frame.edge(own,key,'contains',owner='domain.work',basis=snap['ledger_revision'],label='Recorded phase')
    delivery_coordinates=set()
    if (frame.allowed & {'configured-route','admitted-route'} or frame.payload['facet']=='timeline' or (frame.coordinate or {}).get('kind')=='delivery-event') and any(item.get('kind')=='work-delivery' for item in row.get('deliveries') or ()):
        from laplace.work import work_delivery as D
        observed=D.geometry_observation(frame.root,project,ident,read_context=frame.context,event_id=frame.coordinate['id'] if frame.coordinate and frame.coordinate['kind']=='delivery-event' else None)
        for event in observed['events']:
            coord={'kind':'delivery-event','id':event['id']};delivery_coordinates.add(event['id'])
            key=frame.add(admitted,event['title'],basis=event['basis'],coordinate=coord,detail=event['read'],admit=False,kind='delivery-event',
                standing={'state':event['state'],'admission_observation':event['admission_observation']})
            frame.edge(own,key,'admitted-route' if event['admitted'] else 'configured-route',owner='domain.work',basis=event['basis'],
                label='Observed admitted recipient' if event['admitted'] else 'Recorded delivery intent',
                qualification='VERIFIED_WRITING_TURN' if event['admitted'] else 'INTENT_ONLY',read=event['read'])
            frame.event(admitted,'delivery-state',event['title']+' · '+event['state'],basis=event['basis'],timestamp=event.get('ts'),
                coordinate=coord,read=event['read'],lane='delivery-events')
        frame.lane('delivery-events','domain.work',observed['cut'],coverage={**observed['coverage'],
            'event_order':'Owner event order, latest state per event; not every transition or a merged global chronology.'})
    if frame.coordinate:
        is_phase=frame.coordinate['kind']=='work-phase' and any(x.get('id')==frame.coordinate['id'] for x in phases)
        is_event=frame.coordinate['kind']=='delivery-event' and frame.coordinate['id'] in delivery_coordinates
        if not (is_phase or is_event):raise ValueError('Selected local Work phase/event is unavailable.')
        frame.semantic_kind=frame.coordinate['kind'];frame.title=frame.nodes[_key(admitted,frame.coordinate)]['title']
        frame.parent_read=handle({'facet':'semantic-scope','reference':admitted})
    history=N._history_entries(N._history_rows(frame.root,project,ident))
    for pos,event in enumerate(history):
        read=V.handle(project,{'view':'review','id':ident,'phase_id':event['phase_id']}) if event.get('phase_id') else V.handle(project,{'view':'history','id':ident,'offset':pos,'limit':1})
        frame.event(admitted,event['record'],event.get('title') or event.get('phase') or event.get('status') or 'Recorded Work event',
            basis=identity.canonical_digest(event),timestamp=event.get('at'),coordinate={'kind':'work-phase','id':event['phase_id']} if event.get('phase_id') else None,
            read={'http':read['http'],'native':{'operation':'project','payload':read['payload']}},lane='work-history')
    frame.lane('work','domain.work',snap['cut'],timestamp=row.get('ts'),read=handle({'facet':'inspect','reference':admitted}))
    frame.lane('work-history','domain.work',identity.canonical_digest(history),coverage={'state':'RECORDED_LEDGER_ORDER','known':len(history)},read=handle({'facet':'timeline','reference':admitted}))


def _definition(frame,reference):
    from laplace.pipeline import workflow_definitions as D
    caller=O.project_scope(frame.payload['project_lens'],frame.scope.door) if frame.payload.get('project_lens') else frame.scope
    try:row,head,history=D._select(D._rows(frame.root),caller,{'reference':reference})
    except D.Refused as error:
        if error.details.get('code')!='NOT_IN_SCOPE' or frame.scope.kind!='owned-workspace':raise
        caller=frame.scope;row,head,history=D._select(D._rows(frame.root),caller,{'reference':reference})
    body=D._body(frame.root,row);frame.project_context=(row.get('scope') or {}).get('namespace')
    parent=D.reference(row['definition_id'],row['definition_revision']);frame.focus=parent;frame.semantic_kind='workflow-definition';frame.title=body['title']
    read=D.scoped_handle(caller,row['definition_id'],row['definition_revision']);own=frame.add(parent,body['title'],basis=row['definition_revision'],detail=read,admit=False,
        adapter={'kind':'workflow-definition-editor','reference':parent},standing={'state':'SAVED'})
    steps={x['id']:x for x in body['steps']};keys={}
    for sid,step in steps.items():
        coordinate={'kind':'workflow-step','id':sid}
        keys[sid]=frame.add(parent,step.get('title') or sid,basis=row['definition_revision'],coordinate=coordinate,detail=read,
            adapter={'kind':'workflow-definition-editor','reference':parent,'step_id':sid},admit=False,kind='workflow-step',standing={'state':'CONFIGURED','qualification':'Saved definition; no admission is implied.'})
    for sid,step in steps.items():
        frame.edge(keys.get(step.get('parent_id'),own),keys[sid],'contains',owner=D.OWNER,basis=row['definition_revision'])
    for edge in body.get('edges') or []:
        frame.edge(keys[edge['from']],keys[edge['to']],'configured-route',owner=D.OWNER,basis=row['definition_revision'],label=edge['kind'],qualification='CONFIGURED_ONLY')
    if frame.coordinate:
        if frame.coordinate['kind']!='workflow-step' or frame.coordinate['id'] not in steps:raise ValueError('Selected saved local workflow step is unavailable.')
        if reference.get('version') is None:raise ValueError('A local workflow step requires an exact saved parent version.')
        frame.semantic_kind='workflow-step';frame.title=frame.nodes[_key(parent,frame.coordinate)]['title']
        frame.parent_read=handle({'facet':'semantic-scope','reference':parent,**({'project_lens':frame.payload['project_lens']} if frame.payload.get('project_lens') else {})})
    for edition in history:
        ref=D.reference(edition['definition_id'],edition['definition_revision'])
        frame.event(parent,'saved-definition','Saved workflow edition',basis=edition['definition_revision'],timestamp=edition.get('ts'),read=D.scoped_handle(caller,edition['definition_id'],edition['definition_revision']),lane='workflow-history')
    frame.lane('workflow-definition',D.OWNER,row['definition_revision'],timestamp=row.get('ts'),coverage={'state':'ONE_SAVED_BODY','steps':len(steps),'qualification':'Instructions/settings/body are not transported by this geometry read.'},read=read)


def _scientific(frame,reference):
    from laplace.research import object_context as R
    project=_ref_project(reference)
    if not frame.scope.admits(project):raise ValueError('Selected scientific coordinate unavailable.')
    observed=R.geometry_observation(frame.root,project,reference);metadata=observed['metadata'];frame.context.setdefault(('geometry-scientific-coordinates',project),{}).update(metadata);selected=metadata.get(identity.reference_key(reference))
    if selected is None:raise ValueError('Selected scientific coordinate unavailable.')
    if reference.get('version') and reference.get('version')!={'basis':selected['basis']}:raise ValueError('CHANGED_INPUT: selected scientific version changed.')
    frame.focus=copy.deepcopy(reference);frame.title=selected['title'];frame.semantic_kind=reference['kind'];frame.project_context=project
    own=frame.add(reference,selected['title'],basis=selected['basis'],standing=selected['standing'],admit=False);frame.title=frame.nodes[own]['title']
    refkey=identity.reference_key(reference)
    for relation in observed['relations']:
        a,b=relation['source'],relation['target']
        if refkey not in {identity.reference_key(a),identity.reference_key(b)}:continue
        if relation['kind'] not in frame.allowed:continue
        keys=[]
        try:
            for ref in (a,b):
                meta=metadata.get(identity.reference_key(ref)) or {}
                keys.append(frame.add(ref,meta.get('title'),basis=meta.get('basis'),standing=meta.get('standing')))
        except ValueError:frame.hidden=True;continue
        frame.edge(*keys,relation['kind'],owner='domain.research',basis=selected['basis'],label=relation.get('label'),
            consumed_basis=relation.get('consumed_basis'),qualification=relation['qualification'])
    for event in observed['events']:
        read=handle({'facet':'object','reference':event.get('reference') or reference})
        frame.event(reference,event['kind'],event['title'],basis=event['basis'],timestamp=event.get('timestamp'),read=read,lane='scientific-history')
    frame.lane('scientific-metadata','domain.research',identity.canonical_digest({'selected':selected,'edges':frame.edges,'events':frame.events}),coverage=observed['coverage'])


def request(root,scope,payload,*,read_context=None):
    root=Path(root).resolve();context={} if read_context is None else read_context
    lens=payload.get('project_lens')
    if lens:
        from laplace.work.object_facets import _projects
        if lens not in {x['name'] for x in _projects(root,scope)}:raise ValueError('Project lens is unavailable in the admitted scope.')
    frame=Frame(root,scope,payload,context);reference=payload.get('reference')
    if reference is not None and identity.reference_problems(reference):raise ValueError('Select an exact owner-qualified geometry reference.')
    kind=(reference or {}).get('kind')
    coordinate=payload.get('coordinate')
    if coordinate:
        from jsonschema import Draft202012Validator
        if not Draft202012Validator(COORDINATE).is_valid(coordinate):raise ValueError('Select a closed local coordinate.')
        if (coordinate['kind']=='workflow-step' and kind!='workflow-definition') or (coordinate['kind'] in {'work-phase','delivery-event'} and kind!='work'):
            raise ValueError('Local coordinate does not belong to this parent owner.')
    if payload.get('lane') and payload['facet']!='timeline':raise ValueError('A lane selects a timeline only.')
    if reference is None or kind in {'subsystem','capability'}:_declared(frame,reference)
    elif kind=='work':_work(frame,reference)
    elif kind=='workflow-definition':_definition(frame,reference)
    elif kind in {'concept','research-record','research-concern','reference'}:_scientific(frame,reference)
    else:
        admitted=_admit_metadata(root,scope,reference,context);frame.focus=admitted;frame.semantic_kind=kind
        frame.title=kind.replace('-',' ').title();frame.add(admitted);frame.unavailable.append('This owner exposes no compact related-object/history lane here.')
        frame.lane('selected-coordinate',reference['owner'],identity.canonical_digest(admitted),coverage={'state':'COORDINATE_ONLY','currentness':'NOT_INSPECTED'})
    # A local semantic coordinate is a parent-qualified observation, never an ID.
    nodes=list(frame.nodes.values());events=frame.events
    if frame.focus:
        focuskey=_key(frame.focus,frame.coordinate);local={focuskey}
        for edge in frame.edges:
            if edge['source']==focuskey:local.add(edge['target'])
            if edge['target']==focuskey:local.add(edge['source'])
        nodes=[node for node in nodes if node['key'] in local]
        frame.edges=[edge for edge in frame.edges if edge['source'] in local and edge['target'] in local]
    if frame.coordinate and frame.coordinate['kind'] in {'work-phase','delivery-event'}:
        events=[event for event in events if event.get('coordinate')==frame.coordinate]
    cut=identity.canonical_digest({'scope':[scope.kind,scope.namespace], 'lens':lens,'focus':frame.focus,'coordinate':frame.coordinate,
        'relations':sorted(frame.allowed),'lanes':frame.lanes,'nodes':nodes,'edges':frame.edges,'events':events})
    stable={k:v for k,v in payload.items() if k not in {'offset','as_of'}}
    if payload.get('as_of') and not identity.revision_matches(payload['as_of'],cut):
        raise O.DiscoveryRefusal('CHANGED_INPUT','Owner observations changed; explicitly restart this bounded view.',next_reads=[handle(stable)])
    offset,limit=payload.get('offset',0),payload.get('limit',20)
    timeline=payload['facet']=='timeline';lane=payload.get('lane')
    if lane and lane not in {x['lane'] for x in frame.lanes}:raise ValueError('Selected timeline lane is unavailable.')
    selected_events=[e for e in events if lane is None or e['lane']==lane]
    selected=selected_events if timeline else nodes
    page=selected[offset:offset+limit];keys={x['key'] for x in page}
    # Edges never refer to omitted nodes. The focus remains as a stable anchor.
    focuskey=_key(frame.focus,frame.coordinate) if frame.focus else None
    anchor=frame.nodes.get(focuskey)
    visible=page if not timeline else []
    if not timeline and anchor and anchor['key'] not in keys:visible=[anchor,*visible];keys.add(anchor['key'])
    edges=[e for e in frame.edges if e['source'] in keys and e['target'] in keys] if not timeline else []
    nextread=handle({**stable,'offset':offset+limit,'limit':limit,'as_of':cut}) if offset+limit<len(selected) else None
    from laplace.pipeline.workflow_definitions import _scope_id
    coverage={'state':'BOUNDED_OWNER_OBSERVATIONS','depth':1,'known':len(selected),'omitted':max(0,len(selected)-offset-len(page)),
        'unavailable':frame.unavailable,'atomic':False,'qualification':'Independent owner cuts; spatial proximity and omission imply no relation or permission.'}
    if frame.hidden:coverage['privacy']='Some coordinates are unavailable or excluded; their identities and counts are not disclosed.'
    front=[{'source':node['key'],'relation':'explicit-neighbourhood','coverage':{'state':'NOT_EXPANDED','depth':1},
        'read':node['expand_read']} for node in visible if node['key']!=focuskey]
    if nextread:front.append({'source':focuskey,'relation':'page','coverage':{'state':'MORE_AT_THIS_CUT'},'read':nextread})
    return {'schema_version':SCHEMA,'view':payload['facet'],'scope':scope.public(),'scope_id':_scope_id(root,scope),'project_lens':lens,
        'focus':{'reference':frame.focus,'coordinate':frame.coordinate},'semantic_scope':{'kind':frame.semantic_kind,'title':frame.title,
            'reference':frame.focus,'coordinate':frame.coordinate,'parent_read':frame.parent_read},
        'observations':frame.lanes,'nodes':visible,'edges':edges,'events':page if timeline else [],'coverage':coverage,'frontier':front,
        'pagination':{'offset':offset,'limit':limit,'next_read':nextread,'restart_read':handle(stable),'cut':cut},
        'read':handle({**payload,'as_of':cut}),**navigation(frame.focus,project_lens=lens,coordinate=frame.coordinate)}


def resolve_coordinate(root,scope,reference,coordinate,*,expected_basis):
    payload={'facet':'semantic-scope','reference':reference,'coordinate':coordinate}
    value=request(root,scope,payload);node=next((x for x in value['nodes'] if x['coordinate']==coordinate),None)
    if node is None or not identity.revision_matches(expected_basis,node['basis']):raise ValueError('CHANGED_INPUT: selected local coordinate changed.')
    return {'reference':value['focus']['reference'],'coordinate':copy.deepcopy(coordinate),'basis':node['basis'],
        'summary':{'title':node['title'],'owner':node['owner'],'kind':node['kind']},'read':node['detail_read']}
