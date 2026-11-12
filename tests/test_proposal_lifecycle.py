"""Owned generic fixtures for immutable generated-candidate validation."""
import json
import pytest
from laplace.manuscript import manuscript_proposals as proposals, proposal_preflight as preflight
from laplace.native import tools as writing_tools
from laplace.writing import operations
from laplace.projects import artifacts as writing_artifacts
from laplace.writing import records as writing_records
from laplace.manuscript import source_application
from laplace.writing import session_reads
from laplace.writing.records import _fold as records_fold
from laplace.writing import turn_jobs
from laplace.manuscript import proposal_currentness
from laplace.pipeline import authoring
from test_writing_controller import _import_project,_seed_revision,_bind_rewrite_fixture

@pytest.fixture(autouse=True)
def clear():
    records_fold._CACHE.clear();turn_jobs._JOBS.clear()
    yield
    records_fold._CACHE.clear();turn_jobs._JOBS.clear()

RAW='\\documentclass{article}\n\\begin{document}\nFirst premise.\n\nSecond conclusion.\n\\end{document}\n'

def setup(root):
    manuscript,_=_import_project(root,files={'main.tex':RAW})
    context=authoring.build_context('fixture',{'files':['main.tex']},repo_root=root)
    changes=[{'file':'main.tex','line_start':n,'line_end':n,'before':before,'after':after,'reason':'Clarify.',
              'source_anchor':preflight.source_anchor(RAW,n,n)} for n,before,after in
             [(3,'First premise.','Revised premise.\nExtra explanation.'),(5,'Second conclusion.','Revised conclusion.')]]
    turn=_seed_revision(root,'fixture',changes,selection={'files':['main.tex']},context=context)
    return manuscript,turn,changes,context

def decide(root,turn,row,version,action='accept',**extra):
    return proposals.decide(root,'fixture',{'turn_id':turn,'proposal_version':version,'edit_id':row['edit_id'],'decision':action,**extra})

@pytest.mark.parametrize('order',[(0,1),(1,0)])
def test_disjoint_siblings_use_exact_owned_transitions_without_producer_rebase(tmp_path,monkeypatch,order):
    md,turn,changes,context=setup(tmp_path);calls=_bind_rewrite_fixture(monkeypatch,md)
    p=proposals.preview(tmp_path,'fixture',turn);v=p['proposal_version']
    immutable=json.dumps(session_reads._records(tmp_path)['turns'][turn]['proposal_bases'][v],sort_keys=True)
    first=decide(tmp_path,turn,p['edits'][order[0]],v)
    second=next(row for row in first['edits'] if row['edit_id']==proposals.edit_id(changes[order[1]]))
    assert second['basis_currentness']=='CURRENT' and second['lifecycle']=='actionable'
    final=decide(tmp_path,turn,second,v)
    assert len(calls)==2 and final['remaining']==0
    assert first['application']['candidate_version']==v
    assert final['application']['validation_basis']['transition_ids']==[first['application']['id']]
    observed=session_reads._records(tmp_path)['turns'][turn]
    assert json.dumps(observed['proposal_bases'][v],sort_keys=True)==immutable
    assert observed['context_id']==context['context_id'] and not final['application']['context_rebase']['advanced']
    assert all(row['lifecycle']=='retained-history' and not row['allowed_actions'] for row in final['edits'])

@pytest.mark.parametrize('drift',['undo','external','correction'])
def test_sibling_drift_refuses_cached_mutation_before_owner_write(tmp_path,monkeypatch,drift):
    md,turn,changes,context=setup(tmp_path);calls=_bind_rewrite_fixture(monkeypatch,md)
    p=proposals.preview(tmp_path,'fixture',turn);v=p['proposal_version']
    first=decide(tmp_path,turn,p['edits'][0],v);second=first['edits'][1]
    if drift=='undo':(md/'main.tex').write_text(RAW)
    elif drift=='external':(md/'main.tex').write_text((md/'main.tex').read_text()+'\nExternal science.')
    else:authoring.bank_correction('fixture',{'text':'This requires another assumption.','kind':'factual','scope':'project','by':'author'},repo_root=tmp_path)
    before=(md/'main.tex').read_bytes();blocked=proposals.preview(tmp_path,'fixture',turn,v)['edits'][1]
    assert blocked['lifecycle']=='blocked' and 'merge' not in blocked['allowed_actions']
    with pytest.raises(ValueError):decide(tmp_path,turn,second,v,'merge',review_token=second['review_token'],merged_after=changes[1]['after'])
    assert (md/'main.tex').read_bytes()==before and len(calls)==1

