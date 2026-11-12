"""C1b/C1c/C1d: one source identity, paged comparisons, bounded session rows, scoped and conditional document reads."""
import json, os, time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import pytest
from laplace.work import history as author_history
from laplace.web import authoring as authoring_surface
from laplace.manuscript import projection_viewer as pv, review_surface as rv, walk
from laplace.native import tools as writing_tools
from laplace.writing import session_reads
from laplace.writing import session_projection
from laplace.writing import records
from laplace.writing import turn_context
from laplace.core import checkout
from laplace.writing import child_hosts
from test_editor_document_contract import fixture, read, save
from laplace.research import research_observation   # the owners the code paths read (research family R1)


# ---- C1b: history targets carry the checkout path or an explicit unproved basename ----

def test_manuscript_targets_name_repo_file_or_stay_unproved(tmp_path):
    (tmp_path/'paper').mkdir();(tmp_path/'paper'/'body.tex').write_text('x')
    bound=author_history._manuscript_target(tmp_path,'paper/body.tex',line_start=3)
    assert bound['repo_file']=='paper/body.tex' and bound['binding']=='BOUND' and bound['file']=='paper/body.tex' and bound['line_start']==3
    loose=author_history._manuscript_target(tmp_path,'body.tex')
    assert 'repo_file' not in loose and loose['binding']=='UNPROVED' and loose['file']=='body.tex'
    assert author_history._manuscript_target(tmp_path,'../outside.tex')['binding']=='UNPROVED'


def test_editor_save_items_bind_through_version_source_file_and_mark_legacy_saves_unproved(tmp_path,monkeypatch):
    manuscript=tmp_path/'paper';saves=manuscript/'editor_saves';saves.mkdir(parents=True)
    for version,manifest in (('v1',{'version_id':'v1','file':'body.tex','source_file':'paper/body.tex','author':'a','ts':'2026-10-12T00:00:00Z'}),
                             ('v0',{'version_id':'v0','file':'body.tex','author':'a','ts':'2026-10-11T00:00:00Z'})):
        (saves/version).mkdir();(saves/version/'VERSION.json').write_text(json.dumps(manifest))
    from laplace.manuscript import manuscript_source
    monkeypatch.setattr(manuscript_source,'storage_home',lambda project,root:manuscript)
    items,_,_=author_history._editor_save_items('paper',tmp_path)
    by_id={item['id'].split(':')[-1]:item['targets'][0] for item in items}
    assert by_id['v1']=={'kind':'manuscript','file':'body.tex','repo_file':'paper/body.tex','binding':'BOUND'}
    assert by_id['v0']=={'kind':'manuscript','file':'body.tex','binding':'UNPROVED'}


def test_detail_pages_recorded_comparisons_with_an_owner_continuation_and_record_keeps_all(tmp_path,monkeypatch):
    md=fixture(tmp_path);monkeypatch.setattr(pv,'_repo_root',lambda:tmp_path);monkeypatch.setattr(rv,'_repo_root',lambda:tmp_path)
    _,observed=read(tmp_path);code,saved=save(observed,observed['content']+'An appended sentence.\n');assert code==200
    ident='activity:authoring:'+saved['exemplar']['exemplar_id']
    one=author_history.detail('paper',ident,tmp_path)
    assert one['comparisons_pagination']=={'offset':0,'limit':6,'total':1,'next_offset':None,'next_read':None} and len(one['comparisons'])==1
    assert one['comparison']==one['comparisons'][0]
    # A bounded page over a longer list, with the owner's next read on both doors.
    rows=[{'format':'tex','title':f'h{i}','before':'a','after':'b'} for i in range(15)]
    page=author_history._paged_comparisons('paper',ident,rows,0,6)
    assert [row['title'] for row in page['comparisons']]==['h0','h1','h2','h3','h4','h5'] and page['comparisons_pagination']['total']==15
    nxt=page['comparisons_pagination']['next_read'];assert nxt['payload']=={'view':'activity','id':ident,'comparison_offset':6,'comparison_limit':6}
    query=parse_qs(urlparse(nxt['http']['url']).query);assert query['comparison_offset']==['6'] and query['id']==[ident]
    last=author_history._paged_comparisons('paper',ident,rows,12,6)
    assert [row['title'] for row in last['comparisons']]==['h12','h13','h14'] and last['comparisons_pagination']['next_read'] is None
    # HTTP decodes the page selectors; the contract admits them only beside an id.
    assert author_history.comparison_page(author_history.http_history_payload({'comparison_offset':['6'],'comparison_limit':['3']}))==(6,3)
    author_history.validate_activity_query({'view':'activity','id':ident,'comparison_offset':6})
    with pytest.raises(ValueError):author_history.validate_activity_query({'view':'activity','comparison_offset':6})
    native=writing_tools.execute(tmp_path,'paper','work','author_history',{'view':'activity','id':ident,'comparison_limit':1})
    assert native['comparisons_pagination']['limit']==1 and native['comparisons_pagination']['total']==1
    exact=author_history.record('paper',ident,tmp_path)
    assert exact['comparisons']==one['comparisons'] and 'comparisons_pagination' not in exact
    target=one['links'][0];assert target['repo_file']=='paper/body.tex' and target['binding']=='BOUND'


# ---- C1c: bounded session thread rows, complete single-turn summary ----

def _session_fixture(root):
    long=('A long request that the thread shows in part. '*80).strip()
    records.bank(root,{'record':'writing-session','id':'WS-child','project':'book','title':'Child','provider':'claude','model':'m','effort':'low',
                                  'role':'worker','packet':'P1','dispatch_id':'WORK-dispatch'})
    records.bank(root,{'record':'writing-turn','id':'WT-child','session_id':'WS-child','project':'book','mode':'work','text':long,'ts':'2026-10-12T00:00:00Z',
                                  'workspace_context':{'surface':'project','label':'Project'},'provider_settings':{'provider':'claude','model':'m','effort':'low'},
                                  'steering':[{'id':'ST-1','text':long,'workspace_context':{'surface':'project'},'ts':'2026-10-12T00:00:01Z'}],
                                  'actions':[{'id':f'ACT-{i}','operation':'store_artifact','project':'book','turn_id':'WT-child','payload':{'path':f'development/a{i}.json'},
                                              'outcome':{'status':'SUCCEEDED','artifact':{'id':f'ART-{i}','path':f'development/a{i}.json','sha256':'0'*64}}} for i in range(5)]})
    records.bank(root,{'record':'writing-reply','id':'WR-child','turn_id':'WT-child','session_id':'WS-child','project':'book','status':'completed','text':'Done.','ts':'2026-10-12T00:00:02Z'})
    return long


def test_session_thread_rows_are_bounded_and_the_single_turn_summary_is_complete(tmp_path):
    long=_session_fixture(tmp_path)
    page=session_reads.session_state(tmp_path,'WS-child',view='summary',limit=20)
    row,=page['turns']
    single_count=lambda root:session_reads.session_turn_detail(root,'book','WT-child','summary')['turn'].get('action_count',0)
    # the thread row is a glance (H1, 2026-10-14): ROW_* excerpts with complete-length markers,
    # counts instead of collections, and body_read as the exact read
    T=session_projection.ROW_TEXT_LIMIT
    assert row['text']==long[:T] and row['text_chars']==len(long) and row['text_truncated'] is True
    assert 'steering' not in row and row['steering_total']==1 and row['steering_truncated'] is True
    assert 'workspace_context' not in row and 'work_basis' not in row and row['provider_settings']['provider']=='claude'
    assert row['packet']=='P1' and row['role']=='worker'
    assert row['body_read']['http']['url'].endswith('view=turn') and 'summary_read' not in row and row['detail']=={'turn_id':'WT-child'}
    assert 'text' not in row['reply'] and row['reply']['display_text']=='Done.'
    assert 'result_links' not in row and 'result_links_more' not in row and row.get('action_count',0)==single_count(tmp_path)
    single=session_reads.session_turn_detail(tmp_path,'book','WT-child','summary')['turn']
    assert single['text']==long and 'text_truncated' not in single and single['packet']=='P1' and single['role']=='worker'
    assert single['steering'][0]['text']==long and single['result_links_more'] is False and len(single['result_links'])==single.get('result_links_total',len(single['result_links'])) and single['summary_read']['http']['url'].endswith('view=summary')
    assert row.get('result_links_total',0)==len(single['result_links']),'the row counts exactly the links the single-turn summary lists'
    full=session_reads.session_turn_detail(tmp_path,'book','WT-child','turn')['turn']
    assert full['text']==long and 'text_truncated' not in full
    # The bounded thread page is smaller than one complete single-turn summary.
    assert len(json.dumps(page['turns']).encode())<len(json.dumps([single]).encode())


# ---- C1d: scoped and conditional document reads ----

def _walk_fixture(tmp_path,monkeypatch):
    md=fixture(tmp_path)
    (md/'body.tex').write_text('\\section{One}\nFirst paragraph.\n\n\\section{Two}\nSecond paragraph.\n\nThird paragraph.\n')
    for module in (pv,rv,walk):monkeypatch.setattr(module,'_repo_root',lambda:tmp_path)
    return md


