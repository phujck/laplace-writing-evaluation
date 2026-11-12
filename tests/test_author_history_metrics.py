from laplace.representation import writing_bodies as bodies
import json
from pathlib import Path

import pytest

from laplace.work import history as author_history, author_history_metrics as metrics
from laplace.web import authoring as authoring_surface
from laplace.native import tools as writing_tools
from laplace.writing import session_reads
from laplace.writing.records import _fold as records_fold
from laplace.core import checkout


def append(root, **row):
    path = root / 'contract/talk.jsonl'; path.parent.mkdir(exist_ok=True)
    with path.open('a') as stream: stream.write(json.dumps(row) + '\n')


def seed(root):
    for project, sid, tid in [('p', 'S-A', 'T-A'), ('p', 'S-B', 'T-B'), ('other', 'S-C', 'T-C')]:
        append(root, record='writing-session', id=sid, project=project, provider='codex',
               model='requested', role='author', ts='2026-10-07T01:00:00Z')
        append(root, record='writing-turn', id=tid, session_id=sid, project=project,
               provider_settings={'provider': 'codex', 'model': 'requested', 'effort': 'low'},
               mode='work', text='PRIVATE PROMPT CONTENT', ts='2026-10-07T01:00:01Z')
        append(root, record='writing-tool-read', id='READ-' + tid, project=project,
               turn_id=tid, operation='source', ts='2026-10-07T01:00:02Z')
        append(root, record='writing-tool-read-baseline', id='BASE-' + tid, project=project,
               turn_id=tid, operation='source', ts='2026-10-07T01:00:03Z')
        append(root, record='writing-reply', id='R-' + tid, project=project, session_id=sid,
               turn_id=tid, resolved_model='actual', status='completed',
               text='PRIVATE REPLY CONTENT', usage={'provider': 'codex', 'input': 99},
               context_tokens_used=99, ts='2026-10-07T01:00:04Z')


@pytest.fixture(autouse=True)
def clean():
    metrics._INDEXES.clear()
    yield
    metrics._INDEXES.clear()


def query(root, **fields):
    return author_history.telemetry('p', {'view': 'telemetry', 'projection': 'sessions', **fields}, root)


def test_catalogue_latest_admission_is_separate_from_last_reply_and_respects_cut_order(tmp_path):
    seed(tmp_path)
    previous=query(tmp_path,scope='session',session_id='S-A')
    append(tmp_path,record='writing-turn',id='T-literature',session_id='S-A',project='p',work_id='WORK-literature',
           mode='work',provider_settings={'provider':'codex','model':'new-model','effort':'high'},ts='2026-10-06T00:00:00Z')
    current=query(tmp_path,scope='session',session_id='S-A');row=current['items'][0]
    assert row['latest_turn_id']=='T-literature' and row['work_id']=='WORK-literature'
    assert row['admitted_settings']['model']=='new-model' and row['latest_admission_has_reply'] is False
    assert row['saved_terminal_kind']=='completed' and row['latest_reply_target']['turn_id']=='T-A'
    append(tmp_path,record='writing-turn',id='T-future',session_id='S-A',project='p',work_id='WORK-future',ts='2026-10-05T00:00:00Z')
    metrics._INDEXES.clear()
    held=query(tmp_path,scope='session',session_id='S-A',as_of=current['as_of'])['items'][0]
    assert held['latest_turn_id']=='T-literature' and held['work_id']=='WORK-literature'
    old=query(tmp_path,scope='session',session_id='S-A',as_of=previous['as_of'])['items'][0]
    assert old['latest_turn_id']=='T-A' and old['latest_admission_has_reply'] is True


