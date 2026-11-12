"""Small real-owner joins: logical prose markers, current plan and retained RPUB."""
import copy
import json
import pytest
from laplace.manuscript import reader_restructure as owner, reader_plan
from test_reader_restructure import case


def completed_preview(case, kind='logical-split', selected=None):
    root, _, _ = case
    selected = selected or (['first-p1'] if kind=='logical-split' else ['first-p1','first-p2'])
    initial = owner.preview('book','first',kind,{'paragraph_ids':selected},root)
    ids = [row['paragraph_id'] for row in initial['successors']]
    draft = {'paragraph_ids':selected,
        'successors':[{'paragraph_id':ident,'changes':{'function':'Explain '+str(i),'proposition':'Authored point '+str(i)}} for i,ident in enumerate(ids)],
        'attachment_assignments':[{'attachment_id':row['id'],'disposition':'assign','successor_ids':[ids[0]]} for row in initial['attachment_inventory']],
        'occurrence_assignments':[{'occurrence_id':row['id'],'successor_ids':[ids[i%len(ids)]]} for i,row in enumerate(initial['occurrence_inventory'])]}
    return initial, owner.preview('book','first',kind,draft,root)


def apply(case, value):
    return owner.change('book',{**value['apply_action']['payload'],'draft':value['draft']},case[0])


def test_logical_split_retains_all_occurrences_and_qualification_then_inverse(case):
    root,_,chapter=case
    path=owner._snapshot('book','first',root)['paths']['narrative']
    old=json.loads(path.read_text());old['paragraphs'][0]['qualification']='Prior scope';path.write_text(json.dumps(old))
    source=chapter.read_bytes(); initial, final=completed_preview(case)
    assert len(initial['occurrence_inventory'])==2
    assert next(row for row in initial['attachment_inventory'] if row['kind']=='qualification')['value']=='Prior scope'
    assert final['ready'] and final['apply_action']
    result=apply(case,final)
    assert result['complete'],result
    current=json.loads(path.read_text())['paragraphs']
    assert len(current)==3 and current[0]['qualification']=='Prior scope'
    assert '% first-p1\n' not in chapter.read_text() and chapter.read_text().count('% first-p2\n')==1
    undone=owner.change('book',result['undo_action']['payload'],root)
    assert undone['complete'],undone
    assert chapter.read_bytes()==source and json.loads(path.read_text())==old
    redone=owner.change('book',undone['undo_action']['payload'],root)
    assert redone['complete'],redone
    assert json.loads(path.read_text())['paragraphs']==current


def test_logical_metadata_outage_recovers_saved_source_only(case,monkeypatch):
    root,_,chapter=case;_,final=completed_preview(case)
    path=owner._snapshot('book','first',root)['paths']['provenance'];store=owner._store
    with monkeypatch.context() as outage:
        def fail(project,root,target,*args,**kwargs):
            if target==path:raise OSError('Simulated logical provenance publication failure')
            return store(project,root,target,*args,**kwargs)
        outage.setattr(owner,'_store',fail)
        pending=apply(case,final)
    assert pending['source_effect']['state']=='COMMITTED' and not pending['complete'],pending
    saved=chapter.read_bytes()
    from laplace.manuscript import manuscript_structure
    monkeypatch.setattr(manuscript_structure,'_write_source',lambda *a,**k:pytest.fail('Logical recovery replayed source'))
    recovered=owner.change('book',pending['recovery_action']['payload'],root)
    assert recovered['complete'],recovered
    assert chapter.read_bytes()==saved


def test_plan_only_split_has_no_synthetic_source_receipt(case):
    root,_,chapter=case;chapter.write_text('\\chapter{First}\\label{chapter:first}\n')
    initial,final=completed_preview(case)
    assert not initial['source_required'] and final['ready']
    result=apply(case,final)
    assert result['complete'] and result['source_unchanged'] and 'source_effect' not in result,result
    inverse=owner.change('book',result['undo_action']['payload'],root)
    assert inverse['complete'] and 'source_effect' not in inverse,inverse


def test_current_actions_and_exact_retired_identity_do_not_reappear_in_active_plan(case):
    root,_,_=case
    snapshot=owner._snapshot('book','first',root)
    current=reader_plan.section_view('book',root,snapshot['section'],snapshot['state']['sections'],snapshot['state']['authority']['plan_revision'])
    actions=current['paragraph_plan']['paragraphs']['items'][0]['restructure_actions']
    assert actions['split']['payload']['draft']['paragraph_ids']==['first-p1']
    assert actions['merge']['choices_read']['operation']=='structure'
    _,final=completed_preview(case);result=apply(case,final);assert result['complete']
    snapshot=owner._snapshot('book','first',root)
    retired=reader_plan.section_view('book',root,snapshot['section'],snapshot['state']['sections'],snapshot['state']['authority']['plan_revision'],paragraph_id='first-p1')
    assert retired['paragraph_plan']['status']=='RETIRED'
    old=retired['paragraph_plan']['paragraphs']['items'][0]
    assert old['paragraph_id']=='first-p1' and old['function']=='Introduce' and old['read_only']
    assert len(old['successor_reads'])==2 and old['semantic_currentness']=='HISTORICAL_REVIEW_ONLY'
    assert all(row['paragraph_id']!='first-p1' for row in snapshot['rows'])


