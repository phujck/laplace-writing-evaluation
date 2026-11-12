import json
from pathlib import Path

import pytest

from laplace.projects.writing_portability import source_path, relocate_run, scoped_path
from laplace.writing import session_reads
from laplace.pipeline import registry


def test_exact_alias_and_outside_source_refusal(tmp_path):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"independent")
    (tmp_path / "writing-portability.json").write_text(json.dumps({
        "schema": "laplace.writing-portability/1",
        "source_aliases": {"/original/paper.pdf": {"path": "source.pdf"}}}))
    assert source_path("/original/paper.pdf", tmp_path) == source
    assert source_path("source.pdf", tmp_path) == source
    with pytest.raises(ValueError, match="not included"):
        source_path("/original/other.pdf", tmp_path)


def test_alias_cannot_escape_checkout(tmp_path):
    (tmp_path / "writing-portability.json").write_text(json.dumps({
        "schema": "laplace.writing-portability/1",
        "source_aliases": {"old": {"path": "../private"}}}))
    with pytest.raises(ValueError, match="inside"):
        source_path("old", tmp_path)


def test_import_preserves_history_and_starts_new_native_binding(tmp_path):
    path = tmp_path / "contract/talk.jsonl"
    path.parent.mkdir()
    original = [{"record": "writing-session", "id": "WS-old", "project": "sample",
                 "provider": "codex", "native_id": None},
                {"record": "writing-binding", "session_id": "WS-old", "native_id": "original-provider-id"},
                {"record": "writing-turn", "id": "WT-old", "session_id": "WS-old", "text": "Original work."}]
    raw = "".join(json.dumps(r) + "\n" for r in original)
    path.write_text(raw)
    with path.open("a") as stream:
        stream.write(json.dumps({"record": "writing-session-import", "session_id": "WS-old",
                                "source_manifest_sha256": "sha256:source"}) + "\n")
    records = session_reads._records(tmp_path)
    assert records["sessions"]["WS-old"]["native_id"] is None
    assert records["sessions"]["WS-old"]["imported_history"]
    assert records["turns"]["WT-old"]["text"] == "Original work."
    assert path.read_text().startswith(raw)


def test_export_registry_never_discovers_historical_sibling_projects(tmp_path):
    (tmp_path / 'registry_projects.json').write_text(json.dumps({'projects': [
        {'name': 'sample', 'project_dir': 'projects/sample', 'tex_root': 'projects/sample/text'}]}))
    (tmp_path / 'writing-portability.json').write_text(json.dumps({'schema': 'laplace.writing-portability/1'}))
    # An old built-in project directory must not be interpreted as registration.
    (tmp_path / 'paper_eigen').mkdir()
    assert set(registry.all_projects(tmp_path)) == {'sample'}


def test_historical_run_locations_rebase_without_reading_original_checkout(tmp_path):
    manifest = {'schema': 'laplace.writing-portability/1',
                'directory_aliases': {'/original': '.'}}
    (tmp_path / 'writing-portability.json').write_text(json.dumps(manifest))
    manuscript = tmp_path / 'projects/book/manuscript'
    manuscript.mkdir(parents=True)
    old = {'producer_base': '/original/projects/book',
           'result_absolute': '/original/projects/book/manuscript/research_runs/run.result.json',
           'cancel_path': '/original/projects/book/manuscript/research_runs/run.cancel'}
    new = relocate_run(old, manuscript)
    assert new['producer_base'] == str(tmp_path / 'projects/book')
    assert new['result_absolute'] == str(manuscript / 'research_runs/run.result.json')
    assert old['producer_base'] == '/original/projects/book'
    assert new['recorded_original_locations'] == old
    assert scoped_path(manuscript, old['result_absolute']) == manuscript / 'research_runs/run.result.json'
    assert scoped_path(manuscript, '/original/other-project/secret') is None


def test_path_aliases_survive_a_different_operating_system(tmp_path):
    manifest = {'schema': 'laplace.writing-portability/1', 'directory_aliases': {
        '/original': '.', 'C:\\previous\\workspace': '.'}}
    (tmp_path / 'writing-portability.json').write_text(json.dumps(manifest))
    base = tmp_path / 'project'
    base.mkdir()
    assert scoped_path(base, 'C:\\previous\\workspace\\project\\result.json') == base / 'result.json'
    assert scoped_path(base, '\\original\\project\\result.json') == base / 'result.json'
    assert scoped_path(base, '/original/project/result.json') == base / 'result.json'


def test_alias_versions_resolve_by_recorded_pin_only(tmp_path):
    current = tmp_path / 'docs' / 'guide.md'; current.parent.mkdir(); current.write_bytes(b'current')
    companion = tmp_path / 'supplementary_sources' / ('a' * 64 + '.md'); companion.parent.mkdir(); companion.write_bytes(b'original')
    (tmp_path / 'writing-portability.json').write_text(json.dumps({
        'schema': 'laplace.writing-portability/1',
        'source_aliases': {'/original/docs/guide.md': {'path': 'docs/guide.md', 'original_sha256': 'sha256:' + 'c' * 64,
                            'versions': {'sha256:' + 'a' * 64: {'path': 'supplementary_sources/' + 'a' * 64 + '.md'},
                                         'sha256:' + 'e' * 64: {'path': '../escape.md'}}}}}))
    assert source_path('/original/docs/guide.md', tmp_path) == current
    assert source_path('/original/docs/guide.md', tmp_path, sha256='sha256:' + 'c' * 64) == current
    assert source_path('/original/docs/guide.md', tmp_path, sha256='A' * 64) == companion, 'bare and upper-case pins normalise'
    assert source_path('/original/docs/guide.md', tmp_path, sha256='sha256:' + 'f' * 64) == current, 'an unknown pin is the primary target'
    with pytest.raises(ValueError, match='inside'):
        source_path('/original/docs/guide.md', tmp_path, sha256='sha256:' + 'e' * 64)
    assert source_path('docs/guide.md', tmp_path, sha256='sha256:' + 'a' * 64) == current, 'a relative current path never follows a version'