def test_walk_doc_scoped_by_section_and_conditional_by_revision(tmp_path,monkeypatch):
    md=_walk_fixture(tmp_path,monkeypatch)
    full=walk.doc('paper','',identities=True)
    assert full['ok'] and 'partial' not in full and [row['id'] for row in full['section_index']]==[s['id'] for s in full['sections']]
    assert all(set(row)=={'id','file','blocks','file_revision'} for row in full['section_index'])
    two=next(s['id'] for s in full['sections'] if s['title']=='Two')
    part=walk.doc('paper','',identities=True,sections=[two])
    assert part['partial'] is True and part['selected_sections']==[two] and [s['id'] for s in part['sections']]==[two]
    assert part['section_index']==full['section_index'] and part['macros']==full['macros'] and part['current_revision']==full['current_revision']
    assert len(part['sections'][0]['blocks'])==3 and all(block['expected'] for block in part['sections'][0]['blocks'])
    by_file=walk.doc('paper','',files=['body.tex'])
    assert by_file['partial'] and {s['id'] for s in by_file['sections']}=={s['id'] for s in full['sections'] if s['file']=='body.tex'}
    unchanged=walk.doc('paper','',identities=True,known_revision=full['current_revision'])
    assert unchanged=={'ok':True,'unchanged':True,'corpus':'paper','dir':'','project':'paper','source_observation':full['source_observation'],
                       'presentation_revision':full['presentation_revision'],'current_revision':full['current_revision']}
    assert len(json.dumps(unchanged).encode())<len(json.dumps(part).encode())<len(json.dumps(full).encode())
    (md/'body.tex').write_text((md/'body.tex').read_text()+'\nFourth paragraph.\n')
    changed=walk.doc('paper','',known_revision=full['current_revision'])
    assert 'unchanged' not in changed and changed['current_revision']!=full['current_revision'] and len(changed['sections'][-1]['blocks'])==4
    # The HTTP door decodes the selectors.
    code,_,body=walk.handle('/walk/doc',{'corpus':['paper'],'sections':[two],'identities':['1']},'GET',b'')
    assert code==200 and json.loads(body)['selected_sections']==[two]
    code,_,body=walk.handle('/walk/doc',{'corpus':['paper'],'known_revision':[changed['current_revision']]},'GET',b'')
    assert code==200 and json.loads(body)['unchanged'] is True


def test_build_summary_answers_identity_only_for_a_known_revision(tmp_path,monkeypatch):
    _walk_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    code,_,body=authoring_surface.handle('/authoring/build',{'project':['paper'],'view':['summary']},'GET',b'')
    assert code==200;summary=json.loads(body);token=summary['summary_revision'];revision=summary['current_revision']
    assert token.startswith('sha256:') and 'log_tail' not in summary and summary['source_observation']['schema_version']=='laplace.manuscript-source-observation/1'
    code,_,body=authoring_surface.handle('/authoring/build',{'project':['paper'],'view':['summary'],'known_revision':[token]},'GET',b'')
    assert code==200;small=json.loads(body)
    # H2 (2026-10-14): the unchanged answer is the condition token and the status word only
    assert small['unchanged'] is True and small['summary_revision']==token and small['project']=='paper' and 'source_observation' not in small
    assert set(small)=={'project','unchanged','summary_revision','document_status','as_of'} and len(body)<=300,(sorted(small),len(body))
    assert len(body)<len(json.dumps(summary).encode())//4
    # The document revision alone is not the condition: the token covers the delivered projection.
    code,_,body=authoring_surface.handle('/authoring/build',{'project':['paper'],'view':['summary'],'known_revision':[revision]},'GET',b'')
    assert code==200 and 'unchanged' not in json.loads(body)
    code,_,body=authoring_surface.handle('/authoring/build',{'project':['paper'],'view':['summary'],'known_revision':['sha256:stale']},'GET',b'')
    assert code==200 and 'unchanged' not in json.loads(body)


# ---- integrated repair SR1–SR3 (Sol review): reproductions and fixes ----

def test_sr1_scoped_read_is_never_conditional_and_delivers_the_selected_section(tmp_path,monkeypatch):
    _walk_fixture(tmp_path,monkeypatch)
    full=walk.doc('paper','',identities=True)
    one,two=[s['id'] for s in full['sections'] if s['title'] in ('One','Two')]
    first=walk.doc('paper','',identities=True,sections=[one])
    # Reproduction: a second scoped read carrying the first answer's whole-document revision.
    second=walk.doc('paper','',identities=True,sections=[two],known_revision=first['current_revision'])
    assert 'unchanged' not in second and second['partial'] is True and [s['id'] for s in second['sections']]==[two]
    assert second['known_revision_ignored'] is True and second['selected_sections']==[two]
    assert len(second['sections'][0]['blocks'])==3
    code,_,body=walk.handle('/walk/doc',{'corpus':['paper'],'sections':[two],'known_revision':[first['current_revision']]},'GET',b'')
    assert code==200 and json.loads(body)['selected_sections']==[two]


def test_sr1_section_index_witnesses_move_with_the_edited_file_only(tmp_path,monkeypatch):
    md=_walk_fixture(tmp_path,monkeypatch)
    (md/'main.tex').write_text('\\documentclass{../assets/custom}\n\\begin{document}\n\\input{body}\n\\input{extra}\n\\bibliographystyle{../assets/refs}\n\\bibliography{refs}\n\\end{document}\n')
    (md/'extra.tex').write_text('\\section{Three}\nThird section paragraph.\n')
    before={row['id']:row for row in walk.doc('paper','')['section_index']}
    assert len(before)==3
    (md/'body.tex').write_text((md/'body.tex').read_text().replace('First paragraph.','First paragraph, longer now.'))
    after={row['id']:row for row in walk.doc('paper','')['section_index']}
    moved=[ident for ident in before if before[ident]['file_revision']!=after[ident]['file_revision']]
    # Alpha and Bravo share body.tex: both witnesses move (a splice shifts later spans); Three does not.
    assert sorted(moved)==sorted(ident for ident in before if before[ident]['file']=='body.tex') and len(moved)==2
    assert all(before[ident]['file_revision']==after[ident]['file_revision'] for ident in before if before[ident]['file']=='extra.tex')


def _carriers_fixture(root,*,final_reply=True):
    """Every text carrier the summary projection returns, each 100,000 characters.

    The selection is a normal Review/Research one: the full anchor review_surface banks
    (section/paragraph/file/lines/grade/quote/before/after/passage pair/coarse/block), plus
    unknown body fields at every level, admitted through the actual selection producer.
    """
    big=lambda tag:((tag+'-')*100_000)[:100_000]   # exactly 100,000 characters of a named carrier
    anchor={'section':'sec:intro','paragraph_id':'p-3','file':'paper/body.tex','lines':[3,9],'line_start':3,'line_end':9,'grade':'rewrite',
            'sha256':'f'*64,'quote':big('aquote'),'before':big('before'),'after':big('after'),'passage_before':big('pbefore'),'passage_after':big('pafter'),
            'coarse':False,'block':'b-12','scratch_blob':big('ablob'),'nested_unknown':{'deep':big('deep')}}
    payload={'files':['paper/body.tex'],'section_ids':['one'],'line_start':3,'line_end':9,'quote':big('quote'),'anchor':anchor,
             'unknown_selection_field':big('sblob'),'draft':{'status':'UNSAVED','format':'tex','text':big('draft')[:turn_context._DRAFT_TEXT_LIMIT],'reason':big('reason')[:1000],'anchor':{'file':'paper/body.tex','line_start':3,'line_end':9}}}
    selection,draft=turn_context._selection_draft(payload)   # the actual producer of stored selections and drafts
    assert 'draft' not in selection and selection['anchor'] is anchor
    errors=[{'field':'text','content_handle':'sha256:'+'0'*64,'error':big('storage'),'extra_blob':big('eblob'),'context':{'deep':big('edeep')}}]*7
    records.bank(root,{'record':'writing-session','id':'WS-big','project':'book','title':'Big','provider':'claude','model':'m','effort':'low','role':'worker','packet':'P9','dispatch_id':'WORK-d'})
    records.bank(root,{'record':'writing-turn','id':'WT-big','session_id':'WS-big','project':'book','mode':'work','text':big('request'),'ts':'2026-10-12T00:00:00Z',
        'selection':selection,'unsaved_draft':draft,'workspace_context':{'surface':'project','label':'Project'},
        'queued_work_ids':[f'WORK-{i}' for i in range(30)],'custody_errors':errors,
        'steering':[{'id':f'ST-{i}','text':big('steer'),'selection':selection,'unsaved_draft':draft,'workspace_context':{'surface':'project'},'ts':'2026-10-12T00:00:01Z'} for i in range(7)],
        'pending_proposal':{'answer':big('answer'),'edits':[{'file':'paper/body.tex','line_start':3,'line_end':3,'before':'Original prose.','after':big('after')}]}})
    if final_reply:
        records.bank(root,{'record':'writing-reply','id':'WR-big','turn_id':'WT-big','session_id':'WS-big','project':'book','status':'completed','text':big('reply'),'error':big('error'),'ts':'2026-10-12T00:00:02Z'})
    return big


