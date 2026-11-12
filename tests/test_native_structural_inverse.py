"""Full stdio MCP transport proof for large lazy structural inverses; no providers."""
import contextlib
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

import pytest
from laplace.web import authoring as authoring_surface
from laplace.work import history as author_history
from laplace.native import tools as writing_tools
from laplace.writing import records as writing_records
from laplace.writing import mutation_attribution
from laplace.writing import turn_reads
from laplace.writing import session_reads
from laplace.core import checkout
from test_manuscript_blocks import _fixture


@contextlib.contextmanager
def mcp(root, project='blocks'):
    writing_records.bank(root, {'record':'writing-session','id':'WS-inverse',
                                  'project':project,'provider':'claude'})
    writing_records.bank(root, {'record':'writing-turn','id':'WT-inverse',
        'session_id':'WS-inverse','project':project,'mode':'work'})
    process=subprocess.Popen([sys.executable,'-B','-m','laplace.native.tools',
        '--root',str(root),'--project',project,'--mode','work','--turn-id','WT-inverse'],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    responses=queue.Queue()
    def collect():
        for line in process.stdout:
            responses.put(json.loads(line))
    thread=threading.Thread(target=collect,daemon=True);thread.start()
    counter=0
    def send(operation,payload=None):
        nonlocal counter
        counter+=1
        fields=operation if isinstance(operation,dict) else {'operation':operation,'payload':payload or {}}
        process.stdin.write(json.dumps({'jsonrpc':'2.0','id':counter,'method':'tools/call',
            'params':{'name':'laplace_project','arguments':fields}})+'\n');process.stdin.flush()
        response=responses.get(timeout=20);assert response['id']==counter and 'error' not in response,response
        value=json.loads(response['result']['content'][0]['text'])
        return value,response['result'].get('isError',False)
    try:
        yield send
    finally:
        process.stdin.close()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        thread.join(timeout=2)
        error=process.stderr.read();process.stdout.close();process.stderr.close()
        assert process.returncode==0,error


def digest(path):return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
def snapshot(source):return tuple((source/name).read_bytes() for name in ('chapter.tex','other.tex','manuscript_spec.json'))
def scan_inputs(root,source):
    paths=[root/'contract/talk.jsonl',source/'feedback/feedback.jsonl']
    return [{'path':str(p.relative_to(root)),'bytes':p.stat().st_size if p.exists() else 0,
             'rows':len(p.read_bytes().splitlines()) if p.exists() else 0} for p in paths]


def test_actual_large_mcp_move_read_undo_read_redo_and_recovery_failure(tmp_path,record_property):
    source,figure=_fixture(tmp_path)
    for name in ('chapter.tex','other.tex'):
        with (source/name).open('a') as stream:stream.write(('% retained unrelated source padding '+'x'*100+'\n')*240)
    spec=source/'manuscript_spec.json';spec.write_text(json.dumps(json.loads(spec.read_text()),indent=2)+'\n')
    original=snapshot(source);cost=[]
    with mcp(tmp_path) as send:
        read,error=send('source',{'files':['chapter.tex'],'line_start':2,'line_end':7});assert not error
        origin=read['sources'][0]
        read,error=send('source',{'files':['other.tex'],'line_start':1,'line_end':1});assert not error
        destination=read['sources'][0]
        moved,error=send('block_change',{'operation':'move','block':{
            'file':origin['file'],'line_start':2,'line_end':7,'before':origin['text'].removesuffix('\n'),
            'expected_source_digest':origin['expected_source_digest']},'destination':{
            'file':destination['file'],'line':1,'before':destination['text'].removesuffix('\n'),
            'expected_source_digest':destination['expected_source_digest']}})
        assert not error and moved['full_response_omitted'] and 'undo' not in moved
        assert moved['undo_ref']==moved['action_receipt']['undo_ref']
        assert moved['next_read']['payload']=={'view':'structural-undo','kind':'block','id':moved['undo_ref']['id']}
        moved_state=snapshot(source);assert figure not in (source/'chapter.tex').read_text()
        failed,error=send('author_history',{**moved['next_read']['payload'],'id':'not-a-record'})
        assert error and 'no completed object change' in failed['error']
        assert snapshot(source)==moved_state  # A failed follow-up read never replays the source effect.
        exact,error=send('author_history',{'view':'record','id':'activity:journal:'+moved['action_receipt']['id']})
        assert not error and exact['structural_undo_read']==moved['next_read']
        assert exact['record']['outcome']['status']=='SUCCEEDED'
        assert 'undo' not in exact['record']['outcome']
        def inverse(result):
            observed=scan_inputs(tmp_path,source);start=time.perf_counter()
            value,error=send(result['next_read']);assert not error,value
            cost.append({'seconds':time.perf_counter()-start,'response_bytes':len(json.dumps(value).encode()),
                         'existing_full_scan_inputs':observed})
            assert value['id']==result['undo_ref']['id'] and value['project']=='blocks'
            return value['undo']
        restored,error=send('block_change',inverse(moved));assert not error,restored
        assert snapshot(source)==original
        redone,error=send('block_change',inverse(restored));assert not error,redone
        assert snapshot(source)==moved_state
        inverse_again=inverse(redone)
        spec_before=(source/'manuscript_spec.json').read_bytes()
        changed_spec=json.loads(spec_before);changed_spec['figure_specs'][0]['section']='elsewhere.tex'
        (source/'manuscript_spec.json').write_text(json.dumps(changed_spec))
        before=snapshot(source);refused,error=send('block_change',inverse_again)
        assert error and 'visual placement changed' in refused['error']
        assert snapshot(source)==before
        (source/'manuscript_spec.json').write_bytes(spec_before)
        # Keep exact guards authoritative after the on-demand read.
        (source/'chapter.tex').write_text((source/'chapter.tex').read_text()+'External edit.\n')
        before=snapshot(source)
        refused,error=send('block_change',inverse_again)
        assert error and 'object changed since this operation' in refused['error']
        assert snapshot(source)==before
    record_property('block_inverse_read_cost',json.dumps(cost))


def test_actual_mcp_section_inverse_and_closed_selector(tmp_path,record_property):
    from test_manuscript_structure import _section_fixture
    from laplace.manuscript import project_structure
    source,chapter,_=_section_fixture(tmp_path);chapter.write_text(chapter.read_text()+('% padding '+'x'*100+'\n')*240)
    before=chapter.read_bytes()
    with mcp(tmp_path,'book') as send:
        created,error=send('section_change',{'operation':'create','source_file':str(chapter.relative_to(tmp_path)),
            'after_line':2,'after_before':'First body.','expected_source_digest':digest(chapter),
            'expected_plan_revision':project_structure.state('book',tmp_path)['revision'],
            'title':'Inserted','kind':'section','section_id':'inserted','parent_id':'first'})
        assert not error,created
        assert created['full_response_omitted'] and created['undo_ref']['kind']=='section'
        start=time.perf_counter();inverse,error=send(created['next_read']);assert not error,inverse
        record_property('section_inverse_read_cost',json.dumps({'seconds':time.perf_counter()-start,
            'response_bytes':len(json.dumps(inverse).encode()),'existing_full_scan_inputs':scan_inputs(tmp_path,source)}))
        current=chapter.read_bytes()
        help_read,error=send('help',{'operation':'author_history'});assert not error
        assert 'structural-undo' in json.dumps(help_read)
        for payload in [dict(created['next_read']['payload'],project='OTHER'),
                        dict(created['next_read']['payload'],kind='invalid'),
                        dict(created['next_read']['payload'],kind='block'),
                        dict(created['next_read']['payload'],id='not-a-record'),
                        dict(created['next_read']['payload'],limit=1),
                        {'view':'structural-undo','kind':'section'},
                        {'view':'record','kind':'section','id':created['undo_ref']['id']}]:
            value,error=send('author_history',payload);assert error,value
        assert chapter.read_bytes()==current and current!=before
        restored,error=send('section_change',inverse['undo']);assert not error,restored
        assert chapter.read_bytes()==before
        redo,error=send(restored['next_read']);assert not error,redo
        redone,error=send('section_change',redo['undo']);assert not error,redone
        assert chapter.read_bytes()==current


def test_structural_shared_reader_http_and_partial_projection(tmp_path,monkeypatch):
    source,figure=_fixture(tmp_path)
    changed=writing_tools.execute(tmp_path,'blocks','work','block_change',{'operation':'delete',
        'block':{'file':'source/chapter.tex','line_start':2,'line_end':7,'before':figure,
                 'expected_source_digest':digest(source/'chapter.tex')}})
    ref=changed['undo_ref'];payload={'view':'structural-undo','kind':'block','id':ref['id']}
    native=author_history.structural_undo('blocks',payload,tmp_path)
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    status,_,body=authoring_surface.handle('/authoring/structural-undo',{
        'project':['blocks'],'kind':['block'],'id':[ref['id']]},'GET',b'')
    assert status==200 and json.loads(body)==native
    for query in [{'project':['blocks'],'kind':['block','section'],'id':[ref['id']]},
                  {'project':['blocks'],'kind':['block'],'id':[ref['id']],'limit':['1']}]:
        assert authoring_surface.handle('/authoring/structural-undo',query,'GET',b'')[0]==409
    for partial in [dict(changed,ok=False),dict(changed,complete=False),dict(changed,undo_ref=None)]:
        # A stale successful summary cannot mint a cure for a partial current result.
        summary=writing_tools._action_summary('blocks','block_change',{},changed)
        compact=writing_tools._compact_write_response('blocks','block_change',{},dict(partial,
            action_receipt=dict(summary,id='ACTION-partial'),padding='x'*20000))
        assert 'next_read' not in compact and 'undo_ref' not in compact
        assert 'undo_ref' not in compact.get('action_receipt',{})


def test_actual_inverse_read_is_historical_not_proposal_or_context_basis(tmp_path,monkeypatch):
    from laplace.pipeline import authoring
    source,figure=_fixture(tmp_path)
    with mcp(tmp_path) as send:
        read,error=send('source',{'files':['chapter.tex'],'line_start':2,'line_end':7})
        assert not error
        selected=read['sources'][0]
        changed,error=send('block_change',{'operation':'delete','block':{
            'file':selected['file'],'line_start':2,'line_end':7,'before':figure,
            'expected_source_digest':selected['expected_source_digest']}})
        assert not error
        handle=author_history.structural_undo_read('blocks',changed['undo_ref'])
        inverse,error=send(handle);assert not error
        observed=session_reads._records(tmp_path)['turns']['WT-inverse']
        inverse_read=next(row for row in observed['tool_reads'].values()
                          if row['id']==inverse['read_receipt']['id'])
        assert mutation_attribution._historical_activity_read('author_history',inverse_read['payload'])
        assert mutation_attribution._read_views('author_history',inverse_read['payload'])==set()
        consulted=mutation_attribution._proposal_consulted_reads(observed,[])
        assert inverse_read['id'] not in {row['id'] for row in consulted}
        assert read['read_receipt']['id'] in {row['id'] for row in consulted}
        assert mutation_attribution._read_views('author_history',{'view':'corrections'})=={'corrections','manuscript'}
        monkeypatch.setattr(authoring,'inspect',lambda *args,**kwargs:pytest.fail(
            'A structural history inverse must not inspect or rebase current authoring context'))
        assert turn_reads.refresh_context_after_read(tmp_path,'blocks','WT-inverse',
            'author_history',inverse_read['payload'])=={'refreshed':False,'reason':'historical audit read'}
