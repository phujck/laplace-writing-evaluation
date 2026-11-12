"""Bounded real active publication over an explicit retained PUBLIC base.

The base is a synthetic pre-input fixture assembled through keeper/vector and
actual current-receipt owners. It is not a live fold, metric-quality result or
authored close. Source commit/recovery and their final verifiers are real.
"""
import copy
import hashlib
import json
from pathlib import Path

import pytest
from laplace.core import identity
from laplace.core.records import journal
from laplace.engine import keeper,meaning_upfold
from laplace.representation import source_publication as P,embed_router as E
from laplace.work import owner_discovery as O,source_kernel as K
from test_source_kernel_bridge import sample


def public_base(root):
    """Declared retained-data fixture before the selected kernel input boundary."""
    import numpy as np
    root.mkdir(exist_ok=True);(root/'contract').mkdir(exist_ok=True)
    source=Path(__file__).resolve().parents[1]
    (root/'runtime_profiles.toml').write_bytes((source/'runtime_profiles.toml').read_bytes())
    leaves={'retained.txt':{'name':'retained.txt','kind':'text','essence':'Historical public fact Ω; authority stays with its owner.',
        'keywords':['retained','public'],'sealed':False}}
    nodes=keeper.build_tree(leaves);keeper.write_tree_local(root,nodes)
    keeper.write_skeleton(root,nodes,keeper.grade_stats(nodes))
    (root/'SELF_SHARD_INDEX.md').write_text('# Explicit public retained fixture\nretained.txt\n')
    backend=E.get_backend()
    assert backend and backend.gpu and 'CUDAExecutionProvider' in backend.providers,'Required local GPU unavailable; no CPU fallback'
    texts={n:E.node_text(root,{'nodes':nodes,'lenses':{}},n,{}) for n in nodes}
    values=dict(zip(texts,backend.embed(list(texts.values())),strict=True))
    cache={'backend':backend.name,'format':E.CACHE_FORMAT,'nodes':{n:{'h':E._hash(backend.name,texts[n]),**E._quantize_vec(values[n])} for n in texts}}
    (root/E.CACHE_FILE).write_bytes(identity.canonical_bytes(cache))
    meaning_upfold.write_sidecar(root,backend.name,{'retained.txt':(hashlib.sha1(texts['retained.txt'].encode()).hexdigest(),values['retained.txt'])})
    (root/'.meaning_tree.json').write_bytes(identity.canonical_bytes({'backend':backend.name,'parent_map':{'retained.txt':''},'clusters':{},'leaf_sha':{}}))
    np.savez(root/'.metric_M.npz',M=np.eye(len(values['retained.txt']),dtype='float32'))
    (root/'.metric_M.receipt.json').write_text(json.dumps({'fixture':'Retained public identity metric; NOT metric-distill/AUC evidence.'}))
    (root/'.metric_pairs.json').write_text('{"pairs":[]}')
    (root/'.self_record_floor.jsonl').write_bytes(b'')
    act=journal.act_begin('public-retained-base-fixture',['keeper','local-embedding'],root=root)
    record={'act':'deposit','act_id':act,'mode':'full-rebuild','full_requested':True,
        'ts':'2026-01-01T00:00:00+00:00','fixture':'Explicit public retained base before Source inputs; not an authored close or live full-world fold.',
        'embedding_counts':{'embedded':len(nodes),'cached':0,'deferred':0,'total':len(nodes)},
        'device':{'embedding_backend':'gpu','embedding_providers':list(backend.providers),'required':True}}
    record['publication']=P.full_publication_receipt(root,record,None,nodes,None)
    (root/P.TIMING).write_bytes(identity.canonical_bytes(record)+b'\n')
    journal.act_end(act,'pass',root=root,summary='Public retained-artifact fixture only; actual owner-generated hashes and local GPU vectors.')
    E.release_backend(backend)
    return copy.deepcopy(nodes),P.current(root)


@pytest.fixture
def selected(tmp_path):
    old,parent=public_base(tmp_path)
    payload,phase=sample(tmp_path)
    scope=O.owned_workspace('sdk')
    observed=K.read(tmp_path,scope,payload)
    request={'reference':observed['reference'],'selection':observed['selection'],'segments':['authority']}
    return tmp_path,scope,request,old,parent