@pytest.mark.parametrize('final_reply',[True,False])
def test_sr2_every_text_carrier_is_bounded_by_one_policy_and_exact_on_demand(tmp_path,final_reply):
    big=_carriers_fixture(tmp_path,final_reply=final_reply)
    from laplace.writing import records
    before=json.dumps(records.fold_records(tmp_path)['turns']['WT-big'],sort_keys=True,default=str)
    row,=session_reads.session_state(tmp_path,'WS-big',view='summary',limit=20)['turns']
    encoded=len(json.dumps(row).encode())
    # The row is at most the sum of the declared limits (plus keys, coordinates and markers):
    # was 403,354 B with four unbounded carriers, and 109,874 B with the proposal answer alone.
    text,reply,note=session_projection.ROW_TEXT_LIMIT,session_projection.ROW_REPLY_LIMIT,session_projection.ROW_NOTE_LIMIT
    steer_rows,steer_text=session_projection.ROW_STEERING,session_projection.ROW_STEERING_TEXT
    policy=text+note+steer_rows*(steer_text+note)+reply+text+note+session_projection.ROW_STORAGE_ERRORS*note
    # Character limits, not a universal byte ceiling: this ASCII fixture encodes one byte per character.
    assert encoded<policy+4_000,(encoded,policy)   # the rest is identities, coordinates, anchors and markers
    cut=lambda value,n:value==big(value.split('-')[0])[:n]
    # request on the row; the selection keeps its coordinates and anchor, its quote is on summary_read
    assert cut(row['text'],text) and row['text_truncated'] is True and row['text_chars']==100_000
    assert 'quote' not in row['selection'] and row['selection']['line_start']==3 and 'draft' not in row['selection']
    # Closed shapes at every level: exact coordinates/guards, bounded passage texts, no unknown field.
    def closed_anchor(a):
        assert set(a)<=set(session_projection.ANCHOR_EXACT),sorted(a)
        assert a['file']=='paper/body.tex' and a['lines']==[3,9] and a['line_start']==3 and a['line_end']==9 and a['section']=='sec:intro' and a['paragraph_id']=='p-3' and a['grade']=='rewrite' and a['sha256']=='f'*64 and a['coarse'] is False and a['block']=='b-12'
        # No thread-row consumer reads an anchor's passage texts; they stay in the exact record.
        for key in ('quote','before','after','passage_before','passage_after'): assert key not in a
    assert set(row['selection'])<=set(session_projection.SELECTION_EXACT)|{'anchor','quote_chars'},sorted(row['selection'])
    assert row['selection']['quote_chars']==100_000 and 'quote' not in row['selection'],'the omitted quote keeps its length (R2)'
    closed_anchor(row['selection']['anchor'])
    # the draft travels as its presence and length; the words are on summary_read
    assert row['unsaved_draft']['status']=='UNSAVED' and row['unsaved_draft']['anchor']['file']=='paper/body.tex' and row['unsaved_draft']['text_omitted'] is True and row['unsaved_draft']['text_chars']==turn_context._DRAFT_TEXT_LIMIT and 'text' not in row['unsaved_draft']
    assert cut(row['unsaved_draft']['reason'],note) and row['unsaved_draft']['reason_truncated'] is True
    # steering: ROW_STEERING rows shaped the same way; the rest counted
    assert 'steering' not in row and row['steering_total']==7 and row['steering_truncated'] is True
    # proposal answer fallback (also the only answer when no final reply was saved)
    assert cut(row['proposal_answer'],text) and row['proposal_answer_truncated'] is True and row['proposal_edit_count']==1
    # reply: excerpt and bounded error, meter exact, no body
    if final_reply:
        assert cut(row['reply']['display_text'],reply) and row['reply']['display_text_truncated'] is True and 'text' not in row['reply']
        assert cut(row['reply']['error'],note) and row['reply']['error_truncated'] is True and row['reply']['status']=='completed'
    else:
        assert 'reply' not in row and row['proposal_state'] is not None
    # storage errors and other collections: counted on the row, listed on summary_read
    assert len(row['storage_errors'])==session_projection.ROW_STORAGE_ERRORS and row['storage_errors_total']==7 and row['storage_errors_truncated'] is True
    for e in row['storage_errors']: assert cut(e['message'],note) and e['message_truncated'] is True and e['field']=='text' and e['content_handle']=='sha256:'+'0'*64 and set(e)=={'field','content_handle','message','message_chars','message_truncated'}
    assert 'queued_work_ids' not in row and row['queued_work_ids_total']==30
    assert row['packet']=='P9' and row['role']=='worker' and 'workspace_context' not in row
    # Nothing owner-side was mutated by shaping the row.
    assert json.dumps(records.fold_records(tmp_path)['turns']['WT-big'],sort_keys=True,default=str)==before
    # Exact originals on demand: the single-turn summary and the exact turn.
    single=session_reads.session_turn_detail(tmp_path,'book','WT-big','summary')['turn']
    assert single['text']==big('request') and single['selection']['quote']==big('quote') and single['selection']['anchor']['passage_before']==big('pbefore') and single['selection']['unknown_selection_field']==big('sblob') and single['selection']['anchor']['nested_unknown']['deep']==big('deep') and len(single['steering'])==7
    assert single['unsaved_draft']['text']==big('draft')[:turn_context._DRAFT_TEXT_LIMIT] and single['storage_errors'][0]['extra_blob']==big('eblob')
    assert len(single['queued_work_ids'])==30 and len(single['storage_errors'])==7 and len(single['steering'])==7 and single['selection']['quote']==big('quote')
    assert single['proposal_answer']==big('answer') and single['packet']=='P9'
    if final_reply: assert single['reply']['display_text']==big('reply') and single['reply']['error']==big('error')
    exact=session_reads.session_turn_detail(tmp_path,'book','WT-big','turn')['turn']
    assert exact['text']==big('request') and exact['steering'][6]['text']==big('steer') and exact['steering'][6]['selection']['anchor']['scratch_blob']==big('ablob')
    if final_reply: assert exact['reply']['text']==big('reply')


def test_sr3_build_condition_covers_a_new_job_on_unchanged_source(tmp_path,monkeypatch):
    _walk_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    from laplace.manuscript import projection_viewer
    statuses=iter([{'state':'running','ok':None,'fresh':False,'running':True,'build_job':'BLD-one','started':1.0,'present':False,'pdf':None},
                   {'state':'running','ok':None,'fresh':False,'running':True,'build_job':'BLD-one','started':1.0,'present':False,'pdf':None},
                   {'state':'running','ok':None,'fresh':False,'running':True,'build_job':'BLD-two','started':2.0,'present':False,'pdf':None},
                   {'state':'done','ok':True,'fresh':True,'running':False,'build_job':'BLD-two','started':2.0,'finished':3.0,'present':True,'pdf':'paper/main.pdf'}])
    monkeypatch.setattr(projection_viewer,'recompile_status',lambda *a,**k:dict(next(statuses)))
    read=lambda **extra:json.loads(authoring_surface.handle('/authoring/build',{'project':['paper'],'view':['summary'],**{k:[v] for k,v in extra.items()}},'GET',b'')[2])
    first=read();assert first['build_job']=='BLD-one' and first['running'] is True
    same=read(known_revision=first['summary_revision']);assert same['unchanged'] is True and same['summary_revision']==first['summary_revision']
    # Reproduction: identical source, a different running job. The old token must not hide it.
    newjob=read(known_revision=first['summary_revision'])
    assert 'unchanged' not in newjob and newjob['build_job']=='BLD-two' and newjob['summary_revision']!=first['summary_revision'] and newjob['current_revision']==first['current_revision']
    finished=read(known_revision=newjob['summary_revision'])
    assert 'unchanged' not in finished and finished['state']=='done' and finished['pdf']=='paper/main.pdf' and finished['summary_revision']!=newjob['summary_revision']


# ---- sequential edits: the identity published with the saved source, and the verified repo_file ----

def _sequential_fixture(tmp_path,monkeypatch):
    """A throwaway manuscript tree with every owner rooted at tmp_path (no registry: an unregistered source)."""
    from test_editor_doors import _md
    from laplace.web import shared_ui
    from laplace.pipeline import registry
    md=_md(tmp_path)
    for module in (rv,walk,pv,shared_ui,registry):monkeypatch.setattr(module,'_repo_root',lambda:tmp_path)
    monkeypatch.setattr(rv,'manuscript_dir',lambda corpus='',dir_param='':md)
    monkeypatch.setattr(rv,'_project_name',lambda corpus,md_:'proj')
    return md


def _paragraph_token(md,line):
    """The token the canvas read publishes for the block at `line` of N1.tex, exactly as `_reloadBlock` adopts it."""
    model=walk.doc(dir_param=str(md),identities=True)
    block=next(b for s in model['sections'] for b in s['blocks'] if b['src']['file']=='N1.tex' and b['src']['line_start']==line)
    return block['expected'],block['tex'],block['src']


def _rewrite(md,before,after,expected,**extra):
    from test_editor_doors import _P1_SPAN
    payload={'verb':'rewrite','by':'author','corpus':'proj','section':'N1','file':'N1.tex','line_start':_P1_SPAN[0],'line_end':_P1_SPAN[1],
             'before':before,'after':after,'passage_before':before,'passage_after':after,
             **({'expected':expected} if expected is not None else {}),**extra}
    return rv.adjudicate(md,'proj',payload,repo_root=md.parent)


@pytest.mark.parametrize('edits',[
    ('plain', 'The quick brown fox jumps over the sleepy dog.', 'The quick brown fox leaps over the sleepy dog.'),
    ('typography-inline-tex', 'The quick brown fox --- jumps over the lazy dog $x^2$.', 'The quick brown fox --- jumps over the lazy dog $x^3$.')])
def test_two_consecutive_edits_pass_only_with_the_identity_published_with_the_saved_source(tmp_path,monkeypatch,edits):
    from test_editor_doors import _P1_SPAN,_P1_TEXT,_rows
    md=_sequential_fixture(tmp_path,monkeypatch);line=_P1_SPAN[0];_,first_after,second_after=edits
    t1,tex1,_=_paragraph_token(md,line);assert tex1==_P1_TEXT
    first=_rewrite(md,_P1_TEXT,first_after,t1)
    assert first['ok'] and first['pending'] is False,'the first ordinary edit saves with the published token'
    t2,tex2,_=_paragraph_token(md,line);assert tex2==first_after and t2!=t1,'the owner publishes a new identity with the new source'
    # The served snapshot's mechanism: the next edit sent the OLD token although raw before == found.
    stale=_rewrite(md,first_after,second_after,t1)
    assert stale['pending'] is True and stale['applied'] is None and stale['receipt']['refused']['kind']=='identity-stale'
    assert stale['receipt']['refused']['needed']['expected']==t2 and stale['record']['anchor']['found']==first_after
    text=(md/'N1.tex').read_text(encoding='utf-8');assert first_after in text and second_after not in text,'nothing was spliced; the draft stands as a pending row'
    # With the identity adopted from the re-read the second ordinary edit applies.
    fixed=_rewrite(md,first_after,second_after,t2)
    assert fixed['ok'] and fixed['pending'] is False and second_after in (md/'N1.tex').read_text(encoding='utf-8')
    # New applied AND pending rows carry the verified checkout-relative identity beside the manuscript path.
    rows=[row for row in _rows(md) if row.get('kind') in {'author-rewrite','pending-rewrite'}]
    assert [row['kind'] for row in rows]==['author-rewrite','pending-rewrite','author-rewrite']
    assert all(row['anchor']['file']=='N1.tex' and row['anchor']['repo_file']=='ms/N1.tex' for row in rows)
    # A shifted span: the paragraph below keeps its bytes, moves one line, and the owner publishes
    # the same digest at its CURRENT address (the home the door will compare), never the old one.
    before_shift=_paragraph_token(md,8)[0][0]
    grown=_rewrite(md,second_after,second_after+'\nA second line of the same paragraph.',_paragraph_token(md,line)[0])
    assert grown['ok'] and grown['pending'] is False
    after_shift,tex_p2,src_p2=_paragraph_token(md,9)
    assert 'lazy dog sleeps' in tex_p2 and src_p2['line_start']==9
    assert after_shift[0]!=before_shift and after_shift[0].rsplit(':',1)[1]==before_shift.rsplit(':',1)[1] and ':N1.tex:9-9:' in after_shift[0] and ':N1.tex:8-8:' in before_shift


