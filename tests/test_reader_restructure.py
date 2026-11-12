"""Scoped paragraph owner proofs over tiny explicit source/reader artifacts."""
import json
import pytest
from laplace.manuscript import reader_restructure as owner, reader_plan
from laplace.manuscript import manuscript_source
from test_manuscript_structure import _section_fixture


@pytest.fixture
def case(tmp_path,monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE',str(tmp_path/'state'))
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES',str(tmp_path/'workspaces'))
    manuscript,chapter,_=_section_fixture(tmp_path)
    chapter.write_text('\\chapter{First}\\label{chapter:first}\n% PLAN:first\n% first-p1\nFirst sentence. Second sentence.\n\n% first-p1\n% first-p2\nOther sentence. Last sentence.\n')
    _,path=reader_plan._paths('book',tmp_path,'first');path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'section_id':'first','paragraphs':[
        {'section_id':'first','paragraph_id':'first-p1','function':'Introduce','proposition':'One'},
        {'section_id':'first','paragraph_id':'first-p2','function':'Explain','proposition':'Two'}]}))
    return tmp_path,manuscript,chapter


def split_draft(case):
    root,_,chapter=case
    return {'paragraph_ids':['first-p1'],'source_edits':[{'file':chapter.relative_to(root).as_posix(),
        'line_start':4,'line_end':4,'before':'First sentence. Second sentence.',
        'after':'First sentence.\n\nSecond sentence.',
        'expected_source_digest':owner.revision(chapter.read_bytes()),
        'expected_selection':manuscript_source.selection_identity(manuscript_source.resolve('book',repo_root=root),'book')}],
        'parts':['First sentence.','Second sentence.']}


def test_preview_repeats_complete_logical_identity_and_keeps_source_read_only(case):
    root,_,chapter=case;before=chapter.read_bytes()
    value=owner.preview('book','first','presentation-split',split_draft(case),root)
    assert chapter.read_bytes()==before and value['preview_only']
    assert [row['spec_ids'] for row in value['occurrence_mapping']['after']]==[['first-p1'],['first-p1']]
    assert value['source_changes'][0]['after'].count('% first-p1')==2
    assert set(value['guards'])==set(owner.GUARDS)
    assert 'before' not in value['apply_action']['payload']


def apply(case,value):
    return owner.change('book',{**value['apply_action']['payload'],'draft':value['draft']},case[0])


def test_real_split_publication_and_guarded_structural_inverse(case):
    root,_,chapter=case;before=chapter.read_bytes()
    value=owner.preview('book','first','presentation-split',split_draft(case),root)
    result=apply(case,value)
    assert result['complete'] and result['source_effect']['state']=='COMMITTED'
    assert result['plan_publication']['complete'] and result['receipt']['id'].startswith('RPUB-')
    assert chapter.read_text().count('% first-p1')==3
    undone=owner.change('book',result['undo_action']['payload'],root)
    assert undone['complete'] and chapter.read_bytes()==before


def test_committed_source_pending_metadata_recovers_without_rewrite(case,monkeypatch):
    root,_,chapter=case
    value=owner.preview('book','first','presentation-split',split_draft(case),root)
    store=owner._store
    target=owner._snapshot('book','first',root)['paths']['provenance']
    with monkeypatch.context() as outage:
        def fail(project,root,path,*args,**kwargs):
            if path==target:raise OSError('Simulated provenance publication failure')
            return store(project,root,path,*args,**kwargs)
        outage.setattr(owner,'_store',fail)
        pending=apply(case,value)
    assert pending['source_effect']['state']=='COMMITTED' and not pending['complete']
    assert pending['plan_publication']['status']=='PARTIAL' and pending['remaining_steps']==['provenance-publication']
    physical=chapter.read_bytes()
    from laplace.manuscript import manuscript_structure
    monkeypatch.setattr(manuscript_structure,'_write_source',lambda *a,**k:pytest.fail('Recovery replayed committed source'))
    finished=owner.change('book',pending['recovery_action']['payload'],root)
    assert finished['complete'] and chapter.read_bytes()==physical
    assert finished['source_receipt_id']==pending['source_receipt_id']