def test_catalogue_session_filter_trace_and_original_attempts_no_bodies(tmp_path, monkeypatch):
    seed(tmp_path)
    monkeypatch.setattr(bodies, 'resolve_fields', lambda *a, **k: pytest.fail('body read'))
    monkeypatch.setattr(session_reads, '_records', lambda *a, **k: pytest.fail('rich history cache'))
    data = query(tmp_path, scope='session', session_id='S-A')
    assert [row['session_id'] for row in data['items']] == ['S-A']
    row = data['items'][0]
    assert row['admitted_settings']['model'] == 'requested' and row['resolved_models'] == ['actual']
    assert row['original_tool_attempts']['writing-tool-read'] == 1
    assert row['saved_terminal_kind'] == 'completed' and row['live_state'] == 'UNKNOWN'
    assert 'PRIVATE REPLY CONTENT' not in json.dumps(data)
    assert row['title'] == records_fold._session_display_title('PRIVATE PROMPT CONTENT')
    assert row['title_basis'] == 'existing-owner-catalogue-label'
    trace = metrics.read('p', {'projection': 'trace', 'scope': 'turn', 'turn_id': 'T-A'}, tmp_path)
    assert {r['record'] for r in trace['items']} == {'writing-turn', 'writing-tool-read', 'writing-reply'}
    assert 'PRIVATE' not in json.dumps(trace)


def test_cursor_holds_cut_after_append_other_project_and_own_new_events(tmp_path):
    seed(tmp_path)
    first = query(tmp_path, limit=1)
    append(tmp_path, record='writing-turn', id='T-new', project='other', session_id='S-C')
    read = first['pagination']['next_read']['payload']
    second = author_history.telemetry('p', read, tmp_path)
    assert second['read_cut'] == first['read_cut']
    assert first['items'][0]['id'] != second['items'][0]['id']
    append(tmp_path, record='writing-tool-failure', id='F-new', project='p', turn_id='T-A', error='PRIVATE ERROR')
    again = author_history.telemetry('p', read, tmp_path)
    assert again['read_cut'] == first['read_cut']
    fresh = query(tmp_path)
    assert fresh['read_cut']['revision'] != first['read_cut']['revision']
    assert fresh['coverage']['original_tool_attempts'] == 3


def test_incremental_append_new_turn_and_same_size_rewrite_invalidation(tmp_path):
    seed(tmp_path); query(tmp_path); idx = metrics.index(tmp_path)
    old = dict(idx.stats); query(tmp_path)
    assert idx.stats['bytes_read'] == old['bytes_read']
    append(tmp_path, record='writing-turn', id='T-new', project='p', session_id='S-A', text='PRIVATE')
    query(tmp_path)
    assert idx.stats['scans'] == old['scans'] and idx.stats['suffix_reads'] == old['suffix_reads'] + 1
    assert idx.stats['bytes_read'] - old['bytes_read'] < 1000
    before = query(tmp_path, limit=1)
    path = tmp_path / 'contract/talk.jsonl'
    raw = path.read_text(); path.write_text(raw.replace('requested', 'different'))
    with pytest.raises(ValueError, match='history changed'):
        author_history.telemetry('p', before['pagination']['next_read']['payload'], tmp_path)
    assert idx.stats['scans'] == old['scans'] + 1


def test_native_http_same_metadata_contract_and_cache_cannot_be_poisoned(tmp_path, monkeypatch):
    seed(tmp_path)
    payload = {'view': 'telemetry', 'projection': 'sessions', 'scope': 'session', 'session_id': 'S-A'}
    native = writing_tools.call(tmp_path, 'p', 'work', {'operation': 'author_history', 'payload': payload})
    monkeypatch.setattr(checkout, 'repo_root', lambda: tmp_path)
    status, _, body = authoring_surface.handle('/authoring/history',
        {'project': ['p'], **{k: [v] for k, v in payload.items()}}, 'GET', b'')
    assert status == 200 and json.loads(body) == native
    native['items'][0]['admitted_settings']['model'] = 'POISON'
    assert query(tmp_path, scope='session', session_id='S-A')['items'][0]['admitted_settings']['model'] == 'requested'


def test_legacy_usage_session_filter_does_not_mix_conversations(tmp_path):
    rows = [{'record': 'writing-turn', 'id': 'A', 'session_id': 'S-A', 'project': 'p'},
            {'record': 'writing-turn', 'id': 'B', 'session_id': 'S-B', 'project': 'p'},
            {'record': 'writing-reply', 'turn_id': 'A', 'usage': {}, 'context_tokens_used': 10},
            {'record': 'writing-reply', 'turn_id': 'B', 'usage': {}, 'context_tokens_used': 20}]
    value = author_history._telemetry_usage('p', tmp_path, scope={'session_id': 'S-A'}, as_of=None, talk_rows=rows)
    assert value['records'] == 1 and value['by_provider_model'][0]['latest_context_tokens_used'] == 10


