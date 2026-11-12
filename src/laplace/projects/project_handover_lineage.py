"""Opt-in complete definition lineage through the existing fresh-root handover.

The hidden handover stage is one request's scratch, not a query registry or a
source of authority. Only verified quiescent progress offers an explicit next
cell. Original rows/bodies are never republished as new definition saves.
"""
from __future__ import annotations
from contextlib import ExitStack,contextmanager
import copy
import contextvars
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import time
from laplace.core.identity import canonical_digest
from laplace.pipeline import workflow_definitions as D,workflow_definition_records as R,workflow_definition_history as L
from laplace.work import owner_discovery as O
from . import project_data as C

FORMAT='lineage-v2'
SCHEMA='laplace.project-data-handover/2'
INVENTORY='project-handover.inventory.jsonl'
CELL_ROWS=32
CELL_BYTES=1_000_000
COPY_BUFFER=64*1024
_IO=contextvars.ContextVar("lineage_io",default=None)
_STAGE=contextvars.ContextVar("lineage_stage",default=None)

def _charge(kind,size):
    values=_IO.get()
    if values is not None:values[kind]=values.get(kind,0)+size


def _H():
    from . import project_handover
    return project_handover


def _encoded(value):return _H().encoded(value)
def _fail(code,**facts):raise _H().Refused(code,**facts)
def _stamp(path):
    s=path.stat();return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]


def _file(path):
    if path.is_symlink() or not path.is_file():_fail('HANDOVER_CUSTODY_UNAVAILABLE')
    if path.stat().st_size>_H().PER_FILE:_fail('FILE_BOUND',file=path.name)
    h=hashlib.sha256();size=0
    with path.open('rb') as stream:
        while raw:=stream.read(COPY_BUFFER):size+=len(raw);h.update(raw)
    _charge('verification_hash_bytes',size)
    return {'bytes':size,'sha256':'sha256:'+h.hexdigest()}


def _json(path):
    if path.is_symlink() or not path.is_file():_fail('STAGE_CUSTODY_UNKNOWN')
    if path.stat().st_size>CELL_BYTES:_fail('STAGE_CONTROL_BOUND')
    return json.loads(path.read_bytes(),object_pairs_hook=D.W._unique)


def _check_write(path,extra):
    admitted=_STAGE.get()
    if not admitted:return
    stage,limit=admitted
    if not path.is_relative_to(stage):_fail('STAGE_CUSTODY_UNKNOWN')
    size=0
    if stage.exists():
        for p in stage.rglob('*'):
            if p.is_symlink():_fail('STAGE_CUSTODY_UNKNOWN')
            if p.is_file():size+=p.stat().st_size
    metrics=_IO.get()
    if metrics is not None:metrics['staged_peak_bytes']=max(metrics.get('staged_peak_bytes',0),size+extra)
    if size+extra>limit:_fail('STAGED_BYTE_BOUND',staged_bytes=size,proposed_bytes=extra,maximum=limit)


def _write(path,raw):
    _check_write(path,len(raw))
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    _charge('stage_written_bytes',len(raw))