def test_later_turn_context_does_not_renew_sealed_candidate(tmp_path,monkeypatch):
    md,turn,changes,context=setup(tmp_path);calls=_bind_rewrite_fixture(monkeypatch,md)
    p=proposals.preview(tmp_path,'fixture',turn);v=p['proposal_version']
    authoring.bank_correction('fixture',{'text':'Original basis is no longer sufficient.','kind':'factual','scope':'project','by':'author'},repo_root=tmp_path)
    fresh=authoring.build_context('fixture',{'files':['main.tex']},repo_root=tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-turn-context-baseline','id':'CTX-new','project':'fixture','turn_id':turn,**{k:fresh.get(k) for k in ('context_id','dependencies','document')}})
    blocked=proposals.preview(tmp_path,'fixture',turn,v)['edits'][0]
    assert blocked['basis_currentness']=='STALE' and 'accept' not in blocked['allowed_actions']
    with pytest.raises(ValueError):decide(tmp_path,turn,p['edits'][0],v)
    assert not calls

def test_missing_inputs_unknown_and_author_merge_is_distinct_provenance(tmp_path,monkeypatch):
    md,turn,changes,context=setup(tmp_path);calls=_bind_rewrite_fixture(monkeypatch,md)
    p=proposals.preview(tmp_path,'fixture',turn);v=p['proposal_version'];row=p['edits'][0]
    result=decide(tmp_path,turn,row,v,'merge',review_token=row['review_token'],merged_after='My authored premise.')
    app=result['application']
    assert app['approval_mode']=='author-edited-current-source-rewrite' and app['origin']=='author-rewrite'
    assert app['derived_from_candidate']=={'turn_id':turn,'proposal_version':v,'edit_ids':[row['edit_id']]}
    assert proposals.saved_proposals(session_reads._records(tmp_path)['turns'][turn])[v]['edits'][0]['after']==changes[0]['after']
    other=_seed_revision(tmp_path,'fixture',[{'file':'main.tex','line_start':3,'line_end':3,'before':'My authored premise.','after':'Unknown candidate.','reason':'Unknown.'}],context={},suffix='unknown')
    unknown=proposals.preview(tmp_path,'fixture',other)['edits'][0]
    assert unknown['basis_currentness']=='UNKNOWN' and unknown['lifecycle']=='blocked'
    with pytest.raises(ValueError):decide(tmp_path,other,unknown,proposals.preview(tmp_path,'fixture',other)['proposal_version'])
    assert len(calls)==1

def test_version_decisions_do_not_cross_identical_edit_ids(tmp_path):
    md,turn,changes,context=setup(tmp_path)
    p=proposals.preview(tmp_path,'fixture',turn);v1=p['proposal_version']
    decide(tmp_path,turn,p['edits'][0],v1,'reject')
    second={'answer':'An explicit different retained version.','edits':changes}
    writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-alternative','turn_id':turn,'project':'fixture','proposal':second})
    v2=proposals.preview(tmp_path,'fixture',turn,records_fold._proposal_digest(second))['proposal_version']
    assert proposals.preview(tmp_path,'fixture',turn,v1)['edits'][0]['status']=='rejected'
    assert proposals.preview(tmp_path,'fixture',turn,v2)['edits'][0]['status']=='pending'
    assert not proposals.decisions(proposals.select_version(session_reads._records(tmp_path)['turns'][turn],v2))

@pytest.mark.parametrize('order',[(0,1),(1,0)])
def test_source_read_full_pin_carries_siblings_without_rewriting_receipt(tmp_path,monkeypatch,order):
    md,turn,changes,context=setup(tmp_path);_bind_rewrite_fixture(monkeypatch,md)
    writing_tools.execute(tmp_path,'fixture','revise','source',{'files':['main.tex']},turn_id=turn)
    raw={'answer':'Candidate after exact source read.','edits':changes}
    writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-source','turn_id':turn,'project':'fixture','proposal':raw})
    # Select this exact version rather than the previous final reply.
    v=proposals.preview(tmp_path,'fixture',turn,records_fold._proposal_digest(raw))['proposal_version'];p=proposals.preview(tmp_path,'fixture',turn,v)
    reads=json.dumps(session_reads._records(tmp_path)['turns'][turn]['tool_reads'],sort_keys=True)
    first=decide(tmp_path,turn,p['edits'][order[0]],v)
    other=next(row for row in first['edits'] if row['edit_id']==proposals.edit_id(changes[order[1]]))
    assert other['basis_currentness']=='CURRENT'
    final=decide(tmp_path,turn,other,v)
    assert final['application']['validation_basis']['read_ids']
    assert json.dumps(session_reads._records(tmp_path)['turns'][turn]['tool_reads'],sort_keys=True)==reads


def test_changed_consulted_artifact_blocks_generated_candidate_and_cached_merge(tmp_path,monkeypatch):
    md,turn,changes,context=setup(tmp_path);calls=_bind_rewrite_fixture(monkeypatch,md)
    artifact=writing_artifacts.project_root(tmp_path,'fixture')/'claim-evidence.txt';artifact.write_text('Original controlled evidence.')
    writing_tools.execute(tmp_path,'fixture','revise','read_artifact',{'path':'claim-evidence.txt','scope':'project'},turn_id=turn)
    raw={'answer':'Based on retained evidence.','edits':changes}
    writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-evidence','turn_id':turn,'project':'fixture','proposal':raw})
    v=proposals.preview(tmp_path,'fixture',turn,records_fold._proposal_digest(raw))['proposal_version'];row=proposals.preview(tmp_path,'fixture',turn,v)['edits'][0]
    artifact.write_text('Changed experimental conclusion.')
    blocked=proposals.preview(tmp_path,'fixture',turn,v)['edits'][0]
    assert blocked['basis_currentness']=='STALE' and 'read_artifact' in blocked['error']
    with pytest.raises(ValueError):decide(tmp_path,turn,row,v,'merge',review_token=row['review_token'],merged_after='My draft based on obsolete evidence.')
    assert not calls and (md/'main.tex').read_text()==RAW


def test_overlapping_sibling_is_blocked_after_first_acceptance(tmp_path,monkeypatch):
    md,turn,changes,context=setup(tmp_path);calls=_bind_rewrite_fixture(monkeypatch,md)
    overlap={**changes[0],'after':'Another alternative premise.'}
    raw={'answer':'Overlapping retained components.','edits':[changes[0],overlap]}
    writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-overlap','turn_id':turn,'project':'fixture','proposal':raw})
    v=proposals.preview(tmp_path,'fixture',turn,records_fold._proposal_digest(raw))['proposal_version'];p=proposals.preview(tmp_path,'fixture',turn,v)
    first=decide(tmp_path,turn,p['edits'][0],v);other=first['edits'][1]
    assert other['lifecycle']=='blocked' and 'accept' not in other['allowed_actions']
    with pytest.raises(ValueError):decide(tmp_path,turn,other,v)
    assert len(calls)==1


def test_twenty_versions_keep_small_reference_seals_and_one_basis_check(tmp_path,monkeypatch):
    raw='\\documentclass{article}\n\\begin{document}\n'+'\n\n'.join(f'Claim {i}.' for i in range(32))+'\n\\end{document}\n'
    md,_=_import_project(tmp_path,files={'main.tex':raw})
    context=authoring.build_context('fixture',{'files':['main.tex']},repo_root=tmp_path)
    changes=[{'file':'main.tex','line_start':3+i*2,'line_end':3+i*2,
        'before':f'Claim {i}.','after':f'Revised claim {i}.','reason':'Controlled disjoint edit.',
        'source_anchor':preflight.source_anchor(raw,3+i*2,3+i*2)} for i in range(32)]
    turn=_seed_revision(tmp_path,'fixture',changes,selection={'files':['main.tex']},context=context)
    versions=[]
    for n in range(20):
        raw={'answer':f'Retained version {n}.','edits':changes}
        writing_records.bank(tmp_path,{'record':'writing-proposal','id':f'PROP-version-{n}','project':'fixture','turn_id':turn,'proposal':raw})
        versions.append(proposals.proposal_version(proposals.select_version(session_reads._records(tmp_path)['turns'][turn],records_fold._proposal_digest(raw)))[0])
    rows=[json.loads(line) for line in (tmp_path/'contract/talk.jsonl').read_text().splitlines()]
    seals=[row['proposal_basis'] for row in rows if row.get('record')=='writing-proposal']
    assert len(seals)==20 and max(len(json.dumps(seal)) for seal in seals)<512
    assert all(set(seal)=={'schema_version','record_id','turn_basis_record_id','context_id','read_ids','read_receipts_sha256'} for seal in seals)
    calls=[];inspect=authoring.inspect
    monkeypatch.setattr(authoring,'inspect',lambda *args,**kwargs:(calls.append(kwargs.get('context_id')),inspect(*args,**kwargs))[1])
    import time
    started=time.perf_counter()
    p=proposals.preview(tmp_path,'fixture',turn,versions[0])
    elapsed=time.perf_counter()-started
    assert all(row['basis_currentness']=='CURRENT' for row in p['edits'])
    assert calls==[context['context_id']]
    print(json.dumps({'versions':20,'edits':32,'seal_bytes_total':sum(len(json.dumps(s).encode()) for s in seals),'seal_bytes_max':max(len(json.dumps(s).encode()) for s in seals),'context_checks':len(calls),'preview_seconds':elapsed}))


def test_generated_mutations_require_owner_read_version_even_when_scope_is_current(tmp_path,monkeypatch):
    md,turn,changes,context=setup(tmp_path);calls=_bind_rewrite_fixture(monkeypatch,md)
    row=proposals.preview(tmp_path,'fixture',turn)['edits'][0]
    with pytest.raises(ValueError,match='exact proposal_version'):
        proposals.decide(tmp_path,'fixture',{'turn_id':turn,'edit_id':row['edit_id'],'decision':'accept'})
    with pytest.raises(ValueError,match='exact proposal_version'):
        source_application.apply_proposal(tmp_path,{'turn_id':turn})
    assert not calls and (md/'main.tex').read_text()==RAW


def test_accepted_version_consumes_older_overlapping_alternative_after_undo(tmp_path,monkeypatch):
    md,turn,changes,context=setup(tmp_path);calls=_bind_rewrite_fixture(monkeypatch,md)
    p=proposals.preview(tmp_path,'fixture',turn);v1=p['proposal_version']
    other={'answer':'A retained alternative with different science.','edits':[{**changes[0],'after':'Alternative premise.'}]}
    writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-before-consumption','turn_id':turn,'project':'fixture','proposal':other})
    v2=proposals.preview(tmp_path,'fixture',turn,records_fold._proposal_digest(other))['proposal_version']
    first=decide(tmp_path,turn,p['edits'][0],v1)
    (md/'main.tex').write_text(RAW)  # owned-fixture undo shape; no live recovery.
    row=proposals.preview(tmp_path,'fixture',turn,v2)['edits'][0]
    assert row['lifecycle']=='retained-history' and row['status']=='consumed-alternative'
    assert row['consumption']['application_id']==first['application']['id'] and not row['allowed_actions']
    refused=decide(tmp_path,turn,row,v2)
    assert refused['reused'] and refused['terminal_state']=='consumed-alternative'
    assert len(calls)==1 and (md/'main.tex').read_text()==RAW
    # Fresh observed source/context supports a genuinely new candidate; it does
    # not reopen the consumed old version or change that version's producer basis.
    fresh=authoring.build_context('fixture',{'files':['main.tex']},repo_root=tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-turn-context-baseline','id':'CTX-after-undo','turn_id':turn,'project':'fixture',**{k:fresh.get(k) for k in ('context_id','dependencies','document','selection')}})
    newest={**other,'answer':'A fresh proposal explicitly after observed undo.'}
    writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-after-undo','turn_id':turn,'project':'fixture','proposal':newest})
    v3=proposals.preview(tmp_path,'fixture',turn,records_fold._proposal_digest(newest))['proposal_version']
    assert proposals.preview(tmp_path,'fixture',turn,v3)['edits'][0]['lifecycle']=='actionable'
    assert proposals.preview(tmp_path,'fixture',turn,v2)['edits'][0]['lifecycle']=='retained-history'


def test_missing_context_does_not_gain_scientific_authority_from_source_read(tmp_path):
    md,_=_import_project(tmp_path,files={'main.tex':RAW})
    change={'file':'main.tex','line_start':3,'line_end':3,'before':'First premise.','after':'New premise.','reason':'Unknown science.'}
    turn=_seed_revision(tmp_path,'fixture',[change],context={})
    writing_tools.execute(tmp_path,'fixture','revise','source',{'files':['main.tex']},turn_id=turn)
    raw={'answer':'A new version still lacks scientific context.','edits':[change]}
    writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-no-context','turn_id':turn,'project':'fixture','proposal':raw})
    assert proposals.preview(tmp_path,'fixture',turn,records_fold._proposal_digest(raw))['edits'][0]['basis_currentness']=='UNKNOWN'


def test_identical_authored_json_gets_new_instance_for_fresh_inputs_and_after_undo(tmp_path,monkeypatch):
    md,_=_import_project(tmp_path,files={'main.tex':RAW})
    context=authoring.build_context('fixture',{'files':['main.tex']},repo_root=tmp_path)
    change={'file':'main.tex','line_start':3,'line_end':3,'before':'First premise.',
        'after':'Identical proposed premise.','reason':'Identical authored rationale.',
        'source_anchor':preflight.source_anchor(RAW,3,3)}
    turn=_seed_revision(tmp_path,'fixture',[change],context=context,selection={'files':['main.tex']})
    calls=_bind_rewrite_fixture(monkeypatch,md)
    old=proposals.preview(tmp_path,'fixture',turn);v1=old['proposal_version']
    authored=proposals.saved_proposals(session_reads._records(tmp_path)['turns'][turn])[v1]
    old_basis=json.dumps(session_reads._records(tmp_path)['turns'][turn]['proposal_bases'][v1],sort_keys=True)
    authoring.bank_correction('fixture',{'text':'The conclusion now requires another assumption.','kind':'factual','scope':'project','by':'author'},repo_root=tmp_path)
    fresh=authoring.build_context('fixture',{'files':['main.tex']},repo_root=tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-turn-context-baseline','id':'CTX-collision-new','turn_id':turn,'project':'fixture',**{k:fresh.get(k) for k in ('context_id','dependencies','document','selection')}})
    receipt=writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-identical-fresh','turn_id':turn,'project':'fixture','proposal':authored})
    v2=receipt['proposal_instance_version']
    assert v1!=v2 and receipt['proposal_content_sha256']==records_fold._proposal_digest(authored)
    newer=proposals.preview(tmp_path,'fixture',turn,v2)
    assert newer['proposal_content_sha256']==old['proposal_content_sha256']
    assert newer['edits'][0]['basis_currentness']=='CURRENT'
    assert proposals.preview(tmp_path,'fixture',turn,v1)['edits'][0]['basis_currentness']=='STALE'
    with pytest.raises(ValueError,match='multiple candidate input bases'):
        proposals.preview(tmp_path,'fixture',turn,records_fold._proposal_digest(authored))
    app=decide(tmp_path,turn,newer['edits'][0],v2)['application']
    assert app['candidate_version']==v2 and len(calls)==1
    (md/'main.tex').write_text(RAW)
    old_after=proposals.preview(tmp_path,'fixture',turn,v1)['edits'][0]
    assert old_after['lifecycle']=='retained-history' and not old_after['allowed_actions']
    assert json.dumps(session_reads._records(tmp_path)['turns'][turn]['proposal_bases'][v1],sort_keys=True)==old_basis
    # A newly observed same source after undo may support the identical authored
    # proposal; native early reuse must not return the old application instead.
    latest=authoring.build_context('fixture',{'files':['main.tex']},repo_root=tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-turn-context-baseline','id':'CTX-observed-undo','turn_id':turn,'project':'fixture',**{k:latest.get(k) for k in ('context_id','dependencies','document','selection')}})
    repeated=source_application.apply_revision(tmp_path,'fixture',turn,authored)
    assert repeated['complete'] and not repeated.get('reused') and repeated['id']!=app['id']
    assert repeated['candidate_version'] not in {v1,v2} and len(calls)==2
    assert repeated['request_sha256']==records_fold._proposal_digest(authored)
    assert proposals.preview(tmp_path,'fixture',turn,v1)['edits'][0]['lifecycle']=='retained-history'


def test_malformed_legacy_read_cannot_execute_a_mutation_during_validation(tmp_path,monkeypatch):
    md,turn,changes,context=setup(tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-tool-read','id':'READ-invalid-operation','turn_id':turn,
        'project':'fixture','operation':'block_change','payload':{},'output_sha256':'invalid'})
    raw={'answer':'Malformed consumed receipt.','edits':changes}
    record=writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-invalid-read','turn_id':turn,'project':'fixture','proposal':raw})
    calls=[]
    monkeypatch.setattr(operations,'_execute',lambda *a,**k:calls.append(a) or {})
    p=proposals.preview(tmp_path,'fixture',turn,record['proposal_instance_version'])
    assert all(row['basis_currentness']=='UNKNOWN' and not row.get('review_token') for row in p['edits'])
    assert not calls and (md/'main.tex').read_text()==RAW


def test_native_propose_returns_owner_sealed_instance_not_a_model_paraphrase(tmp_path):
    md,turn,changes,context=setup(tmp_path)
    result=writing_tools.execute(tmp_path,'fixture','revise','propose_revision',{'answer':'Owner-sealed tool candidate.','edits':changes},turn_id=turn)
    p=proposals.preview(tmp_path,'fixture',turn,result['proposal_version'])
    assert p['proposal_version']==result['proposal_version']
    assert p['proposal_content_sha256']==result['proposal_content_sha256']
    assert session_reads._records(tmp_path)['turns'][turn]['proposal_bases'][result['proposal_version']]['record_id']==result['proposal_record_id']
    assert all(row['basis_currentness']=='CURRENT' for row in p['edits']) and (md/'main.tex').read_text()==RAW

@pytest.mark.parametrize('order',[(0,1),(1,0)])
@pytest.mark.parametrize('ending_mode',['crlf','mixed'])
def test_imported_newline_bytes_support_siblings_and_exact_preimage_pin(tmp_path,monkeypatch,order,ending_mode):
    md,_=_import_project(tmp_path,files={'main.tex':RAW})
    if ending_mode=='crlf':physical=RAW.replace('\n','\r\n').encode()
    else:
        endings=['\r\n','\n','\r','\r\n','\n','\r','\r\n']
        physical=''.join(line+endings[i] for i,line in enumerate(RAW.split('\n')[:-1])).encode()
    path=md/'main.tex';path.write_bytes(physical)
    context=authoring.build_context('fixture',{'files':['main.tex']},repo_root=tmp_path)
    changes=[{'file':'main.tex','line_start':n,'line_end':n,'before':before,'after':after,'reason':'Clarify.',
        'source_anchor':preflight.source_anchor(RAW,n,n)} for n,before,after in
        [(3,'First premise.','Revised premise.\nAn explanation.'),(5,'Second conclusion.','Revised conclusion.')]]
    turn=_seed_revision(tmp_path,'fixture',changes,selection={'files':['main.tex']},context=context)
    calls=_bind_rewrite_fixture(monkeypatch,md)
    p=proposals.preview(tmp_path,'fixture',turn);version=p['proposal_version']
    first=decide(tmp_path,turn,p['edits'][order[0]],version)
    pin=first['application']['owned_changes']['files'][0]
    import hashlib
    assert pin['before_sha256']=='sha256:'+hashlib.sha256(physical).hexdigest()
    assert pin['before_source_text_sha256']=='sha256:'+hashlib.sha256(RAW.encode()).hexdigest()
    assert pin['before_sha256']!=pin['before_source_text_sha256']
    assert proposal_currentness._source_preimage_bytes(RAW,pin['before_source_format'])==physical
    other=next(row for row in first['edits'] if row['edit_id']==proposals.edit_id(changes[order[1]]))
    assert other['basis_currentness']=='CURRENT' and other['lifecycle']=='actionable',other.get('error')
    final=decide(tmp_path,turn,other,version)
    assert final['application']['complete'] and len(calls)==2
    assert final['application']['validation_basis']['transition_ids']==[first['application']['id']]


def test_external_byte_format_change_does_not_pass_owned_source_chain(tmp_path,monkeypatch):
    md,turn,changes,context=setup(tmp_path);calls=_bind_rewrite_fixture(monkeypatch,md)
    p=proposals.preview(tmp_path,'fixture',turn);version=p['proposal_version']
    first=decide(tmp_path,turn,p['edits'][0],version);other=first['edits'][1]
    path=md/'main.tex';path.write_bytes(path.read_bytes().replace(b'\n',b'\r\n'))
    before=path.read_bytes();blocked=proposals.preview(tmp_path,'fixture',turn,version)['edits'][1]
    assert blocked['basis_currentness']=='STALE' and 'physical postimage' in blocked['error']
    with pytest.raises(ValueError):decide(tmp_path,turn,other,version)
    assert path.read_bytes()==before and len(calls)==1


def test_unknown_or_corrupt_newline_layout_cannot_invent_physical_preimage():
    with pytest.raises(ValueError):proposal_currentness._source_preimage_bytes('A\nB\n',{'schema_version':'laplace.source-text-bytes/1','encoding':'utf-8','newline_runs':[['\r\n',1]]})
    with pytest.raises(ValueError):proposal_currentness._source_preimage_bytes('A\n',{'schema_version':'unknown','encoding':'utf-8','newline_runs':[['\r\n',1]]})


def test_author_edited_after_does_not_renew_remaining_generated_sibling(tmp_path,monkeypatch):
    md,turn,changes,context=setup(tmp_path);calls=_bind_rewrite_fixture(monkeypatch,md)
    p=proposals.preview(tmp_path,'fixture',turn);version=p['proposal_version']
    first=decide(tmp_path,turn,p['edits'][0],version,'merge',review_token=p['edits'][0]['review_token'],merged_after='An independently authored scientific premise.')
    other=first['edits'][1]
    assert first['application']['approval_mode']=='author-edited-current-source-rewrite'
    assert other['basis_currentness']=='STALE' and 'author-edited rewrite' in other['error']
    assert 'accept' not in other['allowed_actions'] and not other.get('review_token')
    before=(md/'main.tex').read_bytes()
    with pytest.raises(ValueError):decide(tmp_path,turn,other,version)
    assert (md/'main.tex').read_bytes()==before and len(calls)==1


@pytest.mark.parametrize('operation',['logical_plan','concept_tree','reference','concept_history','literature_lookup'])
def test_targeted_semantic_read_outside_current_source_scope_remains_dependency(tmp_path,monkeypatch,operation):
    md,turn,changes,context=setup(tmp_path);calls=_bind_rewrite_fixture(monkeypatch,md)
    from laplace.writing import operations
    from laplace.writing import reads as reads_owner
    payload={'node':'outside-Y'} if operation in {'logical_plan','concept_tree','concept_history'} else {'key':'outside-Y'}
    old={'id':'outside-Y','semantic_statement':'Original outside-scope scientific premise.'}
    writing_records.bank(tmp_path,{'record':'writing-tool-read','id':'READ-outside-'+operation,'turn_id':turn,'project':'fixture',
        'operation':operation,'payload':payload,'output_sha256':reads_owner.read_output_digest(operation,old)})
    candidate={'answer':'Candidate with explicitly consumed outside semantic read.','edits':changes}
    record=writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-outside-'+operation,'turn_id':turn,'project':'fixture','proposal':candidate})
    observations=[];value=dict(old)
    monkeypatch.setattr(operations,'_execute',lambda root,project,mode,op,payload,turn_id=None:(observations.append((op,payload)),value)[1])
    version=record['proposal_instance_version'];before=proposals.preview(tmp_path,'fixture',turn,version)
    assert before['edits'][0]['basis_currentness']=='CURRENT'
    assert not authoring.inspect('fixture',{'files':['main.tex']},repo_root=tmp_path,context_id=context['context_id'])['stale']
    value['semantic_statement']='Changed outside-scope scientific meaning.'
    after=proposals.preview(tmp_path,'fixture',turn,version)
    assert after['edits'][0]['basis_currentness']=='STALE' and operation in after['edits'][0]['error']
    with pytest.raises(ValueError):decide(tmp_path,turn,before['edits'][0],version)
    assert observations and all(op==operation for op,_ in observations)
    assert not calls and (md/'main.tex').read_text()==RAW


@pytest.mark.parametrize('ending_mode',['crlf','mixed'])
def test_physical_source_read_pin_and_context_keep_imported_newline_domain(tmp_path,monkeypatch,ending_mode):
    md,_=_import_project(tmp_path,files={'main.tex':RAW})
    endings=['\r\n']*6 if ending_mode=='crlf' else ['\r\n','\n','\r','\r\n','\n','\r']
    physical=''.join(line+endings[i] for i,line in enumerate(RAW.split('\n')[:-1])).encode()
    path=md/'main.tex';path.write_bytes(physical)
    context=authoring.build_context('fixture',{'files':['main.tex']},repo_root=tmp_path)
    changes=[{'file':'main.tex','line_start':n,'line_end':n,'before':before,'after':after,'reason':'Clarify.',
        'source_anchor':preflight.source_anchor(RAW,n,n)} for n,before,after in
        [(3,'First premise.','Revised premise.\nAn explanation.'),(5,'Second conclusion.','Revised conclusion.')]]
    turn=_seed_revision(tmp_path,'fixture',changes,selection={'files':['main.tex']},context=context)
    writing_tools.execute(tmp_path,'fixture','revise','source',{'files':['main.tex']},turn_id=turn)
    record=writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-newline-source','turn_id':turn,'project':'fixture',
        'proposal':{'answer':'Based on exact physical source read.','edits':changes}})
    calls=_bind_rewrite_fixture(monkeypatch,md);version=record['proposal_instance_version']
    p=proposals.preview(tmp_path,'fixture',turn,version)
    first=decide(tmp_path,turn,p['edits'][0],version)
    assert first['edits'][1]['basis_currentness']=='CURRENT'
    final=decide(tmp_path,turn,first['edits'][1],version)
    assert final['application']['complete'] and len(calls)==2


def test_proven_target_is_readonly_when_consumed_source_elsewhere_changed(tmp_path,monkeypatch):
    md,turn,changes,context=setup(tmp_path);calls=_bind_rewrite_fixture(monkeypatch,md)
    path=md/'main.tex';path.write_text(path.read_text().replace('\\end{document}','An external conclusion.\n\\end{document}'))
    p=proposals.preview(tmp_path,'fixture',turn);row=p['edits'][0]
    assert row['target_proof']['status']=='CURRENT' and row['current_mapping']=='proven-current-source-occurrence'
    assert row['current_anchor']=={'file':'main.tex','line_start':3,'line_end':3}
    assert row['current_before']=='First premise.' and row['basis_currentness']=='STALE'
    assert row['resolution_available'] is False and not row.get('review_token')
    assert 'accept' not in row['allowed_actions'] and 'merge' not in row['allowed_actions']
    with pytest.raises(ValueError):decide(tmp_path,turn,row,p['proposal_version'],'merge',review_token='cached-token',merged_after='Unsafe renewal.')
    assert not calls


def test_opaque_proposal_instance_recipe_is_published_by_active_identity_help():
    from laplace.core import grammar, identity_doors
    home=grammar.HOME_KINDS['proposal']
    assert 'immutable consumed input basis' in home.bytes
    assert 'callers must not derive' in home.closes
    assert 'opaque' in identity_doors.NO_OLD_NAME['apply_proposal']
    assert 'Every decision requires' in identity_doors.NO_OLD_NAME['proposal_decision']


def test_proposal_summary_after_long_partial_acceptance_has_no_application_bodies(tmp_path,monkeypatch):
    long='Generic proposed source sentence. '*3100
    raw='\\documentclass{article}\n\\begin{document}\n'+long+'\n\nSecond conclusion.\n\\end{document}\n'
    md,_=_import_project(tmp_path,files={'main.tex':raw})
    changes=[{'file':'main.tex','line_start':n,'line_end':n,'before':before,'after':after,'reason':'Clarify.',
        'source_anchor':preflight.source_anchor(raw,n,n)} for n,before,after in
        [(3,long,long+' An accepted clarification.'),(5,'Second conclusion.','Revised conclusion.')]]
    turn=_seed_revision(tmp_path,'fixture',changes,selection={'files':['main.tex']})
    _bind_rewrite_fixture(monkeypatch,md)
    p=proposals.preview(tmp_path,'fixture',turn);result=decide(tmp_path,turn,p['edits'][0],p['proposal_version'])
    summary=session_reads.pending_proposals(tmp_path,'fixture',summary=True)
    encoded=json.dumps(summary)
    assert long not in encoded and len(encoded.encode())<5000
    assert summary['count']==1 and summary['proposals'][0]['edit_count']==1
    app=summary['proposals'][0]['application']
    assert 'edits' not in app and 'receipts' not in app and app['detail']['item_id']==result['application']['id']
    exact=session_reads.session_turn_detail(tmp_path,'fixture',turn,'application',item_id=app['id'])
    assert exact['application']['edits'][0]['before']==long


def test_native_copied_multiline_crlf_preimage_uses_canonical_address_and_physical_pin(tmp_path,monkeypatch):
    md,_=_import_project(tmp_path,files={'main.tex':RAW})
    physical=RAW.replace('\n','\r\n').encode();(md/'main.tex').write_bytes(physical)
    context=authoring.build_context('fixture',{'files':['main.tex']},repo_root=tmp_path)
    turn=_seed_revision(tmp_path,'fixture',[],selection={'files':['main.tex']},context=context)
    calls=_bind_rewrite_fixture(monkeypatch,md)
    source=writing_tools.execute(tmp_path,'fixture','revise','source',{'files':['main.tex'],'line_start':3,'line_end':5},turn_id=turn)
    copied=source['sources'][0]['text'].rstrip('\r\n')
    assert '\r\n' in copied
    result=source_application.apply_revision(tmp_path,'fixture',turn,{'edits':[{'file':'main.tex','line_start':3,'line_end':5,
        'before':copied,'after':'A revised premise and conclusion.','reason':'Exact copied raw source.'}]})
    import hashlib
    assert result['complete'] and len(calls)==1
    assert result['owned_changes']['files'][0]['before_sha256']=='sha256:'+hashlib.sha256(physical).hexdigest()
    assert result['edits'][0]['before']=='First premise.\n\nSecond conclusion.'


def test_carriage_return_comment_boundary_cannot_hide_active_document_tokens():
    before='\\documentclass{article}\n\\begin{document}\nCurrent.\n\\end{document}\n'
    after=before.replace('Current.','% Example comment\r\\begin{document}\rChanged.')
    assert preflight.staged_integrity_errors(before,after,is_root=True)

@pytest.mark.parametrize('first_index',[0,1])
def test_selective_then_whole_apply_uses_same_proven_remaining_unit(tmp_path,monkeypatch,first_index):
    md,turn,changes,context=setup(tmp_path);calls=_bind_rewrite_fixture(monkeypatch,md)
    p=proposals.preview(tmp_path,'fixture',turn);version=p['proposal_version']
    first=decide(tmp_path,turn,p['edits'][first_index],version)
    before=json.dumps(session_reads._records(tmp_path)['turns'][turn]['proposal_bases'][version],sort_keys=True)
    # Whole apply must never instantiate the expensive renderer for addressing.
    preview=proposals.preview
    monkeypatch.setattr(proposals,'preview',lambda *a,**k:pytest.fail('Whole apply rendered a preview'))
    whole=source_application.apply_proposal(tmp_path,{'turn_id':turn,'proposal_version':version})
    assert whole['complete'] and whole['candidate_edit_ids']==[proposals.edit_id(changes[1-first_index])]
    assert whole['validation_basis']['transition_ids']==[first['application']['id']]
    assert len(calls)==2
    repeated=source_application.apply_proposal(tmp_path,{'turn_id':turn,'proposal_version':version})
    assert repeated['reused'] and repeated['id']==whole['id'] and len(calls)==2
    monkeypatch.setattr(proposals,'preview',preview)
    final=proposals.preview(tmp_path,'fixture',turn,version)
    assert final['remaining']==0 and all(row['lifecycle']=='retained-history' for row in final['edits'])
    assert json.dumps(session_reads._records(tmp_path)['turns'][turn]['proposal_bases'][version],sort_keys=True)==before


def test_whole_apply_then_selective_retry_is_history_without_new_writes(tmp_path,monkeypatch):
    md,turn,changes,context=setup(tmp_path);calls=_bind_rewrite_fixture(monkeypatch,md)
    p=proposals.preview(tmp_path,'fixture',turn);version=p['proposal_version']
    app=source_application.apply_proposal(tmp_path,{'turn_id':turn,'proposal_version':version})
    assert app['complete'] and set(app['candidate_edit_ids'])=={row['edit_id'] for row in p['edits']}
    repeat=decide(tmp_path,turn,p['edits'][1],version)
    assert repeat['reused'] and repeat['remaining']==0 and len(calls)==1
    assert source_application.apply_proposal(tmp_path,{'turn_id':turn,'proposal_version':version})['reused'] and len(calls)==1


def test_mixed_whole_apply_refuses_stale_science_before_remaining_write(tmp_path,monkeypatch):
    md,turn,changes,context=setup(tmp_path);calls=_bind_rewrite_fixture(monkeypatch,md)
    p=proposals.preview(tmp_path,'fixture',turn);version=p['proposal_version']
    decide(tmp_path,turn,p['edits'][0],version)
    authoring.bank_correction('fixture',{'text':'A new assumption changes this use.','kind':'factual','scope':'project','by':'author'},repo_root=tmp_path)
    before=(md/'main.tex').read_bytes()
    with pytest.raises(ValueError):source_application.apply_proposal(tmp_path,{'turn_id':turn,'proposal_version':version})
    assert len(calls)==1 and (md/'main.tex').read_bytes()==before


def test_whole_remaining_tracks_negative_line_shift_with_original_component_id(tmp_path,monkeypatch):
    raw='\\documentclass{article}\n\\begin{document}\nFirst premise.\nExtra premise line.\n\nSecond conclusion.\n\\end{document}\n'
    md,_=_import_project(tmp_path,files={'main.tex':raw})
    changes=[{'file':'main.tex','line_start':3,'line_end':4,'before':'First premise.\nExtra premise line.','after':'Compact premise.','reason':'Compress.',
              'source_anchor':preflight.source_anchor(raw,3,4)},
             {'file':'main.tex','line_start':6,'line_end':6,'before':'Second conclusion.','after':'Revised conclusion.','reason':'Clarify.',
              'source_anchor':preflight.source_anchor(raw,6,6)}]
    turn=_seed_revision(tmp_path,'fixture',changes,selection={'files':['main.tex']});calls=_bind_rewrite_fixture(monkeypatch,md)
    p=proposals.preview(tmp_path,'fixture',turn);version=p['proposal_version']
    first=decide(tmp_path,turn,p['edits'][0],version)
    assert first['edits'][1]['current_anchor']['line_start']==5
    whole=source_application.apply_proposal(tmp_path,{'turn_id':turn,'proposal_version':version})
    assert whole['edits'][0]['line_start']==5 and whole['candidate_edit_ids']==[proposals.edit_id(changes[1])]
    assert len(calls)==2 and proposals.preview(tmp_path,'fixture',turn,version)['remaining']==0