def test_duplicate_original_rows_are_not_calls_and_exact_catalogue_drilldown_exists(tmp_path):
    seed(tmp_path)
    path = tmp_path / 'contract/talk.jsonl'
    line = next(line for line in path.read_text().splitlines(True) if 'READ-T-A' in line)
    with path.open('a') as stream: stream.write(line)
    value = query(tmp_path, scope='session', session_id='S-A')
    assert value['items'][0]['original_tool_attempts']['writing-tool-read'] == 1
    assert value['coverage']['duplicate_original_rows'] == 1
    trace = metrics.read('p', {'projection': 'trace', 'scope': 'session', 'session_id': 'S-A'}, tmp_path)
    created = next(row for row in trace['items'] if row['record'] == 'writing-session')
    result = author_history.record('p', created['read_handle']['payload']['id'], tmp_path)
    assert result['record']['id'] == 'S-A'


def test_work_contains_descendants_not_prerequisites_and_shared_turns_unallocated(tmp_path):
    seed(tmp_path)
    work = tmp_path / 'corpus_friction/work_orders.jsonl'; work.parent.mkdir()
    work.write_text(''.join(json.dumps(row)+'\n' for row in [
        {'record':'project-work','id':'P','project':'p','depends_on':['PREREQ']},
        {'record':'project-work','id':'C','project':'p','parent_work_id':'P','logical_target':{'node_id':'claim'}},
        {'record':'project-work','id':'PREREQ','project':'p'}]))
    append(tmp_path, record='writing-turn', id='TC', session_id='S-A', project='p', work_id='C', parent_turn_id='T-A')
    append(tmp_path, record='writing-tool-failure', id='FC', turn_id='TC', project='p', error='PRIVATE ERROR')
    append(tmp_path, record='writing-turn', id='TP', session_id='S-B', project='p', work_id='PREREQ')
    data = metrics.read('p', {'projection':'overview','scope':'work','work_id':'P'}, tmp_path)
    assert data['work_scope']['included_work_ids'] == ['C','P']
    assert data['totals']['logical_turns'] == 1 and data['totals']['retained_tool_failures'] == 1
    child = data['nesting']['turns'][0]
    assert child['turn_id'] == 'TC' and child['parent_turn_id'] == 'T-A'
    assert child['conceptric_mapping']['logical_target'] == {'node_id':'claim'}
    all_data = metrics.read('p', {'projection':'overview'}, tmp_path)
    assert 'T-A' in all_data['nesting']['unallocated_turn_ids']


def test_exact_response_feedback_neutral_context_and_beforewrite_refusal(tmp_path, monkeypatch):
    from laplace.pipeline import authoring
    from laplace.work import feedback as author_feedback
    from test_authoring_core import _fixture
    _fixture(tmp_path, monkeypatch); seed(tmp_path)
    target = {'schema_version':author_feedback.TARGET_SCHEMA,'kind':'response','project':'p',
              'session_id':'S-A','turn_id':'T-A','reply_record_id':'R-T-A',
              'response_sha256': __import__('hashlib').sha256(b'PRIVATE REPLY CONTENT').hexdigest()}
    before = list(tmp_path.rglob('feedback.jsonl'))
    for bad in ({**target,'project':'other'}, {**target,'response_sha256':'0'*64},
                {**target,'schema_version':'laplace.feedback-target/99'}, {**target,'turn_id':'T-B'}):
        with pytest.raises(ValueError):
            authoring.bank_correction('p', {'text':'PRIVATE COMMENT','kind':'note','scope':'project',
                                          'feedback_target':bad}, tmp_path)
        assert list(tmp_path.rglob('feedback.jsonl')) == before
    saved = authoring.bank_correction('p', {'text':'PRIVATE COMMENT','kind':'note','scope':'project',
                                         'feedback_target':target}, tmp_path)['correction']
    assert saved['feedback_effect'] == 'observation_only'
    assert not authoring._correction_can_constrain(saved)
    reply=authoring.bank_correction('p', {'text':'Neutral discussion reply','kind':'note','scope':'project','reply_to':saved['id']},tmp_path)['correction']
    assert reply['feedback_effect']=='observation_only' and not authoring._correction_can_constrain(reply)
    state = authoring._with_feedback({'corrections':[]}, tmp_path/'manuscript/feedback/feedback.jsonl')
    assert not authoring._correction_can_constrain(state['corrections'][0])
    result = metrics.read('p', {'projection':'feedback','scope':'session','session_id':'S-A'}, tmp_path)
    assert len(result['items']) == 2 and 'PRIVATE COMMENT' not in json.dumps(result)
    row = next(item for item in result['items'] if item['lineage']['correction_id']==saved['id']); assert row['target_basis'] == 'validated-exact-response'
    assert row['lineage']['correction_id'] == saved['id']
    exact = author_history.record('p', row['read_handle']['payload']['id'], tmp_path)
    assert exact['text'] == 'PRIVATE COMMENT'
    assert metrics.read('p', {'projection':'feedback','scope':'session','session_id':'S-B'}, tmp_path)['items'] == []
    explicit = authoring.bank_correction('p', {'text':'Explicit instruction','kind':'request','scope':'project',
        'feedback_target':target,'feedback_effect':'instruction'}, tmp_path)['correction']
    assert authoring._correction_can_constrain(explicit)
    assert not authoring._correction_can_constrain({**explicit,'feedback_target':{**target,'schema_version':'laplace.feedback-target/99'}})
    with pytest.raises(ValueError, match='retire an instruction'):
        authoring.bank_correction('p', {'text':'Observe','kind':'note','scope':'project',
            'feedback_target':target,'supersedes':explicit['id']}, tmp_path)


