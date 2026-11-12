import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('export_writing_evaluation', Path(__file__).parents[1] / 'scripts/export_writing_evaluation.py')
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)
VERIFY_SPEC = importlib.util.spec_from_file_location('verify_writing_evaluation', Path(__file__).parents[1] / 'scripts/verify_writing_evaluation.py')
verifier = importlib.util.module_from_spec(VERIFY_SPEC)
VERIFY_SPEC.loader.exec_module(verifier)
from test_writing_eval_manifest import fixture, write



def _proofs(export):
    """The alias proofs an export carries beside its portability index (release/alias-proofs.json, pinned by it)."""
    index = json.loads((export / 'writing-portability.json').read_text())['alias_proofs']
    carried = json.loads((export / index['path']).read_text())
    assert len(carried['proofs']) == index['count']
    return carried['proofs']

def test_export_preserves_exact_rows_and_bodies_without_unrelated_state(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    outer, inner = fixture(root)
    write(root, 'soul/private.txt', 'PRIVATE_NEVER_COPY')
    write(root, 'AGENTS.md', 'PRIVATE_STARTUP_INSTRUCTIONS')
    entry = write(root, 'docs/writing-evaluator-agents.md',
                  'Portable entry: read docs/writing-agent-start.md before bounded work.\n')
    write(root, '.codex/auth.json', 'PRIVATE_TOKEN')
    source = write(root, 'projects/first/text/source.txt', 'included source')
    refs = json.loads((root / 'projects/first/text/references.json').read_text())
    refs['sources'][0]['source']['path'] = '/historical/root/projects/first/text/source.txt'
    write(root, 'projects/first/text/references.json', refs)
    target = tmp_path / 'export'
    result = exporter.export(root, target, 'first')
    assert result['imported_sessions'] == 1
    assert not (target / 'soul').exists()
    assert 'PRIVATE_STARTUP_INSTRUCTIONS' not in (target / 'AGENTS.md').read_text()
    assert (target / 'AGENTS.md').read_bytes() == entry.read_bytes()
    assert (target / 'docs/writing-evaluator-agents.md').read_bytes() == entry.read_bytes()
    assert not (target / '.codex').exists()
    assert not (target / 'projects/second').exists()
    rows = [json.loads(x) for x in (target / 'contract/talk.jsonl').read_text().splitlines()]
    assert rows[-1]['record'] == 'writing-session-import'
    assert {x['id'] for x in rows[:-1]} == {'WS1', 'WT1', 'READ1'}
    for ref in [outer, inner]:
        sha = ref['content_handle'].split(':')[1]
        rel = 'contract/writing_bodies/' + sha[:2] + '/' + sha
        assert (target / rel).read_bytes() == (root / rel).read_bytes()
    source_rows = (root / 'contract/talk.jsonl').read_bytes().splitlines(keepends=True)
    assert (target / 'contract/talk.jsonl').read_bytes().startswith(b''.join(source_rows[:3]))
    portable = json.loads((target / 'writing-portability.json').read_text())
    alias = portable['source_aliases']['/historical/root/projects/first/text/source.txt']
    assert alias['path'] == 'projects/first/text/source.txt'
    assert alias['original_sha256'] == exporter.digest(source.read_bytes())


def test_two_project_export_keeps_one_runtime_cas_and_scoped_imports(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    write(root, 'projects/first/text/source.txt', 'included source')
    references = json.loads((root / 'projects/first/text/references.json').read_text())
    references['sources'][0]['source']['path'] = '/historical/root/projects/first/text/source.txt'
    write(root, 'projects/first/text/references.json', references)
    target = tmp_path / 'export'
    result = exporter.export_projects(root, target, ['first', 'second'])
    assert result['schema'] == 'laplace.writing-evaluation-export/2'
    assert result['projects'] == ['first', 'second']
    assert result['history_scope'].startswith('union of exact per-project selections')
    assert result['imported_sessions_by_project'] == {'first': 1, 'second': 1}
    registry = json.loads((target / 'registry_projects.json').read_text())
    assert [row['name'] for row in registry['projects']] == ['first', 'second']
    assert (target / 'projects/first/text/main.tex').is_file()
    assert (target / 'projects/second/text/main.tex').is_file()
    rows = [json.loads(line) for line in (target / 'contract/talk.jsonl').read_text().splitlines()]
    original = [row for row in rows if row.get('record') != 'writing-session-import']
    assert [row.get('id') for row in original[:6]] == ['WS1', 'WT1', 'READ1', 'WS2', 'WT2', 'OTHER']
    imports = [row for row in rows if row.get('record') == 'writing-session-import']
    assert {(row['session_id'], row['project']) for row in imports} == {
        ('WS1', 'first'), ('WS2', 'second')}
    portable = json.loads((target / 'writing-portability.json').read_text())
    assert portable['projects'] == ['first', 'second']
    body_files = list((target / 'contract/writing_bodies').glob('*/*'))
    assert len(body_files) == 3  # shared CAS, each reachable body copied once
    verified = verifier.verify(target)
    assert verified['ok'], verified['failures']
    assert set(verified['per_project']) == {'first', 'second'}


def test_import_scope_refuses_wrong_project_and_unknown_session():
    projects = ['first', 'second']
    sessions = {'WS1': 'first', 'WS2': 'second'}
    assert verifier.import_scope([
        {'session_id': 'WS1', 'project': 'first'},
        {'session_id': 'WS2', 'project': 'second'}], sessions, projects) == []
    failures = verifier.import_scope([
        {'session_id': 'WS1', 'project': 'second'},
        {'session_id': 'MISSING', 'project': 'first'}], sessions, projects)
    assert len(failures) == 2 and all(row['reason'] == 'session import crosses project boundary'
                                      for row in failures)


def test_source_manifest_identity_and_selection_are_verified(tmp_path):
    root=tmp_path/'source';root.mkdir();fixture(root)
    write(root,'projects/first/text/source.txt','included source')
    references=json.loads((root/'projects/first/text/references.json').read_text())
    references['sources'][0]['source']['path']='/historical/root/projects/first/text/source.txt'
    write(root,'projects/first/text/references.json',references)
    target=tmp_path/'out';exporter.export_projects(root,target,['first','second'])
    source=target/'release/source-manifest.json'
    manifest=json.loads(source.read_text())
    manifest['project_manifests']['first']['selected_row_indices']=[len(manifest['selected_rows'])]
    source.write_text(json.dumps(manifest))
    result=verifier.verify(target)
    assert any(x['reason']=='source manifest identity mismatch' for x in result['failures'])
    # Even a newly declared hash cannot make an invalid row reference meaningful.
    report_path=target/'release/export-manifest.json'
    report=json.loads(report_path.read_text());report['source_manifest_sha256']=verifier.sha(source)
    report_path.write_text(json.dumps(report))
    result=verifier.verify(target)
    assert any('invalid project history row selection' in x['reason'] for x in result['failures'])


@pytest.mark.parametrize('missing', ['docs/writing-container.md', 'docs/writing-evaluator-agents.md'])
def test_export_refuses_missing_required_release_document(tmp_path, missing):
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    (root / missing).unlink()
    with pytest.raises(ValueError, match='required release input missing'):
        exporter.export_projects(root, tmp_path / 'out', ['first', 'second'])


def test_historical_alias_proof_refuses_ambiguous_escape_missing_and_hash_mismatch(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    rel = 'projects/first/text/source.txt'; path = write(root, rel, 'proof')
    row = {'path': rel, 'bytes': path.stat().st_size, 'sha256': exporter.digest(path.read_bytes())}
    manifest = {'registry_selection': {'resolved_project_dir': 'projects/first'},
                'groups': {'selected_project': []}}
    assert exporter._project_relative_absolute('/old/projects/first/text/source.txt', 'projects/first') == rel
    with pytest.raises(ValueError, match='unique canonical'):
        exporter._project_relative_absolute('/old/projects/first/archive/projects/first/x', 'projects/first')
    with pytest.raises(Exception, match='unsafe relative'):
        exporter.inventory._safe(root, 'projects/first/../escape')
    refs = write(root, 'projects/first/text/references.json', {'path': '/old/projects/first/text/missing.txt'})
    manifest['groups']['selected_project'] = [{'path': refs.relative_to(root).as_posix()}]
    with pytest.raises(ValueError, match='target missing'):
        exporter._historical_aliases(root, manifest, {rel: row})
    bad = '0' * 64 + '.txt'; bad_path = write(root, 'projects/first/text/' + bad, 'not matching')
    refs.write_text(json.dumps({'path': '/old/projects/first/text/' + bad}))
    bad_rel = bad_path.relative_to(root).as_posix()
    bad_row = {'path': bad_rel, 'bytes': bad_path.stat().st_size,
               'sha256': exporter.digest(bad_path.read_bytes())}
    with pytest.raises(ValueError, match='hash mismatch'):
        exporter._historical_aliases(root, manifest, {bad_rel: bad_row})


def test_recorded_sibling_hashes_bind_project_and_explicit_supplementary_bytes(tmp_path):
    root=tmp_path/'source';root.mkdir();fixture(root)
    rel='projects/first/text/source.txt';path=write(root,rel,'actual bytes')
    row={'path':rel,'bytes':path.stat().st_size,'sha256':exporter.digest(path.read_bytes())}
    refs=write(root,'projects/first/text/references.json',{
        'path':'/old/projects/first/text/source.txt','sha256':'sha256:'+'0'*64})
    manifest={'registry_selection':{'resolved_project_dir':'projects/first'},
              'groups':{'selected_project':[{'path':refs.relative_to(root).as_posix()}]}}
    with pytest.raises(ValueError,match='recorded source hash mismatch'):
        exporter._historical_aliases(root,manifest,{rel:row})
    refs.write_text(json.dumps({'path':'/old/projects/first/text/source.txt','sha256':'not-a-sha'}))
    with pytest.raises(ValueError,match='malformed recorded sha256'):
        exporter._historical_aliases(root,manifest,{rel:row})
    outside=tmp_path/'outside.pdf';outside.write_bytes(b'outside')
    refs.write_text(json.dumps({'source_path':str(outside),'source_sha256':'sha256:'+'0'*64}))
    with pytest.raises(ValueError,match='recorded source hash mismatch'):
        exporter._historical_aliases(root,manifest,{rel:row},
            {str(outside):exporter.digest(outside.read_bytes())})


def selected_repository_reference(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    rel = 'docs/writing-engine-walkthrough.md'
    source = write(root, rel, 'Current selected public walkthrough.\n')
    pin = exporter.digest(source.read_bytes())
    refs = write(root, 'projects/first/text/references.json', {'associations': [{
        'metadata': {'provenance': {'path': str(source), 'sha256': pin}},
        'reading_observations': [{'source_path': str(source), 'source_sha256': pin}],
    }]})
    manifest = {'registry_selection': {'resolved_project_dir': 'projects/first'},
                'groups': {'selected_project': [{'path': refs.relative_to(root).as_posix()}]}}
    return root, source, refs, manifest, {rel: exporter.inventory._file_record(root, source)}


def test_selected_repository_reference_exports_exact_alias_without_duplicate_input(tmp_path):
    root, source, refs, _, _ = selected_repository_reference(tmp_path)
    original = refs.read_bytes()
    target = tmp_path / 'export'
    exporter.export(root, target, 'first')
    portable = json.loads((target / 'writing-portability.json').read_text())
    alias = portable['source_aliases'][str(source)]
    assert alias['path'] == 'docs/writing-engine-walkthrough.md'
    assert alias['original_sha256'] == exporter.digest(source.read_bytes())
    assert alias['proof'] == 'exact selected current-root address and recorded source pin'
    proofs = [p for p in _proofs(target) if p['recorded'] == str(source)]
    assert len(proofs) == 2
    assert all(p['recorded_sha256'] == alias['original_sha256'] for p in proofs)
    assert (target / refs.relative_to(root)).read_bytes() == original == refs.read_bytes()
    assert (target / alias['path']).read_bytes() == source.read_bytes()
    assert verifier.verify(target)['ok']


@pytest.mark.parametrize('fault, error', [
    ('missing-hash', 'requires recorded hash'),
    ('old-hash', 'recorded source hash mismatch'),
    ('changed-bytes', 'selected source bytes changed'),
    ('unselected', 'unique canonical project anchor'),
    ('foreign', 'unique canonical project anchor'),
    ('root-prefix', 'unique canonical project anchor'),
    ('traversal', 'unsafe current-root source path'),
    ('private', 'private or runtime source alias'),
    ('symlink', 'symlink input refused'),
])
def test_selected_repository_reference_refuses_unproved_targets(tmp_path, fault, error):
    root, source, refs, manifest, candidates = selected_repository_reference(tmp_path)
    value = json.loads(refs.read_text())
    provenance = value['associations'][0]['metadata']['provenance']
    value['associations'][0].pop('reading_observations')
    if fault == 'missing-hash':
        provenance.pop('sha256')
    elif fault == 'old-hash':
        provenance['sha256'] = 'sha256:' + '0' * 64
    elif fault == 'changed-bytes':
        source.write_bytes(b'Later source must not be silently repinned.')
    elif fault == 'unselected':
        candidates.clear()
    elif fault == 'foreign':
        provenance['path'] = str(tmp_path / 'foreign' / source.name)
    elif fault == 'root-prefix':
        provenance['path'] = str(root.with_name(root.name + '-foreign') / source.name)
    elif fault == 'traversal':
        provenance['path'] = str(root / 'docs' / '..' / 'docs' / source.name)
    elif fault == 'private':
        private = write(root, 'soul/private.md', 'Not public.')
        provenance.update(path=str(private), sha256=exporter.digest(private.read_bytes()))
        candidates['soul/private.md'] = exporter.inventory._file_record(root, private)
    elif fault == 'symlink':
        outside = write(tmp_path, 'outside.md', 'Not the selected bytes.')
        source.unlink(); source.symlink_to(outside)
    refs.write_text(json.dumps(value))
    with pytest.raises(ValueError, match=error):
        exporter._historical_aliases(root, manifest, candidates)


def test_historical_runtime_observations_are_not_source_alias_inputs(tmp_path):
    root, _, refs, manifest, candidates = selected_repository_reference(tmp_path)
    refs.write_text('{}')
    job = write(root, 'projects/first/research_runs/run-observation.result.json', {
        'atlas': {'source_modules': [{'path': '/old/runtime/module.py', 'sha256': '0' * 64}]},
        'runtime_imports': [{'path': '/old/runtime/other.py', 'sha256': '1' * 64}],
    })
    manifest['groups']['selected_project'].append({'path': job.relative_to(root).as_posix()})
    assert exporter._historical_aliases(root, manifest, candidates) == ({}, [])


def test_optional_result_state_is_scoped_to_its_own_job_occurrence(tmp_path):
    root=tmp_path/'source';root.mkdir();fixture(root)
    shared='/old/projects/first/research_runs/shared.result.json'
    paths=[]
    for name in ('a','b'):
        p=write(root,f'projects/first/research_runs/run-{name}.json',{
            'producer_base':'/old/projects/first','result_absolute':shared})
        paths.append({'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,
                      'sha256':exporter.digest(p.read_bytes())})
    write(root,'projects/first/research_runs/run-a.receipt.json',{'state':'FAILED'})
    manifest={'registry_selection':{'resolved_project_dir':'projects/first'},
              'groups':{'selected_project':paths}}
    candidates={row['path']:row for row in paths}
    with pytest.raises(ValueError,match='historical target missing'):
        exporter._historical_aliases(root,manifest,candidates)
    write(root,'projects/first/research_runs/run-b.receipt.json',{'state':'STALE'})
    with pytest.raises(ValueError,match='historical target missing'):
        exporter._historical_aliases(root,manifest,candidates)


def test_export_refuses_existing_destination_and_unpinned_external_source(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    fixture(root)
    with pytest.raises(ValueError, match='new directory'):
        exporter.export(root, root / 'export', 'first')
    outside = tmp_path / 'paper.pdf'
    outside.write_bytes(b'author paper')
    with pytest.raises(ValueError, match='changed'):
        exporter.export(root, tmp_path / 'out', 'first', [{'path': str(outside), 'sha256': 'sha256:bad', 'reason': 'test'}])
    assert not (tmp_path / 'out').exists()


def test_export_refuses_explicit_source_that_conflicts_with_proven_project_alias(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    source = write(root, 'projects/first/text/source.pdf', 'same project source')
    refs = json.loads((root / 'projects/first/text/references.json').read_text())
    refs['sources'][0]['source']['path'] = str(source.resolve())
    write(root, 'projects/first/text/references.json', refs)
    pinned = {'path': str(source), 'sha256': exporter.digest(source.read_bytes()),
              'reason': 'plant a conflicting supplementary destination'}
    with pytest.raises(ValueError, match='conflicting explicit and historical alias'):
        exporter.export(root, tmp_path / 'out-conflict', 'first', [pinned])


def test_repository_scope_resolves_relative_paths_and_refuses_escape(tmp_path):
    (tmp_path / 'profiles').mkdir(); (tmp_path / 'supplementary_sources').mkdir()
    (tmp_path / 'profiles/writing_sources.json').write_text(json.dumps({
        'repositories': {'laplace': '.', 'supplementary': 'supplementary_sources'}}))
    rows, failures = verifier.repository_scope(tmp_path)
    assert failures == [] and all(row['inside_export'] and row['available'] for row in rows)
    (tmp_path / 'profiles/writing_sources.json').write_text(json.dumps({
        'repositories': {'escape': '../private'}}))
    rows, failures = verifier.repository_scope(tmp_path)
    assert rows[0]['inside_export'] is False and failures[0]['id'] == 'escape'
    (tmp_path / 'profiles/writing_sources.json').write_text(json.dumps({
        'repositories': {'laplace': 'missing-main', 'supplementary': 'missing-extra'}}))
    rows, failures = verifier.repository_scope(tmp_path)
    assert next(row for row in rows if row['id']=='supplementary')['optional'] is True
    assert failures == [{'reason':'required source repository missing','id':'laplace',
                         'declared':'missing-main'}]


def test_missing_result_is_optional_only_with_explicit_terminal_failure_receipt(tmp_path):
    root=tmp_path/'source';root.mkdir();fixture(root)
    rel='projects/first/research_runs/run-x.json'
    job=write(root,rel,{'producer_base':'/old/projects/first',
                        'result_absolute':'/old/projects/first/research_runs/run-x.result.json'})
    row={'path':rel,'bytes':job.stat().st_size,'sha256':exporter.digest(job.read_bytes())}
    manifest={'registry_selection':{'resolved_project_dir':'projects/first'},
              'groups':{'selected_project':[row]}}
    with pytest.raises(ValueError,match='target missing'):
        exporter._historical_aliases(root,manifest,{rel:row})
    write(root,'projects/first/research_runs/run-x.receipt.json',{'state':'FAILED'})
    aliases,proofs=exporter._historical_aliases(root,manifest,{rel:row})
    assert aliases['/old/projects/first/research_runs/run-x.result.json']['path'].endswith('run-x.result.json')
    assert any(p['availability']=='absent-optional' for p in proofs)
    (root/'projects/first/research_runs/run-x.receipt.json').write_text('{broken')
    with pytest.raises(json.JSONDecodeError):
        exporter._historical_aliases(root,manifest,{rel:row})
    write(root,'projects/first/research_runs/run-x.receipt.json',{'state':'STALE'})
    with pytest.raises(ValueError,match='target missing'):
        exporter._historical_aliases(root,manifest,{rel:row})


@pytest.mark.parametrize('prefix', ['', 'sha256:'])
@pytest.mark.parametrize('uppercase', [False, True])
@pytest.mark.parametrize('supplementary', [False, True])
@pytest.mark.parametrize('path_key,hash_key', [
    ('path', 'sha256'), ('source_path', 'source_sha256'),
])
def test_recorded_hash_spellings_bind_exported_bytes(
        tmp_path, prefix, uppercase, supplementary, path_key, hash_key):
    root = tmp_path / 'source'
    root.mkdir()
    fixture(root)
    source = (write(tmp_path, 'supplement.pdf', 'exact supplementary bytes')
              if supplementary else
              write(root, 'projects/first/text/source.txt', 'exact project bytes'))
    actual = exporter.digest(source.read_bytes())
    raw = actual[7:].upper() if uppercase else actual[7:]
    refs = write(root, 'projects/first/text/references.json', {
        'associations': [{'source_refs': [{path_key: str(source), hash_key: prefix + raw}]}],
    })
    original = refs.read_bytes()
    extras = ([{'path': str(source), 'sha256': actual, 'reason': 'test fixture'}]
              if supplementary else [])
    target = tmp_path / 'export'
    exporter.export_projects(root, target, ['first', 'second'], extras)
    portable = json.loads((target / 'writing-portability.json').read_text())
    alias = portable['source_aliases'][str(source)]
    assert alias['original_sha256'] == actual
    assert (target / alias['path']).read_bytes() == source.read_bytes()
    proofs = [row for row in _proofs(target) if row.get('recorded') == str(source)]
    assert proofs and all(row['recorded_sha256'] == actual for row in proofs)
    assert refs.read_bytes() == original
    assert (target / 'projects/first/text/references.json').read_bytes() == original


@pytest.mark.parametrize('prefix', ['', 'sha256:'])
@pytest.mark.parametrize('supplementary', [False, True])
def test_valid_unequal_recorded_hash_still_refuses_export(tmp_path, prefix, supplementary):
    root = tmp_path / 'source'
    root.mkdir()
    fixture(root)
    source = (write(tmp_path, 'supplement.pdf', 'actual supplementary bytes')
              if supplementary else
              write(root, 'projects/first/text/source.txt', 'actual project bytes'))
    actual = exporter.digest(source.read_bytes())
    wrong = ('0' if actual[7] != '0' else '1') + actual[8:]
    write(root, 'projects/first/text/references.json', {
        'source_path': str(source), 'source_sha256': prefix + wrong,
    })
    extras = ([{'path': str(source), 'sha256': actual, 'reason': 'test fixture'}]
              if supplementary else [])
    target = tmp_path / 'export'
    with pytest.raises(ValueError, match='recorded source hash mismatch'):
        exporter.export_projects(root, target, ['first', 'second'], extras)
    assert not target.exists()


@pytest.mark.parametrize('path_key,hash_key', [
    ('path', 'sha256'), ('source_path', 'source_sha256'),
])
@pytest.mark.parametrize('bad', [
    None, True, 42, 1.5, [], {}, '', 'a' * 63, 'a' * 65, 'g' * 64,
    ' ' + 'a' * 64, 'a' * 64 + ' ', 'a' * 64 + '\n', '\t' + 'a' * 64,
    'sha256:' + 'a' * 63, 'sha256:' + 'a' * 65, 'sha256:' + 'g' * 64,
    'sha256: ' + 'a' * 64, 'sha256:' + 'a' * 64 + '\n',
    'SHA256:' + 'a' * 64, 'sha1:' + 'a' * 64,
    'sha256:sha256:' + 'a' * 64,
])
def test_recorded_hash_rejects_malformed_present_values(path_key, hash_key, bad):
    with pytest.raises(ValueError, match='malformed recorded ' + hash_key):
        exporter._recorded_path_hash({hash_key: bad}, path_key)


def test_absent_recorded_hash_remains_optional():
    assert exporter._recorded_path_hash({}, 'path') is None
    assert exporter._recorded_path_hash({}, 'source_path') is None


def supplementary_fixture(tmp_path, relative='evidence/scoped-review.json'):
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    write(root, 'projects/first/text/references.json', {'associations': []})
    source = root / relative
    if not source.is_file():
        source = write(root, relative, '{"status":"public controlled fixture"}\n')
    entry = {'path': str(source), 'sha256': exporter.digest(source.read_bytes()),
             'reason': 'Selected public release review', 'repository_path': relative}
    return root, source, entry


def test_explicit_public_companion_preserves_actual_qualified_repository_read(tmp_path):
    from laplace.projects import writing_sources
    root, source, entry = supplementary_fixture(tmp_path)
    original = source.read_bytes()
    default = tmp_path / 'default'
    exporter.export(root, default, 'first', [{k: v for k, v in entry.items() if k != 'repository_path'}])
    read = {'action': 'read', 'repository': 'laplace', 'path': entry['repository_path']}
    with pytest.raises(ValueError, match='Source path does not exist'):
        writing_sources.execute(default, read)
    target = tmp_path / 'qualified'
    report = exporter.export(root, target, 'first', [entry])
    result = writing_sources.execute(target, read)
    assert (target / entry['repository_path']).read_bytes() == original
    assert result['content'].encode() == original
    assert 'sha256:' + result['source']['sha256'] == entry['sha256']
    assert report['selected_supplementary_sources'] == [{
        'path': entry['repository_path'], 'sha256': entry['sha256'],
        'reason': entry['reason'], 'selection': 'qualified-repository-path'}]
    assert verifier.verify(target)['ok']


@pytest.mark.parametrize('bad', ['../scoped-review.json', 'evidence/../scoped-review.json',
                               '/evidence/scoped-review.json', 'other.json', '', 42])
def test_supplementary_repository_address_refuses_traversal_or_renaming(tmp_path, bad):
    root, _, entry = supplementary_fixture(tmp_path)
    target = tmp_path / 'out'
    with pytest.raises(ValueError, match='exact repo-relative spelling'):
        exporter.export(root, target, 'first', [{**entry, 'repository_path': bad}])
    assert not target.exists()


@pytest.mark.parametrize('relative', ['src/laplace/app.py', 'projects/first/text/main.tex',
                                    'registry_projects.json', 'README.md', 'contract/talk.jsonl'])
def test_supplementary_repository_address_refuses_release_collision(tmp_path, relative):
    root, _, entry = supplementary_fixture(tmp_path, relative)
    target = tmp_path / 'out'
    with pytest.raises(ValueError, match='collides with release input'):
        exporter.export(root, target, 'first', [entry])
    assert not target.exists()


def test_supplementary_repository_address_refuses_duplicate_and_changed_bytes(tmp_path):
    root, _, entry = supplementary_fixture(tmp_path)
    target = tmp_path / 'out'
    with pytest.raises(ValueError, match='destinations collide'):
        exporter.export(root, target, 'first', [entry, entry])
    assert not target.exists()
    with pytest.raises(ValueError, match='supplementary source changed'):
        exporter.export(root, target, 'first', [{**entry, 'sha256': 'sha256:' + '0' * 64}])
    assert not target.exists()


@pytest.mark.parametrize('relative', ['soul/private.md', '.laplace-state/status.json'])
def test_supplementary_repository_address_refuses_private_runtime_namespaces(tmp_path, relative):
    root, _, entry = supplementary_fixture(tmp_path, relative)
    target = tmp_path / 'out'
    with pytest.raises(ValueError, match='private or runtime'):
        exporter.export(root, target, 'first', [entry])
    assert not target.exists()


def test_supplementary_repository_address_refuses_external_file(tmp_path):
    root, _, entry = supplementary_fixture(tmp_path)
    external = tmp_path / 'outside.json'; external.write_text('Explicit outside bytes')
    target = tmp_path / 'out'
    with pytest.raises(ValueError, match='exact repo-relative spelling'):
        exporter.export(root, target, 'first', [{**entry, 'path': str(external),
            'sha256': exporter.digest(external.read_bytes())}])
    assert not target.exists()


@pytest.mark.parametrize('qualified_first', [False, True])
def test_supplementary_repository_address_cannot_overwrite_hashed_supplement(tmp_path, qualified_first):
    root, _, _ = supplementary_fixture(tmp_path)
    outside = tmp_path / 'outside.json'; outside.write_text('Other selected bytes')
    pin = exporter.digest(outside.read_bytes())
    relative = 'supplementary_sources/' + pin.split(':')[1] + '.json'
    inside = write(root, relative, 'Different explicitly selected bytes')
    qualified = {'path': str(inside), 'sha256': exporter.digest(inside.read_bytes()),
                 'reason': 'Qualified fixture', 'repository_path': relative}
    hashed = {'path': str(outside), 'sha256': pin, 'reason': 'Hashed fixture'}
    entries = [qualified, hashed] if qualified_first else [hashed, qualified]
    target = tmp_path / 'out'
    with pytest.raises(ValueError, match='destinations collide'):
        exporter.export(root, target, 'first', entries)
    assert not target.exists()


def published_external_fixture(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    outside = tmp_path / 'original-public-report.json'
    outside.write_bytes(b'{"result":"public generic evidence"}\n')
    original = str(outside)
    write(root, 'projects/first/text/references.json', {
        'source_path': original, 'source_sha256': exporter.digest(outside.read_bytes())})
    target = tmp_path / 'published'
    exporter.export(root, target, 'first', [{'path': str(outside),
        'sha256': exporter.digest(outside.read_bytes()), 'reason': 'Selected generic public report'}])
    original_bytes = outside.read_bytes()
    outside.unlink()  # Relocation cannot consult or recover the original source.
    return target, original, original_bytes


def repin_portable_fixture(root, portable):
    write(root, 'writing-portability.json', portable)
    report = json.loads((root / 'release/export-manifest.json').read_text())
    for row in report['derived_files']:
        if row['path'] == 'writing-portability.json':
            row.update(exporter.inventory._file_record(root, root / row['path']))
    write(root, 'release/export-manifest.json', report)


def test_reexport_reuses_exact_published_source_without_original_access(tmp_path, monkeypatch):
    root, original, raw = published_external_fixture(tmp_path)
    refs = (root / 'projects/first/text/references.json').read_bytes()
    rows = (root / 'contract/talk.jsonl').read_bytes()
    portable = json.loads((root / 'writing-portability.json').read_text())
    alias = portable['source_aliases'][original]
    target = tmp_path / 'reexport'
    original_open = Path.open
    def confined_open(path, *args, **kwargs):
        assert path != Path(original), 'attempted read of original source'
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', confined_open)
    exporter.export(root, target, 'first')
    assert (target / alias['path']).read_bytes() == raw
    assert (target / 'projects/first/text/references.json').read_bytes() == refs
    assert (target / 'contract/talk.jsonl').read_bytes().startswith(rows)
    relocated = json.loads((target / 'writing-portability.json').read_text())
    assert relocated['source_aliases'][original]['original_sha256'] == alias['original_sha256']
    assert relocated['source_aliases'][original]['proof'].startswith('exact published')
    assert verifier.verify(target)['ok']


@pytest.mark.parametrize('fault', ['changed-bytes', 'moved-target', 'forged-alias',
    'outside-root', 'symlink-target', 'private-target', 'missing-pin', 'source-manifest',
    'conflicting-pin', 'directory-only'])
def test_reexport_refuses_unproven_published_alias(tmp_path, fault):
    root, original, raw = published_external_fixture(tmp_path)
    portable = json.loads((root / 'writing-portability.json').read_text())
    alias = portable['source_aliases'][original]
    if fault == 'changed-bytes':
        (root / alias['path']).write_bytes(b'changed')
    elif fault == 'moved-target':
        (root / alias['path']).rename(root / 'moved.json')
    elif fault == 'forged-alias':
        alias['path'] = 'projects/first/text/main.tex'
        write(root, 'writing-portability.json', portable)  # Unchanged published manifest pin.
    elif fault in {'outside-root', 'symlink-target', 'private-target', 'directory-only'}:
        if fault == 'outside-root':
            alias['path'] = '../outside.json'
        elif fault == 'symlink-target':
            outside = tmp_path / 'external-bytes'; outside.write_bytes(raw)
            path = root / alias['path']; path.unlink(); path.symlink_to(outside)
        elif fault == 'private-target':
            alias['path'] = 'soul/private.json'; write(root, alias['path'], raw.decode())
        else:
            portable['source_aliases'].pop(original)
            portable['directory_aliases'][str(Path(original).parent)] = 'supplementary_sources'
        repin_portable_fixture(root, portable)  # Exercise containment beneath provenance check.
    elif fault == 'source-manifest':
        (root / 'release/source-manifest.json').write_bytes(b'{}')
    else:
        report = json.loads((root / 'release/export-manifest.json').read_text())
        if fault == 'missing-pin':
            report['copied_files'] = [r for r in report['copied_files'] if r['path'] != alias['path']]
        else:
            row = next(r for r in report['copied_files'] if r['path'] == alias['path'])
            report['copied_files'].append({**row, 'sha256': 'sha256:' + '0' * 64})
        write(root, 'release/export-manifest.json', report)
    destination = tmp_path / 'refused'
    with pytest.raises((ValueError, FileNotFoundError)):
        exporter.export(root, destination, 'first')
    assert not destination.exists()


@pytest.mark.parametrize('original', [
    '/author/main/evidence/public/report.json',
    r'C:\author\main\evidence\public\report.json'])
def test_explicit_relocated_companion_preserves_original_receipt(tmp_path, original):
    root = tmp_path / 'composed'; root.mkdir(); fixture(root)
    companion = write(root, 'evidence/public/report.json', '{"public":"selected"}\n')
    pin = exporter.digest(companion.read_bytes())
    refs = write(root, 'projects/first/text/references.json', {
        'source_path': original, 'source_sha256': pin})
    entry = {'path': str(companion), 'repository_path': 'evidence/public/report.json',
             'recorded_path': original, 'sha256': pin, 'reason': 'Explicit public companion'}
    target = tmp_path / 'portable'
    result = exporter.export(root, target, 'first', [entry])
    assert (target / 'projects/first/text/references.json').read_bytes() == refs.read_bytes()
    from laplace.projects import writing_portability
    resolved = writing_portability.source_path(original, target)
    assert resolved == target / entry['repository_path']
    assert resolved.read_bytes() == companion.read_bytes()
    assert result['selected_supplementary_sources'][0]['recorded_path'] == original
    assert verifier.verify(target)['ok']
    exporter.export(target, tmp_path / 'reexport', 'first')
    assert writing_portability.source_path(original, tmp_path / 'reexport').read_bytes() == companion.read_bytes()


@pytest.mark.parametrize('recorded', ['evidence/public/report.json',
    '/author/evidence/public/../public/report.json', '/author/report.json',
    '/author/evidence/public/report.json/elsewhere',
    '/author/evidence/public/report.json/evidence/public/report.json',
    '/author/evidence/public/report.json\n', 42])
def test_explicit_relocated_companion_refuses_bad_original_spelling(tmp_path, recorded):
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    companion = write(root, 'evidence/public/report.json', 'public')
    entry = {'path': str(companion), 'repository_path': 'evidence/public/report.json',
             'recorded_path': recorded, 'sha256': exporter.digest(companion.read_bytes()),
             'reason': 'Explicit public companion'}
    destination = tmp_path / 'refused'
    with pytest.raises(ValueError, match='recorded_path'):
        exporter.export(root, destination, 'first', [entry])
    assert not destination.exists()


def test_explicit_relocated_companion_needs_repository_path(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    companion = write(root, 'evidence/public/report.json', 'public')
    with pytest.raises(ValueError, match='recorded_path'):
        exporter.export(root, tmp_path / 'out', 'first', [{
            'path': str(companion), 'recorded_path': '/author/evidence/public/report.json',
            'sha256': exporter.digest(companion.read_bytes()), 'reason': 'public'}])


def test_explicit_relocated_companions_refuse_conflicting_alias_targets(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    entries = []
    for rel in ('evidence/public/report.json', 'public/report.json'):
        path = write(root, rel, 'same exact selected bytes')
        entries.append({'path': str(path), 'repository_path': rel,
            'recorded_path': '/author/evidence/public/report.json',
            'sha256': exporter.digest(path.read_bytes()), 'reason': 'Selected public fixture'})
    target = tmp_path / 'refused'
    with pytest.raises(ValueError, match='conflicting explicit supplementary alias'):
        exporter.export(root, target, 'first', entries)
    assert not target.exists()


# ---- interim historical-citation export (2026-10-13): an original reading of a since-changed current file ----

def historical_reading_fixture(tmp_path):
    """A reference pins an ORIGINAL reading of a doc that is also a current release input."""
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    current = write(root, 'docs/writing-engine-walkthrough.md', '# Walkthrough v2\nThe current owner map.\n')
    original_bytes = b'# Walkthrough v1\nThe owner map as it was read.\n'
    original_sha = exporter.digest(original_bytes)
    captured = tmp_path / 'captured' / 'writing-engine-walkthrough.md'
    captured.parent.mkdir(); captured.write_bytes(original_bytes)
    recorded = str(root / 'docs/writing-engine-walkthrough.md')
    refs = write(root, 'projects/first/text/references.json', {'associations': [{
        'key': 'local:one', 'metadata': {'provenance': {'path': recorded, 'sha256': original_sha}},
        'reading_observations': [{'source_path': recorded, 'source_sha256': original_sha, 'offset': 2, 'length': 10}]}]})
    entry = {'path': str(captured), 'sha256': original_sha, 'recorded_path': recorded,
             'reason': 'Original engineering document bytes read by the architecture manuscript before the release docs changed'}
    return root, current, captured, original_bytes, original_sha, recorded, refs, entry


def test_original_reading_of_a_changed_current_file_exports_beside_it_and_resolves_by_pin(tmp_path):
    from laplace.projects import writing_portability
    from laplace.research import literature
    root, current, captured, original_bytes, original_sha, recorded, refs, entry = historical_reading_fixture(tmp_path)
    # without the explicit companion the export refuses exactly as the interim export did
    with pytest.raises(ValueError, match='recorded source hash mismatch'):
        exporter.export(root, tmp_path / 'refused', 'first', [])
    target = tmp_path / 'export'
    report = exporter.export(root, target, 'first', [entry])
    companion = 'supplementary_sources/' + original_sha.split(':')[-1] + '.md'
    assert (target / 'docs/writing-engine-walkthrough.md').read_bytes() == current.read_bytes(), 'the current doc stays current at its own path'
    assert (target / companion).read_bytes() == original_bytes, 'the original bytes travel beside it, content-addressed'
    assert (target / refs.relative_to(root)).read_bytes() == refs.read_bytes(), 'the reference is not rewritten'
    portable = json.loads((target / 'writing-portability.json').read_text())
    alias = portable['source_aliases'][recorded]
    assert alias['path'] == 'docs/writing-engine-walkthrough.md' and alias['original_sha256'] == exporter.digest(current.read_bytes())
    assert alias['versions'] == {original_sha: {'path': companion, 'original_sha256': original_sha, 'reason': entry['reason'],
                                                'basis': 'explicit pinned companion of an original reading; the current file keeps its own path'}}
    # resolution: the spelling alone is the current file; the spelling with its recorded pin is the original
    assert writing_portability.source_path(recorded, target) == (target / 'docs/writing-engine-walkthrough.md').resolve()
    assert writing_portability.source_path(recorded, target, sha256=original_sha) == (target / companion).resolve()
    assert writing_portability.source_path(recorded, target, sha256='sha256:' + 'f' * 64) == (target / 'docs/writing-engine-walkthrough.md').resolve(), 'an unknown pin falls back to the primary; the reader compares hashes itself'
    assert literature.local_path(recorded, target, original_sha).read_bytes() == original_bytes
    assert literature.local_path(recorded, target).read_bytes() == current.read_bytes()
    proofs = [p for p in _proofs(target) if p['recorded'] == recorded]
    assert len(proofs) == 2 and all(p['availability'] == 'explicit-supplementary' and p['sha256'] == original_sha and p['path'] == companion for p in proofs)
    assert all('different bytes and keeps its own path' in p['resolution_basis'] for p in proofs)
    assert report['selected_supplementary_sources'] == [{'path': companion, 'sha256': original_sha, 'reason': entry['reason'],
                                                         'recorded_path': recorded, 'selection': 'content-addressed-historical-reading'}]
    assert verifier.verify(target)['ok']
    # H1: a re-export carries the exact published alias — current primary AND the pinned version — with
    # and without repeating the companion explicitly; unpinned reads stay current, pinned reads original
    for label, extra in [('again-no-explicit', []), ('again-explicit', [{**entry, 'path': str(target / companion)}])]:
        again = tmp_path / label
        exporter.export(target, again, 'first', extra)
        carried = json.loads((again / 'writing-portability.json').read_text())['source_aliases'][recorded]
        assert carried['path'] == 'docs/writing-engine-walkthrough.md' and carried['original_sha256'] == exporter.digest(current.read_bytes()), label
        assert carried['versions'][original_sha]['path'] == companion and carried['versions'][original_sha]['original_sha256'] == original_sha, label
        assert (again / 'docs/writing-engine-walkthrough.md').read_bytes() == current.read_bytes() and (again / companion).read_bytes() == original_bytes, label
        assert writing_portability.source_path(recorded, again) == (again / 'docs/writing-engine-walkthrough.md').resolve(), label
        assert writing_portability.source_path(recorded, again, sha256=original_sha).read_bytes() == original_bytes, label
        reproofs = [p for p in _proofs(again) if p['recorded'] == recorded]
        assert reproofs and all(p.get('sha256') == original_sha for p in reproofs), label
        assert verifier.verify(again)['ok'], label


@pytest.mark.parametrize('fault, error', [
    ('duplicates-current', 'duplicates the current file'),
    ('wrong-pin', 'supplementary source changed'),
    ('reading-neither', 'recorded source hash mismatch'),
    ('private', 'private or runtime recorded_path'),
    ('traversal', 'absolute spelling without traversal'),
    ('relative', 'absolute spelling without traversal'),
    ('renamed', 'keep the recorded file name'),
    ('two-pins-one-destination', 'conflicting explicit supplementary alias'),
    ('ambiguous-unhashed', 'ambiguous historical reading without a recorded hash'),
])
def test_historical_reading_companion_refuses_wrong_conflicting_private_and_ambiguous_aliases(tmp_path, fault, error):
    root, current, captured, original_bytes, original_sha, recorded, refs, entry = historical_reading_fixture(tmp_path)
    entries = [entry]
    if fault == 'duplicates-current':
        captured.write_bytes(current.read_bytes()); entries = [{**entry, 'sha256': exporter.digest(current.read_bytes())}]
    elif fault == 'wrong-pin':
        entries = [{**entry, 'sha256': 'sha256:' + 'a' * 64}]
    elif fault == 'reading-neither':
        refs.write_text(json.dumps({'associations': [{'metadata': {'provenance': {'path': recorded, 'sha256': 'sha256:' + 'b' * 64}}}]}))
    elif fault == 'private':
        entries = [{**entry, 'recorded_path': str(root / '.laplace-state' / 'writing-engine-walkthrough.md')}]
    elif fault == 'traversal':
        entries = [{**entry, 'recorded_path': str(root / 'docs' / '..' / 'docs' / 'writing-engine-walkthrough.md')}]
    elif fault == 'relative':
        entries = [{**entry, 'recorded_path': 'docs/writing-engine-walkthrough.md'}]
    elif fault == 'renamed':
        entries = [{**entry, 'recorded_path': str(root / 'docs/other-name.md')}]
    elif fault == 'two-pins-one-destination':
        other = tmp_path / 'captured' / 'second.md'; other.write_bytes(original_bytes)
        entries = [entry, {**entry, 'path': str(other), 'repository_path': 'docs/second.md'}]
        write(root, 'docs/second.md', original_bytes.decode())
        error = 'repository_path must be the source'
    elif fault == 'ambiguous-unhashed':
        third = b'# Walkthrough v0\n'; third_path = tmp_path / 'captured' / 'v0' / 'writing-engine-walkthrough.md'
        third_path.parent.mkdir(); third_path.write_bytes(third)
        entries = [entry, {**entry, 'path': str(third_path), 'sha256': exporter.digest(third)}]
        refs.write_text(json.dumps({'associations': [{'metadata': {'provenance': {'path': recorded}}}]}))
    with pytest.raises(ValueError, match=error):
        exporter.export(root, tmp_path / 'export', 'first', entries)
    assert not (tmp_path / 'export').exists() or not (tmp_path / 'export' / 'writing-portability.json').exists()


@pytest.mark.parametrize('tamper', ['version-bytes', 'version-pin', 'version-target-missing', 'directory-only'])
def test_reexport_refuses_tampered_or_missing_published_versions_and_directory_only_authority(tmp_path, tamper):
    root, current, captured, original_bytes, original_sha, recorded, refs, entry = historical_reading_fixture(tmp_path)
    first = tmp_path / 'first'; exporter.export(root, first, 'first', [entry])
    companion = first / 'supplementary_sources' / (original_sha.split(':')[-1] + '.md')
    portable_path = first / 'writing-portability.json'; portable = json.loads(portable_path.read_text())
    if tamper == 'version-bytes':
        companion.write_bytes(b'# not the original\n'); error = 'version .* bytes changed|pin is unavailable or changed'
    elif tamper == 'version-pin':
        portable['source_aliases'][recorded]['versions'][original_sha]['original_sha256'] = 'sha256:' + 'd' * 64
        portable_path.write_text(json.dumps(portable)); error = 'published portability provenance changed|pin is unavailable or changed'
    elif tamper == 'version-target-missing':
        companion.unlink(); error = 'target is missing|bytes changed|pin is unavailable'
    else:
        portable['source_aliases'] = {}; portable['directory_aliases'] = {str(root): '.'}
        portable_path.write_text(json.dumps(portable)); error = 'published portability provenance changed|no exact published alias|recorded source hash mismatch'
    with pytest.raises(ValueError, match=error):
        exporter.export(first, tmp_path / 'again', 'first', [])


@pytest.mark.parametrize('recorded', ['/author/soul/writing-engine-walkthrough.md', '/author/.laplace-state/writing-engine-walkthrough.md',
                                      '/author/.laplace-cache/writing-engine-walkthrough.md', '/author/docs/other.md',
                                      r'C:\\author\\soul\\writing-engine-walkthrough.md', r'C:\\author\\.laplace-state\\writing-engine-walkthrough.md',
                                      r'C:\\author\\docs\\renamed.md', '/author/.ssh/writing-engine-walkthrough.md'])
def test_historical_companion_refuses_private_runtime_and_renamed_spellings_outside_the_root_on_both_path_families(tmp_path, recorded):
    root, current, captured, original_bytes, original_sha, old, refs, entry = historical_reading_fixture(tmp_path)
    refs.write_text(json.dumps({'associations': [{'metadata': {'provenance': {'path': recorded, 'sha256': original_sha}}}]}))
    with pytest.raises(ValueError, match='private or runtime recorded_path refused|keep the recorded file name'):
        exporter.export(root, tmp_path / 'export', 'first', [{**entry, 'recorded_path': recorded}])
    assert not (tmp_path / 'export').exists()


def test_historical_companion_outside_the_root_with_a_clean_spelling_is_admitted(tmp_path):
    from laplace.projects import writing_portability
    root, current, captured, original_bytes, original_sha, old, refs, entry = historical_reading_fixture(tmp_path)
    for recorded in ['/author/checkout/docs/writing-engine-walkthrough.md', r'C:\\author\\checkout\\docs\\writing-engine-walkthrough.md']:
        refs.write_text(json.dumps({'associations': [{'metadata': {'provenance': {'path': recorded, 'sha256': original_sha}}}]}))
        target = tmp_path / ('export-' + str(len(recorded)))
        exporter.export(root, target, 'first', [{**entry, 'recorded_path': recorded}])
        alias = json.loads((target / 'writing-portability.json').read_text())['source_aliases'][recorded]
        assert alias['path'].startswith('supplementary_sources/') and alias['original_sha256'] == original_sha and 'versions' not in alias
        assert writing_portability.source_path(recorded, target, sha256=original_sha).read_bytes() == original_bytes


@pytest.mark.parametrize('historical_first', [False, True])
def test_qualified_companion_spelling_uniqueness_is_independent_of_entry_order_and_covers_raw_aliases(tmp_path, historical_first):
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    current = write(root, 'evidence/public/report.md', 'current report\n')
    captured = tmp_path / 'captured' / 'report.md'; captured.parent.mkdir(); captured.write_text('original report\n')
    current_pin, old_pin = exporter.digest(current.read_bytes()), exporter.digest(captured.read_bytes())
    write(root, 'projects/first/text/references.json', {'associations': [{'metadata': {'provenance': {'path': str(current), 'sha256': old_pin}}}]})
    qualified = {'path': str(current), 'repository_path': 'evidence/public/report.md', 'sha256': current_pin, 'reason': 'Current explicit public report'}
    historical = {'path': str(captured), 'recorded_path': str(current), 'sha256': old_pin, 'reason': 'Original report bytes read before the current report changed'}
    entries = [historical, qualified] if historical_first else [qualified, historical]
    with pytest.raises(ValueError, match='qualified repository_path companion cannot share its spelling with another pin'):
        exporter.export(root, tmp_path / 'export', 'first', entries)
    assert not (tmp_path / 'export').exists()


def two_version_fixture(tmp_path):
    """Two valid ORIGINAL readings of one recorded spelling; the records pin only the first."""
    root, current, captured, original_bytes, original_sha, recorded, refs, entry = historical_reading_fixture(tmp_path)
    older_bytes = b'# Walkthrough v0\nThe owner map before the first reading.\n'
    older_sha = exporter.digest(older_bytes)
    older = tmp_path / 'captured-older' / 'writing-engine-walkthrough.md'
    older.parent.mkdir(); older.write_bytes(older_bytes)
    older_entry = {**entry, 'path': str(older), 'sha256': older_sha, 'reason': 'Older engineering document bytes read before the first recorded reading'}
    return root, current, recorded, (original_bytes, original_sha, entry), (older_bytes, older_sha, older_entry)


def test_reexport_repeating_one_of_two_carried_versions_copies_every_version_target(tmp_path):
    """Sol H1 residual: a late explicit merge discovered the unmentioned carried version after
    the copied-file set was frozen, so its target never travelled while the alias declared it."""
    from laplace.projects import writing_portability
    root, current, recorded, (original_bytes, original_sha, entry), (older_bytes, older_sha, older_entry) = two_version_fixture(tmp_path)
    first = tmp_path / 'first'
    exporter.export(root, first, 'first', [entry, older_entry])
    companion = {sha: 'supplementary_sources/' + sha.split(':')[-1] + '.md' for sha in (original_sha, older_sha)}
    def closed(target, label):
        portable = json.loads((target / 'writing-portability.json').read_text())
        alias = portable['source_aliases'][recorded]
        report = json.loads((target / 'release/export-manifest.json').read_text())
        copied = {row['path']: row['sha256'] for row in report['copied_files']}
        assert alias['path'] == 'docs/writing-engine-walkthrough.md' and alias['original_sha256'] == exporter.digest(current.read_bytes()), label
        assert set(alias['versions']) == {original_sha, older_sha}, label
        for sha, raw in [(original_sha, original_bytes), (older_sha, older_bytes)]:
            assert alias['versions'][sha]['path'] == companion[sha] and alias['versions'][sha]['original_sha256'] == sha, label
            assert copied.get(companion[sha]) == sha, (label, 'every carried version file is a declared copied file with its pin')
            assert (target / companion[sha]).read_bytes() == raw, label
            assert writing_portability.source_path(recorded, target, sha256=sha).read_bytes() == raw, label
        assert (target / 'docs/writing-engine-walkthrough.md').read_bytes() == current.read_bytes(), label
        summary = verifier.verify(target)
        assert summary['ok'], (label, summary['failures'])
    closed(first, 'first')
    # the residual path: only the first companion is repeated explicitly from the published export
    second = tmp_path / 'second'
    exporter.export(first, second, 'first', [{**entry, 'path': str(first / companion[original_sha])}])
    closed(second, 'second')
    # and a further re-export without any explicit companion still carries both
    third = tmp_path / 'third'
    exporter.export(second, third, 'first', [])
    closed(third, 'third')


def test_verifier_refuses_a_dangling_alias_version_target(tmp_path):
    """The verifier closes the same gap: a declared alias version whose target is absent from the
    copied set (and from the export) cannot report success, whatever produced the export."""
    root, current, recorded, (original_bytes, original_sha, entry), (older_bytes, older_sha, older_entry) = two_version_fixture(tmp_path)
    target = tmp_path / 'export'
    exporter.export(root, target, 'first', [entry, older_entry])
    assert verifier.verify(target)['ok']
    older_rel = 'supplementary_sources/' + older_sha.split(':')[-1] + '.md'
    manifest_path = target / 'release/export-manifest.json'
    report = json.loads(manifest_path.read_text())
    report['copied_files'] = [row for row in report['copied_files'] if row['path'] != older_rel]
    manifest_path.write_text(json.dumps(report))
    (target / older_rel).unlink()
    summary = verifier.verify(target)
    assert not summary['ok']
    dangling = [f for f in summary['failures'] if f.get('reason', '').startswith('dangling source alias')]
    reason = 'dangling source alias: alias target is not a declared export file'
    # both aliases that name the lost bytes fail: the captured companion's own address (whose
    # primary is that file) and the recorded spelling's pinned version; nothing else is blamed
    assert dangling == [{'path': older_rel, 'alias': older_entry['path'], 'version': 'primary', 'reason': reason},
                        {'path': older_rel, 'alias': recorded, 'version': older_sha, 'reason': reason}]
    assert [f for f in summary['failures'] if f not in dangling] == [], 'the closure failure is the only complaint'


def _doc_links(text):
    """Relative Markdown links to .md files (no scheme, anchor dropped, %20 decoded)."""
    import re
    from urllib.parse import unquote
    return {unquote(raw.split('#', 1)[0]) for raw in re.findall(r'\]\(([^)\s]+)\)', text)
            if not re.match(r'^[a-z]+:', raw) and raw.split('#', 1)[0].endswith('.md')}


def test_the_operational_doc_selection_is_closed_under_its_doc_links():
    """P2 repair1 (Sol P2-R2): the developer source map is linked from the walkthrough, so it is selected with the
    bounded operational docs, and every docs/*.md an exported operational doc links to is itself selected."""
    tree = Path(__file__).parents[1]
    selected = set(exporter.OPERATIONAL_INPUTS)
    assert 'docs/writing-source-map.md' in selected and 'docs/writing-engine-walkthrough.md' in selected
    assert 'writing-source-map.md' in _doc_links((tree / 'docs/writing-engine-walkthrough.md').read_text(encoding='utf-8'))
    docs = sorted(rel for rel in selected if rel.startswith('docs/') and rel.endswith('.md'))
    unresolved = []
    for rel in docs:
        # the evaluator readme and agent entry are also exported at the root (README.md, AGENTS.md), so their links
        # resolve from there too; a link counts when it names an existing docs/ file of this tree
        bases = [Path(rel).parent] + ([Path('.')] if rel in {'docs/writing-evaluator-readme.md', 'docs/writing-evaluator-agents.md', 'docs/writing-reviewer-guide.md'} else [])
        for link in _doc_links((tree / rel).read_text(encoding='utf-8')):
            # Normalize cross-directory README links before comparing the export's path set.
            import os
            targets = [Path(os.path.normpath((base / link).as_posix())).as_posix() for base in bases]
            named = [t for t in targets if t.startswith('docs/') and (tree / t).is_file()]
            if named and not any(t in selected for t in named):
                unresolved.append((rel, link))
    assert not unresolved, unresolved


def test_an_export_carries_the_source_map_its_walkthrough_links(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    write(root, 'projects/first/text/references.json', {'sources': []})   # no external research input in this check
    walkthrough = write(root, 'docs/writing-engine-walkthrough.md', '# Walkthrough\nOwners: [the source map](writing-source-map.md).\n')
    source_map = write(root, 'docs/writing-source-map.md', '# Source map\nBack to the [walkthrough](writing-engine-walkthrough.md).\n')
    target = tmp_path / 'out'
    exporter.export_projects(root, target, ['first'])
    for doc in (walkthrough, source_map):
        exported = target / 'docs' / doc.name
        assert exported.read_bytes() == doc.read_bytes()
        assert all((exported.parent / link).is_file() for link in _doc_links(exported.read_text())), 'links resolve inside the export'
    assert not verifier.verify(target)['failures']


def test_an_export_carries_the_operational_homes_entry_its_code_overview_links(tmp_path):
    """NP-R3: the one human entry (docs/operational-homes.md) is an explicit operational input, so a curated export that
    carries the code overview carries the entry it links; nothing else is added to the selection."""
    assert 'docs/operational-homes.md' in exporter.OPERATIONAL_INPUTS
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    write(root, 'projects/first/text/references.json', {'sources': []})
    overview = write(root, 'docs/writing-code-overview.md', '# The code base\nWhere things live: [operational homes](operational-homes.md).\n')
    entry = write(root, 'docs/operational-homes.md', '# Where Laplace lives\nBack to the [code overview](writing-code-overview.md).\n')
    target = tmp_path / 'out'
    exporter.export_projects(root, target, ['first'])
    for doc in (overview, entry):
        exported = target / 'docs' / doc.name
        assert exported.read_bytes() == doc.read_bytes()
        assert all((exported.parent / link).is_file() for link in _doc_links(exported.read_text())), 'links resolve inside the export'
    assert not verifier.verify(target)['failures']


def test_export_carries_reviewer_entry_and_portable_test_scope_as_declared_root_files(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    write(root, 'projects/first/text/references.json', {'sources': []})
    guide = write(root, 'docs/writing-reviewer-guide.md', '# Reviewer entry\nRead [README](README.md).\n')
    config = write(root, 'docs/writing-pytest.ini', '[pytest]\ntestpaths = tests\n')
    target = tmp_path / 'out'
    report = exporter.export_projects(root, target, ['first'])
    assert (target / 'REVIEWER_GUIDE.md').read_bytes() == guide.read_bytes()
    assert (target / 'pytest.ini').read_bytes() == config.read_bytes()
    assert {'REVIEWER_GUIDE.md', 'pytest.ini'} <= {row['path'] for row in report['derived_files']}
    assert not verifier.verify(target)['failures']


def _resource_links(text):
    """Relative Markdown links of any kind (no scheme, anchor dropped, %20 decoded)."""
    import re
    from urllib.parse import unquote
    return {unquote(raw.split('#', 1)[0]) for raw in re.findall(r'\]\(([^)\s]+)\)', text)
            if not re.match(r'^[a-z]+:', raw) and raw.split('#', 1)[0]}


def test_every_source_resource_an_exported_operational_doc_links_is_selected():
    """CT-R2: the curated selection carries every non-Python file under src/ that an exported operational document
    links to (a .py file travels with the engine source; .md links are held by the doc-link closure above). The
    front door links the system description that laplace.system.load reads; the earlier closure followed .md only."""
    import os
    tree = Path(__file__).parents[1]
    selected = set()
    for rel in exporter.OPERATIONAL_INPUTS:
        target = tree / rel
        selected.update([p.relative_to(tree).as_posix() for p in target.rglob('*') if p.is_file()] if target.is_dir() else [rel])
    selected.update(p.relative_to(tree).as_posix() for p in (tree / 'src/laplace/web/static_shared').rglob('*') if p.is_file())
    selected.update(p.relative_to(tree).as_posix() for p in (tree / 'src/laplace/web').glob('*.html'))
    assert 'src/laplace/system/description.json' in selected
    unselected = []
    for rel in sorted(r for r in exporter.OPERATIONAL_INPUTS if r.endswith('.md') and (tree / r).is_file()):
        for link in _resource_links((tree / rel).read_text(encoding='utf-8')):
            target = Path(os.path.normpath((Path(rel).parent / link).as_posix())).as_posix()
            if target.startswith('src/') and not target.endswith('.py') and (tree / target).is_file() and target not in selected:
                unselected.append((rel, link))
    assert not unselected, unselected


def test_an_export_carries_the_system_description_its_front_door_links_and_it_loads(tmp_path):
    """CT-R2 fixture: the exact description bytes travel through the curated selection, are declared with their pin,
    load and shape-validate through laplace.system, and the exported front door's link reaches them. (A curated
    export need not pass the full upstream laplace.system check, which also measures tests and docs it omits.)"""
    import hashlib
    from laplace import system
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    write(root, 'projects/first/text/references.json', {'sources': []})
    description = Path(__file__).parents[1] / 'src/laplace/system/description.json'
    copied = root / 'src/laplace/system/description.json'
    copied.parent.mkdir(parents=True, exist_ok=True)
    copied.write_bytes(description.read_bytes())
    write(root, 'docs/writing-code-overview.md', '# The code base\nThe [system description](../src/laplace/system/description.json).\n')
    target = tmp_path / 'out'
    report = exporter.export_projects(root, target, ['first'])
    exported = target / 'src/laplace/system/description.json'
    assert exported.read_bytes() == description.read_bytes()
    pins = {row['path']: row['sha256'] for row in report['copied_files']}
    assert pins['src/laplace/system/description.json'].removeprefix('sha256:') == hashlib.sha256(exported.read_bytes()).hexdigest()
    loaded = system.load(exported)
    assert not system.shape_problems(loaded) and loaded['capabilities'][0]['id'] == 'work.dispatch-return-admission'
    front = target / 'docs/writing-code-overview.md'
    assert all((front.parent / link).resolve().is_file() for link in _resource_links(front.read_text()))
    assert not verifier.verify(target)['failures']
