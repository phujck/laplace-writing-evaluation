"""Repair2 of the Work navigation packet (WORK-source-state-work-repair-20261019; Sol WI-R5a and WI-R5b).

WI-R5a: the model-facing text of an owner result (writing_sources.content_items, both providers) is UTF-8 JSON and the
navigation page line holds in that actual text domain; the outer RPC framing is measured separately.
WI-R5b: a row that alone exceeds the page line is never returned past it, cut or renamed; its position is covered by an
explicit notice and the page says its coverage is incomplete. Synthetic tmp roots only.
"""
from __future__ import annotations

import json

import pytest

from laplace.work import project_work as work, project_work_navigation as nav
from laplace.web import project_work_surface as http
from laplace.projects import writing_sources
from laplace.native import tools as writing_tools
from laplace.core.records import journal
from laplace.writing import child_hosts

P = 'p'
LINE = 30000


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    (tmp_path / 'contract').mkdir()
    (tmp_path / 'registry_projects.json').write_text(json.dumps({'projects': [{'name': P, 'kind': 'general', 'project_dir': 'proj'}]}))
    (tmp_path / 'proj').mkdir()
    monkeypatch.setattr(child_hosts, 'active_child_hosts', lambda root=None: [])
    journal.bank_row('contract/talk.jsonl', {'record': 'writing-turn', 'id': 'WT-n', 'project': P, 'session_id': 'WS-n', 'mode': 'work', 'text': 'x',
                                            'provider_settings': {'provider': 'codex', 'model': 'fixture'}}, root=tmp_path)
    return tmp_path


def make(root, ident, **fields):
    return work.task(P, {'id': ident, 'title': ident, 'goal': 'Goal of ' + ident, **fields}, root)


def get(root, **query):
    code, _, raw = http.handle('/work/state', {'project': [P], **{k: [str(v)] for k, v in query.items()}}, 'GET', repo_root=root)
    return code, raw, json.loads(raw)


def native(root, **payload):
    return writing_tools.execute(root, P, 'work', 'project', payload, 'WT-n')


# ---------------------------------------------------------------------------------------------- WI-R5a

def test_model_facing_text_is_utf8_json_that_parses_back_exactly_for_both_providers():
    value = {'title': '界' * 3 + ' "quoted" \\ back\\slash', 'control': 'a\nb\tc\x00d\x1f', 'emoji': '🌱', 'nested': {'k': ['é', 1, None]}}
    output = {**value, '_image_content': [{'mime_type': 'image/png', 'data': 'QUJD'}]}
    for provider, text_type, image_type in (('claude', 'text', 'image'), ('codex', 'inputText', 'inputImage')):
        items = writing_sources.content_items(output, provider)
        assert [item['type'] for item in items] == [text_type, image_type], 'the image stays a separate typed block'
        text = items[0]['text']
        assert json.loads(text) == value and '_image_content' not in text
        assert '界界界' in text and '\\u754c' not in text and '🌱' in text, 'Unicode is carried as characters, not escapes'
        assert '\\"quoted\\"' in text and '\\\\ back' in text and '\\n' in text and '\\u0000' in text, 'JSON still escapes what it must'
    assert writing_sources.response_wire_contract()['text_encoding'].startswith('UTF-8 JSON text'), 'the published wire contract says so'
    lone = {'bytes': 'x\udcff'}   # an unpaired surrogate: no UTF-8 text can carry it, so this one result falls back to escapes
    text = writing_sources.content_text(lone)
    assert json.loads(text) == lone and text.encode('utf-8') and '\\udcff' in text


def sol_branch(root):
    """Sol WI-R5a probe: parent P-x180 (title 界x300, goal 意x2000) with 40 children of ~186-character ids, title 作x300."""
    parent = 'P-' + 'x' * 180
    make(root, parent, title='界' * 300, goal='意' * 2000)
    for n in range(40):
        make(root, 'K-%s-%03d' % ('y' * 180, n), title='作' * 300, goal='意' * 2000, parent_work_id=parent)
    return parent


def test_the_page_line_holds_in_the_actual_model_text_and_framing_is_measured_apart(root):
    parent = sol_branch(root)
    code, raw, served = get(root, view='branch', id=parent)
    value = native(root, view='branch', id=parent)
    assert code == 200 and len(raw) < LINE
    for provider in ('claude', 'codex'):
        text = writing_sources.content_items(value, provider)[0]['text']
        assert len(text.encode('utf-8')) < LINE, (provider, len(text.encode('utf-8')))
        assert json.loads(text)['children'] == served['children'] and json.loads(text)['node'] == served['node']
    mcp = json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {'content': writing_sources.content_items(value, 'claude')}})
    codex = json.dumps({'id': 1, 'result': {'success': True, 'contentItems': writing_sources.content_items(value, 'codex')}}, ensure_ascii=False)
    assert len(mcp.encode()) > len(codex.encode()), 'the MCP stdio framing escapes again; that is transport, not model text'