def test_usage_domains_unknowns_duplicate_terminal_and_original_admission(tmp_path, monkeypatch):
    from laplace.writing import provider, operating
    seed(tmp_path)
    facts = provider._UsageFacts('claude', tmp_path, 'T-A', 'requested'); facts.bind('native')
    facts.claude_terminal({'usage': {'input_tokens':2,'cache_read_input_tokens':3,
        'cache_creation_input_tokens':0,'output_tokens':7}, 'total_cost_usd':.04,
        'modelUsage': {'actual': {'inputTokens':40,'outputTokens':12,'costUSD':.03,'costBasis':'list'}}})
    append(tmp_path, record='writing-reply',id='R-new',project='p',session_id='S-A',turn_id='T-A',
           status='completed',resolved_model='actual',text='reply',usage_facts_projection=operating.usage_facts_projection(facts.snapshot()))
    # Exact duplicate receipt must not charge a selected attempt twice.
    raw = (tmp_path/'contract/talk.jsonl').read_text().splitlines(True)[-1]
    with (tmp_path/'contract/talk.jsonl').open('a') as stream: stream.write(raw)
    append(tmp_path, record='writing-turn-context-baseline',id='CTX-NEW',project='p',turn_id='T-A',context_id='later')
    monkeypatch.setattr(bodies, 'resolve_fields', lambda *a, **k: pytest.fail('aggregate body read'))
    data = metrics.read('p', {'projection':'usage','scope':'session','session_id':'S-A'}, tmp_path)
    assert len(data['items']) == 2 # legacy attempt stays unknown separately
    known = next(row for row in data['items'] if row['status'] == 'RECORDED')
    assert known['duplicate_reply_receipts'] == 1
    summary = data['accounting']; assert summary['unknown_logical_turn_attempts'] == 1
    assert summary['by_compatible_reported_basis'][0]['reported_counts']['total'] == 12
    assert summary['by_compatible_reported_basis'][0]['reported_counts']['reasoning_output'] is None
    assert summary['billed_cost'] is None and summary['cost_estimate_total'] is None
    assert known['selected']['unselected_variants'][0]['reported_cost_estimate']['invoice'] is False
    future = {**operating.usage_facts_projection(facts.snapshot()),'schema_version':'laplace.provider-usage-facts/99'}
    append(tmp_path,record='writing-reply',id='FUTURE',project='p',turn_id='T-A',usage_facts_projection=future)
    fresh = metrics.read('p', {'projection':'usage','scope':'session','session_id':'S-A'}, tmp_path)
    assert any(row['status']=='UNAVAILABLE' for row in fresh['items'])
    monkeypatch.undo()
    admission = author_history.record('p','activity:admission:T-A',tmp_path)
    assert admission['record']['id'] == 'T-A' and admission['record'].get('context_id') != 'later'


