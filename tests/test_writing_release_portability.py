"""Release-owner closure for the research-collection export (WORK-editor-campaign-release-portability-20261016).

The export owner now resolves each metadata file at its canonical owner, records a snapshot's unauthored metadata as
absent instead of fabricating it, carries a selected TeX source and its exact local inputs even outside the project
directory (bound to every selected owner, copied once), applies an explicit pinned per-file selection, and refuses
oversized or required-but-excluded files before anything is copied. Disposable fixtures only.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

from test_writing_eval_manifest import fixture, write

TREE = Path(__file__).parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, TREE / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = _load('writing_eval_manifest')
exporter = _load('export_writing_evaluation')
verifier = _load('verify_writing_evaluation')


def _sha(path):
    return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


# ---------------------------------------------------------------------------------------------- 1. owners

def test_a_nested_editable_project_keeps_references_and_research_at_its_state_home(tmp_path):
    from laplace.projects import library as wp
    from laplace.native import tools as writing_tools
    from laplace.research import research_context
    from laplace.research import research_records
    from laplace.pipeline import registry
    assert wp.create({'name': 'dd', 'title': 'DD', 'kind': 'general', 'purpose': 'Brief the reviewers.'}, tmp_path)[0] == 201
    home = research_context.owner_home('dd', tmp_path)
    (home / 'research_runs').mkdir()
    (home / 'research_runs' / 'run-1.result.json').write_text('{"score": 1}')
    assert research_records.record('dd', {'kind': 'result', 'id': 'result:score', 'result': 'research_runs/run-1.result.json',
                                          'title': 'Score'}, tmp_path)[0] == 201
    paper = tmp_path / 'supplied.pdf'
    paper.write_bytes(b'%PDF-1.4\n%%EOF')
    writing_tools.execute(tmp_path, 'dd', 'work', 'literature_import',
                          {'metadata': {'title': 'Reference'}, 'provenance': {'description': 'local', 'path': str(paper)}})
    resolved = registry.resolve('dd', repo_root=tmp_path)
    before = m.metadata_paths(tmp_path, 'dd', resolved)
    assert before['references'] == before['research_records'].replace('research_records.json', 'references.json')
    pins = {kind: _sha(tmp_path / before[kind]) for kind in ('references', 'research_records')}
    status, draft = wp.start_manuscript({'project': 'dd', 'title': 'Briefing', 'kind': 'paper'}, tmp_path)
    assert status == 201, draft
    after = m.metadata_paths(tmp_path, 'dd', resolved)
    assert {kind: after[kind] for kind in pins} == {kind: before[kind] for kind in pins}, 'the state home did not move'
    assert {kind: _sha(tmp_path / after[kind]) for kind in pins} == pins, 'same bytes, same ids'
    closure = m.project_closure(tmp_path, 'dd', 'current-project-snapshot')
    assert closure['required_files']['references']['path'] == before['references']
    assert closure['required_files']['research_records']['path'] == before['research_records']
    assert '/working-draft' in closure['required_files']['source']['path'], 'the selected TeX moved to the draft'
    assert '/working-draft' not in before['references'], 'reference associations never follow the selected source'


def test_a_snapshot_records_unauthored_metadata_without_creating_it_and_completed_intent_stays_strict(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    for name in ('projection_plan.json', 'references.json', 'research_records.json'):
        (root / 'projects/second/text' / name).unlink()
    before = _tree(root)
    with pytest.raises(m.ManifestError, match='required project closure is incomplete'):
        m.build_many(root, ['second'])
    manifest = m.build_many(root, ['second'], intents={'second': 'current-project-snapshot'})
    assert {k: v['status'] for k, v in manifest['project_closure']['authored_metadata'].items()} == {
        'plan': 'UNAUTHORED', 'references': 'UNAUTHORED', 'research_records': 'UNAUTHORED'}
    assert _tree(root) == before, 'absence is recorded, never written'
    target = tmp_path / 'export'
    exporter.export_projects(root, target, ['second'], intents={'second': 'current-project-snapshot'})
    assert not (target / 'projects/second/text/references.json').exists()
    verified = verifier.verify(target)
    assert verified['ok'], verified['failures']
    assert verified['per_project']['second']['authored_metadata'] == {
        'plan': 'UNAUTHORED', 'references': 'UNAUTHORED', 'research_records': 'UNAUTHORED'}


def test_a_present_record_that_requires_a_missing_current_file_still_refuses(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    write(root, 'projects/first/text/figure_manifest.json', {'figures': [], 'placed': [{'artefact': 'figures/absent.pdf'}]})
    with pytest.raises(m.ManifestError, match='placed figure artefact is unavailable'):
        m.build_many(root, ['first'], intents={'first': 'current-project-snapshot'})


# ---------------------------------------------------------------------------------------------- 2. shared source

def _shared(root):
    """Corpus owns the tree; Memory's registered TeX root lies inside it (the real campaign layout)."""
    fixture(root)
    registry = json.loads((root / 'registry_projects.json').read_text())
    registry['projects'] += [
        {'name': 'corpus', 'project_dir': 'papers/corpus', 'tex_root': 'papers/corpus/manuscript'},
        {'name': 'memory', 'project_dir': 'writing_projects/memory', 'tex_root': 'papers/corpus/output/v2'}]
    write(root, 'registry_projects.json', registry)
    write(root, 'papers/corpus/manuscript/main.tex', 'Corpus source.')
    (root / 'papers/corpus/manuscript/main.pdf').write_bytes(b'corpus pdf')
    write(root, 'papers/corpus/output/v2/main.tex',
          '\\documentclass{article}\\begin{document}\\input{sections/one}\\includegraphics{figures/plot.pdf}'
          '\\bibliography{refs}\\end{document}\n')
    write(root, 'papers/corpus/output/v2/sections/one.tex', 'Section one.')
    write(root, 'papers/corpus/output/v2/refs.bib', '@misc{a,title={A}}')
    (root / 'papers/corpus/output/v2/figures').mkdir(parents=True)
    (root / 'papers/corpus/output/v2/figures/plot.pdf').write_bytes(b'%PDF plot')
    (root / 'papers/corpus/output/v2/main.pdf').write_bytes(b'memory pdf')
    write(root, 'writing_projects/memory/notes.md', 'Memory project notes.')
    return {'corpus': 'current-project-snapshot', 'memory': 'current-project-snapshot'}