def _replace(path,value):
    temporary=path.with_name(path.name+'.next')
    _write(temporary,_encoded(value));os.replace(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def _safe_destination(root,raw):
    path=Path(raw).absolute()
    if '..' in Path(raw).parts or path.resolve()!=path or path.is_symlink() or path.is_relative_to(root) or root.is_relative_to(path):_fail('FRESH_DESTINATION_REQUIRED')
    if not path.parent.is_dir():_fail('DESTINATION_PARENT_REQUIRED')
    return path


def contract_properties():
    return {'definition_transport':{'const':FORMAT},'definitions':{'type':'array','minItems':1,'maxItems':80,'items':{'type':'object'}},
        'expected_lineage_basis':{'type':'string','pattern':'^sha256:[0-9a-f]{64}$'},
        'expected_checkpoint':{'type':'string','pattern':'^sha256:[0-9a-f]{64}$'},
        'cell_rows':{'type':'integer','minimum':1,'maximum':CELL_ROWS},
        'cell_bytes':{'type':'integer','minimum':1,'maximum':CELL_BYTES},
        'cell_seconds':{'type':'number','exclusiveMinimum':0,'maximum':30},
        'capture_max_bytes':{'type':'integer','minimum':1},'metadata_max_rows':{'type':'integer','minimum':1},
        'max_staged_bytes':{'type':'integer','minimum':1}}


def _wire(root,scope,payload,door):
    # Effect and inspection permission precede even destination/source lookup.
    if not isinstance(scope,O.Scope) or scope.kind!='owned-workspace' or door.get('origin') not in {'human','sdk'}:_fail('EXPLICIT_AUTHOR_EXPORT_SELECTION_REQUIRED')
    allowed={'action','definition_transport','project','request_id','definitions','reference','expected_basis','destination','max_files','max_rows','max_bytes',*contract_properties()}
    if set(payload)-allowed or payload.get('definition_transport')!=FORMAT or payload.get('action') not in {'request','export','continue','inspect'}:_fail('INVALID_LINEAGE_TRANSFER')
    rid=payload.get('request_id')
    if not isinstance(rid,str) or not 1<=len(rid)<=96:_fail('ORIGINAL_REQUEST_ID_REQUIRED')
    if not isinstance(payload.get('destination'),str):_fail('DESTINATION_REQUIRED')
    budgets=_H()._budgets(*(payload.get(k) for k in ('max_files','max_rows','max_bytes')))
    values={**payload,'cell_rows':payload.get('cell_rows',CELL_ROWS),'cell_bytes':payload.get('cell_bytes',CELL_BYTES),
        'cell_seconds':payload.get('cell_seconds',5),'capture_max_bytes':payload.get('capture_max_bytes',L.CAPTURE_BYTES),
        'metadata_max_rows':payload.get('metadata_max_rows',L.METADATA_ROWS),'max_staged_bytes':payload.get('max_staged_bytes',3*budgets['max_bytes'])}
    from jsonschema import Draft202012Validator
    for key,schema in contract_properties().items():
        if key in values and next(Draft202012Validator(schema).iter_errors(values[key]),None):_fail('INVALID_LINEAGE_TRANSFER',field=key)
    # Action/last checkpoint are mutable demands on one immutable transfer wire.
    wire={k:copy.deepcopy(v) for k,v in values.items() if k not in {'action','expected_checkpoint'}}
    wire['source_scope_id']=D._scope_id(root,scope)
    dest=_safe_destination(root,wire['destination']);wire['destination']=str(dest)
    intent=canonical_digest(wire);stage=dest.parent/('.laplace-handover-'+intent.removeprefix('sha256:'))
    return wire,intent,stage,dest


def _selection(root,scope,wire):
    project=wire.get('project');manifest=None;selection=None
    if project is not None:
        if not isinstance(project,str) or not scope.admits(project):_fail('NOT_IN_SCOPE')
        from laplace.pipeline import registry
        record=registry.resolve(project,repo_root=root)
        if not record or record.external_root or not record.project_dir or record.project_dir=='.':_fail('LOCAL_PROJECT_HOME_REQUIRED')
    if 'reference' in wire:
        reference=wire['reference']
        if not project or reference.get('owner')!='domain.projects' or reference.get('kind')!='artifact' or reference.get('identity',{}).get('project')!=project:_fail('MANIFEST_ART_REQUIRED')
        manifest,meta=_H()._retained_manifest(root,project,reference['identity']['id'])
        if not D.identity.revision_matches(wire.get('expected_basis'),meta['revision']):_fail('SELECTED_MANIFEST_CHANGED')
        selection={**manifest['selection'],'manifest_id':reference['identity']['id'],'manifest_sha256':meta['revision']}
        selection['artifact_ids']=list(dict.fromkeys([*selection['artifact_ids'],reference['identity']['id']]))
        refs=selection['definitions']
        if 'definitions' in wire:_fail('CONFLICTING_DEFINITION_SELECTION')
    else:
        refs=wire.get('definitions')
        if wire.get('expected_basis') is not None:_fail('MANIFEST_ART_REQUIRED')
    if not isinstance(refs,list) or not 1<=len(refs)<=80:_fail('EXPLICIT_VERSIONED_SELECTION_REQUIRED')
    return project,selection,refs


def _plan(root,scope,wire,*,rehash=False):
    project,selection,refs=_selection(root,scope,wire);frames=[];ids=set();requests=set();endpoints=[];body_sources={};merged=[]
    for reference in refs:
        frame=L.capture_lineage(root,scope,reference,transfer_project=project,capture_max_bytes=wire['capture_max_bytes'],metadata_max_rows=wire['metadata_max_rows'])
        row=frame['selected']['row'];ident=row['definition_id']
        if ident in ids:_fail('DUPLICATE_SELECTED_DEFINITION')
        ids.add(ident)
        if not project and row['scope']!={'kind':'owned-workspace'}:_fail('WORKSPACE_DEFINITION_ONLY_REQUIRED')
        frames.append(frame)
        endpoints.append({'reference':D.reference(ident,row['definition_revision']),'scope':row['scope'],'known':len(frame['prefix']),
            'cut':canonical_digest(frame['signature'])})
        for ordinal,meta in enumerate(frame['prefix'],1):
            value=meta['row']
            if value['scope']!=row['scope']:_fail('DEFINITION_SCOPE_CHAIN_CHANGED')
            if value['request_id'] in requests:_fail('INVALID_EXPORT_REQUEST_DUPLICATE')
            requests.add(value['request_id'])
            if rehash:R.raw(frame,meta)
            digest=value['body_handle'].removeprefix('sha256:');relative='contract/writing_bodies/'+digest[:2]+'/'+digest
            path=C._safe(root,relative)
            if not path.is_file() or path.stat().st_size>D.MAX_BODY:_fail('UNAVAILABLE_VERSION')
            body_sources[relative]={'path':relative,'stamp':_stamp(path),'bytes':path.stat().st_size,'sha256':value['body_handle']}
            merged.append((meta['order'],frame,meta,ordinal))
    merged.sort(key=lambda r:r[0])
    if len(merged)>wire['max_rows']:_fail('TOTAL_BUDGET')
    generated={};source_files={};base=None
    if project:
        if selection:
            base=_H()._selected_plan(root,project,{**selection,'definitions':[]},caller=scope,_metadata_only=True,
                **{k:wire[k] for k in ('max_files','max_rows','max_bytes')})
            source_files={r['path']:{**r,'stamp':_stamp(C._safe(root,r['path']))} for r in base['files']}
            rows=_H()._selected_artifact_rows(root,project,selection['artifact_ids'],max_rows=wire['max_rows'],max_bytes=wire['max_bytes'])
            generated['contract/talk.jsonl']=b''.join(r[2] for r in sorted(rows,key=lambda r:r[1]))+b''.join(_encoded(r) for r in C._import_rows(project,[],base['manifest_digest']))
            directory=base['project_dir'];registry_row=base['registry_row']
        else:
            from laplace.pipeline import registry
            directory=registry.resolve(project,repo_root=root).project_dir
            registry_row={'name':project,'project_dir':directory,'kind':'project','manifest':{'writing':{'kind':'general','display_name':project}}}
        generated['registry_projects.json']=_encoded({'projects':[registry_row]})
        generated['profiles/writing_sources.json']=_encoded({'repositories':{'workspace':'.'}})
        if not any(Path(p).is_relative_to(directory) for p in source_files):generated[directory+'/'+C.HOME_MARKER]=C.home_marker(project,directory)
    # The definition-only profile deliberately creates no registry/project.
    reserved={INVENTORY,_H().MANIFEST,'contract/dispatches.jsonl'}
    if reserved&set(source_files) or set(generated)&set(source_files) :_fail('OUTPUT_PATH_COLLISION')
    for rel in set(body_sources)&set(source_files):
        if body_sources[rel]['sha256']!=source_files[rel]['sha256'] or body_sources[rel]['bytes']!=source_files[rel]['bytes']:_fail('OUTPUT_PATH_COLLISION')
        del source_files[rel]
    # Finite control bytes are a real admission resource, independent of old
    # v1 version-count limits. Account a conservative worst one-row-per-part
    # checkpoint before the first stage effect.
    progress_paths=['intent.json',INVENTORY]+[f'parts/{i:08d}/{name}' for i in range(len(merged)) for name in ('dispatch.raw','rows.jsonl')]+['payload/'+p for p in [*source_files,*body_sources,*generated,'contract/dispatches.jsonl']]
    progress_paths+=['parts/'+str(i).zfill(8)+'/bodies/'+p for i,p in enumerate(body_sources)]
    progress_bound=len(_encoded({'files':{p:{'bytes':_H().PER_FILE,'sha256':'sha256:'+'f'*64} for p in progress_paths},'body_paths':sorted(body_sources)}))+4096
    if progress_bound>CELL_BYTES:_fail('STAGE_CONTROL_BOUND',admitted_control_bytes=CELL_BYTES,required_upper_bound=progress_bound)
    for path,raw in generated.items():
        if len(raw)>_H().PER_FILE:_fail('FILE_BOUND',file=path)
    row_bytes=sum(meta['end']-meta['offset'] for _,_,meta,_ in merged)
    if row_bytes>_H().PER_FILE:_fail('FILE_BOUND',file='contract/dispatches.jsonl')
    for info in source_files.values():
        if info['bytes']>_H().PER_FILE:_fail('FILE_BOUND',file=info['path'])
    _H()._validate_output_paths([*source_files,*body_sources,*generated,'contract/dispatches.jsonl',INVENTORY,_H().MANIFEST])
    file_count=len(source_files)+len(body_sources)+len(generated)+3
    base_rows=len(base['rows']) if base else 0
    if file_count>wire['max_files'] or len(merged)+base_rows>wire['max_rows']:_fail('TOTAL_BUDGET')
    lower=row_bytes+sum(x['bytes'] for x in source_files.values())+sum(x['bytes'] for x in body_sources.values())+sum(map(len,generated.values()))
    if lower>wire['max_bytes']:_fail('TOTAL_BUDGET')
    staged_lower=lower+row_bytes+sum(x['bytes'] for x in body_sources.values())
    if staged_lower>wire['max_staged_bytes']:_fail('STAGED_BYTE_BOUND',minimum_staged_bytes=staged_lower)
    public={'source_scope_id':D._scope_id(root,scope),'endpoints':endpoints,'source_files':list(source_files.values()),'body_sources':list(body_sources.values()),
        'generated':{p:{'sha256':C._sha(v),'bytes':len(v)} for p,v in generated.items()},'rows':len(merged),'other_rows':base_rows,
        'raw_row_bytes':row_bytes,'project':project,'lower_bound_bytes':lower,'minimum_files':file_count,'progress_control_bound':progress_bound,'minimum_staged_bytes':staged_lower,
        'prefix_basis':canonical_digest([[order,meta['hash']] for order,_,meta,_ in merged])}
    return {'public':public,'basis':canonical_digest(public),'frames':frames,'merged':merged,'generated':generated,'source_files':source_files,'bodies':body_sources}


def _locks(root,plan,stack):
    from filelock import FileLock
    paths=['registry_projects.json.lock','corpus_friction/work_orders.jsonl.lock','contract/.writing-apply.lock','contract/workflow-definitions.lock']
    project=plan.get('project')
    if project:
        from laplace.pipeline import registry
        record=registry.resolve(project,repo_root=root)
        if record:paths.append(record.project_dir+'/manuscript/.authoring.lock')
    for rel in paths:
        path=C._safe(root,rel)
        if rel.endswith('/manuscript/.authoring.lock') and not path.parent.is_dir():continue
        path.parent.mkdir(parents=True,exist_ok=True);stack.enter_context(FileLock(str(path),timeout=20))


def _stage_files(stage,*,max_entries=None):
    result={}
    for number,path in enumerate(stage.rglob('*'),1):
        if max_entries is not None and number>max_entries:_fail('STAGE_CONTROL_BOUND')
        if path.is_symlink():_fail('STAGE_CUSTODY_UNKNOWN')
        if path.is_file():result[path.relative_to(stage).as_posix()]=_file(path)
    return result


def _checkpoint(stage,value):
    # Checkpoint cannot describe its own hash. A next-file or unexpected part is
    # never silently adopted after interruption.
    value={**value,'files':{p:r for p,r in _stage_files(stage).items() if p!='checkpoint.json'}}
    current=sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())
    for _ in range(8):
        peak=max(value.get('peak_staged_bytes',0),(_IO.get() or {}).get('staged_peak_bytes',0),current+len(_encoded(value)))
        if value.get('peak_staged_bytes')==peak:break
        value['peak_staged_bytes']=peak
    if len(_encoded(value))>CELL_BYTES:_fail('STAGE_CONTROL_BOUND')
    _replace(stage/'checkpoint.json',value)
    return value


