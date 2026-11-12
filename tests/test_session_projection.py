"""THE SESSION THREAD PROJECTION (M5 readability P2, 2026-10-14): the passive conversation read shapes moved
from authoring_surface into laplace.writing.session_projection. Exact output, bounds, caps, no mutation of
owner objects, explicit owner reads, the page's single usage meter, and the facade's identity."""
import copy
import json

import pytest

from laplace.web import authoring as authoring_surface
from laplace.writing import session_reads
from laplace.manuscript import proposal_currentness
from laplace.writing import session_projection as sp


def _reads(calls):
    def record(name, value):
        def read(*args, **kwargs):
            calls.append(name)
            return copy.deepcopy(value) if not callable(value) else value(*args, **kwargs)
        return read
    return sp.TurnReads(
        proposal_view=record('proposal_view', {'proposal': {'answer': 'Use the second derivation.', 'edits': [{'file': 'a.tex'}]}, 'proposal_state': 'PENDING'}),
        failure_rows=record('failure_rows', [{'id': 'f1', 'resolved_later': True, 'recovery_read': {'recovers_read_goal': True}}, {'id': 'f2', 'resolved_later': False, 'related_action': {'action_id': 'A2'}}]),
        failure_view=record('failure_view', lambda turn, records: dict(turn)),
        editor_actions=record('editor_actions', [{'id': 'A1', 'operation': 'block_change', 'outcome': {}}]),
        applications=record('applications', []),
        applied_edits=record('applied_edits', []),
        artifact_result_links=record('artifact_result_links', [{'project': 'p', 'path': 'out/%d.json' % i, 'scope': 'project', 'url': '/x/%d' % i, 'basis': 'b', 'http': {}} for i in range(25)]))


RECORDS = {'sessions': {'S1': {'packet': 'pk-1', 'role': 'author', 'provider': 'codex', 'model': 'm1', 'effort': 'high'}}, 'orders': {}}


def _turn(**extra):
    return {'id': 'T1', 'session_id': 'S1', 'project': 'p', 'mode': 'discuss', 'ts': '2026-10-14T00:00:00Z',
            'text': 'Explain «this» passage. ' * 400, 'workspace_context': {'surface': 'manuscript'},
            'selection': {'files': ['a.tex'], 'line_start': 3, 'line_end': 9, 'quote': '"quoted" \\ text\n' * 300,
                          'anchor': {'file': 'a.tex', 'lines': [3, 9], 'quote': 'passage text is never carried'}, 'unknown': {'deep': 1}},
            'steering': [{'id': 's%d' % i, 'text': 'steer %d ' % i * 200, 'ts': 't'} for i in range(8)],
            'reply': {'id': 'R1', 'text': '中文回答 ' * 2000, 'status': 'completed', 'usage': {'input_tokens': 10}, 'provider': 'codex', 'model': 'm1'},
            'custody_errors': [{'field': 'f', 'content_handle': 'h', 'message': 'storage refused ' * 100, 'extra': 'dropped'}] * 7,
            'queued_work_ids': ['WORK-%d' % i for i in range(30)], **extra}


def test_the_single_turn_summary_keeps_exact_texts_and_names_its_reads():
    calls, source = [], _turn()
    before = copy.deepcopy(source)
    summary = sp.turn_summary(source, RECORDS, reads=_reads(calls))
    assert source == before, 'owner objects are never mutated'
    assert summary['text'] == source['text'] and summary['selection'] == source['selection'], 'a single-turn summary is exact'
    assert summary['reply']['display_text'] == source['reply']['text']
    assert (summary['action_count'], summary['failure_count'], summary['resolved_count'], summary['unresolved_count']) == (1, 2, 1, 1)
    assert (summary['read_recovery_count'], summary['related_action_count']) == (1, 1)
    assert summary['proposal_edit_count'] == 1 and summary['proposal_answer'] == 'Use the second derivation.'
    assert len(summary['result_links']) == 20 and summary['result_links_more'] is True and summary['result_links_total'] == 25
    assert summary['result_links_total_basis'] == 'at-least'
    assert (summary['packet'], summary['role']) == ('pk-1', 'author'), 'the session packet and role travel on the turn'
    assert summary['body_read']['http']['url'] == '/authoring/session-turn?project=p&id=T1&view=turn'
    assert summary['summary_read']['http']['url'] == '/authoring/session-turn?project=p&id=T1&view=summary'
    assert set(calls) == {'proposal_view', 'failure_rows', 'editor_actions', 'applications', 'artifact_result_links'}, 'only the declared owner reads'