def test_native_logical_read_parts_are_bounded_and_keep_exact_owner_actions(case):
    from laplace.native import tools as writing_tools
    from laplace.core import grammar
    from laplace.writing import records
    root,_,chapter=case
    # Many repeated physical witnesses must not bloat native discovery.
    chapter.write_text('\\chapter{First}\\label{chapter:first}\n'+''.join('% first-p1\n% first-p2\nParagraph '+str(i)+'.\n\n' for i in range(120)))
    caller='WT-logical';records.bank(root,{'record':'writing-turn','id':caller,'project':'book','mode':'discuss'})
    request={'verb':'read','concept':'plan@plan','target':'book','expected':[],
        'payload':grammar.to_payload({'view':'restructure','section_ids':['first'],'kind':'logical-split','draft':{'paragraph_ids':['first-p1']}}),'by':''}
    answer=writing_tools.call(root,'book','discuss',request,turn_id=caller)
    assert answer.get('ok'),answer
    assert len(json.dumps(answer,ensure_ascii=False,indent=2).encode())<14000
    native=answer['owner_response'];assert native['counts']['occurrence_inventory']==120 and not native['contract_inline']
    text=[];hashes=set();handle=native['contract_read']
    while handle:
        answer=writing_tools.call(root,'book','discuss',handle['native_request'],turn_id=caller)
        assert answer.get('ok'),answer
        assert len(json.dumps(answer,ensure_ascii=False,indent=2).encode())<14000
        part=answer['owner_response'];hashes.add(part['coverage']['sha256']);text.append(part['content']);handle=part.get('next_read')
    assert len(hashes)==1
    complete=json.loads(''.join(text));human=owner.preview('book','first','logical-split',{'paragraph_ids':['first-p1']},root)
    assert complete['restructure_token']==human['restructure_token']
    assert complete['guards']==human['guards'] and complete['occurrence_inventory']==human['occurrence_inventory']


def test_source_and_profile_dependency_races_refuse_without_renewal(case,monkeypatch):
    root,_,chapter=case;_,final=completed_preview(case);old=chapter.read_bytes()
    from laplace.manuscript import reader_logical_publication as publication
    real=publication.inputs
    def changed(*args,**kwargs):
        result=real(*args,**kwargs)
        for basis in result['readers'].values():basis['inputs']['architecture']='sha256:'+'0'*64
        return result
    monkeypatch.setattr(publication,'inputs',changed)
    with pytest.raises(ValueError,match='CHANGED_INPUT'):
        apply(case,final)
    assert chapter.read_bytes()==old


def test_provenance_attachments_are_explicit_and_inverse_restores_full_values(case):
    root,_,chapter=case;snapshot=owner._snapshot('book','first',root)
    path=snapshot['paths']['provenance'];path.parent.mkdir(parents=True,exist_ok=True)
    original={'section_id':'first','custom_top':'kept','paragraphs':[
        {'spec_id':'first-p1','spec_ids':['first-p1'], 'source':{'file':'chapters/chapter-01.tex','line_start':3,'line_end':4},
            'nodes_realised':['claim:one'],'qualifications':['Unproved prior scope'],'custom_annotation':{'note':'Exact prior value'}},
        {'spec_id':'first-p1','spec_ids':['first-p1','first-p2'], 'source':{'file':'chapters/chapter-01.tex','line_start':6,'line_end':8},'equations':['eq:old']}]}
    path.write_text(json.dumps(original));before=chapter.read_bytes()
    initial,final=completed_preview(case)
    fields={row['field'] for row in initial['attachment_inventory']}
    assert {'provenance.nodes_realised','provenance.qualifications','provenance.custom_annotation','provenance.equations'}<=fields
    result=apply(case,final);assert result['complete'],result
    document=json.loads(path.read_text())
    assert document['custom_top']=='kept'
    assert all('nodes_realised' not in row and row['semantic_currentness']=='NOT_REVIEWED' for row in document['paragraphs'])
    inverse=owner.change('book',result['undo_action']['payload'],root)
    assert inverse['complete'],inverse
    assert json.loads(path.read_text())==original and chapter.read_bytes()==before


def test_dependency_change_after_saved_source_refuses_metadata_without_replay(case,monkeypatch):
    root,_,chapter=case;_,final=completed_preview(case)
    target=owner._snapshot('book','first',root)['paths']['provenance'];store=owner._store
    with monkeypatch.context() as outage:
        def fail(project,root,path,*args,**kwargs):
            if path==target:raise OSError('provenance outage')
            return store(project,root,path,*args,**kwargs)
        outage.setattr(owner,'_store',fail);pending=apply(case,final)
    source=chapter.read_bytes()
    actual=reader_plan._architecture
    def changed(*args,**kwargs):
        result=copy.deepcopy(actual(*args,**kwargs));result['effective_projection']['revision']='sha256:'+'a'*64;return result
    monkeypatch.setattr(reader_plan,'_architecture',changed)
    refused=owner.change('book',pending['recovery_action']['payload'],root)
    assert not refused['complete'] and 'dependencies changed' in refused['error']
    assert chapter.read_bytes()==source and refused['source_effect']['state']=='COMMITTED'


def test_merge_keeps_qualified_predecessors_and_explicit_retired_reads(case):
    root,_,chapter=case;snapshot=owner._snapshot('book','first',root)
    path=snapshot['paths']['narrative'];original=json.loads(path.read_text())
    original['paragraphs'][0]['qualification']='One qualification'
    original['paragraphs'][1]['qualification']='Other qualification';path.write_text(json.dumps(original))
    initial=owner.preview('book','first','logical-merge',{'paragraph_ids':['first-p1','first-p2']},root)
    ident=initial['successor_ids'][0]
    draft={'paragraph_ids':['first-p1','first-p2'], 'successors':[{'paragraph_id':ident,'changes':{'function':'Combine','proposition':'Both points'}}],
        'attachment_assignments':[{'attachment_id':row['id'],'disposition':'retain-unresolved','successor_ids':[ident]} for row in initial['attachment_inventory']],
        'occurrence_assignments':[{'occurrence_id':row['id'],'successor_ids':[ident]} for row in initial['occurrence_inventory']]}
    final=owner.preview('book','first','logical-merge',draft,root);result=apply(case,final)
    assert result['complete'],result
    assert len(json.loads(path.read_text())['paragraphs'])==1
    assert sum(row['kind']=='ATTACHMENT_RECONCILIATION' for row in result['review_obligations'])==2
    assert '% first-p1\n' not in chapter.read_text() and '% first-p2\n' not in chapter.read_text()