def prepare_wire(root,request,request_id):
    from laplace import sdk
    prepared=sdk.source_publication({'action':'prepare','inputs':[request]},root=root)
    return prepared,{'action':'commit','request_id':request_id,'prepared':prepared['prepared'],
        'expected_publication_basis':prepared['expected_publication_basis']}


def test_first_supported_active_publication_real_recovery_and_completed_replay(selected,monkeypatch):
    root,scope,request,old,parent=selected
    from laplace import sdk
    prepared,wire=prepare_wire(root,request,'public-first-source-publication')
    assert prepared['expected_publication_basis']==parent['publication_handle']
    before=P.artifact_rows(root);before_cache=P._json(root/E.CACHE_FILE)
    result=sdk.source_publication(wire,root=root)
    assert result['state']=='RECORDED' and result['current']
    current=P.current(root);tree=P._json(root/keeper.GRADED_LOCAL)
    assert current['mode']==P.MODE and current['coverage']['complete_world'] is False
    assert tree['retained.txt']==old['retained.txt']
    assert P._json(root/E.CACHE_FILE)['nodes']['retained.txt']==before_cache['nodes']['retained.txt']
    after=P.artifact_rows(root)
    assert {p for p in before if before[p]!=after[p]}=={'.self_graded.json','SELF_GRADED_INDEX.md','.self_embeddings.json'}
    assert not (root/'contract/close_receipt.json').exists()
    assert not (root/'.semantic_source_coverage.json').exists() and not (root/'.semantic_fold_manifest.json').exists()
    view=K.read(root,scope,{'facet':'source-kernel','view':'counterpart',**request})
    assert view['kernel']['state']=='PUBLISHED'
    row=view['kernel']['counterparts'][0];assert row['publication_handle']==current['publication_handle']
    recovered=K.read(root,scope,row['read']['request'])
    assert recovered['state']=='RECOVERED' and recovered['publication_handle']==current['publication_handle']
    leaf=K.prepare(root,scope,{'facet':'source-kernel','view':'prepare',**request})
    assert recovered['facts']==json.loads(next(iter(leaf['leaves'].values()))['embedding_text'])
    from laplace.engine import descent as D
    monkeypatch.setattr(D,'source_tree',lambda:root) # Explicit public data-root seam, never final verifier substitution.
    typed=row['typed_descent'];exact=D.descend(kind=typed['kind'],reference=typed['reference'],read_scope=O.project_scope('p','native'))
    assert exact['content_handle']==row['content_handle']
    with pytest.raises(D.DescentRefused):D.descend(kind=typed['kind'],reference=typed['reference'],read_scope=O.project_scope('foreign','native'))
    injected={**json.loads(typed['reference']),**wire}
    with pytest.raises(D.DescentRefused):D.descend(kind=typed['kind'],reference=json.dumps(injected),read_scope=scope)
    from laplace.engine import source_kernel_input
    assert source_kernel_input.input_frame(root)['leaves']==leaf['leaves']
    import reembed
    calls=[]
    monkeypatch.setattr(reembed,'ROOT',root)
    monkeypatch.setattr(reembed,'_main_locked',lambda args,**kw:calls.append(kw) or 0)
    assert reembed.main([])==0 and calls[0]['source_kernel_inputs']['packet']==current['source_kernel_inputs']
    assert calls[0]['parent_publication']==current
    saved_timing=(root/P.TIMING).read_bytes();saved_journal=(root/'contract/journal.jsonl').read_bytes()
    target=root/'src/laplace/work/project_work_review.py';target.write_bytes(target.read_bytes()+b'\n# changed AFTER original successful effect\n')
    replay=sdk.source_publication(wire,root=root)
    assert replay['publication']==result['publication'] and (root/P.TIMING).read_bytes()==saved_timing and (root/'contract/journal.jsonl').read_bytes()==saved_journal
    # Published facts remain readable on their own basis while new admission is stale.
    again=K.read(root,scope,row['read']['request']);assert again['facts']==recovered['facts']
    exact_after=D.descend(kind=typed['kind'],reference=typed['reference'],read_scope=O.project_scope('p','native'))
    assert exact_after['content_handle']==exact['content_handle']
    # Moved bytes with unchanged consumed meaning: fresh preparation and the ordinary close carry it.
    assert sdk.source_publication({'action':'prepare','inputs':[request]},root=root)['prepared']==current['source_kernel_inputs']
    assert reembed.main([])==0 and len(calls)==2
    assert [row['state'] for row in calls[1]['source_kernel_inputs']['currentness'].values()]==['CARRIED']
    wrong=copy.deepcopy(row['read']['request']);wrong['publication_handle']='sha256:'+'0'*64
    with pytest.raises(ValueError,match='HISTORICAL_BYTES_UNAVAILABLE'):K.read(root,scope,wrong)
    assert not list(root.glob('.reembed-rollback-*'))
    (root/'real-current-publication-proof.json').write_text(json.dumps({'prepared':prepared,'result':result,'counterpart':view,
        'recovered':recovered,'typed':exact,'before':before,'after':after,'unselected_node_and_embedding_unchanged':True,
        'no_close_receipt':True,'no_retired_F':True,'completed_replay_before_changed_source':True,'published_read_after_changed_source':True,'fresh_admission_after_change_refused':True,'ordinary_wrapper_forwarding_only':'Producer execution substituted; selected input-frame validation real.',
        'fixture_seams':'Synthetic retained public base via actual owners; typed reader explicit data-root seam. Real cached local GPU vectors and final publication verifier, no live kernel/model/provider.'},indent=2))


