"""Small public source-owner fixtures. No provider or external PDF command is used."""
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from laplace.core import json_record, source_pin
from laplace.projects import artifacts, library, writing_sources


@pytest.fixture
def sources(tmp_path):
    assert library.create({'name': 'book', 'title': 'Public source fixture', 'kind': 'general'}, tmp_path)[0] == 201
    (tmp_path / 'profiles').mkdir(exist_ok=True);(tmp_path / 'inputs').mkdir()
    (tmp_path / 'profiles/writing_sources.json').write_text(json.dumps({'repositories': {'public': 'inputs'}}))
    text = 'é中🌱A\nSecond public line.\n'
    raw = ('{ "selected": "' + 'é中🌱' * 40 + '", "other": 1 }\n').encode()
    (tmp_path / 'inputs/plain.txt').write_text(text);(tmp_path / 'inputs/data.json').write_bytes(raw)
    return tmp_path, text, raw


def repository(root, **fields):
    return writing_sources.execute(root, {'action': 'read', 'repository': 'public', 'path': 'plain.txt', **fields})


def follow(root, handle):
    if handle['operation'] == 'repository':return writing_sources.execute(root, handle['payload'])
    if handle['operation'] == 'read_artifact':return artifacts.read(root, 'book', handle['payload'])
    assert handle['operation'] == 'material_references'
    return library.material_references('book', root, **handle['payload'])


def test_plain_repository_source_pin_and_verbatim_page_next_restart(sources):
    root, text, _ = sources
    first = repository(root, limit=3)
    assert first['content'] == 'é中🌱' and first['next_offset'] == 3
    assert follow(root, first['page_read'])['content'] == first['content']
    assert follow(root, first['read_handle'])['content'] == text[3:6]
    assert first['read_handle']['payload']['expected_sha256'] == 'sha256:' + first['source']['sha256']
    assert 'pointer' not in first['page_read']['payload']
    assert repository(root, expected_sha256=first['source']['sha256'].upper())['content'] == text
    identity = writing_sources.reference_identity(root, {'repository': 'public', 'path': 'plain.txt'})
    assert 'expected_sha256' not in identity['read_handle']['payload']
    (root / 'inputs/plain.txt').write_text('Changed current text.')
    with pytest.raises(source_pin.SourcePinRefusal, match='revision conflict'):follow(root, first['read_handle'])
    assert follow(root, first['restart_read'])['content'] == 'Cha'
    with pytest.raises(ValueError):repository(root, path='../profiles/writing_sources.json', expected_sha256=first['source']['sha256'])


@pytest.mark.parametrize('bad', [None, True, 'x' * 20000])
def test_malformed_pin_diagnostics_are_bounded_without_echo(sources, bad):
    root, _, _ = sources
    with pytest.raises(ValueError) as refusal:repository(root, expected_sha256=bad)
    assert len(str(refusal.value)) < 500 and 'xxxx' not in str(refusal.value)
    with pytest.raises(source_pin.SourcePinRefusal) as refusal:
        source_pin.check('0' * 64, {'expected_sha256': bad})
    assert len(str(refusal.value)) < 500 and 'xxxx' not in str(refusal.value)
    with pytest.raises(source_pin.SourcePinRefusal):artifacts.read(root, 'book', {'path': 'absent.txt', 'expected_sha256': bad})


def test_artifact_plain_utf8_byte_pages_are_pinned_and_missing_cannot_match(sources):
    root, text, _ = sources
    saved = artifacts.store(root, 'book', {'path': 'notes.txt', 'before': None, 'content': text, 'reason': 'Public bytes.'})
    first = artifacts.read(root, 'book', {'id': saved['id'], 'limit': 1, 'expected_sha256': saved['revision']})
    assert first['content'] == 'é' and first['next_offset'] == 2
    assert follow(root, first['page_read'])['content'] == 'é'
    next_page = follow(root, first['read_handle']);assert next_page['content'] == '中' and next_page['offset'] == 2
    assert artifacts.read(root, 'book', {'path': 'missing.txt'})['exists'] is False
    with pytest.raises(source_pin.SourcePinRefusal, match='absent'):
        artifacts.read(root, 'book', {'path': 'missing.txt', 'expected_sha256': saved['revision']})
    artifacts.store(root, 'book', {'path': 'notes.txt', 'expected_revision': saved['revision'], 'content': 'New current text', 'reason': 'Public change.'})
    with pytest.raises(source_pin.SourcePinRefusal, match='revision conflict'):follow(root, first['read_handle'])
    assert follow(root, first['restart_read'])['content'] == 'N'