def test_a_thread_row_is_bounded_in_serialized_bytes_with_markers_and_capped_collections():
    calls, source = [], _turn()
    row = sp.turn_summary(source, RECORDS, reads=_reads(calls), bounded=True)
    size = lambda value: len(json.dumps(value, ensure_ascii=False).encode()) - 2
    assert size(row['text']) <= sp.ROW_TEXT_LIMIT and row['text_chars'] == len(source['text']) and row['text_truncated'] is True
    reply = row['reply']
    assert size(reply['display_text']) <= sp.ROW_REPLY_LIMIT and reply['display_text_chars'] == len(source['reply']['text'])
    assert 'quote' not in row['selection'] and row['selection']['quote_chars'] == len(source['selection']['quote']), 'a row omits the quote but keeps its length'
    assert 'quote' not in row['selection']['anchor'] and 'unknown' not in row['selection'], 'closed shapes: no passage text, no unknown key'
    assert 'steering' not in row and row['steering_total'] == 8, 'steering rows are counted (an empty list is omitted), read through summary_read'
    assert 'queued_work_ids' not in row and row['queued_work_ids_total'] == 30, 'queued Work is a dropped row field with its total kept'
    assert row['storage_errors_total'] == 7 and len(row['storage_errors']) <= sp.ROW_STORAGE_ERRORS
    assert all(set(error) <= {'field', 'content_handle', 'message', 'message_chars', 'message_truncated'} for error in row['storage_errors'])
    assert not set(row) & set(sp.ROW_DROPPED) - {'result_links'}, 'the row drops what its page already names'
    assert len(json.dumps(row, ensure_ascii=False).encode()) < 4000, 'a row is a glance'


def test_the_session_page_carries_one_usage_meter_and_reads_the_rewire_index_only_for_legacy_receipts():
    calls, rewire = [], []
    turns = [_turn(id='T%d' % i, provider_settings={'provider': 'codex', 'model': 'm1', 'effort': 'high'}) for i in range(3)]
    page, newest = sp.session_page(turns, RECORDS, RECORDS['sessions']['S1'], view='summary', reads=_reads(calls),
                                   continuation=lambda source: source, rewire_index=lambda project: rewire.append(project) or {})
    assert [row['id'] for row in page] == ['T0', 'T1', 'T2'] and newest is page[-1]
    assert 'usage' in page[-1]['reply'] and all('usage' not in row['reply'] for row in page[:-1]), 'one meter, on the newest row'
    assert 'provider_settings' in page[-1] and all('provider_settings' not in row for row in page[:-1]), 'equal settings say so by absence'
    full, newest = sp.session_page([_turn()], RECORDS, RECORDS['sessions']['S1'], view='full', reads=_reads(calls),
                                   continuation=lambda source: source, rewire_index=lambda project: rewire.append(project) or {})
    assert newest is None and full[0]['actions'] and full[0]['reply']['actions'] == full[0]['actions'] and rewire == []
    legacy = _reads(calls)
    legacy = sp.TurnReads(**{**legacy.__dict__, 'editor_actions': lambda turn: [{'id': 'A9', 'operation': 'concept_change', 'outcome': {'identities': ['RW-1', 'def:kept']}}]})
    full, _ = sp.session_page([_turn()], RECORDS, RECORDS['sessions']['S1'], view='full', reads=legacy,
                              continuation=lambda source: source, rewire_index=lambda project: rewire.append(project) or {'RW-1': {'node': 'def:subject'}})
    outcome = full[0]['actions'][0]['outcome']
    assert rewire == ['p'] and outcome['identities'] == ['def:subject', 'def:kept'] and outcome['receipts'] == ['RW-1']
    assert outcome['display_resolution'] == 'canonical rewire subjects'


