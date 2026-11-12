"""Public exact history/lineage continuation. No execution/provider/live state."""
import copy,json
from pathlib import Path
import pytest
from laplace.pipeline import workflow_definitions as D,workflow as W,workflow_definition_records as R
from laplace.work import owner_discovery as O,project_work_navigation as N

@pytest.fixture(autouse=True)
def passive_catalogue(monkeypatch):
    from laplace.writing import provider_catalogue
    monkeypatch.setattr(provider_catalogue,'provider_catalogue',lambda *a,**k:{'schema_version':'laplace.provider-catalogue/1','observed_at':99999999999,'providers':[{'id':'codex','available':False,'models':[]}]})

def scene(root,count=41,width=27000,*,project=False):
    root.mkdir(parents=True,exist_ok=True);versions=[];scope=O.project_scope('book','sdk') if project else O.owned_workspace('sdk')
    body={'schema_version':D.SCHEMA,'title':'Public history','description':'Ω'*(width//2),'settings':{},'steps':[{'id':'one','title':'One','assignment':{'role':'builder','instructions':'Retain; no execution.','settings':{}}}],'edges':[]}
    for i in range(count):
        body=copy.deepcopy(body);body['title']='Public version '+str(i+1);body['description']='Ω'*(100 if i==0 else width//2)
        versions.append(D.save(root,scope,{'request_id':'public-history-'+str(i),'expected_revision':versions[-1]['version'] if versions else None,**({'definition_id':versions[0]['definition_id']} if versions else {}),'definition':body}))
    return scope,versions

def follow(root,scope,handle):return D.read(root,scope,handle['request'])

def test_all_history_metadata_bodyless_exact_cut_and_readonly_body(tmp_path,monkeypatch):
    scope,versions=scene(tmp_path);ident=versions[0]['definition_id'];head=versions[-1]['version']
    original=D._body
    monkeypatch.setattr(D,'_body',lambda *a:pytest.fail('metadata history must not read bodies'))
    rows=[];page=D.read(tmp_path,scope,{'definition_id':ident,'facet':'history-page','limit':8})
    first=page;cut=page['cut'];total=page['known']
    while True:
        assert page['cut']==cut and page['known']==41 and page['body_verification']=='NOT_INSPECTED';rows+=page['items']
        assert N.emitted(page)<=N.line()
        if not page['next_read']:break
        page=follow(tmp_path,scope,page['next_read'])
    assert [x['ordinal'] for x in rows]==list(range(41,0,-1))
    assert [x['version'] for x in rows]==[x['version'] for x in reversed(versions)]
    assert page['at_end'] and page['returned']<total
    monkeypatch.setattr(D,'_body',original)
    # Old small version fits the unchanged owner line; later large bodies are
    # not opened merely to discover complete version metadata.
    body=follow(tmp_path,scope,rows[-1]['read'])
    assert body['version']==versions[0]['version'] and body['read_only'] and body['currentness']=='HISTORICAL'
    assert body['definition']==versions[0]['definition'] and body['object_read']['native']['payload']['request']['reference']==versions[0]['reference']
    assert len(versions)>32 and sum(len(W.canonical(x['definition'])) for x in versions)>1_000_000
    with pytest.raises(D.Refused,match='EXPORT_BOUND'):D.read(tmp_path,scope,{'reference':versions[-1]['reference'],'facet':'export'})
    (tmp_path/'history-proof.json').write_text(json.dumps({'first':first,'last':page,'old_body':body,'versions':len(rows),'body_bytes':sum(len(W.canonical(x['definition'])) for x in versions)},indent=2))

def test_history_valid_append_scope_limits_and_corrupt_cut(tmp_path,monkeypatch):
    scope,versions=scene(tmp_path,5,200);ident=versions[0]['definition_id']
    page=D.read(tmp_path,scope,{'definition_id':ident,'facet':'history-page','limit':2});held=page['next_read']
    D.save(tmp_path,scope,{'request_id':'later-head','definition_id':ident,'expected_revision':versions[-1]['version'],'definition':{**versions[-1]['definition'],'title':'Later'}})
    later=follow(tmp_path,scope,held);assert later['cut']==page['cut'] and later['known']==5
    with pytest.raises(D.Refused,match='HISTORY_CUT_CHANGED'):D.read(tmp_path,scope,{**held['request'],'as_of':'bad'})
    with pytest.raises(D.Refused,match='CAPTURE_RESOURCE_BOUND'):D.read(tmp_path,scope,{'definition_id':ident,'facet':'history-page','capture_max_bytes':1})
    R._INDEXES.clear()
    with pytest.raises(D.Refused,match='CAPTURE_RESOURCE_BOUND'):D.read(tmp_path,scope,{'definition_id':ident,'facet':'history-page','metadata_max_rows':2})
    monkeypatch.setattr(R,'_index',lambda *a,**k:pytest.fail('foreign admission must precede capture'))
    with pytest.raises(D.Refused,match='NOT_IN_SCOPE'):D.read(tmp_path,None,{'definition_id':ident,'facet':'history-page'})

def test_saved_small_body_and_v1_compatibility(tmp_path):
    scope,versions=scene(tmp_path,3,100);old=versions[0];ident=old['definition_id']
    preview=D.read(tmp_path,scope,{'definition_id':ident,'facet':'history'})
    assert len(preview['history'])==3 and preview['history_read']['request']['facet']=='history-page'
    page=follow(tmp_path,scope,preview['history_read']);body=follow(tmp_path,scope,page['items'][-1]['read'])
    assert body['version']==old['version'] and body['definition']==old['definition']
    package=D.read(tmp_path,scope,{'reference':old['reference'],'facet':'export'})
    assert D.validate_export(package)==package and len(package['versions'])==1
    assert D.read(tmp_path,scope,{} )['definitions'][0]['history_read']['request']['facet']=='history-page'

def test_library_custody_scope_is_distinct_from_actual_caller(tmp_path):
    for project in (False,True):
        root=tmp_path/('project' if project else 'workspace')
        _,versions=scene(root,1,100,project=project)
        caller=O.owned_workspace('sdk')
        listing=D.read(root,caller,{})
        item=listing['definitions'][0]
        assert listing['scope']==caller.public()
        assert item['scope']==versions[0]['scope']
        history=follow(root,caller,item['history_read'])
        assert history['scope']==item['scope']
        item['scope']['kind']='altered-local-copy'
        assert D.read(root,caller,{})['definitions'][0]['scope']==versions[0]['scope']

from laplace.projects import project_handover as H,project_handover_lineage as T,project_data as C


def transfer(root,scope,payload):return H.object_request(root,scope,payload,door={'origin':'sdk'})


def planned_transfer(root,scope,reference,destination,**changes):
    raw={'action':'request','definition_transport':'lineage-v2','request_id':'public-transfer','definitions':[reference],
        'destination':str(destination),'max_files':200,'max_rows':200,'max_bytes':8_000_000,**changes}
    result=transfer(root,scope,raw)
    assert result['state']=='PREPARED' and result['effect']=='none'
    return result['export']['sdk']['payload']


def finish_transfer(root,scope,wire):
    responses=[];value=transfer(root,scope,wire)
    while value['state']=='PARTIAL':
        responses.append(value)
        assert value['last_cell']['versions']<=wire.get('cell_rows',32)
        assert value['last_cell']['payload_bytes']<=wire.get('cell_bytes',1_000_000)
        assert value['resources']['staged_peak_bytes']<=wire.get('max_staged_bytes',3*wire['max_bytes'])
        assert value['resources']['copy_buffer_bytes']<=wire.get('cell_bytes',1_000_000)
        assert not Path(wire['destination']).exists()
        value=transfer(root,scope,value['continue']['sdk']['payload'])
        assert len(responses)<100
    assert value['state']=='COMPLETE';return value,responses

def test_prepared_first_export_has_exact_observation_without_retry(tmp_path):
    root=tmp_path/'origin';scope,versions=scene(root,3,100)
    payload={'action':'request','definition_transport':'lineage-v2','request_id':'public-first-ack',
        'definitions':[versions[-1]['reference']],'destination':str(tmp_path/'recipient'),
        'max_files':100,'max_rows':100,'max_bytes':2_000_000,'cell_rows':1}
    prepared=transfer(root,scope,payload)
    export=prepared['export']['sdk']['payload'];inspect=prepared['inspect']['sdk']['payload']
    assert inspect=={**export,'action':'inspect'}
    before=transfer(root,scope,inspect)
    assert before['state']=='NONE' and not before['terminal']
    assert not list(tmp_path.glob('.laplace-handover-*'))
    first=transfer(root,scope,export)
    assert first['state']=='PARTIAL'
    observed=transfer(root,scope,inspect)
    assert observed['state']=='PARTIAL' and observed['intent']==prepared['intent']
    assert observed['progress']==first['progress'] and observed['checkpoint']==first['checkpoint']
    from laplace.writing import delivery
    with delivery.planned(line=1000):
        with pytest.raises(H.Refused,match='LINEAGE_RESPONSE_BOUND'):
            transfer(root,scope,{**payload,'request_id':'public-oversized-offer','destination':str(tmp_path/'other')})
    assert not (tmp_path/'recipient').exists() and not (tmp_path/'other').exists()


def test_v2_complete_workspace_prefix_original_rows_bodies_and_offline_recipient(tmp_path):
    origin=tmp_path/'origin';scope,versions=scene(origin,41,27000);destination=tmp_path/'recipient'
    # Select the original terminal, then permit a genuinely later valid head.
    wire=planned_transfer(origin,scope,versions[-1]['reference'],destination)
    D.save(origin,scope,{'request_id':'later-after-plan','definition_id':versions[0]['definition_id'],'expected_revision':versions[-1]['version'],
        'definition':{**versions[-1]['definition'],'title':'Later origin head'}})
    result,responses=finish_transfer(origin,scope,wire)
    assert len(responses)>3 and result['counts']['rows']==41
    assert not (destination/'registry_projects.json').exists()
    assert not list(destination.rglob('checkpoint*')) and not list(destination.rglob('*.raw'))
    assert (destination/W.LEDGER).read_bytes()==b''.join((origin/W.LEDGER).read_bytes().splitlines(keepends=True)[:41])
    for version in versions:
        digest=D.W.digest(D.W.canonical(version['definition'])).removeprefix('sha256:');rel=Path('contract/writing_bodies')/digest[:2]/digest
        assert (origin/rel).read_bytes()==(destination/rel).read_bytes()
    import os
    offline=tmp_path/'offline-origin';os.rename(origin,offline)
    inspected=H.inspect_handover(destination);assert inspected['state']=='COMPLETE_MATCH' and inspected['origin_reads']==0
    value=D.read(destination,scope,{'reference':versions[-1]['reference'],'facet':'history-page'})
    assert value['known']==41 and value['head_at_start']==versions[-1]['version']
    exact=D.read(destination,scope,{'reference':versions[-1]['reference'],'facet':'saved-version'})
    chunks=[];body_pages=[]
    while exact.get('state')=='BODY_PAGE':
        assert N.emitted(exact)<=N.line() and exact['body_page']['offset']==sum(map(len,chunks))
        assert exact['body_page']['sha256']==W.digest(W.canonical(versions[-1]['definition']))
        body_pages.append(exact);chunks.append(exact['content'])
        if not exact['next_body_read']:break
        exact=follow(destination,scope,exact['next_body_read'])
    body=json.loads(''.join(chunks)) if chunks else exact['definition']
    assert body==versions[-1]['definition'] and exact['currentness']=='CURRENT'
    (tmp_path/'v2-proof.json').write_text(json.dumps({'wire':wire,'result':result,'responses':responses,'recipient':inspected,'history':value,'saved_body_pages':body_pages},indent=2))


def test_v2_lost_first_ack_pure_inspection_changed_checkpoint_and_stage_unknown(tmp_path):
    root=tmp_path/'origin';scope,versions=scene(root,6,200);wire=planned_transfer(root,scope,versions[-1]['reference'],tmp_path/'recipient',cell_rows=2)
    first=transfer(root,scope,wire);assert first['state']=='PARTIAL'
    # Reusing original wire is observation, never an implicit next cell.
    repeated=transfer(root,scope,wire);assert repeated['checkpoint']==first['checkpoint']
    inspected=transfer(root,scope,{**wire,'action':'inspect'});assert inspected['checkpoint']==first['checkpoint']
    with pytest.raises(H.Refused,match='CHANGED_CHECKPOINT'):transfer(root,scope,{**wire,'action':'continue','expected_checkpoint':'sha256:'+'1'*64})
    _wire,intent,stage,dest=T._wire(root,scope,wire,{'origin':'sdk'})
    (stage/'foreign.part').write_text('public unexpected marker')
    unknown=transfer(root,scope,{**wire,'action':'inspect'});assert unknown['state']=='UNKNOWN' and 'continue' not in unknown
    assert not dest.exists() and (stage/'foreign.part').exists()


def test_v2_source_change_scope_total_and_v1_defaults(tmp_path,monkeypatch):
    root=tmp_path/'origin';scope,versions=scene(root,4,200);wire=planned_transfer(root,scope,versions[-1]['reference'],tmp_path/'recipient',cell_rows=1)
    partial=transfer(root,scope,wire)
    digest=D.W.digest(D.W.canonical(versions[0]['definition'])).removeprefix('sha256:');body=root/'contract/writing_bodies'/digest[:2]/digest
    body.write_bytes(b'x'*body.stat().st_size)
    changed=transfer(root,scope,partial['continue']['sdk']['payload']);assert changed['state']=='CHANGED_INPUT' and 'continue' not in changed
    replayed=transfer(root,scope,wire);assert replayed['state']=='CHANGED_INPUT' and not replayed.get('continue')
    with pytest.raises(H.Refused,match='EXPLICIT_AUTHOR'):transfer(root,O.project_scope('foreign','native'),wire)
    with pytest.raises(H.Refused,match='TOTAL_BUDGET'):planned_transfer(root,scope,versions[-1]['reference'],tmp_path/'too-small',max_rows=2)
    assert not (tmp_path/'too-small').exists()
    # V1 validation remains a separate exact small-package contract.
    with pytest.raises(D.Refused,match='INVALID_EXPORT'):D.validate_export({'schema_version':'laplace.workflow-definition-export/2','versions':[]})


def test_v2_project_selected_handover_and_existing_recipient_owners(tmp_path):
    from laplace.projects import library
    root=tmp_path/'origin';root.mkdir();(root/'registry_projects.json').write_text('{"projects":[]}')
    assert library.create({'name':'book','title':'Public selected project','kind':'general'},root)[0]==201
    _project,versions=scene(root,35,100,project=True);scope=O.owned_workspace('sdk')
    prepared=H.object_request(root,scope,{'action':'prepare','project':'book','request_id':'public-object',
        'entries':[{'class':'included','reference':versions[-1]['reference'],'expected_basis':versions[-1]['version'],'permit_export':True}],
        'max_files':100,'max_rows':100,'max_bytes':5_000_000},door={'origin':'sdk'})
    assert any(a['id']=='export-lineage' for a in prepared['actions'])
    plan=transfer(root,scope,{'action':'request','definition_transport':'lineage-v2','project':'book','reference':prepared['reference'],
        'expected_basis':prepared['basis'],'request_id':'public-project-export','destination':str(tmp_path/'recipient'),
        'max_files':100,'max_rows':100,'max_bytes':5_000_000})
    result,responses=finish_transfer(root,scope,plan['export']['sdk']['payload'])
    recipient=tmp_path/'recipient';assert result['project']=='book' and (recipient/'registry_projects.json').is_file()
    import os
    os.rename(root,tmp_path/'offline')
    assert H.inspect_handover(recipient)['state']=='COMPLETE_MATCH'
    value=D.read(recipient,O.project_scope('book','native'),{'reference':versions[-1]['reference'],'facet':'history-page','project_lens':'book'})
    assert value['known']==35
    (tmp_path/'project-proof.json').write_text(json.dumps({'prepared':prepared,'plan':plan,'result':result,'responses':responses,'recipient_history':value},indent=2))


def test_v2_busy_inspection_no_creation_and_inventory_exact_set(tmp_path):
    from filelock import FileLock
    root=tmp_path/'origin';scope,versions=scene(root,3,100);wire=planned_transfer(root,scope,versions[-1]['reference'],tmp_path/'recipient',cell_rows=1)
    first=transfer(root,scope,wire);_w,intent,stage,dest=T._wire(root,scope,wire,{'origin':'sdk'})
    with FileLock(str(stage)+'.lock',timeout=0):
        busy=transfer(root,scope,{**wire,'action':'inspect'});assert busy['state']=='UNKNOWN' and 'continue' not in busy
    before={p: p.stat().st_mtime_ns for p in [*stage.rglob('*'),root/'contract/workflow-definitions.lock'] if p.is_file()}
    same=transfer(root,scope,{**wire,'action':'inspect'});assert same['checkpoint']==first['checkpoint']
    assert all(p.stat().st_mtime_ns==stamp for p,stamp in before.items())
    result,_=finish_transfer(root,scope,wire)
    (dest/'unexpected-public-file.txt').write_text('Not selected')
    with pytest.raises(H.Refused,match='FILE_SET_CHANGED'):H.inspect_handover(dest)


def test_v2_perfile_cell_metadata_body_bounds_before_effects(tmp_path,monkeypatch):
    root=tmp_path/'origin';scope,versions=scene(root,3,100);destination=tmp_path/'recipient'
    with pytest.raises(H.Refused,match='STAGED_BYTE_BOUND'):planned_transfer(root,scope,versions[-1]['reference'],destination,max_staged_bytes=1)
    wire=planned_transfer(root,scope,versions[-1]['reference'],destination,cell_bytes=10)
    with pytest.raises(H.Refused,match='CELL_ITEM_BOUND'):transfer(root,scope,wire)
    assert not destination.exists()
    with monkeypatch.context() as m:
        m.setattr(H,'PER_FILE',1000)
        with pytest.raises(H.Refused,match='FILE_BOUND'):planned_transfer(root,scope,versions[-1]['reference'],tmp_path/'too-large-file')
    assert H.PER_FILE==100*1024*1024 and D.MAX_BODY==200_000
    digest=D.W.digest(D.W.canonical(versions[0]['definition'])).removeprefix('sha256:');body=root/'contract/writing_bodies'/digest[:2]/digest
    body.write_bytes(b'x'*200001)
    with pytest.raises(H.Refused,match='UNAVAILABLE_VERSION'):planned_transfer(root,scope,versions[-1]['reference'],tmp_path/'oversized-body')
    body.unlink()
    with pytest.raises(H.Refused,match='UNAVAILABLE_VERSION'):planned_transfer(root,scope,versions[-1]['reference'],tmp_path/'missing-body')


def test_v2_interrupted_cell_unknown_and_lost_final_ack(tmp_path,monkeypatch):
    root=tmp_path/'origin';scope,versions=scene(root,4,100);wire=planned_transfer(root,scope,versions[-1]['reference'],tmp_path/'recipient',cell_rows=1)
    first=transfer(root,scope,wire);original=T._checkpoint
    with monkeypatch.context() as m:
        m.setattr(T,'_checkpoint',lambda *a:(_ for _ in ()).throw(RuntimeError('public interruption after immutable part write')))
        with pytest.raises(RuntimeError,match='public interruption'):transfer(root,scope,first['continue']['sdk']['payload'])
    unknown=transfer(root,scope,{**wire,'action':'inspect'});assert unknown['state']=='UNKNOWN' and 'continue' not in unknown
    wire2=planned_transfer(root,scope,versions[-1]['reference'],tmp_path/'other-recipient',request_id='second-explicit-decision',cell_rows=32)
    value=transfer(root,scope,wire2)
    while value['progress']['phase']!='publish':value=transfer(root,scope,value['continue']['sdk']['payload'])
    publish=H._publish
    def lost_ack(stage,dest):publish(stage,dest);raise RuntimeError('public lost final ack')
    with monkeypatch.context() as m:
        m.setattr(H,'_publish',lost_ack)
        with pytest.raises(RuntimeError,match='lost final ack'):transfer(root,scope,value['continue']['sdk']['payload'])
    matched=transfer(root,scope,{**wire2,'action':'inspect'});assert matched['state']=='COMPLETE_MATCH' and matched['counts']['rows']==4


@pytest.mark.parametrize('bad',['gap','reorder','duplicate','request-reuse','bool-ordinal'])
def test_v2_selfconsistent_inventory_cannot_mask_invalid_crosscell_chain(tmp_path,bad):
    root=tmp_path/'origin';scope,versions=scene(root,5,100);wire=planned_transfer(root,scope,versions[-1]['reference'],tmp_path/'recipient',cell_rows=1)
    finish_transfer(root,scope,wire);dest=tmp_path/'recipient';journal=dest/W.LEDGER
    rows=journal.read_bytes().splitlines(keepends=True);inventory=[json.loads(s) for s in (dest/T.INVENTORY).read_bytes().splitlines()]
    metas=[x for x in inventory if x['kind']=='definition-row'];files=[x for x in inventory if x['kind']=='file']
    if bad=='gap':rows.pop(1);metas.pop(1)
    elif bad=='reorder':rows[0],rows[1]=rows[1],rows[0];metas[0],metas[1]=metas[1],metas[0]
    elif bad=='duplicate':rows.insert(1,rows[0]);metas.insert(1,copy.deepcopy(metas[0]))
    elif bad=='request-reuse':
        value=json.loads(rows[2]);value['request_id']=json.loads(rows[0])['request_id'];value['receipt']['request_id']=value['request_id'];rows[2]=W.canonical(value)+b'\n'
    for n,(raw,meta) in enumerate(zip(rows,metas),1):meta.update(ordinal=n,physical_order=n,raw_line_sha256=C._sha(raw))
    if bad=='bool-ordinal':metas[0]['ordinal']=True
    journal.write_bytes(b''.join(rows))
    for item in files:
        if item['path']==W.LEDGER:item.update(T._file(journal))
    raw=b''.join(H.encoded(x) for x in files+metas);(dest/T.INVENTORY).write_bytes(raw)
    header=json.loads((dest/H.MANIFEST).read_bytes());header['inventory'].update(sha256=C._sha(raw),bytes=len(raw),entries=len(files)+len(metas));header['endpoints'][0]['known']=len(rows)
    # Count fixed point is deliberately consistent too; the actual chain must
    # still refuse, independently of transport hashes and complete-file shape.
    base=sum(p.stat().st_size for p in dest.rglob('*') if p.is_file() and p.name!=H.MANIFEST)
    for _ in range(8):
        header['counts']['rows']=len(rows);raw=H.encoded(header);total=base+len(raw)
        if header['counts']['bytes']==total:break
        header['counts']['bytes']=total
    (dest/H.MANIFEST).write_bytes(H.encoded(header))
    with pytest.raises((H.Refused,D.Refused),match='CHAIN|REQUEST_DUPLICATE|INVENTORY|ROW_DRIFT'):H.inspect_handover(dest)


def test_v2_foreign_lock_and_symlink_controls_never_follow_body(tmp_path,monkeypatch):
    root=tmp_path/'origin';scope,versions=scene(root,3,100);wire=planned_transfer(root,scope,versions[-1]['reference'],tmp_path/'recipient',cell_rows=1)
    partial=transfer(root,scope,wire);_w,_intent,stage,_dest=T._wire(root,scope,wire,{'origin':'sdk'})
    marker=tmp_path/'public-marker';marker.write_text('Public foreign sentinel; never an owner control')
    intent=stage/'intent.json';original=intent.read_bytes();intent.unlink();intent.symlink_to(marker)
    unknown=transfer(root,scope,{**wire,'action':'inspect'});assert unknown['state']=='UNKNOWN'
    intent.unlink();intent.write_bytes(original)
    lock=Path(str(stage)+'.lock');lock.unlink();lock.symlink_to(marker)
    unknown=transfer(root,scope,{**wire,'action':'inspect'});assert unknown['state']=='UNKNOWN' and marker.read_text().startswith('Public foreign')
    # Scope admission precedes even the process-local owner index/counters.
    monkeypatch.setattr(R,'stats',lambda *a:pytest.fail('No foreign scope metadata lookup'))
    with pytest.raises(H.Refused,match='EXPLICIT_AUTHOR'):transfer(root,O.project_scope('foreign','native'),wire)


def test_saved_body_pages_keep_original_utf8_spacing_and_pin(tmp_path):
    scope,versions=scene(tmp_path,1,100);journal=tmp_path/W.LEDGER
    row=json.loads(journal.read_bytes());body=versions[0]['definition']
    raw=json.dumps(body,indent=2,ensure_ascii=False).encode('utf-8');handle=W.digest(raw);digest=handle[7:]
    path=tmp_path/'contract/writing_bodies'/digest[:2]/digest;path.parent.mkdir(exist_ok=True);path.write_bytes(raw)
    row['body_handle']=handle;row['receipt']['body_handle']=handle;journal.write_bytes(W.canonical(row)+b'\n')
    assert D._body(tmp_path,row)==body
    page=D.read(tmp_path,scope,{'reference':versions[0]['reference'],'facet':'saved-version','body_offset':0,'body_limit':8000})
    assert page['body_page']['at_end'] and page['content'].encode('utf-8')==raw
    assert W.digest(page['content'].encode('utf-8'))==page['body_page']['sha256']==handle


def test_v2_prepared_source_basis_does_not_move_to_identical_other_root(tmp_path):
    import os
    root=tmp_path/'origin';scope,versions=scene(root,2,100);other=tmp_path/'other';other.mkdir()
    for source in root.rglob('*'):
        target=other/source.relative_to(root)
        if source.is_dir():target.mkdir(exist_ok=True)
        elif source.is_file():target.parent.mkdir(parents=True,exist_ok=True);os.link(source,target)
    wire=planned_transfer(root,scope,versions[-1]['reference'],tmp_path/'recipient',cell_rows=1)
    changed=transfer(other,scope,wire)
    assert changed['state']=='CHANGED_INPUT' and not changed.get('continue')
    assert not (tmp_path/'recipient').exists()


@pytest.mark.parametrize('bad',['phase','bool-cursor','forged-row-count','premature-assemble','body-list','missing-lock'])
def test_v2_stage_control_must_prove_its_phase_and_known_lock(tmp_path,bad):
    root=tmp_path/'origin';scope,versions=scene(root,4,100);wire=planned_transfer(root,scope,versions[-1]['reference'],tmp_path/'recipient',cell_rows=1)
    first=transfer(root,scope,wire);_,_,stage,destination=T._wire(root,scope,wire,{'origin':'sdk'})
    checkpoint=stage/'checkpoint.json';value=json.loads(checkpoint.read_bytes())
    if bad=='phase':value['phase']='NOT_A_TRANSFER_PHASE'
    elif bad=='bool-cursor':value['row_cursor']=True
    elif bad=='forged-row-count':value['row_cursor']=4
    elif bad=='premature-assemble':value.update(phase='assemble',row_cursor=4,copy_cursor=0,copy_offset=0)
    elif bad=='body-list':value['body_paths']=[]
    else:Path(str(stage)+'.lock').unlink()
    if bad!='missing-lock':checkpoint.write_bytes(H.encoded(value))
    import hashlib
    def snapshot():return {p.relative_to(stage).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob('*') if p.is_file()}
    before=snapshot()
    for action in ('inspect','export'):
        result=transfer(root,scope,{**wire,'action':action})
        assert result['state']=='UNKNOWN' and not result.get('continue')
        assert before==snapshot() and not destination.exists()
    if bad=='missing-lock':assert not Path(str(stage)+'.lock').exists()


def test_v2_reuses_existing_normalized_output_path_admission(tmp_path,monkeypatch):
    root=tmp_path/'origin';scope,versions=scene(root,2,100)
    seen=[];original=H._validate_output_paths
    def observed(paths):seen.append(list(paths));return original(paths)
    monkeypatch.setattr(H,'_validate_output_paths',observed)
    planned_transfer(root,scope,versions[-1]['reference'],tmp_path/'recipient')
    assert seen and T.INVENTORY in seen[0] and H.MANIFEST in seen[0] and W.LEDGER in seen[0]
    for names in (['Foo.txt','foo.txt'],['a','a/b'],['bad\\name'],['name.']):
        with pytest.raises(H.Refused,match='COLLISION|UNSAFE_OUTPUT_PATH'):H._validate_output_paths(names)


def test_v2_interleaved_prefixes_keep_global_rows_and_share_only_identical_bodies(tmp_path):
    root=tmp_path/'origin';scope,first=scene(root,1,100);body=first[0]['definition']
    second=D.save(root,scope,{'request_id':'other-create','expected_revision':None,'definition':body})
    one=D.save(root,scope,{'request_id':'first-next','definition_id':first[0]['definition_id'],'expected_revision':first[0]['version'],'definition':body})
    two=D.save(root,scope,{'request_id':'other-next','definition_id':second['definition_id'],'expected_revision':second['version'],'definition':body})
    wire=planned_transfer(root,scope,one['reference'],tmp_path/'recipient',definitions=[two['reference'],one['reference']],cell_rows=1)
    result,responses=finish_transfer(root,scope,wire);recipient=tmp_path/'recipient'
    assert result['counts']['rows']==4 and result['counts']['files']==4
    assert (recipient/W.LEDGER).read_bytes()==(root/W.LEDGER).read_bytes()
    assert len([p for p in (recipient/'contract/writing_bodies').rglob('*') if p.is_file()])==1
    for selected in (one,two):
        value=D.read(recipient,scope,{'reference':selected['reference'],'facet':'history-page'})
        assert value['known']==2