def test_memory_and_corpus_share_one_exact_source_closure_with_both_bindings(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); intents = _shared(root)
    manifest = m.build_many(root, ['corpus', 'memory'], intents=intents)
    shared = 'papers/corpus/output/v2/figures/plot.pdf'
    assert manifest['source_bindings'][shared] == ['corpus', 'memory']
    assert set(manifest['project_manifests']['memory']['selected_source_closure']['files']) >= {
        'papers/corpus/output/v2/main.tex', 'papers/corpus/output/v2/sections/one.tex', 'papers/corpus/output/v2/refs.bib', shared}
    assert any(row['path'] == shared for row in manifest['groups']['selected_project']), 'Corpus walks it'
    target = tmp_path / 'export'
    result = exporter.export_projects(root, target, ['corpus', 'memory'], intents=intents)
    assert [row['path'] for row in result['copied_files']].count(shared) == 1
    assert (target / shared).read_bytes() == b'%PDF plot'
    verified = verifier.verify(target)
    assert verified['ok'], verified['failures']


def test_memory_without_its_owning_corpus_refuses_and_names_the_owner(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); intents = _shared(root)
    with pytest.raises(m.ManifestError, match=r'belongs to an unselected project: papers/corpus/output/v2/.* \(select corpus\)'):
        m.build_many(root, ['memory'], intents={'memory': intents['memory']})


@pytest.mark.parametrize('case', ['symlink', 'private', 'outside'])
def test_source_closure_escapes_refuse(tmp_path, case):
    root = tmp_path / 'source'; root.mkdir(); intents = _shared(root)
    main = root / 'papers/corpus/output/v2/main.tex'
    if case == 'symlink':
        (root / 'papers/corpus/output/v2/sections/one.tex').unlink()
        outside = tmp_path / 'elsewhere.tex'; outside.write_text('escaped')
        os.symlink(outside, root / 'papers/corpus/output/v2/sections/one.tex')
        match = 'symlink|unavailable|escapes'
    elif case == 'private':
        write(root, 'papers/corpus/output/v2/private/secret.tex', 'private')
        main.write_text(main.read_text().replace('\\input{sections/one}', '\\input{private/secret}'))
        match = 'private, fenced or unavailable'
    else:
        main.write_text(main.read_text().replace('\\input{sections/one}', '\\input{../../../../outside}'))
        match = 'selected source closure is incomplete'
    with pytest.raises(m.ManifestError, match=match):
        m.build_many(root, ['corpus', 'memory'], intents=intents)


# ---------------------------------------------------------------------------------------------- 3. pinned selection

def _policy(root, project, directory, exclude=()):
    files = []
    for path in sorted((root / directory).rglob('*')):
        rel = path.relative_to(root).as_posix()
        if not path.is_file() or m._excluded(Path(rel)):
            continue
        files.append({'path': rel, 'sha256': _sha(path), 'bytes': path.stat().st_size,
                      'decision': 'exclude' if rel in exclude else 'include',
                      'reason': 'regenerable embedding cache (acquisition documented)' if rel in exclude else 'retained source/result'})
    return {'schema': m.SELECTION_SCHEMA, 'projects': {project: {'files': files}}}


def _portable_first(root):
    """The fixture's first project with its recorded reference resolvable (as the export suite does)."""
    write(root, 'projects/first/text/source.txt', 'included source')
    references = json.loads((root / 'projects/first/text/references.json').read_text())
    references['sources'][0]['source']['path'] = '/historical/root/projects/first/text/source.txt'
    write(root, 'projects/first/text/references.json', references)


