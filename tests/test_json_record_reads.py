"""CAMPAIGN BOUNDED SOURCE READING (2026-10-14): one JSON value by RFC 6901 pointer through the existing
repository, material and artifact readers, pinned to the source bytes; and truthful logical-plan
availability for a registered source-optional project. Disposable synthetic owners only."""
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from laplace.research import concepts as concepts_surface
from laplace.projects import library as wp, writing_sources
from laplace.native import tools as writing_tools
from laplace.core import json_record
from laplace.projects import artifacts

RECORD = {'id': 1273, 'query': 'Which city hosts the “Ζ” event? 中文 🌱', 'evidence': [{'title': 'a/b ~ c', 'fact': 'quoted "x"\nnext'}] * 3,
          'score': 0.50, 'big': 1e400}
SOURCE_TEXT = ('[' + ','.join(json.dumps({'id': i, 'body': 'filler ' * 40}) for i in range(1273)) + ',' +
               '{"id": 1273, "query": "Which city hosts the \\u201c\\u0396\\u201d event? 中文 🌱", "evidence": ' +
               json.dumps(RECORD['evidence'], ensure_ascii=False) + ', "score": 0.50, "big": 1e400, "a/b": {"~k": [10, 20]}}]')


def _shared(tmp_path, text=SOURCE_TEXT, name='dataset.json'):
    """A general project and a declared shared repository holding one JSON source."""
    assert wp.create({'name': 'campaign', 'title': 'Campaign', 'kind': 'general'}, tmp_path)[0] == 201
    (tmp_path / 'profiles').mkdir(exist_ok=True)
    (tmp_path / 'external').mkdir(exist_ok=True)
    (tmp_path / 'external' / name).write_text(text, encoding='utf-8')
    (tmp_path / 'profiles' / 'writing_sources.json').write_text(json.dumps({'repositories': {'shared': 'external'}}))
    return {'owner': 'repository', 'repository': 'shared', 'path': name}


def _attach(tmp_path, target):
    preview = wp.material_references('campaign', tmp_path, view='preview', target=target)
    changed = wp.change_material_reference('campaign', {'action': 'attach', 'target': target,
        'expected_revision': preview['revision'], 'consumed_revision': preview['current_revision']}, tmp_path)
    return changed['reference']['id']


def _http(root, url):
    parts = urlsplit(url)
    code, _, raw = wp.handle(parts.path, parse_qs(parts.query, keep_blank_values=True), 'GET', b'', repo_root=root)
    return code, json.loads(raw)


# --- the selection rules -------------------------------------------------------------------------
def test_pointer_selection_follows_rfc6901_with_exact_unicode_escaped_keys_and_array_semantics():
    raw = SOURCE_TEXT.encode()
    pin = hashlib.sha256(raw).hexdigest()
    value = json_record.page(raw, pin, {'pointer': '/1273'})
    record = json.loads(value['content'].replace('1e400', '1'))   # the serialization is JSON (1e400 kept as spelled)
    assert record['query'] == RECORD['query'] and record['evidence'] == RECORD['evidence']
    assert '"score": 0.50' in value['content'] and '"big": 1e400' in value['content'], 'original number spellings'
    assert '中文 🌱' in value['content'] and '\\u' not in value['content'], 'ensure_ascii off'
    assert value['json_record']['type'] == 'object' and value['json_record']['members'] == 6 and value['json_record']['tokens'] == ['1273']
    assert value['json_record']['source_sha256'] == 'sha256:' + pin and value['json_record']['parse']['source_bytes'] == len(raw)
    assert json_record.page(raw, pin, {'pointer': '/1273/a~1b/~0k/1'})['content'] == '20', '~1 is "/" and ~0 is "~"'
    assert json_record.page(raw, pin, {'pointer': '/1273/evidence/0/title'})['content'] == '"a/b ~ c"'
    refusals = {'/1274': 'has 1274 elements', '/01': 'not an array index', '/-': 'past the end' if False else 'selects no value',
                '/1273/nope': 'has no key "nope"', '/1273/query/0': 'is a string', '/1273/a~1b/~2': 'invalid "~" escape',
                'no-slash': 'start with "/"'}
    for pointer, words in refusals.items():
        with pytest.raises(json_record.RecordRefusal, match=words):
            json_record.page(raw, pin, {'pointer': pointer})