def test_split_preserves_other_occurrence_of_same_id_and_complete_provenance_fields(case):
    root,_,chapter=case
    path=owner._snapshot('book','first',root)['paths']['provenance'];path.parent.mkdir(parents=True,exist_ok=True)
    file=chapter.relative_to(root).as_posix()
    first={'spec_id':'first-p1','spec_ids':['first-p1'],'source':{'file':file,'line_start':3,'line_end':4},'qualification':'Exact first occurrence','custom_field':{'kept':True}}
    sibling={'spec_id':'first-p1','spec_ids':['first-p1','first-p2'],'source':{'file':file,'line_start':6,'line_end':8},'qualification':'Independent A+B occurrence','nodes_realised':['node:one','node:two']}
    path.write_text(json.dumps({'section_id':'first','paragraphs':[first,sibling]}))
    value=owner.preview('book','first','presentation-split',split_draft(case),root)
    result=apply(case,value);assert result['complete']
    rows=json.loads(path.read_text())['paragraphs']
    unchanged=next(row for row in rows if row['spec_ids']==['first-p1','first-p2'])
    assert unchanged['qualification']==sibling['qualification'] and unchanged['nodes_realised']==sibling['nodes_realised']
    assert unchanged['source']['line_start']==9 and unchanged['source']['line_end']==11
    split=[row for row in rows if row['spec_ids']==['first-p1']]
    assert len(split)==2 and all(row['custom_field']==first['custom_field'] for row in split)


def test_reader_identity_is_not_a_required_plan_comment_in_source(case):
    root,_,chapter=case;chapter.write_text(chapter.read_text().replace('% PLAN:first\n',''))
    draft=split_draft(case);edit=draft['source_edits'][0];edit.update(line_start=3,line_end=3,expected_source_digest=owner.revision(chapter.read_bytes()))
    value=owner.preview('book','first','presentation-split',draft,root)
    assert value['section_id']=='first' and value['occurrence_mapping']['before'][0]['section']==''


def test_inverse_restores_absence_and_next_operation_is_usable(case):
    root,_,_=case;target=owner._snapshot('book','first',root)['paths']['provenance']
    assert not target.exists()
    result=apply(case,owner.preview('book','first','presentation-split',split_draft(case),root))
    undone=owner.change('book',result['undo_action']['payload'],root)
    assert undone['complete'] and not target.exists()
    assert owner.preview('book','first','presentation-split',split_draft(case),root)['apply_action']


@pytest.mark.parametrize('failed_bank',[1,2])
def test_receipt_outage_retains_physical_effect_and_fresh_exact_recovery(case,monkeypatch,failed_bank):
    root,_,chapter=case;bank=owner._record_receipt;calls=0
    with monkeypatch.context() as outage:
        def fail(*args,**kwargs):
            nonlocal calls
            calls+=1
            if calls==failed_bank:raise OSError('Simulated receipt outage')
            return bank(*args,**kwargs)
        outage.setattr(owner,'_record_receipt',fail)
        prepared=owner.preview('book','first','presentation-split',split_draft(case),root)
        pending=apply(case,prepared)
    assert pending['source_effect']['state']=='COMMITTED' and not pending['complete']
    physical=chapter.read_bytes()
    from laplace.writing import records
    records.indexes.clear()
    retained=owner.pending('book','first',root)
    assert len(retained)==1 and retained[0]['receipt']['intent_artifact_id']==pending['receipt']['intent_artifact_id']
    with pytest.raises(ValueError,match='pending structural'):
        apply(case,prepared)
    from laplace.manuscript import manuscript_structure
    monkeypatch.setattr(manuscript_structure,'_write_source',lambda *a,**k:pytest.fail('Physical source replay'))
    recovered=owner.change('book',retained[0]['recovery_action']['payload'],root)
    assert recovered['complete'] and chapter.read_bytes()==physical
    assert not owner.pending('book','first',root)


def test_post_commit_guard_failure_is_saved_source_with_pending_recovery(case,monkeypatch):
    root,_,chapter=case;publish=owner._complete_metadata
    with monkeypatch.context() as outage:
        outage.setattr(owner,'_complete_metadata',lambda *a,**k:(_ for _ in ()).throw(ValueError('CHANGED_INPUT simulated metadata race')))
        pending=apply(case,owner.preview('book','first','presentation-split',split_draft(case),root))
    assert pending['source_effect']['state']=='COMMITTED' and pending['recovery_action'] and not pending['complete']
    assert 'CHANGED_INPUT' in pending['error']
    recovered=owner.change('book',pending['recovery_action']['payload'],root)
    assert recovered['complete']