def _selected(root):
    fixture(root)
    _portable_first(root)
    write(root, 'projects/first/results/frozen.json', '{"metric": 0.5}')
    write(root, 'projects/first/cache/embeddings.npz', 'REGENERABLE' * 100)
    return 'projects/first/cache/embeddings.npz'


def test_a_pinned_selection_exports_exactly_its_included_files_and_travels_for_verification_and_re_export(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); cache = _selected(root)
    policy = _policy(root, 'first', 'projects/first', exclude=(cache,))
    target = tmp_path / 'export'
    result = exporter.export_projects(root, target, ['first'], selection=policy)
    assert not (target / cache).exists() and (target / 'projects/first/results/frozen.json').is_file()
    assert result['selection_policy']['path'] == 'release/selection-policy.json'
    assert result['selected_size']['oversized'] == []
    verified = verifier.verify(target)
    assert verified['ok'], verified['failures']
    # the same policy, from the export itself, drives a re-export; historical aliases and pins are kept
    again = tmp_path / 'again'
    exporter.export_projects(target, again, ['first'], selection=(target / 'release/selection-policy.json').read_bytes())
    assert verifier.verify(again)['ok']
    first = json.loads((target / 'writing-portability.json').read_text())['source_aliases']
    second = json.loads((again / 'writing-portability.json').read_text())['source_aliases']
    recorded = '/historical/root/projects/first/text/source.txt'
    assert second[recorded]['original_sha256'] == first[recorded]['original_sha256']
    assert second[recorded]['path'] == first[recorded]['path'] == 'projects/first/text/source.txt'
    # a tampered travelled policy is caught
    (target / 'release/selection-policy.json').write_text('{}')
    assert any(row['reason'] == 'selection policy identity mismatch' for row in verifier.verify(target)['failures'])


@pytest.mark.parametrize('case', ['stale-include', 'stale-exclude', 'unreviewed', 'excluded-required', 'outside-project', 'proposal-schema'])
def test_selection_refusals_happen_before_any_copy(tmp_path, case):
    root = tmp_path / 'source'; root.mkdir(); cache = _selected(root)
    policy = _policy(root, 'first', 'projects/first', exclude=(cache,))
    match = {'stale-include': 'stale selection pin \\(included', 'stale-exclude': 'stale selection pin \\(excluded',
             'unreviewed': 'does not review 1 project file', 'excluded-required': 'excludes a required current input',
             'outside-project': 'outside its project', 'proposal-schema': 'needs schema'}[case]
    if case == 'stale-include':
        (root / 'projects/first/results/frozen.json').write_text('{"metric": 0.6}')
    elif case == 'stale-exclude':
        (root / cache).write_text('CHANGED')
    elif case == 'unreviewed':
        write(root, 'projects/first/results/new.json', '{}')
    elif case == 'excluded-required':
        for row in policy['projects']['first']['files']:
            if row['path'] == 'projects/first/text/main.tex':
                row['decision'] = 'exclude'
    elif case == 'outside-project':
        other = root / 'projects/second/text/main.tex'
        policy['projects']['first']['files'].append({'path': 'projects/second/text/main.tex', 'sha256': _sha(other),
                                                     'bytes': other.stat().st_size, 'decision': 'include', 'reason': 'x'})
    else:
        policy = {'schema': 'laplace.campaign-release-selection-proposal/1', 'project': 'first',
                  'files': policy['projects']['first']['files']}
    target = tmp_path / 'export'
    with pytest.raises(ValueError, match=match):
        exporter.export_projects(root, target, ['first'], selection=policy)
    assert not target.exists(), 'nothing is copied'


def test_an_oversized_file_and_a_missing_body_refuse_before_copying(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); _selected(root)
    big = root / 'projects/first/cache/huge.npz'
    with big.open('wb') as stream:
        stream.truncate(m.LARGE_FILE_BYTES + 1)
    target = tmp_path / 'export'
    with pytest.raises(ValueError, match=r'over 104857600 bytes .*projects/first/cache/huge.npz \(104857601 B\)'):
        exporter.export_projects(root, target, ['first'])
    assert not target.exists()
    big.unlink()
    with pytest.raises(ValueError, match='exceed the stated budget'):
        exporter.export_projects(root, target, ['first'], max_total_bytes=10)
    assert not target.exists()
    body = next((root / 'contract/writing_bodies').rglob('*'))
    for path in (root / 'contract/writing_bodies').rglob('*'):
        if path.is_file():
            body = path
            break
    body.unlink()
    with pytest.raises(ValueError, match='history body closure is incomplete'):
        exporter.export_projects(root, target, ['first'])
    assert not target.exists()


def test_document_links_are_classified_and_only_a_missing_selected_file_fails(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); fixture(root); _portable_first(root)
    write(root, 'docs/writing-evaluator-readme.md',
          'Read [the first paper](projects/first/text/main.pdf), [the second](projects/second/text/main.pdf) '
          'and [an external page](https://example.org/x).\n')
    target = tmp_path / 'export'
    exporter.export_projects(root, target, ['first'])
    verified = verifier.verify(target)
    assert verified['ok'], verified['failures']
    assert verified['document_links']['resolved'] >= 1 and verified['document_links']['unselected-project'] >= 1
    assert verified['document_links']['missing-selected'] == verified['document_links']['missing-common'] == 0
    assert ['projects/second/text/main.pdf', 'second'] in [list(row) for row in verified['unselected_project_links']]


