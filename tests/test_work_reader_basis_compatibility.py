"""Optional reader observations cannot invalidate accepted pre-M2 Work receipts."""
import copy
import hashlib
import json

import pytest
from laplace.work import project_work as work


# Frozen from the accepted M1 owner at bde831f591, not re-minted by this test.
REVISIONS = {
    'campaign': 'sha256:22c08c9e385c7d0d4c087b306b61313b9a6c4c0df1dac2fcf86cd637d5e0371b',
    'editor': 'sha256:d9b05cdff7c2811d740e14e635ae5aeaed3b47f3957520b5f580a7b17fc9607d',
    'source': 'sha256:68a80018bf53535c3733846e5331c507fbb8157b0688919d4f93f957aeb84f89',
}
ACCEPTED_BASIS = {
    'work_id': 'source', 'revision': REVISIONS['source'],
    'scope_revision': 'sha256:8b5bcc5e4ff1d5ed271e10509d9c557cf4d9d025bd0dbf31f0a20107e896a541',
    'parent': {'work_id': 'editor',
               'scope_revision': 'sha256:30eebbb3001f52cec40dd410a2c940e1b0fa118dce0b584251c3488c8dfc3921'},
}


def legacy_tasks():
    return {ident: {'id': ident, 'project': 'p', 'title': title, 'goal': goal,
                   'task_kind': kind, 'parent_work_id': parent, 'depends_on': [], 'section_ids': []}
            for ident, title, goal, kind, parent in (
                ('campaign', 'Programme', 'Ship the editor', 'campaign', None),
                ('editor', 'Editor', 'Close the source loop', 'execution', 'campaign'),
                ('source', 'Source effects', 'Preserve committed source truth', 'execution', 'editor'))}


@pytest.mark.parametrize('explicit_null', [False, True])
def test_old_task_and_parent_scope_hashes_remain_byte_identical(explicit_null):
    tasks = legacy_tasks()
    if explicit_null:
        for row in tasks.values():
            row['reader_basis'] = None
    assert {ident: work._task_revision(row) for ident, row in tasks.items()} == REVISIONS
    assert work._work_basis(tasks, 'source') == (ACCEPTED_BASIS, None)


def test_existing_accepted_parent_chain_recovers_without_rewriting_receipts(tmp_path):
    tasks = legacy_tasks()
    evidence = tmp_path / 'observed.txt'
    evidence.write_text('The source effect was independently checked.\n')
    tasks['source'].update(status='done', completion_work_basis=copy.deepcopy(ACCEPTED_BASIS),
        evidence_receipts=[{'path': 'observed.txt', 'sha256': hashlib.sha256(evidence.read_bytes()).hexdigest()}])
    ledger = work._ledger(tmp_path)
    ledger.parent.mkdir(parents=True)
    ledger.write_text(''.join(json.dumps({'record': 'project-work', 'task_id': ident,
        'status': row.get('status', 'open'), **row}) + '\n' for ident, row in tasks.items()))
    original = ledger.read_bytes()
    retained = work._tasks('p', tmp_path)
    observed = {row['id']: row for row in work._resolved_tasks(retained, tmp_path)}
    assert observed['source']['status'] == 'done'
    assert observed['source']['evidence_currentness']['status'] == 'CURRENT'
    assert retained['source']['completion_work_basis'] == ACCEPTED_BASIS
    assert ledger.read_bytes() == original
    # Real parent changes must still invalidate the old completion.
    retained['campaign']['goal'] = 'A genuinely changed programme'
    stale = work._completion_currentness(retained['source'], tmp_path, tasks=retained)
    assert stale['status'] == 'STALE' and stale['kind'] == 'WORK_SCOPE_CHANGED'
    assert ledger.read_bytes() == original


def test_non_null_reader_basis_remains_part_of_review_identity():
    row = legacy_tasks()['source']
    first = {**row, 'reader_basis': {'subject_revision': 'sha256:' + '1' * 64, 'inputs': {}}}
    second = {**row, 'reader_basis': {'subject_revision': 'sha256:' + '2' * 64, 'inputs': {}}}
    assert work._task_revision(first) != REVISIONS['source']
    assert work._task_revision(second) != work._task_revision(first)
    # An explicitly authored empty object is non-null too; it is not legacy absence.
    assert work._task_revision({**row, 'reader_basis': {}}) != REVISIONS['source']