# ---------------------------------------------------------------------------------------------- WI-R5b

def test_an_oversized_first_row_is_an_explicit_notice_never_a_page_past_the_line(root):
    big = 'W-' + 'x' * 20000                                   # Sol WI-R5b witness: about 20 KB of admissible identity
    make(root, big, title='Long existing identity', goal='Keep the exact identity')
    code, raw, page = get(root, view='roots')
    assert code == 200 and len(raw) < LINE, len(raw)
    assert page['roots'] == [] and page['pagination']['complete'] is False and page['pagination']['covered'] == 1
    notice = page['pagination']['oversized'][0]
    assert notice['position'] == 0 and notice['id_bytes'] == len(big) and 'id' not in notice and notice['row_bytes'] > notice['page_line_bytes']
    assert 'view:full' in notice['says'] and notice['id_sha256'].startswith('sha256:')
    assert work._tasks(P, root)[big]['title'] == 'Long existing identity', 'the record is kept exactly as it is'


def test_an_oversized_row_after_normal_rows_and_unicode_identities_keep_whole_row_coverage(root):
    for n in range(5):
        make(root, 'A%02d' % n)
    make(root, '界' * 9000)                                   # a Unicode identity of 27 KB
    for n in range(5, 9):
        make(root, 'A%02d' % n)
    seen, notices, query = [], [], {'view': 'roots'}
    while True:
        code, raw, page = get(root, **query)
        assert code == 200 and len(raw) < LINE, len(raw)
        seen += [row['id'] for row in page['roots']];notices += page['pagination'].get('oversized', [])
        if not page['pagination']['next_read']:
            break
        query = {k: v for k, v in page['pagination']['next_read']['payload'].items() if k != 'namespace'}
    assert seen == ['A%02d' % n for n in range(9)], 'every normal root once, in owner order'
    assert [n['position'] for n in notices] == [5] and notices[0]['id_bytes'] == len(('界' * 9000).encode())


def test_an_oversized_notice_names_an_identity_exactly_when_the_identity_itself_fits():
    short, long = 'M-' + 'z' * 1000, 'M-' + 'z' * 1100
    fits, digest = nav._oversized(P, short, 3, 40000, 28000), nav._oversized(P, long, 4, 40000, 28000)
    assert fits['id'] == short and 'row_reads.detail' in fits['says'] and len(json.dumps(fits).encode()) < 2000
    assert 'id' not in digest and digest['id_bytes'] == len(long) and 'view:full' in digest['says']


def test_a_branch_whose_own_record_cannot_share_a_page_refuses_explicitly(root):
    big = 'B-' + 'x' * 20000
    make(root, big);make(root, 'child', parent_work_id=big)
    code, raw, value = get(root, view='branch', id=big)
    assert code == 422 and 'cannot be delivered within its' in value['error'] and 'view:detail' in value['error'] and len(raw) < LINE
    code, _, detail = get(root, view='detail', id=big)
    assert code == 200 and [row['id'] for row in detail['children']['items']] == ['child'], 'the exact detail read still lists it'


def test_the_original_cjk_witness_and_limit_100_pages_stay_whole_and_complete(root):
    for n in range(12):
        make(root, 'C%d' % n, title='界' * 160, goal='意' * 200)
        make(root, 'C%d-K' % n, title='作' * 160, goal='意' * 200, parent_work_id='C%d' % n)
    code, raw, page = get(root, view='roots')
    assert code == 200 and len(raw) < LINE and [r['id'] for r in page['roots']] == ['C%d' % n for n in range(12)] and 'complete' not in page['pagination']
    parent = sol_branch(root)
    seen, query = [], {'view': 'branch', 'id': parent, 'limit': 100}
    while True:
        code, raw, value = get(root, **query)
        assert code == 200 and len(raw) < LINE
        seen += [row['id'] for row in value['children']]
        if not value['pagination']['next_read']:
            break
        query = {k: v for k, v in value['pagination']['next_read']['payload'].items() if k != 'namespace'}
    assert seen == ['K-%s-%03d' % ('y' * 180, n) for n in range(40)]