def test_the_command_line_reads_the_policy_and_budget_and_the_manifest_reports_size(tmp_path, capsys):
    root = tmp_path / 'source'; root.mkdir(); cache = _selected(root)
    policy = tmp_path / 'policy.json'
    policy.write_text(json.dumps(_policy(root, 'first', 'projects/first', exclude=(cache,))))
    assert m.main(['--repo-root', str(root), '--project', 'first', '--selection-policy', str(policy)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['size']['oversized'] == [] and report['size']['per_file_limit_bytes'] == m.LARGE_FILE_BYTES
    assert [row['path'] for row in report['selection']['excluded']] == [cache]
    target = tmp_path / 'export'
    assert exporter.main(['--repo-root', str(root), '--destination', str(target), '--project', 'first',
                          '--selection-policy', str(policy), '--max-total-bytes', str(10 ** 9)]) == 0
    assert (target / 'release/selection-policy.json').read_bytes() == policy.read_bytes()


def test_an_imported_projects_registered_tex_outside_its_directory_travels_exactly(tmp_path):
    """The eleven imported papers: project_dir writing_projects/<name>, registered TeX root elsewhere and owned by no
    other project. The exact closure travels (never the ancestor tree); before M5 only writing_projects/<name> did."""
    root = tmp_path / 'source'; root.mkdir(); fixture(root)
    registry = json.loads((root / 'registry_projects.json').read_text())
    registry['projects'].append({'name': 'imported', 'project_dir': 'writing_projects/imported', 'tex_root': 'papers/imported/tex'})
    write(root, 'registry_projects.json', registry)
    write(root, 'writing_projects/imported/notes.md', 'Import notes.')
    write(root, 'papers/imported/tex/main.tex', '\\documentclass{article}\\begin{document}\\input{body}\\includegraphics{../figures/f.pdf}\\end{document}')
    write(root, 'papers/imported/tex/body.tex', 'Body.')
    (root / 'papers/imported/figures').mkdir(parents=True)
    (root / 'papers/imported/figures/f.pdf').write_bytes(b'%PDF f')
    (root / 'papers/imported/tex/main.pdf').write_bytes(b'%PDF main')
    write(root, 'papers/imported/unrelated-draft.tex', 'NOT IN THE CLOSURE')
    target = tmp_path / 'export'
    exporter.export_projects(root, target, ['imported'], intents={'imported': 'current-project-snapshot'})
    for rel in ('papers/imported/tex/main.tex', 'papers/imported/tex/body.tex', 'papers/imported/figures/f.pdf'):
        assert (target / rel).read_bytes() == (root / rel).read_bytes(), rel
    assert not (target / 'papers/imported/unrelated-draft.tex').exists(), 'no ancestor crawl'
    verified = verifier.verify(target)
    assert verified['ok'], verified['failures']


# ---------------------------------------------------------------------------------------------- repair1 (Sol RP-R1..R4)
# The exporter and the verifier share ONE writing_eval_manifest module object (exporter.inventory); `m` above is a
# separately loaded copy, so invocation-local controls patch exporter.inventory.

def _reasons(result):
    return [(row.get('path'), row['reason']) for row in result['failures']]


@pytest.mark.parametrize('case', ['excluded', 'unreviewed', 'private', 'symlink', 'oversized', 'wrong-hash', 'missing'])
def test_verification_inventories_the_actual_selected_home_never_the_declared_copy_list(tmp_path, monkeypatch, case):
    root = tmp_path / 'source'; root.mkdir(); cache = _selected(root)
    policy = _policy(root, 'first', 'projects/first', exclude=(cache,))
    target = tmp_path / 'export'
    exporter.export_projects(root, target, ['first'], selection=policy)
    assert verifier.verify(target)['ok']
    frozen = 'projects/first/results/frozen.json'
    if case == 'excluded':
        write(target, cache, 'EXCLUDED_CACHE_REINTRODUCED'); want = (cache, 'an excluded file is present in the export')
    elif case == 'unreviewed':
        write(target, 'projects/first/results/extra.json', '{}')
        want = ('projects/first/results/extra.json', 'a file present in the export is not in the reviewed selection')
    elif case == 'private':
        write(target, 'projects/first/.env', 'SYNTHETIC'); want = ('projects/first/.env', 'a private, runtime or secret file is present in the export')
    elif case == 'symlink':
        os.symlink(target / frozen, target / 'projects/first/results/linked.json')
        want = ('projects/first/results/linked.json', 'a symlink is present in the export')
    elif case == 'oversized':
        write(target, 'projects/first/results/big.bin', 'x' * 4096)
        monkeypatch.setattr(exporter.inventory, 'LARGE_FILE_BYTES', 2048)   # a scaled ceiling proves the branch
        want = ('projects/first/results/big.bin', 'file exceeds the per-file export ceiling')
    elif case == 'wrong-hash':
        (target / frozen).write_text('{"metric": 0.9}'); want = (frozen, 'exported bytes differ from the reviewed pin')
    else:
        (target / frozen).unlink(); want = (frozen, 'reviewed included file is missing from the export')
    assert want in _reasons(verifier.verify(target))


def test_a_declared_derived_output_inside_a_policy_home_is_allowed_and_nothing_else_is():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d); write(root, 'p/a.txt', 'a'); write(root, 'p/derived.jsonl', 'row'); write(root, 'p/stray.txt', 's')
        policy = {'schema': m.SELECTION_SCHEMA, 'projects': {'p': {'files': [
            {'path': 'p/a.txt', 'sha256': _sha(root / 'p/a.txt'), 'bytes': 1, 'decision': 'include', 'reason': 'r'}]}}}
        write(root, 'release/selection-policy.json', policy)
        report = {'selection_policy': {'path': 'release/selection-policy.json', 'sha256': _sha(root / 'release/selection-policy.json')},
                  'copied_files': [{'path': 'p/a.txt', 'sha256': _sha(root / 'p/a.txt')}],
                  'derived_files': [{'path': 'p/derived.jsonl', 'sha256': _sha(root / 'p/derived.jsonl')}]}
        failures = verifier.selection_closure(root, report, exporter.inventory, {'p': 'p'})
        assert failures == [{'project': 'p', 'path': 'p/stray.txt', 'reason': 'a file present in the export is not in the reviewed selection'}]


def _imported(root, main, files=(), intent='current-project-snapshot'):
    """An imported snapshot: project_dir writing_projects/imported, its selected source under papers/imported/tex."""
    fixture(root)
    registry = json.loads((root / 'registry_projects.json').read_text())
    registry['projects'].append({'name': 'imported', 'project_dir': 'writing_projects/imported', 'tex_root': 'papers/imported/tex'})
    write(root, 'registry_projects.json', registry)
    write(root, 'writing_projects/imported/notes.md', 'Imported snapshot')
    write(root, 'papers/imported/tex/main.tex', main)
    for rel, text in files:
        write(root, 'papers/imported/tex/' + rel, text)
    (root / 'papers/imported/tex/main.pdf').write_bytes(b'%PDF imported')
    return {'imported': intent}


def test_document_links_are_owned_by_selected_homes_bindings_and_common_inputs(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); intents = _imported(root, '\\documentclass{article}\\begin{document}x\\end{document}\n')
    write(root, 'writing_projects/imported/a file.md', 'spaced')
    write(root, 'docs/writing-evaluator-readme.md', '\n'.join([
        '[pdf](papers/imported/tex/main.pdf) [page](papers/imported/tex/main.pdf#page=2) [spaced](writing_projects/imported/a%20file.md)',
        '[angle](<writing_projects/imported/a file.md>) [titled](writing_projects/imported/notes.md "Notes") [web](https://example.org/x)',
        '[mail](mailto:a@example.org) [frag](#top) [ref][r]', '', '[r]: papers/imported/tex/main.tex', '',
        '[absent figure](papers/imported/tex/figures/absent.pdf) [absent module](src/laplace/never_included.py)',
        '[other project](projects/second/text/main.pdf)']) + '\n')
    target = tmp_path / 'export'
    exporter.export_projects(root, target, ['imported'], intents=intents)
    verified = verifier.verify(target)
    assert verified['document_links'] == {'resolved': 6, 'missing-selected': 1, 'missing-common': 1, 'unselected-project': 1}
    assert sorted((row.get('link'), row['reason']) for row in verified['failures']) == [
        ('papers/imported/tex/figures/absent.pdf', 'document link names a selected file that did not travel'),
        ('src/laplace/never_included.py', 'document link names a common engine, script or document file that did not travel')]
    assert verified['unselected_project_links'] == [('projects/second/text/main.pdf', 'second')]
    assert not (target / 'projects/second').exists(), 'the unselected project is named, never copied'


def test_every_generated_output_is_gated_before_the_destination_exists(tmp_path, monkeypatch):
    root = tmp_path / 'source'; root.mkdir(); cache = _selected(root)
    policy = _policy(root, 'first', 'projects/first', exclude=(cache,))
    policy['projects']['first']['files'][0]['reason'] = 'Reviewed reason ' + 'x' * 40000
    monkeypatch.setattr(exporter.inventory, 'LARGE_FILE_BYTES', 32768)   # scaled ceiling; no >100 MiB file is written
    target = tmp_path / 'export'
    with pytest.raises(ValueError, match=r'planned output file\(s\) over 32768 bytes: release/selection-policy\.json \(\d+ B\)'):
        exporter.export_projects(root, target, ['first'], selection=policy)
    assert not target.exists()


def test_the_total_budget_is_the_complete_written_output(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); cache = _selected(root)
    policy = _policy(root, 'first', 'projects/first', exclude=(cache,))
    first = tmp_path / 'first'
    report = exporter.export_projects(root, first, ['first'], selection=policy)
    written = sum(p.stat().st_size for p in first.rglob('*') if p.is_file())
    manifest = (first / 'release/export-manifest.json').stat().st_size
    assert report['output_size']['bytes_excluding_export_manifest'] + manifest == written
    assert report['output_size']['files'] == sum(1 for p in first.rglob('*') if p.is_file())
    assert report['selected_size']['bytes'] < written, 'source-input bytes are not the output total'
    with pytest.raises(ValueError, match=f'{written} bytes, would exceed the stated budget {written - 1}'):
        exporter.export_projects(root, tmp_path / 'lower', ['first'], selection=policy, max_total_bytes=written - 1)
    assert not (tmp_path / 'lower').exists()
    exact = exporter.export_projects(root, tmp_path / 'exact', ['first'], selection=policy, max_total_bytes=written)
    assert sum(p.stat().st_size for p in (tmp_path / 'exact').rglob('*') if p.is_file()) == written and exact['output_size']


def test_the_verifier_uses_actual_sizes_and_checks_declared_byte_counts(tmp_path, monkeypatch):
    root = tmp_path / 'source'; root.mkdir(); fixture(root); _portable_first(root)
    target = tmp_path / 'export'
    exporter.export_projects(root, target, ['first'])
    manifest = json.loads((target / 'release/export-manifest.json').read_text())
    row = next(item for item in manifest['copied_files'] if item['path'] == 'projects/first/text/main.tex')
    row['bytes'] = 1
    (target / 'release/export-manifest.json').write_text(json.dumps(manifest))
    assert ('projects/first/text/main.tex', 'declared byte count differs from the exported file') in _reasons(verifier.verify(target))
    monkeypatch.setattr(exporter.inventory, 'LARGE_FILE_BYTES', 8)
    assert ('projects/first/text/main.tex', 'file exceeds the per-file export ceiling') in _reasons(verifier.verify(target))


def test_braced_and_unbraced_imported_inputs_outside_the_project_travel_once_and_reverify(tmp_path):
    root = tmp_path / 'source'; root.mkdir()
    intents = _imported(root, '\\documentclass{article}\\usepackage{amsmath}\\begin{document}\\input{one}\n\\input two\n\\end{document}\n',
                        [('one.tex', 'ONE'), ('two.tex', 'TWO')])
    target = tmp_path / 'export'
    report = exporter.export_projects(root, target, ['imported'], intents=intents)
    closure = json.loads((target / 'release/source-manifest.json').read_text())['selected_source_closure']
    assert closure['files'] == ['papers/imported/tex/main.tex', 'papers/imported/tex/one.tex', 'papers/imported/tex/two.tex']
    assert sorted(row['name'] for row in closure['installed_requests']) == ['amsmath', 'article'], 'installed packages/classes are never checkout files'
    copied = [row['path'] for row in report['copied_files']]
    assert copied.count('papers/imported/tex/two.tex') == 1 and (target / 'papers/imported/tex/two.tex').read_text() == 'TWO'
    assert verifier.verify(target)['ok']
    (target / 'papers/imported/tex/two.tex').write_text('CHANGED')
    assert ('papers/imported/tex/two.tex', 'source closure bytes differ from the declared pin') in _reasons(verifier.verify(target))


def test_a_policy_cannot_exclude_another_selected_projects_unbraced_input(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); intents = _shared(root)
    main = root / 'papers/corpus/output/v2/main.tex'
    main.write_text(main.read_text().replace('\\input{sections/one}', '\\input{sections/one}\n\\input sections/two\n'))
    write(root, 'papers/corpus/output/v2/sections/two.tex', 'Section two.')
    policy = _policy(root, 'corpus', 'papers/corpus', exclude=('papers/corpus/output/v2/sections/two.tex',))
    target = tmp_path / 'export'
    with pytest.raises(ValueError, match=r'excludes a required current input: papers/corpus/output/v2/sections/two\.tex'):
        exporter.export_projects(root, target, ['corpus', 'memory'], intents=intents, selection=policy)
    assert not target.exists()


@pytest.mark.parametrize('case', ['missing-bibliography', 'missing-graphic', 'missing-unbraced', 'dynamic', 'cycle'])
def test_unresolved_declarations_refuse_before_copying(tmp_path, case):
    body = {'missing-bibliography': 'Text.\\bibliography{missing}', 'missing-graphic': '\\includegraphics{figures/absent.pdf}',
            'missing-unbraced': '\\input absent', 'dynamic': '\\input{\\jobname-extra}', 'cycle': '\\input{loop}'}[case]
    root = tmp_path / 'source'; root.mkdir()
    intents = _imported(root, '\\documentclass{article}\\begin{document}' + body + '\\end{document}\n', [('loop.tex', '\\input{loop}')])
    target = tmp_path / 'export'
    # a missing declared graphic is already refused by the project closure; every other case by the source closure
    with pytest.raises(ValueError, match='required declared graphic output is unavailable' if case == 'missing-graphic'
                       else 'selected source closure is incomplete'):
        exporter.export_projects(root, target, ['imported'], intents=intents)
    assert not target.exists()
    if case == 'missing-graphic':
        with pytest.raises(ValueError, match=r'incomplete \(MISSING_DECLARATION\): figures/absent\.pdf \[graphic\]'):
            exporter.inventory.selected_source_closure(root.resolve(), {'root': 'papers/imported/tex/main.tex'}, 'current-project-snapshot')


def test_an_installed_tex_input_is_named_never_copied_and_an_unfound_one_refuses(tmp_path, monkeypatch):
    root = tmp_path / 'source'; root.mkdir()
    intents = _imported(root, '\\documentclass{article}\\begin{document}\\input{glyphtounicode}\\end{document}\n')
    installed = tmp_path / 'texlive/glyphtounicode.tex'; installed.parent.mkdir(); installed.write_text('% installed')
    record = {'path': str(installed), 'distribution_root': str(installed.parent), 'relative': installed.name, 'sha256': _sha(installed)}
    monkeypatch.setattr(exporter.inventory, 'installed_tex_input', lambda name: record if name == 'glyphtounicode' else None)
    target = tmp_path / 'export'
    exporter.export_projects(root, target, ['imported'], intents=intents)
    closure = json.loads((target / 'release/source-manifest.json').read_text())['selected_source_closure']
    assert [(row['argument'], row['status']) for row in closure['installed_inputs']] == [('glyphtounicode', 'INSTALLED_TEX_INPUT')]
    assert not any('glyphtounicode' in p.name for p in target.rglob('*')), 'nothing is copied from the system'
    assert verifier.verify(target)['ok']
    monkeypatch.setattr(exporter.inventory, 'installed_tex_input', lambda name: None)
    with pytest.raises(ValueError, match=r'incomplete \(MISSING_DECLARATION\): glyphtounicode \[include\]'):
        exporter.export_projects(root, tmp_path / 'unfound', ['imported'], intents=intents)


def test_a_snapshot_keeps_its_original_frozen_bbl_and_a_completed_manuscript_still_refuses(tmp_path):
    root = tmp_path / 'source'; root.mkdir()
    intents = _imported(root, '\\documentclass{article}\\begin{document}Text.\\bibliography{literature}\\end{document}\n',
                        [('main.bbl', '\\begin{thebibliography}{1}\\end{thebibliography}')])
    target = tmp_path / 'export'
    exporter.export_projects(root, target, ['imported'], intents=intents)
    frozen = json.loads((target / 'release/source-manifest.json').read_text())['selected_source_closure']['frozen_bibliography']
    assert frozen['path'] == 'papers/imported/tex/main.bbl' and frozen['missing_databases'] == ['literature']
    assert frozen['sha256'] == _sha(root / 'papers/imported/tex/main.bbl') == _sha(target / 'papers/imported/tex/main.bbl')
    assert not (target / 'papers/imported/tex/literature.bib').exists(), 'no bibliography is invented'
    assert verifier.verify(target)['ok']
    (target / 'papers/imported/tex/main.bbl').write_text('CHANGED')
    assert any(reason == 'frozen bibliography pin differs from the recorded closure' for _path, reason in _reasons(verifier.verify(target)))
    # the frozen .bbl qualifies a snapshot only: the same source under a completed-manuscript intent refuses
    with pytest.raises(ValueError, match=r'incomplete \(MISSING_DECLARATION\): literature \[bibliography\]'):
        exporter.inventory.selected_source_closure(root.resolve(), {'root': 'papers/imported/tex/main.tex'}, 'completed-manuscript')


def test_an_inside_symlinked_source_alias_refuses_rather_than_travelling_as_its_target(tmp_path):
    root = tmp_path / 'source'; root.mkdir()
    intents = _imported(root, '\\documentclass{article}\\begin{document}\\input{alias}\\end{document}\n', [('real.tex', 'REAL')])
    os.symlink(root / 'papers/imported/tex/real.tex', root / 'papers/imported/tex/alias.tex')
    target = tmp_path / 'export'
    with pytest.raises(ValueError, match='symlinked path'):
        exporter.export_projects(root, target, ['imported'], intents=intents)
    assert not target.exists()



# ---------------------------------------------------------------------------------------------- repair2 (Sol RP-R1-R1, RP-R4-R1)

@pytest.mark.parametrize('rel', ['p/.env', 'p/auth.json', 'p/private/notes.txt', 'p/__pycache__/m.pyc', 'p/.research_previews/x.png', 'p/keys/k.pem'])
@pytest.mark.parametrize('labelled', [True, False])
def test_no_copied_or_derived_label_declassifies_a_private_runtime_or_secret_file(rel, labelled):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d); write(root, 'p/a.txt', 'a'); write(root, 'p/derived.jsonl', 'row'); write(root, rel, 'SYNTHETIC')
        policy = {'schema': m.SELECTION_SCHEMA, 'projects': {'p': {'files': [
            {'path': 'p/a.txt', 'sha256': _sha(root / 'p/a.txt'), 'bytes': 1, 'decision': 'include', 'reason': 'r'}]}}}
        write(root, 'release/selection-policy.json', policy)
        derived = [{'path': 'p/derived.jsonl', 'sha256': _sha(root / 'p/derived.jsonl')}]
        if labelled:
            derived.append({'path': rel, 'sha256': _sha(root / rel), 'derivation': 'declared derived output'})
        report = {'selection_policy': {'path': 'release/selection-policy.json', 'sha256': _sha(root / 'release/selection-policy.json')},
                  'copied_files': [{'path': 'p/a.txt', 'sha256': _sha(root / 'p/a.txt')}], 'derived_files': derived}
        failures = verifier.selection_closure(root, report, exporter.inventory, {'p': 'p'})
        assert failures == [{'project': 'p', 'path': rel, 'reason': 'a private, runtime or secret file is present in the export'}]


