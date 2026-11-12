"""Adjacent diagnostic contracts closed from the 2026-10-13 guide-authoring dossiers."""
import pytest
from pathlib import Path
from laplace.manuscript import proposal_preflight as preflight
from laplace.projects import writing_sources
from laplace.native import tools as writing_tools


def test_duplicate_label_refusals_name_the_label_and_its_source_occurrences():
    before = {'chapters/one.tex': 'One.\n', 'chapters/two.tex': 'Two.\n\\label{fig:shared}\n'}
    after = {**before, 'chapters/one.tex': 'One.\n\\label{fig:shared}\n\\label{fig:shared}\n'}
    errors = preflight.duplicate_label_errors(before, after)
    assert errors == ['replacement creates duplicate canonical labels across source files: fig:shared (chapters/one.tex x2, chapters/two.tex)']
    assert preflight.duplicate_label_errors(before, before) == []
    staged = preflight.staged_integrity_errors('A.\n\\label{eq:a}\n', 'A.\n\\label{eq:a}\n\\label{eq:a}\n')
    assert staged == ['replacement creates duplicate canonical labels: eq:a (x2 in this file)']
    many = {'a.tex': ''.join('\\label{l%d}\n' % i for i in range(10))}
    doubled = {'a.tex': many['a.tex'] * 2}
    assert preflight.duplicate_label_errors(many, doubled)[0].endswith('and 2 more')


def test_review_mode_write_refusal_routes_findings_to_note_and_task(tmp_path):
    response = writing_tools.failure_response(tmp_path, 'p', 'review', 'store_artifact', {'path': 'findings.json', 'before': None, 'content': '{}'},
        ValueError('Independent review can save findings and tasks; reviewed artifacts stay unchanged.'))
    routes = response['review_routes']
    assert routes['findings']['operation'] == 'note' and routes['findings']['payload']['scope'] == 'project'
    assert routes['follow_up']['operation'] == 'task' and 'author' in routes['author_follow_through']
    assert response['contract']['permitted'] is False
    allowed = writing_tools.failure_response(tmp_path, 'p', 'review', 'note', {}, ValueError('note needs text'))
    assert 'review_routes' not in allowed
    working = writing_tools.failure_response(tmp_path, 'p', 'work', 'store_artifact', {'path': 'x'}, ValueError('guard'))
    assert 'review_routes' not in working


@pytest.fixture
def roots(tmp_path):
    root = tmp_path / 'laplace'; root.mkdir(); (root / 'profiles').mkdir()
    repo = tmp_path / 'code'; repo.mkdir()
    (repo / 'a.tex').write_text('Alpha line\n'); (repo / 'b.md').write_text('Beta claim\n'); (repo / 'sub').mkdir(); (repo / 'sub/c.tex').write_text('Gamma claim\n')
    (root / 'profiles/writing_sources.json').write_text('{"repositories": {"code": "%s"}}' % repo)
    return root


def test_repository_omitted_action_with_selectors_names_the_exact_actions(roots):
    with pytest.raises(ValueError, match=r'requires action when selectors are given \(received line_end, line_start, path, repository\)') as refused:
        writing_sources.execute(roots, {'repository': 'code', 'path': 'a.tex', 'line_start': 1, 'line_end': 3})
    assert 'source {files:[path], line_start, line_end}' in str(refused.value) and 'action:"read"' in str(refused.value)
    assert writing_sources.execute(roots, {'action': 'list'})['repositories'][0]['id'] == 'code'
    assert writing_sources.execute(roots, {})['repositories']


def test_glob_and_search_semantics_return_declared_empty_results_not_errors(roots):
    files = writing_sources.execute(roots, {'action': 'files', 'repository': 'code', 'glob': '*.tex'})
    assert sorted(row['path'] for row in files['matches']) == ['a.tex', 'sub/c.tex']
    nothing = writing_sources.execute(roots, {'action': 'files', 'repository': 'code', 'glob': '*.bib'})
    assert nothing['matches'] == [] and nothing['next_offset'] is None and nothing['truncated'] is False and nothing['timed_out'] is False
    hits = writing_sources.execute(roots, {'action': 'search', 'repository': 'code', 'query': 'claim', 'glob': '*.tex'})
    assert [row['path'] for row in hits['matches']] == ['sub/c.tex'] and hits['matches'][0]['line'] == 1
    miss = writing_sources.execute(roots, {'action': 'search', 'repository': 'code', 'query': 'absent-literal'})
    assert miss['matches'] == [] and miss['query'] == 'absent-literal'
    # filename query is a case-insensitive substring over the path, not a glob
    assert [row['path'] for row in writing_sources.execute(roots, {'action': 'files', 'repository': 'code', 'query': 'C.TEX'})['matches']] == ['sub/c.tex']
    assert writing_sources.operation_contract()['operations']['files']['units'].startswith('offset/limit count matching file rows')