def test_history_binds_new_passage_records_through_the_banked_repo_file_and_leaves_old_rows_unproved(tmp_path,monkeypatch):
    from test_editor_doors import _P1_SPAN,_P1_TEXT
    md=_sequential_fixture(tmp_path,monkeypatch)
    t1,_,_=_paragraph_token(md,_P1_SPAN[0])
    applied=_rewrite(md,_P1_TEXT,'The quick brown fox jumps over the sleepy dog.',t1);assert applied['ok'] and applied['pending'] is False
    # M5 S3: the pending row is the door's own byte-mismatch path, a rewrite that carries NO identity guard. An EMPTY
    # guard is not that path: the identity door refuses it as malformed before any effect, and stays strict.
    from laplace.core import identity_doors
    with pytest.raises(identity_doors.IdentityRefused):_rewrite(md,'stale text the caller read','whatever',[])
    pending=_rewrite(md,'stale text the caller read','whatever',None);assert pending['pending'] is True
    # An older row that retained only a basename, exactly as it was banked: no inferred migration.
    with (md/'feedback'/'feedback.jsonl').open('a',encoding='utf-8') as ledger:
        ledger.write(json.dumps({'id':'FB-legacy','kind':'author-rewrite','by':'author','ts':'2026-10-01T00:00:00Z','comment':'old','anchor':{'file':'N1.tex','lines':[5,5],'before':'a','after':'b','applied':True}})+'\n')
    monkeypatch.setattr(author_history,'_manuscript_dir',lambda project,root:md)
    items,records,notes=author_history._correction_items('proj',tmp_path)
    assert notes==[]
    by_id={item['id'].split(':')[-1]:item['targets'][0] for item in items}
    for ident in (applied['record']['id'],pending['record']['id']):
        target=by_id[ident];assert target['binding']=='BOUND' and target['repo_file']=='ms/N1.tex' and target['file']=='N1.tex' and target['correction_id']==ident
    assert by_id['FB-legacy']['binding']=='UNPROVED' and 'repo_file' not in by_id['FB-legacy']
    # The authored identity binds as recorded; a malformed one is ignored rather than trusted.
    assert author_history._manuscript_target(tmp_path,'N1.tex',repo_file='ms/N1.tex')=={'kind':'manuscript','file':'N1.tex','repo_file':'ms/N1.tex','binding':'BOUND'}
    assert author_history._manuscript_target(tmp_path,'N1.tex',repo_file='../escape.tex')['binding']=='UNPROVED'
    assert author_history._manuscript_target(tmp_path,'N1.tex',repo_file='/abs/N1.tex')['binding']=='UNPROVED'


# ---- C1e / G16: the research state is served from its owned index witness ----

def _research_fixture(tmp_path):
    from test_research_surface import _project as research_project
    return research_project(tmp_path)


def test_research_state_is_cached_by_its_index_witness_and_invalidated_by_every_owned_input(tmp_path):
    from laplace.web import research_surface as rs
    from laplace.research import research_catalogue as cache
    from laplace.research import research_records
    cache.state_cache_clear()
    manuscript=_research_fixture(tmp_path)
    status,_=research_records.record('fixture',{'kind':'experiment','id':'experiment:one','config':'config.json','data':['data.json'],'source':'source.py'},tmp_path);assert status==201
    (manuscript/'result.json').write_text('{"score": 1}',encoding='utf-8')
    status,_=research_records.record('fixture',{'kind':'result','id':'result:one','result':'result.json'},tmp_path);assert status==201
    numerics=manuscript.parent/'numerics';(numerics/'deep').mkdir(parents=True);(numerics/'deep'/'table.csv').write_text('a,b\n')
    hashed=[]
    original=research_observation._digest
    def counting(path):hashed.append(str(path));return original(path)
    research_observation._digest=counting
    try:
        first=cache.state_payload('fixture',tmp_path)
        assert first['read_basis']['cache']=='miss' and first['index_stamp'].startswith('sha256:') and first['currentness']['status']=='CURRENT'
        assert [row['path'] for row in first['available_sources']]==['numerics/deep/table.csv'] or any(row['path'].endswith('deep/table.csv') for row in first['available_sources'])
        hashed_first=len(hashed);assert hashed_first>0
        second=cache.state_payload('fixture',tmp_path)
        assert second['read_basis']['cache']=='hit' and second['index_stamp']==first['index_stamp'] and len(hashed)==hashed_first,'a hit hashes no bytes'
        second['results'].clear();assert cache.state_payload('fixture',tmp_path)['results'],'a hit is a copy; consumers cannot mutate the retained entry'
        # the HTTP catalogue rides the same cache and names its basis
        code,_,raw=rs.handle('/research/state',{'project':['fixture'],'view':['summary']},'GET',b'',repo_root=tmp_path)
        summary=json.loads(raw);assert code==200 and summary['read_basis']['cache']=='hit' and summary['index_stamp']==first['index_stamp']
        # every owned input invalidates: a hashed dependency, the records index, the manifest, a new file deep in a scan root
        (manuscript/'data.json').write_text('[1, 2, 3, 4]',encoding='utf-8')
        stale=cache.state_payload('fixture',tmp_path);assert stale['read_basis']['cache']=='miss' and stale['currentness']['status']=='STALE' and stale['index_stamp']!=first['index_stamp']
        assert cache.state_payload('fixture',tmp_path)['read_basis']['cache']=='hit'
        (numerics/'deep'/'later.json').write_text('{}')
        grown=cache.state_payload('fixture',tmp_path);assert grown['read_basis']['cache']=='miss' and any(row['path'].endswith('deep/later.json') for row in grown['available_sources'])
        manifest=manuscript/'figure_manifest.json';manifest.write_text(manifest.read_text()+'\n')
        assert cache.state_payload('fixture',tmp_path)['read_basis']['cache']=='miss'
        status,_=research_records.record('fixture',{'kind':'result','id':'result:two','result':'result.json'},tmp_path);assert status==201
        assert cache.state_payload('fixture',tmp_path)['read_basis']['cache']=='miss'
        assert cache.state_payload('fixture',tmp_path)['read_basis']['cache']=='hit'
        # the TTL bounds cross-owner staleness; an entry past it derives again even when unchanged
        with cache._STATE_CACHE_LOCK:
            for entry in cache._STATE_CACHE.values():entry['at']-=cache.STATE_CACHE_TTL_S+1
        assert cache.state_payload('fixture',tmp_path)['read_basis']['cache']=='miss'
        # finite retention
        for n in range(cache.STATE_CACHE_MAX_ENTRIES+3):
            with cache._STATE_CACHE_LOCK:cache._STATE_CACHE[f'/elsewhere::{n}']={'at':0,'witness':{},'stamp':'x','payload':{}};cache._STATE_CACHE.move_to_end(f'/elsewhere::{n}')
        with cache._STATE_CACHE_LOCK:
            for entry in cache._STATE_CACHE.values():entry['at']=-10**9   # every entry is past its TTL: the next read stores afresh
        assert cache.state_payload('fixture',tmp_path)['read_basis']['cache']=='miss'
        with cache._STATE_CACHE_LOCK:assert len(cache._STATE_CACHE)<=cache.STATE_CACHE_MAX_ENTRIES and f'{tmp_path.resolve()}::fixture' in cache._STATE_CACHE
    finally:
        research_observation._digest=original;cache.state_cache_clear()


def test_research_state_is_published_only_when_its_read_time_witness_holds(tmp_path):
    """Sol RESEARCH-CACHE (2026-10-12): an input that changes DURING the derivation used to
    be published as CURRENT under a fresh stamp. Now the derivation is retried, and when the
    inputs keep moving it is served uncached and says so."""
    from laplace.research import research_catalogue as cache
    from laplace.research import research_records
    cache.state_cache_clear()
    manuscript=_research_fixture(tmp_path)
    status,_=research_records.record('fixture',{'kind':'experiment','id':'experiment:one','config':'config.json','data':['data.json'],'source':'source.py'},tmp_path);assert status==201
    original=research_observation._digest;moved=[]
    def mutate_once(path):
        observation=original(path)
        if path.name=='data.json' and not moved:
            moved.append(path);(manuscript/'data.json').write_text('[9, 9, 9]',encoding='utf-8')   # changes after it was hashed
        return observation
    research_observation._digest=mutate_once
    try:
        value=cache.state_payload('fixture',tmp_path)
        assert moved and value['read_basis']['cache']=='miss' and value['read_basis']['retries']==1
        assert value['currentness']['status']=='STALE','the published derivation saw the moved input; the stale CURRENT answer was not published'
        assert cache.state_payload('fixture',tmp_path)['read_basis']['cache']=='hit'
        basis=value['read_basis'];assert set(basis)>={'cache','index_stamp','observed_at','age_s','asset_join'} and basis['asset_join']['basis']=='ttl' and basis['asset_join']['ttl_s']==cache.STATE_CACHE_TTL_S
        # inputs that move on EVERY attempt: bounded retries, then an honest uncached answer that is not retained
        cache.state_cache_clear();counter=[0]
        def mutate_always(path):
            observation=original(path)
            if path.name=='data.json':
                counter[0]+=1;(manuscript/'data.json').write_text(json.dumps([counter[0]]),encoding='utf-8')
            return observation
        research_observation._digest=mutate_always
        value=cache.state_payload('fixture',tmp_path)
        assert value['read_basis']['cache']=='uncached' and value['read_basis']['retries']==cache.STATE_DERIVE_ATTEMPTS-1 and 'reason' in value['read_basis']
        with cache._STATE_CACHE_LOCK:assert f'{tmp_path.resolve()}::fixture' not in cache._STATE_CACHE
        research_observation._digest=original
        assert cache.state_payload('fixture',tmp_path)['read_basis']['cache']=='miss'
    finally:
        research_observation._digest=original;cache.state_cache_clear()