def test_native_logical_apply_inverse_keeps_actual_actor_and_exact_owner_identity(case):
    from laplace.native import tools as writing_tools
    from laplace.core import grammar
    from laplace.writing import records
    root,_,chapter=case;before=chapter.read_bytes();_,prepared=completed_preview(case)
    caller='WT-logical-author';records.bank(root,{'record':'writing-turn','id':caller,'project':'book','mode':'work'})
    request=copy.deepcopy(prepared['apply_action']['native_request'])
    request['payload']=grammar.to_payload({**grammar.to_owner_payload(request['payload']),'draft':prepared['draft']})
    result=writing_tools.call(root,'book','work',request,turn_id=caller)
    assert result.get('ok'),result
    value=result['owner_response'];assert value['complete'] and value['undo_action']['native_request']
    assert owner._intent('book',root,value['receipt']['intent_artifact_id'])['actor']['turn_id']==caller
    inverse=writing_tools.call(root,'book','work',value['undo_action']['native_request'],turn_id=caller)
    assert inverse.get('ok'),inverse
    assert inverse['owner_response']['complete'] and chapter.read_bytes()==before


@pytest.mark.parametrize('logical_kind',[False,True])
def test_explicit_current_source_metadata_reconciliation_never_replays_later_edit(case,monkeypatch,logical_kind):
    from test_reader_restructure import split_draft
    root,_,chapter=case
    final=completed_preview(case)[1] if logical_kind else owner.preview('book','first','presentation-split',split_draft(case),root)
    target=owner._snapshot('book','first',root)['paths']['provenance'];store=owner._store
    with monkeypatch.context() as outage:
        def fail(project,root,path,*args,**kwargs):
            if path==target:raise OSError('metadata unavailable')
            return store(project,root,path,*args,**kwargs)
        outage.setattr(owner,'_store',fail);partial=apply(case,final)
    assert not partial['complete'] and partial['source_effect']['state']=='COMMITTED'
    chapter.write_bytes(chapter.read_bytes().replace(b'First sentence.',b'Later human edit.'))
    physical=chapter.read_bytes()
    query=partial['reconciliation_read']['payload']
    inspected=owner.read('book',query,root);reconciliation=inspected['metadata_reconciliation']
    assert reconciliation['status']=='READY',reconciliation
    from laplace.manuscript import manuscript_structure
    monkeypatch.setattr(manuscript_structure,'_write_source',lambda *a,**k:pytest.fail('Metadata reconciliation rewrote source'))
    acknowledged=owner.change('book',reconciliation['action']['payload'],root)
    assert acknowledged['complete'] and acknowledged['metadata_only'],acknowledged
    assert acknowledged['source_receipt_id']==partial['source_receipt_id']
    assert acknowledged['source_effect']==partial['source_effect']
    assert acknowledged['current_observation']['file_revisions'][chapter.relative_to(root).as_posix()]==owner.revision(physical).removeprefix('sha256:')
    assert chapter.read_bytes()==physical and not owner.pending('book','first',root)
    assert not acknowledged.get('undo_action') and acknowledged['review_obligations']


def test_current_source_reconciliation_refuses_changed_marker_layout_and_stale_adoption(case,monkeypatch):
    root,_,chapter=case;_,final=completed_preview(case);store=owner._store
    target=owner._snapshot('book','first',root)['paths']['provenance']
    with monkeypatch.context() as outage:
        def fail(project,root,path,*args,**kwargs):
            if path==target:raise OSError('metadata unavailable')
            return store(project,root,path,*args,**kwargs)
        outage.setattr(owner,'_store',fail);partial=apply(case,final)
    chapter.write_bytes(chapter.read_bytes().replace(b'First sentence.',b'Later human edit.'))
    ready=owner.read('book',partial['reconciliation_read']['payload'],root)['metadata_reconciliation']
    assert ready['status']=='READY'
    chapter.write_bytes(chapter.read_bytes().replace(b'Later human edit.',b'Later changed edit.'))
    before=chapter.read_bytes()
    with pytest.raises(ValueError,match='CHANGED_INPUT'):
        owner.change('book',ready['action']['payload'],root)
    assert chapter.read_bytes()==before
    marker=('% '+final['successor_ids'][0]+'\n').encode()
    chapter.write_bytes(before.replace(marker,b'% unrelated-p999\n',1))
    unproved=owner.read('book',partial['reconciliation_read']['payload'],root)['metadata_reconciliation']
    assert unproved['status']=='UNPROVABLE' and not unproved['action'] and unproved['source_reads']


def test_fixed_scope_split_inverse_has_stable_attachment_and_retained_intent_size(case):
    root,_,chapter=case;before=chapter.read_bytes();sizes=[];counts=[]
    from laplace.writing import records
    for _ in range(4):
        initial,final=completed_preview(case);counts.append(len(initial['attachment_inventory']))
        result=apply(case,final);assert result['complete']
        intent=owner._intent('book',root,result['receipt']['intent_artifact_id'])
        sizes.append(len(json.dumps(intent).encode()))
        inverse=owner.change('book',result['undo_action']['payload'],root);assert inverse['complete']
        assert chapter.read_bytes()==before
    assert counts==[0,0,0,0] and max(sizes)<min(sizes)*1.03