def _verify_stage(stage,intent,wire):
    value=_json(stage/'checkpoint.json')
    if value.get('intent')!=intent or not isinstance(value.get('files'),dict):_fail('STAGE_CUSTODY_UNKNOWN')
    phase=value.get('phase');pin=lambda v:isinstance(v,str) and re.fullmatch(r'sha256:[0-9a-f]{64}',v)
    required={'intent','plan_basis','phase','row_cursor','cells','body_paths','files','peak_staged_bytes'}
    if phase not in {'capture','assemble','inventory','publish'}:_fail('STAGE_CUSTODY_UNKNOWN')
    if phase!='capture':required|={'copy_cursor','copy_offset'}
    if phase in {'inventory','publish'}:required.add('inventory_cursor')
    if not required<=set(value) or set(value)-required-{'last_cell'} or not pin(value['plan_basis']):_fail('STAGE_CUSTODY_UNKNOWN')
    for field in ('row_cursor','cells','peak_staged_bytes','copy_cursor','copy_offset','inventory_cursor'):
        if field in value and (type(value[field])!=int or value[field]<0):_fail('STAGE_CUSTODY_UNKNOWN')
    if value['cells']>value['row_cursor'] or value['row_cursor']>wire['max_rows'] or value['peak_staged_bytes']>wire['max_staged_bytes']:_fail('STAGE_CUSTODY_UNKNOWN')
    paths=value['body_paths']
    if not isinstance(paths,list) or any(not isinstance(p,str) or not re.fullmatch(r'contract/writing_bodies/[0-9a-f]{2}/[0-9a-f]{64}',p) or p.split('/')[-2]!=p.split('/')[-1][:2] for p in paths) or paths!=sorted(set(paths)):_fail('STAGE_CUSTODY_UNKNOWN')
    if value['cells'] and 'last_cell' not in value:_fail('STAGE_CUSTODY_UNKNOWN')
    if 'last_cell' in value:
        last=value['last_cell']
        if not isinstance(last,dict) or not {'versions','payload_bytes'}<=set(last) or set(last)-{'versions','payload_bytes','semantic_body_bytes'} or any(type(v)!=int or v<0 for v in last.values()):_fail('STAGE_CUSTODY_UNKNOWN')
        if last['versions']>wire['cell_rows'] or last['payload_bytes']>wire['cell_bytes'] or last.get('semantic_body_bytes',0)>last['payload_bytes']:_fail('STAGE_CUSTODY_UNKNOWN')
    for path,item in value['files'].items():
        if not isinstance(path,str) or path=='checkpoint.json' or not isinstance(item,dict) or set(item)!={'bytes','sha256'} or type(item['bytes'])!=int or item['bytes']<0 or not pin(item['sha256']):_fail('STAGE_CUSTODY_UNKNOWN')
        C._safe(stage,path)
    directory_bound=5+sum(len(Path(p).parts) for p in value['files'])
    actual={p:r for p,r in _stage_files(stage,max_entries=directory_bound).items() if p!='checkpoint.json'}
    if actual!=value['files']:_fail('STAGE_CUSTODY_UNKNOWN')
    return value