def test_repeated_small_split_inverse_has_linear_individual_intent_storage(case):
    root,_,chapter=case;original=chapter.read_bytes();sizes=[]
    from laplace.writing import records
    for _ in range(6):
        result=apply(case,owner.preview('book','first','presentation-split',split_draft(case),root))
        owner.change('book',result['undo_action']['payload'],root)
        assert chapter.read_bytes()==original
        meta=records.index(root).reader_restructure_intents[('book','first')]
        body=records.selected_journal_fields('book',meta['id'],root,fields=['after'])['after']
        intent=json.loads(body);sizes.append(len(body.encode()))
        assert 'provenance_before' not in intent and 'provenance_after' not in intent
        current=owner._snapshot('book','first',root)['documents']['decisions']['decisions']
        assert len([row for row in current if row.get('owner')=='reader-restructure'])==1
        assert 'intent' not in current[-1]
    assert max(sizes)<min(sizes)*1.05 and max(sizes)<8000


def test_owner_walk_lease_uses_declared_reader_and_exact_physical_source(case):
    root,_,chapter=case;chapter.write_text(chapter.read_text().replace('% PLAN:first\n',''))
    source=manuscript_source.resolve('book',repo_root=root)
    sections=[{'blocks':[{'kind':'para','spec_ids':['first-p1'],
        'src':{'repo_file':chapter.relative_to(root).as_posix(),'line_start':3,'line_end':3}}]}]
    pending=owner.annotate_walk('book',root,sections,source,manuscript_source.traversal(source['root'],root))
    handle=sections[0]['blocks'][0]['restructure_preview']
    assert not pending and handle['payload']['section_id']=='first'
    assert handle['payload']['source_guards'][chapter.relative_to(root).as_posix()]==owner.revision(chapter.read_bytes())
    assert 'before' not in json.dumps(handle)


@pytest.mark.parametrize('count',[20,1000])
def test_actual_native_large_preview_is_bounded_and_exact_parts_join(case,count):
    from laplace.native import tools as writing_tools
    from laplace.core import grammar
    from laplace.writing import records
    root,_,chapter=case;text=('alpha beta gamma delta '*count).strip()
    chapter.write_text('\\chapter{First}\\label{chapter:first}\n% PLAN:first\n% first-p1\n'+text+'\n')
    cut=len(text)//2;cut=text.index(' ',cut)
    parts=[text[:cut],text[cut+1:]]
    draft=split_draft(case);draft['source_edits'][0].update(before=text,after='\n\n'.join(parts));draft['parts']=parts
    caller='WT-structure';records.bank(root,{'record':'writing-turn','id':caller,'project':'book','mode':'discuss'})
    request={'verb':'read','concept':'plan@plan','target':'book','expected':[],
        'payload':grammar.to_payload({'view':'restructure','section_ids':['first'],'kind':'presentation-split','draft':draft}),'by':''}
    answer=writing_tools.call(root,'book','discuss',request,turn_id=caller)
    assert answer.get('ok'),answer
    assert len(json.dumps(answer,ensure_ascii=False,indent=2).encode())<14000
    value=answer['owner_response'];assert 'draft' not in value and 'before' not in value['source_changes'][0]
    chunks=[];handle=value['source_changes'][0]['text_reads']['after']
    while handle:
        part=writing_tools.call(root,'book','discuss',handle['native_request'],turn_id=caller)
        assert part.get('ok'),part
        assert len(json.dumps(part,ensure_ascii=False,indent=2).encode())<14000
        part=part['owner_response'];chunks.append(part['content']);handle=part.get('next_read')
    assert ''.join(chunks)==owner.preview('book','first','presentation-split',draft,root)['source_changes'][0]['after']