KPSEWHICH = __import__('shutil').which('kpsewhich')


@pytest.mark.skipif(KPSEWHICH is None, reason='needs the real kpsewhich')
def test_an_author_input_found_through_texinputs_is_not_an_installed_distribution_input(tmp_path, monkeypatch):
    outside = tmp_path / 'author-owned-external-input'; outside.mkdir()
    (outside / 'sol_external_input.tex').write_text('SYNTHETIC AUTHOR OWNED EXTERNAL TEX')
    root = tmp_path / 'source'; root.mkdir()
    intents = _imported(root, '\\documentclass{article}\n\\begin{document}\n\\input{sol_external_input}\n\\end{document}\n')
    monkeypatch.setenv('TEXINPUTS', str(outside) + '//:')
    monkeypatch.setenv('TEXMFHOME', str(outside))
    monkeypatch.setenv('TEXMFDIST', str(outside)); monkeypatch.setenv('TEXMFMAIN', str(outside))   # nor can a session redefine the distribution
    assert exporter.inventory.installed_tex_input('sol_external_input') is None
    target = tmp_path / 'export'
    with pytest.raises(ValueError, match=r'incomplete \(MISSING_DECLARATION\): sol_external_input \[include\]'):
        exporter.export_projects(root, target, ['imported'], intents=intents)
    assert not target.exists()