def _verify_progress(root,stage,plan,wire,state):
    """Derive progress from source-bound immutable parts and exact payload.

    The checkpoint's counters and digest table are observations to verify, not
    evidence that its requested phase was ever reached. Recovery work is bounded
    by admitted output/control resources and is charged separately from a cell.
    """
    if {p.name for p in stage.iterdir()}!={'intent.json','checkpoint.json','parts','payload'}:_fail('STAGE_CUSTODY_UNKNOWN')
    parts=list((stage/'parts').iterdir())
    if {p.name for p in parts}!={f'{n:08d}' for n in range(state['cells'])} or any(not p.is_dir() or p.is_symlink() for p in parts):_fail('STAGE_CUSTODY_UNKNOWN')
    allowed={'intent.json'};covered=0;body_locations={};previous={};requests=set()
    for part in sorted(parts):
        rows_path=part/'rows.jsonl';raw_path=part/'dispatch.raw'
        if any(not p.is_file() or p.stat().st_size>wire['cell_bytes'] for p in (rows_path,raw_path)):_fail('STAGE_CUSTODY_UNKNOWN')
        row_lines=rows_path.read_bytes().splitlines(keepends=True);raw_lines=raw_path.read_bytes().splitlines(keepends=True)
        if not 1<=len(row_lines)<=wire['cell_rows'] or len(raw_lines)!=len(row_lines) or covered+len(raw_lines)>len(plan['merged']):_fail('STAGE_CUSTODY_UNKNOWN')
        allowed|={rows_path.relative_to(stage).as_posix(),raw_path.relative_to(stage).as_posix()};spent=0
        for raw_meta,raw in zip(row_lines,raw_lines):
            if not raw_meta.endswith(b'\n') or not raw.endswith(b'\n'):_fail('STAGE_CUSTODY_UNKNOWN')
            item=json.loads(raw_meta,object_pairs_hook=D.W._unique);physical,_frame,meta,ordinal=plan['merged'][covered];row=meta['row']
            expected={'kind':'definition-row','definition_id':row['definition_id'],'version':row['definition_revision'],
                'ordinal':ordinal,'physical_order':physical,'raw_line_sha256':meta['hash'],'body_handle':row['body_handle']}
            if any(type(item.get(k))!=int for k in ('ordinal','physical_order')) or item!=expected or C._sha(raw)!=meta['hash']:_fail('STAGE_CUSTODY_UNKNOWN')
            actual=json.loads(raw,object_pairs_hook=D.W._unique)
            digest=row['body_handle'][7:];rel='contract/writing_bodies/'+digest[:2]+'/'+digest
            if rel not in body_locations:
                path=part/'bodies'/rel;name=path.relative_to(stage).as_posix()
                if state['files'].get(name)!={'bytes':plan['bodies'][rel]['bytes'],'sha256':row['body_handle']}:_fail('STAGE_CUSTODY_UNKNOWN')
                body_locations[rel]=part/'bodies';allowed.add(name)
            body,body_raw=D._body(body_locations[rel],actual,with_raw=True)
            _charge('recovery_semantic_body_bytes',len(body_raw))
            previous[row['definition_id']]=D.validate_lineage_version(actual,body,row['definition_id'],previous.get(row['definition_id']),requests)
            spent+=len(raw)+plan['bodies'][rel]['bytes'];covered+=1
        if spent>wire['cell_bytes']:_fail('STAGE_CUSTODY_UNKNOWN')
    if covered!=state['row_cursor'] or sorted(body_locations)!=state['body_paths']:_fail('STAGE_CUSTODY_UNKNOWN')
    if state['phase']=='capture':
        if covered>=len(plan['merged']) or set(state['files'])!=allowed:_fail('STAGE_CUSTODY_UNKNOWN')
        return
    if covered!=len(plan['merged']):_fail('STAGE_CUSTODY_UNKNOWN')
    tasks=_copy_tasks(stage,plan);cursor=state['copy_cursor'];offset=state['copy_offset']
    if cursor>len(tasks) or cursor==len(tasks) and offset or cursor<len(tasks) and (tasks[cursor][2]>0 and offset>=tasks[cursor][2] or tasks[cursor][2]==0 and offset!=0):_fail('STAGE_CUSTODY_UNKNOWN')
    if state['phase']=='assemble' and cursor==len(tasks) or state['phase']!='assemble' and cursor!=len(tasks):_fail('STAGE_CUSTODY_UNKNOWN')
    for number,(rel,sources,total) in enumerate(tasks):
        length=total if number<cursor else offset if number==cursor else 0
        present=number<cursor or number==cursor and offset>0
        if not present:continue
        name='payload/'+rel;observed=state['files'].get(name)
        if observed is None or observed['bytes']!=length:_fail('STAGE_CUSTODY_UNKNOWN')
        digest=hashlib.sha256()
        for start in range(0,length,COPY_BUFFER):digest.update(_copy_piece(root,sources,start,min(COPY_BUFFER,length-start)))
        if observed['sha256']!='sha256:'+digest.hexdigest():_fail('STAGE_CUSTODY_UNKNOWN')
        allowed.add(name)
    if state['phase'] in {'inventory','publish'}:
        inv=stage/'payload'/INVENTORY;position=state['inventory_cursor'];seen=0
        if position:
            if not inv.is_file():_fail('STAGE_CUSTODY_UNKNOWN')
            allowed.add('payload/'+INVENTORY)
        with ExitStack() as resources:
            stream=resources.enter_context(inv.open('rb')) if position else None
            for item in _inventory_rows(stage,plan):
                if seen<position:
                    raw=_encoded(item)
                    if stream.read(len(raw))!=raw:_fail('STAGE_CUSTODY_UNKNOWN')
                seen+=1
            if position>seen or stream and stream.read(1) or state['phase']=='publish' and position!=seen or state['phase']=='inventory' and position>=seen:_fail('STAGE_CUSTODY_UNKNOWN')
    if set(state['files'])!=allowed:_fail('STAGE_CUSTODY_UNKNOWN')


def _part_path(stage,index):return stage/'parts'/('%08d'%index)