def test_cut_uses_original_session_and_turn_metadata_and_inodes(tmp_path):
    seed(tmp_path); first = query(tmp_path,limit=1)
    append(tmp_path,record='writing-turn',id='T-future',project='p',session_id='S-A',
           text='Future title',provider_settings={'model':'future'})
    page = author_history.telemetry('p', first['pagination']['next_read']['payload'], tmp_path)
    assert page['items'][0]['admitted_settings']['model'] == 'requested'
    path = tmp_path/'contract/talk.jsonl'; replacement=tmp_path/'replacement'
    replacement.write_text(path.read_text().replace('requested','changed'))
    replacement.replace(path)
    with pytest.raises(ValueError,match='history changed'):
        author_history.telemetry('p',first['pagination']['next_read']['payload'],tmp_path)
    path.write_text('')
    assert query(tmp_path)['items'] == []


def test_delivery_missing_future_and_exact_lazy_basis_and_model_filters(tmp_path, monkeypatch):
    from laplace.writing import operating as wo
    from test_writing_operating import _project
    _project(tmp_path); brief=wo.build('book','review',tmp_path)
    append(tmp_path,record='writing-session',id='S',project='book')
    append(tmp_path,record='writing-turn',id='T',session_id='S',project='book',context_id='original',
        provider_settings={'provider':'codex','model':'requested'},dependencies={'source_basis':'exact'})
    append(tmp_path,record='writing-tool-read',id='READ',project='book',turn_id='T',operation='source')
    receipt=wo.delivery_receipt(brief,'codex','PRIVATE TASK')
    append(tmp_path,record='writing-reply',id='R',project='book',turn_id='T',resolved_model='actual',status='completed',
        delivery_receipt_projection=wo.delivery_receipt_projection(receipt))
    append(tmp_path,record='writing-reply',id='OLD',project='book',turn_id='T')
    data=metrics.read('book',{'projection':'delivery'},tmp_path)
    assert [x['status'] for x in data['items']]==['RECORDED','UNAVAILABLE']
    assert 'PRIVATE TASK' not in json.dumps(data)
    known=data['items'][0];assert known['receipt']['native_inventory']['state']=='UNOBSERVABLE'
    basis=author_history.record('book',known['admission_read']['payload']['id'],tmp_path)
    assert basis['record']['context_id']=='original' and basis['record']['dependencies']=={'source_basis':'exact'}
    trace=metrics.read('book',{'projection':'trace','resolved_model':'actual'},tmp_path)
    assert 'READ' in {row['event_id'] for row in trace['items']}
    assert metrics.read('book',{'projection':'trace','admitted_model':'actual'},tmp_path)['items']==[]
    future={**wo.delivery_receipt_projection(receipt),'schema_version':'laplace.provider-delivery/99'}
    append(tmp_path,record='writing-reply',id='F',project='book',turn_id='T',delivery_receipt_projection=future)
    result=metrics.read('book',{'projection':'delivery'},tmp_path)
    assert result['items'][-1]['status']=='UNAVAILABLE'


def test_missing_journal_not_stale_and_partial_line_append(tmp_path):
    seed(tmp_path); first=query(tmp_path)
    path=tmp_path/'contract/talk.jsonl'; raw=json.dumps({'record':'writing-turn','id':'PARTIAL','project':'p','session_id':'S-A'})
    with path.open('a') as stream:stream.write(raw[:30])
    before=metrics.index(tmp_path).stats['scans']
    assert query(tmp_path)['items'][0]['turn_count']==1
    with path.open('a') as stream:stream.write(raw[30:]+'\n')
    assert metrics.index(tmp_path).stats['scans']==before
    assert any(row['turn_count']==2 for row in query(tmp_path)['items'])
    path.unlink()
    missing=query(tmp_path)
    assert missing['items']==[] and missing['status']=='PARTIAL'
    assert missing['coverage']['talk_source_status']=='MISSING'