@pytest.mark.skipif(KPSEWHICH is None or not exporter.inventory.installed_tex_input('glyphtounicode'), reason='needs TeX Live glyphtounicode')
def test_a_real_distribution_input_is_named_with_provenance_and_reverification_detects_a_change(tmp_path, monkeypatch):
    root = tmp_path / 'source'; root.mkdir()
    intents = _imported(root, '\\documentclass{article}\\begin{document}\\input{glyphtounicode}\\end{document}\n')
    target = tmp_path / 'export'
    exporter.export_projects(root, target, ['imported'], intents=intents)
    [row] = json.loads((target / 'release/source-manifest.json').read_text())['selected_source_closure']['installed_inputs']
    assert row['relative'] == 'tex/generic/pdftex/glyphtounicode.tex' and row['sha256'].startswith('sha256:')
    assert row['status'] == 'INSTALLED_TEX_INPUT' and not any(p.name == 'glyphtounicode.tex' for p in target.rglob('*'))
    assert verifier.verify(target)['ok']
    real = exporter.inventory.installed_tex_input
    monkeypatch.setattr(exporter.inventory, 'installed_tex_input', lambda name: {**real(name), 'sha256': 'sha256:' + '0' * 64})
    assert any(f['reason'] == 'installed TeX input provenance or availability differs from the recorded closure'
               for f in verifier.verify(target)['failures'])
    monkeypatch.setattr(exporter.inventory, 'installed_tex_input', lambda name: None)
    assert any('does not re-establish' in f['reason'] for f in verifier.verify(target)['failures']), 'an unavailable input is not silently accepted'


@pytest.mark.skipif(KPSEWHICH is None, reason='needs the real kpsewhich')
def test_a_texmfhome_author_tree_found_by_kpsewhich_is_not_the_distribution(tmp_path, monkeypatch):
    home = tmp_path / 'home'; (home / 'texmf/tex/latex/sol').mkdir(parents=True)
    (home / 'texmf/tex/latex/sol/sol_home_input.tex').write_text('SYNTHETIC AUTHOR HOME TREE INPUT')
    monkeypatch.setenv('HOME', str(home))   # kpathsea derives TEXMFHOME from HOME, which no override filter removes
    assert exporter.inventory.installed_tex_input('sol_home_input') is None, 'found by kpsewhich, but outside TEXMFDIST/TEXMFMAIN'
    root = tmp_path / 'source'; root.mkdir()
    intents = _imported(root, '\\documentclass{article}\\begin{document}\\input{sol_home_input}\\end{document}\n')
    with pytest.raises(ValueError, match=r'incomplete \(MISSING_DECLARATION\): sol_home_input \[include\]'):
        exporter.export_projects(root, tmp_path / 'export', ['imported'], intents=intents)