def test_json_pointer_presence_and_full_source_value_distinction(sources):
    root, _, raw = sources
    first = repository(root, path='data.json', pointer='/selected', limit=7)
    assert first['json_record']['source_sha256'] != first['json_record']['value_sha256']
    assert follow(root, first['page_read'])['content'] == first['content']
    assert follow(root, first['read_handle'])['offset'] == 7
    plain = repository(root, path='data.json', limit=40000)
    entire = repository(root, path='data.json', pointer='', limit=40000)
    assert plain['content'] == raw.decode() and entire['content'] != plain['content']
    assert entire['page_read']['payload']['pointer'] == ''
    with pytest.raises(json_record.RecordRefusal, match='revision conflict'):
        repository(root, path='data.json', pointer='/selected', expected_sha256=first['json_record']['value_sha256'])
    (root / 'inputs/data.json').write_bytes(raw.replace(b'"other": 1', b'"other": 2'))
    current = repository(root, path='data.json', pointer='/selected', limit=7)
    assert current['json_record']['value_sha256'] == first['json_record']['value_sha256']
    with pytest.raises(json_record.RecordRefusal, match='revision conflict'):follow(root, first['read_handle'])
    assert follow(root, first['restart_read'])['source']['sha256'] == current['source']['sha256']


@pytest.mark.parametrize('owner', ['repository', 'artifact'])
def test_Material_plain_pin_human_next_restart_closure(sources, owner):
    root, text, _ = sources
    if owner == 'artifact':
        artifacts.store(root, 'book', {'path': 'notes.txt', 'before': None, 'content': text, 'reason': 'Public Material.'})
        target = {'owner': 'artifact', 'project': 'book', 'path': 'notes.txt', 'scope': 'project'}
    else:target = {'owner': 'repository', 'repository': 'public', 'path': 'plain.txt'}
    first = library.material_references('book', root, view='preview', target=target, limit=3)
    page = follow(root, first['page_read'])
    assert page['owner_result']['content'] == first['owner_result']['content']
    next_page = follow(root, first['read_handle']);assert next_page['owner_result']['offset'] == first['owner_result']['next_offset']
    parts = urlsplit(first['human_read']['url'])
    code, _, body = library.handle(parts.path, parse_qs(parts.query, keep_blank_values=True), 'GET', b'', repo_root=root)
    assert code == 200 and json.loads(body)['owner_result']['content'] == first['owner_result']['content']
    assert 'expected_sha256=' in parts.query and 'pointer=' not in parts.query
    path = root / 'inputs/plain.txt' if owner == 'repository' else artifacts.resolve_path(root, 'book', 'notes.txt')
    path.write_text('Changed source current bytes.')
    with pytest.raises(source_pin.SourcePinRefusal):follow(root, first['read_handle'])
    assert follow(root, first['restart_read'])['current_revision'] != first['current_revision']
    assert first['currentness'] == page['currentness'] == 'UNBOUND'


def test_workspace_Material_plain_page_keeps_exact_consumer_scope(sources):
    root, _, _ = sources;target = {'owner': 'repository', 'repository': 'public', 'path': 'plain.txt'}
    preview = library.material_references('book', root, view='preview', target=target)
    attached = library.change_material_reference('book', {'action': 'attach', 'target': target,
        'expected_revision': preview['revision'], 'consumed_revision': preview['current_revision']}, root)
    value = library.material_references('book', root, view='workspace-source', consumer='book', id=attached['reference']['id'], limit=3)
    assert value['page_read']['payload']['view'] == 'workspace-source'
    assert value['page_read']['payload']['consumer'] == value['read_handle']['payload']['consumer'] == 'book'
    assert follow(root, value['page_read'])['scope'] == 'workspace'


