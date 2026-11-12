"""M2 exact source witnesses and the existing reader-plan publication owner."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from laplace.manuscript import project_structure, storyboard
from laplace.native import tools as writing_tools
from laplace.manuscript import bindings
from laplace.writing import records
from test_manuscript_structure import _section_fixture
from test_writing_controller import _import_project


def _bind(root, section='first', line=1):
    outline = writing_tools.execute(root, 'book', 'work', 'structure', {'view': 'outline'})
    summary = writing_tools.execute(root, 'book', 'work', 'structure', {'view': 'summary'})
    heading = next(row for row in outline['headings']['items'] if row['line'] == line)
    payload = {'operation': 'bind_source', 'section_id': section, 'file': heading['file'],
               'line': heading['line'], 'heading_before': heading['heading_before'],
               'expected_plan_revision': summary['authority']['plan_revision'],
               'expected_selection': outline['selected_source']['selection_identity'],
               'expected_source_digest': outline['sources'][heading['file']]['source_digest']}
    return writing_tools.execute(root, 'book', 'work', 'structure_change', payload), payload


def test_source_only_outline_preserves_balanced_tex_and_raw_crlf_basis(tmp_path):
    source, _ = _import_project(tmp_path)
    text = b'\\documentclass{article}\r\n\\begin{document}\r\n\\section{A \\emph{nested} title}\r\nBody.\r\n\\end{document}\r\n'
    (source / 'main.tex').write_bytes(text)
    value = writing_tools.execute(tmp_path, 'fixture', 'work', 'structure', {'view': 'outline'})
    heading = value['headings']['items'][0]
    assert heading['title'] == r'A \emph{nested} title'
    basis = value['sources'][heading['file']]
    assert basis['source_digest'] == 'sha256:' + hashlib.sha256(text).hexdigest()
    assert value['read_routes']['source_read']['http']['route'] == '/projection/tex' and value['read_routes']['source_read']['payload']['files'] == ['<file>']
    assert set(heading) == set(bindings.OUTLINE_ROW_FIELDS), 'the outline row is the trimmed list row'
    from laplace.manuscript import manuscript_source
    observed = manuscript_source.observation('fixture', tmp_path)
    assert 'sha256:' + observed['file_revisions'][heading['file']] == basis['source_digest']
    assert value['status'] == 'AVAILABLE'
    assert project_structure.read('fixture', {'view': 'summary'}, tmp_path)['availability']['reader_plan'] == 'MISSING'
    (source / 'main.tex').write_bytes(text + b'% changed\r\n')
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        project_structure.read('fixture', {'view': 'outline', 'as_of': value['as_of']}, tmp_path)


def test_binding_changes_only_plan_and_noop_does_not_append(tmp_path):
    manuscript, source, _ = _section_fixture(tmp_path)
    before = source.read_bytes()
    result, payload = _bind(tmp_path)
    assert result['link_established'] and result['binding']['precision'] == 'EXACT_HEADING'
    assert source.read_bytes() == before and 'source_effect' not in result
    ledger = storyboard._sidecar('book', '.friction.jsonl', tmp_path)
    first = ledger.read_bytes()
    payload['expected_plan_revision'] = bindings.digest((manuscript / 'projection_plan.json').read_bytes())
    again = project_structure.change('book', payload, tmp_path)
    assert again['changed'] is False and ledger.read_bytes() == first
    payload['expected_source_digest'] = 'sha256:' + '0' * 64
    with pytest.raises(ValueError, match='source bytes changed'):
        project_structure.change('book', payload, tmp_path)
    assert ledger.read_bytes() == first


def test_exact_parent_child_coverage_and_local_deepest_enclosure(tmp_path):
    _, source, _ = _section_fixture(tmp_path)
    _bind(tmp_path, 'first', 1)
    _bind(tmp_path, 'first-child', 3)
    _bind(tmp_path, 'second', 5)
    snapshot = bindings.reader_snapshot('book', tmp_path)
    file = source.relative_to(tmp_path).as_posix()
    covered, _ = bindings.sections_for_span(snapshot, file, 1, 4)
    assert [row['id'] for row in covered] == ['first', 'first-child']
    local, _ = bindings.sections_for_span(snapshot, file, 4, 4)
    assert [row['id'] for row in local] == ['first-child']
    assert 'second' not in [row['id'] for row in local]


def test_unrelated_same_title_and_duplicate_labels_do_not_bind_by_guess(tmp_path):
    _, source, _ = _section_fixture(tmp_path)
    summary = project_structure.read('book', {'view': 'summary'}, tmp_path)
    assert summary['sections']['items'][0]['precision'] == 'FILE_ONLY'
    snapshot = bindings.reader_snapshot('book', tmp_path)
    found, limits = bindings.sections_for_span(snapshot, source.relative_to(tmp_path).as_posix(), 2, 2)
    assert not found and limits
    source.write_text('\\chapter{First}\n\\label{dup}\nBody.\n\\chapter{Second}\n\\label{dup}\n')
    with pytest.raises(ValueError, match='ambiguous'):
        _bind(tmp_path)


def test_warm_plan_batch_uses_no_full_ledger_and_refuses_external_plan_edit(tmp_path, monkeypatch):
    manuscript, _, _ = _section_fixture(tmp_path)
    first = storyboard.plan_write('book', {'kind': 'edit-job', 'section': 'first', 'job': 'new'}, tmp_path)
    assert first['applied']
    monkeypatch.setattr(storyboard, '_read_ledger', lambda *a: pytest.fail('whole history read'))
    index = records.index(tmp_path, storyboard._sidecar('book', '.friction.jsonl', tmp_path).relative_to(tmp_path))
    scans = index.stats['scans']
    result = storyboard.plan_write_batch('book', [
        {'kind': 'retitle', 'section': 'first', 'title': 'Renamed'},
        {'kind': 'edit-notes', 'section': 'first', 'notes': 'Owned notes'}], tmp_path)
    assert result['applied'] and index.stats['scans'] == scans
    path = manuscript / 'projection_plan.json'
    changed = json.loads(path.read_text()); changed['sections'][0]['title'] = 'External'
    path.write_text(json.dumps(changed))
    before = path.read_bytes()
    refused = storyboard.plan_write('book', {'kind': 'retitle', 'section': 'first', 'title': 'Overwrite'}, tmp_path)
    assert refused['status'] == 'PROJECTION_DIVERGED' and path.read_bytes() == before


@pytest.mark.parametrize('failure', ['second_append', 'publication'])
def test_plan_batch_failure_compensates_only_its_exact_tail_and_owner_can_recover(tmp_path, monkeypatch, failure):
    manuscript, _, _ = _section_fixture(tmp_path)
    path = manuscript / 'projection_plan.json'; before = path.read_bytes()
    append = storyboard._append_ledger
    publish = storyboard._write_plan_json
    calls = 0
    def failed_append(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError('append fixture failure')
        return append(*args)
    def failed_publish(*args):
        raise OSError('publication fixture failure')
    monkeypatch.setattr(storyboard, '_append_ledger', failed_append if failure == 'second_append' else append)
    monkeypatch.setattr(storyboard, '_write_plan_json', failed_publish if failure == 'publication' else publish)
    with pytest.raises(storyboard.PlanPublicationFailure) as caught:
        storyboard.plan_write_batch('book', [
            {'kind': 'retitle', 'section': 'first', 'title': 'One'},
            {'kind': 'retitle', 'section': 'second', 'title': 'Two'}], tmp_path)
    assert caught.value.details['plan_publication']['status'] == 'COMPENSATED', caught.value.details
    assert path.read_bytes() == before
    assert storyboard._sidecar('book', '.friction.jsonl', tmp_path).read_bytes() == b''
    monkeypatch.setattr(storyboard, '_append_ledger', append)
    monkeypatch.setattr(storyboard, '_write_plan_json', publish)
    result = storyboard.plan_write('book', {'kind': 'retitle', 'section': 'first', 'title': 'Explicit recovery'}, tmp_path)
    assert result['applied']