def test_invalid_ambiguous_and_oversized_sources_are_refused_and_paging_is_exact_in_characters(monkeypatch):
    for text, words in (('{"a": 1,', 'not valid JSON'), ('{"a": NaN}', 'not strict JSON'), ('{"a": 1, "a": 2}', 'ambiguous'),
                        ('{"o": {"k": 1, "k": 2}}', 'selected value is ambiguous')):
        raw = text.encode()
        with pytest.raises(json_record.RecordRefusal, match=words):
            json_record.page(raw, hashlib.sha256(raw).hexdigest(), {'pointer': '/a' if 'a' in text and '"o"' not in text else ''})
    assert json_record.page('﻿{"k": "v"}'.encode(), '0' * 64, {'pointer': '/k'})['content'] == '"v"', 'a UTF-8 BOM is accepted'
    raw = json.dumps({'text': 'é中🌱' * 3000}, ensure_ascii=False).encode()
    pin = hashlib.sha256(raw).hexdigest()
    first = json_record.page(raw, pin, {'pointer': '/text'})
    assert len(first['content']) == json_record.POINTER_DEFAULT_LIMIT == first['next_offset'] and first['truncated']
    pages, offset = [first['content']], first['next_offset']
    while offset is not None:
        page = json_record.page(raw, pin, {'pointer': '/text', 'offset': offset, 'expected_sha256': 'sha256:' + pin})
        pages.append(page['content']); offset = page['next_offset']
    assert json.loads(''.join(pages)) == 'é中🌱' * 3000 and first['json_record']['value_chars'] == len(''.join(pages))
    assert set(first) == {'json_record', 'content', 'offset', 'limit', 'truncated', 'next_offset', 'units'}, 'no full value beside the page'
    with pytest.raises(json_record.RecordRefusal, match='revision conflict'):
        json_record.page(raw, pin, {'pointer': '/text', 'expected_sha256': '1' * 64})
    with pytest.raises(json_record.RecordRefusal, match='past the end'):
        json_record.page(raw, pin, {'pointer': '/text', 'offset': 10 ** 6})
    monkeypatch.setattr(json_record, 'POINTER_MAX_SOURCE_BYTES', 100)
    with pytest.raises(json_record.RecordRefusal, match='parse at most 100 bytes'):
        json_record.page(raw, pin, {'pointer': '/text'})


# --- the repository reader --------------------------------------------------------------------------
def test_repository_read_selects_one_record_of_a_large_shared_source_inside_the_same_perimeter(tmp_path, monkeypatch):
    _shared(tmp_path)
    raw = (tmp_path / 'external' / 'dataset.json').read_bytes()
    assert len(raw) > 300_000
    out = writing_sources.execute(tmp_path, {'action': 'read', 'repository': 'shared', 'path': 'dataset.json', 'pointer': '/1273/query'})
    assert out['source']['sha256'] == hashlib.sha256(raw).hexdigest() and out['source']['bytes'] == len(raw)
    assert json.loads(out['content']) == RECORD['query'] and out['next_offset'] is None and out['json_record']['type'] == 'string'
    assert len(json.dumps(out, ensure_ascii=False)) < 3000, 'one record, not the 300 KB source'
    with pytest.raises(ValueError, match='escapes the selected repository'):
        writing_sources.execute(tmp_path, {'action': 'read', 'repository': 'shared', 'path': '../profiles/writing_sources.json', 'pointer': ''})
    with pytest.raises(ValueError, match='Source revision conflict'):
        writing_sources.execute(tmp_path, {'action': 'read', 'repository': 'shared', 'path': 'dataset.json', 'expected_sha256': '0' * 64})
    with pytest.raises(ValueError, match='expected_sha256 is a complete sha256 digest'):
        writing_sources.execute(tmp_path, {'action': 'read', 'repository': 'shared', 'path': 'dataset.json', 'pointer': '', 'expected_sha256': 'abc'})
    with pytest.raises(ValueError, match='at most 4096'):
        writing_sources.execute(tmp_path, {'action': 'read', 'repository': 'shared', 'path': 'dataset.json', 'pointer': '/' + 'x' * 5000})
    monkeypatch.setattr(json_record, 'POINTER_MAX_SOURCE_BYTES', 1000)
    with pytest.raises(json_record.RecordRefusal, match='parse at most 1000 bytes'):
        writing_sources.execute(tmp_path, {'action': 'read', 'repository': 'shared', 'path': 'dataset.json', 'pointer': '/0'})
    plain = writing_sources.execute(tmp_path, {'action': 'read', 'repository': 'shared', 'path': 'dataset.json', 'limit': 20})
    assert len(plain['content']) == 20 and 'json_record' not in plain, 'plain character reads are unchanged'