def test_the_projection_names_live_in_the_projection_and_the_owner_supplies_its_reads():
    for name in ('reply_presentation_text', 'ROW_TEXT_LIMIT', 'SUMMARY_COLLECTIONS', 'SELECTION_EXACT', '_thread_row', '_clip_utf8', '_serialized_bytes', '_bounded_text'):
        assert hasattr(sp, name) and not hasattr(authoring_surface, name), name
    reads = session_reads._turn_reads()
    assert reads.proposal_view is proposal_currentness.proposal_view and reads.failure_rows is session_reads._turn_failure_rows
    assert reads.artifact_result_links is session_reads._artifact_result_links
    with pytest.raises(TypeError):
        sp.turn_summary(_turn(), RECORDS)   # the owner reads are explicit, never implied


@pytest.mark.parametrize('raw,shown,origin', [
    ('{"answer":"Refused: the y-values have mean 3.","edits":[]}', 'Refused: the y-values have mean 3.', 'structured.answer'),
    ('{"answer":"Changed one line.","edits":[{"file":"a.tex","old":"x","new":"y"}]}', 'Changed one line.', 'structured.answer'),
    ('{"edits":[{"file":"a.tex","old":"x","new":"y"}]}', sp.STRUCTURED_EDIT_FALLBACK, 'structured-edit-fallback'),
    ('{"edits":[]}', '', 'structured-empty'),
    ('{"answer":"unterminated","edits":[', '{"answer":"unterminated","edits":[', 'text'),
])
def test_a_structured_reply_shows_its_answer_and_claims_proposed_changes_only_for_a_real_edit(raw, shown, origin):
    calls = []
    source = _turn(reply={'id': 'R1', 'text': raw, 'status': 'completed', 'edits': [], 'proposal': None, 'display_text': None})
    before = copy.deepcopy(source)
    assert sp.reply_presentation(source['reply']) == {'text': shown, 'origin': origin} and origin in sp.PRESENTATION_ORIGINS
    summary = sp.turn_summary(source, RECORDS, reads=_reads(calls))
    assert source == before, 'the saved reply is never rewritten'
    assert summary['reply']['display_text'] == shown
    assert summary['reply']['text'] == (shown if origin in sp.STRUCTURED_ORIGINS else raw), 'raw structured JSON stays at Audit'
    assert (sp.STRUCTURED_EDIT_FALLBACK in summary['reply']['display_text']) == (origin == 'structured-edit-fallback')
    row = sp.turn_summary(source, RECORDS, reads=_reads(calls), bounded=True)
    assert row['reply']['display_text'] == shown and 'text' not in row['reply']


def _serialized(text):
    import json
    return len(json.dumps(text, ensure_ascii=False).encode('utf-8')) - 2


def test_bounds_the_single_turn_summary_keeps_the_full_reply_and_a_row_delivers_a_160_byte_preview():
    calls = []
    full = 'é"\\中' * 1500   # 6000 characters; serialized 2 + 2 (\") + 2 (\\\\) + 3 bytes per four characters
    source = _turn(reply={'id': 'R1', 'text': full, 'status': 'completed'})
    single = sp.turn_summary(source, RECORDS, reads=_reads(calls))['reply']
    assert single['display_text'] == full and len(full) > sp.SUMMARY_REPLY_LIMIT, 'the single-turn summary applies no cut'
    shaped = sp._summary_reply({'display_text': full})   # the intermediate shaping cut, never delivered as such
    assert shaped['display_text'] == full[:sp.SUMMARY_REPLY_LIMIT] and shaped['display_text_chars'] == 6000 and shaped['display_text_truncated']
    row = sp.turn_summary(source, RECORDS, reads=_reads(calls), bounded=True)['reply']
    assert row['display_text'] == full[:71] and _serialized(row['display_text']) == 159 <= sp.ROW_REPLY_LIMIT
    assert _serialized(full[:72]) > sp.ROW_REPLY_LIMIT, 'the next character would exceed the delivered width'
    assert row['display_text_chars'] == 6000 and row['display_text_truncated'] is True and 'text' not in row
    exact = sp.turn_summary(_turn(reply={'id': 'R2', 'text': 'é' * 80, 'status': 'completed'}), RECORDS, reads=_reads(calls), bounded=True)['reply']
    assert exact['display_text'] == 'é' * 80 and _serialized(exact['display_text']) == sp.ROW_REPLY_LIMIT
    assert 'display_text_truncated' not in exact and 'display_text_chars' not in exact