def test_fresh_profile_dependency_refusal_precedes_inverse_source_effect(case,monkeypatch):
    root,_,chapter=case;result=apply(case,completed_preview(case)[1]);before=chapter.read_bytes()
    architecture=reader_plan._architecture
    def changed(*args,**kwargs):
        value=copy.deepcopy(architecture(*args,**kwargs));value['effective_projection']['revision']='sha256:'+'b'*64;return value
    monkeypatch.setattr(reader_plan,'_architecture',changed)
    with pytest.raises(ValueError,match='CHANGED_INPUT'):
        owner.change('book',result['undo_action']['payload'],root)
    assert chapter.read_bytes()==before


def reconciliation_case(case,monkeypatch,logical_kind=True,line_shift=False):
    """Actual producer fixture for the shared current-source recovery interface."""
    from test_reader_restructure import split_draft
    root,_,chapter=case
    final=completed_preview(case)[1] if logical_kind else owner.preview('book','first','presentation-split',split_draft(case),root)
    target=owner._snapshot('book','first',root)['paths']['provenance'];store=owner._store
    with monkeypatch.context() as outage:
        def fail(project,root,path,*args,**kwargs):
            if path==target:raise OSError('metadata unavailable')
            return store(project,root,path,*args,**kwargs)
        outage.setattr(owner,'_store',fail);partial=apply(case,final)
    chapter.write_bytes(chapter.read_bytes().replace(b'First sentence.',b'Later human edit.'))
    if line_shift:chapter.write_bytes(b'% Later preamble line\n'+chapter.read_bytes())
    current=chapter.read_bytes();ready=owner.read('book',partial['reconciliation_read']['payload'],root)
    needs_input=copy.deepcopy(ready)
    if ready['metadata_reconciliation']['status']=='NEEDS_INPUT':
        view=ready['metadata_reconciliation'];assignments=[]
        for expected in view['occurrence_inventory']:
            selected=next(row for row in view['current_occurrence_choices'] if row['line_start']==expected['line_start']+1)
            assignments.append({'expected_occurrence_id':expected['id'],'current_occurrence_id':selected['id']})
        ready=owner.change('book',{**view['preview_action']['payload'],'current_occurrence_assignments':assignments},root)
    from laplace.manuscript.projection_viewer import parse_paragraphs
    first_marker=parse_paragraphs(current.decode())[0]['spec_ids'][0]
    chapter.write_bytes(current.replace(('% '+first_marker+'\n').encode(),b'% unrelated-p999\n',1))
    unprovable=owner.read('book',partial['reconciliation_read']['payload'],root)
    chapter.write_bytes(current)
    acknowledged=owner.change('book',ready['metadata_reconciliation']['action']['payload'],root)
    assert acknowledged['complete'] and acknowledged['metadata_only'] and chapter.read_bytes()==current
    assert not acknowledged.get('error') and not acknowledged.get('recovery_action')
    return {'partial':partial,'ready':ready,'unprovable':unprovable,'acknowledged':acknowledged,'needs_input':needs_input}


def test_native_current_source_reconciliation_keeps_historical_effect_and_real_actor(case,monkeypatch):
    from laplace.native import tools as writing_tools
    from laplace.core import grammar
    from laplace.writing import records
    root,_,chapter=case
    # Prepare actual retained pending receipt, then use native inspect/adopt.
    final=completed_preview(case)[1];target=owner._snapshot('book','first',root)['paths']['provenance'];store=owner._store
    with monkeypatch.context() as outage:
        def fail(project,root,path,*args,**kwargs):
            if path==target:raise OSError('metadata unavailable')
            return store(project,root,path,*args,**kwargs)
        outage.setattr(owner,'_store',fail);partial=apply(case,final)
    chapter.write_bytes(chapter.read_bytes().replace(b'First sentence.',b'Later human edit.'));physical=chapter.read_bytes()
    caller='WT-reconciliation';records.bank(root,{'record':'writing-turn','id':caller,'project':'book','mode':'work'})
    response=writing_tools.call(root,'book','work',partial['reconciliation_read']['native_request'],turn_id=caller)
    assert response.get('ok'),response
    native=response['owner_response'];assert native['metadata_reconciliation']['status']=='READY'
    assert len(json.dumps(response,ensure_ascii=False,indent=2).encode())<14000
    action=native['metadata_reconciliation']['action']['native_request']
    ack=writing_tools.call(root,'book','work',action,turn_id=caller)
    assert ack.get('ok'),ack
    value=ack['owner_response'];assert value['complete'] and value['metadata_only']
    assert value['action_receipt']['status']=='RECORDED' and value['action_receipt']['metadata_only']
    assert value['action_receipt']['source_currentness']=='HISTORICAL_EFFECT_WITH_SEPARATE_CURRENT_OBSERVATION'
    actual=owner._receipt('book',root,value['receipt']['id'],value['receipt']['intent_artifact_id'])
    assert actual['metadata_reconciliation']['actor']['turn_id']==caller
    assert value['source_effect']==partial['source_effect'] and chapter.read_bytes()==physical


def test_attachment_order_and_native_contract_are_stable_across_fresh_processes(case):
    import os, subprocess
    root,_,_=case;path=owner._snapshot('book','first',root)['paths']['narrative']
    document=json.loads(path.read_text());document['paragraphs'][0].update(
        qualification='Exact scope',from_previous='Prior bridge',to_next='Next bridge',citations=['bib:one'],input_nodes=['concept:first'])
    path.write_text(json.dumps(document))
    script="""import json,sys,hashlib
from pathlib import Path
from laplace.manuscript import reader_restructure as owner
value=owner.preview('book','first','logical-split',{'paragraph_ids':['first-p1']},Path(sys.argv[1]))
print(json.dumps({'token':value['restructure_token'],'guards':value['guards'],'ids':[row['id'] for row in value['attachment_inventory']]},sort_keys=True))
"""
    outputs=[]
    for seed in ('1','61'):
        result=subprocess.run(['./scripts/laplace-python','-c',script,str(root)],env={**os.environ,'PYTHONHASHSEED':seed},capture_output=True,text=True,check=True)
        outputs.append(result.stdout)
    assert outputs[0]==outputs[1]