def test_changed_base_source_and_operator_scope_refuse_before_effect(selected,monkeypatch):
    root,scope,request,old,parent=selected
    prepared,wire=prepare_wire(root,request,'public-refused-source-publication')
    before=(root/'contract/journal.jsonl').read_bytes()
    with monkeypatch.context() as m:
        m.setattr(P,'current',lambda *_:pytest.fail('Native publication reached publication metadata'))
        for wrong in [O.project_scope('p','native'),O.owned_workspace('native'),O.project_scope('p','sdk')]:
            with pytest.raises(ValueError,match='TRUSTED_OPERATOR_ONLY'):P.request(root,wrong,wire)
    source_index=root/'SELF_SHARD_INDEX.md';original=source_index.read_bytes();source_index.write_bytes(original+b'Changed public base\n')
    with pytest.raises(ValueError,match='ARTIFACTS_CHANGED'):P.request(root,scope,wire)
    source_index.write_bytes(original)
    bad=copy.deepcopy(wire);bad['prepared']['inputs'][0]['prepared_basis']='sha256:'+'0'*64
    with pytest.raises(ValueError,match='INPUT_CHANGED'):P.request(root,scope,bad)
    source=root/'src/laplace/work/project_work_review.py';source.unlink()  # A deleted pin is UNKNOWN; fresh selection refuses it.
    with pytest.raises(ValueError,match='SOURCE_KERNEL_SOURCE_UNKNOWN'):P.request(root,scope,wire)
    assert (root/'contract/journal.jsonl').read_bytes()==before
    assert P.inspect_request(root,scope,wire['request_id'])['state']=='NONE'


def test_mid_rename_refusal_restores_exact_parent_and_terminal_request(selected,monkeypatch):
    root,scope,request,old,parent=selected
    prepared,wire=prepare_wire(root,request,'public-midstage-source-publication')
    before=P.artifact_rows(root);timing=(root/P.TIMING).read_bytes();replace=P.os.replace;once=[]
    def failing(source,target):
        if Path(target)==root/'.self_embeddings.json' and str(source).endswith('.stage') and not once:
            once.append(True);raise OSError('Public injected mid-rename failure')
        return replace(source,target)
    monkeypatch.setattr(P.os,'replace',failing)
    with pytest.raises(OSError,match='mid-rename'):P.request(root,scope,wire)
    assert once and P.artifact_rows(root)==before and (root/P.TIMING).read_bytes()==timing
    assert P.current(root)['publication_handle']==parent['publication_handle']
    outcome=P.request(root,scope,{'action':'request','request_id':wire['request_id']});assert outcome['state']=='REJECTED'
    assert P.request(root,scope,wire)==outcome
    assert not list(root.glob('.reembed-rollback-*'))
    (root/'rollback-proof.json').write_text(json.dumps({'outcome':outcome,'parent_unchanged':True,'artifacts':before,'no_repeat_publication':True},indent=2))