def test_join_unions_complete_ids_and_inverse_restores_all_bytes_and_fields(case):
    root,_,chapter=case;before=chapter.read_bytes();split=split_draft(case);lease=split['source_edits'][0]
    draft={'paragraph_ids':['first-p1','first-p2'],'source_edits':[
        {**lease,'after':'First sentence. Second sentence. Other sentence. Last sentence.'},
        {**lease,'line_start':8,'line_end':8,'before':'Other sentence. Last sentence.','after':''}]}
    value=owner.preview('book','first','presentation-join',draft,root)
    assert value['occurrence_mapping']['after'][0]['spec_ids']==['first-p1','first-p2']
    result=apply(case,value);assert result['complete']
    undone=owner.change('book',result['undo_action']['payload'],root)
    assert undone['complete'] and chapter.read_bytes()==before


def test_tagged_untagged_join_retains_body_and_reports_unreviewed_content(case):
    root,_,chapter=case
    chapter.write_text('\\chapter{First}\\label{chapter:first}\n% PLAN:first\n% first-p1\nFirst sentence. Second sentence.\n\nUnmarked tail.\n')
    lease=split_draft(case)['source_edits'][0]
    draft={'paragraph_ids':['first-p1'],'source_edits':[
        {**lease,'after':'First sentence. Second sentence. Unmarked tail.'},
        {**lease,'line_start':6,'line_end':6,'before':'Unmarked tail.','after':''}]}
    value=owner.preview('book','first','presentation-join',draft,root)
    assert value['occurrence_mapping']['before'][1]['spec_ids']==[]
    assert value['review_obligations'][0]['kind']=='UNATTRIBUTED_SOURCE_JOINED'
    result=apply(case,value);assert result['complete'] and 'Unmarked tail.' in chapter.read_text()
    assert result['review_obligations']==value['review_obligations']


def test_native_apply_records_actual_actor_and_exact_inverse_handle(case):
    from laplace.native import tools as writing_tools
    from laplace.core import grammar
    from laplace.writing import records
    root,_,chapter=case;before=chapter.read_bytes();prepared=owner.preview('book','first','presentation-split',split_draft(case),root)
    caller='WT-structural-author';records.bank(root,{'record':'writing-turn','id':caller,'project':'book','mode':'work'})
    request=prepared['apply_action']['native_request'];request['payload']=grammar.to_payload({**grammar.to_owner_payload(request['payload']),'draft':prepared['draft']})
    result=writing_tools.call(root,'book','work',request,turn_id=caller)
    assert result.get('ok'),result
    value=result['owner_response'];assert value['complete'] and value['undo_action']['native_request']
    assert owner._intent('book',root,value['receipt']['intent_artifact_id'])['actor']['turn_id']==caller
    assert chapter.read_bytes()!=before
    undone=writing_tools.call(root,'book','work',value['undo_action']['native_request'],turn_id=caller)
    assert undone.get('ok'),undone
    assert undone['owner_response']['complete'] and chapter.read_bytes()==before


@pytest.mark.parametrize('mode,dispatch',[('work',None),('discuss',None),('revise',None),('review',None),('work','WORK-child')])
def test_native_preview_all_roles_and_parent_only_source_mutation(case,mode,dispatch):
    from laplace.native import tools as writing_tools
    from laplace.core import grammar
    from laplace.writing import records
    root,_,chapter=case;before=chapter.read_bytes();caller='WT-role'
    records.bank(root,{'record':'writing-turn','id':caller,'project':'book','mode':mode,'dispatch_id':dispatch})
    draft=split_draft(case)
    query={'verb':'read','concept':'plan@plan','target':'book','expected':[],
        'payload':grammar.to_payload({'view':'restructure','section_ids':['first'],'kind':'presentation-split','draft':draft}),'by':''}
    preview=writing_tools.call(root,'book',mode,query,turn_id=caller)
    assert preview.get('ok') and chapter.read_bytes()==before,preview
    if mode=='review' or dispatch:
        action=owner.preview('book','first','presentation-split',draft,root)['apply_action']['native_request']
        action['payload']={**action['payload'],'draft':draft}
        denied=writing_tools.call(root,'book',mode,action,turn_id=caller)
        assert not denied.get('ok') and chapter.read_bytes()==before,denied