def _retained_run_fixture(tmp_path, *, state='COMPLETE'):
    """A result record naming a legacy run whose job, receipt and result live beside each other."""
    from laplace.research import research_records
    manuscript=_research_fixture(tmp_path)
    status,_=research_records.record('fixture',{'kind':'experiment','id':'experiment:one','config':'config.json','data':['data.json'],'source':'source.py'},tmp_path);assert status==201
    (manuscript/'result.json').write_text('{"score": 1}',encoding='utf-8')
    runs=manuscript/'research_runs';runs.mkdir(exist_ok=True)
    result=manuscript/'result.json'   # the run's declared output IS the record's result file
    import hashlib
    job={'id':'run-one','project':'fixture','state':state,'result_path':'result.json',
         'result_absolute':str(result),'pid':os.getpid(),'deadline_at':time.time()+600}
    (runs/'run-one.json').write_text(json.dumps(job))
    (runs/'run-one.receipt.json').write_text(json.dumps({'state':'COMPLETE','result_sha256':hashlib.sha256(result.read_bytes()).hexdigest()}))
    status,_=research_records.record('fixture',{'kind':'result','id':'result:one','result':'result.json'},tmp_path);assert status==201
    # the record door admits a run_id only for a run it can prove current; this synthetic
    # legacy run is bound in the retained records container directly (tmp fixture, no owner)
    container=manuscript/research_records._RECORDS;data=json.loads(container.read_text())
    for row in data['records']:
        if row.get('id')=='result:one':row['run_id']='run-one'
    container.write_text(json.dumps(data))
    return manuscript,runs


def test_research_cache_witnesses_run_receipts_consumed_during_derivation(tmp_path):
    """Sol RESEARCH-CACHE (2026-10-12, second review): changing <run>.receipt.json produced a HIT
    with the old state while an uncached read showed FAILED; the receipt was never witnessed."""
    from laplace.research import research_catalogue as cache
    cache.state_cache_clear()
    manuscript,runs=_retained_run_fixture(tmp_path)
    first=cache.state_payload('fixture',tmp_path)
    run=next(row for row in first['producer_runs'] if row['id']=='run-one')
    assert first['read_basis']['cache']=='miss' and run['state'] in {'COMPLETE','STALE'} and 'live_facts' not in first['read_basis']
    witness=cache._STATE_CACHE[f'{tmp_path.resolve()}::fixture']['witness']['files']
    assert str(runs/'run-one.receipt.json') in witness and str(manuscript/'result.json') in witness,'the receipt and the result output are witnessed because they were consumed'
    assert cache.state_payload('fixture',tmp_path)['read_basis']['cache']=='hit'
    (runs/'run-one.receipt.json').write_text(json.dumps({'state':'FAILED','exit_code':3}))
    changed=cache.state_payload('fixture',tmp_path)
    assert changed['read_basis']['cache']=='miss' and next(row for row in changed['producer_runs'] if row['id']=='run-one')['state']=='FAILED'
    uncached=cache.state_payload('fixture',tmp_path,cached=False)
    assert next(row for row in uncached['producer_runs'] if row['id']=='run-one')['state']=='FAILED','a hit and an uncached read agree'
    cache.state_cache_clear()


def test_research_live_process_facts_are_qualified_and_short_lived(tmp_path):
    from laplace.research import research_catalogue as cache
    cache.state_cache_clear()
    manuscript,runs=_retained_run_fixture(tmp_path,state='RUNNING')
    (runs/'run-one.receipt.json').unlink()
    first=cache.state_payload('fixture',tmp_path)
    live=first['read_basis']['live_facts']
    assert live['runs']==['run-one'] and live['basis']=='ttl' and live['ttl_s']==cache.STATE_CACHE_LIVE_TTL_S and 'sampled' in live['note']
    assert first['read_basis']['asset_join']['ttl_s']==cache.STATE_CACHE_LIVE_TTL_S,'the whole entry lives only as long as its live facts'
    second=cache.state_payload('fixture',tmp_path);assert second['read_basis']['cache']=='hit' and second['read_basis']['live_facts']['runs']==['run-one']
    with cache._STATE_CACHE_LOCK:
        for entry in cache._STATE_CACHE.values():entry['at']-=cache.STATE_CACHE_LIVE_TTL_S+0.5
    assert cache.state_payload('fixture',tmp_path)['read_basis']['cache']=='miss','past the live TTL the processes are sampled again'
    cache.state_cache_clear()


class _Clock:
    """A controllable clock standing in for the research owner's `time` module."""
    def __init__(self):self.wall=1_700_000_000.0;self.mono=1000.0
    def advance(self,seconds):self.wall+=seconds;self.mono+=seconds
    def time(self):return self.wall
    def monotonic(self):return self.mono
    def __getattr__(self,name):return getattr(time,name)


def test_research_ttl_is_anchored_to_observation_and_an_expired_derivation_is_not_retained(tmp_path,monkeypatch):
    """Sol (2026-10-12, repair review): retention started at publication, so a 3 s derivation of a
    2 s live entry was served as a HIT at age 3 with zero remaining."""
    from laplace.research import research_catalogue as cache
    cache.state_cache_clear()
    manuscript,runs=_retained_run_fixture(tmp_path,state='RUNNING');(runs/'run-one.receipt.json').unlink()
    # S1 B5: the clock and the derivation are read by the cache's one owner, writing.research_catalogue.
    clock=_Clock();monkeypatch.setattr(cache,'time',clock)
    original=cache._derive_state;slow=[3.0]
    def slow_derive(project,root):
        value=original(project,root);clock.advance(slow[0]);return value
    monkeypatch.setattr(cache,'_derive_state',slow_derive)
    first=cache.state_payload('fixture',tmp_path)
    assert first['read_basis']['cache']=='uncached' and 'longer than the 2 s retention' in first['read_basis']['reason'],'a live entry whose derivation outlived its TTL is served but not retained'
    with cache._STATE_CACHE_LOCK:assert f'{tmp_path.resolve()}::fixture' not in cache._STATE_CACHE
    slow[0]=1.0
    second=cache.state_payload('fixture',tmp_path)
    assert second['read_basis']['cache']=='miss' and second['read_basis']['live_facts']['remaining_s']==1.0,'remaining is measured from observation, not publication'
    clock.advance(0.5)
    third=cache.state_payload('fixture',tmp_path)
    assert third['read_basis']['cache']=='hit' and third['read_basis']['age_s']==1.5 and third['read_basis']['live_facts']['remaining_s']==0.5
    clock.advance(0.6)
    assert cache.state_payload('fixture',tmp_path)['read_basis']['cache']=='miss','2.1 s after observation the live entry has expired'
    # the ordinary 30 s domain is anchored the same way
    (runs/'run-one.json').unlink()
    slow[0]=3.0;clock.advance(1)
    plain=cache.state_payload('fixture',tmp_path);assert plain['read_basis']['cache']=='miss' and 'live_facts' not in plain['read_basis']
    clock.advance(26.5);assert cache.state_payload('fixture',tmp_path)['read_basis']['cache']=='hit'
    clock.advance(1);assert cache.state_payload('fixture',tmp_path)['read_basis']['cache']=='miss','30 s after observation (27 after publication) the entry is gone'
    cache.state_cache_clear()


def test_research_derivation_footprint_is_fully_witnessed(tmp_path,monkeypatch):
    """The audit Sol asked for: every file the derivation reads or probes under the project
    root must be in the witness, so no hand-missed path can masquerade as a current hit."""
    from pathlib import Path as P
    from laplace.research import research_catalogue as cache
    cache.state_cache_clear()
    manuscript,runs=_retained_run_fixture(tmp_path)
    numerics=manuscript.parent/'numerics';numerics.mkdir();(numerics/'table.csv').write_text('a\n')
    (manuscript/'producers.json').write_text(json.dumps({'producers':[{'id':'prod','executable':'source.py'}]}))
    reads,probes=set(),set()
    base=str(tmp_path.resolve())
    def spy(name,bucket):
        original=getattr(P,name)
        def wrapped(self,*args,**kwargs):
            if str(self).startswith(base):bucket.add(str(self))
            return original(self,*args,**kwargs)
        monkeypatch.setattr(P,name,wrapped)
    for name in ('read_text','read_bytes','open'):spy(name,reads)
    for name in ('is_file','exists'):spy(name,probes)
    payload,witness,_digests,ledger=cache._derive_state('fixture',tmp_path.resolve())
    files=set(witness['files']);dirs=[P(d) for d in witness['dirs']]
    under_dir=lambda p:any(P(p).is_relative_to(d) for d in dirs)
    unwitnessed_reads=sorted(p for p in reads if p not in files)
    unwitnessed_probes=sorted(p for p in probes if p not in files and not under_dir(p))
    assert reads and unwitnessed_reads==[],unwitnessed_reads
    assert unwitnessed_probes==[],unwitnessed_probes
    assert str(runs/'run-one.receipt.json') in ledger['files'] and ledger['live']=={}
    # the ledger's identities are the ones taken when the file was consumed
    for path,identity in ledger['files'].items():assert witness['files'][path]==identity