def test_dead_exact_cli_attempt_recovers_only_own_partial_state(selected):
    import subprocess,sys
    root,scope,request,old,parent=selected
    _,wire=prepare_wire(root,request,'public-crashed-cli-publication')
    before=P.artifact_rows(root);timing=(root/P.TIMING).read_bytes()
    metadata={p.name:(p.stat().st_mode,p.stat().st_mtime_ns) for p in [root/'.self_graded.json',root/E.CACHE_FILE,root/'SELF_GRADED_INDEX.md',root/P.TIMING]}
    (root/'crash-wire.json').write_bytes(identity.canonical_bytes(wire))
    actor=Path(__file__).parent/'helpers/source_publication_crash.py'
    child=subprocess.run([sys.executable,'-B',str(actor),str(root)],capture_output=True,timeout=40)
    (root/'actor-stdout.txt').write_bytes(child.stdout);(root/'actor-stderr.txt').write_bytes(child.stderr)
    assert child.returncode==88,(child.returncode,child.stdout[-8192:],child.stderr[-8192:])
    actor_proof=json.loads((root/'crash-actor-proof.json').read_text());assert actor_proof['denials']==[]
    unknown=P.request(root,scope,{'action':'request','request_id':wire['request_id']});assert unknown['state']=='UNKNOWN'
    saved=(root/'contract/journal.jsonl').read_bytes();assert P.request(root,scope,wire)==unknown
    assert (root/'contract/journal.jsonl').read_bytes()==saved
    unrelated=root/'SELF_SHARD_INDEX.md';raw=unrelated.read_bytes();unrelated.write_bytes(raw+b'Unrelated newer state\n')
    with pytest.raises(ValueError,match='UNRELATED_ARTIFACT_MOVED'):P.request(root,scope,{'action':'recover','request_id':wire['request_id']})
    assert unrelated.read_bytes()!=raw and (root/'contract/journal.jsonl').read_bytes()==saved
    unrelated.write_bytes(raw)
    marker=identity.canonical_bytes({'act':'unrelated-public-observation','note':'Must survive exact recovery'})+b'\n'
    (root/P.TIMING).write_bytes(timing+marker)
    with pytest.raises(ValueError,match='FOREIGN_TIMING_CUSTODY'):P.request(root,scope,{'action':'recover','request_id':wire['request_id']})
    assert (root/P.TIMING).read_bytes()==timing+marker and (root/'contract/journal.jsonl').read_bytes()==saved
    (root/P.TIMING).write_bytes(timing)
    result=P.request(root,scope,{'action':'recover','request_id':wire['request_id']});assert result['state']=='REJECTED'
    assert P.artifact_rows(root)==before and (root/P.TIMING).read_bytes()==timing
    assert P.current(root)['publication_handle']==parent['publication_handle']
    for name,value in metadata.items():assert ((root/name).stat().st_mode,(root/name).stat().st_mtime_ns)==value
    assert P.request(root,scope,wire)==result and not list(root.glob('.reembed-rollback-*'))
    (root/'dead-cli-recovery-proof.json').write_text(json.dumps({'actor':actor_proof,'unknown':unknown,'terminal':result,
        'parent_restored':True,'unrelated_change_refused':True,'replay_no_effect':True,'real_owned_child_reaped':child.returncode},indent=2))