def test_crlf_and_guard_race_do_not_drop_or_replay_source(case):
    root,_,chapter=case;chapter.write_bytes(chapter.read_bytes().replace(b'\n',b'\r\n'));before=chapter.read_bytes()
    prepared=owner.preview('book','first','presentation-split',split_draft(case),root)
    result=apply(case,prepared);assert result['complete']
    assert b'\r\n% first-p1\r\n' in chapter.read_bytes() and b'\n' not in chapter.read_bytes().replace(b'\r\n',b'')
    assert owner.change('book',result['undo_action']['payload'],root)['complete'] and chapter.read_bytes()==before
    prepared=owner.preview('book','first','presentation-split',split_draft(case),root)
    chapter.write_bytes(chapter.read_bytes()+b'% Concurrent save\r\n');current=chapter.read_bytes()
    with pytest.raises(ValueError,match='CHANGED_INPUT|source file changed'):apply(case,prepared)
    assert chapter.read_bytes()==current


def n_part_draft(case,count,*,multi=False):
    draft=split_draft(case);parts=['Authored paragraph '+str(number)+'.' for number in range(count)]
    if multi:
        draft['paragraph_ids']=['first-p1','first-p2']
        draft['source_edits'][0].update(line_start=8,line_end=8,before='Other sentence. Last sentence.')
    draft['parts']=parts;draft['source_edits'][0]['after']='\n\n'.join(parts)
    return draft


@pytest.mark.parametrize('count',[3,12])
def test_n_part_split_one_effect_retains_complete_multi_ids_and_inverse(case,count):
    root,_,chapter=case;before=chapter.read_bytes();draft=n_part_draft(case,count,multi=True)
    preview=owner.preview('book','first','presentation-split',draft,root)
    assert len(preview['occurrence_mapping']['after'])==count
    assert all(row['spec_ids']==['first-p1','first-p2'] for row in preview['occurrence_mapping']['after'])
    result=apply(case,preview)
    assert result['complete'] and len(result['source_effect']['files'])==1
    assert len(result['remapped_occurrences'])==count and result['source_scope']['line_start']==6
    intent=owner._intent('book',root,result['receipt']['intent_artifact_id'])
    assert len(intent['source_changes'])==1 and len(intent['occurrence_mapping']['after'])==count
    restored=owner.change('book',result['undo_action']['payload'],root)
    assert restored['complete'] and chapter.read_bytes()==before


@pytest.mark.parametrize('parts',[['','Two.','Three.'],['One.',' ','Three.'],['One.','Two.','']])
def test_n_part_empty_draft_is_retained_without_any_source_effect(case,parts):
    root,_,chapter=case;before=chapter.read_bytes();draft=n_part_draft(case,3)
    draft['parts']=parts;draft['source_edits'][0]['after']='\n\n'.join(parts)
    with pytest.raises(ValueError,match='empty paragraph|nonempty physical'):
        owner.preview('book','first','presentation-split',draft,root)
    assert chapter.read_bytes()==before
    assert not owner.pending('book','first',root)


def test_n_part_source_race_preserves_current_source(case):
    root,_,chapter=case;draft=n_part_draft(case,12,multi=True)
    preview=owner.preview('book','first','presentation-split',draft,root)
    chapter.write_bytes(chapter.read_bytes()+b'% Concurrent edit\n');current=chapter.read_bytes()
    with pytest.raises(ValueError,match='CHANGED_INPUT'):apply(case,preview)
    assert chapter.read_bytes()==current