def test_research_state_witnesses_absent_scan_roots(tmp_path):
    """Sol RESEARCH-CACHE (2026-10-12): creating the absent numerics directory and a file in it
    returned a stale hit, because only existing roots were witnessed."""
    from laplace.research import research_catalogue as cache
    cache.state_cache_clear()
    manuscript=_research_fixture(tmp_path)
    numerics=manuscript.parent/'numerics';assert not numerics.exists()
    first=cache.state_payload('fixture',tmp_path);assert first['read_basis']['cache']=='miss' and first['available_sources']==[]
    assert str(numerics) in cache._STATE_CACHE[f'{tmp_path.resolve()}::fixture']['witness']['dirs'],'the absent root is witnessed'
    assert cache.state_payload('fixture',tmp_path)['read_basis']['cache']=='hit'
    numerics.mkdir();(numerics/'fresh.csv').write_text('a\n')
    grown=cache.state_payload('fixture',tmp_path)
    assert grown['read_basis']['cache']=='miss' and [row['path'] for row in grown['available_sources']]==['numerics/fresh.csv']
    cache.state_cache_clear()


def test_detail_member_pages_refuse_a_changed_membership_order(tmp_path):
    """Sol STRUCTURE-CONTINUATION (2026-10-12): reversing the node order between two member
    pages returned the same member twice. A continuation now carries the ordered-membership
    cut it was paging and a changed plan refuses it."""
    from test_project_structure import _fixture
    from laplace.manuscript import project_structure as structure
    from laplace.web import project_work_surface
    manuscript=_fixture(tmp_path)
    first=structure.read('book',{'view':'detail','section_ids':['N1'],'member_limit':1},tmp_path)['sections'][0]['members']
    assert [row['id'] for row in first['items']]==['res:one'] and first['cut'].startswith('sha256:') and first['next_read']['payload']['member_cut']==first['cut']
    second=structure.read('book',first['next_read']['payload'],tmp_path)['sections'][0]['members']
    assert [row['id'] for row in second['items']]==['def:one'] and second['cut']==first['cut']
    plan_path=manuscript/'projection_plan.json';plan=json.loads(plan_path.read_text())
    plan['sections'][0]['nodes_in_order']=['def:one','res:one'];plan_path.write_text(json.dumps(plan,indent=2))
    with pytest.raises(ValueError,match='CHANGED_INPUT'):
        structure.read('book',first['next_read']['payload'],tmp_path)
    continuation={key:[json.dumps(v) if isinstance(v,list) else str(v)] for key,v in first['next_read']['payload'].items()}
    code,_,raw=project_work_surface.handle('/work/structure',{'project':['book'],**continuation},'GET',b'',repo_root=tmp_path)
    assert code==422 and 'CHANGED_INPUT' in json.loads(raw)['error']
    fresh=structure.read('book',{'view':'detail','section_ids':['N1'],'member_limit':1},tmp_path)['sections'][0]['members']
    assert fresh['cut']!=first['cut'] and [row['id'] for row in fresh['items']]==['def:one']
    assert 'member_cut' in json.dumps(structure.read_contract()),'the detail contract declares the cut'


def test_research_source_scan_walks_once_without_rglob_and_skips_hidden_parts(tmp_path):
    from laplace.research import research_catalogue as cache
    base=tmp_path/'numerics';(base/'.cache').mkdir(parents=True);(base/'b'/'c').mkdir(parents=True)
    for rel in ('top.csv','b/mid.json','b/c/deep.py','.cache/hidden.csv','b/.secret.txt','b/ignored.bin'):(base/rel).write_text('x')
    assert [p.relative_to(base).as_posix() for p in cache._walk_sources(base)]==['top.csv','b/mid.json','b/c/deep.py']
    before=cache._directory_signature(base)
    (base/'b'/'c'/'new.csv').write_text('y')
    assert cache._directory_signature(base)!=before,'a file added deep in the tree moves its directory signature'
    # S1 B5: the derivation lives in its owner, writing.research_catalogue; the facade only re-exports it.
    from laplace.research import research_catalogue
    derive=Path(research_catalogue.__file__).read_text().split('def _derive_state(')[1].split('def _catalogue_result(')[0]
    assert 'rglob(' not in derive and '_walk_sources(' in derive,'the state derivation enumerates sources through the one walk'


# ---- C1g / G18, G18b, P4: reader-plan list rows and trimmed outline rows with detail handles ----

def test_reader_plan_summary_rows_are_the_list_and_detail_keeps_members_correspondence_and_actions(tmp_path):
    from test_project_structure import _fixture
    from laplace.manuscript import project_structure as structure
    _fixture(tmp_path)
    summary=structure.read('book',{'view':'summary'},tmp_path)
    assert summary['schema_version']=='laplace.project-structure-summary/2'
    rows=summary['sections']['items'];assert rows
    for row in rows:
        assert set(row)=={'id','title','kind','parent_id','number','order','job','collection','precision','binding_status','member_count','detail_read'},sorted(row)
        assert row['detail_read']=={'operation':'structure','payload':{'view':'detail','section_ids':[row['id']]}}
    assert len(json.dumps(rows).encode())/len(rows)<600,'a list row is bounded by its title and purpose'
    full=structure.state('book',tmp_path)
    detail=structure.read('book',rows[0]['detail_read']['payload'],tmp_path)
    section=detail['sections'][0]
    assert section['source']==full['sections'][0]['source'] and section['clearing_action'] and section['members']['total']==rows[0]['member_count']
    assert [m['role'] for m in section['members']['items']]==['node']*len(section['node_ids'])+['beat']*len(section['beat_ids'])
    assert section['members']['items'][0]['detail_read']['operation']=='concept'
    # the HTTP door decodes the detail member paging it already coerces
    from laplace.web import project_work_surface
    code,_,raw=project_work_surface.handle('/work/structure',{'project':['book'],'view':['detail'],'section_ids':['["'+rows[0]['id']+'"]'],'member_limit':['1']},'GET',b'',repo_root=tmp_path)
    page=json.loads(raw)['sections'][0]['members'];assert code==200 and page['limit']==1 and len(page['items'])==1 and (page['total']<=1 or page['next_read']['payload']['member_offset']==1)


def test_outline_rows_are_trimmed_and_the_consumer_rebuilds_the_exact_occurrence_from_owner_templates(tmp_path):
    from test_manuscript_structure import _section_fixture
    from laplace.manuscript import project_structure as structure
    from laplace.manuscript import bindings
    _section_fixture(tmp_path)
    value=structure.read('book',{'view':'outline','limit':80},tmp_path)
    assert value['schema_version']=='laplace.source-outline/2' and value['headings']['items']
    for row in value['headings']['items']:
        assert set(row)==set(bindings.OUTLINE_ROW_FIELDS),sorted(row)
        assert row['file'] in value['sources'] and value['sources'][row['file']]['source_digest'].startswith('sha256:')
    source,tree=bindings.selected_tree('book',tmp_path)
    complete={(r['file'],r['line']):r for r in bindings.outline_rows(source,tree)}
    routes=value['read_routes']
    def fill(template,row):
        text=json.dumps(template).replace('"<file>"',json.dumps(row['file'])).replace('"<line>"',str(row['line'])).replace('"<line_end>"',str(row['line_end']))
        return json.loads(text)
    for row in value['headings']['items']:
        full=complete[(row['file'],row['line'])]
        assert fill(routes['source_read'],row)==full['source_read'] and fill(routes['structure_read'],row)==full['structure_read'],'the templates reproduce the owner handles exactly'
        assert value['sources'][row['file']]['source_digest']==full['basis']['source_digest'] and value['selected_source']['selection_identity']==full['basis']['selection_identity']
    per_row=len(json.dumps(value['headings']['items']).encode())/len(value['headings']['items'])
    assert per_row<400,per_row
    # the state's own source_outline still has the complete rows
    assert 'basis' in structure.state('book',tmp_path)['source_outline'][0]


# ---- C1f / G8: the help owner's areas, journeys and controls, shared by native help, HTTP and the guide ----

def test_help_declarations_are_one_owner_for_native_http_and_the_guide(tmp_path,monkeypatch):
    from laplace.native import declarations as d, tools as writing_tools
    from laplace.web import authoring as authoring_surface
    d.validate_help_declarations()
    (tmp_path/'proj').mkdir();(tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'project','project_dir':'proj'}]}))
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    areas=d.help_areas('p')
    assert areas['schema_version']=='laplace.help-areas/1' and areas['version'].startswith('sha256:')
    encoded=len(json.dumps(areas).encode());assert encoded<32768,encoded   # bounded research-workspace help content ceiling: 28 KiB
    # native help and the HTTP areas door render the same declarations
    native=writing_tools.execute(tmp_path,'p','work','help',{'concept':'journeys'})
    assert native['journeys']==areas['journeys'] and native['requested_concept']=='journeys' and native['version']==areas['version']
    code,_,raw=authoring_surface.handle('/authoring/help',{'project':['p'],'view':['areas']},'GET',b'')
    body=json.loads(raw);assert code==200 and body['inspection']=={'binding':'declarations','turn_id':None,'mode':None} and body['help']==areas
    assert authoring_surface.handle('/authoring/help',{'project':['p'],'view':['areas'],'mode':['work']},'GET',b'')[0]==409,'a declarations read takes no role'
    bare=writing_tools.execute(tmp_path,'p','work','help',{})
    assert bare['workspace_help']['version']==areas['version'] and bare['workspace_help']['http']['query']=={'project':'p','view':'areas'}
    # the fixture the guide tests run against IS this owner's rendering
    fixture=json.loads(Path('tests/fixtures/help/areas.json').read_text())
    assert {k:v for k,v in fixture.items() if k!='project'}=={k:v for k,v in d.help_areas('book').items() if k!='project'}
    # every journey step names a declared control and an observed fact; rendered controls exist in the shell source
    from workspace_source import workspace_source
    shell=workspace_source()   # the shell and its domain controllers (M5 S2 F1)
    controls={row['id']:{**row,'renders_in':d.CONTROL_DECLARATIONS[row['id']]['renders_in']} for row in areas['controls']}
    assert all('renders_in' not in row for row in areas['controls']),'where a control renders is the registry note, not help payload'
    for journey in areas['journeys']:
        for step in journey['steps']:
            assert step['control'] in controls
    # a rendered control's data-control literal lives in the module its declaration names
    # (renders_in starts with that module), the shell by default
    sources={'workspace.mjs':shell}
    for ident,row in controls.items():
        if row['rendered']:
            module=str(row.get('renders_in') or '').split(' ')[0]
            if module.endswith('.mjs') and module not in sources:sources[module]=Path('src/laplace/web/static_shared/'+module).read_text()
            source=sources.get(module,shell)
            assert ('data-control="'+ident+'"' in source) or (ident.startswith('nav:') and "b.dataset.control='nav:'+id" in source) or ("dataset.control='"+ident+"'" in source) or ("'data-control','"+ident+"'" in source) or ("control: '"+ident+"'" in source),ident
    # the hand-authored copy is retired and the shell reads the owner
    guide=Path('src/laplace/web/static_shared/workspace-guide.mjs').read_text()
    assert 'export const GUIDE_STEPS' not in guide and 'journeySteps' in guide and 'journeySteps' in shell and "view:'areas'" in shell