def test_current_metadata_adoption_qualifies_unavailable_old_history_instead_of_fabricating_it(case,monkeypatch):
    root,_,chapter=case;_,final=completed_preview(case)
    from laplace.manuscript import projection_viewer
    with monkeypatch.context() as outage:
        outage.setattr(projection_viewer,'bank_editor_save',lambda *a,**k:(_ for _ in ()).throw(OSError('history unavailable')))
        pending=apply(case,final)
    assert not pending['complete'] and pending['source_effect']['state']=='COMMITTED'
    chapter.write_bytes(chapter.read_bytes().replace(b'First sentence.',b'Later human edit.'));physical=chapter.read_bytes()
    inspected=owner.read('book',pending['reconciliation_read']['payload'],root)['metadata_reconciliation']
    assert inspected['status']=='READY'
    result=owner.change('book',inspected['action']['payload'],root)
    assert result['complete'] and result['metadata_only'] and chapter.read_bytes()==physical
    assert any(row['kind']=='ORIGINAL_SOURCE_HISTORY_UNAVAILABLE' for row in result['review_obligations'])
    assert not projection_viewer._load_saves_index(case[1]).get('saves')
    assert result['source_effect']==pending['source_effect']


@pytest.mark.parametrize('logical_kind,shift',[(False,1),(False,3),(True,1)])
def test_line_shift_current_recovery_uses_exact_unique_bindings_or_explicit_occurrence_choices(case,monkeypatch,logical_kind,shift):
    from test_reader_restructure import split_draft
    root,_,chapter=case
    final=completed_preview(case)[1] if logical_kind else owner.preview('book','first','presentation-split',split_draft(case),root)
    target=owner._snapshot('book','first',root)['paths']['provenance'];store=owner._store
    with monkeypatch.context() as outage:
        def fail(project,root,path,*args,**kwargs):
            if path==target:raise OSError('metadata unavailable')
            return store(project,root,path,*args,**kwargs)
        outage.setattr(owner,'_store',fail);partial=apply(case,final)
    chapter.write_bytes(b'% A later preamble line\n'*shift+chapter.read_bytes());physical=chapter.read_bytes()
    inspected=owner.read('book',partial['reconciliation_read']['payload'],root)['metadata_reconciliation']
    if logical_kind:
        assert inspected['status']=='READY' # Each distinct successor marker set is unique.
    else:
        assert inspected['status']=='NEEDS_INPUT' # Two repeated A groups require a person to choose.
        assert not inspected['current_occurrence_assignments'] # Partial coordinate coincidences cannot infer identity.
        assert not inspected['action'] and inspected['preview_action']
        assignments=[]
        for expected in inspected['occurrence_inventory']:
            chosen=next(row for row in inspected['current_occurrence_choices'] if row['line_start']==expected['line_start']+shift)
            assignments.append({'expected_occurrence_id':expected['id'],'current_occurrence_id':chosen['id']})
        inspected=owner.change('book',{**inspected['preview_action']['payload'],'current_occurrence_assignments':assignments},root)['metadata_reconciliation']
        assert inspected['status']=='READY'
    result=owner.change('book',inspected['action']['payload'],root)
    assert result['complete'] and result['metadata_only'] and chapter.read_bytes()==physical,result
    provenance=json.loads(target.read_text())['paragraphs']
    expected={ (row['after']['line_start'],row['after']['line_end'],tuple(row['after']['spec_ids'])) for row in inspected['relocations'] }
    observed={ (row['source']['line_start'],row['source']['line_end'],tuple(row['spec_ids'])) for row in provenance }
    assert expected<=observed


def test_plan_only_pending_dependency_adoption_never_invents_a_source_effect(case,monkeypatch):
    root,_,chapter=case;chapter.write_text('\\chapter{First}\\label{chapter:first}\n')
    _,final=completed_preview(case);target=owner._snapshot('book','first',root)['paths']['provenance'];store=owner._store
    with monkeypatch.context() as outage:
        def fail(project,root,path,*args,**kwargs):
            if path==target:raise OSError('metadata unavailable')
            return store(project,root,path,*args,**kwargs)
        outage.setattr(owner,'_store',fail);partial=apply(case,final)
    architecture=reader_plan._architecture
    def changed(*args,**kwargs):
        result=copy.deepcopy(architecture(*args,**kwargs));result['effective_projection']['revision']='sha256:'+'a'*64;return result
    monkeypatch.setattr(reader_plan,'_architecture',changed)
    ready=owner.read('book',partial['reconciliation_read']['payload'],root)['metadata_reconciliation']
    assert ready['status']=='READY' and ready['changed_dependencies']
    result=owner.change('book',ready['action']['payload'],root)
    assert result['complete'] and result['metadata_only'] and 'source_effect' not in result
    assert result['source_unchanged'] and any(row['kind']=='CHANGED_LOGICAL_READER_INPUTS' for row in result['review_obligations'])


def test_incomplete_selected_source_traversal_withholds_logical_apply(case):
    root,_,chapter=case;chapter.write_text(chapter.read_text()+'\\input{missing-source-part}\n')
    value=owner.preview('book','first','logical-split',{'paragraph_ids':['first-p1']},root)
    assert not value['ready'] and not value['apply_action'] and value['inventory_diagnostics']
    assert any(row['kind']=='OCCURRENCE_COVERAGE' for row in value['needs_input'])