def test_growing_mapping_native_summary_and_exact_parts_stay_bounded(case):
    from laplace.native import tools as writing_tools
    from laplace.core import grammar
    from laplace.writing import records
    root,_,chapter=case;draft=n_part_draft(case,120,multi=True)
    caller='WT-n-part';records.bank(root,{'record':'writing-turn','id':caller,'project':'book','mode':'work'})
    query={'verb':'read','concept':'plan@plan','target':'book','expected':[],
        'payload':grammar.to_payload({'view':'restructure','section_ids':['first'],'kind':'presentation-split','draft':draft}),'by':''}
    read=writing_tools.call(root,'book','work',query,turn_id=caller);assert read.get('ok'),read
    assert len(json.dumps(read,indent=2).encode())<14000
    projected=read['owner_response'];assert projected['occurrence_mapping']['counts']['after']==120
    assert 'remapped_occurrences' not in projected and not projected['occurrence_mapping']['inline']
    chunks=[];handle=projected['occurrence_mapping']['read']
    while handle:
        response=writing_tools.call(root,'book','work',handle['native_request'],turn_id=caller);assert response.get('ok'),response
        assert len(json.dumps(response,indent=2).encode())<14000
        value=response['owner_response'];chunks.append(value['content']);handle=value.get('next_read')
    assert json.loads(''.join(chunks))==owner.preview('book','first','presentation-split',draft,root)['occurrence_mapping']
    import copy
    action=copy.deepcopy(projected['apply_action']['native_request']);action['payload']['draft']=draft
    result=writing_tools.call(root,'book','work',action,turn_id=caller);assert result.get('ok'),result
    assert len(json.dumps(result,indent=2).encode())<14000
    value=result['owner_response'];assert value['complete'] and value['occurrence_mapping']['counts']['after']==120
    idx=__import__('laplace.writing.records',fromlist=['records']).index(root)
    meta=idx.reader_restructure_receipts[('book',value['receipt']['intent_artifact_id'])]['reader_metadata']['restructure']
    assert 'remapped_occurrences' not in meta and meta['occurrence_counts']['after']==120
    receipt_read=value['occurrence_mapping']['read'];parts=[]
    # Historical exact mapping remains addressable after unrelated source drift,
    # without renewing the now-stale inverse/source authority.
    chapter.write_bytes(chapter.read_bytes()+b'% Later source\n')
    while receipt_read:
        result=writing_tools.call(root,'book','work',receipt_read['native_request'],turn_id=caller);assert result.get('ok'),result
        part=result['owner_response'];assert part['source_currentness']=='HISTORICAL_MAPPING_ONLY'
        parts.append(part['content']);receipt_read=part.get('next_read')
    assert len(json.loads(''.join(parts))['after'])==120


def test_legacy_feedback_partial_receipt_stays_readable_and_recovers_missing_metadata(case,monkeypatch):
    from laplace.writing import records
    from laplace.writing.records._index import _metadata
    root,home,chapter=case;feedback=home/'feedback/feedback.jsonl';feedback.parent.mkdir(parents=True,exist_ok=True)
    legacy=(json.dumps({'id':'FB-legacy','project':'book','ts':'2026-10-11T20:57:51Z',
        'source':'synthetic fixture','anchor':chapter.relative_to(root).as_posix(),'supersedes':'','scope':'paragraph',
        'kind':'author-rewrite','node_id':'','section':'first','text':'Preserved synthetic legacy rewrite.',
        'by':'author','status':'resolved','file':'chapters/chapter-01.tex','baseline':{},'counts':{},'hunks':[]})+'\n').encode()
    feedback.write_bytes(legacy)
    prepared=owner.preview('book','first','presentation-split',split_draft(case),root)
    # Reproduce the released extractor mismatch before testing the fixed owner.
    with monkeypatch.context() as old_owner:
        old_owner.setattr(owner,'_protection_index',lambda root,path:records.index(root,path=path.relative_to(root).as_posix(),extractor=_metadata))
        pending=apply(case,prepared)
    physical=chapter.read_bytes()
    assert pending['source_effect']['state']=='COMMITTED' and pending['error']=="'record'"
    assert pending['remaining_steps']==['author-protection','provenance-publication']
    read=owner.read('book',{'view':'restructure','section_ids':['first'],
        'receipt_id':pending['receipt']['id'],'intent_artifact_id':pending['receipt']['intent_artifact_id']},root)
    assert read['error']=="'record'" and read['recovery_action'] and read['source_effect']['state']=='COMMITTED'
    from laplace.manuscript import manuscript_structure, projection_viewer
    versions_before=projection_viewer._load_saves_index(home)['saves']
    monkeypatch.setattr(manuscript_structure,'_write_source',lambda *a,**k:pytest.fail('Recovery replayed the saved split'))
    recovered=owner.change('book',read['recovery_action']['payload'],root)
    assert recovered['complete'] and recovered['receipt']['intent_artifact_id']==pending['receipt']['intent_artifact_id']
    assert recovered['source_receipt_id']==pending['source_receipt_id'] and chapter.read_bytes()==physical
    assert projection_viewer._load_saves_index(home)['saves']==versions_before
    assert feedback.read_bytes().startswith(legacy)
    rows=owner._protection_index(root,feedback).by_id
    assert len(rows['EDIT-RESTRUCT-'+pending['receipt']['intent_artifact_id']])==1