def _capture_cell(root,stage,plan,wire,state,deadline):
    start=state['row_cursor'];limit=wire['cell_rows'];budget=wire['cell_bytes'];used=0;items=[];raws=[];bodies={}
    existing=set(state['body_paths']);previous={};requests=set()
    # Whole prefix metadata chain was validated before effects. Reuse its exact
    # predecessor for this cell, rather than pretending a cell starts a new chain.
    for _,_,meta,_ in plan['merged'][:start]:previous[meta['row']['definition_id']]=meta['row']['definition_revision'];requests.add(meta['row']['request_id'])
    for physical,frame,meta,ordinal in plan['merged'][start:start+limit]:
        row=meta['row'];digest=row['body_handle'].removeprefix('sha256:');rel='contract/writing_bodies/'+digest[:2]+'/'+digest
        estimate=(meta['end']-meta['offset'])+plan['bodies'][rel]['bytes']
        if used+estimate>budget or time.monotonic()>=deadline:
            if not items and estimate>budget:_fail('CELL_ITEM_BOUND',required_bytes=estimate,cell_bytes=budget)
            break
        actual,raw=R.raw(frame,meta)
        body_raw=D.writing_bodies.store(root).get(row['body_handle'],max_bytes=D.MAX_BODY)
        _charge('semantic_body_bytes',len(body_raw));_charge('selected_raw_row_bytes',len(raw))
        body=json.loads(body_raw,object_pairs_hook=D.W._unique)
        D.validate_lineage_version(actual,body,actual['definition_id'],previous.get(actual['definition_id']),requests)
        if body_raw!=D.W.canonical(body):_fail('NONCANONICAL_SAVED_BODY')
        if _stamp(C._safe(root,rel))!=plan['bodies'][rel]['stamp']:_fail('CHANGED_INPUT')
        previous[actual['definition_id']]=actual['definition_revision']
        if rel not in existing:bodies[rel]=body_raw;existing.add(rel)
        items.append({'kind':'definition-row','definition_id':actual['definition_id'],'version':actual['definition_revision'],
            'ordinal':ordinal,'physical_order':physical,'raw_line_sha256':C._sha(raw),'body_handle':actual['body_handle']})
        raws.append(raw);used+=len(raw)+len(body_raw)
    if not items:_fail('CELL_DEADLINE_NO_PROGRESS')
    part=_part_path(stage,state['cells']);part.mkdir(parents=True,exist_ok=False)
    _write(part/'dispatch.raw',b''.join(raws));_write(part/'rows.jsonl',b''.join(_encoded(i) for i in items))
    for rel,raw in bodies.items():_write(part/'bodies'/rel,raw)
    state={**state,'row_cursor':start+len(items),'cells':state['cells']+1,'body_paths':sorted(existing),
        'last_cell':{'versions':len(items),'payload_bytes':used,'semantic_body_bytes':sum(plan['bodies']['contract/writing_bodies/'+i['body_handle'][7:9]+'/'+i['body_handle'][7:]]['bytes'] for i in items)}}
    if state['row_cursor']==len(plan['merged']):state.update(phase='assemble',copy_cursor=0,copy_offset=0)
    return state


def _copy_tasks(stage,plan):
    tasks=[]
    for rel,info in sorted(plan['source_files'].items()):tasks.append((rel,[(None,rel)],info['bytes']))
    for rel,raw in sorted(plan['generated'].items()):tasks.append((rel,[(raw,None)],len(raw)))
    parts=sorted((stage/'parts').iterdir())
    tasks.append(('contract/dispatches.jsonl',[(None,p/'dispatch.raw') for p in parts],plan['public']['raw_row_bytes']))
    for rel in sorted(plan['bodies']):
        sources=[p/'bodies'/rel for p in parts if (p/'bodies'/rel).is_file()]
        if len(sources)!=1:_fail('STAGE_BODY_CUSTODY_UNKNOWN')
        tasks.append((rel,[(None,sources[0])],plan['bodies'][rel]['bytes']))
    return tasks


def _copy_piece(root,sources,offset,length):
    result=[];left=length;skip=offset
    for raw,path in sources:
        size=len(raw) if raw is not None else (root/path if isinstance(path,str) else path).stat().st_size
        if skip>=size:skip-=size;continue
        take=min(left,size-skip)
        if raw is not None:result.append(raw[skip:skip+take])
        else:
            target=C._safe(root,path) if isinstance(path,str) else path
            with target.open('rb') as stream:stream.seek(skip);data=stream.read(take)
            if len(data)!=take:_fail('CHANGED_INPUT')
            result.append(data)
        left-=take;skip=0
        if not left:break
    if left:_fail('STAGE_SOURCE_TRUNCATED')
    _charge('payload_copy_read_bytes',length)
    return b''.join(result)