# ---- C7-C9 repair H1/R1-R3: bounded synthetic T=200 pages with qualified linked records ----

def _joined_records(n=200, artifacts_per_turn=6, unicode=False, carrier=None):
    """Two hundred distinct in-memory turns joined to retained artifact records through real
    tool_actions (exact receipts and pins, safe paths): the owner's own link join yields
    `artifacts_per_turn` links per turn. Nothing is banked, copied or read from a real history."""
    turns, records = {}, {}
    for i in range(n):
        tid = f'WT-{i:03}'; acts = []
        for k in range(artifacts_per_turn):
            ident = 'ART-' + f'{i * 1000 + k:032x}'; path = f'development/a{k}.json'; pin = 'a' * 64
            records[('synthetic', ident)] = {'id': ident, 'artifact_path': path, 'path': path, 'scope': 'project', 'sha256': pin, 'turn_id': tid}
            acts.append({'id': f'ACT-{i}-{k}', 'operation': 'store_artifact', 'project': 'synthetic', 'turn_id': tid, 'payload': {'path': path, 'scope': 'project'},
                         'outcome': {'status': 'SUCCEEDED', 'receipts': [ident], 'revisions': {'revision': pin}}})
        turns[tid] = {'id': tid, 'session_id': 'WS-synthetic', 'project': 'synthetic', 'mode': 'work', 'ts': f'{i:03}',
                      'text': 'Useful request ' + (carrier or ('中' if unicode else 'x')) * 5000, 'provider_settings': {'provider': 'claude', 'model': 'm', 'effort': 'low'},
                      'selection': {'files': ['paper/body.tex'], 'line_start': 3, 'line_end': 9, 'quote': 'q' * 3000},
                      'steering': [{'id': f'ST-{i}-{k}', 'text': 's' * 2500, 'ts': 't'} for k in range(4)], 'tool_actions': acts,
                      'reply': {'id': f'WR-{i}', 'status': 'completed', 'text': 'Useful answer ' + (carrier or ('文' if unicode else 'y')) * 7000, 'provider': 'claude', 'model': 'm',
                                'context_tokens_used': 4321, 'context_window_effective': 8000, 'usage': {'input_tokens': 1000 + i, 'output_tokens': 50},
                                'usage_facts_projection': {'schema_version': 'laplace.provider-usage-facts/1', 'selected': {'context_snapshot': {'metric': 'last_request_input_proxy', 'value': 1000 + i}}, 'observations': ['o' * 2000]},
                                'delivery_receipt_projection': {'schema_version': 'laplace.provider-delivery/1', 'blob': 'd' * 1500}}}
    return {'sessions': {'WS-synthetic': {'id': 'WS-synthetic', 'project': 'synthetic', 'role': 'worker', 'provider': 'claude', 'model': 'm', 'effort': 'low', 'packet': 'P-synthetic'}},
            'turns': turns, 'orders': {}, 'actions': {}, 'applications': {}, 'artifact_records': records}


@pytest.mark.parametrize('unicode,carrier', [(False, None), (True, None), (False, '"key": "value", '), (False, 'C:\\path\\ "quoted"\t\n')])
def test_thread_pages_stay_under_the_useful_page_budget_at_t200_with_safe_cursors(monkeypatch, tmp_path, unicode, carrier):
    """R1: every 20-row page of 200 joined turns (six exact artifact links each, 4 steering rows,
    a 3,000-char quote, usage facts and delivery projections; ASCII and CJK carriers) is
    <= 20,000 actual UTF-8 bytes, both as the owner value and as the raw HTTP response; the
    older_cursor chain covers every turn exactly once and ends at None; counts match the
    single-turn summary; the usage meter and its identity travel once per page; no owner
    object is mutated."""
    import copy
    records = _joined_records(unicode=unicode, carrier=carrier); frozen = copy.deepcopy(records); turns = records['turns']
    monkeypatch.setattr(session_reads, '_records', lambda root: records)
    monkeypatch.setattr(session_reads, 'child_execution', lambda *args, **kw: {'state': 'IDLE'})
    monkeypatch.setattr(child_hosts, "child_execution", session_reads.child_execution)   # the owner the family calls directly
    monkeypatch.setattr(checkout, 'repo_root', lambda: tmp_path)
    single_links = lambda ident: session_reads._session_turn_summary(turns[ident], records, bounded=False)['result_links']
    before, seen, pages = '', [], []
    while True:
        page = session_reads.session_state(tmp_path, 'WS-synthetic', before, view='summary', limit=20)
        encoded = len(json.dumps(page, ensure_ascii=False, default=str).encode())
        code, _, raw = authoring_surface.handle('/authoring/session', {'id': ['WS-synthetic'], 'view': ['summary'], 'limit': ['20'], **({'before': [before]} if before else {})}, 'GET', b'')
        assert code == 200 and len(raw) <= 20_000 and encoded <= 20_000, (len(pages), encoded, len(raw))
        pages.append((len(page['turns']), encoded, len(raw)))
        seen.extend(row['id'] for row in page['turns'])
        for row in page['turns']:
            assert 'result_links' not in row and row['result_links_total'] == 6 == len(single_links(row['id'])) and 'result_links_more' not in row and row['body_read']['http']['url'].endswith('view=turn')
            assert row['steering_total'] == 4 and 'steering' not in row and row['steering_truncated'] is True
            assert 'quote' not in row['selection'] and row['selection']['quote_chars'] == 3000 and row['text_chars'] == len(turns[row['id']]['text'])
            # the cap is the serialized form (quotes, backslashes and control characters escaped)
            assert session_projection._serialized_bytes(row['text']) <= session_projection.ROW_TEXT_LIMIT and session_projection._serialized_bytes(row['reply']['display_text']) <= session_projection.ROW_REPLY_LIMIT
            assert turns[row['id']]['text'].startswith(row['text']) and row['text_truncated'] is True
            assert 'delivery_receipt_projection' not in row['reply'] and 'observations' not in json.dumps(row['reply'])
        meters = [row for row in page['turns'] if 'usage' in row['reply']]
        assert len(meters) == 1 and meters[0]['id'] == page['turns'][-1]['id'] == page['usage_meter_turn_id'], 'the usage meter travels once, on the newest row'
        meter = meters[0]['reply']
        assert meter['provider'] == 'claude' and meter['model'] == 'm' and meter['context_tokens_used'] == 4321 and meter['context_window_effective'] == 8000 and meter['usage_facts_projection']['selected']['context_snapshot']['value'] == 1000 + int(meters[0]['id'][3:]), 'the meter keeps its identity and selected counter (R2)'
        assert all('provider' not in row['reply'] for row in page['turns'] if row is not meters[0])
        if not page['older_cursor']: break
        assert page['older_cursor'] == page['turns'][0]['id']
        before = page['older_cursor']
    assert [count for count, _, _ in pages] == [20] * 10 and len(seen) == 200 == len(set(seen)) and sorted(seen) == sorted(turns)
    assert records == frozen, 'row shaping mutated no owner object'
    single = session_reads._session_turn_summary(turns['WT-007'], records, bounded=False)
    assert single['text'] == turns['WT-007']['text'] and single['reply']['delivery_receipt_projection']['blob'] == 'd' * 1500 and len(single['steering']) == 4 and len(single['result_links']) == 6


def test_capped_link_discovery_is_a_lower_bound_and_the_summary_states_its_coverage():
    """R3: thirty qualified artifact actions: the row counts 21 (the discovery cap) as a lower
    bound, the single-turn summary lists 20 with more:true and the same basis; six stay exact."""
    records = _joined_records(n=1, artifacts_per_turn=30); turn = records['turns']['WT-000']
    row = session_reads._session_turn_summary(turn, records, bounded=True)
    assert row['result_links_total'] == 21 and row['result_links_total_basis'] == 'at-least' and row['result_links_more'] is True
    full = session_reads._session_turn_summary(turn, records, bounded=False)
    assert len(full['result_links']) == 20 and full['result_links_more'] is True and full['result_links_total_basis'] == 'at-least' and full['result_links_total'] == 21
    six = _joined_records(n=1, artifacts_per_turn=6)
    row = session_reads._session_turn_summary(six['turns']['WT-000'], six, bounded=True)
    assert row['result_links_total'] == 6 and 'result_links_total_basis' not in row and 'result_links_more' not in row


def test_audit_counts_are_retained_on_rows_rather_than_reported_as_zero():
    """R2: a row keeps the quote length and the draft length it omits the words of."""
    records = _joined_records(n=1); turn = records['turns']['WT-000']
    turn['unsaved_draft'] = {'status': 'UNSAVED', 'format': 'tex', 'text': 'draft' * 1000, 'reason': 'synthetic'}
    row = session_reads._session_turn_summary(turn, records, bounded=True)
    assert row['selection']['quote_chars'] == 3000 and 'quote' not in row['selection']
    assert row['unsaved_draft']['text_chars'] == 5000 and row['unsaved_draft']['text_omitted'] is True and 'text' not in row['unsaved_draft']