def test_large_timing_history_streaming_commit_unknown_and_recovery(selected,monkeypatch):
    """Actual 35,055,057B/303-row public history; history-sized buffers forbidden."""
    import subprocess,sys,os
    root,scope,request,old,parent=selected;path=root/P.TIMING
    original=path.read_bytes();target=35055057;maximum=1279882;remaining=target-len(original)
    with path.open('wb') as stream:
        for n in range(302):
            length=maximum if n==0 else remaining//(302-n)
            row={'act':'public-history-observation','n':n,'padding':''}
            row['padding']='x'*(length-len(identity.canonical_bytes(row))-1)
            raw=identity.canonical_bytes(row)+b'\n';assert len(raw)==length<=maximum
            stream.write(raw);remaining-=length
        stream.write(original)
    assert path.stat().st_size==target and sum(1 for _ in P._timings(root))==303
    read_bytes=Path.read_bytes
    def bounded_reads(self):
        if P.TIMING in self.name:pytest.fail('Whole timing history read_bytes is forbidden')
        return read_bytes(self)
    monkeypatch.setattr(Path,'read_bytes',bounded_reads)
    before=P._pin(path);assert P.current(root)['publication_handle']==parent['publication_handle']
    prepared,wire=prepare_wire(root,request,'public-large-history-first')
    result=P.request(root,scope,wire);assert result['state']=='RECORDED'
    current=P.current(root);assert current['publication_handle']==result['publication']['publication_handle']
    assert current['mode']==P.MODE and P.selections(root)==current['source_kernel_inputs']
    with path.open('rb') as stream:
        import hashlib
        digest=hashlib.sha256();left=target
        while left:
            block=stream.read(min(left,1024*1024));digest.update(block);left-=len(block)
        last=json.loads(stream.readline());assert stream.read(1)==b''
    assert 'sha256:'+digest.hexdigest()==before and last['publication']==result['publication']
    # Failed newer publication metadata is not a replacement for the active one.
    failed=journal.act_begin('public-failed-publication',['stage'],root=root)
    journal.act_end(failed,'fail',root=root,summary='Declared synthetic failed metadata; no artifact effect.')
    with path.open('ab') as stream:stream.write(identity.canonical_bytes({'act':'deposit','act_id':failed,'publication':{'schema_version':'unpublished-failure'}})+b'\n')
    assert P.current(root)['publication_handle']==current['publication_handle']
    saved=path.stat().st_size
    for invalid,reason in [(b'[]\n','MALFORMED'),(b'{"act":"unfinished"','INCOMPLETE')]:
        with path.open('ab') as stream:stream.write(invalid)
        with pytest.raises(ValueError,match=reason):P.current(root)
        with path.open('r+b') as stream:stream.truncate(saved)
    with path.open('ab') as stream:
        for _ in range(P.MAX_TIMING_RECORD//(1024*1024)):stream.write(b'x'*(1024*1024))
        stream.write(b'x\n')
    with pytest.raises(ValueError,match='RECEIPT_BOUND'):P.current(root)
    with path.open('r+b') as stream:stream.truncate(saved)
    with path.open('ab') as stream:stream.write(identity.canonical_bytes(last)+b'\n')
    with pytest.raises(ValueError,match='CUSTODY_AMBIGUOUS'):P.inspect_request(root,scope,wire['request_id'])
    with path.open('r+b') as stream:stream.truncate(saved)
    assert P.request(root,scope,wire)['publication']==result['publication']
    # The same scaled history also crosses real CLI crash/staged recovery seams.
    _,second=prepare_wire(root,request,'public-large-history-crash')
    (root/'crash-wire.json').write_bytes(identity.canonical_bytes(second))
    monkeypatch.setenv('LAPLACE_ASSERT_STREAM_TIMING','1')
    actor=Path(__file__).parent/'helpers/source_publication_crash.py'
    child=subprocess.run([sys.executable,'-B',str(actor),str(root)],capture_output=True,timeout=40)
    (root/'actor-stdout.txt').write_bytes(child.stdout);(root/'actor-stderr.txt').write_bytes(child.stderr)
    assert child.returncode==88,(child.returncode,child.stderr[-8192:])
    unknown=P.inspect_request(root,scope,second['request_id']);assert unknown['state']=='UNKNOWN'
    journal_before=(root/'contract/journal.jsonl').read_bytes();assert P.request(root,scope,second)==unknown
    marker=identity.canonical_bytes({'act':'later-public-observation'})+b'\n'
    with path.open('ab') as stream:stream.write(marker)
    cut=P._pin(path)
    with pytest.raises(ValueError,match='FOREIGN_TIMING_CUSTODY'):P.recover(root,scope,second['request_id'])
    assert P._pin(path)==cut and (root/'contract/journal.jsonl').read_bytes()==journal_before
    with path.open('r+b') as stream:stream.truncate(saved)
    outcome=P.recover(root,scope,second['request_id']);assert outcome['state']=='REJECTED'
    assert path.stat().st_size==saved and P.current(root)['publication_handle']==current['publication_handle']
    assert not list(root.glob('.reembed-rollback-*'))
    (root/'large-history-proof.json').write_text(json.dumps({'initial_bytes':target,'initial_rows':303,'max_row_bytes':maximum,
        'per_record_bound':P.MAX_TIMING_RECORD,'initial_history_sha256':before,'successful_publication':result,
        'prefix_exact':True,'whole_history_read_bytes_forbidden':True,'failed_newest_skipped':True,'malformed_incomplete_oversized_refused':True,
        'duplicate_request_refused':True,'completed_replay':True,'actual_cli_child':child.returncode,'UNKNOWN_no_repeat':True,
        'foreign_timing_preserved':True,'recovery':outcome,'parent_after_recovery':current['publication_handle']},indent=2))
