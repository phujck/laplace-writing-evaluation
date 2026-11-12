"""Current human candidates use real custody/source owners without provider turns."""
import hashlib
import json
import time

import pytest

from laplace.web import authoring as authoring_surface
from laplace.manuscript import manuscript_proposals, manuscript_source, proposal_navigation
from laplace.writing import records as writing_records
from laplace.writing import session_reads
from laplace.writing import provider as writing_provider
from laplace.writing import records as writing_records
from laplace.manuscript import source_application
from laplace.manuscript import reconciliation
from laplace.writing import records
from laplace.core import checkout
from test_writing_controller import _import_project, _seed_revision


@pytest.fixture
def current_candidate(tmp_path,monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE',str(tmp_path/'state'))
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES',str(tmp_path/'workspaces'))
    before='Red statement.\n\nGreen statement.\n\nBlue statement.'
    after='Rose statement.\n\nEmerald statement.\n\nAzure statement.'
    md,source=_import_project(tmp_path,files={'main.tex':'\\documentclass{article}\n\\begin{document}\n'+before+'\n\\end{document}\n'})
    edits=[{'file':'main.tex','line_start':3,'line_end':7,'before':before,'after':after,'reason':'Three distinct revisions.'}]
    tid=_seed_revision(tmp_path,'fixture',edits,selection={'files':['main.tex']})
    idx=records.index(tmp_path);carrier=next(row for row in idx.by_turn[tid] if row.get('has_proposal'))
    selector={'turn_id':tid,'proposal_version':carrier['proposal_instance_version'],'edit_id':manuscript_proposals.edit_id(edits[0])}
    monkeypatch.setattr(writing_provider, 'WritingTurn',lambda *a,**k:pytest.fail('Human reconciliation launched a provider.'))
    return tmp_path,md,source,selector


def target(root,md,source):
    raw=(md/'main.tex').read_bytes()
    return {'file':(md/'main.tex').relative_to(root).as_posix(),'line_start':3,'line_end':7,
        'before':'\n'.join(raw.decode().split('\n')[2:7]),'expected_source_digest':'sha256:'+hashlib.sha256(raw).hexdigest(),
        'expected_selection':manuscript_source.selection_identity(source,'fixture')}


def prepared_case(case,*,stale=True):
    root,md,source,selector=case
    if stale:(md/'main.tex').write_text((md/'main.tex').read_text().replace('Green statement.','Violet statement.'))
    result=reconciliation.prepare(root,'fixture',selector)
    if result['target_required']:result=reconciliation.prepare(root,'fixture',{**selector,'target':target(root,md,source)})
    choices=[{'hunk_id':row['id'],'choice':kind,**({'text':'Cobalt statement.'} if kind=='custom' else {})}
        for row,kind in zip(result['hunks'],['current','proposed','custom'],strict=True)]
    return result,{**result['actions']['apply']['payload'],'choices':choices}


def test_current_hunks_apply_without_provider_or_rich_history_and_keep_original_basis(current_candidate,monkeypatch):
    root,md,source,selector=current_candidate
    prepared,payload=prepared_case(current_candidate)
    assert len(prepared['hunks'])==3
    before_turns=set(records.index(root).turns)
    monkeypatch.setattr(writing_records,'fold_records',lambda *a:pytest.fail('Current candidate entered global rich fold.'))   # the owner
    result=manuscript_proposals.decide(root,'fixture',payload)
    assert result['application']['complete'],result
    assert 'Red statement.\n\nEmerald statement.\n\nCobalt statement.' in (md/'main.tex').read_text()
    assert set(records.index(root).turns)==before_turns
    candidate=records.selected_journal_fields('fixture',result['candidate_ref']['id'],root,
        fields=['record','turn_id','author','predecessor','proposal'])
    assert candidate['record']=='writing-proposal' and not candidate.get('turn_id') and candidate['author']['kind']=='human'
    assert candidate['predecessor']['proposal_version']==selector['proposal_version']
    assert result['application'].get('candidate_ref')==result['candidate_ref'] and not result['application'].get('turn_id')
    again=reconciliation.apply_candidate(root,'fixture',{'candidate_ref':result['candidate_ref']})
    assert again['application']['reused'] and again['application']['id']==result['application']['id']


def test_source_race_refuses_before_sealing_and_retains_supplied_choices(current_candidate):
    root,md,source,selector=current_candidate;prepared,payload=prepared_case(current_candidate)
    choices=json.dumps(payload['choices']);before=len(records.index(root).rows)
    (md/'main.tex').write_text((md/'main.tex').read_text().replace('Violet','Orange'))
    with pytest.raises(ValueError,match='CHANGED_INPUT'):reconciliation.apply_resolution(root,'fixture',payload)
    assert json.dumps(payload['choices'])==choices and len(records.index(root).rows)==before


def test_served_human_preview_renders_resolved_source_without_application(current_candidate,monkeypatch):
    root,md,source,selector=current_candidate;prepared,payload=prepared_case(current_candidate)
    payload['decision']='preview-resolution'
    monkeypatch.setattr(checkout, 'repo_root',lambda:root)
    before=(md/'main.tex').read_bytes()
    status,_,raw=authoring_surface.handle('/authoring/proposal-decision',{},'POST',json.dumps(payload).encode())
    result=json.loads(raw)
    assert status==200 and result['after_blocks'] and result['resolved_after'].startswith('Red'),result
    assert (md/'main.tex').read_bytes()==before and not records.index(root).by_candidate


def test_owner_hunk_identity_survives_explicit_refresh_of_unchanged_regions(current_candidate):
    root,md,source,selector=current_candidate;first,payload=prepared_case(current_candidate)
    (md/'main.tex').write_text((md/'main.tex').read_text().replace('Violet','Orange'))
    refreshed=reconciliation.prepare(root,'fixture',{**selector,'target':target(root,md,source)})
    assert first['resolution_token']!=refreshed['resolution_token']
    assert first['hunks'][0]['id']==refreshed['hunks'][0]['id']
    assert first['hunks'][1]['id']!=refreshed['hunks'][1]['id']
    assert first['hunks'][2]['id']==refreshed['hunks'][2]['id']
    with pytest.raises(ValueError,match='CHANGED_INPUT'):reconciliation.preview(root,'fixture',payload)


def test_independent_same_line_word_hunks_apply_through_real_source_owner(current_candidate):
    root,md,source,_=current_candidate
    before='Red statement; green statement; blue statement.'
    after='Rose statement; emerald statement; azure statement.'
    file=md/'main.tex';file.write_text('\\documentclass{article}\n\\begin{document}\n'+before+'\n\\end{document}\n')
    edit={'file':'main.tex','line_start':3,'line_end':3,'before':before,'after':after,'reason':'Three changes within one paragraph line.'}
    tid=_seed_revision(root,'fixture',[edit],selection={'files':['main.tex']},suffix='same-line')
    carrier=next(row for row in records.index(root).by_turn[tid] if row.get('has_proposal'))
    selector={'turn_id':tid,'proposal_version':carrier['proposal_instance_version'],'edit_id':manuscript_proposals.edit_id(edit)}
    file.write_text(file.read_text().replace('green','violet'))
    raw=file.read_bytes();selection={'file':file.relative_to(root).as_posix(),'line_start':3,'line_end':3,
        'before':raw.decode().split('\n')[2],'expected_source_digest':'sha256:'+hashlib.sha256(raw).hexdigest(),
        'expected_selection':manuscript_source.selection_identity(source,'fixture')}
    prepared=reconciliation.prepare(root,'fixture',{**selector,'target':selection})
    assert len(prepared['hunks'])==3 and [row['current'] for row in prepared['hunks']]==['Red','violet','blue']
    choices=[{'hunk_id':row['id'],'choice':choice,**({'text':'cobalt'} if choice=='custom' else {})}
        for row,choice in zip(prepared['hunks'],['current','proposed','custom'],strict=True)]
    result=reconciliation.apply_resolution(root,'fixture',{**prepared['actions']['apply']['payload'],'choices':choices})
    assert result['application']['complete'] and file.read_text().split('\n')[2]=='Red statement; emerald statement; cobalt statement.'


def test_owner_token_hunks_preserve_whole_tex_tokens_and_whitespace():
    original=r'Red \\cite{key-one} green \\label{sec:one} blue.'
    proposed=r'Rose \\cite{key-two} emerald \\label{sec:one} azure.'
    rows=reconciliation.hunks(original,original,proposed,{'turn_id':'WT-real','edit_id':'EDIT-real'})
    assert len(rows)==4 and any(row['current']==r'\\cite{key-one}' for row in rows)
    assert all('label' not in row['current']+row['proposed'] for row in rows)
    value=original
    for row in reversed(rows):
        lo,hi=row['current_range'];value=value[:lo]+row['proposed']+value[hi:]
    assert value==proposed


def test_repetitive_single_line_comparison_has_bounded_work_and_exact_choices(monkeypatch):
    old=('alpha beta gamma delta '*1000).strip()
    words=old.split(' ');words[100]='changed-one';words[3000]='changed-two';new=' '.join(words)
    matching=reconciliation.difflib.SequenceMatcher;compared=[]
    def bounded(*args,**kwargs):
        pairs=len(kwargs.get('a',()))*len(kwargs.get('b',()))
        compared.append(pairs)
        assert pairs<=reconciliation.MAX_COMPARE_PAIRS
        return matching(*args,**kwargs)
    monkeypatch.setattr(reconciliation.difflib,'SequenceMatcher',bounded)
    started=time.perf_counter();rows=reconciliation.hunks(old,old,new,{'turn_id':'WT-scale','edit_id':'EDIT-scale'})
    elapsed=time.perf_counter()-started
    assert len(old)==22999 and len(rows)==2 and elapsed<0.5
    assert [row['proposed'] for row in rows]==['changed-one','changed-two']
    value=old
    for row in reversed(rows):
        lo,hi=row['current_range'];value=value[:lo]+row['proposed']+value[hi:]
    assert value==new and all(pairs<=reconciliation.MAX_COMPARE_PAIRS for pairs in compared)


def test_coarse_fallback_keeps_complete_editable_text_and_requires_exact_new_hunks(current_candidate,monkeypatch):
    root,md,source,selector=current_candidate;fine,payload=prepared_case(current_candidate)
    monkeypatch.setattr(reconciliation,'MAX_COMPARE_REGIONS',1)
    coarse=reconciliation.prepare(root,'fixture',fine['actions']['apply']['payload'])
    assert coarse['resolution_token']==fine['resolution_token'] and coarse['comparison']['scope']=='coarse'
    assert len(coarse['hunks'])==1 and coarse['hunks'][0]['comparison_scope']=='coarse'
    assert coarse['hunks'][0]['current']==fine['current'] and coarse['hunks'][0]['proposed']==fine['proposed']
    with pytest.raises(ValueError,match='hunk|Hunk'):reconciliation.preview(root,'fixture',payload)
    selected={**coarse['actions']['preview']['payload'],'choices':[{'hunk_id':coarse['hunks'][0]['id'],'choice':'proposed'}]}
    assert reconciliation.preview(root,'fixture',selected)['resolved_after']==fine['proposed']
    edited={**coarse['actions']['preview']['payload'],'resolved_after':'Complete authored text.'}
    assert reconciliation.preview(root,'fixture',edited)['resolved_after']=='Complete authored text.'


def test_large_unaligned_comparison_falls_back_without_truncation():
    old=('alpha beta gamma delta '*1000).strip();new=('omega theta '*1100).strip()
    rows=reconciliation.hunks(old,old,new,{'turn_id':'WT-coarse','edit_id':'EDIT-coarse'})
    assert len(rows)==1 and rows[0]['comparison_scope']=='coarse'
    assert rows[0]['original']==rows[0]['current']==old and rows[0]['proposed']==new


def test_total_regions_and_matching_work_stay_bounded_across_line_refinement(monkeypatch):
    old='\n'.join('Line '+str(n)+' alpha beta gamma delta.\nUnchanged separator '+str(n) for n in range(100))
    new=old.replace('alpha','ALPHA').replace('gamma','GAMMA')
    matching=reconciliation.difflib.SequenceMatcher;work=[]
    def counted(*args,**kwargs):
        work.append(len(kwargs.get('a',()))*len(kwargs.get('b',())))
        return matching(*args,**kwargs)
    monkeypatch.setattr(reconciliation.difflib,'SequenceMatcher',counted)
    rows=reconciliation.hunks(old,old,new,{'turn_id':'WT-multiline','edit_id':'EDIT-multiline'})
    assert len(rows)==1 and rows[0]['comparison_scope']=='coarse'
    assert rows[0]['current']==old and rows[0]['proposed']==new
    assert sum(work)<=reconciliation.MAX_COMPARE_PAIRS and len(rows)<=reconciliation.MAX_COMPARE_REGIONS


@pytest.mark.parametrize('count',[20,1000])
def test_actual_native_resolution_envelopes_and_exact_parts_stay_bounded(current_candidate,count):
    from laplace.native import tools as writing_tools
    from laplace.core import grammar
    root,md,source,_=current_candidate
    before=('alpha beta gamma delta '*count).strip();words=before.split(' ')
    words[count//2]='CHANGED';words[count*3]='SECOND';after=' '.join(words)
    path=md/'main.tex';path.write_text('\\documentclass{article}\n\\begin{document}\n'+before+'\n\\end{document}\n')
    edit={'file':'main.tex','line_start':3,'line_end':3,'before':before,'after':after,'reason':'Bounded native contract.'}
    caller=_seed_revision(root,'fixture',[edit],selection={'files':['main.tex']},suffix='bounded-native')
    carrier=next(row for row in records.index(root).by_turn[caller] if row.get('has_proposal'))
    selector={'turn_id':caller,'proposal_version':carrier['proposal_instance_version'],'edit_id':manuscript_proposals.edit_id(edit)}
    def call(request):
        result=writing_tools.call(root,'fixture','revise',request,turn_id=caller)
        assert result['ok'],result
        assert len(json.dumps(result,ensure_ascii=False).encode())<10_000
        assert len(json.dumps(result,ensure_ascii=False,indent=2).encode())<12_000
        return result['owner_response']
    prepared=call(reconciliation.action('fixture','prepare-resolution',selector)['native_request'])
    assert prepared['projection']=='metadata' and 'before' not in prepared['target']
    assert not any(key in prepared for key in ('original','current','proposed'))
    assert len(prepared['hunks'])==2 and prepared['pagination']['total']==2
    parts=[];handle=prepared['text_reads']['current'];coverage=[]
    while handle:
        part=call(handle['native_request']);parts.append(part['content']);coverage.append(part['coverage'])
        handle=part.get('next_read')
    assert ''.join(parts)==before and coverage[0]['start']==0 and coverage[-1]['end']==len(before.encode())
    assert len({row['sha256'] for row in coverage})==1
    assert all(right['start']==left['end'] for left,right in zip(coverage,coverage[1:]))
    choices=[{'hunk_id':row['id'],'choice':'proposed'} for row in prepared['hunks']]
    preview=prepared['actions']['preview']['native_request'];preview['payload']={**preview['payload'],'choices':choices}
    resolved=call(preview);parts=[];handle=resolved['text_reads']['resolved']
    while handle:
        part=call(handle['native_request']);parts.append(part['content']);handle=part.get('next_read')
    assert ''.join(parts)==after
    action=prepared['actions']['apply']['native_request'];action['payload']={**action['payload'],'choices':choices}
    applied=call(action)
    assert applied['application']['complete'] and applied['author']['kind']=='agent'
    assert path.read_text().split('\n')[2]==after
    saved=call(applied['read_handle']['native_request'])
    assert saved['candidate_ref']==applied['candidate_ref'] and saved['proposal_state']=='applied'


def test_native_resolution_parts_refuse_retargeting_or_source_drift(current_candidate):
    from laplace.native import tools as writing_tools
    root,md,source,selector=current_candidate
    prepare=writing_tools.call(root,'fixture','revise',reconciliation.action('fixture','prepare-resolution',selector)['native_request'],turn_id=selector['turn_id'])['owner_response']
    request=prepare['text_reads']['current']['native_request']
    bad={**request,'payload':{**request['payload'],'id':'WT-another'}}
    refused=writing_tools.call(root,'fixture','revise',bad,turn_id=selector['turn_id'])
    assert not refused['ok']
    (md/'main.tex').write_text((md/'main.tex').read_text().replace('Green','Violet'))
    refused=writing_tools.call(root,'fixture','revise',request,turn_id=selector['turn_id'])
    assert not refused['ok'] and 'CHANGED_INPUT' in refused['refused']['said']


def test_guard_only_action_cannot_retarget_the_inspected_resolution(current_candidate):
    root,md,source,selector=current_candidate;prepared,payload=prepared_case(current_candidate)
    assert 'before' not in payload['target']
    payload['target']={**payload['target'],'line_end':3}
    before=(md/'main.tex').read_bytes()
    with pytest.raises(ValueError,match='CHANGED_INPUT'):reconciliation.apply_resolution(root,'fixture',payload)
    assert (md/'main.tex').read_bytes()==before and not records.index(root).by_candidate


def test_native_contract_fallback_is_exact_paged_json_not_complete_truncation(current_candidate,monkeypatch):
    from laplace.native import tools as writing_tools
    root,md,source,selector=current_candidate
    monkeypatch.setattr(reconciliation,'NATIVE_RESPONSE_BYTES',1)
    request=reconciliation.action('fixture','prepare-resolution',selector)['native_request'];parts=[];coverage=[]
    while request:
        result=writing_tools.call(root,'fixture','revise',request,turn_id=selector['turn_id'])
        assert result['ok'],result
        body=result['owner_response'];assert body['projection']=='contract-part'
        assert len(json.dumps(result,ensure_ascii=False,indent=2).encode())<12_000
        parts.append(body['content']);coverage.append(body['coverage'])
        request=(body.get('next_read') or {}).get('native_request')
    contract=json.loads(''.join(parts))
    assert contract['projection']=='metadata' and contract['actions']['apply']['native_request']['verb']=='delete'
    assert len({row['sha256'] for row in coverage})==1
    assert coverage[-1]['end']==coverage[-1]['total']


def test_native_utf8_parts_cover_exact_bytes_with_bounded_encoded_content():
    text=('α🌿\\n\x00'*1000);offset=0;parts=[]
    while offset<len(text.encode()):
        part,end=reconciliation._text_part(text,offset)
        assert end>offset and part['coverage']['start']==offset
        assert len(json.dumps(part['content'],ensure_ascii=False).encode())<=reconciliation.NATIVE_TEXT_BYTES
        parts.append(part['content']);offset=end
    assert ''.join(parts)==text


def test_full_and_compact_share_exact_ids_handles_and_immutable_body_after_drift(current_candidate):
    from laplace.native import tools as writing_tools
    root,md,source,selector=current_candidate;prepared,payload=prepared_case(current_candidate)
    applied=reconciliation.apply_resolution(root,'fixture',payload);ref=applied['candidate_ref']
    full=reconciliation.read_candidate(root,'fixture',ref)
    compact=writing_tools.call(root,'fixture','discuss',full['read_handle']['native_request'],turn_id=selector['turn_id'])['owner_response']
    assert compact['candidate_ref']==full['candidate_ref'] and compact['predecessor']==full['predecessor']
    assert compact['edits'][0]['edit_id']==full['edits'][0]['edit_id']
    assert compact['predecessor_read']==full['predecessor_read']
    original=writing_tools.call(root,'fixture','discuss',compact['predecessor_read']['native_request'],turn_id=selector['turn_id'])['owner_response']
    assert original['proposal_state']=='resolved-into-successor' and original['read_only']
    assert original['edits'][0]['edit_id']==selector['edit_id'] and original['edits'][0]['successor_ref']==ref
    carrier=original['carrier_ref']
    alias=proposal_navigation.read(root,'fixture',{'id':carrier['id'],'proposal_version':carrier['version'],'view':'summary'})
    assert alias['edits'][0]['edit_id']==selector['edit_id'] and alias['proposal_version']==selector['proposal_version']
    (md/'main.tex').write_text((md/'main.tex').read_text()+'\n% later unrelated change\n')
    for value,expected in [(compact,full['edits'][0]['after']),(original,prepared['proposed'])]:
        body=writing_tools.call(root,'fixture','discuss',value['edits'][0]['text_reads']['proposed']['native_request'],turn_id=selector['turn_id'])['owner_response']
        assert body['content']==expected and body['coverage']['basis']=='IMMUTABLE_SAVED_CANDIDATE'
        assert body['source_currentness']=='NOT_ASSERTED' and body['edit_id']==value['edits'][0]['edit_id']


def test_finish_disposition_is_exact_metadata_only_and_does_not_replay_changed_source(current_candidate,monkeypatch):
    root,md,source,selector=current_candidate;prepared,payload=prepared_case(current_candidate)
    bank=writing_records.bank
    with monkeypatch.context() as outage:
        def failed(path,row):
            if row.get('record')=='writing-proposal-decision':raise OSError('Simulated disposition outage')
            return bank(path,row)
        outage.setattr(writing_records,'bank',failed)   # the owner and the facade alias
        applied=reconciliation.apply_resolution(root,'fixture',payload,actor={'kind':'agent','turn_id':selector['turn_id'],'mode':'revise'})
    assert applied['application']['complete'] and applied['disposition']['status']=='PENDING'
    assert proposal_navigation.read(root,'fixture',{})['count']==1
    pending=proposal_navigation.read(root,'fixture',{'id':selector['turn_id'],'proposal_version':selector['proposal_version'],'view':'summary'})
    assert pending['edits'][0]['disposition_status']=='PENDING'
    assert pending['edits'][0]['pending_successors'][0]['successor_ref']==applied['candidate_ref']
    assert pending['edits'][0]['successor_read']==applied['read_handle']
    (md/'main.tex').write_text((md/'main.tex').read_text()+'\n% independent change after saved application\n')
    before=(md/'main.tex').read_bytes();action=applied['disposition']['recovery_action']
    monkeypatch.setattr(source_application,'_apply_proposal_locked',lambda *a,**k:pytest.fail('Metadata recovery reopened source application'))   # the owner
    finished=manuscript_proposals.decide(root,'fixture',action['payload'])
    assert finished['metadata_only'] and finished['disposition']['status']=='RECORDED'
    decision=records.selected_journal_fields('fixture',finished['disposition']['decision_id'],root,fields=['actor'])
    assert decision['actor']['kind']=='human' and finished['application']['actor']['kind']=='agent'
    assert (md/'main.tex').read_bytes()==before and proposal_navigation.read(root,'fixture',{})['count']==0
    assert manuscript_proposals.decide(root,'fixture',action['payload'])['disposition']['decision_id']==finished['disposition']['decision_id']
    with pytest.raises(ValueError):manuscript_proposals.decide(root,'fixture',{**action['payload'],'resolution_application_id':'WA-other'})


def test_resolution_retires_only_exact_original_edit_in_mixed_bundle(current_candidate):
    root,md,source,_=current_candidate
    edits=[{'file':'main.tex','line_start':3,'line_end':3,'before':'Red statement.','after':'Rose statement.','reason':'First.'},
        {'file':'main.tex','line_start':5,'line_end':5,'before':'Green statement.','after':'Emerald statement.','reason':'Second.'}]
    caller=_seed_revision(root,'fixture',edits,selection={'files':['main.tex']},suffix='mixed-bundle')
    carrier=next(row for row in records.index(root).by_turn[caller] if row.get('has_proposal'))
    selector={'turn_id':caller,'proposal_version':carrier['proposal_instance_version'],'edit_id':manuscript_proposals.edit_id(edits[0])}
    prepare=reconciliation.prepare(root,'fixture',selector)
    applied=reconciliation.apply_resolution(root,'fixture',{**prepare['actions']['apply']['payload'],'resolved_after':'Resolved first statement.'})
    assert applied['disposition']['status']=='RECORDED'
    summary=proposal_navigation.read(root,'fixture',{'id':caller,'proposal_version':selector['proposal_version'],'view':'summary'})
    assert summary['proposal_state']=='ready' and summary['edits'][0]['status']=='resolved-into-successor'
    assert summary['edits'][1]['status'] in {'pending','conflict'}  # sibling's old source authority is never renewed
    exact=proposal_navigation.read(root,'fixture',{'id':caller,'proposal_version':selector['proposal_version'],'edit_id':selector['edit_id'],'view':'edit'})
    assert exact['read_only'] and exact['edits'][0]['before']==edits[0]['before'] and exact['edits'][0]['after']==edits[0]['after']
    queue=proposal_navigation.read(root,'fixture',{})
    assert next(row for row in queue['proposals'] if row['id']==caller)['edit_count']==1


def test_shared_native_action_attributes_actual_agent_and_refuses_review_or_child(current_candidate):
    from laplace.native import tools as writing_tools, verbs as writing_verbs
    from laplace.core import grammar
    root,md,source,selector=current_candidate;prepared,payload=prepared_case(current_candidate)
    native={**prepared['actions']['apply']['native_request'],'payload':grammar.to_payload(payload)}
    assert writing_verbs.choose(native['verb'],native['concept'],payload).operation=='authoring/proposal-decision'
    for mode,caller,dispatch in [('review','WT-review',None),('revise','WT-child','WORK-dispatch')]:
        writing_records.bank(root,{'record':'writing-turn','id':caller,'project':'fixture','mode':mode,'dispatch_id':dispatch})
        refused=writing_tools.call(root,'fixture',mode,native,turn_id=caller)
        assert not refused['ok'] and 'cannot apply' in refused['refused']['said']
    caller=selector['turn_id']
    result=writing_tools.call(root,'fixture','revise',native,turn_id=caller)
    assert result['ok'],result
    owner=result['owner_response'];ref=owner['candidate_ref']
    row=records.selected_journal_fields('fixture',ref['id'],root,fields=['author','record','turn_id'])
    assert row['author']['kind']=='agent' and row['author']['turn_id']==caller and not row.get('turn_id')
    assert owner['application']['actor']['kind']=='agent' and owner['application']['actor']['turn_id']==caller
    exact=proposal_navigation.read(root,'fixture',{'id':ref['id'],'proposal_version':ref['version'],'view':'preview'})
    assert exact['candidate_ref']==ref and exact['proposal_state']=='applied' and exact['predecessor_read']


@pytest.mark.parametrize('mode,dispatch',[('work',None),('review',None),('revise',None),('discuss',None),('work','WORK-detached')])
def test_resolution_native_inspection_is_a_read_in_every_existing_role(current_candidate,mode,dispatch):
    from laplace.native import tools as writing_tools
    from laplace.core import grammar
    root,md,source,selector=current_candidate;prepared,payload=prepared_case(current_candidate)
    caller='WT-inspection-'+mode
    writing_records.bank(root,{'record':'writing-turn','id':caller,'project':'fixture','mode':mode,'dispatch_id':dispatch})
    action=reconciliation.action('fixture','prepare-resolution',{**selector,'target':prepared['actions']['apply']['payload']['target']})
    assert action['native_request']['verb']=='read'
    before=(md/'main.tex').read_bytes()
    result=writing_tools.call(root,'fixture',mode,action['native_request'],turn_id=caller)
    assert result['ok'] and result['outcome']=='read',result
    read=result['owner_response'];assert read['resolution_token']==prepared['resolution_token']
    preview=read['actions']['preview']['native_request']
    preview['payload']=grammar.to_payload({**grammar.to_owner_payload(preview['payload']),'choices':payload['choices']})
    result=writing_tools.call(root,'fixture',mode,preview,turn_id=caller)
    assert result['ok'] and result['outcome']=='read' and result['owner_response']['changed'],result
    assert (md/'main.tex').read_bytes()==before
    rows=records.index(root).by_turn[caller]
    assert all(row['record']!='writing-tool-action' for row in rows)
    assert any(row['record']=='writing-tool-read' and row['operation']=='authoring/proposal-preview' for row in rows)


def test_current_text_application_keeps_stale_science_review_and_unrelated_standing(tmp_path,monkeypatch):
    from laplace.research import concepts as concepts_surface, corpus_ingest
    from laplace.manuscript import proposal_basis
    from test_project_structure import _fixture
    from test_accepted_link_index import _rows,_edit
    monkeypatch.setenv('LAPLACE_STATE',str(tmp_path/'state'))
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES',str(tmp_path/'workspaces'))
    md=_fixture(tmp_path)
    pin=concepts_surface.state('book',node='res:one',root=tmp_path)['content_revision']
    unrelated=concepts_surface.state('book',node='res:two',root=tmp_path)['content_revision']
    edit={'file':'N1.tex','line_start':2,'line_end':2,'before':'Opening prose.','after':'Revised opening prose.',
        'reason':'Clarify wording.','develops':[{'id':'res:one','content_revision':pin}]}
    tid=_seed_revision(tmp_path,'book',[edit],selection={'files':['N1.tex']})
    row=next(row for row in records.index(tmp_path).by_turn[tid] if row.get('has_proposal'))
    selector={'turn_id':tid,'proposal_version':row['proposal_instance_version'],'edit_id':manuscript_proposals.edit_id(edit)}
    other={**_edit('N2.tex','Result prose.'),'develops':[{'id':'res:two','content_revision':unrelated}],'evidence_refs':[]}
    for row in _rows(tmp_path,'WA-unrelated',edits=[other]):writing_records.bank(tmp_path,row)
    before=proposal_basis.accepted_links(tmp_path,'book',application_id='WA-unrelated')['links'][0]
    prepared=reconciliation.prepare(tmp_path,'book',selector)
    assert not prepared['target_required'] and prepared['basis']['develops'][0]['read']
    assert not corpus_ingest.rewire_add(tmp_path,'book',{'kind':'edit-essence','node':'res:one','value':'Changed scientific meaning.'}).get('error')
    payload={**prepared['actions']['apply']['payload'],'resolved_after':'Author resolved opening prose.'}
    result=reconciliation.apply_resolution(tmp_path,'book',payload)
    assert result['application']['complete'] and result['application']['validation_basis']['semantic_currentness']=='REVIEW_REQUIRED'
    links=proposal_basis.accepted_links(tmp_path,'book',application_id=result['application']['id'])['links']
    assert len(links)==1 and links[0]['status']=='LIVE_TEXT_REVIEW_REQUIRED' and links[0]['review_obligations']
    assert links[0]['candidate_id']==result['candidate_ref']['id'] and not links[0]['turn_id']
    assert links[0]['develops'][0]['content_revision']==pin
    assert proposal_basis.accepted_links(tmp_path,'book',application_id='WA-unrelated')['links'][0]==before


def test_selected_candidate_does_not_open_unrelated_history(current_candidate,monkeypatch):
    root,md,source,selector=current_candidate
    for number in range(80):
        writing_records.bank(root,{'record':'writing-turn','id':'WT-cold-'+str(number),'project':'fixture','document':source})
        writing_records.bank(root,{'record':'writing-proposal','id':'PROP-cold-'+str(number),'project':'fixture',
            'turn_id':'WT-cold-'+str(number),'proposal':{'answer':'Cold prose '*500,'edits':[
                {'file':'unrelated.tex','line_start':1,'line_end':1,'before':'Cold','after':'Still cold','reason':'Unrelated'}]}})
    opened=[];original=proposal_navigation._raw
    def selected(idx,meta):
        opened.append(meta['id']);assert 'cold' not in meta['id'];return original(idx,meta)
    monkeypatch.setattr(proposal_navigation,'_raw',selected)
    result=proposal_navigation.read(root,'fixture',{'id':selector['turn_id'],'proposal_version':selector['proposal_version'],'view':'preview'})
    assert result['edits'][0]['before'].startswith('Red') and result['coverage']['whole_history_loaded'] is False
    assert opened and len(opened)<8


def test_committed_source_with_unproved_application_retains_exact_candidate_without_replay(current_candidate,monkeypatch):
    root,md,source,selector=current_candidate;prepared,payload=prepared_case(current_candidate)
    bank=writing_records.bank
    def fail_application(path,row):
        if row.get('record')=='writing-application':raise OSError('Simulated application publication outage')
        return bank(path,row)
    monkeypatch.setattr(writing_records,'bank',fail_application)
    monkeypatch.setattr(writing_records,'fold_records',lambda *a:pytest.fail('Tracking failure hydrated rich history.'))   # the owner
    result=reconciliation.apply_resolution(root,'fixture',payload)
    assert result['application']['status']=='SOURCE_APPLIED_TRACKING_UNPROVED'
    assert result['application']['source_applied'] and not result['application']['complete']
    assert result['application']['application_tracking']['attempted_id'].startswith('WA-')
    assert result['candidate_ref']['id'].startswith('PROP-') and not result['apply_action']['permitted']
    before=(md/'main.tex').read_bytes()
    with pytest.raises(ValueError):reconciliation.apply_candidate(root,'fixture',{'candidate_ref':result['candidate_ref']})
    assert (md/'main.tex').read_bytes()==before


def test_unproven_historical_target_requires_explicit_source_selection(current_candidate):
    root,md,source,selector=current_candidate
    (md/'main.tex').write_text((md/'main.tex').read_text().replace('Green','Violet'))
    result=reconciliation.prepare(root,'fixture',selector)
    assert result['target_required'] and not result.get('resolution_token')
    explicit=reconciliation.prepare(root,'fixture',{**selector,'target':target(root,md,source)})
    assert not explicit['target_required'] and explicit['target']['before'].startswith('Red statement.')
    assert result['target_files'][0]['read']['http']['url'].startswith('/projection/tex?')


def test_bad_choices_and_marker_mutation_never_apply(current_candidate):
    root,md,source,selector=current_candidate;prepared,payload=prepared_case(current_candidate)
    with pytest.raises(ValueError,match='Hunk choices'):reconciliation.preview(root,'fixture',{**payload,'choices':[{**row,'hunk_id':'HUNK-guessed'} for row in payload['choices']]})
    result=reconciliation.apply_resolution(root,'fixture',{**{key:val for key,val in payload.items() if key!='choices'},
        'resolved_after':'% fake-p1\nAuthored text.'})
    assert result['candidate_retained'] and 'marker' in result['error'].lower()
    assert 'Violet statement.' in (md/'main.tex').read_text()


def test_selected_terminal_repetition_promotes_exact_body_without_renewing_old_basis(current_candidate):
    root,md,source,selector=current_candidate
    turn=session_reads._records(root)['turns'][selector['turn_id']]
    proposal=turn['reply']['proposal']
    writing_records.bank(root,{'record':'writing-reply','id':'WR-terminal-repeat','project':'fixture',
        'turn_id':selector['turn_id'],'session_id':'WS-x','status':'completed','proposal':proposal})
    (md/'main.tex').write_text((md/'main.tex').read_text().replace('Green','Violet'))
    preview=proposal_navigation.read(root,'fixture',{'id':selector['turn_id'],'view':'preview'})
    assert preview['proposal_version']==selector['proposal_version']
    assert preview['edits'][0]['before']=='Red statement.\n\nGreen statement.\n\nBlue statement.'
    assert preview['edits'][0]['status']=='conflict' and not preview['edits'][0].get('review_token')
    assert preview['edits'][0]['resolution_action']['payload']['decision']=='prepare-resolution'