# --- the material reader: native, HTTP and the human route ----------------------------------------------
def test_material_source_reads_one_pinned_record_natively_and_over_http_with_an_exact_continuation(tmp_path):
    target = _shared(tmp_path)
    ident = _attach(tmp_path, target)
    native = writing_tools.execute(tmp_path, 'campaign', 'work', 'material_references', {'view': 'source', 'id': ident, 'pointer': '/1273', 'limit': 120})
    owner = native['owner_result']
    pin = 'sha256:' + hashlib.sha256((tmp_path / 'external' / 'dataset.json').read_bytes()).hexdigest()
    assert owner['json_record']['pointer'] == '/1273' and owner['json_record']['source_sha256'] == pin and len(owner['content']) == 120
    assert native['units'] == owner['units'] and 'selected value' in native['units'] and native['currentness'] == 'CURRENT'
    follow = native['read_handle']
    assert follow['payload'] == {'id': ident, 'view': 'source', 'offset': 120, 'limit': 120, 'pointer': '/1273', 'expected_sha256': pin}
    assert 'expected_sha256' not in native['restart_read']['payload'] and native['restart_read']['payload']['offset'] == 0
    code, http = _http(tmp_path, native['human_read']['url'])
    assert code == 200 and http['owner_result']['content'] == owner['content'] and {k: v for k, v in http['owner_result']['json_record'].items() if k != 'parse'} == {k: v for k, v in owner['json_record'].items() if k != 'parse'}, 'the human route opens the same record page (parse timing aside)'
    assert native['human_read']['kind'] == 'material-source' and 'pointer=%2F1273' in native['human_read']['url']
    default = writing_tools.execute(tmp_path, 'campaign', 'work', 'material_references', {'view': 'source', 'id': ident, 'pointer': '/1273'})
    assert default['owner_result']['limit'] == json_record.POINTER_DEFAULT_LIMIT, 'a record page defaults to 6000 characters'
    text, handle = owner['content'], follow
    while handle:
        code, page = _http(tmp_path, handle['http']['url'])
        assert code == 200; text += page['owner_result']['content']; handle = page.get('read_handle')
    assert json.loads(text.replace('1e400', '1'))['query'] == RECORD['query'], 'the continuation completes the exact record'
    # the stale guard: a continuation after the source changed is a revision conflict, never a mixed record
    (tmp_path / 'external' / 'dataset.json').write_text(SOURCE_TEXT.replace('filler', 'FILLER'), encoding='utf-8')
    code, refused = _http(tmp_path, follow['http']['url'])
    assert code == 409 and 'changed since the pinned read' in refused['error']
    # a missing pointer is a refusal of the request, not a 200 diagnostic
    code, refused = _http(tmp_path, wp.material_read_handle('campaign', {'view': 'source', 'id': ident, 'pointer': '/9999'})['http']['url'])
    assert code == 422 and 'has 1274 elements' in refused['error']
    with pytest.raises(ValueError, match='source, preview or workspace-source'):
        wp.material_references('campaign', tmp_path, view='list', pointer='/0')


