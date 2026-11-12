from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('writing_eval_manifest', Path(__file__).parents[1] / 'scripts/writing_eval_manifest.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def write(root, relative, value):
    p = root / relative
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(value if isinstance(value, str) else json.dumps(value))
    return p


def rows(root, path, values):
    return write(root, path, ''.join(json.dumps(x) + '\n' for x in values))


def blob(root, value):
    raw = json.dumps(value).encode()
    digest = hashlib.sha256(raw).hexdigest()
    p = root / 'contract/writing_bodies' / digest[:2] / digest
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(raw)
    return {'schema_version': m.BODY_SCHEMA, 'store': 'contract/writing_bodies',
            'content_handle': 'sha256:' + digest, 'bytes': len(raw)}


def fixture(root):
    write(root, 'pyproject.toml', '[project]\nname="example"\n')
    write(root, 'registry_projects.json', {'projects': [
        {'name': 'first', 'project_dir': 'projects/first', 'tex_root': 'projects/first/text'},
        {'name': 'second', 'project_dir': 'projects/second', 'tex_root': 'projects/second/text'}]})
    write(root, 'src/laplace/app.py', 'import json\nfrom laplace import source\n')
    write(root, 'src/laplace/ignored.txt', 'Not Python code.')
    write(root, 'src/laplace/web/static_shared/app.mjs', 'export const x=1;')
    write(root, 'src/laplace/app.html', '<main>Readable</main>')
    write(root, 'projects/first/text/main.tex', 'Project source.')
    write(root, 'projects/first/text/references.json', {'sources': [
        {'doi': '10.1000/example', 'source': {'path': '/external/research.tex'}}]})
    write(root, 'projects/first/.env', 'PRIVATE_TEST_VALUE')
    write(root, 'projects/first/.claude/session.json', 'PRIVATE_TEST_VALUE')
    write(root, 'projects/second/text/main.tex', 'Other source.')
    write(root, 'projects/second/text/references.json', {'associations': []})
    for project in ('first', 'second'):
        for name, value in (
            ('projection_plan.json', {'sections': []}),
            ('research_records.json', {'records': []}),
            ('research_producers.json', {'producers': []}),
            ('figure_manifest.json', {'figures': []}),
        ):
            write(root, f'projects/{project}/text/{name}', value)
        p = root / f'projects/{project}/text/main.pdf'; p.write_bytes((project + ' pdf').encode())
    for relative in (
        'docs/writing-evaluation-release.md', 'docs/writing-evaluator-readme.md',
        'docs/writing-evaluator-agents.md',
        'docs/writing-container.md', 'docs/writing-registry.md', 'deploy/writing/Dockerfile',
        'deploy/writing/writing-entrypoint.sh', 'deploy/writing/smoke.py',
    ):
        write(root, relative, 'required release input')
    inner = blob(root, {'text': 'Scientific history.'})
    outer = blob(root, {'nested': [inner], 'ordinary_source_sha256': 'f' * 64})
    secret = blob(root, {'text': 'Unrelated history.'})
    rows(root, 'contract/talk.jsonl', [
        {'record': 'writing-session', 'id': 'WS1', 'project': 'first'},
        {'record': 'writing-turn', 'id': 'WT1', 'project': 'first', 'session_id': 'WS1'},
        {'record': 'writing-tool-read', 'id': 'READ1', 'turn_id': 'WT1',
         'operation': 'source', 'payload': {}, 'body': outer},
        {'record': 'writing-session', 'id': 'WS2', 'project': 'second'},
        {'record': 'writing-turn', 'id': 'WT2', 'project': 'second', 'session_id': 'WS2'},
        {'record': 'writing-reply', 'id': 'OTHER', 'project': 'second', 'turn_id': 'WT2',
         'text': 'I mention first.', 'body': secret},
        {'record': 'unscoped', 'id': 'UNRELATED', 'text': 'first'}])
    rows(root, 'corpus_friction/first.jsonl', [{'node': 'claim:one', 'meaning': 'A claim.'}])
    rows(root, 'corpus_friction/second.jsonl', [{'node': 'claim:two', 'meaning': 'Another claim.'}])
    rows(root, 'corpus_friction/work_orders.jsonl', [
        {'id': 'WO1', 'project': 'first'}, {'id': 'WO2', 'project': 'second', 'text': 'first'}])
    rows(root, 'contract/journal.jsonl', [
        {'record': 'act', 'act_id': 'A'},
        {'record': 'bank', 'act_id': 'A', 'store': 'contract/talk.jsonl', 'row_id': 'READ1'},
        {'record': 'bank', 'act_id': 'A', 'store': 'contract/talk.jsonl', 'row_id': 'OTHER'},
        {'record': 'act_end', 'act_id': 'A'}])
    return outer, inner


def test_registry_scope_exact_rows_and_recursive_typed_body_closure(tmp_path):
    outer, inner = fixture(tmp_path)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result = m.build(tmp_path, 'first')
    assert result['export_ready'] is False
    assert result['registry_selection']['selected_row']['project_dir'] == 'projects/first'
    ids = {r['id'] for r in result['selected_rows']}
    assert {'WS1', 'WT1', 'READ1', 'WO1'} <= ids
    assert not {'OTHER', 'UNRELATED', 'WO2'} & ids
    banks = [r for r in result['selected_rows'] if r['record'] == 'bank']
    assert len(banks) == 1
    assert {r['sha256'] for r in result['public_body_refs']} == {outer['content_handle'], inner['content_handle']}
    assert result['missing_public_bodies'] == []  # Ordinary 64-character hashes are not refs.
    assert all(p['path'].endswith('.py') for p in result['groups']['engine_python_candidates'])
    project_paths = {r['path'] for r in result['groups']['selected_project']}
    assert 'projects/first/text/main.tex' in project_paths
    assert not any('.env' in p or '.claude' in p or 'projects/second' in p for p in project_paths)
    assert len(result['scientific_source_dependencies']) == 2
    assert {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == before


def test_two_project_manifest_shares_scans_and_deduplicates_original_rows(tmp_path, monkeypatch):
    fixture(tmp_path)
    calls = {}
    original = m._rows
    def observed(root, relative):
        calls[relative] = calls.get(relative, 0) + 1
        return original(root, relative)
    monkeypatch.setattr(m, '_rows', observed)
    result = m.build_many(tmp_path, ['first', 'second'])
    assert result['schema'] == 'laplace.writing-evaluation-manifest/3'
    assert result['projects'] == ['first', 'second']
    assert calls['contract/talk.jsonl'] == 1 and calls['contract/journal.jsonl'] == 1
    ids = [row['id'] for row in result['selected_rows']]
    assert {'WS1', 'WT1', 'READ1', 'WS2', 'WT2', 'OTHER'} <= set(ids)
    assert [row['record'] for row in result['selected_rows']].count('act') == 1
    assert [row['record'] for row in result['selected_rows']].count('act_end') == 1
    assert len(result['public_body_refs']) == 3
    for project in ['first', 'second']:
        assert 'selected_rows' not in result['project_manifests'][project]
        assert m.project_rows(result, project) == m.build(tmp_path, project)['selected_rows']


def test_selected_banks_accept_exact_root_absolute_paths_without_rewriting_history(tmp_path):
    outer, inner = fixture(tmp_path)
    bank_body = blob(tmp_path, {'detail': 'Only reachable through the absolute bank.'})
    entries = [
        {'record': 'act', 'act_id': 'relative'},
        {'record': 'bank', 'act_id': 'relative', 'store': 'contract/talk.jsonl', 'row_id': 'READ1'},
        {'record': 'act_end', 'act_id': 'relative'},
        {'record': 'act', 'act_id': 'absolute'},
        {'record': 'bank', 'act_id': 'absolute',
         'store': str(tmp_path / 'corpus_friction/work_orders.jsonl'), 'row_id': 'WO1', 'body': bank_body},
        {'record': 'bank', 'act_id': 'absolute',
         'store': str(tmp_path / 'contract/talk.jsonl'), 'row_id': 'READ1'},
        {'record': 'act_end', 'act_id': 'absolute'},
        {'record': 'bank', 'act_id': 'foreign',
         'store': str(tmp_path.parent / 'other-root/corpus_friction/work_orders.jsonl'), 'row_id': 'WO1'},
        {'record': 'bank', 'act_id': 'prefix-lookalike',
         'store': str(tmp_path.with_name(tmp_path.name + '-lookalike') / 'corpus_friction/work_orders.jsonl'),
         'row_id': 'WO1'},
        {'record': 'bank', 'act_id': 'traversal',
         'store': 'contract/../corpus_friction/work_orders.jsonl', 'row_id': 'WO1'},
        {'record': 'bank', 'act_id': 'absolute-traversal',
         'store': str(tmp_path / 'contract/../corpus_friction/work_orders.jsonl'), 'row_id': 'WO1'},
        {'record': 'bank', 'act_id': 'other-project',
         'store': str(tmp_path / 'corpus_friction/work_orders.jsonl'), 'row_id': 'WO2'},
        {'record': 'bank', 'act_id': 'malformed', 'store': {'path': 'contract/talk.jsonl'}, 'row_id': 'READ1'},
    ]
    path = rows(tmp_path, 'contract/journal.jsonl', entries)
    before = path.read_bytes()
    result = m.build(tmp_path, 'first')
    selected = [row for row in result['selected_rows'] if row['file'] == 'contract/journal.jsonl']
    assert [row['line'] for row in selected] == [1, 2, 3, 4, 5, 6, 7]
    raw_lines = before.splitlines(keepends=True)
    assert [row['row_sha256'] for row in selected] == [m._sha(line) for line in raw_lines[:7]]
    assert path.read_bytes() == before
    assert {row['sha256'] for row in result['public_body_refs']} == {
        outer['content_handle'], inner['content_handle'], bank_body['content_handle']}


@pytest.mark.parametrize('indices', [[-1], [999], [True], [0, 0], [1, 0]])
def test_project_history_selection_rejects_invalid_indices(indices):
    value={'selected_rows':[{},{}], 'project_manifests':{'p':{'selected_row_indices':indices}}}
    with pytest.raises(m.ManifestError, match='history row selection'):
        m.project_rows(value,'p')


def test_required_project_closure_fails_explicitly(tmp_path):
    fixture(tmp_path)
    (tmp_path / 'projects/second/text/main.pdf').unlink()
    with pytest.raises(m.ManifestError, match='build_pdf'):
        m.build_many(tmp_path, ['first', 'second'])


def test_project_without_executable_producers_preserves_owner_empty_state(tmp_path):
    fixture(tmp_path)
    path=tmp_path/'projects/second/text/research_producers.json'
    path.unlink()
    from laplace.research import research_catalogue
    assert research_catalogue.state_payload('second',tmp_path)['producers']==[]
    result=m.build_many(tmp_path,['first','second'])
    assert 'research_producers' not in result['project_manifests']['second']['required_project_files']
    assert not path.exists()


def test_missing_and_corrupt_body_are_not_replaced_by_external_state(tmp_path):
    outer, inner = fixture(tmp_path)
    digest = inner['content_handle'].split(':')[1]
    p = tmp_path / 'contract/writing_bodies' / digest[:2] / digest
    p.unlink()
    result = m.build(tmp_path, 'first')
    assert [r['content_handle'] for r in result['missing_public_bodies']] == [inner['content_handle']]
    p.write_bytes(b'wrong bytes')
    with pytest.raises(m.ManifestError, match='hash mismatch'):
        m.build(tmp_path, 'first')


def test_conventional_registry_includes_research_and_numerics_siblings(tmp_path):
    fixture(tmp_path)
    write(tmp_path, 'registry_projects.json', {'projects': [
        {'name': 'first', 'tex_root': 'synthetics papers/first/manuscript'}]})
    for relative in ['manuscript/main.tex', 'manuscript/main.pdf',
                     'manuscript/projection_plan.json', 'manuscript/references.json',
                     'manuscript/research_records.json', 'manuscript/research_producers.json',
                     'manuscript/figure_manifest.json', 'numerics/experiment.py',
                     'research/receipt.json']:
        write(tmp_path, 'synthetics papers/first/' + relative, '{}' if relative.endswith('.json') else 'source')
    result = m.build(tmp_path, 'first')
    paths = {r['path'] for r in result['groups']['selected_project']}
    assert result['registry_selection']['resolved_project_dir'] == 'synthetics papers/first'
    assert 'synthetics papers/first/numerics/experiment.py' in paths
    assert 'synthetics papers/first/research/receipt.json' in paths


def test_parent_symlink_and_traversing_registry_are_refused(tmp_path):
    fixture(tmp_path)
    (tmp_path / 'alias').symlink_to(tmp_path / 'projects', target_is_directory=True)
    data = json.loads((tmp_path / 'registry_projects.json').read_text())
    data['projects'][0]['project_dir'] = 'alias/first'
    write(tmp_path, 'registry_projects.json', data)
    with pytest.raises(m.ManifestError, match='symlink'):
        m.build(tmp_path, 'first')
    data['projects'][0]['project_dir'] = '../outside'
    write(tmp_path, 'registry_projects.json', data)
    with pytest.raises(m.ManifestError, match='unsafe relative'):
        m.build(tmp_path, 'first')


def test_unknown_project_and_malformed_ledger_are_not_silently_ignored(tmp_path):
    fixture(tmp_path)
    with pytest.raises(m.ManifestError, match='registered project'):
        m.build(tmp_path, 'unknown')
    write(tmp_path, 'contract/talk.jsonl', '{broken json\n')
    with pytest.raises(m.ManifestError, match='malformed journal'):
        m.build(tmp_path, 'first')


def test_explicit_manifest_output_cannot_overwrite_an_input(tmp_path, capsys):
    fixture(tmp_path)
    path = tmp_path / 'registry_projects.json'
    before = path.read_bytes()
    assert m.main(['--repo-root', str(tmp_path), '--project', 'first', '--output', str(path)]) == 2
    assert path.read_bytes() == before
    assert 'overwrite an input' in capsys.readouterr().out
