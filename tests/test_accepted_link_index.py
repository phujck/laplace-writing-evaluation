"""Scoped accepted declarations share the journal index and exact body owner."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from laplace.manuscript import manuscript_proposals, manuscript_source, proposal_basis
from laplace.writing.records import _bank as records_bank
from laplace.representation import writing_bodies as bodies
from laplace.writing import records


def _fixture(root):
    manuscript = root / 'book' / 'manuscript'
    manuscript.mkdir(parents=True)
    (root / 'registry_projects.json').write_text(json.dumps({'projects': [{
        'name': 'book', 'kind': 'conceptric', 'project_dir': 'book',
        'tex_root': 'book/manuscript', 'manifest': {'document': {'root': 'book/manuscript/main.tex'}}}]}))
    (manuscript / 'main.tex').write_text('\\documentclass{book}\n\\begin{document}\nAccepted text.\n\\end{document}\n')
    return manuscript


def _edit(file='main.tex', after='Accepted text.'):
    return {'file': file, 'line_start': 3, 'line_end': 3, 'before': 'Old text.', 'after': after,
            'develops': [{'id': 'res:one', 'content_revision': 'sha256:' + '1' * 64}],
            'evidence_refs': [{'id': 'result:one', 'revision': 'sha256:' + '2' * 64}]}


def _rows(root, app='WA-selected', edits=None, document=True):
    turn = {'record': 'writing-turn', 'id': 'WT-' + app, 'session_id': 'WS-' + app, 'project': 'book'}
    if document:
        turn['document'] = manuscript_source.resolve('book', repo_root=root)
    return [{'record': 'writing-session', 'id': 'WS-' + app, 'project': 'book'}, turn,
            {'record': 'writing-application', 'id': app, 'turn_id': turn['id'],
             'project': 'book', 'complete': True, 'edits': edits or [_edit()]}]


def _append(root, rows):
    path = root / 'contract' / 'talk.jsonl'
    path.parent.mkdir(exist_ok=True)
    with path.open('a', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')


def _current(monkeypatch):
    monkeypatch.setattr(proposal_basis, 'assess', lambda *args, **kwargs: {'errors': []})


def test_scoped_read_opens_selected_fields_only_with_large_unrelated_history(tmp_path, monkeypatch):
    _fixture(tmp_path)
    _current(monkeypatch)
    selected = _rows(tmp_path)
    selected[-1]['edits'][0]['reason'] = 'selected proposal explanation ' * 500
    selected[-1]['receipts'] = [{'body': 'unused receipt ' * 1000}]
    unrelated = []
    for index in range(1200):
        row = _rows(tmp_path, 'WA-unrelated-' + str(index), [_edit('elsewhere.tex')])
        # The same project and file basename in another project must both stay cold.
        if index % 2:
            for item in row:
                item['project'] = 'other'
            row[-1]['edits'][0]['file'] = 'main.tex'
        row[-1]['edits'][0]['reason'] = 'unrelated retained prose ' * 500
        unrelated.extend(row)
    _append(tmp_path, [records_bank.prepare_custody_row(tmp_path, row) for row in unrelated + selected])
    opened = []
    read_bytes = bodies.read_bytes
    monkeypatch.setattr(bodies, 'read_bytes', lambda value, root: (opened.append(value['content_handle']), read_bytes(value, root))[1])
    monkeypatch.setattr(records, 'fold_records', lambda *args, **kwargs: pytest.fail('global body fold'))
    candidates = records.accepted_link_candidates(tmp_path, 'book', files=['main.tex'])
    assert candidates['pagination']['candidate_total'] == 1
    assert candidates['coverage']['body_reads'] == 0 and opened == []
    idx = records.index(tmp_path)
    first_stats = dict(idx.stats)
    result = proposal_basis.accepted_links(tmp_path, 'book', files=['main.tex'])
    assert len(result['links']) == 1 and result['links'][0]['status'] == 'LIVE_CURRENT_BASIS'
    assert result['coverage']['source_files_read'] == 1
    assert len(opened) == 1  # selected edits only; selected receipts are lazy
    assert idx.stats['bytes_read'] == first_stats['bytes_read']
    assert idx.stats['scans'] == 1 and idx.stats['custody_bodies_opened'] == 1
    assert idx.stats['selected_rows_read'] == 3  # application and original turn/session
    assert result['links'][0]['develops'] == _edit()['develops']


def test_pagination_is_stable_across_unrelated_append_and_preserves_remaining(tmp_path):
    _fixture(tmp_path)
    for index in range(5):
        _append(tmp_path, _rows(tmp_path, 'WA-' + str(index)))
    page = records.accepted_link_candidates(tmp_path, 'book', files=['main.tex'], limit=2)
    assert page['pagination']['candidate_total'] == 5
    assert page['pagination']['remaining_candidates'] == 3
    assert page['coverage']['status'] == 'PARTIAL'
    _append(tmp_path, _rows(tmp_path, 'WA-other', [_edit('other.tex')]))
    following = records.accepted_link_candidates(tmp_path, 'book', files=['main.tex'], limit=2,
        offset=page['pagination']['next_offset'], as_of=page['as_of'])
    assert following['pagination']['candidate_total'] == 5
    assert {row['application_id'] for row in page['candidates']}.isdisjoint(
        row['application_id'] for row in following['candidates'])
    with pytest.raises(ValueError, match='another scope'):
        records.accepted_link_candidates(tmp_path, 'book', files=['other.tex'], as_of=page['as_of'])


def test_replaced_selected_basis_refuses_cut_and_exact_field_pin(tmp_path):
    _fixture(tmp_path)
    rows = _rows(tmp_path)
    _append(tmp_path, rows)
    page = records.accepted_link_candidates(tmp_path, 'book', files=['main.tex'])
    handle = page['candidates'][0]['application_read']
    rows[-1]['edits'][0]['develops'][0]['content_revision'] = 'changed'
    (tmp_path / 'contract/talk.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
    with pytest.raises(ValueError, match='basis changed'):
        records.accepted_link_candidates(tmp_path, 'book', files=['main.tex'], as_of=page['as_of'])
    with pytest.raises(ValueError, match='changed since discovery'):
        records.selected_journal_fields('book', handle['id'], tmp_path, fields=['edits'], expected_row_sha256=handle['row_sha256'])


def test_legacy_headers_missing_carriers_and_other_editions_remain_explicit(tmp_path, monkeypatch):
    _fixture(tmp_path)
    _current(monkeypatch)
    legacy = _rows(tmp_path, 'WA-legacy')
    legacy[-1] = records_bank.prepare_custody_row(tmp_path, legacy[-1])
    # Actual historical header predates declarations; its exact retained body has them.
    edit = _edit()
    edit['reason'] = 'legacy retained body ' * 1000
    legacy[-1] = records_bank.prepare_custody_row(tmp_path, {**legacy[-1], 'edits': [edit]})
    for header in legacy[-1]['edit_projection']:
        for key in ('declaration_schema', 'develops', 'evidence_refs'):
            header.pop(key)
    missing = _rows(tmp_path, 'WA-missing')
    missing[-1].pop('edits')
    unpinned = _rows(tmp_path, 'WA-unpinned', document=False)
    edition = _rows(tmp_path, 'WA-former')
    edition[1]['document']['edition'] = 'former'
    _append(tmp_path, legacy + missing + unpinned + edition)
    candidates = records.accepted_link_candidates(tmp_path, 'book', files=['main.tex'])
    assert candidates['coverage']['unknown_scope_candidates'] == 2
    assert candidates['coverage']['legacy_declaration_candidates'] == 2
    links = proposal_basis.accepted_links(tmp_path, 'book', files=['main.tex'])['links']
    by_id = {row['application_id']: row for row in links}
    assert by_id['WA-legacy']['develops'] == edit['develops']
    assert by_id['WA-legacy']['status'] == 'LIVE_CURRENT_BASIS'
    assert by_id['WA-missing']['status'] == 'LEGACY_CARRIER_UNAVAILABLE'
    assert by_id['WA-unpinned']['status'] == 'UNPINNED_OR_OTHER_EDITION'
    assert by_id['WA-former']['status'] == 'UNPINNED_OR_OTHER_EDITION'
    assert all(row['read_more']['operation'] == 'author_history' for row in links)


def test_exact_proposal_carrier_recovers_only_consumed_components(tmp_path, monkeypatch):
    _fixture(tmp_path)
    _current(monkeypatch)
    rows = _rows(tmp_path)
    proposal = {'edits': [_edit(), _edit('other.tex', 'Other text.')]}
    carrier = {'record': 'writing-proposal', 'id': 'PROP-exact', 'project': 'book',
               'turn_id': rows[1]['id'], 'proposal_instance_version': 'version-one', 'proposal': proposal}
    rows[-1].pop('edits')
    rows[-1].update(candidate_version='version-one', candidate_edit_ids=[manuscript_proposals.edit_id(proposal['edits'][0])])
    _append(tmp_path, rows[:2] + [carrier, rows[-1]])
    result = proposal_basis.accepted_links(tmp_path, 'book', files=['main.tex'])
    assert len(result['links']) == 1 and result['links'][0]['carrier_read']['id'] == 'PROP-exact'
    assert result['links'][0]['develops'] == proposal['edits'][0]['develops']
    assert records.accepted_link_candidates(tmp_path, 'book', files=['other.tex'])['candidates'] == []


def test_ambiguous_record_and_missing_body_never_become_current(tmp_path, monkeypatch):
    _fixture(tmp_path)
    _current(monkeypatch)
    rows = _rows(tmp_path)
    _append(tmp_path, rows + [copy.deepcopy(rows[-1])])
    result = proposal_basis.accepted_links(tmp_path, 'book', files=['main.tex'])
    assert all(row['status'] == 'RECORD_UNAVAILABLE' for row in result['links'])
    other = _rows(tmp_path, 'WA-lost')
    other[-1]['edits'][0]['reason'] = 'lost retained body ' * 1000
    encoded = records_bank.prepare_custody_row(tmp_path, other[-1])
    other[-1] = encoded
    _append(tmp_path, other)
    monkeypatch.setattr(bodies, 'read_bytes', lambda *args: (_ for _ in ()).throw(OSError('missing body')))
    result = proposal_basis.accepted_links(tmp_path, 'book', files=['main.tex'], application_id='WA-lost')
    assert result['links'][0]['status'] == 'RECORD_UNAVAILABLE'


def test_disjoint_preamble_change_preserves_unique_text_but_duplicate_does_not(tmp_path, monkeypatch):
    manuscript = _fixture(tmp_path)
    _current(monkeypatch)
    _append(tmp_path, _rows(tmp_path))
    path = manuscript / 'main.tex'
    path.write_text('% independent preamble change\n' + path.read_text())
    result = proposal_basis.accepted_links(tmp_path, 'book', files=['main.tex'])
    assert result['links'][0]['status'] == 'LIVE_CURRENT_BASIS'
    assert result['links'][0]['anchor']['line_start'] == 4
    path.write_text(path.read_text() + 'Accepted text.\n')
    assert proposal_basis.accepted_links(tmp_path, 'book')['links'][0]['status'] == 'STALE_OR_AMBIGUOUS'


def test_title_only_legacy_placement_does_not_award_current_scientific_basis(tmp_path):
    from test_project_structure import _fixture as scientific_fixture
    from laplace.research import concepts as concepts_surface
    manuscript = scientific_fixture(tmp_path)
    path = manuscript / 'projection_plan.json'
    plan = json.loads(path.read_text())
    for section in plan['sections']:
        section.pop('source_file', None)
        section.pop('source_label', None)
    path.write_text(json.dumps(plan))
    edit = _edit('N1.tex', 'Opening prose.')
    edit['develops'] = [{'id': 'res:one', 'content_revision': concepts_surface.state(
        'book', node='res:one', root=tmp_path)['content_revision']}]
    edit['evidence_refs'] = []
    _append(tmp_path, _rows(tmp_path, edits=[edit]))
    result = proposal_basis.accepted_links(tmp_path, 'book', files=['N1.tex'])
    assert result['links'][0]['status'] == 'LIVE_TEXT_STALE_BASIS'
    assert any('not canonically placed' in error for error in result['links'][0]['basis']['errors'])


def test_exact_recorded_path_aliases_do_not_merge_other_directories_or_editions(tmp_path, monkeypatch):
    manuscript = _fixture(tmp_path)
    _current(monkeypatch)
    _append(tmp_path, _rows(tmp_path, 'WA-relative'))
    _append(tmp_path, _rows(tmp_path, 'WA-qualified', [_edit('book/manuscript/main.tex')]))
    for side in ('left', 'right'):
        (manuscript / side).mkdir()
        (manuscript / side / 'same.tex').write_text('Accepted text.\n')
        _append(tmp_path, _rows(tmp_path, 'WA-' + side, [_edit(side + '/same.tex')]))
    former = _rows(tmp_path, 'WA-former-path')
    former[1]['document'].update(manuscript_dir='book/former', root='book/former/main.tex', edition='former')
    _append(tmp_path, former)
    relative = proposal_basis.accepted_links(tmp_path, 'book', files=['main.tex'])
    qualified = proposal_basis.accepted_links(tmp_path, 'book', files=['book/manuscript/main.tex'])
    assert {row['application_id'] for row in relative['links']} == {'WA-relative', 'WA-qualified'}
    assert relative['links'] == qualified['links']
    assert all(row['anchor']['file'] == 'book/manuscript/main.tex' for row in relative['links'])
    assert records.accepted_link_candidates(tmp_path, 'book', files=['same.tex'])['candidates'] == []
    left = proposal_basis.accepted_links(tmp_path, 'book', files=['book/manuscript/left/same.tex'])
    assert [row['application_id'] for row in left['links']] == ['WA-left']
    old = proposal_basis.accepted_links(tmp_path, 'book', files=['book/former/main.tex'])
    assert [row['application_id'] for row in old['links']] == ['WA-former-path']
    assert old['links'][0]['status'] == 'UNPINNED_OR_OTHER_EDITION'


def test_passage_selects_current_hash_before_paging_older_same_file_declaration(tmp_path, monkeypatch):
    manuscript = _fixture(tmp_path)
    monkeypatch.setattr(proposal_basis, 'assess', lambda *args, **kwargs: {
        'errors': [], 'automatic_sections': [], 'automatic_section_concepts': [], 'limitations': []})
    _append(tmp_path, _rows(tmp_path, 'WA-old-overlap'))
    texts = ['Newer disjoint passage ' + str(index) for index in range(65)]
    for index, text in enumerate(texts):
        _append(tmp_path, _rows(tmp_path, 'WA-newer-' + str(index), [_edit(after=text)]))
    path = manuscript / 'main.tex'
    path.write_text('% preamble moves original line\n' + path.read_text() + '\n'.join(texts) + '\n')
    context = proposal_basis.passage_context(tmp_path, 'book', {
        'file': 'book/manuscript/main.tex', 'line_start': 4, 'line_end': 4}, {'obligations': []})
    assert [row['application_id'] for row in context['accepted_proposals']] == ['WA-old-overlap']
    assert context['accepted_proposals'][0]['status'] == 'LIVE_CURRENT_BASIS'
    assert context['accepted_proposal_pagination']['candidate_total'] == 1
    assert context['accepted_proposal_coverage']['body_reads'] == 1
    assert context['accepted_proposal_coverage']['status'] == 'COMPLETE'
    assert context['accepted_proposal_coverage']['source_files_read'] == 1


def test_span_budget_preserves_explicit_uncertain_scope_instead_of_false_empty(tmp_path, monkeypatch):
    manuscript = _fixture(tmp_path)
    monkeypatch.setattr(proposal_basis, 'assess', lambda *args, **kwargs: {
        'errors': [], 'automatic_sections': [], 'automatic_section_concepts': [], 'limitations': []})
    long_edit = _edit(after='\n'.join(['outside'] * 2000))
    _append(tmp_path, _rows(tmp_path, 'WA-large-span', [long_edit]))
    # The current file is deliberately large enough to exceed the metadata hash-work bound.
    (manuscript / 'main.tex').write_text('Accepted text.\n' + 'outside\n' * 2000)
    result = proposal_basis.accepted_links(tmp_path, 'book', files=['main.tex'],
        _span={'file': 'main.tex', 'line_start': 1, 'line_end': 1})
    assert result['coverage']['status'] == 'PARTIAL_CURRENT_SCOPE'
    assert result['coverage']['current_span']['incomplete_widths'] == [2000]
    assert result['links'][0]['application_id'] == 'WA-large-span'
    assert result['links'][0]['read_more']['operation'] == 'author_history'


def test_partial_empty_passage_keeps_callable_exact_history_recovery(tmp_path, monkeypatch):
    from laplace.work import history as author_history
    from laplace.native import tools as writing_tools
    _fixture(tmp_path)
    rows = _rows(tmp_path)
    rows[-1]['edits'][0].update(develops=[], evidence_refs=[],
                               reason='Historical unclassified editorial body ' * 500)
    rows[-1] = records_bank.prepare_custody_row(tmp_path, rows[-1])
    for edit in rows[-1]['edit_projection']:
        for key in ('declaration_schema', 'develops', 'evidence_refs', 'after_line_count'):
            edit.pop(key, None)
    _append(tmp_path, rows)
    monkeypatch.setattr(records, 'fold_records', lambda *args, **kwargs: pytest.fail('global body fold'))
    monkeypatch.setattr(author_history, '_all', lambda *args, **kwargs: pytest.fail('whole project history'))
    context = proposal_basis.passage_context(tmp_path, 'book', {
        'file': 'book/manuscript/main.tex', 'line_start': 3, 'line_end': 3}, {'obligations': []})
    assert context['accepted_proposals'] == []
    assert context['accepted_proposal_coverage']['status'] == 'PARTIAL_CURRENT_SCOPE'
    assert context['accepted_proposal_pagination']['candidate_total'] == 1
    assert context['accepted_proposal_pagination']['remaining_candidates'] == 0
    recovery = context['accepted_proposal_recovery']
    assert len(recovery) == 1
    assert recovery[0]['scope'] == 'RETAINED_CANDIDATE_INSPECTION'
    assert recovery[0]['passage_membership'] == 'NOT_ASSERTED'
    assert recovery[0]['declaration_status'] == 'NO_DECLARATION_IN_SELECTED_EDITS'
    handle = recovery[0]['read_more']
    assert handle == {'operation': 'author_history', 'payload': {
        'view': 'record', 'id': 'activity:journal:WA-selected'}}
    inspected = writing_tools.execute(tmp_path, 'book', 'work', handle['operation'], handle['payload'])
    assert inspected['record_kind'] == 'writing-application'
    assert inspected['record']['id'] == rows[-1]['id']
    assert inspected['record']['edits'][0]['develops'] == []


def test_index_preserves_optional_spine_observation_without_graph_bodies(tmp_path):
    _fixture(tmp_path)
    rows = _rows(tmp_path)
    observation = {'plan_revision': 'sha256:' + '1' * 64,
                   'spine_revision': 'sha256:' + '2' * 64,
                   'selection_identity': 'sha256:' + '3' * 64,
                   'source_files': [{'file': 'book/manuscript/main.tex',
                                     'source_digest': 'sha256:' + '4' * 64}]}
    rows[1]['workspace_context'] = {'surface': 'structure', 'structure_observation': {
        **observation, 'graph_body': 'Must not be retained'}}
    _append(tmp_path, rows)
    indexed = records.index(tmp_path).turns[rows[1]['id']]['workspace_context']['structure_observation']
    assert indexed == observation