# --- the artifact reader -------------------------------------------------------------------------------
def test_read_artifact_reads_one_record_of_a_json_artifact_with_a_pinned_continuation_and_no_update_proposal(tmp_path):
    assert wp.create({'name': 'campaign', 'title': 'Campaign', 'kind': 'general'}, tmp_path)[0] == 201
    home = artifacts.project_root(tmp_path, 'campaign')
    (home / 'inputs').mkdir(parents=True, exist_ok=True)
    (home / 'inputs' / 'excerpts.json').write_text(json.dumps({'records': [{'q': 'π' * 9000}]}, ensure_ascii=False), encoding='utf-8')
    first = writing_tools.execute(tmp_path, 'campaign', 'work', 'read_artifact', {'path': 'inputs/excerpts.json', 'scope': 'project', 'pointer': '/records/0/q'})
    assert first['json_record']['type'] == 'string' and len(first['content']) == 6000 and first['complete'] is False
    assert 'update_handle' not in first and 'pointer=%2Frecords%2F0%2Fq' in first['human_read']['url'] and first['revision'] in first['human_read']['url']
    follow = first['read_handle']['payload']
    assert follow['pointer'] == '/records/0/q' and follow['offset'] == 6000 and follow['expected_sha256'] == 'sha256:' + first['revision']
    rest = writing_tools.execute(tmp_path, 'campaign', 'work', 'read_artifact', follow)
    assert json.loads(first['content'] + rest['content']) == 'π' * 9000 and rest['complete'] is True
    (home / 'inputs' / 'excerpts.json').write_text(json.dumps({'records': [{'q': 'changed'}]}), encoding='utf-8')
    with pytest.raises(Exception, match='changed since the pinned read'):
        writing_tools.execute(tmp_path, 'campaign', 'work', 'read_artifact', follow)
    plain = writing_tools.execute(tmp_path, 'campaign', 'work', 'read_artifact', {'path': 'inputs/excerpts.json', 'scope': 'project'})
    assert 'json_record' not in plain and plain['update_handle'], 'plain reads are unchanged'


# --- logical-plan availability --------------------------------------------------------------------------
def test_a_known_source_optional_project_answers_logical_plan_truthfully_while_unknown_projects_are_still_refused(tmp_path):
    assert wp.create({'name': 'campaign', 'title': 'Campaign', 'kind': 'general'}, tmp_path)[0] == 201
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob('*'))
    for payload, route, query in (({}, '/concepts/plan/context', {}), ({'view': 'catalog'}, '/concepts/catalog', {}),
                                  ({'node': 'def:missing'}, '/concepts/plan/context', {'node': ['def:missing']})):
        native = writing_tools.execute(tmp_path, 'campaign', 'work', 'logical_plan', payload)
        code, _, raw = concepts_surface.handle(route, {'project': ['campaign'], **query}, 'GET', b'', repo_root=tmp_path)
        assert code == 200 and json.loads(raw) == native
        assert native['status'] == 'NOT_AVAILABLE' and native['available'] is False and native['items'] == [] and native['total'] == 0
        assert 'not an unknown-project refusal' in native['reason'] and native['write_permission'] is False
        assert {row['operation'] for row in native['supported_reads']} == {'research', 'material_references', 'read_artifact', 'project_metadata'}
    code, _, raw = concepts_surface.handle('/concepts/plan', {'project': ['campaign']}, 'GET', b'', repo_root=tmp_path)
    assert code == 200 and json.loads(raw)['status'] == 'NOT_AVAILABLE'
    help_ = writing_tools.execute(tmp_path, 'campaign', 'work', 'help', {'operation': 'logical_plan'})
    assert help_['action']['permitted'] is True and help_['action']['project_availability']['status'] == 'NOT_AVAILABLE'
    review_help = writing_tools.execute(tmp_path, 'campaign', 'review', 'help', {'operation': 'logical_plan_change'})
    assert review_help['action']['permitted'] is False, 'permissions are unchanged'
    code, refused = concepts_surface.logical_plan_change({'project': 'campaign', 'operation': 'add_node', 'node': 'def:x'}, root=tmp_path)
    assert code == 404 and refused['error'].startswith('No logical plan exists to change') and refused['status'] == 'NOT_AVAILABLE', 'still refused, truthfully'
    assert concepts_surface.logical_plan_change({'project': 'no-such-project'}, root=tmp_path) == (404, {'error': 'unknown project'})
    assert sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob('*') if 'contract' not in p.parts) == [p for p in before if not p.startswith('contract')], 'nothing was created'
    for route, words in (('/concepts/plan/context', 'unknown project or logical object'), ('/concepts/catalog', 'unknown project'), ('/concepts/plan', 'unknown project')):
        code, _, raw = concepts_surface.handle(route, {'project': ['no-such-project']}, 'GET', b'', repo_root=tmp_path)
        assert code == 404 and json.loads(raw)['error'] == words
    assert concepts_surface.logical_plan_availability('no-such-project', tmp_path) is None