def test_recent_sessions_order_pinned_pages_and_undated_activity_fallback(tmp_path):
    seed(tmp_path)
    append(tmp_path,record='writing-tool-read',id='LATEST-A',project='p',turn_id='T-A',ts='2026-10-08T00:00:00Z')
    first=query(tmp_path,limit=1);assert first['items'][0]['id']=='S-A'
    append(tmp_path,record='writing-tool-read',id='NEWEST-B',project='p',turn_id='T-B',ts='2026-10-09T00:00:00Z')
    page=author_history.telemetry('p',first['pagination']['next_read']['payload'],tmp_path)
    assert page['items'][0]['id']=='S-B' and page['items'][0]['latest_recorded_at']=='2026-10-07T01:00:04Z'
    assert query(tmp_path)['items'][0]['id']=='S-B'
    append(tmp_path,record='writing-tool-read',id='UNDATED-B',project='p',turn_id='T-B')
    assert query(tmp_path)['items'][0]['latest_recorded_at']=='2026-10-09T00:00:00Z'


def test_many_owner_metadata_paths_do_not_evict_hot_journal(tmp_path):
    seed(tmp_path);query(tmp_path);hot=metrics.index(tmp_path);before=dict(hot.stats)
    for number in range(24):
        metrics.index(tmp_path, 'missing-project-'+str(number)+'/feedback/feedback.jsonl', metrics._feedback_metadata)
    assert metrics.index(tmp_path) is hot and hot.stats['bytes_read']==before['bytes_read']


def test_usage_projection_retains_native_baseline_alias_coverage_without_actual_model_guess(tmp_path):
    from laplace.writing import provider as wp, operating as wo
    seed(tmp_path)
    facts=wp._UsageFacts('codex',tmp_path,'T-A','requested');facts.bind('native',fresh=True);facts.bind('native','turn')
    facts.native={'state':'observed_bytecut','start':123,'end':456,'omitted_before':99,'trace_coverage':'partial'}
    facts.model('requested','thread_response_model') # Alias observation, not actual inference model.
    facts.codex({'last':{'inputTokens':5,'cachedInputTokens':1,'cacheWriteInputTokens':0,'outputTokens':3,'totalTokens':8}})
    facts.codex({'total':{'inputTokens':10,'cachedInputTokens':3,'cacheWriteInputTokens':0,'outputTokens':7,'totalTokens':17}})
    append(tmp_path,record='writing-reply',id='NEW',project='p',turn_id='T-A',resolved_model='requested',
           usage_facts_projection=wo.usage_facts_projection(facts.snapshot()))
    value=metrics.read('p',{'projection':'usage','scope':'session','session_id':'S-A'},tmp_path)
    row=next(item for item in value['items'] if item['status']=='RECORDED')
    assert row['coverage']['native_metadata']['trace_coverage']=='partial'
    assert row['coverage']['native_metadata']['omitted_before']==99
    assert row['baseline']['value']['input']==0
    assert row['model_observations'][0]['resolved_alias']=='requested'
    assert row['reported_actual_models']==[]
    assert row['selected']['context_snapshot']['metric']=='last_request_input_proxy'
    assert row['selected']['context_snapshot']['exact_post_compaction_occupancy']=='UNOBSERVABLE'
    assert row['selected']['logical_turn']['derivation']=='new thread/start zero baseline; no prior turns'
    summary=value['accounting']['by_compatible_reported_basis'][0]
    assert summary['actual_reported_model'] is None and summary['model_basis']=='UNAVAILABLE-or-multiple-models'


def test_artifact_metadata_lookup_never_hydrates_rich_journal_and_refuses_namespace_ambiguity(tmp_path, monkeypatch):
    append(tmp_path,record='writing-artifact',id='ART-one',project='p',artifact_path='safe.txt',scope='project',sha256='a'*64)
    append(tmp_path,record='writing-artifact',id='ART-one',project='other',artifact_path='other.txt',scope='project',sha256='b'*64)
    monkeypatch.setattr(session_reads,'_records',lambda *a, **k:pytest.fail('rich journal hydration'))
    assert session_reads.artifact_record(tmp_path,'p','ART-one')['artifact_path']=='safe.txt'
    assert session_reads.artifact_record(tmp_path,'unknown','ART-one') is None
    append(tmp_path,record='writing-artifact',id='ART-one',project='p',artifact_path='wrong.txt',scope='project',sha256='c'*64)
    with pytest.raises(ValueError,match='ambiguous'):session_reads.artifact_record(tmp_path,'p','ART-one')


