"""A Work review-setup read must not poison a later manuscript proposal."""
import pytest

from laplace.manuscript import manuscript_proposals as proposals, proposal_currentness
from laplace.native import tools
from laplace.work import project_work
from laplace.writing import records, operations
from laplace.writing.records._fold import _proposal_digest
from test_proposal_lifecycle import clear, setup, decide
from test_writing_controller import _bind_rewrite_fixture


def candidate_after_review_setup(root, monkeypatch):
    manuscript, turn, changes, _ = setup(root)
    calls = _bind_rewrite_fixture(monkeypatch, manuscript)
    work = project_work.task('fixture', {'id': 'WORK-read-setup',
        'title': 'Review this example', 'goal': 'Inspect the source-bound change.'}, root)
    tools.execute(root, 'fixture', 'revise', 'work_delivery',
                  {'action': 'review-setup', 'work_id': work['id']}, turn_id=turn)
    proposal = {'answer': 'Clarify the inspected premise.', 'edits': changes}
    records.bank(root, {'record': 'writing-proposal', 'id': 'PROP-after-setup',
                       'turn_id': turn, 'project': 'fixture',
                       'proposal': proposal})
    return turn, calls, work, _proposal_digest(proposal)


def test_real_review_setup_read_then_proposal_can_apply(tmp_path, monkeypatch):
    turn, calls, _, version = candidate_after_review_setup(tmp_path, monkeypatch)
    preview = proposals.preview(tmp_path, 'fixture', turn, version)
    row = preview['edits'][0]
    assert row['basis_currentness'] == 'CURRENT', row
    assert 'accept' in row['allowed_actions']
    result = decide(tmp_path, turn, row, preview['proposal_version'])
    assert result['application'] and len(calls) == 1


def test_changed_review_setup_basis_still_refuses_without_write(tmp_path, monkeypatch):
    turn, calls, work, version = candidate_after_review_setup(tmp_path, monkeypatch)
    current = project_work._tasks('fixture', tmp_path)[work['id']]
    project_work.task('fixture', {'id': work['id'],
        'expected_work_revision': project_work._task_revision(current),
        'goal': 'The review now consumes a different purpose.'}, tmp_path)
    preview = proposals.preview(tmp_path, 'fixture', turn, version)
    row = preview['edits'][0]
    assert row['basis_currentness'] != 'CURRENT'
    assert 'accept' not in row['allowed_actions']
    assert not calls


@pytest.mark.parametrize('payload', [{'action': 'continue'}, {'action': 'unknown'}, {}])
def test_write_or_unknown_action_is_never_replayed_as_a_read(tmp_path, monkeypatch, payload):
    monkeypatch.setattr(operations, 'replay_read',
                        lambda *args, **kwargs: pytest.fail('A write was replayed.'))
    with pytest.raises(proposal_currentness._BasisNotCurrent, match='not a read operation'):
        proposal_currentness._observe_read(tmp_path, {'project': 'fixture', 'id': 'WT-example'},
            {'id': 'READ-invalid', 'operation': 'work_delivery', 'payload': payload}, {})