@pytest.mark.parametrize('reply,shown,origin', [
    ({'text': '{"answer":"A","edits":{"file":"a.tex","new":"EDIT BODY"}}'}, '{"answer":"A","edits":{"file":"a.tex","new":"EDIT BODY"}}', 'text'),
    ({'text': 'Proposed: {"answer":"A","edits":[{"file":"a.tex","new":"EDIT BODY"}]}'}, 'Proposed: {"answer":"A","edits":[{"file":"a.tex","new":"EDIT BODY"}]}', 'text'),
    ({'text': '```{"answer":"A","edits":[{"file":"a.tex","new":"EDIT BODY"}]}```'}, '```{"answer":"A","edits":[{"file":"a.tex","new":"EDIT BODY"}]}```', 'text'),
    ({'text': '```json\n{"edits":[{"file":"a.tex","new":"EDIT BODY"}]}\n```'}, sp.STRUCTURED_EDIT_FALLBACK, 'structured-edit-fallback'),
    ({'display_text': None, 'text': 'T'}, 'T', 'text'),
    ({'display_text': 0, 'text': 'T'}, '0', 'display_text'),
    ({'display_text': '', 'text': 'T'}, '', 'display_text'),
    ({'text': 42}, '42', 'text'),
    ({'text': ['a']}, "['a']", 'text'),
    ({'text': 0, 'error': 'E'}, 'E', 'error'),
    ({'error': 7}, '7', 'error'),
    ({'text': '{"edits":[]}', 'error': 'E'}, 'E', 'error'),
])
def test_unrecognised_forms_stay_raw_and_non_string_fields_are_presented_through_str(reply, shown, origin):
    # B3: only a recognised structured reply hides its edit bodies; N1: display_text wins when not None.
    assert sp.reply_presentation(reply) == {'text': shown, 'origin': origin}
    calls = []
    summary = sp.turn_summary(_turn(reply={'id': 'R1', 'status': 'completed', **reply}), RECORDS, reads=_reads(calls))
    assert summary['reply']['display_text'] == shown
    if origin == 'text' and isinstance(reply.get('text'), str):
        assert summary['reply']['text'] == reply['text'], 'unrecognised raw text, edit JSON included, is not replaced'


def test_the_session_read_states_when_it_observed_the_running_turn(monkeypatch, tmp_path):
    """Brief A7 (sessions-display): the owner read that says a conversation is running carries the time of that
    observation, so the conversation list and the navigation never show a running word without its time."""
    import datetime as _dt
    from laplace.writing import session_settings
    session = {"id": "WS-1", "project": "garden-study", "title": "Please note", "provider": "claude", "model": "opus"}
    monkeypatch.setattr(session_reads, "_records", lambda root: {"sessions": {"WS-1": session}, "turns": {}})
    monkeypatch.setattr(session_reads, "_failure_read_cut", lambda records, turns: records)
    monkeypatch.setattr(session_reads.session_projection, "session_page", lambda *a, **k: ([], None))
    monkeypatch.setattr(session_settings, "handle", lambda *a, **k: {})
    monkeypatch.setattr(session_reads, "child_execution", lambda *a, **k: {"state": "NONE"})
    monkeypatch.setitem(session_reads._JOBS, "WT-1", {"id": "WT-1", "session_id": "WS-1", "done": False, "text": "",
                                                      "progress": "agent Message", "events": [], "work_id": "WORK-a"})
    value = session_reads.session_state(tmp_path, "WS-1", view="summary", limit=1)
    active = value["active"]
    assert active["id"] == "WT-1" and active["work_id"] == "WORK-a" and active["capabilities"]["can_interrupt"] is True
    observed = _dt.datetime.fromisoformat(active["observed_at"].replace("Z", "+00:00"))
    assert active["observed_at"].endswith("Z") and abs((_dt.datetime.now(_dt.timezone.utc) - observed).total_seconds()) < 60
    monkeypatch.delitem(session_reads._JOBS, "WT-1")
    monkeypatch.setattr(session_reads, "child_execution", lambda *a, **k: {"state": "RUNNING", "turn_id": "WT-2"})
    hosted = session_reads.session_state(tmp_path, "WS-1", view="summary", limit=1)["active"]
    assert hosted["progress"] == "RUNNING" and hosted["observed_at"].endswith("Z")
    monkeypatch.setattr(session_reads, "child_execution", lambda *a, **k: {"state": "FINISHED"})
    assert session_reads.session_state(tmp_path, "WS-1", view="summary", limit=1)["active"] is None