def test_feedback_alias_null_conflict_and_future_anchor_refuse_before_all_owner_writes(tmp_path,monkeypatch):
    from laplace.work import feedback as author_feedback
    from laplace.manuscript import manuscript_bridge
    from laplace.pipeline import authoring
    from test_authoring_core import _fixture
    _fixture(tmp_path,monkeypatch);seed(tmp_path)
    target={'schema_version':author_feedback.TARGET_SCHEMA,'kind':'response','project':'p','session_id':'S-A',
        'turn_id':'T-A','reply_record_id':'R-T-A','response_sha256':__import__('hashlib').sha256(b'PRIVATE REPLY CONTENT').hexdigest()}
    anchor={'feedback_target':target,'feedback_effect':'observation_only'}
    base={'text':'Observe','kind':'note','scope':'project'}
    variants=[{'feedback_target':None,'feedback_effect':None,'anchor':anchor},
              {'feedback_target':None,'anchor':{**anchor,'feedback_target':{**target,'schema_version':'laplace.feedback-target/99'}}},
              {'feedback_target':target,'feedback_effect':'instruction','anchor':anchor},
              {'feedback_target':{**target,'turn_id':'T-B'},'anchor':anchor},
              {'anchor':{'feedback_target':{**target,'schema_version':'laplace.feedback-target/99'},'feedback_effect':'observation_only'}}]
    state=tmp_path/'manuscript/authoring.json';ledger=tmp_path/'manuscript/feedback/feedback.jsonl'
    before={str(path):path.read_bytes() for path in (state,ledger) if path.exists()}
    for variant in variants:
        with pytest.raises(ValueError):authoring.bank_correction('p',{**base,**variant},tmp_path)
        result=manuscript_bridge.feedback_add(tmp_path,'p',{'node_id':'fixture','comment':'Observe',**variant},ledger=ledger)
        assert result.get('error')
        assert {str(path):path.read_bytes() for path in (state,ledger) if path.exists()}==before
    saved=authoring.bank_correction('p',{**base,'anchor':anchor},tmp_path)['correction']
    assert saved['feedback_effect']=='observation_only' and saved['context_role']=='observation-only'
    assert not authoring._correction_can_constrain(saved)
    matching=authoring.bank_correction('p',{**base,'anchor':anchor,'feedback_target':target,'feedback_effect':'observation_only'},tmp_path)['correction']
    assert matching['feedback_effect']=='observation_only'


@pytest.mark.parametrize('query',[{'provider':0},{'session_id':False},{'role':None},{'scope':[]},
    {'from':'nan'},{'from':'inf'},{'from':'-inf'},{'from':'1e999'},{'from':123}])
def test_declared_query_types_and_finite_times_refuse_without_scanning(tmp_path,query,monkeypatch):
    monkeypatch.setattr(metrics,'index',lambda *a,**k:pytest.fail('invalid query reached owner I/O'))
    with pytest.raises(ValueError):metrics.read('p',{'projection':'trace',**query},tmp_path)


def test_both_cursor_and_cut_are_bound_to_same_scope_and_revision(tmp_path):
    seed(tmp_path)
    own=metrics.read('p',{'projection':'trace','limit':1},tmp_path)
    foreign=metrics.read('other',{'projection':'trace','limit':1},tmp_path)
    with pytest.raises(ValueError,match='another scope'):
        metrics.read('p',{'projection':'trace','limit':1,'as_of':own['as_of'],
            'cursor':foreign['pagination']['next_read']['payload']['cursor']},tmp_path)
    append(tmp_path,record='writing-tool-read',id='NEW',project='p',turn_id='T-A')
    later=metrics.read('p',{'projection':'trace','limit':1},tmp_path)
    with pytest.raises(ValueError,match='same owner cut'):
        metrics.read('p',{'projection':'trace','limit':1,'as_of':own['as_of'],
            'cursor':later['pagination']['next_read']['payload']['cursor']},tmp_path)
    valid=metrics.read('p',{'projection':'trace','limit':1,'as_of':own['as_of'],
        'cursor':own['pagination']['next_read']['payload']['cursor']},tmp_path)
    assert valid['pagination']['offset']==1 and valid['as_of']==own['as_of']