def larger_reconciliation_case(case,monkeypatch,count=120):
    """One actual repeated-group owner preview, no fake inventory or root state."""
    from test_reader_restructure import n_part_draft
    root,_,chapter=case
    final=owner.preview('book','first','presentation-split',n_part_draft(case,count),root)
    target=owner._snapshot('book','first',root)['paths']['provenance'];store=owner._store
    with monkeypatch.context() as outage:
        def fail(project,root,path,*args,**kwargs):
            if path==target:raise OSError('metadata unavailable')
            return store(project,root,path,*args,**kwargs)
        outage.setattr(owner,'_store',fail);partial=apply(case,final)
    chapter.write_bytes(b'% Later preamble line\n'+chapter.read_bytes())
    inspected=owner.read('book',partial['reconciliation_read']['payload'],root)
    assert inspected['metadata_reconciliation']['status']=='NEEDS_INPUT'
    return {'partial':partial,'inspected':inspected}


def test_repeated_current_choices_use_one_linear_eligibility_table(case,monkeypatch):
    value=larger_reconciliation_case(case,monkeypatch)['inspected']['metadata_reconciliation']
    assert len(value['occurrence_inventory'])==120 and len(value['current_occurrence_choices'])==120
    assert len(value['current_occurrence_groups'])==1
    group=value['current_occurrence_groups'][0]
    assert len(group['choice_ids'])==120
    assert all(row['allowed_current_occurrence_group_id']==group['id'] and 'allowed_current_occurrence_ids' not in row for row in value['occurrence_inventory'])
    assert len(json.dumps(value).encode())<120*2500


def retained_operation_case(case):
    root,_,chapter=case;original=chapter.read_bytes()
    saved=apply(case,completed_preview(case)[1]);assert saved['complete']
    summary=owner.latest_operation('book','first',root)
    inspected=owner.read('book',summary['read_handle']['payload'],root)
    assert inspected['inverse_currentness']['status']=='CURRENT' and inspected['undo_action']['title']=='Undo this structural operation'
    inverse=owner.change('book',inspected['undo_action']['payload'],root)
    assert inverse['complete'] and chapter.read_bytes()==original
    inverse_summary=owner.latest_operation('book','first',root)
    inverse_read=owner.read('book',inverse_summary['read_handle']['payload'],root)
    assert inverse_read['inverse_currentness']['status']=='CURRENT' and inverse_read['undo_action']['title']=='Redo this structural operation'
    chapter.write_bytes(chapter.read_bytes().replace(b'First sentence.',b'A later human edit.'))
    changed=owner.read('book',inverse_summary['read_handle']['payload'],root)
    assert changed['inverse_currentness']['status']=='CHANGED' and not changed.get('undo_action')
    return {'summary':summary,'inspected':inspected,'inverse':inverse,'inverse_summary':inverse_summary,'inverse_read':inverse_read,'changed':changed}


def test_completed_operation_is_compact_lazy_discoverable_and_inverse_is_rechecked(case,monkeypatch):
    root,_,chapter=case
    saved=apply(case,completed_preview(case)[1]);assert saved['complete']
    with monkeypatch.context() as lazy:
        lazy.setattr(owner,'_intent',lambda *a,**k:pytest.fail('Section summary hydrated immutable body'))
        lazy.setattr(owner,'_snapshot',lambda *a,**k:pytest.fail('Section summary hydrated current reader state'))
        summary=owner.latest_operation('book','first',root)
    assert summary['currentness']['status']=='NOT_REOBSERVED' and len(json.dumps(summary).encode())<2500
    assert 'guards' not in summary and 'source_effect' not in summary and 'undo_action' not in summary
    inspected=owner.read('book',summary['inverse_inspection_read']['payload'],root)
    assert inspected['receipt']['id']==saved['receipt']['id'] and inspected['inverse_currentness']['status']=='CURRENT'
    assert inspected['undo_action']['title']=='Undo this structural operation'
    snapshot=owner._snapshot('book','first',root)
    plan=reader_plan.section_view('book',root,snapshot['section'],snapshot['state']['sections'],snapshot['state']['authority']['plan_revision'])['paragraph_plan']
    assert plan['latest_restructure']['receipt']['id']==saved['receipt']['id']
    assert all('latest_restructure' not in row for row in plan['paragraphs']['items'])
    chapter.write_bytes(chapter.read_bytes()+b'% Later source change\n')
    changed=owner.read('book',summary['read_handle']['payload'],root)
    assert changed['inverse_currentness']['status']=='CHANGED' and not changed.get('undo_action')
    assert changed['undo_unavailable']


def test_owner_derived_direction_survives_close_reopen_and_read_only_inspection(case):
    value=retained_operation_case(case)
    assert value['inspected']['inverse_direction']=='UNDO' and value['inverse_read']['inverse_direction']=='REDO'