def test_a_paper_project_keeps_its_logical_plan_semantics(tmp_path):
    from test_manuscript_structure import _section_fixture
    _section_fixture(tmp_path)
    assert concepts_surface.logical_plan_availability('book', tmp_path) is None, 'only registered source-optional projects are qualified'
    value = writing_tools.execute(tmp_path, 'book', 'work', 'logical_plan', {})
    assert 'status' not in value or value['status'] != 'NOT_AVAILABLE'
    help_ = writing_tools.execute(tmp_path, 'book', 'work', 'help', {'operation': 'logical_plan'})
    assert 'project_availability' not in help_['action']


# --- repair1 (2026-10-14): Sol's four findings ------------------------------------------------------------
def _short_id(value):
    """pytest ids: the case label, never the (huge) adversarial input."""
    return value if isinstance(value, str) and value.isascii() and value.isprintable() and len(value) <= 40 and '{' not in value and '/' not in value else '_'


def _get(root, url):
    parts = urlsplit(url)
    code, _, raw = wp.handle(parts.path, parse_qs(parts.query, keep_blank_values=True), 'GET', b'', repo_root=root)
    return code, json.loads(raw)


def test_r1_human_record_links_keep_the_pointer_page_and_pin_and_restart_is_separate_for_repository_and_artifact(tmp_path):
    # repository record through the material reader
    target = _shared(tmp_path, '[{"id": "original", "body": "' + 'a' * 100 + '"}]', 'records.json')
    ident = _attach(tmp_path, target)
    native = writing_tools.execute(tmp_path, 'campaign', 'work', 'material_references', {'view': 'source', 'id': ident, 'pointer': '/0/id'})
    url = native['human_read']['url']
    assert 'pointer=%2F0%2Fid' in url and 'expected_sha256=' in url and 'offset=0' in url
    code, human = _get(tmp_path, url)
    assert code == 200 and human['owner_result']['content'] == native['owner_result']['content'] == '"original"', 'native -> human parity'
    assert 'expected_sha256' not in native['restart_read']['payload'] and native['restart_read_semantics'].startswith('restart_read reads the CURRENT source')
    # artifact record: the human link is the record page, not the whole file
    home = artifacts.project_root(tmp_path, 'campaign')
    (home / 'record.json').write_text('{"selected": {"x": "original"}, "other": "unrelated"}', encoding='utf-8')
    art = writing_tools.execute(tmp_path, 'campaign', 'work', 'read_artifact', {'path': 'record.json', 'scope': 'project', 'pointer': '/selected'})
    code, shown = _get(tmp_path, art['human_read']['url'])
    assert code == 200 and shown['owner_result']['content'] == art['content'] and 'unrelated' not in json.dumps(shown, ensure_ascii=False)
    assert shown['owner_result']['json_record']['pointer'] == '/selected' and shown['current_revision'] == art['revision']
    # the stale initial human link: both sources change before the person opens the link
    (tmp_path / 'external' / 'records.json').write_text('[{"id": "replacement", "body": "' + 'b' * 100 + '"}]', encoding='utf-8')
    (home / 'record.json').write_text('{"selected": {"x": "replacement"}, "other": "unrelated"}', encoding='utf-8')
    for link, restart in ((url, native['restart_read']), (art['human_read']['url'], art['restart_read'])):
        code, refused = _get(tmp_path, link)
        assert code == 409 and 'changed since the pinned read' in refused['error'], 'the issued link refuses, never a replacement record'
        code, current = _get(tmp_path, restart['http']['url'])
        assert code == 200 and 'replacement' in current['owner_result']['content'], 'restart reads the current source explicitly'


DEEP = '[' * 600 + '0' + ']' * 600


@pytest.mark.parametrize('label,text,pointer,words', [
    ('deep-array', DEEP, '', 'nests deeper than 256 levels'),
    ('deep-object', '{"a":' * 400 + '0' + '}' * 400, '/a', 'nests deeper than 256 levels'),
    ('surrogate-value', '{"x": "\\ud800"}', '/x', 'unpaired UTF-16 surrogate'),
    ('surrogate-key', '{"\\udc00": 1}', '', 'unpaired UTF-16 surrogate')], ids=_short_id)
