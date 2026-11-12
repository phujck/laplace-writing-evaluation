"""Bounded regressions replaying the archived 6 October Spanspermia facts."""
import json
from pathlib import Path

import pytest

from laplace.manuscript import manuscript_proposals as proposals
from laplace.writing import records as writing_records
from laplace.writing import session_reads
from laplace.writing import session_projection
from laplace.writing.records import _fold as records_fold
from test_manuscript_proposals import fixture
from test_writing_controller import _bind_rewrite_fixture,_import_project,_seed_revision

ARCHIVE = json.loads((Path(__file__).parent / 'fixtures/spanspermia_editor_archive.json').read_text())


def test_all_six_archived_versions_remain_reachable_after_last_edit_is_accepted(tmp_path):
    _import_project(tmp_path)
    turn=_seed_revision(tmp_path,'fixture',[],context={})
    # Replay the exact archived rows as legacy history, without sealing them
    # against this fixture's current context.
    writing_records.bank(tmp_path, {'record': 'writing-reply', 'id': 'WR-reset-seed',
        'turn_id': turn, 'project': 'fixture', 'proposal': {'answer': 'Finished.', 'edits': []}})
    from laplace.core.records import journal
    for row in ARCHIVE['proposals']:
        journal.bank_row('contract/talk.jsonl', {**row, 'turn_id': turn, 'project': 'fixture'},root=tmp_path)
    writing_records.bank(tmp_path, {**ARCHIVE['decisions'][0], 'turn_id': turn, 'project': 'fixture'})
    pending = session_reads.pending_proposals(tmp_path, 'fixture')
    expected = {records_fold._proposal_digest(row['proposal']) for row in ARCHIVE['proposals']}
    assert {item['proposal_version'] for item in pending['proposals']} == expected
    assert sum(item['edit_count'] for item in pending['proposals']) == 10
    # The archived decision names another version digest. It remains history
    # and cannot be reassigned to an identically addressed retained edit.
    assert session_reads._records(tmp_path)['turns'][turn]['proposal_decisions'][0]['proposal_version'] not in expected
    # A provider's empty final response has no human decision authority.
    writing_records.bank(tmp_path, {'record': 'writing-reply', 'id': 'WR-empty-final',
        'turn_id': turn, 'project': 'fixture', 'proposal': {'answer': 'Finished.', 'edits': []}})
    assert {item['proposal_version'] for item in session_reads.pending_proposals(tmp_path, 'fixture')['proposals']} == expected
    assert all(records_fold._proposal_digest(row['proposal']) == row['proposal_version'] for row in pending['proposals'])


def test_earlier_same_passage_version_can_be_merged_and_history_keeps_exact_changes(tmp_path, monkeypatch):
    manuscript, turn, edits = fixture(tmp_path)
    _bind_rewrite_fixture(monkeypatch, manuscript)
    earlier = proposals.preview(tmp_path, 'fixture', turn)
    alternative_receipt=writing_records.bank(tmp_path, {'record': 'writing-proposal', 'id': 'PROP-redraft',
        'project': 'fixture', 'turn_id': turn,
        'proposal': {'answer': 'Another version.', 'edits': [{**edits[0], 'after': 'Different suggestion.'}]}})
    selected = proposals.preview(tmp_path, 'fixture', turn, earlier['proposal_version'])
    row = selected['edits'][0]
    assert row['after'] == edits[0]['after'] and row['current_before'] == edits[0]['before']
    merged = 'The author has edited the suggestion.'
    result = proposals.decide(tmp_path, 'fixture', {'turn_id': turn, 'edit_id': row['edit_id'],
        'proposal_version': selected['proposal_version'], 'decision': 'merge',
        'review_token': row['review_token'], 'merged_after': merged})
    assert merged in (manuscript / 'main.tex').read_text()
    actions = session_projection.editor_actions(session_reads._records(tmp_path)['turns'][turn])
    application = next(action for action in actions if action['outcome'].get('application_id') == result['application']['id'])
    assert application['outcome']['edits'][0]['before'] == edits[0]['before']
    assert application['outcome']['edits'][0]['after'] == merged
    assert application['outcome']['proposal_version'] == earlier['proposal_version']
    recorded = proposals.preview(tmp_path, 'fixture', turn, earlier['proposal_version'])
    assert recorded['edits'][0]['after'] == merged
    # Source consumption retires the retained alternative; it is not pending
    # work again after an undo, nor a source replacement permission.
    alternative=proposals.preview(tmp_path,'fixture',turn,alternative_receipt['proposal_instance_version'])['edits'][0]
    assert alternative['status']=='consumed-alternative' and alternative['lifecycle']=='retained-history'
    assert not alternative['allowed_actions']


def test_edit_the_clean_edit_refuses_stale_review_and_preserves_author_text(tmp_path, monkeypatch):
    manuscript, turn, _edits = fixture(tmp_path)
    _bind_rewrite_fixture(monkeypatch, manuscript)
    review = proposals.preview(tmp_path, 'fixture', turn)
    path = manuscript / 'main.tex'
    path.write_text(path.read_text().replace('First paragraph.', 'Author has revised this.'))
    original = path.read_bytes()
    with pytest.raises(ValueError, match='current passage changed|consumed source changed outside'):
        proposals.decide(tmp_path, 'fixture', {'turn_id': turn,
            'edit_id': review['edits'][0]['edit_id'], 'proposal_version': review['proposal_version'],
            'decision': 'merge', 'review_token': review['edits'][0]['review_token'], 'merged_after': 'Stale edit.'})
    assert path.read_bytes() == original


def test_archived_render_failures_without_a_journal_cut_remain_historical():
    rows = [row for row in ARCHIVE['attempts'] if row['turn_id'] == ARCHIVE['turn_id']]
    failures = [row for row in rows if row['record'] == 'writing-tool-failure' and row['operation'] == 'visual_render']
    actions = [row for row in rows if row['record'] == 'writing-tool-action' and row['operation'] == 'visual_render']
    turn = {'tool_failures': failures, 'tool_actions': actions}
    result = session_reads._turn_failure_rows(turn)
    assert len(result) == 5 and all(not row['resolved_later'] for row in result)
    assert all(row['related_action'] is None for row in result), 'timestamps cannot mint an exact journal read'