def test_shared_text_chunk_eof_is_explicit_without_certifying_whole_text():
    from laplace.manuscript.reconciliation import _text_part
    text='λ'*(37774//2)
    value,end=_text_part(text,34526)
    assert end==37774 and value['coverage']['end']==value['coverage']['total']
    assert value['coverage']['complete'] is False
    assert value['coverage']['at_end'] is True and value['coverage']['has_more'] is False
    first,_=_text_part(text,0)
    assert first['coverage']['complete'] is False and first['coverage']['has_more'] is True and not first['coverage']['at_end']


def test_historical_parts_do_not_mix_live_inverse_generations(case):
    from laplace.core import grammar
    root,_,chapter=case;result=apply(case,completed_preview(case)[1])
    query={**result['read_handle']['payload'],'part':'logical','offset':0}
    first=owner.native_projection(owner.read('book',query,root),query)
    expected=first['coverage']['sha256'];chunks=[first['content']]
    chapter.write_bytes(chapter.read_bytes()+b'% A later human source change\n')
    live=owner.read('book',result['read_handle']['payload'],root)
    assert live['inverse_currentness']['status']=='CHANGED' and not live.get('undo_action')
    part=first
    while part.get('next_read'):
        query=grammar.to_owner_payload(part['next_read']['native_request']['payload'])
        part=owner.native_projection(owner.read('book',query,root),query)
        assert part['coverage']['sha256']==expected
        chunks.append(part['content'])
    assert part['coverage']['at_end'] and not part['coverage']['has_more'] and not part.get('next_read')
    value=json.loads(''.join(chunks))
    assert 'inverse_currentness' not in value and value['action_currentness'].startswith('AS_RECORDED_ONLY')
    assert value['retained_operation']['source_changes']
    with pytest.raises(ValueError,match='another declared section'):
        owner.read('book',{**query,'section_ids':['second']},root)


def test_compact_dispositions_keep_exact_qualification_and_counts_without_history_bodies(case):
    root,_,_=case;path=owner._snapshot('book','first',root)['paths']['narrative'];document=json.loads(path.read_text())
    document['paragraphs'][0]['qualification']='This is a workflow example, not scientific acceptance.';path.write_text(json.dumps(document))
    result=apply(case,completed_preview(case)[1]);value=owner.read('book',result['read_handle']['payload'],root)
    summary=value['disposition_summary']
    assert summary['basis']['intent_artifact_id']==result['receipt']['intent_artifact_id']
    assert summary['attachment_count']==1 and summary['disposition_counts']['assign']==1
    assert summary['qualifications'][0]['value']==document['paragraphs'][0]['qualification']
    assert summary['coverage']['qualifications_complete'] and summary['old_reviews']=='HISTORICAL_ONLY'
    assert len(json.dumps(summary,ensure_ascii=False,separators=(',',':')).encode())<=2400
    projected=owner.native_projection(value,result['read_handle']['payload'])
    assert projected['disposition_summary']==summary and projected['inverse_currentness']['status']=='CURRENT'
    assert len(json.dumps(projected,ensure_ascii=False,indent=2).encode())<14000


def _feedback_attachment_case(case):
    root, home, chapter = case
    feedback = home/'feedback/feedback.jsonl'; feedback.parent.mkdir(parents=True, exist_ok=True)
    rows = [{'record': kind, 'id': ident, 'project': 'book', 'kind': 'author-rewrite' if kind=='author-edit' else 'note',
        'file': chapter.relative_to(root).as_posix(), 'anchor': {'paragraph_id': 'first-p1', 'spec_ids': ['first-p1']},
        'text': 'Exact original attachment body'} for kind, ident in [('author-edit', 'EDIT-original'), ('note', 'NOTE-original')]]
    feedback.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    path = owner._snapshot('book','first',root)['paths']['narrative']
    document=json.loads(path.read_text());document['paragraphs'][0]['qualification']='Prior scope'
    path.write_text(json.dumps(document))
    return path


def _attachment_preview(case, kind, selected, disposition='assign', *, both=False):
    initial, final = completed_preview(case,kind,selected)
    draft=copy.deepcopy(final['draft'])
    for assignment in draft['attachment_assignments']:
        item=next(row for row in initial['attachment_inventory'] if row['id']==assignment['attachment_id'])
        if item['kind'] in {'note','protection'}:
            assignment.update(disposition=disposition, successor_ids=final['successor_ids'] if disposition=='assign' and both else
                final['successor_ids'][:1] if disposition=='assign' else [])
    return initial,owner.preview('book','first',kind,draft,case[0])


def test_carried_typed_refs_split_merge_cycles_are_flat_and_retained_cost_linear(case):
    from laplace.writing import records
    from laplace.writing.records._index import MetadataIndex
    root,_,_=case;_feedback_attachment_case(case)
    selected=['first-p1'];sizes=[];totals=[];counts=[]
    for cycle in range(4):
        cycle_sizes=[]
        for kind in ('logical-split','logical-merge'):
            initial,final=_attachment_preview(case,kind,selected,both=True)
            assert not any(row['field']=='attachment_refs' or row.get('origin_unavailable') for row in initial['attachment_inventory'])
            typed=[row for row in initial['attachment_inventory'] if row['kind'] in {'note','protection'}]
            assert len(typed)==2 and {row['record_id'] for row in typed}=={'EDIT-original','NOTE-original'}
            counts.append(len(initial['attachment_inventory']))
            result=apply(case,final);assert result['complete'],result
            intent=owner._intent('book',root,result['receipt']['intent_artifact_id'])
            cycle_sizes.append(len(json.dumps(intent).encode()))
            selected=result['successor_ids']
            index=records.index(root);expected=dict(index.reader_unit_creations)
            scans=index.stats['scans'];assert records.index(root) is index
            assert index.stats['scans']==scans and index.reader_unit_creations==expected
            assert MetadataIndex(root).advance().reader_unit_creations==expected
        sizes.append(sum(cycle_sizes))
        totals.append(sum(path.stat().st_size for path in root.rglob('*') if path.is_file()))
    increments=[b-a for a,b in zip(totals,totals[1:])]
    assert max(sizes[1:]) < min(sizes[1:])*1.04,(sizes,totals,counts)
    assert max(increments) < min(increments)*1.06,(sizes,totals,counts)
    current=owner._snapshot('book','first',root)['rows'][0]
    assert current['qualification']=='Prior scope'
    assert len(current['attachment_refs'])==3
    assert all(set(ref)<= {'id','kind','pin','owner','record_id','paragraph_ids'} for ref in current['attachment_refs'])
    print(json.dumps({'intent_bytes_per_split_merge':sizes,'retained_bytes':totals,'increments':increments,'inventory_counts':counts}))


def test_retired_refs_stay_retired_and_unresolved_empty_scope_stays_visible(case):
    _feedback_attachment_case(case)
    _,final=_attachment_preview(case,'logical-split',['first-p1'],disposition='retain-unresolved')
    saved=apply(case,final);assert saved['complete']
    pending=owner.preview('book','first','logical-merge',{'paragraph_ids':saved['successor_ids']},case[0])
    refs=[row for row in pending['attachment_inventory'] if row['kind'] in {'note','protection'}]
    assert len(refs)==2 and all(row['prior_disposition']=='retain-unresolved' for row in refs)
    assert all(len(row['prior_dispositions'])==2 and all(w['scope_unresolved'] for w in row['prior_dispositions']) for row in refs)
    _,final=_attachment_preview(case,'logical-merge',saved['successor_ids'],disposition='retain-retired')
    merged=apply(case,final);assert merged['complete']
    current=owner.preview('book','first','logical-split',{'paragraph_ids':merged['successor_ids']},case[0])
    assert not any(row['kind'] in {'note','protection'} or row['field']=='unlinked_feedback' for row in current['attachment_inventory'])
    historical=owner._intent('book',case[0],merged['receipt']['intent_artifact_id'])
    assert sum(row['disposition']=='retain-retired' for row in historical['attachment_dispositions'])==2


def test_branch_disposition_witnesses_are_not_first_branch_wins(case):
    _feedback_attachment_case(case)
    _,final=_attachment_preview(case,'logical-split',['first-p1'],both=True)
    saved=apply(case,final);left,right=saved['successor_ids']
    _,final=_attachment_preview(case,'logical-split',[left],disposition='retain-unresolved')
    branch=apply(case,final);selected=[branch['successor_ids'][0],right]
    merged=owner.preview('book','first','logical-merge',{'paragraph_ids':selected},case[0])
    refs=[row for row in merged['attachment_inventory'] if row['kind'] in {'note','protection'}]
    assert len(refs)==2
    for ref in refs:
        assert ref['prior_disposition']=='MIXED'
        assert {row['paragraph_id']:row['disposition'] for row in ref['prior_dispositions']}=={
            selected[0]:'retain-unresolved',right:'assign'}


def test_unverified_flat_reference_is_explicit_not_an_opaque_container(case):
    path=_feedback_attachment_case(case);document=json.loads(path.read_text())
    document['paragraphs'][0]['attachment_refs']=[{'id':'ATT-missing','pin':'sha256:missing','kind':'note','owner':'feedback','record_id':'NOTE-missing'}]
    path.write_text(json.dumps(document))
    initial=owner.preview('book','first','logical-split',{'paragraph_ids':['first-p1']},case[0])
    unavailable=[row for row in initial['attachment_inventory'] if row.get('origin_unavailable')]
    assert len(unavailable)==1 and unavailable[0]['value']['id']=='ATT-missing'
    assert unavailable[0]['field']!='attachment_refs' and unavailable[0]['read']


@pytest.mark.parametrize('disposition',['retain-retired','assign'])
def test_released_opaque_refs_retired_by_merge_are_not_silently_readopted(case,monkeypatch,disposition):
    from laplace.manuscript import reader_logical_publication as publication
    _feedback_attachment_case(case)
    _,final=_attachment_preview(case,'logical-split',['first-p1'],both=True)
    split=apply(case,final);assert split['complete']
    original=publication.inputs
    # Reproduce the released field ingestion using only this tiny fixture's
    # actual generated rows. Its explicit retired choice remains authoritative.
    def released(*args,**kwargs):
        value=original(*args,**kwargs)
        value['attachments']=[row for row in value['attachments'] if row['kind'] not in {'note','protection'}]
        selected=args[2]['paragraph_ids']
        for row in value['snapshot']['rows']:
            if row['paragraph_id'] in selected:
                refs=row.get('attachment_refs') or []
                value['attachments'].append(publication._attachment('book','first',row['paragraph_id'],
                    'attachment_refs',refs,'legacy',pin=publication.logical.fingerprint(refs),
                    read=reader_plan.read_handle('book','first',paragraph_id=row['paragraph_id'])))
        return value
    with monkeypatch.context() as old:
        old.setattr(publication,'inputs',released)
        initial,final=completed_preview(case,'logical-merge',split['successor_ids'])
        draft=copy.deepcopy(final['draft'])
        legacy_ids={row['id'] for row in initial['attachment_inventory'] if row['field']=='attachment_refs'}
        assert len(legacy_ids)==2
        for row in draft['attachment_assignments']:
            if row['attachment_id'] in legacy_ids:row.update(disposition=disposition,successor_ids=[] if disposition=='retain-retired' else final['successor_ids'])
        final=owner.preview('book','first','logical-merge',draft,case[0]);merged=apply(case,final)
        assert merged['complete'],merged
    current=owner.preview('book','first','logical-split',{'paragraph_ids':merged['successor_ids']},case[0])
    assert not any(row['kind'] in {'note','protection'} or row['field'] in {'attachment_refs','unlinked_feedback'} for row in current['attachment_inventory'])
    unavailable=[row for row in current['attachment_inventory'] if row.get('origin_unavailable')]
    assert len(unavailable)==(0 if disposition=='retain-retired' else 2)
    assert all(isinstance(row['value'],dict) and row['value']['origin_intent_artifact_id']==merged['receipt']['intent_artifact_id'] for row in unavailable)
    old=owner._intent('book',case[0],merged['receipt']['intent_artifact_id'])
    assert sum(row['attachment_id'] in legacy_ids and row['disposition']==disposition for row in old['attachment_dispositions'])==2
