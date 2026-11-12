import json
from pathlib import Path

from laplace.manuscript import manuscript_fragments, review_surface
from laplace.projects import library as writing_projects
from laplace.pipeline import authoring, edits, ledger


def _project(root: Path) -> Path:
    source = root / 'sources' / 'book'
    source.mkdir(parents=True)
    (source / 'main.tex').write_text(
        '\\documentclass{article}\n\\begin{document}\nCurrent paragraph.\n\\end{document}\n')
    status, result = writing_projects.import_source({
        'name': 'book', 'title': 'Book', 'root': 'sources/book/main.tex', 'editable': True}, root)
    assert status == 201, result
    return source


def test_baseline_change_preview_returns_typed_before_after_blocks(tmp_path, monkeypatch):
    _project(tmp_path)
    monkeypatch.setattr(review_surface, 'hand_hunks', lambda corpus, file, root: {
        'ok': True, 'file': file, 'attributed': True, 'whole_file': False,
        'baseline': {'id': 'VERSION-1', 'kind': 'machine', 'ts': 'now'},
        'counts': {'passages': 1, 'lines': 1}, 'note': 'one passage',
        'hunks': [{'start': 3, 'end': 3, 'before': ['Earlier paragraph.'],
                   'after': ['Current paragraph.']}],
    })

    value = manuscript_fragments.change_preview('book', {'file': 'main.tex'}, tmp_path)

    assert value['mode'] == 'baseline' and value['baseline']['id'] == 'VERSION-1'
    assert value['hunks'][0]['anchor'] == {'file': 'main.tex', 'line_start': 3, 'line_end': 3}
    assert value['hunks'][0]['before_blocks'][0]['kind'] == 'para'
    assert value['hunks'][0]['after_blocks'][0]['kind'] == 'para'


def test_exact_applied_edit_preview_relocates_only_unique_current_after(tmp_path):
    source = _project(tmp_path)
    state_dir = tmp_path / 'writing_projects' / 'book'
    feedback = state_dir / 'feedback' / 'feedback.jsonl'
    row = edits.make_author_edit('section', 'p1', 'main.tex', 'Earlier paragraph.',
                                 'Current paragraph.', project='book')
    ledger.append_jsonl(feedback, row)

    value = manuscript_fragments.change_preview('book', {'id': row['id']}, tmp_path)

    assert value['mode'] == 'correction' and value['locatable'] is True
    assert value['hunks'][0]['anchor']['line_start'] == 3
    assert value['hunks'][0]['before_blocks'][0]['kind'] == 'para'
    assert value['hunks'][0]['after_blocks'][0]['kind'] == 'para'
    assert value['correction']['applied'] is True

    (source / 'main.tex').write_text((source / 'main.tex').read_text().replace(
        '\\end{document}', 'Current paragraph.\n\\end{document}'))
    ambiguous = manuscript_fragments.change_preview('book', {'id': row['id']}, tmp_path)
    assert ambiguous['locatable'] is False


def test_author_structure_feedback_is_applied_history_not_active_context(tmp_path):
    _project(tmp_path)
    state_dir = tmp_path / 'writing_projects' / 'book'
    feedback = state_dir / 'feedback' / 'feedback.jsonl'
    ledger.append_jsonl(feedback, {
        'id': 'FB-structure', 'project': 'book',
        'kind': 'author-structure', 'comment': 'Created empty chapter.', 'by': 'author',
        'status': 'open', 'anchor': {'file': 'main.tex', 'before': 'A', 'after': 'B'}})

    state = authoring.load('book', tmp_path)
    context = authoring.build_context('book', {'files': ['main.tex']}, tmp_path)
    item = next(row for row in state['corrections'] if row['id'] == 'FB-structure')

    assert item['applied'] is True and item['kind'] == 'author-structure'
    assert 'FB-structure' not in context['consumed']['corrections']


def test_whole_file_atomic_history_is_projected_as_sparse_delete_marker(tmp_path):
    source = _project(tmp_path)
    state_dir = tmp_path / 'writing_projects' / 'book'
    feedback = state_dir / 'feedback' / 'feedback.jsonl'
    after = (source / 'main.tex').read_text()
    before = after.replace('Current paragraph.', 'Deleted paragraph.\nCurrent paragraph.')
    ledger.append_jsonl(feedback, {
        'id': 'FB-source-edit', 'project': 'book', 'kind': 'source-edit',
        'comment': 'Deleted one paragraph.', 'by': 'author', 'status': 'resolved',
        'before': before, 'after': after, 'anchor': {'file': 'main.tex'}})

    value = manuscript_fragments.change_preview('book', {'id': 'FB-source-edit'}, tmp_path)

    assert value['locatable'] is True and len(value['hunks']) == 1
    hunk = value['hunks'][0]
    assert hunk['deleted'] is True
    assert hunk['before'] == 'Deleted paragraph.' and hunk['after'] == ''
    assert hunk['before_blocks'][0]['kind'] == 'para' and hunk['after_blocks'] == []