def test_row_excerpts_are_capped_in_serialized_bytes_and_never_split_a_character_or_escape():
    """R1-escaped: the serialized form of an excerpt (JSON string body, ensure_ascii=False) never
    exceeds the cap; quotes and backslashes cost two bytes, control characters six, CJK three;
    the clip is a true prefix and the complete character count is kept."""
    clip, size = session_projection._clip_utf8, session_projection._serialized_bytes
    for text in ['"key": "value", ' * 40, 'C:\\path\\ "q"\t\n' * 30, '中文' * 200, 'plain ascii ' * 40, '\x01\x02' * 100]:
        for limit in (1, 7, 16, 120, 160):
            out = clip(text, limit)
            assert text.startswith(out) and size(out) <= limit, (text[:12], limit, size(out))
            assert out == text or size(out + text[len(out)]) > limit, 'the clip is maximal'
            json.loads(json.dumps(out, ensure_ascii=False))   # a complete, valid JSON string
    row = {'text': '"a": "b", ' * 50}
    session_projection._rebound(row, 'text', 30)
    assert size(row['text']) <= 30 and row['text_chars'] == 500 and row['text_truncated'] is True


# ---- C10-C11 (2026-10-14): diagrams and the checklist are help concepts; every control literal in the
# shell modules is declared; the HTTP help door serves one concept per view without a role
def test_help_diagrams_checklist_and_control_literals_are_one_declaration(tmp_path, monkeypatch):
    import re
    from laplace.native import declarations as d, tools as writing_tools
    from laplace.web import authoring as authoring_surface
    (tmp_path/'proj').mkdir();(tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'project','project_dir':'proj'}]}))
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    areas=d.help_areas('p')
    assert areas['reads']['diagrams']['http']['query']=={'project':'p','view':'diagrams'} and set(d.HELP_OWNER_CONCEPTS)=={'areas','journeys','controls','diagrams','checklist'}
    # every area names its diagram's size; the diagrams concept carries the drawable declaration (title, description, nodes, edges, layout)
    assert all(row['diagram'] and row['diagram']['nodes']>=3 for row in areas['areas'])
    diagrams=writing_tools.execute(tmp_path,'p','work','help',{'concept':'diagrams'})['diagrams']
    assert {row['id'] for row in diagrams}=={row['id'] for row in areas['areas']}
    for diagram in diagrams:
        ids={node['id'] for node in diagram['nodes']}
        assert diagram['title'] and diagram['description'] and all(edge['source'] in ids and edge['target'] in ids for edge in diagram['edges'])
        assert set(diagram['layout']['rank'])<=ids
    assert len(json.dumps(diagrams).encode())<16000
    code,_,raw=authoring_surface.handle('/authoring/help',{'project':['p'],'view':['diagrams']},'GET',b'')
    assert code==200 and json.loads(raw)['help']['diagrams']==diagrams
    assert authoring_surface.handle('/authoring/help',{'project':['p'],'view':['diagrams'],'mode':['work']},'GET',b'')[0]==409
    # the acceptance checklist: one row per area, controls per view, journeys and diagram flags, with totals
    checklist=writing_tools.execute(tmp_path,'p','work','help',{'concept':'checklist'})['checklist']
    assert checklist['schema_version']=='laplace.help-checklist/1' and checklist['version']==areas['version']
    rows={row['area']:row for row in checklist['rows']}
    assert rows['work']['journeys']==['why-waiting'] and rows['work']['diagram'] is True and {c['id'] for c in rows['work']['controls']}>={'work:item','work:next-step','work:neighbourhood'}
    assert checklist['totals']['controls']==len(d.CONTROL_DECLARATIONS) and checklist['totals']['journeys']==len(d.JOURNEY_DECLARATIONS)
    code,_,raw=authoring_surface.handle('/authoring/help',{'project':['p'],'view':['checklist']},'GET',b'')
    assert code==200 and json.loads(raw)['help']['checklist']==checklist
    # every data-control literal in the shell modules is a declared control (no undeclared control ever renders)
    declared=set(d.CONTROL_DECLARATIONS)
    literal=re.compile(r"""data-control=\\?"([a-z-]+:[a-z-]+)\\?"|dataset\.control=\s*'([a-z-]+:[a-z-]+)'|'data-control',\s*'([a-z-]+:[a-z-]+)'|\bcontrol:\s*'([a-z-]+:[a-z-]+)'""")
    found={}
    for path in sorted(Path('src/laplace/web/static_shared').glob('*.mjs')):
        for match in literal.finditer(path.read_text()):
            found.setdefault(next(g for g in match.groups() if g),set()).add(path.name)
    undeclared={ident:sorted(files) for ident,files in found.items() if ident not in declared}
    assert not undeclared,undeclared
    # and every rendered declared control has a literal somewhere (the per-module check is the test above)
    missing=[ident for ident,row in d.CONTROL_DECLARATIONS.items() if row['rendered'] and ident not in found and not ident.startswith('nav:')]
    assert not missing,missing
    # the learning record replaces the retired guide key: the modules never write laplace:guide
    for name in ('workspace-guide.mjs','workspace.mjs','workspace-help.mjs'):
        assert "setItem('laplace:guide" not in Path('src/laplace/web/static_shared/'+name).read_text()
    journeys=Path('src/laplace/web/static_shared/workspace-journeys.mjs').read_text()
    assert "removeItem(legacy)" in journeys and "laplace:learning:" in journeys


# ---- repair H6 (2026-10-14): finite per-view states, per-control applicability and source/actual coverage ----
def test_control_states_and_coverage_are_one_declaration_served_by_the_controls_concept(tmp_path, monkeypatch):
    import re
    from laplace.native import declarations as d, tools as writing_tools
    from laplace.web import authoring as authoring_surface
    (tmp_path/'proj').mkdir();(tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'project','project_dir':'proj'}]}))
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    controls=writing_tools.execute(tmp_path,'p','work','help',{'concept':'controls'})
    assert set(controls)>={'controls','view_states','coverage','version'} and controls['version']==d.help_areas('p')['version']
    rows={row['id']:row for row in controls['controls']}
    assert len(rows)==len(d.CONTROL_DECLARATIONS) and all(row['states'] and isinstance(row['dynamic'],bool) for row in rows.values())
    for row in rows.values():
        assert set(row['states'])<=set(controls['view_states'][row['view']]),row['id']
    for view,states in controls['view_states'].items():
        for state in states:
            cover=controls['coverage'][view][state];assert cover['coverage'] in('source','actual') and (cover.get('harness') if cover['coverage']=='source' else cover.get('reason'))
    assert rows['reader-plan:item']['dynamic'] and rows['work:item']['dynamic'] and rows['material:file']['dynamic'] and not rows['help:layer']['dynamic']
    assert rows['manuscript:focus']['view']=='shell' and rows['manuscript:focus']['states']==['manuscript-view'] and rows['output:document']['view']=='presentation'
    # the aggregate areas payload stays within its bounded 32 KiB content ceiling; controls carries the registry; HTTP serves both
    areas=d.help_areas('p');assert all('states' not in row and 'dynamic' not in row for row in areas['controls']) and len(json.dumps(areas).encode())<32768
    code,_,raw=authoring_surface.handle('/authoring/help',{'project':['p'],'view':['controls']},'GET',b'')
    assert code==200 and json.loads(raw)['help']['coverage']==controls['coverage']
    # the fixture the source coverage test runs against IS this rendering
    fixture=json.loads(Path('tests/fixtures/help/controls.json').read_text())
    assert {k:v for k,v in fixture.items() if k!='project'}=={k:v for k,v in d.help_areas('book','controls').items() if k!='project'}
    # the source coverage test mounts exactly the states declared source-covered (its harness keys are read from the file)
    test_source=Path('tests/workspace_control_coverage.test.mjs').read_text()
    source_states={view+'/'+state for view,states in d.STATE_COVERAGE.items() for state,cover in states.items() if cover['coverage']=='source'}
    block=test_source[test_source.index('const HARNESSES={'):test_source.index('};',test_source.index('const HARNESSES={'))]
    harness_keys=set(re.findall(r"'([a-z-]+/[a-z-]+)':",block))
    assert harness_keys==source_states,(harness_keys^source_states)
    totals=d.help_checklist('p')['totals'];assert totals['states']==totals['states_source_covered']+totals['states_actual_only'] and totals['states_source_covered']==len(source_states)


def test_workspace_help_is_projectless_but_turn_and_role_help_keep_project_binding(tmp_path,monkeypatch):
    from laplace.native import declarations as d, tools as writing_tools
    from laplace.web import authoring as surface
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    code,_,raw=surface.handle('/authoring/help',{'view':['areas']},'GET',b'')
    body=json.loads(raw)
    assert code==200 and body['help']==d.help_areas('')
    assert body['inspection']=={'binding':'declarations','turn_id':None,'mode':None}
    assert any(row['id']=='research-workbench' for row in body['help']['areas'])
    for query in ({'mode':['work']},{'turn_id':['WT-not-a-binding']},{'view':['areas'],'mode':['work']},{'view':['areas'],'turn_id':['WT-not-a-binding']}):
        assert surface.handle('/authoring/help',query,'GET',b'')[0]==409
    native=writing_tools.execute(tmp_path,'public','work','help',{'concept':'areas'})
    assert native['version']==body['help']['version'] and native['areas']==body['help']['areas']
    (tmp_path/'help-response-sizes.json').write_text(json.dumps({'canonical_bytes':len(json.dumps(body['help']).encode()),'actual_http_bytes':len(raw),'native_json_bytes':len(json.dumps(native).encode()),'version':native['version']},indent=2))