def _assemble_cell(root,stage,plan,wire,state,deadline):
    tasks=_copy_tasks(stage,plan);cursor=state['copy_cursor'];offset=state['copy_offset'];used=0
    while cursor<len(tasks) and used<wire['cell_bytes'] and time.monotonic()<deadline:
        rel,sources,total=tasks[cursor];take=min(total-offset,wire['cell_bytes']-used)
        target=C._safe(stage/'payload',rel);target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and target.stat().st_size!=offset:_fail('STAGE_CUSTODY_UNKNOWN')
        raw=_copy_piece(root,sources,offset,take)
        _check_write(target,len(raw))
        with target.open('ab' if offset else 'xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        _charge('stage_written_bytes',len(raw));used+=len(raw);offset+=len(raw)
        if offset==total:
            if total>_H().PER_FILE:_fail('FILE_BOUND',file=rel)
            cursor+=1;offset=0
        elif not raw:_fail('CELL_NO_PROGRESS')
    if not used and cursor<len(tasks):_fail('CELL_DEADLINE_NO_PROGRESS')
    state={**state,'copy_cursor':cursor,'copy_offset':offset,'last_cell':{'versions':0,'payload_bytes':used}}
    if cursor==len(tasks):state.update(phase='inventory',inventory_cursor=0)
    return state


def _inventory_rows(stage,plan):
    for path in sorted((stage/'payload').rglob('*')):
        if path.is_file() and path.relative_to(stage/'payload').as_posix() not in {INVENTORY,_H().MANIFEST}:yield {'kind':'file','path':path.relative_to(stage/'payload').as_posix(),**_file(path)}
    for part in sorted((stage/'parts').iterdir()):
        with (part/'rows.jsonl').open('rb') as stream:
            for raw in stream:yield json.loads(raw,object_pairs_hook=D.W._unique)


def _inventory_cell(stage,plan,wire,state,deadline):
    cursor=state['inventory_cursor'];used=0;covered=0;versions=0;done=True
    target=stage/'payload'/INVENTORY
    with target.open('ab' if cursor else 'xb',buffering=0) as output:
        for number,row in enumerate(_inventory_rows(stage,plan)):
            if number<cursor:continue
            raw=_encoded(row)
            if used+len(raw)>wire['cell_bytes'] or versions>=wire['cell_rows'] or time.monotonic()>=deadline:done=False;break
            if target.stat().st_size+len(raw)>_H().PER_FILE:_fail('FILE_BOUND',file=INVENTORY)
            _check_write(target,len(raw));output.write(raw);_charge('stage_written_bytes',len(raw));used+=len(raw);covered+=1;versions+=row['kind']=='definition-row'
        output.flush();os.fsync(output.fileno())
    if not covered and not done:_fail('CELL_DEADLINE_NO_PROGRESS')
    return {**state,'inventory_cursor':cursor+covered,'phase':'publish' if done else 'inventory','last_cell':{'versions':versions,'payload_bytes':used}}


def _header(stage,plan,wire,intent):
    inventory=_file(stage/'payload'/INVENTORY)
    with (stage/'payload'/INVENTORY).open('rb') as stream:inventory['entries']=sum(1 for _ in stream)
    values=list((stage/'payload').rglob('*'));files=[p for p in values if p.is_file()]
    counts={'files':len(files)+1,'rows':plan['public']['rows']+plan['public']['other_rows'],'bytes':sum(p.stat().st_size for p in files)}
    header={'schema':SCHEMA,'definition_transport':FORMAT,'intent':intent,'source_scope_id':wire['source_scope_id'],'project':plan['public']['project'],
        'inventory':{'path':INVENTORY,**inventory},'endpoints':plan['public']['endpoints'],'budgets':{k:wire[k] for k in ('max_files','max_rows','max_bytes')},
        'counts':counts,'constraints':{'single_body_bytes':D.MAX_BODY,'per_file_bytes':_H().PER_FILE},
        'qualification':'Original selected full prefixes and bytes. No runtime, settings, credentials, execution grant or origin-head renewal is carried.'}
    for _ in range(8):
        raw=_encoded(header);new=counts['bytes']+len(raw)
        if header['counts']['bytes']==new:break
        header['counts']={**counts,'bytes':new}
    else:_fail('RECEIPT_SIZE_UNSTABLE')
    if any(header['counts'][k]>wire['max_'+k] for k in ('files','rows','bytes')):_fail('TOTAL_BUDGET',counts=header['counts'])
    if len(raw)>_H().PER_FILE:_fail('FILE_BOUND',file=_H().MANIFEST)
    return header,raw


def inspect(root,*,expected_intent=None):
    """Pure bounded inventory/chain check; ordinary recipient, origin not needed."""
    root=Path(root).resolve();header=C._json(C._safe(root,_H().MANIFEST))
    required={'schema','definition_transport','intent','source_scope_id','project','inventory','endpoints','budgets','counts','constraints','qualification'}
    if set(header)!=required or header.get('schema')!=SCHEMA or header.get('definition_transport')!=FORMAT or expected_intent and header['intent']!=expected_intent:_fail('UNKNOWN_LINEAGE_HANDOVER')
    if header['constraints']!={'single_body_bytes':D.MAX_BODY,'per_file_bytes':_H().PER_FILE}:_fail('UNSUPPORTED_LINEAGE_LIMITS')
    _H()._budgets(**header['budgets']);inventory=header['inventory']
    if set(header['counts'])!={'files','rows','bytes'} or any(type(v)!=int or v<0 for v in header['counts'].values()):_fail('INVALID_LINEAGE_COUNTS')
    if not isinstance(header['endpoints'],list) or not 1<=len(header['endpoints'])<=80:_fail('INVALID_LINEAGE_TERMINAL')
    for endpoint in header['endpoints']:
        if set(endpoint)!={'reference','scope','known','cut'} or type(endpoint['known'])!=int or endpoint['known']<1:_fail('INVALID_LINEAGE_TERMINAL')
        ident,version=D._selector({'reference':endpoint['reference']},strict=True)
        if version is None:_fail('EXACT_SAVED_VERSION_REQUIRED')
        D._scope(endpoint['scope'])
    if type(inventory.get('entries'))!=int or inventory['entries']<1:_fail('INVALID_INVENTORY')
    if inventory.get('path')!=INVENTORY or set(inventory)!={'path','bytes','sha256','entries'} or inventory['bytes']>_H().PER_FILE:_fail('INVALID_INVENTORY')
    if _file(C._safe(root,INVENTORY))!={k:inventory[k] for k in ('bytes','sha256')}:_fail('INVENTORY_CHANGED')
    files={};rows=[];inventory_count=0
    with (root/INVENTORY).open('rb') as stream:
        for raw in stream:
            inventory_count+=1
            if len(raw)>CELL_BYTES or not raw.endswith(b'\n'):_fail('INVALID_INVENTORY')
            item=json.loads(raw,object_pairs_hook=D.W._unique)
            if item.get('kind')=='file':
                if set(item)!={'kind','path','bytes','sha256'} or item['path'] in files or item['path'] in {INVENTORY,_H().MANIFEST}:_fail('INVALID_INVENTORY')
                if type(item['bytes'])!=int or item['bytes']<0:_fail('INVALID_INVENTORY')
                if item['bytes']>_H().PER_FILE or _file(C._safe(root,item['path']))!={k:item[k] for k in ('bytes','sha256')}:_fail('HANDOVER_DRIFT')
                files[item['path']]=item
            elif item.get('kind')=='definition-row':
                if set(item)!={'kind','definition_id','version','ordinal','physical_order','raw_line_sha256','body_handle'}:_fail('INVALID_INVENTORY')
                if any(type(item[k])!=int or item[k]<1 for k in ('ordinal','physical_order')):_fail('INVALID_INVENTORY')
                rows.append(item)
            else:_fail('INVALID_INVENTORY')
            if len(files)+2>header['budgets']['max_files'] or len(rows)>header['budgets']['max_rows']:_fail('TOTAL_BUDGET')
    if inventory_count!=inventory['entries']:_fail('INVALID_INVENTORY')
    actual=set()
    for path in root.rglob('*'):
        if path.is_symlink():_fail('HANDOVER_DRIFT')
        if path.is_file():actual.add(path.relative_to(root).as_posix())
    if actual!=set(files)|{INVENTORY,_H().MANIFEST}:_fail('HANDOVER_FILE_SET_CHANGED')
    previous={};requests=set();ordinals={};physical=0;read_rows=0
    with C._safe(root,'contract/dispatches.jsonl').open('rb') as stream:
        for number,raw in enumerate(stream):
            if number>=len(rows) or not raw.endswith(b'\n'):_fail('HANDOVER_ROW_DRIFT')
            read_rows+=1;item=rows[number];row=json.loads(raw,object_pairs_hook=D.W._unique);ident=row['definition_id']
            endpoint=next((e for e in header['endpoints'] if e['reference']['identity']['id']==ident),None)
            if endpoint is None or row['scope']!=endpoint['scope']:_fail('DEFINITION_SCOPE_CHAIN_CHANGED')
            if C._sha(raw)!=item['raw_line_sha256'] or row['definition_revision']!=item['version'] or ident!=item['definition_id'] or row['body_handle']!=item['body_handle'] or item['physical_order']<=physical:_fail('HANDOVER_ROW_DRIFT')
            physical=item['physical_order'];ordinal=ordinals.get(ident,0)+1
            if item['ordinal']!=ordinal:_fail('INVALID_EXPORT_CHAIN')
            ordinals[ident]=ordinal;body=D._body(root,row)
            previous[ident]=D.validate_lineage_version(row,body,ident,previous.get(ident),requests)
        if len(rows)!=read_rows:_fail('HANDOVER_ROW_DRIFT')
    expected={e['reference']['identity']['id']:e for e in header['endpoints']}
    if len(expected)!=len(header['endpoints']) or set(previous)!=set(expected):_fail('INVALID_LINEAGE_TERMINAL')
    for ident,version in previous.items():
        item=expected[ident]
        if version!=item['reference']['version']['definition_revision'] or ordinals[ident]!=item['known']:_fail('INVALID_LINEAGE_TERMINAL')
    observed={'files':len(files)+2,'rows':len(rows),'bytes':sum(p.stat().st_size for p in root.rglob('*') if p.is_file())}
    # Other selected ART rows are accounted independently in the pinned header.
    talk=root/'contract/talk.jsonl';other_rows=0
    if talk.exists():
        with talk.open('rb') as stream:
            for raw in stream:
                if len(raw)>CELL_BYTES:_fail('INVALID_INVENTORY')
                item=json.loads(raw,object_pairs_hook=D.W._unique)
                other_rows+=item.get('record')=='writing-artifact'
    observed['rows']+=other_rows
    if observed!=header['counts'] or any(observed[k]>header['budgets']['max_'+k] for k in observed):_fail('TOTAL_BUDGET')
    return {'state':'COMPLETE_MATCH','schema_version':SCHEMA,'destination':str(root),'intent':header['intent'],'counts':observed,
        'receipt_sha256':C._sha((root/_H().MANIFEST).read_bytes()),'project':header['project'],
        'definitions':[{'reference':e['reference'],'versions':e['known'],'history_read':D.handle(e['reference']['identity']['id'],e['reference']['version']['definition_revision'],facet='history-page')} for e in header['endpoints']],
        'origin_reads':0,'providers_started':0,'qualification':header['qualification']}


def _response(root,scope,wire,intent,stage,dest,state):
    from laplace.work import project_work_navigation as N
    staged_files=_stage_files(stage)
    checkpoint=canonical_digest(state);payload={k:copy.deepcopy(v) for k,v in wire.items() if k!='source_scope_id'}
    value={'schema_version':SCHEMA,'state':'PARTIAL','terminal':False,'intent':intent,'destination':str(dest),'checkpoint':checkpoint,
        'progress':{k:state[k] for k in ('phase','row_cursor','cells')},'last_cell':state.get('last_cell'),
        'resources':{'cell_rows':wire['cell_rows'],'cell_bytes':wire['cell_bytes'],'copy_buffer_bytes':wire['cell_bytes'],'hash_buffer_bytes':COPY_BUFFER,'decoded_body_limit_bytes':D.MAX_BODY,'max_staged_bytes':wire['max_staged_bytes'],
            'staged_bytes':sum(i['bytes'] for i in staged_files.values()),'staged_files':len(staged_files),
            'staged_peak_bytes':max(state.get('peak_staged_bytes',0),(_IO.get() or {}).get('staged_peak_bytes',0)),'capture_max_bytes':wire['capture_max_bytes'],'metadata_max_rows':wire['metadata_max_rows'],
            'qualification':'Capture/index/selected-row validation, progress verification and inventory hashing are charged separately from delivered/copied cell payload. Cold capture and inspection can remain linear; no hard realtime or fixed RSS claim.'},
        'inspect':_H().object_handle(wire.get('project'),{**payload,'action':'inspect'}),
        'continue':_H().object_handle(wire.get('project'),{**payload,'action':'continue','expected_checkpoint':checkpoint}),
        'qualification':'Verified quiescent staged progress only. No recipient directory has been published. Continue is an explicit author decision.'}
    if N.emitted(value)>N.line():_fail('LINEAGE_RESPONSE_BOUND')
    return value


@contextmanager
def _stage_lock(stage,readonly):
    from filelock import FileLock,Timeout
    lock_path=Path(str(stage)+'.lock')
    if lock_path.is_symlink() or lock_path.exists() and (not lock_path.is_file() or lock_path.stat().st_size!=0):raise Timeout(str(stage))
    if not readonly:
        with FileLock(str(stage)+'.lock',timeout=0):yield
        return
    import fcntl
    try:stream=Path(str(stage)+'.lock').open('rb')
    except OSError:raise Timeout(str(stage))
    with stream:
        try:fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Timeout(str(stage))
        try:yield
        finally:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def _request(root,scope,payload,*,door):
    started=time.monotonic();root=Path(root).resolve();wire,intent,stage,dest=_wire(root,scope,payload,door)
    _STAGE.set((stage,wire['max_staged_bytes']));deadline=started+wire['cell_seconds']
    if dest.exists():
        try:return inspect(dest,expected_intent=intent)
        except (ValueError,OSError,KeyError,TypeError):return {'state':'UNKNOWN','destination':str(dest),'reason':'Occupied or incomplete destination; no replacement/continuation is admitted.'}
    if not stage.exists() and payload['action']=='inspect':return {'state':'NONE','terminal':False,'destination':str(dest),'reason':'Neither exact stage nor completed destination is visible. Effect is unknown; absence grants no retry.'}
    from filelock import FileLock,Timeout
    # A supported pure preparation banks no stage. Its issued original effect
    # wire includes the exact observed cut/basis before the first effect POST.
    if payload['action']=='request':
        plan=_plan(root,scope,wire);offered={k:v for k,v in wire.items() if k!='source_scope_id'}
        offered['expected_lineage_basis']=plan['basis'];offered['action']='export'
        _new_wire,new_intent,_new_stage,_dest=_wire(root,scope,offered,door)
        result={'schema_version':SCHEMA,'state':'PREPARED','effect':'none','intent':new_intent,'endpoints':plan['public']['endpoints'],
            'resources':plan['public'],'export':_H().object_handle(wire.get('project'),offered),
            'inspect':_H().object_handle(wire.get('project'),{**offered,'action':'inspect'}),
            'qualification':'Explicit next Export retains this exact original wire/cut. No stage, recipient or share effect exists yet.'}
        from laplace.work import project_work_navigation as N
        if N.emitted(result)>N.line():_fail('LINEAGE_RESPONSE_BOUND')
        return result
    if not wire.get('expected_lineage_basis'):_fail('ORIGINAL_PREPARED_BASIS_REQUIRED')
    try:
        # Outside the candidate: never published or included in inventory.
        with _stage_lock(stage,payload['action']=='inspect' or payload['action']=='export' and stage.exists()):
            if dest.exists():
                try:return inspect(dest,expected_intent=intent)
                except (ValueError,OSError,KeyError,TypeError):return {'state':'UNKNOWN','destination':str(dest),'reason':'Destination changed during original-request observation; no continuation.'}
            if stage.exists():
                try:
                    if stage.is_symlink():_fail('STAGE_CUSTODY_UNKNOWN')
                    held=_json(stage/'intent.json')
                    if held!={'intent':intent,'wire':wire}:_fail('STAGE_CUSTODY_UNKNOWN')
                    state=_verify_stage(stage,intent,wire)
                except (OSError,ValueError,TypeError,KeyError):return {'state':'UNKNOWN','intent':intent,'reason':'Exact stage is incomplete, changed or unverified; no effect continuation.'}
                if payload['action']=='continue' and payload.get('expected_checkpoint')!=canonical_digest(state):_fail('CHANGED_CHECKPOINT')
            else:
                if payload['action']!='export':return {'state':'UNKNOWN','intent':intent,'reason':'Original stage is absent; no replacement continuation.'}
                state=None
            observing=payload['action']=='inspect' or payload['action']=='export' and state is not None
            with ExitStack() as locks:
                if not observing:_locks(root,wire,locks)
                try:plan=_plan(root,scope,wire)
                except (ValueError,OSError) as exc:
                    if state is not None:return {'state':'CHANGED_INPUT','intent':intent,'reason':str(exc),'continue':None}
                    raise
                if wire['expected_lineage_basis']!=plan['basis']:return {'state':'CHANGED_INPUT','intent':intent,'reason':'Prepared source/cut changed. No new stage or continuation admitted.'}
                if time.monotonic()>=deadline and not observing:_fail('CELL_DEADLINE_NO_PROGRESS')
                if state is None:
                    stage.mkdir();_write(stage/'intent.json',_encoded({'intent':intent,'wire':wire}));(stage/'parts').mkdir();(stage/'payload').mkdir()
                    state=_checkpoint(stage,{'intent':intent,'plan_basis':plan['basis'],'phase':'capture','row_cursor':0,'cells':0,'body_paths':[]})
                if state['plan_basis']!=plan['basis']:return {'state':'CHANGED_INPUT','intent':intent,'reason':'Selected source/custody changed; original stage preserved and no continuation admitted.'}
                try:_verify_progress(root,stage,plan,wire,state)
                except (OSError,ValueError,KeyError,TypeError):return {'state':'UNKNOWN','intent':intent,'reason':'Stage progress does not prove its exact source-bound phase or copied payload; no continuation.'}
                if observing:return _response(root,scope,wire,intent,stage,dest,state)
                if state['phase']=='capture':state=_capture_cell(root,stage,plan,wire,state,deadline)
                elif state['phase']=='assemble':state=_assemble_cell(root,stage,plan,wire,state,deadline)
                elif state['phase']=='inventory':state=_inventory_cell(stage,plan,wire,state,deadline)
                elif state['phase']=='publish':
                    # Re-hash exact selected raw spans; selected body file stamps
                    # bind the already verified bytes through this lock boundary.
                    final=_plan(root,scope,wire,rehash=True)
                    if final['basis']!=state['plan_basis']:_fail('CHANGED_INPUT')
                    header,raw=_header(stage,plan,wire,intent);_write(stage/'payload'/_H().MANIFEST,raw)
                    result=inspect(stage/'payload',expected_intent=intent)
                    result['staging_accounting']={'peak_file_bytes':max(state.get('peak_staged_bytes',0),(_IO.get() or {}).get('staged_peak_bytes',0)),
                        'limit_file_bytes':wire['max_staged_bytes'],'qualification':'Observed file-byte peak, including immutable parts, payload and checkpoint temp. Filesystem block/metadata allocation and RSS are not this number.'}
                    if sum(r['bytes'] for r in _stage_files(stage).values())>wire['max_staged_bytes']:_fail('STAGED_BYTE_BOUND')
                    actual=_stage_files(stage);expected={**state['files'],'payload/'+_H().MANIFEST:{'bytes':len(raw),'sha256':C._sha(raw)}}
                    if {p:r for p,r in actual.items() if p!='checkpoint.json'}!=expected:_fail('STAGE_CUSTODY_UNKNOWN')
                    if time.monotonic()>=deadline:_fail('CELL_DEADLINE_BEFORE_PUBLICATION',effect='none; candidate retained but uncheckpointed, inspect original request')
                    _H()._publish(stage/'payload',dest)
                    outer={p:r for p,r in _stage_files(stage).items() if p!='checkpoint.json'}
                    if outer!={p:r for p,r in state['files'].items() if not p.startswith('payload/')}:
                        return {**result,'destination':str(dest),'state':'COMPLETE','terminal':True,'scratch_cleanup':'UNKNOWN; changed outer scratch preserved'}
                    shutil.rmtree(stage)
                    return {**result,'destination':str(dest),'state':'COMPLETE','terminal':True}
                else:_fail('STAGE_CUSTODY_UNKNOWN')
                for frame in plan['frames']:R.finish(frame)
                if sum(r['bytes'] for r in _stage_files(stage).values())>wire['max_staged_bytes']:_fail('STAGED_BYTE_BOUND')
                state=_checkpoint(stage,state)
                return _response(root,scope,wire,intent,stage,dest,state)
    except Timeout:return {'state':'UNKNOWN','intent':intent,'reason':'Exact stage is busy; no effect continuation.'}


def request(root,scope,payload,*,door):
    """One bounded demand with truthful cumulative I/O, not an O(delta) claim."""
    if not isinstance(scope,O.Scope) or scope.kind!='owned-workspace' or door.get('origin') not in {'human','sdk'}:_fail('EXPLICIT_AUTHOR_EXPORT_SELECTION_REQUIRED')
    metrics={};token=_IO.set(metrics);stage_token=_STAGE.set(None);start=time.monotonic();before=R.stats(root)
    try:
        result=_request(root,scope,payload,door=door);after=R.stats(root)
        result['accounting']={'observed_work_bytes':dict(metrics),'capture_delta':{k:after.get(k,0)-before.get(k,0) for k in
            ('bytes_read','rows_seen','selected_bytes_read','index_anchor_bytes','capture_body_bytes')},
            'elapsed_seconds':time.monotonic()-start,
            'qualification':'Hash/inspection bytes and selected capture are separately charged. Semantic body bytes count the returned canonical value, not undocumented body-store internal I/O. Payload cell bytes are not total I/O. Deadline checks are safe-boundary checks, not hard realtime; no fixed RSS claim.'}
        from laplace.work import project_work_navigation as N
        if N.emitted(result)>N.line():_fail('LINEAGE_RESPONSE_BOUND',effect='Inspect the exact original request; a cell may already be retained.')
        return result
    finally:_IO.reset(token);_STAGE.reset(stage_token)