def test_r2_deep_and_unpaired_surrogate_values_are_clear_refusals_on_every_record_route(tmp_path, label, text, pointer, words):
    target = _shared(tmp_path, text, 'edge.json')
    with pytest.raises(json_record.RecordRefusal, match=words):
        writing_sources.execute(tmp_path, {'action': 'read', 'repository': 'shared', 'path': 'edge.json', 'pointer': pointer})
    home = artifacts.project_root(tmp_path, 'campaign')
    (home / 'edge.json').write_text(text, encoding='utf-8')
    with pytest.raises(json_record.RecordRefusal, match=words):
        artifacts.read(tmp_path, 'campaign', {'path': 'edge.json', 'scope': 'project', 'pointer': pointer})
    for handle in (wp.material_read_handle('campaign', {'view': 'preview', 'target': target, 'pointer': pointer, 'limit': 10}),
                   wp.material_read_handle('campaign', {'view': 'preview', 'target': {'owner': 'artifact', 'project': 'campaign', 'path': 'edge.json', 'scope': 'project'}, 'pointer': pointer})):
        code, refused = _get(tmp_path, handle['http']['url'])
        assert code == 422 and words in refused['error'], (label, code, refused)
    assert json_record.page(b'{"k": "\\ud83c\\udf31"}', '0' * 64, {'pointer': '/k'})['content'] == '"🌱"', 'a paired surrogate escape is ordinary text'
    with pytest.raises(json_record.RecordRefusal, match='pointer contains an unpaired'):
        json_record.tokens('/\ud800')


def test_r3_availability_reports_no_logical_plan_owner_separately_from_the_selected_manuscript(tmp_path):
    assert wp.create({'name': 'campaign', 'title': 'Campaign', 'kind': 'general'}, tmp_path)[0] == 201
    def observed():
        native = writing_tools.execute(tmp_path, 'campaign', 'work', 'logical_plan', {})
        code, _, raw = concepts_surface.handle('/concepts/plan/context', {'project': ['campaign']}, 'GET', b'', repo_root=tmp_path)
        assert code == 200 and json.loads(raw) == native
        help_ = writing_tools.execute(tmp_path, 'campaign', 'work', 'help', {'operation': 'logical_plan'})['action']['project_availability']
        assert {k: help_[k] for k in ('status', 'reason', 'manuscript', 'logical_plan_owner')} == {k: native[k] for k in ('status', 'reason', 'manuscript', 'logical_plan_owner')}
        return native
    before = observed()
    assert before['status'] == 'NOT_AVAILABLE' and before['logical_plan_owner'] is None and before['manuscript']['selected'] is False
    assert 'no selected manuscript' in before['reason'] and 'starts_a_plan' not in before and 'creates nothing' in before['creates_a_plan']
    assert next(r for r in before['supported_reads'] if r['operation'] == 'project_metadata')['says'] == 'display title, selected-source facts and capabilities'
    assert before['authoring_state'] == 'NO_MANUSCRIPT' and before['next_action']['payload']['operation'] == 'start_authoring'
    # M5 bootstrap: a manuscript started WITHOUT plan ownership (the existing-project case, e.g. created before the
    # lifecycle transition existed) keeps the plan unavailable and names the guarded start_authoring next action
    status, draft = wp._start_manuscript_unplanned({'project': 'campaign', 'title': 'Audit report', 'kind': 'paper'}, tmp_path)
    assert status == 201, draft
    after = observed()
    assert after['status'] == 'NOT_AVAILABLE' and after['manuscript'] == {'status': 'resolved', 'selected': True, 'read_only': False}
    assert 'selected manuscript is readable' in after['reason'] and 'no manuscript' not in after['reason'] and 'no selected manuscript' not in after['reason']
    assert after['authoring_state'] == 'MANUSCRIPT_WITHOUT_PLAN' and after['next_action']['payload']['operation'] == 'start_authoring'
    caps = wp.metadata('campaign', tmp_path)['capabilities']
    assert caps['manuscript'] is True and caps['concepts'] is False and caps['start_planning'] is True
    code, refused = concepts_surface.logical_plan_change({'project': 'campaign', 'operation': 'add_node', 'node': 'def:x'}, root=tmp_path)
    assert code == 404 and refused['error'].startswith('No logical plan exists to change') and 'selected manuscript' in refused['error']
    # the guarded transition makes the same project's logical plan available; nothing else about it moves
    writing_tools.execute(tmp_path, 'campaign', 'work', 'structure_change', after['next_action']['payload'])
    owned = writing_tools.execute(tmp_path, 'campaign', 'work', 'logical_plan', {})
    assert owned.get('status') != 'NOT_AVAILABLE' and wp.metadata('campaign', tmp_path)['capabilities']['concepts'] is True