@pytest.mark.parametrize('existing_provenance',[False,True])
def test_native_repeated_undo_redo_keeps_each_operation_direction_and_exact_metadata(case,existing_provenance,monkeypatch):
    from laplace.native import tools as writing_tools
    from laplace.core import grammar
    from laplace.writing import records
    root,_,chapter=case;target=owner._snapshot('book','first',root)['paths']['provenance']
    if existing_provenance:
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps({'section_id':'first','other_metadata':{'keep':'complete values'},'paragraphs':[
            {'spec_ids':['first-p1'],'spec_id':'first-p1','qualification':'Independent A','source':{'file':chapter.relative_to(root).as_posix(),'line_start':3,'line_end':4}},
            {'spec_ids':['first-p1','first-p2'],'spec_id':'first-p1','qualification':'Shared A+B','nodes_realised':['claim:one','claim:two'],
             'source':{'file':'chapters/chapter-01.tex','line_start':6,'line_end':8}}]}))
    before_source=chapter.read_bytes();before_metadata=owner.reader_plan._json(target)[0]
    caller='WT-redo';records.bank(root,{'record':'writing-turn','id':caller,'project':'book','mode':'work'})
    prepared=owner.preview('book','first','presentation-split',n_part_draft(case,3,multi=True),root)
    request=prepared['apply_action']['native_request'];request['payload']=grammar.to_payload({**grammar.to_owner_payload(request['payload']),'draft':prepared['draft']})
    result=writing_tools.call(root,'book','work',request,turn_id=caller);assert result.get('ok'),result
    current=result['owner_response'];after_source=chapter.read_bytes();after_metadata=reader_plan._json(target)[0];sizes=[]
    for number in range(6):
        request=current['undo_action']['native_request']
        result=writing_tools.call(root,'book','work',request,turn_id=caller);assert result.get('ok'),result
        current=result['owner_response'];assert current['complete']
        inverse=number%2==0
        assert chapter.read_bytes()==(before_source if inverse else after_source)
        assert reader_plan._json(target)[0]==(before_metadata if inverse else after_metadata)
        intent=owner._intent('book',root,current['receipt']['intent_artifact_id'])
        assert intent['provenance_direction']==('inverse' if inverse else 'forward')
        sizes.append(len(json.dumps(intent).encode()))
        if number==0:
            # Root's held Undo ART predates the direction field. Resolve that
            # exact historical shape; do not rewrite or replace its journal row.
            original=owner._intent;legacy_id=current['receipt']['intent_artifact_id']
            def legacy(project,root,ident):
                value=original(project,root,ident)
                if ident==legacy_id:value.pop('provenance_direction',None)
                return value
            monkeypatch.setattr(owner,'_intent',legacy)
    assert max(sizes)<min(sizes)*1.05  # Flat one-operation patches, not nested histories.


def test_large_inverse_provenance_restores_contiguous_scope_and_unrelated_rows(case):
    root,_,chapter=case;file=chapter.relative_to(root).as_posix();count=4000
    old={'spec_ids':['first-p1','first-p2'],'qualification':'Full original metadata','source':{'file':file,'line_start':6,'line_end':8}}
    inserted=[{'spec_ids':['first-p1','first-p2'],'qualification':'Part '+str(i),
               'source':{'file':file,'line_start':6+3*i,'line_end':8+3*i}} for i in range(count)]
    untouched={'spec_ids':['unrelated-p1'],'extra':{'preserved':True},'source':{'file':file,'line_start':20+3*(count-1),'line_end':21+3*(count-1)}}
    patch={'removed':[{'index':0,'row':old}],'inserted':inserted,'insert_at':0,'source_file':file,
           'line_end':8,'after_line_end':8+3*(count-1),'delta':3*(count-1),'before_absent':False,
           'manuscript_dir':chapter.parent.parent.relative_to(root).as_posix()}
    restored=owner._apply_provenance_patch({'section_id':'first','other_metadata':{'keep':True},'paragraphs':inserted+[untouched]},
        patch,inverse=True,section_id='first',root=root)
    assert restored['paragraphs'][0]==old and restored['other_metadata']=={'keep':True}
    assert restored['paragraphs'][1]['source']['line_start']==20 and restored['paragraphs'][1]['extra']=={'preserved':True}
