"""Distribution controls for reached source/resource omissions and exact replay."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS) not in sys.path: sys.path.insert(0, str(SCRIPTS))
import writing_eval_manifest as inventory
import export_writing_evaluation as exporter


def fixture(tmp_path, monkeypatch):
    root = tmp_path / 'source'
    (root / 'src/atlas').mkdir(parents=True)
    (root / 'src/atlas/feature.py').write_text('VALUE = 1\n')
    (root / 'src/atlas/schema.json').write_text('{"type":"object"}\n')
    monkeypatch.setattr(inventory, 'APPLICATION_ROOTS', ('src',))
    monkeypatch.setattr(inventory, 'APPLICATION_FILES', ())
    monkeypatch.setattr(inventory, 'PRIVATE_APPLICATION_INPUTS', ('src/private-author',))
    rows = inventory.application_closure(root, tests=True)['files']
    (root / 'release').mkdir()
    selection = root / 'release/selection-manifest.json'
    selection.write_text(json.dumps({'schema': 'laplace.curated-evaluation-selection/1', 'files': rows, 'derived_files': {}}))
    return root, selection


def test_complete_family_includes_resource_and_detects_future_addition(tmp_path, monkeypatch):
    root, selection = fixture(tmp_path, monkeypatch)
    (root / 'src/private-author').mkdir()
    (root / 'src/private-author/facts.md').write_text('never distributed')
    closure = inventory.application_closure(root)
    assert {r['path'] for r in closure['files']} == {'src/atlas/feature.py', 'src/atlas/schema.json'}
    assert closure['excluded_files'] == ['src/private-author/facts.md']
    (root / 'src/atlas/new-feature.py').write_text('NEW = True\n')
    destination = tmp_path / 'export'
    with pytest.raises(ValueError, match='omits application closure'):
        exporter.export_curated(root, destination, selection)
    assert not destination.exists()


def test_exact_replay_preserves_bytes_and_new_root(tmp_path, monkeypatch):
    root, selection = fixture(tmp_path, monkeypatch)
    destination = tmp_path / 'export'
    result = exporter.export_curated(root, destination, selection)
    assert result['status'] == 'EXACT_CURATED_REPLAY'
    assert (destination / 'src/atlas/schema.json').read_bytes() == (root / 'src/atlas/schema.json').read_bytes()
    assert (destination / 'release/selection-manifest.json').read_bytes() == selection.read_bytes()
    assert not (destination / '.git').exists()
    with pytest.raises(ValueError, match='new directory'):
        exporter.export_curated(root, destination, selection)


def test_changed_bytes_refuse_before_output(tmp_path, monkeypatch):
    root, selection = fixture(tmp_path, monkeypatch)
    (root / 'src/atlas/feature.py').write_text('VALUE = 2\n')
    destination = tmp_path / 'export'
    with pytest.raises(ValueError, match='selected bytes changed'):
        exporter.export_curated(root, destination, selection)
    assert not destination.exists()


def test_selection_size_budget_counts_manifest(tmp_path, monkeypatch):
    root, selection = fixture(tmp_path, monkeypatch)
    total = sum(p.stat().st_size for p in (root / 'src').rglob('*') if p.is_file())
    with pytest.raises(ValueError, match='exceed'):
        exporter.export_curated(root, tmp_path / 'export', selection, max_total_bytes=total)


def test_project_export_uses_stable_research_home_for_nested_draft(tmp_path):
    root = tmp_path / 'workspace'
    home = root / 'writing_projects/public/manuscript'
    draft = home / 'working-draft'
    draft.mkdir(parents=True)
    (draft / 'main.tex').write_text(r"\documentclass{article}\begin{document}One claim.\end{document}")
    (home / 'research_runs').mkdir()
    result = home / 'research_runs/finite.result.json'
    result.write_text('{"value":1}')
    (home / 'research_records.json').write_text(json.dumps({'records': [
        {'id': 'finite', 'kind': 'result', 'result': 'research_runs/finite.result.json',
         'result_scope': 'manuscript', 'scope': 'project'}]}))
    (root / 'registry_projects.json').write_text(json.dumps({'projects': [{
        'name': 'public', 'kind': 'project', 'project_dir': 'writing_projects/public',
        'manifest': {'document': {'root': 'writing_projects/public/manuscript/working-draft/main.tex',
            'manuscript_dir': 'writing_projects/public/manuscript/working-draft',
            'state_dir': 'writing_projects/public/manuscript'}}}]}))
    closure = inventory.project_closure(root, 'public', intent='current-project-snapshot')
    assert result.relative_to(root).as_posix() in closure['current_inputs']
    assert not any('working-draft/research_runs' in item for item in closure['current_inputs'])


def test_document_links_use_declared_root_entry_render_context(tmp_path):
    import verify_writing_evaluation as verifier
    root = tmp_path / 'docs-export'
    (root / 'docs').mkdir(parents=True)
    (root / 'src').mkdir()
    (root / 'src/feature.py').write_text('VALUE = 1\n')
    text = '[Implementation](src/feature.py)\n'
    (root / 'README.md').write_text('# Current generated entry\n' + text)
    (root / 'docs/writing-evaluator-readme.md').write_text(text)
    (root / 'docs/ordinary.md').write_text(text)
    paths = ['README.md', 'docs/writing-evaluator-readme.md', 'docs/ordinary.md', 'src/feature.py']
    rows, failures = verifier.document_links(root, {'copied_files': [{'path': p, 'sha256': 'sha256:' + hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in paths], 'derived_files': []},
                                               {'selected': {}, 'unselected': {}, 'bindings': {}})
    assert len(failures) == 1
    assert failures[0]['path'] == 'docs/ordinary.md'
    assert any(row['path'] == 'docs/writing-evaluator-readme.md' and row['status'] == 'resolved' for row in rows)