def test_r4_a_source_that_grows_after_the_stat_is_read_at_most_cap_plus_one_bytes_and_refused(tmp_path, monkeypatch):
    _shared(tmp_path, '{"x": "small"}', 'grow.json')
    home = artifacts.project_root(tmp_path, 'campaign')
    (home / 'grow.json').write_text('{"x": "small"}', encoding='utf-8')
    requested, grow = [], {}
    real_open, real_read = json_record.os.open, json_record.os.read
    def opening(path, flags, *args):
        if str(path) in grow:   # the file grows after the reader's stat and before its read
            pathlib_path = grow.pop(str(path)); pathlib_path.write_text('{"x": "' + 'a' * 50_000 + '"}', encoding='utf-8')
        return real_open(path, flags, *args)
    def reading(fd, size):
        requested.append(size); return real_read(fd, size)
    monkeypatch.setattr(json_record.os, 'open', opening)
    monkeypatch.setattr(json_record.os, 'read', reading)
    monkeypatch.setattr(json_record, 'POINTER_MAX_SOURCE_BYTES', 1000)
    source = tmp_path / 'external' / 'grow.json'
    grow[str(source)] = source
    with pytest.raises(json_record.RecordRefusal, match='parse at most 1000 bytes'):
        writing_sources.execute(tmp_path, {'action': 'read', 'repository': 'shared', 'path': 'grow.json', 'pointer': '/x'})
    assert sum(requested) <= 1001, requested
    # growth between open and read: the descriptor read is still capped at cap + 1 and refused
    requested.clear(); source.write_text('{"x": "small"}', encoding='utf-8')
    def opening_then_grow(path, flags, *args):
        fd = real_open(path, flags, *args)
        if str(path) == str(source):
            source.write_text('{"x": "' + 'b' * 50_000 + '"}', encoding='utf-8')
        return fd
    monkeypatch.setattr(json_record.os, 'open', opening_then_grow)
    with pytest.raises(json_record.RecordRefusal):
        writing_sources.execute(tmp_path, {'action': 'read', 'repository': 'shared', 'path': 'grow.json', 'pointer': '/x'})
    assert sum(requested) <= 1001, requested
    # the artifact record route keeps its 2 MB cap the same way
    requested.clear(); monkeypatch.setattr(json_record.os, 'open', opening)
    monkeypatch.setattr(artifacts, '_ARTIFACT_TEXT_MAX', 1000)
    grow[str(home / 'grow.json')] = home / 'grow.json'
    with pytest.raises(json_record.RecordRefusal, match='parse at most 1000 bytes'):
        artifacts.read(tmp_path, 'campaign', {'path': 'grow.json', 'scope': 'project', 'pointer': '/x'})
    assert sum(requested) <= 1001, requested
    # unchanged sources still read and pin from exactly the admitted bytes
    monkeypatch.setattr(json_record.os, 'open', real_open)
    source.write_text('{"x": "small"}', encoding='utf-8')
    out = writing_sources.execute(tmp_path, {'action': 'read', 'repository': 'shared', 'path': 'grow.json', 'pointer': '/x'})
    assert out['content'] == '"small"' and out['source']['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()


# JSON-R2 bounded refusal diagnostics (2026-10-14): source-controlled keys and locations never make a refusal large;
# a safe prefix and the complete length and identity remain, and short keys stay readable.
@pytest.mark.parametrize('label,text,pointer,words', [
    ('long-cjk-duplicate', '{' + json.dumps('汉' * 50000, ensure_ascii=False) + ':1,' + json.dumps('汉' * 50000, ensure_ascii=False) + ':2}', '', 'appears more than once'),
    ('long-escaped-duplicate', '{"' + '\\u0041' * 40000 + '":1,"' + 'A' * 40000 + '":2}', '', 'appears more than once'),
    ('long-key-on-path', '{"' + 'k' * 60000 + '": {"a": 1, "a": 2}}', '/' + 'k' * 60000, 'ambiguous'),
    ('long-unpaired-key', '{"' + 'z' * 30000 + '\\udc00": 1}', '', 'unpaired UTF-16 surrogate'),
    ('deep-location', '[' * 600 + '0' + ']' * 600, '', 'nests deeper than 256 levels'),
    ('long-missing-token', '{"a": 1}', '/' + '缺' * 3000, 'has no key'),
    # escape-heavy controls (serialized-transport budget): NUL, quote, backslash and newline keys and pointers
    ('nul-location', json.dumps({'\x00' * 230: {'exists': 1}}), '/' + '\x00' * 230 + '/' + 'missing' * 400, 'has no key'),
    ('quote-backslash-duplicate', '{' + json.dumps('"\\' * 20000) + ':1,' + json.dumps('"\\' * 20000) + ':2}', '', 'appears more than once'),
    ('newline-deep-key', '{' + json.dumps('\n' * 3000) + ':' + '[' * 300 + '0' + ']' * 300 + '}', '/' + '\n' * 3000, 'nests deeper than 256 levels')], ids=_short_id)
def test_refusal_diagnostics_are_bounded_by_utf8_with_a_prefix_and_identity(tmp_path, label, text, pointer, words):
    raw = text.encode()
    if label == 'long-key-on-path':
        pointer = '/' + 'k' * 4000   # the pointer itself is limited to 4096 characters
        raw = ('{"' + 'k' * 4000 + '": {"a": 1, "a": 2}}').encode()
        pointer = pointer + '/a'
    with pytest.raises(json_record.RecordRefusal) as caught:
        json_record.page(raw, hashlib.sha256(raw).hexdigest(), {'pointer': pointer})
    message = str(caught.value)
    assert words in message and json_record.serialized_bytes(message) <= json_record.MAX_DIAGNOSTIC_BYTES, (label, json_record.serialized_bytes(message))
    assert '[truncated:' in message and 'sha256:' in message, 'the remainder is named, not silently dropped'
    target = _shared(tmp_path, raw.decode(), 'edge.json')
    parts = urlsplit(wp.material_read_handle('campaign', {'view': 'preview', 'target': target, 'pointer': pointer})['http']['url'])
    code, _, body = wp.handle(parts.path, parse_qs(parts.query, keep_blank_values=True), 'GET', b'', repo_root=tmp_path)
    refused = json.loads(body)
    assert code == 422 and words in refused['error'] and set(refused) == {'error'}
    assert len(body) <= json_record.MAX_DIAGNOSTIC_BYTES + json_record.REFUSAL_ENVELOPE_BYTES, ('the actual HTTP bytes, escapes and envelope included', label, len(body))


def test_short_keys_and_locations_stay_whole_and_readable_in_refusals():
    raw = '{"o": {"π键": 1, "π键": 2}}'.encode()
    with pytest.raises(json_record.RecordRefusal) as caught:
        json_record.page(raw, hashlib.sha256(raw).hexdigest(), {'pointer': '/o'})
    assert str(caught.value) == 'The selected value is ambiguous: key "π键" appears more than once at /o; it has no single JSON reading.'
    assert json_record._bounded('x' * 98, 100) == 'x' * 98, 'a text whose serialized string fits is shown whole'
    bounded = json_record._bounded('é' * 51, 100)
    assert json_record.serialized_bytes(bounded) <= 100 and 'truncated: 51 characters, 102 UTF-8 bytes' in bounded and bounded.startswith('é')
    controls = json_record._bounded('\x00' * 100, 200)   # each NUL serializes as \u0000 (6 bytes)
    assert json_record.serialized_bytes(controls) <= 200 and 'truncated: 100 characters, 100 UTF-8 bytes' in controls
    assert json_record.serialized_bytes('\x00') == 8 and json_record.serialized_bytes('é') == 4