@pytest.mark.parametrize('record', [{}, {'pointer': '/selected'}])
def test_cross_project_Material_only_exposes_qualified_artifact_pages(sources, record):
    root, _, _ = sources
    assert library.create({'name': 'other', 'title': 'Other public owner', 'kind': 'general'}, root)[0] == 201
    text = '{"selected":"identical source bytes"}'
    for project in ('book', 'other'):
        artifacts.store(root, project, {'path': 'same.txt', 'scope': 'project', 'before': None,
            'content': text, 'reason': 'Public same-bytes/different-target control.'})
    target = {'owner': 'artifact', 'project': 'other', 'path': 'same.txt', 'scope': 'project'}
    first = library.material_references('book', root, view='preview', target=target, limit=5, **record)
    owner = first['owner_result']
    wrong = artifacts.read(root, 'book', {'path': 'same.txt', 'scope': 'project', 'limit': 5, **record})
    assert owner['revision'] == wrong['revision'] and owner['path'] != wrong['path']
    assert 'page_read' not in owner
    assert not any(value.get('operation') == 'read_artifact' for key, value in owner.items()
                   if key in {'read_handle', 'restart_read', 'page_read'} and isinstance(value, dict))
    for key in (('record_read', 'read_handle', 'restart_read') if record else ('page_read', 'read_handle', 'restart_read')):
        observed = follow(root, first[key])
        assert observed['target'] == target
        assert observed['owner_result']['path'] == owner['path']
    if record:
        # Preserve the previously qualified nested JSON record/current restart closure.
        for key in ('record_read', 'restart_read'):
            assert follow(root, owner[key])['target'] == target
    else:
        assert 'restart_read' not in owner
    changed = '{"selected":"changed other owner"}'
    artifacts.resolve_path(root, 'other', 'same.txt').write_text(changed)
    with pytest.raises((source_pin.SourcePinRefusal, json_record.RecordRefusal)):
        follow(root, first['read_handle'])
    restarted = follow(root, first['restart_read'])
    assert restarted['target'] == target and restarted['owner_result']['path'] == owner['path']
    assert restarted['current_revision'] != first['current_revision']
    assert artifacts.read(root, 'book', {'path': 'same.txt', 'scope': 'project'})['content'] == text
    (root / 'cross-project-wrapper-proof.json').write_text(json.dumps({'target': target,
        'record': record, 'source_path': owner['path'], 'different_consumer_path': wrong['path'],
        'identical_initial_raw_digest': owner['revision'] == wrong['revision'],
        'nested_direct_descriptors_removed': True, 'qualified_record_closure_preserved': bool(record),
        'explicit_restart_target': restarted['target']}, indent=2))


def test_comparison_reuses_existing_owner_identity_and_no_full_content_in_handles(sources, monkeypatch):
    root, _, raw = sources;calls=[];binary_opens=[];original=source_pin.check;path_open=Path.open;fd_open=os.open
    def check(identity,payload):calls.append(identity);return original(identity,payload)
    def opened(path,mode='r',*args,**kwargs):
        if path in {root/'inputs/plain.txt',root/'inputs/data.json'} and 'b' in mode:binary_opens.append(str(path))
        return path_open(path,mode,*args,**kwargs)
    def descriptor(path,*args,**kwargs):
        if Path(path) in {root/'inputs/plain.txt',root/'inputs/data.json'}:binary_opens.append(str(path))
        return fd_open(path,*args,**kwargs)
    monkeypatch.setattr(source_pin,'check',check);monkeypatch.setattr(Path,'open',opened);monkeypatch.setattr(os,'open',descriptor)
    plain=repository(root,limit=3);assert len(calls)==len(binary_opens)==1
    calls.clear();binary_opens.clear()
    selected=repository(root,path='data.json',pointer='/selected',limit=7)
    assert len(calls)==len(binary_opens)==1
    assert all('content' not in handle['payload'] for handle in [plain['page_read'],plain['read_handle'],plain['restart_read']])
    assert raw.decode() not in json.dumps(selected,ensure_ascii=False)
    proof={'raw_source_bytes':len(raw),'content_utf8_bytes':len(selected['content'].encode()),
        'response_utf8_bytes':len(json.dumps(selected,ensure_ascii=False).encode()),
        'repository_plain_source_binary_opens':1,'pointer_source_binary_opens':1,'pointer_comparison_calls':1,'extra_source_reads_or_hashes_by_comparator':0}
    (root/'source-read-work-proof.json').write_text(json.dumps(proof,indent=2))


def test_pdf_text_pin_uses_original_binary_identity_and_existing_page_controls(sources, monkeypatch):
    root, _, _ = sources;raw=b'%PDF public deterministic adapter fixture';(root/'inputs/source.pdf').write_bytes(raw);calls=[]
    monkeypatch.setattr(writing_sources,'_tool',lambda name:name)
    def run(argv):calls.append(argv);return b'Pages: 3\n' if argv[0]=='pdfinfo' else 'é extracted page text'.encode()
    monkeypatch.setattr(writing_sources,'_run',run)
    first=repository(root,path='source.pdf',page=2,page_count=1,limit=40000)
    assert first['source']['sha256']==hashlib.sha256(raw).hexdigest()
    assert first['read_handle']['payload']['page']==3 and first['read_handle']['payload']['offset']==0
    assert first['restart_read']['payload']['page']==2 and 'expected_sha256' not in first['restart_read']['payload']
    before=len(calls)
    with pytest.raises(source_pin.SourcePinRefusal):repository(root,path='source.pdf',expected_sha256=hashlib.sha256(first['content'].encode()).hexdigest())
    assert len(calls)==before  # stale raw pin refuses before extraction, no renderer changes
